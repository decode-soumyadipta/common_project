param(
    [string]$CondaEnvName = "offline-3d-gis",
    [switch]$SkipInstaller,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

function Run-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )
    Write-Host "==> $Message" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Action
    if ($global:LASTEXITCODE -ne 0) {
        throw "Step failed with exit code $($global:LASTEXITCODE): $Message"
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
Set-Location $repoRoot

if ($Clean) {
    Run-Step -Message "Cleaning prior build artifacts" -Action {
        Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
    }
}

Run-Step -Message "Installing/Updating PyInstaller in conda env" -Action {
    conda run -n $CondaEnvName python -m pip install --upgrade "pyinstaller>=6.10,<7.0"
}

Run-Step -Message "Building OfflineGIS-Server bundle" -Action {
    conda run -n $CondaEnvName pyinstaller --noconfirm --clean "packaging/windows/OfflineGIS-Server.spec"
}

Run-Step -Message "Building OfflineGIS-Client bundle" -Action {
    conda run -n $CondaEnvName pyinstaller --noconfirm --clean "packaging/windows/OfflineGIS-Client.spec"
}

$serverExe = Join-Path $repoRoot "dist/OfflineGIS-Server/OfflineGIS-Server.exe"
$clientExe = Join-Path $repoRoot "dist/OfflineGIS-Client/OfflineGIS-Client.exe"

if (-not (Test-Path $serverExe)) {
    throw "Server bundle missing executable: $serverExe"
}
if (-not (Test-Path $clientExe)) {
    throw "Client bundle missing executable: $clientExe"
}

Write-Host "Build outputs:" -ForegroundColor Green
Write-Host "  $serverExe"
Write-Host "  $clientExe"

if ($SkipInstaller) {
    Write-Host "Installer build skipped by -SkipInstaller." -ForegroundColor Yellow
    exit 0
}

$isccPaths = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$iscc = $null
foreach ($candidate in $isccPaths) {
    if (Test-Path $candidate) {
        $iscc = $candidate
        break
    }
}

if (-not $iscc) {
    Write-Host "Inno Setup compiler (ISCC.exe) not found. Bundles are ready in dist/." -ForegroundColor Yellow
    Write-Host "Install Inno Setup 6 and rerun this script to produce installer wizard executable." -ForegroundColor Yellow
    exit 0
}

Run-Step -Message "Compiling OfflineGIS dual installer wizard" -Action {
    & $iscc "packaging/windows/OfflineGIS_Dual_Installer.iss"
}

$installer = Join-Path $repoRoot "dist/installer/OfflineGIS-Dual-Setup.exe"
if (Test-Path $installer) {
    Write-Host "Installer built:" -ForegroundColor Green
    Write-Host "  $installer"
}
