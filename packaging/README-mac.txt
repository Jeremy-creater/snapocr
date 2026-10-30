snapocr — 截图 / OCR / 翻译，全程在本机
=====================================

安装
  把 snapocr.app 拖进“应用程序”文件夹。需要 Apple 芯片的 Mac。

使用
  1. 双击 snapocr.app。没有窗口弹出，图标在屏幕顶部的菜单栏里。
  2. 第一次打开 macOS 可能拦下它（程序没有 Apple 开发者签名）：到
     “系统设置 → 隐私与安全性”，往下找到 snapocr，点“仍要打开”。
  3. 截图要“屏幕录制”权限：按提示在“系统设置 → 隐私与安全性 → 屏幕与系统录音”里
     打开 snapocr，再重启它。换新版本后可能要重新授权。如果开关已打开却仍然反复提示，
     退出 snapocr，在“终端”里运行下面这行，再打开 snapocr 重新授权并重启它：
     tccutil reset ScreenCapture io.github.jeremy-creater.snapocr
  4. 热键：
     Option+1 截图（可标注、贴图、另存为）  Option+2 截图识别文字
     Option+3 截图翻译                      Option+4 输入文字翻译
     Option+5 识别代码（保留缩进）          Option+6 识别表格
     热键、开机自启动等在菜单栏图标的“设置”里改。移动 snapocr.app 后，要重新勾选开机自启动。

翻译
  截图和识别文字不需要别的软件。翻译要另装 Ollama 和翻译模型，步骤见
  https://github.com/Jeremy-creater/snapocr/blob/main/README.zh-CN.md

文件位置
  配置文件  ~/Library/Application Support/snapocr/config.toml
  日志      ~/Library/Logs/snapocr

卸载
  先在“设置”里关掉“开机自启动”，退出 snapocr，再把 snapocr.app 移到废纸篓，
  并删除上面两个位置的 snapocr 文件夹。

许可证：MIT。许可证和第三方组件说明在 snapocr.app/Contents/Resources 里。


snapocr — screenshot / OCR / translation, fully local
====================================================

Install: drag snapocr.app to Applications. Needs an Apple Silicon Mac.

Usage
  1. Double-click snapocr.app. No window opens; the icon is in the menu bar.
  2. If macOS blocks the first start (the app has no Apple developer signature), go to
     System Settings > Privacy & Security, find snapocr and click "Open Anyway".
  3. Screenshots need the Screen Recording permission: turn on snapocr under System Settings >
     Privacy & Security > Screen & System Audio Recording, then restart it. A new version may
     need it again. If it keeps asking although the switch is on, quit snapocr, run this in
     Terminal, then open snapocr, grant the permission again and restart it:
     tccutil reset ScreenCapture io.github.jeremy-creater.snapocr
  4. Hotkeys: Option+1 screenshot, Option+2 OCR, Option+3 screenshot translation,
     Option+4 text translation, Option+5 code OCR, Option+6 table OCR.
     Change them, and start at login, in Settings (menu bar icon). The interface is in Chinese.
     After moving snapocr.app, tick start at login again.

Translation needs Ollama and a translation model; see
https://github.com/Jeremy-creater/snapocr#set-up-translation-optional

Files: config ~/Library/Application Support/snapocr/config.toml, logs ~/Library/Logs/snapocr.
Uninstall: turn off start at login in Settings, quit snapocr, move snapocr.app to the Trash, and
delete the snapocr folders in those two locations.

License: MIT. License files and third-party notices are in snapocr.app/Contents/Resources.
