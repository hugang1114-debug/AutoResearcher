from autoresearcher.dedupe import deduplicate_papers
from autoresearcher.models import PaperMetadata
from autoresearcher.ranking import rank_papers


def test_deduplicate_papers_prefers_richer_record():
    sparse = PaperMetadata(
        title="RAG Evaluation",
        source="arxiv",
        arxiv_id="2401.00001v1",
        url="https://arxiv.org/abs/2401.00001v1",
    )
    rich = PaperMetadata(
        title="RAG Evaluation",
        source="semantic_scholar",
        arxiv_id="2401.00001",
        abstract="A detailed abstract.",
        authors=["Ada"],
        citation_count=12,
    )

    unique = deduplicate_papers([sparse, rich])

    assert len(unique) == 1
    assert unique[0].source == "semantic_scholar"
    assert unique[0].abstract == "A detailed abstract."


def test_deduplicate_papers_matches_normalized_title_when_ids_differ():
    first = PaperMetadata(
        title="RAG: Evaluation!",
        source="arxiv",
        paper_id="a1",
    )
    second = PaperMetadata(
        title="rag evaluation",
        source="semantic_scholar",
        paper_id="s1",
        abstract="Richer metadata.",
    )

    unique = deduplicate_papers([first, second])

    assert len(unique) == 1
    assert unique[0].source == "semantic_scholar"


def test_rank_papers_uses_topic_overlap():
    on_topic = PaperMetadata(
        title="Retrieval Augmented Generation Evaluation",
        abstract="Evaluation for retrieval augmented generation systems.",
        year=2024,
    )
    off_topic = PaperMetadata(
        title="Graph Coloring",
        abstract="A combinatorial optimization method.",
        year=2024,
    )

    ranked = rank_papers("retrieval augmented generation evaluation", [off_topic, on_topic])

    assert ranked[0].title == "Retrieval Augmented Generation Evaluation"
    assert ranked[0].relevance_score > ranked[1].relevance_score
