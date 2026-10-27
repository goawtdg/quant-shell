"""L1 磁盘缓存 — TTL / 按日 pickle，以及可回放的 JSON 样本。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_shell.common.atomic_io import write_pickle_atomic, write_text_atomic
from quant_shell.common.logging_config import get_logger

logger = get_logger(__name__)

CACHE_ROOT = Path("data/cache")


def load_frame_ttl(
    path: Path,
    ttl_sec: float,
    *,
    allow_stale: bool = False,
) -> pd.DataFrame | None:
    """读取 ``{ts, frame}``。过期默认作废；``allow_stale`` 时仍返回上一份成功样本。"""
    if not path.exists():
        return None
    try:
        payload = pd.read_pickle(path)
    except (OSError, ValueError, EOFError, ModuleNotFoundError, ImportError, AttributeError) as exc:
        logger.warning("disk_cache ttl load fail path=%s err=%s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    ts = float(payload.get("ts", 0))
    if ttl_sec > 0 and time.time() - ts > ttl_sec and not allow_stale:
        return None
    frame = payload.get("frame")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    return frame


def save_frame_ttl(path: Path, frame: pd.DataFrame) -> None:
    try:
        write_pickle_atomic(path, {"ts": time.time(), "frame": frame.copy()})
    except OSError as exc:
        logger.warning("disk_cache ttl save fail path=%s err=%s", path, exc)


def load_frame_day(path: Path) -> pd.DataFrame | None:
    """读取 ``{day, frame}``；仅当日有效。"""
    if not path.exists():
        return None
    try:
        payload = pd.read_pickle(path)
    except (OSError, ValueError, EOFError, ModuleNotFoundError, ImportError, AttributeError) as exc:
        logger.warning("disk_cache day load fail path=%s err=%s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("day") != date.today().isoformat():
        return None
    frame = payload.get("frame")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    return frame


def save_frame_day(path: Path, frame: pd.DataFrame) -> None:
    try:
        write_pickle_atomic(
            path,
            {"day": date.today().isoformat(), "frame": frame.copy()},
        )
    except OSError as exc:
        logger.warning("disk_cache day save fail path=%s err=%s", path, exc)


def load_any(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return pd.read_pickle(path)
    except (OSError, ValueError, EOFError) as exc:
        logger.warning("disk_cache load fail path=%s err=%s", path, exc)
        return None


def save_any(path: Path, obj: Any) -> None:
    try:
        write_pickle_atomic(path, obj)
    except OSError as exc:
        logger.warning("disk_cache save fail path=%s err=%s", path, exc)


def load_json_record(
    path: Path,
    ttl_sec: float,
    *,
    allow_stale: bool = False,
) -> Any | None:
    """读取 ``{ts, data}``。过期默认作废；``allow_stale`` 时回放上一份。"""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        logger.warning("disk_cache json load fail path=%s err=%s", path, exc)
        return None
    if not isinstance(payload, dict) or "data" not in payload:
        return None
    ts = float(payload.get("ts", 0) or 0)
    if ttl_sec > 0 and time.time() - ts > ttl_sec and not allow_stale:
        return None
    return payload.get("data")


def save_json_record(path: Path, data: Any) -> None:
    try:
        write_text_atomic(
            path,
            json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False),
        )
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("disk_cache json save fail path=%s err=%s", path, exc)
