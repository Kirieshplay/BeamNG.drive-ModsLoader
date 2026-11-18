from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

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
    window.resize(int(os.environ.get("CAPTURE_WIDTH", "1200")), int(os.environ.get("CAPTURE_HEIGHT", "860")))
    window.show()

    target = Path(os.environ.get("TEMP", ".")) / os.environ.get("CAPTURE_NAME", "beamng_ui_capture.png")

    def capture() -> None:
        window.grab().save(str(target))
        print(target)
        app.quit()

    QTimer.singleShot(3200, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
