from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reference_pack.schemas import TrustedEvidence, TrustedReference
from reference_pack.validation import TrustedV2Repository

from .content_sanitizer import sanitize_generation_text, sanitize_source_label
from .schemas import (
    ReferenceFacts,
    ReferenceSourceBundle,
    SourceSupportRecord,
    SourceType,
    SupportedFact,
)


FACT_FIELDS = (
    "reference_number",
    "mission_title",
    "client",
    "country",
    "period",
    "sector",
    "offering",
    "business_unit",
)


@dataclass(frozen=True)
class SourceBundleBuildResult:
    references: list[TrustedReference]
    bundles: list[ReferenceSourceBundle]
    support_index: dict[str, SourceSupportRecord]
    known_fact_values: dict[str, set[str]]


class _SupportIdAllocator:
    def __init__(self) -> None:
        self.value = 0

    def next(self) -> str:
        self.value += 1
        return f"S{self.value}"


def _document_source_types(document_type: str) -> list[SourceType]:
    normalized = document_type.casefold().replace("-", "_").replace(" ", "_")
    types: list[SourceType] = []
    if "attestation" in normalized or "completion" in normalized or "certificate" in normalized:
        types.extend((SourceType.CLIENT_ATTESTATION, SourceType.COMPLETED_WORK_EVIDENCE))
    elif "contract" in normalized or "contrat" in normalized:
        types.append(SourceType.CONTRACTUAL_SCOPE)
    elif any(marker in normalized for marker in ("proposal", "technical_offer", "offre_technique", "tender")):
        types.append(SourceType.PROPOSAL_SCOPE)
    else:
        types.append(SourceType.UNVERIFIED_METADATA)
    return list(dict.fromkeys(types))


class ReferenceSourceBundleBuilder:
    """Build the only reference payload permitted to cross the LLM boundary."""

    def __init__(self, repository: TrustedV2Repository):
        self.repository = repository
        self._document_types = {
            str(row["chunk_id"]): str(row.get("document_type") or "")
            for _, row in repository.chunks.iterrows()
        }

    def _fact_record(
        self,
        allocator: _SupportIdAllocator,
        reference_id: str,
        field: str,
        value: str,
    ) -> tuple[SupportedFact, SourceSupportRecord]:
        support_id = allocator.next()
        cleaned = sanitize_generation_text(value, maximum_characters=2000)
        fact = SupportedFact(field=field, value=cleaned, support_id=support_id)
        record = SourceSupportRecord(
            support_id=support_id,
            reference_id=reference_id,
            support_types=[SourceType.FACT, SourceType.STRUCTURED_METADATA],
            text=f"{field}: {cleaned}",
            source_label=f"Trusted reference fact: {field}",
        )
        return fact, record

    def _evidence_record(
        self,
        allocator: _SupportIdAllocator,
        reference_id: str,
        evidence: TrustedEvidence,
    ) -> SourceSupportRecord:
        document_type = self._document_types.get(evidence.chunk_id, "")
        return SourceSupportRecord(
            support_id=allocator.next(),
            reference_id=reference_id,
            support_types=_document_source_types(document_type),
            text=sanitize_generation_text(evidence.display_text, maximum_characters=4000),
            source_label=sanitize_source_label(evidence.source_file_name) or "Approved source",
            page=evidence.source_page,
        )

    @staticmethod
    def _unavailable_fields(records: list[SourceSupportRecord]) -> list[str]:
        unavailable: list[str] = []
        # Challenges and qualitative benefits are presentation synthesis
        # fields, not source columns. Missing literal labels must not prevent
        # the writer from deriving them from trusted context and project work.
        if not any(SourceType.COMPLETED_WORK_EVIDENCE in record.support_types for record in records):
            unavailable.append("completed_work_details")
        return unavailable

    def build(self, selected_reference_ids: list[str]) -> SourceBundleBuildResult:
        references = self.repository.load_selected(selected_reference_ids)
        allocator = _SupportIdAllocator()
        support_index: dict[str, SourceSupportRecord] = {}
        bundles: list[ReferenceSourceBundle] = []

        for reference in references:
            fact_values: dict[str, Any] = {"reference_id": reference.reference_id}
            structured_records: list[SourceSupportRecord] = []
            for field in FACT_FIELDS:
                raw = getattr(reference, field)
                if raw is None or not str(raw).strip():
                    fact_values[field] = None
                    continue
                fact, record = self._fact_record(
                    allocator,
                    reference.reference_id,
                    field,
                    str(raw),
                )
                fact_values[field] = fact
                structured_records.append(record)
                support_index[record.support_id] = record

            technology_facts: list[SupportedFact] = []
            for technology in reference.technologies:
                fact, record = self._fact_record(
                    allocator,
                    reference.reference_id,
                    "technology",
                    technology,
                )
                record.support_types = [SourceType.STRUCTURED_METADATA, SourceType.UNVERIFIED_METADATA]
                technology_facts.append(fact)
                structured_records.append(record)
                support_index[record.support_id] = record
            fact_values["technologies"] = technology_facts

            if reference.description:
                metadata_record = SourceSupportRecord(
                    support_id=allocator.next(),
                    reference_id=reference.reference_id,
                    support_types=[SourceType.STRUCTURED_METADATA, SourceType.UNVERIFIED_METADATA],
                    text=sanitize_generation_text(reference.description, maximum_characters=6000),
                    source_label="Structured catalog scope",
                )
                structured_records.append(metadata_record)
                support_index[metadata_record.support_id] = metadata_record

            display_records: list[SourceSupportRecord] = []
            completed_records: list[SourceSupportRecord] = []
            proposal_records: list[SourceSupportRecord] = []
            for evidence in reference.evidence:
                record = self._evidence_record(allocator, reference.reference_id, evidence)
                display_records.append(record)
                support_index[record.support_id] = record
                if SourceType.COMPLETED_WORK_EVIDENCE in record.support_types:
                    completed_records.append(record)
                if any(
                    source_type in record.support_types
                    for source_type in (SourceType.PROPOSAL_SCOPE, SourceType.CONTRACTUAL_SCOPE)
                ):
                    proposal_records.append(record)

            all_records = [*structured_records, *display_records]
            bundles.append(
                ReferenceSourceBundle(
                    reference_id=reference.reference_id,
                    facts=ReferenceFacts(**fact_values),
                    completed_work_evidence=completed_records,
                    structured_metadata_scope=structured_records,
                    proposal_scope=proposal_records,
                    display_evidence=display_records,
                    unavailable_fields=self._unavailable_fields(all_records),
                )
            )

        known_fact_values: dict[str, set[str]] = {}
        for field in ("client", "country", "sector", "offering", "project_year"):
            if field in self.repository.references.columns:
                known_fact_values[field] = {
                    sanitize_generation_text(str(value), maximum_characters=500)
                    for value in self.repository.references[field].dropna().tolist()
                    if sanitize_generation_text(str(value), maximum_characters=500)
                }
        return SourceBundleBuildResult(references, bundles, support_index, known_fact_values)
