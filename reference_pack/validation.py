from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from retrieval.metadata import THEME_RULES, TECHNOLOGY_RULES, _matched_labels, clean_text

from .schemas import TrustedEvidence, TrustedReference


SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ReferenceValidationError(ValueError):
    def __init__(self, reason: str, reference_ids: list[str], detail: str):
        super().__init__(detail)
        self.reason = reason
        self.reference_ids = reference_ids
        self.detail = detail

    def as_detail(self) -> dict[str, Any]:
        return {"reason": self.reason, "reference_ids": self.reference_ids, "message": self.detail}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_rows(value: Any) -> list[int]:
    try:
        return [int(item) for item in json.loads(str(value))]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _short_title(value: str, fallback: str) -> str:
    cleaned = clean_text(value) or clean_text(fallback) or "Devoteam reference"
    candidate = re.split(r"[•\n]|(?<=[.!?])\s+", cleaned, maxsplit=1)[0].strip()
    if len(candidate) <= 52:
        return candidate
    shortened = candidate[:52].rsplit(" ", 1)[0].rstrip(" ,;:-")
    shortened = re.sub(
        r"\s+(?:à|au|aux|de|des|du|d['’]|en|et|pour|vers)$",
        "",
        shortened,
        flags=re.IGNORECASE,
    ).rstrip(" ,;:-")
    return shortened or candidate[:52].rstrip(" ,;:-")


@dataclass(frozen=True)
class CorpusIdentity:
    version: str
    manifest_path: Path
    manifest_sha256: str
    manifest: dict[str, Any]
    chunks_sha256: str
    reference_catalog_sha256: str


