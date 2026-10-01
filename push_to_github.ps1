# ============================================================
# Push OpenCut Studio to GitHub (PowerShell Engine)
# ============================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Push OpenCut Studio to GitHub"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   OpenCut Bodycam Studio - Day code len GitHub" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Tim Git ──────────────────────────────────────────────
$gitExe = $null

# Kiem tra trong PATH
$cmd = Get-Command git -ErrorAction SilentlyContinue
if ($cmd) {
    $gitExe = $cmd.Source
}

# Kiem tra cac duong dan mac dinh
if (-not $gitExe) {
    $candidates = @(
        "C:\Program Files\Git\cmd\git.exe",
        "C:\Program Files\Git\bin\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\git.exe",
        "C:\Program Files (x86)\Git\cmd\git.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $gitExe = $c
            $env:PATH = (Split-Path $c) + ";" + $env:PATH
            break
        }
    }
}

if (-not $gitExe) {
    Write-Host "[!] Khong tim thay Git tren may tinh." -ForegroundColor Red
    Write-Host "Dang tien hanh cai dat Git tu dong qua winget..." -ForegroundColor Yellow
    winget install --id Git.Git -e --source winget
    if (Test-Path "C:\Program Files\Git\cmd\git.exe") {
        $gitExe = "C:\Program Files\Git\cmd\git.exe"
        $env:PATH = "C:\Program Files\Git\cmd;" + $env:PATH
    } else {
        Write-Host "[LOI] Khong the tim thay Git. Vui long cai Git tai: https://git-scm.com" -ForegroundColor Red
        Read-Host "Bam Enter de thoat..."
        exit 1
    }
}

$gitVer = (& $gitExe --version)
Write-Host "[OK] $gitVer" -ForegroundColor Green
Write-Host ""

# ── 2. Doc hoac nhap link GitHub Repo ───────────────────────
$existingRepo = ""
if (Test-Path "updater_config.json") {
    try {
        $cfg = Get-Content "updater_config.json" -Raw | ConvertFrom-Json
        $existingRepo = $cfg.github_repo
    } catch {}
}

Write-Host "Buoc 1: Mo trinh duyet vao: https://github.com/new" -ForegroundColor Yellow
Write-Host "        - Dat ten Repository (vi du: auto-highlight)" -ForegroundColor Gray
Write-Host "        - Chon Public" -ForegroundColor Gray
Write-Host "        - Khong tich vao Add README, gitignore" -ForegroundColor Gray
Write-Host "        - Bam 'Create repository'" -ForegroundColor Gray
Write-Host "Buoc 2: Copy link Repo (dang: https://github.com/tai_khoan/ten_repo.git)" -ForegroundColor Yellow
Write-Host ""

if ($existingRepo) {
    Write-Host "Link Repository hien tai: $existingRepo" -ForegroundColor Cyan
    $inputUrl = Read-Host "Nhap link GitHub moi (hoac bam Enter de giu nguyen)"
    if ([string]::IsNullOrWhiteSpace($inputUrl)) {
        $repoUrl = $existingRepo
    } else {
        $repoUrl = $inputUrl.Trim()
    }
} else {
    $repoUrl = Read-Host ">> Dan link GitHub Repository cua ban vao day"
}

if ([string]::IsNullOrWhiteSpace($repoUrl)) {
    Write-Host "[LOI] Ban chua nhap link GitHub repository." -ForegroundColor Red
    Read-Host "Bam Enter de thoat..."
    exit 1
}

# Lam sach link (bo .git o duoi neu co de lam link web)
$cleanWebUrl = $repoUrl -replace "\.git$",""
$cleanGitUrl = $cleanWebUrl + ".git"

# Luu vao updater_config.json
$updateCfg = @{ github_repo = $cleanWebUrl } | ConvertTo-Json
$updateCfg | Set-Content "updater_config.json" -Encoding UTF8
Write-Host "[OK] Da cau hinh Auto-Update den: $cleanWebUrl" -ForegroundColor Green
Write-Host ""

# ── 3. Khoi tao Git & Bao ve du lieu ca nhan ────────────────
Write-Host "[1/4] Kiem tra Git va file bao mat .gitignore..." -ForegroundColor Yellow
if (-not (Test-Path ".git")) {
    & $gitExe init -b main
}

# Bat ho tro duong dan dai (longpaths) tranh loi Windows Path length
& $gitExe config core.longpaths true

# Thiet lap danh tinh Git neu chua tung set
$uName = (& $gitExe config user.name)
if (-not $uName) {
    & $gitExe config user.name "OpenCut Developer"
}
$uMail = (& $gitExe config user.email)
if (-not $uMail) {
    & $gitExe config user.email "opencut@local.dev"
}

# Dat remote origin
& $gitExe remote remove origin 2>$null
& $gitExe remote add origin $cleanGitUrl

Write-Host "[2/4] Kiem tra an toan API Key & Du lieu ca nhan..." -ForegroundColor Yellow
# Lam sach index va ap dung .gitignore moi nhat
& $gitExe rm -r --cached . 2>$null

Write-Host "[3/4] Chuan bi ma nguon..." -ForegroundColor Yellow
& $gitExe add .

$status = (& $gitExe status --porcelain)
if ($status) {
    Write-Host "[4/4] Commit code..." -ForegroundColor Yellow
    & $gitExe commit -m "feat: OpenCut Studio v2.8.6 with Auto-Update & YouTube Batch"
} else {
    Write-Host "[4/4] Ma nguon da san sang, khong co file thay doi." -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  DANG DAY CODE LEN GITHUB..." -ForegroundColor Cyan
Write-Host "  (Neu trinh duyet hien cua so GitHub, bam Sign In/Authorize)" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

& $gitExe push -u origin main --force

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  [THANH CONG RUC RO!]" -ForegroundColor Green
    Write-Host "  Code da duoc day len GitHub: $cleanWebUrl" -ForegroundColor Green
    Write-Host "  Tu bay gio, moi khi may khac mo 'run.bat':" -ForegroundColor Green
    Write-Host "  Tool se tu dong cap nhat code moi nhat tu day!" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[CANH BAO] Push chua thanh cong (Exit code: $LASTEXITCODE)." -ForegroundColor Red
    Write-Host "Vui long kiem tra lai: Link repo da tao chua? Co quyen ghi khong?" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Bam Enter de hoan tat..."
