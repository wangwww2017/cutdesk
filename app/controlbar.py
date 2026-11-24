"""选区边框与控制条浮窗。"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

BTN_H = 28
BAR_H = 48
PAD = 10
STATUS_W = 118
BTN_W = 64
CLOSE_W = 22
GAP = 8

ACCENT = QColor(229, 72, 77)
ACCENT_HOVER = QColor(242, 96, 100)
BAR_BG = QColor(24, 26, 33, 246)
BAR_BORDER = QColor(72, 78, 92, 200)
TXT_MAIN = QColor(236, 239, 243)
TXT_DIM = QColor(138, 146, 160)


class FrameState(Enum):
    READY = "ready"
    RECORDING = "recording"
    PROCESSING = "processing"
    SAVED = "saved"


class RegionFrame(QWidget):
    """贴在录制区域外侧的标记框，鼠标可穿透，不会被录入画面。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._state = FrameState.READY
        self._blink = True
        self._timer = QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._on_blink)
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.setInterval(4000)
        self._saved_timer.timeout.connect(lambda: self.set_state(FrameState.READY))

    def _on_blink(self) -> None:
        self._blink = not self._blink
        self.update()

    def set_state(self, state: FrameState) -> None:
        self._state = state
        if state == FrameState.RECORDING:
            self._blink = True
            self._timer.start()
        else:
            self._timer.stop()
            self._blink = True
        # 保存完成后短暂显示绿色，随后回到待录状态
        if state == FrameState.SAVED:
            self._saved_timer.start()
        else:
            self._saved_timer.stop()
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._state == FrameState.RECORDING:
            color = QColor(ACCENT) if self._blink else QColor(255, 255, 255, 210)
        elif self._state == FrameState.PROCESSING:
            color = QColor(240, 176, 64)
        elif self._state == FrameState.SAVED:
            color = QColor(76, 200, 130)
        else:
            color = QColor(255, 255, 255, 190)
        pen = QPen(color, 2)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()


