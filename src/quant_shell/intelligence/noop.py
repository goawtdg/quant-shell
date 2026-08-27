"""L2 情报 — 框架默认 intel_off（中性情绪）。"""
from __future__ import annotations

import importlib
import os
from datetime import datetime

from quant_shell.common.interfaces import IntelligenceFusion
from quant_shell.common.types import MarketSnapshot, SentimentFactors


class NoopIntelligenceFusion(IntelligenceFusion):
    """无情报源：composite=0，cross_validation=0.5（中性，不制造假空头）。"""

    def analyze(self, symbol: str, market: MarketSnapshot) -> SentimentFactors:
        ts = market.timestamp if market.timestamp else datetime.now()
        return SentimentFactors(
            symbol=symbol,
            timestamp=ts,
            composite=0.0,
            cross_validation=0.5,
        )


def build_default_intelligence_fusion() -> IntelligenceFusion:
    spec = os.getenv("INTEL_MODULE", "").strip()
    if not spec:
        return NoopIntelligenceFusion()
    if ":" not in spec:
        raise ValueError(f"INTEL_MODULE must be 'module:Class', got {spec!r}")
    mod_path, _, cls_name = spec.partition(":")
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls()
