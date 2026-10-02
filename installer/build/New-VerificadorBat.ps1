<#
.SYNOPSIS
    Genera el verificador de un solo archivo: AVACOM-Verificar-Instalador.bat

.DESCRIPTION
    Es el .bat que se entrega junto al instalador (installer\latest) y que sirve
    para dos cosas:

      * ANTES de instalar: comprueba que la descarga esta completa (SHA256), ejecuta
        las diez comprobaciones del asistente (sin instalar) y revisa el equipo.
      * DESPUES, cuando algo falla en el aula (por ejemplo, la aplicacion se cierra
        al abrir una leccion): recoge el error exacto -Visor de eventos de Windows y
        el registro de fallos de la aplicacion de cada usuario-, comprueba permisos,
        servicio, registros y la comunicacion con AVACOM Contenido, y deja un informe
        y un .zip con las evidencias en el escritorio.

    El nodo principal del aula es tactil y no tiene teclado, asi que tiene que poder
    lanzarse con un toque y sin escribir nada. Eso descarta un .ps1 suelto: Windows
    no lo ejecuta con un doble toque (lo abre en el Bloc de notas) y, al descargarlo
    de la release, queda marcado como venido de internet y la directiva RemoteSigned
    lo bloquea. Este script mete el PowerShell DENTRO del .bat, detras de un
    marcador: al ejecutarlo, la parte de lotes se lee a si misma, extrae el
    PowerShell a un temporal y lo corre con la directiva en Bypass.

    Se genera en lugar de mantenerse a mano para que el .bat no se quede atras: la
    unica fuente es installer\tools\Verificar-Instalador.ps1.

.NOTES
    El .bat se escribe en UTF-8 SIN BOM: cmd.exe se atraganta con el BOM en la
    primera linea. Por eso la parte de lotes es ASCII puro y el PowerShell, que si
    lleva acentos, se lee explicitamente como UTF-8 desde .NET.
#>
[CmdletBinding()]
param(
    [string] $Origen = '',
    [string] $Destino = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Origen)  { $Origen  = Join-Path $raiz 'installer\tools\Verificar-Instalador.ps1' }
if (-not $Destino) { $Destino = Join-Path $raiz 'installer\latest\AVACOM-Verificar-Instalador.bat' }

if (-not (Test-Path $Origen)) { throw "No se encontro el verificador en $Origen." }
New-Item -ItemType Directory -Force (Split-Path $Destino -Parent) | Out-Null

# Lo que se incrusta es el texto, no los bytes del archivo. El BOM se recorta comparando el
# caracter, no con StartsWith (sensible a la cultura: U+FEFF es ignorable y StartsWith
# devolveria True sobre cualquier cadena, llevandose por delante el primer caracter bueno).
$powershell = [System.IO.File]::ReadAllText($Origen, [System.Text.UTF8Encoding]::new($false))
while ($powershell.Length -gt 0 -and [int]$powershell[0] -eq 0xFEFF) {
    $powershell = $powershell.Substring(1)
}

# El marcador se parte en dos en la linea que lo busca para que la unica aparicion
# literal en el archivo sea la que separa las dos mitades.
$cabecera = @'
@echo off
rem ===========================================================================
rem  AVACOM OPS Master - Verificador del instalador y del equipo
rem
rem  UN SOLO ARCHIVO. No necesita nada mas (salvo el instalador y SHA256.txt, si
rem  quieres comprobarlos): el verificador va dentro de este mismo .bat, detras
rem  del marcador de abajo.
rem
rem  Uso: toca este archivo. Al terminar deja en el escritorio un informe y un
rem  .zip con las evidencias, y abre el informe.
rem
rem  Sirve ANTES de instalar (descarga completa, comprobaciones del equipo) y
rem  DESPUES, si algo falla (por ejemplo, la aplicacion se cierra al abrir una
rem  leccion): busca el error exacto, revisa permisos, servicio, registros y la
rem  comunicacion con AVACOM Contenido.
rem
rem  No cambia la configuracion, los datos ni el servicio. Para probar los
rem  permisos crea y borra al instante un archivo temporal.
rem
rem  Generado por installer\build\New-VerificadorBat.ps1 desde
rem  installer\tools\Verificar-Instalador.ps1. No editar a mano.
rem ===========================================================================
setlocal
title AVACOM OPS Master - Verificador

rem  /silencioso: sin abrir el informe ni esperar un toque al final (para automatizar).
set "ABRIR=-Abrir"
if /i "%~1"=="/silencioso" set "ABRIR="

