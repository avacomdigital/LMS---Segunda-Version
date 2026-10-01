<#
.SYNOPSIS
    Convierte la app Student de AVACOM en Device Owner de UNA tableta Android por ADB.

.DESCRIPTION
    Automatiza los pasos de kiosk.md §3.5 para una tableta conectada por ADB (la APK ya debe
    estar instalada):

        adb shell dumpsys account        ->  debe mostrar «Accounts: 0»
        adb shell dpm list-owners        ->  debe decir «no owners»
        adb shell pm list users          ->  exactamente un UserInfo
        adb shell dpm set-device-owner <componente>
        adb shell dpm list-owners        ->  debe NOMBRAR el paquete (un «Success» no basta)

    Solo ejecuta set-device-owner si TODAS las comprobaciones previas pasan. Antes avisa de que
    es IRREVERSIBLE (solo un restablecimiento de fábrica lo deshace) y exige teclear el número
    de serie de la tableta (o usar -Force).

    -DryRun: imprime los comandos adb que ejecutaría y NO llama a adb en absoluto (ni siquiera
    «adb devices»).

    -Verify: solo lectura. Ejecuta «dpm list-owners» (debe nombrar el paquete) y filtra
    «dumpsys activity activities» por LockTaskModeState (el nombre exacto varía por versión de
    Android; con la tableta fuera de examen suele ser NONE). Combinable con -DryRun.

    Códigos de salida: 0 = correcto / verificado; 1 = error, comprobación fallida o cancelado.

    LÍMITES: el apagado forzado por hardware (mantener el botón) no lo impide ningún software.
    Este script se escribió a partir de la documentación y NO se ha probado en una tableta real.

.PARAMETER Serial
    Número de serie de la tableta (el de «adb devices»). Opcional si solo hay un dispositivo.

.PARAMETER Component
    Componente del receptor de administración. Predeterminado:
    com.avacom.lms.student/com.avacom.lms.student.ExamDeviceAdminReceiver

.PARAMETER AdbPath
    Ejecutable de adb. Predeterminado: «adb» (del PATH).

.PARAMETER DryRun
    Solo imprime los comandos que ejecutaría; no llama a adb.

.PARAMETER Force
    Omite la confirmación tecleando el número de serie. NO omite ninguna comprobación previa.

.PARAMETER Verify
    Solo lectura: comprueba que la app es Device Owner y muestra el estado de Lock Task.

.EXAMPLE
    .\Provision-DeviceOwner.ps1 -DryRun

.EXAMPLE
    .\Provision-DeviceOwner.ps1 -Serial R58M12345AB

.EXAMPLE
    .\Provision-DeviceOwner.ps1 -Serial R58M12345AB -Verify
#>
[CmdletBinding()]
param(
    [string]$Serial,

    [string]$Component = 'com.avacom.lms.student/com.avacom.lms.student.ExamDeviceAdminReceiver',

    [string]$AdbPath = 'adb',

    [switch]$DryRun,

    [switch]$Force,

    [switch]$Verify
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:AdbExe = $null
$script:AdbSerial = $null
$script:AndroidExitCode = 0

function Write-AdbLog {
    param(
        [Parameter(Mandatory = $true, Position = 0)][ValidateSet('INFO', 'WARN', 'ERROR', 'OK', 'DRYRUN', 'STEP')][string]$Level,
        [Parameter(Mandatory = $true, Position = 1)][AllowEmptyString()][string]$Message
    )
    $color = 'Gray'
    switch ($Level) {
        'WARN'   { $color = 'Yellow' }
        'ERROR'  { $color = 'Red' }
        'OK'     { $color = 'Green' }
        'DRYRUN' { $color = 'Cyan' }
        'STEP'   { $color = 'White' }
    }
    Write-Host ('[{0}] {1}' -f $Level, $Message) -ForegroundColor $color
}

function Resolve-AdbExecutable {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (Test-Path -LiteralPath $Name -PathType Leaf) { return (Resolve-Path -LiteralPath $Name).Path }
    $cmd = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $cmd) { return $cmd.Source }
    return $null
}

