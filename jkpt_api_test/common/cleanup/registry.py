# common/cleanup/registry.py
# L0 清理调度器：谁造数谁注册 + tier 分层 + 失败隔离。
# 纪律（迁移自四轮架构评审）：
#   1. 副作用落地即注册——入库成功就 register，不等 fixture 走完（堵半途失败泄漏）。
#   2. tier 语义：100 会话级业务对象(群/订单) / 200 设备 / 300 组织(分组) /
#      400+ 外部系统（与 jkpt 内部 100-300 无依赖关系，顺序不敏感；如需"定位/执行"
#      两阶段，执行阶段用 N+10，保证晚于同组所有定位阶段，见 glht.py）。
#      新域挑层，不挑位置；同 tier 按注册序。
#   3. run_session_cleanup 结束后清空注册表——防跨 session（同进程多次 run）重复清理。
#   4. 本文件零项目依赖（仅标准库）：不 import pytest/requests/common.*，
#      HTTP 客户端与日志由 ctx / cleaner 自备——保证可整体复制到其他项目（skill 模板源身）。
#   5. CleanupContext.token 时效依赖声明：jkpt JWT TTL 实测约 83 天（2026-08-18 探针），
#      session 内不过期，故不做清理前重登；若后端收紧 JWT 策略，需补重登。
#   6. 新增域先套 references/cleanup-framework.md 的 2×2 矩阵选模板，
#      不要现场发明第三种登记方式。
import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class CleanupContext:
    """清理上下文：由 conftest 壳构造，逐域传给 cleaner。"""
    base_url: str
    auth_headers: Dict[str, str]
    extras: Dict[str, Any] = field(default_factory=dict)  # 域自有参数（如 keep_orders）


@dataclass
class _Entry:
    tier: int
    seq: int
    domain: str
    payload: Any
    cleaner: Callable[..., Any]


# 进程内注册表（有意为模块级单例：用例无需摸 pytestconfig 即可注册；
# xdist 下每 worker 一份，各清各的，与 fixture 语义一致）
_REGISTRY: list = []
_SEQ = itertools.count()


def register_cleanup(domain: str, payload: Any, cleaner: Callable[..., Any], *, tier: int = 500) -> None:
    """登记一个待清理副作用。

    Args:
        domain: 域名（唯一键仅用于报告展示；同域可多次注册，如多张订单）。
        payload: cleaner 需要的定位数据（sn / id 列表 / order_no…）。
        cleaner: callable(ctx, payload, **flags) -> str（统计摘要）。
        tier: 分层见模块 docstring 纪律 2。
    """
    _REGISTRY.append(_Entry(tier=tier, seq=next(_SEQ), domain=domain,
                            payload=payload, cleaner=cleaner))


def register_cleanup_once(domain: str, payload: Any, cleaner: Callable[..., Any], *, tier: int = 500) -> None:
    """登记一个待清理副作用；若同名 domain 已登记则跳过（防重复挂载）。

    用于「动态·逐项 domain」模板：domain 名内嵌实例标识（如 f"unpaid_order_{no}"）。
    这里的去重是防御性的（同一实例被 register 两次时只挂一条），
    不要拿它去实现「共享 domain + 累积列表」模板——那种场景应由域模块自己维护
    模块级列表 + 首次登记才调用本函数（domain 名固定不变），而不是每次都传新 domain。

    Args: 同 register_cleanup。
    """
    if any(d == domain for _, d in registered_domains()):
        return
    register_cleanup(domain, payload, cleaner, tier=tier)


def unregister_cleanup(domain: str) -> None:
    """按 domain 精确名移除已登记条目（用例内消费完成时调用，防 session 末重复收尾）。

    仅服务于「动态·逐项 domain」模板的可选注销语义；
    「共享 domain + 模块内累积列表」模板不需要它——那种场景的"注销"是域模块自己
    从内部列表里 remove 一项，压根不动 registry。
    """
    _REGISTRY[:] = [e for e in _REGISTRY if e.domain != domain]


def run_session_cleanup(ctx: CleanupContext, **flags) -> Dict[str, Any]:
    """session 末尾调度：tier 升序执行，逐域失败隔离，末尾清空注册表。

    Returns:
        report: {domain: 摘要或 "FAILED: …"}，供壳层 allure attach / 落盘。
    """
    report: Dict[str, Any] = {}
    try:
        ordered = sorted(_REGISTRY, key=lambda e: (e.tier, e.seq))
        for entry in ordered:
            try:
                outcome = entry.cleaner(ctx, entry.payload, **flags)
                report[entry.domain] = outcome if outcome is not None else "ok"
            except Exception as exc:  # 失败隔离：单域崩不阻断后续域
                report[entry.domain] = f"FAILED: {exc}"
        return report
    finally:
        _REGISTRY.clear()  # 纪律 3：跑完即清空


def registered_domains() -> list:
    """当前已注册条目快照（诊断用）：[(tier, domain), …]"""
    return [(e.tier, e.domain) for e in _REGISTRY]


def reset_registry() -> None:
    """显式清空（单测 / 手动场景；run_session_cleanup 已自动清）。"""
    _REGISTRY.clear()
