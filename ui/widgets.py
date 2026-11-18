from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QPainter,
    QPalette,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.utils import extract_urls
from ui import theme
from ui.motion import draw_falling_text


def logo_font(size: float, weight: int = 600) -> QFont:
    families = set(QFontDatabase.families())
    font = QFont("Segoe UI" if "Segoe UI" in families else theme.MONO_FAMILY)
    font.setPointSizeF(size)
    font.setWeight(QFont.Weight(weight))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.1)
    return font


def mix(first: QColor, second: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(first.red() + (second.red() - first.red()) * amount),
        round(first.green() + (second.green() - first.green()) * amount),
        round(first.blue() + (second.blue() - first.blue()) * amount),
        round(first.alpha() + (second.alpha() - first.alpha()) * amount),
    )


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self._apply_elision()

    def setText(self, text: str) -> None:
        self._full_text = text
        self._apply_elision()

    def fullText(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        width = max(0, self.contentsRect().width())
        rendered = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideMiddle,
            width,
        )
        super().setText(rendered)


class TypingLabel(QWidget):
    def __init__(
        self,
        text: str = "",
        size: float = 9.0,
        weight: int = 600,
        letter_spacing: float = 0.4,
        color: QColor | None = None,
        speed: float = 46.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._font = theme.mono_font(size, weight, letter_spacing)
        self._metrics = QFontMetricsF(self._font)
        self._text = text
        self._color = QColor(color or theme.TEXT_SOFT)
        self._speed = speed
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(int(math.ceil(self._metrics.height())) + 10)

    def sizeHint(self) -> QSize:
        return QSize(
            int(math.ceil(self._metrics.horizontalAdvance(self._text))),
            self.height(),
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def setText(self, text: str) -> None:
        self._text = text
        self.restart()

    def text(self) -> str:
        return self._text

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def restart(self) -> None:
        self._elapsed.start()
        self._timer.start()
        self.update()

    def _advance(self) -> None:
        if self._elapsed.elapsed() / 1000.0 * self._speed > len(self._text) + 0.8:
            self._timer.stop()
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.restart()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)
        elapsed = self._elapsed.elapsed() / 1000.0 if self._elapsed.isValid() else 0.0
        baseline = (self.height() + self._metrics.ascent() - self._metrics.descent()) / 2.0
        draw_falling_text(
            painter,
            0.0,
            baseline,
            self._text,
            self._metrics,
            self._color,
            elapsed,
            self._speed,
            drop=5.0,
        )
        painter.end()


class TerminalButton(QAbstractButton):
    def __init__(
        self,
        text: str,
        kind: str = "secondary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self._label_font = theme.mono_font(8.9, 600, 0.45)
        self.setFont(self._label_font)
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(26)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetricsF(self._label_font)
        width = metrics.horizontalAdvance(f"[{self.text()}]") + 12
        return QSize(max(44, int(width)), max(22, self.minimumHeight()))

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self._hover = True
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        enabled = self.isEnabled()
        hover = self._hover and enabled
        pressed = self.isDown() and enabled
        if not enabled:
            text_color = theme.FAINT
        elif self._kind == "accent" or self._kind == "primary":
            text_color = QColor("#ffffff") if hover or self.hasFocus() else theme.ORANGE
        elif self._kind == "danger_text" or self._kind == "danger":
            text_color = QColor("#ff8b84") if hover else theme.RED
        elif self._kind == "text" or self._kind == "secondary":
            text_color = theme.ORANGE if hover or self.hasFocus() else theme.MUTED
        else:
            text_color = theme.TEXT if hover else theme.TEXT_SOFT
        if hover and enabled and not pressed:
            highlight = QColor(theme.ORANGE)
            highlight.setAlphaF(0.10)
            painter.fillRect(rect, highlight)
        if pressed and enabled:
            painter.fillRect(rect, theme.ORANGE)
            text_color = theme.BG
        painter.setFont(self._label_font)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"[{self.text()}]")
        painter.end()


class WindowButton(QAbstractButton):
    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self._hover = False
        self._maximized = False
        self.setFixedSize(30, 28)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        names = {"min": "Свернуть", "max": "Развернуть", "close": "Закрыть"}
        self.setAccessibleName(names.get(kind, ""))

    def set_maximized_icon(self, maximized: bool) -> None:
        self._maximized = maximized
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self.kind == "close":
            color = theme.RED if self._hover else theme.MUTED
            glyph = "X"
        elif self.kind == "max":
            color = theme.ORANGE if self._hover else theme.MUTED
            glyph = "[#]" if self._maximized else "[ ]"
        else:
            color = theme.ORANGE if self._hover else theme.MUTED
            glyph = "_"
        painter.setFont(theme.mono_font(10.5, 500))
        painter.setPen(color)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
        painter.end()


class TitleBar(QWidget):
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    settings_requested = Signal()

    def __init__(
        self, parent: QWidget | None = None, mark: QPixmap | None = None
    ) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self._drag_origin: QPoint | None = None
        self._dragging = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 8, 0)
        layout.setSpacing(0)
        if mark is not None and not mark.isNull():
            scaled = mark.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(2.0)
            self.mark = QLabel(self)
            self.mark.setPixmap(scaled)
            self.mark.setFixedSize(scaled.width() // 2, 24)
            self.mark.setStyleSheet("background: transparent;")
            self.mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addSpacing(10)
        self.logo = QLabel(
            '<span style="color:#ff8c1a">BeamNG</span>'
            '<span style="color:#ffffff">.drive</span>',
            self,
        )
        self.logo.setTextFormat(Qt.TextFormat.RichText)
        self.logo.setFont(theme.mono_font(12.6, 700, 0.3))
        self.logo.setStyleSheet("background: transparent;")
        layout.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        self.settings_button = TerminalButton("настройки", "text", parent=self)
        self.settings_button.setFixedSize(116, 28)
        layout.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(10)
        self.min_button = WindowButton("min", self)
        self.max_button = WindowButton("max", self)
        self.close_button = WindowButton("close", self)
        layout.addWidget(self.min_button)
        layout.addSpacing(2)
        layout.addWidget(self.max_button)
        layout.addSpacing(2)
        layout.addWidget(self.close_button)
        self.settings_button.clicked.connect(self.settings_requested)
        self.min_button.clicked.connect(self.minimize_requested)
        self.max_button.clicked.connect(self.maximize_requested)
        self.close_button.clicked.connect(self.close_requested)

    def set_maximized(self, maximized: bool) -> None:
        self.max_button.set_maximized_icon(maximized)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if not self._dragging:
                movement = (event.globalPosition().toPoint() - self._drag_origin).manhattanLength()
                if movement >= 5:
                    self._dragging = True
                    window = self.window()
                    handle = window.windowHandle()
                    if handle is not None and hasattr(handle, "startSystemMove"):
                        handle.startSystemMove()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_origin = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_requested.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.end()


class FolderField(QWidget):
    browse_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)
        self._path = Path.home()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.caption = TypingLabel(
            "папка", 8.6, 600, 0.5, theme.ACCENT_FOLDER, 40.0, self
        )
        self.caption.setFixedWidth(62)
        layout.addWidget(self.caption, 0, Qt.AlignmentFlag.AlignVCenter)
        self.path_label = ElidedLabel(str(self._path), self)
        self.path_label.setFont(theme.mono_font(9.8, 450, 0.0))
        self.path_label.setStyleSheet(f"color: {theme.TEXT.name()}; background: transparent;")
        layout.addWidget(self.path_label, 1)
        self.browse_button = TerminalButton("изменить", "text", parent=self)
        self.browse_button.setFixedSize(104, 22)
        layout.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.browse_button.clicked.connect(self.browse_requested)
        self._warning = False
        self._warning_timer = QTimer(self)
        self._warning_timer.setSingleShot(True)
        self._warning_timer.setInterval(4200)
        self._warning_timer.timeout.connect(self._restore_path)

    def set_path(self, path: Path) -> None:
        self._path = Path(path)
        self._warning = False
        self._warning_timer.stop()
        self.path_label.setStyleSheet(f"color: {theme.TEXT.name()}; background: transparent;")
        self.path_label.setText(str(self._path))

    def flash_error(self, message: str) -> None:
        self._warning = True
        self.path_label.setStyleSheet(f"color: {theme.RED.name()}; background: transparent;")
        self.path_label.setText(message)
        self._warning_timer.start()

    def set_busy(self, busy: bool) -> None:
        self.browse_button.setEnabled(not busy)

    def restart(self) -> None:
        self.caption.restart()

    def _restore_path(self) -> None:
        self._warning = False
        self.path_label.setStyleSheet(f"color: {theme.TEXT.name()}; background: transparent;")
        self.path_label.setText(str(self._path))


