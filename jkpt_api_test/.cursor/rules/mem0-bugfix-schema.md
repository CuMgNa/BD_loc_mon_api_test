# mem0 Bugfix 记忆 · 共享 Schema 与模板

> 本文件被 `mem0-bugfix-recorder.mdc` 与 `mem0-bugfix-recall.mdc` 共同引用。
> 适配项目：`jkpt_api_test`（Python / pytest / requests / yaml 接口自动化测试框架）。
> mem0 MCP 已切换为官方云端 `streamable-http`，工具名为 `add_memory` / `search_memories` / `update_memory` / `get_memory` / `delete_memory`。

## 1. 记忆正文 · 7 段式模板

固定结构，单条 150–400 字，每段一句、独立一行，便于向量切分与召回：

```
[场景] 在 <模块/接口/fixture> 中出现 <报错关键词>。
[触发条件] 当 <前置条件/参数/环境> 时发生。
[根因] 真实原因是 <一句话根因>，背后机制是 <机制说明>。
[排查路径] 关键定位手段：<日志关键字/工具/复现命令>。
[修复方案] 推荐做法：<最终采纳的修复>；次选：<备选方案>。
[验证方式] 通过 <验证步骤/pytest 用例> 确认已修复。
[反模式] 不要 <常见错误修法，会导致 X>。
```

> 错误码、接口路径、异常类名、关键变量名、pytest 节点名 **原文保留**，不要意译 —— 否则关键词召回会失效。

## 2. 元数据 · metadata（适配本项目）

```json
{
  "type": "bugfix",
  "category": "api_failure | test_failure | fixture_failure | assertion_failure | env_failure | config_failure",
  "project": "jkpt_api_test",
  "module": "conftest | protocol_codec | protocol_transport | terminal_controller | batch_terminal | bd_protocol | export_assert",
  "stack": ["python", "pytest", "requests", "yaml"],
  "error_signature": "<ExceptionClass>@<module.function> 或 <error_keyword>@</api/path>",
  "severity": "P0|P1|P2|P3",
  "tags": [],
  "source": "cursor-agent",
  "verified": true,
  "parent_id": null
}
```

- `error_signature` 是**去重主键**：格式 `<异常类/错误关键词>@<module.function 或 接口路径>`。
- `module` / `category` 取上面枚举值之一；无法归类时填 `unknown`。

## 3. 抽取 JSON（Agent 内部产物）

```json
{
  "scene": "...",
  "trigger": "...",
  "root_cause": "...",
  "debug_path": "...",
  "fix_primary": "...",
  "fix_alt": "...",
  "verify": "...",
  "anti_pattern": "...",
  "metadata": { /* 见第 2 节 */ }
}
```

字段缺失时：
- 可推断的 → 填入并在末尾加 `(推断)`；
- 无法推断的 → 填 `"unknown"`，并把 `metadata.verified` 置为 `false`。

## 4. 官方云端 mem0 工具调用约定

- 写入：`add_memory(text, user_id="tongmeina", metadata={...}, source="cursor-agent")`
- 更新：`update_memory(memory_id, text, source="cursor-agent")`
- 检索：`search_memories(query, filters={"AND": [{"user_id": "tongmeina"}]}, top_k=5, source="cursor-agent")`
  - 注意：**不是** 旧本地脚本的 `search_memory`，参数用 `top_k` 而非 `limit`。
  - `filters` 只接受官方允许键：`user_id` / `agent_id` / `run_id` / `app_id` / `categories` / `keywords` / `metadata` / `created_at` / `updated_at` / `memory_ids` 等。
  - **自定义字段**（`type` / `project` / `module` / `error_signature`）不能直接作为顶层 filter 键，否则报 `Unknown filter key`；需放在 `{"metadata": {...}}` 下，或先按 `user_id` 检索再在返回结果的 `metadata` 上人工比对。
  - 返回结果含 `score` 与 `metadata`，可参考但不作为唯一判断依据。

## 5. 硬约束

- 禁止编造根因；不确定写 `疑似:...` 并 `verified:false`。
- 错误码、接口路径、异常类名原文保留。
- 单条正文 ≤ 400 字；超长则拆主记忆 + 子记忆，`metadata.parent_id` 串联。
- 不写时间、人名、聊天上下文等易变信息。
- 去重不强依赖 score：只有明确匹配相同 `error_signature` 且能取到 `memory_id` 时才 `update_memory`，否则 `add_memory`。
