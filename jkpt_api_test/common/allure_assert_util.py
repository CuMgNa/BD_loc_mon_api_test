import json

from common.logger_util import print_result

try:
    import allure  # pyright: ignore[reportMissingImports]
except Exception:
    allure = None


def _attach_text(content, name):
    """安全附加文本到 Allure。"""
    if allure:
        allure.attach(content, name=name, attachment_type=allure.attachment_type.TEXT)


def _attach_json(data, name):
    """安全附加 JSON 到 Allure。"""
    if allure:
        allure.attach(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            name=name,
            attachment_type=allure.attachment_type.JSON
        )


def assert_api_result(case_name, expected_code, expected_msg, actual_code, actual_msg, biz_context=None):
    """
    统一接口断言与 Allure 附件输出。

    - 成功：附加简要成功信息
    - 失败：附加失败上下文并抛出清晰断言错误
    """
    if actual_code == expected_code and actual_msg == expected_msg:
        print_result(True, "验证通过!")
        _attach_text(
            f"验证通过: code={actual_code}, msg={actual_msg}",
            name="【成功】验证结果"
        )
        assert actual_code == expected_code, f"code不匹配: 预期{expected_code}, 实际{actual_code}"
        assert actual_msg == expected_msg, f"msg不匹配: 预期{expected_msg}, 实际{actual_msg}"
        return

    failure_context = {
        "测试用例": case_name,
        "预期结果": {
            "code": expected_code,
            "msg": expected_msg
        },
        "实际结果": {
            "code": actual_code,
            "msg": actual_msg
        },
        "业务上下文": biz_context or {}
    }
    print_result(False, "验证失败!")
    _attach_json(failure_context, name="【失败】验证失败上下文")

    assert actual_code == expected_code, (
        f"[{case_name}] code不匹配: 预期={expected_code}, 实际={actual_code}, msg={actual_msg}"
    )
    assert actual_msg == expected_msg, (
        f"[{case_name}] msg不匹配: 预期={expected_msg}, 实际={actual_msg}"
    )
