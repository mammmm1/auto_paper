from __future__ import annotations

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


def build_experiment_route(project: dict[str, Any], materials: list[dict[str, Any]]) -> dict[str, Any]:
    selected = sorted(
        materials,
        key=lambda item: (
            AREA_ORDER.get(str(item.get("integration_area")), 99),
            -float(item.get("stitchability_score") or 0),
        ),
    )
    baseline = " + ".join(
        value
        for value in [
            str(project.get("backbone") or ""),
            str(project.get("neck") or ""),
            str(project.get("head") or ""),
        ]
        if value
    ) or "当前项目基线"

    steps = [
        {
            "order": index,
            "area": material.get("integration_area") or "Experiment",
            "title": material.get("title") or "未命名素材",
            "action": material.get("stitch_action") or "人工确认接入位置后进行单变量实验。",
            "difficulty": material.get("stitch_difficulty") or "中",
            "score": float(material.get("stitchability_score") or 0),
        }
        for index, material in enumerate(selected, start=1)
    ]
    areas = list(dict.fromkeys(str(item["area"]) for item in steps))
    area_text = "、".join(areas) if areas else "待选择"

    return {
        "name": f"{project.get('name') or '当前项目'} · 第一轮实验路线",
        "hypothesis": project.get("idea") or "验证所选素材能否提升当前任务表现。",
        "baseline": baseline,
        "dataset": project.get("dataset") or "当前数据集",
        "selection_summary": f"已选择 {len(selected)} 张素材，覆盖 {area_text}。",
        "innovation_statement": (
            f"围绕“{project.get('idea') or '当前研究假设'}”，"
            f"在 {area_text} 环节组合验证所选方法，并通过逐项消融确认真实贡献。"
        ),
        "steps": steps,
        "validation": [
            "复现并冻结基线结果与训练配置。",
            "每次只接入一张素材对应的改动，记录精度、参数量、速度和训练稳定性。",
            "保留有效单项后再做组合实验，避免无法归因。",
            "最后补充组件消融、尺度分组指标和跨数据集验证。",
        ],
        "risks": _route_risks(selected),
    }


def _route_risks(materials: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    if any(item.get("stitch_difficulty") == "高" for item in materials):
        risks.append("包含高改造成本素材，建议放到低侵入实验验证之后。")
    if len(materials) > 5:
        risks.append("首轮素材超过 5 张，实验变量可能过多，建议拆成两轮。")
    if materials and not any(float(item.get("code_availability_score") or 0) >= 55 for item in materials):
        risks.append("所选素材缺少明确代码线索，需要预留复现与接口适配时间。")
    if not risks:
        risks.append("当前组合风险可控，但仍需先做单变量实验再合并。")
    return risks
