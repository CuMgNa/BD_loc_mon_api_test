# api_test_framework/data.py
import yaml
import json
import os
from typing import Any, Dict, List, Union


class VariableStore:
    """内存变量存储，支持 {{var}} 占位符解析"""

    def __init__(self, initial_data: Dict = None):
        self.data = initial_data or {}

    def set(self, key: str, value: Any):
        """存储变量"""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取变量"""
        return self.data.get(key, default)

    def resolve(self, data: Union[str, Dict, List]) -> Union[str, Dict, List]:
        """递归解析 {{var}} 占位符"""
        if isinstance(data, str):
            for key, value in self.data.items():
                placeholder = f"{{{{{key}}}}}"
                if placeholder in data:
                    data = data.replace(placeholder, str(value))
            return data
        elif isinstance(data, dict):
            return {k: self.resolve(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.resolve(item) for item in data]
        return data

    def clear(self):
        """清空所有变量"""
        self.data = {}


def read_yaml(file_path: str) -> Dict:
    """读取YAML文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def write_yaml(file_path: str, data: Dict):
    """写入YAML文件（追加模式）"""
    existing = {}
    if os.path.exists(file_path):
        existing = read_yaml(file_path)
    existing.update(data)
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(existing, f, allow_unicode=True)


def clear_yaml(file_path: str = "./extract.yaml"):
    """清空extract.yaml"""
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump({}, f)


def read_json(file_path: str) -> Dict:
    """读取JSON文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(file_path: str, data: Dict):
    """写入JSON文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)