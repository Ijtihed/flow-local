; Flow installer.  Build:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" flow.iss   ->  installer\FlowSetup-1.0.0.exe
; Per-user install, no admin prompt. The speech model and GPU libraries download during first-run setup.

#define AppName "Flow"
#define AppVersion "1.5.8"

[Setup]
AppId={{6F1B5A0E-2C4D-4F3B-9E1A-3F10D1C7A7E0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Flow
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=FlowSetup
SetupIconFile=assets\flow.ico
UninstallDisplayIcon={app}\Flow.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSmallImageFile=assets\wizard_small.bmp
WizardImageFile=assets\wizard_large.bmp
Compression=lzma2/ultra64
SolidCompression=yes
AppMutex=FlowDictationMutex
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Open Flow when I sign in"; GroupDescription: "Startup:"

[Files]
Source: "dist\Flow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Flow.exe"; IconFilename: "{app}\Flow.exe"; IconIndex: 0
Name: "{group}\{#AppName} Settings"; Filename: "{app}\Flow.exe"; Parameters: "--window"; IconFilename: "{app}\Flow.exe"; IconIndex: 0
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\Flow.exe"; IconFilename: "{app}\Flow.exe"; IconIndex: 0; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Flow"; ValueData: """{app}\Flow.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\Flow.exe"; Description: "Open Flow"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM Flow.exe"; Flags: runhidden; RunOnceId: "StopFlow"

[Messages]
WelcomeLabel2=This installs Flow voice dictation. Choose on-device speech or an optional transcription API during setup.%n%nHold Ctrl + Win anywhere, talk, and let go. Your words appear where you're typing.
FinishedLabel=Flow is installed. It lives in your system tray; the first time it opens, it walks you through a quick setup.
