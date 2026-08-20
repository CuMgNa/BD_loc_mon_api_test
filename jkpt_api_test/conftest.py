# conftest.py
import pytest
import time
import datetime
import logging
import json
import os
from common.requests_util import BaseRequest, get_last_http_context, NonJsonResponseError, parse_response_json
from common.run_artifact_util import wipe_allure_raw_dirs
from common.yaml_util import clear_yaml
from common.captcha_util import CaptchaRecognizer, generate_captcha_id
from common.logger_util import sep, key, print_request, print_response
from common.bd_protocol_client import BDProtocolClient
from common.protocol_transport import BDProtocolTransport
from common.rescue_platform_client import (
    RescuePlatformSession,
    RescueUplinkClient,
    generate_rescue_sn,
)
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

# ==================== 配置清理行为 ====================
ENABLE_AUTO_CLEANUP = os.getenv("ENABLE_AUTO_CLEANUP", "true").lower() == "true"

JKPT_ACCOUNT = os.getenv("JKPT_ACCOUNT", "user1752216001906")
JKPT_PASSWORD = os.getenv("JKPT_PASSWORD", "4f9cb165cd6249312e5804fcf9416c5e")
JKPT_ACCOUNT_B = os.getenv("JKPT_ACCOUNT_B", "user13128251672")
JKPT_PASSWORD_B = os.getenv("JKPT_PASSWORD_B", JKPT_PASSWORD)  # 同 A 的 MD5
# GLHT_* 常量与 ENABLE_GLHT_CLEANUP 已挪进 common/cleanup/glht.py（域模块自读环境变量）

# ==================== 配置 ====================
def pytest_configure(config):
    config.base_url = os.getenv("JKPT_BASE_URL", "http://back.tdwtv2.pg8.ink")
    config.accept_language = "zh-CN"
    wiped = wipe_allure_raw_dirs(config.rootpath)
    sep(" 配置信息 ")
    key("🌐 base_url", config.base_url)
    key("🌐 Accept-Language", config.accept_language)
    if wiped:
        key("🧹 已清空 Allure raw", ", ".join(wiped))

@pytest.fixture(scope="session")
def base_url(pytestconfig):
    return pytestconfig.base_url

@pytest.fixture(scope="session")
def accept_language(pytestconfig):
    return pytestconfig.accept_language

def _login_token(base_url, account, password, label):
    """验证码 OCR + 登录，最多 5 次。失败 pytest.fail。"""
    sep(f" 🔐 认证流程 - {label} 获取Token ")
    print()
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        print(f"  ▶️  第 {attempt}/{max_attempts} 次尝试")
        captcha_id = generate_captcha_id()
        key("🔑 captchaId", captcha_id)
        captcha_url = f"{base_url}/api/monitor/captcha?captchaId={captcha_id}"
        resp = http.send_request(
            method="get", url=captcha_url, case_name=f"{label}获取验证码", log_level="none",
        )
        key("🖼️ 验证码图片", "获取成功")
        captcha_text = ocr.recognize_from_response(resp)
        key("🔤 识别结果", captcha_text)
        login_url = f"{base_url}/api/monitor/web-user/login"
        login_data = {
            "account": account, "password": password,
            "captcha": captcha_text, "captchaId": captcha_id,
        }
        print_request("POST", login_url, params=login_data)
        login_resp = http.send_request(
            method="post", url=login_url, params=login_data,
            case_name=f"{label}用户登录", log_level="none",
        )
        print_response(login_resp)
        json_data = login_resp.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            token = _jsonpath_parse(json_data, "$.data.token")[0]
            key("🎫 Token", f"{token[:30]}...")
            key("✅ 结果", f"{label}登录成功!")
            return token
        msg = _jsonpath_parse(json_data, "$.msg")[0]
        key("❌ 失败原因", f"code={code}, msg={msg}")
        if attempt < max_attempts:
            print("  ⏳ 1秒后重试...")
            time.sleep(1)
    pytest.fail(f"{label}登录失败，已重试5次仍未成功")


