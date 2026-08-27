"""同花顺财经直播直连 API。"""
from __future__ import annotations

from quant_shell.common.exceptions import DataFetchError
from quant_shell.intelligence.client import get_json
from quant_shell.intelligence.providers.constants import THS_PUSH_URL, THS_REFERER


def fetch_ths_flash(*, page: int = 1) -> list[dict[str, object]]:
    """拉取同花顺 push 快讯。"""
    params = {"page": str(page), "tag": "", "track": "website"}
    payload = get_json(
        "ths_flash",
        THS_PUSH_URL,
        params=params,
        headers={"Referer": THS_REFERER},
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataFetchError(
            message="ths_flash 缺少 data 字段",
            suggestion="检查同花顺 push API",
        )
    items = data.get("list")
    if not isinstance(items, list):
        raise DataFetchError(
            message="ths_flash 缺少 list",
            suggestion="检查同花顺 push API 响应结构",
        )
    return [row for row in items if isinstance(row, dict)]
