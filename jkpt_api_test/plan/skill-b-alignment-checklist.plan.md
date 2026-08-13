# 仓内 Skill（主体 B）对齐 — 任务执行清单

## 已拍板

- **主体**：仓库根 `skills/api-test-framework/` Skill，约束 AI 按同一套写法生成 jkpt 用例。
- **运行时**：`common/` + `conftest.py` + `testcases/` + `yaml/`。
- **不做什么**：不把 `api_test_framework/` 做成可安装框架；不以「第二个项目能否 import」为门槛。
- **评价标准**：新接口主要靠 Skill 生成；生成只走 `common.*` + 模式 A/B/B′；`common/` 新能力回写 Skill。

## 不要动（复审已排除）

- `yaml/监控平台.jmx`（协议出处）
- `yaml/import-device-template2026_5_1.xlsx`（导入活数据，只修路径）
- `archive/拟改动范围说明.md`（已归档）
- `assets/templates/` 整目录（技能载荷；模式 C 模板只加警告或移出 jkpt 生成路径，不整目录删除）
- `GeoPoint` / `get_current_timestamp` / `send_sms_94`：不是孤儿文件；后两项可另开「未覆盖 API」小任务

---

## P0 — 技能追上代码（B 的主回路）

技能是唯一真相源，当前已落后于 5 月之后的代码。

1. **补 `references/conftest-jkpt.md`**
   - 写入：`msg_test_terminal`、`terminal_use_scopes`、`terminal_type_enum_cases`
   - 写入：`glht_base_url` / `glht_token` / `glht_cleanup_test_data`（autouse）及对整场 session 的影响
   - 更新 fixture 依赖图与速查表
2. **修正 `references/methods-reference.md`**
   - `yaml_util.write_yaml` 改为真实签名 `(file_path, data, mode=)`
   - 补 `parse_response_json`、`NonJsonResponseError`、`get_last_http_context`、`get_current_timestamp`、`export_assert_util`
3. **改 `SKILL.md` 与事实一致**
   - 删除「common 间接使用引擎」
   - 协议用例列为正式模式（无 YAML / `assert result.success`），不要只藏在附录
   - CONTRIBUTING 去掉「新项目复制通用层 4 文件」；改成「仅本仓生成依据」
4. **`CHANGELOG.md` 补 Unreleased**：报警、枚举入库、导出断言、glht 清理、上述文档变更

验收：只 `@` 仓库技能，能写出与现有 `test_alarm_controller` / 协议用例同风格的新接口，且不出现 `run_case`。

---

## P1 — 运行时与技能规则对齐

5. **抽 `_resolve_value` 进 `common/`**（≥2 文件重复，已违反自定提取规则）
   - 改现有 testcase + `test_case_crud.tpl.py` 为 import
   - methods-reference + CHANGELOG 同步
6. **修好导入模板路径**
   - `_TEMPLATE_XLSX` 改为相对路径，指向 `yaml/import-device-template2026_5_1.xlsx`（或真正启用 `testcases/fixtures/` 并删掉另一份）
   - 删除未使用的 `_FIXTURE_DIR`
7. **依赖清单对齐**
   - `pyproject.toml` 声明 `jsonpath`（或实际用的包名）
   - 不用则去掉 `pytest-rerunfailures`，用则写入 `pytest.ini`

验收：`pytest testcases/test_batch_terminal_controller.py -q` 正向导入不再因绝对路径 skip；新用例不再手写一份 `_resolve_value`。

---

## P2 — 去掉 A 残骸对生成的干扰

8. **`methods-reference.md` 第 1–7 章**（`api_test_framework` 引擎）移到文末「历史归档」或单独 `archive/` 文档，生成路径默认看不到
9. **`test_case_yaml.tpl.py`**：保留则文首警告保持；从 jkpt 生成检查清单中彻底消失
10. **`login.yaml` 改名为 `test_login.yaml`**，同步 `test_login.py`（符合自定命名）
11. ~~`api_test_framework/` 归档~~ **已删除**（含模式 C 模板）
12. ~~技能目录去套娃~~ **已完成**：现为仓库根 `skills/api-test-framework/`

验收：Rules + SKILL + 模板三条路径都不再把 `run_case` 当成可选项。

---

## P3 — 套件行为（生成出来也会踩）

13. **`glht_cleanup_test_data` 改为非默认 autouse**（或 `ENABLE_GLHT_CLEANUP` 默认 false），并写入 conftest-jkpt
14. **凭据**：conftest 与适配层文档不要继续明文抄账号/密码哈希；改环境变量；文档只写变量名
15. **加 `.gitignore`**：`reports/`、`temps/`、`extract.yaml`、`__pycache__/`、`.pytest_cache/`
16. **`test_login.py`**：验证码走 conftest 已有能力，去掉类内复制的 captcha 流程（负向「验证码错误」除外）

验收：只跑 jkpt HTTP 用例时不必登录 glht；git status 不再被 Allure 产物淹没。

---

## P4 — 确认后的孤儿与断链

17. 删除 `_debug_terminalInfo.xlsx`
18. 二选一：删除 `testcases/fixtures/batch_import_template.xlsx`，或改为唯一导入模板并改代码
19. 修或删 `AGENTS.md` 里对已不存在的 `./skills/caveman/` 的引用

---

## 建议执行顺序

```
P0（技能补全） → P1-5（_resolve_value） → P1-6（xlsx 路径）
    → P2（去掉生成干扰） → P3（glht / gitignore / 凭据） → P4（真孤儿）
```

P2-11/12 改名可最后做，不阻塞前几项。

## 刻意不做

- 复活 `run_case` / `pytest_plugin` / OpenAPI 生成器
- 把协议、OCR、glht 抽成跨项目框架包
- 为「并行 xdist」重构 `extract.yaml`（需单独立项）
