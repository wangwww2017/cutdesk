"""CutDesk - 配置与运行时路径管理。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "CutDesk"
APP_VERSION = "1.0.0"

IS_FROZEN = getattr(sys, "frozen", False)
# 打包后以 exe 所在目录为基准，开发时以项目根目录为基准
BASE_DIR = Path(sys.executable).parent if IS_FROZEN else Path(__file__).resolve().parent.parent

CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_OUT_DIR = str(Path.home() / "Videos" / APP_NAME)

DEFAULTS: dict = {
    "hotkey": "Ctrl+Alt+R",
    "out_dir": DEFAULT_OUT_DIR,
    "ffmpeg_path": "",
    "max_seconds": 1800,
    "make_gif": True,
    "fps": 30,
    "mp4_crf": 21,
    "mp4_max_width": 1600,
    "mp4_preset": "medium",
    "audio_source": "system",      # system | mic | both | none
    "audio_bitrate": "96k",
    "gif_fps": 12,
    "gif_width": 480,
    "gif_colors": 128,
    "gif_max_seconds": 10,
    "gif_max_mb": 5.0,
    "keep_selection": True,
    "notify_open_folder": True,
}

_HOTKEY_MODS = {
    "ctrl": 0x0002,
    "control": 0x0002,
    "alt": 0x0001,
    "shift": 0x0004,
    "win": 0x0008,
    "super": 0x0008,
    "meta": 0x0008,
}

_NAME_TO_VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pause": 0x13,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}
for _i in range(12):
    _NAME_TO_VK[f"f{_i + 1}"] = 0x70 + _i


def parse_hotkey(text: str) -> tuple[int, int]:
    """把 'Ctrl+Alt+R' 解析为 (modifiers, vk)。无法解析时抛出 ValueError。"""
    if not text or not text.strip():
        raise ValueError("快捷键为空")
    mods = 0
    vk = None
    parts = [p.strip().lower() for p in text.replace("-", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("快捷键为空")
    for part in parts:
        if part in _HOTKEY_MODS:
            mods |= _HOTKEY_MODS[part]
        elif part in _NAME_TO_VK:
            vk = _NAME_TO_VK[part]
        elif len(part) == 1:
            ch = part.upper()
            if ch.isalpha() or ch.isdigit():
                vk = ord(ch)
            else:
                raise ValueError(f"不支持的按键：{part}")
        else:
            raise ValueError(f"不支持的按键：{part}")
    if vk is None:
        raise ValueError("缺少主键（如 R 或 F8）")
    if mods == 0:
        raise ValueError("必须包含至少一个修饰键（Ctrl/Alt/Shift/Win）")
    return mods, vk


def format_hotkey(text: str) -> str:
    """规范化显示，如 ctrl+alt+r -> Ctrl+Alt+R"""
    out = []
    for p in text.replace("-", "+").split("+"):
        p = p.strip()
        if not p:
            continue
        low = p.lower()
        if low in ("ctrl", "control"):
            out.append("Ctrl")
        elif low == "alt":
            out.append("Alt")
        elif low == "shift":
            out.append("Shift")
        elif low in ("win", "super", "meta"):
            out.append("Win")
        elif len(p) == 1:
            out.append(p.upper())
        else:
            out.append(p.upper() if low.startswith("f") and low[1:].isdigit() else p.capitalize())
    return "+".join(out)


def find_ffmpeg() -> str | None:
    """按优先级查找 ffmpeg：exe 同目录 -> 项目 bin -> PATH -> 常见安装位置。"""
    names = ["ffmpeg.exe", "ffmpeg"]
    candidates: list[Path] = []
    for n in names:
        candidates.append(BASE_DIR / n)
        candidates.append(BASE_DIR / "bin" / n)
    for n in names:
        p = shutil.which(n)
        if p:
            candidates.append(Path(p))
    candidates.append(Path(r"D:\ffmpeg\bin\ffmpeg.exe"))
    candidates.append(Path(r"C:\ffmpeg\bin\ffmpeg.exe"))
    for c in candidates:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return None


class Config:
    """轻量 JSON 配置对象。"""

    def __init__(self) -> None:
        self.data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if CONFIG_PATH.is_file():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if k in DEFAULTS:
                            self.data[k] = v
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CONFIG_PATH.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except OSError:
            pass

    def __getitem__(self, key: str):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value) -> None:
        self.data[key] = value

    def get(self, key: str, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def out_dir(self) -> Path:
        p = Path(str(self.data.get("out_dir") or DEFAULT_OUT_DIR)).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError:
            p = Path.home() / APP_NAME
            p.mkdir(parents=True, exist_ok=True)
        return p
