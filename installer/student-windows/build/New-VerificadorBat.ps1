<#
.SYNOPSIS
    Genera el verificador de un solo archivo: AVACOM-Verificar-Student.bat

.DESCRIPTION
    Es el .bat que se entrega junto al instalador de Student (installer\student-windows\latest) y que
    sirve para dos cosas:

      * ANTES de instalar: comprueba que la descarga esta completa (SHA256), ejecuta las ocho
        comprobaciones del asistente (sin instalar) y revisa el equipo.
      * DESPUES, cuando algo falla (por ejemplo, la aplicacion se cierra al abrir una leccion, o no
        encuentra el aula): recoge el error exacto -Visor de eventos de Windows y los registros de
        fallos de la aplicacion y del lanzador de cada usuario-, comprueba permisos y la
        comunicacion con AVACOM OPS Master, y deja un informe y un .zip con las evidencias en el
        escritorio.

    Tiene que poder lanzarse con un toque y sin escribir nada. Eso descarta un .ps1 suelto: Windows no
    lo ejecuta con un doble toque (lo abre en el Bloc de notas) y, al descargarlo, queda marcado como
    venido de internet y la directiva RemoteSigned lo bloquea. Este script mete el PowerShell DENTRO
    del .bat, detras de un marcador: al ejecutarlo, la parte de lotes se lee a si misma, extrae el
    PowerShell a un temporal y lo corre con la directiva en Bypass.

    Se genera en lugar de mantenerse a mano para que el .bat no se quede atras: la unica fuente es
    installer\student-windows\tools\Verificar-Student.ps1.

.NOTES
    El .bat se escribe en UTF-8 SIN BOM: cmd.exe se atraganta con el BOM en la primera linea. Por eso
    la parte de lotes es ASCII puro y el PowerShell, que si lleva acentos, se lee explicitamente como
    UTF-8 desde .NET.
#>
[CmdletBinding()]
param(
    [string] $Origen = '',
    [string] $Destino = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
if (-not $Origen)  { $Origen  = Join-Path $raiz 'installer\student-windows\tools\Verificar-Student.ps1' }
if (-not $Destino) { $Destino = Join-Path $raiz 'installer\student-windows\latest\AVACOM-Verificar-Student.bat' }

if (-not (Test-Path $Origen)) { throw "No se encontro el verificador en $Origen." }
New-Item -ItemType Directory -Force (Split-Path $Destino -Parent) | Out-Null

# Lo que se incrusta es el texto, no los bytes del archivo. El BOM se recorta comparando el caracter.
$powershell = [System.IO.File]::ReadAllText($Origen, [System.Text.UTF8Encoding]::new($false))
while ($powershell.Length -gt 0 -and [int]$powershell[0] -eq 0xFEFF) {
    $powershell = $powershell.Substring(1)
}

$cabecera = @'
@echo off
rem ===========================================================================
rem  AVACOM Student (Windows) - Verificador del instalador y del equipo
rem
rem  UN SOLO ARCHIVO. No necesita nada mas (salvo el instalador y SHA256.txt, si
rem  quieres comprobarlos): el verificador va dentro de este mismo .bat, detras
rem  del marcador de abajo.
rem
rem  Uso: toca este archivo. Al terminar deja en el escritorio un informe y un
rem  .zip con las evidencias, y abre el informe.
rem
rem  Opcional: AVACOM-Verificar-Student.bat http://192.168.0.55:8000
rem  comprueba esa direccion del aula en lugar de la que Student tiene guardada.
rem
rem  Sirve ANTES de instalar (descarga completa, comprobaciones del equipo) y
rem  DESPUES, si algo falla (por ejemplo, la aplicacion se cierra al abrir una
rem  leccion, o no encuentra el aula): busca el error exacto, revisa permisos,
rem  el perfil de WebView2 y la comunicacion con AVACOM OPS Master.
rem
rem  No cambia la configuracion ni los datos. Para probar los permisos crea y
rem  borra al instante un archivo temporal.
rem
rem  Generado por installer\student-windows\build\New-VerificadorBat.ps1 desde
rem  installer\student-windows\tools\Verificar-Student.ps1. No editar a mano.
rem ===========================================================================
setlocal
title AVACOM Student - Verificador

rem  /silencioso: sin abrir el informe ni esperar un toque al final (para automatizar).
set "ABRIR=-Abrir"
set "AULA="
if /i "%~1"=="/silencioso" set "ABRIR="
if not "%~1"=="" if /i not "%~1"=="/silencioso" set "AULA=-Aula '%~1'"

echo.
echo   AVACOM Student
echo   Verificador del instalador y del equipo
echo.
echo   Revisando... esto tarda entre 10 y 60 segundos.
echo   Si hay un instalador junto a este archivo, Windows pedira permiso de
echo   administrador UNA vez para las comprobaciones del asistente: tocalo.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8); $m='#@AVACOM'+'-VERIFICADOR@'; $i=$t.IndexOf($m); if($i -lt 0){ Write-Host '  El archivo esta incompleto: vuelve a descargarlo.' -ForegroundColor Red; exit 9 }; $f=Join-Path $env:TEMP ('avacom-student-verificador-'+[guid]::NewGuid().ToString('N')+'.ps1'); [IO.File]::WriteAllText($f,$t.Substring($i+$m.Length),(New-Object Text.UTF8Encoding($true))); $r=9; try { & $f %ABRIR% %AULA% -Paquete -CarpetaDelInstalador '%~dp0.'; $r=$LASTEXITCODE } finally { Remove-Item $f -Force -ErrorAction SilentlyContinue }; exit $r"

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

# CRLF en todo el archivo: cmd.exe lo exige en la parte de lotes.
$contenido = ($cabecera -replace "`r?`n", "`r`n") + "`r`n" + ($powershell -replace "`r?`n", "`r`n")

[System.IO.File]::WriteAllText($Destino, $contenido, [System.Text.UTF8Encoding]::new($false))

# --- Comprobaciones de lo que hace que esto funcione o no.
$bytes = [System.IO.File]::ReadAllBytes($Destino)
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    throw 'El .bat quedo con BOM: cmd.exe no ejecutaria la primera linea.'
}

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

# Prueba de la extraccion, hecha igual que la hace el .bat: generar un .bat valido no sirve de nada
# si lo que extrae no es PowerShell valido.
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
