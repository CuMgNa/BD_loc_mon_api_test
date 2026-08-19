# 清理框架统一化 Implementation Plan

> **For agentic workers:** 本计划承接 `common/cleanup/` 现状分析（见对话记录），已完成设计评审（grill-me 会话，Q1–Q12 + 三遍遗漏检查）。执行时严格遵循「Global Constraints」，不要重新发明格子分类——新域先套 §1 矩阵挑格子，不要凭感觉写。

**Goal:** 修复 `unpaid_order`/`intercom_group` 未接入 `registry` 调度的缺陷，把两者迁移成统一的「动态·逐项 domain」模板；`registry.py` 补两个原语；`b_terminals`/`b_groups` 从 `conftest.py` 挪进 `common/cleanup/` 包；补全 `cleanup-framework.md` 技能文档与 `CHANGELOG.md`。

**Architecture:** 不引入类/继承体系，保持纯函数风格。`registry.py` 加 `register_cleanup_once`（挂载前查重）+ `unregister_cleanup`（按 domain 精确移除），两者只碰 `_REGISTRY`，零新依赖。域模块按「登记时机 × 调度粒度」2×2 矩阵挑现成模板抄：静态一次性（`group.py`/`terminal.py`，不动）、动态·逐项 domain（`unpaid_order.py`/`intercom_group.py`，本次迁移目标；`rescue_chat_{sn}` 已是这个形状但**不是**范例，先天缺 `register()`/去重，只保留现状不模仿）、动态·共享累积列表（暂无实例，留给未来"批量解绑设备"类需求）。

**Tech Stack:** Python 3 + pytest；`common/cleanup/` 子包零 pytest/requests 依赖（仅 `registry.py`，供 skill 复制到新项目）。

## Global Constraints

- `registry.py` 保持零项目依赖（仅标准库 `itertools`/`dataclasses`/`typing`），新加函数不得 import `common.logger_util`/`requests` 等
- `register()`/`unregister()` 对外公开签名不变（`register(group_id)` / `register(order_no)` / `unregister(group_id)`，均单参数）——调用点（`testcases/test_intercom_group_controller.py:267,416,848`、`test_emergency_combo_controller.py:343`、`test_star_bean_controller.py:218`）**一行不改**
- domain 命名统一前缀格式 `f"{模块名}_{实例标识}"`（如 `unpaid_order_{no}`、`intercom_group_{gid}`），前缀取模块名保证跨域不冲突
- `rescue_chat` 本次**不迁移**（超出范围），但 `cleanup-framework.md` 必须明确标注它是技术债、不能被抄成范例
- 不改变任何 cleaner 的 HTTP 调用序列（先 cancel 再 delete / 先 close 再 delete），只改「谁在什么时候调用它、payload 是整表还是单项」
- `cleanup-report.yaml` 落盘结构会变（域粒度从聚合变逐项）——`CHANGELOG.md` 标 BREAKING，不做兼容层
- 每个任务改完本地跑一次相关 testcase（或至少 `python -c "import ..."` 语法自检），确认不引入 `ImportError`/签名不匹配

---

## 0. 背景与决策矩阵（写死进代码注释和 skill 文档，不要口头传递）

**问题**：`unpaid_order.register()` 只把订单号塞进模块内列表，从未调用 `registry.register_cleanup`——它的 `cleaner` 永远不会被 `run_session_cleanup` 执行，订单泄漏到账号历史。`intercom_group.py` 是唯一做对了「首次登记挂 cleaner」的域，但用的是自造的模块级列表去重，没有复用到通用原语。

（旁证：`plan/intercom-group-tests.plan.md` 第 127 行显示对讲群清理的**原始设计**就是 `register_cleanup(f"intercom_group_{id}", id, cleaner, tier=100)`——逐项 domain 本来就是设计意图，实现时才走样成共享列表。本计划是把实现拉回原始设计，不是引入新花样。）

**2×2 决策矩阵**（新增清理域时，回答两个问题选格子）：

