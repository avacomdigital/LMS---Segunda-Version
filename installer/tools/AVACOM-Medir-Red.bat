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
<#
.SYNOPSIS
    Mide la red del aula: latencia, jitter, pérdida, velocidad de descarga y de carga entre este equipo y el nodo de AVACOM OPS, pasando por el router.

.DESCRIPTION
    Qué responde, en este orden:
      1. Qué equipo y qué enlace es este (Wi-Fi o cable, velocidad negociada, señal) y quién es el router.
      2. Latencia, jitter y pérdida hasta el router y hasta el nodo (en reposo y BAJO CARGA: el aviso «cambió la lámina» viaja por el mismo camino).
      3. Cuánto baja y cuánto sube de verdad entre este equipo y el nodo con 1, 4 y 8 conexiones a la vez: la capacidad del router o punto de acceso.
      4. (Opcional) Internet: lo que el router le da al proveedor. El aula NO lo necesita: las tabletas sólo hablan con el nodo.
      5. Qué significa eso para 35 tabletas: cuánto le tocaría a cada una y cuánto tardaría en llegar una lámina con video a todas.

    DÓNDE correrlo: en una laptop conectada por WIFI al mismo router que las tabletas, con el nodo (OPS) encendido y, si se puede, por CABLE. Así el camino
    medido es el mismo que el de una tableta. Si se corre en el propio equipo del nodo sólo se miden el router y, si hay, Internet (el caudal con el nodo es
    interno y no dice nada del router).

    No instala nada, no cambia ninguna configuración y no toca el expediente. Los únicos datos que viajan son ceros: no hay nada del aula en la medición.
    El nodo atiende las mediciones en /api/diagnostico/velocidad/ (se apagan con AVACOM_DIAGNOSTICO_VELOCIDAD=0).

.PARAMETER Nodo
    Dirección del nodo (192.168.1.10, 192.168.1.10:8000 o http://192.168.1.10:8000). Vacía: lo busca solo en la red de este equipo.
.PARAMETER Segundos
    Duración de cada prueba de caudal. 12 por omisión; -Rapido la baja a 5.
.PARAMETER Flujos
    Conexiones simultáneas de la prueba de caudal. 1, 4 y 8 por omisión (la tableta real abre varias a la vez).
.PARAMETER Internet
    Fuerza la prueba contra Internet. Sin este parámetro se hace sola si hay salida a Internet; -SinInternet la omite.
.PARAMETER Abrir
    Al terminar abre el informe.

.NOTES
    Códigos de salida: 0 = la red aguanta 35 tabletas · 2 = aguanta con avisos · 1 = no aguanta o no se pudo medir.
    Compatible con Windows PowerShell 5.1 y PowerShell 7.
#>
[CmdletBinding()]
param(
    [string] $Nodo = '',
    [int] $Puerto = 8000,
    [int] $Segundos = 12,
    [int[]] $Flujos = @(1, 4, 8),
    [switch] $Internet,
    [switch] $SinInternet,
    [switch] $Rapido,
    [switch] $Abrir,
    [string] $Informe = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
if ($Rapido) { $Segundos = 5 }
$Tabletas = 35
$cultura = [System.Globalization.CultureInfo]::CurrentCulture
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor [System.Net.SecurityProtocolType]::Tls12 } catch { }
[System.Net.ServicePointManager]::DefaultConnectionLimit = 256
[System.Net.ServicePointManager]::Expect100Continue = $false
Add-Type -AssemblyName System.Net.Http

# ---------------------------------------------------------------------- salida
$script:Lineas = New-Object System.Collections.Generic.List[string]
$script:Avisos = New-Object System.Collections.Generic.List[string]
$script:Fallos = New-Object System.Collections.Generic.List[string]
$script:Datos = [ordered]@{}

function Texto([string] $t, [string] $color = '') {
    $script:Lineas.Add($t)
    if ($color) { Write-Host $t -ForegroundColor $color } else { Write-Host $t }
}
function Titulo([string] $t) { Texto ''; Texto ('== ' + $t) 'Cyan' }
function Bien([string] $t)   { Texto ('  [ OK ] ' + $t) 'Green' }
function Aviso([string] $t)  { $script:Avisos.Add($t); Texto ('  [AVISO] ' + $t) 'Yellow' }
function Mal([string] $t)    { $script:Fallos.Add($t); Texto ('  [ MAL ] ' + $t) 'Red' }
function Dato([string] $t)   { Texto ('         ' + $t) }
function N([double] $v, [int] $dec = 1) { [string]::Format($cultura, ('{0:F' + $dec + '}'), $v) }

# ------------------------------------------------------------------ estadística
function Percentil($ordenado, [double] $p) {
    $cuantos = @($ordenado).Count
    $i = [int][Math]::Ceiling($p / 100.0 * $cuantos) - 1
    if ($i -lt 0) { $i = 0 }
    if ($i -ge $cuantos) { $i = $cuantos - 1 }
    @($ordenado)[$i]
}

function Estadistica([double[]] $v) {
    if (-not $v -or $v.Count -eq 0) { return $null }
    $o = @($v | Sort-Object)
    $jit = 0.0
    if ($v.Count -gt 1) { $s = 0.0; for ($i = 1; $i -lt $v.Count; $i++) { $s += [Math]::Abs($v[$i] - $v[$i - 1]) }; $jit = $s / ($v.Count - 1) }
    [pscustomobject]@{ N = $o.Count; Min = $o[0]; Prom = ($v | Measure-Object -Average).Average; P50 = (Percentil $o 50); P95 = (Percentil $o 95); Max = $o[$o.Count - 1]; Jitter = $jit }
}

function Linea-Latencia($e, [int] $enviados, [int] $perdidos) {
    $perd = if ($enviados -gt 0) { 100.0 * $perdidos / $enviados } else { 100.0 }
    if (-not $e) { return ('sin respuesta · pérdida {0} %' -f (N $perd 0)) }
    ('mín {0} · prom {1} · p95 {2} · máx {3} ms · jitter {4} ms · pérdida {5} %' -f (N $e.Min), (N $e.Prom), (N $e.P95), (N $e.Max), (N $e.Jitter), (N $perd 0))
}

function Ping-Serie([string] $destino, [int] $n, [int] $esperaMs = 1000, [int] $pausaMs = 80) {
    $p = New-Object System.Net.NetworkInformation.Ping
    $ms = New-Object System.Collections.Generic.List[double]
    $perdidos = 0
    for ($i = 0; $i -lt $n; $i++) {
        try {
            $r = $p.Send($destino, $esperaMs)
            if ($r.Status -eq 'Success') { $ms.Add([double]$r.RoundtripTime) } else { $perdidos++ }
        } catch { $perdidos++ }
        Start-Sleep -Milliseconds $pausaMs
    }
    [pscustomobject]@{ Enviados = $n; Perdidos = $perdidos; Muestras = $ms.ToArray(); Estadistica = (Estadistica $ms.ToArray()) }
}

# -------------------------------------------------------------------- HTTP breve
function Cliente-Http([int] $segundos = 15) {
    $h = New-Object System.Net.Http.HttpClientHandler
    $h.UseProxy = $false
    $c = New-Object System.Net.Http.HttpClient($h)
    $c.Timeout = [TimeSpan]::FromSeconds($segundos)
    $c
}

function Http-Serie([string] $url, [int] $n, [int] $pausaMs = 100) {
    $cli = Cliente-Http 3
    $ms = New-Object System.Collections.Generic.List[double]
    $perdidos = 0
    for ($i = 0; $i -lt $n; $i++) {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $r = $cli.GetAsync($url).GetAwaiter().GetResult()
            if ($r.IsSuccessStatusCode) { $ms.Add($sw.Elapsed.TotalMilliseconds) } else { $perdidos++ }
            $r.Dispose()
        } catch { $perdidos++ }
        Start-Sleep -Milliseconds $pausaMs
    }
    $cli.Dispose()
    [pscustomobject]@{ Enviados = $n; Perdidos = $perdidos; Muestras = $ms.ToArray(); Estadistica = (Estadistica $ms.ToArray()) }
}

