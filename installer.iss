; GTclaw Personal AI Assistant — Inno Setup Installer Script
; Build with:  .\build.ps1 -Installer
; Requires:    Inno Setup 6 from https://jrsoftware.org/isinfo.php

#define AppName    "GTclaw AI Assistant"
#define AppVersion "1.1.0"
#define AppPublisher "GTclaw"
#define AppExeName "GTclawDashboard.exe"
#define ServiceExe "GTclawService.exe"

[Setup]
AppId={{B9C4D7E2-F3A1-4B8C-9D2E-AB3456789012}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\GTclawAI
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=GTclawAI_Setup_{#AppVersion}
SetupIconFile=logo.ico
WizardSmallImageFile=logo_wizard.bmp
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#AppExeName}
ChangesEnvironment=no
RestartIfNeededByRun=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create &desktop shortcut";            GroupDescription: "Shortcuts:"
Name: "autostart";    Description: "Auto-start bot service with &Windows"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "startservice"; Description: "&Start the bot service now";           GroupDescription: "Startup:"

[Files]
; Dashboard EXE — self-contained, no Python required on target machine
Source: "dist\GTclawDashboard.exe"; DestDir: "{app}"; Flags: ignoreversion

; Service EXE
Source: "dist\GTclawService.exe";   DestDir: "{app}"; Flags: ignoreversion

; App icon (for Start Menu shortcuts etc.)
Source: "logo.ico";         DestDir: "{app}"; Flags: ignoreversion
Source: "logo_wizard.bmp";  DestDir: "{app}"; Flags: ignoreversion

; Default config templates (onlyifdoesntexist preserves settings on upgrades)
Source: "config\config.template.json"; DestDir: "{app}\config"; DestName: "config.json"; Flags: onlyifdoesntexist
Source: "config\identity.json";  DestDir: "{app}\config"; Flags: onlyifdoesntexist
Source: "config\settings.json";  DestDir: "{app}\config"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName} Dashboard"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\logo.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; IconFilename: "{app}\logo.ico"

[Registry]
; Add service to Windows startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "GTclawService"; \
  ValueData: """{app}\{#ServiceExe}"" debug"; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Stop any running instance first (upgrade scenario)
Filename: "taskkill"; Parameters: "/IM GTclawService.exe /F"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Stopping existing service..."

; Optionally start service immediately
Filename: "{app}\{#ServiceExe}"; Parameters: "debug"; \
  Flags: nowait runhidden; Tasks: startservice; StatusMsg: "Starting AI bot service..."

; Open dashboard to configure API keys
Filename: "{app}\{#AppExeName}"; \
  Description: "Open Dashboard now (configure your API keys)"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM GTclawService.exe /F"; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "taskkill"; Parameters: "/IM GTclawDashboard.exe /F"; \
  Flags: runhidden waituntilterminated; RunOnceId: "StopDash"

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption :=
    'Welcome to GTclaw AI Assistant!' + #13#10 + #13#10 +
    'This installs a 24/7 personal AI assistant powered by Claude AI.' + #13#10 +
    'You can chat via Telegram AND via the built-in dashboard.' + #13#10 + #13#10 +
    'After installation the Dashboard opens automatically.' + #13#10 +
    'Go to Settings to enter your:' + #13#10 +
    '  • Anthropic API key  (console.anthropic.com)' + #13#10 +
    '  • Telegram bot token  (create via @BotFather on Telegram)' + #13#10 +
    '  • Your Telegram user ID  (get from @userinfobot)' + #13#10 +
    '  • Tavily Search key  (optional — app.tavily.com)' + #13#10 + #13#10 +
    'The Telegram wizard button in Settings will walk you through setup.';
end;
