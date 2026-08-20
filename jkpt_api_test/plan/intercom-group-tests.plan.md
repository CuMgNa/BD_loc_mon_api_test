# 对讲群接口测试 Implementation Plan

> **For agentic workers:** 先做第 0 节探针，**禁止**在探针前把 YAML `expected.code/msg` 写成臆测值。实现时遵循 `skills/api-test-framework`（只 `from common.*`、模式 A/B′、正向 `expected.msg` / 负向 `expected.error_msg`、`read_expected_msg` + `assert_api_result` 且必传 `biz_context`）。一类一接口，叶子默认 `[case0]`，**禁止**中文 `parametrize ids`。每个接口的 query / json 以本文 §2 为准。
>
> 来源：Apifox tag `对讲群接口`（13 URL）；业务依据 [对讲群-个人账号邀请成员核心流程.md](../../skills/output/runtime/对讲群-个人账号邀请成员核心流程.md)（下称「业务文档」）
> 契约：Apifox「Swagger3接口文档」刷新时间 **2026-08-18T05:51:19.205Z**
> 主人拍板（2026-08-18 访谈）：全 13 URL 规划、两批执行收官；接受扣豆自造自清；A+B 双支路；消息域与换群并发挂批 2 尾/挂起；群收尾用例内 close→delete + registry 兜底

**Goal:** 对讲群全生命周期闭环：cost 查费 → create（A 扣豆流水比对）→ update 改群名 → invite（A 支路直入群 / B 支路通知确认）→ terminal/list / remainder 查询 → member nickname 编辑 → addr/remove 移除 → close → delete。不测消息收发（挂起）、不测支付。

**Architecture:** 模式 A（cost 无参查询）+ 模式 B′（create 写 `ig_group_id` → invite/list/remainder/nickname/remove/close/delete 全链消费）。群号走 extract；A 侧救援棒走 `rescue_sat_terminal`（复用求救群聊 fixture）；B 侧设备走新 fixture `rescue_sat_terminal_b`（探针 S0 验链路）。群收尾：用例内正常链 close+delete；registry 新增 IntercomGroupCleaner（tier 100）兜底中断遗留。

**Tech Stack:** pytest + YAML + `BaseRequest` + Allure + `common.cleanup`（与商城/星豆/订单同一套）

## Global Constraints

- 只 `from common.*`；禁止 `api_test_framework` / 模式 C
- Authorization：OAS 写 **query required**；现网惯例 header。**默认只 Header**；探针锁定后全文统一，YAML 不写真实 token
- 正向 `expected.msg`，负向 `expected.error_msg`；禁止正向写 `error_msg: "成功"`
- `no_auth: true` 只剥 `Authorization`，保留 `Accept-Language`
- YAML 不写真实卡号/密码/群号；设备 `{{rescue_sat_terminal}}` / `{{rescue_sat_terminal_b}}` 由 testcase 字符串替换，**不要** `resolve_extract_value`
- **负向 `intercomGroupId` / `addr` 一律字面量假值**（`0` / `INVALID` / 假 sn），禁止任何 `{{}}` 占位符——缺 extract 时 skip 会吞掉负向
- **群名唯一性**：create 的 `intercomGroupName` 由 testcase 用 `get_current_datetime()` 后缀注入（YAML 写占位串 `AUTO_IG_{ts}`，代码 replace），禁止写死
- 扣费验证：**A 账号 invite/create 前后各查一次** `GET /star-bean/transaction/page?type=CREATE_GROUP|INVITE_MEMBER` 比对新增扣豆记录（仅 A；B 是被邀请方不扣，不查 B 流水——主人拍板）
- `json_data = res.json()` 每请求只调一次；`send_request(..., log_level="none")`；失败排查可临时 `"simple"`
- **本文件禁 pytest-xdist**（extract 链 + 群生命周期序）；**create / invite / close / delete 叶子禁 rerun**（副作用扣豆/毁群，重试重复扣费）
- 断言一律 `assert_api_result(...)` 且**必须传 `biz_context`**（至少 `{"请求参数": params或body}`）
- 方法签名注入 `base_url, auth_headers, case`；需要设备时按类注入 `rescue_sat_terminal` / `rescue_sat_terminal_b`
- 传参形态（OAS 核实）：create/close/update/delete/addr_remove **全 query `params=`**；invitation **POST `json=`**；cost/remainder/terminal_list GET `params=`
- 共享逻辑收敛 `_IgHelpers`（不以 Test 开头）：headers / resolve_addr / resolve_group_id / balance_before / assert_deducted

