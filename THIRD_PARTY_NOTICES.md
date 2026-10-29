# Third-party notices

snapocr itself is MIT-licensed (see `LICENSE`). The source repository contains no third-party code or model files (only the LGPL-3.0 and GPL-3.0 license texts in `packaging/licenses`); the packages below are installed by pip / uv from PyPI as dependencies, each under its own license. The Windows portable build bundles them; see the section below.

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

## Windows portable build (zip on the Releases page)

The zip (PRD F22) bundles the packages above, unmodified, together with what they need at run time. The license files of every bundled package are in the `licenses` folder of the zip, one subfolder per package.

| Component | License |
|---|---|
| Python 3.12 runtime | PSF-2.0 (`licenses/python/LICENSE.txt`) |
| PyInstaller bootloader (starts `snapocr.exe`) | GPL-2.0-or-later with the bootloader exception, which allows distributing it with programs under any license |
| Microsoft Visual C++ runtime (`VCRUNTIME140*.dll`), Universal C runtime (`api-ms-win-*.dll`) | Redistributable under Microsoft's terms |
| OpenSSL (Python's `ssl` module) | Apache-2.0 |
| Dependencies of RapidOCR: Pillow, Shapely (with GEOS), pyclipper, PyYAML, omegaconf, tqdm, colorlog, requests, urllib3, idna, charset-normalizer, certifi, protobuf, flatbuffers, six, packaging, colorama | MIT-CMU, BSD-3-Clause (GEOS: LGPL-2.1), MIT (Clipper: BSL-1.0), MIT, BSD-3-Clause, MPL-2.0 AND MIT, MIT, Apache-2.0, MIT, BSD-3-Clause, MIT, MPL-2.0, BSD-3-Clause, Apache-2.0, MIT, Apache-2.0 OR BSD-2-Clause, BSD-3-Clause |

certifi and tqdm (MPL-2.0) are included unmodified; their source is on PyPI. flatbuffers ships no license file; it is under the Apache License 2.0, the same text as in `licenses/rapidocr/licenses/LICENSE`.

## Qt / LGPL

From pip or uv, snapocr uses PySide6 as an ordinary dependency and does not modify or redistribute Qt. The portable build does redistribute PySide6 and Qt, unmodified, under the LGPL-3.0: it is a one-folder build, so the Qt and PySide6 libraries are separate files in `_internal\PySide6` that you can replace with your own build of the same version. The LGPL-3.0 and GPL-3.0 texts are in `licenses/pyside6`. Qt's source code is available from https://download.qt.io/ and PySide6's from https://code.qt.io/cgit/pyside/pyside-setup.git/. The same applies to GEOS (LGPL-2.1), a separate DLL in `_internal\Shapely.libs`.

## Translation model

snapocr does not ship any translation model. It talks to a model server you run yourself (by default Ollama on `127.0.0.1`). The model you choose — for example Tencent's Hunyuan-MT used by `docs/hy-mt2-7b.Modelfile` — comes with its own license, which may include usage or regional restrictions. Read it before you download the model.
