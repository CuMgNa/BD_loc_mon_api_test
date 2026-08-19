# common/cleanup/unpaid_order.py
# tier 100：收 session 登记的待支付订单（cancel → delete，逐单失败不抛）。
# 对外登记入口：common.cleanup.register_unpaid_order_no（即本模块 register，
# 由包 __init__ re-export；原 common/order_cleanup_util.py 已删除）。
# 模板：动态·逐项 domain（无批量接口，一单一 domain；与 intercom_group.py 同款，
# 详见 references/cleanup-framework.md 2×2 矩阵）。
from common.cleanup.registry import register_cleanup_once
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "unpaid_order"


def register(order_no) -> None:
    """登记待支付单（buy 成功后调用；落一个独立 domain，同号天然去重）。"""
    if order_no is None:
        return
    no = str(order_no).strip()
    if not no:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{no}", no, cleaner, tier=100)
    key("登记待支付订单", no)


def _try_order_action(method, url, order_no, auth_headers, case_name) -> bool:
    try:
        res = _http.send_request(
            method,
            url,
            params={"orderNo": order_no},
            headers=auth_headers,
            case_name=f"{case_name} {order_no}",
            log_level="none",
        )
        data = parse_response_json(res, context=case_name)
        code = data.get("code")
        msg = data.get("msg")
        if code == 0:
            key(case_name, f"{order_no} code=0")
            return True
        key(case_name, f"{order_no} code={code} msg={msg}")
        return False
    except Exception as exc:
        key(case_name, f"{order_no} 忽略: {exc}")
        return False


def cleaner(ctx, order_no, **flags) -> str:
    """registry 入口：payload = 单个 order_no（每单独立 domain，session 末逐单收尾）。

    flags.keep_orders=True 时跳过（未来扫码场景的参数位；
    当前主人拍板：订单默认收走，总闸 ENABLE_AUTO_CLEANUP=false 时整个调度不进来）。
    """
    if flags.get("keep_orders"):
        return "keep_orders=True，跳过收单"
    cancelled = _try_order_action(
        "post", f"{ctx.base_url}/api/monitor/order/cancel",
        order_no, ctx.auth_headers, "session收尾-取消订单",
    )
    deleted = _try_order_action(
        "delete", f"{ctx.base_url}/api/monitor/order/delete",
        order_no, ctx.auth_headers, "session收尾-删除订单",
    )
    key("待支付订单收尾", f"{order_no} cancel={cancelled}, delete={deleted}")
    return f"cancel={cancelled}, delete={deleted}"
