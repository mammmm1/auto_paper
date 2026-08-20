from __future__ import annotations

import ast
from typing import Any


CONFIG_AREA_KEYS = {
    "Backbone": {"backbone", "encoder"},
    "Neck": {"decoder", "feature_fusion", "neck"},
    "Head": {
        "auxiliary_head",
        "bbox_head",
        "decode_head",
        "detection_head",
        "head",
        "mask_head",
        "roi_head",
        "rpn_head",
        "seg_head",
    },
    "Loss": {
        "criterion",
        "loss",
        "loss_aux",
        "loss_bbox",
        "loss_cls",
        "loss_decode",
        "loss_mask",
    },
    "Data": {
        "data",
        "data_preprocessor",
        "dataloader",
        "dataset",
        "pipeline",
        "test_dataloader",
        "train_dataloader",
        "val_dataloader",
    },
    "Training": {"optim_wrapper", "optimizer", "param_scheduler", "train_cfg", "train_loop"},
    "Experiment": {"default_hooks", "env_cfg", "test_cfg", "val_cfg", "visualizer"},
}

IMPORTANT_CONFIG_PARAMETERS = {
    "type",
    "in_channels",
    "out_channels",
    "num_outs",
    "out_indices",
    "embed_dims",
    "strides",
    "featmap_strides",
    "in_index",
    "num_classes",
    "input_size",
    "img_scale",
    "crop_size",
    "size",
    "channels",
    "pool_scales",
    "dilations",
    "align_corners",
    "ignore_index",
    "mean",
    "std",
    "bgr_to_rgb",
    "pad_val",
    "seg_pad_val",
    "use_sigmoid",
    "loss_weight",
    "frozen_stages",
    "norm_cfg",
    "init_cfg",
}


def inspect_python_tree(tree: ast.Module, relative_path: str) -> dict[str, Any]:
    classes = []
    registrations = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        registration = _registration(node)
        constructor = next(
            (item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "__init__"),
            None,
        )
        forward = next(
            (
                item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "forward"
            ),
            None,
        )
        class_info = {
            "name": node.name,
            "path": relative_path,
            "line": node.lineno,
            "bases": [_dotted_name(base) for base in node.bases if _dotted_name(base)],
            "registry": registration.get("registry", ""),
            "registered_name": registration.get("name", ""),
            "constructor": _signature(constructor) if constructor else {"parameters": [], "defaults": {}},
            "interface": _forward_contract(forward),
        }
        classes.append(class_info)
        if registration:
            registrations.append(
                {
                    "registry": registration["registry"],
                    "name": registration["name"] or node.name,
                    "class_name": node.name,
                    "path": relative_path,
                    "line": node.lineno,
                }
            )

    config_file = _python_config(tree, relative_path)
    return {
        "classes": classes,
        "registrations": registrations,
        "config_file": config_file,
    }


