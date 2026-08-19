# glht 入库记录清理统一化 Implementation Plan

> **For agentic workers:** 本计划承接对 `common/cleanup/glht.py` 的深入分析（见对话记录）：实测确认现有「按日期模糊猜格式」的清理逻辑对 `generate_rescue_sn()` 生成的救援棒 SN（月+日+时+分+秒+盐，不含年份）完全失效，只对 `terminal_type_enum_cases` 生成的 SN（含 `YYYYMMDD` 前缀）有效——这是方法论层面的缺陷，不是某个日期格式写错。整改方向：抛弃"猜格式"，回到「谁造数谁登记」纪律，把 glht 入库并入统一 `registry`，做成新的 tier 400/410。
>
> **已拍板（本次会话）：**
> - tier 归属：新增 tier 400（外部系统，与 jkpt 内部 100/200/300 无依赖关系）
> - `ENABLE_GLHT_CLEANUP` 默认值：`false` → `true`
> - **历史遗留的 1321 条存量入库记录本计划不处理**（明确排除，之前实测确认存在但未拍板是否清；本计划只保证"以后新造的都能精确清掉"，存量清理留待后续单独决策，不要顺手写脚本清掉）

**Goal:** 把 `glht.py` 从「按 session 起始日模糊搜索、盲删全部匹配项」改造成「入库成功即登记 sn → session 末按 sn 精确查、批量删」，格式无关，彻底移除对 SN 编码规则的依赖；4 个入库点（`rescue_sat_terminal`/`_provision_b_rescue_stick`/`test_intercom_group_controller.py::provision_rescue_stick`/`TestTm07AddTerminalByEnum`）接入登记；废弃 `conftest.py` 里独立的 glht fixture 链路，并入主 `cleanup_test_data` 统一报告。

**Architecture:** 新增一种清理形状——「逐项登记 + 集中批量收尾」（下称模板 D，模板 A/B/C 见 `cleanup-framework.md`）：每个 sn 各开一个 `glht_inventory_{sn}`（tier 400）domain，`cleaner` 只做「精确查询定位 id」，不立即删除，而是把 id 塞进模块级 `_pending_ids`；另挂一个全局唯一的 `glht_inventory_flush`（tier 410，通过 `register_cleanup_once` 保证只挂一次、且 tier 更大保证在所有 400 之后执行）负责真正的批量 `DELETE`。这样既保留了逐项登记的可诊断性（report 里能看到每个 sn 的定位结果），又不会把批量删除拆成 N 次网络请求。

`glht.py` 从"半独立"（架构决策 C：自带登录态，但仍需 conftest 提供 `glht_token`/`glht_base_url` fixture）变成完全自包含域模块：自读 `GLHT_BASE_URL`/`GLHT_ACCOUNT`/`GLHT_PASSWORD`/`ENABLE_GLHT_CLEANUP` 环境变量，惰性、进程内缓存登录 token，不依赖任何 conftest fixture——这也是当前 `unpaid_order.py`/`intercom_group.py`/`terminal.py`/`group.py` 已经遵循的自包含形状，glht 之前是唯一例外，本次一并拉齐。

**Tech Stack:** Python 3 + pytest；`common/cleanup/` 子包保持零 pytest/requests 依赖仅限 `registry.py`（本次不改 `registry.py` 的函数，只改 docstring）。

## Global Constraints

- `registry.py` 本次**不新增函数**（`register_cleanup_once`/`unregister_cleanup` 已够用），只改模块顶部 docstring 的 tier 语义说明
- `glht.py` 对外新增的公开入口是 `register(sn)`（单参数），包级门面 `register_glht_inventory = glht.register`——4 个调用点一行接入，不改造用方法签名
- 行为变更（需在 CHANGELOG 显式标注 Breaking）：glht 清理并入 `run_session_cleanup` 后，会**额外**受 `ENABLE_AUTO_CLEANUP` 总闸控制——之前 `ENABLE_AUTO_CLEANUP=false` 时 glht 清理仍独立运行，迁移后 `ENABLE_AUTO_CLEANUP=false` 会连带跳过 glht。`ENABLE_GLHT_CLEANUP` 子开关语义不变（关闭时 `cleaner`/`flush_cleaner` 直接返回"跳过"，零网络开销）
- 不处理历史遗留的 1321 条存量数据——本计划的 `cleaner` 只按"本次 session 实际登记过的 sn"精确查删，不做任何全表扫描/批量猜测
- 按内容定位改 `conftest.py`，不按行号（历史教训：删除会导致后续行号整体偏移）
- 每个任务改完至少跑一次语法自检（`python -c "import ..."`），核心改动（Task 3）跑一次真实回归

