import numpy as np

from retrieval.bm25 import BM25Index
from retrieval.dense import DenseIndex
from retrieval.hybrid import HybridRetriever


class FixedEncoder:
    def encode_query(self, query: str) -> np.ndarray:
        return np.asarray([1.0, 0.0], dtype=np.float32)


def test_hybrid_is_deterministic_and_combines_retrievers() -> None:
    bm25 = BM25Index.build(["exact api gateway", "semantic reference", "unrelated text"])
    dense = DenseIndex(
        np.asarray([[0.7, 0.7141428], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        FixedEncoder(),
    )
    config = {"hybrid": {"candidate_depth": 3, "rrf_k": 60, "lexical_weight": 0.5, "dense_weight": 0.5}}
    retriever = HybridRetriever(bm25, dense, ["a", "b", "c"], config)
    first = retriever.score("exact api", np.ones(3, dtype=bool))
    second = retriever.score("exact api", np.ones(3, dtype=bool))
    assert first.fused_ranked == second.fused_ranked
    assert set(first.fused_ranked[:2]) == {0, 1}


def test_hybrid_hard_mask_excludes_rows() -> None:
    bm25 = BM25Index.build(["api", "api gateway"])
    dense = DenseIndex(np.asarray([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32), FixedEncoder())
    config = {"hybrid": {"candidate_depth": 2, "rrf_k": 60, "lexical_weight": 0.5, "dense_weight": 0.5}}
    scores = HybridRetriever(bm25, dense, ["a", "b"], config).score(
        "api", np.asarray([False, True])
    )
    assert scores.fused_ranked == [1]

