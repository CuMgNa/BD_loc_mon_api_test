# 应急套餐订单接口测试 Implementation Plan

> **For agentic workers:** 先做第 0 节探针，**禁止**在探针前把 YAML `expected.code/msg` 写成臆测值。实现时遵循 `skills/api-test-framework`（只 `from common.*`、模式 A/B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result` 且必传 `biz_context`）。一类一接口，叶子默认 `[case0]`，**禁止**中文 `parametrize ids`。每个接口的 query / json 以本文 §2 为准。
>
> 来源：Apifox tag `应急套餐订单接口`（6 URL / 7 operation）；覆盖缺口 [api-automation-coverage-gap.plan.md](./api-automation-coverage-gap.plan.md) §4.5
> 契约：Apifox「Swagger3接口文档」刷新时间 **2026-08-18T05:51:19.205Z**（`refresh_project_oas_webcsm`）
> 互补：[emergency-combo-mall-tests.plan.md](./emergency-combo-mall-tests.plan.md)（商城 buy 写 `combo_order_no` 本文件可读、**禁止用例内 cancel 那张单**）；[star-bean-tests.plan.md](./star-bean-tests.plan.md)（同 page 可能混入 `STAR_BEAN`；本文件另造 `eo_lifecycle_star_bean_order_no` 做 cancel）
> 沿用主人拍板（2026-08-17）：自动化**不完成支付、不扫码、不验开通后扣量**
> 主人拍板（2026-08-18）：cancel 覆盖套餐 + 星豆两种 `productType`（各造 lifecycle 单）；session 末只收**登记表**里的待支付单（商城/星豆 buy）；**本文件 lifecycle 单不登记**，由 Eo03/Eo04 吃掉，避免双重清除。`ENABLE_AUTO_CLEANUP=false` 时保留登记单给人工扫码

**Goal:** 订单查询（page / detail）+ 本文件自造待支付单的取消/删除闭环（套餐 + 星豆各一张）。不调微信小程序支付，不扫二维码完成实付。

**Architecture:** 模式 A（page 无单也可跑）+ 模式 B′（可选读商城 `combo_order_no` 做 detail 命中；本文件 HTTP 调 `POST /emergency/combo/buy` 写 `eo_lifecycle_order_no`、调 `POST /star-bean/buy` 写 `eo_lifecycle_star_bean_order_no` → cancel → delete；**lifecycle 不** `register_unpaid_order_no`）。**禁止** `from testcases.test_emergency_combo_controller import …` / `from testcases.test_star_bean_controller import …`。套餐 buy 的设备 addr 走 `rescue_sat_terminal`；星豆 buy **不依赖设备**。

**Tech Stack:** pytest + YAML + `BaseRequest` + Allure（与商城/星豆同一套）

## Global Constraints

- 只 `from common.*`；禁止 `api_test_framework` / 模式 C
- Authorization：OAS 写 **query required**。**默认只 Header**；探针锁定后全文统一，YAML 不写真实 token
- 正向 `expected.msg`，负向 `expected.error_msg`；禁止正向写 `error_msg: "成功"`
- `no_auth: true` 只剥 `Authorization`，保留 `Accept-Language`
- YAML 不写真实卡号/密码/真实 orderNo；设备 `{{rescue_sat_terminal}}` 由 testcase 字符串替换，**不要** `resolve_extract_value`
- **禁止**完成支付：不扫码、不调微信、不断言 `orderStatus=PAID`、不断言 info `status=1`
- **禁止**用例内 cancel / delete 商城 `{{combo_order_no}}`、星豆 `{{star_bean_order_no}}`（那两张由商城/星豆 `register_unpaid_order_no`，session 末收；碰了会和收尾双重清除）
- **禁止**对本文件 helper buy 的 lifecycle 单调用 `register_unpaid_order_no`（会在 Eo03/Eo04 吃掉后再被 session 清一次）
- 负向 `orderNo` 一律字面量假值（如 `0` / `INVALID_ORDER_NO`），禁止 `{{combo_order_no}}` / `{{star_bean_order_no}}` / `{{eo_lifecycle_order_no}}` / `{{eo_lifecycle_star_bean_order_no}}` 占位符——缺 extract 时 skip 会吞掉负向
- `json_data = res.json()` 每个请求只调一次；`send_request(..., log_level="none")`；失败排查可临时 `"simple"`
- **本文件禁 pytest-xdist**（extract 链 + 生命周期单）；**cancel / delete / 本文件 buy 叶子禁 rerun**（副作用改单 / 堆单）
- 断言一律 `assert_api_result(...)` 且**必须传 `biz_context`**（至少 `{"请求参数": params或body}`）
- 方法签名一律注入 `base_url, auth_headers, case`；需要设备时再加 `rescue_sat_terminal`
- cancel 是 **POST + `params=`**（query `orderNo`），禁止抄成 `json=`；delete 是 **DELETE + `params=`**；payment 是 **GET + `params=`**

---

## 0. 范围、执行顺序、session 副作用

Apifox tag **应急套餐订单接口** 恰好 6 个 URL（刷新后未增删）。`payment/wx/applet` 上有 **GET（deprecated）+ POST** 两个 operation，本批都不做。

| 序 | 类名 | 方法 | 路径 | OAS summary | 本批 |
|----|------|------|------|-------------|------|
| 1 | `TestEo01Page` | GET | `/api/monitor/order/page` | 分页查询订单列表 | 做 |
| 2 | `TestEo02Detail` | GET | `/api/monitor/order/detail` | 订单详情 | 做 |
| 3 | `TestEo03Cancel` | POST | `/api/monitor/order/cancel` | 取消订单 | **做（套餐 + 星豆各一张本文件自造单）** |
| 4 | `TestEo04Delete` | DELETE | `/api/monitor/order/delete` | 删除订单 | **做（探针后钉：先取消再删 / 未支付可删）** |
| 5 | — | GET | `/api/monitor/order/payment` | 二维码支付订单 | **本批不做正向**（探针可打一次记形态，YAML 不写扫码/实付 case） |
| 6 | — | GET+POST | `/api/monitor/order/payment/wx/applet` | 微信小程序支付 | **不做**（GET deprecated；POST 要 `loginCode`） |

文件内类定义顺序必须 01→04。`TestEo03` 必须在 `TestEo04` 之前（若探针证明删除对象必须是已取消单）。

**明确不做（本计划全文）：**

- 扫码 / 支付宝 / 微信把 `UNPAID` 变成 `PAID`
- `payment/wx/applet` 整段（含未弃用的 POST）
- 退款态 `PROCESSING_REFUND` / `REFUNDED` / `REFUNDED_FAILED` 的正向造数
- **用例内**取消或删除商城 `combo_order_no`、星豆 `star_bean_order_no`（那两键不是 cancel 正向；session 末登记表另收）
- page 全账号扫描 UNPAID 再删（方案 B 不做；历史脏单由人先清）
- 互 import 商城 / 星豆 testcase 类
- 开通后 info/remaining/usage 守恒（仍属串测）

**session 副作用（商城/星豆待支付单走登记表 + `cleanup_test_data`；本文件不要再挂 teardown，lifecycle 单也不进登记表）：**

- session `autouse` 的 `cleanup_test_data` → 登录 + 建三级分组；`ENABLE_AUTO_CLEANUP=true`（默认）时 session 末：关求救群 → **cancel→delete 登记表**（仅商城/星豆 buy 登过的单）→ 删设备 → 删分组。单条失败只打日志，不让 session 红
- **避免双重清除：** 会在用例里 cancel/delete 的 `orderNo` 不进登记表。本文件 helper 只 `write_yaml` lifecycle 键，**禁止** `register_unpaid_order_no`
- `ENABLE_AUTO_CLEANUP=false`：保留**登记表**里的待支付单给人工扫码（商城/星豆）；不影响本文件 Eo03/Eo04 仍会吃掉 lifecycle 单。**不要**另开订单清理开关
- 注入 `rescue_sat_terminal` 的类会再入库一根救援棒（套餐 lifecycle buy 需要；星豆 lifecycle 不需要设备）
- 本文件生命周期最多 **1 次** `POST /emergency/combo/buy` + **1 次** `POST /star-bean/buy`（与商城/星豆模块的 extract 单分开；连续 buy 现网会 `999`/`下单过于频繁` → skip，不许改去动遗留 extract 单）
- helper buy 已成功但 Eo03/Eo04 skip 或失败：lifecycle 单不在登记表，session **不会**收。接受偶发残留（与历史脏单同一口径，人清），禁止失败路径再登记
- 单跑 `TestEo02Detail`：无 `combo_order_no` 且 page 也抽不到单 → **skip**
- 单跑 `TestEo03Cancel` / `TestEo04Delete`：套餐 helper 无 mall id 时自己 GET mall；无设备 fixture 时**不要**套餐 buy。星豆 helper 无设备依赖，`json={"amount":1}`

**与商城同 session 跑时的纪律：**

```text
pytest testcases/test_emergency_combo_controller.py testcases/test_emergency_order_controller.py
```

- 商城先跑，`extract.yaml` 有 `combo_order_no` / `combo_mall_id` / `combo_mall_price`
- 本文件 detail 正向优先用 `{{combo_order_no}}` 做「商城刚下的单能查到」
- **用例内不得**对该 orderNo 或 `star_bean_order_no` 调 cancel / delete / payment

---

## 1. 三条传值通道

### 通道 A — Fixture

| Fixture | 给谁用 | 怎么用 |
|---------|--------|--------|
| `base_url` | 所有请求 | 前缀 `{base_url}/api/monitor` |
| `auth_headers` | 所有请求 | `no_auth: true` 时只去掉 `Authorization` |
| `rescue_sat_terminal` | 本文件自造 buy 的 `addrs` | YAML `{{rescue_sat_terminal}}`，Helpers 字符串替换 |

page / detail / 负向 cancel·delete / **星豆 lifecycle 正向**可以不注入设备 fixture（detail / 星豆 buy 不带 addr）。套餐 lifecycle buy 必须注入 `rescue_sat_terminal`。`TestEo03Cancel` 同一方法含套餐正向时整方法注入设备 fixture（星豆 case 会多一根 session 设备，可接受）。

占位符解析收敛到 `_EoHelpers`（禁多处内联）：

```python
class _EoHelpers:
    """共享逻辑；不以 Test 开头，pytest 不收集。"""

    @staticmethod
    def resolve_addr(raw, rescue_sat_terminal):
        if isinstance(raw, str) and raw.strip() == "{{rescue_sat_terminal}}":
            return rescue_sat_terminal
        return raw

    @staticmethod
    def _headers(auth_headers, case):
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        return headers

    @staticmethod
    def resolve_order_no(raw, required=False):
        if is_extract_placeholder(raw):
            return resolve_extract_value(raw, required=required)
        return raw
