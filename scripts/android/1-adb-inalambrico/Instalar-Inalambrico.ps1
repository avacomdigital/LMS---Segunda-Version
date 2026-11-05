<#
.SYNOPSIS
    Instala la Student en UNA tableta Android 11+ por Wi-Fi (depuracion inalambrica), sin cable ni drivers.
.PARAMETER Apk        APK a instalar (opcional: se busca solo).
.PARAMETER Reemplazar Si hay otra Student con distinta firma, la desinstala (borra sus datos).
#>
[CmdletBinding()]
param([string]$Apk, [switch]$Reemplazar)
$ErrorActionPreference = 'Continue'   # adb escribe avisos en stderr
. (Join-Path $PSScriptRoot '..\comun\AdbComun.ps1')

Write-Host 'AVACOM Student - instalacion por Wi-Fi (sin cable)' -ForegroundColor Cyan
$adb = Obtener-Adb
$apkRuta = Buscar-Apk $Apk
Write-Host "APK: $apkRuta"

Paso 'En la tableta (el computador y la tableta deben estar en el MISMO Wi-Fi)'
Write-Host '  1. Ajustes > Opciones de desarrollador > Depuracion inalambrica: ACTIVALA.'
Write-Host '  2. Toca el texto "Depuracion inalambrica" (no el interruptor) para entrar.'
Write-Host '  3. Toca "Vincular dispositivo con codigo de vinculacion".'
Write-Host '  4. Veras un codigo de 6 digitos y una direccion como 192.168.1.50:37215.'
Read-Host 'Cuando lo veas en pantalla, pulsa Enter'

& $adb start-server | Out-Null
$vinculado = $false
while (-not $vinculado) {
    $dirPar = (Read-Host 'Escribe la direccion de VINCULACION que muestra la tableta (con los dos puntos y el numero)').Trim()
    $codigo = (Read-Host 'Escribe el codigo de 6 digitos').Trim()
    if ($dirPar -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$') { Aviso 'La direccion debe verse como 192.168.1.50:37215. Intenta otra vez.'; continue }
    $r = (& $adb pair $dirPar $codigo 2>&1) -join ' '
    Write-Host $r
    if ($r -match 'Successfully paired') { $vinculado = $true }
    else { Aviso 'No se pudo vincular. El codigo caduca: en la tableta cierra el aviso, toca de nuevo "Vincular dispositivo" y usa el codigo nuevo.' }
}
Bien 'Vinculada.'

Paso 'Conectando'
Write-Host 'Mira la pantalla principal de "Depuracion inalambrica": arriba dice "Direccion IP y puerto" (otro numero distinto al de vincular).'
$conectado = $false
$destino = ''
while (-not $conectado) {
    $destino = (Read-Host 'Escribe esa direccion IP y puerto').Trim()
    $r = (& $adb connect $destino 2>&1) -join ' '
    Write-Host $r
    if ($r -match 'connected to') { $conectado = $true } else { Aviso 'No conecto. Revisa que el puerto sea el de la pantalla principal, no el de vincular.' }
}

Paso 'Comprobando la tableta'
$android = ((& $adb -s $destino shell getprop ro.build.version.release) -join '').Trim()
$abi = ((& $adb -s $destino shell getprop ro.product.cpu.abi) -join '').Trim()
Write-Host "Android $android, procesador $abi"
if ($abi -ne 'arm64-v8a' -and $apkRuta -like '*arm64*') { Termina "La tableta es $abi y el APK es arm64." }

Paso 'Instalando la Student (puede tardar un minuto)'
$res = Instalar-En $adb $destino $apkRuta ([bool]$Reemplazar)
if ($res -ne 'OK') { Termina $res }
Bien "`nListo: Student instalada. Ya puedes desactivar la Depuracion inalambrica en la tableta."
Read-Host 'Pulsa Enter para cerrar' | Out-Null