---

## 0. 范围、执行顺序、session 副作用

Apifox tag **对讲群接口** 13 URL，本计划规划全部、两批执行：

| 序 | 类名 | 方法 | 路径 | OAS summary | 批次 |
|----|------|------|------|-------------|------|
| 1 | `TestIg01Cost` | GET | `/api/monitor/intercom/group/cost` | 对讲群扣费信息 | 批 1 |
| 2 | `TestIg02Create` | PUT | `/api/monitor/intercom/group/create` | 创建对讲群 | 批 1 |
| 3 | `TestIg03Update` | PUT | `/api/monitor/intercom/group/update` | 修改对讲群名称 | 批 1 |
| 4 | `TestIg04Invite` | POST | `/api/monitor/intercom/group/invitation` | 邀请用户加入对讲群 | 批 1（A 支路）/ 批 2（B 支路） |
| 5 | `TestIg05TerminalList` | GET | `/api/monitor/intercom/group/terminal/list` | 查询群成员列表 | 批 1 |
| 6 | `TestIg06Remainder` | GET | `/api/monitor/intercom/group/remainder` | 剩余额度与状态 | 批 1 |
| 7 | `TestIg07Nickname` | PUT | `/api/monitor/intercom/member/update/nickname` | 编辑成员昵称 | 批 1 |
| 8 | `TestIg08AddrRemove` | GET | `/api/monitor/intercom/group/addr/remove` | 设备移除群聊 | 批 1 |
| 9 | `TestIg09Close` | PUT | `/api/monitor/intercom/group/close` | 关闭群聊 | 批 1 |
| 10 | `TestIg10Delete` | DELETE | `/api/monitor/intercom/group/delete` | 删除对讲群 | 批 1 |
| 11 | `TestIg11InviteNotice` | GET×3 | `/intercom/message/invitation/{notice/list,pending/count,send/list}` | 邀请通知域 | 批 2 |
| 12 | `TestIg12InviteHandler` | PUT | `/api/monitor/intercom/message/invitation/handler` | 处理邀请通知（同意） | 批 2 |
| — | — | POST | `/intercom/group/closed/delivery/cancel` | 管理后台投递取消 | **挂起**（web 账号预期无权限，参考 complete/addr 3001 先例） |
| — | — | GET×4 | `/intercom/message/{page,receive/info,clear/unread,clear/all-unread}` | 消息域 | **已解除挂起**，另立 [intercom-message-tests.plan.md](intercom-message-tests.plan.md) 落地（2026-08-20，`testcases/test_intercom_message_controller.py`，34 条） |
| — | — | PUT | `/intercom/member/update/nickname` 已并入 #7；边界场景（换群/并发/上限） | — | 批 2 尾部 |

文件内类定义顺序 01→12。批 1 类序 01→10；批 2 追加 11→12（同一文件追加类，不另开文件）。

**明确不做（本计划全文）：**

- ~~消息域 4 口（page / receive/info / clear×2）——挂起~~ → 2026-08-20 已在 [intercom-message-tests.plan.md](intercom-message-tests.plan.md) 独立落地（造数走 10304 终端上行，不占本文件）
- `closed/delivery/cancel`（管理后台）
- 微信/扫码支付、星豆充值链（星豆模块已覆盖）
- §9.1 拒绝退费、§9.2 自己设备换群弹窗/静默——**口径冲突未收口，断言不写死**（批 2 拒绝支路按「退还开关开/关各打一枪、只锁返回码不锁流水方向」处理；换群场景批 2 尾部探明后写双预期）
- 企业账号链路（企业直接拉群/纯企业设备邀请）——业务文档明确按归属隔离，个人不能邀纯企业设备只做一条负向

**session 副作用与收尾（registry 已就位，conftest 只加 B 系 fixture）：**

