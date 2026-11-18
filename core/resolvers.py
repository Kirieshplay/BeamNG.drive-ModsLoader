from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from pathlib import Path
from typing import Callable
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

import requests
from bs4 import BeautifulSoup

from core.utils import normalize_url, sanitize_filename


class TransferError(Exception):
    pass


class UnsupportedHostError(TransferError):
    pass


class DownloadCancelled(Exception):
    pass


@dataclass(slots=True)
class PreparedFile:
    response: requests.Response
    url: str
    filename: str
    total: int | None
    host: str
    referer: str | None
    content_type: str
    etag: str | None
    last_modified: str | None


LogCallback = Callable[[str, str], None]
CancelCallback = Callable[[], bool]

SERVICE_HOSTS = (
    ("modsfire.com", "MODSFIRE"),
    ("mediafire.com", "MEDIAFIRE"),
    ("drive.google.com", "GOOGLE DRIVE"),
    ("drive.usercontent.google.com", "GOOGLE DRIVE"),
    ("docs.google.com", "GOOGLE DRIVE"),
    ("dropbox.com", "DROPBOX"),
    ("dropboxusercontent.com", "DROPBOX"),
    ("pixeldrain.com", "PIXELDRAIN"),
    ("disk.yandex.ru", "ЯНДЕКС ДИСК"),
    ("disk.yandex.com", "ЯНДЕКС ДИСК"),
    ("disk.yandex.by", "ЯНДЕКС ДИСК"),
    ("disk.yandex.kz", "ЯНДЕКС ДИСК"),
    ("disk.yandex.ua", "ЯНДЕКС ДИСК"),
    ("yadi.sk", "ЯНДЕКС ДИСК"),
    ("disk.360.yandex.ru", "ЯНДЕКС ДИСК"),
)

UNSUPPORTED_HOSTS = {
    "mega.nz": "MEGA шифрует файлы. Используйте официальный MEGAsync или другое зеркало.",
    "mega.io": "MEGA шифрует файлы. Используйте официальный MEGAsync или другое зеркало.",
    "sharemods.com": "ShareMods запрашивает капчу. Автоматическое скачивание этого зеркала недоступно.",
    "1fichier.com": "1fichier ограничивает прямые загрузки и запрашивает ожидание.",
    "rapidgator.net": "Rapidgator требует авторизацию или ожидание.",
    "turbobit.net": "Turbobit требует авторизацию или ожидание.",
    "nitroflare.com": "Nitroflare требует авторизацию.",
    "katfile.com": "Katfile требует ожидание и капчу.",
    "ddownload.com": "DDownload требует ожидание и капчу.",
}

ARCHIVE_SUFFIXES = {
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".mod",
    ".beamng",
}

MIME_SUFFIXES = {
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/vnd.rar": ".rar",
    "application/x-7z-compressed": ".7z",
}

CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "cf_chl_opt",
    "enable javascript and cookies to continue",
    "attention required",
    "checking your browser before accessing",
    "ddos protection by",
    "verify you are human",
    "wrong captcha",
)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def service_label(url: str) -> str | None:
    host = host_of(url)
    for suffix, label in SERVICE_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return label
    return None


def display_host(url: str) -> str:
    label = service_label(url)
    if label:
        return label
    host = host_of(url)
    return host.removeprefix("www.").upper() if host else "DIRECT"


def _is_page(response: requests.Response) -> bool:
    disposition = response.headers.get("content-disposition", "").lower()
    if "attachment" in disposition:
        return False
    content_type = response.headers.get("content-type", "").lower()
    return (
        content_type.startswith("text/html")
        or content_type.startswith("application/xhtml")
        or content_type.startswith("application/json")
        or content_type.startswith("application/xml")
        or content_type.startswith("text/")
    )


def _is_challenge(text: str) -> bool:
    folded = text[:200000].lower()
    return any(marker in folded for marker in CHALLENGE_MARKERS)


