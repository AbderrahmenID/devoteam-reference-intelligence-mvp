from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from retrieval.evidence import EvidenceQualityEvaluator, derive_display_text
from retrieval.normalization import tokenize_multilingual
from retrieval.terms import CAPABILITY_CONCEPTS, QueryTermAnalysis


REPORTED_BAD_CHUNK_IDS = {
    "a55d8dbb2b1ba55e3e976fa9ca81f6d022838f8e1a32876d2b4cd7a271e6d8e6",
    "304e29d0615d33cf429436d4c8e97099332c7f05091d5ca343864eae793963f7",
    "38500b06bd19daf7d0930ca994f293c19b3ff879ade0bb62bbb3a2552130d0fc",
    "e9945759d8098d7241cc13630c5b6db31d8b4253afd925f24ccea36a9e3a874e",
    "5361816dacb87bb88f4ef261c80df1898260d75c79bbbf0ab13d5b2bb31eadb2",
}

SEVERE_REASONS = {
    "LOW_PRINTABLE_RATIO",
    "OCR_GIBBERISH",
    "EXCESSIVE_SINGLE_CHARACTER_TOKENS",
    "EXCESSIVE_FRAGMENTATION",
    "REPETITIVE_TEXT",
}


def _json_ints(value: object) -> list[int]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    output: list[int] = []
    for item in parsed:
        try:
            output.append(int(item))
        except (TypeError, ValueError):
            continue
    return output


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(tuple(tokens[index : index + width]) == phrase for index in range(len(tokens) - width + 1))


def _concepts(text: object) -> set[str]:
    tokens = tokenize_multilingual(text)
    return {
        concept
        for concept, aliases in CAPABILITY_CONCEPTS.items()
        if any(_contains_phrase(tokens, alias) for alias in aliases)
    }


def _empty_query_analysis() -> QueryTermAnalysis:
    return QueryTermAnalysis(
        normalized_query="",
        raw_tokens=[],
        bm25_tokens=[],
        meaningful_terms=[],
        removed_stopwords=[],
        rejected_common_terms=[],
        rejected_out_of_vocabulary=[],
        concepts=[],
    )


