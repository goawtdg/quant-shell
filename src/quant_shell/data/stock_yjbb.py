"""东财业绩报表 — ROE / 行业；磁盘优先，选股前预热一次。"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from quant_shell.common.exceptions import DataFetchError
from quant_shell.common.http_session import create_http_session
from quant_shell.common.logging_config import get_logger
from quant_shell.data.akshare_client import _run_fetch
from quant_shell.data.constants import NETWORK_HINT, REQUEST_TIMEOUT_SEC
from quant_shell.data.disk_cache import CACHE_ROOT, load_any, save_any

logger = get_logger(__name__)

_http = create_http_session()
_YJBB_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}
_REPORT_DATES: tuple[str, ...] = (
    "20251231",
    "20241231",
    "20260331",
    "20250930",
    "20250630",
    "20250331",
    "20240930",
)


def _disk_path(report_date: str):
    return CACHE_ROOT / f"yjbb_{report_date}.pkl"


def _fetch_pages(report_date: str) -> pd.DataFrame:
    filter_date = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:]}"
    params: dict[str, str] = {
        "sortColumns": "UPDATE_DATE,SECURITY_CODE",
        "sortTypes": "-1,-1",
        "pageSize": "500",
        "pageNumber": "1",
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f"(REPORTDATE='{filter_date}')",
    }

    def _page(num: int) -> dict:
        p = dict(params)
        p["pageNumber"] = str(num)
        resp = _http.get(
            _YJBB_URL, params=p, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SEC
        )
        resp.raise_for_status()
        return resp.json()

    first = _page(1)
    result = first.get("result") if isinstance(first, dict) else None
    if not isinstance(result, dict) or not result.get("data"):
        return pd.DataFrame()
    pages = int(result.get("pages") or 1)
    chunks = [pd.DataFrame(result["data"])]
    for page in range(2, pages + 1):
        payload = _page(page)
        page_result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(page_result, dict) or not page_result.get("data"):
            break
        chunks.append(pd.DataFrame(page_result["data"]))
        if page % 5 == 0 or page == pages:
            logger.info("yjbb progress date=%s page=%d/%d", report_date, page, pages)

    big = pd.concat(chunks, ignore_index=True)
    if "SECURITY_CODE" not in big.columns or "WEIGHTAVG_ROE" not in big.columns:
        return pd.DataFrame()
    industry = big["PUBLISHNAME"] if "PUBLISHNAME" in big.columns else None
    if industry is None and "BOARD_NAME" in big.columns:
        industry = big["BOARD_NAME"]
    return pd.DataFrame(
        {
            "股票代码": big["SECURITY_CODE"].astype(str).str.zfill(6),
            "股票简称": big["SECURITY_NAME_ABBR"]
            if "SECURITY_NAME_ABBR" in big.columns
            else "",
            "净资产收益率": pd.to_numeric(big["WEIGHTAVG_ROE"], errors="coerce"),
            "所处行业": industry.fillna("").astype(str) if industry is not None else "",
        }
    ).reset_index(drop=True)


@lru_cache(maxsize=1)
def fetch_yjbb_frame() -> pd.DataFrame:
    """最近一期业绩报表（ROE、行业）；磁盘命中则跳过网络。"""
    for report_date in _REPORT_DATES:
        disk = load_any(_disk_path(report_date))
        if (
            isinstance(disk, pd.DataFrame)
            and not disk.empty
            and "股票代码" in disk.columns
            and "净资产收益率" in disk.columns
        ):
            logger.info("fetch_yjbb_frame disk_hit date=%s rows=%d", report_date, len(disk))
            return disk
        try:
            frame = _run_fetch(
                "stock_yjbb_em",
                lambda d=report_date: _fetch_pages(d),
            )
        except DataFetchError:
            continue
        if (
            not frame.empty
            and "股票代码" in frame.columns
            and "净资产收益率" in frame.columns
        ):
            save_any(_disk_path(report_date), frame)
            logger.info("fetch_yjbb_frame date=%s rows=%d", report_date, len(frame))
            return frame
    logger.warning("fetch_yjbb_frame no data hint=%s", NETWORK_HINT)
    return pd.DataFrame()


def prefetch_yjbb_frame() -> pd.DataFrame:
    """选股前预热。"""
    return fetch_yjbb_frame()


def fetch_stock_roe(symbol: str) -> float:
    """ROE；失败返回 0。"""
    frame = fetch_yjbb_frame()
    if frame.empty:
        return 0.0
    matched = frame.loc[frame["股票代码"].astype(str).str.zfill(6) == symbol]
    if matched.empty:
        return 0.0
    roe_raw = pd.to_numeric(matched.iloc[0]["净资产收益率"], errors="coerce")
    if pd.isna(roe_raw):
        return 0.0
    roe_val = float(roe_raw)
    return roe_val / 100.0 if roe_val > 1.0 else roe_val


def lookup_yjbb_industry(symbol: str) -> str | None:
    """从业绩报表查行业。"""
    frame = fetch_yjbb_frame()
    if frame.empty or "所处行业" not in frame.columns:
        return None
    matched = frame.loc[frame["股票代码"].astype(str).str.zfill(6) == symbol]
    if matched.empty:
        return None
    industry = str(matched.iloc[0]["所处行业"]).strip()
    return industry or None
