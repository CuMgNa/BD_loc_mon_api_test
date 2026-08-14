---
name: enclosure-controller-tests
overview: 对接围栏管理 7 个操作。创建/编辑仅 name+pointJson。现网名称非空且最长30。分享码正向 28feceb1b1；自己的码按反向断言（现网会成功，待确认）。
todos:
  - id: add-yaml
    content: 新建 yaml/test_enclosure_controller.yaml（7 个 *_cases；业务名用 enclosureName）
    status: completed
  - id: add-testcase
    content: 新建 testcases/test_enclosure_controller.py（test_enc_a～g + teardown 清理）
    status: completed
  - id: spec-lock
    content: 联调已回填 KML/负向 msg；自己的分享码现网成功，反向 expected 待确认
    status: pending
  - id: verify-pytest
    content: 18 passed / 1 failed（自己的分享码反向）；teardown 清主围栏+导入围栏
    status: pending
isProject: false
---

# 围栏管理接口测试 Implementation Plan

> **For agentic workers:** 按本文件「参数传递」原样实现。创建/编辑只有 `name` + `pointJson`。分享码正向字面量 `28feceb1b1`；`{{enclosure_share_code}}` 是反向（自己的码）。

**Goal:** 单文件跑通围栏 CRUD + 绑设备 + KML 导出；用他账号分享码导入一条围栏并在 teardown 删除。

**Architecture:** 模式 B′。创建只传 name+pointJson。extract 存主围栏 id 和自己的 shareCode（供反向）。导入成功的 id 存 `enclosure_cloned_id`。teardown 无条件 DELETE 这两个 id。不要删对方账号上的原围栏。

---

## 0. 执行顺序

字典序方法名，**禁止**把分享码插到创建和编辑之间。

| 序 | 方法 | 接口 | 依赖 |
|----|------|------|------|
| a | `test_enc_a_add` | POST `/enclosures` | 无 |
| b | `test_enc_b_list` | GET `/enclosures` | 正向核验需要 a 写入的 `enclosure_id`；`no_auth` 不需要 |
| c | `test_enc_c_update` | PUT `/enclosures/{id}` | `enclosure_id` |
| d | `test_enc_d_terminals` | PUT `/enclosures/{id}/terminals` | `enclosure_id` + `msg_test_terminal` |
| e | `test_enc_e_export` | GET `/enclosures/{id}/export` | `enclosure_id` |
| f | `test_enc_f_add_by_code` | POST `/enclosures/codes/{shareCode}` | 正向：YAML 字面量 `28feceb1b1`；反向：extract 自己的码；非法码不依赖 extract |
| g | `test_enc_g_delete` | DELETE `/enclosures/{id}` | 正向删主 id；克隆 id 留给 teardown |

teardown（class/module fixture `yield` 之后，不参与断言）：对 `enclosure_cloned_id`、`enclosure_id` 各 DELETE 一次，HTTP/业务失败只打日志。这样 a～f 中途失败也不会留围栏。

副作用：`test_enc_d_terminals` 注入 `msg_test_terminal` 会拉起 `group_fixture`（建三级分组 + 消息测试设备，session 末再清分组）。单跑本文件预期如此。

---

## 1. 三条传值通道（先定通道，再对接口）

和技能一致：**fixture / extract.yaml / YAML 字面量**。禁止在 YAML 写真实设备号、真实 URL、明文密码。

### 通道 A — Fixture（方法参数注入）

| Fixture | 给谁用 | 怎么用 |
|---------|--------|--------|
| `base_url` | 所有请求拼 URL | `f"{base_url}/api/monitor/enclosures"` |
| `auth_headers` | 所有请求 Header | `headers = {**auth_headers}`；`no_auth: true` 时 **只去掉** key 名为 `Authorization` 的项，保留 `Accept-Language` |
| `msg_test_terminal` | 仅 `test_enc_d_terminals` | 返回设备 SN 字符串。YAML 写 `{{msg_test_terminal}}`，**不要**走 `resolve_extract_value`（那是 extract 通道） |

默认 **Authorization 只放 Header**。若联调 401/3001，再按位置接口那样把同一 token **同时**放进 `params["Authorization"]`，并记入第 6 节。