| | 逐项 domain（一实例一 domain） | 共享 domain + 模块内累积列表 |
|---|---|---|
| **静态登记**（fixture 一次性，setup 时数据已知全貌） | 少见，暂无实例 | `group.py` / `terminal.py`（fixture 一次性给完整字典，不动） |
| **动态登记**（运行中逐次触发） | `unpaid_order.py` / `intercom_group.py`（本计划迁移目标）——cleaner 逐项调 HTTP，无批量接口 | 暂无实例，留给未来「批量解绑设备」类需求——cleaner 必须拿到完整名单才能拼一次批量请求 |

**选格子的判断标准**：cleaner 处理这个域时，是「逐项调 HTTP」（选左列）还是「必须打包成一次批量请求」（选右列，比如复用 `terminal.py` 的 `/terminals/batch` 那种逗号拼接接口）。选错列的代价：逐项域硬塞进累积列表格子 → 失去逐项失败归因；批量域硬拆成逐项 domain → 把 1 次批量请求拆成 N 次单项请求，多打 HTTP。

---

## 1. Task 1：`registry.py` 加两个原语

**Files:**
- Modify: `jkpt_api_test/common/cleanup/registry.py`

**Interfaces:**
- Produces：`register_cleanup_once(domain: str, payload: Any, cleaner: Callable, *, tier: int = 500) -> None`、`unregister_cleanup(domain: str) -> None`，供 Task 2/3 使用

**Step 1：在 `register_cleanup` 之后加 `register_cleanup_once`**

```python
def register_cleanup_once(domain: str, payload: Any, cleaner: Callable[..., Any], *, tier: int = 500) -> None:
    """登记一个待清理副作用；若同名 domain 已登记则跳过（防重复挂载）。

    用于「动态·逐项 domain」模板：domain 名内嵌实例标识（如 f"unpaid_order_{no}"）。
    这里的去重是防御性的（同一实例被 register 两次时只挂一条），
    不要拿它去实现「共享 domain + 累积列表」模板——那种场景应由域模块自己维护
    模块级列表 + 首次登记才调用本函数（domain 名固定不变），而不是每次都传新 domain。

    Args: 同 register_cleanup。
    """
    if any(d == domain for _, d in registered_domains()):
        return
    register_cleanup(domain, payload, cleaner, tier=tier)


def unregister_cleanup(domain: str) -> None:
    """按 domain 精确名移除已登记条目（用例内消费完成时调用，防 session 末重复收尾）。

    仅服务于「动态·逐项 domain」模板的可选注销语义；
    「共享 domain + 模块内累积列表」模板不需要它——那种场景的"注销"是域模块自己
    从内部列表里 remove 一项，压根不动 registry。
    """
    _REGISTRY[:] = [e for e in _REGISTRY if e.domain != domain]
```

**Step 2：更新模块顶部 docstring 纪律清单**，在纪律 4 之后加一条：

```python
#   6. 新增域先套 references/cleanup-framework.md 的 2×2 矩阵选模板，
#      不要现场发明第三种登记方式。
```

**Step 3：语法自检**

```bash
python -c "from common.cleanup.registry import register_cleanup_once, unregister_cleanup; print('ok')"
```

期望输出 `ok`。

**Step 4：Commit**（本任务不单独提交，跟 Task 2 一起提交，因为 Task 2 才是这两个原语的第一个消费者，独立提交没有可运行的验证点）

---

## 2. Task 2：`unpaid_order.py` 迁移成「动态·逐项 domain」

**Files:**
- Modify: `jkpt_api_test/common/cleanup/unpaid_order.py`

**Interfaces:**
- Consumes：Task 1 的 `register_cleanup_once`
- Produces：`register(order_no)`（签名不变）、`cleaner(ctx, order_no, **flags) -> str`（payload 类型从 `None` 变成单个 `order_no` 字符串，仅 registry 内部调用，无外部消费者依赖旧签名）

**Step 1：整份重写**

