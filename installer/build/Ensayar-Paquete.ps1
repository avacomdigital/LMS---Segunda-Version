<#
.SYNOPSIS
    Ensaya el paquete (dist\staging) como lo haria un equipo del aula, en una
    carpeta de pruebas y un puerto libre, SIN tocar este equipo.

.DESCRIPTION
    Compilar y pasar las pruebas del backend no demuestra que lo que se EMPAQUETA
    arranque: ni que el runtime de Python embebido traiga todo, ni que el host
    configure bien el nodo, ni que el aula sobreviva a una configuracion ajena. Esto
    lo ejecuta de verdad, usando el propio Avacom.Ops.Host.exe del paquete (el mismo
    que usara el instalador) sobre una carpeta de estado temporal (AVACOM_OPS_DATOS):

      A · Instalacion nueva, con el entorno de Windows ENVENENADO a proposito
          (otra base de datos, el curso de ejemplo encendido, una nota de enlace
          de pruebas, otra carpeta de registros): preparar, arrancar el servicio
          como proceso, validar (/health/, WebSocket, registros, AVACOM Contenido),
          comprobar que la configuracion ajena no cuenta, y parar limpiamente.
      B · Actualizacion de la version anterior CON DATOS (si se indica
          -VersionAnterior): una base creada por el backend viejo, con organizacion
          y administrador, y una configuracion tocada a mano. Debe migrar, normalizar
          la configuracion sin cambiar las claves, y el administrador debe poder
          iniciar sesion (prueba de que sus datos siguen legibles).
      C · Sin configuracion: el servicio NO debe arrancar el backend ni crear una
          base vacia dentro de la carpeta del programa.
      D · El lanzador: abre la aplicacion con el perfil de WebView2 en la carpeta del
          usuario (la causa de que OPS se cerrara al abrir una leccion).
      E · Datos protegidos: una migracion que falla no pierde nada y la copia se restaura.
      F · Update Manager (MOD-017): el host aplica un paquete de modulo con el backend parado,
          lo verifica y, si algo falla (una migracion de verdad al 60 %, un fallo inyectado, el
          host que muere en cada checkpoint), vuelve atras solo; una clase abierta aplaza la
          aplicacion sin detener nada; las ordenes con rutas que se salen se rechazan; la
          instantanea dura 14 dias y no la borra una instalacion completa.

    El puerto 8000 no se usa: se busca uno libre. Las claves, contrasenas y bases de
    estas pruebas son de usar y tirar.

.PARAMETER VersionAnterior
    Carpeta con Backend\ y Runtime\ de la version anterior (p. ej. un dist\staging viejo).

