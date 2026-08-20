# 对讲群消息接口测试 Implementation Plan（定稿版）

> **For agentic workers:** 本文剩余 `TBD-探针Sx` 是**硬闸门**。探针未跑完之前，**禁止**把 YAML `expected.code/msg` 或字段实名写成臆测值。实现时遵循 `skills/api-test-framework` + `.cursor/rules/jkpt-api-test.mdc`：只 `from common.*`、模式 B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result` 且必传 `biz_context`。一类一接口，叶子默认 `[caseN]`，**禁止**中文 `parametrize ids`。
>
> 来源：Apifox「Swagger3接口文档」tag **对讲群消息接口**（8 URL，其中 4 URL 属邀请通知域已由 `plan/intercom-group-tests.plan.md` 批 2 覆盖，本文只做剩余 4 个消息域 URL）
> 契约：OAS 于 2026-08-19 经 apifox-jkpt MCP 逐 `$ref` 拉取核实（路径 / 参数位置 / 响应 schema 均为原文，非推断）
> 业务事实：2026-08-19 主人访谈实锤（见 §1.4，**优先级高于探针预设**，探针只做复核）
> 前置计划：[intercom-group-tests.plan.md](intercom-group-tests.plan.md)（群生命周期 51 passed，§5 现网基线可直接继承）
> 状态：**已落地**（2026-08-20）。探针 S0~S6 实测完成 → §1.5 记录 4 处与预设的偏差、§6 全表填实测；实现 `testcases/test_intercom_message_controller.py` + `yaml/test_intercom_message_controller.yaml`，34 条（Im00 自检 1 / Im01 分页 16 / Im02 接收 7 / Im03 清群未读 5 / Im04 清所有未读 3 / Im05 状态 2）。表头「TBD-探针Sx」硬闸门已全部解除。

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

### 1.5 探针实测对 §1.4 的修正（2026-08-20 S0~S6，**实测优先于访谈预设**）

| # | 预设 | 实测 | 处置 |
|---|------|------|------|
| M1 | SOS 上报落库 `sendType=ALARM` | **`TEXT`**，`content` = `遇到危险，触发SOS报警，请求帮助!` / `…触发落水报警…`，带 `loc.lng/lat` + `wgs84Lng/Lat` | sendType 断言收窄为 **`{TEXT, VOICE}`**；ALARM 现网不产生，B7 的"不可造"名单加上 ALARM |
| M2 | B3 心跳/取消都不产消息 | 对讲群侧成立（零增长）；**SOS 群侧心跳会产一条 TEXT**，取消(flag=10)两侧都不产 | 零增长断言只对对讲群；双群一致性把"SOS 侧多出条数"记为观察项 |
| M3 | B5 flag=10 结束 SOS 态 | **flag=0 心跳就把 SOS 群 status 打成 0**（正常位置上报即解除），flag=10 时已是 0 | 收尾仍成立（跑完 SOS 态必已结束），但归因写心跳；语音仍单落对讲群 |
| M4 | B4 双账号可触发已读，readCount +1 | **消息级 `readCount/unreadCount/failCount` 恒 0，`receive/info` 三列表恒空**——B 棒入群成为成员、B 侧 `clear/unread` 之后仍全 0 | 已读明细现网未落地：case0a 按计划降级条款改为**留痕 + 成员侧查询等价性**断言 |
| M5 | 未读靠消息级 `unreadCount` | 未读是**聊天项级**：`platform-chats/chat-item/page` 的 `unreadNum`（GROUP 项的 `id` 就是对讲群 id，可按 `itemName=群名` 过滤）。A 侧查 `message/page` **不**清未读，只有 `clear/unread` 会清 | `clear/unread` 断言口径改为 chat-item `unreadNum` 归零 + 消息级计数不变 |
| M6 | 越权参考 `close` 的 `999 只有群主` | **消息域 4 口全无权限校验**：B 账号（非群成员）`message/page` 能读到全部消息内容、`receive/info` code=0、`clear/unread` code=0（不影响群主侧未读） | 按实测写 `code=0`，差异以「缺陷留痕」行呈报，**不臆造失败码**；建议提缺陷 |

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

## 6. 现网基线（2026-08-20 探针 S0~S6 实测填满）

| 项 | 探针 | 结论 |
|----|------|------|
| A 账号余额 `balanceAfter`（闸门） | S0 | 探针起点 **5112**；一轮造数（建群 20 + 邀 1 台 10）实扣 30，B 棒入群再 10。**注意**：终端上行本身也在消耗群的位置/语音额度，整轮跑完余额跌幅大于纯 30/40，闸门取 200 仍安全 |
| SOS 求救群 与 对讲群 是否互斥（同一根棒） | S0 | **不互斥**：同一根棒可同时挂 SOS 伴生群 + 对讲群（flag=1 建 SOS 群时对讲群成员身份不受影响） |
| **双落群复核**：flag=1/2 消息两侧都在；cancel 后语音单落对讲群 | S1 | **成立**。SOS 侧 `emergency/chat/record/page` 与对讲群 `message/page` 同一条消息 `chatTime` 偏差约 13~20ms（断言容差取 5000ms）；语音（发于取消后）只在对讲群 |
| flag=0/10 零增长复核 | S1 | **对讲群侧成立**（total 2→2→2）；**SOS 群侧心跳会多一条 TEXT**（见 §1.5 M2） |
| SOS 群自动创建形态与捕获方式 | S1 | `emergency/chat/item/page?itemName=<sn>` 直接可查，`itemName` 形如 `SOS-<sn>-0001`，无需差集；status 1 → 心跳后 0 |
| `readCount` / `unreadCount` / `failCount` 语义 | S3 | **恒 0**（终端上行消息无接收方明细），2 个成员时亦然 |
| **B 账号侧触发已读的手段** | S3 | **无**：B 入群成为成员并调 `clear/unread` 后，消息级计数与三列表仍全空（§1.5 M4） |
| `receive/info` 三列表与 page 计数是否严格相等 | S3 | **严格相等**（都是 0/空），断言按"长度 == 对应 Count"写 |
| `TEXT` 是否必带 `loc`；`VOICE` 的 `fileSize` / `content` 实形 | S3 | TEXT（SOS 上报）**必带** `loc.lng/lat` + `wgs84*`；VOICE `fileSize=3`（秒）、`content` 为 `oss…` 十六进制短音文件 id、`loc=null`；两类 `avatarInfo.memberAccount` == 上报终端 sn，`memberAccountType=TERMINAL_DEVICE` |
| 分页负向码 | S4 | `pageSize=0` → **999 失败**；`pageSize=-1` / `page=0` / `page=-1` → **code=0**（按默认处理，等价首页/全量）；`page` 超界 → code=0 + `items: []` 且 total 不变；群 id 空串 / `INVALID_GROUP` / `0` → **3003 群聊不存在**；缺 `intercomGroupId` → **1001 请检查请求参数是否正确**；无 token → **3001 没有访问权限**；`pageSize=abc` → 1001 + Java 类型转换异常原文（msg 含 `pageSize`，不做全等断言） |
| 假 `intercomMessageId` 返回形态 | S4 | 假 id 与空串均 **code=0 + 三空列表**（不是 3003）；缺参 1001；无 token 3001 |
| `clear/unread` 真实清的是什么 | S5 | **聊天项级**：`chat-item` 的 `unreadNum` 1→0，消息级计数不动；重复调用 code=0 且不回涨；假群 id / `0` 也返回 **code=0**（后端不校验群存在，与 `page` 的 3003 不一致，留痕） |
| `clear/all-unread` 的 `data:int` 语义 + 幂等第二次的值 | S5 | `data` = **本次清掉的聊天项数**（首次 1，二次 **0**）；清完 A 侧全部 GROUP 项 `unreadNum` 归零 |
| B 账号越权查 A 群消息的码 | S6 | **无拦截**：`page` code=0 且返回全部消息内容、`receive/info` code=0、`clear/unread` code=0（不影响群主侧 unreadNum）、`remainder` code=0。与 `close` 的 `999 只有群主` 形成对照——**建议提缺陷** |
| close 后 / delete 后查消息的形态 | S6 | close 后：消息全量仍可查（total 不变），chat-item 仍在但 `groupStatus=0`；delete 后：**消息仍可查（软删）**，chat-item 从列表摘除，`receive/info` / `clear/unread` 仍 code=0 |

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

**已按默认值执行（2026-08-20「执行该计划」指令 = 采纳 §7 默认取值）**：

| # | 问题 | 落地取值 |
|---|------|----------|
| 7-5 | 星豆预算 | **40 豆档**（1 群 + A棒C + B棒4 入群）。跨群 `all-unread` 语义已由 S5 单群证据定性（`data` = 本次清掉的聊天项数、二次为 0）+ A 账号既有存量群交叉验证，**不再为此多造一个 4 分钟上行链的群**（省 20~30 豆与 4 分钟） |
| 7-8 | 负向边界深度 | **全打**：分页边界（page=0/-1/超界、pageSize=0/-1）+ 非法类型 `pageSize="abc"` 走用例内特殊分支（后端返 Java 转换异常原文，只断 code=1001 + msg 含 `pageSize`） |
| 7-9 | 探针许可 | **已执行** S0~S6（两轮探针，自造自清：群 close+delete、A/B 棒与测试分组删除，无残留）。§6 全表已填实测 |

---

## 8. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/intercom-message-tests.plan.md` | 本文 |
| `yaml/test_intercom_message_controller.yaml` | 4 组 `intercom_msg_*_cases` |
| `testcases/test_intercom_message_controller.py` | `_ImHelpers` + `TestIm00`–`TestIm05` |
| `conftest.py` | +`rescue_sat_terminal_c`、+`rescue_sat_terminal_b4`、+`intercom_message_group` |
| `plan/intercom-group-tests.plan.md` | §0 挂起表更新：消息域 4 口移交本文 |