```python
# common/cleanup/unpaid_order.py
# tier 100：收 session 登记的待支付订单（cancel → delete，逐单失败不抛）。
# 对外登记入口：common.cleanup.register_unpaid_order_no（即本模块 register，
# 由包 __init__ re-export；原 common/order_cleanup_util.py 已删除）。
# 模板：动态·逐项 domain（无批量接口，一单一 domain；与 intercom_group.py 同款，
# 详见 references/cleanup-framework.md 2×2 矩阵）。
from common.cleanup.registry import register_cleanup_once
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "unpaid_order"


def register(order_no) -> None:
    """登记待支付单（buy 成功后调用；落一个独立 domain，同号天然去重）。"""
    if order_no is None:
        return
    no = str(order_no).strip()
    if not no:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{no}", no, cleaner, tier=100)
    key("登记待支付订单", no)


def _try_order_action(method, url, order_no, auth_headers, case_name) -> bool:
    try:
        res = _http.send_request(
            method,
            url,
            params={"orderNo": order_no},
            headers=auth_headers,
            case_name=f"{case_name} {order_no}",
            log_level="none",
        )
        data = parse_response_json(res, context=case_name)
        code = data.get("code")
        msg = data.get("msg")
        if code == 0:
            key(case_name, f"{order_no} code=0")
            return True
        key(case_name, f"{order_no} code={code} msg={msg}")
        return False
    except Exception as exc:
        key(case_name, f"{order_no} 忽略: {exc}")
        return False


def cleaner(ctx, order_no, **flags) -> str:
    """registry 入口：payload = 单个 order_no（每单独立 domain，session 末逐单收尾）。

    flags.keep_orders=True 时跳过（未来扫码场景的参数位；
    当前主人拍板：订单默认收走，总闸 ENABLE_AUTO_CLEANUP=false 时整个调度不进来）。
    """
    if flags.get("keep_orders"):
        return "keep_orders=True，跳过收单"
    cancelled = _try_order_action(
        "post", f"{ctx.base_url}/api/monitor/order/cancel",
        order_no, ctx.auth_headers, "session收尾-取消订单",
    )
    deleted = _try_order_action(
        "delete", f"{ctx.base_url}/api/monitor/order/delete",
        order_no, ctx.auth_headers, "session收尾-删除订单",
    )
    key("待支付订单收尾", f"{order_no} cancel={cancelled}, delete={deleted}")
    return f"cancel={cancelled}, delete={deleted}"
```

**Step 2：语法自检 + 回归**

```bash
python -c "from common.cleanup import register_unpaid_order_no; print('ok')"
```

跑一条会触发 buy 的用例确认登记路径不报错（挑一条快的，不用全量）：

```bash
pytest testcases/test_star_bean_controller.py -k Buy -vs
```

期望：用例通过，控制台能看到 `[登记待支付订单] xxx` 日志。

**Step 3：Commit**

```bash
git add jkpt_api_test/common/cleanup/registry.py jkpt_api_test/common/cleanup/unpaid_order.py
git commit -m "fix(cleanup): unpaid_order 接入 registry 调度，迁移为逐项 domain"
```

---

## 3. Task 3：`intercom_group.py` 迁移成同款模板

**Files:**
- Modify: `jkpt_api_test/common/cleanup/intercom_group.py`

**Interfaces:**
- Consumes：Task 1 的 `register_cleanup_once` / `unregister_cleanup`
- Produces：`register(group_id)` / `unregister(group_id)`（签名不变）、`cleaner(ctx, group_id, **flags) -> str`

**Step 1：整份重写**（同时清掉现有文件里未被使用的 `_jp()`/`_jsonpath_parse` 死代码——`_act` 用的是 `parse_response_json`，不是 jsonpath）

