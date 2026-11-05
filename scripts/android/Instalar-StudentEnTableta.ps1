<#
.SYNOPSIS
    Instala la Student de AVACOM en UNA tableta Android por USB y, si se pide, la fija como Device Owner.

.DESCRIPTION
    Pasos: (1) opcional -ArreglarDriver, (2) adb ve la tableta, (3) comprueba la arquitectura,
    (4) instala el APK, (5) opcional -FijarOwner (llama a Provision-DeviceOwner.ps1).

    -ArreglarDriver necesita ADMINISTRADOR (el script se vuelve a lanzar solo con el aviso de UAC).
    Registra en Windows el identificador de interfaz que adb busca en la interfaz "ADB Interface"
    de la tableta (valor DeviceInterfaceGUIDs) y reinicia ese dispositivo. No instala ningun driver.
    Es reversible: -QuitarArreglo borra ese valor. No se ha probado en otras tabletas.

    Nunca desinstala la Student salvo que pases -Desinstalar (borra los datos de la app en la tableta).
    -FijarOwner es IRREVERSIBLE (solo un restablecimiento de fabrica lo deshace).

.PARAMETER Serial          Serial de adb. Opcional si solo hay una tableta.
.PARAMETER Apk             APK a instalar. Por omision, el arm64 de C:\avs05\out.
.PARAMETER Vid             Fabricante USB para el arreglo del driver (VID_2207 = Rockchip).
.PARAMETER ArreglarDriver  Registra el identificador de interfaz ADB (pide administrador).
.PARAMETER QuitarArreglo   Deshace -ArreglarDriver (pide administrador).
.PARAMETER Desinstalar     Si falla por llave distinta, desinstala la Student y reintenta.
.PARAMETER FijarOwner      Al terminar, ejecuta Provision-DeviceOwner.ps1 para esta tableta.
.PARAMETER DryRun          Muestra lo que haria sin ejecutar nada.

.EXAMPLE
    .\Instalar-StudentEnTableta.ps1 -ArreglarDriver
.EXAMPLE
    .\Instalar-StudentEnTableta.ps1
.EXAMPLE
    .\Instalar-StudentEnTableta.ps1 -FijarOwner
