# Next Human Actions

## 1. Unblock official workbook creation

Enable the required spreadsheet artifact runtime, or explicitly open and connect a supported Microsoft Excel authoring session. Resume from the validated blinded CSV; do not reconstruct candidates manually and do not expose the private mapping to reviewers.

The official workbook must contain the eight prescribed sheets and must pass formatting, protection, validation, formula, hash, and blank-judgment checks before distribution.

## 2. Reviewer 1

Reviewer 1 works only in the `Reviewer_1` fields and assigns relevance using the judging guide. System versions, retrievers, scores, and original ranks must remain hidden. Evidence quality and reference relevance must be judged separately.

## 3. Reviewer 2

Reviewer 2 completes an independent copy or independently protected fields without seeing Reviewer 1's labels or notes. Reviewer 2 must not access the private candidate-pool files.

## 4. Adjudication

After both reviews are frozen, an independent adjudicator resolves disagreements and records the final label and rationale. Original reviewer labels must not be overwritten.

## 5. Protected fields

Do not edit query IDs, blinded candidate IDs, query text, approved filters, candidate metadata, evidence text, source document, or source page. Do not unblind candidates during review.

## 6. Return and tuning boundary

Return the completed workbook into `evaluation/judging/` with a new filename and preserve the original blank workbook. Validate reviewer identities, completeness, allowed labels, disagreements, and hashes before producing qrels.

No threshold, weight, candidate-depth, aggregation, reranker, or model tuning may begin until adjudicated qrels are frozen. No official retrieval metrics exist yet.

`DEV-041` currently has no filter-eligible candidate under the approved strict filter. Preserve that zero-candidate state unless the project owner explicitly changes the query filter in a new version.
