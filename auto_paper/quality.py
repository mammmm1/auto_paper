from __future__ import annotations

from collections import defaultdict
from typing import Any


POSITIVE_FEEDBACK = {"useful", "stitchable"}
LABELED_FEEDBACK = POSITIVE_FEEDBACK | {"irrelevant"}


def rank_materials(
    materials: list[dict[str, Any]],
    use_feedback: bool = True,
) -> list[dict[str, Any]]:
    preferences = _feedback_preferences(materials) if use_feedback else _empty_preferences()
    ranked: list[dict[str, Any]] = []

    for material in materials:
        item = dict(material)
        stitchability = float(item.get("stitchability_score") or 0)
        relevance = float(item.get("relevance_score") or 0)
        code = float(item.get("code_availability_score") or 0)
        base_score = stitchability * 0.65 + relevance * 0.25 + code * 0.10

        tier = str(item.get("relevance_tier") or "reference")
        tier_bonus = {
            "direct": 8.0,
            "transferable": 3.0,
            "reference": -8.0,
            "irrelevant": -25.0,
        }.get(tier, -8.0)
        difficulty_bonus = {"低": 4.0, "中": 1.5, "高": 0.0}.get(
            str(item.get("stitch_difficulty") or "中"),
            0.0,
        )
        learned_bonus = _learned_bonus(item, preferences)
        feedback = str(item.get("user_feedback") or "")
        direct_feedback_bonus = {
            "useful": 10.0,
            "stitchable": 15.0,
            "irrelevant": -60.0,
        }.get(feedback, 0.0) if use_feedback else 0.0

        adjustment = tier_bonus + difficulty_bonus + learned_bonus + direct_feedback_bonus
        item["feedback_adjustment"] = round(adjustment, 1)
        item["ranking_score"] = round(max(0, min(base_score + adjustment, 100)), 1)
        item["ranking_reason"] = _ranking_reason(
            tier,
            learned_bonus,
            feedback if use_feedback else "",
            difficulty_bonus,
        )
        ranked.append(item)

    return sorted(
        ranked,
        key=lambda item: (
            float(item.get("ranking_score") or 0),
            float(item.get("stitchability_score") or 0),
            str(item.get("published_at") or ""),
        ),
        reverse=True,
    )


def build_quality_metrics(materials: list[dict[str, Any]], top_n: int = 10) -> dict[str, Any]:
    personalized = rank_materials(materials)
    visible = [item for item in personalized if _is_effectively_relevant(item)]
    recommendation_top = visible[:top_n]
    system_ranked = rank_materials(materials, use_feedback=False)
    evaluation_top = [item for item in system_ranked if bool(item.get("is_relevant"))][:top_n]
    labeled = [item for item in evaluation_top if item.get("user_feedback") in LABELED_FEEDBACK]
    positive = [item for item in labeled if item.get("user_feedback") in POSITIVE_FEEDBACK]
    irrelevant = [item for item in labeled if item.get("user_feedback") == "irrelevant"]
    tier_counts: dict[str, int] = defaultdict(int)
    for item in system_ranked:
        tier_counts[str(item.get("relevance_tier") or "reference")] += 1

    label_coverage = round(len(labeled) / len(evaluation_top) * 100, 1) if evaluation_top else 0.0
    useful_rate = round(len(positive) / len(labeled) * 100, 1) if labeled else None
    positive_target = min(7, len(evaluation_top))
    if len(labeled) < positive_target:
        status = "collecting"
    elif len(positive) >= positive_target and len(irrelevant) <= 2:
        status = "on_track"
    else:
        status = "needs_work"

    return {
        "top_n": len(evaluation_top),
        "top_material_ids": [item["id"] for item in recommendation_top],
        "evaluation_material_ids": [item["id"] for item in evaluation_top],
        "labeled_count": len(labeled),
        "positive_count": len(positive),
        "irrelevant_count": len(irrelevant),
        "remaining_labels": max(0, len(evaluation_top) - len(labeled)),
        "label_coverage": label_coverage,
        "useful_rate": useful_rate,
        "status": status,
        "targets": {
            "positive_min": positive_target,
            "irrelevant_max": 2,
        },
        "tier_counts": dict(tier_counts),
    }


def _feedback_preferences(materials: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    preferences = _empty_preferences()
    for item in materials:
        feedback = str(item.get("user_feedback") or "")
        weight = {"useful": 1.0, "stitchable": 1.5, "irrelevant": -1.5}.get(feedback, 0.0)
        if not weight:
            continue
        preferences["area"][str(item.get("integration_area") or "")] += weight
        preferences["type"][str(item.get("material_type") or "")] += weight
        preferences["subtag"][str(item.get("integration_subtag") or "")] += weight
    return preferences


def _empty_preferences() -> dict[str, dict[str, float]]:
    return {
        "area": defaultdict(float),
        "type": defaultdict(float),
        "subtag": defaultdict(float),
    }


def _learned_bonus(
    material: dict[str, Any],
    preferences: dict[str, dict[str, float]],
) -> float:
    bonus = (
        preferences["area"].get(str(material.get("integration_area") or ""), 0.0) * 2.0
        + preferences["type"].get(str(material.get("material_type") or ""), 0.0) * 1.2
        + preferences["subtag"].get(str(material.get("integration_subtag") or ""), 0.0) * 0.8
    )
    return round(max(-12.0, min(bonus, 12.0)), 1)


def _ranking_reason(
    tier: str,
    learned_bonus: float,
    feedback: str,
    difficulty_bonus: float,
) -> str:
    tier_label = {
        "direct": "直接相关",
        "transferable": "跨领域可迁移",
        "reference": "仅供参考",
        "irrelevant": "不相关",
    }.get(tier, "待判断")
    reasons = [tier_label]
    if feedback == "useful":
        reasons.append("你已标记有用")
    elif feedback == "stitchable":
        reasons.append("你已标记可缝合")
    elif feedback == "irrelevant":
        reasons.append("你已标记不相关")
    elif learned_bonus > 0:
        reasons.append("同类素材获得过正向反馈")
    elif learned_bonus < 0:
        reasons.append("同类素材出现过负向反馈")
    if difficulty_bonus >= 4:
        reasons.append("改造成本较低")
    return "；".join(reasons)


def _is_effectively_relevant(material: dict[str, Any]) -> bool:
    feedback = str(material.get("user_feedback") or "")
    if feedback in POSITIVE_FEEDBACK:
        return True
    if feedback == "irrelevant":
        return False
    return bool(material.get("is_relevant"))