```python
# common/cleanup/intercom_group.py
# tier 100：收 session 遗留的对讲群（close → delete）。
# 模板：动态·逐项 domain（无批量接口，一群一 domain；与 unpaid_order.py 同款，
# 详见 references/cleanup-framework.md 2×2 矩阵）。
# create 成功即 register；用例内 delete 成功后 unregister——
# session 末只兜底中断/失败透留的群，无双重收尾。
from common.cleanup.registry import register_cleanup_once, unregister_cleanup
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "intercom_group"


def register(group_id) -> None:
    """create 成功后登记（落一个独立 domain，同 id 天然去重）。"""
    if group_id is None:
        return
    gid = str(group_id).strip()
    if not gid:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{gid}", gid, cleaner, tier=100)
    key("登记对讲群", gid)


def unregister(group_id) -> None:
    """用例内 delete 成功后注销（消费完成出网，防 session 末重复收尾）。"""
    gid = str(group_id).strip()
    if not gid:
        return
    unregister_cleanup(f"{_DOMAIN_PREFIX}_{gid}")


def _act(method, url, gid, auth_headers, case_name) -> bool:
    try:
        res = _http.send_request(
            method, url, params={"intercomGroupId": gid},
            headers=auth_headers, case_name=f"{case_name} {gid}", log_level="none",
        )
        data = parse_response_json(res, context=case_name)
        code = data.get("code")
        if code == 0:
            key(case_name, f"{gid} code=0")
            return True
        key(case_name, f"{gid} code={code} msg={data.get('msg')}")
        return False
    except Exception as exc:
        key(case_name, f"{gid} 忽略: {exc}")
        return False


def cleaner(ctx, group_id, **flags) -> str:
    """registry 入口：payload = 单个 group_id（每群独立 domain）。

    先 close（已关闭/不存在返回非 0 只记日志）再 delete。
    探针实证活跃群也能直接删，close 只是稳妥化步骤。
    """
    closed = _act("put", f"{ctx.base_url}/api/monitor/intercom/group/close",
                  group_id, ctx.auth_headers, "session收尾-关闭对讲群")
    deleted = _act("delete", f"{ctx.base_url}/api/monitor/intercom/group/delete",
                    group_id, ctx.auth_headers, "session收尾-删除对讲群")
    key("对讲群收尾", f"{group_id} close={closed}, delete={deleted}")
    return f"close={closed}, delete={deleted}"
```

**Step 2：回归**

```bash
python -c "from common.cleanup import register_intercom_group, intercom_group; print('ok')"
pytest testcases/test_intercom_group_controller.py -vs
```

期望：全部用例通过；`Ig02Create` 正向后能在日志看到 `[登记对讲群]`；`Ig10Delete`（或对应 close/delete 收尾用例）成功后能看到 `unregister` 生效（session 末报告里该群不再出现 FAILED/重复收尾）。

**Step 3：Commit**

```bash
git add jkpt_api_test/common/cleanup/intercom_group.py
git commit -m "refactor(cleanup): intercom_group 迁移为逐项 domain，复用 registry 原语"
```

---

## 4. Task 4：`b_terminals`/`b_groups` 挪进 `common/cleanup/` 包

**Files:**
- Modify: `jkpt_api_test/common/cleanup/terminal.py`（加 `cleaner_b`）
- Modify: `jkpt_api_test/common/cleanup/group.py`（加 `cleaner_b`）
- Modify: `jkpt_api_test/conftest.py:527-585` 附近（删 `_cleanup_b_terminals`/`_cleanup_b_groups`，改注册调用）

**Interfaces:**
- Produces：`terminal.cleaner_b(ctx, payload, **flags) -> str`、`group.cleaner_b(ctx, payload, **flags) -> str`（payload 形状与现有 `_B_STACK` 字典一致：`{"auth_headers":…, "one_id":…, "two_id":…, "three_id":…}`）

**Step 1：`terminal.py` 追加**（文件末尾，`cleaner` 函数之后）

```python
def cleaner_b(ctx, payload, **flags) -> str:
    """registry 入口（B 支路变体）：payload 自带 B token，
    不能用 ctx.auth_headers（那是 A 的）。B 测试分组下设备用 B 权限批量删。"""
    headers = payload["auth_headers"]
    total_deleted, total_failed = 0, 0
    for level in ("three_id", "two_id", "one_id"):
        group_id = payload.get(level)
        if not group_id:
            continue
        addrs = get_terminals_by_group(ctx.base_url, headers, group_id)
        if addrs:
            deleted, failed = cleanup_terminals_batch(ctx.base_url, headers, group_id, addrs)
            total_deleted += deleted
            total_failed += failed
    key("B设备删除统计", f"成功: {total_deleted}, 失败: {total_failed}")
    return f"成功: {total_deleted}, 失败: {total_failed}"
```

**Step 2：`group.py` 追加**（文件末尾，`cleaner` 函数之后）

```python
def cleaner_b(ctx, payload, **flags) -> str:
    """registry 入口（B 支路变体）：payload 自带 B token，删 B 测试一级分组。"""
    success, fail = delete_groups_in_order(ctx.base_url, payload["auth_headers"], payload)
    key("B分组删除统计", f"成功: {success}, 失败: {fail}")
    return f"成功: {success}, 失败: {fail}"
```