```

### 通道 B — extract.yaml

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `combo_order_no` | **商城** `TestEcm05Buy`（本文件不写） | `TestEo02Detail` 正向「按商城单号」；缺失 → skip 该 case | 证明商城刚下的待支付单在订单模块可见；**不是** cancel 正向 |
| `combo_mall_id` / `combo_mall_price` | **商城** mall 正向 | 本文件 helper 套餐 buy；缺失则 helper **自己 GET mall** 取最低价日包，不 skip 整文件 | 套餐生命周期下单 |
| `eo_page_order_no` | **仅** `TestEo01Page` 正向-UNPAID 且列表非空：优先 `productType==COMMUNICATION_COMBO` 的第一条 | `TestEo02Detail` 正向「按分页抽出的单」兜底 | 单跑本文件、商城没跑时仍能 detail |
| `eo_lifecycle_order_no` | helper 本文件套餐 buy `code==0`（只写一次） | cancel 正向-套餐 / delete 正向-套餐 | 套餐自造单闭环；**不是** `combo_order_no` |
| `eo_lifecycle_star_bean_order_no` | helper 本文件星豆 buy `code==0`（只写一次，`amount=1`） | cancel 正向-星豆 / delete 正向-星豆 | 星豆自造单闭环；**不是** `star_bean_order_no`。星豆模块 extract last-wins 会丢掉第一张充值单，故 **禁止** 复用 `star_bean_order_no` 做 cancel |

`write_yaml(mode="append")` 同 key last-wins；`clear_data_per_session` 开跑前清空。

**登记表（`register_unpaid_order_no`）不是本文件的事：** 商城/星豆 buy 成功才登记，session 末收。本文件 helper **只写 extract，不登记**。conftest **不写** extract。

**只写一次：**

- `eo_page_order_no`：模块布尔 `_PAGE_EXTRACTED`；只在 `orderStatus=UNPAID` 那条正向写
- `eo_lifecycle_order_no`：模块布尔 `_COMBO_LIFECYCLE_BOUGHT`；cancel 类进入套餐正向时若还没有则 buy 一次；delete 只读，禁止再 buy
- `eo_lifecycle_star_bean_order_no`：模块布尔 `_STAR_BEAN_LIFECYCLE_BOUGHT`；cancel 类进入星豆正向时若还没有则 buy 一次；delete 只读

读取：

```python
order_no = _EoHelpers.resolve_order_no(case.get("orderNo"), required=is_extract_placeholder(case.get("orderNo")))
```

### 通道 C — YAML 字面量

字段名与 OAS **驼峰一致**：

| YAML 字段 | 含义 |
|-----------|------|
| `name` | 只做标题，不发给接口 |
| `orderStatus` | page：`UNPAID` / `CANCELLED` / `PAID` / `EXPIRED` 等；缺省 case 不写该键 |
| `page` / `pageSize` | page 分页 |
| `orderNo` | detail / cancel / delete：正向占位符或字面量假值 |
| `no_auth` | `true` 时剥 token |
| `expected.code` / `expected.msg` / `expected.error_msg` | 正向 msg、负向 error_msg |

page **没有** `productType` 过滤参数（OAS 无此 query）。混入星豆单是合法的；命中商城单靠 `orderNo`，不要假设第一页第一条就是通信套餐。

---

## 2. 接口参数传递

公共前缀：`{base_url}/api/monitor`。

### 2.1 GET `/order/page` — `TestEo01Page.test_order_page`

**怎么传：** 全 **query**，`params=`。

| HTTP 参数 | 位置 | 正向-无过滤 | 正向-UNPAID | 正向-CANCELLED | 边界 pageSize=0（探针后） | 负向-非法状态 | 负向-无 Token |
|-----------|------|-------------|-------------|----------------|--------------------------|---------------|---------------|
| `orderStatus` | query | **不传** | `UNPAID` | `CANCELLED` | 不传或 UNPAID | `FOO` | 任意 |
| `page` | query | 不传 | 不传 | 不传 | 探针 | 不传 | 不传 |
| `pageSize` | query | 不传 | 不传 | 不传 | 探针 | 不传 | 不传 |
| `Authorization` | Header | token | token | token | token | token | **删除** |

```python
def test_order_page(self, base_url, auth_headers, case):
    url = f"{base_url}/api/monitor/order/page"
    headers = self._headers(auth_headers, case)
    params = {}
    for key_name in ("orderStatus", "page", "pageSize"):
        if key_name in case:
            params[key_name] = case[key_name]
    res = http.send_request("get", url, params=params, headers=headers,
                            case_name=case["name"], log_level="none")
    json_data = res.json()
