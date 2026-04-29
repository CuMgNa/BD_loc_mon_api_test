"""
conftest.py — API自动化测试项目标准模板
从 api-test-framework Skill 生成
使用说明: 将【修改点】标注的地方替换为你的实际配置即可
"""

# ==================== 第一部分：导入（基本不变）====================
from common.ipconfig import get_local_ips
import jsonpath
from common.yaml_util import clear_yaml
from common.requests_util import BaseRequest
import json, allure, requests, pytest
from logs import get_logger
import traceback

_test_logger = get_logger(name="test_case", log_level="INFO")

# ==================== 第二部分：全局数据管理器（推荐保留）====================
class GlobalData:
    """跨用例共享数据的容器"""
    def __init__(self):
        self.devices = []

    def add_device(self, device_info):
        self.devices.append(device_info)

global_device_data = GlobalData()

@pytest.fixture(scope="session")
def device_manager():
    return global_device_data

# ==================== 第三部分：命令行参数 + 动态URL配置 ====================
def pytest_addoption(parser):
    parser.addoption("--host", action="store", default=None,
                     help="手动指定测试主机IP")

def pytest_configure(config):
    # 【修改点1】改成你的服务端口号和协议
    ip = config.getoption("--host") or get_local_ips()[0]
    base_url = f"http://{ip}:9004"          # ← 改端口号
    config.doubao_base_url = base_url
    print(f"\n\033[92m[配置] base_url: {base_url}\033[0m", flush=True)

@pytest.fixture(scope="session")
def base_url(pytestconfig):
    return pytestconfig.doubao_base_url

# ==================== 第四部分：【必须定制】认证Fixture ====================
@pytest.fixture(scope="session")
def auth_token(base_url):
    """登录获取token"""
    # 【修改点2】改成你的登录接口
    url = f"{base_url}/api/xxx/login"       # ← 登录接口路径
    payload = {
        "account": "admin",                 # ← 你的账号
        "password": "your_password_here",   # ← 你的密码(建议放环境变量)
    }
    res = BaseRequest().send_request(method="post", url=url, params=payload)
    token = jsonpath.JSONPath("$.data.token").parse(res.json())[0]
    if not token:
        pytest.fail("登录失败，无法获取token")
    return token

@pytest.fixture(scope="session")
def auth_headers(auth_token):
    """构造认证请求头"""
    # 【修改点3】按你的认证方式调整header格式
    return {
        "Authorization": f"{auth_token}",  # 可能是 Bearer xxx / Token xxx 等
    }

# ==================== 第五部分：【按需添加】业务前置数据Fixture ====================
# 示例：如果你的测试需要预先存在某些资源，在这里添加fixture
#
# @pytest.fixture(scope="session")
# def groupid(base_url, auth_headers):
#     """预创建测试分组"""
#     url = f"{base_url}/api/groups"
#     res = BaseRequest().send_request(method="post", url=url,
#                                       params={"groupName": "测试分组"},
#                                       headers=auth_headers)
#     return jsonpath.JSONPath("$.data.id").parse(res.json())[0]

# ==================== 第六部分：自动钩子（直接复制，不用改）====================
@pytest.fixture(scope="session", autouse=True)
def clear_data_per_session():
    clear_yaml()
    yield