# ------------------------------------------------------------------------ caudal
# Cada conexión es un runspace que baja (o sube) bytes sin parar; cada una cuenta lo suyo en su propia casilla y quien mide muestrea la suma cada segundo.
$trabajador = {
    param($urlDescarga, $urlCarga, $modo, $i, $contador, $parar, $errores, $mbCarga)
    try {
        Add-Type -AssemblyName System.Net.Http
        $buf = New-Object byte[] 262144
        if ($modo -eq 'descarga') {
            $h = New-Object System.Net.Http.HttpClientHandler
            $h.UseProxy = $false
            $cli = New-Object System.Net.Http.HttpClient($h)
            $cli.Timeout = [TimeSpan]::FromSeconds(120)
            while (-not $parar[0]) {
                $resp = $cli.GetAsync($urlDescarga, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
                if (-not $resp.IsSuccessStatusCode) { $errores.Enqueue('HTTP ' + [int]$resp.StatusCode); $resp.Dispose(); Start-Sleep -Milliseconds 400; continue }
                $st = $resp.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
                while (-not $parar[0]) {
                    $n = $st.Read($buf, 0, $buf.Length)
                    if ($n -le 0) { break }
                    $contador[$i] += $n
                }
                $st.Dispose(); $resp.Dispose()
            }
        } else {
            $total = [long]$mbCarga * 1024 * 1024
            while (-not $parar[0]) {
                $req = [System.Net.HttpWebRequest]::Create($urlCarga)
                $req.Method = 'POST'
                $req.Proxy = $null
                $req.ContentType = 'application/octet-stream'
                $req.AllowWriteStreamBuffering = $false
                $req.ContentLength = $total
                $req.Timeout = 60000
                $req.ReadWriteTimeout = 60000
                $s = $req.GetRequestStream()
                $enviado = 0L
                while ($enviado -lt $total -and -not $parar[0]) {
                    $n = [int][Math]::Min($buf.Length, $total - $enviado)
                    $s.Write($buf, 0, $n)
                    $enviado += $n
                    $contador[$i] += $n
                }
                if ($enviado -lt $total) { $req.Abort(); break }
                $s.Close()
                $resp = $req.GetResponse()
                $resp.Close()
            }
        }
    } catch { $errores.Enqueue($_.Exception.Message) }
}

function Medir-Caudal([string] $UrlDescarga, [string] $UrlCarga, [string] $Modo, [int] $NFlujos, [int] $Duracion, [string] $SondaPing = '') {
    $contador = New-Object 'long[]' $NFlujos
    $parar = New-Object 'bool[]' 1
    $errores = New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'
    $pool = [runspacefactory]::CreateRunspacePool(1, $NFlujos + 1)
    $pool.Open()
    $trabajos = @()
    for ($i = 0; $i -lt $NFlujos; $i++) {
        $ps = [powershell]::Create()
        $ps.RunspacePool = $pool
        [void]$ps.AddScript($trabajador).AddArgument($UrlDescarga).AddArgument($UrlCarga).AddArgument($Modo).AddArgument($i).AddArgument($contador).AddArgument($parar).AddArgument($errores).AddArgument(16)
        $trabajos += [pscustomobject]@{ Ps = $ps; Estado = $ps.BeginInvoke() }
    }
    # La misma conexión que el aviso «cambió la lámina»: cuánto tarda una petición mínima MIENTRAS el caudal está al máximo.
    $sonda = $null
    if ($SondaPing) {
        $sondaPs = [powershell]::Create()
        $sondaPs.RunspacePool = $pool
        [void]$sondaPs.AddScript({
            param($url, $parar, $salida)
            try {
                Add-Type -AssemblyName System.Net.Http
                $h = New-Object System.Net.Http.HttpClientHandler; $h.UseProxy = $false
                $cli = New-Object System.Net.Http.HttpClient($h); $cli.Timeout = [TimeSpan]::FromSeconds(10)
                while (-not $parar[0]) {
                    $sw = [Diagnostics.Stopwatch]::StartNew()
                    try { $r = $cli.GetAsync($url).GetAwaiter().GetResult(); $r.Dispose(); $salida.Enqueue($sw.Elapsed.TotalMilliseconds) } catch { $salida.Enqueue(-1.0) }
                    Start-Sleep -Milliseconds 250
                }
            } catch { }
        }).AddArgument($SondaPing).AddArgument($parar)
        $salidaSonda = New-Object 'System.Collections.Concurrent.ConcurrentQueue[double]'
        [void]$sondaPs.AddArgument($salidaSonda)
        $sonda = [pscustomobject]@{ Ps = $sondaPs; Estado = $sondaPs.BeginInvoke(); Salida = $salidaSonda }
    }
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    $porSegundo = New-Object System.Collections.Generic.List[double]
    $previo = 0L
    $tPrevio = 0.0
    for ($s = 1; $s -le $Duracion; $s++) {
        $falta = 1000 * $s - $reloj.ElapsedMilliseconds
        if ($falta -gt 0) { Start-Sleep -Milliseconds $falta }
        $suma = 0L; foreach ($c in $contador) { $suma += $c }
        $t = $reloj.Elapsed.TotalSeconds
        $porSegundo.Add((($suma - $previo) * 8.0 / 1000000.0) / [Math]::Max(0.001, $t - $tPrevio))
        $previo = $suma; $tPrevio = $t
    }
    $totalBytes = $previo
    $seg = $reloj.Elapsed.TotalSeconds
    $parar[0] = $true
    foreach ($t in $trabajos) { try { [void]$t.Ps.EndInvoke($t.Estado) } catch { } ; $t.Ps.Dispose() }
    $enCarga = @()
    if ($sonda) { try { [void]$sonda.Ps.EndInvoke($sonda.Estado) } catch { }; $sonda.Ps.Dispose(); $enCarga = @($sonda.Salida.ToArray()) }
    $pool.Close(); $pool.Dispose()
    $errs = @(); $e = $null; while ($errores.TryDequeue([ref]$e)) { $errs += $e }
    # El primer segundo es el arranque lento de TCP: la mediana de los demás es lo que el enlace sostiene.
    $estables = if ($porSegundo.Count -gt 3) { $porSegundo.GetRange(1, $porSegundo.Count - 1).ToArray() } else { $porSegundo.ToArray() }
    $est = Estadistica $estables
    [pscustomobject]@{
        Flujos = $NFlujos; Segundos = $seg; Bytes = $totalBytes
        Promedio = ($totalBytes * 8.0 / 1000000.0) / [Math]::Max(0.001, $seg)
        Sostenido = $(if ($est) { $est.P50 } else { 0.0 }); Minimo = $(if ($est) { $est.Min } else { 0.0 }); Maximo = $(if ($est) { $est.Max } else { 0.0 })
        Errores = $errs; SondaBajoCarga = $enCarga
    }
}

# --------------------------------------------------------------------- el equipo
function Direccion-Local {
    $ruta = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Where-Object { $_.NextHop -ne '0.0.0.0' } |
        Sort-Object { $_.RouteMetric + $_.InterfaceMetric } | Select-Object -First 1
    if (-not $ruta) { return $null }
    $ip = Get-NetIPAddress -InterfaceIndex $ruta.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1
    $ad = Get-NetAdapter -InterfaceIndex $ruta.InterfaceIndex -ErrorAction SilentlyContinue
    [pscustomobject]@{ Router = $ruta.NextHop; Ip = $(if ($ip) { $ip.IPAddress } else { '' }); Adaptador = $ad; Indice = $ruta.InterfaceIndex }
}

function Datos-Wifi {
    $salida = @{}
    try {
        $lineas = & netsh.exe wlan show interfaces 2>$null
        foreach ($l in $lineas) {
            if ($l -match '^\s*(?<k>[^:]+?)\s*:\s*(?<v>.+?)\s*$') {
                $k = $Matches['k']; $v = $Matches['v']
                if ($k -match '^(SSID)$') { $salida['SSID'] = $v }
                elseif ($k -match '^BSSID$') { $salida['BSSID'] = $v }
                elseif ($k -match 'radio|Radio') { $salida['Radio'] = $v }
                elseif ($k -match '^(Canal|Channel)$') { $salida['Canal'] = $v }
                elseif ($k -match 'Banda|Band') { $salida['Banda'] = $v }
                elseif ($k -match 'recepci|Receive') { $salida['Recepcion'] = $v }
                elseif ($k -match 'transmisi|Transmit') { $salida['Transmision'] = $v }
                elseif ($k -match '^(Se.al|Signal)$') { $salida['Senal'] = $v }
            }
        }
    } catch { }
    $salida
}

function Es-Local([string] $ip) {
    if ($ip -in @('127.0.0.1', 'localhost', '::1')) { return $true }
    try { return [bool](Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -eq $ip }) } catch { return $false }
}