# ==================== 认证核心：auth_token fixture ====================
@pytest.fixture(scope="session")
def auth_token(base_url):
    """A 账号 token（验证码 OCR + 重试）"""
    return _login_token(base_url, JKPT_ACCOUNT, JKPT_PASSWORD, "A")

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


@pytest.fixture(scope="session")
def auth_token_b(base_url):
    """B 账号 token。仅批 2 注入时拉活，不影响批 1。"""
    return _login_token(base_url, JKPT_ACCOUNT_B, JKPT_PASSWORD_B, "B")


@pytest.fixture(scope="session")
def auth_headers_b(auth_token_b, accept_language):
    """B 认证头。仅 TestIg04 B 支路 / Ig11 / Ig12 注入。"""
    sep(" 🔑 B 认证头信息 ")
    key("Authorization", f"Bearer {auth_token_b[:20]}...")
    key("Accept-Language", accept_language)
    return {
        "Authorization": f"{auth_token_b}",
        "Accept-Language": accept_language,
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
def group_fixture(base_url, auth_headers, pytestconfig):
    """自动创建分组数据，供其他测试复用"""
    sep(" 📦 创建全局分组数据 ")

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
    try:
        json_data = parse_response_json(resp, context="group_fixture创建一级分组")
    except NonJsonResponseError as e:
        pytest.fail(str(e))
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
    try:
        json_data = parse_response_json(resp, context="group_fixture创建二级分组")
    except NonJsonResponseError as e:
        pytest.fail(str(e))
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
    try:
        json_data = parse_response_json(resp, context="group_fixture创建三级分组")
    except NonJsonResponseError as e:
        pytest.fail(str(e))
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        group_ids["three_id"] = _jsonpath_parse(json_data, "$.data.id")[0]
        key("三级分组ID", group_ids["three_id"])
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        pytest.fail(f"group_fixture创建三级分组失败: code={code}, msg={msg}")

    # 存储到 stash，供 session 结束时清理使用
    pytestconfig.stash["test_group_ids"] = group_ids.copy()

    # 副作用落地即注册（纪律 1）：三级分组建好即挂 cleaner
    # （tier 200 设备 → 300 分组，同 payload；顺序由 registry 保证）
    from common.cleanup import register_cleanup, group as _g, terminal as _t
    register_cleanup("groups", group_ids, _g.cleaner, tier=300)
    register_cleanup("terminals", group_ids, _t.cleaner, tier=200)

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


@pytest.fixture(scope="session")
def terminal_use_scopes(base_url, auth_headers):
    """获取所有使用范围枚举，session级别只调用一次"""
    sep(" 📋 获取使用范围枚举 ")
    url = f"{base_url}/api/monitor/enums/terminal-use-scopes"
    resp = http.send_request(
        method="get",
        url=url,
        headers=auth_headers,
        case_name="获取使用范围枚举",
        log_level="none",
    )
    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        scopes = _jsonpath_parse(json_data, "$.data[*]")
        if scopes:
            key("使用范围列表", scopes)
            return scopes
        key("使用范围列表", "未获取到")
        return []
    msg = _jsonpath_parse(json_data, "$.msg")[0]
    key("获取使用范围失败", f"code={code}, msg={msg}")
    return []


@pytest.fixture(scope="session")
def terminal_type_enum_cases(terminal_types, terminal_use_scopes):
    """生成 N 条枚举用例（useScope 循环选取，SN 防碰撞）"""
    if not terminal_types or not terminal_use_scopes:
        pytest.skip("terminal_types 或 terminal_use_scopes 为空，跳过枚举用例")
    base_sn = datetime.datetime.now().strftime("%Y%m%d")
    salt = str(int(time.time()) % 10000).zfill(4)
    cases = []
    for i, t in enumerate(terminal_types, start=1):
        scope = terminal_use_scopes[i % len(terminal_use_scopes)]
        sn = f"{base_sn}{salt}{i:03d}"
        cases.append({
            "sn": sn,
            "terminalType": t["name"],
            "remark": t["value"],
            "useScope": scope["name"],
        })
    key("枚举用例数量", len(cases))
    return cases


# ==================== 测试设备 Fixture ====================
TEST_TERMINALS = [
    {"sn": "20260430200104", "remark": "bd协议测试", "icon": "🛰️", "name": "BD协议测试设备"},
    {"sn": "20260430200105", "remark": "消息测试",    "icon": "📬", "name": "消息测试设备"},
]


def _create_terminal(base_url, auth_headers, group_id, addr, remark, icon, name):
    """在指定分组下创建设备，若已存在则复用。"""
    sep(f" {icon} 创建{name} ")
    url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
    body = {
        "sn": addr,
        "remark": remark,
        "groupId": group_id,
        "terminalType": "PD18",
        "useScope": "STEAMER",
        "fromAddr": "",
        "trackColor": "#141323",
        "trackSize": 5,
        "groupCallNumber": "",
        "ipAddress": "",
        "gatewayParam": {
            "colorCodeId": 1,
            "gid": 0,
            "radioRcvChn": "",
            "radioSndChn": "",
            "radioPower": 0,
            "rxCss": "",
            "txCss": "",
            "width": 0,
        },
        "fieldJson": "",
    }
    resp = http.send_request(
        method="post", url=url, json=body, headers=auth_headers,
        case_name=f"创建{name}", log_level="none",
    )
    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code == 0:
        key(name, f"创建成功 addr={addr}")
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        key(f"⚠️ {name}创建失败(将复用)", f"code={code}, msg={msg}")
    return addr


@pytest.fixture(scope="session")
def bd_test_terminal(base_url, auth_headers, group_fixture):
    group_id = group_fixture["one_id"]
    t = TEST_TERMINALS[0]
    return _create_terminal(base_url, auth_headers, group_id, t["sn"], t["remark"], t["icon"], t["name"])


@pytest.fixture(scope="session")
def msg_test_terminal(base_url, auth_headers, group_fixture):
    group_id = group_fixture["one_id"]
    t = TEST_TERMINALS[1]
    return _create_terminal(base_url, auth_headers, group_id, t["sn"], t["remark"], t["icon"], t["name"])


@pytest.fixture(scope="session")
def bd_client(base_url, auth_headers):
    """北斗协议客户端（11 种 content 一站式发送）"""
    transport = BDProtocolTransport(base_url=base_url, headers=auth_headers, http=http)
    return BDProtocolClient(transport=transport)


# ==================== 卫星救援终端（10304）造数 fixtures ====================
RESCUE_PLATFORM_USER = os.getenv("RESCUE_PLATFORM_USER", "admin")
RESCUE_PLATFORM_PASSWORD = os.getenv("RESCUE_PLATFORM_PASSWORD", "admin@0415")


@pytest.fixture(scope="session")
def rescue_client():
    """10304 上行模拟造数客户端（U0~U5 报文一站式发送）。

    session 级单例；结束时自动断开所有活跃模拟会话。
    语音样本注入：用例侧如需 send_speech，先调 set_speech_sample()。
    """
    sep(" 🛰️ 初始化救援平台客户端 ")
    mgr = RescuePlatformSession(RESCUE_PLATFORM_USER, RESCUE_PLATFORM_PASSWORD)
    client = RescueUplinkClient(mgr, http=http)
    key("救援平台", "120.77.17.225:10304")
    yield client
    # session 末：断开所有活跃模拟会话
    n = client.disconnect_all()
    if n:
        key("救援平台会话清理", f"断开 {n} 个会话")


@pytest.fixture(scope="session")
def rescue_sat_terminal(base_url, auth_headers, group_fixture):
    """入库+添加一台卫星救援终端（TT_RESCUE_STICK），返回 sn（12位纯数字）。

    链：GET mock-in-storage（remark=天通救援棒-tmn）→ POST groups/{one_id}/terminals。
    任一步失败 pytest.fail（不静默复用）。入库成功即 register_glht_inventory(sn)。
    """
    sep(" 🛰️ 创建卫星救援终端 ")
    sn = generate_rescue_sn()
    key("救援终端 sn", sn)

    # ① 入库
    r = http.send_request(
        method="get",
        url=f"{base_url}/api/monitor/mock-in-storage",
        params={
            "Authorization": auth_headers.get("Authorization"),
            "addr": sn, "sn": sn, "name": "救援测试",
            "remark": "天通救援棒-tmn",
            "terminalType": "TT_RESCUE_STICK",
            "useScope": "STEAMER",
        },
        headers=auth_headers,
        case_name="救援终端入库",
        log_level="none",
    )
    json_data = parse_response_json(r, context="救援终端入库")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"救援终端入库失败: code={code}, msg={msg[0] if msg else '未知'}")
    key("入库", f"sn={sn} type=TT_RESCUE_STICK")

    # 副作用落地即注册（纪律 1）：入库成功立刻登记——
    # 即便下一步「添加设备」失败，session 末也有据可收（真正堵住 glht 入库记录泄漏，
    # 不再依赖"日期猜格式"）。
    from common.cleanup import register_cleanup, register_glht_inventory, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    register_glht_inventory(sn)

    # ② 添加到 one_id 分组（复用 _create_terminal 模板，仅换类型）
    group_id = group_fixture["one_id"]
    body = {
        "sn": sn, "remark": "天通救援棒-tmn", "groupId": group_id,
        "terminalType": "TT_RESCUE_STICK", "useScope": "STEAMER",
        "fromAddr": "", "trackColor": "#141323", "trackSize": 5,
        "groupCallNumber": "", "ipAddress": "", "gatewayParam": {}, "fieldJson": "",
    }
    r = http.send_request(
        method="post",
        url=f"{base_url}/api/monitor/groups/{group_id}/terminals",
        json=body, headers=auth_headers,
        case_name="救援终端添加", log_level="none",
    )
    json_data = parse_response_json(r, context="救援终端添加")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"救援终端添加失败: code={code}, msg={msg[0] if msg else '未知'}")
    key("添加", f"sn={sn} → group={group_id}")

    # sn 的 stash/registry 登记已前移到「入库成功即注册」（堵半途失败泄漏）
    return sn


