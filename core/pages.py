from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from core.resolvers import (
    ARCHIVE_SUFFIXES,
    CHALLENGE_MARKERS,
    UNSUPPORTED_HOSTS,
    DownloadCancelled,
    host_of,
    service_label,
)
from core.utils import normalize_url

MAX_PAGE_BYTES = 6 * 1024 * 1024
LISTING_PATH = re.compile(
    r"/(?:page|pages|category|categories|tag|tags|mods?|files?|catalog)/",
    re.IGNORECASE,
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class FeedError(Exception):
    pass


class NotAFeedError(FeedError):
    pass


@dataclass(slots=True)
class FeedItem:
    title: str
    url: str
    version: str = ""
    image: str = ""


@dataclass(slots=True)
class FeedPage:
    url: str
    title: str
    items: list[FeedItem]


def is_listing_url(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    host = (parsed.hostname or "").lower().strip(".")
    path = (parsed.path or "/").lower()
    if not host or parsed.scheme.lower() not in {"http", "https"}:
        return False
    if service_label(value) is not None or host in UNSUPPORTED_HOSTS:
        return False
    if host.startswith(("download.", "dl.")):
        return False
    if path.endswith(tuple(ARCHIVE_SUFFIXES)) or path.endswith((".html", ".htm")):
        return False
    if host == "beamnghub.ru" or host.endswith(".beamnghub.ru"):
        return True
    if LISTING_PATH.search(path):
        return True
    if (host.startswith(("mod", "beamng")) or "mod" in host) and (
        path == "/" or path.endswith("/")
    ):
        return True
    return False


def page_path(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    path = unquote(parsed.path or "/")
    if parsed.query:
        path += "?" + parsed.query
    return path


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _challenge(payload: bytes) -> bool:
    folded = payload[:200000].decode("utf-8", errors="ignore").lower()
    return any(marker in folded for marker in CHALLENGE_MARKERS)


def _decode_title(soup: BeautifulSoup) -> str:
    if soup.title is None:
        return ""
    title = _clean_text(soup.title.get_text(" ", strip=True))
    title = re.sub(r"\s*[-–-|»]\s*BeamNGhub.*$", "", title, flags=re.IGNORECASE)
    return title


def _item_from(article, page_url: str, page_host: str) -> FeedItem | None:
    title_link = article.select_one(
        "h2.short__title a[href], h3.short__title a[href], h1.short__title a[href]"
    )
    if title_link is None:
        title_link = article.select_one(".short__title a[href]")
    if title_link is None:
        heading = article.find(["h1", "h2", "h3", "h4"])
        if heading is not None:
            title_link = heading.find("a", href=True)
    image_link = article.select_one("a.short__img[href]")
    anchor = title_link or image_link or article.find("a", href=True)
    if anchor is None:
        return None
    href = str(anchor.get("href", "")).strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "data:")):
        return None
    absolute = urljoin(page_url, href)
    parsed = urlsplit(absolute)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if host_of(absolute) != page_host:
        return None
    if absolute.rstrip("/") == page_url.rstrip("/"):
        return None
    title = _clean_text(title_link.get_text(" ", strip=True)) if title_link else ""
    if not title:
        image = article.find("img")
        alt = _clean_text(str(image.get("alt", ""))) if image is not None else ""
        title = alt or unquote(parsed.path.rsplit("/", 1)[-1])
    title = title.strip(" -–-")
    if not title:
        return None
    version = ""
    version_node = article.select_one(".short_meta_vers div, .short_meta_vers")
    if version_node is not None:
        version = _clean_text(version_node.get_text(" ", strip=True))
        if len(version) > 24:
            version = version[:23] + "..."
    image_url = ""
    image = article.select_one(".short__img img[src], img[src]")
    if image is not None:
        raw_image = str(image.get("src", "")).strip()
        if raw_image and not raw_image.startswith("data:"):
            candidate = urljoin(page_url, raw_image)
            if urlsplit(candidate).scheme.lower() in {"http", "https"}:
                image_url = candidate
    return FeedItem(title=title, url=absolute, version=version, image=image_url)


def parse_feed(page_url: str, payload: bytes | str) -> FeedPage:
    soup = BeautifulSoup(payload, "html.parser")
    page_host = host_of(page_url)
    containers = soup.select("#content-block article.short, main article.short, article.short")
    specific = bool(containers)
    if not containers:
        containers = soup.select("#content-block article, main article, article")
    items: list[FeedItem] = []
    seen: set[str] = set()
    for article in containers:
        item = _item_from(article, page_url, page_host)
        if item is None:
            continue
        key = item.url.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    if not items:
        raise FeedError("На странице не найдены моды.")
    if not specific and len(items) < 2:
        raise FeedError("Страница не похожа на список модов.")
    return FeedPage(url=page_url, title=_decode_title(soup), items=items)


def fetch_feed(
    value: str,
    cancel: Callable[[], bool] | None = None,
) -> FeedPage:
    url = normalize_url(value)
    cancelled = cancel or (lambda: False)

    def check_cancel() -> None:
        if cancelled():
            raise DownloadCancelled()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
    )
    check_cancel()
    try:
        response = session.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=(15, 30),
        )
    except requests.Timeout as error:
        raise FeedError("Страница не ответила вовремя. Повторите попытку.") from error
    except requests.SSLError as error:
        raise FeedError("Ошибка SSL-сертификата сайта.") from error
    except requests.ConnectionError as error:
        raise FeedError("Не удалось подключиться к сайту. Проверьте интернет.") from error
    except requests.RequestException as error:
        raise FeedError(f"Ошибка запроса: {error.__class__.__name__}.") from error
    try:
        status = response.status_code
        if status >= 400:
            if status == 404:
                raise FeedError("Страница не найдена: сервер вернул 404.")
            if status in {401, 403}:
                raise FeedError("Сайт закрыл доступ к странице.")
            if status == 429:
                raise FeedError("Сайт временно ограничил запросы.")
            raise FeedError(f"Страница вернула ошибку HTTP {status}.")
        content_type = response.headers.get("content-type", "").lower()
        if content_type and not any(
            token in content_type
            for token in (
                "text/html",
                "application/xhtml",
                "text/plain",
                "application/xml",
                "text/xml",
                "application/json",
            )
        ):
            raise NotAFeedError()
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
            raise NotAFeedError()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(65536):
            check_cancel()
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_PAGE_BYTES:
                raise NotAFeedError()
            chunks.append(chunk)
        payload = b"".join(chunks)
    finally:
        response.close()
    check_cancel()
    if _challenge(payload):
        raise FeedError("Сайт требует проверку браузера. Откройте страницу в браузере.")
    return parse_feed(response.url, payload)
