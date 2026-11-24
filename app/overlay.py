"""区域选择遮罩：每个屏幕一个全屏半透明层，拖拽出录制区域。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .screeninfo import client_rect_on_screen

MIN_SIZE = 24  # 逻辑像素


class SelectionOverlay(QWidget):
    """单屏遮罩层。"""

    def __init__(self, screen, manager: "SelectionManager") -> None:
        super().__init__(None)
        self._screen = screen
        self._manager = manager
        self._origin: QPoint | None = None
        self._cursor: QPoint | None = None
        self._sel: QRect | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        geo = screen.geometry()
        self.setGeometry(geo)

    # ---------------------------------------------------------------- 展示
    def popup(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def screen(self):
        return self._screen

    def selection(self) -> QRect | None:
        return self._sel

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        full = QPainterPath()
        full.addRect(QRectF(self.rect()))
        dim = QColor(8, 10, 16, 168)

        if self._sel and self._sel.width() > 1 and self._sel.height() > 1:
            path = QPainterPath()
            path.setFillRule(Qt.OddEvenFill)
            path.addRect(QRectF(self.rect()))
            path.addRect(QRectF(self._sel))
            p.fillPath(path, dim)

            pen = QPen(QColor(255, 255, 255, 235), 1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(self._sel)

            # 四角强调
            p.setPen(QPen(QColor(255, 92, 92), 3))
            arm = 12
            r = self._sel
            p.drawLine(r.left(), r.top(), r.left() + arm, r.top())
            p.drawLine(r.left(), r.top(), r.left(), r.top() + arm)
            p.drawLine(r.right(), r.top(), r.right() - arm, r.top())
            p.drawLine(r.right(), r.top(), r.right(), r.top() + arm)
            p.drawLine(r.left(), r.bottom(), r.left() + arm, r.bottom())
            p.drawLine(r.left(), r.bottom(), r.left(), r.bottom() - arm)
            p.drawLine(r.right(), r.bottom(), r.right() - arm, r.bottom())
            p.drawLine(r.right(), r.bottom(), r.right(), r.bottom() - arm)

            self._draw_size_badge(p, r)
        else:
            p.fillPath(full, dim)
            if self._cursor is not None:
                p.setRenderHint(QPainter.Antialiasing, False)
                p.setPen(QPen(QColor(255, 255, 255, 96), 1))
                cy, cx = self._cursor.y(), self._cursor.x()
                p.drawLine(0, cy, self.width(), cy)
                p.drawLine(cx, 0, cx, self.height())
                p.setRenderHint(QPainter.Antialiasing, True)

        self._draw_hint(p)
        p.end()

    def _draw_size_badge(self, p: QPainter, sel: QRect) -> None:
        dpr = float(self._screen.devicePixelRatio() or 1.0)
        pw = int(round(sel.width() * dpr))
        ph = int(round(sel.height() * dpr))
        text = f"{pw} × {ph}"

        f = QFont("Microsoft YaHei UI", 9)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 18
        h = fm.height() + 8
        x = sel.center().x() - w // 2
        y = sel.top() - h - 8
        if y < 6:
            y = sel.top() + 8
        x = max(6, min(x, self.width() - w - 6))
        box = QRect(int(x), int(y), int(w), int(h))
        p.setPen(QPen(QColor(255, 255, 255, 48), 1))
        p.setBrush(QColor(22, 25, 32, 246))
        p.drawRoundedRect(box, 5, 5)
        p.setPen(QColor(242, 245, 249))
        p.drawText(box, Qt.AlignCenter, text)

    def _draw_hint(self, p: QPainter) -> None:
        if self._origin is not None:
            return
        text = "拖动鼠标框选录制区域    Esc / 右键 取消"
        f = QFont("Microsoft YaHei UI", 11)
        f.setBold(True)
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 36
        h = fm.height() + 18
        x = (self.width() - w) // 2
        y = int(self.height() * 0.12)
        box = QRect(int(x), y, int(w), int(h))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(22, 25, 32, 244))
        p.drawRoundedRect(box, 10, 10)
        p.setPen(QColor(242, 245, 249))
        p.drawText(box, Qt.AlignCenter, text)

    # ---------------------------------------------------------------- 交互
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self._manager.cancel()
            return
        if event.button() != Qt.LeftButton:
            return
        self._origin = self._clamp(event.position().toPoint())
        self._cursor = self._origin
        self._sel = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._cursor = self._clamp(event.position().toPoint())
        if self._origin is not None:
            self._sel = QRect(self._origin, self._cursor).normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._origin is None:
            return
        sel = QRect(self._origin, self._clamp(event.position().toPoint())).normalized()
        self._origin = None
        if sel.width() < MIN_SIZE or sel.height() < MIN_SIZE:
            self._sel = None
            self.update()
            self._manager.cancel()
            return
        self._sel = sel
        self.update()
        global_rect = QRect(sel)
        global_rect.translate(self.geometry().topLeft())
        self._manager.accept(global_rect, self._screen, self.physical_rect(sel))

    def physical_rect(self, sel: QRect) -> tuple[int, int, int, int]:
        """把窗口内的逻辑选区换算为屏幕物理像素矩形。

        用窗口客户区的真实物理尺寸反推缩放比例，比依赖 devicePixelRatio 更稳，
        且在多屏不同缩放时同样成立。
        """
        info = client_rect_on_screen(int(self.winId()))
        if info is not None:
            left, top, cw, ch = info
            sx = cw / max(1, self.width())
            sy = ch / max(1, self.height())
        else:
            dpr = float(self._screen.devicePixelRatio() or 1.0)
            left = top = 0
            sx = sy = dpr

        px = left + int(round(sel.x() * sx))
        py = top + int(round(sel.y() * sy))
        pw = int(round(sel.width() * sx))
        ph = int(round(sel.height() * sy))
        # H.264 需要偶数尺寸
        pw -= pw % 2
        ph -= ph % 2
        return px, py, max(2, pw), max(2, ph)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._manager.cancel()
        else:
            super().keyPressEvent(event)

    def _clamp(self, pt: QPoint) -> QPoint:
        return QPoint(
            max(0, min(pt.x(), self.width() - 1)),
            max(0, min(pt.y(), self.height() - 1)),
        )


class SelectionManager(QObject):
    """统一管理所有屏幕的遮罩层。"""

    finished = Signal(object, object, object)  # (QRect 全局逻辑, QScreen, 物理矩形)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._overlays: list[SelectionOverlay] = []
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def begin(self) -> None:
        if self._active:
            return
        self._active = True
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        for screen in app.screens():
            ov = SelectionOverlay(screen, self)
            self._overlays.append(ov)
            ov.popup()

    def _teardown(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        overlays, self._overlays = self._overlays, []
        self._active = False
        for ov in overlays:
            try:
                ov.hide()
                ov.close()
                ov.deleteLater()
            except RuntimeError:
                pass

    def accept(self, rect: QRect, screen, phys: tuple[int, int, int, int]) -> None:
        self._teardown()
        self.finished.emit(rect, screen, phys)

    def cancel(self) -> None:
        if not self._active:
            return
        self._teardown()
        self.cancelled.emit()

    # 全局捕获 Esc（多屏遮罩时只有最后一个窗口有焦点）
    def eventFilter(self, obj, event) -> bool:
        if self._active and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancel()
                return True
        return False
