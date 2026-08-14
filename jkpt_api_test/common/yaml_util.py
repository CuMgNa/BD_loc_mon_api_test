# common/yaml_util.py
import os
import re
from typing import Any, Dict

import pytest
import yaml

_EXTRACT_PLACEHOLDER = re.compile(r"^\{\{(\w+)\}\}$")


def read_yaml(file_path: str) -> Dict:
    """读取YAML文件，返回dict/list"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def write_yaml(file_path: str, data: Dict, mode: str = 'append'):
    """
    写入YAML文件

    Args:
        file_path: 文件路径
        data: 要写入的数据
        mode: 'append' 追加模式（合并现有数据），'overwrite' 覆盖模式
    """
    if mode == 'append' and os.path.exists(file_path):
        existing = read_yaml(file_path)
        existing.update(data)
        data = existing

    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def clear_yaml(file_path: str = "./extract.yaml"):
    """清空extract.yaml"""
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump({}, f, allow_unicode=True)


def is_extract_placeholder(yaml_value: Any) -> bool:
    if yaml_value is None or not isinstance(yaml_value, str):
        return False
    return bool(_EXTRACT_PLACEHOLDER.match(yaml_value.strip()))


def resolve_extract_value(
    yaml_value: Any,
    required: bool = False,
    extract_path: str = "./extract.yaml",
):
    """解析 YAML 中整段 `{{var}}` 占位符，从 extract.yaml 取值。

    required=True 且变量不存在时 pytest.skip。
    """
    if yaml_value is None:
        return None
    if isinstance(yaml_value, str):
        match = _EXTRACT_PLACEHOLDER.match(yaml_value.strip())
        if match:
            var_name = match.group(1)
            try:
                data = read_yaml(extract_path) or {}
            except Exception:
                data = {}
            value = data.get(var_name)
            if value is None and required:
                pytest.skip(f"依赖的变量 {var_name} 不存在，请先执行相关正向用例")
            return value
    return yaml_value


def read_expected_msg(expected: Any) -> str:
    """读 YAML expected 的文案：正向用 `msg`，负向用 `error_msg`。两者都有时优先 `msg`。"""
    if not isinstance(expected, dict):
        return ""
    if expected.get("msg") not in (None, ""):
        return str(expected["msg"])
    return str(expected.get("error_msg") or "")
