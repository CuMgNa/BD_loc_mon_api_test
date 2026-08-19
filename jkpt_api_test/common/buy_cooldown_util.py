# common/buy_cooldown_util.py
# 同一测试账号连续 buy（套餐/星豆/订单 lifecycle）会 999「下单过于频繁」。
# 进程内共享钟：谁 buy 谁 mark，下一处 wait。窗口来自现网实测约 65s。

import time

from common.logger_util import key

BUY_COOLDOWN_SECONDS = 65
_last_buy_time = 0.0


def reset_buy_cooldown():
    """单测 / 手动复位。"""
    global _last_buy_time
    _last_buy_time = 0.0


def mark_bought():
    """一次 buy 请求已发出（成功、失败、999 都算）。"""
    global _last_buy_time
    _last_buy_time = time.time()


def wait_buy_cooldown():
    """距上次 mark 不足窗口则阻塞到窗口结束。从未 mark 则立即返回。"""
    if not _last_buy_time:
        return
    elapsed = time.time() - _last_buy_time
    if elapsed < BUY_COOLDOWN_SECONDS:
        wait = BUY_COOLDOWN_SECONDS - elapsed
        key("buy 限频冷却", f"{wait:.0f}s")
        time.sleep(wait)
