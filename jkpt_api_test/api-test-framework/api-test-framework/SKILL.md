---
name: api-test-framework
description: >
  API自动化测试框架编码参考规范。当用户需要编写API接口自动化测试用例、
  生成测试代码、搭建新项目测试框架、或涉及pytest+YAML数据驱动的接口测试时触发。
  覆盖BaseRequest请求类、conftest.py fixture编写、YAML测试数据格式、
  参数化断言模式、Allure报告集成等全流程。触发词：
  写接口测试、API自动化、写测试用例、pytest参数化、YAML数据驱动、
  搭建测试框架、生成测试代码、接口断言、conftest fixture、
  BaseRequest、run_case、VariableStore
---

# API自动化测试框架 — AI编码参考规范

## 框架概述

基于 pytest + requests + YAML 的5层分层API自动化测试框架。AI在编写测试用例时，必须严格遵循以下层级调用约定和编码模式。

### 层级依赖关系

```
yaml/*.py(测试数据) → test_*.py(用例) → common/(公共工具) → api_test_framework/(核心引擎)
                                           ↑
                                      conftest.py(fixture配置)
```

**调用规则**：
- 用例层 → 调用 `common/` 的方法（不直接调用 `api_test_framework/`）
- `common/requests_util.py` 是手写用例的**唯一入口**
- `api_test_framework/runner.py` 仅用于纯YAML驱动模式

---

## 第1层：核心引擎 (`api_test_framework/`) — 方法速查

> ⚠️ 用例代码通常不直接导入此层。此层的类通过 `common/` 间接使用，或仅在框架驱动模式(`run_case`)下直接调用。

| 类/函数 | 文件 | 用途 | 调用场景 |
|---------|------|------|---------|
| `BaseRequest` | client.py | 轻量HTTP客户端 | 框架内部、生成代码 |
| `ApiTestConfig` | config.py | 配置dataclass | pytest_plugin加载 |
| `load_config()` | config.py | YAML+环境变量→配置对象 | 启动时 |
| `VariableStore` | data.py | 内存变量存储+`{{var}}`解析 | 框架驱动模式 |
| `read_yaml()` / `write_yaml()` | data.py | YAML/JSON读写 | 任何地方 |
| `assert_response()` | assertions.py | 声明式断言引擎 | `run_case()` 内部 |
| `extract_json_path()` | assertions.py | JSONPath提取 `$.a.b[0]` | 断言/提取 |
| `ApiCase` | schema.py | 用例数据模型(dataclass) | 框架驱动模式 |
| `normalize_case()` | schema.py | dict→ApiCase转换 | `run_case()` 入口 |
| `run_case()` | runner.py | 完整用例执行生命周期 | 纯YAML驱动模式 |

---

## 第2层：公共工具 (`common/`) — ⭐ 用例代码主要调用此层

### 2.1 `BaseRequest` — 增强版请求类（手写用例首选）

**文件**: `common/requests_util.py`
**导入**: `from common.requests_util import BaseRequest`

#### 构造与发送

```python
# 创建实例（默认debug=True）
http = BaseRequest()              # 默认超时30s，开启日志
http = BaseRequest(debug=False)   # 关闭日志

# 发送请求 — 核心方法
response = http.send_request(
    method="post",                # str: get/post/put/delete/patch
    url="https://...",            # str: 完整URL或相对路径
    params={},                    # dict: URL查询参数（GET/query风格）
    json={},                      # dict: JSON请求体
    data={},                      # dict: 表单请求体
    headers={},                   # dict: 请求头
    files={},                     # dict: 文件上传
    timeout=30,                   # float: 超时秒数
    case_name="登录测试",          # str: 用例名称（用于日志标识）
    log_level="full"             # str: "full"|"simple"|"none"
)
# 返回: requests.Response 对象
```

#### log_level 三种模式

| 模式 | 请求日志 | 响应日志 | 适用场景 |
|------|---------|---------|---------|
| `"full"` | 完整headers/body | 完整JSON body | 调试问题 |
| `"simple"` | 只显示params/data | 只显示code+msg | **日常运行（推荐）** |
| `"none"` | 无 | 无 | 批量性能测试 |

#### 敏感信息脱敏（自动处理）

以下关键字段自动隐藏：`authorization`, `cookie`, `token`, `password`, `secret`, `key`

#### 典型调用模式

