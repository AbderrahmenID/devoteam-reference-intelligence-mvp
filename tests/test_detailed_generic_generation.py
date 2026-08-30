from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.api.settings import PROJECT_ROOT, load_config
from reference_narrative.field_policy import build_detailed_presentation_support_plan
from reference_narrative.ollama_client import DisabledNarrativeProvider
from reference_narrative.presentation_copy import (
    DetailedRealisationCopy,
    DetailedReferenceCopy,
    PresentationCopyService,
    _source_activity_clauses,
    build_detailed_prompt,
)
from reference_narrative.presentation_schemas import DirectPresentationRequest
from reference_narrative.quality import assess_reference_language
from reference_narrative.service import ReferenceNarrativeService
from reference_pack.validation import TrustedV2Repository


REFERENCE_A = "6f1f43d3bfa0132fe5d5a08c4a17868e0521f514a0336d065a227518e2a3e6dd"
REFERENCE_B = "7d7b037dca83a49215fb4c22852c76ff11e98b80f3cc019feaf959620b140fab"


class _SequentialProvider:
    def __init__(self, responses: list[DetailedReferenceCopy]):
        self.responses = responses
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages, _response_schema) -> str:
        self.calls.append(messages)
        return self.responses[len(self.calls) - 1].model_dump_json()


class _LanguageRepairService(PresentationCopyService):
    """Keep this regression focused on orchestration around the real detector."""

    def _safe_supported_portions(self, request, source_result, bundle, plan, candidate):
        return self._reference_from_copy(candidate, plan, request.template_id)

    def _validate_one(self, source_result, bundle, plan, narrative):
        return SimpleNamespace(warnings=[])

    def _detailed_quality_status(self, request, bundle, plan, narrative):
        result = assess_reference_language(narrative, request.target_language)
        return {"language_ok": result.status != "CLEAR_MISMATCH"}


def test_source_activity_parser_splits_semicolons_and_benchmark_workstreams() -> None:
    clauses = _source_activity_clauses(
        "Recueil des besoins métiers Benchmark international; Analyse des écarts; "
        "Élaboration de la feuille de route"
    )
    assert clauses == [
        "Recueil des besoins métiers",
        "Benchmark international",
        "Analyse des écarts",
        "Élaboration de la feuille de route",
    ]


def test_repeated_response_tail_is_removed_without_domain_rules() -> None:
    value = "Fournir un reporting mensuel avec les indicateurs par application Fournir un"
    assert PresentationCopyService._strip_repeated_trailing_fragment(value) == (
        "Fournir un reporting mensuel avec les indicateurs par application"
    )


def test_dangling_connector_is_removed_from_cutoff_bullet() -> None:
    assert PresentationCopyService._strip_dangling_tail(
        "Plans de communication et de"
    ) == "Plans de communication"


def test_orphan_test_phase_is_not_attached_to_unrelated_activity() -> None:
    assert PresentationCopyService._strip_orphan_phase_label(
        "Rédaction du plan de communication de crise (Phase 2 : Test)."
    ) == "Rédaction du plan de communication de crise."
    assert PresentationCopyService._strip_orphan_phase_label(
        "Préparation du premier test PCA (Phase 2 : Test)."
    ).endswith("(Phase 2 : Test).")


def test_multi_clause_subitem_is_not_atomic() -> None:
    malformed = "Mission title; pilotage du portefeuille; préparation des statuts"
    assert not PresentationCopyService._is_atomic_bullet(malformed)
    assert PresentationCopyService._is_atomic_bullet("Pilotage, reporting et suivi des risques")


