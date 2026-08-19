from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

from .normalization import normalize_search_text


YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
ONGOING_RE = re.compile(r"\b(?:ongoing|present|présent|en\s+cours|actuel(?:le)?)\b", re.I)
INVALID_TEXT = {"", "nan", "none", "null", "#value!", "n/a", "na"}


COUNTRY_ALIASES = {
    "abidjan": ("Côte d’Ivoire", "CI"),
    "algerie": ("Algérie", "DZ"),
    "benin": ("Bénin", "BJ"),
    "burkina faso": ("Burkina Faso", "BF"),
    "cameroun": ("Cameroun", "CM"),
    "cote d ivoire": ("Côte d’Ivoire", "CI"),
    "france": ("France", "FR"),
    "libya": ("Libye", "LY"),
    "libye": ("Libye", "LY"),
    "mali": ("Mali", "ML"),
    "maroc": ("Maroc", "MA"),
    "mauritanie": ("Mauritanie", "MR"),
    "niger": ("Niger", "NE"),
    "rwanda": ("Rwanda", "RW"),
    "senegal": ("Sénégal", "SN"),
    "togo": ("Togo", "TG"),
    "tunise": ("Tunisie", "TN"),
    "tunisie": ("Tunisie", "TN"),
}


TECHNOLOGY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("API management", ("api gateway", "api management", "kong")),
    ("Cloud", ("cloud", "infonuagique")),
    ("COBIT", ("cobit",)),
    ("Core banking", ("core banking",)),
    ("Data platform", ("data warehouse", "big data", "plateforme data", "lac de donnees")),
    ("Digital identity", ("identity and access", "gestion des identites", "iam")),
    ("ERP", ("enterprise resource planning", " erp ", "sap")),
    ("IPv6", ("ipv6",)),
    ("ITIL", ("itil", "service desk")),
    ("Network", ("reseau", "network", "vpn", "backbone")),
)


THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Audit technique et organisationnel", ("audit", "diagnostic", "etat des lieux", "evaluation de l existant")),
    ("Réingénierie des processus", ("reingenierie", "processus metier", "processus operationnel", "optimisation des processus")),
    ("Rédaction des cahiers des charges", ("cahier des charges", "specifications fonctionnelles", "specifications techniques", " rfp ", " rfi ")),
    ("Réseaux et architecture", ("architecture", "reseau", "network", "infrastructure")),
    ("Sécurité des SI et interopérabilité", ("securite", "cyber", "interoperabilite", "pentest", "protection des donnees")),
    ("Accompagnement à la mise en place", ("mise en place", "mise en oeuvre", "deploiement", "assistance a maitrise d ouvrage", "amoa")),
    ("Conduite du changement", ("conduite du changement", "transfert de competences", "formation des utilisateurs", "accompagnement au changement")),
)


FILTER_CATEGORIES = (
    "country",
    "sector",
    "client",
    "offering",
    "service_nature",
    "technology",
    "status",
    "evidence_available",
    "evidence_type",
    "language",
    "themes",
    "business_unit",
    "data_quality_status",
)


def clean_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return "" if text.casefold() in INVALID_TEXT else text