def _extract_filename(response: requests.Response) -> str:
    disposition = response.headers.get("content-disposition", "")
    if disposition:
        message = Message()
        message["content-disposition"] = disposition
        try:
            name = message.get_filename()
        except Exception:
            name = None
        if name:
            name = unquote(name)
            cleaned = sanitize_filename(name, "")
            if cleaned:
                return cleaned
    path = unquote(urlsplit(response.url).path)
    if path and not path.endswith("/"):
        candidate = sanitize_filename(path, "")
        if candidate and "." in candidate:
            return candidate
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    suffix = MIME_SUFFIXES.get(content_type, ".zip")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"BeamNG_mod_{stamp}{suffix}"


def _content_length(response: requests.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw:
        try:
            value = int(raw)
            return value if value >= 0 else None
        except ValueError:
            pass
    raw_range = response.headers.get("content-range", "")
    match = re.search(r"/(\d+)\s*$", raw_range)
    if match:
        return int(match.group(1))
    return None


class DownloadPreparer:
    def __init__(
        self,
        on_log: LogCallback | None = None,
        cancel: CancelCallback | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self._log_callback = on_log or (lambda level, message: None)
        self._cancel_callback = cancel or (lambda: False)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                "Accept-Encoding": "identity",
                "Connection": "keep-alive",
            }
        )

    def _log(self, level: str, message: str) -> None:
        self._log_callback(level, message)

    def _check_cancel(self) -> None:
        if self._cancel_callback():
            raise DownloadCancelled()

    def prepare(self, raw_url: str) -> PreparedFile:
        url = normalize_url(raw_url)
        original_host = host_of(url)
        for blocked_host, reason in UNSUPPORTED_HOSTS.items():
            if original_host == blocked_host or original_host.endswith("." + blocked_host):
                raise UnsupportedHostError(reason)
        if original_host.endswith("modsfire.com") and "/modpacks/" in urlsplit(url).path:
            raise TransferError("Ссылка ведёт на модпак из нескольких файлов. Выберите отдельный файл на ModsFire.")
        label = display_host(url)
        self._log("NET", f"источник {label} | проверка ссылки")
        target = url
        hint = label
        direct_prepared = self._prepare_service_url(url)
        if direct_prepared is not None:
            target, hint = direct_prepared
        return self._follow(target, hint)

    def _prepare_service_url(self, url: str) -> tuple[str, str] | None:
        host = host_of(url)
        path = urlsplit(url).path
        if host.endswith("drive.google.com") or host.endswith("docs.google.com"):
            if "/folders/" in path:
                raise TransferError("Ссылка ведёт на папку Google Drive. Нужен файл.")
            match = re.search(r"/file/d/([A-Za-z0-9_-]{10,})", path)
            if not match:
                query_id = dict(parse_qsl(urlsplit(url).query)).get("id")
                if query_id:
                    match_id = query_id
                else:
                    raise TransferError("Не удалось определить файл Google Drive.")
            else:
                match_id = match.group(1)
            direct = (
                "https://drive.usercontent.google.com/download?"
                + urlencode({"id": match_id, "export": "download", "confirm": "t"})
            )
            self._log("HOST", "Google Drive | используется прямая выдача")
            return direct, "GOOGLE DRIVE"
        if host.endswith("pixeldrain.com"):
            parts = [part for part in path.split("/") if part]
            if parts and parts[0] == "l":
                raise TransferError("Ссылка ведёт на список Pixeldrain. Нужен отдельный файл.")
            if parts and parts[0] == "u" and len(parts) >= 2:
                direct = f"https://pixeldrain.com/api/file/{quote(parts[1])}?download"
                return direct, "PIXELDRAIN"
            if parts and parts[0] == "api" and len(parts) >= 3 and parts[1] == "file":
                return url, "PIXELDRAIN"
        if host.endswith("dropbox.com") or host.endswith("dropboxusercontent.com"):
            parsed = urlsplit(url)
            query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "dl"]
            query.append(("dl", "1"))
            direct = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
            return direct, "DROPBOX"
        if host.endswith("mediafire.com"):
            if host.startswith("download") and path not in {"", "/"}:
                return url, "MEDIAFIRE"
            return url, "MEDIAFIRE"
        yandex_hosts = ("yadi.sk", "disk.yandex.ru", "disk.yandex.com", "disk.yandex.by", "disk.yandex.kz", "disk.yandex.ua")
        if any(host == item or host.endswith("." + item) for item in yandex_hosts):
            self._check_cancel()
            self._log("HOST", "Яндекс Диск | запрос прямой ссылки")
            try:
                response = self.session.get(
                    "https://cloud-api.yandex.net/v1/disk/public/resources/download",
                    params={"public_key": url},
                    timeout=(20, 45),
                )
            except requests.RequestException as error:
                raise TransferError("Нет связи с API Яндекс Диска.") from error
            self._check_cancel()
            if response.status_code != 200:
                raise TransferError("Яндекс Диск не выдал файл. Проверьте доступ к ссылке.")
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError) as error:
                raise TransferError("Яндекс Диск вернул неожиданный ответ.") from error
            direct = payload.get("href")
            if not direct:
                raise TransferError("Яндекс Диск не вернул адрес файла.")
            return direct, "ЯНДЕКС ДИСК"
        if host == "modsfire.com" or host.endswith(".modsfire.com"):
            return url, "MODSFIRE"
        return None

    def _follow(self, start_url: str, initial_hint: str) -> PreparedFile:
        current_url = start_url
        referer: str | None = None
        hint = initial_hint
        seen: set[str] = set()
        for step in range(7):
            self._check_cancel()
            if current_url in seen:
                raise TransferError("Обнаружен цикл перенаправлений. Проверьте ссылку.")
            seen.add(current_url)
            response = self._open(current_url, referer)
            self._check_cancel()
            if not _is_page(response):
                prepared = self._build_prepared(response, hint, referer)
                self._log("FILE", f"файл {prepared.filename}")
                return prepared
            self._log("NET", f"разбор страницы | шаг {step + 1}")
            try:
                text = response.text
                page_url = response.url
            finally:
                response.close()
            if _is_challenge(text):
                raise TransferError("Сайт требует проверку браузера. Автоматическое скачивание остановлено.")
            next_url = self._extract_next_link(page_url, text, hint)
            if not next_url:
                raise TransferError(self._missing_link_message(page_url, text, hint))
            next_url = urljoin(page_url, next_url)
            next_scheme = urlsplit(next_url).scheme.lower()
            if next_scheme not in {"http", "https"}:
                raise TransferError("Сайт предложил неподдерживаемый тип ссылки.")
            detected = service_label(next_url)
            if detected:
                hint = detected
            elif service_label(page_url) is None and from_file_extension(next_url):
                hint = display_host(page_url)
            else:
                hint = display_host(next_url)
            referer = page_url
            current_url = next_url
            self._log("HOST", f"найден источник | {hint}")
        raise TransferError("Слишком много промежуточных страниц. Не удалось добраться до файла.")

    def _open(self, url: str, referer: str | None) -> requests.Response:
        headers: dict[str, str] = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self.session.get(
                url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(20, 30),
            )
        except requests.Timeout as error:
            raise TransferError("Сервер не ответил вовремя. Повторите попытку.") from error
        except requests.SSLError as error:
            raise TransferError("Ошибка SSL-сертификата сайта.") from error
        except requests.ConnectionError as error:
            raise TransferError("Не удалось подключиться к серверу. Проверьте интернет.") from error
        except requests.RequestException as error:
            raise TransferError(f"Ошибка сетевого запроса: {error.__class__.__name__}.") from error
        if response.status_code >= 400:
            status = response.status_code
            response.close()
            if status == 404:
                raise TransferError("Файл не найден: сервер вернул 404.")
            if status in {401, 403}:
                raise TransferError("Доступ запрещён. Возможно, ссылка устарела или закрыта.")
            if status == 429:
                raise TransferError("Сервер временно ограничил запросы. Повторите позже.")
            if status >= 500:
                raise TransferError(f"Сервер временно недоступен (HTTP {status}).")
            raise TransferError(f"Сервер вернул ошибку HTTP {status}.")
        return response

    def _extract_next_link(self, page_url: str, text: str, hint: str) -> str | None:
        soup = BeautifulSoup(text, "html.parser")
        host = host_of(page_url)
        if host == "beamnghub.ru" or host.endswith(".beamnghub.ru"):
            for selector in ("a#secondBlock[href]", "a.btn_download[href]"):
                button = soup.select_one(selector)
                if button is not None:
                    href = str(button.get("href", "")).strip()
                    if href and not href.startswith("#"):
                        return href
        if hint == "MODSFIRE" or host.endswith("modsfire.com"):
            candidate = self._extract_modsfire(soup)
            if candidate:
                return candidate
        if hint == "MEDIAFIRE" or host.endswith("mediafire.com"):
            candidate = self._extract_mediafire(soup)
            if candidate:
                return candidate
        if hint == "GOOGLE DRIVE" or host.endswith("google.com"):
            candidate = self._extract_google_drive(soup)
            if candidate:
                return candidate
        refresh = soup.find("meta", attrs={"http-equiv": re.compile("^refresh$", re.I)})
        if refresh:
            content = refresh.get("content", "")
            match = re.search(r"url\s*=\s*['\"]?([^'\";]+)", content, re.I)
            if match:
                return match.group(1).strip()
        candidates: list[tuple[int, str]] = []
        seen_links: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            raw_href = str(anchor.get("href", "")).strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "data:")):
                continue
            absolute = urljoin(page_url, raw_href)
            if absolute in seen_links:
                continue
            seen_links.add(absolute)
            if urlsplit(absolute).scheme.lower() not in {"http", "https"}:
                continue
            target_host = host_of(absolute)
            if not target_host:
                continue
            anchor_text = " ".join(anchor.get_text(" ", strip=True).lower().split())
            classes = " ".join(anchor.get("class", [])).lower()
            anchor_id = str(anchor.get("id", "")).lower()
            has_download_attr = anchor.has_attr("download")
            suffix = Path(urlsplit(absolute).path).suffix.lower()
            known_other = service_label(absolute) is not None and target_host != host
            score = 0
            if known_other:
                score += 110
            if target_host.startswith("download.") or target_host.startswith("dl."):
                score += 100
            if suffix in ARCHIVE_SUFFIXES:
                score += 90
            if has_download_attr:
                score += 80
            if "download" in classes or "download" in anchor_id:
                score += 55
            if "download" in anchor_text or "скачать" in anchor_text:
                score += 45
            if any(word in anchor_text for word in ("login", "register", "premium", "how to download", "инструкция")):
                score -= 120
            if any(part in urlsplit(absolute).path.lower() for part in ("/login", "/register", "/premium", "/pages/")):
                score -= 100
            if score >= 45:
                candidates.append((score, absolute))
        for script in soup.find_all("script"):
            script_text = script.string or ""
            for match in re.finditer(r"https?://[^\s\"'<>\\]+", script_text):
                candidate = match.group(0).rstrip("),;")
                if service_label(candidate) and host_of(candidate) != host:
                    candidates.append((70, candidate))
                elif Path(urlsplit(candidate).path).suffix.lower() in ARCHIVE_SUFFIXES:
                    candidates.append((65, candidate))
        for element in soup.find_all(attrs={"data-href": True}):
            candidate = urljoin(page_url, str(element.get("data-href")))
            if urlsplit(candidate).scheme.lower() in {"http", "https"}:
                candidates.append((40, candidate))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            selected = candidates[0][1]
            if selected != page_url:
                return selected
        lower = soup.get_text(" ", strip=True).lower()
        if any(marker in lower for marker in ("file not found", "file was removed", "file has been removed", "ссылка не найдена")):
            return None
        return None

    def _extract_modsfire(self, soup: BeautifulSoup) -> str | None:
        selectors = (
            "a#downloadnow[href]",
            "a.download-button[href]",
            "a[href*='/d/']",
        )
        for selector in selectors:
            anchor = soup.select_one(selector)
            if anchor and anchor.get("href"):
                href = str(anchor.get("href")).strip()
                if href and not href.startswith("#"):
                    return href
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href"))
            if re.search(r"^https?://modsfire\.com/d/", href):
                return href
        return None

    def _extract_mediafire(self, soup: BeautifulSoup) -> str | None:
        anchor = soup.select_one("a#downloadButton[href]")
        if anchor:
            return str(anchor.get("href"))
        for selector in ("a.input.popsok[href]", ".download_link a[href]", "#download_link a[href]"):
            anchor = soup.select_one(selector)
            if anchor:
                href = str(anchor.get("href"))
                if "mediafire.com" in href:
                    return href
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href"))
            target_host = host_of(href)
            if target_host.startswith("download") and target_host.endswith("mediafire.com"):
                return href
        return None

    def _extract_google_drive(self, soup: BeautifulSoup) -> str | None:
        form = soup.select_one("form#download-form")
        if form:
            action = str(form.get("action") or "https://drive.usercontent.google.com/download")
            payload: list[tuple[str, str]] = []
            for field in form.find_all("input"):
                name = field.get("name")
                if name:
                    payload.append((str(name), str(field.get("value", ""))))
            if payload:
                return action + "?" + urlencode(payload)
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href"))
            if "drive.usercontent.google.com/download" in href or "/uc?export=download" in href:
                return href
        return None

    def _missing_link_message(self, page_url: str, text: str, hint: str) -> str:
        folded = text.lower()
        host = host_of(page_url)
        if hint == "MODSFIRE" or host.endswith("modsfire.com"):
            return "ModsFire не выдал прямую ссылку. Файл удалён или ссылка устарела."
        if hint == "MEDIAFIRE" or host.endswith("mediafire.com"):
            if "dangerous" in folded or "scan" in folded:
                return "MediaFire требует подтверждение проверки файла. Скачивание остановлено."
            return "MediaFire не выдал файл. Он удалён или доступ ограничен."
        if hint == "GOOGLE DRIVE":
            if "quota" in folded or "too many users" in folded:
                return "Google Drive временно ограничил скачивание этого файла."
            return "Google Drive не выдал файл. Проверьте доступ по ссылке."
        if "not found" in folded or "removed" in folded or "удален" in folded or "удалён" in folded:
            return "Файл не найден или был удалён."
        return "На странице не найдена прямая ссылка на файл. Возможно, нужен вход или файл удалён."

    def _build_prepared(
        self,
        response: requests.Response,
        hint: str,
        referer: str | None,
    ) -> PreparedFile:
        filename = _extract_filename(response)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not Path(filename).suffix and content_type in MIME_SUFFIXES:
            filename += MIME_SUFFIXES[content_type]
        total = _content_length(response)
        if total is not None and total <= 0:
            total = None
        label = hint if hint else display_host(response.url)
        return PreparedFile(
            response=response,
            url=response.url,
            filename=filename,
            total=total,
            host=label,
            referer=referer,
            content_type=content_type,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )


def from_file_extension(url: str) -> bool:
    return Path(unquote(urlsplit(url).path)).suffix.lower() in ARCHIVE_SUFFIXES


def parse_direct_response(response: requests.Response) -> PreparedFile:
    host = display_host(response.url)
    return PreparedFile(
        response=response,
        url=response.url,
        filename=_extract_filename(response),
        total=_content_length(response),
        host=host,
        referer=None,
        content_type=response.headers.get("content-type", ""),
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )
