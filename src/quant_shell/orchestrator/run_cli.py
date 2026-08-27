"""共享 CLI 运行逻辑 — main.py / sim_run.py 复用。"""
from __future__ import annotations

import argparse
import sys

from quant_shell.common import audit
from quant_shell.common.exceptions import QuantSystemError
from quant_shell.common.types import FullLinkageResult
from quant_shell.config.settings import settings
from quant_shell.execution.portfolio import PaperPortfolioStore
from quant_shell.orchestrator.full_linkage import (
    FullLinkageOrchestrator,
    format_linkage_summary,
    hard_phase_errors,
)


def build_parser(description: str) -> argparse.ArgumentParser:
    """构建联动 CLI 参数。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--symbol", help="单标的代码（配合 --skip-stocks）")
    parser.add_argument("--symbols", help="多标的逗号分隔")
    parser.add_argument("--skip-intel", action="store_true", help="跳过 L2 情报监控")
    parser.add_argument("--skip-stocks", action="store_true", help="跳过截面选股与个股入场")
    parser.add_argument(
        "--skip-hold-review",
        action="store_true",
        help="跳过持仓重评阶段",
    )
    parser.add_argument("--no-auto", action="store_true", help="关闭纸面自动确认")
    return parser


def add_portfolio_args(parser: argparse.ArgumentParser) -> None:
    """追加模拟账户管理参数。"""
    parser.add_argument("--status", action="store_true", help="查看模拟账户")
    parser.add_argument("--reset", action="store_true", help="重置模拟账户")


def parse_symbols(args: argparse.Namespace) -> list[str] | None:
    if args.symbols:
        return [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.symbol:
        return [args.symbol.strip()]
    return None


def run_from_args(args: argparse.Namespace) -> FullLinkageResult | None:
    """根据 CLI 参数执行；账户管理命令返回 None。"""
    store = PaperPortfolioStore()
    if getattr(args, "reset", False):
        portfolio = store.reset()
        print(f"模拟盘已重置，初始资金 {portfolio.cash:,.2f} 元")
        return None
    if getattr(args, "status", False):
        _print_portfolio(store)
        return None

    sym_list = parse_symbols(args)
    audit.reset()
    audit.emit(
        layer="orch",
        event="cli_mode",
        data={
            "mode": "full_linkage",
            "symbols": sym_list or settings.monitor_symbol_list,
            "skip_intel": args.skip_intel,
            "skip_stocks": args.skip_stocks,
            "skip_hold_review": args.skip_hold_review,
            "auto_approve": not args.no_auto,
            "job_id": audit.current_job_id(),
        },
    )

    return FullLinkageOrchestrator(portfolio_store=store).run(
        symbols=sym_list,
        auto_approve=not args.no_auto,
        run_intel=not args.skip_intel,
        run_stock_pick=not args.skip_stocks,
        run_hold_review=not args.skip_hold_review,
    )


def main_cli(description: str, *, with_portfolio: bool = False) -> None:
    """统一 CLI 入口。"""
    parser = build_parser(description)
    if with_portfolio:
        add_portfolio_args(parser)
    args = parser.parse_args()
    try:
        result = run_from_args(args)
    except QuantSystemError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        if exc.suggestion:
            print(f"建议: {exc.suggestion}", file=sys.stderr)
        sys.exit(1)
    if result is not None:
        print(format_linkage_summary(result))
        hard = hard_phase_errors(result.phase_errors)
        if hard:
            print(
                f"ERROR: 联动含 {len(hard)} 项硬错误，退出码 1（禁止假成功）",
                file=sys.stderr,
            )
            for err in hard[:12]:
                print(
                    f"  [{err.get('error_code')}] {err.get('phase')}/{err.get('symbol')}: "
                    f"{err.get('error')}",
                    file=sys.stderr,
                )
            if len(hard) > 12:
                print(f"  ... 另有 {len(hard) - 12} 项", file=sys.stderr)
            sys.exit(1)
        soft = [
            e
            for e in (result.phase_errors or [])
            if str(e.get("error_code") or "")
            not in (
                "PIPELINE_ERROR",
                "SPOT_PREFETCH",
                "OHLCV_SESSION_LAG",
            )
        ]
        if soft:
            print(
                f"WARN: 联动含 {len(soft)} 项软降级"
                f"（INTEL_SOURCE_FAIL / OHLCV_SESSION_LAG_SOFT 等），job 仍成功",
                file=sys.stderr,
            )


def _print_portfolio(store: PaperPortfolioStore) -> None:
    portfolio = store.load()
    print("=== 模拟账户 ===")
    print(f"  现金:     {portfolio.cash:,.2f}")
    print(f"  初始资金: {portfolio.initial_cash:,.2f}")
    if portfolio.positions:
        print("  持仓:")
        for sym, pos in portfolio.positions.items():
            print(f"    {sym}  {pos.quantity:.0f} 股  成本={pos.avg_cost:.4f}")
    else:
        print("  持仓: （空）")
