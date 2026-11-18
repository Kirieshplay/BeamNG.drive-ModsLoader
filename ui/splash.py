from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from ui import theme

TITLE = "BeamNG.drive"
ACCENT = "BeamNG"
STATUS_TEXT = "> загрузка модов"
BOOT_LINES = ("шрифты", "настройки", "интерфейс")

EFFECTS = ("type", "fade", "static")
SPEEDS = {"slow": 0.62, "normal": 1.0, "fast": 1.7}


class SplashScreen(QWidget):
    finished = Signal()

    BASE_HOLD_MS = 2600
    FADE_MS = 260
    BAR_CELLS = 26
    BOOT_STEP = 22.0

    def __init__(
        self,
        effect: str = "type",
        speed: str = "normal",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setFixedSize(1000, 500)
        self.setWindowTitle("BeamNG.drive")
        self.setAccessibleName("Заставка BeamNG.drive")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._effect = effect if effect in EFFECTS else "type"
        self._factor = SPEEDS.get(speed, 1.0)
        self._hold_ms = int(self.BASE_HOLD_MS / self._factor)
        self._title_font = self._fit_title_font()
        self._status_font = theme.mono_font(13.0, 500, 0.2)
        self._boot_font = theme.mono_font(10.5, 500, 0.1)
        self._bar_font = theme.mono_font(12.0, 500, 0.0)
        self._title_metrics = QFontMetricsF(self._title_font)
        self._status_metrics = QFontMetricsF(self._status_font)
        self._boot_metrics = QFontMetricsF(self._boot_font)
        self._bar_metrics = QFontMetricsF(self._bar_font)
        self._layout_text()
        self._elapsed = QElapsedTimer()
        self._started = False
        self._fading = False
        self._finished = False
        self._clock = QTimer(self)
        self._clock.setInterval(16)
        self._clock.timeout.connect(self.update)
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(self._hold_ms)
        self._hold_timer.timeout.connect(self._begin_fade)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(self.FADE_MS)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.finished.connect(self._complete)

    @property
    def hold_ms(self) -> int:
        return self._hold_ms

    def _fit_title_font(self) -> QFont:
        size = 84.0
        while size > 30.0:
            font = theme.mono_font(size, 700, 0.0)
            if QFontMetricsF(font).horizontalAdvance(TITLE) <= self.width() * 0.74:
                return font
            size -= 2.0
        return theme.mono_font(30.0, 700, 0.0)

    def _layout_text(self) -> None:
        title_height = self._title_metrics.height()
        self._title_width = self._title_metrics.horizontalAdvance(TITLE)
        self._title_x = (self.width() - self._title_width) / 2.0
        self._accent_width = self._title_metrics.horizontalAdvance(ACCENT)
        status_height = self._status_metrics.height()
        bar_height = self._bar_metrics.height()
        block = (
            title_height
            + 34.0
            + status_height
            + 22.0
            + self.BOOT_STEP * len(BOOT_LINES)
            + 26.0
            + bar_height
        )
        top = max(24.0, (self.height() - block) / 2.0)
        self._title_baseline = top + self._title_metrics.ascent()
        self._status_baseline = top + title_height + 34.0 + self._status_metrics.ascent()
        self._boot_first = self._status_baseline + 22.0 + self._boot_metrics.ascent()
        self._bar_baseline = (
            self._boot_first
            + self.BOOT_STEP * (len(BOOT_LINES) - 1)
            + 26.0
            + self._bar_metrics.ascent()
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._center()
        if not self._started:
            self._started = True
            self._elapsed.start()
            self._clock.start()
            self._hold_timer.start()

    def _center(self) -> None:
        screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(
            available.left() + (available.width() - self.width()) // 2,
            available.top() + (available.height() - self.height()) // 2,
        )

    def finish_now(self) -> None:
        self._begin_fade()

    def _begin_fade(self) -> None:
        if self._fading or self._finished:
            return
        self._fading = True
        self._hold_timer.stop()
        self._clock.stop()
        self._fade.start()

    def _complete(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._clock.stop()
        self._hold_timer.stop()
        self.finished.emit()
        self.close()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.finish_now()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        self.finish_now()
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, False)
        painter.fillRect(self.rect(), theme.BG)
        if not self._started:
            painter.end()
            return
        elapsed = self._elapsed.elapsed() / 1000.0
        self._paint_title(painter, elapsed)
        self._paint_status(painter, elapsed)
        self._paint_boot(painter, elapsed)
        self._paint_bar(painter, elapsed)
        painter.end()

    def _paint_title(self, painter: QPainter, elapsed: float) -> None:
        painter.setFont(self._title_font)
        visible = len(TITLE)
        alpha = 1.0
        if self._effect == "type":
            span = max(0.2, self._hold_ms / 1000.0 * 0.5)
            visible = int(len(TITLE) * min(1.0, elapsed / span))
        elif self._effect == "fade":
            alpha = max(0.0, min(1.0, elapsed / 0.45))
        if alpha <= 0.0:
            return
        orange = QColor(theme.ORANGE)
        orange.setAlphaF(alpha)
        white = QColor("#ffffff")
        white.setAlphaF(alpha)
        shown = TITLE[:visible]
        accent = shown[: len(ACCENT)]
        painter.setPen(orange)
        painter.drawText(QPointF(self._title_x, self._title_baseline), accent)
        if len(shown) > len(ACCENT):
            painter.setPen(white)
            painter.drawText(
                QPointF(self._title_x + self._accent_width, self._title_baseline),
                shown[len(ACCENT) :],
            )
        typing = self._effect == "type" and visible < len(TITLE)
        if typing and (elapsed * 2.2) % 2 < 1.2:
            cursor_x = self._title_x + self._title_metrics.horizontalAdvance(shown)
            painter.fillRect(
                QRectF(
                    cursor_x + 3.0,
                    self._title_baseline - self._title_metrics.ascent() * 0.78,
                    4.0,
                    self._title_metrics.ascent() * 0.92,
                ),
                theme.ORANGE,
            )

    def _paint_status(self, painter: QPainter, elapsed: float) -> None:
        painter.setFont(self._status_font)
        if self._effect == "static":
            painter.setPen(theme.MUTED)
            painter.drawText(QPointF(self._title_x, self._status_baseline), STATUS_TEXT)
            return
        if self._effect == "fade":
            alpha = max(0.0, min(1.0, (elapsed - 0.30) / 0.45))
            if alpha <= 0.0:
                return
            color = QColor(theme.MUTED)
            color.setAlphaF(alpha)
            painter.setPen(color)
            painter.drawText(QPointF(self._title_x, self._status_baseline), STATUS_TEXT)
            return
        local = elapsed - 0.30
        if local < 0:
            return
        visible = min(len(STATUS_TEXT), int(local * 34.0))
        if visible <= 0:
            return
        painter.setPen(theme.MUTED)
        painter.drawText(
            QPointF(self._title_x, self._status_baseline),
            STATUS_TEXT[:visible],
        )
        width = self._status_metrics.horizontalAdvance(STATUS_TEXT[:visible])
        if visible < len(STATUS_TEXT) or (elapsed * 2.4) % 2 < 1.2:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.ORANGE)
            painter.drawRect(
                QRectF(
                    self._title_x + width + 6.0,
                    self._status_baseline - 11.0,
                    8.0,
                    13.0,
                )
            )

    def _paint_boot(self, painter: QPainter, elapsed: float) -> None:
        painter.setFont(self._boot_font)
        offset = self._boot_metrics.horizontalAdvance("[ok]  ")
        for index, line in enumerate(BOOT_LINES):
            if self._effect != "static" and elapsed < (0.85 + index * 0.30) / self._factor:
                continue
            baseline = self._boot_first + index * self.BOOT_STEP
            painter.setPen(theme.GREEN)
            painter.drawText(QPointF(self._title_x, baseline), "[ok]")
            painter.setPen(theme.MUTED)
            painter.drawText(QPointF(self._title_x + offset, baseline), line)

    def _paint_bar(self, painter: QPainter, elapsed: float) -> None:
        if self._effect == "static":
            progress = 1.0
        else:
            span = max(0.2, self._hold_ms / 1000.0 - 0.35)
            progress = max(0.0, min(1.0, (elapsed - 0.20) / span))
        filled = int(round(progress * self.BAR_CELLS))
        empty = self.BAR_CELLS - filled
        metrics = self._bar_metrics
        painter.setFont(self._bar_font)
        x = self._title_x
        painter.setPen(theme.FAINT)
        painter.drawText(QPointF(x, self._bar_baseline), "[")
        x += metrics.horizontalAdvance("[")
        painter.setPen(theme.ORANGE)
        painter.drawText(QPointF(x, self._bar_baseline), "#" * filled)
        x += metrics.horizontalAdvance("#" * filled)
        painter.setPen(theme.FAINT)
        painter.drawText(QPointF(x, self._bar_baseline), "-" * empty + "]")
        x += metrics.horizontalAdvance("-" * empty + "]")
        painter.setPen(theme.MUTED)
        painter.drawText(
            QPointF(x + metrics.horizontalAdvance(" "), self._bar_baseline),
            f"{int(round(progress * 100)):3d}%",
        )
