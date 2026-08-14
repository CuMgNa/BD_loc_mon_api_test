# common/rescue_platform_client.py
"""卫星应急救援终端平台（10304）上行模拟造数客户端

覆盖 6 种终端上行报文形态（U0~U5）：
    U0 login(仅登录) / U1~U4 position(reportFlag=0/1/2/10) / U5 speech(语音)

用法（用例层唯一入口）：
    rescue_client.send_position(sn, report_flag=1)   # 按键SOS建群
    rescue_client.send_speech(sn)                    # 语音消息（默认412B样本）

设计依据（2026-08-14 Spike 实锤）：
- terminalId 上限 12 位（13位起登录帧被静默丢弃）——SN 用 12 位短号
- hardwareId 任意值可过（message-log 实锤多终端共用 ABCDEF1234）
- code=1 三种含义：未登录 / 同终端会话冲突 / 编码拒收；会话冲突自动断开重试
- HTTP code:0 ≠ 群聊建成（异步UDP）；建群验证靠监控平台 item/page 轮询
- 登录走 cookie（POST /api/login，无验证码）；401 自动重登一次

模板定稿原则：样例报文即模板，唯一变量是 terminalId，其余字段一律照抄。
"""
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from common.requests_util import BaseRequest

# ==================== 定稿模板常量（2026-08-14 主人提供样例，勿改） ====================
RESCUE_PLATFORM_URL = "http://120.77.17.225:10304"
DEFAULT_HARDWARE_ID = "ABCDEF1234"
DEFAULT_SERVER_HOST = "120.77.17.225"
DEFAULT_SERVER_PORT = 10306
DEFAULT_TRANSPORT = "udp"
DEFAULT_LNG = 113.461605
DEFAULT_LAT = 23.171917
DEFAULT_ALTITUDE = 50
BIZ_ID_POSITION = 2
BIZ_ID_SPEECH = 3
DEFAULT_CODE_RATE = 2

# 语音上行定稿样本（462字节，2026-08-14 主人提供，多帧压缩码流）
DEFAULT_SPEECH_HEX: str = "dfe550345caa2fc890345caa37c010345caa004df0345caa004010345caa37c890345caa3c4df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa004010345caa004df0345caa004010345caa37c890345caa37c010345caa004010345caa37c010345caa004df0345caa224df0345caa"


def generate_rescue_sn() -> str:
    """12位纯数字SN：月(1)+日(2)+时(2)+分(2)+秒(2)+盐(3)
    依据：2026-08-14 实验实锤 terminalId 上限 12 位，13位起被拒。
    盐 = 毫秒后3位，同一秒并发下唯一。"""
    import datetime
    now = datetime.datetime.now()
    salt = str(int(time.time() * 1000))[-3:]
    return f"{now.month:01d}{now.day:02d}{now.hour:02d}{now.minute:02d}{now.second:02d}{salt}"


@dataclass
class RescueSendResult:
    """上行发送结果（对齐 bd 系 ProtocolSendResult）"""
    code: int                      # 业务码（0=成功）
    message: str                   # 平台消息
    session_id: Optional[str]      # 会话ID（成功时）
    terminal_id: str
    status: str                    # connected / disconnected
    raw_response: Dict[str, Any] = field(default_factory=dict)
    request_body: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.code == 0 and self.session_id is not None


class RescuePlatformSession:
    """10304 cookie 会话管理（JSESSIONID）

    登录无验证码；401/未授权时自动重登一次。用例勿直接用，经 RescueUplinkClient 间接使用。
    """

    def __init__(self, username: str, password: str, base_url: str = RESCUE_PLATFORM_URL):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[requests.Session] = None

    def login(self) -> None:
        self._session = requests.Session()
        r = self._session.post(
            f"{self.base_url}/api/login",
            json={"username": self.username, "password": self.password},
            timeout=15,
        )
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"10304登录失败: {data}")

    def ensure_login(self) -> None:
        """确保已登录；未登录或失效则登录/重登"""
        if self._session is None:
            self.login()
            return
        try:
            r = self._session.get(f"{self.base_url}/api/check-auth", timeout=8)
            data = r.json()
            if data.get("code") != 0 or data.get("data") is not True:
                self.login()
        except Exception:
            self.login()

    @property
    def session(self) -> requests.Session:
        self.ensure_login()
        assert self._session is not None
        return self._session

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.session.post(f"{self.base_url}{path}", timeout=15, **kwargs)

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.session.get(f"{self.base_url}{path}", timeout=15, **kwargs)


