"""
test_xxx.py — CRUD有状态接口模板（模式B′）
适用场景: 增删改查接口，使用 fixture + extract.yaml 管理依赖数据
从 api-test-framework Skill 生成
"""

import jsonpath
import pytest
import re
import time
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml
from common.allure_assert_util import assert_api_result

# 可选：生成唯一测试名（与 time.time() 二选一）
# from common.common_data import get_current_datetime

_jsonpath_parse = jsonpath.jsonpath   # ← 项目统一别名，使用函数式API


class Test_xxxAPI:
    """
    XXX管理接口测试（CRUD）

    接口信息:
      - 创建: POST   /api/xxx
      - 编辑: PUT    /api/xxx/{id}
      - 删除: DELETE /api/xxx/{id}
      - 查询: GET    /api/xxx

    数据依赖（模式B′）:
      - session级前置数据: 通过 conftest fixture 注入（如 group_fixture）
      - 同文件链路数据: 通过 extract.yaml 中转（如 created_id）
      - 不修改 parametrize 注入的 case 字典，在方法体内组装请求参数
    """

    # 仅用于控制首次提取，避免后续正向用例覆盖 extract.yaml 中的关键变量
    _first_id_extracted = False

    # 1️⃣ 从YAML读取数据
    test_data = read_yaml("./yaml/test_xxx.yaml")["cases"]

    # ==================== CREATE：创建 ====================
    # 与 test_data.tpl.yaml 对齐：cases[0:3]
    @pytest.mark.parametrize("case", test_data[:3])
    def test_create(self, base_url, auth_headers, case):
        # 不改 case，动态值在方法体内计算
        name_field = case.get("name_field", "")
        if "{int(time.time())}" in str(name_field):
            name_field = name_field.replace("{int(time.time())}", str(int(time.time())))
        # 若用 get_current_datetime() 生成唯一名：
        # if "{datetime}" in str(name_field):
        #     name_field = name_field.replace("{datetime}", get_current_datetime())

        url = f"{base_url}/api/xxx"
        payload = {
            "field1": name_field,
            # "field2": case.get("field2", ""),
            # ... 其它字段按接口补齐
        }

        res = BaseRequest().send_request(
            method="post", url=url, json=payload,
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

        # ⭐ 首次成功时提取ID写入 extract.yaml，供后续用例读取
        if code == 0 and not self._first_id_extracted:
            created_id = _jsonpath_parse(json_data, "$.data.id")
            if created_id:
                write_yaml("./extract.yaml", {"created_id": created_id[0]}, mode="append")
                self._first_id_extracted = True

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )

    # ==================== UPDATE：编辑（依赖CREATE）====================
    # 与 test_data.tpl.yaml 对齐：cases[3:5]
    @pytest.mark.parametrize("case", test_data[3:5])
    def test_update(self, base_url, auth_headers, case, group_fixture):
        # 优先使用YAML传入的id占位符（如 {{created_id}}），否则按场景兜底
        resource_id = self._resolve_value(case.get("id"), required=False)
        if resource_id is None and "编辑成功" in case.get("name", ""):
            resource_id = self._resolve_value("{{created_id}}", required=True)

        # 示例：若某些编辑场景依赖 fixture 前置数据，可在此按名称分支注入
        if "编辑非空资源" in case.get("name", "") and isinstance(group_fixture, dict):
            resource_id = group_fixture.get("one_id") or resource_id

        name_field = case.get("name_field", "")
        if "{int(time.time())}" in str(name_field):
            name_field = name_field.replace("{int(time.time())}", str(int(time.time())))

        url = f"{base_url}/api/xxx/{resource_id}"
        payload = {
            "id": resource_id,
            "field1": name_field,
            # ... 其它字段按接口补齐
        }

        res = BaseRequest().send_request(
            method="put", url=url,
            json=payload,                                 # 若接口是query参数，改为 params=payload
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )

    # ==================== DELETE：删除 ====================
    # 与 test_data.tpl.yaml 对齐：cases[5:]
    @pytest.mark.parametrize("case", test_data[5:])
    def test_delete(self, base_url, auth_headers, case, group_fixture):
        # 按名称分支选择依赖来源：extract.yaml 或 fixture
        case_name = case.get("name", "")
        resource_id = self._resolve_value(case.get("id"), required=False)

        if "删除成功-资源为空" in case_name:
            resource_id = self._resolve_value("{{created_id}}", required=True)
        elif "删除失败-资源非空" in case_name and isinstance(group_fixture, dict):
            resource_id = group_fixture.get("one_id") or resource_id

        if resource_id is None:
            pytest.skip("依赖的资源ID不存在，请先执行创建/前置fixture相关正向用例")

        url = f"{base_url}/api/xxx/{resource_id}"
        payload = {"id": resource_id}

        res = BaseRequest().send_request(
            method="delete", url=url,
            params=payload,
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )

    # ==================== 辅助方法 ====================
    def _resolve_value(self, yaml_value, required=False):
        """
        解析YAML中的变量占位符:
        - 占位符格式: {{variable_name}}
        - 如果是占位符，从extract.yaml读取
        - 如果不是占位符，直接返回原值
        """
        if yaml_value is None:
            return None

        if isinstance(yaml_value, str):
            match = re.match(r"^\\{\\{(\\w+)\\}\\}$", yaml_value)
            if match:
                var_name = match.group(1)
                value = self._get_variable(var_name)
                if value is None and required:
                    pytest.skip(f"依赖的变量 {var_name} 不存在，请先执行相关正向用例")
                return value

        return yaml_value

    def _get_variable(self, key_name):
        """从extract.yaml获取变量，不存在返回None"""
        try:
            data = read_yaml("./extract.yaml")
            return data.get(key_name)
        except Exception:
            return None
