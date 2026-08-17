from __future__ import annotations

import csv
import io


def papers_to_markdown(papers: list[dict]) -> str:
    lines = ["# Auto Paper 推荐日报", ""]
    if not papers:
        return "# Auto Paper 推荐日报\n\n暂无论文。\n"

    current_topic = None
    for index, paper in enumerate(papers, start=1):
        if paper["topic_name"] != current_topic:
            current_topic = paper["topic_name"]
            lines.extend([f"## {current_topic}", ""])
        lines.extend(
            [
                f"### {index}. {paper['title']}",
                "",
                f"- 推荐分：{paper['recommendation_score']}",
                f"- 可缝合度：{paper.get('stitchability_score', 0)}",
                f"- 相关性：{paper.get('relevance_score', 0)}",
                f"- 代码可用性：{paper.get('code_availability_score', 0)}",
                f"- 素材类型：{paper.get('material_type', '')}",
                f"- 可接入位置：{paper.get('integration_area', '')} > {paper.get('integration_subtag', '')}",
                f"- 接入难度：{paper.get('stitch_difficulty', '')}",
                f"- 缝合动作：{paper.get('stitch_action', paper['recommendation_reason'])}",
                f"- 证据来源：{paper.get('evidence_sources', '')}",
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
    return "\n".join(lines)


def papers_to_csv(papers: list[dict]) -> str:
    output = io.StringIO()
    fieldnames = [
        "topic_name",
        "title",
        "authors",
        "published_at",
        "recommendation_score",
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
        "summary",
        "entry_url",
        "pdf_url",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for paper in papers:
        writer.writerow({field: paper.get(field, "") for field in fieldnames})
    return output.getvalue()
