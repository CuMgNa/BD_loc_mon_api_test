---
name: 测试设备数据自动清理方案
overview: 通过在 pytest session 结束时自动删除测试期间创建的所有设备，解决测试产生垃圾数据的问题
todos:
  - id: track_groups
    content: 在 conftest.py 的 group_fixture 中添加分组 ID 追踪
    status: pending
  - id: add_cleanup_logic
    content: 在 clear_data_per_session fixture 中添加设备清理逻辑
    status: pending
  - id: test_cleanup
    content: 测试验证清理功能是否正常工作
    status: pending
isProject: false
---

## 问题分析

当前测试存在的问题：

1. 每次执行 [test_add_terminal](jkpt_api_test/testcases/test_terminal_controller.py:24) 方法都会创建新的设备
2. 批量添加接口 [test_batch_add_terminals](jkpt_api_test/testcases/test_terminal_controller.py:103) 会创建多个设备
3. 测试结束后，这些设备保留在平台上，产生大量垃圾数据
4. 多次执行测试会不断累积垃圾数据

## 解决方案

采用 **统一清理机制**，在 pytest session 结束时按照正确的顺序自动删除所有测试创建的设备和分组。

### 实现步骤

1. **在 conftest.py 中添加设备追踪机制**
  - 修改 `group_fixture`，在 pytest.config.stash 中存储分组 ID
  - 确保每个测试 session 创建的分组都能被追踪
2. **实现设备批量删除函数**
  - 使用 `/api/monitor/terminals/batch` 接口批量删除设备
  - 需要先获取每个分组下的设备列表
  - 支持传入设备地址列表进行批量删除
3. **实现分组删除函数**
  - 使用 `/api/monitor/groups/{groupId}` 接口删除分组
  - 按照三级 → 二级 → 一级的顺序删除空分组
  - 处理删除失败的情况
4. **创建清理 fixture**
  - 创建 session 级别的 autouse fixture
  - 在 yield 之后执行清理逻辑
  - 先删除所有设备，再按顺序删除分组
5. **清理流程**

```
   测试开始
     ↓
   创建带时间戳后缀的测试分组 (L1_xxx, L2_xxx, L3_xxx)
     ↓
   在这些分组下创建设备进行测试
     ↓
   测试结束
     ↓
   步骤1: 批量删除所有测试分组下的设备
   步骤2: 按顺序删除空分组 (三级 → 二级 → 一级)
   

```

### 具体修改

**修改文件：** [jkpt_api_test/conftest.py](jkpt_api_test/conftest.py)

**修改位置：**

1. **第 32 行后**：添加环境变量配置 `ENABLE_AUTO_CLEANUP`
2. **第 187-255 行**：修改 `group_fixture` fixture
  - 在 pytest.config.stash 中存储创建的分组 ID
  - 返回完整的分组信息供清理使用
3. **第 290-295 行**：修改 `clear_data_per_session` fixture
  - 简化为只负责清理 extract.yaml
  - 实际数据清理由新的 cleanup fixture 处理
4. **第 295 行后**：添加新的函数和 fixture
  - `cleanup_terminals_batch()` - 批量删除设备函数
  - `get_terminals_by_group()` - 获取分组下的设备列表
  - `delete_groups_in_order()` - 按顺序删除分组
  - `cleanup_test_data()` - 清理 fixture

## 详细代码实现

### 1. 添加环境变量配置（第 32 行后）

```python
import os

# ==================== 配置清理行为 ====================
ENABLE_AUTO_CLEANUP = os.getenv("ENABLE_AUTO_CLEANUP", "true").lower() == "true"
```

### 2. 修改 group_fixture fixture（第 187-255 行）

在现有代码的基础上，在 `return group_ids` 之前添加以下代码：

```python
    # 将分组 ID 写入 extract.yaml
    write_yaml("./extract.yaml", group_ids, mode="append")

    # 将分组 ID 存储到 pytest.config.stash 供清理使用
    if hasattr(pytest, 'config'):
        pytest.config.stash.setdefault('test_group_ids', []).extend([
            group_ids["one_id"],
            group_ids["two_id"],
            group_ids["three_id"]
        ])

    return group_ids
```

