# Build script for Signum Savotta installer
# Produces: dist\SignumSavottaSetup.exe
#
# Usage:
#   .\build.ps1
#   .\build.ps1 -InnoSetupPath "D:\Tools\InnoSetup6\ISCC.exe"
#
# Prerequisites:
#   - Poetry  (https://python-poetry.org)
#   - Inno Setup 6  (https://jrsoftware.org/issetup.php)

param(
    [string]$InnoSetupPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Locate Inno Setup compiler
# ---------------------------------------------------------------------------
if ($InnoSetupPath -eq "") {
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Users\MikkoVihonen\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $InnoSetupPath = $c; break }
    }
}
if ($InnoSetupPath -eq "" -or -not (Test-Path $InnoSetupPath)) {
    Write-Error @"
Inno Setup 6 compiler not found.
Install it from https://jrsoftware.org/issetup.php or pass the path:
  .\build.ps1 -InnoSetupPath "C:\path\to\ISCC.exe"
"@
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Compile Qt resources
# ---------------------------------------------------------------------------
Write-Host "==> Compiling Qt resources..."
poetry run pyside6-rcc assets.qrc -o src/assets_rc.py

# ---------------------------------------------------------------------------
# 2. Build the application with PyInstaller
# ---------------------------------------------------------------------------
Write-Host "==> Building application..."
poetry run pyinstaller main.spec --clean --noconfirm

# ---------------------------------------------------------------------------
# 3. Compile the Inno Setup installer
#    The installer bundles config.ini.example (all updated settings, empty
#    [registration]) and migrates the real registration from any existing
#    installation at install time — see installer.iss [Code] section.
# ---------------------------------------------------------------------------
Write-Host "==> Compiling installer..."
& $InnoSetupPath "installer.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Inno Setup compilation failed (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==> Done: dist\SignumSavottaSetup.exe"
