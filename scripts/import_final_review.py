from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SNAPSHOT_ID = "20260714T154731Z_129ff982c8"
REVIEW_RELATIVE_PATH = Path("audit/corpus_quality/HUMAN_CHUNK_REVIEW_FINAL.xlsx")
SOURCE_ROOT = Path(r"C:\Users\abder\Downloads\Devoteam_AI_Workspace\Devoteam_AI_CLEAN_PIPELINE")

FINAL_ACTIONS = {
    "KEEP_RETRIEVAL_AND_DISPLAY",
    "KEEP_RETRIEVAL_ONLY",
    "EXCLUDE_GENERIC_OR_NON_EVIDENTIARY_TEXT",
    "REPAIR_OR_REEXTRACT",
    "REVIEW_REFERENCE_LINKAGE",
    "HUMAN_CONFIRMATION_REQUIRED",
}
HUMAN_CLASSIFICATIONS = {
    "CLEAN",
    "READABLE_WITH_LAYOUT_NOISE",
    "CORRUPTED",
    "INCOHERENT_MIXED_CONTENT",
    "WRONG_PAGE_ASSOCIATION",
    "NEEDS_HUMAN_REVIEW",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference)
    if not letters:
        raise ValueError(f"Invalid XLSX cell reference: {cell_reference}")
    result = 0
    for character in letters.group(0):
        result = result * 26 + ord(character) - 64
    return result - 1


def read_xlsx_sheet(path: Path, sheet_name: str) -> tuple[list[dict[str, str]], int]:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
                for item in root.findall(f"{{{MAIN_NS}}}si")
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        target: str | None = None
        for sheet in workbook.find(f"{{{MAIN_NS}}}sheets") or []:
            if sheet.attrib["name"] == sheet_name:
                target = relationship_map[sheet.attrib[f"{{{REL_NS}}}id"]].lstrip("/")
                break
        if target is None:
            raise ValueError(f"Sheet not found: {sheet_name}")
        if not target.startswith("xl/"):
            target = "xl/" + target
        root = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        formula_count = 0
        for row in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
            values: dict[int, str] = {}
            for cell in row.findall(f"{{{MAIN_NS}}}c"):
                index = _column_index(cell.attrib["r"])
                cell_type = cell.attrib.get("t")
                raw_value = cell.find(f"{{{MAIN_NS}}}v")
                inline = cell.find(f"{{{MAIN_NS}}}is")
                formula = cell.find(f"{{{MAIN_NS}}}f")
                formula_count += int(formula is not None)
                value = ""
                if cell_type == "s" and raw_value is not None:
                    value = shared_strings[int(raw_value.text or "0")]
                elif inline is not None:
                    value = "".join(node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t"))
                elif raw_value is not None:
                    value = raw_value.text or ""
                values[index] = value
            if values:
                rows.append([values.get(index, "") for index in range(max(values) + 1)])
        if not rows:
            return [], formula_count
        header = rows[0]
        records = []
        for row in rows[1:]:
            padded = row + [""] * max(0, len(header) - len(row))
            if any(str(value).strip() for value in padded):
                records.append({header[index]: str(padded[index]) for index in range(len(header))})
        return records, formula_count


def _split_ids(value: object) -> list[str]:
    return sorted({item.strip() for item in str(value or "").split(";") if item.strip()})


def _normalize_bool(value: object) -> str:
    text = str(value or "").strip().upper()
    if text in {"TRUE", "1", "YES"}:
        return "YES"
    if text in {"FALSE", "0", "NO"}:
        return "NO"
    return text


def _numeric_equal(left: object, right: object) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-6)
    except (TypeError, ValueError):
        return str(left or "").strip() == str(right or "").strip()


def _dangerous_formula_value(value: object) -> bool:
    text = str(value or "").lstrip()
    return bool(text) and text[0] in {"=", "+", "@"}


