# 星豆接口测试 Implementation Plan

> **For agentic workers:** 先做第 0 节探针，**禁止**在探针前把 YAML `expected.code/msg` 写成臆测值。实现时遵循 `skills/api-test-framework`（只 `from common.*`、模式 A/B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result` 且必传 `biz_context`）。一类一接口，叶子默认 `[case0]`，**禁止**中文 `parametrize ids`。每个接口的 query / json 以本文 §2 为准。
>
> 来源：Apifox tag `监控平台-星豆接口`；与 [emergency-combo-mall-tests.plan.md](./emergency-combo-mall-tests.plan.md) 互补（该计划明确把 `star-bean/*` 留给本计划）
> 契约：Apifox「Swagger3接口文档」刷新时间 **2026-08-17T09:08:33.807Z**
> 沿用主人拍板（2026-08-17，应急套餐侧）：buy 现网是**待支付订单**不是当场扣费；自动化只校验订单生成，**不支付、不扣豆、不验余额变动**

**Goal:** 4 个星豆接口：3 个查询（换算 / 套餐列表 / 流水分页）+ 充值下单（断言 `orderNo`）。核心验证**换算守恒**（`starBeans == amount × exchangeRatio`）与 **amount / starBeanPackageId 二选一互斥**。

**Architecture:** 模式 A（3 个 GET，`params=`）+ 模式 B′（package/active 提取 `star_bean_package_id/price/bean_count` → buy `json=` → extract `star_bean_order_no` 本文件不读）。**无设备依赖**——4 个接口都不需要 `rescue_sat_terminal` / `group_fixture` 业务注入（session autouse 的分组副作用仍存在，见 §0）。**用例内不 cancel**。buy 成功后 `register_unpaid_order_no`（两条正向各登一次，避免 extract last-wins 漏第一张）；session 末 conftest 按登记表收。订单模块 cancel 正向用独立键 `eo_lifecycle_star_bean_order_no`，**禁止**复用 `star_bean_order_no`。

**Tech Stack:** pytest + YAML + `BaseRequest` + Allure（与应急套餐/围栏同一套）

## Global Constraints

- 只 `from common.*`；禁止 `api_test_framework` / 模式 C
- Authorization：OAS 写 **query required**；现网惯例 header。**默认只 Header**；探针锁定后全文统一，YAML 不写真实 token
- 正向 `expected.msg`，负向 `expected.error_msg`；禁止正向写 `error_msg: "成功"`
- `no_auth: true` 只剥 `Authorization`，保留 `Accept-Language`
- buy 正向只断言「生成了待支付订单」（`orderNo` 非空 + `price`/`starBeanNum` 与来源一致）；**禁止**断言余额变化、`transaction/page` 出现 RECHARGE 流水
- **本文件禁 pytest-xdist**（有 extract 链 package→buy）；**buy 叶子禁 rerun**（副作用是落待支付充值单，重试堆单）
- **负向 case 的 `starBeanPackageId` 一律字面量假 id，禁止 `{{star_bean_package_id}}` 占位符**——extract 缺失时占位符会 `pytest.skip`，把负向用例静默吞掉
- 断言一律 `assert_api_result(...)` 且**必须传 `biz_context`**（至少 `{"请求参数": params或body}`）
- `json_data = res.json()` 每个请求只调一次；`send_request(..., log_level="none")`；单条失败排查时可临时改 `"simple"`（Allure 附件不受影响）
- 方法签名一律注入 `base_url, auth_headers, case`（本文件**无**业务 fixture 注入）
- 共享逻辑（amount 解析等）放模块级 `_SbHelpers`（不以 `Test` 开头），禁多处内联

---

## 0. 范围、执行顺序、session 副作用

Apifox tag **监控平台-星豆接口** 共 4 个 URL（刷新后未增删）：

| 序 | 类名 | 方法 | 路径 | OAS summary | 本批 |
|----|------|------|------|-------------|------|
| 1 | `TestSb01Calculate` | GET | `/api/monitor/star-bean/calculate` | 自定义金额换算 | 做 |
| 2 | `TestSb02PackageActive` | GET | `/api/monitor/star-bean/package/active` | 星豆套餐列表（购买） | 做 |
| 3 | `TestSb03Buy` | POST | `/api/monitor/star-bean/buy` | 星豆充值下单 | **做（只验下单）** |
| 4 | `TestSb04TransactionPage` | GET | `/api/monitor/star-bean/transaction/page` | 星豆使用明细查询 | 做 |

文件内类定义顺序必须 01→04。**`TestSb04` 排在 buy 之后**：纯结构验证 + 探针 P7 结论的落地（见 §2.4——两种结论下都不加旁证断言，区别只是报不报缺陷）。

**buy 两条正向分支的执行关系（设计意图，勿随手调序）：**

- YAML 序：自定义金额分支在前、固定套餐分支在后。自定义金额分支**不依赖任何 extract 主链**，永远可跑——它先跑保证「Sb02 无货时本文件至少有一条正向 buy 落地」
- 固定套餐分支依赖 Sb02 的三键 extract，缺失 → `pytest.skip`（不是 fail）
- **脏单口径：每条正向 buy case 各落 1 笔待支付充值单，整文件一轮 = 2 笔**；extract 只留最后一张。用例内不 cancel；两张都 `register_unpaid_order_no`，session 末按登记表收

**明确不做（本计划全文）：**

- 充值支付（payment / 扫码）、支付后的余额守恒与 RECHARGE 流水验证
- 星豆**消费**链路（建群 / 邀人 / 通讯扣豆）——那是求救群聊侧的串测
- 余额查询接口（本 tag 内无此 URL；余额只能从流水 `balanceAfter` 旁推，不做）
- 重复下单幂等（探针顺带观察，不写成自动化 case，默认不加）

**session 副作用（不为星豆单独加 fixture；待支付单收尾走已有 `cleanup_test_data`）：**

- session autouse 的 `cleanup_test_data` 依赖 `group_fixture` → 登录 + 建三级分组，session 末：关求救群 → 收登记待支付单 → 删设备 → 删分组（本文件**不注入**任何设备 fixture，**不入设备**）
- buy 正向每次落 1 笔**待支付充值单**并登记；一轮 2 笔。`ENABLE_AUTO_CLEANUP=true` 时 session 末收走；要留单扫码关该开关

---

## 1. 三条传值通道

### 通道 A — Fixture（方法参数注入）

| Fixture | 给谁用 | 怎么用 |
|---------|--------|--------|
| `base_url` | 所有请求 | 前缀 `{base_url}/api/monitor` |
| `auth_headers` | 所有请求 | `headers = {**auth_headers}`；`no_auth: true` 时**只去掉** `Authorization` |

### 通道 B — extract.yaml（同文件写入，testcase 读）

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `sb_exchange_ratio` | `TestSb01Calculate` 正向基线（amount=1 或探针定的最小整数） | `TestSb03Buy` 正向-自定义金额分支的联动断言；**缺失 → 仅联动断言 skip，主断言照常**（见 §2.3） | 换算比率 |
| `star_bean_package_id` | **仅** `TestSb02PackageActive` 正向首条成功且列表非空 | `TestSb03Buy` 正向-固定套餐分支 | 使用中（`status==1`）且 `sort` 最小的套餐 id |
| `star_bean_package_price` / `star_bean_package_beans` | 与 `star_bean_package_id` 同元素同次写入 | `TestSb03Buy` 正向-套餐分支一致性断言 | 所选套餐价格 / 豆数 |
| `star_bean_order_no` | `TestSb03Buy` 正向 `code==0` | **本文件无人读（含 Sb04 旁证，见 §2.4）** | extract last-wins 只留最后一张。给人扫码（仅 `ENABLE_AUTO_CLEANUP=false`）。两张都 `register_unpaid_order_no`，session 收。订单模块 **禁止** 拿此键做 cancel；星豆 cancel 用自造 `eo_lifecycle_star_bean_order_no`（不登记） |

extract 语义备注（源码事实）：`write_yaml(mode="append")` 同 key **last-wins 覆盖**；`clear_data_per_session` 每轮开跑前清空——无跨轮残留。「只写一次」防的是本轮内多 case 覆盖。

写入（仅 testcase，禁止 conftest）：

```python
write_yaml("./extract.yaml", {"star_bean_package_id": pkg_id,
                              "star_bean_package_price": price,
                              "star_bean_package_beans": beans}, mode="append")
# buy 成功后再：
write_yaml("./extract.yaml", {"star_bean_order_no": order_no}, mode="append")
```

读取（buy 正向-套餐分支）：

```python
pkg_id = resolve_extract_value(case.get("starBeanPackageId"),
                               required=is_extract_placeholder(case.get("starBeanPackageId")))
```

- `star_bean_package_id` 缺失（套餐列表空 / 只跑 buy 类）→ buy 套餐分支 `pytest.skip`（不是 fail）
- **所有负向 case 的 `starBeanPackageId` 一律字面量假 id**（如 `"0"` / `"999999999"`）
- 禁止 YAML 写死套餐 ID

**`star_bean_package_id` 写入规则：**

1. YAML `package_active_cases` 第一条为正向基线；列表非空才有后续。
2. 只从 `status==1`（使用中）的元素里取 `sort` **最小**的；顺带写同元素 `price` → `star_bean_package_price`、`beanCount` → `star_bean_package_beans`。
3. 列表为空或全部 `status==0` → 不写 extract；buy 套餐分支 `skip`。
4. extract 已有 `star_bean_package_id` 则不再写（首条成功赢）。

### 通道 C — YAML 字面量

字段名与 OAS **驼峰一致**（`amount` / `starBeanPackageId` / `type` / `page` / `pageSize`），禁止蛇形命名。

| YAML 字段 | 接口 | 说明 |
|-----------|------|------|
| `amount` | calculate / buy | 充值金额（元，**整数**，OAS `minimum: 1`） |
| `starBeanPackageId` | buy | 与 `amount` **二选一**；正向套餐分支 `{{star_bean_package_id}}`，负向字面量 |
| `type` | transaction/page | 枚举五值：`COMMUNICATION` / `CREATE_GROUP` / `INVITE_MEMBER` / `RECHARGE` / `REFUND` |
| `page` / `pageSize` | transaction/page | 分页 |
| `no_auth` | 全部 | `true` 剥 token |
| `expected.*` | 全部 | 同技能约定 |

---

## 2. 接口参数传递

公共 URL 前缀：`{base_url}/api/monitor/star-bean`。
3 个 GET **全部 `params=`**；buy **必须 `json=`**。

### 2.1 GET `/calculate` — `TestSb01Calculate.test_calculate`

| 参数 | 位置 | 正向-基线 | 正向-大额 | 负向-缺 amount | 负向-0 | 负向-负数 | 负向-小数 | 负向-无 Token |
|------|------|-----------|-----------|----------------|--------|-----------|-----------|---------------|
| `amount` | query | `1` | `999999`（探针定上限） | **不传** | `0` | `-1` | `0.5`（描述写整数） | 任意合法 |
| `Authorization` | Header | token | token | token | token | token | token | **删除** |

```python
class _SbHelpers:
    @staticmethod
    def build_headers(auth_headers, case):
        headers = {**auth_headers}
        if case.get("no_auth"):
            headers.pop("Authorization", None)
        return headers

class TestSb01Calculate:
    @pytest.mark.parametrize("case", _TEST_DATA["star_bean_calculate_cases"])
    def test_calculate(self, base_url, auth_headers, case):
        headers = _SbHelpers.build_headers(auth_headers, case)
        params = {}
        if "amount" in case:
            params["amount"] = case["amount"]
        res = http.send_request(
            "get", f"{base_url}/api/monitor/star-bean/calculate",
            params=params, headers=headers, case_name=case["name"], log_level="none",
        )
        json_data = res.json()
```

断言：

- `assert_api_result` + `read_expected_msg`，`biz_context={"请求参数": params}`
- 正向结构：`$.data.starBeans`（int）、`$.data.exchangeRatio`（int）、`$.data.amount` 为数字
- **换算守恒（计费红线，探针 P1 定公式后钉死）**：默认 `starBeans == amount × exchangeRatio`；若现网公式不同（如分段 / 取整规则），把真实公式写入 §5 并按其断言
- 正向基线写 `sb_exchange_ratio`（供 §2.3 联动断言复核）

### 2.2 GET `/package/active` — `TestSb02PackageActive.test_package_active`

无业务参数（只有鉴权）。

| 参数 | 位置 | 正向 | 负向-无 Token |
|------|------|------|---------------|
| `Authorization` | Header | token | **删除** |

断言：

- 正向：`code=0`，`$.data` 为 list（**可空**——空列表是合法正向，只锁 code/msg；此时不写 extract，buy 套餐分支后续 skip）
- 列表非空则元素含 `id`（str）、`price`（数字 ≥ 0）、`beanCount`（int ≥ 0）、`status`∈{0,1}
- **`status==0`（已禁用）的套餐出现在「购买列表」里 → 直接 fail**（口径探针 P2 定：若现网本就返回含禁用项，把该断言降级为「buy 时跳过 status==0」并记 §5）
- 写入 `star_bean_package_id/price/beans` 规则见 §1 通道 B

### 2.3 POST `/buy` — `TestSb03Buy.test_buy`

**`json=` 请求体。`amount` 与 `starBeanPackageId` 二选一**（OAS 原文如此，且两处字段名描述不一致——`starBeanPackageId` 的描述写的是 `customAmountYuan`，契约自身有笔误，以字段名为准）。

| 参数 | 位置 | 正向-自定义金额 | 正向-固定套餐 | 负向-都传 | 负向-都不传 | 负向-amount=0 | 负向-假套餐id | 负向-无 Token |
|------|------|-----------------|---------------|-----------|-------------|---------------|---------------|---------------|
| `amount` | JSON | `1` | **不传** | `1` | **不传** | `0` | 不传 | `1` |
| `starBeanPackageId` | JSON | **不传** | `{{star_bean_package_id}}` | 字面量假 id | **不传** | 不传 | `"999999999"` | 不传 |
| `Authorization` | Header | token | token | token | token | token | token | **删除** |

说明：

- 「都传」「都不传」是**二选一互斥**的正反两面——这是本接口最核心的契约点，探针 P5 必须先回填真实 code/msg
- 负向-假套餐id、负向-都传里的 `starBeanPackageId` **一律字面量**（Global Constraints）
- 负向 `amount` 边界（0 / 负 / 0.5）与 calculate 共用同一套心智，负向码以 buy 探针为准（可能比 calculate 更严）

```python
class TestSb03Buy:
    @pytest.mark.parametrize("case", _TEST_DATA["star_bean_buy_cases"])
    def test_buy(self, base_url, auth_headers, case):
        headers = _SbHelpers.build_headers(auth_headers, case)
        body = {}
        if "amount" in case:
            body["amount"] = case["amount"]
        pkg = case.get("starBeanPackageId")
        if is_extract_placeholder(pkg):
            pkg = resolve_extract_value(pkg, required=True)
        if pkg is not None:
            body["starBeanPackageId"] = pkg
        res = http.send_request(
            "post", f"{base_url}/api/monitor/star-bean/buy",
            json=body, headers=headers, case_name=case["name"], log_level="none",
        )
        json_data = res.json()
```

正向断言：

- `code=0` 且 `$.data.orderNo` 非空、`orderCreateTime`/`orderExpireTime` 非空、`expire > create`（时间序）
- **一致性断言（同模块计费守恒）**：
  - 自定义金额分支：`$.data.starBeanNum == amount × sb_exchange_ratio`（与 calculate 同口径；探针 P6 验证两接口换算是否同引擎，不同则按 §5 实测口径断言或降级）。**`sb_exchange_ratio` 缺失时（如只跑本类）：用 `resolve_extract_value(..., required=True)` 语义——联动断言 `pytest.skip`，orderNo 等主断言照常执行，禁止拿 `None` 参与比较 crash**
  - 固定套餐分支：`$.data.price == star_bean_package_price` 且 `$.data.starBeanNum == star_bean_package_beans`
  - 两条分支都断言 `price > 0`、`starBeanNum > 0`（充 0 元 / 0 豆是红线）
- 写入 `star_bean_order_no`；本文件后续**不再读取**（Sb04 旁证也不读，见 §2.4）；并 `register_unpaid_order_no(order_no)`（两条正向各登一次，避免 last-wins 漏第一张）
- **不要**断言 transaction/page 出现 RECHARGE、不要调任何支付接口

### 2.4 GET `/transaction/page` — `TestSb04TransactionPage.test_transaction_page`

全 **query**。分页路径 OAS 已给：`$.data.items` / `total` / `totalPage`（不像应急套餐要探针猜）。

| 参数 | 位置 | 正向-默认 | 正向-各 type | 边界 | 负向-非法 type | 负向-无 Token |
|------|------|-----------|--------------|------|----------------|---------------|
| `type` | query | 不传 | 五枚举各一条 | 不传 | `FOO` | 不传 |
| `page` | query | 不传（默认1） | 不传 | `0` / `-1` | 不传 | 不传 |
| `pageSize` | query | 不传（默认100） | 不传 | `0` / 极大 `10000` | 不传 | 不传 |
| `Authorization` | Header | token | token | token | token | **删除** |

断言：

- 正向：`code=0`；`$.data.items` 为 list（可空）、`total`/`totalPage` 为 int ≥ 0
- 列表非空则元素含 `id`、`amount`（int，**带符号**——正充负扣）、`balanceAfter`（int）、`transactionType`∈五枚举
- **待支付与流水的关系（探针 P7 定，二元结论，不写依赖订单号的断言）**：
  - P7 = **有流水**（待支付充值单就产生 RECHARGE 记录）→ 这是「未支付先记账」的计费红线，**直接报缺陷**，自动化不加任何适配断言
  - P7 = **无流水** → TestSb04 维持纯结构验证，**不加**旁证断言（`star_bean_order_no` 不被任何 case 读取；按 `description` 关联订单号太脆弱，不做）
  - 即：两种结论下 TestSb04 都不加旁证断言，区别只在要不要提缺陷单
- 边界 case 不 5xx

---

## 3. YAML 文件头与样例

路径：`yaml/test_star_bean_controller.yaml`。顶层 key `<模块>_<动作>_cases` 带前缀。负向 `code`/`error_msg` **探针后填**，禁止臆造。

```yaml
# yaml/test_star_bean_controller.yaml
# 星豆接口：换算 / 套餐列表 / 充值下单 / 流水分页
# star_bean_package_id/price/beans：仅 package_active 首条成功且 status==1 非空时写入
# {{star_bean_package_id}} 整段占位才 resolve_extract_value；负向一律字面量
# star_bean_order_no 只写不读；sb_exchange_ratio 由 calculate 基线写入

star_bean_calculate_cases:
  - name: "星豆-换算-正向-最小金额"
    amount: 1
    expected:
      code: 0
      msg: "成功"   # S1 探针后若不同则改
  # 大额 / 负向（缺 amount、0、-1、0.5、无 token）：探针 P1/P4 后补 code 与 error_msg

star_bean_package_active_cases:
  - name: "星豆-套餐列表-正向"
    expected:
      code: 0
      msg: "成功"

star_bean_buy_cases:
  - name: "星豆-充值下单-正向-自定义金额"
    amount: 1
    expected:
      code: 0
      msg: "成功"
  - name: "星豆-充值下单-正向-固定套餐"
    starBeanPackageId: "{{star_bean_package_id}}"
    expected:
      code: 0
      msg: "成功"
  # 负向（都传 / 都不传 / amount=0 / 假套餐id / 无 token）：探针 P5 后补

star_bean_transaction_page_cases:
  - name: "星豆-流水分页-正向-默认"
    expected:
      code: 0
      msg: "成功"
  # 各 type / 边界 / 非法 type / 无 token：探针后补
```

---

## 4. 第 0 节：现网探针（先于 YAML 定稿）

用当前 web 测试账号手工或临时脚本打一遍（结果回填 §5；临时脚本放 `temps/`，用完即删）：

| ID | 请求 | 要记下的 |
|----|------|----------|
| P1 | calculate `amount=1` / `=10` / `=999999` | code/msg；`starBeans` 与 `exchangeRatio` 实际值；**守恒公式**是否 `starBeans == amount × exchangeRatio`；token 只 header 是否通过 |
| P2 | package/active | 列表是否空；`status` 分布（有没有 0 混在购买列表）；`id` 样例；`price`/`beanCount` 样例 |
| P3 | transaction/page 默认 + 各 type | 空页是否 code=0；`$.data.items` 路径核实；流水元素字段实际形态 |
| P4 | calculate 负向全套：缺 amount / `0` / `-1` / `0.5` / 无 token | 各自真实 code/msg（**勿假设**——0 与 0.5 可能不同码） |
| P5 | buy 负向：都传 / 都不传 / `amount=0` / 假套餐id / 无 token | 各自真实 code/msg；**无 token 时确认无订单副作用**；「都传」到底听谁的还是报错 |
| P6 | buy 正向 `amount=1`（**不支付不 cancel**） | `orderNo` 路径；`starBeanNum` 是否 == P1 的换算结果（两接口同引擎？）；`price`/`starBeanNum` 实际值 |
| P7 | P6 之后 GET transaction/page `type=RECHARGE` 首页 | **待支付单是否产生流水**（二元结论：有 → 报缺陷「未支付先记账」；无 → Sb04 纯结构验证；两种都不加旁证断言，见 §2.4） |

没有 P1–P7 禁止把负向文案写死。P6 与实现可同一轮：先打通正向再补负向码。

---

## 5. 现网基线（2026-08-18 探针实测）

| 项 | 结论 |
|----|------|
| Token 位置 | **只 Header 即可**（全程未传 query token，code=0） |
| calculate 守恒公式 | **`starBeans == amount × exchangeRatio` 成立**（amount=1 → ratio=10000 → starBeans=10000） |
| calculate 金额范围 | **仅允许 1 元**：amount=10 / 999999 → `1001 充值金额范围：1~1元`（范围文案「1~1元」疑似配置缺陷，见 §7.9） |
| calculate 负向各码 | 缺 amount → `1001 请检查请求参数是否正确`；0 / -1 / 0.5 → `1001 充值金额范围：1~1元`；无 token → `3001 没有访问权限` |
| transaction/page 非法 type | `FOO` → `1001 未知参数错误`（非静默忽略） |
| package/active | 非空，4 个套餐 **全部 status=1**，`sort` 全为 1（排序区分度无）。代表值：`6a38f497…` price=1.0 beans=100 |
| buy 二选一 | **都传 → `999 套餐不存在或已下架`（套餐 id 先校验，假 id 时遇不到二选一报错）**；都不传 → `999 下单过于频繁，请稍后重试`（被限频码掩盖，真码未知，见 §7.10） |
| buy `starBeanNum` 口径 | **与 calculate 同引擎**：buy amount=1 → `starBeanNum=10000 == 1 × 10000`。联动断言可写 |
| buy 正向实测 | `$.data.orderNo` 确认；`price=1`、`starBeanNum=10000`、`orderCreateTime/orderExpireTime` 格式 `yyyy-MM-dd HH:mm:ss`，间隔 **10 分钟** |
| buy 限频 | **同一账号连续下单（含失败负向）会触发 `999 下单过于频繁`**；冷却约 60s 后恢复（实测 65s 可过，紧接再下单又 999）。**测试用例间必须留冷却**（见 §2.3 实现约束） |
| buy 负向码 | amount=0 → `1001 充值金额必须大于0`；假套餐id → `999 下单过于频繁`（同上被掩盖）；无 token → `3001 没有访问权限`（无订单副作用——3001 在业务校验前） |
| buy 待支付是否产生 RECHARGE 流水 | **否**——P7 实测 buy 成功后 RECHARGE 首页最新一条 createdTime 距今 76132s（早于本次下单），本次单未产生流水。**Sb04 纯结构验证，不加旁证断言，不报缺陷** |

---

## 6. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/star-bean-tests.plan.md` | 本文 |
| `yaml/test_star_bean_controller.yaml` | `star_bean_calculate_cases` / `star_bean_package_active_cases` / `star_bean_buy_cases` / `star_bean_transaction_page_cases` |
| `testcases/test_star_bean_controller.py` | `TestSb01`–`04` + `_SbHelpers`；package 写 extract 三键；buy 写 `star_bean_order_no`（不读）并每条正向 `register_unpaid_order_no` |

不为星豆单独加 fixture。待支付单收尾是跨模块能力，见 `common/order_cleanup_util.py` + `cleanup_test_data`。

### 任务

- [ ] **Task 0** 探针 P1–P7（P6 不支付、用例内不 cancel），填 §5
  - 验收：守恒公式、二选一互斥各码、orderNo 路径均已填；P7 二元结论已记（有流水 → 先提缺陷单再继续）
- [ ] **Task 1** YAML + `TestSb01Calculate`（守恒公式按 §5 钉死；基线写 `sb_exchange_ratio`）
- [ ] **Task 2** `TestSb02PackageActive`（空列表只锁 code；status==0 红线按 §5 口径）
  - 验收：有使用中套餐则 extract 三键齐且不被覆盖
- [ ] **Task 3** `TestSb03Buy`：`json=`；两条正向分支 + 一致性断言；不支付、用例内不 cancel、不读 `star_bean_order_no`；成功后登记
  - 验收：extract 有 `star_bean_order_no`；无套餐 id 时套餐分支 skip；全文件 collect 含 01→04，叶子 `[case0]`
- [ ] **Task 4** `TestSb04TransactionPage`（`$.data.items` 结构；按 §2.4 不加旁证断言）
- [ ] **Task 5** 整文件回归（含 2 条正向 buy = 2 笔待支付充值单，均登记；默认 session 末收走）

---

## 7. 仍不敢装懂、需要现网说话的点

1. 换算公式是否线性（`amount × ratio`）；`exchangeRatio` 单位是「豆/元」还是别的口径。
2. calculate 与 buy 是否同一换算引擎（决定跨接口联动断言能不能写）。
3. 「都传 / 都不传」的真实行为（报错？还是静默优先某一个——后者是契约缺陷，值得报）。
4. buy `amount=0.5`：calculate 侧与 buy 侧校验是否同严。
5. package/active 里 `status==0` 会不会混进购买列表（口径问题，不是想当然 fail）。
6. 待支付充值单是否产生 RECHARGE 流水（有 = 计费红线缺陷，不是用例适配问题）。
7. ~~大额上限~~ 已测：金额范围锁定 1~1 元（见 §5）。
8. 契约笔误：`StarBeanRechargeReqDto.starBeanPackageId` 的描述写着 `customAmountYuan`——实现以字段名为准，但建议向开发反馈文档修正。
9. **疑似配置缺陷**：calculate 报错文案「充值范围在1~1元」——上限疑似配置成了 1。建议向开发确认真实上限（若是 1~1000 之类，YAML 大额 case 需同步改）。
10. **buy 限频掩盖了两个真负向码**：「都不传」与「假套餐id」实测都返回 `999 下单过于频繁`。自动化里这两条 case 若与其它 buy case 同 session 连跑，会 **间歇性** 拿到限频码——要么接受以 `999` 锁定（脆弱），要么负向 case 之间加冷却（慢）。**本计划取舍：YAML 的 expected 写实测 `999`，但 buy 负向 case 之间加 `time.sleep(65)` 冷却以稳定复现；`都不传`的真码留待开发澄清后修正**。
11. 「都传」实测走到套餐 id 校验（假 id → 套餐不存在），说明**服务端并没有强制二选一互斥**——二选一约束目前只在文档里。建议向开发确认这是否是契约缺口（amount 被静默忽略的隐患）。

---

## 8. 与应急套餐模块的关系

- 同一账号体系、同一「下单不支付」拍板；两个模块各自独立文件、独立 extract 键（`combo_*` / `star_bean_*` 前缀隔离），可同 session 跑、互不依赖。
- 应急套餐计划中「buy 不能证明未扣费」的缺口，在人完成**星豆充值支付**后，由本模块 `transaction/page`（`RECHARGE` 流水）+ 应急套餐订单串测共同补齐——那是后续串测计划，不在本文。
