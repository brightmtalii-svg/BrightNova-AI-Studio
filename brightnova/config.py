from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_NAME = "BRIGHTNOVA AI STUDIO"
APP_VERSION = "3.0.0"
TAGLINE = "Build Locally. Think Beyond."
DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_SYSTEM_PROMPT = (
    "You are BrightNova, a personal AI coding mentor. Help the user understand "
    "software engineering concepts, debug programs, design applications, and "
    "improve coding skills. Prioritize teaching over blindly generating entire "
    "projects."
)

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def config_dir() -> Path:
    override = os.environ.get("BRIGHTNOVA_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "brightnova"


@dataclass
class Project:
    name: str
    path: str
    model: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Project":
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex[:12]),
            name=str(payload.get("name") or "Untitled project"),
            path=str(payload.get("path") or ""),
            model=str(payload.get("model") or ""),
            created_at=str(payload.get("created_at") or _utc_now()),
            updated_at=str(payload.get("updated_at") or _utc_now()),
        )


@dataclass
class Settings:
    selected_model: str = "qwen2.5-coder:7b"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    refresh_interval_seconds: float = 2.0
    ollama_host: str = DEFAULT_HOST
    projects: list[Project] = field(default_factory=list)
    last_project_id: str = ""
    window_width: int = 1440
    window_height: int = 900
    confirm_before_service_stop: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["projects"] = [project.to_dict() for project in self.projects]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Settings":
        raw_projects = payload.get("projects") or []
        projects = [
            Project.from_dict(item)
            for item in raw_projects
            if isinstance(item, dict)
        ]
        interval = payload.get("refresh_interval_seconds", 2.0)
        try:
            interval = min(10.0, max(1.0, float(interval)))
        except (TypeError, ValueError):
            interval = 2.0
        return cls(
            selected_model=str(payload.get("selected_model") or "qwen2.5-coder:7b"),
            system_prompt=str(payload.get("system_prompt") or DEFAULT_SYSTEM_PROMPT),
            refresh_interval_seconds=interval,
            ollama_host=str(payload.get("ollama_host") or DEFAULT_HOST).rstrip("/"),
            projects=projects,
            last_project_id=str(payload.get("last_project_id") or ""),
            window_width=max(1024, int(payload.get("window_width") or 1440)),
            window_height=max(700, int(payload.get("window_height") or 900)),
            confirm_before_service_stop=bool(
                payload.get("confirm_before_service_stop", True)
            ),
        )


class ConfigStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else config_dir()
        self.path = self.directory / "settings.json"
        self.last_error = ""
        self.settings = Settings()
        self.load()

    def load(self) -> Settings:
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.settings = Settings()
            self.save()
            return self.settings
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError("Settings root must be a JSON object")
            self.settings = Settings.from_dict(payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.last_error = str(exc)
            logger.exception("Unable to load settings from %s", self.path)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.path.with_name(f"settings.corrupt-{stamp}.json")
            try:
                if self.path.exists():
                    self.path.replace(backup)
            except OSError:
                logger.exception("Unable to preserve corrupt settings file")
            self.settings = Settings()
            self.save()
        return self.settings

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.settings.to_dict(), indent=2) + "\n"
        descriptor, temporary = tempfile.mkstemp(
            prefix=".settings-", suffix=".json", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get_project(self, project_id: str) -> Project | None:
        return next(
            (project for project in self.settings.projects if project.id == project_id),
            None,
        )

    def last_project(self) -> Project | None:
        project = self.get_project(self.settings.last_project_id)
        if project:
            return project
        return self.settings.projects[0] if self.settings.projects else None

    def add_project(self, project: Project) -> Project:
        existing = next(
            (
                item
                for item in self.settings.projects
                if item.path == project.path or item.name.lower() == project.name.lower()
            ),
            None,
        )
        if existing:
            existing.name = project.name
            existing.path = project.path
            existing.model = project.model
            existing.updated_at = _utc_now()
            self.settings.last_project_id = existing.id
            self.save()
            return existing
        self.settings.projects.append(project)
        self.settings.last_project_id = project.id
        self.save()
        return project

    def update_project(self, project: Project) -> None:
        for index, existing in enumerate(self.settings.projects):
            if existing.id == project.id:
                project.updated_at = _utc_now()
                self.settings.projects[index] = project
                if self.settings.last_project_id == project.id:
                    self.settings.selected_model = project.model
                self.save()
                return
        raise KeyError(f"Unknown project: {project.id}")

    def remove_project(self, project_id: str) -> None:
        self.settings.projects = [
            project for project in self.settings.projects if project.id != project_id
        ]
        if self.settings.last_project_id == project_id:
            self.settings.last_project_id = (
                self.settings.projects[0].id if self.settings.projects else ""
            )
        self.save()

    def set_last_project(self, project_id: str) -> None:
        if self.get_project(project_id):
            self.settings.last_project_id = project_id
            self.save()
