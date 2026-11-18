from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.engine import TransferMeta, TransferProgress, TransferResult
from core.utils import human_bytes, human_eta, human_speed
from ui import theme
from ui.widgets import TerminalButton


class TransferPanel(QWidget):
    cancel_requested = Signal()
    reveal_requested = Signal()
    skip_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Состояние передачи")
        self._prompt_font = theme.mono_font(10.6, 700, 0.0)
        self._status_font = theme.mono_font(8.8, 500, 0.3)
        self._host_font = theme.mono_font(8.2, 400, 0.2)
        self._bar_font = theme.mono_font(9.2, 400, 0.0)
        self._file_font = theme.mono_font(9.8, 400, 0.0)
        self._stats_font = theme.mono_font(8.4, 400, 0.2)
        self._status_metrics = QFontMetricsF(self._status_font)
        self._host_metrics = QFontMetricsF(self._host_font)
        self._file_metrics = QFontMetricsF(self._file_font)
        self._state = "idle"
        self._status = "ожидание"
        self._host = ""
        self._filename = ""
        self._downloaded = 0
        self._total: int | None = None
        self._speed = 0.0
        self._eta: float | None = None
        self._target_percent: float | None = None
        self._displayed = 0.0
        self._phase = 0.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._last_tick = time.monotonic()
        self.action_button = TerminalButton("отмена", "danger_text", parent=self)
        self.action_button.setFixedSize(100, 26)
        self.action_button.clicked.connect(self._on_action)
        self.action_button.hide()
        self.skip_button = TerminalButton("пропуск", "text", parent=self)
        self.skip_button.setFixedSize(100, 26)
        self.skip_button.clicked.connect(self.skip_requested.emit)
        self.skip_button.hide()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._place_button()

    def resizeEvent(self, event) -> None:
        self._place_button()
        super().resizeEvent(event)

    def _place_button(self) -> None:
        action_width = self.action_button.width()
        self.action_button.move(self.width() - action_width, 0)
        self.skip_button.move(
            self.width() - action_width - self.skip_button.width() - 8, 0
        )

    def _meta_right(self) -> float:
        edges = [float(self.width())]
        for button in (self.action_button, self.skip_button):
            if not button.isHidden():
                edges.append(float(button.x()))
        return min(edges) - 12

    def reset(self) -> None:
        self._state = "idle"
        self._status = "ожидание"
        self._host = ""
        self._filename = ""
        self._downloaded = 0
        self._total = None
        self._speed = 0.0
        self._eta = None
        self._target_percent = None
        self._displayed = 0.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._timer.stop()
        self._sync_action()
        self.update()

    def set_queue(self, position: int, total: int) -> None:
        self._queue_pos = max(0, position)
        self._queue_total = max(0, total)
        self._sync_action()
        self.update()

    def begin_preparing(self, host: str = "") -> None:
        self._state = "preparing"
        self._status = "подключение"
        self._host = host
        self._filename = ""
        self._downloaded = 0
        self._total = None
        self._speed = 0.0
        self._eta = None
        self._target_percent = None
        self._displayed = 0.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._last_tick = time.monotonic()
        self._timer.start()
        self._sync_action()
        self.update()

    def begin_transfer(self, meta: TransferMeta) -> None:
        self._state = "active"
        self._status = "передача"
        self._host = meta.host
        self._filename = meta.filename
        self._downloaded = 0
        self._total = meta.total
        self._speed = 0.0
        self._eta = None
        self._target_percent = 0.0 if meta.total else None
        self._displayed = 0.0
        self._summary = ""
        self._last_tick = time.monotonic()
        self._timer.start()
        self._sync_action()
        self.update()

    def update_progress(self, update: TransferProgress) -> None:
        if self._state not in {"active", "preparing"}:
            self._state = "active"
            self._status = "передача"
            self._sync_action()
        self._downloaded = update.downloaded
        self._total = update.total
        self._speed = update.speed
        self._eta = update.eta
        self._target_percent = update.percent
        if not self._timer.isActive():
            self._last_tick = time.monotonic()
            self._timer.start()
        self.update()

    def finish_success(self, result: TransferResult) -> None:
        self._state = "success"
        self._status = "готово"
        self._host = result.host
        self._filename = result.filename
        self._downloaded = result.size
        self._total = result.size
        self._speed = 0.0
        self._eta = 0.0
        self._target_percent = 100.0
        self._displayed = 100.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._timer.stop()
        self._sync_action()
        self.update()

    def finish_error(self, message: str) -> None:
        self._state = "error"
        self._status = "ошибка"
        self._filename = message
        self._speed = 0.0
        self._eta = None
        self._target_percent = None
        self._displayed = 0.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._timer.stop()
        self._sync_action()
        self.update()

    def finish_cancelled(self) -> None:
        self._state = "cancelled"
        self._status = "отменено"
        self._speed = 0.0
        self._eta = None
        self._target_percent = None
        self._displayed = 0.0
        self._queue_pos = 0
        self._queue_total = 0
        self._summary = ""
        self._timer.stop()
        self._sync_action()
        self.update()

    def finish_batch(
        self,
        total: int,
        success: int,
        failed: int,
        cancelled: int,
        skipped: int = 0,
        stopped: bool = False,
    ) -> None:
        skipped = max(skipped, max(0, total - success - failed - cancelled))
        self._queue_pos = 0
        self._queue_total = 0
        self._speed = 0.0
        self._eta = None
        self._timer.stop()
        if success == total and total > 0:
            self._state = "success"
            self._status = "готово"
            self._filename = f"очередь | сохранено {success}"
            self._summary = f"завершено {total} из {total}"
            self._target_percent = 100.0
            self._displayed = 100.0
        elif stopped or cancelled > 0:
            self._state = "cancelled"
            self._status = "остановлено"
            self._filename = f"сохранено {success} | пропущено {skipped}"
            self._summary = "очередь прервана"
            self._target_percent = None
            self._displayed = 0.0
        elif success == 0:
            self._state = "error"
            self._status = "ошибка"
            self._filename = f"сохранено 0 | ошибок {failed}"
            self._summary = "очередь завершена"
            self._target_percent = None
            self._displayed = 0.0
        else:
            self._state = "partial"
            self._status = "частично"
            tail = f" | пропущено {skipped}" if skipped else ""
            self._filename = f"сохранено {success} | ошибок {failed}{tail}"
            self._summary = "очередь завершена"
            self._target_percent = 100.0
            self._displayed = 100.0
        self._sync_action()
        self.update()

    def set_cancelling(self) -> None:
        self._status = "остановка"
        self.action_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.update()

    def _on_action(self) -> None:
        if self._state in {"success", "partial"}:
            self.reveal_requested.emit()
        elif self._state in {"active", "preparing"}:
            self.cancel_requested.emit()

    def _sync_action(self) -> None:
        visible = self._state in {"preparing", "active", "success", "partial"}
        self.action_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        if self._state in {"success", "partial"}:
            self.action_button.setText("показать")
            self.action_button.set_kind("accent")
        else:
            self.action_button.setText("отмена")
            self.action_button.set_kind("danger_text")
        self.action_button.setVisible(visible)
        self.skip_button.setVisible(
            self._state in {"preparing", "active"}
            and self._queue_total > 1
            and 0 < self._queue_pos < self._queue_total
        )
        self._place_button()

    def _tick(self) -> None:
        now = time.monotonic()
        delta = min(0.1, now - self._last_tick)
        self._last_tick = now
        self._phase = (self._phase + delta * 0.6) % 1.0
        if self._target_percent is not None:
            difference = self._target_percent - self._displayed
            if abs(difference) < 0.03:
                self._displayed = self._target_percent
            else:
                self._displayed += difference * 0.18
            if self._displayed < 0.0:
                self._displayed = 0.0
        self.update()

    def _accent(self) -> QColor:
        return {
            "idle": theme.AMBER,
            "preparing": theme.AMBER,
            "active": theme.ORANGE,
            "success": theme.GREEN,
            "partial": theme.AMBER,
            "error": theme.RED,
            "cancelled": theme.AMBER,
        }.get(self._state, theme.MUTED)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        accent = self._accent()
        painter.setFont(self._prompt_font)
        painter.setPen(accent)
        painter.drawText(QPointF(0.0, 14.0), ">")
        painter.setFont(self._status_font)
        painter.setPen(accent)
        painter.drawText(QPointF(14.0, 14.0), self._status)
        meta_parts: list[str] = []
        if self._host:
            meta_parts.append(self._host)
        if self._queue_total > 1 and self._queue_pos > 0:
            meta_parts.append(f"{self._queue_pos}/{self._queue_total}")
        if meta_parts:
            meta_text = " | ".join(meta_parts)
            meta_x = 14.0 + self._status_metrics.horizontalAdvance(self._status) + 10
            meta_width = self._meta_right() - meta_x
            if meta_width > 24:
                painter.setFont(self._host_font)
                painter.setPen(theme.FAINT)
                display = self._host_metrics.elidedText(
                    meta_text,
                    Qt.TextElideMode.ElideRight,
                    int(meta_width),
                )
                painter.drawText(QPointF(meta_x, 14.0), display)
        painter.setFont(self._file_font)
        if self._state == "error":
            file_color = theme.RED
        elif self._state == "idle" or not self._filename:
            file_color = theme.FAINT
        else:
            file_color = theme.TEXT
        painter.setPen(file_color)
        filename = self._filename
        if filename:
            display = self._file_metrics.elidedText(
                filename,
                Qt.TextElideMode.ElideMiddle,
                max(80.0, self.width() - 28.0),
            )
            painter.drawText(QPointF(14.0, 38.0), display)
        cells = 28
        filled = 0
        percent = "--"
        if self._target_percent is not None:
            fraction = max(0.0, min(1.0, self._displayed / 100.0))
            filled = int(round(cells * fraction))
            percent = f"{int(round(self._displayed))}%"
        bar = "#" * filled + "-" * (cells - filled)
        if self._state in {"preparing", "active"} and self._target_percent is None:
            chars = ["-"] * cells
            start = int(self._phase * cells)
            for offset in range(4):
                chars[(start + offset) % cells] = "#"
            bar = "".join(chars)
        if self._target_percent is not None or self._state in {"preparing", "active"}:
            painter.setFont(self._bar_font)
            bar_color = accent if self._state != "error" else theme.RED
            painter.setPen(bar_color)
            painter.drawText(QPointF(14.0, 56.0), f"[{bar}] {percent}")
        painter.setFont(self._stats_font)
        painter.setPen(theme.MUTED)
        stats = self._stats_text()
        if stats:
            painter.drawText(QPointF(14.0, 74.0), stats)
        painter.end()

    def _stats_text(self) -> str:
        if self._summary:
            return self._summary
        if self._state == "idle":
            return ""
        if self._state == "preparing":
            return "получение файла"
        if self._state == "active":
            parts = []
            downloaded = human_bytes(self._downloaded)
            if self._total is not None:
                downloaded += f" / {human_bytes(self._total)}"
            parts.append(downloaded)
            if self._speed > 0:
                parts.append(human_speed(self._speed))
            if self._eta is not None:
                parts.append(f"осталось {human_eta(self._eta)}")
            return "   |   ".join(parts)
        if self._state == "success":
            return f"{human_bytes(self._total or self._downloaded)}   |   сохранено"
        if self._state == "error":
            return "передача не завершена"
        return "временный файл удалён"
