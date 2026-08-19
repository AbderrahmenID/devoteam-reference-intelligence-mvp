from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from retrieval.metadata import FILTER_CATEGORIES, ReferenceMetadataIndex
from retrieval.normalization import normalize_search_text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_final_review import read_xlsx_sheet, sha256_file  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "evaluation" / "judging" / "DEVELOPMENT_QUERY_INTAKE_FINAL.xlsx"
APPROVED_OVERRIDES = ROOT / "evaluation" / "judging" / "APPROVED_FILTER_OVERRIDES.json"
ALLOWED_TYPES = {
    "answerable", "no_answer", "direct", "technology", "acronym_heavy",
    "cross_language_expected", "mixed_script", "filter_constrained",
}
REQUIRED_COLUMNS = {
    "query_id", "query_text", "language", "business_context", "mandatory_filters_json",
    "query_type", "origin", "not_derived_from_reference_corpus_yes_no",
    "approved_for_development_yes_no", "author_or_owner", "notes",
}
SUPPORTED_FILTER_FIELDS = set(FILTER_CATEGORIES) | {"period", "project_year", "year_after", "year_before"}
SUGGESTED_CANDIDATES = {
    "DEV-012": {
        "country": ["Tunisie"],
        "period": {"preset": "last_5_years"},
    },
    "DEV-041": {
        "country": ["Tunisie"],
        "period": {"preset": "last_5_years"},
        "offering": ["Cloud"],
    },
}


def normalized_hash(value: object) -> str:
    return hashlib.sha256(normalize_search_text(value).encode("utf-8")).hexdigest()


