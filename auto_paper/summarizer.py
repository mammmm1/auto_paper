from __future__ import annotations

import re


METHOD_WORDS = {
    "benchmark",
    "dataset",
    "framework",
    "model",
    "method",
    "pipeline",
    "training",
}


def summarize_paper(title: str, abstract: str, query: str) -> str:
    sentences = _split_sentences(abstract)
    if not sentences:
        return title

    keywords = _keywords(f"{title} {query}")
    ranked = sorted(
        sentences,
        key=lambda sentence: _sentence_score(sentence, keywords),
        reverse=True,
    )
    selected = ranked[:2]
    contribution = _best_sentence(sentences, {"propose", "present", "introduce", "show", "demonstrate"})
    method = _best_sentence(sentences, METHOD_WORDS)

    parts = []
    if contribution:
        parts.append(f"核心贡献：{contribution}")
    if method and method != contribution:
        parts.append(f"方法线索：{method}")
    if not parts:
        parts = [f"摘要要点：{sentence}" for sentence in selected]
    return "\n".join(parts)


def _split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    pieces = re.split(r"(?<=[.!?])\s+", normalized)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 20]


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    stopwords = {
        "and",
        "are",
        "for",
        "from",
        "large",
        "model",
        "paper",
        "that",
        "the",
        "this",
        "with",
    }
    return {word for word in words if word not in stopwords}


def _sentence_score(sentence: str, keywords: set[str]) -> int:
    lowered = sentence.lower()
    score = sum(1 for keyword in keywords if keyword in lowered)
    score += sum(1 for word in METHOD_WORDS if word in lowered)
    return score


def _best_sentence(sentences: list[str], signals: set[str]) -> str:
    for sentence in sentences:
        lowered = sentence.lower()
        if any(signal in lowered for signal in signals):
            return sentence
    return ""

