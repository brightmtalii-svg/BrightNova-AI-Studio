from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from brightnova.config import APP_NAME, APP_VERSION, TAGLINE
from brightnova.ollama_manager import HealthResult
from brightnova.workers import MonitorWorker, TaskWorker
from ui.about_page import AboutPage
from ui.chat_page import ChatPage
from ui.dashboard import DashboardPage
from ui.models_page import ModelsPage
from ui.monitor_page import MonitorPage
from ui.opencode_page import OpenCodePage
from ui.projects_page import ProjectsPage
from ui.settings_page import SettingsPage
from ui.widgets import NavButton, StatusBadge, make_label


logger = logging.getLogger(__name__)


PAGE_DEFINITIONS = [
    ("dashboard", "Dashboard", "dashboard.svg", "WORKSPACE"),
    ("models", "AI Models", "models.svg", ""),
    ("chat", "AI Chat", "chat.svg", ""),
    ("projects", "Development Projects", "projects.svg", "BUILD"),
    ("opencode", "OpenCode Integration", "opencode.svg", ""),
    ("monitor", "System Monitor", "monitor.svg", ""),
    ("settings", "Settings", "settings.svg", "SYSTEM"),
    ("about", "About BrightNova", "about.svg", ""),
]


class MainWindow(QMainWindow):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.workers: list[TaskWorker] = []
        self.health_busy = False
        self.models_busy = False
        self.monitor_worker: MonitorWorker | None = None
        self.pages = {}
        self.nav_buttons = {}
        self._build()
        self._connect_context()
        self._start_monitor()
        QTimer.singleShot(250, self.check_health)
        QTimer.singleShot(1500, self.load_models)
        self.health_timer = QTimer(self)
        self.health_timer.setInterval(10_000)
        self.health_timer.timeout.connect(self.check_health)
        self.health_timer.start()
        self.models_timer = QTimer(self)
        self.models_timer.setInterval(60_000)
        self.models_timer.timeout.connect(self.load_models)
        self.models_timer.start()
        self.navigate("dashboard")

    def _build(self) -> None:
        self.setWindowTitle(f"{APP_NAME} — {TAGLINE}")
        icon_path = self.context.asset("icons", "logo.svg")
        self.setWindowIcon(QIcon(icon_path))
        self.resize(
            self.context.settings.window_width,
            self.context.settings.window_height,
        )
        self.setMinimumSize(1100, 720)
        root = QWidget()
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.pages = {
            "dashboard": DashboardPage(self.context, self.navigate),
            "models": ModelsPage(self.context, self.navigate),
            "chat": ChatPage(self.context, self.navigate),
            "projects": ProjectsPage(self.context, self.navigate),
            "opencode": OpenCodePage(self.context, self.navigate),
            "monitor": MonitorPage(self.context, self.navigate),
            "settings": SettingsPage(self.context, self.navigate),
            "about": AboutPage(self.context, self.navigate),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.toast = QFrame(self)
        self.toast.setObjectName("toast")
        self.toast.setFixedWidth(360)
        toast_layout = QVBoxLayout(self.toast)
        toast_layout.setContentsMargins(15, 12, 15, 13)
        toast_layout.setSpacing(3)
        self.toast_title = make_label("", "toastTitle")
        self.toast_body = make_label("", "toastBody", wrap=True)
        toast_layout.addWidget(self.toast_title)
        toast_layout.addWidget(self.toast_body)
        self.toast_hide_timer = QTimer(self)
        self.toast_hide_timer.setSingleShot(True)
        self.toast_hide_timer.timeout.connect(self.toast.hide)
        self.toast.hide()

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(246)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 16)
        layout.setSpacing(8)

        brand = QHBoxLayout()
        brand.setSpacing(11)
        logo = QLabel()
        pixmap = QPixmap(self.context.asset("icons", "logo.svg"))
        logo.setPixmap(
            pixmap.scaled(
                38,
                38,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setFixedSize(38, 38)
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(make_label("BRIGHTNOVA", "brandTitle"))
        brand_text.addWidget(make_label("AI STUDIO", "brandSubtitle"))
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        last_section = ""
        for key, label, icon, section in PAGE_DEFINITIONS:
            if section and section != last_section:
                layout.addSpacing(6)
                layout.addWidget(make_label(section, "sidebarSection"))
                last_section = section
            button = NavButton(label, self.context.asset("icons", icon))
            button.clicked.connect(lambda _checked=False, target=key: self.navigate(target))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch(1)

        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(13, 11, 13, 11)
        status_layout.setSpacing(6)
        status_row = QHBoxLayout()
        status_row.setSpacing(7)
        self.sidebar_dot = make_label("●", "statusDot")
        self.sidebar_status = StatusBadge("SERVER OFFLINE")
        status_row.addWidget(self.sidebar_dot)
        status_row.addWidget(self.sidebar_status)
        status_row.addStretch(1)
        status_layout.addLayout(status_row)
        self.sidebar_model = make_label(
            self.context.current_model() or "No model selected", "mono"
        )
        self.sidebar_model.setWordWrap(True)
        status_layout.addWidget(self.sidebar_model)
        layout.addWidget(status_card)
        layout.addSpacing(8)
        layout.addWidget(make_label(TAGLINE, "sidebarFooter"))
        layout.addWidget(make_label(f"Version {APP_VERSION}", "sidebarFooter"))
        return sidebar

    def _connect_context(self) -> None:
        self.context.server_changed.connect(self._server_changed)
        self.context.model_selected.connect(self._model_selected)
        self.context.notify.connect(self.show_toast)
        self.context.settings_changed.connect(self._settings_changed)
        self._server_changed(self.context.current_health)

    def navigate(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        button = self.nav_buttons.get(key)
        if button:
            button.setChecked(True)
        if key == "models":
            page.refresh()
        if key == "opencode":
            page.refresh()

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

    def check_health(self) -> None:
        if self.health_busy:
            return
        self.health_busy = True

        def done(health: HealthResult) -> None:
            self.health_busy = False
            self.context.set_health(health)
            if health.online and not self.context.current_models:
                self.load_models()

        def failed(message: str) -> None:
            self.health_busy = False
            logger.warning("Health check failed: %s", message)

        self._start_task(self.context.ollama.health, done, failed)

    def load_models(self) -> None:
        if self.models_busy or not self.context.current_health.online:
            return
        self.models_busy = True

        def done(models) -> None:
            self.models_busy = False
            self.context.set_models(list(models))

        def failed(message: str) -> None:
            self.models_busy = False
            logger.debug("Model discovery failed: %s", message)

        self._start_task(self.context.ollama.list_models, done, failed)

    def _start_monitor(self) -> None:
        if self.monitor_worker is not None:
            previous = self.monitor_worker
            previous.stop()
            previous.finished.connect(previous.deleteLater)
            if not previous.wait(3000):
                logger.warning("Previous monitor worker is still stopping")
        worker = MonitorWorker(
            self.context.monitor,
            self.context.ollama,
            self.context.settings.refresh_interval_seconds,
            self,
        )
        self.monitor_worker = worker
        worker.sample_ready.connect(self.context.monitor_updated)
        worker.failed.connect(
            lambda message: logger.warning("System monitor failed: %s", message)
        )
        worker.start()

    def _settings_changed(self) -> None:
        self._start_monitor()

    def _server_changed(self, health: HealthResult) -> None:
        state = {
            "ONLINE": "online",
            "OFFLINE": "offline",
            "CONNECTING": "connecting",
        }.get(health.status, "offline")
        label = {
            "online": "ONLINE",
            "offline": "OFFLINE",
            "connecting": "CONNECTING",
        }[state]
        self.sidebar_dot.setProperty("state", state)
        self.sidebar_dot.style().unpolish(self.sidebar_dot)
        self.sidebar_dot.style().polish(self.sidebar_dot)
        self.sidebar_status.set_state(state, label)
        if health.online:
            self.sidebar_model.setText(self.context.current_model() or "No model selected")
        else:
            self.sidebar_model.setText("Ollama API unavailable")

    def _model_selected(self, model: str) -> None:
        self.sidebar_model.setText(model if self.context.current_health.online else "Ollama API unavailable")

    def show_toast(self, title: str, message: str) -> None:
        self.toast_title.setText(title)
        self.toast_body.setText(message)
        self.toast.adjustSize()
        self._position_toast()
        self.toast.show()
        self.toast.raise_()
        self.toast_hide_timer.start(5000)

    def _position_toast(self) -> None:
        if not hasattr(self, "toast"):
            return
        self.toast.adjustSize()
        margin = 24
        x = max(margin, self.width() - self.toast.width() - margin)
        y = max(margin, self.height() - self.toast.height() - margin)
        self.toast.move(x, y)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_toast()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.isMaximized():
            self.context.settings.window_width = max(1100, self.width())
            self.context.settings.window_height = max(720, self.height())
        try:
            self.context.save()
        except OSError:
            logger.exception("Unable to save window settings")
        self.health_timer.stop()
        self.models_timer.stop()
        chat = self.pages.get("chat")
        if chat is not None and chat.chat_worker is not None:
            chat.chat_worker.cancel()
            chat.chat_worker.wait(2500)
        if self.monitor_worker is not None:
            self.monitor_worker.stop()
            self.monitor_worker.wait(3000)
        for worker in list(self.workers):
            worker.requestInterruption()
            worker.wait(300)
        for page in self.pages.values():
            for worker in list(getattr(page, "workers", [])):
                worker.requestInterruption()
                worker.wait(300)
        self.context.ollama.shutdown()
        logger.info("BrightNova shutting down")
        event.accept()
