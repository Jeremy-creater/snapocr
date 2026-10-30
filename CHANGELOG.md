# Changelog

[中文说明见下方](#中文)

## [0.2.0] - 2026-10-31

macOS support. The Windows features are unchanged.

Download `snapocr-0.2.0-macos-arm64.zip` from the Release, unzip it and drag `snapocr.app` to Applications: no Python needed. Needs an Apple Silicon Mac. The app has no Apple developer signature, so macOS blocks the first start; the README explains how to open it.

### Added

- Menu bar app for macOS with the same features as on Windows: `Option+1` to `Option+6`, `Cmd` shortcuts in the windows, and hotkeys that can be recorded with `Cmd`.
- Screenshots on every display at physical pixels, also over full-screen apps, with a prompt for the Screen Recording permission.
- Start at login on macOS, and a notice when snapocr is already running.
- Install from source on macOS (see the README).

## [0.1.0] - 2026-10-29

First public release. Windows 11 only; the user interface is in Chinese.

Download `snapocr-0.1.0-windows-x64.zip` from the Release, unzip it and run `snapocr.exe`: no Python needed. Or install from source with Python 3.12 (see the README).

### Added

- Tray app with global hotkeys, one job per hotkey, result on the clipboard:
  - `Alt+1` screenshot, with annotation (rectangle, ellipse, arrow, text, numbered markers, pen, mosaic, select / move / delete, undo), pin on screen, and save as a file.
  - `Alt+2` OCR with clean-up for Chinese / English text (spacing, punctuation, line joins).
  - `Alt+3` screenshot translation and `Alt+4` text translation in one translation window (Chinese ⇄ English, editable source text, target language switch).
  - `Alt+5` code OCR that keeps indentation; `Alt+6` table OCR that pastes as HTML and Markdown.
- OCR in-process with RapidOCR (PP-OCR models), no network.
- Translation through a local OpenAI-compatible server (Ollama by default); only `127.0.0.1` is ever contacted, Ollama cloud models are refused.
- Settings window: hotkeys, start with Windows, translation model, save folder, window style (light / dark glass, light solid, follow Windows), notification privacy, debug mode.
- Multiple monitors with different scaling.
- Config file in `%APPDATA%\snapocr\config.toml` (created on first start), logs in `%LOCALAPPDATA%\snapocr`; `--config`, `SNAPOCR_CONFIG` and `SNAPOCR_RUNTIME_DIR` override them.

---

## 中文

## [0.2.0] - 2026-10-31

支持 macOS。Windows 上的功能没有变化。

从 Release 下载 `snapocr-0.2.0-macos-arm64.zip`，解压后把 `snapocr.app` 拖进“应用程序”，不用装 Python。需要 Apple 芯片的 Mac。程序没有 Apple 开发者签名，第一次打开会被 macOS 拦下，打开方法见 README。

- macOS 菜单栏程序，功能和 Windows 一样：`Option+1` 到 `Option+6`，窗口里用 `Cmd` 快捷键，录热键时可以用 `Cmd`。
- 所有显示器都按物理像素截图，别的程序全屏时也能截，缺屏幕录制权限时会提示。
- macOS 开机自启动；重复启动时提示已在运行。
- 可以在 macOS 上从源码安装（见 README）。

## [0.1.0] - 2026-10-29

第一个公开版本。只支持 Windows 11，界面只有中文。

从 Release 下载 `snapocr-0.1.0-windows-x64.zip`，解压后运行 `snapocr.exe`，不用装 Python。也可以用 Python 3.12 从源码安装（见 README）。

- 托盘常驻，全局热键，一个热键做一件事，结果进剪贴板：
  - `Alt+1` 截图，可以标注（矩形、椭圆、箭头、文字、序号、画笔、马赛克、选中移动删除、撤销）、贴图、另存为文件。
  - `Alt+2` OCR，中英文后处理（空格、标点、断行合并）。
  - `Alt+3` 截图翻译、`Alt+4` 文字翻译，共用一个翻译窗口（中英互译，可改原文，可切目标语言）。
  - `Alt+5` 代码 OCR，保留缩进；`Alt+6` 表格 OCR，粘贴成 HTML 表格和 Markdown。
- OCR 在程序内部运行（RapidOCR，PP-OCR 模型），不联网。
- 翻译走本机的 OpenAI 兼容接口（默认 Ollama），只访问 `127.0.0.1`，拒绝 Ollama 云模型。
- 设置窗口：热键、开机自启动、翻译模型、保存目录、窗口风格（浅色 / 深色毛玻璃、浅色实底、跟随系统）、通知隐私、debug 模式。
- 支持多显示器、不同缩放。
- 配置文件在 `%APPDATA%\snapocr\config.toml`（第一次启动时生成），日志在 `%LOCALAPPDATA%\snapocr`；可用 `--config`、`SNAPOCR_CONFIG`、`SNAPOCR_RUNTIME_DIR` 改位置。