def build_code_graph(
    components: list[dict[str, Any]],
    registrations: list[dict[str, Any]],
    config_files: list[dict[str, Any]],
    frameworks: set[str],
) -> dict[str, Any]:
    source_components = [item for item in components if item.get("kind") == "class"]
    links = []
    unresolved = []
    for config_file in config_files:
        for config_component in config_file.get("components") or []:
            configured_type = str(config_component.get("type") or "")
            if not configured_type:
                continue
            candidates = [
                item
                for item in source_components
                if _normalize_symbol(item.get("name")) == _normalize_symbol(configured_type)
                or _normalize_symbol(item.get("registered_name")) == _normalize_symbol(configured_type)
            ]
            if candidates:
                target = max(candidates, key=lambda item: int(item.get("confidence") or 0))
                links.append(
                    {
                        "area": config_component.get("area") or target.get("area"),
                        "type": configured_type,
                        "config_path": config_file["path"],
                        "config_key": config_component.get("config_key") or "",
                        "config_line": config_component.get("line") or 1,
                        "source_path": target.get("path") or "",
                        "source_line": target.get("line") or 1,
                        "symbol": target.get("name") or configured_type,
                        "registry": target.get("registry") or "",
                        "confidence": 95 if target.get("registry") else 88,
                    }
                )
            else:
                unresolved.append(
                    {
                        "area": config_component.get("area") or "",
                        "type": configured_type,
                        "config_path": config_file["path"],
                        "config_key": config_component.get("config_key") or "",
                    }
                )

    framework_set = set(frameworks)
    if "MMSegmentation" in framework_set:
        adapter = "mmsegmentation"
        adapter_label = "MMSegmentation / MMEngine"
    elif "MMDetection" in framework_set:
        adapter = "mmdetection"
        adapter_label = "MMDetection / MMEngine"
    elif "OpenMMLab" in framework_set or any(
        item.get("registry") in {"MODELS", "DATASETS", "TRANSFORMS"}
        for item in registrations
    ):
        adapter = "mmengine"
        adapter_label = "MMEngine"
    elif "PyTorch" in framework_set:
        adapter = "pytorch"
        adapter_label = "PyTorch"
    else:
        adapter = "generic_python"
        adapter_label = "Generic Python"

    interface_count = sum(
        1
        for item in source_components
        if (item.get("interface") or {}).get("parameters")
    )
    unique_registrations = _unique_dicts(registrations, ("registry", "name", "path"))
    unique_links = _unique_dicts(links, ("config_path", "config_key", "source_path", "symbol"))
    unique_unresolved = _unique_dicts(unresolved, ("config_path", "config_key", "type"))
    return {
        "adapter": adapter,
        "adapter_label": adapter_label,
        "config_files": config_files,
        "registrations": unique_registrations,
        "links": unique_links,
        "unresolved": unique_unresolved,
        "summary": {
            "config_file_count": len(config_files),
            "registration_count": len(unique_registrations),
            "link_count": len(unique_links),
            "unresolved_count": len(unique_unresolved),
            "interface_count": interface_count,
        },
    }


def _registration(node: ast.ClassDef) -> dict[str, str]:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        dotted = _dotted_name(target)
        if not dotted or not dotted.endswith(".register_module"):
            continue
        registry = dotted.rsplit(".", 1)[0].split(".")[-1]
        registered_name = ""
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if keyword.arg == "name":
                    value = _safe_value(keyword.value)
                    if isinstance(value, str):
                        registered_name = value
        return {"registry": registry, "name": registered_name}
    return {}


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    arguments = [*node.args.posonlyargs, *node.args.args]
    names = [item.arg for item in arguments if item.arg not in {"self", "cls"}]
    defaults = {}
    offset = len(arguments) - len(node.args.defaults)
    for index, default in enumerate(node.args.defaults, start=offset):
        if index < len(arguments) and arguments[index].arg not in {"self", "cls"}:
            defaults[arguments[index].arg] = _safe_value(default)
    if node.args.vararg:
        names.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        names.append(f"**{node.args.kwarg.arg}")
    return {"parameters": names, "defaults": defaults}


