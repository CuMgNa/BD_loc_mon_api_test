"""
test_xxx.py — CRUD有状态接口模板（模式B）
适用场景: 增删改查接口，后续接口依赖前面接口返回的ID
从 api-test-framework Skill 生成
"""

import jsonpath
import pytest
from common.common_data import get_current_datetime
from common.requests_util import BaseRequest
from common.yaml_util import read_yaml
from common.allure_assert_util import assert_api_result


class Test_xxxAPI:
    """
    XXX管理接口测试（CRUD）
    
    接口信息:
      - 创建: POST   /api/xxx
      - 编辑: PUT    /api/xxx/{id}
      - 删除: DELETE /api/xxx/{id}
      - 查询: GET    /api/xxx
    
    数据依赖:
      - test_edit 依赖 test_create 返回的 id
      - test_delete 可能依赖 conftest.py 中预创建的 fixture 数据
    """

    # ===== 类变量：跨方法共享创建的资源ID =====
    created_id = None

    # 1️⃣ 从YAML读取数据
    test_data = read_yaml("./yaml/test_xxx.yaml")["cases"]

    # ==================== CREATE：创建 ====================
    @pytest.mark.parametrize("case", test_data[:3])       # 前3条是创建用例
    def test_create(self, base_url, auth_headers, case):
        # 关键字匹配 → 动态修改数据（保证唯一性，避免名称冲突）
        if case.get("name") == "创建成功":
            case["name_field"] = f"测试_{get_current_datetime()}"

        url = f"{base_url}/api/xxx"
        payload = {"field1": case.get("name_field"), ...}

        res = BaseRequest().send_request(
            method="post", url=url, json=payload,
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        msg = jsonpath.JSONPath("$.msg").parse(res.json())[0]

        if code == 0:
            # ⭐ 提取ID → 存到类变量 → 后续方法使用
            Test_xxxAPI.created_id = jsonpath.JSONPath("$.data.id").parse(res.json())[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )

    # ==================== UPDATE：编辑（依赖CREATE）====================
    @pytest.mark.parametrize("case", test_data[3:5])     # 第4-5条是编辑用例
    def test_update(self, base_url, auth_headers, case):
        # 注入上一步创建的ID
        if "编辑成功" in case.get("name", ""):
            case["id"] = Test_xxxAPI.created_id          # ← 用类变量
            case["name_field"] = f"编辑_{get_current_datetime()}"

        url = f"{base_url}/api/xxx/{case['id']}"
        payload = {"id": case["id"], "field1": case["name_field"], ...}

        res = BaseRequest().send_request(
            method="put", url=url,
            params=payload or json=payload,              # 根据实际参数风格选择
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        msg = jsonpath.JSONPath("$.msg").parse(res.json())[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )

    # ==================== DELETE：删除 ====================
    @pytest.mark.parametrize("case", test_data[5:])     # 剩余是删除用例
    def test_delete(self, base_url, auth_headers, case, groupid1):  # ← 注入fixture
        # 通过关键字决定注入哪个ID
        casse_name = case.get("name", "")
        
        keywords_empty = ["删除成功-资源为空"]
        keywords_not_empty = ["删除失败-资源非空"]
        
        if any(kw in casse_name for kw in keywords_empty):
            case["id"] = Test_xxxAPI.created_id           # 自己创建的空资源
        elif any(kw in casse_name for kw in keywords_not_empty):
            case["id"] = groupid1                          # conftest预创建的非空资源

        url = f"{base_url}/api/xxx/{case['id']}"
        payload = {"id": case["id"]}

        res = BaseRequest().send_request(
            method="delete", url=url,
            params=payload,
            headers=auth_headers,
            case_name=case["name"], log_level="simple"
        )
        code = jsonpath.JSONPath("$.code").parse(res.json())[0]
        msg = jsonpath.JSONPath("$.msg").parse(res.json())[0]

        assert_api_result(
            case_name=case["name"],
            expected_code=case["expected"]["code"],
            expected_msg=case["expected"]["error_msg"],
            actual_code=code,
            actual_msg=msg,
            biz_context={"请求参数": payload}
        )