function Invoke-Adb {
    <# Ejecuta adb (sin cmd ni 2>&1) y devuelve ExitCode, StdOut y StdErr. NUNCA se llama en -DryRun. #>
    param([Parameter(Mandatory = $true)][string[]]$AdbArguments)

    if ($DryRun) { throw 'Error interno: se intento llamar a adb en modo -DryRun.' }
    if ([string]::IsNullOrEmpty($script:AdbExe)) { throw 'Error interno: adb no esta resuelto.' }

    $parts = @()
    foreach ($a in $AdbArguments) {
        if ($a -match '[\s"]') { $parts += ('"' + ($a -replace '"', '\"') + '"') } else { $parts += $a }
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:AdbExe
    $psi.Arguments = ($parts -join ' ')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = [System.Diagnostics.Process]::Start($psi)
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()
    if (-not $proc.WaitForExit(60000)) {
        try { $proc.Kill() } catch { }
        throw 'adb no respondio en 60 s.'
    }
    $proc.WaitForExit()
    return [pscustomobject]@{
        ExitCode = $proc.ExitCode
        StdOut   = [string]$outTask.Result
        StdErr   = [string]$errTask.Result
    }
}

function Invoke-AdbOnDevice {
    <# adb -s <serie> <argumentos...> #>
    param([Parameter(Mandatory = $true)][string[]]$AdbArguments)
    return (Invoke-Adb -AdbArguments (@('-s', $script:AdbSerial) + $AdbArguments))
}

function ConvertFrom-AdbDevices {
    <# Interpreta la salida de «adb devices». Devuelve objetos Serial/State. #>
    param([AllowEmptyString()][string]$Text)
    $list = @()
    foreach ($line in ($Text -split "`r?`n")) {
        $l = $line.Trim()
        if ($l -eq '' -or $l.StartsWith('List of devices') -or $l.StartsWith('*')) { continue }
        if ($l -match '^(\S+)\s+(.+)$') {
            $list += [pscustomobject]@{ Serial = $Matches[1]; State = $Matches[2].Trim() }
        }
    }
    return $list
}

function Test-AccountsAreZero {
    <# «dumpsys account»: debe haber al menos una linea «Accounts: N» y todas con N = 0. #>
    param([AllowEmptyString()][string]$Text)
    $found = 0
    foreach ($m in [regex]::Matches($Text, '(?im)^\s*Accounts:\s*(\d+)')) {
        $found++
        if ([int]$m.Groups[1].Value -ne 0) { return $false }
    }
    return ($found -gt 0)
}

function Test-NoOwners {
    param([AllowEmptyString()][string]$Text)
    return ($Text -match '(?i)no owners')
}

function Get-UserInfoCount {
    param([AllowEmptyString()][string]$Text)
    return ([regex]::Matches($Text, 'UserInfo\{')).Count
}

function Test-OwnerNamesPackage {
    <# «dpm list-owners» debe NOMBRAR el paquete; «no owners» o un «Success» suelto no valen. #>
    param([AllowEmptyString()][string]$Text, [Parameter(Mandatory = $true)][string]$Package)
    if (Test-NoOwners -Text $Text) { return $false }
    return ($Text.IndexOf($Package, [System.StringComparison]::Ordinal) -ge 0)
}

function Format-AdbCommand {
    param([string[]]$AdbArguments, [string]$SerialText)
    $prefix = $AdbPath
    if (-not [string]::IsNullOrEmpty($SerialText)) { $prefix = $AdbPath + ' -s ' + $SerialText }
    return ($prefix + ' ' + ($AdbArguments -join ' '))
}

function Select-AdbDevice {
    <# Fija $script:AdbSerial. Exige exactamente un dispositivo elegido y en estado «device». #>
    $r = Invoke-Adb -AdbArguments @('devices')
    if ($r.ExitCode -ne 0) { throw ("'adb devices' fallo: " + $r.StdErr.Trim()) }
    $devs = @(ConvertFrom-AdbDevices -Text $r.StdOut)
    if ($devs.Count -eq 0) { throw 'No hay ninguna tableta conectada (adb devices vacio). Conecta el cable y acepta la depuracion USB en la tableta.' }

    if (-not [string]::IsNullOrEmpty($Serial)) {
        $match = @($devs | Where-Object { $_.Serial -ceq $Serial })
        if ($match.Count -ne 1) {
            throw ("El numero de serie '{0}' no aparece en adb devices. Dispositivos vistos: {1}" -f $Serial, (($devs | ForEach-Object { $_.Serial + ' (' + $_.State + ')' }) -join ', '))
        }
        $chosen = $match[0]
    } else {
        if ($devs.Count -gt 1) {
            throw ('Hay {0} dispositivos conectados: {1}. Indica cual con -Serial.' -f $devs.Count, (($devs | ForEach-Object { $_.Serial + ' (' + $_.State + ')' }) -join ', '))
        }
        $chosen = $devs[0]
    }
    if ($chosen.State -ne 'device') {
        throw ("El dispositivo '{0}' esta en estado '{1}' (se necesita 'device'). Si es 'unauthorized', acepta la clave RSA en la pantalla de la tableta." -f $chosen.Serial, $chosen.State)
    }
    $script:AdbSerial = $chosen.Serial
}

function Invoke-ReadOnlyCheck {
    <# Ejecuta un comando de lectura en la tableta y falla si adb devuelve error. #>
    param([Parameter(Mandatory = $true)][string[]]$AdbArguments)
    $r = Invoke-AdbOnDevice -AdbArguments $AdbArguments
    if ($r.ExitCode -ne 0) {
        throw ("'{0}' devolvio {1}: {2}" -f (Format-AdbCommand -AdbArguments $AdbArguments -SerialText $script:AdbSerial), $r.ExitCode, ($r.StdErr + $r.StdOut).Trim())
    }
    return $r.StdOut
}

function Get-ComponentPackage {
    param([Parameter(Mandatory = $true)][string]$ComponentName)
    return $ComponentName.Split('/')[0]
}

function Show-DryRunPlan {
    param([string]$Package)
    $s = $Serial
    if ([string]::IsNullOrEmpty($s)) { $s = '<SERIE>' }
    Write-AdbLog DRYRUN 'Modo simulacion: NO se llama a adb. Estos son los comandos que se ejecutarian, en este orden:'
    $c = @()
    $c += ($AdbPath + ' devices                                   # elegir exactamente UN dispositivo')
    if ($Verify) {
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dpm', 'list-owners') -SerialText $s) + '          # debe nombrar ' + $Package
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dumpsys', 'activity', 'activities') -SerialText $s) + '   # filtrado por LockTaskModeState (en el PC, sin findstr)'
    } else {
        $c += (Format-AdbCommand -AdbArguments @('shell', 'pm', 'list', 'packages', $Package) -SerialText $s) + '   # la APK debe estar instalada'
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dumpsys', 'account') -SerialText $s) + '                  # debe mostrar Accounts: 0'
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dpm', 'list-owners') -SerialText $s) + '          # debe decir no owners'
        $c += (Format-AdbCommand -AdbArguments @('shell', 'pm', 'list', 'users') -SerialText $s) + '             # exactamente un UserInfo'
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dpm', 'set-device-owner', $Component) -SerialText $s) + '   # IRREVERSIBLE (solo un restablecimiento de fabrica lo deshace)'
        $c += (Format-AdbCommand -AdbArguments @('shell', 'dpm', 'list-owners') -SerialText $s) + '          # debe NOMBRAR ' + $Package + ' (un Success no basta)'
    }
    foreach ($line in $c) { Write-Host ('    ' + $line) }
    if (-not $Verify -and -not $Force) {
        Write-AdbLog DRYRUN 'Antes de set-device-owner se mostraria el aviso de irreversibilidad y se exigiria teclear el numero de serie (o -Force).'
    }
    Write-AdbLog OK 'SIMULACION TERMINADA. No se llamo a adb.'
}

function Invoke-VerifyDevice {
    param([string]$Package)
    $owners = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'dpm', 'list-owners')
    Write-AdbLog INFO ("dpm list-owners:`n" + $owners.Trim())
    $ok = Test-OwnerNamesPackage -Text $owners -Package $Package

    $act = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'dumpsys', 'activity', 'activities')
    $lt = @(($act -split "`r?`n") | Where-Object { $_ -match '(?i)LockTaskModeState' })
    if ($lt.Count -gt 0) {
        Write-AdbLog INFO ('LockTaskModeState (informativo; NONE = fuera de examen, LOCKED/PINNED = en examen):' + "`n" + (($lt | ForEach-Object { '  ' + $_.Trim() }) -join "`n"))
    } else {
        Write-AdbLog WARN 'No aparece LockTaskModeState en dumpsys activity activities (el nombre exacto varia por version de Android).'
    }
    if ($ok) {
        Write-AdbLog OK ("VERIFICADO: '{0}' es Device Owner de la tableta {1}." -f $Package, $script:AdbSerial)
        return 0
    }
    Write-AdbLog ERROR ("NO VERIFICADO: dpm list-owners no nombra '{0}'. La tableta NO esta aprovisionada." -f $Package)
    return 1
}

