from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.widgets import TerminalButton, TypingLabel, WindowButton


class Toggle(QAbstractButton):
    def __init__(self, checked: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(84, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = False
        self._font = theme.mono_font(8.8, 500, 0.3)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.setAccessibleName("включено" if checked else "выключено")
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
        checked = self.isChecked()
        if checked:
            color = theme.ORANGE
        elif self._hover or self.hasFocus():
            color = theme.TEXT
        else:
            color = theme.MUTED
        painter.setFont(self._font)
        painter.setPen(color)
        painter.drawText(
            self.rect().adjusted(0, 0, -4, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "[x] вкл" if checked else "[ ] выкл",
        )
        painter.end()


class SegmentButton(QAbstractButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setFixedSize(88, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = False
        self._font = theme.mono_font(8.8, 500, 0.3)

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
        checked = self.isChecked()
        if checked:
            color = theme.ORANGE
            label = f"[{self.text()}]"
        else:
            color = theme.TEXT if self._hover or self.hasFocus() else theme.MUTED
            label = self.text()
        painter.setFont(self._font)
        painter.setPen(color)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.end()


class SegmentPicker(QWidget):
    changed = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],
        current: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for value, label in options:
            button = SegmentButton(label, self)
            button.setChecked(value == current)
            self._group.addButton(button)
            layout.addWidget(button)
            button.clicked.connect(
                lambda checked=False, value=value: self.changed.emit(value)
            )
        layout.addStretch(1)


class SettingsHeader(QWidget):
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 8, 0)
        layout.setSpacing(0)
        prompt = QLabel(">", self)
        prompt.setFont(theme.mono_font(10.4, 700, 0.0))
        prompt.setStyleSheet(f"color: {theme.ORANGE.name()}; background: transparent;")
        prompt.setFixedWidth(14)
        prompt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title = TypingLabel(
            "настройки",
            9.4,
            600,
            0.6,
            theme.TEXT_SOFT,
            34.0,
            self,
        )
        layout.addWidget(prompt, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(6)
        layout.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        self.close_button = WindowButton("close", self)
        layout.addWidget(self.close_button)
        self.close_button.clicked.connect(self.close_requested)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    setting_changed = Signal(str, object)

    def __init__(
        self,
        typing: str,
        splash: bool,
        paste_autostart: bool,
        splash_effect: str = "type",
        splash_speed: str = "normal",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(600, 430)
        self.setWindowTitle("настройки")
        self._typing = typing
        self._build_ui(splash, paste_autostart, splash_effect, splash_speed)

    def _build_ui(
        self,
        splash: bool,
        paste_autostart: bool,
        splash_effect: str,
        splash_speed: str,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = SettingsHeader(self)
        root.addWidget(self.header)
        self.header.close_requested.connect(self.accept)

        body = QWidget(self)
        root.addWidget(body, 1)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 12, 24, 0)
        layout.setSpacing(0)

        layout.addWidget(self._section("оформление", body))
        picker = SegmentPicker(
            [("smooth", "плавно"), ("fast", "быстро"), ("off", "выкл")],
            self._typing,
            body,
        )
        picker.changed.connect(self._on_typing)
        layout.addWidget(self._row("анимация текста", picker, body))

        layout.addSpacing(16)
        layout.addWidget(self._section("заставка", body, theme.AMBER))
        splash_toggle = Toggle(splash, body)
        splash_toggle.toggled.connect(
            lambda checked: self.setting_changed.emit("splash", checked)
        )
        layout.addWidget(self._row("показывать при запуске", splash_toggle, body))
        effect_picker = SegmentPicker(
            [("type", "печать"), ("fade", "плавно"), ("static", "сразу")],
            splash_effect,
            body,
        )
        effect_picker.changed.connect(
            lambda value: self.setting_changed.emit("splash_effect", value)
        )
        layout.addWidget(self._row("эффект", effect_picker, body))
        speed_picker = SegmentPicker(
            [("slow", "медленно"), ("normal", "обычно"), ("fast", "быстро")],
            splash_speed,
            body,
        )
        speed_picker.changed.connect(
            lambda value: self.setting_changed.emit("splash_speed", value)
        )
        layout.addWidget(self._row("скорость", speed_picker, body))

        layout.addSpacing(16)
        layout.addWidget(self._section("поток", body, theme.ACCENT_LOG))
        paste_toggle = Toggle(paste_autostart, body)
        paste_toggle.toggled.connect(
            lambda checked: self.setting_changed.emit("paste_autostart", checked)
        )
        layout.addWidget(self._row("скачивание при вставке", paste_toggle, body))
        layout.addStretch(1)

        footer = QWidget(self)
        root.addWidget(footer)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 8, 24, 14)
        footer_layout.setSpacing(0)
        done = TerminalButton("готово", "accent", footer)
        done.setFixedSize(100, 26)
        footer_layout.addWidget(done)
        footer_layout.addStretch(1)
        done.clicked.connect(self.accept)

    def _section(
        self, text: str, parent: QWidget, color: QColor | None = None
    ) -> QLabel:
        label = QLabel(text, parent)
        label.setFont(theme.mono_font(8.6, 600, 0.5))
        tint = color or theme.ORANGE
        label.setStyleSheet(f"color: {tint.name()}; background: transparent;")
        label.setFixedHeight(22)
        return label

    def _row(self, title: str, control: QWidget, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        row.setFixedHeight(32)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        heading = QLabel(title, row)
        heading.setFont(theme.mono_font(9.4, 400, 0.1))
        heading.setStyleSheet(
            f"color: {theme.TEXT_SOFT.name()}; background: transparent;"
        )
        heading.setFixedWidth(250)
        layout.addWidget(heading, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return row

    def _on_typing(self, value: str) -> None:
        self._typing = value
        self.setting_changed.emit("typing", value)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.BG)
        painter.setPen(theme.BORDER_STRONG)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