def _classification(
    *,
    quality_pass: bool,
    quality_score: float,
    reasons: set[str],
    diagnostics: dict[str, Any],
    strong_wrong_page_association: bool,
) -> str:
    if strong_wrong_page_association:
        return "WRONG_PAGE_ASSOCIATION"
    if "INCOHERENT_MIXED_SCRIPT" in reasons:
        return "INCOHERENT_MIXED_CONTENT"
    if reasons & SEVERE_REASONS:
        return "CORRUPTED"
    if not quality_pass or quality_score < 0.57:
        return "NEEDS_HUMAN_REVIEW"
    noisy = (
        float(diagnostics["line_fragmentation"]) >= 0.25
        or float(diagnostics["leading_fragmentation"]) >= 0.25
        or float(diagnostics["repeated_line_ratio"]) >= 0.10
        or float(diagnostics["one_character_token_ratio"]) >= 0.12
        or float(diagnostics["suspicious_symbol_ratio"]) >= 0.03
    )
    return "READABLE_WITH_LAYOUT_NOISE" if noisy else "CLEAN"


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    chunks = pd.read_parquet(root / config["data"]["chunks"]).reset_index(drop=True)
    references = pd.read_parquet(root / config["data"]["reference_catalog"]).reset_index(drop=True)
    if len(chunks) != 1185:
        raise AssertionError(f"Expected 1,185 chunks, found {len(chunks):,}")
    if not chunks["chunk_id"].is_unique:
        raise AssertionError("Chunk IDs are not unique")

    refs_by_row = {
        int(row["row_number"]): row
        for row in references.to_dict(orient="records")
    }
    evaluator = EvidenceQualityEvaluator(config["evidence_quality"])
    empty_query = _empty_query_analysis()
    audit_rows: list[dict[str, Any]] = []
    bad_search_chunk_ids: set[str] = set()
    reproduction_path = root / "audit" / "hotfix-reproduction.json"
    if reproduction_path.is_file():
        reproduction = json.loads(reproduction_path.read_text(encoding="utf-8"))
        bad_search_chunk_ids.update(
            str(candidate["candidate_chunk_id"])
            for candidate in reproduction.get("candidates", [])
            if candidate.get("candidate_chunk_id")
        )
        for reference in reproduction.get("reference_selection", []):
            bad_search_chunk_ids.update(
                str(chunk_id) for chunk_id in reference.get("candidate_chunk_ids", [])
            )

    for chunk in chunks.to_dict(orient="records"):
        raw = str(chunk.get("chunk_text") or "")
        display = derive_display_text(raw)
        quality = evaluator.evaluate(
            raw,
            display,
            empty_query,
            dense_score=0.0,
            query_language=str(chunk.get("page_language") or "und"),
            extraction_quality=str(chunk.get("data_quality_status") or "") or None,
        )
        diagnostics = quality.diagnostics
        linked_rows = _json_ints(chunk.get("reference_rows_json"))
        linked_refs = [refs_by_row[row] for row in linked_rows if row in refs_by_row]
        linked_reference_ids = sorted(str(ref["reference_id"]) for ref in linked_refs)
        linked_document_ids = {
            str(ref.get("canonical_document_id") or "") for ref in linked_refs
        } - {""}
        source_document_id = str(chunk.get("document_id") or "")
        document_link_mismatch = bool(linked_document_ids and source_document_id not in linked_document_ids)

        chunk_concepts = _concepts(display)
        metadata_text = " ".join(
            str(ref.get(field) or "")
            for ref in linked_refs
            for field in ("service_nature", "offering")
        )
        metadata_concepts = _concepts(metadata_text)
        concept_conflict = bool(chunk_concepts and metadata_concepts and chunk_concepts.isdisjoint(metadata_concepts))
        strong_wrong_page = document_link_mismatch
        wrong_page_candidate = document_link_mismatch or concept_conflict or not linked_reference_ids
        reasons = set(quality.rejection_reasons)
        classification = _classification(
            quality_pass=quality.quality_pass,
            quality_score=quality.quality_score,
            reasons=reasons,
            diagnostics=diagnostics,
            strong_wrong_page_association=strong_wrong_page,
        )
        if wrong_page_candidate and classification in {"CLEAN", "READABLE_WITH_LAYOUT_NOISE"}:
            classification = "NEEDS_HUMAN_REVIEW"

        audit_rows.append(
            {
                "chunk_id": str(chunk["chunk_id"]),
                "reference_id": ";".join(linked_reference_ids),
                "source_document": str(chunk.get("source_file_name") or ""),
                "source_page": int(chunk.get("page_number_1_based") or 0),
                "linked_reference_ids": ";".join(linked_reference_ids),
                "character_count": len(raw),
                "word_count": int(chunk.get("chunk_word_count") or len(raw.split())),
                "ocr_confidence": "",
                "language": str(diagnostics["language"]),
                "scripts": ";".join(str(value) for value in diagnostics["scripts"]),
                "printable_character_ratio": diagnostics["printable_character_ratio"],
                "alphabetic_character_ratio": diagnostics["alphabetic_character_ratio"],
                "meaningful_token_count": diagnostics["meaningful_token_count"],
                "average_token_length": diagnostics["average_token_length"],
                "one_character_token_ratio": diagnostics["one_character_token_ratio"],
                "line_count": diagnostics["line_count"],
                "line_fragmentation": diagnostics["line_fragmentation"],
                "leading_fragmentation": diagnostics["leading_fragmentation"],
                "repeated_line_ratio": diagnostics["repeated_line_ratio"],
                "suspicious_symbol_ratio": diagnostics["suspicious_symbol_ratio"],
                "sentence_completeness": diagnostics["sentence_completeness"],
                "mixed_script": diagnostics["mixed_script"],
                "mixed_script_coherence": (
                    "INCOHERENT" if "INCOHERENT_MIXED_SCRIPT" in reasons
                    else ("COHERENT" if diagnostics["mixed_script"] else "NOT_APPLICABLE")
                ),
                "evidence_quality_pass": quality.quality_pass,
                "evidence_quality_score": quality.quality_score,
                "rejection_reasons": ";".join(quality.rejection_reasons),
                "wrong_page_candidate": wrong_page_candidate,
                "wrong_page_candidate_reasons": ";".join(
                    reason
                    for flag, reason in (
                        (document_link_mismatch, "DOCUMENT_LINK_MISMATCH"),
                        (concept_conflict, "DISJOINT_CAPABILITY_CONCEPTS"),
                        (not linked_reference_ids, "NO_LINKED_ELIGIBLE_REFERENCE"),
                    )
                    if flag
                ),
                "chunk_capability_concepts": ";".join(sorted(chunk_concepts)),
                "metadata_capability_concepts": ";".join(sorted(metadata_concepts)),
                "reported_bad_chunk": str(chunk["chunk_id"]) in REPORTED_BAD_CHUNK_IDS,
                "reported_bad_search_candidate": str(chunk["chunk_id"]) in bad_search_chunk_ids,
                "classification": classification,
                "automatic_classification": classification,
                "automatic_reason": ";".join(quality.rejection_reasons) or (
                    ";".join(
                        reason
                        for flag, reason in (
                            (document_link_mismatch, "DOCUMENT_LINK_MISMATCH"),
                            (concept_conflict, "DISJOINT_CAPABILITY_CONCEPTS"),
                            (not linked_reference_ids, "NO_LINKED_ELIGIBLE_REFERENCE"),
                        )
                        if flag
                    ) or "INTRINSIC_QUALITY_PASS"
                ),
                "data_quality_status": str(chunk.get("data_quality_status") or ""),
                "citation_label": str(chunk.get("citation_label") or ""),
                "citation_uri": str(chunk.get("citation_uri") or ""),
                "display_excerpt": display[:700],
                "raw_text_excerpt": raw[:700],
            }
        )

    audit_frame = pd.DataFrame(audit_rows).sort_values("chunk_id").reset_index(drop=True)
    output_dir = root / "audit" / "corpus_quality"
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "CHUNK_QUALITY_AUDIT.csv"
    audit_frame.to_csv(audit_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)

    document_rows: list[dict[str, Any]] = []
    for source_document, group in audit_frame.groupby("source_document", dropna=False, sort=True):
        classifications = Counter(group["classification"])
        languages = Counter(group["language"])
        document_rows.append(
            {
                "source_document": source_document,
                "chunk_count": len(group),
                "page_count": group["source_page"].nunique(),
                "languages": ";".join(f"{key}:{value}" for key, value in sorted(languages.items())),
                "clean_chunks": classifications["CLEAN"],
                "readable_with_layout_noise_chunks": classifications["READABLE_WITH_LAYOUT_NOISE"],
                "corrupted_chunks": classifications["CORRUPTED"],
                "wrong_page_association_chunks": classifications["WRONG_PAGE_ASSOCIATION"],
                "incoherent_mixed_content_chunks": classifications["INCOHERENT_MIXED_CONTENT"],
                "needs_human_review_chunks": classifications["NEEDS_HUMAN_REVIEW"],
                "evidence_quality_pass_chunks": int(group["evidence_quality_pass"].sum()),
                "evidence_quality_pass_rate": round(float(group["evidence_quality_pass"].mean()), 6),
                "average_evidence_quality_score": round(float(group["evidence_quality_score"].mean()), 6),
                "minimum_evidence_quality_score": round(float(group["evidence_quality_score"].min()), 6),
                "wrong_page_candidates": int(group["wrong_page_candidate"].sum()),
                "reported_bad_chunks": int(group["reported_bad_chunk"].sum()),
            }
        )
    document_frame = pd.DataFrame(document_rows)
    document_path = output_dir / "DOCUMENT_QUALITY_SUMMARY.csv"
    document_frame.to_csv(document_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)

    required_review = audit_frame[
        audit_frame["classification"].isin(
            ["CORRUPTED", "WRONG_PAGE_ASSOCIATION", "INCOHERENT_MIXED_CONTENT", "NEEDS_HUMAN_REVIEW"]
        )
        | audit_frame["wrong_page_candidate"]
        | audit_frame["reported_bad_chunk"]
        | audit_frame["reported_bad_search_candidate"]
    ].copy()
    clean_samples: list[pd.DataFrame] = []
    for language in ("fr", "en", "ar", "mixed"):
        eligible = audit_frame[
            (audit_frame["classification"] == "CLEAN") & (audit_frame["language"] == language)
        ].sort_values("chunk_id")
        clean_samples.append(eligible.head(3))
    sample_frame = pd.concat(clean_samples, ignore_index=True) if clean_samples else pd.DataFrame()
    human = pd.concat([required_review, sample_frame], ignore_index=True).drop_duplicates("chunk_id")
    human = human.sort_values(["classification", "language", "chunk_id"]).reset_index(drop=True)
    human.insert(0, "review_item_id", [f"CQ-{index:04d}" for index in range(1, len(human) + 1)])
    human["human_classification"] = ""
    human["human_wrong_page_judgment"] = ""
    human["human_coherence_judgment"] = ""
    human["human_reviewer_id"] = ""
    human["human_reviewed_at"] = ""
    human["human_comments"] = ""
    human_path = output_dir / "HUMAN_CHUNK_REVIEW.csv"
    human.to_csv(human_path, index=False, encoding="utf-8", quoting=csv.QUOTE_MINIMAL)

    counts = Counter(audit_frame["classification"])
    language_counts = Counter(audit_frame["language"])
    severe_count = (
        counts["CORRUPTED"]
        + counts["WRONG_PAGE_ASSOCIATION"]
        + counts["INCOHERENT_MIXED_CONTENT"]
    )
    top_docs = document_frame.assign(
        severe=lambda value: value["corrupted_chunks"]
        + value["wrong_page_association_chunks"]
        + value["incoherent_mixed_content_chunks"]
    ).sort_values(["severe", "needs_human_review_chunks", "source_document"], ascending=[False, False, True]).head(15)

    lines = [
        "# Corpus Quality Report",
        "",
        "Date: 2026-08-02  ",
        "Scope: exhaustive audit of immutable `data/chunks.parquet`",
        "",
        "## Coverage and integrity",
        "",
        f"- Audited rows: **{len(audit_frame):,} / 1,185**.",
        f"- Unique chunk IDs: **{audit_frame['chunk_id'].nunique():,}**.",
        f"- Source documents: **{audit_frame['source_document'].nunique():,}**.",
        f"- Human-review packet rows: **{len(human):,}**.",
        "- OCR confidence: unavailable in the serving chunk schema; the audit leaves this field blank rather than inventing a value.",
        "",
        "## Classification distribution",
        "",
        "| Classification | Chunks | Percent |",
        "|---|---:|---:|",
    ]
    for label in (
        "CLEAN",
        "READABLE_WITH_LAYOUT_NOISE",
        "CORRUPTED",
        "WRONG_PAGE_ASSOCIATION",
        "INCOHERENT_MIXED_CONTENT",
        "NEEDS_HUMAN_REVIEW",
    ):
        lines.append(f"| {label} | {counts[label]:,} | {counts[label] / len(audit_frame):.2%} |")
    lines += [
        "",
        f"Severe automatic findings (corrupted, wrong association, or incoherent mixed content): **{severe_count:,} ({severe_count / len(audit_frame):.2%})**.",
        "",
        "## Detected language distribution",
        "",
        "| Language | Chunks | Percent |",
        "|---|---:|---:|",
    ]
    for label, count in sorted(language_counts.items()):
        lines.append(f"| {label} | {count:,} | {count / len(audit_frame):.2%} |")
    lines += [
        "",
        "## Quality gate summary",
        "",
        f"- Evidence-quality pass: **{int(audit_frame['evidence_quality_pass'].sum()):,} / {len(audit_frame):,} ({audit_frame['evidence_quality_pass'].mean():.2%})**.",
        f"- Wrong-page candidates requiring review: **{int(audit_frame['wrong_page_candidate'].sum()):,}**.",
        f"- Previously reported bad chunks present: **{int(audit_frame['reported_bad_chunk'].sum()):,} / {len(REPORTED_BAD_CHUNK_IDS)}**.",
        f"- Chunks involved in the reproduced bad search: **{int(audit_frame['reported_bad_search_candidate'].sum()):,}**.",
        "",
        "## Most affected documents",
        "",
        "| Source document | Chunks | Severe | Needs review | Quality pass rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in top_docs.to_dict(orient="records"):
        source_label = str(row["source_document"]).replace("|", "&#124;")
        lines.append(
            f"| {source_label} | {row['chunk_count']} | {row['severe']} | "
            f"{row['needs_human_review_chunks']} | {row['evidence_quality_pass_rate']:.2%} |"
        )
    lines += [
        "",
        "## Method and interpretation",
        "",
        "The audit reuses the serving evidence-quality evaluator with an empty query, so only intrinsic text quality is measured. It does not convert retrieval scores or metadata into relevance labels. `CORRUPTED` requires a severe deterministic text-quality reason. `INCOHERENT_MIXED_CONTENT` requires the evaluator's mixed-script incoherence rule. `WRONG_PAGE_ASSOCIATION` is assigned only for a canonical-document linkage mismatch; weaker disjoint-capability or missing-link signals are candidates for human review. Clean-vs-layout-noise classification uses transparent fragmentation, repetition, single-character, and suspicious-symbol indicators.",
        "",
        "The automated labels are triage decisions, not substitutes for human review. Every severe item, every wrong-page candidate, every prior reported-bad chunk, every `NEEDS_HUMAN_REVIEW` item, and deterministic clean samples for available FR/EN/AR/mixed languages are included in `HUMAN_CHUNK_REVIEW.csv` with blank human fields.",
        "",
        "## Artifacts",
        "",
        "- `CHUNK_QUALITY_AUDIT.csv`: one row for every serving chunk.",
        "- `DOCUMENT_QUALITY_SUMMARY.csv`: source-document aggregation.",
        "- `HUMAN_CHUNK_REVIEW.csv`: blinded human validation packet.",
    ]
    report_path = output_dir / "CORPUS_QUALITY_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "audited_chunks": len(audit_frame),
        "classifications": dict(sorted(counts.items())),
        "human_review_rows": len(human),
        "wrong_page_candidates": int(audit_frame["wrong_page_candidate"].sum()),
        "reported_bad_chunks_found": int(audit_frame["reported_bad_chunk"].sum()),
        "outputs": [str(audit_path), str(document_path), str(report_path), str(human_path)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit every serving chunk without modifying corpus artifacts.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
