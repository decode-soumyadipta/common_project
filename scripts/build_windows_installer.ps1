param(
    [string]$Platform = "win-64",
    [string]$ConfigDir = "installer/constructor/win-64",
    [string]$OutputDir = "dist/windows-installer"
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if (-not (Test-Path $ConfigDir)) {
    throw "Constructor config directory not found: $ConfigDir"
}

if (-not (Test-CommandExists "python")) {
    throw "Python executable not found in current shell. Activate your build environment first."
}

if (-not (Test-CommandExists "constructor")) {
    if (-not (Test-CommandExists "conda")) {
        throw "constructor not found and conda is unavailable to install it."
    }
    Run-Step -Message "Installing constructor from conda-forge" -Action {
        conda install -y -c conda-forge constructor
    }
}

Run-Step -Message "Installing Python wheel build tooling" -Action {
    python -m pip install --upgrade pip build
}

$wheelDir = Join-Path $ConfigDir "payload/wheels"
if (-not (Test-Path $wheelDir)) {
    New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
}

Run-Step -Message "Cleaning old wheel payload" -Action {
    Get-ChildItem -Path $wheelDir -Filter "*.whl" -ErrorAction SilentlyContinue | Remove-Item -Force
}

Run-Step -Message "Building project wheel into installer payload" -Action {
    python -m build --wheel --outdir $wheelDir
}

if (-not (Get-ChildItem -Path $wheelDir -Filter "*.whl" -ErrorAction SilentlyContinue)) {
    throw "No wheel generated in $wheelDir"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Run-Step -Message "Building Windows installer with constructor" -Action {
    constructor $ConfigDir --platform $Platform --output-dir $OutputDir
}

Write-Host "" 
Write-Host "Windows installer build complete." -ForegroundColor Green
Write-Host "Output directory: $OutputDir" -ForegroundColor Green
Write-Host "" 
Write-Host "Expected artifact: offline-3d-gis-desktop-0.1.0-Windows-x86_64.exe" -ForegroundColor Yellow
