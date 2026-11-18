from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = ROOT / "requirements.txt"
MODULES = ("PySide6", "requests", "bs4", "soupsieve")
PACKAGES = ("PySide6>=6.6", "requests>=2.31", "beautifulsoup4>=4.12")


def _log(message: str) -> None:
    if sys.stdout is not None:
        print(f"[deps] {message}", flush=True)


def missing() -> list[str]:
    return [name for name in MODULES if importlib.util.find_spec(name) is None]


def _call(command: list[str], interactive: bool) -> int:
    kwargs: dict[str, object] = {}
    if sys.platform == "win32" and interactive and sys.stdout is None:
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    try:
        return subprocess.call(command, **kwargs)
    except OSError as error:
        _log(f"не удалось запустить pip: {error}")
        return 1


def _probe(command: list[str]) -> int:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
        ).returncode
    except OSError:
        return 1


def ensure_dependencies() -> bool:
    absent = missing()
    if not absent:
        return True
    _log("не найдены: " + ", ".join(absent))
    if _probe([sys.executable, "-m", "pip", "--version"]) != 0:
        _log("pip недоступен, включаю ensurepip")
        _call([sys.executable, "-m", "ensurepip", "--upgrade"], interactive=False)
    if REQUIREMENTS.is_file():
        target = ["-r", str(REQUIREMENTS)]
    else:
        target = list(PACKAGES)
    code = _call(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *target,
        ],
        interactive=True,
    )
    if code != 0:
        _log(f"pip завершился с кодом {code}")
        return False
    importlib.invalidate_caches()
    still = missing()
    if still:
        _log("после установки не найдены: " + ", ".join(still))
        return False
    _log("зависимости готовы")
    return True


def launch() -> int:
    python = Path(sys.executable)
    windowed = python.with_name("pythonw.exe")
    target = windowed if windowed.exists() else python
    subprocess.Popen([str(target), str(ROOT / "main.py")], cwd=str(ROOT))
    return 0


def main() -> int:
    if not ensure_dependencies():
        _log("установка не удалась, запуск отменён")
        return 1
    if "--install" in sys.argv:
        return 0
    return launch()


if __name__ == "__main__":
    raise SystemExit(main())
