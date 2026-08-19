# Retrieval Diagnostic Guide

Run the selected v2 retrieval path from the project root:

```powershell
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -m retrieval.diagnose `
  --query 'Références PCA pour une banque' `
  --json
```

Add hard filters as JSON when needed:

```powershell
.\.venv\Scripts\python.exe -m retrieval.diagnose `
  --query 'cybersécurité et protection des données' `
  --filters '{"country":["Tunisie"],"period":{"preset":"last_5_years"}}' `
  --candidate-limit 10 `
  --json
```

The JSON trace includes normalized query text, detected language/scripts, meaningful terms, removed stopwords, resolved filters, eligible counts, field-aware BM25 candidates, dense candidates, weighted-RRF candidates, per-reference field scores, aggregation, selected/second evidence chunks, evidence-quality decisions, rejection reasons, final references, abstention and total diagnostic latency.

Diagnostics expose internal engineering scores by design. The user interface does not display those scores or fake confidence percentages. Without `--json`, the command prints only the final decision, result count and latency. `scripts/diagnose_retrieval.py` remains a compatibility wrapper for the same module.

To inspect another configuration without changing files:

```powershell
$env:DEVOTEAM_CONFIG = 'config/baselines/PRE_RETRIEVAL_IMPROVEMENT.yaml'
.\.venv\Scripts\python.exe -m retrieval.diagnose --query 'API Gateway Kong' --json
Remove-Item Env:DEVOTEAM_CONFIG
```
