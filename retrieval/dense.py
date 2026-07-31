from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import numpy as np


class QueryEncoder(Protocol):
    def encode_query(self, query: str) -> np.ndarray: ...


class E5QueryEncoder:
    """Offline-only adapter preserving the source index's exact E5 contract."""

    def __init__(self, model_config: dict, device: str | None = None):
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

        local_path = Path(model_config["local_path"]).expanduser().resolve()
        if not local_path.is_dir():
            raise FileNotFoundError(
                f"Pinned E5 model is unavailable at {local_path}. Startup will not download it."
            )
        self.prefix = str(model_config["query_prefix"])
        if self.prefix != "query: ":
            raise ValueError("E5 query prefix must remain 'query: '")
        if str(model_config["passage_prefix"]) != "passage: ":
            raise ValueError("E5 passage prefix must remain 'passage: '")
        self.normalize = bool(model_config["normalize_embeddings"])
        self.dimension = int(model_config["dimensions"])
        self.model = SentenceTransformer(str(local_path), device=device, local_files_only=True)
        actual_dimension = int(self.model.get_sentence_embedding_dimension())
        if actual_dimension != self.dimension:
            raise AssertionError(f"Embedding dimension changed: {actual_dimension}")

    def encode_query(self, query: str) -> np.ndarray:
        vector = self.model.encode(
            [self.prefix + query], normalize_embeddings=self.normalize,
            convert_to_numpy=True, show_progress_bar=False,
        )[0]
        vector = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        if vector.shape != (self.dimension,) or not np.isfinite(vector).all():
            raise AssertionError("Dense query vector is invalid")
        if self.normalize and not np.isclose(norm, 1.0, atol=1e-4):
            raise AssertionError("Dense query vector is not normalized")
        return vector


class DenseIndex:
    def __init__(self, embeddings: np.ndarray, encoder: QueryEncoder):
        self.embeddings = embeddings
        self.encoder = encoder
        if len(embeddings.shape) != 2 or not np.isfinite(embeddings).all():
            raise AssertionError("Passage embedding matrix is invalid")

    @classmethod
    def load(cls, embeddings_path: Path, encoder: QueryEncoder) -> "DenseIndex":
        return cls(np.load(embeddings_path, mmap_mode="r"), encoder)

    def score(self, query: str, allowed_mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        vector = self.encoder.encode_query(query)
        if vector.shape != (self.embeddings.shape[1],):
            raise ValueError("Query vector dimension does not match passage embeddings")
        scores = np.asarray(self.embeddings @ vector, dtype=np.float32)
        if allowed_mask is not None:
            mask = np.asarray(allowed_mask, dtype=bool)
            if mask.shape != (self.embeddings.shape[0],):
                raise ValueError("Dense allowed mask has the wrong shape")
            scores[~mask] = -np.inf
        return scores, vector