function Buscar-Nodo([string] $ipLocal, [int] $puerto) {
    if (-not $ipLocal) { return @() }
    $red = $ipLocal -replace '\.\d+$', ''
    $tareas = foreach ($i in 1..254) {
        $c = New-Object System.Net.Sockets.TcpClient
        [pscustomobject]@{ Ip = "$red.$i"; C = $c; T = $c.ConnectAsync("$red.$i", $puerto) }
    }
    try { [void][System.Threading.Tasks.Task]::WaitAll(@($tareas | ForEach-Object { $_.T }), 1800) } catch { }
    $hallados = @()
    foreach ($t in $tareas) {
        $abierto = ($t.T.Status -eq 'RanToCompletion' -and $t.C.Connected)
        try { $t.C.Close() } catch { }
        if (-not $abierto) { continue }
        try {
            $r = Invoke-WebRequest -Uri "http://$($t.Ip):$puerto/health/" -UseBasicParsing -TimeoutSec 4
            if ($r.Content -match 'avacom-lms-backend') { $hallados += $t.Ip }
        } catch { }
    }
    $hallados
}

function Ruta-Informe {
    if ($Informe) { return $Informe }
    $carpeta = [Environment]::GetFolderPath('Desktop')
    if (-not $carpeta -or -not (Test-Path $carpeta)) { $carpeta = $env:TEMP }
    Join-Path $carpeta ('AVACOM-Medicion-Red-{0}.txt' -f (Get-Date -Format 'yyyyMMdd-HHmm'))
}

