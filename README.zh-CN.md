# snapocr

[English](README.md)

Windows 托盘常驻的截图工具：**一个热键做一件事，结果直接进剪贴板。** 框选截图、OCR、翻译，全程在本机完成。OCR 在程序内部运行（RapidOCR，PP-OCR 模型）；翻译调用你自己电脑上的模型服务（默认 Ollama）。snapocr 只访问 `127.0.0.1`。

这是我（Jeremy）和 AI 编程助手（[Claude Code](https://claude.com/claude-code)）一起做的第一款软件，从第一天起就是先写测试再写代码。

> 目前界面**只有中文**。

## 截图

| 截图标注（`Alt+1`） | 翻译窗口（`Alt+3` / `Alt+4`） | 托盘菜单 |
|---|---|---|
| ![截图标注工具栏](docs/images/annotate.png) | ![翻译窗口](docs/images/translate.png) | ![托盘菜单](docs/images/tray-menu.png) |

## 功能

| 热键 | 作用 |
|---|---|
| `Alt+1` | 截图 → 剪贴板。复制前可以标注（矩形、椭圆、箭头、文字、序号、画笔、马赛克、撤销），也可以钉在屏幕上，或另存为图片文件 |
| `Alt+2` | 截图 → OCR → 整理过的文字进剪贴板（中英文空格、标点、断行合并） |
| `Alt+3` | 截图 → OCR → 翻译窗口（中英互译）；译文进剪贴板，原文识别错了可以改了再翻 |
| `Alt+4` | 打开翻译窗口，翻译手动输入或粘贴的文字 |
| `Alt+5` | 代码 OCR：保留缩进 |
| `Alt+6` | 表格 OCR：粘进 Excel / Word 是表格（HTML），粘进编辑器是 Markdown |

所有热键都能在**设置**（托盘菜单 → 设置…）里改；设置里还有开机自启动、翻译模型、截图保存目录、窗口风格（浅色 / 深色毛玻璃、浅色实底、跟随系统）。支持缩放比例不同的多显示器。

## 下载就能用（不用装 Python）

1. 打开 [Releases 页面](https://github.com/Jeremy-creater/snapocr/releases/latest)，下载 `snapocr-<版本>-windows-x64.zip`（约 120 MB）。
2. 解压到任意位置，比如 `D:\Apps`，会得到一个 `snapocr` 文件夹。
3. 双击文件夹里的 `snapocr.exe`。不会弹出窗口，图标在右下角托盘里（可能藏在 `^` 里）。

第一次运行时，Windows 可能提示 **“Windows 已保护你的电脑”**。这是因为 snapocr 没有付费的代码签名，Windows 还不认识它。点 **“更多信息”**，再点 **“仍要运行”**。

截图和识别文字马上就能用。翻译要另装 Ollama 和模型，见 [准备翻译](#准备翻译可选)。

升级：退出 snapocr，把新版本解压覆盖旧文件夹，设置会保留。卸载：先在设置里关掉“开机自启动”，退出 snapocr，再删除 `snapocr` 文件夹、`%APPDATA%\snapocr` 和 `%LOCALAPPDATA%\snapocr`。

## 系统要求

- Windows 11（64 位）。Windows 10 应该能用，但没测过；毛玻璃风格需要 Windows 11，其他系统自动改用实底。
- 约 300 MB 硬盘。OCR 模型已包含在内，运行时不下载任何东西。
- 只有翻译需要：[Ollama](https://ollama.com/)（或其他在 `127.0.0.1` 上提供 OpenAI 兼容接口的服务，如 LM Studio、llama.cpp server）。截图和 OCR 不需要。
- 从源码安装（见下）还需要 Python **3.12**（只能是 3.12，暂不支持 3.13），Python 依赖约占 500 MB。

## 从源码安装（Python 3.12）

给开发者，或者更想用 Python 包而不是 zip 的人。用 [uv](https://docs.astral.sh/uv/)：

```powershell
uv tool install --python 3.12 git+https://github.com/Jeremy-creater/snapocr
uv tool update-shell   # 只需一次，让 snapocr 进 PATH（之后开一个新终端）
snapocr
```

上面装的是 `main` 上的最新代码。要装固定版本，在地址后面加标签：`git+https://github.com/Jeremy-creater/snapocr@v0.1.0`（见 [CHANGELOG.md](CHANGELOG.md) 和 Releases 页面）。

或者用 pip 装进一个虚拟环境：

```powershell
py -3.12 -m venv %USERPROFILE%\snapocr-env
%USERPROFILE%\snapocr-env\Scripts\python.exe -m pip install git+https://github.com/Jeremy-creater/snapocr
%USERPROFILE%\snapocr-env\Scripts\snapocr.exe
```

`snapocr` 启动后没有控制台窗口，图标在系统托盘里。同一时间只运行一个。要开机自动启动，在设置里勾选“开机自启动”。

## 准备翻译（可选）

1. 安装并启动 [Ollama](https://ollama.com/)。
2. 准备翻译模型。snapocr 默认用 `hy-mt2:7b`，即腾讯的 HY-MT2-7B 翻译模型（GGUF），用仓库里的 Modelfile 导入：
   ```powershell
   # 先把 docs/hy-mt2-7b.Modelfile 里 FROM 一行改成你的 .gguf 文件路径，然后：
   ollama create hy-mt2:7b -f docs/hy-mt2-7b.Modelfile
   ```
   Ollama 里的其他对话模型也可以用，比如 `ollama pull qwen2.5:7b`，然后在设置里选（翻译模型），或者改配置文件的 `model`。
3. 模型有各自的许可证，下载前先看清楚。

Ollama 没启动时，翻译窗口会提示；OCR 和截图照常工作。

## 配置和文件位置

| 内容 | 位置 |
|---|---|
| 配置文件 | `%APPDATA%\snapocr\config.toml`，第一次启动时自动生成，带中文注释。常用选项在设置窗口里；其余的在这个文件里，改完重启生效 |
| 日志和 debug 输出 | `%LOCALAPPDATA%\snapocr` |

可以覆盖：`snapocr --config 路径`，或者环境变量 `SNAPOCR_CONFIG`（配置文件）、`SNAPOCR_RUNTIME_DIR`（日志和 debug 输出的目录，必须是绝对路径）。

## 隐私

- 全部在本机运行。OCR 在 snapocr 内部离线完成；翻译请求只发往 `http://127.0.0.1:<端口>`，其他地址和 Ollama 云模型一律拒绝。
- 截图和识别出的文字只在内存里。只有你点了“保存”，或者开了 debug 模式（`[debug] enabled = true`，把每次的截图和文字写进日志目录下的 `debug` 文件夹）时才会写硬盘。
- 日志里从不写识别出的文字。

## 开发

需求在 [`docs/PRD.md`](docs/PRD.md)，工作规则在 [`CLAUDE.md`](CLAUDE.md)。项目用 Claude Code 和 tdd-guardian 插件按 TDD 开发。

```powershell
git clone https://github.com/Jeremy-creater/snapocr
cd snapocr
uv venv --python 3.12
.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
```

测试分车道：

| 车道 | 命令 | 需要 |
|---|---|---|
| unit | `python -m pytest -m "not integration and not engine and not perf and not gui"` | 什么都不需要（Qt 用 offscreen） |
| engine | `python -m pytest -m "engine and not perf and not gui"` | 真实的 OCR 模型（随 `rapidocr` 安装） |
| gui | `python -m pytest -m "gui and not perf" --qt-desktop` | 真实的 Windows 桌面；会注册测试用热键、动剪贴板 |
| integration | `python -m pytest -m "integration and not perf"` | Ollama 在运行，并且有配置里的模型 |

CI 在 Windows 上跑 unit 和 engine 两条车道。

## 许可证

[MIT](LICENSE)。第三方组件及其许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
