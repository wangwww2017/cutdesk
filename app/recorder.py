"""录制与编码核心。

流程：
  1. 采集线程用 mss 抓取选区画面 -> BGRA 原始帧 -> 实时喂给 ffmpeg 编码成无声 MP4（临时）
  2. 音频线程用 WASAPI loopback / 麦克风录制 -> 48kHz 16bit WAV
  3. 停止后用 ffmpeg 以 -c:v copy 无损合流，速度接近瞬时
  4. 再由 MP4 生成调色板优化的 GIF，并按体积预算自适应降级

时间轴处理：采集帧率受 CPU 影响不可能严格恒定，因此按真实流逝时间补帧
（重复上一帧），保证 MP4 的时间轴等于真实耗时，从而与音频同步。
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import find_ffmpeg

CREATE_NO_WINDOW = 0x08000000
AUDIO_RATE = 48000
AUDIO_CHANNELS = 2


@dataclass
class RecordResult:
    ok: bool = False
    mp4: Path | None = None
    gif: Path | None = None
    duration: float = 0.0
    mp4_size: int = 0
    gif_size: int = 0
    frames: int = 0
    has_audio: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.ok:
            return self.error or "录制失败"
        parts = [f"时长 {self.duration:.1f}s"]
        parts.append(f"MP4 {_fmt_size(self.mp4_size)}")
        if self.gif:
            parts.append(f"GIF {_fmt_size(self.gif_size)}")
        if not self.has_audio:
            parts.append("无音轨")
        return " · ".join(parts)


def _fmt_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _run_ffmpeg(ffmpeg: str, args: list[str], timeout: float = 600) -> tuple[int, str]:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args]
    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, "ffmpeg 执行超时"
    except OSError as exc:
        return -1, f"无法调用 ffmpeg：{exc}"
    err = proc.stderr.decode("utf-8", "replace").strip()
    return proc.returncode, err


class Recorder:
    """一次录制会话。"""

    def __init__(self, region: tuple[int, int, int, int], config) -> None:
        self.x, self.y, self.w, self.h = region
        self.cfg = config
        self.ffmpeg = str(config.get("ffmpeg_path") or "") or (find_ffmpeg() or "")
        self.fps = max(5, int(config.get("fps") or 30))
        self.max_seconds = max(5, int(config.get("max_seconds") or 1800))

        self.tmp_dir = Path(config.out_dir()) / ".tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.token = uuid.uuid4().hex[:8]
        self.raw_video = self.tmp_dir / f"video_{self.token}.mp4"
        self.audio_path = self.tmp_dir / f"audio_{self.token}.wav"
        self.mic_path = self.tmp_dir / f"mic_{self.token}.wav"

        self._stop_evt = threading.Event()
        self._vthread: threading.Thread | None = None
        self._athread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None

        self._t_video_start = 0.0
        self._frames = 0
        self._v_error = ""
        self._a_error = ""
        self._audio_ok = False
        self._audio_started = 0.0
        self._started_at = 0.0
        self._running = False

    # ------------------------------------------------------------------ 状态
    @property
    def running(self) -> bool:
        return self._running

    def elapsed(self) -> float:
        if not self._running:
            return 0.0
        return max(0.0, time.perf_counter() - self._started_at)

    # ------------------------------------------------------------------ 启动
    def start(self) -> bool:
        if self._running:
            return False
        if not self.ffmpeg:
            self._v_error = "未找到 ffmpeg，可在设置中指定路径"
            return False

        vf_parts: list[str] = []
        max_w = int(self.cfg.get("mp4_max_width") or 0)
        if max_w and self.w > max_w:
            vf_parts.append(f"scale={max_w}:-2:flags=lanczos")
        vf_parts.append("format=yuv420p")

        args = [
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{self.w}x{self.h}",
            "-framerate", str(self.fps),
            "-i", "pipe:0",
            "-an",
            "-c:v", "libx264",
            "-preset", str(self.cfg.get("mp4_preset") or "medium"),
            "-crf", str(int(self.cfg.get("mp4_crf") or 21)),
            "-profile:v", "high",
            "-g", str(self.fps * 2),
            # 高质量色度下采样，屏幕上的彩色边缘 / 渐变明显更干净
            "-sws_flags", "accurate_rnd+full_chroma_int+bicubic",
            "-vf", ",".join(vf_parts),
            str(self.raw_video),
        ]
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            self._v_error = f"启动 ffmpeg 失败：{exc}"
            return False

        self._stop_evt.clear()
        self._frames = 0
        self._running = True
        self._started_at = time.perf_counter()
        self._t_video_start = self._started_at

        self._vthread = threading.Thread(target=self._video_loop, name="cd-video", daemon=True)
        self._vthread.start()

        source = str(self.cfg.get("audio_source") or "system")
        if source in ("system", "mic", "both"):
            self._athread = threading.Thread(
                target=self._audio_loop, args=(source,), name="cd-audio", daemon=True
            )
            self._athread.start()
        return True

    # ------------------------------------------------------------- 视频采集
    def _video_loop(self) -> None:
        try:
            import mss
        except Exception as exc:  # pragma: no cover
            self._v_error = f"屏幕采集模块不可用：{exc}"
            return

        monitor = {"left": self.x, "top": self.y, "width": self.w, "height": self.h}
        frame_bytes = self.w * self.h * 4
        proc = self._proc
        if proc is None or proc.stdin is None:
            self._v_error = "视频编码进程未就绪"
            return

        t0 = 0.0
        sent = 0
        last_raw: bytes | None = None
        deadline = self.max_seconds

        try:
            with mss.mss() as sct:
                while not self._stop_evt.is_set():
                    now = time.perf_counter()
                    if t0 == 0.0:
                        t0 = now
                        self._t_video_start = now
                    if now - t0 >= deadline:
                        break

                    due = int((now - t0) * self.fps)
                    if last_raw is not None and due <= sent:
                        # 还没到下一帧的时间点，短暂休眠避免空转
                        wait = (sent + 1) / self.fps - (now - t0)
                        time.sleep(min(max(wait, 0.001), 0.02))
                        continue

                    try:
                        shot = sct.grab(monitor)
                        raw = shot.raw
                        if len(raw) != frame_bytes:
                            raw = bytes(shot.bgra)
                    except Exception as exc:
                        self._v_error = f"抓屏失败：{exc}"
                        break

                    last_raw = raw
                    now = time.perf_counter()
                    due = int((now - t0) * self.fps) + 1
                    need = due - sent
                    if need <= 0:
                        need = 1
                    # 落后过多时丢弃积压，避免雪崩（画面会跳，但时间轴保持真实）
                    if need > self.fps * 2:
                        sent = due - self.fps
                        need = self.fps
                    try:
                        for _ in range(need):
                            proc.stdin.write(raw)
                        sent += need
                        self._frames = sent
                    except (BrokenPipeError, OSError, ValueError):
                        break
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
            stderr = b""
            try:
                if proc.stderr:
                    stderr = proc.stderr.read()
            except OSError:
                pass
            if not self._v_error and proc.returncode not in (0, None):
                msg = stderr.decode("utf-8", "replace").strip()
                self._v_error = msg.splitlines()[-1] if msg else f"编码进程退出码 {proc.returncode}"
            if not last_raw and not self._v_error:
                self._v_error = "没有捕获到任何画面"

    # ------------------------------------------------------------- 音频采集
    def _audio_loop(self, source: str) -> None:
        try:
            import soundcard as sc
        except Exception as exc:  # pragma: no cover
            self._a_error = f"音频模块不可用：{exc}"
            return

        targets: list[tuple[str, object]] = []
        try:
            if source in ("system", "both"):
                spk = sc.default_speaker()
                if spk is not None:
                    targets.append(("system", sc.get_microphone(str(spk.name), include_loopback=True)))
            if source in ("mic", "both"):
                mic = sc.default_microphone()
                if mic is not None:
                    targets.append(("mic", mic))
        except Exception as exc:
            self._a_error = f"未找到录音设备：{exc}"
            return

        if not targets:
            self._a_error = "没有可用的录音设备"
            return

        self._audio_started = time.perf_counter()
        pad_seconds = max(0.0, min(self._audio_started - self._t_video_start, 1.5))

        threads: list[threading.Thread] = []
        results: dict[str, bool] = {}

        def worker(kind: str, dev, path: Path) -> None:
            results[kind] = self._record_device(dev, path, pad_seconds)

        for kind, dev in targets:
            path = self.audio_path if kind == "system" else self.mic_path
            th = threading.Thread(target=worker, args=(kind, dev, path), daemon=True)
            th.start()
            threads.append(th)
        for th in threads:
            th.join(timeout=10)
        self._audio_ok = any(results.values())

    def _record_device(self, dev, path: Path, pad_seconds: float) -> bool:
        try:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(AUDIO_RATE)
                if pad_seconds > 0.002:
                    silent = np.zeros((int(pad_seconds * AUDIO_RATE), AUDIO_CHANNELS), dtype=np.int16)
                    wf.writeframes(silent.tobytes())
                with dev.recorder(samplerate=AUDIO_RATE, channels=AUDIO_CHANNELS) as rec:
                    block = max(256, AUDIO_RATE // 20)  # 50ms
                    while not self._stop_evt.is_set():
                        data = rec.record(numframes=block)
                        if data is None or len(data) == 0:
                            continue
                        pcm = np.clip(data, -1.0, 1.0)
                        pcm = (pcm * 32767.0).astype(np.int16)
                        if pcm.shape[1] < AUDIO_CHANNELS:
                            pcm = np.repeat(pcm, AUDIO_CHANNELS, axis=1)[:, :AUDIO_CHANNELS]
                        elif pcm.shape[1] > AUDIO_CHANNELS:
                            pcm = pcm[:, :AUDIO_CHANNELS]
                        wf.writeframes(pcm.tobytes())
            return True
        except Exception as exc:
            self._a_error = f"录音失败：{exc}"
            return False

    # --------------------------------------------------------------- 停止
    def stop(self) -> RecordResult:
        """停止录制并完成编码，返回结果。耗时通常在 1~3 秒。"""
        if not self._running and not self._vthread:
            return RecordResult(error="当前没有进行中的录制")

        self._running = False
        self._stop_evt.set()
        duration = max(0.0, time.perf_counter() - self._started_at)
        self._started_at = 0.0

        if self._vthread:
            self._vthread.join(timeout=90)
        if self._athread:
            self._athread.join(timeout=15)

        if self._v_error and not self.raw_video.is_file():
            self._cleanup()
            return RecordResult(error=self._v_error, duration=duration)

        result = RecordResult(ok=True, duration=duration, frames=self._frames)
        result.has_audio = self._audio_ok
        if not self._audio_ok and self._a_error:
            result.warnings.append(self._a_error)

        final_mp4 = self._finalize(duration, result)
        result.mp4 = final_mp4

        if final_mp4 and final_mp4.is_file():
            result.mp4_size = final_mp4.stat().st_size
            if bool(self.cfg.get("make_gif", True)):
                gif, warns = self._make_gif(final_mp4, duration)
                result.gif = gif
                if gif and gif.is_file():
                    result.gif_size = gif.stat().st_size
                result.warnings.extend(warns)
        else:
            result.ok = False
            result.error = self._v_error or "视频编码失败"

        self._cleanup()
        return result

    def _finalize(self, duration: float, result: RecordResult) -> Path | None:
        if not self.raw_video.is_file():
            return None
        out_dir = self.cfg.out_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        final = out_dir / f"CutDesk_{stamp}.mp4"
        idx = 1
        while final.exists():
            final = out_dir / f"CutDesk_{stamp}_{idx}.mp4"
            idx += 1

        audio_inputs: list[Path] = []
        if self.audio_path.is_file() and self.audio_path.stat().st_size > 64:
            audio_inputs.append(self.audio_path)
        if self.mic_path.is_file() and self.mic_path.stat().st_size > 64:
            audio_inputs.append(self.mic_path)

        if not audio_inputs:
            # 无音轨，直接移动到输出目录
            try:
                shutil.move(str(self.raw_video), str(final))
                return final
            except OSError as exc:
                result.error = f"保存失败：{exc}"
                return None

        args: list[str] = ["-i", str(self.raw_video)]
        for a in audio_inputs:
            args += ["-i", str(a)]
        args += ["-map", "0:v:0"]
        if len(audio_inputs) == 1:
            args += ["-map", "1:a:0"]
        else:
            args += [
                "-filter_complex",
                "[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[aout]",
                "-map", "[aout]",
            ]
        args += [
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", str(self.cfg.get("audio_bitrate") or "96k"),
            "-ar", str(AUDIO_RATE),
            "-ac", str(AUDIO_CHANNELS),
            "-movflags", "+faststart",
            "-shortest",
            str(final),
        ]
        code, err = _run_ffmpeg(self.ffmpeg, args, timeout=120)
        if code != 0 or not final.is_file():
            result.error = f"合流失败：{err[:200]}" if err else "合流失败"
            result.has_audio = False
            try:
                shutil.move(str(self.raw_video), str(final))
                return final
            except OSError:
                return None
        return final

    # ----------------------------------------------------------------- GIF
    def _make_gif(self, mp4: Path, duration: float) -> tuple[Path | None, list[str]]:
        warnings: list[str] = []
        gif_path = mp4.with_suffix(".gif")
        max_bytes = int(float(self.cfg.get("gif_max_mb") or 5.0) * 1024 * 1024)
        max_sec = float(self.cfg.get("gif_max_seconds") or 10)
        clip = min(duration, max_sec) if duration > 0 else max_sec
        if duration > max_sec + 0.3:
            warnings.append(f"GIF 仅截取前 {max_sec:.0f} 秒（完整内容在 MP4 中）")

        base_w = int(self.cfg.get("gif_width") or 480)
        base_fps = int(self.cfg.get("gif_fps") or 12)
        base_colors = int(self.cfg.get("gif_colors") or 128)

        # 体积自适应降级阶梯
        plan = [
            (base_w, base_fps, base_colors),
            (max(320, int(base_w * 0.85)), max(8, base_fps - 2), max(96, base_colors - 32)),
            (max(320, int(base_w * 0.7)), max(8, base_fps - 4), 96),
            (320, 8, 64),
            (280, 8, 48),
        ]
        best: Path | None = None
        for idx, (w, fps, colors) in enumerate(plan):
            tmp = gif_path.with_name(gif_path.stem + f"_try{idx}.gif")
            filt = (
                f"[0:v]fps={fps},scale={w}:-1:flags=lanczos,split[a][b];"
                f"[a]palettegen=max_colors={colors}:stats_mode=diff[p];"
                f"[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"
            )
            args = [
                "-t", f"{clip:.3f}",
                "-i", str(mp4),
                "-filter_complex", filt,
                "-loop", "0",
                str(tmp),
            ]
            code, err = _run_ffmpeg(self.ffmpeg, args, timeout=300)
            if code != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
                if err:
                    warnings.append(f"GIF 生成失败：{err.splitlines()[-1][:120]}")
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            size = tmp.stat().st_size
            if best and best.is_file():
                try:
                    best.unlink()
                except OSError:
                    pass
            best = tmp
            if size <= max_bytes:
                break
            warnings.append(
                f"GIF 体积 {_fmt_size(size)} 超出 {max_bytes / 1024 / 1024:.1f} MB 预算，自动降低画质重试"
            )

        if best is None:
            return None, warnings
        try:
            shutil.move(str(best), str(gif_path))
        except OSError as exc:
            return None, warnings + [f"GIF 保存失败：{exc}"]
        if gif_path.stat().st_size > max_bytes:
            warnings.append(
                f"已降至最低画质，GIF 仍为 {_fmt_size(gif_path.stat().st_size)}"
            )
        return gif_path, warnings

    # ------------------------------------------------------------- 清理
    def _cleanup(self) -> None:
        for p in (self.raw_video, self.audio_path, self.mic_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            if self.tmp_dir.is_dir() and not any(self.tmp_dir.iterdir()):
                self.tmp_dir.rmdir()
        except OSError:
            pass
