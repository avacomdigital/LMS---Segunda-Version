<#
.SYNOPSIS
    Construye el instalador de AVACOM Student para Windows desde el codigo de este repositorio.

.DESCRIPTION
    Es otro producto que AVACOM OPS Master: su propio instalador, su propio identificador de
    instalacion, su propia carpeta de entrega (installer\student-windows\latest). Comparten solo la
    fuente de la version (installer\version.json), para poder saber si un OPS y un Student son
    compatibles.

    El script hace, en orden:

        1. Comprueba las herramientas del equipo de compilacion.
        2. Toma la huella del codigo que va a empaquetar.
        3. Publica AVACOM Student (.NET MAUI, Windows) con el runtime de .NET y el Windows App SDK dentro.
        4. Publica el lanzador (perfil de WebView2 por persona).
        5. Escribe el manifiesto de lo empaquetado y comprueba el paquete (el lanzador lo verifica).
        6. Ejecuta las comprobaciones del asistente en este Windows (arnes, sin instalar nada).
        7. Genera el verificador de un solo archivo (.bat).
        8. Compila el asistente con Inno Setup y demuestra que es la version actual.

    Lo que se empaqueta es SIEMPRE lo que hay ahora en el repositorio: el script publica desde el
    codigo fuente y no reutiliza binarios sueltos, y lo DEMUESTRA con huellas tomadas al empezar y al
    terminar (si el codigo cambio mientras se compilaba, el .exe se descarta).

.PARAMETER OmitirApp
    Reutiliza la publicacion de la app de dist\student-windows\staging, que es la etapa lenta. Solo se
    acepta si su huella es la del codigo actual.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\student-windows\build\Build-StudentInstaller.ps1
#>
[CmdletBinding()]
param(
    [string] $Version,
    [string] $Configuracion = 'Release',
    [switch] $OmitirApp,
    [switch] $PermitirCambiosDuranteLaCompilacion
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$base = Join-Path $raiz 'installer\student-windows'
$staging = Join-Path $raiz 'dist\student-windows\staging'
$salida = Join-Path $base 'latest'
$iss = Join-Path $base 'src\AvacomStudent.iss'
$props = Join-Path $PSScriptRoot 'Distribucion.props'
$nombreInstalador = 'AVACOM-Student-Setup'

if (-not $Version) {
    $Version = (Get-Content (Join-Path $raiz 'installer\version.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
}
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)$') { throw "Version '$Version' no es major.minor.patch." }
$codigoVersion = [int]$Matches[1] * 10000 + [int]$Matches[2] * 100 + [int]$Matches[3]

function Paso([string] $texto) { Write-Host ''; Write-Host "==> $texto" -ForegroundColor Cyan }
function Fallar([string] $texto) { throw $texto }

# Huella de un conjunto de carpetas: SHA-256 del listado ordenado de "ruta relativa | SHA-256 del contenido".
function Huella-Carpetas {
    param(
        [Parameter(Mandatory)] [string[]] $Raices,
        [string[]] $ExcluirCarpetas = @('bin', 'obj', '.venv', '__pycache__', 'node_modules', '.vs'),
        [string[]] $ExcluirArchivos = @()
    )
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $lineas = New-Object System.Collections.Generic.List[string]
    function Recorrer([string] $carpeta, [string] $baseRel) {
        foreach ($archivo in [IO.Directory]::EnumerateFiles($carpeta)) {
            $nombre = [IO.Path]::GetFileName($archivo)
            $omitir = $false
            foreach ($patron in $ExcluirArchivos) { if ($nombre -like $patron) { $omitir = $true; break } }
            if ($omitir) { continue }
            $hash = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($archivo))).Replace('-', '')
            $lineas.Add(($archivo.Substring($baseRel.Length)).ToLowerInvariant() + '|' + $hash)
        }
        foreach ($sub in [IO.Directory]::EnumerateDirectories($carpeta)) {
            if ($ExcluirCarpetas -contains [IO.Path]::GetFileName($sub)) { continue }
            Recorrer $sub $baseRel
        }
    }
    foreach ($r in $Raices) {
        if (-not (Test-Path $r)) { continue }
        $completa = (Resolve-Path $r).Path.TrimEnd('\')
        Recorrer $completa ((Split-Path $completa -Parent).TrimEnd('\') + '\')
    }
    $texto = (($lineas | Sort-Object) -join "`n")
    return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($texto))).Replace('-', '').ToLowerInvariant()
}

# Lo que decide que hay dentro de la app de Student: ella, lo que comparte con OPS y la marca.
function Huella-App {
    Huella-Carpetas -Raices @(
        (Join-Path $raiz 'src\Avacom.Lms.Student'), (Join-Path $raiz 'src\Avacom.Lms.Core'),
        (Join-Path $raiz 'src\Avacom.Lms.Ui'), (Join-Path $raiz 'assets')) -ExcluirArchivos @('*.user', '*.log')
}
# El asistente, el lanzador, el verificador y los scripts de compilacion (sin lo que la compilacion genera).
function Huella-Instalador {
    $codigo = Huella-Carpetas -ExcluirArchivos @('*.log', '*.bat', '*.exe') -Raices @(
        (Join-Path $base 'src'), (Join-Path $base 'tools'), (Join-Path $base 'build'))
    $version = (Get-FileHash (Join-Path $raiz 'installer\version.json') -Algorithm SHA256).Hash
    $sha = [System.Security.Cryptography.SHA256]::Create()
    [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes("$codigo|$version"))).Replace('-', '').ToLowerInvariant()
}

