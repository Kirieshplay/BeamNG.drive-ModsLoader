from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.engine import DownloadEngine


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    payload = b""
    drop_after = 0
    ignore_range = False
    dropped: set[str] = set()

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        data = self.payload
        header = self.headers.get("Range")
        start = 0
        if header and header.startswith("bytes=") and not self.ignore_range:
            start = int(header.split("=", 1)[1].split("-", 1)[0])
        body = data[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", 'attachment; filename="resume_test.zip"')
        self.send_header("Content-Length", str(len(body)))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        self.end_headers()
        try:
            if (
                self.drop_after
                and start == 0
                and self.path not in self.dropped
            ):
                self.dropped.add(self.path)
                self.wfile.write(body[: self.drop_after])
                self.wfile.flush()
                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                return
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def serve(handler) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def run_case(name: str, payload: bytes, drop_after: int, ignore_range: bool) -> None:
    class CaseHandler(Handler):
        pass

    CaseHandler.payload = payload
    CaseHandler.drop_after = drop_after
    CaseHandler.ignore_range = ignore_range
    CaseHandler.dropped = set()
    server, port = serve(CaseHandler)
    output = Path(tempfile.mkdtemp(prefix="beamng_resume_"))
    logs: list[tuple[str, str]] = []
    try:
        result = DownloadEngine(
            f"http://127.0.0.1:{port}/resume.zip",
            output,
            on_log=lambda level, message: logs.append((level, message)),
        ).run()
        if result.path.read_bytes() != payload:
            raise AssertionError(f"{name}: payload mismatch")
        print(f"{name}: OK · {result.size} bytes · retries={sum(1 for l in logs if 'повтор' in l[1])}")
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    run_case("resume after drop", os.urandom(2 * 1024 * 1024), 700_000, False)
    run_case("server ignores range", os.urandom(1536 * 1024), 420_000, True)
    print("RESUME OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
