# snapocr — 项目规则

个人定制的截图文字识别工具。以本机已安装的 Umi-OCR 作为 OCR 后端，snapocr 负责调用、后处理和输出编排。

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
| 运行数据（日志、临时截图、缓存） | `D:\DevLocal\runtime\snapocr` |
| Umi-OCR 安装（只读参考） | `D:\ProgramData\Umi-OCR_Paddle_v2.1.5` |

## 环境

- Python 3.12 only，不用 conda。
- 创建环境：`uv venv D:\DevLocal\envs\snapocr --python 3.12`
- 安装：`uv pip install --python D:\DevLocal\envs\snapocr\Scripts\python.exe -e ".[dev]"`（或激活后 `python -m pip install -e ".[dev]"`）
- **先激活环境，再在同一个终端里启动 `claude`**，否则 tdd-guardian 会报 `runner-missing`。
- 新增运行时依赖前，先在 PRD 或计划里写明理由。

## 架构边界

- **不修改 Umi-OCR 安装目录下的任何文件。** 只通过它的公开接口使用：
  - HTTP：`POST http://127.0.0.1:1224/api/ocr`（`base64` + `options`），`GET /api/ocr/get_options`
  - 命令行：`Umi-OCR.exe --screenshot / --clipboard / --path`
- OCR 后端放在一个适配层后面（`snapocr.engines`），业务代码不直接拼 Umi 的 HTTP 请求，便于以后接 VLM 或别的引擎。
- 纯逻辑（后处理、版面整理、配置解析）与 I/O（HTTP、剪贴板、截图、热键）分开，纯逻辑必须可在无 Umi、无 GUI 的环境下测试。
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
| `unit` | 纯逻辑 + 假 HTTP，不需要 Umi 运行 | `python -m pytest -m "not integration" --cov=snapocr --cov-branch --cov-report=json` | taskCompleted、commit |
| `integration` | 连真实运行中的 Umi-OCR（`@pytest.mark.integration`） | `python -m pytest -m integration` | manual |

- 覆盖率模式：`no-decrease`。
- 初期不开 `blockCommitWithoutFreshGate`；熟悉流程后再开。
- integration 测试在 Umi 未运行时必须**明确失败并提示**，不得静默跳过后报绿。

## 测试数据与隐私

- 测试截图放 `tests/fixtures/`，只放无隐私内容的样例；真实使用中的截图不进 Git。
- 不在日志里写 OCR 出来的全文，除非开了 debug 开关，且日志只写到 `D:\DevLocal\runtime\snapocr`。

## Git

- 每个 WI 提交一次；提交前跑 `unit` 车道。
- `git push`、rebase、reset --hard 前先问 Jeremy。
