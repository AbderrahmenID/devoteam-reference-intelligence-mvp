from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.dependencies import get_reference_narrative_service  # noqa: E402
from reference_narrative.quality import calculate_backend_guarantees, calculate_model_quality  # noqa: E402
from reference_narrative.schemas import NarrativeGenerationRequest  # noqa: E402
from reference_narrative.service import NarrativeStructuredOutputError, ReferenceNarrativeService  # noqa: E402


CLASSIFICATION = "DEVELOPMENT / NON-PRODUCTION"
DEFAULT_CASES = PROJECT_ROOT / "evaluation" / "reference_narrative" / "cases.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "reference_narrative" / "results"


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    request: NarrativeGenerationRequest


class EvaluationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    classification: str
    cases: list[EvaluationCase] = Field(min_length=1, max_length=20)

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, value: str) -> str:
        if value != CLASSIFICATION:
            raise ValueError(f"classification must be {CLASSIFICATION!r}")
        return value

    @field_validator("cases")
    @classmethod
    def validate_unique_case_ids(cls, values: list[EvaluationCase]) -> list[EvaluationCase]:
        case_ids = [case.case_id for case in values]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case IDs must be unique")
        return values


def load_cases(path: Path) -> EvaluationSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationSuite.model_validate(payload)


def _warning_counts(warnings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"INFO": 0, "WARNING": 0, "BLOCKING": 0}
    for warning in warnings:
        severity = str(warning.get("severity", "BLOCKING"))
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _field_markdown(label: str, value: dict[str, Any]) -> str:
    text = str(value.get("text", "")).strip() or "_(empty)_"
    supports = ", ".join(value.get("support_ids", [])) or "none"
    return f"- **{label}:** {text}\n  - Supports: `{supports}`"


def _case_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['title']}",
        "",
        f"> **{CLASSIFICATION}** — generated output for human review; not approved for proposal use.",
        "",
        f"- Case: `{result['case_id']}`",
        f"- Status: `{result['status']}`",
        f"- Provider/model: `{result.get('provider', '')}` / `{result.get('model', '')}`",
        f"- Latency: `{result['latency_ms']:.1f} ms`",
        f"- Schema failures: `{result['schema_failure_count']}`",
    ]
    if result["status"] != "completed":
        lines.extend(["", "## Error", "", str(result.get("error", "Unknown error"))])
        return "\n".join(lines) + "\n"

    backend = result["backend_guarantees"]
    model_quality = result["model_quality"]
    validation = result["validation"]
    lines.extend(
        [
            f"- Validation valid: `{validation['valid']}`",
            f"- Export eligible: `{validation['export_eligible']}`",
            f"- Backend identity coverage: `{backend['reference_identity_coverage']:.1%}`",
            f"- Deterministic support coverage: `{backend['deterministic_support_coverage']:.1%}`",
            f"- Empty-support violations: `{backend['empty_support_field_violation_count']}`",
            f"- Model words / exact duplicates: `{model_quality['total_word_count']}` / `{model_quality['duplicate_text_count']}`",
            "",
            "## Section narrative",
            "",
        ]
    )
    narrative = result["narrative"]
    for key in ("section_intro", "overall_storyline", "why_these_references"):
        lines.append(_field_markdown(key, narrative[key]))
    for index, reference in enumerate(narrative["references"], start=1):
        lines.extend(["", f"## Reference {index}: `{reference['reference_id']}`", ""])
        for key in ("headline", "short_description", "challenge", "devoteam_contribution"):
            lines.append(_field_markdown(key, reference[key]))
        for key in ("realisations", "benefits"):
            if not reference[key]:
                lines.append(f"- **{key}:** _(empty)_")
            for bullet_index, bullet in enumerate(reference[key], start=1):
                lines.append(_field_markdown(f"{key} {bullet_index}", bullet))
        lines.append(_field_markdown("why_relevant_to_opportunity", reference["why_relevant_to_opportunity"]))
    lines.extend(["", "## Validation warnings", ""])
    if not result["warnings"]:
        lines.append("No warnings.")
    for warning in result["warnings"]:
        lines.append(
            f"- `{warning['severity']}` `{warning['code']}` — {warning['message']} "
            f"(field: `{warning.get('field_path') or 'n/a'}`)"
        )
    return "\n".join(lines) + "\n"


