from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from retrieval.service import RetrievalService


SEED = "devoteam-mvp-technical-packet-v1"
TECHNICAL_QUERIES = [
    ("TECH-FR-001", "Références de plan de continuité d’activité pour une banque", "fr", "SUPPORTED"),
    ("TECH-EN-001", "Bank business continuity planning references", "en", "SUPPORTED"),
    ("TECH-AR-001", "مراجع حول استمرارية الأعمال للبنوك", "ar", "SUPPORTED"),
    ("TECH-MIX-001", "PCA للبنوك en Tunisie", "mixed", "SUPPORTED"),
    ("TECH-NEG-001", "recette de cuisine pour gâteau au chocolat", "fr", "UNSUPPORTED"),
]


def _blind_key(query_id: str, reference_id: str) -> str:
    return hashlib.sha256(f"{SEED}|{query_id}|{reference_id}".encode("utf-8")).hexdigest()


def create_packet(root: Path) -> dict:
    root = root.resolve()
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    service = RetrievalService(root, config)
    output = root / "evaluation" / "judging"
    output.mkdir(parents=True, exist_ok=True)

    query_rows: list[dict] = []
    judging_rows: list[dict] = []
    diagnostic_rows: list[dict] = []
    for query_id, query_text, language, scope in TECHNICAL_QUERIES:
        outcome = service.search(query_text, page=1, page_size=50, sort="relevance")
        query_rows.append(
            {
                "query_id": query_id,
                "query_text": query_text,
                "query_language": language,
                "origin": "EXISTING_TECHNICAL_SMOKE",
                "official_development_query": False,
                "system_abstained": outcome.abstained,
                "system_abstention_reason": outcome.abstention_reason,
                "system_result_count": outcome.total_count,
                "human_query_approval": "",
                "human_no_answer_expected": "",
                "reviewer_id": "",
                "reviewer_comments": "",
            }
        )
        results = list(outcome.results[:20])
        blinded = sorted(results, key=lambda result: _blind_key(query_id, result.reference_id))
        candidate_ids = {
            result.reference_id: f"{query_id}-C{index:02d}"
            for index, result in enumerate(blinded, start=1)
        }
        for result in blinded:
            primary = result.supporting_passages[0]
            candidate_id = candidate_ids[result.reference_id]
            judging_rows.append(
                {
                    "query_id": query_id,
                    "candidate_id": candidate_id,
                    "query_text": query_text,
                    "query_language": language,
                    "project_title": result.project_title,
                    "client": result.client,
                    "country": result.country,
                    "sector": result.sector,
                    "offerings": ";".join(result.offerings),
                    "service_nature": result.service_nature,
                    "evidence_excerpt": primary.text,
                    "source_document": primary.source_document,
                    "source_page": primary.source_page,
                    "citation_label": primary.citation_label,
                    "relevance_0_1_2": "",
                    "wrong_evidence_chunk_yes_no": "",
                    "failure_category": "",
                    "evidence_notes": "",
                    "reviewer_id": "",
                    "reviewed_at": "",
                }
            )
            diagnostic_rows.append(
                {
                    "query_id": query_id,
                    "candidate_id": candidate_id,
                    "reference_id": result.reference_id,
                    "serving_rank": result.rank,
                    "bm25_score": result.score_components.bm25_score,
                    "dense_cosine": result.score_components.dense_cosine,
                    "hybrid_rrf": result.score_components.hybrid_rrf,
                    "query_term_coverage": result.score_components.query_term_coverage,
                    "source_document": primary.source_document,
                    "source_page": primary.source_page,
                    "relevance_judgment": "",
                }
            )

    pd.DataFrame(query_rows).to_csv(
        output / "TECHNICAL_QUERY_REVIEW.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL
    )
    pd.DataFrame(judging_rows).to_csv(
        output / "TECHNICAL_CANDIDATE_POOL_BLINDED.csv",
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
    )
    pd.DataFrame(diagnostic_rows).to_csv(
        output / "TECHNICAL_CANDIDATE_DIAGNOSTICS_INTERNAL.csv",
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
    )
    intake_rows = [
        {
            "query_id": f"DEV-{index:03d}",
            "query_text": "",
            "language": "",
            "business_context": "",
            "mandatory_filters_json": "{}",
            "query_type": "",
            "origin": "",
            "not_derived_from_reference_corpus_yes_no": "",
            "approved_for_development_yes_no": "",
            "author_or_owner": "",
            "notes": "",
        }
        for index in range(1, 51)
    ]
    pd.DataFrame(intake_rows).to_csv(
        output / "DEVELOPMENT_QUERY_INTAKE.csv",
        index=False,
        encoding="utf-8",
        quoting=csv.QUOTE_MINIMAL,
    )
    return {
        "technical_queries": len(query_rows),
        "blinded_candidates": len(judging_rows),
        "development_query_slots": len(intake_rows),
        "judgment_fields_left_blank": True,
    }


def main() -> int:
    result = create_packet(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
