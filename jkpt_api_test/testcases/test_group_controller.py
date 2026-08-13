# testcases/test_group_controller.py
import jsonpath
import pytest
import time
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml, resolve_extract_value
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()


class TestGroupController:
    """分组管理接口测试 (Group Controller)"""

    test_data = read_yaml("./yaml/test_group_controller.yaml")

    # ==================== 添加分组-一级分组 ====================
    @pytest.mark.parametrize("case", test_data["add_group_l1_cases"])
    def test_add_group_level1(self, base_url, auth_headers, case):
        """添加分组-一级分组"""
        url = f"{base_url}/api/monitor/groups"
        headers = {**auth_headers}

        parent_id = resolve_extract_value(case.get("parentId"))

        group_name = case.get("groupName", "")
    
        params = {
            "groupName": group_name,
            "parentId": parent_id
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, params=params, headers=headers)
        res = http.send_request(
            "post", url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            one_id = _jsonpath_parse(json_data, "$.data.id")
            if one_id:
                write_yaml("./extract.yaml", {"one_id": one_id[0]}, mode="append")

        self._assert_and_report(case, res)

    # ==================== 添加分组-二级分组 ====================
    @pytest.mark.parametrize("case", test_data["add_group_l2_cases"])
    def test_add_group_level2(self, base_url, auth_headers, case):
        """添加分组-二级分组"""
        url = f"{base_url}/api/monitor/groups"
        headers = {**auth_headers}

        parent_id = resolve_extract_value(case.get("parentId"), required=True)

        group_name = case.get("groupName", "")

        params = {
            "groupName": group_name,
            "parentId": parent_id
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, params=params, headers=headers)
        res = http.send_request(
            "post", url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            two_id = _jsonpath_parse(json_data, "$.data.id")
            if two_id:
                write_yaml("./extract.yaml", {"two_id": two_id[0]}, mode="append")

        self._assert_and_report(case, res)

    # ==================== 添加分组-三级分组 ====================
    @pytest.mark.parametrize("case", test_data["add_group_l3_cases"])
    def test_add_group_level3(self, base_url, auth_headers, case):
        """添加分组-三级分组"""
        url = f"{base_url}/api/monitor/groups"
        headers = {**auth_headers}

        parent_id = resolve_extract_value(case.get("parentId"), required=True)

        group_name = case.get("groupName", "")

        params = {
            "groupName": group_name,
            "parentId": parent_id
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, params=params, headers=headers)
        res = http.send_request(
            "post", url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            three_id = _jsonpath_parse(json_data, "$.data.id")
            if three_id:
                write_yaml("./extract.yaml", {"three_id": three_id[0]}, mode="append")

        self._assert_and_report(case, res)

    # ==================== 获取分组列表 ====================
    @pytest.mark.parametrize("case", test_data["get_groups_cases"])
    def test_get_groups(self, base_url, auth_headers, case):
        """获取设备分组信息"""
        url = f"{base_url}/api/monitor/groups"

        if case.get("no_auth"):
            headers = {}
        else:
            headers = {**auth_headers}

        params = {
            "account": "",
            "include": "true",
            "queryType": "ALL",
            "terminalType": ""
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

        self._assert_and_report(case, res)

        # 正向用例：提取所有分组ID，降序拼接写入extract.yaml
        if case["name"] == "获取设备分组信息-正向":
            json_data = res.json()
            code = _jsonpath_parse(json_data, "$.code")[0]
            if code == 0:
                all_ids = _jsonpath_parse(json_data, "$.data[*].id")
                if all_ids:
                    sorted_ids_desc = sorted(all_ids, reverse=True)
                    group_ids_str = ",".join(str(i) for i in sorted_ids_desc)
                    write_yaml("./extract.yaml", {"parent_group_ids": group_ids_str}, mode="append")


    # ==================== 编辑分组名称 ====================
    @pytest.mark.parametrize("case", test_data["update_group_cases"])
    def test_update_group(self, base_url, auth_headers, case):
        """编辑分组名称"""
        group_id = resolve_extract_value(case.get("groupId"), required=True)
        url = f"{base_url}/api/monitor/groups/{group_id}"
        headers = {**auth_headers}
        group_name = case.get("groupName", "")

        if group_name:  # groupName 有值
            if "{int(time.time())}" in group_name:
                group_name = group_name.replace("{int(time.time())}", str(int(time.time())))
            params = {"groupName": group_name}
        else:  # groupName 为空或不存在
            params = {}

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

    # ==================== 分组排序 ====================
    @pytest.mark.parametrize("case", test_data["sort_groups_cases"])
    def test_sort_groups(self, base_url, auth_headers, case):
        """分组排序"""
        url = f"{base_url}/api/monitor/groups"
        headers = {**auth_headers}

        group_ids = resolve_extract_value(case.get("groupIds"), required=True)

        if group_ids:
            json_data = {"groupIds": group_ids}
        else:
            json_data = {}
        

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, json=json_data, headers=headers)
        res = http.send_request(
            "put", url,
            json=json_data,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        self._assert_and_report(case, res)
    
      # ==================== 删除分组 ====================
    @pytest.mark.parametrize("case", test_data["delete_group_cases"])
    def test_delete_group(self, base_url, auth_headers, case):
        """删除分组"""
        group_id = resolve_extract_value(case.get("groupId"), required=True)
        url = f"{base_url}/api/monitor/groups/{group_id}"
        headers = {**auth_headers}

        sep(f" 测试用例: {case['name']}")
        print_request("DELETE", url, headers=headers)
        res = http.send_request(
            "delete", url,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )
        print_response(res)

        self._assert_and_report(case, res)

    # ==================== 辅助方法 ====================
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
