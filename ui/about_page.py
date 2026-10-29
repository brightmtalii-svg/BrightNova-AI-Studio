from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from brightnova.config import APP_NAME, APP_VERSION, TAGLINE
from ui.widgets import InfoRow, PageHeader, make_label


class AboutPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self._build()
        self.context.models_changed.connect(self._models_changed)

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
                "Product",
                "About BrightNova",
                "A private, local-first AI development studio built for teaching and "
                "software craft.",
            )
        )

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(28, 24, 28, 24)
        hero_layout.setSpacing(24)
        logo = QLabel()
        pixmap = QPixmap(self.context.asset("icons", "logo.svg"))
        logo.setPixmap(
            pixmap.scaled(
                112,
                112,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setFixedSize(112, 112)
        hero_layout.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(make_label(APP_NAME, "heroTitle"))
        text.addWidget(make_label(TAGLINE, "heroSubtitle"))
        text.addWidget(
            make_label(
                "BrightNova turns a local Ollama runtime into a complete development "
                "workbench: model control, a streaming coding mentor, project-aware "
                "OpenCode integration, and live system telemetry.",
                "muted",
                wrap=True,
            )
        )
        chips = QHBoxLayout()
        chips.setSpacing(8)
        for item in ("LOCAL-FIRST", "ZERO API COST", "OPEN SOURCE"):
            chips.addWidget(make_label(item, "tag"))
        chips.addStretch(1)
        text.addLayout(chips)
        text.addStretch(1)
        hero_layout.addLayout(text, 1)
        layout.addWidget(hero)

        cards = QGridLayout()
        cards.setSpacing(14)
        cards.addWidget(
            self._feature_card(
                "Local intelligence",
                "All inference is routed to Ollama on localhost. No prompts, code, "
                "or telemetry leave the machine.",
            ),
            0,
            0,
        )
        cards.addWidget(
            self._feature_card(
                "Teaching mindset",
                "The default mentor prompt prioritizes understanding, debugging, and "
                "engineering judgment over blind code generation.",
            ),
            0,
            1,
        )
        cards.addWidget(
            self._feature_card(
                "Toolchain integration",
                "Projects receive an OpenAI-compatible local provider for OpenCode "
                "while existing configuration is preserved and backed up.",
            ),
            1,
            0,
        )
        cards.addWidget(
            self._feature_card(
                "Operational clarity",
                "Every server state comes from a real health check. Model load state "
                "and memory telemetry come from the Ollama API.",
            ),
            1,
            1,
        )
        layout.addLayout(cards)

        details = QFrame()
        details.setObjectName("card")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(24, 20, 24, 22)
        details_layout.setSpacing(10)
        details_layout.addWidget(make_label("This build", "sectionTitle"))
        details_layout.addWidget(
            InfoRow("BrightNova", f"Version {APP_VERSION}", mono=True)
        )
        details_layout.addWidget(
            InfoRow("Python", platform.python_version(), mono=True)
        )
        details_layout.addWidget(
            InfoRow("PySide6", PySide6.__version__, mono=True)
        )
        details_layout.addWidget(
            InfoRow("Platform", platform.platform(), mono=True)
        )
        self.models_row = InfoRow(
            "Local models", str(len(self.context.current_models)), mono=True
        )
        details_layout.addWidget(self.models_row)
        layout.addWidget(details)

        privacy = QFrame()
        privacy.setObjectName("card")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(24, 20, 24, 22)
        privacy_layout.setSpacing(8)
        privacy_layout.addWidget(make_label("Privacy by architecture", "sectionTitle"))
        privacy_layout.addWidget(
            make_label(
                "BrightNova binds to the local Ollama endpoint at 127.0.0.1:11434, "
                "stores settings under your home directory, and never installs models "
                "or software automatically. You remain in control of every process "
                "and file change.",
                "muted",
                wrap=True,
            )
        )
        layout.addWidget(privacy)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _feature_card(self, title: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 20)
        layout.setSpacing(7)
        layout.addWidget(make_label(title, "cardTitle"))
        layout.addWidget(make_label(body, "muted", wrap=True))
        layout.addStretch(1)
        return card

    def _models_changed(self, models) -> None:
        self.models_row.set_value(str(len(models)))
