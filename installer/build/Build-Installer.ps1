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
    script publica desde el codigo fuente y no reutiliza binarios sueltos. Y lo
    DEMUESTRA: antes de empezar toma la huella del codigo que va a empaquetar
    (backend, aplicacion, asistente), comprueba al terminar que el paquete
    contiene exactamente eso y que nada cambio mientras se compilaba, y deja las
    huellas en manifiesto.json y SHA256.txt.

.PARAMETER OmitirPruebas
    Salta la suite del backend. Solo para iterar; una entrega no deberia
    empaquetarse sin haberla pasado.

.PARAMETER OmitirApp
    Reutiliza la publicacion de la app de dist\staging, que es la etapa lenta.
    Solo se acepta si esa publicacion corresponde al codigo actual (su huella
    coincide con la del codigo fuente): una app vieja dentro de un instalador
    nuevo fue justo lo que ya paso una vez.

.PARAMETER OmitirEnsayo
    Salta el ensayo del paquete (Ensayar-Paquete.ps1), que levanta el backend
    empaquetado en un puerto libre y lo valida como lo haria el aula.

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
    [switch] $OmitirApp,
    [switch] $OmitirEnsayo,
    # Carpeta con Backend\ y Runtime\ de la version anterior (p. ej. copiada de un dist\staging viejo):
    # el ensayo la usa para probar la actualizacion sobre una base de datos de esa version.
    [string] $VersionAnterior = '',
    # Por defecto, si el codigo cambia mientras se compila, la compilacion se aborta: lo que se
    # empaqueto ya no seria lo que hay en el repositorio.
    [switch] $PermitirCambiosDuranteLaCompilacion
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
    Huella de un conjunto de carpetas: SHA-256 del listado ordenado de
    "ruta relativa | SHA-256 del contenido". Sirve para DEMOSTRAR que lo que se
    empaqueto es el codigo que habia al empezar, y que el paquete contiene
    exactamente lo que debe (ni un archivo de mas ni de menos).

    No se desciende a las carpetas excluidas: bin y obj de una app MAUI pesan
    cientos de MB y no son codigo.