```

正向：`code=0`；分页路径 **探针后钉进 §5**（候选 `$.data.items` / `$.data.records` / `$.data.list`，商城 usage 是 `items`）。空页允许。

`orderStatus=UNPAID` 且 `code==0` 且列表非空时：挑 `productType=="COMMUNICATION_COMBO"` 的第一条（没有则退回列表第一条），写入 `eo_page_order_no`。

若请求带了 `orderStatus` 且列表非空：每条 `orderStatus` 必须等于请求值。

### 2.2 GET `/order/detail` — `TestEo02Detail.test_order_detail`

**怎么传：** query `orderNo` **必填**（OAS required）。

| HTTP 参数 | 位置 | 正向-商城单号 | 正向-分页抽出 | 负向-缺 orderNo | 负向-假单号 | 负向-无 Token |
|-----------|------|---------------|---------------|-----------------|-------------|---------------|
| `orderNo` | query | `{{combo_order_no}}` | `{{eo_page_order_no}}` | **不传该键** | 字面量 `0` | 字面量假值 |
| `Authorization` | Header | token | token | token | token | **删除** |

YAML 两条正向都写占位符；`required=True`，缺键 skip（单跑本类、商城没跑、page 又空时预期如此）。

正向 `code==0` 后：

- `$.data.orderNo` == 请求的 `orderNo`
- `$.data.orderStatus` 存在（商城刚下的单预期 `UNPAID`，**仅当**来源是 `{{combo_order_no}}` 时锁 `UNPAID`；分页抽出的单可能已被人改状态，只锁非空枚举）
- 若 `productType` 返回：商城单号那条锁 `COMMUNICATION_COMBO`
- 若有 `emergencyUserCombo` 且非空：`[0].addr` 非空即可（本批不强制等于本 session 新棒——商城单才是新棒）
- OAS `orderExpireTime` 类型是 **int64**，商城 buy 响应里是 **字符串时间**。detail 以探针为准，禁止按 buy 的字符串格式臆造断言

### 2.3 POST `/order/cancel` — `TestEo03Cancel.test_order_cancel`

**怎么传：** **POST + `params={"orderNo": ...}`**，body 为空。OAS 无 JSON schema。

| HTTP 参数 | 位置 | 正向-套餐自造单 | 正向-星豆自造单 | 负向-缺 orderNo | 负向-假单号 | 负向-无 Token |
|-----------|------|-----------------|-----------------|-----------------|-------------|---------------|
| `orderNo` | query | `{{eo_lifecycle_order_no}}` | `{{eo_lifecycle_star_bean_order_no}}` | **不传** | 字面量 | 字面量 |
| `Authorization` | Header | token | token | token | token | **删除** |

正向前按 YAML 占位符分流：套餐 case 调 `_ensure_lifecycle_order(...)`；星豆 case 调 `_ensure_lifecycle_star_bean_order(...)`。缺对应 lifecycle 单 → skip **该 case**，不要连坐另一条正向。

正向成功后同方法副作用（不另开 YAML）：

1. GET detail 同一 `orderNo`，`orderStatus==CANCELLED`（枚举名以探针为准，可能是文案「已取消」只出现在 `orderStatusName`）
2. **不要**再 cancel `combo_order_no` / `star_bean_order_no`

重复取消：探针若稳定（二次 cancel 明确码），可加一条负向「已取消再取消」用**套餐** lifecycle 单；不稳定则不加。星豆二次 cancel 探针顺带记，默认不加第二条负向。

### 2.4 DELETE `/order/delete` — `TestEo04Delete.test_order_delete`

**怎么传：** **DELETE + `params=`**。

删除对象 **探针 S6 拍板**，禁止猜：

| 探针结论 | 正向怎么做 |
|----------|------------|
| 只能删 `CANCELLED` / `EXPIRED` | 读已 cancel 的 `eo_lifecycle_order_no` / `eo_lifecycle_star_bean_order_no`；若对应 03 没跑 → skip 该条 |
| 未支付可直接删 | **§5 已钉：UNPAID 与 CANCELLED 都能删。** 本批 **03 先 cancel、04 删已取消单**，禁止再 buy 一张去测 UNPAID delete |
| 都不能删（业务拒绝） | 正向降级为负向，YAML 锁探针码；停下来问主人 |

负向：缺 `orderNo`、假单号、无 token。假单号字面量。

正向成功后再 GET detail：预期非 0（已不存在）或 page UNPAID/CANCELLED 不再含该 `orderNo`。以探针为准。

### 2.5 GET `/order/payment` 与 wx applet — 本批无 Test 类

覆盖缺口标了资金风险。主人拍板自动化不完成支付。

- Task 0 允许 **手工/临时脚本** 对一张**即将被本文件 cancel 的自造单** GET `payMethod=WECHAT`，只记 `code/msg/data` 形态（是否 URL / 是否改 `orderStatus`）
- **禁止**把该请求写进正式 YAML 正向
- `payment/wx/applet` GET deprecated、POST 要 `loginCode`：正式用例不写
- 若主人以后要「只验二维码字符串非空、不扫码」，另开任务，不在 Task 1–6

### 2.6 本文件自造待支付单（非被测接口，禁止拆 Test 类）

`_EoHelpers.ensure_lifecycle_order`（套餐，`productType=COMMUNICATION_COMBO`）：

1. 已有 `eo_lifecycle_order_no` → return
2. `combo_id = resolve_extract_value("{{combo_mall_id}}", required=False)`；没有则 GET `/emergency/combo/mall?packageType=COMBINATION&terminalType=TT_RESCUE_STICK`，日包最低价（与商城 extract 规则相同），没有日包 → skip
3. POST `/emergency/combo/buy`，`json={"terminalType":"TT_RESCUE_STICK","addrs":[sn],"emergencyComboId": combo_id}`
4. `code==0` 且 `$.data.orderNo` 非空 → **只** `write_yaml(..., {"eo_lifecycle_order_no": order_no})`。**禁止** `register_unpaid_order_no`（Eo03/Eo04 会吃掉；再登记 = 双重清除）
5. `999` 下单过于频繁 → skip（不要改去 cancel 商城单）

`_EoHelpers.ensure_lifecycle_star_bean_order`（星豆，`productType=STAR_BEAN`）：

1. 已有 `eo_lifecycle_star_bean_order_no` → return
2. **不读** `star_bean_order_no` / 套餐 extract；**不依赖** `rescue_sat_terminal`
3. POST `/star-bean/buy`，`json={"amount": 1}`（星豆计划现网金额范围曾是 1～1 元；不要抄套餐 `addrs`）
4. `code==0` 且 `$.data.orderNo` 非空 → **只** `write_yaml(..., {"eo_lifecycle_star_bean_order_no": order_no})`。**禁止** `register_unpaid_order_no`
5. `999` 下单过于频繁 → skip（星豆模块刚 buy 过时很常见；不要 sleep 硬等，不要改去 cancel `star_bean_order_no`）

只在 `TestEo03Cancel` 对应正向 `code` 断言之前调用。delete 正向只 `resolve_extract_value` 对应键 `required=True`。

---

## 3. YAML 文件头与样例

路径：`yaml/test_emergency_order_controller.yaml`。顶层 key 必须 `_cases` 结尾，一类一 key。

```yaml
# yaml/test_emergency_order_controller.yaml
# 应急套餐订单：page / detail / cancel / delete
# {{combo_order_no}} 由商城 TestEcm05 写入，本文件只读、禁止用例内 cancel/delete 该单
# {{eo_page_order_no}} 由 page 正向-UNPAID 写入
# {{eo_lifecycle_order_no}} / {{eo_lifecycle_star_bean_order_no}} 由 helper buy 写入；不 register_unpaid_order_no
# {{rescue_sat_terminal}} 由 _EoHelpers 注入，不走 extract
# 负向 orderNo 一律字面量；负向码探针后填

