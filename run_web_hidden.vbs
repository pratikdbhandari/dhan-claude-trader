' ============================================================
'  Dhan-Claude Trader — silent launcher
'  Double-click: starts the web app with no console window and
'  opens the Live Market page once the server actually answers.
'
'  Deliberately runs python.exe with the console HIDDEN rather
'  than pythonw.exe: pythonw leaves sys.stdout = None, which
'  crashes uvicorn's logging (see commit a5f105c). A hidden
'  console still has real streams, and we redirect them to
'  web-server.log so a silent start is never a blind one.
'
'  To stop the server: double-click stop_web.bat
' ============================================================
Option Explicit

Dim sh, fso, base, logFile, cmd, http, i, isUp

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base
logFile = base & "\web-server.log"

Const URL_HEALTH = "http://127.0.0.1:8501/health"
Const URL_APP    = "http://127.0.0.1:8501/live"

' --- already running? just open the page, don't start a second server ---
If ServerUp() Then
    sh.Run URL_APP, 1, False
    WScript.Quit 0
End If

' --- start hidden (0 = hidden window, False = don't block) ---
cmd = "cmd /c python -m uvicorn web.server:app --host 127.0.0.1 --port 8501 > """ & logFile & """ 2>&1"
sh.Run cmd, 0, False

' --- wait until it really answers (up to ~30s), then open the browser ---
isUp = False
For i = 1 To 60
    WScript.Sleep 500
    If ServerUp() Then
        isUp = True
        Exit For
    End If
Next

If isUp Then
    sh.Run URL_APP, 1, False
Else
    MsgBox "The trading app did not start within 30 seconds." & vbCrLf & vbCrLf & _
           "Error details were written to:" & vbCrLf & logFile & vbCrLf & vbCrLf & _
           "Open that file to see what went wrong.", _
           vbCritical, "Dhan-Claude Trader"
    sh.Run "notepad.exe """ & logFile & """", 1, False
End If

' True only when OUR app answers. Checking for the "dhan-claude-trader" marker
' rather than a bare 200 matters: Streamlit (run_app.bat) and other servers also
' answer /health on 8501, and opening the browser at one of those is exactly the
' wrong-app confusion this launcher exists to prevent.
Function ServerUp()
    ServerUp = False
    On Error Resume Next
    Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "GET", URL_HEALTH, False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 And InStr(http.responseText, "dhan-claude-trader") > 0 Then
            ServerUp = True
        End If
    End If
    Err.Clear
    On Error GoTo 0
End Function
