from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.pages import FeedItem, FeedPage
from ui import theme
from ui.widgets import ElidedLabel, TerminalButton, TypingLabel, WindowButton
from ui.worker import FeedWorker


class FeedHeader(QWidget):
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
        prompt.setFixedWidth(12)
        prompt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title = TypingLabel(
            "выбор модов", 9.4, 600, 0.6, theme.TEXT_SOFT, 38.0, self
        )
        layout.addWidget(prompt, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(8)
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


class FeedRow(QAbstractButton):
    def __init__(self, item: FeedItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setCheckable(True)
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(item.title)
        self._hover = False
        self._check_font = theme.mono_font(9.0, 600, 0.4)
        self._title_font = theme.mono_font(9.6, 450, 0.0)
        self._title_metrics = QFontMetricsF(self._title_font)

    def enterEvent(self, event) -> None:
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(self.rect())
        checked = self.isChecked()
        if self.hasFocus():
            painter.setFont(self._check_font)
            painter.setPen(theme.ORANGE)
            painter.drawText(QRectF(0, 0, 14, rect.height()), Qt.AlignmentFlag.AlignVCenter, ">")
        painter.setFont(self._check_font)
        painter.setPen(theme.ORANGE if checked else theme.FAINT)
        painter.drawText(
            QRectF(18, 0, 32, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "[x]" if checked else "[ ]",
        )
        title_left = 54.0
        title_width = max(20.0, rect.width() - 18.0 - title_left)
        if checked:
            title_color = theme.TEXT
        elif self._hover or self.hasFocus():
            title_color = QColor("#ffffff")
        else:
            title_color = theme.TEXT_SOFT
        painter.setFont(self._title_font)
        painter.setPen(title_color)
        title = self._title_metrics.elidedText(
            self.item.title,
            Qt.TextElideMode.ElideRight,
            int(title_width),
        )
        painter.drawText(
            QRectF(title_left, 0, title_width, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )
        painter.end()


class FeedDialog(QDialog):
    FALLBACK_RESULT = 2

    def __init__(self, url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(760, 560)
        self.setWindowTitle("выбор модов")
        self._url = url
        self._page: FeedPage | None = None
        self._rows: list[FeedRow] = []
        self._thread: QThread | None = None
        self._worker: FeedWorker | None = None
        self._pending_result: int | None = None
        self._fallback_direct = False
        self._dots = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(240)
        self._loading_timer.timeout.connect(self._tick_loading)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = FeedHeader(self)
        root.addWidget(self.header)
        body = QWidget(self)
        root.addWidget(body, 1)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 14, 24, 0)
        body_layout.setSpacing(0)
        self.loading_label = QLabel("> загрузка страницы", body)
        self.loading_label.setFont(theme.mono_font(9.2, 400, 0.2))
        self.loading_label.setStyleSheet(
            f"color: {theme.MUTED.name()}; background: transparent;"
        )
        self.loading_label.setFixedHeight(40)
        self.loading_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        body_layout.addWidget(self.loading_label)
        self.error_label = QLabel("", body)
        self.error_label.setWordWrap(True)
        self.error_label.setFont(theme.mono_font(9.2, 400, 0.1))
        self.error_label.setStyleSheet(f"color: {theme.RED.name()}; background: transparent;")
        self.error_label.hide()
        body_layout.addWidget(self.error_label)
        self.scroll = QScrollArea(body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        palette = self.scroll.viewport().palette()
        palette.setColor(QPalette.ColorRole.Window, theme.BG)
        palette.setColor(QPalette.ColorRole.Base, theme.BG)
        self.scroll.viewport().setPalette(palette)
        self.scroll.viewport().setAutoFillBackground(True)
        self.content = QWidget(self.scroll)
        content_palette = self.content.palette()
        content_palette.setColor(QPalette.ColorRole.Window, theme.BG)
        content_palette.setColor(QPalette.ColorRole.Base, theme.BG)
        self.content.setPalette(content_palette)
        self.content.setAutoFillBackground(True)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addStretch(1)
        self.scroll.setWidget(self.content)
        self.scroll.hide()
        body_layout.addWidget(self.scroll, 1)
        footer = QWidget(self)
        root.addWidget(footer)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 10, 24, 16)
        footer_layout.setSpacing(10)
        self.all_button = TerminalButton("все", "text", parent=footer)
        self.all_button.setFixedSize(84, 26)
        self.download_button = TerminalButton("скачать", "accent", parent=footer)
        self.download_button.setFixedSize(140, 26)
        self.all_button.setEnabled(False)
        self.download_button.setEnabled(False)
        footer_layout.addWidget(self.all_button)
        footer_layout.addWidget(self.download_button)
        footer_layout.addStretch(1)
        self.header.close_requested.connect(self.reject)
        self.all_button.clicked.connect(self._toggle_all)
        self.download_button.clicked.connect(self._download)

    @property
    def fallback_direct(self) -> bool:
        return self._fallback_direct

    def selected_items(self) -> list[FeedItem]:
        return [row.item for row in self._rows if row.isChecked()]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._thread is None and self._page is None:
            self._start_fetch()

    def _start_fetch(self) -> None:
        self._loading_timer.start()
        thread = QThread(self)
        worker = FeedWorker(self._url)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._on_loaded)
        worker.failed.connect(self._on_failed)
        worker.not_feed.connect(self._on_not_feed)
        worker.cancelled.connect(self._on_fetch_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_fetch_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _tick_loading(self) -> None:
        self._dots = (self._dots + 1) % 4
        self.loading_label.setText("> загрузка страницы" + "." * self._dots)

    def _on_loaded(self, page: FeedPage) -> None:
        if self._pending_result is not None:
            return
        self._loading_timer.stop()
        self._page = page
        self._loading_label_done()
        if not page.items:
            self._show_error("На странице не найдены моды.")
            return
        for index, item in enumerate(page.items):
            row = FeedRow(item, self.content)
            row.toggled.connect(self._update_summary)
            self.content_layout.insertWidget(index, row)
            self._rows.append(row)
        self.scroll.show()
        self.all_button.setEnabled(True)
        self._update_summary()
        if self._rows:
            QTimer.singleShot(0, self._rows[0].setFocus)

    def _loading_label_done(self) -> None:
        self.loading_label.hide()

    def _on_failed(self, message: str) -> None:
        if self._pending_result is not None:
            return
        self._loading_timer.stop()
        self._show_error(message)

    def _on_fetch_cancelled(self) -> None:
        if self._pending_result is None:
            self._loading_timer.stop()
            self._show_error("Загрузка страницы отменена.")

    def _on_not_feed(self) -> None:
        self._fallback_direct = True
        self._request_done(self.FALLBACK_RESULT)

    def _show_error(self, message: str) -> None:
        self._loading_label_done()
        self.scroll.hide()
        self.error_label.setText(message)
        self.error_label.show()
        self.all_button.setEnabled(False)
        self.download_button.setEnabled(False)

    def _on_fetch_finished(self) -> None:
        self._thread = None
        self._worker = None
        if self._pending_result is not None:
            result = self._pending_result
            self._pending_result = None
            self.done(result)

    def _update_summary(self) -> None:
        total = len(self._rows)
        selected = sum(1 for row in self._rows if row.isChecked())
        self.all_button.setText("снять" if total > 0 and selected == total else "все")
        self.download_button.setText(f"скачать {selected}" if selected else "скачать")
        self.download_button.setEnabled(selected > 0)

    def _toggle_all(self) -> None:
        if not self._rows:
            return
        select = not all(row.isChecked() for row in self._rows)
        for row in self._rows:
            row.blockSignals(True)
            row.setChecked(select)
            row.blockSignals(False)
            row.update()
        self._update_summary()

    def _download(self) -> None:
        if self._pending_result is not None:
            return
        if not self.selected_items():
            return
        self._request_done(QDialog.DialogCode.Accepted)

    def _request_done(self, result: int) -> None:
        if self._pending_result is not None:
            return
        if self._thread is not None and self._thread.isRunning():
            self._pending_result = result
            if self._worker is not None:
                self._worker.cancel()
            self.all_button.setEnabled(False)
            self.download_button.setEnabled(False)
            self.loading_label.setText("> остановка")
            self.loading_label.show()
            return
        self.done(result)

    def reject(self) -> None:
        self._request_done(QDialog.DialogCode.Rejected)

    def closeEvent(self, event) -> None:
        if self._thread is not None and self._thread.isRunning():
            event.ignore()
            self._request_done(QDialog.DialogCode.Rejected)
            return
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._loading_timer.stop()
        super().done(result)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._download()
            return
        if (
            event.key() == Qt.Key.Key_A
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._toggle_all()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.BG)
        painter.setPen(theme.BORDER_STRONG)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
