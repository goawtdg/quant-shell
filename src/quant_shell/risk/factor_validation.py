"""因子离线验证标准与报告构建。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from quant_shell.common.logging_config import get_logger
from quant_shell.risk.constants import (
    FAIL_STREAK_TO_DISABLE,
    IC_LOOKBACK_DAYS,
    IC_LONG_LOOKBACK_DAYS,
    MAX_DEGRADED_FACTORS,
    MIN_LIVE_FACTORS,
)
from quant_shell.risk.cross_section_ic import CrossSectionICResult

logger = get_logger(__name__)

MIN_MEAN_IC: Final[float] = 0.02
MIN_IR: Final[float] = 0.3
MIN_Q5_Q1_SPREAD: Final[float] = 0.0

# ETF 多标的 pooled IC 阈值（宽基 ETF 单标的时序 IC 噪声大，略放宽）
ETF_MIN_MEAN_IC: Final[float] = 0.005
ETF_MIN_IR: Final[float] = 0.15

# 验证报告超过该天数禁止作为 --apply 依据
VALIDATION_MAX_AGE_DAYS: Final[int] = 30


def parse_evaluated_at(value: object) -> datetime | None:
    """解析报告 / meta 中的 evaluated_at。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def validation_is_fresh(
    evaluated_at: object,
    *,
    max_age_days: int = VALIDATION_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> bool:
    """报告是否在新鲜度窗口内。"""
    ts = parse_evaluated_at(evaluated_at)
    if ts is None:
        return False
    age = (now or datetime.now()) - ts
    return age <= timedelta(days=max_age_days)


def ensure_fresh_for_apply(
    evaluated_at: object,
    *,
    max_age_days: int = VALIDATION_MAX_AGE_DAYS,
) -> None:
    """过期验证报告拒绝写入 registry。"""
    if validation_is_fresh(evaluated_at, max_age_days=max_age_days):
        return
    raise ValueError(
        f"validation report stale (max_age_days={max_age_days}); "
        "re-run validate_* before --apply"
    )


def warn_if_validation_stale(
    evaluated_at: object,
    *,
    scope: str,
    max_age_days: int = VALIDATION_MAX_AGE_DAYS,
) -> None:
    """加载 registry 时若验证过期则打 FACTOR_STALE 告警。"""
    if evaluated_at is None:
        return
    if validation_is_fresh(evaluated_at, max_age_days=max_age_days):
        return
    logger.warning(
        "FACTOR_STALE scope=%s evaluated_at=%s max_age_days=%d; re-run validate_* --apply",
        scope,
        evaluated_at,
        max_age_days,
    )


def verdict_from_metrics(mean_ic: float, ir: float, spread: float) -> str:
    """由 IC / IR / spread 给出 pass / review / fail。"""
    if mean_ic >= MIN_MEAN_IC and ir >= MIN_IR and spread > MIN_Q5_Q1_SPREAD:
        return "pass"
    if mean_ic <= 0 and ir <= 0:
        return "fail"
    return "review"


@dataclass(frozen=True)
class SignedMetrics:
    """最佳符号下的 IC 指标。"""

    mean_ic: float
    ir: float
    spread: float
    sign: float
    verdict: str
    verdict_raw: str


def signed_metrics(result: CrossSectionICResult) -> SignedMetrics:
    """同时评估 +IC 与 -IC，取更优方向（pass>review>fail，再比 IR、|IC|）。"""
    raw_verdict = verdict_from_metrics(
        result.mean_ic, result.ir, result.q5_q1_spread_annual
    )
    flip_ic = -result.mean_ic
    flip_ir = -result.ir
    flip_spread = -result.q5_q1_spread_annual
    flip_verdict = verdict_from_metrics(flip_ic, flip_ir, flip_spread)

    def _rank(verdict: str, ic: float, ir: float) -> tuple[int, float, float]:
        tier = {"pass": 2, "review": 1, "fail": 0}[verdict]
        return (tier, ir, abs(ic))

    if _rank(flip_verdict, flip_ic, flip_ir) > _rank(
        raw_verdict, result.mean_ic, result.ir
    ):
        return SignedMetrics(
            mean_ic=flip_ic,
            ir=flip_ir,
            spread=flip_spread,
            sign=-1.0,
            verdict=flip_verdict,
            verdict_raw=raw_verdict,
        )
    return SignedMetrics(
        mean_ic=result.mean_ic,
        ir=result.ir,
        spread=result.q5_q1_spread_annual,
        sign=1.0,
        verdict=raw_verdict,
        verdict_raw=raw_verdict,
    )


def factor_verdict(result: CrossSectionICResult) -> str:
    """单因子验证结论（最佳符号）：pass / fail / review。"""
    return signed_metrics(result).verdict


def factor_passes(result: CrossSectionICResult | None) -> bool:
    """是否全权通过离线验证（pass→active）。"""
    if result is None:
        return False
    return factor_verdict(result) == "pass"


def stock_factor_status(result: CrossSectionICResult | None) -> str:
    """单窗最佳符号 → 三态（仅测试/诊断）。

    **禁止**用于股票 ``validate_factors --apply``。
    生产写入必须走 ``stock_factor_status_with_policy`` +
    ``FactorHealthMonitor.apply_stock_gate_policy``（双窗/迟滞/Top-K）。
    """
    from quant_shell.factors.registry import FactorStatus

    if result is None:
        return FactorStatus.DISABLED.value
    verdict = factor_verdict(result)
    if verdict == "pass":
        return FactorStatus.ACTIVE.value
    if verdict == "review":
        return FactorStatus.DEGRADED.value
    return FactorStatus.DISABLED.value


def stock_factor_status_with_policy(
    short: CrossSectionICResult | None,
    long: CrossSectionICResult | None,
    *,
    previous_status: str,
    fail_streak: int,
    fail_streak_to_disable: int = FAIL_STREAK_TO_DISABLE,
) -> tuple[str, float, int]:
    """双窗 + 迟滞门禁。

    Returns:
        (status, sign, new_fail_streak)
    """
    from quant_shell.factors.registry import FactorStatus

    _ = previous_status  # 保留参数便于后续扩展「降一档」
    if short is None:
        streak = fail_streak + 1
        if streak >= fail_streak_to_disable:
            return FactorStatus.DISABLED.value, 1.0, streak
        return FactorStatus.DEGRADED.value, 1.0, streak

    short_sm = signed_metrics(short)
    long_sm = signed_metrics(long) if long is not None else short_sm

    if short_sm.verdict == "pass":
        return FactorStatus.ACTIVE.value, short_sm.sign, 0
    if short_sm.verdict == "review":
        return FactorStatus.DEGRADED.value, short_sm.sign, 0

    # 短窗 fail：长窗仍可用 → 半权保留，不累计 streak
    if long_sm.verdict != "fail":
        sign = long_sm.sign if long_sm.verdict in ("pass", "review") else short_sm.sign
        return FactorStatus.DEGRADED.value, sign, 0

    new_streak = fail_streak + 1
    if new_streak >= fail_streak_to_disable:
        return FactorStatus.DISABLED.value, short_sm.sign, new_streak
    return FactorStatus.DEGRADED.value, short_sm.sign, new_streak


def etf_factor_verdict(result: CrossSectionICResult) -> str:
    """ETF pooled IC 验证结论。"""
    if result.mean_ic >= ETF_MIN_MEAN_IC and result.ir >= ETF_MIN_IR:
        return "pass"
    if result.mean_ic <= -0.15 and result.ir <= -0.8:
        return "fail"
    return "review"


def etf_factor_passes(result: CrossSectionICResult | None) -> bool:
    """ETF 因子是否保留（pass/review 均保留，仅 fail 禁用）。"""
    if result is None:
        return False
    return etf_factor_verdict(result) != "fail"


def etf_factor_status(result: CrossSectionICResult | None) -> str:
    """ETF 因子目标状态：pass→active, review→degraded, fail→disabled。"""
    from quant_shell.factors.registry import FactorStatus

    if result is None:
        return FactorStatus.DISABLED.value
    verdict = etf_factor_verdict(result)
    if verdict == "pass":
        return FactorStatus.ACTIVE.value
    if verdict == "review":
        return FactorStatus.DEGRADED.value
    return FactorStatus.DISABLED.value


def build_validation_payload(
    *,
    universe: str,
    symbol_count: int,
    alpha_results: list[CrossSectionICResult],
    fundamental_results: list[CrossSectionICResult],
    long_results: list[CrossSectionICResult] | None = None,
    policy_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """构建 validate_factors 输出 JSON。"""
    long_by_name = {r.name: r for r in (long_results or [])}
    policy_by_name = {str(r["name"]): r for r in (policy_rows or []) if "name" in r}

    alphas: list[dict[str, object]] = []
    for r in alpha_results:
        sm = signed_metrics(r)
        long_r = long_by_name.get(r.name)
        long_sm = signed_metrics(long_r) if long_r is not None else None
        pol = policy_by_name.get(r.name, {})
        row: dict[str, object] = {
            "name": r.name,
            "mean_ic": round(r.mean_ic, 4),
            "ir": round(r.ir, 4),
            "sample_count": r.sample_count,
            "q5_q1_spread_annual": round(r.q5_q1_spread_annual, 4),
            "lookback": IC_LOOKBACK_DAYS,
            "verdict_raw": sm.verdict_raw,
            "verdict": sm.verdict,
            "sign": int(sm.sign),
            "signed_mean_ic": round(sm.mean_ic, 4),
            "signed_ir": round(sm.ir, 4),
        }
        if long_sm is not None and long_r is not None:
            row["long_lookback"] = IC_LONG_LOOKBACK_DAYS
            row["long_mean_ic"] = round(long_r.mean_ic, 4)
            row["long_ir"] = round(long_r.ir, 4)
            row["long_verdict"] = long_sm.verdict
            row["long_sign"] = int(long_sm.sign)
        if pol:
            row["fail_streak"] = pol.get("fail_streak", 0)
            row["target_status"] = pol.get("status")
        alphas.append(row)

    if policy_rows:
        active_n = sum(1 for r in policy_rows if r.get("status") == "active")
        degraded_n = sum(1 for r in policy_rows if r.get("status") == "degraded")
        disable_n = sum(1 for r in policy_rows if r.get("status") == "disabled")
    else:
        active_n = sum(1 for r in alpha_results if factor_verdict(r) == "pass")
        degraded_n = sum(1 for r in alpha_results if factor_verdict(r) == "review")
        disable_n = sum(1 for r in alpha_results if factor_verdict(r) == "fail")

    return {
        "universe": universe,
        "evaluated_at": datetime.now().isoformat(),
        "symbol_count": symbol_count,
        "lookback_short": IC_LOOKBACK_DAYS,
        "lookback_long": IC_LONG_LOOKBACK_DAYS,
        "min_live_factors": MIN_LIVE_FACTORS,
        "max_degraded_factors": MAX_DEGRADED_FACTORS,
        "fail_streak_to_disable": FAIL_STREAK_TO_DISABLE,
        "alphas": alphas,
        "fundamentals": [
            {
                "name": r.name,
                "mean_ic": round(r.mean_ic, 4),
                "ir": round(r.ir, 4),
                "q5_q1_spread_annual": round(r.q5_q1_spread_annual, 4),
            }
            for r in fundamental_results
        ],
        "recommendation": (
            f"active {active_n} / degraded {degraded_n} / disable {disable_n}"
        ),
    }


def simulate_live_floor(
    rows: list[dict[str, object]],
    *,
    min_live: int = MIN_LIVE_FACTORS,
) -> None:
    """dry-run / 报告：按 |signed IC| 模拟保底升权（与 apply_stock_gate_policy 一致）。"""
    live = sum(1 for r in rows if r.get("status") in ("active", "degraded"))
    need = min_live - live
    if need <= 0:
        return
    disabled = [r for r in rows if r.get("status") == "disabled"]
    disabled.sort(
        key=lambda r: abs(float(r.get("signed_mean_ic") or 0.0)),
        reverse=True,
    )
    for row in disabled[:need]:
        row["status"] = "degraded"
        row["fail_streak"] = 0


def simulate_degraded_trim(
    rows: list[dict[str, object]],
    *,
    max_degraded: int = MAX_DEGRADED_FACTORS,
    min_live: int = MIN_LIVE_FACTORS,
) -> None:
    """dry-run / 报告：degraded Top-K 淘汰（与 apply_stock_gate_policy 一致）。"""
    degraded = [r for r in rows if r.get("status") == "degraded"]
    if len(degraded) <= max_degraded:
        return
    degraded.sort(
        key=lambda r: (
            float(r.get("signed_ir") or 0.0),
            abs(float(r.get("signed_mean_ic") or 0.0)),
        ),
        reverse=True,
    )
    trimmed = degraded[max_degraded:]
    for row in trimmed:
        row["status"] = "disabled"

    live = sum(1 for r in rows if r.get("status") in ("active", "degraded"))
    need = min_live - live
    if need <= 0:
        return
    for row in trimmed[:need]:
        row["status"] = "degraded"
        row["fail_streak"] = 0


def postprocess_stock_policy_rows(
    rows: list[dict[str, object]],
    *,
    min_live: int = MIN_LIVE_FACTORS,
    max_degraded: int = MAX_DEGRADED_FACTORS,
) -> None:
    """统一 dry-run 后处理：先保底再 Top-K（禁止另写一套顺序）。"""
    simulate_live_floor(rows, min_live=min_live)
    simulate_degraded_trim(rows, max_degraded=max_degraded, min_live=min_live)
