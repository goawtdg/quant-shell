"""东财业绩报表 — ROE / 行业；磁盘优先，选股前预热一次。"""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

from quant_shell.common.exceptions import DataFetchError, ValidationError
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
    notice_col = next(
        (col for col in ("NOTICE_DATE", "ANN_DATE", "DECLAREDATE") if col in big.columns),
        None,
    )
    if notice_col is None:
        raise ValidationError(
            message="业绩表缺少公告日",
            suggestion="东财列里需要 NOTICE_DATE / ANN_DATE / DECLAREDATE",
        )
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
            "公告日": pd.to_datetime(big[notice_col], errors="coerce"),
            "报告期": report_date,
        }
    ).reset_index(drop=True)


def _usable_yjbb(frame: object) -> bool:
    return (
        isinstance(frame, pd.DataFrame)
        and not frame.empty
        and {"股票代码", "净资产收益率", "公告日"}.issubset(frame.columns)
    )


def _load_one_report(report_date: str) -> pd.DataFrame:
    disk = load_any(_disk_path(report_date))
    if _usable_yjbb(disk):
        logger.info("yjbb disk_hit date=%s rows=%d", report_date, len(disk))
        return disk
    frame = _run_fetch("stock_yjbb_em", lambda d=report_date: _fetch_pages(d))
    if frame.empty:
        return frame
    if not _usable_yjbb(frame):
        raise ValidationError(
            message=f"业绩表 {report_date} 缺少代码、ROE 或公告日",
            suggestion="不要使用没有公告日的缓存",
        )
    save_any(_disk_path(report_date), frame)
    logger.info("yjbb fetched date=%s rows=%d", report_date, len(frame))
    return frame


@lru_cache(maxsize=1)
def _yjbb_history() -> pd.DataFrame:
    """全部报告期。某一期网络失败直接抛出，不用更旧的一期冒充。"""
    frames = [_load_one_report(report_date) for report_date in _REPORT_DATES]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise DataFetchError(
            message="业绩表没有任何报告期",
            suggestion=NETWORK_HINT,
        )
    return pd.concat(frames, ignore_index=True)


def latest_announced(history: pd.DataFrame, asof: date) -> pd.DataFrame:
    """每只股票保留公告日不晚于 asof 的最后一行。"""
    if "公告日" not in history.columns:
        raise ValidationError(
            message="业绩表缺少公告日",
            suggestion="重新拉取业绩表，旧缓存没有公告日",
        )
    table = history.copy()
    table["公告日"] = pd.to_datetime(table["公告日"], errors="coerce")
    if table["公告日"].isna().all():
        raise ValidationError(
            message="业绩表公告日无法解析",
            suggestion="检查 NOTICE_DATE 的格式",
        )
    table = table.dropna(subset=["公告日"])
    table = table.loc[table["公告日"].dt.date <= asof]
    if table.empty:
        return table
    table = table.sort_values("公告日")
    return table.groupby("股票代码", as_index=False).tail(1)


def fetch_yjbb_frame(asof: date | None = None) -> pd.DataFrame:
    """公告日不晚于 asof 的最新 ROE 与行业。"""
    return latest_announced(_yjbb_history(), asof or date.today())


def prefetch_yjbb_frame() -> pd.DataFrame:
    """选股前预热。"""
    return fetch_yjbb_frame()


def fetch_stock_roe(symbol: str, asof: date | None = None) -> float | None:
    """已公告 ROE。没有不晚于 asof 的报告时返回 None。"""
    frame = fetch_yjbb_frame(asof)
    if frame.empty:
        return None
    matched = frame.loc[frame["股票代码"].astype(str).str.zfill(6) == symbol]
    if matched.empty:
        return None
    roe_raw = pd.to_numeric(matched.iloc[0]["净资产收益率"], errors="coerce")
    if pd.isna(roe_raw):
        return None
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