```python
# 模式A：GET带查询参数
res = BaseRequest().send_request(
    method="get",
    url=f"{base_url}/api/users",
    params={"page": 1, "size": 10},
    headers=auth_headers,
    case_name="获取用户列表",
    log_level="simple"
)

# 模式B：POST JSON body
res = BaseRequest().send_request(
    method="post",
    url=f"{base_url}/api/users",
    json={"name": "test", "role": "admin"},
    headers=auth_headers,
    case_name="创建用户",
    log_level="simple"
)

# 模式C：POST query参数风格（你的项目常用）
res = BaseRequest().send_request(
    method="post",
    url=f"{base_url}/api/login",
    params={"account": "admin", "password": "xxx"},
    case_name="登录",
    log_level="simple"
)
```

---

### 2.2 YAML工具

**文件**: `common/yaml_util.py`
**导入**: `from common.yaml_util import read_yaml, write_yaml, clear_yaml`

```python
# 读取YAML → 返回dict/list
data = read_yaml("./yaml/test_login.yaml")
# data = {"login_cases": [{"name": "...", ...}, ...]}

# 写入extract.yaml（追加模式，跨用例持久化变量）
write_yaml({"user_id": 123})

# 清空extract.yaml（每轮测试前调用）
clear_yaml()
```

---

### 2.3 IP获取

**文件**: `common/ipconfig.py`
**导入**: `from common.ipconfig import get_local_ips`

```python
ips = get_local_ips()
# 返回: ["192.168.1.100"]  排除127.x.x.x，默认取第一个
```

---

### 2.4 公共数据

**文件**: `common/common_data.py`
**导入**: `from common.common_data import get_current_datetime`

```python
ts = get_current_datetime()
# 返回: "20260427133000"  用于生成唯一测试数据名称
```

### 2.5 Allure断言封装（推荐）

**文件**: `common/allure_assert_util.py`  
**导入**: `from common.allure_assert_util import assert_api_result`

```python
assert_api_result(
    case_name=case["name"],
    expected_code=case["expected"]["code"],
    expected_msg=case["expected"]["error_msg"],
    actual_code=code,
    actual_msg=msg,
    biz_context={"请求参数": payload}
)
```

**用途**:
- 统一成功/失败分支断言，避免每个用例重复写 if/else
- 成功时自动附加 Allure 文本附件
- 失败时自动附加结构化 JSON 上下文附件（含业务上下文）

**biz_context 建议字段**:
- `请求参数`: 用例关键请求字段（建议脱敏）
- `关键中间变量`: 如动态 ID、验证码、提取值

---

### 2.6 日志工具

**文件**: `common/logger_util.py`  
**导入**: `from common.logger_util import sep, key, print_request, print_response, print_result`

```python
sep(" 测试用例: 登录失败 ")
key("captchaId", captcha_id)
print_request("POST", url, params=payload, headers=headers)
print_response(res)
print_result(True, "验证通过!")
```

**约定**:
- 统一使用该工具输出关键日志，避免各用例日志风格不一致
- 敏感字段（password/token/authorization 等）应做脱敏处理

---

### 2.7 验证码识别工具

**文件**: `common/captcha_util.py`  
**导入**: `from common.captcha_util import CaptchaRecognizer`

```python
ocr = CaptchaRecognizer()
captcha_text = ocr.recognize_from_response(resp)
```

**建议**:
- 验证码登录场景通过 fixture（如 `auth_token`）统一处理，不在每个测试重复识别逻辑
- 当识别失败导致登录失败时，使用重试机制而非直接失败

---

## 第3层：`conftest.py` 编码规范

### 必须提供的 Fixture

| Fixture名 | 作用域 | 用途 | 是否必须实现 |
|-----------|--------|------|-------------|
| `base_url` | session | 动态基础URL | ✅ 必须 |
| `auth_token` / `access_token` | session | 登录认证凭据 | ✅ 必须（按实际认证方式命名） |
| `auth_headers` / `api_headers` | session | 认证请求头字典 | ✅ 必须 |
| 业务前置数据(groupid/deviceid等) | session | 预创建的资源ID | ⚠️ 按需 |
| `device_manager` | session | GlobalData全局容器 | ✅ 推荐 |
| `clear_data_per_session` | session autouse | 清空extract.yaml | ✅ 必须（直接复制） |
| `log_all_requests_and_responses` | function autouse | Allure记录请求响应 | ✅ 必须（直接复制） |
| `pytest_runtest_makereport` | hookimpl | 测试结果日志 | ✅ 必须（直接复制） |

### 推荐通用能力（可直接复用）

- `generate_captcha_id()`：统一生成验证码 `captchaId`（时间戳 + 随机数）
- `auth_token`：验证码识别 + 登录获取 token（失败自动重试）
- `auth_headers`：统一返回鉴权头，如 `{"Authorization": token}`
- `pytest_runtest_makereport`：失败时自动附加请求/响应/错误/断言详情到 Allure
- `clear_data_per_session`：会话级测试前清理、测试后收尾

