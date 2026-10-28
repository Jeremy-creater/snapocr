"""Hypothesis strategy for settings-window values (M3 WI-2 onwards): one distinct hotkey per command."""

from __future__ import annotations

from pathlib import Path

from hypothesis import strategies as st

from snapocr.config.schema import HOTKEY_COMMANDS
from snapocr.config.settings import Settings
from snapocr.hotkeys import Hotkey

_KEYS = [0x41 + n for n in range(26)] + [0x30 + n for n in range(10)] + [0x70 + n for n in range(24)]
hotkeys = st.builds(Hotkey, st.integers(1, 0xF), st.sampled_from(_KEYS))
# Absolute folders, with spaces, CJK and a UNC share; the default among them.
save_dirs = st.sampled_from([
    Path("E:/shots"), Path("D:/a b/截图"), Path("//nas/share/snap"), Path.home() / "Pictures" / "snapocr",
])


@st.composite
def window_settings(draw) -> Settings:
    keys = draw(st.lists(hotkeys, min_size=len(HOTKEY_COMMANDS), max_size=len(HOTKEY_COMMANDS), unique=True))
    return Settings(
        hotkeys=dict(zip(HOTKEY_COMMANDS, keys, strict=True)),
        paragraphs=draw(st.booleans()),
        spacing=draw(st.booleans()),
        punctuation=draw(st.booleans()),
        target_lang=draw(st.sampled_from(["auto", "zh", "en"])),
        model=draw(st.sampled_from(["hy-mt2:7b", "qwen3:8b", "llama3", "my/model:q4_K_M"])),
        show_text=draw(st.booleans()),  # M3 WI-11
        save_dir=draw(save_dirs),  # M4 WI-22
    )
