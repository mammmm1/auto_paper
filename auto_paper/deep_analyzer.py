from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Any


ANALYSIS_SCHEMA_VERSION = "2026-08-19-v1"
RULE_MODEL = "rules-v1"
ANALYSIS_AREAS = ["Backbone", "Neck", "Head", "Loss", "Data", "Training", "Experiment"]

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "core_problem": {"type": "string"},
        "method_summary": {"type": "string"},
        "reusable_module": {"type": "string"},
        "project_match": {"type": "string"},
        "integration_area": {"type": "string", "enum": ANALYSIS_AREAS},
        "integration_interface": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "inputs": {"type": "array", "items": {"type": "string"}},
                "outputs": {"type": "array", "items": {"type": "string"}},
                "code_changes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["inputs", "outputs", "code_changes"],
        },
        "minimal_implementation": {"type": "array", "items": {"type": "string"}},
        "experiment_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "change": {"type": "string"},
                    "control": {"type": "string"},
                    "metrics": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "change", "control", "metrics"],
            },
        },
        "expected_gain": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "limitations": {"type": "string"},
    },
    "required": [
        "core_problem",
        "method_summary",
        "reusable_module",
        "project_match",
        "integration_area",
        "integration_interface",
        "minimal_implementation",
        "experiment_plan",
        "expected_gain",
        "risks",
        "evidence",
        "confidence",
        "limitations",
    ],
}


def analysis_engine(api_key: str, model: str) -> str:
    return f"openai:{model}" if api_key.strip() else RULE_MODEL