### 通道 B — extract.yaml（同文件写入，testcase 读）

写入（仅 testcase，禁止 conftest）：

```python
write_yaml("./extract.yaml", {
    "enclosure_id": <$.data.id>,
    "enclosure_share_code": <$.data.shareCode>,  # 没有则不写该键
    "enclosure_name": <当时的 enclosureName>,
}, mode="append")
```

分享码**正向**（他账号码）成功后再：

```python
write_yaml("./extract.yaml", {"enclosure_cloned_id": <$.data.id>}, mode="append")
```

读取：

```python
from common.yaml_util import resolve_extract_value, is_extract_placeholder

tid = resolve_extract_value(case.get("enclosureId"), required=is_extract_placeholder(case.get("enclosureId")))
```

- YAML 整段 `{{enclosure_id}}` → 从 extract 取值；缺失且 `required=True` → `pytest.skip`
- YAML 字面量（如 `ffffffffffffffffffffffff`、`28feceb1b1`）→ 原样返回，不读 extract

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `enclosure_id` | `test_enc_a_add` 正向 `code==0` | c/d/e/g 的 path `{id}`；b 列表核验 | 主围栏 |
| `enclosure_share_code` | `test_enc_a_add` 正向 `code==0` 且响应有码 | `test_enc_f` **反向** path | 本账号自己的分享码 |
| `enclosure_name` | 同上 | `test_enc_b_list` 可选按名查找 | 列表核验 |
| `enclosure_cloned_id` | `test_enc_f` **正向**（他账号码）`code==0` | teardown DELETE | 导入到本账号的围栏 |

### 通道 C — YAML 字面量 + 运行时替换

- 用例标题：`name`（**只做标题**，禁止当围栏名称发给接口）
- 围栏名称：`enclosureName`。规则以**现网为准**（联调 2026-08-14）：
  - 不能为空；空名称 msg=`围栏名称不能为空,最长30个字`
  - 最长 30 个字；31 位负向。产品口述「2–12」**未在接口生效**（1 位、13 位均 `code=0`），故不把 1/13 当负向，避免误创建残留。
  - 正向唯一名：`E{int(time.time())}` → 11 位。禁止 `AUTO_ENC_` 前缀。
- 点串：`pointJson`，YAML 里是 **字符串**，Python **不要再 `json.dumps`**。创建/编辑**没有**类型/半径/颜色等其它业务字段。
- 非法 id：`ffffffffffffffffffffffff`（24 位 hex，贴近现网 Mongo id）
- 分享码正向（他账号）：字面量 `28feceb1b1`
- 分享码反向（自己的码）：`{{enclosure_share_code}}`（现网会成功克隆，仍按反向断言；成功时把 id 写入 cleanup）
- 分享码非法：`INVALID_SHARE_XXXX` → 现网 `1001` / `围栏不存在`

---

## 2. 接口参数传递（每个接口：放哪 / 传什么 / 代码形态）

Swagger 来源：tag「围栏管理接口」，2026-08-14。文档把若干 string 标成 object，**按描述当 string 传**。

公共 URL 前缀：`{base_url}/api/monitor`。

闭合围栏点（正向默认；若后端拒收再改文档示例的未闭合两点并回填第 6 节）：

```text
{"points":[{"lng":113.466203,"lat":23.170439},{"lng":113.467203,"lat":23.170439},{"lng":113.466703,"lat":23.171139},{"lng":113.466203,"lat":23.170439}]}
```

名称负向也带这份 `pointJson`，避免缺点和名称错误缠在一起。

### 2.1 POST `/enclosures` — 添加围栏（`test_enc_a_add`）

**怎么传：** 全部 **query**（`send_request(..., params=...)`），**不是** JSON body。不要传 `points[0].lat`（与 `pointJson` 两套点会冲突）。**目前只有 `name` + `pointJson`。**

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-空/1位/13位 |
|-------------|------|----------|------|------------------|
| （无 path） | — | — | URL 即 `/enclosures` | 同左 |
| `name` | query | YAML `enclosureName` → 替换时间戳 | `E`+10 位时间戳（11 位） | `""` / `"A"` / `"1234567890123"` |
| `pointJson` | query | YAML `pointJson` 字符串原样 | 闭合四点 JSON 文本 | 同左（仍传，测的是名称） |
| `Authorization` | Header | `auth_headers` | token | token |

