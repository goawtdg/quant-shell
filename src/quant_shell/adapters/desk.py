"""Desk / API 消费 quant-shell 的薄适配。

决策台应只依赖本模块契约，勿硬绑外部私有仓。

用法示例（FastAPI）::

    from quant_shell.adapters.desk import desk_plugin_payload, desk_health

    @app.get("/api/shell/plugins")
    def plugins():
        return desk_plugin_payload()
"""
from __future__ import annotations

from typing import Any

from quant_shell.factory import plugin_status
from quant_shell.plugin.loader import reference_installed


def desk_plugin_payload() -> dict[str, Any]:
    """供 Desk 展示当前策略/因子插件与 profile hash。"""
    st = plugin_status()
    return {
        "ok": True,
        "plugins": st,
        "reference_installed": reference_installed(),
        "narrative": (
            "quant-shell core + optional plugins; "
            "reference_policy is not required for the framework."
        ),
    }


def desk_health() -> dict[str, Any]:
    """最小健康检查。"""
    return {
        "ok": True,
        "framework": "quant-shell",
        "reference_installed": reference_installed(),
    }


def desk_studio_get() -> dict[str, Any]:
    from quant_shell.studio.schema import studio_payload
    from quant_shell.studio.store import load_active_model

    return studio_payload(load_active_model())


def desk_studio_compile(idea: str) -> dict[str, Any]:
    from quant_shell.studio.compiler import compile_idea
    from quant_shell.studio.schema import studio_payload

    model, via = compile_idea(idea)
    payload = studio_payload(model)
    payload["compiler"] = via
    return payload


def desk_studio_save(raw: dict[str, Any]) -> dict[str, Any]:
    from quant_shell.studio.hydrate import apply_model_env
    from quant_shell.studio.schema import model_from_dict, studio_payload
    from quant_shell.studio.store import save_active_model

    model = model_from_dict(raw)
    save_active_model(model)
    apply_model_env(model)
    payload = studio_payload(model)
    payload["saved"] = True
    return payload
