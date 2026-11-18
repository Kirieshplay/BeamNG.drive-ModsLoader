from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.engine import TransferMeta, TransferProgress, TransferResult
from ui import theme
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BeamNGMods")
    app.setOrganizationName("BeamNGMods")
    assets = ROOT / "assets"
    theme.load_fonts(assets)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.GLOBAL_STYLE.replace("'Cascadia Mono'", f"'{theme.MONO_FAMILY}'"))
    window = MainWindow(assets)
    window.resize(1200, 860)
    window.show()
    QTest.qWait(1200)
    target = Path(os.environ.get("TEMP", "."))
    window.transfer.begin_transfer(
        TransferMeta(
            "Pack Good Mods for BeamNG Drive.zip",
            "MODSFIRE",
            3_060_169_449,
            Path("C:/Users/User/Documents/BeamNG.drive/mods/Pack Good Mods for BeamNG Drive.zip"),
        )
    )
    window.transfer.update_progress(
        TransferProgress(
            downloaded=1_234_567_890,
            total=3_060_169_449,
            speed=12_400_000.0,
            eta=147.0,
            percent=40.3,
        )
    )
    window.terminal.set_live(True)
    window.terminal.append("NET", "источник MODSFIRE · проверка ссылки")
    window.terminal.append("FILE", "Pack Good Mods for BeamNG Drive.zip · 2.85 GB · MODSFIRE")
    window.terminal.append("NET", "поток открыт · сервер поддерживает докачку")
    QTest.qWait(2400)
    window.grab().save(str(target / "beamng_state_active.png"))
    window.transfer.finish_success(
        TransferResult(
            Path("C:/Users/User/Documents/BeamNG.drive/mods/Pack Good Mods for BeamNG Drive.zip"),
            "Pack Good Mods for BeamNG Drive.zip",
            3_060_169_449,
            "MODSFIRE",
        )
    )
    window.terminal.set_live(False)
    window.terminal.append("OK", "готово · 2.85 GB · файл записан")
    window.terminal.append("SYS", "C:/Users/User/Documents/BeamNG.drive/mods/Pack Good Mods for BeamNG Drive.zip")
    window.terminal.append("END", "файл готов · мод можно подключать в игре")
    window.source_bar.shell.editor.clear()
    window.source_bar.set_busy(False)
    QTest.qWait(2600)
    window.grab().save(str(target / "beamng_state_success.png"))
    window.transfer.finish_error(
        "Недостаточно свободного места: нужно 2.85 GB. Освободите место и повторите."
    )
    window.terminal.append("ERR", "Недостаточно свободного места: нужно 2.85 GB. Освободите место и повторите.")
    QTest.qWait(1200)
    window.grab().save(str(target / "beamng_state_error.png"))
    print(target / "beamng_state_active.png")
    print(target / "beamng_state_success.png")
    print(target / "beamng_state_error.png")
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