#>
function Huella-Carpetas {
    param(
        [Parameter(Mandatory)] [string[]] $Raices,
        [string[]] $ExcluirCarpetas = @('bin', 'obj', '.venv', '__pycache__', 'node_modules', '.vs'),
        [string[]] $ExcluirArchivos = @(),
        # Rutas completas de carpetas que no cuentan (p. ej. backend\logs).
        [string[]] $ExcluirRutas = @()
    )

    $sha = [System.Security.Cryptography.SHA256]::Create()
    $lineas = New-Object System.Collections.Generic.List[string]
    $excluidas = @($ExcluirRutas | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') })

    function Recorrer([string] $carpeta, [string] $base) {
        foreach ($archivo in [IO.Directory]::EnumerateFiles($carpeta)) {
            $nombre = [IO.Path]::GetFileName($archivo)
            $omitir = $false
            foreach ($patron in $ExcluirArchivos) { if ($nombre -like $patron) { $omitir = $true; break } }
            if ($omitir) { continue }
            $hash = [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($archivo))).Replace('-', '')
            $lineas.Add(($archivo.Substring($base.Length)).ToLowerInvariant() + '|' + $hash)
        }
        foreach ($sub in [IO.Directory]::EnumerateDirectories($carpeta)) {
            $nombre = [IO.Path]::GetFileName($sub)
            if ($ExcluirCarpetas -contains $nombre) { continue }
            if ($excluidas -contains $sub.TrimEnd('\')) { continue }
            Recorrer $sub $base
        }
    }

    foreach ($raiz in $Raices) {
        if (-not (Test-Path $raiz)) { continue }
        $completa = (Resolve-Path $raiz).Path.TrimEnd('\')
        # La base es el PADRE: asi la raiz forma parte de la ruta relativa y dos raices
        # distintas con un archivo del mismo nombre no se confunden.
        Recorrer $completa ((Split-Path $completa -Parent).TrimEnd('\') + '\')
    }

    $texto = (($lineas | Sort-Object) -join "`n")
    return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($texto))).Replace('-', '').ToLowerInvariant()
}

# Lo que el instalador de OPS empaqueta y de lo que depende su contenido. Student queda fuera: no viaja aqui.
# '.env' y '.env.*' son la configuracion de DESARROLLO (backend\.env: sesion obligatoria y el PIN maestro de la primera
# instalacion del desarrollador). No se versionan y NUNCA viajan: un PIN maestro conocido dentro de cada paquete
# seria un agujero, y la configuracion del nodo instalado es solo Config\backend.env.
# Tambien cualquier base SQLite suelta (el desarrollador prueba con otras, p. ej. primer-arranque.sqlite3, y puede tenerlas
# abiertas): ni se empaquetan ni cuentan en la huella (leerlas, ademas, falla si otro proceso las tiene abiertas).
$ArchivosDeLog = @('*.log', '*.log.*', 'db.sqlite3', 'db.sqlite3-wal', 'db.sqlite3-shm', '*.sqlite3', '*.sqlite3-wal', '*.sqlite3-shm', '*.sqlite3-journal', '*.db', '*.pyc', '.escritura', '.env', '.env.*')
function Huella-Backend([string] $carpeta) {
    Huella-Carpetas -Raices @($carpeta) -ExcluirArchivos $ArchivosDeLog -ExcluirRutas @((Join-Path $carpeta 'logs'))
}
function Huella-App {
    Huella-Carpetas -Raices @(
        (Join-Path $raiz 'src\Avacom.Lms.Ops'), (Join-Path $raiz 'src\Avacom.Lms.Core'),
        (Join-Path $raiz 'src\Avacom.Lms.Ui'), (Join-Path $raiz 'assets')) -ExcluirArchivos @('*.user', '*.log')
}
function Huella-Instalador {
    # El asistente, el host, el verificador y los scripts de compilacion: todo lo que decide que hay
    # dentro del .exe y de los .bat. Se excluye lo que la propia compilacion genera (los .bat, el arnes).
    $codigo = Huella-Carpetas -ExcluirArchivos @('*.log', '*.bat', '*.exe') -Raices @(
        (Join-Path $raiz 'installer\src'), (Join-Path $raiz 'installer\tools'), (Join-Path $raiz 'installer\build'))
    $version = (Get-FileHash (Join-Path $raiz 'installer\version.json') -Algorithm SHA256).Hash
    $sha = [System.Security.Cryptography.SHA256]::Create()
    [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes("$codigo|$version"))).Replace('-', '').ToLowerInvariant()
}

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

# El instalador se compila de lo que hay en disco, este o no confirmado en git.
# Se anota cuanto hay sin confirmar para que un instalador no pueda hacerse pasar por
# una revision que no es del todo (el manifiesto lo lleva). Los registros y la base de
# desarrollo, y las propias salidas de esta compilacion, no cuentan.
$cambiosSinConfirmar = @()
try {
    $porcelana = @(git -C $raiz status --porcelain 2>$null)
    if ($LASTEXITCODE -eq 0) {
        $cambiosSinConfirmar = @($porcelana |
            ForEach-Object { if ($_.Length -gt 3) { $_.Substring(3).Trim('"') } } |
            Where-Object { $_ -and $_ -notmatch '^(backend/logs/|backend/db\.sqlite3|dist/|installer/latest/|installer/src/host/(bin|obj)/|installer/build/PruebaAsistente\.exe)' })
    }
} catch { $cambiosSinConfirmar = @() }
$arbolLimpio = (@($cambiosSinConfirmar).Count -eq 0)
if ($arbolLimpio) {
    Write-Host '  Arbol de trabajo limpio: el instalador es exactamente esa revision.'
} else {
    Write-Host "  AVISO: hay $(@($cambiosSinConfirmar).Count) archivo(s) sin confirmar en git; se empaquetan tal como estan:" -ForegroundColor Yellow
    $cambiosSinConfirmar | Select-Object -First 12 | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    if (@($cambiosSinConfirmar).Count -gt 12) { Write-Host "    ... y $(@($cambiosSinConfirmar).Count - 12) mas" -ForegroundColor Yellow }
}

# Huellas del codigo AL EMPEZAR. Al final se vuelven a tomar: si no coinciden, el codigo
# cambio mientras se compilaba (otro proceso editando el repositorio) y el instalador
# ya no es lo que hay en disco.
Write-Host '  Tomando la huella del codigo que se va a empaquetar ...'
$huellaBackendInicial = Huella-Backend (Join-Path $raiz 'backend')
$huellaAppInicial = Huella-App
$huellaInstaladorInicial = Huella-Instalador
Write-Host "  backend $($huellaBackendInicial.Substring(0, 12)) · app $($huellaAppInicial.Substring(0, 12)) · asistente $($huellaInstaladorInicial.Substring(0, 12))"

# ------------------------------------------------------------------ 2. Pruebas
if ($OmitirPruebas) {
    Write-Host ''
    Write-Host '==> 2/8  Pruebas del backend OMITIDAS por parametro' -ForegroundColor Yellow
} else {
    Paso '2/8  Pruebas del backend'
    $venv = Join-Path $raiz 'backend\.venv\Scripts\python.exe'
    $pythonPruebas = if (Test-Path $venv) { $venv } else { (Get-Command python).Source }
    # Desde que settings.py lee backend\.env en desarrollo (que trae la sesion obligatoria), las pruebas heredarian ese
    # modo. Se escribieron para el modo por defecto del backend (sin sesion obligatoria; las que necesitan sesion la
    # activan ellas mismas): se les da ese entorno, y se restaura al terminar. Una variable del entorno manda sobre .env.
    $exigirAntes = $env:AVACOM_LMS_EXIGIR_SESION
    $env:AVACOM_LMS_EXIGIR_SESION = '0'
    try {
        $codigo = Nativo -Ejecutable $pythonPruebas -Argumentos @('manage.py', 'test') `
                         -Directorio (Join-Path $raiz 'backend')
    } finally {
        if ($null -eq $exigirAntes) { Remove-Item Env:\AVACOM_LMS_EXIGIR_SESION -ErrorAction SilentlyContinue } else { $env:AVACOM_LMS_EXIGIR_SESION = $exigirAntes }
    }
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
$selloApp = Join-Path $staging 'huella-app.txt'
if ($OmitirApp -and (Test-Path (Join-Path $staging 'App\Avacom.Lms.Ops.exe'))) {
    Write-Host ''
    Write-Host '==> 4/8  Publicacion de la app OMITIDA: se reutiliza la de dist\staging' -ForegroundColor Yellow
    # Una app vieja dentro de un instalador nuevo ya paso una vez (se empaqueto una publicacion de
    # hacia semanas). Solo se reutiliza si es de ESTE codigo: su huella lo dice.
    $huellaPublicada = if (Test-Path $selloApp) { (Get-Content $selloApp -Raw).Trim() } else { '(sin huella)' }
    if ($huellaPublicada -ne $huellaAppInicial) {
        Fallar ("La app de dist\staging no corresponde al codigo actual (huella publicada $huellaPublicada; " +
                "huella del codigo $huellaAppInicial). Vuelve a compilar sin -OmitirApp.")
    }
    Write-Host '  La publicacion reutilizada es de este mismo codigo (la huella coincide).'
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

    # El sello va en la raiz de dist\staging y NO dentro de App\: no viaja en el instalador.
    Set-Content -Path $selloApp -Value $huellaAppInicial -Encoding ascii
}

# Compilada hace un momento y no antes del ultimo cambio de codigo: el binario de la app es mas
# nuevo que cualquier archivo que lo produce.
$ultimoCodigo = Get-ChildItem (Join-Path $raiz 'src\Avacom.Lms.Ops'), (Join-Path $raiz 'src\Avacom.Lms.Core'), (Join-Path $raiz 'src\Avacom.Lms.Ui') `
    -Recurse -File -Include '*.cs', '*.xaml', '*.csproj', '*.svg', '*.png' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\(bin|obj)\\' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$dllApp = Get-Item (Join-Path $staging 'App\Avacom.Lms.Ops.dll') -ErrorAction SilentlyContinue
if ($dllApp -and $ultimoCodigo -and $dllApp.LastWriteTime -lt $ultimoCodigo.LastWriteTime.AddSeconds(-2)) {
    Fallar ("La app empaquetada ($($dllApp.LastWriteTime)) es anterior al ultimo cambio de codigo " +
            "($($ultimoCodigo.Name), $($ultimoCodigo.LastWriteTime)): no es la version actual.")
}
if ($dllApp) { Write-Host "  Avacom.Lms.Ops.dll compilada el $($dllApp.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')), despues del ultimo cambio de codigo." }

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
#   logs         los registros del desarrollador (backend-app.log, ...): el nodo
#                escribe los suyos en ProgramData, y los de otro equipo no se
#                reparten por las aulas
# robocopy usa 0-7 para exitos (1 = se copiaron archivos) y 8+ para fallos.
$codigo = Nativo -Ejecutable 'robocopy' -Argumentos @(
    (Join-Path $raiz 'backend'), $destinoBackend, '/E'
    '/XD', '.venv', '__pycache__', (Join-Path $raiz 'backend\logs')
    '/XF', 'db.sqlite3', 'db.sqlite3-wal', 'db.sqlite3-shm', '*.sqlite3', '*.sqlite3-wal', '*.sqlite3-shm', '*.sqlite3-journal', '*.db', '*.log', '*.log.*', '*.pyc', '.escritura', '.env', '.env.*'
    '/NFL', '/NDL', '/NJH', '/NJS', '/NP'
) -Silencioso
if ($codigo -ge 8) { Fallar "robocopy fallo al copiar el backend (codigo $codigo)." }

foreach ($obligatorio in @('manage.py', 'avacom_lms\settings.py', 'avacom_lms\wsgi.py', 'expediente\migrations')) {
    if (-not (Test-Path (Join-Path $destinoBackend $obligatorio))) {
        Fallar "El backend copiado esta incompleto: falta $obligatorio."
    }
}
if (Get-ChildItem $destinoBackend -Recurse -Include '*.sqlite3*', '*.db' -ErrorAction SilentlyContinue) {
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
if (Get-ChildItem $destinoBackend -Recurse -Force -Filter '.env*' -File -ErrorAction SilentlyContinue) {
    Fallar 'La configuracion de desarrollo (backend\.env) se colo en el paquete: llevaria un PIN maestro conocido a cada aula.'
}
if (Test-Path (Join-Path $destinoBackend 'logs')) {
    Fallar 'Los registros de desarrollo (backend\logs) se colaron en el paquete.'
}

# Integridad: el backend empaquetado ES, archivo por archivo, el del repositorio (menos lo que
# se excluye a proposito). Si falta uno, sobra uno o difiere un byte, el paquete no sale.
$huellaBackendPaquete = Huella-Backend $destinoBackend
if ($huellaBackendPaquete -ne $huellaBackendInicial) {
    Fallar ("El backend empaquetado no coincide con el del repositorio (paquete $huellaBackendPaquete; " +
            "repositorio $huellaBackendInicial). O la copia fallo, o el codigo cambio mientras se copiaba.")
}
Write-Host "  El backend empaquetado es el del repositorio (huella $($huellaBackendPaquete.Substring(0, 12)))."

# Toda app de Django que settings.py instala viaja completa, con sus migraciones: una app
# nueva (auditoria, evaluacion, modo de estudio...) que no llegara al paquete daria un nodo
# que arranca y falla en la primera ruta que la usa.
$textoAjustes = Get-Content (Join-Path $raiz 'backend\avacom_lms\settings.py') -Raw -Encoding UTF8
$bloqueApps = [regex]::Match($textoAjustes, '(?s)INSTALLED_APPS\s*=\s*\[(.*?)\n\]').Groups[1].Value
$modulosBackend = @([regex]::Matches($bloqueApps, '(?m)^\s*"([A-Za-z0-9_]+)"\s*,') |
    ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -notin @('daphne', 'rest_framework', 'channels') })
if (@($modulosBackend).Count -lt 8) { Fallar "No se pudieron leer las apps de INSTALLED_APPS (salieron $(@($modulosBackend).Count))." }
foreach ($modulo in $modulosBackend) {
    if (-not (Test-Path (Join-Path $destinoBackend "$modulo\__init__.py"))) {
        Fallar "La app $modulo esta en INSTALLED_APPS pero no llego al paquete."
    }
    if ((Test-Path (Join-Path $raiz "backend\$modulo\migrations")) -and -not (Test-Path (Join-Path $destinoBackend "$modulo\migrations"))) {
        Fallar "La app $modulo perdio sus migraciones al empaquetarse."
    }
}
Write-Host "  Apps del backend en el paquete ($(@($modulosBackend).Count)): $($modulosBackend -join ', ')"

$paquetes = Get-ChildItem (Join-Path $staging 'Runtime\Python\Lib\site-packages') -Directory -Filter '*.dist-info' |
    ForEach-Object { $_.Name -replace '\.dist-info$', '' } | Sort-Object

$manifiesto = [ordered]@{
    producto            = 'AVACOM OPS Master'
    version             = $Version
    revision            = $revision
    arbol_limpio        = $arbolLimpio
    archivos_sin_confirmar = @($cambiosSinConfirmar | Select-Object -First 40)
    huella_backend      = $huellaBackendPaquete
    huella_app          = $huellaAppInicial
    huella_asistente    = $huellaInstaladorInicial
    empaquetado         = (Get-Date).ToString('o')
    servicio            = 'AVACOMOPSBackend'
    escucha             = '0.0.0.0:8000'
    servidor_asgi       = 'daphne (avacom_lms.asgi:application, HTTP y WebSocket)'
    politica_datos      = $PoliticaDatos
    id_instalacion      = 'B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31'
    runtime_python      = $VersionPython
    paquetes_python     = @($paquetes)
    runtime_dotnet      = 'incluido en la aplicacion (autocontenido)'
    modulos_backend     = @($modulosBackend)
    carpeta_registros   = '%ProgramData%\AVACOM\OPS Master\Logs'
    fuente_de_cursos    = 'AVACOM Contenido (biblioteca); el curso de ejemplo esta apagado'
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
  %ProgramData%\AVACOM\OPS Master\Logs      registros del nodo (backend, auditoria en archivo,
                                            instalador y lanzador) para diagnostico

El servicio (cuenta SYSTEM) escribe ahi la base de datos y los registros; el
instalador les da los permisos que necesitan. La aplicacion del profesor guarda
el perfil de WebView2 (audio, video, PDF y laboratorios de las lecciones) en el
perfil de Windows de quien da la clase, nunca dentro de esta carpeta.

Los cursos no viven aqui: son de AVACOM Contenido, que se instala aparte y
tiene su propia carpeta. AVACOM OPS Master los consulta y guarda solo el
expediente: inscripcion, progreso, intentos y notas. Si AVACOM Contenido no
esta abierto, el aula arranca igual y los cursos aparecen cuando lo este.

PRIMER ARRANQUE (instalacion nueva): el nodo queda sin organizacion. Al abrir AVACOM OPS
Master por primera vez, la aplicacion lo detecta y abre el primer arranque: pais y nombre del
aula, el administrador (documento, nombres, apellidos, contrasena) y el PIN maestro (seis
digitos). La hoja de acceso se muestra UNA vez y el PIN maestro no se puede volver a ver.
Despues, desde OPS (Grupos) se crean los grupos y los alumnos, o los alumnos se crean solos y
los profesores se registran con el PIN maestro. Cada tableta se registra sola al conectar.
ACTUALIZACION de un nodo que ya tenia organizacion: no tiene PIN maestro hasta que la
administracion lo configure en OPS (Seguridad del aula); a los alumnos con PIN provisional
conviene dejarlos en "PIN pendiente" (Nuevo PIN, en Grupos).

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

# Los dos .bat (un solo archivo cada uno, con el PowerShell dentro) se regeneran
# desde sus fuentes para que no se queden atras:
#   AVACOM-Verificar-Instalador.bat    revisa el equipo, el instalador y lo instalado, y busca el
#                                      error exacto cuando algo falla (installer\latest)
#   AVACOM-Probar-Comunicacion.bat     diagnostico a fondo de la comunicacion con AVACOM Contenido
& (Join-Path $PSScriptRoot 'New-ProbadorBat.ps1') | Out-Null
& (Join-Path $PSScriptRoot 'New-VerificadorBat.ps1') | Out-Null
# La carpeta de entrega (la release) lleva todo junto: el diagnostico de Contenido se copia junto al instalador.
Copy-Item (Join-Path $raiz 'installer\tools\AVACOM-Probar-Comunicacion.bat') (Join-Path $salida 'AVACOM-Probar-Comunicacion.bat') -Force

# ----------------------------------------------------- 7b. Ensayo del paquete
if ($OmitirEnsayo) {
    Write-Host ''
    Write-Host '==> 7b  Ensayo del paquete OMITIDO por parametro' -ForegroundColor Yellow
} else {
    Paso '7b  Ensayando el paquete como lo haria el aula (en una carpeta de pruebas, sin tocar este equipo)'
    $argumentosEnsayo = @{ Staging = $staging }
    if ($VersionAnterior) { $argumentosEnsayo.VersionAnterior = $VersionAnterior }
    & (Join-Path $PSScriptRoot 'Ensayar-Paquete.ps1') @argumentosEnsayo
    if ($LASTEXITCODE -ne 0) { Fallar 'El ensayo del paquete fallo: no se compila el instalador.' }
}

# ------------------------------------------------------------ 8. Inno Setup
Paso '8/8  Compilando el asistente con Inno Setup'

# Una compilacion interrumpida deja un .tmp a medias y, peor, puede dejar el .exe de la version
# anterior como si fuera el de esta: se retira todo antes de compilar.
Get-ChildItem $salida -Filter 'AVACOM-OPS-Master-Setup-*' -ErrorAction SilentlyContinue |
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
if (Get-ChildItem $salida -Filter '*.tmp' -ErrorAction SilentlyContinue) {
    Fallar 'Quedo un archivo temporal de Inno Setup en installer\latest: la compilacion no termino bien.'
}

# El .exe producido es de esta version: lo dice el propio archivo, no el script.
$infoExe = (Get-Item $instalador.FullName).VersionInfo
if ($infoExe.FileVersion -notlike "$Version*") {
    Remove-Item $instalador.FullName -Force
    Fallar "El instalador producido dice ser la version $($infoExe.FileVersion) y se compilo la $Version."
}
if ($instalador.Name -ne "AVACOM-OPS-Master-Setup-$Version.exe") {
    Remove-Item $instalador.FullName -Force
    Fallar "El instalador se llama $($instalador.Name) y deberia llamarse AVACOM-OPS-Master-Setup-$Version.exe."
}

# El codigo no cambio mientras se compilaba (otro proceso editando el repositorio): el
# instalador es lo que habia en disco al empezar, y eso es lo que el paquete contiene.
$huellaBackendFinal = Huella-Backend (Join-Path $raiz 'backend')
$huellaAppFinal = Huella-App
$huellaInstaladorFinal = Huella-Instalador
$cambiaron = @()
if ($huellaBackendFinal -ne $huellaBackendInicial) { $cambiaron += 'el backend' }
if ($huellaAppFinal -ne $huellaAppInicial) { $cambiaron += 'la aplicacion' }
if ($huellaInstaladorFinal -ne $huellaInstaladorInicial) { $cambiaron += 'el asistente' }
if ($cambiaron.Count -gt 0) {
    if ($PermitirCambiosDuranteLaCompilacion) {
        Write-Host "  AVISO: cambio $($cambiaron -join ', ') mientras se compilaba; se acepto por parametro." -ForegroundColor Yellow
    } else {
        Remove-Item $instalador.FullName -Force
        Fallar ("Cambio $($cambiaron -join ', ') mientras se compilaba: el instalador ya no es lo que hay en el repositorio " +
                'y se descarto. Vuelve a compilar con el repositorio quieto.')
    }
} else {
    Write-Host '  El codigo no cambio durante la compilacion: el instalador es lo que habia al empezar.'
}

# Huella para poder verificar el archivo que se distribuye.
$huella = (Get-FileHash $instalador.FullName -Algorithm SHA256).Hash
@"
$($instalador.Name)
SHA256  $huella
Version $Version
Revision $revision
Arbol-limpio $(if ($arbolLimpio) { 'si' } else { 'no (' + @($cambiosSinConfirmar).Count + ' archivos sin confirmar; ver manifiesto.json)' })
Huella-backend $huellaBackendPaquete
Huella-app $huellaAppInicial
Huella-asistente $huellaInstaladorInicial
Empaquetado $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz'))
"@ | Set-Content -Path (Join-Path $salida 'SHA256.txt') -Encoding utf8

# Los dos .bat los acaba de generar el paso 7: tienen que estar.
if (-not (Test-Path (Join-Path $salida 'AVACOM-Verificar-Instalador.bat'))) {
    Fallar 'Falta installer\latest\AVACOM-Verificar-Instalador.bat: la carpeta de entrega esta incompleta.'
}
if (-not (Test-Path (Join-Path $salida 'AVACOM-Probar-Comunicacion.bat'))) {
    Fallar 'Falta installer\latest\AVACOM-Probar-Comunicacion.bat: la carpeta de entrega esta incompleta.'
}

@"
AVACOM OPS Master $Version (revision $revision)

Esta carpeta es lo que se sube como release de GitHub:

  $($instalador.Name)   el instalador (no se versiona: supera los 100 MB de GitHub)
  SHA256.txt                            la huella del instalador y del codigo que lleva
  AVACOM-Verificar-Instalador.bat       revisa el equipo, el instalador y lo ya instalado, y busca
                                        el error exacto cuando algo falla. NO modifica nada.
  AVACOM-Probar-Comunicacion.bat        el diagnostico a fondo de la comunicacion con AVACOM
                                        Contenido (por que el aula no ve cursos). NO modifica nada.
  LEEME.txt                             este archivo

PARA INSTALAR: toca el instalador. Todo se maneja con toques: no hay que escribir nada.
Python, .NET y todo lo que la API necesita van dentro; no hace falta internet.

ANTES DE INSTALAR en un equipo del aula, o SI ALGO FALLA despues (por ejemplo, la aplicacion se
cierra al abrir una leccion): toca AVACOM-Verificar-Instalador.bat. Comprueba la descarga (SHA256),
ejecuta las diez comprobaciones del asistente, revisa permisos, servicio, registros y la
comunicacion con AVACOM Contenido, y recoge los errores de la aplicacion (registro de fallos y
Visor de eventos de Windows). Deja un informe y un .zip con las evidencias en el escritorio.

Esta version incluye: Modo Estudio, Evaluacion y entrega, Auditoria y registros del nodo, y el
acceso con PIN maestro (alta propia de profesores y alumnos, visitante, traspaso entre OPS y Student).

PRIMER ARRANQUE: tras una instalacion nueva, abre AVACOM OPS Master. Pedira (con el teclado tactil
de Windows) pais y nombre del aula, el administrador (documento, contrasena) y el PIN maestro de
seis digitos. La hoja de acceso se muestra una sola vez. Luego crea los grupos y alumnos en Grupos
(o deja que se registren solos). En cada tableta, AVACOM Student pide la direccion del aula que
muestra la ultima pantalla del instalador.
Politica de datos de esta version: $PoliticaDatos.
"@ | Set-Content -Path (Join-Path $salida 'LEEME.txt') -Encoding utf8

Write-Host ''
Write-Host 'Instalador listo' -ForegroundColor Green
Write-Host "  $($instalador.FullName)"
Write-Host "  $([math]::Round($instalador.Length / 1MB, 1)) MB"
Write-Host "  Version $Version · revision $revision · $(if ($arbolLimpio) { 'arbol limpio' } else { "$(@($cambiosSinConfirmar).Count) archivos sin confirmar" })"
Write-Host "  SHA256 $huella"
