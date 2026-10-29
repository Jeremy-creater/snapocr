snapocr — 截图 / OCR / 翻译，全程在本机
=====================================

使用
  1. 双击 snapocr.exe。没有窗口弹出，图标在右下角托盘里（可能藏在“^”里）。
  2. 第一次运行时 Windows 可能提示“Windows 已保护你的电脑”：点“更多信息”→“仍要运行”。
     这是因为程序没有付费的代码签名，不是病毒。
  3. 热键：
     Alt+1 截图（可标注、贴图、另存为）    Alt+2 截图识别文字
     Alt+3 截图翻译                        Alt+4 输入文字翻译
     Alt+5 识别代码（保留缩进）            Alt+6 识别表格
     热键、开机自启动等在托盘菜单的“设置”里改。

翻译
  截图和识别文字不需要别的软件。翻译要另装 Ollama 和翻译模型，步骤见
  https://github.com/Jeremy-creater/snapocr/blob/main/README.zh-CN.md

文件位置
  配置文件  %APPDATA%\snapocr\config.toml
  日志      %LOCALAPPDATA%\snapocr

卸载
  先在“设置”里关掉“开机自启动”，退出 snapocr，再删除这个文件夹，
  以及 %APPDATA%\snapocr 和 %LOCALAPPDATA%\snapocr。

许可证：MIT（LICENSE），第三方组件见 THIRD_PARTY_NOTICES.md。


snapocr — screenshot / OCR / translation, fully local
====================================================

Usage
  1. Double-click snapocr.exe. No window opens; the icon is in the tray (maybe under "^").
  2. On the first start Windows may say "Windows protected your PC": click "More info",
     then "Run anyway". The app has no paid code-signing certificate.
  3. Hotkeys: Alt+1 screenshot, Alt+2 OCR, Alt+3 screenshot translation,
     Alt+4 text translation, Alt+5 code OCR, Alt+6 table OCR.
     Change them, and start-with-Windows, in Settings (tray menu). The interface is in Chinese.

Translation needs Ollama and a translation model; see
https://github.com/Jeremy-creater/snapocr#set-up-translation-optional

Files: config %APPDATA%\snapocr\config.toml, logs %LOCALAPPDATA%\snapocr.
Uninstall: turn off start-with-Windows in Settings, quit snapocr, delete this folder,
%APPDATA%\snapocr and %LOCALAPPDATA%\snapocr.

License: MIT (LICENSE); third-party components: THIRD_PARTY_NOTICES.md.
