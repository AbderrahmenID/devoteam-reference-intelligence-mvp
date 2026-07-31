from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from retrieval.service import RetrievalService

from .metrics import ndcg_at, precision_at, recall_at, reciprocal_rank_at, success_at


REQUIRED_QUERY_COLUMNS = {
    "query_id", "query_text", "query_language", "expected_evidence_language",
    "cross_language_expected", "query_type", "no_answer_expected", "reviewer", "notes",
}
REQUIRED_QREL_COLUMNS = {"query_id", "reference_id", "relevance", "reviewer", "notes"}


def _truthy(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "y"}


def evaluate(queries_path: Path, qrels_path: Path, root: Path) -> dict[str, Any]:
    queries = pd.read_csv(queries_path, dtype=str).fillna("")
    qrels = pd.read_csv(qrels_path, dtype=str).fillna("")
    missing_queries = REQUIRED_QUERY_COLUMNS - set(queries.columns)
    missing_qrels = REQUIRED_QREL_COLUMNS - set(qrels.columns)
    if missing_queries or missing_qrels:
        raise ValueError(
            f"Template columns missing: queries={sorted(missing_queries)}, qrels={sorted(missing_qrels)}"
        )
    if queries.empty or qrels.empty:
        return {
            "status": "HUMAN_JUDGMENTS_REQUIRED",
            "message": "Add reviewed multilingual queries and qrels before calculating relevance metrics.",
            "query_rows": int(len(queries)), "qrel_rows": int(len(qrels)), "metrics": None,
        }

    config = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    service = RetrievalService(root, config)
    judgments: dict[str, dict[str, float]] = defaultdict(dict)
    for row in qrels.to_dict(orient="records"):
        relevance = float(row["relevance"])
        judgments[str(row["query_id"])][str(row["reference_id"])] = relevance

    ranking_values: dict[str, list[float]] = defaultdict(list)
    no_answer_count = no_answer_false_positives = 0
    answerable_count = answerable_zero_results = 0
    latency: list[float] = []
    language_counts: Counter[str] = Counter()
    cross_language_count = 0
    evaluated = 0

    for row in queries.to_dict(orient="records"):
        query_id = str(row["query_id"])
        graded = judgments.get(query_id, {})
        no_answer = _truthy(row["no_answer_expected"])
        if not no_answer and not graded:
            continue
        result = service.search(str(row["query_text"]), top_k=3)
        ranked = service.rank_reference_ids(str(row["query_text"]), limit=20)
        latency.append(float(result.latency_ms))
        language_counts[str(row["query_language"] or "und")] += 1
        cross_language_count += int(_truthy(row["cross_language_expected"]))
        evaluated += 1
        if no_answer:
            no_answer_count += 1
            no_answer_false_positives += int(result.result_count > 0)
            continue
        relevant = {reference_id for reference_id, value in graded.items() if value > 0}
        answerable_count += 1
        answerable_zero_results += int(result.result_count == 0)
        ranking_values["success_at_1"].append(success_at(ranked, relevant, 1))
        ranking_values["success_at_3"].append(success_at(ranked, relevant, 3))
        ranking_values["precision_at_3"].append(precision_at(ranked, relevant, 3))
        ranking_values["recall_at_10"].append(recall_at(ranked, relevant, 10))
        ranking_values["recall_at_20"].append(recall_at(ranked, relevant, 20))
        ranking_values["mrr_at_10"].append(reciprocal_rank_at(ranked, relevant, 10))
        ranking_values["ndcg_at_10"].append(ndcg_at(ranked, graded, 10))

    means = {name: round(statistics.fmean(values), 6) if values else None for name, values in ranking_values.items()}
    means.update({
        "no_answer_false_positive_rate": round(no_answer_false_positives / no_answer_count, 6) if no_answer_count else None,
        "answerable_zero_result_rate": round(answerable_zero_results / answerable_count, 6) if answerable_count else None,
        "per_language_sample_counts": dict(sorted(language_counts.items())),
        "cross_language_sample_count": cross_language_count,
        "p50_latency_ms": round(float(np.percentile(latency, 50)), 2) if latency else None,
        "p95_latency_ms": round(float(np.percentile(latency, 95)), 2) if latency else None,
    })
    return {
        "status": "HUMAN_JUDGMENTS_EVALUATED", "evaluated_queries": evaluated,
        "answerable_queries": answerable_count, "no_answer_queries": no_answer_count,
        "metrics": means,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate human-reviewed multilingual reference qrels")
    parser.add_argument("--queries", type=Path, default=Path("evaluation/queries_multilingual.csv"))
    parser.add_argument("--qrels", type=Path, default=Path("evaluation/qrels_multilingual.csv"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(evaluate(args.queries, args.qrels, args.root.resolve()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

