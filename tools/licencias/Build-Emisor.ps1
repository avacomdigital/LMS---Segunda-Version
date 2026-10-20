<#
.SYNOPSIS
    Arma la carpeta PORTATIL del Emisor de Licencias (uso interno de AVACOM).

.DESCRIPTION
    El personal que emite licencias no tiene por que tener Python. Este script arma, en el equipo de compilacion, una carpeta autocontenida con:

        python\            Python embeddable (misma version que el backend) + cryptography (copiado del venv del backend: sin internet, sin pip)
        avacom_licencias\  la herramienta
        vendor\            SOLO el dominio puro del nodo (licenciamiento\__init__.py y licenciamiento\dominio\*.py): nunca las pruebas, nunca las llaves de desarrollo
        planes\            los planes (datos)
        Emitir-Licencia.bat y avacom-licencias.bat

    El resultado queda en tools\licencias\dist\ (no se versiona) y NO se copia al instalador del colegio: esa exclusion la comprueba LT-48.

.PARAMETER Zip
    Ademas de la carpeta, deja un .zip y su SHA-256.

.NOTES
    Requiere el venv del backend (backend\.venv) y, la primera vez, internet SOLO para bajar el Python embeddable a la cache de compilacion (la misma del instalador).
#>
[CmdletBinding()]
param(
    [string] $Salida,
    [string] $PythonVersion = '3.12.10',
    [string] $CacheDirectory,
    [switch] $Zip
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = $PSScriptRoot
$repo = (Resolve-Path (Join-Path $raiz '..\..')).Path
$venvSitio = Join-Path $repo 'backend\.venv\Lib\site-packages'
$venvCfg = Join-Path $repo 'backend\.venv\pyvenv.cfg'

# --- version de la herramienta
$init = Get-Content (Join-Path $raiz 'avacom_licencias\__init__.py') -Raw
if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { throw 'No se encontro __version__ en avacom_licencias\__init__.py.' }
$version = $Matches[1]
$nombre = "AVACOM-Emisor-Licencias-$version"
if (-not $Salida) { $Salida = Join-Path $raiz "dist\$nombre" }
Write-Host "== Emisor de Licencias $version -> $Salida"

# --- comprobaciones previas
if (-not (Test-Path $venvSitio)) { throw "No existe el venv del backend ($venvSitio). Crealo primero: es de donde se copian cryptography y sus dependencias." }
$cfg = Get-Content $venvCfg -Raw
if ($cfg -notmatch 'version\s*=\s*(\d+\.\d+)') { throw 'No se pudo leer la version de Python del venv.' }
$venvMenor = $Matches[1]
$embebidoMenor = (($PythonVersion -split '\.')[0..1]) -join '.'
if ($venvMenor -ne $embebidoMenor) { throw "El venv usa Python $venvMenor y el embeddable seria ${embebidoMenor}: las ruedas nativas no son compatibles." }
foreach ($paquete in 'cryptography', 'cffi', 'pycparser') {
    if (-not (Test-Path (Join-Path $venvSitio $paquete))) { throw "Falta $paquete en el venv del backend." }
}

# --- carpeta de salida limpia
if (Test-Path $Salida) { Remove-Item -Recurse -Force $Salida }
New-Item -ItemType Directory -Force -Path $Salida | Out-Null

# --- Python embeddable (de la cache del instalador; internet solo si no esta)
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $env:LOCALAPPDATA 'AVACOM\build-cache\python' }
New-Item -ItemType Directory -Force -Path $CacheDirectory | Out-Null
$zipNombre = "python-$PythonVersion-embed-amd64.zip"
$zipRuta = Join-Path $CacheDirectory $zipNombre
if (-not (Test-Path $zipRuta)) {
    Write-Host "  Descargando $zipNombre ..."
    $anterior = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    try { Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PythonVersion/$zipNombre" -OutFile $zipRuta -UseBasicParsing } finally { $ProgressPreference = $anterior }
} else {
    Write-Host "  $zipNombre ya estaba en la cache de compilacion."
}
$python = Join-Path $Salida 'python'
Expand-Archive -Path $zipRuta -DestinationPath $python -Force
if (-not (Test-Path (Join-Path $python 'python.exe'))) { throw 'El Python embeddable no trajo python.exe.' }

# --- cryptography y sus dependencias nativas, copiadas del venv del backend
$sitio = Join-Path $python 'Lib\site-packages'
New-Item -ItemType Directory -Force -Path $sitio | Out-Null
foreach ($paquete in 'cryptography', 'cffi', 'pycparser') {
    Copy-Item -Recurse -Force (Join-Path $venvSitio $paquete) (Join-Path $sitio $paquete)
    Get-ChildItem $venvSitio -Directory -Filter "$paquete-*.dist-info" | ForEach-Object { Copy-Item -Recurse -Force $_.FullName (Join-Path $sitio $_.Name) }
}
Get-ChildItem $venvSitio -File -Filter '_cffi_backend*.pyd' | ForEach-Object { Copy-Item -Force $_.FullName $sitio }
Get-ChildItem $sitio -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

# --- el ._pth es lo unico que define sys.path en el embeddable
$corto = (($PythonVersion -split '\.')[0..1]) -join ''
$pth = Join-Path $python "python$corto._pth"
if (-not (Test-Path $pth)) { throw "No se encontro $pth." }
Set-Content -Path $pth -Encoding ASCII -Value @("python$corto.zip", '.', 'Lib\site-packages', '..')

# --- la herramienta
$destino = Join-Path $Salida 'avacom_licencias'
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Get-ChildItem (Join-Path $raiz 'avacom_licencias') -File -Filter '*.py' | ForEach-Object { Copy-Item -Force $_.FullName $destino }
foreach ($archivo in 'iniciar.py', 'Emitir-Licencia.bat', 'avacom-licencias.bat', 'LEEME.txt') { Copy-Item -Force (Join-Path $raiz $archivo) $Salida }
Copy-Item -Recurse -Force (Join-Path $raiz 'planes') (Join-Path $Salida 'planes')

# --- SOLO el dominio puro del nodo
$vendor = Join-Path $Salida 'vendor\licenciamiento'
New-Item -ItemType Directory -Force -Path (Join-Path $vendor 'dominio') | Out-Null
Copy-Item -Force (Join-Path $repo 'backend\licenciamiento\__init__.py') $vendor
Get-ChildItem (Join-Path $repo 'backend\licenciamiento\dominio') -File -Filter '*.py' | ForEach-Object { Copy-Item -Force $_.FullName (Join-Path $vendor 'dominio') }

# --- carpetas de trabajo
foreach ($c in 'entrada', 'salida', 'datos', 'claves-publicas') { New-Item -ItemType Directory -Force -Path (Join-Path $Salida $c) | Out-Null }

# --- comprobaciones del contenido (LT-48): nada de llaves privadas, de desarrollo ni de pruebas
$semilla = 'avacom-licencia-' + 'desarrollo'
$prohibidos = @($semilla, ('BEGIN ' + 'PRIVATE KEY'), ('licenciamiento' + '.tests'))
$archivosTexto = Get-ChildItem $Salida -Recurse -File | Where-Object { $_.Extension -in '.py', '.bat', '.json', '.txt', '.md' -and $_.FullName -notmatch '\\python\\' }
foreach ($archivo in $archivosTexto) {
    foreach ($patron in $prohibidos) {
        if (Select-String -Path $archivo.FullName -Pattern $patron -SimpleMatch -Quiet) {
            if ($patron -eq ('licenciamiento' + '.tests') -and (Select-String -Path $archivo.FullName -Pattern '^\s*(from|import)\s+licenciamiento\.tests' -Quiet) -eq $false) { continue }
            throw "El paquete contiene '$patron' en $($archivo.Name): no se entrega."
        }
    }
}
if (Get-ChildItem $Salida -Recurse -Filter '*.avkey' -ErrorAction SilentlyContinue) { throw 'El paquete contiene una llave privada (.avkey).' }
if (Test-Path (Join-Path $vendor 'tests')) { throw 'El paquete trae las pruebas del nodo.' }

# --- humo: la herramienta corre con su propio Python
$pythonExe = Join-Path $python 'python.exe'
$humo = & $pythonExe (Join-Path $Salida 'iniciar.py') planes 2>&1
if ($LASTEXITCODE -ne 0) { throw "La prueba de humo fallo: $humo" }
$humo = & $pythonExe (Join-Path $Salida 'iniciar.py') --version 2>&1
Write-Host "  Prueba de humo: $humo"

# --- zip y huella
if ($Zip) {
    $zipSalida = "$Salida.zip"
    if (Test-Path $zipSalida) { Remove-Item -Force $zipSalida }
    # Un antivirus puede tener abierto, un instante, lo que acaba de ejecutarse (la prueba de humo): se reintenta antes de rendirse.
    for ($intento = 1; $intento -le 4 -and -not (Test-Path $zipSalida); $intento++) {
        try { Compress-Archive -Path (Join-Path $Salida '*') -DestinationPath $zipSalida -CompressionLevel Optimal -ErrorAction Stop } catch { Start-Sleep -Seconds 2 }
    }
    if (-not (Test-Path $zipSalida)) { throw "No se pudo crear $zipSalida." }
    $hash = (Get-FileHash $zipSalida -Algorithm SHA256).Hash.ToLower()
    Set-Content -Path "$zipSalida.sha256" -Encoding ASCII -Value "$hash  $(Split-Path $zipSalida -Leaf)"
    Write-Host "  Zip: $zipSalida"
    Write-Host "  SHA-256: $hash"
}
$tamano = [math]::Round(((Get-ChildItem $Salida -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "== Listo: $Salida ($tamano MB)"
