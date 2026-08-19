# Supervisor demo guide

1. Open PowerShell in the project and run `.\start.ps1`.
2. Open <http://127.0.0.1:3000>; point out the real backend health indicator.
3. Search French: `Références de plan de continuité d’activité pour une banque`.
4. Show the total count, 10/20/50 page size, deterministic sorting and page navigation beyond the former three-result limit.
5. Select `Tunisie` and `PCA/PCI`; explain that facets are source-derived and the hard mask is applied before retrieval.
6. Toggle between the template-inspired summary table and detailed annex-style reference fields.
7. Select the current page, move to another page, select another stable ID and show the persistent selected count.
8. Export the selected DOCX; point out the summary table, per-reference annex and filename/page/link citations.
9. Search English: `Bank business continuity planning references` to demonstrate cross-language evidence.
10. Search Arabic: `مراجع حول استمرارية الأعمال للبنوك`, then mixed text: `PCA للبنوك en Tunisie`; show RTL-aware rendering and readable LTR citations.
11. Search `recette de cuisine pour gâteau au chocolat`; show explicit zero-result abstention rather than a nearest false positive.
12. Apply `last 3 years`; in 2026 this resolves to 2024–2026 and correctly shows `NO_ELIGIBLE_REFERENCE` because the eligible catalog ends in 2022.
13. Optionally open <http://127.0.0.1:8000/docs> to show facets, search and DOCX export contracts.
14. Run `.\scripts\demo_check.ps1` and explain that these are technical smoke inputs, not expert relevance labels.
15. Run `.\stop.ps1` to stop only the recorded backend/frontend processes.

Close by stating the honest remaining work: expert qrels, multilingual quality review, threshold calibration, security/auth design, OCR dependency installation if scanned preview is required and page-image DOCX QA on a host with a working renderer.
