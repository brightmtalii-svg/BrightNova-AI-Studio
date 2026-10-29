from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child is not None:
            clear_layout(child)


def make_label(
    text: str,
    object_name: str = "",
    wrap: bool = False,
    alignment: Qt.AlignmentFlag | None = None,
) -> QLabel:
    label = QLabel(text)
    if object_name:
        label.setObjectName(object_name)
    label.setWordWrap(wrap)
    if alignment is not None:
        label.setAlignment(alignment)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def tinted_icon(path: str | Path, color: str, size: int = 20) -> QIcon:
    renderer = QSvgRenderer(str(path))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


class NavButton(QPushButton):
    def __init__(self, text: str, icon_path: str | Path, parent=None):
        super().__init__(text, parent)
        self.icon_path = str(icon_path)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumHeight(42)
        self.toggled.connect(self._refresh_icon)
        self._refresh_icon(False)

    def _refresh_icon(self, checked: bool) -> None:
        color = "#79ABFF" if checked else "#8798B2"
        self.setIcon(tinted_icon(self.icon_path, color, 18))


class StatusBadge(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("serverState")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("state", "offline")

    def set_state(self, state: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class MetricCard(QFrame):
    def __init__(
        self,
        label: str,
        value: str = "--",
        detail: str = "",
        progress_object: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(118)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        self.label = make_label(label.upper(), "statLabel")
        self.value = make_label(value, "statValue")
        self.detail = make_label(detail, "muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        if progress_object:
            self.progress.setObjectName(progress_object)
        else:
            self.progress.setVisible(False)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.progress)
        layout.addWidget(self.detail)

    def set_value(self, value: str, percent: int | None = None, detail: str = "") -> None:
        self.value.setText(value)
        if percent is not None:
            self.progress.setValue(max(0, min(100, int(percent))))
        self.detail.setText(detail)


class Sparkline(QWidget):
    def __init__(self, color: str = "#3B82F6", parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.values: list[float] = []
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add_value(self, value: float) -> None:
        self.values.append(max(0.0, min(100.0, float(value))))
        if len(self.values) > 70:
            self.values = self.values[-70:]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        painter.fillRect(rect, QColor("#0C121D"))
        grid_pen = QPen(QColor("#1B2638"))
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        for fraction in (0.25, 0.5, 0.75):
            y = rect.top() + rect.height() * fraction
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if len(self.values) < 2:
            painter.end()
            return
        path = QPainterPath()
        step = rect.width() / max(1, len(self.values) - 1)
        for index, value in enumerate(self.values):
            point = QPointF(
                rect.left() + step * index,
                rect.bottom() - (value / 100.0) * rect.height(),
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        fill = QPainterPath(path)
        fill.lineTo(rect.bottomRight())
        fill.lineTo(rect.bottomLeft())
        fill.closeSubpath()
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        top = QColor(self.color)
        top.setAlpha(70)
        bottom = QColor(self.color)
        bottom.setAlpha(5)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.fillPath(fill, gradient)
        line_pen = QPen(self.color, 2.0)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(line_pen)
        painter.drawPath(path)
        painter.end()


class PageHeader(QWidget):
    def __init__(
        self,
        eyebrow: str,
        title: str,
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(make_label(eyebrow.upper(), "eyebrow"))
        layout.addWidget(make_label(title, "pageTitle"))
        if subtitle:
            layout.addWidget(make_label(subtitle, "muted", wrap=True))


class SectionHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(make_label(title, "sectionTitle"))
        if subtitle:
            layout.addWidget(make_label(subtitle, "muted", wrap=True))


def card(radius: int | None = None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    if radius is not None:
        frame.setStyleSheet(f"border-radius: {radius}px;")
    return frame


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    return line


class InfoRow(QWidget):
    def __init__(self, key: str, value: str, mono: bool = False, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.key = make_label(key, "muted")
        self.value = make_label(value, "mono" if mono else "accentText")
        self.value.setWordWrap(True)
        layout.addWidget(self.key)
        layout.addStretch(1)
        layout.addWidget(self.value, 0, Qt.AlignmentFlag.AlignRight)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class EmptyState(QFrame):
    def __init__(
        self,
        title: str,
        body: str,
        action_text: str = "",
        action=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("emptyState")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            make_label(title, "cardTitle", alignment=Qt.AlignmentFlag.AlignCenter)
        )
        layout.addWidget(
            make_label(
                body,
                "muted",
                wrap=True,
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
        )
        if action_text and action is not None:
            button = QPushButton(action_text)
            button.setObjectName("primaryButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(action)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)


def row(*widgets: QWidget, spacing: int = 8) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return container


def stretch_row(*widgets: QWidget, spacing: int = 8) -> QWidget:
    container = row(*widgets, spacing=spacing)
    container.layout().addStretch(1)
    return container