# ===================================================================== el informe
Texto ''
Texto '  AVACOM · Medición de la red del aula' 'White'
Texto ('  {0}  ·  equipo {1}  ·  35 tabletas de referencia' -f (Get-Date -Format 'yyyy-MM-dd HH:mm'), $env:COMPUTERNAME)

# --- 1. este equipo y el router
Titulo '1. Este equipo y el router'
$local = $null
try { $local = Direccion-Local } catch { }
$router = ''
$ipLocal = ''
$esWifi = $false
if ($local -and $local.Adaptador) {
    $ad = $local.Adaptador
    $router = $local.Router; $ipLocal = $local.Ip
    $esWifi = ("$($ad.PhysicalMediaType)" -match '802\.11|Wireless|Wi-?Fi') -or ("$($ad.InterfaceDescription)" -match 'Wi-?Fi|Wireless|802\.11')
    Dato ('Adaptador: {0} ({1}) · {2} · velocidad negociada {3}' -f $ad.Name, $ad.InterfaceDescription, $(if ($esWifi) { 'Wi-Fi' } else { 'cable' }), $ad.LinkSpeed)
    Dato ('Mi dirección: {0} · router (puerta de enlace): {1}' -f $ipLocal, $router)
    $script:Datos['adaptador'] = [ordered]@{ nombre = $ad.Name; wifi = $esWifi; velocidad = "$($ad.LinkSpeed)"; ip = $ipLocal; router = $router }
    if ($esWifi) {
        $w = Datos-Wifi
        if ($w.Count -gt 0) {
            Dato ('Wi-Fi: {0} · radio {1} · canal {2} · señal {3} · recibe {4} Mbps · envía {5} Mbps' -f $w['SSID'], $w['Radio'], $w['Canal'], $w['Senal'], $w['Recepcion'], $w['Transmision'])
            $script:Datos['wifi'] = $w
            $senal = 0; if ("$($w['Senal'])" -match '(\d+)') { $senal = [int]$Matches[1] }
            if ($senal -gt 0 -and $senal -lt 50) { Aviso ('La señal Wi-Fi de este equipo es baja ({0} %): acércate al punto de acceso para medir el enlace, no la distancia.' -f $senal) }
            elseif ($senal -ge 50) { Bien ('Señal Wi-Fi {0} %' -f $senal) }
            if ("$($w['Radio'])" -match '802\.11(b|g|n)\b' -and "$($w['Radio'])" -notmatch 'ac|ax') { Aviso ('El enlace es {0}: un punto de acceso 802.11ac/ax (5 GHz) rinde mucho más con 35 tabletas.' -f $w['Radio']) }
            if ("$($w['Banda'])$($w['Canal'])" -match '^\s*(\d{1,2})\s*$' -and [int]$Matches[1] -le 14) { Aviso 'El enlace está en 2,4 GHz (canal 1–14): con 35 tabletas conviene la banda de 5 GHz.' }
        }
    } else {
        Bien 'Este equipo va por cable: la medición es la del router y la del nodo, sin el Wi-Fi de por medio.'
    }
} else {
    Mal 'Este equipo no tiene salida de red (no hay puerta de enlace). ¿Está conectado al router del aula?'
}

