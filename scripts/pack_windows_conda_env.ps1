param(
    [string]$EnvName = "offline-3d-gis",
    [string]$OutputPath = "dist/offline-3d-gis-win64.zip"
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
    & $Action
}

if (-not (Test-CommandExists "conda")) {
    throw "Conda executable not found. Install Miniconda/Anaconda first."
}

if (-not (Test-CommandExists "conda-pack")) {
    Run-Step -Message "Installing conda-pack" -Action {
        conda install -y -c conda-forge conda-pack
    }
}

$outputDir = Split-Path -Parent $OutputPath
if ($outputDir -and -not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

Run-Step -Message "Packing environment '$EnvName' into $OutputPath" -Action {
    conda-pack -n $EnvName -o $OutputPath
}

Write-Host ""
Write-Host "Conda pack completed: $OutputPath" -ForegroundColor Green
Write-Host ""
Write-Host "Transfer and unpack on target Windows machine:" -ForegroundColor Green
Write-Host "  1) unzip to C:\\offline-3d-gis"
Write-Host "  2) C:\\offline-3d-gis\\Scripts\\activate"
Write-Host "  3) conda-unpack"
Write-Host "  4) python -m offline_gis_app.cli desktop-client"
