from __future__ import annotations

import math

from PySide6.QtGui import QColor, QFontMetricsF, QPainter


def ease_out_cubic(value: float) -> float:
    remaining = 1.0 - max(0.0, min(1.0, value))
    return 1.0 - remaining * remaining * remaining


def draw_falling_text(
    painter: QPainter,
    x: float,
    baseline: float,
    text: str,
    metrics: QFontMetricsF,
    color: QColor,
    elapsed: float,
    speed: float,
    drop: float = 6.5,
    duration: float = 0.2,
) -> float:
    if not text:
        return 0.0
    if speed <= 0 or elapsed >= len(text) / speed:
        painter.setPen(color)
        painter.drawText(int(round(x)), int(round(baseline)), text)
        return metrics.horizontalAdvance(text)
    advance = 0.0
    for index, char in enumerate(text):
        local = elapsed * speed - index
        width = metrics.horizontalAdvance(char)
        if local <= 0:
            break
        appeared = local / speed
        progress = min(1.0, appeared / duration)
        eased = ease_out_cubic(progress)
        offset = drop * (1.0 - eased)
        if progress > 0.72:
            settle = (progress - 0.72) / 0.28
            offset -= math.sin(settle * math.pi) * 1.4 * (1.0 - settle)
        if char != " ":
            ink = QColor(color)
            ink.setAlphaF(ink.alphaF() * min(1.0, appeared / 0.16))
            painter.setPen(ink)
            painter.drawText(
                int(round(x + advance)),
                int(round(baseline - offset)),
                char,
            )
        advance += width
    return advance
