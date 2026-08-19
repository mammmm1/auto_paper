from __future__ import annotations

from typing import Any


DETECTION_TERMS = (
    "目标检测",
    "object detection",
    "detection head",
    "detector",
    "bounding box",
    "bbox",
)
SEGMENTATION_TERMS = (
    "语义分割",
    "实例分割",
    "semantic segmentation",
    "instance segmentation",
    "segmentation head",
    "mask head",
)


def validate_project_profile(project: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    score = 100

    required_fields = {
        "name": ("项目名称", 15),
        "task_type": ("任务类型", 20),
        "idea": ("当前 idea", 25),
    }
    missing_required = 0
    for field, (label, penalty) in required_fields.items():
        if str(project.get(field) or "").strip():
            continue
        missing_required += 1
        score -= penalty
        issues.append(
            {
                "severity": "error",
                "code": f"missing_{field}",
                "fields": [field],
                "message": f"{label}尚未填写，分析结果缺少稳定锚点。",
                "suggestion": f"先补充{label}，再运行论文搜索或深度分析。",
            }
        )

    for field, label in {
        "domain": "研究领域",
        "keywords": "关键词",
        "backbone": "Backbone",
        "neck": "Neck",
        "head": "Head",
        "dataset": "Dataset",
    }.items():
        if str(project.get(field) or "").strip():
            continue
        score -= 4
        issues.append(
            {
                "severity": "info",
                "code": f"missing_{field}",
                "fields": [field],
                "message": f"{label}未填写，接入建议会更偏通用。",
                "suggestion": f"补充{label}可提高接口和实验建议的具体程度。",
            }
        )

    task_type = str(project.get("task_type") or "").strip().lower()
    supporting_text = " ".join(
        str(project.get(field) or "")
        for field in ("idea", "keywords", "head")
    ).lower()
    task_is_segmentation = _contains_any(task_type, SEGMENTATION_TERMS)
    task_is_detection = _contains_any(task_type, DETECTION_TERMS)
    content_has_detection = _contains_any(supporting_text, DETECTION_TERMS)
    content_has_segmentation = _contains_any(supporting_text, SEGMENTATION_TERMS)

    if task_is_segmentation and content_has_detection:
        score -= 24
        issues.append(
            {
                "severity": "warning",
                "code": "task_idea_mismatch",
                "fields": ["task_type", "idea", "head"],
                "message": "任务类型是分割，但 idea 或 Head 描述的是目标检测。",
                "suggestion": "确认主任务：若做检测，将任务类型改为目标检测；若做分割，请改写 idea 和 Head。",
            }
        )
    elif task_is_detection and content_has_segmentation:
        score -= 24
        issues.append(
            {
                "severity": "warning",
                "code": "task_idea_mismatch",
                "fields": ["task_type", "idea", "head"],
                "message": "任务类型是目标检测，但 idea 或 Head 描述的是分割。",
                "suggestion": "统一任务类型、研究假设和输出 Head，避免检索结果偏向错误任务。",
            }
        )

    if task_type and not task_is_detection and not task_is_segmentation:
        issues.append(
            {
                "severity": "info",
                "code": "custom_task_type",
                "fields": ["task_type"],
                "message": "当前任务类型未命中内置检测/分割词表，将按自由文本理解。",
                "suggestion": "在关键词和 idea 中补充常用中英文任务名称。",
            }
        )

    status = "ready"
    if missing_required >= 2:
        status = "blocked"
    elif any(issue["severity"] in {"error", "warning"} for issue in issues):
        status = "warning"

    return {
        "status": status,
        "readiness_score": max(0, score),
        "summary": _summary(status),
        "issues": issues,
    }


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _summary(status: str) -> str:
    if status == "blocked":
        return "画像缺少关键字段，建议补充后再分析。"
    if status == "warning":
        return "画像可以使用，但存在会影响检索和缝合判断的问题。"
    return "画像逻辑一致，可以进入搜索与深度分析。"
