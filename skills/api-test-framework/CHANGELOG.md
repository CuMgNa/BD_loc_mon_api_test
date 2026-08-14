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
