from __future__ import annotations

import json
import re
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
    code_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = [item for item in materials if _is_relevant(item)][:10]
    comparison = [_comparison_item(item) for item in selected]
    relationships = _compatibility_relationships(comparison)
    schemes = _build_schemes(project, comparison, relationships, code_scan or {})
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
        "code_context": _code_context(project, code_scan or {}),
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
        "limitations": _limitations(comparison, code_scan or {}),
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
    code_scan: dict[str, Any],
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
        _scheme(project, scheme_id, name, strategy, selected, rationale, relationships, code_scan)
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
    code_scan: dict[str, Any],
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
        "implementation_map": _implementation_map(selected, code_scan),
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


def _limitations(items: list[dict[str, Any]], code_scan: dict[str, Any]) -> list[str]:
    if code_scan.get("status") == "ready":
        limitations = ["文件位置来自只读静态扫描；尚未执行代码，也没有验证真实张量形状和运行时依赖。"]
    else:
        limitations = ["兼容性来自论文接口描述与规则推断，尚未扫描你的真实代码和张量形状。"]
    missing_analysis = sum(1 for item in items if not item["analysis_ready"])
    missing_evidence = sum(1 for item in items if not item["evidence_ready"])
    if missing_analysis:
        limitations.append(f"{missing_analysis} 张素材缺少结构化深度分析，相关组合仅作候选建议。")
    if missing_evidence:
        limitations.append(f"{missing_evidence} 张素材缺少全文证据，关键方法仍需人工复核。")
    return limitations


def _code_context(project: dict[str, Any], code_scan: dict[str, Any]) -> dict[str, Any]:
    summary = code_scan.get("summary") or {}
    graph = code_scan.get("code_graph") or {}
    graph_summary = graph.get("summary") or {}
    return {
        "status": code_scan.get("status") or "not_scanned",
        "repository_name": code_scan.get("repository_name") or "",
        "repository_url": project.get("code_repo_url") or "",
        "root": code_scan.get("root") or project.get("code_path") or "",
        "scanned_at": code_scan.get("scanned_at") or project.get("code_scan_updated_at") or "",
        "frameworks": code_scan.get("frameworks") or [],
        "areas": code_scan.get("areas") or [],
        "files_scanned": int(summary.get("files_scanned") or 0),
        "component_count": int(summary.get("component_count") or 0),
        "adapter": graph.get("adapter") or "none",
        "adapter_label": graph.get("adapter_label") or "未识别",
        "registration_count": int(graph_summary.get("registration_count") or 0),
        "config_link_count": int(graph_summary.get("link_count") or 0),
        "interface_count": int(graph_summary.get("interface_count") or 0),
        "unresolved_count": int(graph_summary.get("unresolved_count") or 0),
        "entrypoints": code_scan.get("entrypoints") or [],
        "warnings": code_scan.get("warnings") or [],
    }


def _implementation_map(
    items: list[dict[str, Any]],
    code_scan: dict[str, Any],
) -> list[dict[str, Any]]:
    components = code_scan.get("components") or []
    graph = code_scan.get("code_graph") or {}
    links = graph.get("links") or []
    mapped = []
    for item in items:
        area_links = [link for link in links if link.get("area") == item["area"]]
        configured_link = max(
            area_links,
            key=lambda value: int(value.get("confidence") or 0),
            default=None,
        )
        linked_paths = {link.get("source_path") for link in area_links if link.get("source_path")}
        candidates = [
            component
            for component in components
            if component.get("area") == item["area"] and component.get("kind") != "config"
        ]
        target = None
        if configured_link:
            target = next(
                (
                    component
                    for component in candidates
                    if component.get("path") == configured_link.get("source_path")
                    and component.get("name") == configured_link.get("symbol")
                ),
                None,
            )
        target = target or max(
            candidates,
            key=lambda value: _target_score(item, value, linked_paths),
            default=None,
        )
        config_candidates = [
            component
            for component in components
            if component.get("area") == item["area"]
            and component.get("kind") == "config"
            and component.get("config_key")
        ]
        config_target = None
        if configured_link:
            config_target = next(
                (
                    component
                    for component in config_candidates
                    if component.get("path") == configured_link.get("config_path")
                    and component.get("config_key") == configured_link.get("config_key")
                ),
                None,
            )
        config_target = config_target or max(
            config_candidates,
            key=lambda value: _target_score(item, value, set()),
            default=None,
        )
        interface = (target.get("interface") or {}) if target else {}
        registry = str(target.get("registry") or "") if target else ""
        if target:
            location = f"{target.get('path')}:{target.get('line', 1)}"
            if config_target and (interface.get("parameters") or registry):
                action = (
                    f"以 {location} 的 {target.get('name') or '现有实现'} 为接口基线，"
                    f"在 {config_target.get('path')} 的 {config_target.get('config_key')} 切换候选模块。"
                )
                status = "contract_ready"
            else:
                action = (
                    f"优先检查 {location} 的 {target.get('name') or '现有实现'}，"
                    f"通过独立配置开关接入 {item['module']}。"
                )
                status = "mapped"
        else:
            action = f"未找到明确的 {item['area']} 实现；先定位注册表或构建函数，再接入 {item['module']}。"
            status = "unmapped"
        conflicts = _contract_conflicts(item["area"], target, config_target, graph)
        mapped.append(
            {
                "paper_id": item["paper_id"],
                "area": item["area"],
                "module": item["module"],
                "status": status,
                "target": (
                    {
                        key: target.get(key)
                        for key in (
                            "path",
                            "line",
                            "name",
                            "kind",
                            "confidence",
                            "registry",
                            "registered_name",
                            "constructor",
                            "interface",
                        )
                    }
                    if target
                    else None
                ),
                "config_target": (
                    {
                        key: config_target.get(key)
                        for key in (
                            "path",
                            "line",
                            "name",
                            "config_key",
                            "configured_type",
                            "parameters",
                        )
                    }
                    if config_target
                    else None
                ),
                "mapping_confidence": _mapping_confidence(status, target, configured_link),
                "action": action,
                "change_plan": _change_plan(item, target, config_target, graph),
                "contract_checks": _contract_checks(target, config_target),
                "conflicts": conflicts,
                "validation": _code_validation(item["area"], graph.get("adapter") or ""),
            }
        )
    return mapped