**Step 3：`conftest.py` 改动**（按内容定位，不按行号——第一步删除会让后面行号整体上移，不要依赖 Step 1 写的原始行号）：

1. 删除 `_cleanup_b_terminals`/`_cleanup_b_groups` 两个完整函数定义（从 `def _cleanup_b_terminals(ctx, payload, **flags) -> str:` 起，到 `_cleanup_b_groups` 函数体最后一行 `return f"成功: {success}, 失败: {fail}"` 止），保留 `_B_STACK = {...}` 那一行不动。
2. 把原来的

```python
    from common.cleanup import register_cleanup
    register_cleanup("b_terminals", _B_STACK, _cleanup_b_terminals, tier=200)
    register_cleanup("b_groups", _B_STACK, _cleanup_b_groups, tier=300)
```

改成：

```python
    from common.cleanup import register_cleanup, terminal as _t, group as _g
    register_cleanup("b_terminals", _B_STACK, _t.cleaner_b, tier=200)
    register_cleanup("b_groups", _B_STACK, _g.cleaner_b, tier=300)
```

（用 `StrReplace` 按上面这段完整代码块做精确匹配替换，不要用行号切片。）

**Step 4：回归**（B 支路目前只在批 2/对讲群 B 支路场景触发，若本地没有 B 账号环境变量，至少跑语法自检确保没打错 import）

```bash
python -c "import ast; ast.parse(open('conftest.py', encoding='utf-8').read())"
python -c "from common.cleanup import terminal, group; print(hasattr(terminal, 'cleaner_b'), hasattr(group, 'cleaner_b'))"
```

期望：两条都不报错，第二条输出 `True True`。若本地有 B 账号环境变量，额外跑一次涉及 `rescue_sat_terminal_b` 的用例做真实回归。

**Step 5：Commit**

```bash
git add jkpt_api_test/common/cleanup/terminal.py jkpt_api_test/common/cleanup/group.py jkpt_api_test/conftest.py
git commit -m "refactor(cleanup): b_terminals/b_groups 移入 common/cleanup 包，conftest 只留装配"
```

---

## 5. Task 5：补 `cleanup-framework.md` + 同步 `conftest-jkpt.md` + `CHANGELOG.md`

**Files:**
- Create: `skills/api-test-framework/references/cleanup-framework.md`
- Modify: `skills/api-test-framework/references/conftest-jkpt.md`（第 21、261、275-283 行附近，内部辅助函数表已过期——`get_terminals_by_group`/`cleanup_terminals_batch`/`delete_groups_in_order` 早已搬进 `common/cleanup/`，不再是"不在 common/ 的内部函数"）
- Modify: `skills/api-test-framework/CHANGELOG.md`（顶部追加一条 `[Unreleased]` 段）

**Step 1：`cleanup-framework.md` 内容骨架**（含 §0 矩阵、两种模板的完整可复制示例、`rescue_chat` 技术债说明、新增域 checklist、三层可移植性说明）：