class _CharFall:
    __slots__ = ("position", "char", "start")

    def __init__(self, position: int, char: str, start: float) -> None:
        self.position = position
        self.char = char
        self.start = start


class _FallingOverlay(QWidget):
    DURATION = 0.29

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor.viewport())
        self._editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setGeometry(editor.viewport().rect())
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _tick(self) -> None:
        now = time.monotonic()
        self._editor._falls = [
            fall for fall in self._editor._falls if now - fall.start < self.DURATION
        ]
        self.update()
        if not self._editor._falls:
            self._timer.stop()

    def paintEvent(self, event) -> None:
        falls = self._editor._falls
        if not falls:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = self._editor.font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        document = self._editor.document()
        now = time.monotonic()
        for fall in falls:
            cursor = QTextCursor(document)
            cursor.setPosition(fall.position)
            rect = self._editor.cursorRect(cursor)
            if rect.isNull() or rect.bottom() < 0 or rect.top() > self.height():
                continue
            left = rect.left()
            top = rect.top()
            width = metrics.horizontalAdvance(fall.char) + 1.8
            painter.fillRect(
                QRectF(left, top, width, rect.height()),
                theme.BG,
            )
            local = now - fall.start
            if local < 0:
                continue
            draw_falling_text(
                painter,
                left,
                top + metrics.ascent(),
                fall.char,
                metrics,
                QColor("#eef2f4"),
                local,
                1000.0,
                drop=9.0,
                duration=self.DURATION,
            )
        painter.end()


