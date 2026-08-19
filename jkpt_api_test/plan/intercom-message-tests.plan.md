# 对讲群消息接口测试 Implementation Plan（定稿版）

> **For agentic workers:** 本文剩余 `TBD-探针Sx` 是**硬闸门**。探针未跑完之前，**禁止**把 YAML `expected.code/msg` 或字段实名写成臆测值。实现时遵循 `skills/api-test-framework` + `.cursor/rules/jkpt-api-test.mdc`：只 `from common.*`、模式 B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result` 且必传 `biz_context`。一类一接口，叶子默认 `[caseN]`，**禁止**中文 `parametrize ids`。
>
> 来源：Apifox「Swagger3接口文档」tag **对讲群消息接口**（8 URL，其中 4 URL 属邀请通知域已由 `plan/intercom-group-tests.plan.md` 批 2 覆盖，本文只做剩余 4 个消息域 URL）
> 契约：OAS 于 2026-08-19 经 apifox-jkpt MCP 逐 `$ref` 拉取核实（路径 / 参数位置 / 响应 schema 均为原文，非推断）
> 业务事实：2026-08-19 主人访谈实锤（见 §1.4，**优先级高于探针预设**，探针只做复核）
> 前置计划：[intercom-group-tests.plan.md](intercom-group-tests.plan.md)（群生命周期 51 passed，§5 现网基线可直接继承）
> 状态：**已定稿**（原 §7 九问中 6 问已由主人拍板，剩 3 问见 §7）

**Goal:** 把对讲群「消息域」4 个口从挂起状态收口：`message/page`（主口）为核心，`receive/info` 提供已读明细做交叉验证 + **双账号真实触发已读**，`clear/unread` / `clear/all-unread` 提供未读写侧闭环（含幂等）。核心命题不是「接口 200」，而是**消息真的能被查出来、双落群两侧一致、分页守恒、未读数与已读明细互相对得上、清未读后真归零**。

**Architecture:** 模式 B′。前置造数走新 session fixture `intercom_message_group`（建群 → 邀救援棒入群 → **5 次终端上行（位置族×4 + 语音×1）** → 轮询 `message/page` 确认落库），群号/消息号经 `extract.yaml` 传给下游类。群收尾复用现成 `IntercomGroupCleaner`（tier 100，close→delete），SOS 态用 **reportFlag=10 一石二鸟收尾**。

**Tech Stack:** pytest + YAML + `BaseRequest` + Allure + `common.cleanup` + `rescue_client`（10304 上行模拟）

---

## Global Constraints

- 只 `from common.*`；禁止 `api_test_framework` / 模式 C
- **Authorization 只走 Header**（与 `test_intercom_group_controller.py` 的 `_IgHelpers.headers` 一致；OAS 虽标 `in: query required`，对讲群家族已实证 header 生效）。`no_auth: true` 只剥 `Authorization`，保留 `Accept-Language`
- 正向 `expected.msg`，负向 `expected.error_msg`；禁止正向写 `error_msg: "成功"`
- 4 个口**全部 query `params=`**（OAS 核实：无一个是 body）
- YAML 不写真实群号 / 消息号 / 卡号；正向用 `{{im_group_id}}` / `{{im_message_id}}`，**负向一律字面量假值**（`0` / `INVALID_GROUP` / `nonexist_msg_999`）——负向依赖 extract 会被 skip 吞掉
- `json_data = res.json()` 每请求只调一次；`send_request(..., log_level="none")`
- **禁 pytest-xdist**（extract 链 + 未读状态是全局单向状态机）；**clear/unread / clear/all-unread 叶子禁 rerun**（重试会污染后续未读断言）
- 断言一律 `assert_api_result(...)` 且**必须传 `biz_context`**（至少 `{"请求参数": params}`）
- 扩展断言（结构 / 分页数学 / 交叉一致性）走 `_ImHelpers.report_extra` 同款：成功一行结论，失败才打全表
- **执行顺序锁死**：读侧（page / receive/info）的未读断言必须**先于** clear 系执行。文件内类定义序 = 执行序：`Im00 → Im01 → Im02 → Im03 → Im04`
- **60s 上报间隔是硬约束**（conftest `emergency_chat_voice` 注释载明，2026-08-17 主人定稿）：同一终端两次上行间隔必须 > 60s

---

## 0. 范围与 URL 清单

Apifox tag **对讲群消息接口** 共 8 URL，其中 4 个是邀请通知域（`invitation/notice/list`、`invitation/pending/count`、`invitation/handler`、`send/invitation/list`），**已由对讲群计划批 2（TestIg11/Ig12）覆盖，本文不重复**。

本文覆盖剩余 4 个：

| 序 | 类名 | 方法 | 路径（前缀 `{base_url}/api/monitor`） | OAS summary | 响应 schema |
|----|------|------|------|-------------|-------------|
| 0 | `TestIm00FixtureChain` | — | — | 造数链自检（非接口） | — |
| 1 | `TestIm01Page` | GET | `/intercom/message/page` | 分页获取对讲群聊天消息记录 | `CommonResult«PageResult«IntercomMessageVo»»` |
| 2 | `TestIm02ReceiveInfo` | GET | `/intercom/message/receive/info` | 消息接收列表 | `CommonResult«IntercomMessageReceiveInfoVo»»` |
| 3 | `TestIm03ClearUnread` | PUT | `/intercom/message/clear/unread` | 清群聊未读数量 | `CommonResult«string»` |
| 4 | `TestIm04ClearAllUnread` | PUT | `/intercom/message/clear/all-unread` | 清空所有对讲群未读数量 | `CommonResult«int»` |

**明确不做：**

- 邀请通知域 4 口（已在对讲群批 2）
- `DELETE /api/monitor/platform-chats/chat-item` 与 `GET /platform-chats/chat-item/page` 的全量用例——属「平台聊天管理接口」tag，另立计划；但本文**将其作为交叉验证证据源**（`chatItemType=GROUP&itemName=AUTO_IM_{ts}` 查 `unreadNum` / 群 `id`），不算覆盖
- 语音内容正确性（短音文件播放 / 增强）——`content` 只断非空，不断音频内容
- 星豆充值链 / 支付

---

## 1. 契约事实

### 1.1 `GET /intercom/message/page`

| 参数 | 位置 | 必填 | OAS 描述 | 类型 |
|------|------|------|----------|------|
| `Authorization` | query | required | 授权码 | string |
| `intercomGroupId` | query | **required** | 群聊Id | string |
| `page` | query | 否 | 页码。默认第1页 | int32 |
| `pageSize` | query | 否 | 页大小，默认100条 | int32 |

响应 `data`：`PageResult«IntercomMessageVo»` = `{items: IntercomMessageVo[], total: int64, totalPage: int64}`

`IntercomMessageVo` 全字段（12 个，OAS 原文描述）：

| 字段 | 类型 | OAS 描述 |
|------|------|----------|
| `id` | string | 消息ID |
| `groupId` | string | 群ID |
| `chatTime` | int64 | 消息时间（用于时间线展示） |
| `sendType` | enum | **枚举 = `ALARM` / `IMAGE` / `OK` / `TEXT` / `VOICE`** |
| `content` | string | 消息内容；语音时为可播放短音文件ID |
| `fileSize` | int32 | 语音时长（秒） |
| `readCount` | int32 | 已读人数 |
| `unreadCount` | int32 | 未读人数，**0=所有人已读** |
| `failCount` | int32 | 失败人数 |
| `reportId` | string | 上报ID（用于发送端标识的消息） |
| `loc` | `LocationRespDto` | 位置信息 |
| `avatarInfo` | `AvatarInfoDto` | 发送方头像信息（SOS发起设备） |

### 1.2 其余 3 口

| 口 | 参数（除 `Authorization`） | 响应 data |
|----|--------------------------|-----------|
| `receive/info` | `intercomMessageId`（**required**） | `{readList[], unreadList[], failList[]}`，元素 `ReceiverDto` |
| `clear/unread` | `intercomGroupId`（**required**） | string |
| `clear/all-unread` | **无业务参数** | int（语义 **TBD-探针S5** 实测） |

### 1.3 可继承的现网基线（来自对讲群计划 §5，已实测，无需重探）

- 建群扣 **20 豆**（`CREATE_GROUP`）；邀成员扣 **10 豆/台**（`INVITE_MEMBER`），邀请即扣
- 群名上限 **15 字符**；A 账号余额约 **9714 豆**
- 假群 id → **`3003 群聊不存在`**；无 token → **`3001 没有访问权限`**；参数缺失 → **`1001 请检查请求参数是否正确`**
- `invitation` 请求体 `addrInfos: [{"addr": sn}]` 即可，A 邀自己的棒 `confirm=1` 直接入群；**跨账号邀请（B 棒）走 PENDING 通知，需 B 账号 `handler(AGREED)` 闭环入群**（既有 B 支路已验证）
- `remainder` 返回 `maxMembers`（2026-08-19 实测 = 3）、`allRemainingVoiceNumber` / `allRemainingPositionNumber`
- 关群 `close` 后 `remainder` 仍可查、`status=0`；`delete` 后 `remainder` 仍可查
- 越权先例：对讲群 `close` 非群主实测 `999 只有群主可以查看详情`

### 1.4 主人访谈实锤业务事实（2026-08-19，优先级最高）

| # | 事实 | 对计划的直接影响 |
|---|------|----------------|
| B1 | **双落群**：终端发 reportFlag=1/2 会自动创建 SOS 群，消息**同时落 SOS 群 + 手动对讲群**；SOS 群未结束时，语音上报也**双落** | 新增双群一致性断言（§4.2 case2a）；造数链要把 SOS 群纳入管理（§3.3 ⑥） |
| B2 | **上行矩阵**：位置族 reportFlag=**0/1/2/10 四次 + 语音族一次，共 5 次上行** | 造数定稿为 5 次上行（§3.3 ③），单群至少 3 条消息，分页守恒的"凑数成本"TBD 消解 |
| B3 | **只 SOS+语音入消息流**：心跳(0)/取消SOS(10) 不生成消息记录 | 心跳与取消后 items 零增长写为**负向断言**（§4.2 case1a） |
| B4 | **双账号已读验证**：B 账号真实触发已读，前后对比 readCount/unreadCount 变动 | receive/info 新增写侧验证腿（§4.3 case0a） |
| B5 | **cancel-sos 收尾**：reportFlag=10 既结束 SOS 态又是位置族第 4 次上行，一石二鸟 | 收尾清单加入"结束 SOS 群"（§5.3） |
| B6 | 造数**全走 10304 上行**（C4 h5-mock 已被否决）；单终端串行 session 级 | S1 探针范围收缩（§3.1） |
| B7 | IMAGE/OK/TEXT 三类 sendType **协议不可造** | 三类标记"本期不覆盖、留痕"；sendType 断言收窄为 ALARM/VOICE |
| B8 | 消息查询前需**轮询等待落库**（10304 异步 UDP，发送成功 ≠ 落库） | 造数链落库闸门不可省（§3.3 ④） |

---

## 2. 三条传值通道

### 通道 A — Fixture

| Fixture | 作用域 | 状态 | 说明 |
|---------|--------|------|------|
| `base_url` / `auth_headers` | session | 现成 | — |
| `rescue_client` | session | 现成 | 10304 上行模拟（`send_position` / `send_speech` / `send_cancel_sos`） |
| `rescue_sat_terminal` | session | 现成 | A 名下救援棒。**冲突警告见 §5.1**，默认不用 |
| `rescue_sat_terminal_c` | session | **待新增** | A 名下**独立**棒，专供对讲群消息域，与求救群聊隔离。实现照抄 `rescue_sat_terminal`（`mock-in-storage` → `POST groups/{one_id}/terminals`），仅换 label |
| `intercom_message_group` | session | **待新增** | 造数主链，见 §3.3 |
| `auth_headers_b` | session | 现成 | 双账号已读验证（§4.3）+ 越权用例（§4.6）注入 |

### 通道 B — extract.yaml

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `im_group_id` | `TestIm00` 消费 fixture 后写（只写一次） | Im01 / Im03 正向 | 消息域主群 |
| `im_message_id` | `TestIm01` 正向首条消息 `id`（只写一次） | `TestIm02ReceiveInfo` 正向 | 消息 id |
| `im_sos_group_id` | 造数链发现 SOS 群时写 | 双群一致性断言 | SOS 侧群标识（可选用） |

**约定**：fixture 返回 dict，**由 testcase 写 extract，不在 conftest 写**（`.cursor/rules/jkpt-api-test.mdc` 明令）。负向 case 一律字面量，不依赖任何 extract。

### 通道 C — YAML 字面量

| YAML 字段 | 含义 |
|-----------|------|
| `scenario` | 分支开关（`positive` / `paging_conserve` / `page_overflow` / `zero_growth` / `idempotent` / `no_auth` / `cross_account`…），沿用 `test_emergency_chat_controller.yaml` 风格 |
| `intercomGroupId` | 正向 `{{im_group_id}}`；负向字面量 |
| `intercomMessageId` | 正向 `{{im_message_id}}`；负向字面量 |
| `page` / `page_size` | 分页边界值 |
| `no_auth` | 剥 token 开关 |

---

## 3. 造数链（5 次上行定稿）

### 3.1 造数路径：已定，探针只做复核

主人已拍板**全走 10304 终端上行**（C4 h5-mock 否决）。OAS 侧背景留档：求救群聊有 `POST /emergency/chat/send`，对讲群**没有**平台侧发消息口，消息只能由设备上行产生——这一定性不变。

S1 探针从「四选一判定」收缩为**复核性实打**：

| 上行 | 手段 | 预期 sendType | S1 复核点 |
|------|------|----------------|-----------|
| flag=1 按键SOS | `send_position(sn, 1)` | ALARM（**双落**：SOS群+对讲群） | 双落是否如期；SOS 群自动创建形态 |
| flag=2 落水SOS | `send_position(sn, 2)` | ALARM（双落） | 同上 |
| flag=0 心跳 | `send_position(sn, 0)` | **不产消息**（B3） | items 零增长 |
| flag=10 取消SOS | `send_cancel_sos(sn)` | **不产消息**，SOS 群结束（B5） | SOS 群状态翻 0 |
| U5 语音 | `send_speech(sn)` | VOICE（SOS 群未结束则双落） | 落群归属随取消时点变化 |

**S1 若实测与 B1/B3 不符（如消息只落单群）：停下呈报，不自行改断言。**

### 3.2 60 秒间隔约束下的执行形态（已定稿）

- **单终端串行、session 级**（主人拍板）：5 次上行 4 个间隔 > 60s，总耗时约 3~4 分钟
- 上行次序固定：`flag=1 → (60s) flag=2 → (60s) flag=0 → (60s) flag=10 → (60s) 语音`
  - 语音放 cancel-sos **之后**：此时 SOS 群已结束，语音**单落对讲群**——既验证「取消后单落」的时序行为，又避免测试群消息依赖 SOS 群存活状态
  - 若 S1 实测取消后语音不进对讲群，则调整时序（语音放取消前、双落）并呈报
- 单群最终消息数 = **ALARM×2 + VOICE×1 = 3 条**，满足分页守恒（pageSize=1 取三页 / pageSize=2 取两页）的最低需求
- 原「不同终端是否也受 60s 约束（TBD-S2）」**不再需要**——单终端串行已定，不依赖该结论

### 3.3 `intercom_message_group` fixture 目标形态

```
① PUT  /intercom/group/create?intercomGroupName=AUTO_IM_{ts}   → 群 id（扣 20 豆）
   └ 成功即 register_intercom_group(group_id)  ← 副作用落地即注册（tier 100，close→delete）
