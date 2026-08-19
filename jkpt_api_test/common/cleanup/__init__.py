# common/cleanup/__init__.py
# 数据清理子包：一域一文件 + L0 调度器。对外唯一导入面，内部文件名不外泄。
#
# 纪律（详见 registry.py docstring）：
#   - 只 `from common.cleanup import …`；用例勿直接调 cleaner（session 收尾专用）
#   - 谁造数谁注册：副作用落地即 register_cleanup
#   - 手动收数场景可独立 import 本包（无需起 pytest session）
#
# 域清单（tier 升序 = 清理顺序）：
#   100  rescue_chat    关求救群（含双路线降级）
#   100  unpaid_order   收待支付订单（cancel→delete）；登记入口 = register_unpaid_order_no
#   100  intercom_group 收对讲群（close→delete）；登记入口 = register_intercom_group
#   200  terminal       删设备（按分组聚合）
#   300  group          删三级分组（倒序）
#   独立  glht           独立闸直调（自带登录态，不走 tier 调度）
from common.cleanup.registry import (
    CleanupContext,
    register_cleanup,
    run_session_cleanup,
    registered_domains,
    reset_registry,
)
from common.cleanup import rescue_chat
from common.cleanup import terminal
from common.cleanup import group
from common.cleanup import unpaid_order
from common.cleanup import glht
from common.cleanup import intercom_group

# 订单登记包级入口：用例 buy 成功后调用（副作用落地即注册，tier 100）。
# 原 common/order_cleanup_util.py 兼容层已删，统一从本包导入。
register_unpaid_order_no = unpaid_order.register

# 对讲群登记包级入口：create 成功后调用；用例内 delete 成功后调 unregister。
register_intercom_group = intercom_group.register

__all__ = [
    "CleanupContext",
    "register_cleanup",
    "run_session_cleanup",
    "registered_domains",
    "reset_registry",
    "register_unpaid_order_no",
    "register_intercom_group",
    "rescue_chat",
    "terminal",
    "group",
    "unpaid_order",
    "glht",
    "intercom_group",
]