---

## 0. 决策矩阵新增一格（模板 D）

在 `cleanup-framework.md` 已有的 2×2 矩阵基础上补一个正交问题：

> **cleaner 要不要把"定位"和"执行"拆成两步？** ——如果域的删除动作本身支持批量接口（像 glht 的 `DELETE /api/admin/inventory` 一次可传多个 id），但登记时机是逐项、动态的（每次入库成功才知道一个新 sn），模板 B（逐项 domain，cleaner 里直接单项调 HTTP）会把 1 次批量接口拆成 N 次单项请求，浪费；模板 C（共享 domain + 累积列表）又要求所有实例走同一个 `register()` 才能攒进同一个列表，登记语义上不如"每个实例一个 domain"直观、不好单独 `unregister`。
>
> **模板 D = 逐项登记（沿用模板 B 的 domain 命名/去重/可诊断性）+ 集中批量收尾（沿用模板 C 的"一次批量请求"效率）**：每个实例仍然各开一个 `f"{prefix}_{id}"` domain（tier N），`cleaner(ctx, id, **flags)` 只做"定位"（查询/校验，不做实际删除动作），把结果写入模块级累积容器；额外用 `register_cleanup_once` 挂一个**全局唯一**、**tier = N+10**（保证在所有逐项 domain 之后执行）的 `flush_cleaner`，读取累积容器，一次批量执行。
>
> 适用场景：批量接口存在 + 登记时机动态 + 想保留逐项可诊断性，三者都要时选模板 D；只要三者有一个不成立，仍然选 A/B/C。

---

## 1. Task 1：`common/cleanup/glht.py` 整份重写为模板 D

**Files:**
- Modify: `jkpt_api_test/common/cleanup/glht.py`

**Interfaces:**
- Produces：`register(sn) -> None`（新增，供 4 个入库点调用）、`cleaner(ctx, sn, **flags) -> str`（签名变化：payload 从 `None` 变成单个 sn，仅 registry 内部调用）、`flush_cleaner(ctx, _payload, **flags) -> str`（新增）
- Consumes：`registry.register_cleanup_once`
- 废弃：`cleanup_inventory(glht_token, glht_base_url, date_str)`（旧函数整体删除，无其他调用点——已检索确认仅 `conftest.py` 引用）

**Step 1：整份重写**

