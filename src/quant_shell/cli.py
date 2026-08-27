"""quant-shell CLI — 单标的纸面 / 全链路联动。"""
from __future__ import annotations

import argparse
import json
import sys

from quant_shell.common.exceptions import QuantSystemError
from quant_shell.common.logging_config import setup_logging
from quant_shell.config.env_loader import load_env_file
from quant_shell.execution.portfolio import PaperPortfolioStore
from quant_shell.factory import plugin_status
from quant_shell.orchestrator.full_linkage import (
    format_linkage_summary,
    hard_phase_errors,
)
from quant_shell.orchestrator.paper_pipeline import PaperTradingPipeline
from quant_shell.orchestrator.run_cli import (
    build_parser as build_linkage_parser,
    run_from_args as run_linkage_from_args,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="quant-shell — 插件化量化框架")
    sub = p.add_subparsers(dest="cmd", required=False)

    run_p = sub.add_parser("run", help="单标的纸面七层")
    run_p.add_argument("--symbol", default="510300")
    run_p.add_argument("--mode", choices=("entry", "hold"), default="entry")
    run_p.add_argument("--no-auto", action="store_true")

    sub.add_parser("linkage", help="全链路联动（ETF+选股+情报，见 linkage 参数）")

    acc = sub.add_parser("account", help="模拟账户")
    acc.add_argument("--status", action="store_true")
    acc.add_argument("--reset", action="store_true")

    plug = sub.add_parser("plugins", help="显示当前 STRATEGY/FACTOR 等插件规格")
    plug.add_argument("--json", action="store_true", help="JSON 输出")

    sub.add_parser("model", help="显示当前前端保存的交易模型")
    return p


def _run_single(args: argparse.Namespace) -> int:
    store = PaperPortfolioStore()
    try:
        pipe = PaperTradingPipeline.create_integrated(portfolio_store=store)
        ctx = pipe.run_symbol(
            args.symbol,
            evaluation_mode=args.mode,
            auto_approve=not args.no_auto,
        )
    except QuantSystemError as exc:
        print(f"错误: {exc.message}", file=sys.stderr)
        return 1
    action = ctx.ai_decision.action.value if ctx.ai_decision else "—"
    print(f"{args.symbol}  mode={args.mode}  action={action}")
    return 0


def _print_plugins(*, as_json: bool) -> int:
    status = plugin_status()
    if as_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    for key, val in status.items():
        print(f"{key}: {val if val is not None else '—'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    setup_logging()
    from quant_shell.studio.hydrate import hydrate_studio

    hydrate_studio()
    raw = list(argv) if argv is not None else sys.argv[1:]
    if raw[:1] == ["linkage"]:
        lp = build_linkage_parser("quant-shell 全链路联动")
        la = lp.parse_args(raw[1:])
        try:
            result = run_linkage_from_args(la)
        except QuantSystemError as exc:
            print(f"错误: {exc.message}", file=sys.stderr)
            return 1
        if result is not None:
            print(format_linkage_summary(result))
            if hard_phase_errors(result.phase_errors):
                return 1
        return 0

    args = build_parser().parse_args(argv)

    if args.cmd == "account":
        store = PaperPortfolioStore()
        if args.reset:
            p = store.reset()
            print(f"模拟盘已重置，初始资金 {p.cash:,.2f}")
            return 0
        pf = store.load()
        print(f"现金 {pf.cash:,.2f}  持仓 {len(pf.positions)}")
        status = plugin_status()
        print(f"strategy: {status['strategy_module']}")
        if status.get("strategy_profile_hash"):
            print(f"profile_hash: {status['strategy_profile_hash']}")
        return 0

    if args.cmd == "plugins":
        return _print_plugins(as_json=bool(args.json))

    if args.cmd == "model":
        from quant_shell.studio.schema import studio_payload
        from quant_shell.studio.store import load_active_model

        print(json.dumps(studio_payload(load_active_model()), ensure_ascii=False, indent=2))
        return 0

    # default: run
    if args.cmd is None or args.cmd == "run":
        run_args = args if args.cmd == "run" else argparse.Namespace(
            symbol="510300", mode="entry", no_auto=False
        )
        return _run_single(run_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