emergency_order_page_cases:
  - name: "套餐订单-分页-正向-无过滤"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-分页-正向-UNPAID"
    orderStatus: "UNPAID"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-分页-正向-CANCELLED"
    orderStatus: "CANCELLED"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-分页-负向-orderStatus非法"
    orderStatus: "FOO"
    expected:
      code: 1001          # 探针后改
      error_msg: "待填"

  - name: "套餐订单-分页-负向-缺token"
    orderStatus: "UNPAID"
    no_auth: true
    expected:
      code: 3001          # 探针后改
      error_msg: "待填"

emergency_order_detail_cases:
  - name: "套餐订单-详情-正向-商城待支付单"
    orderNo: "{{combo_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-详情-正向-分页抽出单"
    orderNo: "{{eo_page_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-详情-负向-缺orderNo"
    expected:
      code: 1001
      error_msg: "待填"

  - name: "套餐订单-详情-负向-假orderNo"
    orderNo: "0"
    expected:
      code: 1001          # 探针后改（可能 0 空 data 或 999）
      error_msg: "待填"

  - name: "套餐订单-详情-负向-缺token"
    orderNo: "0"
    no_auth: true
    expected:
      code: 3001
      error_msg: "待填"

emergency_order_cancel_cases:
  - name: "套餐订单-取消-正向-套餐自造单"
    orderNo: "{{eo_lifecycle_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-取消-正向-星豆自造单"
    orderNo: "{{eo_lifecycle_star_bean_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-取消-负向-缺orderNo"
    expected:
      code: 1001
      error_msg: "待填"

  - name: "套餐订单-取消-负向-假orderNo"
    orderNo: "0"
    expected:
      code: 1001
      error_msg: "待填"

  - name: "套餐订单-取消-负向-缺token"
    orderNo: "0"
    no_auth: true
    expected:
      code: 3001
      error_msg: "待填"

