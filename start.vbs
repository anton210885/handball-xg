' Handball xG starten – ohne Konsolenfenster.
' Startet den Server im Hintergrund (falls er nicht schon laeuft) und oeffnet den Browser.
Option Explicit
Dim shell, fso, root, pythonw, http, i, ready
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\backend\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python-Umgebung fehlt: " & pythonw & vbCrLf & "Bitte zuerst die Einrichtung aus der README ausfuehren.", vbExclamation, "Handball xG"
    WScript.Quit 1
End If
If Not fso.FileExists(root & "\frontend\dist\index.html") Then
    MsgBox "Die Oberflaeche ist noch nicht gebaut." & vbCrLf & "Im Ordner frontend einmal 'npm run build' ausfuehren.", vbExclamation, "Handball xG"
    WScript.Quit 1
End If

' 0 = unsichtbar, False = nicht warten
shell.CurrentDirectory = root & "\backend"
shell.Run """" & pythonw & """ """ & root & "\backend\run_server.py""", 0, False

' Warten, bis der Server antwortet (max. 20 s)
ready = False
For i = 1 To 40
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
    http.Open "GET", "http://127.0.0.1:8010/api/meta", False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 Then ready = True
    End If
    Err.Clear
    On Error GoTo 0
    If ready Then Exit For
    WScript.Sleep 500
Next

If ready Then
    shell.Run "http://localhost:8010", 1, False
Else
    MsgBox "Der Server ist nicht gestartet. Details: backend\data\server.log", vbExclamation, "Handball xG"
End If
