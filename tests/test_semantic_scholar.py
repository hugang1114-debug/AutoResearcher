from autoresearcher.clients.semantic_scholar import parse_semantic_scholar_response


def test_parse_semantic_scholar_response_normalizes_metadata():
    payload = {
        "data": [
            {
                "paperId": "abc123",
                "title": "RAG Evaluation",
                "authors": [{"name": "Ada Lovelace"}],
                "abstract": "A paper about evaluation.",
                "url": "https://www.semanticscholar.org/paper/abc123",
                "year": 2024,
                "citationCount": 42,
                "venue": "TestConf",
                "externalIds": {"DOI": "10.1000/example", "ArXiv": "2401.00001"},
                "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                "publicationDate": "2024-01-01",
            }
        ]
    }

    papers = parse_semantic_scholar_response(payload)

    assert len(papers) == 1
    assert papers[0].source == "semantic_scholar"
    assert papers[0].paper_id == "abc123"
    assert papers[0].doi == "10.1000/example"
    assert papers[0].arxiv_id == "2401.00001"
    assert papers[0].citation_count == 42
    assert papers[0].pdf_url == "https://example.com/paper.pdf"
