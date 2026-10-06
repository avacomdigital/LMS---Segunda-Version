<#
.SYNOPSIS
    Verificador de AVACOM Student para Windows: revisa el equipo, el instalador y lo ya instalado, y
    BUSCA EL ERROR EXACTO cuando algo falla. No modifica nada.

.DESCRIPTION
    Es lo que hay detrás de AVACOM-Verificar-Student.bat (el .bat lleva este PowerShell dentro: ver
    installer\student-windows\build\New-VerificadorBat.ps1). Se puede usar ANTES de instalar y
    DESPUÉS, cuando algo falla en el equipo del estudiante.

      1 · El instalador       huella SHA256 contra SHA256.txt, versión, descarga completa
      2 · El equipo           las ocho comprobaciones del asistente, ejecutadas de verdad con
                              /VOLCADO: no se instala nada (Windows pide permiso de administrador
                              una vez)
      3 · Lo instalado        versión, archivos, manifiesto, accesos directos y la comprobación del
                              lanzador (sin abrir la aplicación)
      4 · Permisos            quién puede escribir dónde: el perfil de WebView2, los datos de la
                              persona, los registros. Se prueba con la cuenta de quien ejecuta esto
      5 · La aplicación       por qué se cierra Student: Visor de eventos de Windows, el registro de
                              fallos de la aplicación y el del lanzador de CADA usuario
      6 · El aula             la dirección guardada en cada cuenta y si AVACOM OPS Master contesta

    Al terminar deja en el escritorio un informe y un .zip con las evidencias (sin claves ni
    tokens), para enviarlos sin tocar el equipo.

    No cambia la configuración ni los datos. Para probar los permisos crea y borra al instante un
    archivo temporal en las carpetas que revisa.

    No ejecutar como administrador salvo que haga falta leer el perfil de OTRO usuario de Windows:
    los permisos se prueban con la cuenta de quien usa el equipo.

.PARAMETER CarpetaDelInstalador
    Dónde buscar AVACOM-Student-Setup-*.exe y SHA256.txt (el .bat pasa su carpeta).

