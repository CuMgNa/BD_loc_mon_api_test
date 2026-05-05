# common/protocol_types.py
"""北斗协议相关数据类型定义"""
from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass
class GeoPoint:
    """WGS84 经纬度坐标点"""
    lon: float
    lat: float

    def as_tuple(self) -> Tuple[float, float]:
        return (self.lon, self.lat)


@dataclass
class ProtocolSendResult:
    """协议发送结果"""
    status_code: int
    code: int
    msg: str
    raw_response: Dict[str, Any] = field(default_factory=dict)
    request_body: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status_code == 200 and self.code == 0
