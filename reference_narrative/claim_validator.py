from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from retrieval.metadata import TECHNOLOGY_RULES

from .schemas import (
    NarrativeValidationResult,
    NarrativeSupportPlan,
    ReferenceSectionNarrative,
    ReferenceSourceBundle,
    SourceSupportRecord,
    SourceType,
    SupportedNarrativeText,
    ValidationSeverity,
    ValidationWarning,
)


LOCAL_PATH_RE = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\[^\s\\]+[\\/]|/(?:Users|home|root|tmp|var|opt)/)",
    re.IGNORECASE,
)
RETRIEVAL_SCORE_RE = re.compile(
    r"\b(?:bm25|rrf|dense(?:\s+(?:score|similarity))?|cosine(?:\s+similarity)?|"
    r"retrieval\s+score|hybrid\s+score|embedding\s+score)\b",
    re.IGNORECASE,
)
CHUNK_ID_RE = re.compile(r"\bchunk(?:[_ -]?id)?\b|\b[0-9a-f]{64}\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<![\w])(?:\d+(?:[.,]\d+)?)(?:\s*%)?")
COMPLETION_RE = re.compile(
    r"\b(?:completed|implemented|delivered|deployed|achieved|produced|executed|performed|"
    r"resulted|reduced|increased|improved|realised|realized|"
    r"réalis(?:é|ée|és|ées)|mis(?:e)?\s+en\s+(?:œuvre|oeuvre|place)|livr(?:é|ée|és|ées)|"
    r"déploy(?:é|ée|és|ées)|exécut(?:é|ée|és|ées)|achev(?:é|ée|és|ées)|"
    r"تم\s+(?:تنفيذ|إنجاز|تسليم))\b",
    re.IGNORECASE,
)
CAPITALIZED_SEQUENCE_RE = re.compile(
    r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,}(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]{1,})+\b"
)
TITLED_PERSON_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Mme|Mlle|Dr|Prof|Pr)\.?\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+"
    r"(?:\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+)+\b",
    re.IGNORECASE,
)
PORTFOLIO_SUPERLATIVE_RE = re.compile(
    r"\b(?:extensive experience|market leader|leading provider|hundreds of projects|"
    r"dozens of projects|unrivalled experience|unmatched experience|"
    r"vaste exp[ée]rience|leader du march[ée]|des centaines de projets|des dizaines de projets|"
    r"خبرة واسعة|رائد السوق|مئات المشاريع)\b",
    re.IGNORECASE,
)
ROI_RE = re.compile(r"\b(?:roi|return on investment|retour sur investissement)\b", re.IGNORECASE)
FINANCIAL_OUTCOME_RE = re.compile(
    r"\b(?:cost savings?|financial gains?|revenue increase|profit increase|"
    r"économies?|gains? financiers?|augmentation (?:du chiffre d['’]affaires|des revenus|des bénéfices)|"
    r"وفورات|أرباح|زيادة الإيرادات)\b",
    re.IGNORECASE,
)
AWARD_RE = re.compile(
    r"\b(?:award(?:ed)?|prize|trophée|distinction|récompense|جائزة|تكريم)\b",
    re.IGNORECASE,
)
CERTIFICATION_RE = re.compile(
    r"\b(?:ISO\s*\d{4,5}(?::\d{4})?|PMP|ITIL|certif(?:ied|ication|ié|iée|iés|iées)|معتمد|شهادة)\b",
    re.IGNORECASE,
)
SUCCESS_RE = re.compile(
    r"\b(?:successfully|avec succès|réussi(?:e|es|s)?|réussite|بنجاح)\b",
    re.IGNORECASE,
)
CLIENT_OUTCOME_RE = re.compile(
    r"\b(?:the client (?:achieved|obtained|reduced|increased|improved)|"
    r"enabled the client to|resulted in|le client a (?:obtenu|réduit|augmenté|amélioré)|"
    r"a permis au client de|نتج عن|مكّن العميل من)\b",
    re.IGNORECASE,
)
ACRONYM_EXPANSION_RE = re.compile(
    r"\b((?:[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*\s+){1,6}"
    r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.-]*)\s*\(([A-Z]{2,8})\)"
)
CONSERVATIVE_BENEFIT_RE = re.compile(
    r"^\s*(?:renforcement|am[ée]lioration|structuration|meilleure\s+visibilit[ée]|"
    r"clarification|s[ée]curisation|mise\s+[àa]\s+disposition|strengthening|"
    r"structuring|improved\s+ability|greater\s+ability|improved\s+visibility|"
    r"greater\s+visibility|better\s+preparedness|enhanced\s+preparedness|securing|availability|"
    r"تعزيز|هيكلة|تحسين\s+الرؤية|توضيح|تأمين|إتاحة|قدرة\s+أفضل|تحسين\s+القدرة|رفع\s+الجاهزية)\b",
    re.IGNORECASE,
)

