"""Capture every Mac screen with ``CGDisplayCreateImage`` (PRD F23-3, F23-4, M9 plan D13 to D15).

The permission is checked first: without it macOS returns only the wallpaper,
so nothing is grabbed. Each display is grabbed on its own in physical pixels
(BGRA premultiplied, which is ``QImage.Format_ARGB32_Premultiplied`` on a
little-endian Mac) and the images are laid side by side in Qt's order
(``geometry.stack_physical``) as one RGB32 image, the shape the overlay and
``crop_box`` already use.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable, Sequence

from PySide6.QtGui import QGuiApplication, QImage, QPainter

from snapocr.geometry import Rect, ScreenMismatch, pair_displays, stack_physical
from snapocr.gui.boundaries import Capture, CaptureError, CapturePermissionError
from snapocr.gui.platform.mac import _cocoa as c
from snapocr.gui.platform.mac.permission import request_screen_capture, screen_capture_allowed

_MAX_DISPLAYS = 16

QtScreen = tuple[str, Rect, float, Rect]  # name, logical geometry, dpr, available geometry


def qt_screens() -> list[QtScreen]:
    result = []
    for screen in QGuiApplication.screens():
        g, a = screen.geometry(), screen.availableGeometry()
        result.append((screen.name(), Rect(g.x(), g.y(), g.width(), g.height()), screen.devicePixelRatio(),
                       Rect(a.x(), a.y(), a.width(), a.height())))
    return result


def cg_displays() -> list[tuple[int, Rect]]:
    """Active displays and their bounds in global points (the same space as Qt's geometry)."""
    ids = (c.CGDirectDisplayID * _MAX_DISPLAYS)()
    count = ctypes.c_uint32(0)
    c.cg.CGGetActiveDisplayList(_MAX_DISPLAYS, ids, ctypes.byref(count))  # on error count stays 0
    result = []
    for display in ids[: count.value]:
        b = c.cg.CGDisplayBounds(display)
        result.append((int(display), Rect(round(b.origin.x), round(b.origin.y), round(b.size.width), round(b.size.height))))
    return result


def grab_display(display: int) -> QImage:
    """One display in physical pixels, copied into Qt-owned memory."""
    image = c.cg.CGDisplayCreateImage(display)
    if not image:
        raise CaptureError(f"屏幕截取失败（CGDisplayCreateImage，显示器 {display}）")
    try:
        w, h = c.cg.CGImageGetWidth(image), c.cg.CGImageGetHeight(image)
        stride = c.cg.CGImageGetBytesPerRow(image)
        data = c.cg.CGDataProviderCopyData(c.cg.CGImageGetDataProvider(image))
        try:
            pixels = (ctypes.c_ubyte * (stride * h)).from_address(c.cf.CFDataGetBytePtr(data))
            return QImage(pixels, w, h, stride, QImage.Format.Format_ARGB32_Premultiplied).copy()
        finally:
            c.cf.CFRelease(data)
    finally:
        c.cg.CGImageRelease(image)


class MacCapture:
    """The real ``CaptureProvider`` on a Mac."""

    def __init__(
        self,
        *,
        preflight: Callable[[], bool] = screen_capture_allowed,
        request: Callable[[], bool] = request_screen_capture,
        screens: Callable[[], Sequence[QtScreen]] = qt_screens,
        displays: Callable[[], Sequence[tuple[int, Rect]]] = cg_displays,
        grab: Callable[[int], QImage] = grab_display,
    ) -> None:
        self._preflight, self._request = preflight, request
        self._screens, self._displays, self._grab = screens, displays, grab

    def capture(self) -> Capture:
        if not self._preflight():
            self._request()  # the first time, macOS shows its own prompt
            raise CapturePermissionError("没有屏幕录制权限")
        qt = list(self._screens())
        try:
            ids = pair_displays([(name, logical, dpr) for name, logical, dpr, _ in qt], self._displays())
        except ScreenMismatch as err:
            raise CaptureError(f"Qt 和 macOS 的屏幕信息对不上：{err}") from err
        # Two identical monitors have the same Qt name; the display id tells them apart.
        names = [f"{name} #{display}" for (name, _, _, _), display in zip(qt, ids)]
        screens = stack_physical([(n, logical, dpr) for n, (_, logical, dpr, _) in zip(names, qt)])
        canvas = QImage(sum(s.physical.w for s in screens), max(s.physical.h for s in screens),
                        QImage.Format.Format_RGB32)
        canvas.fill(0)
        painter = QPainter(canvas)
        try:
            for s, display in zip(screens, ids):
                image = self._grab(display)
                if (image.width(), image.height()) != (s.physical.w, s.physical.h):
                    raise CaptureError(
                        f"{s.name} 截到 {image.width()}x{image.height()}，应为 {s.physical.w}x{s.physical.h}"
                    )
                painter.drawImage(s.physical.x, 0, image)
        finally:
            painter.end()
        work = {n: available for n, (_, _, _, available) in zip(names, qt)}
        return Capture(canvas, (0, 0), tuple(screens), work)
