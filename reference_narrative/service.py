from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from reference_pack.validation import TrustedV2Repository

from .claim_validator import ClaimValidator
from .field_policy import build_field_support_plan, build_reference_capsule, build_section_support_plan
from .ollama_client import (
    NarrativeModelUnavailableError,
    NarrativeProvider,
    NarrativeProviderDisabledError,
    NarrativeProviderError,
    NarrativeProviderResponseError,
    NarrativeProviderTimeoutError,
    NarrativeProviderUnavailableError,
)
from .prompt_builder import PromptPackage, build_reference_prompt, build_section_prompt
from .provenance import build_generation_provenance, source_support_summaries
from .schemas import (
    FieldSupportPlan,
    NarrativeGenerationRequest,
    NarrativeGenerationResponse,
    NarrativeEditValidationRequest,
    NarrativeReferenceMetadata,
    NarrativeRegenerationRequest,
    NarrativeReviewResponse,
    NarrativeSupportPlan,
    ReferenceNarrative,
    ReferenceNarrativeDraft,
    ReferenceSectionNarrative,
    SectionNarrativeDraft,
    SupportedNarrativeText,
)
from .source_bundle import ReferenceSourceBundleBuilder


class NarrativeStructuredOutputError(RuntimeError):
    pass


DraftT = TypeVar("DraftT", bound=BaseModel)
LOGGER = logging.getLogger("uvicorn.error")
ProgressCallback = Callable[[dict[str, object]], None]
ISOLATABLE_GENERATION_ERRORS = (NarrativeProviderError, NarrativeStructuredOutputError)


