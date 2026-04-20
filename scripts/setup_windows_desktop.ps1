param(
    [ValidateSet("auto", "conda", "venv")]
    [string]$Mode = "auto",
    [string]$CondaEnvName = "offline-3d-gis",
    [string]$VenvPath = ".venv",
    [switch]$CreateVenv
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

function Resolve-Mode {
    param(
        [string]$RequestedMode,
        [string]$RepoRoot,
        [string]$VenvPath
    )

    if ($RequestedMode -ne "auto") {
        return $RequestedMode
    }

    if ($env:VIRTUAL_ENV) {
        return "venv"
    }

    if ($env:CONDA_PREFIX) {
        return "conda"
    }

    $venvPython = Join-Path $RepoRoot (Join-Path $VenvPath "Scripts/python.exe")
    if (Test-Path $venvPython) {
        return "venv"
    }

    if (Test-CommandExists "conda") {
        return "conda"
    }

    return "venv"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$selectedMode = Resolve-Mode -RequestedMode $Mode -RepoRoot $repoRoot -VenvPath $VenvPath
Write-Host "Selected setup mode: $selectedMode" -ForegroundColor Yellow

if ($selectedMode -eq "conda") {
    if (-not (Test-CommandExists "conda")) {
        throw "Conda executable not found. Install Miniconda/Anaconda or run with -Mode venv."
    }

    if (Test-Path (Join-Path $repoRoot "environment.yml")) {
        Run-Step -Message "Updating conda environment from environment.yml" -Action {
            conda env update -f environment.yml --prune
        }
    } else {
        Run-Step -Message "Ensuring conda Qt runtime packages" -Action {
            conda install -n $CondaEnvName -y -c conda-forge pyside6 pyside6-webengine
        }
    }

    Run-Step -Message "Ensuring explicit Qt WebEngine packages in conda env" -Action {
        conda install -n $CondaEnvName -y -c conda-forge pyside6 pyside6-webengine
    }

    Run-Step -Message "Upgrading pip in conda env" -Action {
        conda run -n $CondaEnvName python -m pip install --upgrade pip
    }

    Run-Step -Message "Installing project in editable mode (without pip Qt override)" -Action {
        conda run -n $CondaEnvName python -m pip install -e .[geo,dev]
    }

    Run-Step -Message "Verifying Qt WebEngine import in conda env" -Action {
        conda run -n $CondaEnvName python -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
    }

    Write-Host "" 
    Write-Host "Conda desktop setup completed." -ForegroundColor Green
    Write-Host "Next commands:" -ForegroundColor Green
    Write-Host "  conda activate $CondaEnvName"
    Write-Host "  python -m offline_gis_app.cli desktop-client"
    Write-Host "" 
    Write-Host "If DLL errors persist on Windows, install Microsoft Visual C++ 2015-2022 Redistributable (x64)." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-CommandExists "python")) {
    throw "Python executable not found. Install Python 3.11+ or run from an active environment."
}

$venvPython = ""
$venvScriptsPath = Join-Path $repoRoot (Join-Path $VenvPath "Scripts")
$venvPythonCandidate = Join-Path $venvScriptsPath "python.exe"

if ($env:VIRTUAL_ENV) {
    $venvPython = "python"
} elseif (Test-Path $venvPythonCandidate) {
    $venvPython = $venvPythonCandidate
} elseif ($CreateVenv -or $Mode -eq "auto") {
    Run-Step -Message "Creating virtual environment at $VenvPath" -Action {
        python -m venv $VenvPath
    }
    $venvPython = $venvPythonCandidate
} else {
    throw "Virtual environment not found at '$VenvPath'. Re-run with -CreateVenv or activate a venv first."
}

Run-Step -Message "Upgrading pip in venv" -Action {
    & $venvPython -m pip install --upgrade pip
}

Run-Step -Message "Installing desktop + geo + dev dependencies" -Action {
    & $venvPython -m pip install -e .[desktop,geo,dev]
}

Run-Step -Message "Verifying Qt WebEngine import in venv" -Action {
    & $venvPython -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('QtWebEngine OK')"
}

Write-Host ""
Write-Host "Venv desktop setup completed." -ForegroundColor Green
Write-Host "Next command:" -ForegroundColor Green
if ($env:VIRTUAL_ENV) {
    Write-Host "  python -m offline_gis_app.cli desktop-client"
} else {
    Write-Host "  $VenvPath\Scripts\Activate.ps1"
    Write-Host "  python -m offline_gis_app.cli desktop-client"
}
Write-Host ""
Write-Host "If DLL errors persist on Windows, install Microsoft Visual C++ 2015-2022 Redistributable (x64)." -ForegroundColor Yellow
