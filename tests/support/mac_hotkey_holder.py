"""Hold a Carbon hotkey in a separate process, as another program would (gui-mac lane, M9).

``python mac_hotkey_holder.py "<combination>" <seconds>`` prints ``REGISTERED <status>``,
then ``FIRED`` for each press, and exits after ``seconds``.
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from snapocr.gui.platform.mac.hotkeys import CarbonHotkeys
from snapocr.hotkeys import parse_hotkey

if __name__ == "__main__":
    app = QApplication(sys.argv)
    hotkey = parse_hotkey(sys.argv[1], platform="darwin")
    backend = CarbonHotkeys()
    backend.activated.connect(lambda _: print("FIRED", flush=True))
    print("REGISTERED", backend.register(1, hotkey.mods, hotkey.vk), flush=True)
    QTimer.singleShot(int(sys.argv[2]) * 1000, app.quit)
    app.exec()
    backend.close()
