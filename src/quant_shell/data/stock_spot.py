"""A 股现价 — 热路径只走单票；全表快照仅供运维脚本显式调用。"""
from __future__ import annotations

import math
from functools import lru_cache

import pandas as pd

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.http_session import create_http_session
from quant_shell.common.logging_config import get_logger
from quant_shell.data.akshare_client import _run_fetch, resolve_sina_symbol
from quant_shell.data.constants import (
    EASTMONEY_UT_TOKEN,
    NETWORK_HINT,
    REQUEST_TIMEOUT_SEC,
)
from quant_shell.data.disk_cache import (
    CACHE_ROOT,
    load_frame_ttl,
    save_frame_ttl,
)

logger = get_logger(__name__)

_http = create_http_session()

_SPOT_CODE = "代码"
_SPOT_NAME = "名称"
_SPOT_PRICE = "最新价"
_SPOT_VOLUME = "成交量"
_SPOT_PE = "市盈率-动态"
_SPOT_MCAP = "总市值"
_SPOT_TURNOVER = "换手率"

_CLIST_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_QUOTE_URLS = (
    "https://push2delay.eastmoney.com/api/qt/stock/get",
    "https://push2.eastmoney.com/api/qt/stock/get",
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}
# 东财 clist 单页硬顶 100；全 A ≈ 59 页，禁止进入选股/盯市热路径。
_PAGE_SIZE = 100
_BATCH_DISK = CACHE_ROOT / "a_share_spot.pkl"
_FIELD_MAP = {
    "f12": _SPOT_CODE,
    "f14": _SPOT_NAME,
    "f2": _SPOT_PRICE,
    "f5": _SPOT_VOLUME,
    "f9": _SPOT_PE,
    "f20": _SPOT_MCAP,
    "f8": _SPOT_TURNOVER,
}


def _require_symbol(symbol: str) -> str:
    if not symbol or len(symbol) != 6:
        raise ValidationError(
            message=f"无效股票代码: {symbol}",
            suggestion="使用 6 位 A 股代码",
        )
    return symbol


def _secid(symbol: str) -> str:
    market = 1 if symbol.startswith(("5", "6", "9")) else 0
    return f"{market}.{symbol}"