echo.
echo   AVACOM OPS Master
echo   Verificador del instalador y del equipo
echo.
echo   Revisando... esto tarda entre 10 y 60 segundos.
echo   Si hay un instalador junto a este archivo, Windows pedira permiso de
echo   administrador UNA vez para las comprobaciones del asistente: tocalo.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8); $m='#@AVACOM'+'-VERIFICADOR@'; $i=$t.IndexOf($m); if($i -lt 0){ Write-Host '  El archivo esta incompleto: vuelve a descargarlo.' -ForegroundColor Red; exit 9 }; $f=Join-Path $env:TEMP ('avacom-verificador-'+[guid]::NewGuid().ToString('N')+'.ps1'); [IO.File]::WriteAllText($f,$t.Substring($i+$m.Length),(New-Object Text.UTF8Encoding($true))); $r=9; try { & $f %ABRIR% -Paquete -CarpetaDelInstalador '%~dp0.'; $r=$LASTEXITCODE } finally { Remove-Item $f -Force -ErrorAction SilentlyContinue }; exit $r"

set CODIGO=%ERRORLEVEL%
echo.
if "%CODIGO%"=="0" echo   Resultado: todo en orden.
if "%CODIGO%"=="1" echo   Resultado: hay problemas que resolver. Mira el informe.
if "%CODIGO%"=="2" echo   Resultado: funciona, con avisos. Mira el informe.
if "%CODIGO%"=="9" echo   Resultado: el verificador no pudo ejecutarse.
echo.
if /i not "%~1"=="/silencioso" pause
exit /b %CODIGO%

rem #@AVACOM-VERIFICADOR@
'@

# CRLF en todo el archivo: cmd.exe lo exige en la parte de lotes. El salto entre el marcador
# y el PowerShell es explicito porque un here-string no conserva su ultima linea en blanco.
$contenido = ($cabecera -replace "`r?`n", "`r`n") + "`r`n" + ($powershell -replace "`r?`n", "`r`n")

[System.IO.File]::WriteAllText($Destino, $contenido, [System.Text.UTF8Encoding]::new($false))

# --- Comprobaciones de lo que hace que esto funcione o no.
$bytes = [System.IO.File]::ReadAllBytes($Destino)
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    throw 'El .bat quedo con BOM: cmd.exe no ejecutaria la primera linea.'
}

# La parte de lotes (hasta el marcador) tiene que ser ASCII puro: cmd.exe no lee acentos con seguridad.
$texto = [System.IO.File]::ReadAllText($Destino, [System.Text.Encoding]::UTF8)
$marcador = '#@AVACOM' + '-VERIFICADOR@'
$apariciones = ([regex]::Matches($texto, [regex]::Escape($marcador))).Count
if ($apariciones -ne 1) {
    throw "El marcador aparece $apariciones veces y debe aparecer exactamente una."
}
$parteDeLotes = $texto.Substring(0, $texto.IndexOf($marcador))
if ($parteDeLotes -match '[^\x00-\x7F]') {
    throw 'La parte de lotes del .bat tiene caracteres no ASCII: cmd.exe los leeria mal.'
}

# Prueba de la extraccion, hecha igual que la hace el .bat: generar un .bat valido no sirve de
# nada si lo que extrae no es PowerShell valido, y eso no se ve hasta ejecutarlo en el aula.
$extraido = $texto.Substring($texto.IndexOf($marcador) + $marcador.Length)
if (-not $extraido.TrimStart("`r", "`n").StartsWith('<#')) {
    throw 'Lo extraido no empieza donde debe: el .bat no produciria PowerShell valido.'
}

$erroresDeAnalisis = $null
[void][System.Management.Automation.Language.Parser]::ParseInput($extraido, [ref]$null, [ref]$erroresDeAnalisis)
if ($erroresDeAnalisis -and $erroresDeAnalisis.Count -gt 0) {
    $erroresDeAnalisis | Select-Object -First 5 | ForEach-Object {
        Write-Host "  linea $($_.Extent.StartLineNumber): $($_.Message)" -ForegroundColor Red
    }
    throw "El PowerShell incrustado tiene $($erroresDeAnalisis.Count) error(es) de sintaxis."
}

$kb = [math]::Round((Get-Item $Destino).Length / 1KB, 1)
Write-Host "  $Destino  ($kb KB, un solo archivo)"
