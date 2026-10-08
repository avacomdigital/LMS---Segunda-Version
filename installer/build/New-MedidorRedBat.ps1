<#
.SYNOPSIS
    Genera el medidor de red de un solo archivo: AVACOM-Medir-Red.bat

.DESCRIPTION
    Mide la latencia, el jitter, la pérdida y la velocidad de descarga y de carga entre una laptop (o el propio equipo del nodo) y el nodo de AVACOM OPS,
    pasando por el router, para saber si la red del aula aguanta 35 tabletas. La medición está en installer\tools\Medir-Red.ps1; este script la mete DENTRO de
    un .bat por las mismas razones que el probador de comunicación (ver New-ProbadorBat.ps1): un .bat se ejecuta con un doble toque, no hay que escribir
    nada y la directiva de ejecución de PowerShell no lo bloquea por venir de internet.

    Uso desde el .bat (todo opcional; sin nada, busca el nodo solo):
        AVACOM-Medir-Red.bat                       busca el nodo en la red y mide
        AVACOM-Medir-Red.bat 192.168.1.10          mide contra ese nodo
        AVACOM-Medir-Red.bat 192.168.1.10 /rapido  pruebas de 5 s en vez de 12 s
        AVACOM-Medir-Red.bat /internet             añade la prueba contra Internet aunque no se detecte salida
        AVACOM-Medir-Red.bat /sininternet          sin la prueba de Internet

.NOTES
    El .bat se escribe en UTF-8 SIN BOM (cmd.exe se atraganta con él en la primera línea); la parte de lotes es ASCII puro y el PowerShell, que lleva
    acentos, se lee como UTF-8 desde .NET y se guarda CON BOM en el archivo temporal que ejecuta Windows PowerShell 5.1.
#>
[CmdletBinding()]
param(
    [string] $Origen = '',
    [string[]] $Destino = @()
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Origen)  { $Origen  = Join-Path $raiz 'installer\tools\Medir-Red.ps1' }
if ($Destino.Count -eq 0) { $Destino = @(Join-Path $raiz 'installer\tools\AVACOM-Medir-Red.bat') }
if (-not (Test-Path $Origen)) { throw "No se encontro el medidor en $Origen." }

# Se incrusta el texto, no los bytes; el BOM se recorta comparando el caracter (StartsWith con U+FEFF es sensible a la cultura: ver New-ProbadorBat.ps1).
$powershell = [System.IO.File]::ReadAllText($Origen, [System.Text.UTF8Encoding]::new($false))
while ($powershell.Length -gt 0 -and [int]$powershell[0] -eq 0xFEFF) { $powershell = $powershell.Substring(1) }

$cabecera = @'
@echo off
rem ===========================================================================
rem  AVACOM - Medicion de la red del aula (latencia, bajada y subida)
rem
rem  UN SOLO ARCHIVO. Mide cuanto aguanta el camino laptop <-> router <-> nodo
rem  (AVACOM OPS) para saber si la red soporta 35 tabletas. Correlo desde una
rem  laptop conectada por WIFI al mismo router que las tabletas, con AVACOM OPS
rem  encendido. Si lo corres en el propio equipo del nodo mide al servidor.
rem
rem  Uso:  toca este archivo (busca el nodo solo), o desde una consola:
rem          AVACOM-Medir-Red.bat 192.168.1.10          (direccion del nodo)
rem          AVACOM-Medir-Red.bat 192.168.1.10 /rapido  (pruebas de 5 s)
rem          AVACOM-Medir-Red.bat /internet | /sininternet
rem
rem  No instala nada, no cambia configuracion y no toca el expediente: solo
rem  manda y recibe ceros. Deja un informe en el escritorio y lo abre.
rem
rem  Generado por installer\build\New-MedidorRedBat.ps1 desde
rem  installer\tools\Medir-Red.ps1. No editar a mano.
rem ===========================================================================
setlocal
title AVACOM - Medicion de red

echo.
echo   AVACOM - Medicion de la red del aula
echo   Latencia, jitter, perdida, bajada y subida. Tarda 1 o 2 minutos.
echo   Deja este equipo quieto y no uses el Wi-Fi para otra cosa mientras mide.
echo.

