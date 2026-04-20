#define AppName "Offline GIS Desktop Suite"
#define AppVersion "0.1.0"
#define Publisher "Offline GIS"
#define ServerBuild "..\..\dist\OfflineGIS-Server"
#define ClientBuild "..\..\dist\OfflineGIS-Client"

[Setup]
AppId={{D2F2F8E8-86A4-4B04-8D9A-3C2F218EFB5A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\OfflineGIS
DefaultGroupName=OfflineGIS
UninstallDisplayIcon={app}\Server\OfflineGIS-Server.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
OutputDir=..\..\dist\installer
OutputBaseFilename=OfflineGIS-Dual-Setup

[Tasks]
Name: "desktopicons"; Description: "Create desktop shortcuts"; GroupDescription: "Additional icons:"; Flags: unchecked

[Dirs]
Name: "{localappdata}\OfflineGIS"
Name: "{localappdata}\OfflineGIS\data"
Name: "{localappdata}\OfflineGIS\logs"

[Files]
Source: "{#ServerBuild}\*"; DestDir: "{app}\Server"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#ClientBuild}\*"; DestDir: "{app}\Client"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\OfflineGIS Ingestion Server"; Filename: "{app}\Server\OfflineGIS-Server.exe"
Name: "{group}\OfflineGIS Search Client"; Filename: "{app}\Client\OfflineGIS-Client.exe"
Name: "{commondesktop}\OfflineGIS Ingestion Server"; Filename: "{app}\Server\OfflineGIS-Server.exe"; Tasks: desktopicons
Name: "{commondesktop}\OfflineGIS Search Client"; Filename: "{app}\Client\OfflineGIS-Client.exe"; Tasks: desktopicons

[Run]
Filename: "{app}\Server\OfflineGIS-Server.exe"; Description: "Launch Ingestion Server app"; Flags: nowait postinstall skipifsilent unchecked
Filename: "{app}\Client\OfflineGIS-Client.exe"; Description: "Launch Search Client app"; Flags: nowait postinstall skipifsilent unchecked
