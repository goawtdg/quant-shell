"""全局配置 — 从 .env / 环境变量读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from quant_shell.config.env_loader import load_env_file


def _env_str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """系统配置。"""

    # 标的与监控
    default_symbol: str = "510300"
    monitor_symbols: str = "510300"
    monitor_interval_min: int = 60

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_sec: int = 90
    deepseek_enabled: bool = True

    # L5 风控（组合/入场门控；单票 hold 清仓见 hold_exit_dd_*）
    max_drawdown: float = 0.15
    portfolio_max_drawdown: float = 0.15
    single_stock_limit: float = 0.10
    total_position_limit: float = 0.80
    kelly_cap: float = 0.30
    risk_free_rate: float = 0.03

    # 单票 hold 清仓：大 A 波动自适应（默认比固定 15% 更宽）
    hold_exit_dd_k: float = 1.75
    hold_exit_dd_window_days: int = 60
    hold_exit_dd_floor: float = 0.18
    hold_exit_dd_ceiling: float = 0.28

    # 模拟盘（L6 纸面交易，非实盘）
    paper_initial_cash: float = 1_000_000.0
    paper_commission_rate: float = 0.0003
    paper_min_trade_value: float = 1000.0
    paper_auto_approve: bool = True
    paper_reduce_fraction: float = 0.5
    reentry_cooldown_days: int = 1
    # 全市场现货缓存 TTL（秒）：盯市批量复用；网络慢时不宜过短
    spot_cache_ttl_sec: float = 600.0
    # 收盘后日 K 滞后宽限（HH:MM）：此前软降级，此后硬失败禁止假成功
    ohlcv_lag_hard_after: str = "18:30"
    # 截面选股基本面采集并发（单票行情+日 K）；过大易触发限流
    universe_fetch_workers: int = 8
    # 情报源并行数；市场快讯每轮只采一次
    intel_source_workers: int = 4
    # hold 规则已决断（止盈/止损/纪律）时跳过 L7 DeepSeek
    hold_skip_llm_if_rule_resolved: bool = True

    # 全链路联动
    linkage_stock_top_n: int = 5
    linkage_reeval_holdings: bool = True
    # 因子健康画像：按可用质量门控（非禁用个数）
    factor_min_usable: int = 4
    factor_min_active: int = 3
    factor_green_min_usable: int = 6
    factor_min_coverage: float = 0.70
    factor_coverage_scale_floor: float = 0.35
    intel_cache_max_age_min: int = 120
    linkage_intel_prefetch_stocks: bool = True
    linkage_skip_industry_fetch: bool = False
    pick_refresh_fundamental_health: bool = False
    pick_universe: str = "csi300"
    pick_max_symbols: int = 0
    # 选股/入场剔除创业板、科创板、北交所等有账户门槛标的
    pick_filter_board_permission: bool = True
    # 仅影响 L3 均线周期 profile，不参与开平仓路由
    investment_mode: str = "long_term"

    # 策略袖套政策（L4 policy 唯一读取）
    core_pe_block_percentile: float = 0.85
    core_min_hold_days: int = 5
    theme_swing_enabled: bool = True
    theme_max_position: float = 0.05
    theme_sleeve_budget: float = 0.15
    theme_max_hold_days: int = 8
    theme_exit_dd: float = 0.12
    theme_min_sentiment: float = 0.25
    theme_min_signal_conf: float = 0.45

    # 估值体制 blend（L3）与止盈（L4）
    pe_undervalue_blend: float = 0.35
    pe_overvalue_blend: float = 0.65
    take_profit_partial_pct: float = 0.12
    take_profit_scale_pct: float = 0.25
    take_profit_full_pct: float = 0.40
    take_profit_trail_pct: float = 0.08
    take_profit_pe_rich: float = 0.70
    take_profit_pe_exit: float = 0.85

    # L3/L7 信号门槛（运行时以 settings 为准；constants 仅作默认值）
    signal_threshold_moderate: float = 0.07
    signal_threshold_strong: float = 0.10
    signal_moderate_buy_scale: float = 0.5
    # 实盘/近窗夏普相对回测偏离低于该值 → STRATEGY_DEGRADED
    strategy_degradation_threshold: float = -0.30
    # 入场遇 STRATEGY_DEGRADED 时仓位缩放（不再硬 WAIT；hold 仍 REDUCE）
    strategy_degraded_entry_scale: float = 0.5
    # True：持仓遇 STRATEGY_DEGRADED 时 HOLD/BUY→REDUCE；False 仅标记不改动作（消融用）
    strategy_degraded_hold_tighten: bool = True
    # 持仓未满该日数时，不因 STRATEGY_DEGRADED 强制 REDUCE（0=立即收紧，生产默认）
    strategy_degraded_hold_min_days: int = 0
    # True：持仓 DEGRADED 仅当 unrealized_pnl<0 才 REDUCE（消融用，默认关）
    strategy_degraded_hold_reduce_only_if_loss: bool = False
    # True：ETF_BETA 持仓遇 STRATEGY_DEGRADED 仍 REDUCE；False 仅标记（P4.ETF e1 消融）
    strategy_degraded_etf_hold_tighten: bool = True
    # True：持仓 REDUCE 用组合 Sharpe 偏离；False 用标的偏离（P4.hold_semantic_A）
    strategy_degraded_hold_use_portfolio_deviation: bool = False
    # True：DEGRADED 持仓 REDUCE 仅 range/bear；bull 豁免（P4.hold_semantic_B）
    strategy_degraded_hold_regime_gated: bool = False

    # L3 融合权重（默认与 constants 一致；消融经 env 覆盖）
    signal_weight_math: float = 0.40
    signal_weight_sentiment: float = 0.35
    signal_weight_intelligence: float = 0.25
    tech_weight_in_math: float = 0.45
    alpha_weight_in_math: float = 0.55
    # True：sentiment/intel 绝对值均 < eps 时，将剩余权重量归一到 math（intel_off 检验）
    fusion_renormalize_inactive: bool = False

    # 因子双轨 IC（registry 仅由 validate_* --apply 写入）
    paper_relax_factor_gate: bool = False
    # 模拟盘：一般 human_review（非黑天鹅/HUMAN_ONLY）不硬拦 BUY
    paper_relax_intel_review: bool = True

    # 网络（可选，AkShare / 情报源走 requests Session）
    disable_proxy: bool = False
    http_proxy: str = ""
    https_proxy: str = ""

    @property
    def monitor_symbol_list(self) -> list[str]:
        """监控标的列表。"""
        return [s.strip() for s in self.monitor_symbols.split(",") if s.strip()]

    @property
    def has_deepseek(self) -> bool:
        """是否配置了 DeepSeek Key 且启用。"""
        return self.deepseek_enabled and bool(self.deepseek_api_key)

    @property
    def pick_max_symbols_resolved(self) -> int | None:
        """0 表示全量扫描 universe 成分。"""
        return None if self.pick_max_symbols == 0 else self.pick_max_symbols


def load_settings() -> Settings:
    """读取 .env 后构建 Settings。"""
    load_env_file()
    s = Settings(
        default_symbol=_env_str("DEFAULT_SYMBOL", "510300"),
        monitor_symbols=_env_str("MONITOR_SYMBOLS", _env_str("DEFAULT_SYMBOL", "510300")),
        monitor_interval_min=_env_int("MONITOR_INTERVAL_MIN", 60),
        deepseek_api_key=_env_str("DEEPSEEK_API_KEY"),
        deepseek_base_url=_env_str("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=_env_str("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        deepseek_timeout_sec=_env_int("DEEPSEEK_TIMEOUT_SEC", 90),
        deepseek_enabled=_env_bool("DEEPSEEK_ENABLED", True),
        max_drawdown=_env_float("MAX_DRAWDOWN", 0.15),
        portfolio_max_drawdown=_env_float("PORTFOLIO_MAX_DRAWDOWN", 0.15),
        single_stock_limit=_env_float("SINGLE_STOCK_LIMIT", 0.10),
        total_position_limit=_env_float("TOTAL_POSITION_LIMIT", 0.80),
        kelly_cap=_env_float("KELLY_CAP", 0.30),
        risk_free_rate=_env_float("RISK_FREE_RATE", 0.03),
        hold_exit_dd_k=_env_float("HOLD_EXIT_DD_K", 1.75),
        hold_exit_dd_window_days=_env_int("HOLD_EXIT_DD_WINDOW_DAYS", 60),
        hold_exit_dd_floor=_env_float("HOLD_EXIT_DD_FLOOR", 0.18),
        hold_exit_dd_ceiling=_env_float("HOLD_EXIT_DD_CEILING", 0.28),
        paper_initial_cash=_env_float("PAPER_INITIAL_CASH", 1_000_000.0),
        paper_commission_rate=_env_float("PAPER_COMMISSION_RATE", 0.0003),
        paper_min_trade_value=_env_float("PAPER_MIN_TRADE_VALUE", 1000.0),
        paper_auto_approve=_env_bool("PAPER_AUTO_APPROVE", True),
        paper_reduce_fraction=_env_float("PAPER_REDUCE_FRACTION", 0.5),
        reentry_cooldown_days=_env_int("REENTRY_COOLDOWN_DAYS", 1),
        spot_cache_ttl_sec=_env_float("SPOT_CACHE_TTL_SEC", 600.0),
        ohlcv_lag_hard_after=_env_str("OHLCV_LAG_HARD_AFTER", "18:30"),
        universe_fetch_workers=_env_int("UNIVERSE_FETCH_WORKERS", 8),
        intel_source_workers=_env_int("INTEL_SOURCE_WORKERS", 4),
        hold_skip_llm_if_rule_resolved=_env_bool("HOLD_SKIP_LLM_IF_RULE_RESOLVED", True),
        linkage_stock_top_n=_env_int("LINKAGE_STOCK_TOP_N", 5),
        linkage_reeval_holdings=_env_bool("LINKAGE_REEVAL_HOLDINGS", True),
        factor_min_usable=_env_int("FACTOR_MIN_USABLE", 4),
        factor_min_active=_env_int("FACTOR_MIN_ACTIVE", 3),
        factor_green_min_usable=_env_int("FACTOR_GREEN_MIN_USABLE", 6),
        factor_min_coverage=_env_float("FACTOR_MIN_COVERAGE", 0.70),
        factor_coverage_scale_floor=_env_float("FACTOR_COVERAGE_SCALE_FLOOR", 0.35),
        intel_cache_max_age_min=_env_int("INTEL_CACHE_MAX_AGE_MIN", 120),
        linkage_intel_prefetch_stocks=_env_bool("LINKAGE_INTEL_PREFETCH_STOCKS", True),
        linkage_skip_industry_fetch=_env_bool("LINKAGE_SKIP_INDUSTRY_FETCH", False),
        pick_refresh_fundamental_health=_env_bool("PICK_REFRESH_FUNDAMENTAL_HEALTH", False),
        pick_universe=_env_str("PICK_UNIVERSE", "csi300"),
        pick_max_symbols=_env_int("PICK_MAX_SYMBOLS", 0),
        pick_filter_board_permission=_env_bool("PICK_FILTER_BOARD_PERMISSION", True),
        investment_mode=_env_str("INVESTMENT_MODE", "long_term"),
        core_pe_block_percentile=_env_float("CORE_PE_BLOCK_PERCENTILE", 0.85),
        core_min_hold_days=_env_int("CORE_MIN_HOLD_DAYS", 5),
        theme_swing_enabled=_env_bool("THEME_SWING_ENABLED", True),
        theme_max_position=_env_float("THEME_MAX_POSITION", 0.05),
        theme_sleeve_budget=_env_float("THEME_SLEEVE_BUDGET", 0.15),
        theme_max_hold_days=_env_int("THEME_MAX_HOLD_DAYS", 8),
        theme_exit_dd=_env_float("THEME_EXIT_DD", 0.12),
        theme_min_sentiment=_env_float("THEME_MIN_SENTIMENT", 0.25),
        theme_min_signal_conf=_env_float("THEME_MIN_SIGNAL_CONF", 0.45),
        pe_undervalue_blend=_env_float("PE_UNDERVALUE_BLEND", 0.35),
        pe_overvalue_blend=_env_float("PE_OVERVALUE_BLEND", 0.65),
        take_profit_partial_pct=_env_float("TAKE_PROFIT_PARTIAL_PCT", 0.12),
        take_profit_scale_pct=_env_float("TAKE_PROFIT_SCALE_PCT", 0.25),
        take_profit_full_pct=_env_float("TAKE_PROFIT_FULL_PCT", 0.40),
        take_profit_trail_pct=_env_float("TAKE_PROFIT_TRAIL_PCT", 0.08),
        take_profit_pe_rich=_env_float("TAKE_PROFIT_PE_RICH", 0.70),
        take_profit_pe_exit=_env_float("TAKE_PROFIT_PE_EXIT", 0.85),
        signal_threshold_moderate=_env_float("SIGNAL_THRESHOLD_MODERATE", 0.07),
        signal_threshold_strong=_env_float("SIGNAL_THRESHOLD_STRONG", 0.10),
        signal_moderate_buy_scale=_env_float("SIGNAL_MODERATE_BUY_SCALE", 0.5),
        strategy_degradation_threshold=_env_float(
            "STRATEGY_DEGRADATION_THRESHOLD", -0.30
        ),
        strategy_degraded_entry_scale=_env_float(
            "STRATEGY_DEGRADED_ENTRY_SCALE", 0.5
        ),
        strategy_degraded_hold_tighten=_env_bool(
            "STRATEGY_DEGRADED_HOLD_TIGHTEN", True
        ),
        strategy_degraded_hold_min_days=_env_int(
            "STRATEGY_DEGRADED_HOLD_MIN_DAYS", 0
        ),
        strategy_degraded_hold_reduce_only_if_loss=_env_bool(
            "STRATEGY_DEGRADED_HOLD_REDUCE_ONLY_IF_LOSS", False
        ),
        strategy_degraded_etf_hold_tighten=_env_bool(
            "STRATEGY_DEGRADED_ETF_HOLD_TIGHTEN", True
        ),
        strategy_degraded_hold_use_portfolio_deviation=_env_bool(
            "STRATEGY_DEGRADED_HOLD_USE_PORTFOLIO_DEVIATION", False
        ),
        strategy_degraded_hold_regime_gated=_env_bool(
            "STRATEGY_DEGRADED_HOLD_REGIME_GATED", False
        ),
        signal_weight_math=_env_float("SIGNAL_WEIGHT_MATH", 0.40),
        signal_weight_sentiment=_env_float("SIGNAL_WEIGHT_SENTIMENT", 0.35),
        signal_weight_intelligence=_env_float("SIGNAL_WEIGHT_INTELLIGENCE", 0.25),
        tech_weight_in_math=_env_float("TECH_WEIGHT_IN_MATH", 0.45),
        alpha_weight_in_math=_env_float("ALPHA_WEIGHT_IN_MATH", 0.55),
        fusion_renormalize_inactive=_env_bool("FUSION_RENORMALIZE_INACTIVE", False),
        paper_relax_factor_gate=_env_bool("PAPER_RELAX_FACTOR_GATE", False),
        paper_relax_intel_review=_env_bool("PAPER_RELAX_INTEL_REVIEW", True),
        disable_proxy=_env_bool("DISABLE_PROXY", False),
        http_proxy=_env_str("HTTP_PROXY"),
        https_proxy=_env_str("HTTPS_PROXY"),
    )
    _apply_proxy(s)
    return s


_PROXY_ENV_KEYS: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)
_NO_PROXY_BYPASS_ALL = "*"


def _apply_proxy(s: Settings) -> None:
    """按配置设置代理或强制直连（保留梯子环境变量）。"""
    if s.disable_proxy:
        # 保留 HTTP_PROXY 等系统/用户变量不动，仅让 requests 绕过代理直连
        os.environ["NO_PROXY"] = _NO_PROXY_BYPASS_ALL
        os.environ["no_proxy"] = _NO_PROXY_BYPASS_ALL
        return
    for key in ("NO_PROXY", "no_proxy"):
        os.environ.pop(key, None)
    if s.http_proxy:
        os.environ.setdefault("HTTP_PROXY", s.http_proxy)
    if s.https_proxy:
        os.environ.setdefault("HTTPS_PROXY", s.https_proxy)


settings = load_settings()


def reload_settings() -> Settings:
    """按当前环境变量重建全局 settings，并回写已 import 的同名绑定。"""
    global settings
    settings = load_settings()
    import sys

    for mod in sys.modules.values():
        if mod is None:
            continue
        name = getattr(mod, "__name__", "") or ""
        if not name.startswith("quant_shell"):
            continue
        bound = getattr(mod, "settings", None)
        if bound is not None and type(bound) is Settings:
            setattr(mod, "settings", settings)
    return settings
