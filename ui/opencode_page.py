from __future__ import annotations

import json
import logging
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brightnova.project_manager import ProjectError
from brightnova.workers import TaskWorker
from ui.widgets import (
    InfoRow,
    PageHeader,
    StatusBadge,
    make_label,
)


logger = logging.getLogger(__name__)


class OpenCodePage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self.workers: list[TaskWorker] = []
        self.tools_loaded = False
        self.tools_busy = False
        self._build()
        self.context.projects_changed.connect(self.refresh)
        self.context.project_changed.connect(lambda _project: self.refresh())
        self.context.models_changed.connect(lambda _models: self.refresh())
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("pageBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 28, 32, 32)
        layout.setSpacing(18)
        layout.addWidget(
            PageHeader(
                "Toolchain bridge",
                "OpenCode Integration",
                "Connect local Ollama models to the OpenCode coding agent through a "
                "verified project configuration.",
            )
        )

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(22, 20, 22, 20)
        status_layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(make_label("Integration status", "sectionTitle"))
        top.addStretch(1)
        self.badge = StatusBadge("NOT CONFIGURED")
        top.addWidget(self.badge)
        status_layout.addLayout(top)
        self.summary = make_label(
            "Select a development project to prepare its OpenCode configuration.",
            "muted",
            wrap=True,
        )
        status_layout.addWidget(self.summary)
        rows = QFrame()
        rows.setObjectName("transparent")
        row_layout = QVBoxLayout(rows)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        self.project_row = InfoRow("Project", "None")
        self.config_row = InfoRow("Config file", "Not available", mono=True)
        self.model_row = InfoRow("Default model", "Not configured", mono=True)
        self.endpoint_row = InfoRow("OpenCode endpoint", "http://127.0.0.1:11434/v1", mono=True)
        row_layout.addWidget(self.project_row)
        row_layout.addWidget(self.config_row)
        row_layout.addWidget(self.model_row)
        row_layout.addWidget(self.endpoint_row)
        status_layout.addWidget(rows)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.configure_button = QPushButton("CONFIGURE PROJECT")
        self.configure_button.setObjectName("primaryButton")
        self.configure_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.configure_button.clicked.connect(self.configure_project)
        self.vscode_button = QPushButton("OPEN IN VS CODE")
        self.vscode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vscode_button.clicked.connect(self.open_vscode)
        self.launch_button = QPushButton("LAUNCH OPENCODE")
        self.launch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_button.clicked.connect(self.launch_opencode)
        refresh_button = QPushButton("RECHECK")
        refresh_button.setObjectName("ghostButton")
        refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_button.clicked.connect(lambda: self.refresh(force_tools=True))
        for button in (self.configure_button, self.vscode_button, self.launch_button):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(refresh_button)
        status_layout.addLayout(actions)
        layout.addWidget(status_card)

        details_row = QHBoxLayout()
        details_row.setSpacing(14)
        tools_card = QFrame()
        tools_card.setObjectName("card")
        tools_layout = QVBoxLayout(tools_card)
        tools_layout.setContentsMargins(22, 18, 22, 20)
        tools_layout.setSpacing(10)
        tools_layout.addWidget(make_label("Detected toolchain", "sectionTitle"))
        self.opencode_row = InfoRow("OpenCode", "Checking...")
        self.vscode_row = InfoRow("VS Code", "Checking...")
        self.terminal_row = InfoRow("Terminal", "Checking...")
        self.ollama_row = InfoRow("Ollama API", self.context.settings.ollama_host, mono=True)
        for row in (
            self.opencode_row,
            self.vscode_row,
            self.terminal_row,
            self.ollama_row,
        ):
            tools_layout.addWidget(row)
        tools_layout.addStretch(1)
        details_row.addWidget(tools_card, 1)

        guide_card = QFrame()
        guide_card.setObjectName("card")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(22, 18, 22, 20)
        guide_layout.setSpacing(8)
        guide_layout.addWidget(make_label("How the integration works", "sectionTitle"))
        for text in (
            "1. BrightNova discovers the models installed in Ollama.",
            "2. It adds an OpenAI-compatible Ollama provider to the project's "
            "opencode.json file.",
            "3. The selected local model becomes the project's default model.",
            "4. OpenCode runs inside the project directory with that configuration.",
        ):
            guide_layout.addWidget(make_label(text, "muted", wrap=True))
        guide_layout.addSpacing(4)
        guide_layout.addWidget(
            make_label(
                "Existing providers are preserved. Existing configuration files are "
                "backed up before an approved update.",
                "muted",
                wrap=True,
            )
        )
        guide_layout.addStretch(1)
        details_row.addWidget(guide_card, 1)
        layout.addLayout(details_row)

        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(22, 18, 22, 20)
        preview_layout.setSpacing(10)
        preview_title = QHBoxLayout()
        preview_title.addWidget(make_label("Project configuration preview", "sectionTitle"))
        preview_title.addStretch(1)
        self.preview_note = make_label("Read-only", "tag")
        preview_title.addWidget(self.preview_note)
        preview_layout.addLayout(preview_title)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(210)
        self.preview.setPlaceholderText("No project configuration available.")
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_card)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _start_task(self, function, success, failure) -> None:
        worker = TaskWorker(function, self)
        self.workers.append(worker)

        def cleanup() -> None:
            if worker in self.workers:
                self.workers.remove(worker)
            worker.deleteLater()

        worker.succeeded.connect(success)
        worker.failed.connect(failure)
        worker.finished.connect(cleanup)
        worker.start()

    def _detect_tools(self) -> None:
        if self.tools_busy or self.tools_loaded:
            return
        self.tools_busy = True

        def collect():
            version = self.context.projects.opencode_version()
            code = shutil.which("code")
            terminal = next(
                (
                    name
                    for name in (
                        "ptyxis",
                        "gnome-terminal",
                        "konsole",
                        "xfce4-terminal",
                        "kitty",
                        "xterm",
                        "x-terminal-emulator",
                    )
                    if shutil.which(name)
                ),
                "",
            )
            return version, code, terminal

        def done(result) -> None:
            version, code, terminal = result
            self.tools_busy = False
            self.tools_loaded = True
            self.opencode_row.set_value(f"v{version}" if version else "Not found")
            self.vscode_row.set_value("Available" if code else "Not found")
            self.terminal_row.set_value(terminal or "Not found")

        def failed(message: str) -> None:
            self.tools_busy = False
            self.tools_loaded = True
            logger.warning("Tool detection failed: %s", message)

        self._start_task(collect, done, failed)

    def refresh(self, force_tools: bool = False) -> None:
        if force_tools:
            self.tools_loaded = False
        self._detect_tools()
        project = self.context.store.last_project()
        if project is None:
            self.project_row.set_value("None")
            self.config_row.set_value("Not available")
            self.model_row.set_value("Not configured")
            self.badge.set_state("offline", "NOT CONFIGURED")
            self.summary.setText(
                "Add and configure a development project to bridge Ollama into OpenCode."
            )
            self.preview.clear()
            self.configure_button.setEnabled(False)
            self.vscode_button.setEnabled(False)
            self.launch_button.setEnabled(False)
            return
        self.configure_button.setEnabled(True)
        self.vscode_button.setEnabled(True)
        self.launch_button.setEnabled(True)
        self.project_row.set_value(project.name)
        config_path = self.context.projects.config_path(project.path)
        self.config_row.set_value(str(config_path))
        config = {}
        error = ""
        if config_path.exists():
            try:
                config = self.context.projects.read_config(project.path)
            except ProjectError as exc:
                error = str(exc)
        provider = config.get("provider") or {}
        ollama = provider.get("ollama") if isinstance(provider, dict) else None
        configured = isinstance(ollama, dict) and bool(ollama.get("models"))
        default_model = str(config.get("model") or "")
        if configured:
            self.badge.set_state("online", "INTEGRATION READY")
            self.summary.setText(
                "BrightNova found a local Ollama provider. Launch OpenCode inside the "
                "project to work with the selected model."
            )
            self.model_row.set_value(default_model or project.model)
        else:
            self.badge.set_state("offline", "NOT CONFIGURED")
            self.summary.setText(
                "No verified Ollama provider was found. Configure the project before "
                "expecting OpenCode to use a local model."
            )
            self.model_row.set_value("Not configured")
        if error:
            self.summary.setText(f"Configuration could not be read: {error}")
        if config_path.exists():
            if config:
                self.preview.setPlainText(json.dumps(config, indent=2))
            else:
                self.preview.setPlainText(error or "Configuration is not valid JSON.")
        else:
            self.preview.clear()

    def configure_project(self) -> None:
        project = self.context.store.last_project()
        if project is None:
            self.navigate("projects")
            return
        if not self.context.current_models:
            QMessageBox.warning(
                self,
                "No local models",
                "Start Ollama and refresh the model library before configuring OpenCode.",
            )
            return
        config_path = self.context.projects.config_path(project.path)
        allow_existing = False
        if config_path.exists():
            answer = QMessageBox.question(
                self,
                "Update OpenCode configuration",
                f"{config_path}\n\nBrightNova will preserve other providers and "
                "settings, update the Ollama provider, set the selected default model, "
                "and create a timestamped backup.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            allow_existing = True
        manager = self.context.projects
        models = [model.name for model in self.context.current_models]

        def done(result) -> None:
            self.refresh()
            self.context.notify_user("OpenCode configured", result["path"])
            QMessageBox.information(
                self,
                "Integration configured",
                f"OpenCode configuration: {result['path']}\n"
                f"Default model: {result['model']}",
            )

        self._start_task(
            lambda: manager.configure(project, models, allow_existing=allow_existing),
            done,
            lambda message: QMessageBox.critical(
                self, "Configuration failed", message
            ),
        )

    def open_vscode(self) -> None:
        project = self.context.store.last_project()
        if project is None:
            self.navigate("projects")
            return
        manager = self.context.projects
        self._start_task(
            lambda: manager.open_vscode(project),
            lambda result: self.context.notify_user("VS Code", result.message),
            lambda message: QMessageBox.critical(self, "VS Code", message),
        )

    def launch_opencode(self) -> None:
        project = self.context.store.last_project()
        if project is None:
            self.navigate("projects")
            return
        try:
            config = self.context.projects.read_config(project.path)
        except ProjectError as exc:
            QMessageBox.critical(self, "Invalid configuration", str(exc))
            return
        provider = config.get("provider") or {}
        ollama = provider.get("ollama") if isinstance(provider, dict) else None
        if not isinstance(ollama, dict) or not ollama.get("models"):
            QMessageBox.warning(
                self,
                "Not configured",
                "Configure this project before launching OpenCode with a local model.",
            )
            return
        manager = self.context.projects
        self._start_task(
            lambda: manager.launch_opencode(project),
            lambda result: self.context.notify_user("OpenCode", result.message),
            lambda message: QMessageBox.critical(self, "OpenCode", message),
        )
