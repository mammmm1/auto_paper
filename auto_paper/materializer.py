from __future__ import annotations

import re
from typing import Any


AREAS = {
    "Backbone": {
        "tags": ["Layer-wise Attention", "Representation", "Transformer Block"],
        "signals": ["backbone", "transformer", "swin", "vit", "encoder", "layer", "attention"],
    },
    "Neck": {
        "tags": ["Feature Fusion", "Multi-scale Enhancement", "Pyramid"],
        "signals": ["neck", "fpn", "pyramid", "fusion", "multi-scale", "multiscale", "feature aggregation"],
    },
    "Head": {
        "tags": ["Detection Head", "Decoder", "Prediction"],
        "signals": ["head", "detector", "decoder", "query", "proposal", "classification", "regression"],
    },
    "Loss": {
        "tags": ["Small-object Reweighting", "Auxiliary Supervision", "Optimization"],
        "signals": ["loss", "objective", "supervision", "reweight", "imbalance", "optimization"],
    },
    "Data": {
        "tags": ["Dataset", "Augmentation", "Sampling"],
        "signals": ["dataset", "augmentation", "sample", "sampling", "dota", "dior", "nwpu", "remote sensing"],
    },
    "Training": {
        "tags": ["Training Strategy", "Pretraining", "Schedule"],
        "signals": ["training", "pretrain", "fine-tune", "schedule", "distillation", "contrastive"],
    },
    "Experiment": {
        "tags": ["Ablation", "Benchmark", "Evaluation"],
        "signals": ["ablation", "benchmark", "evaluation", "experiment", "metric", "comparison"],
    },
}

TYPE_SIGNALS = {
    "code": ["code", "github", "repository", "implementation", "open-source"],
    "architecture": ["architecture", "framework", "pipeline", "network"],
    "module": ["module", "block", "attention", "fusion", "head", "loss"],
    "experiment": ["ablation", "benchmark", "evaluation", "experiment"],
    "dataset": ["dataset", "data", "dota", "dior", "nwpu"],
    "idea": ["propose", "introduce", "present", "hypothesis", "approach"],
}

REMOTE_DOMAIN_SIGNALS = [
    "remote sensing",
    "earth observation",
    "satellite image",
    "satellite imagery",
    "aerial image",
    "aerial imagery",
    "overhead image",
    "geospatial",
    "dota",
    "dior",
    "nwpu",
    "sar image",
    "hyperspectral",
]

VISION_TASK_SIGNALS = [
    "object detection",
    "small object",
    "tiny object",
    "oriented object",
    "semantic segmentation",
    "instance segmentation",
    "change detection",
]

METHOD_SIGNALS = [
    "transformer",
    "attention",
    "multi-scale",
    "multiscale",
    "feature pyramid",
    "feature fusion",
    "swin",
    "vision transformer",
]

UNRELATED_DOMAIN_SIGNALS = [
    "wireless communication",
    "6g network",
    "teleoperation",
    "robotic manipulation",
    "medical imaging",
    "drug discovery",
    "large language model",
]


def build_material_card(candidate: Any, project: dict[str, Any], summary: str) -> dict[str, Any]:
    text = f"{candidate.title} {candidate.abstract}".lower()
    area, area_score = _best_area(text, project)
    subtag = _subtag(area, text)
    material_type = _material_type(text)
    relevance = _relevance_score(text, project)
    is_relevant, relevance_tier, filter_reason = _relevance_gate(text, project, relevance)
    code_availability = _code_score(text)
    stitchability = _stitchability_score(area_score, relevance, code_availability, text, project)
    if relevance_tier == "reference":
        stitchability = min(stitchability, 49.0)
    elif relevance_tier == "irrelevant":
        stitchability = min(stitchability, 25.0)
    difficulty = _difficulty(area, text, project)
    action = _stitch_action(area, subtag, material_type, project)
    evidence_sources, evidence_quote = _evidence(candidate.title, candidate.abstract, area, project)

    return {
        "material_type": material_type,
        "integration_area": area,
        "integration_subtag": subtag,
        "stitch_action": action,
        "stitch_difficulty": difficulty,
        "relevance_score": relevance,
        "is_relevant": is_relevant,
        "relevance_tier": relevance_tier,
        "filter_reason": filter_reason,
        "stitchability_score": stitchability,
        "code_availability_score": code_availability,
        "recommendation_score": stitchability,
        "recommendation_reason": f"{area} > {subtag}；{action}",
        "evidence_sources": evidence_sources,
        "evidence_quote": evidence_quote,
        "summary": summary,
    }


