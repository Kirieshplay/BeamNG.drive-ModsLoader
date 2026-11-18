from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui import theme
from ui.main_window import MainWindow


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    payload = b""
    slow = False
    fail = False

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.fail or not self.path.startswith("/file"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = self.payload
        start = 0
        header = self.headers.get("Range")
        if header and header.startswith("bytes="):
            start = int(header.split("=", 1)[1].split("-", 1)[0])
        chunk = data[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header(
            "Content-Disposition", 'attachment; filename="local_test_mod.zip"'
        )
        self.send_header("Content-Length", str(len(chunk)))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        self.end_headers()
        try:
            if self.slow:
                block = 65536
                for offset in range(0, len(chunk), block):
                    self.wfile.write(chunk[offset : offset + block])
                    self.wfile.flush()
                    time.sleep(0.04)
            else:
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def wait_until(app: QApplication, predicate, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def main() -> int:
    payload = os.urandom(3 * 1024 * 1024)
    Handler.payload = payload
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    app = QApplication(sys.argv)
    app.setApplicationName("BeamNGModsTest")
    app.setOrganizationName("BeamNGModsTest")
    assets = ROOT / "assets"
    theme.load_fonts(assets)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.GLOBAL_STYLE.replace("'Cascadia Mono'", f"'{theme.MONO_FAMILY}'"))
    config = Path(tempfile.mkdtemp(prefix="beamng_cfg_"))
    output = Path(tempfile.mkdtemp(prefix="beamng_out_"))
    window = MainWindow(assets)
    window._settings = QSettings(str(config / "settings.ini"), QSettings.Format.IniFormat)
    window._destination = output
    window._update_folder_view()
    failures: list[str] = []

    url = f"http://127.0.0.1:{port}/file.zip"
    print("stage: success start", flush=True)
    QApplication.clipboard().setText(url)
    window.paste_link()
    if window.source_bar.text() != url:
        failures.append("paste did not fill the source field")
    QTest.keyClick(window.source_bar.shell.editor, Qt.Key.Key_Return)
    finished = wait_until(app, lambda: not window._busy, 25)
    print("stage: success end", window._last_outcome, flush=True)
    target = output / "local_test_mod.zip"
    if not finished:
        failures.append("success flow did not finish")
    if not target.is_file():
        failures.append("downloaded file is missing")
    elif target.read_bytes() != payload:
        failures.append("downloaded bytes differ")
    if window._last_outcome != "success":
        failures.append(f"unexpected outcome: {window._last_outcome}")
    if window.transfer._state != "success":
        failures.append(f"unexpected panel state: {window.transfer._state}")

    Handler.slow = True
    Handler.payload = os.urandom(10 * 1024 * 1024)
    slow_url = f"http://127.0.0.1:{port}/file_slow.zip"
    print("stage: cancel start", flush=True)
    window.start_download(slow_url)
    started = wait_until(app, lambda: window.transfer._downloaded > 400_000, 12)
    print("stage: cancel started", started, window.transfer._downloaded, flush=True)
    if not started:
        failures.append("slow download never started")
    window.cancel_download()
    cancelled = wait_until(app, lambda: not window._busy, 20)
    print("stage: cancel end", cancelled, window._last_outcome, flush=True)
    if not cancelled:
        failures.append("cancel flow did not finish")
    if window._last_outcome != "cancelled":
        failures.append(f"unexpected cancel outcome: {window._last_outcome}")
    leftovers = list(output.glob("*.part"))
    if leftovers:
        failures.append(f"part file left behind: {leftovers}")

    Handler.slow = False
    Handler.fail = True
    print("stage: failure start", flush=True)
    window.start_download(f"http://127.0.0.1:{port}/missing.zip")
    failed = wait_until(app, lambda: not window._busy, 20)
    print("stage: failure end", failed, window._last_outcome, flush=True)
    if not failed:
        failures.append("failure flow did not finish")
    if window._last_outcome != "error":
        failures.append(f"unexpected failure outcome: {window._last_outcome}")

    print("stage: unsupported start", flush=True)
    window.start_download("https://mega.nz/file/unsupported")
    unsupported = wait_until(app, lambda: not window._busy, 20)
    print("stage: unsupported end", unsupported, window._last_outcome, flush=True)
    if not unsupported:
        failures.append("unsupported host flow did not finish")
    if window._last_outcome != "error":
        failures.append(f"unexpected unsupported outcome: {window._last_outcome}")
    if window._busy:
        failures.append("window still busy at end")

    server.shutdown()
    window._closing = True
    window.close()
    app.processEvents()
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1
    print("FLOW OK: success, cancel, error")
    print("bytes:", target.stat().st_size)
    print("panel:", window.transfer._state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