class LinkEdit(QPlainTextEdit):
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabChangesFocus(True)
        self.setFont(theme.mono_font(10.2, 400))
        self.setMinimumWidth(80)
        self.document().setDocumentMargin(0)
        self.setViewportMargins(24, 2, 8, 2)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, theme.FAINT)
        self.setPalette(palette)
        self._previous = ""
        self._falls: list[_CharFall] = []
        self._animate = True
        self._overlay = _FallingOverlay(self)
        self._overlay.show()
        self._overlay.raise_()
        self.textChanged.connect(self._handle_text_change)

    def set_animation_speed(self, factor: float) -> None:
        self._animate = factor > 0
        if not self._animate:
            self._falls.clear()
            self._overlay.update()

    def _handle_text_change(self) -> None:
        text = self.toPlainText()
        previous = self._previous
        self._previous = text
        if text == previous:
            return
        if not self._animate:
            self._falls.clear()
            self._overlay.update()
            return
        prefix = 0
        limit = min(len(text), len(previous))
        while prefix < limit and text[prefix] == previous[prefix]:
            prefix += 1
        suffix = 0
        max_suffix = min(len(text) - prefix, len(previous) - prefix)
        while (
            suffix < max_suffix
            and text[len(text) - 1 - suffix] == previous[len(previous) - 1 - suffix]
        ):
            suffix += 1
        inserted = len(text) - prefix - suffix
        removed = len(previous) - prefix - suffix
        if removed or inserted <= 0 or inserted > 120:
            self._falls.clear()
            self._overlay.update()
            return
        if prefix != len(previous):
            self._falls.clear()
        self._falls = [
            fall
            for fall in self._falls
            if len(text) > fall.position and text[fall.position] == fall.char
        ]
        now = time.monotonic()
        stagger = 0.0 if inserted == 1 else min(0.012, 0.24 / inserted)
        for offset in range(inserted):
            position = prefix + offset
            self._falls.append(
                _CharFall(position, text[position], now + offset * stagger)
            )
        if len(self._falls) > 400:
            del self._falls[: len(self._falls) - 400]
        self._overlay.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._overlay.setGeometry(self.viewport().rect())
        self._overlay.raise_()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._overlay.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submitted.emit()
            return
        super().keyPressEvent(event)


