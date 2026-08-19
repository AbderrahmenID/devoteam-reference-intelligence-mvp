from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.settings import load_config  # noqa: E402
from reference_narrative.ollama_client import OllamaNarrativeClient  # noqa: E402
from reference_narrative.quality import (  # noqa: E402
    assess_target_language,
    calculate_narrative_completeness,
    count_factual_drift,
)
from reference_narrative.schemas import (  # noqa: E402
    NarrativeSupportPlan,
    NarrativeValidationResult,
    ReferenceSectionNarrative,
)
from reference_narrative.service import ReferenceNarrativeService  # noqa: E402
from reference_pack.validation import TrustedV2Repository  # noqa: E402
from scripts.evaluate_reference_narrative import (  # noqa: E402
    CLASSIFICATION,
    DEFAULT_CASES,
    EvaluationCase,
    evaluate_case,
    load_cases,
)


DEFAULT_MODELS = ["qwen2.5-coder:7b-instruct", "qwen3:8b", "qwen3.5:9b"]
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "reference_narrative" / "model_benchmark"
CANDIDATE_MAPPING = {
    "Candidate A": "qwen3.5:9b",
    "Candidate B": "qwen2.5-coder:7b-instruct",
    "Candidate C": "qwen3:8b",
}


def _slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", model.casefold()).strip("_")


def _command_output(command: list[str]) -> str:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _installed_models(base_url: str) -> dict[str, dict[str, Any]]:
    response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=20)
    response.raise_for_status()
    return {str(item["name"]): item for item in response.json().get("models", [])}


def _unload_benchmark_models(base_url: str, models: list[str]) -> list[str]:
    response = httpx.get(f"{base_url.rstrip('/')}/api/ps", timeout=20)
    response.raise_for_status()
    loaded = {str(item["name"]) for item in response.json().get("models", [])}
    unloaded: list[str] = []
    for model in models:
        if model not in loaded:
            continue
        stop = httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=20,
        )
        stop.raise_for_status()
        unloaded.append(model)
    return unloaded


def _memory_snapshot() -> dict[str, int | str]:
    if platform.system() != "Windows":
        return {"status": "unavailable"}
    raw = _command_output(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$os=Get-CimInstance Win32_OperatingSystem; "
                "[pscustomobject]@{total_bytes=[int64]$os.TotalVisibleMemorySize*1024; "
                "free_bytes=[int64]$os.FreePhysicalMemory*1024}|ConvertTo-Json -Compress"
            ),
        ]
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": raw}


