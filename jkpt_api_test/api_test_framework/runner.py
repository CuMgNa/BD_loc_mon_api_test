# api_test_framework/runner.py
from typing import Dict, Optional
from api_test_framework.client import BaseRequest
from api_test_framework.schema import ApiCase, normalize_case
from api_test_framework.data import VariableStore
from api_test_framework.assertions import assert_response, extract_json_path


def run_case(
    case: ApiCase,
    base_url: str,
    headers: Optional[Dict] = None,
    variables: Optional[VariableStore] = None
) -> Dict:
    """
    完整用例执行生命周期

    1. normalize_case() -> 统一为 ApiCase
    2. variables.resolve(request) -> 替换 {{变量}}
    3. 合并 headers
    4. BaseRequest.send_request() -> 发请求
    5. assert_response() -> 执行所有断言
    6. _extract_values() -> 提取变量到 store
    """
    # 1. 标准化用例
    case = normalize_case(case)

    # 2. 解析变量
    if variables:
        url = variables.resolve(f"{base_url}{case.path}")
        if case.params:
            case.params = variables.resolve(case.params)
        if case.json:
            case.json = variables.resolve(case.json)
        if case.data:
            case.data = variables.resolve(case.data)
    else:
        url = f"{base_url}{case.path}"

    # 3. 合并 headers
    request_headers = headers or {}
    if case.headers:
        request_headers.update(case.headers)

    # 4. 发送请求
    http = BaseRequest()
    response = http.send_request(
        method=case.method,
        url=url,
        params=case.params,
        json=case.json,
        data=case.data,
        headers=request_headers,
        case_name=case.name
    )

    # 5. 解析响应
    json_data = response.json()

    # 6. 执行断言
    if case.expected:
        assert_response(json_data, case.expected)

    # 7. 提取变量
    if variables and case.extract:
        for key, path in case.extract.items():
            values = extract_json_path(json_data, path)
            if values:
                variables.set(key, values[0])

    return json_data