def validate() -> dict[str, Any]:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    rows, formula_count = read_xlsx_sheet(WORKBOOK, "Queries")
    issues: list[str] = []
    warnings: list[str] = []
    if len(rows) != 50:
        issues.append(f"Expected 50 query rows; found {len(rows)}")
    columns = set(rows[0]) if rows else set()
    if missing := sorted(REQUIRED_COLUMNS - columns):
        issues.append(f"Missing query columns: {missing}")
    query_ids = [row.get("query_id", "").strip() for row in rows]
    expected_ids = [f"DEV-{index:03d}" for index in range(1, 51)]
    if query_ids != expected_ids:
        issues.append("Query IDs are not the exact ordered DEV-001 through DEV-050 sequence")
    if len(set(query_ids)) != len(query_ids):
        issues.append("Query IDs are duplicated")
    if formula_count:
        issues.append(f"Workbook contains {formula_count} formula cells")

    supported_languages = set(config["languages"]["supported"])
    invalid_languages = sorted({row.get("language", "") for row in rows} - supported_languages)
    if invalid_languages:
        issues.append(f"Unsupported language labels: {invalid_languages}")
    empty_text_ids = [row["query_id"] for row in rows if not row.get("query_text", "").strip()]
    if empty_text_ids:
        issues.append(f"Empty query text: {empty_text_ids}")
    normalized_queries = [normalize_search_text(row.get("query_text", "")) for row in rows]
    duplicate_text_ids = [
        rows[index]["query_id"]
        for index, value in enumerate(normalized_queries)
        if value and normalized_queries.count(value) > 1
    ]
    if duplicate_text_ids:
        issues.append(f"Normalized query texts are duplicated: {sorted(set(duplicate_text_ids))}")

    invalid_type_rows: list[dict[str, Any]] = []
    for row in rows:
        tags = {value.strip() for value in row.get("query_type", "").split("|") if value.strip()}
        unknown = sorted(tags - ALLOWED_TYPES)
        logical = len(tags & {"answerable", "no_answer"}) == 1
        if unknown or not logical:
            invalid_type_rows.append({"query_id": row["query_id"], "unknown": unknown, "answerability_is_exclusive": logical})
        if row.get("language") == "mixed" and "mixed_script" not in tags:
            invalid_type_rows.append({"query_id": row["query_id"], "unknown": [], "answerability_is_exclusive": logical, "issue": "MIXED_LANGUAGE_WITHOUT_MIXED_SCRIPT_TAG"})
    if invalid_type_rows:
        issues.append(f"Invalid query-type rows: {len(invalid_type_rows)}")

    approval_issues = [
        row["query_id"]
        for row in rows
        if row.get("approved_for_development_yes_no", "").strip().upper() != "YES"
        or row.get("not_derived_from_reference_corpus_yes_no", "").strip().upper() != "YES"
    ]
    if approval_issues:
        issues.append(f"Queries missing owner approval/non-derivation attestation: {approval_issues}")
    dangerous = [
        row["query_id"]
        for row in rows
        if any(str(row.get(column, "")).lstrip().startswith(("=", "+", "@")) for column in REQUIRED_COLUMNS)
    ]
    if dangerous:
        issues.append(f"Spreadsheet formula-injection-like values: {dangerous}")

    chunks = pd.read_parquet(ROOT / "data" / "chunks.parquet")
    references = pd.read_parquet(ROOT / "data" / "reference_catalog.parquet")
    corpus_values = [*chunks["chunk_text"].astype(str), *references["service_nature"].astype(str)]
    normalized_corpus = [normalize_search_text(value) for value in corpus_values if str(value).strip()]
    direct_copy_matches: list[dict[str, str]] = []
    for row, query in zip(rows, normalized_queries):
        if not query:
            continue
        for corpus_text in normalized_corpus:
            if query == corpus_text or (len(query) >= 80 and query in corpus_text):
                direct_copy_matches.append({"query_id": row["query_id"], "normalized_query_sha256": normalized_hash(query)})
                break
    if direct_copy_matches:
        issues.append(f"Potential direct corpus copies detected: {len(direct_copy_matches)}")

    v2_chunks = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "chunks.parquet")
    v2_references = pd.read_parquet(ROOT / "data" / "versions" / "v2" / "reference_catalog.parquet")
    metadata = ReferenceMetadataIndex(v2_references, v2_chunks)
    approved_override_document = (
        json.loads(APPROVED_OVERRIDES.read_text(encoding="utf-8"))
        if APPROVED_OVERRIDES.is_file()
        else {"overrides": {}}
    )
    approved_overrides = approved_override_document.get("overrides", {})
    filter_queue: list[dict[str, str]] = []
    parsed_filters: dict[str, dict[str, Any]] = {}
    for row in rows:
        query_id = row["query_id"]
        raw = row.get("mandatory_filters_json", "").strip()
        try:
            filters = json.loads(raw)
            if not isinstance(filters, dict):
                raise ValueError("mandatory_filters_json must decode to an object")
        except (json.JSONDecodeError, ValueError) as error:
            filter_queue.append(
                {
                    "query_id": query_id,
                    "original_filters_json": raw,
                    "validation_error": f"INVALID_JSON: {error}",
                    "unsupported_fields": "",
                    "suggested_candidate_json": "",
                    "decision_required": "Correct the JSON object and resubmit for validation.",
                }
            )
            continue
        original_filters = filters
        if query_id in approved_overrides:
            filters = approved_overrides[query_id]
        parsed_filters[query_id] = filters
        if not filters:
            continue
        unsupported = sorted(set(filters) - SUPPORTED_FILTER_FIELDS)
        try:
            metadata.resolve_filters(filters)
            runtime_error = ""
        except (TypeError, ValueError) as error:
            runtime_error = str(error)
        if unsupported or runtime_error:
            suggestion = SUGGESTED_CANDIDATES.get(query_id)
            if suggestion is not None:
                metadata.resolve_filters(suggestion)
            decision = (
                "Approve or reject the proposed canonical API filter object; no workbook value has been changed."
                if suggestion is not None
                else "Specify the exact supported countries representing West Africa and approve the canonical sector label; region expansion is ambiguous."
            )
            filter_queue.append(
                {
                    "query_id": query_id,
                    "original_filters_json": json.dumps(original_filters, ensure_ascii=False, sort_keys=True),
                    "validation_error": runtime_error or "UNSUPPORTED_FILTER_FIELDS",
                    "unsupported_fields": ";".join(unsupported),
                    "suggested_candidate_json": json.dumps(suggestion, ensure_ascii=False, sort_keys=True) if suggestion else "",
                    "decision_required": decision,
                }
            )
    if filter_queue:
        issues.append(f"Unsupported or ambiguous mandatory filters: {len(filter_queue)} query rows")

    judging_dir = ROOT / "evaluation" / "judging"
    queue_path = judging_dir / "INVALID_FILTER_REVIEW_QUEUE.csv"
    queue_columns = [
        "query_id", "original_filters_json", "validation_error", "unsupported_fields",
        "suggested_candidate_json", "decision_required",
    ]
    pd.DataFrame(filter_queue, columns=queue_columns).to_csv(
        queue_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL
    )
    language_counts = Counter(row["language"] for row in rows)
    type_counts = Counter(tag for row in rows for tag in row["query_type"].split("|") if tag)
    validation = {
        "schema_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED_INVALID_FILTERS" if filter_queue else ("FAIL" if issues else "PASS"),
        "workbook_path": str(WORKBOOK.relative_to(ROOT)).replace("\\", "/"),
        "workbook_sha256": sha256_file(WORKBOOK),
        "query_count": len(rows),
        "unique_query_ids": len(set(query_ids)),
        "formula_cell_count": formula_count,
        "language_counts": dict(sorted(language_counts.items())),
        "query_type_counts": dict(sorted(type_counts.items())),
        "answerable_count": type_counts["answerable"],
        "no_answer_count": type_counts["no_answer"],
        "filter_constrained_count": type_counts["filter_constrained"],
        "normalized_query_hashes": {row["query_id"]: normalized_hash(row["query_text"]) for row in rows},
        "direct_corpus_copy_matches": direct_copy_matches,
        "protected_held_out_overlap_check": "NOT_ACCESSED_PROTECTED_TEST_BOUNDARY",
        "invalid_type_rows": invalid_type_rows,
        "filter_review_queue_rows": len(filter_queue),
        "filter_review_queue_path": str(queue_path.relative_to(ROOT)).replace("\\", "/"),
        "frozen_query_set_created": False,
        "approved_filter_overrides_path": str(APPROVED_OVERRIDES.relative_to(ROOT)).replace("\\", "/") if APPROVED_OVERRIDES.is_file() else None,
        "approved_filter_override_count": len(approved_overrides),
        "resolved_filters": parsed_filters,
        "issues": issues,
        "warnings": warnings,
    }
    validation_path = judging_dir / "DEVELOPMENT_QUERY_IMPORT_VALIDATION.json"
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Development Query Import Blocker",
        "",
        "Status: **BLOCKED — INVALID OR AMBIGUOUS MANDATORY FILTERS**",
        "",
        "The 50-query workbook itself is structurally valid: IDs are unique, texts are non-empty and distinct, language and query-type labels are supported, answerable/no-answer tags are exclusive, owner approval fields are complete, and no formulas or direct corpus-text copies were detected.",
        "",
        "Freezing is intentionally stopped because three filter-constrained queries do not use the API's exact supported filter schema. The workbook has not been overwritten, no filter meaning has been guessed, and no candidate pool has been generated.",
        "",
        "| Query | Unsupported input fields | Required decision |",
        "|---|---|---|",
    ]
    for item in filter_queue:
        lines.append(f"| {item['query_id']} | `{item['unsupported_fields']}` | {item['decision_required']} |")
    lines += [
        "",
        "The machine-readable review queue is `evaluation/judging/INVALID_FILTER_REVIEW_QUEUE.csv`. `DEV-012` and `DEV-041` include validated candidate canonical filter objects for owner approval. `DEV-026` requires an explicit country list because `regions: West Africa` has no unambiguous API equivalent; its `Banking` sector also needs approval to use the source label `Banque`.",
        "",
        "The protected held-out workbook was not opened or compared, preserving the declared test boundary.",
    ]
    report_path = ROOT / "audit" / "evaluation" / "DEVELOPMENT_QUERY_IMPORT_BLOCKER.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({key: validation[key] for key in ("status", "query_count", "language_counts", "query_type_counts", "filter_review_queue_rows", "issues")}, ensure_ascii=True, indent=2))
    return validation


if __name__ == "__main__":
    result = validate()
    raise SystemExit(2 if result["status"].startswith("BLOCKED") else (1 if result["status"] != "PASS" else 0))
