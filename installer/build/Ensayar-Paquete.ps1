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
    [switch] $Conservar
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
}

function Puerto-Libre {
    $oyente = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $oyente.Start(); $puerto = $oyente.LocalEndpoint.Port; $oyente.Stop()
    return $puerto
}

# Peticion HTTP que no lanza por el codigo de estado; devuelve Estado, Cuerpo y Json.
function Pedir {
    param([string] $Url, [string] $Metodo = 'GET', [string] $Cuerpo = '', [int] $Segundos = 20)
    $r = [pscustomobject]@{ Estado = 0; Cuerpo = ''; Json = $null; Error = '' }
    $respuesta = $null
    try {
        $p = [System.Net.HttpWebRequest]::Create($Url)
        $p.Method = $Metodo; $p.Timeout = $Segundos * 1000; $p.ReadWriteTimeout = $Segundos * 1000; $p.Proxy = $null
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

try {
    Write-Host ''
    Write-Host "  Ensayo del paquete en $Raiz" -ForegroundColor White
    New-Item -ItemType Directory -Force $Raiz | Out-Null
    $backendNuevo = Join-Path $Staging 'Backend'
    $runtimeNuevo = Join-Path $Staging 'Runtime'
    foreach ($necesario in @((Join-Path $backendNuevo 'manage.py'), (Join-Path $runtimeNuevo 'Avacom.Ops.Host.exe'), (Join-Path $runtimeNuevo 'Python\python.exe'))) {
        if (-not (Test-Path $necesario)) { throw "El paquete esta incompleto: falta $necesario." }
    }

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
        $auditoria = Pedir "http://127.0.0.1:$puertoA/api/auditoria/estado/"
        Comprobar ($auditoria.Estado -in 200, 401, 403) 'El modulo de auditoria esta en el paquete (/api/auditoria/ responde)' "/api/auditoria/estado/ respondio $($auditoria.Estado)"
        $evaluacion = Pedir "http://127.0.0.1:$puertoA/api/evaluacion/asignaciones/"
        Comprobar ($evaluacion.Estado -ne 404 -and $evaluacion.Estado -ne 500) "El modulo de evaluacion esta en el paquete (respondio $($evaluacion.Estado))" "/api/evaluacion/ respondio $($evaluacion.Estado)"
        $estudio = Pedir "http://127.0.0.1:$puertoA/api/modo-estudio/estado/"
        Comprobar ($estudio.Estado -in 200, 401, 403) "El modulo de modo estudio esta en el paquete (respondio $($estudio.Estado))" "/api/modo-estudio/estado/ respondio $($estudio.Estado)"

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

        $instalacion = Python-Del-Nodo $instB $datosB @('manage.py', 'acceso_instalar', '--codigo', 'ENSAYO', '--nombre', 'Ensayo del instalador', '--pais', 'CO',
            '--admin-dni', '1000000001', '--admin-nombres', 'Ensayo', '--admin-apellidos', 'Del Instalador', '--admin-password', 'Ensayo.2026!')
        Comprobar ($instalacion.Codigo -eq 0) 'Se creo la organizacion y el administrador con el backend viejo' "acceso_instalar fallo: $($instalacion.Salida)"
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
            # Un nodo que ya tenia organizacion antes del PIN maestro no lo tiene tras actualizar: lo dice el resumen que lee la pantalla final.
            Comprobar ((Leer-Texto (Join-Path $datosB 'Logs\resumen-nodo.txt')) -match '(?m)^pin_maestro=sin_configurar') 'El nodo actualizado avisa que le falta el PIN maestro (se configura en OPS, Seguridad del aula)' 'El resumen del nodo actualizado no dice pin_maestro=sin_configurar'
            $login = Pedir "http://127.0.0.1:$puertoB/api/acceso/sesiones/" 'POST' '{"identificador":"1000000001","secreto":"Ensayo.2026!"}' 30
            Comprobar ($login.Estado -eq 200) 'El administrador inicia sesion tras actualizar: sus datos siguen legibles con las mismas claves' "El inicio de sesion respondio $($login.Estado): $($login.Cuerpo)"
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