② POST /intercom/group/invitation  json={"intercomGroupId": gid,
                                         "addrInfos": [{"addr": sn_c}], "force": false}
   → confirm=1 直接入群（扣 10 豆）；GET /intercom/group/terminal/list 复核该 addr 在列表
③ 5 次上行（§3.2 次序，间隔 >60s）：
   A 棒 sn_c：flag=1 → flag=2 → flag=0 → flag=10 → 语音
   ⚠️ 若双账号已读验证（B4）需要 B 棒在群内：跨账号邀请走 PENDING，
     B 账号 handler(AGREED) 闭环后再上行——是否需要 B 棒入群见 §4.3
④ 落库闸门：轮询 GET /intercom/message/page?intercomGroupId=gid（3 次 × 2s）
   直到 items 非空且含 ALARM；超时 pytest.fail 并附 rescue_client.session_records /
   message_logs 归因
⑤ SOS 群登记：flag=1 后轮询 /emergency/chat/item/page?itemName=sn_c 捕获 SOS 群
   chatItemId（差集法：与上行前存量比对，新出现即本次），写入 extract.im_sos_group_id；
   若用于双群一致性断言，登记到求救群 cleaner
⑥ 返回 {"groupId":…, "sn":…, "messageIds":[…], "sendTypes":[…], "groupName":…,
        "sosChatItemId":…}
