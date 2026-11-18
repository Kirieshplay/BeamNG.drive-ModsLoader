from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.pages import FeedError, fetch_feed, is_listing_url, parse_feed
from ui import theme
from ui.feed_dialog import FeedDialog
from ui.main_window import MainWindow, QueueTask

PAGE_TEMPLATE = """<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Моды BeamNG.drive — BeamNGhub</title></head>
<body>
<div id="content-block">
<article class="short">
  <a class="short__img" href="/files/mod-a.zip"><img src="/thumb.png" alt="A"></a>
  <h2 class="short__title"><a href="/files/mod-a.zip">Alpha Pack</a></h2>
  <div class="short_meta_vers"><div>v1.2</div></div>
</article>
<article class="short">
  <a class="short__img" href="/files/mod-b.zip"><img src="/thumb.png" alt="B"></a>
  <h2 class="short__title"><a href="/files/mod-b.zip">Beta Pack</a></h2>
  <div class="short_meta_vers"><div>v3.0</div></div>
</article>
<article class="short">
  <a class="short__img" href="/files/mod-c.zip"><img src="/thumb.png" alt="C"></a>
  <h2 class="short__title"><a href="/files/mod-c.zip">Gamma Pack</a></h2>
  <div class="short_meta_vers"><div>v0.9</div></div>
</article>
<article class="short">
  <h2 class="short__title"><a href="/files/mod-a.zip">Alpha Duplicate</a></h2>
</article>
<article class="short">
  <h2 class="short__title"><a href="https://example.com/foreign-mod.html">Foreign Mod</a></h2>
</article>
</div>
</body>
</html>
"""