def _environment(base_url: str, installed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    disk = shutil.disk_usage(PROJECT_ROOT)
    gpu_csv = _command_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,memory.used,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "classification": CLASSIFICATION,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "ollama_version": _command_output(["ollama", "--version"]),
        "ollama_url": base_url,
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "memory": _memory_snapshot(),
        "gpu_nvidia_smi": gpu_csv,
        "models": {
            name: {
                "digest": details.get("digest"),
                "size_bytes": details.get("size"),
                "details": details.get("details", {}),
            }
            for name, details in installed.items()
        },
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _enhance_result(result: dict[str, Any], case: EvaluationCase) -> dict[str, Any]:
    result["language"] = case.request.target_language
    result["schema_success"] = result["status"] == "completed"
    if result["status"] != "completed":
        result["language_compliance"] = None
        result["completeness"] = None
        result["factual_drift_count"] = None
        result["model_quality_failures"] = ["SCHEMA_FAILURE"]
        return result
    narrative = ReferenceSectionNarrative.model_validate(result["narrative"])
    support_plan = NarrativeSupportPlan.model_validate(result["support_plan"])
    validation = NarrativeValidationResult.model_validate(result["validation"])
    language = assess_target_language(narrative, case.request.target_language)
    completeness = calculate_narrative_completeness(narrative, support_plan, validation)
    factual_drift_count = count_factual_drift(validation)
    failures: list[str] = []
    if not language.compliant:
        failures.append("TARGET_LANGUAGE_NONCOMPLIANCE")
    if factual_drift_count:
        failures.append("FACTUAL_DRIFT")
    if completeness.unusable_eligible_field_count:
        failures.append("UNUSABLE_ELIGIBLE_CONTENT")
    result["language_compliance"] = asdict(language)
    result["completeness"] = asdict(completeness)
    result["factual_drift_count"] = factual_drift_count
    result["model_quality_failures"] = failures
    return result


def _model_summary(model: str, results: list[dict[str, Any]], artifact: dict[str, Any]) -> dict[str, Any]:
    completed = [result for result in results if result["status"] == "completed"]
    schema_success_count = len(completed)
    latencies = [float(result["latency_ms"]) for result in results]
    eligible = sum(result["completeness"]["eligible_field_count"] for result in completed)
    populated = sum(result["completeness"]["populated_eligible_field_count"] for result in completed)
    backend = [result["backend_guarantees"] for result in completed]
    return {
        "model": model,
        "artifact_digest": artifact.get("digest"),
        "artifact_size_bytes": artifact.get("size"),
        "case_count": len(results),
        "schema_success_count": schema_success_count,
        "schema_success_rate": schema_success_count / len(results) if results else 0.0,
        "target_language_compliant_case_count": sum(
            bool(result["language_compliance"]["compliant"]) for result in completed
        ),
        "target_language_compliance_rate": (
            sum(bool(result["language_compliance"]["compliant"]) for result in completed)
            / len(results)
            if results
            else 0.0
        ),
        "valid_case_count": sum(bool(result["validation"]["valid"]) for result in completed),
        "export_eligible_case_count": sum(
            bool(result["validation"]["export_eligible"]) for result in completed
        ),
        "blocking_warning_count": sum(
            result["warning_counts"].get("BLOCKING", 0) for result in completed
        ),
        "factual_drift_count": sum(int(result["factual_drift_count"]) for result in completed),
        "proposal_completion_confusion_count": sum(
            warning["code"] in {"PROPOSAL_SCOPE_AS_COMPLETED", "UNSUPPORTED_COMPLETION_LANGUAGE"}
            and warning["severity"] == "BLOCKING"
            for result in completed
            for warning in result["warnings"]
        ),
        "eligible_field_count": eligible,
        "populated_eligible_field_count": populated,
        "empty_eligible_field_count": sum(
            result["completeness"]["empty_eligible_field_count"] for result in completed
        ),
        "unusable_eligible_field_count": sum(
            result["completeness"]["unusable_eligible_field_count"] for result in completed
        ),
        "eligible_field_population_rate": populated / eligible if eligible else 1.0,
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "structured_retry_count": sum(
            int(result.get("structured_output_retry_count") or 0) for result in results
        ),
        "prompt_token_count": sum(
            int(result.get("generation_usage", {}).get("prompt_token_count") or 0) for result in results
        ) or None,
        "generated_token_count": sum(
            int(result.get("generation_usage", {}).get("generated_token_count") or 0) for result in results
        ) or None,
        "backend_guarantees": {
            "reference_identity_coverage": (
                sum(item["reference_identity_count"] for item in backend)
                / max(1, sum(item["expected_reference_count"] for item in backend))
            ),
            "deterministic_support_coverage": (
                sum(item["deterministically_supported_field_count"] for item in backend)
                / max(1, sum(item["eligible_populated_field_count"] for item in backend))
            ),
            "unknown_support_id_count": sum(item["unknown_support_id_count"] for item in backend),
            "unselected_support_count": sum(item["unselected_support_count"] for item in backend),
            "empty_support_field_violation_count": sum(
                item["empty_support_field_violation_count"] for item in backend
            ),
            "blocking_provenance_count": sum(item["blocking_provenance_count"] for item in backend),
        },
    }


def _selection_gates(summary: dict[str, Any]) -> dict[str, bool]:
    backend = summary["backend_guarantees"]
    gates = {
        "schema_reliability": (
            summary["schema_success_count"] == summary["case_count"]
            and summary["structured_retry_count"] <= 1
        ),
        "target_language_compliance": (
            summary["target_language_compliant_case_count"] == summary["case_count"]
        ),
        "provenance_integrity": (
            backend["reference_identity_coverage"] == 1.0
            and backend["deterministic_support_coverage"] == 1.0
            and backend["unknown_support_id_count"] == 0
            and backend["unselected_support_count"] == 0
            and backend["empty_support_field_violation_count"] == 0
            and backend["blocking_provenance_count"] == 0
        ),
        "no_repeated_factual_drift": summary["factual_drift_count"] <= 1,
        "no_proposal_completion_confusion": summary["proposal_completion_confusion_count"] == 0,
    }
    gates["automated_gate_pass"] = all(gates.values())
    return gates


def _field_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item.get('text', '').strip()}" for item in value if item.get("text", "").strip()) or "_(empty)_"
    return str(value.get("text", "")).strip() or "_(empty)_"


