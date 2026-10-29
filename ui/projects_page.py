from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brightnova.config import Project
from brightnova.project_manager import ProjectError
from brightnova.workers import TaskWorker
from ui.widgets import (
    EmptyState,
    PageHeader,
    clear_layout,
    make_label,
)


logger = logging.getLogger(__name__)


class ProjectDialog(QDialog):
    def __init__(self, models, project: Project | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit project" if project else "Add project")
        self.setMinimumWidth(560)
        self.models = models
        self.result_project: Project | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(
            make_label("Development project", "sectionTitle")
        )
        layout.addWidget(
            make_label(
                "BrightNova stores project metadata locally and configures OpenCode "
                "inside the selected directory.",
                "muted",
                wrap=True,
            )
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.path_edit = QLineEdit(str(project.path) if project else "")
        self.path_edit.setPlaceholderText("/home/you/Projects/MyProject")
        browse = QPushButton("BROWSE")
        browse.setObjectName("smallButton")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        form.addRow(make_label("Project directory", "muted"), path_widget)
        self.name_edit = QLineEdit(project.name if project else "")
        self.name_edit.setPlaceholderText("Display name")
        form.addRow(make_label("Project name", "muted"), self.name_edit)
        self.model_combo = QComboBox()
        for model in models:
            self.model_combo.addItem(model.display_name, model.name)
        if project:
            index = self.model_combo.findData(project.model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            elif project.model:
                self.model_combo.addItem(project.model, project.model)
                self.model_combo.setCurrentIndex(self.model_combo.count() - 1)
        form.addRow(make_label("Local model", "muted"), self.model_combo)
        layout.addLayout(form)
        if not models:
            layout.addWidget(
                make_label(
                    "No local models are available. Start Ollama and refresh AI Models "
                    "before configuring a project.",
                    "muted",
                    wrap=True,
                )
            )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.edit_project = project

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select project directory",
            self.path_edit.text() or str(Path.home()),
        )
        if directory:
            self.path_edit.setText(directory)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(directory).name)

    def _accept(self) -> None:
        path_text = self.path_edit.text().strip()
        if not path_text:
            QMessageBox.warning(self, "Missing directory", "Choose a project directory.")
            return
        try:
            path = Path(path_text).expanduser().resolve(strict=True)
        except OSError:
            QMessageBox.warning(
                self,
                "Directory not found",
                "The selected project directory does not exist.",
            )
            return
        if not path.is_dir():
            QMessageBox.warning(self, "Invalid path", "The selected path is not a directory.")
            return
        model = self.model_combo.currentData()
        if not model:
            QMessageBox.warning(
                self,
                "No model available",
                "Start Ollama and load an installed model before adding a project.",
            )
            return
        name = self.name_edit.text().strip() or path.name
        existing = self.edit_project
        if existing:
            self.result_project = Project(
                id=existing.id,
                name=name,
                path=str(path),
                model=model,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )
        else:
            self.result_project = Project(
                id=uuid4().hex[:12],
                name=name,
                path=str(path),
                model=model,
            )
        self.accept()


class ProjectsPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self.workers: list[TaskWorker] = []
        self._build()
        self.context.projects_changed.connect(self.rebuild)
        self.rebuild()

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
        header = QHBoxLayout()
        header.addWidget(
            PageHeader(
                "Workspace",
                "Development Projects",
                "Connect local models to real codebases through OpenCode and VS Code.",
            ),
            1,
        )
        add_button = QPushButton("ADD PROJECT")
        add_button.setObjectName("primaryButton")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self.add_project)
        header.addWidget(add_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
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

    def rebuild(self) -> None:
        clear_layout(self.cards_layout)
        projects = self.context.settings.projects
        if not projects:
            self.cards_layout.addWidget(
                EmptyState(
                    "No development projects yet",
                    "Add a project directory to configure OpenCode with a local model, "
                    "open it in VS Code, and launch an AI-assisted coding session.",
                    "ADD PROJECT",
                    self.add_project,
                )
            )
            return
        for project in projects:
            self.cards_layout.addWidget(self._project_card(project))

    def _project_card(self, project: Project) -> QWidget:
        card = QFrame()
        card.setObjectName("projectCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(9)
        top.addWidget(make_label(project.name, "cardTitle"))
        model = next(
            (item for item in self.context.current_models if item.name == project.model),
            None,
        )
        top.addWidget(
            make_label(model.display_name if model else project.model, "roleTag")
        )
        top.addStretch(1)
        config_path = self.context.projects.config_path(project.path)
        if config_path.exists():
            top.addWidget(make_label("OPENCODE CONFIG", "tag"))
        else:
            top.addWidget(make_label("NOT CONFIGURED", "tag"))
        layout.addLayout(top)
        layout.addWidget(make_label(project.path, "mono", wrap=True))
        actions = QHBoxLayout()
        actions.setSpacing(8)
        vscode = self._button("OPEN IN VS CODE", lambda: self.open_vscode(project))
        opencode = self._button(
            "LAUNCH OPENCODE", lambda: self.launch_opencode(project), primary=True
        )
        configure = self._button(
            "CONFIGURE OPENCODE", lambda: self.configure_project(project)
        )
        if config_path.exists():
            actions.addWidget(
                self._button("VIEW CONFIG", lambda: self.view_config(config_path))
            )
        edit = self._button("EDIT", lambda: self.edit_project(project))
        remove = self._button(
            "REMOVE", lambda: self.remove_project(project), danger=True
        )
        actions.addWidget(vscode)
        actions.addWidget(opencode)
        actions.addWidget(configure)
        actions.addStretch(1)
        actions.addWidget(edit)
        actions.addWidget(remove)
        layout.addLayout(actions)
        return card

    def _button(self, text: str, callback, primary: bool = False, danger: bool = False):
        button = QPushButton(text)
        button.setObjectName(
            "primaryButton" if primary else "dangerButton" if danger else "smallButton"
        )
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def add_project(self) -> None:
        if not self.context.current_models:
            QMessageBox.information(
                self,
                "No local models",
                "Start Ollama and wait for the model library to load before adding a "
                "project.",
            )
            self.navigate("models")
            return
        dialog = ProjectDialog(self.context.current_models, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.result_project:
            return
        project = dialog.result_project
        saved = self.context.store.add_project(project)
        self.context.select_project(saved)
        self.context.projects_changed.emit()
        self.context.notify_user("Project added", f"{saved.name} is ready to configure.")

    def edit_project(self, project: Project) -> None:
        dialog = ProjectDialog(self.context.current_models, project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.result_project:
            return
        try:
            self.context.store.update_project(dialog.result_project)
        except KeyError:
            QMessageBox.warning(self, "Project missing", "This project no longer exists.")
            return
        self.context.projects_changed.emit()
        self.context.notify_user("Project updated", dialog.result_project.name)

    def remove_project(self, project: Project) -> None:
        answer = QMessageBox.question(
            self,
            "Remove project",
            f"Remove {project.name} from BrightNova?\n\nNo files or project "
            "configuration will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.context.store.remove_project(project.id)
        self.context.projects_changed.emit()
        self.context.notify_user("Project removed", project.name)

    def configure_project(self, project: Project) -> None:
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
                f"{config_path}\n\nThis file already exists. BrightNova will preserve "
                "other providers and settings, update the local Ollama provider, set "
                "the selected default model, and create a timestamped backup.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            allow_existing = True
        manager = self.context.projects
        models = [model.name for model in self.context.current_models]

        def done(result) -> None:
            backup = f"\nBackup: {result['backup']}" if result.get("backup") else ""
            self.context.projects_changed.emit()
            self.context.notify_user("OpenCode configured", f"Default model: {result['model']}")
            QMessageBox.information(
                self,
                "OpenCode configured",
                f"Configuration written to:\n{result['path']}\n\n"
                f"Default model: {result['model']}{backup}\n\n"
                "Launch OpenCode from this project to use the local model.",
            )

        self.context.notify_user(
            "Configuring project", f"Writing OpenCode configuration for {project.name}."
        )
        self._start_task(
            lambda: manager.configure(project, models, allow_existing=allow_existing),
            done,
            self._operation_failed,
        )

    def _config_is_ready(self, project: Project) -> bool:
        try:
            config = self.context.projects.read_config(project.path)
        except ProjectError:
            return False
        provider = config.get("provider") or {}
        ollama = provider.get("ollama") if isinstance(provider, dict) else None
        return bool(isinstance(ollama, dict) and ollama.get("models"))

    def open_vscode(self, project: Project) -> None:
        manager = self.context.projects
        self.context.select_project(project)
        self._start_task(
            lambda: manager.open_vscode(project),
            lambda result: self.context.notify_user("VS Code", result.message),
            self._operation_failed,
        )

    def launch_opencode(self, project: Project) -> None:
        if not self._config_is_ready(project):
            answer = QMessageBox.question(
                self,
                "OpenCode is not configured",
                "BrightNova has not verified a local Ollama provider for this project.\n\n"
                "Launch OpenCode anyway? The selected local model may not be available "
                "until you configure the project.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        manager = self.context.projects
        self.context.select_project(project)
        self._start_task(
            lambda: manager.launch_opencode(project),
            lambda result: self.context.notify_user("OpenCode", result.message),
            self._operation_failed,
        )

    def view_config(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _operation_failed(self, message: str) -> None:
        QMessageBox.critical(self, "BrightNova project error", message)