class ControlBar(QWidget):
    """跟随选区的小型控制条。"""

    start_clicked = Signal()
    stop_clicked = Signal()
    close_clicked = Signal()
    reselect_clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

        self._state = FrameState.READY
        self._status = ""
        self._hover = -1
        self._dragging = False
        self._drag_offset = QPoint()
        self._blink = True
        self._pinned = False

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(600)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self._reset_timer = QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(lambda: self.set_state(FrameState.READY))

        self._f_btn = QFont("Microsoft YaHei UI", 9)
        self._f_btn.setBold(True)
        self._f_status = QFont("Microsoft YaHei UI", 9)
        self._f_status.setBold(True)

        self.setFixedSize(self._preferred_width(), BAR_H)

    # ------------------------------------------------------------- 尺寸/布局
    def _preferred_width(self) -> int:
        return PAD + STATUS_W + BTN_W + GAP + BTN_W + GAP + CLOSE_W + PAD

    def _rect_start(self) -> QRect:
        x = PAD + STATUS_W + 4
        return QRect(x, (BAR_H - BTN_H) // 2, BTN_W, BTN_H)

    def _rect_stop(self) -> QRect:
        r = self._rect_start()
        return QRect(r.right() + 1 + GAP, r.y(), BTN_W, BTN_H)

    def _rect_close(self) -> QRect:
        r = self._rect_stop()
        x = r.right() + 1 + GAP
        return QRect(x, (BAR_H - CLOSE_W) // 2, CLOSE_W, CLOSE_W)

    def sizeHint(self) -> QSize:
        return QSize(self._preferred_width(), BAR_H)

    # ------------------------------------------------------------- 状态
    def set_state(self, state: FrameState, status: str = "") -> None:
        self._state = state
        self._status = status
        if state == FrameState.RECORDING:
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink = True
        if state == FrameState.SAVED:
            self._reset_timer.start(4000)
        self.update()

    def set_status(self, status: str) -> None:
        self._status = status
        self.update()

    def _toggle_blink(self) -> None:
        self._blink = not self._blink
        self.update()

    # ------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        body = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(body.toRectF(), 10, 10)
        p.setPen(QPen(BAR_BORDER, 1))
        p.setBrush(BAR_BG)
        p.drawPath(path)

        # 状态区
        self._paint_status(p, QRect(PAD, 0, STATUS_W, BAR_H))

        # 开始按钮
        self._paint_button(
            p, self._rect_start(), "开始",
            enabled=self._state == FrameState.READY,
            hover=self._hover == 0,
            primary=True,
            dot=True,
        )
        # 停止按钮
        self._paint_button(
            p, self._rect_stop(), "停止",
            enabled=self._state == FrameState.RECORDING,
            hover=self._hover == 1,
            primary=True,
            dot=False,
            square=True,
        )
        # 关闭
        self._paint_close(p, self._rect_close(), self._hover == 2)
        p.end()

    def _paint_status(self, p: QPainter, rect: QRect) -> None:
        p.setFont(self._f_status)
        fm = p.fontMetrics()
        if self._state == FrameState.RECORDING:
            dot_r = 4
            dot_x = rect.left() + 4
            cy = rect.center().y()
            if self._blink:
                p.setPen(Qt.NoPen)
                p.setBrush(ACCENT)
                p.drawEllipse(QPoint(dot_x + dot_r, cy), dot_r, dot_r)
            p.setPen(TXT_MAIN)
            p.drawText(
                QRect(rect.left() + 18, rect.top(), rect.width() - 18, rect.height()),
                Qt.AlignVCenter | Qt.AlignLeft,
                self._status or "00:00",
            )
        else:
            p.setPen(TXT_MAIN if self._state == FrameState.READY else TXT_DIM)
            text = self._status or "就绪"
            p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_button(
        self,
        p: QPainter,
        rect: QRect,
        label: str,
        enabled: bool,
        hover: bool,
        primary: bool,
        dot: bool = False,
        square: bool = False,
    ) -> None:
        r = rect.toRectF()
        if not enabled:
            bg = QColor(42, 46, 56, 230)
            fg = QColor(110, 118, 132)
        elif primary:
            bg = ACCENT_HOVER if hover else ACCENT
            fg = QColor(255, 255, 255)
        else:
            bg = QColor(58, 64, 76) if not hover else QColor(72, 79, 94)
            fg = TXT_MAIN

        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 7, 7)

        p.setFont(self._f_btn)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(label)
        icon_w = 12 if (dot or square) else 0
        total = text_w + icon_w + (5 if icon_w else 0)
        x = r.center().x() - total / 2
        cy = r.center().y()

        if dot:
            p.setBrush(QColor(255, 255, 255) if enabled else fg)
            p.drawEllipse(QPoint(int(x + 4), int(cy)), 4, 4)
            x += icon_w + 5
        elif square:
            p.setBrush(QColor(255, 255, 255) if enabled else fg)
            p.drawRoundedRect(QRect(int(x), int(cy - 4), 8, 8), 1.5, 1.5)
            x += icon_w + 5

        p.setPen(fg)
        p.drawText(QRect(int(x), int(r.top()), int(text_w + 4), int(r.height())),
                   Qt.AlignVCenter | Qt.AlignLeft, label)

    def _paint_close(self, p: QPainter, rect: QRect, hover: bool) -> None:
        enabled = self._state in (FrameState.READY, FrameState.SAVED)
        if hover and enabled:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(58, 64, 76))
            p.drawRoundedRect(rect.toRectF(), 6, 6)
        color = (TXT_MAIN if hover else TXT_DIM) if enabled else QColor(78, 84, 96)
        p.setPen(QPen(color, 1.6))
        c = rect.center()
        d = 4
        p.drawLine(c.x() - d, c.y() - d, c.x() + d, c.y() + d)
        p.drawLine(c.x() + d, c.y() - d, c.x() - d, c.y() + d)

    # ------------------------------------------------------------- 交互
    def _hit(self, pos: QPoint) -> int:
        if self._rect_start().contains(pos):
            return 0
        if self._rect_stop().contains(pos):
            return 1
        if self._rect_close().contains(pos):
            return 2
        return -1

    def _enabled(self, idx: int) -> bool:
        if idx == 0:
            return self._state == FrameState.READY
        if idx == 1:
            return self._state == FrameState.RECORDING
        if idx == 2:
            # 录制 / 转码过程中不允许关闭，否则会失去停止入口
            return self._state in (FrameState.READY, FrameState.SAVED)
        return False

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            new_pos = QCursor.pos() - self._drag_offset
            self._pinned = True
            self.move(new_pos)
            return
        hit = self._hit(event.position().toPoint())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit >= 0 else Qt.SizeAllCursor)
            self.update()

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        pos = event.position().toPoint()
        hit = self._hit(pos)
        if hit >= 0:
            return
        self._dragging = True
        self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self._dragging:
            self._dragging = False
            return
        pos = event.position().toPoint()
        hit = self._hit(pos)
        if hit < 0 or not self._enabled(hit):
            return
        if hit == 0:
            self.start_clicked.emit()
        elif hit == 1:
            self.stop_clicked.emit()
        elif hit == 2:
            self.close_clicked.emit()

    # ------------------------------------------------------------- 定位
    def attach_to(self, region: QRect, screen) -> None:
        """把控制条放到选区外：优先下方，其次上方，最后叠在内部。"""
        self._pinned = False
        avail = screen.availableGeometry()
        w, h = self.width(), self.height()
        margin = 10

        x = region.center().x() - w // 2
        y = region.bottom() + margin
        if y + h > avail.bottom():
            y = region.top() - h - margin
        if y < avail.top():
            y = max(avail.top(), region.bottom() - h - margin)

        x = max(avail.left() + 4, min(x, avail.right() - w - 4))
        y = max(avail.top() + 4, min(y, avail.bottom() - h - 4))
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()

    def clamp_into(self, screen) -> None:
        avail = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = max(avail.left() + 4, min(self.x(), avail.right() - w - 4))
        y = max(avail.top() + 4, min(self.y(), avail.bottom() - h - 4))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
