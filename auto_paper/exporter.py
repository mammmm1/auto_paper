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
                f"- 推荐理由：{paper['recommendation_reason']}",
                f"- 作者：{paper['authors']}",
                f"- 发布时间：{paper['published_at']}",
                f"- 论文链接：{paper['entry_url']}",
                f"- PDF：{paper['pdf_url']}",
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
        "recommendation_reason",
        "summary",
        "entry_url",
        "pdf_url",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for paper in papers:
        writer.writerow({field: paper.get(field, "") for field in fieldnames})
    return output.getvalue()

