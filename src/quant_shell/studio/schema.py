"""交易模型 — 前端卡片的唯一结构；用户不写 YAML / 不写插件路径。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from quant_shell.studio.catalog import catalog_public, known_factor_ids


@dataclass
class FactorPick:
    id: str
    enabled: bool = True
    weight: float = 0.2


@dataclass
class EntrySpec:
    moderate_threshold: float = 0.07
    strong_threshold: float = 0.10
    moderate_buy_scale: float = 0.5


@dataclass
class RiskSpec:
    max_drawdown: float = 0.15
    single_stock_limit: float = 0.10
    total_position_limit: float = 0.80


@dataclass
class TradingModel:
    name: str = "untitled"
    idea: str = ""
    summary: str = ""
    symbol: str = "510300"
    factors: list[FactorPick] = field(default_factory=list)
    entry: EntrySpec = field(default_factory=EntrySpec)
    risk: RiskSpec = field(default_factory=RiskSpec)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_model() -> TradingModel:
    return TradingModel(
        name="尚未设置",
        summary="还没有交易想法。在决策台写下你想怎么买卖，生成后再跑模拟盘。",
        factors=[
            FactorPick(id="momentum_20", enabled=False, weight=0.3),
            FactorPick(id="low_vol", enabled=False, weight=0.2),
            FactorPick(id="volume_ratio", enabled=False, weight=0.15),
            FactorPick(id="ma_deviation", enabled=False, weight=0.2),
            FactorPick(id="momentum_5", enabled=False, weight=0.15),
        ],
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def model_from_dict(raw: dict[str, Any]) -> TradingModel:
    """校验并裁剪到菜谱白名单；未知因子记入 notes，不执行。"""
    known = known_factor_ids()
    notes: list[str] = []
    for extra in raw.get("notes") or []:
        if extra:
            notes.append(str(extra))

    factors: list[FactorPick] = []
    seen: set[str] = set()
    for item in raw.get("factors") or []:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or "").strip()
        if not fid:
            continue
        if fid not in known:
            notes.append(f"框架暂时没有「{fid}」这种因子，已忽略。")
            continue
        if fid in seen:
            continue
        seen.add(fid)
        factors.append(
            FactorPick(
                id=fid,
                enabled=bool(item.get("enabled", True)),
                weight=_clamp(float(item.get("weight") or 0.2), 0.01, 1.0),
            )
        )
    if not factors:
        factors = empty_model().factors
        notes.append("未识别到可用因子，已放上默认的 20 日动量。")
    else:
        for item in catalog_public():
            fid = str(item["id"])
            if fid not in seen:
                factors.append(
                    FactorPick(
                        id=fid,
                        enabled=False,
                        weight=_clamp(float(item["default_weight"]), 0.01, 1.0),
                    )
                )

    entry_raw = raw.get("entry") if isinstance(raw.get("entry"), dict) else {}
    risk_raw = raw.get("risk") if isinstance(raw.get("risk"), dict) else {}
    moderate = _clamp(float(entry_raw.get("moderate_threshold") or 0.07), 0.01, 0.5)
    strong = _clamp(float(entry_raw.get("strong_threshold") or 0.10), 0.01, 0.8)
    if strong < moderate:
        strong = min(0.8, moderate + 0.02)

    symbol = str(raw.get("symbol") or "510300").strip() or "510300"
    if not symbol.isdigit() or len(symbol) != 6:
        notes.append(f"标的代码「{symbol}」不像 A 股代码，已改回 510300。")
        symbol = "510300"

    return TradingModel(
        name=str(raw.get("name") or "untitled")[:40],
        idea=str(raw.get("idea") or ""),
        summary=str(raw.get("summary") or "")[:500],
        symbol=symbol,
        factors=factors,
        entry=EntrySpec(
            moderate_threshold=moderate,
            strong_threshold=strong,
            moderate_buy_scale=_clamp(
                float(entry_raw.get("moderate_buy_scale") or 0.5), 0.1, 1.0
            ),
        ),
        risk=RiskSpec(
            max_drawdown=_clamp(float(risk_raw.get("max_drawdown") or 0.15), 0.05, 0.40),
            single_stock_limit=_clamp(
                float(risk_raw.get("single_stock_limit") or 0.10), 0.02, 0.40
            ),
            total_position_limit=_clamp(
                float(risk_raw.get("total_position_limit") or 0.80), 0.10, 1.0
            ),
        ),
        notes=notes,
    )


def studio_payload(model: TradingModel | None) -> dict[str, Any]:
    active = model or empty_model()
    return {
        "ok": True,
        "model": active.to_dict(),
        "catalog": catalog_public(),
        "active": model is not None,
    }
