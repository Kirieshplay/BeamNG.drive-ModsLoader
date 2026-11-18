from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui import theme
from ui.splash import SplashScreen


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BeamNGModsSplash")
    assets = ROOT / "assets"
    theme.load_fonts(assets)
    app.setStyle("Fusion")
    screen = SplashScreen()
    screen.show()
    target = Path(os.environ.get("TEMP", "."))
    QTest.qWait(320)
    screen.grab().save(str(target / "beamng_splash_fall.png"))
    QTest.qWait(1500)
    screen.grab().save(str(target / "beamng_splash_settled.png"))
    screen.finish_now()
    QTest.qWait(420)
    app.processEvents()
    print(target / "beamng_splash_fall.png")
    print(target / "beamng_splash_settled.png")
    print("finished:", screen._finished, "visible:", screen.isVisible())
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
