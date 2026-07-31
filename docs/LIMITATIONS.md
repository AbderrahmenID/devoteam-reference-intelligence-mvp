# Limitations

- This is an internship prototype, not a production-readiness claim.
- There is no production authentication, tenant isolation or document-level authorization.
- The internal corpus must not be exposed as a public service.
- There is no official held-out evaluation; human relevance labels are still required.
- A reviewed multilingual and cross-language evaluation sample is still required.
- Abstention thresholds are deterministic prototype heuristics pending expert calibration.
- The reranker is disabled; no cross-encoder is served.
- The corpus may not cover every commercial domain or newer engagement.
- A nearest result is not always a relevant result; this is why zero-result abstention exists.
- Source metadata can contain inconsistencies inherited from the validated corpus.
- Extraction quality varies on scanned, rotated or mixed-language PDFs.
- Tesseract and its `fra+eng+ara` packs are absent on the current machine, so scanned-page OCR preview is blocked until installed; retrieval is unaffected.
- No corpus rebuild, embedding regeneration, model fine-tuning, LLM answering or cloud deployment is included.

