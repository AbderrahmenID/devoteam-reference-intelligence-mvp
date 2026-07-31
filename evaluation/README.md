# Human evaluation

The CSV files are empty, schema-valid templates. Add multilingual queries reviewed by domain experts and their qrels; do not treat technical smoke queries as official judgments.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m evaluation.evaluate
```

With empty qrels, the evaluator returns `HUMAN_JUDGMENTS_REQUIRED` and no metrics. With reviewed labels it reports Success@1/3, Precision@3, Recall@10/20, MRR@10, nDCG@10, no-answer false-positive rate, answerable zero-result rate, sample counts and p50/p95 latency. Rankings come from the same retrieval service used by the API; only evaluation is allowed to inspect more than the three UI results.

