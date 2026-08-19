from __future__ import annotations

import json

from app.api.settings import PROJECT_ROOT, load_config
from reference_narrative.presentation_copy import PresentationCopyService
from reference_narrative.presentation_schemas import DirectPresentationRequest
from reference_narrative.service import ReferenceNarrativeService
from reference_pack.validation import TrustedV2Repository

from test_reference_narrative import FakeProvider


GENERIC_REFERENCE_ID = "6f1f43d3bfa0132fe5d5a08c4a17868e0521f514a0336d065a227518e2a3e6dd"


def test_detailed_challenge_fit_measurement_is_section_local() -> None:
    repository = TrustedV2Repository(PROJECT_ROOT, load_config())
    overflowing_challenge = [
        "Analyser les différents scénarios d’évolution identifiés pour tous les domaines spécifiés dans la portée de la mission, ainsi que pour tout autre domaine pertinent " * 2,
        "Proposer une architecture du Système d’Information de l’Agence : architecture fonctionnelle et architecture applicative couvrant le front office " * 2,
        "Détailler les actions à entreprendre à court, moyen et à long termes et analyser les risques et les avantages y afférents pour tous les domaines spécifiés " * 2,
    ]
    provider = FakeProvider([])
    narrative_service = ReferenceNarrativeService(repository, provider)
    request = DirectPresentationRequest(
        selected_reference_ids=[GENERIC_REFERENCE_ID],
        target_language="fr",
        template_id="detailed_reference",
        output_format="both",
    )
    copy = PresentationCopyService(narrative_service, provider, PROJECT_ROOT)

    overflowing = copy._measure_field(request, "challenge", overflowing_challenge, 0)
    compact = copy._measure_field(request, "challenge", ["Analyse de l’existant"], 0)

    assert not overflowing.fits
    assert compact.fits
    assert overflowing.required_lines > compact.required_lines
    assert provider.calls == []
