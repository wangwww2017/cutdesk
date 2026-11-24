"""CutDesk 主程序：托盘、热键、选区、录制调度。"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRect, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .config import APP_NAME, APP_VERSION, Config, find_ffmpeg, format_hotkey, parse_hotkey
from .controlbar import ControlBar, FrameState, RegionFrame
from .hotkey import GlobalHotkey
from .icons import app_icon
from .overlay import SelectionManager
from .recorder import RecordResult, Recorder
from .settings_dialog import SettingsDialog

MUTEX_NAME = "Global\\CutDesk_SingleInstance_v1"


def _fmt_time(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class StopWorker(QThread):
    done = Signal(object)

    def __init__(self, rec: Recorder) -> None:
        super().__init__()
        self._rec = rec

    def run(self) -> None:
        try:
            res = self._rec.stop()
        except Exception as exc:  # 保护线程不静默崩溃
            res = RecordResult(error=f"处理失败：{exc}")
        self.done.emit(res)


class CutDeskApp(QObject):
    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self.qapp = qapp
        self.cfg = Config()
        self.icon = app_icon()
        qapp.setWindowIcon(self.icon)

        self.mgr = SelectionManager(self)
        self.mgr.finished.connect(self._on_region_selected)
        self.mgr.cancelled.connect(self._on_selection_cancelled)

        self.frame = RegionFrame()
        self.bar = ControlBar()
        self.bar.start_clicked.connect(self.start_recording)
        self.bar.stop_clicked.connect(self.stop_recording)
        self.bar.close_clicked.connect(self._dismiss_controls)

        self.hotkey = GlobalHotkey(parent=self)
        self.hotkey.activated.connect(self.on_hotkey)

        self.recorder: Recorder | None = None
        self.worker: StopWorker | None = None
        self.region: tuple[QRect, object, tuple[int, int, int, int]] | None = None
        self.last_saved: Path | None = None

        self.tick = QTimer(self)
        self.tick.setInterval(250)
        self.tick.timeout.connect(self._tick)

        self._build_tray()
        self._apply_hotkey(notify=True)

    # ------------------------------------------------------------------ 托盘
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(f"{APP_NAME} {APP_VERSION} · 屏幕 GIF 录制")
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu{background:#1B1E25;color:#E8ECF2;border:1px solid #3A404C;padding:4px;}"
            "QMenu::item{padding:6px 22px 6px 14px;border-radius:5px;}"
            "QMenu::item:selected{background:#2E333D;}"
            "QMenu::separator{height:1px;background:#2E333D;margin:4px 8px;}"
        )

        self.act_capture = QAction("选区录制", self)
        self.act_capture.triggered.connect(self.begin_selection)
        menu.addAction(self.act_capture)

        self.act_stop = QAction("停止并保存", self)
        self.act_stop.triggered.connect(self.stop_recording)
        self.act_stop.setEnabled(False)
        menu.addAction(self.act_stop)

        menu.addSeparator()
        act_open = QAction("打开保存目录", self)
        act_open.triggered.connect(self._open_out_dir)
        menu.addAction(act_open)

        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit)
        menu.addAction(act_quit)

        self._menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.begin_selection()

    def _on_message_clicked(self) -> None:
        if self.last_saved and self.last_saved.parent.exists():
            self._reveal(self.last_saved)

    def _build_menu_labels(self) -> None:
        hk = format_hotkey(str(self.cfg.get("hotkey")))
        self.act_capture.setText(f"选区录制\t{hk}")

    # ------------------------------------------------------------------ 热键
    def _apply_hotkey(self, notify: bool = False) -> bool:
        text = str(self.cfg.get("hotkey"))
        try:
            mods, vk = parse_hotkey(text)
        except ValueError as exc:
            self._toast("快捷键配置无效", str(exc))
            return False
        ok, err = self.hotkey.register(mods, vk)
        self._build_menu_labels()
        if not ok:
            self._toast("快捷键不可用", f"{err}\n仍可通过托盘菜单开始录制。")
            return False
        if notify:
            self.tray.setToolTip(f"{APP_NAME} · {format_hotkey(text)} 开始录制")
        return True

    def on_hotkey(self) -> None:
        if self.recorder is not None and self.recorder.running:
            self.stop_recording()
            return
        self.begin_selection()

    # ------------------------------------------------------------------ 选区
    def begin_selection(self) -> None:
        if self.recorder is not None and self.recorder.running:
            self._toast("正在录制", "先停止当前录制再重新选区。")
            return
        if self.mgr.active:
            return
        if self.worker is not None and self.worker.isRunning():
            self._toast("正在生成文件", "请等待当前文件处理完成。")
            return
        self._dismiss_controls()
        self.mgr.begin()

    def _on_selection_cancelled(self) -> None:
        if self.region is not None:
            self._restore_controls()

    def _on_region_selected(self, rect, screen, phys) -> None:
        self.region = (QRect(rect), screen, tuple(phys))
        self._restore_controls()

    def _restore_controls(self) -> None:
        if self.region is None:
            return
        rect, screen, phys = self.region
        self.frame.setGeometry(rect.adjusted(-2, -2, 2, 2))
        self.frame.set_state(FrameState.READY)
        self.frame.show()
        self.frame.raise_()
        _, _, pw, ph = phys
        self.bar.set_state(FrameState.READY, f"{pw}×{ph}")
        self.bar.attach_to(rect, screen)

    def _dismiss_controls(self) -> None:
        self.bar.hide()
        self.frame.hide()
        self.region = None

    # ------------------------------------------------------------------ 录制
    def start_recording(self) -> None:
        if self.region is None:
            self._toast("未选择区域", "按快捷键选择要录制的区域。")
            return
        if self.recorder is not None and self.recorder.running:
            return
        _, screen, phys = self.region
        rec = Recorder(phys, self.cfg)
        if not rec.start():
            self.bar.set_state(FrameState.READY, "启动失败")
            self._toast("无法开始录制", rec._v_error or "请检查 ffmpeg 配置")
            return
        self.recorder = rec
        self.frame.set_state(FrameState.RECORDING)
        self.bar.set_state(FrameState.RECORDING, "00:00")
        self.act_stop.setEnabled(True)
        self.tick.start()

    def _tick(self) -> None:
        if self.recorder is None:
            self.tick.stop()
            return
        self.bar.set_status(_fmt_time(self.recorder.elapsed()))

    def stop_recording(self) -> None:
        if self.recorder is None or not self.recorder.running:
            return
        self.tick.stop()
        rec = self.recorder
        self.recorder = None
        self.act_stop.setEnabled(False)
        self.frame.set_state(FrameState.PROCESSING)
        self.bar.set_state(FrameState.PROCESSING, "生成中")
        self.worker = StopWorker(rec)
        self.worker.done.connect(self._on_record_done)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _on_record_done(self, result: RecordResult) -> None:
        if result.ok and result.mp4:
            self.last_saved = result.mp4
            self.frame.set_state(FrameState.SAVED)
            self.bar.set_state(FrameState.SAVED, "已保存")
            title = "录制完成"
            body = f"{result.mp4.name}\n{result.summary}"
            if result.warnings:
                body += "\n" + "\n".join(result.warnings[:2])
            self._toast(title, body, 5000)
        else:
            self.frame.set_state(FrameState.READY)
            self.bar.set_state(FrameState.READY, "失败")
            self._toast("录制失败", result.error or "未知错误")

    # ------------------------------------------------------------------ 其它
    def open_settings(self) -> None:
        if self.recorder is not None and self.recorder.running:
            self._toast("正在录制", "请先停止录制再修改设置。")
            return
        dlg = SettingsDialog(self.cfg)
        if dlg.exec():
            self._apply_hotkey()
            self._toast("设置已保存", "新的参数将在下次录制时生效。")

    def _open_out_dir(self) -> None:
        d = self.cfg.out_dir()
        try:
            os.startfile(str(d))  # noqa: S606
        except OSError:
            self._toast("无法打开目录", str(d))

    def _reveal(self, path: Path) -> None:
        try:
            os.startfile(str(path.parent))  # noqa: S606
        except OSError:
            pass

    def _toast(self, title: str, body: str, msec: int = 3500) -> None:
        try:
            self.tray.showMessage(title, body, self.icon, msec)
        except Exception:
            pass

    def quit(self) -> None:
        try:
            if self.recorder is not None and self.recorder.running:
                self.recorder.stop()
            if self.worker is not None and self.worker.isRunning():
                self.worker.wait(8000)
        except Exception:
            pass
        self.hotkey.shutdown()
        self.tray.hide()
        self.qapp.quit()


def _acquire_single_instance() -> bool:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            return False
        globals()["_MUTEX_HANDLE"] = handle
        return True
    except Exception:
        return True


def main() -> int:
    if not _acquire_single_instance():
        tmp = QApplication(sys.argv)
        QMessageBox.information(None, APP_NAME, "CutDesk 已在运行，请查看系统托盘。")
        return 0

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationDisplayName(APP_NAME)
    qapp.setApplicationVersion(APP_VERSION)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setFont(QFont("Microsoft YaHei UI", 9))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "当前系统不支持托盘图标，无法运行。")
        return 1

    app = CutDeskApp(qapp)
    ff = find_ffmpeg()
    if not ff:
        app._toast(
            "未找到 ffmpeg",
            "录制需要 ffmpeg。请安装后放入程序目录的 bin 文件夹，或在设置中配置。",
            8000,
        )
    else:
        app._toast(
            f"{APP_NAME} 已启动",
            f"按 {format_hotkey(str(app.cfg.get('hotkey')))} 框选区域开始录制\n点击托盘图标亦可",
            4000,
        )
    return qapp.exec()