def _parse_quote(symbol: str, payload: object) -> dict[str, float | str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise DataFetchError(
            message=f"单票行情无 data: {symbol}",
            suggestion="检查东财 push2 是否可达",
        )
    price = float(data.get("f43") or 0)
    if price <= 0:
        raise DataFetchError(
            message=f"单票现价无效: {symbol}={price}",
            suggestion="休市或停牌时可能无最新价",
        )
    market_cap = float(data.get("f116") or 0)
    if 0 < market_cap < 1_000_000:
        market_cap *= 1e8
    # 单票 qt/stock/get：动态 PE 在 f162（clist 全表才是 f9；f9 常缺省→0）
    pe = _first_positive_float(data, ("f162", "f164", "f9"))
    return {
        "symbol": symbol,
        "name": str(data.get("f58") or ""),
        "price": price,
        "volume": float(data.get("f47") or 0),
        "pe": pe,
        "market_cap": market_cap,
        "turnover_rate": float(data.get("f168") or 0),
    }


def _first_positive_float(data: dict, keys: tuple[str, ...]) -> float:
    for key in keys:
        raw = data.get(key)
        if raw in (None, "", "-"):
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            return val
    return 0.0


def _quote_em(symbol: str, url: str) -> dict[str, float | str]:
    params = {
        "fltt": "2",
        "invt": "2",
        # f162=市盈率动 / f164=PE(TTM)；f9 在单票接口经常不返回
        "fields": "f43,f47,f57,f58,f9,f116,f162,f164,f168",
        "secid": _secid(symbol),
    }

    def _call() -> dict[str, float | str]:
        resp = _http.get(
            url, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SEC
        )
        resp.raise_for_status()
        return _parse_quote(symbol, resp.json())

    return _run_fetch(f"stock_spot_quote_em:{symbol}", _call)


def _quote_sina(symbol: str) -> dict[str, float | str]:
    sina = resolve_sina_symbol(symbol)
    url = f"https://hq.sinajs.cn/list={sina}"

    def _call() -> dict[str, float | str]:
        resp = _http.get(
            url,
            headers={**_HEADERS, "Referer": "https://finance.sina.com.cn"},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        text = resp.text
        if "=" not in text or '"' not in text:
            raise DataFetchError(
                message=f"新浪单票行情格式异常: {symbol}",
                suggestion=NETWORK_HINT,
            )
        parts = text.split('"', 2)[1].split(",")
        if len(parts) < 4:
            raise DataFetchError(
                message=f"新浪单票字段不足: {symbol}",
                suggestion=NETWORK_HINT,
            )
        price = float(parts[3] or 0)
        if price <= 0:
            raise DataFetchError(
                message=f"新浪现价无效: {symbol}={price}",
                suggestion="休市或停牌时可能无最新价",
            )
        return {
            "symbol": symbol,
            "name": str(parts[0] or ""),
            "price": price,
            "volume": float(parts[8] or 0) if len(parts) > 8 else 0.0,
            "pe": 0.0,
            "market_cap": 0.0,
            "turnover_rate": 0.0,
        }

    return _run_fetch(f"stock_spot_quote_sina:{symbol}", _call)


def fetch_stock_spot_quote(symbol: str) -> dict[str, float | str]:
    """单票现价：东财 → 新浪。选股/盯市唯一热路径。"""
    symbol = _require_symbol(symbol)
    errors: list[str] = []
    for url in _QUOTE_URLS:
        try:
            return _quote_em(symbol, url)
        except (DataFetchError, OSError) as exc:
            errors.append(f"{url}:{exc}")
    try:
        row = _quote_sina(symbol)
        logger.info("stock_spot_quote fallback=sina symbol=%s", symbol)
        return row
    except (DataFetchError, OSError) as exc:
        errors.append(f"sina:{exc}")
        raise DataFetchError(
            message=f"单票行情全部失败: {symbol} | {'; '.join(errors[:3])}",
            suggestion=NETWORK_HINT,
        ) from exc


def fetch_stock_spot(symbol: str) -> dict[str, float | str]:
    """个股现货 — 始终单票，绝不触发全 A 分页。"""
    return fetch_stock_spot_quote(symbol)


def _spot_ttl_sec() -> float:
    from quant_shell.config.settings import settings

    return float(getattr(settings, "spot_cache_ttl_sec", 600.0) or 600.0)


def _normalize_batch(raw: pd.DataFrame) -> pd.DataFrame:
    missing = [k for k in _FIELD_MAP if k not in raw.columns]
    if missing:
        raise DataFetchError(
            message=f"A 股快照缺少字段: {missing}",
            suggestion="检查东财 clist fields 是否变更",
        )
    out = pd.DataFrame({name: raw[code] for code, name in _FIELD_MAP.items()})
    for col in (_SPOT_PRICE, _SPOT_VOLUME, _SPOT_PE, _SPOT_MCAP, _SPOT_TURNOVER):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out[_SPOT_CODE] = out[_SPOT_CODE].astype(str).str.zfill(6)
    return out.reset_index(drop=True)


def _fetch_batch_pages() -> pd.DataFrame:
    params: dict[str, str] = {
        "pn": "1",
        "pz": str(_PAGE_SIZE),
        "po": "1",
        "np": "1",
        "ut": EASTMONEY_UT_TOKEN,
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": (
            "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
            "f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152"
        ),
    }

    def _page(pn: int) -> dict:
        p = dict(params)
        p["pn"] = str(pn)
        resp = _http.get(_CLIST_URL, params=p, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return resp.json()

    first = _page(1)
    data = first.get("data") if isinstance(first, dict) else None
    if not isinstance(data, dict) or not data.get("diff"):
        raise DataFetchError(message="A 股全表快照为空", suggestion=NETWORK_HINT)
    chunks = [pd.DataFrame(data["diff"])]
    per_page = max(len(data["diff"]), 1)
    total = int(data.get("total") or per_page)
    pages = max(1, math.ceil(total / per_page))
    logger.info("a_share_spot paging total=%d pages=%d", total, pages)
    for page in range(2, pages + 1):
        payload = _page(page)
        page_data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(page_data, dict) or not page_data.get("diff"):
            break
        chunks.append(pd.DataFrame(page_data["diff"]))
        if page % 10 == 0 or page == pages:
            logger.info("a_share_spot progress page=%d/%d", page, pages)
    return pd.concat(chunks, ignore_index=True)


@lru_cache(maxsize=1)
def fetch_a_share_spot_batch() -> pd.DataFrame:
    """全 A 快照（慢：~59 页）。仅运维脚本显式调用，选股/盯市勿用。"""
    disk = load_frame_ttl(_BATCH_DISK, _spot_ttl_sec())
    if disk is not None:
        logger.info("fetch_a_share_spot_batch disk_hit rows=%d", len(disk))
        return disk
    raw = _run_fetch("a_share_spot_batch", _fetch_batch_pages)
    frame = _normalize_batch(raw)
    save_frame_ttl(_BATCH_DISK, frame)
    logger.info("fetch_a_share_spot_batch rows=%d", len(frame))
    return frame
