"""设置对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import format_hotkey, parse_hotkey

QSS = """
QDialog { background: #1B1E25; }
QLabel { color: #C6CDD8; font-size: 12px; }
QLabel#title { color: #F0F3F7; font-size: 15px; font-weight: 600; }
QLabel#hint { color: #7F8899; font-size: 11px; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QKeySequenceEdit {
    background: #262A33; color: #E8ECF2; border: 1px solid #3A404C;
    border-radius: 6px; padding: 5px 8px; min-height: 18px; font-size: 12px;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: #4E5666; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #262A33; color: #E8ECF2; selection-background-color: #E5484D;
    border: 1px solid #3A404C; outline: none;
}
QPushButton {
    background: #2E333D; color: #E8ECF2; border: 1px solid #3E4552;
    border-radius: 7px; padding: 6px 14px; font-size: 12px;
}
QPushButton:hover { background: #39404C; }
QPushButton#primary { background: #E5484D; border: none; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #F2555A; }
QSlider::groove:horizontal { height: 4px; background: #333944; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #E5484D; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
}
QCheckBox { color: #C6CDD8; font-size: 12px; }
QCheckBox::indicator { width: 15px; height: 15px; border-radius: 4px; border: 1px solid #4A515F; background: #262A33; }
QCheckBox::indicator:checked { background: #E5484D; border-color: #E5484D; }
"""


def _combo(items: list[tuple[str, object]], current) -> QComboBox:
    cb = QComboBox()
    for label, value in items:
        cb.addItem(label, value)
    for i in range(cb.count()):
        if cb.itemData(i) == current:
            cb.setCurrentIndex(i)
            break
    return cb


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("CutDesk 设置")
        self.setModal(True)
        self.setStyleSheet(QSS)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 16)
        root.setSpacing(14)

        title = QLabel("录制设置")
        title.setObjectName("title")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # 输出目录
        out_row = QWidget()
        out_lay = QHBoxLayout(out_row)
        out_lay.setContentsMargins(0, 0, 0, 0)
        out_lay.setSpacing(6)
        self.ed_out = QLineEdit(str(cfg.out_dir()))
        btn_out = QPushButton("浏览…")
        btn_out.clicked.connect(self._pick_dir)
        out_lay.addWidget(self.ed_out, 1)
        out_lay.addWidget(btn_out)
        form.addRow("保存目录", out_row)

        # 快捷键
        self.ed_hotkey = QKeySequenceEdit()
        self.ed_hotkey.setKeySequence(
            QKeySequence.fromString(str(cfg.get("hotkey")), QKeySequence.PortableText)
        )
        self.ed_hotkey.setMaximumSequenceLength(1)
        form.addRow("全局快捷键", self.ed_hotkey)

        # 帧率
        self.cb_fps = _combo(
            [("15 fps（更省空间）", 15), ("24 fps", 24), ("30 fps（推荐）", 30), ("60 fps（高动态）", 60)],
            int(cfg.get("fps")),
        )
        form.addRow("视频帧率", self.cb_fps)

        # 画质
        self.sl_crf = QSlider(Qt.Horizontal)
        self.sl_crf.setRange(16, 32)
        self.sl_crf.setValue(int(cfg.get("mp4_crf")))
        self.sl_crf.setSingleStep(1)
        self.lb_crf = QLabel()
        self.lb_crf.setMinimumWidth(96)
        crf_row = QWidget()
        crf_lay = QHBoxLayout(crf_row)
        crf_lay.setContentsMargins(0, 0, 0, 0)
        crf_lay.setSpacing(8)
        crf_lay.addWidget(self.sl_crf, 1)
        crf_lay.addWidget(self.lb_crf)
        self.sl_crf.valueChanged.connect(self._sync_crf_label)
        self._sync_crf_label()
        form.addRow("视频画质", crf_row)

        # 最大宽度
        self.cb_width = _combo(
            [("保持原始分辨率", 0), ("最大 1280 px", 1280), ("最大 1600 px", 1600), ("最大 1920 px", 1920)],
            int(cfg.get("mp4_max_width")),
        )
        form.addRow("视频尺寸", self.cb_width)

        # 音频
        self.cb_audio = _combo(
            [
                ("系统声音", "system"),
                ("麦克风", "mic"),
                ("系统声音 + 麦克风", "both"),
                ("不录音", "none"),
            ],
            str(cfg.get("audio_source")),
        )
        form.addRow("录音来源", self.cb_audio)

        gif_title = QLabel("GIF 表情")
        gif_title.setObjectName("title")

        form2 = QFormLayout()
        form2.setSpacing(10)
        form2.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form2.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.cb_gif_fps = _combo([("8 fps", 8), ("10 fps", 10), ("12 fps（推荐）", 12), ("15 fps", 15)], int(cfg.get("gif_fps")))
        form2.addRow("GIF 帧率", self.cb_gif_fps)

        self.cb_gif_w = _combo([("320 px（小）", 320), ("400 px", 400), ("480 px（推荐）", 480), ("600 px（大）", 600)], int(cfg.get("gif_width")))
        form2.addRow("GIF 宽度", self.cb_gif_w)

        self.cb_gif_c = _combo([("64 色", 64), ("96 色", 96), ("128 色（推荐）", 128), ("256 色", 256)], int(cfg.get("gif_colors")))
        form2.addRow("GIF 色深", self.cb_gif_c)

        self.sp_gif_sec = QSpinBox()
        self.sp_gif_sec.setRange(2, 30)
        self.sp_gif_sec.setValue(int(cfg.get("gif_max_seconds")))
        self.sp_gif_sec.setSuffix(" 秒")
        form2.addRow("GIF 最长时长", self.sp_gif_sec)

        self.sp_gif_mb = QDoubleSpinBox()
        self.sp_gif_mb.setRange(0.5, 20.0)
        self.sp_gif_mb.setSingleStep(0.5)
        self.sp_gif_mb.setDecimals(1)
        self.sp_gif_mb.setValue(float(cfg.get("gif_max_mb")))
        self.sp_gif_mb.setSuffix(" MB")
        form2.addRow("GIF 体积上限", self.sp_gif_mb)

        self.chk_gif = QCheckBox("停止录制时同时生成 GIF 表情")
        self.chk_gif.setChecked(bool(cfg.get("make_gif")))
        form2.addRow("", self.chk_gif)

        root.addLayout(form)
        root.addSpacing(4)
        root.addWidget(gif_title)
        root.addLayout(form2)

        ff_row = QWidget()
        ff_lay = QHBoxLayout(ff_row)
        ff_lay.setContentsMargins(0, 0, 0, 0)
        ff_lay.setSpacing(6)
        self.ed_ff = QLineEdit(str(cfg.get("ffmpeg_path") or ""))
        self.ed_ff.setPlaceholderText("留空则自动查找")
        btn_ff = QPushButton("浏览…")
        btn_ff.clicked.connect(self._pick_ffmpeg)
        ff_lay.addWidget(self.ed_ff, 1)
        ff_lay.addWidget(btn_ff)
        form.addRow("ffmpeg 路径", ff_row)

        from .config import find_ffmpeg

        found = find_ffmpeg() or ""
        self.lb_ff = QLabel(f"当前使用：{found or '未找到 ffmpeg，无法录制'}")
        self.lb_ff.setObjectName("hint")
        root.addWidget(self.lb_ff)

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("保存")
        btn_ok.setObjectName("primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _sync_crf_label(self) -> None:
        v = self.sl_crf.value()
        if v <= 19:
            name = "极高"
        elif v <= 22:
            name = "高"
        elif v <= 25:
            name = "均衡"
        elif v <= 28:
            name = "省空间"
        else:
            name = "极限压缩"
        self.lb_crf.setText(f"{name} (CRF {v})")

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择保存目录", self.ed_out.text())
        if d:
            self.ed_out.setText(d)

    def _pick_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 ffmpeg 可执行文件", str(Path.home()), "可执行文件 (*.exe);;所有文件 (*)"
        )
        if path:
            self.ed_ff.setText(path)

    def _on_accept(self) -> None:
        seq = self.ed_hotkey.keySequence().toString(QKeySequence.PortableText)
        seq = seq.replace("Meta", "Win")
        if not seq:
            self.ed_hotkey.setFocus()
            return
        try:
            parse_hotkey(seq)
        except ValueError:
            self.ed_hotkey.setFocus()
            self.ed_hotkey.setStyleSheet("border: 1px solid #E5484D;")
            return

        cfg = self.cfg
        cfg["hotkey"] = format_hotkey(seq)
        cfg["ffmpeg_path"] = self.ed_ff.text().strip()
        cfg["out_dir"] = self.ed_out.text().strip() or str(cfg.out_dir())
        cfg["fps"] = int(self.cb_fps.currentData())
        cfg["mp4_crf"] = int(self.sl_crf.value())
        cfg["mp4_max_width"] = int(self.cb_width.currentData())
        cfg["audio_source"] = str(self.cb_audio.currentData())
        cfg["gif_fps"] = int(self.cb_gif_fps.currentData())
        cfg["gif_width"] = int(self.cb_gif_w.currentData())
        cfg["gif_colors"] = int(self.cb_gif_c.currentData())
        cfg["gif_max_seconds"] = int(self.sp_gif_sec.value())
        cfg["gif_max_mb"] = float(self.sp_gif_mb.value())
        cfg["make_gif"] = bool(self.chk_gif.isChecked())
        try:
            Path(cfg["out_dir"]).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        cfg.save()
        self.accept()
