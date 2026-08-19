from __future__ import annotations

from pathlib import Path

import pytest

from reference_narrative.quality import (
    assess_target_language,
    calculate_narrative_completeness,
    count_factual_drift,
)
from reference_narrative.schemas import (
    FieldSupportPlan,
    NarrativeSupportPlan,
    NarrativeValidationResult,
    ReferenceNarrative,
    ReferenceSectionNarrative,
    SectionSupportPlan,
    SupportedNarrativeText,
    ValidationSeverity,
    ValidationWarning,
)
from scripts.benchmark_reference_narrative_models import (
    CANDIDATE_MAPPING,
    _blind_review,
    _memory_snapshot,
    _selection_gates,
    _unload_benchmark_models,
)
from scripts.evaluate_reference_narrative import load_cases


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = "a" * 64
SUPPORT_ID = "S001"


def _text(value: str) -> SupportedNarrativeText:
    return SupportedNarrativeText(text=value, support_ids=[SUPPORT_ID] if value else [])


def _narrative(value: str, *, benefits: list[str] | None = None) -> ReferenceSectionNarrative:
    return ReferenceSectionNarrative(
        section_intro=_text(value),
        overall_storyline=_text(value),
        why_these_references=_text(value),
        references=[
            ReferenceNarrative(
                reference_id=REFERENCE_ID,
                headline=_text(value),
                short_description=_text(value),
                challenge=_text(""),
                devoteam_contribution=_text(value),
                realisations=[],
                benefits=[_text(item) for item in (benefits or [])],
                why_relevant_to_opportunity=_text(value),
            )
        ],
    )


@pytest.mark.parametrize(
    ("language", "value"),
    [
        ("fr", "Cette mission est une référence pour le client et les équipes dans le secteur bancaire."),
        ("en", "This mission is a relevant reference for the client and their teams in the banking sector."),
        ("ar", "هذه المهمة مرجع مهم للعميل ولفرق العمل في القطاع المصرفي."),
    ],
)
def test_deterministic_language_check_accepts_target_language(language: str, value: str) -> None:
    result = assess_target_language(_narrative(value), language)

    assert result.compliant is True
    assert result.status == "PASS"
    assert result.detected_language == language


def test_deterministic_language_check_rejects_wrong_language() -> None:
    value = "This mission is a relevant reference for the client and their teams in the banking sector."

    result = assess_target_language(_narrative(value), "fr")

    assert result.compliant is False
    assert result.status == "CLEAR_MISMATCH"
    assert result.detected_language == "en"


@pytest.mark.parametrize(
    "value",
    [
        "Opérationnalisation du PCA de la BCT avec préparation du MCO pour les équipes.",
        "Cette mission menée pour la Banque centrale de Tunisie structure les procédures de continuité.",
    ],
)
def test_french_acronyms_and_client_names_are_language_neutral(value: str) -> None:
    result = assess_target_language(_narrative(value), "fr")

    assert result.status == "PASS"
    assert result.compliant is True


def test_short_acronym_heavy_title_is_uncertain_not_a_failure() -> None:
    result = assess_target_language(_narrative("PCA BCT MCO PSI PMO SI"), "fr")

    assert result.status == "UNCERTAIN"
    assert result.compliant is True


def test_completeness_uses_only_eligible_fields_and_marks_blocked_content_unusable() -> None:
    narrative = _narrative("Grounded reference", benefits=[])
    plan = NarrativeSupportPlan(
        references=[
            FieldSupportPlan(
                reference_id=REFERENCE_ID,
                headline=[SUPPORT_ID],
                benefits=[SUPPORT_ID],
            )
        ],
        section=SectionSupportPlan(),
    )
    validation = NarrativeValidationResult(
        valid=False,
        export_blocked=True,
        warnings=[
            ValidationWarning(
                code="UNSUPPORTED_SUCCESS_CLAIM",
                message="Unsupported claim",
                severity=ValidationSeverity.BLOCKING,
                field_path="references[0].headline",
            )
        ],
    )

    metrics = calculate_narrative_completeness(narrative, plan, validation)

    assert metrics.eligible_field_count == 2
    assert metrics.populated_eligible_field_count == 1
    assert metrics.empty_eligible_field_count == 1
    assert metrics.usable_eligible_field_count == 0
    assert metrics.unusable_eligible_field_count == 1
    assert metrics.eligible_field_population_rate == 0.5


