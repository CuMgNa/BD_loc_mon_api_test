# Changelog

所有对 `api-test-framework/` 技能（SKILL、references、templates）的变更，按时间倒序记录。

> 维护原则（详见 [CONTRIBUTING.md](CONTRIBUTING.md)）：
> - 改 `common/*.py` → 至少更新 `references/methods-reference.md` 或本文件
> - 改 `conftest.py` fixture → 更新 `references/conftest-jkpt.md`
> - 改 YAML 字段约定 → 更新 `references/yaml-conventions.md`

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
