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
# rendered text line. All text is synthetic and privacy-free.

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
