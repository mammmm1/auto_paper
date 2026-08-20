from __future__ import annotations

import ast
import configparser
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "checkpoints",
    "dist",
    "env",
    "logs",
    "node_modules",
    "outputs",
    "runs",
    "site-packages",
    "tests",
    "venv",
    "wandb",
    "weights",
}

CONFIG_SUFFIXES = {".cfg", ".ini", ".json", ".toml", ".yaml", ".yml"}
IGNORED_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"}
MAX_FILES = 800
MAX_FILE_BYTES = 1_000_000
MAX_COMPONENTS = 160

AREA_KEYWORDS = {
    "Backbone": {"backbone", "backbones", "encoder", "encoders", "resnet", "swin", "transformer", "vit"},
    "Neck": {"bifpn", "decoder", "decoders", "feature", "fpn", "fusion", "neck", "necks", "pyramid"},
    "Head": {"classifier", "decodehead", "detection", "head", "heads", "predictor", "roi", "rpn"},
    "Loss": {"criterion", "criteria", "loss", "losses", "objective"},
    "Data": {"augment", "augmentation", "data", "dataloader", "dataset", "datasets", "pipeline", "transform", "transforms"},
    "Training": {"engine", "engines", "optimizer", "scheduler", "train", "trainer", "training"},
    "Experiment": {"config", "configs", "eval", "evaluate", "experiment", "inference", "test"},
}

FRAMEWORK_IMPORTS = {
    "detectron2": "Detectron2",
    "keras": "TensorFlow / Keras",
    "lightning": "PyTorch Lightning",
    "mmcv": "OpenMMLab",
    "mmdet": "MMDetection",
    "mmengine": "OpenMMLab",
    "pytorch_lightning": "PyTorch Lightning",
    "tensorflow": "TensorFlow / Keras",
    "torch": "PyTorch",
    "torchvision": "PyTorch",
    "transformers": "Hugging Face Transformers",
    "ultralytics": "Ultralytics",
}


def scan_codebase(path_value: str) -> dict[str, Any]:
    configured_path = str(path_value or "").strip()
    if not configured_path:
        return _empty_result("not_configured", "请先在项目画像中填写本地代码目录。")

    try:
        root = Path(configured_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return _empty_result("not_found", "代码目录不存在或当前进程无法访问。", configured_path)
    if not root.is_dir():
        return _empty_result("not_directory", "配置的代码路径不是目录。", str(root))

    components: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []
    frameworks: set[str] = set()
    files_scanned = 0
    python_files = 0
    config_files = 0
    skipped_large_files = 0
    parse_errors = 0
    truncated = False

    for path in _source_files(root):
        if files_scanned >= MAX_FILES:
            truncated = True
            break
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped_large_files += 1
                continue
        except OSError:
            continue

        files_scanned += 1
        relative_path = path.relative_to(root).as_posix()
        if path.suffix.lower() == ".py":
            python_files += 1
            parsed = _scan_python_file(path, relative_path)
            components.extend(parsed["components"])
            entrypoints.extend(parsed["entrypoints"])
            frameworks.update(parsed["frameworks"])
            parse_errors += int(parsed["parse_error"])
        else:
            config_files += 1
            components.extend(_scan_config_file(path, relative_path))

        if len(components) >= MAX_COMPONENTS:
            components = components[:MAX_COMPONENTS]
            truncated = True
            break

    components = _deduplicate_components(components)
    areas = list(dict.fromkeys(item["area"] for item in components))
    files_by_area = {
        area: list(dict.fromkeys(item["path"] for item in components if item["area"] == area))[:12]
        for area in AREA_KEYWORDS
        if any(item["area"] == area for item in components)
    }
    warnings = []
    if skipped_large_files:
        warnings.append(f"已跳过 {skipped_large_files} 个超过 1 MB 的源码或配置文件。")
    if parse_errors:
        warnings.append(f"有 {parse_errors} 个 Python 文件无法完成 AST 解析。")
    if truncated:
        warnings.append("仓库较大，当前结果已按安全上限截断。")
    if not components:
        warnings.append("未识别到模型组件；可检查目录是否指向 Python 训练工程根目录。")

    return {
        "status": "ready" if files_scanned else "empty",
        "root": str(root),
        "repository_name": root.name,
        "scanned_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "frameworks": sorted(frameworks),
        "areas": areas,
        "summary": {
            "files_scanned": files_scanned,
            "python_files": python_files,
            "config_files": config_files,
            "component_count": len(components),
            "entrypoint_count": len(entrypoints),
            "truncated": truncated,
        },
        "components": components,
        "entrypoints": _deduplicate_entries(entrypoints)[:30],
        "files_by_area": files_by_area,
        "warnings": warnings,
    }


def _source_files(root: Path):
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name.lower() not in IGNORED_DIRECTORIES and not name.startswith(".")
        )
        for file_name in sorted(file_names):
            if file_name.lower() in IGNORED_FILES:
                continue
            path = Path(directory) / file_name
            if path.suffix.lower() == ".py" or path.suffix.lower() in CONFIG_SUFFIXES:
                yield path


