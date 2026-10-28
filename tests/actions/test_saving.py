"""M4 WI-21, WI-25: writing the screenshot file (PRD v1.1 F17-1, F17-3, F17-4; plan D29; unit lane).

Pinned here:
- File names are ``snapocr_YYYYMMDD_HHMMSS.png``, then ``_2``, ``_3`` ... for
  the same second.
- ``suggest_path``: the save-as dialog's preset, the first of those names not
  yet in the save folder; the folder (and its parents) is created first, and
  a folder that cannot be created is left to the dialog (no error).
- ``save_flow`` writes the file the user picked, replacing an existing one
  (the dialog asked first). Saved or not, the PNG goes to the clipboard;
  success has no notice, failure says why and names the file.
- Everything writes under ``tmp_path`` (CLAUDE.md).
"""

import datetime
from itertools import islice
from pathlib import Path

from snapocr.actions.messages import save_failed_notice
from snapocr.actions.outcomes import ClipboardPng, Notice, Outcome
from snapocr.actions.saving import save_flow, save_names, suggest_path

PNG = b"\x89PNG\r\n\x1a\nfake image"
NOW = datetime.datetime(2026, 10, 27, 21, 5, 9, 123456)
FIRST = "snapocr_20261027_210509.png"


def test_names_count_up_within_one_second():
    assert list(islice(save_names(NOW), 4)) == [
        FIRST,
        "snapocr_20261027_210509_2.png",
        "snapocr_20261027_210509_3.png",
        "snapocr_20261027_210509_4.png",
    ]


def test_names_pad_single_digits():
    assert next(save_names(datetime.datetime(2027, 1, 2, 3, 4, 5))) == "snapocr_20270102_030405.png"


def test_suggest_the_first_name_in_an_empty_folder(tmp_path):
    assert suggest_path(tmp_path, NOW) == tmp_path / FIRST
    assert list(tmp_path.iterdir()) == []


def test_suggest_skips_names_already_taken(tmp_path):
    (tmp_path / FIRST).write_bytes(b"first")
    (tmp_path / "snapocr_20261027_210509_2.png").write_bytes(b"second")
    assert suggest_path(tmp_path, NOW) == tmp_path / "snapocr_20261027_210509_3.png"
    assert (tmp_path / FIRST).read_bytes() == b"first"


def test_suggest_creates_the_missing_folder(tmp_path):
    folder = tmp_path / "a" / "b"
    assert suggest_path(folder, NOW) == folder / FIRST
    assert folder.is_dir()
    assert list(folder.iterdir()) == []


def test_suggest_leaves_an_impossible_folder_to_the_dialog(tmp_path):
    blocker = tmp_path / "taken"
    blocker.write_bytes(b"a file where the folder should be")
    assert suggest_path(blocker / "shots", NOW) == blocker / "shots" / FIRST
    assert blocker.read_bytes() == b"a file where the folder should be"


def test_save_writes_the_picked_file_and_copies_without_notice(tmp_path):
    path = tmp_path / "my shot.png"
    out = save_flow(PNG, path)
    assert path.is_file()
    assert path.read_bytes() == PNG
    assert out == Outcome(ClipboardPng(PNG), None, None)


def test_save_replaces_a_file_the_dialog_confirmed(tmp_path):
    path = tmp_path / FIRST
    path.write_bytes(b"old")
    assert save_flow(PNG, path) == Outcome(ClipboardPng(PNG), None, None)
    assert path.read_bytes() == PNG


def test_failure_still_copies_and_names_the_file(tmp_path):
    blocker = tmp_path / "taken"
    blocker.write_bytes(b"a file where the folder should be")
    path = blocker / FIRST
    out = save_flow(PNG, path)
    assert out.clipboard == ClipboardPng(PNG)
    assert out.record is None
    assert out.notice is not None
    assert out.notice.title == "保存失败"
    assert str(path) in out.notice.body
    assert blocker.read_bytes() == b"a file where the folder should be"


def test_failed_notice_text():
    path = Path("D:/shots/snapocr_20261027_210509.png")
    # M5 WI-3 (F18-3): a failure, so with the warning icon.
    assert save_failed_notice(path, "拒绝访问。") == Notice("保存失败", f"拒绝访问。\n{path}", warning=True)