# --- 2. latencia hasta el router
Titulo '2. Latencia hasta el router'
if ($router) {
    $pr = Ping-Serie $router 60 1000 60
    $e = $pr.Estadistica
    Dato ('Router {0}: {1}' -f $router, (Linea-Latencia $e $pr.Enviados $pr.Perdidos))
    $script:Datos['latencia_router'] = [ordered]@{ ip = $router; enviados = $pr.Enviados; perdidos = $pr.Perdidos; prom_ms = $(if ($e) { [Math]::Round($e.Prom, 1) } else { $null }); p95_ms = $(if ($e) { $e.P95 } else { $null }); max_ms = $(if ($e) { $e.Max } else { $null }) }
    if (-not $e) { Aviso 'El router no contesta a ping (algunos lo bloquean). No es un fallo: se mide la latencia contra el nodo más abajo.' }
    else {
        $perd = 100.0 * $pr.Perdidos / $pr.Enviados
        # Un router atiende el ping con la prioridad más baja: perder algunos no es perder datos de verdad (eso lo dice la medición HTTP contra el nodo).
        if ($perd -ge 10) { Mal ('Se pierde el {0} % de los paquetes hasta el router: la tableta pierde avisos y recarga medios.' -f (N $perd 0)) }
        elseif ($perd -ge 1) { Aviso ('Se pierde el {0} % de los pings hasta el router (algunos routers los descartan a propósito; mira la medición HTTP contra el nodo).' -f (N $perd 0)) }
        if ($e.P95 -gt 60) { Mal ('p95 de {0} ms hasta el router: el enlace es lento o está saturado.' -f (N $e.P95 0)) }
        elseif ($e.P95 -gt 25) { Aviso ('p95 de {0} ms hasta el router: aceptable para el aula, justo para varias tabletas.' -f (N $e.P95 0)) }
        elseif ($perd -eq 0) { Bien ('Latencia al router sana (p95 {0} ms, sin pérdidas).' -f (N $e.P95 0)) }
    }
} else { Dato 'Sin router que medir.' }

