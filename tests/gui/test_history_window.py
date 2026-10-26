"""M2 WI-16: last-results window (PRD F10-1 to F10-4; plan D7).

Pinned here:
- Entries are numbered oldest = 1 ... newest = n; ``index`` is 0-based in that
  order and the label reads "k / n". ``show_latest()`` refreshes from the
  history, selects the newest and shows the window. "上一条" (prev) goes to the
  older entry, "下一条" (next) to the newer one; each is disabled at its end.
- ``on_new_result()`` refreshes and selects the newest only while the window
  is visible; a hidden window picks it up on the next ``show_latest()``.
- Empty history: ``empty_label`` "暂无结果" visible, label empty, text views
  empty, every copy and navigation button disabled; ``index`` is None.
- Thumbnail: the record's PNG scaled to ``fit_size(..., THUMB_MAX)``; a PNG
  that cannot be decoded shows ``NO_IMAGE`` instead.
- Text views are editable; copy buttons copy the current (edited) text.
  Switching entries drops edits; the history itself never changes.
- No translation: the view shows "（无）", is read-only and its copy button is
  disabled. A record's ``error`` is shown in ``error_label`` (hidden if None).
- Esc hides the window.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from snapocr.actions.history import ResultHistory
from snapocr.actions.outcomes import HistoryRecord
from snapocr.geometry import fit_size
from snapocr.gui.history_window import EMPTY_TEXT, NO_IMAGE, NO_TRANSLATION, THUMB_MAX, LastResultWindow
from snapocr.gui.imageops import encode_png
from support import qt_input as qi
from support.qimages import gradient

SENTINEL = "snapocr-sentinel-clipboard"


@pytest.fixture
def clipboard(qapp):
    cb = QGuiApplication.clipboard()
    cb.setText(SENTINEL)
    yield cb
    cb.clear()


def record(i: int, *, w=40, h=30, translation="unset", error=None) -> HistoryRecord:
    return HistoryRecord(
        png=encode_png(gradient(w, h)),
        raw=f"raw {i}\n第二行",
        text=f"text {i}",
        translation=f"translation {i}" if translation == "unset" else translation,
        error=error,
    )


@pytest.fixture
def make(qtbot):
    def factory(records=()):
        history = ResultHistory()
        for r in records:
            history.push(r)
        window = LastResultWindow(history)
        qtbot.addWidget(window)
        return window, history

    return factory


def click(qtbot, button):
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)


def view(window):
    return {
        "raw": window.raw_view.toPlainText(),
        "text": window.text_view.toPlainText(),
        "translation": window.translation_view.toPlainText(),
        "label": window.position_label.text(),
    }


# --- F10-4 ---------------------------------------------------------------------------


def test_empty_history_shows_placeholder_and_disables_everything(make):
    window, _ = make()
    window.show_latest()
    assert window.isVisible()
    assert window.index is None
    assert window.empty_label.text() == EMPTY_TEXT and window.empty_label.isVisible()
    assert view(window) == {"raw": "", "text": "", "translation": "", "label": ""}
    for b in (window.copy_raw_button, window.copy_text_button, window.copy_translation_button,
              window.prev_button, window.next_button):
        assert not b.isEnabled()


# --- F10-1 -----------------------------------------------------------------------------


def test_latest_record_is_shown(make):
    window, _ = make([record(1), record(2, w=500, h=100)])
    window.show_latest()
    assert window.index == 1
    assert not window.empty_label.isVisible()
    assert view(window) == {"raw": "raw 2\n第二行", "text": "text 2", "translation": "translation 2", "label": "2 / 2"}
    pixmap = window.thumbnail_label.pixmap()
    assert (pixmap.width(), pixmap.height()) == fit_size((500, 100), THUMB_MAX)
    assert window.copy_translation_button.isEnabled()
    assert not window.error_label.isVisible()


def test_small_screenshot_is_not_enlarged(make):
    window, _ = make([record(1, w=40, h=30)])
    window.show_latest()
    pixmap = window.thumbnail_label.pixmap()
    assert (pixmap.width(), pixmap.height()) == (40, 30)


def test_undecodable_png_shows_placeholder(make):
    window, _ = make([HistoryRecord(png=b"not a png", raw="r", text="t")])
    window.show_latest()
    assert window.thumbnail_label.pixmap().isNull()
    assert window.thumbnail_label.text() == NO_IMAGE
    assert view(window)["text"] == "t"


def test_no_translation_shows_none_and_disables_copy(make):
    window, _ = make([record(1, translation=None)])
    window.show_latest()
    assert view(window)["translation"] == NO_TRANSLATION
    assert window.translation_view.isReadOnly()
    assert not window.copy_translation_button.isEnabled()
    assert window.copy_raw_button.isEnabled() and window.copy_text_button.isEnabled()


def test_error_is_shown(make):
    window, _ = make([record(1, translation=None, error="翻译失败：timeout")])
    window.show_latest()
    assert window.error_label.isVisible()
    assert "翻译失败：timeout" in window.error_label.text()


# --- F10-2 -----------------------------------------------------------------------------


def test_copy_buttons_copy_each_text(make, clipboard, qtbot):
    window, _ = make([record(1)])
    window.show_latest()
    click(qtbot, window.copy_raw_button)
    assert clipboard.text() == "raw 1\n第二行"
    click(qtbot, window.copy_text_button)
    assert clipboard.text() == "text 1"
    click(qtbot, window.copy_translation_button)
    assert clipboard.text() == "translation 1"


def test_edited_text_is_copied(make, clipboard, qtbot):
    window, _ = make([record(1)])
    window.show_latest()
    assert not window.text_view.isReadOnly() and not window.raw_view.isReadOnly()
    assert not window.translation_view.isReadOnly()
    window.text_view.setPlainText("改过的 text")
    window.translation_view.setPlainText("edited translation")
    click(qtbot, window.copy_text_button)
    assert clipboard.text() == "改过的 text"
    click(qtbot, window.copy_translation_button)
    assert clipboard.text() == "edited translation"


def test_edits_are_dropped_on_switch_and_never_written_back(make, qtbot):
    window, history = make([record(1), record(2)])
    before = history.snapshot()
    window.show_latest()
    window.text_view.setPlainText("edited")
    click(qtbot, window.prev_button)
    click(qtbot, window.next_button)
    assert view(window)["text"] == "text 2"
    assert history.snapshot() == before


# --- F10-3 navigation --------------------------------------------------------------------


def test_navigation_through_ten_records(make, qtbot):
    window, _ = make([record(i) for i in range(1, 13)])  # history keeps the last 10: 3..12
    window.show_latest()
    assert view(window)["label"] == "10 / 10"
    assert view(window)["text"] == "text 12"
    assert window.prev_button.isEnabled() and not window.next_button.isEnabled()
    click(qtbot, window.prev_button)
    assert view(window)["label"] == "9 / 10" and view(window)["text"] == "text 11"
    assert window.prev_button.isEnabled() and window.next_button.isEnabled()
    for _ in range(8):
        click(qtbot, window.prev_button)
    assert view(window)["label"] == "1 / 10" and view(window)["text"] == "text 3"
    assert not window.prev_button.isEnabled() and window.next_button.isEnabled()
    click(qtbot, window.prev_button)  # disabled: no effect
    assert window.index == 0


def test_single_record_disables_both_nav_buttons(make):
    window, _ = make([record(1)])
    window.show_latest()
    assert view(window)["label"] == "1 / 1"
    assert not window.prev_button.isEnabled() and not window.next_button.isEnabled()


def test_show_latest_always_jumps_to_newest(make, qtbot):
    window, history = make([record(1), record(2), record(3)])
    window.show_latest()
    click(qtbot, window.prev_button)
    click(qtbot, window.prev_button)
    window.hide()
    window.show_latest()
    assert view(window)["label"] == "3 / 3"


def test_new_result_while_open_jumps_to_newest(make, qtbot):
    window, history = make([record(1), record(2)])
    window.show_latest()
    click(qtbot, window.prev_button)
    history.push(record(3))
    window.on_new_result()
    assert view(window)["label"] == "3 / 3" and view(window)["text"] == "text 3"


def test_new_result_while_hidden_is_picked_up_on_open(make):
    window, history = make([record(1)])
    window.on_new_result()
    assert not window.isVisible()
    history.push(record(2))
    window.on_new_result()
    assert not window.isVisible()
    window.show_latest()
    assert view(window)["label"] == "2 / 2"


def test_first_result_while_open_on_empty_window(make):
    window, history = make()
    window.show_latest()
    history.push(record(1))
    window.on_new_result()
    assert not window.empty_label.isVisible()
    assert view(window)["label"] == "1 / 1"


def test_esc_hides(make):
    window, _ = make([record(1)])
    window.show_latest()
    qi.key(window, Qt.Key.Key_Escape)
    assert not window.isVisible()


# --- property: navigation index stays in range ----------------------------------------------


@settings(max_examples=30, deadline=None)
@given(st.integers(0, 12), st.lists(st.sampled_from(["prev", "next", "new", "reopen"]), max_size=30))
def test_index_stays_in_range_and_label_matches(qapp, initial, steps):
    history = ResultHistory()
    for i in range(initial):
        history.push(record(i))
    window = LastResultWindow(history)
    counter = initial
    try:
        window.show_latest()
        for step in steps:
            if step == "prev":
                window.prev_button.click()
            elif step == "next":
                window.next_button.click()
            elif step == "new":
                history.push(record(counter))
                counter += 1
                window.on_new_result()
            else:
                window.show_latest()
            n = len(history.snapshot())
            if n == 0:
                assert window.index is None and window.position_label.text() == ""
                continue
            assert 0 <= window.index <= n - 1
            assert window.position_label.text() == f"{window.index + 1} / {n}"
            expected = history.snapshot()[n - 1 - window.index]
            assert window.text_view.toPlainText() == expected.text
            assert window.prev_button.isEnabled() == (window.index > 0)
            assert window.next_button.isEnabled() == (window.index < n - 1)
    finally:
        window.deleteLater()


def test_other_keys_do_not_hide(make):
    window, _ = make([record(1)])
    window.show_latest()
    qi.key(window, Qt.Key.Key_A)
    assert window.isVisible()
