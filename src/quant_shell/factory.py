"""create_strategy_engine — 统一工厂。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Callable

from quant_shell.common.interfaces import StockPicker, StrategyEngine
from quant_shell.plugin.loader import (
    DEFAULT_COMMIT_MODULE,
    DEFAULT_PICKER_MODULE,
    load_callable,
    load_strategy_class,
    resolve_strategy_spec,
)
from quant_shell.plugin.profile import StrategyProfile


def _resolve_profile_path() -> Path | None:
    from quant_shell.config.env_loader import project_root

    raw = os.getenv("STRATEGY_PROFILE", "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p
    root = project_root()
    for candidate in (root / raw, root / "examples" / Path(raw).name):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"STRATEGY_PROFILE not found: {raw}")


def create_strategy_engine(
    *,
    strategy_module: str | None = None,
    strategy_profile: str | Path | StrategyProfile | None = None,
    **kwargs: object,
) -> StrategyEngine:
    spec = resolve_strategy_spec(strategy_module)
    profile: StrategyProfile | None = None
    if isinstance(strategy_profile, StrategyProfile):
        profile = strategy_profile
    elif strategy_profile is not None:
        profile = StrategyProfile.load(strategy_profile)
    else:
        path = _resolve_profile_path()
        if path is not None:
            profile = StrategyProfile.load(path)
        elif os.getenv("STRATEGY_PROFILE", "").strip() == "":
            from quant_shell.studio.hydrate import model_to_profile
            from quant_shell.studio.store import load_active_model

            studio = load_active_model()
            if studio is not None:
                profile = model_to_profile(studio)

    cls = load_strategy_class(spec)

    if profile is not None and hasattr(cls, "from_profile"):
        engine = cls.from_profile(profile, **kwargs)  # type: ignore[attr-defined]
    else:
        if profile is not None:
            cfg = profile.to_policy_config()
            kwargs.setdefault("config", cfg)
        engine = cls(**kwargs)  # type: ignore[call-arg]

    if not isinstance(engine, StrategyEngine):
        raise TypeError(f"{spec} did not produce a StrategyEngine")
    return engine


def create_signal_generator(**kwargs: object):
    """加载 L3 信号生成器；默认 SignalFusionGenerator + FACTOR_MODULE 因子。"""
    from quant_shell.signals.fusion import SignalFusionGenerator

    spec = os.getenv("SIGNAL_MODULE", "").strip()
    if spec:
        cls = load_strategy_class(spec)
        return cls(**kwargs)  # type: ignore[call-arg]
    return SignalFusionGenerator(**kwargs)  # type: ignore[arg-type]


def create_commit_decision() -> Callable[..., Any]:
    """加载 L4→L7 commit；默认 reference_policy，可用 COMMIT_MODULE 替换。"""
    spec = (os.getenv("COMMIT_MODULE") or DEFAULT_COMMIT_MODULE).strip()
    return load_callable(spec)


def create_stock_picker(*, registry: object | None = None, **kwargs: object) -> StockPicker:
    """加载截面选股；默认 FactorStrategyEngine，可用 PICKER_MODULE 替换。"""
    spec = (os.getenv("PICKER_MODULE") or DEFAULT_PICKER_MODULE).strip()
    cls = load_strategy_class(spec)
    if registry is not None and hasattr(cls, "from_registry"):
        picker = cls.from_registry(registry, **kwargs)  # type: ignore[attr-defined]
    else:
        if registry is not None:
            kwargs.setdefault("registry", registry)
        picker = cls(**kwargs)  # type: ignore[call-arg]
    if not isinstance(picker, StockPicker):
        raise TypeError(f"{spec} did not produce a StockPicker")
    return picker


def create_layer4_service(
    *,
    registry: object | None = None,
    portfolio_store: object | None = None,
):
    from quant_shell.orchestrator.layer4 import Layer4Service

    return Layer4Service.create_default(
        registry=registry,  # type: ignore[arg-type]
        portfolio_store=portfolio_store,
    )


def plugin_status() -> dict[str, str | None]:
    """当前加载的插件规格（Desk/CLI 展示用）。"""
    from quant_shell.config.env_loader import project_root
    from quant_shell.plugin.loader import reference_installed

    profile_raw = os.getenv("STRATEGY_PROFILE", "").strip() or None
    profile_hash: str | None = None
    if profile_raw:
        path = Path(profile_raw)
        if not path.is_file():
            root = project_root()
            for candidate in (root / profile_raw, root / "examples" / Path(profile_raw).name):
                if candidate.is_file():
                    path = candidate
                    break
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            profile_hash = digest[:12]
    from quant_shell.studio.store import load_active_model

    studio = load_active_model()
    return {
        "strategy_module": resolve_strategy_spec(None),
        "factor_module": os.getenv("FACTOR_MODULE", "").strip() or None,
        "signal_module": os.getenv("SIGNAL_MODULE", "").strip() or None,
        "intel_module": os.getenv("INTEL_MODULE", "").strip() or None,
        "commit_module": (os.getenv("COMMIT_MODULE") or DEFAULT_COMMIT_MODULE).strip(),
        "picker_module": (os.getenv("PICKER_MODULE") or DEFAULT_PICKER_MODULE).strip(),
        "strategy_profile": profile_raw,
        "strategy_profile_hash": profile_hash,
        "reference_installed": "1" if reference_installed() else "0",
        "studio_model": studio.name if studio is not None else None,
    }
