# conftest.py
import pytest
import time
import datetime
import random
import logging
import json
import traceback
import os
from common.requests_util import BaseRequest, get_last_http_context, NonJsonResponseError, parse_response_json
from common.yaml_util import clear_yaml
from common.captcha_util import CaptchaRecognizer
from common.logger_util import sep, key, print_request, print_response
from common.bd_protocol_client import BDProtocolClient
from common.protocol_transport import BDProtocolTransport
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


# ==================== 自动清理 ====================
@pytest.fixture(scope="session", autouse=True)
def clear_data_per_session():
    """在 session 开始和结束时清理临时数据文件"""
    sep(" 🚀 测试开始 ")
    clear_yaml()
    yield
    sep(" 🏁 测试结束 ")


# ==================== 设备和分组清理 ====================
def get_terminals_by_group(base_url, auth_headers, group_id):
    """获取指定分组下的所有设备地址列表"""
    url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
    params = {"page": 1, "pageSize": 1000}

    resp = http.send_request(
        method="get",
        url=url,
        params=params,
        headers=auth_headers,
        case_name=f"获取分组 {group_id} 下的设备",
        log_level="none"
    )

    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]

    if code == 0:
        terminals = _jsonpath_parse(json_data, "$.data.items[*].addr")
        return terminals if terminals else []

    key(f"获取分组 {group_id} 设备失败", "将返回空列表")
    return []


def cleanup_terminals_batch(base_url, auth_headers, group_id, addrs):
    """批量删除指定分组下的设备"""
    if not addrs:
        key(f"分组 {group_id}", "无设备需要删除")
        return 0, 0

    url = f"{base_url}/api/monitor/terminals/batch"
    data = {"addrs": ",".join(addrs)}

    resp = http.send_request(
        method="delete",
        url=url,
        json=data,
        headers=auth_headers,
        case_name=f"批量删除分组 {group_id} 下的设备",
        log_level="none"
    )

    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]

    if code == 0:
        key(f"✅ 分组 {group_id} 设备删除", f"成功删除 {len(addrs)} 个设备")
        return len(addrs), 0

    msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
    key(f"❌ 分组 {group_id} 设备删除失败", f"code={code}, msg={msg}")
    return 0, len(addrs)


def delete_groups_in_order(base_url, auth_headers, group_ids):
    """按顺序删除分组：三级 → 二级 → 一级"""
    groups_url = f"{base_url}/api/monitor/groups"
    success_count = 0
    fail_count = 0

    for level in ["three_id", "two_id", "one_id"]:
        group_id = group_ids.get(level)
        if group_id is None:
            continue

        delete_url = f"{groups_url}/{group_id}"
        resp = http.send_request(
            method="delete",
            url=delete_url,
            headers=auth_headers,
            case_name=f"删除{level}分组 {group_id}",
            log_level="none"
        )

        json_data = resp.json()
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code == 0:
            success_count += 1
            key(f"✅ 删除{level}分组 {group_id}", "成功")
        else:
            fail_count += 1
            msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
            key(f"❌ 删除{level}分组 {group_id} 失败", f"code={code}, msg={msg}")

    return success_count, fail_count


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(base_url, auth_headers, group_fixture, pytestconfig):
    """在 session 结束时自动清理测试数据和分组"""
    yield

    if not ENABLE_AUTO_CLEANUP:
        sep(" ⚠️  自动清理已禁用 (ENABLE_AUTO_CLEANUP=false)")
        return

    sep(" 🧹 开始清理测试数据 ")
    group_dict = pytestconfig.stash.get("test_group_ids", group_fixture)

    sep(" 步骤1: 删除设备 ")
    total_deleted_terminals = 0
    total_failed_terminals = 0

    for level in ["three_id", "two_id", "one_id"]:
        group_id = group_dict.get(level)
        if not group_id:
            continue
        addrs = get_terminals_by_group(base_url, auth_headers, group_id)
        if addrs:
            deleted, failed = cleanup_terminals_batch(base_url, auth_headers, group_id, addrs)
            total_deleted_terminals += deleted
            total_failed_terminals += failed

    key("设备删除统计", f"成功: {total_deleted_terminals}, 失败: {total_failed_terminals}")

    sep(" 步骤2: 删除分组 ")
    group_success, group_fail = delete_groups_in_order(base_url, auth_headers, group_dict)
    key("分组删除统计", f"成功: {group_success}, 失败: {group_fail}")

    sep(" 🎉 清理完成 ")


