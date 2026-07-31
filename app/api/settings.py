from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    configured = Path(os.getenv("DEVOTEAM_CONFIG", "config.yaml")).expanduser()
    path = configured if configured.is_absolute() else PROJECT_ROOT / configured
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {"data", "model", "bm25", "dense", "hybrid", "abstention", "languages", "extraction", "api"}
    missing = required - set(config or {})
    if missing:
        raise ValueError(f"Configuration is missing sections: {sorted(missing)}")
    if int(config["hybrid"]["maximum_final_results"]) != 3:
        raise ValueError("maximum_final_results must be 3")
    if config["model"]["query_prefix"] != "query: " or config["model"]["passage_prefix"] != "passage: ":
        raise ValueError("Pinned E5 prefixes changed")
    if config.get("reranker_enabled"):
        raise ValueError("The MVP reranker must remain disabled")
    return config


def resolve_data_path(relative_path: str) -> Path:
    return (PROJECT_ROOT / relative_path).resolve()