set "AVACOM_ARGS=%*"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $t=[IO.File]::ReadAllText('%~f0',[Text.Encoding]::UTF8); $m='#@AVACOM'+'-MEDIR-RED@'; $i=$t.IndexOf($m); if($i -lt 0){ Write-Host '  El archivo esta incompleto: vuelve a descargarlo.' -ForegroundColor Red; exit 9 }; $f=Join-Path $env:TEMP ('avacom-medir-red-'+[guid]::NewGuid().ToString('N')+'.ps1'); [IO.File]::WriteAllText($f,$t.Substring($i+$m.Length),(New-Object Text.UTF8Encoding($true))); $p=@{ Abrir=$true }; foreach($x in @($env:AVACOM_ARGS -split '\s+' | Where-Object { $_ })){ switch -regex ($x){ '^[/-](rapido|r)$' { $p.Rapido=$true } '^[/-]internet$' { $p.Internet=$true } '^[/-]sininternet$' { $p.SinInternet=$true } default { if(-not $p.ContainsKey('Nodo')){ $p.Nodo=$x } } } }; $r=9; try { & $f @p; $r=$LASTEXITCODE } finally { Remove-Item $f -Force -ErrorAction SilentlyContinue }; exit $r"

set CODIGO=%ERRORLEVEL%
echo.
if "%CODIGO%"=="0" echo   Resultado: la red aguanta 35 tabletas.
if "%CODIGO%"=="1" echo   Resultado: la red NO aguanta, o no se pudo medir. Mira el informe.
if "%CODIGO%"=="2" echo   Resultado: la red aguanta, con avisos. Mira el informe.
if "%CODIGO%"=="9" echo   El medidor no pudo arrancar.
echo.
rem Si se abrio con doble toque, la ventana esperaria a ser leida; desde una consola no estorba.
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
exit /b %CODIGO%

rem #@AVACOM-MEDIR-RED@
'@

$contenido = ($cabecera -replace "`r?`n", "`r`n") + "`r`n" + ($powershell -replace "`r?`n", "`r`n")

foreach ($d in $Destino) {
    [System.IO.File]::WriteAllText($d, $contenido, [System.Text.UTF8Encoding]::new($false))

    $bytes = [System.IO.File]::ReadAllBytes($d)
    if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { throw 'El .bat quedo con BOM: cmd.exe no ejecutaria la primera linea.' }
    $texto = [System.IO.File]::ReadAllText($d, [System.Text.Encoding]::UTF8)
    $marcador = '#@AVACOM' + '-MEDIR-RED@'
    $apariciones = ([regex]::Matches($texto, [regex]::Escape($marcador))).Count
    if ($apariciones -ne 1) { throw "El marcador aparece $apariciones veces y debe aparecer exactamente una." }

    # La parte de lotes tiene que ser ASCII puro (cmd.exe lee el archivo con la pagina de codigos del sistema).
    $lotes = $texto.Substring(0, $texto.IndexOf($marcador))
    if ($lotes -match '[^\x00-\x7F]') { throw 'La parte de lotes del .bat tiene caracteres que no son ASCII.' }

    # Prueba de la extraccion hecha igual que la hace el .bat: lo extraido debe ser PowerShell que parsee.
    $extraido = $texto.Substring($texto.IndexOf($marcador) + $marcador.Length)
    if (-not $extraido.TrimStart("`r", "`n").StartsWith('<#')) { throw 'Lo extraido no empieza donde debe: el .bat no produciria PowerShell valido.' }
    $erroresDeAnalisis = $null
    [void][System.Management.Automation.Language.Parser]::ParseInput($extraido, [ref]$null, [ref]$erroresDeAnalisis)
    if ($erroresDeAnalisis -and $erroresDeAnalisis.Count -gt 0) {
        $erroresDeAnalisis | Select-Object -First 5 | ForEach-Object { Write-Host "  linea $($_.Extent.StartLineNumber): $($_.Message)" -ForegroundColor Red }
        throw "El PowerShell incrustado tiene $($erroresDeAnalisis.Count) error(es) de sintaxis."
    }
    Write-Host ("  {0}  ({1} KB, un solo archivo)" -f $d, [math]::Round((Get-Item $d).Length / 1KB, 1))
}
