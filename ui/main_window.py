from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QSettings,
    QStandardPaths,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.net import has_internet
from core.pages import is_listing_url
from core.resolvers import display_host
from core.utils import (
    ensure_directory,
    extract_urls,
    open_folder,
    path_label,
    resolve_destination,
    reveal_in_explorer,
)
from ui import backdrop, theme
from ui.feed_dialog import FeedDialog
from ui.settings_dialog import SettingsDialog
from ui.splash import EFFECTS as SPLASH_EFFECTS, SPEEDS as SPLASH_SPEEDS
from ui.terminal import TerminalLog
from ui.transfer import TransferPanel
from ui.widgets import (
    FolderField,
    SourceBar,
    StatusLine,
    TerminalButton,
    TitleBar,
    TypingLabel,
)
from ui.worker import DownloadWorker

HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
WM_NCHITTEST = 0x0084
TYPING_SPEEDS = {"smooth": 1.0, "fast": 2.6, "off": 0.0}


def links_word(count: int) -> str:
    number = abs(count) % 100
    if 11 <= number <= 19:
        return "ссылок"
    last = number % 10
    if last == 1:
        return "ссылка"
    if 2 <= last <= 4:
        return "ссылки"
    return "ссылок"


@dataclass(slots=True)
class QueueTask:
    url: str
    title: str = ""


class CloseDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setFixedSize(440, 108)
        self.setWindowTitle("закрытие")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 14)
        layout.setSpacing(0)
        title = QLabel("> закрыть приложение?", self)
        title.setFont(theme.mono_font(10.4, 500, 0.2))
        title.setStyleSheet(f"color: {theme.TEXT_SOFT.name()}; background: transparent;")
        layout.addWidget(title)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        stay = TerminalButton("остаться", "text", parent=self)
        stay.setFixedSize(104, 26)
        close = TerminalButton("закрыть", "danger_text", parent=self)
        close.setFixedSize(104, 26)
        row.addWidget(stay)
        row.addWidget(close)
        row.addStretch(1)
        layout.addLayout(row)
        stay.clicked.connect(self.reject)
        close.clicked.connect(self.accept)
        stay.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self.reject()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), theme.BG)
        painter.setPen(theme.BORDER_STRONG)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class MainWindow(QWidget):
    net_checked = Signal(bool)

    def __init__(self, asset_root: Path) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(900, 640)
        self.setWindowTitle("BeamNG.drive")
        self.setWindowIcon(QIcon(str(asset_root / "icon.ico")))
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._asset_root = asset_root
        self._settings = self._create_settings()
        self._typing_mode = self._load_typing_mode()
        self._splash_enabled = self._settings.value("ui/splash", True, type=bool)
        self._paste_autostart = self._settings.value(
            "flow/paste_autostart", True, type=bool
        )
        self._splash_effect = self._settings.value("ui/splash_effect", "type", type=str)
        if self._splash_effect not in SPLASH_EFFECTS:
            self._splash_effect = "type"
        self._splash_speed = self._settings.value("ui/splash_speed", "normal", type=str)
        if self._splash_speed not in SPLASH_SPEEDS:
            self._splash_speed = "normal"
        self._destination = self._load_destination()
        self._worker: DownloadWorker | None = None
        self._thread: QThread | None = None
        self._busy = False
        self._closing = False
        self._last_outcome = ""
        self._reveal_path: Path | None = None
        self._frame_applied = False
        self._tasks: list[QueueTask] = []
        self._task_index = 0
        self._batch_success = 0
        self._batch_failed = 0
        self._batch_cancelled = 0
        self._batch_skipped = 0
        self._batch_stop = False
        self._skip_current = False
        self._net_reported = False
        self._build_ui()
        self.net_checked.connect(self._on_net_state)
        QTimer.singleShot(260, self._probe_network)
        self._restore_geometry()
        self._wire_shortcuts()
        self._update_folder_view()
        self._seed_terminal()
        self.terminal.set_animation_speed(TYPING_SPEEDS[self._typing_mode])
        self.source_bar.set_animation_speed(TYPING_SPEEDS[self._typing_mode])

    @property
    def splash_enabled(self) -> bool:
        return bool(self._splash_enabled)

    @property
    def splash_effect(self) -> str:
        return self._splash_effect

    @property
    def splash_speed(self) -> str:
        return self._splash_speed

    def _load_typing_mode(self) -> str:
        value = self._settings.value("ui/typing", "smooth", type=str)
        return value if value in TYPING_SPEEDS else "smooth"

    def _create_settings(self) -> QSettings:
        base = Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        )
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path.home()
        return QSettings(str(base / "settings.ini"), QSettings.Format.IniFormat)

    def _load_destination(self) -> Path:
        saved = self._settings.value("destination", "", type=str)
        if saved and saved.strip():
            candidate = Path(saved)
            if candidate.is_dir() or candidate.parent.is_dir():
                return candidate
        return resolve_destination()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar(self, QPixmap(str(self._asset_root / "logo.png")))
        root.addWidget(self.title_bar)
        body = QWidget(self)
        root.addWidget(body, 1)
        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 6)
        footer_layout.setSpacing(0)
        self.status = StatusLine(footer)
        footer_layout.addWidget(self.status)
        root.addWidget(footer)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 16, 24, 12)
        layout.setSpacing(0)
        self.folder_field = FolderField(body)
        layout.addWidget(self.folder_field)
        layout.addSpacing(20)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(0)
        self.source_label = TypingLabel(
            "ссылки", 8.6, 600, 0.5, theme.ORANGE, 40.0, body
        )
        self.source_label.setFixedWidth(62)
        self.source_count = QLabel("0", body)
        self.source_count.setFont(theme.mono_font(9.0, 500, 0.3))
        self.source_count.setStyleSheet(
            f"color: {theme.FAINT.name()}; background: transparent;"
        )
        self.source_count.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        source_row.addWidget(self.source_label, 0, Qt.AlignmentFlag.AlignVCenter)
        source_row.addSpacing(2)
        source_row.addWidget(self.source_count, 0, Qt.AlignmentFlag.AlignVCenter)
        source_row.addStretch(1)
        layout.addLayout(source_row)
        layout.addSpacing(4)
        self.source_bar = SourceBar(body)
        layout.addWidget(self.source_bar)
        layout.addSpacing(20)
        self.transfer = TransferPanel(body)
        layout.addWidget(self.transfer)
        layout.addSpacing(16)
        log_row = QHBoxLayout()
        log_row.setContentsMargins(0, 0, 0, 0)
        log_row.setSpacing(0)
        self.log_label = TypingLabel(
            "журнал", 8.6, 600, 0.5, theme.ACCENT_LOG, 40.0, body
        )
        self.log_label.setFixedWidth(62)
        log_row.addWidget(self.log_label, 0, Qt.AlignmentFlag.AlignVCenter)
        log_row.addStretch(1)
        layout.addLayout(log_row)
        layout.addSpacing(2)
        self.terminal = TerminalLog(body)
        layout.addWidget(self.terminal, 1)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximize)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.settings_requested.connect(self.open_settings)
        self.folder_field.browse_requested.connect(self.choose_folder)
        self.source_bar.paste_requested.connect(self.paste_link)
        self.source_bar.submitted.connect(self.start_download)
        self.source_bar.changed.connect(self._update_source_count)
        self.transfer.cancel_requested.connect(self.cancel_download)
        self.transfer.skip_requested.connect(self.skip_current)
        self.transfer.reveal_requested.connect(self.reveal_result)

    def _wire_shortcuts(self) -> None:
        self._shortcut_folder = QShortcut(QKeySequence("Ctrl+O"), self)
        self._shortcut_folder.activated.connect(self.choose_folder)
        self._shortcut_focus = QShortcut(QKeySequence("Ctrl+L"), self)
        self._shortcut_focus.activated.connect(self.source_bar.focus_input)
        self._shortcut_escape = QShortcut(QKeySequence("Escape"), self)
        self._shortcut_escape.activated.connect(self._on_escape)

    def _restore_geometry(self) -> None:
        stored = self._settings.value("window/geometry", b"")
        restored = False
        if stored:
            try:
                restored = self.restoreGeometry(bytes(stored))
            except (TypeError, ValueError):
                restored = False
        if not restored:
            screen = QApplication.primaryScreen()
            available = screen.availableGeometry() if screen is not None else None
            if available is not None:
                width = min(1120, max(900, available.width() - 120))
                height = min(820, max(640, available.height() - 100))
                self.resize(width, height)
                self.move(
                    available.left() + (available.width() - width) // 2,
                    available.top() + (available.height() - height) // 2,
                )
            else:
                self.resize(1120, 820)
        self._ensure_on_screen()

    def _ensure_on_screen(self) -> None:
        screens = QApplication.screens()
        frame = self.frameGeometry()
        if any(screen.availableGeometry().intersects(frame) for screen in screens):
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(
            available.left() + (available.width() - self.width()) // 2,
            available.top() + (available.height() - self.height()) // 2,
        )

    def _seed_terminal(self) -> None:
        self.terminal.set_live(False)
        self.terminal.append("SYS", "BeamNG.drive | локальный клиент")
        self.terminal.append("SYS", f"папка | {path_label(self._destination, 120)}")

    def _update_folder_view(self) -> None:
        self.folder_field.set_path(self._destination)

    def _update_source_count(self, text: str) -> None:
        count = len(extract_urls(text))
        self.status.set_links(count)
        color = theme.ORANGE if count else theme.FAINT
        self.source_count.setText(str(count))
        self.source_count.setStyleSheet(
            f"color: {color.name()}; background: transparent;"
        )

    def open_settings(self) -> None:
        if self._closing:
            return
        dialog = SettingsDialog(
            typing=self._typing_mode,
            splash=self._splash_enabled,
            paste_autostart=self._paste_autostart,
            splash_effect=self._splash_effect,
            splash_speed=self._splash_speed,
            parent=self,
        )
        dialog.setting_changed.connect(self._apply_setting)
        dialog.move(
            self.mapToGlobal(
                QPoint(
                    (self.width() - dialog.width()) // 2,
                    (self.height() - dialog.height()) // 2,
                )
            )
        )
        dialog.exec()
        dialog.deleteLater()

    def _apply_destination(self, value: str) -> None:
        path = Path(value)
        try:
            ensure_directory(path)
        except OSError as error:
            self.terminal.append("ERR", f"папка недоступна | {error}")
            return
        self._destination = path
        self._settings.setValue("destination", str(path))
        self._settings.sync()
        self._update_folder_view()
        self.terminal.append("SYS", f"папка изменена | {path_label(path, 120)}")

    def _apply_setting(self, key: str, value: object) -> None:
        if key == "typing":
            mode = str(value)
            if mode not in TYPING_SPEEDS:
                return
            self._typing_mode = mode
            self.terminal.set_animation_speed(TYPING_SPEEDS[mode])
            self.source_bar.set_animation_speed(TYPING_SPEEDS[mode])
            self._settings.setValue("ui/typing", mode)
            self.folder_field.restart()
            self.source_label.restart()
            self.log_label.restart()
        elif key == "splash":
            self._splash_enabled = bool(value)
            self._settings.setValue("ui/splash", self._splash_enabled)
        elif key == "paste_autostart":
            self._paste_autostart = bool(value)
            self._settings.setValue("flow/paste_autostart", self._paste_autostart)
        elif key == "splash_effect":
            effect = str(value)
            if effect not in SPLASH_EFFECTS:
                return
            self._splash_effect = effect
            self._settings.setValue("ui/splash_effect", effect)
        elif key == "splash_speed":
            speed = str(value)
            if speed not in SPLASH_SPEEDS:
                return
            self._splash_speed = speed
            self._settings.setValue("ui/splash_speed", speed)
        else:
            return
        self._settings.sync()

    def _folder_error(self, message: str) -> None:
        self.folder_field.flash_error(message)

    def _invalid(self, log_message: str) -> None:
        self.source_bar.flash_error()
        self.source_bar.focus_input()
        self.terminal.append("ERR", log_message)

    def choose_folder(self) -> None:
        if self._busy:
            return
        start = self._destination if self._destination.exists() else self._destination.parent
        selected = QFileDialog.getExistingDirectory(
            self,
            "Папка для модов BeamNG.drive",
            str(start),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected:
            return
        path = Path(selected)
        try:
            ensure_directory(path)
        except OSError as error:
            self._folder_error(str(error))
            self.terminal.append("ERR", f"папка недоступна | {error}")
            return
        self._destination = path
        self._settings.setValue("destination", str(path))
        self._settings.sync()
        self._update_folder_view()
        self.terminal.append("SYS", f"папка изменена | {path_label(path, 120)}")

    def paste_link(self) -> None:
        if self._busy:
            return
        text = QApplication.clipboard().text().strip()
        if not text:
            self._invalid("в буфере обмена нет текста")
            return
        urls = extract_urls(text)
        if not urls:
            self._invalid("в буфере обмена нет ссылок http или https")
            return
        added = self.source_bar.add_links(urls)
        if added == 0:
            self.terminal.append("WARN", "ссылки уже добавлены")
            self.source_bar.focus_input()
            return
        total = len(extract_urls(self.source_bar.text()))
        if added == 1:
            self.terminal.append("NET", f"ссылка добавлена | {display_host(urls[0])}")
        else:
            self.terminal.append(
                "NET",
                f"добавлено {added} {links_word(added)} | в поле {total}",
            )
        if self._paste_autostart:
            QTimer.singleShot(120, self._autostart_after_paste)

    def _autostart_after_paste(self) -> None:
        if self._busy or self._closing:
            return
        text = self.source_bar.text()
        if text:
            self.start_download(text)

    def start_download(self, raw: str) -> None:
        if self._busy or self._closing:
            return
        urls = extract_urls(raw)
        if not urls:
            self._invalid("в поле нет ссылок http или https")
            return
        feeds = [url for url in urls if is_listing_url(url)]
        if feeds:
            urls = [url for url in urls if not is_listing_url(url)]
            if not urls:
                self._open_feed(feeds[0])
                return
            self.terminal.append("WARN", "ссылки на страницы пропущены в пакете")
        if not urls:
            return
        self._start_batch([QueueTask(url=url) for url in urls])

    def _open_feed(self, url: str) -> None:
        if self._busy or self._closing:
            return
        dialog = FeedDialog(url, self)
        dialog.move(
            self.mapToGlobal(
                QPoint(
                    (self.width() - dialog.width()) // 2,
                    (self.height() - dialog.height()) // 2,
                )
            )
        )
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            items = dialog.selected_items()
            dialog.deleteLater()
            if not items:
                return
            self.source_bar.clear()
            self.terminal.append(
                "SYS",
                f"страница | выбрано {len(items)} модов | {display_host(url)}",
            )
            self._start_batch(
                [QueueTask(url=item.url, title=item.title) for item in items]
            )
            return
        fallback = dialog.fallback_direct
        dialog.deleteLater()
        if result == FeedDialog.FALLBACK_RESULT and fallback:
            self._start_batch([QueueTask(url=url)])

    def _start_batch(self, tasks: list[QueueTask]) -> None:
        if not tasks or self._busy or self._closing:
            return
        try:
            ensure_directory(self._destination)
        except OSError as error:
            self._folder_error(str(error))
            self.source_bar.flash_error()
            self.terminal.append("ERR", f"папка недоступна | {error}")
            return
        self._tasks = list(tasks)
        self._task_index = 0
        self._batch_success = 0
        self._batch_failed = 0
        self._batch_cancelled = 0
        self._batch_skipped = 0
        self._batch_stop = False
        self._skip_current = False
        self.status.set_mode("загрузка")
        self._last_outcome = ""
        self._reveal_path = None
        self._busy = True
        self.source_bar.clear()
        self.source_bar.set_busy(True)
        self.folder_field.set_busy(True)
        self.source_bar.shell.editor.clearFocus()
        self.terminal.set_live(True)
        total = len(self._tasks)
        if total > 1:
            self.terminal.append("SYS", f"очередь | {total} {links_word(total)}")
        else:
            self.terminal.append(
                "SYS", f"задача принята | {display_host(self._tasks[0].url)}"
            )
        self.transfer.reset()
        self._start_task()

    def _start_task(self) -> None:
        if self._closing or not self._tasks:
            return
        task = self._tasks[self._task_index]
        position = self._task_index + 1
        total = len(self._tasks)
        host = display_host(task.url)
        self.transfer.begin_preparing(host)
        if total > 1:
            self.transfer.set_queue(position, total)
            self.terminal.append(
                "SYS", f"задача {position}/{total} | {task.title or host}"
            )
        thread = QThread(self)
        worker = DownloadWorker(task.url, self._destination)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self._on_log)
        worker.meta.connect(self.transfer.begin_transfer)
        worker.progress.connect(self.transfer.update_progress)
        worker.completed.connect(self._on_task_completed)
        worker.failed.connect(self._on_task_failed)
        worker.cancelled.connect(self._on_task_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()

    def cancel_download(self) -> None:
        if not self._busy:
            return
        self._batch_stop = True
        if self._worker is not None:
            self._worker.cancel()
            self.transfer.set_cancelling()
            self.terminal.append("SYS", "запрошена остановка передачи...")
            return
        self._finish_batch()

    def skip_current(self) -> None:
        if not self._busy or self._worker is None:
            return
        if self._task_index + 1 >= len(self._tasks):
            return
        self._skip_current = True
        self._worker.cancel()
        self.transfer.set_cancelling()
        task = self._tasks[self._task_index]
        self.terminal.append(
            "WARN", f"пропуск мода | {task.title or display_host(task.url)}"
        )

    def _probe_network(self) -> None:
        def worker() -> None:
            try:
                online = has_internet()
            except Exception:
                online = False
            self.net_checked.emit(online)

        threading.Thread(target=worker, daemon=True).start()

    def _on_net_state(self, online: bool) -> None:
        self.status.set_net("ok" if online else "нет")
        if not online and not self._net_reported:
            self._net_reported = True
            self.terminal.append("WARN", "нет соединения | проверьте интернет")
        elif online:
            self._net_reported = False

    def _on_log(self, level: str, message: str) -> None:
        self.terminal.append(level, message)

    def _on_task_completed(self, result) -> None:
        self._last_outcome = "success"
        self._batch_success += 1
        self._reveal_path = result.path
        self.transfer.finish_success(result)
        self.status.set_mode("готово")
        if len(self._tasks) <= 1:
            self.terminal.set_live(False)
            self.terminal.append("END", "готово | мод можно подключать в игре")
            if not self.isActiveWindow():
                QApplication.alert(self, 2500)

    def _on_task_failed(self, message: str) -> None:
        self._last_outcome = "error"
        self._batch_failed += 1
        self.transfer.finish_error(message)
        self.terminal.append("ERR", message)
        self.status.set_mode("ошибка")
        self._probe_network()
        if len(self._tasks) <= 1:
            self.terminal.set_live(False)
            if not self.isActiveWindow():
                QApplication.alert(self, 2500)

    def _on_task_cancelled(self) -> None:
        self._last_outcome = "cancelled"
        self.transfer.finish_cancelled()
        if self._skip_current:
            self.terminal.append("WARN", "мод пропущен | временный файл удалён")
            return
        self._batch_cancelled += 1
        self.status.set_mode("остановлено")
        self.terminal.append("WARN", "передача остановлена | временный файл удалён")

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._thread = None
        if self._closing:
            self._busy = False
            QTimer.singleShot(0, self.close)
            return
        if self._skip_current:
            self._skip_current = False
            self._batch_skipped += 1
            if self._task_index + 1 < len(self._tasks):
                self._task_index += 1
                self._start_task()
                return
            self._finish_batch()
            return
        if self._batch_stop:
            self._finish_batch()
            return
        if self._task_index + 1 < len(self._tasks):
            self._task_index += 1
            self._start_task()
            return
        self._finish_batch()

    def _finish_batch(self) -> None:
        total = len(self._tasks)
        success = self._batch_success
        failed = self._batch_failed
        cancelled = self._batch_cancelled
        skipped = max(self._batch_skipped, max(0, total - success - failed - cancelled))
        stopped = self._batch_stop
        self._busy = False
        self.source_bar.set_busy(False)
        self.folder_field.set_busy(False)
        self.terminal.set_live(False)
        self.transfer.set_queue(0, 0)
        self.status.set_mode(
            "ошибка" if failed and not success else "готово"
        )
        if total > 1:
            self.transfer.finish_batch(
                total, success, failed, cancelled, skipped, stopped=stopped
            )
            if stopped:
                self._last_outcome = "cancelled"
                self.status.set_mode("остановлено")
                self.terminal.append(
                    "WARN",
                    "очередь остановлена | "
                    f"готово {success} | ошибок {failed} | пропущено {skipped}",
                )
            elif success + skipped == total:
                self._last_outcome = "success"
                self.terminal.append(
                    "END",
                    f"очередь завершена | готово {success} | пропущено {skipped}",
                )
            else:
                self._last_outcome = "error"
                self.terminal.append(
                    "WARN",
                    f"очередь завершена | готово {success} | ошибок {failed}"
                    + (f" | пропущено {skipped}" if skipped else ""),
                )
            if not self.isActiveWindow():
                QApplication.alert(self, 2500)
        self.source_bar.focus_input()
        self._tasks = []
        self._task_index = 0
        self._batch_stop = False

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_escape(self) -> None:
        if self._busy:
            self.cancel_download()
            return
        if self._closing:
            return
        if self.source_bar.text():
            self.source_bar.clear()
        self.source_bar.focus_input()

    def open_destination(self) -> None:
        try:
            ensure_directory(self._destination)
        except OSError as error:
            self._folder_error(str(error))
            self.terminal.append("ERR", f"не удалось открыть папку | {error}")
            return
        try:
            open_folder(self._destination)
        except OSError as error:
            self.terminal.append("ERR", f"проводник недоступен | {error}")

    def reveal_result(self) -> None:
        if self._reveal_path is not None and self._reveal_path.exists():
            try:
                reveal_in_explorer(self._reveal_path)
                return
            except OSError as error:
                self.terminal.append("ERR", f"проводник недоступен | {error}")
        self.open_destination()

    def dragEnterEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            return
        mime = event.mimeData()
        if mime.hasUrls():
            if any(url.scheme().lower() in {"http", "https"} for url in mime.urls()):
                event.acceptProposedAction()
                return
        if mime.hasText() and extract_urls(mime.text()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            return
        mime = event.mimeData()
        candidates: list[str] = []
        if mime.hasUrls():
            candidates.extend(
                url.toString()
                for url in mime.urls()
                if url.scheme().lower() in {"http", "https"}
            )
        if mime.hasText():
            candidates.extend(extract_urls(mime.text()))
        urls = extract_urls("\n".join(candidates))
        if not urls:
            event.ignore()
            return
        event.acceptProposedAction()
        text = "\n".join(urls)
        self.source_bar.set_text(text)
        self.start_download(text)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._frame_applied:
            self._frame_applied = True
            QTimer.singleShot(0, self._apply_windows_frame)
        QTimer.singleShot(260, self.source_bar.focus_input)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def _apply_windows_frame(self) -> None:
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            square = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(square), ctypes.sizeof(square))
            dark = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and not self.isMaximized():
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST:
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    point = self.mapFromGlobal(QPoint(x, y))
                    edge = 6
                    left = point.x() < edge
                    right = point.x() >= self.width() - edge
                    top = point.y() < edge
                    bottom = point.y() >= self.height() - edge
                    if top and left:
                        return True, HTTOPLEFT
                    if top and right:
                        return True, HTTOPRIGHT
                    if bottom and left:
                        return True, HTBOTTOMLEFT
                    if bottom and right:
                        return True, HTBOTTOMRIGHT
                    if top:
                        return True, HTTOP
                    if bottom:
                        return True, HTBOTTOM
                    if left:
                        return True, HTLEFT
                    if right:
                        return True, HTRIGHT
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        backdrop.paint(painter, self.width(), self.height())
        painter.setPen(QPen(theme.BORDER_STRONG, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing:
            if self._thread is not None and self._thread.isRunning():
                event.ignore()
                return
            self._save_state()
            event.accept()
            return
        if self._busy:
            dialog = CloseDialog(self)
            dialog.move(
                self.mapToGlobal(
                    QPoint(
                        (self.width() - dialog.width()) // 2,
                        (self.height() - dialog.height()) // 2,
                    )
                )
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                event.ignore()
                return
            event.ignore()
            self._closing = True
            self._batch_stop = True
            self.transfer.set_cancelling()
            self.terminal.append("SYS", "закрытие после остановки передачи...")
            if self._worker is not None:
                self._worker.cancel()
            else:
                self._busy = False
                QTimer.singleShot(0, self.close)
            return
        self._save_state()
        event.accept()

    def _save_state(self) -> None:
        if not self.isMaximized() and not self.isMinimized():
            self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("destination", str(self._destination))
        self._settings.sync()
