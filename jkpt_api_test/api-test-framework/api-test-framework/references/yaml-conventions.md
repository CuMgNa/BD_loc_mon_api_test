# jkpt — YAML 测试数据约定

> **适配层文档（仅 jkpt_api_test）**。其他项目用本仓库技能时按相同结构自建 `yaml-conventions-<project>.md`。
>
> 通用 SKILL 第 5 层「YAML 数据文件格式规范」已含跨项目共识；本文件**只**补 jkpt 特定约定（顶层 key 命名、占位符、运行时注入等）。

实例参考：[../../../yaml/test_location_controller.yaml](../../../yaml/test_location_controller.yaml)、[../../../yaml/test_group_controller.yaml](../../../yaml/test_group_controller.yaml)、[../../../yaml/test_terminal_controller.yaml](../../../yaml/test_terminal_controller.yaml)

---

## 1. 文件命名与文件头

| 项 | 约定 |
|----|------|
| 文件名 | `yaml/test_<controller>.yaml`，与 testcase `testcases/test_<controller>.py` 一一对应 |
| 文件头注释 | 第 1 行写 `# yaml/test_xxx.yaml`，紧随 2–4 行说明：接口、占位符解析方式、特殊字段（如时区） |
| 编码 | UTF-8，缩进 2 空格 |

文件头示例（取自 `test_location_controller.yaml`）：

```yaml
# yaml/test_location_controller.yaml
# 位置管理接口：分页列表、轨迹、导出
# addr 占位 {{bd_test_terminal}} 由 test_location_controller.py 解析
# startTimeStr/endTimeStr 省略时由代码按 Asia/Shanghai 当天 00:00:00–23:59:59 注入
```

---

## 2. 顶层 key 命名

### 模式

`<动词或场景>_<模块>_cases` 或 `<模块>_<动作>_cases`。**多场景一个文件，多顶层 key**。

| 类型 | 命名 | 实例 |
|------|------|------|
| 列表/分页 | `<module>_list_cases` | `location_list_cases`、`list_field_templates_cases` |
| 详情 | `<module>_detail_cases` / `get_<module>_cases` | `get_groups_cases` |
| 新增 | `add_<module>_cases` | `add_terminal_cases`、`add_field_template_cases` |
| 修改 | `update_<module>_cases` | `update_group_cases` |
| 删除 | `delete_<module>_cases` | `delete_field_template_cases` |
| 批量 | `batch_<动作>_cases` | `batch_import_cases`、`batch_delete_cases` |
| 业务动作 | `<动作>_<module>_cases` | `sort_groups_cases`、`follow_terminal_cases` |
| 协议/导出/特殊 | 自由命名 + `_cases` | `location_export_cases`、`location_track_cases` |

**强约定**：顶层 key 必须以 `_cases` 结尾，与 `@pytest.mark.parametrize` 的 `test_data["<key>"]` 一一映射。

### 同文件多顶层 key

按业务流程划分；CRUD 类常见组合：

```yaml
add_xxx_cases:
update_xxx_cases:
get_xxx_cases:
delete_xxx_cases:
```

在 testcase 内分别用 `@pytest.mark.parametrize("case", test_data["add_xxx_cases"])` 等绑定各方法。

---

## 3. 每个 case 的字段约定

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 用例名称，**语义化**含模块/动作/正负向；用于关键字匹配、Allure 标题、日志 |
| `expected.code` | int | 预期业务码（与项目接口规范一致；成功一般为 0） |

### 推荐字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `expected.error_msg` | str | 预期错误信息（与 `assert_api_result` 的 `expected_msg` 对齐） |
| `scenario` | str | 场景标签：`positive` / `empty_xxx` / `no_auth` / `invalid_xxx` 等，便于 testcase 分支与统计 |
| `no_auth` | bool | 用例级鉴权开关；testcase 内 strip `Authorization` |
| `expected.http_status` | int | 仅非 JSON 响应（如导出二进制）才用 |
| `binary_response` | bool | 标明响应为二进制流（如文件导出），跳过 `.json()` |

### `name` 命名建议

格式：`<模块>-<动作>-<正/负向>-<细节>`

示例：

- `"分页查询位置列表-正向"`
- `"分页查询位置列表-负向-addr为空"`
- `"分页查询位置列表-负向-未授权"`
- `"添加分组-一级分组-负向-分组名称大于20"`

testcase 内可用 `if "正向" in case["name"]` / `if "负向" in case["name"]` 做分支。

---

## 4. 占位符与运行时注入

