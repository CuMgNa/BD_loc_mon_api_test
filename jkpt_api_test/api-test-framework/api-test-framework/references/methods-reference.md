# API测试框架 — 完整方法签名参考

## 目录
- [1. api_test_framework/client.py](#1-apitest_frameworkclientpy)
- [2. api_test_framework/config.py](#2-apitest_frameworkconfigpy)
- [3. api_test_framework/data.py](#3-apitest_framewordatapy)
- [4. api_test_framework/assertions.py](#4-apitest_frameworkassertionspy)
- [5. api_test_framework/schema.py](#5-apitest_frameworkschemapy)
- [6. api_test_framework/runner.py](#6-apitest_frameworkrunnerpy)
- [7. api_test_framework/pytest_plugin.py](#7-apitest_frameworkpytest_pluginpy)
- [8. common/requests_util.py](#8-commonrequests_utilpy)
- [9. common/yaml_util.py](#9-commonyaml_utilpy)
- [10. common/ipconfig.py](#10-commonipconfigpy)
- [11. common/common_data.py](#11-commoncommon_datapy)
- [12. common/allure_assert_util.py](#12-commonallure_assert_utilpy)
- [13. common/logger_util.py](#13-commonlogger_utilpy)
- [14. common/captcha_util.py](#14-commoncaptcha_utilpy)
- [15. conftest.py 常用fixture和hook](#15-conftestpy-常用fixture和hook)

---

## 1. api_test_framework/client.py

### `sanitize_data(value) -> Any`
递归脱敏敏感字段。自动隐藏 key 中包含 authorization/cookie/password/token/secret/key 的值。

| 参数 | 类型 | 说明 |
|------|------|------|
| value | Any | 任意数据（dict/list/基本类型） |
| 返回 | Any | 脱敏后的副本（原对象不变） |

### class `BaseRequest`
轻量 requests.Session 封装。

```python
class BaseRequest:
    def __init__(
        self,
        session: requests.Session | None = None,   # 复用已有session
        logger: logging.Logger | None = None,       # 自定义日志器
        debug: bool = True,                          # 是否记录日志
        default_timeout: float | None = 30,          # 默认超时(秒)
    ) -> None: ...

    def send_request(self, **kwargs) -> requests.Response:
        """
        发送HTTP请求。
        
        标准requests参数: method, url, params, json, data, headers, files, timeout
        框架扩展参数:
          - case_name: str     日志中的用例标识 (默认 "unknown case")
          - log_level: str     "full"|"simple"|"none" (默认 "full")
        
        自动行为:
          - 未指定timeout时使用default_timeout
          - debug=True时自动记录请求/响应日志
          - 异常时记录完整错误堆栈
        """
```

---

## 2. api_test_framework/config.py

### class `ApiTestConfig` (dataclass)
配置数据模型。

| 字段 | 类型 | 默认值 | 环境变量 |
|------|------|--------|---------|
| base_url | str | "" | API_TEST_BASE_URL |
| host | str | "127.0.0.1" | API_TEST_HOST |
| port | int \| None | None | API_TEST_PORT |
| scheme | str | "http" | API_TEST_SCHEME |
| timeout | float | 30 | API_TEST_TIMEOUT |
| environment | str | "local" | API_TEST_ENV |
| allure_enabled | bool | True | API_TEST_ALLURE_ENABLED |
| results_dir | str | "temps" | API_TEST_RESULTS_DIR |
| extract_file | str | "extract.yaml" | API_TEST_EXTRACT_FILE |
| log_level | str | "INFO" | API_TEST_LOG_LEVEL |

#### `resolved_base_url() -> str`
按优先级返回完整URL: base_url → host:port → host

#### `from_mapping(data: dict) -> ApiTestConfig` (classmethod)
从字典构建，自动过滤未知字段、处理空字符串port。

### `load_config(path=None, prefix="API_TEST_") -> ApiTestConfig`
加载配置：先读YAML文件，再用环境变量覆盖。环境变量优先级更高。

---

## 3. api_test_framework/data.py

### 文件操作函数
```python
def read_yaml(path: str | Path) -> Any      # YAML→Python对象
def write_yaml(path: str | Path, data: Any) # Python对象→YAML文件
def read_json(path: str | Path) -> Any      # JSON→Python对象
def write_json(path: str | Path, data: Any) # Python对象→JSON文件
def clear_file(path: str | Path) -> None    # 清空文件内容
```

### class `VariableStore`
内存键值存储 + 占位符解析引擎。

```python
class VariableStore:
    def __init__(self, initial: dict[str, Any] | None = None) -> None: ...
    
    def set(self, name: str, value: Any) -> None:      # 存储变量
    
    def get(self, name: str, default: Any = None) -> Any:  # 获取变量
    
    def as_dict(self) -> dict[str, Any]:                 # 导出全部为字典
    
    def resolve(self, value: Any) -> Any:
        """
        递归解析 {{variable_name}} 占位符。
        支持str/dict/list嵌套。
        未找到的变量保留原始 {{xxx}} 文本。
        """
```

**resolve 示例**:
```python
store = VariableStore({"user_id": 42, "name": "test"})
store.resolve("user_{{user_id}}")           # → "user_42"
store.resolve({"id": "{{user_id}}"})         # → {"id": 42}
store.resolve(["{{name}}", "hello"])         # → ["test", "hello"]
store.resolve("{{unknown_key}}")             # → "{{unknown_key}}" （不替换）
```

---

## 4. api_test_framework/assertions.py

### `assert_response(response: Response, case: ApiCase | dict) -> None`
执行一个用例中声明的所有断言。内部流程：
1. 断言 HTTP status_code（如果 expected.status_code 存在）
2. 断言 body 字段精确匹配（如果 expected.body 是 dict）
3. 遍历 assertions 列表逐个执行

### `extract_json_path(data: Any, path: str) -> Any`
轻量级 JSONPath 提取器。支持语法：`$.a.b[0].c`

| 输入示例 | 返回 |
|---------|------|
| `{"code": 0}`, `"$.code"` | `0` |
| `{"data": {"token": "abc"}}`, `"$.data.token"` | `"abc"` |
| `{"list": [1,2,3]}, "$.list[1]"` | `2` |
| `{"data": {...}}, "$"` | 整个 data |

路径不存在时返回 `None`。

### 支持的断言类型 (`assertions` 列表项)

```python
# type: status_code — HTTP状态码
{"type": "status_code", "expected": 200}

# type: jsonpath_equal — JSONPath精确匹配
{"type": "jsonpath_equal", "path": "$.code", "expected": 0}

# type: jsonpath_exists — 字段存在性检查
{"type": "jsonpath_exists", "path": "$.data.token"}

# type: contains — 响应文本包含
{"type": "contains", "expected": "success"}
```

---

## 5. api_test_framework/schema.py

### class `ApiCase` (dataclass, slots=True)
标准API用例模型。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | str | ✅ | 用例名称 |
| method | str | ✅ | HTTP方法（自动转大写） |
| path | str | ✅ | 接口路径 |
| case_id | str \| None | ❌ | 用例唯一ID |
| tags | list[str] | ❌ | 标签列表 |
| auth_required | bool | ❌ | 是否需要认证（默认False） |
| request | dict | ❌ | 请求数据(headers/params/json/data/files等) |
| expected | dict | ❌ | 预期结果(status_code/body) |
| assertions | list[dict] | ❌ | 声明式断言列表 |
| extract | dict | ❌ | 要提取的变量 {name: jsonpath} |
| setup | list[dict] | ❌ | 前置步骤 |
| teardown | list[dict] | ❌ | 后置步骤 |
| meta | dict | ❌ | 元数据 |

#### `from_dict(raw: Mapping) -> ApiCase` (classmethod)
从字典构建，校验 name/method/path 必填字段。

#### `to_dict() -> dict`
转为字典，自动过滤空值字段。

### `normalize_case(raw: ApiCase | Mapping) -> ApiCase`
统一转换入口：ApiCase直接返回，dict则调用from_dict。

---

## 6. api_test_framework/runner.py

### `run_case(case, *, base_url, client=None, headers=None, variables=None) -> Response`
执行单个用例的完整生命周期。

| 参数 | 类型 | 说明 |
|------|------|------|
| case | ApiCase \| dict | 用例数据（自动normalize） |
| base_url | str | 基础URL |
| client | BaseRequest \| None | HTTP客户端（默认新建） |
| headers | dict \| None | 额外请求头 |
| variables | VariableStore \| None | 变量存储（默认新建） |

**执行流程**:
1. normalize_case() → 统一为 ApiCase
2. store.resolve(request) → 替换 {{变量}}
3. 合并 headers
4. BaseRequest.send_request() → 发请求
5. assert_response() → 执行所有断言
6. _extract_values() → 提取变量到 store
7. 返回 Response

---

## 7. api_test_framework/pytest_plugin.py

### 命令行参数
| 参数 | 说明 |
|------|------|
| `--api-config` | 配置文件路径(YAML) |
| `--api-base-url` | 直接指定base_url |
| `--api-host` | 指定主机 |
| `--api-port` | 指定端口(int) |
| `--api-no-allure` | 禁用Allure附件 |

### 提供的Fixture
| Fixture名 | 作用域 | 返回类型 | 说明 |
|-----------|--------|---------|------|
| `api_config` | session | ApiTestConfig | 配置对象 |
| `base_url` | session | str | 解析后的完整URL |
| `api_client` | session | BaseRequest | 预配置客户端 |
| `api_variables` | session | VariableStore | 变量存储 |
| `api_headers` | session | dict | 空header字典(可覆写) |
| `clear_extract_file` | session autouse | None | 清空extract.yaml |
| `attach_requests_to_allure` | function autouse | None | Allure monkey-patch |

---

## 8. common/requests_util.py

### class `BaseRequest` (增强版)
⭐ **这是手写测试用例的主要入口类**

```python
class BaseRequest:
    def __init__(self, debug=True):
        self.session = requests.Session()
        self.debug = debug

    def send_request(self, **kwargs) -> requests.Response:
        """
        核心请求方法。
        
        标准requests参数: method, url, params, json, data, headers, files, timeout
        框架参数:
          - case_name: str  用例名称 (默认 '未知用例')
          - log_level: str  "full"|"simple"|"none" (默认 'full')
        
        与核心层client.py的区别:
          - 使用emoji风格日志 (🚀✅🟢🔴❌)
          - 自动识别业务码并带颜色标记
          - _safe_headers() 超长Authorization截断+隐藏关键字段
        """
    
    def enable_debug(self) -> None: ...   # 启用日志
    def disable_debug(self) -> None: ...  # 禁用日志
```

**日志输出示例** (log_level="simple"):
```
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀 请求开始 🚀...
📋 用例: 登录测试
📍 方法: POST
📍 URL: http://192.168.1.100:9004/api/login
📍 参数: {'account': 'admin', 'password': '***'}
✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅ 响应开始 ✅...
📋 用例: 登录测试
📊 状态码: 200
📊 请求耗时: 0.153秒
📊 业务码: 0
📊 消息: success
🟢 业务状态: code=0, msg=success
✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅✅ 响应结束 ✅...
```

---

## 9. common/yaml_util.py

```python
def read_yaml(file_path) -> Any:
    """读取yaml文件 → Python对象"""

def write_yaml(data) -> None:
    """追加写入 ./extract.yaml（运行时跨用例持久化变量）"""

def clear_yaml() -> None:
    """清空 ./extract.yaml"""
```

---

## 10. common/ipconfig.py

```python
def get_local_ips() -> list[str]:
    """
    获取本机所有IPv4地址，排除127.x.x.x回环地址。
    返回: ["192.168.1.100"] 或 fallback ["127.0.0.1"]
    """
```

---

## 11. common/common_data.py

```python
def get_current_datetime() -> str:
    """
    返回当前时间紧凑格式字符串。
    用于生成唯一的测试数据名称。
    返回示例: "20260427133000"
    """
```

---

## 12. common/allure_assert_util.py

### `assert_api_result(case_name, expected_code, expected_msg, actual_code, actual_msg, biz_context=None) -> None`

统一接口断言与 Allure 附件输出。

| 参数 | 类型 | 说明 |
|------|------|------|
| case_name | str | 用例名称（用于断言报错与附件） |
| expected_code | Any | 预期业务码 |
| expected_msg | str | 预期错误信息/提示 |
| actual_code | Any | 实际业务码 |
| actual_msg | str | 实际错误信息/提示 |
| biz_context | dict \| None | 业务上下文（可选，建议传请求参数、动态变量） |

**行为约定**:
- 断言通过：打印成功日志并附加 `【成功】验证结果` 文本附件
- 断言失败：附加 `【失败】验证失败上下文` JSON 附件，并抛出带用例名的清晰断言错误

### `_attach_text(content, name) -> None`
内部辅助：安全附加 TEXT 附件（allure 不可用时自动跳过）。

### `_attach_json(data, name) -> None`
内部辅助：安全附加 JSON 附件（allure 不可用时自动跳过）。

---

## 13. common/logger_util.py

```python
def sep(title="") -> None:
    """打印分隔线；有title时打印标题块"""

def key(key, value) -> None:
    """打印键值对"""

def print_request(method, url, params=None, headers=None) -> None:
    """格式化打印请求信息（包含基础脱敏）"""

def print_response(response) -> None:
    """格式化打印响应信息（优先输出JSON）"""

def print_result(success=True, message="") -> None:
    """打印测试结果（✅/❌）"""
```

**使用建议**:
- 用例日志统一走该模块，输出风格保持一致
- 请求输出中应始终对密码、token 等敏感字段脱敏

---

## 14. common/captcha_util.py

### class `CaptchaRecognizer`

```python
class CaptchaRecognizer:
    def __init__(self) -> None:
        # 初始化 ddddocr 识别器
        ...

    def recognize(self, image_bytes: bytes) -> str:
        """识别验证码图片字节，返回字符串"""

    def recognize_from_response(self, response) -> str:
        """从 requests.Response.content 直接识别验证码"""
```

**典型调用**:
```python
ocr = CaptchaRecognizer()
captcha_text = ocr.recognize_from_response(resp)
```

---

## 15. conftest.py 常用fixture和hook

### `pytest_configure(config) -> None`
设置全局配置（如 `base_url`）并输出启动信息。

### `base_url(pytestconfig) -> str` (fixture, session)
返回基础 URL。

### `generate_captcha_id() -> str`
生成验证码请求用 `captchaId`（时间戳 + 随机数）。

### `auth_token(base_url) -> str` (fixture, session)
验证码识别 + 登录获取 token（建议内置重试机制）。

### `auth_headers(auth_token) -> dict` (fixture, session)
基于 token 返回认证请求头。

### `pytest_runtest_makereport(item, call)` (hookimpl)
测试失败时附加请求/响应/错误/断言详情到 Allure。

### `clear_data_per_session()` (fixture, session, autouse)
测试会话前清理 `extract.yaml`，会话结束收尾日志输出。
