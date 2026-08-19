"""
test_xxx.py — 简单无状态接口模板（模式A）
适用: 单个接口（登录、单查询）。同一文件多个接口时改用 test_case_crud.tpl.py 的多类骨架。
从 api-test-framework Skill 生成

Allure Suites：一类 = 一个报告分组单元。单接口可以只有 Test01*。
parametrize 不要传 ids=；YAML name 只给日志/附件，不是树标题。
"""

import jsonpath
import pytest
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, read_expected_msg
from common.allure_assert_util import assert_api_result

_jsonpath_parse = jsonpath.jsonpath
_TEST_DATA = read_yaml("./yaml/test_xxx.yaml")
http = BaseRequest()


class Test01Xxx:
    """POST /api/your/endpoint — 单接口示例（类名补零便于 Suites 排序）"""

    @pytest.mark.parametrize("case", _TEST_DATA["xxx_cases"])
    def test_xxx(self, base_url, case):
        url = f"{base_url}/api/your/endpoint"
        payload = {
            "field1": case["field1"],
            "field2": case["field2"],
        }

        headers = None
        if not case.get("no_auth"):
            # 需要认证时：方法签名加 auth_headers，这里 headers = {**auth_headers}
            pass

        res = http.send_request(
            method="post",
            url=url,
            params=payload,
            headers=headers,
            case_name=case["name"],
            log_level="simple",
        )

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=read_expected_msg(case["expected"]),
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload},
        )