def facet_key(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", normalize_search_text(value), flags=re.UNICODE).strip()


def _matched_labels(text: str, rules: Iterable[tuple[str, tuple[str, ...]]]) -> list[str]:
    normalized = f" {normalize_search_text(text)} "
    return [label for label, needles in rules if any(needle in normalized for needle in needles)]


def _country(raw: Any) -> tuple[str, str | None]:
    value = clean_text(raw)
    if not value:
        return "", None
    lookup_key = facet_key(value)
    return COUNTRY_ALIASES.get(lookup_key, (value, None))


def _document_languages(chunks: pd.DataFrame, indices: list[int]) -> list[str]:
    values: set[str] = set()
    for index in indices:
        value = clean_text(chunks.iloc[index].get("document_language"))
        if value:
            values.update(part for part in value.casefold().split("-") if part)
    return sorted(values)


@dataclass(slots=True)
class NormalizedReference:
    reference_id: str
    row_number: int
    reference_number: str | None
    project_title: str
    mission_name: str
    client: str
    country: str
    country_code: str | None
    sector: str
    offering: str
    service_nature: str
    business_unit: str
    start_year: int | None
    end_year: int | None
    source_end_year: int | None
    period: str
    status: str | None
    evidence_available: bool
    evidence_types: list[str]
    document_languages: list[str]
    technologies: list[str]
    key_themes: list[str]
    data_quality_status: str
    linked_chunk_indices: list[int] = field(default_factory=list)

    def facet_values(self, category: str) -> set[str]:
        mapping: dict[str, Iterable[str]] = {
            "country": [self.country],
            "sector": [self.sector],
            "client": [self.client],
            "offering": [self.offering],
            "service_nature": [self.service_nature],
            "technology": self.technologies,
            "status": [self.status or ""],
            "evidence_available": ["available" if self.evidence_available else "unavailable"],
            "evidence_type": self.evidence_types,
            "language": self.document_languages,
            "themes": self.key_themes,
            "business_unit": [self.business_unit],
            "data_quality_status": [self.data_quality_status],
        }
        return {value for value in mapping[category] if value}


class ReferenceMetadataIndex:
    """Deterministic, in-memory metadata projection over immutable parquet assets."""

    def __init__(self, references: pd.DataFrame, chunks: pd.DataFrame, current_year: int | None = None):
        self.current_year = current_year or datetime.now().year
        self.references_frame = references
        self.chunks = chunks
        self.reference_ids_by_row: dict[int, list[str]] = defaultdict(list)
        eligible_records: dict[str, dict[str, Any]] = {}
        for record in references.to_dict(orient="records"):
            if not bool(record.get("document_retrieval_eligible")):
                continue
            reference_id = str(record["reference_id"])
            eligible_records[reference_id] = record
            self.reference_ids_by_row[int(record["row_number"])].append(reference_id)

        chunks_by_reference: dict[str, list[int]] = defaultdict(list)
        for index, chunk in chunks.iterrows():
            try:
                rows = [int(value) for value in json.loads(chunk["reference_rows_json"])]
            except (TypeError, ValueError, json.JSONDecodeError):
                rows = []
            for row in rows:
                for reference_id in self.reference_ids_by_row.get(row, []):
                    chunks_by_reference[reference_id].append(int(index))

        self.by_id: dict[str, NormalizedReference] = {}
        for reference_id, record in eligible_records.items():
            linked = sorted(set(chunks_by_reference.get(reference_id, [])))
            if not linked:
                continue
            normalized = self._normalize(record, linked)
            self.by_id[reference_id] = normalized

        self.all_ids = set(self.by_id)
        self._vocabularies = self._build_vocabularies()

    def _normalize(self, record: dict[str, Any], linked: list[int]) -> NormalizedReference:
        service_nature = clean_text(record.get("service_nature"))
        offering = clean_text(record.get("offering"))
        client = clean_text(record.get("client"))
        country, country_code = _country(record.get("country"))
        raw_period = clean_text(record.get("project_year"))
        years = sorted({int(value) for value in YEAR_RE.findall(raw_period)})
        ongoing = bool(ONGOING_RE.search(raw_period))
        start_year = years[0] if years else None
        source_end_year = years[-1] if years else None
        end_year = self.current_year if ongoing and start_year else source_end_year
        if start_year and ongoing:
            period = f"{start_year}–present"
        elif start_year and end_year and start_year != end_year:
            period = f"{start_year}–{end_year}"
        elif start_year:
            period = str(start_year)
        else:
            period = ""
        status = "ongoing" if ongoing else ("completed" if years else None)

        evidence_types = {
            clean_text(record.get("attestation_available")),
            *(
                clean_text(self.chunks.iloc[index].get("document_type"))
                for index in linked
            ),
        }
        evidence_types.discard("")
        if "Sans JUSTIF" in evidence_types:
            evidence_types.remove("Sans JUSTIF")

        source_text = " ".join(
            [service_nature, offering]
            + [clean_text(self.chunks.iloc[index].get("chunk_text")) for index in linked]
        )
        reference_number = clean_text(record.get("reference_number")) or None
        title = service_nature or offering
        if len(title) > 220:
            title = title[:217].rstrip() + "…"

        return NormalizedReference(
            reference_id=str(record["reference_id"]),
            row_number=int(record["row_number"]),
            reference_number=reference_number,
            project_title=title,
            mission_name=service_nature,
            client=client,
            country=country,
            country_code=country_code,
            sector=clean_text(record.get("sector")),
            offering=offering,
            service_nature=service_nature,
            business_unit=clean_text(record.get("business_unit")),
            start_year=start_year,
            end_year=end_year,
            source_end_year=source_end_year,
            period=period,
            status=status,
            evidence_available=bool(record.get("evidence_available")) and bool(linked),
            evidence_types=sorted(evidence_types, key=normalize_search_text),
            document_languages=_document_languages(self.chunks, linked),
            technologies=_matched_labels(source_text, TECHNOLOGY_RULES),
            key_themes=_matched_labels(source_text, THEME_RULES),
            data_quality_status=clean_text(record.get("data_quality_status")),
            linked_chunk_indices=linked,
        )

    def _build_vocabularies(self) -> dict[str, dict[str, str]]:
        vocabularies: dict[str, dict[str, str]] = {}
        for category in FILTER_CATEGORIES:
            counts: Counter[str] = Counter()
            label_by_key: dict[str, str] = {}
            for reference in self.by_id.values():
                for label in reference.facet_values(category):
                    key = facet_key(label)
                    if not key:
                        continue
                    counts[key] += 1
                    label_by_key.setdefault(key, label)
            vocabularies[category] = {
                key: label_by_key[key]
                for key, _ in sorted(counts.items(), key=lambda item: (-item[1], label_by_key[item[0]].casefold()))
            }
        return vocabularies

    def _canonical_values(self, category: str, requested: Any) -> tuple[set[str], list[str]]:
        values = requested if isinstance(requested, list) else [requested]
        wanted: set[str] = set()
        labels: list[str] = []
        vocabulary = self._vocabularies[category]
        unknown: list[str] = []
        for value in values:
            key = facet_key(value)
            if not key:
                continue
            if key not in vocabulary:
                unknown.append(str(value))
                continue
            wanted.add(key)
            labels.append(vocabulary[key])
        if unknown:
            raise ValueError(f"Unknown {category} filter value(s): {', '.join(sorted(unknown))}")
        return wanted, labels

    def resolve_filters(self, filters: dict[str, Any] | None) -> tuple[set[str], dict[str, Any], dict[str, int] | None]:
        requested = {key: value for key, value in (filters or {}).items() if value not in (None, "", [])}
        for legacy_name in ("attestation_available", "document_type"):
            legacy = requested.pop(legacy_name, None)
            if legacy is None:
                continue
            legacy_values = legacy if isinstance(legacy, list) else [legacy]
            current = requested.get("evidence_type", [])
            current_values = current if isinstance(current, list) else [current]
            requested["evidence_type"] = [*current_values, *legacy_values]
        supported = set(FILTER_CATEGORIES) | {"period", "project_year", "year_after", "year_before"}
        unknown_categories = set(requested) - supported
        if unknown_categories:
            raise ValueError(f"Unsupported hard filters: {sorted(unknown_categories)}")

        eligible = set(self.all_ids)
        applied: dict[str, Any] = {}
        for category in FILTER_CATEGORIES:
            if category not in requested:
                continue
            wanted, labels = self._canonical_values(category, requested[category])
            if not wanted:
                continue
            eligible &= {
                reference_id
                for reference_id, reference in self.by_id.items()
                if {facet_key(value) for value in reference.facet_values(category)} & wanted
            }
            applied[category] = labels

        resolved_period = self._resolve_period(requested)
        if resolved_period:
            start, end = resolved_period["start_year"], resolved_period["end_year"]
            eligible &= {
                reference_id
                for reference_id, reference in self.by_id.items()
                if reference.start_year is not None
                and reference.end_year is not None
                and reference.start_year <= end
                and reference.end_year >= start
            }
            applied["period"] = dict(resolved_period)

        if "project_year" in requested:
            raw_values = requested["project_year"] if isinstance(requested["project_year"], list) else [requested["project_year"]]
            try:
                years = {int(value) for value in raw_values}
            except (TypeError, ValueError) as exc:
                raise ValueError("project_year values must be four-digit years") from exc
            if any(year < 1900 or year > 2100 for year in years):
                raise ValueError("project_year values must be between 1900 and 2100")
            eligible &= {
                reference_id
                for reference_id, reference in self.by_id.items()
                if reference.start_year is not None
                and reference.end_year is not None
                and any(reference.start_year <= year <= reference.end_year for year in years)
            }
            applied["project_year"] = sorted(years)

        return eligible, applied, resolved_period

    def _resolve_period(self, requested: dict[str, Any]) -> dict[str, int] | None:
        period = dict(requested.get("period") or {})
        if "year_after" in requested:
            period["start_year"] = int(requested["year_after"])
        if "year_before" in requested:
            period["end_year"] = int(requested["year_before"])
        if not period:
            return None
        preset = period.get("preset")
        if preset and (period.get("start_year") is not None or period.get("end_year") is not None):
            raise ValueError("period preset cannot be combined with explicit years")
        if preset:
            presets = {"last_3_years": 3, "last_5_years": 5, "last_10_years": 10}
            if preset not in presets:
                raise ValueError(f"Unknown period preset: {preset}")
            start = self.current_year - presets[preset] + 1
            end = self.current_year
        else:
            start = int(period.get("start_year", 1900))
            end = int(period.get("end_year", self.current_year))
        if start < 1900 or end > 2100 or start > end:
            raise ValueError("period must be a valid interval between 1900 and 2100")
        return {"start_year": start, "end_year": end}

    def facets(self, reference_ids: set[str] | None = None) -> dict[str, Any]:
        ids = self.all_ids if reference_ids is None else set(reference_ids)
        output: dict[str, Any] = {}
        for category in FILTER_CATEGORIES:
            counts: Counter[str] = Counter()
            labels: dict[str, str] = {}
            for reference_id in ids:
                reference = self.by_id.get(reference_id)
                if not reference:
                    continue
                for label in reference.facet_values(category):
                    key = facet_key(label)
                    counts[key] += 1
                    labels[key] = self._vocabularies[category].get(key, label)
            output[category] = [
                {"value": labels[key], "count": count}
                for key, count in sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]].casefold()))
            ]
        years = [
            year
            for reference_id in ids
            for year in (
                self.by_id[reference_id].start_year,
                self.by_id[reference_id].end_year,
            )
            if year is not None
        ]
        output["period"] = {
            "min_year": min(years) if years else None,
            "max_year": max(years) if years else None,
            "current_year": self.current_year,
            "presets": ["last_3_years", "last_5_years", "last_10_years"],
        }
        return output
