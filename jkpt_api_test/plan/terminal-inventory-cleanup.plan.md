---
description: 管理员系统库存查询与删除清理计划（与 jkpt 清理架构分离，独立运转）
todos:
  - id: add-glht-fixtures
    content: 在 conftest.py 新增 glht_base_url / glht_token fixtures 和 _glht_cleanup_inventory 函数
    status: pending
  - id: add-autouse-cleanup
    content: 新增 session autouse cleanup 独立清理 glht 入库记录
    status: pending
  - id: run-verify
    content: 运行验证清理逻辑正确性
    status: pending
---

# 计划：管理员系统库存查询与删除清理

> jkpt（监控平台）与 glht（管理员系统）是**两个完全独立系统**，清理架构各自独立、互不干扰。

## 背景

| 系统 | 用途 | base URL |
|------|------|----------|
| jkpt（监控平台） | 设备监控、分组管理 | `http://back.tdwtv2.pg8.ink` |
| glht（管理员系统） | 管理员登录、入库记录管理 | `http://back.tdwt.admin.pg8.ink` |

- **glht 登录账号**：`admin` / `123abc!!`
- 清理对象：`/api/admin/inventory` 中的入库记录（按当日日期模糊匹配）
- jkpt 现有 `cleanup_test_data` 保持不变，独立运转

---

## 接口信息（来自 apifox-glht MCP）

### 1. 管理员登录
- **POST** `/api/admin/login`
- Body: `{"account": "admin", "password": "123abc!!"}`
- 响应 `data.token` 即为 Authorization token

### 2. 查询入库记录
- **GET** `/api/admin/inventory`
- Query 参数：

| 参数 | 值 | 说明 |
|------|-----|------|
| `Authorization` | `{glht_token}` | 登录获取 |
| `content` | `YYYY-MM-DD` | 年月日模糊搜索 |
| `index` | `0` | 0=全部 |
| `specifyTime` | `false` | 不指定时间范围 |
| `startTimeStr` | `""` | 空字符串 |
| `endTimeStr` | `""` | 空字符串 |
| `page` | `1` | 默认第1页 |
| `pageSize` | `100` | 默认100条 |

- 响应结构：`data.list[].{id, addr, sn, name, terminalType, useScope, timeStr, ...}`

### 3. 批量删除
- **DELETE** `/api/admin/inventory`
- Body: `{"ids": "id1,id2,id3"}`（逗号分隔的 ID 字符串）
- 响应 `code == 0` 表示成功

---

## 数据流

```mermaid
flowchart TD
    subgraph jkpt_cleanup [jkpt cleanup_test_data]
        J1[删除设备] --> J2[删除分组]
    end

    subgraph glht_cleanup [glht 独立清理]
        G1[glht_cleanup_test_data<br/>session autouse] --> G2[POST /api/admin/login<br/>获取 glht_token]
        G2 --> G3[GET /api/admin/inventory<br/>content=当日日期]
        G3 --> G4{records > 0?}
        G4 -->|是| G5[DELETE /api/admin/inventory<br/>ids=id1,id2,..."]
        G4 -->|否| G6[无需清理]
        G5 --> G7[打印清理结果]
    end
```

---

## 文件变更

### conftest.py — 新增 glht 清理 region

在 `conftest.py` 末尾（`cleanup_test_data` region 之后）新增独立 region：

