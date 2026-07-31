from retrieval.language import analyze_language
from retrieval.normalization import normalize_search_text


def test_french_english_arabic_and_mixed_detection() -> None:
    french = analyze_language("Références de sécurité pour une banque")
    english = analyze_language("Cloud strategy for a bank")
    arabic = analyze_language("مراجع حول استمرارية الأعمال للبنوك")
    mixed = analyze_language("PCA للبنوك en Tunisie")

    assert french.detected_language == "fr"
    assert english.detected_language == "en"
    assert arabic.detected_language == "ar" and arabic.rtl
    assert mixed.detected_language == "mixed" and mixed.mixed_script
    assert mixed.scripts == ["Latin", "Arabic"]


def test_arabic_normalization_is_retrieval_only_and_non_destructive() -> None:
    original = "أعمال وإستراتيجية"
    normalized = normalize_search_text(original)
    assert original == "أعمال وإستراتيجية"
    assert normalized == "اعمال واستراتيجية"
