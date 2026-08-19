from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .bm25 import BM25Index
from .metadata import NormalizedReference, ReferenceMetadataIndex, clean_text
from .normalization import normalize_search_text
from .terms import QueryTermAnalysis, matched_meaningful_terms


SEARCHABLE_FIELDS = (
    "title",
    "mission_name",
    "services_delivered",
    "description",
    "technologies",
    "offerings",
    "sector",
    "client",
    "evidence",
)


@dataclass(frozen=True)
class FieldAwareScores:
    reference_ids: list[str]
    combined: np.ndarray
    per_field: dict[str, np.ndarray]
    exact_matches: dict[str, dict[str, list[str]]]
    matched_fields: dict[str, list[str]]

    def diagnostics_for(self, reference_id: str) -> dict[str, Any]:
        row = self.reference_ids.index(reference_id)
        return {
            "combined_score": round(float(self.combined[row]), 8),
            "field_scores": {
                field: round(float(scores[row]), 8)
                for field, scores in self.per_field.items()
                if float(scores[row]) > 0.0
            },
            "exact_matches": self.exact_matches.get(reference_id, {}),
            "matched_fields": self.matched_fields.get(reference_id, []),
        }


def _remainder(full_text: str, prefix: str) -> str:
    if not full_text or not prefix:
        return ""
    normalized_full = normalize_search_text(full_text)
    prefix = prefix.rstrip(" .;:|-–—…")
    normalized_prefix = normalize_search_text(prefix)
    if normalized_full == normalized_prefix:
        return ""
    if normalize_search_text(full_text).startswith(normalized_prefix):
        return full_text[len(prefix) :].lstrip(" .;:|-–—")
    return full_text


class FieldAwareBM25:
    """Reference-level lexical retrieval over independently weighted fields.

    The source catalog has one rich ``service_nature`` field that is also used
    as the user-facing title.  The title-sized prefix is indexed as ``title``
    and any remaining text as ``services_delivered`` so the same source text is
    not counted several times merely because the API exposes aliases for it.
    """

    def __init__(
        self,
        metadata: ReferenceMetadataIndex,
        chunks: pd.DataFrame,
        settings: dict[str, Any],
        bm25_settings: dict[str, Any],
    ) -> None:
        self.settings = settings
        self.reference_ids = sorted(metadata.by_id)
        self.row_by_id = {reference_id: row for row, reference_id in enumerate(self.reference_ids)}
        self.documents = self._build_documents(metadata, chunks)
        self.indexes = {
            field: BM25Index.build(
                [self.documents[reference_id][field] for reference_id in self.reference_ids],
                k1=float(bm25_settings["k1"]),
                b=float(bm25_settings["b"]),
                allow_empty=True,
            )
            for field in SEARCHABLE_FIELDS
        }

    @staticmethod
    def _valid_evidence(chunk: dict[str, Any]) -> bool:
        return (
            bool(chunk.get("approved_for_retrieval", True))
            and bool(clean_text(chunk.get("source_file_name")))
            and int(chunk.get("page_number_1_based") or 0) > 0
            and bool(clean_text(chunk.get("citation_uri")))
        )

    def _build_documents(
        self,
        metadata: ReferenceMetadataIndex,
        chunks: pd.DataFrame,
    ) -> dict[str, dict[str, str]]:
        documents: dict[str, dict[str, str]] = {}
        for reference_id in self.reference_ids:
            reference: NormalizedReference = metadata.by_id[reference_id]
            evidence_parts: list[str] = []
            for row in reference.linked_chunk_indices:
                chunk = chunks.iloc[row].to_dict()
                if self._valid_evidence(chunk):
                    evidence_parts.append(clean_text(chunk.get("retrieval_text") or chunk.get("chunk_text")))
            title = clean_text(reference.project_title)
            mission = clean_text(reference.mission_name)
            title_prefix = normalize_search_text(title.rstrip(" .;:|-–—…"))
            documents[reference_id] = {
                "title": title,
                "mission_name": (
                    ""
                    if title_prefix and normalize_search_text(mission).startswith(title_prefix)
                    else mission
                ),
                "services_delivered": _remainder(clean_text(reference.service_nature), title),
                "description": "",
                "technologies": " ".join(reference.technologies),
                "offerings": clean_text(reference.offering),
                "sector": clean_text(reference.sector),
                "client": clean_text(reference.client),
                "evidence": "\n".join(part for part in evidence_parts if part),
            }
        return documents

    def score(
        self,
        query_terms: QueryTermAnalysis,
        eligible_ids: set[str],
    ) -> FieldAwareScores:
        allowed = np.asarray(
            [reference_id in eligible_ids for reference_id in self.reference_ids], dtype=bool
        )
        weights = self.settings["weights"]
        exact_settings = self.settings["exact_match"]
        per_field: dict[str, np.ndarray] = {}
        combined = np.full(len(self.reference_ids), -np.inf, dtype=np.float32)
        combined[allowed] = 0.0
        exact_matches: dict[str, dict[str, list[str]]] = {}
        matched_fields: dict[str, list[str]] = {}

        for field in SEARCHABLE_FIELDS:
            raw = self.indexes[field].score(
                query_terms.normalized_query,
                allowed,
                query_tokens=query_terms.bm25_tokens,
            )
            finite = raw[allowed & np.isfinite(raw)]
            maximum = float(finite.max()) if finite.size else 0.0
            normalized = np.zeros(len(raw), dtype=np.float32)
            if maximum > 0:
                normalized[allowed] = np.maximum(raw[allowed], 0.0) / maximum
            normalized[~allowed] = -np.inf
            per_field[field] = normalized
            combined[allowed] += float(weights[field]) * normalized[allowed]

        base_bonus = float(exact_settings["per_term"])
        maximum_bonus = float(exact_settings["maximum"])
        strong_multiplier = float(exact_settings["technology_acronym_multiplier"])
        field_multipliers = exact_settings.get("field_multipliers", {})
        for reference_id in self.reference_ids:
            if reference_id not in eligible_ids:
                continue
            row = self.row_by_id[reference_id]
            reference_matches: dict[str, list[str]] = {}
            for field in SEARCHABLE_FIELDS:
                matches = matched_meaningful_terms(query_terms, self.documents[reference_id][field])
                if not matches:
                    continue
                unique = list(dict.fromkeys(match.normalized for match in matches))
                reference_matches[field] = unique
                bonus = 0.0
                for match in matches:
                    multiplier = strong_multiplier if match.category in {"technology", "acronym"} else 1.0
                    bonus += base_bonus * multiplier
                combined[row] += min(bonus, maximum_bonus) * float(
                    field_multipliers.get(field, 1.0)
                )
            exact_matches[reference_id] = reference_matches
            matched_fields[reference_id] = sorted(reference_matches)

        return FieldAwareScores(
            reference_ids=self.reference_ids,
            combined=combined,
            per_field=per_field,
            exact_matches=exact_matches,
            matched_fields=matched_fields,
        )
