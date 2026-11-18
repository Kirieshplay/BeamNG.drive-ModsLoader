from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from core.engine import DownloadEngine
from core.pages import FeedError, NotAFeedError, fetch_feed
from core.resolvers import DownloadCancelled, TransferError


class FeedWorker(QObject):
    loaded = Signal(object)
    failed = Signal(str)
    not_feed = Signal()
    cancelled = Signal()
    finished = Signal()

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            page = fetch_feed(self._url, self._cancel_event.is_set)
            self.loaded.emit(page)
        except DownloadCancelled:
            self.cancelled.emit()
        except NotAFeedError:
            self.not_feed.emit()
        except FeedError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Не удалось разобрать страницу. Повторите попытку.")
            traceback.print_exc()
        finally:
            self.finished.emit()


class DownloadWorker(QObject):
    log = Signal(str, str)
    meta = Signal(object)
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, url: str, destination: Path) -> None:
        super().__init__()
        self._url = url
        self._destination = Path(destination)
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            engine = DownloadEngine(
                url=self._url,
                destination=self._destination,
                on_log=lambda level, message: self.log.emit(level, message),
                on_meta=lambda meta: self.meta.emit(meta),
                on_progress=lambda update: self.progress.emit(update),
                cancel=self._cancel_event.is_set,
            )
            result = engine.run()
            self.completed.emit(result)
        except DownloadCancelled:
            self.cancelled.emit()
        except TransferError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Непредвиденная ошибка передачи. Подробности сохранены в журнале.")
            traceback.print_exc()
        finally:
            self.finished.emit()
