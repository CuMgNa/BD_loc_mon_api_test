# API 自动化覆盖缺口盘点（P0/P1/P2）

> 生成时间：2026-08-14
> 数据来源：Apifox 项目「Swagger3接口文档」OAS 实时拉取（x-download-time: 2026-08-14T06:33:06Z）
> 比对基准：`jkpt_api_test/testcases/*.py` 中实际请求的接口路径（YAML 数据驱动的执行层）
> 数值口径：以最新 Apifox 文档为准；接口如有变更请重新拉取比对。

---

## 一、盘点口径说明（先读，避免误读数字）

1. **粒度**：按 URL 计（一个 URL 记 1，不论其下有几个 HTTP method）；全集 398 个 URL / 426 个操作。
2. **归一化规则**：路径变量名归一（`{tid}`/`{eid}`/`{alarm_id}` → `{}`）后与 OAS 匹配，消除"同接口不同变量名"的误判。
3. **人工修正**：`/api/monitor/alarms/{addr}`（查历史报警）与 `/api/monitor/alarms/{id}`（处理报警）**均已实现**，机器口径仅匹配其一，本文档按修正后口径统计。
4. **已知歧义（不计入已实现，也不建议当独立缺口补测）**：
   - `/api/monitor/captcha`：在 `conftest.py` 登录链路中被调用，但无独立断言用例（属前置工具）。
   - `/api/datas/bd`、`/api/monitor/mock-in-storage` 等：作为协议造数工具被调用，非被测对象。
5. **P2 中的 mock/h5-mock/datas/mock-\* 系列**：多为造数/模拟接口，本身不是业务被测对象，是否补测由测试目标决定。

---

## 二、总览

| 维度 | 数量 | 占比 |
|------|------|------|
| OAS 接口全集（URL） | 398 | 100% |
| ✅ 已实现自动化 | **35** | **8.8%** |
| ❌ 未实现自动化 | **363** | 91.2% |
| └─ 🔴 P0 高风险写操作 | 143 | 36.0% |
| └─ 🟡 P1 消息/通知/触达 | 64 | 16.1% |
| └─ 🟢 P2 枚举/地图/造数/低ROI | 156 | 39.3% |

**判级依据**：
- **P0** = 资金扣费 / 绑定关系变更 / 设备写指令 / 账号安全与越权 / 救命功能（应急求救）。出了事最赔不起。
- **P1** = 消息触达类：漏发、重发、未读数不一致属业务事故但非资金损失。
- **P2** = 纯枚举、静态资源、大屏聚合、造数桩、测试桩。自动化 ROI 低或有批量参数化的快胜路径。

---

## 三、✅ 已实现自动化的接口（35 个，8 个模块）

| 模块 | 数量 | 测试文件 | 覆盖接口 |
|------|------|----------|----------|
| alarms 报警 | 7 | test_alarm_controller.py | `/alarms`、`/alarms/{addr}`、`/alarms/latest/{addr}`、`/alarms/{id}`(PUT处理)、`batch-handle`、`batch-handle/ids`、`batch-info` |
| terminals/batch 终端批量 | 8 | test_batch_terminal_controller.py | `/batch`、`aggr-point-details`、`details`、`export`、`import`、`lnglat-details`、`move-group`、`remark` |
| groups 分组+组设备 | 6 | test_group_controller.py + test_terminal_controller.py | `/groups`、`/groups/{id}`、`{groupId}/terminals`、`{groupId}/terminals/batch`、`{addr}/follow`、`{addr}/move` |
| enclosures 围栏 | 5 | test_enclosure_controller.py | `/enclosures`、`{id}`、`codes/{shareCode}`、`{id}/export`、`{id}/terminals` |
| locations 定位 | 3 | test_location_controller.py | `/locations`、`/export`、`/track` |
| field-templates 字段模板 | 3 | test_field_template_controller.py | `/field-templates`、`{id}`、`{id}/fields` |
| alarm-settings 报警设置 | 2 | test_alarm_settings_controller.py | `/alarm-settings`、`{id}` |
| web-user 登录 | 1 | test_login.py | `/web-user/login`（正向在 conftest，负向有用例） |

> 质量提醒：已实现模块断言多停留在 `code/msg` 层，副作用（落库/消息推送/扣费）未验证。覆盖 ≠ 覆盖到位。

---

## 四、🔴 P0 未实现清单（143 个，16 个模块）

