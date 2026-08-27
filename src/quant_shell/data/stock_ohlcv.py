"""A 股日 K — 腾讯前复权单源 + 当日磁盘缓存。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.http_session import create_http_session
from quant_shell.common.logging_config import get_logger
from quant_shell.common.retry import call_with_retry
from quant_shell.data.akshare_client import _run_fetch, resolve_sina_symbol
from quant_shell.data.constants import (
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_TRADE_DATE,
    COL_VOLUME,
    HISTORY_CALENDAR_DAYS,
    NETWORK_HINT,
    REQUEST_TIMEOUT_SEC,
)
from quant_shell.data.ohlcv_cache import (
    get_cached_ohlcv,
    is_ohlcv_session_lag,
    note_ohlcv_session_lag,
    store_ohlcv,
)
from quant_shell.data.ohlcv_quality import (
    ensure_ohlcv_length,
    required_ohlcv_bars,
)

logger = get_logger(__name__)

_http = create_http_session()
_TX_URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}


def _fetch_tx_hist(symbol: str) -> pd.DataFrame:
    code = resolve_sina_symbol(symbol)
    end = datetime.now()
    start = end - timedelta(days=HISTORY_CALENDAR_DAYS)
    params = {
        "_var": "kline_dayqfq",
        "param": (
            f"{code},day,{start.strftime('%Y-%m-%d')},"
            f"{end.strftime('%Y-%m-%d')},640,qfq"
        ),
        "r": "0.82",
    }

    def _call() -> pd.DataFrame:
        resp = _http.get(
            _TX_URL, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SEC
        )
        resp.raise_for_status()
        text = resp.text
        brace = text.find("={")
        if brace < 0:
            raise DataFetchError(
                message=f"腾讯日 K 格式异常: {symbol}",
                suggestion=NETWORK_HINT,
            )
        payload = json.loads(text[brace + 1 :])
        data = payload.get("data") if isinstance(payload, dict) else None
        block = data.get(code) if isinstance(data, dict) else None
        if not isinstance(block, dict):
            raise DataFetchError(
                message=f"腾讯日 K 无 data: {symbol}",
                suggestion=NETWORK_HINT,
            )
        rows = block.get("qfqday") or block.get("day") or block.get("hfqday")
        if not rows:
            raise DataFetchError(
                message=f"腾讯日 K 为空: {symbol}",
                suggestion=NETWORK_HINT,
            )
        parsed = pd.DataFrame(rows).iloc[:, :6]
        parsed.columns = [
            COL_TRADE_DATE,
            COL_OPEN,
            COL_CLOSE,
            COL_HIGH,
            COL_LOW,
            COL_VOLUME,
        ]
        parsed[COL_TRADE_DATE] = pd.to_datetime(parsed[COL_TRADE_DATE])
        for col in (COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME):
            parsed[col] = pd.to_numeric(parsed[col], errors="coerce")
        return parsed.sort_values(COL_TRADE_DATE).reset_index(drop=True)

    return _run_fetch(f"stock_zh_a_hist_tx:{symbol}", _call)


def fetch_stock_daily_ohlcv(symbol: str) -> pd.DataFrame:
    """股票日 K OHLCV（腾讯前复权；内存 + 当日磁盘；收盘后缺完整日则重拉）。"""
    from quant_shell.data.market_session import last_completed_a_share_session

    if not symbol or len(symbol) != 6:
        raise ValidationError(
            message=f"无效股票代码: {symbol}",
            suggestion="使用 6 位 A 股代码",
        )
    cached = get_cached_ohlcv(symbol, min_bars=required_ohlcv_bars())
    if cached is not None:
        return cached

    last_ok: dict[str, object] = {}

    def _pull() -> pd.DataFrame:
        frame = _fetch_tx_hist(symbol)
        last_bar = pd.to_datetime(frame[COL_TRADE_DATE], errors="coerce").max()
        last_bar_date = None if pd.isna(last_bar) else last_bar.date()
        column_map = {
            COL_OPEN: "open",
            COL_HIGH: "high",
            COL_LOW: "low",
            COL_CLOSE: "close",
            COL_VOLUME: "volume",
        }
        ohlcv = frame[list(column_map.keys())].rename(columns=column_map)
        ohlcv = ohlcv.apply(pd.to_numeric, errors="coerce").dropna()
        if ohlcv.empty:
            raise DataFetchError(
                message=f"股票 {symbol} OHLCV 为空",
                suggestion="确认代码正确",
            )
        ohlcv = ohlcv.reset_index(drop=True)
        if COL_TRADE_DATE in frame.columns:
            ohlcv["trade_date"] = frame[COL_TRADE_DATE].values
        ensure_ohlcv_length(symbol, ohlcv)
        last_ok["ohlcv"] = ohlcv
        last_ok["last_bar"] = last_bar_date
        if is_ohlcv_session_lag(last_bar_date):
            raise DataFetchError(
                message=f"日 K 未覆盖 {last_completed_a_share_session()}，最新 {last_bar_date}",
                suggestion="重试腾讯日 K；仍滞后则本进程钉住缓存",
            )
        return ohlcv

    lagged = False
    try:
        ohlcv = call_with_retry(_pull, layer="L1", op="stock_ohlcv", symbol=symbol)
        last_bar_date = last_ok.get("last_bar")
    except DataFetchError:
        ohlcv = last_ok.get("ohlcv")
        last_bar_date = last_ok.get("last_bar")
        if not isinstance(ohlcv, pd.DataFrame):
            raise
        lagged = True
        note_ohlcv_session_lag(symbol)
        audit.emit(
            layer="L1",
            event="ohlcv_session_lag",
            severity="ERROR",
            error_code="OHLCV_SESSION_LAG",
            symbol=symbol,
            message=(
                f"日 K 未覆盖 {last_completed_a_share_session()}，最新 {last_bar_date}；"
                "本进程钉住；联动将记硬错误"
            ),
        )
    bar_date = last_bar_date if isinstance(last_bar_date, date) else None
    store_ohlcv(symbol, ohlcv, last_bar_date=bar_date, pin_process=True)
    logger.debug(
        "fetch_stock_daily_ohlcv symbol=%s bars=%d last_bar=%s lagged=%s",
        symbol,
        len(ohlcv),
        bar_date,
        lagged,
    )
    return ohlcv