emergency_order_delete_cases:
  - name: "套餐订单-删除-正向-套餐生命周期单"
    orderNo: "{{eo_lifecycle_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-删除-正向-星豆生命周期单"
    orderNo: "{{eo_lifecycle_star_bean_order_no}}"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐订单-删除-负向-缺orderNo"
    expected:
      code: 1001
      error_msg: "待填"

  - name: "套餐订单-删除-负向-假orderNo"
    orderNo: "0"
    expected:
      code: 1001
      error_msg: "待填"

  - name: "套餐订单-删除-负向-缺token"
    orderNo: "0"
    no_auth: true
    expected:
      code: 3001
      error_msg: "待填"
```

实现时把所有 `待填` 换成 §5 探针值。分页边界（`page=0` / `pageSize=0`）探针后再决定加不加，不预写。

---

## 4. 第 0 节：现网探针（先于 YAML 定稿）

用当前 web 测试账号。生命周期探针用一根 `rescue_sat_terminal` 造套餐单 + 一次星豆 `amount=1` 造充值单，**不要** cancel 账号里未登记的历史单。

| ID | 请求 | 要记下的 |
|----|------|----------|
| S1 | page 无过滤；page `orderStatus=UNPAID` / `CANCELLED` / `PAID` | jsonpath；空页是否 code=0；UNPAID 里是否混 `STAR_BEAN`；`orderStatus` 过滤是否严格 |
| S2 | page `orderStatus=FOO`；page 无 token | 真实 code/msg |
| S3 | page `page=0` / `page=-1` / `pageSize=0` / `pageSize=10000` | 与商城 usage 是否同口径 |
| S4 | 有 UNPAID 则 detail 真 `orderNo`；再打缺 `orderNo`、`orderNo=0`、无 token | 假单号是 1001 还是 0+空；`orderExpireTime` 是毫秒还是字符串；`emergencyUserCombo` 是否出现 |
| S5 | 本文件口径 buy 一张最低价日包（**不要**随后 payment） | 新 `orderNo`；page UNPAID 能否命中；detail `orderStatus` / `productType=COMMUNICATION_COMBO` |
| S5b | `POST /star-bean/buy` `json={"amount":1}`（**不要**随后 payment） | 新 `orderNo`；page 是否混入 `STAR_BEAN`；detail `productType` |
| S6 | 对 S5 套餐单 cancel；再 detail；再二次 cancel。对 S5b 星豆单再 cancel 一次 | 一次成功码；二次码；detail 是否 `CANCELLED`；两种 productType 是否同一套码 |
| S7 | 对已取消的套餐单、星豆单各 delete；必要时再买一张试「未支付直接 delete」 | **二选一写进 §5**（套餐与星豆同一规则）；delete 后 detail/page 表现 |
| S8 | （可选，用即将 delete 的单）GET payment `payMethod=WECHAT` | 是否改状态；data 形态。打完仍走 S6/S7 清掉。**禁止**扫码 |

没有 S1–S7（含 S5b）禁止把负向文案写成死的。S8 默认不进正式用例。

---

## 5. 现网基线（2026-08-18 探针）

| 项 | 结论 |
|----|------|
| Token 位置 | **只 Header**；无 token → `3001 没有访问权限` |
| page 分页路径 | `$.data.items` + `total` + `totalPage`；空页 `code=0`（当时 UNPAID total=0） |
| 无过滤混单 | 合法：同页可同时有 `COMMUNICATION_COMBO` 与 `STAR_BEAN` |
| `orderStatus` 过滤 | 严格：UNPAID/CANCELLED/PAID 列表内状态均等于请求值 |
| 缺参 / 非法枚举 / 假 orderNo / 无 token | 见下分接口 |
| 分页边界 | `page=0` / `page=-1` → `0 成功`（**不加 case**）；`pageSize=0` → `999 失败`（负向已写）；`pageSize=10000` → `0 成功`（不加） |
| detail `orderExpireTime` 形态 | **字符串** `yyyy-MM-dd HH:mm:ss`（与 buy 一致，不是 int64 毫秒） |
| cancel 一次 / 二次 | 一次 `0 成功`；二次 `999 订单状态异常，请稍后重试`（星豆实测；套餐与星豆同一接口，YAML 用套餐 lifecycle 锁二次码） |
| delete 前置状态 | **未支付可直接删**（套餐 UNPAID delete `0`）；**已取消也可删**（星豆 CANCELLED delete `0`）。本批 **Eo03 先 cancel、Eo04 删已取消单**，不再为 UNPAID 另买一张 |
| delete 后 detail | `999 订单不存在，请刷新页面重试` |
| payment GET 是否改 UNPAID | 正式用例不写正向（S8 未打） |

**page / detail / cancel / delete 负向码（字面量假单号 `0`）：**

| 接口 | 缺 orderNo / 缺参 | `orderNo=0` | 无 token |
|------|-------------------|-------------|----------|
| page `orderStatus=FOO` | `1001 未知参数错误` | — | `3001 没有访问权限` |
| detail | `1001 请检查请求参数是否正确` | `999 订单不存在，请刷新页面重试` | `3001 没有访问权限` |
| cancel | `1001 请检查请求参数是否正确` | `999 订单不存在，请刷新页面重试` | `3001 没有访问权限` |
| delete | `1001 请检查请求参数是否正确` | `999 订单不存在，请刷新页面重试` | `3001 没有访问权限` |

---

## 6. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/emergency-combo-order-tests.plan.md` | 本文 |
| `yaml/test_emergency_order_controller.yaml` | `emergency_order_page_cases` / `_detail_cases` / `_cancel_cases` / `_delete_cases` |
| `testcases/test_emergency_order_controller.py` | `TestEo01`–`04` + `_EoHelpers`；page 写 `eo_page_order_no`；helper 只写 `eo_lifecycle_order_no` + `eo_lifecycle_star_bean_order_no`（**不** `register_unpaid_order_no`）；可读商城 `combo_order_no` 做 detail |
| `common/cleanup/unpaid_order.py` | session 收**登记表**（商城/星豆）；本文件不调用 |

