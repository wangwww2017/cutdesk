# CutDesk · 屏幕动图截取工具 / Screen Recorder

托盘常驻的轻量录屏小工具：一个快捷键框选屏幕区域，点两下鼠标就能同时得到一份带声音的 MP4 视频和一份可以直接发到聊天软件的表情 GIF。

A lightweight tray-resident screen recorder: one hotkey to select a region, two clicks to get both a narrated MP4 and a chat-ready GIF emoji.

**简体中文** ｜ [English](#english)

---

## 功能

- **托盘运行**：常驻系统托盘，不占任务栏，随用随录。
- **全局快捷键框选**：默认 `Ctrl+Alt+R`，在任何程序中按下即可唤出选区遮罩，拖拽框选后松开即完成选区。
- **贴边控制条**：选区外侧自动出现控制条，含「开始」「停止」「关闭」与实时计时，不会挡住、也不会被录入录制画面。
- **一次录制，双份产出**：
  - MP4：H.264 + AAC，带系统声音（可选麦克风），可直接播放或上传。
  - GIF：自动调色板优化，适配聊天软件表情，默认压到 5 MB 以内。
- **体积自适应**：GIF 超出体积预算时自动阶梯式降低分辨率 / 帧率 / 色数，直到符合预算，并给出提示。
- **录制中再次按快捷键**即可停止并保存，符合开关式直觉。

## 使用

1. 启动 `CutDesk.exe`，托盘出现图标。
2. 按 `Ctrl+Alt+R`（或点击托盘图标）。
3. 在屏幕上拖拽框选要录制的区域。
4. 在选区旁的控制条上点击「开始」，录制中显示红点与计时。
5. 点击「停止」，等待约 1～3 秒生成文件，完成后托盘弹出通知，点击通知可打开所在文件夹。

框选后可随时拖动控制条到顺手的位置；点「×」关闭当前选区，重新按快捷键可再次框选。

## 输出

默认保存到 `%USERPROFILE%\Videos\CutDesk`，文件名为 `CutDesk_年月日_时分秒.mp4` / `.gif`。

| 类型 | 默认参数 | 说明 |
| --- | --- | --- |
| MP4 | 30 fps · H.264 High · CRF 21 · AAC 96k | 中英文字边缘锐利，静止画面码率极低 |
| GIF | 12 fps · 480 px 宽 · 128 色 · 最长 10 秒 | 超长时间自动截取前段，完整内容仍在 MP4 中 |

体积参考（实测 960×540 静态桌面 5 秒）：MP4 约 200 KB，GIF 约 110 KB。
动态内容（窗口滚动、视频播放）会明显增大，属正常现象。

## 设置

托盘菜单 →「设置…」，可调整：

- 保存目录、全局快捷键
- 视频帧率（15 / 24 / 30 / 60）、画质 CRF、最大宽度、录音来源
- GIF 帧率 / 宽度 / 色数 / 最长时长 / 体积上限 / 是否生成 GIF

配置保存在 `%APPDATA%\CutDesk\config.json`。

## 依赖

- 屏幕采集：`mss`（GDI BitBlt），音频：`soundcard`（WASAPI loopback，直接抓系统输出，无需虚拟声卡）
- 编码：**ffmpeg**（libx264 + AAC）
- 界面：PySide6 / Qt 6

程序按以下顺序查找 ffmpeg：程序目录 → 程序目录 `bin\` → 系统 PATH → `D:\ffmpeg\bin` → `C:\ffmpeg\bin`。
若全部找不到，录制会失败并在托盘提示，可在设置中手动指定。

## 从源码运行

```bash
python -m venv .venv
.venv\Scripts\pip install PySide6 mss soundcard numpy
.venv\Scripts\python run.py
```

## 打包

```bash
python build.py                # 轻量版，依赖系统内已有 ffmpeg
python build.py --with-ffmpeg  # 内置 ffmpeg，可独立分发（体积大幅增加）
```

输出目录 `dist/CutDesk/`。使用 onedir 模式（本机 `--onefile` 存在 bootloader 残留问题）。

## 已知限制

- 选区限定在单个显示器内，不支持跨屏框选。
- 录制帧率受编码速度与 CPU 占用影响；采集跟不上时会重复上一帧以保持时间轴准确，画面表现为轻微卡顿而非音画不同步。
- 需要 Windows 10 及以上（依赖 WASAPI 与桌面合成）。

---

<a id="english"></a>

# English

A lightweight screen recorder that lives in the Windows system tray. Press one hotkey to select a region; two clicks later you have both a video with audio and a chat-ready GIF emoji.

[简体中文](#cutdesk--屏幕动图截取工具--screen-recorder) ｜ **English**

---

## Features

- **Tray-resident** — no taskbar clutter, ready whenever you need it.
- **Hotkey region capture** — default `Ctrl+Alt+R`, works from any application. A full-screen overlay appears; drag to select and release to confirm.
- **Control bar beside the selection** — Start / Stop / Close plus a live timer, placed outside the region so it never covers or gets captured into the recording.
- **One recording, two outputs**
  - MP4: H.264 + AAC with system audio (microphone optional), ready to play or upload.
  - GIF: palette-optimized for chat emoji, capped at 5 MB by default.
- **Adaptive GIF size** — resolution, frame rate, and color count are stepped down automatically until the GIF fits the budget, with a notice when it happens.
- **Press the hotkey again while recording** to stop and save — toggle behavior instead of hunting for a button.

## Usage

1. Launch `CutDesk.exe`; the tray icon appears.
2. Press `Ctrl+Alt+R` (or click the tray icon).
3. Drag on screen to choose the recording region.
4. Click **Start** on the control bar; a red dot and timer confirm recording.
5. Click **Stop** and wait 1–3 seconds for the files to be written. A tray notification appears — click it to open the output folder.

The control bar can be dragged anywhere convenient after selecting. Click **×** to dismiss the current selection, then press the hotkey again to select a new region.

## Output

Files are written to `%USERPROFILE%\Videos\CutDesk` as `CutDesk_YYYYMMDD_HHMMSS.mp4` / `.gif`.

| Type | Defaults | Notes |
| --- | --- | --- |
| MP4 | 30 fps · H.264 High · CRF 21 · AAC 96k | Sharp text edges; extremely low bitrate on static frames |
| GIF | 12 fps · 480 px wide · 128 colors · max 10 s | Longer clips keep only the first segment; the full version stays in the MP4 |

Measured reference (960×540 static desktop, 5 s): MP4 ≈ 200 KB, GIF ≈ 110 KB.
Motion content (scrolling, video playback) grows noticeably — that is expected.

## Settings

Tray menu → **Settings…** lets you adjust:

- Output folder and global hotkey
- Video frame rate (15 / 24 / 30 / 60), CRF quality, max width, audio source
- GIF frame rate / width / colors / max duration / size cap / whether to generate a GIF

Config is stored at `%APPDATA%\CutDesk\config.json`.

## Dependencies

- Capture: `mss` (GDI BitBlt)
- Audio: `soundcard` (WASAPI loopback — records system output directly, no virtual audio cable needed)
- Encoding: **ffmpeg** (libx264 + AAC)
- UI: PySide6 / Qt 6

ffmpeg is searched in this order: app folder → `bin\` inside the app folder → system PATH → `D:\ffmpeg\bin` → `C:\ffmpeg\bin`.
If none is found, recording fails with a tray warning; you can also point to it manually in Settings.

## Run from Source

```bash
python -m venv .venv
.venv\Scripts\pip install PySide6 mss soundcard numpy
.venv\Scripts\python run.py
```

## Build

```bash
python build.py                # slim build, relies on an ffmpeg already on the system
python build.py --with-ffmpeg  # bundles ffmpeg for standalone distribution (much larger)
```

Output goes to `dist/CutDesk/`. onedir mode is used — `--onefile` leaves a lingering bootloader process and `_MEI` temp folders on this machine.

## Known Limitations

- Selection is limited to a single monitor; cross-monitor regions are not supported.
- Frame rate depends on encoding speed and CPU load. When capture falls behind, the previous frame is repeated to keep the timeline accurate, so you see slight stutter rather than audio drift.
- Requires Windows 10 or later (WASAPI and desktop composition).
