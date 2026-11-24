"""Windows 物理像素与 Qt 逻辑像素之间的映射。

Qt 使用逻辑坐标（受系统 DPI 缩放影响），而屏幕采集 / ffmpeg 需要物理像素坐标。
Windows 上通过 EnumDisplayMonitors + GetMonitorInfo 取出各显示器的物理矩形，
再与 QScreen 一一配对。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ClientToScreen.restype = wintypes.BOOL


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
)


def enum_monitors() -> list[dict]:
    """返回物理像素坐标的显示器列表：[{name, left, top, width, height, primary}]"""
    result: list[dict] = []

    def _cb(hmon, hdc, lprc, data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            result.append(
                {
                    "name": info.szDevice,
                    "left": int(r.left),
                    "top": int(r.top),
                    "width": int(r.right - r.left),
                    "height": int(r.bottom - r.top),
                    "primary": bool(info.dwFlags & 1),
                }
            )
        return True

    user32.EnumDisplayMonitors(0, 0, MONITORENUMPROC(_cb), 0)
    return result


def _center_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def monitor_for_screen(qscreen) -> dict | None:
    """为给定 QScreen 找到对应的物理显示器信息。"""
    monitors = enum_monitors()
    if not monitors:
        return None

    # 1) 优先按设备名匹配（Qt 在 Windows 上返回 \\.\DISPLAYn）
    try:
        qname = qscreen.name()
    except Exception:
        qname = ""
    if qname:
        for m in monitors:
            if m["name"].lower() == qname.lower():
                return m

    # 2) 退化方案：用逻辑中心按 dpr 换算后与物理中心比对
    try:
        geo = qscreen.geometry()
        dpr = float(qscreen.devicePixelRatio() or 1.0)
    except Exception:
        return monitors[0] if len(monitors) == 1 else None
    logical_center = (geo.x() + geo.width() / 2.0, geo.y() + geo.height() / 2.0)

    best, best_score = None, None
    for m in monitors:
        phys_center = (m["left"] + m["width"] / 2.0, m["top"] + m["height"] / 2.0)
        scaled = (logical_center[0] * dpr, logical_center[1] * dpr)
        score = _center_distance(scaled, phys_center)
        if best_score is None or score < best_score:
            best, best_score = m, score
    return best


def logical_rect_to_physical(qscreen, rect) -> tuple[int, int, int, int]:
    """把全局逻辑矩形 (x, y, w, h) 换算成物理像素矩形。

    rect 为 Qt 全局逻辑坐标（QRect），要求其位于 qscreen 覆盖范围内。
    """
    mon = monitor_for_screen(qscreen)
    geo = qscreen.geometry()
    dpr = float(qscreen.devicePixelRatio() or 1.0)

    rel_x = rect.x() - geo.x()
    rel_y = rect.y() - geo.y()

    if mon is None:
        # 极端兜底：直接按 dpr 缩放
        return (
            int(round(rel_x * dpr)),
            int(round(rel_y * dpr)),
            max(2, int(round(rect.width() * dpr))),
            max(2, int(round(rect.height() * dpr))),
        )

    px = mon["left"] + int(round(rel_x * dpr))
    py = mon["top"] + int(round(rel_y * dpr))
    pw = max(2, int(round(rect.width() * dpr)))
    ph = max(2, int(round(rect.height() * dpr)))

    # 裁剪到显示器物理边界内，避免采集越界出现黑边
    px = max(mon["left"], min(px, mon["left"] + mon["width"] - 2))
    py = max(mon["top"], min(py, mon["top"] + mon["height"] - 2))
    pw = min(pw, mon["left"] + mon["width"] - px)
    ph = min(ph, mon["top"] + mon["height"] - py)
    # H.264 要求偶数尺寸
    pw -= pw % 2
    ph -= ph % 2
    return px, py, max(2, pw), max(2, ph)


def primary_work_area() -> tuple[int, int, int, int]:
    """主屏工作区（物理像素，不含任务栏）。"""
    for m in enum_monitors():
        if m["primary"]:
            return m["left"], m["top"], m["width"], m["height"]
    return 0, 0, 1920, 1080


def client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    """返回窗口客户区在屏幕上的物理像素矩形 (left, top, width, height)。

    进程为 per-monitor DPI aware 时，Win32 返回真实物理像素；这是把 Qt 逻辑
    坐标换算成采集坐标最可靠的方式，无需在 QScreen 与显示器之间做配对。
    """
    try:
        h = wintypes.HWND(hwnd)
        rect = RECT()
        if not user32.GetClientRect(h, ctypes.byref(rect)):
            return None
        pt = POINT(rect.left, rect.top)
        if not user32.ClientToScreen(h, ctypes.byref(pt)):
            return None
        w = int(rect.right - rect.left)
        hh = int(rect.bottom - rect.top)
        if w <= 0 or hh <= 0:
            return None
        return int(pt.x), int(pt.y), w, hh
    except Exception:
        return None


def set_process_dpi_aware() -> None:
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
