# common/yaml_util.py
import yaml
import os
from typing import Dict, Any


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