# testcases/test_field_template_controller.py
# 字段模板管理 — 方法名 test_ft_a_* … test_ft_e_* 保证 pytest 收集顺序 a→e
import jsonpath
import pytest
import re
import time
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()


class TestFieldTemplateController:
    """字段模板管理接口测试 - 共 5 个接口"""

    test_data = read_yaml("./yaml/test_field_template_controller.yaml")

    # ---------- a. 获取字段模板列表（GET /api/monitor/field-templates） ----------
    @pytest.mark.parametrize("case", test_data["list_field_templates_cases"])
    def test_ft_a_list_field_templates(self, base_url, auth_headers, case):
        """获取字段模板列表"""
        url = f"{base_url}/api/monitor/field-templates"
        if case.get("no_auth"):
            headers = {}
        else:
            headers = {**auth_headers}

        sep(f" 测试用例: {case['name']}")
        print_request("GET", url, headers=headers)
        res = http.send_request(
            "get",
            url,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- b. 新增字段模板（POST /api/monitor/field-templates） ----------
    @pytest.mark.parametrize("case", test_data["add_field_template_cases"])
    def test_ft_b_add_field_template(self, base_url, auth_headers, case):
        """新增模板；正向成功写入 extract.yaml 的 field_template_id"""
        url = f"{base_url}/api/monitor/field-templates"
        headers = {**auth_headers}
        tname = case.get("templateName") or ""
        if tname and "{int(time.time())}" in tname:
            tname = tname.replace("{int(time.time())}", str(int(time.time())))

        params = {"name": tname}

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, params=params, headers=headers)
        res = http.send_request(
            "post",
            url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0 and case.get("name") == "字段模板-创建-正向":
            tid = _jsonpath_parse(json_data, "$.data.id")
            if tid:
                write_yaml("./extract.yaml", {"field_template_id": tid[0]}, mode="append")

        self._assert_and_report(case, res)

    # ---------- c. 编辑字段模板名称（PUT /api/monitor/field-templates/{id}） ----------
    @pytest.mark.parametrize("case", test_data["update_field_template_cases"])
    def test_ft_c_update_field_template(self, base_url, auth_headers, case):
        """修改模板名称（query: name）"""
        raw_id = case.get("templateId")
        tid = self._resolve_value(raw_id, required=self._is_extract_placeholder(raw_id))
        url = f"{base_url}/api/monitor/field-templates/{tid}"
        headers = {**auth_headers}
        tname = case.get("templateName") or ""
        if tname and "{int(time.time())}" in tname:
            tname = tname.replace("{int(time.time())}", str(int(time.time())))

        params = {"name": tname}

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, params=params, headers=headers)
        res = http.send_request(
            "put",
            url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- d. 保存模板内字段名列表（POST /api/monitor/field-templates/{id}/fields） ----------
    @pytest.mark.parametrize("case", test_data["save_fields_cases"])
    def test_ft_d_save_fields(self, base_url, auth_headers, case):
        """写入/覆盖该模板下字段名（query: fields）；非删模板"""
        raw_id = case.get("templateId")
        tid = self._resolve_value(raw_id, required=self._is_extract_placeholder(raw_id))
        url = f"{base_url}/api/monitor/field-templates/{tid}/fields"
        headers = {**auth_headers}

        if case.get("omit_fields_query"):
            req_params = None
            log_params = {}
        else:
            fields = case.get("fields") or []
            req_params = [("fields", f) for f in fields]
            log_params = {"fields": fields}

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, params=log_params, headers=headers)
        res = http.send_request(
            "post",
            url,
            params=req_params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- e. 删除字段模板（DELETE /api/monitor/field-templates/{id}） ----------
    @pytest.mark.parametrize("case", test_data["delete_field_template_cases"])
    def test_ft_e_delete_field_template(self, base_url, auth_headers, case):
        """删除整张模板；非 /fields 保存、非删单个字段名接口"""
        raw_id = case.get("templateId")
        tid = self._resolve_value(raw_id, required=self._is_extract_placeholder(raw_id))
        url = f"{base_url}/api/monitor/field-templates/{tid}"
        headers = {**auth_headers}

        sep(f" 测试用例: {case['name']}")
        print_request("DELETE", url, headers=headers)
        res = http.send_request(
            "delete",
            url,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    @staticmethod
    def _is_extract_placeholder(yaml_value):
        if yaml_value is None or not isinstance(yaml_value, str):
            return False
        return bool(re.match(r"^\{\{\w+\}\}$", yaml_value))

    def _resolve_value(self, yaml_value, required=False):
        if yaml_value is None:
            return None
        if isinstance(yaml_value, str):
            match = re.match(r"^\{\{(\w+)\}\}$", yaml_value)
            if match:
                var_name = match.group(1)
                value = self._get_variable(var_name)
                if value is None and required:
                    pytest.skip(f"依赖的变量 {var_name} 不存在，请先执行相关正向用例")
                return value
        return yaml_value

    def _get_variable(self, key_name):
        try:
            data = read_yaml("./extract.yaml")
            return data.get(key_name)
        except Exception:
            return None

    def _assert_and_report(self, case, res):
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        raw_msg = _jsonpath_parse(json_data, "$.msg")
        msg = raw_msg[0] if raw_msg else "未知错误"

        sep(" 断言结果 ")
        key("预期 code", case["expected"]["code"])
        key("实际 code", code)
        key("预期 msg", case["expected"]["error_msg"])
        key("实际 msg", msg)

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
        )
