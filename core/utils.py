from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import QStandardPaths

UNITS = ("B", "KB", "MB", "GB", "TB", "PB")
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def human_bytes(value: int | float | None, precision: int = 2) -> str:
    if value is None:
        return "--"
    number = float(value)
    if number < 1024:
        return f"{int(number)} B"
    unit_index = 0
    while number >= 1024 and unit_index < len(UNITS) - 1:
        number /= 1024
        unit_index += 1
    if number >= 100:
        digits = 0
    elif number >= 10:
        digits = 1
    else:
        digits = precision
    rendered = f"{number:.{digits}f}"
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return f"{rendered} {UNITS[unit_index]}"


def human_speed(value: float | None) -> str:
    if value is None or value <= 0:
        return "0 B/s"
    number = float(value)
    unit_index = 0
    while number >= 1024 and unit_index < len(UNITS) - 1:
        number /= 1024
        unit_index += 1
    digits = 0 if number >= 100 else 1
    return f"{number:.{digits}f} {UNITS[unit_index]}/s"


def human_eta(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds != seconds:
        return "--:--"
    total = int(round(seconds))
    if total >= 3600:
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def normalize_url(value: str) -> str:
    candidate = value.strip().strip("\"'<>")
    if not candidate:
        raise ValueError("Ссылка не указана.")
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Поддерживаются только ссылки http и https.")
    if not parsed.hostname:
        raise ValueError("В ссылке отсутствует адрес сервера.")
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("Локальные адреса не поддерживаются.")
    if len(candidate) > 8192:
        raise ValueError("Слишком длинная ссылка.")
    return candidate


def is_probably_url(value: str) -> bool:
    text = value.strip()
    if not text or len(text) > 8192 or any(char.isspace() for char in text):
        return False
    try:
        parsed = urlsplit(text if "://" in text else "https://" + text)
    except ValueError:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)


URL_PATTERN = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
URL_TRAILING = ".,;:!?)]}>»”'\"`"


def extract_urls(value: str, limit: int | None = None) -> list[str]:
    if limit is not None and limit <= 0:
        return []
    found: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> bool:
        try:
            normalized = normalize_url(candidate)
        except ValueError:
            return False
        key = normalized.lower()
        if key in seen:
            return False
        seen.add(key)
        found.append(normalized)
        return True

    for line in (value or "").splitlines():
        matches = URL_PATTERN.findall(line)
        if matches:
            for match in matches:
                candidate = match.rstrip(URL_TRAILING)
                if candidate and add(candidate):
                    if limit is not None and len(found) >= limit:
                        return found
            continue
        token = line.strip().strip("\"'<>")
        if token and "." in token and not any(char.isspace() for char in token):
            if add(token) and limit is not None and len(found) >= limit:
                return found
    return found



def sanitize_filename(value: str, fallback: str = "BeamNG_mod.zip") -> str:
    name = unquote(value or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    stem = Path(name).stem.strip(" .")
    suffix = Path(name).suffix
    if stem.upper() in WINDOWS_RESERVED:
        stem = "_" + stem
    if len(stem) > 170:
        stem = stem[:170].rstrip(" .")
    if suffix and len(suffix) <= 16:
        name = stem + suffix
    else:
        name = stem
    return name or fallback


def unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / sanitize_filename(filename)
    if not candidate.exists() and not Path(str(candidate) + ".part").exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(2, 1000):
        alternative = directory / f"{stem} ({index}){suffix}"
        if not alternative.exists() and not Path(str(alternative) + ".part").exists():
            return alternative
    raise FileExistsError("Не удалось подобрать свободное имя файла.")


def resolve_destination() -> Path:
    documents = Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation))
    candidates: list[Path] = []
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "BeamNG.drive"
    for mods in (documents / "BeamNG.drive" / "mods", Path.home() / "Documents" / "BeamNG.drive" / "mods"):
        if mods.is_dir() and mods not in candidates:
            candidates.append(mods)
    if local.is_dir():
        version_dirs = [item for item in local.iterdir() if item.is_dir() and (item / "mods").is_dir()]
        version_dirs.sort(key=lambda item: _version_key(item.name), reverse=True)
        for item in version_dirs:
            if item / "mods" not in candidates:
                candidates.append(item / "mods")
        direct = local / "mods"
        if direct.is_dir() and direct not in candidates:
            candidates.append(direct)
    if candidates:
        return candidates[0]
    downloads = Path(QStandardPaths.writableLocation(QStandardPaths.DownloadLocation))
    return downloads / "BeamNG.drive MODS"


def _version_key(value: str) -> tuple:
    parts = re.split(r"[._-]", value)
    result: list[object] = []
    for part in parts:
        try:
            result.append((0, int(part)))
        except ValueError:
            result.append((1, part.lower()))
    return tuple(result)


def path_label(path: Path, limit: int = 92) -> str:
    raw = str(path)
    home = str(Path.home())
    if raw.lower().startswith(home.lower()):
        raw = "~" + raw[len(home):]
    if len(raw) <= limit:
        return raw
    keep = max(24, limit - 3)
    left = keep // 2
    right = keep - left
    return raw[:left].rstrip() + "..." + raw[-right:].lstrip()


def disk_free(path: Path) -> int | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise OSError("Целевой путь не является папкой.")
    probe = path / ".beamng_mods_write_test"
    try:
        probe.write_bytes(b"0")
        probe.unlink()
    except OSError as error:
        raise OSError("Нет прав на запись в выбранную папку.") from error


def reveal_in_explorer(path: Path) -> None:
    if not path.exists():
        return
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", f"/select,{os.path.normpath(str(path))}"])
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path.parent)])


def open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
