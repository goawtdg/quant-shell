"""当前启用的交易模型落盘 — 仅 JSON，给前端读写。"""
from __future__ import annotations

import json
from pathlib import Path

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.config.env_loader import project_root
from quant_shell.studio.schema import TradingModel, model_from_dict


def models_dir() -> Path:
    path = project_root() / "data" / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def active_path() -> Path:
    return models_dir() / "active.json"


def load_active_model() -> TradingModel | None:
    path = active_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return model_from_dict(raw)


def save_active_model(model: TradingModel) -> Path:
    path = active_path()
    write_text_atomic(path, json.dumps(model.to_dict(), ensure_ascii=False, indent=2))
    return path
