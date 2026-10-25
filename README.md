# snapocr

个人定制的托盘常驻截图工具：热键截图、截图 OCR、截图翻译，结果直接进剪贴板。OCR 引擎内置（RapidOCR），翻译使用本地模型（默认 Ollama）。

- 需求：`docs/PRD.md`
- 规则：`CLAUDE.md`

## 开发环境

```powershell
uv venv D:\DevLocal\envs\snapocr --python 3.12
D:\DevLocal\envs\snapocr\Scripts\Activate.ps1
cd D:\LLM\workspace\snapocr
python -m pip install -e ".[dev]"
claude
```

## 测试

```powershell
python -m pytest -m "not integration"   # unit，不需要任何外部服务
python -m pytest -m integration         # 需要 Ollama 运行且已导入翻译模型
```