### 3. 添加设备批量删除函数（第 295 行后）

```python
# ==================== 设备和分组清理 ====================
def get_terminals_by_group(base_url, auth_headers, group_id):
    """获取指定分组下的所有设备地址列表"""
    url = f"{base_url}/api/monitor/groups/{group_id}/terminals"
    params = {"page": 1, "pageSize": 1000}

    resp = http.send_request(
        method="get",
        url=url,
        params=params,
        headers=auth_headers,
        case_name=f"获取分组 {group_id} 下的设备",
        log_level="none"
    )

    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]

    if code == 0:
        # 提取设备地址列表
        terminals = _jsonpath_parse(json_data, "$.data.list[*].addr")
        return terminals if terminals else []
    else:
        key(f"获取分组 {group_id} 设备失败", "将返回空列表")
        return []

def cleanup_terminals_batch(base_url, auth_headers, group_id, addrs):
    """批量删除指定分组下的设备"""
    if not addrs:
        key(f"分组 {group_id}", "无设备需要删除")
        return 0, 0

    url = f"{base_url}/api/monitor/terminals/batch"
    data = {"addrs": addrs}

    resp = http.send_request(
        method="delete",
        url=url,
        json=data,
        headers=auth_headers,
        case_name=f"批量删除分组 {group_id} 下的设备",
        log_level="none"
    )

    json_data = resp.json()
    code = _jsonpath_parse(json_data, "$.code")[0]

    if code == 0:
        deleted_count = _jsonpath_parse(json_data, "$.data.deletedCount")
        if deleted_count:
            key(f"✅ 分组 {group_id} 设备删除", f"成功删除 {deleted_count[0]} 个设备")
            return int(deleted_count[0]), 0
        else:
            key(f"✅ 分组 {group_id} 设备删除", "删除成功")
            return len(addrs), 0
    else:
        msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
        key(f"❌ 分组 {group_id} 设备删除失败", f"code={code}, msg={msg}")
        return 0, len(addrs)

def delete_groups_in_order(base_url, auth_headers, group_ids):
    """按顺序删除分组：三级 → 二级 → 一级"""
    groups_url = f"{base_url}/api/monitor/groups"
    success_count = 0
    fail_count = 0

    # 按三级、二级、一级的顺序删除
    delete_order = ["three_id", "two_id", "one_id"]

    for level in delete_order:
        group_id = group_ids.get(level)
        if group_id is None:
            continue

        delete_url = f"{groups_url}/{group_id}"
        resp = http.send_request(
            method="delete",
            url=delete_url,
            headers=auth_headers,
            case_name=f"删除{level}分组 {group_id}",
            log_level="none"
        )

        json_data = resp.json()
        code = _jsonpath_parse(json_data, "$.code")[0]

        if code == 0:
            success_count += 1
            key(f"✅ 删除{level}分组 {group_id}", "成功")
        else:
            fail_count += 1
            msg = _jsonpath_parse(json_data, "$.msg")[0] if _jsonpath_parse(json_data, "$.msg") else "未知错误"
            key(f"❌ 删除{level}分组 {group_id} 失败", f"code={code}, msg={msg}")

    return success_count, fail_count
```

### 4. 添加清理 fixture（第 295 行后）

