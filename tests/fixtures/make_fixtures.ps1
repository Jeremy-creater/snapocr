# Regenerates the static OCR sample images in this directory.
#
# Tests only READ the committed PNGs; they never call this script. Rendering
# depends on the installed font version and text-rendering settings, so
# regenerating may change bytes (and the recorded engine numbers). Re-run the
# engine lane after regenerating and review the diff before committing.
#
# Usage (PowerShell 7 on Windows):
#   pwsh -NoProfile -File tests\fixtures\make_fixtures.ps1 [-OutDir <dir>]
#
# Every image: white background, Microsoft YaHei, 24bpp RGB (no alpha).
# Every ground-truth .txt: UTF-8 without BOM, LF line endings, one line per
# rendered text line. All text is synthetic and privacy-free.

param(
    [string]$OutDir = $PSScriptRoot
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
    $png = Join-Path $OutDir "$Name.png"
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
