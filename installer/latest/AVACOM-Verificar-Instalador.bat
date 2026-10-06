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
<#
.SYNOPSIS
    Verificador de AVACOM OPS Master: revisa el equipo, el instalador y lo ya
    instalado, y BUSCA EL ERROR EXACTO cuando algo falla. No modifica nada.

.DESCRIPTION
    Es lo que hay detrás de AVACOM-Verificar-Instalador.bat (el .bat lleva este
    PowerShell dentro: ver installer\build\New-VerificadorBat.ps1). Se puede usar
    ANTES de instalar y DESPUÉS, cuando algo falla en el aula.

      1 · El instalador       huella SHA256 contra SHA256.txt, versión, descarga completa
      2 · El equipo           las diez comprobaciones del asistente, ejecutadas de verdad
                              con /VOLCADO: no se instala nada (Windows pide permiso de
                              administrador una vez)
      3 · Lo instalado        versión, servicio, puerto 8000, /health/, canal en tiempo
                              real, base de datos, configuración (sin mostrar secretos)
      4 · Permisos            quién puede escribir dónde: registros, datos, perfil de
                              WebView2. Se prueba con la cuenta de quien ejecuta esto
      5 · Registros del nodo  errores del backend (JSON Lines) y del servicio
      6 · La aplicación       por qué se cierra OPS: Visor de eventos de Windows y el
                              registro de fallos de la aplicación de CADA usuario
      7 · AVACOM Contenido    si el aula alcanza a la biblioteca, y por qué no

    Al terminar deja en el escritorio un informe y un .zip con las evidencias
    (sin claves ni tokens), para enviarlos sin tocar el equipo.

    No cambia la configuración, los datos ni el servicio. Para probar los permisos
    crea y borra al instante un archivo temporal en las carpetas que revisa.

    No ejecutar como administrador salvo que haga falta leer el perfil de OTRO
    usuario de Windows: los permisos se prueban con la cuenta de quien da la clase.

.PARAMETER CarpetaDelInstalador
    Dónde buscar AVACOM-OPS-Master-Setup-*.exe y SHA256.txt (el .bat pasa su carpeta).

.PARAMETER SinAsistente
    No ejecuta las comprobaciones del asistente (no pide permiso de administrador).

.NOTES
    Códigos de salida:  0 todo en orden · 1 hay algo que bloquea · 2 sólo avisos
#>
[CmdletBinding()]
param(
    [string] $CarpetaDelInstalador = '',
    [string] $Instalador = '',
    [int]    $Puerto = 8000,
    # Para analizar otra carpeta de estado o de instalación (ensayos, un nodo copiado).
    [string] $RaizDatos = '',
    [string] $RaizInstalacion = '',
    [string] $RutaEnlace = '',
    # Dónde dejar el informe y el .zip. Por defecto, el escritorio.
    [string] $Salida = '',
    [int]    $DiasDeEventos = 14,
    [int]    $HorasDeLog = 48,
    [switch] $SinAsistente,
    [switch] $Abrir,
    [switch] $Paquete
)

Set-StrictMode -Version Latest
# A propósito NO se usa 'Stop': un verificador que se cae en la primera comprobación
# que falla no sirve para nada. Cada bloque maneja su error.
$ErrorActionPreference = 'Continue'

$VersionVerificador = '2.3.0'
$NombreServicio = 'AVACOMOPSBackend'
$IdInstalacion = '{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}_is1'

# ---------------------------------------------------------------- utilidades

$Hallazgos = New-Object System.Collections.Generic.List[object]
$Renglones = New-Object System.Collections.Generic.List[string]
$Evidencias = New-Object System.Collections.Generic.List[object]

function Escribir {
    param([string] $Texto = '', [string] $Color = 'Gray')
    $Renglones.Add($Texto)
    Write-Host $Texto -ForegroundColor $Color
}

function Seccion {
    param([string] $Titulo)
    Escribir ''
    Escribir ('=' * 74) 'DarkGray'
    Escribir "  $Titulo" 'Cyan'
    Escribir ('=' * 74) 'DarkGray'
}

<#
    Anota un hallazgo. La gravedad decide el color, el orden del resumen final
    y el código de salida.

      OK      · está bien
      INFO    · dato de contexto, no hay nada que hacer
      AVISO   · funciona, pero hay algo que conviene mirar
      BLOQUEA · esto es lo que impide que funcione
#>
function Anotar {
    param(
        [ValidateSet('OK', 'INFO', 'AVISO', 'BLOQUEA')] [string] $Gravedad,
        [string] $Titulo,
        [string] $Detalle = '',
        [string] $Accion = ''
    )

    $Hallazgos.Add([pscustomobject]@{ Gravedad = $Gravedad; Titulo = $Titulo; Detalle = $Detalle; Accion = $Accion })

    $marca = switch ($Gravedad) {
        'OK'      { '  [ok]     ' }
        'INFO'    { '  [info]   ' }
        'AVISO'   { '  [aviso]  ' }
        'BLOQUEA' { '  [FALLA]  ' }
    }
    $color = switch ($Gravedad) {
        'OK'      { 'Green' }
        'INFO'    { 'Gray' }
        'AVISO'   { 'Yellow' }
        'BLOQUEA' { 'Red' }
    }
    Escribir "$marca$Titulo" $color
    if ($Detalle) {
        foreach ($linea in ($Detalle -split "`n")) { Escribir "            $linea" 'DarkGray' }
    }
}

# Con StrictMode, tocar una propiedad que no existe es un error que aborta el script.
function Prop {
    param($Objeto, [string] $Nombre, $PorDefecto = $null)
    if ($null -eq $Objeto) { return $PorDefecto }
    if ($Objeto -isnot [psobject]) { return $PorDefecto }
    $propiedad = $Objeto.PSObject.Properties[$Nombre]
    if ($null -eq $propiedad) { return $PorDefecto }
    if ($null -eq $propiedad.Value) { return $PorDefecto }
    return $propiedad.Value
}

function Recortar {
    param([string] $Texto, [int] $Largo = 300)
    if (-not $Texto) { return '' }
    $imprimible = [regex]::Replace($Texto, '[^ -~ -￿]', '.')
    $limpio = ($imprimible -replace '\s+', ' ').Trim()
    if ($limpio.Length -le $Largo) { return $limpio }
    return $limpio.Substring(0, $Largo) + '...'
}

# Petición HTTP que NO lanza por un código de estado (un 401 o un 503 son respuestas, no fallos).
function Invoke-Peticion {
    param([string] $Url, [hashtable] $Cabeceras = $null, [int] $SegundosDeEspera = 8)

    $resultado = [pscustomobject]@{ Url = $Url; Estado = 0; Cuerpo = ''; Json = $null; Error = '' }
    $respuesta = $null
    try {
        $peticion = [System.Net.HttpWebRequest]::Create($Url)
        $peticion.Method = 'GET'
        $peticion.Timeout = $SegundosDeEspera * 1000
        $peticion.ReadWriteTimeout = $SegundosDeEspera * 1000
        $peticion.AllowAutoRedirect = $false
        $peticion.UserAgent = "AVACOM-Verificador/$VersionVerificador"
        $peticion.Proxy = $null
        if ($Cabeceras) { foreach ($clave in $Cabeceras.Keys) { $peticion.Headers.Add($clave, $Cabeceras[$clave]) } }
        $respuesta = $peticion.GetResponse()
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { $respuesta = $_.Exception.Response } else { $resultado.Error = $_.Exception.Message }
    } catch {
        $resultado.Error = $_.Exception.Message
    }

    if ($respuesta) {
        try {
            $resultado.Estado = [int]$respuesta.StatusCode
            $flujo = $respuesta.GetResponseStream()
            if ($flujo) {
                $lector = New-Object System.IO.StreamReader($flujo, [System.Text.Encoding]::UTF8)
                $resultado.Cuerpo = $lector.ReadToEnd()
                $lector.Dispose()
            }
        } catch { $resultado.Error = $_.Exception.Message } finally { try { $respuesta.Close() } catch { } }
    }
    if ($resultado.Cuerpo) { try { $resultado.Json = $resultado.Cuerpo | ConvertFrom-Json } catch { } }
    return $resultado
}

function Guardar-Evidencia {
    param([string] $Nombre, [string] $Contenido)
    $Evidencias.Add([pscustomobject]@{ Nombre = $Nombre; Contenido = $Contenido })
}

# Las claves, tokens y contraseñas no salen del equipo: ni en el informe ni en el .zip.
function Ocultar-Secretos {
    param([string] $Texto)
    if (-not $Texto) { return '' }
    $salida = New-Object System.Collections.Generic.List[string]
    foreach ($linea in ($Texto -split "`r?`n")) {
        if ($linea -match '^\s*(?<clave>[A-Za-z0-9_]*(SECRET|CLAVE|TOKEN|PASSWORD|KEY)[A-Za-z0-9_]*)\s*=') {
            $salida.Add("$($Matches['clave'])=<oculto>")
        } elseif ($linea -match '"token"\s*:') {
            $salida.Add(($linea -replace '("token"\s*:\s*)"[^"]*"', '$1"<oculto>"'))
        } else {
            $salida.Add($linea)
        }
    }
    return ($salida -join "`n")
}

# Las últimas N líneas de un archivo, aunque otro proceso lo tenga abierto escribiendo.
function Cola-De-Archivo {
    param([string] $Ruta, [int] $Lineas = 200)
    try {
        if (-not (Test-Path -LiteralPath $Ruta)) { return @() }
        return @(Get-Content -LiteralPath $Ruta -Tail $Lineas -Encoding UTF8 -ErrorAction Stop)
    } catch { return @() }
}