function Invoke-ProvisionDevice {
    param([string]$Package)

    # Comprobaciones previas (todas de solo lectura)
    Write-AdbLog STEP 'Comprobaciones previas (solo lectura)...'
    $pk = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'pm', 'list', 'packages', $Package)
    if ($pk -notmatch ('(?m)^package:' + [regex]::Escape($Package) + '\s*$')) {
        throw ("La app '{0}' no esta instalada en la tableta. Instala la APK antes de aprovisionar." -f $Package)
    }
    Write-AdbLog OK ("App instalada: {0}" -f $Package)

    $acc = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'dumpsys', 'account')
    if (-not (Test-AccountsAreZero -Text $acc)) {
        throw 'La tableta tiene cuentas configuradas (dumpsys account no muestra "Accounts: 0"). Restablece de fabrica y NO inicies sesion en ninguna cuenta.'
    }
    Write-AdbLog OK 'dumpsys account: Accounts: 0'

    $own = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'dpm', 'list-owners')
    if (-not (Test-NoOwners -Text $own)) {
        throw ("La tableta ya tiene propietario (dpm list-owners):`n" + $own.Trim() + "`nSolo un restablecimiento de fabrica permite cambiarlo.")
    }
    Write-AdbLog OK 'dpm list-owners: no owners'

    $usr = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'pm', 'list', 'users')
    $n = Get-UserInfoCount -Text $usr
    if ($n -ne 1) {
        throw ("pm list users debe mostrar exactamente un UserInfo y muestra {0}:`n{1}" -f $n, $usr.Trim())
    }
    Write-AdbLog OK 'pm list users: un unico usuario'

    # Confirmacion
    Write-Host ''
    Write-AdbLog WARN '*** ATENCION: set-device-owner es IRREVERSIBLE. Solo un restablecimiento de fabrica (con perdida de datos) lo deshace. ***'
    Write-AdbLog WARN ("Tableta: {0}  Componente: {1}" -f $script:AdbSerial, $Component)
    if (-not $Force) {
        $typed = Read-Host -Prompt ('Para continuar teclea el numero de serie exacto ({0})' -f $script:AdbSerial)
        if ($typed -cne $script:AdbSerial) { throw 'Cancelado: el numero de serie tecleado no coincide.' }
    } else {
        Write-AdbLog WARN '-Force: se omite la confirmacion por numero de serie.'
    }

    # Accion irreversible
    Write-AdbLog STEP 'Ejecutando dpm set-device-owner...'
    $r = Invoke-AdbOnDevice -AdbArguments @('shell', 'dpm', 'set-device-owner', $Component)
    $text = ($r.StdOut + "`n" + $r.StdErr).Trim()
    Write-AdbLog INFO ("Salida de set-device-owner (codigo {0}):`n{1}" -f $r.ExitCode, $text)
    if ($r.ExitCode -ne 0 -or $text -match '(?i)exception|error|not allowed|failed') {
        throw 'dpm set-device-owner fallo. Revisa la salida anterior (causas tipicas: hay cuentas, mas de un usuario, o ya hay propietario).'
    }

    # Verificacion posterior: un 'Success' no basta
    $after = Invoke-ReadOnlyCheck -AdbArguments @('shell', 'dpm', 'list-owners')
    Write-AdbLog INFO ("dpm list-owners:`n" + $after.Trim())
    if (-not (Test-OwnerNamesPackage -Text $after -Package $Package)) {
        throw ("set-device-owner no quedo verificado: dpm list-owners no nombra '{0}'." -f $Package)
    }
    Write-AdbLog OK ("LISTO: '{0}' es Device Owner de la tableta {1}." -f $Package, $script:AdbSerial)
    Write-AdbLog INFO 'Comprueba a mano con la tableta en examen: Inicio, Recientes, deslizar desde arriba, Atras y mantener el boton de encendido.'
    Write-AdbLog INFO 'El apagado forzado por hardware (mantener el boton varios segundos) no lo impide ningun software.'
    Write-AdbLog INFO 'Para comprobar en cualquier momento: .\Provision-DeviceOwner.ps1 -Verify'
}

