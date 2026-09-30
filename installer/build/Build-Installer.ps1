<#
.SYNOPSIS
    Construye el instalador de AVACOM OPS Master desde el codigo de este
    repositorio.

.DESCRIPTION
    Un solo comando produce el .exe distribuible. El script hace, en orden:

        1. Comprueba las herramientas del equipo de compilacion.
        2. Publica AVACOM OPS Master (.NET MAUI) con el runtime dentro.
        3. Publica el host del backend (servicio + lanzador + preparacion).
        4. Ensambla el runtime de Python con Django, DRF, Channels y Daphne.
        5. Copia el backend tal como esta en backend\.
        6. Escribe el manifiesto de lo empaquetado.
        7. Ejecuta las comprobaciones del asistente en este Windows.
        8. Compila el asistente con Inno Setup.

    El resultado queda en installer\latest. El contenido intermedio queda en
    dist\staging, que es la "version instalable" antes de empaquetarla.

    Lo que se empaqueta es SIEMPRE lo que hay ahora en el repositorio: el
    script publica desde el codigo fuente y no reutiliza binarios sueltos.

.PARAMETER OmitirPruebas
    Salta la suite del backend. Solo para iterar; una entrega no deberia
    empaquetarse sin haberla pasado.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\build\Build-Installer.ps1
