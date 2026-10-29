from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from brightnova.system_monitor import format_bytes
from brightnova.workers import MonitorPayload
from ui.widgets import (
    MetricCard,
    PageHeader,
    Sparkline,
    StatusBadge,
    make_label,
)


class MonitorPage(QWidget):
    def __init__(self, context, navigate, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.context = context
        self.navigate = navigate
        self._build()
        self.context.monitor_updated.connect(self.update_payload)

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

        header = QHBoxLayout()
        header.addWidget(
            PageHeader(
                "Live telemetry",
                "System Monitor",
                "Hardware and Ollama runtime telemetry refreshed every two seconds.",
            ),
            1,
        )
        self.status = StatusBadge("AWAITING DATA")
        self.status.set_state("connecting", "AWAITING DATA")
        header.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        metrics = QGridLayout()
        metrics.setSpacing(14)
        self.cpu_card = MetricCard("CPU usage", "--", "Processor load", "cpuBar")
        self.ram_card = MetricCard("Memory", "--", "Physical RAM", "ramBar")
        self.disk_card = MetricCard("Disk usage", "--", "Ubuntu storage", "diskBar")
        self.ollama_card = MetricCard("Ollama memory", "--", "Process RSS")
        metrics.addWidget(self.cpu_card, 0, 0)
        metrics.addWidget(self.ram_card, 0, 1)
        metrics.addWidget(self.disk_card, 0, 2)
        metrics.addWidget(self.ollama_card, 0, 3)
        layout.addLayout(metrics)

        charts = QHBoxLayout()
        charts.setSpacing(14)
        cpu_card = self._chart_card("CPU history", "Last 70 samples")
        self.cpu_chart = Sparkline("#3B82F6")
        cpu_card.layout().addWidget(self.cpu_chart)
        ram_card = self._chart_card("Memory history", "Last 70 samples")
        self.ram_chart = Sparkline("#8B5CF6")
        ram_card.layout().addWidget(self.ram_chart)
        charts.addWidget(cpu_card, 1)
        charts.addWidget(ram_card, 1)
        layout.addLayout(charts)

        details = QHBoxLayout()
        details.setSpacing(14)
        memory_card = QFrame()
        memory_card.setObjectName("card")
        memory_layout = QVBoxLayout(memory_card)
        memory_layout.setContentsMargins(22, 18, 22, 20)
        memory_layout.setSpacing(10)
        memory_layout.addWidget(make_label("Memory detail", "sectionTitle"))
        self.total_row = self._detail_row(memory_layout, "Total RAM")
        self.used_row = self._detail_row(memory_layout, "Used RAM")
        self.available_row = self._detail_row(memory_layout, "Available RAM")
        self.percent_row = self._detail_row(memory_layout, "Memory pressure")
        memory_layout.addStretch(1)
        details.addWidget(memory_card, 1)

        storage_card = QFrame()
        storage_card.setObjectName("card")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(22, 18, 22, 20)
        storage_layout.setSpacing(10)
        storage_layout.addWidget(make_label("Storage and runtime", "sectionTitle"))
        self.disk_total_row = self._detail_row(storage_layout, "Disk total")
        self.disk_used_row = self._detail_row(storage_layout, "Disk used")
        self.disk_free_row = self._detail_row(storage_layout, "Disk free")
        self.ollama_process_row = self._detail_row(storage_layout, "Ollama processes")
        storage_layout.addStretch(1)
        details.addWidget(storage_card, 1)
        layout.addLayout(details)

        loaded_card = QFrame()
        loaded_card.setObjectName("card")
        loaded_layout = QVBoxLayout(loaded_card)
        loaded_layout.setContentsMargins(22, 18, 22, 20)
        loaded_layout.setSpacing(10)
        title_row = QHBoxLayout()
        title_row.addWidget(make_label("Loaded Ollama models", "sectionTitle"))
        title_row.addStretch(1)
        self.loaded_hint = make_label("Read from /api/ps", "muted")
        title_row.addWidget(self.loaded_hint)
        loaded_layout.addLayout(title_row)
        self.loaded_table = QTableWidget(0, 3)
        self.loaded_table.setHorizontalHeaderLabels(["MODEL", "MEMORY", "EXPIRES"])
        self.loaded_table.verticalHeader().setVisible(False)
        self.loaded_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.loaded_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.loaded_table.setShowGrid(False)
        header_view = self.loaded_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.loaded_table.setMinimumHeight(150)
        loaded_layout.addWidget(self.loaded_table)
        self.loaded_empty = make_label(
            "No models are currently loaded. Use AI Models to run a model.",
            "muted",
        )
        loaded_layout.addWidget(self.loaded_empty)
        layout.addWidget(loaded_card)
        layout.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    def _chart_card(self, title: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)
        layout.addWidget(make_label(title, "sectionTitle"))
        layout.addWidget(make_label(subtitle, "muted"))
        return card

    def _detail_row(self, layout: QVBoxLayout, label: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        key = make_label(label, "muted")
        value = make_label("--", "accentText")
        row_layout.addWidget(key)
        row_layout.addStretch(1)
        row_layout.addWidget(value)
        layout.addWidget(row)
        value.setObjectName("mono")
        return value

    def update_payload(self, payload: MonitorPayload) -> None:
        sample = payload.sample
        if payload.ollama_online:
            self.status.set_state("online", "LIVE")
        else:
            self.status.set_state("offline", "OLLAMA OFFLINE")
        self.cpu_card.set_value(
            f"{sample.cpu_percent:.0f}%",
            int(sample.cpu_percent),
            "Processor load",
        )
        self.ram_card.set_value(
            f"{sample.memory_percent:.0f}%",
            int(sample.memory_percent),
            f"{format_bytes(sample.memory_used)} of {format_bytes(sample.memory_total)}",
        )
        self.disk_card.set_value(
            f"{sample.disk_percent:.0f}%",
            int(sample.disk_percent),
            f"{format_bytes(sample.disk_free)} free",
        )
        self.ollama_card.set_value(
            format_bytes(sample.ollama_rss),
            None,
            f"{sample.ollama_processes} process(es) detected",
        )
        self.cpu_chart.add_value(sample.cpu_percent)
        self.ram_chart.add_value(sample.memory_percent)
        self.total_row.setText(format_bytes(sample.memory_total))
        self.used_row.setText(format_bytes(sample.memory_used))
        self.available_row.setText(format_bytes(sample.memory_available))
        self.percent_row.setText(f"{sample.memory_percent:.1f}%")
        self.disk_total_row.setText(format_bytes(sample.disk_total))
        self.disk_used_row.setText(format_bytes(sample.disk_used))
        self.disk_free_row.setText(format_bytes(sample.disk_free))
        self.ollama_process_row.setText(str(sample.ollama_processes))
        self._update_loaded(payload.running_models)

    def _update_loaded(self, models) -> None:
        self.loaded_table.setRowCount(len(models))
        for row_index, model in enumerate(models):
            self.loaded_table.setItem(row_index, 0, QTableWidgetItem(model.name))
            self.loaded_table.setItem(
                row_index, 1, QTableWidgetItem(model.size_label)
            )
            self.loaded_table.setItem(
                row_index, 2, QTableWidgetItem(model.expires_at or "--")
            )
        self.loaded_table.setVisible(bool(models))
        self.loaded_empty.setVisible(not models)
        self.loaded_hint.setText(
            f"{len(models)} model(s) loaded" if models else "No loaded models"
        )
