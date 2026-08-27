"""统一日志配置。"""
from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """配置根日志格式。

    Args:
        level: 根 logger 级别，默认 INFO。
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        # stderr：避免污染 --json 等 stdout 机器可读输出
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。

    Args:
        name: 通常传 ``__name__``。

    Returns:
        配置好的 Logger 实例。
    """
    return logging.getLogger(name)
