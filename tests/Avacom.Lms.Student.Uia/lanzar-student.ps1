# Arranca AVACOM Student (compilado para Windows) y deja su pid en salida\student.pid para los guiones.
# Uso: powershell -File lanzar-student.ps1 [-Exe <ruta al exe>] [-SinFoco]
# -SinFoco: en cuanto la ventana se activó (WinUI no expone su árbol a UI Automation hasta entonces) el foco vuelve a la ventana que estaba delante.
# Sin esto, lo que el usuario teclee en otra ventana mientras corre la prueba cae en Student (y puede marcar un PIN equivocado).
param([string]$Exe = "$PSScriptRoot\..\..\src\Avacom.Lms.Student\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Student.exe", [switch]$SinFoco)
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class VentanaSinFoco {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
New-Item -ItemType Directory -Force "$PSScriptRoot\salida" | Out-Null
$antes = [VentanaSinFoco]::GetForegroundWindow()
$p = Start-Process -PassThru $Exe
if ($SinFoco) {
    for ($i = 0; $i -lt 60; $i++) { Start-Sleep -Milliseconds 250; $p.Refresh(); if ($p.MainWindowHandle -ne [IntPtr]::Zero) { break } }
    Start-Sleep -Seconds 4
    if ($antes -ne [IntPtr]::Zero -and $antes -ne $p.MainWindowHandle) { [VentanaSinFoco]::SetForegroundWindow($antes) | Out-Null }
}
Start-Sleep -Seconds 8
$p.Id | Out-File -Encoding ascii "$PSScriptRoot\salida\student.pid"
Write-Output ("Student pid " + $p.Id)
