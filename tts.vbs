' Simple SAPI TTS Wrapper
If WScript.Arguments.Count < 2 Then WScript.Quit

text = WScript.Arguments(0)
persona = WScript.Arguments(1)

Set Sapi = CreateObject("SAPI.SpVoice")
Set Voices = Sapi.GetVoices

' Simple Voice Selection
' 0 = First Voice (Usually David)
' 1 = Second Voice (Usually Zira)

On Error Resume Next

If persona = "soren" Then
    If Voices.Count > 1 Then
        Set Sapi.Voice = Voices.Item(1) ' Try Zira
    Else
        Set Sapi.Voice = Voices.Item(0)
    End If
    Sapi.Rate = 1
Else
    Set Sapi.Voice = Voices.Item(0) ' Try David
    Sapi.Rate = 2
End If

Sapi.Speak text
