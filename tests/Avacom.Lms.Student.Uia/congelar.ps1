# Congela un proceso unos segundos (NtSuspendProcess) para que el nodo deje de recibir su latido, y lo reanuda.
# Sirve para ver, sin tocar la red, cómo la tableta vive que su examen quedó en pausa (PAN-122). Úsalo SÓLO con una instancia de prueba propia.
# Uso: powershell -File congelar.ps1 -ProcId 1234 -Segundos 14
param([int]$ProcId, [int]$Segundos = 14)
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Nt {
    [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr h);
    [DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr h);
}
"@
$p = Get-Process -Id $ProcId -ErrorAction Stop
$h = $p.Handle
[Nt]::NtSuspendProcess($h) | Out-Null
Write-Output "CONGELADO $ProcId por $Segundos s"
try { Start-Sleep -Seconds $Segundos } finally { [Nt]::NtResumeProcess($h) | Out-Null; Write-Output "REANUDADO $ProcId" }
