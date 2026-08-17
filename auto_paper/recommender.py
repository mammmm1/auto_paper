from __future__ import annotations

from datetime import datetime, timezone
import re


def score_paper(title: str, abstract: str, query: str, published_at: str) -> tuple[float, str]:
    text = f"{title} {abstract}".lower()
    keywords = _keywords(query)
    keyword_hits = [word for word in keywords if word in text]
    keyword_score = min(len(keyword_hits) / max(len(keywords), 1), 1.0) * 55

    freshness_score = _freshness_score(published_at)
    signal_score = _signal_score(text)
    score = round(min(keyword_score + freshness_score + signal_score, 100), 1)

    reasons = []
    if keyword_hits:
        reasons.append(f"命中关键词：{', '.join(keyword_hits[:5])}")
    if freshness_score >= 20:
        reasons.append("近期发布")
    if signal_score >= 12:
        reasons.append("摘要中包含方法、基准或数据集等可复用信号")
    if not reasons:
        reasons.append("与主题存在弱相关，可作为补充阅读")
    return score, "；".join(reasons)


def _keywords(query: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", query.lower())
    operators = {"and", "cat", "not", "or"}
    return {word for word in words if word not in operators}


def _freshness_score(published_at: str) -> float:
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 10
    days = (datetime.now(timezone.utc) - published).days
    if days <= 7:
        return 30
    if days <= 30:
        return 22
    if days <= 90:
        return 12
    return 5


def _signal_score(text: str) -> float:
    signals = ["benchmark", "dataset", "code", "framework", "state-of-the-art", "evaluation"]
    return min(sum(1 for signal in signals if signal in text) * 4, 15)