# B 测试分组（session 内两根棒共用一个 L1）。payload 自带 B headers——
# cleanup_test_data 的 ctx.auth_headers 是 A 的，不能拿来删 B 的组/设备。
_B_STACK = {"one_id": None, "auth_headers": None}


def _ensure_b_l1_group(base_url, auth_headers_b):
    """B token 建一级测试分组；测试棒共用。cleaner 只登记一次。"""
    if _B_STACK["one_id"]:
        return _B_STACK["one_id"]
    sep(" 📦 创建 B 测试一级分组 ")
    suffix = str(int(time.time() * 1000))[-8:]
    resp = http.send_request(
        method="post",
        url=f"{base_url}/api/monitor/groups",
        params={"groupName": f"L1_{suffix}", "parentId": 0},
        headers=auth_headers_b,
        case_name="创建B一级分组",
        log_level="none",
    )
    json_data = parse_response_json(resp, context="创建B一级分组")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"B一级分组创建失败: code={code}, msg={msg[0] if msg else '未知'}")
    gid = _jsonpath_parse(json_data, "$.data.id")[0]
    key("B一级分组ID", gid)
    _B_STACK["one_id"] = gid
    _B_STACK["auth_headers"] = auth_headers_b
    from common.cleanup import register_cleanup, terminal as _t, group as _g
    register_cleanup("b_terminals", _B_STACK, _t.cleaner_b, tier=200)
    register_cleanup("b_groups", _B_STACK, _g.cleaner_b, tier=300)
    return gid


