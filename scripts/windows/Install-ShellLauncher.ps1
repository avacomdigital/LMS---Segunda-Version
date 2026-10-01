<#
.SYNOPSIS
    Bloquea un equipo Windows para el examen de AVACOM LMS con Shell Launcher v2 (alternativa a Assigned Access).

.DESCRIPTION
    Alternativa a Install-Kiosk.ps1 para equipos Enterprise, Education o IoT Enterprise
    (Shell Launcher NO está disponible en Windows Pro: allí usa Install-Kiosk.ps1).

    Sustituye el shell (explorer.exe) por el ejecutable de la Student SOLO para la cuenta
    indicada; el resto de cuentas y el grupo Administradores conservan explorer.exe. Está
    pensado para ejecutables de escritorio estables (kiosk.md §4.5).

    Hace lo siguiente (modo real, como administrador):
      1. Comprueba la edición de Windows y la característica opcional Client-EmbeddedShellLauncher.
         Si está desactivada, NO la activa en silencio: muestra el comando exacto
             Enable-WindowsOptionalFeature -Online -FeatureName Client-EmbeddedShellLauncher -All -NoRestart
         y se detiene. Con -EnableFeature la activa el propio script (puede requerir reinicio:
         reinicia y vuelve a ejecutar el script).
      2. Exige OTRA cuenta administradora local habilitada (recuperación) y que la cuenta del
         kiosco sea un usuario estándar; la crea si falta (contraseña con Read-Host
         -AsSecureString o -Password SecureString; nunca se muestra ni se guarda).
      3. Configura por WMI (espacio de nombres root\standardcimv2\embedded, clase WESL_UserSetting):
           SetCustomShell(<SID del usuario>, <exe>, $null, $null, <acción al cerrarse>)
           SetDefaultShell('explorer.exe', reiniciar shell)
           SetCustomShell(<SID Administradores>, 'explorer.exe', ...)   <- recuperación segura
           SetEnabled($true)
      4. Escribe %ProgramData%\AVACOM\kiosk-provisioned.marker con "mode":"shell-launcher"
         (solo un indicio, kiosk.md §5.1) y el registro
         %ProgramData%\AVACOM\logs\kiosk-install.log (solo en modo real).

    -DryRun y -Verify funcionan SIN elevación y son estrictamente de solo lectura: no crean
    usuarios, no escriben WMI/registro ni archivos; en -DryRun todo va a la consola.
    -Verify consulta el estado REAL (WESL_UserSetting), no el marcador.

    ADVERTENCIA (sin probar): Shell Launcher cambia el shell, pero según la documentación de
    Microsoft NO oculta por sí solo las opciones de Ctrl+Alt+Supr (Administrador de tareas,
    Cambiar de usuario…). Si necesitas cerrar también esa vía, hacen falta directivas de cuenta
    adicionales que estos scripts NO aplican; Assigned Access (Install-Kiosk.ps1) sí restringe
    esa pantalla. Valídalo en un equipo real.

    Códigos de salida: 0 = correcto / aprovisionado; 1 = error, bloqueo o NO aprovisionado;
    2 = (solo -Verify) no se pudo comprobar el estado real sin privilegios de administrador.

.PARAMETER UserName
    Cuenta local del kiosco. Predeterminado: AvacomExam.

.PARAMETER ExecutablePath
    Ruta absoluta del ejecutable de la Student de Windows (OBLIGATORIO). Debe existir en modo
    real. Ejemplo: C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe

.PARAMETER Password
    Contraseña de la cuenta NUEVA como SecureString. Si falta, se pide con Read-Host -AsSecureString.

.PARAMETER OnShellExit
    Qué hace Windows cuando el shell (la Student) termina: RestartShell (predeterminado),
    RestartDevice, ShutdownDevice o DoNothing.

.PARAMETER EnableFeature
    Activa la característica Client-EmbeddedShellLauncher si está desactivada.

.PARAMETER DryRun
    Simulación sin cambios (funciona sin elevación).

.PARAMETER Force
    No pide la confirmación interactiva y permite continuar aunque la cuenta tenga ya una
    configuración de Assigned Access. No omite ninguna otra protección.

.PARAMETER Verify
    Solo lectura: consulta el estado real y sale con 0/1/2.

