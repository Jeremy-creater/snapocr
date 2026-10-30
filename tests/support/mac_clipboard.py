"""The real Mac pasteboard for the gui-mac lane (M9 WI-21): read it, save it and put it back.

Tests that write the clipboard take a ``snapshot()`` first and ``restore`` it
after, so the user's clipboard is what it was (CLAUDE.md). Through libobjc,
like the snapocr code itself; no third-party package.
"""

from __future__ import annotations

import ctypes

from snapocr.gui.platform.mac import _cocoa as c

PNG = "public.png"
Snapshot = list[list[tuple[str, bytes]]]  # items, each a list of (type, data)


def _ns_string(text: str):
    return c.send(c.ns_class("NSString"), "stringWithUTF8String:", text.encode(), argtypes=(ctypes.c_char_p,))


def _py_string(ns) -> str:
    return c.send(ns, "UTF8String", restype=ctypes.c_char_p).decode()


def _list(ns_array) -> list:
    count = c.send(ns_array, "count", restype=ctypes.c_ulong)
    return [c.send(ns_array, "objectAtIndex:", i, argtypes=(ctypes.c_ulong,)) for i in range(count)]


def _bytes(ns_data) -> bytes:
    length = c.send(ns_data, "length", restype=ctypes.c_ulong)
    return ctypes.string_at(c.send(ns_data, "bytes"), length) if length else b""


def _board():
    return c.send(c.ns_class("NSPasteboard"), "generalPasteboard")


def types() -> list[str]:
    array = c.send(_board(), "types")
    return [_py_string(t) for t in _list(array)] if array else []


def read(kind: str) -> bytes | None:
    data = c.send(_board(), "dataForType:", _ns_string(kind), argtypes=(c.vp,))
    return _bytes(data) if data else None


def snapshot() -> Snapshot:
    items = c.send(_board(), "pasteboardItems")
    saved: Snapshot = []
    for item in _list(items) if items else []:
        entry = []
        for t in _list(c.send(item, "types")):
            data = c.send(item, "dataForType:", t, argtypes=(c.vp,))
            if data:
                entry.append((_py_string(t), _bytes(data)))
        saved.append(entry)
    return saved


def restore(saved: Snapshot) -> None:
    board = _board()
    c.send(board, "clearContents", restype=ctypes.c_long)
    if not saved:
        return
    array = c.send(c.ns_class("NSMutableArray"), "array")
    for entry in saved:
        item = c.send(c.send(c.ns_class("NSPasteboardItem"), "alloc"), "init")
        for kind, data in entry:
            ns_data = c.send(c.ns_class("NSData"), "dataWithBytes:length:", data, len(data),
                             argtypes=(ctypes.c_char_p, ctypes.c_ulong))
            c.send(item, "setData:forType:", ns_data, _ns_string(kind), argtypes=(c.vp, c.vp), restype=ctypes.c_bool)
        c.send(array, "addObject:", item, argtypes=(c.vp,), restype=None)
    c.send(board, "writeObjects:", array, argtypes=(c.vp,), restype=ctypes.c_bool)
