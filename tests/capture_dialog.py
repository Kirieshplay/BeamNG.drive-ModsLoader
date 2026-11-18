from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui import theme
from ui.main_window import CloseDialog, MainWindow


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
    QTest.qWait(600)
    dialog = CloseDialog(window)
    dialog.move(
        window.mapToGlobal(
            QPoint((window.width() - dialog.width()) // 2, (window.height() - dialog.height()) // 2)
        )
    )
    dialog.show()
    QTest.qWait(500)
    target = Path(os.environ.get("TEMP", ".")) / "beamng_close_dialog.png"
    dialog.grab().save(str(target))
    print(target)
    dialog.close()
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
