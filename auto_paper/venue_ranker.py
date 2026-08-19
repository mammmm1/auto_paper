from __future__ import annotations

import json
import re
from typing import Any


CCF_SOURCE_URL = "https://www.ccf.org.cn/Academic_Evaluation/By_category/"
IEEE_JCR_SOURCE_URL = (
    "https://open.ieee.org/wp-content/uploads/IEEE-Title-List-August-2025-CAPES.pdf"
)
REMOTE_SENSING_JCR_SOURCE_URL = "https://www.mdpi.com/journal/remotesensing/stats"


def _ccf(rank: str) -> dict[str, str]:
    return {
        "system": "CCF",
        "rank": rank,
        "label": f"CCF {rank}",
        "year": "2026",
        "source_url": CCF_SOURCE_URL,
    }


def _jcr(
    rank: str,
    *,
    year: str = "2024",
    source_url: str = IEEE_JCR_SOURCE_URL,
    category: str = "",
) -> dict[str, str]:
    result = {
        "system": "JCR",
        "index": "SCIE",
        "rank": rank,
        "label": f"JCR {rank}",
        "year": year,
        "source_url": source_url,
    }
    if category:
        result["category"] = category
    return result


def _venue(
    name: str,
    venue_type: str,
    aliases: tuple[str, ...],
    rankings: tuple[dict[str, str], ...] = (),
) -> dict[str, Any]:
    return {
        "name": name,
        "type": venue_type,
        "aliases": aliases,
        "rankings": rankings,
    }


# The catalog intentionally stays compact and conservative. A missing rank is
# preferable to assigning a paper to the wrong venue or ranking system.
VENUE_CATALOG = (
    _venue("CVPR", "conference", ("CVPR", "Computer Vision and Pattern Recognition"), (_ccf("A"),)),
    _venue("ICCV", "conference", ("ICCV", "International Conference on Computer Vision"), (_ccf("A"),)),
    _venue("NeurIPS", "conference", ("NeurIPS", "NIPS", "Neural Information Processing Systems"), (_ccf("A"),)),
    _venue("AAAI", "conference", ("AAAI", "AAAI Conference on Artificial Intelligence"), (_ccf("A"),)),
    _venue("ICML", "conference", ("ICML", "International Conference on Machine Learning"), (_ccf("A"),)),
    _venue("IJCAI", "conference", ("IJCAI", "International Joint Conference on Artificial Intelligence"), (_ccf("A"),)),
    _venue("ACL", "conference", ("ACL", "Annual Meeting of the Association for Computational Linguistics"), (_ccf("A"),)),
    _venue("ACM MM", "conference", ("ACM MM", "ACM Multimedia", "ACM International Conference on Multimedia"), (_ccf("A"),)),
    _venue("SIGGRAPH", "conference", ("SIGGRAPH", "ACM SIGGRAPH"), (_ccf("A"),)),
    _venue("ECCV", "conference", ("ECCV", "European Conference on Computer Vision"), (_ccf("B"),)),
    _venue("EMNLP", "conference", ("EMNLP", "Empirical Methods in Natural Language Processing"), (_ccf("B"),)),
    _venue("ICRA", "conference", ("ICRA", "International Conference on Robotics and Automation"), (_ccf("B"),)),
    _venue("COLT", "conference", ("COLT", "Conference on Learning Theory"), (_ccf("B"),)),
    _venue("ECAI", "conference", ("ECAI", "European Conference on Artificial Intelligence"), (_ccf("B"),)),
    _venue("ICAPS", "conference", ("ICAPS", "International Conference on Automated Planning and Scheduling"), (_ccf("B"),)),
    _venue("COLING", "conference", ("COLING", "International Conference on Computational Linguistics"), (_ccf("B"),)),
    _venue("UAI", "conference", ("UAI", "Conference on Uncertainty in Artificial Intelligence"), (_ccf("B"),)),
    _venue("AAMAS", "conference", ("AAMAS", "Autonomous Agents and Multi-agent Systems"), (_ccf("B"),)),
    _venue("NAACL", "conference", ("NAACL", "North American Chapter of the Association for Computational Linguistics"), (_ccf("B"),)),
    _venue("AISTATS", "conference", ("AISTATS", "Artificial Intelligence and Statistics"), (_ccf("C"),)),
    _venue("ACCV", "conference", ("ACCV", "Asian Conference on Computer Vision"), (_ccf("C"),)),
    _venue("ACML", "conference", ("ACML", "Asian Conference on Machine Learning"), (_ccf("C"),)),
    _venue("BMVC", "conference", ("BMVC", "British Machine Vision Conference"), (_ccf("C"),)),
    _venue("IROS", "conference", ("IROS", "Intelligent Robots and Systems"), (_ccf("C"),)),
    _venue("IGARSS", "conference", ("IGARSS", "International Geoscience and Remote Sensing Symposium")),
    _venue(
        "IEEE TPAMI",
        "journal",
        ("IEEE TPAMI", "TPAMI", "Transactions on Pattern Analysis and Machine Intelligence"),
        (_ccf("A"), _jcr("Q1")),
    ),
    _venue("IJCV", "journal", ("IJCV", "International Journal of Computer Vision"), (_ccf("A"),)),
    _venue("AIJ", "journal", ("AIJ", "Artificial Intelligence Journal", "Artificial Intelligence"), (_ccf("A"),)),
    _venue("JMLR", "journal", ("JMLR", "Journal of Machine Learning Research"), (_ccf("A"),)),
    _venue(
        "IEEE TIP",
        "journal",
        ("IEEE TIP", "Transactions on Image Processing"),
        (_ccf("A"), _jcr("Q1")),
    ),
    _venue(
        "IEEE TMM",
        "journal",
        ("IEEE TMM", "Transactions on Multimedia"),
        (_ccf("A"), _jcr("Q1")),
    ),
    _venue(
        "IEEE TVCG",
        "journal",
        ("IEEE TVCG", "Transactions on Visualization and Computer Graphics"),
        (_ccf("A"), _jcr("Q1")),
    ),
    _venue("Pattern Recognition", "journal", ("Pattern Recognition",), (_ccf("B"),)),
    _venue(
        "IEEE TNNLS",
        "journal",
        ("IEEE TNNLS", "Transactions on Neural Networks and Learning Systems"),
        (_ccf("B"), _jcr("Q1")),
    ),
    _venue(
        "IEEE TGRS",
        "journal",
        ("IEEE TGRS", "Transactions on Geoscience and Remote Sensing"),
        (_jcr("Q1"),),
    ),
    _venue(
        "Remote Sensing",
        "journal",
        ("Remote Sensing",),
        (
            _jcr(
                "Q1",
                year="2025",
                source_url=REMOTE_SENSING_JCR_SOURCE_URL,
                category="Geosciences, Multidisciplinary",
            ),
        ),
    ),
    _venue(
        "IEEE JSTARS",
        "journal",
        ("IEEE JSTARS", "Journal of Selected Topics in Applied Earth Observations and Remote Sensing"),
    ),
    _venue(
        "IEEE GRSL",
        "journal",
        ("IEEE GRSL", "Geoscience and Remote Sensing Letters"),
    ),
    _venue(
        "ISPRS Journal of Photogrammetry and Remote Sensing",
        "journal",
        ("ISPRS Journal of Photogrammetry and Remote Sensing", "ISPRS JPRS"),
    ),
    _venue(
        "Remote Sensing of Environment",
        "journal",
        ("Remote Sensing of Environment",),
    ),
)