def _provision_b_rescue_stick(base_url, auth_headers_b, label):
    """B 名下救援棒：与 A 同款 web 链。建 L1 → mock-in-storage → POST groups/{id}/terminals。

    不走小程序 pre-bind / bind/addr（会把 webAccount 写成 useruser…）。
    收尾用 B token 删组内设备再删测试分组，不动 B 原「我的分组」。
    """
    group_id = _ensure_b_l1_group(base_url, auth_headers_b)
    sep(f" 🛰️ 创建 B 卫星救援终端 ({label}) ")
    sn = generate_rescue_sn()
    key(f"{label} sn", sn)

    r = http.send_request(
        "get", f"{base_url}/api/monitor/mock-in-storage",
        params={
            "Authorization": auth_headers_b.get("Authorization"),
            "addr": sn, "sn": sn, "name": "救援测试B",
            "remark": "天通救援棒-tmn",
            "terminalType": "TT_RESCUE_STICK",
            "useScope": "STEAMER",
        },
        headers=auth_headers_b, case_name=f"{label}入库", log_level="none",
    )
    json_data = parse_response_json(r, context=f"{label}入库")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"{label}入库失败: code={code}, msg={msg[0] if msg else '未知'}")
    key(f"{label}入库", f"sn={sn} type=TT_RESCUE_STICK")

    from common.cleanup import register_cleanup, register_glht_inventory, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    register_glht_inventory(sn)

    body = {
        "sn": sn, "remark": "天通救援棒-tmn", "groupId": group_id,
        "terminalType": "TT_RESCUE_STICK", "useScope": "STEAMER",
        "fromAddr": "", "trackColor": "#141323", "trackSize": 5,
        "groupCallNumber": "", "ipAddress": "", "gatewayParam": {}, "fieldJson": "",
    }
    r = http.send_request(
        method="post",
        url=f"{base_url}/api/monitor/groups/{group_id}/terminals",
        json=body, headers=auth_headers_b,
        case_name=f"{label}添加", log_level="none",
    )
    json_data = parse_response_json(r, context=f"{label}添加")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"{label}添加失败: code={code}, msg={msg[0] if msg else '未知'}")
    key(f"{label}添加", f"sn={sn} → group={group_id}")
    return sn


