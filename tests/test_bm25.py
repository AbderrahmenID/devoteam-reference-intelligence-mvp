from pathlib import Path

import numpy as np

from retrieval.bm25 import BM25Index
from retrieval.normalization import normalize_search_text, tokenize_multilingual


ROOT = Path(__file__).resolve().parents[1]


def test_multilingual_normalization_handles_accents_and_arabic_variants() -> None:
    assert tokenize_multilingual("Sécurité française") == ["securite", "francaise"]
    assert normalize_search_text("إدارة أعمال") == normalize_search_text("ادارة أعمال")


def test_bm25_ranks_exact_domain_terms_first() -> None:
    index = BM25Index.build(["API gateway Kong SUNU", "cloud migration", "business strategy"])
    scores = index.score("Kong API gateway")
    assert int(np.argmax(scores)) == 0
    assert scores[0] > scores[1]


def test_source_bm25_artifact_loads_and_filters() -> None:
    index = BM25Index.load(
        ROOT / "data/indexes/bm25_index.npz", ROOT / "data/indexes/bm25_vocabulary.json"
    )
    assert index.document_count == 1185
    allowed = np.zeros(1185, dtype=bool)
    allowed[:10] = True
    scores = index.score("PCA", allowed)
    assert np.isneginf(scores[10:]).all()

