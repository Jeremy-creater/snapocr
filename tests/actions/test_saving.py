"""M4 WI-21: saving the screenshot into the save folder (PRD F17-1, F17-3, F17-4; unit lane).

Pinned here:
- File names are ``snapocr_YYYYMMDD_HHMMSS.png``, then ``_2``, ``_3`` ... for
  the same second; an existing file is never overwritten.
- The folder (and its parents) is created when missing.
- Saved or not, the PNG goes to the clipboard (F17-1, F17-4); the notice
  names the file, or the folder and the reason.
- Everything writes under ``tmp_path`` (CLAUDE.md).
"""

import datetime
from itertools import islice
from pathlib import Path

from snapocr.actions.messages import save_failed_notice, save_ok_notice
from snapocr.actions.outcomes import ClipboardPng, Notice, Outcome
from snapocr.actions.saving import save_flow, save_names

PNG = b"\x89PNG\r\n\x1a\nfake image"
NOW = datetime.datetime(2026, 10, 27, 21, 5, 9, 123456)


def test_names_count_up_within_one_second():
    assert list(islice(save_names(NOW), 4)) == [
        "snapocr_20261027_210509.png",
        "snapocr_20261027_210509_2.png",
        "snapocr_20261027_210509_3.png",
        "snapocr_20261027_210509_4.png",
    ]


def test_names_pad_single_digits():
    assert next(save_names(datetime.datetime(2027, 1, 2, 3, 4, 5))) == "snapocr_20270102_030405.png"


def test_save_writes_the_png_and_copies_it(tmp_path):
    out = save_flow(PNG, tmp_path, NOW)
    path = tmp_path / "snapocr_20261027_210509.png"
    assert path.read_bytes() == PNG
    assert out == Outcome(ClipboardPng(PNG), save_ok_notice(path), None)
    assert out.notice == Notice("已保存截图", str(path))


def test_save_creates_missing_folders(tmp_path):
    folder = tmp_path / "a" / "b"
    save_flow(PNG, folder, NOW)
    assert (folder / "snapocr_20261027_210509.png").read_bytes() == PNG


def test_existing_files_are_never_overwritten(tmp_path):
    (tmp_path / "snapocr_20261027_210509.png").write_bytes(b"first")
    (tmp_path / "snapocr_20261027_210509_2.png").write_bytes(b"second")
    out = save_flow(PNG, tmp_path, NOW)
    third = tmp_path / "snapocr_20261027_210509_3.png"
    assert third.read_bytes() == PNG
    assert (tmp_path / "snapocr_20261027_210509.png").read_bytes() == b"first"
    assert (tmp_path / "snapocr_20261027_210509_2.png").read_bytes() == b"second"
    assert out.notice == save_ok_notice(third)


def test_two_saves_in_one_second_keep_both(tmp_path):
    save_flow(PNG, tmp_path, NOW)
    save_flow(PNG + b"2", tmp_path, NOW)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["snapocr_20261027_210509.png", "snapocr_20261027_210509_2.png"]
    assert (tmp_path / "snapocr_20261027_210509_2.png").read_bytes() == PNG + b"2"


def test_failure_still_copies_and_names_the_folder(tmp_path):
    blocker = tmp_path / "taken"
    blocker.write_bytes(b"a file where the folder should be")
    folder = blocker / "shots"
    out = save_flow(PNG, folder, NOW)
    assert out.clipboard == ClipboardPng(PNG)
    assert out.record is None
    assert out.notice.title == "保存失败"
    assert str(folder) in out.notice.body
    assert blocker.read_bytes() == b"a file where the folder should be"


def test_failed_notice_text():
    folder = Path("D:/shots")
    assert save_failed_notice(folder, "拒绝访问。") == Notice("保存失败", f"拒绝访问。\n{folder}")