**不要**为本模块再挂一份 teardown，也**不要**把 lifecycle 单登进登记表。商城/星豆的收尾仍走现有 `cleanup_test_data`。

### 任务

- [x] **Task 0** 探针 S1–S7（含 S5b 星豆 buy；S8 未做），填 §5；YAML 里所有 `待填` 换成实测值  
  - 验收：负向码、分页路径、delete 前置状态已填；**未**对未登记历史单 cancel
- [x] **Task 1** YAML + `TestEo01Page` + `_EoHelpers` 骨架（含 `resolve_order_no` / `_headers`）  
  - 验收：page 按探针通过；UNPAID 非空则 extract 有 `eo_page_order_no`
- [x] **Task 2** `TestEo02Detail`  
  - 验收：有 `combo_order_no` 时商城单号那条过；两条占位都缺则 skip 不是 fail
- [x] **Task 3** `ensure_lifecycle_order` + `ensure_lifecycle_star_bean_order` + `TestEo03Cancel`  
  - 验收：正向两条分别 cancel `eo_lifecycle_*`；helper **未**调用 `register_unpaid_order_no`；`combo_order_no` / `star_bean_order_no` 用例内未被本类 cancel
- [x] **Task 4** `TestEo04Delete`（按 §5：03 先 cancel、04 删已取消单；套餐与星豆各一条正向）  
  - 验收：两张生命周期单 delete 后 detail `999`；缺对应键 skip 该条
