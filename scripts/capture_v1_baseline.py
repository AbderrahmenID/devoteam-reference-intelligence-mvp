from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ASSETS = [
    "data/chunks.parquet",
    "data/reference_catalog.parquet",
    "data/indexes/bm25_index.npz",
    "data/indexes/bm25_vocabulary.json",
    "data/indexes/embeddings.npy",
    "data/indexes/chunk_lookup.parquet",
    "data/DATA_MANIFEST.json",
    "data/source_metadata/PHASE_4_MANIFEST.json",
    "data/indexes/PHASE_5_MANIFEST.json",
    "data/indexes/retrieval_runtime.json",
    "config.yaml",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "data/DATA_MANIFEST.json").read_text(encoding="utf-8"))
    expected = {
        str(item["destination_path"]): str(item["sha256"])
        for item in manifest["files"]
    }
    records = []
    for relative in ASSETS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        expected_digest = expected.get(relative)
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "manifest_sha256": expected_digest,
                "manifest_match": expected_digest is None or digest == expected_digest,
            }
        )
    if not all(record["manifest_match"] for record in records):
        raise AssertionError("A v1 runtime asset differs from DATA_MANIFEST.json")
    payload = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "snapshot_id": manifest["corpus_identity"]["snapshot_id"],
        "status": "PASS",
        "assets": records,
    }
    output = root / "audit/v1_runtime_asset_hashes.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
