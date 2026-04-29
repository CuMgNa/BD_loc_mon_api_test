# common/logger_util.py
# 公共日志格式化工具，提供美观的控制台输出格式


def sep(title=""):
    """
    打印分隔线

    Usage:
        sep()           # 打印一条分隔线
        sep("标题")     # 打印带标题的分隔线
    """
    if title:
        print(f"\n{'━'*50}")
        print(f"  {title}")
        print(f"{'━'*50}")
    else:
        print(f"{'━'*50}")


def key(key, value):
    """
    打印键值对

    Usage:
        key("名称", "值")
        key("base_url", "http://xxx.com")
    """
    print(f"  {key}: {value}")


def print_request(method, url, params=None, json=None, headers=None):
    """
    格式化打印请求信息

    Usage:
        print_request("POST", "http://xxx.com/api/login", params={"a": 1}, headers={"Token": "xxx"})
        print_request("PUT", "http://xxx.com/api/data", json={"id": 1}, headers={"Token": "xxx"})
    """
    print(f"\n  📤 {method} {url}")
    if params:
        print(f"  📋 Params:")
        for k, v in params.items():
            # 敏感字段脱敏
            if any(s in k.lower() for s in ['password', 'token', 'authorization', 'secret', 'key']):
                print(f"     {k}: ******")
            else:
                print(f"     {k}: {v}")
    if json:
        print(f"  📦 JSON:")
        for k, v in json.items():
            # 敏感字段脱敏
            if any(s in k.lower() for s in ['password', 'token', 'authorization', 'secret', 'key']):
                print(f"     {k}: ******")
            else:
                print(f"     {k}: {v}")
    if headers:
        print(f"  📑 Headers:")
        for k, v in headers.items():
            print(f"     {k}: {v}")


def print_response(response):
    """
    格式化打印响应信息

    Usage:
        print_response(response)  # response 是 requests.Response 对象
    """
    print(f"\n  📥 Status: {response.status_code}")
    try:
        import json
        json_data = response.json()
        print(f"  📦 Response:")
        print(f"     {json.dumps(json_data, indent=6, ensure_ascii=False)}")
    except:
        print(f"     {response.text[:500] if response.text else 'Empty'}")


def print_result(success=True, message=""):
    """
    打印结果信息

    Usage:
        print_result(True, "验证通过")
        print_result(False, "登录失败")
    """
    if success:
        print(f"\n  ✅ {message}")
    else:
        print(f"\n  ❌ {message}")