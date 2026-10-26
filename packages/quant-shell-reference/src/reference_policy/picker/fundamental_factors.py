"""第 4 层基本面因子健康报告（仅诊断，不自动 disable）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.data.fundamentals import build_universe_frame
from quant_shell.risk.cross_section_ic import CrossSectionICResult
from reference_policy.picker.factor_scorer import industry_relative_return

logger = get_logger(__name__)

_MIN_NAMES = 5
_REQUIRED_COLUMNS = (
    "symbol",
    "pe",
    "roe",
    "return_3m",
    "industry",
    "turnover_rate",
    "forward_return_5d",
)

_FUNDAMENTAL_DIR = Path("data/factor_fundamental_health")
_LATEST_PATH = _FUNDAMENTAL_DIR / "latest.json"

FUNDAMENTAL_FACTOR_NAMES: tuple[str, ...] = (
    "value_ep",
    "quality_roe",
    "momentum_3m",
    "industry_rel_momentum",
    "liquidity",
)


def evaluate_fundamentals_snapshot(frame: pd.DataFrame) -> list[CrossSectionICResult]:
    """每个因子与随后 5 日收益做一次截面 Pearson。

    只有一天的截面，信息比率没有定义。样本不够就失败，不写 0 或 1。
    """
    missing = [col for col in _REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValidationError(
            message="快照没有随后5日收益" if missing == ["forward_return_5d"] else f"快照缺少列: {', '.join(missing)}",
            suggestion="用已经走出 5 个交易日的截面，写入 forward_return_5d 后再算",
        )

    working = frame.set_index("symbol")
    forward = pd.to_numeric(working["forward_return_5d"], errors="coerce")
    pe = pd.to_numeric(working["pe"], errors="coerce")
    factors = {
        "value_ep": 1.0 / pe.where(pe > 0),
        "quality_roe": pd.to_numeric(working["roe"], errors="coerce"),
        "momentum_3m": pd.to_numeric(working["return_3m"], errors="coerce"),
        "industry_rel_momentum": industry_relative_return(frame),
        "liquidity": pd.to_numeric(working["turnover_rate"], errors="coerce"),
    }

    results: list[CrossSectionICResult] = []
    for name in FUNDAMENTAL_FACTOR_NAMES:
        paired = pd.DataFrame({"factor": factors[name], "forward": forward}).dropna()
        if (
            len(paired) < _MIN_NAMES
            or float(paired["factor"].std()) == 0
            or float(paired["forward"].std()) == 0
        ):
            raise ValidationError(
                message=f"{name} 与随后5日收益的有效样本不足，当前 {len(paired)}",
                suggestion="样本少于 5 只或没有波动时不要写 IC",
            )
        ic = float(paired["factor"].corr(paired["forward"]))
        if ic != ic:
            raise ValidationError(
                message=f"{name} 的截面相关系数不是数字",
                suggestion="检查因子和随后5日收益是否为常数",
            )
        results.append(
            CrossSectionICResult(
                name=name,
                mean_ic=ic,
                ir=float("nan"),
                sample_count=len(paired),
                q5_q1_spread_annual=float("nan"),
            )
        )
    return results


def save_fundamental_health_report(
    results: list[CrossSectionICResult],
    *,
    universe: str,
    symbol_count: int,
) -> Path:
    """持久化基本面因子健康报告。"""
    _FUNDAMENTAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "universe": universe,
        "evaluated_at": datetime.now().isoformat(),
        "symbol_count": symbol_count,
        "factors": [
            {
                "name": r.name,
                "mean_ic": _json_float(r.mean_ic),
                "ir": _json_float(r.ir),
                "sample_count": r.sample_count,
                "q5_q1_spread_annual": _json_float(r.q5_q1_spread_annual),
            }
            for r in results
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _LATEST_PATH.write_text(text, encoding="utf-8")
    logger.info("save_fundamental_health path=%s factors=%d", _LATEST_PATH, len(results))
    return _LATEST_PATH


def _json_float(value: float) -> float | None:
    number = float(value)
    if number != number:
        return None
    return round(number, 4)


def refresh_fundamental_health_report(
    universe: str,
    symbols: list[str],
    *,
    max_symbols: int | None = None,
    frame: pd.DataFrame | None = None,
    skip_industry: bool = False,
) -> list[CrossSectionICResult]:
    """拉取 universe 基本面并写入基本面因子健康报告。"""
    data = frame if frame is not None else build_universe_frame(
        symbols,
        max_symbols=max_symbols,
        skip_industry=skip_industry,
    )
    results = evaluate_fundamentals_snapshot(data)
    save_fundamental_health_report(
        results,
        universe=universe,
        symbol_count=len(data),
    )
    return results