```

**纪律**：发送成功 ≠ 落库（B8），第 ④ 步闸门不可省。

---

## 4. 每口：参数怎么传 / 前置是什么 / 断什么

### 4.1 `TestIm00FixtureChain` — 造数链自检（无 YAML）

**前置**：`intercom_message_group`
**断言**（纯 Python assert，不走 `assert_api_result`，与 `TestEc00FixtureChain` 同款）：

- `groupId` 非空 → 写 `extract.im_group_id`
- `terminal/list` 含造数棒 `sn`（真入群，不是 `confirm=1` 的一面之词）
- `message/page` 的 `items` 长度 ≥ 3 且含 ALARM 与 VOICE（B2/B3 的直接核验）
- `remainder.status == 1`（群活跃）

### 4.2 `TestIm01Page` — GET `/intercom/message/page`

`params = {"intercomGroupId": <gid>, "page": case.page, "pageSize": case.page_size}`；`headers = auth_headers`（`no_auth` 时剥 Authorization）。

| # | case（`scenario`） | 参数 | 前置 | 断言 |
|---|---|---|---|---|
| 0 | 正向-默认分页（`positive`） | `{{im_group_id}}`, page=1, pageSize=10 | Im00 通过 | **信封** `code=0 / msg=成功`；**结构** `data.items` 是 list、`total` / `totalPage` 是 int；**内容** `len(items)>=3`；每条 `groupId == 请求 gid`（不串群）、`id` 非空、`sendType ∈ {ALARM,VOICE}`（B7 收窄）、`chatTime` 为 13 位毫秒级 int；首条 `id` → 写 `extract.im_message_id` |
| 1 | 正向-字段级（`field_shape`） | 同上，pageSize=100 | 同上 | `ALARM` → `loc` 非空（**TBD-探针S3** 确认是否必带）；`VOICE` → `fileSize` 为正 int 且 `content` 非空（OAS：语音时 content 是短音文件ID） |
| 1a | 正向-双群一致性（`dual_group_consistency`，**B1 新增**） | 同 case0 + SOS 群侧 | Im00 且 `im_sos_group_id` 已写 | 同一终端同期消息，SOS 群侧（`/emergency/chat/item/page` 或其 record 口）与对讲群侧 `message/page` 的 sendType/条数**一致**（flag=1/2 两条 ALARM 两侧都在）；语音（发于 cancel 后）**只在对讲群侧**。两侧 `chatTime` 交叉验证。若 `im_sos_group_id` 未提取到 → `pytest.skip` 不算失败 |
| 2 | 边界-零增长（`zero_growth`，**B3 新增**） | `{{im_group_id}}`, pageSize=100 | Im00 通过 | 记录当前 `total`；断言心跳(flag=0)与取消(flag=10) 发送时刻**早于** Im00 的消息已全部落库——即本 case 断言当前 items 中**不存在**由 flag=0/10 产生的新消息：`total` 与 case0 一致且每条 `sendType ∈ {ALARM,VOICE}`。（flag=0/10 在造数期已发，此处以结果反证零增长） |
| 3 | 边界-分页守恒（`paging_conserve`） | pageSize=1，遍历 page=1..totalPage；再 pageSize=2 复验 | 群内 ≥3 条（B2 保证） | 各页条数 = min(pageSize, total-(page-1)*pageSize)；`id` 无重叠无遗漏、并集 == 全量 id 集；`total` / `totalPage` 各页一致；`totalPage == ceil(total/pageSize)`；末页不满页行为正确 |
| 4 | 边界-页码超界（`page_overflow`） | page=9999, pageSize=10 | — | `code=0` 且 `items` 为空列表（**不是** null / 不是报错）；`total` 与正向一致 |
| 5 | 边界-pageSize=0 | pageSize=0 | — | **TBD-探针S4**：可能 `code=0` 走默认 100，也可能 `1001`。禁止预填 |
| 6 | 边界-page=0 / page=-1 | page=0 / -1 | — | **TBD-探针S4** |
| 7 | 负向-假群 id | `intercomGroupId: "INVALID_GROUP"` | — | 预期 `3003 群聊不存在`（继承 §1.3），**S4 复核本口是否同码**——若本口返回 `code=0` 空列表（`emergency/chat/record/page` 就是这行为），按实测改，不硬套 |
| 8 | 负向-缺 `intercomGroupId` | 不传该键 | — | 预期 `1001 请检查请求参数是否正确`（**S4 复核**） |
| 9 | 负向-群 id 空串 | `intercomGroupId: ""` | — | **TBD-探针S4**（空串与缺参常不同码） |
| 10 | 负向-无 token | `no_auth: true` | — | `3001 没有访问权限` |

### 4.3 `TestIm02ReceiveInfo` — GET `/intercom/message/receive/info`

`params = {"intercomMessageId": <mid>}`。**前置：Im01 已写 `im_message_id`**；未写则 `pytest.skip("消息 id 未提取")`（照抄 `TestEc08ReadList`）。

| # | case | 断言 |
|---|---|---|
| 0 | 正向 | `code=0`；`data` 含 `readList` / `unreadList` / `failList` 三键且均为 list；**交叉一致性**：三个列表长度与 `message/page` 同一条消息的 `readCount` / `unreadCount` / `failCount` 对齐——先按「长度严格相等」打一枪，若不等则降级为「已读∩未读 = ∅ 且 已读∪未读 ⊆ 群成员集」并把实测差异记 §6（降级口径由 S3 决定，**不是**先写宽松断言糊过去） |
| 0a | 正向-双账号已读触发（`read_transition`，**B4 新增**） | 造数链中 B 棒入群（invitation PENDING → B 账号 handler(AGREED)）。本 case：B 账号（`auth_headers_b`）侧触发已读（进入消息/清未读动作，具体触发手段 **TBD-探针S3**：可能是 B 侧调 `clear/unread` 或页面行为）；前后对比 `receive/info` 的 `readList`/`unreadList` 与 `message/page` 的 `readCount`/`unreadCount`：readCount **增 1**、unreadCount **减 1**，且 B 的 addr 从 unreadList 移入 readList。若 S3 实测 B 侧无法触发已读（如 app 端行为），降级为记录性断言并呈报 |
| 1 | 负向-假消息 id | `nonexist_msg_999` → **TBD-探针S4**（`3003` 还是 `code=0` 空列表） |
| 2 | 负向-缺参 | 不传 → `1001`（**S4 复核**） |
| 3 | 负向-无 token | `3001` |
| 4 | 负向-越权（§4.6） | 用 `auth_headers_b` 查 A 群的消息 id → **TBD-探针S6** |

### 4.4 `TestIm03ClearUnread` — PUT `/intercom/message/clear/unread`

`params = {"intercomGroupId": <gid>}`，method `put`。**必须在 Im01 / Im02 之后执行**（会把未读清零）。

| # | case | 断言 |
|---|---|---|
| 0 | 正向 | `code=0`；**数据往返**：回查 `message/page` 本群消息 `unreadCount` 变化 + **双证据源**：`platform-chats/chat-item/page?chatItemType=GROUP&itemName=AUTO_IM_{ts}` 的 `unreadNum` 前后对比。⚠️ **语义未知点**：清的是「我（群主）对别人消息的未读」还是「别人对我消息的未读」？**TBD-探针S5**——若消息级 `unreadCount` 不变而 `chat-item` 的 `unreadNum` 归零，说明该口清的是**聊天项级**未读，断言口径按实测重写，**不许把断言删掉了事** |
| 1 | 幂等-重复调用 | 二次调用 `code=0` 且未读仍为 0（不回涨、不翻倍），照抄 `TestEc07AllRead` 幂等写法 |
| 2 | 负向-假群 id | **TBD-探针S4** |
| 3 | 负向-缺参 | `1001`（S4 复核） |
| 4 | 负向-无 token | `3001` |

### 4.5 `TestIm04ClearAllUnread` — PUT `/intercom/message/clear/all-unread`

**无业务参数**，只有 token。**放最后**（全局清零，之后任何未读断言都失效）。

| # | case | 断言 |
|---|---|---|
| 0 | 正向 | `code=0`；`data` 是 int → **记录其语义**（清理群数？总条数？**TBD-探针S5**）；数据往返：A 账号侧 `chat-item/page` 所有 GROUP 项 `unreadNum` 全 0 |
| 1 | 幂等-重复调用 | `code=0`，且 `data` 值变化符合 S5 定下的语义（如「已清群数」则第二次应为 0）——**语义定了才写这条断言** |
| 2 | 负向-无 token | `3001` |

### 4.6 越权与状态维度（主人拍板：做）

- B 账号（非群成员）调 `message/page` 查 A 的群 → 期望被拒（码 **TBD-探针S6**；参考先例 `999 只有群主可以查看详情`）。注：若 B 棒已入群（§4.3 case0a），则 B 是成员——本 case 需用**未入群的第三视角**或改用 C 棒不入群版本，S6 时定
- 已 `close` 的群（`status=0`）查消息 → 是否仍可查（**TBD-探针S6**）。已 `delete` 的群查消息 → 形态（**TBD-探针S6**，观察项不写死）
- 已退出群成员视角查询 → 观察项（S6）

---

## 5. 副作用、联跑纪律与收尾

### 5.1 ⚠️ 设备互斥（最高优先级风险）

对讲群计划 §8 明载：**同一根救援棒同一时刻只能在一个活跃群**。而现成 fixture `emergency_chat_item` 会拿 `rescue_sat_terminal` 发 SOS 建**求救群**。

结论：本文**默认新增独立的 `rescue_sat_terminal_c`**，不复用 `rescue_sat_terminal`。

**但注意与 B1 的交互**：本计划的 flag=1/2 上行**必然自动创建 SOS 群**——即使不复用 `rescue_sat_terminal`，`_c` 棒也会同时挂一个 SOS 群和一个对讲群。主人实锤这是既定行为（双落），因此：
- SOS 群是**本计划预期内的伴生副作用**，造数链第 ⑤ 步捕获并登记（§3.3）
- 造数链第 ③ 步的 `flag=10` 取消 SOS 后，`_c` 棒的 SOS 态结束，**不会与求救群聊模块的 `rescue_sat_terminal` 冲突**（不同棒）
- S0 仍顺带实测「SOS 求救群与对讲群是否真互斥」——若实测互斥导致 flag=1 建群失败，停下呈报

### 5.2 星豆成本

单 session：建群 20 + 邀 1 台 10 = **30 豆**；若 B 棒入群（双账号已读）再 +10；若 §7-1 批准两群（验 `clear/all-unread` 跨群语义）则 **60–70 豆**。余额闸门沿用对讲群方案：**< 200 豆 → 全文件 skip 并提示充值**。

### 5.3 收尾（主人拍板：全量清理）

- **SOS 态**：造数链内 `flag=10` 已收尾（B5 一石二鸟）；SOS 群若已登记 cleaner 则随 session 清理
- 群：`register_intercom_group(group_id)` 建群成功即登记（tier 100，session 末 close→delete）。**本文的群不是被测对象，不做用例内 close/delete，全交 cleaner**（§4.6 状态用例若需 close，单独造第二个群）
- 设备：`rescue_sat_terminal_c` 照抄现有模板，入库成功即 `register_cleanup(f"rescue_chat_{sn}", …, tier=100)`
- 消息：**无删除接口**。消息随群 delete 一起消失，**接受残留**
- 10304 会话：`rescue_client` fixture 自带 `disconnect_all()`
- `clear/all-unread`：仅在 A 账号（测试账号）侧执行，不涉 B 账号

---

## 6. 现网基线（探针后填）

| 项 | 探针 | 结论 |
|----|------|------|
| A 账号余额 `balanceAfter`（闸门） | S0 | TBD |
| SOS 求救群 与 对讲群 是否互斥（同一根棒） | S0 | TBD |
| **双落群复核**：flag=1/2 消息两侧都在；cancel 后语音单落对讲群 | S1 | 主人实锤=双落/取消后单落，**探针复核** |
| flag=0/10 零增长复核 | S1 | 主人实锤=不入消息流，**探针复核** |
| SOS 群自动创建形态与捕获方式（差集法） | S1 | TBD |
| `readCount` / `unreadCount` / `failCount` 语义（是否 == 成员数、群主自己发的算不算已读） | S3 | TBD |
| **B 账号侧触发已读的手段**（clear/unread? 页面行为?） | S3 | TBD |
| `receive/info` 三列表与 page 计数是否严格相等 | S3 | TBD |
| `ALARM` 是否必带 `loc`；`VOICE` 的 `fileSize` / `content` 实形 | S3 | TBD |
| 分页负向码：pageSize=0 / page=0 / page=-1 / 空串群 id / 缺参 / 假群 id（本口） | S4 | TBD |
| 假 `intercomMessageId` 返回形态 | S4 | TBD |
| `clear/unread` 真实清的是什么（消息级未读 or 聊天项级未读） | S5 | TBD |
| `clear/all-unread` 的 `data:int` 语义 + 幂等第二次的值 | S5 | TBD |
| B 账号越权查 A 群消息的码（注意 B 是否已入群影响视角） | S6 | TBD |
| close 后 / delete 后查消息的形态 | S6 | TBD |

---

## 7. 需主人说话的点（原九问已答六问，剩三问）

**已拍板（2026-08-19 访谈）**：

- ~~7-1 范围~~ → **4 口全收**（含双群一致性、双账号已读）
- ~~7-2 造数路径~~ → **全走 10304 上行**（5 次矩阵），C4 h5-mock 否决
- ~~7-3 代码落地~~ → 沿用原建议**新建 `test_intercom_message_controller.py`**（消息域独立 suite）
- ~~7-4 设备资源~~ → 新增 `rescue_sat_terminal_c`（沿原建议）+ B 棒按需入群
- ~~7-6 断言深度~~ → **全要**（code+msg / 结构 / 字段级 / 分页数学 / 排序 / 跨接口一致性 / 双群一致性 / 双账号已读）
- ~~7-7 权限与状态~~ → **做**（B 越权 + close 后查 + 已退出视角观察）
- ~~7-0 业务文档~~ → 无文档，**以主人实锤（§1.4）+ 探针为准**

**仍待拍板**：

| # | 问题 | 默认取值 |
|---|------|----------|
| 7-5 | 星豆预算：30 豆（1 群 1 棒）/ 40 豆（+B 棒入群）/ 60–70 豆（2 群，验跨群 all-unread） | **60–70 豆**（`clear/all-unread` 的「all」不跨群就没验到） |
| 7-8 | 负向边界深度：+分页边界（已纳入 case5/6）/ 全打含 `pageSize="abc"` 等可能 400 的非法类型 | **+分页边界**；非法类型单独一条用例内特殊分支 |
| 7-9 | **探针许可**：是否允许现在就在现网跑 S0–S6（真扣豆、真建群、真造消息，探针群自造自清） | **需要主人明确批准**。未批准前 §6 空白项不填、YAML 对应 expected 不定稿 |

---

## 8. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/intercom-message-tests.plan.md` | 本文 |
| `yaml/test_intercom_message_controller.yaml` | 4 组 `intercom_msg_*_cases` |
| `testcases/test_intercom_message_controller.py` | `_ImHelpers` + `TestIm00`–`TestIm04` |
| `conftest.py` | +`rescue_sat_terminal_c`、+`intercom_message_group` |
| `plan/intercom-group-tests.plan.md` | §0 挂起表更新：消息域 4 口移交本文 |