.PARAMETER Aula
    Dirección del aula a comprobar (por ejemplo http://192.168.0.55:8000). Si no se da, se usa la
    que Student tiene guardada en cada cuenta de Windows.

.PARAMETER SinAsistente
    No ejecuta las comprobaciones del asistente (no pide permiso de administrador).

.NOTES
    Códigos de salida:  0 todo en orden · 1 hay algo que bloquea · 2 sólo avisos
#>
[CmdletBinding()]
param(
    [string] $CarpetaDelInstalador = '',
    [string] $Instalador = '',
    [string] $Aula = '',
    # Para analizar otra carpeta de instalación (ensayos).
    [string] $RaizInstalacion = '',
    # Dónde dejar el informe y el .zip. Por defecto, el escritorio.
    [string] $Salida = '',
    [int]    $DiasDeEventos = 14,
    [switch] $SinAsistente,
    [switch] $Abrir,
    [switch] $Paquete
)

Set-StrictMode -Version Latest
# A propósito NO se usa 'Stop': un verificador que se cae en la primera comprobación que falla no
# sirve para nada. Cada bloque maneja su error.
$ErrorActionPreference = 'Continue'

$VersionVerificador = '2.3.0'
$IdInstalacion = '{4C2DB723-841F-4620-BBE3-8F5CC7E57D1D}_is1'

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
        $peticion.UserAgent = "AVACOM-Student-Verificador/$VersionVerificador"
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
    $RaizInstalacion = if ($ubicacion) { $ubicacion.TrimEnd('\') } else { Join-Path $env:ProgramFiles 'AVACOM\Student' }
}
if (-not $CarpetaDelInstalador) { $CarpetaDelInstalador = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path } }
$CarpetaDelInstalador = $CarpetaDelInstalador.TrimEnd('\', '.')
if (-not $CarpetaDelInstalador) { $CarpetaDelInstalador = '.' }
if ($CarpetaDelInstalador.EndsWith(':')) { $CarpetaDelInstalador += '\' }   # la raíz de una unidad: «C:» no es «C:\»

$CarpetaApp = Join-Path $RaizInstalacion 'App'
$ExeApp = Join-Path $CarpetaApp 'Avacom.Lms.Student.exe'
$ExeLanzador = Join-Path $RaizInstalacion 'Lanzador\Avacom.Student.Lanzador.exe'
$CarpetaWebViewJuntoAlExe = $ExeApp + '.WebView2'
$InstalacionPresente = Test-Path -LiteralPath $ExeApp

$usuariosDeWindows = @()
try { $usuariosDeWindows = @(Get-ChildItem (Join-Path $env:SystemDrive 'Users') -Directory -ErrorAction Stop |
        Where-Object { @('Public', 'Default', 'Default User', 'All Users') -notcontains $_.Name }) } catch { }

Escribir ''
Escribir "  AVACOM Student (Windows) · verificador $VersionVerificador" 'White'
Escribir "  $($Hoy.ToString('yyyy-MM-dd HH:mm:ss'))   equipo: $env:COMPUTERNAME   usuario: $env:USERNAME" 'DarkGray'
Escribir "  Windows $([Environment]::OSVersion.Version)   PowerShell $($PSVersionTable.PSVersion)" 'DarkGray'
if ($EsAdmin) {
    Escribir '  (ejecutado como administrador: las pruebas de permisos de abajo NO representan a quien usa el equipo)' 'DarkYellow'
} else {
    Escribir '  (sin permisos de administrador: así se prueban los permisos de quien usa el equipo)' 'DarkGray'
}

# ======================================================== 1 · El instalador
Seccion '1 · El instalador'

$ArchivoInstalador = $null
if ($Instalador -and (Test-Path -LiteralPath $Instalador)) {
    $ArchivoInstalador = Get-Item -LiteralPath $Instalador
} else {
    $candidatos = @(Get-ChildItem -LiteralPath $CarpetaDelInstalador -Filter 'AVACOM-Student-Setup-*.exe' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    if (@($candidatos).Count -gt 0) { $ArchivoInstalador = $candidatos[0] }
}

$VersionDelInstalador = ''
if (-not $ArchivoInstalador) {
    Anotar 'INFO' 'No hay ningún AVACOM-Student-Setup-*.exe junto a este archivo' `
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
            'Baja también SHA256.txt y déjalo junto al instalador.'
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
            Anotar 'AVISO' "SHA256.txt es de otro instalador ($primera)" '' 'Baja el SHA256.txt que corresponde a este instalador.'
        } elseif ($real -eq $esperada) {
            Anotar 'OK' 'La huella SHA256 coincide con SHA256.txt: la descarga está completa'
        } else {
            Anotar 'BLOQUEA' 'La huella NO coincide: el archivo está corrupto o es de otra versión' `
                "Esperada: $esperada`nReal:     $real" 'Vuelve a descargar el instalador.'
        }
        foreach ($etiqueta in 'Version', 'Revision', 'Arbol-limpio') {
            if ($textoHuellas -match "(?im)^$etiqueta\s+(.+)$") { Escribir "            $etiqueta`: $($Matches[1].Trim())" 'DarkGray' }
        }
    }

    # Una descarga de internet lleva la marca de zona: Windows avisa de «editor desconocido» (SmartScreen).
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
            Anotar 'INFO' "Ya está instalada la misma versión ($VersionInstalada): instalar de nuevo la reinstala y conserva los datos de cada persona"
        } else {
            Anotar 'INFO' "Ya está instalada la versión ${VersionInstalada}: este instalador la actualizará a la $nueva" `
                'Se conservan la dirección del aula y el trabajo pendiente; si algo falla se vuelve a la versión anterior.'
        }
    }
}

# ================================================= 2 · Comprobaciones del equipo
Seccion '2 · El equipo (las comprobaciones del asistente, sin instalar nada)'

if ($SinAsistente -or -not $ArchivoInstalador) {
    Anotar 'INFO' $(if ($SinAsistente) { 'Se omiten las comprobaciones del asistente (-SinAsistente)' } else { 'Sin instalador no hay comprobaciones del asistente' })
} else {
    $carpetaTemporal = Join-Path $env:TEMP 'avacom-verificar-student'
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
            Anotar 'OK' 'El equipo está listo para instalar AVACOM Student'
        } elseif ($resultado) {
            Anotar 'BLOQUEA' 'El equipo NO está listo para instalar' ($resultado -replace '^Resultado:\s*', '')
        }
        Guardar-Evidencia 'asistente-comprobaciones.txt' ($lineasVolcado -join "`n")
    } else {
        Anotar 'AVISO' 'El asistente no llegó a escribir sus comprobaciones' '' 'Si cancelaste el permiso de administrador, vuelve a ejecutar este archivo.'
    }
}

# ====================================================== 3 · Lo ya instalado
Seccion '3 · Lo que hay instalado en este equipo'

if (-not $InstalacionPresente -and -not $VersionInstalada) {
    Anotar 'INFO' 'AVACOM Student no está instalado en este equipo' "Se buscó en $RaizInstalacion"
} else {
    if ($VersionInstalada) { Anotar 'INFO' "Versión instalada (según Windows): $VersionInstalada" } else {
        Anotar 'AVISO' 'No consta en «Aplicaciones instaladas» de Windows' '' 'Si lo instalaste con este instalador, vuelve a instalar: así se registra para actualizarlo y desinstalarlo.'
    }

    foreach ($par in @(
        @($ExeApp, 'La aplicación (Avacom.Lms.Student.exe) está en su carpeta'),
        @((Join-Path $CarpetaApp 'hostfxr.dll'), 'El runtime de .NET viaja dentro de la aplicación (hostfxr.dll)'),
        @((Join-Path $CarpetaApp 'Microsoft.WindowsAppRuntime.dll'), 'El Windows App SDK viaja dentro de la aplicación'),
        @($ExeLanzador, 'El lanzador (el que abre el icono) está en su carpeta'))) {
        if (Test-Path -LiteralPath $par[0]) { Anotar 'OK' $par[1] } else { Anotar 'BLOQUEA' "Falta: $($par[1])" $par[0] 'Vuelve a instalar AVACOM Student.' }
    }

    $versionDelExe = ''
    if (Test-Path -LiteralPath $ExeApp) {
        $versionDelExe = [string](Get-Item -LiteralPath $ExeApp).VersionInfo.FileVersion
        Anotar 'INFO' "Versión que declara la aplicación: $versionDelExe"
        if ($VersionInstalada -and $versionDelExe -and ($versionDelExe -replace '\.0$', '') -ne $VersionInstalada) {
            Anotar 'AVISO' "La aplicación ($versionDelExe) no es la versión que Windows tiene registrada ($VersionInstalada)" '' 'Una actualización quedó a medias: vuelve a instalar.'
        }
    }

    $archivoManifiesto = Join-Path $RaizInstalacion 'manifiesto.json'
    $manifiesto = Leer-Json-De-Archivo $archivoManifiesto
    if ($manifiesto) {
        Anotar 'INFO' "Manifiesto: versión $(Prop $manifiesto 'version' '?') · revisión $(Prop $manifiesto 'revision' '?') · empaquetado $(Prop $manifiesto 'empaquetado' '?')"
        if ((Prop $manifiesto 'arbol_limpio' $true) -eq $false) {
            Anotar 'INFO' 'El instalador se compiló con cambios sin confirmar en git (consta en manifiesto.json)'
        }
        Guardar-Evidencia 'manifiesto.json' ([IO.File]::ReadAllText($archivoManifiesto, [Text.Encoding]::UTF8))
    } else {
        Anotar 'AVISO' 'No se pudo leer manifiesto.json' $archivoManifiesto
    }

    # Los accesos directos: el del escritorio no es una opción, se crea siempre.
    $escritorioComun = [Environment]::GetFolderPath('CommonDesktopDirectory')
    $acceso = Join-Path $escritorioComun 'AVACOM Student.lnk'
    if (Test-Path -LiteralPath $acceso) {
        try {
            $objetivo = (New-Object -ComObject WScript.Shell).CreateShortcut($acceso)
            Anotar 'OK' 'El icono de AVACOM Student está en el escritorio de todas las cuentas' "$($objetivo.TargetPath) $($objetivo.Arguments)"
            if ($objetivo.TargetPath -and -not (Test-Path -LiteralPath $objetivo.TargetPath)) {
                Anotar 'BLOQUEA' 'El icono del escritorio apunta a un archivo que ya no existe' $objetivo.TargetPath 'Vuelve a instalar AVACOM Student.'
            }
        } catch { Anotar 'INFO' 'El icono del escritorio existe (no se pudo leer su destino)' }
    } else {
        Anotar 'AVISO' 'No está el icono de AVACOM Student en el escritorio de todas las cuentas' $acceso 'Vuelve a instalar AVACOM Student: el icono se crea siempre.'
    }

    # El lanzador comprueba lo instalado sin abrir la aplicación (lo mismo que hace el asistente al terminar).
    if (Test-Path -LiteralPath $ExeLanzador) {
        $archivoVerif = Join-Path $env:TEMP "avacom-student-lanzador-$([guid]::NewGuid().ToString('N').Substring(0, 8)).txt"
        try {
            $p = Start-Process -FilePath $ExeLanzador -ArgumentList 'verificar', "`"$archivoVerif`"" -Wait -PassThru -WindowStyle Hidden
            $lineasLanzador = if (Test-Path -LiteralPath $archivoVerif) { @(Get-Content -LiteralPath $archivoVerif -Encoding UTF8) } else { @() }
            foreach ($l in $lineasLanzador) {
                if ($l.StartsWith('ok: ')) { Anotar 'OK' "Lanzador: $($l.Substring(4))" }
                elseif ($l.StartsWith('aviso: ')) { Anotar 'AVISO' "Lanzador: $($l.Substring(7))" }
                elseif ($l.StartsWith('falla: ')) { Anotar 'BLOQUEA' "Lanzador: $($l.Substring(7))" '' 'Vuelve a instalar AVACOM Student.' }
            }
            if (@($lineasLanzador).Count -eq 0) { Anotar 'AVISO' "El lanzador no escribió su comprobación (código $($p.ExitCode))" }
            Guardar-Evidencia 'lanzador-verificar.txt' ($lineasLanzador -join "`n")
        } catch {
            Anotar 'AVISO' 'No se pudo ejecutar el lanzador' $_.Exception.Message
        } finally { Remove-Item -LiteralPath $archivoVerif -Force -ErrorAction SilentlyContinue }
    }

    # Ni servicio ni puerto: Student solo conecta hacia fuera.
    $servicios = @()
    try { $servicios = @(Get-Service -ErrorAction Stop | Where-Object { $_.Name -like 'AVACOM*Student*' }) } catch { }
    if (@($servicios).Count -eq 0) { Anotar 'OK' 'Student no tiene servicio de Windows ni abre puertos (solo conecta hacia la OPS), como debe ser' }
    else { Anotar 'AVISO' "Hay un servicio con nombre de Student ($($servicios[0].Name)); este producto no instala servicios" }
}

# ======================================================== 4 · Permisos
Seccion '4 · Permisos de escritura y lectura'

if ($InstalacionPresente) {
    # La carpeta de la aplicación es de SOLO LECTURA para los usuarios: nadie cambia binarios.
    $escribeEnApp = Probar-Escritura $CarpetaApp
    if ($EsAdmin) {
        Anotar 'INFO' 'Ejecutado como administrador: no se puede probar que los usuarios NO escriben en la carpeta de la aplicación' 'Vuelve a ejecutar sin administrador.'
    } elseif ($escribeEnApp -eq 'denegado') {
        Anotar 'OK' 'La carpeta de la aplicación es de solo lectura para esta cuenta (nadie puede cambiar los binarios)'
    } elseif ($escribeEnApp -eq 'si') {
        Anotar 'AVISO' 'Esta cuenta puede ESCRIBIR en la carpeta de la aplicación' $CarpetaApp 'Los usuarios no deberían poder cambiar los binarios: vuelve a instalar.'
    }

    # La red de seguridad de WebView2: junto al ejecutable, escribible por los usuarios.
    if (Test-Path -LiteralPath $CarpetaWebViewJuntoAlExe) {
        $r = Probar-Escritura $CarpetaWebViewJuntoAlExe
        if ($r -eq 'si') { Anotar 'OK' 'La carpeta de WebView2 junto a la aplicación es escribible (red de seguridad si se abre sin el icono)' }
        else { Anotar 'BLOQUEA' "Esta cuenta NO puede escribir en la carpeta de WebView2 junto a la aplicación ($r)" $CarpetaWebViewJuntoAlExe `
            'Si la aplicación se abre sin el icono, se cerrará al abrir una lección. Vuelve a instalar AVACOM Student.' }
    } else {
        Anotar 'AVISO' 'No existe la carpeta de WebView2 junto a la aplicación' $CarpetaWebViewJuntoAlExe 'Se crea al instalar la versión 2.3.0 o posterior. Vuelve a instalar.'
    }
}

# Lo de CADA cuenta de Windows: el perfil de WebView2 del lanzador, los datos de Student y los registros.
$perfilesSinAcceso = @()
$PatronDePermisos = 'UnauthorizedAccess|Acceso denegado|Access is denied|0x80070005|E_ACCESSDENIED|WebView2|CoreWebView2|EnsureCoreWebView2'
$huboFallosDePermisos = $false
$perfilesConLanzador = 0
$direccionesGuardadas = New-Object System.Collections.Generic.List[object]

foreach ($usuario in $usuariosDeWindows) {
    $local = Join-Path $usuario.FullName 'AppData\Local'
    try { $null = Get-ChildItem -LiteralPath $usuario.FullName -ErrorAction Stop } catch { $perfilesSinAcceso += $usuario.Name; continue }

    $perfil = Join-Path $local 'AVACOM\Student\WebView2'
    $datos = Join-Path $local 'User Name\com.avacom.lms.student'
    $registros = Join-Path $local 'AVACOM\lms'
    if (-not (Test-Path -LiteralPath (Join-Path $local 'AVACOM\Student')) -and -not (Test-Path -LiteralPath $datos) -and -not (Test-Path -LiteralPath $registros)) { continue }

    Escribir ''
    Escribir "  Usuario de Windows: $($usuario.Name)" 'White'
    $esEsteUsuario = ($usuario.Name -eq $env:USERNAME)

    if (Test-Path -LiteralPath $perfil) {
        $perfilesConLanzador++
        if ($esEsteUsuario) {
            $r = Probar-Escritura $perfil
            if ($r -eq 'si') { Anotar 'OK' 'Perfil de WebView2 de esta cuenta: se puede escribir' $perfil } else { Anotar 'BLOQUEA' "Perfil de WebView2 de esta cuenta: no se puede escribir ($r)" $perfil 'Las lecciones con audio, video o PDF cerrarán la aplicación. Borra esa carpeta o vuelve a instalar.' }
        } else { Anotar 'INFO' 'Tiene perfil de WebView2 propio (lo creó el icono)' $perfil }
    } else {
        Anotar 'INFO' 'Todavía no hay perfil de WebView2 de esta cuenta (se crea al abrir Student con el icono)'
    }

    if (Test-Path -LiteralPath $datos) {
        if ($esEsteUsuario) {
            $r = Probar-Escritura (Join-Path $datos 'Data')
            if ($r -eq 'si') { Anotar 'OK' 'Datos de Student de esta cuenta (dirección del aula, respuestas pendientes): se pueden escribir' $datos }
            elseif ($r -eq 'no existe') { Anotar 'INFO' 'Datos de Student de esta cuenta: todavía sin carpeta Data' $datos }
            else { Anotar 'BLOQUEA' "Datos de Student de esta cuenta: no se pueden escribir ($r)" $datos 'Student no podrá guardar la cola de respuestas: corrige los permisos de esa carpeta.' }
        } else { Anotar 'INFO' 'Tiene datos de Student guardados' $datos }

        # La dirección del aula que Student tiene guardada (Preferences: {"": {"student_server": ...}}).
        # (ConvertFrom-Json de PowerShell 5.1 se atraganta con la clave vacía: se lee con el serializador de .NET.)
        $servidor = ''
        try {
            Add-Type -AssemblyName System.Web.Extensions -ErrorAction Stop
            $texto = [IO.File]::ReadAllText((Join-Path $datos 'Settings\preferences.dat'), [Text.Encoding]::UTF8).TrimStart([char]0xFEFF)
            $raizPreferencias = (New-Object System.Web.Script.Serialization.JavaScriptSerializer).DeserializeObject($texto)
            if ($raizPreferencias -and $raizPreferencias.ContainsKey('') -and $raizPreferencias[''].ContainsKey('student_server')) {
                $servidor = [string]$raizPreferencias['']['student_server']
            }
        } catch { }
        if ($servidor) { $direccionesGuardadas.Add([pscustomobject]@{ Usuario = $usuario.Name; Direccion = $servidor }) }
        $cola = Join-Path $datos 'Data\cola-respuestas.json'
        if (Test-Path -LiteralPath $cola) {
            $kb = [math]::Round((Get-Item -LiteralPath $cola).Length / 1KB, 1)
            if ($kb -gt 1) { Anotar 'INFO' "Hay respuestas que todavía no llegaron a la OPS ($kb KB en la cola)" 'No desinstales ni borres los datos hasta que Student se conecte y las entregue.' }
        }
    }

    if (Test-Path -LiteralPath $registros) {
        if ($esEsteUsuario) {
            $r = Probar-Escritura $registros
            if ($r -eq 'si') { Anotar 'OK' 'Carpeta de registros de la aplicación (AVACOM\lms): se puede escribir' $registros }
            else { Anotar 'AVISO' "Carpeta de registros de la aplicación: no se puede escribir ($r)" $registros 'Student no podrá dejar constancia de sus fallos.' }
        }
    }
}
if (@($perfilesSinAcceso).Count -gt 0) {
    Anotar 'INFO' "No se pudieron leer los perfiles de: $($perfilesSinAcceso -join ', ')" '' 'Ejecuta este archivo como administrador para revisarlos.'
}

# ================================================ 5 · La aplicación
Seccion '5 · La aplicación de Student: por qué se cierra'

$abiertas = @()
try { $abiertas = @(Get-Process -Name 'Avacom.Lms.Student' -ErrorAction Stop) } catch { }
if (@($abiertas).Count -gt 0) {
    foreach ($p in $abiertas) {
        $respondiendo = try { $p.Responding } catch { $true }
        $inicioTexto = try { $p.StartTime.ToString('HH:mm:ss') } catch { '?' }
        Anotar 'INFO' "AVACOM Student está abierto (pid $($p.Id), desde $inicioTexto)$(if (-not $respondiendo) { ' y NO responde' })"
    }
} else {
    Anotar 'INFO' 'AVACOM Student no está abierto ahora mismo'
}

# Visor de eventos de Windows (Aplicación). 1000 = Application Error, 1002 = Application Hang,
# 1026 = .NET Runtime, 1001 = Windows Error Reporting.
$eventosDeLaApp = New-Object System.Collections.Generic.List[object]
try {
    $crudos = @(Get-WinEvent -FilterHashtable @{ LogName = 'Application'; Id = 1000, 1001, 1002, 1026; StartTime = $Hoy.AddDays(-$DiasDeEventos) } -ErrorAction Stop)
    foreach ($e in $crudos) {
        $texto = ''
        try { $texto = [string]$e.Message } catch { }
        if ($texto -notmatch 'Avacom\.Lms\.Student|Avacom\.Student\.Lanzador') { continue }
        $propiedades = @($e.Properties | ForEach-Object { [string]$_.Value })
        $eventosDeLaApp.Add([pscustomobject]@{ Momento = $e.TimeCreated; Id = $e.Id; Proveedor = $e.ProviderName; Texto = $texto; Propiedades = $propiedades })
    }
} catch {
    if ($_.Exception.Message -notmatch 'No events were found|No se encontraron') {
        Anotar 'AVISO' 'No se pudo leer el Visor de eventos de Windows' $_.Exception.Message
    }
}

$FallosPorUsuario = @{}
foreach ($usuario in $usuariosDeWindows) {
    $rutaDeFallos = Join-Path $usuario.FullName 'AppData\Local\AVACOM\lms\fallos-student.log'
    if (Test-Path -LiteralPath $rutaDeFallos) { $FallosPorUsuario[$usuario.Name] = Leer-Fallos $rutaDeFallos $Hoy.AddDays(-$DiasDeEventos) }
}

$cierresInesperados = @($eventosDeLaApp | Where-Object { $_.Id -in 1000, 1002, 1026 } | Sort-Object Momento -Descending)
if (@($cierresInesperados).Count -eq 0) {
    Anotar 'OK' "Windows no registró cierres inesperados de AVACOM Student en los últimos $DiasDeEventos días"
} else {
    Anotar 'AVISO' "Windows registró $(@($cierresInesperados).Count) cierre(s) inesperado(s) de AVACOM Student en los últimos $DiasDeEventos días"
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
        $causa = $null; $deQuien = ''
        foreach ($nombreUsuario in $FallosPorUsuario.Keys) {
            foreach ($f in $FallosPorUsuario[$nombreUsuario]) {
                $segundos = ($e.Momento - $f.Momento).TotalSeconds
                if ($segundos -lt -5 -or $segundos -gt 20) { continue }
                if (-not $causa -or [math]::Abs($segundos) -lt [math]::Abs(($e.Momento - $causa.Momento).TotalSeconds)) { $causa = $f; $deQuien = $nombreUsuario }
            }
        }
        if ($causa) { Escribir "                 la aplicación anotó ($deQuien · $($causa.Origen)): $(Recortar $causa.Excepcion 150)" 'White' }
    }
    if (@($cierresInesperados | Where-Object { $_.Id -eq 1000 -and @($_.Propiedades).Count -gt 6 -and $_.Propiedades[6] -match 'c000027b' }).Count -gt 0) {
        Escribir '            0xc000027b en Microsoft.UI.Xaml.dll es la firma de CUALQUIER excepción no controlada de la interfaz:' 'DarkGray'
        Escribir '            el Visor no dice cuál. La causa exacta queda en fallos-student.log (justo debajo).' 'DarkGray'
    }
}
if ($eventosDeLaApp.Count -gt 0) {
    Guardar-Evidencia 'eventos-de-windows.txt' (($eventosDeLaApp | Sort-Object Momento -Descending | ForEach-Object {
        "[{0}] {1} id {2}`n{3}`n" -f $_.Momento.ToString('yyyy-MM-dd HH:mm:ss'), $_.Proveedor, $_.Id, $_.Texto }) -join "`n")
}

$perfilesRevisados = 0
foreach ($usuario in $usuariosDeWindows) {
    $carpetaLms = Join-Path $usuario.FullName 'AppData\Local\AVACOM\lms'
    $carpetaStudent = Join-Path $usuario.FullName 'AppData\Local\AVACOM\Student'
    if (-not (Test-Path -LiteralPath $carpetaLms) -and -not (Test-Path -LiteralPath $carpetaStudent)) { continue }
    $perfilesRevisados++
    Escribir ''
    Escribir "  Usuario de Windows: $($usuario.Name)" 'White'

    $rutaFallos = Join-Path $carpetaLms 'fallos-student.log'
    if (Test-Path -LiteralPath $rutaFallos) {
        $info = Get-Item -LiteralPath $rutaFallos
        $entradas = @($FallosPorUsuario[$usuario.Name])
        if (@($entradas).Count -eq 0) {
            Anotar 'OK' "fallos-student.log: sin fallos en los últimos $DiasDeEventos días ($([math]::Round($info.Length / 1KB)) KB en total)"
        } else {
            $grupos = @($entradas | Group-Object { "$($_.Origen)|$(Recortar $_.Excepcion 120)" } | Sort-Object { ($_.Group | Measure-Object Momento -Maximum).Maximum } -Descending)
            Anotar 'AVISO' "fallos-student.log: $(@($entradas).Count) fallo(s) en $(@($grupos).Count) forma(s) distinta(s) en los últimos $DiasDeEventos días" $rutaFallos
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
            '[' + $_.Momento.ToString('yyyy-MM-dd HH:mm:ss') + '] ' + $_.Origen + "`n" + (($_.Texto -split "`n" | Select-Object -First 25) -join "`n") + "`n" }) -join "`n"
        if ($ultimas) { Guardar-Evidencia "usuarios\$($usuario.Name)\fallos-student.log (ultimos)" $ultimas }
    } else {
        Anotar 'INFO' 'No hay fallos-student.log: Student no ha dejado ningún fallo no controlado' $rutaFallos
    }

    $rutaErrores = Join-Path $carpetaLms 'logs\student-errores.log'
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
                    Evento = [string](Prop $r 'evento' ''); Mensaje = [string](Prop $r 'mensaje' ''); Traza = [string](Prop $r 'traza' '') }
            } catch { }
        }
        if (@($ultimosRenglones).Count -eq 0) {
            Anotar 'OK' "student-errores.log: sin advertencias ni errores en los últimos $DiasDeEventos días"
        } else {
            $agrupados = @($ultimosRenglones | Group-Object { "$($_.Canal)|$($_.Evento)|$(Recortar $_.Mensaje 80)" } | Sort-Object Count -Descending)
            Anotar 'INFO' "student-errores.log: $(@($ultimosRenglones).Count) renglón(es) en $(@($agrupados).Count) forma(s) distinta(s) en los últimos $DiasDeEventos días" $rutaErrores
            foreach ($grupo in ($agrupados | Select-Object -First 5)) {
                $m = $grupo.Group | Sort-Object Momento -Descending | Select-Object -First 1
                Escribir ("            {0} {1,-8} x{2,-3} [{3}] {4}" -f $m.Momento.ToString('MM-dd HH:mm'), $m.Nivel, $grupo.Count, $m.Canal, (Recortar "$($m.Evento) $($m.Mensaje)" 100)) 'Yellow'
                if ($m.Traza -match $PatronDePermisos) { $huboFallosDePermisos = $true }
            }
        }
        $colaErrores = Cola-De-Archivo $rutaErrores 200
        if (@($colaErrores).Count -gt 0) { Guardar-Evidencia "usuarios\$($usuario.Name)\student-errores.log" ($colaErrores -join "`n") }
    }

    # Lo que hizo el icono: perfil de WebView2 elegido, pid, y si la aplicación se cerró al abrirse.
    $rutaLanzador = Join-Path $carpetaStudent 'lanzador.log'
    if (Test-Path -LiteralPath $rutaLanzador) {
        $colaLanzador = Cola-De-Archivo $rutaLanzador 60
        $cerrada = @($colaLanzador | Where-Object { $_ -match 'se cerro a los pocos segundos|ADVERTENCIA|No se pudo abrir|No se encontro la aplicacion' })
        if (@($cerrada).Count -gt 0) {
            Anotar 'AVISO' 'El lanzador anotó problemas al abrir la aplicación' (($cerrada | Select-Object -Last 3 | ForEach-Object { Recortar $_ 200 }) -join "`n") $rutaLanzador
            if (($cerrada -join ' ') -match 'perfil de WebView2') { $huboFallosDePermisos = $true }
        } else {
            Anotar 'OK' 'lanzador.log: el icono abrió la aplicación sin problemas' $rutaLanzador
        }
        Guardar-Evidencia "usuarios\$($usuario.Name)\lanzador.log (cola)" ($colaLanzador -join "`n")
    }
}
if ($perfilesRevisados -eq 0) {
    Anotar 'INFO' 'No se encontró ningún registro de Student en los perfiles que esta cuenta puede leer' '' 'Student aún no se ha abierto, o el perfil de quien lo usa es de otro usuario: ejecuta este archivo como administrador.'
}

