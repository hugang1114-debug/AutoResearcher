from autoresearcher.clients.arxiv import parse_arxiv_response


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <updated>2024-01-02T00:00:00Z</updated>
    <published>2024-01-01T00:00:00Z</published>
    <title>Retrieval Augmented Generation Evaluation</title>
    <summary> We evaluate RAG systems. </summary>
    <author><name>Ada Lovelace</name></author>
    <arxiv:doi>10.1000/example</arxiv:doi>
    <link href="http://arxiv.org/pdf/2401.00001v1" title="pdf" />
  </entry>
</feed>
"""


def test_parse_arxiv_response_normalizes_metadata():
    papers = parse_arxiv_response(ARXIV_XML)

    assert len(papers) == 1
    assert papers[0].title == "Retrieval Augmented Generation Evaluation"
    assert papers[0].authors == ["Ada Lovelace"]
    assert papers[0].arxiv_id == "2401.00001v1"
    assert papers[0].doi == "10.1000/example"
    assert papers[0].year == 2024
    assert papers[0].pdf_url == "http://arxiv.org/pdf/2401.00001v1"
