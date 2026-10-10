# ============================================================
#  OpenCutStudio - Build + Package Release Script (PowerShell)
#  Output: dist\OpenCutStudio_vX.Y.Z\
#          dist\OpenCutStudio_vX.Y.Z.zip
# ============================================================
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$APP_NAME  = "OpenCutStudio"
$VERSION   = "2.9.6"
if (Test-Path "version.json") {
    try {
        $vJson = Get-Content "version.json" -Raw | ConvertFrom-Json
        if ($vJson.version) { $VERSION = $vJson.version.Trim() }
    } catch {}
}
$SPEC_FILE = "OpenCutStudio.spec"
$PYTHON    = ".venv\Scripts\python.exe"
$RELEASE   = "dist\${APP_NAME}_v${VERSION}"
$ZIP_OUT   = "dist\${APP_NAME}_v${VERSION}.zip"

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  $APP_NAME - Release Build v$VERSION" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Prerequisites & Frontend Build ──────────────────────────
Write-Host "[1/6] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Path $PYTHON)) {
    throw "ERROR: .venv not found. Run setup.bat first."
}

# Build Web Frontend if node/npm exists
if (Test-Path "web\package.json") {
    Write-Host "  Building Web Frontend (Vite/React)..." -ForegroundColor Gray
    Push-Location "web"
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "npm run build returned non-zero code. Using existing web/dist if available."
        }
    } catch {
        Write-Warning "npm run build failed: $_. Using existing web/dist if available."
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path "web\dist\index.html")) {
    throw "ERROR: web\dist\index.html not found. Run 'npm run build' inside web directory first."
}
Write-Host "  Web Frontend OK" -ForegroundColor Green

# Find ffmpeg / ffprobe / ffplay
$ffmpegPath  = $null
$ffprobePath = $null
$ffplayPath  = $null
foreach ($candidate in @("ffmpeg.exe", "C:\ffmpeg\bin\ffmpeg.exe", "C:\ffmpeg\ffmpeg.exe")) {
    if (Test-Path $candidate) { $ffmpegPath = (Resolve-Path $candidate).Path; break }
}
if (-not $ffmpegPath) {
    $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($cmd) { $ffmpegPath = $cmd.Source }
}
if (-not $ffmpegPath) { throw "ERROR: ffmpeg.exe not found. Install from https://ffmpeg.org/download.html" }

foreach ($candidate in @("ffprobe.exe", "C:\ffmpeg\bin\ffprobe.exe", "C:\ffmpeg\ffprobe.exe")) {
    if (Test-Path $candidate) { $ffprobePath = (Resolve-Path $candidate).Path; break }
}
if (-not $ffprobePath) {
    $cmd2 = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($cmd2) { $ffprobePath = $cmd2.Source }
}
if (-not $ffprobePath) {
    $ffprobePath = $ffmpegPath -replace "ffmpeg.exe","ffprobe.exe"
}

foreach ($candidate in @("ffplay.exe", "C:\ffmpeg\bin\ffplay.exe", "C:\ffmpeg\ffplay.exe")) {
    if (Test-Path $candidate) { $ffplayPath = (Resolve-Path $candidate).Path; break }
}
if (-not $ffplayPath) {
    $cmd3 = Get-Command ffplay -ErrorAction SilentlyContinue
    if ($cmd3) { $ffplayPath = $cmd3.Source }
}

Write-Host "  ffmpeg  : $ffmpegPath"
Write-Host "  ffprobe : $ffprobePath"
if ($ffplayPath) { Write-Host "  ffplay  : $ffplayPath" }

# Ensure PyInstaller is installed
& $PYTHON -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
    & $PYTHON -m pip install pyinstaller --quiet
}
Write-Host "  Prerequisites OK" -ForegroundColor Green
Write-Host ""

# ── 2. Strip API keys from config before bundling ────────────
Write-Host "[2/5] Sanitizing config.json (removing API keys)..." -ForegroundColor Yellow
$cfgPath = "config.json"
$cfgOrig = Get-Content $cfgPath -Raw
$cfg = $cfgOrig | ConvertFrom-Json
$cfg.api_keys    = @("")
if ($cfg.PSObject.Properties["api_key"]) { $cfg.api_key = "" }
$cfg.video_files = @()
$cfg.output_folder = ""
# Write clean config as temp file — restore original after build
$cleanJson = $cfg | ConvertTo-Json -Depth 10
$cleanJson | Set-Content $cfgPath -Encoding UTF8
Write-Host "  OK (original will be restored after build)" -ForegroundColor Green
Write-Host ""

# ── 3. Clean old artifacts ───────────────────────────────────
Write-Host "[3/5] Cleaning old build artifacts..." -ForegroundColor Yellow
if (Test-Path "build\$APP_NAME")    { Remove-Item "build\$APP_NAME"    -Recurse -Force }
if (Test-Path "dist\$APP_NAME.exe") { Remove-Item "dist\$APP_NAME.exe" -Force }
if (Test-Path $RELEASE)             { Remove-Item $RELEASE             -Recurse -Force }
if (Test-Path $ZIP_OUT)             { Remove-Item $ZIP_OUT             -Force }
Write-Host "  OK" -ForegroundColor Green
Write-Host ""

# ── 4. Build EXE ─────────────────────────────────────────────
Write-Host "[4/5] Building EXE with PyInstaller (3-6 min)..." -ForegroundColor Yellow
Write-Host ""
try {
    & $PYTHON -m PyInstaller $SPEC_FILE --clean --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited with code $LASTEXITCODE" }
} finally {
    # Always restore original config — even if build fails
    $cfgOrig | Set-Content $cfgPath -Encoding UTF8
    Write-Host ""
    Write-Host "  config.json restored." -ForegroundColor Gray
}
Write-Host "  Build OK" -ForegroundColor Green
Write-Host ""

