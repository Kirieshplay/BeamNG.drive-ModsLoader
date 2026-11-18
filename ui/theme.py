from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = QColor("#000000")
SURFACE = QColor("#000000")
SURFACE_RAISED = QColor("#0a0a0a")
SURFACE_HOVER = QColor("#121212")
BORDER = QColor("#1b1b1b")
BORDER_STRONG = QColor("#333333")
TEXT = QColor("#e2e2e2")
TEXT_SOFT = QColor("#bdbdbd")
MUTED = QColor("#8a8a8a")
FAINT = QColor("#555555")
ORANGE = QColor("#ff8c1a")
ORANGE_HOVER = QColor("#ffa54d")
ORANGE_DIM = QColor("#4a2408")
GREEN = QColor("#9be49b")
RED = QColor("#ff5f56")
AMBER = QColor("#ffb454")
FIELD = QColor("#121212")
FIELD_FOCUS = QColor("#1b1b1b")
FIELD_ERROR = QColor("#241111")
ACCENT_FOLDER = QColor("#79b8d1")
ACCENT_LOG = QColor("#9be49b")

MONO_FAMILY = "Cascadia Mono"
PIXEL_FAMILY = "Handjet"
PIXEL_SCALE = 1.3
PIXEL_WEIGHT_BOOST = 100
FONT_SCALE = 1.0
WEIGHT_BOOST = 0
_loaded = False


def load_fonts(asset_root: Path) -> None:
    global MONO_FAMILY, FONT_SCALE, WEIGHT_BOOST, _loaded
    if _loaded:
        return
    font_dir = asset_root / "fonts"
    preferred = []
    if font_dir.is_dir():
        for path in sorted(font_dir.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                preferred.extend(QFontDatabase.applicationFontFamilies(font_id))
    families = QFontDatabase.families()
    if PIXEL_FAMILY in preferred or PIXEL_FAMILY in families:
        MONO_FAMILY = PIXEL_FAMILY
        FONT_SCALE = PIXEL_SCALE
        WEIGHT_BOOST = PIXEL_WEIGHT_BOOST
        _loaded = True
        return
    if "Cascadia Mono" in preferred:
        MONO_FAMILY = "Cascadia Mono"
    elif "Cascadia Mono" in families:
        MONO_FAMILY = "Cascadia Mono"
    elif "Cascadia Code" in families:
        MONO_FAMILY = "Cascadia Code"
    elif "Consolas" in families:
        MONO_FAMILY = "Consolas"
    else:
        MONO_FAMILY = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    _loaded = True


def mono_font(
    size: float,
    weight: int = 400,
    letter_spacing: float = 0.0,
    italic: bool = False,
) -> QFont:
    font = QFont(MONO_FAMILY)
    font.setPointSizeF(size * FONT_SCALE)
    font.setWeight(QFont.Weight(min(900, weight + WEIGHT_BOOST)))
    font.setItalic(italic)
    if letter_spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_spacing)
    return font


GLOBAL_STYLE = """
QWidget {
    color: #e2e2e2;
    font-family: 'Cascadia Mono';
    font-size: 15px;
    outline: none;
}
QMainWindow, QDialog {
    background: #000000;
}
QLineEdit, QPlainTextEdit {
    background: transparent;
    border: 0;
    padding: 0;
    color: #ffffff;
    selection-background-color: #ff8c1a;
    selection-color: #000000;
    font-family: 'Cascadia Mono';
    font-size: 16px;
}
QPlainTextEdit > QWidget {
    background: transparent;
}
QScrollArea {
    background: transparent;
    border: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 6px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #2b2b2b;
    min-width: 24px;
    border-radius: 0;
}
QScrollBar::handle:horizontal:hover {
    background: #4a4a4a;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2b2b2b;
    min-height: 24px;
    border-radius: 0;
}
QScrollBar::handle:vertical:hover {
    background: #4a4a4a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QMenu {
    background: #0a0a0a;
    border: 1px solid #2b2b2b;
    padding: 4px;
    font-family: 'Cascadia Mono';
    font-size: 13px;
}
QMenu::item {
    padding: 6px 24px 6px 10px;
    color: #c7c7c7;
}
QMenu::item:selected {
    background: #1a1a1a;
    color: #ff8c1a;
}
"""
