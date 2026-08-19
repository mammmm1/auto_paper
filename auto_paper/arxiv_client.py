from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass(frozen=True)
class PaperCandidate:
    external_id: str
    title: str
    authors: str
    abstract: str
    published_at: str
    updated_at: str
    pdf_url: str
    entry_url: str


def search_arxiv(query: str, max_results: int = 10) -> list[PaperCandidate]:
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max(1, min(max_results, 50)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(
        f"{ARXIV_API_URL}?{params}",
        headers={"User-Agent": "auto_paper/0.1 (+https://github.com/mammmm1/auto_paper)"},
    )
    data = _read_url(request)

    root = ET.fromstring(data)
    papers: list[PaperCandidate] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = _text(entry, "atom:id")
        pdf_url = _find_pdf_url(entry)
        papers.append(
            PaperCandidate(
                external_id=entry_id.rsplit("/", 1)[-1],
                title=_clean(_text(entry, "atom:title")),
                authors=", ".join(
                    _clean(author.findtext("atom:name", default="", namespaces=ATOM_NS))
                    for author in entry.findall("atom:author", ATOM_NS)
                ),
                abstract=_clean(_text(entry, "atom:summary")),
                published_at=_text(entry, "atom:published"),
                updated_at=_text(entry, "atom:updated"),
                pdf_url=pdf_url,
                entry_url=entry_id,
            )
        )
    return papers


def _text(entry: ET.Element, path: str) -> str:
    return entry.findtext(path, default="", namespaces=ATOM_NS).strip()


def _clean(value: str) -> str:
    return " ".join(value.split())


def _find_pdf_url(entry: ET.Element) -> str:
    for link in entry.findall("atom:link", ATOM_NS):
        if link.attrib.get("title") == "pdf":
            return link.attrib.get("href", "")
    return ""


def _read_url(request: urllib.request.Request) -> bytes:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except urllib.error.URLError as exc:
            last_error = exc
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                try:
                    # arXiv metadata is public. Some Windows Python installs lack
                    # CA roots, so retry without verification only for this case.
                    context = ssl._create_unverified_context()
                    with urllib.request.urlopen(request, timeout=25, context=context) as response:
                        return response.read()
                except (urllib.error.URLError, TimeoutError) as fallback_exc:
                    last_error = fallback_exc
        except TimeoutError as exc:
            last_error = exc

        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise RuntimeError("arXiv request failed without an error")