```python
# common/cleanup/glht.py
# tier 400/410（外部系统，与 jkpt 内部 tier 100/200/300 无依赖关系，顺序不敏感）：
# glht 管理员系统入库记录清理。模板 D（逐项登记 + 集中批量收尾，详见
# references/cleanup-framework.md）：cleaner 只按 sn 精确定位 id，不立即删；
# flush_cleaner 统一批量 DELETE，避免 N 次入库对应 N 次删除请求。
# 完全自包含：自读 GLHT_* 环境变量，登录态惰性缓存于进程内，不依赖任何
# conftest fixture（对齐 unpaid_order.py/intercom_group.py 的自包含形状）。
import hashlib
import os

from common.cleanup.registry import register_cleanup_once
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "glht_inventory"
_FLUSH_DOMAIN = "glht_inventory_flush"

GLHT_BASE_URL = os.getenv("GLHT_BASE_URL", "http://back.tdwt.admin.pg8.ink")
GLHT_ACCOUNT = os.getenv("GLHT_ACCOUNT", "admin")
GLHT_PASSWORD = os.getenv("GLHT_PASSWORD", "123abc!!")
ENABLE_GLHT_CLEANUP = os.getenv("ENABLE_GLHT_CLEANUP", "true").lower() == "true"

_pending_ids: list = []          # tier400 各 cleaner 只追加，tier410 flush 统一清空+批删
_token_cache = {"token": None}   # 进程内惰性缓存，避免每个 sn 各登录一次


def register(sn) -> None:
    """入库成功后登记（副作用落地即注册，纪律 1）；同 sn 天然去重。"""
    if sn is None:
        return
    s = str(sn).strip()
    if not s:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{s}", s, cleaner, tier=400)
    register_cleanup_once(_FLUSH_DOMAIN, None, flush_cleaner, tier=410)
    key("登记glht入库", s)


def _login() -> str:
    if _token_cache["token"]:
        return _token_cache["token"]
    pwd_md5 = hashlib.md5(GLHT_PASSWORD.encode()).hexdigest()
    resp = _http.send_request(
        method="post", url=f"{GLHT_BASE_URL}/api/admin/login",
        json={"account": GLHT_ACCOUNT, "password": pwd_md5},
        case_name="glht管理员登录", log_level="none",
    )
    data = parse_response_json(resp, context="glht管理员登录")
    if data.get("code") != 0:
        raise RuntimeError(f"glht 登录失败: code={data.get('code')}, msg={data.get('msg')}")
    token = data.get("data", {}).get("token")
    _token_cache["token"] = token
    key("glht token", f"{token[:20]}...")
    return token


def cleaner(ctx, sn, **flags) -> str:
    """registry 入口（tier400）：按 sn 精确查询定位 id，只登记待删，不在此处删除。"""
    if not ENABLE_GLHT_CLEANUP:
        return "跳过(ENABLE_GLHT_CLEANUP=false)"
    try:
        token = _login()
    except Exception as exc:
        return f"FAILED: {exc}"
    resp = _http.send_request(
        method="get", url=f"{GLHT_BASE_URL}/api/admin/inventory",
        params={
            "Authorization": token, "content": sn, "index": 0,
            "specifyTime": "false", "startTimeStr": "", "endTimeStr": "",
            "page": 1, "pageSize": 10,
        },
        case_name=f"glht查询入库记录 {sn}", log_level="none",
    )
    data = parse_response_json(resp, context="glht查询入库记录")
    if data.get("code") != 0:
        return f"FAILED: 查询 code={data.get('code')}"
    items = data.get("data", {}).get("items") or []
    # content 是模糊子串匹配，这里做一次精确 sn 比对防误命中（防御性）
    matched = [it["id"] for it in items if str(it.get("sn")) == sn and it.get("id")]
    if not matched:
        return "未找到(可能已被其它路径清过)"
    _pending_ids.extend(matched)
    return f"已定位 {len(matched)} 条，待批量删除"


def flush_cleaner(ctx, _payload, **flags) -> str:
    """registry 入口（tier410，全局唯一，晚于所有 glht_inventory_<sn>）：批量执行删除。"""
    if not ENABLE_GLHT_CLEANUP:
        _pending_ids.clear()
        return "跳过(ENABLE_GLHT_CLEANUP=false)"
    if not _pending_ids:
        return "无需删除"
    try:
        token = _login()
    except Exception as exc:
        return f"FAILED: {exc}"
    ids = list(dict.fromkeys(_pending_ids))  # 去重保序
    _pending_ids.clear()
    deleted_total = 0
    for i in range(0, len(ids), 100):  # 单次删除量上限未知，按 100 分块保守处理
        chunk = ids[i:i + 100]
        resp = _http.send_request(
            method="delete", url=f"{GLHT_BASE_URL}/api/admin/inventory",
            params={"Authorization": token}, json={"ids": ",".join(chunk)},
            case_name="glht批量删除入库记录", log_level="none",
        )
        data = parse_response_json(resp, context="glht删除入库记录")
        if data.get("code") == 0:
            deleted_total += len(chunk)
        else:
            key("glht删除失败", f"code={data.get('code')}, msg={data.get('msg')}")
    return f"删除 {deleted_total}/{len(ids)} 条"
```

**Step 2：语法自检**

```bash
python -c "from common.cleanup.glht import register, cleaner, flush_cleaner; print('ok')"
```

**Step 3：Commit**（本任务不单独提交，跟 Task 2/3 一起提交，独立提交没有可运行的验证点）

---

## 2. Task 2：`common/cleanup/__init__.py` 加包级入口 + 更新域清单注释

**Files:**
- Modify: `jkpt_api_test/common/cleanup/__init__.py`

**Interfaces:**
- Produces：`register_glht_inventory = glht.register`（供 4 个入库点导入）

**Step 1：域清单注释更新**（原第 9-15 行）

```python
# 域清单（tier 升序 = 清理顺序）：
#   100  rescue_chat    关求救群（含双路线降级）
#   100  unpaid_order   收待支付订单（cancel→delete）；登记入口 = register_unpaid_order_no
#   100  intercom_group 收对讲群（close→delete）；登记入口 = register_intercom_group
#   200  terminal       删设备（按分组聚合）
#   300  group          删三级分组（倒序）
#   400  glht(cleaner)  查 glht 入库记录 id（按 sn 精确定位，不在此层删除）
#   410  glht(flush)    批量删除 400 层定位到的 id；登记入口 = register_glht_inventory
```

