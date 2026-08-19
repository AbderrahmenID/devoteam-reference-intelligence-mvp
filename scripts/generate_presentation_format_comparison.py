from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.api.settings import PROJECT_ROOT, load_config
from reference_narrative.presentation_schemas import NarrativePresentationRequest
from reference_narrative.presentation_service import NarrativePresentationService
from reference_narrative.schemas import (
    EditableReferenceSectionNarrative,
    NarrativeGenerationRequest,
    ReferenceNarrativeDraft,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _request(reviewed: dict, template_id: str) -> NarrativePresentationRequest:
    narrative = reviewed["narrative"]
    return NarrativePresentationRequest(
        generation_request=NarrativeGenerationRequest.model_validate(reviewed["generation_context"]),
        narrative=EditableReferenceSectionNarrative(
            section_intro=narrative["section_intro"],
            overall_storyline=narrative["overall_storyline"],
            why_these_references=narrative["why_these_references"],
            references=[
                ReferenceNarrativeDraft.model_validate(
                    {key: value for key, value in item.items() if key != "reference_id"}
                )
                for item in narrative["references"]
            ],
        ),
        template_id=template_id,
        approved=True,
        approved_narrative_status="READY_FOR_PRESENTATION",
        approved_reference_ids=reviewed["selected_reference_ids"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reviewed_content", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "audit/reference_narrative_phase6/development",
    )
    args = parser.parse_args()

    reviewed_path = args.reviewed_content.resolve()
    output_root = args.output_root.resolve()
    if PROJECT_ROOT != output_root and PROJECT_ROOT not in output_root.parents:
        raise ValueError("Comparison output must remain inside the project")
    output_root.mkdir(parents=True, exist_ok=True)

    reviewed = _read_json(reviewed_path)
    service = NarrativePresentationService(PROJECT_ROOT, load_config())
    service.output_root = output_root
    responses = {}
    manifests = {}
    for template_id in ("orange_bank_compact", "detailed_reference"):
        response = service.generate(_request(reviewed, template_id))
        responses[template_id] = response.model_dump(mode="json")
        manifests[template_id] = _read_json(
            output_root / response.generation_id / "generation_manifest.json"
        )

    compact = manifests["orange_bank_compact"]
    detailed = manifests["detailed_reference"]
    checks = {
        "reviewed_content_hash_equal": compact["reviewed_content_sha256"]
        == detailed["reviewed_content_sha256"],
        "selected_reference_ids_equal": compact["selected_reference_ids"]
        == detailed["selected_reference_ids"],
        "detailed_has_no_evidence_annex": detailed["evidence_pages"] == [],
        "exact_supported_formats": sorted(manifests)
        == ["detailed_reference", "orange_bank_compact"],
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "source_reviewed_content": str(reviewed_path.relative_to(PROJECT_ROOT)),
        "responses": responses,
        "checks": checks,
    }
    (output_root / "format_comparison.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