```python
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data(base_url, auth_headers, group_fixture):
    """在 session 结束时自动清理测试数据和分组"""
    yield

    # 检查是否启用自动清理
    if not ENABLE_AUTO_CLEANUP:
        sep(" ⚠️  自动清理已禁用 (ENABLE_AUTO_CLEANUP=false)")
        return

    sep(" 🧹 开始清理测试数据 ")

    # 获取需要清理的分组 ID
    if hasattr(pytest, 'config') and 'test_group_ids' in pytest.config.stash:
        group_ids = pytest.config.stash['test_group_ids']
        group_dict = {
            "one_id": group_ids[0] if len(group_ids) > 0 else None,
            "two_id": group_ids[1] if len(group_ids) > 1 else None,
            "three_id": group_ids[2] if len(group_ids) > 2 else None
        }
    else:
        # 如果 stash 中没有，从 group_fixture 中获取
        group_dict = group_fixture

    # 步骤1: 批量删除所有测试分组下的设备
    sep(" 步骤1: 删除设备 ")
    total_deleted_terminals = 0
    total_failed_terminals = 0

    for level in ["three_id", "two_id", "one_id"]:
        group_id = group_dict.get(level)
        if group_id:
            addrs = get_terminals_by_group(base_url, auth_headers, group_id)
            if addrs:
                deleted, failed = cleanup_terminals_batch(base_url, auth_headers, group_id, addrs)
                total_deleted_terminals += deleted
                total_failed_terminals += failed

    key("设备删除统计", f"成功: {total_deleted_terminals}, 失败: {total_failed_terminals}")

    # 步骤2: 按顺序删除空分组 (三级 → 二级 → 一级)
    sep(" 步骤2: 删除分组 ")
    group_success, group_fail = delete_groups_in_order(base_url, auth_headers, group_dict)
    key("分组删除统计", f"成功: {group_success}, 失败: {group_fail}")

    sep(" 🎉 清理完成 ")
```

### 5. 修改 clear_data_per_session fixture（第 290-295 行）

```python
@pytest.fixture(scope="session", autouse=True)
def clear_data_per_session():
    """在 session 开始和结束时清理临时数据文件"""
    sep(" 🚀 测试开始 ")
    clear_yaml()
    yield
    sep(" 🏁 测试结束 ")
    # 注意：实际的设备和分组清理在 cleanup_test_data fixture 中执行
```

## 清理流程详解

1. **测试开始时**：
  - `clear_data_per_session` 清理 extract.yaml
  - `group_fixture` 创建带时间戳后缀的测试分组（L1_xxx, L2_xxx, L3_xxx）
  - 将分组 ID 存储到 pytest.config.stash
2. **测试过程中**：
  - 测试用例在这些分组下创建设备进行测试
  - 所有测试数据都在带时间戳的分组中
3. **测试结束时**：
  - `cleanup_test_data` fixture 自动执行
  - 步骤1：调用 `/api/monitor/terminals/batch` 批量删除所有测试分组下的设备
  - 步骤2：按三级 → 二级 → 一级的顺序删除空分组
  - 输出详细的清理统计信息

## API 接口说明

- **删除设备接口**: `DELETE /api/monitor/terminals/batch`
  - 请求体: `{"addrs": ["addr1", "addr2", ...]}`
  - 响应: 包含 deletedCount 字段，显示删除的设备数量
- **删除分组接口**: `DELETE /api/monitor/groups/{groupId}`
  - 依赖：分组必须为空（无子分组和设备）
  - 因此需要按从下到上的顺序删除：三级 → 二级 → 一级

### 优势

1. **自动化**：无需手动干预，测试结束后自动清理
2. **完整性**：清理所有测试创建的设备和分组
3. **安全性**：只删除带时间戳后缀的测试分组，不影响正常数据
4. **顺序正确**：先删除设备，再按三级→二级→一级的顺序删除分组
5. **可追溯**：通过时间戳后缀可以识别测试数据
6. **可控制**：通过环境变量可以禁用自动清理

### 使用方式

```bash
# 默认启用自动清理
pytest testcases/test_terminal_controller.py -v

# 禁用自动清理（保留测试数据）
set ENABLE_AUTO_CLEANUP=false
pytest testcases/test_terminal_controller.py -v

# 或者在 Linux/Mac 下
export ENABLE_AUTO_CLEANUP=false
pytest testcases/test_terminal_controller.py -v
```

### 注意事项

- 需要确保删除设备和分组的 API 存在且可正常工作
- 清理失败时会有明确的错误提示和统计信息
- 分组删除必须按照三级→二级→一级的顺序，否则会因依赖关系而失败
- 可以通过环境变量 `ENABLE_AUTO_CLEANUP` 控制是否启用自动清理

