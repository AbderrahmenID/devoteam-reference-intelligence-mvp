from __future__ import annotations

import json
from pathlib import Path

from app.api.settings import load_config
from reference_pack.schemas import ReferencePackRequest
from reference_pack.service import ReferencePackService
from reference_pack.validation import ReferenceValidationError


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    service = ReferencePackService(ROOT, load_config())
    valid: list[tuple[str, str, str]] = []
    eligible = service.repository.references.loc[
        service.repository.references["document_retrieval_eligible"], "reference_id"
    ].astype(str)
    for reference_id in eligible:
        try:
            reference = service.repository.load_selected([reference_id])[0]
        except ReferenceValidationError:
            continue
        valid.append((reference_id, reference.mission_title, reference.client))
        if len(valid) >= 10:
            break

    cases = [
        ("fr-one", 1, "fr", "Références pertinentes pour la mission", "Client de démonstration", "Sélection de références Devoteam"),
        ("en-three", 3, "en", "Relevant references for the opportunity", "Demonstration client", "Selected Devoteam references"),
        ("ar-four", 4, "ar", "المراجع ذات الصلة بالفرصة", "عميل تجريبي", "مجموعة مختارة من مراجع ديفوتيم"),
        ("fr-ten", 10, "fr", "Références Devoteam pertinentes", "Opportunité de démonstration", "Dossier multi-références"),
    ]
    outputs = []
    for name, count, language, title, client, subtitle in cases:
        request = ReferencePackRequest(
            title=title,
            client_name=client,
            subtitle=subtitle,
            language=language,
            reference_ids=[item[0] for item in valid[:count]],
            output_formats=["pptx", "pdf"],
        )
        artifact = service.generate(request)
        outputs.append(
            {
                "case": name,
                "directory": artifact.directory,
                "response": artifact.response.model_dump(mode="json"),
                "latency_ms": artifact.manifest["generation_latency_ms"],
            }
        )
        print(json.dumps(outputs[-1], ensure_ascii=False), flush=True)

    audit = ROOT / "audit/reference_pack"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "demo_generations.json").write_text(
        json.dumps({"selected_references": valid, "outputs": outputs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