**Step 2：`register_unpaid_order_no`/`register_intercom_group` 之后加**

```python
# glht 入库登记包级入口：mock-in-storage 成功后调用（副作用落地即注册，tier 400/410）。
register_glht_inventory = glht.register
```

**Step 3：`__all__` 追加 `"register_glht_inventory"`**

**Step 4：语法自检**

```bash
python -c "from common.cleanup import register_glht_inventory; print('ok')"
```

**Step 5：Commit**（同 Task 1，与 Task 3 一起提交）

---

## 3. Task 3：4 个入库点接入登记 + `conftest.py` 拆掉旧 glht 独立链路

**Files:**
- Modify: `jkpt_api_test/conftest.py`
- Modify: `jkpt_api_test/testcases/test_intercom_group_controller.py`
- Modify: `jkpt_api_test/testcases/test_terminal_controller.py`

### Step 1：`conftest.py` — 顶部常量清理

原（第 47-55 行附近）：

```python
ENABLE_AUTO_CLEANUP = os.getenv("ENABLE_AUTO_CLEANUP", "true").lower() == "true"
ENABLE_GLHT_CLEANUP = os.getenv("ENABLE_GLHT_CLEANUP", "false").lower() == "true"

JKPT_ACCOUNT = os.getenv("JKPT_ACCOUNT", "user1752216001906")
JKPT_PASSWORD = os.getenv("JKPT_PASSWORD", "4f9cb165cd6249312e5804fcf9416c5e")
JKPT_ACCOUNT_B = os.getenv("JKPT_ACCOUNT_B", "user13128251672")
JKPT_PASSWORD_B = os.getenv("JKPT_PASSWORD_B", JKPT_PASSWORD)  # 同 A 的 MD5
GLHT_ACCOUNT = os.getenv("GLHT_ACCOUNT", "admin")
GLHT_PASSWORD = os.getenv("GLHT_PASSWORD", "123abc!!")
```

改为：

```python
ENABLE_AUTO_CLEANUP = os.getenv("ENABLE_AUTO_CLEANUP", "true").lower() == "true"

JKPT_ACCOUNT = os.getenv("JKPT_ACCOUNT", "user1752216001906")
JKPT_PASSWORD = os.getenv("JKPT_PASSWORD", "4f9cb165cd6249312e5804fcf9416c5e")
JKPT_ACCOUNT_B = os.getenv("JKPT_ACCOUNT_B", "user13128251672")
JKPT_PASSWORD_B = os.getenv("JKPT_PASSWORD_B", JKPT_PASSWORD)  # 同 A 的 MD5
# GLHT_* 常量与 ENABLE_GLHT_CLEANUP 已挪进 common/cleanup/glht.py（域模块自读环境变量）
```

### Step 2：`conftest.py` — `pytest_configure` 删除已无消费者的 `pytest_session_start_day`

原：

```python
def pytest_configure(config):
    config.base_url = os.getenv("JKPT_BASE_URL", "http://back.tdwtv2.pg8.ink")
    global pytest_session_start_day
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    pytest_session_start_day = _dt.now(_tz(_td(hours=8))).strftime("%Y%m%d")
    config.accept_language = "zh-CN"
```

改为：

```python
def pytest_configure(config):
    config.base_url = os.getenv("JKPT_BASE_URL", "http://back.tdwtv2.pg8.ink")
    config.accept_language = "zh-CN"
```

（`pytest_session_start_day` 唯一消费者是即将删除的旧 `glht_cleanup_test_data`，已检索确认无其他引用。）

### Step 3：`conftest.py` — `rescue_sat_terminal` 接入登记

原（`# 副作用落地即注册（纪律 1）` 段落）：

```python
    # 副作用落地即注册（纪律 1）：入库成功立刻登记——
    # 即便下一步「添加设备」失败，session 末也有据可收（堵 glht 入库记录泄漏）。
    from common.cleanup import register_cleanup, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    pytestconfig.stash.setdefault("rescue_terminal_sns", []).append(sn)
```

改为：

```python
    # 副作用落地即注册（纪律 1）：入库成功立刻登记——
    # 即便下一步「添加设备」失败，session 末也有据可收（真正堵住 glht 入库记录泄漏，
    # 不再依赖"日期猜格式"）。
    from common.cleanup import register_cleanup, register_glht_inventory, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    register_glht_inventory(sn)
    pytestconfig.stash.setdefault("rescue_terminal_sns", []).append(sn)
```

