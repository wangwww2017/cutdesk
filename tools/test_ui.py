"""UI 渲染冒烟测试：把各个浮层画到模拟桌面上并导出 PNG。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.controlbar import ControlBar, FrameState, RegionFrame  # noqa: E402
from app.overlay import SelectionOverlay  # noqa: E402

OUT = ROOT / "tools" / "_shots"
OUT.mkdir(parents=True, exist_ok=True)


def fake_desktop(w: int, h: int) -> QPixmap:
    pm = QPixmap(w, h)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0.0, QColor(30, 34, 44))
    g.setColorAt(1.0, QColor(18, 20, 26))
    p.fillRect(0, 0, w, h, QBrush(g))
    p.setPen(Qt.NoPen)
    for i, c in enumerate([(56, 120, 200), (72, 160, 120), (200, 150, 60), (170, 80, 90)]):
        p.setBrush(QColor(*c, 90))
        p.drawRoundedRect(60 + i * 210, 120 + (i % 2) * 90, 180, 110, 12, 12)
    p.setPen(QColor(200, 208, 220))
    f = QFont("Microsoft YaHei UI", 16)
    p.setFont(f)
    p.drawText(rect_for(w), Qt.AlignCenter, "模拟桌面背景")
    p.end()
    return pm


def rect_for(w):
    from PySide6.QtCore import QRect

    return QRect(0, 0, w, 320)


def compose(layer: QPixmap, bg: QPixmap) -> QPixmap:
    canvas = QPixmap(bg.size())
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.drawPixmap(0, 0, bg)
    p.drawPixmap(0, 0, layer)
    p.end()
    return canvas


def main() -> None:
    app = QApplication([])
    screen = app.primaryScreen()
    geo = screen.geometry()
    W, H = 1280, 800
    bg = fake_desktop(W, H)

    # 1) 选区遮罩（拖拽中状态）
    mgr = type("M", (), {"cancel": lambda self: None, "accept": lambda *a: None})()
    ov = SelectionOverlay(screen, mgr)
    ov.setGeometry(0, 0, W, H)
    ov.resize(W, H)
    ov._sel = QRect(300, 210, 640, 360)
    ov._cursor = QPoint(940, 570)
    ov._origin = QPoint(300, 210)
    shot = ov.grab()
    compose(shot, bg).save(str(OUT / "1_overlay_selecting.png"))

    # 2) 选区遮罩（初始提示）
    ov2 = SelectionOverlay(screen, mgr)
    ov2.setGeometry(0, 0, W, H)
    ov2.resize(W, H)
    ov2._cursor = QPoint(700, 420)
    compose(ov2.grab(), bg).save(str(OUT / "2_overlay_hint.png"))

    # 3) 控制条三种状态
    for idx, (state, text) in enumerate(
        [
            (FrameState.READY, "1280×720"),
            (FrameState.RECORDING, "00:12"),
            (FrameState.PROCESSING, "生成中"),
        ]
    ):
        bar = ControlBar()
        bar.set_state(state, text)
        pm = bar.grab()
        canvas = QPixmap(pm.width() + 40, pm.height() + 40)
        canvas.fill(QColor(32, 35, 44))
        p = QPainter(canvas)
        p.drawPixmap(20, 20, pm)
        p.end()
        canvas.save(str(OUT / f"3_bar_{idx}_{state.value}.png"))

    # 4) 选区边框
    fr = RegionFrame()
    fr.setGeometry(0, 0, 200, 120)
    fr.set_state(FrameState.RECORDING)
    fr_pm = fr.grab()
    canvas = QPixmap(fr_pm.width() + 40, fr_pm.height() + 40)
    canvas.fill(QColor(245, 245, 246))
    p = QPainter(canvas)
    p.drawPixmap(20, 20, fr_pm)
    p.end()
    canvas.save(str(OUT / "4_frame_recording.png"))

    print("saved to", OUT)
    for f in sorted(OUT.glob("*.png")):
        print(" ", f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
