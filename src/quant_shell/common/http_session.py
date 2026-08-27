"""项目 HTTP Session — 按配置决定是否信任系统代理。"""
from __future__ import annotations

import requests


def create_http_session() -> requests.Session:
    """创建 requests Session；DISABLE_PROXY 时忽略 HTTP_PROXY 环境变量。"""
    from quant_shell.config.settings import settings

    session = requests.Session()
    if settings.disable_proxy:
        session.trust_env = False
    return session