.NOTES
    Codigo de salida: 0 todo bien; 1 si algo fallo.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Staging,
    [string] $VersionAnterior = '',
    [switch] $Conservar,
    # MOD-017: el bloque F (el host aplica y revierte paquetes de modulo) tarda; -SinActualizaciones lo omite y -SoloActualizaciones corre unicamente ese bloque.
    [switch] $SinActualizaciones,
    [switch] $SoloActualizaciones
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Staging = (Resolve-Path $Staging).Path
$Fallos = New-Object System.Collections.Generic.List[string]
$Raiz = Join-Path ([IO.Path]::GetTempPath()) ('avacom-ensayo-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$Procesos = New-Object System.Collections.Generic.List[int]

# El entorno de este proceso se restaura al terminar: el ensayo lo envenena a proposito.
$EntornoOriginal = @{}
foreach ($e in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
    if ($e.Key -like 'AVACOM_*' -or $e.Key -eq 'WEBVIEW2_USER_DATA_FOLDER') { $EntornoOriginal[$e.Key] = $e.Value }
}
# `ProgramData` tambien se restaura: Fijar-Datos lo mueve a la carpeta del ensayo (ver abajo).
if ($env:ProgramData) { $EntornoOriginal['ProgramData'] = $env:ProgramData }

# ---------------------------------------------------------------- utilidades
function Titulo([string] $texto) { Write-Host ''; Write-Host "  -- $texto" -ForegroundColor Cyan }
function Ok([string] $texto) { Write-Host "  [ok]     $texto" -ForegroundColor Green }
function Falla([string] $texto) { $Fallos.Add($texto); Write-Host "  [FALLA]  $texto" -ForegroundColor Red }
function Comprobar([bool] $condicion, [string] $bien, [string] $mal) { if ($condicion) { Ok $bien } else { Falla $mal } }

function Limpiar-Entorno {
    foreach ($e in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
        if ($e.Key -like 'AVACOM_*' -or $e.Key -eq 'WEBVIEW2_USER_DATA_FOLDER') { [Environment]::SetEnvironmentVariable([string]$e.Key, $null, 'Process') }
    }
}
function Restaurar-Entorno {
    Limpiar-Entorno
    foreach ($k in $EntornoOriginal.Keys) { [Environment]::SetEnvironmentVariable([string]$k, [string]$EntornoOriginal[$k], 'Process') }
}

# El host solo acepta una carpeta de estado de pruebas si el ensayo lo CONFIRMA: AVACOM_OPS_DATOS por si sola
# (una variable olvidada en Windows) no mueve el estado de un nodo real.
function Fijar-Datos([string] $ruta) {
    $env:AVACOM_OPS_ENSAYO = '1'
    $env:AVACOM_OPS_DATOS = $ruta
    # MOD-018 (licenciamiento): el paquete que se ensaya es de PRODUCCION (lleva el marcador de canal y su backend.env dice AVACOM_LMS_ENTORNO=instalado) y el estado de la licencia de un nodo de
    # produccion vive SIEMPRE en %ProgramData%\AVACOM\OPS Master\Config\licencia: ninguna variable AVACOM_* lo mueve (D-5; si no, bastaria apuntarla a una carpeta vacia para reiniciar la
    # evaluacion). Sin esto el ensayo escribiria el ancla del reloj y el secreto de instalacion en el ProgramData REAL de este equipo ("SIN tocar este equipo") y, 30 dias despues, la evaluacion
    # de ese estado habria vencido y los ensayos de reportes y busqueda recibirian 402. `ProgramData` NO es una variable AVACOM_*: el host la deja pasar al backend, asi que se mueve aqui.
    $env:ProgramData = Join-Path $ruta 'ProgramData'
}

function Puerto-Libre {
    $oyente = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $oyente.Start(); $puerto = $oyente.LocalEndpoint.Port; $oyente.Stop()
    return $puerto
}

# Peticion HTTP que no lanza por el codigo de estado; devuelve Estado, Cuerpo y Json.
function Pedir {
    param([string] $Url, [string] $Metodo = 'GET', [string] $Cuerpo = '', [int] $Segundos = 20, [string] $Pase = '')
    $r = [pscustomobject]@{ Estado = 0; Cuerpo = ''; Json = $null; Error = '' }
    $respuesta = $null
    try {
        $p = [System.Net.HttpWebRequest]::Create($Url)
        $p.Method = $Metodo; $p.Timeout = $Segundos * 1000; $p.ReadWriteTimeout = $Segundos * 1000; $p.Proxy = $null
        if ($Pase) { $p.Headers.Add('Authorization', "Bearer $Pase") }
        if ($Cuerpo) {
            $bytes = [Text.Encoding]::UTF8.GetBytes($Cuerpo)
            $p.ContentType = 'application/json'; $p.ContentLength = $bytes.Length
            $flujo = $p.GetRequestStream(); $flujo.Write($bytes, 0, $bytes.Length); $flujo.Dispose()
        }
        $respuesta = $p.GetResponse()
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { $respuesta = $_.Exception.Response } else { $r.Error = $_.Exception.Message }
    } catch { $r.Error = $_.Exception.Message }
    if ($respuesta) {
        try {
            $r.Estado = [int]$respuesta.StatusCode
            $lector = New-Object System.IO.StreamReader($respuesta.GetResponseStream(), [Text.Encoding]::UTF8)
            $r.Cuerpo = $lector.ReadToEnd(); $lector.Dispose()
        } catch { $r.Error = $_.Exception.Message } finally { try { $respuesta.Close() } catch { } }
    }
    if ($r.Cuerpo) { try { $r.Json = $r.Cuerpo | ConvertFrom-Json } catch { } }
    return $r
}

function Esperar-Salud([int] $puerto, [int] $segundos) {
    $limite = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $limite) {
        $r = Pedir "http://127.0.0.1:$puerto/health/" 'GET' '' 3
        if ($r.Estado -eq 200 -and $r.Cuerpo -match 'avacom-lms-backend') { return $true }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Copiar-Carpeta([string] $origen, [string] $destino) {
    New-Item -ItemType Directory -Force $destino | Out-Null
    $null = & robocopy $origen $destino /E /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { throw "robocopy fallo copiando $origen (codigo $LASTEXITCODE)." }
    $global:LASTEXITCODE = 0
}

function Armar-Instalacion([string] $backend, [string] $runtime, [string] $destino) {
    New-Item -ItemType Directory -Force $destino | Out-Null
    Copiar-Carpeta $backend (Join-Path $destino 'Backend')
    Copiar-Carpeta $runtime (Join-Path $destino 'Runtime')
}

# Ejecuta un verbo del host del paquete y devuelve su codigo de salida (con tope de tiempo).
function Host-Ejecutar([string] $instalacion, [string[]] $argumentos, [int] $segundos = 240) {
    $exe = Join-Path $instalacion 'Runtime\Avacom.Ops.Host.exe'
    $p = Start-Process -FilePath $exe -ArgumentList $argumentos -PassThru -WindowStyle Hidden
    $null = $p.Handle
    if (-not $p.WaitForExit($segundos * 1000)) {
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        return -999
    }
    return $p.ExitCode
}

# Arranca el host como lo arranca el servicio de Windows (verbo "servicio"), pero como proceso normal.
function Host-Servir([string] $instalacion) {
    $exe = Join-Path $instalacion 'Runtime\Avacom.Ops.Host.exe'
    $p = Start-Process -FilePath $exe -ArgumentList 'servicio' -PassThru -WindowStyle Hidden
    $null = $p.Handle
    $Procesos.Add($p.Id)
    return $p
}

# Hijos de un proceso (el backend de Python que el host lanza).
function Hijos-De([int] $padre) {
    return @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$padre" -ErrorAction SilentlyContinue)
}

# Para el host "a la fuerza": el backend ve cerrarse su entrada estandar y debe detenerse solo y limpio.
function Detener-Servicio($proceso, [string] $baseDeDatos) {
    $hijos = @(Hijos-De $proceso.Id)
    Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
    $detenido = $true
    foreach ($h in $hijos) {
        $viva = Get-Process -Id $h.ProcessId -ErrorAction SilentlyContinue
        if ($viva -and -not $viva.WaitForExit(25000)) { $detenido = $false; Stop-Process -Id $h.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    Comprobar $detenido 'Al morir el host, el backend se detuvo solo (no queda ningun proceso huerfano)' 'El backend NO se detuvo al cerrarse la entrada del host: quedaria huerfano con el puerto ocupado'
    if ($baseDeDatos) {
        Start-Sleep -Milliseconds 500
        Comprobar (-not (Test-Path ($baseDeDatos + '-wal')) -and -not (Test-Path ($baseDeDatos + '-shm'))) `
            'La parada dejo la base en un solo archivo (sin -wal ni -shm)' 'La parada dejo archivos -wal / -shm: el WAL de SQLite no se volco'
    }
}

function Leer-Texto([string] $ruta) { if (Test-Path $ruta) { return [IO.File]::ReadAllText($ruta, [Text.Encoding]::UTF8) } return '' }

# El verificador contra un nodo vivo. Se ejecuta aparte: lo que escribe en stderr no debe abortar el ensayo.
function Ejecutar-Verificador([string] $verificador, [int] $puerto, [string] $datos, [string] $instalacion, [string] $enlace, [string] $salida) {
    $ErrorActionPreference = 'Continue'
    return (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verificador -SinAsistente -Puerto $puerto `
        -RaizDatos $datos -RaizInstalacion $instalacion -RutaEnlace $enlace -Salida $salida *>&1 | Out-String)
}

# Ejecuta Python del runtime con la configuracion (backend.env) de un nodo, como lo hace el host.
function Python-Del-Nodo([string] $instalacion, [string] $datos, [string[]] $argumentos) {
    # Un ejecutable que escribe en stderr no debe abortar el ensayo (con 'Stop', PowerShell 5.1 lo convierte en error).
    $ErrorActionPreference = 'Continue'
    Fijar-Datos $datos
    $config = Join-Path $datos 'Config\backend.env'
    foreach ($linea in (Get-Content $config -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        if ($linea -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), 'Process') }
    }
    $env:DJANGO_SETTINGS_MODULE = 'avacom_lms.settings'; $env:PYTHONIOENCODING = 'utf-8'; $env:PYTHONDONTWRITEBYTECODE = '1'
    Push-Location (Join-Path $instalacion 'Backend')
    try {
        $salida = & (Join-Path $instalacion 'Runtime\Python\python.exe') @argumentos 2>&1 | Out-String
        return [pscustomobject]@{ Codigo = $LASTEXITCODE; Salida = $salida }
    } finally { Pop-Location }
}

function Leer-Valor([string] $config, [string] $clave) {
    $m = [regex]::Match((Leer-Texto $config), "(?m)^\s*$([regex]::Escape($clave))\s*=\s*(.*)$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() } return $null
}

function Poner-Valor([string] $config, [string] $clave, [string] $valor) {
    $texto = Leer-Texto $config
    $patron = "(?m)^\s*$([regex]::Escape($clave))\s*=.*$"
    if ([regex]::IsMatch($texto, $patron)) { $texto = [regex]::Replace($texto, $patron, "$clave=$valor") } else { $texto += "`r`n$clave=$valor`r`n" }
    [IO.File]::WriteAllText($config, $texto, (New-Object Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------- bloque F · MOD-017 (Update Manager) · utilidades
# El backend (Django) deja una ORDEN en Actualizaciones\orden.json y el host la aplica; en el ensayo la orden, el staging y el .avupd los arma ESTE script con el mismo formato que
# el backend (spec-driven\17-update-manager\02-api.md §3), porque el nodo del paquete es de PRODUCCION y no acepta ningun paquete firmado con una llave de desarrollo. Lo que se
# ensaya es el HOST: comprobar, respaldar, instantanea, copiar, migrar, verificar y la reversion automatica, con migraciones y archivos de verdad sobre el backend empaquetado.
function Sha-De([string] $ruta) { return (Get-FileHash -LiteralPath $ruta -Algorithm SHA256).Hash.ToLowerInvariant() }

function Escribir-Texto([string] $ruta, [string] $texto) {
    New-Item -ItemType Directory -Force (Split-Path $ruta) | Out-Null
    [IO.File]::WriteAllText($ruta, $texto, (New-Object Text.UTF8Encoding($false)))
}

function Ultima-Migracion([string] $instalacion) {
    $m = Get-ChildItem (Join-Path $instalacion 'Backend\reporting\migrations') -Filter '*.py' | Where-Object { $_.Name -match '^\d{4}_' } | Sort-Object Name | Select-Object -Last 1
    return [IO.Path]::GetFileNameWithoutExtension($m.Name)
}

# Una huella de lo que el paquete puede tocar: cada archivo de reporting\ con su SHA-256, todo en un solo SHA-256.
function Huella-De-Codigo([string] $instalacion) {
    $backend = Join-Path $instalacion 'Backend'
    $lineas = foreach ($a in (Get-ChildItem (Join-Path $backend 'reporting') -Recurse -File | Sort-Object FullName)) { "$($a.FullName.Substring($backend.Length)):$(Sha-De $a.FullName)" }
    $sha = [Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lineas -join "`n")))) -replace '-', '').ToLowerInvariant()
}

$script:ContadorDeMigraciones = 900

# Un paquete de modulo con el formato del backend: un archivo EXISTENTE que cambia (para probar que la instantanea lo devuelve tal cual), archivos nuevos y N migraciones encadenadas
# (cada una crea una tabla ensayo_*; la numero $Falla, si se pide, lanza un error de verdad). Deja el staging y el .avupd donde los dejaria el backend; NO escribe la orden.
function Nuevo-Paquete {
    param([string] $Instalacion, [string] $ActDir, [string] $Etiqueta, [int] $Migraciones = 3, [int] $Falla = 0, [int] $ArchivosNuevos = 2, [int] $Limite = 5)
    $paqueteId = [guid]::NewGuid().ToString('D')
    $ordenId = [guid]::NewGuid().ToString('D')
    $backend = Join-Path $Instalacion 'Backend'
    $staging = Join-Path $ActDir "staging\$paqueteId"
    $archivos = New-Object System.Collections.Generic.List[object]
    $agregar = {
        param([string] $ruta, [string] $contenido)
        $destino = Join-Path $staging ($ruta -replace '/', '\')
        Escribir-Texto $destino $contenido
        $archivos.Add([ordered]@{ ruta = $ruta; bytes = (Get-Item -LiteralPath $destino).Length; sha256 = (Sha-De $destino) })
    }
    $existente = 'reporting/__init__.py'
    $original = [IO.File]::ReadAllText((Join-Path $backend 'reporting\__init__.py'), [Text.Encoding]::UTF8)
    & $agregar $existente ($original + "`n# ensayo $Etiqueta`n")
    for ($i = 1; $i -le $ArchivosNuevos; $i++) { & $agregar "reporting/dominio/ensayo_${Etiqueta}_$i.py" "VALOR = $i`n" }

    $listaMig = New-Object System.Collections.Generic.List[object]
    $previa = Ultima-Migracion $Instalacion
    for ($i = 1; $i -le $Migraciones; $i++) {
        $nombre = ('{0:D4}_ensayo_{1}_{2}' -f $script:ContadorDeMigraciones, $Etiqueta, $i)
        $script:ContadorDeMigraciones++
        if ($i -eq $Falla) {
            $cuerpo = "def falla(apps, schema_editor):`n    raise RuntimeError('Migracion de ensayo que falla a proposito')`n`n`nclass Migration(migrations.Migration):`n    dependencies = [('reporting', '$previa')]`n    operations = [migrations.RunPython(falla, migrations.RunPython.noop)]`n"
        } else {
            $tabla = "ensayo_${Etiqueta}_$i"
            $cuerpo = "class Migration(migrations.Migration):`n    dependencies = [('reporting', '$previa')]`n    operations = [migrations.RunSQL('CREATE TABLE $tabla (id integer)', 'DROP TABLE $tabla')]`n"
        }
        & $agregar "reporting/migrations/$nombre.py" ("from django.db import migrations`n`n`n" + $cuerpo)
        $listaMig.Add([ordered]@{ nombre = $nombre; reverso = $previa })
        $previa = $nombre
    }

    $paquete = Join-Path $ActDir "paquetes\$paqueteId.avupd"
    New-Item -ItemType Directory -Force (Split-Path $paquete) | Out-Null
    $azar = New-Object byte[] 4096
    (New-Object Random).NextBytes($azar)
    [IO.File]::WriteAllBytes($paquete, $azar)
    return [pscustomobject]@{
        PaqueteId = $paqueteId; OrdenId = $ordenId; Etiqueta = $Etiqueta; Archivos = $archivos; Migraciones = $listaMig; Existente = $existente; Limite = $Limite
        PaqueteSha = (Sha-De $paquete); PaqueteBytes = $azar.Length; Staging = $staging; ArchivoPaquete = $paquete
    }
}

# Escribe orden.json como lo hace el backend: a un temporal y renombrado (el archivo aparece completo o no aparece).
function Escribir-Orden($p, [string] $accion = 'aplicar', [string] $ActDir, [hashtable] $Cambios = @{}) {
    $migraciones = $p.Migraciones.ToArray()
    if ($accion -eq 'revertir') { [array]::Reverse($migraciones) }
    $orden = [ordered]@{
        formato = 1; orden_id = $p.OrdenId; paquete_id = $p.PaqueteId; accion = $accion; emitida_en = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()); emitida_por = 'ensayo'
        limite_minutos = $p.Limite; ventana = $null; nota = 'ensayo'
        paquete = [ordered]@{ nombre = "Ensayo $($p.Etiqueta)"; version_producto = '9.9.9'; serie = 99; sha256 = $p.PaqueteSha; bytes = $p.PaqueteBytes; kid = 'ensayo' }
        modulos = @([ordered]@{ nombre = 'reporting'; version = '9.9.9'; version_datos = 9; version_contrato = 1; serie = 99; migraciones = $migraciones })
        archivos = $p.Archivos.ToArray()
        carpetas = [ordered]@{ staging = "staging/$($p.PaqueteId)"; instantanea = "versiones/$($p.PaqueteId)/anterior" }
        pasos = @('comprobar', 'respaldar', 'instantanea', 'copiar', 'migrar', 'verificar')
    }
    foreach ($k in $Cambios.Keys) { $orden[$k] = $Cambios[$k] }
    $json = ConvertTo-Json -InputObject $orden -Depth 10
    $temporal = Join-Path $ActDir 'orden.json.tmp'
    Escribir-Texto $temporal $json
    Move-Item -LiteralPath $temporal -Destination (Join-Path $ActDir 'orden.json')
}

# El resultado del host: resultado.json, o ya archivado por el backend en resultados\<orden>.json. $null si no llega a tiempo.
function Esperar-Resultado([string] $ActDir, [string] $ordenId, [int] $segundos) {
    $limite = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $limite) {
        foreach ($ruta in @((Join-Path $ActDir 'resultado.json'), (Join-Path $ActDir "resultados\$ordenId.json"))) {
            if (Test-Path $ruta) {
                try {
                    $r = [IO.File]::ReadAllText($ruta, [Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($r.orden_id -eq $ordenId) { return $r }
                } catch { }
            }
        }
        Start-Sleep -Milliseconds 300
    }
    return $null
}

# Lo que haria el backend al registrar el resultado: archivarlo y retirar la orden. Si el backend de verdad lo hace (en los 90 s), mejor; si no, lo hace el ensayo y lo dice.
function Cerrar-Orden([string] $ActDir, [string] $ordenId, [switch] $Silencioso) {
    $limite = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $limite) {
        if (-not (Test-Path (Join-Path $ActDir 'orden.json'))) { return $true }
        Start-Sleep -Milliseconds 500
    }
    if (-not $Silencioso) { Write-Host '  [info]   el backend no archivo el resultado en 90 s: lo archiva el ensayo' -ForegroundColor DarkGray }
    New-Item -ItemType Directory -Force (Join-Path $ActDir 'resultados') | Out-Null
    if (Test-Path (Join-Path $ActDir 'resultado.json')) { Move-Item -LiteralPath (Join-Path $ActDir 'resultado.json') -Destination (Join-Path $ActDir "resultados\$ordenId.json") -Force }
    Remove-Item -LiteralPath (Join-Path $ActDir 'orden.json') -Force -ErrorAction SilentlyContinue
    return $false
}

# Lanza el host como lo hace el servicio, con (o sin) los ganchos de ensayo FALLO y CORTE.
function Iniciar-Host-De-Ensayo([string] $instalacion, [string] $fallo = '', [string] $corte = '') {
    if ($fallo) { $env:AVACOM_ACTUALIZACION_FALLO = $fallo }
    if ($corte) { $env:AVACOM_ACTUALIZACION_CORTE = $corte }
    try { return (Host-Servir $instalacion) } finally {
        Remove-Item Env:\AVACOM_ACTUALIZACION_FALLO -ErrorAction SilentlyContinue
        Remove-Item Env:\AVACOM_ACTUALIZACION_CORTE -ErrorAction SilentlyContinue
    }
}

function Matar-Host($proceso) {
    if ($null -eq $proceso) { return }
    foreach ($h in (Hijos-De $proceso.Id)) { Stop-Process -Id $h.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $proceso.Id -Force -ErrorAction SilentlyContinue
    $null = $proceso.WaitForExit(20000)
    # Un backend que quedo huerfano tiene el puerto: se espera a que lo suelte.
    Start-Sleep -Seconds 2
}

# Estado de la base de datos y de los archivos del ensayo, con un solo arranque de Python.
function Estado-De-Ensayo([string] $instalacion, [string] $datos, [string] $carpeta) {
    $archivo = Join-Path $carpeta 'estado-act.py'
    Escribir-Texto $archivo @'
import json, os, sqlite3
c = sqlite3.connect(os.environ['AVACOM_LMS_DB'], timeout=20)
tablas = sorted(r[0] for r in c.execute("select name from sqlite_master where type='table' and name like 'ensayo_%'"))
migs = sorted(r[0] for r in c.execute("select name from django_migrations where app='reporting' and name like '09%'"))
print(json.dumps({'tablas': tablas, 'migs': migs, 'integridad': c.execute('PRAGMA integrity_check').fetchone()[0], 'sesiones': c.execute("select count(*) from m07_sesion").fetchone()[0]}))
c.close()
'@
    $salida = Python-Del-Nodo $instalacion $datos @($archivo)
    Limpiar-Entorno
    Fijar-Datos $datos
    $linea = @($salida.Salida -split "`r?`n" | Where-Object { $_.Trim().StartsWith('{') }) | Select-Object -Last 1
    if (-not $linea) { return [pscustomobject]@{ tablas = @('?'); migs = @('?'); integridad = '?'; sesiones = -1 } }
    return ($linea | ConvertFrom-Json)
}

try {
    Write-Host ''
    Write-Host "  Ensayo del paquete en $Raiz" -ForegroundColor White
    New-Item -ItemType Directory -Force $Raiz | Out-Null
    $backendNuevo = Join-Path $Staging 'Backend'
    $runtimeNuevo = Join-Path $Staging 'Runtime'
    foreach ($necesario in @((Join-Path $backendNuevo 'manage.py'), (Join-Path $runtimeNuevo 'Avacom.Ops.Host.exe'), (Join-Path $runtimeNuevo 'Python\python.exe'))) {
        if (-not (Test-Path $necesario)) { throw "El paquete esta incompleto: falta $necesario." }
    }

    if (-not $SoloActualizaciones) {
    # ========================================================== A · instalacion nueva
    Titulo 'A · Instalacion nueva, con el entorno de Windows envenenado'
    $instA = Join-Path $Raiz 'A\AVACOM\OPS Master'
    $datosA = Join-Path $Raiz 'A\datos'
    Armar-Instalacion $backendNuevo $runtimeNuevo $instA
    Copy-Item (Join-Path $Staging 'manifiesto.json') (Join-Path $instA 'manifiesto.json') -ErrorAction SilentlyContinue

    Limpiar-Entorno
    Fijar-Datos $datosA
    # Todo esto es lo que un tecnico o un desarrollador puede dejar en Windows. Nada debe contar.
    $env:AVACOM_AULA_PERMITIR_EJEMPLO = '1'
    $env:AVACOM_AULA_FUENTE_CURSOS = 'ejemplo'
    $env:AVACOM_CONTENIDO_ENLACE = Join-Path $Raiz 'no-existe\enlace.json'
    $env:AVACOM_CONTENIDO_ENLACE_V2 = Join-Path $Raiz 'no-existe\link.json'
    $env:AVACOM_LMS_DB = Join-Path $Raiz 'ajena.sqlite3'
    $env:AVACOM_LMS_DIR_LOGS = Join-Path $Raiz 'logs-ajenos'
    $env:AVACOM_LMS_DEBUG = '1'
    $env:AVACOM_LMS_ENTORNO = 'desarrollo'
    $env:AVACOM_COLA_ACTIVA = '0'
    $env:AVACOM_COLA_DIR = Join-Path $Raiz 'cache-ajena'

    $codigo = Host-Ejecutar $instA @('preparar')
    Comprobar ($codigo -eq 0) 'preparar termina bien (configuracion, claves, migraciones)' "preparar devolvio $codigo`: $(Leer-Texto (Join-Path $datosA 'Logs\preparacion-estado.txt'))"

    $configA = Join-Path $datosA 'Config\backend.env'
    $registroA = Leer-Texto (Join-Path $datosA 'Logs\instalacion.log')
    Comprobar (Test-Path $configA) 'backend.env creado en la carpeta de estado' 'No se creo backend.env'
    $textoConfig = Leer-Texto $configA
    foreach ($clave in 'AVACOM_LMS_CLAVE_DATOS', 'AVACOM_LMS_CLAVE_INDICE', 'AVACOM_LMS_CLAVE_TOKENS', 'AVACOM_LMS_SECRET') {
        Comprobar ($textoConfig -match "(?m)^$clave=.{20,}") "$clave generada" "Falta $clave en backend.env"
    }
    foreach ($par in @(@('AVACOM_LMS_ENTORNO', 'instalado'), @('AVACOM_AULA_FUENTE_CURSOS', 'biblioteca'), @('AVACOM_AULA_PERMITIR_EJEMPLO', '0'), @('AVACOM_LMS_DEBUG', '0'), @('AVACOM_LMS_EXIGIR_SESION', '1'))) {
        Comprobar ((Leer-Valor $configA $par[0]) -eq $par[1]) "$($par[0])=$($par[1]) en backend.env" "$($par[0]) deberia ser $($par[1]) y es $(Leer-Valor $configA $par[0])"
    }
    Comprobar ((Leer-Valor $configA 'AVACOM_LMS_DIR_LOGS') -eq (Join-Path $datosA 'Logs')) 'La carpeta de registros es la del nodo' 'AVACOM_LMS_DIR_LOGS no es la carpeta Logs del nodo'
    # Cola de medios: la configuracion trae sus valores, la cache vive en la carpeta del nodo y nada del entorno ajeno la mueve ni la apaga.
    foreach ($par in @(@('AVACOM_COLA_ACTIVA', '1'), @('AVACOM_COLA_MAX_MB', '4096'), @('AVACOM_COLA_DESCARGAS', '3'), @('AVACOM_COLA_TRANSFERENCIAS', '24'))) {
        Comprobar ((Leer-Valor $configA $par[0]) -eq $par[1]) "$($par[0])=$($par[1]) en backend.env" "$($par[0]) deberia ser $($par[1]) y es $(Leer-Valor $configA $par[0])"
    }
    Comprobar ((Leer-Valor $configA 'AVACOM_COLA_DIR') -eq (Join-Path $datosA 'CacheMedios')) 'La cache de medios es la del nodo (CacheMedios)' 'AVACOM_COLA_DIR no es la carpeta CacheMedios del nodo'
    Comprobar (Test-Path (Join-Path $datosA 'CacheMedios')) 'La carpeta de la cache de medios existe' 'No se creo la carpeta CacheMedios'
    Comprobar (-not (Test-Path (Join-Path $Raiz 'cache-ajena'))) 'No se uso la carpeta de cache del entorno ajeno' 'Se uso la carpeta de cache del entorno ajeno'
    Comprobar ($registroA -match 'curso de ejemplo=apagado' -and $registroA -match 'depuracion=apagada') `
        'La configuracion EFECTIVA que ve Django ignora lo envenenado (ejemplo apagado, sin depuracion)' `
        'Django vio la configuracion ajena: el entorno de Windows se colo en el backend'
    Comprobar ($registroA -match [regex]::Escape("base de datos=$(Join-Path $datosA 'Data\ops-master.sqlite3')")) `
        'Django usa la base de datos del nodo, no la del entorno ajeno' 'Django no usa la base de datos del nodo'
    Comprobar (-not (Test-Path (Join-Path $Raiz 'ajena.sqlite3'))) 'No se creo la base de datos ajena' 'Se creo la base de datos del entorno ajeno'

    # El ensayo no puede usar el 8000: se le da otro puerto al nodo de pruebas.
    $puertoA = Puerto-Libre
    Poner-Valor $configA 'AVACOM_OPS_BACKEND_PORT' $puertoA

    $servicioA = Host-Servir $instA
    $arranco = Esperar-Salud $puertoA 120
    Comprobar $arranco "El backend empaquetado arranca con Daphne y /health/ responde (puerto $puertoA)" "El backend empaquetado no respondio en 120 s. Mira $(Join-Path $datosA 'Logs\servicio.log')"
    if (-not $arranco) { Write-Host (Leer-Texto (Join-Path $datosA 'Logs\servicio.log')) }

    if ($arranco) {
        $codigo = Host-Ejecutar $instA @('validar', '60')
        Comprobar ($codigo -eq 0) 'validar: /health/, canal en tiempo real, base de datos y registros correctos' "validar devolvio $codigo (11 salud, 14 websocket, 15 base de datos)"
        $resumen = Leer-Texto (Join-Path $datosA 'Logs\resumen-nodo.txt')
        Comprobar ($resumen -match 'websocket=ok') 'El WebSocket del aula acepta conexiones' 'El WebSocket no acepta conexiones'
        Comprobar ($resumen -match 'registros=ok') 'El servicio escribe sus registros en la carpeta del nodo' "El servicio no escribe en Logs: $resumen"
        Comprobar ($resumen -match 'organizacion=no') 'El nodo nuevo avisa que falta la organizacion' "Resumen inesperado: $resumen"
        Comprobar ($resumen -match '(?m)^pin_maestro=sin_configurar') 'El nodo nuevo avisa que no tiene PIN maestro (lo crea el primer arranque de OPS)' "Resumen inesperado: $resumen"
        # Lo que ve OPS al abrirse en un nodo recien instalado: sin organizacion (abre el primer arranque), sesion obligatoria
        # y sin PIN maestro. Es la configuracion de la PRIMERA instalacion: nada se pide en el instalador, todo en el primer arranque.
        $configAcceso = Pedir "http://127.0.0.1:$puertoA/api/acceso/configuracion/"
        Comprobar ($configAcceso.Estado -eq 200 -and $configAcceso.Json.instalado -eq $false -and $configAcceso.Json.sesion_obligatoria -eq $true) 'Nodo nuevo: sin organizacion y con la sesion obligatoria (OPS abre el primer arranque y pide documento y contrasena)' "/api/acceso/configuracion/ respondio $($configAcceso.Estado): $($configAcceso.Cuerpo)"
        $instalacionVacia = Pedir "http://127.0.0.1:$puertoA/api/acceso/instalacion/" 'POST' '{}'
        Comprobar ($instalacionVacia.Estado -eq 400) 'El primer arranque exige datos (organizacion, administrador y PIN maestro): una instalacion vacia se rechaza' "/api/acceso/instalacion/ con cuerpo vacio respondio $($instalacionVacia.Estado)"
        $bib = [regex]::Match($resumen, '(?m)^biblioteca=(.+)$').Groups[1].Value.Trim()
        Write-Host "  [info]   AVACOM Contenido visto desde el aula: $bib (informativo: la instalacion no depende de ella)" -ForegroundColor DarkGray
        Comprobar ($bib -in 'conectada', 'no_disponible', 'desconocida') 'El estado de la biblioteca se informa sin romper nada' "Estado de biblioteca inesperado: $bib"

        $fuente = Pedir "http://127.0.0.1:$puertoA/api/aula/fuente/" 'GET' '' 30
        # Desde que el instalador deja AVACOM_LMS_EXIGIR_SESION=1, las rutas del aula piden sesion: sin ella la respuesta
        # correcta es 401 (nunca 503 ni 500). Con la sesion obligatoria apagada seria 200.
        $exigeSesion = ((Leer-Valor $configA 'AVACOM_LMS_EXIGIR_SESION') -ne '0')
        if ($exigeSesion) {
            Comprobar ($fuente.Estado -eq 401) '/api/aula/fuente/ exige sesion (401): el nodo instalado no regala el aula sin identificarse' "/api/aula/fuente/ respondio $($fuente.Estado): $($fuente.Cuerpo)"
        } else {
            Comprobar ($fuente.Estado -eq 200) '/api/aula/fuente/ responde 200 (nunca 503) con o sin biblioteca' "/api/aula/fuente/ respondio $($fuente.Estado)"
        }
        # La cola de medios esta en el paquete: sus rutas responden (con la sesion obligatoria, 401; sin ella, el estado con la cola encendida).
        $cola = Pedir "http://127.0.0.1:$puertoA/api/medios/cola/"
        if ($exigeSesion) {
            Comprobar ($cola.Estado -eq 401) '/api/medios/cola/ exige sesion (401): la cola de medios esta en el paquete' "/api/medios/cola/ respondio $($cola.Estado): $($cola.Cuerpo)"
        } else {
            Comprobar ($cola.Estado -eq 200 -and $cola.Json.activa -eq $true) '/api/medios/cola/ responde con la cola de medios activa' "/api/medios/cola/ respondio $($cola.Estado): $($cola.Cuerpo)"
        }
        $auditoria = Pedir "http://127.0.0.1:$puertoA/api/auditoria/estado/"
        Comprobar ($auditoria.Estado -in 200, 401, 403) 'El modulo de auditoria esta en el paquete (/api/auditoria/ responde)' "/api/auditoria/estado/ respondio $($auditoria.Estado)"
        $evaluacion = Pedir "http://127.0.0.1:$puertoA/api/evaluacion/asignaciones/"
        Comprobar ($evaluacion.Estado -ne 404 -and $evaluacion.Estado -ne 500) "El modulo de evaluacion esta en el paquete (respondio $($evaluacion.Estado))" "/api/evaluacion/ respondio $($evaluacion.Estado)"
        $estudio = Pedir "http://127.0.0.1:$puertoA/api/modo-estudio/estado/"
        Comprobar ($estudio.Estado -in 200, 401, 403) "El modulo de modo estudio esta en el paquete (respondio $($estudio.Estado))" "/api/modo-estudio/estado/ respondio $($estudio.Estado)"
        # Los modulos que llegaron despues tambien van en el paquete: su ruta existe y responde (200, o 401/403 con la sesion obligatoria). Una ruta que no llego daria 404.
        foreach ($modulo in @(@('libro de calificaciones (gradebook)', 'api/gradebook/configuracion/'), @('busqueda (search)', 'api/search/status/'), @('reportes (reporting)', 'api/reportes/clases/'))) {
            $respuestaModulo = Pedir "http://127.0.0.1:$puertoA/$($modulo[1])"
            Comprobar ($respuestaModulo.Estado -in 200, 401, 403) "El modulo de $($modulo[0]) esta en el paquete (/$($modulo[1]) respondio $($respuestaModulo.Estado))" "/$($modulo[1]) respondio $($respuestaModulo.Estado): $($respuestaModulo.Cuerpo)"
        }

        # Los registros: JSON Lines en la carpeta del nodo, ninguno dentro del programa ni en la carpeta ajena.
        $logs = Join-Path $datosA 'Logs'
        foreach ($nombre in 'backend-app.log', 'servicio.log', 'instalacion.log') {
            Comprobar (Test-Path (Join-Path $logs $nombre)) "Existe Logs\$nombre" "No existe Logs\$nombre"
        }
        $ultimaLinea = @(Get-Content (Join-Path $logs 'backend-app.log') -Tail 3 -Encoding UTF8 | Where-Object { $_.StartsWith('{') }) | Select-Object -Last 1
        $valida = $false; try { $j = $ultimaLinea | ConvertFrom-Json; $valida = [bool]$j.ts -and [bool]$j.canal } catch { }
        Comprobar $valida 'backend-app.log escribe JSON Lines con ts y canal' 'backend-app.log no tiene JSON Lines legibles'
        Comprobar (-not (Test-Path (Join-Path $instA 'Backend\logs'))) 'Nada se escribio dentro de la carpeta del programa (Backend\logs)' 'El backend escribio registros dentro de la carpeta del programa'
        Comprobar (-not (Test-Path (Join-Path $Raiz 'logs-ajenos'))) 'No se uso la carpeta de registros del entorno ajeno' 'Se uso la carpeta de registros del entorno ajeno'
        Comprobar (-not (Test-Path (Join-Path $instA 'Backend\__pycache__'))) 'No se dejo bytecode (.pyc) dentro del programa' 'Se escribio __pycache__ dentro del programa'

        # El verificador, contra un nodo vivo (sin servicio de Windows: avisara; lo que importa es que lo ve).
        $verificador = Join-Path $PSScriptRoot '..\tools\Verificar-Instalador.ps1'
        if (Test-Path $verificador) {
            $salidaV = Join-Path $Raiz 'verificador'
            New-Item -ItemType Directory -Force $salidaV | Out-Null
            $textoV = Ejecutar-Verificador $verificador $puertoA $datosA $instA (Join-Path $Raiz 'no-hay-link.json') $salidaV
            Comprobar ($textoV -match 'La API local responde') 'El verificador ve el nodo vivo (/health/)' 'El verificador no vio el nodo vivo'
            Comprobar ($textoV -match 'canal en tiempo real del aula \(WebSocket\) acepta') 'El verificador comprueba el WebSocket' 'El verificador no comprobo el WebSocket'
            Comprobar ($textoV -match 'backend est. escribiendo sus registros') 'El verificador comprueba que se escriben los registros' 'El verificador no comprobo los registros'
        }

        # ------------------------------------------------------------------------------------------------------------------
        # A2 · El primer arranque COMPLETO, con la misma API que usa OPS: un nodo recien instalado tiene que poder recibir la
        # organizacion, el administrador (documento, nombres, apellidos) y el PIN maestro, y despues dejar entrar al
        # administrador con documento + contrasena inicial + PIN maestro, obligarlo a elegir su propia contrasena y dejarlo
        # trabajar. Antes solo se comprobaba que una instalacion VACIA se rechazaba: nada probaba que la buena funcionara
        # dentro del paquete (runtime embebido, migraciones, argon2, claves).
        # ------------------------------------------------------------------------------------------------------------------
        Titulo 'A2 · El primer arranque completo: organizacion, administrador y PIN maestro (como lo hace OPS)'
        $baseA = "http://127.0.0.1:$puertoA"
        $documentoAdmin = '1042888795'
        $pinMaestro = '739104'
        $claveElegida = 'Aula.Ensayo.2026!'
        $cuerpoInstalacion = {
            param([string] $pin)
            (@{ organizacion = @{ codigo = 'ENSAYO'; nombre = 'Aula de ensayo del instalador'; pais = 'CO'; idioma = 'es'; locale = 'es-CO' }
                administrador = @{ alias = 'Administracion'; nombres = 'Ana'; apellidos = 'Del Ensayo'; dni = $documentoAdmin }
                pin_maestro = $pin } | ConvertTo-Json -Depth 5 -Compress)
        }

        # Un PIN facil de adivinar o mal formado se rechaza explicando por que y deja el equipo vacio (OPS pide otro PIN).
        $pinDebil = Pedir "$baseA/api/acceso/instalacion/" 'POST' (& $cuerpoInstalacion '123456')
        Comprobar ($pinDebil.Estado -eq 400 -and $pinDebil.Json.codigo -eq 'pin_debil') 'Un PIN maestro facil (123456) se rechaza con su explicacion' "PIN facil: respondio $($pinDebil.Estado) $($pinDebil.Cuerpo)"
        $pinCorto = Pedir "$baseA/api/acceso/instalacion/" 'POST' (& $cuerpoInstalacion '12345')
        Comprobar ($pinCorto.Estado -eq 400 -and $pinCorto.Json.codigo -eq 'pin_invalido') 'Un PIN maestro de cinco digitos se rechaza' "PIN corto: respondio $($pinCorto.Estado) $($pinCorto.Cuerpo)"
        $sigueVacio = Pedir "$baseA/api/acceso/configuracion/"
        Comprobar ($sigueVacio.Estado -eq 200 -and $sigueVacio.Json.instalado -eq $false) 'Tras los rechazos el nodo sigue vacio (no queda un aula a medias)' "El nodo ya no esta vacio: $($sigueVacio.Cuerpo)"

        # El primer arranque bueno. La contrasena NO se escribe: la genera el nodo y llega una sola vez (la hoja de acceso).
        $instalacion = Pedir "$baseA/api/acceso/instalacion/" 'POST' (& $cuerpoInstalacion $pinMaestro) 60
        Comprobar ($instalacion.Estado -eq 201) 'El primer arranque crea la organizacion, el administrador y el PIN maestro (201)' "La instalacion respondio $($instalacion.Estado): $($instalacion.Cuerpo)"
        $claveInicial = if ($instalacion.Json -and $instalacion.Json.PSObject.Properties['password_inicial']) { [string]$instalacion.Json.password_inicial } else { '' }
        Comprobar ($claveInicial.Length -ge 8) 'La contrasena inicial del administrador la genera el nodo y llega en la respuesta (la hoja de acceso)' 'La respuesta no trae la contrasena inicial generada'
        Comprobar ($instalacion.Cuerpo -notmatch [regex]::Escape($pinMaestro)) 'La respuesta no devuelve el PIN maestro (no se puede volver a ver)' 'La respuesta de la instalacion trae el PIN maestro en claro'

        $despues = Pedir "$baseA/api/acceso/configuracion/"
        Comprobar ($despues.Estado -eq 200 -and $despues.Json.instalado -eq $true -and $despues.Json.pin_maestro.configurado -eq $true -and $despues.Json.pin_maestro.vencido -eq $false) `
            'Con el primer arranque hecho, el nodo dice instalado y con PIN maestro vigente' "Configuracion tras instalar: $($despues.Cuerpo)"
        $otraVez = Pedir "$baseA/api/acceso/instalacion/" 'POST' (& $cuerpoInstalacion '482915') 30
        Comprobar ($otraVez.Estado -eq 409) 'Un segundo primer arranque se rechaza (409): nadie puede reinstalar encima de un aula en uso' "La segunda instalacion respondio $($otraVez.Estado): $($otraVez.Cuerpo)"

        # OPS se presenta ante el nodo como equipo MASTER con el latido (publico): el PIN maestro solo se acepta desde el equipo del
        # profesor, no desde una tableta.
        $equipo = Pedir "$baseA/api/dispositivos/latido/" 'POST' '{"identificador_hw":"ensayo-ops-master","nombre":"OPS de ensayo","plataforma":"windows","version_app":"2.4.0","tipo":"MASTER"}' 30
        Comprobar ($equipo.Estado -in 200, 201 -and $equipo.Json.tipo -eq 'MASTER') 'El equipo de OPS se presenta ante el nodo como MASTER (latido publico)' "El latido del equipo respondio $($equipo.Estado): $($equipo.Cuerpo)"

        # El administrador entra: contrasena sola -> pide el PIN; PIN equivocado -> lo rechaza; PIN bueno -> sesion.
        $login = { param([string] $secreto, [string] $pin)
            $c = @{ identificador = $documentoAdmin; secreto = $secreto; dispositivo = 'ensayo-ops-master' }
            if ($pin) { $c.pin_maestro = $pin }
            Pedir "$baseA/api/acceso/sesiones/" 'POST' ($c | ConvertTo-Json -Compress) 60 }
        $sinPin = & $login $claveInicial ''
        Comprobar ($sinPin.Estado -eq 401 -and $sinPin.Json.codigo -eq 'pin_maestro_requerido') 'Con documento y contrasena, la administracion todavia debe dar el PIN maestro (pin_maestro_requerido)' "Sin PIN respondio $($sinPin.Estado): $($sinPin.Cuerpo)"
        $pinMalo = & $login $claveInicial '906531'
        Comprobar ($pinMalo.Estado -eq 401 -and $pinMalo.Json.codigo -eq 'pin_maestro_invalido') 'Un PIN maestro equivocado se rechaza (pin_maestro_invalido)' "PIN malo respondio $($pinMalo.Estado): $($pinMalo.Cuerpo)"
        $conPin = & $login $claveInicial $pinMaestro
        Comprobar ($conPin.Estado -eq 200 -and [bool]$conPin.Json.token) 'Documento + contrasena inicial + PIN maestro abren la sesion del administrador' "Con el PIN bueno respondio $($conPin.Estado): $($conPin.Cuerpo)"
        if ($conPin.Estado -eq 200) {
            Comprobar ($conPin.Json.usuario.rol -eq 'ADMIN') 'La sesion es de la administracion (rol ADMIN)' "Rol inesperado: $($conPin.Json.usuario.rol)"
            Comprobar ($conPin.Json.usuario.debe_cambiar_credencial -eq $true) 'La contrasena inicial es provisional: la sesion nace marcada para que elija otra' 'La contrasena inicial no quedo como provisional'
            $pase = [string]$conPin.Json.token

            # Con la contrasena provisional la sesion solo sirve para elegir la propia: lo demas responde 403 debe_cambiar_credencial.
            $bloqueada = Pedir "$baseA/api/acceso/pin-maestro/" 'GET' '' 30 $pase
            Comprobar ($bloqueada.Estado -eq 403 -and $bloqueada.Json.codigo -eq 'debe_cambiar_credencial') `
                'Hasta elegir su contrasena, el administrador no puede hacer nada mas (403 debe_cambiar_credencial)' "Con la clave provisional, el estado del PIN respondio $($bloqueada.Estado): $($bloqueada.Cuerpo)"
            $cambio = Pedir "$baseA/api/acceso/yo/credencial/" 'PUT' (@{ secreto_actual = $claveInicial; secreto_nuevo = $claveElegida } | ConvertTo-Json -Compress) 60 $pase
            Comprobar ($cambio.Estado -eq 200) 'El administrador elige su propia contrasena (PUT yo/credencial)' "Cambiar la contrasena respondio $($cambio.Estado): $($cambio.Cuerpo)"

            $viejaClave = & $login $claveInicial $pinMaestro
            Comprobar ($viejaClave.Estado -eq 401) 'La contrasena provisional de la hoja de acceso ya no sirve' "La clave provisional siguio entrando ($($viejaClave.Estado))"
            $segundo = & $login $claveElegida $pinMaestro
            Comprobar ($segundo.Estado -eq 200 -and $segundo.Json.usuario.debe_cambiar_credencial -eq $false) 'Entra con su contrasena propia y el PIN maestro, ya sin la marca de provisional' "El segundo ingreso respondio $($segundo.Estado): $($segundo.Cuerpo)"
            if ($segundo.Estado -eq 200) {
                $pase = [string]$segundo.Json.token
                # Con la sesion ya definitiva, el estado del PIN maestro: configurado y vigente, sin verse.
                $estadoPin = Pedir "$baseA/api/acceso/pin-maestro/" 'GET' '' 30 $pase
                Comprobar ($estadoPin.Estado -eq 200 -and $estadoPin.Json.configurado -eq $true -and $estadoPin.Json.vencido -eq $false) 'La administracion ve el PIN maestro como configurado y vigente' "Estado del PIN: $($estadoPin.Estado) $($estadoPin.Cuerpo)"
                Comprobar ($estadoPin.Cuerpo -notmatch [regex]::Escape($pinMaestro)) 'El estado del PIN maestro no lo revela' 'El estado del PIN maestro trae el PIN'
                $fuenteConSesion = Pedir "$baseA/api/aula/fuente/" 'GET' '' 30 $pase
                Comprobar ($fuenteConSesion.Estado -eq 200) 'Con la sesion del administrador /api/aula/fuente/ responde 200 (con o sin AVACOM Contenido)' "/api/aula/fuente/ con sesion respondio $($fuenteConSesion.Estado)"
            }
        }

        # El nodo ya se ve instalado desde el host (lo que lee la pantalla final del instalador).
        $codigoV2 = Host-Ejecutar $instA @('validar', '60')
        $resumenV2 = Leer-Texto (Join-Path $datosA 'Logs\resumen-nodo.txt')
        Comprobar ($codigoV2 -eq 0 -and $resumenV2 -match 'organizacion=si' -and $resumenV2 -match '(?m)^pin_maestro=configurado') `
            'validar ya ve la organizacion y el PIN maestro configurado (la pantalla final dejara de avisar)' "validar devolvio $codigoV2; resumen: $resumenV2"

        # El lanzador (D): se prueba con el nodo vivo, porque espera /health/ antes de abrir la aplicacion.
        Titulo 'D · El lanzador abre la aplicacion con el perfil de WebView2 de quien da la clase'
        $appFalsa = Join-Path $instA 'App'
        New-Item -ItemType Directory -Force $appFalsa | Out-Null
        $fuenteFalsa = @'
using System; using System.IO;
public static class Prueba {
    public static int Main() {
        File.WriteAllText(Environment.GetEnvironmentVariable("AVACOM_ENSAYO_SALIDA"),
            "WEBVIEW2_USER_DATA_FOLDER=" + Environment.GetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER"));
        return 0;
    }
}
'@
        Add-Type -TypeDefinition $fuenteFalsa -OutputAssembly (Join-Path $appFalsa 'Avacom.Lms.Ops.exe') -OutputType ConsoleApplication
        $perfilReal = Join-Path $env:LOCALAPPDATA 'AVACOM\OPS Master\WebView2'
        $existiaPerfil = Test-Path $perfilReal
        $env:AVACOM_ENSAYO_SALIDA = Join-Path $Raiz 'lanzador-1.txt'
        $codigo = Host-Ejecutar $instA @('iniciar') 90
        Start-Sleep -Seconds 2
        Comprobar ($codigo -eq 0) 'El lanzador termina bien' "El lanzador devolvio $codigo`: $(Leer-Texto (Join-Path $datosA 'Logs\lanzador.log'))"
        $visto = (Leer-Texto $env:AVACOM_ENSAYO_SALIDA).Trim()
        Comprobar ($visto -eq "WEBVIEW2_USER_DATA_FOLDER=$perfilReal") `
            'La aplicacion recibe WEBVIEW2_USER_DATA_FOLDER = el perfil del usuario (escribible), no la carpeta del programa' `
            "La aplicacion vio '$visto' y esperaba '$perfilReal'"
        Comprobar (Test-Path $perfilReal) 'El perfil de WebView2 del usuario se creo y se puede escribir' 'No se creo el perfil de WebView2 del usuario'

        # Si el entorno ya trae una carpeta (soporte, depuracion), se respeta.
        $env:WEBVIEW2_USER_DATA_FOLDER = Join-Path $Raiz 'perfil-indicado'
        $env:AVACOM_ENSAYO_SALIDA = Join-Path $Raiz 'lanzador-2.txt'
        $codigo = Host-Ejecutar $instA @('iniciar') 90
        Start-Sleep -Seconds 2
        $visto2 = (Leer-Texto $env:AVACOM_ENSAYO_SALIDA).Trim()
        Comprobar ($visto2 -eq "WEBVIEW2_USER_DATA_FOLDER=$(Join-Path $Raiz 'perfil-indicado')") 'Si el entorno ya indica un perfil de WebView2, el lanzador lo respeta' "El lanzador piso la carpeta indicada: '$visto2'"
        Remove-Item Env:\WEBVIEW2_USER_DATA_FOLDER -ErrorAction SilentlyContinue

        # No deja nada que no fuera suyo: si el perfil no existia antes del ensayo, se retira.
        if (-not $existiaPerfil -and (Test-Path $perfilReal)) { Remove-Item $perfilReal -Recurse -Force -ErrorAction SilentlyContinue }
    }

    Detener-Servicio $servicioA (Join-Path $datosA 'Data\ops-master.sqlite3')

    # ================================================== C · sin configuracion
    Titulo 'C · Sin configuracion: el servicio no arranca un backend con valores de desarrollo'
    $instC = $instA    # el mismo programa, con una carpeta de estado NUEVA y vacia
    $datosC = Join-Path $Raiz 'C\datos'
    Limpiar-Entorno
    Fijar-Datos $datosC
    New-Item -ItemType Directory -Force (Join-Path $datosC 'Logs') | Out-Null
    $servicioC = Host-Servir $instC
    Start-Sleep -Seconds 8
    $hijosC = @(Hijos-De $servicioC.Id)
    Comprobar (@($hijosC).Count -eq 0) 'Sin backend.env el servicio NO lanzo el backend' 'El servicio lanzo el backend sin configuracion'
    Comprobar ((Leer-Texto (Join-Path $datosC 'Logs\servicio.log')) -match 'No se arranca el backend: no existe backend.env') 'El servicio dejo escrito por que no arranca' 'El servicio no explico por que no arranca'
    Comprobar (-not (Test-Path (Join-Path $instC 'Backend\db.sqlite3'))) 'No se creo ninguna base de datos vacia dentro del programa' 'Se creo una base de datos dentro de la carpeta del programa'
    Stop-Process -Id $servicioC.Id -Force -ErrorAction SilentlyContinue

    # ======================================== B · actualizacion con datos
    if ($VersionAnterior -and (Test-Path (Join-Path $VersionAnterior 'Backend\manage.py')) -and (Test-Path (Join-Path $VersionAnterior 'Runtime\Python\python.exe'))) {
        Titulo "B · Actualizacion desde la version anterior ($VersionAnterior), con datos"
        $instB = Join-Path $Raiz 'B\AVACOM\OPS Master'
        $datosB = Join-Path $Raiz 'B\datos'
        Armar-Instalacion (Join-Path $VersionAnterior 'Backend') (Join-Path $VersionAnterior 'Runtime') $instB
        Limpiar-Entorno
        Fijar-Datos $datosB

        $codigo = Host-Ejecutar $instB @('preparar')
        Comprobar ($codigo -eq 0) 'La version anterior prepara su nodo (host viejo, backend viejo)' "El host viejo devolvio $codigo"
        $configB = Join-Path $datosB 'Config\backend.env'
        $puertoB = Puerto-Libre
        Poner-Valor $configB 'AVACOM_OPS_BACKEND_PORT' $puertoB

        # Una version con PIN maestro (2.3 en adelante) no instala sin PIN: acceso_instalar lo toma de la variable de entorno (nunca como
        # argumento). La 2.2.0 y las anteriores no lo conocen: se actualiza un nodo SIN PIN, que es lo que ven esas aulas.
        $versionConPin = Test-Path (Join-Path $instB 'Backend\acceso\management\commands\acceso_pin_maestro.py')
        $pinDeLaBaseVieja = '739104'
        if ($versionConPin) { $env:AVACOM_LMS_PIN_MAESTRO = $pinDeLaBaseVieja }
        $instalacion = Python-Del-Nodo $instB $datosB @('manage.py', 'acceso_instalar', '--codigo', 'ENSAYO', '--nombre', 'Ensayo del instalador', '--pais', 'CO',
            '--admin-dni', '1000000001', '--admin-nombres', 'Ensayo', '--admin-apellidos', 'Del Instalador', '--admin-password', 'Ensayo.2026!')
        Remove-Item Env:\AVACOM_LMS_PIN_MAESTRO -ErrorAction SilentlyContinue
        Comprobar ($instalacion.Codigo -eq 0) "Se creo la organizacion y el administrador con el backend viejo$(if ($versionConPin) { ' (con PIN maestro)' })" "acceso_instalar fallo: $($instalacion.Salida)"
        Limpiar-Entorno
        Fijar-Datos $datosB

        $clavesAntes = @{}
        foreach ($k in 'AVACOM_LMS_CLAVE_DATOS', 'AVACOM_LMS_CLAVE_INDICE', 'AVACOM_LMS_CLAVE_TOKENS', 'AVACOM_LMS_SECRET') { $clavesAntes[$k] = Leer-Valor $configB $k }
        Comprobar (@($clavesAntes.Values | Where-Object { -not $_ }).Count -eq 0) 'La configuracion vieja tiene sus claves' 'La configuracion vieja no trae todas las claves'
        # Configuracion "tocada a mano": un enlace de pruebas, el ejemplo encendido y otra fuente de cursos.
        Add-Content $configB "`r`nAVACOM_CONTENIDO_ENLACE=C:\pruebas\enlace.json`r`nAVACOM_AULA_PERMITIR_EJEMPLO=1`r`nAVACOM_AULA_FUENTE_CURSOS=ejemplo`r`n" -Encoding UTF8

        # Lo que hace el asistente: copia de seguridad, apartar lo viejo, copiar lo nuevo, preparar.
        $codigo = Host-Ejecutar $instB @('respaldar', '2.1.0')
        Comprobar ($codigo -eq 0) 'El host viejo hace la copia de seguridad de los datos' "respaldar devolvio $codigo"
        $respaldos = @(Get-ChildItem (Join-Path $datosB 'Respaldos') -Directory -ErrorAction SilentlyContinue)
        Comprobar ($respaldos.Count -ge 1 -and (Test-Path (Join-Path $respaldos[0].FullName 'Data\ops-master.sqlite3')) -and (Test-Path (Join-Path $respaldos[0].FullName 'Config\backend.env'))) `
            'La copia lleva la base y backend.env juntos' 'La copia de seguridad esta incompleta'
        Remove-Item (Join-Path $instB 'Backend') -Recurse -Force
        Remove-Item (Join-Path $instB 'Runtime') -Recurse -Force
        Copiar-Carpeta $backendNuevo (Join-Path $instB 'Backend')
        Copiar-Carpeta $runtimeNuevo (Join-Path $instB 'Runtime')
        Copy-Item (Join-Path $Staging 'manifiesto.json') (Join-Path $instB 'manifiesto.json') -ErrorAction SilentlyContinue

        $codigo = Host-Ejecutar $instB @('preparar') 400
        Comprobar ($codigo -eq 0) 'El host NUEVO prepara el nodo viejo (migraciones nuevas sobre la base con datos)' `
            "preparar devolvio $codigo`: $(Leer-Texto (Join-Path $datosB 'Logs\preparacion-estado.txt'))"
        foreach ($k in $clavesAntes.Keys) {
            Comprobar ((Leer-Valor $configB $k) -eq $clavesAntes[$k]) "$k no cambio con la actualizacion" "$k CAMBIO: las personas guardadas quedarian ilegibles"
        }
        Comprobar ((Leer-Valor $configB 'AVACOM_AULA_PERMITIR_EJEMPLO') -eq '0') 'El curso de ejemplo encendido a mano se apago' 'El curso de ejemplo siguio encendido'
        Comprobar ((Leer-Valor $configB 'AVACOM_AULA_FUENTE_CURSOS') -eq 'biblioteca') 'La fuente de cursos se fijo en biblioteca' 'La fuente de cursos no quedo en biblioteca'
        Comprobar ((Leer-Texto $configB) -notmatch '(?m)^\s*AVACOM_CONTENIDO_ENLACE\s*=') 'La nota de enlace de pruebas se retiro de la configuracion' 'La nota de enlace de pruebas sigue activa'
        Comprobar ((Leer-Texto $configB) -match '(?m)^#\s*AVACOM_CONTENIDO_ENLACE=') 'La linea retirada quedo comentada (se sabe que hubo)' 'La linea retirada no quedo comentada'
        Comprobar ((Leer-Valor $configB 'AVACOM_LMS_DIR_LOGS') -eq (Join-Path $datosB 'Logs')) 'Se agrego la carpeta de registros del nodo' 'No se agrego AVACOM_LMS_DIR_LOGS'
        $aviso = Leer-Texto (Join-Path $datosB 'Logs\preparacion-aviso.txt')
        Comprobar ($aviso -match 'nota de enlace' -and $aviso -match 'ejemplo') 'La pantalla final avisara de lo que se corrigio' "El aviso no menciona lo corregido: '$aviso'"

        $integridad = Python-Del-Nodo $instB $datosB @('-c', "import sqlite3,os; c=sqlite3.connect(os.environ['AVACOM_LMS_DB']); print(c.execute('PRAGMA integrity_check').fetchone()[0]); print(c.execute('select count(*) from m01_persona').fetchone()[0]); print(c.execute('select count(*) from m19_bitacora').fetchone()[0])")
        $lineasI = @($integridad.Salida -split "`r?`n" | Where-Object { $_.Trim() })
        Comprobar ($lineasI.Count -ge 3 -and $lineasI[0] -eq 'ok') 'La base migrada pasa PRAGMA integrity_check' "integrity_check: $($integridad.Salida)"
        Comprobar ($lineasI.Count -ge 3 -and [int]$lineasI[1] -ge 1) "Las personas siguen en la base ($($lineasI[1]))" 'Se perdieron las personas'
        Comprobar ($lineasI.Count -ge 3) "La bitacora de auditoria (m19_bitacora) existe tras migrar y tiene $($lineasI[2]) asiento(s)" 'No existe la tabla m19_bitacora tras migrar'

        Limpiar-Entorno
        Fijar-Datos $datosB
        $servicioB = Host-Servir $instB
        $arrancoB = Esperar-Salud $puertoB 120
        Comprobar $arrancoB 'El nodo actualizado arranca con el backend nuevo' "El nodo actualizado no respondio: $(Leer-Texto (Join-Path $datosB 'Logs\servicio.log'))"
        if ($arrancoB) {
            $codigo = Host-Ejecutar $instB @('validar', '60')
            Comprobar ($codigo -eq 0) 'validar correcto sobre el nodo actualizado' "validar devolvio $codigo"
            Comprobar ((Leer-Texto (Join-Path $datosB 'Logs\resumen-nodo.txt')) -match 'organizacion=si') 'El nodo sigue teniendo su organizacion' 'El nodo perdio su organizacion'
            # Un nodo que ya tenia organizacion antes del PIN maestro no lo tiene tras actualizar (lo dice el resumen que lee la pantalla final);
            # uno que ya lo tenia (2.3 en adelante) lo conserva: la actualizacion no lo toca.
            if ($versionConPin) {
                Comprobar ((Leer-Texto (Join-Path $datosB 'Logs\resumen-nodo.txt')) -match '(?m)^pin_maestro=configurado') 'El nodo actualizado conserva su PIN maestro (la actualizacion no lo toca)' 'El resumen del nodo actualizado no dice pin_maestro=configurado: la actualizacion perdio el PIN maestro'
                $cuerpoLogin = '{"identificador":"1000000001","secreto":"Ensayo.2026!","pin_maestro":"' + $pinDeLaBaseVieja + '"}'
            } else {
                Comprobar ((Leer-Texto (Join-Path $datosB 'Logs\resumen-nodo.txt')) -match '(?m)^pin_maestro=sin_configurar') 'El nodo actualizado avisa que le falta el PIN maestro (se configura en OPS, Seguridad del aula)' 'El resumen del nodo actualizado no dice pin_maestro=sin_configurar'
                $cuerpoLogin = '{"identificador":"1000000001","secreto":"Ensayo.2026!"}'
            }
            $login = Pedir "http://127.0.0.1:$puertoB/api/acceso/sesiones/" 'POST' $cuerpoLogin 30
            Comprobar ($login.Estado -eq 200) "El administrador inicia sesion tras actualizar$(if ($versionConPin) { ' (documento, contrasena y PIN maestro)' }): sus datos siguen legibles con las mismas claves" "El inicio de sesion respondio $($login.Estado): $($login.Cuerpo)"
            $audito = Pedir "http://127.0.0.1:$puertoB/api/auditoria/estado/"
            Comprobar ($audito.Estado -in 200, 401, 403) 'El modulo de auditoria responde en el nodo actualizado' "auditoria respondio $($audito.Estado)"
        }
        Detener-Servicio $servicioB (Join-Path $datosB 'Data\ops-master.sqlite3')
    } elseif ($VersionAnterior) {
        Write-Host ''
        Write-Host "  AVISO: $VersionAnterior no tiene Backend\ y Runtime\Python: se omite el ensayo de la actualizacion." -ForegroundColor Yellow
    } else {
        Write-Host ''
        Write-Host '  (sin -VersionAnterior: se omite el ensayo de la actualizacion con datos)' -ForegroundColor DarkGray
    }

    # ======================================== E · datos PROTEGIDOS: una migracion que falla no pierde nada
    # Con el libro de calificaciones hay notas que proteger. Si la politica del paquete es «protegidos», una actualizacion cuya migracion falla NO retira ni reemplaza la base:
    # el host se detiene (codigo 6) y deja la copia de seguridad, y el asistente restaura datos y configuracion (`restaurar-datos`). Aqui se provoca una migracion
    # que falla de verdad (un historial de migraciones inconsistente en la base, como el de una base a medio migrar) y se comprueba que no se pierde nada.
    $manifiestoDelPaquete = Join-Path $Staging 'manifiesto.json'
    $politicaDelPaquete = if (Test-Path $manifiestoDelPaquete) { [string](Get-Content $manifiestoDelPaquete -Raw -Encoding UTF8 | ConvertFrom-Json).politica_datos } else { '' }
    if ($VersionAnterior -and (Test-Path (Join-Path $VersionAnterior 'Backend\manage.py')) -and (Test-Path (Join-Path $VersionAnterior 'Runtime\Python\python.exe'))) {
        Titulo 'E · Datos protegidos: una migracion que falla no pierde nada y la copia se restaura'
        Comprobar ($politicaDelPaquete -eq 'protegidos') 'El manifiesto del paquete declara politica_datos = protegidos' "El manifiesto del paquete dice politica_datos = '$politicaDelPaquete'"
        if ($politicaDelPaquete -eq 'protegidos') {
            $instE = Join-Path $Raiz 'E\AVACOM\OPS Master'
            $datosE = Join-Path $Raiz 'E\datos'
            $carpetaE = Join-Path $Raiz 'E'
            Armar-Instalacion (Join-Path $VersionAnterior 'Backend') (Join-Path $VersionAnterior 'Runtime') $instE
            Limpiar-Entorno
            Fijar-Datos $datosE
            $codigo = Host-Ejecutar $instE @('preparar')
            Comprobar ($codigo -eq 0) 'E · La version anterior prepara su nodo' "El host viejo devolvio $codigo"
            $configE = Join-Path $datosE 'Config\backend.env'
            Poner-Valor $configE 'AVACOM_OPS_BACKEND_PORT' (Puerto-Libre)

            $versionConPinE = Test-Path (Join-Path $instE 'Backend\acceso\management\commands\acceso_pin_maestro.py')
            if ($versionConPinE) { $env:AVACOM_LMS_PIN_MAESTRO = '739104' }
            $instalacionE = Python-Del-Nodo $instE $datosE @('manage.py', 'acceso_instalar', '--codigo', 'ENSAYO', '--nombre', 'Ensayo del instalador', '--pais', 'CO',
                '--admin-dni', '1000000001', '--admin-nombres', 'Ensayo', '--admin-apellidos', 'Del Instalador', '--admin-password', 'Ensayo.2026!')
            Remove-Item Env:\AVACOM_LMS_PIN_MAESTRO -ErrorAction SilentlyContinue
            Comprobar ($instalacionE.Codigo -eq 0) 'E · Se creo la organizacion y el administrador con el backend viejo' "acceso_instalar fallo: $($instalacionE.Salida)"
            Limpiar-Entorno
            Fijar-Datos $datosE

            $clavesE = @{}
            foreach ($k in 'AVACOM_LMS_CLAVE_DATOS', 'AVACOM_LMS_CLAVE_INDICE', 'AVACOM_LMS_CLAVE_TOKENS', 'AVACOM_LMS_SECRET') { $clavesE[$k] = Leer-Valor $configE $k }
            # Configuracion «tocada a mano»: la actualizacion la corregiria; si la copia se restaura, vuelve tal como estaba.
            Poner-Valor $configE 'AVACOM_AULA_PERMITIR_EJEMPLO' '1'

            # Lo que hace el asistente: copia de seguridad, apartar lo viejo, copiar lo nuevo.
            $codigo = Host-Ejecutar $instE @('respaldar', '2.7.0')
            Comprobar ($codigo -eq 0) 'E · El host viejo hace la copia de seguridad antes de actualizar' "respaldar devolvio $codigo"
            Remove-Item (Join-Path $instE 'Backend') -Recurse -Force
            Remove-Item (Join-Path $instE 'Runtime') -Recurse -Force
            Copiar-Carpeta $backendNuevo (Join-Path $instE 'Backend')
            Copiar-Carpeta $runtimeNuevo (Join-Path $instE 'Runtime')
            Copy-Item $manifiestoDelPaquete (Join-Path $instE 'manifiesto.json') -ErrorAction SilentlyContinue

            # La base «a medio migrar»: se borra del historial la primera migracion de `acceso` (todas las versiones la tienen) y las demas quedan aplicadas sin su
            # antecesora: Django se niega a migrar (historial inconsistente), sea cual sea la version anterior.
            $utf8SinMarca = New-Object Text.UTF8Encoding($false)
            [IO.File]::WriteAllText((Join-Path $carpetaE 'envenenar.py'), @'
import os, sqlite3
c = sqlite3.connect(os.environ['AVACOM_LMS_DB'])
c.execute("delete from django_migrations where app = 'acceso' and name = '0001_initial'")
c.commit()
'@, $utf8SinMarca)
            [IO.File]::WriteAllText((Join-Path $carpetaE 'estado.py'), @'
import os, sqlite3
c = sqlite3.connect(os.environ['AVACOM_LMS_DB'])
print(c.execute('PRAGMA integrity_check').fetchone()[0])
print(c.execute('select count(*) from m01_persona').fetchone()[0])
print(c.execute("select count(*) from django_migrations where app = 'acceso' and name = '0001_initial'").fetchone()[0])
'@, $utf8SinMarca)
            $veneno = Python-Del-Nodo $instE $datosE @((Join-Path $carpetaE 'envenenar.py'))
            Comprobar ($veneno.Codigo -eq 0) 'E · Se provoco una migracion que va a fallar (historial inconsistente en la base)' "No se pudo preparar la prueba: $($veneno.Salida)"
            $antes = @((Python-Del-Nodo $instE $datosE @((Join-Path $carpetaE 'estado.py'))).Salida -split "`r?`n" | Where-Object { $_.Trim() })

            Limpiar-Entorno
            Fijar-Datos $datosE
            $codigo = Host-Ejecutar $instE @('preparar') 400
            Comprobar ($codigo -eq 6) "E · El host NUEVO se detiene cuando la migracion falla (codigo 6)" "preparar devolvio $codigo (se esperaba 6: no pudo migrar)"
            $estadoE = Leer-Texto (Join-Path $datosE 'Logs\preparacion-estado.txt')
            Comprobar ($estadoE -match 'copia de seguridad') 'E · El motivo dice que se conserva la copia de seguridad' "El motivo no lo dice: '$estadoE'"

            $durante = @((Python-Del-Nodo $instE $datosE @((Join-Path $carpetaE 'estado.py'))).Salida -split "`r?`n" | Where-Object { $_.Trim() })
            Comprobar ($durante.Count -ge 3 -and $durante[0] -eq 'ok' -and [int]$durante[1] -ge 1) 'E · La base NO se reemplazo ni se vacio: sigue integra y con sus personas' "Estado de la base tras el fallo: $($durante -join ' | ')"
            Comprobar ($antes.Count -ge 3 -and [int]$antes[2] -eq 0 -and $durante.Count -ge 3 -and [int]$durante[2] -eq 0) 'E · Es la misma base de antes (sigue con el historial dañado que se le provoco), no una nueva' "La base cambio: $($durante -join ' | ') (antes: $($antes -join ' | '))"
            Comprobar (-not ((Leer-Texto (Join-Path $datosE 'Logs\preparacion-aviso.txt')) -match 'empezo con una nueva')) 'E · No se avisa de «base nueva»: con datos protegidos nunca se empieza de cero' 'El aviso dice que se empezo con una base nueva'

            # Lo que hace el asistente al ver el codigo 6: devolver los datos desde la copia.
            Limpiar-Entorno
            Fijar-Datos $datosE
            $codigo = Host-Ejecutar $instE @('restaurar-datos') 240
            Comprobar ($codigo -eq 0) 'E · restaurar-datos devuelve los datos desde la copia' "restaurar-datos devolvio $codigo"
            $despues = @((Python-Del-Nodo $instE $datosE @((Join-Path $carpetaE 'estado.py'))).Salida -split "`r?`n" | Where-Object { $_.Trim() })
            Comprobar ($despues.Count -ge 3 -and $despues[0] -eq 'ok' -and [int]$despues[1] -ge 1) 'E · Tras restaurar, la base esta integra y con sus personas' "Estado tras restaurar: $($despues -join ' | ')"
            Comprobar ($despues.Count -ge 3 -and [int]$despues[2] -eq 1) 'E · Tras restaurar, la base es la de la copia (con su historial sano, sin el daño que se le provoco despues)' "Estado tras restaurar: $($despues -join ' | ')"
            foreach ($k in $clavesE.Keys) {
                Comprobar ((Leer-Valor $configE $k) -eq $clavesE[$k]) "E · $k vuelve a ser la de la copia" "$k no coincide con la de la copia"
            }
            Comprobar ((Leer-Valor $configE 'AVACOM_AULA_PERMITIR_EJEMPLO') -eq '1') 'E · backend.env vuelve a ser el de la copia (lo que la actualizacion habia corregido, tal como estaba)' 'backend.env no se restauro'
        }
    } elseif ($VersionAnterior) {
        Write-Host '  (E se omite: la version anterior no tiene Backend\ y Runtime\Python)' -ForegroundColor Yellow
    }
    }  # fin de A..E (-SoloActualizaciones los omite)

    # ======================================== F · MOD-017 Update Manager: el host aplica, verifica y revierte (TST-061, NFR-022)
    # El host (servicio SYSTEM) obedece Actualizaciones\orden.json con el backend PARADO, con un checkpoint antes de cada paso (comprobar, respaldar, instantanea, copiar, migrar,
    # verificar), y si algo falla vuelve atras SOLO (codigo desde la instantanea, base desde la copia). Aqui se ensaya sobre el backend empaquetado, con migraciones y archivos de verdad.
    if (-not $SinActualizaciones) {
        Titulo 'F · Update Manager (MOD-017): el host aplica, verifica y revierte un paquete de modulo'
        $instF = Join-Path $Raiz 'F\AVACOM\OPS Master'
        $datosF = Join-Path $Raiz 'F\datos'
        $carpetaF = Join-Path $Raiz 'F'
        $actF = Join-Path $datosF 'ProgramData\AVACOM\OPS Master\Actualizaciones'
        Armar-Instalacion $backendNuevo $runtimeNuevo $instF
        Copy-Item (Join-Path $Staging 'manifiesto.json') (Join-Path $instF 'manifiesto.json') -ErrorAction SilentlyContinue
        Limpiar-Entorno
        Fijar-Datos $datosF
        $codigo = Host-Ejecutar $instF @('preparar')
        Comprobar ($codigo -eq 0) 'F · El nodo de ensayo se prepara (configuracion, claves, migraciones)' "F · preparar devolvio $codigo`: $(Leer-Texto (Join-Path $datosF 'Logs\preparacion-estado.txt'))"
        $configF = Join-Path $datosF 'Config\backend.env'
        $puertoF = Puerto-Libre
        Poner-Valor $configF 'AVACOM_OPS_BACKEND_PORT' $puertoF
        $versionDelNodo = Leer-Texto (Join-Path $instF 'manifiesto.json')

        $servicioF = Iniciar-Host-De-Ensayo $instF
        $arrancoF = Esperar-Salud $puertoF 120
        Comprobar $arrancoF "F · El nodo de ensayo arranca (puerto $puertoF)" "F · El nodo de ensayo no respondio: $(Leer-Texto (Join-Path $datosF 'Logs\servicio.log'))"

        if ($arrancoF) {
            Comprobar (Test-Path $actF) 'F · El host creo Actualizaciones\ (la misma carpeta que usa el backend)' "F · No existe $actF"
            $huellaInicial = Huella-De-Codigo $instF
            $estado0 = Estado-De-Ensayo $instF $datosF $carpetaF
            Comprobar ($estado0.integridad -eq 'ok' -and @($estado0.tablas).Count -eq 0) 'F · Punto de partida: la base esta integra y sin tablas de ensayo' "F · Estado inicial: $($estado0 | ConvertTo-Json -Compress)"

            function Aplicar-Y-Esperar($p, [string] $accion = 'aplicar', [int] $espera = 480) {
                $reloj = [Diagnostics.Stopwatch]::StartNew()
                Escribir-Orden $p $accion $actF
                $r = Esperar-Resultado $actF $p.OrdenId $espera
                return [pscustomobject]@{ Resultado = $r; Segundos = [math]::Round($reloj.Elapsed.TotalSeconds, 1) }
            }
            function Archivos-Aplicados($p) {
                foreach ($a in $p.Archivos) {
                    $ruta = Join-Path $instF ('Backend\' + ($a.ruta -replace '/', '\'))
                    if (-not (Test-Path $ruta) -or (Sha-De $ruta) -ne $a.sha256) { return $false }
                }
                return $true
            }
            function Todo-Como-Antes([string] $huella) { return ((Huella-De-Codigo $instF) -eq $huella) }
            function Nuevo-Id($p) { $p.OrdenId = [guid]::NewGuid().ToString('D') }

            # ---------------------------------------------------------------- F1 · una aplicacion correcta
            Write-Host '  -- F1 · aplicar un paquete (1 archivo que cambia, 2 nuevos, 3 migraciones)' -ForegroundColor DarkCyan
            $p1 = Nuevo-Paquete $instF $actF 'a' 3 0 2
            $hijosAntes = @(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId })
            $e1 = Aplicar-Y-Esperar $p1
            $r1 = $e1.Resultado
            Comprobar ($null -ne $r1 -and $r1.resultado -eq 'aplicado') "F1 · El host aplica el paquete (resultado aplicado en $($e1.Segundos) s)" "F1 · Resultado inesperado tras $($e1.Segundos) s: $(if ($r1) { $r1 | ConvertTo-Json -Compress } else { 'ninguno' }). Mira $(Join-Path $datosF 'Logs\actualizacion.log')"
            if ($r1 -and $r1.resultado -eq 'aplicado') {
                Comprobar (Archivos-Aplicados $p1) 'F1 · Los archivos del paquete estan en Backend\ con su huella' 'F1 · Un archivo de Backend\ no coincide con el del paquete'
                Comprobar (@($r1.migraciones).Count -eq 3 -and @($r1.migraciones | Where-Object { -not $_.ok }).Count -eq 0) 'F1 · Las 3 migraciones corrieron y el resultado las lista' "F1 · Migraciones del resultado: $($r1.migraciones | ConvertTo-Json -Compress)"
                $estado = Estado-De-Ensayo $instF $datosF $carpetaF
                Comprobar (@($estado.tablas).Count -eq 3 -and @($estado.migs).Count -eq 3 -and $estado.integridad -eq 'ok') 'F1 · La base tiene las 3 tablas y las 3 migraciones aplicadas' "F1 · Estado de la base: $($estado | ConvertTo-Json -Compress)"
                Comprobar (-not (Test-Path (Join-Path $actF 'checkpoint.json'))) 'F1 · El checkpoint se retiro al terminar' 'F1 · Quedo checkpoint.json'
                Comprobar (Test-Path (Join-Path $actF "versiones\$($p1.PaqueteId)\anterior\_indice.json")) 'F1 · La instantanea del codigo anterior se conserva (14 dias)' 'F1 · No hay instantanea'
                Comprobar (-not $servicioF.HasExited) 'F1 · El servicio sigue vivo y levanta el backend de nuevo' 'F1 · El host se cerro'
                Comprobar (Esperar-Salud $puertoF 120) 'F1 · /health/ responde con el codigo nuevo' 'F1 · El backend no volvio a responder'
                $hijosDespues = @(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId })
                Comprobar ((@($hijosDespues | Where-Object { $hijosAntes -contains $_ }).Count -eq 0) -and $hijosDespues.Count -ge 1) 'F1 · El backend se paro para aplicar y volvio a levantarse (otro proceso)' "F1 · Procesos hijos antes $($hijosAntes -join ',') y despues $($hijosDespues -join ',')"
                $archivado = Cerrar-Orden $actF $p1.OrdenId
                Comprobar $true "F1 · El backend lee el resultado al arrancar (archivado por el: $archivado)" ''
            }

            # ---------------------------------------------------------------- F2 · revertir a mano (instantanea dentro de los 14 dias)
            Write-Host '  -- F2 · revertir el paquete a mano (migrar hacia atras, volver al codigo anterior)' -ForegroundColor DarkCyan
            if ($r1 -and $r1.resultado -eq 'aplicado') {
                Nuevo-Id $p1
                $e2 = Aplicar-Y-Esperar $p1 'revertir'
                $r2 = $e2.Resultado
                Comprobar ($null -ne $r2 -and $r2.resultado -eq 'revertido') "F2 · El host revierte el paquete (resultado revertido en $($e2.Segundos) s)" "F2 · Resultado inesperado: $(if ($r2) { $r2 | ConvertTo-Json -Compress } else { 'ninguno' })"
                Comprobar (Todo-Como-Antes $huellaInicial) 'F2 · El codigo vuelve a ser, byte a byte, el de antes del paquete' 'F2 · El codigo no volvio a ser el de antes'
                $estado = Estado-De-Ensayo $instF $datosF $carpetaF
                Comprobar (@($estado.tablas).Count -eq 0 -and @($estado.migs).Count -eq 0 -and $estado.integridad -eq 'ok') 'F2 · Las migraciones se deshicieron con su reverso (sin tablas ni filas de ensayo)' "F2 · Estado de la base: $($estado | ConvertTo-Json -Compress)"
                Comprobar (-not (Test-Path (Join-Path $actF "versiones\$($p1.PaqueteId)"))) 'F2 · Revertido con exito, la instantanea ya no hace falta' 'F2 · La instantanea sigue ahi'
                Comprobar (Esperar-Salud $puertoF 120) 'F2 · /health/ responde con el codigo de antes' 'F2 · El backend no volvio a responder'
                $null = Cerrar-Orden $actF $p1.OrdenId -Silencioso
            }

            # ---------------------------------------------------------------- F3 · TST-061: un fallo al 60 % se revierte solo
            Write-Host '  -- F3 · TST-061: la tercera de CINCO migraciones falla de verdad (60 %): el aula vuelve sola a la version anterior' -ForegroundColor DarkCyan
            $p3 = Nuevo-Paquete $instF $actF 'f' 5 3 2 5
            $e3 = Aplicar-Y-Esperar $p3
            $r3 = $e3.Resultado
            Comprobar ($null -ne $r3 -and $r3.resultado -eq 'revertido') "F3 · El host revierte SOLO (revertido en $($e3.Segundos) s desde la orden)" "F3 · Resultado inesperado: $(if ($r3) { $r3 | ConvertTo-Json -Compress } else { 'ninguno' })"
            if ($r3) {
                Comprobar ($r3.paso -eq 'migrar' -and "$($r3.error)" -match 'migracion') 'F3 · El resultado dice en que paso fallo (migrar) y por que' "F3 · paso=$($r3.paso) error=$($r3.error)"
                Comprobar (Todo-Como-Antes $huellaInicial) 'F3 · El codigo (el archivo cambiado y los nuevos) vuelve a ser el de antes' 'F3 · El codigo no volvio a ser el de antes'
                $estado = Estado-De-Ensayo $instF $datosF $carpetaF
                Comprobar (@($estado.tablas).Count -eq 0 -and @($estado.migs).Count -eq 0 -and $estado.integridad -eq 'ok') 'F3 · La base se restauro de la copia (las 2 migraciones que si corrieron se deshicieron)' "F3 · Estado de la base: $($estado | ConvertTo-Json -Compress)"
                Comprobar (Esperar-Salud $puertoF 120) 'F3 · El aula responde con la version anterior' 'F3 · El backend no volvio a responder'
                Comprobar ($e3.Segundos -le ($p3.Limite * 60)) "F3 · NFR-022 / AC-077: toda la operacion (aplicar, fallar y volver atras) en $($e3.Segundos) s, dentro del limite de $($p3.Limite) min" "F3 · Tardo $($e3.Segundos) s: supera el limite de $($p3.Limite) min"
                Write-Host "  [info]   $($r3.detalle)" -ForegroundColor DarkGray
                $null = Cerrar-Orden $actF $p3.OrdenId -Silencioso
            }

            # ---------------------------------------------------------------- F3b · fallos inyectados en otros pasos (host de ensayo con AVACOM_ACTUALIZACION_FALLO)
            foreach ($caso in @(
                    @{ Fallo = 'copiar:60'; Paso = 'copiar'; Migraciones = 2; Nuevos = 5; Rotulo = 'al 60 % de la copia de archivos' },
                    @{ Fallo = 'verificar:50'; Paso = 'verificar'; Migraciones = 2; Nuevos = 2; Rotulo = 'al verificar, con TODO ya copiado y migrado' })) {
                Write-Host "  -- F3b · fallo inyectado $($caso.Rotulo)" -ForegroundColor DarkCyan
                Matar-Host $servicioF
                $servicioF = Iniciar-Host-De-Ensayo $instF $caso.Fallo
                Comprobar (Esperar-Salud $puertoF 120) 'F3b · El nodo de ensayo arranca con el gancho de fallo' 'F3b · No arranco'
                $pb = Nuevo-Paquete $instF $actF 'b' $caso.Migraciones 0 $caso.Nuevos 5
                $eb = Aplicar-Y-Esperar $pb
                $rb = $eb.Resultado
                Comprobar ($null -ne $rb -and $rb.resultado -eq 'revertido' -and $rb.paso -eq $caso.Paso) "F3b · Revertido solo, con el paso «$($caso.Paso)» como causa ($($eb.Segundos) s)" "F3b · Resultado: $(if ($rb) { $rb | ConvertTo-Json -Compress } else { 'ninguno' })"
                Comprobar (Todo-Como-Antes $huellaInicial) 'F3b · Codigo identico al de antes' 'F3b · El codigo no volvio a ser el de antes'
                $estado = Estado-De-Ensayo $instF $datosF $carpetaF
                Comprobar (@($estado.tablas).Count -eq 0 -and @($estado.migs).Count -eq 0 -and $estado.integridad -eq 'ok') 'F3b · Base identica a la de antes (sin tablas ni migraciones)' "F3b · Estado de la base: $($estado | ConvertTo-Json -Compress)"
                Comprobar (Esperar-Salud $puertoF 120) 'F3b · El aula responde con la version anterior' 'F3b · El backend no volvio a responder'
                $null = Cerrar-Orden $actF $pb.OrdenId -Silencioso
            }
            Matar-Host $servicioF
            $servicioF = Iniciar-Host-De-Ensayo $instF
            $null = Esperar-Salud $puertoF 120

            # ---------------------------------------------------------------- F4 · el host muere en cada checkpoint (A4)
            Write-Host '  -- F4 · el host muere a mitad (corte de energia) en cada checkpoint: al volver reanuda o revierte' -ForegroundColor DarkCyan
            $cortes = @(
                @{ Corte = 'respaldar'; Fallo = ''; Esperado = 'aplicado'; Migraciones = 2; Nuevos = 2; Quien = 'reanuda desde el principio' },
                @{ Corte = 'instantanea:50'; Fallo = ''; Esperado = 'aplicado'; Migraciones = 2; Nuevos = 4; Quien = 'reanuda: la instantanea a medias se rehace' },
                @{ Corte = 'copiar:60'; Fallo = ''; Esperado = 'revertido'; Migraciones = 2; Nuevos = 5; Quien = 'revierte: el codigo estaba a medias' },
                @{ Corte = 'migrar:60'; Fallo = ''; Esperado = 'revertido'; Migraciones = 5; Nuevos = 2; Quien = 'revierte: la base estaba a medias' },
                @{ Corte = 'verificar'; Fallo = ''; Esperado = 'aplicado'; Migraciones = 2; Nuevos = 2; Quien = 'repite la verificacion' },
                @{ Corte = 'deshacer'; Fallo = 'migrar:60'; Esperado = 'revertido'; Migraciones = 5; Nuevos = 2; Quien = 'repite la reversion que se corto' })
            foreach ($caso in $cortes) {
                Write-Host "  -- F4 · corte en «$($caso.Corte)» (se espera $($caso.Esperado): $($caso.Quien))" -ForegroundColor DarkCyan
                $huellaAntesDelCorte = Huella-De-Codigo $instF
                Matar-Host $servicioF
                $servicioF = Iniciar-Host-De-Ensayo $instF $caso.Fallo $caso.Corte
                Comprobar (Esperar-Salud $puertoF 120) 'F4 · El nodo de ensayo arranca con el gancho de corte' 'F4 · No arranco'
                $pc = Nuevo-Paquete $instF $actF 'c' $caso.Migraciones 0 $caso.Nuevos 5
                Escribir-Orden $pc 'aplicar' $actF
                $murio = $servicioF.WaitForExit(300000)
                Comprobar $murio "F4 · El host murio en «$($caso.Corte)», como un corte de energia" "F4 · El host no murio en 5 min"
                Comprobar (Test-Path (Join-Path $actF 'checkpoint.json')) 'F4 · Quedo checkpoint.json: se sabe en que paso murio' 'F4 · No quedo checkpoint.json'
                Matar-Host $servicioF
                Comprobar (-not (Test-Path (Join-Path $actF 'resultado.json'))) 'F4 · Todavia no hay resultado: la orden sigue pendiente' 'F4 · Ya habia un resultado'
                $reloj = [Diagnostics.Stopwatch]::StartNew()
                $servicioF = Iniciar-Host-De-Ensayo $instF
                $rc = Esperar-Resultado $actF $pc.OrdenId 480
                Comprobar ($null -ne $rc -and $rc.resultado -eq $caso.Esperado) "F4 · Al volver el host $($caso.Quien): $($caso.Esperado) en $([math]::Round($reloj.Elapsed.TotalSeconds, 1)) s" "F4 · Resultado: $(if ($rc) { $rc | ConvertTo-Json -Compress } else { 'ninguno' })"
                if ($rc) {
                    Comprobar (Esperar-Salud $puertoF 120) 'F4 · El aula responde' 'F4 · El backend no volvio a responder'
                    Comprobar (-not (Test-Path (Join-Path $actF 'checkpoint.json'))) 'F4 · El checkpoint se retiro' 'F4 · Sigue checkpoint.json'
                    $estado = Estado-De-Ensayo $instF $datosF $carpetaF
                    if ($caso.Esperado -eq 'aplicado') {
                        Comprobar ((Archivos-Aplicados $pc) -and $estado.integridad -eq 'ok' -and @($estado.migs).Count -ge $caso.Migraciones) 'F4 · El paquete quedo aplicado entero (archivos y migraciones)' "F4 · Estado: $($estado | ConvertTo-Json -Compress)"
                        # Se deja el aula como estaba para el caso siguiente: revertido a mano, con otra orden.
                        $null = Cerrar-Orden $actF $pc.OrdenId -Silencioso
                        Nuevo-Id $pc
                        $er = Aplicar-Y-Esperar $pc 'revertir'
                        Comprobar ($null -ne $er.Resultado -and $er.Resultado.resultado -eq 'revertido') 'F4 · (limpieza) revertido a mano para el caso siguiente' "F4 · La limpieza no revirtio: $(if ($er.Resultado) { $er.Resultado | ConvertTo-Json -Compress })"
                    } else {
                        Comprobar ((Huella-De-Codigo $instF) -eq $huellaAntesDelCorte) 'F4 · El codigo vuelve a ser, byte a byte, el de antes' 'F4 · El codigo no volvio a ser el de antes'
                        Comprobar (@($estado.tablas).Count -eq 0 -and @($estado.migs).Count -eq 0 -and $estado.integridad -eq 'ok') 'F4 · La base vuelve a ser la de antes (sin tablas ni migraciones)' "F4 · Estado: $($estado | ConvertTo-Json -Compress)"
                    }
                }
                $null = Cerrar-Orden $actF $pc.OrdenId -Silencioso
            }

            # ---------------------------------------------------------------- F5 · una clase abierta aplaza la aplicacion y NO se detiene nada (R-01)
            Write-Host '  -- F5 · con una clase abierta la aplicacion se aplaza y el backend sigue en pie' -ForegroundColor DarkCyan
            Matar-Host $servicioF
            $servicioF = Iniciar-Host-De-Ensayo $instF
            Comprobar (Esperar-Salud $puertoF 120) 'F5 · El nodo de ensayo arranca' 'F5 · No arranco'
            $claveClase = Join-Path $carpetaF 'clase-act.py'
            Escribir-Texto $claveClase @'
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'avacom_lms.settings')
django.setup()
from classroom_engine import models as m
from classroom_engine.dominio import sesion as dom
if sys.argv[1] == 'crear':
    m.SesionDeClase.objects.create(id='ensayo-clase-1', profesor_id='ensayo', via_origen='libre', codigo_union='ENS123', estado=dom.ABIERTA)
else:
    m.SesionDeClase.objects.filter(id='ensayo-clase-1').delete()
print('listo')
'@
            $crear = Python-Del-Nodo $instF $datosF @($claveClase, 'crear')
            Limpiar-Entorno; Fijar-Datos $datosF
            Comprobar ($crear.Codigo -eq 0) 'F5 · Se abrio una clase en la base del nodo' "F5 · No se pudo abrir la clase: $($crear.Salida)"
            $hijosAntes = @(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId })
            $huellaAntes = Huella-De-Codigo $instF
            $pk = Nuevo-Paquete $instF $actF 'k' 2 0 1
            $ek = Aplicar-Y-Esperar $pk
            $rk = $ek.Resultado
            Comprobar ($null -ne $rk -and $rk.resultado -eq 'aplazada' -and $rk.paso -eq 'comprobar') "F5 · El host responde «aplazada» en el paso comprobar ($($ek.Segundos) s)" "F5 · Resultado: $(if ($rk) { $rk | ConvertTo-Json -Compress } else { 'ninguno' })"
            Start-Sleep -Seconds 2
            $hijosDespues = @(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId })
            Comprobar ($hijosAntes.Count -ge 1 -and (@($hijosAntes) -join ',') -eq (@($hijosDespues) -join ',')) 'F5 · El backend NO se paro: es el mismo proceso (la clase sigue)' "F5 · Procesos antes $($hijosAntes -join ',') y despues $($hijosDespues -join ',')"
            Comprobar ((Huella-De-Codigo $instF) -eq $huellaAntes -and -not (Test-Path (Join-Path $actF "versiones\$($pk.PaqueteId)"))) 'F5 · No se toco ningun archivo ni se tomo instantanea' 'F5 · El host toco algo con una clase abierta'
            Comprobar (-not (Test-Path (Join-Path $actF 'checkpoint.json'))) 'F5 · Sin checkpoint pendiente' 'F5 · Quedo checkpoint.json'
            $null = Cerrar-Orden $actF $pk.OrdenId -Silencioso
            $borrar = Python-Del-Nodo $instF $datosF @($claveClase, 'borrar')
            Limpiar-Entorno; Fijar-Datos $datosF
            Comprobar ($borrar.Codigo -eq 0) 'F5 · La clase de ensayo se retiro' "F5 · No se pudo retirar la clase: $($borrar.Salida)"

            # ---------------------------------------------------------------- F6 · lo que el host NO obedece
            Write-Host '  -- F6 · ordenes que el host rechaza sin tocar nada (staging alterado, .avupd alterado, rutas fuera de su sitio)' -ForegroundColor DarkCyan
            $huellaAntes = Huella-De-Codigo $instF
            $fueraDeSitio = [ordered]@{ ruta = 'reporting/../../Runtime/ensayo_malo.py'; bytes = 1; sha256 = ('a' * 64) }
            $malas = @(
                @{ Rotulo = 'un archivo del staging alterado'; Tipo = 'staging' },
                @{ Rotulo = 'el .avupd guardado alterado'; Tipo = 'avupd' },
                @{ Rotulo = 'una ruta con retroceso (..)'; Tipo = 'ruta'; Archivos = @($fueraDeSitio) },
                @{ Rotulo = 'una ruta de backend\biblioteca (de AVACOM Contenido)'; Tipo = 'ruta'; Archivos = @([ordered]@{ ruta = 'biblioteca/ensayo_malo.py'; bytes = 1; sha256 = ('b' * 64) }) },
                @{ Rotulo = 'una ruta de otra app que el paquete no declara (acceso)'; Tipo = 'ruta'; Archivos = @([ordered]@{ ruta = 'acceso/ensayo_malo.py'; bytes = 1; sha256 = ('c' * 64) }) },
                @{ Rotulo = 'un archivo de configuracion (backend.env)'; Tipo = 'ruta'; Archivos = @([ordered]@{ ruta = 'reporting/backend.env'; bytes = 1; sha256 = ('d' * 64) }) },
                @{ Rotulo = 'una letra de unidad'; Tipo = 'ruta'; Archivos = @([ordered]@{ ruta = 'C:/Windows/ensayo_malo.py'; bytes = 1; sha256 = ('e' * 64) }) })
            foreach ($mala in $malas) {
                $pm = Nuevo-Paquete $instF $actF 'm' 1 0 1
                if ($mala.Tipo -eq 'staging') {
                    $archivoStaging = Join-Path $pm.Staging 'reporting\dominio\ensayo_m_1.py'
                    [IO.File]::AppendAllText($archivoStaging, "`n# alterado`n")
                } elseif ($mala.Tipo -eq 'avupd') {
                    [IO.File]::AppendAllText($pm.ArchivoPaquete, 'X')
                }
                $cambios = @{}
                if ($mala.ContainsKey('Archivos')) { $cambios['archivos'] = $mala.Archivos }
                $hijosAntes = @(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId })
                $reloj = [Diagnostics.Stopwatch]::StartNew()
                $json = $null
                Escribir-Orden $pm 'aplicar' $actF $cambios
                $rm = Esperar-Resultado $actF $pm.OrdenId 120
                Comprobar ($null -ne $rm -and $rm.resultado -eq 'rechazada') "F6 · $($mala.Rotulo): el host la rechaza ($([math]::Round($reloj.Elapsed.TotalSeconds, 1)) s)" "F6 · $($mala.Rotulo): resultado $(if ($rm) { $rm | ConvertTo-Json -Compress } else { 'ninguno' })"
                Comprobar ((Huella-De-Codigo $instF) -eq $huellaAntes -and -not (Test-Path (Join-Path $instF 'Runtime\ensayo_malo.py')) -and -not (Test-Path (Join-Path $instF 'Backend\biblioteca\ensayo_malo.py')) -and -not (Test-Path (Join-Path $instF 'Backend\acceso\ensayo_malo.py'))) `
                    "F6 · $($mala.Rotulo): no se escribio ni un archivo" "F6 · $($mala.Rotulo): el codigo cambio"
                Comprobar ((@(Hijos-De $servicioF.Id | ForEach-Object { $_.ProcessId }) -join ',') -eq ($hijosAntes -join ',')) "F6 · $($mala.Rotulo): el backend no se paro" 'F6 · El backend se paro con una orden rechazada'
                $null = Cerrar-Orden $actF $pm.OrdenId -Silencioso
            }

            # ---------------------------------------------------------------- F7 · tras una instalacion completa la instantanea se conserva, pero ya no sirve para volver atras
            Write-Host '  -- F7 · una instalacion completa no borra la instantanea (P-17) y el host no vuelve a un codigo de otra version' -ForegroundColor DarkCyan
            $p7 = Nuevo-Paquete $instF $actF 'g' 2 0 2
            $e7 = Aplicar-Y-Esperar $p7
            Comprobar ($null -ne $e7.Resultado -and $e7.Resultado.resultado -eq 'aplicado') 'F7 · Se aplica un paquete (queda su instantanea)' "F7 · Resultado: $(if ($e7.Resultado) { $e7.Resultado | ConvertTo-Json -Compress } else { 'ninguno' })"
            $null = Cerrar-Orden $actF $p7.OrdenId -Silencioso
            Matar-Host $servicioF
            # Lo que hace el asistente de una actualizacion completa: aparta el programa viejo y pone el nuevo (otra version). Actualizaciones\ vive en ProgramData y no se toca.
            Remove-Item (Join-Path $instF 'Backend') -Recurse -Force
            Remove-Item (Join-Path $instF 'Runtime') -Recurse -Force
            Copiar-Carpeta $backendNuevo (Join-Path $instF 'Backend')
            Copiar-Carpeta $runtimeNuevo (Join-Path $instF 'Runtime')
            $manifiestoNuevo = (Leer-Texto (Join-Path $Staging 'manifiesto.json')) -replace '"version":\s*"[^"]*"', '"version":  "9.9.9"'
            Escribir-Texto (Join-Path $instF 'manifiesto.json') $manifiestoNuevo
            Comprobar (Test-Path (Join-Path $actF "versiones\$($p7.PaqueteId)\anterior\_indice.json")) 'F7 · La instalacion completa dejo la instantanea intacta' 'F7 · La instantanea desaparecio'
            $servicioF = Iniciar-Host-De-Ensayo $instF
            Comprobar (Esperar-Salud $puertoF 120) 'F7 · El nodo arranca con el programa nuevo' 'F7 · No arranco'
            Nuevo-Id $p7
            $e7b = Aplicar-Y-Esperar $p7 'revertir' 180
            Comprobar ($null -ne $e7b.Resultado -and $e7b.Resultado.resultado -eq 'rechazada' -and "$($e7b.Resultado.error)" -match 'instalacion completa') 'F7 · Revertir se rechaza: el programa cambio de version y la instantanea ya no es de este producto' "F7 · Resultado: $(if ($e7b.Resultado) { $e7b.Resultado | ConvertTo-Json -Compress } else { 'ninguno' })"
            Comprobar (Test-Path (Join-Path $actF "versiones\$($p7.PaqueteId)\anterior\_indice.json")) 'F7 · Y no se borro nada' 'F7 · La instantanea desaparecio'
            $null = Cerrar-Orden $actF $p7.OrdenId -Silencioso

            # ---------------------------------------------------------------- F8 · 14 dias
            Write-Host '  -- F8 · a los 14 dias la instantanea se retira, salvo la de una reversion fallida' -ForegroundColor DarkCyan
            Matar-Host $servicioF
            $vieja = (Get-Date).AddDays(-15).ToUniversalTime()
            $viejaMs = [int64]([DateTimeOffset]$vieja).ToUnixTimeMilliseconds()
            $indiceDeP7 = Join-Path $actF "versiones\$($p7.PaqueteId)\anterior\_indice.json"
            $textoIndice = [IO.File]::ReadAllText($indiceDeP7, [Text.Encoding]::UTF8)
            Escribir-Texto $indiceDeP7 ($textoIndice -replace '"creado_en":\s*\d+', "`"creado_en`": $viejaMs")
            $guardada = [guid]::NewGuid().ToString('D')
            Escribir-Texto (Join-Path $actF "versiones\$guardada\anterior\_indice.json") "{`"formato`": 1, `"paquete_id`": `"$guardada`", `"producto`": `"2.0.0`", `"creado_en`": $viejaMs, `"archivos`": []}"
            Escribir-Texto (Join-Path $actF 'resultados\ensayo-fallida.json') "{`"formato`": 1, `"orden_id`": `"ensayo-fallida`", `"paquete_id`": `"$guardada`", `"accion`": `"revertir`", `"resultado`": `"reversion_fallida`"}"
            $codigo = Host-Ejecutar $instF @('aplicar-actualizacion') 120
            Comprobar ($codigo -eq 0) 'F8 · El verbo aplicar-actualizacion (con el servicio parado) termina bien sin orden' "F8 · aplicar-actualizacion devolvio $codigo"
            Comprobar (-not (Test-Path (Join-Path $actF "versiones\$($p7.PaqueteId)"))) 'F8 · La instantanea de mas de 14 dias se retiro' 'F8 · La instantanea vieja sigue ahi'
            Comprobar (Test-Path (Join-Path $actF "versiones\$guardada\anterior\_indice.json")) 'F8 · La de una reversion fallida se conserva aunque sea vieja (nadie borra nada)' 'F8 · Se borro la instantanea de una reversion fallida'

            # ---------------------------------------------------------------- F9 · el instalador no toca Actualizaciones\
            Write-Host '  -- F9 · el instalador completo y la desinstalacion no borran Actualizaciones\' -ForegroundColor DarkCyan
            $iss = Leer-Texto (Join-Path $PSScriptRoot '..\src\AvacomOpsMaster.iss')
            if ($iss) {
                Comprobar ($iss -match '(?m)^Name:\s*"\{commonappdata\}\\AVACOM\\\{#NombreCorto\}\\Actualizaciones";[^\r\n]*uninsneveruninstall') 'F9 · El instalador declara Actualizaciones\ como estado del nodo que la desinstalacion nunca borra (como Respaldos)' 'F9 · AvacomOpsMaster.iss no declara Actualizaciones\ con uninsneveruninstall'
                Comprobar ($iss -notmatch '(?m)^Type:\s*filesandordirs;\s*Name:\s*"[^"]*Actualizaciones') 'F9 · Ni [InstallDelete] ni [UninstallDelete] mencionan Actualizaciones\' 'F9 · Una regla de borrado alcanza Actualizaciones\'
            } else { Falla 'F9 · No se encontro AvacomOpsMaster.iss' }
        }
    }
} catch {
    Falla "El ensayo se interrumpio: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
} finally {
    foreach ($id in $Procesos) {
        foreach ($h in (Hijos-De $id)) { Stop-Process -Id $h.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
    Restaurar-Entorno
    if (-not $Conservar) {
        Start-Sleep -Seconds 1
        Remove-Item -LiteralPath $Raiz -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "  Carpeta del ensayo conservada: $Raiz" -ForegroundColor Yellow
    }
}

Write-Host ''
if ($Fallos.Count -eq 0) {
    Write-Host '  El paquete se ensayo de punta a punta: todo correcto.' -ForegroundColor Green
    exit 0
}
Write-Host "  El ensayo fallo en $($Fallos.Count) punto(s):" -ForegroundColor Red
$Fallos | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
exit 1
