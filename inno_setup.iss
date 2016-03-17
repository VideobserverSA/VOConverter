; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define MyAppName "Vo Converter"
#define MyAppVersion "1.0.80"
#define MyAppPublisher "Videobserver SA"
#define MyAppURL "http://www.videobserver.com"
#define MyAppExeName "voconverter.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{03D2C6E6-88C8-4A86-8A39-8BC238D0807F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright=Copyright (C) 2015 Videobserver SA
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName={#MyAppName}
LicenseFile=C:\Users\Rui\PycharmProjects\VOConverter\gpl.txt
OutputDir=C:\Users\Rui\PycharmProjects\VOConverter\pack_out
OutputBaseFilename=vo_converter_setup_{#MyAppVersion}
SetupIconFile=C:\Users\Rui\PycharmProjects\VOConverter\icon.ico
Compression=lzma
SolidCompression=yes
WizardImageFile=wizard.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "C:\Users\Rui\PycharmProjects\VOConverter\dist\voconverter.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\Rui\PycharmProjects\VOConverter\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; AfterInstall: UpdateLanguage
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

;[Ini]
;Filename: "{app}\default_lang.ini"; Section: "Install Settings"; Flags: uninsdeletesection
;Filename: "{app}\default_lang.ini"; Section: "Install Settings"; Key: "Teste"; String: "Yes it is a test"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure UpdateLanguage();
var
  CurrentLang:String;
  Locale:String;
  IniFile:String;
begin
   CurrentLang := ActiveLanguage();
   //have a sensible default
   Locale := 'en_US';
   if CurrentLang = 'english' then
   begin
      Locale := 'en_US';
   end;
   if CurrentLang = 'portuguese' then
   begin
      Locale := 'pt_PT';
   end;
   //write the INI directive
   IniFile := ExpandConstant('{app}') + '\' + 'lang.ini';
   SetIniString('Language', 'Default Locale', Locale, IniFile);
   //MsgBox('fdx ' + IniFile, mbInformation, MB_OK)
   Log('Set locale to: ' + Locale)
end;

