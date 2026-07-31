from pathlib import Path

import numpy as np
import yaml

from retrieval.dense import DenseIndex, E5QueryEncoder


ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    def encode_query(self, query: str) -> np.ndarray:
        assert query == "target"
        return np.asarray([1.0, 0.0], dtype=np.float32)


def test_dense_dot_product_and_hard_mask() -> None:
    embeddings = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    index = DenseIndex(embeddings, FakeEncoder())
    scores, vector = index.score("target", np.asarray([True, False]))
    assert np.allclose(vector, [1.0, 0.0])
    assert scores[0] == 1.0 and np.isneginf(scores[1])


def test_local_e5_query_encoder_uses_pinned_snapshot() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    encoder = E5QueryEncoder(config["model"], device="cpu")
    vector = encoder.encode_query("bank business continuity")
    assert vector.shape == (768,)
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-4)

