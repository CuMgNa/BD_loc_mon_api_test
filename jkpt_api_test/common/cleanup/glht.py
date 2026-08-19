# common/cleanup/glht.py
# 独立闸（ENABLE_GLHT_CLEANUP，默认 false）：清理当日 glht 入库记录。
# 不走 registry tier 调度（自带 glht 登录态，非 jkpt auth_headers）——
# conftest 的 glht_cleanup_test_data 壳直调本模块（架构决策 C）。
# 原样搬迁自 conftest._glht_cleanup_inventory；日期口径顺带修复：
# 用 session 起始日（payload 传入）替代清理时取今天，堵跨午夜漏清。
from common.logger_util import key
from common.requests_util import BaseRequest, parse_response_json

_http = BaseRequest()


def _jp():
    global _jsonpath_parse
    if _jsonpath_parse is None:
        import jsonpath
        _jsonpath_parse = jsonpath.jsonpath
    return _jsonpath_parse

_jsonpath_parse = None


def cleanup_inventory(glht_token: str, glht_base_url: str, date_str: str) -> int:
    """循环查询并删除 glht 入库记录，返回总删除条数。

    使用 seen_ids 去重防止删除最终一致性延迟导致的重复计数。
    date_str：YYYYMMDD，由调用方传 session 起始日。
    """
    seen_ids: set = set()
    max_loops = 50
    for _ in range(max_loops):
        resp = _http.send_request(
            method="get",
            url=f"{glht_base_url}/api/admin/inventory",
            params={
                "Authorization": glht_token,
                "content": date_str,
                "index": 0,
                "specifyTime": "false",
                "startTimeStr": "",
                "endTimeStr": "",
                "page": 1,
                "pageSize": 100,
            },
            case_name=f"glht查询入库记录 {date_str}",
            log_level="none",
        )
        json_data = parse_response_json(resp, context="glht查询入库记录")
        code = _jp()(json_data, "$.code")[0]
        if code != 0:
            key("glht查询失败", f"code={code}")
            break

        ids_raw = _jp()(json_data, "$.data.items[*].id")
        if not ids_raw:
            if not seen_ids:
                key(f"glht {date_str}", "无入库记录")
            break

        new_ids = [str(i) for i in ids_raw if i and str(i) not in seen_ids]
        if not new_ids:
            break

        del_resp = _http.send_request(
            method="delete",
            url=f"{glht_base_url}/api/admin/inventory",
            params={"Authorization": glht_token},
            json={"ids": ",".join(new_ids)},
            case_name="glht批量删除入库记录",
            log_level="none",
        )
        del_json = parse_response_json(del_resp, context="glht删除入库记录")
        del_code = _jp()(del_json, "$.code")[0]
        if del_code != 0:
            msg_list = _jp()(del_json, "$.msg")
            del_msg = msg_list[0] if msg_list else "未知"
            key("glht删除失败", f"code={del_code}, msg={del_msg}")
            break

        seen_ids.update(new_ids)
        key(f"glht清理 {date_str}", f"本批删除 {len(new_ids)} 条")

    return len(seen_ids)
