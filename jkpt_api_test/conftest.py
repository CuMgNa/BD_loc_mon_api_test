# conftest.py
import pytest
import time
import random
import logging
import json
import traceback
from common.requests_util import BaseRequest, get_last_http_context
from common.yaml_util import clear_yaml
from common.captcha_util import CaptchaRecognizer
from common.logger_util import sep, key, print_request, print_response
import jsonpath

# 修复 jsonpath API 兼容性
_jsonpath_parse = jsonpath.jsonpath

# Allure 附件
try:
    import allure
except Exception:
    allure = None

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== 全局实例 ====================
http = BaseRequest()
ocr = CaptchaRecognizer()

# ==================== 配置 ====================
def pytest_configure(config):
    config.base_url = "http://back.tdwtv2.pg8.ink"
    config.accept_language = "zh-CN"
    sep(" 配置信息 ")
    key("🌐 base_url", config.base_url)
    key("🌐 Accept-Language", config.accept_language)

@pytest.fixture(scope="session")
def base_url(pytestconfig):
    return pytestconfig.base_url

@pytest.fixture(scope="session")
def accept_language(pytestconfig):
    return pytestconfig.accept_language

# ==================== 认证核心：auth_token fixture ====================
def generate_captcha_id():
    """生成18位无0开头的captchaId"""
    timestamp = str(int(time.time() * 1000))
    random_5 = str(random.randint(10000, 99999))
    return timestamp + random_5

@pytest.fixture(scope="session")
def auth_token(base_url):
    """通过验证码识别获取token，带循环重试机制"""
    sep(" 🔐 认证流程 - 获取Token ")
    print()

    max_attempts = 5

    for attempt in range(1, max_attempts + 1):
        print(f"  ▶️  第 {attempt}/{max_attempts} 次尝试")

        # 步骤1：获取验证码
        captcha_id = generate_captcha_id()
        key("🔑 captchaId", captcha_id)
        captcha_url = f"{base_url}/api/monitor/captcha?captchaId={captcha_id}"

        resp = http.send_request(
            method="get",
            url=captcha_url,
            case_name="获取验证码",
            log_level="none"
        )
        key("🖼️ 验证码图片", "获取成功")

        # 步骤2：识别验证码
        captcha_text = ocr.recognize_from_response(resp)
        key("🔤 识别结果", captcha_text)

        # 步骤3：执行登录
        login_url = f"{base_url}/api/monitor/web-user/login"
        login_data = {
            "account": "tmn",
            "password": "4f9cb165cd6249312e5804fcf9416c5e",
            "captcha": captcha_text,
            "captchaId": captcha_id
        }

        print_request("POST", login_url, params=login_data)

        login_resp = http.send_request(
            method="post",
            url=login_url,
            params=login_data,
            case_name="用户登录",
            log_level="none"
        )

        print_response(login_resp)

        json_data = login_resp.json()
        code = _jsonpath_parse(json_data, "$.code")[0]

        if code == 0:
            token = _jsonpath_parse(json_data, "$.data.token")[0]
            key("🎫 Token", f"{token[:30]}...")
            key("✅ 结果", "登录成功!")
            return token
        else:
            msg = _jsonpath_parse(json_data, "$.msg")[0]
            key("❌ 失败原因", f"code={code}, msg={msg}")
            if attempt < max_attempts:
                print("  ⏳ 1秒后重试...")
                time.sleep(1)

    pytest.fail("登录失败，已重试5次仍未成功")

# ==================== 认证头：auth_headers fixture ====================
@pytest.fixture(scope="session")
def auth_headers(auth_token, accept_language):
    """构造认证请求头"""
    sep(" 🔑 认证头信息 ")
    key("Authorization", f"Bearer {auth_token[:20]}...")
    key("Accept-Language", accept_language)
    return {
        "Authorization": f"{auth_token}",
        "Accept-Language": accept_language
    }

