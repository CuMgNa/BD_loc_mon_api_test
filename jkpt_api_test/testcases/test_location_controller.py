# testcases/test_location_controller.py
# 位置管理接口 — 方法名 test_location_a_* / b_* / c_* 保证 pytest 收集顺序 list → track → export
# 计划见 plan/location-controller-tests.plan.md：addr 仅用 bd_test_terminal；时间窗为 Asia/Shanghai 当天
import jsonpath
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from common.requests_util import BaseRequest
from common.yaml_util import read_yaml
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class TestLocationController:
    """位置管理接口测试（GET /locations、GET /locations/track、POST /locations/export）"""

    test_data = read_yaml("./yaml/test_location_controller.yaml")

    # ---------- a. 分页查询位置列表 ----------
    @pytest.mark.parametrize("case", test_data["location_list_cases"])
    def test_location_a_list(self, base_url, auth_headers, bd_test_terminal, case):
        """分页查询位置列表"""
        url = f"{base_url}/api/monitor/locations"
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}

        addr = self._resolve_bd_addr(case.get("addr"), bd_test_terminal)
        params = self._build_location_query_params(headers, addr, case)

        sep(f" 测试用例: {case['name']}")
        print_request("GET", url, params=params, headers=headers)
        res = http.send_request(
            "get",
            url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- b. 获取指定时间段内的轨迹 ----------
    @pytest.mark.parametrize("case", test_data["location_track_cases"])
    def test_location_b_track(self, base_url, auth_headers, bd_test_terminal, case):
        """轨迹查询"""
        url = f"{base_url}/api/monitor/locations/track"
        headers = {**auth_headers}

        addr = self._resolve_bd_addr(case.get("addr"), bd_test_terminal)
        params = self._build_location_query_params(headers, addr, case)

        sep(f" 测试用例: {case['name']}")
        print_request("GET", url, params=params, headers=headers)
        res = http.send_request(
            "get",
            url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- c. 导出轨迹（POST + query + Time-Zone） ----------
    @pytest.mark.parametrize("case", test_data["location_export_cases"])
    def test_location_c_export(self, base_url, auth_headers, bd_test_terminal, case):
        """导出轨迹；正文为 JSON 时断言业务 code/msg，否则断言 HTTP + 非空二进制"""
        url = f"{base_url}/api/monitor/locations/export"
        headers = {
            **auth_headers,
            "Time-Zone": "Asia/Shanghai",
        }

        addr = self._resolve_bd_addr(case.get("addr"), bd_test_terminal)
        params = self._build_location_query_params(headers, addr, case)

        sep(f" 测试用例: {case['name']}")
        key("请求方法", "POST")
        key("请求地址", url)
        key("查询参数", {k: ("******" if k.lower() == "authorization" else v) for k, v in params.items()})
        key("请求头", {k: ("******" if k.lower() == "authorization" else v) for k, v in headers.items()})
        res = http.send_request(
            "post",
            url,
            params=params,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)

        if case.get("binary_response"):
            self._assert_export_response(case, res)
        else:
            self._assert_and_report(case, res)

    # ---------- 辅助 ----------
    @staticmethod
    def _today_range_shanghai():
        d = datetime.now(_SHANGHAI).date().strftime("%Y-%m-%d")
        return f"{d} 00:00:00", f"{d} 23:59:59"

    def _time_window(self, case):
        st = case.get("startTimeStr")
        et = case.get("endTimeStr")
        if st and et:
            return st, et
        return self._today_range_shanghai()

    def _resolve_bd_addr(self, yaml_value, bd_test_terminal):
        if isinstance(yaml_value, str) and yaml_value.strip() == "{{bd_test_terminal}}":
            return bd_test_terminal
        return yaml_value if yaml_value is not None else ""

    def _build_location_query_params(self, headers, addr, case):
        """OpenAPI 将 Authorization 标为 query；与 Header 一并传入以兼容网关。"""
        auth = headers.get("Authorization") or ""
        start_str, end_str = self._time_window(case)
        params = {
            "Authorization": auth,
            "addr": addr,
            "startTimeStr": start_str,
            "endTimeStr": end_str,
        }
        if "page" in case:
            params["page"] = case.get("page", 1)
        if "pageSize" in case:
            params["pageSize"] = case.get("pageSize", 100)
        return params

    def _assert_and_report(self, case, res):
        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else ""

        sep(" 断言结果 ")
        key("预期 code", case["expected"]["code"])
        key("实际 code", code)
        key("预期 msg", case["expected"].get("error_msg", ""))
        key("实际 msg", msg)

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"].get("error_msg", ""),
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求用例": case["name"]},
        )

    def _assert_export_response(self, case, res):
        """导出：正文以 UTF-8 JSON 起头则断言业务 code/msg，否则断言 HTTP + 非空正文。"""
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
        key("响应体字节数", len(raw))

        assert res.status_code == expected_http, (
            f"[{case['name']}] HTTP 状态码不匹配: 预期={expected_http}, 实际={res.status_code}"
        )
        assert len(raw) > 0, f"[{case['name']}] 导出正文为空"
