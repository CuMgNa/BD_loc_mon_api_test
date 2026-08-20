# common/case_report_util.py
"""用例层通用「信封断言 + 扩展结果」工具。

抽取动机：对讲群（`_IgHelpers`）与对讲群消息（`_ImHelpers`）两套 suite 逐字重复同一套
headers/send/assert/report 逻辑（规则：≥2 个 testcase 重复 ≥5 行 → 抽到 common/）。
口径原样保留：扩展断言成功只打一行结论，失败才打全表 + Allure 附件。
"""
import json as _json

import jsonpath

from common.allure_assert_util import assert_api_result
from common.logger_util import key, print_request, print_response, print_result, sep
from common.yaml_util import read_expected_msg

try:
    import allure
except Exception:
    allure = None

_jsonpath_parse = jsonpath.jsonpath


def jp_first(data, expr):
    """jsonpath 取首个匹配；无匹配返回 None（jsonpath 失败返回 False 的坑已封）。"""
    found = _jsonpath_parse(data, expr)
    if found:
        return found[0]
    return None


def jp_list(data, expr):
    """jsonpath 取列表；无匹配返回 []。"""
    found = _jsonpath_parse(data, expr)
    return found if found else []


def case_headers(auth_headers, case):
    """`no_auth: true` 用例剥 Authorization，保留 Accept-Language。"""
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    return headers


def send_case(http, method, url, case, headers, *, params=None, json=None):
    """打印请求/响应并返回响应 json（每请求只 .json() 一次）。"""
    sep(f" 测试用例: {case['name']}")
    print_request(method.upper(), url, params=params, json=json, headers=headers)
    res = http.send_request(
        method, url, params=params, json=json, headers=headers,
        case_name=case["name"], log_level="none",
    )
    print_response(res)
    return res.json()


def assert_case(case, json_data, biz_context):
    """信封断言：正向读 expected.msg，负向读 expected.error_msg。返回 (code, msg)。"""
    code = jp_first(json_data, "$.code")
    msg = jp_first(json_data, "$.msg") or ""
    sep(" 断言结果 ")
    key("预期 code", case["expected"]["code"])
    key("实际 code", code)
    key("预期 msg", read_expected_msg(case["expected"]))
    key("实际 msg", msg)
    assert_api_result(
        case_name=case["name"],
        expected_code=case["expected"]["code"],
        expected_msg=read_expected_msg(case["expected"]),
        actual_code=code,
        actual_msg=msg,
        biz_context=biz_context,
    )
    return code, msg


def report_extra(title, rows, *, ok, summary=None):
    """扩展结果：成功一行结论 + Allure 压缩 JSON；失败框+全表 + Allure rows。"""
    line = summary or (f"{title}通过" if ok else f"{title}失败")
    if ok:
        print(f"  ✅ {line}")
        if allure:
            allure.attach(
                _json.dumps({"title": title, "ok": True, "summary": line},
                            indent=2, ensure_ascii=False, default=str),
                name=f"【扩展】{title}",
                attachment_type=allure.attachment_type.JSON,
            )
        return
    sep(title)
    print(f"  {'项':<32} {'期望':<28} {'实际'}")
    for row in rows:
        print(
            f"  {str(row.get('项', '')):<32} "
            f"{str(row.get('期望', '')):<28} "
            f"{str(row.get('实际', ''))}"
        )
    print_result(False, f"{title}失败")
    if allure:
        allure.attach(
            _json.dumps({"title": title, "ok": False, "rows": rows},
                        indent=2, ensure_ascii=False, default=str),
            name=f"【扩展】{title}",
            attachment_type=allure.attachment_type.JSON,
        )


def report_extra_and_assert(title, rows, summary):
    """扩展结果 + 失败即抛：行内 `通过` 为 False 即整体失败。"""
    ok = all(r.get("通过", True) for r in rows)
    report_extra(title, rows, ok=ok, summary=summary if ok else None)
    if not ok:
        bad = [r for r in rows if r.get("通过") is False]
        raise AssertionError(f"{title}失败: {bad}")