def analysis_input_hash(
    paper: dict[str, Any],
    project: dict[str, Any],
    engine: str,
) -> str:
    payload = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "engine": engine,
        "project": {
            field: project.get(field) or ""
            for field in (
                "name",
                "domain",
                "task_type",
                "idea",
                "keywords",
                "backbone",
                "neck",
                "head",
                "dataset",
            )
        },
        "paper": {
            field: paper.get(field) or ""
            for field in (
                "title",
                "abstract",
                "summary",
                "material_type",
                "integration_area",
                "integration_subtag",
                "stitch_action",
                "evidence_sources",
                "evidence_quote",
            )
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analyze_material(
    paper: dict[str, Any],
    project: dict[str, Any],
    api_key: str = "",
    model: str = "gpt-5-mini",
) -> dict[str, Any]:
    engine = analysis_engine(api_key, model)
    input_hash = analysis_input_hash(paper, project, engine)
    if not api_key.strip():
        return {
            "analysis": build_rule_analysis(paper, project),
            "source": "rules",
            "model": RULE_MODEL,
            "input_hash": input_hash,
            "warning": "未配置 OPENAI_API_KEY，当前结果由规则模板生成。",
        }

    try:
        analysis = _request_openai_analysis(paper, project, api_key, model)
        _validate_analysis_shape(analysis)
        return {
            "analysis": analysis,
            "source": "openai",
            "model": model,
            "input_hash": input_hash,
            "warning": "",
        }
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        fallback = build_rule_analysis(paper, project)
        fallback["limitations"] += " OpenAI 请求失败，本次已自动降级为规则结果。"
        return {
            "analysis": fallback,
            "source": "rules_fallback",
            "model": RULE_MODEL,
            "input_hash": input_hash,
            "warning": f"OpenAI 分析失败，已降级：{_safe_error(exc)}",
        }


def build_rule_analysis(paper: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    area = str(paper.get("integration_area") or "Experiment")
    if area not in ANALYSIS_AREAS:
        area = "Experiment"
    interface = _interface_for_area(area, project)
    title = str(paper.get("title") or "未命名论文").strip()
    abstract = " ".join(str(paper.get("abstract") or "").split())
    summary = str(paper.get("summary") or "").strip()
    action = str(paper.get("stitch_action") or "").strip()
    subtag = str(paper.get("integration_subtag") or "通用方法").strip()
    material_type = str(paper.get("material_type") or "idea").strip()
    task = str(project.get("task_type") or "当前任务").strip()
    dataset = str(project.get("dataset") or "当前数据集").strip()
    metrics = _metrics_for_task(task)
    evidence = [f"标题证据：{title}"]
    evidence_quote = str(paper.get("evidence_quote") or "").strip()
    if evidence_quote:
        evidence.append(f"摘要证据：{_clip(evidence_quote, 180)}")
    elif abstract:
        evidence.append(f"摘要证据：{_clip(abstract, 180)}")

    return {
        "core_problem": _clip(summary or abstract or f"论文围绕 {title} 展开。", 260),
        "method_summary": _clip(
            summary or f"从标题和摘要判断，该工作尝试用 {subtag} 改进 {task}。",
            320,
        ),
        "reusable_module": f"可提取为 {area} 环节的 {subtag} {material_type} 素材。",
        "project_match": (
            f"与项目“{project.get('name') or '当前项目'}”的 {task} 目标在 {area} 环节存在接点。"
            f"建议先按单变量方式验证，不直接替换完整 pipeline。"
        ),
        "integration_area": area,
        "integration_interface": interface,
        "minimal_implementation": [
            f"冻结当前基线，记录 {dataset} 上的 {', '.join(metrics)}。",
            action or f"在 {area} 环节增加一个可开关的 {subtag} 适配模块。",
            "保持数据、训练轮数和其余组件不变，只验证该模块的独立贡献。",
            "通过配置开关保留原路径，确认有效后再进入组合实验。",
        ],
        "experiment_plan": [
            {
                "name": "E0 基线复核",
                "change": "不改代码结构，复跑并固化当前基线。",
                "control": "使用现有随机种子、数据划分和训练配置。",
                "metrics": metrics,
            },
            {
                "name": f"E1 {subtag} 单项接入",
                "change": action or f"仅在 {area} 环节接入候选模块。",
                "control": "除候选模块外，其余配置与 E0 完全一致。",
                "metrics": metrics,
            },
            {
                "name": "E2 消融与成本复核",
                "change": "移除或简化候选模块的关键分支，记录性能与成本变化。",
                "control": "沿用 E1 训练预算，至少重复一次关键实验。",
                "metrics": [*metrics, "显存占用", "训练稳定性"],
            },
        ],
        "expected_gain": (
            f"若素材判断成立，预期在 {task} 的核心指标或目标尺度分组指标上优于基线；"
            "规则分析不提供未经实验验证的具体增益数值。"
        ),
        "risks": [
            "论文模块的张量尺寸、特征层级或训练目标可能与当前 pipeline 不兼容。",
            "摘要中的总体提升不能证明该单一模块就是增益来源，需要消融验证。",
            "缺少全文与代码核验时，复现成本和实现细节仍可能被低估。",
        ],
        "evidence": evidence,
        "confidence": _rule_confidence(paper, abstract),
        "limitations": "当前仅基于标题、摘要和已有素材卡生成，尚未核验 PDF 全文、公式、架构图或代码仓库。",
    }


def extract_response_text(response: dict[str, Any]) -> str:
    for output in response.get("output", []):
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"])
    raise ValueError("OpenAI response did not contain output_text")


def _request_openai_analysis(
    paper: dict[str, Any],
    project: dict[str, Any],
    api_key: str,
    model: str,
) -> dict[str, Any]:
    context = {
        "project_profile": {
            field: project.get(field) or ""
            for field in (
                "name",
                "domain",
                "task_type",
                "idea",
                "keywords",
                "backbone",
                "neck",
                "head",
                "dataset",
            )
        },
        "paper_material": {
            field: paper.get(field) or ""
            for field in (
                "title",
                "abstract",
                "summary",
                "material_type",
                "integration_area",
                "integration_subtag",
                "stitch_action",
                "stitch_difficulty",
                "evidence_sources",
                "evidence_quote",
            )
        },
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "你是科研工程落地分析器。只使用给定项目画像、论文标题和摘要进行判断。"
                            "不要声称读过全文或代码，不要编造结构、公式、指标和仓库。"
                            "目标是输出可执行的最小接入方案和单变量实验。证据必须可追溯到输入文本，"
                            "不确定内容写入 limitations，所有字段使用中文。"
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(context, ensure_ascii=False),
                    }
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "paper_stitch_analysis",
                "strict": True,
                "schema": ANALYSIS_SCHEMA,
            }
        },
        "max_output_tokens": 4000,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OSError(f"OpenAI HTTP {exc.code}: {_clip(detail, 180)}") from exc
    return json.loads(extract_response_text(body))