# Ejecuta un programa externo y devuelve su codigo de salida (PowerShell 5.1 trata stderr como error).
function Nativo {
    param([Parameter(Mandatory)] [string] $Ejecutable, [Parameter(Mandatory)] [string[]] $Argumentos,
          [string] $Directorio = $raiz, [int] $LineasSiFalla = 25, [switch] $Silencioso)
    $bitacora = Join-Path ([IO.Path]::GetTempPath()) ("avacom-build-" + [Guid]::NewGuid().ToString('N') + '.txt')
    try {
        $p = Start-Process -FilePath $Ejecutable -ArgumentList $Argumentos -WorkingDirectory $Directorio `
            -Wait -PassThru -NoNewWindow -RedirectStandardOutput $bitacora -RedirectStandardError "$bitacora.err"
        $texto = @(); foreach ($a in @($bitacora, "$bitacora.err")) { if (Test-Path $a) { $texto += Get-Content $a } }
        if ($p.ExitCode -ne 0 -or -not $Silencioso) {
            $n = if ($p.ExitCode -ne 0) { $LineasSiFalla } else { 4 }
            $texto | Where-Object { $_.Trim() -ne '' } | Select-Object -Last $n | ForEach-Object { Write-Host "  $_" }
        }
        return $p.ExitCode
    } finally { Remove-Item $bitacora, "$bitacora.err" -Force -ErrorAction SilentlyContinue }
}

# ------------------------------------------------------------- 1. Herramientas
Paso '1/8  Comprobando el equipo de compilacion'
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { Fallar 'No se encontro el SDK de .NET (winget install Microsoft.DotNet.SDK.10).' }
Write-Host "  .NET SDK $(dotnet --version)"
$iscc = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    'C:\Program Files\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Fallar 'No se encontro Inno Setup 6 (winget install JRSoftware.InnoSetup).' }
Write-Host "  Inno Setup: $iscc"
Write-Host "  Version del producto: $Version (de installer\version.json)"

$revision = 'sin-revision'
try { $revision = (git -C $raiz rev-parse --short HEAD 2>$null); if ($LASTEXITCODE -ne 0 -or -not $revision) { $revision = 'sin-revision' } } catch { $revision = 'sin-revision' }
Write-Host "  Revision del repositorio: $revision"

$cambiosSinConfirmar = @()
try {
    $porcelana = @(git -C $raiz status --porcelain 2>$null)
    if ($LASTEXITCODE -eq 0) {
        # Solo cuenta lo que entra en este instalador.
        $cambiosSinConfirmar = @($porcelana | ForEach-Object { if ($_.Length -gt 3) { $_.Substring(3).Trim('"') } } |
            Where-Object { $_ -match '^(src/Avacom\.Lms\.(Student|Core|Ui)/|assets/|installer/version\.json|installer/student-windows/(src|build|tools)/)' -and $_ -notmatch '/(bin|obj)/' })
    }
} catch { $cambiosSinConfirmar = @() }
$arbolLimpio = (@($cambiosSinConfirmar).Count -eq 0)
if ($arbolLimpio) { Write-Host '  Arbol de trabajo limpio (en lo que entra en este instalador): es exactamente esa revision.' }
else {
    Write-Host "  AVISO: hay $(@($cambiosSinConfirmar).Count) archivo(s) sin confirmar que entran en este instalador; se empaquetan tal como estan:" -ForegroundColor Yellow
    $cambiosSinConfirmar | Select-Object -First 12 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}

# ----------------------------------------------------------------- 2. Huellas
Paso '2/8  Tomando la huella del codigo que se va a empaquetar'
$huellaAppInicial = Huella-App
$huellaInstaladorInicial = Huella-Instalador
Write-Host "  app $($huellaAppInicial.Substring(0, 12)) · asistente $($huellaInstaladorInicial.Substring(0, 12))"

# ------------------------------------------------------------------ 3. Staging
Paso '3/8  Publicando AVACOM Student (.NET MAUI, con runtime incluido)'
if (-not $OmitirApp -and (Test-Path $staging)) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Force $staging, $salida | Out-Null

$selloApp = Join-Path $staging 'huella-app.txt'
if ($OmitirApp -and (Test-Path (Join-Path $staging 'App\Avacom.Lms.Student.exe'))) {
    Write-Host '  Publicacion OMITIDA: se reutiliza la de dist\student-windows\staging' -ForegroundColor Yellow
    $huellaPublicada = if (Test-Path $selloApp) { (Get-Content $selloApp -Raw).Trim() } else { '(sin huella)' }
    if ($huellaPublicada -ne $huellaAppInicial) {
        Fallar "La app de dist\student-windows\staging no corresponde al codigo actual (huella publicada $huellaPublicada; del codigo $huellaAppInicial). Vuelve a compilar sin -OmitirApp."
    }
} else {
    $codigo = Nativo -Ejecutable 'dotnet' -Argumentos @(
        'publish', (Join-Path $raiz 'src\Avacom.Lms.Student\Avacom.Lms.Student.csproj')
        '-c', $Configuracion, '-f', 'net10.0-windows10.0.19041.0'
        "-p:CustomBeforeMicrosoftCommonProps=$props"
        "-p:PublishDir=$staging\App\"
        "-p:Version=$Version", "-p:ApplicationDisplayVersion=$Version", "-p:ApplicationVersion=$codigoVersion"
        '--nologo', '-v', 'minimal'
    ) -Silencioso
    if ($codigo -ne 0) { Fallar 'No se pudo publicar AVACOM Student.' }
    Set-Content -Path $selloApp -Value $huellaAppInicial -Encoding ascii
}

$exeApp = Join-Path $staging 'App\Avacom.Lms.Student.exe'
if (-not (Test-Path $exeApp)) { Fallar "La publicacion no produjo $exeApp." }
if (-not (Test-Path (Join-Path $staging 'App\hostfxr.dll'))) { Fallar 'La publicacion no quedo autocontenida: falta hostfxr.dll.' }
if (-not (Test-Path (Join-Path $staging 'App\Microsoft.WindowsAppRuntime.dll'))) { Fallar 'La publicacion no incluyo el Windows App SDK autocontenido.' }
Write-Host "  App publicada: $([math]::Round(((Get-ChildItem -Recurse -File (Join-Path $staging 'App') | Measure-Object -Sum Length).Sum / 1MB),0)) MB"

# La aplicacion declara la version del producto (lo dice el propio archivo, no el script).
$versionApp = (Get-Item $exeApp).VersionInfo.FileVersion
if ($versionApp -notlike "$Version*") { Fallar "La aplicacion publicada dice ser la version $versionApp y se esperaba la $Version." }
Write-Host "  Avacom.Lms.Student.exe declara la version $versionApp."

# Compilada despues del ultimo cambio de codigo.
$ultimoCodigo = Get-ChildItem (Join-Path $raiz 'src\Avacom.Lms.Student'), (Join-Path $raiz 'src\Avacom.Lms.Core'), (Join-Path $raiz 'src\Avacom.Lms.Ui') `
    -Recurse -File -Include '*.cs', '*.xaml', '*.csproj', '*.svg', '*.png' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(bin|obj)\\' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$dllApp = Get-Item (Join-Path $staging 'App\Avacom.Lms.Student.dll') -ErrorAction SilentlyContinue
if ($dllApp -and $ultimoCodigo -and $dllApp.LastWriteTime -lt $ultimoCodigo.LastWriteTime.AddSeconds(-2)) {
    Fallar "La app empaquetada ($($dllApp.LastWriteTime)) es anterior al ultimo cambio de codigo ($($ultimoCodigo.Name), $($ultimoCodigo.LastWriteTime)): no es la version actual."
}
if ($dllApp) { Write-Host "  Avacom.Lms.Student.dll compilada el $($dllApp.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')), despues del ultimo cambio de codigo." }

# El logotipo de la plantilla de .NET MAUI no puede colarse en un producto de AVACOM.
$iconoFuente = Join-Path $raiz 'src\Avacom.Lms.Student\Resources\AppIcon\appicon.svg'
$iconoSinComentarios = [regex]::Replace((Get-Content $iconoFuente -Raw), '(?s)<!--.*?-->', '')
# Decision del 2026-10-06: Student TODAVIA lleva el icono de la plantilla (a diferencia de OPS, que ya usa el simbolo de
# AVACOM). Se avisa en cada compilacion y queda escrito en el manifiesto, pero no detiene la entrega. Arreglarlo es copiar
# los dos SVG de src\Avacom.Lms.Ops\Resources\AppIcon a los de Student (un cambio de src, que se pide aparte).
$iconoDePlantilla = ($iconoSinComentarios -match '512BD4')
if ($iconoDePlantilla) {
    Write-Host '  AVISO: el icono de Student sigue siendo el de la plantilla de .NET MAUI (cuadrado morado); se entrega asi, anotado en el manifiesto.' -ForegroundColor Yellow
}

# Imagenes de marca del asistente, desde el mismo simbolo que usa la aplicacion.
$simbolo = Join-Path $staging 'App\avacom_mark.scale-400.png'
if (-not (Test-Path $simbolo)) { Fallar "No se encontro el simbolo de AVACOM en la publicacion ($simbolo)." }
& (Join-Path $raiz 'installer\build\New-ImagenesAsistente.ps1') -SimboloPng $simbolo -Destino (Join-Path $staging 'Asistente')

# ----------------------------------------------------------------- 4. Lanzador
Paso '4/8  Publicando el lanzador'
$codigo = Nativo -Ejecutable 'dotnet' -Argumentos @(
    'publish', (Join-Path $base 'src\lanzador\Avacom.Student.Lanzador.csproj')
    '-c', $Configuracion, "-p:PublishDir=$staging\Lanzador\", "-p:Version=$Version", '--nologo', '-v', 'minimal'
) -Silencioso
if ($codigo -ne 0) { Fallar 'No se pudo publicar el lanzador.' }
Get-ChildItem (Join-Path $staging 'Lanzador') -Filter '*.pdb' -ErrorAction SilentlyContinue | Remove-Item -Force
$lanzador = Join-Path $staging 'Lanzador\Avacom.Student.Lanzador.exe'
if (-not (Test-Path $lanzador)) { Fallar "La publicacion no produjo $lanzador." }
Write-Host "  Lanzador: $([math]::Round((Get-Item $lanzador).Length / 1MB, 1)) MB"

# --------------------------------------------------------------- 5. Manifiesto
Paso '5/8  Escribiendo el manifiesto y comprobando el paquete'
$manifiesto = [ordered]@{
    producto               = 'AVACOM Student (Windows)'
    version                = $Version
    revision               = $revision
    arbol_limpio           = $arbolLimpio
    archivos_sin_confirmar = @($cambiosSinConfirmar | Select-Object -First 40)
    huella_app             = $huellaAppInicial
    huella_asistente       = $huellaInstaladorInicial
    advertencias           = @(if ($iconoDePlantilla) { 'El icono de la aplicacion es el de la plantilla de .NET MAUI (pendiente de cambiar por el simbolo de AVACOM)' })
    empaquetado            = (Get-Date).ToString('o')
    id_instalacion         = '4C2DB723-841F-4620-BBE3-8F5CC7E57D1D'
    id_aplicacion          = 'com.avacom.lms.student'
    runtime_dotnet         = 'incluido en la aplicacion (autocontenido)'
    instalacion            = 'para todo el equipo (Program Files\AVACOM\Student); datos por usuario'
    servicio               = 'ninguno'
    puertos_abiertos       = 'ninguno (Student solo hace conexiones salientes hacia la OPS)'
    carpeta_de_datos_de_cada_usuario = '%LOCALAPPDATA%\User Name\com.avacom.lms.student ; %LOCALAPPDATA%\AVACOM\Student'
}
$manifiesto | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $staging 'manifiesto.json') -Encoding utf8

@"
AVACOM Student $Version (revision $revision) - Windows

Lo instalado aqui es:

  App\        AVACOM Student, la aplicacion del estudiante. El runtime de .NET y el Windows
              App SDK van dentro: no hace falta instalar nada mas ni tener internet.
  Lanzador\   Lo que abre el icono: le da a las lecciones (WebView2) un perfil propio de cada
              persona de Windows y comprueba lo instalado.

Student solo hace conexiones SALIENTES hacia AVACOM OPS Master: no instala servicios, no abre
puertos y no toca el firewall. La primera vez, escribe la direccion del aula que muestra OPS
(algo como http://192.168.0.55:8000).

Lo que cambia con el uso NO esta en esta carpeta; vive en el perfil de cada persona de Windows:

  %LOCALAPPDATA%\User Name\com.avacom.lms.student   direccion del aula, respuestas pendientes,
                                                     material de estudio descargado
  %LOCALAPPDATA%\AVACOM\Student                      perfil de WebView2 y registro del lanzador
  %LOCALAPPDATA%\AVACOM\lms                          registros de la aplicacion (compartida con OPS)

Al actualizar se conserva todo eso. Para quitar el producto usa "Aplicaciones instaladas" de
Windows: la desinstalacion pregunta si borrar los datos de esa cuenta (por defecto, no).
"@ | Set-Content -Path (Join-Path $staging 'LEEME.txt') -Encoding utf8

# El lanzador verifica el paquete tal como lo hara en el equipo: sus carpetas hermanas.
$archivoVerif = Join-Path ([IO.Path]::GetTempPath()) 'avacom-student-verificar.txt'
Remove-Item $archivoVerif -Force -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $lanzador -ArgumentList 'verificar', "`"$archivoVerif`"" -Wait -PassThru
$lineasVerif = if (Test-Path $archivoVerif) { @(Get-Content $archivoVerif -Encoding UTF8) } else { @() }
$lineasVerif | ForEach-Object { Write-Host "  $_" }
if ($proc.ExitCode -eq 1 -or @($lineasVerif | Where-Object { $_ -like 'falla:*' }).Count -gt 0) {
    Fallar 'El lanzador no da por bueno el paquete (ver las lineas "falla:" de arriba).'
}
Remove-Item $archivoVerif -Force -ErrorAction SilentlyContinue
Write-Host "  Contenido a empaquetar: $([math]::Round(((Get-ChildItem -Recurse -File $staging | Measure-Object -Sum Length).Sum / 1MB), 0)) MB"

# ------------------------------------------------- 6. Verificacion del asistente
Paso '6/8  Verificando el codigo del asistente en este Windows'
$arnes = Join-Path $PSScriptRoot 'PruebaAsistenteStudent.exe'
$volcado = Join-Path ([IO.Path]::GetTempPath()) 'avacom-student-diagnostico-asistente.txt'
Remove-Item $arnes, $volcado -Force -ErrorAction SilentlyContinue
$codigo = Nativo -Ejecutable $iscc -Argumentos @((Join-Path $PSScriptRoot 'PruebaAsistente.iss')) -Directorio $PSScriptRoot -Silencioso
if ($codigo -ne 0) { Fallar 'El codigo del asistente no compila.' }
$ejecucion = Start-Process -FilePath $arnes -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', "/VOLCADO=$volcado" -Wait -PassThru
Remove-Item $arnes -Force -ErrorAction SilentlyContinue
if (-not (Test-Path $volcado)) { Fallar "El asistente no llego a ejecutar sus comprobaciones (codigo $($ejecucion.ExitCode))." }
$lineasV = Get-Content $volcado -Encoding UTF8
Remove-Item $volcado -Force -ErrorAction SilentlyContinue
$comprobaciones = @($lineasV | Where-Object { $_ -like 'check: *' })
if ($comprobaciones.Count -ne 8) { $lineasV | ForEach-Object { Write-Host "  $_" }; Fallar "Se esperaban 8 comprobaciones y se ejecutaron $($comprobaciones.Count)." }
if (-not ($lineasV | Where-Object { $_ -like 'Resultado:*' })) { Fallar 'El asistente no emitio un veredicto.' }
$comprobaciones | ForEach-Object { Write-Host "  $_" }
Write-Host '  Las 8 comprobaciones del asistente se ejecutaron y dieron veredicto.'

# ----------------------------------------------------------- 7. Verificador .bat
Paso '7/8  Generando el verificador de un solo archivo'
& (Join-Path $PSScriptRoot 'New-VerificadorBat.ps1') | Out-Null

# ------------------------------------------------------------ 8. Inno Setup
Paso '8/8  Compilando el asistente con Inno Setup'
Get-ChildItem $salida -Filter "$nombreInstalador-*" -ErrorAction SilentlyContinue | Remove-Item -Force
$codigo = Nativo -Ejecutable $iscc -Argumentos @(
    "/DCarpetaContenido=$staging", "/DCarpetaSalida=$salida", "/DRevision=$revision", "/DVersionProducto=$Version", $iss
) -Directorio (Split-Path $iss) -LineasSiFalla 40
if ($codigo -ne 0) { Fallar 'Inno Setup no pudo compilar el asistente.' }

$instalador = Get-ChildItem $salida -Filter "$nombreInstalador-*.exe" | Select-Object -First 1
if (-not $instalador) { Fallar 'Inno Setup termino sin producir el instalador.' }
if (Get-ChildItem $salida -Filter '*.tmp' -ErrorAction SilentlyContinue) { Fallar 'Quedo un archivo temporal de Inno Setup en la carpeta de entrega.' }
$infoExe = (Get-Item $instalador.FullName).VersionInfo
if ($infoExe.FileVersion -notlike "$Version*") { Remove-Item $instalador.FullName -Force; Fallar "El instalador producido dice ser la version $($infoExe.FileVersion) y se compilo la $Version." }
if ($instalador.Name -ne "$nombreInstalador-$Version.exe") { Remove-Item $instalador.FullName -Force; Fallar "El instalador se llama $($instalador.Name)." }

# El codigo no cambio mientras se compilaba.
$cambiaron = @()
if ((Huella-App) -ne $huellaAppInicial) { $cambiaron += 'la aplicacion' }
if ((Huella-Instalador) -ne $huellaInstaladorInicial) { $cambiaron += 'el asistente' }
if ($cambiaron.Count -gt 0) {
    if ($PermitirCambiosDuranteLaCompilacion) { Write-Host "  AVISO: cambio $($cambiaron -join ', ') mientras se compilaba; se acepto por parametro." -ForegroundColor Yellow }
    else { Remove-Item $instalador.FullName -Force; Fallar "Cambio $($cambiaron -join ', ') mientras se compilaba: el instalador se descarto. Vuelve a compilar con el repositorio quieto." }
} else { Write-Host '  El codigo no cambio durante la compilacion: el instalador es lo que habia al empezar.' }

$huella = (Get-FileHash $instalador.FullName -Algorithm SHA256).Hash
@"
$($instalador.Name)
SHA256  $huella
Version $Version
Revision $revision
Arbol-limpio $(if ($arbolLimpio) { 'si' } else { 'no (' + @($cambiosSinConfirmar).Count + ' archivos sin confirmar en lo que entra en este instalador; ver manifiesto.json)' })
Huella-app $huellaAppInicial
Huella-asistente $huellaInstaladorInicial
Empaquetado $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz'))
"@ | Set-Content -Path (Join-Path $salida 'SHA256.txt') -Encoding utf8

if (-not (Test-Path (Join-Path $salida 'AVACOM-Verificar-Student.bat'))) { Fallar 'Falta AVACOM-Verificar-Student.bat en la carpeta de entrega.' }

@"
AVACOM Student $Version para Windows (revision $revision)

  $($instalador.Name)      el instalador (no se versiona: supera los 100 MB de GitHub)
  SHA256.txt                           la huella del instalador y del codigo que lleva
  AVACOM-Verificar-Student.bat         revisa el equipo, el instalador y lo ya instalado, y busca el
                                       error exacto cuando algo falla. NO modifica nada.
  LEEME.txt                            este archivo

PARA INSTALAR: toca el instalador. Se maneja con toques: no hay que escribir nada. El runtime de .NET
y todo lo que la aplicacion necesita van dentro; no hace falta internet. Pide permiso de administrador
UNA vez, al principio.

La primera vez que se abra AVACOM Student, escribe la direccion del aula que muestra AVACOM OPS Master
(algo como http://192.168.0.55:8000).

SI ALGO FALLA (por ejemplo, la aplicacion se cierra al abrir una leccion): toca
AVACOM-Verificar-Student.bat. Deja un informe y un .zip con las evidencias en el escritorio.

Student es independiente de AVACOM OPS Master: no exige que este en el mismo equipo y no lo modifica.
"@ | Set-Content -Path (Join-Path $salida 'LEEME.txt') -Encoding utf8

Write-Host ''
Write-Host 'Instalador de Student listo' -ForegroundColor Green
Write-Host "  $($instalador.FullName)"
Write-Host "  $([math]::Round($instalador.Length / 1MB, 1)) MB"
Write-Host "  Version $Version · revision $revision · $(if ($arbolLimpio) { 'arbol limpio' } else { "$(@($cambiosSinConfirmar).Count) archivos sin confirmar" })"
Write-Host "  SHA256 $huella"
