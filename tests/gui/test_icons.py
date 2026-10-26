"""M2 WI-18: the packaged application icon loads with all its sizes (F5-6)."""

import pytest
from PySide6.QtCore import QSize

from snapocr.gui.icons import app_icon

pytestmark = pytest.mark.usefixtures("qapp")


def test_app_icon_has_all_sizes():
    icon = app_icon()
    assert not icon.isNull()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert {(16, 16), (24, 24), (32, 32), (48, 48), (256, 256)} <= sizes


def test_small_pixmap_is_exact_size():
    pixmap = app_icon().pixmap(QSize(16, 16))
    assert (pixmap.width(), pixmap.height()) == (16, 16)
