' Start  Bot as tray icon – completely invisible, no console window.
' Double-click this file or put it in your Startup folder.
Set WShell = CreateObject("WScript.Shell")
WShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
Set FSO = CreateObject("Scripting.FileSystemObject")
ProjectPython = WShell.CurrentDirectory & "\.venv\Scripts\pythonw.exe"
Helper = Chr(34) & WShell.CurrentDirectory & "\tools\python_environment.py" & Chr(34)
Arguments = ""
For Each Argument In WScript.Arguments
    If Not IsNumeric(Argument) Then
        MsgBox "The optional argument must be a WebUI port number.", 16, "Bot startup"
        WScript.Quit 1
    End If
    Arguments = Arguments & " " & Argument
Next
If FSO.FolderExists(WShell.CurrentDirectory & "\.venv") Then
    If Not FSO.FileExists(ProjectPython) Then
        MsgBox "Project .venv is incomplete. Repair it before starting the bot.", 16, "Bot startup"
        WScript.Quit 1
    End If
    Command = Chr(34) & ProjectPython & Chr(34) & " " & Helper & " --launch" & Arguments
Else
    Command = "pythonw " & Helper & " --launch" & Arguments
End If
On Error Resume Next
WShell.Run Command, 0, False
If Err.Number <> 0 Then
    MsgBox "Python could not be started. Run INSTALL-ENVIRONMENT.bat first.", 16, "Bot startup"
    WScript.Quit 1
End If