STOPWORDS = {
    "about", "after", "also", "avec", "avoir", "client", "dans", "devoteam", "elle", "elles",
    "from", "have", "having", "leur", "leurs", "mission", "pour", "project", "projet", "reference",
    "référence", "that", "their", "this", "through", "using", "with", "work", "completed", "delivered",
    "implemented", "performed", "réalisé", "réalisée", "réalisés", "mise", "place", "oeuvre", "œuvre",
}

EXTRA_TECHNOLOGIES: dict[str, tuple[str, ...]] = {
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "Google Cloud": ("google cloud", "gcp"),
    "Kubernetes": ("kubernetes",),
    "Docker": ("docker",),
    "Oracle": ("oracle",),
    "Salesforce": ("salesforce",),
    "ServiceNow": ("servicenow",),
    "Power BI": ("power bi",),
    "Tableau": ("tableau",),
    "Python": ("python",),
    "Java": ("java",),
}

COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "Tunisie": ("tunisie", "tunisia"),
    "France": ("france",),
    "Maroc": ("maroc", "morocco"),
    "Algérie": ("algérie", "algerie", "algeria"),
    "Côte d'Ivoire": ("côte d'ivoire", "cote d ivoire", "ivory coast"),
    "Sénégal": ("sénégal", "senegal"),
    "Arabie saoudite": ("arabie saoudite", "saudi arabia", "ksa"),
    "Rwanda": ("rwanda",),
    "Mali": ("mali",),
    "Niger": ("niger",),
    "Togo": ("togo",),
    "Bénin": ("bénin", "benin"),
    "Cameroun": ("cameroun", "cameroon"),
    "Mauritanie": ("mauritanie", "mauritania"),
    "Libye": ("libye", "libya"),
    "Burkina Faso": ("burkina faso",),
    "Canada": ("canada",),
    "Germany": ("germany", "allemagne"),
    "United Kingdom": ("united kingdom", "royaume uni", "uk"),
    "United States": ("united states", "etats unis", "usa"),
    "United Arab Emirates": ("united arab emirates", "emirats arabes unis", "uae"),
    "Qatar": ("qatar",),
    "Egypt": ("egypt", "egypte"),
}


@dataclass(frozen=True)
class _Claim:
    field_path: str
    value: SupportedNarrativeText
    reference_id: str | None


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    folded = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^\w%]+", " ", folded.casefold(), flags=re.UNICODE).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {_normalize(text)} "
    normalized_phrase = _normalize(phrase)
    return bool(normalized_phrase and f" {normalized_phrase} " in normalized_text)


def _numbers(value: str) -> set[str]:
    return {match.replace(" ", "").replace(",", ".") for match in NUMBER_RE.findall(value)}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _normalize(value).split()
        if len(token) >= 4 and token not in STOPWORDS and not token.isdigit()
    }


