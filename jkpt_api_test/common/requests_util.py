# common/requests_util.py
import json
import logging
import time
from typing import Optional, Dict, Any

import requests

try:
    import allure
except Exception:  # pragma: no cover
    allure = None


_LAST_HTTP_CONTEXT: Dict[str, Any] = {}


def get_last_http_context() -> Dict[str, Any]:
    return _LAST_HTTP_CONTEXT.copy()


class BaseRequest:
    """增强版请求类，手写用例首选入口"""

    def __init__(self, timeout: int = 30, debug: bool = True):
        self.timeout = timeout
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        self.sensitive_keys = ['authorization', 'token', 'cookie', 'password', 'secret', 'key']

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
        """
        发送HTTP请求

        Args:
            method: HTTP方法 (get/post/put/delete/patch)
            url: 请求URL
            params: URL查询参数
            json: JSON请求体
            data: 表单请求体
            headers: 请求头
            files: 文件上传
            timeout: 超时秒数
            case_name: 用例名称（用于日志标识）
            log_level: 日志级别 (full/simple/none)
        """
        timeout = timeout or self.timeout

        # 日志输出
        if log_level == "full":
            print(f"\n[用例] {case_name}")
            print(f"[请求] {method.upper()} {url}")
            if params:
                sanitized_params = self._sanitize(params)
                print(f"[参数] {sanitized_params}")
            if headers:
                print(f"[请求头] {self._sanitize(headers)}")
            if json:
                print(f"[JSON] {self._sanitize(json)}")

        start = time.time()
        request_context = {
            "case_name": case_name,
            "method": method.upper(),
            "url": url,
            "params": self._sanitize(params),
            "json": self._sanitize(json),
            "data": self._sanitize(data),
            "headers": self._sanitize(headers),
        }

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
            elapsed_ms = int((time.time() - start) * 1000)
            response_context = self._build_response_context(response, elapsed_ms)
            self._attach_allure_context(request_context, response_context)
            self._set_last_http_context(request_context, response_context)

            if log_level in ("full", "simple"):
                try:
                    resp_json = response.json()
                    print(f"[响应] {resp_json}")
                except:
                    print(f"[响应] {response.text[:500]}")

            return response

        except requests.exceptions.RequestException as e:
            elapsed_ms = int((time.time() - start) * 1000)
            error_context = {
                "error_type": e.__class__.__name__,
                "error_message": str(e),
                "elapsed_ms": elapsed_ms,
            }
            self._attach_allure_context(request_context, None, error_context)
            self._set_last_http_context(request_context, None, error_context)
            print(f"[错误] 请求失败: {e}")
            raise

    def _sanitize(self, data: Optional[Dict]) -> Optional[Dict]:
        """过滤敏感信息"""
        if not isinstance(data, dict):
            return data
        sanitized = {}
        for k, v in data.items():
            if any(s in k.lower() for s in self.sensitive_keys):
                sanitized[k] = "******"
            else:
                sanitized[k] = v
        return sanitized

    @staticmethod
    def _to_pretty_json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    def _build_response_context(self, response: requests.Response, elapsed_ms: int) -> Dict[str, Any]:
        try:
            body = response.json()
        except Exception:
            body = response.text[:5000] if response.text else ""
        return {
            "status_code": response.status_code,
            "headers": self._sanitize(dict(response.headers)),
            "body": body,
            "elapsed_ms": elapsed_ms,
        }

    def _attach_allure_context(
        self,
        request_context: Dict[str, Any],
        response_context: Optional[Dict[str, Any]] = None,
        error_context: Optional[Dict[str, Any]] = None
    ) -> None:
        if allure is None:
            return
        allure.attach(
            self._to_pretty_json(request_context),
            name="request.json",
            attachment_type=allure.attachment_type.JSON
        )
        if response_context is not None:
            allure.attach(
                self._to_pretty_json(response_context),
                name="response.json",
                attachment_type=allure.attachment_type.JSON
            )
        if error_context is not None:
            allure.attach(
                self._to_pretty_json(error_context),
                name="request_error.json",
                attachment_type=allure.attachment_type.JSON
            )

    def _set_last_http_context(
        self,
        request_context: Dict[str, Any],
        response_context: Optional[Dict[str, Any]] = None,
        error_context: Optional[Dict[str, Any]] = None
    ) -> None:
        global _LAST_HTTP_CONTEXT
        payload: Dict[str, Any] = {"request": request_context}
        if response_context is not None:
            payload["response"] = response_context
        if error_context is not None:
            payload["error"] = error_context
        _LAST_HTTP_CONTEXT = payload