### conftest.py 定制清单（改这3处就行）

```python
# 【位置1】pytest_configure() — 改端口号
base_url = f"http://{ip}:9004"        # ← 你的服务端口

# 【位置2】auth_token fixture — 改登录接口
url = f"{base_url}/api/xxx/login"     # ← 你的登录路径
payload = {"account": "admin", "password": "xxx"}  # ← 你的凭据

# 【位置3】auth_headers fixture — 改header格式
return {"Authorization": f"{token}"}  # 可能是Bearer/Token/其他格式
```

### 命令行参数支持

```bash
pytest --host=192.168.1.100    # 手动指定目标主机IP
```

---

## 第4层：用例编码模式

### 模式A：简单无状态接口（如登录、查询）

**适用**: 接口之间无依赖，每个用例独立运行。

**文件结构**: 一个 `test_xxx.py` + 一个 `yaml/test_xxx.yaml`

**Python模板**:
```python
import jsonpath
import pytest
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml

class Test_xxxAPI:
    test_data = read_yaml("./yaml/test_xxx.yaml")["xxx_cases"]

    @pytest.mark.parametrize("case", test_data)
    def test_xxx(self, base_url, case):
        url = f"{base_url}/your/api/path"
        payload = { /* 从case构建 */ }
        
        res = BaseRequest().send_request(
            method="post", url=url, params=payload,
            case_name=case["name"], log_level="simple"
        )
        
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        if code == 0:
            assert code == case["expected"]["code"]
            # 成功时的额外断言...
        else:
            assert code == case["expected"]["code"]
            assert case["expected"]["error_msg"] == res.json()["msg"]
```

### 模式B：有状态CRUD接口（增删改查有关联）

**适用**: 后面的接口依赖前面接口返回的ID。

**关键机制**:
- **类变量**共享ID: `Test_xxxAPI.created_id = ...`
- **关键字匹配**动态修改数据: `if "xxx成功" in case["name"]: case["field"] = dynamic_value`
- **fixture注入**前置数据: def test_xxx(self, ..., groupid1):

```python
import jsonpath
import pytest
from common.common_data import get_current_datetime
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml

class Test_crudAPI:
    created_id = None           # ← 类变量，跨方法共享
    
    test_data = read_yaml("./yaml/test_xxx.yaml")["cases"]

    # CREATE
    @pytest.mark.parametrize("case", test_data[:N])
    def test_create(self, base_url, auth_headers, case):
        if case.get("name") == "创建成功":
            case["name_field"] = f"测试_{get_current_datetime()}"  # 保证唯一性
        
        res = BaseRequest().send_request(method="post", url=..., ...)
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        if code == 0:
            Test_crudAPI.created_id = jsonpath.JSONPath("$.data.id").parse(res.json())[0]
            assert code == case["expected"]["code"]
        else:
            assert code == case["expected"]["code"]
            assert case["expected"]["error_msg"] == res.json()["msg"]

    # UPDATE (依赖CREATE的结果)
    @pytest.mark.parametrize("case", test_data[N:M])
    def test_update(self, base_url, auth_headers, case):
        if "编辑成功" in case.get("name", ""):
            case["id"] = Test_crudAPI.created_id   # ← 注入上一步的ID
        
        res = BaseRequest().send_request(method="put", url=f".../{case['id']}", ...)
        # 断言同上...

    # DELETE (可能需要conftest的前置fixture)
    @pytest.mark.parametrize("case", test_data[M:])
    def test_delete(self, base_url, auth_headers, case, groupid1):  # ← 注入fixture
        if "删除空资源" in case.get("name", ""):
            case["id"] = Test_crudAPI.created_id
        elif "删除非空资源" in case.get("name", ""):
            case["id"] = groupid1                        # ← 用fixture的数据
        
        res = BaseRequest().send_request(method="delete", url=f".../{case['id']}", ...)
        # 断言同上...
```

### 模式C：框架驱动模式（纯YAML + run_case）

**适用**: 标准CRUD接口，无需复杂条件分支。

```python
import pytest
from api_test_framework.runner import run_case
from api_test_framework.data import read_yaml, VariableStore
from api_test_framework.schema import ApiCase

store = VariableStore()

@pytest.mark.parametrize("raw_case", read_yaml("./yaml/test_xxx.yaml")["cases"])
def test_xxx(raw_case, base_url, auth_headers):
    run_case(case=ApiCase.from_dict(raw_case),
              base_url=base_url, headers=auth_headers, variables=store)
```

