from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)

from ui import theme

WHEEL = (
    "    .----------------.    ",
    "  .'  .------------.  '.  ",
    " /   /              \\   \\ ",
    "|   |    .------.    |   |",
    "|   |   /        \\   |   |",
    "|   |  |   (  )   |  |   |",
    "|   |   \\        /   |   |",
    "|   |    '------'    |   |",
    " \\   \\              /   / ",
    "  '.  '------------'  .'  ",
    "    '----------------'    ",
)


def paint(painter: QPainter, width: int, height: int) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    background = QLinearGradient(0.0, 0.0, 0.0, float(height))
    background.setColorAt(0.0, QColor("#000000"))
    background.setColorAt(1.0, QColor("#0a0705"))
    painter.fillRect(QRectF(0, 0, width, height), background)

    glow = QRadialGradient(
        QPointF(width * 0.16, -40.0),
        max(340.0, width * 0.8),
    )
    center = QColor(theme.ORANGE)
    center.setAlphaF(0.09)
    edge = QColor(theme.ORANGE)
    edge.setAlphaF(0.0)
    glow.setColorAt(0.0, center)
    glow.setColorAt(1.0, edge)
    painter.fillRect(QRectF(0, 0, width, height), glow)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#101010"))
    for x in range(22, width - 10, 30):
        for y in range(96, height - 18, 30):
            painter.drawRect(QRectF(x, y, 1.0, 1.0))

    paint_wheel(painter, width, height)


def paint_wheel(painter: QPainter, width: int, height: int) -> None:
    font = theme.mono_font(13.0, 700)
    metrics = QFontMetricsF(font)
    cell = metrics.horizontalAdvance("M")
    art_width = max(len(line) for line in WHEEL) * cell
    line_height = metrics.height() * 1.02
    art_height = len(WHEEL) * line_height
    x = width - art_width - 36.0
    y = height - art_height - 46.0
    if x < width * 0.40 or y < 140.0:
        return
    color = QColor(theme.ORANGE)
    color.setAlphaF(0.11)
    painter.setFont(font)
    painter.setPen(color)
    baseline = y + metrics.ascent()
    for index, line in enumerate(WHEEL):
        painter.drawText(QPointF(x, baseline + index * line_height), line)