### 任务序（每步都有 gate，不许跳）

- [x] **Task 0** 三问按 §7 默认取值拍板（2026-08-20）
- [x] **Task 1** 探针 S0：余额 5112（>200 闸门）；SOS 群与对讲群**不互斥**，§5.1 的独立棒方案保留
- [x] **Task 2** 探针 S1：5 次上行逐条实打——双落/取消后语音单落/对讲群零增长成立；`sendType=TEXT`（非 ALARM）、SOS 群由心跳解除，两处偏差见 §1.5
- [x] **Task 3** 探针 S3–S6：§6 全表已填（已读明细现网未落地；clear 清的是聊天项级未读；消息域无越权拦截）
- [x] **Task 4** conftest 加 `rescue_sat_terminal_c`（A 侧造棒逻辑抽成 `_provision_a_rescue_stick`）、`rescue_sat_terminal_b4`、`intercom_message_group`（含逐步落库闸门、SOS 群捕获、失败附 10304 会话/消息日志）
- [x] **Task 5** YAML 定稿（每条 `expected` 出处 = §6 实测）+ `TestIm00` / `TestIm01`（16 条：正向/字段级/双群一致性/零增长/分页守恒/超界/回落/pageSize 边界与非法类型/越权/假群/空串/缺参/无 token）
- [x] **Task 6** `TestIm02ReceiveInfo`（交叉一致性 + 双账号已读**降级为留痕**：B棒4 入群 → B 侧 clear → 计数仍全 0）
- [x] **Task 7** `TestIm03ClearUnread` / `TestIm04ClearAllUnread`（幂等 + chat-item `unreadNum` 双证据 + 消息级计数不变 + all-unread 二次为 0）
- [x] **Task 8** 越权与状态维度：越权做成 `code=0` + 缺陷留痕行；`TestIm05StateAfterCloseDelete` 覆盖 close 后 / delete 后仍可查（delete 后注销 cleaner）
- [x] **Task 9** 整文件回归：34 条，类序 Im00→Im05，叶子 `[caseN]`。两轮现网：
  - 第一轮 30 passed / 4 failed（假群 `error_msg` 写成「群聊不存在」、extract 残留上一轮 `im_message_id`）
  - 修 YAML 文案为「对讲群不存在」+ `live_message_id` 兜底后第二轮 **33 passed / 1 failed**：`test_page[case7]` 主断言已 200，辅助「首页基线」GET 被远端 `RemoteDisconnected`；同用例第一轮 PASSED。辅助 GET 已加 1 次连接重试；用上一轮软删群号轻量复核 `page=-1` 与 `page=1` 三条 id 一致（`CASE7_RECHECK_OK`）。**未再付 40 豆整文件第三轮**
