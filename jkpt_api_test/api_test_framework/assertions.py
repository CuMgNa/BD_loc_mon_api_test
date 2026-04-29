# api_test_framework/assertions.py
import jsonpath
from typing import Any, Dict, List


def assert_response(response_data: Dict, assertions: Dict):
    """声明式断言引擎"""
    for key, expected in assertions.items():
        actual = jsonpath.JSONPath(key).parse(response_data)
        if actual:
            actual_value = actual[0]
            assert actual_value == expected, f"断言失败: {key} 预期 {expected}, 实际 {actual_value}"


def extract_json_path(data: Dict, path: str) -> List:
    """JSONPath提取"""
    result = jsonpath.JSONPath(path).parse(data)
    return result if result else []