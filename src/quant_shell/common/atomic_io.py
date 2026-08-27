"""原子落盘与文件锁 — 全仓库唯一写盘原语。"""
from __future__ import annotations

import os
import pickle
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """先写同目录临时文件再 ``os.replace``。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def write_pickle_atomic(path: Path, obj: Any) -> None:
    """pickle 原子替换（日 K / TTL 缓存）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
    os.replace(tmp, path)


def append_text(path: Path, line: str, *, encoding: str = "utf-8") -> None:
    """追加一行；失败抛 OSError，禁止吞掉。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = line if line.endswith("\n") else line + "\n"
    with path.open("a", encoding=encoding) as fh:
        fh.write(text)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """同目录 ``{name}.lock`` 排他锁（Windows msvcrt / POSIX fcntl）。"""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not lock_path.exists() or lock_path.stat().st_size == 0:
            lock_path.write_bytes(b"\0")
    except OSError:
        if not lock_path.exists():
            raise
    fh = lock_path.open("r+b")
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