def _blind_review(case: EvaluationCase, candidates: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# CASE_{case.case_id}_BLIND_REVIEW",
        "",
        f"> **{CLASSIFICATION}** — model identities are intentionally hidden.",
        "",
        f"- Opportunity: {case.request.opportunity_title}",
        f"- Target language: `{case.request.target_language}`",
        "",
    ]
    for candidate, result in candidates.items():
        lines.extend([f"## {candidate}", ""])
        if result["status"] != "completed":
            lines.extend(["Generation failed.", ""])
        else:
            for index, reference in enumerate(result["narrative"]["references"], start=1):
                lines.extend([f"### Reference {index}", ""])
                for label, key in (
                    ("Headline", "headline"),
                    ("Description", "short_description"),
                    ("Challenge", "challenge"),
                    ("Contribution", "devoteam_contribution"),
                    ("Realisations", "realisations"),
                    ("Benefits", "benefits"),
                    ("Opportunity relevance", "why_relevant_to_opportunity"),
                ):
                    lines.extend([f"**{label}**", "", _field_text(reference[key]), ""])
        lines.extend(
            [
                "### Reviewer rubric",
                "",
                "- FACTUAL FIDELITY (1–5):",
                "- LANGUAGE QUALITY (1–5):",
                "- COMMERCIAL USEFULNESS (1–5):",
                "- CLARITY/CONCISION (1–5):",
                "- COMPLETENESS (1–5):",
                "",
                "Reviewer comments:",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Controlled multilingual narrative model benchmark",
        "",
        f"> **{CLASSIFICATION}** — automated metrics only; blind human scores remain unfilled.",
        "",
        "| Model | Schema | Language | Valid | Blocking | Drift | Eligible populated | Median ms | P95 ms | Retries |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["models"]:
        median = f"{item['median_latency_ms']:.1f}" if item["median_latency_ms"] is not None else "n/a"
        p95 = f"{item['p95_latency_ms']:.1f}" if item["p95_latency_ms"] is not None else "n/a"
        lines.append(
            f"| {item['model']} | {item['schema_success_rate']:.0%} | "
            f"{item['target_language_compliance_rate']:.0%} | {item['valid_case_count']}/8 | "
            f"{item['blocking_warning_count']} | {item['factual_drift_count']} | "
            f"{item['eligible_field_population_rate']:.0%} | {median} | "
            f"{p95} | {item['structured_retry_count']} |"
        )
    lines.extend(
        [
            "",
            "No aggregate score is calculated. Factual fidelity and target-language compliance are selection gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_benchmark(models: list[str], cases_path: Path, output_dir: Path, base_url: str, timeout: float) -> dict[str, Any]:
    suite = load_cases(cases_path)
    installed = _installed_models(base_url)
    missing = [model for model in models if model not in installed]
    if missing:
        raise RuntimeError(f"Required benchmark models are not installed: {', '.join(missing)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw_safe_results"
    blind_dir = output_dir / "blind_reviews"
    raw_dir.mkdir(parents=True, exist_ok=True)
    blind_dir.mkdir(parents=True, exist_ok=True)
    environment = _environment(base_url, installed)
    (output_dir / "benchmark_environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    results_by_model: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        _unload_benchmark_models(base_url, models)
        provider = OllamaNarrativeClient(base_url, model, timeout)
        repository = TrustedV2Repository(PROJECT_ROOT, load_config())
        service = ReferenceNarrativeService(repository, provider)
        model_dir = raw_dir / _slug(model)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_results: list[dict[str, Any]] = []
        for case in suite.cases:
            result = _enhance_result(evaluate_case(service, case), case)
            model_results.append(result)
            (model_dir / f"{case.case_id}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"{model} / {case.case_id}: {result['status']} ({result['latency_ms']:.1f} ms)", flush=True)
        results_by_model[model] = model_results
    _unload_benchmark_models(base_url, models)

    mapping = {
        "classification": "CONFIDENTIAL / DEVELOPMENT",
        "mapping": CANDIDATE_MAPPING,
    }
    (output_dir / "BLIND_CANDIDATE_MAPPING.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for case_index, case in enumerate(suite.cases):
        candidates = {
            candidate: results_by_model[model][case_index]
            for candidate, model in CANDIDATE_MAPPING.items()
        }
        (blind_dir / f"CASE_{case.case_id}_BLIND_REVIEW.md").write_text(
            _blind_review(case, candidates), encoding="utf-8"
        )
    model_summaries = [
        _model_summary(model, results_by_model[model], installed[model]) for model in models
    ]
    for model_summary in model_summaries:
        model_summary["selection_gates"] = _selection_gates(model_summary)
    summary = {
        "classification": CLASSIFICATION,
        "suite": suite.suite,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(suite.cases),
        "runtime_isolation": "All benchmark models unloaded before each candidate; cold-load latency included.",
        "models": model_summaries,
        "aggregate_score": None,
        "blind_review_directory": "blind_reviews",
        "confidential_mapping": "BLIND_CANDIDATE_MAPPING.json",
    }
    (output_dir / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "benchmark_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark the approved local narrative models.")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = args.models or DEFAULT_MODELS
    if models != DEFAULT_MODELS:
        print("Warning: non-default model ordering requested", file=sys.stderr)
    try:
        run_benchmark(models, args.cases, args.output_dir, args.ollama_url, args.timeout_seconds)
    except Exception as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
