' ─────────────────────────────────────────────────────────────────────
'  AudViewer — one-click launcher
'  Double-click this file to start the app.
'  • First run shows a console window while dependencies install.
'  • After that it launches silently (the app window appears on its own).
'  If something goes wrong, run run.bat directly to see the error output.
' ─────────────────────────────────────────────────────────────────────
Option Explicit
Dim sh, fso, scriptDir, style

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = scriptDir

If fso.FolderExists(scriptDir & "\.venv") Then
    style = 0   ' already set up -> launch hidden
Else
    style = 1   ' first run -> show setup progress
End If

' style window, do not wait for the process to finish
sh.Run "cmd /c """ & scriptDir & "\run.bat""", style, False
