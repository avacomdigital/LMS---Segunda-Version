# Arranca AVACOM Student (compilado para Windows) y deja su pid en salida\student.pid para los guiones.
# Uso: powershell -File lanzar-student.ps1 [-Exe <ruta al exe>]
param([string]$Exe = "$PSScriptRoot\..\..\src\Avacom.Lms.Student\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Student.exe")
New-Item -ItemType Directory -Force "$PSScriptRoot\salida" | Out-Null
$p = Start-Process -PassThru $Exe
Start-Sleep -Seconds 8
$p.Id | Out-File -Encoding ascii "$PSScriptRoot\salida\student.pid"
Write-Output ("Student pid " + $p.Id)