def _forward_contract(node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> dict[str, Any]:
    if node is None:
        return {"parameters": [], "returns": [], "line": 0, "annotation": ""}
    signature = _signature(node)
    returns = []
    for item in ast.walk(node):
        if isinstance(item, ast.Return):
            return_kind = _return_kind(item.value)
            if return_kind and return_kind not in returns:
                returns.append(return_kind)
    annotation = ""
    if node.returns is not None:
        try:
            annotation = ast.unparse(node.returns)[:120]
        except (ValueError, TypeError):
            annotation = ""
    return {
        "parameters": signature["parameters"],
        "returns": returns,
        "line": node.lineno,
        "annotation": annotation,
    }


def _python_config(tree: ast.Module, relative_path: str) -> dict[str, Any] | None:
    bases = []
    components = []
    found_config = False
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) and node.targets else node.target
        if not isinstance(target, ast.Name):
            continue
        value_node = node.value
        if value_node is None:
            continue
        if target.id == "_base_":
            raw_bases = _safe_value(value_node)
            if isinstance(raw_bases, str):
                bases.append(raw_bases)
            elif isinstance(raw_bases, list):
                bases.extend(str(item) for item in raw_bases if isinstance(item, str))
            found_config = True
            continue
        if target.id not in {
            "model",
            "train_dataloader",
            "val_dataloader",
            "test_dataloader",
            "optim_wrapper",
            "param_scheduler",
            "train_cfg",
            "val_cfg",
            "test_cfg",
        }:
            continue
        value = _safe_value(value_node)
        if isinstance(value, dict):
            found_config = True
            components.extend(_config_components(value, target.id, relative_path, node.lineno))
    if not found_config:
        return None
    return {"path": relative_path, "bases": bases, "components": components}


def _config_components(
    value: dict[str, Any],
    key_path: str,
    relative_path: str,
    line: int,
) -> list[dict[str, Any]]:
    components = []
    area = _config_area(key_path)
    configured_type = value.get("type")
    if area and (configured_type or key_path != "model"):
        components.append(
            {
                "area": area,
                "type": str(configured_type or ""),
                "config_key": key_path,
                "path": relative_path,
                "line": line,
                "parameters": {
                    key: child
                    for key, child in value.items()
                    if key in IMPORTANT_CONFIG_PARAMETERS and _is_serializable_value(child)
                },
            }
        )
    for key, child in value.items():
        if isinstance(child, dict):
            components.extend(_config_components(child, f"{key_path}.{key}", relative_path, line))
        elif isinstance(child, list):
            for index, entry in enumerate(child):
                if isinstance(entry, dict):
                    components.extend(
                        _config_components(entry, f"{key_path}.{key}[{index}]", relative_path, line)
                    )
    return components


def _config_area(key_path: str) -> str:
    ordered_parts = [
        part.lower()
        for part in key_path.replace("[", ".").replace("]", "").split(".")
        if part and not part.isdigit()
    ]
    if ordered_parts:
        leaf = ordered_parts[-1]
        for area, keys in CONFIG_AREA_KEYS.items():
            if leaf in keys:
                return area
    parts = set(ordered_parts)
    for area, keys in CONFIG_AREA_KEYS.items():
        if parts.intersection(keys):
            return area
    return ""


def _safe_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_safe_value(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            key = _safe_value(key_node) if key_node is not None else None
            if isinstance(key, (str, int, float, bool)):
                result[str(key)] = _safe_value(value_node)
        return result
    if isinstance(node, ast.Call) and _dotted_name(node.func) == "dict":
        return {
            str(keyword.arg): _safe_value(keyword.value)
            for keyword in node.keywords
            if keyword.arg is not None
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _safe_value(node.operand)
        if isinstance(operand, (int, float)):
            return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.Name):
        return f"${node.id}"
    return None


def _return_kind(node: ast.AST | None) -> str:
    if node is None:
        return "none"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Name):
        return f"symbol:{node.id}"
    dotted = _dotted_name(node)
    if dotted:
        return f"symbol:{dotted}"
    if isinstance(node, ast.Call):
        called = _dotted_name(node.func) or "unknown"
        return called if called in {"dict", "list", "tuple"} else f"call:{called}"
    return node.__class__.__name__.lower()


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _normalize_symbol(value: Any) -> str:
    return "".join(character.lower() for character in str(value or "") if character.isalnum())


def _is_serializable_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_serializable_value(item) for item in value)
    if isinstance(value, dict):
        return all(_is_serializable_value(item) for item in value.values())
    return False


def _unique_dicts(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    unique = {}
    for item in items:
        unique[tuple(item.get(key) for key in keys)] = item
    return list(unique.values())
