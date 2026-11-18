from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui import theme
from ui.motion import draw_falling_text

TAG_COLORS = {
    "SYS": QColor("#77838a"),
    "NET": QColor("#82a9bd"),
    "FILE": QColor("#aab4b9"),
    "HOST": QColor("#ff8a33"),
    "OK": QColor("#8ac6a1"),
    "WARN": QColor("#d3a15f"),
    "ERR": QColor("#de7a71"),
    "END": QColor("#8ac6a1"),
}


@dataclass(slots=True)
class LogLine:
    stamp: str
    tag: str
    text: str
    tag_color: QColor
    text_color: QColor
    reveal: int
    start: float = 0.0


class TerminalLog(QWidget):
    MAX_LINES = 560
    live_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Журнал")
        self._font = theme.mono_font(9.2, 400, 0.05)
        self._time_font = theme.mono_font(8.5, 400, 0.05)
        self._tag_font = theme.mono_font(8.5, 600, 0.45)
        self._prompt_font = theme.mono_font(10.6, 700, 0.0)
        self._badge_font = theme.mono_font(7.4, 600, 0.4)
        self._metrics = QFontMetricsF(self._font)
        self._time_metrics = QFontMetricsF(self._time_font)
        self._tag_metrics = QFontMetricsF(self._tag_font)
        self._prompt_metrics = QFontMetricsF(self._prompt_font)
        self._line_height = int(self._metrics.height() * 1.52)
        self._lines: list[LogLine] = []
        self._pending: deque[LogLine] = deque()
        self._active: LogLine | None = None
        self._carry = 0.0
        self._speed = 1.0
        self._pause_until = 0.0
        self._scroll = 0
        self._live = False
        self._badge_rect = QRectF()
        self._badge_hover = False
        self._last_tick = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def append(self, tag: str, message: str, color: QColor | None = None) -> None:
        key = (tag or "SYS").upper()[:5]
        tag_color = TAG_COLORS.get(key, theme.MUTED)
        text_color = color or theme.TEXT_SOFT
        line = LogLine(
            stamp=datetime.now().strftime("%H:%M:%S"),
            tag=key,
            text=message,
            tag_color=QColor(tag_color),
            text_color=QColor(text_color),
            reveal=0,
        )
        self._pending.append(line)
        self._trim()
        if self._active is None:
            self._start_next()
        self.update()

    def clear(self) -> None:
        self._lines.clear()
        self._pending.clear()
        self._active = None
        self._scroll = 0
        self._carry = 0.0
        self.update()

    def set_live(self, live: bool) -> None:
        if live == self._live:
            self.update()
            return
        self._live = live
        self.update()
        self.live_changed.emit(live)

    def set_animation_speed(self, factor: float) -> None:
        self._speed = max(0.0, factor)
        if self._speed <= 0 and self._active is not None:
            self._active.reveal = len(self._active.text)
            self._active = None
            self._pause_until = time.monotonic() + 0.04
            self._set_fast(False)
        self.update()

    def count(self) -> int:
        return len(self._lines)

    def _trim(self) -> None:
        excess = len(self._lines) - self.MAX_LINES
        if excess <= 0:
            return
        while excess > 0 and self._lines and self._lines[0] is not self._active:
            self._lines.pop(0)
            excess -= 1
        if self._active is not None and len(self._lines) > self.MAX_LINES:
            try:
                index = self._lines.index(self._active)
            except ValueError:
                index = -1
            if index > 0:
                del self._lines[: min(index, len(self._lines) - self.MAX_LINES)]

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        if self._scroll > 0:
            self._scroll += 1
        line = self._pending.popleft()
        line.start = time.monotonic()
        self._lines.append(line)
        self._active = line
        self._carry = 0.0
        if self._speed <= 0:
            line.reveal = len(line.text)
            self._active = None
            self._pause_until = line.start + 0.04
            self._set_fast(False)
            return
        self._set_fast(True)

    def _set_fast(self, fast: bool) -> None:
        interval = 16 if fast else 40
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _tick(self) -> None:
        now = time.monotonic()
        delta = min(0.12, max(0.0, now - self._last_tick))
        self._last_tick = now
        changed = False
        if self._active is None and self._pending and now >= self._pause_until:
            self._start_next()
            changed = True
        if self._active is not None:
            line = self._active
            self._carry += delta * 260.0 * self._speed
            advance = int(self._carry)
            if advance > 0:
                self._carry -= advance
                line.reveal = min(len(line.text), line.reveal + advance)
                changed = True
                if line.reveal >= len(line.text):
                    self._active = None
                    self._pause_until = now + 0.06
                    self._set_fast(False)
        if changed:
            self.update()
        elif self._active is None and not self._pending:
            if int(now * 2.0) != int((now - delta) * 2.0):
                self.update()

    def _visible_rows(self) -> int:
        body_height = self.height() - 4
        return max(1, int(body_height // self._line_height))

    def _max_scroll(self) -> int:
        rows = self._visible_rows()
        return max(0, len(self._lines) - max(1, rows - 1))

    def resizeEvent(self, event) -> None:
        self._scroll = min(self._scroll, self._max_scroll())
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        steps = int(delta / 120) or (1 if delta > 0 else -1)
        maximum = self._max_scroll()
        if maximum <= 0:
            event.accept()
            return
        self._scroll = max(0, min(maximum, self._scroll + steps * 3))
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._badge_rect.contains(
            event.position()
        ):
            self._scroll = 0
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        hover = self._badge_rect.contains(event.position()) and self._scroll > 0
        if hover != self._badge_hover:
            self._badge_hover = hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._badge_hover:
            self._badge_hover = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        body = QRectF(rect.left(), rect.top(), rect.width() - 10, rect.height() - 2)
        self._paint_lines(painter, body)
        self._paint_scrollbar(painter, rect, body)
        if self._scroll > 0:
            self._paint_badge(painter, rect)
        else:
            self._badge_rect = QRectF()
        painter.end()

    def _paint_lines(self, painter: QPainter, body: QRectF) -> None:
        painter.save()
        painter.setClipRect(body)
        rows = self._visible_rows()
        show_prompt = (
            self._active is None
            and not self._pending
            and self._scroll == 0
            and not self._live
        )
        available = max(1, rows - (1 if show_prompt else 0))
        total = len(self._lines)
        maximum = self._max_scroll()
        self._scroll = max(0, min(self._scroll, maximum))
        end = max(0, total - self._scroll)
        start = max(0, end - available)
        shown = self._lines[start:end]
        if total <= available:
            content_top = body.top()
        else:
            content_top = body.bottom() - (len(shown) + (1 if show_prompt else 0)) * self._line_height
        time_width = self._time_metrics.horizontalAdvance("00:00:00")
        tag_width = (
            max(
                self._tag_metrics.horizontalAdvance(f"[{tag}]")
                for tag in ("SYS", "NET", "FILE", "HOST", "OK", "WARN", "ERR", "END")
            )
            + 2
        )
        message_x = body.left() + time_width + 10 + tag_width + 10
        message_width = max(30.0, body.right() - message_x - 2)
        cursor_on = (time.monotonic() % 1.05) < 0.58
        now = time.monotonic()
        for index, line in enumerate(shown):
            top = content_top + index * self._line_height
            baseline = top + self._metrics.ascent() + 3
            painter.setFont(self._time_font)
            painter.setPen(QColor("#3d474c"))
            painter.drawText(QPointF(body.left(), baseline), line.stamp)
            tag_x = body.left() + time_width + 10
            painter.setFont(self._tag_font)
            painter.setPen(line.tag_color)
            painter.drawText(QPointF(tag_x, baseline), f"[{line.tag}]")
            painter.setFont(self._font)
            if line is self._active:
                painter.save()
                painter.setClipRect(
                    QRectF(message_x - 1, top, message_width + 6, self._line_height)
                )
                advance = draw_falling_text(
                    painter,
                    message_x,
                    baseline,
                    line.text,
                    self._metrics,
                    line.text_color,
                    max(0.0, now - line.start),
                    260.0 * self._speed,
                    drop=4.2,
                )
                painter.restore()
                if cursor_on:
                    cursor_x = message_x + min(advance + 2.0, message_width - 7.0)
                    cursor_height = self._metrics.ascent() + 2
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(theme.ORANGE)
                    painter.drawRect(
                        QRectF(cursor_x, baseline - cursor_height + 1, 6.0, cursor_height)
                    )
            else:
                painter.setPen(line.text_color)
                display = self._metrics.elidedText(
                    line.text,
                    Qt.TextElideMode.ElideMiddle,
                    message_width - 9,
                )
                painter.drawText(QPointF(message_x, baseline), display)
        if show_prompt:
            prompt_top = content_top + len(shown) * self._line_height
            prompt_baseline = prompt_top + self._prompt_metrics.ascent() + 2
            painter.setFont(self._prompt_font)
            painter.setPen(theme.ORANGE)
            painter.drawText(QPointF(body.left(), prompt_baseline), ">")
            prompt_width = self._prompt_metrics.horizontalAdvance(">")
            if cursor_on:
                cursor_height = self._metrics.ascent() + 3
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.ORANGE)
                painter.drawRect(
                    QRectF(
                        body.left() + prompt_width + 8,
                        prompt_baseline - cursor_height + 1,
                        7.0,
                        cursor_height,
                    )
                )
        painter.restore()

    def _paint_scrollbar(self, painter: QPainter, rect: QRectF, body: QRectF) -> None:
        rows = self._visible_rows()
        total = len(self._lines)
        maximum = self._max_scroll()
        if maximum <= 0:
            return
        track = QRectF(rect.right() - 7, body.top() + 1, 2, body.height() - 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#171d20"))
        painter.drawRect(track)
        visible_ratio = rows / max(1, total)
        thumb_height = max(16.0, track.height() * visible_ratio)
        position = 1.0 - (self._scroll / maximum if maximum else 0.0)
        offset = (track.height() - thumb_height) * max(0.0, min(1.0, position))
        painter.setBrush(theme.BORDER_STRONG)
        painter.drawRect(QRectF(track.left(), track.top() + offset, track.width(), thumb_height))

    def _paint_badge(self, painter: QPainter, rect: QRectF) -> None:
        width = 88.0
        height = 18.0
        self._badge_rect = QRectF(
            rect.right() - width - 14,
            rect.bottom() - height - 9,
            width,
            height,
        )
        painter.setPen(QPen(theme.ORANGE if self._badge_hover else theme.BORDER_STRONG, 1))
        painter.setBrush(QColor("#0d1113"))
        painter.drawRect(self._badge_rect)
        painter.setFont(self._badge_font)
        painter.setPen(theme.ORANGE if self._badge_hover else theme.MUTED)
        painter.drawText(self._badge_rect, Qt.AlignmentFlag.AlignCenter, "[ новые ]")
