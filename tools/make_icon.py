"""生成 app.ico（多尺寸）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.icons import app_icon, app_icon_pixmap  # noqa: E402


def main() -> None:
    app = QApplication([])
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)

    # 各尺寸单独 PNG 便于检查
    for size in (16, 32, 48, 256):
        app_icon_pixmap(size).save(str(out / f"icon_{size}.png"))

    # ICO：以 256 为主图，Windows 会缩放
    pm = app_icon_pixmap(256)
    ok = pm.save(str(out / "app.ico"), "ICO")
    print("ico saved:", ok, (out / "app.ico").stat().st_size if (out / "app.ico").exists() else "-")

    pm32 = app_icon_pixmap(32)
    pm32.save(str(out / "app32.ico"), "ICO")
    print("out dir:", out)


if __name__ == "__main__":
    main()
