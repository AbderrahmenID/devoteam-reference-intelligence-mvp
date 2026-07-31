from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .abstention import decide_abstention, invalid_query_decision
from .bm25 import BM25Index
from .dense import DenseIndex, E5QueryEncoder, QueryEncoder
from .hybrid import HybridRetriever, HybridScores
from .language import analyze_language
from .normalization import exact_term_matches, json_values, normalize_search_text, term_coverage
from .schemas import RetrievalResult, ScoreComponents, SearchOutcome


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
        self.reference_by_row = {
            int(row["row_number"]): row for row in self.references.to_dict(orient="records")
        }
        self.bm25 = BM25Index.load(self.root / data["bm25_index"], self.root / data["bm25_vocabulary"])
        self.encoder = encoder or E5QueryEncoder(config["model"])
        self.dense = DenseIndex.load(self.root / data["embeddings"], self.encoder)
        self.hybrid = HybridRetriever(
            self.bm25, self.dense, self.chunks.chunk_id.astype(str).tolist(), config
        )
        self._filter_cache = self._build_filter_cache()

    def _build_filter_cache(self) -> dict[str, list[set[str]]]:
        output: dict[str, list[set[str]]] = {}
        for name, column in self.config["filters"]["supported_exact"].items():
            if column.endswith("_json"):
                output[name] = [
                    {normalize_search_text(value) for value in json_values(raw)} for raw in self.chunks[column]
                ]
            else:
                output[name] = [
                    {normalize_search_text(raw)} if str(raw or "").strip() else set()
                    for raw in self.chunks[column]
                ]
        return output

    def filter_mask(self, filters: dict[str, Any] | None = None) -> np.ndarray:
        settings = self.config["filters"]
        allowed_security = {normalize_search_text(value) for value in settings["allowed_security_classifications"]}
        mask = self.chunks.security_classification.map(
            lambda value: normalize_search_text(value) in allowed_security
        ).to_numpy(dtype=bool)
        requested_filters = filters or {}
        supported = set(settings["supported_exact"]) | set(settings["supported_ranges"])
        unknown = set(requested_filters) - supported
        if unknown:
            raise ValueError(f"Unsupported hard filters: {sorted(unknown)}")
        year_column = next(iter(set(settings["supported_ranges"].values())))
        year_cache = [
            {int(year) for value in json_values(raw) for year in __import__("re").findall(r"\b(?:19|20)\d{2}\b", value)}
            for raw in self.chunks[year_column]
        ]
        for name, requested in requested_filters.items():
            if requested is None or requested == "" or requested == []:
                continue
            if name in settings["supported_exact"]:
                values = requested if isinstance(requested, list) else [requested]
                wanted = {normalize_search_text(value) for value in values if str(value).strip()}
                if wanted:
                    mask &= np.asarray([bool(row_values & wanted) for row_values in self._filter_cache[name]])
            elif name == "year_before":
                try:
                    threshold = int(requested)
                except (TypeError, ValueError) as exc:
                    raise ValueError("year_before must be an integer") from exc
                mask &= np.asarray([bool(years) and any(year <= threshold for year in years) for years in year_cache])
            elif name == "year_after":
                try:
                    threshold = int(requested)
                except (TypeError, ValueError) as exc:
                    raise ValueError("year_after must be an integer") from exc
                mask &= np.asarray([bool(years) and any(year >= threshold for year in years) for years in year_cache])
        return mask

    def _group_references(self, query: str, scores: HybridScores) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        max_chunks = int(self.config["hybrid"]["evidence_chunks_per_reference"])
        for row_index in scores.fused_ranked:
            chunk = self.chunks.iloc[row_index].to_dict()
            reference_rows = [int(value) for value in json.loads(chunk["reference_rows_json"])]
            for reference_row in reference_rows:
                reference = self.reference_by_row.get(reference_row)
                if not reference or not bool(reference.get("document_retrieval_eligible")):
                    continue
                reference_id = str(reference["reference_id"])
                item = grouped.setdefault(reference_id, {
                    "reference": reference, "evidence": [], "best_fused": float(scores.fused[row_index]),
                    "best_bm25": float(scores.bm25[row_index]), "best_dense": float(scores.dense[row_index]),
                })
                item["best_fused"] = max(item["best_fused"], float(scores.fused[row_index]))
                item["best_bm25"] = max(item["best_bm25"], float(scores.bm25[row_index]))
                item["best_dense"] = max(item["best_dense"], float(scores.dense[row_index]))
                if len(item["evidence"]) < max_chunks:
                    item["evidence"].append({
                        "row": row_index, "chunk": chunk, "coverage": term_coverage(query, chunk["chunk_text"]),
                        "fused": float(scores.fused[row_index]), "bm25": float(scores.bm25[row_index]),
                        "dense": float(scores.dense[row_index]),
                    })
        return sorted(grouped.values(), key=lambda item: (-item["best_fused"], -item["best_dense"], str(item["reference"]["reference_id"])))

    def search(self, query: str, top_k: int = 3, filters: dict[str, Any] | None = None, debug: bool = False) -> SearchOutcome:
        started = time.perf_counter()
        language = analyze_language(query if isinstance(query, str) else "")
        invalid = invalid_query_decision(query, int(self.config["api"]["query_length_limit"]))
        if invalid:
            return SearchOutcome(
                query=query if isinstance(query, str) else "", detected_language=language.detected_language,
                scripts=language.scripts, rtl=language.rtl, abstained=True,
                abstention_reason=invalid.reason, result_count=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2), results=[],
                diagnostics=invalid.features if debug else None,
            )
        top_k = max(1, min(int(top_k), int(self.config["hybrid"]["maximum_final_results"])))
        mask = self.filter_mask(filters)
        if not mask.any():
            decision_features = {"eligible_chunks": 0, "candidate_references": 0}
            return SearchOutcome(
                query=query, detected_language=language.detected_language, scripts=language.scripts,
                rtl=language.rtl, abstained=True, abstention_reason="NO_ELIGIBLE_REFERENCE",
                result_count=0, latency_ms=round((time.perf_counter() - started) * 1000, 2),
                results=[], diagnostics=decision_features if debug else None,
            )
        scores = self.hybrid.score(query, mask)
        grouped = self._group_references(query, scores)
        top_dense_values = [float(scores.dense[row]) for row in scores.dense_ranked[:5]]
        best = grouped[0] if grouped else None
        features = {
            "eligible_chunks": int(mask.sum()), "candidate_references": len(grouped),
            "best_bm25": float(best["best_bm25"]) if best else 0.0,
            "best_dense": float(best["best_dense"]) if best else -1.0,
            "mean_top_dense": float(np.mean(top_dense_values)) if top_dense_values else -1.0,
            "best_term_coverage": max((e["coverage"] for e in best["evidence"]), default=0.0) if best else 0.0,
            "retriever_agreement": scores.top_retriever_agreement,
            "independent_passages": len(best["evidence"]) if best else 0,
            "evidence_concentration": round(len(best["evidence"]) / max(len(scores.fused_ranked), 1), 4) if best else 0.0,
        }
        decision = decide_abstention(query, features, self.config)
        results: list[RetrievalResult] = []
        if not decision.abstained:
            for rank, item in enumerate(grouped[:top_k], start=1):
                evidence = item["evidence"][0]
                chunk = evidence["chunk"]
                reference = item["reference"]
                matches = exact_term_matches(query, chunk["chunk_text"])
                reasons: list[str] = []
                if matches:
                    reasons.append("Exact terms: " + ", ".join(matches[:5]))
                if evidence["dense"] >= float(self.config["abstention"]["minimum_best_dense"]):
                    reasons.append("Multilingual semantic match")
                if evidence["row"] in scores.bm25_ranked[:10] and evidence["row"] in scores.dense_ranked[:10]:
                    reasons.append("BM25 and dense retrievers agree")
                if filters:
                    reasons.append("Matches requested metadata filters")
                title = str(reference.get("target_name") or "").strip()
                if not title:
                    title = str(reference.get("service_nature") or "Devoteam reference")[:140]
                results.append(RetrievalResult(
                    reference_id=str(reference["reference_id"]), title=title,
                    client=str(reference.get("client") or ""), sector=str(reference.get("sector") or ""),
                    offering=str(reference.get("offering") or ""), supporting_passage=str(chunk["chunk_text"]),
                    source_document=str(chunk["source_file_name"]), source_page=int(chunk["page_number_1_based"]),
                    citation_label=str(chunk["citation_label"]), citation_uri=str(chunk["citation_uri"]),
                    evidence_language=str(chunk.get("page_language") or chunk.get("document_language") or "und"),
                    match_reasons=reasons or ["Ranked by hybrid retrieval"], rank=rank,
                    score_components=ScoreComponents(
                        bm25_score=round(float(item["best_bm25"]), 6),
                        dense_cosine=round(float(item["best_dense"]), 6),
                        hybrid_rrf=round(float(item["best_fused"]), 8),
                        query_term_coverage=round(float(evidence["coverage"]), 6),
                        supporting_passages=len(item["evidence"]),
                    ),
                ))
        return SearchOutcome(
            query=query, detected_language=language.detected_language, scripts=language.scripts,
            rtl=language.rtl, abstained=decision.abstained, abstention_reason=decision.reason,
            result_count=len(results), latency_ms=round((time.perf_counter() - started) * 1000, 2),
            results=results, diagnostics=decision.features if debug else None,
        )

    def rank_reference_ids(
        self, query: str, limit: int = 20, filters: dict[str, Any] | None = None
    ) -> list[str]:
        """Expose deeper rankings for human-label evaluation without duplicating retrieval logic."""
        invalid = invalid_query_decision(query, int(self.config["api"]["query_length_limit"]))
        if invalid:
            return []
        mask = self.filter_mask(filters)
        if not mask.any():
            return []
        scores = self.hybrid.score(query, mask)
        grouped = self._group_references(query, scores)
        return [str(item["reference"]["reference_id"]) for item in grouped[: max(0, int(limit))]]
