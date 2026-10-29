# Third-party notices

snapocr itself is MIT-licensed (see `LICENSE`). It does not bundle any third-party code or model files in this repository; the packages below are installed by pip / uv from PyPI as dependencies, each under its own license.

| Component | Used for | License |
|---|---|---|
| [PySide6-Essentials](https://pypi.org/project/PySide6-Essentials/) / shiboken6 (Qt for Python) | Tray, windows, screen overlay, clipboard | LGPL-3.0-only (or GPL-2.0 / GPL-3.0) |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | OCR engine wrapper | Apache-2.0 |
| PP-OCR models (`PP-OCRv6_det_small`, `PP-OCRv6_rec_small`, `ch_ppocr_mobile_v2.0_cls_mobile`), shipped inside the RapidOCR wheel, originally from [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Text detection and recognition | Apache-2.0 |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | Runs the OCR models | MIT |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Image handling for OCR | Apache-2.0 |
| [NumPy](https://numpy.org/) | Image arrays | BSD-3-Clause (and bundled permissive licenses) |
| [tomlkit](https://github.com/python-poetry/tomlkit) | Writing the config file while keeping comments | MIT |

Development-only dependencies (pytest, pytest-cov, pytest-qt, hypothesis) are not needed to run snapocr.

## Qt / LGPL

snapocr uses PySide6 as an ordinary pip dependency and does not modify or redistribute Qt. If you build a stand-alone package (for example with PyInstaller), keep the Qt libraries as separate, replaceable files (a "one-folder" build) to stay within the LGPL.

## Translation model

snapocr does not ship any translation model. It talks to a model server you run yourself (by default Ollama on `127.0.0.1`). The model you choose — for example Tencent's Hunyuan-MT used by `docs/hy-mt2-7b.Modelfile` — comes with its own license, which may include usage or regional restrictions. Read it before you download the model.