```python
# ==================== glht 管理员系统清理（独立运转） ====================
GLHT_BASE_URL_DEFAULT = "http://back.tdwt.admin.pg8.ink"


def _glht_cleanup_inventory(glht_token: str, glht_base_url: str, date_str: str) -> int:
    """根据日期查询并删除 glht 入库记录，返回删除条数（内部函数）"""
    # 1. 查询入库记录
    resp = http.send_request(
        method="get",
        url=f"{glht_base_url}/api/admin/inventory",
        params={
            "Authorization": glht_token,
            "content": date_str,
            "index": 0,
            "specifyTime": False,
            "startTimeStr": "",
            "endTimeStr": "",
            "page": 1,
            "pageSize": 100,
        },
        case_name=f"glht查询入库记录 {date_str}",
        log_level="none",
    )
    json_data = parse_response_json(resp, context="glht查询入库记录")
    code = _jsonpath_parse(json_data, "$.code")[0]
    if code != 0:
        key("glht查询失败", f"code={code}")
        return 0

    records = _jsonpath_parse(json_data, "$.data.list[*]")
    if not records:
        key(f"glht {date_str}", "无入库记录")
        return 0

    ids = [r for r in _jsonpath_parse(json_data, "$.data.list[*].id") if r]
    if not ids:
        return 0

    # 2. 批量删除
    del_resp = http.send_request(
        method="delete",
        url=f"{glht_base_url}/api/admin/inventory",
        params={"Authorization": glht_token},
        json={"ids": ",".join(ids)},
        case_name="glht批量删除入库记录",
        log_level="none",
    )
    del_json = parse_response_json(del_resp, context="glht删除入库记录")
    del_code = _jsonpath_parse(del_json, "$.code")[0]
    if del_code != 0:
        del_msg = _jsonpath_parse(del_json, "$.msg")[0] if _jsonpath_parse(del_json, "$.msg") else "未知"
        key("glht删除失败", f"code={del_code}, msg={del_msg}")
        return 0

    key(f"glht清理 {date_str}", f"删除 {len(ids)} 条入库记录")
    return len(ids)


@pytest.fixture(scope="session")
def glht_base_url():
    """glht 管理员系统 base URL"""
    import os
    return os.environ.get("GLHT_BASE_URL", GLHT_BASE_URL_DEFAULT)


@pytest.fixture(scope="session")
def glht_token(glht_base_url):
    """glht 管理员系统登录，获取 glht token"""
    sep(" 🔐 glht 管理员登录 ")
    resp = http.send_request(
        method="post",
        url=f"{glht_base_url}/api/admin/login",
        json={"account": "admin", "password": "123abc!!"},
        case_name="glht管理员登录",
        log_level="none",
    )
    json_data = parse_response_json(resp, context="glht管理员登录")
    code = _jsonpath_parse(json_data, "$.code")[0]
    assert code == 0, f"glht 登录失败: code={code}, msg={_jsonpath_parse(json_data, '$.msg')[0]}"
    token = _jsonpath_parse(json_data, "$.data.token")[0]
    key("glht token", f"{token[:20]}...")
    return token


@pytest.fixture(scope="session", autouse=True)
def glht_cleanup_test_data(glht_token, glht_base_url):
    """glht 入库记录清理（session 结束时自动执行，独立于 jkpt cleanup_test_data）"""
    from datetime import datetime, timezone, timedelta

    yield

    if not ENABLE_AUTO_CLEANUP:
        sep(" ⚠️  glht 自动清理已禁用 (ENABLE_AUTO_CLEANUP=false)")
        return

    sep(" 🧹 glht 入库记录清理 ")
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    try:
        deleted = _glht_cleanup_inventory(glht_token, glht_base_url, today)
        key("glht清理结果", f"删除 {deleted} 条入库记录")
    except Exception as e:
        key("glht清理异常", str(e))

    sep(" 🎉 glht 清理完成 ")
```

---

## 架构说明

| 设计 | 说明 |
|------|------|
| 职责分离 | glht 清理与 jkpt 清理**完全独立**，各管各的系统 |
| autouse session | glht 清理在 session 结束时自动执行，无需手动挂载到用例 |
| 独立 token | glht 有自己的 session 级 `glht_token` fixture，与 jkpt 的 `auth_token` 互不干扰 |
| 架构一致 | 全部使用 `http.send_request`、`_jsonpath_parse`、`parse_response_json`、`sep()`、`key()` |
