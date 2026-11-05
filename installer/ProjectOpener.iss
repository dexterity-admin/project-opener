; Inno Setup script for Project Opener (per-user install, no admin rights).
;
;   iscc installer\ProjectOpener.iss /DAppVersion=3.0.0
;
; Expects the PyInstaller output in dist\ProjectOpener\ (see tools\build.ps1).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
; Windows file version info must be numeric (a.b.c.d); a dev or pre-release
; version such as 4.0.0.dev0 passes its numeric part as AppVersionNum.
#ifndef AppVersionNum
  #define AppVersionNum AppVersion
#endif
#define AppName "Project Opener"
#define AppPublisher "Dexterity Design Services Pvt. Ltd."
#define AppExeName "ProjectOpener.exe"
#define AppId "{{7C2F0E39-5B4A-4F1E-9A3C-2D1E7A6B5F10}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/dexterity-admin/project-opener
AppSupportURL=https://github.com/dexterity-admin/project-opener/issues
DefaultDirName={localappdata}\Programs\Project Opener
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ProjectOpener-Setup-{#AppVersion}
SetupIconFile=..\project_opener\resources\icon\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
MinVersion=10.0
VersionInfoVersion={#AppVersionNum}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} installer
ShowLanguageDialog=no
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Project Opener when I sign in to Windows (minimised to the tray)"; GroupDescription: "Start-up:"; Flags: unchecked
Name: "explorer"; Description: "Add ""Add to running activity"" and ""Send to > Project Opener"" to Explorer"; GroupDescription: "Explorer entries:"

[Files]
Source: "..\dist\ProjectOpener\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
; Send to > Project Opener (Windows appends the selected paths after --sendto). {usersendto} is per user.
Name: "{usersendto}\Project Opener"; Filename: "{app}\{#AppExeName}"; Parameters: "--sendto"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Comment: "Add the selected files to the running activity in Project Opener"; Tasks: explorer

[Registry]
; Start with Windows (per-user Run key). The app can also toggle this itself.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DexterityProjectOpener"; ValueData: """{app}\{#AppExeName}"" --minimised"; Flags: uninsdeletevalue; Tasks: startup
; projectopener:// deep links (projectopener://open/<project id or name>)
Root: HKCU; Subkey: "Software\Classes\projectopener"; ValueType: string; ValueName: ""; ValueData: "URL:Project Opener"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\projectopener"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\projectopener\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"",0"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\projectopener\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey

; v4: "Add to running activity" on files and folders (desktop/shellext.py writes the same keys from
; Settings > Snapshot).  Per user, no admin; removed on uninstall.
Root: HKCU; Subkey: "Software\Classes\*\shell\ProjectOpener.AddToActivity"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Add to running activity"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\*\shell\ProjectOpener.AddToActivity"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExeName}"",0"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\*\shell\ProjectOpener.AddToActivity\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" --add ""%1"""; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\ProjectOpener.AddToActivity"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Add to running activity"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\ProjectOpener.AddToActivity"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\{#AppExeName}"",0"; Flags: uninsdeletekey; Tasks: explorer
Root: HKCU; Subkey: "Software\Classes\Directory\shell\ProjectOpener.AddToActivity\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" --add ""%1"""; Flags: uninsdeletekey; Tasks: explorer

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Leftovers from Project Opener 1.x / 2.x builds that installed into the same folder.
Type: files; Name: "{app}\Project Opener_SR*.exe"
Type: files; Name: "{app}\app.exe"
Type: files; Name: "{app}\1.ico"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; The app may have written these itself (Settings > Snapshot) even when the installer task was off.
Type: files; Name: "{usersendto}\Project Opener.lnk"

[Code]
// Project Opener 1.x/2.x used a different AppId but the same folder. Uninstall it
// silently first so Programs & Features shows a single entry afterwards.
const
  OldAppKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{012BA30E-0D7B-4B6A-8BD2-CA7420D4B880}_is1';

function UninstallOldVersion(): Boolean;
var
  Uninstaller: String;
  ResultCode: Integer;
begin
  Result := True;
  if RegQueryStringValue(HKCU, OldAppKey, 'UninstallString', Uninstaller) then
  begin
    Uninstaller := RemoveQuotes(Uninstaller);
    if FileExists(Uninstaller) then
    begin
      Log('Removing previous Project Opener install: ' + Uninstaller);
      Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Log('Previous uninstaller exit code: ' + IntToStr(ResultCode));
    end
    else
      RegDeleteKeyIncludingSubkeys(HKCU, OldAppKey);
  end;
end;

// The Explorer verb may also have been written by the app (Settings > Snapshot) when the installer
// task was off, so the uninstaller removes it whichever way it got there.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\*\shell\ProjectOpener.AddToActivity');
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Classes\Directory\shell\ProjectOpener.AddToActivity');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    UninstallOldVersion();
  if CurStep = ssPostInstall then
    DeleteFile(ExpandConstant('{userdesktop}\Project Opener_SR2.lnk'));
end;