def resolve_venue(journal_ref: str = "", comment: str = "", doi: str = "") -> dict[str, str]:
    journal_ref = _clean(journal_ref)
    comment = _clean(comment)
    doi = _clean(doi)

    declared = _extract_declared_venue(comment)
    matched = _match_catalog(journal_ref) if journal_ref else None
    source = "arXiv journal_ref" if matched else ""
    status = "published" if matched else ""

    if matched is None and declared:
        matched = _match_catalog(declared)
        if matched is not None:
            source = "arXiv comment"
            status = "accepted"

    if matched is not None:
        rankings = [dict(item) for item in matched["rankings"]]
        return _result(
            name=str(matched["name"]),
            venue_type=str(matched["type"]),
            status=status,
            source=source,
            rankings=rankings,
            journal_ref=journal_ref,
            comment=comment,
            doi=doi,
        )

    if journal_ref:
        return _result(
            name=_trim_reference(journal_ref),
            venue_type=_guess_type(journal_ref),
            status="published",
            source="arXiv journal_ref",
            rankings=[],
            journal_ref=journal_ref,
            comment=comment,
            doi=doi,
        )

    if declared:
        return _result(
            name=declared,
            venue_type=_guess_type(declared),
            status="accepted",
            source="arXiv comment",
            rankings=[],
            journal_ref=journal_ref,
            comment=comment,
            doi=doi,
        )

    return _result(
        name="arXiv",
        venue_type="preprint",
        status="preprint",
        source="arXiv",
        rankings=[],
        journal_ref=journal_ref,
        comment=comment,
        doi=doi,
    )


def _result(
    *,
    name: str,
    venue_type: str,
    status: str,
    source: str,
    rankings: list[dict[str, str]],
    journal_ref: str,
    comment: str,
    doi: str,
) -> dict[str, str]:
    return {
        "venue_name": name,
        "venue_type": venue_type,
        "venue_rank": " / ".join(item["label"] for item in rankings),
        "venue_rankings_json": json.dumps(rankings, ensure_ascii=False),
        "venue_source": source,
        "venue_status": status,
        "doi": doi,
        "journal_ref": journal_ref,
        "comments": comment,
    }


def _match_catalog(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for venue in VENUE_CATALOG:
        for alias in venue["aliases"]:
            if _contains_alias(text, alias):
                candidates.append((len(alias), venue))
                break
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _contains_alias(text: str, alias: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _extract_declared_venue(comment: str) -> str:
    if not comment:
        return ""
    patterns = (
        r"(?:accepted|to appear|published)\s+(?:at|to|in|by|for)\s+([^.;]{2,90})",
        r"(?:oral|spotlight)\s+(?:at|in)\s+([^.;]{2,90})",
    )
    for pattern in patterns:
        match = re.search(pattern, comment, flags=re.IGNORECASE)
        if match:
            return _trim_reference(match.group(1))
    return ""


def _guess_type(value: str) -> str:
    lowered = value.lower()
    if any(term in lowered for term in ("conference", "proceedings", "workshop", "symposium")):
        return "conference"
    return "journal"


def _trim_reference(value: str) -> str:
    cleaned = _clean(value).strip(" ,;:-")
    return cleaned if len(cleaned) <= 120 else f"{cleaned[:117]}..."


def _clean(value: str) -> str:
    return " ".join(str(value or "").split())