```python
params = {"name": ename}
if case.get("pointJson"):
    params["pointJson"] = case["pointJson"]
http.send_request("post", url, params=params, headers=headers, case_name=case["name"], log_level="none")
```

正向 `code==0` 后提取并写入 extract（路径联调可改，默认）：

- `$.data.id` → `enclosure_id`（没有 id 则 `pytest.fail`，后续全 skip 无意义）
- `$.data.shareCode` → 有则写 `enclosure_share_code`
- 当时的 `ename` → `enclosure_name`

### 2.2 GET `/enclosures` — 列表（`test_enc_b_list`）

**怎么传：** 无业务 query。Swagger 只标了 query `Authorization`；我们先只 Header。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-无Token |
|-------------|------|----------|------|----------------|
| （无） | — | — | 空 params | 空 params |
| `Authorization` | Header | fixture | token | **删除该 header** |

正向额外断言（请求仍无过滤参数，在响应上过滤）：

1. `resolve_extract_value("{{enclosure_id}}", required=True)` 得到主 id
2. 列表结构按顺序试：`$.data[*].id`（文档是 `List`），其次 `$.data.items[*].id`
3. 主 id 必须出现在列表中，否则 fail

`no_auth` 不读 extract，只断言 `expected.code/msg`。

### 2.3 PUT `/enclosures/{id}` — 编辑（`test_enc_c_update`）

**怎么传：** `id` 在 **path**；`name`/`pointJson` 在 **JSON body**（`json=`，不是 query）。这与「添加」不同，不要抄 a 的 params。**目前只有 `name` + `pointJson`。**

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-空/1位/13位 | 负向-非法 id |
|-------------|------|----------|------|------------------|--------------|
| `id` | path | YAML `enclosureId` → `resolve_extract_value` | extract 的主 id | 同左 | 字面量 `ffffffffffffffffffffffff` |
| `name` | JSON body | YAML `enclosureName` → 替换时间戳 | `U`+10 位时间戳（11 位） | `""` / `"A"` / `"1234567890123"` | 合法长度名 `BadEncName12`（12 位，测的是 id） |
| `pointJson` | JSON body | YAML `pointJson` | 与创建同一闭合串 | 同左 | 省略 |
| `Authorization` | Header | fixture | token | token | token |

```python
tid = resolve_extract_value(case.get("enclosureId"), required=is_extract_placeholder(case.get("enclosureId")))
url = f"{base_url}/api/monitor/enclosures/{tid}"
body = {"name": ename}
if case.get("pointJson"):
    body["pointJson"] = case["pointJson"]
http.send_request("put", url, json=body, headers=headers, case_name=case["name"], log_level="none")
```

YAML：`enclosureId: "{{enclosure_id}}"` 或 `enclosureId: "ffffffffffffffffffffffff"`。

### 2.4 PUT `/enclosures/{id}/terminals` — 添加/清空设备（`test_enc_d_terminals`）

**怎么传：** `id` 在 **path**；`addrs` 在 **JSON body 的一个字符串**（逗号拼接），**不是** JSON 数组、不是 query。

文档：空字符串表示清空该围栏设备。只清当前测试围栏，应测。

| HTTP 参数名 | 位置 | 值从哪来 | 正向-绑定 | 正向-清空 |
|-------------|------|----------|-----------|-----------|
| `id` | path | `{{enclosure_id}}` → extract | 主 id | 主 id |
| `addrs` | JSON `{"addrs": "..."}` | YAML `addrs` | fixture `msg_test_terminal`（YAML 写 `{{msg_test_terminal}}`，Python 按字符串相等替换） | `""` |
| `Authorization` | Header | fixture | token | token |

```python
def test_enc_d_terminals(self, base_url, auth_headers, msg_test_terminal, case):
    tid = resolve_extract_value(case.get("enclosureId"), required=True)
    addrs = case.get("addrs")
    if isinstance(addrs, str) and addrs.strip() == "{{msg_test_terminal}}":
        addrs = msg_test_terminal
    http.send_request(
        "put",
        f"{base_url}/api/monitor/enclosures/{tid}/terminals",
        json={"addrs": addrs if addrs is not None else ""},
        headers={**auth_headers},
        case_name=case["name"],
        log_level="none",
    )
```

