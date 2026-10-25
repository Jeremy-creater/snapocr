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
| `unit` | 纯逻辑 + 假实现，不需要任何外部服务，不加载 OCR 模型 | `python -m pytest -m "not integration and not engine and not perf" --cov=snapocr --cov-branch --cov-report=json` | taskCompleted、commit |
| `engine` | 进程内真实 RapidOCR 模型（`@pytest.mark.engine`），不需要外部服务、不联网 | `python -m pytest -m "engine and not perf" --cov=snapocr --cov-branch --cov-report=json:coverage-engine.json` | taskCompleted、commit |
| `integration` | 连真实运行中的本地模型服务（Ollama，`@pytest.mark.integration`） | `python -m pytest -m "integration and not perf"` | manual |

- 覆盖率模式：`no-decrease`。
- 初期不开 `blockCommitWithoutFreshGate`；熟悉流程后再开。
- integration 测试在 Ollama 未运行或模型未导入时必须**明确失败并提示**，不得静默跳过后报绿。
- engine 测试在模型文件缺失或损坏时必须**明确失败并提示**，不能跳过。归为独立车道的依据：冒烟实测加载 + 识别约 1–2 s，不需要外部服务，适合每次提交跑，但不该混进毫秒级的 unit。
- `perf`（`@pytest.mark.perf`，延迟实测）只能手动跑：`python -m pytest -m perf -s`，不参与任何 gate。同时带 `integration` 和 `perf` 的测试（翻译延迟）也只能手动跑，同样需要 Ollama。
- GUI 层的自动化测试方式（如 pytest-qt + offscreen）在 M2 计划时再定，定下后先改本文件。

## 测试数据与隐私

- 测试截图放 `tests/fixtures/`，只放无隐私内容的样例；真实使用中的截图不进 Git。
- 不在日志里写 OCR 出来的全文，除非开了 debug 开关，且日志只写到 `D:\DevLocal\runtime\snapocr`。

## Git

- 每个 WI 提交一次；提交前跑 `unit` + `engine` 车道。
- `git push`、rebase、reset --hard 前先问 Jeremy。
