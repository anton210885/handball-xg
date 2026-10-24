' Handball xG beenden – stoppt den unsichtbar laufenden Server.
Option Explicit
Dim wmi, procs, p, n
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name LIKE 'python%' AND CommandLine LIKE '%handball-xg%run_server.py%'")
n = 0
' pythonw aus der venv startet einen zweiten Prozess; endet einer, ist der andere evtl. schon weg
On Error Resume Next
For Each p In procs
    p.Terminate
    n = n + 1
Next
On Error GoTo 0
If n > 0 Then
    MsgBox "Handball xG wurde beendet.", vbInformation, "Handball xG"
Else
    MsgBox "Handball xG lief nicht.", vbInformation, "Handball xG"
End If
