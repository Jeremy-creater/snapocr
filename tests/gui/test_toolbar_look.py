"""M7 WI-9: the annotation toolbar wears the light solid palette (PRD v1.7 F20-7).

Pinned here (beyond the plan text):
- Pixels are read from a black parent's ``grab()`` (the dimmed overlay stands
  in), at 100% scale. The panel is sampled in the top margin, a button just
  inside its top edge, where no icon is drawn.
- The look is fixed: the toolbar takes no theme and does not follow the
  "窗口风格" setting.
"""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QToolButton, QWidget

from snapocr.gui.annotate_toolbar import AnnotateToolbar
from snapocr.theme import PALETTES, over

pytestmark = pytest.mark.usefixtures("qapp")

P = PALETTES["light_solid"]
AT = 10  # the toolbar's offset inside the parent


def shot():
    parent = QWidget()
    pal = parent.palette()
    pal.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
    parent.setPalette(pal)
    parent.setAutoFillBackground(True)
    parent.resize(1000, 100)
    bar = AnnotateToolbar(parent=parent)
    bar.setGeometry(AT, AT, bar.sizeHint().width(), bar.sizeHint().height())
    bar.keep = parent  # else the parent, and the toolbar with it, is deleted
    return bar, parent.grab().toImage()


def rgb(image, x, y):
    c = image.pixelColor(x, y)
    return (c.red(), c.green(), c.blue())


def near(a, b, tolerance=2):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def test_panel_is_the_light_solid_window_colour():
    bar, image = shot()
    assert near(rgb(image, AT + bar.width() // 2, AT + 2), P.window[:3])


def test_panel_has_round_corners():
    _, image = shot()
    assert sum(rgb(image, AT + 1, AT + 1)) < 60  # the black parent shows through


def test_checked_tool_has_the_focus_tint_and_others_the_panel_colour():
    bar, _ = shot()
    rect = bar.findChild(QToolButton, "tool-rect")
    rect.click()
    image = bar.parentWidget().grab().toImage()
    for name, want in (("tool-rect", over(P.focus, P.window)), ("tool-ellipse", P.window[:3])):
        b = bar.findChild(QToolButton, name)
        top = b.mapTo(bar.parentWidget(), b.rect().center())
        assert near(rgb(image, top.x(), AT + b.y() + 1), want), name


def test_icons_are_drawn_in_the_text_colour():
    pixmap = AnnotateToolbar().findChild(QToolButton, "tool-rect").icon().pixmap(QSize(20, 20), 1)
    # The rectangle's left edge (x = 3.5, pen 1.6) covers pixel column 3 completely.
    c = pixmap.toImage().pixelColor(3, 10)
    assert c.alpha() == 255
    assert (c.red(), c.green(), c.blue()) == P.text[:3]
