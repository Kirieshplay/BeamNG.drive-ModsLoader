from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def _quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def _make(link: Path, target: Path, entry: Path, root: Path, icon: Path) -> bool:
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut('{_quote(link)}'); "
        f"$shortcut.TargetPath = '{_quote(target)}'; "
        f"$shortcut.Arguments = '\"{_quote(entry)}\"'; "
        f"$shortcut.WorkingDirectory = '{_quote(root)}'; "
        f"$shortcut.IconLocation = '{_quote(icon)}'; "
        "$shortcut.Description = 'BeamNG.drive MODS'; "
        "$shortcut.WindowStyle = 1; "
        "$shortcut.Save()"
    )
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or result.stdout.strip())
    return link.exists()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    entry = root / "main.py"
    icon = root / "assets" / "icon.ico"
    python = Path(sys.executable)
    windowed = python.with_name("pythonw.exe")
    target = windowed if windowed.exists() else python
    desktop = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    )
    if not desktop.is_dir():
        print("папка рабочего стола не найдена")
        return 1
    link = desktop / "BeamNG.drive.lnk"
    if not _make(link, target, entry, root, icon):
        print("не удалось создать ярлык")
        return 1
    print(f"ярлык готов | {link}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