def build_project_query(project: dict[str, Any]) -> str:
    parts = [
        project.get("domain", ""),
        project.get("task_type", ""),
        project.get("idea", ""),
        project.get("keywords", ""),
        project.get("backbone", ""),
        project.get("neck", ""),
        project.get("head", ""),
        project.get("dataset", ""),
    ]
    profile_text = " ".join(str(part) for part in parts).lower()
    if _is_remote_sensing_project(profile_text):
        domain_clause = (
            '(all:"remote sensing" OR all:"earth observation" OR '
            'all:"satellite image" OR all:"aerial image" OR all:geospatial '
            'OR all:DOTA OR all:DIOR)'
        )
        focus_terms = []
        for signal in VISION_TASK_SIGNALS + METHOD_SIGNALS:
            if signal in profile_text:
                focus_terms.append(signal)
        if "目标检测" in profile_text:
            focus_terms.extend(["object detection", "small object"])
        if "分割" in profile_text:
            focus_terms.extend(["semantic segmentation", "instance segmentation"])
        focus_terms.extend(["transformer", "multi-scale"])
        selected = list(dict.fromkeys(focus_terms))[:8]
        focus_clause = " OR ".join(f'all:"{term}"' for term in selected)
        return f"cat:cs.CV AND {domain_clause} AND ({focus_clause})"

    terms = sorted(_keywords(profile_text))[:10]
    if not terms:
        return "cat:cs.CV AND all:transformer"
    query = " OR ".join(f'all:"{term}"' if "-" in term else f"all:{term}" for term in terms)
    return f"cat:cs.CV AND ({query})"


def _best_area(text: str, project: dict[str, Any]) -> tuple[str, int]:
    scores: dict[str, int] = {}
    project_hints = {
        "Backbone": project.get("backbone", ""),
        "Neck": project.get("neck", ""),
        "Head": project.get("head", ""),
        "Data": project.get("dataset", ""),
    }
    for area, config in AREAS.items():
        score = sum(1 for signal in config["signals"] if signal in text)
        hint = str(project_hints.get(area, "")).lower()
        if hint and hint in text:
            score += 3
        scores[area] = score
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "Experiment", 0
    return best, scores[best]


def _subtag(area: str, text: str) -> str:
    if area == "Backbone" and any(word in text for word in ["layer", "shallow", "deep"]):
        return "Layer-wise Attention"
    if area == "Neck" and any(word in text for word in ["fusion", "fpn", "pyramid", "multi-scale", "multiscale"]):
        return "Feature Fusion"
    if area == "Loss" and any(word in text for word in ["small object", "imbalance", "reweight"]):
        return "Small-object Reweighting"
    if area == "Experiment" and "ablation" in text:
        return "Ablation"
    return AREAS[area]["tags"][0]