def _target_score(
    item: dict[str, Any],
    component: dict[str, Any],
    linked_paths: set[str],
) -> float:
    source_tokens = _word_tokens(
        " ".join(
            str(value or "")
            for value in (item.get("module"), item.get("subtag"), item.get("action"))
        )
    )
    target_tokens = _word_tokens(
        " ".join(
            str(value or "")
            for value in (component.get("name"), component.get("path"), " ".join(component.get("signals") or []))
        )
    )
    configured_bonus = 35 if component.get("path") in linked_paths else 0
    interface_bonus = 8 if (component.get("interface") or {}).get("parameters") else 0
    registry_bonus = 8 if component.get("registry") else 0
    return (
        float(component.get("confidence") or 0)
        + len(source_tokens.intersection(target_tokens)) * 12
        + configured_bonus
        + interface_bonus
        + registry_bonus
    )


def _mapping_confidence(
    status: str,
    target: dict[str, Any] | None,
    configured_link: dict[str, Any] | None,
) -> int:
    if status == "unmapped":
        return 0
    if configured_link:
        return min(98, int(configured_link.get("confidence") or 88))
    return min(82, int((target or {}).get("confidence") or 60))


def _change_plan(
    item: dict[str, Any],
    target: dict[str, Any] | None,
    config_target: dict[str, Any] | None,
    graph: dict[str, Any],
) -> list[str]:
    if not target:
        return [f"定位 {item['area']} 的注册表、构建函数或配置入口。"]
    steps = [
        f"以 {target.get('path')}:{target.get('line', 1)} 的 {target.get('name')} 作为兼容接口基线。"
    ]
    registry = str(target.get("registry") or "")
    if registry:
        steps.append(f"为新模块使用 {registry}.register_module 注册独立类型名。")
    elif graph.get("adapter") in {"mmdetection", "mmsegmentation", "mmengine"}:
        framework = "MMSegmentation" if graph.get("adapter") == "mmsegmentation" else "MMEngine"
        steps.append(f"确认新模块进入 {framework} MODELS 注册表，避免直接修改现有类。")
    if config_target:
        steps.append(
            f"复制实验配置，在 {config_target.get('path')} 的 {config_target.get('config_key')}.type 切换新类型。"
        )
    else:
        steps.append("新增独立实验配置开关，保留当前实现作为基线。")
    steps.append("保持原接口与默认参数可回退，再运行最小烟雾测试。")
    return steps


