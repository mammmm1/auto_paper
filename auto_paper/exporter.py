from __future__ import annotations

import csv
import io
import json
from typing import Any


def papers_to_markdown(papers: list[dict]) -> str:
    lines = ["# Auto Paper 推荐日报", ""]
    if not papers:
        return "# Auto Paper 推荐日报\n\n暂无论文。\n"

    current_topic = None
    for index, paper in enumerate(papers, start=1):
        full_text = _json_object(paper.get("full_text_json"))
        code = full_text.get("code") or {}
        code_urls = [str(item.get("url") or "") for item in code.get("urls", []) if item.get("url")]
        deep_analysis = _json_object(paper.get("deep_analysis_json"))
        if paper["topic_name"] != current_topic:
            current_topic = paper["topic_name"]
            lines.extend([f"## {current_topic}", ""])
        lines.extend(
            [
                f"### {index}. {paper['title']}",
                "",
                f"- 推荐分：{paper['recommendation_score']}",
                f"- 反馈重排分：{paper.get('ranking_score', 0)}",
                f"- 相关性等级：{paper.get('relevance_tier', '')}",
                f"- 可缝合度：{paper.get('stitchability_score', 0)}",
                f"- 相关性：{paper.get('relevance_score', 0)}",
                f"- 代码可用性：{paper.get('code_availability_score', 0)}",
                f"- 素材类型：{paper.get('material_type', '')}",
                f"- 可接入位置：{paper.get('integration_area', '')} > {paper.get('integration_subtag', '')}",
                f"- 接入难度：{paper.get('stitch_difficulty', '')}",
                f"- 缝合动作：{paper.get('stitch_action') or paper.get('recommendation_reason', '')}",
                f"- 证据来源：{paper.get('evidence_sources', '')}",
                f"- 全文核验：{paper.get('full_text_status', '') or '未核验'}",
                f"- 代码仓库状态：{code.get('status', 'not_found')}",
                f"- 代码仓库：{', '.join(code_urls) or '未发现'}",
                f"- 发表源：{paper.get('venue_name') or 'arXiv'}",
                f"- 发表类型：{_venue_type_label(paper.get('venue_type'))}",
                f"- 刊会等级：{paper.get('venue_rank') or '未定级'}",
                f"- 发表状态：{_venue_status_label(paper.get('venue_status'))}",
                f"- 元数据来源：{paper.get('venue_source') or 'arXiv'}",
                f"- DOI：{paper.get('doi') or '未提供'}",
                f"- 作者：{paper['authors']}",
                f"- 发布时间：{paper['published_at']}",
                f"- 论文链接：{paper['entry_url']}",
                f"- PDF：{paper['pdf_url']}",
                "",
                f"关键证据：{paper.get('evidence_quote', '')}",
                "",
                paper["summary"],
                "",
            ]
        )
        if full_text.get("sections"):
            lines.extend(["**全文证据**", ""])
            for section in full_text["sections"]:
                lines.append(
                    f"- {section.get('label', '正文')} · 第 {section.get('page', '?')} 页："
                    f"{_clip(section.get('text', ''), 360)}"
                )
            lines.append("")
        if deep_analysis:
            lines.extend(
                [
                    "**深度缝合分析**",
                    "",
                    f"- 可复用模块：{deep_analysis.get('reusable_module', '')}",
                    f"- 项目匹配：{deep_analysis.get('project_match', '')}",
                    f"- 置信度：{deep_analysis.get('confidence', 0)}/100",
                ]
            )
            for step_index, step in enumerate(deep_analysis.get("minimal_implementation", []), start=1):
                lines.append(f"  {step_index}. {step}")
            lines.extend(["", f"分析边界：{deep_analysis.get('limitations', '')}", ""])
    return "\n".join(lines)


def papers_to_csv(papers: list[dict]) -> str:
    output = io.StringIO()
    fieldnames = [
        "topic_name",
        "title",
        "authors",
        "published_at",
        "venue_name",
        "venue_type",
        "venue_rank",
        "venue_status",
        "venue_source",
        "venue_rankings_json",
        "doi",
        "journal_ref",
        "comments",
        "recommendation_score",
        "ranking_score",
        "ranking_reason",
        "feedback_adjustment",
        "relevance_tier",
        "relevance_score",
        "stitchability_score",
        "code_availability_score",
        "recommendation_reason",
        "material_type",
        "integration_area",
        "integration_subtag",
        "stitch_action",
        "stitch_difficulty",
        "evidence_sources",
        "evidence_quote",
        "full_text_status",
        "full_text_pages",
        "full_text_sections",
        "code_repository_status",
        "code_repository_urls",
        "deep_analysis_source",
        "deep_analysis_confidence",
        "deep_analysis_minimal_steps",
        "deep_analysis_limitations",
        "summary",
        "entry_url",
        "pdf_url",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for paper in papers:
        row = {field: paper.get(field, "") for field in fieldnames}
        full_text = _json_object(paper.get("full_text_json"))
        code = full_text.get("code") or {}
        deep_analysis = _json_object(paper.get("deep_analysis_json"))
        row.update(
            {
                "full_text_pages": (full_text.get("pdf") or {}).get("page_count", ""),
                "full_text_sections": " | ".join(
                    f"{item.get('label', '正文')} P{item.get('page', '?')}: {_clip(item.get('text', ''), 240)}"
                    for item in full_text.get("sections", [])
                ),
                "code_repository_status": code.get("status", ""),
                "code_repository_urls": " | ".join(
                    str(item.get("url") or "")
                    for item in code.get("urls", [])
                    if item.get("url")
                ),
                "deep_analysis_confidence": deep_analysis.get("confidence", ""),
                "deep_analysis_minimal_steps": " | ".join(
                    str(item) for item in deep_analysis.get("minimal_implementation", [])
                ),
                "deep_analysis_limitations": deep_analysis.get("limitations", ""),
            }
        )
        writer.writerow(row)
    return output.getvalue()


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _venue_type_label(value: Any) -> str:
    return {
        "conference": "会议",
        "journal": "期刊",
        "preprint": "预印本",
    }.get(str(value or ""), "未知")


def _venue_status_label(value: Any) -> str:
    return {
        "published": "已发表",
        "accepted": "已录用（作者声明）",
        "preprint": "预印本",
    }.get(str(value or ""), "待核验")