function Invoke-ProvisionMain {
    if ($Verify) { $modeText = 'VERIFICAR (solo lectura)' } elseif ($DryRun) { $modeText = 'SIMULACION -DryRun (no se llama a adb)' } else { $modeText = 'REAL' }
    Write-AdbLog STEP ('AVACOM LMS - aprovisionar Device Owner (una tableta) - modo: ' + $modeText)

    if ($Component -notmatch '^[A-Za-z][A-Za-z0-9_.]*/[.A-Za-z][A-Za-z0-9_.$]*$') {
        throw "Componente no valido: '$Component'. Formato esperado: paquete/clase"
    }
    if ((-not [string]::IsNullOrEmpty($Serial)) -and ($Serial -notmatch '^[A-Za-z0-9._:\-]+$')) {
        throw "Numero de serie no valido: '$Serial'."
    }
    $package = Get-ComponentPackage -ComponentName $Component

    if ($DryRun) {
        Show-DryRunPlan -Package $package
        return
    }

    $script:AdbExe = Resolve-AdbExecutable -Name $AdbPath
    if ($null -eq $script:AdbExe) {
        throw "No se encuentra adb ('$AdbPath'). Instala Android platform-tools y anadelo al PATH, o pasa -AdbPath con la ruta completa."
    }
    Write-AdbLog INFO ('adb: ' + $script:AdbExe)

    Select-AdbDevice
    Write-AdbLog OK ('Dispositivo seleccionado: ' + $script:AdbSerial)

    if ($Verify) {
        $script:AndroidExitCode = Invoke-VerifyDevice -Package $package
    } else {
        Invoke-ProvisionDevice -Package $package
    }
}

function Invoke-Provision {
    try {
        Invoke-ProvisionMain
    } catch {
        Write-AdbLog ERROR $_.Exception.Message
        $script:AndroidExitCode = 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $null = Invoke-Provision
    exit $script:AndroidExitCode
}