- 新增 `IntercomGroupCleaner`（`common/cleanup/intercom_group.py`，tier 100）：create 成功即 `register_cleanup`（**副作用落地即注册**）；用例内 delete 成功后注销（`unregister` 同款语义——消费完成即出网，防双重收尾，与 unpaid_order 模式一致）
- 正常链：`TestIg09Close` 关群 → `TestIg10Delete` 删群（两接口皆被测正向，即清理动作本身）
- 中断遗留：close 未 delete / CI 中途红 → session 末 cleaner 对登记群先 close（若 status=1）再 delete；已 delete 的群不在名单，无双重收尾噪音
- 设备：A 支路复用 `rescue_sat_terminal`（求救群模块同款造数链）；批 2 新增 `rescue_sat_terminal_b`（B 登录 + B 名下造棒绑定，链路探针 S0 验）
- **余额闸门**：探针 S0 查 A 账号 `transaction/page` 最新 `balanceAfter`；**< 200 豆 → 全文件 skip 并提示充值**（每 session 批 1+2 估算：2 群 × 20 + 3 邀 × 20 = 100+ 豆，留一倍余量）
- B 系 fixture（`auth_headers_b` / `rescue_sat_terminal_b`）session 级、批 1 不注入不拉活——对现有用例零影响

---

## 1. 三条传值通道

### 通道 A — Fixture

| Fixture | 作用域 | 给谁用 | 说明 |
|---------|--------|--------|------|
| `base_url` / `auth_headers` | session | 全部 | 同现有 |
| `rescue_sat_terminal` | session | TestIg04（A 支路）/ 07 / 08 | 复用求救群聊 fixture（12 位 sn） |
| `auth_headers_b` | session | 批 2：TestIg04（B 支路）/ 11 / 12 | B 登录（`JKPT_ACCOUNT_B=user13128251672`，密码同 A 规则 MD5；验证码 OCR + 重试同 A 款） |
| `rescue_sat_terminal_b` | session | 批 2 B 支路 | B 名下救援棒：与 A 同款。B token 建 L1 测试分组 → mock-in-storage → `POST groups/{one_id}/terminals`。收尾删组内设备再删该 L1，**不动** B 原「我的分组」。不走 `pre-bind`/`bind/addr` |

### 通道 B — extract.yaml

| extract 键 | 谁写入 | 谁读取 | 用途 |
|------------|--------|--------|------|
| `ig_group_id` | `TestIg02Create` 正向 `code==0`（只写一次） | 03–10 全部正向 | 主群号 |
| `ig_group_id_b2` | 批 2 helper 二号群 create（只写一次） | 换群/边界场景 | 第二个群（批 2 尾部用） |
| `ig_member_id` | `TestIg05TerminalList` 正向首条 `myTerminal==true` 成员 | `TestIg07Nickname` 正向 | 成员 id |
| `ig_invite_notice_id` | 批 2：B 支路 invite 后 `notice/list` 首条待确认 | `TestIg12InviteHandler` 同意 | 通知 id（字段名探针钉） |

负向一律字面量，**所有负向 case 不依赖任何 extract**。

### 通道 C — YAML 字面量

| YAML 字段 | 含义 |
|-----------|------|
| `intercomGroupName` | create / update：占位串 `AUTO_IG_{ts}`，代码 replace 时间戳 |
| `intercomGroupId` | update / list / remainder / close / delete：正向 `{{ig_group_id}}`，负向字面量 |
| `addrInfos` | invite JSON 数组（元素结构探针 S4 钉：addr + 可能的 phone/nickname） |
| `force` | invite：A 支路 false；换群场景探针后定 |
| `addr` | nickname / addr_remove：`{{rescue_sat_terminal}}` 或字面量假 sn |
| `nickname` | 昵称字面量（改后再改回不强制） |
| `memberId` | nickname：正向 `{{ig_member_id}}`，负向字面量 |
| `no_auth` / `expected.*` | 同技能约定 |

---

## 2. 接口参数传递与断言（每口：放哪 / 传什么 / 断什么）

公共前缀 `{base_url}/api/monitor`。**除 invitation 是 `json=` 外全部 `params=`**（OAS 核实：create/close/update/delete/addr_remove 均纯 query）。

### 2.1 GET `/intercom/group/cost` — `TestIg01Cost`

