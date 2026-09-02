#define AppName "ACE Studio"
#define AppVersion "0.1.5"
[Setup]
AppId={{2FA9BF09-D8B3-44D2-A444-0ECFE5CF98F9}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\ACE Studio
OutputDir=..\..\build
OutputBaseFilename=ACE-Studio-Windows-Setup
SetupIconFile=ACE-Studio.ico
UninstallDisplayIcon={app}\ACE Studio.exe
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
[Files]
Source: "..\..\build\windows\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{autoprograms}\ACE Studio"; Filename: "{app}\ACE Studio.exe"
[Run]
Filename: "{app}\ACE Studio.exe"; Description: "Launch ACE Studio"; Flags: nowait postinstall skipifsilent
