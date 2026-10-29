from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from brightnova.workers import ChatWorker, TaskWorker
from ui.widgets import PageHeader, make_label


logger = logging.getLogger(__name__)


class ChatPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self.workers: list[TaskWorker] = []
        self.chat_worker: ChatWorker | None = None
        self.history: list[dict[str, str]] = []
        self.current_response = ""
        self.current_bubble: QLabel | None = None
        self.current_copy: QPushButton | None = None
        self._discarding = False
        self._build()
        self.context.models_changed.connect(self._models_changed)
        self.context.model_selected.connect(self._sync_combo)
        self._load_models()
        self._reset_history()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.addWidget(
            PageHeader(
                "Local conversation",
                "AI Chat",
                "A focused coding mentor running entirely on your machine.",
            ),
            1,
        )
        model_layout = QVBoxLayout()
        model_layout.setSpacing(5)
        model_layout.addWidget(make_label("MODEL", "eyebrow"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(260)
        self.model_combo.currentIndexChanged.connect(self._combo_changed)
        model_layout.addWidget(self.model_combo)
        header_row.addLayout(model_layout)
        self.copy_button = QPushButton("COPY LAST")
        self.copy_button.setObjectName("ghostButton")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self.copy_last)
        header_row.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignBottom)
        self.clear_button = QPushButton("CLEAR")
        self.clear_button.setObjectName("ghostButton")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_conversation)
        header_row.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(header_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_widget = QWidget()
        self.messages_widget.setObjectName("pageBody")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(8, 8, 14, 8)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch(1)
        self.scroll.setWidget(self.messages_widget)
        layout.addWidget(self.scroll, 1)

        composer = QFrame()
        composer.setObjectName("chatComposer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(14, 12, 14, 12)
        composer_layout.setSpacing(8)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Ask about a bug, an architecture decision, or a concept..."
        )
        self.input.setMinimumHeight(70)
        self.input.setMaximumHeight(150)
        self.input.setTabChangesFocus(True)
        composer_layout.addWidget(self.input)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.hint = make_label("Enter to send  ·  Shift+Enter for a new line", "muted")
        footer.addWidget(self.hint)
        footer.addStretch(1)
        self.stop_button = QPushButton("STOP")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_generation)
        footer.addWidget(self.stop_button)
        self.send_button = QPushButton("SEND")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_message)
        footer.addWidget(self.send_button)
        composer_layout.addLayout(footer)
        layout.addWidget(composer)

        install_shortcut = getattr(self.input, "installEventFilter", None)
        if install_shortcut:
            self.input.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.input and event.type() == QEvent.Type.KeyPress:
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self.send_message()
                return True
        return super().eventFilter(watched, event)

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

    def _load_models(self) -> None:
        manager = self.context.ollama

        def done(models) -> None:
            self.context.set_models(list(models))

        self._start_task(manager.list_models, done, lambda _message: None)

    def _models_changed(self, models) -> None:
        current = self.context.current_model()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem("No local models available", "")
            self.model_combo.setEnabled(False)
            self.send_button.setEnabled(False)
        else:
            self.model_combo.setEnabled(True)
            self.send_button.setEnabled(self.chat_worker is None)
            for model in models:
                self.model_combo.addItem(model.display_name, model.name)
            index = self.model_combo.findData(current)
            if index < 0:
                index = 0
                self.context.select_model(self.model_combo.itemData(0), announce=False)
            self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)

    def _sync_combo(self, name: str) -> None:
        index = self.model_combo.findData(name)
        if index >= 0 and index != self.model_combo.currentIndex():
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentIndex(index)
            self.model_combo.blockSignals(False)

    def _combo_changed(self, _index: int) -> None:
        model = self.model_combo.currentData()
        if model:
            self.context.select_model(model, announce=False)

    def _reset_history(self) -> None:
        self.history = []
        prompt = self.context.settings.system_prompt.strip()
        if prompt:
            self.history.append({"role": "system", "content": prompt})
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._add_welcome()

    def _add_welcome(self) -> None:
        welcome = QFrame()
        welcome.setObjectName("card")
        layout = QVBoxLayout(welcome)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(8)
        layout.addWidget(make_label("BrightNova is ready.", "welcomeTitle"))
        layout.addWidget(
            make_label(
                "Ask for a code review, a debugging strategy, or an explanation of a "
                "software engineering concept. Everything stays local through Ollama.",
                "welcomeBody",
                wrap=True,
            )
        )
        layout.addSpacing(4)
        layout.addWidget(
            make_label(
                "The mentor is configured to teach first and generate second.",
                "muted",
                wrap=True,
            )
        )
        self.messages_layout.insertWidget(0, welcome)

    def _remove_welcome(self) -> None:
        first = self.messages_layout.itemAt(0)
        if first and first.widget() and first.widget().objectName() == "card":
            first.widget().deleteLater()
            self.messages_layout.takeAt(0)

    def _bubble(
        self, role: str, text: str, markdown: bool = True
    ) -> tuple[QFrame, QLabel, QPushButton | None]:
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)
        bubble = QFrame()
        bubble.setObjectName("userBubble" if role == "user" else "assistantBubble")
        bubble.setMaximumWidth(830)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(18, 13, 18, 14)
        bubble_layout.setSpacing(7)
        role_label = "YOU" if role == "user" else "BRIGHTNOVA"
        bubble_layout.addWidget(make_label(role_label, "bubbleRole"))
        body = QLabel(text)
        body.setObjectName("bubbleText")
        body.setWordWrap(True)
        body.setTextFormat(
            Qt.TextFormat.MarkdownText if markdown else Qt.TextFormat.PlainText
        )
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        body.setOpenExternalLinks(True)
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        bubble_layout.addWidget(body)
        copy_button = None
        if role == "assistant":
            copy_button = QPushButton("COPY")
            copy_button.setObjectName("smallButton")
            copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_button.setMaximumWidth(76)
            copy_button.clicked.connect(lambda: self._copy_text(body.text()))
            bubble_layout.addWidget(copy_button, 0, Qt.AlignmentFlag.AlignRight)
        if role == "user":
            wrapper_layout.addStretch(1)
            wrapper_layout.addWidget(bubble)
        else:
            wrapper_layout.addWidget(bubble)
            wrapper_layout.addStretch(1)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, wrapper)
        self._scroll_to_bottom()
        return bubble, body, copy_button

    def _add_message(self, role: str, text: str) -> None:
        self._remove_welcome()
        self._bubble(role, text, markdown=role == "assistant")

    def send_message(self) -> None:
        if self.chat_worker is not None:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        model = self.model_combo.currentData()
        if not model:
            QMessageBox.warning(
                self,
                "No model selected",
                "Start Ollama and select an installed model before chatting.",
            )
            return
        self._remove_welcome()
        self.history.append({"role": "user", "content": text})
        self._add_message("user", text)
        self.input.clear()
        self._begin_generation(model)

    def _begin_generation(self, model: str) -> None:
        self._discarding = False
        self.current_response = ""
        _, body, copy_button = self._bubble("assistant", "Thinking locally...", markdown=True)
        self.current_bubble = body
        self.current_copy = copy_button
        self.send_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.input.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.model_combo.setEnabled(False)
        worker = ChatWorker(self.context.ollama, model, list(self.history), self)
        self.chat_worker = worker
        worker.chunk.connect(self._on_chunk)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(self._cleanup_worker)
        worker.start()

    def _on_chunk(self, chunk: str) -> None:
        if self._discarding:
            return
        self.current_response += chunk
        if self.current_bubble is not None:
            self.current_bubble.setText(self.current_response)
        self._scroll_to_bottom()

    def _on_completed(self, text: str) -> None:
        if self._discarding:
            return
        final = text or self.current_response
        if not final.strip():
            final = "_The model returned an empty response._"
        if self.current_bubble is not None:
            self.current_bubble.setText(final)
        if text.strip():
            self.history.append({"role": "assistant", "content": text})
        self._scroll_to_bottom()

    def _on_failed(self, message: str) -> None:
        if self._discarding:
            return
        if self.current_bubble is not None:
            self.current_bubble.setText(f"**Request failed**\n\n{message}")
        self.context.notify_user("Chat request failed", message)

    def _on_cancelled(self) -> None:
        if self._discarding:
            return
        if self.current_response.strip():
            self.history.append({"role": "assistant", "content": self.current_response})
            if self.current_bubble is not None:
                self.current_bubble.setText(
                    self.current_response + "\n\n_Generation stopped._"
                )
        elif self.current_bubble is not None:
            self.current_bubble.setText("_Generation stopped._")

    def _cleanup_worker(self) -> None:
        if self.chat_worker is not None:
            self.chat_worker.deleteLater()
        self.chat_worker = None
        self.current_bubble = None
        self.current_copy = None
        self._discarding = False
        self.send_button.setEnabled(self.model_combo.count() > 0)
        self.stop_button.setEnabled(False)
        self.input.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.model_combo.setEnabled(self.model_combo.count() > 0)
        self.input.setFocus()

    def stop_generation(self) -> None:
        if self.chat_worker is not None:
            self.stop_button.setEnabled(False)
            self.chat_worker.cancel()

    def clear_conversation(self) -> None:
        if self.chat_worker is not None:
            answer = QMessageBox.question(
                self,
                "Clear conversation",
                "Stop the current response and clear this conversation?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._discarding = True
            self.current_bubble = None
            self.current_copy = None
            self.chat_worker.cancel()
        elif len(self.history) > 1:
            answer = QMessageBox.question(
                self,
                "Clear conversation",
                "Clear the current conversation history?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._reset_history()
        self.context.notify_user("Conversation cleared", "A fresh session is ready.")

    def copy_last(self) -> None:
        for item in reversed(self.history):
            if item.get("role") == "assistant" and item.get("content"):
                self._copy_text(item["content"])
                return
        self.context.notify_user("Nothing to copy", "There is no response yet.")

    def _copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.context.notify_user("Copied", "Response copied to the clipboard.")

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )
