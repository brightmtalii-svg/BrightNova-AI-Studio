from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SystemSample:
    cpu_percent: float = 0.0
    memory_total: int = 0
    memory_used: int = 0
    memory_available: int = 0
    memory_percent: float = 0.0
    disk_total: int = 0
    disk_used: int = 0
    disk_free: int = 0
    disk_percent: float = 0.0
    ollama_rss: int = 0
    ollama_processes: int = 0
    disk_path: str = ""
    timestamp: float = field(default_factory=time.time)


def format_bytes(value: int | float) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units[:-1]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


class SystemMonitor:
    def __init__(self, disk_path: str | Path | None = None):
        self.disk_path = Path(disk_path or Path.home())
        try:
            import psutil

            self.psutil = psutil
            psutil.cpu_percent(interval=None)
        except ImportError as exc:
            raise RuntimeError(
                "psutil is required for system monitoring. Install it with "
                "'python3 -m pip install psutil'."
            ) from exc

    def sample(self) -> SystemSample:
        psutil = self.psutil
        memory = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(str(self.disk_path))
        except OSError:
            disk = psutil.disk_usage("/")
        rss = 0
        count = 0
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (process.info.get("name") or "").lower()
                cmdline = " ".join(process.info.get("cmdline") or []).lower()
                if name.startswith("ollama") or "ollama serve" in cmdline:
                    rss += process.memory_info().rss
                    count += 1
            except (psutil.Error, OSError):
                continue
        return SystemSample(
            cpu_percent=float(psutil.cpu_percent(interval=None)),
            memory_total=int(memory.total),
            memory_used=int(memory.used),
            memory_available=int(memory.available),
            memory_percent=float(memory.percent),
            disk_total=int(disk.total),
            disk_used=int(disk.used),
            disk_free=int(disk.free),
            disk_percent=float(disk.percent),
            ollama_rss=int(rss),
            ollama_processes=count,
            disk_path=str(self.disk_path),
        )