def _material_type(text: str) -> str:
    scores = {
        material_type: sum(1 for signal in signals if signal in text)
        for material_type, signals in TYPE_SIGNALS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "idea"


def _relevance_score(text: str, project: dict[str, Any]) -> float:
    profile_text = " ".join(str(value) for value in project.values()).lower()
    if _is_remote_sensing_project(profile_text):
        domain_hits = _signal_hits(text, REMOTE_DOMAIN_SIGNALS)
        task_hits = _signal_hits(text, VISION_TASK_SIGNALS)
        target_task_hits = _signal_hits(text, _project_task_signals(project))
        method_hits = _signal_hits(text, METHOD_SIGNALS)
        project_hits = _project_alignment_hits(text, project)
        negative_hits = _signal_hits(text, UNRELATED_DOMAIN_SIGNALS)
        score = (
            10
            + min(domain_hits * 22, 40)
            + min(target_task_hits * 18, 30)
            + min(task_hits * 5, 10)
            + min(method_hits * 5, 15)
            + min(project_hits * 4, 16)
        )
        score -= min(negative_hits * 18, 36)
        return round(max(0, min(score, 100)), 1)

    project_terms = _keywords(
        " ".join(
            str(project.get(field, ""))
            for field in ["domain", "task_type", "idea", "keywords", "backbone", "neck", "head", "dataset"]
        )
    )
    if not project_terms:
        return 40.0
    hits = sum(1 for term in project_terms if term in text)
    return round(min(35 + hits / len(project_terms) * 65, 100), 1)


def _relevance_gate(text: str, project: dict[str, Any], relevance: float) -> tuple[bool, str, str]:
    profile_text = " ".join(str(value) for value in project.values()).lower()
    if not _is_remote_sensing_project(profile_text):
        if relevance >= 65:
            return True, "direct", "项目关键词高度覆盖，判定为直接相关"
        if relevance >= 45:
            return True, "transferable", "项目关键词部分覆盖，可作为迁移素材"
        if relevance >= 30:
            return False, "reference", "关键词覆盖有限，仅作为补充参考"
        return False, "irrelevant", "关键词覆盖不足"

    domain_hits = [signal for signal in REMOTE_DOMAIN_SIGNALS if signal in text]
    task_hits = [signal for signal in VISION_TASK_SIGNALS if signal in text]
    target_task_hits = [signal for signal in _project_task_signals(project) if signal in text]
    method_hits = [signal for signal in METHOD_SIGNALS if signal in text]
    unrelated_hits = [signal for signal in UNRELATED_DOMAIN_SIGNALS if signal in text]

    if domain_hits and target_task_hits:
        return True, "direct", (
            f"同时命中遥感领域与当前任务：{', '.join((domain_hits + target_task_hits)[:3])}"
        )
    if domain_hits and method_hits:
        return True, "transferable", (
            f"命中遥感领域与可迁移方法：{', '.join((domain_hits + method_hits)[:3])}"
        )
    if task_hits and method_hits and not unrelated_hits:
        return True, "transferable", "未直接命中遥感词，但任务与方法均匹配，可跨领域迁移"
    if domain_hits:
        return False, "reference", f"仅命中遥感领域证据：{', '.join(domain_hits[:2])}"
    if unrelated_hits:
        return False, "irrelevant", f"疑似来自无关领域：{', '.join(unrelated_hits[:2])}"
    return False, "irrelevant", "缺少遥感领域证据，且未同时命中视觉任务与可迁移方法"


def _is_remote_sensing_project(text: str) -> bool:
    return any(
        signal in text
        for signal in ["遥感", "remote sensing", "earth observation", "dota", "dior", "nwpu"]
    )


def _signal_hits(text: str, signals: list[str]) -> int:
    return sum(1 for signal in signals if signal in text)


def _project_task_signals(project: dict[str, Any]) -> list[str]:
    task = str(project.get("task_type") or "").lower()
    if any(signal in task for signal in ["变化检测", "change detection"]):
        return ["change detection"]
    if any(signal in task for signal in ["语义分割", "semantic segmentation"]):
        return ["semantic segmentation"]
    if any(signal in task for signal in ["实例分割", "instance segmentation"]):
        return ["instance segmentation"]
    if any(signal in task for signal in ["目标检测", "object detection", "detection"]):
        return ["object detection", "small object", "tiny object", "oriented object"]
    return VISION_TASK_SIGNALS


def _project_alignment_hits(text: str, project: dict[str, Any]) -> int:
    generic = {
        "remote",
        "sensing",
        "image",
        "images",
        "object",
        "detection",
        "segmentation",
        "feature",
    }
    terms = _keywords(
        " ".join(
            str(project.get(field) or "")
            for field in ["idea", "keywords", "backbone", "neck", "head", "dataset"]
        )
    ) - generic
    return sum(1 for term in terms if term in text)


def _stitchability_score(
    area_score: int,
    relevance: float,
    code_availability: float,
    text: str,
    project: dict[str, Any],
) -> float:
    component_bonus = 0
    for field in ["backbone", "neck", "head", "dataset"]:
        value = str(project.get(field, "")).lower()
        if value and value in text:
            component_bonus += 6
    score = 25 + min(area_score * 9, 30) + relevance * 0.25 + code_availability * 0.12 + component_bonus
    return round(min(score, 100), 1)


def _code_score(text: str) -> float:
    if any(signal in text for signal in ["github", "code is available", "open-source", "repository"]):
        return 80.0
    if any(signal in text for signal in ["implementation", "framework", "pytorch", "tensorflow"]):
        return 55.0
    return 25.0


def _difficulty(area: str, text: str, project: dict[str, Any]) -> str:
    if area in {"Loss", "Experiment", "Training"}:
        return "低"
    if any(str(project.get(field, "")).lower() in text for field in ["backbone", "neck", "head"] if project.get(field)):
        return "中"
    if area in {"Backbone", "Head"}:
        return "高"
    return "中"


def _stitch_action(area: str, subtag: str, material_type: str, project: dict[str, Any]) -> str:
    task = project.get("task_type") or "当前任务"
    backbone = project.get("backbone") or "当前 backbone"
    neck = project.get("neck") or "当前 neck"
    templates = {
        "Backbone": f"优先评估其对 {backbone} 表征层的改造价值，关注浅层/深层特征是否能服务 {task}。",
        "Neck": f"优先尝试把 {subtag} 思路放到 {neck} 的特征融合路径中，观察多尺度目标特征是否更稳定。",
        "Head": f"把该素材作为检测/分割头的候选改造点，先做局部替换或辅助分支实验。",
        "Loss": "将该损失或监督信号作为附加项接入训练，先做小权重 ablation，避免破坏 baseline。",
        "Data": "把该数据或增强策略作为补充实验入口，优先验证对小目标和尺度分布的影响。",
        "Training": "把该训练策略作为低侵入实验，先固定模型结构，只观察收敛和指标变化。",
        "Experiment": "把该工作转成对比实验或消融模板，用来证明你的模块改动是否真的有效。",
    }
    action = templates.get(area, "把该素材作为补充阅读，人工判断可缝合位置。")
    if material_type == "code":
        action += " 若后续找到代码仓库，优先检查依赖框架、模型接口和配置文件。"
    return action


def _evidence(title: str, abstract: str, area: str, project: dict[str, Any]) -> tuple[str, str]:
    sources = ["标题", "摘要"]
    signals = AREAS[area]["signals"] + list(_keywords(project.get("keywords", "")))
    sentences = _split_sentences(abstract)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(signal in lowered for signal in signals):
            return "、".join(sources), sentence[:240]
    return "、".join(sources), title[:240]


def _keywords(text: str) -> set[str]:
    stopwords = {
        "and",
        "for",
        "from",
        "image",
        "images",
        "the",
        "this",
        "with",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    return {word for word in words if word not in stopwords}


def _split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", normalized) if piece.strip()]