def _claims(narrative: ReferenceSectionNarrative) -> Iterable[_Claim]:
    yield _Claim("section_intro", narrative.section_intro, None)
    yield _Claim("overall_storyline", narrative.overall_storyline, None)
    yield _Claim("why_these_references", narrative.why_these_references, None)
    for index, reference in enumerate(narrative.references):
        root = f"references[{index}]"
        yield _Claim(f"{root}.headline", reference.headline, reference.reference_id)
        yield _Claim(f"{root}.short_description", reference.short_description, reference.reference_id)
        yield _Claim(f"{root}.challenge", reference.challenge, reference.reference_id)
        yield _Claim(f"{root}.devoteam_contribution", reference.devoteam_contribution, reference.reference_id)
        for bullet_index, bullet in enumerate(reference.realisations):
            yield _Claim(f"{root}.realisations[{bullet_index}]", bullet, reference.reference_id)
        for bullet_index, bullet in enumerate(reference.benefits):
            yield _Claim(f"{root}.benefits[{bullet_index}]", bullet, reference.reference_id)
        yield _Claim(
            f"{root}.why_relevant_to_opportunity",
            reference.why_relevant_to_opportunity,
            reference.reference_id,
        )


class ClaimValidator:
    def __init__(
        self,
        bundles: list[ReferenceSourceBundle],
        support_index: dict[str, SourceSupportRecord],
        known_fact_values: dict[str, set[str]] | None = None,
        support_plan: NarrativeSupportPlan | None = None,
        allow_catalog_completion_detail: bool = False,
    ):
        self.bundles = {bundle.reference_id: bundle for bundle in bundles}
        self.support_index = support_index
        self.known_fact_values = known_fact_values or {}
        self.support_plan = support_plan
        self.allow_catalog_completion_detail = allow_catalog_completion_detail
        self.reference_plans = (
            {plan.reference_id: plan for plan in support_plan.references} if support_plan is not None else {}
        )

    def _planned_support_ids(self, claim: _Claim) -> list[str] | None:
        if self.support_plan is None:
            return None
        if claim.reference_id is None:
            return list(getattr(self.support_plan.section, claim.field_path))
        plan = self.reference_plans.get(claim.reference_id)
        if plan is None:
            return []
        field_name = claim.field_path.rsplit(".", 1)[-1].split("[", 1)[0]
        return list(getattr(plan, field_name))

    @staticmethod
    def _warning(
        code: str,
        message: str,
        *,
        claim: _Claim | None = None,
        reference_id: str | None = None,
        support_ids: list[str] | None = None,
        severity: ValidationSeverity = ValidationSeverity.BLOCKING,
    ) -> ValidationWarning:
        return ValidationWarning(
            code=code,
            message=message,
            severity=severity,
            blocking=severity == ValidationSeverity.BLOCKING,
            field_path=claim.field_path if claim else None,
            reference_id=reference_id if reference_id is not None else (claim.reference_id if claim else None),
            support_ids=support_ids or (list(claim.value.support_ids) if claim else []),
        )

    def _validate_reference_set(
        self,
        narrative: ReferenceSectionNarrative,
        selected_reference_ids: list[str],
    ) -> list[ValidationWarning]:
        warnings: list[ValidationWarning] = []
        generated_ids = [reference.reference_id for reference in narrative.references]
        for reference_id in generated_ids:
            if reference_id not in selected_reference_ids:
                warnings.append(
                    self._warning(
                        "UNSELECTED_REFERENCE",
                        "The model introduced a reference that the user did not select.",
                        reference_id=reference_id,
                    )
                )
        if len(generated_ids) != len(set(generated_ids)):
            warnings.append(self._warning("DUPLICATE_REFERENCE", "The generated narrative duplicates a reference."))
        missing = [reference_id for reference_id in selected_reference_ids if reference_id not in generated_ids]
        for reference_id in missing:
            warnings.append(
                self._warning(
                    "MISSING_SELECTED_REFERENCE",
                    "The generated narrative omitted a selected reference.",
                    reference_id=reference_id,
                )
            )
        if not missing and not any(warning.code == "UNSELECTED_REFERENCE" for warning in warnings):
            if generated_ids != selected_reference_ids:
                warnings.append(
                    self._warning(
                        "REFERENCE_ORDER_CHANGED",
                        "The generated reference ordering differs from the user selection.",
                    )
                )
        return warnings

    def _allowed_fact_text(self, reference_ids: set[str]) -> str:
        values: list[str] = []
        for reference_id in reference_ids:
            bundle = self.bundles.get(reference_id)
            if not bundle:
                continue
            for field_name in (
                "reference_number", "mission_title", "client", "country", "period", "sector", "offering",
                "business_unit",
            ):
                fact = getattr(bundle.facts, field_name)
                if fact:
                    values.append(fact.value)
            values.extend(fact.value for fact in bundle.facts.technologies)
        return " ".join(values)

    def _validate_known_facts(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        reference_ids = {claim.reference_id} if claim.reference_id else {record.reference_id for record in referenced_records}
        allowed = self._allowed_fact_text({value for value in reference_ids if value})
        support_text = " ".join(record.text for record in referenced_records)
        warnings: list[ValidationWarning] = []
        for field, candidates in self.known_fact_values.items():
            for candidate in candidates:
                if len(_normalize(candidate)) < 4 or not _contains_phrase(claim.value.text, candidate):
                    continue
                if _contains_phrase(allowed, candidate) or _contains_phrase(support_text, candidate):
                    continue
                code_field = "year" if field == "project_year" else field
                warnings.append(
                    self._warning(
                        f"UNSUPPORTED_{code_field.upper()}",
                        f"The narrative contains an unsupported {code_field} value.",
                        claim=claim,
                    )
                )
        for country, aliases in COUNTRY_ALIASES.items():
            if not any(_contains_phrase(claim.value.text, alias) for alias in aliases):
                continue
            if any(_contains_phrase(allowed, alias) or _contains_phrase(support_text, alias) for alias in aliases):
                continue
            warnings.append(
                self._warning(
                    "UNSUPPORTED_COUNTRY",
                    f"The narrative contains an unsupported country value: {country}.",
                    claim=claim,
                )
            )
        return warnings

    def _validate_technology(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        technologies = {label: needles for label, needles in TECHNOLOGY_RULES}
        technologies.update(EXTRA_TECHNOLOGIES)
        support_text = " ".join(record.text for record in referenced_records)
        reference_ids = {claim.reference_id} if claim.reference_id else {record.reference_id for record in referenced_records}
        allowed = f"{support_text} {self._allowed_fact_text({value for value in reference_ids if value})}"
        for label, aliases in technologies.items():
            mentions = (label, *aliases)
            if not any(_contains_phrase(claim.value.text, value) for value in mentions):
                continue
            if any(_contains_phrase(allowed, value) for value in mentions):
                continue
            return [
                self._warning(
                    "FABRICATED_TECHNOLOGY",
                    f"The narrative introduces unsupported technology: {label}.",
                    claim=claim,
                )
            ]
        return []

    def _validate_sensitive_wording(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        support_text = " ".join(record.text for record in referenced_records)
        checks = (
            (ROI_RE, "UNSUPPORTED_ROI", "The narrative introduces an unsupported ROI claim."),
            (
                FINANCIAL_OUTCOME_RE,
                "UNSUPPORTED_FINANCIAL_OUTCOME",
                "The narrative introduces unsupported monetary or financial value.",
            ),
            (
                AWARD_RE,
                "UNSUPPORTED_AWARD",
                "The narrative introduces an unsupported award or distinction.",
            ),
            (
                CERTIFICATION_RE,
                "UNSUPPORTED_CERTIFICATION",
                "The narrative introduces an unsupported certification claim.",
            ),
            (
                SUCCESS_RE,
                "UNSUPPORTED_SUCCESS_CLAIM",
                "The narrative describes delivery as successful without direct support.",
            ),
            (
                CLIENT_OUTCOME_RE,
                "UNSUPPORTED_CLIENT_OUTCOME",
                "The narrative introduces an unsupported client outcome.",
            ),
        )
        warnings: list[ValidationWarning] = []
        for pattern, code, message in checks:
            matches = [match.group(0) for match in pattern.finditer(claim.value.text)]
            if matches and not all(_contains_phrase(support_text, value) for value in matches):
                warnings.append(self._warning(code, message, claim=claim))
        if claim.reference_id is None:
            matches = [match.group(0) for match in PORTFOLIO_SUPERLATIVE_RE.finditer(claim.value.text)]
            if matches and not all(_contains_phrase(support_text, value) for value in matches):
                warnings.append(
                    self._warning(
                        "UNSUPPORTED_PORTFOLIO_SUPERLATIVE",
                        "The section-level narrative contains an unsupported portfolio superlative.",
                        claim=claim,
                    )
                )
        return warnings

    def _weak_support_warning(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        source_types = {
            source_type
            for record in referenced_records
            for source_type in record.support_types
        }
        strong_types = {SourceType.COMPLETED_WORK_EVIDENCE, SourceType.CLIENT_ATTESTATION}
        if source_types and not (source_types & strong_types):
            return [
                self._warning(
                    "WEAK_SOURCE_SUPPORT",
                    "The claim is supported only by catalog, proposal, contractual, or unverified evidence.",
                    claim=claim,
                    severity=ValidationSeverity.WARNING,
                )
            ]
        return []

    def _validate_named_entities(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        support_text = " ".join(record.text for record in referenced_records)
        reference_ids = {claim.reference_id} if claim.reference_id else {record.reference_id for record in referenced_records}
        allowed = f"{support_text} {self._allowed_fact_text({value for value in reference_ids if value})}"
        candidates = set(CAPITALIZED_SEQUENCE_RE.findall(claim.value.text))
        titled_people = set(TITLED_PERSON_RE.findall(claim.value.text))
        for candidate in sorted(candidates | titled_people):
            if _contains_phrase(allowed, candidate):
                continue
            return [
                self._warning(
                    "UNSUPPORTED_NAMED_ENTITY",
                    f"The narrative introduces an unsupported named entity or person: {candidate}.",
                    claim=claim,
                )
            ]
        return []

    def _validate_acronym_expansions(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        support_text = " ".join(record.text for record in referenced_records)
        for expansion, acronym in ACRONYM_EXPANSION_RE.findall(claim.value.text):
            if _contains_phrase(support_text, expansion) and _contains_phrase(support_text, acronym):
                continue
            return [
                self._warning(
                    "UNSUPPORTED_ACRONYM_EXPANSION",
                    f"The generated expansion of {acronym} is not present in trusted source text.",
                    claim=claim,
                )
            ]
        return []

    def _validate_completion(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        if claim.field_path.endswith(".headline"):
            return []
        if not COMPLETION_RE.search(claim.value.text):
            return []
        completed = [
            record
            for record in referenced_records
            if SourceType.COMPLETED_WORK_EVIDENCE in record.support_types
        ]
        if not completed:
            proposal_only = any(
                source_type in record.support_types
                for record in referenced_records
                for source_type in (SourceType.PROPOSAL_SCOPE, SourceType.CONTRACTUAL_SCOPE)
            )
            return [
                self._warning(
                    "PROPOSAL_SCOPE_AS_COMPLETED" if proposal_only else "UNSUPPORTED_COMPLETION_LANGUAGE",
                    (
                        "Proposal or contractual scope is represented as completed delivery."
                        if proposal_only
                        else "Completion language is not supported by completed-work evidence."
                    ),
                    claim=claim,
                )
            ]

        # The completion document may attest the mission globally while the
        # trusted catalog record carries its detailed activity list.
        completed_text = " ".join(
            record.text
            for record in (referenced_records if self.allow_catalog_completion_detail else completed)
        )
        claim_tokens = _tokens(claim.value.text)
        completed_tokens = _tokens(completed_text)
        coverage = len(claim_tokens & completed_tokens) / max(1, len(claim_tokens))
        unsupported_completed_numbers = _numbers(claim.value.text) - _numbers(completed_text)
        if coverage < 0.5 or unsupported_completed_numbers:
            return [
                self._warning(
                    "COMPLETION_DETAIL_NOT_ATTESTED",
                    "Detailed completed-work wording is not supported by the cited completion evidence.",
                    claim=claim,
                )
            ]
        return []

    def _validate_benefit(
        self,
        claim: _Claim,
        referenced_records: list[SourceSupportRecord],
    ) -> list[ValidationWarning]:
        if ".benefits[" not in claim.field_path or not claim.value.text.strip():
            return []
        support_tokens = _tokens(" ".join(record.text for record in referenced_records))
        claim_tokens = _tokens(claim.value.text)
        coverage = len(claim_tokens & support_tokens) / max(1, len(claim_tokens))
        conservative_entailed = bool(CONSERVATIVE_BENEFIT_RE.search(claim.value.text)) and coverage >= 0.25
        if coverage < 0.4 and not conservative_entailed:
            return [
                self._warning(
                    "UNSUPPORTED_BENEFIT",
                    "The benefit is not directly supported by the cited source text.",
                    claim=claim,
                )
            ]
        return []

    def _validate_claim(
        self,
        claim: _Claim,
        selected_reference_ids: set[str],
    ) -> list[ValidationWarning]:
        text = claim.value.text
        support_ids = list(claim.value.support_ids)
        planned_support_ids = self._planned_support_ids(claim)
        warnings: list[ValidationWarning] = []
        if not text.strip():
            if support_ids:
                warnings.append(
                    self._warning(
                        "EMPTY_TEXT_WITH_SUPPORT",
                        "An empty narrative field must not claim source support.",
                        claim=claim,
                    )
                )
            return warnings
        if not support_ids:
            warnings.append(
                self._warning("MISSING_SUPPORT", "A non-empty narrative field has no support IDs.", claim=claim)
            )
        if planned_support_ids is not None:
            if not planned_support_ids:
                warnings.append(
                    self._warning(
                        "EMPTY_SUPPORT_PLAN_VIOLATION",
                        "The model populated a field for which the deterministic support plan is empty.",
                        claim=claim,
                    )
                )
            elif support_ids != planned_support_ids:
                warnings.append(
                    self._warning(
                        "PROVENANCE_PLAN_MISMATCH",
                        "The attached support IDs do not match the deterministic field support plan.",
                        claim=claim,
                    )
                )

        referenced_records: list[SourceSupportRecord] = []
        for support_id in support_ids:
            record = self.support_index.get(support_id)
            if record is None:
                warnings.append(
                    self._warning(
                        "UNKNOWN_SUPPORT_ID",
                        f"The narrative references an unknown support ID: {support_id}.",
                        claim=claim,
                        support_ids=[support_id],
                    )
                )
                continue
            referenced_records.append(record)
            if record.reference_id not in selected_reference_ids:
                warnings.append(
                    self._warning(
                        "UNSELECTED_REFERENCE_SUPPORT",
                        "A narrative field cites support belonging to an unselected reference.",
                        claim=claim,
                        support_ids=[support_id],
                    )
                )
            if claim.reference_id and record.reference_id != claim.reference_id:
                warnings.append(
                    self._warning(
                        "WRONG_REFERENCE_SUPPORT",
                        "A per-reference narrative field cites support belonging to another reference.",
                        claim=claim,
                        support_ids=[support_id],
                    )
                )

        if LOCAL_PATH_RE.search(text):
            warnings.append(self._warning("INTERNAL_PATH", "A local filesystem path appears in narrative text.", claim=claim))
        if RETRIEVAL_SCORE_RE.search(text):
            warnings.append(self._warning("RETRIEVAL_SCORE", "A retrieval score appears in narrative text.", claim=claim))
        if CHUNK_ID_RE.search(text):
            warnings.append(self._warning("INTERNAL_CHUNK_ID", "An internal chunk/reference identifier appears in narrative text.", claim=claim))

        supported_numbers = _numbers(" ".join(record.text for record in referenced_records))
        for number in sorted(_numbers(text) - supported_numbers):
            plain_number = number.rstrip("%")
            is_year = plain_number.isdigit() and len(plain_number) == 4 and 1900 <= int(plain_number) <= 2099
            warnings.append(
                self._warning(
                    (
                        "UNSUPPORTED_PERCENTAGE"
                        if number.endswith("%")
                        else "UNSUPPORTED_YEAR" if is_year else "UNSUPPORTED_NUMBER"
                    ),
                    f"The narrative contains an unsupported numeric value: {number}.",
                    claim=claim,
                )
            )
        warnings.extend(self._validate_known_facts(claim, referenced_records))
        warnings.extend(self._validate_technology(claim, referenced_records))
        warnings.extend(self._validate_named_entities(claim, referenced_records))
        warnings.extend(self._validate_acronym_expansions(claim, referenced_records))
        warnings.extend(self._validate_completion(claim, referenced_records))
        warnings.extend(self._validate_benefit(claim, referenced_records))
        warnings.extend(self._validate_sensitive_wording(claim, referenced_records))
        if referenced_records:
            warnings.extend(self._weak_support_warning(claim, referenced_records))
        return warnings

    def _unavailable_field_info(
        self,
        narrative: ReferenceSectionNarrative,
    ) -> list[ValidationWarning]:
        warnings: list[ValidationWarning] = []
        generated = {reference.reference_id: reference for reference in narrative.references}
        for reference_id, bundle in self.bundles.items():
            reference = generated.get(reference_id)
            if reference is None:
                continue
            empty_fields: list[str] = []
            if "challenge" in bundle.unavailable_fields and not reference.challenge.text.strip():
                empty_fields.append("challenge")
            if "benefits" in bundle.unavailable_fields and not reference.benefits:
                empty_fields.append("benefits")
            if "completed_work_details" in bundle.unavailable_fields and not reference.realisations:
                empty_fields.append("realisations")
            for field_name in empty_fields:
                warnings.append(
                    self._warning(
                        "UNAVAILABLE_FIELD_LEFT_EMPTY",
                        f"The unavailable {field_name} field was intentionally left empty.",
                        reference_id=reference_id,
                        severity=ValidationSeverity.INFO,
                    )
                )
        return warnings

    def validate(
        self,
        narrative: ReferenceSectionNarrative,
        selected_reference_ids: list[str],
    ) -> NarrativeValidationResult:
        warnings = self._validate_reference_set(narrative, selected_reference_ids)
        selected_reference_id_set = set(selected_reference_ids)
        for claim in _claims(narrative):
            warnings.extend(self._validate_claim(claim, selected_reference_id_set))
        warnings.extend(self._unavailable_field_info(narrative))

        deduplicated: list[ValidationWarning] = []
        seen: set[tuple[str, str | None, str | None, tuple[str, ...]]] = set()
        for warning in warnings:
            key = (warning.code, warning.field_path, warning.reference_id, tuple(warning.support_ids))
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(warning)
        blocked = any(warning.severity == ValidationSeverity.BLOCKING for warning in deduplicated)
        return NarrativeValidationResult(
            valid=not blocked,
            export_blocked=blocked,
            export_eligible=not blocked,
            warnings=deduplicated,
        )
