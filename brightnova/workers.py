from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from .ollama_manager import OllamaManager, RunningModel
from .system_monitor import SystemMonitor, SystemSample


@dataclass
class MonitorPayload:
    sample: SystemSample = field(default_factory=SystemSample)
    running_models: list[RunningModel] = field(default_factory=list)
    ollama_online: bool = False
    error: str = ""


class TaskWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.function = function

    def run(self) -> None:
        try:
            result = self.function()
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)


class ChatWorker(QThread):
    chunk = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        manager: OllamaManager,
        model: str,
        messages: list[dict[str, str]],
        parent=None,
    ):
        super().__init__(parent)
        self.manager = manager
        self.model = model
        self.messages = messages
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.manager.cancel_generation()

    def run(self) -> None:
        try:
            text = self.manager.chat_stream(
                self.model,
                self.messages,
                self.chunk.emit,
                cancel_event=self.cancel_event,
            )
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(text)


class MonitorWorker(QThread):
    sample_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        monitor: SystemMonitor,
        manager: OllamaManager,
        interval: float = 2.0,
        parent=None,
    ):
        super().__init__(parent)
        self.monitor = monitor
        self.manager = manager
        self.interval = max(1.0, interval)
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                sample = self.monitor.sample()
            except Exception as exc:
                self.failed.emit(str(exc))
                self.stop_event.wait(self.interval)
                continue
            running: list[RunningModel] = []
            online = False
            error = ""
            try:
                running = self.manager.running_models(timeout=1.5)
                online = True
            except Exception as exc:
                error = str(exc)
            self.sample_ready.emit(MonitorPayload(sample, running, online, error))
            self.stop_event.wait(self.interval)

    def stop(self) -> None:
        self.stop_event.set()