- [x] **Task 5** 整文件回归（2026-08-18：`20 passed, 2 skipped`；skip 为 detail 两条占位缺 extract；清理报告无 unpaid_orders）  
  - 验收：collect 含 01→04，叶子 `[case0]`；无 payment / wx applet 类；lifecycle 不进登记表

---

## 7. 仍不敢装懂、需要现网说话的点

1. 无 token 是 3001 还是 999（本仓库两种现网都有）。
2. 假 `orderNo=0`：参数校验失败还是「查无此单仍成功」。
3. `orderExpireTime` OAS int64 vs buy 字符串。
4. 未支付能否 delete；已支付 / 退款中 delete 的码（本批不造 PAID）。
5. cancel 是否把套餐 info 的 `status=0` 记录一并去掉（副作用 GET info 可记入 §5，**不要**写成必须 status 变化——未支付套餐记录语义以探针为准）。
6. 连续 buy `999` 过于频繁：本文件套餐买 1 次、星豆买 1 次；与商城/星豆同 session 时已有各自 buy，本文件再买可能踩限流 → helper 遇 999 就 skip，不要改去动 `combo_order_no` / `star_bean_order_no`。

---

## 8. 与商城 / 星豆模块的关系

- 共用账号、共用 `extract.yaml`、共用 `rescue_sat_terminal` fixture 实现。
- 商城 / 星豆文件 **用例内** 不读各自 orderNo、**不** cancel；buy 成功后 `register_unpaid_order_no`（session 统一收）。
- 本文件 **可以** 读 `combo_order_no` 做 detail（只读不改状态）；cancel/delete **只用** 自己的 `eo_lifecycle_order_no` 与 `eo_lifecycle_star_bean_order_no`，且这两张 **不登记**。
- page 可能出现星豆充值单（`productType=STAR_BEAN`）。不要当失败。detail 商城单号那条才锁 `COMMUNICATION_COMBO`。
- session 末只按登记表收商城 1 张 + 星豆最多 2 张。lifecycle 由 Eo03/Eo04 闭环。要留商城/星豆单扫码：`ENABLE_AUTO_CLEANUP=false`（lifecycle 仍会被本文件 cancel/delete）。
- 人扫码付完之后的 PAID / 开通守恒，另开串测，不在本文。
