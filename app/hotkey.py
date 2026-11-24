"""Win32 全局热键注册。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkey") -> None:
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and int(msg.wParam) == self.owner.hotkey_id:
                    self.owner.activated.emit()
                    return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, hotkey_id: int = 0xA17, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.hotkey_id = hotkey_id
        self._registered = False
        self._filter: _Filter | None = None
        self._mods = 0
        self._vk = 0

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self, mods: int, vk: int) -> tuple[bool, str]:
        self.unregister()
        ok = user32.RegisterHotKey(None, self.hotkey_id, mods | MOD_NOREPEAT, vk)
        if not ok:
            code = ctypes.get_last_error()
            hint = {
                1409: "该快捷键已被其他程序占用",
            }.get(code, f"系统返回错误码 {code}")
            return False, f"全局快捷键注册失败：{hint}"
        self._registered = True
        self._mods, self._vk = mods, vk
        app = QApplication.instance()
        if app is not None and self._filter is None:
            self._filter = _Filter(self)
            app.installNativeEventFilter(self._filter)
        return True, ""

    def unregister(self) -> None:
        if not self._registered:
            return
        try:
            user32.UnregisterHotKey(None, self.hotkey_id)
        except Exception:
            pass
        self._registered = False

    def shutdown(self) -> None:
        self.unregister()
        app = QApplication.instance()
        if app is not None and self._filter is not None:
            try:
                app.removeNativeEventFilter(self._filter)
            except Exception:
                pass
            self._filter = None
