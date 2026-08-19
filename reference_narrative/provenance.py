from __future__ import annotations

from datetime import datetime, timezone

from .schemas import (
    NarrativeGenerationProvenance,
    NarrativeValidationResult,
    SourceSupportRecord,
    SourceSupportSummary,
)


def source_support_summaries(
    support_index: dict[str, SourceSupportRecord],
) -> list[SourceSupportSummary]:
    def sequence(record: SourceSupportRecord) -> int:
        try:
            return int(record.support_id.removeprefix("S"))
        except ValueError:
            return 10**9

    return [
        SourceSupportSummary(
            support_id=record.support_id,
            reference_id=record.reference_id,
            support_types=list(record.support_types),
            source_label=record.source_label,
            page=record.page,
        )
        for record in sorted(support_index.values(), key=sequence)
    ]


def build_generation_provenance(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    prompt_sha256: str,
    selected_reference_ids: list[str],
    support_index: dict[str, SourceSupportRecord],
    retry_count: int,
    validation: NarrativeValidationResult,
) -> NarrativeGenerationProvenance:
    return NarrativeGenerationProvenance(
        generated_at_utc=datetime.now(timezone.utc),
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        selected_reference_ids=list(selected_reference_ids),
        source_supports=source_support_summaries(support_index),
        structured_output_retry_count=retry_count,
        validation_warning_codes=[warning.code for warning in validation.warnings],
    )