def _validate_analysis_shape(analysis: dict[str, Any]) -> None:
    missing = [field for field in ANALYSIS_SCHEMA["required"] if field not in analysis]
    if missing:
        raise ValueError(f"analysis missing fields: {', '.join(missing)}")
    if analysis.get("integration_area") not in ANALYSIS_AREAS:
        raise ValueError("analysis returned an invalid integration_area")


def _interface_for_area(area: str, project: dict[str, Any]) -> dict[str, list[str]]:
    backbone = str(project.get("backbone") or "Backbone")
    neck = str(project.get("neck") or "Neck")
    head = str(project.get("head") or "Task Head")
    interfaces = {
        "Data": {
            "inputs": ["原始影像与标注"],
            "outputs": ["与基线格式一致的训练 batch"],
            "code_changes": ["数据集配置", "增强 pipeline", "采样器或标注转换"],
        },
        "Backbone": {
            "inputs": ["预处理后的图像张量"],
            "outputs": [f"供 {neck} 使用的多层特征"],
            "code_changes": [f"为 {backbone} 增加可开关模块", "保持输出层数和通道契约"],
        },
        "Neck": {
            "inputs": [f"{backbone} 输出的多尺度特征"],
            "outputs": [f"与 {head} 输入契约一致的融合特征"],
            "code_changes": [f"扩展或替换 {neck} 的局部融合节点", "增加配置开关和维度适配"],
        },
        "Head": {
            "inputs": ["Backbone/Neck 输出特征"],
            "outputs": ["与现有标签和评估器兼容的预测"],
            "code_changes": [f"在 {head} 内增加候选分支", "复用现有后处理和评估接口"],
        },
        "Loss": {
            "inputs": ["模型预测", "批次标注"],
            "outputs": ["可与基线损失加权求和的标量"],
            "code_changes": ["实现独立损失项", "暴露权重配置并记录分项日志"],
        },
        "Training": {
            "inputs": ["模型、数据加载器与优化器状态"],
            "outputs": ["与基线可比较的检查点和日志"],
            "code_changes": ["新增训练策略配置", "保持评估流程不变"],
        },
        "Experiment": {
            "inputs": ["冻结的基线配置与候选假设"],
            "outputs": ["可归因的对照实验结果"],
            "code_changes": ["新增实验配置", "统一指标和结果记录格式"],
        },
    }
    return interfaces[area]


def _metrics_for_task(task_type: str) -> list[str]:
    normalized = task_type.lower()
    if "分割" in normalized or "segmentation" in normalized:
        return ["mIoU", "mF1", "Params", "FPS"]
    if "检测" in normalized or "detection" in normalized:
        return ["mAP", "AP_small", "Params", "FPS"]
    return ["主任务指标", "参数量", "推理速度", "训练稳定性"]


def _rule_confidence(paper: dict[str, Any], abstract: str) -> int:
    confidence = 52
    if len(abstract) >= 400:
        confidence += 10
    if paper.get("evidence_quote"):
        confidence += 6
    if paper.get("integration_subtag"):
        confidence += 4
    return min(confidence, 72)


def _clip(text: str, limit: int) -> str:
    normalized = " ".join(str(text).split())
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def _safe_error(error: Exception) -> str:
    return _clip(str(error).replace("\n", " "), 180)
