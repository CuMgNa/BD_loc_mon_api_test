# testcases/test_batch_terminal_controller.py
# 设备批量管理接口 — 方法名 test_batch_a_* … test_batch_h_* 保证 pytest 收集顺序 a→h
import io
import jsonpath
import os
import re
import pytest
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
_TEMPLATE_XLSX = r"C:\Users\33606\Desktop\jkpt_api_test\jkpt_api_test\yaml\import-device-template2026_5_1.xlsx"


class TestBatchTerminalController:
    """设备批量管理接口测试 - 共 8 个接口"""

    test_data = read_yaml("./yaml/test_batch_terminal_controller.yaml")
    _first_batch_addrs_written = False

    # ---------- a. 批量导入设备（POST /api/monitor/terminals/batch/import） ----------
    @pytest.mark.parametrize("case", test_data["batch_import_cases"])
    def test_batch_a_import(self, base_url, auth_headers, case):
        """批量导入设备（正向提取 batch_addrs 写入 extract.yaml）"""
        url = f"{base_url}/api/monitor/terminals/batch/import"
        headers = {**auth_headers}
        scenario = case.get("scenario", "positive")
        files = None

        if scenario == "positive":
            if not os.path.isfile(_TEMPLATE_XLSX):
                pytest.skip(f"缺少导入模板文件: {_TEMPLATE_XLSX}")
            with open(_TEMPLATE_XLSX, "rb") as fp:
                files = {
                    "importFile": (
                        os.path.basename(_TEMPLATE_XLSX),
                        fp,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }
                sep(f" 测试用例: {case['name']}")
                print_request("POST", url, headers=headers)
                res = http.send_request(
                    "post",
                    url,
                    headers=headers,
                    files=files,
                    case_name=case["name"],
                    log_level="none",
                )
        elif scenario == "no_file":
            sep(f" 测试用例: {case['name']}")
            print_request("POST", url, headers=headers)
            res = http.send_request(
                "post",
                url,
                headers=headers,
                case_name=case["name"],
                log_level="none",
            )
        elif scenario == "empty_file":
            files = {"importFile": ("empty.xlsx", io.BytesIO(b""), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            sep(f" 测试用例: {case['name']}")
            print_request("POST", url, headers=headers)
            res = http.send_request(
                "post",
                url,
                headers=headers,
                files=files,
                case_name=case["name"],
                log_level="none",
            )
        else:
            pytest.fail(f"未知场景类型: {scenario}")

        print_response(res)
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]

        if scenario == "positive" and code == 0 and not self._first_batch_addrs_written:
            addrs = _jsonpath_parse(json_data, "$.data.addedTerminals[*].addr") or []
            addrs = [addr for addr in addrs if addr]
            if addrs:
                write_yaml("./extract.yaml", {"batch_addrs": ",".join(addrs)}, mode="append")
                self._first_batch_addrs_written = True

        self._assert_and_report(case, res)

    # ---------- b. 批量查询设备详情（POST /api/monitor/terminals/batch/details） ----------
    @pytest.mark.parametrize("case", test_data["batch_details_cases"])
    def test_batch_b_query_details(self, base_url, auth_headers, case):
        """批量查询设备详细信息"""
        url = f"{base_url}/api/monitor/terminals/batch/details"
        headers = {**auth_headers, "Content-Type": "application/json"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)
        body = {"addrs": addrs}

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=body, headers=headers)
        res = http.send_request(
            "post",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- c. 批量查询设备备注（POST /api/monitor/terminals/batch/remark） ----------
    @pytest.mark.parametrize("case", test_data["batch_remark_cases"])
    def test_batch_c_query_remark(self, base_url, auth_headers, case):
        """批量查询设备备注信息"""
        url = f"{base_url}/api/monitor/terminals/batch/remark"
        headers = {**auth_headers, "Content-Type": "application/json"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)
        body = {"addrs": addrs}

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=body, headers=headers)
        res = http.send_request(
            "post",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- d. 聚合点批量查询设备详情（POST /api/monitor/terminals/batch/aggr-point-details） ----------
    @pytest.mark.parametrize("case", test_data["batch_aggr_point_cases"])
    def test_batch_d_aggr_point(self, base_url, auth_headers, case):
        """根据聚合点批量查询设备详细信息"""
        url = f"{base_url}/api/monitor/terminals/batch/aggr-point-details"
        headers = {**auth_headers, "Content-Type": "application/json"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)
        body = {
            "addrs": addrs,
            "page": case.get("page", 1),
            "pageSize": case.get("pageSize", 100),
        }

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=body, headers=headers)
        res = http.send_request(
            "post",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- e. 经纬度批量查询设备详情（POST /api/monitor/terminals/batch/lnglat-details） ----------
    @pytest.mark.parametrize("case", test_data["batch_lnglat_cases"])
    def test_batch_e_lnglat(self, base_url, auth_headers, case):
        """根据经纬度批量查询设备详细信息"""
        url = f"{base_url}/api/monitor/terminals/batch/lnglat-details"
        headers = {**auth_headers, "Content-Type": "application/json"}
        body = {
            "points": case.get("points") or [],
            "page": case.get("page", 1),
            "pageSize": case.get("pageSize", 100),
        }
        addr_val = case.get("addr")
        if addr_val:
            body["addr"] = addr_val

        sep(f" 测试用例: {case['name']}")
        print_request("POST", url, json=body, headers=headers)
        res = http.send_request(
            "post",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- f. 批量移动设备分组（PUT /api/monitor/terminals/batch/move-group） ----------
    @pytest.mark.parametrize("case", test_data["batch_move_group_cases"])
    def test_batch_f_move_group(self, base_url, auth_headers, group_fixture, case):
        """批量移动分组"""
        url = f"{base_url}/api/monitor/terminals/batch/move-group"
        headers = {**auth_headers, "Content-Type": "application/json"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)

        ng_raw = case.get("newGroupId")
        if "{{one_id}}" in str(ng_raw):
            new_gid = group_fixture.get("one_id")
        else:
            new_gid = ng_raw

        body = {"addrs": addrs, "newGroupId": new_gid}

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, json=body, headers=headers)
        res = http.send_request(
            "put",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- g. 批量导出设备信息（POST /api/monitor/terminals/batch/export） ----------
    @pytest.mark.parametrize("case", test_data["batch_export_cases"])
    def test_batch_g_export(self, base_url, auth_headers, case):
        """批量导出设备信息（成功为二进制流或 JSON 错误）"""
        url = f"{base_url}/api/monitor/terminals/batch/export"
        headers = {**auth_headers, "Content-Type": "application/json", "Time-Zone": "Asia/Shanghai"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)
        addr_list = [a.strip() for a in str(addrs).split(",") if a.strip()] if addrs else []

        sep(f" 测试用例: {case['name']}")
        key("请求方法", "POST")
        key("请求地址", url)
        key("请求体", addr_list)
        key("请求头", {k: ("******" if k.lower() == "authorization" else v) for k, v in headers.items()})
        res = http.send_request(
            "post",
            url,
            json=addr_list,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_export_response(case, res)

    # ---------- h. 批量解绑设备（DELETE /api/monitor/terminals/batch） ----------
    @pytest.mark.parametrize("case", test_data["batch_delete_cases"])
    def test_batch_h_delete(self, base_url, auth_headers, case):
        """批量解绑设备"""
        url = f"{base_url}/api/monitor/terminals/batch"
        headers = {**auth_headers, "Content-Type": "application/json"}
        addrs_raw = case.get("addrs")
        addrs = self._resolve_batch_addrs(addrs_raw)
        body = {"addrs": addrs}

        sep(f" 测试用例: {case['name']}")
        print_request("DELETE", url, json=body, headers=headers)
        res = http.send_request(
            "delete",
            url,
            json=body,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- 辅助方法 ----------
    def _resolve_batch_addrs(self, yaml_value):
        """解析 {{batch_addrs}}；正向依赖导入接口，缺失则跳过。"""
        if yaml_value is None:
            return None
        if isinstance(yaml_value, str):
            m = re.match(r"^\{\{(\w+)\}\}$", yaml_value.strip())
            if m and m.group(1) == "batch_addrs":
                val = self._get_variable("batch_addrs")
                if val is None:
                    pytest.skip("依赖 batch_addrs：请先跑通「批量导入设备-正向」")
                return val
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
            actual_msg=msg,
            biz_context={"请求用例": case["name"]},
        )

    def _assert_export_response(self, case, res):
        """导出接口：正文以 UTF-8 JSON 对象/数组起头时断言业务 code/msg，否则断言 HTTP + 二进制正文。

        分支只看 body 前缀，不因 Content-Type: application/json 就走 JSON（网关/网关错标时仍可下载文件）。"""
        exp = case["expected"]
        raw = res.content or b""
        trimmed = raw.lstrip()
        looks_like_json = trimmed[:1] in (b"{", b"[")
        if looks_like_json:
            self._assert_and_report(case, res)
            return

        expected_http = exp.get("http_status")
        if expected_http is None:
            expected_http = exp.get("code")
        assert expected_http is not None, (
            f"[{case['name']}] 二进制响应需在 expected 中配置 http_status（或兼容字段 code）"
        )

        sep(" 断言结果(二进制导出) ")
        key("预期 HTTP 状态码", expected_http)
        key("实际 HTTP 状态码", res.status_code)
        key("Content-Type", res.headers.get("Content-Type"))
        body = raw
        key("响应体字节数", len(body))

        assert res.status_code == expected_http, (
            f"[{case['name']}] HTTP 状态码不匹配: 预期={expected_http}, 实际={res.status_code}"
        )
        assert len(body) > 0, f"[{case['name']}] 导出正文为空"
