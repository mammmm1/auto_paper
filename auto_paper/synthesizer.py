from __future__ import annotations

import json
from typing import Any


AREA_ORDER = {
    "Data": 1,
    "Backbone": 2,
    "Neck": 3,
    "Head": 4,
    "Loss": 5,
    "Training": 6,
    "Experiment": 7,
}

DIFFICULTY_COST = {"low": 1, "medium": 2, "high": 3, "低": 1, "中": 2, "高": 3}


def build_research_synthesis(
    project: dict[str, Any],
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    selected = [item for item in materials if _is_relevant(item)][:10]
    comparison = [_comparison_item(item) for item in selected]
    relationships = _compatibility_relationships(comparison)
    schemes = _build_schemes(project, comparison, relationships)
    analyzed_count = sum(1 for item in comparison if item["analysis_ready"])
    evidence_count = sum(1 for item in comparison if item["evidence_ready"])
    code_count = sum(1 for item in comparison if item["code_ready"])
    areas = list(
        dict.fromkeys(
            item["area"]
            for item in sorted(comparison, key=lambda value: AREA_ORDER.get(value["area"], 99))
        )
    )
    confidence = round(
        sum(item["confidence"] for item in comparison) / len(comparison)
    ) if comparison else 0
    relationship_counts = {
        status: sum(1 for item in relationships if item["status"] == status)
        for status in ("compatible", "conditional", "alternative")
    }
    primary = next((item for item in schemes if item["id"] == "balanced"), schemes[0] if schemes else None)

    return {
        "project_id": project.get("id"),
        "project_name": project.get("name") or "当前项目",
        "hypothesis": project.get("idea") or "验证候选模块能否改善当前任务。",
        "material_count": len(comparison),
        "coverage": {
            "analyzed_count": analyzed_count,
            "evidence_count": evidence_count,
            "code_count": code_count,
            "areas": areas,
            "confidence": confidence,
        },
        "comparison": comparison,
        "compatibility": {
            "counts": relationship_counts,
            "relationships": relationships,
        },
        "schemes": schemes,
        "recommendation": {
            "primary_scheme_id": primary["id"] if primary else "",
            "reason": (
                "优先从平衡方案开始：先验证不同接入位置的独立贡献，再决定是否组合。"
                if primary and primary["id"] == "balanced"
                else "当前候选较少，先执行单模块保守验证。"
            ),
            "first_action": (
                primary["implementation_steps"][0]
                if primary and primary["implementation_steps"]
                else "先补充可分析的候选论文。"
            ),
        },
        "limitations": _limitations(comparison),
    }


def _comparison_item(material: dict[str, Any]) -> dict[str, Any]:
    analysis = _json_object(material.get("deep_analysis_json"))
    evidence = _json_object(material.get("full_text_json"))
    interface = analysis.get("integration_interface") or {}
    code = evidence.get("code") or {}
    area = str(analysis.get("integration_area") or material.get("integration_area") or "Experiment")
    score = float(material.get("ranking_score") or material.get("stitchability_score") or 0)
    evidence_ready = str(material.get("full_text_status") or "") in {"verified", "text_insufficient"}
    code_ready = code.get("status") == "verified_repository"
    confidence = int(analysis.get("confidence") or _fallback_confidence(material, evidence_ready, code_ready))
    risks = [str(item) for item in analysis.get("risks") or []]
    minimal_steps = [str(item) for item in analysis.get("minimal_implementation") or []]

    return {
        "paper_id": int(material.get("id") or 0),
        "title": str(material.get("title") or "未命名论文"),
        "area": area,
        "subtag": str(material.get("integration_subtag") or "General"),
        "module": str(
            analysis.get("reusable_module")
            or f"{area} · {material.get('integration_subtag') or material.get('material_type') or '候选模块'}"
        ),
        "action": str(
            (minimal_steps[1] if len(minimal_steps) > 1 else "")
            or material.get("stitch_action")
            or "以配置开关接入候选模块。"
        ),
        "inputs": [str(item) for item in interface.get("inputs") or []],
        "outputs": [str(item) for item in interface.get("outputs") or []],
        "code_changes": [str(item) for item in interface.get("code_changes") or []],
        "expected_gain": str(analysis.get("expected_gain") or "需要通过单变量实验验证实际收益。"),
        "difficulty": str(material.get("stitch_difficulty") or "中"),
        "score": round(score, 1),
        "confidence": max(0, min(confidence, 100)),
        "evidence": _best_evidence(material, analysis, evidence),
        "analysis_ready": bool(analysis),
        "evidence_ready": evidence_ready,
        "code_ready": code_ready,
        "risks": risks,
        "minimal_steps": minimal_steps,
    }


def _compatibility_relationships(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relationships = []
    for index, left in enumerate(items):
        for right in items[index + 1 :]:
            if left["area"] == right["area"] and left["subtag"] == right["subtag"]:
                status = "alternative"
                reason = f"两项都修改 {left['area']} > {left['subtag']}，首轮应作为替代方案分别验证。"
            elif left["area"] == right["area"]:
                status = "conditional"
                reason = f"两项共享 {left['area']} 接入位置，需要先核对执行顺序与张量接口。"
            elif not left["analysis_ready"] or not right["analysis_ready"]:
                status = "conditional"
                reason = "至少一项缺少结构化接口分析，组合前需要补齐输入输出契约。"
            else:
                status = "compatible"
                reason = f"分别作用于 {left['area']} 与 {right['area']}，适合在单项有效后做组合实验。"
            relationships.append(
                {
                    "left_id": left["paper_id"],
                    "right_id": right["paper_id"],
                    "left_title": left["title"],
                    "right_title": right["title"],
                    "status": status,
                    "reason": reason,
                }
            )
    return relationships


def _build_schemes(
    project: dict[str, Any],
    items: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not items:
        return []

    conservative = min(
        items,
        key=lambda item: (
            _cost(item["difficulty"]),
            -item["confidence"],
            -item["score"],
        ),
    )
    balanced = _select_diverse(
        sorted(
            items,
            key=lambda item: (
                item["score"] + item["confidence"] * 0.12 - _cost(item["difficulty"]) * 4,
                item["code_ready"],
            ),
            reverse=True,
        ),
        3,
    )
    exploratory = _select_diverse(
        sorted(
            items,
            key=lambda item: (
                item["score"] + item["confidence"] * 0.16 + _cost(item["difficulty"]),
                item["analysis_ready"],
            ),
            reverse=True,
        ),
        4,
    )

    specs = [
        (
            "conservative",
            "保守方案",
            "单模块低侵入验证",
            [conservative],
            "先用最低改造成本的候选确认研究假设是否有可观测信号。",
        ),
        (
            "balanced",
            "平衡方案",
            "跨位置渐进组合",
            balanced,
            "选择不同接入位置的高分模块，先单项、后组合，兼顾收益与可归因性。",
        ),
        (
            "exploratory",
            "探索方案",
            "多环节联合改造",
            exploratory,
            "覆盖更多 pipeline 环节，用于验证更完整的架构假设，但实验成本和归因难度更高。",
        ),
    ]
    return [
        _scheme(project, scheme_id, name, strategy, selected, rationale, relationships)
        for scheme_id, name, strategy, selected, rationale in specs
    ]


def _scheme(
    project: dict[str, Any],
    scheme_id: str,
    name: str,
    strategy: str,
    selected: list[dict[str, Any]],
    rationale: str,
    relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_ids = {item["paper_id"] for item in selected}
    related = [
        item
        for item in relationships
        if item["left_id"] in selected_ids and item["right_id"] in selected_ids
    ]
    confidence = round(sum(item["confidence"] for item in selected) / len(selected)) if selected else 0
    implementation_steps = [
        f"冻结 {project.get('backbone') or 'Backbone'} + {project.get('neck') or 'Neck'} + "
        f"{project.get('head') or 'Head'} 基线与随机种子。"
    ]
    implementation_steps.extend(
        f"{index}. {item['area']}：{item['action']}"
        for index, item in enumerate(selected, start=1)
    )
    if len(selected) > 1:
        implementation_steps.append("仅保留单项有效模块，核对接口后开启组合配置。")

    experiments = [
        {
            "name": "E0 基线复核",
            "change": "不修改模型，固化当前基线与资源消耗。",
        }
    ]
    experiments.extend(
        {
            "name": f"E{index} {item['area']} 单项",
            "change": item["action"],
        }
        for index, item in enumerate(selected, start=1)
    )
    if len(selected) > 1:
        experiments.append(
            {
                "name": f"E{len(experiments)} 有效项组合",
                "change": "组合单项实验中确认有效且接口兼容的模块。",
            }
        )

    risks = []
    for relation in related:
        if relation["status"] != "compatible":
            risks.append(relation["reason"])
    for item in selected:
        risks.extend(item["risks"][:1])
    if any(not item["code_ready"] for item in selected):
        risks.append("部分候选没有已验证代码仓库，需要预留复现和接口适配时间。")
    if not risks:
        risks.append("规则未发现明显接口冲突，但组合前仍需以真实张量形状和配置验证。")

    return {
        "id": scheme_id,
        "name": name,
        "strategy": strategy,
        "rationale": rationale,
        "material_ids": [item["paper_id"] for item in selected],
        "modules": [
            {
                key: item[key]
                for key in ("paper_id", "title", "area", "module", "action", "difficulty", "score")
            }
            for item in selected
        ],
        "estimated_cost": _estimated_cost(selected),
        "confidence": confidence,
        "implementation_steps": implementation_steps,
        "experiments": experiments,
        "metrics": _metrics(project),
        "stop_conditions": _stop_conditions(project),
        "risks": list(dict.fromkeys(str(item) for item in risks))[:5],
    }


def _select_diverse(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected = []
    areas = set()
    for item in items:
        if item["area"] in areas:
            continue
        selected.append(item)
        areas.add(item["area"])
        if len(selected) >= limit:
            break
    if len(selected) < min(limit, len(items)):
        for item in items:
            if item not in selected:
                selected.append(item)
            if len(selected) >= limit:
                break
    return selected


def _best_evidence(
    material: dict[str, Any],
    analysis: dict[str, Any],
    evidence: dict[str, Any],
) -> str:
    sections = evidence.get("sections") or []
    method = next((item for item in sections if item.get("kind") == "method"), None)
    if method:
        return f"全文第 {method.get('page', '?')} 页：{_clip(method.get('text'), 180)}"
    analysis_evidence = analysis.get("evidence") or []
    if analysis_evidence:
        return _clip(analysis_evidence[0], 200)
    return _clip(material.get("evidence_quote") or material.get("summary") or "仅有标题证据。", 200)


def _fallback_confidence(material: dict[str, Any], evidence_ready: bool, code_ready: bool) -> int:
    confidence = 42
    confidence += 12 if evidence_ready else 0
    confidence += 8 if code_ready else 0
    confidence += round(float(material.get("relevance_score") or 0) * 0.12)
    return min(confidence, 72)


def _estimated_cost(items: list[dict[str, Any]]) -> str:
    total = sum(_cost(item["difficulty"]) for item in items)
    if total <= 2:
        return "低 · 约 1-2 个工作日"
    if total <= 5:
        return "中 · 约 3-5 个工作日"
    return "高 · 约 1-2 周"


def _metrics(project: dict[str, Any]) -> list[str]:
    task = str(project.get("task_type") or "").lower()
    if "检测" in task or "detection" in task:
        return ["mAP", "AP_small", "Params", "FPS", "显存峰值"]
    if "分割" in task or "segmentation" in task:
        return ["mIoU", "mF1", "Params", "FPS", "显存峰值"]
    return ["主任务指标", "参数量", "推理速度", "显存峰值"]


def _stop_conditions(project: dict[str, Any]) -> list[str]:
    primary = _metrics(project)[0]
    return [
        f"单项实验的 {primary} 不高于基线且重复两次无改善时停止组合。",
        "显存或训练时间增加超过 30% 且主指标收益不足 1% 时停止。",
        "出现接口不稳定、无法复现或收益无法归因时回退到上一个有效配置。",
    ]


def _limitations(items: list[dict[str, Any]]) -> list[str]:
    limitations = ["兼容性来自论文接口描述与规则推断，尚未扫描你的真实代码和张量形状。"]
    missing_analysis = sum(1 for item in items if not item["analysis_ready"])
    missing_evidence = sum(1 for item in items if not item["evidence_ready"])
    if missing_analysis:
        limitations.append(f"{missing_analysis} 张素材缺少结构化深度分析，相关组合仅作候选建议。")
    if missing_evidence:
        limitations.append(f"{missing_evidence} 张素材缺少全文证据，关键方法仍需人工复核。")
    return limitations


def _is_relevant(material: dict[str, Any]) -> bool:
    feedback = str(material.get("user_feedback") or "")
    if feedback in {"useful", "stitchable"}:
        return True
    if feedback == "irrelevant":
        return False
    return bool(material.get("is_relevant", True))


def _cost(value: str) -> int:
    return DIFFICULTY_COST.get(str(value), 2)


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