# ── 5. Assemble release folder ───────────────────────────────
Write-Host "[5/5] Assembling release package..." -ForegroundColor Yellow

# Kill any running media tools or prior instances that might hold file locks
Get-Process -Name "ffmpeg", "ffprobe", "ffplay", "$APP_NAME" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

New-Item $RELEASE -ItemType Directory -Force | Out-Null

Copy-Item "dist\$APP_NAME.exe" "$RELEASE\$APP_NAME.exe" -Force
Write-Host "  + $APP_NAME.exe"

Copy-Item $ffmpegPath  "$RELEASE\ffmpeg.exe" -Force
Write-Host "  + ffmpeg.exe"

if (Test-Path $ffprobePath) {
    Copy-Item $ffprobePath "$RELEASE\ffprobe.exe" -Force
    Write-Host "  + ffprobe.exe"
}

if ($ffplayPath -and (Test-Path $ffplayPath)) {
    Copy-Item $ffplayPath "$RELEASE\ffplay.exe" -Force
    Write-Host "  + ffplay.exe"
}

# Copy sanitized template config.json
$cleanJson | Set-Content "$RELEASE\config.json" -Encoding UTF8
Write-Host "  + config.json (clean template)"

if (Test-Path "version.json") {
    Copy-Item "version.json" "$RELEASE\version.json" -Force
    Write-Host "  + version.json"
}

# Copy fonts directory
if (Test-Path "fonts") {
    Copy-Item "fonts" "$RELEASE\fonts" -Recurse -Force
    Write-Host "  + fonts\"
}

# Copy edit_presets directory
if (Test-Path "edit_presets") {
    Copy-Item "edit_presets" "$RELEASE\edit_presets" -Recurse -Force
    Write-Host "  + edit_presets\"
}

# Create runtime directories and copy models if present
New-Item "$RELEASE\overlay_assets\cutouts" -ItemType Directory -Force | Out-Null
New-Item "$RELEASE\overlay_assets\models"  -ItemType Directory -Force | Out-Null
New-Item "$RELEASE\temp_uploads"           -ItemType Directory -Force | Out-Null
if (Test-Path "overlay_assets\models") {
    Copy-Item "overlay_assets\models\*" "$RELEASE\overlay_assets\models\" -Force
    Write-Host "  + overlay_assets\models\ (AI segmentation models)"
}
Write-Host "  + overlay_assets\ & temp_uploads\"

# Write README.txt
@"
$APP_NAME v$VERSION
========================================

Requirements:
  - Windows 10/11 64-bit
  - Internet connection (for Google Gemini AI)
  - A FREE Google Gemini API key
    Get one at: https://aistudio.google.com/apikey

How to run:
  1. Extract the ZIP to any folder (e.g. Desktop or C:\OpenCutStudio)
  2. Double-click $APP_NAME.exe
  3. The app automatically launches and opens in your default browser

First run:
  1. Enter your Gemini API key in the Settings / API panel
  2. Select video files or drag & drop them into the studio
  3. Analyze videos, detect highlights, edit subtitles, overlays & layers, and export!

Included in v${VERSION}:
  - Complete Standalone Package: OpenCutStudio.exe + FFmpeg suite bundled
  - RapidOCR ONNX Runtime & OpenCV: Auto-detect subtitles & object tracking blur
  - Google Gemini AI: Fast audio/video transcription, highlights & viral titles
  - BiRefNet & Overlay Engine: Background removal, transparent WebM/PNG overlays
  - Hardware Acceleration: Auto-detects NVIDIA NVENC / Intel QSV / AMD AMF
  - Multi-track timeline & synced subtitle editing
  - Full Unicode / UTF-8 support for Vietnamese text, titles, subtitles & filenames

Notes:
  - Keep ffmpeg.exe and ffprobe.exe in the SAME folder as $APP_NAME.exe
  - Your API key, settings, and edit history are saved automatically
"@ | Set-Content "$RELEASE\README.txt" -Encoding UTF8
Write-Host "  + README.txt"

# ZIP the release using Python shutil (most reliable on Windows)
Write-Host ""
Write-Host "  Creating ZIP..." -ForegroundColor Gray

if (Test-Path $ZIP_OUT) { Remove-Item $ZIP_OUT -Force }

$relAbs = (Resolve-Path $RELEASE).Path
$zipBase = $ZIP_OUT -replace "\.zip$",""
$zipAbs = (Join-Path (Get-Location) $zipBase)

& $PYTHON -c "import shutil; shutil.make_archive(r'$zipAbs', 'zip', r'$relAbs')"

if (-not (Test-Path $ZIP_OUT)) {
    Write-Host "  Falling back to PowerShell Compress-Archive..." -ForegroundColor Yellow
    Compress-Archive -Path "$RELEASE\*" -DestinationPath $ZIP_OUT -CompressionLevel Optimal -Force
}

$exeMB  = [math]::Round((Get-Item "$RELEASE\$APP_NAME.exe").Length / 1MB, 1)
$zipMB  = [math]::Round((Get-Item $ZIP_OUT).Length / 1MB, 1)

Write-Host ""
Write-Host "====================================================" -ForegroundColor Green
Write-Host "  RELEASE READY!" -ForegroundColor Green
Write-Host "  Folder : $RELEASE"
Write-Host "  EXE    : $APP_NAME.exe  (~$exeMB MB)"
Write-Host "  ZIP    : $ZIP_OUT  (~$zipMB MB)"
Write-Host "====================================================" -ForegroundColor Green
Write-Host ""

# Open release folder in Explorer
Start-Process "explorer.exe" (Resolve-Path $RELEASE)