# ==================== glht 管理员系统清理（独立运转） ====================
GLHT_BASE_URL_DEFAULT = "http://back.tdwt.admin.pg8.ink"


def _glht_cleanup_inventory(glht_token: str, glht_base_url: str, date_str: str) -> int:
    """循环查询并删除 glht 入库记录，返回总删除条数（内部函数）

    使用 seen_ids 去重防止删除最终一致性延迟导致的重复计数。
    """
    seen_ids: set[str] = set()
    max_loops = 50
    for _ in range(max_loops):
        resp = http.send_request(
            method="get",
            url=f"{glht_base_url}/api/admin/inventory",
            params={
                "Authorization": glht_token,
                "content": date_str,
                "index": 0,
                "specifyTime": "false",
                "startTimeStr": "",
                "endTimeStr": "",
                "page": 1,
                "pageSize": 100,
            },
            case_name=f"glht查询入库记录 {date_str}",
            log_level="none",
        )
        json_data = parse_response_json(resp, context="glht查询入库记录")
        code = _jsonpath_parse(json_data, "$.code")[0]
        if code != 0:
            key("glht查询失败", f"code={code}")
            break

        ids_raw = _jsonpath_parse(json_data, "$.data.items[*].id")
        if not ids_raw:
            if not seen_ids:
                key(f"glht {date_str}", "无入库记录")
            break

        new_ids = [str(i) for i in ids_raw if i and str(i) not in seen_ids]
        if not new_ids:
            break

        del_resp = http.send_request(
            method="delete",
            url=f"{glht_base_url}/api/admin/inventory",
            params={"Authorization": glht_token},
            json={"ids": ",".join(new_ids)},
            case_name="glht批量删除入库记录",
            log_level="none",
        )
        del_json = parse_response_json(del_resp, context="glht删除入库记录")
        del_code = _jsonpath_parse(del_json, "$.code")[0]
        if del_code != 0:
            msg_list = _jsonpath_parse(del_json, "$.msg")
            del_msg = msg_list[0] if msg_list else "未知"
            key("glht删除失败", f"code={del_code}, msg={del_msg}")
            break

        seen_ids.update(new_ids)
        key(f"glht清理 {date_str}", f"本批删除 {len(new_ids)} 条")

    return len(seen_ids)


@pytest.fixture(scope="session")
def glht_base_url():
    """glht 管理员系统 base URL"""
    import os
    return os.environ.get("GLHT_BASE_URL", GLHT_BASE_URL_DEFAULT)


@pytest.fixture(scope="session")
def glht_token(glht_base_url):
    """glht 管理员系统登录，获取 glht token"""
    import hashlib
    sep(" 🔐 glht 管理员登录 ")
    password_md5 = hashlib.md5("123abc!!".encode()).hexdigest()
    resp = http.send_request(
        method="post",
        url=f"{glht_base_url}/api/admin/login",
        json={"account": "admin", "password": password_md5},
        case_name="glht管理员登录",
        log_level="none",
    )
    json_data = parse_response_json(resp, context="glht管理员登录")
    code = _jsonpath_parse(json_data, "$.code")[0]
    assert code == 0, f"glht 登录失败: code={code}, msg={_jsonpath_parse(json_data, '$.msg')[0]}"
    token = _jsonpath_parse(json_data, "$.data.token")[0]
    key("glht token", f"{token[:20]}...")
    return token


@pytest.fixture(scope="session", autouse=True)
def glht_cleanup_test_data(glht_token, glht_base_url):
    """glht 入库记录清理（session 结束时自动执行，独立于 jkpt cleanup_test_data）"""
    from datetime import datetime, timezone, timedelta

    yield

    if not ENABLE_AUTO_CLEANUP:
        sep(" ⚠️  glht 自动清理已禁用 (ENABLE_AUTO_CLEANUP=false)")
        return

    sep(" 🧹 glht 入库记录清理 ")
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
    try:
        deleted = _glht_cleanup_inventory(glht_token, glht_base_url, today)
        key("glht清理结果", f"删除 {deleted} 条入库记录")
    except Exception as e:
        key("glht清理异常", str(e))

    sep(" 🎉 glht 清理完成 ")