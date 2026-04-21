param(
    [string]$PythonExe = "python",
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

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$specDir = Join-Path $PSScriptRoot "pyinstaller"
$distRoot = Join-Path $repoRoot "dist\windows-exe"
$buildRoot = Join-Path $repoRoot "build\pyinstaller"

Set-Location $repoRoot

if ($Clean) {
    if (Test-Path $distRoot) {
        Run-Step -Message "Removing previous dist output" -Action {
            Remove-Item -Recurse -Force $distRoot
        }
    }
    if (Test-Path $buildRoot) {
        Run-Step -Message "Removing previous build cache" -Action {
            Remove-Item -Recurse -Force $buildRoot
        }
    }
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null

Run-Step -Message "Installing/Updating PyInstaller in active environment" -Action {
    & $PythonExe -m pip install --upgrade pyinstaller
}

Run-Step -Message "Building server.exe (desktop server mode)" -Action {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $distRoot "server") `
        --workpath (Join-Path $buildRoot "server") `
        (Join-Path $specDir "server.spec")
}

Run-Step -Message "Building client.exe (desktop client mode)" -Action {
    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath (Join-Path $distRoot "client") `
        --workpath (Join-Path $buildRoot "client") `
        (Join-Path $specDir "client.spec")
}

Write-Host "" 
Write-Host "Build completed." -ForegroundColor Green
Write-Host "Server app:" -ForegroundColor Green
Write-Host "  $distRoot\server\server.exe"
Write-Host "Client app:" -ForegroundColor Green
Write-Host "  $distRoot\client\client.exe"
Write-Host "" 
Write-Host "Distribute server.exe and client.exe together with offline data packs if your workflow requires them." -ForegroundColor Yellow
