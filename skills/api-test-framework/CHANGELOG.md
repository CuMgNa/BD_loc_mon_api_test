## [Unreleased] — 2026-08-19 清理框架统一化

### Fixed
- `unpaid_order.register()` 从未接入 `registry.register_cleanup`，导致待支付订单从不进入 session 收尾调度——迁移为逐项 domain 后正式接入

### Added
- `registry.py`：`register_cleanup_once`（挂载前查重）、`unregister_cleanup`（按 domain 精确移除）
- `references/cleanup-framework.md`：新增清理域的 2×2 决策矩阵 + 三套模板 + checklist + 可移植性说明

### Changed
- `unpaid_order.py` / `intercom_group.py` 从「共享 domain + 模块内平行列表」迁移为「动态·逐项 domain」，复用 `registry.py` 新原语
- `b_terminals`/`b_groups` 清理逻辑从 `conftest.py` 内联函数挪进 `common/cleanup/terminal.py`/`group.py`（`cleaner_b` 变体）
- `references/conftest-jkpt.md`：同步过期的「内部辅助函数不在 common/」描述，补链接到 `cleanup-framework.md`

### Breaking
- `cleanup-report.yaml` / session 清理报告的 domain 粒度从「聚合一行」变为「逐项一行」（如 `intercom_groups: ...` 变成多条 `intercom_group_<gid>: ...`）；无代码依赖旧 key 名（已检索确认），仅影响人工读报告时的行数

---

## [Unreleased] — 2026-08-18 开跑清空 Allure raw

### Added
- `common.run_artifact_util.wipe_allure_raw_dirs`：按项目根删除 `temps/`、`allure-results/`
- `pytest_configure` 开跑调用（`config.rootpath`）；不删 `reports/`，session 结束不删

---

## [Unreleased] — 2026-08-18 下单限频共享冷却钟

### Added
- `common.buy_cooldown_util`：`wait_buy_cooldown` / `mark_bought`（进程内 65s 钟；套餐/星豆/订单 lifecycle 共用）

### Changed
- 商城 `TestEcm05Buy`、星豆 `TestSb03Buy`、订单 `ensure_lifecycle_*` 改为共享钟；lifecycle 遇 999 再买一次再 skip

---

## [Unreleased] — 2026-08-18 待支付单 session 收尾

### Added
- `common.order_cleanup_util`：`register_unpaid_order_no` / `cleanup_registered_unpaid_orders`（进程内名单，不写 extract）
- `cleanup_test_data` 步骤 0.5：对本轮登记单 cancel→delete；`ENABLE_AUTO_CLEANUP=false` 时保留给人工扫码

### Changed
- 商城 / 星豆正向 buy 成功后登记订单号；用例内仍不 cancel `combo_order_no` / `star_bean_order_no`

---

## [Unreleased] — 2026-08-18 Suites 四层对齐

### Added
- `SKILL.md` 第 4 层「Allure Suites 四层对齐」：文件→类→方法→parametrize 为通用轴；默认一类一报告分组单元
- `yaml-conventions.md` §8：jkpt 填法（一类一 HTTP 接口、`TestEn01` 前缀、不传 ids）
- HTTP 模板改为多类骨架（`Test01`/`Test02` 占位前缀 + `_XxxHelpers` + module 清理）

### Changed
- 有状态默认改为模式 B′（文件内多类 + extract）；模式 B 单类切片标为勿用于 Suites
- YAML `name` 不再写成「Allure 标题」；叶子不传中文 `ids=`、不用 `@allure.title(name)`
- `jkpt-api-test.mdc`：拆类 / 禁止切片 / 禁止中文 ids 写入必须与禁止
- `CONTRIBUTING.md`：编码模式变更须同步 mdc
- `methods-reference.md`：`case_name` 只说明附件标题

### Deprecated
- 同一 Test 类内 `test_data[:N]` 切片 CRUD（Allure 会摊平）；改用一类一 `*_cases`

---

## [Unreleased] — 2026-08-14 正向 expected.msg / 负向 expected.error_msg

### Added
- `common.yaml_util.read_expected_msg`：正向读 `msg`，负向读 `error_msg`

### Changed
- 全部 jkpt YAML 正向用例由 `error_msg: "成功"` 改为 `msg: "成功"`；负向仍用 `error_msg`
- testcase / `export_assert_util` / 模板改为 `read_expected_msg(case["expected"])`
- `yaml-conventions.md`：正向禁止写 `error_msg: "成功"`