> 定位提示：此段紧跟在 `key("入库", f"sn={sn} type=TT_RESCUE_STICK")` 之后，`_provision_b_rescue_stick` 里有一段几乎相同的文字（见 Step 4），改的时候要连同各自上一行的 `key(...)` 一起框进匹配范围，避免两处文本冲突导致替换工具报"不唯一"。

### Step 4：`conftest.py` — `_provision_b_rescue_stick` 接入登记

原：

```python
    json_data = parse_response_json(r, context=f"{label}入库")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"{label}入库失败: code={code}, msg={msg[0] if msg else '未知'}")
    key(f"{label}入库", f"sn={sn} type=TT_RESCUE_STICK")

    from common.cleanup import register_cleanup, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    pytestconfig.stash.setdefault("rescue_terminal_sns", []).append(sn)
```

改为：

```python
    json_data = parse_response_json(r, context=f"{label}入库")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        msg = _jsonpath_parse(json_data, "$.msg")
        pytest.fail(f"{label}入库失败: code={code}, msg={msg[0] if msg else '未知'}")
    key(f"{label}入库", f"sn={sn} type=TT_RESCUE_STICK")

    from common.cleanup import register_cleanup, register_glht_inventory, rescue_chat as _rc
    register_cleanup(f"rescue_chat_{sn}", [sn], _rc.cleaner, tier=100)
    register_glht_inventory(sn)
    pytestconfig.stash.setdefault("rescue_terminal_sns", []).append(sn)
```

（此函数是 `rescue_sat_terminal_b`/`b2`/`b3` 三个 fixture 的共用实现，改一处即覆盖三个 B 棒。）

### Step 5：`conftest.py` — `cleanup_test_data` 文档注释补一行

原：

```python
    注册来源（副作用落地即注册）：
      group_fixture → groups(tier300) + terminals(tier200)  # A token
      rescue_sat_terminal → rescue_chat_{sn}(tier100，入库成功即注册)
      rescue_sat_terminal_b → b_terminals(200) + b_groups(300)（payload 自带 B headers）
      用例 buy → unpaid_orders(tier100，经包级入口 register_unpaid_order_no)
    执行序由 registry tier 保证：群/订单(100) → 设备(200) → 分组(300)。
```

改为：

```python
    注册来源（副作用落地即注册）：
      group_fixture → groups(tier300) + terminals(tier200)  # A token
      rescue_sat_terminal → rescue_chat_{sn}(tier100，入库成功即注册)
      rescue_sat_terminal_b → b_terminals(200) + b_groups(300)（payload 自带 B headers）
      用例 buy → unpaid_orders(tier100，经包级入口 register_unpaid_order_no)
      4 处 mock-in-storage 入库点 → glht_inventory_{sn}(tier400) + glht_inventory_flush(tier410，
        经包级入口 register_glht_inventory，按 sn 精确查删，格式无关)
    执行序由 registry tier 保证：群/订单(100) → 设备(200) → 分组(300) → 外部系统(400/410)。
```

### Step 6：`conftest.py` — 删除整个旧 glht 独立链路

删除从 `# ==================== glht 管理员系统清理（独立运转） ====================` 起，到 `glht_cleanup_test_data` 函数体最后一行 `sep(" 🎉 glht 清理完成 ")` 止的整段（含 `GLHT_BASE_URL_DEFAULT` 常量、`glht_base_url`/`glht_token`/`glht_cleanup_test_data` 三个 fixture），原内容：

```python
# ==================== glht 管理员系统清理（独立运转） ====================
GLHT_BASE_URL_DEFAULT = "http://back.tdwt.admin.pg8.ink"


@pytest.fixture(scope="session")
def glht_base_url():
    """glht 管理员系统 base URL"""
    return os.environ.get("GLHT_BASE_URL", GLHT_BASE_URL_DEFAULT)


@pytest.fixture(scope="session")
def glht_token(glht_base_url):
    """glht 管理员系统登录，获取 glht token"""
    sep(" 🔐 glht 管理员登录 ")
    password_md5 = hashlib.md5(GLHT_PASSWORD.encode()).hexdigest()
    resp = http.send_request(
        method="post",
        url=f"{glht_base_url}/api/admin/login",
        json={"account": GLHT_ACCOUNT, "password": password_md5},
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
def glht_cleanup_test_data(request):
    """glht 入库记录清理。默认关闭；ENABLE_GLHT_CLEANUP=true 时才登录并清理。"""
    from datetime import datetime, timezone, timedelta

    if not ENABLE_GLHT_CLEANUP:
        yield
        return

    glht_token = request.getfixturevalue("glht_token")
    glht_base_url = request.getfixturevalue("glht_base_url")
    yield

    sep(" 🧹 glht 入库记录清理 ")
    # 日期口径：session 起始日（堵跨午夜漏清；迁移时顺带修复）
    start_day = pytest_session_start_day
    try:
        from common.cleanup.glht import cleanup_inventory
        deleted = cleanup_inventory(glht_token, glht_base_url, start_day)
        key("glht清理结果", f"删除 {deleted} 条入库记录")
    except Exception as e:
        key("glht清理异常", str(e))

    sep(" 🎉 glht 清理完成 ")
```

