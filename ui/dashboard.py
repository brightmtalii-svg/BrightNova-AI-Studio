from __future__ import annotations

import logging

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brightnova.config import TAGLINE
from brightnova.ollama_manager import CONNECTING, OFFLINE, ONLINE, HealthResult
from brightnova.workers import MonitorPayload, TaskWorker
from ui.widgets import (
    InfoRow,
    MetricCard,
    PageHeader,
    StatusBadge,
    make_label,
    tinted_icon,
)


logger = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self.workers: list[TaskWorker] = []
        self._build()
        self.context.server_changed.connect(self.apply_health)
        self.context.models_changed.connect(self._models_changed)
        self.context.model_selected.connect(self._model_selected)
        self.context.monitor_updated.connect(self._monitor_changed)
        self.apply_health(self.context.current_health)

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
        layout.setSpacing(20)
        layout.addWidget(
            PageHeader(
                "Command center",
                "Dashboard",
                "Your local AI development environment at a glance.",
            )
        )
        layout.addWidget(self._build_hero())
        layout.addWidget(self._build_status_and_stats())
        layout.addWidget(self._build_server_controls())
        layout.addWidget(self._build_actions())
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("heroCard")
        hero.setMinimumHeight(184)
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(26, 24, 28, 24)
        layout.setSpacing(24)
        accent = QFrame()
        accent.setObjectName("heroAccent")
        accent.setFixedWidth(5)
        accent.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout.addWidget(accent)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        text_layout.addWidget(make_label("LOCAL AI WORKSPACE", "eyebrow"))
        title = make_label("BRIGHTNOVA AI STUDIO", "heroTitle", wrap=True)
        text_layout.addWidget(title)
        subtitle = make_label(
            "Your Local AI Development Environment", "heroSubtitle"
        )
        text_layout.addWidget(subtitle)
        tagline = make_label(TAGLINE, "muted")
        tagline.setStyleSheet("color: #6E85A6; font-size: 12px; margin-top: 4px;")
        text_layout.addWidget(tagline)
        text_layout.addStretch(1)
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        for text in ("PRIVATE", "LOCAL", "OPEN SOURCE"):
            tag = make_label(text, "tag")
            tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            badge_row.addWidget(tag)
        badge_row.addStretch(1)
        text_layout.addLayout(badge_row)
        layout.addLayout(text_layout, 1)
        logo = QLabel()
        pixmap = QPixmap(self.context.asset("icons", "logo.svg"))
        logo.setPixmap(
            pixmap.scaled(
                118,
                118,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setFixedSize(118, 118)
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        return hero

    def _build_status_and_stats(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(22, 20, 22, 20)
        status_layout.setSpacing(20)

        state_block = QVBoxLayout()
        state_block.setSpacing(8)
        dot_row = QHBoxLayout()
        dot_row.setSpacing(9)
        self.dot = make_label("●", "statusDot")
        self.status_badge = StatusBadge("SERVER OFFLINE")
        dot_row.addWidget(self.dot)
        dot_row.addWidget(self.status_badge)
        dot_row.addStretch(1)
        state_block.addLayout(dot_row)
        self.server_headline = make_label("Server offline", "serverHeadline")
        state_block.addWidget(self.server_headline)
        self.server_detail = make_label(
            "Start Ollama to unlock model management, chat, and project integration.",
            "muted",
            wrap=True,
        )
        self.server_detail.setMaximumWidth(410)
        state_block.addWidget(self.server_detail)
        state_block.addStretch(1)
        status_layout.addLayout(state_block, 2)

        info_card = QWidget()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(9)
        self.endpoint_row = InfoRow("API endpoint", "localhost:11434", mono=True)
        self.active_row = InfoRow(
            "Active model", self.context.current_model() or "Not selected", mono=True
        )
        self.managed_row = InfoRow("Managed by", "Unknown")
        self.version_row = InfoRow("Ollama version", "Unavailable")
        info_layout.addWidget(self.endpoint_row)
        info_layout.addWidget(self.active_row)
        info_layout.addWidget(self.managed_row)
        info_layout.addWidget(self.version_row)
        info_layout.addStretch(1)
        status_layout.addWidget(info_card, 2)
        layout.addWidget(status_card)

        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.cpu_card = MetricCard("CPU usage", "--", "Waiting for samples", "cpuBar")
        self.ram_card = MetricCard("Memory", "--", "Waiting for samples", "ramBar")
        self.disk_card = MetricCard("Disk usage", "--", "Ubuntu storage", "diskBar")
        self.models_card = MetricCard("Local models", "--", "Discovering Ollama models")
        for widget in (self.cpu_card, self.ram_card, self.disk_card, self.models_card):
            metrics.addWidget(widget, 1)
        layout.addLayout(metrics)
        return container

    def _build_server_controls(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(make_label("Server controls", "sectionTitle"))
        header.addStretch(1)
        self.server_hint = make_label("Ollama API is checked before reporting online", "muted")
        header.addWidget(self.server_hint)
        layout.addLayout(header)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start_button = QPushButton("START SERVER")
        self.start_button.setObjectName("primaryButton")
        self.stop_button = QPushButton("STOP SERVER")
        self.stop_button.setObjectName("dangerButton")
        self.restart_button = QPushButton("RESTART SERVER")
        self.refresh_button = QPushButton("REFRESH STATUS")
        self.refresh_button.setObjectName("ghostButton")
        for button in (
            self.start_button,
            self.stop_button,
            self.restart_button,
            self.refresh_button,
        ):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.restart_button.clicked.connect(self.restart_server)
        self.refresh_button.clicked.connect(self.refresh_status)
        return card

    def _build_actions(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(14)
        layout.addWidget(make_label("Quick actions", "sectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(10)
        actions = [
            (
                "Select a local model",
                "SELECT MODEL",
                "models",
                "models.svg",
                self._select_model,
            ),
            (
                "Chat with BrightNova",
                "OPEN AI CHAT",
                "chat",
                "chat.svg",
                self._open_chat,
            ),
            (
                "Open the last project",
                "OPEN VSCODE",
                "projects",
                "projects.svg",
                self._open_vscode,
            ),
            (
                "Run OpenCode locally",
                "LAUNCH OPENCODE",
                "opencode",
                "opencode.svg",
                self._launch_opencode,
            ),
            (
                "Inspect live resources",
                "SYSTEM MONITOR",
                "monitor",
                "monitor.svg",
                self._open_monitor,
            ),
        ]
        for index, (tooltip, text, _page, icon, callback) in enumerate(actions):
            button = QPushButton(text)
            button.setObjectName("actionButton")
            button.setToolTip(tooltip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(62)
            button.setIcon(
                tinted_icon(self.context.asset("icons", icon), "#79ABFF", 20)
            )
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(callback)
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid)
        return card

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

    def _set_connecting(self) -> None:
        health = HealthResult(
            status=CONNECTING,
            message="Contacting the Ollama API...",
            managed_by=self.context.current_health.managed_by,
        )
        self.apply_health(health)

    def refresh_status(self) -> None:
        self._set_connecting()
        manager = self.context.ollama

        def done(health: HealthResult) -> None:
            self.context.set_health(health)

        self._start_task(manager.health, done, self._task_failed)

    def start_server(self) -> None:
        self._set_connecting()
        manager = self.context.ollama

        def done(result) -> None:
            health = manager.health()
            self.context.set_health(health)
            if result.ok:
                self.context.notify_user("Server online", result.message)
            else:
                self._result_failed(result)

        self._start_task(manager.start_server, done, self._task_failed)

    def stop_server(self) -> None:
        health = self.context.current_health
        if not health.online:
            self.refresh_status()
            return
        managed = health.managed_by
        if managed not in ("brightnova", "systemd"):
            QMessageBox.information(
                self,
                "Externally managed Ollama",
                "Ollama is running outside BrightNova. BrightNova will not terminate "
                "an unrelated process. Stop it from its owning terminal or service "
                "manager.",
            )
            return
        requires_confirmation = (
            managed == "brightnova"
            or self.context.settings.confirm_before_service_stop
        )
        if requires_confirmation:
            if managed == "systemd":
                prompt = (
                    "Ollama is managed by systemd and may be used by other "
                    "applications.\n\nStop the system service? Administrator "
                    "authentication may be required."
                )
            else:
                prompt = "Stop the Ollama process started by BrightNova?"
            answer = QMessageBox.question(
                self,
                "Stop Ollama",
                prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._set_connecting()
        manager = self.context.ollama

        def done(result) -> None:
            health = manager.health()
            self.context.set_health(health)
            if result.ok:
                self.context.notify_user("Server stopped", result.message)
            else:
                self._result_failed(result)

        self._start_task(
            lambda: manager.stop_server(allow_service_stop=managed == "systemd"),
            done,
            self._task_failed,
        )

    def restart_server(self) -> None:
        health = self.context.current_health
        if health.online:
            answer = QMessageBox.question(
                self,
                "Restart Ollama",
                "Restart the Ollama server? Active generation will be interrupted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._set_connecting()
        manager = self.context.ollama

        def done(result) -> None:
            health = manager.health()
            self.context.set_health(health)
            if result.ok:
                self.context.notify_user("Server restarted", result.message)
            else:
                self._result_failed(result)

        self._start_task(
            lambda: manager.restart_server(allow_service_stop=True),
            done,
            self._task_failed,
        )

    def _task_failed(self, message: str) -> None:
        self.refresh_status()
        QMessageBox.critical(self, "BrightNova operation failed", message)

    def _result_failed(self, result) -> None:
        detail = f"\n\n{result.detail}" if getattr(result, "detail", "") else ""
        QMessageBox.critical(self, "Ollama", f"{result.message}{detail}")

    def apply_health(self, health: HealthResult) -> None:
        state = {
            ONLINE: "online",
            OFFLINE: "offline",
            CONNECTING: "connecting",
        }.get(health.status, "offline")
        label = {
            "online": "BRIGHT NOVA IS ONLINE",
            "offline": "SERVER OFFLINE",
            "connecting": "CONNECTING",
        }[state]
        self.dot.setProperty("state", state)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        self.status_badge.set_state(state, label)
        if state == "online":
            self.server_headline.setText("Local intelligence is ready")
            self.server_detail.setText(
                "Ollama is responding to health checks. Models, chat, and project "
                "integration are available."
            )
        elif state == "connecting":
            self.server_headline.setText("Connecting to Ollama")
            self.server_detail.setText(
                "BrightNova is waiting for a successful API health check before "
                "marking the server online."
            )
        else:
            self.server_headline.setText("Server offline")
            self.server_detail.setText(
                health.message
                or "Start Ollama to unlock model management, chat, and project integration."
            )
        version = health.version or "Unavailable"
        self.version_row.set_value(version)
        self.managed_row.set_value(health.managed_by.capitalize())
        self.active_row.set_value(self.context.current_model() or "Not selected")
        online = state == "online"
        connecting = state == "connecting"
        self.start_button.setEnabled(not online and not connecting)
        self.stop_button.setEnabled(online)
        self.restart_button.setEnabled(not connecting)
        self.refresh_button.setEnabled(not connecting)

    def _models_changed(self, models) -> None:
        self.models_card.set_value(
            str(len(models)),
            detail="Installed locally" if models else "No models discovered",
        )
        self.active_row.set_value(self.context.current_model() or "Not selected")

    def _model_selected(self, model: str) -> None:
        self.active_row.set_value(model or "Not selected")

    def _monitor_changed(self, payload: MonitorPayload) -> None:
        sample = payload.sample
        self.cpu_card.set_value(
            f"{sample.cpu_percent:.0f}%",
            int(sample.cpu_percent),
            "Processor load",
        )
        self.ram_card.set_value(
            f"{sample.memory_percent:.0f}%",
            int(sample.memory_percent),
            f"{sample.memory_used / (1024 ** 3):.1f} GB of "
            f"{sample.memory_total / (1024 ** 3):.1f} GB",
        )
        self.disk_card.set_value(
            f"{sample.disk_percent:.0f}%",
            int(sample.disk_percent),
            f"{sample.disk_free / (1024 ** 3):.0f} GB free",
        )

    def _select_model(self) -> None:
        self.navigate("models")

    def _open_chat(self) -> None:
        self.navigate("chat")

    def _open_monitor(self) -> None:
        self.navigate("monitor")

    def _last_project_or_hint(self, action: str):
        project = self.context.store.last_project()
        if project:
            return project
        QMessageBox.information(
            self,
            "No project selected",
            f"Add a development project before using {action}.",
        )
        self.navigate("projects")
        return None

    def _open_vscode(self) -> None:
        project = self._last_project_or_hint("Open VS Code")
        if not project:
            return
        self._start_task(
            lambda: self.context.projects.open_vscode(project),
            lambda result: self.context.notify_user("VS Code", result.message),
            self._task_failed,
        )

    def _launch_opencode(self) -> None:
        project = self._last_project_or_hint("Launch OpenCode")
        if not project:
            return
        self._start_task(
            lambda: self.context.projects.launch_opencode(project),
            lambda result: self.context.notify_user(
                "OpenCode", result.message
            ),
            self._task_failed,
        )
