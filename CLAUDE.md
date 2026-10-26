# snapocr — 项目规则

个人定制的托盘常驻 GUI 截图工具（截图 / OCR / 翻译，结果进剪贴板）。独立运行，不依赖 Umi-OCR：OCR 引擎内置（RapidOCR，进程内），翻译调用本地模型（默认 Ollama）。

需求见 `docs/PRD.md`。本文件只规定"怎么做"，不规定"做什么"。

## 文档分工与变更顺序

- `docs/PRD.md`：范围、需求、验收标准。需求变化先改 PRD。
- `CLAUDE.md`：工作规则。规则变化先改本文件，再改代码。
- `.claude/tdd-guardian/`：TDD 计划、测试矩阵、审计结果（由 tdd-guardian 生成；`config.json`、计划和矩阵提交进 Git，`state.json` / `receipts.json` 不提交）。
- 文档用中文；代码、注释、命令、路径、配置键用英文。

## 路径

| 东西 | 位置 |
|---|---|
| 源码 | `D:\LLM\workspace\snapocr`（用户指定，例外于全局规则的 `D:\Sync\Projects`） |
| 虚拟环境 | `D:\DevLocal\envs\snapocr` |
| 用户配置 | `D:\LLM\workspace\snapocr\config.local.toml`（不进 Git；不要放进 venv，重建环境会被删） |
| 运行数据（日志、debug 截图） | `D:\DevLocal\runtime\snapocr`（只在需要写日志时创建） |
| 本地模型（gguf、Ollama） | `D:\LLM`（只读使用；导入或下载模型前先问 Jeremy） |

## 环境

- Python 3.12 only，不用 conda。
- 创建环境：`uv venv D:\DevLocal\envs\snapocr --python 3.12`
- 安装：`uv pip install --python D:\DevLocal\envs\snapocr\Scripts\python.exe -e ".[dev]"`（或激活后 `python -m pip install -e ".[dev]"`）
- **先激活环境，再在同一个终端里启动 `claude`**，否则 tdd-guardian 会报 `runner-missing`。
- 新增运行时依赖前，先在 PRD 或计划里写明理由。

## 架构边界

- **不依赖 Umi-OCR**，不 fork、不调用它。截图由 snapocr 自己实现（PRD §5）。
- OCR 引擎放在适配层后面（`snapocr.engines`），对外只暴露引擎无关的结果结构；业务代码不 import `rapidocr`，便于以后换 PaddleOCR 或 VLM。
- OCR 运行时不联网：模型文件在本地，只读本地路径。
- 翻译后端放在适配层后面（`snapocr.translators`），只走 OpenAI 兼容接口（`POST {base_url}/v1/chat/completions`），默认 `http://127.0.0.1:11434`（Ollama）。
- **只访问 `127.0.0.1`。** 任何外网请求（云端模型等）必须先改 PRD，并做成默认关闭的显式开关。
- GUI 层（`snapocr.gui`，PySide6）只做界面和 I/O（托盘、热键、遮罩、浮窗、剪贴板），不含业务规则；流程编排放 `snapocr.actions`，可用假引擎测试。
- 纯逻辑（后处理、翻译方向判断、热键字符串解析、坐标换算、配置解析）与 I/O（HTTP、剪贴板、截图、热键注册）分开，纯逻辑必须可在无 OCR 模型、无翻译服务、无 GUI 的环境下测试。
- 全局热键用 Win32 `RegisterHotKey`（`ctypes`），不引入第三方热键库。
- 包结构：`src/snapocr/`（src layout）。

## TDD 规则

使用 tdd-guardian 插件（用户级已安装）。

1. **先红后绿**：任何新行为先写一个因断言失败而变红的测试，再写实现。
2. **修 bug 先写复现测试**，看到红再改代码。
3. **不许为了变绿而放松已有断言**。需求变了，先改 PRD，再改测试。
4. 补测试时发现的可疑行为记入计划的 `Deferred`，不顺手改。
5. 一个工作项（WI）= 一轮红-绿-重构 = 一次提交。
6. 禁止"接线测试"（只断言 mock 被调用）。外部依赖用假实现，但要断言真实输出。

### 车道（lanes）