def test_detailed_prompt_contains_only_the_current_reference() -> None:
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    service = ReferenceNarrativeService(repository, DisabledNarrativeProvider())
    source, plans, _capsules, _section = service._review_context([REFERENCE_A, REFERENCE_B])
    request = DirectPresentationRequest(
        selected_reference_ids=[REFERENCE_A, REFERENCE_B],
        opportunity_context="UNTRUSTED OPPORTUNITY MARKER",
        template_id="detailed_reference",
    )
    plan = build_detailed_presentation_support_plan(
        source.bundles[0], source.support_index, plans[0]
    )
    package = build_detailed_prompt(
        request,
        source.bundles[0],
        plan,
        source.support_index,
        repair=False,
    )
    payload = json.loads(package.messages[1]["content"])
    serialized = json.dumps(payload, ensure_ascii=False)
    assert payload["current_commercial_opportunity"] == {
        "context_for_relevance_and_phrasing_only": "UNTRUSTED OPPORTUNITY MARKER",
        "factual_use": "FORBIDDEN — this is not evidence about the reference",
    }
    assert "PNUD" in serialized
    assert "SUNU Assurance" not in serialized


def test_bct_challenges_and_qualitative_benefits_are_synthesized_without_literal_fields() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    bundle = source.bundles[0]
    plan = build_detailed_presentation_support_plan(bundle, source.support_index, plans[0])
    request = DirectPresentationRequest(
        selected_reference_ids=[reference_id],
        target_language="fr",
        template_id="detailed_reference",
    )
    candidate = DetailedReferenceCopy(
        mission_title="Opérationnalisation du PCA de la BCT",
        challenges=[
            "Besoin de structurer les procédures de continuité métier et de secours informatique.",
            "Nécessité de préparer un dispositif PCA testable et maintenable dans le temps.",
        ],
        realisations=[
            DetailedRealisationCopy(text="Conduite d’ateliers sur les procédures métiers.", subitems=[]),
            DetailedRealisationCopy(text="Formalisation des procédures PSI.", subitems=[]),
            DetailedRealisationCopy(text="Élaboration du plan global de test PCA.", subitems=[]),
        ],
        benefits=[
            "Renforcement de la résilience opérationnelle de la banque.",
            "Amélioration de la préparation des équipes aux interruptions majeures.",
            "Mise à disposition d’un dispositif PCA structuré et testable.",
        ],
    )
    copy_service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)

    safe = copy_service._safe_supported_portions(
        request, source, bundle, plan, candidate
    ).detailed_presentation

    assert safe is not None
    assert len(safe.challenges) == 2
    assert len(safe.realisations) == 3
    assert len(safe.benefits) == 3
    assert "challenge" not in bundle.unavailable_fields
    assert "benefits" not in bundle.unavailable_fields


def test_whole_reference_language_detection_and_one_reference_rewrite() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    english = DetailedReferenceCopy(
        mission_title="Operationalizing the BCT business continuity plan",
        challenges=["The bank needs a structured continuity and recovery framework for its teams."],
        realisations=[
            DetailedRealisationCopy(text="The team prepared the PCA procedures and testing plan.", subitems=[]),
            DetailedRealisationCopy(text="The team organized workshops for the business units.", subitems=[]),
            DetailedRealisationCopy(text="The team documented the MCO and PSI activities.", subitems=[]),
        ],
        benefits=["The work provides a clearer and more testable continuity framework."],
    )
    french = DetailedReferenceCopy(
        mission_title="Opérationnalisation du PCA de la BCT Phase 1 : Mise en place du PCA",
        challenges=["Besoin de structurer les procédures de continuité pour les équipes de la banque."],
        realisations=[
            DetailedRealisationCopy(text="Préparation des procédures du PCA et du plan de test.", subitems=[]),
            DetailedRealisationCopy(text="Organisation des ateliers avec les unités métiers.", subitems=[]),
            DetailedRealisationCopy(text="Formalisation des activités MCO et PSI.", subitems=[]),
        ],
        benefits=["Renforcement de la préparation des équipes et de la continuité métier."],
    )
    provider = _SequentialProvider([english, french])
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    plan = build_detailed_presentation_support_plan(
        source.bundles[0], source.support_index, plans[0]
    )
    request = DirectPresentationRequest(
        selected_reference_ids=[reference_id],
        target_language="fr",
        template_id="detailed_reference",
    )
    service = _LanguageRepairService(narrative_service, provider, PROJECT_ROOT)

    repaired, record = service._generate_one(request, source, source.bundles[0], plan)

    assert len(provider.calls) == 2
    assert record["attempts"] == 2
    assert assess_reference_language(repaired, "fr").status == "PASS"
    assert repaired.detailed_presentation.mission_title.text == french.mission_title
    repair_payload = json.loads(provider.calls[1][1]["content"])
    assert repair_payload["repair_only_these_fields"] == [
        "mission_title", "challenges", "realisations", "benefits"
    ]
    assert "entirely in the requested language" in repair_payload["repair_instruction"]


