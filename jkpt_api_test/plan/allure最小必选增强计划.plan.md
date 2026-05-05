---
name: Allure最小必选增强计划
overview: 仅聚焦 Allure 报告最小必选能力，确保导出报告能稳定展示请求参数、请求头、响应结果和失败原因，满足快速定位问题的底线需求。
todos:
  - id: analyze-current-allure
    content: 确认当前报告最小必选字段覆盖范围与缺失项（请求头/参数/响应/失败原因）
    status: pending
  - id: enhance-request-attachments
    content: 在 BaseRequest 中统一追加最小必选请求与响应附件（含脱敏）
    status: pending
  - id: enhance-failure-context
    content: 在测试与钩子中补充最小必选失败上下文、断言差异与 traceback
    status: pending
  - id: validate-minimal-output
    content: 使用至少1条失败样本验证最小必选输出完整性
    status: pending
  - id: export-and-check
    content: 生成并导出报告，确认离线查看信息完整
    status: pending
isProject: false
---

# Allure 报告最小必选计划

## 现状分析（基于当前报告）

- 当前报告入口是 `[C:\Users\33606\Desktop\jkpt_api_test\reports\index.html](C:\Users\33606\Desktop\jkpt_api_test\reports\index.html)`，Allure 版本为 `2.39.0`。
- 统计结果显示 4 条用例全部通过，失败数为 0，因此当前报告里没有可直接验证“失败原因展示效果”的样本。
- 用例明细（如 `[C:\Users\33606\Desktop\jkpt_api_test\reports\data\test-cases\37b5659761812a89.json](C:\Users\33606\Desktop\jkpt_api_test\reports\data\test-cases\37b5659761812a89.json)`）仅包含 `parameters.case`，未看到请求头、请求体、响应体、异常堆栈等 Allure attachment。
- 请求发送逻辑在 `[C:\Users\33606\Desktop\jkpt_api_test\common\requests_util.py](C:\Users\33606\Desktop\jkpt_api_test\common\requests_util.py)`，目前主要是控制台打印，未写入 Allure 附件。
- 测试用例在 `[C:\Users\33606\Desktop\jkpt_api_test\testcases\test_login.py](C:\Users\33606\Desktop\jkpt_api_test\testcases\test_login.py)`，断言失败时仅有普通 `assert` 提示，缺少结构化失败上下文。

## 改造目标（仅最小必选）

- 报告中每条 API 测试都可直接查看：请求方法/URL、请求头、请求参数（query/json/form）、响应状态码、响应头、响应内容。
- 失败场景可直接查看：断言期望与实际、接口响应关键信息、异常堆栈、关联请求上下文。
- 导出后的 Allure 报告在离线查看时也能完整保留上述信息。

## 最小必选范围定义

- 请求信息：`method`、`url`、`query/body/json`、请求头（脱敏后）。
- 响应信息：`status_code`、响应头、响应体、请求耗时。
- 失败信息：断言期望/实际差异、异常 traceback、失败时关联请求与响应快照。
- 基础元信息：用例名、环境标识（如 base_url / env）、基础标签（模块/接口）。

## 实施方案（仅最小必选）

- 在 `[C:\Users\33606\Desktop\jkpt_api_test\common\requests_util.py](C:\Users\33606\Desktop\jkpt_api_test\common\requests_util.py)` 增加统一 Allure 记录能力：
  - 封装请求/响应序列化函数（含敏感字段脱敏）。
  - 每次请求后用 `allure.attach(..., attachment_type=...)` 附加 `request.json`、`response.json`。
  - 响应非 JSON 时回退文本附件，避免解析失败导致信息缺失。
- 在 `[C:\Users\33606\Desktop\jkpt_api_test\testcases\test_login.py](C:\Users\33606\Desktop\jkpt_api_test\testcases\test_login.py)` 强化失败可读性：
  - 将断言改为“带上下文”的断言消息（期望/实际/用例名/关键字段）。
- 在 `[C:\Users\33606\Desktop\jkpt_api_test\conftest.py](C:\Users\33606\Desktop\jkpt_api_test\conftest.py)` 增加全局失败补充机制：
  - 通过 `pytest_runtest_makereport` 在失败时自动附加异常信息与 traceback 到 Allure。
  - 如存在最近一次请求上下文（可由 BaseRequest 暴露），失败时自动附加，避免只看到断言文本。
- 增加最小验证失败样本（新增或临时启用 1 条必失败用例）用于验证报告效果：
  - 验证报告是否出现完整的请求、响应、失败原因附件。
  - 验证导出报告在本地打开时内容完整可读。
- 最后统一执行报告生成与导出命令，确认最小必选信息在离线报告中可查看。

## 验收标准

- 任一测试用例详情页可直接看到请求与响应附件，不依赖控制台日志。
- 失败用例详情页可直接看到失败原因（断言差异 + traceback + 关联请求响应）。
- 导出后的报告可离线复现同样信息，不出现关键调试信息丢失。
- 不实现推荐项与高阶项（如趋势治理、flaky 统计、缺陷平台联动）作为本次范围边界。

