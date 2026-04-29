# common/ipconfig.py
import socket


def get_local_ips() -> list:
    """
    获取本机IP地址列表

    Returns:
        排除127.x.x.x后的IP列表，默认取第一个
    """
    ips = []
    try:
        # 获取主机名
        hostname = socket.gethostname()
        # 获取所有IP（包含IPv4和IPv6）
        addr_info = socket.getaddrinfo(hostname, None)

        for info in addr_info:
            ip = info[4][0]
            # 排除本地回环地址
            if not ip.startswith('127.'):
                ips.append(ip)

        # 去重
        ips = list(set(ips))

    except Exception:
        pass

    # 如果没有找到，返回默认值
    if not ips:
        ips = ['127.0.0.1']

    return ips