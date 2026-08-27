"""A 股行业 — 业绩报表查表 + 批量结束一次落盘。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from quant_shell.common.logging_config import get_logger
from quant_shell.data.stock_yjbb import lookup_yjbb_industry

logger = get_logger(__name__)

_UNKNOWN = "未知"
_CACHE_PATH = Path("data/cache/stock_industry.json")
_TTL_SEC = 7 * 24 * 3600

_lock = threading.Lock()
_memory: dict[str, dict[str, object]] = {}
_dirty = False
_loaded = False


def fetch_stock_industry(symbol: str) -> str:
    if not symbol or len(symbol) != 6:
        return _UNKNOWN
    industry = lookup_yjbb_industry(symbol)
    if industry:
        _remember(symbol, industry)
        return industry
    cached = _read(symbol)
    return cached or _UNKNOWN


def prefetch_industries(symbols: list[str]) -> dict[str, str]:
    out = {sym: fetch_stock_industry(sym) for sym in symbols}
    flush_industry_disk_cache()
    return out


def flush_industry_disk_cache() -> None:
    global _dirty
    with _lock:
        _ensure_loaded()
        if not _dirty:
            return
        payload = dict(_memory)
        _dirty = False
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("industry disk flush fail err=%s", exc)


def _remember(symbol: str, industry: str) -> None:
    global _dirty
    with _lock:
        _ensure_loaded()
        _memory[symbol] = {"industry": industry, "ts": time.time()}
        _dirty = True


def _read(symbol: str) -> str | None:
    with _lock:
        _ensure_loaded()
        entry = _memory.get(symbol)
    if not isinstance(entry, dict):
        return None
    if time.time() - float(entry.get("ts", 0)) > _TTL_SEC:
        return None
    value = str(entry.get("industry", "")).strip()
    return value or None


def _ensure_loaded() -> None:
    global _loaded, _memory
    if _loaded:
        return
    if _CACHE_PATH.exists():
        try:
            raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            _memory = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, OSError):
            _memory = {}
    else:
        _memory = {}
    _loaded = True