@pytest.fixture(scope="session")
def rescue_sat_terminal_b(base_url, auth_headers_b):
    """B 名下救援棒（批 2）。仅被 B 支路 getfixturevalue / 注入时拉活。"""
    return _provision_b_rescue_stick(base_url, auth_headers_b, "B棒1")


@pytest.fixture(scope="session")
def rescue_sat_terminal_b2(base_url, auth_headers_b):
    """B 第二根棒（拒绝支路）。仅拒绝用例注入时拉活。"""
    return _provision_b_rescue_stick(base_url, auth_headers_b, "B棒2")


@pytest.fixture(scope="session")
def rescue_sat_terminal_b3(base_url, auth_headers_b):
    """B 第三根棒（关群非群主-被邀请人）。仅 Ig09 invitee 拉活，勿复用 B棒1。"""
    return _provision_b_rescue_stick(base_url, auth_headers_b, "B棒3")


@pytest.fixture(scope="session")
def emergency_chat_item(base_url, auth_headers, rescue_sat_terminal, rescue_client):
    """造一个求救群聊并提取 chatItemId。

    链：rescue_client.send_sos(sn, kind=1) → 轮询 item/page?itemName=sn（3次×2s）。
    返回 {"chatItemId": ..., "sn": ..., "itemName": ..., "status": 1}。
    失败 pytest.fail 并附 10304 会话/消息日志上下文（归因依据）。
    """
    sn = rescue_sat_terminal
    sep(" 🆘 造求救群聊 ")

    result = rescue_client.send_sos(sn, kind=1)
    if not result.success:
        # 归因：打 10304 会话记录与消息日志
        records = rescue_client.session_records(terminal_id=sn, page_size=3)
        logs = rescue_client.message_logs(terminal_id=sn, page_size=3)
        pytest.fail(
            f"SOS发送失败: code={result.code}, msg={result.message}\n"
            f"  会话记录: {records}\n  消息日志: {logs}"
        )
    key("SOS已发", f"sn={sn} sid={result.session_id}")

    # 轮询搜群（3次×2s，复用 alarm 短轮询模式）
    chat_item = None
    for i in range(3):
        time.sleep(2)
        r = http.send_request(
            method="get",
            url=f"{base_url}/api/monitor/emergency/chat/item/page",
            params={"Authorization": auth_headers.get("Authorization"),
                    "itemName": sn, "page": 1, "pageSize": 10},
            headers=auth_headers,
            case_name=f"搜群第{i+1}轮",
            log_level="none",
        )
        json_data = parse_response_json(r, context="搜群")
        items = _jsonpath_parse(json_data, "$.data.items[*]") or \
                _jsonpath_parse(json_data, "$.data.records[*]") or []
        if items:
            chat_item = items[0]
            break

    if not chat_item:
        records = rescue_client.session_records(terminal_id=sn, page_size=3)
        pytest.fail(f"搜群超时: sn={sn} 未找到群聊。10304会话记录: {records}")

    chat_id = chat_item.get("id")
    item_name = chat_item.get("itemName")
    status = chat_item.get("status")
    key("群聊创建成功", f"chatItemId={chat_id} itemName={item_name} status={status}")

    # chatItemId 写 extract.yaml 供同文件下游用例消费
    from common.yaml_util import write_yaml
    write_yaml("./extract.yaml", {
        "emergency_chat_item_id": chat_id,
        "emergency_chat_sn": sn,
        "emergency_chat_item_name": item_name,
    }, mode="append")

    return {
        "chatItemId": chat_id,
        "sn": sn,
        "itemName": item_name,
        "status": status,
        "created_at": time.time(),  # 建群时刻（U2上报时刻近似）——供上报间隔合规计算
    }


