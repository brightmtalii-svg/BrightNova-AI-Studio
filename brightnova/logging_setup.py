from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import config_dir


def setup_logging(level: int = logging.INFO) -> Path:
    directory = config_dir() / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "brightnova.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(handler, logging.handlers.RotatingFileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_path
        for handler in root.handlers
    ):
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    if not any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    ):
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)
    return log_path
