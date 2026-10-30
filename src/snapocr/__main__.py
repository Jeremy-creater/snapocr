"""``python -m snapocr [--config PATH]``; the ``snapocr`` gui-script calls ``main`` directly."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--self-check" in argv[1:]:  # F22-4: no tray, no hotkeys, no config file
        from snapocr.app import parse_args
        from snapocr.engines.config import OcrEngineConfig
        from snapocr.engines.rapidocr_engine import RapidOcrEngine
        from snapocr.selfcheck import run_self_check

        def load_engine() -> RapidOcrEngine:
            from snapocr.gui.platform.launch import platform_kit

            platform_kit()  # loaded by name: a build that left it out must fail here, not at the user's first start
            return RapidOcrEngine(OcrEngineConfig()).load()

        image, report = parse_args(argv[1:]).self_check
        return run_self_check(image, report, load_engine)

    from snapocr.gui.platform.launch import main as gui_main

    return gui_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