def make_png(color: str) -> bytes:
    image = QImage(128, 80, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    path = Path(tempfile.gettempdir()) / f"beamng_feed_{color.strip('#')}.png"
    image.save(str(path), "PNG")
    data = path.read_bytes()
    try:
        path.unlink()
    except OSError:
        pass
    return data


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    media: dict[str, bytes] = {}
    slow = False

    def log_message(self, format, *args):
        pass

    def _send_bytes(self, data: bytes, content_type: str, filename: str = "") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/page/1/":
            self._send_bytes(
                PAGE_TEMPLATE.encode("utf-8"), "text/html; charset=utf-8"
            )
            return
        if path == "/thumb.png":
            self._send_bytes(self.media["thumb"], "image/png")
            return
        if path == "/direct.zip":
            self._send_bytes(b"direct-binary" * 128, "application/zip", "direct.zip")
            return
        if path.startswith("/files/") and path.endswith(".zip"):
            name = path.rsplit("/", 1)[-1]
            if name == "missing.zip":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = self.media.get(name, b"")
            if name == "slow.zip":
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Disposition", 'attachment; filename="slow.zip"'
                )
                self.end_headers()
                block = 65536
                try:
                    for offset in range(0, len(data), block):
                        self.wfile.write(data[offset : offset + block])
                        self.wfile.flush()
                        time.sleep(0.03)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                return
            self._send_bytes(data, "application/zip", name)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


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
    app = QApplication(sys.argv)
    app.setApplicationName("BeamNGModsFeedTest")
    app.setOrganizationName("BeamNGModsFeedTest")
    assets = ROOT / "assets"
    theme.load_fonts(assets)
    app.setStyle("Fusion")
    try:
        app.setStyleSheet(
            theme.GLOBAL_STYLE.replace("'Cascadia Mono'", f"'{theme.MONO_FAMILY}'")
        )
    except Exception:
        pass
    failures: list[str] = []

    checks = [
        ("https://beamnghub.ru/page/8/", True),
        ("https://beamnghub.ru/", True),
        ("https://beamnghub.ru/", True),
        ("https://beamnghub.ru/mods/car-pack.html", False),
        ("https://modsfire.com/Z0606lhmRM8n3K8", False),
        ("https://example.com/files/mod.zip", False),
        ("https://example.com/mods/", True),
        ("https://example.com/page/2/", True),
        ("https://example.com/download/file", False),
    ]
    for url, expected in checks:
        actual = is_listing_url(url)
        if actual != expected:
            failures.append(f"listing check {url}: {actual} != {expected}")

    thumb = make_png("#3b4a52")
    Handler.media = {
        "thumb": thumb,
        "thumb.png": thumb,
        "mod-a.zip": os.urandom(240_000),
        "mod-b.zip": os.urandom(180_000),
        "mod-c.zip": os.urandom(150_000),
        "slow.zip": os.urandom(9 * 1024 * 1024),
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    page_url = base + "/page/1/"
    temp = Path(tempfile.gettempdir())

    parsed = parse_feed(page_url, PAGE_TEMPLATE)
    if [item.title for item in parsed.items] != [
        "Alpha Pack",
        "Beta Pack",
        "Gamma Pack",
    ]:
        failures.append(f"parse titles: {[item.title for item in parsed.items]}")
    if [item.version for item in parsed.items] != ["v1.2", "v3.0", "v0.9"]:
        failures.append(f"parse versions: {[item.version for item in parsed.items]}")
    if parsed.title != "Моды BeamNG.drive":
        failures.append(f"page title: {parsed.title}")

    try:
        fetched = fetch_feed(page_url)
    except FeedError as error:
        failures.append(f"fetch feed failed: {error}")
        fetched = None
    if fetched is not None and len(fetched.items) != 3:
        failures.append(f"fetched items: {len(fetched.items)}")

    print("stage: dialog rows", flush=True)
    dialog = FeedDialog(page_url)
    dialog.show()
    loaded = wait_until(app, lambda: len(dialog._rows) == 3, 20)
    if not loaded:
        failures.append("feed dialog rows did not load")
    if dialog.loading_label.isVisible():
        failures.append("loading label still visible")
    if dialog.count_label.text() != "3 МОДА":
        failures.append(f"count label: {dialog.count_label.text()}")
    if dialog.download_button.isEnabled():
        failures.append("download enabled before selection")
    dialog.grab().save(str(temp / "beamng_feed_dialog.png"))
    dialog.all_button.click()
    if sum(1 for row in dialog._rows if row.isChecked()) != 3:
        failures.append("select all did not check every row")
    if dialog.selection_label.text() != "ВЫБРАНО 3 / 3":
        failures.append(f"selection label: {dialog.selection_label.text()}")
    if not dialog.download_button.isEnabled():
        failures.append("download disabled after select all")
    QTest.qWait(500)
    dialog.grab().save(str(temp / "beamng_feed_selected.png"))
    dialog.download_button.click()
    accepted = wait_until(app, lambda: not dialog.isVisible(), 5)
    if not accepted or dialog.result() != int(FeedDialog.DialogCode.Accepted):
        failures.append(f"dialog accept: {dialog.result()}")
    if len(dialog.selected_items()) != 3:
        failures.append("selected items lost after accept")
    dialog.deleteLater()

    print("stage: fallback", flush=True)
    fallback = FeedDialog(base + "/direct.zip")
    fallback.show()
    fallback_done = wait_until(
        app,
        lambda: not fallback.isVisible()
        or fallback.result() == FeedDialog.FALLBACK_RESULT,
        15,
    )
    if not fallback_done:
        failures.append("fallback dialog did not finish")
    if fallback.result() != FeedDialog.FALLBACK_RESULT:
        failures.append(f"fallback result: {fallback.result()}")
    if not fallback.fallback_direct:
        failures.append("fallback flag not set")
    fallback.deleteLater()

    print("stage: queue success", flush=True)
    config = Path(tempfile.mkdtemp(prefix="beamng_feed_cfg_"))
    output = Path(tempfile.mkdtemp(prefix="beamng_feed_out_"))
    window = MainWindow(assets)
    window._settings = QSettings(str(config / "settings.ini"), QSettings.Format.IniFormat)
    window._destination = output
    window._update_folder_view()
    window._start_batch(
        [
            QueueTask(url=base + "/files/mod-a.zip"),
            QueueTask(url=base + "/files/mod-b.zip"),
            QueueTask(url=base + "/files/mod-c.zip"),
        ]
    )
    finished = wait_until(app, lambda: not window._busy, 40)
    if not finished:
        failures.append("queue success did not finish")
    if window._batch_success != 3 or window._batch_failed != 0:
        failures.append(
            f"queue counters: success={window._batch_success} failed={window._batch_failed}"
        )
    if window.transfer._state != "success":
        failures.append(f"queue panel: {window.transfer._state}")
    for name in ("mod-a.zip", "mod-b.zip", "mod-c.zip"):
        target = output / name
        if not target.is_file():
            failures.append(f"queue file missing: {name}")
        elif target.read_bytes() != Handler.media[name]:
            failures.append(f"queue bytes differ: {name}")

    print("stage: queue partial", flush=True)
    Handler.media["partial.zip"] = os.urandom(120_000)
    window._start_batch(
        [
            QueueTask(url=base + "/files/partial.zip"),
            QueueTask(url=base + "/files/missing.zip"),
            QueueTask(url=base + "/files/mod-a.zip"),
        ]
    )
    partial = wait_until(app, lambda: not window._busy, 40)
    if not partial:
        failures.append("partial queue did not finish")
    if window._batch_success != 2 or window._batch_failed != 1:
        failures.append(
            f"partial counters: success={window._batch_success} failed={window._batch_failed}"
        )
    if window.transfer._state != "partial":
        failures.append(f"partial panel: {window.transfer._state}")

    print("stage: queue stop", flush=True)
    stop_output = Path(tempfile.mkdtemp(prefix="beamng_feed_stop_"))
    window._destination = stop_output
    window._update_folder_view()
    window._start_batch(
        [
            QueueTask(url=base + "/files/mod-a.zip"),
            QueueTask(url=base + "/files/slow.zip"),
            QueueTask(url=base + "/files/mod-c.zip"),
        ]
    )
    started = wait_until(app, lambda: window.transfer._downloaded > 300_000, 15)
    if not started:
        failures.append("slow queue item never started")
    window.cancel_download()
    stopped = wait_until(app, lambda: not window._busy, 25)
    if not stopped:
        failures.append("stopped queue did not finish")
    if window.transfer._state != "cancelled":
        failures.append(f"stop panel: {window.transfer._state}")
    if window._batch_success != 1:
        failures.append(f"stop success count: {window._batch_success}")
    if window._batch_cancelled != 1:
        failures.append(f"stop cancelled count: {window._batch_cancelled}")
    leftovers = list(stop_output.glob("*.part"))
    if leftovers:
        failures.append(f"part files left: {leftovers}")
    if (stop_output / "mod-c.zip").exists():
        failures.append("queue continued after cancel")

    print("stage: listing launch", flush=True)
    listing_output = Path(tempfile.mkdtemp(prefix="beamng_feed_pick_"))
    window._destination = listing_output
    window._update_folder_view()
    state = {"dialog": None, "start": time.time()}

    def drive() -> None:
        found = [
            widget
            for widget in QApplication.topLevelWidgets()
            if isinstance(widget, FeedDialog) and widget.isVisible()
        ]
        if not found:
            if time.time() - state["start"] < 25:
                QTimer.singleShot(60, drive)
            return
        dialog_widget = found[0]
        state["dialog"] = dialog_widget
        if len(dialog_widget._rows) < 3:
            QTimer.singleShot(60, drive)
            return
        dialog_widget._rows[0].setChecked(True)
        dialog_widget._rows[2].setChecked(True)
        dialog_widget.download_button.click()

    QTimer.singleShot(60, drive)
    window.start_download(page_url)
    picked = wait_until(app, lambda: not window._busy, 40)
    if state["dialog"] is None:
        failures.append("listing did not open the picker")
    if not picked:
        failures.append("listing download did not finish")
    if window._batch_success != 2:
        failures.append(f"listing picked count: {window._batch_success}")
    if not (listing_output / "mod-a.zip").is_file():
        failures.append("listing did not save first pick")
    if not (listing_output / "mod-c.zip").is_file():
        failures.append("listing did not save third pick")
    if (listing_output / "mod-b.zip").exists():
        failures.append("listing downloaded an unselected pick")

    server.shutdown()
    window._closing = True
    window.close()
    app.processEvents()
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1
    print("FEED OK: parse, picker, fallback, queue success/partial/stop, listing launch")
    print("capture:", temp / "beamng_feed_dialog.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