def test_mixed_full_reference_is_a_clear_mismatch() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    plan = build_detailed_presentation_support_plan(
        source.bundles[0], source.support_index, plans[0]
    )
    service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    mixed = service._reference_from_copy(
        DetailedReferenceCopy(
            mission_title="Mise en place du PCA de la banque",
            challenges=["Besoin de structurer la continuité pour les équipes."],
            realisations=[
                DetailedRealisationCopy(
                    text="The team prepared the recovery plan and organized workshops with the business units.",
                    subitems=[],
                )
            ],
            benefits=["Renforcement de la préparation opérationnelle."],
        ),
        plan,
        "detailed_reference",
    )

    assert assess_reference_language(mixed, "fr").status == "CLEAR_MISMATCH"


def test_derived_benefit_classifier_is_multilingual_and_rejects_measured_claims() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, _plans, _capsules, _section = narrative_service._review_context([reference_id])
    bundle = source.bundles[0]

    assert PresentationCopyService._is_conservative_derived_benefit(
        "Strengthening PCA operational resilience.", bundle, "en"
    )
    assert PresentationCopyService._is_conservative_derived_benefit(
        "تعزيز مرونة نظام PCA التشغيلي.", bundle, "ar"
    )
    assert not PresentationCopyService._is_conservative_derived_benefit(
        "Amélioration de la visibilité sur le PCA avec 35 % de réduction.", bundle, "fr"
    )


def test_missing_trusted_acronyms_are_recovered_from_exact_activity_clauses() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    bundle = source.bundles[0]
    plan = build_detailed_presentation_support_plan(bundle, source.support_index, plans[0])
    request = DirectPresentationRequest(
        selected_reference_ids=[reference_id],
        target_language="fr",
        template_id="detailed_reference",
    )
    copy_service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    without_acronyms = DetailedReferenceCopy(
        mission_title="Opérationnalisation du PCA de la BCT",
        realisations=[
            DetailedRealisationCopy(text=f"Activité de continuité numéro {index}", subitems=[])
            for index in range(1, 7)
        ],
    )
    narrative = copy_service._reference_from_copy(without_acronyms, plan, "detailed_reference")

    recovered = copy_service._recover_required_source_acronyms(
        request, source, bundle, plan, narrative
    )
    generated = " ".join(
        value
        for item in recovered.detailed_presentation.realisations
        for value in [item.text.text, *[subitem.text for subitem in item.subitems]]
    )

    assert "PSI" in generated
    assert "MCO" in generated
    assert ";" not in generated


def test_missing_qualitative_benefit_does_not_abort_trusted_fallback() -> None:
    """A sparse source must still produce an editable detailed reference."""
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(
        TrustedV2Repository(PROJECT_ROOT, load_config()), provider
    )
    service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    result = service.generate(
        DirectPresentationRequest(
            selected_reference_ids=[reference_id],
            target_language="fr",
            template_id="detailed_reference",
        )
    )

    assert result.review.validation.export_eligible
    assert result.generation_records[0]["quality_gate"]["status"] == (
        "PARTIAL_TRUSTED_FALLBACK"
    )
    assert result.review.narrative.references[0].detailed_presentation is not None


def test_multiple_sparse_references_complete_as_one_presentation() -> None:
    """One weak reference must not abort the rest of a selected set."""
    reference_ids = [
        "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82",
        "54b110427999b6eebe2f45331c0f98f70c2f5085e0d81e6fac012c72d3ca4278",
        "14487247262c61e6abc0ec22c292f435c00759df934fa36376214bbc79130ddd",
        "647624c5a1758d25a07147463c4f652d15470db496512123252d16f1d30ae3a7",
    ]
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(
        TrustedV2Repository(PROJECT_ROOT, load_config()), provider
    )
    service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    result = service.generate(
        DirectPresentationRequest(
            selected_reference_ids=reference_ids,
            target_language="fr",
            template_id="detailed_reference",
        )
    )

    assert result.review.validation.export_eligible
    assert [item.reference_id for item in result.review.narrative.references] == reference_ids
    assert len(result.generation_records) == len(reference_ids)


