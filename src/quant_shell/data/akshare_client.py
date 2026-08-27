"""AkShare / 东财 / 乐咕数据采集 — 第 1 层唯一外部 IO 入口。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, TypeVar

import akshare as ak
import pandas as pd
import py_mini_racer
import requests
from akshare.stock_feature.stock_a_indicator import get_cookie_csrf
from akshare.stock_feature.stock_a_pe_and_pb import hash_code

from quant_shell.common.exceptions import (
    DataFetchError,
    EXTERNAL_IO_ERRORS,
    QuantSystemError,
    ValidationError,
)
from quant_shell.common.http_session import create_http_session
from quant_shell.common.logging_config import get_logger
from quant_shell.data.constants import (
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_TRADE_DATE,
    COL_VOLUME,
    HISTORY_CALENDAR_DAYS,
    LEGULEGU_CSRF_PAGE_URL,
    LEGULEGU_FIELD_PE_QUANTILE,
    LEGULEGU_INDEX_CODE,
    LEGULEGU_PE_API_URL,
    NETWORK_HINT,
    PE_HISTORY_MIN_ROWS,
    REQUEST_TIMEOUT_SEC,
    SHANGHAI_SYMBOL_PREFIXES,
    SYMBOL_TO_INDEX_NAME,
)

logger = get_logger(__name__)
T = TypeVar("T")

_http_session = create_http_session()
# py_mini_racer / V8 非线程安全：并行 MiniRacer() 会 FATAL partition_address_space
_MINI_RACER_LOCK = threading.Lock()


@dataclass(frozen=True)
class EtfSpotRow:
    """ETF 现货一行数据。"""

    price: float
    volume: float


def resolve_sina_symbol(symbol: str) -> str:
    """解析新浪行情代码（sh510300 / sz159915）。"""
    prefix = "sh" if symbol.startswith(SHANGHAI_SYMBOL_PREFIXES) else "sz"
    return f"{prefix}{symbol}"


_SPOT_CODE_COL = "代码"
_SPOT_PRICE_COL = "最新价"
_SPOT_VOLUME_COL = "成交量"


def _legulegu_token() -> str:
    """生成乐咕乐股 API token。"""
    with _MINI_RACER_LOCK:
        js_runtime = py_mini_racer.MiniRacer()
        js_runtime.eval(hash_code)
        return str(js_runtime.call("hex", datetime.now().date().isoformat())).lower()


def _run_fetch(api_name: str, fetcher: Callable[[], T]) -> T:
    """调用 fetcher 并在源边界收成 DataFetchError。"""
    try:
        return fetcher()
    except QuantSystemError:
        raise
    except requests.RequestException as exc:
        raise DataFetchError(
            message=f"{api_name} 网络请求失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc
    except EXTERNAL_IO_ERRORS as exc:
        raise DataFetchError(
            message=f"{api_name} 失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc


def fetch_etf_spot_batch() -> pd.DataFrame:
    """拉取 ETF 全市场快照（无缓存；TTL 缓存在 live_price）。"""
    frame = _run_fetch("fund_etf_spot_em", ak.fund_etf_spot_em)
    for col in (_SPOT_CODE_COL, _SPOT_PRICE_COL, _SPOT_VOLUME_COL):
        if col not in frame.columns:
            raise DataFetchError(
                message=f"fund_etf_spot_em 缺少列: {col}",
                suggestion="检查 AkShare 版本",
            )
    out = frame[[_SPOT_CODE_COL, _SPOT_PRICE_COL, _SPOT_VOLUME_COL]].copy()
    out[_SPOT_CODE_COL] = out[_SPOT_CODE_COL].astype(str).str.zfill(6)
    for col in (_SPOT_PRICE_COL, _SPOT_VOLUME_COL):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    logger.info("fetch_etf_spot_batch rows=%d", len(out))
    return out.reset_index(drop=True)


def fetch_etf_spot(symbol: str) -> EtfSpotRow:
    """拉取单只 ETF 现货：只查 live_price TTL 批次，禁止新浪收盘当现价。"""
    if not symbol or not symbol.strip():
        raise ValidationError(
            message="symbol 不能为空",
            suggestion="传入 6 位 ETF 代码，例如 510300",
        )
    from quant_shell.data.live_price import lookup_etf_spot

    return lookup_etf_spot(symbol)


def _fetch_legulegu_pe_quantile(index_name: str) -> float:
    """从乐咕乐股拉取指数 PE 历史分位。"""
    index_code = LEGULEGU_INDEX_CODE.get(index_name)
    if index_code is None:
        raise ValidationError(
            message=f"指数 {index_name} 无乐咕代码映射",
            suggestion="在 layer1_data/constants.py LEGULEGU_INDEX_CODE 中添加",
        )

    token = _legulegu_token()
    params = {"token": token, "indexCode": index_code}
    cookie_kwargs = get_cookie_csrf(url=LEGULEGU_CSRF_PAGE_URL)

    def _call() -> requests.Response:
        return _http_session.get(
            LEGULEGU_PE_API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SEC,
            **cookie_kwargs,
        )

    response = _run_fetch("legulegu_index_pe", _call)
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload:
        raise DataFetchError(
            message=f"乐咕乐股 PE 响应异常: {index_name}",
            suggestion="检查 legulegu.com 是否可访问",
        )

    frame = pd.DataFrame(payload["data"])
    if LEGULEGU_FIELD_PE_QUANTILE not in frame.columns:
        raise DataFetchError(
            message="乐咕 PE 响应缺少 ttmPeQuantile 列",
            suggestion="检查乐咕 API 字段是否变更",
        )

    quantile_series = pd.to_numeric(
        frame[LEGULEGU_FIELD_PE_QUANTILE], errors="coerce"
    ).dropna()
    if len(quantile_series) < PE_HISTORY_MIN_ROWS:
        raise DataFetchError(
            message=f"指数 {index_name} PE 历史不足 {PE_HISTORY_MIN_ROWS} 行",
            suggestion="检查 legulegu 数据源",
        )

    return float(quantile_series.iloc[-1])


def fetch_index_pe_percentile(symbol: str) -> float:
    """获取跟踪指数 PE 的历史分位（乐咕乐股 ttmPeQuantile）。"""
    index_name = SYMBOL_TO_INDEX_NAME.get(symbol)
    if index_name is None:
        raise ValidationError(
            message=f"symbol {symbol} 无指数 PE 映射",
            suggestion="在 layer1_data/constants.py SYMBOL_TO_INDEX_NAME 中添加映射",
        )

    logger.debug("fetch_index_pe symbol=%s index=%s", symbol, index_name)
    percentile = _fetch_legulegu_pe_quantile(index_name)
    logger.debug("pe_percentile=%.4f", percentile)
    return percentile


def _fetch_etf_hist_em(symbol: str) -> pd.DataFrame:
    """东财 ETF 日 K（无 MiniRacer，可并行）。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=max(HISTORY_CALENDAR_DAYS, 1500))).strftime(
        "%Y%m%d"
    )
    raw = _run_fetch(
        "fund_etf_hist_em",
        lambda: ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="",
        ),
    )
    if raw.empty:
        raise DataFetchError(
            message=f"东财 ETF 历史为空: {symbol}",
            suggestion="确认代码有效且在东财有行情",
        )
    missing = [
        cn
        for cn in (COL_TRADE_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME)
        if cn not in raw.columns
    ]
    if missing:
        raise DataFetchError(
            message=f"fund_etf_hist_em 缺少列: {missing}",
            suggestion="检查 AkShare 返回字段",
        )
    frame = raw[
        [COL_TRADE_DATE, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]
    ].copy()
    frame[COL_TRADE_DATE] = pd.to_datetime(frame[COL_TRADE_DATE])
    return frame.sort_values(COL_TRADE_DATE).reset_index(drop=True)


