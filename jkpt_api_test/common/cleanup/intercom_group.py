# common/cleanup/intercom_group.py
# tier 100：收 session 遗留的对讲群（close → delete）。
# 模板：动态·逐项 domain（无批量接口，一群一 domain；与 unpaid_order.py 同款，
# 详见 references/cleanup-framework.md 2×2 矩阵）。
# create 成功即 register；用例内 delete 成功后 unregister——
# session 末只兜底中断/失败透留的群，无双重收尾。
from common.cleanup.registry import register_cleanup_once, unregister_cleanup
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()
_DOMAIN_PREFIX = "intercom_group"


def register(group_id) -> None:
    """create 成功后登记（落一个独立 domain，同 id 天然去重）。"""
    if group_id is None:
        return
    gid = str(group_id).strip()
    if not gid:
        return
    register_cleanup_once(f"{_DOMAIN_PREFIX}_{gid}", gid, cleaner, tier=100)
    key("登记对讲群", gid)


def unregister(group_id) -> None:
    """用例内 delete 成功后注销（消费完成出网，防 session 末重复收尾）。"""
    if group_id is None:
        return
    gid = str(group_id).strip()
    if not gid:
        return
    unregister_cleanup(f"{_DOMAIN_PREFIX}_{gid}")


def _act(method, url, gid, auth_headers, case_name) -> bool:
    try:
        res = _http.send_request(
            method, url, params={"intercomGroupId": gid},
            headers=auth_headers, case_name=f"{case_name} {gid}", log_level="none",
        )
        data = parse_response_json(res, context=case_name)
        code = data.get("code")
        if code == 0:
            key(case_name, f"{gid} code=0")
            return True
        key(case_name, f"{gid} code={code} msg={data.get('msg')}")
        return False
    except Exception as exc:
        key(case_name, f"{gid} 忽略: {exc}")
        return False


def cleaner(ctx, group_id, **flags) -> str:
    """registry 入口：payload = 单个 group_id（每群独立 domain）。

    先 close（已关闭/不存在返回非 0 只记日志）再 delete。
    探针实证活跃群也能直接删，close 只是稳妥化步骤。
    """
    closed = _act("put", f"{ctx.base_url}/api/monitor/intercom/group/close",
                  group_id, ctx.auth_headers, "session收尾-关闭对讲群")
    deleted = _act("delete", f"{ctx.base_url}/api/monitor/intercom/group/delete",
                    group_id, ctx.auth_headers, "session收尾-删除对讲群")
    key("对讲群收尾", f"{group_id} close={closed}, delete={deleted}")
    return f"close={closed}, delete={deleted}"
