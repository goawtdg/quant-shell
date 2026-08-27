"""加载项目根目录 .env 文件。"""
from __future__ import annotations

import os
from pathlib import Path

from quant_shell.common.logging_config import get_logger

logger = get_logger(__name__)


def project_root() -> Path:
    """工作区根目录（含 ``pyproject.toml`` / ``.env`` / ``data/``）。

    解析顺序：
    1. ``QUANT_SHELL_ROOT`` 环境变量
    2. 自本文件向上查找名为 ``quant-shell`` 的 ``pyproject.toml``（editable 布局）
    3. 当前工作目录（已安装 wheel / 独立部署时在项目根下运行）
    """
    override = os.getenv("QUANT_SHELL_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in here.parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if 'name = "quant-shell"' in text or "name = 'quant-shell'" in text:
            return parent

    return Path.cwd().resolve()


def load_env_file() -> Path | None:
    """加载 .env；已存在的环境变量不会被覆盖。

    Returns:
        成功加载的 .env 路径；文件不存在则返回 None。
    """
    root = project_root()
    candidates = (root / ".env", root / "src" / ".env")
    env_path = next((p for p in candidates if p.is_file()), None)
    if env_path is None:
        logger.debug("load_env_file skip: no .env under %s", root)
        return None

    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        logger.warning(
            "python-dotenv 未安装，跳过 .env 加载: %s",
            exc,
        )
        return None

    load_dotenv(env_path, override=False)
    logger.info("load_env_file ok path=%s", env_path)
    return env_path
