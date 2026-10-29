from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import ConfigStore, Project
from .ollama_manager import OFFLINE, HealthResult, OllamaManager
from .project_manager import ProjectManager
from .system_monitor import SystemMonitor


ROOT = Path(__file__).resolve().parent.parent


class AppContext(QObject):
    server_changed = Signal(object)
    models_changed = Signal(list)
    model_selected = Signal(str)
    project_changed = Signal(object)
    projects_changed = Signal()
    monitor_updated = Signal(object)
    settings_changed = Signal()
    notify = Signal(str, str)

    def __init__(self, store: ConfigStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = store.settings
        self.ollama = OllamaManager(self.settings.ollama_host)
        self.projects = ProjectManager(self.settings.ollama_host)
        self.monitor = SystemMonitor()
        self.current_health = HealthResult(status=OFFLINE, managed_by="unknown")
        self.current_models = []

    def save(self) -> None:
        self.store.save()

    def set_health(self, health: HealthResult) -> None:
        self.current_health = health
        self.server_changed.emit(health)

    def set_models(self, models: list) -> None:
        self.current_models = models
        self.models_changed.emit(models)

    def select_model(self, model: str, announce: bool = True) -> None:
        if not model:
            return
        self.settings.selected_model = model
        self.save()
        self.model_selected.emit(model)
        if announce:
            self.notify.emit("Model selected", f"{model} is now the active model.")

    def current_model(self) -> str:
        return self.settings.selected_model

    def select_project(self, project: Project) -> None:
        self.settings.last_project_id = project.id
        self.save()
        self.project_changed.emit(project)

    def notify_user(self, title: str, message: str) -> None:
        self.notify.emit(title, message)

    def asset(self, *parts: str) -> str:
        return str(ROOT.joinpath("assets", *parts))
