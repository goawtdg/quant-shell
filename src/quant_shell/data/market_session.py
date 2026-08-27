"""A 股交易时段辅助 — 用于日 K 收盘后刷新判定。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

# 日 K 一般在 15:00 后陆续可取；留 10 分钟缓冲，避免半成品 bar。
_A_SHARE_CLOSE_REFRESH = time(15, 10)
# 免费源（腾讯/东财/新浪）常晚于收盘才落当日 K；此前仅软降级，过点后硬失败。
_DEFAULT_OHLCV_LAG_HARD_AFTER = time(18, 30)


def is_after_a_share_close(now: datetime | None = None) -> bool:
    """当前是否已过 A 股收盘刷新点（工作日 15:10 后）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return True
    return (now.hour, now.minute) >= (
        _A_SHARE_CLOSE_REFRESH.hour,
        _A_SHARE_CLOSE_REFRESH.minute,
    )


def parse_hhmm(raw: str, default: time = _DEFAULT_OHLCV_LAG_HARD_AFTER) -> time:
    """解析 HH:MM；非法则回退默认。"""
    text = (raw or "").strip()
    if not text:
        return default
    try:
        hour_s, minute_s = text.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return default
        return time(hour, minute)
    except ValueError:
        return default


def is_ohlcv_session_lag_hard(
    now: datetime | None = None,
    *,
    hard_after: time | None = None,
) -> bool:
    """日 K 会话滞后是否已过宽限（应记硬错误）。

    工作日：15:10 起可检测滞后，但须晚于 hard_after 才硬失败。
    周末：相对上周五仍滞后则始终硬失败（当日 K 理应早已落地）。
    """
    now = now or datetime.now()
    if now.weekday() >= 5:
        return True
    deadline = hard_after or _ohlcv_lag_hard_after_from_settings()
    return (now.hour, now.minute) >= (deadline.hour, deadline.minute)


def _ohlcv_lag_hard_after_from_settings() -> time:
    try:
        from quant_shell.config.settings import settings

        return parse_hhmm(settings.ohlcv_lag_hard_after)
    except Exception:
        return _DEFAULT_OHLCV_LAG_HARD_AFTER


def last_completed_a_share_session(now: datetime | None = None) -> date:
    """最近一个应已收盘完成的 A 股交易日（忽略法定节假日，仅跳过周末）。"""
    now = now or datetime.now()
    if now.weekday() < 5 and is_after_a_share_close(now):
        session = now.date()
    else:
        session = now.date() - timedelta(days=1)
    while session.weekday() >= 5:
        session -= timedelta(days=1)
    return session
