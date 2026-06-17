import re
import time

import jsonpath
import pytest

from common.allure_assert_util import assert_api_result
from common.logger_util import key, print_request, print_response, sep
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml, write_yaml

_jsonpath_parse = jsonpath.jsonpath
http = BaseRequest()


class TestAlarmController:
    """报警管理接口测试（7 个接口）"""

    test_data = read_yaml("./yaml/test_alarm_controller.yaml")

    # ---------- a0. 前置造数 ----------
    def test_alarm_a0_seed_protocol_alarms(
        self, bd_client, msg_test_terminal, bd_test_terminal, base_url
    ):
        """前置造数：先给 msg+bd 设备写入报警，减少后续查询空数据概率"""
        case_name = "报警前置造数-msg+bd"
        result = bd_client.send_alarm_13_batch(
            from_addrs=[msg_test_terminal, bd_test_terminal],
            phone="13250703582",
            case_name=case_name,
        )
        sep(f" 测试用例: {case_name}")
        print_request("POST", f"{base_url}/api/datas/bd", json=result.request_body)
        print_response_info = {
            "code": result.code,
            "msg": result.msg,
            "success": result.success,
            "status_code": result.status_code,
        }
        key("前置造数结果", str(print_response_info))
        assert result.success, f"前置造数失败：code={result.code}, msg={result.msg}"

    # ---------- a. 分页查询所有设备的报警信息 ----------
    @pytest.mark.parametrize("case", test_data["alarm_list_cases"])
    def test_alarm_a_list(self, base_url, auth_headers, msg_test_terminal, case):
        """分页查询报警列表"""
        url = f"{base_url}/api/monitor/alarms"
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}

        addr = self._resolve_addr(case.get("addr"), msg_test_terminal)
        params = self._build_query_params(headers, addr, case)

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

    # ---------- b. 分页查询设备历史报警信息 ----------
    @pytest.mark.parametrize("case", test_data["alarm_history_cases"])
    def test_alarm_b_history(self, base_url, auth_headers, msg_test_terminal, case):
        """查询设备历史报警"""
        addr = self._resolve_addr(case.get("addr"), msg_test_terminal)
        url = f"{base_url}/api/monitor/alarms/{addr}"
        headers = {**auth_headers}
        params = self._build_pagination(headers, case)

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

    # ---------- c. 获取最新一条报警 ----------
    @pytest.mark.parametrize("case", test_data["alarm_latest_cases"])
    def test_alarm_c_latest(self, base_url, auth_headers, msg_test_terminal, case):
        """获取最新报警"""
        addr = self._resolve_addr(case.get("addr"), msg_test_terminal)
        url = f"{base_url}/api/monitor/alarms/latest/{addr}"
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

    # ---------- d. 处理报警 ----------
    @pytest.mark.parametrize("case", test_data["alarm_handle_cases"])
    def test_alarm_d_handle(
        self, base_url, auth_headers, bd_client, msg_test_terminal, case
    ):
        """处理报警"""
        handle_result = case.get("handle_result", case.get("handleResult", ""))
        headers = {**auth_headers}

        if case.get("scenario") == "positive":
            # 单条处理固定使用 msg 设备报警，避免与批量链路抢数据
            self._seed_alarm_for_addr(
                bd_client=bd_client,
                from_addr=msg_test_terminal,
                case_name=f"{case['name']}-seed",
            )
            # 先从接口动态提取单条报警ID，再写入 extract.yaml 供当前用例读取
            alarm_id = self._extract_single_alarm_id_with_retry(
                base_url=base_url,
                headers=headers,
                addr=msg_test_terminal,
                bd_client=bd_client,
                retry_seed_addr=msg_test_terminal,
            )
            write_yaml("./extract.yaml", {"alarm_single_id": alarm_id}, mode="append")
            alarm_id = self._resolve_value("{{alarm_single_id}}", required=True)
        else:
            alarm_id = case.get("id")

        url = f"{base_url}/api/monitor/alarms/{alarm_id}"
        params = {"handleResult": handle_result}

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

    # ---------- e. 按类型批量处理 ----------
    @pytest.mark.parametrize("case", test_data["alarm_batch_handle_cases"])
    def test_alarm_e_batch_handle(
        self, base_url, auth_headers, bd_client, msg_test_terminal, case
    ):
        """按类型批量处理报警"""
        url = f"{base_url}/api/monitor/alarms/batch-handle"
        headers = {**auth_headers}
        alarm_type = case.get("alarmTypes", "")
        handle_result = case.get("handle_result", case.get("handleResult", "批量已处理"))

        if case.get("scenario") == "positive":
            self._seed_alarm_for_addr(
                bd_client=bd_client,
                from_addr=msg_test_terminal,
                case_name=f"{case['name']}-seed",
            )

        body = {"alarmTypes": alarm_type, "handleResult": handle_result}

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

    # ---------- f. 按 ID 批量处理 ----------
    @pytest.mark.parametrize("case", test_data["alarm_batch_handle_ids_cases"])
    def test_alarm_f_batch_handle_ids(
        self, base_url, auth_headers, bd_client, msg_test_terminal, bd_test_terminal, case
    ):
        """按 ID 批量处理报警"""
        url = f"{base_url}/api/monitor/alarms/batch-handle/ids"
        headers = {**auth_headers}
        handle_result = case.get("handle_result", case.get("handleResult", "批量已处理"))

        if case.get("scenario") == "positive":
            # 批量处理先造两设备报警，确保至少有2个可处理ID
            self._seed_alarm_for_two_terminals(
                bd_client=bd_client,
                msg_addr=msg_test_terminal,
                bd_addr=bd_test_terminal,
                case_name=f"{case['name']}-seed-batch",
            )
            # 优先取两台设备“最新报警ID”，尽量避免混入历史脏数据
            ids = []
            latest_msg_id = self._query_latest_alarm_id(base_url, headers, msg_test_terminal)
            latest_bd_id = self._query_latest_alarm_id(base_url, headers, bd_test_terminal)
            if latest_msg_id is not None:
                ids.append(latest_msg_id)
            if latest_bd_id is not None and latest_bd_id not in ids:
                ids.append(latest_bd_id)
            if len(ids) < 2:
                # 兜底：改走“查询列表+状态过滤+重试补造”提取
                ids = self._extract_batch_alarm_ids_with_retry(
                    base_url=base_url,
                    headers=headers,
                    addr=bd_test_terminal,
                    need_count=2,
                    bd_client=bd_client,
                    msg_addr=msg_test_terminal,
                    bd_addr=bd_test_terminal,
                )
            write_yaml("./extract.yaml", {"alarm_batch_ids": ids}, mode="append")
            ids = self._resolve_value("{{alarm_batch_ids}}", required=True)
            if not isinstance(ids, list):
                pytest.fail(f"alarm_batch_ids 解析结果不是列表: {ids}")
            # Apifox 契约：字段必须是 idStr（逗号拼接），不是 ids
            payload = {
                "idStr": ",".join([str(x) for x in ids[:2]]),
                "handleResult": handle_result,
            }
        else:
            raw_ids = case.get("ids", [])
            payload = {
                "idStr": ",".join([str(x) for x in raw_ids]) if isinstance(raw_ids, list) else str(raw_ids),
                "handleResult": handle_result,
            }

        sep(f" 测试用例: {case['name']}")
        print_request("PUT", url, json=payload, headers=headers)
        res = http.send_request(
            "put",
            url,
            json=payload,
            headers=headers,
            case_name=case["name"],
            log_level="none",
        )
        print_response(res)
        self._assert_and_report(case, res)

    # ---------- g. 获取报警类型及设备数量 ----------
    @pytest.mark.parametrize("case", test_data["alarm_batch_info_cases"])
    def test_alarm_g_batch_info(self, base_url, auth_headers, case):
        """获取报警类型统计"""
        url = f"{base_url}/api/monitor/alarms/batch-info"
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}

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

    # ---------- 辅助 ----------
    @staticmethod
    def _resolve_addr(yaml_value, msg_test_terminal):
        if isinstance(yaml_value, str) and yaml_value.strip() == "{{msg_test_terminal}}":
            return msg_test_terminal
        return yaml_value if yaml_value is not None else ""

    @staticmethod
    def _resolve_value(yaml_value, required=False):
        if yaml_value is None:
            return None
        if isinstance(yaml_value, str):
            match = re.match(r"^\{\{(\w+)\}\}$", yaml_value.strip())
            if match:
                var_name = match.group(1)
                data = read_yaml("./extract.yaml") or {}
                value = data.get(var_name)
                if value is None and required:
                    pytest.fail(f"依赖变量 {var_name} 不存在，无法继续")
                return value
        return yaml_value

    def _build_query_params(self, headers, addr, case):
        auth = headers.get("Authorization") or ""
        params = {"Authorization": auth, "addr": addr}
        alarm_type = case.get("alarm_type", case.get("alarmType"))
        if alarm_type is not None:
            params["alarmType"] = alarm_type
        self._add_pagination(params, case)
        return params

    @staticmethod
    def _build_pagination(headers, case):
        auth = headers.get("Authorization") or ""
        params = {"Authorization": auth}
        if "page" in case:
            params["page"] = case.get("page", 1)
        if "page_size" in case or "pageSize" in case:
            params["pageSize"] = case.get("page_size", case.get("pageSize", 100))
        return params

    @staticmethod
    def _add_pagination(params, case):
        if "page" in case:
            params["page"] = case.get("page", 1)
        if "page_size" in case or "pageSize" in case:
            params["pageSize"] = case.get("page_size", case.get("pageSize", 100))

    @staticmethod
    def _seed_alarm_for_addr(bd_client, from_addr, case_name):
        r = bd_client.send_alarm_13(
            from_addr=from_addr, phone="13250703582", case_name=case_name
        )
        if not r.success:
            pytest.fail(f"协议造数失败 from_addr={from_addr}: code={r.code}, msg={r.msg}")

    @staticmethod
    def _seed_alarm_for_two_terminals(bd_client, msg_addr, bd_addr, case_name):
        r = bd_client.send_alarm_13_batch(
            from_addrs=[msg_addr, bd_addr], phone="13250703582", case_name=case_name
        )
        if not r.success:
            pytest.fail(f"批量协议造数失败: code={r.code}, msg={r.msg}")

    @staticmethod
    def _query_alarm_items(base_url, headers, addr, page=1, page_size=50):
        # 优先查 history 接口，按设备维度更稳定，返回的是 AlarmInfoRespDto 列表
        url = f"{base_url}/api/monitor/alarms/{addr}"
        params = {
            "Authorization": headers.get("Authorization") or "",
            "page": page,
            "pageSize": page_size,
        }
        res = http.send_request(
            "get",
            url,
            params=params,
            headers=headers,
            case_name=f"查询报警列表-{addr}",
            log_level="none",
        )
        data = res.json()
        items = _jsonpath_parse(data, "$.data.items[*]")
        if items:
            return items
        records = _jsonpath_parse(data, "$.data.records[*]")
        if records:
            return records
        data_list = _jsonpath_parse(data, "$.data[*]")
        if data_list:
            return data_list

        # 回退到 /alarms 查询：部分环境下历史接口短时可能查不到最新入库
        fallback_url = f"{base_url}/api/monitor/alarms"
        fallback_params = {
            "Authorization": headers.get("Authorization") or "",
            "addr": addr,
            "page": page,
            "pageSize": page_size,
        }
        r2 = http.send_request(
            "get",
            fallback_url,
            params=fallback_params,
            headers=headers,
            case_name=f"查询报警列表回退-{addr}",
            log_level="none",
        )
        d2 = r2.json()
        items2 = _jsonpath_parse(d2, "$.data.items[*]")
        if items2:
            return items2
        records2 = _jsonpath_parse(d2, "$.data.records[*]")
        return records2 if records2 else []

    @staticmethod
    def _is_unhandled_alarm(item):
        # 兼容不同字段命名/类型，统一判断“未处理”状态
        for key_name in ("handleStatus", "status", "handled"):
            if key_name not in item:
                continue
            val = item.get(key_name)
            if isinstance(val, bool):
                return not val
            if isinstance(val, int):
                return val in (0, 1)
            if isinstance(val, str):
                v = val.strip().lower()
                if any(k in v for k in ("unhandled", "未处理", "new", "pending")):
                    return True
                if any(k in v for k in ("handled", "已处理", "done")):
                    return False
        return True

    def _extract_single_alarm_id_with_retry(
        self, base_url, headers, addr, bd_client, retry_seed_addr
    ):
        # 先查询 + 短轮询，再补造一次并重查，尽量降低异步入库导致的空ID概率
        for _ in range(3):
            items = self._query_alarm_items(base_url, headers, addr)
            ids = [i.get("id") for i in items if isinstance(i, dict) and i.get("id") is not None]
            unhandled_ids = [
                i.get("id")
                for i in items
                if isinstance(i, dict)
                and i.get("id") is not None
                and self._is_unhandled_alarm(i)
            ]
            if unhandled_ids:
                return unhandled_ids[0]
            if ids:
                return ids[0]
            latest_id = self._query_latest_alarm_id(base_url, headers, addr)
            if latest_id is not None:
                return latest_id
            global_ids = self._query_global_alarm_ids(base_url, headers)
            if global_ids:
                return global_ids[0]
            time.sleep(0.8)

        self._seed_alarm_for_addr(
            bd_client=bd_client,
            from_addr=retry_seed_addr,
            case_name="单条处理-兜底补造",
        )
        items = self._query_alarm_items(base_url, headers, addr)
        ids = [i.get("id") for i in items if isinstance(i, dict) and i.get("id") is not None]
        if not ids:
            latest_id = self._query_latest_alarm_id(base_url, headers, addr)
            if latest_id is not None:
                return latest_id
            global_ids = self._query_global_alarm_ids(base_url, headers)
            if global_ids:
                return global_ids[0]
        if not ids:
            pytest.fail("alarms/{id} 无法提取报警ID（补造后仍为空）")
        return ids[0]

    @staticmethod
    def _query_latest_alarm_id(base_url, headers, addr):
        url = f"{base_url}/api/monitor/alarms/latest/{addr}"
        res = http.send_request(
            "get",
            url,
            headers=headers,
            case_name=f"查询最新报警-{addr}",
            log_level="none",
        )
        data = res.json()
        direct = _jsonpath_parse(data, "$.data.id")
        if direct:
            return direct[0]
        deep = _jsonpath_parse(data, "$..id")
        if not deep:
            return None
        for v in deep:
            if isinstance(v, (int, str)) and str(v).strip():
                return v
        return None

    @staticmethod
    def _query_global_alarm_ids(base_url, headers):
        url = f"{base_url}/api/monitor/alarms"
        params = {
            "Authorization": headers.get("Authorization") or "",
            "page": 1,
            "pageSize": 50,
        }
        r = http.send_request(
            "get",
            url,
            params=params,
            headers=headers,
            case_name="查询全局报警列表兜底",
            log_level="none",
        )
        data = r.json()
        ids = _jsonpath_parse(data, "$.data.items[*].id")
        if ids:
            return ids
        ids = _jsonpath_parse(data, "$.data.records[*].id")
        if ids:
            return ids
        return []

    def _extract_batch_alarm_ids_with_retry(
        self, base_url, headers, addr, need_count, bd_client, msg_addr, bd_addr
    ):
        def collect_unhandled_ids():
            # 批量场景从 msg/bd 两设备合并收集，去重后取未处理ID
            msg_items = self._query_alarm_items(base_url, headers, msg_addr)
            bd_items = self._query_alarm_items(base_url, headers, bd_addr)
            merged = []
            seen = set()
            for i in [*msg_items, *bd_items]:
                if not isinstance(i, dict):
                    continue
                _id = i.get("id")
                if _id is None or _id in seen:
                    continue
                seen.add(_id)
                if self._is_unhandled_alarm(i):
                    merged.append(_id)
            return merged

        for _ in range(3):
            unhandled_ids = collect_unhandled_ids()
            if len(unhandled_ids) >= need_count:
                return unhandled_ids[:need_count]
            time.sleep(0.8)

        self._seed_alarm_for_two_terminals(
            bd_client=bd_client,
            msg_addr=msg_addr,
            bd_addr=bd_addr,
            case_name="批量处理-兜底补造",
        )
        ids = collect_unhandled_ids()
        if len(ids) < need_count:
            pytest.fail(f"batch-handle/ids 提取ID不足: 需要{need_count}条，实际{len(ids)}条")
        return ids[:need_count]

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
