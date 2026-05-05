# testcases/test_bd_protocol_client.py
"""BD 协议客户端测试用例

使用方式（傻瓜调用，所有变量内部自动计算）：

    def test_xxx(bd_client, bd_test_terminal, base_url):
        result = bd_client.send_text_93(from_addr=bd_test_terminal)
        assert result.success

    # 也可以指定坐标
    def test_yyy(bd_client, bd_test_terminal, base_url):
        result = bd_client.send_alarm_13(
            from_addr=bd_test_terminal,
            lon=113.50,
            lat=23.20,
        )
        assert result.success
"""
import copy
import json

from common.logger_util import print_request, sep
from common.protocol_types import ProtocolSendResult


def _bd_api_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/datas/bd"


def _shrink_request_body_for_log(body: dict, content_max: int = 200) -> dict:
    """commInfos[].content HEX 过长时截断，避免控制台刷屏。"""
    out = copy.deepcopy(body)
    for item in out.get("commInfos") or []:
        c = item.get("content")
        if isinstance(c, str) and len(c) > content_max:
            item["content"] = f"{c[:content_max]}...<截断 len={len(c)}>"
    return out


def _print_protocol_send_result(case_name: str, base_url: str, result: ProtocolSendResult) -> None:
    """与 REST 用例一致的 sep + print_request + 响应摘要（对象为 ProtocolSendResult）。"""
    sep(f" 测试用例: {case_name}")
    display_body = _shrink_request_body_for_log(result.request_body)
    print_request("POST", _bd_api_url(base_url), json=display_body)
    print(f"\n  📥 Status: {result.status_code}")
    if result.raw_response:
        print("  📦 Response:")
        print(f"     {json.dumps(result.raw_response, indent=6, ensure_ascii=False)}")
    else:
        print(f"     code/msg: {result.code} / {result.msg}")


class TestBDProtocolClient:
    """11 种 BD 协议接口集成测试，依赖 bd_client + bd_test_terminal fixture"""

    # ---------- 92：短文本（无位置） ----------
    # def test_send_text_92(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-92短文本无位置"
    #     result = bd_client.send_text_92(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success, f"92 协议失败：code={result.code}, msg={result.msg}"

    # ---------- 93：短文本（有位置） ----------
    # def test_send_text_93(self, bd_client, bd_test_terminal, base_url):
    #     """最简调用：坐标自动从中心点(113.47, 23.17)半径100m内随机生成"""
    #     case_name = "协议-93短文本有位置"
    #     result = bd_client.send_text_93(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success, f"93 协议失败：code={result.code}, msg={result.msg}"

    # def test_send_text_93_with_custom_coord(self, bd_client, bd_test_terminal, base_url):
    #     """指定坐标"""
    #     case_name = "协议-93短文本-指定坐标"
    #     result = bd_client.send_text_93(
    #         from_addr=bd_test_terminal,
    #         lon=113.50,
    #         lat=23.20,
    #         case_name=case_name,
    #     )
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # ---------- A6：神经语音（固定 HEX） ----------
    # def test_send_voice_a6(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-A6神经语音"
    #     result = bd_client.send_voice_a6(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # # ---------- 13：EE 推送报警（有定位） ----------
    # def test_send_alarm_13(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-13报警"
    #     result = bd_client.send_alarm_13(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    def test_send_alarm_13_with_custom(self, bd_client, bd_test_terminal, base_url):
        case_name = "协议-13报警-指定坐标与手机"
        result = bd_client.send_alarm_13(
            from_addr=bd_test_terminal,
            phone="13250703582",
            case_name=case_name
        )
        _print_protocol_send_result(case_name, base_url, result)
        assert result.success

    # ---------- 14：报平安（有定位） ----------
    def test_send_safe_14(self, bd_client, bd_test_terminal, base_url):
        case_name = "协议-14报平安"
        result = bd_client.send_safe_14(from_addr=bd_test_terminal, case_name=case_name)
        _print_protocol_send_result(case_name, base_url, result)
        assert result.success

    # ---------- A4：定位轨迹（5 点 DMS） ----------
    # def test_send_location_a4(self, bd_client, bd_test_terminal, base_url):
    #     """5点轨迹自动生成"""
    #     case_name = "协议-A4定位轨迹"
    #     result = bd_client.send_location_a4(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # def test_send_location_a4_with_custom_points(self, bd_client, bd_test_terminal, base_url):
    #     """指定5个轨迹点"""
    #     case_name = "协议-A4定位轨迹-指定5点"
    #     custom_points = [(113.46 + i * 0.01, 23.17 + i * 0.01) for i in range(5)]
    #     result = bd_client.send_location_a4(
    #         from_addr=bd_test_terminal,
    #         points=custom_points,
    #         case_name=case_name,
    #     )
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # # ---------- AA：图片（7 次 POST：第 1 包重复 + 2～6）----------
    # def test_send_image_aa(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-AA图片"
    #     results = bd_client.send_image_aa(from_addr=bd_test_terminal, case_name=case_name)
    #     assert len(results) == 7, "AA 协议应发送 7 个分包（与 JMX 一致）"
    #     for i, r in enumerate(results, start=1):
    #         _print_protocol_send_result(f"{case_name}-分包{i}", base_url, r)
    #         assert r.success, f"AA 第 {i} 包失败：{r.msg}"

    # # ---------- 15：多点定位（5 点 INT + 各点时间戳） ----------
    # def test_send_location_15(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-15多点定位"
    #     result = bd_client.send_location_15(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # # ---------- EE：报警（北京时间 + DMS） ----------
    # def test_send_alarm_ee(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-EE报警"
    #     result = bd_client.send_alarm_ee(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success

    # # ---------- E1：报平安（北京时间 + DMS） ----------
    # def test_send_safe_e1(self, bd_client, bd_test_terminal, base_url):
    #     case_name = "协议-E1报平安"
    #     result = bd_client.send_safe_e1(from_addr=bd_test_terminal, case_name=case_name)
    #     _print_protocol_send_result(case_name, base_url, result)
    #     assert result.success


