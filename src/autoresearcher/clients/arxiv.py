from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from autoresearcher.models import PaperMetadata

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def search_arxiv(query: str, limit: int = 10, timeout: float = 20.0) -> list[PaperMetadata]:
    """Search arXiv and return normalized paper metadata."""
    params = urllib.parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(
        f"{ARXIV_API_URL}?{params}",
        headers={"User-Agent": "AutoResearcher/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8")
    return parse_arxiv_response(xml_text)


def parse_arxiv_response(xml_text: str) -> list[PaperMetadata]:
    """Parse the arXiv Atom API response."""
    root = ET.fromstring(xml_text)
    papers: list[PaperMetadata] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        title = _clean_text(_entry_text(entry, "atom:title"))
        abstract = _clean_text(_entry_text(entry, "atom:summary"))
        url = _entry_text(entry, "atom:id").strip()
        published_at = _entry_text(entry, "atom:published").strip() or None
        authors = [
            _clean_text(name.text or "")
            for name in entry.findall("atom:author/atom:name", ATOM_NS)
            if name.text
        ]
        doi_node = entry.find(f"{ARXIV_NS}doi")
        doi = _clean_text(doi_node.text or "") if doi_node is not None else None
        arxiv_id = _extract_arxiv_id(url)
        pdf_url = _find_pdf_url(entry)
        papers.append(
            PaperMetadata(
                title=title,
                authors=authors,
                abstract=abstract,
                url=url,
                source="arxiv",
                paper_id=arxiv_id,
                doi=doi or None,
                arxiv_id=arxiv_id,
                published_at=published_at,
                year=_extract_year(published_at),
                pdf_url=pdf_url,
            )
        )
    return papers


def _entry_text(entry: ET.Element, path: str) -> str:
    node = entry.find(path, ATOM_NS)
    return node.text if node is not None and node.text else ""


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d{4})", value)
    return int(match.group(1)) if match else None


def _extract_arxiv_id(url: str) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1]


def _find_pdf_url(entry: ET.Element) -> str | None:
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            return link.attrib.get("href")
    return None
