# common/protocol_codec.py
"""北斗协议编码工具：时间HEX、坐标HEX(INT/DMS)、手机号HEX、随机点/轨迹、XOR校验

完全对应 监控平台.jmx 中 JSR223Sampler / BeanShellSampler 里的 Groovy 逻辑。
"""
import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

# 默认中心点（广州附近，与 JMX centerLat=23.170439, centerLon=113.466203 对齐）
DEFAULT_CENTER_LON = 113.466203
DEFAULT_CENTER_LAT = 23.170439
DEFAULT_RADIUS_M = 100        # 单点随机半径
DEFAULT_TRAJECTORY_STEP_M = 10  # 轨迹相邻点间距

# 默认手机号（用于 13/14/94 协议未传 phone 时）：纯数字字符串，会按 ASCII 编码为 HEX
DEFAULT_PHONE = "13250703582"

# 北京时区
_CST = timezone(timedelta(hours=8))


class ProtocolCodec:
    """协议字段编码工具集（无状态，全部静态方法）"""

    # ========== 时间相关 ==========

    @staticmethod
    def hex_timestamp_up() -> str:
        """当前 Unix 秒级时间戳大写 HEX
        对应 JMX BeanShell：Long.toHexString(currentTimeMillis).toUpperCase()
        """
        return f"{int(time.time()):X}"

    @staticmethod
    def hex_datetime_cst() -> dict:
        """北京时间各分量 2 位 HEX 字符串
        对应 JMX：hexyear/hexMonth/hexday/hexhour/hexminute/hexsecond
        """
        now = datetime.now(_CST)
        return {
            "yy": f"{now.year % 100:02X}",
            "mm": f"{now.month:02X}",
            "dd": f"{now.day:02X}",
            "hh": f"{now.hour:02X}",
            "mi": f"{now.minute:02X}",
            "ss": f"{now.second:02X}",
        }

    @staticmethod
    def hex_ts_deltas(count: int = 5, step_sec: int = 5) -> List[str]:
        """过去 N 个时间点的秒级 HEX，每步 step_sec 秒
        对应 JMX 0x15 协议 hexMin1..5
        返回 [最近, ..., 最早]，长度为 count
        """
        now = int(time.time())
        return [f"{(now - step_sec * (i + 1)):X}" for i in range(count)]

    # ========== INT 格式坐标（用于 13/14/15/92/93）==========

    @staticmethod
    def lon_int_hex(lon: float) -> str:
        """经度 INT4 字节 HEX：lon * 1e6 取整 → 4 字节大端 HEX
        对应 JMX convertToSpecialHex(lon, 4)
        """
        return ProtocolCodec._scale_to_hex(lon, 4)

    @staticmethod
    def lat_int_hex(lat: float) -> str:
        """纬度 INT4 字节 HEX"""
        return ProtocolCodec._scale_to_hex(lat, 4)

    @staticmethod
    def _scale_to_hex(value: float, byte_count: int) -> str:
        scaled = int(value * 1e6)
        # 4 字节大端有符号整数
        return scaled.to_bytes(byte_count, byteorder="big", signed=True).hex().upper()

    # ========== DMS 格式坐标（用于 A4/EE/E1）==========

    @staticmethod
    def lon_dms_hex(lon: float) -> str:
        """经度 DMS 8 字符 HEX：度(2)+分(2,含方向位)+秒(2)+小秒(2)
        对应 JMX dmsToHexComponents(decimal, isLongitude=true)
        """
        return ProtocolCodec._dms_hex(lon, is_longitude=True)

    @staticmethod
    def lat_dms_hex(lat: float) -> str:
        """纬度 DMS 8 字符 HEX"""
        return ProtocolCodec._dms_hex(lat, is_longitude=False)

    @staticmethod
    def _dms_hex(decimal: float, is_longitude: bool) -> str:
        abs_dec = abs(decimal)
        degrees = int(abs_dec)
        remaining = (abs_dec - degrees) * 60
        minutes = int(remaining)
        seconds = (remaining - minutes) * 60
        sec_int = int(seconds)
        subsec_int = int((seconds - sec_int) * 100)

        # 方向位写到 minutes 最高位
        if is_longitude:
            # 经度：负数为西经
            if decimal < 0:
                minutes |= 0x80
            else:
                minutes &= 0x7F
        else:
            # 纬度：负数为南纬
            if decimal < 0:
                minutes |= 0x80
            else:
                minutes &= 0x7F

        return f"{degrees:02X}{minutes:02X}{sec_int:02X}{subsec_int:02X}"

    # ========== 手机号 HEX ==========

    @staticmethod
    def phone_hex(phone: str) -> str:
        """手机号 → HEX

        规则：
        - 空字符串 / None → 用 DEFAULT_PHONE 的数字转换HEX
        - 纯数字字符串 → 作为数字转换为5字节HEX，不足前面补零
        - 合法 HEX 串（包含字母 A-F，长度为10）→ 大写返回
        - 其他非法字符 → 回退到 DEFAULT_PHONE
        """
        if phone is None or phone == "":
            return ProtocolCodec._phone_to_int_hex(DEFAULT_PHONE)

        # 纯数字 → 作为数字转换为5字节HEX
        if phone.isdigit():
            return ProtocolCodec._phone_to_int_hex(phone)

        # 合法 HEX 串且长度为10（5字节）→ 大写返回
        if all(c in "0123456789abcdefABCDEF" for c in phone) and len(phone) == 10:
            return phone.upper()

        # 其他非法 → 回退默认
        return ProtocolCodec._phone_to_int_hex(DEFAULT_PHONE)

    @staticmethod
    def _phone_to_int_hex(phone: str) -> str:
        """手机号作为数字转换为5字节HEX，不足前面补零"""
        phone_num = int(phone)
        return format(phone_num, '010X')  # 5字节=10个16进制字符，前面补零

    # ========== 方向角 HEX ==========

    @staticmethod
    def angle_hex(angle_deg: int) -> str:
        """方向角 0-360° → 4 字符 HEX（2字节）"""
        return f"{int(angle_deg) & 0xFFFF:04X}"

    # ========== XOR 校验 ==========

    @staticmethod
    def calc_xor(hex_str: str) -> str:
        """对 HEX 字符串各字节做异或，返回 2 字符 HEX
        对应 JMX 0xA4 协议 calculateXorChecksum
        """
        s = hex_str.replace(" ", "").upper()
        if len(s) % 2 != 0:
            raise ValueError("hex 字符串长度必须为偶数")
        result = 0
        for i in range(0, len(s), 2):
            result ^= int(s[i:i + 2], 16)
        return f"{result:02X}"

    # ========== 随机点 / 轨迹 ==========

    @staticmethod
    def random_point(
        center_lon: float = DEFAULT_CENTER_LON,
        center_lat: float = DEFAULT_CENTER_LAT,
        radius_m: float = DEFAULT_RADIUS_M,
    ) -> Tuple[float, float]:
        """在中心点半径 radius_m 米圆内均匀随机取一个点（WGS84）
        对应 JMX generateRandomPoint
        """
        angle = random.random() * 2 * math.pi
        distance = radius_m * math.sqrt(random.random())

        delta_north = distance * math.cos(angle)
        delta_east = distance * math.sin(angle)

        lat_delta = delta_north / 110574.0
        lon_delta = delta_east / (111320.0 * math.cos(math.radians(center_lat)))

        return (center_lon + lon_delta, center_lat + lat_delta)

    @staticmethod
    def random_trajectory(
        count: int = 5,
        center_lon: float = DEFAULT_CENTER_LON,
        center_lat: float = DEFAULT_CENTER_LAT,
        step_m: float = DEFAULT_TRAJECTORY_STEP_M,
    ) -> Tuple[List[Tuple[float, float]], int]:
        """从中心点附近随机起点，沿同一随机方向生成 count 个等距点
        对应 JMX generateTrajectory（17 步翻译为可配置 count）

        返回：(points, angle_deg)
            points: WGS84 坐标列表
            angle_deg: 方向角 0-360（用于 0xA4 angle_hex 字段）
        """
        start_lon, start_lat = ProtocolCodec.random_point(center_lon, center_lat)
        angle_rad = random.random() * 2 * math.pi
        angle_deg = int(math.degrees(angle_rad)) % 360

        delta_x = step_m * math.cos(angle_rad)
        delta_y = step_m * math.sin(angle_rad)

        lon_delta = delta_x / (111320.0 * math.cos(math.radians(start_lat)))
        lat_delta = delta_y / 110574.0

        points = [
            (start_lon + lon_delta * i, start_lat + lat_delta * i)
            for i in range(count)
        ]
        return points, angle_deg


def resolve_phone_hex(phone: str | None, default_phone: str = DEFAULT_PHONE) -> str:
    """解析 phone 入参为 HEX

    - 空 → 返回 default_phone 的数字转换HEX
    - 否则交给 ProtocolCodec.phone_hex 处理
    """
    if phone is None or phone == "":
        return ProtocolCodec._phone_to_int_hex(default_phone)
    return ProtocolCodec.phone_hex(phone)
