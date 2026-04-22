' Start  Bot as tray icon – completely invisible, no console window.
' Double-click this file or put it in your Startup folder.
Set WShell = CreateObject("WScript.Shell")
WShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WShell.Run "pythonw tray_runner.py", 0, False
