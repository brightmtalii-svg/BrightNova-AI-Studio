from __future__ import annotations


from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from brightnova.config import APP_VERSION, DEFAULT_SYSTEM_PROMPT
from ui.widgets import InfoRow, PageHeader, make_label
from brightnova.logging_setup import setup_logging


class SettingsPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self._build()
        self.context.models_changed.connect(self._models_changed)
        self.context.model_selected.connect(self._sync_model)
        self._sync_model(self.context.current_model())

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
                "Preferences",
                "Settings",
                "Persistent local configuration for BrightNova and its Ollama runtime.",
            )
        )

        assistant_card = QFrame()
        assistant_card.setObjectName("card")
        assistant_layout = QVBoxLayout(assistant_card)
        assistant_layout.setContentsMargins(24, 20, 24, 22)
        assistant_layout.setSpacing(12)
        assistant_layout.addWidget(make_label("Assistant behavior", "sectionTitle"))
        assistant_layout.addWidget(
            make_label(
                "This system prompt is applied when a new chat session starts.",
                "muted",
            )
        )
        self.system_prompt = QTextEdit()
        self.system_prompt.setPlainText(self.context.settings.system_prompt)
        self.system_prompt.setMinimumHeight(130)
        assistant_layout.addWidget(self.system_prompt)
        reset_prompt = QPushButton("RESTORE DEFAULT PROMPT")
        reset_prompt.setObjectName("ghostButton")
        reset_prompt.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_prompt.clicked.connect(
            lambda: self.system_prompt.setPlainText(DEFAULT_SYSTEM_PROMPT)
        )
        assistant_layout.addWidget(reset_prompt, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(assistant_card)

        runtime_card = QFrame()
        runtime_card.setObjectName("card")
        runtime_layout = QVBoxLayout(runtime_card)
        runtime_layout.setContentsMargins(24, 20, 24, 22)
        runtime_layout.setSpacing(12)
        runtime_layout.addWidget(make_label("Runtime", "sectionTitle"))
        model_row = QHBoxLayout()
        model_row.addWidget(make_label("Default local model", "muted"))
        model_row.addStretch(1)
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(280)
        self.model_combo.currentIndexChanged.connect(self._model_combo_changed)
        model_row.addWidget(self.model_combo)
        runtime_layout.addLayout(model_row)
        interval_row = QHBoxLayout()
        interval_row.addWidget(make_label("Monitor refresh interval", "muted"))
        interval_row.addStretch(1)
        self.interval = QSpinBox()
        self.interval.setRange(1, 10)
        self.interval.setSuffix(" seconds")
        self.interval.setValue(
            int(round(self.context.settings.refresh_interval_seconds))
        )
        interval_row.addWidget(self.interval)
        runtime_layout.addLayout(interval_row)
        confirm_row = QHBoxLayout()
        confirm_row.addWidget(
            make_label("Confirm before stopping the systemd Ollama service", "muted")
        )
        confirm_row.addStretch(1)
        self.confirm_stop = QCheckBox()
        self.confirm_stop.setChecked(self.context.settings.confirm_before_service_stop)
        confirm_row.addWidget(self.confirm_stop)
        runtime_layout.addLayout(confirm_row)
        self.endpoint_row = InfoRow(
            "Ollama API endpoint", self.context.settings.ollama_host, mono=True
        )
        runtime_layout.addWidget(self.endpoint_row)
        runtime_layout.addWidget(
            make_label(
                "The endpoint is intentionally local. BrightNova does not expose "
                "Ollama to the public internet.",
                "muted",
                wrap=True,
            )
        )
        layout.addWidget(runtime_card)

        storage_card = QFrame()
        storage_card.setObjectName("card")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(24, 20, 24, 22)
        storage_layout.setSpacing(10)
        storage_layout.addWidget(make_label("Local storage", "sectionTitle"))
        self.config_row = InfoRow("Settings file", str(self.context.store.path), mono=True)
        self.config_dir_row = InfoRow(
            "Configuration directory", str(self.context.store.directory), mono=True
        )
        self.log_row = InfoRow(
            "Log file", str(self.context.store.directory / "logs" / "brightnova.log"), mono=True
        )
        storage_layout.addWidget(self.config_row)
        storage_layout.addWidget(self.config_dir_row)
        storage_layout.addWidget(self.log_row)
        storage_actions = QHBoxLayout()
        storage_actions.setSpacing(8)
        open_config = QPushButton("OPEN CONFIG FOLDER")
        open_config.setObjectName("ghostButton")
        open_config.setCursor(Qt.CursorShape.PointingHandCursor)
        open_config.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.context.store.directory))
            )
        )
        open_logs = QPushButton("OPEN LOG FOLDER")
        open_logs.setObjectName("ghostButton")
        open_logs.setCursor(Qt.CursorShape.PointingHandCursor)
        open_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.context.store.directory / "logs"))
            )
        )
        storage_actions.addWidget(open_config)
        storage_actions.addWidget(open_logs)
        storage_actions.addStretch(1)
        storage_layout.addLayout(storage_actions)
        layout.addWidget(storage_card)

        privacy_card = QFrame()
        privacy_card.setObjectName("card")
        privacy_layout = QVBoxLayout(privacy_card)
        privacy_layout.setContentsMargins(24, 20, 24, 22)
        privacy_layout.setSpacing(8)
        privacy_layout.addWidget(make_label("Privacy and cost", "sectionTitle"))
        privacy_layout.addWidget(
            make_label(
                "All model communication stays on localhost through Ollama. "
                "BrightNova uses no paid API keys, cloud inference, telemetry, or "
                "automatic model downloads.",
                "muted",
                wrap=True,
            )
        )
        privacy_layout.addWidget(
            make_label(f"BrightNova version {APP_VERSION}", "muted")
        )
        layout.addWidget(privacy_card)
        layout.addStretch(1)

        footer = QHBoxLayout()
        self.saved_label = make_label("", "muted")
        footer.addWidget(self.saved_label)
        footer.addStretch(1)
        save_button = QPushButton("SAVE SETTINGS")
        save_button.setObjectName("primaryButton")
        save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        save_button.clicked.connect(self.save)
        footer.addWidget(save_button)
        layout.addLayout(footer)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _models_changed(self, models) -> None:
        current = self.context.current_model()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model.display_name, model.name)
        index = self.model_combo.findData(current)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        elif models:
            self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)

    def _sync_model(self, name: str) -> None:
        index = self.model_combo.findData(name)
        if index >= 0 and index != self.model_combo.currentIndex():
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentIndex(index)
            self.model_combo.blockSignals(False)

    def _model_combo_changed(self, _index: int) -> None:
        model = self.model_combo.currentData()
        if model:
            self.context.select_model(model, announce=False)

    def save(self) -> None:
        prompt = self.system_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(
                self,
                "System prompt required",
                "Keep a system prompt or restore the default before saving.",
            )
            return
        model = self.model_combo.currentData()
        if model:
            self.context.settings.selected_model = model
        self.context.settings.system_prompt = prompt
        self.context.settings.refresh_interval_seconds = float(self.interval.value())
        self.context.settings.confirm_before_service_stop = self.confirm_stop.isChecked()
        self.context.save()
        self.context.model_selected.emit(self.context.settings.selected_model)
        self.context.settings_changed.emit()
        self.saved_label.setText("Settings saved. New chat sessions use the updated prompt.")
        self.context.notify_user(
            "Settings saved", "Local preferences were written successfully."
        )
        try:
            setup_logging()
        except OSError:
            pass
