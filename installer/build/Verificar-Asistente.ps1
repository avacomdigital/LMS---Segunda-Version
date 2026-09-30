<#
.SYNOPSIS
    Comprueba que el código del asistente funciona, no solo que compila.

.DESCRIPTION
    Compila PruebaAsistente.iss -que incluye tal cual la lógica de
    installer\src\codigo.iss- y la ejecuta en modo diagnóstico. Así se prueba
    en un Windows real lo que ningún compilador puede comprobar:

        · que se parsea la salida de netstat para saber quién usa el puerto,
        · que se le pregunta a /health/ por COM para distinguir nuestro backend
          de un programa ajeno,
        · que se detectan los procesos abiertos y la instalación previa,
        · que se detecta AVACOM Contenido (link.json),
        · que los controles de la página táctil se crean sin fallar.

    No instala nada y no necesita permisos de administrador: el propio
    asistente aborta en cuanto ha escrito el diagnóstico.

    Ojo con la lectura: en una sesión de desarrollo es NORMAL que salgan en
    rojo «permisos de administrador» (el arnés corre sin elevar) y «AVACOM OPS
    Master está abierto» (si lo tienes abierto). Lo que se verifica aquí es que
    las diez comprobaciones se ejecutan y dan un veredicto, no que este equipo
    concreto esté listo para instalar.
#>
[CmdletBinding()]
param(
    [string] $Iscc
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $Iscc) {
    $Iscc = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw 'No se encontro Inno Setup 6.' }

$guion = Join-Path $PSScriptRoot 'PruebaAsistente.iss'
$arnes = Join-Path $PSScriptRoot 'PruebaAsistente.exe'
$volcado = Join-Path ([IO.Path]::GetTempPath()) 'avacom-diagnostico-asistente.txt'

Remove-Item $arnes, $volcado -Force -ErrorAction SilentlyContinue

$bitacora = Join-Path ([IO.Path]::GetTempPath()) 'avacom-arnes-iscc.txt'
$compilacion = Start-Process -FilePath $Iscc -ArgumentList $guion -WorkingDirectory $PSScriptRoot `
    -Wait -PassThru -NoNewWindow -RedirectStandardOutput $bitacora -RedirectStandardError "$bitacora.err"
if ($compilacion.ExitCode -ne 0) {
    Get-Content $bitacora, "$bitacora.err" -ErrorAction SilentlyContinue |
        Select-Object -Last 20 | ForEach-Object { Write-Host "  $_" }
    throw 'El codigo del asistente no compila.'
}

# El arnes aborta a proposito, asi que su codigo de salida no es 0.
$ejecucion = Start-Process -FilePath $arnes `
    -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', "/VOLCADO=$volcado" -Wait -PassThru
Remove-Item $arnes -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $volcado)) {
    throw "El asistente no llego a ejecutar sus comprobaciones (codigo $($ejecucion.ExitCode))."
}

$lineas = Get-Content $volcado -Encoding UTF8
Remove-Item $volcado -Force -ErrorAction SilentlyContinue

# @() fuerza un arreglo: con StrictMode, .Count sobre $null o sobre una sola
# cadena es un error, y justamente el caso de cero comprobaciones es el que hay
# que poder detectar.
$comprobaciones = @($lineas | Where-Object { $_ -like 'check: *' })
if ($comprobaciones.Count -ne 10) {
    $lineas | ForEach-Object { Write-Host "  $_" }
    throw "Se esperaban 10 comprobaciones y se ejecutaron $($comprobaciones.Count)."
}
if (-not ($lineas | Where-Object { $_ -like 'Resultado:*' })) {
    throw 'El asistente no emitio un veredicto.'
}

$comprobaciones | ForEach-Object { Write-Host "  $_" }
Write-Host '  Las 10 comprobaciones del asistente se ejecutaron y dieron veredicto.'
