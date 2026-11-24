"""无界面录制管线自测：python tools/test_record.py [秒数] [宽] [高]"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config, find_ffmpeg  # noqa: E402
from app.recorder import Recorder  # noqa: E402


def main() -> int:
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    w = int(sys.argv[2]) if len(sys.argv) > 2 else 960
    h = int(sys.argv[3]) if len(sys.argv) > 3 else 540

    cfg = Config()
    print("ffmpeg:", find_ffmpeg())
    print("outdir:", cfg.out_dir())
    print("audio :", cfg.get("audio_source"))

    rec = Recorder((120, 120, w, h), cfg)
    t0 = time.perf_counter()
    if not rec.start():
        print("启动失败")
        return 1
    print(f"录制中 {secs}s ...")
    while time.perf_counter() - t0 < secs:
        time.sleep(0.2)
        print(f"\r  elapsed={rec.elapsed():5.2f}s frames={rec._frames}", end="", flush=True)
    print()
    t1 = time.perf_counter()
    res = rec.stop()
    print(f"停止耗时 {time.perf_counter() - t1:.2f}s")
    print("ok =", res.ok)
    print("summary =", res.summary)
    print("mp4 =", res.mp4, res.mp4_size)
    print("gif =", res.gif, res.gif_size)
    print("frames =", res.frames, "duration =", round(res.duration, 2))
    print("error =", res.error)
    print("warnings =", res.warnings)
    return 0 if res.ok else 2


if __name__ == "__main__":
    sys.exit(main())
