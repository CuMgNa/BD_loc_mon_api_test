# 对讲群扩展断言结果 — 完整大纲（待校验，未实施）

> 目的：信封层继续走技能 `assert_api_result`；本文件正向用例的**部门扩展断言**补上与信封同级的可读结果（控制台对照表 + Allure 独立附件）。
> 不改判定公式（扣豆仍用全局余额基线）；不改 `common/allure_assert_util.py`；不改技能。
> 本文件只覆盖批 1 `test_intercom_group_controller.py` / 对应 YAML。批 2 未落地，不写。

---

## 0. 原则

| 层 | 谁做 | 成功时人看到什么 |
|----|------|------------------|
| 信封 | `assert_api_result`（技能，不动） | `code` / `msg`，Allure「【成功】验证结果」 |
| 扩展 | 本文件 `_IgHelpers.report_extra` | 标题 + 期望/实际表 + 通过/失败，Allure「【扩展】{标题}」 |

两条并列，扩展不写进信封那句「验证通过: code=0, msg=成功」。

- 只给 **正向且 `code==0` 之后** 打扩展表。负向只信封。
- 二次 HTTP 仍可 `log_level="none"`，表里必须带抽出的值，开发不用肉眼对两个接口。
- 先打表，再 `assert`。失败时表已在、Allure 已贴，last-HTTP 即使是流水/list 也能靠附件看懂。

---

## 1. Helper（仅本文件）

```text
report_extra(title: str, rows: list[dict], *, ok: bool) -> None
  rows 元素: { "项", "期望", "实际" }  可选 "通过": bool
```

控制台：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {title}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  项              期望            实际
  groupName       AUTO_IG_103012  AUTO_IG_103012
  ...
  ✅ {title}通过    或   ❌ {title}失败