# --- 3. el nodo
Titulo '3. El nodo (AVACOM OPS)'
$ipNodo = ''
$base = ''
if ($Nodo) {
    $t = $Nodo.Trim() -replace '^https?://', '' -replace '/.*$', ''
    if ($t -match '^(?<h>[^:]+):(?<p>\d+)$') { $ipNodo = $Matches['h']; $Puerto = [int]$Matches['p'] } else { $ipNodo = $t }
} elseif ($env:AVACOM_NODO) {
    $ipNodo = $env:AVACOM_NODO.Trim()
} else {
    Dato ('Buscando el nodo en {0}.x (puerto {1})…' -f ($ipLocal -replace '\.\d+$', ''), $Puerto)
    $hallados = @(Buscar-Nodo $ipLocal $Puerto)
    if ($hallados.Count -gt 0) {
        $ipNodo = $hallados[0]
        Bien ('Nodo encontrado: {0}{1}' -f $ipNodo, $(if ($hallados.Count -gt 1) { ' (hay más: ' + (($hallados | Select-Object -Skip 1) -join ', ') + '; usa -Nodo para elegir)' } else { '' }))
    } elseif ([Environment]::UserInteractive -and -not $env:AVACOM_SIN_PREGUNTAR) {
        try {
            $r = Read-Host '  No encontré el nodo solo. Escribe su dirección (ej. 192.168.1.10) o deja vacío para omitirlo'
            if ($r) { $ipNodo = $r.Trim() -replace '^https?://', '' -replace '/.*$', ''; if ($ipNodo -match '^(?<h>[^:]+):(?<p>\d+)$') { $ipNodo = $Matches['h']; $Puerto = [int]$Matches['p'] } }
        } catch { }
    }
}
$lan = $false
$modoNodo = $false      # verdadero: este equipo ES el nodo; el caudal mide al servidor, no al router
if ($ipNodo) {
    $base = "http://${ipNodo}:$Puerto"
    $nodoLocal = Es-Local $ipNodo
    $script:Datos['nodo'] = [ordered]@{ direccion = $base; es_este_equipo = $nodoLocal }
    $vivo = $false
    try {
        $cli = Cliente-Http 5
        $r = $cli.GetAsync("$base/api/diagnostico/velocidad/ping/").GetAwaiter().GetResult()
        $vivo = $r.IsSuccessStatusCode
        if ($r.StatusCode -eq 404) { Mal 'El nodo contesta pero no tiene los puntos de medición: es un OPS anterior a la 2.5.1. Actualiza el nodo y vuelve a medir.' }
        elseif ($r.StatusCode -eq 429) { Aviso 'El nodo está atendiendo otras mediciones; se reintentará.'; $vivo = $true }
        $r.Dispose(); $cli.Dispose()
    } catch { Mal ('No pude hablar con el nodo en {0}: {1}' -f $base, $_.Exception.Message) }
    if ($vivo) {
        $lan = $true
        if ($nodoLocal) {
            $modoNodo = $true
            Dato 'El nodo es ESTE mismo equipo: la prueba de caudal mide cuánto puede ENTREGAR el nodo sin red de por medio (su techo). Para medir el router y el Wi-Fi corre este .bat desde una laptop conectada por Wi-Fi.'
        } else {
            $pn = Ping-Serie $ipNodo 40 1000 60
            Dato ('Ping (ICMP) al nodo {0}: {1}' -f $ipNodo, (Linea-Latencia $pn.Estadistica $pn.Enviados $pn.Perdidos))
            if ($pn.Perdidos -eq $pn.Enviados) { Dato '(el equipo del nodo no responde a ping; es normal si su cortafuegos lo bloquea. Lo que cuenta es la petición HTTP, abajo)' }
        }
        $hs = Http-Serie "$base/api/diagnostico/velocidad/ping/" 80 80
        $eh = $hs.Estadistica
        Dato ('Petición HTTP al nodo: {0}' -f (Linea-Latencia $eh $hs.Enviados $hs.Perdidos))
        $script:Datos['latencia_nodo_http'] = [ordered]@{ enviados = $hs.Enviados; perdidos = $hs.Perdidos; prom_ms = $(if ($eh) { [Math]::Round($eh.Prom, 1) } else { $null }); p95_ms = $(if ($eh) { $eh.P95 } else { $null }); max_ms = $(if ($eh) { $eh.Max } else { $null }) }
        if ($eh) {
            if ($hs.Perdidos -gt 2) { Mal ('Fallaron {0} de {1} peticiones al nodo.' -f $hs.Perdidos, $hs.Enviados) }
            if ($eh.P95 -gt 150) { Mal ('p95 de {0} ms al nodo: el aviso «cambió la lámina» llegaría tarde.' -f (N $eh.P95 0)) }
            elseif ($eh.P95 -gt 60) { Aviso ('p95 de {0} ms al nodo: aceptable en reposo; mira la latencia bajo carga más abajo.' -f (N $eh.P95 0)) }
            else { Bien ('Latencia al nodo sana (p95 {0} ms).' -f (N $eh.P95 0)) }
        }
    } else { $lan = $false }
} else {
    Aviso 'No hay nodo que medir: sólo se midió el router. Enciende AVACOM OPS o pasa su dirección: AVACOM-Medir-Red.bat 192.168.1.10'
}

