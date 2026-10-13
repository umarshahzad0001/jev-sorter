; Per-user installer: no admin prompt, installs under %LOCALAPPDATA%\Programs.
; Built by build.ps1, which passes /DAppVersion=<pyproject version>.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

; A test build passes its own /DAppGuid so installing and uninstalling it never touches a real install.
#ifndef AppGuid
  #define AppGuid "{{6F3B7C1E-8A52-4D0B-9E1F-4C7D2A9B5E31}"
#endif

; The "Start with Windows" switch in the app writes this Run value. The installer never creates it,
; but it removes it on uninstall so no dead startup entry is left behind. Tests pass their own name.
#ifndef RunName
  #define RunName "JevSorter"
#endif

[Setup]
AppId={#AppGuid}
AppName=Jev Sorter
AppVersion={#AppVersion}
AppPublisher=Jev Sorter
DefaultDirName={autopf}\Jev Sorter
DefaultGroupName=Jev Sorter
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=JevSorter-Setup-{#AppVersion}
SetupIconFile=jevsorter.ico
UninstallDisplayIcon={app}\JevSorter.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "folderverb"; Description: "Add ""Sort with Jev Sorter"" to the folder right-click menu"; GroupDescription: "Explorer:"

[Files]
Source: "dist\JevSorter\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{group}\Jev Sorter"; Filename: "{app}\JevSorter.exe"
Name: "{autodesktop}\Jev Sorter"; Filename: "{app}\JevSorter.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JevSorter"; ValueType: string; ValueData: "Sort with Jev Sorter"; Flags: uninsdeletekey; Tasks: folderverb
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JevSorter"; ValueName: "Icon"; ValueType: string; ValueData: "{app}\JevSorter.exe"; Tasks: folderverb
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JevSorter\command"; ValueType: string; ValueData: """{app}\JevSorter.exe"" ""%1"""; Tasks: folderverb
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "{#RunName}"; ValueType: none; Flags: uninsdeletevalue

[Run]
Filename: "{app}\JevSorter.exe"; Description: "Launch Jev Sorter"; Flags: nowait postinstall skipifsilent