def test_semantic_deduplication_preserves_acronyms_from_merged_items() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    plan = build_detailed_presentation_support_plan(
        source.bundles[0], source.support_index, plans[0]
    )
    copy_service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    copy = DetailedReferenceCopy(
        mission_title="Opérationnalisation du PCA",
        realisations=[
            DetailedRealisationCopy(
                text="Rédaction du plan de sécurité des personnes et des biens.", subitems=[]
            ),
            DetailedRealisationCopy(
                text="Rédaction et structuration du plan de sécurité des personnes et des biens PSI.",
                subitems=[],
            ),
        ],
    )
    narrative = copy_service._reference_from_copy(copy, plan, "detailed_reference")

    deduplicated = copy_service._deduplicate_detailed_reference(narrative, plan)
    generated = " ".join(
        item.text.text for item in deduplicated.detailed_presentation.realisations
    )

    assert "PSI" in generated


def test_post_dedup_recovery_restores_distinct_source_activities() -> None:
    reference_id = "38f6543c913e6155ed935bc93b2eb9adb740b8d292f9afd40065032ca7b62b82"
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    provider = DisabledNarrativeProvider()
    narrative_service = ReferenceNarrativeService(repository, provider)
    source, plans, _capsules, _section = narrative_service._review_context([reference_id])
    bundle = source.bundles[0]
    plan = build_detailed_presentation_support_plan(bundle, source.support_index, plans[0])
    request = DirectPresentationRequest(
        selected_reference_ids=[reference_id],
        target_language="fr",
        template_id="detailed_reference",
    )
    copy_service = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)
    copy = DetailedReferenceCopy(
        mission_title="Opérationnalisation du PCA de la BCT",
        realisations=[
            DetailedRealisationCopy(
                text="Rédaction du plan de communication de crise et du plan de sécurité des personnes et des biens (Phase 2 : Test).",
                subitems=[],
            ),
            DetailedRealisationCopy(
                text="Définition et rédaction des procédures de Sécurité des Personnes et des Biens (PSI) ainsi que du plan de communication de crise.",
                subitems=[],
            ),
            DetailedRealisationCopy(
                text="Élaboration du plan de test PCA et du Plan MCO.",
                subitems=[],
            ),
        ],
    )
    narrative = copy_service._reference_from_copy(copy, plan, "detailed_reference")

    recovered, _records = copy_service._fit_and_repair_one(
        request, source, bundle, plan, narrative, 0
    )
    activities = [
        value
        for item in recovered.detailed_presentation.realisations
        for value in [item.text.text, *[subitem.text for subitem in item.subitems]]
    ]

    assert len(activities) >= 3
    assert any("ateliers" in value.casefold() for value in activities)
    assert sum("sécurité des personnes" in value.casefold() for value in activities) == 1


def test_production_generator_has_no_named_client_or_reference_branches() -> None:
    production = (Path(__file__).parents[1] / "reference_narrative").glob("*.py")
    text = "\n".join(path.read_text(encoding="utf-8") for path in production).casefold()
    for forbidden in ("albaraka", "\bstb\b", "\bbts\b"):
        assert re.search(forbidden, text) is None
    for forbidden in (r"if\s+client\s*==\s*['\"]", r"if\s+reference_id\s*==\s*['\"]"):
        assert re.search(forbidden, text) is None


def test_generated_copy_is_word_safely_fitted_before_schema_validation() -> None:
    long_subitem = "Mise en place du dispositif de continuite et de gouvernance " * 5
    copy = DetailedRealisationCopy(
        text="Pilotage du programme de continuite",
        subitems=[long_subitem],
    )

    assert len(copy.subitems[0]) <= 180
    assert not copy.subitems[0].endswith(" ")
    assert copy.subitems[0] in long_subitem
