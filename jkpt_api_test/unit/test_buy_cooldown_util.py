# unit/test_buy_cooldown_util.py — 进程内 buy 限频钟（不进 testpaths）
import pytest

from common import buy_cooldown_util as cooldown


@pytest.fixture(autouse=True)
def _reset_clock():
    cooldown.reset_buy_cooldown()
    yield
    cooldown.reset_buy_cooldown()


def test_first_wait_does_not_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(cooldown.time, "sleep", lambda s: slept.append(s))
    cooldown.wait_buy_cooldown()
    assert slept == []


def test_wait_after_mark_sleeps_remainder(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(cooldown.time, "time", lambda: clock["t"])
    slept = []
    monkeypatch.setattr(cooldown.time, "sleep", lambda s: slept.append(s))
    cooldown.mark_bought()
    clock["t"] = 1020.0
    cooldown.wait_buy_cooldown()
    assert slept == [pytest.approx(45.0)]


def test_wait_after_full_window_does_not_sleep(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(cooldown.time, "time", lambda: clock["t"])
    slept = []
    monkeypatch.setattr(cooldown.time, "sleep", lambda s: slept.append(s))
    cooldown.mark_bought()
    clock["t"] = 1000.0 + cooldown.BUY_COOLDOWN_SECONDS
    cooldown.wait_buy_cooldown()
    assert slept == []