class SourceShell(QWidget):
    paste_requested = Signal()
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(84)
        self._focus = False
        self._error = False
        self._prompt_font = theme.mono_font(10.6, 700)
        self._prompt_metrics = QFontMetricsF(self._prompt_font)
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.setInterval(1200)
        self._error_timer.timeout.connect(self._clear_error)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.editor = LinkEdit(self)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor, 1)
        actions = QHBoxLayout()
        actions.setContentsMargins(24, 0, 0, 2)
        actions.setSpacing(8)
        self.paste_button = TerminalButton("вставить", "text", parent=self)
        self.paste_button.setFixedSize(96, 22)
        self.download_button = TerminalButton("скачать", "accent", parent=self)
        self.download_button.setFixedSize(96, 22)
        actions.addWidget(self.paste_button)
        actions.addWidget(self.download_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.paste_button.clicked.connect(self.paste_requested.emit)
        self.editor.submitted.connect(self.submitted.emit)

    def _clear_error(self) -> None:
        self._error = False
        self.update()

    def flash_error(self) -> None:
        self._error = True
        self._error_timer.start()
        self.update()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.editor:
            if event.type() == event.Type.FocusIn:
                self._focus = True
                self.update()
            elif event.type() == event.Type.FocusOut:
                self._focus = False
                self.update()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self._error:
            color = theme.RED
            background = theme.FIELD_ERROR
        elif self._focus:
            color = theme.ORANGE
            background = theme.FIELD_FOCUS
        else:
            color = theme.MUTED
            background = theme.FIELD
        painter.fillRect(self.rect(), background)
        painter.setFont(self._prompt_font)
        painter.setPen(color)
        painter.drawText(QPointF(0.0, 2.0 + self._prompt_metrics.ascent()), ">")
        painter.end()


class SourceBar(QWidget):
    submitted = Signal(str)
    paste_requested = Signal()
    changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(84)
        self._busy = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.shell = SourceShell(self)
        layout.addWidget(self.shell, 1)
        self.shell.paste_requested.connect(self.paste_requested.emit)
        self.shell.submitted.connect(self._submit)
        self.shell.download_button.clicked.connect(self._submit)
        self.shell.editor.textChanged.connect(
            lambda: self.changed.emit(self.shell.editor.toPlainText())
        )

    def _submit(self) -> None:
        if self._busy:
            return
        text = self.shell.editor.toPlainText().strip()
        if text:
            self.submitted.emit(text)

    def set_animation_speed(self, factor: float) -> None:
        self.shell.editor.set_animation_speed(factor)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.shell.editor.setReadOnly(busy)
        self.shell.paste_button.setEnabled(not busy)
        self.shell.download_button.setEnabled(not busy)
        self.shell.download_button.setText("загрузка" if busy else "скачать")

    def set_text(self, text: str) -> None:
        self.shell.editor.setPlainText(text)
        cursor = self.shell.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.shell.editor.setTextCursor(cursor)
        self.shell.editor.ensureCursorVisible()
        self.shell.editor.setFocus()

    def add_links(self, urls: list[str]) -> int:
        existing = extract_urls(self.text())
        seen = {url.lower() for url in existing}
        added: list[str] = []
        for url in urls:
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            added.append(url)
        if added:
            base = self.text()
            combined = base + ("\n" if base else "") + "\n".join(added)
            self.set_text(combined)
        return len(added)

    def clear(self) -> None:
        self.shell.editor.clear()

    def text(self) -> str:
        return self.shell.editor.toPlainText().strip()

    def focus_input(self) -> None:
        self.shell.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def flash_error(self) -> None:
        self.shell.flash_error()


class StatusLine(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._font = theme.mono_font(8.4, 450, 0.2)
        self._metrics = QFontMetricsF(self._font)
        self._net = "-"
        self._links = 0
        self._mode = "готов"

    def set_net(self, value: str) -> None:
        self._net = value
        self.update()

    def set_links(self, count: int) -> None:
        self._links = max(0, int(count))
        self.update()

    def set_mode(self, text: str) -> None:
        self._mode = text
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        baseline = (
            self.height() + self._metrics.ascent() - self._metrics.descent()
        ) / 2.0
        if self._net == "ok":
            net_color = theme.GREEN
        elif self._net == "нет":
            net_color = theme.RED
        else:
            net_color = theme.FAINT
        if self._mode == "готов":
            mode_color = theme.MUTED
        elif self._mode == "ошибка":
            mode_color = theme.RED
        else:
            mode_color = theme.ORANGE
        segments = (
            ("сеть ", theme.FAINT),
            (self._net, net_color),
            ("  |  ", theme.FAINT),
            ("ссылок ", theme.FAINT),
            (str(self._links), theme.TEXT_SOFT if self._links else theme.FAINT),
            ("  |  ", theme.FAINT),
            (self._mode, mode_color),
        )
        x = 0.0
        for text, color in segments:
            painter.setPen(color)
            painter.drawText(QPointF(x, baseline), text)
            x += self._metrics.horizontalAdvance(text)
        painter.end()

