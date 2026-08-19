from __future__ import annotations

from pathlib import Path

import yaml

from retrieval.bm25 import BM25Index
from retrieval.evidence import EvidenceQualityEvaluator, clean_display_text, select_best_evidence
from retrieval.terms import analyze_query_terms


ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def _analysis(query: str, evidence: str):
    corpus = [evidence, "unrelated technical delivery", "another distinct source"]
    return analyze_query_terms(query, BM25Index.build(corpus), CONFIG["meaningful_terms"])


def _quality(query: str, evidence: str, language: str):
    analysis = _analysis(query, evidence)
    return EvidenceQualityEvaluator(CONFIG["evidence_quality"]).evaluate(
        evidence,
        clean_display_text(evidence),
        analysis,
        dense_score=0.84,
        query_language=language,
        extraction_quality="PASS",
    )


def test_clean_french_english_arabic_and_coherent_mixed_evidence_passes() -> None:
    french = "Objet du contrat : accompagnement à la mise en place du PCA et réalisation des tests de continuité d’activité pour la banque."
    english = "Project scope: cloud implementation and services delivered for a secure Azure migration programme."
    arabic = "نطاق المشروع هو تنفيذ خطة استمرارية الأعمال وتقديم الخدمات اللازمة للبنوك وإدارة الاختبارات."
    mixed = "تحليل المخاطر واستمرارية الأعمال للبنك. Mission PCA réalisée avec des ateliers et un plan de test complet."
    assert _quality("PCA banque", french, "fr").quality_pass
    assert _quality("Azure cloud migration", english, "en").quality_pass
    assert _quality("استمرارية الأعمال للبنوك", arabic, "ar").quality_pass
    assert _quality("PCA استمرارية الأعمال", mixed, "mixed").quality_pass


def test_corrupted_ocr_evidence_is_rejected_with_diagnostics() -> None:
    corrupted = """x R ee
T 9
م س ر
aa |
PCA
1
2
zz 77
banque
@@@ ###
q"""
    quality = _quality("PCA banque", corrupted, "fr")
    assert not quality.quality_pass
    assert {
        "EXCESSIVE_FRAGMENTATION",
        "EXCESSIVE_SINGLE_CHARACTER_TOKENS",
        "OCR_GIBBERISH",
    } & set(quality.rejection_reasons)
    assert quality.diagnostics["line_fragmentation"] > 0.5


def test_pdf_line_wrap_and_safe_hyphenation_are_repaired() -> None:
    raw = """La mission couvre la continuité des activi-
tés et la préparation du plan de
test pour la banque.

Deuxième paragraphe source."""
    cleaned = clean_display_text(raw)
    assert "activités" in cleaned
    assert "plan de test" in cleaned
    assert "\n\nDeuxième paragraphe" in cleaned


def test_retrieval_prefix_is_never_exposed_as_display_text() -> None:
    cleaned = clean_display_text("passage: Projet cloud livré avec succès et services rendus au client.")
    assert cleaned.startswith("Projet cloud")
    assert not cleaned.startswith("passage:")


def test_clean_evidence_is_selected_over_noisy_higher_score_chunk() -> None:
    query = "PCA banque"
    clean = "Objet du contrat : réalisation d'une mission PCA pour la banque, avec tests et maintien en condition opérationnelle."
    noisy = "x R\nT 9\nم س\nPCA\nbanque\n1\n2\nzz\n@@@"
    analysis = _analysis(query, clean + " " + noisy)
    candidates = [
        {"row": 0, "chunk": {"chunk_id": "noisy", "chunk_text": noisy, "data_quality_status": "PASS"}, "dense": 0.95, "bm25": 9.0, "fused": 0.02, "coverage": 1.0},
        {"row": 1, "chunk": {"chunk_id": "clean", "chunk_text": clean, "data_quality_status": "PASS"}, "dense": 0.81, "bm25": 4.0, "fused": 0.01, "coverage": 1.0},
    ]
    selected, evaluated = select_best_evidence(
        candidates,
        analysis,
        "fr",
        "PCA/PCI banque continuité d'activité",
        EvidenceQualityEvaluator(CONFIG["evidence_quality"]),
        CONFIG["meaningful_terms"],
        CONFIG["evidence_quality"],
    )
    assert selected[0]["chunk"]["chunk_id"] == "clean"
    assert not next(item for item in evaluated if item["chunk"]["chunk_id"] == "noisy")["quality"].quality_pass


def test_reference_has_no_selected_evidence_when_every_chunk_is_unusable() -> None:
    query = "PCA banque"
    analysis = _analysis(query, "PCA banque")
    candidates = [
        {"row": 0, "chunk": {"chunk_id": "bad", "chunk_text": "P\nC\nA\n1\n2", "data_quality_status": "REVIEW"}, "dense": 0.99, "bm25": 10.0, "fused": 0.02, "coverage": 0.0},
    ]
    selected, _ = select_best_evidence(
        candidates,
        analysis,
        "fr",
        "PCA/PCI banque",
        EvidenceQualityEvaluator(CONFIG["evidence_quality"]),
        CONFIG["meaningful_terms"],
        CONFIG["evidence_quality"],
    )
    assert selected == []


def test_retrieval_only_chunk_is_never_selected_for_display() -> None:
    query = "PCA banque"
    evidence = "Objet du contrat : réalisation d'une mission PCA complète pour une banque avec tests de continuité."
    analysis = _analysis(query, evidence)
    candidates = [
        {
            "row": 0,
            "chunk": {
                "chunk_id": "retrieval-only",
                "chunk_text": evidence,
                "data_quality_status": "PASS",
                "approved_for_display": False,
            },
            "dense": 0.95,
            "bm25": 9.0,
            "fused": 0.02,
            "coverage": 1.0,
        }
    ]
    selected, evaluated = select_best_evidence(
        candidates,
        analysis,
        "fr",
        "PCA/PCI banque",
        EvidenceQualityEvaluator(CONFIG["evidence_quality"]),
        CONFIG["meaningful_terms"],
        CONFIG["evidence_quality"],
    )
    assert selected == []
    assert evaluated == []


def test_frontend_renders_only_api_display_passage() -> None:
    component = (ROOT / "app/frontend/components/ResultCard.tsx").read_text(encoding="utf-8")
    assert "{passage.text}" in component
    assert "retrieval_text" not in component
    assert 'dir="auto"' in component
    assert "diagnostics" not in component
