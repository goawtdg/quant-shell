"""本仓决策台 API（FastAPI）— 独立于父仓 quant/。"""
from quant_shell.desk.app import app, create_app

__all__ = ["app", "create_app"]
