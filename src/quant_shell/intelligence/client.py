"""HTTP JSON 请求与情报源 fetch 封装。"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import requests

from quant_shell.common.exceptions import DataFetchError
from quant_shell.common.http_session import create_http_session
from quant_shell.data.constants import NETWORK_HINT
from quant_shell.intelligence.providers.constants import DEFAULT_USER_AGENT

T = TypeVar("T")
_http_session = create_http_session()


def get_json(
    api_name: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    """GET JSON 并统一异常。"""
    merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged_headers.update(headers)
    try:
        response = _http_session.get(
            url,
            params=params,
            headers=merged_headers,
            timeout=15,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        payload = response.json()
    except requests.RequestException as exc:
        raise DataFetchError(
            message=f"{api_name} 网络请求失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc

    if not isinstance(payload, dict):
        raise DataFetchError(
            message=f"{api_name} 返回非 JSON 对象",
            suggestion="检查 API 是否变更",
        )
    return payload


def run_source_fetch(api_name: str, fetcher: Callable[[], T]) -> T:
    """调用情报源 fetcher 并统一异常。"""
    try:
        return fetcher()
    except requests.RequestException as exc:
        raise DataFetchError(
            message=f"{api_name} 网络请求失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc
    except OSError as exc:
        raise DataFetchError(
            message=f"{api_name} 网络请求失败: {exc}",
            suggestion=NETWORK_HINT,
        ) from exc
    except DataFetchError:
        raise
    except (KeyError, ValueError, TypeError) as exc:
        raise DataFetchError(
            message=f"{api_name} 响应解析失败: {exc}",
            suggestion="检查 API 响应结构",
        ) from exc
