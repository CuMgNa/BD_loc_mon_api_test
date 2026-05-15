# 贡献规范 — api-test-framework 技能

本技能（[SKILL.md](SKILL.md) + references + assets/templates）是 jkpt 接口测试用例生成的**唯一真相源**。维护要点：**改代码必改文档，改文档必同步 CHANGELOG**。

## 三类变更 → 必须同步的文件

| 改了什么 | 必须同步 |
|---------|---------|
| `common/<新模块或新方法>` | [references/methods-reference.md](references/methods-reference.md) 对应章节 + [CHANGELOG.md](CHANGELOG.md) |
| `conftest.py` 新增 / 修改 fixture | [references/conftest-jkpt.md](references/conftest-jkpt.md) 速查表 / 详解 / 依赖图 + [CHANGELOG.md](CHANGELOG.md) |
| YAML 字段约定（新增顶层 key 模式、占位符、`expected` 结构） | [references/yaml-conventions.md](references/yaml-conventions.md) + [CHANGELOG.md](CHANGELOG.md) |
| 新增用例编码模式 / 调整 import 路径 | [SKILL.md](SKILL.md)（模式 / 必须 / 禁止）+ `assets/templates/` 模板 + [CHANGELOG.md](CHANGELOG.md) |
| 标记某能力废弃 / 未实现 | 在原文加 `> ⚠️ ...` 块 + [CHANGELOG.md](CHANGELOG.md) Deprecated 段 |

## 公共能力提取流程（从 testcase → common）

满足 **以下任一两条**才提取：

1. ≥2 个 testcase 重复 ≥5 行同样逻辑
2. 不抽出会漏断言 / 漏 Allure 上下文
3. import 路径稳定（`from common.xxx import yyy`）

步骤：

1. 抽函数到 `common/<topic>_util.py`，保持行为不变
2. 改写原 testcase 为 import 调用
3. 在 [methods-reference.md](references/methods-reference.md) 加章节（签名 + 一段最小用例）
4. 若改了用例模式 → 同步 [SKILL.md](SKILL.md) + 模板
5. 在 [CHANGELOG.md](CHANGELOG.md) `[Unreleased]` 记录
6. 跑 pytest 验证：

```powershell
pytest testcases/test_<受影响模块>.py -q --tb=short
```

## 不要做

- 不要在 `conftest.py` 写 `extract.yaml`（清理职责分离）
- 不要新增 `headers_no_auth` 等同义 fixture
- 不要在 testcase 直接 `import api_test_framework.*`
- 不要在 YAML 写可执行表达式
- 不要把项目专属（特定账号、URL、业务 ID）写进通用层（SKILL / methods-reference）；写进 `references/conftest-jkpt.md` 或 `.cursor/rules/jkpt-api-test.mdc`

## 文档分层（避免污染通用层）

| 层 | 文件 | 是否跨项目可复用 |
|----|------|--------------|
| 通用层 | [SKILL.md](SKILL.md) | ✅ |
| 通用层 | [references/methods-reference.md](references/methods-reference.md) | ✅ |
| 通用层 | [assets/templates/test_case_simple.tpl.py](assets/templates/test_case_simple.tpl.py)、[test_case_crud.tpl.py](assets/templates/test_case_crud.tpl.py)、[test_case_protocol.tpl.py](assets/templates/test_case_protocol.tpl.py) | ✅ |
| 适配层 | [references/conftest-jkpt.md](references/conftest-jkpt.md) | ❌ 仅 jkpt |
| 适配层 | [references/yaml-conventions.md](references/yaml-conventions.md) | ❌ 仅 jkpt |
| 适配层 | `.cursor/rules/jkpt-api-test.mdc` | ❌ 仅 jkpt |

新项目复用：复制通用层 4 个文件，自建 `conftest-<project>.md`、`yaml-conventions-<project>.md`、`.cursor/rules/<project>-api-test.mdc`。

## CHANGELOG 写法

模板见 [CHANGELOG.md](CHANGELOG.md) 文末。优先级：

1. Added（新增章节 / 文件 / 模板）
2. Changed（行为或写法变更）
3. Deprecated（标记勿生成）
4. Removed / Fixed

PR / commit message 引用 CHANGELOG 章节标题即可。