#>
[CmdletBinding()]
param(
    # Por defecto sale de installer\version.json, la fuente unica de version del producto.
    [string] $Version,
    [string] $Configuracion = 'Release',
    [string] $VersionPython = '3.12.10',
    # Que se hace con la base de datos al actualizar. Es un dato de cada version:
    #   reemplazables  la base todavia es desechable (se conserva si migra bien)
    #   protegidos     nunca se reemplaza; copia previa obligatoria y rollback
    # Al llegar el modulo de progreso y calificaciones, cambiar a 'protegidos'.
    [ValidateSet('reemplazables', 'protegidos')] [string] $PoliticaDatos = 'reemplazables',
    [switch] $OmitirPruebas,
    [switch] $OmitirApp
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$staging = Join-Path $raiz 'dist\staging'
$salida = Join-Path $raiz 'installer\latest'
$iss = Join-Path $raiz 'installer\src\AvacomOpsMaster.iss'
$props = Join-Path $PSScriptRoot 'Distribucion.props'

if (-not $Version) {
    $Version = (Get-Content (Join-Path $raiz 'installer\version.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
}

function Paso([string] $texto) {
    Write-Host ''
    Write-Host "==> $texto" -ForegroundColor Cyan
}

function Fallar([string] $texto) { throw $texto }

<#
    Ejecuta un programa externo y devuelve su codigo de salida.

    Windows PowerShell 5.1 convierte cada linea que un .exe escribe en stderr
    en un ErrorRecord; con $ErrorActionPreference = 'Stop' eso aborta el script
    aunque el programa haya terminado bien (django test, por ejemplo, escribe
    su progreso en stderr). Redirigir a archivo y esperar el proceso evita ese
    comportamiento por completo y ademas deja el detalle disponible si falla.
#>
function Nativo {
    param(
        [Parameter(Mandatory)] [string]   $Ejecutable,
        [Parameter(Mandatory)] [string[]] $Argumentos,
        [string] $Directorio = $raiz,
        [int]    $LineasSiFalla = 25,
        [switch] $Silencioso
    )

    $bitacora = Join-Path ([IO.Path]::GetTempPath()) ("avacom-build-" + [Guid]::NewGuid().ToString('N') + '.txt')
    $erroresArchivo = "$bitacora.err"
    try {
        $proceso = Start-Process -FilePath $Ejecutable -ArgumentList $Argumentos `
            -WorkingDirectory $Directorio -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $bitacora -RedirectStandardError $erroresArchivo

        $texto = @()
        foreach ($archivo in @($bitacora, $erroresArchivo)) {
            if (Test-Path $archivo) { $texto += Get-Content $archivo }
        }

        if ($proceso.ExitCode -ne 0 -or -not $Silencioso) {
            $cuantas = if ($proceso.ExitCode -ne 0) { $LineasSiFalla } else { 4 }
            $texto | Where-Object { $_.Trim() -ne '' } | Select-Object -Last $cuantas |
                ForEach-Object { Write-Host "  $_" }
        }
        return $proceso.ExitCode
    } finally {
        Remove-Item $bitacora, $erroresArchivo -Force -ErrorAction SilentlyContinue
    }
}

# --------------------------------------------------------------- 1. Herramientas
Paso '1/8  Comprobando el equipo de compilacion'

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Fallar 'No se encontro el SDK de .NET. Instalalo con: winget install Microsoft.DotNet.SDK.10'
}
Write-Host "  .NET SDK $(dotnet --version)"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Fallar 'No se encontro Python. Instalalo con: winget install Python.Python.3.12'
}
Write-Host "  $(python --version)"

# Inno Setup es el motor del asistente. winget lo instala en la carpeta del
# usuario, asi que se busca en las dos ubicaciones habituales.
$candidatos = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    'C:\Program Files\Inno Setup 6\ISCC.exe'
)
$iscc = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Fallar 'No se encontro Inno Setup 6. Instalalo con: winget install JRSoftware.InnoSetup'
}
Write-Host "  Inno Setup: $iscc"

$revision = 'sin-revision'
try {
    $revision = (git -C $raiz rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $revision) { $revision = 'sin-revision' }
} catch { $revision = 'sin-revision' }
Write-Host "  Revision del repositorio: $revision"

# ------------------------------------------------------------------ 2. Pruebas
if ($OmitirPruebas) {
    Write-Host ''
    Write-Host '==> 2/8  Pruebas del backend OMITIDAS por parametro' -ForegroundColor Yellow
} else {
    Paso '2/8  Pruebas del backend'
    $venv = Join-Path $raiz 'backend\.venv\Scripts\python.exe'
    $pythonPruebas = if (Test-Path $venv) { $venv } else { (Get-Command python).Source }
    $codigo = Nativo -Ejecutable $pythonPruebas -Argumentos @('manage.py', 'test') `
                     -Directorio (Join-Path $raiz 'backend')
    if ($codigo -ne 0) { Fallar 'La suite del backend no paso: no se empaqueta.' }
}

# ------------------------------------------------------------------ 3. Staging
Paso '3/8  Preparando dist\staging'

if (-not $OmitirApp -and (Test-Path $staging)) {
    Remove-Item -Recurse -Force $staging
}
New-Item -ItemType Directory -Force $staging | Out-Null
New-Item -ItemType Directory -Force $salida | Out-Null

# ------------------------------------------------------- 4. AVACOM OPS Master
if ($OmitirApp -and (Test-Path (Join-Path $staging 'App\Avacom.Lms.Ops.exe'))) {
    Write-Host ''
    Write-Host '==> 4/8  Publicacion de la app OMITIDA: se reutiliza la de dist\staging' -ForegroundColor Yellow
} else {
    Paso '4/8  Publicando AVACOM OPS Master (.NET MAUI, con runtime incluido)'
    # -f solo el destino Windows. Las propiedades de RID y autocontenido se
    # inyectan con Distribucion.props para no tocar ningun .csproj.
    $codigo = Nativo -Ejecutable 'dotnet' -Argumentos @(
        'publish', (Join-Path $raiz 'src\Avacom.Lms.Ops\Avacom.Lms.Ops.csproj')
        '-c', $Configuracion
        '-f', 'net10.0-windows10.0.19041.0'
        "-p:CustomBeforeMicrosoftCommonProps=$props"
        "-p:PublishDir=$staging\App\"
        '--nologo', '-v', 'minimal'
    ) -Silencioso
    if ($codigo -ne 0) { Fallar 'No se pudo publicar AVACOM OPS Master.' }

    $exeApp = Join-Path $staging 'App\Avacom.Lms.Ops.exe'
    if (-not (Test-Path $exeApp)) { Fallar "La publicacion no produjo $exeApp." }
    # Sin esto el equipo destino necesitaria instalar el runtime de .NET.
    if (-not (Test-Path (Join-Path $staging 'App\hostfxr.dll'))) {
        Fallar 'La publicacion no quedo autocontenida: falta hostfxr.dll.'
    }
    if (-not (Test-Path (Join-Path $staging 'App\Microsoft.WindowsAppRuntime.dll'))) {
        Fallar 'La publicacion no incluyo el Windows App SDK autocontenido.'
    }
    Write-Host "  App publicada: $([math]::Round(((Get-ChildItem -Recurse -File (Join-Path $staging 'App') | Measure-Object -Sum Length).Sum / 1MB),0)) MB"
}

# La plantilla de .NET MAUI trae el logotipo de Microsoft como icono y como
# pantalla de arranque. Si vuelve a colarse, se para aqui y no se distribuye un
# producto de AVACOM con la marca de otro.
$iconoFuente = Join-Path $raiz 'src\Avacom.Lms.Ops\Resources\AppIcon\appicon.svg'
# Se quitan los comentarios XML antes de mirar: el propio archivo explica en un
# comentario que ese morado se retiro, y buscarlo en crudo se encontraria a si
# mismo.
$iconoSinComentarios = [regex]::Replace((Get-Content $iconoFuente -Raw), '(?s)<!--.*?-->', '')
if ($iconoSinComentarios -match '512BD4') {
    Fallar 'El icono de la aplicacion sigue siendo el de la plantilla de .NET MAUI.'
}

# Imagenes de marca del asistente, desde el mismo simbolo que usa la aplicacion.
$simbolo = Join-Path $staging 'App\avacom_mark.scale-400.png'
if (-not (Test-Path $simbolo)) {
    Fallar "No se encontro el simbolo de AVACOM en la publicacion ($simbolo)."
}
& (Join-Path $PSScriptRoot 'New-ImagenesAsistente.ps1') `
    -SimboloPng $simbolo -Destino (Join-Path $staging 'Asistente')

# --------------------------------------------------------- 5. Host del backend
Paso '5/8  Publicando el host del backend y el runtime de Python'

$codigo = Nativo -Ejecutable 'dotnet' -Argumentos @(
    'publish', (Join-Path $raiz 'installer\src\host\Avacom.Ops.Host.csproj')
    '-c', $Configuracion
    "-p:PublishDir=$staging\Runtime\"
    "-p:Version=$Version"
    '--nologo', '-v', 'minimal'
) -Silencioso
if ($codigo -ne 0) { Fallar 'No se pudo publicar el host del backend.' }
Remove-Item (Join-Path $staging 'Runtime\*.pdb') -Force -ErrorAction SilentlyContinue

Copy-Item (Join-Path $raiz 'installer\src\payload\avacom_ops_backend.py') `
          (Join-Path $staging 'Runtime') -Force

& (Join-Path $PSScriptRoot 'Get-PythonRuntime.ps1') `
    -PythonVersion $VersionPython `
    -Destination (Join-Path $staging 'Runtime\Python') `
    -RequirementsFile (Join-Path $raiz 'installer\src\payload\requirements-runtime.txt') | Out-Null

# ----------------------------------------------------------------- 6. Backend
Paso '6/8  Copiando el backend y escribiendo el manifiesto'

$destinoBackend = Join-Path $staging 'Backend'
if (Test-Path $destinoBackend) { Remove-Item -Recurse -Force $destinoBackend }
New-Item -ItemType Directory -Force $destinoBackend | Out-Null

# Se excluye lo que es del equipo de desarrollo, no del producto:
#   .venv        entorno virtual local, no portable
#   db.sqlite3*  base de datos de desarrollo (con su -wal y su -shm); el nodo
#                crea la suya vacia
#   __pycache__  bytecode del interprete del desarrollador
# robocopy usa 0-7 para exitos (1 = se copiaron archivos) y 8+ para fallos.
$codigo = Nativo -Ejecutable 'robocopy' -Argumentos @(
    (Join-Path $raiz 'backend'), $destinoBackend, '/E'
    '/XD', '.venv', '__pycache__'
    '/XF', 'db.sqlite3', 'db.sqlite3-wal', 'db.sqlite3-shm'
    '/NFL', '/NDL', '/NJH', '/NJS', '/NP'
) -Silencioso
if ($codigo -ge 8) { Fallar "robocopy fallo al copiar el backend (codigo $codigo)." }

foreach ($obligatorio in @('manage.py', 'avacom_lms\settings.py', 'avacom_lms\wsgi.py', 'expediente\migrations')) {
    if (-not (Test-Path (Join-Path $destinoBackend $obligatorio))) {
        Fallar "El backend copiado esta incompleto: falta $obligatorio."
    }
}
if (Get-ChildItem $destinoBackend -Filter 'db.sqlite3*' -ErrorAction SilentlyContinue) {
    Fallar 'La base de datos de desarrollo se colo en el paquete.'
}
foreach ($obligatorio in @('avacom_lms\asgi.py', 'classroom_engine\interfaces\websockets.py')) {
    if (-not (Test-Path (Join-Path $destinoBackend $obligatorio))) {
        Fallar "El backend no trae lo que Daphne sirve: falta $obligatorio."
    }
}
if (Get-ChildItem $destinoBackend -Recurse -Include '*.pyc' -ErrorAction SilentlyContinue) {
    Fallar 'Hay bytecode compilado (.pyc) dentro del backend a empaquetar.'
}

$paquetes = Get-ChildItem (Join-Path $staging 'Runtime\Python\Lib\site-packages') -Directory -Filter '*.dist-info' |
    ForEach-Object { $_.Name -replace '\.dist-info$', '' } | Sort-Object

$manifiesto = [ordered]@{
    producto            = 'AVACOM OPS Master'
    version             = $Version
    revision            = $revision
    empaquetado         = (Get-Date).ToString('o')
    servicio            = 'AVACOMOPSBackend'
    escucha             = '0.0.0.0:8000'
    servidor_asgi       = 'daphne (avacom_lms.asgi:application, HTTP y WebSocket)'
    politica_datos      = $PoliticaDatos
    id_instalacion      = 'B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31'
    runtime_python      = $VersionPython
    paquetes_python     = @($paquetes)
    runtime_dotnet      = 'incluido en la aplicacion (autocontenido)'
    administra_cursos   = $false
    dueno_de_los_cursos = 'AVACOM Contenido'
}
$manifiesto | ConvertTo-Json -Depth 4 |
    Set-Content -Path (Join-Path $staging 'manifiesto.json') -Encoding utf8

@"
AVACOM OPS Master $Version (revision $revision)

Este equipo es el nodo principal del aula. Lo instalado aqui es:

  App\       AVACOM OPS Master, la aplicacion del profesor.
  Backend\   La API local del aula (Django REST Framework) y su canal en
             tiempo real (WebSocket), servidos por Daphne.
  Runtime\   Lo que la API necesita para ejecutarse. No hace falta instalar
             Python ni .NET: ya van dentro.

La API se ejecuta como el servicio de Windows AVACOMOPSBackend, escuchando en
0.0.0.0:8000, y arranca sola al encender el equipo. Las tabletas del aula se
conectan a http://<IP de este equipo>:8000.

Lo que cambia con el uso NO esta en esta carpeta, esta en:

  %ProgramData%\AVACOM\OPS Master\Config    configuracion de este equipo
  %ProgramData%\AVACOM\OPS Master\Data      base de datos del nodo (organizacion, personas,
                                            tabletas, clases, expediente)
  %ProgramData%\AVACOM\OPS Master\Respaldos  copias de seguridad previas a cada actualizacion
  %ProgramData%\AVACOM\OPS Master\Logs      registros para diagnostico

Los cursos no viven aqui: son de AVACOM Contenido, que se instala aparte y
tiene su propia carpeta. AVACOM OPS Master los consulta y guarda solo el
expediente: inscripcion, progreso, intentos y notas.

Para quitar el producto, usa "Aplicaciones instaladas" de Windows. La
desinstalacion pregunta si quieres conservar los datos y su configuracion (van
juntos); conservarlos es la respuesta por defecto.

Politica de datos de esta version: $PoliticaDatos.
"@ | Set-Content -Path (Join-Path $staging 'LEEME.txt') -Encoding utf8

$tamano = [math]::Round(((Get-ChildItem -Recurse -File $staging | Measure-Object -Sum Length).Sum / 1MB), 0)
Write-Host "  Contenido a empaquetar: $tamano MB"

# ------------------------------------------------- 7. Verificacion del asistente
Paso '7/8  Verificando el codigo del asistente en este Windows'

# Compilar no prueba que Pascal Script funcione. Esto ejecuta las diez
# comprobaciones del equipo de verdad, sin instalar nada, y aborta si alguna
# no llega a dar un veredicto.
& (Join-Path $PSScriptRoot 'Verificar-Asistente.ps1') -Iscc $iscc

# El probador de comunicacion (un .bat con el PowerShell dentro) se regenera
# desde su fuente para que no se quede atras.
& (Join-Path $PSScriptRoot 'New-ProbadorBat.ps1') | Out-Null

# ------------------------------------------------------------ 8. Inno Setup
Paso '8/8  Compilando el asistente con Inno Setup'

Get-ChildItem $salida -Filter 'AVACOM-OPS-Master-Setup-*.exe' -ErrorAction SilentlyContinue |
    Remove-Item -Force

$codigo = Nativo -Ejecutable $iscc -Argumentos @(
    "/DCarpetaContenido=$staging"
    "/DCarpetaSalida=$salida"
    "/DRevision=$revision"
    "/DVersionProducto=$Version"
    "/DPoliticaDatos=$PoliticaDatos"
    $iss
) -Directorio (Split-Path $iss) -LineasSiFalla 40
if ($codigo -ne 0) { Fallar 'Inno Setup no pudo compilar el asistente.' }

$instalador = Get-ChildItem $salida -Filter 'AVACOM-OPS-Master-Setup-*.exe' | Select-Object -First 1
if (-not $instalador) { Fallar 'Inno Setup termino sin producir el instalador.' }

# Huella para poder verificar el archivo que se distribuye.
$huella = (Get-FileHash $instalador.FullName -Algorithm SHA256).Hash
@"
$($instalador.Name)
SHA256  $huella
Version $Version
Revision $revision
Empaquetado $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz'))
"@ | Set-Content -Path (Join-Path $salida 'SHA256.txt') -Encoding utf8

# El verificador se versiona junto al instalador (installer\latest) y no se
# genera: si falta, la carpeta de entrega esta incompleta.
if (-not (Test-Path (Join-Path $salida 'AVACOM-Verificar-Instalador.bat'))) {
    Fallar 'Falta installer\latest\AVACOM-Verificar-Instalador.bat: la carpeta de entrega esta incompleta.'
}

@"
AVACOM OPS Master $Version (revision $revision)

Esta carpeta es lo que se sube como release de GitHub:

  $($instalador.Name)   el instalador (no se versiona: supera los 100 MB de GitHub)
  SHA256.txt                            la huella del instalador; si se versiona
  AVACOM-Verificar-Instalador.bat       revisa el equipo y el instalador SIN instalar nada
  LEEME.txt                             este archivo

Antes de instalar en un equipo del aula, toca AVACOM-Verificar-Instalador.bat:
comprueba la descarga (SHA256), ejecuta las diez comprobaciones del asistente y
enseña el estado de lo ya instalado. No modifica el equipo.

Para instalar, toca el instalador. Todo se maneja con toques: no hay que escribir
nada. Python, .NET y todo lo que la API necesita van dentro; no hace falta internet.

Politica de datos de esta version: $PoliticaDatos.
"@ | Set-Content -Path (Join-Path $salida 'LEEME.txt') -Encoding utf8

Write-Host ''
Write-Host 'Instalador listo' -ForegroundColor Green
Write-Host "  $($instalador.FullName)"
Write-Host "  $([math]::Round($instalador.Length / 1MB, 1)) MB"
Write-Host "  SHA256 $huella"
