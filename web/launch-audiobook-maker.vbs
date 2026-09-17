' Audiobook Maker — one-click launcher (same pattern as SPACESTATION Control Center).
' 1) If the server isn't running, start it hidden via run-background.vbs.
' 2) Wait until it responds.
' 3) Open the app in a Chrome app window (falls back to default browser).
' The desktop shortcut points here. Run with /dryrun:1 to test without opening anything.
Option Explicit

' Tailscale IP on purpose — the server doesn't bind localhost (see AGENTS.md).
Const BASE = "http://100.69.165.27:8765"
Const PROJ = "A:\Cowork\audiobooks"

Dim PING: PING = BASE & "/api/jobs"
Dim sh:  Set sh = CreateObject("WScript.Shell")
Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
Dim dry: dry = WScript.Arguments.Named.Exists("dryrun")

Function ServerUp()
  On Error Resume Next
  Dim h: Set h = CreateObject("WinHttp.WinHttpRequest.5.1")
  h.SetTimeouts 500, 500, 800, 800
  h.Open "GET", PING, False
  h.Send
  ServerUp = (Err.Number = 0 And h.Status = 200)
  On Error GoTo 0
End Function

If Not ServerUp() Then
  If dry Then
    WScript.Echo "DRY: server down, would start it hidden via web\run-background.vbs"
  Else
    sh.Run "wscript.exe """ & PROJ & "\web\run-background.vbs""", 0, False
    Dim i
    For i = 1 To 120 ' up to ~60s — torch/Kokoro imports make cold boots slow
      WScript.Sleep 500
      If ServerUp() Then Exit For
    Next
  End If
End If

' Prefer Chrome's app mode — a clean standalone window without browser chrome.
Dim chrome, candidates, c
candidates = Array( _
  sh.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe", _
  sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Google\Chrome\Application\chrome.exe", _
  sh.ExpandEnvironmentStrings("%LocalAppData%") & "\Google\Chrome\Application\chrome.exe")
chrome = ""
For Each c In candidates
  If fso.FileExists(c) Then chrome = c: Exit For
Next

' A plain "chrome --app=URL" hands the URL to the already-running Chrome and
' ignores window flags, so --start-maximized would do nothing. Giving the app
' its OWN user-data-dir makes it a separate Chrome instance where the flag
' applies (and Chrome then remembers the maximised state); the clean profile
' also sidesteps the stale-HTML cache that kept the old layout showing.
Const APP_PROFILE = "A:\Cowork\.audire-chrome-profile"
Dim FLAGS: FLAGS = " --start-maximized --no-first-run --no-default-browser-check --user-data-dir=""" & APP_PROFILE & """"

If dry Then
  If chrome <> "" Then
    WScript.Echo "DRY: would open MAXIMISED chrome app window -> " & BASE
  Else
    WScript.Echo "DRY: chrome not found, would open default browser -> " & BASE
  End If
ElseIf chrome <> "" Then
  sh.Run """" & chrome & """ --app=" & BASE & FLAGS, 1, False
Else
  sh.Run BASE, 1, False
End If