YAML 两条都放在 `add_enclosure_terminals_cases`，**绑定在前、清空在后**（parametrize 顺序 = YAML 顺序）。

### 2.5 GET `/enclosures/{id}/export` — 导出 KML（`test_enc_e_export`）

**怎么传：** 只有 path `id` + Header。不要套 xlsx 的 `PK` 断言。不要默认加 `Time-Zone`（位置导出才需要）；联调若 4xx 再补。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-无Token | 负向-非法 id |
|-------------|------|----------|------|----------------|--------------|
| `id` | path | extract 或字面量 | `{{enclosure_id}}` | `{{enclosure_id}}`（仍要合法 path，测的是鉴权） | `ffffffffffffffffffffffff` |
| `Authorization` | Header | fixture | token | 去掉 Authorization | token |

断言：

1. 正文 stripped 首字节是 `{` 或 `[` → 当 JSON，走 `assert_api_result`（无 token/非法 id 多半走这里）
2. 否则当文件流：HTTP=`expected.http_status`（默认 200）、`len(content)>0`、前 500 字节能看出 `kml` 或 `<?xml`
3. 禁止 `assert_export_response(..., require_binary=True)`

### 2.6 POST `/enclosures/codes/{shareCode}` — 分享码添加（`test_enc_f_add_by_code`）

**怎么传：** `shareCode` **只在 path**，无 body、无业务 query。

| HTTP 参数名 | 位置 | 值从哪来 | 正向（他账号） | 反向（自己的码） | 负向-非法码 |
|-------------|------|----------|----------------|------------------|-------------|
| `shareCode` | path | YAML 字面量或 extract | `28feceb1b1` | `{{enclosure_share_code}}` | `INVALID_SHARE_XXXX` |
| `Authorization` | Header | fixture | token | token | token |

```python
share = resolve_extract_value(case.get("shareCode"), required=is_extract_placeholder(case.get("shareCode")))
url = f"{base_url}/api/monitor/enclosures/codes/{share}"
http.send_request("post", url, headers=headers, case_name=case["name"], log_level="none")
```

YAML 顺序：**正向他账号 → 反向自己的码 → 非法码**。

- 正向成功且 `$.data.id` 存在 → 写入 `enclosure_cloned_id`（本账号新建的围栏，teardown 删它；**不要**删对方账号原围栏）
- 反向：创建返回的自己的码，预期业务失败（初值 `1001` / 「不能添加自己的围栏」，联调按实回填）
- 非法码始终执行，不依赖 extract

创建未返回 `shareCode` 时，反向用例 `required=True` 会 `pytest.skip`。

### 2.7 DELETE `/enclosures/{id}` — 删除（`test_enc_g_delete`）

**怎么传：** 仅 path `id` + Header，无 body。

| HTTP 参数名 | 位置 | 值从哪来 | 正向 | 负向-非法 id |
|-------------|------|----------|------|----------------|
| `id` | path | extract / 字面量 | `{{enclosure_id}}` | `ffffffffffffffffffffffff` |
| `Authorization` | Header | fixture | token | token |

YAML **正向必须写在负向前**。正向只删主围栏。克隆不在这条断言里删，交给 teardown（避免「断言失败导致克隆没删」和「克隆失败拖垮正向」缠在一起）。

teardown 伪代码：

```python
@pytest.fixture(scope="class", autouse=True)
def _cleanup_enclosures(self, base_url, auth_headers):
    yield
    for key in ("enclosure_cloned_id", "enclosure_id"):
        eid = resolve_extract_value("{{%s}}" % key, required=False)
        if not eid:
            continue
        try:
            http.send_request("delete", f"{base_url}/api/monitor/enclosures/{eid}",
                              headers=auth_headers, case_name=f"teardown-del-{key}", log_level="none")
        except Exception as exc:
            key("teardown-del-失败", f"{key}: {exc}")
```

先删 cloned 再删主 id。失败只打日志，不 assert。

---

## 3. YAML 顶层 key（与方法一一对应）

