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
    [string] $Iscc,
    # La política de datos con que se compila el instalador (la de Build-Installer.ps1). Sin ella, la de definiciones.iss.
    [ValidateSet('', 'reemplazables', 'protegidos')] [string] $PoliticaDatos = ''
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
$bitacora = Join-Path ([IO.Path]::GetTempPath()) 'avacom-arnes-iscc.txt'

# Compila el arnés (con la política indicada, o la de definiciones.iss si va vacía), lo ejecuta en modo diagnóstico y devuelve las líneas del volcado.
function Correr-Arnes([string] $politica) {
    Remove-Item $arnes, $volcado -Force -ErrorAction SilentlyContinue
    $argumentos = @()
    if ($politica) { $argumentos += "/DPoliticaDatos=$politica" }
    $argumentos += $guion
    $compilacion = Start-Process -FilePath $Iscc -ArgumentList $argumentos -WorkingDirectory $PSScriptRoot `
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
    return $lineas
}

$lineas = Correr-Arnes $PoliticaDatos

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

# ---- La política de datos: la pantalla «Datos del aula» (Conservar / Empezar de cero) se ofrece SOLO con datos reemplazables.
# Se prueba la política real del instalador Y la contraria, para demostrar que la lógica distingue (no que siempre diga lo mismo).
function Pantalla-De([string[]] $volcadoDeLineas) {
    $linea = @($volcadoDeLineas | Where-Object { $_ -like 'Pantalla de datos con datos previos: *' })
    if ($linea.Count -ne 1) { throw "El diagnostico no dice si se ofrece la pantalla de datos: $($volcadoDeLineas -join ' | ')" }
    return ($linea[0] -replace '^Pantalla de datos con datos previos: ', '').Trim()
}
function Politica-De([string[]] $volcadoDeLineas) {
    $linea = @($volcadoDeLineas | Where-Object { $_ -like 'Politica de datos: *' })
    if ($linea.Count -ne 1) { throw "El diagnostico no dice la politica de datos: $($volcadoDeLineas -join ' | ')" }
    return ($linea[0] -replace '^Politica de datos: ', '').Trim()
}
$esperada = @{ 'protegidos' = 'no'; 'reemplazables' = 'si' }
$real = Politica-De $lineas
if (-not $esperada.ContainsKey($real)) { throw "Politica de datos desconocida en el diagnostico: '$real'." }
if ($PoliticaDatos -and $real -ne $PoliticaDatos) { throw "Se compilo con la politica '$PoliticaDatos' y el diagnostico dice '$real'." }
if ((Pantalla-De $lineas) -ne $esperada[$real]) {
    throw "Con datos $real la pantalla de eleccion de datos deberia ofrecerse = '$($esperada[$real])' y el diagnostico dice '$(Pantalla-De $lineas)'."
}
$contraria = if ($real -eq 'protegidos') { 'reemplazables' } else { 'protegidos' }
$lineasContraria = Correr-Arnes $contraria
if ((Politica-De $lineasContraria) -ne $contraria -or (Pantalla-De $lineasContraria) -ne $esperada[$contraria]) {
    throw "Con datos $contraria la pantalla de eleccion deberia ofrecerse = '$($esperada[$contraria])': la logica no distingue las politicas."
}
Write-Host "  Politica de datos '$real': la pantalla de eleccion de datos $(if ($esperada[$real] -eq 'no') { 'NO se ofrece (los datos se conservan siempre)' } else { 'se ofrece' }); con '$contraria' $(if ($esperada[$contraria] -eq 'no') { 'no se ofreceria' } else { 'se ofreceria' }): la logica distingue."
