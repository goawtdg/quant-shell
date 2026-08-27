"""PE 分位数据质量 — 唯一结构 PeResolution；门控只认 reliable。"""
from __future__ import annotations

from dataclasses import dataclass

from quant_shell.common.types import MarketSnapshot

PE_SOURCE_STOCK_HIST: str = "stock_value_em_hist"
PE_SOURCE_ETF_LEGULEGU: str = "legulegu_index"
PE_SOURCE_FALLBACK_PROXY: str = "pe_over_200_proxy"
PE_SOURCE_FALLBACK_ETF_UNMAPPED: str = "default_neutral_unmapped"


@dataclass(frozen=True)
class PeResolution:
    """PE 分位唯一解析结果。中性 0.5 + reliable=False 不得参与估值门控。"""

    source: str
    percentile: float
    reliable: bool
    reason: str = ""
    pe_ttm: float | None = None
    pe_proxy_over_200: float | None = None

    def as_extra(self) -> dict[str, object]:
        extra: dict[str, object] = {
            "pe_percentile_source": self.source,
            "pe_reliable": self.reliable,
        }
        if self.reason:
            extra["pe_unreliable_reason"] = self.reason
        if self.pe_ttm is not None:
            extra["pe_ttm"] = self.pe_ttm
        if self.pe_proxy_over_200 is not None:
            extra["pe_proxy_over_200"] = self.pe_proxy_over_200
        return extra


def is_pe_percentile_reliable(market: MarketSnapshot | None) -> bool:
    """只认 extra.pe_reliable；缺省视为不可靠。"""
    if market is None:
        return False
    return bool((market.extra or {}).get("pe_reliable") is True)


def pe_unreliable_reason(market: MarketSnapshot | None) -> str:
    """人类可读不可靠说明；可靠时返回空串。"""
    if market is None or is_pe_percentile_reliable(market):
        return ""
    extra = market.extra or {}
    reason = str(extra.get("pe_unreliable_reason", "") or "").strip()
    source = str(extra.get("pe_percentile_source", "") or "")
    proxy = extra.get("pe_proxy_over_200")
    bits = [f"PE分位不可靠[{source or 'missing'}]"]
    if proxy is not None:
        bits.append(f"proxy={float(proxy):.2%}(仅诊断,未参与决策)")
    if reason:
        bits.append(reason)
    bits.append("估值加减分/PE止盈已禁用")
    return "; ".join(bits)


def pe_fallback_reason(market: MarketSnapshot | None) -> str:
    """兼容旧调用名；语义等同 pe_unreliable_reason。"""
    return pe_unreliable_reason(market)