if ($huboFallosDePermisos -or ($InstalacionPresente -and $cierresInesperados.Count -gt 0 -and -not (Test-Path -LiteralPath $CarpetaWebViewJuntoAlExe) -and $perfilesConLanzador -eq 0)) {
    Anotar 'AVISO' 'Causa probable del cierre: permisos de escritura del perfil de WebView2 (Microsoft Edge)' `
        'WebView2 guarda su perfil junto al .exe, y la aplicación vive en Program Files, donde quien usa el equipo no puede escribir.' `
        'El instalador de Student lo resuelve (perfil en la carpeta de cada usuario y una carpeta escribible junto a la aplicación). Abre Student SIEMPRE con el icono, o vuelve a instalar.'
}

# ======================================================== 6 · El aula
Seccion '6 · El aula (AVACOM OPS Master)'

$direcciones = New-Object System.Collections.Generic.List[object]
if ($Aula) { $direcciones.Add([pscustomobject]@{ Usuario = '(indicada)'; Direccion = $Aula }) }
else { foreach ($d in $direccionesGuardadas) { $direcciones.Add($d) } }

if ($direcciones.Count -eq 0) {
    Anotar 'INFO' 'Student todavía no tiene guardada la dirección del aula en ninguna cuenta que se pueda leer' '' `
        'La primera vez que se abre, Student pide la dirección que muestra AVACOM OPS Master (algo como http://192.168.0.55:8000). También puedes pasarla a este archivo: AVACOM-Verificar-Student.bat http://192.168.0.55:8000'
}
$yaProbadas = @{}
foreach ($d in $direcciones) {
    $texto = ([string]$d.Direccion).Trim()
    if (-not $texto) { continue }
    if (-not ($texto -match '^[a-z]+://')) { $texto = "http://$texto" }
    $texto = $texto.TrimEnd('/')
    if ($yaProbadas.ContainsKey($texto)) { continue }
    $yaProbadas[$texto] = $true
    Escribir ''
    Escribir "  Dirección del aula: $texto   (cuenta: $($d.Usuario))" 'White'

    if ($texto -match '^http://(127\.0\.0\.1|localhost)(:|$)' -and -not (Test-Path -LiteralPath (Join-Path $env:ProgramFiles 'AVACOM\OPS Master'))) {
        Anotar 'AVISO' 'La dirección apunta a ESTE mismo equipo (127.0.0.1) y aquí no está AVACOM OPS Master' '' `
            'En un equipo de estudiante la dirección debe ser la de la OPS en la red del aula (algo como http://192.168.0.55:8000).'
    }

    $salud = Invoke-Peticion "$texto/health/" $null 8
    if ($salud.Estado -eq 200 -and (Prop $salud.Json 'componente' '') -eq 'avacom-lms-backend') {
        $accesoSalud = Prop $salud.Json 'acceso' $null
        $errorAcceso = [string](Prop $accesoSalud 'error' '')
        if ($errorAcceso) { Anotar 'AVISO' 'La OPS responde, pero su módulo de acceso no puede usar la base de datos' (Recortar $errorAcceso 200) 'Avisa a quien administra la OPS.' }
        else { Anotar 'OK' 'AVACOM OPS Master contesta en esa dirección (/health/)' }
        if ((Prop $accesoSalud 'instalado' $true) -eq $false) {
            Anotar 'AVISO' 'La OPS todavía no tiene organización: nadie puede entrar desde las tabletas' '' 'En la OPS, abre AVACOM OPS Master y haz el primer arranque (organización, administrador y PIN maestro).'
        }
        $estadoPin = [string](Prop $accesoSalud 'pin_maestro' '')
        if ((Prop $accesoSalud 'instalado' $true) -eq $true -and $estadoPin -eq 'sin_configurar') {
            Anotar 'INFO' 'La OPS no tiene PIN maestro: en Student no aparece «Crear mi usuario» de los profesores (los alumnos no lo necesitan)'
        }
        $configuracion = Invoke-Peticion "$texto/api/acceso/configuracion/" $null 8
        if ($configuracion.Estado -eq 200) {
            if ((Prop $configuracion.Json 'sesion_obligatoria' $true) -eq $true) {
                Anotar 'OK' 'El aula exige identificarse: el estudiante toca su nombre y marca su PIN, entra como visitante o crea su usuario'
            } else {
                Anotar 'INFO' 'El aula está en modo prototipo (no exige sesión): Student pedirá solo «Tu nombre»'
            }
        }
        Guardar-Evidencia "aula-health ($($d.Usuario)).json" $salud.Cuerpo
    } elseif ($salud.Estado -gt 0) {
        Anotar 'BLOQUEA' "En esa dirección contesta algo que no es el backend de AVACOM ($($salud.Estado))" (Recortar $salud.Cuerpo 200) 'Revisa la dirección: debe ser la que muestra AVACOM OPS Master.'
    } else {
        Anotar 'BLOQUEA' 'La OPS no contesta en esa dirección' $salud.Error `
            'Comprueba que este equipo y la OPS están en la misma red, que la dirección es la que muestra OPS y que la red del aula es «privada» en la OPS (Windows bloquea la entrada en redes públicas).'
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
$rutaInforme = Join-Path $escritorio "AVACOM-Student-verificacion-$sello.txt"
try {
    [IO.File]::WriteAllLines($rutaInforme, [string[]]($Renglones | ForEach-Object { $_ }), (New-Object Text.UTF8Encoding($true)))
    Escribir ''
    Escribir "  Informe: $rutaInforme" 'White'
} catch {
    $rutaInforme = ''
    Escribir "  No se pudo escribir el informe: $($_.Exception.Message)" 'Yellow'
}

if ($Paquete) {
    $carpetaPaquete = Join-Path $env:TEMP "avacom-student-verificacion-$sello"
    $rutaZip = Join-Path $escritorio "AVACOM-Student-verificacion-$sello.zip"
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