### 断言标准模式

```python
# 推荐：先提取核心断言字段
code = jsonpath.JSONPath("$.code").parse(res.json())[0]
msg = jsonpath.JSONPath("$.msg").parse(res.json())[0]

# 推荐：调用公共断言工具，避免重复写失败上下文与Allure附件
assert_api_result(
    case_name=case["name"],
    expected_code=case["expected"]["code"],
    expected_msg=case["expected"]["error_msg"],
    actual_code=code,
    actual_msg=msg,
    biz_context={"请求参数": payload}
)
```

### JSONPath 提取常用写法

```python
import jsonpath

# 提取单个值
token = jsonpath.JSONPath("$.data.token").parse(res.json())[0]
user_id = jsonpath.JSONPath("$.data.userList[0].id").parse(res.json())[0]

# 提取列表
addr_list = jsonpath.JSONPath("$.data.addr").parse(res.json())
# addr_list可能是单个值或列表，统一处理:
if addr_list:
    result_ids = addr_list if isinstance(addr_list, list) else [addr_list]
```

---

## 第5层：YAML 数据文件格式规范

### 标准结构

```yaml
# yaml/test_xxx.yaml
xxx_cases:                    # ← 顶层key，与read_yaml()中的键对应
  - name: "用例名称（语义化，用于关键字匹配）"
    field1: "value1"           # ← 直接做请求数据的字段
    field2: "value2"
    expected:                  # ← 预期结果（必填）
      code: 0                  # 0=成功, 其他=业务错误码
      error_msg: "错误信息"    # 仅负向用例填

  - name: "负向用例—参数为空"
    field1: ""                 # 空值测试
    expected:
      code: 1001
      error_msg: "xxx不能为空"
```

### 设计规则

| 规则 | 说明 |
|------|------|
| `name` 必须语义化 | Python中用 `case["name"]` 做关键词匹配来走不同逻辑分支 |
| `expected.code` 必填 | 作为主断言目标 |
| 动态字段留空或占位 | 在Python中通过关键字匹配后用 `get_current_datetime()` 或注入ID覆盖 |
| 正向用例在前，负向在后 | Python中用切片 `test_data[:N]` 分组参数化 |

---

## AI编写用例的工作流

当用户要求"帮我写XX接口的测试用例"时，按以下步骤执行：

### Step 1: 收集接口信息
- 接口URL路径
- HTTP方法(GET/POST/PUT/DELETE)
- 请求参数（query params or JSON body）
- 认证方式（是否需要token/header）
- 预期的正向返回和各类错误返回

### Step 2: 判断使用哪种模式
- 无状态接口 → **模式A**
- CRUD有关联 → **模式B**
- 简单标准CRUD → **模式C**

### Step 3: 生成两个文件
1. `yaml/test_xxx.yaml` — 测试数据
2. `testcases/test_xxx.py` — 测试逻辑

### Step 4: 检查清单
- [ ] 导入是否正确（`BaseRequest` from `common.requests_util`）
- [ ] `read_yaml` 路径是否正确（`./yaml/test_xxx.yaml`）
- [ ] `@pytest.mark.parametrize` 数据源是否匹配YAML顶层key
- [ ] fixture注入是否完整（`base_url`, `auth_headers`, 业务fixture）
- [ ] 断言是否优先使用 `assert_api_result(...)`
- [ ] 关键字匹配逻辑是否覆盖了所有case name
- [ ] 有动态数据的场景是否用了 `get_current_datetime()`
- [ ] `case_name` 和 `log_level` 参数是否传入 `send_request`

---

## 项目文件结构（新项目骨架）

```
project-root/
├── api_test_framework/     # 核心引擎（100%不动）
├── common/                 # 公共工具（删CoordinateConverter.py）
│   ├── requests_util.py    # ⭐ 主要调用入口
│   ├── allure_assert_util.py # ⭐ 统一断言+Allure附件
│   ├── logger_util.py
│   ├── captcha_util.py
│   ├── yaml_util.py
│   ├── ipconfig.py
│   └── common_data.py
├── conftest.py             # ⭐ 唯一需要定制的配置文件
├── pytest.ini
├── pyproject.toml
├── run.py                  # 一键运行入口
├── extract.yaml            # 空文件，运行时变量存储
├── testcases/              # 测试用例（你来写）
│   └── test_*.py
└── yaml/                   # 测试数据（你来写）
    └── test_*.yaml
```

---

## 详细方法签名与源码

> 各层完整的方法签名、参数说明、源码实现见 `references/methods-reference.md`
> 代码模板文件见 `assets/templates/` 目录（可直接复制到新项目使用）