def _fetch_etf_hist_sina(symbol: str) -> pd.DataFrame:
    """新浪 ETF 日 K 兜底（内部 MiniRacer，必须串行）。"""
    with _MINI_RACER_LOCK:
        raw = _run_fetch(
            "fund_etf_hist_sina",
            lambda: ak.fund_etf_hist_sina(symbol=resolve_sina_symbol(symbol)),
        )
    if raw.empty:
        raise DataFetchError(
            message=f"新浪 ETF 历史为空: {symbol}",
            suggestion="确认新浪代码映射 resolve_sina_symbol",
        )

    frame = raw.rename(
        columns={
            "date": COL_TRADE_DATE,
            "open": COL_OPEN,
            "high": COL_HIGH,
            "low": COL_LOW,
            "close": COL_CLOSE,
            "volume": COL_VOLUME,
        }
    )
    missing = [cn for cn in (COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME) if cn not in frame.columns]
    if missing:
        raise DataFetchError(
            message=f"fund_etf_hist_sina 缺少列: {missing}",
            suggestion="检查 AkShare 返回字段",
        )
    frame[COL_TRADE_DATE] = pd.to_datetime(frame[COL_TRADE_DATE])
    return frame.sort_values(COL_TRADE_DATE).reset_index(drop=True)


def _fetch_etf_hist_frame(symbol: str) -> pd.DataFrame:
    """拉取 ETF 日 K：优先东财，失败再新浪（加锁）。"""
    if not symbol or not symbol.strip():
        raise ValidationError(
            message="symbol 不能为空",
            suggestion="传入 6 位 ETF 代码，例如 510300",
        )
    try:
        return _fetch_etf_hist_em(symbol)
    except (DataFetchError, ValidationError, OSError) as exc:
        logger.warning(
            "fund_etf_hist_em failed symbol=%s; fallback sina err=%s",
            symbol,
            exc,
        )
        return _fetch_etf_hist_sina(symbol)


