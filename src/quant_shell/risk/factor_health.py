"""因子健康监控 — IC 评估 + 注册表状态更新（ETF 时序 / 股票截面）。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import FactorHealthReport, FactorICRecord
from quant_shell.risk.factor_ops import (
    evaluate_etf_alpha_pooled,
    fetch_symbol_ohlcv_map,
)
from quant_shell.factors.registry import FactorRegistry, FactorStatus
from quant_shell.risk.constants import (
    FAIL_STREAK_TO_DISABLE,
    IC_DEGRADED_THRESHOLD,
    IC_DISABLED_THRESHOLD,
    IC_RECOVERY_THRESHOLD,
    MAX_DEGRADED_FACTORS,
    MIN_LIVE_FACTORS,
)
from quant_shell.risk.cross_section_ic import (
    CrossSectionICResult,
    evaluate_registry_cross_section,
)
from quant_shell.risk.factor_validation import (
    signed_metrics,
    stock_factor_status_with_policy,
)
from quant_shell.factors.state_store import (
    FactorScope,
    build_stock_meta,
    load_registry,
    load_registry_meta,
    save_registry_state,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class StatusTransition:
    """因子状态迁移。"""

    name: str
    previous: FactorStatus
    current: FactorStatus


class FactorHealthMonitor:
    """滚动 IC 监控，自动降级/禁用失效因子。"""

    def __init__(
        self,
        registry: FactorRegistry | None = None,
        scope: FactorScope = "etf",
    ) -> None:
        self._scope = scope
        self._registry = registry or load_registry(scope=scope)

    @property
    def registry(self) -> FactorRegistry:
        """当前因子注册表。"""
        return self._registry

    @property
    def scope(self) -> FactorScope:
        """监控 scope（etf / stock）。"""
        return self._scope

    def evaluate_cross_section(
        self,
        symbols: list[str],
        *,
        universe: str = "csi300",
        persist: bool = True,
        max_symbols: int | None = None,
    ) -> FactorHealthReport:
        """股票截面 IC 评估并更新 stock registry。"""
        subset = symbols[:max_symbols] if max_symbols else symbols
        symbol_ohlcv = fetch_symbol_ohlcv_map(subset)

        ic_results = evaluate_registry_cross_section(symbol_ohlcv, self._registry)
        return self._apply_ic_results(
            ic_results,
            symbol=universe,
            persist=persist,
            universe=universe,
            symbol_count=len(symbol_ohlcv),
        )

    def apply_validation_results(
        self,
        ic_results: list[CrossSectionICResult],
        *,
        universe: str = "csi300",
        symbol_count: int = 0,
        persist: bool = True,
        pass_fn: Callable[[CrossSectionICResult | None], bool] | None = None,
        status_fn: Callable[[CrossSectionICResult | None], str] | None = None,
    ) -> FactorHealthReport:
        """根据离线验证结果更新 registry（validate_factors --apply）。"""
        return self._apply_ic_results(
            ic_results,
            symbol=universe,
            persist=persist,
            universe=universe,
            symbol_count=symbol_count,
            pass_fn=pass_fn,
            status_fn=status_fn,
        )

    def apply_stock_gate_policy(
        self,
        short_results: list[CrossSectionICResult],
        long_results: list[CrossSectionICResult],
        *,
        universe: str = "csi300",
        symbol_count: int = 0,
        persist: bool = True,
        prior_fail_streak: dict[str, int] | None = None,
        min_live: int = MIN_LIVE_FACTORS,
        fail_streak_to_disable: int = FAIL_STREAK_TO_DISABLE,
    ) -> tuple[FactorHealthReport, list[dict[str, object]]]:
        """双窗符号自适应 + 迟滞 + 存活保底（股票 validate --apply）。"""
        short_by = {r.name: r for r in short_results}
        long_by = {r.name: r for r in long_results}
        if prior_fail_streak is None:
            meta = load_registry_meta(scope=self._scope) if self._scope == "stock" else {}
            raw_streak = meta.get("fail_streak") if isinstance(meta, dict) else {}
            prior_fail_streak = (
                {str(k): int(v) for k, v in raw_streak.items()}
                if isinstance(raw_streak, dict)
                else {}
            )

        transitions: list[StatusTransition] = []
        policy_rows: list[dict[str, object]] = []
        mean_ic_map: dict[str, float] = {}
        signs: dict[str, int] = {}
        fail_streak_out: dict[str, int] = {}

        for spec in self._registry.all_specs():
            previous = spec.status
            short = short_by.get(spec.name)
            long = long_by.get(spec.name)
            streak_in = int(prior_fail_streak.get(spec.name, 0))
            status_s, sign, streak_out = stock_factor_status_with_policy(
                short,
                long,
                previous_status=previous.value,
                fail_streak=streak_in,
                fail_streak_to_disable=fail_streak_to_disable,
            )
            new_status = FactorStatus(status_s)
            mean_ic_map[spec.name] = short.mean_ic if short is not None else 0.0
            signs[spec.name] = int(sign)
            fail_streak_out[spec.name] = int(streak_out)

            if new_status != previous:
                self._registry.set_status(spec.name, new_status)
                transitions.append(StatusTransition(spec.name, previous, new_status))
            self._registry.set_sign(spec.name, sign)

            sm = signed_metrics(short) if short is not None else None
            policy_rows.append(
                {
                    "name": spec.name,
                    "status": new_status.value,
                    "sign": int(sign),
                    "fail_streak": int(streak_out),
                    "signed_mean_ic": sm.mean_ic if sm else 0.0,
                    "signed_ir": sm.ir if sm else 0.0,
                    "verdict": sm.verdict if sm else "fail",
                }
            )

        promoted = self._ensure_live_floor(
            short_by,
            signs=signs,
            fail_streak_out=fail_streak_out,
            policy_rows=policy_rows,
            min_live=min_live,
        )
        if promoted:
            logger.info("FACTOR_FLOOR promoted=%s", ",".join(promoted))

        trimmed = self._trim_degraded_pool(
            short_by,
            signs=signs,
            fail_streak_out=fail_streak_out,
            policy_rows=policy_rows,
            max_degraded=MAX_DEGRADED_FACTORS,
            min_live=min_live,
        )
        if trimmed:
            logger.info("FACTOR_TRIM degraded_cut=%s", ",".join(trimmed))

        action_by_name = {
            t.name: self._action_label(t.previous, t.current) for t in transitions
        }
        records: list[FactorICRecord] = []
        for row in policy_rows:
            name = str(row["name"])
            short = short_by.get(name)
            if name in promoted:
                action = "floor_promoted"
            elif name in trimmed:
                action = "degraded_trimmed"
            else:
                action = action_by_name.get(name, "kept")
            records.append(
                FactorICRecord(
                    name=name,
                    mean_ic=float(mean_ic_map.get(name, 0.0)),
                    ir=float(short.ir) if short is not None else 0.0,
                    sample_count=int(short.sample_count) if short is not None else 0,
                    status=str(row["status"]),
                    action=action,
                )
            )

        if persist:
            meta = build_stock_meta(
                universe=universe,
                symbol_count=symbol_count,
                mean_ic=mean_ic_map,
                signs=signs,
                fail_streak=fail_streak_out,
            )
            save_registry_state(self._registry, scope=self._scope, meta=meta)

        return self._build_report(records, universe), policy_rows

    def _ensure_live_floor(
        self,
        short_by: dict[str, CrossSectionICResult],
        *,
        signs: dict[str, int],
        fail_streak_out: dict[str, int],
        policy_rows: list[dict[str, object]],
        min_live: int,
    ) -> list[str]:
        """若 live < min_live，按 |signed IC| 从 disabled 升至 degraded。"""
        live = [
            s
            for s in self._registry.all_specs()
            if s.status != FactorStatus.DISABLED
        ]
        need = min_live - len(live)
        if need <= 0:
            return []

        candidates: list[tuple[float, str, float]] = []
        for spec in self._registry.all_specs():
            if spec.status != FactorStatus.DISABLED:
                continue
            short = short_by.get(spec.name)
            if short is None:
                continue
            sm = signed_metrics(short)
            candidates.append((abs(sm.mean_ic), spec.name, sm.sign))
        candidates.sort(reverse=True)

        promoted: list[str] = []
        row_by = {str(r["name"]): r for r in policy_rows}
        for _abs_ic, name, sign in candidates:
            if len(promoted) >= need:
                break
            self._registry.set_status(name, FactorStatus.DEGRADED)
            self._registry.set_sign(name, sign)
            signs[name] = int(sign)
            fail_streak_out[name] = 0
            if name in row_by:
                row_by[name]["status"] = FactorStatus.DEGRADED.value
                row_by[name]["sign"] = int(sign)
                row_by[name]["fail_streak"] = 0
            promoted.append(name)
        return promoted

    def _trim_degraded_pool(
        self,
        short_by: dict[str, CrossSectionICResult],
        *,
        signs: dict[str, int],
        fail_streak_out: dict[str, int],
        policy_rows: list[dict[str, object]],
        max_degraded: int,
        min_live: int,
    ) -> list[str]:
        """degraded 超出上限时按 signed IR 淘汰；若 live 不足再回补。"""
        row_by = {str(r["name"]): r for r in policy_rows}
        degraded_specs = [
            s for s in self._registry.all_specs() if s.status == FactorStatus.DEGRADED
        ]
        if len(degraded_specs) <= max_degraded:
            return []

        ranked: list[tuple[float, float, str]] = []
        for spec in degraded_specs:
            row = row_by.get(spec.name, {})
            signed_ir = float(row.get("signed_ir") or 0.0)
            signed_ic = float(row.get("signed_mean_ic") or 0.0)
            if spec.name in short_by and "signed_ir" not in row:
                sm = signed_metrics(short_by[spec.name])
                signed_ir, signed_ic = sm.ir, sm.mean_ic
            ranked.append((signed_ir, abs(signed_ic), spec.name))
        ranked.sort(reverse=True)

        keep = {name for _, _, name in ranked[:max_degraded]}
        trimmed: list[str] = []
        for _ir, _ic, name in ranked[max_degraded:]:
            if name in keep:
                continue
            self._registry.set_status(name, FactorStatus.DISABLED)
            if name in row_by:
                row_by[name]["status"] = FactorStatus.DISABLED.value
            trimmed.append(name)

        # trim 后若 live < min_live，从刚裁掉的按 IR 回补
        live_n = sum(
            1 for s in self._registry.all_specs() if s.status != FactorStatus.DISABLED
        )
        need = min_live - live_n
        if need > 0 and trimmed:
            restore_ranked = [
                (signed_ir, abs_ic, name)
                for signed_ir, abs_ic, name in ranked
                if name in trimmed
            ]
            restored: list[str] = []
            for _ir, _ic, name in restore_ranked:
                if len(restored) >= need:
                    break
                short = short_by.get(name)
                sm = signed_metrics(short) if short is not None else None
                sign = float(sm.sign) if sm else float(signs.get(name, 1))
                self._registry.set_status(name, FactorStatus.DEGRADED)
                self._registry.set_sign(name, sign)
                signs[name] = int(sign)
                fail_streak_out[name] = 0
                if name in row_by:
                    row_by[name]["status"] = FactorStatus.DEGRADED.value
                    row_by[name]["sign"] = int(sign)
                    row_by[name]["fail_streak"] = 0
                restored.append(name)
                trimmed.remove(name)
            if restored:
                logger.info("FACTOR_TRIM restored_for_floor=%s", ",".join(restored))

        return trimmed

    def evaluate_etf_pooled(
        self,
        symbols: list[str] | None = None,
        *,
        max_etfs: int = 20,
        persist: bool = True,
    ) -> FactorHealthReport:
        """多 ETF pooled 时序 IC（运维/验证专用）。"""
        from quant_shell.risk.factor_validation import etf_factor_status

        ic_results, panels = evaluate_etf_alpha_pooled(
            symbols,
            self._registry,
            max_etfs=max_etfs,
        )
        return self._apply_ic_results(
            ic_results,
            symbol="etf_pool",
            persist=persist,
            universe="etf",
            symbol_count=len(panels),
            status_fn=etf_factor_status,
        )

    def report_registry_state(self, symbol: str = "") -> FactorHealthReport:
        """仅报告当前 registry 状态，不重新计算 IC。"""
        records = [
            FactorICRecord(
                name=spec.name,
                mean_ic=0.0,
                ir=0.0,
                sample_count=0,
                status=spec.status.value,
                action="kept",
            )
            for spec in self._registry.all_specs()
        ]
        return self._build_report(records, symbol)

    def _apply_ic_results(
        self,
        ic_results: list[CrossSectionICResult],
        *,
        symbol: str,
        persist: bool,
        universe: str,
        symbol_count: int,
        pass_fn: Callable[[CrossSectionICResult | None], bool] | None = None,
        status_fn: Callable[[CrossSectionICResult | None], str] | None = None,
    ) -> FactorHealthReport:
        records: list[FactorICRecord] = []
        transitions: list[StatusTransition] = []
        mean_ic_map: dict[str, float] = {}
        allow_gradient = persist and status_fn is None and pass_fn is None
        if allow_gradient and self._scope == "stock":
            logger.warning(
                "stock registry write blocked; use validate_factors.py --apply"
            )
            allow_gradient = False

        ic_by_name = {r.name: r for r in ic_results}
        for spec in self._registry.all_specs():
            previous = spec.status
            result = ic_by_name.get(spec.name)
            if result is None:
                mean_ic, ir, samples = 0.0, 0.0, 0
            else:
                mean_ic = result.mean_ic
                ir = result.ir
                samples = result.sample_count
            mean_ic_map[spec.name] = mean_ic

            if status_fn is not None:
                new_status = FactorStatus(status_fn(result))
            elif pass_fn is not None:
                new_status = (
                    FactorStatus.ACTIVE if pass_fn(result) else FactorStatus.DISABLED
                ) if result else FactorStatus.DISABLED
            elif allow_gradient:
                new_status = self._decide_status(mean_ic, previous)
            else:
                new_status = previous

            if new_status != previous and (status_fn is not None or pass_fn is not None or allow_gradient):
                self._registry.set_status(spec.name, new_status)
                transitions.append(StatusTransition(spec.name, previous, new_status))

            records.append(
                FactorICRecord(
                    name=spec.name,
                    mean_ic=mean_ic,
                    ir=ir,
                    sample_count=samples,
                    status=new_status.value,
                    action=self._action_label(previous, new_status),
                )
            )
        if persist and (transitions or pass_fn is not None or status_fn is not None):
            meta = build_stock_meta(
                universe=universe,
                symbol_count=symbol_count,
                mean_ic=mean_ic_map,
            )
            save_registry_state(self._registry, scope=self._scope, meta=meta)

        return self._build_report(records, symbol)

    def _build_report(
        self,
        records: list[FactorICRecord],
        symbol: str,
    ) -> FactorHealthReport:
        disabled = sum(1 for r in records if r.status == FactorStatus.DISABLED.value)
        degraded = sum(1 for r in records if r.status == FactorStatus.DEGRADED.value)
        active = len(records) - disabled - degraded
        usable = active + degraded
        coverage = self._coverage_from_registry()
        logger.info(
            "FactorHealthMonitor scope=%s symbol=%s active=%d degraded=%d "
            "disabled=%d usable=%d coverage=%.3f",
            self._scope,
            symbol,
            active,
            degraded,
            disabled,
            usable,
            coverage,
        )
        return FactorHealthReport(
            symbol=symbol,
            timestamp=datetime.now(),
            factors=records,
            degraded_count=degraded,
            disabled_count=disabled,
            active_count=active,
            usable_count=usable,
            coverage=coverage,
            scope=self._scope,
        )

    def _coverage_from_registry(self) -> float:
        """可用因子有效权重 / 名义权重（disabled 不计入分母）。"""
        usable_specs = [
            s for s in self._registry.all_specs() if s.status != FactorStatus.DISABLED
        ]
        total_weight = sum(s.weight for s in usable_specs)
        if total_weight <= 0:
            return 0.0
        effective = sum(FactorRegistry.effective_weight(s) for s in usable_specs)
        return float(effective / total_weight)

    def _decide_status(self, mean_ic: float, current: FactorStatus) -> FactorStatus:
        """根据 IC 均值决定因子状态。"""
        if mean_ic <= IC_DISABLED_THRESHOLD:
            return FactorStatus.DISABLED
        if mean_ic < IC_DEGRADED_THRESHOLD:
            return FactorStatus.DEGRADED
        if current == FactorStatus.DEGRADED and mean_ic < IC_RECOVERY_THRESHOLD:
            return FactorStatus.DEGRADED
        return FactorStatus.ACTIVE

    @staticmethod
    def _action_label(previous: FactorStatus, current: FactorStatus) -> str:
        """状态变更动作标签。"""
        if previous == current:
            return "kept"
        if current == FactorStatus.DISABLED:
            return "disabled"
        if current == FactorStatus.DEGRADED:
            return "degraded"
        return "recovered"