def evaluate_case(service: ReferenceNarrativeService, case: EvaluationCase) -> dict[str, Any]:
    started = time.perf_counter()
    generation_stats = getattr(service.provider, "generation_stats", None)
    stats_start = len(generation_stats) if isinstance(generation_stats, list) else 0
    try:
        response = service.generate(case.request)
    except Exception as exc:
        case_generation_stats = generation_stats[stats_start:] if isinstance(generation_stats, list) else []
        return {
            "classification": CLASSIFICATION,
            "case_id": case.case_id,
            "title": case.title,
            "description": case.description,
            "request": case.request.model_dump(mode="json"),
            "status": "failed",
            "provider": getattr(service.provider, "provider_name", ""),
            "model": getattr(service.provider, "model_name", ""),
            "latency_ms": (time.perf_counter() - started) * 1000,
            "schema_failure_count": 1 if isinstance(exc, NarrativeStructuredOutputError) else 0,
            "structured_output_retry_count": (
                1 if isinstance(exc, NarrativeStructuredOutputError) else 0
            ),
            "generation_usage": {
                "call_count": len(case_generation_stats),
                "prompt_token_count": sum(
                    int(item.get("prompt_token_count") or 0) for item in case_generation_stats
                ) or None,
                "generated_token_count": sum(
                    int(item.get("generated_token_count") or 0) for item in case_generation_stats
                ) or None,
                "calls": case_generation_stats,
            },
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    latency_ms = (time.perf_counter() - started) * 1000
    case_generation_stats = generation_stats[stats_start:] if isinstance(generation_stats, list) else []
    response_data = response.model_dump(mode="json")
    support_index = {support.support_id: support for support in response.source_supports}
    backend_metrics = calculate_backend_guarantees(
        response.narrative,
        support_index,  # safe summaries expose the ownership needed by the metric
        case.request.selected_reference_ids,
        response.support_plan,
        response.validation,
    )
    model_metrics = calculate_model_quality(response.narrative, case.request.target_language, latency_ms)
    warnings = [warning.model_dump(mode="json") for warning in response.warnings]
    return {
        "classification": CLASSIFICATION,
        "case_id": case.case_id,
        "title": case.title,
        "description": case.description,
        "request": case.request.model_dump(mode="json"),
        "status": "completed",
        "provider": response.provenance.provider,
        "model": response.provenance.model,
        "latency_ms": latency_ms,
        "schema_failure_count": 0,
        "structured_output_retry_count": response.provenance.structured_output_retry_count,
        "generation_usage": {
            "call_count": len(case_generation_stats),
            "prompt_token_count": sum(
                int(item.get("prompt_token_count") or 0) for item in case_generation_stats
            ) or None,
            "generated_token_count": sum(
                int(item.get("generated_token_count") or 0) for item in case_generation_stats
            ) or None,
            "calls": case_generation_stats,
        },
        "narrative": response_data["narrative"],
        "validation": response_data["validation"],
        "warnings": warnings,
        "warning_counts": _warning_counts(warnings),
        "backend_guarantees": asdict(backend_metrics),
        "model_quality": asdict(model_metrics),
        "source_supports": response_data["source_supports"],
        "support_plan": response_data["support_plan"],
        "provenance": response_data["provenance"],
    }


def run_suite(
    service: ReferenceNarrativeService,
    suite: EvaluationSuite,
    output_dir: Path,
    selected_case_ids: set[str] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [case for case in suite.cases if not selected_case_ids or case.case_id in selected_case_ids]
    if selected_case_ids and {case.case_id for case in cases} != selected_case_ids:
        missing = sorted(selected_case_ids - {case.case_id for case in cases})
        raise ValueError(f"unknown case IDs: {', '.join(missing)}")
    results: list[dict[str, Any]] = []
    for case in cases:
        result = evaluate_case(service, case)
        results.append(result)
        (output_dir / f"{case.case_id}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (output_dir / f"{case.case_id}.md").write_text(_case_markdown(result), encoding="utf-8")
        print(f"{case.case_id}: {result['status']} ({result['latency_ms']:.1f} ms)", flush=True)

    completed = [result for result in results if result["status"] == "completed"]
    summary = {
        "classification": CLASSIFICATION,
        "suite": suite.suite,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(results),
        "completed_case_count": len(completed),
        "failed_case_count": len(results) - len(completed),
        "schema_failure_count": sum(result["schema_failure_count"] for result in results),
        "valid_case_count": sum(bool(result["validation"]["valid"]) for result in completed),
        "export_eligible_case_count": sum(bool(result["validation"]["export_eligible"]) for result in completed),
        "backend_guarantees": {
            "reference_identity_coverage": (
                sum(result["backend_guarantees"]["reference_identity_count"] for result in completed)
                / max(1, sum(result["backend_guarantees"]["expected_reference_count"] for result in completed))
            ),
            "deterministic_support_coverage": (
                sum(result["backend_guarantees"]["deterministically_supported_field_count"] for result in completed)
                / max(1, sum(result["backend_guarantees"]["eligible_populated_field_count"] for result in completed))
            ),
            "unknown_support_id_count": sum(
                result["backend_guarantees"]["unknown_support_id_count"] for result in completed
            ),
            "unselected_support_count": sum(
                result["backend_guarantees"]["unselected_support_count"] for result in completed
            ),
            "empty_support_field_violation_count": sum(
                result["backend_guarantees"]["empty_support_field_violation_count"] for result in completed
            ),
            "blocking_provenance_count": sum(
                result["backend_guarantees"]["blocking_provenance_count"] for result in completed
            ),
        },
        "model_quality": {
            "median_latency_ms": (
                statistics.median(result["model_quality"]["latency_ms"] for result in completed)
                if completed
                else None
            ),
            "total_word_count": sum(result["model_quality"]["total_word_count"] for result in completed),
            "duplicate_text_count": sum(
                result["model_quality"]["duplicate_text_count"] for result in completed
            ),
            "human_review_required": True,
        },
        "case_results": [
            {
                "case_id": result["case_id"],
                "status": result["status"],
                "latency_ms": result["latency_ms"],
                "schema_failure_count": result["schema_failure_count"],
                "valid": result.get("validation", {}).get("valid"),
                "export_eligible": result.get("validation", {}).get("export_eligible"),
                "backend_guarantees": result.get("backend_guarantees"),
                "model_quality": result.get("model_quality"),
                "warning_counts": result.get("warning_counts"),
            }
            for result in results
        ],
    }
    (output_dir / "development_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run development-only reference narrative evaluation cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        suite = load_cases(args.cases)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid evaluation fixture: {exc}", file=sys.stderr)
        return 2
    if args.validate_only:
        print(f"Validated {len(suite.cases)} {CLASSIFICATION} cases from {args.cases}")
        return 0
    try:
        summary = run_suite(
            get_reference_narrative_service(),
            suite,
            args.output_dir,
            set(args.case_ids) if args.case_ids else None,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0 if summary["failed_case_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
