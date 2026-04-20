param(
    [Parameter(Mandatory = $true)]
    [string]$InstallPrefix
)

$ErrorActionPreference = "Stop"

function New-Shortcut {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LinkPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [string]$Arguments = "",
        [string]$WorkingDirectory = "",
        [string]$Description = ""
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($LinkPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.Arguments = $Arguments
    if ($WorkingDirectory) {
        $shortcut.WorkingDirectory = $WorkingDirectory
    }
    if ($Description) {
        $shortcut.Description = $Description
    }
    $shortcut.Save()
}

$prefix = (Resolve-Path $InstallPrefix).Path
$clientLauncher = Join-Path $prefix "offline-gis-desktop-client.bat"
$serverLauncher = Join-Path $prefix "offline-gis-desktop-server.bat"
$apiLauncher = Join-Path $prefix "offline-gis-api.bat"

if (-not (Test-Path $clientLauncher)) {
    throw "Client launcher not found: $clientLauncher"
}

$programsRoot = [Environment]::GetFolderPath("Programs")
$desktopRoot = [Environment]::GetFolderPath("Desktop")
$menuFolder = Join-Path $programsRoot "Offline 3D GIS"
if (-not (Test-Path $menuFolder)) {
    New-Item -ItemType Directory -Path $menuFolder -Force | Out-Null
}

$clientMenuLink = Join-Path $menuFolder "Offline 3D GIS Desktop Client.lnk"
$serverMenuLink = Join-Path $menuFolder "Offline 3D GIS Desktop Server.lnk"
$apiMenuLink = Join-Path $menuFolder "Offline 3D GIS API.lnk"
$desktopLink = Join-Path $desktopRoot "Offline 3D GIS Desktop Client.lnk"

New-Shortcut -LinkPath $clientMenuLink -TargetPath $clientLauncher -WorkingDirectory $prefix -Description "Launch Offline 3D GIS desktop client"
if (Test-Path $serverLauncher) {
    New-Shortcut -LinkPath $serverMenuLink -TargetPath $serverLauncher -WorkingDirectory $prefix -Description "Launch Offline 3D GIS desktop server"
}
if (Test-Path $apiLauncher) {
    New-Shortcut -LinkPath $apiMenuLink -TargetPath $apiLauncher -WorkingDirectory $prefix -Description "Launch Offline 3D GIS API"
}
New-Shortcut -LinkPath $desktopLink -TargetPath $clientLauncher -WorkingDirectory $prefix -Description "Launch Offline 3D GIS desktop client"

Write-Host "Created Start Menu shortcuts in: $menuFolder"
Write-Host "Created desktop shortcut: $desktopLink"