直接删除，不保留替代代码（glht 清理现在完全由 `common/cleanup/glht.py` + 主 `cleanup_test_data` 调度承担）。

### Step 7：`test_intercom_group_controller.py` — `provision_rescue_stick` 接入登记

顶部 import（原第 13 行）：

```python
from common.cleanup import register_intercom_group, intercom_group, register_cleanup, rescue_chat
```

改为：

```python
from common.cleanup import (
    register_intercom_group,
    intercom_group,
    register_cleanup,
    register_glht_inventory,
    rescue_chat,
)
```

方法体（`provision_rescue_stick` 内）原：

```python
        data = r.json()
        if _jp_first(data, "$.code") != 0:
            raise AssertionError(f"满员造棒入库失败: {data}")
        register_cleanup(f"rescue_chat_{sn}", [sn], rescue_chat.cleaner, tier=100)
```

改为：

```python
        data = r.json()
        if _jp_first(data, "$.code") != 0:
            raise AssertionError(f"满员造棒入库失败: {data}")
        register_cleanup(f"rescue_chat_{sn}", [sn], rescue_chat.cleaner, tier=100)
        register_glht_inventory(sn)
```

### Step 8：`test_terminal_controller.py` — `TestTm07AddTerminalByEnum` 接入登记

顶部 import 区新增一行（放在现有 `from common.logger_util import ...` 之后）：

```python
from common.cleanup import register_glht_inventory
```

循环体内原：

```python
            storage_code = _jsonpath_parse(storage_json, "$.code")[0]
            if storage_code != 0:
                storage_msg = _jsonpath_parse(storage_json, "$.msg")[0]
                pytest.fail(
                    f"入库失败 [{case['terminalType']} SN={case['sn']}]: "
                    f"code={storage_code}, msg={storage_msg}"
                )

            sep(f" 添加: {case['terminalType']} SN={case['sn']}")
```

改为：

```python
            storage_code = _jsonpath_parse(storage_json, "$.code")[0]
            if storage_code != 0:
                storage_msg = _jsonpath_parse(storage_json, "$.msg")[0]
                pytest.fail(
                    f"入库失败 [{case['terminalType']} SN={case['sn']}]: "
                    f"code={storage_code}, msg={storage_msg}"
                )
            register_glht_inventory(case["sn"])

            sep(f" 添加: {case['terminalType']} SN={case['sn']}")
```

**Step 9：语法自检**

```bash
python -c "import ast; ast.parse(open('conftest.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('testcases/test_intercom_group_controller.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('testcases/test_terminal_controller.py', encoding='utf-8').read())"
```

**Step 10：Commit**

```bash
git add jkpt_api_test/common/cleanup/glht.py jkpt_api_test/common/cleanup/__init__.py jkpt_api_test/conftest.py jkpt_api_test/testcases/test_intercom_group_controller.py jkpt_api_test/testcases/test_terminal_controller.py
git commit -m "fix(cleanup): glht 入库记录改为精确按 sn 登记查删，替换失效的日期猜格式方案"
```

---

## 4. Task 4：文档同步——`registry.py` tier 注释 + `cleanup-framework.md` 模板 D + `conftest-jkpt.md` + `CHANGELOG.md`

**Files:**
- Modify: `jkpt_api_test/common/cleanup/registry.py`（仅 docstring）
- Modify: `skills/api-test-framework/references/cleanup-framework.md`
- Modify: `skills/api-test-framework/references/conftest-jkpt.md`
- Modify: `skills/api-test-framework/CHANGELOG.md`

**Step 1：`registry.py` 模块顶部纪律 2 更新**

原：

```python
#   2. tier 语义：100 会话级业务对象(群/订单) / 200 设备 / 300 组织(分组)。
#      新域挑层，不挑位置；同 tier 按注册序。
```

改为：

