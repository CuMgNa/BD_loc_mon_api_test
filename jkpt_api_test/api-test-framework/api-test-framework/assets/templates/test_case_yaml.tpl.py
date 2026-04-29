"""
test_xxx.py — 纯YAML驱动模式（模式C）
适用场景: 标准CRUD接口，无需复杂条件分支，一行run_case搞定
从 api-test-framework Skill 生成
"""

import pytest
from api_test_framework.runner import run_case
from api_test_framework.data import read_yaml, VariableStore
from api_test_framework.schema import ApiCase

# 全局变量存储（跨用例共享提取的值）
store = VariableStore()

# 读取YAML数据
test_cases = read_yaml("./yaml/test_xxx.yaml")["cases"]

@pytest.mark.parametrize("raw_case", test_cases)
def test_xxx(raw_case, base_url, auth_headers):
    """
    一行代码执行完整的用例生命周期:
    读取→变量替换→发请求→断言→提取变量
    """
    run_case(
        case=ApiCase.from_dict(raw_case),   # YAML dict → ApiCase
        base_url=base_url,
        headers=auth_headers,
        variables=store,
    )