@pytest.fixture(autouse=True)
def log_all_requests_and_responses():
    """全局自动记录请求/响应到Allure报告（monkey-patch）"""
    original_request = requests.Session.request

    def wrapped_request(session, method, url, **kwargs):
        # --- 请求记录 ---
        query_params = parse_query_params(url, kwargs.get('params'))
        request_info = {
            "method": method.upper(),
            "url": url,
            "query_params": query_params,
            "headers": sanitize_data(kwargs.get('headers', {})),
            "body": extract_body(kwargs),
        }
        allure.attach(
            json.dumps(request_info, indent=2, ensure_ascii=False),
            name="Request", attachment_type=allure.attachment_type.JSON
        )

        response = original_request(session, method, url, **kwargs)

        # --- 响应记录 ---
        try:
            resp_body = response.json()
            body_type, body_data = "json", sanitize_data(resp_body)
        except (ValueError, Exception):
            resp_body = response.text[:10000]
            body_type, body_data = "text", resp_body

        response_info = {
            "status": response.status_code,
            "headers": sanitize_data(dict(response.headers)),
            "body": {"type": body_type, "data": body_data},
            "time_ms": response.elapsed.total_seconds() * 1000,
        }
        allure.attach(
            json.dumps(response_info, indent=2, ensure_ascii=False),
            name="Response", attachment_type=allure.attachment_type.JSON
        )
        return response

    requests.Session.request = wrapped_request
    yield
    requests.Session.request = original_request


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """记录每个测试的执行结果到日志"""
    outcome = yield
    rep = outcome.get_result()
    test_name = item.name
    test_file = item.fspath.basename if hasattr(item, 'fspath') else 'unknown'
    test_class = item.cls.__name__ if item.cls else 'None'

    if rep.when == "setup":
        _test_logger.info(f"{'='*60}")
        _test_logger.info(f"测试开始 | 文件: {test_file} | 类: {test_class} | 用例: {test_name}")

    if rep.when == "call":
        if rep.outcome == "passed":
            _test_logger.info(f"✅ 通过 | {test_file} | {test_class} | {test_name}")
        elif rep.outcome == "failed":
            _test_logger.error(f"❌ 失败 | {test_file} | {test_class} | {test_name}")
            if rep.longrepr:
                _test_logger.error(f"原因: {rep.longrepr}")
            if call and call.excinfo:
                exc_type = call.excinfo.type.__name__ if call.excinfo.type else "?"
                exc_value = str(call.excinfo.value) if call.excinfo.value else "?"
                _test_logger.error(f"异常: {exc_type} | {exc_value}")
        elif rep.outcome == "skipped":
            _test_logger.warning(f"⏭️ 跳过 | {test_file} | {test_class} | {test_name}")

    if rep.when == "teardown":
        _test_logger.info(f"结束 | {test_file} | {test_class} | {test_name}")
        _test_logger.info(f"{'='*60}")

    return rep


# ==================== 第七部分：辅助函数（直接复制，不用改）====================
def sanitize_data(data):
    """过滤敏感信息"""
    if isinstance(data, dict):
        return {k: "******" if any(s in k.lower() for s in ['pass', 'token', 'auth', 'secret', 'key'])
                else v for k, v in data.items()}
    return data


def parse_query_params(url, params_kwarg):
    """合并URL查询参数和params参数"""
    from urllib.parse import urlparse, parse_qsl
    url_parsed = urlparse(url)
    url_params = dict(parse_qsl(url_parsed.query))
    if params_kwarg:
        if isinstance(params_kwarg, dict):
            url_params.update(params_kwarg)
        elif isinstance(params_kwarg, str):
            url_params.update(dict(parse_qsl(params_kwarg)))
    return sanitize_data(url_params)


def extract_body(kwargs):
    """
    分步提取请求body。
    返回: {"type": "json/form/binary/raw", "data": ...}
    """
    if 'json' in kwargs:
        return {"type": "json", "data": sanitize_data(kwargs['json'])}
    if 'data' not in kwargs:
        return None
    data = kwargs['data']
    if isinstance(data, dict):
        return {"type": "form", "data": sanitize_data(data)}
    if isinstance(data, (str, bytes)):
        try:
            if isinstance(data, bytes): data = data.decode('utf-8')
            try:
                parsed = json.loads(data)
                return {"type": "json", "data": sanitize_data(parsed)}
            except json.JSONDecodeError:
                pass
            if 'application/x-www-form-urlencoded' in kwargs.get('headers', {}).get('Content-Type', ''):
                return {"type": "form", "data": sanitize_data(dict(parse_qsl(data)))}
        except (UnicodeDecodeError, ValueError):
            pass
        return {"type": "raw", "data": str(data)[:1000]}
    if 'files' in kwargs:
        return {"type": "binary", "data": f"File upload: {list(kwargs['files'].keys())}"}
    return {"type": "raw", "data": str(data)[:1000]}
