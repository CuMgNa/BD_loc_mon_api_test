# testcases/test_login.py
import jsonpath  # pyright: ignore[reportMissingImports]
import pytest  # pyright: ignore[reportMissingImports]
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml
from common.captcha_util import CaptchaRecognizer, generate_captcha_id
from common.logger_util import sep, key, print_request, print_response
from common.allure_assert_util import assert_api_result

# 修复 jsonpath API 兼容性
_jsonpath_parse = jsonpath.jsonpath

# 全局实例
http = BaseRequest()
ocr = CaptchaRecognizer()


class TestLoginAPI:
    """
    登录接口测试（负向场景）
    """

    test_data = read_yaml("./yaml/test_login.yaml")["login_cases"]

    @pytest.mark.parametrize("case", test_data)
    def test_login_negative(self, base_url, auth_headers, case):
        """登录接口负向测试"""

        # 构建请求参数
        url = f"{base_url}/api/monitor/web-user/login"
        headers = {**auth_headers}

        # 根据测试场景决定验证码来源
        if case["name"] == "验证码错误":
            # 验证码错误场景：使用固定错误验证码
            captcha_id = case["captchaId"]
            captcha_text = case["captcha"]
        else:
            # 其他场景：动态获取有效验证码
            captcha_id = generate_captcha_id()
            captcha_url = f"{base_url}/api/monitor/captcha?captchaId={captcha_id}"

            resp = http.send_request(
                method="get",
                url=captcha_url,
                case_name="获取验证码",
                log_level="none"
            )
            captcha_text = ocr.recognize_from_response(resp)

        # 构建请求参数
        payload = {
            "account": case["account"],
            "password": case["password"],
            "captcha": captcha_text,
            "captchaId": captcha_id
        }

        # 打印测试用例信息
        sep(f" 测试用例: {case['name']}")
        key("captchaId", captcha_id)
        key("验证码", captcha_text)
        print_request("POST", url, params=payload, headers=headers)

        # 发送请求
        res = BaseRequest().send_request(
            method="post",
            url=url,
            params=payload,
            headers=headers,
            case_name=case["name"],
            log_level="none"
        )

        # 打印响应
        print_response(res)

        json_data = res.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        msg = _jsonpath_parse(json_data, "$.msg")[0]

        # 打印断言结果
        sep(" 断言结果 ")
        key("预期 code", case["expected"]["code"])
        key("实际 code", code)
        key("预期 msg", case["expected"]["error_msg"])
        key("实际 msg", msg)

        expected_code = case["expected"]["code"]
        expected_msg = case["expected"]["error_msg"]
        assert_api_result(
            case_name=case["name"],
            expected_code=expected_code,
            expected_msg=expected_msg,
            actual_code=code,
            actual_msg=msg,
            biz_context={
                "请求参数": {
                    "account": case["account"],
                    "captchaId": captcha_id,
                    "captcha": captcha_text if case["name"] == "验证码错误" else "[动态获取]"
                }
            }
        )