@pytest.fixture(scope="session")
def emergency_chat_voice(base_url, auth_headers, emergency_chat_item, rescue_client) -> dict:
    """主群 complete 前上行一条终端语音（U5）——TestEc10ItemComplete 正向 case 消费。

    协议约束（2026-08-17 主人定稿）：终端上报消息间隔必须 >60s。
    - 间隔合规：距建群（U2 SOS 上报）不足 VOICE_DELAY_SECONDS(默认60s) 时补足等待；
      全量跑 Ec01~Ec09 天然间隔足够，仅单跑 Ec10 时会真正等待。
    - 落库闸门：轮询 record/page 确认新增 sendType=VOICE 记录后才放行 complete
      （complete 是状态机闸门，语音必须在途完成落库，否则完结拦截行为未验证）。
    - 会话兜底：60s 空闲后 uplink-sim 会话可能超时——send_speech 失败时
      login_terminal(sn) 重建会话后重发 1 次。
    返回 {"voiceRecordId":..., "chatItemId":..., "sn":...}。
    """
    import os as _os
    sn = emergency_chat_item["sn"]
    chat_id = emergency_chat_item["chatItemId"]
    delay = float(_os.getenv("VOICE_DELAY_SECONDS", "60"))

    elapsed = time.time() - emergency_chat_item.get("created_at", 0)
    wait = delay - elapsed
    if wait > 0:
        sep(f" 🎙️ 终端语音上报间隔合规等待 {wait:.0f}s（协议约束：上报间隔>60s） ")
        time.sleep(wait)
    else:
        key("间隔合规", f"距建群已 {elapsed:.0f}s，满足 >{delay:.0f}s 约束，无需等待")

    # 上报（失败→重建会话→重发1次）
    result = rescue_client.send_speech(sn)
    if not result.success:
        key("会话兜底", f"send_speech 失败(code={result.code})，login_terminal 重建后重发")
        rescue_client.login_terminal(sn)
        result = rescue_client.send_speech(sn)
    if not result.success:
        pytest.fail(f"终端语音上报失败(含会话重建重试): code={result.code}, msg={result.message}")

    # 落库闸门：轮询 record 确认 VOICE 落库（发送成功≠落地，机制认知#1）
    voice_record = None
    for i in range(3):
        time.sleep(2)
        r = http.send_request(
            method="get",
            url=f"{base_url}/api/monitor/emergency/chat/record/page",
            params={"Authorization": auth_headers.get("Authorization"),
                    "chatItemId": chat_id, "page": 1, "pageSize": 20},
            headers=auth_headers,
            case_name=f"语音落库确认第{i+1}轮",
            log_level="none",
        )
        items = _jsonpath_parse(r.json(), "$.data.items[*]") or []
        voice_record = next((it for it in items if it.get("sendType") == "VOICE"
                             and str(it.get("avatarInfo", {}).get("memberAccount") or "") == sn), None)
        if voice_record:
            break
    if not voice_record:
        records = rescue_client.session_records(terminal_id=sn, page_size=3)
        pytest.fail(f"终端语音未落库(3×2s轮询超时): sn={sn} chatItemId={chat_id}。"
                    f"10304会话记录: {records}")

    key("终端语音已落库", f"recordId={voice_record.get('id')}")
    return {
        "voiceRecordId": voice_record.get("id"),
        "chatItemId": chat_id,
        "sn": sn,
    }


