"""端到端测试：模拟选区 -> 录制动态画面 + 播放音调 -> 停止保存。

用法：python tools/test_e2e.py
"""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app.main import CutDeskApp  # noqa: E402

REC_W = 640
REC_H = 400
ORIGIN = QPoint(260, 200)


class Mover(QWidget):
    """屏幕上不断变化的方块，用来模拟真实动态内容。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(REC_W + 40, REC_H + 40)
        self.move(ORIGIN.x() - 20, ORIGIN.y() - 20)
        self.t = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self) -> None:
        self.t += 1
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(26, 30, 40))
        span = self.width() - 100
        x = 50 + int((self.t * 6) % span)
        y = 60 + int(80 + 60 * __import__("math").sin(self.t * 0.06))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(229, 72, 77))
        p.drawEllipse(x, y, 56, 56)
        p.setBrush(QColor(72, 200, 140))
        p.drawRect(40, self.height() - 90, int((self.t * 9) % (self.width() - 90)), 26)
        p.setPen(QColor(235, 240, 246))
        p.setFont(QFont("Microsoft YaHei UI", 14))
        p.drawText(40, 44, f"CutDesk 端到端测试  frame={self.t}")
        p.end()


def play_tone(seconds: float) -> None:
    try:
        import numpy as np
        import soundcard as sc

        spk = sc.default_speaker()
        if spk is None:
            return
        sr = 48000
        t = np.arange(int(sr * seconds)) / sr
        wave = (0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        stereo = np.stack([wave, wave], axis=1)
        with spk.player(samplerate=sr, channels=2) as player:
            player.play(stereo)
    except Exception as exc:
        print("[audio] 播放测试音失败:", exc)


def send_mouse(widget, etype, pos: QPoint) -> None:
    buttons = Qt.LeftButton if etype in (QEvent.MouseButtonPress,) else Qt.NoButton
    ev = QMouseEvent(
        etype,
        QPointF(pos),
        QPointF(widget.mapToGlobal(pos)),
        Qt.LeftButton,
        buttons,
        Qt.NoModifier,
    )
    QApplication.sendEvent(widget, ev)


def main() -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    cds = CutDeskApp(app)
    holder = Mover()
    holder.show()
    holder.raise_()

    state = {"phase": "init", "t0": 0.0}
    threading.Thread(target=play_tone, args=(14.0,), daemon=True).start()

    def log(*a):
        print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)

    def do_select() -> None:
        log("phase: begin_selection")
        cds.begin_selection()

    def do_drag() -> None:
        ov = None
        for o in cds.mgr._overlays:
            if o.screen() == app.primaryScreen():
                ov = o
                break
        if ov is None:
            log("!! no overlay")
            app.quit()
            return
        geo = ov.geometry()
        start = QPoint(ORIGIN.x() - geo.x() + 20, ORIGIN.y() - geo.y() + 20)
        end = QPoint(start.x() + REC_W, start.y() + REC_H)
        log("phase: drag", start, end)
        send_mouse(ov, QEvent.MouseButtonPress, start)
        send_mouse(ov, QEvent.MouseMove, QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2))
        send_mouse(ov, QEvent.MouseMove, end)
        send_mouse(ov, QEvent.MouseButtonRelease, end)

    def do_start() -> None:
        log("phase: start_recording; region =", cds.region)
        if cds.region is None:
            log("!! region 为空")
            app.quit()
            return
        state["t0"] = time.perf_counter()
        cds.start_recording()

    def do_stop() -> None:
        log("phase: stop_recording  elapsed=", round(time.perf_counter() - state["t0"], 2))
        cds.stop_recording()

    def check_done() -> None:
        if cds.worker is not None and cds.worker.isRunning():
            QTimer.singleShot(300, check_done)
            return
        log("phase: done")
        QTimer.singleShot(1200, app.quit)

    QTimer.singleShot(600, do_select)
    QTimer.singleShot(1100, do_drag)
    QTimer.singleShot(1900, do_start)
    QTimer.singleShot(6400, do_stop)
    QTimer.singleShot(7000, check_done)

    app.exec()

    if cds.last_saved:
        p = Path(cds.last_saved)
        log("saved:", p, p.stat().st_size if p.exists() else "missing")
        g = p.with_suffix(".gif")
        if g.exists():
            log("gif:", g, g.stat().st_size)
    else:
        log("!! 没有产生输出文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
