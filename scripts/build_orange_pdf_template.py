from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml
from pypdf import PdfReader, PdfWriter

from reference_pack.pdf_converter import LibreOfficePdfConverter
from reference_pack.validation import sha256_file


POWERPOINT_FIRST_SLIDE = 10
POWERPOINT_LAST_SLIDE = 29


def build(project_root: Path) -> tuple[Path, Path]:
    root = project_root.resolve()
    registry_path = root / "templates/reference_pack/qwen_studio/template_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    entry = registry["templates"]["orange_bank_compact"]
    source = (root / entry["source_file"]).resolve()
    expected_hash = str(entry["source_sha256"])
    before_hash = sha256_file(source)
    if before_hash != expected_hash:
        raise RuntimeError("Orange Bank PDF SHA-256 does not match the template registry")

    output_dir = root / "templates/reference_pack/derived"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "orange_pdf_pages_10_29.pptx"
    manifest_path = output_dir / "orange_pdf_pages_10_29.json"

    config = yaml.safe_load((root / entry["mapping_file"]).read_text(encoding="utf-8"))
    converter = LibreOfficePdfConverter(config["generation"]["libreoffice_candidates"])
    executable = converter.executable()
    if executable is None:
        raise RuntimeError("LibreOffice is required to import the Orange Bank PDF")

    reader = PdfReader(source)
    if len(reader.pages) < POWERPOINT_LAST_SLIDE:
        raise RuntimeError("Orange Bank PDF does not contain pages 10 through 29")

    with tempfile.TemporaryDirectory(prefix="orange_pdf_template_") as temporary:
        temporary_dir = Path(temporary)
        excerpt = temporary_dir / "orange_pdf_pages_10_29.pdf"
        writer = PdfWriter()
        for page_number in range(POWERPOINT_FIRST_SLIDE, POWERPOINT_LAST_SLIDE + 1):
            writer.add_page(reader.pages[page_number - 1])
        with excerpt.open("wb") as stream:
            writer.write(stream)

        command = [
            str(executable),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            "--infilter=impress_pdf_import",
            "--convert-to",
            "pptx",
            "--outdir",
            str(temporary_dir),
            str(excerpt),
        ]
        completed = subprocess.run(
            command,
            cwd=temporary_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        converted = temporary_dir / "orange_pdf_pages_10_29.pptx"
        if completed.returncode != 0 or not converted.is_file():
            details = (completed.stderr or completed.stdout or "unknown LibreOffice error").strip()
            raise RuntimeError(f"Orange Bank PDF import failed: {details}")
        shutil.copy2(converted, output)

    after_hash = sha256_file(source)
    if after_hash != before_hash:
        raise RuntimeError("Orange Bank source PDF changed during template import")

    manifest = {
        "schema_version": 1,
        "authoritative_source": source.relative_to(root).as_posix(),
        "authoritative_source_sha256": before_hash,
        "source_range_powerpoint": [POWERPOINT_FIRST_SLIDE, POWERPOINT_LAST_SLIDE],
        "source_range_zero_based": [POWERPOINT_FIRST_SLIDE - 1, POWERPOINT_LAST_SLIDE - 1],
        "derived_clone_base": output.relative_to(root).as_posix(),
        "derived_clone_base_sha256": sha256_file(output),
        "derived_slide_count": POWERPOINT_LAST_SLIDE - POWERPOINT_FIRST_SLIDE + 1,
        "roles": {
            "divider": [10],
            "compact_summary": list(range(11, 18)),
            "evidence_attestation": list(range(18, 30)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    output, manifest = build(args.project_root)
    print(output)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
