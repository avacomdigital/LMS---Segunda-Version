<#
.SYNOPSIS
    Construye el APK de AVACOM Student (Android) para instalarlo a mano en las tabletas.

.DESCRIPTION
    Publica src\Avacom.Lms.Student para net10.0-android en Release, firmado, y deja en
    installer\student-android\ un solo archivo instalable: "Student LMS <version>.apk".

    No toca ningun proyecto del repositorio: el nombre visible ("Student LMS"), la version y el
    codigo de version se inyectan por propiedades de MSBuild, igual que Distribucion.props hace
    con OPS. La version sale de installer\version.json (fuente unica del producto) y el codigo
    de version de Android se deriva de ella: major*10000 + minor*100 + patch (2.2.0 -> 20200).
    Android solo deja actualizar encima si el codigo AUMENTA; -Revision lo sube sin cambiar la
    version cuando hay que reinstalar el mismo numero.

    Firma: por defecto, la llave de depuracion de Android (%USERPROFILE%\.android\debug.keystore).
    Sirve para probar y para actualizar encima mientras sea la MISMA llave en todas las versiones;
    si se pierde, cada tableta debe desinstalar antes de instalar la nueva. La llave de una entrega
    real y quien la custodia es una decision pendiente (spec-driven\instalador\contexto.md, punto 6).

.PARAMETER Arquitectura
    android-arm64 (tabletas reales, por defecto) o android-x64 (emulador).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installer\build\Build-StudentApk.ps1
#>
[CmdletBinding()]
param(
    [string] $Version,
    [int] $Revision = 0,
    [ValidateSet('android-arm64', 'android-x64')] [string] $Arquitectura = 'android-arm64',
    [string] $Keystore = (Join-Path $env:USERPROFILE '.android\debug.keystore'),
    [string] $KeystoreAlias = 'androiddebugkey',
    [string] $KeystoreClave = 'android',
    [string] $AndroidSdk = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$proyecto = Join-Path $raiz 'src\Avacom.Lms.Student\Avacom.Lms.Student.csproj'
$salida = Join-Path $raiz 'installer\student-android'
$trabajo = Join-Path $raiz 'dist\student-android'
$nombre = 'Student LMS'

function Paso([string] $texto) { Write-Host ''; Write-Host "==> $texto" -ForegroundColor Cyan }

if (-not $Version) {
    $Version = (Get-Content (Join-Path $raiz 'installer\version.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
}
if ($Version -notmatch '^(\d+)\.(\d+)\.(\d+)$') { throw "Version '$Version' no es major.minor.patch." }
$codigo = [int]$Matches[1] * 10000 + [int]$Matches[2] * 100 + [int]$Matches[3] + $Revision

Paso 'Comprobando el equipo de compilacion'
if (-not $AndroidSdk) {
    $candidatos = @(
        $env:ANDROID_HOME, $env:ANDROID_SDK_ROOT,
        'C:\Program Files (x86)\Android\android-sdk',
        (Join-Path $env:LOCALAPPDATA 'Android\Sdk')
    ) | Where-Object { $_ -and (Test-Path (Join-Path $_ 'platforms\android-36')) }
    if (-not $candidatos) { throw 'No hay un Android SDK con la plataforma android-36 (API 36), que pide .NET 10 para compilar.' }
    $AndroidSdk = @($candidatos)[0]
}
if (-not (Test-Path $Keystore)) { throw "No existe la llave de firma: $Keystore" }
Write-Host "Android SDK : $AndroidSdk"
Write-Host "Llave       : $Keystore ($KeystoreAlias)"
Write-Host "Version     : $Version  (codigo de version $codigo)  $Arquitectura"

Paso 'Publicando el APK firmado (Release)'
if (Test-Path $trabajo) { Remove-Item $trabajo -Recurse -Force }
$estaVez = Get-Date
& dotnet publish $proyecto -f net10.0-android -c Release `
    -p:RuntimeIdentifier=$Arquitectura `
    -p:AndroidPackageFormat=apk `
    -p:AndroidSdkDirectory="$AndroidSdk" `
    -p:ApplicationTitle="$nombre" `
    -p:ApplicationDisplayVersion=$Version `
    -p:ApplicationVersion=$codigo `
    -p:AndroidKeyStore=true `
    -p:AndroidSigningKeyStore="$Keystore" `
    -p:AndroidSigningKeyAlias=$KeystoreAlias `
    -p:AndroidSigningKeyPass="$KeystoreClave" `
    -p:AndroidSigningStorePass="$KeystoreClave" `
    -o $trabajo
if ($LASTEXITCODE -ne 0) { throw "dotnet publish fallo ($LASTEXITCODE)." }

Paso 'Verificando el APK'
$apk = Get-ChildItem $trabajo -Filter '*-Signed.apk' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $apk) { throw "No se produjo un APK firmado en $trabajo." }
if ($apk.LastWriteTime -lt $estaVez) { throw "El APK $($apk.Name) es anterior a esta compilacion: no se usa." }

$bt = Get-ChildItem (Join-Path $AndroidSdk 'build-tools') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$aapt2 = Join-Path $bt.FullName 'aapt2.exe'
$apksigner = Join-Path $bt.FullName 'apksigner.bat'
$info = (& $aapt2 dump badging $apk.FullName) -join "`n"
if ($info -notmatch "package: name='com\.avacom\.lms\.student' versionCode='$codigo' versionName='$([regex]::Escape($Version))'") {
    throw "El APK no declara la version esperada ($Version / $codigo):`n$($info.Split("`n")[0])"
}
if ($info -notmatch "application-label:'$nombre'") { throw "El APK no se llama '$nombre'." }
$firma = (& $apksigner verify --verbose --print-certs $apk.FullName) -join "`n"
if ($firma -notmatch 'Verifies') { throw "La firma del APK no verifica:`n$firma" }

Paso 'Dejando el instalador'
New-Item -ItemType Directory -Force $salida | Out-Null
Get-ChildItem $salida -Filter '*.apk' | Remove-Item -Force
$destino = Join-Path $salida "$nombre $Version.apk"
Copy-Item $apk.FullName $destino -Force
$sha = (Get-FileHash $destino -Algorithm SHA256).Hash
$cert = ($firma -split "`n" | Where-Object { $_ -match 'certificate SHA-256 digest' } | Select-Object -First 1)
$revGit = (& git -C $raiz rev-parse --short HEAD)
$sucio = [bool](& git -C $raiz status --porcelain -uno -- src installer/version.json)
@"
Student LMS $Version  (codigo de version $codigo, $Arquitectura)
Archivo : $(Split-Path $destino -Leaf)
SHA-256 : $sha
Firma   : $cert
Git     : $revGit$(if ($sucio) { '  (con cambios sin confirmar en src)' })
Paquete : com.avacom.lms.student  |  Android minimo declarado: 5.0 (API 21)  |  Objetivo de pruebas: Android 13 y 14 (API 33 y 34)
"@ | Set-Content (Join-Path $salida 'LEEME.txt') -Encoding UTF8

Write-Host ''
Write-Host "APK listo: $destino" -ForegroundColor Green
Write-Host ("Tamano   : {0:N1} MB   SHA-256: {1}" -f ((Get-Item $destino).Length / 1MB), $sha)