```markdown
# 清理框架（common/cleanup/）

## 0. 决策矩阵：新增域先回答两个问题

|              | 逐项 domain | 共享 domain + 累积列表 |
|--------------|------------|------------------------|
| 静态登记（fixture 一次性） | 少见 | `group.py` / `terminal.py` |
| 动态登记（运行中逐次触发） | `unpaid_order.py` / `intercom_group.py` | 暂无实例（留给有真批量接口的域） |

选左列还是右列，只看一个问题：cleaner 处理这个域时是「逐项调 HTTP」还是「必须打包成一次批量请求」？
有真批量接口（如 `/terminals/batch` 逗号拼 addr）→ 选右列；没有 → 选左列。

**`rescue_chat_{sn}`（`conftest.py` 内 `register_cleanup(f"rescue_chat_{sn}", ...)`）是已知技术债，
不是范例**——它没有包一层 `register()`，也没有用 `register_cleanup_once` 去重。不要抄它，抄下面两个模板。

## 1. 模板 A：静态一次性域

不需要额外包装，`register_cleanup` 本身已经足够薄：

    from common.cleanup import register_cleanup
    register_cleanup("groups", group_ids, group.cleaner, tier=300)

fixture 只跑一次，payload 在注册时已知全貌，无需去重/注销。

## 2. 模板 B：动态·逐项 domain（无批量接口）

三个函数：`register(id)` 落一个独立 domain，`cleaner(ctx, id, **flags)` 处理单个实例，
可选 `unregister(id)`（用例内消费完成时调用）。完整范例见
`common/cleanup/unpaid_order.py`（无 unregister 需求）与
`common/cleanup/intercom_group.py`（有 unregister 需求）。

    from common.cleanup.registry import register_cleanup_once, unregister_cleanup

    _DOMAIN_PREFIX = "your_domain"

    def register(item_id) -> None:
        if item_id is None:
            return
        iid = str(item_id).strip()
        if not iid:
            return
        register_cleanup_once(f"{_DOMAIN_PREFIX}_{iid}", iid, cleaner, tier=100)

    def unregister(item_id) -> None:      # 仅在有用例内消费场景时才写
        unregister_cleanup(f"{_DOMAIN_PREFIX}_{item_id}")

    def cleaner(ctx, item_id, **flags) -> str:
        ...  # 单项清理逻辑
        return "..."

`register_cleanup_once` 在这里的去重是**防御性**的（同一实例被 register 两次时只挂一条），
不是核心机制。

## 3. 模板 C：动态·共享 domain + 累积列表（有真批量接口）

暂无实例，未来若新增"批量解绑设备"一类、复用批量接口的域，照这个形状写：

    from common.cleanup.registry import register_cleanup_once
    from common.cleanup import registered_domains

    _DOMAIN = "your_batch_domain"          # 固定不变，不带实例 id
    _PENDING: list = []

    def register(item_id) -> None:
        if item_id is None or item_id in _PENDING:
            return
        _PENDING.append(item_id)
        register_cleanup_once(_DOMAIN, None, cleaner, tier=200)   # 只挂一次

    def cleaner(ctx, _payload, **flags) -> str:
        items = list(_PENDING)
        if not items:
            return "无登记"
        # 一次批量请求处理 items，不要逐项循环调 HTTP
        ...
        return f"登记 {len(items)}, ..."

这里 `register_cleanup_once` 的去重是**核心机制**：domain 名固定，多次调用只挂一次 cleaner，
后续调用只管往 `_PENDING` 追加。跟模板 B 的用法容易混——模板 B 每次传的 domain 都不同（带 id），
模板 C 每次传的 domain 都相同。

## 4. 新增域 checklist

1. 什么时候知道要清？fixture 一次性 → 模板 A；运行中逐次 → B 或 C。
2. cleaner 处理时是逐项调 HTTP 还是要打包批量？逐项 → B；批量 → C。
3. 用例内会不会主动消费掉这个实例（如 delete 成功）？会 → 模板 B 要写 `unregister`。
4. tier 怎么选：100 会话级业务对象（群/订单）/ 200 设备 / 300 组织（分组）；新域挑层不挑位置。

## 5. 可移植性：换项目怎么套用

- **L0 内核 `registry.py`**：零依赖（仅 stdlib），直接整份拷贝到新项目，不用改一行。
- **域模块**（`terminal.py`/`unpaid_order.py`…）：业务强绑定，不迁移代码，只迁移模板形状——
  按上面 §1–3 的模板在新项目里为每个业务域重写 `register()`/`cleaner()`。
- **conftest 收尾壳**：结构可参考（起一个 session fixture，构造 `CleanupContext`，
  调 `run_session_cleanup`，落报告），但 `base_url`/`auth_headers`/`ENABLE_XXX_CLEANUP`
  这些取值要按新项目自己的鉴权体系重写。
```

**Step 2：`conftest-jkpt.md` 同步修正**——把第 21 行「内部辅助函数（用例勿调）」行和第 275-283 行整段改成指向 `common/cleanup/`（`get_terminals_by_group`/`cleanup_terminals_batch` 现在在 `common/cleanup/terminal.py`，`delete_groups_in_order` 在 `common/cleanup/group.py`，均可 `from common.cleanup import terminal, group` 后按需调用，不再是"不在 common/ 的内部函数"），并在「会话清理」行后加一句指向新文档：