```python
#   2. tier 语义：100 会话级业务对象(群/订单) / 200 设备 / 300 组织(分组) /
#      400+ 外部系统（与 jkpt 内部 100-300 无依赖关系，顺序不敏感；如需"定位/执行"
#      两阶段，执行阶段用 N+10，保证晚于同组所有定位阶段，见 glht.py）。
#      新域挑层，不挑位置；同 tier 按注册序。
```

**Step 2：`cleanup-framework.md` 补模板 D**

在现有「模板 C」章节之后、「新增域 checklist」之前插入本计划 §0 的模板 D 说明全文（矩阵补充问题 + 适用场景），并在 checklist 里追加一条：

```
5. 删除动作是否支持批量接口，但登记时机又是动态逐项？两者都成立 → 模板 D（逐项定位 + 集中批量收尾，参考 `common/cleanup/glht.py`）。
```

同时把决策矩阵表格下方的"`rescue_chat_{sn}` 是技术债"提示段落之后，追加一句：`glht.py` 是模板 D 的范例实现（`register(sn)` / `cleaner` 定位 / `flush_cleaner` 批量执行）。

**Step 3：`conftest-jkpt.md` 同步**

- 第 20 行「会话清理」表格行：删除 `glht_cleanup_test_data（autouse，默认不登录 glht）` 这部分描述，改为说明 glht 清理已并入 `cleanup_test_data`（一行调度）
- 第 31-32 行 `ENABLE_GLHT_CLEANUP`/`GLHT_BASE_URL` 环境变量说明：更新默认值（`false`→`true`），补充"由 `common/cleanup/glht.py` 自读，非 conftest 常量"
- 第 69-71 行 mermaid 流程图里 `glht_token`/`glht_cleanup_test_data` 相关节点删除
- 第 93-95 行 fixture 表格：删除 `glht_base_url`/`glht_token`/`glht_cleanup_test_data` 三行
- 第 266-268 行 `glht_cleanup_test_data` 独立小节：整段删除，改为一句指向 `cleanup-framework.md` 模板 D 的说明

**Step 4：`CHANGELOG.md` 顶部追加**（在现有最新的 `[Unreleased] — 2026-08-19 清理框架统一化` 条目**之前**插入一条新的，作为最新记录）

```markdown
## [Unreleased] — 2026-08-19 glht 入库记录清理改为精确登记

### Fixed
- `glht.py` 原按"session 起始日模糊字符串"猜测 SN 编码规则来批量删除入库记录，对 `generate_rescue_sn()`（月+日+时+分+秒+盐，无年份）生成的救援棒 SN 完全失效，只对含 `YYYYMMDD` 前缀的 SN（`terminal_type_enum_cases`）有效——迁移为按 sn 精确登记查删后，与 SN 格式完全无关

### Added
- `common/cleanup/glht.py`：`register(sn)`（副作用落地即注册入口）、`flush_cleaner`（tier410，批量执行删除）
- `common/cleanup/__init__.py`：包级入口 `register_glht_inventory`
- `references/cleanup-framework.md`：新增模板 D（逐项登记 + 集中批量收尾），适用于"批量接口 + 动态登记 + 需要逐项可诊断性"三者并存的场景

### Changed
- `glht.py` 从"半独立"（依赖 conftest 的 `glht_token`/`glht_base_url` fixture）改为完全自包含域模块（自读 `GLHT_*` 环境变量），对齐其余域模块的形状
- `registry.py` tier 语义文档新增 400/410（外部系统，两阶段"定位/执行"约定）
- `conftest.py` 删除独立的 `glht_base_url`/`glht_token`/`glht_cleanup_test_data` fixture 及 `pytest_session_start_day` 全局变量（唯一消费者已随之删除），glht 清理并入主 `cleanup_test_data` 调度
- `ENABLE_GLHT_CLEANUP` 默认值：`false` → `true`

### Breaking
- glht 清理从"独立于 `ENABLE_AUTO_CLEANUP` 运行"变为"并入 `run_session_cleanup`，受 `ENABLE_AUTO_CLEANUP` 总闸控制"——`ENABLE_AUTO_CLEANUP=false` 时会连带跳过 glht 清理（此前不会）
- `cleanup-report.yaml` 新增 `glht_inventory_<sn>` / `glht_inventory_flush` 两类 key；不影响已有 key

### Deferred（未处理，需后续单独决策）
- glht 后台历史遗留的存量入库记录（本次分析发现的量级：全量 1321 条，其中「今日」新增 141 条，均由 `terminal_type_enum_cases` 产生）本次不做一次性清理，仅保证"以后新造的都能精确清掉"

---
```

