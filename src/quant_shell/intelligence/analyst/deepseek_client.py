"""DeepSeek 官方 API 客户端。"""
from __future__ import annotations

import json

import requests

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.config.settings import settings

logger = get_logger(__name__)


def resolve_api_key(explicit: str | None = None) -> str:
    """解析 DeepSeek API Key。"""
    key = (explicit or settings.deepseek_api_key).strip()
    if not key:
        raise ValidationError(
            message="未配置 DEEPSEEK_API_KEY",
            suggestion="在项目根目录 .env 中设置 DEEPSEEK_API_KEY（参考 .env.example）",
        )
    return key


def chat_json(
    messages: list[dict[str, str]],
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    """调用 DeepSeek Chat Completions（JSON 模式）。"""
    key = resolve_api_key(api_key)
    model_name = model or settings.deepseek_model
    url = f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.deepseek_timeout_sec,
        )
        if response.status_code >= 400:
            detail = (response.text or "")[:400]
            raise DataFetchError(
                message=(
                    f"DeepSeek API 请求失败: {response.status_code} "
                    f"for url: {url} body={detail}"
                ),
                suggestion="检查模型名/Key/报文是否超限；400 常见于 context 过长或模型不可用",
            )
        body = response.json()
    except DataFetchError:
        raise
    except requests.RequestException as exc:
        raise DataFetchError(
            message=f"DeepSeek API 请求失败: {exc}",
            suggestion="检查 .env 中 DEEPSEEK_API_KEY 与网络",
        ) from exc

    content = _extract_content(body)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DataFetchError(
            message=f"DeepSeek 返回非 JSON: {content[:200]}",
            suggestion="重试或降低 prompt 复杂度",
        ) from exc

    if not isinstance(parsed, dict):
        raise DataFetchError(
            message="DeepSeek JSON 根节点非 object",
            suggestion="检查 response_format 是否生效",
        )
    logger.info("DeepSeek chat_json ok model=%s keys=%s", model_name, list(parsed.keys()))
    return parsed


def _extract_content(body: dict[str, object]) -> str:
    """从 chat completion 响应提取 content。"""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DataFetchError(
            message="DeepSeek 响应缺少 choices",
            suggestion="检查 API 版本",
        )
    first = choices[0]
    if not isinstance(first, dict):
        raise DataFetchError(message="DeepSeek choices[0] 格式异常", suggestion="检查 API 响应")
    message = first.get("message")
    if not isinstance(message, dict):
        raise DataFetchError(message="DeepSeek message 缺失", suggestion="检查 API 响应")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise DataFetchError(message="DeepSeek content 为空", suggestion="重试请求")
    return content.strip()
