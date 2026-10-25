# Regenerates the static OCR sample images in this directory.
#
# Tests only READ the committed PNGs; they never call this script. Rendering
# depends on the installed font version and text-rendering settings, so
# regenerating may change bytes (and the recorded engine numbers). Re-run the
# engine lane after regenerating and review the diff before committing.
#
# Usage (PowerShell 7 on Windows):
#   pwsh -NoProfile -File tests\fixtures\make_fixtures.ps1 [-OutDir <dir>] [-Force]
#
# By default an image whose .png already exists in -OutDir is SKIPPED (both
# the .png and its .txt), so adding a new fixture never rewrites committed
# ones. Pass -Force to regenerate everything, then check `git diff --stat`.
# To compare without touching the repo, render into a scratch -OutDir.
#
# Every image: white background, Microsoft YaHei, 24bpp RGB (no alpha).
# Every ground-truth .txt: UTF-8 without BOM, LF line endings, one line per
# rendered text line (an empty string renders as an empty line and is kept
# as an empty line in the .txt). All text is synthetic and privacy-free.
#
# -Expected writes <Name>.expected.txt (same encoding rules): the exact text
# post-processing must produce from the image (F2, plan WI-8), one line per
# output line. It is skipped together with the .png.

param(
    [string]$OutDir = $PSScriptRoot,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$FontName = 'Microsoft YaHei'

function New-TextImage {
    param(
        [string]$Name,
        [int]$Width,
        [int]$Height,
        [string[]]$Lines,
        [float]$FontPt = 28,
        [int]$Gray = 0,
        [int]$Left = 24,
        [int]$Top = 22,
        [int]$LineStep = 82,
        [string[]]$Expected = @(),
        [switch]$NoTruth
    )
    $png = Join-Path $OutDir "$Name.png"
    if ((Test-Path -LiteralPath $png) -and -not $Force) {
        Write-Output "skip $png (exists; use -Force to regenerate)"
        return
    }
    $bmp = New-Object System.Drawing.Bitmap($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $g.Clear([System.Drawing.Color]::White)
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
        $font = New-Object System.Drawing.Font($FontName, $FontPt, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Point)
        $brush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, $Gray, $Gray, $Gray))
        for ($i = 0; $i -lt $Lines.Count; $i++) {
            $g.DrawString($Lines[$i], $font, $brush, [float]$Left, [float]($Top + $i * $LineStep))
        }
        $font.Dispose()
        $brush.Dispose()
    }
    finally {
        $g.Dispose()
    }
    $bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()

    if ($Lines.Count -gt 0 -and -not $NoTruth) {
        $txt = Join-Path $OutDir "$Name.txt"
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($txt, (($Lines -join "`n") + "`n"), $utf8)
    }
    if ($Expected.Count -gt 0) {
        $exp = Join-Path $OutDir "$Name.expected.txt"
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($exp, (($Expected -join "`n") + "`n"), $utf8)
    }
    Write-Output "wrote $png"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# Mixed Chinese / English, two lines, 900x200.
New-TextImage -Name 'mixed' -Width 900 -Height 200 -Lines @(
    '使用Python3截图识别，自动复制到剪贴板。',
    'Hello World, snapocr 123 test.'
)

# Pure white, no text, same size.
New-TextImage -Name 'blank' -Width 900 -Height 200 -Lines @()

# Tiny (3pt) text: exists only to produce blocks whose recognition score is
# below 0.5, proving Global.text_score=0.0 reaches RapidOCR. Recognition is
# expected to be wrong, so no ground-truth .txt is written for it.
New-TextImage -Name 'lowconf' -Width 900 -Height 200 -FontPt 3 -LineStep 40 -NoTruth -Lines @(
    '使用Python3截图识别，自动复制到剪贴板。',
    'Hello World, snapocr 123 test.',
    '极小号文字用于测试置信度阈值。',
    'Tiny text for the 0.5 threshold.'
)

# Pure Chinese, three lines, 1000x280. Synthetic, privacy-free text.
New-TextImage -Name 'zh' -Width 1000 -Height 280 -Lines @(
    '今天天气晴朗，适合在公园里散步和读书。',
    '截图识别的文字会自动复制到剪贴板中。',
    '样例图片统一放在测试目录下管理。'
)

# Pure English, three lines, 1120x280 (line 2 is ~1050px wide). Synthetic, privacy-free text.
New-TextImage -Name 'en' -Width 1120 -Height 280 -Lines @(
    'The quick brown fox jumps over the lazy dog.',
    'Screenshots are recognized and copied to the clipboard.',
    'Sample text 2026, version 0.1, no private data.'
)

# Dense 1920x1080 page for the manual latency test (WI-10, PRD §8). Twelve
# alternating zh / en lines, each well under 1870px wide. Only timing is
# measured, so no ground-truth .txt is written. Synthetic, privacy-free text.
New-TextImage -Name 'perf_1080p' -Width 1920 -Height 1080 -NoTruth -Lines @(
    '截图识别工具在后台常驻，按下快捷键后选择区域，识别结果自动进入剪贴板。',
    'The tray tool captures a region, recognizes the text and copies it to the clipboard.',
    '识别引擎在本地运行，不需要联网，模型文件随安装包一起提供。',
    'Recognition runs locally with bundled models and never touches the network.',
    '翻译功能调用本机的模型服务，原文和译文显示在浮动窗口里。',
    'Translation uses a local model service and shows source and result in a popup.',
    '如果识别结果有误，可以调出最近一次的原始识别文本进行核对。',
    'If a result looks wrong, the last raw recognition can be reopened for review.',
    '样例页面用于测量一张全高清截图从解码到输出结果所需的时间。',
    'This sample page measures how long a full HD screenshot takes end to end.',
    '数字和符号也会出现：版本 0.1，端口 11434，日期 2026-10-25。',
    'Numbers and symbols appear too: version 0.1, port 11434, date 2026-10-25.'
)

# Paragraph layout for F2 post-processing (plan WI-8, matrix rev 1), 1200x680.
# Line by line, each merge decision has exactly one blocking reason:
#   title            -> not merged only because it is not a full line;
#   lines 2+3        -> merged (full line, ends with a comma);
#   line 3 / line 4  -> not merged only because line 3 ends with a full stop;
#   line 4 / "第二段" -> not merged only because of the paragraph gap (the
#                       empty rendered line); line 4 is full and ends with a comma;
#   list 1 / list 2  -> not merged only because the next line is a list item.
# Lines 2, 3, 4 and 6 must render full: right - min left >= 0.85 * region width.
New-TextImage -Name 'wrap' -Width 1200 -Height 680 -Lines @(
    '第一章 概述',
    '截图识别工具在后台常驻，按下快捷键后选择屏幕上的一块区域，',
    '程序会识别其中的文字并自动复制到剪贴板，整个过程不需要联网。',
    '识别结果也可以在浮动窗口里查看，原文也可以随时用快捷键找回来，',
    '',
    '第二段正文从这里开始。',
    '1. 支持中文和英文混排的截图识别，结果自动进入剪贴板并保留段落',
    '2. 支持一键翻译'
) -Expected @(
    '第一章 概述',
    '截图识别工具在后台常驻，按下快捷键后选择屏幕上的一块区域，程序会识别其中的文字并自动复制到剪贴板，整个过程不需要联网。',
    '识别结果也可以在浮动窗口里查看，原文也可以随时用快捷键找回来，',
    '',
    '第二段正文从这里开始。',
    '1. 支持中文和英文混排的截图识别，结果自动进入剪贴板并保留段落',
    '2. 支持一键翻译'
)
