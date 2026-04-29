"""
test_xxx.py — 简单无状态接口模板（模式A）
适用场景: 登录、查询等接口之间无依赖的测试
从 api-test-framework Skill 生成
"""

import jsonpath
import pytest
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml
from common.allure_assert_util import assert_api_result


class Test_xxxAPI:
    """
    XXX接口测试
    
    接口信息:
      - 路径: /api/your/endpoint
      - 方法: POST
      - 认证: 是/否
    """

    # 1️⃣ 从YAML读取数据（key要与yaml中的顶层key一致）
    test_data = read_yaml("./yaml/test_xxx.yaml")["xxx_cases"]

    # 2️⃣ 参数化驱动 — 每行数据生成一个独立测试
    @pytest.mark.parametrize("case", test_data)
    def test_xxx(self, base_url, case):   # 3️⃣ 注入fixture（需要认证则加 auth_headers）
        # 4️⃣ 构造请求URL和参数
        url = f"{base_url}/api/your/endpoint"
        payload = {
            "field1": case["field1"],
            "field2": case["field2"],
        }

        # 5️⃣ 发送请求
        res = BaseRequest().send_request(
            method="post",
            url=url,
            params=payload,              # query参数风格；或用 json=payload 发JSON
            # headers=auth_headers,       # 需要认证时取消注释并注入fixture
            case_name=case["name"],       # 用于日志标识
            log_level="simple"            # full=调试 / simple=日常 / none=静默
        )

        # 6️⃣ 统一断言（自动处理成功/失败分支 + Allure附件）
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        msg = jsonpath.JSONPath("$.msg").parse(res.json())[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )
