; Inno Setup script for Quant Research Lab (design note 6.2).
;
; Compile from the repository root after the PyInstaller build and the notices:
;   ISCC.exe /DAppVersion=0.4.0 packaging\installer.iss
; It packs dist\Quant Research Lab\ into dist\QuantResearchLab-<version>-win64-setup.exe.
;
; Per-user installation, no administrator rights. Uninstalling removes only the program folder:
; workspaces (the user's data) and the settings file are never touched.

#ifndef AppVersion
  #error Pass the version: ISCC.exe /DAppVersion=x.y.z packaging\installer.iss
#endif
#define AppName "Quant Research Lab"
#define AppExe "QuantResearchLab.exe"
#define SourceDir "..\dist\Quant Research Lab"

[Setup]
; Fixed: a new version upgrades the installed one in place. Never change it.
AppId={{5D099139-A0D3-458A-931D-7377A67D1909}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Alessandro Zanichelli
; With lowest privileges {autopf} is %LOCALAPPDATA%\Programs.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=QuantResearchLab-{#AppVersion}-win64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "disclaimer_en.txt"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"; InfoBeforeFile: "disclaimer_it.txt"

[Messages]
english.FinishedLabel=Setup has finished installing [name].%n%nYour settings are kept in %APPDATA%\qrlab\qrlab-app.ini and your workspaces stay where you created them: uninstalling removes neither.
italian.FinishedLabel=L'installazione di [name] è terminata.%n%nLe impostazioni restano in %APPDATA%\qrlab\qrlab-app.ini e i workspace dove li hai creati: la disinstallazione non li rimuove.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
