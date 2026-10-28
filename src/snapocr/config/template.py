"""The commented default config file written when none exists (PRD F9-2). Stdlib only.

Lines starting with "## " explain; lines starting with "# " are settings
commented out at their default value, so a later change of a default in code
is not pinned by an old file. Removing the leading "# " enables a setting.
Values come from the config classes, so the template cannot drift from them.
"""

from __future__ import annotations

import json

from snapocr.config.schema import DEFAULT_HOTKEY_TEXT, HOTKEY_COMMANDS, AppConfig, default_save_dir
from snapocr.engines.config import OcrEngineConfig
from snapocr.postprocess import PostprocessOptions
from snapocr.translators.config import SAMPLING_KEYS, TranslatorConfig

# Shown for settings whose default is "not set"; enabling them is a real choice.
EXAMPLE_MODEL_DIR = "D:/LLM/models/rapidocr"
EXAMPLE_REPLACEMENT = ("0CR", "OCR")


def _toml(value: bool | int | float | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)  # a valid TOML basic string
    return repr(value)  # int or finite float


_HOTKEY_HELP = {
    "capture": "截图，图片复制到剪贴板",
    "ocr": "截图并识别文字，文字复制到剪贴板",
    "translate": "截图、识别并翻译，译文复制到剪贴板",
    "translate_text": "打开翻译窗口，手动输入文字翻译",
    "code_ocr": "截图识别代码，保留换行和缩进，复制到剪贴板",
    "table_ocr": "截图识别表格，表格（HTML）和 Markdown 文本一起复制到剪贴板",
}


def _build() -> str:
    ocr = OcrEngineConfig()
    pp = PostprocessOptions()
    tr = TranslatorConfig()
    out = [
        "## snapocr 配置文件（TOML 格式，UTF-8）。文件不存在时由 snapocr 生成，之后不会再覆盖。",
        "## 以“# ”开头的行是被注释掉的设置，写的是默认值；去掉行首的“# ”才会生效。",
        "## 以“## ”开头的行是说明。修改后重启 snapocr 生效。",
        "",
        "[hotkeys]",
        "## 全局热键：Ctrl、Alt、Shift、Win 至少一个，加一个主键（A–Z、0–9、F1–F24、Space、方向键等）。",
        "## 被其他软件占用时，启动通知会指出是哪一个，其余照常工作。",
    ]
    for command in HOTKEY_COMMANDS:
        out += [f"## {command.value}：{_HOTKEY_HELP[command.value]}",
                f"# {command.value} = {_toml(DEFAULT_HOTKEY_TEXT[command])}"]
    out += [
        "",
        "[capture]",
        "## 截图工具栏“保存”存到这个文件夹，必须是绝对路径；不存在时保存那一刻创建。",
        "## 路径里用 / 分隔（如 D:/截图），或用单引号包起来；双引号里的 \\ 要写两个。",
        f"# save_dir = {_toml(str(default_save_dir()))}",
        "",
        "[ocr]",
        "## 置信度低于这个值的文本块丢弃，范围 0 到 1。",
        f"# min_score = {_toml(ocr.min_score)}",
        "## 模型目录。不写时用 rapidocr 自带的模型；相对路径按本文件所在的目录计算。下面只是示例。",
        f"# model_dir = {_toml(EXAMPLE_MODEL_DIR)}",
        "",
        "[postprocess]",
        "## 把自动折行的行合并回段落。",
        f"# paragraphs = {_toml(pp.paragraphs)}",
        "## 在汉字和英文字母、数字之间加空格。",
        f"# spacing = {_toml(pp.spacing)}",
        "## 中文语境里的半角标点转成全角。",
        f"# punctuation = {_toml(pp.punctuation)}",
        "## 自定义替换表（常见误识别），字面量替换，默认为空。不满足约束时整张表作废并报错，",
        "## 约束见 docs/postprocess.md。下面只是示例。",
        "# [postprocess.replacements]",
        f"# {_toml(EXAMPLE_REPLACEMENT[0])} = {_toml(EXAMPLE_REPLACEMENT[1])}",
        "",
        "[notify]",
        "## OCR 完成的托盘通知里显示识别出的前 30 个字；false 时只显示字数。",
        f"# show_text = {_toml(AppConfig.show_text)}",
        "",
        "[debug]",
        "## 排查问题用：每次 OCR / 翻译的截图和全文存到 D:/DevLocal/runtime/snapocr/debug，不会自动删除。",
        f"# enabled = {_toml(AppConfig.debug)}",
        "",
        "[translator]",
        "## 本地模型服务的地址，只接受 http://127.0.0.1:<端口>，不带路径。",
        f"# base_url = {_toml(tr.base_url)}",
        "## 模型名。Ollama 云模型（tag 为 cloud 或以 -cloud 结尾）会把原文发出本机，一律拒绝。",
        f"# model = {_toml(tr.model)}",
        "## 超时秒数（连接和每次读取），大于 0、不超过 600。",
        f"# timeout_s = {_toml(tr.timeout_s)}",
        "## 目标语言：auto（按下面的阈值自动判断）、zh 或 en（固定目标语言）。",
        f"# target_lang = {_toml(tr.target_lang)}",
        "## auto 时：汉字数 / (汉字数 + ASCII 字母数) ≥ 这个值就译成英文，否则译成中文。大于 0、不超过 1。",
        f"# direction_threshold = {_toml(tr.direction_threshold)}",
        "## 提示词模板：{source_text} 必须出现一次，{target_language} 最多一次。",
        f"# prompt_template = {_toml(tr.prompt_template)}",
        "## 原文超过这么多字符时报错，不截断。",
        f"# max_input_chars = {_toml(tr.max_input_chars)}",
        f"## 采样参数，只允许 {'、'.join(sorted(SAMPLING_KEYS))}。",
        "# [translator.sampling]",
    ]
    out += [f"# {name} = {_toml(value)}" for name, value in tr.sampling.items()]
    return "\n".join(out) + "\n"


DEFAULT_TEMPLATE: str = _build()
