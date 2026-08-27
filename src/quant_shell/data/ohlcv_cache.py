"""日 K 缓存 — 进程内 + 按日磁盘；收盘后若缺完整交易日则失效。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quant_shell.common.atomic_io import write_pickle_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.data.disk_cache import CACHE_ROOT
from quant_shell.data.market_session import (
    is_after_a_share_close,
    last_completed_a_share_session,
)

logger = get_logger(__name__)

_OHLCV_CACHE: dict[str, pd.DataFrame] = {}
_OHLCV_LAST_BAR: dict[str, date] = {}
# 本进程已接受的实拉结果（含会话滞后）：后续层走内存，不把未盖住今日的盘当命中。
_OHLCV_LIVE_PIN: set[str] = set()
# 本进程收盘后日 K 滞后命中（联动结束汇总为硬错误，禁止假成功）
_OHLCV_SESSION_LAG_HITS: list[str] = []
_DISK_DIR = CACHE_ROOT / "ohlcv"


def _today() -> date:
    return date.today()


def is_ohlcv_session_lag(last_bar: date | None) -> bool:
    """收盘后最新 K 仍早于应完成交易日。"""
    if last_bar is None:
        return False
    expected = last_completed_a_share_session()
    return last_bar < expected and is_after_a_share_close()


def invalidate_ohlcv(symbol: str) -> None:
    """丢弃内存与当日磁盘缓存（短序列 / 损坏不得继续当数据）。"""
    _OHLCV_CACHE.pop(symbol, None)
    _OHLCV_LAST_BAR.pop(symbol, None)
    _OHLCV_LIVE_PIN.discard(symbol)
    path = _DISK_DIR / f"{symbol}.pkl"
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("ohlcv cache unlink fail symbol=%s err=%s", symbol, exc)


def get_cached_ohlcv(symbol: str, *, min_bars: int = 0) -> pd.DataFrame | None:
    expected = last_completed_a_share_session()
    mem = _OHLCV_CACHE.get(symbol)
    if mem is not None:
        last = _OHLCV_LAST_BAR.get(symbol)
        if _cache_covers_session(last, expected) or symbol in _OHLCV_LIVE_PIN:
            return _accept_cached_frame(symbol, mem, min_bars=min_bars)
        _OHLCV_CACHE.pop(symbol, None)
        _OHLCV_LAST_BAR.pop(symbol, None)

    disk = _load_ohlcv_disk(_DISK_DIR / f"{symbol}.pkl", expected)
    if disk is not None:
        frame, last_bar = disk
        _OHLCV_CACHE[symbol] = frame
        if last_bar is not None:
            _OHLCV_LAST_BAR[symbol] = last_bar
        return _accept_cached_frame(symbol, frame, min_bars=min_bars)
    return None


def _accept_cached_frame(
    symbol: str, frame: pd.DataFrame, *, min_bars: int
) -> pd.DataFrame | None:
    if min_bars > 0 and len(frame) < min_bars:
        logger.warning(
            "ohlcv cache too short symbol=%s bars=%d need=%d",
            symbol,
            len(frame),
            min_bars,
        )
        invalidate_ohlcv(symbol)
        return None
    return frame.copy()


def store_ohlcv(
    symbol: str,
    frame: pd.DataFrame,
    *,
    last_bar_date: date | None = None,
    pin_process: bool = False,
) -> None:
    resolved = last_bar_date or _infer_last_bar_date(frame)
    _OHLCV_CACHE[symbol] = frame.copy()
    if resolved is not None:
        _OHLCV_LAST_BAR[symbol] = resolved
    else:
        _OHLCV_LAST_BAR.pop(symbol, None)
    if pin_process:
        _OHLCV_LIVE_PIN.add(symbol)
    expected = last_completed_a_share_session()
    if _cache_covers_session(resolved, expected):
        _save_ohlcv_disk(_DISK_DIR / f"{symbol}.pkl", frame, resolved)
    elif pin_process:
        logger.warning(
            "ohlcv pin in-process lag symbol=%s last_bar=%s expected=%s",
            symbol,
            resolved,
            expected,
        )


def clear_ohlcv_cache() -> None:
    """清空内存缓存（测试用；不删磁盘）。"""
    _OHLCV_CACHE.clear()
    _OHLCV_LAST_BAR.clear()
    _OHLCV_LIVE_PIN.clear()
    _OHLCV_SESSION_LAG_HITS.clear()


def note_ohlcv_session_lag(symbol: str) -> None:
    """记录收盘后日 K 滞后（钉住继续用，联动结束再硬失败）。"""
    sym = str(symbol).strip()
    if sym and sym not in _OHLCV_SESSION_LAG_HITS:
        _OHLCV_SESSION_LAG_HITS.append(sym)


def consume_ohlcv_session_lag_hits() -> list[str]:
    """取出并清空本进程会话滞后清单。"""
    hits = list(_OHLCV_SESSION_LAG_HITS)
    _OHLCV_SESSION_LAG_HITS.clear()
    return hits


def _disk_path(symbol: str) -> Path:
    """测试用路径辅助。"""
    return _DISK_DIR / f"{symbol}.pkl"


def _cache_covers_session(last_bar: date | None, expected: date) -> bool:
    """缓存是否已覆盖应完成的交易日。"""
    if last_bar is not None:
        return last_bar >= expected
    # 旧缓存无 last_bar：收盘后视为过期，强制重拉一次写入新元数据。
    if is_after_a_share_close():
        return False
    return True


def _infer_last_bar_date(frame: pd.DataFrame) -> date | None:
    if "trade_date" not in frame.columns or frame.empty:
        return None
    raw = frame["trade_date"].iloc[-1]
    ts = pd.to_datetime(raw, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def _load_ohlcv_disk(
    path: Path, expected: date
) -> tuple[pd.DataFrame, date | None] | None:
    if not path.exists():
        return None
    try:
        payload = pd.read_pickle(path)
    except (
        OSError,
        ValueError,
        EOFError,
        ModuleNotFoundError,
        ImportError,
        AttributeError,
    ) as exc:
        logger.warning("ohlcv disk load fail path=%s err=%s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("day") != _today().isoformat():
        return None
    frame = payload.get("frame")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    last_bar = _parse_bar_date(payload.get("last_bar_date"))
    if not _cache_covers_session(last_bar, expected):
        logger.info(
            "ohlcv cache stale symbol=%s last_bar=%s expected=%s",
            path.stem,
            last_bar,
            expected,
        )
        return None
    return frame, last_bar


def _save_ohlcv_disk(
    path: Path, frame: pd.DataFrame, last_bar_date: date | None
) -> None:
    try:
        write_pickle_atomic(
            path,
            {
                "day": _today().isoformat(),
                "last_bar_date": (
                    last_bar_date.isoformat() if last_bar_date is not None else None
                ),
                "frame": frame.copy(),
            },
        )
    except OSError as exc:
        logger.warning("ohlcv disk save fail path=%s err=%s", path, exc)


def _parse_bar_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
