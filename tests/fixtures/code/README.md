# 代码 OCR 验收样例（PRD F13-6，M3 WI-13）

真实截图，2026-10-27 Jeremy 提供（原图在不进 Git 的 `tempsnap/`）。内容都是 snapocr 自己的测试代码，没有隐私。测试只读这些文件，没有生成脚本。

| 图片 | 原图 | 来源 | 看点 |
|---|---|---|---|
| `nested.png` | `tempsnap/7.png` | `tests/gui/test_overlay.py` 第 31–62 行，VS Code 深色主题、等宽字体 | 两层缩进、函数之间两个空行、行尾注释 |
| `continuation.png` | `tempsnap/6.png` | `tests/gui/test_settings_window.py` 第 14–45 行，同上 | 对齐到括号的续行、单独一行的 `)` 识别不出来 |
| `proportional.png` | `tempsnap/2.png` | `tests/test_autostart.py` 第 1–21 行，比例字体 | 字符宽度估不准时的缩进 |

`<名字>.expected.txt` 是 snapocr 按 F13 **应该**输出的文字（UTF-8，无 BOM，LF），不完全等于源码：

- `continuation`：续行源码缩进 13 格，按 F13-3 对齐到 4 的倍数，写成 12 格。
- `proportional`：源码缩进 4 格，比例字体下按 F13-3 推出单位 2，写成 2 格（文档字符串里本来就是 2 格的那一行不变）。

验收只比对行数和缩进（两边都不是空行的行），不比对字符：识别错字不在 F13 范围内（F13-5）。
