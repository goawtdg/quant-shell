"""指数成分股候选池。"""
from __future__ import annotations

import json
import time
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.http_session import create_http_session
from quant_shell.common.logging_config import get_logger
from quant_shell.data.constants import (
    INDEX_CODE_MAP,
    NETWORK_HINT,
    REQUEST_TIMEOUT_SEC,
)
from quant_shell.data.disk_cache import CACHE_ROOT

logger = get_logger(__name__)

COL_SYMBOL_CANDIDATES: tuple[str, ...] = (
    "成分券代码",
    "品种代码",
    "stock_code",
    "code",
    "Constituent Code",
)

# 中证官网 OSS；akshare 同址但无 timeout，易在代理下挂死
_CSINDEX_CONS_URL = (
    "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
    "file/autofile/cons/{symbol}cons.xls"
)
_UNIVERSE_CACHE_TTL_SEC = 7 * 24 * 3600


def fetch_index_constituents(universe: str) -> list[str]:
    """拉取指数成分股代码列表。

    Args:
        universe: ``csi300`` 或 ``csi500``。

    Returns:
        6 位股票代码列表。
    """
    index_code = INDEX_CODE_MAP.get(universe)
    if index_code is None:
        raise ValidationError(
            message=f"未知 universe: {universe}",
            suggestion=f"可选: {list(INDEX_CODE_MAP.keys())}",
        )

    logger.info("fetch_index_constituents universe=%s code=%s", universe, index_code)
    cache_path = CACHE_ROOT / f"universe_{index_code}.json"
    local_xls = CACHE_ROOT / f"{index_code}cons.xls"

    # 新鲜磁盘缓存（7 日内）直接用，避免每次卡在中证 OSS
    cached_fresh = _load_universe_cache(cache_path, allow_stale=False)
    if cached_fresh:
        logger.info(
            "universe=%s count=%d source=cache_fresh", universe, len(cached_fresh)
        )
        return cached_fresh

    try:
        if local_xls.exists():
            symbols = _parse_csindex_xls(local_xls.read_bytes())
            if symbols:
                _save_universe_cache(cache_path, symbols)
                logger.info(
                    "universe=%s count=%d source=local_xls", universe, len(symbols)
                )
                return symbols
        symbols = _fetch_csindex_cons(index_code)
    except (
        DataFetchError,
        ValidationError,
        OSError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
    ) as exc:
        cached = _load_universe_cache(cache_path, allow_stale=True)
        if cached:
            logger.warning(
                "fetch_index_constituents fallback_cache universe=%s count=%d err=%s",
                universe,
                len(cached),
                exc,
            )
            return cached
        raise DataFetchError(
            message=f"指数 {universe} 成分股拉取失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc

    if not symbols:
        cached = _load_universe_cache(cache_path, allow_stale=True)
        if cached:
            logger.warning(
                "fetch_index_constituents empty_live fallback_cache universe=%s count=%d",
                universe,
                len(cached),
            )
            return cached
        raise DataFetchError(
            message=f"指数 {universe} 成分股为空",
            suggestion="检查中证 cons.xls 接口",
        )

    _save_universe_cache(cache_path, symbols)
    logger.info("universe=%s count=%d", universe, len(symbols))
    return symbols


def _parse_csindex_xls(content: bytes) -> list[str]:
    frame = pd.read_excel(BytesIO(content))
    symbol_col = _resolve_symbol_column(frame)
    return frame[symbol_col].astype(str).str.zfill(6).tolist()


def _fetch_csindex_cons(index_code: str) -> list[str]:
    """带超时拉取中证成分 xls（不走 akshare 无超时 get）。

    先按项目 DISABLE_PROXY 策略直连；失败再尝试信任系统代理
    （中证 OSS 在部分网络下必须走代理才能通）。
    """
    url = _CSINDEX_CONS_URL.format(symbol=index_code)
    errors: list[str] = []
    for trust_env in (False, True):
        session = create_http_session()
        session.trust_env = trust_env
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SEC)
            response.raise_for_status()
            symbols = _parse_csindex_xls(response.content)
            logger.info(
                "csindex_cons ok code=%s trust_env=%s count=%d",
                index_code,
                trust_env,
                len(symbols),
            )
            return symbols
        except (
            requests.RequestException,
            OSError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            errors.append(f"trust_env={trust_env}: {exc}")
            logger.warning(
                "csindex_cons try failed code=%s trust_env=%s err=%s",
                index_code,
                trust_env,
                exc,
            )
    raise DataFetchError(
        message=f"中证成分拉取失败 code={index_code}; " + " | ".join(errors),
        suggestion=NETWORK_HINT,
    )


def _resolve_symbol_column(frame: pd.DataFrame) -> str:
    """解析成分股代码列名（兼容中证中英拼接表头）。"""
    for col in COL_SYMBOL_CANDIDATES:
        if col in frame.columns:
            return col
    for col in frame.columns:
        name = str(col)
        if "Constituent Code" in name or "成分券代码" in name:
            return col
    raise DataFetchError(
        message=f"成分股表缺少代码列，现有: {list(frame.columns)}",
        suggestion="更新 COL_SYMBOL_CANDIDATES",
    )


def _load_universe_cache(path: Path, *, allow_stale: bool) -> list[str] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return None
    out = [str(s).zfill(6) for s in symbols]
    ts = float(payload.get("ts", 0))
    age = time.time() - ts
    if age > _UNIVERSE_CACHE_TTL_SEC and not allow_stale:
        return None
    return out


def _save_universe_cache(path: Path, symbols: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"ts": time.time(), "symbols": symbols}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("universe cache save fail path=%s err=%s", path, exc)