### 4.1 `{{变量名}}`（与 `extract.yaml` 联动）

适用「同文件内接口 A 响应 → 接口 B 请求」。

- **写入**（上游 testcase）：`write_yaml("./extract.yaml", {"devices_addr": addr}, mode="append")`
- **YAML 引用**：`addr: "{{devices_addr}}"`
- **读取**（下游 testcase）：`self._resolve_value("{{devices_addr}}", required=True)`

`required=True` 且变量未提取时 `pytest.skip`。

### 4.2 `{{bd_test_terminal}}` 特例

由 testcase（如 `test_location_controller.py`）**显式解析**，**不**走 `extract.yaml`：

```python
def _resolve_bd_addr(self, raw_addr, bd_test_terminal):
    if raw_addr == "{{bd_test_terminal}}":
        return bd_test_terminal
    return raw_addr
```

理由：`bd_test_terminal` 是 session 级 fixture 返回的固定 addr，**不写入** `extract.yaml`。

### 4.3 `{{three_id}}` / `{{one_id}}`（分组占位）

**两种通道并存**：

- 走 `group_fixture`：testcase 内 `if "{{three_id}}" in str(case["groupId"]): group_id = group_fixture["three_id"]`
- 走 `extract.yaml`：上游 `test_group_controller` 创建成功后 `write_yaml` 写入 `one_id/two_id/three_id`，下游模块用 `_resolve_value`

按接口依赖选用；**不要**同时使用两种方式写同一字段。

### 4.4 运行时占位符（不在 YAML 求值）

YAML 字面量串如 `"Updated_{int(time.time())}"`，**testcase 内 `case["x"].replace("{int(time.time())}", str(int(time.time())))` 替换**，**禁止**在 YAML 写可执行表达式（不使用 `!python/expr` 等扩展）。

### 4.5 时区 / 日期窗口

如 `startTimeStr` / `endTimeStr` 在 YAML 中省略，**testcase 内按 `Asia/Shanghai` 当天 00:00–23:59:59 注入**（参考 `test_location_controller.py` `_build_location_query_params`）。

---

## 5. expected 结构

### 5.1 标准（JSON 响应）

```yaml
expected:
  code: 0
  error_msg: "成功"
```

`assert_api_result` 直接读 `case["expected"]["code"]` 与 `case["expected"]["error_msg"]`。

### 5.2 二进制响应

```yaml
binary_response: true
expected:
  http_status: 200
  code: 999            # 若服务对失败仍返回 JSON
  error_msg: "失败"
```

testcase 内分支处理 `.json()` vs `.content`。

### 5.3 不要扩展 `assertions[]` 数组

**禁止**采用全局 Cursor 技能里的 `assertions: [{type: ..., expected: ...}]` 结构 —— jkpt 不使用 `run_case`，断言一律走 `assert_api_result` + 必要的 jsonpath 手写。

---

## 6. 顺序与切片

| 习惯 | 说明 |
|------|------|
| 正向在前，负向在后 | 便于 `test_data[:N]` 切片用于「先 CREATE 成功后 UPDATE」 |
| 多正向时第一条为基线 | 便于「只写一次 extract」类逻辑（如 `_first_addr_extracted`） |
| 删除类放最后 | 避免后续用例无数据可用 |

---

## 7. 与 SKILL / conftest 的映射

| YAML 现象 | 对应能力 |
|----------|---------|
| 顶层 `_cases` 多块 | 模式 B / B′ 多个 `parametrize` |
| `{{bd_test_terminal}}` | conftest `bd_test_terminal` fixture |
| `{{one_id}}` 等分组占位 | conftest `group_fixture` 或 `extract.yaml` |
| `no_auth: true` | testcase 内 strip Authorization 头 |
| `expected.error_msg` | `assert_api_result(expected_msg=...)` |

完整 fixture 文档见 [conftest-jkpt.md](conftest-jkpt.md)。

---

## 8. 自检清单

写完 YAML 对照：

- [ ] 顶层 key 以 `_cases` 结尾且与 testcase `parametrize` 一致
- [ ] 每个 case 至少有 `name` + `expected.code`
- [ ] 占位符 `{{xxx}}` 在 testcase 中有明确解析路径（fixture 或 `_resolve_value`）
- [ ] 没有可执行表达式（如 `!python` / `eval`）
- [ ] 没有硬编码生产 URL / 真实密码 / 真实手机号
- [ ] 没有引入 `assertions[]` 数组（jkpt 不使用）
- [ ] 时区敏感字段在 testcase 注入而非 YAML 字面量