> 🔴🔴 标记 = P0 中的最高危（扣钱 / 改归属 / 砖机 / 账号安全），建议第一波补测。

### 4.1 emergency 应急/求救（18 个）⭐ 主人点名模块

**A. 求救群聊本体（emergency/chat/*）— 救命功能，触达失败=人命**

| 接口 | 风险点 |
|------|--------|
| `/api/monitor/emergency/chat/send` | 求救消息发送：幂等（不重复广播）、送达回执、漏触达 |
| `/api/monitor/emergency/chat/member/add` | 群成员添加：越权加人 |
| `/api/monitor/emergency/chat/member/edit` | 群成员编辑：越权改人 |
| `/api/monitor/emergency/chat/member/list` | 群成员查询 |
| `/api/monitor/emergency/chat/item/page` | 消息分页 |
| `/api/monitor/emergency/chat/item/all/read` | 全部已读：幂等 |
| `/api/monitor/emergency/chat/item/clear/all-unread` | 清未读 |
| `/api/monitor/emergency/chat/item/complete` | 结束求救会话：**状态机非法跃迁**（已结束又发消息？） |
| `/api/monitor/emergency/chat/item/complete/addr` | 按设备结束会话 |
| `/api/monitor/emergency/chat/item/complete/status` | 会话结束状态查询 |
| `/api/monitor/emergency/chat/record/page` | 聊天记录分页 |
| `/api/monitor/emergency/chat/record/read/list` | 已读列表 |
| `/api/monitor/emergency/chat/record/errorMsg` | 错误消息记录 |

**B. 求救套餐（emergency/combo/*）— 计费扣量，最高危**

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/emergency/combo/buy` | 购买套餐=扣星豆/扣费：**只扣一次、幂等、余额不足拦截** |
| `/api/monitor/emergency/combo/chat/item/info` | 套餐内消息条数信息 |
| `/api/monitor/emergency/combo/chat/item/remaining` | 剩余条数（对账基准） |
| `/api/monitor/emergency/combo/mall` | 套餐商城列表 |
| `/api/monitor/emergency/combo/usage/page` | 用量分页 |

### 4.2 app-users 小程序用户（25 个）— 绑定关系变更最大户

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/app-users/bind/addr` | 绑定设备：**越权绑定他人设备** |
| 🔴🔴 `/api/monitor/app-users/unbind/addr` | 解绑设备：归属变更、误解绑 |
| 🔴🔴 `/api/monitor/app-users/login/wx-applet` | 微信登录：账号体系入口 |
| 🔴🔴 `/api/monitor/app-users/login/wx-applet-password` | 微信密码登录 |
| 🔴🔴 `/api/monitor/app-users/bind/emergency-contact` | 绑定紧急联系人：**谁能成为我的求救对象** |
| 🔴🔴 `/api/monitor/app-users/bind/multiple-emergency-contact` | 批量绑定紧急联系人 |
| 🔴🔴 `/api/monitor/app-users/save/emergency-contact` | 保存紧急联系人 |
| 🔴🔴 `/api/monitor/app-users/delete/emergency-contact` | 删除紧急联系人 |
| 🔴🔴 `/api/monitor/app-users/unbind/emergency-contact/{phone}` | 解绑紧急联系人 |
| `/api/monitor/app-users/pre-bind/{sn}` | 预绑定校验 |
| `/api/monitor/app-users/pre-follow-platform/{followPlatformAccount}/{addr}` | 预关注平台 |
| `/api/monitor/app-users/location/report` | 位置上报 |
| `/api/monitor/app-users/location/report/{cardNum}/` | 按卡号位置上报 |
| `/api/monitor/app-users/voice-clone` | 声纹克隆：生物特征、隐私滥用 |
| `/api/monitor/app-users/voice-clone/enabled` | 声纹开关 |
| `/api/monitor/app-users/voice-clone/ref` | 声纹参考音频 |
| `/api/monitor/app-users/voice-clone/ref/play` | 播放参考音频 |
| `/api/monitor/app-users/applet-my-info` | 我的信息 |
| `/api/monitor/app-users/avatar-nickname` | 头像昵称 |
| `/api/monitor/app-users/emergency-contact` | 紧急联系人查询 |
| `/api/monitor/app-users/emergency-contact/friends` | 联系人好友 |
| `/api/monitor/app-users/friend/emergency-noti` | 好友紧急通知 |
| `/api/monitor/app-users/group/intercom` | 群对讲 |
| `/api/monitor/app-users/group/level` | 群等级 |
| `/api/monitor/app-users/info` | 用户信息 |

### 4.3 pn07 设备指令（21 个）— 设备写操作

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/pn07/codes/upgrade` | 固件升级：**失败砖机** |
| 🔴🔴 `/api/monitor/pn07/codes/restart` | 远程重启 |
| 🔴🔴 `/api/monitor/pn07/codes/shutdown` | 远程关机 |
| `/api/monitor/pn07/codes/text` | 下发文本指令 |
| `/api/monitor/pn07/codes/work-mode` | 工作模式 |
| `/api/monitor/pn07/codes/report-freq` | 上报频率 |
| `/api/monitor/pn07/codes/angle` | 角度 |
| `/api/monitor/pn07/codes/call-location` | 回拨定位 |
| `/api/monitor/pn07/codes/ip-domain` | IP/域名设置 |
| `/api/monitor/pn07/codes/device-id` | 设备ID设置 |
| `/api/monitor/pn07/codes/initialization` | 初始化 |
| `/api/monitor/pn07/codes/upgrade-setting` | 升级设置 |
| `/api/monitor/pn07/codes` | 指令列表 |
| `/api/monitor/pn07/codes/batch` | 批量指令：**幂等+部分失败** |
| `/api/monitor/pn07/codes/batch/{batchId}` | 批次删除 |
| `/api/monitor/pn07/codes/{id}` | 单条指令删/改 |
| `/api/monitor/pn07/codes/query/info` | 指令回执查询（验"指令真到了"） |
| `/api/monitor/pn07/codes/query/version` | 版本查询 |
| `/api/monitor/pn07/active` | 激活 |
| `/api/monitor/pn07/active/info/{addr}` | 激活信息 |
| `/api/monitor/pn07/active/upload` | 激活上传 |

### 4.4 pn06 设备指令（12 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/pn06/codes/upgrade` | 固件升级：砖机风险 |
| `/api/monitor/pn06/codes/text` | 文本指令 |
| `/api/monitor/pn06/codes/motion-mode` | 运动模式 |
| `/api/monitor/pn06/codes/timing-mode` | 定时模式 |
| `/api/monitor/pn06/codes/ip-port` | IP/端口 |
| `/api/monitor/pn06/codes/domain-port` | 域名/端口 |
| `/api/monitor/pn06/codes/feedback/{businessId}` | 指令反馈 |
| `/api/monitor/pn06/codes` | 指令列表 |
| `/api/monitor/pn06/codes/batch` | 批量指令 |
| `/api/monitor/pn06/codes/batch/{batchId}` | 批次删除 |
| `/api/monitor/pn06/codes/{id}` | 单条删/改 |
| `/api/datas/pn06` | pn06 数据上报 |

### 4.5 order 订单（6 个）— 纯资金流

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/order/payment` | 发起支付：**重复支付、金额篡改** |
| 🔴🔴 `/api/monitor/order/payment/wx/applet` | 微信小程序支付 |
| 🔴🔴 `/api/monitor/order/cancel` | 取消订单：**退款幂等、重复取消** |
| 🔴🔴 `/api/monitor/order/delete` | 删除订单 |
| `/api/monitor/order/page` | 订单列表（对账查询） |
| `/api/monitor/order/detail` | 订单详情 |

### 4.6 star-bean 星豆虚拟资产（4 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/star-bean/buy` | 充值星豆：**扣费守恒** |
| `/api/monitor/star-bean/calculate` | 价格计算（与 buy 金额对账） |
| `/api/monitor/star-bean/transaction/page` | 流水（资产守恒对账唯一真源） |
| `/api/monitor/star-bean/package/active` | 激活套餐 |

### 4.7 ver-codes 验证码（7 个）— 账号安全

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/ver-codes/login` | 登录验证码：**爆破** |
| 🔴🔴 `/api/monitor/ver-codes/register` | 注册验证码：**短信轰炸** |
| 🔴🔴 `/api/monitor/ver-codes/retrieve` | 找回密码验证码：**改密越权** |
| 🔴🔴 `/api/monitor/ver-codes/update/pwd` | 改密验证码 |
| `/api/monitor/ver-codes/bind/email` | 绑邮箱验证码 |
| `/api/monitor/ver-codes/bind/phone` | 绑手机验证码 |
| `/api/monitor/ver-codes/set/emergency-contact` | 设紧急联系人验证码 |

### 4.8 web-users 平台用户（13 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/web-users/pwd` | 修改密码 |
| 🔴🔴 `/api/monitor/web-users/reset-pwd` | 重置密码 |
| 🔴🔴 `/api/monitor/web-users/code/pwd` | 验证码改密 |
| 🔴🔴 `/api/monitor/web-users/authentication` | 实名认证 |
| `/api/monitor/web-users/phone` | 改手机号 |
| `/api/monitor/web-users/email` | 改邮箱 |
| `/api/monitor/web-users/name` | 改名称 |
| `/api/monitor/web-users/avatar` | 改头像 |
| `/api/monitor/web-users/platform-logo` | 平台logo |
| `/api/monitor/web-users/platform-name` | 平台名称 |
| `/api/monitor/web-users/info` | 用户信息 |
| `/api/monitor/web-users/records` | 操作记录 |
| `/api/monitor/web-users/pre-bind-validation` | 预绑定校验 |

### 4.9 web-sub-users 子账号（6 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/web-sub-users` | 子账号增删查（GET/POST） |
| 🔴🔴 `/api/monitor/web-sub-users/{account}` | 子账号改/删 |
| 🔴🔴 `/api/monitor/web-sub-users/{account}/bind` | 子账号绑定 |
| `/api/monitor/web-sub-users/{account}/reset` | 子账号重置 |
| `/api/monitor/web-sub-users/{account}/terminals` | 子账号终端 |
| `/api/monitor/web-sub-users/{account}/v2/terminals` | 子账号终端v2 |

### 4.10 ao-wei 奥纬绑定（8 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/ao-wei/bind/{addr}` | 绑定：**跨账号越权** |
| 🔴🔴 `/api/monitor/ao-wei/unbind/{addr}` | 解绑 |
| `/api/monitor/ao-wei/cancel-req/{addr}` | 取消请求 |
| `/api/monitor/ao-wei/modify/{addr}` | 修改 |
| `/api/monitor/ao-wei/status/{addr}` | 状态 |
| `/api/monitor/ao-wei/friends` | 好友 |
| `/api/monitor/ao-wei/info` | 信息 |
| `/api/monitor/ao-wei/my-list` | 我的列表 |

### 4.11 share 共享（7 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/share/users/{addr}/cancel` | 取消共享：**水平越权** |
| 🔴🔴 `/api/monitor/share/users/{addr}/batch/cancel` | 批量取消 |
| `/api/monitor/share/follow` | 关注 |
| `/api/monitor/share/pre-follow` | 预关注 |
| `/api/monitor/share/terminals` | 共享终端 |
| `/api/monitor/share/terminals/follow-num` | 关注数 |
| `/api/monitor/share/users/{addr}` | 共享用户 |

### 4.12 follow-platforms 关注平台（5 个）

| 接口 | 风险点 |
|------|--------|
| 🔴🔴 `/api/monitor/follow-platforms/{followPlatformAccount}/bind/{addr}` | 绑定终端 |
| 🔴🔴 `/api/monitor/follow-platforms/{followPlatformAccount}/remove/{addr}` | 移除终端 |
| `/api/monitor/follow-platforms` | 平台列表/新增 |
| `/api/monitor/follow-platforms/{followPlatformAccount}` | 平台删/改 |
| `/api/monitor/follow-platforms/terminals` | 平台终端 |

### 4.13 subscription 订阅（4 个）

| 接口 | 风险点 |
|------|--------|
| `/api/monitor/subscription/subscribe` | 订阅：状态机 |
| `/api/monitor/subscription/cancel` | 取消订阅：**重复取消/幂等** |
| `/api/monitor/subscription` | 订阅列表 |
| `/api/monitor/subscription/friends` | 订阅好友 |

### 4.14 mock-terminal 造数终端（4 个）

| 接口 | 风险点 |
|------|--------|
| `/api/monitor/mock-terminal` | 造数终端增删查：**数据污染源头**，补"用完即删"清理用例 |
| `/api/monitor/mock-terminal/{id}` | 改/删 |
| `/api/monitor/mock-terminal/init-loc` | 初始化位置 |
| `/api/monitor/mock-terminal/{id}/addrs` | 追加地址 |

### 4.15 offline-alarm-settings 离线报警设置（2 个）

| 接口 | 风险点 |
|------|--------|
| `/api/monitor/offline-alarm-settings` | 设置列表 |
| `/api/monitor/offline-alarm-settings/{id}` | 编辑设置：可配项测改前/改后/边界 |

### 4.16 msg-noti-records 通知记录（1 个）

| 接口 | 风险点 |
|------|--------|
| `/api/monitor/msg-noti-records/{type}` | 通知记录查询 |

---

## 五、🟡 P1 未实现清单（64 个，10 个模块）

### 5.1 intercom 对讲（19 个）

```
/api/monitor/intercom/group/create            群创建
/api/monitor/intercom/group/update            群更新
/api/monitor/intercom/group/delete            群删除（状态机）
/api/monitor/intercom/group/close             群关闭
/api/monitor/intercom/group/invitation        群邀请
/api/monitor/intercom/group/addr/remove       移除群设备
/api/monitor/intercom/group/cost              群费用（涉计费，留意）
/api/monitor/intercom/group/remainder         群剩余
/api/monitor/intercom/group/terminal/list     群终端列表
/api/monitor/intercom/group/closed/delivery/cancel   关闭投递取消
/api/monitor/intercom/member/update/nickname  成员昵称
/api/monitor/intercom/message/page            消息分页
/api/monitor/intercom/message/receive/info    接收信息
/api/monitor/intercom/message/clear/unread    清单未读（幂等）
/api/monitor/intercom/message/clear/all-unread 清全部未读（幂等）
/api/monitor/intercom/message/invitation/handler      邀请处理
/api/monitor/intercom/message/invitation/notice/list  邀请通知
/api/monitor/intercom/message/invitation/pending/count 待处理数
/api/monitor/intercom/message/send/invitation/list    发出的邀请
```

### 5.2 platform-chats 平台聊天（15 个）

```
/api/monitor/platform-chats/chat-list         会话列表
/api/monitor/platform-chats/chat-item         会话项删除
/api/monitor/platform-chats/chat-item/page    会话项分页
/api/monitor/platform-chats/query             查询
/api/monitor/platform-chats/records           记录删除
/api/monitor/platform-chats/unread            未读
/api/monitor/platform-chats/clear/all-unread  清全部未读
/api/monitor/platform-chats/clear/{addr}/unread   清单端未读
/api/monitor/platform-chats/{addr}            单会话详情
/api/monitor/platform-chats/{addr}/text       发文本（触达）
/api/monitor/platform-chats/{addr}/voice      发语音（触达）
/api/monitor/platform-chats/{addr}/follow/{follow}      关注开关
/api/monitor/platform-chats/{addr}/msg-remind/{notDisturb} 免打扰开关
/api/monitor/platform-chats/{id}/album        相册
/api/monitor/platform-chats/{id}/enhance/voice 语音增强
```

### 5.3 msg-notification 通知开关（11 个）— 可 1 个参数化用例批量覆盖

```
/api/monitor/msg-notification/msg-noti-setting          总设置
/api/monitor/msg-notification/bd-new-msg-noti-type      北斗新消息
/api/monitor/msg-notification/bd2-new-msg-noti-type     北斗2
/api/monitor/msg-notification/bd3-new-msg-noti-type     北斗3
/api/monitor/msg-notification/lora-new-msg-noti-type   LoRa
/api/monitor/msg-notification/tian-tong-new-msg-noti-type 天通
/api/monitor/msg-notification/yx-new-msg-noti-type     易信
/api/monitor/msg-notification/other-new-msg-noti-type  其他新消息
/api/monitor/msg-notification/other-alarm-noti-type    其他报警
/api/monitor/msg-notification/alarm-statistics-noti-setting 报警统计
（可配项：读→改→边界→非法值，一套模板跑全部）
```

### 5.4 beacons 信标（3 个）

```
/api/monitor/beacons  /api/monitor/beacons/all  /api/monitor/beacons/total
```

### 5.5 ok-msgs 报平安（4 个）

```
/api/monitor/ok-msgs            列表
/api/monitor/ok-msgs/mark       标记已读（幂等）
/api/monitor/ok-msgs/mark/all   全部已读（幂等）
/api/monitor/ok-msgs/unread-num 未读数一致性
```

### 5.6 h5-sms（3 个）

```
/api/monitor/h5-sms/info  /api/monitor/h5-sms/text  /api/monitor/h5-sms/chat-records
```

### 5.7 platform-mock-chats 造数（4 个，可降 P2）

```
/api/monitor/platform-mock-chats/platform/to/{addr}/text
/api/monitor/platform-mock-chats/{addr}/to/platform/text
/api/monitor/platform-mock-chats/{addr}/to/platform/image
/api/monitor/platform-mock-chats/{addr}/to/platform/voice
```

### 5.8 unread 未读（2 个）

```
/api/monitor/unread  /api/monitor/unread/chat
```

### 5.9 wx-service-notification 微信服务通知（2 个）

```
/api/monitor/wx-service-notification/subscribe  /api/monitor/wx-service-notification/subscribe/num
```

### 5.10 phrases 常用语（1 个）

```
/api/monitor/phrases/list
```

---

## 六、🟢 P2 未实现汇总（156 个，模块级）

| 类别 | 模块（数量） | 处理建议 |
|------|--------------|----------|
| 纯枚举字典 | enums(19) | **1 个参数化用例全包** |
| 造数/模拟 | h5-mock(13)、mock(5)、mock-device-chats(6)、mock-loc1~6(6)、mock-ok1/2(2)、datas 上报系列 bd/dc-http-push/fy/jili/pd15/pl/public-net/rtk/sms/tt/yixing(11)、platform-mock-chats 已在P1、mock-qr(1) | 造数工具为主，按需 |
| 地图/坐标 | h5-map(4)、map(6)、map-setting(1)、aggregation(2) | 静态资源，ROI 极低 |
| 大屏统计 | large-data-screen(8) | 只读聚合，冒烟即可 |
| 直播 | live-broadcast(7) | 业务边缘 |
| 第三方对接回调 | receive-event(6)、api/open(6)、ntn check/datas(2)、tianyi(1)、qianxun(1)、fzwlw(1)、terminal-status(1) | 需 mock 上游再测 |
| 群组查询类 | groups(8)：`chat`、`chat/members`、`select`、`{groupId}/terminals/from/list`、`yy/list`、`{addr}/comm-records`、`{id}/expand`、`{id}/select` | 介于 P1/P2，读接口，随 groups 二期补 |
| 登录页配置 | web-user(4)：`login-flag`、`login-page-info`、`rotate-image`×2 | 低 |
| 文件 | files(3)：`{fileId}`、`mp3`、`video` | 低 |
| 缓存 | cache(3) | 运维向 |
| 基站 | stations(4) | 随设备二期 |
| 救援队 | rescue(2) | 只读 |
| 测试桩 | test(6)、test-ali-text-check(1)、delayQueue、transaction、pool、ws/print、version、captcha、diag、config、suggestions、templates、terminal、retrieve、app/unread、sms(1)、bd(1) 等 | 生产无关/工具 |

> P2 明细合计 156（机器口径 157，含已被人工修正为"已实现"的 `alarms/{addr}` 1 条）。

---

## 七、补测建议（分层推进）

1. **第一波（🔴🔴 约 30 个）**：emergency/combo/buy + order 全套 + star-bean/buy —— **资金链路串测**（套餐购买→星豆扣减→订单生成→取消退款，验守恒与幂等）；加上 ver-codes 爆破/轰炸、web-sub-users 越权。
2. **第二波**：app-users 绑定/解绑/紧急联系人（越权矩阵）+ pn07/pn06 高危指令（upgrade/restart/shutdown 的幂等与回执）。
3. **快胜**：msg-notification 11 个开关 1 个参数化模板；enums 19 个 1 个参数化模板 —— 两个模板直接拿回 30 个接口覆盖。
4. **emergency/chat 群聊**：send 幂等 + 成员越权 + complete 状态机非法跃迁，三个用例锚住核心风险。
5. **每条用例要求**：自带数据构造与清理；写操作验证"只发生一次副作用"；断言分层到副作用（落库/消息/扣费）。

---

## 附：比对方法存档

- OAS 来源：Apifox MCP `read_project_oas`（实时刷新）
- 已实现提取：`testcases/*.py` 中 `url = f"{base_url}/..."` 及裸路径正则
- 匹配规则：路径变量名归一化 `{xxx}` → `{}`
- 已知局限：同段位不同变量名（`{addr}` vs `{id}`）需人工核对；带 query 的 URL（captcha）不参与匹配
