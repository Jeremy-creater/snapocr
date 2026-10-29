"""M7 WI-5: the translation window's controls and colours (PRD F20-5, F19-2 v1.6; M7 plan D9, D10).

Pinned here (beyond the plan text):
- ``target_box`` is a ``SegmentedControl``: one checkable button per choice
  (``segment_buttons``), exactly one checked, with the ``QComboBox`` calls
  the controller uses.
- The copy buttons read "复制" with an icon; their tooltips name what they copy.
- ``set_look`` restyles the open window: checked on the rendered pixels
  (``grab()``) of the window fill (left margin), the source box and a corner.
  A new window starts with the light solid look.
"""

import pytest
from PySide6.QtCore import QPoint, QRect, Qt

from snapocr.gui.popup import TranslationPopup
from snapocr.gui.segmented import SegmentedControl
from snapocr.theme import FONT_FAMILIES, PALETTES, Look, over

LEFT = Qt.MouseButton.LeftButton


@pytest.fixture
def window(qtbot):
    w = TranslationPopup()
    qtbot.addWidget(w)
    w.setGeometry(QRect(200, 150, 420, 260))
    w.show()
    qtbot.waitExposed(w)
    return w


def test_target_box_is_a_segmented_control(qtbot, window):
    box = window.target_box
    assert isinstance(box, SegmentedControl)
    assert [b.text() for b in box.segment_buttons] == ["自动", "中文", "英文"]
    assert [b.isChecked() for b in box.segment_buttons] == [True, False, False]
    qtbot.mouseClick(box.segment_buttons[2], LEFT)
    assert window.target == "en"
    assert box.currentIndex() == 2
    assert [b.isChecked() for b in box.segment_buttons] == [False, False, True]
    qtbot.mouseClick(box.segment_buttons[2], LEFT)  # clicking the checked one keeps it
    assert window.target == "en"
    box.setCurrentIndex(1)
    assert window.target == "zh"
    assert [b.isChecked() for b in box.segment_buttons] == [False, True, False]


def test_segmented_signal(qtbot):
    box = SegmentedControl()
    qtbot.addWidget(box)
    box.addItem("a", 1)
    box.addItem("b", 2)
    with qtbot.waitSignal(box.currentIndexChanged, timeout=1000) as blocker:
        qtbot.mouseClick(box.segment_buttons[1], LEFT)
    assert blocker.args == [1]
    with qtbot.assertNotEmitted(box.currentIndexChanged):
        box.setCurrentIndex(1)
    assert (box.count(), box.itemText(0), box.itemData(1), box.currentData()) == (2, "a", 2, 2)


def test_copy_buttons_and_translate_row(window):
    for button, tip in ((window.copy_source_button, "复制原文"), (window.copy_translation_button, "复制译文")):
        assert button.text() == "复制"
        assert button.toolTip() == tip
        assert not button.icon().isNull()
    assert window.translate_button.text() == "翻译"
    assert window.hint_label.text() == "Ctrl+Enter"
    assert window.hint_label.isVisible()
    hint, button = window.hint_label.geometry(), window.translate_button.geometry()
    assert hint.right() < button.left() and abs(hint.center().y() - button.center().y()) <= 2


def test_font_families(window):
    assert window.font().families()[:3] == list(FONT_FAMILIES)


def pixel(window, x, y):
    c = window.grab().toImage().pixelColor(QPoint(x, y) * window.grab().devicePixelRatio())
    return (c.red(), c.green(), c.blue(), c.alpha())


def close(a, b, tol=3):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def source_centre(window):
    window.source_view.clear()
    view = window.source_view
    return view.mapTo(window, view.rect().center())


def test_starts_light_solid(window):
    assert window.look == Look(PALETTES["light_solid"], False)
    assert close(pixel(window, 9, 130), PALETTES["light_solid"].window)


@pytest.mark.parametrize("name", ["light_solid", "dark_solid"])
def test_solid_looks_render_their_colours(qtbot, window, name):
    p = PALETTES[name]
    window.set_look(Look(p, False))
    assert window.look == Look(p, False)
    qtbot.wait(10)
    assert close(pixel(window, 9, 130), p.window)
    c = source_centre(window)
    assert close(pixel(window, c.x(), c.y()), (*over(p.field, p.window), 255))
    assert pixel(window, 0, 0)[3] < 40  # rounded corner


@pytest.mark.parametrize("name", ["light_glass", "dark_glass"])
def test_glass_looks_are_translucent(qtbot, window, name):
    p = PALETTES[name]
    window.set_look(Look(p, True))
    qtbot.wait(10)
    fill = pixel(window, 9, 130)
    assert abs(fill[3] - p.window[3]) <= 2  # the acrylic behind shows through
    assert pixel(window, 0, 0)[3] < 40


def test_switching_looks_changes_the_open_window(qtbot, window):
    window.set_look(Look(PALETTES["dark_solid"], False))
    qtbot.wait(10)
    dark = pixel(window, 9, 130)
    window.set_look(Look(PALETTES["light_solid"], False))
    qtbot.wait(10)
    assert pixel(window, 9, 130) != dark
    assert window.isVisible()


def _fit_viewport(qtbot, window, view, height):
    """Resize the window until ``view``'s viewport is exactly ``height`` px tall."""
    for _ in range(20):
        delta = height - view.viewport().height()
        if delta == 0:
            return
        window.resize(window.width(), window.height() + delta)
        qtbot.wait(10)
    pytest.fail(f"viewport stuck at {view.viewport().height()} px, wanted {height}")


@pytest.mark.parametrize("theme", ["light_solid", "dark_glass"])
@pytest.mark.parametrize("box", ["source_view", "translation_view"])
def test_no_scrollbar_while_the_lines_fit(qtbot, window, theme, box):
    """M7 WI-10: the stylesheet padding is the only inset, so lines that fit the viewport do not scroll."""
    window.set_look(Look(PALETTES[theme], theme.endswith("glass")))
    view = getattr(window, box)
    lines = 2
    _fit_viewport(qtbot, window, view, lines * view.fontMetrics().lineSpacing() + 1)
    view.setPlainText("\n".join(["Hello 你好"] * lines))
    qtbot.wait(10)
    bar = view.verticalScrollBar()
    assert (bar.maximum(), bar.isVisible()) == (0, False)
    view.setPlainText("\n".join(["Hello 你好"] * (lines + 1)))  # one line too many still scrolls
    qtbot.wait(10)
    assert (bar.maximum(), bar.isVisible()) == (1, True)