无业务参数。断言：`code=0`；`$.data.createGroupDeductBeans`(int≥0)、`createGroupDeductEnabled`(bool)、`inviteMemberDeductBeans`(int≥0)、`inviteMemberDeductEnabled`(bool)。**四值写进日志并回填 §5**——它们决定流水断言的期望豆数（现网默认 20/20，以实测为准）。负向：无 token。

### 2.2 PUT `/intercom/group/create` — `TestIg02Create`

`params={"intercomGroupName": "AUTO_IG_{ts}"}`（代码 replace）。

正向断言：
- `code=0`；`$.data.id` 非空 → 写 `ig_group_id` + `register_cleanup(f"intercom_group_{id}", id, IntercomGroupCleaner.cleaner, tier=100)`
- `$.data.groupName` == 请求名；`status==1`（进行中）；`webAccount` == A 账号
- `starBeanInsufficient` 为 false（true 则 fail——余额闸门失效信号）
- **扣费流水比对**（若 §5 `createGroupDeductEnabled=true`）：create 前后各查 `transaction/page?type=CREATE_GROUP`，断言新增 1 条 `amount == -createGroupDeductBeans` 且 `balanceAfter` 减少对应值

负向：缺 `intercomGroupName`（不传键）、群名超长（探针 S2 定上限）、无 token。

### 2.3 PUT `/intercom/group/update` — `TestIg03Update`

`params={"intercomGroupId": {{ig_group_id}}, "intercomGroupName": "AUTO_IG_RENAMED_{ts}"}`。

正向：`code=0` 后**同方法副作用** GET remainder 复核 `groupName` == 新名（remainder 返回 groupName——OAS 核实）。负向：假群 id、缺群名、缺群 id、无 token。

### 2.4 POST `/intercom/group/invitation` — `TestIg04Invite`

**`json=` 请求体**：`{"intercomGroupId": "…", "addrInfos": [{…}], "force": false}`（addrInfos 元素结构探针 S4 钉）。

**批 1 A 支路**（自己设备：邀请即扣→直接入群，无通知）：

- 正向前 `balance_before = transaction/page?type=INVITE_MEMBER` 最新 `balanceAfter`
- invite `code==0` 后断言：`$.data.confirm==1`（已确认成功）、`starBeanInsufficient==false`、`groupMembers` 含该 addr
- **同方法副作用**：GET terminal/list 该 addr 在列表中（业务文档 §5 支路 A：直接入群）
- **扣费比对**（若 `inviteMemberDeductEnabled=true`）：新增 1 条 INVITE_MEMBER 扣豆、金额 == `-inviteMemberDeductBeans`

**批 2 B 支路**（他人设备：扣费→发通知→B 同意）：

- A 邀 B 名下棒（`addrInfos` 用 `{{rescue_sat_terminal_b}}`），断言 `confirm==0`（待确认）或按 §5 实测
- A 侧 `send/invitation/list` 可见记录；B 登录 `notice/list` 有待确认通知 → 写 `ig_invite_notice_id`，`pending/count` ≥1
- `TestIg12InviteHandler`：B 调 handler 同意 → 返回码锁探针值；**真闭环**：A 侧 terminal/list 该 addr 成员可见
- 拒绝支路（另一台 B 棒或第二张通知）：handler 拒绝，**只锁返回码**；退费流水**不写死方向**（§9.1 冲突）——退还开关开/关各打一枪，结果记 §5 呈主人

负向（批 1 就做）：假群 id、空 `addrInfos`、非救援棒类型设备（用 `bd_test_terminal` 的 sn——业务文档 §3：仅 TT_RESCUE_STICK 可入群）、无 token、A 余额不足（不主动造，若 §5 星豆不足码现网可得则记）。

### 2.5 GET `/intercom/group/terminal/list` — `TestIg05TerminalList`

`params={"intercomGroupId": …}`。正向：`$.data` 为 list（A 支路 invite 后非空）；元素含 `id`/`addr`；**首条 `myTerminal==true` 写 `ig_member_id`**（只写一次）。负向：假群 id、无 token。

### 2.6 GET `/intercom/group/remainder` — `TestIg06Remainder`

同参。正向：`$.data.status==1`、`groupName` 非空、`maxMembers`（int，回填 §5——业务文档默认 5）、`allRemainingVoiceNumber`/`allRemainingPositionNumber` int≥0、`isOwner==true`、`exited==false`。负向：假群 id、无 token。

