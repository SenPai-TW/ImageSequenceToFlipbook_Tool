Option Explicit
Dim shell, fso, folder, command, marker, pythonPath
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
marker = folder & "\.flipbook-python-path"
If fso.FileExists(marker) Then
    With fso.OpenTextFile(marker, 1, False, -1)
        pythonPath = Trim(.ReadAll)
        .Close
    End With
End If
If Len(pythonPath) > 0 And fso.FileExists(pythonPath) Then
    pythonPath = fso.BuildPath(fso.GetParentFolderName(pythonPath), "pythonw.exe")
    command = """" & pythonPath & """ """ & folder & "\flipbook_gui.pyw"""
Else
    command = "pyw -3 """ & folder & "\flipbook_gui.pyw"""
End If
shell.Run command, 0, False
