"""财联社电报直连 API。"""
from __future__ import annotations

import hashlib
import time

from quant_shell.common.exceptions import DataFetchError
from quant_shell.intelligence.client import get_json
from quant_shell.intelligence.providers.constants import (
    CLS_APP,
    CLS_OS,
    CLS_REFRESH_TYPE,
    CLS_REFERER,
    CLS_ROLL_URL,
    CLS_SV,
)


def build_cls_sign(param_string: str) -> str:
    """财联社 sign = MD5(SHA1(param_string))。"""
    sha1_hex = hashlib.sha1(param_string.encode("utf-8")).hexdigest()
    return hashlib.md5(sha1_hex.encode("utf-8")).hexdigest()


def fetch_cls_telegraph(*, rn: int = 20) -> list[dict[str, object]]:
    """拉取财联社电报（v1/roll/get_roll_list）。"""
    last_time = int(time.time())
    param_string = (
        f"app={CLS_APP}&last_time={last_time}&os={CLS_OS}"
        f"&refresh_type={CLS_REFRESH_TYPE}&rn={rn}&sv={CLS_SV}"
    )
    params = {
        "app": CLS_APP,
        "last_time": str(last_time),
        "os": CLS_OS,
        "refresh_type": CLS_REFRESH_TYPE,
        "rn": str(rn),
        "sv": CLS_SV,
        "sign": build_cls_sign(param_string),
    }
    payload = get_json(
        "cls_telegraph",
        CLS_ROLL_URL,
        params=params,
        headers={"Referer": CLS_REFERER},
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataFetchError(
            message="cls_telegraph 缺少 data 字段",
            suggestion="对照 RSSHub lib/routes/cls 更新 sign 或路径",
        )
    roll_data = data.get("roll_data")
    if not isinstance(roll_data, list):
        raise DataFetchError(
            message="cls_telegraph 缺少 roll_data",
            suggestion="检查财联社 API 响应结构",
        )
    return [row for row in roll_data if isinstance(row, dict)]
