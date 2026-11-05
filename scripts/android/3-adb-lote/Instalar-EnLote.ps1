<#
.SYNOPSIS
    Instala la Student en VARIAS tabletas por Wi-Fi a partir de una lista, y deja un informe por tableta.
.DESCRIPTION
    Lee tabletas.txt (una por linea). Formatos:
        192.168.1.50:41234                          tableta ya vinculada: solo conecta e instala
        192.168.1.50:41234;192.168.1.50:37215;123456   vincula primero (direccion de vincular;codigo) y luego instala
    Las lineas vacias y las que empiezan con # se ignoran. Escribe informe-AAAAMMDD-HHMMSS.csv junto a la lista.
.PARAMETER Lista      Archivo de tabletas (por omision tabletas.txt junto a este script).
.PARAMETER Apk        APK a instalar (opcional: se busca solo).
.PARAMETER Reemplazar Desinstala la Student si tiene otra firma (borra sus datos).
#>
[CmdletBinding()]
param([string]$Lista, [string]$Apk, [switch]$Reemplazar)
$ErrorActionPreference = 'Continue'   # adb escribe avisos en stderr; los fallos se controlan con throw
. (Join-Path $PSScriptRoot '..\comun\AdbComun.ps1')
if (-not $Lista) { $Lista = Join-Path $PSScriptRoot 'tabletas.txt' }

Write-Host 'AVACOM Student - instalacion en lote por Wi-Fi' -ForegroundColor Cyan
if (-not (Test-Path $Lista)) {
    $ejemplo = Join-Path $PSScriptRoot 'tabletas.ejemplo.txt'
    if (Test-Path $ejemplo) { Copy-Item $ejemplo $Lista }
    Write-Host "Se creo $Lista con un ejemplo. Abrelo con el Bloc de notas, escribe una tableta por linea, guarda y vuelve a tocar este archivo."
    Start-Process notepad.exe $Lista
    Read-Host 'Pulsa Enter para cerrar' | Out-Null
    exit 0
}
$lineas = @(Get-Content $Lista -Encoding UTF8 | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
if ($lineas.Count -eq 0) { Termina "La lista $Lista no tiene tabletas (borra el # de las lineas de ejemplo o agrega las tuyas)." }

$adb = Obtener-Adb
$apkRuta = Buscar-Apk $Apk
Write-Host "APK: $apkRuta"
Write-Host "Tabletas en la lista: $($lineas.Count)"
& $adb start-server | Out-Null

$informe = @()
$n = 0
foreach ($linea in $lineas) {
    $n++
    $partes = @($linea -split ';' | ForEach-Object { $_.Trim() })
    $destino = $partes[0]
    $estado = ''; $detalle = ''; $modelo = ''
    Paso "[$n/$($lineas.Count)] $destino"
    try {
        if ($destino -notmatch '^\d{1,3}(\.\d{1,3}){3}:\d{2,5}$') { throw 'Direccion mal escrita: debe ser IP:puerto, por ejemplo 192.168.1.50:41234.' }
        if ($partes.Count -ge 3) {
            $p = (& $adb pair $partes[1] $partes[2] 2>&1) -join ' '
            if ($p -notmatch 'Successfully paired') { throw "No vinculo ($p). El codigo de 6 digitos caduca: pide uno nuevo en la tableta." }
        }
        $c = (& $adb connect $destino 2>&1) -join ' '
        if ($c -notmatch 'connected to') { throw "No conecto ($c). Revisa Wi-Fi, que la Depuracion inalambrica siga activa y el puerto actual (cambia al reactivarla)." }
        $est = (& $adb -s $destino get-state 2>&1) -join ''
        if ($est -notmatch 'device') { throw 'La tableta no autorizo este computador: vinculala con codigo (formato de 3 campos) o acepta el aviso en su pantalla.' }
        $modelo = ((& $adb -s $destino shell getprop ro.product.model) -join '').Trim()
        $abi = ((& $adb -s $destino shell getprop ro.product.cpu.abi) -join '').Trim()
        if ($abi -ne 'arm64-v8a' -and $apkRuta -like '*arm64*') { throw "Procesador ${abi}: el APK es arm64." }
        $res = Instalar-En $adb $destino $apkRuta ([bool]$Reemplazar)
        if ($res -ne 'OK') { throw $res }
        $estado = 'OK'; $detalle = 'Instalada'
        Bien 'OK'
    } catch {
        $estado = 'FALLO'; $detalle = $_.Exception.Message
        Write-Host $detalle -ForegroundColor Red
    }
    $informe += [pscustomobject]@{ Tableta = $destino; Modelo = $modelo; Resultado = $estado; Detalle = $detalle }
    & $adb disconnect $destino 2>&1 | Out-Null
}

$csv = Join-Path (Split-Path $Lista) ("informe-{0}.csv" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$informe | Export-Csv -Path $csv -NoTypeInformation -Encoding UTF8
$ok = @($informe | Where-Object Resultado -eq 'OK').Count
Paso 'Resumen'
$informe | Format-Table -AutoSize | Out-Host
$color = 'Green'; if ($ok -lt $informe.Count) { $color = 'Yellow' }
Write-Host "Instaladas: $ok de $($informe.Count). Informe: $csv" -ForegroundColor $color
Read-Host 'Pulsa Enter para cerrar' | Out-Null