class TrustedV2Repository:
    """Reload and validate reference content from manifest-pinned v2 assets."""

    def __init__(self, project_root: Path, config: dict[str, Any]):
        self.project_root = project_root.resolve()
        self.config = config
        self.chunks_path = (self.project_root / config["data"]["chunks"]).resolve()
        self.references_path = (self.project_root / config["data"]["reference_catalog"]).resolve()
        self.manifest_path = (self.project_root / config["data"]["manifest"]).resolve()
        self.policy_path = self.project_root / "data/versions/v2/chunk_policy.parquet"
        self.quarantine_path = self.project_root / "data/versions/v2/quarantined_chunks.parquet"
        self._assert_inside_project(self.chunks_path)
        self._assert_inside_project(self.references_path)
        self._assert_inside_project(self.manifest_path)
        self.identity = self._validate_manifest()
        self.chunks = pd.read_parquet(self.chunks_path)
        self.references = pd.read_parquet(self.references_path)
        self.policies = pd.read_parquet(self.policy_path)
        self.quarantined = pd.read_parquet(self.quarantine_path)
        self._validate_v2_contract()

    def _assert_inside_project(self, path: Path) -> None:
        if path != self.project_root and self.project_root not in path.parents:
            raise RuntimeError(f"Trusted data path escapes the project root: {path.name}")

    def _validate_manifest(self) -> CorpusIdentity:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if manifest.get("pipeline_version") != "targeted_repair_v2" or manifest.get("status") != "PASS":
            raise RuntimeError("The selected corpus manifest is not a passing targeted-repair v2 manifest")
        artifacts = {record["path"]: record for record in manifest.get("artifacts", [])}
        chunk_key = self.chunks_path.relative_to(self.project_root).as_posix()
        reference_key = self.references_path.relative_to(self.project_root).as_posix()
        for key, path in ((chunk_key, self.chunks_path), (reference_key, self.references_path)):
            expected = artifacts.get(key, {}).get("sha256")
            actual = sha256_file(path)
            if not expected or actual != expected:
                raise RuntimeError(f"Trusted v2 artifact hash mismatch: {key}")
        return CorpusIdentity(
            version="v2",
            manifest_path=self.manifest_path,
            manifest_sha256=sha256_file(self.manifest_path),
            manifest=manifest,
            chunks_sha256=artifacts[chunk_key]["sha256"],
            reference_catalog_sha256=artifacts[reference_key]["sha256"],
        )

    def _validate_v2_contract(self) -> None:
        required_chunk_columns = {
            "chunk_id", "document_id", "source_file_name", "source_sha256",
            "page_number_1_based", "citation_label", "citation_uri", "reference_rows_json",
            "approved_for_retrieval", "approved_for_display", "display_text",
            "security_classification", "page_language", "document_language", "source_relative_path",
        }
        missing = required_chunk_columns - set(self.chunks.columns)
        if missing:
            raise RuntimeError(f"Trusted v2 chunks are missing columns: {sorted(missing)}")
        if not self.chunks["chunk_id"].astype(str).is_unique:
            raise RuntimeError("Trusted v2 chunk IDs are not unique")
        if not self.chunks["approved_for_retrieval"].astype(bool).all():
            raise RuntimeError("The active v2 retrieval asset contains a non-approved chunk")

    def _linked_chunks(self, row_number: int) -> pd.DataFrame:
        mask = self.chunks["reference_rows_json"].map(lambda value: row_number in _load_rows(value))
        return self.chunks.loc[mask].copy()

    def _is_quarantined_only(self, row_number: int) -> bool:
        if self.quarantined.empty:
            return False
        return bool(
            self.quarantined["reference_rows_json"].map(
                lambda value: row_number in _load_rows(value)
            ).any()
        )

    def load_selected(self, reference_ids: list[str]) -> list[TrustedReference]:
        if len(reference_ids) != len(set(reference_ids)):
            raise ReferenceValidationError(
                "DUPLICATE_REFERENCE_ID", reference_ids, "Duplicate reference IDs are not allowed"
            )
        by_id = self.references.set_index(self.references["reference_id"].astype(str), drop=False)
        unknown = [reference_id for reference_id in reference_ids if reference_id not in by_id.index]
        if unknown:
            raise ReferenceValidationError(
                "UNKNOWN_REFERENCE_ID", unknown, "One or more selected references do not exist in v2"
            )

        output: list[TrustedReference] = []
        for reference_id in reference_ids:
            row = by_id.loc[reference_id]
            if isinstance(row, pd.DataFrame):
                raise ReferenceValidationError(
                    "AMBIGUOUS_REFERENCE_ID", [reference_id], "The stable reference ID is not unique"
                )
            row_number = int(row["row_number"])
            if not bool(row.get("document_retrieval_eligible")):
                reason = "REFERENCE_QUARANTINED" if self._is_quarantined_only(row_number) else "REFERENCE_NOT_RETRIEVAL_APPROVED"
                raise ReferenceValidationError(reason, [reference_id], "The selected reference is not exportable")

            linked = self._linked_chunks(row_number)
            if linked.empty:
                raise ReferenceValidationError(
                    "REFERENCE_WITHOUT_EVIDENCE", [reference_id], "No v2 evidence is linked to the selected reference"
                )
            if not linked["approved_for_retrieval"].astype(bool).all():
                raise ReferenceValidationError(
                    "REFERENCE_NOT_RETRIEVAL_APPROVED", [reference_id], "Linked evidence is not retrieval-approved"
                )

            allowed_security = set(self.config["filters"]["allowed_security_classifications"])
            authorized = linked[linked["security_classification"].astype(str).isin(allowed_security)]
            if authorized.empty:
                raise ReferenceValidationError(
                    "REFERENCE_NOT_AUTHORIZED", [reference_id], "The current local user context cannot access this reference"
                )
            display = authorized[authorized["approved_for_display"].astype(bool)].copy()
            if display.empty:
                raise ReferenceValidationError(
                    "DISPLAY_EVIDENCE_REQUIRED", [reference_id], "The reference has no display-approved evidence"
                )

            evidence: list[TrustedEvidence] = []
            document_hashes: dict[str, str] = {}
            display = display.sort_values(["document_id", "page_number_1_based", "chunk_index_in_page", "chunk_id"])
            for _, chunk in display.iterrows():
                document_id = clean_text(chunk["document_id"])
                source_name = Path(clean_text(chunk["source_file_name"])).name
                source_hash = clean_text(chunk["source_sha256"]).casefold()
                source_page = int(chunk["page_number_1_based"])
                citation_label = clean_text(chunk["citation_label"])
                citation_uri = clean_text(chunk["citation_uri"])
                display_text = clean_text(chunk["display_text"])
                valid = (
                    bool(document_id)
                    and bool(source_name)
                    and bool(SHA256_RE.fullmatch(source_hash))
                    and source_page > 0
                    and bool(citation_label)
                    and bool(citation_uri)
                    and bool(display_text)
                )
                if not valid:
                    raise ReferenceValidationError(
                        "INVALID_SOURCE_LINEAGE", [reference_id], "Display evidence has incomplete document/page lineage"
                    )
                previous_hash = document_hashes.setdefault(document_id, source_hash)
                if previous_hash != source_hash:
                    raise ReferenceValidationError(
                        "SOURCE_HASH_MISMATCH", [reference_id], "A source document maps to multiple source hashes"
                    )
                evidence.append(
                    TrustedEvidence(
                        chunk_id=str(chunk["chunk_id"]),
                        document_id=document_id,
                        source_file_name=source_name,
                        source_sha256=source_hash,
                        source_page=source_page,
                        citation_label=citation_label,
                        citation_uri=citation_uri,
                        language=clean_text(chunk.get("page_language")) or clean_text(chunk.get("document_language")) or "und",
                        display_text=display_text,
                        source_relative_path=clean_text(chunk.get("source_relative_path")),
                    )
                )

            service = clean_text(row.get("service_nature"))
            offering = clean_text(row.get("offering"))
            source_text = f"{service} {offering}"
            output.append(
                TrustedReference(
                    reference_id=reference_id,
                    reference_number=clean_text(row.get("reference_number")) or None,
                    row_number=row_number,
                    mission_title=_short_title(service, offering),
                    client=clean_text(row.get("client")),
                    country=clean_text(row.get("country")),
                    period=clean_text(row.get("project_year")),
                    sector=clean_text(row.get("sector")),
                    offering=offering,
                    business_unit=clean_text(row.get("business_unit")),
                    description=service,
                    services_delivered=[service] if service else [],
                    technologies=_matched_labels(source_text, TECHNOLOGY_RULES),
                    capabilities=_matched_labels(source_text, THEME_RULES),
                    evidence=evidence,
                )
            )
        return output
