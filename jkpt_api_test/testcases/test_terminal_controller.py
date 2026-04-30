# testcases/test_terminal_controller.py
import jsonpath
import pytest
import time
import re
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result
from common.common_data import get_current_datetime

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()


class TestTerminalController:
    """设备管理接口测试 (Terminal Controller)"""

    test_data = read_yaml("./yaml/test_terminal_controller.yaml")
    _first_addr_extracted = False  # 控制只提取第一个成功的设备地址

    # ==================== 添加单个设备 ====================
    @pytest.mark.parametrize("case", test_data["add_terminal_cases"])
    def test_add_terminal(self, base_url, auth_headers, group_fixture, case):
        """添加单个设备"""
        group_id = group_fixture.get("three_id") if "{{three_id}}" in str(case.get("groupId")) else case.get("groupId")
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
        headers = {**auth_headers, "Content-Type": "application/json"}

        terminal_data = {
            "addr": case.get("addr", ""),
            "remark": case.get("remark", ""),
            "useScope": case.get("useScope", "ANIMAL"),
            "sn": case.get("sn", ""),
            "password": case.get("password", ""),
            "trackColor": case.get("trackColor", "#141323"),
            "trackSize": case.get("trackSize", 5),
            "gatewayParam": case.get("gatewayParam"),
            "fieldJson": case.get("fieldJson", {}),
            "fields": case.get("fields", [])
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=terminal_data, headers=headers)
        res = http.send_request(
            "post", url,
            json=terminal_data,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        # 成功时提取 addr 供后续编辑用例使用
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0 and not self._first_addr_extracted:
            terminal_addr = _jsonpath_parse(json_data, "$.data.addr")
            if terminal_addr:
                write_yaml("./extract.yaml", {"devices_addr": terminal_addr[0]}, mode="append")
                self._first_addr_extracted = True

        self._assert_and_report(case, res)

    # ==================== 编辑设备 ====================
    @pytest.mark.parametrize("case", test_data["update_terminal_cases"])
    def test_update_terminal(self, base_url, auth_headers, group_fixture, case):
        """编辑设备"""
        group_id = group_fixture.get("three_id") if "{{three_id}}" in str(case.get("groupId")) else case.get("groupId")
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
        headers = {**auth_headers, "Content-Type": "application/json"}

        devices_addr = self._resolve_value("{{devices_addr}}", required=True)

        terminal_data = {
            "addr": devices_addr,
            "remark": case.get("remark", ""),
            "useScope": case.get("useScope", "ANIMAL"),
            "sn": case.get("sn", ""),
            "password": case.get("password", ""),
            "trackColor": case.get("trackColor", "#141323"),
            "trackSize": case.get("trackSize", 5),
            "gatewayParam": case.get("gatewayParam"),
            "fieldJson": case.get("fieldJson", {}),
            "fields": case.get("fields", [])
        }

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, json=terminal_data, headers=headers)
        res = http.send_request(
            "put", url,
            json=terminal_data,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        self._assert_and_report(case, res)

    # ==================== 手动输入SN码批量添加 ====================
    @pytest.mark.parametrize("case", test_data["batch_add_terminals_cases"])
    def test_batch_add_terminals(self, base_url, auth_headers, group_fixture, case):
        """手动输入SN码批量添加"""
        group_id = group_fixture.get("two_id") if "{{two_id}}" in str(case.get("groupId")) else case.get("groupId")
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals/batch"
        headers = {**auth_headers, "Content-Type": "application/json"}

        items = []
        yaml_items = case.get("item", [])
        for yaml_item in yaml_items:

            items.append({
                "sn": yaml_item.get("sn", ""),
                "remark": yaml_item.get("remark", ""),
                "password": yaml_item.get("password", "")
            })

        batch_data = {
            "useScope": case.get("useScope", "TRAIN"),
            "item": items,
            "gatewayParam": case.get("gatewayParam")
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=batch_data, headers=headers)
        res = http.send_request(
            "post", url,
            json=batch_data,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            added_terminals = _jsonpath_parse(json_data, "$.data.addedTerminals")
            if added_terminals and len(added_terminals) > 0:
                addrs = [t.get("addr") for t in added_terminals if isinstance(t, dict)]
                if addrs:
                    write_yaml("./extract.yaml", {"addrList": ",".join(addrs)}, mode="append")

        self._assert_and_report(case, res)

    # ==================== 关注/收藏设备 ====================
    @pytest.mark.parametrize("case", test_data["follow_terminal_cases"])
    def test_follow_terminal(self, base_url, auth_headers, group_fixture, case):
        """关注/收藏设备"""
        group_id = group_fixture.get("three_id") if "{{three_id}}" in str(case.get("groupId")) else case.get("groupId")
        devices_addr = self._resolve_value("{{devices_addr}}", required=True)
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals/{devices_addr}/follow"
        headers = {**auth_headers}

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, headers=headers)
        res = http.send_request(
            "put", url,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        self._assert_and_report(case, res)

    # ==================== 移动设备分组(单个) ====================
    @pytest.mark.parametrize("case", test_data["move_terminal_cases"])
    def test_move_terminal(self, base_url, auth_headers, group_fixture, case):
        """移动设备分组"""
        group_id = group_fixture.get("three_id") if "{{three_id}}" in str(case.get("groupId")) else case.get("groupId")
        new_group_id = group_fixture.get("one_id") if "{{one_id}}" in str(case.get("newGroupId")) else case.get("newGroupId")
        devices_addr = self._resolve_value("{{devices_addr}}", required=True)
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals/{devices_addr}/move"
        headers = {**auth_headers}

        params = {"newGroupId": new_group_id}

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, params=params, headers=headers)
        res = http.send_request(
            "put", url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        self._assert_and_report(case, res)
    
    # ==================== 分页获取分组下设备列表 ====================
    @pytest.mark.parametrize("case", test_data["list_terminals_cases"])
    def test_list_terminals(self, base_url, auth_headers, group_fixture, case):
        """分页获取分组下设备列表"""
        group_id = group_fixture.get("two_id") if "{{two_id}}" in str(case.get("groupId")) else case.get("groupId")
        url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers.pop("Authorization", None)

        params = {
            "addr": case.get("addr", ""),
            "page": case.get("page", 1),
            "pageSize": case.get("pageSize", 100),
        }

        sep(f" 测试用例: {case['name']}")
        print_request("GET", url, params=params, headers=headers)
        res = http.send_request(
            "get", url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        self._assert_and_report(case, res)

    # ==================== 辅助方法 ====================
    def _resolve_value(self, yaml_value, required=False):
        """
        解析YAML中的变量占位符
        占位符格式: {{variable_name}}
        """
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

    def _assert_and_report(self, case, res):
        """统一断言并输出报告"""
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

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
            actual_msg=msg
        )

    def _get_variable(self, key_name):
        """从extract.yaml获取变量，不存在则返回None"""
        try:
            data = read_yaml("./extract.yaml")
            return data.get(key_name)
        except:
            return None
