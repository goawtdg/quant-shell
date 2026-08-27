"""第 1 层常量 — 东财 API 与 symbol 映射。"""
from __future__ import annotations

from typing import Final

# ETF 代码 -> 指数名称（用于 PE 查询）
SYMBOL_TO_INDEX_NAME: Final[dict[str, str]] = {
    "510300": "沪深300",
    "510500": "中证500",
    "159915": "创业板指",
    "588000": "科创50",
}

# 东财 UT；个股现价走单票 push2，日 K 走腾讯（全 A clist 仅运维脚本）
EASTMONEY_UT_TOKEN: Final[str] = "bd1d9ddb04089700cf9c27f6f7426281"

# 上交所 ETF/股票代码前缀
SHANGHAI_SYMBOL_PREFIXES: Final[tuple[str, ...]] = ("5", "6")

# 乐咕乐股指数代码
LEGULEGU_INDEX_CODE: Final[dict[str, str]] = {
    "沪深300": "000300.SH",
    "中证500": "000905.SH",
    "创业板指": "399006.SZ",
    "科创50": "000688.SH",
}

LEGULEGU_PE_API_URL: Final[str] = "https://legulegu.com/api/stockdata/index-basic-pe"
LEGULEGU_CSRF_PAGE_URL: Final[str] = "https://legulegu.com/stockdata/sz50-ttm-lyr"
LEGULEGU_FIELD_PE_QUANTILE: Final[str] = "ttmPeQuantile"

DATA_SOURCE_NAME: Final[str] = "akshare_eastmoney_legulegu"
PE_HISTORY_MIN_ROWS: Final[int] = 30
REQUEST_TIMEOUT_SEC: Final[int] = 15

# ETF 日 K 线（fund_etf_hist_em）
COL_TRADE_DATE: Final[str] = "日期"
COL_OPEN: Final[str] = "开盘"
COL_HIGH: Final[str] = "最高"
COL_LOW: Final[str] = "最低"
COL_CLOSE: Final[str] = "收盘"
COL_VOLUME: Final[str] = "成交量"
HISTORY_CALENDAR_DAYS: Final[int] = 200

MOMENTUM_3M_DAYS: Final[int] = 63
VOLUME_MA_DAYS: Final[int] = 20

UNIVERSE_CSI300: Final[str] = "csi300"
UNIVERSE_CSI500: Final[str] = "csi500"

INDEX_CODE_MAP: Final[dict[str, str]] = {
    UNIVERSE_CSI300: "000300",
    UNIVERSE_CSI500: "000905",
}

NETWORK_HINT: Final[str] = (
    "1) .env 设 DISABLE_PROXY=true 可保留梯子变量、本项目直连；"
    "2) L1：个股现价单票 push2，日 K 腾讯，选股勿拉全 A clist；"
    "3) TUN 模式请在 Clash 为 eastmoney.com / finance.qq.com 设 DIRECT"
)