class RescueUplinkClient:
    """10304 上行模拟造数门面 —— 用例层唯一入口

    封装 6 种报文（U0~U5），参数除 terminalId 外全部有定稿默认值。
    同终端会话冲突时自动断开后重试一次。
    """

    def __init__(self, session_mgr: RescuePlatformSession, http: Optional[BaseRequest] = None):
        self.mgr = session_mgr
        self.http = http or BaseRequest()
        self._active_sessions: Dict[str, str] = {}   # terminal_id -> session_id
        self._speech_hex = DEFAULT_SPEECH_HEX

    # ---------- 语音样本注入（conftest 启动时调用） ----------
    def set_speech_sample(self, speech_hex: str) -> None:
        """注入语音上行定稿样本（412B），供 send_speech 缺省使用"""
        self._speech_hex = speech_hex

    # ---------- 核心发送 ----------
    def _send(self, payload: Dict[str, Any], terminal_id: str) -> RescueSendResult:
        """发送上行报文；同终端会话冲突(code=1)时自动断开旧会话重试一次"""
        body = self._build_payload(payload)
        r = self.mgr.post("/admin/protocol/uplink-sim/send", json=body)
        data = self._parse(r)
        if data.get("code") == 1 and "已有活跃" in str(data.get("message", "")):
            # 会话冲突：断开该终端旧会话后重试
            self.disconnect_by_terminal(terminal_id)
            r = self.mgr.post("/admin/protocol/uplink-sim/send", json=body)
            data = self._parse(r)
        return self._to_result(data, body, terminal_id)

    def _build_payload(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """样例即模板：定稿字段全量铺底，overrides 覆盖业务字段"""
        body = {
            "terminalId": "",
            "hardwareId": DEFAULT_HARDWARE_ID,
            "serverHost": DEFAULT_SERVER_HOST,
            "serverPort": DEFAULT_SERVER_PORT,
            "transport": DEFAULT_TRANSPORT,
        }
        body.update(overrides)
        return body

    def _parse(self, r: requests.Response) -> Dict[str, Any]:
        try:
            return r.json()
        except Exception:
            return {"code": -1, "message": f"HTTP {r.status_code}", "raw": r.text[:200]}

    def _to_result(self, data: Dict[str, Any], body: Dict[str, Any], terminal_id: str) -> RescueSendResult:
        d = data.get("data") or {}
        sid = d.get("sessionId")
        if sid:
            self._active_sessions[terminal_id] = sid
        return RescueSendResult(
            code=int(data.get("code", -1)),
            message=str(data.get("message", "")),
            session_id=sid,
            terminal_id=terminal_id,
            status=str(d.get("status", "")),
            raw_response=data,
            request_body=body,
        )

    # ---------- U0 仅登录 ----------
    def login_terminal(self, terminal_id: str) -> RescueSendResult:
        """U0：仅登录建会话（5个基础字段，无业务字段）"""
        return self._send({"terminalId": terminal_id, "messageType": "login"}, terminal_id)

    # ---------- U1~U4 位置族 ----------
    def send_position(
        self,
        terminal_id: str,
        report_flag: int,
        *,
        lng: float = DEFAULT_LNG,
        lat: float = DEFAULT_LAT,
        altitude: int = DEFAULT_ALTITUDE,
        speed: int = 0,
        direction: int = 0,
    ) -> RescueSendResult:
        """U1~U4：位置上报。reportFlag=0心跳/1按键SOS/2落水/10取消SOS"""
        return self._send({
            "terminalId": terminal_id,
            "messageType": "position",
            "reportFlag": report_flag,
            "longitude": lng,
            "latitude": lat,
            "altitude": altitude,
            "speed": speed,
            "direction": direction,
            "terminalBusinessId": BIZ_ID_POSITION,
        }, terminal_id)

    def send_sos(self, terminal_id: str, *, kind: int = 1) -> RescueSendResult:
        """SOS 快捷方法：kind=1 按键SOS / 2 落水SOS（建群主入口）"""
        return self.send_position(terminal_id, report_flag=kind)

    def send_cancel_sos(self, terminal_id: str) -> RescueSendResult:
        """U4：取消SOS（reportFlag=10）——状态机场景"""
        return self.send_position(terminal_id, report_flag=10)

    # ---------- U5 语音族 ----------
    def send_speech(
        self,
        terminal_id: str,
        *,
        speech_hex: Optional[str] = None,
        code_rate: int = DEFAULT_CODE_RATE,
    ) -> RescueSendResult:
        """U5：语音上行。speech_hex 缺省用定稿样本（需先 set_speech_sample）"""
        hex_data = speech_hex or self._speech_hex
        if not hex_data:
            raise RuntimeError("语音样本未注入：conftest 需调 rescue_client.set_speech_sample()")
        return self._send({
            "terminalId": terminal_id,
            "messageType": "speech",
            "codeRate": code_rate,
            "speechHex": hex_data,
            "terminalBusinessId": BIZ_ID_SPEECH,
        }, terminal_id)

    def encode_speech(self, pcm_hex: str, rate_name: str = "R1200") -> Dict[str, Any]:
        """PCM→压缩HEX（造新语音时用；代理调用压缩库）"""
        r = self.mgr.post("/admin/protocol/uplink-sim/speech-encode",
                          json={"pcmHex": pcm_hex, "rateName": rate_name})
        return self._parse(r)

    # ---------- 会话管理 ----------
    def sessions(self) -> List[Dict[str, Any]]:
        """当前所有活跃模拟会话"""
        r = self.mgr.get("/admin/protocol/uplink-sim/sessions")
        data = self._parse(r)
        return data.get("data") or []

    def disconnect(self, session_id: str) -> bool:
        """断开指定会话"""
        r = self.mgr.post(f"/admin/protocol/uplink-sim/disconnect?sessionId={session_id}")
        return self._parse(r).get("code") == 0

    def disconnect_by_terminal(self, terminal_id: str) -> int:
        """断开某终端的所有活跃会话，返回断开数量"""
        count = 0
        for sess in self.sessions():
            if sess.get("terminalId") == terminal_id:
                if self.disconnect(sess.get("sessionId")):
                    count += 1
        self._active_sessions.pop(terminal_id, None)
        return count

    def disconnect_all(self) -> int:
        """断开所有活跃会话（session 末清理用）"""
        count = 0
        for sess in self.sessions():
            if self.disconnect(sess.get("sessionId")):
                count += 1
        self._active_sessions.clear()
        return count

    # ---------- 归因查询（造数失败排查用） ----------
    def session_records(self, terminal_id: Optional[str] = None, page_size: int = 10) -> List[Dict[str, Any]]:
        """会话记录（登录帧终态：login_success / disconnected）"""
        r = self.mgr.get(f"/admin/protocol/session-record/page?pageNum=1&pageSize={page_size}")
        items = (self._parse(r).get("data") or {}).get("items") or []
        if terminal_id:
            items = [i for i in items if i.get("terminalId") == terminal_id]
        return items

    def uplink_fail_logs(self, page_size: int = 10) -> List[Dict[str, Any]]:
        """上行校验失败报文（报文到协议层但格式被拒的记录）"""
        r = self.mgr.get(f"/admin/protocol/uplink-check-fail-log/page?pageNum=1&pageSize={page_size}")
        return (self._parse(r).get("data") or {}).get("items") or []

    def message_logs(self, terminal_id: Optional[str] = None, page_size: int = 10) -> List[Dict[str, Any]]:
        """消息记录（登录帧/位置帧原文与解析结果）"""
        r = self.mgr.get(f"/admin/protocol/message-log/page?pageNum=1&pageSize={page_size}")
        items = (self._parse(r).get("data") or {}).get("items") or []
        if terminal_id:
            items = [i for i in items if i.get("terminalId") == terminal_id]
        return items
