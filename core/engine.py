from __future__ import annotations

import os
import shutil
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from core.net import has_internet
from core.resolvers import DownloadCancelled, DownloadPreparer, PreparedFile, TransferError
from core.utils import ensure_directory, human_bytes, sanitize_filename, unique_path


@dataclass(slots=True)
class TransferMeta:
    filename: str
    host: str
    total: int | None
    path: Path


@dataclass(slots=True)
class TransferProgress:
    downloaded: int
    total: int | None
    speed: float
    eta: float | None
    percent: float | None


@dataclass(slots=True)
class TransferResult:
    path: Path
    filename: str
    size: int
    host: str


LogCallback = Callable[[str, str], None]
MetaCallback = Callable[[TransferMeta], None]
ProgressCallback = Callable[[TransferProgress], None]
CancelCallback = Callable[[], bool]

MIN_FREE_MARGIN = 16 * 1024 * 1024
CHUNK_SIZE = 512 * 1024
MAX_ATTEMPTS = 4


class DownloadEngine:
    def __init__(
        self,
        url: str,
        destination: Path,
        on_log: LogCallback | None = None,
        on_meta: MetaCallback | None = None,
        on_progress: ProgressCallback | None = None,
        cancel: CancelCallback | None = None,
    ) -> None:
        self.url = url
        self.destination = Path(destination)
        self._log = on_log or (lambda level, message: None)
        self._meta = on_meta or (lambda meta: None)
        self._progress = on_progress or (lambda update: None)
        self._cancel = cancel or (lambda: False)
        self.session = requests.Session()
        self._response: requests.Response | None = None

    def _check_cancel(self) -> None:
        if self._cancel():
            raise DownloadCancelled()

    def run(self) -> TransferResult:
        ensure_directory(self.destination)
        self._log("SYS", "папка назначения доступна для записи")
        preparer = DownloadPreparer(self._log, self._cancel, self.session)
        prepared = preparer.prepare(self.url)
        target = unique_path(self.destination, prepared.filename)
        part_path = Path(str(target) + ".part")
        try:
            self._validate_space(prepared, target)
            sane_name = sanitize_filename(prepared.filename)
            meta = TransferMeta(sane_name, prepared.host, prepared.total, target)
            self._meta(meta)
            if prepared.total:
                self._log(
                    "FILE",
                    f"{sane_name} | {human_bytes(prepared.total)} | {prepared.host}",
                )
            else:
                self._log("FILE", f"{sane_name} | размер уточняется | {prepared.host}")
            if target.suffix.lower() in {".rar", ".7z"}:
                self._log("WARN", "архив не является ZIP - для установки распакуйте его вручную")
            self._download(prepared, target, part_path)
            size = target.stat().st_size
            self._progress(
                TransferProgress(
                    downloaded=size,
                    total=size,
                    speed=0.0,
                    eta=0.0,
                    percent=100.0,
                )
            )
            self._log("OK", f"готово | {human_bytes(size)} | файл записан")
            self._log("SYS", str(target))
            return TransferResult(target, target.name, size, prepared.host)
        except DownloadCancelled:
            self._cleanup_part(part_path)
            raise
        except Exception:
            self._cleanup_part(part_path)
            raise
        finally:
            if self._response is not None:
                self._response.close()
                self._response = None

    def _validate_space(self, prepared: PreparedFile, target: Path) -> None:
        self._check_cancel()
        try:
            free = shutil.disk_usage(self.destination).free
        except OSError:
            free = None
        if free is None:
            return
        if prepared.total is not None and free < prepared.total + MIN_FREE_MARGIN:
            raise TransferError(
                "Недостаточно свободного места: нужно "
                f"{human_bytes(prepared.total)}. Освободите место и повторите."
            )

    def _download(self, prepared: PreparedFile, target: Path, part_path: Path) -> None:
        offset = 0
        start_time = time.monotonic()
        samples: deque[tuple[float, int]] = deque()
        last_update = 0.0
        response = prepared.response
        self._response = response
        first_chunk = True
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._check_cancel()
            if attempt > 1:
                response, restart = self._reopen(prepared, offset)
                self._response = response
                if restart:
                    offset = 0
                start_time = time.monotonic()
                samples.clear()
                first_chunk = True
            mode = "ab" if offset > 0 else "wb"
            try:
                with open(part_path, mode) as handle:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        self._check_cancel()
                        if not chunk:
                            continue
                        if first_chunk:
                            if offset == 0:
                                self._verify_payload_start(chunk, prepared)
                            first_chunk = False
                        handle.write(chunk)
                        offset += len(chunk)
                        now = time.monotonic()
                        if now - last_update >= 0.08:
                            update = self._make_progress(offset, prepared.total, now, start_time, samples)
                            self._progress(update)
                            last_update = now
                    handle.flush()
                    os.fsync(handle.fileno())
                response.close()
                self._response = None
                if prepared.total is not None and offset < prepared.total:
                    raise TransferError(
                        f"соединение закрыто раньше времени: {human_bytes(offset)} из {human_bytes(prepared.total)}"
                    )
                if prepared.total is not None and offset > prepared.total:
                    raise TransferError("сервер передал больше данных, чем заявлено.")
                if offset == 0:
                    raise TransferError("сервер вернул пустой файл.")
                self._progress(self._make_progress(offset, prepared.total or offset, time.monotonic(), start_time, samples))
                os.replace(part_path, target)
                if prepared.total is None:
                    self._meta(TransferMeta(target.name, prepared.host, offset, target))
                return
            except DownloadCancelled:
                response.close()
                self._response = None
                raise
            except (requests.RequestException, TransferError) as error:
                response.close()
                self._response = None
                if isinstance(error, requests.ConnectionError) and not has_internet(1.0):
                    raise TransferError(
                        "нет соединения | проверьте интернет и повторите"
                    ) from error
                if attempt >= MAX_ATTEMPTS:
                    raise TransferError(
                        f"загрузка прервана после {attempt} попыток: {self._short_error(error)}"
                    ) from error
                self._log(
                    "WARN",
                    f"сбой соединения | повтор {attempt + 1}/{MAX_ATTEMPTS} | {self._short_error(error)}",
                )
                self._wait_before_retry(attempt)
                try:
                    offset = part_path.stat().st_size
                except OSError:
                    offset = 0
                if prepared.total is not None and offset == prepared.total:
                    os.replace(part_path, target)
                    self._progress(
                        self._make_progress(offset, prepared.total, time.monotonic(), start_time, samples)
                    )
                    return
            except OSError as error:
                response.close()
                self._response = None
                raise TransferError(f"Не удалось записать файл: {error}") from error
        raise TransferError("не удалось завершить загрузку.")

    def _make_progress(
        self,
        offset: int,
        total: int | None,
        now: float,
        start_time: float,
        samples: deque[tuple[float, int]],
    ) -> TransferProgress:
        samples.append((now, offset))
        while len(samples) > 2 and now - samples[0][0] > 2.4:
            samples.popleft()
        if len(samples) >= 2:
            elapsed = samples[-1][0] - samples[0][0]
            delta = samples[-1][1] - samples[0][1]
            speed = delta / elapsed if elapsed > 0.05 else 0.0
        else:
            elapsed = max(now - start_time, 0.05)
            speed = offset / elapsed
        if speed < 0:
            speed = 0.0
        eta = (total - offset) / speed if total is not None and speed > 0 else None
        percent = offset / total * 100 if total else None
        return TransferProgress(offset, total, speed, eta, percent)

    def _reopen(self, prepared: PreparedFile, offset: int) -> tuple[requests.Response, bool]:
        self._check_cancel()
        headers: dict[str, str] = {}
        if prepared.referer:
            headers["Referer"] = prepared.referer
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
            validator = prepared.etag or prepared.last_modified
            if validator:
                headers["If-Range"] = validator
        try:
            response = self.session.get(
                prepared.url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(20, 30),
            )
        except requests.RequestException as error:
            if isinstance(error, requests.ConnectionError) and not has_internet(1.0):
                raise TransferError("нет соединения | проверьте интернет") from error
            raise TransferError("не удалось возобновить соединение.") from error
        if response.status_code == 416 and prepared.total is not None and offset >= prepared.total:
            response.close()
            raise TransferError("файл уже получен полностью.")
        if response.status_code not in {200, 206}:
            response.close()
            if response.status_code in {401, 403}:
                raise TransferError("прямая ссылка истекла. Запустите скачивание заново.")
            raise TransferError(f"возобновление отклонено сервером (HTTP {response.status_code}).")
        restart = response.status_code == 200 and offset > 0
        if restart:
            self._log("WARN", "сервер не поддерживает докачку | передача начата заново")
        return response, restart

    def _wait_before_retry(self, attempt: int) -> None:
        delay = min(6.0, 1.2 * attempt)
        finish = time.monotonic() + delay
        while time.monotonic() < finish:
            self._check_cancel()
            time.sleep(0.1)

    def _verify_payload_start(self, chunk: bytes, prepared: PreparedFile) -> None:
        head = chunk[:512].lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html") or head.startswith(b"<?xml"):
            raise TransferError("сервер вернул страницу вместо файла. Проверьте ссылку.")
        if prepared.filename.lower().endswith(".zip") and not head.startswith(b"pk"):
            self._log("WARN", "содержимое файла не похоже на ZIP-архив")

    def _short_error(self, error: Exception) -> str:
        message = str(error).strip().replace("\n", " ")
        if len(message) > 160:
            message = message[:157] + "..."
        return message or error.__class__.__name__

    def _cleanup_part(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass


def cancellable_sleep(seconds: float, cancel: CancelCallback) -> None:
    finish = time.monotonic() + seconds
    while time.monotonic() < finish:
        if cancel():
            raise DownloadCancelled()
        time.sleep(0.05)
