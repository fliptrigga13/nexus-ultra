; ─────────────────────────────────────────────────────────────────────────────
; NEXUS ULTRA — Inno Setup Installer Script
; Compile with Inno Setup 6: https://jrsoftware.org/isinfo.php
; Output: installer\Output\NexusUltra_Setup.exe
; ─────────────────────────────────────────────────────────────────────────────

#define AppName      "NEXUS ULTRA"
#define AppVersion   "1.0.0"
#define AppPublisher "NEXUS Prime Project"
#define AppURL       "https://github.com/YOUR_USERNAME/nexus-ultra"
#define AppExeName   "START_ULTIMATE_GOD_MODE.bat"
#define SrcDir       ".."    ; relative to this .iss file (nexus-ultra root)

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\NexusUltra
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=NexusUltra_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Require admin so we can write to Program Files
PrivilegesRequired=admin
; Architecture
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Custom pages ─────────────────────────────────────────────────────────────
[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nNEXUS ULTRA runs a 6-agent AI swarm entirely on your local GPU.%n%nPrerequisites (install before running):%n  • Ollama (ollama.com)%n  • Python 3.11+%n  • Julia 1.10+ (optional — for PSO GPU optimiser)%n%nClick Next to continue.

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checked
Name: "startmenu";  Description: "Create a &Start Menu shortcut";  GroupDescription: "Additional icons:"; Flags: checked
Name: "feedingestor"; Description: "Add Feed Ingestor to startup (auto-pulls HackerNews + ArXiv)"; GroupDescription: "Optional:"; Flags: unchecked

[Files]
; ── Core Python scripts ───────────────────────────────────────────────────────
Source: "{#SrcDir}\nexus_swarm_loop.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_eh.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_cognitive_engine.py";DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_evolution.py";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_antennae.py";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_rogue_agents.py";    DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_mycelium.py";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_hub_server.py";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_memory_core.py";     DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_feed_ingestor.py";   DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\SELF_EVOLUTION_LOOP.py";   DestDir: "{app}"; Flags: ignoreversion

; ── Launcher ──────────────────────────────────────────────────────────────────
Source: "{#SrcDir}\START_ULTIMATE_GOD_MODE.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\CHECK_HEALTH.ps1";            DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\WEEKLY_MAINTENANCE.ps1";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\SWARM_CHAOS_TEST.py";         DestDir: "{app}"; Flags: ignoreversion

; ── HTML dashboards ───────────────────────────────────────────────────────────
Source: "{#SrcDir}\nexus_ultimate_hub.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_hub.html";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcDir}\nexus_personal.html";     DestDir: "{app}"; Flags: ignoreversion

; ── Julia PSO brain ───────────────────────────────────────────────────────────
Source: "{#SrcDir}\local-scripts\pso_swarm.jl"; DestDir: "{app}\local-scripts"; Flags: ignoreversion

; ── README ────────────────────────────────────────────────────────────────────
Source: "{#SrcDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
; Desktop shortcut
Name: "{autodesktop}\NEXUS GOD MODE"; Filename: "{app}\{#AppExeName}"; \
  WorkingDir: "{app}"; Comment: "Launch NEXUS ULTRA — all 10 engines"; \
  Tasks: desktopicon

; Start Menu shortcuts
Name: "{group}\NEXUS GOD MODE";        Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: startmenu
Name: "{group}\Health Check";          Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\CHECK_HEALTH.ps1"""; WorkingDir: "{app}"; Tasks: startmenu
Name: "{group}\Uninstall {#AppName}";  Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
; Install Python dependencies
Filename: "pip"; Parameters: "install httpx"; \
  WorkingDir: "{app}"; StatusMsg: "Installing Python dependencies (httpx)..."; \
  Flags: runhidden waituntilterminated

; Optionally register Feed Ingestor in Windows Task Scheduler (hourly)
Filename: "schtasks"; \
  Parameters: "/Create /F /SC HOURLY /TN ""NexusUltraFeedIngestor"" /TR ""python \""{app}\nexus_feed_ingestor.py\"""" /RL HIGHEST"; \
  WorkingDir: "{app}"; StatusMsg: "Registering Feed Ingestor (hourly)..."; \
  Flags: runhidden waituntilterminated; Tasks: feedingestor

[UninstallRun]
; Remove Task Scheduler entry on uninstall
Filename: "schtasks"; Parameters: "/Delete /F /TN ""NexusUltraFeedIngestor"""; \
  Flags: runhidden waituntilterminated; Tasks: feedingestor

[Code]
// ── Prerequisite check: warn if Ollama or Python not found ───────────────────
function InitializeSetup(): Boolean;
var
  OllamaPath, PythonPath: String;
  Msg: String;
begin
  Result := True;
  Msg := '';

  if not FileExists(ExpandConstant('{pf}\Ollama\ollama.exe')) and
     not FileExists('C:\Users\' + GetUserNameString + '\AppData\Local\Programs\Ollama\ollama.exe') then
    Msg := Msg + '  ⚠  Ollama not found. Install from https://ollama.com first.' + #13#10;

  if not FileExists('C:\Python311\python.exe') and
     not FileExists('C:\Python312\python.exe') and
     not FileExists('C:\Python313\python.exe') and
     not FileExists('C:\Python314\python.exe') then
    Msg := Msg + '  ⚠  Python 3.11+ not found. Install from https://python.org first.' + #13#10;

  if Msg <> '' then begin
    if MsgBox('Missing prerequisites detected:' + #13#10 + Msg + #13#10 +
              'Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;

function GetUserNameString: String;
var
  Len: DWORD;
begin
  Len := 256;
  SetLength(Result, Len);
  GetUserNameExW(0, Result, Len);
  SetLength(Result, Len);
end;
