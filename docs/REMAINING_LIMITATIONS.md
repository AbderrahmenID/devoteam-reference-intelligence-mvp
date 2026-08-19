# Remaining Limitations

- Human-labeled multilingual qrels are unavailable. Technical regression safety is verified, but no official precision, recall, MRR or nDCG claim is possible.
- Four answerable-intent regression rows abstain under the selected conservative gate: DEV-012, DEV-020 and DEV-026 lack sufficient clean supporting evidence under their query/filter context; DEV-041 has no eligible reference under its mandatory Tunisia + Cloud + last-five-years filter.
- The source catalog aliases several commercial fields to `service_nature`. The field index de-duplicates those aliases and indexes only genuinely distinct text; missing descriptions/services are not invented.
- Field-aware BM25 indexes are built in memory at service startup. Startup is slower than loading the existing chunk BM25 alone, though query execution remains within the measured local regression envelope.
- Explicit out-of-portfolio scope phrases are deterministic and maintainable, but not exhaustive. Novel unsupported domains may still require the general relevance gate to abstain.
- Arabic and mixed-script behavior passed technical checks, but fluent Arabic-speaking reviewers are still required for qualitative language assessment.
- The local corpus is finite and internal. Absence of a result means insufficient eligible evidence, not proof that Devoteam has no such experience.
- The system has no authentication or document-level authorization and is suitable only for the controlled local environment.
- Reranking, LLM generation, generative RAG, model replacement and fine-tuning remain deliberately out of scope.