.EXAMPLE
    .\Install-ShellLauncher.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -DryRun

.EXAMPLE
    .\Install-ShellLauncher.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -EnableFeature

.EXAMPLE
    .\Install-ShellLauncher.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -Verify
#>
[CmdletBinding()]
param(
    [string]$UserName = 'AvacomExam',

    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath,

    [System.Security.SecureString]$Password,

    [ValidateSet('RestartShell', 'RestartDevice', 'ShutdownDevice', 'DoNothing')]
    [string]$OnShellExit = 'RestartShell',

    [switch]$EnableFeature,

    [switch]$DryRun,

    [switch]$Force,

    [switch]$Verify
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$commonPath = Join-Path $PSScriptRoot 'Kiosk.Common.ps1'
if (-not (Test-Path -LiteralPath $commonPath)) {
    Write-Host "[ERROR] Falta Kiosk.Common.ps1 junto a este script ($commonPath). Copia ambos archivos juntos." -ForegroundColor Red
    exit 1
}
. $commonPath

$script:ShellExitActions = @{ RestartShell = 0; RestartDevice = 1; ShutdownDevice = 2; DoNothing = 3 }
$script:EnableFeatureCommand = 'Enable-WindowsOptionalFeature -Online -FeatureName Client-EmbeddedShellLauncher -All -NoRestart'

function Invoke-ShellLauncherVerify {
    param([Parameter(Mandatory = $true)][string]$Exe)

    $marker = Read-KioskMarker
    if ($null -ne $marker) {
        Write-KioskLog INFO ("Marcador presente (SOLO un indicio, no una comprobacion): modo={0}, usuario={1}, aplicado={2}." -f $marker.mode, $marker.user, $marker.appliedAtUtc)
    } else {
        Write-KioskLog INFO 'No hay marcador (kiosk-provisioned.marker). El marcador es solo un indicio; se consulta el estado real.'
    }

    $user = Get-KioskUser -Name $UserName
    if ($null -eq $user) {
        Write-KioskLog ERROR ("NO APROVISIONADO: la cuenta local '{0}' no existe." -f $UserName)
        return 1
    }
    $st = Get-KioskShellLauncherState -UserSid $user.SID.Value -ExecutablePath $Exe
    Write-KioskLog INFO $st.Detail
    if (-not $st.ClassAvailable) {
        Write-KioskLog ERROR 'NO APROVISIONADO: Shell Launcher no esta activado en este equipo.'
        return 1
    }
    if (-not $st.Queried) {
        Write-KioskLog WARN 'NO SE PUDO VERIFICAR: Shell Launcher esta presente pero no se puede leer sin privilegios de administrador. Ejecuta -Verify desde una consola elevada.'
        return 2
    }
    if (-not $st.Enabled) {
        Write-KioskLog ERROR 'NO APROVISIONADO: Shell Launcher esta instalado pero desactivado (IsEnabled = falso).'
        return 1
    }
    if (-not $st.UserMapped) {
        Write-KioskLog ERROR ("NO APROVISIONADO: la cuenta '{0}' no tiene un shell personalizado asignado." -f $UserName)
        return 1
    }
    if (-not $st.ExeMatch) {
        Write-KioskLog ERROR ("NO APROVISIONADO: la cuenta '{0}' tiene un shell distinto de '{1}'." -f $UserName, $Exe)
        return 1
    }
    Write-KioskLog OK ("APROVISIONADO: Shell Launcher activo y '{0}' lanza '{1}' como shell." -f $UserName, $Exe)
    return 0
}

function Invoke-ShellLauncherMain {
    $isVerify = [bool]$Verify
    $isDry = ([bool]$DryRun) -and (-not $isVerify)
    $isReal = (-not $isVerify) -and (-not $isDry)
    $modeText = 'REAL'
    if ($isVerify) { $modeText = 'VERIFICAR (solo lectura)' }
    elseif ($isDry) { $modeText = 'SIMULACION -DryRun (no se modifica nada)' }

    Initialize-KioskLog -ScriptName 'Install-ShellLauncher' -LogFileName 'kiosk-install.log' -ToFile $false
    if ($isReal) { Set-KioskBlockMode -Mode 'throw' } else { Set-KioskBlockMode -Mode 'collect' }

    Write-KioskLog STEP ('AVACOM LMS - kiosco de examen (Shell Launcher v2) - modo: ' + $modeText)
    if ($Verify -and $DryRun) { Write-KioskLog WARN '-Verify ya es de solo lectura; se ignora -DryRun.' }

    # 1. Entradas
    if (-not (Test-KioskUserName -Name $UserName)) {
        throw "Nombre de usuario no valido: '$UserName'. Usa 1 a 20 caracteres: letras, numeros, punto, guion o guion bajo."
    }
    $exe = Resolve-KioskPath -Path $ExecutablePath
    if ($exe -notmatch '\.exe$') { throw "ExecutablePath debe ser un archivo .exe: '$exe'" }
    $exitAction = [int]$script:ShellExitActions[$OnShellExit]

    # 2. Elevacion y registro
    if ($isReal) {
        if (-not (Test-KioskElevated)) {
            throw 'Este script debe ejecutarse como administrador (consola elevada) para aplicar cambios. Usa -DryRun o -Verify si solo quieres consultar.'
        }
        Initialize-KioskLog -ScriptName 'Install-ShellLauncher' -LogFileName 'kiosk-install.log' -ToFile $true
        Write-KioskLog INFO ('Registro en: ' + (Get-KioskLogFile))
    } elseif (-not (Test-KioskElevated)) {
        Write-KioskLog INFO 'Sin privilegios de administrador: modo de solo lectura; algunas consultas pueden ser parciales.'
    }

    # 3. Edicion de Windows
    $ed = Get-KioskEdition
    Write-KioskLog INFO ("Windows: {0} (EditionID={1}, compilacion {2})." -f $ed.Caption, $ed.EditionId, $ed.Build)
    $editionOk = Test-KioskEditionSupported -Mode ShellLauncher -EditionId $ed.EditionId
    if (-not $editionOk) {
        $msg = "La edicion '{0}' NO admite Shell Launcher (solo Enterprise, Education o IoT Enterprise; NO Pro). En Pro usa Install-Kiosk.ps1 (Assigned Access)." -f $ed.EditionId
        if ($isVerify) { Write-KioskLog WARN $msg } else { Add-KioskBlocker -Message $msg }
    }

    # 4. Verificacion: solo consulta y sale
    if ($isVerify) {
        $script:KioskExitCode = Invoke-ShellLauncherVerify -Exe $exe
        return
    }

    # 5. Ejecutable
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        Write-KioskLog INFO ("Ejecutable encontrado: {0}" -f $exe)
    } else {
        $msg = "No existe el ejecutable '$exe'. Instala la Student de Windows y pasa su ruta real."
        if ($isReal) { Add-KioskBlocker -Message $msg } else { Write-KioskLog WARN ($msg + ' (en -DryRun solo se avisa)') }
    }

    # 6. Caracteristica opcional Client-EmbeddedShellLauncher
    $featureState = Get-KioskShellLauncherFeatureState
    Write-KioskLog INFO ('Caracteristica Client-EmbeddedShellLauncher: ' + $featureState)
    $needEnable = $false
    switch ($featureState) {
        'Enabled' { }
        'Disabled' {
            $needEnable = $true
            if ($isReal -and $EnableFeature) {
                Write-KioskLog INFO 'Se activara la caracteristica (-EnableFeature).'
            } else {
                Add-KioskBlocker -Message ("La caracteristica Client-EmbeddedShellLauncher esta DESACTIVADA. Activala (como administrador, y reinicia si lo pide) con:`n    {0}`nO bien vuelve a ejecutar este script con -EnableFeature para que la active el." -f $script:EnableFeatureCommand)
            }
        }
        'EnablePending' { Add-KioskBlocker -Message 'La caracteristica esta pendiente de activar: reinicia el equipo y vuelve a ejecutar el script.' }
        default {
            if ($isReal) {
                Add-KioskBlocker -Message 'No se pudo consultar el estado de la caracteristica Client-EmbeddedShellLauncher (Get-WindowsOptionalFeature).'
            } else {
                Write-KioskLog WARN ('No se pudo consultar la caracteristica sin elevacion. Con administrador, el comando para activarla seria: ' + $script:EnableFeatureCommand)
            }
        }
    }

    # 7. Cuentas: usuario estandar + administrador de recuperacion
    $existingUser = Test-KioskAccountsPreflight -UserName $UserName
    $userSid = ''
    if ($null -ne $existingUser) { $userSid = $existingUser.SID.Value }

    # 8. Conflicto con Assigned Access para la misma cuenta
    if ($null -ne $existingUser) {
        $aa = Get-KioskAssignedAccessState -UserName $UserName -ExecutablePath $exe -UserSid $userSid
        if ($aa.HasConfig -eq $true -and $aa.UserMatch) {
            if ($Force) {
                Write-KioskLog WARN ("La cuenta '{0}' ya tiene Assigned Access; -Force: se continua (no mezcles ambos mecanismos en una cuenta)." -f $UserName)
            } else {
                Add-KioskBlocker -Message ("La cuenta '{0}' ya esta configurada con Assigned Access. No combines Assigned Access y Shell Launcher en la misma cuenta: ejecuta antes Remove-Kiosk.ps1 o usa -Force." -f $UserName)
            }
        }
    }

    # 9. Plan
    $sidText = $userSid
    if ([string]::IsNullOrEmpty($sidText)) { $sidText = '<SID del usuario, se conocera al crearlo>' }
    $configSha = Get-KioskSha256Hex -Text ('shell-launcher|{0}|{1}|{2}|default=explorer.exe|admins=explorer.exe' -f $sidText, $exe, $OnShellExit)
    $cmds = @(
        ('SetDefaultShell(''explorer.exe'', 0)                       # resto de cuentas: explorer, reiniciar shell'),
        ('SetCustomShell({0}, ''explorer.exe'', $null, $null, 0)   # Administradores: explorer' -f $script:KioskAdminsSid),
        ('SetCustomShell({0}, ''{1}'', $null, $null, {2})   # {3}: shell del kiosco, al cerrarse: {4}' -f $sidText, $exe, $exitAction, $UserName, $OnShellExit),
        ('SetEnabled($true)')
    )

    if ($isDry) {
        if ($needEnable) { Write-KioskLog DRYRUN ('Activaria la caracteristica con: ' + $script:EnableFeatureCommand + ' (solo con -EnableFeature)') }
        if ($null -eq $existingUser) {
            Write-KioskLog DRYRUN ("Crearia el usuario local ESTANDAR '{0}' (grupo Usuarios) pidiendo la contrasena con Read-Host -AsSecureString." -f $UserName)
        } else {
            Write-KioskLog DRYRUN ("Reutilizaria el usuario existente '{0}' (su contrasena no se toca)." -f $UserName)
        }
        Write-KioskLog DRYRUN ('Llamaria a {0}\{1} (RemoveCustomShell previo del usuario, si existia) y despues:' -f $script:KioskWeslNamespace, $script:KioskWeslClass)
        foreach ($c in $cmds) { Write-Host ('    ' + $c) }
        Write-KioskLog DRYRUN ('Escribiria el marcador {0} con:' -f (Get-KioskMarkerPath))
        Write-Host (Get-KioskMarkerJson -Mode 'shell-launcher' -UserName $UserName -ExecutablePath $exe -ConfigSha256 $configSha)
        Write-KioskLog DRYRUN ('Escribiria el registro en {0}.' -f (Join-Path $env:ProgramData 'AVACOM\logs\kiosk-install.log'))
        Write-KioskLog DRYRUN 'Despues habria que cerrar sesion / REINICIAR e iniciar sesion como ese usuario.'
        $n = Get-KioskBlockerCount
        if ($n -gt 0) {
            Write-KioskLog ERROR ('SIMULACION TERMINADA con {0} bloqueo(s): un run real se detendria. No se modifico nada.' -f $n)
            $script:KioskExitCode = 1
        } else {
            Write-KioskLog OK 'SIMULACION TERMINADA sin bloqueos. No se modifico nada.'
        }
        return
    }

    # 10. Confirmacion (solo modo real, sin -Force)
    if (-not $Force) {
        Write-Host ''
        Write-KioskLog WARN ("Se va a sustituir el shell de '{0}' por '{1}' y a fijar explorer.exe como shell predeterminado y de Administradores." -f $UserName, $exe)
        $answer = Read-Host -Prompt 'Escribe APLICAR (en mayusculas) para continuar'
        if ($answer -cne 'APLICAR') { throw 'Operacion cancelada: no se escribio APLICAR.' }
    }

    # 11. Activar la caracteristica si se pidio
    if ($needEnable) {
        $restart = Enable-KioskShellLauncherFeature
        Write-KioskLog OK 'Caracteristica Client-EmbeddedShellLauncher activada.'
        if ($restart) {
            Write-KioskLog WARN 'Windows pide REINICIAR para completar la activacion. Reinicia el equipo y vuelve a ejecutar este script.'
            $script:KioskExitCode = 1
            return
        }
    }
    $probe = Get-KioskShellLauncherState
    if (-not $probe.ClassAvailable) {
        throw 'La clase WMI WESL_UserSetting no esta disponible todavia. Reinicia el equipo y vuelve a ejecutar el script.'
    }

    # 12. Crear el usuario si falta
    if ($null -eq $existingUser) {
        $pw = $Password
        if ($null -eq $pw) { $pw = Read-KioskNewPassword -UserName $UserName }
        New-KioskLocalUser -UserName $UserName -Password $pw
        Write-KioskLog OK ("Usuario local estandar '{0}' creado (la contrasena no se registra)." -f $UserName)
        $existingUser = Get-KioskUser -Name $UserName
        $userSid = $existingUser.SID.Value
        $configSha = Get-KioskSha256Hex -Text ('shell-launcher|{0}|{1}|{2}|default=explorer.exe|admins=explorer.exe' -f $userSid, $exe, $OnShellExit)
    } elseif ($null -ne $Password) {
        Write-KioskLog WARN ("La cuenta '{0}' ya existe: se ignora -Password y no se cambia su contrasena." -f $UserName)
    }

    # 13. Aplicar
    Invoke-KioskShellLauncherApply -UserSid $userSid -ExecutablePath $exe -ExitAction $exitAction
    Write-KioskLog OK ("Shell Launcher configurado: '{0}' ({1}) arranca '{2}'; al cerrarse: {3}." -f $UserName, $userSid, $exe, $OnShellExit)

    # 14. Comprobar y dejar el marcador
    $st = Get-KioskShellLauncherState -UserSid $userSid -ExecutablePath $exe
    if ($st.ClassAvailable -and $st.Queried -and $st.Enabled -and $st.UserMapped -and $st.ExeMatch) {
        Write-KioskLog OK 'Comprobacion posterior: Shell Launcher activo y asignado al usuario.'
    } else {
        Write-KioskLog WARN ('Comprobacion posterior no concluyente: ' + $st.Detail + ' Tras reiniciar, ejecuta este script con -Verify.')
    }
    Write-KioskMarker -Mode 'shell-launcher' -UserName $UserName -ExecutablePath $exe -ConfigSha256 $configSha
    Write-KioskLog OK ('Marcador escrito: ' + (Get-KioskMarkerPath) + ' (recuerda: es solo un indicio).')

    Write-Host ''
    Write-KioskLog STEP 'SIGUIENTE PASO: REINICIA el equipo e inicia sesion como el usuario del kiosco.'
    Write-KioskLog INFO ("  Usuario: {0}. En lugar del escritorio arrancara: {1}" -f $UserName, $exe)
    Write-KioskLog INFO '  Despues, desde una consola de administrador: .\Install-ShellLauncher.ps1 -ExecutablePath <ruta> -Verify'
    Write-KioskLog INFO '  Para deshacer: .\Remove-Kiosk.ps1 -DisableShellLauncher (conserva la cuenta y sus datos).'
    Write-KioskLog INFO '  Ctrl+Alt+Supr NO queda cerrado solo por Shell Launcher (sin probar); el apagado fisico tampoco.'
}

function Invoke-ShellLauncherInstall {
    try {
        Invoke-ShellLauncherMain
    } catch {
        Write-KioskLog ERROR $_.Exception.Message
        $script:KioskExitCode = 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $null = Invoke-ShellLauncherInstall
    exit $script:KioskExitCode
}