class ReferenceNarrativeService:
    def __init__(self, repository: TrustedV2Repository, provider: NarrativeProvider):
        self.repository = repository
        self.provider = provider
        self.source_builder = ReferenceSourceBundleBuilder(repository)

    def _generate_and_parse(
        self,
        model_type: type[DraftT],
        prompt_builder: Callable[[bool], PromptPackage],
        timings: dict[str, float] | None = None,
    ) -> tuple[DraftT, PromptPackage, int]:
        prompt_started = time.perf_counter()
        prompt = prompt_builder(False)
        if timings is not None:
            timings["prompt"] += time.perf_counter() - prompt_started
            timings["prompt_chars"] += sum(len(message["content"]) for message in prompt.messages)
        ollama_started = time.perf_counter()
        try:
            raw = self.provider.generate(prompt.messages, prompt.response_schema)
        finally:
            if timings is not None:
                timings["ollama"] += time.perf_counter() - ollama_started
        parsing_started = time.perf_counter()
        first_parse_recorded = False
        try:
            return model_type.model_validate_json(raw), prompt, 0
        except ValidationError:
            if timings is not None:
                timings["parsing"] += time.perf_counter() - parsing_started
            first_parse_recorded = True
            repair_prompt_started = time.perf_counter()
            repair_prompt = prompt_builder(True)
            if timings is not None:
                timings["prompt"] += time.perf_counter() - repair_prompt_started
                timings["prompt_chars"] += sum(len(message["content"]) for message in repair_prompt.messages)
            repair_ollama_started = time.perf_counter()
            try:
                repaired = self.provider.generate(repair_prompt.messages, repair_prompt.response_schema)
            finally:
                if timings is not None:
                    timings["ollama"] += time.perf_counter() - repair_ollama_started
            repair_parsing_started = time.perf_counter()
            try:
                return model_type.model_validate_json(repaired), repair_prompt, 1
            except ValidationError as exc:
                raise NarrativeStructuredOutputError(
                    "The local model returned malformed prose-only structured JSON twice"
                ) from exc
            finally:
                if timings is not None:
                    timings["parsing"] += time.perf_counter() - repair_parsing_started
        finally:
            if timings is not None and not first_parse_recorded:
                timings["parsing"] += time.perf_counter() - parsing_started

    @staticmethod
    def _supported_text(text: str, support_ids: list[str]) -> SupportedNarrativeText:
        cleaned = text.strip()
        return SupportedNarrativeText(text=cleaned, support_ids=list(support_ids) if cleaned else [])

    def _reference_envelope(self, draft: ReferenceNarrativeDraft, plan: FieldSupportPlan) -> ReferenceNarrative:
        return ReferenceNarrative(
            reference_id=plan.reference_id,
            headline=self._supported_text(draft.headline, plan.headline),
            short_description=self._supported_text(draft.short_description, plan.short_description),
            challenge=self._supported_text(draft.challenge, plan.challenge),
            devoteam_contribution=self._supported_text(draft.devoteam_contribution, plan.devoteam_contribution),
            realisations=[self._supported_text(text, plan.realisations) for text in draft.realisations if text.strip()],
            benefits=[self._supported_text(text, plan.benefits) for text in draft.benefits if text.strip()],
            why_relevant_to_opportunity=self._supported_text(
                draft.why_relevant_to_opportunity,
                plan.why_relevant_to_opportunity,
            ),
            warnings=[],
        )

    def _review_context(self, selected_reference_ids: list[str]):
        source_result = self.source_builder.build(selected_reference_ids)
        field_plans = [
            build_field_support_plan(bundle, source_result.support_index)
            for bundle in source_result.bundles
        ]
        capsules = [
            build_reference_capsule(bundle, source_result.support_index)
            for bundle in source_result.bundles
        ]
        section_plan = build_section_support_plan(capsules)
        return source_result, field_plans, capsules, section_plan

    def _canonical_edit(self, request: NarrativeEditValidationRequest):
        source_result, field_plans, capsules, section_plan = self._review_context(
            request.generation_request.selected_reference_ids
        )
        if len(request.narrative.references) != len(field_plans):
            raise ValueError("Edited narrative must contain exactly one prose block per selected reference")
        narrative = ReferenceSectionNarrative(
            section_intro=self._supported_text(
                request.narrative.section_intro,
                section_plan.section_intro,
            ),
            overall_storyline=self._supported_text(
                request.narrative.overall_storyline,
                section_plan.overall_storyline,
            ),
            why_these_references=self._supported_text(
                request.narrative.why_these_references,
                section_plan.why_these_references,
            ),
            references=[
                self._reference_envelope(draft, plan)
                for draft, plan in zip(request.narrative.references, field_plans, strict=True)
            ],
        )
        return source_result, field_plans, capsules, section_plan, narrative

    @staticmethod
    def _metadata(source_result) -> list[NarrativeReferenceMetadata]:
        values: list[NarrativeReferenceMetadata] = []
        for bundle in source_result.bundles:
            def fact(name: str) -> str:
                item = getattr(bundle.facts, name)
                return item.value if item else ""

            values.append(
                NarrativeReferenceMetadata(
                    reference_id=bundle.reference_id,
                    mission_title=fact("mission_title"),
                    client=fact("client"),
                    country=fact("country"),
                    sector=fact("sector"),
                    period=fact("period"),
                    offering=fact("offering"),
                )
            )
        return values

    def _review_response(
        self,
        source_result,
        field_plans: list[FieldSupportPlan],
        section_plan,
        narrative: ReferenceSectionNarrative,
        *,
        allow_catalog_completion_detail: bool = False,
    ) -> NarrativeReviewResponse:
        support_plan = NarrativeSupportPlan(references=field_plans, section=section_plan)
        validation = ClaimValidator(
            source_result.bundles,
            source_result.support_index,
            source_result.known_fact_values,
            support_plan=support_plan,
            allow_catalog_completion_detail=allow_catalog_completion_detail,
        ).validate(narrative, [bundle.reference_id for bundle in source_result.bundles])
        return NarrativeReviewResponse(
            narrative=narrative,
            validation=validation,
            warnings=list(validation.warnings),
            support_plan=support_plan,
            reference_metadata=self._metadata(source_result),
        )

    def validate_edit(self, request: NarrativeEditValidationRequest) -> NarrativeReviewResponse:
        source_result, field_plans, _capsules, section_plan, narrative = self._canonical_edit(request)
        return self._review_response(source_result, field_plans, section_plan, narrative)

    def regenerate(self, request: NarrativeRegenerationRequest) -> NarrativeReviewResponse:
        source_result, field_plans, capsules, section_plan, narrative = self._canonical_edit(request)
        if request.scope == "section_intro":
            regenerated, _prompt, _retries = self._generate_and_parse(
                SectionNarrativeDraft,
                lambda repair: build_section_prompt(
                    request.generation_request,
                    capsules,
                    repair_attempt=repair,
                ),
            )
            narrative.section_intro = self._supported_text(
                regenerated.section_intro,
                section_plan.section_intro,
            )
        else:
            selected_ids = request.generation_request.selected_reference_ids
            if request.reference_id not in selected_ids:
                raise ValueError("reference_id must belong to the selected reference set")
            index = selected_ids.index(request.reference_id)
            bundle = source_result.bundles[index]
            plan = field_plans[index]
            regenerated, _prompt, _retries = self._generate_and_parse(
                ReferenceNarrativeDraft,
                lambda repair: build_reference_prompt(
                    request.generation_request,
                    bundle,
                    plan,
                    source_result.support_index,
                    repair_attempt=repair,
                ),
            )
            narrative.references[index] = self._reference_envelope(regenerated, plan)
        return self._review_response(source_result, field_plans, section_plan, narrative)

    @staticmethod
    def _empty_reference(plan: FieldSupportPlan) -> ReferenceNarrative:
        return ReferenceNarrative(
            reference_id=plan.reference_id,
            headline=SupportedNarrativeText(text="", support_ids=[]),
            short_description=SupportedNarrativeText(text="", support_ids=[]),
            challenge=SupportedNarrativeText(text="", support_ids=[]),
            devoteam_contribution=SupportedNarrativeText(text="", support_ids=[]),
            realisations=[],
            benefits=[],
            why_relevant_to_opportunity=SupportedNarrativeText(text="", support_ids=[]),
            warnings=[],
        )

    @staticmethod
    def _failure_detail(exc: Exception) -> tuple[str, str]:
        reasons = {
            NarrativeProviderDisabledError: "REFERENCE_NARRATIVE_DISABLED",
            NarrativeModelUnavailableError: "REFERENCE_NARRATIVE_MODEL_UNAVAILABLE",
            NarrativeProviderTimeoutError: "REFERENCE_NARRATIVE_CONNECTION_TIMEOUT",
            NarrativeProviderUnavailableError: "REFERENCE_NARRATIVE_PROVIDER_UNAVAILABLE",
            NarrativeProviderResponseError: "REFERENCE_NARRATIVE_INVALID_RESPONSE",
            NarrativeStructuredOutputError: "REFERENCE_NARRATIVE_INVALID_RESPONSE",
        }
        return reasons.get(type(exc), "REFERENCE_NARRATIVE_UNIT_FAILED"), str(exc)

    def _provider_metrics(self, start_index: int, ollama_seconds: float) -> tuple[int | None, float]:
        stats = getattr(self.provider, "generation_stats", None)
        if not isinstance(stats, list):
            return None, ollama_seconds
        records = stats[start_index:]
        token_values = [item.get("prompt_token_count") for item in records if isinstance(item, dict)]
        prompt_tokens = sum(value for value in token_values if isinstance(value, int)) or None
        duration_values = [item.get("total_duration_ns") for item in records if isinstance(item, dict)]
        duration_ns = sum(value for value in duration_values if isinstance(value, (int, float)))
        return prompt_tokens, duration_ns / 1_000_000_000 if duration_ns else ollama_seconds

    def _log_unit(
        self,
        *,
        unit: str,
        reference_id: str | None,
        status: str,
        unit_timings: dict[str, float],
        stats_start: int,
        retries: int,
    ) -> dict[str, object]:
        prompt_tokens, response_seconds = self._provider_metrics(stats_start, unit_timings["ollama"])
        total_seconds = unit_timings["total"]
        LOGGER.info(
            "reference_narrative_unit: unit=%s reference_id=%s status=%s prompt_chars=%d "
            "prompt_tokens=%s response=%.2fs total=%.2fs retries=%d",
            unit,
            reference_id or "-",
            status,
            int(unit_timings["prompt_chars"]),
            prompt_tokens if prompt_tokens is not None else "unavailable",
            response_seconds,
            total_seconds,
            retries,
        )
        return {
            "prompt_characters": int(unit_timings["prompt_chars"]),
            "prompt_tokens": prompt_tokens,
            "response_seconds": round(response_seconds, 3),
            "total_seconds": round(total_seconds, 3),
            "structured_output_retries": retries,
        }

    @staticmethod
    def _emit(callback: ProgressCallback | None, event: dict[str, object]) -> None:
        if callback is not None:
            callback(event)

    def _generate(
        self,
        request: NarrativeGenerationRequest,
        *,
        on_progress: ProgressCallback | None,
        isolate_failures: bool,
    ) -> dict[str, object]:
        total_started = time.perf_counter()
        timings = {
            "bundle": 0.0,
            "prompt": 0.0,
            "prompt_chars": 0.0,
            "ollama": 0.0,
            "parsing": 0.0,
            "validation": 0.0,
        }
        try:
            self._emit(on_progress, {
                "event": "started",
                "message": "Preparing AI-assisted draft…",
                "total_references": len(request.selected_reference_ids),
            })
            bundle_started = time.perf_counter()
            source_result = self.source_builder.build(request.selected_reference_ids)
            timings["bundle"] = time.perf_counter() - bundle_started
            field_plans = [
                build_field_support_plan(bundle, source_result.support_index) for bundle in source_result.bundles
            ]
            capsules = [
                build_reference_capsule(bundle, source_result.support_index) for bundle in source_result.bundles
            ]
            section_plan = build_section_support_plan(capsules)
            section_draft = SectionNarrativeDraft()
            references = [self._empty_reference(plan) for plan in field_plans]
            prompts: list[PromptPackage] = []
            failures: list[dict[str, object]] = []
            retry_count = 0

            # Unit 1: the section narrative sees safe capsules only and completes
            # before any individual reference generation starts.
            self._emit(on_progress, {"event": "unit_started", "unit": "section", "message": "Preparing section narrative…"})
            unit_started = time.perf_counter()
            unit_timings = {"prompt": 0.0, "prompt_chars": 0.0, "ollama": 0.0, "parsing": 0.0, "total": 0.0}
            stats_start = len(getattr(self.provider, "generation_stats", []))
            try:
                section_draft, section_prompt, section_retries = self._generate_and_parse(
                    SectionNarrativeDraft,
                    lambda repair: build_section_prompt(request, capsules, repair_attempt=repair),
                    unit_timings,
                )
                prompts.append(section_prompt)
                retry_count += section_retries
                unit_timings["total"] = time.perf_counter() - unit_started
                metric = self._log_unit(
                    unit="section", reference_id=None, status="completed", unit_timings=unit_timings,
                    stats_start=stats_start, retries=section_retries,
                )
                self._emit(on_progress, {
                    "event": "unit_completed",
                    "unit": "section",
                    "message": "Section narrative complete",
                    "result": {
                        "section_intro": self._supported_text(section_draft.section_intro, section_plan.section_intro).model_dump(mode="json"),
                        "overall_storyline": self._supported_text(section_draft.overall_storyline, section_plan.overall_storyline).model_dump(mode="json"),
                        "why_these_references": self._supported_text(section_draft.why_these_references, section_plan.why_these_references).model_dump(mode="json"),
                    },
                    "timing": metric,
                })
            except ISOLATABLE_GENERATION_ERRORS as exc:
                unit_timings["total"] = time.perf_counter() - unit_started
                if not isolate_failures:
                    raise
                reason, message = self._failure_detail(exc)
                failure = {"unit": "section", "reference_id": None, "reason": reason, "message": message}
                failures.append(failure)
                metric = self._log_unit(
                    unit="section", reference_id=None, status="failed", unit_timings=unit_timings,
                    stats_start=stats_start, retries=0,
                )
                self._emit(on_progress, {"event": "unit_failed", **failure, "timing": metric})
            finally:
                for key in ("prompt", "prompt_chars", "ollama", "parsing"):
                    timings[key] += unit_timings[key]

            # Units 2-5: exactly one selected reference bundle per call, in order.
            for index, (bundle, plan) in enumerate(zip(source_result.bundles, field_plans, strict=True)):
                message = f"Reference {index + 1} of {len(field_plans)} — {self._metadata(source_result)[index].client or 'Client'}"
                self._emit(on_progress, {
                    "event": "unit_started", "unit": "reference", "reference_id": plan.reference_id,
                    "index": index, "message": message,
                })
                unit_started = time.perf_counter()
                unit_timings = {"prompt": 0.0, "prompt_chars": 0.0, "ollama": 0.0, "parsing": 0.0, "total": 0.0}
                stats_start = len(getattr(self.provider, "generation_stats", []))
                try:
                    draft, prompt, retries = self._generate_and_parse(
                        ReferenceNarrativeDraft,
                        lambda repair, bundle=bundle, plan=plan: build_reference_prompt(
                            request,
                            bundle,
                            plan,
                            source_result.support_index,
                            repair_attempt=repair,
                        ),
                        unit_timings,
                    )
                    references[index] = self._reference_envelope(draft, plan)
                    prompts.append(prompt)
                    retry_count += retries
                    unit_timings["total"] = time.perf_counter() - unit_started
                    metric = self._log_unit(
                        unit="reference", reference_id=plan.reference_id, status="completed",
                        unit_timings=unit_timings, stats_start=stats_start, retries=retries,
                    )
                    self._emit(on_progress, {
                        "event": "unit_completed", "unit": "reference", "reference_id": plan.reference_id,
                        "index": index, "message": f"{message} complete",
                        "result": references[index].model_dump(mode="json"), "timing": metric,
                    })
                except ISOLATABLE_GENERATION_ERRORS as exc:
                    unit_timings["total"] = time.perf_counter() - unit_started
                    if not isolate_failures:
                        raise
                    reason, failure_message = self._failure_detail(exc)
                    failure = {
                        "unit": "reference", "reference_id": plan.reference_id, "index": index,
                        "reason": reason, "message": failure_message,
                    }
                    failures.append(failure)
                    metric = self._log_unit(
                        unit="reference", reference_id=plan.reference_id, status="failed",
                        unit_timings=unit_timings, stats_start=stats_start, retries=0,
                    )
                    self._emit(on_progress, {"event": "unit_failed", **failure, "timing": metric})
                finally:
                    for key in ("prompt", "prompt_chars", "ollama", "parsing"):
                        timings[key] += unit_timings[key]

            narrative = ReferenceSectionNarrative(
                section_intro=self._supported_text(section_draft.section_intro, section_plan.section_intro),
                overall_storyline=self._supported_text(section_draft.overall_storyline, section_plan.overall_storyline),
                why_these_references=self._supported_text(
                    section_draft.why_these_references,
                    section_plan.why_these_references,
                ),
                references=references,
            )
            self._emit(on_progress, {"event": "validation_started", "message": "Final validation…"})
            validation_started = time.perf_counter()
            review = self._review_response(source_result, field_plans, section_plan, narrative)
            timings["validation"] = time.perf_counter() - validation_started

            response: NarrativeGenerationResponse | None = None
            if not failures:
                summaries = source_support_summaries(source_result.support_index)
                aggregate_hash = hashlib.sha256(
                    "".join(prompt.prompt_sha256 for prompt in prompts).encode("ascii")
                ).hexdigest()
                provenance = build_generation_provenance(
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    prompt_version=prompts[0].prompt_version,
                    prompt_sha256=aggregate_hash,
                    selected_reference_ids=request.selected_reference_ids,
                    support_index=source_result.support_index,
                    retry_count=retry_count,
                    validation=review.validation,
                )
                response = NarrativeGenerationResponse(
                    narrative=narrative,
                    validation=review.validation,
                    warnings=list(review.warnings),
                    source_supports=summaries,
                    support_plan=review.support_plan,
                    provenance=provenance,
                )

            total = time.perf_counter() - total_started
            result: dict[str, object] = {
                "response": response,
                "review": review,
                "failures": failures,
                "timings": {
                    "validation_seconds": round(timings["validation"], 3),
                    "total_seconds": round(total, 3),
                },
            }
            self._emit(on_progress, {
                "event": "completed" if not failures else "partial",
                "message": "Draft complete" if not failures else "Draft completed with isolated unit failures",
                "response": response.model_dump(mode="json") if response else None,
                "review": review.model_dump(mode="json"),
                "failures": failures,
                "timings": result["timings"],
            })
            return result
        finally:
            total = time.perf_counter() - total_started
            LOGGER.info(
                "reference_narrative: bundle=%.2fs prompt=%.2fs prompt_chars=%d ollama=%.2fs "
                "parsing=%.2fs validation=%.2fs total=%.2fs",
                timings["bundle"],
                timings["prompt"],
                int(timings["prompt_chars"]),
                timings["ollama"],
                timings["parsing"],
                timings["validation"],
                total,
            )

    def generate(self, request: NarrativeGenerationRequest) -> NarrativeGenerationResponse:
        result = self._generate(request, on_progress=None, isolate_failures=False)
        response = result["response"]
        if not isinstance(response, NarrativeGenerationResponse):
            raise RuntimeError("Narrative generation completed without a canonical response")
        return response

    def generate_progressive(
        self,
        request: NarrativeGenerationRequest,
        on_progress: ProgressCallback,
    ) -> dict[str, object]:
        return self._generate(request, on_progress=on_progress, isolate_failures=True)
