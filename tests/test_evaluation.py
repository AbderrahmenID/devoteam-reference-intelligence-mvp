from pathlib import Path

from evaluation.evaluate import evaluate
from evaluation.metrics import ndcg_at, precision_at, recall_at, reciprocal_rank_at, success_at


ROOT = Path(__file__).resolve().parents[1]


def test_empty_templates_require_human_judgments() -> None:
    result = evaluate(
        ROOT / "evaluation/queries_multilingual.csv",
        ROOT / "evaluation/qrels_multilingual.csv",
        ROOT,
    )
    assert result["status"] == "HUMAN_JUDGMENTS_REQUIRED"
    assert result["metrics"] is None


def test_metric_formulas_on_a_small_technical_example() -> None:
    ranked = ["a", "b", "c"]
    relevant = {"b", "c"}
    assert success_at(ranked, relevant, 1) == 0
    assert success_at(ranked, relevant, 3) == 1
    assert precision_at(ranked, relevant, 3) == 2 / 3
    assert recall_at(ranked, relevant, 2) == 1 / 2
    assert reciprocal_rank_at(ranked, relevant, 10) == 1 / 2
    assert 0 < ndcg_at(ranked, {"b": 2, "c": 1}, 10) < 1

