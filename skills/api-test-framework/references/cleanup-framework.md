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

```python
from common.cleanup import register_cleanup
register_cleanup("groups", group_ids, group.cleaner, tier=300)
```

fixture 只跑一次，payload 在注册时已知全貌，无需去重/注销。

## 2. 模板 B：动态·逐项 domain（无批量接口）

三个函数：`register(id)` 落一个独立 domain，`cleaner(ctx, id, **flags)` 处理单个实例，
可选 `unregister(id)`（用例内消费完成时调用）。完整范例见
`common/cleanup/unpaid_order.py`（无 unregister 需求）与
`common/cleanup/intercom_group.py`（有 unregister 需求）。

```python
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
```

`register_cleanup_once` 在这里的去重是**防御性**的（同一实例被 register 两次时只挂一条），
不是核心机制。

## 3. 模板 C：动态·共享 domain + 累积列表（有真批量接口）

暂无实例，未来若新增"批量解绑设备"一类、复用批量接口的域，照这个形状写：

```python
from common.cleanup.registry import register_cleanup_once

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
```

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