def _scan_python_file(path: Path, relative_path: str) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=relative_path)
    except (OSError, SyntaxError, ValueError):
        return {"components": [], "entrypoints": [], "frameworks": [], "parse_error": True}

    frameworks = set()
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for module in modules:
            root_module = module.split(".", 1)[0]
            if root_module in FRAMEWORK_IMPORTS:
                frameworks.add(FRAMEWORK_IMPORTS[root_module])

    definitions = [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    ranked = sorted(
        definitions,
        key=lambda node: (
            0 if isinstance(node, ast.ClassDef) else 1,
            0 if _classify_area(node.name)[0] else 1,
            node.lineno,
        ),
    )
    components = []
    for node in ranked[:6]:
        area, signals = _classify_area(f"{relative_path} {node.name}")
        if not area:
            continue
        confidence = min(96, 58 + len(signals) * 6 + (5 if isinstance(node, ast.ClassDef) else 0))
        components.append(
            {
                "area": area,
                "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                "name": node.name,
                "path": relative_path,
                "line": node.lineno,
                "confidence": confidence,
                "signals": signals[:4],
            }
        )

    path_area, path_signals = _classify_area(relative_path)
    if path_area and not components:
        components.append(
            {
                "area": path_area,
                "kind": "module",
                "name": path.stem,
                "path": relative_path,
                "line": 1,
                "confidence": min(78, 52 + len(path_signals) * 6),
                "signals": path_signals[:4],
            }
        )

    entrypoints = []
    stem = path.stem.lower()
    if stem in {"main", "train", "trainer", "eval", "evaluate", "test", "inference"}:
        entrypoints.append(
            {
                "kind": "entrypoint",
                "name": path.stem,
                "path": relative_path,
                "line": 1,
            }
        )
    return {
        "components": components,
        "entrypoints": entrypoints,
        "frameworks": frameworks,
        "parse_error": False,
    }


def _scan_config_file(path: Path, relative_path: str) -> list[dict[str, Any]]:
    keys = _structured_config_keys(path)
    detected: dict[str, tuple[str, list[str]]] = {}
    for key in keys:
        area, signals = _classify_area(key)
        if area and area not in detected:
            detected[area] = (key, signals)
    if not detected:
        area, signals = _classify_area(relative_path)
        if area:
            detected[area] = (path.stem, signals)
    return [
        {
            "area": area,
            "kind": "config",
            "name": key,
            "path": relative_path,
            "line": 1,
            "confidence": min(82, 56 + len(signals) * 6),
            "signals": signals[:4],
        }
        for area, (key, signals) in detected.items()
    ]


def _structured_config_keys(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return _mapping_keys(value)
        if suffix == ".toml":
            with path.open("rb") as handle:
                return _mapping_keys(tomllib.load(handle))
        if suffix in {".cfg", ".ini"}:
            parser = configparser.ConfigParser()
            parser.read(path, encoding="utf-8")
            return [*parser.sections(), *(key for section in parser.sections() for key in parser[section])]
    except (OSError, ValueError, json.JSONDecodeError, configparser.Error, tomllib.TOMLDecodeError):
        return []
    return []


def _mapping_keys(value: Any, depth: int = 0) -> list[str]:
    if not isinstance(value, dict) or depth > 4:
        return []
    keys = []
    for key, child in value.items():
        keys.append(str(key))
        keys.extend(_mapping_keys(child, depth + 1))
    return keys[:160]


def _classify_area(value: str) -> tuple[str, list[str]]:
    tokens = set(_tokens(value))
    scored = []
    for area, keywords in AREA_KEYWORDS.items():
        matches = sorted(tokens.intersection(keywords))
        if matches:
            scored.append((len(matches), area, matches))
    if not scored:
        return "", []
    _, area, matches = max(scored, key=lambda item: (item[0], -list(AREA_KEYWORDS).index(item[1])))
    return area, matches


def _tokens(value: str) -> list[str]:
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", expanded) if token]


def _deduplicate_components(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for item in items:
        key = (item["area"], item["path"], item["name"])
        if key not in unique or item["confidence"] > unique[key]["confidence"]:
            unique[key] = item
    return sorted(
        unique.values(),
        key=lambda item: (list(AREA_KEYWORDS).index(item["area"]), item["path"], item["line"]),
    )[:MAX_COMPONENTS]


def _deduplicate_entries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for item in items:
        unique[(item["kind"], item["path"])] = item
    return sorted(unique.values(), key=lambda item: item["path"])


def _empty_result(status: str, message: str, root: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "root": root,
        "repository_name": Path(root).name if root else "",
        "scanned_at": "",
        "frameworks": [],
        "areas": [],
        "summary": {
            "files_scanned": 0,
            "python_files": 0,
            "config_files": 0,
            "component_count": 0,
            "entrypoint_count": 0,
            "truncated": False,
        },
        "components": [],
        "entrypoints": [],
        "files_by_area": {},
        "warnings": [message],
    }
