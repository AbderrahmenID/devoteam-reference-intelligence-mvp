from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .abstention import decide_abstention, invalid_query_decision
from .aggregation import aggregate_reference
from .bm25 import BM25Index
from .dense import DenseIndex, E5QueryEncoder, QueryEncoder
from .evidence import EvidenceQualityEvaluator, select_best_evidence
from .field_bm25 import FieldAwareBM25, FieldAwareScores
from .hybrid import HybridRetriever, HybridScores
from .language import analyze_language
from .metadata import NormalizedReference, ReferenceMetadataIndex
from .normalization import normalize_search_text
from .relevance import decide_relevance
from .schemas import EvidencePassage, MatchReason, RetrievalResult, ScoreComponents, SearchOutcome
from .terms import (
    analyze_query_terms,
    matched_meaningful_terms,
    meaningful_term_coverage,
    metadata_supports_concepts,
)


ALLOWED_SORTS = {"relevance", "newest", "oldest", "project_title", "client", "country"}


class RetrievalService:
    def __init__(self, root: Path, config: dict, encoder: QueryEncoder | None = None):
        self.root = root.resolve()
        self.config = config
        data = config["data"]
        self.chunks = pd.read_parquet(self.root / data["chunks"]).reset_index(drop=True)
        self.references = pd.read_parquet(self.root / data["reference_catalog"]).reset_index(drop=True)
        self.lookup = pd.read_parquet(self.root / data["chunk_lookup"]).reset_index(drop=True)
        if self.chunks.chunk_id.astype(str).tolist() != self.lookup.chunk_id.astype(str).tolist():
            raise AssertionError("Chunk and embedding lookup order differ")
        self.metadata = ReferenceMetadataIndex(self.references, self.chunks)
        self.bm25 = BM25Index.load(self.root / data["bm25_index"], self.root / data["bm25_vocabulary"])
        self.encoder = encoder or E5QueryEncoder(config["model"])
        self.dense = DenseIndex.load(self.root / data["embeddings"], self.encoder)
        self.hybrid = HybridRetriever(
            self.bm25, self.dense, self.chunks.chunk_id.astype(str).tolist(), config
        )
        self.field_bm25 = (
            FieldAwareBM25(self.metadata, self.chunks, config["field_bm25"], config["bm25"])
            if config.get("field_bm25", {}).get("enabled", False)
            else None
        )
        self.evidence_evaluator = EvidenceQualityEvaluator(config["evidence_quality"])
        allowed_security = {
            normalize_search_text(value)
            for value in config["filters"]["allowed_security_classifications"]
        }
        self._security_mask = self.chunks.security_classification.map(
            lambda value: normalize_search_text(value) in allowed_security
        ).to_numpy(dtype=bool)

    def _field_lexical_scores(
        self,
        query: str,
        eligible_ids: set[str],
        mask: np.ndarray,
    ) -> tuple[Any, FieldAwareScores | None, np.ndarray | None]:
        query_terms = analyze_query_terms(
            query, self.bm25, self.config["meaningful_terms"]
        )
        if self.field_bm25 is None:
            return query_terms, None, None
        field_scores = self.field_bm25.score(query_terms, eligible_ids)
        projected = np.full(len(self.chunks), -np.inf, dtype=np.float32)
        for reference_id in eligible_ids:
            reference = self.metadata.by_id.get(reference_id)
            if reference is None:
                continue
            score = float(field_scores.combined[field_scores.reference_ids.index(reference_id)])
            for row in reference.linked_chunk_indices:
                if mask[row]:
                    projected[row] = max(float(projected[row]), score)
        return query_terms, field_scores, projected

    @property
    def safety_ceiling(self) -> int:
        return int(self.config["search"]["safety_ceiling"])

    def facets(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        eligible_ids, applied, resolved = self.metadata.resolve_filters(filters)
        return {
            "applied_filters": applied,
            "resolved_period": resolved,
            "eligible_reference_count": len(eligible_ids),
            "facets": self.metadata.facets(eligible_ids),
        }

    def _mask_for_reference_ids(self, eligible_ids: set[str]) -> np.ndarray:
        mask = np.zeros(len(self.chunks), dtype=bool)
        for reference_id in eligible_ids:
            reference = self.metadata.by_id.get(reference_id)
            if reference:
                mask[reference.linked_chunk_indices] = True
        return mask & self._security_mask

    def filter_mask(self, filters: dict[str, Any] | None = None) -> np.ndarray:
        eligible_ids, _, _ = self.metadata.resolve_filters(filters)
        return self._mask_for_reference_ids(eligible_ids)

    def _group_references(
        self,
        query: str,
        scores: HybridScores,
        eligible_ids: set[str],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        max_chunks = int(self.config["evidence_quality"]["candidate_pool_per_reference"])
        for row_index in scores.fused_ranked:
            chunk = self.chunks.iloc[row_index].to_dict()
            try:
                reference_rows = [int(value) for value in json.loads(chunk["reference_rows_json"])]
            except (TypeError, ValueError, json.JSONDecodeError):
                reference_rows = []
            candidate_ids = {
                reference_id
                for row in reference_rows
                for reference_id in self.metadata.reference_ids_by_row.get(row, [])
            }
            for reference_id in sorted(candidate_ids & eligible_ids):
                reference = self.metadata.by_id[reference_id]
                item = grouped.setdefault(
                    reference_id,
                    {
                        "reference": reference,
                        "evidence": [],
                        "all_rows": [],
                        "best_fused": float(scores.fused[row_index]),
                        "best_bm25": float(scores.bm25[row_index]),
                        "best_dense": float(scores.dense[row_index]),
                    },
                )
                item["best_fused"] = max(item["best_fused"], float(scores.fused[row_index]))
                item["best_bm25"] = max(item["best_bm25"], float(scores.bm25[row_index]))
                item["best_dense"] = max(item["best_dense"], float(scores.dense[row_index]))
                item["all_rows"].append(row_index)
                if len(item["evidence"]) < max_chunks:
                    item["evidence"].append(
                        {
                            "row": row_index,
                            "chunk": chunk,
                            "coverage": meaningful_term_coverage(
                                scores.query_terms, chunk["chunk_text"]
                            ),
                            "fused": float(scores.fused[row_index]),
                            "bm25": float(scores.bm25[row_index]),
                            "dense": float(scores.dense[row_index]),
                        }
                    )
        return sorted(
            grouped.values(),
            key=lambda item: (
                -item["best_fused"],
                -item["best_dense"],
                item["reference"].reference_id,
            ),
        )

    def _attach_reference_signals(
        self,
        grouped: list[dict[str, Any]],
        field_scores: FieldAwareScores | None,
    ) -> None:
        dense_order = sorted(
            grouped,
            key=lambda item: (-float(item["best_dense"]), item["reference"].reference_id),
        )
        dense_rank = {
            item["reference"].reference_id: rank for rank, item in enumerate(dense_order, start=1)
        }
        if field_scores is None:
            for item in grouped:
                item["field_diagnostics"] = {}
                item["reference_retriever_agreement"] = 0
            return
        field_order = sorted(
            (
                reference_id
                for reference_id in field_scores.reference_ids
                if np.isfinite(field_scores.combined[field_scores.reference_ids.index(reference_id)])
            ),
            key=lambda reference_id: (
                -float(field_scores.combined[field_scores.reference_ids.index(reference_id)]),
                reference_id,
            ),
        )
        lexical_rank = {reference_id: rank for rank, reference_id in enumerate(field_order, start=1)}
        depth = int(self.config["hybrid"]["per_candidate_agreement_depth"])
        for item in grouped:
            reference_id = item["reference"].reference_id
            item["field_diagnostics"] = field_scores.diagnostics_for(reference_id)
            item["reference_retriever_agreement"] = int(
                lexical_rank.get(reference_id, depth + 1) <= depth
                and dense_rank.get(reference_id, depth + 1) <= depth
            )

    def _select_evidence(
        self,
        item: dict[str, Any],
        query_language: str,
    ) -> None:
        reference: NormalizedReference = item["reference"]
        reference_text = " ".join(
            value
            for value in (
                reference.service_nature,
                reference.offering,
                reference.sector,
                " ".join(reference.technologies),
                " ".join(reference.key_themes),
            )
            if value
        )
        item["metadata_compatibility"] = metadata_supports_concepts(
            item["scores"].query_terms.concepts, reference_text
        )
        selected, evaluated = select_best_evidence(
            item["evidence"],
            item["scores"].query_terms,
            query_language,
            reference_text,
            self.evidence_evaluator,
            self.config["meaningful_terms"],
            self.config["evidence_quality"],
        )
        item["evidence"] = selected
        item["evaluated_evidence"] = evaluated

    def _candidate_features(
        self,
        item: dict[str, Any],
        eligible_chunk_count: int,
    ) -> dict[str, Any]:
        rows = item["all_rows"]
        best_bm25_row = max(rows, key=lambda row: float(item["scores"].bm25[row]))
        best_dense_row = max(rows, key=lambda row: float(item["scores"].dense[row]))
        agreement_depth = int(self.config["hybrid"]["per_candidate_agreement_depth"])
        lexical_top = set(item["scores"].bm25_ranked[:agreement_depth])
        dense_top = set(item["scores"].dense_ranked[:agreement_depth])
        agreed_rows = set(rows) & lexical_top & dense_top
        dense_values = sorted(
            (float(item["scores"].dense[row]) for row in rows), reverse=True
        )[:5]
        field_diagnostics = item.get("field_diagnostics", {})
        exact_matches = field_diagnostics.get("exact_matches", {})
        strong_fields = {
            "title", "mission_name", "services_delivered", "description", "technologies", "evidence"
        }
        strong_exact_terms = {
            term
            for field, terms in exact_matches.items()
            if field in strong_fields
            for term in terms
        }
        term_categories = {
            term.normalized: term.category for term in item["scores"].query_terms.meaningful_terms
        }
        technology_matches = {
            term
            for term in strong_exact_terms
            if term_categories.get(term) in {"technology", "acronym"}
        }
        selected_evidence = item["evidence"]
        valid_lineage = all(
            str(evidence["chunk"].get("source_file_name") or "").strip()
            and int(evidence["chunk"].get("page_number_1_based") or 0) > 0
            and str(evidence["chunk"].get("citation_uri") or "").strip()
            for evidence in selected_evidence
        ) and bool(selected_evidence)
        return {
            "eligible_chunks": eligible_chunk_count,
            "candidate_references": 1,
            "best_bm25": float(item["best_bm25"]),
            "best_dense": float(item["best_dense"]),
            "mean_top_dense": float(np.mean(dense_values)) if dense_values else -1.0,
            "best_term_coverage": max(
                (evidence["coverage"] for evidence in item["evidence"]), default=0.0
            ),
            "retriever_agreement": (
                2 if agreed_rows and best_bm25_row == best_dense_row else (1 if agreed_rows else 0)
            ),
            "independent_passages": len(item["evidence"]),
            "clean_evidence_passages": len(item["evidence"]),
            "best_evidence_quality": max(
                (evidence["quality"].quality_score for evidence in item["evidence"]),
                default=0.0,
            ),
            "best_selected_dense": max(
                (float(evidence["dense"]) for evidence in item["evidence"]),
                default=-1.0,
            ),
            "cross_language_evidence": any(
                bool(evidence["quality"].diagnostics["semantic_cross_language_support"])
                for evidence in item["evidence"]
            ),
            "meaningful_query_token_count": len(item["scores"].query_terms.bm25_tokens),
            "query_concepts": item["scores"].query_terms.concepts,
            "metadata_compatibility": bool(item.get("metadata_compatibility", True)),
            "evidence_concentration": round(len(rows) / max(eligible_chunk_count, 1), 4),
            "strong_exact_term_count": len(strong_exact_terms),
            "technology_acronym_match_count": len(technology_matches),
            "capability_field_support": len(
                set(field_diagnostics.get("matched_fields", []))
                & {"title", "mission_name", "services_delivered", "description", "technologies"}
            ),
            "evidence_field_support": "evidence" in set(
                field_diagnostics.get("matched_fields", [])
            ),
            "reference_retriever_agreement": int(
                item.get("reference_retriever_agreement", 0)
            ),
            "project_specific_evidence": any(
                bool(evidence["quality"].diagnostics.get("project_delivery_signal"))
                for evidence in selected_evidence
            ),
            "valid_lineage": valid_lineage,
            "field_diagnostics": field_diagnostics,
        }

    def _build_result(
        self,
        item: dict[str, Any],
        query: str,
        relevance_rank: int,
        applied_filters: dict[str, Any],
        query_language: str,
    ) -> RetrievalResult:
        reference: NormalizedReference = item["reference"]
        evidence_models: list[EvidencePassage] = []
        for evidence in item["evidence"]:
            chunk = evidence["chunk"]
            evidence_models.append(
                EvidencePassage(
                    text=str(evidence["display_text"]),
                    source_document=str(chunk["source_file_name"]),
                    source_page=int(chunk["page_number_1_based"]),
                    citation_label=str(chunk["citation_label"]),
                    citation_uri=str(chunk["citation_uri"]),
                    language=str(chunk.get("page_language") or chunk.get("document_language") or "und"),
                )
            )
        primary = evidence_models[0]
        primary_raw = item["evidence"][0]
        matches = matched_meaningful_terms(item["scores"].query_terms, primary.text)
        match_details: list[MatchReason] = []

        def add_reason(category: str, values: list[str], description: str) -> None:
            cleaned = list(dict.fromkeys(value for value in values if value))
            if cleaned or category in {"Semantic similarity", "Cross-language semantic match"}:
                match_details.append(
                    MatchReason(category=category, values=cleaned, description=description)
                )

        field_exact = item.get("field_diagnostics", {}).get("exact_matches", {})
        exact_values = {
            value
            for field in ("title", "mission_name", "services_delivered", "technologies", "evidence")
            for value in field_exact.get(field, [])
        }
        term_by_normalized = {
            term.normalized: term for term in item["scores"].query_terms.meaningful_terms
        }
        technologies = list(
            dict.fromkeys(
                term_by_normalized[value].display
                for value in exact_values
                if value in term_by_normalized
                and term_by_normalized[value].category in {"technology", "acronym"}
            )
        )[:4]
        if technologies:
            add_reason(
                "Confirmed technology or capability",
                technologies,
                "Evidence confirms project work involving " + ", ".join(technologies) + ".",
            )

        metadata_fields = (
            ("Matching offering", reference.offering),
            ("Matching sector", reference.sector),
        )
        for category, value in metadata_fields:
            field_matches = matched_meaningful_terms(item["scores"].query_terms, value)
            if field_matches:
                description = (
                    f"Relevant experience in the {value} sector."
                    if category == "Matching sector"
                    else f"Matches the requested {value} offering."
                )
                add_reason(category, [value], description)
        capability_matches = matched_meaningful_terms(
            item["scores"].query_terms, reference.service_nature
        )
        capability_values = list(dict.fromkeys(match.display for match in capability_matches))[:4]
        if capability_values:
            add_reason(
                "Matching capability",
                capability_values,
                "Matches the requested capability: " + ", ".join(capability_values) + ".",
            )

        evidence_language = primary.language.casefold()
        if item["best_dense"] >= float(self.config["abstention"]["minimum_best_dense"]):
            cross_language = (
                query_language not in {"und", "mixed"}
                and evidence_language not in {"und", "mixed", query_language}
            )
            category = "Cross-language semantic match" if cross_language else "Semantic similarity"
            description = (
                "Cross-language evidence describes the requested project capability."
                if cross_language
                else "Supporting evidence describes the requested project capability."
            )
            add_reason(category, [], description)

        if primary_raw["quality"].diagnostics.get("project_delivery_signal"):
            add_reason(
                "Confirmed delivery evidence",
                [primary.citation_label],
                "Supporting evidence confirms delivered project services.",
            )

        if "country" in applied_filters:
            values = [str(value) for value in applied_filters["country"]]
            add_reason(
                "Matching country/filter",
                values,
                "Project country matches the selected filter: " + ", ".join(values) + ".",
            )
        if "period" in applied_filters:
            period = applied_filters["period"]
            value = f"{period['start_year']}–{period['end_year']}"
            add_reason(
                "Matching period/filter",
                [value],
                "Project period overlaps the selected date range " + value + ".",
            )

        reasons = [reason.description for reason in match_details]
        if not reasons and matches:
            values = list(dict.fromkeys(match.display for match in matches))[:4]
            add_reason(
                "Matching capability",
                values,
                "Selected evidence contains the requested capability: " + ", ".join(values) + ".",
            )
            reasons = [reason.description for reason in match_details]

        display_title = self._display_title(reference.project_title, reference.client)
        return RetrievalResult(
            reference_id=reference.reference_id,
            reference_number=reference.reference_number,
            display_title=display_title,
            project_title=reference.project_title,
            mission_name=reference.mission_name,
            client=reference.client,
            contracting_authority=reference.client,
            country=reference.country,
            country_code=reference.country_code,
            country_label=reference.country,
            project_start_year=reference.start_year,
            project_end_year=reference.source_end_year,
            project_ongoing=reference.status == "ongoing",
            project_start_date=str(reference.start_year) if reference.start_year else None,
            completion_date=(
                str(reference.source_end_year)
                if reference.source_end_year and reference.status != "ongoing"
                else None
            ),
            period=reference.period,
            period_display=reference.period,
            status=reference.status,
            sector=reference.sector,
            offerings=[reference.offering] if reference.offering else [],
            service_nature=reference.service_nature,
            technologies=reference.technologies,
            key_themes=reference.key_themes,
            themes=reference.key_themes,
            description=reference.service_nature,
            services_delivered=[passage.text for passage in evidence_models],
            supporting_passages=evidence_models,
            evidence_available=reference.evidence_available,
            evidence_types=reference.evidence_types,
            evidence_type=reference.evidence_types,
            document_languages=reference.document_languages,
            match_reasons=reasons,
            match_details=match_details,
            rank=relevance_rank,
            relevance_rank=relevance_rank,
            score_components=ScoreComponents(
                bm25_score=round(float(item["best_bm25"]), 6),
                dense_cosine=round(float(item["best_dense"]), 6),
                hybrid_rrf=round(
                    float(item.get("aggregation").score if item.get("aggregation") else item["best_fused"]),
                    8,
                ),
                query_term_coverage=round(float(primary_raw["coverage"]), 6),
                supporting_passages=len(item["evidence"]),
            ),
            title=reference.project_title,
            offering=reference.offering,
            supporting_passage=primary.text,
            source_document=primary.source_document,
            source_page=primary.source_page,
            citation_label=primary.citation_label,
            citation_uri=primary.citation_uri,
            source_uri=primary.citation_uri,
            evidence_language=primary.language,
        )

    @staticmethod
    def _display_title(project_title: str, client: str, maximum: int = 96) -> str:
        """Return a deterministic commercial label without changing source text."""
        bullet = "\u2022"
        normalized = " ".join((project_title or "").split()).strip(f" -{bullet}|")
        for separator in (f" {bullet} ", " | ", "\n", " - Phase", " - Etape", " - \u00c9tape"):
            if separator in normalized:
                candidate = normalized.split(separator, 1)[0].strip(f" -{bullet}|,.;:")
                if len(candidate) >= 18:
                    normalized = candidate
                    break
        if not normalized:
            normalized = " ".join((client or "R\u00e9f\u00e9rence Devoteam").split())
        if len(normalized) <= maximum:
            return normalized
        shortened = normalized[: maximum + 1].rsplit(" ", 1)[0].rstrip(f" -{bullet}|,.;:")
        return shortened or normalized[:maximum].rstrip()

    @staticmethod
    def _sort_results(results: list[RetrievalResult], sort: str) -> list[RetrievalResult]:
        if sort == "relevance":
            return results
        if sort == "newest":
            return sorted(
                results,
                key=lambda result: (
                    -(int(result.completion_date or result.project_start_date or -1)),
                    result.relevance_rank,
                ),
            )
        if sort == "oldest":
            return sorted(
                results,
                key=lambda result: (
                    int(result.project_start_date or 9999),
                    result.relevance_rank,
                ),
            )
        attribute = {"project_title": "project_title", "client": "client", "country": "country"}[sort]
        return sorted(
            results,
            key=lambda result: (normalize_search_text(getattr(result, attribute)), result.relevance_rank),
        )

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int = 20,
        sort: str = "relevance",
        debug: bool = False,
        include_facets: bool = False,
    ) -> SearchOutcome:
        started = time.perf_counter()
        language = analyze_language(query if isinstance(query, str) else "")
        eligible_ids, applied_filters, resolved_period = self.metadata.resolve_filters(filters)
        if sort not in ALLOWED_SORTS:
            raise ValueError(f"Unknown sort: {sort}")
        allowed_page_sizes = set(int(value) for value in self.config["search"]["page_sizes"])
        if page_size not in allowed_page_sizes and page_size != self.safety_ceiling:
            raise ValueError(f"page_size must be one of {sorted(allowed_page_sizes)}")
        if page < 1:
            raise ValueError("page must be at least 1")
        page_size = min(page_size, self.safety_ceiling)

        common = {
            "query": query if isinstance(query, str) else "",
            "applied_filters": applied_filters,
            "resolved_period": resolved_period,
            "resolved_time_interval": resolved_period,
            "detected_language": language.detected_language,
            "scripts": language.scripts,
            "rtl": language.rtl,
            "page": page,
            "page_size": page_size,
            "sort": sort,
            "facets": self.metadata.facets(eligible_ids) if include_facets else None,
        }
        invalid = invalid_query_decision(query, int(self.config["api"]["query_length_limit"]))
        if invalid:
            return SearchOutcome(
                **common,
                abstained=True,
                abstention_reason=invalid.reason,
                total_count=0,
                result_count=0,
                total_pages=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                results=[],
                diagnostics=invalid.features if debug else None,
            )
        if not eligible_ids:
            diagnostics = {"eligible_chunks": 0, "candidate_references": 0}
            return SearchOutcome(
                **common,
                abstained=True,
                abstention_reason="NO_ELIGIBLE_REFERENCE",
                total_count=0,
                result_count=0,
                total_pages=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                results=[],
                diagnostics=diagnostics if debug else None,
            )

        mask = self._mask_for_reference_ids(eligible_ids)
        if not mask.any():
            return SearchOutcome(
                **common,
                abstained=True,
                abstention_reason="NO_ELIGIBLE_REFERENCE",
                total_count=0,
                result_count=0,
                total_pages=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                results=[],
                diagnostics={"eligible_chunks": 0, "candidate_references": 0} if debug else None,
            )

        query_terms, field_scores, lexical_scores = self._field_lexical_scores(
            query, eligible_ids, mask
        )
        scores = self.hybrid.score(
            query,
            mask,
            query_terms=query_terms,
            lexical_scores=lexical_scores,
        )
        grouped = self._group_references(query, scores, eligible_ids)
        self._attach_reference_signals(grouped, field_scores)
        retained: list[RetrievalResult] = []
        gate_diagnostics: dict[str, Any] = {}
        for item in grouped:
            item["scores"] = scores
            self._select_evidence(item, language.detected_language)
            aggregation_settings = self.config.get(
                "reference_aggregation",
                {"strategy": "A_MAX", "support_bonus": 0.0008},
            )
            item["aggregation"] = aggregate_reference(
                item["evidence"],
                strategy=str(aggregation_settings["strategy"]),
                field_diagnostics=item.get("field_diagnostics"),
                support_bonus=float(aggregation_settings.get("support_bonus", 0.0008)),
            )
            features = self._candidate_features(item, int(mask.sum()))
            decision = (
                decide_relevance(query, features, self.config)
                if self.config.get("relevance_gate", {}).get("enabled", False)
                else decide_abstention(query, features, self.config)
            )
            candidate_diagnostic = {
                "abstained": not decision.passed if hasattr(decision, "passed") else decision.abstained,
                "reason": decision.reason,
                **decision.features,
                "aggregation": {
                    "strategy": item["aggregation"].strategy,
                    "score": round(item["aggregation"].score, 10),
                    "best_chunk_id": item["aggregation"].best_chunk_id,
                    "supporting_chunk_id": item["aggregation"].supporting_chunk_id,
                    "explanation": item["aggregation"].explanation,
                },
            }
            if hasattr(decision, "patterns"):
                candidate_diagnostic["passing_patterns"] = decision.patterns
            if debug:
                candidate_diagnostic["evidence_selection"] = [
                    {
                        "chunk_id": str(evidence["chunk"]["chunk_id"]),
                        "quality_pass": evidence["quality"].quality_pass,
                        "quality_score": evidence["quality"].quality_score,
                        "rejection_reasons": evidence["quality"].rejection_reasons,
                        "diagnostics": evidence["quality"].diagnostics,
                        "selection_score": evidence["selection_score"],
                        "selected": evidence in item["evidence"],
                    }
                    for evidence in item["evaluated_evidence"]
                ]
            gate_diagnostics[item["reference"].reference_id] = candidate_diagnostic
            if (not decision.passed if hasattr(decision, "passed") else decision.abstained):
                continue

        passing_items = [
            item
            for item in grouped
            if not gate_diagnostics[item["reference"].reference_id]["abstained"]
        ]
        passing_items.sort(
            key=lambda item: (
                -float(item["aggregation"].score),
                -float(item["best_dense"]),
                item["reference"].reference_id,
            )
        )
        for item in passing_items:
            retained.append(
                self._build_result(
                    item,
                    query=query,
                    relevance_rank=len(retained) + 1,
                    applied_filters=applied_filters,
                    query_language=language.detected_language,
                )
            )

        sorted_results = self._sort_results(retained, sort)
        for rank, result in enumerate(sorted_results, start=1):
            result.rank = rank
        total_count = len(sorted_results)
        total_pages = math.ceil(total_count / page_size) if total_count else 0
        offset = (page - 1) * page_size
        page_results = sorted_results[offset : offset + page_size]
        abstained = total_count == 0
        gate_reasons = {value["reason"] for value in gate_diagnostics.values()}
        abstention_reason = (
            "UNSUPPORTED_PORTFOLIO_SCOPE"
            if abstained and gate_reasons == {"UNSUPPORTED_PORTFOLIO_SCOPE"}
            else ("NO_RELEVANT_REFERENCE" if abstained else "SUFFICIENT_EVIDENCE")
        )
        diagnostics = None
        if debug:
            diagnostics = {
                "eligible_references": len(eligible_ids),
                "eligible_chunks": int(mask.sum()),
                "candidate_references": len(grouped),
                "retained_references": total_count,
                "query_terms": scores.query_terms.diagnostics(),
                "field_aware_bm25": bool(self.field_bm25),
                "candidate_gates": gate_diagnostics,
            }
        return SearchOutcome(
            **common,
            abstained=abstained,
            abstention_reason=abstention_reason,
            total_count=total_count,
            result_count=len(page_results),
            total_pages=total_pages,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            results=page_results,
            diagnostics=diagnostics,
        )

    def all_results(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        sort: str = "relevance",
    ) -> SearchOutcome:
        return self.search(
            query=query,
            filters=filters,
            page=1,
            page_size=self.safety_ceiling,
            sort=sort,
            debug=False,
            include_facets=False,
        )

    def rank_reference_ids(
        self, query: str, limit: int = 20, filters: dict[str, Any] | None = None
    ) -> list[str]:
        """Expose deeper ungated rankings for human-label evaluation."""
        invalid = invalid_query_decision(query, int(self.config["api"]["query_length_limit"]))
        if invalid:
            return []
        eligible_ids, _, _ = self.metadata.resolve_filters(filters)
        mask = self._mask_for_reference_ids(eligible_ids)
        if not mask.any():
            return []
        query_terms, field_scores, lexical_scores = self._field_lexical_scores(
            query, eligible_ids, mask
        )
        scores = self.hybrid.score(
            query, mask, query_terms=query_terms, lexical_scores=lexical_scores
        )
        grouped = self._group_references(query, scores, eligible_ids)
        self._attach_reference_signals(grouped, field_scores)
        return [item["reference"].reference_id for item in grouped[: max(0, int(limit))]]
