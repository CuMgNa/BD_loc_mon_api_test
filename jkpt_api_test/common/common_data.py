# common/common_data.py
from datetime import datetime


def get_current_datetime(format: str = "%Y%m%d%H%M%S") -> str:
    """
    获取当前日期时间字符串

    Args:
        format: 日期格式，默认为 "%Y%m%d%H%M%S" (如 20260427133000)

    Returns:
        格式化后的日期时间字符串
    """
    return datetime.now().strftime(format)


def get_current_timestamp() -> int:
    """获取当前时间戳（13位毫秒）"""
    return int(datetime.now().timestamp() * 1000)