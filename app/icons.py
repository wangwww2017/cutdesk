"""程序化生成图标，避免外部资源依赖。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def app_icon_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size)

    # 背板
    body = QRectF(s * 0.04, s * 0.04, s * 0.92, s * 0.92)
    path = QPainterPath()
    path.addRoundedRect(body, s * 0.22, s * 0.22)
    p.fillPath(path, QColor(28, 31, 40))

    # 选区虚线框
    inset = s * 0.24
    frame = QRectF(inset, inset, s - 2 * inset, s - 2 * inset)
    pen = QPen(QColor(214, 220, 232), max(1.4, s * 0.035))
    pen.setStyle(Qt.DashLine)
    pen.setDashPattern([2.2, 1.6])
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(frame, s * 0.06, s * 0.06)

    # 录制点
    r = s * 0.155
    c = QPointF(s / 2.0, s / 2.0)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(229, 72, 77))
    p.drawEllipse(c, r, r)

    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_icon_pixmap(size))
    return icon


def status_dot_icon(color: QColor, size: int = 16) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    p.end()
    return QIcon(pm)
