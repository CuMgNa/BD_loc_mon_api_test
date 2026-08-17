# 应急套餐商城接口测试 Implementation Plan

> **For agentic workers:** 先做第 0 节探针，**禁止**在探针前把 YAML `expected.code/msg` 写成臆测值。实现时遵循 `skills/api-test-framework`（只 `from common.*`、模式 A/B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result`）。一类一接口，叶子用默认 `[case0]`，**禁止**中文 `parametrize ids`。每个接口的 query / json / 示例 `send_request` 以本文 §2 为准。
>
> 来源：Apifox tag `应急套餐商城`；覆盖缺口 [api-automation-coverage-gap.plan.md](./api-automation-coverage-gap.plan.md) §4.1 B
> 契约：Apifox「Swagger3接口文档」刷新时间 **2026-08-17T09:08:33.807Z**
> 主人拍板（2026-08-17）：5 口都做；buy 现网是**待支付订单**不是当场扣费；设备用 `rescue_sat_terminal`（`TT_RESCUE_STICK`）；buy **本批可跑**，只校验订单是否生成；二维码支付由人在订单模块补，自动化不调 payment

**Goal:** 5 个应急套餐商城接口：4 个查询 + 订购生成待支付订单（断言 `orderNo`）。不支付、不扣星豆、不测开通后扣量。

**Architecture:** 模式 A（4 个 GET，`params=`）+ 模式 B′（mall 提取 `combo_mall_id` → buy `json=` → extract `combo_order_no` 只留给人工扫码，本文件不读）。**默认不 cancel**。设备 addr 走已有 fixture。

**Tech Stack:** pytest + YAML + `BaseRequest` + Allure（与围栏/求救群聊同一套）

## Global Constraints

- 只 `from common.*`；禁止 `api_test_framework` / 模式 C
- Authorization：OAS 写 **query required**；求救群聊现网常 header+query。**默认只 Header**；探针锁定后全文统一，YAML 不写真实 token
- 正向 `expected.msg`，负向 `expected.error_msg`；禁止正向写 `error_msg: "成功"`
- `no_auth: true` 只剥 `Authorization`，保留 `Accept-Language`
- YAML 不写真实卡号/密码；addr 用 `{{rescue_sat_terminal}}` 由 testcase 注入（fixture 字符串，**不要** `resolve_extract_value`）
- 不测 `order/payment*`、不测 `star-bean/*`（别的 tag）；支付由人用二维码在订单侧完成
- buy 正向只断言「生成了待支付订单」（`orderNo` 非空）；**禁止**断言已扣费、套餐 status=1
- **禁止**用 `payAmount` 去和星豆余额比较（OAS 描述是「实付金额（元）」；星豆流水不在本 tag，也无法在本模块证明「未扣费」）
- 正向 buy **不自动 cancel**（要把单留给人工支付）；负向失败无单则无需清理
- `json_data = res.json()` 每个请求只调一次；`send_request(..., log_level="none")`；需要日志时用 `sep` / `print_request` / `print_response` / `key`
- 方法签名一律注入 `base_url, auth_headers, case`；需要设备号时再加 `rescue_sat_terminal`

---

## 0. 范围、执行顺序、session 副作用

Apifox tag **应急套餐商城** 恰好 5 个 URL（刷新后未增删）：

| 序 | 类名 | 方法 | 路径 | OAS summary | 本批 |
|----|------|------|------|-------------|------|
| 1 | `TestEcm01Mall` | GET | `/api/monitor/emergency/combo/mall` | 套餐商城列表（日包、月包） | 做 |
| 2 | `TestEcm02ComboInfo` | GET | `/api/monitor/emergency/combo/chat/item/info` | 我的套餐信息 | 做 |
| 3 | `TestEcm03Remaining` | GET | `/api/monitor/emergency/combo/chat/item/remaining` | 群聊套餐余额与最新情况 | 做 |
| 4 | `TestEcm04UsagePage` | GET | `/api/monitor/emergency/combo/usage/page` | 套餐使用明细分页 | 做 |
| 5 | `TestEcm05Buy` | POST | `/api/monitor/emergency/combo/buy` | 订购 | **做（只验下单）** |

文件内类定义顺序必须 01→05。`TestEcm02` 在 buy **之前**跑，**不能**用来验证刚下的待支付单。

**明确不做（本计划全文）：**

- tag `应急套餐订单接口` 当被测：`order/page`、`detail`、`payment*`、`delete`、`cancel`
- tag 星豆：`star-bean/buy`、`package/active`、流水（因此 **S8/正向都不能证明「未扣费」**，只能证明返回了 `orderNo`）
- 求救群聊 `emergency/chat/*`
- 自动化扫码/微信支付；开通后的余量扣减守恒
- 本文件 **禁止** `resolve_extract_value("{{combo_order_no}}")`，禁止拿订单号去打 remaining / info / usage（那不是套餐 id，也不是已支付凭证）

**session 副作用（不改 `conftest.py`，但单跑本文件仍会发生）：**

- session `autouse` 的 `cleanup_test_data` 依赖 `group_fixture` → 登录 + 建三级分组，session 末再清
- 注入 `rescue_sat_terminal` 的类（info 带 addr、remaining、usage、buy）会再 **入库一根救援棒**。不是 SOS 群（`emergency_chat_item`），但会造数
- 单跑 `TestEcm01Mall`：不入棒，仍会建分组
- 单跑 `TestEcm05Buy`：无 `combo_mall_id` 时 **skip**（不是 fail）；collect/IDE 只跑该类时预期如此

---

## 1. 三条传值通道

和技能一致：**fixture / extract.yaml / YAML 字面量**。禁止在 YAML 写真实设备号、真实 URL、明文 token。

### 通道 A — Fixture（方法参数注入）

| Fixture | 给谁用 | 怎么用 |
|---------|--------|--------|
| `base_url` | 所有请求拼 URL | 前缀 `{base_url}/api/monitor` |
| `auth_headers` | 所有请求 Header | `headers = {**auth_headers}`；`no_auth: true` 时 **只去掉** `Authorization` |
| `rescue_sat_terminal` | info 带 addr、remaining、usage 带 addr、buy 的 `addrs` | 返回 12 位 sn。YAML 写 `{{rescue_sat_terminal}}`，Python **字符串相等替换**，**不要** `resolve_extract_value` |

mall 正向/负向不需要 sn，方法可以不注入该 fixture。

默认 **Authorization 只放 Header**。若联调 401/3001，再把同一 token **同时**放进 `params["Authorization"]`，并记入 §6。

### 通道 B — extract.yaml（同文件写入，testcase 读）

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `combo_mall_id` | **仅** `TestEcm01Mall` 正向，且满足下面「只写一次」规则 | `TestEcm05Buy` 正向 `emergencyComboId` | 救援棒日包 id |
| `combo_order_no` | `TestEcm05Buy` 正向 `code==0` | **本文件无人读** | 给人扫码；别的模块/人工用 |

写入（仅 testcase，禁止 conftest）：

```python
write_yaml("./extract.yaml", {"combo_mall_id": combo_id}, mode="append")
# buy 成功后再：
write_yaml("./extract.yaml", {"combo_order_no": order_no}, mode="append")
```

读取（buy 正向）：

```python
combo_id = resolve_extract_value(case.get("emergencyComboId"), required=is_extract_placeholder(case.get("emergencyComboId")))
```

- YAML 整段 `{{combo_mall_id}}` → extract；缺失且 `required=True` → `pytest.skip`
- 假 id 负向用字面量（如 `0` 或 `999999999`），不读 extract

**`combo_mall_id` 只写一次（禁止三种 packageType 互相覆盖）：**

1. YAML `mall_cases` 顺序必须：`COMBINATION` 带类型 → `POSITION` 带类型 → `SHORT_MESSAGE` 带类型 → 正向-不带 `terminalType` → 负向。
2. **只**在「带 `terminalType=TT_RESCUE_STICK`」且 `code==0` 且 `dailyPackages` **非空** 时考虑写入。
3. 从该次响应的日包里取 **最低价** `id`（`servicePeriod==0`；价格字段 `price`）。
4. extract 里 **已有** `combo_mall_id` 则不再写（第一次成功的带类型日包赢；按 YAML 序即优先 COMBINATION）。
5. **禁止**从「不带 terminalType」那条写入（避免买到非救援棒套餐再配 `TT_RESCUE_STICK`）。
6. **禁止**日包空、月包有货时改用月包。三种带类型都无日包 → 不写 extract；buy 正向 `skip`。
7. 禁止 YAML 写死套餐 ID。

### 通道 C — YAML 字面量 + 运行时替换

字段名与 OAS **驼峰一致**，禁止 `package_type` / `emergency_combo_id`：

| YAML 字段 | 含义 |
|-----------|------|
| `name` | **只做标题**，不发给接口 |
| `packageType` | mall：`COMBINATION` / `POSITION` / `SHORT_MESSAGE`；缺省 case 不写该键 |
| `terminalType` | mall 可选；buy 必填 `TT_RESCUE_STICK` |
| `addr` | info / remaining / usage；`{{rescue_sat_terminal}}` 或假值 |
| `status` | info：`0` / `1` / `2` |
| `showMyBuy` | info；探针无差异则不要凑数 |
| `page` / `pageSize` | usage 分页 |
| `emergencyUserComboId` | **仅** usage 负向假值；本批正向 **不传**（没支付就没有使用中套餐 id） |
| `addrs` | buy JSON 数组；正向 `["{{rescue_sat_terminal}}"]` |
| `emergencyComboId` | buy：正向 `{{combo_mall_id}}`；负向字面量假 id |
| `no_auth` | `true` 时剥 token |
| `expected.code` / `expected.msg` / `expected.error_msg` | 正向 msg、负向 error_msg |

---

## 2. 接口参数传递（每个接口：放哪 / 传什么 / 代码形态）

公共 URL 前缀：`{base_url}/api/monitor`。  
四个 GET **全部 `params=`**，禁止抄成 JSON body。  
buy **必须 `json=`**，禁止把 `addrs` / `emergencyComboId` 放进 query。

### 2.1 GET `/emergency/combo/mall` — `TestEcm01Mall.test_mall`

**怎么传：** 业务参数全在 **query**。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 ×3 带类型 | 正向-不带类型 | 负向-缺 packageType | 负向-非法 | 负向-无 Token |
|-------------|------|----------|----------------|---------------|---------------------|-----------|---------------|
| `packageType` | query | YAML | COMBINATION / POSITION / SHORT_MESSAGE | 同左（仍传一种，建议 COMBINATION） | **不传该键** | `FOO` | 任意合法值 |
| `terminalType` | query | YAML | `TT_RESCUE_STICK` | **不传该键** | 带或不带均可 | 带 | 带 |
| `Authorization` | Header | fixture | token | token | token | token | **删除** |

```python
def test_mall(self, base_url, auth_headers, case):
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    params = {}
    if "packageType" in case:
        params["packageType"] = case["packageType"]
    if case.get("terminalType"):
        params["terminalType"] = case["terminalType"]
    res = http.send_request(
        "get", f"{base_url}/api/monitor/emergency/combo/mall",
        params=params, headers=headers, case_name=case["name"], log_level="none",
    )
    json_data = res.json()
```

断言（探针后把负向码写入 YAML）：

- `assert_api_result` + `read_expected_msg`
- 正向结构：`$.data.dailyPackages`、`$.data.monthlyPackages` 存在且为 list（允许 `[]`）
- 列表非空则元素含 `id`、`price`、`servicePeriod`∈{0,1}
- 写入 extract 规则见 §1 通道 B

### 2.2 GET `/emergency/combo/chat/item/info` — `TestEcm02ComboInfo.test_combo_info`

**怎么传：** 参数全可选，都在 **query**。本类跑在 buy 之前，**不**验证刚下的待支付单。

| HTTP 参数名 | 位置 | 值从哪来 | 正向-无过滤 | 正向-按 addr | 正向-status | 负向-无 Token |
|-------------|------|----------|-------------|--------------|-------------|---------------|
| `addr` | query | fixture 替换 | 不传 | `{{rescue_sat_terminal}}` | 不传或同 addr | 任意 |
| `status` | query | YAML 字面量 | 不传 | 不传 | `0` / `1` / `2` 各一条 | 不传 |
| `showMyBuy` | query | YAML | 默认不传 | 不传 | 不传 | 不传 |
| `Authorization` | Header | fixture | token | token | token | **删除** |

```python
def test_combo_info(self, base_url, auth_headers, rescue_sat_terminal, case):
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    params = {}
    addr = case.get("addr")
    if isinstance(addr, str) and addr.strip() == "{{rescue_sat_terminal}}":
        params["addr"] = rescue_sat_terminal
    elif addr:
        params["addr"] = addr
    if "status" in case:
        params["status"] = case["status"]
    res = http.send_request(
        "get", f"{base_url}/api/monitor/emergency/combo/chat/item/info",
        params=params, headers=headers, case_name=case["name"], log_level="none",
    )
    json_data = res.json()
```

断言：

- 正向：`code=0`，`$.data` 为 list（**可空**）。空列表是合法正向，只锁 code/msg，日志标明「账号无套餐记录」
- **仅当列表非空** 且本 case 传了 addr：命中项 `addr` 应等于 sn。空列表时 **不要** 再断言命中 addr（两条规则不可同时强制）
- `showMyBuy`：探针有差异再加 case，没有就不要凑数

### 2.3 GET `/emergency/combo/chat/item/remaining` — `TestEcm03Remaining.test_remaining`

**怎么传：** `addr` 必填，**query**。本批正向 **不传** `chatItemId`（默认不绑 SOS 群）。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-缺 addr | 负向-假 addr | 负向-无 Token |
|-------------|------|----------|------|--------------|--------------|---------------|
| `addr` | query | fixture / 字面量 | `{{rescue_sat_terminal}}` | **不传** | `000000000000` | 救援棒 sn |
| `chatItemId` | query | — | **不传** | 不传 | 不传 | 不传 |
| `Authorization` | Header | fixture | token | token | token | **删除** |

```python
def test_remaining(self, base_url, auth_headers, rescue_sat_terminal, case):
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    params = {}
    addr = case.get("addr")
    if isinstance(addr, str) and addr.strip() == "{{rescue_sat_terminal}}":
        params["addr"] = rescue_sat_terminal
    elif "addr" in case:
        params["addr"] = addr
    res = http.send_request(
        "get", f"{base_url}/api/monitor/emergency/combo/chat/item/remaining",
        params=params, headers=headers, case_name=case["name"], log_level="none",
    )
    json_data = res.json()
```

正向结构（路径以探针为准，默认）：`allRemainingVoiceNumber`、`allRemainingPositionNumber`、`latestInfo` 可空/0。  
若探针证明必须有群才能 `code=0`：**停下来问**，勿擅自绑 `emergency_chat_item`。

### 2.4 GET `/emergency/combo/usage/page` — `TestEcm04UsagePage.test_usage_page`

**怎么传：** 全 **query**。本批正向 **只带 addr / 分页，不传 `emergencyUserComboId`**（info 虽有该字段，未支付通常没有「使用中」套餐；不要从 info 抽 id）。

| HTTP 参数名 | 位置 | 值从哪来 | 正向-默认分页 | 正向-addr | 边界 page | 负向-假 comboId | 负向-无 Token |
|-------------|------|----------|---------------|-----------|-----------|-----------------|---------------|
| `addr` | query | fixture | 不传或救援棒 | `{{rescue_sat_terminal}}` | 救援棒 | 不传 | 任意 |
| `page` | query | YAML | 不传（默认 1） | 不传 | `0` | 不传 | 不传 |
| `pageSize` | query | YAML | 不传（默认 100） | 不传 | 极大（如 `10000`） | 不传 | 不传 |
| `emergencyUserComboId` | query | YAML 字面量 | **不传** | **不传** | **不传** | 假值（如 `0`） | 不传 |
| `Authorization` | Header | fixture | token | token | token | token | **删除** |

```python
def test_usage_page(self, base_url, auth_headers, rescue_sat_terminal, case):
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    params = {}
    addr = case.get("addr")
    if isinstance(addr, str) and addr.strip() == "{{rescue_sat_terminal}}":
        params["addr"] = rescue_sat_terminal
    elif addr:
        params["addr"] = addr
    for key_name in ("page", "pageSize", "emergencyUserComboId"):
        if key_name in case:
            params[key_name] = case[key_name]
    res = http.send_request(
        "get", f"{base_url}/api/monitor/emergency/combo/usage/page",
        params=params, headers=headers, case_name=case["name"], log_level="none",
    )
    json_data = res.json()
```

正向：`code=0`；分页路径 **探针后钉进 §6**（候选 `$.data.items` / `$.data.records` / `$.data.list`）。空页允许。边界 case 不 5xx。

### 2.5 POST `/emergency/combo/buy` — `TestEcm05Buy.test_buy`

**怎么传：** **JSON body**（`json=`），不是 query。必须排在 mall 之后。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-缺 addrs | 负向-假 comboId | 负向-无 Token |
|-------------|------|----------|------|---------------|-----------------|---------------|
| `addrs` | JSON | fixture 替换数组 | `[rescue_sn]` | **不传或 `[]`** | `[rescue_sn]` | `[rescue_sn]` |
| `emergencyComboId` | JSON | extract / 字面量 | `{{combo_mall_id}}` | 合法 extract 或任意 | 字面量假 id | extract |
| `terminalType` | JSON | YAML | `TT_RESCUE_STICK` | 同左 | 同左 | 同左 |
| `Authorization` | Header | fixture | token | token | token | **删除** |

```python
def test_buy(self, base_url, auth_headers, rescue_sat_terminal, case):
    headers = {**auth_headers}
    if case.get("no_auth"):
        headers.pop("Authorization", None)
    addrs = case.get("addrs")
    if isinstance(addrs, list):
        addrs = [
            rescue_sat_terminal if (isinstance(x, str) and x.strip() == "{{rescue_sat_terminal}}") else x
            for x in addrs
        ]
    combo_id = case.get("emergencyComboId")
    if is_extract_placeholder(combo_id):
        combo_id = resolve_extract_value(combo_id, required=True)
    body = {"terminalType": case.get("terminalType") or "TT_RESCUE_STICK"}
    if addrs is not None:
        body["addrs"] = addrs
    if combo_id is not None:
        body["emergencyComboId"] = combo_id
    res = http.send_request(
        "post", f"{base_url}/api/monitor/emergency/combo/buy",
        json=body, headers=headers, case_name=case["name"], log_level="none",
    )
    json_data = res.json()
```

正向断言：

- `code=0` 且 `$.data.orderNo` 非空（路径以 S8 为准，默认这条）
- 写入 `combo_order_no`；本文件后续 **不再读取**
- 可选：`payAmount` 为数字、`productType` 若返回则含 `COMMUNICATION_COMBO`
- **不要**断言 remaining/info 变成「使用中」
- **不要**调 payment / cancel / 星豆流水来证明未扣费

**buy 之后要不要查 info（消掉 S8 与类序矛盾）：**

- `TestEcm02` 不承担「刚下的单」。
- 实现 **默认**：正向只锁 `orderNo`，**同方法内不要再 GET info**。
- 仅当 §6 写明「buy 后 info `status=0`+`addr=sn` 能看到该单」时，才在 `TestEcm05` 正向成功后 **同方法副作用** 再 GET 一次 info（不另开 YAML case、不改类序）。
- 探针 S8 负责回答能不能看到；在填 §6 之前禁止把这条写成必过断言。

不做：payment、cancel、幂等连订（S8 若稳定再加，默认不加）。

---

## 3. YAML 文件头与样例

路径：`yaml/test_emergency_combo_controller.yaml`。顶层 key 必须 `_cases` 结尾。负向 `code`/`error_msg` **探针后填**，下面正向 `msg: "成功"` 是本仓库常见值，S1 若不同则改 YAML 与 §6。

```yaml
# yaml/test_emergency_combo_controller.yaml
# combo_mall_id：仅第一条「带 TT_RESCUE_STICK 且日包非空」的 mall 正向写入
# {{rescue_sat_terminal}} 由 testcase 注入 fixture，不走 extract
# {{combo_mall_id}} 整段占位才 resolve_extract_value
# combo_order_no 只写不读

mall_cases:
  - name: "套餐商城-列表-正向-COMBINATION-救援棒"
    packageType: "COMBINATION"
    terminalType: "TT_RESCUE_STICK"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐商城-列表-正向-POSITION-救援棒"
    packageType: "POSITION"
    terminalType: "TT_RESCUE_STICK"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐商城-列表-正向-SHORT_MESSAGE-救援棒"
    packageType: "SHORT_MESSAGE"
    terminalType: "TT_RESCUE_STICK"
    expected:
      code: 0
      msg: "成功"

  - name: "套餐商城-列表-正向-不带终端类型"
    packageType: "COMBINATION"
    expected:
      code: 0
      msg: "成功"

  # 负向-缺 packageType / 非法 FOO / 无 token：等 S3/S4 回填 §5 后再写 code 与 error_msg，禁止臆造

buy_cases:
  - name: "套餐商城-订购-正向-待支付订单"
    addrs:
      - "{{rescue_sat_terminal}}"
    emergencyComboId: "{{combo_mall_id}}"
    terminalType: "TT_RESCUE_STICK"
    expected:
      code: 0
      msg: "成功"
```

`combo_info_cases` / `remaining_cases` / `usage_page_cases` 按 §2 意图补全；`no_auth: true` 的 case 不要依赖 extract。

---

## 4. 第 0 节：现网探针（先于 YAML 定稿）

用当前 web 测试账号 + `rescue_sat_terminal` 的 sn，手工或临时脚本打一遍（结果回填 §6，再写负向 expected）：

| ID | 请求 | 要记下的 |
|----|------|----------|
| S1 | mall `packageType=COMBINATION`，不带 / 带 `terminalType=TT_RESCUE_STICK` | code/msg；日包月包是否空；套餐 `id` 样例；token 只 header 是否 3001 |
| S2 | mall `POSITION`、`SHORT_MESSAGE` 各一次（带救援棒类型） | 是否空列表仍 code=0；**有无日包**（决定 extract 会不会轮到该类型） |
| S3 | mall 缺 `packageType`、非法值 `FOO` | 真实 code/msg |
| S4 | mall 无 token | 是否 3001「没有访问权限」（勿假设，complete/addr 无 token 曾是 999） |
| S5 | info 无过滤；info `addr=sn`；info `status=0/1/2` | 列表是否空；字段是否出现（**此时尚未 buy**，空列表合法） |
| S6 | remaining 仅 `addr=sn`；再试缺 addr；再试假 addr | **是否必须 chatItemId** |
| S7 | usage 默认分页 + `addr=sn`（**不传** emergencyUserComboId） | 空页是否 code=0；分页 jsonpath；page=0 / pageSize 极大 |
| S8 | buy 最低价日包 × 1 个救援棒 addr（**不要**随后 cancel） | code/msg；`orderNo` 字段路径；**随后** GET info `addr=sn&status=0` 能否看到该单（只记结论，不在此步调星豆） |

没有 S1–S8 禁止把 YAML 负向文案写成死的。S8 与实现可同一轮：先打通正向再补负向码。

---

## 5. 现网基线（探针后填）

| 项 | 结论 |
|----|------|
| Token 位置 | _待填：header / query / 两者_ |
| mall 三种 packageType × 救援棒 | _待填：空还是有货；哪种有日包_ |
| 缺 packageType / 非法枚举 code,msg | _待填_ |
| 无 token code,msg | _待填_ |
| remaining 无群是否成功 | _待填_ |
| usage 空页路径 | _待填 jsonpath（items / records / list）_ |
| buy 正向 orderNo 路径 / 负向码 | _待填；默认试 `$.data.orderNo`_ |
| buy 后 info `status=0` 能否看到该单 | _待填：能 → TestEcm05 加副作用 GET；不能/未测 → 只锁 orderNo_ |

---

## 6. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/emergency-combo-mall-tests.plan.md` | 本文 |
| `yaml/test_emergency_combo_controller.yaml` | `mall_cases` / `combo_info_cases` / `remaining_cases` / `usage_page_cases` / `buy_cases` |
| `testcases/test_emergency_combo_controller.py` | `TestEcm01`–`05`；mall 按规则写 `combo_mall_id`；buy 写 `combo_order_no`（不读） |

**不要**为了本模块去改 `conftest.py`，除非探针证明缺 fixture（当前不缺）。

### 任务

- [ ] **Task 0** 探针 S1–S8（S8 不要 cancel），填 §5  
  - 验收：负向码、orderNo 路径、buy 后 info 是否可见已填
- [ ] **Task 1** YAML + `TestEcm01Mall`（顺序与 extract 只写一次按 §1）  
  - 验收：该类按探针通过；有日包则 extract 有 `combo_mall_id` 且不被后两条覆盖
- [ ] **Task 2** `TestEcm02ComboInfo`（空列表只锁 code，不强制 addr）
- [ ] **Task 3** `TestEcm03Remaining`（若必须 SOS 群则停下来问，勿擅自绑 `emergency_chat_item`）
- [ ] **Task 4** `TestEcm04UsagePage`（正向不传 `emergencyUserComboId`）
- [ ] **Task 5** `TestEcm05Buy`：`json=`；正向验 `orderNo`；不 payment、不 cancel、不读 `combo_order_no`  
  - 验收：extract 有 `combo_order_no`；全文件 collect 含 01→05，叶子 `[case0]`；无 mall id 时 skip
- [ ] **Task 6** 整文件回归（含一次真实 buy）

---

## 7. 仍不敢装懂、需要现网说话的点

1. 救援棒在商城三种 `packageType` 是否都上架（空列表 ≠ 接口失败）；哪种有日包决定 extract 写谁。
2. `remaining` / `info` 是否隐含「必须先有求救群」。
3. 无 token 是 3001 还是 999（本仓库已有两种现网）。
4. buy 响应里订单号字段是否一定是 `$.data.orderNo`（以 S8 为准）。
5. 重复跑正向 buy 会堆未支付单——接受；不要为干净账号自动 cancel。
6. 未付款单是否出现在 info `status=0`（决定 TestEcm05 要不要加副作用 GET）。

---

## 8. 与求救群聊模块的关系

- 共用 `rescue_sat_terminal`，查询/下单都 **不要** 默认依赖 `emergency_chat_item`。
- 人付完之后的余量/用量守恒，另开订单+套餐串测，不在本文。