| 车道 | 内容 | 命令 | 触发 |
|---|---|---|---|
| `unit` | 纯逻辑 + 假实现 + offscreen Qt，不需要任何外部服务，不加载 OCR 模型 | `python -m pytest -m "not integration and not engine and not perf and not gui" --cov=snapocr --cov-branch --cov-report=json` | taskCompleted、commit |
| `engine` | 进程内真实 RapidOCR 模型（`@pytest.mark.engine`），不需要外部服务、不联网 | `python -m pytest -m "engine and not perf and not gui" --cov=snapocr --cov-branch --cov-report=json:coverage-engine.json` | taskCompleted、commit |
| `gui` | 真实 Windows 桌面（`@pytest.mark.gui`）：托盘、全局热键、屏幕截取、DPI | 见下 | manual |
| `integration` | 连真实运行中的本地模型服务（Ollama，`@pytest.mark.integration`） | `python -m pytest -m "integration and not perf"` | manual |

- 覆盖率模式：`no-decrease`。
- 初期不开 `blockCommitWithoutFreshGate`；熟悉流程后再开。
- integration 测试在 Ollama 未运行或模型未导入时必须**明确失败并提示**，不得静默跳过后报绿。
- engine 测试在模型文件缺失或损坏时必须**明确失败并提示**，不能跳过。归为独立车道的依据：冒烟实测加载 + 识别约 1–2 s，不需要外部服务，适合每次提交跑，但不该混进毫秒级的 unit。
- hypothesis 样例数（2026-10-26 Jeremy 定）：`tests/conftest.py` 注册两个 profile，默认加载 `unit`（`max_examples=50`，所有车道都用它），`thorough`（`max_examples=200`）只手动跑：在任一车道命令后加 `--hypothesis-profile=thorough`。测试里显式写了 `max_examples` 的不受 profile 影响。unit 车道（带 coverage）再超过 45 s 时考虑 `pytest-xdist`。
- `perf`（`@pytest.mark.perf`，延迟实测）只能手动跑：`python -m pytest -m perf -s`，不参与任何 gate。同时带 `integration` 和 `perf` 的测试（翻译延迟）也只能手动跑，同样需要 Ollama。
- `gui`（`@pytest.mark.gui`，需要真实 Windows 桌面）只能手动跑：`python -m pytest -m gui --qt-desktop --cov=snapocr.gui.platform --cov-config=coverage-gui.toml --cov-branch --cov-report=json:coverage-gui.json`。没有 `--qt-desktop` 时 `gui` 用例必须**明确失败并提示**，不能跳过。

### GUI 测试方式（2026-10-26 Jeremy 定）

- 用 `pytest-qt`（只是开发依赖）。unit 车道里 Qt 一律用 `QT_QPA_PLATFORM=offscreen`，由 `tests/conftest.py` 在创建 `QApplication` 之前设置；不弹真实窗口，不碰真实剪贴板以外的桌面状态。
- offscreen 下测窗口和控件的**真实状态**（文字、可见性、几何位置、按钮可用性）和**真实信号**（`qtbot.waitSignal`），不 mock Qt 类，不断言"某方法被调用"。
- 依赖真实桌面的部分（托盘图标显示、`RegisterHotKey` 全局热键、真实屏幕截取、多显示器 / DPI、单实例互斥）集中放在 `snapocr.gui.platform` 下的薄封装里，只由 `gui` 车道覆盖；业务判断不得放进这些封装。M2 计划要列出这些模块。
- 覆盖率分工（2026-10-26，M2 计划 D11）：commit / taskCompleted 门禁只合并 unit 和 engine 的覆盖率，所以 `pyproject.toml` 让这两条车道不统计 `snapocr.gui.platform`（`omit`）。platform 的 100% 行和分支覆盖由 gui 车道负责（`coverage-gui.toml`，不 omit）：每个改动 platform 的 WI 提交前手动跑一次 gui 车道，把覆盖率结果写进计划。不用 `# pragma: no cover`。
- `snapocr.gui` 其余代码和 `snapocr.actions` 必须由 unit 车道覆盖。`snapocr.actions` 不 import Qt，用假引擎、假翻译器测试；流程函数返回结果值（要放进剪贴板的内容、通知、浮窗状态、历史记录），剪贴板和通知以返回值断言，不需要假剪贴板（M2 计划 D2）。
- `gui` 车道用例要用不会和日常使用冲突的热键（如 `Ctrl+Alt+Shift+F24`），跑完恢复剪贴板。

## 测试数据与隐私

- 测试截图放 `tests/fixtures/`，只放无隐私内容的样例；真实使用中的截图不进 Git。
- 不在日志里写 OCR 出来的全文，除非开了 debug 开关，且日志只写到 `D:\DevLocal\runtime\snapocr`。

## Git

- 每个 WI 提交一次；提交前跑 `unit` + `engine` 车道。
- `git push`、rebase、reset --hard 前先问 Jeremy。