- [x] **Task 10** 回填本文 §1.5/§6/§7 + `plan/intercom-group-tests.plan.md` §0 解除挂起

**实现相对计划的偏差（有意，非漏做）**：

1. `TestIm05StateAfterCloseDelete` 在**造数主群**上做 close+delete（计划 §5.3 原写"群不做用例内 close/delete，全交 cleaner"）——另造第二个带消息的群要再付 4 分钟上行链 + 20~30 豆，收益为零；删成功即 `intercom_group.unregister(gid)`，无双重收尾
2. 「已退出群成员视角查询」（§4.6 第三条观察项）未做：需要先把成员移出群再查，与 Im05 的 close/delete 抢同一个群且属对讲群域动作，留待与对讲群 `addr/remove` 用例合并时一起看
3. `clear/all-unread` 的跨群语义没造第二个群（见 §7-5）

---

## 9. 与现有模块的关系

- **对讲群模块**（`test_intercom_group_controller.py`）：本文消费其 create / invitation / terminal/list / remainder 作**前置**，只读不改其用例；负向码 `3003` / `3001` / `1001` 直接继承 §1.3
- **求救群聊模块**（`test_emergency_chat_controller.py`）：本文的 `record/page` ↔ `message/page`、`read/list` ↔ `receive/info`、`clear/unread` 三组**同构**，实现风格与扩展断言直接照抄；SOS 群侧数据（双群一致性）消费其 item/page 口。**设备隔离**（§5.1）
- **星豆模块**：只在余额闸门读 `GET /star-bean/transaction/page`，不做扣费流水比对
- **`common/cleanup`**：复用 `IntercomGroupCleaner`（tier 100）与 `rescue_chat` cleaner，**不新增 cleaner**
