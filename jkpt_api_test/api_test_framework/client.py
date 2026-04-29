# api_test_framework/client.py
import requests
import logging
from typing import Optional, Dict, Any


class BaseRequest:
    """轻量HTTP客户端"""

    def __init__(self, timeout: int = 30, debug: bool = True):
        self.timeout = timeout
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    def send_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None,
        case_name: str = "",
        log_level: str = "simple"
    ) -> requests.Response:
        """发送HTTP请求"""
        timeout = timeout or self.timeout

        # 日志输出
        if log_level == "full":
            print(f"[请求] {method.upper()} {url}")
            if params:
                print(f"[参数] {params}")
            if headers:
                print(f"[请求头] {self._sanitize_headers(headers)}")
            if json:
                print(f"[JSON] {json}")

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                data=data,
                headers=headers,
                files=files,
                timeout=timeout
            )

            if log_level in ("full", "simple"):
                try:
                    resp_json = response.json()
                    print(f"[响应] {resp_json}")
                except:
                    print(f"[响应] {response.text[:500]}")

            return response

        except requests.exceptions.RequestException as e:
            print(f"[错误] 请求失败: {e}")
            raise

    def _sanitize_headers(self, headers: Dict) -> Dict:
        """过滤敏感信息"""
        sensitive_keys = ['authorization', 'token', 'cookie', 'password', 'secret', 'key']
        sanitized = {}
        for k, v in headers.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "******"
            else:
                sanitized[k] = v
        return sanitized