# --- 4. caudal con el nodo
$mejorBaja = 0.0
$mejorSube = 0.0
$bajoCarga = $null
if ($lan) {
    if ($modoNodo) { Titulo ('4. Capacidad del nodo, sin red de por medio ({0} s por prueba)' -f $Segundos) }
    else { Titulo ('4. Velocidad entre este equipo y el nodo, pasando por el router ({0} s por prueba)' -f $Segundos) }
    $urlD = "$base/api/diagnostico/velocidad/descarga/?mb=64"
    $urlU = "$base/api/diagnostico/velocidad/carga/"
    $resultadosBaja = @()
    foreach ($f in $Flujos) {
        $sonda = $(if ($f -eq ($Flujos | Measure-Object -Maximum).Maximum) { "$base/api/diagnostico/velocidad/ping/" } else { '' })
        $r = Medir-Caudal $urlD $urlU 'descarga' $f $Segundos $sonda
        $resultadosBaja += $r
        Dato ('BAJADA con {0} conexión(es): {1} Mbps sostenidos (prom {2} · mín {3} · máx {4})  ≈ {5} MB/s' -f $f, (N $r.Sostenido 0), (N $r.Promedio 0), (N $r.Minimo 0), (N $r.Maximo 0), (N ($r.Sostenido / 8) 1))
        if ($r.Errores.Count -gt 0) { Aviso ('Errores en la bajada con {0} conexión(es): {1}' -f $f, (($r.Errores | Select-Object -Unique -First 2) -join ' | ')) }
        if ($r.Sostenido -gt $mejorBaja) { $mejorBaja = $r.Sostenido }
        if ($sonda) { $bajoCarga = $r.SondaBajoCarga }
    }
    $resultadosSube = @()
    foreach ($f in @($Flujos | Where-Object { $_ -le 4 })) {
        $r = Medir-Caudal $urlD $urlU 'carga' $f $Segundos ''
        $resultadosSube += $r
        Dato ('SUBIDA con {0} conexión(es): {1} Mbps sostenidos (prom {2} · mín {3} · máx {4})  ≈ {5} MB/s' -f $f, (N $r.Sostenido 0), (N $r.Promedio 0), (N $r.Minimo 0), (N $r.Maximo 0), (N ($r.Sostenido / 8) 1))
        if ($r.Errores.Count -gt 0) { Aviso ('Errores en la subida con {0} conexión(es): {1}' -f $f, (($r.Errores | Select-Object -Unique -First 2) -join ' | ')) }
        if ($r.Sostenido -gt $mejorSube) { $mejorSube = $r.Sostenido }
    }
    $script:Datos['caudal_lan'] = [ordered]@{
        bajada = @($resultadosBaja | ForEach-Object { [ordered]@{ flujos = $_.Flujos; sostenido_mbps = [Math]::Round($_.Sostenido, 1); promedio_mbps = [Math]::Round($_.Promedio, 1); minimo_mbps = [Math]::Round($_.Minimo, 1) } })
        subida = @($resultadosSube | ForEach-Object { [ordered]@{ flujos = $_.Flujos; sostenido_mbps = [Math]::Round($_.Sostenido, 1); promedio_mbps = [Math]::Round($_.Promedio, 1); minimo_mbps = [Math]::Round($_.Minimo, 1) } })
    }
    if ($bajoCarga -and $bajoCarga.Count -gt 3) {
        $ok = @($bajoCarga | Where-Object { $_ -ge 0 })
        $perdidosCarga = $bajoCarga.Count - $ok.Count
        $ec = Estadistica ([double[]]$ok)
        if ($ec) {
            Dato ('LATENCIA BAJO CARGA (con la bajada al máximo): {0}' -f (Linea-Latencia $ec $bajoCarga.Count $perdidosCarga))
            $script:Datos['latencia_bajo_carga'] = [ordered]@{ muestras = $bajoCarga.Count; perdidas = $perdidosCarga; p50_ms = [Math]::Round($ec.P50, 1); p95_ms = [Math]::Round($ec.P95, 1); max_ms = [Math]::Round($ec.Max, 1) }
            if ($ec.P95 -gt 1000) { Mal ('Bajo carga el nodo tarda hasta {0} ms en contestar algo mínimo: con la red llena, el cambio de lámina y los avisos llegarían con segundos de retraso.' -f (N $ec.P95 0)) }
            elseif ($ec.P95 -gt 300) { Aviso ('Bajo carga la latencia sube a p95 {0} ms: los avisos se retrasan cuando la red está llena de medios.' -f (N $ec.P95 0)) }
            else { Bien ('Con la red llena la latencia se mantiene (p95 {0} ms).' -f (N $ec.P95 0)) }
        }
    }
    if ($mejorBaja -lt 1) { Mal 'No se pudo medir la bajada (0 Mbps): revisa que el puerto del nodo esté abierto en el cortafuegos del equipo del nodo.' }
}

# --- 5. Internet (opcional)
$mejorWan = 0.0
$mejorWanSube = 0.0
$probarInternet = $false
if ($Internet) { $probarInternet = $true }
elseif (-not $SinInternet) {
    try { $cli = Cliente-Http 4; $r = $cli.GetAsync('https://speed.cloudflare.com/__down?bytes=1000').GetAwaiter().GetResult(); $probarInternet = $r.IsSuccessStatusCode; $r.Dispose(); $cli.Dispose() } catch { $probarInternet = $false }
}
Titulo ('5. Internet (lo que el router recibe del proveedor; el aula NO lo necesita)')
if ($probarInternet) {
    $p1 = Ping-Serie '1.1.1.1' 20 1000 60
    Dato ('Latencia a Internet (1.1.1.1): {0}' -f (Linea-Latencia $p1.Estadistica $p1.Enviados $p1.Perdidos))
    $dur = [Math]::Min($Segundos, 10)
    $rd = Medir-Caudal 'https://speed.cloudflare.com/__down?bytes=25000000' 'https://speed.cloudflare.com/__up' 'descarga' 4 $dur ''
    $ru = Medir-Caudal 'https://speed.cloudflare.com/__down?bytes=25000000' 'https://speed.cloudflare.com/__up' 'carga' 3 $dur ''
    $mejorWan = $rd.Sostenido; $mejorWanSube = $ru.Sostenido
    Dato ('Internet · BAJADA: {0} Mbps · SUBIDA: {1} Mbps' -f (N $rd.Sostenido 0), (N $ru.Sostenido 0))
    $script:Datos['internet'] = [ordered]@{ bajada_mbps = [Math]::Round($rd.Sostenido, 1); subida_mbps = [Math]::Round($ru.Sostenido, 1) }
} else {
    Dato 'Sin salida a Internet (o apagada con -SinInternet). Es lo normal en un aula sin conexión: no afecta a las tabletas.'
}

