"""``python -m snapocr [--config PATH]``; the ``snapocr`` gui-script calls ``main`` directly."""

from snapocr.gui.platform.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
