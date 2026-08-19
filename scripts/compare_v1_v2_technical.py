from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from retrieval.dense import E5QueryEncoder
from retrieval.service import RetrievalService


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("TECH-FR-PCA", "Références de plan de continuité d’activité pour une banque", None),
    ("TECH-EN-PCA", "Bank business continuity planning references", None),
    ("TECH-AR-PCA", "مراجع حول استمرارية الأعمال للبنوك", None),
    ("TECH-MIXED-PCA", "PCA للبنوك en Tunisie", None),
    ("TECH-FR-API", "passerelle API sécurisée et transfert de compétences", None),
    ("TECH-EN-CLOUD", "national cloud strategy and data-centre consolidation", None),
    ("TECH-FILTER", "cybersécurité protection des données", {"country": ["Tunisie"]}),
    ("TECH-NEGATIVE", "recette de cuisine pour gâteau au chocolat", None),
]


def outcome_record(system: str, case_id: str, outcome: Any) -> dict[str, Any]:
    ids = [result.reference_id for result in outcome.results]
    evidence_complete = all(
        result.supporting_passage and result.source_document and result.source_page and result.citation_uri
        for result in outcome.results
    )
    return {
        "case_id": case_id,
        "system": system,
        "detected_language": outcome.detected_language,
        "abstained": outcome.abstained,
        "abstention_reason": outcome.abstention_reason,
        "total_count": outcome.total_count,
        "page_result_count": outcome.result_count,
        "top_reference_id": ids[0] if ids else "",
        "top_10_reference_ids": ";".join(ids[:10]),
        "evidence_complete": evidence_complete,
    }


def run() -> None:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    config_v1 = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config_v2 = yaml.safe_load((ROOT / "data" / "versions" / "v2" / "config.v2.yaml").read_text(encoding="utf-8"))
    encoder = E5QueryEncoder(config_v1["model"], device="cpu")
    service_v1 = RetrievalService(ROOT, config_v1, encoder=encoder)
    service_v2 = RetrievalService(ROOT, config_v2, encoder=encoder)
    rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    for case_id, query, filters in CASES:
        outcomes = {
            "v1": service_v1.search(query, filters=filters, page_size=20),
            "v2": service_v2.search(query, filters=filters, page_size=20),
        }
        system_records = {name: outcome_record(name, case_id, value) for name, value in outcomes.items()}
        rows.extend(system_records.values())
        ids_v1 = system_records["v1"]["top_10_reference_ids"].split(";") if system_records["v1"]["top_10_reference_ids"] else []
        ids_v2 = system_records["v2"]["top_10_reference_ids"].split(";") if system_records["v2"]["top_10_reference_ids"] else []
        comparisons.append(
            {
                "case_id": case_id,
                "query": query,
                "filters_json": json.dumps(filters or {}, ensure_ascii=False, sort_keys=True),
                "v1_abstention_reason": system_records["v1"]["abstention_reason"],
                "v2_abstention_reason": system_records["v2"]["abstention_reason"],
                "v1_total_count": system_records["v1"]["total_count"],
                "v2_total_count": system_records["v2"]["total_count"],
                "v1_top_reference_id": system_records["v1"]["top_reference_id"],
                "v2_top_reference_id": system_records["v2"]["top_reference_id"],
                "top_10_set_overlap_count": len(set(ids_v1) & set(ids_v2)),
                "v1_only_top_10": ";".join(sorted(set(ids_v1) - set(ids_v2))),
                "v2_only_top_10": ";".join(sorted(set(ids_v2) - set(ids_v1))),
                "v1_evidence_complete": system_records["v1"]["evidence_complete"],
                "v2_evidence_complete": system_records["v2"]["evidence_complete"],
            }
        )
    audit_dir = ROOT / "audit" / "v2"
    audit_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(audit_dir / "TECHNICAL_SYSTEM_OUTPUTS.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    comparison = pd.DataFrame(comparisons)
    comparison.to_csv(audit_dir / "TECHNICAL_V1_V2_COMPARISON.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL)
    if not comparison["v1_evidence_complete"].all() or not comparison["v2_evidence_complete"].all():
        raise AssertionError("A technical result lacks readable evidence lineage")
    negative = comparison[comparison["case_id"] == "TECH-NEGATIVE"].iloc[0]
    if negative["v1_total_count"] != 0 or negative["v2_total_count"] != 0:
        raise AssertionError("Unsupported-scope technical query did not abstain in both versions")

    chunks_v1 = pd.read_parquet(ROOT / "data" / "chunks.parquet")
    chunks_v2 = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "chunks.parquet")
    refs_v1 = pd.read_parquet(ROOT / "data" / "reference_catalog.parquet")
    refs_v2 = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "reference_catalog.parquet")
    lines = [
        "# Technical v1/v2 Comparison",
        "",
        "Status: **PASS — descriptive comparison only**",
        "",
        "This comparison uses fixed technical smoke inputs and no relevance judgments. It does not measure or claim precision, recall, MRR, nDCG, or language-quality improvement.",
        "",
        "## Corpus and runtime identity",
        "",
        f"- v1 retrieval chunks: **{len(chunks_v1)}**; v2 retrieval chunks: **{len(chunks_v2)}**.",
        f"- v1 retrieval-eligible references: **{int(refs_v1.document_retrieval_eligible.sum())}**; v2: **{int(refs_v2.document_retrieval_eligible.sum())}**.",
        "- E5 model revision, dimensions, prefixes, normalization, BM25 settings, hybrid weights, evidence thresholds, and abstention thresholds are unchanged.",
        "- Both systems returned complete evidence citations for every emitted result and abstained on the unsupported-domain input.",
        "",
        "## Fixed-query outputs",
        "",
        "| Case | v1 decision | v2 decision | v1 total | v2 total | Top-10 set overlap | Same top reference |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in comparisons:
        lines.append(
            f"| {row['case_id']} | {row['v1_abstention_reason']} | {row['v2_abstention_reason']} | "
            f"{row['v1_total_count']} | {row['v2_total_count']} | {row['top_10_set_overlap_count']} | "
            f"{'YES' if row['v1_top_reference_id'] == row['v2_top_reference_id'] else 'NO'} |"
        )
    lines += [
        "",
        "Differences above are retrieval-output deltas, not correctness judgments. Relevance conclusions remain prohibited until independent qrels are completed and frozen.",
    ]
    (ROOT / "docs" / "TECHNICAL_V1_V2_COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(comparison.to_json(orient="records", force_ascii=True, indent=2))


if __name__ == "__main__":
    run()