def fetch_etf_daily_closes(symbol: str) -> pd.Series:
    """拉取 ETF 日 K 收盘价序列（单标的，供 L3 数学指标）。

    与 ``fetch_etf_daily_ohlcv`` 共用缓存，避免同次任务对 510300 等重复拉网。
    """
    ohlcv = fetch_etf_daily_ohlcv(symbol)
    closes = pd.to_numeric(ohlcv["close"], errors="coerce").dropna()
    if closes.empty:
        raise DataFetchError(
            message=f"ETF {symbol} 历史收盘价为空",
            suggestion="确认代码正确且已上市",
        )
    logger.debug("fetch_etf_daily_closes symbol=%s bars=%d", symbol, len(closes))
    return closes.reset_index(drop=True)


def _etf_hist_to_ohlcv(symbol: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, date | None]:
    """东财/新浪日 K 帧转小写 OHLCV；根数不足抛 ValidationError。"""
    from quant_shell.data.ohlcv_quality import ensure_ohlcv_length

    column_map = {
        COL_OPEN: "open",
        COL_HIGH: "high",
        COL_LOW: "low",
        COL_CLOSE: "close",
        COL_VOLUME: "volume",
    }
    missing = [cn for cn in column_map if cn not in frame.columns]
    if missing:
        raise DataFetchError(
            message=f"ETF {symbol} OHLCV 缺少列: {missing}",
            suggestion="检查东财/新浪 ETF 日 K 返回字段",
        )

    ohlcv = frame[list(column_map.keys())].rename(columns=column_map)
    ohlcv = ohlcv.apply(pd.to_numeric, errors="coerce")
    if COL_TRADE_DATE in frame.columns:
        ohlcv["trade_date"] = frame[COL_TRADE_DATE].values
    ohlcv = ohlcv.dropna(subset=["close"])
    if ohlcv.empty:
        raise DataFetchError(
            message=f"ETF {symbol} OHLCV 为空",
            suggestion="确认代码正确且已上市",
        )
    ohlcv = ohlcv.reset_index(drop=True)
    ensure_ohlcv_length(symbol, ohlcv)
    last_bar = None
    if "trade_date" in ohlcv.columns:
        ts = pd.to_datetime(ohlcv["trade_date"], errors="coerce").max()
        if not pd.isna(ts):
            last_bar = ts.date()
    return ohlcv, last_bar


def fetch_etf_daily_ohlcv(symbol: str) -> pd.DataFrame:
    """拉取 ETF 日 K OHLCV（供 Alpha 因子库）。

    内存 + 当日磁盘缓存（与股票日 K 同机制）：同进程内同一标的只打一次外网。
    收盘后未盖住完整交易日则重试一次（东财优先）；仍滞后则 ERROR + 钉住，
    联动结束汇总为 OHLCV_SESSION_LAG 硬错误。

    Returns:
        列名 ``open/high/low/close/volume`` 的小写 DataFrame。
    """
    from quant_shell.common import audit
    from quant_shell.common.retry import call_with_retry
    from quant_shell.data.market_session import last_completed_a_share_session
    from quant_shell.data.ohlcv_cache import (
        get_cached_ohlcv,
        is_ohlcv_session_lag,
        store_ohlcv,
    )
    from quant_shell.data.ohlcv_quality import required_ohlcv_bars

    need = required_ohlcv_bars()
    cached = get_cached_ohlcv(symbol, min_bars=need)
    if cached is not None:
        logger.debug("fetch_etf_daily_ohlcv cache_hit symbol=%s bars=%d", symbol, len(cached))
        return cached

    last_ok: dict[str, object] = {}

    def _pull() -> pd.DataFrame:
        ohlcv, last_bar = _etf_hist_to_ohlcv(symbol, _fetch_etf_hist_frame(symbol))
        last_ok["ohlcv"] = ohlcv
        last_ok["last_bar"] = last_bar
        if is_ohlcv_session_lag(last_bar):
            raise DataFetchError(
                message=f"日 K 未覆盖 {last_completed_a_share_session()}，最新 {last_bar}",
                suggestion="重试东财后再用新浪；仍滞后则本进程钉住缓存",
            )
        return ohlcv

    lagged = False
    try:
        ohlcv = call_with_retry(_pull, layer="L1", op="etf_ohlcv", symbol=symbol)
        last_bar = last_ok.get("last_bar")
    except DataFetchError:
        ohlcv = last_ok.get("ohlcv")
        last_bar = last_ok.get("last_bar")
        if not isinstance(ohlcv, pd.DataFrame):
            raise
        lagged = True
        from quant_shell.data.ohlcv_cache import note_ohlcv_session_lag

        note_ohlcv_session_lag(symbol)
        audit.emit(
            layer="L1",
            event="ohlcv_session_lag",
            severity="ERROR",
            error_code="OHLCV_SESSION_LAG",
            symbol=symbol,
            message=(
                f"日 K 未覆盖 {last_completed_a_share_session()}，最新 {last_bar}；"
                "本进程钉住；联动将记硬错误"
            ),
        )
    bar_date = last_bar if isinstance(last_bar, date) else None
    store_ohlcv(symbol, ohlcv, last_bar_date=bar_date, pin_process=True)
    logger.debug(
        "fetch_etf_daily_ohlcv symbol=%s bars=%d last_bar=%s lagged=%s",
        symbol,
        len(ohlcv),
        bar_date,
        lagged,
    )
    return ohlcv
