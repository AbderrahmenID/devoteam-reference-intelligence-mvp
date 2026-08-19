# Development Query Import Blocker

Status: **BLOCKED — INVALID OR AMBIGUOUS MANDATORY FILTERS**

The 50-query workbook itself is structurally valid: IDs are unique, texts are non-empty and distinct, language and query-type labels are supported, answerable/no-answer tags are exclusive, owner approval fields are complete, and no formulas or direct corpus-text copies were detected.

Freezing is intentionally stopped because three filter-constrained queries do not use the API's exact supported filter schema. The workbook has not been overwritten, no filter meaning has been guessed, and no candidate pool has been generated.

| Query | Unsupported input fields | Required decision |
|---|---|---|

The machine-readable review queue is `evaluation/judging/INVALID_FILTER_REVIEW_QUEUE.csv`. `DEV-012` and `DEV-041` include validated candidate canonical filter objects for owner approval. `DEV-026` requires an explicit country list because `regions: West Africa` has no unambiguous API equivalent; its `Banking` sector also needs approval to use the source label `Banque`.

The protected held-out workbook was not opened or compared, preserving the declared test boundary.