#>
[CmdletBinding()]
param(
    [string]$Serial,
    [string]$Apk = 'C:\avs05\out\Student-LMS-2.12.0-kiosco-politica-arm64.apk',
    [string]$AdbPath = 'C:\Users\AVACOM\AppData\Local\Android\Sdk\platform-tools\adb.exe',
    [string]$Vid = 'VID_2207',
    [switch]$ArreglarDriver,
    [switch]$QuitarArreglo,
    [switch]$Desinstalar,
    [switch]$FijarOwner,
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$Paquete = 'com.avacom.lms.student'
$GuidAdb = '{F72FE0D4-CBCB-407D-8814-9ED673D0DD6}'
$script:Elevado = $false

function Paso($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Falla($t) {
    Write-Host "ERROR: $t" -ForegroundColor Red
    if ($script:Elevado) { Read-Host 'Enter para cerrar' | Out-Null }
    exit 1
}
function Es-Admin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- 1. Arreglo del driver (administrador) ---
if ($ArreglarDriver -or $QuitarArreglo) {
    if (-not (Es-Admin)) {
        if ($DryRun) { Write-Host '[DRY-RUN] Se volveria a lanzar como administrador.'; exit 0 }
        Paso 'Pidiendo permisos de administrador (acepta el aviso de Windows)'
        $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
        foreach ($p in $PSBoundParameters.GetEnumerator()) {
            if ($p.Value -is [switch]) { if ($p.Value.IsPresent) { $argumentos += "-$($p.Key)" } }
            else { $argumentos += "-$($p.Key)"; $argumentos += "`"$($p.Value)`"" }
        }
        Start-Process powershell.exe -Verb RunAs -ArgumentList $argumentos
        exit 0
    }
    $script:Elevado = $true
    Paso 'Registrando la interfaz ADB en Windows'
    $interfaces = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "USB\$Vid*" -and $_.FriendlyName -eq 'ADB Interface' })
    if ($interfaces.Count -eq 0) { Falla "No hay ninguna 'ADB Interface' $Vid conectada. Conecta la tableta y activa la depuracion USB." }
    foreach ($i in $interfaces) {
        $clave = "HKLM:\SYSTEM\CurrentControlSet\Enum\$($i.InstanceId)\Device Parameters"
        Write-Host "Dispositivo: $($i.InstanceId)"
        if ($QuitarArreglo) {
            if ($DryRun) { Write-Host "[DRY-RUN] Borraria DeviceInterfaceGUIDs en $clave"; continue }
            Remove-ItemProperty -Path $clave -Name DeviceInterfaceGUIDs -ErrorAction SilentlyContinue
        } else {
            if ($DryRun) { Write-Host "[DRY-RUN] Escribiria DeviceInterfaceGUIDs=$GuidAdb en $clave"; continue }
            New-ItemProperty -Path $clave -Name DeviceInterfaceGUIDs -PropertyType MultiString -Value @($GuidAdb) -Force | Out-Null
        }
        & pnputil.exe /restart-device "$($i.InstanceId)" | Out-Host
    }
    Start-Sleep -Seconds 4
    if ($QuitarArreglo) { Write-Host 'Arreglo deshecho.'; Read-Host 'Enter para cerrar' | Out-Null; exit 0 }
}

# --- 2. adb ve la tableta ---
Paso 'Buscando la tableta con adb'
if (-not (Test-Path $AdbPath)) { Falla "No existe adb en $AdbPath" }
if ($DryRun) {
    Write-Host "[DRY-RUN] adb devices; getprop ro.product.cpu.abi; install -r `"$Apk`""
    if ($FijarOwner) { Write-Host '[DRY-RUN] Provision-DeviceOwner.ps1' }
    exit 0
}
& $AdbPath kill-server | Out-Null
& $AdbPath start-server | Out-Null
$lista = & $AdbPath devices
$lista | Out-Host
$tabletas = @($lista | Select-Object -Skip 1 | Where-Object { $_ -match '\s(device|unauthorized|offline)$' })
if ($tabletas.Count -eq 0) { Falla 'adb no ve ninguna tableta. Si Windows la detecta, ejecuta con -ArreglarDriver; si no, revisa el cable y la depuracion USB.' }
if ($tabletas | Where-Object { $_ -match 'unauthorized' }) { Falla 'La tableta pide autorizacion: acepta el aviso "Permitir depuracion USB" en su pantalla y repite.' }
if (-not $Serial) {
    if ($tabletas.Count -gt 1) { Falla 'Hay varias tabletas: indica -Serial.' }
    $Serial = ($tabletas[0] -split '\s+')[0]
}
Write-Host "Tableta: $Serial"
function Adb { & $AdbPath -s $Serial @args }

# --- 3. Arquitectura y version ---
Paso 'Comprobando la tableta'
$abi = ((Adb shell getprop ro.product.cpu.abi) -join '').Trim()
$android = ((Adb shell getprop ro.build.version.release) -join '').Trim()
$modelo = ((Adb shell getprop ro.product.model) -join '').Trim()
Write-Host "Modelo: $modelo | Android $android | ABI $abi"
if ($abi -ne 'arm64-v8a' -and $Apk -like '*arm64*') { Falla "La tableta es $abi y el APK es arm64. Indica el APK correcto con -Apk." }
if ($android -notlike '14*') { Write-Host "AVISO: Android $android (la prueba es para Android 14)." -ForegroundColor Yellow }
if (-not (Test-Path $Apk)) { Falla "No existe el APK: $Apk" }

# --- 4. Instalar ---
Paso 'Instalando la Student'
$yaEsta = (Adb shell pm list packages $Paquete) -join ''
if ($yaEsta) { Write-Host 'La Student ya estaba instalada: se actualiza con install -r.' }
$salida = (Adb install -r $Apk 2>&1) -join "`n"
Write-Host $salida
if ($salida -match 'INSTALL_FAILED_UPDATE_INCOMPATIBLE') {
    if (-not $Desinstalar) { Falla 'La app instalada esta firmada con otra llave. Repite con -Desinstalar (borra sus datos en la tableta).' }
    Write-Host 'Desinstalando la version anterior...' -ForegroundColor Yellow
    Adb uninstall $Paquete | Out-Host
    $salida = (Adb install -r $Apk 2>&1) -join "`n"
    Write-Host $salida
}
if ($salida -notmatch 'Success') { Falla 'La instalacion no termino con Success.' }
Adb shell dumpsys package $Paquete | Select-String 'versionName|versionCode' | Select-Object -First 2 | Out-Host

# --- 5. Device Owner (opcional) ---
if ($FijarOwner) {
    Paso 'Fijando el Device Owner (irreversible)'
    & (Join-Path $PSScriptRoot 'Provision-DeviceOwner.ps1') -Serial $Serial -AdbPath $AdbPath
    if ($LASTEXITCODE -ne 0) { Falla 'Provision-DeviceOwner.ps1 fallo.' }
}
Write-Host "`nListo." -ForegroundColor Green
if ($script:Elevado) { Read-Host 'Enter para cerrar' | Out-Null }
