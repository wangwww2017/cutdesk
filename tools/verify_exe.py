"""验证打包后的 exe：模拟真实按键与鼠标，完整跑一遍录制流程。

用法：python tools/verify_exe.py [exe路径]
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tools" / "_exe"
SHOTS.mkdir(parents=True, exist_ok=True)

u = ctypes.windll.user32
VK_CONTROL, VK_MENU, VK_R = 0x11, 0x12, 0x52
KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    u.SetProcessDPIAware()


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def find_windows_by_size(wmin: int, wmax: int, hmin: int, hmax: int) -> list[tuple[int, int, int, int, int]]:
    """返回可见窗口 (hwnd, left, top, width, height)。"""
    found: list[tuple[int, int, int, int, int]] = []

    def _cb(hwnd, lp):
        if not u.IsWindowVisible(hwnd):
            return True
        r = RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if wmin <= w <= wmax and hmin <= h <= hmax:
            found.append((hwnd, r.left, r.top, w, h))
        return True

    u.EnumWindows(ENUMPROC(_cb), 0)
    return found

OUT_DIR = Path.home() / "Videos" / "CutDesk"


def shot(name: str) -> Path:
    import mss
    from mss.tools import to_png

    p = SHOTS / f"{name}.png"
    with mss.mss() as sct:
        img = sct.grab(sct.monitors[1])
        to_png(img.rgb, img.size, output=str(p))
    return p


def press_hotkey() -> None:
    u.keybd_event(VK_CONTROL, 0, 0, 0)
    u.keybd_event(VK_MENU, 0, 0, 0)
    u.keybd_event(VK_R, 0, 0, 0)
    time.sleep(0.08)
    u.keybd_event(VK_R, 0, KEYUP, 0)
    u.keybd_event(VK_MENU, 0, KEYUP, 0)
    u.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    u.SetCursorPos(x1, y1)
    time.sleep(0.15)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.12)
    steps = 12
    for i in range(1, steps + 1):
        u.SetCursorPos(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps)
        time.sleep(0.02)
    time.sleep(0.1)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def click(x: int, y: int) -> None:
    u.SetCursorPos(x, y)
    time.sleep(0.2)
    u.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "CutDesk" / "CutDesk.exe"
    if not exe.is_file():
        print("找不到 exe:", exe)
        return 1

    before = {p.name for p in OUT_DIR.glob("CutDesk_*")}
    print("启动", exe)
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent))

    time.sleep(5.0)
    print("进程存活:", proc.poll() is None)
    shot("1_started")
    if proc.poll() is not None:
        print("!! 程序已退出，退出码", proc.returncode)
        return 2

    print("发送 Ctrl+Alt+R …")
    press_hotkey()
    time.sleep(1.6)
    shot("2_overlay")

    print("拖拽选区 …")
    drag(400, 300, 1120, 780)
    time.sleep(1.4)
    shot("3_controlbar")

    # 控制条是 304x48 逻辑（约 380x60 物理）的无边框窗口，靠尺寸识别
    bars = find_windows_by_size(340, 460, 45, 90)
    bars.sort(key=lambda x: x[2], reverse=True)  # 取最靠下的
    if not bars:
        print("!! 未找到控制条窗口", find_windows_by_size(200, 2000, 100, 2000)[:6])
        return 4
    hwnd, bx, by, bw, bh = bars[0]
    print(f"控制条 hwnd={hwnd} rect=({bx},{by},{bw},{bh})")
    scale = bw / 304.0

    start_x = bx + int(164 * scale)
    start_y = by + int(24 * scale)
    print(f"点击开始 ({start_x},{start_y})")
    click(start_x, start_y)
    time.sleep(1.2)
    shot("4_recording")
    time.sleep(3.2)
    shot("5_recording2")

    stop_x = bx + int(236 * scale)
    print(f"点击停止 ({stop_x},{start_y})")
    click(stop_x, start_y)
    time.sleep(5.0)
    shot("6_done")

    after = {p.name for p in OUT_DIR.glob("CutDesk_*")}
    new = sorted(after - before)
    print("新增文件:", new)
    for n in new:
        p = OUT_DIR / n
        print(f"  {n}  {p.stat().st_size / 1024:.1f} KB")

    print("关闭程序")
    try:
        proc.terminate()
        proc.wait(timeout=8)
    except Exception:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False)

    return 0 if new else 3


if __name__ == "__main__":
    sys.exit(main())