function Es-Administrador {
    try {
        return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

# El SID de una identidad de una lista de permisos, para no depender del idioma de Windows
# («Usuarios» o «Users», «SYSTEM» o «SISTEMA»).
function Sid-De {
    param($Referencia)
    try { return $Referencia.Translate([System.Security.Principal.SecurityIdentifier]).Value } catch { return '' }
}

# ¿Tiene ese SID alguno de los derechos pedidos sobre la carpeta? (permisos permitidos, no denegados)
function Tiene-Derechos {
    param([string] $Ruta, [string] $Sid, [System.Security.AccessControl.FileSystemRights] $Derechos)
    try {
        $acl = Get-Acl -LiteralPath $Ruta -ErrorAction Stop
        foreach ($regla in $acl.Access) {
            if ($regla.AccessControlType -ne 'Allow') { continue }
            if ((Sid-De $regla.IdentityReference) -ne $Sid) { continue }
            if (($regla.FileSystemRights -band $Derechos) -eq $Derechos) { return $true }
        }
    } catch { }
    return $false
}

$SidSistema = 'S-1-5-18'
$SidAdministradores = 'S-1-5-32-544'
$SidUsuarios = 'S-1-5-32-545'
$SidTodos = 'S-1-1-0'

# Prueba REAL de escritura con la cuenta de quien ejecuta: crea y borra un archivo.
function Probar-Escritura {
    param([string] $Carpeta)
    try {
        if (-not (Test-Path -LiteralPath $Carpeta)) { return 'no existe' }
        $prueba = Join-Path $Carpeta (".verificador-{0}.tmp" -f [guid]::NewGuid().ToString('N').Substring(0, 8))
        [IO.File]::WriteAllText($prueba, 'ok')
        Remove-Item -LiteralPath $prueba -Force -ErrorAction Stop
        return 'si'
    } catch [System.UnauthorizedAccessException] {
        return 'denegado'
    } catch {
        return "error ($($_.Exception.GetType().Name))"
    }
}

# fallos-ops.log: «[fecha] origen», luego la excepción completa y una línea en blanco. Devuelve las
# entradas de los últimos días (la más reciente al final), con la primera línea de la excepción aparte
# para poder agruparlas. Devuelve un arreglo normal: una List[object] envuelta en @() da un error de
# tipos en PowerShell 5.1.
function Leer-Fallos {
    param([string] $Ruta, [datetime] $Desde)
    $entradas = New-Object System.Collections.Generic.List[object]
    $texto = (Cola-De-Archivo $Ruta 700) -join "`n"
    $opciones = [System.Text.RegularExpressions.RegexOptions]::Multiline -bor [System.Text.RegularExpressions.RegexOptions]::Singleline
    $patron = '^\[(?<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^\]]*\] (?<origen>[^\n]*)\n(?<cuerpo>.*?)(?=^\[\d{4}-\d{2}-\d{2} \d{2}:|\z)'
    foreach ($c in [regex]::Matches($texto, $patron, $opciones)) {
        $momento = $null
        try { $momento = [datetime]::ParseExact($c.Groups['ts'].Value, 'yyyy-MM-dd HH:mm:ss', $null) } catch { continue }
        if ($momento -lt $Desde) { continue }
        $cuerpo = $c.Groups['cuerpo'].Value.Trim()
        $primera = ($cuerpo -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
        $entradas.Add([pscustomobject]@{
            Momento = $momento; Origen = $c.Groups['origen'].Value.Trim(); Excepcion = [string]$primera; Texto = $cuerpo })
    }
    return , $entradas.ToArray()
}

function Leer-Json-De-Archivo {
    param([string] $Ruta)
    try {
        if (-not (Test-Path -LiteralPath $Ruta)) { return $null }
        $texto = [IO.File]::ReadAllText($Ruta, [Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
        return $texto | ConvertFrom-Json
    } catch { return $null }
}

# ================================================================== arranque
$EsAdmin = Es-Administrador
$Hoy = Get-Date

$ClaveDesinstalar = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$IdInstalacion"
$RegistroDeInstalacion = $null
try { $RegistroDeInstalacion = Get-ItemProperty -Path $ClaveDesinstalar -ErrorAction Stop } catch { }
$VersionInstalada = [string](Prop $RegistroDeInstalacion 'DisplayVersion' '')

if (-not $RaizInstalacion) {
    $ubicacion = [string](Prop $RegistroDeInstalacion 'InstallLocation' '')
    $RaizInstalacion = if ($ubicacion) { $ubicacion.TrimEnd('\') } else { Join-Path $env:ProgramFiles 'AVACOM\OPS Master' }
}
if (-not $RaizDatos) { $RaizDatos = Join-Path $env:ProgramData 'AVACOM\OPS Master' }
if (-not $RutaEnlace) { $RutaEnlace = Join-Path $env:ProgramData 'AVACOM\content\link.json' }
if (-not $CarpetaDelInstalador) { $CarpetaDelInstalador = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path } }
$CarpetaDelInstalador = $CarpetaDelInstalador.TrimEnd('\', '.')
if (-not $CarpetaDelInstalador) { $CarpetaDelInstalador = '.' }
if ($CarpetaDelInstalador.EndsWith(':')) { $CarpetaDelInstalador += '\' }   # la raíz de una unidad: «C:» no es «C:\»

$CarpetaLogs = Join-Path $RaizDatos 'Logs'
$CarpetaDatos = Join-Path $RaizDatos 'Data'
$CarpetaConfig = Join-Path $RaizDatos 'Config'
$CarpetaRespaldos = Join-Path $RaizDatos 'Respaldos'
$ArchivoConfig = Join-Path $CarpetaConfig 'backend.env'
$BaseDeDatos = Join-Path $CarpetaDatos 'ops-master.sqlite3'
$InstalacionPresente = Test-Path -LiteralPath (Join-Path $RaizInstalacion 'Runtime\Avacom.Ops.Host.exe')

Escribir ''
Escribir "  AVACOM OPS Master · verificador $VersionVerificador" 'White'
Escribir "  $($Hoy.ToString('yyyy-MM-dd HH:mm:ss'))   equipo: $env:COMPUTERNAME   usuario: $env:USERNAME" 'DarkGray'
Escribir "  Windows $([Environment]::OSVersion.Version)   PowerShell $($PSVersionTable.PSVersion)" 'DarkGray'
if ($EsAdmin) {
    Escribir '  (ejecutado como administrador: las pruebas de permisos de abajo NO representan a quien da la clase)' 'DarkYellow'
} else {
    Escribir '  (sin permisos de administrador: así se prueban los permisos de quien da la clase)' 'DarkGray'
}

# ======================================================== 1 · El instalador
Seccion '1 · El instalador'

$ArchivoInstalador = $null
if ($Instalador -and (Test-Path -LiteralPath $Instalador)) {
    $ArchivoInstalador = Get-Item -LiteralPath $Instalador
} else {
    $candidatos = @(Get-ChildItem -LiteralPath $CarpetaDelInstalador -Filter 'AVACOM-OPS-Master-Setup-*.exe' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    if (@($candidatos).Count -gt 0) { $ArchivoInstalador = $candidatos[0] }
}

$VersionDelInstalador = ''
if (-not $ArchivoInstalador) {
    Anotar 'INFO' 'No hay ningún AVACOM-OPS-Master-Setup-*.exe junto a este archivo' `
        "Se buscó en $CarpetaDelInstalador" `
        'Para revisar un instalador, déjalo junto a este archivo. Lo que sigue revisa lo que ya hay instalado.'
} else {
    $mb = [math]::Round($ArchivoInstalador.Length / 1MB, 1)
    $VersionDelInstalador = ([string]$ArchivoInstalador.VersionInfo.FileVersion)
    Anotar 'INFO' "Instalador: $($ArchivoInstalador.Name) ($mb MB)" `
        "Versión que declara el propio archivo: $VersionDelInstalador   ·   modificado: $($ArchivoInstalador.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))"

    $archivoHuellas = Join-Path (Split-Path $ArchivoInstalador.FullName -Parent) 'SHA256.txt'
    if (-not (Test-Path -LiteralPath $archivoHuellas)) {
        Anotar 'AVISO' 'No está SHA256.txt junto al instalador: no se puede comprobar la descarga' '' `
            'Baja también SHA256.txt de la release y déjalo junto al instalador.'
    } else {
        $textoHuellas = [IO.File]::ReadAllText($archivoHuellas, [Text.Encoding]::UTF8)
        $esperada = ''
        if ($textoHuellas -match '(?im)^SHA256\s+([0-9a-f]{64})') { $esperada = $Matches[1].ToUpperInvariant() }
        $primera = (($textoHuellas -split "`r?`n") | Where-Object { $_.Trim() } | Select-Object -First 1).Trim().TrimStart([char]0xFEFF)
        $real = ''
        try { $real = (Get-FileHash -LiteralPath $ArchivoInstalador.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToUpperInvariant() } catch { }

        if (-not $real) {
            Anotar 'AVISO' 'No se pudo calcular la huella del instalador'
        } elseif (-not $esperada) {
            Anotar 'AVISO' 'SHA256.txt no trae una huella legible'
        } elseif ($primera -and $primera -ne $ArchivoInstalador.Name) {
            Anotar 'AVISO' "SHA256.txt es de otro instalador ($primera)" '' `
                'Baja de la release el SHA256.txt que corresponde a este instalador.'
        } elseif ($real -eq $esperada) {
            Anotar 'OK' 'La huella SHA256 coincide con SHA256.txt: la descarga está completa'
        } else {
            Anotar 'BLOQUEA' 'La huella NO coincide: el archivo está corrupto o es de otra versión' `
                "Esperada: $esperada`nReal:     $real" `
                'Vuelve a descargar el instalador de la release.'
        }

        foreach ($etiqueta in 'Version', 'Revision', 'Arbol-limpio') {
            if ($textoHuellas -match "(?im)^$etiqueta\s+(.+)$") { Escribir "            $etiqueta`: $($Matches[1].Trim())" 'DarkGray' }
        }
    }

    # Una descarga de internet lleva la marca de zona: Windows 10 avisa de «editor desconocido» (SmartScreen).
    try {
        $zona = Get-Content -LiteralPath $ArchivoInstalador.FullName -Stream Zone.Identifier -ErrorAction Stop
        if ($zona) {
            Anotar 'INFO' 'Windows marcó este instalador como descargado de internet' `
                'Al abrirlo puede aparecer «Windows protegió su PC» (SmartScreen).' `
                'Toca «Más información» y luego «Ejecutar de todos modos»: el instalador no tiene firma de código todavía.'
        }
    } catch { }

    if ($VersionInstalada -and $VersionDelInstalador) {
        $nueva = $VersionDelInstalador -replace '\.0$', ''
        if ($VersionInstalada -eq $nueva) {
            Anotar 'INFO' "Ya está instalada la misma versión ($VersionInstalada): instalar de nuevo la reinstala y conserva los datos"
        } else {
            Anotar 'INFO' "Ya está instalada la versión ${VersionInstalada}: este instalador la actualizará a la $nueva" `
                'Se hace una copia de seguridad de los datos antes de tocar nada, y si algo falla se vuelve a la versión anterior.'
        }
    }
}

# ================================================= 2 · Comprobaciones del equipo
Seccion '2 · El equipo (las comprobaciones del asistente, sin instalar nada)'

$VolcadoAsistente = ''
if ($SinAsistente -or -not $ArchivoInstalador) {
    Anotar 'INFO' $(if ($SinAsistente) { 'Se omiten las comprobaciones del asistente (-SinAsistente)' } else { 'Sin instalador no hay comprobaciones del asistente' })
} elseif ($VersionDelInstalador -and ([version]($VersionDelInstalador -replace '[^\d\.].*$', '') -lt [version]'2.0.0')) {
    Anotar 'AVISO' "Este instalador ($VersionDelInstalador) es anterior a 2.0.0 y no sabe comprobar sin instalar: no se ejecuta"
} else {
    $carpetaTemporal = Join-Path $env:TEMP 'avacom-verificar-instalador'
    New-Item -ItemType Directory -Force $carpetaTemporal | Out-Null
    $VolcadoAsistente = Join-Path $carpetaTemporal 'diagnostico.txt'
    Remove-Item -LiteralPath $VolcadoAsistente -Force -ErrorAction SilentlyContinue
    Escribir '  Windows va a pedir permiso de administrador: tócalo para continuar.' 'DarkGray'
    try {
        # /VOLCADO hace que el asistente escriba sus comprobaciones y se detenga: no instala nada.
        Start-Process -FilePath $ArchivoInstalador.FullName -Wait `
            -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/VOLCADO=$VolcadoAsistente" | Out-Null
    } catch {
        Anotar 'AVISO' 'No se ejecutaron las comprobaciones del asistente' $_.Exception.Message `
            'Si cancelaste el permiso de administrador, vuelve a ejecutar este archivo y acéptalo.'
    }

    if (Test-Path -LiteralPath $VolcadoAsistente) {
        $lineasVolcado = @(Get-Content -LiteralPath $VolcadoAsistente -Encoding UTF8)
        $marcaBien = [string][char]0x2713; $marcaMal = [string][char]0x2717; $marcaAviso = [string][char]0x26A0
        foreach ($linea in $lineasVolcado) {
            if (-not $linea.StartsWith('check: ')) { continue }
            $texto = $linea.Substring(7)
            $simbolo = $texto.Substring(0, [math]::Min(1, $texto.Length))
            $cuerpo = ($texto.Substring([math]::Min(1, $texto.Length))).Trim()
            switch ($simbolo) {
                $marcaBien  { Anotar 'OK' $cuerpo }
                $marcaMal   { Anotar 'BLOQUEA' $cuerpo }
                $marcaAviso { Anotar 'AVISO' $cuerpo }
                default     { Anotar 'INFO' $texto }
            }
        }
        $resultado = $lineasVolcado | Where-Object { $_.StartsWith('Resultado:') } | Select-Object -First 1
        if ($resultado -and $resultado -match 'Todo listo') {
            Anotar 'OK' 'El equipo está listo para instalar AVACOM OPS Master'
        } elseif ($resultado) {
            Anotar 'BLOQUEA' 'El equipo NO está listo para instalar' ($resultado -replace '^Resultado:\s*', '')
        }
        Guardar-Evidencia 'asistente-comprobaciones.txt' ($lineasVolcado -join "`n")
    } else {
        Anotar 'AVISO' 'El asistente no llegó a escribir sus comprobaciones' '' `
            'Si cancelaste el permiso de administrador, vuelve a ejecutar este archivo.'
    }
}

# ====================================================== 3 · Lo ya instalado
Seccion '3 · Lo que hay instalado en este equipo'

$Manifiesto = $null
$Salud = $null
$Config = @{}

if (-not $InstalacionPresente) {
    Anotar 'INFO' 'AVACOM OPS Master no está instalado en este equipo (primera instalación)' `
        "Se buscó en $RaizInstalacion"
} else {
    Anotar 'INFO' $(if ($VersionInstalada) { "Versión instalada: $VersionInstalada" } else { 'Versión instalada: no consta en Aplicaciones instaladas' }) `
        "Carpeta: $RaizInstalacion"

    $Manifiesto = Leer-Json-De-Archivo (Join-Path $RaizInstalacion 'manifiesto.json')
    if ($Manifiesto) {
        $revision = [string](Prop $Manifiesto 'revision' '?')
        $limpio = Prop $Manifiesto 'arbol_limpio' $null
        $limpioTexto = if ($null -eq $limpio) { '' } elseif ($limpio) { ' · árbol limpio' } else { ' · con cambios sin confirmar en git' }
        Escribir "            manifiesto: versión $(Prop $Manifiesto 'version' '?') · revisión $revision$limpioTexto · política de datos $(Prop $Manifiesto 'politica_datos' '?')" 'DarkGray'
        $modulos = @(Prop $Manifiesto 'modulos_backend' @())
        if (@($modulos).Count -gt 0) { Escribir "            módulos del backend: $($modulos -join ', ')" 'DarkGray' }
        Guardar-Evidencia 'manifiesto.json' ([IO.File]::ReadAllText((Join-Path $RaizInstalacion 'manifiesto.json'), [Text.Encoding]::UTF8))
    } else {
        Anotar 'AVISO' 'No se pudo leer manifiesto.json de la instalación' '' 'Reinstala AVACOM OPS Master.'
    }

    foreach ($pieza in 'App\Avacom.Lms.Ops.exe', 'Backend\manage.py', 'Runtime\Python\python.exe', 'Runtime\Avacom.Ops.Host.exe', 'Runtime\avacom_ops_backend.py') {
        if (-not (Test-Path -LiteralPath (Join-Path $RaizInstalacion $pieza))) {
            Anotar 'BLOQUEA' "Falta $pieza en la instalación" '' 'La instalación está incompleta: vuelve a ejecutar el instalador.'
        }
    }
    if (Test-Path -LiteralPath (Join-Path $RaizInstalacion 'Anterior')) {
        Anotar 'AVISO' 'Hay una carpeta «Anterior» de una actualización que no terminó' (Join-Path $RaizInstalacion 'Anterior') `
            'Vuelve a ejecutar el instalador: la termina o la deshace.'
    }

    # --- Servicio
    $servicio = $null
    try { $servicio = Get-Service -Name $NombreServicio -ErrorAction Stop } catch { }
    if (-not $servicio) {
        Anotar 'BLOQUEA' "El servicio $NombreServicio no está registrado" '' 'Vuelve a ejecutar el instalador: lo registra.'
    } else {
        $detalleServicio = $null
        try { $detalleServicio = Get-CimInstance -ClassName Win32_Service -Filter "Name='$NombreServicio'" -ErrorAction Stop } catch { }
        $modo = [string](Prop $detalleServicio 'StartMode' '?')
        $cuenta = [string](Prop $detalleServicio 'StartName' '?')
        if ($servicio.Status -eq 'Running') {
            Anotar 'OK' "Servicio $NombreServicio en marcha (inicio: $modo, cuenta: $cuenta)"
        } else {
            Anotar 'BLOQUEA' "El servicio $NombreServicio está $($servicio.Status)" "inicio: $modo · cuenta: $cuenta" `
                'Mira el registro del servicio (sección 5). Para arrancarlo: toca el icono de AVACOM OPS Master.'
        }
        if ($modo -ne 'Auto') {
            Anotar 'AVISO' "El servicio no arranca solo con Windows (inicio: $modo)" '' 'Vuelve a ejecutar el instalador.'
        }
        # Que quien da la clase pueda arrancarlo y pararlo sin credenciales de administrador.
        $sddl = (& "$env:SystemRoot\System32\sc.exe" sdshow $NombreServicio 2>$null | Out-String).Trim()
        if ($sddl -match '\(A;;(?<d>[A-Z]+);;;IU\)') {
            if ($Matches['d'] -match 'RP' -and $Matches['d'] -match 'WP') {
                Anotar 'OK' 'Los usuarios del equipo pueden arrancar y detener el servicio sin credenciales de administrador'
            } else {
                Anotar 'AVISO' "Los usuarios solo tienen estos derechos sobre el servicio: $($Matches['d'])"
            }
        } elseif ($sddl) {
            Anotar 'AVISO' 'Los usuarios del equipo no pueden arrancar el servicio sin credenciales de administrador' '' `
                'Vuelve a ejecutar el instalador: lo configura.'
        }
        Guardar-Evidencia 'servicio.txt' ((& "$env:SystemRoot\System32\sc.exe" qc $NombreServicio 2>&1 | Out-String) + "`n" + $sddl)
    }

    # --- Puerto
    $escuchando = @()
    try { $escuchando = @(Get-NetTCPConnection -State Listen -LocalPort $Puerto -ErrorAction Stop) } catch { }
    if (@($escuchando).Count -eq 0) {
        Anotar 'AVISO' "Nadie escucha en el puerto $Puerto" '' 'Si el servicio está en marcha pero no escucha, mira su registro (sección 5).'
    } else {
        foreach ($conexion in ($escuchando | Sort-Object OwningProcess -Unique)) {
            $proceso = $null
            try { $proceso = Get-Process -Id $conexion.OwningProcess -ErrorAction Stop } catch { }
            $nombre = if ($proceso) { $proceso.ProcessName } else { "pid $($conexion.OwningProcess)" }
            $ruta = ''
            try { if ($proceso) { $ruta = [string]$proceso.Path } } catch { }
            $esNuestro = $ruta -and $ruta.StartsWith($RaizInstalacion, [StringComparison]::OrdinalIgnoreCase)
            if ($esNuestro) {
                Anotar 'OK' "El puerto $Puerto lo escucha el backend de AVACOM OPS ($($conexion.LocalAddress))"
            } else {
                Anotar 'BLOQUEA' "El puerto $Puerto lo ocupa otro programa: $nombre" $ruta `
                    'AVACOM OPS Master necesita ese puerto. Cierra ese programa y reinicia el servicio.'
            }
            if ($conexion.LocalAddress -in @('127.0.0.1', '::1')) {
                Anotar 'AVISO' 'El backend escucha solo en este equipo: las tabletas no podrán llegar' '' 'Debe escuchar en 0.0.0.0:8000.'
            }
        }
    }

    # --- Salud del backend
    $respuestaSalud = Invoke-Peticion "http://127.0.0.1:$Puerto/health/"
    if ($respuestaSalud.Estado -eq 200 -and (Prop $respuestaSalud.Json 'componente' '') -eq 'avacom-lms-backend') {
        $Salud = $respuestaSalud.Json
        $acceso = Prop $Salud 'acceso' $null
        $errorAcceso = [string](Prop $acceso 'error' '')
        if ($errorAcceso) {
            Anotar 'BLOQUEA' 'El backend responde pero no puede usar su base de datos' (Recortar $errorAcceso 240) `
                'Revisa los permisos de la carpeta Data y que ninguna otra copia de manage.py esté usando la base.'
        } else {
            Anotar 'OK' 'La API local responde (/health/)'
        }
        if ((Prop $acceso 'instalado' $true) -eq $false) {
            Anotar 'INFO' 'El nodo todavía no tiene organización ni administrador: falta el primer arranque' '' `
                'Abre AVACOM OPS Master: el primer arranque pide país, nombre del aula, el administrador (documento y contraseña) y el PIN maestro de seis dígitos. La hoja de acceso se muestra UNA vez. Hasta entonces el inicio de sesión responde 409 y las tabletas no entran. Después se crean los grupos y alumnos en Grupos (o se registran solos).'
        } else {
            $estadoPin = [string](Prop $acceso 'pin_maestro' 'desconocido')
            if ($estadoPin -eq 'configurado') {
                Anotar 'OK' 'El PIN maestro está configurado (los profesores pueden crear su usuario y restablecer su contraseña)'
            } elseif ($estadoPin -eq 'vencido') {
                Anotar 'AVISO' 'El PIN maestro está vencido' '' 'Cámbialo en AVACOM OPS Master, Seguridad del aula, o con el técnico: manage.py acceso_pin_maestro --cambiar.'
            } elseif ($estadoPin -eq 'sin_configurar') {
                Anotar 'AVISO' 'El nodo tiene organización pero no PIN maestro' '' `
                    'Hasta que la administración lo configure (AVACOM OPS Master, Seguridad del aula, o manage.py acceso_pin_maestro --cambiar) no aparecen «Crear mi usuario» ni «Olvidé mi contraseña». En una actualización, deja además a los alumnos con PIN provisional en «PIN pendiente» (Nuevo PIN, en Grupos).'
            }
        }
        $configuracionAcceso = Invoke-Peticion "http://127.0.0.1:$Puerto/api/acceso/configuracion/"
        if ($configuracionAcceso.Estado -eq 200) {
            if ((Prop $configuracionAcceso.Json 'sesion_obligatoria' $true) -eq $true) {
                Anotar 'OK' 'El nodo exige identificarse (AVACOM_LMS_EXIGIR_SESION=1): el personal con documento y contraseña, el alumno con su nombre y PIN, o como visitante'
            } else {
                Anotar 'AVISO' 'El nodo está en modo prototipo: NO exige sesión (AVACOM_LMS_EXIGIR_SESION=0)' '' 'Student pedirá solo «Tu nombre». Ponlo en 1 en backend.env y reinicia el servicio para que el aula exija el acceso.'
            }
        }
        if ((Prop $acceso 'claves_derivadas' $false) -eq $true) {
            Anotar 'INFO' 'Este nodo usa las claves derivadas de la versión anterior' '' `
                'Es normal en un nodo que ya tenía personas guardadas: cambiarlas las dejaría ilegibles.'
        }
        Guardar-Evidencia 'health.json' $respuestaSalud.Cuerpo
    } elseif ($respuestaSalud.Estado -gt 0) {
        Anotar 'BLOQUEA' "En el puerto $Puerto contesta algo que no es el backend de AVACOM ($($respuestaSalud.Estado))" `
            (Recortar $respuestaSalud.Cuerpo 200) 'Cierra el programa que usa el puerto.'
    } else {
        Anotar 'BLOQUEA' 'La API local no responde' $respuestaSalud.Error `
            'Comprueba el servicio y su registro (sección 5). Las tabletas y la interfaz dependen de ella.'
    }

    # --- Canal en tiempo real (WebSocket): lo mismo que valida el instalador al terminar
    if ($respuestaSalud.Estado -eq 200) {
        $socket = New-Object System.Net.WebSockets.ClientWebSocket
        $limite = New-Object System.Threading.CancellationTokenSource(6000)
        try {
            $socket.ConnectAsync([Uri]"ws://127.0.0.1:$Puerto/ws/aula/sesiones/verificador-de-la-instalacion/?rol=docente", $limite.Token).Wait()
            Anotar 'OK' 'El canal en tiempo real del aula (WebSocket) acepta conexiones'
        } catch {
            $causa = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
            Anotar 'BLOQUEA' 'El canal en tiempo real del aula (WebSocket) no acepta conexiones' (Recortar $causa 200) `
                'El backend debe correr con Daphne (avacom_lms.asgi). Mira el registro del servicio (sección 5).'
        } finally { $socket.Dispose(); $limite.Dispose() }

        # --- Auditoría: la ruta existe y exige sesión (401/403); 404 sería un backend sin el módulo
        $auditoria = Invoke-Peticion "http://127.0.0.1:$Puerto/api/auditoria/estado/"
        if ($auditoria.Estado -in 200, 401, 403) {
            Anotar 'OK' "El módulo de auditoría responde ($($auditoria.Estado)$(if ($auditoria.Estado -ne 200) { ', exige sesión' }))"
        } elseif ($auditoria.Estado -eq 404) {
            Anotar 'BLOQUEA' 'El backend instalado no trae el módulo de auditoría (/api/auditoria/)' '' 'Es de una versión anterior: vuelve a ejecutar el instalador.'
        } else {
            Anotar 'AVISO' "El módulo de auditoría contestó $($auditoria.Estado)" (Recortar $auditoria.Cuerpo 200)
        }
    }

    # --- Configuración (sin secretos)
    if (-not (Test-Path -LiteralPath $ArchivoConfig)) {
        Anotar 'BLOQUEA' 'No existe backend.env: el servicio no arranca sin configuración' $ArchivoConfig 'Vuelve a ejecutar el instalador.'
    } else {
        $textoConfig = ''
        try { $textoConfig = [IO.File]::ReadAllText($ArchivoConfig, [Text.Encoding]::UTF8) } catch {
            Anotar 'AVISO' 'No se pudo leer backend.env con esta cuenta' $_.Exception.Message
        }
        foreach ($linea in ($textoConfig -split "`r?`n")) {
            if ($linea -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { $Config[$Matches[1]] = $Matches[2].Trim() }
        }
        Guardar-Evidencia 'backend.env.txt' (Ocultar-Secretos $textoConfig)

        $faltan = @('AVACOM_LMS_SECRET', 'AVACOM_LMS_DB') | Where-Object { -not $Config.ContainsKey($_) -or -not $Config[$_] }
        if (@($faltan).Count -gt 0) {
            Anotar 'BLOQUEA' "Faltan en backend.env: $($faltan -join ', ')" '' 'Sin ellas el backend usaría la clave de prototipo y una base vacía. Vuelve a ejecutar el instalador.'
        }
        if ($Config.ContainsKey('AVACOM_LMS_DEBUG') -and $Config['AVACOM_LMS_DEBUG'] -eq '1') {
            Anotar 'AVISO' 'La depuración del backend está encendida (AVACOM_LMS_DEBUG=1)' '' `
                'La API muestra trazas de error a la red del aula. Ponla en 0 y reinicia el servicio al terminar de diagnosticar.'
        }
        if ($Config.ContainsKey('AVACOM_AULA_PERMITIR_EJEMPLO') -and $Config['AVACOM_AULA_PERMITIR_EJEMPLO'] -eq '1') {
            Anotar 'AVISO' 'El curso de ejemplo está encendido (AVACOM_AULA_PERMITIR_EJEMPLO=1)' '' `
                'Los cursos deben salir siempre de AVACOM Contenido. Vuelve a ejecutar el instalador: lo apaga.'
        }
        if ($Config.ContainsKey('AVACOM_AULA_FUENTE_CURSOS') -and $Config['AVACOM_AULA_FUENTE_CURSOS'] -ne 'biblioteca') {
            Anotar 'AVISO' "La fuente de cursos es «$($Config['AVACOM_AULA_FUENTE_CURSOS'])» y debe ser «biblioteca»" '' 'Vuelve a ejecutar el instalador.'
        }
        foreach ($variable in 'AVACOM_CONTENIDO_ENLACE', 'AVACOM_CONTENIDO_ENLACE_V2') {
            if ($Config.ContainsKey($variable) -and $Config[$variable]) {
                Anotar 'AVISO' "$variable apunta a una nota de enlace distinta de la normal" $Config[$variable] `
                    'Es una configuración de pruebas: deja al aula sin cursos aunque AVACOM Contenido esté abierto. Vuelve a ejecutar el instalador: la retira.'
            }
        }
        if (-not $Config.ContainsKey('AVACOM_LMS_ENTORNO') -or -not $Config.ContainsKey('AVACOM_LMS_DIR_LOGS')) {
            Anotar 'INFO' 'La configuración es de una versión anterior (no fija la carpeta de registros)' '' `
                'Funciona: el backend deduce la carpeta de ProgramData. Se completa al actualizar.'
        }
        if ($Config.ContainsKey('AVACOM_LMS_DB') -and $Config['AVACOM_LMS_DB'] -and
            ($Config['AVACOM_LMS_DB'].TrimEnd('\') -ne $BaseDeDatos.TrimEnd('\'))) {
            Anotar 'AVISO' 'La base de datos configurada no es la del nodo' "Configurada: $($Config['AVACOM_LMS_DB'])`nDel nodo:     $BaseDeDatos" `
                'Las copias de seguridad miran la ruta del nodo.'
        }
        $claves = @('AVACOM_LMS_CLAVE_DATOS', 'AVACOM_LMS_CLAVE_INDICE', 'AVACOM_LMS_CLAVE_TOKENS') | Where-Object { $Config.ContainsKey($_) -and $Config[$_] }
        Escribir "            claves de acceso propias: $(@($claves).Count) de 3 (los valores nunca se muestran)" 'DarkGray'
    }

    # --- Datos
    if (Test-Path -LiteralPath $BaseDeDatos) {
        $baseInfo = Get-Item -LiteralPath $BaseDeDatos
        $extras = @('-wal', '-shm') | Where-Object { Test-Path -LiteralPath ($BaseDeDatos + $_) }
        Anotar 'OK' "Base de datos del nodo: $([math]::Round($baseInfo.Length / 1KB)) KB" `
            "$BaseDeDatos`nÚltima escritura: $($baseInfo.LastWriteTime.ToString('yyyy-MM-dd HH:mm'))$(if (@($extras).Count) { '   (con ' + ($extras -join ' y ') + ': normal mientras el servicio corre)' })"
    } else {
        Anotar 'AVISO' 'No hay base de datos del nodo todavía' $BaseDeDatos 'Se crea al iniciar el servicio por primera vez.'
    }
    if (Test-Path -LiteralPath $CarpetaRespaldos) {
        $copias = @(Get-ChildItem -LiteralPath $CarpetaRespaldos -Directory -ErrorAction SilentlyContinue | Sort-Object CreationTime -Descending)
        if (@($copias).Count -gt 0) {
            Escribir "            copias de seguridad: $(@($copias).Count) (la última: $($copias[0].Name))" 'DarkGray'
        }
    }

    # --- Firewall y red del aula
    try {
        $regla = @(Get-NetFirewallRule -DisplayName 'AVACOM OPS Master Backend' -ErrorAction Stop)
        if (@($regla | Where-Object { $_.Enabled -eq 'True' }).Count -gt 0) {
            Anotar 'OK' 'La regla de firewall para las tabletas existe y está activa' `
                (($regla | ForEach-Object { "perfiles: $($_.Profile)" }) -join '; ')
        } else {
            Anotar 'AVISO' 'La regla de firewall existe pero está desactivada' '' 'Las tabletas no podrán llegar. Vuelve a ejecutar el instalador.'
        }
    } catch {
        Anotar 'AVISO' 'No se encontró la regla de firewall «AVACOM OPS Master Backend»' '' `
            'Sin ella, este equipo funciona pero las tabletas no lo alcanzan. Vuelve a ejecutar el instalador.'
    }
    try {
        $publicas = @(Get-NetConnectionProfile -ErrorAction Stop | Where-Object { $_.NetworkCategory -eq 'Public' })
        if (@($publicas).Count -gt 0) {
            Anotar 'AVISO' "Windows clasifica como pública la red: $(($publicas | ForEach-Object { $_.Name }) -join ', ')" '' `
                'La regla de firewall solo abre redes privadas y de dominio: en una red pública las tabletas no llegan. Cámbiala a privada.'
        }
    } catch { }
    try {
        $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
            Select-Object -ExpandProperty IPAddress)
        if (@($ips).Count -gt 0) {
            Anotar 'INFO' 'Dirección de este equipo para las tabletas' (($ips | ForEach-Object { "http://${_}:$Puerto" }) -join "`n")
        }
    } catch { }
}

# =================================================================== 4 · Permisos
Seccion '4 · Permisos de escritura y lectura'

if (-not (Test-Path -LiteralPath $RaizDatos)) {
    Anotar 'INFO' 'Todavía no existe la carpeta de datos del nodo' "$RaizDatos (la crea el instalador)"
} else {
    foreach ($carpeta in @(@('Config', $CarpetaConfig), @('Data', $CarpetaDatos), @('Respaldos', $CarpetaRespaldos), @('Logs', $CarpetaLogs))) {
        $nombre = $carpeta[0]; $ruta = $carpeta[1]
        if (-not (Test-Path -LiteralPath $ruta)) { Anotar 'AVISO' "No existe la carpeta $nombre" $ruta 'Vuelve a ejecutar el instalador.'; continue }

        # El servicio corre como SYSTEM: sin control total ahí, escribiría en otra parte o no escribiría.
        $sistema = Tiene-Derechos $ruta $SidSistema ([System.Security.AccessControl.FileSystemRights]::FullControl)
        $admins = Tiene-Derechos $ruta $SidAdministradores ([System.Security.AccessControl.FileSystemRights]::FullControl)
        if ($sistema -and $admins) {
            Anotar 'OK' "$nombre`: SYSTEM (el servicio) y los administradores tienen control total"
        } else {
            Anotar 'BLOQUEA' "$nombre`: falta control total para $(@(if (-not $sistema) { 'SYSTEM (el servicio)' }; if (-not $admins) { 'los administradores' }) -join ' y ')" $ruta `
                'Sin esto el servicio no puede escribir ahí. Vuelve a ejecutar el instalador: lo corrige.'
        }
    }

    # Logs: quien da la clase debe poder escribir (el lanzador deja ahí su diagnóstico).
    if (Test-Path -LiteralPath $CarpetaLogs) {
        $usuariosModifican = (Tiene-Derechos $CarpetaLogs $SidUsuarios ([System.Security.AccessControl.FileSystemRights]::Modify)) -or
                             (Tiene-Derechos $CarpetaLogs $SidTodos ([System.Security.AccessControl.FileSystemRights]::Modify))
        $prueba = Probar-Escritura $CarpetaLogs
        if ($prueba -eq 'si') {
            Anotar 'OK' "Logs: $env:USERNAME puede crear y borrar archivos$(if ($EsAdmin) { ' (como administrador: no es representativo)' })"
        } else {
            Anotar 'AVISO' "Logs: $env:USERNAME NO puede escribir ($prueba)" $CarpetaLogs `
                'El lanzador no podrá dejar su diagnóstico. Vuelve a ejecutar el instalador: da el permiso.'
        }
        if (-not $usuariosModifican) {
            Anotar 'AVISO' 'Logs: el grupo Usuarios no tiene permiso de modificación' '' 'Vuelve a ejecutar el instalador.'
        }
    }
}

# Perfil de WebView2: la causa conocida de que la aplicación se cierre al abrir una lección.
if ($InstalacionPresente) {
    $perfilJunto = Join-Path $RaizInstalacion 'App\Avacom.Lms.Ops.exe.WebView2'
    if (Test-Path -LiteralPath $perfilJunto) {
        $prueba = Probar-Escritura $perfilJunto
        if ($prueba -eq 'si') {
            Anotar 'OK' 'Perfil de WebView2 junto a la aplicación: se puede escribir (red de seguridad)'
        } else {
            Anotar 'BLOQUEA' "El perfil de WebView2 junto a la aplicación NO se puede escribir con esta cuenta ($prueba)" $perfilJunto `
                'Si la aplicación se abre sin el icono del escritorio y se cierra al abrir una lección, es por esto. Vuelve a ejecutar el instalador.'
        }
    } else {
        Anotar 'AVISO' 'Falta la carpeta de perfil de WebView2 junto a la aplicación' $perfilJunto `
            'Es la red de seguridad si la aplicación se abre sin el icono. Se crea con el instalador 2.2.0 o posterior.'
    }
    $pruebaApp = Probar-Escritura (Join-Path $RaizInstalacion 'App')
    if ($pruebaApp -eq 'si' -and -not $EsAdmin) {
        Anotar 'AVISO' 'Quien da la clase puede modificar la carpeta de la aplicación' (Join-Path $RaizInstalacion 'App') `
            'Debería ser de solo lectura: un usuario podría reemplazar binarios.'
    } elseif (-not $EsAdmin) {
        Anotar 'OK' 'La carpeta de la aplicación es de solo lectura para quien da la clase (como debe ser)'
    }
}

# Perfiles de WebView2 por usuario: existen cuando el icono del escritorio abrió OPS al menos una vez.
$usuariosDeWindows = @()
try { $usuariosDeWindows = @(Get-ChildItem (Join-Path $env:SystemDrive 'Users') -Directory -ErrorAction Stop |
        Where-Object { @('Public', 'Default', 'Default User', 'All Users') -notcontains $_.Name }) } catch { }
$perfilesConLanzador = 0
$perfilesSinAcceso = @()
foreach ($usuario in $usuariosDeWindows) {
    $localAvacom = Join-Path $usuario.FullName 'AppData\Local\AVACOM'
    try { $null = Get-ChildItem -LiteralPath $usuario.FullName -ErrorAction Stop } catch { $perfilesSinAcceso += $usuario.Name; continue }
    if (Test-Path -LiteralPath (Join-Path $localAvacom 'OPS Master\WebView2')) { $perfilesConLanzador++ }
}
if ($InstalacionPresente) {
    if ($perfilesConLanzador -gt 0) {
        Anotar 'OK' "El icono del escritorio ya abrió OPS con su perfil propio de WebView2 ($perfilesConLanzador usuario(s))"
    } elseif (@($perfilesSinAcceso).Count -eq 0) {
        Anotar 'INFO' 'Nadie ha abierto OPS desde el icono del escritorio todavía (no hay perfil de WebView2 en ningún usuario)'
    }
    if (@($perfilesSinAcceso).Count -gt 0) {
        Anotar 'INFO' "No se pudo mirar el perfil de: $($perfilesSinAcceso -join ', ')" '' `
            'Para revisar el perfil de otro usuario, ejecuta este archivo como administrador (mantén el toque y elige «Ejecutar como administrador»).'
    }
}

# Runtime de WebView2: lo usan las lecciones (audio, video, PDF y laboratorios).
$versionWebView = ''
foreach ($ruta in @('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
                    'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
                    'HKCU:\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')) {
    try { $pv = (Get-ItemProperty -Path $ruta -Name pv -ErrorAction Stop).pv; if ($pv -and $pv -ne '0.0.0.0') { $versionWebView = $pv; break } } catch { }
}
if ($versionWebView) {
    Anotar 'OK' "Runtime de WebView2 (Edge) presente: $versionWebView"
} else {
    Anotar 'AVISO' 'Falta el runtime de WebView2 de Microsoft' '' `
        'Las lecciones con audio, video, PDF o laboratorio pueden cerrar la aplicación. Instálalo desde Microsoft (Evergreen WebView2 Runtime).'
}

# ============================================================== 5 · Registros
Seccion '5 · Registros del nodo'

if (-not (Test-Path -LiteralPath $CarpetaLogs)) {
    Anotar 'INFO' 'Todavía no hay registros del nodo' $CarpetaLogs
} else {
    $archivosDeLog = @(Get-ChildItem -LiteralPath $CarpetaLogs -File -ErrorAction SilentlyContinue | Sort-Object Name)
    Escribir "            $(@($archivosDeLog).Count) archivo(s) en $CarpetaLogs" 'DarkGray'
    foreach ($archivo in ($archivosDeLog | Where-Object { $_.Name -notmatch '\.log\.\d+$' })) {
        Escribir ("            {0,-28} {1,8} KB   {2}" -f $archivo.Name, [math]::Round($archivo.Length / 1KB), $archivo.LastWriteTime.ToString('yyyy-MM-dd HH:mm')) 'DarkGray'
    }

    # backend-app.log: ¿lo está escribiendo el servicio?
    $backendApp = Join-Path $CarpetaLogs 'backend-app.log'
    if ($InstalacionPresente -and $Salud) {
        $ultimaLinea = (Cola-De-Archivo $backendApp 3 | Where-Object { $_.StartsWith('{') } | Select-Object -Last 1)
        $marca = $null
        if ($ultimaLinea) { try { $marca = [datetimeoffset]::Parse((($ultimaLinea | ConvertFrom-Json).ts)) } catch { } }
        if ($marca -and ([datetimeoffset]::Now - $marca).TotalMinutes -lt 10) {
            Anotar 'OK' "El backend está escribiendo sus registros (último renglón: $($marca.ToString('HH:mm:ss')))"
        } elseif ($marca) {
            Anotar 'INFO' "El último renglón de backend-app.log es de hace $([math]::Round(([datetimeoffset]::Now - $marca).TotalMinutes)) min" `
                'Normal si nadie ha usado la API en ese tiempo.'
        } else {
            Anotar 'AVISO' 'El backend responde pero backend-app.log no tiene renglones legibles' $backendApp `
                'Puede que el servicio no pueda escribir en la carpeta de registros y los esté guardando en la carpeta temporal del sistema.'
        }
    }

    # Errores del backend: backend-errores.log (JSON Lines, solo WARNING o más).
    $desde = $Hoy.AddHours(-$HorasDeLog)
    $renglonesDeError = New-Object System.Collections.Generic.List[object]
    foreach ($nombre in 'backend-errores.log', 'backend-errores.log.1') {
        foreach ($linea in (Cola-De-Archivo (Join-Path $CarpetaLogs $nombre) 500)) {
            if (-not $linea.StartsWith('{')) { continue }
            try {
                $registroJson = $linea | ConvertFrom-Json
                $momento = [datetimeoffset]::Parse([string](Prop $registroJson 'ts' ''))
                if ($momento.LocalDateTime -lt $desde) { continue }
                $renglonesDeError.Add([pscustomobject]@{
                    Momento = $momento.LocalDateTime
                    Nivel   = [string](Prop $registroJson 'nivel' '')
                    Evento  = [string](Prop $registroJson 'evento' '')
                    Mensaje = [string](Prop $registroJson 'mensaje' '')
                    Traza   = [string](Prop $registroJson 'traza' '')
                })
            } catch { }
        }
    }
    $conTraza = @($renglonesDeError | Where-Object { $_.Nivel -in 'ERROR', 'CRITICAL' })
    if ($renglonesDeError.Count -eq 0) {
        Anotar 'OK' "backend-errores.log: sin advertencias ni errores en las últimas $HorasDeLog h"
    } else {
        $grupos = @($renglonesDeError | Group-Object { "$($_.Nivel)|$($_.Evento)|$((Recortar $_.Mensaje 90))" } | Sort-Object Count -Descending)
        Anotar $(if (@($conTraza).Count -gt 0) { 'AVISO' } else { 'INFO' }) `
            "backend-errores.log: $($renglonesDeError.Count) renglón(es) en $(@($grupos).Count) forma(s) distinta(s), últimas $HorasDeLog h ($(@($conTraza).Count) de nivel ERROR)"
        foreach ($grupo in ($grupos | Select-Object -First 6)) {
            $muestra = $grupo.Group | Sort-Object Momento -Descending | Select-Object -First 1
            Escribir ("            {0} {1,-8} x{2,-3} {3}" -f $muestra.Momento.ToString('MM-dd HH:mm'), $muestra.Nivel, $grupo.Count, (Recortar "$($muestra.Evento) $($muestra.Mensaje)" 110)) 'Yellow'
            if ($muestra.Traza) {
                $excepcion = (($muestra.Traza -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 1)).Trim()
                Escribir "                 $(Recortar $excepcion 130)" 'DarkGray'
            }
        }
        Escribir '            Para analizar los errores a fondo: AVACOM-Probar-Comunicacion.bat (apartado 10).' 'DarkGray'
    }

    # El registro del servicio (el host): arranques, reinicios, y por qué no arrancó.
    $servicioLog = Join-Path $CarpetaLogs 'servicio.log'
    $lineasServicio = Cola-De-Archivo $servicioLog 800
    if (@($lineasServicio).Count -gt 0) {
        $reinicios = @($lineasServicio | Where-Object { $_ -match 'El backend termino con codigo' }).Count
        $sinConfig = @($lineasServicio | Where-Object { $_ -match 'No se arranca el backend' })
        $ocupado = @($lineasServicio | Where-Object { $_ -match 'lo ocupa otro programa' })
        $trazas = @($lineasServicio | Where-Object { $_ -match 'Traceback \(most recent call last\)' }).Count
        if ($sinConfig.Count -gt 0) {
            Anotar 'BLOQUEA' 'El servicio se negó a arrancar el backend por falta de configuración' ($sinConfig | Select-Object -Last 1) `
                'Vuelve a ejecutar el instalador: recrea la configuración sin tocar los datos.'
        }
        if ($ocupado.Count -gt 0) {
            Anotar 'AVISO' 'El servicio encontró el puerto ocupado por otro programa' ($ocupado | Select-Object -Last 1)
        }
        if ($reinicios -gt 3) {
            Anotar 'BLOQUEA' "El backend se reinició $reinicios veces" 'Algo lo está tumbando.' 'Mira el primer error de Python del registro del servicio.'
        } elseif ($reinicios -gt 0) {
            Anotar 'INFO' "El backend se reinició $reinicios vez/veces en el tramo revisado del registro del servicio"
        }
        if ($trazas -gt 0) {
            Anotar 'AVISO' "El registro del servicio tiene $trazas error(es) de Python" '' `
                'Para clasificarlos y saber qué hacer: AVACOM-Probar-Comunicacion.bat.'
        }
        if ($sinConfig.Count -eq 0 -and $ocupado.Count -eq 0 -and $reinicios -eq 0 -and $trazas -eq 0) {
            Anotar 'OK' 'El registro del servicio no muestra reinicios ni errores'
        }
    }
    foreach ($nombre in 'servicio.log', 'instalacion.log', 'lanzador.log', 'instalador-ultimo.log', 'backend-errores.log', 'backend-app.log') {
        $cola = Cola-De-Archivo (Join-Path $CarpetaLogs $nombre) 300
        if (@($cola).Count -gt 0) { Guardar-Evidencia "logs\$nombre" ($cola -join "`n") }
    }
    $ultimasInstalacion = Cola-De-Archivo (Join-Path $CarpetaLogs 'instalacion.log') 6 | Where-Object { -not $_.StartsWith('{') }
    if (@($ultimasInstalacion).Count -gt 0) {
        Escribir '            últimas líneas del registro de instalación:' 'DarkGray'
        foreach ($l in $ultimasInstalacion) { Escribir "              $(Recortar $l 150)" 'DarkGray' }
    }
}

# ================================================ 6 · La aplicación del profesor
Seccion '6 · La aplicación del profesor (OPS): por qué se cierra'

$abiertas = @()
try { $abiertas = @(Get-Process -Name 'Avacom.Lms.Ops' -ErrorAction Stop) } catch { }
if (@($abiertas).Count -gt 0) {
    foreach ($p in $abiertas) {
        $respondiendo = try { $p.Responding } catch { $true }
        # StartTime lanza una excepción si el proceso es de otra sesión o está elevado.
        $inicioTexto = try { $p.StartTime.ToString('HH:mm:ss') } catch { '?' }
        Anotar 'INFO' "AVACOM OPS Master está abierto (pid $($p.Id), desde $inicioTexto)$(if (-not $respondiendo) { ' y NO responde' })"
    }
} else {
    Anotar 'INFO' 'AVACOM OPS Master no está abierto ahora mismo'
}

# --- Visor de eventos de Windows (Aplicación). Se filtra por proveedor e identificador, no por texto:
#     el texto sale en el idioma de Windows. 1000 = Application Error, 1002 = Application Hang,
#     1026 = .NET Runtime, 1001 = Windows Error Reporting.
$eventosDeLaApp = New-Object System.Collections.Generic.List[object]
try {
    $crudos = @(Get-WinEvent -FilterHashtable @{
        LogName = 'Application'; Id = 1000, 1001, 1002, 1026; StartTime = $Hoy.AddDays(-$DiasDeEventos)
    } -ErrorAction Stop)
    foreach ($e in $crudos) {
        $texto = ''
        try { $texto = [string]$e.Message } catch { }
        if ($texto -notmatch 'Avacom\.Lms\.Ops|Avacom\.Ops\.Host') { continue }
        $propiedades = @($e.Properties | ForEach-Object { [string]$_.Value })
        $eventosDeLaApp.Add([pscustomobject]@{
            Momento = $e.TimeCreated; Id = $e.Id; Proveedor = $e.ProviderName; Texto = $texto; Propiedades = $propiedades
        })
    }
} catch {
    if ($_.Exception.Message -notmatch 'No events were found|No se encontraron') {
        Anotar 'AVISO' 'No se pudo leer el Visor de eventos de Windows' $_.Exception.Message
    }
}

# El registro de fallos de la aplicación de CADA usuario de Windows. Es donde queda la excepción
# exacta: la escribe el propio OPS justo antes de cerrarse, en el perfil de quien lo ejecutó.
$FallosPorUsuario = @{}
foreach ($usuario in $usuariosDeWindows) {
    $rutaDeFallos = Join-Path $usuario.FullName 'AppData\Local\AVACOM\lms\fallos-ops.log'
    if (Test-Path -LiteralPath $rutaDeFallos) { $FallosPorUsuario[$usuario.Name] = Leer-Fallos $rutaDeFallos $Hoy.AddDays(-$DiasDeEventos) }
}

$cierresInesperados = @($eventosDeLaApp | Where-Object { $_.Id -in 1000, 1002, 1026 } | Sort-Object Momento -Descending)
if (@($cierresInesperados).Count -eq 0) {
    Anotar 'OK' "Windows no registró cierres inesperados de AVACOM OPS Master en los últimos $DiasDeEventos días"
} else {
    Anotar 'AVISO' "Windows registró $(@($cierresInesperados).Count) cierre(s) inesperado(s) de AVACOM OPS Master en los últimos $DiasDeEventos días"
    foreach ($e in ($cierresInesperados | Select-Object -First 6)) {
        $resumen = switch ($e.Id) {
            1000 {
                $modulo = if (@($e.Propiedades).Count -gt 3) { $e.Propiedades[3] } else { '?' }
                $codigo = if (@($e.Propiedades).Count -gt 6) { $e.Propiedades[6] } else { '?' }
                "se cerró por un error: módulo $modulo · código $codigo"
            }
            1002 { 'dejó de responder y Windows lo cerró' }
            1026 { 'excepción de .NET sin controlar: ' + (Recortar (($e.Texto -split "`r?`n" | Select-Object -First 8) -join ' ') 200) }
            default { Recortar $e.Texto 160 }
        }
        Escribir ("            {0}  [{1}]  {2}" -f $e.Momento.ToString('yyyy-MM-dd HH:mm:ss'), $e.Id, $resumen) 'Yellow'

        # La excepción exacta de ESE cierre: la que la aplicación anotó en los segundos anteriores.
        $causa = $null; $deQuien = ''
        foreach ($nombreUsuario in $FallosPorUsuario.Keys) {
            foreach ($f in $FallosPorUsuario[$nombreUsuario]) {
                $segundos = ($e.Momento - $f.Momento).TotalSeconds
                if ($segundos -lt -5 -or $segundos -gt 20) { continue }
                if (-not $causa -or [math]::Abs($segundos) -lt [math]::Abs(($e.Momento - $causa.Momento).TotalSeconds)) { $causa = $f; $deQuien = $nombreUsuario }
            }
        }
        if ($causa) {
            Escribir "                 la aplicación anotó ($deQuien · $($causa.Origen)): $(Recortar $causa.Excepcion 150)" 'White'
        }
    }
    if (@($cierresInesperados | Where-Object { $_.Id -eq 1000 -and @($_.Propiedades).Count -gt 6 -and $_.Propiedades[6] -match 'c000027b' }).Count -gt 0) {
        Escribir '            0xc000027b en Microsoft.UI.Xaml.dll es la firma de CUALQUIER excepción no controlada de la interfaz:' 'DarkGray'
        Escribir '            el Visor no dice cuál. La causa exacta queda en fallos-ops.log (justo debajo).' 'DarkGray'
    }
}
if ($eventosDeLaApp.Count -gt 0) {
    Guardar-Evidencia 'eventos-de-windows.txt' (($eventosDeLaApp | Sort-Object Momento -Descending | ForEach-Object {
        "[{0}] {1} id {2}`n{3}`n" -f $_.Momento.ToString('yyyy-MM-dd HH:mm:ss'), $_.Proveedor, $_.Id, $_.Texto }) -join "`n")
}

# --- El registro de fallos de la aplicación, de CADA usuario de Windows. Es donde queda la excepción
#     exacta (la escribe el propio OPS antes de cerrarse). Vive en el perfil de quien ejecutó OPS.
$PatronDePermisos = 'UnauthorizedAccess|Acceso denegado|Access is denied|0x80070005|E_ACCESSDENIED|WebView2|CoreWebView2|EnsureCoreWebView2'
$huboFallosDePermisos = $false
$perfilesRevisados = 0

foreach ($usuario in $usuariosDeWindows) {
    $carpetaLms = Join-Path $usuario.FullName 'AppData\Local\AVACOM\lms'
    if (-not (Test-Path -LiteralPath $carpetaLms)) { continue }
    $perfilesRevisados++
    Escribir ''
    Escribir "  Usuario de Windows: $($usuario.Name)" 'White'

    # fallos-ops.log: [fecha] origen, luego la excepción completa, y una línea en blanco.
    $rutaFallos = Join-Path $carpetaLms 'fallos-ops.log'
    if (Test-Path -LiteralPath $rutaFallos) {
        $info = Get-Item -LiteralPath $rutaFallos
        $entradas = @($FallosPorUsuario[$usuario.Name])
        if (@($entradas).Count -eq 0) {
            Anotar 'OK' "fallos-ops.log: sin fallos en los últimos $DiasDeEventos días ($([math]::Round($info.Length / 1KB)) KB en total)"
        } else {
            $grupos = @($entradas | Group-Object { "$($_.Origen)|$(Recortar $_.Excepcion 120)" } | Sort-Object { ($_.Group | Measure-Object Momento -Maximum).Maximum } -Descending)
            Anotar 'AVISO' "fallos-ops.log: $(@($entradas).Count) fallo(s) en $(@($grupos).Count) forma(s) distinta(s) en los últimos $DiasDeEventos días" $rutaFallos
            foreach ($grupo in ($grupos | Select-Object -First 5)) {
                $ultimo = $grupo.Group | Sort-Object Momento -Descending | Select-Object -First 1
                Escribir ("            {0}  x{1,-3} {2}" -f $ultimo.Momento.ToString('yyyy-MM-dd HH:mm:ss'), $grupo.Count, $ultimo.Origen) 'Yellow'
                Escribir "                 $(Recortar $ultimo.Excepcion 170)" 'White'
                $pila = $ultimo.Texto -split "`n" | Where-Object { $_ -match '^\s+at ' } | Select-Object -First 3
                foreach ($paso in $pila) { Escribir "                 $(Recortar $paso 150)" 'DarkGray' }
                if ($ultimo.Texto -match $PatronDePermisos) { $huboFallosDePermisos = $true }
            }
        }
        $ultimas = ($entradas | Sort-Object Momento -Descending | Select-Object -First 8 | ForEach-Object {
            '[' + $_.Momento.ToString('yyyy-MM-dd HH:mm:ss') + '] ' + $_.Origen + "`n" +
            (($_.Texto -split "`n" | Select-Object -First 25) -join "`n") + "`n" }) -join "`n"
        if ($ultimas) { Guardar-Evidencia "usuarios\$($usuario.Name)\fallos-ops.log (ultimos)" $ultimas }
    } else {
        Anotar 'INFO' 'No hay fallos-ops.log: OPS no ha dejado ningún fallo no controlado' $rutaFallos
    }

    # ops-errores.log: el registro nuevo (JSON Lines, MOD-019): solo WARNING o más.
    $rutaErrores = Join-Path $carpetaLms 'logs\ops-errores.log'
    if (Test-Path -LiteralPath $rutaErrores) {
        $ultimosRenglones = @()
        foreach ($linea in (Cola-De-Archivo $rutaErrores 300)) {
            if (-not $linea.StartsWith('{')) { continue }
            try {
                $r = $linea | ConvertFrom-Json
                $momento = [datetimeoffset]::Parse([string](Prop $r 'ts' ''))
                if ($momento.LocalDateTime -lt $Hoy.AddDays(-$DiasDeEventos)) { continue }
                $ultimosRenglones += [pscustomobject]@{
                    Momento = $momento.LocalDateTime; Nivel = [string](Prop $r 'nivel' ''); Canal = [string](Prop $r 'canal' '')
                    Evento = [string](Prop $r 'evento' ''); Mensaje = [string](Prop $r 'mensaje' ''); Traza = [string](Prop $r 'traza' '')
                }
            } catch { }
        }
        if (@($ultimosRenglones).Count -eq 0) {
            Anotar 'OK' "ops-errores.log: sin advertencias ni errores en los últimos $DiasDeEventos días"
        } else {
            $agrupados = @($ultimosRenglones | Group-Object { "$($_.Canal)|$($_.Evento)|$(Recortar $_.Mensaje 80)" } | Sort-Object Count -Descending)
            Anotar 'INFO' "ops-errores.log: $(@($ultimosRenglones).Count) renglón(es) en $(@($agrupados).Count) forma(s) distinta(s) en los últimos $DiasDeEventos días" $rutaErrores
            foreach ($grupo in ($agrupados | Select-Object -First 5)) {
                $m = $grupo.Group | Sort-Object Momento -Descending | Select-Object -First 1
                Escribir ("            {0} {1,-8} x{2,-3} [{3}] {4}" -f $m.Momento.ToString('MM-dd HH:mm'), $m.Nivel, $grupo.Count, $m.Canal, (Recortar "$($m.Evento) $($m.Mensaje)" 100)) 'Yellow'
                if ($m.Traza -match $PatronDePermisos) { $huboFallosDePermisos = $true }
            }
        }
        $colaErrores = Cola-De-Archivo $rutaErrores 200
        if (@($colaErrores).Count -gt 0) { Guardar-Evidencia "usuarios\$($usuario.Name)\ops-errores.log" ($colaErrores -join "`n") }
    }
}
if ($perfilesRevisados -eq 0) {
    Anotar 'INFO' 'No se encontró ningún registro de fallos de la aplicación en los perfiles que esta cuenta puede leer' '' `
        'OPS aún no ha fallado, o el perfil de quien la usa es de otro usuario: ejecuta este archivo como administrador.'
}

if ($huboFallosDePermisos -or ($InstalacionPresente -and $cierresInesperados.Count -gt 0 -and -not (Test-Path -LiteralPath (Join-Path $RaizInstalacion 'App\Avacom.Lms.Ops.exe.WebView2')) -and $perfilesConLanzador -eq 0)) {
    Anotar 'AVISO' 'Causa probable del cierre: permisos de escritura del perfil de WebView2 (Microsoft Edge)' `
        'WebView2 guarda su perfil junto al .exe, y la aplicación vive en Program Files, donde quien da la clase no puede escribir.' `
        'El instalador 2.2.0 o posterior lo resuelve (perfil en la carpeta de cada usuario y una carpeta escribible junto a la aplicación). Vuelve a instalar.'
}

# ======================================================== 7 · AVACOM Contenido
Seccion '7 · AVACOM Contenido (la biblioteca de cursos)'

$estadoBiblioteca = 'desconocido'
$enlace = Leer-Json-De-Archivo $RutaEnlace
if (-not (Test-Path -LiteralPath $RutaEnlace)) {
    $instaladaLaBiblioteca = Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'AVACOM\Contenido')
    Anotar 'AVISO' $(if ($instaladaLaBiblioteca) { 'AVACOM Contenido está instalado pero no está abierto (no hay link.json)' } else { 'AVACOM Contenido no está instalado en este equipo' }) $RutaEnlace `
        'El aula funciona, pero sin cursos hasta que AVACOM Contenido esté instalado y abierto. Esta instalación no depende de él.'
    $estadoBiblioteca = 'ausente'
} elseif (-not $enlace) {
    Anotar 'AVISO' 'link.json no se pudo leer (no es JSON válido)' $RutaEnlace 'Cierra AVACOM Contenido y vuelve a abrirlo para que lo reescriba.'
    $estadoBiblioteca = 'ilegible'
} else {
    $puertoApi = [int](Prop $enlace 'apiPort' 0)
    $procesoBiblioteca = [int](Prop $enlace 'pid' 0)
    $token = [string](Prop $enlace 'token' '')
    Anotar 'INFO' "link.json: contrato $(Prop $enlace 'contract' '?') · API en el puerto $puertoApi · medios en el $(Prop $enlace 'mediaPort' '?')" $RutaEnlace
    Guardar-Evidencia 'contenido-link.json' (Ocultar-Secretos ([IO.File]::ReadAllText($RutaEnlace, [Text.Encoding]::UTF8)))

    $vivo = $true
    if ($procesoBiblioteca -gt 0) {
        $vivo = $null -ne (Get-Process -Id $procesoBiblioteca -ErrorAction SilentlyContinue)
        if (-not $vivo) {
            Anotar 'AVISO' "link.json es de una sesión anterior: el proceso $procesoBiblioteca ya no existe (AVACOM Contenido está cerrado)" '' `
                'Abre AVACOM Contenido: reescribe link.json y el aula recupera los cursos sin reiniciar nada.'
            $estadoBiblioteca = 'cerrada'
        }
    }

    if ($puertoApi -le 0 -or -not $token) {
        Anotar 'AVISO' 'link.json está incompleto (faltan apiPort o token)' '' 'Cierra AVACOM Contenido y vuelve a abrirlo.'
        $estadoBiblioteca = 'incompleta'
    } elseif ($vivo) {
        $directa = Invoke-Peticion "http://127.0.0.1:$puertoApi/v2/health" @{ 'X-Avacom-Token' = $token }
        if ($directa.Estado -eq 200) {
            Anotar 'OK' "AVACOM Contenido contesta directamente (versión $(Prop $directa.Json 'appVersion' '?'), esquema $(Prop $directa.Json 'schema' '?'))"
            $estadoBiblioteca = 'responde'
            Guardar-Evidencia 'contenido-health.json' $directa.Cuerpo
            if ("$(Prop $directa.Json 'index' '')" -eq 'rebuilding') {
                Anotar 'INFO' 'AVACOM Contenido está reconstruyendo su índice: los cursos aparecen en unos segundos'
            }
        } elseif ($directa.Estado -eq 401) {
            Anotar 'AVISO' 'AVACOM Contenido rechazó el token de link.json (401)' '' 'link.json es de otra sesión: cierra y vuelve a abrir AVACOM Contenido.'
            $estadoBiblioteca = 'rechaza'
        } elseif ($directa.Estado -gt 0) {
            Anotar 'AVISO' "AVACOM Contenido contestó $($directa.Estado)" (Recortar $directa.Cuerpo 200)
            $estadoBiblioteca = 'error'
        } else {
            Anotar 'AVISO' "AVACOM Contenido no contesta en el puerto $puertoApi" $directa.Error `
                'Abierta pero atascada, o link.json de otra sesión: ciérrala y vuelve a abrirla.'
            $estadoBiblioteca = 'sin_respuesta'
        }
    }

    # Lo que el aula ve de ella: si Contenido contesta y el aula no, el problema está en el backend.
    if ($Salud) {
        $fuente = Invoke-Peticion "http://127.0.0.1:$Puerto/api/aula/fuente/" $null 15
        if ($fuente.Estado -eq 200) {
            $disponible = (Prop $fuente.Json 'disponible' $false)
            $cursos = @(Prop $fuente.Json 'cursos_instalados' @())
            Guardar-Evidencia 'aula-fuente.json' $fuente.Cuerpo
            if ($disponible) {
                Anotar 'OK' "El aula ve AVACOM Contenido: $(@($cursos).Count) curso(s) instalado(s)"
                if ($estadoBiblioteca -eq 'responde' -and @($cursos).Count -eq 0) {
                    Anotar 'AVISO' 'AVACOM Contenido está conectado pero no tiene ningún curso instalado' '' 'Instala un paquete de curso en AVACOM Contenido.'
                }
            } elseif ($estadoBiblioteca -eq 'responde') {
                Anotar 'BLOQUEA' 'AVACOM Contenido contesta, pero el aula NO la alcanza: el problema está en el backend del aula' `
                    (Recortar "$(Prop $fuente.Json 'motivo' '')" 220) `
                    'Causas: una configuración de pruebas (sección 3), la cuenta del servicio sin permiso para leer link.json, o el servicio con un error: reinícialo y mira su registro.'
            } else {
                Anotar 'AVISO' 'El aula no ve cursos: AVACOM Contenido no está disponible' (Recortar "$(Prop $fuente.Json 'motivo' '')" 220) `
                    (Recortar "$(Prop $fuente.Json 'sugerencia' '')" 200)
            }
        } elseif ($fuente.Estado -eq 401) {
            # Es lo normal desde que el nodo exige identificarse: el estado de la biblioteca solo se ve con sesión. Lo que
            # importa (si Contenido contesta) ya se comprobó directamente arriba.
            Anotar 'INFO' 'El aula exige sesión: lo que ve de AVACOM Contenido solo se consulta desde la aplicación (la comprobación directa de arriba es la que vale)'
        } else {
            Anotar 'AVISO' "No se pudo consultar al aula qué ve de AVACOM Contenido ($($fuente.Estado))" $fuente.Error
        }
    }

    # La cuenta del servicio (SYSTEM) tiene que poder LEER link.json.
    $sistemaLee = Tiene-Derechos $RutaEnlace $SidSistema ([System.Security.AccessControl.FileSystemRights]::ReadData)
    $usuariosLeen = Tiene-Derechos $RutaEnlace $SidUsuarios ([System.Security.AccessControl.FileSystemRights]::ReadData)
    if (-not $sistemaLee -and -not $usuariosLeen) {
        Anotar 'AVISO' 'No consta que la cuenta del servicio (SYSTEM) pueda leer link.json' $RutaEnlace `
            'Si el aula no ve cursos aunque AVACOM Contenido responde, este permiso es la causa probable.'
    }
}

# ================================================================== Veredicto
Seccion 'Resultado'

$Bloqueos = @($Hallazgos | Where-Object { $_.Gravedad -eq 'BLOQUEA' })
$Avisos = @($Hallazgos | Where-Object { $_.Gravedad -eq 'AVISO' })

if (@($Bloqueos).Count -eq 0 -and @($Avisos).Count -eq 0) {
    Escribir ''
    Escribir '  Todo en orden.' 'Green'
    $CodigoSalida = 0
} else {
    if (@($Bloqueos).Count -gt 0) {
        Escribir ''
        Escribir "  $(@($Bloqueos).Count) problema(s) que hay que resolver:" 'Red'
        $n = 0
        foreach ($b in $Bloqueos) {
            $n++
            Escribir "    $n. $($b.Titulo)" 'Red'
            if ($b.Accion) { Escribir "       Qué hacer: $($b.Accion)" 'DarkGray' }
        }
    }
    if (@($Avisos).Count -gt 0) {
        Escribir ''
        Escribir "  $(@($Avisos).Count) aviso(s) que conviene mirar:" 'Yellow'
        $n = 0
        foreach ($a in $Avisos) {
            $n++
            Escribir "    $n. $($a.Titulo)" 'Yellow'
            if ($a.Accion) { Escribir "       Qué hacer: $($a.Accion)" 'DarkGray' }
        }
    }
    $CodigoSalida = if (@($Bloqueos).Count -gt 0) { 1 } else { 2 }
}

# ============================================================ Informe y paquete
$escritorio = $Salida
if (-not $escritorio) { $escritorio = [Environment]::GetFolderPath('Desktop') }
if (-not $escritorio -or -not (Test-Path -LiteralPath $escritorio)) { $escritorio = $env:TEMP }
$sello = $Hoy.ToString('yyyyMMdd-HHmmss')
$rutaInforme = Join-Path $escritorio "AVACOM-verificacion-$sello.txt"
try {
    [IO.File]::WriteAllLines($rutaInforme, [string[]]($Renglones | ForEach-Object { $_ }), (New-Object Text.UTF8Encoding($true)))
    Escribir ''
    Escribir "  Informe: $rutaInforme" 'White'
} catch {
    $rutaInforme = ''
    Escribir "  No se pudo escribir el informe: $($_.Exception.Message)" 'Yellow'
}

if ($Paquete) {
    $carpetaPaquete = Join-Path $env:TEMP "avacom-verificacion-$sello"
    $rutaZip = Join-Path $escritorio "AVACOM-verificacion-$sello.zip"
    try {
        New-Item -ItemType Directory -Force $carpetaPaquete | Out-Null
        [IO.File]::WriteAllLines((Join-Path $carpetaPaquete 'informe.txt'), [string[]]($Renglones | ForEach-Object { $_ }), (New-Object Text.UTF8Encoding($true)))
        foreach ($evidencia in $Evidencias) {
            $destino = Join-Path $carpetaPaquete ($evidencia.Nombre -replace '[:*?"<>|]', '_')
            New-Item -ItemType Directory -Force (Split-Path $destino -Parent) | Out-Null
            [IO.File]::WriteAllText($destino, [string]$evidencia.Contenido, (New-Object Text.UTF8Encoding($true)))
        }
        Compress-Archive -Path (Join-Path $carpetaPaquete '*') -DestinationPath $rutaZip -Force -ErrorAction Stop
        Escribir "  Evidencias (sin claves ni tokens): $rutaZip" 'White'
    } catch {
        Escribir "  No se pudo crear el .zip de evidencias: $($_.Exception.Message)" 'Yellow'
    } finally {
        Remove-Item -LiteralPath $carpetaPaquete -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if ($Abrir -and $rutaInforme) {
    try { Start-Process -FilePath 'notepad.exe' -ArgumentList "`"$rutaInforme`"" } catch { }
}

exit $CodigoSalida