### 任务序（每步都有 gate，不许跳）

- [ ] **Task 0** 主人拍板剩三问（尤其 7-9 探针许可）
- [ ] **Task 1** 探针 S0：余额闸门 + SOS/对讲群互斥实测。余额 <200 或互斥结论推翻 §5.1 → 停下呈报
- [ ] **Task 2** 探针 S1：5 次上行逐条实打，复核双落/单落/零增长/取消行为与 §1.4 一致。**不符 → 停下呈报**
- [ ] **Task 3** 探针 S3–S6：填满 §6 全表（重点：B 侧触发已读手段、clear 语义）
- [ ] **Task 4** conftest 加 `rescue_sat_terminal_c` + `intercom_message_group`（含落库闸门、SOS 群捕获与归因日志）
- [ ] **Task 5** YAML 定稿（所有 `expected` 有实测出处）+ `TestIm00` / `TestIm01`（含双群一致性 case1a、零增长 case2）
- [ ] **Task 6** `TestIm02ReceiveInfo`（含交叉一致性 + 双账号已读触发 case0a）
- [ ] **Task 7** `TestIm03ClearUnread` / `TestIm04ClearAllUnread`（含幂等 + 数据往返 + chat-item 双证据源）
- [ ] **Task 8** 越权与状态维度（按 S6 结果，注意 B 入群后的视角问题）
- [ ] **Task 9** 整文件回归：`pytest testcases/test_intercom_message_controller.py`，核对类序 Im00→Im04、叶子 `[caseN]`、session 末 cleaner 把群 close+delete、SOS 态已结束、无双重收尾噪音
- [ ] **Task 10** 回填 `plan/intercom-group-tests.plan.md` §0（消息域解除挂起）+ 本文 §6

---

## 9. 与现有模块的关系

- **对讲群模块**（`test_intercom_group_controller.py`）：本文消费其 create / invitation / terminal/list / remainder 作**前置**，只读不改其用例；负向码 `3003` / `3001` / `1001` 直接继承 §1.3
- **求救群聊模块**（`test_emergency_chat_controller.py`）：本文的 `record/page` ↔ `message/page`、`read/list` ↔ `receive/info`、`clear/unread` 三组**同构**，实现风格与扩展断言直接照抄；SOS 群侧数据（双群一致性）消费其 item/page 口。**设备隔离**（§5.1）
- **星豆模块**：只在余额闸门读 `GET /star-bean/transaction/page`，不做扣费流水比对
- **`common/cleanup`**：复用 `IntercomGroupCleaner`（tier 100）与 `rescue_chat` cleaner，**不新增 cleaner**
