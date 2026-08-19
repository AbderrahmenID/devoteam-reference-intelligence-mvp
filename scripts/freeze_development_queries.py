from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_final_review import read_xlsx_sheet, sha256_file  # noqa: E402
from validate_development_queries import APPROVED_OVERRIDES, ROOT, WORKBOOK, normalized_hash, validate  # noqa: E402


FROZEN_DIR = ROOT / "evaluation" / "judging" / "frozen"
FROZEN_CSV = FROZEN_DIR / "development_queries_v1.csv"
FROZEN_MANIFEST = FROZEN_DIR / "DEVELOPMENT_QUERY_MANIFEST.json"


def run() -> dict:
    validation = validate()
    if validation["status"] != "PASS":
        raise RuntimeError("Development query validation has not passed")
    rows, _ = read_xlsx_sheet(WORKBOOK, "Queries")
    override_document = json.loads(APPROVED_OVERRIDES.read_text(encoding="utf-8"))
    overrides = override_document["overrides"]
    frozen_rows: list[dict[str, str]] = []
    for row in rows:
        query_id = row["query_id"].strip()
        filters = overrides.get(query_id, json.loads(row["mandatory_filters_json"]))
        tags = [tag.strip() for tag in row["query_type"].split("|") if tag.strip()]
        frozen_rows.append(
            {
                "query_id": query_id,
                "query_text": row["query_text"].strip(),
                "normalized_query_sha256": normalized_hash(row["query_text"]),
                "language": row["language"].strip(),
                "business_context": row["business_context"].strip(),
                "mandatory_filters_json": json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "query_type": "|".join(tags),
                "answerability": "answerable" if "answerable" in tags else "no_answer",
                "origin": row["origin"].strip(),
                "not_derived_from_reference_corpus_yes_no": row["not_derived_from_reference_corpus_yes_no"].strip().upper(),
                "approved_for_development_yes_no": row["approved_for_development_yes_no"].strip().upper(),
                "author_or_owner": row["author_or_owner"].strip(),
                "notes": row["notes"].strip(),
                "filter_source": "OWNER_APPROVED_OVERRIDE" if query_id in overrides else "ORIGINAL_WORKBOOK",
            }
        )
    frame = pd.DataFrame(frozen_rows)
    if len(frame) != 50 or not frame["query_id"].is_unique or not frame["normalized_query_sha256"].is_unique:
        raise AssertionError("Frozen query identities are invalid")
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(FROZEN_CSV, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_ALL, lineterminator="\n")
    type_counts = Counter(tag for value in frame["query_type"] for tag in value.split("|"))
    manifest = {
        "schema_version": 1,
        "query_set_version": "development_queries_v1",
        "status": "FROZEN_PROVISIONAL_DEVELOPMENT_QUERY_SET",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_workbook_path": str(WORKBOOK.relative_to(ROOT)).replace("\\", "/"),
        "source_workbook_sha256": sha256_file(WORKBOOK),
        "approved_filter_overrides_path": str(APPROVED_OVERRIDES.relative_to(ROOT)).replace("\\", "/"),
        "approved_filter_overrides_sha256": sha256_file(APPROVED_OVERRIDES),
        "validation_path": "evaluation/judging/DEVELOPMENT_QUERY_IMPORT_VALIDATION.json",
        "validation_sha256": sha256_file(ROOT / "evaluation" / "judging" / "DEVELOPMENT_QUERY_IMPORT_VALIDATION.json"),
        "frozen_csv_path": str(FROZEN_CSV.relative_to(ROOT)).replace("\\", "/"),
        "frozen_csv_sha256": sha256_file(FROZEN_CSV),
        "query_count": len(frame),
        "language_counts": dict(sorted(Counter(frame["language"]).items())),
        "answerable_count": int((frame["answerability"] == "answerable").sum()),
        "no_answer_count": int((frame["answerability"] == "no_answer").sum()),
        "filter_constrained_count": type_counts["filter_constrained"],
        "cross_language_expected_count": type_counts["cross_language_expected"],
        "mixed_script_count": type_counts["mixed_script"],
        "acronym_heavy_count": type_counts["acronym_heavy"],
        "owner_approved_filter_override_count": len(overrides),
        "direct_corpus_copy_match_count": len(validation["direct_corpus_copy_matches"]),
        "protected_held_out_overlap_check": validation["protected_held_out_overlap_check"],
        "allowed_use": [
            "development diagnostics",
            "candidate-pool generation",
            "precision and abstention tuning only after independent qrels are frozen",
        ],
        "prohibited_claims": [
            "official gold set",
            "held-out test set",
            "official precision, recall, MRR, or nDCG before independent judgments",
        ],
    }
    FROZEN_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
    return manifest


if __name__ == "__main__":
    run()
