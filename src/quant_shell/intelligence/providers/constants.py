"""第 2 层直连 API 常量。"""
from __future__ import annotations

from typing import Final

CLS_ROLL_URL: Final[str] = "https://www.cls.cn/v1/roll/get_roll_list"
CLS_APP: Final[str] = "CailianpressWeb"
CLS_OS: Final[str] = "web"
CLS_SV: Final[str] = "8.7.9"
CLS_REFRESH_TYPE: Final[str] = "1"
CLS_REFERER: Final[str] = "https://www.cls.cn/telegraph"

THS_PUSH_URL: Final[str] = "https://news.10jqka.com.cn/tapp/news/push/stock"
THS_REFERER: Final[str] = "https://news.10jqka.com.cn/realtimenews.html"

DEFAULT_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