### 2.7 PUT `/intercom/member/update/nickname` — `TestIg07Nickname`

`params={"memberId": {{ig_member_id}}, "nickname": "AUTO_NICK_{ts}", …}`（参数名探针 S4 钉——OAS 此口未拉详情）。正向：`code=0` 后副作用 terminal/list 复核该成员昵称字段 == 新值（字段名探针钉）。负向：假 memberId、改他人设备昵称（B 棒入群后批 2 补，若 myTerminal 语义严格应被拒——锁探针码）、无 token。

### 2.8 GET `/intercom/group/addr/remove` — `TestIg08AddrRemove`

`params={"intercomGroupId": …, "addr": {{rescue_sat_terminal}}}`。正向：`code=0` 后副作用 terminal/list 该 addr **不在**列表（移除生效）；被移除设备**不退豆**（业务文档 §7 不退清单 #1——不写流水断言，仅记日志）。负向：假群 id、假 addr、设备不在群（移除后二次 remove）、无 token。

⚠️ **顺序约束**：remove 之后 close 之前，若批 2 需要群内有成员的场景，helper 需重新 invite（再扣 20 豆）——批 1 主链 remove 放 close 前，避免二次邀请成本。

### 2.9 PUT `/intercom/group/close` — `TestIg09Close`

`params={"intercomGroupId": …}`。正向：`code=0` 后副作用 remainder `status==0`（已关闭）。负向：假群 id、二次 close（已关闭再关）、无 token。

### 2.10 DELETE `/intercom/group/delete` — `TestIg10Delete`

`params={"intercomGroupId": …}`。正向：`code=0` 后副作用 remainder 假码/异常（群不存在）或探针钉的形态；**delete 成功即从 cleaner 注销**（消费完成出网）。负向：假群 id、删除未关闭的活跃群（若业务要求先 close——探针 S6 钉，形成「活跃群不可直接删」或「可直接删」两分支写 §5）、无 token。

### 2.11 批 2 通知域三 GET — `TestIg11InviteNotice`

`notice/list` / `pending/count` / `send/invitation/list`（B token / A token 各按语义）：结构断言 + B 支路联动（见 2.4）。负向：无 token。**字段名（状态枚举：待确认/已接受/已拒绝/已过期 vs 待处理/已同意/已失效——§9.3 冲突）全部以实测响应为准回填 §5，禁止按文档名写死**。

### 2.12 PUT `/intercom/message/invitation/handler` — `TestIg12InviteHandler`

B token 调用，入参（通知 id + 同意/拒绝动作）探针 S7 钉。同意→真闭环（A 侧可见）；拒绝→只锁码（§9.1）。负向：假通知 id、重复处理（已同意再同意）、无 token。

---

## 3. YAML 文件头与样例（骨架，负向码探针后填）

路径：`yaml/test_intercom_group_controller.yaml`。顶层 key `<模块>_<动作>_cases` 一类一 key（批 1 十个 + 批 2 追加）。

```yaml
# yaml/test_intercom_group_controller.yaml
# 对讲群：cost/create/update/invite/list/remainder/nickname/remove/close/delete（批1）
#         邀请通知域 + handler（批2追加）
# {{ig_group_id}} 由 TestIg02 写入；{{ig_member_id}} 由 TestIg05 写入
# {{rescue_sat_terminal}}/_b 由 _IgHelpers 注入，不走 extract
# 群名占位 AUTO_IG_{ts} 由代码 replace；负向 id 一律字面量；负向码探针后填

intercom_cost_cases:
  - name: "对讲群-扣费信息-正向"
    expected: {code: 0, msg: "成功"}

intercom_create_cases:
  - name: "对讲群-创建-正向"
    intercomGroupName: "AUTO_IG_{ts}"
    expected: {code: 0, msg: "成功"}
  # 负向：缺群名 / 超长 / 无 token —— 探针 S2 后补

intercom_invite_cases:
  - name: "对讲群-邀请-正向-A支路自己的救援棒"
    addrInfos:
      - addr: "{{rescue_sat_terminal}}"
    force: false
    expected: {code: 0, msg: "成功"}
  # 批2追加 B 支路两条；负向：假群id/空addrInfos/非救援棒/无token
# …update/list/remainder/nickname/remove/close/delete 同构，略——
# 完整骨架实现时按 §2 逐口补全，负向码全部待填探针值
```