def _contract_checks(
    target: dict[str, Any] | None,
    config_target: dict[str, Any] | None,
) -> list[str]:
    checks = []
    if target:
        interface = target.get("interface") or {}
        parameters = interface.get("parameters") or []
        returns = interface.get("returns") or []
        if parameters:
            checks.append(
                f"forward({', '.join(parameters)})"
                + (f" -> {' / '.join(returns)}" if returns else "")
            )
        if target.get("registry"):
            checks.append(
                f"注册表 {target['registry']} · 类型 {target.get('registered_name') or target.get('name')}"
            )
    if config_target:
        parameters = config_target.get("parameters") or {}
        important = {
            key: value
            for key, value in parameters.items()
            if key
            in {
                "align_corners",
                "channels",
                "in_channels",
                "in_index",
                "num_classes",
                "num_outs",
                "out_channels",
                "out_indices",
                "pool_scales",
                "strides",
            }
        }
        checks.append(f"配置键 {config_target.get('config_key')}")
        if important:
            checks.append(json.dumps(important, ensure_ascii=False, separators=(",", ":")))
    return checks


def _contract_conflicts(
    area: str,
    target: dict[str, Any] | None,
    config_target: dict[str, Any] | None,
    graph: dict[str, Any],
) -> list[dict[str, str]]:
    conflicts = []
    if not target:
        return [{"severity": "warning", "message": "缺少源码实现定位，无法核验输入输出契约。"}]
    interface = target.get("interface") or {}
    if area in {"Backbone", "Neck", "Head"} and not interface.get("parameters"):
        conflicts.append({"severity": "warning", "message": "未解析到 forward 参数，需要人工确认调用签名。"})
    if graph.get("adapter") in {"mmdetection", "mmsegmentation"} and not target.get("registry"):
        conflicts.append({"severity": "warning", "message": "目标类未发现 MMEngine 注册装饰器，配置 type 可能无法构建。"})
    parameters = (config_target or {}).get("parameters") or {}
    in_channels = parameters.get("in_channels")
    in_index = parameters.get("in_index")
    num_outs = parameters.get("num_outs")
    if isinstance(in_channels, list) and isinstance(num_outs, int) and num_outs < len(in_channels):
        conflicts.append(
            {
                "severity": "warning",
                "message": f"num_outs={num_outs} 小于输入特征层数量 {len(in_channels)}，需要核对尺度输出。",
            }
        )
    config_key = str((config_target or {}).get("config_key") or "")
    if (
        graph.get("adapter") == "mmsegmentation"
        and "head" in config_key
        and isinstance(in_channels, list)
        and isinstance(in_index, list)
        and len(in_channels) != len(in_index)
    ):
        conflicts.append(
            {
                "severity": "warning",
                "message": (
                    f"in_channels 包含 {len(in_channels)} 层，但 in_index 包含 {len(in_index)} 层，"
                    "decode head 无法逐层对齐。"
                ),
            }
        )
    return conflicts


def _word_tokens(value: str) -> set[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    return {token.lower() for token in re.split(r"[^A-Za-z0-9]+", expanded) if len(token) > 2}


def _code_validation(area: str, adapter: str = "") -> list[str]:
    if adapter == "mmsegmentation":
        segmentation_checks = {
            "Backbone": ["检查各 stage 输出尺寸、通道数与 out_indices", "运行最小前向传播和显存测试"],
            "Neck": ["检查多尺度特征数量、stride 与通道数", "运行特征融合单元测试"],
            "Head": ["检查 in_channels、in_index 与类别 logits", "运行单批次 encode_decode 烟雾测试"],
            "Loss": ["检查 ignore_index、loss_decode 键名与有限梯度", "在固定 mask 上比较基线损失"],
            "Data": ["检查 mask 类别映射、裁剪尺寸和 seg_pad_val", "可视化 Potsdam/Vaihingen 样本及标签"],
            "Training": ["检查优化器参数组和调度器步进时机", "运行短周期训练烟雾测试"],
            "Experiment": ["记录 mIoU、mF1、OA 与分类别指标", "保留基线配置用于可归因对照"],
        }
        return segmentation_checks.get(area, ["运行导入检查", "执行最小分割烟雾测试"])
    checks = {
        "Backbone": ["检查各 stage 输出尺寸与通道数", "运行最小前向传播和显存测试"],
        "Neck": ["检查多尺度特征数量、stride 与通道数", "运行特征融合单元测试"],
        "Head": ["检查类别数、输出字段与后处理接口", "运行单批次预测烟雾测试"],
        "Loss": ["检查 loss 字典键名与梯度是否有限", "在固定 batch 上比较基线损失"],
        "Data": ["检查样本字段、标注格式与增强顺序", "可视化一个 batch 的输入和标签"],
        "Training": ["检查优化器参数组和调度器步进时机", "运行短周期训练烟雾测试"],
        "Experiment": ["新增独立配置并固定随机种子", "保留基线配置用于可归因对照"],
    }
    return checks.get(area, ["运行导入检查", "执行最小烟雾测试"])


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