def import_review(root: Path) -> dict[str, Any]:
    root = root.resolve()
    review_path = root / REVIEW_RELATIVE_PATH
    rows, formula_count = read_xlsx_sheet(review_path, "Review")
    review = pd.DataFrame(rows)
    required_columns = {
        "review_item_id", "chunk_id", "reference_id", "source_document", "source_page",
        "linked_reference_ids", "human_classification", "human_wrong_page_judgment",
        "human_coherence_judgment", "human_reviewer_id", "human_reviewed_at",
        "human_comments", "approved_for_retrieval", "approved_for_display",
        "review_confidence", "review_basis", "final_action",
    }
    missing_columns = sorted(required_columns - set(review.columns))
    if missing_columns:
        raise AssertionError(f"Required review columns are missing: {missing_columns}")

    chunks = pd.read_parquet(root / "data/chunks.parquet").reset_index(drop=True)
    references = pd.read_parquet(root / "data/reference_catalog.parquet").reset_index(drop=True)
    original_audit = pd.read_csv(root / "audit/corpus_quality/CHUNK_QUALITY_AUDIT.csv", keep_default_na=False)
    canonical_pages_path = (
        SOURCE_ROOT / "data/canonical" / SNAPSHOT_ID / "phase4_corpus_v1/canonical_pages.parquet"
    )
    canonical_pages = pd.read_parquet(canonical_pages_path)

    issues: list[str] = []
    warnings: list[str] = []
    if len(review) != 180:
        issues.append(f"Expected 180 review rows, found {len(review)}")
    duplicate_chunks = sorted(review.loc[review["chunk_id"].duplicated(keep=False), "chunk_id"].unique())
    if duplicate_chunks:
        issues.append(f"Duplicate chunk IDs: {duplicate_chunks}")
    duplicate_items = sorted(review.loc[review["review_item_id"].duplicated(keep=False), "review_item_id"].unique())
    if duplicate_items:
        issues.append(f"Duplicate review item IDs: {duplicate_items}")

    corpus_chunk_ids = set(chunks["chunk_id"].astype(str))
    unknown_chunk_ids = sorted(set(review["chunk_id"]) - corpus_chunk_ids)
    if unknown_chunk_ids:
        issues.append(f"Review chunk IDs absent from v1: {unknown_chunk_ids}")
    catalog_reference_ids = set(references["reference_id"].astype(str))
    unknown_reference_ids = sorted(
        {
            reference_id
            for value in review["reference_id"]
            for reference_id in _split_ids(value)
            if reference_id not in catalog_reference_ids
        }
    )
    if unknown_reference_ids:
        issues.append(f"Reference IDs absent from the catalogue: {unknown_reference_ids}")
    mismatched_reference_columns = [
        row["chunk_id"]
        for row in rows
        if _split_ids(row["reference_id"]) != _split_ids(row["linked_reference_ids"])
    ]
    if mismatched_reference_columns:
        issues.append(
            f"reference_id and linked_reference_ids disagree for {len(mismatched_reference_columns)} chunks"
        )

    invalid_actions = sorted(set(review["final_action"]) - FINAL_ACTIONS)
    if invalid_actions:
        issues.append(f"Unknown final actions: {invalid_actions}")
    invalid_classifications = sorted(set(review["human_classification"]) - HUMAN_CLASSIFICATIONS)
    if invalid_classifications:
        issues.append(f"Unknown human classifications: {invalid_classifications}")
    for column, allowed in {
        "approved_for_retrieval": {"YES", "NO"},
        "approved_for_display": {"YES", "NO"},
        "review_confidence": {"HIGH", "MEDIUM", "LOW"},
        "human_wrong_page_judgment": {"YES", "NO", "UNCERTAIN", "NOT_APPLICABLE"},
        "human_coherence_judgment": {
            "COHERENT", "INCOHERENT", "UNCERTAIN", "NOT_APPLICABLE",
            "PARTIALLY_COHERENT", "INSUFFICIENT_CONTEXT", "COHERENT_BUT_MISASSOCIATED",
        },
    }.items():
        invalid = sorted({_normalize_bool(value) for value in review[column]} - allowed)
        if invalid:
            issues.append(f"Invalid {column} values: {invalid}")

    expected_policy = {
        "KEEP_RETRIEVAL_AND_DISPLAY": ("YES", "YES"),
        "KEEP_RETRIEVAL_ONLY": ("YES", "NO"),
        "EXCLUDE_GENERIC_OR_NON_EVIDENTIARY_TEXT": ("NO", "NO"),
        "REPAIR_OR_REEXTRACT": ("NO", "NO"),
        "REVIEW_REFERENCE_LINKAGE": ("NO", "NO"),
    }
    policy_violations: list[dict[str, str]] = []
    for row in rows:
        action = row["final_action"]
        retrieval = _normalize_bool(row["approved_for_retrieval"])
        display = _normalize_bool(row["approved_for_display"])
        expected = expected_policy.get(action)
        if expected and (retrieval, display) != expected:
            policy_violations.append(
                {"chunk_id": row["chunk_id"], "action": action, "retrieval": retrieval, "display": display}
            )
        if action == "HUMAN_CONFIRMATION_REQUIRED" and display != "NO":
            policy_violations.append(
                {"chunk_id": row["chunk_id"], "action": action, "retrieval": retrieval, "display": display}
            )
    if policy_violations:
        issues.append(f"Retrieval/display policy violations: {len(policy_violations)}")

    editable_fields = [
        "human_classification", "human_wrong_page_judgment", "human_coherence_judgment",
        "human_reviewer_id", "human_comments", "approved_for_retrieval", "approved_for_display",
        "review_confidence", "review_basis", "final_action",
    ]
    injection_cells = [
        {"review_item_id": row["review_item_id"], "column": column}
        for row in rows
        for column in editable_fields
        if _dangerous_formula_value(row.get(column))
    ]
    if formula_count or injection_cells:
        issues.append(
            f"Spreadsheet formula/injection content found: formulas={formula_count}, suspicious_values={len(injection_cells)}"
        )

    audit_by_chunk = original_audit.set_index("chunk_id", drop=False)
    source_value_mismatches: list[dict[str, str]] = []
    for row in rows:
        if row["chunk_id"] not in audit_by_chunk.index:
            continue
        original = audit_by_chunk.loc[row["chunk_id"]]
        checks = {
            "source_document": str(original["source_document"]),
            "source_page": str(original["source_page"]),
            "reference_id": str(original["reference_id"]),
            "linked_reference_ids": str(original["linked_reference_ids"]),
            "automatic_classification": str(original["automatic_classification"]),
            "automatic_reason": str(original["automatic_reason"]),
            "citation_label": str(original["citation_label"]),
            "citation_uri": str(original["citation_uri"]),
            "display_excerpt": str(original["display_excerpt"]),
            "raw_text_excerpt": str(original["raw_text_excerpt"]),
        }
        for field, expected in checks.items():
            imported = str(row.get(field, ""))
            safely_escaped = imported == "'" + expected and expected.startswith(("-", "+", "@", "="))
            if imported != expected and not safely_escaped:
                source_value_mismatches.append({"chunk_id": row["chunk_id"], "field": field})
        for field in ("character_count", "word_count", "evidence_quality_score"):
            if not _numeric_equal(row.get(field, ""), original[field]):
                source_value_mismatches.append({"chunk_id": row["chunk_id"], "field": field})
    if source_value_mismatches:
        issues.append(f"Imported workbook changed {len(source_value_mismatches)} source/audit values")

    action_counts = Counter(review["final_action"])
    classification_counts = Counter(review["human_classification"])
    language_counts = Counter(review["language"])
    retrieval_yes = sum(_normalize_bool(value) == "YES" for value in review["approved_for_retrieval"])
    display_yes = sum(_normalize_bool(value) == "YES" for value in review["approved_for_display"])
    if retrieval_yes != 106 or display_yes != 65:
        warnings.append(
            f"Workbook summary screenshot expected retrieval/display approvals 106/65; found {retrieval_yes}/{display_yes}"
        )

    audit_dir = root / "audit/corpus_quality"
    linkage = review[review["final_action"] == "REVIEW_REFERENCE_LINKAGE"].copy()
    confirmation = review[review["final_action"] == "HUMAN_CONFIRMATION_REQUIRED"].copy()
    queue_columns = [
        "review_item_id", "chunk_id", "reference_id", "source_document", "source_page",
        "human_classification", "human_wrong_page_judgment", "human_coherence_judgment",
        "approved_for_retrieval", "approved_for_display", "review_confidence",
        "human_comments", "final_action",
    ]
    linkage[queue_columns].to_csv(
        audit_dir / "LINKAGE_REVIEW_QUEUE.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL
    )
    confirmation[queue_columns].to_csv(
        audit_dir / "REMAINING_HUMAN_CONFIRMATION.csv", index=False, encoding="utf-8", quoting=csv.QUOTE_ALL
    )

    review_by_chunk = review.set_index("chunk_id", drop=False)
    chunk_by_id = chunks.set_index(chunks["chunk_id"].astype(str), drop=False)
    page_rows: list[dict[str, Any]] = []
    repairs = review[review["final_action"] == "REPAIR_OR_REEXTRACT"]
    for (source_document, source_page), group in repairs.groupby(
        ["source_document", "source_page"], sort=True
    ):
        affected_ids = sorted(group["chunk_id"].astype(str))
        first_chunk = chunk_by_id.loc[affected_ids[0]]
        document_id = str(first_chunk["document_id"])
        page_number = int(float(source_page))
        page_chunks = chunks[
            (chunks["document_id"].astype(str) == document_id)
            & (chunks["page_number_1_based"].astype(int) == page_number)
        ]
        canonical = canonical_pages[
            (canonical_pages["document_id"].astype(str) == document_id)
            & (canonical_pages["page_number_1_based"].astype(int) == page_number)
        ]
        if len(canonical) != 1:
            issues.append(
                f"Canonical page lineage expected one row for {document_id} page {page_number}; found {len(canonical)}"
            )
            extraction_method = ""
            ocr_confidence: Any = ""
        else:
            canonical_row = canonical.iloc[0]
            extraction_method = str(canonical_row["extraction_method"] or "")
            ocr_raw = canonical_row["ocr_confidence"]
            ocr_confidence = "" if pd.isna(ocr_raw) else float(ocr_raw)
        source_relative_path = str(first_chunk["source_relative_path"])
        snapshot_root = SOURCE_ROOT / "data/snapshots" / SNAPSHOT_ID
        source_path = snapshot_root / source_relative_path
        source_path_resolution = "EXACT_RELATIVE_PATH"
        if not source_path.is_file():
            candidates = sorted((snapshot_root / "raw/evidence").glob(f"{document_id}__*"))
            if len(candidates) == 1:
                source_path = candidates[0]
                source_path_resolution = "STABLE_DOCUMENT_ID_FILENAME_MATCH"
        source_exists = source_path.is_file()
        expected_source_hash = str(first_chunk["source_sha256"])
        actual_source_hash = sha256_file(source_path) if source_exists else ""
        source_hash_matches = source_exists and actual_source_hash == expected_source_hash
        if not source_exists:
            issues.append(f"Repair source is missing: {source_path}")
        elif not source_hash_matches:
            issues.append(f"Repair source hash mismatch: {source_path}")
        proposed = (
            "DIGITAL_TEXT_REEXTRACT_THEN_OCR_FRA_ENG_ARA_IF_UNRELIABLE"
            if "digital" in extraction_method.casefold()
            else "MULTILINGUAL_OCR_FRA_ENG_ARA_CONTROLLED_STRATEGIES"
        )
        reference_ids = sorted(
            {
                reference_id
                for value in group["reference_id"]
                for reference_id in _split_ids(value)
            }
        )
        page_rows.append(
            {
                "repair_id": f"V2-REPAIR-{len(page_rows) + 1:03d}",
                "source_document_id": document_id,
                "source_document_hash": expected_source_hash,
                "source_file_name": str(source_document),
                "source_file_path": str(source_path),
                "source_file_path_resolution": source_path_resolution,
                "source_page": page_number,
                "affected_v1_chunk_ids": ";".join(affected_ids),
                "page_v1_chunk_ids": ";".join(sorted(page_chunks["chunk_id"].astype(str))),
                "reference_ids": ";".join(reference_ids),
                "automatic_defect_classification": ";".join(sorted(set(group["automatic_classification"]))),
                "reviewed_classification": ";".join(sorted(set(group["human_classification"]))),
                "final_action": "REPAIR_OR_REEXTRACT",
                "repair_reason": " | ".join(dict.fromkeys(group["human_comments"].astype(str))),
                "automatic_reasons": ";".join(sorted(set(group["automatic_reason"]))),
                "extraction_method_used_v1": extraction_method,
                "ocr_confidence": ocr_confidence,
                "proposed_v2_extraction_method": proposed,
                "required_human_follow_up": "YES_VERIFY_REPAIRED_TEXT_AND_LINEAGE",
                "repair_status": "PENDING_DEPENDENCY_CHECK",
                "source_file_exists": source_exists,
                "source_hash_matches": source_hash_matches,
            }
        )

    v2_dir = root / "data/versions/v2"
    v2_dir.mkdir(parents=True, exist_ok=True)
    repair_frame = pd.DataFrame(page_rows)
    repair_csv = v2_dir / "TARGETED_REPAIR_MANIFEST.csv"
    repair_frame.to_csv(repair_csv, index=False, encoding="utf-8", quoting=csv.QUOTE_ALL)
    repair_json = v2_dir / "TARGETED_REPAIR_MANIFEST.json"
    repair_json.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pipeline_version": "targeted_repair_v2_manifest_only",
                "snapshot_id": SNAPSHOT_ID,
                "review_workbook_path": REVIEW_RELATIVE_PATH.as_posix(),
                "review_workbook_sha256": sha256_file(review_path),
                "status": "VALIDATED_MANIFEST_PENDING_DEPENDENCIES" if not issues else "INVALID",
                "repair_chunk_count": len(repairs),
                "unique_repair_page_count": len(repair_frame),
                "records": page_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    validation = {
        "schema_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if not issues else "FAIL",
        "workbook_path": REVIEW_RELATIVE_PATH.as_posix(),
        "workbook_sha256": sha256_file(review_path),
        "review_rows": len(review),
        "unique_chunk_ids": int(review["chunk_id"].nunique()),
        "formula_cell_count": formula_count,
        "formula_injection_value_count": len(injection_cells),
        "unknown_chunk_ids": unknown_chunk_ids,
        "unknown_reference_ids": unknown_reference_ids,
        "source_value_mismatches": source_value_mismatches,
        "policy_violations": policy_violations,
        "action_counts": dict(sorted(action_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "language_counts": dict(sorted(language_counts.items())),
        "approved_for_retrieval": retrieval_yes,
        "approved_for_display": display_yes,
        "linkage_review_rows": len(linkage),
        "human_confirmation_rows": len(confirmation),
        "repair_chunk_rows": len(repairs),
        "unique_repair_pages": len(repair_frame),
        "reviewer_values": sorted(set(review["human_reviewer_id"])),
        "issues": issues,
        "warnings": warnings,
        "v1_chunks_sha256": sha256_file(root / "data/chunks.parquet"),
        "v1_reference_catalog_sha256": sha256_file(root / "data/reference_catalog.parquet"),
    }
    validation_path = audit_dir / "REVIEW_IMPORT_VALIDATION.json"
    validation_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Review Decision Summary",
        "",
        "Date: 2026-08-02  ",
        f"Import status: **{validation['status']}**  ",
        f"Workbook SHA-256: `{validation['workbook_sha256']}`",
        "",
        "## Reconciliation",
        "",
        f"- Rows imported: **{len(review)}**; unique v1 chunk IDs: **{review['chunk_id'].nunique()}**.",
        f"- Unknown chunk IDs: **{len(unknown_chunk_ids)}**; unknown reference IDs: **{len(unknown_reference_ids)}**.",
        f"- Formula cells: **{formula_count}**; suspicious editable values: **{len(injection_cells)}**.",
        f"- Source/audit value mismatches: **{len(source_value_mismatches)}**.",
        f"- Retrieval/display policy violations: **{len(policy_violations)}**.",
        "",
        "## Final actions",
        "",
        "| Action | Rows |",
        "|---|---:|",
    ]
    for action in sorted(FINAL_ACTIONS):
        lines.append(f"| {action} | {action_counts[action]} |")
    lines += [
        "",
        f"Approved for retrieval: **{retrieval_yes}**. Approved for primary display: **{display_yes}**.",
        "",
        "## Reviewed classifications",
        "",
        "| Classification | Rows |",
        "|---|---:|",
    ]
    for classification in sorted(HUMAN_CLASSIFICATIONS):
        lines.append(f"| {classification} | {classification_counts[classification]} |")
    lines += [
        "",
        "## Governance interpretation",
        "",
        "The workbook records a single `GPT-5.6 AI-assisted review` identity. The user's submission authorizes importing these owner-reviewed operational decisions, but it does not create independent relevance qrels or replace the 37 explicitly provisional `HUMAN_CONFIRMATION_REQUIRED` rows. Those rows remain excluded from primary display and are preserved in a separate confirmation queue.",
        "",
        f"The repair scope contains **{len(repairs)} reviewed chunks across {len(repair_frame)} unique source pages**. One linkage item is quarantined and is not automatically relinked.",
    ]
    if issues:
        lines += ["", "## Blocking issues", ""] + [f"- {issue}" for issue in issues]
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {warning}" for warning in warnings]
    (audit_dir / "REVIEW_DECISION_SUMMARY.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    if issues:
        raise AssertionError("Review import validation failed; see REVIEW_IMPORT_VALIDATION.json")
    return validation | {
        "repair_manifest_csv_sha256": sha256_file(repair_csv),
        "repair_manifest_json_sha256": sha256_file(repair_json),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(import_review(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
