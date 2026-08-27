"""全链路阶段进度 — 调度提示与 ETA，改善 CLI 体验。"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field


@dataclass
class PhaseSpec:
    """一个可调度阶段。"""

    key: str
    title: str
    units: int = 1


@dataclass
class LinkageProgress:
    """按阶段推进的进度条（stdout）。

    用法::
        prog = LinkageProgress.from_plan([...])
        with prog.phase("hold", n=8) as p:
            for sym in held:
                ...
                p.tick(sym)
    """

    phases: list[PhaseSpec]
    _index: int = 0
    _t0: float = field(default_factory=time.monotonic)
    _phase_t0: float = 0.0
    _phase: PhaseSpec | None = None
    _done_units: int = 0
    _phase_done: int = 0
    enabled: bool = True

    @classmethod
    def from_plan(cls, phases: list[tuple[str, str, int]], *, enabled: bool = True) -> LinkageProgress:
        return cls(
            phases=[PhaseSpec(key=k, title=t, units=max(1, n)) for k, t, n in phases],
            enabled=enabled,
        )

    @property
    def total_units(self) -> int:
        return sum(p.units for p in self.phases)

    def begin(self) -> None:
        if not self.enabled:
            return
        titles = " -> ".join(p.title for p in self.phases)
        self._emit(f"[联动] 开始 | 阶段: {titles}")

    def phase(self, key: str, *, units: int | None = None) -> _PhaseGuard:
        spec = next((p for p in self.phases if p.key == key), None)
        if spec is None:
            spec = PhaseSpec(key=key, title=key, units=units or 1)
        elif units is not None:
            spec = PhaseSpec(key=spec.key, title=spec.title, units=max(1, units))
        return _PhaseGuard(self, spec)

    def _enter_phase(self, spec: PhaseSpec) -> None:
        self._phase = spec
        self._phase_done = 0
        self._phase_t0 = time.monotonic()
        if not self.enabled:
            return
        idx = next((i for i, p in enumerate(self.phases) if p.key == spec.key), self._index)
        self._index = idx
        self._emit(
            f"[联动] ({idx + 1}/{len(self.phases)}) {spec.title} "
            f"- 0/{spec.units} | {_fmt_eta(self._eta_seconds())}"
        )

    def _tick(self, label: str = "") -> None:
        if self._phase is None:
            return
        self._phase_done = min(self._phase.units, self._phase_done + 1)
        self._done_units = min(self.total_units, self._done_units + 1)
        if not self.enabled:
            return
        detail = f" [{label}]" if label else ""
        self._emit(
            f"[联动] ({self._index + 1}/{len(self.phases)}) {self._phase.title} "
            f"- {self._phase_done}/{self._phase.units}{detail} | {_fmt_eta(self._eta_seconds())}"
        )

    def _leave_phase(self) -> None:
        if self._phase is None:
            return
        elapsed = time.monotonic() - self._phase_t0
        if self.enabled:
            self._emit(
                f"[联动] [OK] {self._phase.title} 完成 "
                f"({self._phase.units} 项, {elapsed:.1f}s)"
            )
        # 若 tick 不足 units，补齐计数避免 ETA 偏低
        remain = max(0, self._phase.units - self._phase_done)
        self._done_units = min(self.total_units, self._done_units + remain)
        self._phase = None

    def finish(self) -> None:
        if not self.enabled:
            return
        self._emit(f"[联动] 全部完成 | 总耗时 {time.monotonic() - self._t0:.1f}s")

    def _eta_seconds(self) -> float | None:
        done = max(self._done_units, 1) if self._phase_done or self._done_units else 0
        if done <= 0:
            return None
        elapsed = time.monotonic() - self._t0
        rate = elapsed / max(self._done_units, 1)
        remain = max(0, self.total_units - self._done_units)
        return rate * remain

    def _emit(self, msg: str) -> None:
        """Windows GBK 控制台下安全打印（避免 UnicodeEncodeError）。"""
        stream = sys.stdout
        try:
            print(msg, file=stream, flush=True)
        except UnicodeEncodeError:
            encoding = getattr(stream, "encoding", None) or "utf-8"
            safe = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
            print(safe, file=stream, flush=True)


@dataclass
class _PhaseGuard:
    progress: LinkageProgress
    spec: PhaseSpec

    def __enter__(self) -> _PhaseGuard:
        self.progress._enter_phase(self.spec)
        return self

    def __exit__(self, *args: object) -> None:
        self.progress._leave_phase()

    def tick(self, label: str = "") -> None:
        self.progress._tick(label)


def _fmt_eta(seconds: float | None) -> str:
    if seconds is None:
        return "ETA --"
    if seconds < 60:
        return f"ETA ~{seconds:.0f}s"
    return f"ETA ~{seconds / 60:.1f}m"
