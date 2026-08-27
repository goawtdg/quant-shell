"""python -m quant_shell.desk — 启动本仓决策台 API。"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="quant-shell Desk API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    # 保证相对 data/ 路径落在包根
    from quant_shell.config.env_loader import project_root

    root = project_root()
    os.chdir(root)
    os.environ.setdefault("QUANT_SHELL_ROOT", str(root))

    import uvicorn

    uvicorn.run(
        "quant_shell.desk.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(root / "src")] if args.reload else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