```
详见 [cleanup-framework.md](./cleanup-framework.md)：新增清理域先套 2×2 矩阵选模板。
```

**Step 3：`CHANGELOG.md` 顶部追加**

```markdown
## [Unreleased] — 2026-08-19 清理框架统一化

### Fixed
- `unpaid_order.register()` 从未接入 `registry.register_cleanup`，导致待支付订单从不进入 session 收尾调度——迁移为逐项 domain 后正式接入

### Added
- `registry.py`：`register_cleanup_once`（挂载前查重）、`unregister_cleanup`（按 domain 精确移除）
- `references/cleanup-framework.md`：新增清理域的 2×2 决策矩阵 + 三套模板 + checklist + 可移植性说明

### Changed
- `unpaid_order.py` / `intercom_group.py` 从「共享 domain + 模块内平行列表」迁移为「动态·逐项 domain」，复用 `registry.py` 新原语
- `b_terminals`/`b_groups` 清理逻辑从 `conftest.py` 内联函数挪进 `common/cleanup/terminal.py`/`group.py`（`cleaner_b` 变体）

### Breaking
- `cleanup-report.yaml` / session 清理报告的 domain 粒度从「聚合一行」变为「逐项一行」（如 `intercom_groups: ...` 变成多条 `intercom_group_<gid>: ...`）；无代码依赖旧 key 名（已检索确认），仅影响人工读报告时的行数

---
```

**Step 4：Commit**

```bash
git add skills/api-test-framework/references/cleanup-framework.md skills/api-test-framework/references/conftest-jkpt.md skills/api-test-framework/CHANGELOG.md
git commit -m "docs(cleanup): 补 cleanup-framework.md 决策矩阵，同步 conftest-jkpt.md，CHANGELOG 记录本次迁移"
```

---

## 6. Task 6：整体回归

**Step 1：全量跑受影响的三个 testcase 文件**

```bash
pytest testcases/test_intercom_group_controller.py testcases/test_emergency_combo_controller.py testcases/test_star_bean_controller.py -vs
```

期望：全部通过（或与迁移前基线一致，无新增失败）。

**Step 2：检查落盘报告粒度确实变细**

```bash
cat cleanup-report.yaml   # Windows 用 Get-Content
```

期望：能看到 `unpaid_order_<no>` / `intercom_group_<gid>` 这类逐项 key，而不是聚合的 `unpaid_order`/`intercom_groups`。

**Step 3：确认 `unregister` 真的生效**——挑一条对讲群 delete 成功的用例跑完后，检查该群的 domain 没有出现在 `run_session_cleanup` 返回的 report 里（说明 session 末没有重复收尾）。可以在 `cleaner()` 里临时加一行 `print` 或直接看 Allure「【收尾】清理报告」附件确认。

**Step 4：无需 commit**（本任务是验证，不产出代码变更；若发现问题回退到对应 Task 修复）

---

## 待创建/修改文件清单

| 文件路径 | 变更类型 | 说明 |
|----------|---------|------|
| `jkpt_api_test/common/cleanup/registry.py` | 修改 | 加 `register_cleanup_once`/`unregister_cleanup` |
| `jkpt_api_test/common/cleanup/unpaid_order.py` | 重写 | 迁移为逐项 domain |
| `jkpt_api_test/common/cleanup/intercom_group.py` | 重写 | 迁移为逐项 domain，清掉死代码 |
| `jkpt_api_test/common/cleanup/terminal.py` | 修改 | 加 `cleaner_b` |
| `jkpt_api_test/common/cleanup/group.py` | 修改 | 加 `cleaner_b` |
| `jkpt_api_test/conftest.py` | 修改 | 删内联 `_cleanup_b_terminals`/`_cleanup_b_groups`，改注册调用 |
| `skills/api-test-framework/references/cleanup-framework.md` | 新建 | 决策矩阵 + 模板 + checklist |
| `skills/api-test-framework/references/conftest-jkpt.md` | 修改 | 同步过期的内部函数说明 |
| `skills/api-test-framework/CHANGELOG.md` | 修改 | 记录本次迁移，标 Breaking |
