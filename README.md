# snapocr

个人定制的截图文字识别工具，后端使用本机的 Umi-OCR（HTTP API）。

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
python -m pytest -m "not integration"   # unit，不需要 Umi
python -m pytest -m integration         # 需要 Umi-OCR 运行并开启 HTTP 服务
```