def test_factual_drift_counts_only_blocking_factual_codes() -> None:
    validation = NarrativeValidationResult(
        valid=False,
        export_blocked=True,
        warnings=[
            ValidationWarning(
                code="UNSUPPORTED_YEAR",
                message="Invented year",
                severity=ValidationSeverity.BLOCKING,
            ),
            ValidationWarning(
                code="WEAK_SOURCE_SUPPORT",
                message="Weak source",
                severity=ValidationSeverity.WARNING,
            ),
        ],
    )

    assert count_factual_drift(validation) == 1


def test_blind_review_hides_model_names_and_leaves_scores_blank() -> None:
    case = load_cases(PROJECT_ROOT / "evaluation" / "reference_narrative" / "cases.json").cases[0]
    result = {"status": "completed", "narrative": _narrative("Grounded reference").model_dump(mode="json")}

    content = _blind_review(case, {candidate: result for candidate in CANDIDATE_MAPPING})

    assert all(model not in content for model in CANDIDATE_MAPPING.values())
    assert "Candidate A" in content and "Candidate B" in content and "Candidate C" in content
    assert "- FACTUAL FIDELITY (1–5):\n" in content
    assert "Reviewer comments:\n" in content

    failed_content = _blind_review(
        case,
        {candidate: {"status": "failed"} for candidate in CANDIDATE_MAPPING},
    )
    assert failed_content.count("- FACTUAL FIDELITY (1–5):") == 3


def test_memory_snapshot_has_machine_readable_values_on_windows() -> None:
    snapshot = _memory_snapshot()

    assert "status" in snapshot or (
        int(snapshot["total_bytes"]) > 0 and int(snapshot["free_bytes"]) > 0
    )


def test_selection_gates_are_individual_and_strict_without_an_aggregate_score() -> None:
    model_summary = {
        "case_count": 8,
        "schema_success_count": 8,
        "structured_retry_count": 0,
        "target_language_compliant_case_count": 8,
        "factual_drift_count": 1,
        "proposal_completion_confusion_count": 0,
        "backend_guarantees": {
            "reference_identity_coverage": 1.0,
            "deterministic_support_coverage": 1.0,
            "unknown_support_id_count": 0,
            "unselected_support_count": 0,
            "empty_support_field_violation_count": 0,
            "blocking_provenance_count": 0,
        },
    }

    gates = _selection_gates(model_summary)

    assert gates["automated_gate_pass"] is True
    model_summary["factual_drift_count"] = 2
    assert _selection_gates(model_summary)["automated_gate_pass"] is False


def test_runtime_isolation_unloads_only_loaded_benchmark_models(monkeypatch) -> None:
    calls: list[tuple[str, dict | None]] = []

    class Response:
        def __init__(self, payload: dict | None = None):
            self.payload = payload or {}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def fake_get(url: str, timeout: int):
        assert timeout == 20
        calls.append((url, None))
        return Response({"models": [{"name": "qwen3:8b"}, {"name": "unrelated:latest"}]})

    def fake_post(url: str, json: dict, timeout: int):
        assert timeout == 20
        calls.append((url, json))
        return Response()

    monkeypatch.setattr("scripts.benchmark_reference_narrative_models.httpx.get", fake_get)
    monkeypatch.setattr("scripts.benchmark_reference_narrative_models.httpx.post", fake_post)

    unloaded = _unload_benchmark_models(
        "http://127.0.0.1:11434",
        ["qwen2.5-coder:7b-instruct", "qwen3:8b", "qwen3.5:9b"],
    )

    assert unloaded == ["qwen3:8b"]
    assert calls[-1][1] == {"model": "qwen3:8b", "keep_alive": 0}
