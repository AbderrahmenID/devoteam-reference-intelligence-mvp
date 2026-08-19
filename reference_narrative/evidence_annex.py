from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from reference_pack.evidence_renderer import EvidenceRenderer, EvidenceVisual
from reference_pack.schemas import TrustedEvidence, TrustedReference

from .content_sanitizer import sanitize_generation_text, sanitize_source_label
from .schemas import NarrativeReviewResponse, SourceSupportRecord


@dataclass(frozen=True)
class NarrativeEvidenceSelection:
    reference: TrustedReference
    evidence: TrustedEvidence
    visual: EvidenceVisual
    selection_reason: str


def _narrative_support_ids(review: NarrativeReviewResponse, reference_index: int) -> list[str]:
    """Return narrative evidence supports in a stable, delivery-first order."""
    reference = review.narrative.references[reference_index]
    values = [
        *reference.realisations,
        reference.devoteam_contribution,
        *reference.benefits,
        reference.short_description,
        reference.headline,
        reference.challenge,
        reference.why_relevant_to_opportunity,
    ]
    return list(dict.fromkeys(support_id for value in values for support_id in value.support_ids))


def _matching_evidence(
    reference: TrustedReference,
    support: SourceSupportRecord,
) -> TrustedEvidence | None:
    if support.reference_id != reference.reference_id or support.page is None:
        return None
    source_label = sanitize_source_label(support.source_label)
    support_text = sanitize_generation_text(support.text, maximum_characters=4000)
    for evidence in reference.evidence:
        if evidence.source_page != support.page:
            continue
        if sanitize_source_label(evidence.source_file_name) != source_label:
            continue
        evidence_text = sanitize_generation_text(evidence.display_text, maximum_characters=4000)
        if evidence_text == support_text:
            return evidence
    return None


def choose_evidence(
    references: list[TrustedReference],
    review: NarrativeReviewResponse,
    support_index: dict[str, SourceSupportRecord],
) -> list[tuple[TrustedReference, TrustedEvidence, str]]:
    """Choose one display-approved page per reference without retrieval or model calls."""
    if [item.reference_id for item in references] != [item.reference_id for item in review.narrative.references]:
        raise ValueError("Trusted evidence order does not match the reviewed narrative")

    selected: list[tuple[TrustedReference, TrustedEvidence, str]] = []
    for index, reference in enumerate(references):
        evidence: TrustedEvidence | None = None
        reason = "highest_priority_display_evidence"
        for support_id in _narrative_support_ids(review, index):
            support = support_index.get(support_id)
            if support is None:
                continue
            evidence = _matching_evidence(reference, support)
            if evidence is not None:
                reason = "approved_narrative_support"
                break
        if evidence is None and reference.evidence:
            evidence = reference.evidence[0]
        if evidence is not None:
            selected.append((reference, evidence, reason))
    return selected


def render_evidence(
    renderer: EvidenceRenderer,
    selections: Iterable[tuple[TrustedReference, TrustedEvidence, str]],
    output_dir: Path,
) -> list[NarrativeEvidenceSelection]:
    rendered: list[NarrativeEvidenceSelection] = []
    for index, (reference, evidence, reason) in enumerate(selections, start=1):
        visual = renderer.render_required(
            reference.reference_id,
            evidence,
            output_dir / f"evidence-{index:03d}-page-{evidence.source_page}.png",
        )
        rendered.append(NarrativeEvidenceSelection(reference, evidence, visual, reason))
    return rendered
