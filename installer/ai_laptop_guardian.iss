; AI Laptop Guardian — Inno Setup Script
;
; Installs the packaged PyInstaller application into a
; per-user location.  User data (preferences, tokens,
; logs) lives outside the installation directory and is
; NOT removed on uninstall.
;
; Build from project root:
;   "C:\Users\ajeet\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\ai_laptop_guardian.iss

#define MyAppName "AI Laptop Guardian"
#define MyAppVersion "0.14.0.0"
#define MyAppDisplayVersion "0.14.0"
#define MyAppPublisher "AI Laptop Guardian"
#define MyAppExeName "AI-Laptop-Guardian.exe"

; Source: the PyInstaller folder-based build output.
#define DistDir "..\dist\AI-Laptop-Guardian"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\AI-Laptop-Guardian
DefaultGroupName={#MyAppName}
OutputDir=..\installer_output
OutputBaseFilename=AI-Laptop-Guardian-{#MyAppDisplayVersion}-Setup
Compression=lzma2
SolidCompression=yes
; Per-user install — no administrator privileges required.
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=no
; Do NOT auto-remove the user-data directory on uninstall.
; Show license if present.
; LicenseFile=..\LICENSE
; Use the application icon for the installer/uninstaller.
; (SetupIconFile removed — .exe too large for direct use as icon source)
UninstallDisplayIcon={app}\AI-Laptop-Guardian.exe
; Version info for the installer executable.
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (C) 2026

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Install the entire PyInstaller folder-based distribution.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut — always created.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop shortcut — optional (user selects during install).
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Launch the application after installation finishes.
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove only the installed application directory.
; User data in %LOCALAPPDATA%\AI-Laptop-Guardian is NOT touched.
Type: filesandordirs; Name: "{app}"

[Code]
// Ensure the install directory is empty before installing.
// This prevents old files from lingering after an upgrade.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Force-remove the app directory on upgrade so stale
    // DLLs from the previous build do not persist.
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
