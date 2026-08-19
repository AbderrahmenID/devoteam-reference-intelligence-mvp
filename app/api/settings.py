from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    configured = Path(
        os.getenv(
            "DEVOTEAM_CONFIG",
            "config/baselines/SELECTED_RETRIEVAL_CONFIGURATION.yaml",
        )
    ).expanduser()
    path = configured if configured.is_absolute() else PROJECT_ROOT / configured
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {
        "data", "model", "bm25", "dense", "hybrid", "search", "filters", "export",
        "abstention", "meaningful_terms", "evidence_quality", "languages", "extraction", "api",
    }
    missing = required - set(config or {})
    if missing:
        raise ValueError(f"Configuration is missing sections: {sorted(missing)}")
    page_sizes = [int(value) for value in config["search"]["page_sizes"]]
    if page_sizes != [10, 20, 50]:
        raise ValueError("Supported page sizes must remain 10, 20, and 50")
    if int(config["search"]["safety_ceiling"]) <= 161:
        raise ValueError("Search safety_ceiling must exceed the full catalog size")
    if config["model"]["query_prefix"] != "query: " or config["model"]["passage_prefix"] != "passage: ":
        raise ValueError("Pinned E5 prefixes changed")
    if config.get("reranker_enabled"):
        raise ValueError("The MVP reranker must remain disabled")
    return config


def resolve_data_path(relative_path: str) -> Path:
    return (PROJECT_ROOT / relative_path).resolve()
