from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from brightnova.config import APP_NAME, APP_VERSION, ConfigStore
from brightnova.context import AppContext
from brightnova.logging_setup import setup_logging
from ui.main_window import MainWindow


ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _load_stylesheet(application: QApplication) -> None:
    path = ROOT / "ui" / "styles.qss"
    try:
        application.setStyleSheet(path.read_text(encoding="utf-8"))
    except OSError:
        logger.exception("Unable to load stylesheet from %s", path)


def _application_font() -> QFont:
    available = set(QFontDatabase.families())
    for family in ("Inter", "Ubuntu", "Noto Sans", "DejaVu Sans"):
        if family in available:
            font = QFont(family)
            font.setPointSize(10)
            return font
    return QFont()


def _install_exception_hook(application: QApplication) -> None:
    def handle(exc_type, exc_value, exc_traceback) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.critical("Unhandled exception:\n%s", text)
        QMessageBox.critical(
            None,
            "BrightNova encountered an error",
            f"{exc_value}\n\nDetails were written to the BrightNova log file.",
        )

    sys.excepthook = handle


def main() -> int:
    setup_logging()
    logger.info("Starting %s %s", APP_NAME, APP_VERSION)
    application = QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    application.setOrganizationName("BrightNova")
    application.setDesktopFileName("brightnova")
    application.setStyle("Fusion")
    application.setFont(_application_font())
    application.setWindowIcon(QIcon(str(ROOT / "assets" / "icons" / "logo.svg")))
    _load_stylesheet(application)
    _install_exception_hook(application)
    try:
        store = ConfigStore()
        context = AppContext(store)
    except Exception as exc:
        logger.exception("Unable to initialize BrightNova")
        QMessageBox.critical(
            None,
            "BrightNova could not start",
            f"{exc}\n\nCheck the dependency installation and try again.",
        )
        return 1
    if store.last_error:
        logger.warning("Settings were reset: %s", store.last_error)
    window = MainWindow(context)
    window.show()
    logger.info("Interface ready")
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