# --- 6. qué significa para 35 tabletas
Titulo ('6. Qué significa para {0} tabletas' -f $Tabletas)
$estado = 0
if ($lan -and $mejorBaja -ge 1) {
    $cadaUna = $mejorBaja / $Tabletas
    $t10 = (10.0 * 8 * $Tabletas) / $mejorBaja
    $t30 = (30.0 * 8 * $Tabletas) / $mejorBaja
    if ($modoNodo) { Dato ('Lo máximo que el nodo puede entregar (la mejor prueba, sin red): {0} Mbps. Si el Wi-Fi/router da menos que esto, el cuello es la red, no el nodo.' -f (N $mejorBaja 0)) }
    else { Dato ('Caudal de bajada que el nodo sostiene hacia este equipo por el router (la mejor prueba): {0} Mbps' -f (N $mejorBaja 0)) }
    if ($modoNodo) { Dato ('El servidor, por sí solo, podría dar ≈ {1} Mbps a cada una de las {0} tabletas (sin contar la red).' -f $Tabletas, (N $cadaUna 1)) }
    else { Dato ('Si las {0} tabletas piden a la vez, a cada una le tocarían ≈ {1} Mbps.' -f $Tabletas, (N $cadaUna 1)) }
    Dato ('Una lámina de 10 MB (video corto) llegaría a TODAS en ≈ {0} s; una lección con todos sus medios (≈30 MB), en ≈ {1} s.' -f (N $t10 $(if ($t10 -lt 10) { 1 } else { 0 })), (N $t30 $(if ($t30 -lt 10) { 1 } else { 0 })))
    Dato 'Referencia del curso «Guerra Fría»: los videos pesan 3–8 MB (≈0,8 Mbps al reproducirse); la lección más pesada, ≈30 MB.'
    $script:Datos['estimacion'] = [ordered]@{ tabletas = $Tabletas; mbps_por_tableta = [Math]::Round($cadaUna, 2); segundos_10mb_todas = [Math]::Round($t10, 0); segundos_30mb_todas = [Math]::Round($t30, 0) }
    if ($cadaUna -lt 1.5) { Mal ('Con {0} tabletas a la vez, cada una tendría menos de 1,5 Mbps: un video del curso se cortaría.' -f $Tabletas); $estado = 1 }
    elseif ($cadaUna -lt 4) { Aviso ('Cada tableta tendría ≈ {0} Mbps: los videos se ven, pero cambiar de lección con todas a la vez tarda.' -f (N $cadaUna 1)); $estado = [Math]::Max($estado, 2) }
    else { Bien ('Cada tableta tendría ≈ {0} Mbps: sobra para video y para cargar la lección.' -f (N $cadaUna 1)) }
    if ($modoNodo) { Dato 'OJO: desde el propio nodo sólo se mide al servidor. Para saber si el router aguanta, corre este .bat desde una laptop por Wi-Fi: si da bastante menos que arriba, el cuello es la red.' }
    else { Dato 'OJO: esto mide UN equipo contra el nodo. Es el techo del camino, no una prueba con 35 tabletas reales: úsalo para saber si el router/AP es el cuello.' }
} elseif ($mejorWan -gt 0) {
    Dato 'Sin nodo medible desde este equipo: sólo hay datos de Internet, que no afectan al aula.'
} else {
    Dato 'No hay datos de caudal con el nodo, así que no hay estimación.'
    $estado = [Math]::Max($estado, 2)
}
if ($script:Fallos.Count -gt 0) { $estado = 1 } elseif ($script:Avisos.Count -gt 0) { $estado = [Math]::Max($estado, 2) }

Titulo 'Resumen'
$veredicto = switch ($estado) { 0 { 'LA RED AGUANTA' } 2 { 'LA RED AGUANTA, CON AVISOS' } default { 'LA RED NO AGUANTA O NO SE PUDO MEDIR' } }
$colorV = switch ($estado) { 0 { 'Green' } 2 { 'Yellow' } default { 'Red' } }
Texto ('  ' + $veredicto) $colorV
foreach ($f in $script:Fallos) { Texto ('   · MAL: ' + $f) 'Red' }
foreach ($a in $script:Avisos) { Texto ('   · aviso: ' + $a) 'Yellow' }
$script:Datos['veredicto'] = $veredicto
$script:Datos['fallos'] = @($script:Fallos)
$script:Datos['avisos'] = @($script:Avisos)

# --- el archivo
$ruta = Ruta-Informe
try {
    $encabezado = @('AVACOM · Medición de la red del aula', ('Fecha: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')), ('Equipo: ' + $env:COMPUTERNAME), '')
    $json = $script:Datos | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllLines($ruta, [string[]]($encabezado + $script:Lineas + @('', '--- datos en bruto (JSON) ---', $json)), (New-Object System.Text.UTF8Encoding($true)))
    Texto ''
    Texto ('  Informe guardado en: ' + $ruta) 'Cyan'
    if ($Abrir -and -not $env:AVACOM_SIN_ABRIR) { try { Start-Process notepad.exe $ruta } catch { } }
} catch { Write-Host ('  No pude guardar el informe: ' + $_.Exception.Message) -ForegroundColor Yellow }
exit $estado
