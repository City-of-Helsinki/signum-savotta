#define MyAppName "Signum Savotta"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Helsingin Kaupunginkirjasto"
#define MyAppExeName "main.exe"
; Unique application ID — do NOT change after the first public release,
; otherwise Windows will treat upgrades as separate applications.
#define MyAppId "{6D4A2B1C-3E5F-4A8B-9C7D-E0F1A2B3C4D5}"

[Setup]
AppId={{#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\tulostus
DisableDirPage=yes
DefaultGroupName={#MyAppName}
; Overwrite an existing installation without prompting
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=SignumSavottaSetup
SetupIconFile=assets\signumsavotta.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Admin required: USB hardware access and install to Program Files
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Application executable
Source: "dist\main\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Python runtime and all bundled dependencies
Source: "dist\main\_internal\*"; DestDir: "{app}\_internal"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Assets: fonts and icons loaded from the filesystem by the printer module
Source: "assets\*"; DestDir: "{app}\assets"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; Configuration template — has all updated settings and empty [registration].
; The [Code] section below migrates the real registration from an existing
; installation after this file is written.
Source: "config.ini.example"; DestDir: "{app}"; DestName: "config.ini"; \
  Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
; Grant Users Modify access on the install directory so the application can
; write config.ini at runtime (registration, etc.) without admin privileges.
Filename: "icacls"; \
  Parameters: """{app}"" /grant Users:(OI)(CI)M /T /Q"; \
  Flags: runhidden waituntilterminated

[Code]

{ Path of the byte-for-byte copy of the old config made in InitializeWizard,
  before the installer overwrites C:\tulostus. Empty = no prior installation. }
var
  OldConfigTempPath: String;

procedure InitializeWizard;
begin
  { Copy the existing config to a temp file NOW, before the installer
    overwrites C:\tulostus. FileCopy preserves the original encoding. }
  OldConfigTempPath := '';
  if FileExists('C:\tulostus\config.ini') then
  begin
    OldConfigTempPath := ExpandConstant('{tmp}\signum_old_config.ini');
    if not FileCopy('C:\tulostus\config.ini', OldConfigTempPath, False) then
      OldConfigTempPath := '';
  end;
end;

{ After the new config.ini template has been written, run a PowerShell
  script that merges old settings into it and saves the result as
  UTF-8 without BOM — the encoding Python's configparser expects. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  PsLines:    TArrayOfString;
  PsPath:     String;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  if OldConfigTempPath = '' then Exit;

  PsPath := ExpandConstant('{tmp}\signum_merge.ps1');

  SetArrayLength(PsLines, 24);
  PsLines[0]  := '$old_path = ''' + OldConfigTempPath + '''';
  PsLines[1]  := '$new_path = ''' + ExpandConstant('{app}\config.ini') + '''';
  PsLines[2]  := '$enc = [Text.Encoding]::UTF8';
  PsLines[3]  := '$old = [IO.File]::ReadAllLines($old_path, $enc)';
  PsLines[4]  := '$new = [IO.File]::ReadAllLines($new_path, $enc)';
  PsLines[5]  := '$section = ''''';
  PsLines[6]  := '$values  = @{}';
  PsLines[7]  := 'foreach ($line in $old) {';
  PsLines[8]  := '    $t = $line.Trim()';
  PsLines[9]  := '    if ($t -match ' + #39 + '^\[(.+)\]$' + #39 + ') { $section = $Matches[1] }';
  PsLines[10] := '    elseif ($section -and $t -match ' + #39 + '^([^;=#][^=]*)=(.*)$' + #39 + ') {';
  PsLines[11] := '        $values["$section|$($Matches[1].Trim())"] = $Matches[2].Trim() } }';
  PsLines[12] := '$out     = [Collections.Generic.List[string]]::new()';
  PsLines[13] := '$section = ''''';
  PsLines[14] := 'foreach ($line in $new) {';
  PsLines[15] := '    $t = $line.Trim()';
  PsLines[16] := '    if ($t -match ' + #39 + '^\[(.+)\]$' + #39 + ') {';
  PsLines[17] := '        $section = $Matches[1]; $out.Add($line) }';
  PsLines[18] := '    elseif ($section -and $t -match ' + #39 + '^([^;=#][^=]*)=(.*)$' + #39 + ') {';
  PsLines[19] := '        $k = "$section|$($Matches[1].Trim())"';
  PsLines[20] := '        if ($values.ContainsKey($k)) { $out.Add($Matches[1].Trim() + '' = '' + $values[$k]) }';
  PsLines[21] := '        else { $out.Add($line) }';
  PsLines[22] := '    } else { $out.Add($line) } }';
  PsLines[23] := '[IO.File]::WriteAllLines($new_path, $out, [Text.UTF8Encoding]::new($false))';

  SaveStringsToFile(PsPath, PsLines, False);

  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + PsPath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
