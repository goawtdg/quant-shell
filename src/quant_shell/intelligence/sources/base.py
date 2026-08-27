"""情报源抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from quant_shell.common.types import IntelligenceItem


class IntelligenceSource(ABC):
    """单个 OSINT 情报源。"""

    name: str
    # True：依赖 symbol（个股新闻）；False：市场级快讯，每轮只采一次
    is_symbol_scoped: bool = False

    @abstractmethod
    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取情报条目。

        Args:
            symbol: 可选标的代码，个股新闻源会使用。

        Returns:
            归一化后的 IntelligenceItem 列表。
        """