---

## 4. 第 0 节：现网探针（先于 YAML 定稿；临时脚本放 temps/ 用完即删）

| ID | 请求 | 要记下的 |
|----|------|----------|
| S0 | ① A `transaction/page` 最新 `balanceAfter`（余额闸门基线）② **B 登录**（user13128251672 + 同款 MD5；验证码 OCR）③ **B 造棒链**：B token mock-in-storage 入库→terminal 添加→「我的」绑定接口在哪/怎么调（若 web 端做不到→**停下来问主人**备选：管理后台绑定 or B 扫码真机）④ cost 四值 | 余额数；B 登录可行性；B 绑定链路；扣豆开关与豆数 |
| S1 | create `AUTO_IG_{ts}` | 群 id 路径；status/webAccount 字段实形；**是否真扣 20 豆**（前后流水） |
| S2 | create 负向：缺群名 / 超长（20/50/100 字）/ 无 token；update 假群 id | 各真实 code/msg；群名长度上限 |
| S3 | invite A 支路：`addrInfos` 元素结构先按 `{"addr": sn}` 试，不行再看 4xx 报文提示 | **addrInfos 必填字段**；confirm 实测值；扣豆流水 |
| S4 | terminal/list / remainder / nickname / addr_remove 逐口打真群 | 各字段实名（nickname 入参名、成员昵称字段名）；remainder 的 maxMembers 实值 |
| S5 | close → remainder(status) → delete → remainder | close 后 status 形态；delete 后查群形态；**活跃群能否直接 delete**（不 close 先试一张探针群） |
| S6 | 批 2 前置探针（批 1 落地后跑）：B 支路 invite → B notice/list 字段与状态枚举实名 → handler 入参 | 通知 id 字段；状态枚举实测（§9.3）；handler 同意/拒绝入参与返回码 |
| S7 | 拒绝支路退还观察（可选，一张通知）：handler 拒绝 → A 流水有无 REFUND/INVITE_MEMBER 正数 | §9.1 现网实际行为，记 §5 呈主人，**不写死断言** |

探针铁律：不 cancel/动账号里**未登记**的历史群；探针群自造自清（close+delete）。

---

## 5. 现网基线（探针后填）

