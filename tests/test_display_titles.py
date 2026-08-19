from retrieval.service import RetrievalService


def test_display_title_uses_the_first_meaningful_source_clause() -> None:
    title = (
        "Opérationnalisation du PCA de la BCT Phase 1 • Mise en place du PCA "
        "• Réalisation des ateliers et procédures"
    )
    assert RetrievalService._display_title(title, "BCT") == "Opérationnalisation du PCA de la BCT Phase 1"


def test_display_title_is_deterministic_short_and_separate_from_source_copy() -> None:
    source = "Mission de transformation et accompagnement " + "stratégique " * 30
    first = RetrievalService._display_title(source, "Client")
    second = RetrievalService._display_title(source, "Client")
    assert first == second
    assert len(first) <= 96
    assert source.startswith(first)
    assert source != first


def test_display_title_has_a_safe_source_based_fallback() -> None:
    assert RetrievalService._display_title("", "Orange Bank") == "Orange Bank"