# ==================== 失败上下文钩子 ====================
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """在测试失败时自动附加请求/响应上下文到Allure"""
    outcome = yield
    report = outcome.get_result()

    # 只在测试失败时执行
    if report.when == "call" and report.failed:
        context = get_last_http_context()

        if context and allure:
            # 附加请求上下文
            if "request" in context:
                request_info = context["request"]
                allure.attach(
                    json.dumps(request_info, indent=2, ensure_ascii=False),
                    name="【失败】请求信息",
                    attachment_type=allure.attachment_type.JSON
                )

            # 附加响应上下文
            if "response" in context:
                response_info = context["response"]
                allure.attach(
                    json.dumps(response_info, indent=2, ensure_ascii=False),
                    name="【失败】响应信息",
                    attachment_type=allure.attachment_type.JSON
                )

            # 附加错误上下文
            if "error" in context:
                error_info = context["error"]
                allure.attach(
                    json.dumps(error_info, indent=2, ensure_ascii=False),
                    name="【失败】错误信息",
                    attachment_type=allure.attachment_type.JSON
                )

            # 附加断言失败详情
            if hasattr(report.longrepr, 'reprcrash'):
                failure_msg = str(report.longrepr.reprcrash.message) if hasattr(report.longrepr, 'reprcrash') else str(report.longrepr)
                allure.attach(
                    failure_msg,
                    name="【失败】断言详情",
                    attachment_type=allure.attachment_type.TEXT
                )

# ==================== 全局分组 Fixture ====================
@pytest.fixture(scope="session")
def group_fixture(base_url, auth_headers):
    """自动创建分组数据，并写入 extract.yaml 供其他测试复用"""
    sep(" 📦 创建全局分组数据 ")

    from common.yaml_util import write_yaml

    groups_url = f"{base_url}/api/monitor/groups"
    group_ids = {"one_id": None, "two_id": None, "three_id": None}
    suffix = str(int(time.time() * 1000))[-8:]

    # 1. 创建一级分组
    resp = http.send_request(
        method="post",
        url=groups_url,
        params={"groupName": f"L1_{suffix}", "parentId": 0},
        headers=auth_headers,
        case_name="创建一级分组",
        log_level="none"
    )
    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        group_ids["one_id"] = _jsonpath_parse(json_data, "$.data.id")[0]
        key("一级分组ID", group_ids["one_id"])
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        pytest.fail(f"group_fixture创建一级分组失败: code={code}, msg={msg}")

    # 2. 创建二级分组
    resp = http.send_request(
        method="post",
        url=groups_url,
        params={"groupName": f"L2_{suffix}", "parentId": group_ids["one_id"]},
        headers=auth_headers,
        case_name="创建二级分组",
        log_level="none"
    )
    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        group_ids["two_id"] = _jsonpath_parse(json_data, "$.data.id")[0]
        key("二级分组ID", group_ids["two_id"])
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        pytest.fail(f"group_fixture创建二级分组失败: code={code}, msg={msg}")

    # 3. 创建三级分组
    resp = http.send_request(
        method="post",
        url=groups_url,
        params={"groupName": f"L3_{suffix}", "parentId": group_ids["two_id"]},
        headers=auth_headers,
        case_name="创建三级分组",
        log_level="none"
    )
    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        group_ids["three_id"] = _jsonpath_parse(json_data, "$.data.id")[0]
        key("三级分组ID", group_ids["three_id"])
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        pytest.fail(f"group_fixture创建三级分组失败: code={code}, msg={msg}")

    # 将分组ID写入 extract.yaml
    write_yaml("./extract.yaml", group_ids, mode="append")

    return group_ids

# ==================== 设备类型 Fixture ====================
@pytest.fixture(scope="session")
def terminal_types(base_url, auth_headers):
    """获取所有设备类型枚举，session级别只调用一次"""
    sep(" 📋 获取设备类型枚举 ")
    url = f"{base_url}/api/monitor/enums/terminal-types"

    resp = http.send_request(
        method="get",
        url=url,
        headers=auth_headers,
        case_name="获取设备类型枚举",
        log_level="none"
    )

    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]

    if code == 0:
        # 返回字典列表: [{"name": "PN07", "value": "PN07设备"}, ...]
        types = _jsonpath_parse(json_data, "$.data[*]")
        if types:
            key("设备类型列表", types)
            return types
        else:
            key("设备类型列表", "未获取到类型")
            return []
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0]
        key("获取设备类型失败", f"code={code}, msg={msg}")
        return []

# ==================== 自动清理 ====================
@pytest.fixture(scope="session", autouse=True)
def clear_data_per_session():
    sep(" 🚀 测试开始 ")
    clear_yaml()
    yield
    sep(" 🏁 测试结束 ")