| 项 | 结论 |
|----|------|
| cost 四值（create/invite 开关与豆数） | **实测（2026-08-18 探针 S0）**：create 开=20 豆；invite 开=**10 豆**/台（注意：业务文档写 20/台，以实测 10 为准） |
| A 账号 balanceAfter | **9714 豆**（探针消耗后）——远超闸门 200 |
| B 登录 + B 造棒绑定链 | B 登录 `user13128251672` 可行（同款 OCR + MD5）。**web 链已通（2026-08-19 纠偏）**：B token 建 L1 → `mock-in-storage` → `POST groups/{id}/terminals`，`code=0`，`belongToDesc=我的`，`webAccount=null`。第一次添加曾偶发 `3004`，当时误走小程序 `bind/addr` 导致 `webAccount=useruser…`——**该绕路已废弃**。收尾：B token 删测试组设备再删 L1，**不删**原「我的分组」`6a842aa4d76e0c3dcfb71a1f`。邀请/通知/handler 需在此链上重跑 S6 后回填。 |
| addrInfos 元素必填结构 | **`[{"addr": sn}]` 即可**（S3 实测 code=0） |
| create / invite 扣豆流水实测 | create：`CREATE_GROUP amount=-20`「创建群组扣减星豆」；invite：`INVITE_MEMBER amount=-10`「邀请成员扣减星豆」——**邀请即扣实证**（confirm=1 同时流水落账） |
| create 响应形态 | `$.data.{id,groupName,webAccount,status:1,starBeanInsufficient:false,createdTime(int ms)}` ✓ 与 OAS 一致 |
| 群名长度上限 | **15 字符**（超长 → `1001 群名称不能超过15个字符`） |
| 缺群名 / 无 token | `1001 请检查请求参数是否正确` / `3001 没有访问权限` |
| 假群 id（update 实测） | **`3003 群聊不存在`**（新码型——负向断言用 3003 不是 1001） |
| invite A 支路形态 | `confirm=1`（自己设备直接入群）✓；`groupMembers[0]` 含 `{id,addr,myTerminal:null}`；**terminal/list 里 myTerminal=true** |
| invite B 支路形态（2026-08-19 web 造棒纠偏后） | A 邀 B 测试组棒：响应仍是 **`confirm=1` 且 `groupMembers=[]`**（待确认不是 confirm=0）。A `send/invitation/list` 有 `PENDING`；**B `notice/list` PENDING 能收到同 id**；`pending/count=1`。B handler `AGREED` → **code=0**，之后 A `terminal/list` 含该棒。 |
| remainder 形态 | `{id,isOwner:true,exited:false,groupName,status,maxMembers,allRemaining*}` ✓；**maxMembers 以 remainder 为准（2026-08-19 满员探针 = 3，文档默认 5 勿写死）** |
| 重复邀请（DUP） | 已在本群再邀 → `1001 设备已经加入该群聊，无需重复邀请`，不扣豆，成员不变。本群已 PENDING 再邀 → `1001 该设备“{sn}”邀请中/待对方确认`，不扣豆，通知 id 沿用 |
| 满员 | 填满 maxMembers 后再邀 1 台 → `1001 群成员数将超出上限{N}人，无法邀请1人，请调整邀请数量后重试`，不扣豆 |
| 换群（§9.2 收口） | **自己棒** `force=false`：`code=0 confirm=0`，留原群、不入新群、不扣豆。`force=true`：`confirm=1` 静默退原群入新群，另扣 10 豆。**他人棒** `force=false`：新 PENDING，旧群仍在；B 同意后才退原群入新群（邀请即扣） |
| addr/remove | `code=0`；remove 后 terminal/list **立即为空** ✓；不退豆（无新增流水） |
| nickname 假 id | `1001 请检查请求参数是否正确`（入参名 memberId+nickname 可用；真成员昵称字段=avatarInfo.nickname，批 1 落地时副作用断言用） |
| close | 群主正向 `code=0`，remainder `status=0` 仍可查 ✓。重复关闭（独立叶子）→ `1001 群聊已结束，无法操作`，status 仍 0。非群主关（路人 / 被邀请人新棒独立群）→ `999 只有群主可以查看详情`，主链/该群 `status` 仍 1（2026-08-19 关群探针） |
| delete | 已关群主删 `code=0`（Ig10 正向）。**群主删活跃**：接口不拦截，`code=0` 且 remainder `status` 1→0（2026-08-19 逐步日志）；限制只在前端。主人拍板该方案 **Pass，等后端修复再补「须先 close」负向**。非群主删活跃信封也是 `0` 但 status 仍 1（空成功）——同样不写期望失败。remainder 删后仍可查，正向不锁消失。 |
| 通知域状态枚举实测（§9.3） | OAS/现网一致：`PENDING` 待确认、`AGREED` 已同意、`REJECTED` 已拒绝、`EXPIRED` 已失效；通知 id 字段=`id` |
| handler 同意/拒绝入参与返回码 | query `handlerType=AGREED\|REJECTED` + `invitationNoticeId`；假 id → `3003 邀请记录不存在`；无 token → `3001`；**B web 处理设备邀请 → `code=0`**（web 造棒归属正确后真闭环可达；先前 999 是小程序 bind 把账号写成 useruser… 的假象） |
| 拒绝退费现网行为（§9.1） | 拒绝码已可达 `0`；退费流水方向仍不写死，联跑时记 §5 |
| 换群（§9.2） | 见上「换群（§9.2 收口）」；Ig13 已按 force 真假两条边落地，不再双预期放过 |

---

## 6. 文件与任务

| 文件 | 职责 |
|------|------|
| `plan/intercom-group-tests.plan.md` | 本文 |
| `yaml/test_intercom_group_controller.yaml` | 批 1 十组 `intercom_*_cases` + 批 2 追加通知/handler 组 |
| `testcases/test_intercom_group_controller.py` | `TestIg01`–`10`（批 1）+ `TestIg11`–`12`（批 2）+ `_IgHelpers` |
| `common/cleanup/intercom_group.py` | 新增 IntercomGroupCleaner（tier 100，close→delete，含注销语义） |
| `conftest.py` | +`auth_headers_b` / `rescue_sat_terminal_b`（批 2 前加；批 1 不动） |