```

Allure：`attachment` JSON `{ title, ok, rows }`，name=`【扩展】{title}`。成功失败都贴。

扣豆轮询：命中后组 rows，再 `report_extra`；未命中也组「最后一次实际」再报再抛。rows 含「命中轮次 / 等待秒数」。

**不抽**到 `common/`。create/invite 共用本文件的 `wait_new_deduction`（内部改成先组表再 assert）。

---

## 2. 按类：扩展块清单

每块 = 一次 `report_extra`。一块内多行。逻辑与现网代码一致，只补展示。

### Ig01 Cost — 1 块（仅正向）

标题：`cost 四值`

| 项 | 期望 | 实际来源 |
|----|------|----------|
| createGroupDeductBeans | int ≥ 0 | `$.data` |
| createGroupDeductEnabled | bool | 同上 |
| inviteMemberDeductBeans | int ≥ 0 | 同上 |
| inviteMemberDeductEnabled | bool | 同上 |

四值仍写入 `_COST` 供后续扣豆。负向无 token：无扩展块。

### Ig02 Create — 2 块（仅正向）

**块 A 标题：`创建响应字段`**

| 项 | 期望 | 说明 |
|----|------|------|
| id | 非空 | 现逻辑 |
| groupName | == 请求 `intercomGroupName` | |
| status | 1 | |
| webAccount | 非空 | **不**锁等于 A 账号（计划有句，现网格式未钉，本轮不收紧） |
| starBeanInsufficient | false | |

然后写 extract + `register_intercom_group`（登记不是断言，不进表）。

**块 B 标题：`扣豆对账`**（开关开时）

| 项 | 期望 | 说明 |
|----|------|------|
| type | CREATE_GROUP | |
| 扣前余额 | 查询值 | 不限类型最新 `balanceAfter` |
| 期望扣减 | `-createGroupDeductBeans`（来自 `_COST`） | |
| 期望余额 | 扣前 − beans | |
| 实际 amount | 该 type 最新一条 | |
| 实际 balanceAfter | 同上 | |
| 命中 | 第 N 次 / 等待 Xs | |

开关关：一块「扣豆对账」行「开关关闭，跳过」，`ok=true`，不查流水。

负向三条：无 A/B。

### Ig03 Update — 1 块（仅改名正向）

标题：`改名复核`

二次：GET remainder（可 none）。

| 项 | 期望 | 实际 |
|----|------|------|
| remainder.groupName | 请求新名 | `$.data.groupName` |

负向（假 id / 缺群名 / 超长 / 无 token）：无扩展。假 id 若 code≠0 本来就不会进块。

### Ig04 Invite — 3 块（仅 A 支路正向）

**块 A 标题：`邀请响应字段`**

| 项 | 期望 |
|----|------|
| confirm | 1 |
| starBeanInsufficient | false |
| groupMembers 含 addr | 请求的救援棒 sn |

**块 B 标题：`成员列表复核`**

二次：GET terminal/list。

| 项 | 期望 |
|----|------|
| list 含 addr | 同上 sn |

**块 C 标题：`扣豆对账`**

同 Ig02 块 B，type=`INVITE_MEMBER`，beans=`inviteMemberDeductBeans * 台数`。

负向（假群 / 空 addrInfos / 非救援棒 / 无 token）：无扩展。

### Ig05 TerminalList — 1 块（仅正向）

标题：`成员结构`

| 项 | 期望 |
|----|------|
| data 为 list 且非空 | 邀请后必有成员 |
| 每条有 id、addr | 现逻辑 |
| 存在 myTerminal==true | 用于写 `ig_member_id`（写出的 id 进「实际」列） |

写 extract 仍只一次。负向无扩展。

### Ig06 Remainder — 1 块（仅正向）

标题：`额度与状态`

现逻辑原样展示（不在本轮收紧 status 必须为 1，因代码允许 0|1；本文件序在 close 前，实际应为 1）：

| 项 | 期望 |
|----|------|
| groupName | 非空 |
| status | 0 或 1（现逻辑） |
| maxMembers | int > 0 |
| allRemainingVoiceNumber | int ≥ 0 |
| allRemainingPositionNumber | int ≥ 0 |
| isOwner | true |
| exited | false |

负向无扩展。

### Ig07 Nickname — 1 块（仅改自己设备正向）

标题：`昵称复核`

二次：GET terminal/list。

| 项 | 期望 |
|----|------|
| 成员 id 命中 | == `intercomGroupMemberId` |
| avatarInfo.nickname | == 请求 `newNickname` |

假 id / 无 token：无扩展。

### Ig08 AddrRemove — 1 块（仅移除正向）

标题：`移除复核`

二次：GET terminal/list。

| 项 | 期望 |
|----|------|
| addr 不在 list | 被移除的救援棒 sn |

负向无扩展。

### Ig09 Close — 2 块（仅关闭正向）

**块 A 标题：`关群复核`**

二次：GET remainder。

| 项 | 期望 |
|----|------|
| remainder.status | 0 |

**块 B 标题：`二次关闭`**

二次：再 PUT close（探针：已关再关）。

| 项 | 期望 |
|----|------|
| code | 1001 |

假 id / 无 token：无扩展。YAML 未单开「二次 close」case，仍由正向副作用覆盖。

### Ig10 Delete — 0 块

信封即可。探针：delete 后 remainder 仍能查到（软删），不能做「消失」表。成功只 `unregister`。不发明「群已删除」对照。

---

## 3. 块数汇总

| 类 | 正向扩展块数 | 二次 HTTP |
|----|--------------|-----------|
| Ig01 | 1 | 0 |
| Ig02 | 2 | 流水（轮询） |
| Ig03 | 1 | remainder |
| Ig04 | 3 | list + 流水 |
| Ig05 | 1 | 0 |
| Ig06 | 1 | 0 |
| Ig07 | 1 | list |
| Ig08 | 1 | list |
| Ig09 | 2 | remainder + close |
| Ig10 | 0 | 0 |
| **合计** | **13** | — |

负向全部 0 块。

---

## 4. 明确不做（本轮）

| 项 | 原因 |
|----|------|
| 改 `assert_api_result` / 技能 | 信封契约保持 |
| 扣前改回 `type=CREATE_GROUP` 余额 | 交错会错位 |
| 流水拉全页做「条数 +1」 | 串行下金额+余额足够 |
| `webAccount == A 账号` | 格式未钉，避免误红 |
| 负向失败不得扣豆 | 另开需求 |
| Ig08「不退豆」流水断言 | 计划只要记日志；若要展示另开 |
| Ig10 remainder 消失 | 探针否定 |
| 批 2（B 支路 / 通知 / handler） | 未落地 |
| 抽到 `common/` | 先本文件；≥2 文件再抽 |

---

## 5. 失败与收尾

- 扩展失败：表已打印、Allure 已贴 `ok=false`，再抛。
- create 已成功、扣豆表失败：群已在 registry，session 末 cleaner 收。create/invite **禁 rerun**（现状无 `--reruns`，保持）。
- 轮询：中间失败只内部记轮次，**最后一次**才 `report_extra` + 抛，避免 Allure 贴 8 份。

---

## 6. 改哪些文件

| 文件 | 动作 |
|------|------|
| `testcases/test_intercom_group_controller.py` | 加 `report_extra`；改 `wait_new_deduction`；Ig01–09 正向接表 |
| `yaml/test_intercom_group_controller.yaml` | **不改**（不新增 case） |
| `common/*` / 技能 | **不改** |

验收：`pytest testcases/test_intercom_group_controller.py` 仍 35 绿；正向控制台能看到对应「【扩展】」块；失败时 Allure 有扩展 JSON，不只信封成功附件。

---

## 7. 请你校验的点

1. 13 块是否该全做，还是先做「跨接口」6 类（Ig02B / Ig03 / Ig04B+C / Ig07 / Ig08 / Ig09）同响应字段先不动？
2. Ig06 `status` 展示 0\|1 还是改锁 1？
3. Ig08 不退豆、负向不扣豆：本轮是否仍排除？
4. Allure 每块一份附件（最多 3 份/用例）是否可接受？

通过后再改代码。