**Step 5：Commit**

```bash
git add jkpt_api_test/common/cleanup/registry.py skills/api-test-framework/references/cleanup-framework.md skills/api-test-framework/references/conftest-jkpt.md skills/api-test-framework/CHANGELOG.md
git commit -m "docs(cleanup): 补模板 D 说明，同步 glht 迁移到 cleanup-framework.md/conftest-jkpt.md/CHANGELOG"
```

---

## 5. Task 5：整体回归

**Step 1：语法自检全量**

```bash
python -c "from common.cleanup import register_glht_inventory, glht; print('ok')"
python -m py_compile conftest.py testcases/test_intercom_group_controller.py testcases/test_terminal_controller.py
```

**Step 2：跑受影响的三个 testcase 文件**（`test_terminal_controller.py` 含 `TestTm07AddTerminalByEnum`，`test_intercom_group_controller.py` 含"满员"场景）

```bash
$env:ENABLE_GLHT_CLEANUP="true"; pytest testcases/test_terminal_controller.py testcases/test_intercom_group_controller.py -vs
```

期望：全部通过；控制台能看到 `[登记glht入库]` 日志，session 末能看到若干 `已定位 N 条，待批量删除` 与一条 `删除 N/M 条`。

**Step 3：核对 `cleanup-report.yaml`**

```powershell
Get-Content .\cleanup-report.yaml -Tail 60
```

期望：能看到 `glht_inventory_<sn>: 已定位 1 条，待批量删除` 若干条，以及 `glht_inventory_flush: 删除 N/N 条`（N 应等于本次运行中所有 mock-in-storage 成功入库的 sn 数量）。

**Step 4：抽样验证真删除**（可选但推荐，复用之前分析用的只读探测手法）——挑一个刚在报告里出现的 sn，用只读查询确认 glht 后台已查不到：

```python
# 手工验证脚本，验证完删除，不留痕
import hashlib, requests
base = "http://back.tdwt.admin.pg8.ink"
pwd_md5 = hashlib.md5("123abc!!".encode()).hexdigest()
token = requests.post(f"{base}/api/admin/login", json={"account":"admin","password":pwd_md5}).json()["data"]["token"]
sn = "<粘贴报告里的一个 sn>"
r = requests.get(f"{base}/api/admin/inventory", params={"Authorization": token, "content": sn, "index":0, "specifyTime":"false", "startTimeStr":"", "endTimeStr":"", "page":1, "pageSize":10})
print(r.json()["data"]["total"])  # 期望 0
```

**Step 5：确认救援棒相关用例不受影响**（`rescue_sat_terminal`/B 棒系列涉及的求救群聊、对讲群用例）

```bash
pytest testcases/test_emergency_chat_controller.py testcases/test_intercom_group_controller.py -vs
```

期望：全部通过（或与迁移前基线一致），说明 `register_glht_inventory` 的接入没有影响原有 `rescue_chat_{sn}`/群相关清理逻辑。

**Step 6：无需 commit**（本任务是验证；若发现问题回退到对应 Task 修复）

---

## 待创建/修改文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `jkpt_api_test/common/cleanup/glht.py` | 重写 | 模板 D：`register`/`cleaner`（定位）/`flush_cleaner`（批量删），自读环境变量 |
| `jkpt_api_test/common/cleanup/__init__.py` | 修改 | 加 `register_glht_inventory`，更新域清单注释 |
| `jkpt_api_test/conftest.py` | 修改 | 删旧 glht fixture 链路 + `pytest_session_start_day`，4 处接入点中 2 处（`rescue_sat_terminal`/`_provision_b_rescue_stick`），更新 `cleanup_test_data` 文档注释 |
| `jkpt_api_test/testcases/test_intercom_group_controller.py` | 修改 | `provision_rescue_stick` 接入 `register_glht_inventory` |
| `jkpt_api_test/testcases/test_terminal_controller.py` | 修改 | `TestTm07AddTerminalByEnum` 接入 `register_glht_inventory` |
| `jkpt_api_test/common/cleanup/registry.py` | 修改 | tier 语义文档补 400/410 |
| `skills/api-test-framework/references/cleanup-framework.md` | 修改 | 新增模板 D |
| `skills/api-test-framework/references/conftest-jkpt.md` | 修改 | 同步 glht fixture 已删除、并入统一调度 |
| `skills/api-test-framework/CHANGELOG.md` | 修改 | 记录本次迁移，标 Breaking + Deferred |
