"""M2 WI-2: registering and releasing the global hotkeys (PRD F5-3, F5-5), with a fake table."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from snapocr.commands import Command
from snapocr.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    Hotkey,
    HotkeyFailure,
    RegistrationReport,
    hotkey_id,
    parse_hotkey,
    register_all,
    unregister_all,
)
from support.fake_hotkeys import (
    ERROR_HOTKEY_ALREADY_REGISTERED,
    OTHER_PROGRAM,
    FakeHotkeyTable,
)

# Ids written out independently: position in Command, from 1.
IDS = {
    Command.CAPTURE: 1,
    Command.OCR: 2,
    Command.TRANSLATE: 3,
    Command.TRANSLATE_TEXT: 4,
    Command.OPEN_CONFIG: 5,
    Command.QUIT: 6,
    Command.SETTINGS: 7,  # M3 WI-6: added at the end
    Command.CODE_OCR: 8,  # M3 WI-14 (F13-1): added at the end
    Command.TABLE_OCR: 9,  # M4 WI-15 (F16-1): added at the end
}

DEFAULTS = {
    Command.CAPTURE: parse_hotkey("Alt+1"),
    Command.OCR: parse_hotkey("Alt+2"),
    Command.TRANSLATE: parse_hotkey("Alt+3"),
    Command.TRANSLATE_TEXT: parse_hotkey("Alt+4"),
}


def test_command_members():
    assert [c.name for c in Command] == list(n.name for n in IDS)
    assert [c.value for c in Command] == ["capture", "ocr", "translate", "translate_text", "open_config", "quit",
                                         "settings", "code_ocr", "table_ocr"]


@pytest.mark.parametrize(("command", "expected"), sorted(IDS.items(), key=lambda kv: kv[1]))
def test_hotkey_id(command, expected):
    assert hotkey_id(command) == expected


def test_second_of_four_taken_by_other_program():
    table = FakeHotkeyTable()
    table.preoccupy(MOD_ALT, 0x32)
    report = register_all(DEFAULTS, table.register)
    assert report == RegistrationReport(
        registered={1: Command.CAPTURE, 3: Command.TRANSLATE, 4: Command.TRANSLATE_TEXT},
        failed=[HotkeyFailure(Command.OCR, "Alt+2", ERROR_HOTKEY_ALREADY_REGISTERED)],
    )
    assert table.snapshot() == {
        (MOD_ALT, 0x31): 1,
        (MOD_ALT, 0x32): OTHER_PROGRAM,
        (MOD_ALT, 0x33): 3,
        (MOD_ALT, 0x34): 4,
    }

    released = unregister_all(report, table.unregister)
    assert sorted(released) == [1, 3, 4]
    assert table.snapshot() == {(MOD_ALT, 0x32): OTHER_PROGRAM}


def test_registered_with_norepeat():
    table = FakeHotkeyTable()
    register_all({Command.QUIT: Hotkey(MOD_CONTROL | MOD_SHIFT, 0x51)}, table.register)
    assert table.ours == {6: (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x51)}


def test_all_succeed():
    table = FakeHotkeyTable()
    report = register_all(DEFAULTS, table.register)
    assert report == RegistrationReport(registered={IDS[c]: c for c in DEFAULTS}, failed=[])
    assert unregister_all(report, table.unregister) == [1, 2, 3, 4]
    assert table.snapshot() == {}


def test_all_fail_in_command_order():
    table = FakeHotkeyTable()
    for hk in DEFAULTS.values():
        table.preoccupy(hk.mods, hk.vk)
    before = table.snapshot()
    report = register_all(dict(reversed(list(DEFAULTS.items()))), table.register)
    assert report.registered == {}
    assert report.failed == [
        HotkeyFailure(c, f"Alt+{n}", ERROR_HOTKEY_ALREADY_REGISTERED) for n, c in enumerate(DEFAULTS, 1)
    ]
    assert unregister_all(report, table.unregister) == []
    assert table.snapshot() == before


def test_empty_bindings():
    table = FakeHotkeyTable()
    report = register_all({}, table.register)
    assert report == RegistrationReport(registered={}, failed=[])
    assert unregister_all(report, table.unregister) == []
    assert table.snapshot() == {}


def test_failure_text_is_canonical():
    table = FakeHotkeyTable()
    table.preoccupy(MOD_CONTROL | MOD_ALT, 0x70)
    report = register_all({Command.TRANSLATE: parse_hotkey(" alt + control + f1 ")}, table.register)
    assert report.failed == [HotkeyFailure(Command.TRANSLATE, "Ctrl+Alt+F1", ERROR_HOTKEY_ALREADY_REGISTERED)]


def test_same_combination_twice_later_command_fails():
    table = FakeHotkeyTable()
    hk = parse_hotkey("Alt+1")
    report = register_all({Command.OCR: hk, Command.CAPTURE: hk}, table.register)
    assert report.registered == {1: Command.CAPTURE}
    assert report.failed == [HotkeyFailure(Command.OCR, "Alt+1", ERROR_HOTKEY_ALREADY_REGISTERED)]


def test_other_error_codes_reported_as_given():
    report = register_all(DEFAULTS, lambda i, m, v: 5 if i == 3 else 0)
    assert report.registered == {1: Command.CAPTURE, 2: Command.OCR, 4: Command.TRANSLATE_TEXT}
    assert report.failed == [HotkeyFailure(Command.TRANSLATE, "Alt+3", 5)]


def test_unregister_failure_not_listed_as_released():
    table = FakeHotkeyTable()
    report = register_all(DEFAULTS, table.register)

    def flaky(i):
        return 1419 if i == 2 else table.unregister(i)

    assert unregister_all(report, flaky) == [1, 3, 4]
    assert table.snapshot() == {(MOD_ALT, 0x32): 2}


# --- properties ------------------------------------------------------------------

pool = st.sampled_from(
    [Hotkey(MOD_ALT, 0x31), Hotkey(MOD_ALT, 0x32), Hotkey(MOD_CONTROL, 0x31), Hotkey(MOD_ALT | MOD_SHIFT, 0x87)]
)
bindings_st = st.dictionaries(st.sampled_from(list(Command)), pool)
occupied_st = st.sets(pool)


@given(bindings_st, occupied_st)
def test_conservation(bindings, occupied):
    table = FakeHotkeyTable()
    for hk in occupied:
        table.preoccupy(hk.mods, hk.vk)
    report = register_all(bindings, table.register)

    ok = list(report.registered.values())
    bad = [f.command for f in report.failed]
    assert sorted(ok + bad, key=IDS.get) == sorted(bindings, key=IDS.get)
    assert not set(ok) & set(bad)
    assert all(i == IDS[c] for i, c in report.registered.items())

    # Expected failures: combination held by another program or by an earlier command.
    taken = set(occupied)
    expected_bad = []
    for c in sorted(bindings, key=IDS.get):
        if bindings[c] in taken:
            expected_bad.append(c)
        taken.add(bindings[c])
    assert bad == expected_bad
    assert all(f.error_code == ERROR_HOTKEY_ALREADY_REGISTERED for f in report.failed)
    assert all(parse_hotkey(f.hotkey_text) == bindings[f.command] for f in report.failed)


@given(bindings_st, occupied_st)
def test_register_then_unregister_restores_table(bindings, occupied):
    table = FakeHotkeyTable()
    for hk in occupied:
        table.preoccupy(hk.mods, hk.vk)
    before = table.snapshot()
    report = register_all(bindings, table.register)
    released = unregister_all(report, table.unregister)
    assert sorted(released) == sorted(report.registered)
    assert table.snapshot() == before
    assert table.ours == {}
