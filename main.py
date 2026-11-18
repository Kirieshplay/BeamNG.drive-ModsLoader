from __future__ import annotations

import ctypes
import sys
import tempfile
import threading
import traceback
from pathlib import Path

SERVER_KEY = "BeamNGMods.Desktop"


def _asset_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets"
    return Path(__file__).resolve().parent / "assets"


def _fatal(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "BeamNG.drive", 0x10)
    except Exception:
        print(message)


def _crash_log(error_type, error, tb) -> None:
    if sys.stderr is not None:
        traceback.print_exception(error_type, error, tb)
    try:
        target = Path(tempfile.gettempdir()) / "beamng_mods_crash.log"
        with open(target, "a", encoding="utf-8") as handle:
            handle.write("\n")
            traceback.print_exception(error_type, error, tb, file=handle)
    except OSError:
        pass


def _ensure_dependencies() -> bool:
    if getattr(sys, "frozen", False):
        return True
    try:
        import bootstrap
    except Exception:
        return True
    try:
        return bootstrap.ensure_dependencies()
    except Exception:
        return False


def main() -> int:
    if not _ensure_dependencies():
        _fatal(
            "Не удалось установить зависимости.\n\n"
            "Установите вручную:\n"
            "py -m pip install -r requirements.txt"
        )
        return 1
    try:
        from PySide6.QtCore import QLocale, Qt, QTimer
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWidgets import QApplication

        from ui import theme
        from ui.main_window import MainWindow
        from ui.splash import SplashScreen
    except ImportError as error:
        _fatal(
            "Не удалось загрузить компоненты приложения.\n\n"
            f"{error}\n\n"
            "Установите зависимости командой:\n"
            "py -m pip install PySide6 requests beautifulsoup4"
        )
        return 1
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BeamNGMods.Desktop.1"
            )
        except Exception:
            pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    class SafeApplication(QApplication):
        def notify(self, receiver, event):
            try:
                return super().notify(receiver, event)
            except Exception:
                _crash_log(*sys.exc_info())
                return False

    app = SafeApplication(sys.argv)
    app.setApplicationName("BeamNGMods")
    app.setApplicationDisplayName("BeamNG.drive")
    app.setOrganizationName("BeamNGMods")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")
    QLocale.setDefault(QLocale(QLocale.Language.Russian, QLocale.Country.Russia))
    sys.excepthook = _crash_log

    def thread_crash(args) -> None:
        _crash_log(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_crash
    probe = QLocalSocket()
    probe.connectToServer(SERVER_KEY)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return 0
    QLocalServer.removeServer(SERVER_KEY)
    server = QLocalServer()
    server.listen(SERVER_KEY)
    assets = _asset_root()
    theme.load_fonts(assets)
    style = theme.GLOBAL_STYLE.replace("'Cascadia Mono'", f"'{theme.MONO_FAMILY}'")
    app.setStyleSheet(style)
    app.setWindowIcon(QIcon(str(assets / "icon.ico")))
    window = MainWindow(assets)
    splash = (
        SplashScreen(window.splash_effect, window.splash_speed)
        if window.splash_enabled
        else None
    )
    state = {"revealed": False, "splash_done": splash is None}

    def reveal() -> None:
        if state["revealed"]:
            return
        state["revealed"] = True
        if window.isMinimized():
            window.showNormal()
        window.show()
        window.raise_()
        window.activateWindow()

    def splash_finished() -> None:
        state["splash_done"] = True
        reveal()

    def skip_splash() -> None:
        if splash is None or state["splash_done"]:
            reveal()
            return
        splash.finish_now()

    def accept_connections() -> None:
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is not None:
                connection.readAll()
                connection.disconnectFromServer()
                connection.deleteLater()
        skip_splash()

    server.newConnection.connect(accept_connections)
    if splash is None:
        reveal()
    else:
        splash.finished.connect(splash_finished)
        splash.show()
        splash.raise_()
        splash.activateWindow()
        QTimer.singleShot(splash.hold_ms + 1400, splash.finish_now)
        QTimer.singleShot(splash.hold_ms + 2400, reveal)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
