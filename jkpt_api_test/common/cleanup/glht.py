# common/cleanup/glht.py
# tier 400/410（外部系统，与 jkpt 内部 tier 100/200/300 无依赖关系，顺序不敏感）：
# glht 管理员系统入库记录清理。模板 D（逐项登记 + 集中批量收尾，详见
# references/cleanup-framework.md）：cleaner 只按 sn 精确定位 id，不立即删；
# flush_cleaner 统一批量 DELETE，避免 N 次入库对应 N 次删除请求。
# 完全自包含：自读 GLHT_* 环境变量，登录态惰性缓存于进程内，不依赖任何
# conftest fixture（对齐 unpaid_order.py/intercom_group.py 的自包含形状）。
#
# 跨 session 语义（R1，显式声明）：ENABLE_AUTO_CLEANUP=false 时 conftest 的
# cleanup_test_data 直接 return，run_session_cleanup 不执行，因此 _REGISTRY
# （registry 纪律 3 只在 run_session_cleanup 的 finally 里清空）与本模块的
# _pending_ids 都不会被清理。登记会在进程内累积；同进程若随后跑一个开着总闸的
# session，上一轮的登记会被一并收走（补删，非泄漏）。单进程单 session 的常规
# 跑法下进程退出即释放，无实际影响。
import hashlib
import os

from common.cleanup.registry import register_cleanup_once
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "glht_inventory"
_FLUSH_DOMAIN = "glht_inventory_flush"

GLHT_BASE_URL = os.getenv("GLHT_BASE_URL", "http://back.tdwt.admin.pg8.ink")
GLHT_ACCOUNT = os.getenv("GLHT_ACCOUNT", "admin")
GLHT_PASSWORD = os.getenv("GLHT_PASSWORD", "123abc!!")
ENABLE_GLHT_CLEANUP = os.getenv("ENABLE_GLHT_CLEANUP", "true").lower() == "true"

_pending_ids: list = []          # tier400 各 cleaner 只追加，tier410 flush 统一清空+批删
_token_cache = {"token": None}   # 进程内惰性缓存，避免每个 sn 各登录一次


def register(sn) -> None:
    """入库成功后登记（副作用落地即注册，纪律 1）；同 sn 天然去重。"""
    if sn is None:
        return
    s = str(sn).strip()
    if not s:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{s}", s, cleaner, tier=400)
    register_cleanup_once(_FLUSH_DOMAIN, None, flush_cleaner, tier=410)
    key("登记glht入库", s)


def _login() -> str:
    if _token_cache["token"]:
        return _token_cache["token"]
    pwd_md5 = hashlib.md5(GLHT_PASSWORD.encode()).hexdigest()
    resp = _http.send_request(
        method="post", url=f"{GLHT_BASE_URL}/api/admin/login",
        json={"account": GLHT_ACCOUNT, "password": pwd_md5},
        case_name="glht管理员登录", log_level="none",
    )
    data = parse_response_json(resp, context="glht管理员登录")
    if data.get("code") != 0:
        raise RuntimeError(f"glht 登录失败: code={data.get('code')}, msg={data.get('msg')}")
    token = data.get("data", {}).get("token")
    _token_cache["token"] = token
    key("glht token", f"{token[:20]}...")
    return token


def cleaner(ctx, sn, **flags) -> str:
    """registry 入口（tier400）：按 sn 精确查询定位 id，只登记待删，不在此处删除。"""
    if not ENABLE_GLHT_CLEANUP:
        return "跳过(ENABLE_GLHT_CLEANUP=false)"
    try:
        token = _login()
    except Exception as exc:
        return f"FAILED: {exc}"
    resp = _http.send_request(
        method="get", url=f"{GLHT_BASE_URL}/api/admin/inventory",
        params={
            "Authorization": token, "content": sn, "index": 0,
            "specifyTime": "false", "startTimeStr": "", "endTimeStr": "",
            # pageSize 与旧实现口径一致取 100：同 sn 正常只有 1 条，
            # 但历史存量里可能有同 sn 重复入库，取小了会漏定位（R2）
            "page": 1, "pageSize": 100,
        },
        case_name=f"glht查询入库记录 {sn}", log_level="none",
    )
    data = parse_response_json(resp, context="glht查询入库记录")
    if data.get("code") != 0:
        return f"FAILED: 查询 code={data.get('code')}"
    items = data.get("data", {}).get("items") or []
    # content 是模糊子串匹配，这里做一次精确 sn 比对防误命中（防御性）
    matched = [it["id"] for it in items if str(it.get("sn")) == sn and it.get("id")]
    if not matched:
        return "未找到(可能已被其它路径清过)"
    _pending_ids.extend(matched)
    return f"已定位 {len(matched)} 条，待批量删除"


def flush_cleaner(ctx, _payload, **flags) -> str:
    """registry 入口（tier410，全局唯一，晚于所有 glht_inventory_<sn>）：批量执行删除。"""
    if not ENABLE_GLHT_CLEANUP:
        _pending_ids.clear()
        return "跳过(ENABLE_GLHT_CLEANUP=false)"
    if not _pending_ids:
        return "无需删除"
    try:
        token = _login()
    except Exception as exc:
        return f"FAILED: {exc}"
    ids = list(dict.fromkeys(_pending_ids))  # 去重保序
    _pending_ids.clear()
    deleted_total = 0
    # 分块 100 沿用旧实现口径（旧版按 pageSize=100 取回后整批删，线上跑过）；
    # DELETE 接口真实单次上限未验证，故保守分块而非一次性全量拼接（R5）
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        resp = _http.send_request(
            method="delete", url=f"{GLHT_BASE_URL}/api/admin/inventory",
            params={"Authorization": token}, json={"ids": ",".join(chunk)},
            case_name="glht批量删除入库记录", log_level="none",
        )
        data = parse_response_json(resp, context="glht删除入库记录")
        if data.get("code") == 0:
            deleted_total += len(chunk)
        else:
            key("glht删除失败", f"code={data.get('code')}, msg={data.get('msg')}")
    return f"删除 {deleted_total}/{len(ids)} 条"
