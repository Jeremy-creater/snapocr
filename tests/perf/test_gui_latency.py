"""M2 WI-23: latency on the real desktop (PRD §8). Manual only:

    python -m pytest -m "gui and perf" --qt-desktop -s

- Hotkey to every overlay exposed: median < 300 ms.
- Real screenshot of a 1080p page of dense text, from confirming the
  selection (Enter; plan A11) to the text on the clipboard: median < 2 s with
  the engine already loaded.
If a median misses its budget, do NOT loosen the assertion: Jeremy decides.
"""

import statistics
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

from snapocr.gui.platform.launch import start
from snapocr.hotkeys import parse_hotkey
from support import qt_input as qi
from support import win_clipboard as wc
from support.win_input import press_combo

pytestmark = [pytest.mark.gui, pytest.mark.perf]

OVERLAY_BUDGET_S = 0.3
OCR_BUDGET_S = 2.0
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "perf_1080p.png"
KEYS = {"capture": "Ctrl+Alt+Shift+F21", "ocr": "Ctrl+Alt+Shift+F22"}
SENTINEL = "snapocr-perf-sentinel"
OFFSET = (120, 120)  # physical px from the primary screen's top-left


@pytest.fixture
def app(qapp, tmp_path):
    path = tmp_path / "config.local.toml"
    path.write_text("[hotkeys]\n" + "".join(f'{k} = "{v}"\n' for k, v in KEYS.items()), encoding="utf-8")
    running = start(["snapocr", "--config", str(path)])
    yield running
    running.shutdown()


def exposed(overlays) -> bool:
    return bool(overlays) and all(o.windowHandle() is not None and o.windowHandle().isExposed() for o in overlays)


def press(text: str) -> None:
    hk = parse_hotkey(text)
    press_combo(hk.mods, hk.vk)


def test_hotkey_to_overlays_median(qtbot, app):
    timings = []
    for _ in range(7):
        t0 = time.perf_counter()
        press(KEYS["capture"])
        qtbot.waitUntil(lambda: exposed(app.controller.overlays), timeout=3000)
        timings.append(time.perf_counter() - t0)
        press_combo(0, 0x1B)  # Esc
        qtbot.waitUntil(lambda: app.controller.overlays == (), timeout=2000)
        qtbot.wait(100)
    median = statistics.median(timings)
    print(f"\n[WI-23] hotkey->overlays ms: {[round(t * 1000) for t in timings]} median={median * 1000:.0f}")
    assert median < OVERLAY_BUDGET_S, f"median {median * 1000:.0f} ms >= {OVERLAY_BUDGET_S * 1000:.0f} ms"


class PageWindow(QWidget):
    """Shows an image 1:1 in physical pixels at a physical offset on the primary screen."""

    def __init__(self, image: QImage):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        screen = QGuiApplication.primaryScreen()
        self.dpr = screen.devicePixelRatio()
        self._image = QImage(image)
        self._image.setDevicePixelRatio(self.dpr)
        g = screen.geometry()
        self.local = (OFFSET[0] / self.dpr, OFFSET[1] / self.dpr)
        self.size_logical = (image.width() / self.dpr, image.height() / self.dpr)
        self.setGeometry(QRect(round(g.x() + self.local[0]), round(g.y() + self.local[1]),
                               round(self.size_logical[0]), round(self.size_logical[1])))

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), self._image, QRectF(self._image.rect()))
        p.end()


def test_real_screenshot_ocr_median(qtbot, app):
    page = PageWindow(QImage(str(FIXTURE)))
    qtbot.addWidget(page)
    page.show()
    qtbot.waitExposed(page)
    qtbot.wait(300)
    primary = QGuiApplication.primaryScreen().geometry()
    saved = wc.snapshot()
    timings, texts = [], []
    try:
        for run in range(6):  # the first run also waits for the warm-up; it is not timed
            QGuiApplication.clipboard().setText(SENTINEL)
            press(KEYS["ocr"])
            qtbot.waitUntil(lambda: exposed(app.controller.overlays), timeout=3000)
            overlay = next(o for o in app.controller.overlays if o.geometry().topLeft() == primary.topLeft())
            x0, y0 = page.local
            w, h = page.size_logical
            qi.drag(overlay, x0, y0, x0 + w, y0 + h)
            t0 = time.perf_counter()
            qi.key(overlay, Qt.Key.Key_Return)
            qtbot.waitUntil(lambda: QGuiApplication.clipboard().text() != SENTINEL, timeout=30000)
            if run:
                timings.append(time.perf_counter() - t0)
            texts.append(QGuiApplication.clipboard().text())
    finally:
        wc.restore(saved)
        page.hide()
    median = statistics.median(timings)
    lines = [line for line in texts[-1].split("\n") if line.strip()]
    print(f"\n[WI-23] confirm->clipboard s: {[round(t, 2) for t in timings]} median={median:.2f} lines={len(lines)}")
    assert len(lines) >= 12, "the dense page should give at least 12 lines of text"
    assert median < OCR_BUDGET_S, f"median {median:.2f} s >= {OCR_BUDGET_S} s"
