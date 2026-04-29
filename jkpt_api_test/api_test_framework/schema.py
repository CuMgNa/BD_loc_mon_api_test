# api_test_framework/schema.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ApiCase:
    """用例数据模型"""
    name: str
    method: str
    path: str
    params: Optional[Dict] = None
    json: Optional[Dict] = None
    data: Optional[Dict] = None
    headers: Optional[Dict] = None
    expected: Optional[Dict] = None
    setup: Optional[List[Dict]] = None
    teardown: Optional[List[Dict]] = None
    extract: Optional[Dict] = None

    @classmethod
    def from_dict(cls, data: Dict) -> "ApiCase":
        """从字典创建ApiCase"""
        return cls(
            name=data.get("name", ""),
            method=data.get("method", "get"),
            path=data.get("path", ""),
            params=data.get("params"),
            json=data.get("json"),
            data=data.get("data"),
            headers=data.get("headers"),
            expected=data.get("expected"),
            setup=data.get("setup"),
            teardown=data.get("teardown"),
            extract=data.get("extract")
        )


def normalize_case(case: Union[Dict, ApiCase]) -> ApiCase:
    """统一转换为ApiCase"""
    if isinstance(case, ApiCase):
        return case
    return ApiCase.from_dict(case)