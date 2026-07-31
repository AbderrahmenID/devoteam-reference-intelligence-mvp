# Supervisor demo guide

1. Open PowerShell in the project and run `.\start.ps1`.
2. Open <http://127.0.0.1:3000>; point out the real backend health indicator.
3. Search French: `Références de plan de continuité d’activité pour une banque`.
4. Show that at most three cards contain original passages, page citations, language and match reasons.
5. Search English: `Bank business continuity planning references` to demonstrate cross-language evidence.
6. Search Arabic: `مراجع حول استمرارية الأعمال للبنوك`, then mixed text: `PCA للبنوك en Tunisie`; show RTL-aware rendering and readable LTR citations.
7. Search `recette de cuisine pour gâteau au chocolat`; show explicit zero-result abstention rather than a nearest false positive.
8. Optionally open <http://127.0.0.1:8000/docs> to show the small API contract.
9. Run `.\scripts\demo_check.ps1` and explain that these are technical smoke inputs, not expert relevance labels.
10. Run `.\stop.ps1` to stop only the recorded backend/frontend processes.

Close by stating the honest remaining work: expert qrels, multilingual quality review, threshold calibration, security/auth design and OCR dependency installation if scanned preview is required.

