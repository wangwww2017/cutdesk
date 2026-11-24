"""一键打包脚本。

用法：
    python build.py                # 轻量包（依赖系统已有 ffmpeg）
    python build.py --with-ffmpeg  # 自带 ffmpeg，可独立分发（体积大幅增加）
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
FFMPEG_CANDIDATES = [
    Path(r"D:\ffmpeg\bin\ffmpeg.exe"),
    Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
]


def main() -> int:
    with_ffmpeg = "--with-ffmpeg" in sys.argv
    py = VENV_PY if VENV_PY.is_file() else Path(sys.executable)

    print("[1/3] 运行 PyInstaller …")
    code = subprocess.call(
        [str(py), "-m", "PyInstaller", "--noconfirm", "--clean", "build.spec"],
        cwd=str(ROOT),
    )
    if code != 0:
        print("打包失败")
        return code

    dist = ROOT / "dist" / "CutDesk"
    exe = dist / "CutDesk.exe"
    if not exe.is_file():
        print("未找到输出 exe：", exe)
        return 1

    if with_ffmpeg:
        print("[2/3] 复制 ffmpeg …")
        src = next((p for p in FFMPEG_CANDIDATES if p.is_file()), None)
        if src is None:
            which = shutil.which("ffmpeg")
            src = Path(which) if which else None
        if src is None:
            print("  未找到 ffmpeg，跳过（程序将使用系统 PATH 中的 ffmpeg）")
        else:
            bin_dir = dist / "bin"
            bin_dir.mkdir(exist_ok=True)
            shutil.copy2(src, bin_dir / "ffmpeg.exe")
            print(f"  已复制 {src} -> {bin_dir / 'ffmpeg.exe'}")
    else:
        print("[2/3] 跳过 ffmpeg（如需独立分发请加 --with-ffmpeg）")

    readme = ROOT / "README.md"
    if readme.is_file():
        shutil.copy2(readme, dist / "README.md")

    total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
    print("[3/3] 完成")
    print(f"  输出目录：{dist}")
    print(f"  总大小：{total / 1024 / 1024:.1f} MB")
    print(f"  可执行：{exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
