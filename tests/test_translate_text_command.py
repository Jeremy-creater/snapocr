"""M6 WI-5: "文字翻译" replaces "上次结果" (PRD F19-1, F19-3, F19-8; plan D9 to D11).

Pinned here:
- ``Command.TRANSLATE_TEXT`` ("translate_text") takes the place of
  ``LAST_RESULT``, so its hotkey id stays 4 and its default stays Alt+4.
- ``[hotkeys] translate_text`` is read; the old ``last_result`` key is
  reported as renamed and its value is not used.
- Labels: 截图翻译 (TRANSLATE) and 文字翻译 (TRANSLATE_TEXT), in the tray
  menu too; the config template documents ``translate_text``.
- ``center_in(size, available)``: centred in ``available``, shrunk to fit it.
"""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.actions.messages import COMMAND_LABELS
from snapocr.commands import Command
from snapocr.config.load import build_config
from snapocr.config.schema import DEFAULT_HOTKEY_TEXT, HOTKEY_COMMANDS, KNOWN_KEYS, ConfigIssue
from snapocr.config.template import DEFAULT_TEMPLATE
from snapocr.geometry import Rect, center_in
from snapocr.hotkeys import hotkey_id, parse_hotkey

SRC = Path("D:/x/config.local.toml")


def test_translate_text_takes_the_place_of_last_result():
    assert Command.TRANSLATE_TEXT.value == "translate_text"
    assert "LAST_RESULT" not in Command.__members__
    assert [c.value for c in Command][3] == "translate_text"
    assert hotkey_id(Command.TRANSLATE_TEXT) == 4
    assert HOTKEY_COMMANDS[3] is Command.TRANSLATE_TEXT
    assert DEFAULT_HOTKEY_TEXT[Command.TRANSLATE_TEXT] == "Alt+4"


def test_translate_text_key_is_read():
    config, issues = build_config({"hotkeys": {"translate_text": "Ctrl+Alt+T"}}, source=SRC)
    assert issues == []
    assert config.hotkeys[Command.TRANSLATE_TEXT] == parse_hotkey("Ctrl+Alt+T")
    assert "translate_text" in KNOWN_KEYS["hotkeys"] and "last_result" not in KNOWN_KEYS["hotkeys"]


def test_old_last_result_key_is_reported_as_renamed():
    config, issues = build_config({"hotkeys": {"last_result": "Ctrl+Alt+L"}}, source=SRC)
    assert issues == [ConfigIssue(SRC, "hotkeys.last_result", "renamed to 'translate_text', ignored")]
    assert config.hotkeys[Command.TRANSLATE_TEXT] == parse_hotkey("Alt+4")


def test_both_keys_use_the_new_one_and_still_report_the_old():
    config, issues = build_config({"hotkeys": {"last_result": "Ctrl+Alt+L", "translate_text": "Ctrl+Alt+T"}}, source=SRC)
    assert [i.key_path for i in issues] == ["hotkeys.last_result"]
    assert config.hotkeys[Command.TRANSLATE_TEXT] == parse_hotkey("Ctrl+Alt+T")


def test_labels():
    assert COMMAND_LABELS[Command.TRANSLATE] == "截图翻译"
    assert COMMAND_LABELS[Command.TRANSLATE_TEXT] == "文字翻译"


def test_template_documents_translate_text():
    assert "# translate_text = " in DEFAULT_TEMPLATE
    assert "last_result" not in DEFAULT_TEMPLATE


def test_center_in_examples():
    assert center_in((400, 300), Rect(0, 0, 1000, 700)) == Rect(300, 200, 400, 300)
    assert center_in((400, 300), Rect(-1707, 40, 1707, 1000)) == Rect(-1054, 390, 400, 300)
    assert center_in((400, 300), Rect(10, 10, 200, 100)) == Rect(10, 10, 200, 100)


@given(
    st.tuples(st.integers(0, 3000), st.integers(0, 3000)),
    st.builds(Rect, st.integers(-4000, 4000), st.integers(-4000, 4000), st.integers(1, 4000), st.integers(1, 4000)),
)
def test_center_in_stays_inside_and_centred(size, av):
    r = center_in(size, av)
    assert (r.w, r.h) == (min(size[0], av.w), min(size[1], av.h))
    assert av.x <= r.x and r.x + r.w <= av.x + av.w
    assert av.y <= r.y and r.y + r.h <= av.y + av.h
    assert abs((r.x - av.x) - (av.x + av.w - r.x - r.w)) <= 1
    assert abs((r.y - av.y) - (av.y + av.h - r.y - r.h)) <= 1


@pytest.mark.parametrize("size", [(-1, 10), (10, -1), (1.5, 10), (True, 10)])
def test_center_in_rejects_bad_sizes(size):
    with pytest.raises(ValueError, match="size"):
        center_in(size, Rect(0, 0, 100, 100))
