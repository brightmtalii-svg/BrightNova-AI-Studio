from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brightnova.ollama_manager import OllamaError, OllamaModel, RunningModel
from brightnova.workers import TaskWorker
from ui.widgets import (
    EmptyState,
    PageHeader,
    clear_layout,
    make_label,
)


logger = logging.getLogger(__name__)


class ModelsPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self.workers: list[TaskWorker] = []
        self.models: list[OllamaModel] = []
        self.running: dict[str, RunningModel] = {}
        self.selection_buttons: dict[str, QPushButton] = {}
        self.unload_buttons: dict[str, QPushButton] = {}
        self._build()
        self.context.model_selected.connect(self._selection_changed)
        self.context.server_changed.connect(self._server_changed)
        self._selection_changed(self.context.current_model())

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

        header_row = QHBoxLayout()
        header_row.addWidget(
            PageHeader(
                "Model library",
                "AI Models",
                "Discover and manage the models installed in your local Ollama runtime.",
            ),
            1,
        )
        self.refresh_button = QPushButton("REFRESH MODELS")
        self.refresh_button.setObjectName("ghostButton")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)
        header_row.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header_row)

        self.status_label = make_label("Models have not been loaded yet.", "muted")
        layout.addWidget(self.status_label)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        layout.addWidget(self.cards_container)
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

    def refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self.status_label.setText("Contacting Ollama and loading model metadata...")
        manager = self.context.ollama

        def collect():
            models = manager.list_models()
            try:
                running = manager.running_models()
            except OllamaError:
                running = []
            return models, running

        def done(result) -> None:
            models, running = result
            self.refresh_button.setEnabled(True)
            self.models = models
            self.running = {model.name: model for model in running}
            self.status_label.setText(
                f"{len(models)} locally installed model(s). "
                "Loaded state comes directly from Ollama."
            )
            self.content_changed(models)
            if models and self.context.current_model() not in {
                model.name for model in models
            }:
                self.context.select_model(models[0].name, announce=False)
            self._rebuild()

        def failed(message: str) -> None:
            self.refresh_button.setEnabled(True)
            self.models = []
            self.running = {}
            self.status_label.setText(
                "Ollama is offline or unavailable. Start the server to discover models."
            )
            self.content_changed([])
            self._show_offline(message)

        self._start_task(collect, done, failed)

    def content_changed(self, models) -> None:
        self.context.set_models(list(models))

    def _show_offline(self, message: str) -> None:
        clear_layout(self.cards_layout)
        self.selection_buttons.clear()
        self.unload_buttons.clear()
        state = EmptyState(
            "Ollama is offline",
            f"{message}\n\nStart the local server to load your model library.",
            "START OLLAMA",
            self._start_server,
        )
        self.cards_layout.addWidget(state)

    def _start_server(self) -> None:
        manager = self.context.ollama
        self.status_label.setText("Starting Ollama...")

        def done(result) -> None:
            if result.ok:
                self.context.notify_user("Server online", result.message)
                self.refresh()
            else:
                detail = f"\n\n{result.detail}" if result.detail else ""
                QMessageBox.critical(
                    self, "Unable to start Ollama", f"{result.message}{detail}"
                )

        self._start_task(manager.start_server, done, self._operation_failed)

    def _rebuild(self) -> None:
        clear_layout(self.cards_layout)
        self.selection_buttons.clear()
        self.unload_buttons.clear()
        if not self.models:
            state = EmptyState(
                "No local models installed",
                "Install a model from a terminal with a command such as "
                "'ollama pull qwen2.5-coder:7b'. BrightNova never downloads models "
                "without confirmation.",
            )
            self.cards_layout.addWidget(state)
            return
        for model in self.models:
            self.cards_layout.addWidget(self._model_card(model))

    def _model_card(self, model: OllamaModel) -> QWidget:
        loaded = model.name in self.running
        card = QFrame()
        card.setObjectName("modelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(make_label(model.display_name, "cardTitle"))
        role = self._role_for(model.name)
        if role:
            title_row.addWidget(make_label(role, "roleTag"))
        if loaded:
            title_row.addWidget(make_label("LOADED", "loadedTag"))
        title_row.addStretch(1)
        layout.addLayout(title_row)

        technical = make_label(model.name, "mono")
        layout.addWidget(technical)

        metadata = QHBoxLayout()
        metadata.setSpacing(18)
        metadata.addWidget(make_label(f"Size  {model.size_label}", "muted"))
        if model.parameter_size:
            metadata.addWidget(make_label(f"Parameters  {model.parameter_size}", "muted"))
        if model.quantization:
            metadata.addWidget(make_label(f"Quantization  {model.quantization}", "muted"))
        metadata.addStretch(1)
        layout.addLayout(metadata)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        select_button = QPushButton("SELECT MODEL")
        select_button.setObjectName("smallButton")
        select_button.setCursor(Qt.CursorShape.PointingHandCursor)
        select_button.clicked.connect(lambda: self.select_model(model.name))
        run_button = QPushButton("RUN MODEL")
        run_button.setObjectName("smallButton")
        run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        run_button.clicked.connect(lambda: self.run_model(model.name))
        unload_button = QPushButton("UNLOAD MODEL")
        unload_button.setObjectName("smallButton")
        unload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        unload_button.setEnabled(loaded)
        unload_button.clicked.connect(lambda: self.unload_model(model.name))
        actions.addWidget(select_button)
        actions.addWidget(run_button)
        actions.addWidget(unload_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.selection_buttons[model.name] = select_button
        self.unload_buttons[model.name] = unload_button
        self._apply_selection(model.name, select_button)
        return card

    def _role_for(self, name: str) -> str:
        if name == "qwen2.5-coder:7b":
            return "MAIN CODING MODEL"
        if name == "qwen2.5-coder:3b":
            return "LIGHTWEIGHT CODING MODEL"
        return "LOCAL MODEL"

    def _apply_selection(self, name: str, button: QPushButton) -> None:
        if name == self.context.current_model():
            button.setText("ACTIVE MODEL")
            button.setEnabled(False)
        else:
            button.setText("SELECT MODEL")
            button.setEnabled(True)

    def _selection_changed(self, name: str) -> None:
        for model_name, button in self.selection_buttons.items():
            self._apply_selection(model_name, button)

    def select_model(self, name: str) -> None:
        self.context.select_model(name)
        self._selection_changed(name)

    def run_model(self, name: str) -> None:
        self.status_label.setText(f"Loading {name} into memory...")
        manager = self.context.ollama

        def done(result) -> None:
            self.context.notify_user(
                "Model loaded",
                f"{name} is ready. Keeping it loaded for 30 minutes.",
            )
            self.refresh()

        def failed(message: str) -> None:
            self.status_label.setText(f"Could not load {name}.")
            self._operation_failed(message)

        self._start_task(lambda: manager.load_model(name), done, failed)

    def unload_model(self, name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Unload model",
            f"Unload {name}? Any active generation using it will be interrupted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        manager = self.context.ollama
        self.status_label.setText(f"Unloading {name}...")

        def done(result) -> None:
            self.context.notify_user("Model unloaded", result.message)
            self.refresh()

        self._start_task(lambda: manager.unload_model(name), done, self._operation_failed)

    def _operation_failed(self, message: str) -> None:
        QMessageBox.critical(self, "BrightNova", message)

    def _server_changed(self, health) -> None:
        if not health.online and not self.models:
            self.status_label.setText(
                "Ollama is offline. Start the server to discover local models."
            )
