# Evaluation Data Inventory

Date: 2026-08-02  
Scope: `devoteam-reference-mvp` plus read-only inspection of `Devoteam_AI_CLEAN_PIPELINE`

## Decision

**No adequate human-judged development set exists. Precision tuning is blocked.**

The MVP evaluation templates contain no queries and no qrels. The source project's bootstrap data is explicitly metadata-derived and non-expert. Its multilingual query-intake workbook is explicitly frozen-test-only, remains draft, has incomplete governance, and has no label or adjudication artifacts. It cannot be repurposed for development tuning.

## MVP assets

| Asset | Rows / scope | Languages | Relevance labels | Reviewers | Provenance and leakage | Allowed use | May tune? |
|---|---:|---|---|---:|---|---|---|
| `evaluation/queries_multilingual.csv` | 0 queries | schema supports multilingual | none | 0 | Empty human-query template | Future reviewed query registry | No |
| `evaluation/qrels_multilingual.csv` | 0 qrels | n/a | none | 0 | Empty qrel template | Future reviewed judgments | No |
| `evaluation/evaluate.py` and `evaluation/metrics.py` | evaluator code | language-agnostic | consumes graded qrels | n/a | Returns `HUMAN_JUDGMENTS_REQUIRED` when empty | Reproducible evaluation after labels exist | No data to tune |
| `scripts/demo_check.ps1` | 5 technical smoke inputs | FR, EN, AR, mixed; one unsupported FR | none | 0 | Hand-coded technical regression inputs; not official queries | Encoding, lifecycle, citation, abstention regression | No |
| Python test suite | 62 technical tests | FR, EN, AR, mixed examples | no corpus relevance judgments | 0 | Synthetic unit/integration fixtures and deterministic corpus assertions | Software correctness and regression safety | No |
| `audit/hotfix-reproduction.json` | 1 reproduced query, 46 unique reference-candidate chunks | FR query; multilingual evidence | none | 0 | Diagnostic generated from the reported PCA defect | Hotfix trace and corpus-review inclusion | No |
| `audit/corpus_quality/HUMAN_CHUNK_REVIEW.csv` | 180 chunk-review rows | FR, EN, AR, mixed | human fields blank | 0 | Intrinsic text-quality triage, not query/reference relevance | Human corpus validation only | No |

## Read-only source-project assets

Source root: external immutable `Devoteam_AI_CLEAN_PIPELINE` project (not required at runtime)

| Asset | Rows / scope | Languages | Relevance labels | Reviewers | Human-authored / judged | Synthetic or leakage status | Boundary and allowed use | May tune? |
|---|---:|---|---|---:|---|---|---|---|
| `data/indexes/20260714T154731Z_129ff982c8/phase5_hybrid_retrieval_v1/evaluation/bootstrap_queries.parquet` | 50 queries | FR only | document IDs derived from metadata | 0 | No / No | `BOOTSTRAP_METADATA_NOT_EXPERT`; query construction and labels expose corpus metadata | Technical bootstrap diagnostics only | No |
| `.../evaluation/bootstrap_results.parquet` | 1,494 result rows; 50 queries; 3 modes; ranks through 10 | FR queries | `is_relevant_bootstrap` only | 0 | No / No | Synthetic metadata relevance; high leakage risk for real precision claims | Plumbing and deterministic retrieval checks only | No |
| `.../evaluation/bootstrap_metrics.json` | 50-query aggregate | FR | metrics over bootstrap labels | 0 | No / No | Explicitly disallows production-quality claims | Historical technical diagnostics only | No |
| `.../evaluation/EXPERT_GOLD_SET_TEMPLATE.xlsx` | 50 blank query slots; 500 blank label slots | defaults to FR but editable | 0 completed labels | 0 | Template only | No populated data | Controlled future gold-set template | No |
| `data/evaluations/20260714T154731Z_129ff982c8/phase5_1_expert_evaluation_v1/human_inputs/PHASE_5_1_QUERY_INTAKE.xlsm` | 50 draft queries | 30 FR, 10 EN, 10 AR | none | evaluation owner named; labeler 1, labeler 2, adjudicator, and supervisor blank/unconfirmed | Authorship not evidenced; not human-judged | All rows say `APPROVED_REALISTIC`, `YES` for approval/non-derivation, but every note says draft and Devoteam review is still required | Protected `FROZEN_TEST_ONLY_NO_TUNING`; inventory only until governance validates it | No—never development tuning |
| `.../phase5_1_expert_evaluation_v1/PHASE_5_1_STATE.json` | one state record | n/a | none | 0 completed reviewers | No completed evaluation | Status `AWAITING_QUERY_INTAKE` | Governance/status evidence | No |
| `config/phase5_1_evaluation.yaml` and `src/devoteam_reference_ai/phase5_1_evaluation.py` | controlled workflow | requires at least 30 FR, 5 EN, 5 AR | requires two independent 0/1/2 labelers plus independent adjudication | 2 + adjudicator + supervisor | Intended human workflow | Anti-leakage purpose is `FROZEN_TEST_ONLY_NO_TUNING` | Future protected test evaluation; automatic promotion prohibited | No |

No `BLINDED_CANDIDATE_POOL`, labeler packets, adjudication packet, expert qrels, final expert queries, final labels, per-query metrics, or completed Phase 5.1 manifest exist in the source run. The source state confirms the process has not advanced to candidate judging.

## Human-authorship, judgment, and reviewer findings

- Human-authored development queries with verified provenance: **0**.
- Human-judged query/reference pairs: **0**.
- Completed independent relevance reviewers: **0**.
- Completed adjudications: **0**.
- Valid development/held-out split: **none**.
- Protected test candidate: the source Phase 5.1 workbook, but it is incomplete and must remain no-tuning.
- Metadata-derived bootstrap probes: available, but disallowed for relevance calibration or official metrics.

## Leakage and governance assessment

The bootstrap queries and their labels are derived from catalog/document metadata and therefore can reward direct metadata overlap. Their recorded MRR, nDCG, precision, and recall are technical bootstrap diagnostics only. They must not be compared with current MVP metrics as if they were human relevance results.

The source multilingual workbook has an appropriate anti-leakage intent, but its own state and row notes show that governance is incomplete. Because it is marked `FROZEN_TEST_ONLY_NO_TUNING`, its query text must not be used for configuration selection, threshold adjustment, failure-driven tuning, or development experiments. Any completed judgments belong to a protected final evaluation.

## Required evaluation boundary

1. Build a separate development set from real or explicitly approved realistic user information needs that were not copied from the reference corpus, bootstrap probes, or protected workbook.
2. Use two independent Devoteam domain experts, an independent adjudicator, and a named supervisor. Keep relevance fields blank until those people judge them.
3. Freeze the source Phase 5.1 workbook as held-out test material only after its governance is complete; do not inspect or reuse its text during tuning.
4. Tune only on adjudicated development qrels. Evaluate the held-out set once after configuration selection.
5. Preserve all source judgments. Corrections must be additive review records, never silent edits.

## Immediate action

Create an MVP-local blinded judging workflow. Existing smoke queries may be used only to validate the packet mechanics; they cannot become the official development set or unblock tuning. Domain experts must complete a separate query-intake file before a real development candidate pool is frozen.
