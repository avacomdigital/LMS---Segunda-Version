# Funciones compartidas por las alternativas sin cable de scripts\android. Se usa con: . (Join-Path $PSScriptRoot '..\comun\AdbComun.ps1')
# No instala controladores ni toca el sistema: adb va en una carpeta propia del usuario.

$script:Paquete = 'com.avacom.lms.student'
$script:CarpetaAdb = Join-Path $env:LOCALAPPDATA 'AVACOM\platform-tools'

function Paso($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Bien($t) { Write-Host $t -ForegroundColor Green }
function Aviso($t) { Write-Host $t -ForegroundColor Yellow }
function Termina($t) {
    Write-Host "`nERROR: $t" -ForegroundColor Red
    Read-Host 'Pulsa Enter para cerrar' | Out-Null
    exit 1
}

# Devuelve la ruta de adb.exe. Usa SIEMPRE la copia propia (la descarga una vez); no usa la del Android SDK.
function Obtener-Adb {
    $adb = Join-Path $script:CarpetaAdb 'adb.exe'
    if (-not (Test-Path $adb)) {
        Paso 'Descargando adb (una sola vez, unos 7 MB)'
        $zip = Join-Path $env:TEMP 'avacom-platform-tools.zip'
        $destino = Split-Path $script:CarpetaAdb
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile $zip -UseBasicParsing -ErrorAction Stop
            New-Item -ItemType Directory -Force $destino | Out-Null
            Expand-Archive -Path $zip -DestinationPath $destino -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
        } catch {
            Termina 'No se pudo descargar adb. Revisa que este equipo tenga internet y vuelve a tocar el archivo.'
        }
        if (-not (Test-Path $adb)) { Termina 'La descarga no trajo adb.exe. Vuelve a intentarlo.' }
    }
    return $adb
}

# Elige el APK: el indicado, o el kiosco arm64 mas nuevo de C:\avs05\out, o el de installer\student-android.
function Buscar-Apk([string]$Indicado) {
    if ($Indicado) {
        if (Test-Path $Indicado) { return (Resolve-Path $Indicado).Path }
        Termina "No existe el APK indicado: $Indicado"
    }
    $raiz = Resolve-Path (Join-Path $PSScriptRoot '..\..\..') -ErrorAction SilentlyContinue
    $candidatos = @()
    $candidatos += Get-ChildItem 'C:\avs05\out' -Filter '*arm64*.apk' -ErrorAction SilentlyContinue
    if ($raiz) { $candidatos += Get-ChildItem (Join-Path $raiz.Path 'installer\student-android') -Filter '*.apk' -ErrorAction SilentlyContinue }
    $candidatos += Get-ChildItem (Join-Path $PSScriptRoot '..') -Filter '*.apk' -Recurse -ErrorAction SilentlyContinue
    $mejor = $candidatos | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $mejor) { Termina 'No encuentro el APK de Student. Copia el archivo .apk junto a este script y vuelve a tocarlo.' }
    return $mejor.FullName
}

# Instala el APK en un destino de adb (serial o ip:puerto). Devuelve un texto con el resultado.
function Instalar-En([string]$Adb, [string]$Destino, [string]$Apk, [bool]$Reemplazar) {
    $salida = (& $Adb -s $Destino install -r $Apk 2>&1) -join ' '
    if ($salida -match 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' -or $salida -match 'INSTALL_FAILED_VERSION_DOWNGRADE') {
        if (-not $Reemplazar) { return 'FALLO: ya hay otra Student instalada con distinta firma. Repite con "reemplazar" (borra sus datos en la tableta).' }
        & $Adb -s $Destino uninstall $script:Paquete | Out-Null
        $salida = (& $Adb -s $Destino install -r $Apk 2>&1) -join ' '
    }
    if ($salida -match 'Success') { return 'OK' }
    if ($salida -match 'NO_MATCHING_ABIS') { return 'FALLO: el APK no es para este procesador (usa el APK arm64).' }
    return "FALLO: $salida"
}
