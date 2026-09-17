Set WshShell = CreateObject("WScript.Shell")
Dim fso: Set fso = CreateObject("Scripting.FileSystemObject")
Dim here: here = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & fso.BuildPath(here, "start-audiobook-server.bat") & Chr(34), 0
Set WshShell = Nothing