---

## [Unreleased] — 2026-08-13 技能追上代码与运行时对齐

### Added
- `common.yaml_util.resolve_extract_value` / `is_extract_placeholder`：统一解析 `{{var}}`，`required=True` 时 `pytest.skip`
- `common.captcha_util.generate_captcha_id`：登录与 conftest 共用
- `conftest-jkpt.md`：`msg_test_terminal`、`terminal_use_scopes`、`terminal_type_enum_cases`、glht 清理（默认关闭）
- `methods-reference.md`：`parse_response_json` / `NonJsonResponseError` / `get_last_http_context` / `get_current_timestamp` / `assert_export_response`

### Changed
- `write_yaml` 文档改为真实签名 `(file_path, data, mode="append")`
- CRUD 用例与模板改为 import `resolve_extract_value`，不再各写一份 `_resolve_value`
- 批量导入模板改为 `testcases/fixtures/batch_import_template.xlsx`
- `login.yaml` 改名为 `test_login.yaml`
- 登录凭据改环境变量；文档只写变量名
- `ENABLE_GLHT_CLEANUP` 默认 `false`，避免每场 session 都登录 glht
- `pyproject.toml` 声明 `jsonpath`；`.gitignore` 忽略 `reports/`、`temps/`、`extract.yaml`
- `CONTRIBUTING.md`：本技能仅作本仓生成依据，不再写「复制 4 文件到新项目」


### Removed
- `jkpt_api_test/api_test_framework/`（`run_case` 引擎，jkpt 从未引用）
- `assets/templates/test_case_yaml.tpl.py`（模式 C）

### Changed
- `SKILL.md` / `methods-reference.md`：引擎层改为「已移除」，生成路径只保留模式 A/B/B′ 与协议层

---

## [Unreleased] — 2026-08-13 技能目录迁到仓库根 `skills/`

### Changed
- 技能从套娃路径 `jkpt_api_test/api-test-framework/api-test-framework/` 迁至 `skills/api-test-framework/`，与 Python 包 `api_test_framework/` 区分
- `.cursor/rules/jkpt-api-test.mdc` 及技能内指向 `conftest.py` / `common/` / `yaml/` 的相对链接已同步

---

## [Unreleased] — 2026-05-15 技能同步重构

### Added（新增）
- `SKILL.md` 顶部 **jkpt 标准栈声明**：明确通用层/适配层/禁止项三类边界
- `references/conftest-jkpt.md`（适配层）：jkpt 专属 fixture 表 + 依赖图
- `references/yaml-conventions.md`（适配层）：jkpt YAML 命名与占位符约定
- `references/methods-reference.md` 新增协议层 4 模块章节：
  - `common/bd_protocol_client.py`（11 个 `send_*`）
  - `common/protocol_transport.py`
  - `common/protocol_codec.py`
  - `common/protocol_types.py`
- `assets/templates/test_case_protocol.tpl.py`：协议用例模板
- `CONTRIBUTING.md`：文档同步约定
- `.cursor/rules/jkpt-api-test.mdc`（仓库根 `.cursor/rules/`）：Cursor 生成约束

### Changed（修改）
- `SKILL.md` 第 1 层增加「jkpt 不使用」警示；模式 C 标 `[可选/jkpt 未使用]`
- `SKILL.md` 项目文件结构骨架补充协议层 4 模块
- `references/methods-reference.md` 目录按「通用层 / 适配层 / 历史归档」分组
- `assets/templates/test_case_yaml.tpl.py` 文首标「jkpt 未使用，勿复制」

### Deprecated（标记弃用 / 勿生成）
- `api_test_framework.run_case`（jkpt 未使用）
- `api_test_framework/pytest_plugin.py`（文件不存在）
- `pytest_plugins = ["api_test_framework.pytest_plugin"]`

### Archived（归档）
- `拟改动范围说明.md` → `archive/拟改动范围说明.md`（其内容大部分已落地，由本 CHANGELOG 代替跟踪）

---

## 维护模板

```markdown
## [Unreleased] — YYYY-MM-DD <变更主题>

### Added
- `<新增文件或章节>`：<一句话用途>

### Changed
- `<被改文件>`：<改了什么、影响范围>

### Deprecated
- `<旧 API>`：<为何弃用、替代方案>

### Removed
- `<被删>`

### Fixed
- `<文档错误纠正>`
```
