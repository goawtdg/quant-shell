"""Adapters — optional frontends (Desk/API) consume shell contracts only."""
from quant_shell.adapters.desk import (
    desk_health,
    desk_plugin_payload,
    desk_studio_compile,
    desk_studio_get,
    desk_studio_save,
)

__all__ = [
    "desk_health",
    "desk_plugin_payload",
    "desk_studio_compile",
    "desk_studio_get",
    "desk_studio_save",
]