业务名称字段 **只允许 `enclosureName`**，禁止用 `name` 表示围栏名。

| YAML key | 方法 | 用例条数与意图 |
|----------|------|----------------|
| `add_enclosure_cases` | `test_enc_a_add` | 正向 11 位名+pointJson；负向空 / 1 位 / 13 位 |
| `list_enclosure_cases` | `test_enc_b_list` | 正向（响应含 enclosure_id）；负向 no_auth |
| `update_enclosure_cases` | `test_enc_c_update` | 正向改名+点；负向空 / 1 位 / 13 位；负向非法 id |
| `add_enclosure_terminals_cases` | `test_enc_d_terminals` | 绑定 `{{msg_test_terminal}}`；清空 `addrs: ""` |
| `export_enclosure_cases` | `test_enc_e_export` | 正向文件流；负向 no_auth；负向非法 id |
| `add_enclosure_by_code_cases` | `test_enc_f_add_by_code` | 正向 `28feceb1b1`；反向 `{{enclosure_share_code}}`；负向非法码 |
| `delete_enclosure_cases` | `test_enc_g_delete` | 正向删主 id；负向非法 id |

落地稿见 `yaml/test_enclosure_controller.yaml`。正向 `expected.msg`，负向 `expected.error_msg`；负向 code/文案以联调为准。

---

## 4. 文件清单

| 动作 | 路径 |
|------|------|
| 新增 | `jkpt_api_test/yaml/test_enclosure_controller.yaml` |
| 新增 | `jkpt_api_test/testcases/test_enclosure_controller.py` |
| 不改 | `conftest.py`（只注入已有 fixture） |
| 不改 | `export_assert_util.py` |

---

## 5. 任务

### Task 1: YAML

- [ ] 按第 3 节原文落地；`enclosureName` 不得改回 `name`；名称禁止超 12 位的 `AUTO_ENC_` 前缀

### Task 2: testcase

- [ ] 方法 `test_enc_a_add` … `test_enc_g_delete`
- [ ] 每个接口的 `params` / `json` / path 与第 2 节一致
- [ ] `{{msg_test_terminal}}` 只在 d 用 fixture 替换
- [ ] class teardown 删除 cloned + 主 id
- [ ] `_assert_and_report` + KML 导出分支；无 token 导出先判断是否 JSON

### Task 3: 联调

- [ ] 确认创建是 query；`pointJson` 闭合四点
- [ ] 确认 `$.data.id` / `shareCode`
- [ ] 分享码正向 `28feceb1b1`；反向自己的码按实回填 expected
- [ ] 名称空 / 1 位 / 13 位的 code-msg 按实回填
- [ ] 跑：`$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest testcases/test_enclosure_controller.py -q --tb=short`

### Task 4: 验收

- [ ] 整文件无 `-k` 通过
- [ ] 人为让 c 失败再跑时，teardown 仍能删掉 a 创建的围栏（抽测一次即可）

---

## 6. 联调回填

| 项 | 计划假设 | 实际 |
|----|----------|------|
| 创建 | query `name` + `pointJson`，无其它字段 | 已确认 |
| 编辑 | path id + JSON `{name, pointJson}` | 已确认 |
| 绑设备 | JSON `{addrs: "sn"}` 字符串 | 已确认 |
| 列表 data | `$.data` 为数组 | 已确认 |
| shareCode | 创建响应 `$.data.shareCode` | 已确认 |
| 正向分享码 | 他账号 `28feceb1b1` 导入到本账号 | 已确认，会在本账号新建围栏 |
| 导出 | KML/XML 流，否则 JSON | 正向 KML 已过 |
| Header 是否够鉴权 | 先 Header | 已确认 |
| 空名称 | 1001 / 围栏名称不能为空,最长30个字 | 已确认 |
| 1 位 / 13 位名称 | 1001 / 围栏名称长度必须为2-12个字符 | 现网 code=0，已改为测 31 位 |
| 31 位名称 | 1001 / 围栏名称最长30个字符 | 已确认 |
| 非法 id | 1001 / 电子围栏不存在 | 已确认 |
| 非法码 | 1001 / 围栏不存在 | 已确认 |
| 反向分享码 | 自己的码业务失败 | 现网 code=0 会克隆，待产品确认 |
