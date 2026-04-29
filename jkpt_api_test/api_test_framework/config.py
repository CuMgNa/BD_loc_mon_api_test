# api_test_framework/config.py
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ApiTestConfig:
    """API测试配置dataclass"""
    base_url: str
    timeout: int = 30
    debug: bool = True
    log_level: str = "simple"


def load_config() -> ApiTestConfig:
    """从环境变量和YAML配置加载配置"""
    base_url = os.getenv("API_TEST_BASE_URL", "http://back.tdwtv2.pg8.ink")
    timeout = int(os.getenv("API_TEST_TIMEOUT", "30"))
    debug = os.getenv("API_TEST_DEBUG", "true").lower() == "true"
    log_level = os.getenv("API_TEST_LOG_LEVEL", "simple")

    return ApiTestConfig(
        base_url=base_url,
        timeout=timeout,
        debug=debug,
        log_level=log_level
    )