# ==================== 自动清理 ====================
@pytest.fixture(scope="session", autouse=True)
def clear_data_per_session():
    """在 session 开始和结束时清理临时数据文件"""
    sep(" 🚀 测试开始 ")
    clear_yaml()
    yield
    sep(" 🏁 测试结束 ")


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(base_url, auth_headers, group_fixture, pytestconfig):
    """session 末统一清理：一行调度（清理逻辑见 common/cleanup/ 子包）。

    注册来源（副作用落地即注册）：
      group_fixture → groups(tier300) + terminals(tier200)  # A token
      rescue_sat_terminal → rescue_chat_{sn}(tier100，入库成功即注册)
      rescue_sat_terminal_b → b_terminals(200) + b_groups(300)（payload 自带 B headers）
      用例 buy → unpaid_orders(tier100，经包级入口 register_unpaid_order_no)
      4 处 mock-in-storage 入库点 → glht_inventory_{sn}(tier400) + glht_inventory_flush(tier410，
        经包级入口 register_glht_inventory，按 sn 精确查删，格式无关)
    执行序由 registry tier 保证：群/订单(100) → 设备(200) → 分组(300) → 外部系统(400/410)。
    """
    yield

    if not ENABLE_AUTO_CLEANUP:
        sep(" ⚠️  自动清理已禁用 (ENABLE_AUTO_CLEANUP=false)")
        return

    sep(" 🧹 开始清理测试数据 ")
    from common.cleanup import CleanupContext, run_session_cleanup
    ctx = CleanupContext(base_url=base_url, auth_headers=auth_headers)
    report = run_session_cleanup(ctx)  # 订单默认收走；keep_orders 参数位留待扫码场景

    # report 落盘：allure 附件 + cleanup-report.yaml 追写（泄漏可归因物证）
    try:
        import yaml
        with open("./cleanup-report.yaml", "a", encoding="utf-8") as f:
            f.write(yaml.safe_dump(
                {"session_cleanup": report}, allow_unicode=True, sort_keys=True))
        if allure:
            allure.attach(
                json.dumps(report, indent=2, ensure_ascii=False),
                name="【收尾】清理报告",
                attachment_type=allure.attachment_type.JSON,
            )
        key("清理报告", report)
    except Exception as exc:
        key("⚠️ 清理报告落盘失败", str(exc))

    sep(" 🎉 清理完成 ")
