"""
test_xxx.py — 纯YAML驱动模式（模式C）

⚠️ jkpt 项目未使用本模板，请勿复制到 jkpt 仓库。
   jkpt 用例统一使用模式 A（test_case_simple.tpl.py）或模式 B（test_case_crud.tpl.py）。
   协议用例使用 test_case_protocol.tpl.py。

本文件仅为其他独立项目参考保留。
"""

import pytest
from api_test_framework.runner import run_case
# 模式C使用框架层 read_yaml；手写用例模式A/B优先 common.yaml_util.read_yaml
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