### 任务（两批）

**批 1（单账号 A，类序 01→10）：**

- [x] **Task 0** 探针 S0–S5（S0 含 B 登录预验，失败即呈主人），填 §5；余额 <200 停
- [x] **Task 1** `common/cleanup/intercom_group.py` + YAML + `TestIg01Cost` / `TestIg02Create`（流水比对 + registry 注册）
- [x] **Task 2** `TestIg03Update` / `TestIg05TerminalList` / `TestIg06Remainder`
- [x] **Task 3** `TestIg04Invite` A 支路（直入群 + 扣豆比对 + terminal/list 副作用）
- [x] **Task 4** `TestIg07Nickname` / `TestIg08AddrRemove`
- [x] **Task 5** `TestIg09Close` / `TestIg10Delete`（delete 后注销 cleaner）
- [x] **Task 6** 批 1 整文件回归：collect 01→10、叶子 `[caseN]`、session 末 cleaner 兜底日志、**用例内已 delete 的群不出现双重收尾**

**批 2（双账号，追加类 11→12 + 边界）：**

- [x] **Task 7** conftest B 系 fixture + 探针 S6（B 支路链路钉字段）
- [x] **Task 8** B 支路 invite → `TestIg11InviteNotice`（notice/pending/send-list）→ `TestIg12InviteHandler`（现网 web 返回 999，非 APP 真闭环）
- [x] **Task 9** 拒绝支路 + 真换群（他人棒 pending→同意退原群；自己棒 force=false 不换 / force=true 静默换）
- [x] **Task 10** 重复邀请（已在本群 / 已 pending 不扣豆）+ 满员（按 remainder.maxMembers 填满再邀）
- [x] **Task 11** 回归：`pytest testcases/test_intercom_group_controller.py` **51 passed**（2026-08-19）

---

## 7. 仍不敢装懂、需要现网说话的点

1. `addrInfos` 元素必填结构（OAS 只给了 `IntercomUserInvite` 引用未展开）——S3 钉。
2. nickname 口的完整入参名（OAS 此口未展开）——S4 钉。
3. 活跃群群主能否直接 delete——现网 API 允许（`code=0`，status 1→0）；前端限制。**方案 Pass，等后端修复再补负向**（2026-08-19 主人拍板）。
4. 通知域状态枚举实名（图谱 vs 处理文档两套名，§9.3）——S6 钉，**断言前禁止按文档名写死**。
5. B 名下造棒的「我的」绑定链路（web mock 入库能否归属 B）——S0 钉，不通即停呈主人。
6. 扣豆开关现网状态（cost 四值）——若 create/invite 均不扣费，流水比对断言自动降级为「无新增流水」。
7. 换群时自己设备弹窗 vs 静默（§9.2 冲突）——批 2 探明写双预期，等产品收口再删。
8. 邀请限频是否存在（星豆 buy 有 65s 限频先例；invite 连续多台是否触发未知）——批 1 Task 3 顺带观察。

---

## 8. 与现有模块的关系

- **星豆模块**：流水比对消费 `GET /star-bean/transaction/page`（只读，不改星豆用例）；CREATE_GROUP / INVITE_MEMBER 类型即为本模块的扣费凭证。
- **求救群聊模块**：共用 `rescue_sat_terminal` 造数链与 A 账号。**注意**：同一根救援棒同一时刻只能在一个活跃群（业务文档 §1）——若同 session 先跑求救群聊（emergency_chat_item 造 SOS 群）再跑本文件 invite，会构成「换群」场景而非干净正向。**联跑纪律：本文件批 1 与求救群聊文件不同 session 跑，或本文件用独立新棒**（探针 S0 顺带确认 SOS 群与对讲群是否互斥——业务上求救群 ≠ 对讲群，但设备归属约束可能交叉，以实测为准）。
- **common/cleanup**：IntercomGroupCleaner 与 unpaid_order / rescue_chat 同 tier 100、同「消费完成即注销」语义；session 末清理序：群/订单 → 设备 → 分组，无新增依赖。
