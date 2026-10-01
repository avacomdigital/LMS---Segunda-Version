<#
.SYNOPSIS
    Revierte el bloqueo de examen de Windows (Assigned Access y, opcionalmente, Shell Launcher).

.DESCRIPTION
    Deshace lo que hicieron Install-Kiosk.ps1 e Install-ShellLauncher.ps1:

      * Assigned Access: borra la configuración de MDM_AssignedAccess
        (root\cimv2\mdm\dmmap, propiedad Configuration = vacía). Esa clase guarda UNA sola
        configuración por equipo, así que se borra para todas las cuentas; si la configuración
        actual incluye a OTRAS cuentas, el script se detiene salvo que uses -Force. Como
        refuerzo, si el sistema conserva la configuración, usa Clear-AssignedAccess.
        Igual que al instalar, si Windows responde «Acceso denegado» se reintenta como SYSTEM
        con una tarea programada de un solo uso.
      * Con -DisableShellLauncher: quita la asignación de shell de la cuenta (WESL_UserSetting) y,
        si no queda ninguna otra asignación, también la de Administradores y desactiva Shell
        Launcher. Con -DisableFeature además desactiva la característica opcional
        Client-EmbeddedShellLauncher (requiere reinicio; solo si nadie más usa Shell Launcher).
      * Borra el marcador %ProgramData%\AVACOM\kiosk-provisioned.marker si corresponde al
        mecanismo revertido (si el marcador es de Shell Launcher y no pasas
        -DisableShellLauncher, se conserva porque sigue siendo cierto).

    NO borra la cuenta local ni sus datos: se conservan siempre.

    Modo real: exige consola elevada y escribe %ProgramData%\AVACOM\logs\kiosk-remove.log.
    -DryRun funciona SIN elevación, es estrictamente de solo lectura y solo escribe en la consola.

    Códigos de salida: 0 = correcto; 1 = error o bloqueo.

.PARAMETER UserName
    Cuenta local del kiosco (predeterminado AvacomExam). Se conserva.

.PARAMETER DisableShellLauncher
    También revierte la configuración de Shell Launcher de esa cuenta.

.PARAMETER DisableFeature
    Con -DisableShellLauncher: desactiva además la característica Client-EmbeddedShellLauncher.

.PARAMETER DryRun
    Simulación: muestra lo que haría sin modificar nada (funciona sin elevación).

.PARAMETER Force
    No pide la confirmación interactiva y permite borrar una configuración de Assigned Access
    que incluye a otras cuentas.

.EXAMPLE
    .\Remove-Kiosk.ps1 -DryRun

.EXAMPLE
    .\Remove-Kiosk.ps1

.EXAMPLE
    .\Remove-Kiosk.ps1 -DisableShellLauncher -DisableFeature
#>
[CmdletBinding()]
param(
    [string]$UserName = 'AvacomExam',

    [switch]$DisableShellLauncher,

    [switch]$DisableFeature,

    [switch]$DryRun,

    [switch]$Force
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$commonPath = Join-Path $PSScriptRoot 'Kiosk.Common.ps1'
if (-not (Test-Path -LiteralPath $commonPath)) {
    Write-Host "[ERROR] Falta Kiosk.Common.ps1 junto a este script ($commonPath). Copia ambos archivos juntos." -ForegroundColor Red
    exit 1
}
. $commonPath

function Invoke-RemoveKioskMain {
    $isDry = [bool]$DryRun
    $isReal = -not $isDry
    $modeText = 'REAL'
    if ($isDry) { $modeText = 'SIMULACION -DryRun (no se modifica nada)' }

    Initialize-KioskLog -ScriptName 'Remove-Kiosk' -LogFileName 'kiosk-remove.log' -ToFile $false
    if ($isReal) { Set-KioskBlockMode -Mode 'throw' } else { Set-KioskBlockMode -Mode 'collect' }

    Write-KioskLog STEP ('AVACOM LMS - revertir kiosco de examen - modo: ' + $modeText)

    # 1. Entradas
    if (-not (Test-KioskUserName -Name $UserName)) {
        throw "Nombre de usuario no valido: '$UserName'."
    }
    if ($DisableFeature -and -not $DisableShellLauncher) {
        throw '-DisableFeature solo tiene sentido junto con -DisableShellLauncher.'
    }

    # 2. Elevacion y registro
    if ($isReal) {
        if (-not (Test-KioskElevated)) {
            throw 'Este script debe ejecutarse como administrador (consola elevada) para revertir cambios. Usa -DryRun si solo quieres ver el plan.'
        }
        Initialize-KioskLog -ScriptName 'Remove-Kiosk' -LogFileName 'kiosk-remove.log' -ToFile $true
        Write-KioskLog INFO ('Registro en: ' + (Get-KioskLogFile))
    } elseif (-not (Test-KioskElevated)) {
        Write-KioskLog INFO 'Sin privilegios de administrador: modo de solo lectura; algunas consultas pueden ser parciales.'
    }

    # 3. Marcador (indicio)
    $marker = Read-KioskMarker
    $markerMode = ''
    if ($null -ne $marker) {
        $markerMode = [string]$marker.mode
        Write-KioskLog INFO ("Marcador presente (solo un indicio): modo={0}, usuario={1}, aplicado={2}." -f $marker.mode, $marker.user, $marker.appliedAtUtc)
    } else {
        Write-KioskLog INFO 'No hay marcador (kiosk-provisioned.marker).'
    }

    # 4. Assigned Access: estado actual
    $aaHas = $null
    $aaOthers = $null     # $null = no se pudo saber que cuentas incluye
    $mdm = Get-KioskMdmConfiguration
    if ($mdm.Status -eq 'Ok') {
        if ([string]::IsNullOrWhiteSpace($mdm.Configuration)) {
            $aaHas = $false
            Write-KioskLog INFO 'Assigned Access (MDM): sin configuracion.'
        } else {
            $aaHas = $true
            $sum = Get-KioskAssignedAccessSummary -ConfigText $mdm.Configuration
            $aaOthers = @($sum.Accounts | Where-Object { ($_ -ine $UserName) -and ($_ -notlike ('*\' + $UserName)) })
            Write-KioskLog INFO ('Assigned Access (MDM): configuracion presente; cuentas: ' + (($sum.Accounts) -join ', '))
        }
    } else {
        $reg = Get-KioskAssignedAccessRegistry
        if ($reg.Empty) {
            $aaHas = $false
            Write-KioskLog INFO 'Assigned Access: no se pudo leer MDM, pero el almacen del sistema en el registro esta vacio (sin configuracion).'
        } else {
            $aaHas = $true
            Write-KioskLog WARN ('Assigned Access: hay datos en el registro del sistema y MDM no se pudo leer ({0}: {1}). No se sabe que cuentas incluye.' -f $mdm.Status, $mdm.Message)
        }
    }
    if ($aaHas -eq $true -and $null -ne $aaOthers -and $aaOthers.Count -gt 0) {
        if ($Force) {
            Write-KioskLog WARN ('La configuracion incluye otras cuentas ({0}); -Force: se borrara tambien para ellas.' -f ($aaOthers -join ', '))
        } else {
            Add-KioskBlocker -Message ('La configuracion de Assigned Access incluye otras cuentas ({0}) y borrarla las afectaria. Usa -Force si es lo que quieres.' -f ($aaOthers -join ', '))
        }
    }

    # 5. Shell Launcher (solo con -DisableShellLauncher): estado actual
    $slDo = $false
    $user = Get-KioskUser -Name $UserName
    if ($DisableShellLauncher) {
        if ($null -eq $user) {
            Write-KioskLog WARN ("La cuenta '{0}' no existe: no se puede determinar su SID; se omite Shell Launcher." -f $UserName)
        } else {
            $sl = Get-KioskShellLauncherState -UserSid $user.SID.Value
            if (-not $sl.ClassAvailable) {
                Write-KioskLog INFO 'Shell Launcher: la caracteristica no esta activa; nada que revertir.'
            } elseif (-not $sl.Queried) {
                if ($isReal) { Add-KioskBlocker -Message ('No se pudo leer Shell Launcher: ' + $sl.Detail) }
                else { Write-KioskLog WARN ('Shell Launcher: ' + $sl.Detail + ' (se necesitan privilegios de administrador).') }
            } else {
                $slDo = $true
                Write-KioskLog INFO ("Shell Launcher: activo={0}; la cuenta '{1}' tiene asignacion={2}." -f $sl.Enabled, $UserName, $sl.UserMapped)
            }
        }
    }

    # 6. Plan
    $doAa = ($aaHas -ne $false)
    if ($isDry) {
        if ($doAa) {
            Write-KioskLog DRYRUN ('Pondria {0}\{1}.Configuration = '''' (borra la configuracion de Assigned Access): primero directo y, si da Acceso denegado, como SYSTEM con una tarea programada temporal.' -f $script:KioskMdmNamespace, $script:KioskMdmClass)
            Write-KioskLog DRYRUN 'Si el sistema conservara la configuracion, ejecutaria Clear-AssignedAccess.'
        } else {
            Write-KioskLog DRYRUN 'Assigned Access: nada que revertir.'
        }
        if ($slDo) {
            Write-KioskLog DRYRUN ('Llamaria a {0}\{1}: RemoveCustomShell(<SID de {2}>); si no quedan otras asignaciones, RemoveCustomShell(Administradores) y SetEnabled($false).' -f $script:KioskWeslNamespace, $script:KioskWeslClass, $UserName)
            if ($DisableFeature) { Write-KioskLog DRYRUN 'Despues, si nadie mas usa Shell Launcher: Disable-WindowsOptionalFeature -Online -FeatureName Client-EmbeddedShellLauncher -NoRestart (requiere reinicio).' }
        }
        if ($null -ne $marker) {
            Write-KioskLog DRYRUN ('Borraria el marcador {0} si corresponde al mecanismo revertido (modo actual: {1}).' -f (Get-KioskMarkerPath), $markerMode)
        }
        Write-KioskLog DRYRUN ("Conservaria la cuenta '{0}' y todos sus datos." -f $UserName)
        Write-KioskLog DRYRUN ('Escribiria el registro en {0}.' -f (Join-Path $env:ProgramData 'AVACOM\logs\kiosk-remove.log'))
        $n = Get-KioskBlockerCount
        if ($n -gt 0) {
            Write-KioskLog ERROR ('SIMULACION TERMINADA con {0} bloqueo(s): un run real se detendria. No se modifico nada.' -f $n)
            $script:KioskExitCode = 1
        } else {
            Write-KioskLog OK 'SIMULACION TERMINADA sin bloqueos. No se modifico nada.'
        }
        return
    }

    # 7. Confirmacion
    if (-not $Force) {
        Write-Host ''
        Write-KioskLog WARN ("Se va a quitar el bloqueo de examen. La cuenta '{0}' y sus datos se conservan." -f $UserName)
        $answer = Read-Host -Prompt 'Escribe REVERTIR (en mayusculas) para continuar'
        if ($answer -cne 'REVERTIR') { throw 'Operacion cancelada: no se escribio REVERTIR.' }
    }

    # 8. Revertir Assigned Access
    $aaReverted = $true
    if ($doAa) {
        $how = Invoke-AssignedAccessApply -Xml ''
        Write-KioskLog OK ('Configuracion de Assigned Access borrada: ' + $how)
        $reg2 = Get-KioskAssignedAccessRegistry
        if (-not $reg2.Empty) {
            if (Get-Command -Name Clear-AssignedAccess -ErrorAction SilentlyContinue) {
                Write-KioskLog WARN 'El almacen del sistema aun conserva datos de Assigned Access; se ejecuta Clear-AssignedAccess.'
                Clear-AssignedAccess
                $reg2 = Get-KioskAssignedAccessRegistry
            }
            if (-not $reg2.Empty) {
                Write-KioskLog WARN 'El almacen del sistema (registro) aun conserva datos de Assigned Access. Reinicia y revisa con Install-Kiosk.ps1 -Verify.'
                $aaReverted = $false
            }
        }
    } else {
        Write-KioskLog INFO 'Assigned Access: nada que revertir.'
    }

    # 9. Revertir Shell Launcher
    $slReverted = $false
    if ($slDo) {
        $userSid = $user.SID.Value
        foreach ($m in @(Invoke-KioskShellLauncherRemove -UserSid $userSid)) { Write-KioskLog OK $m }
        $slReverted = $true
        if ($DisableFeature) {
            $others = @(Get-CimInstance -Namespace $script:KioskWeslNamespace -ClassName $script:KioskWeslClass -ErrorAction Stop |
                    Where-Object { [string]$_.Sid -ine $script:KioskAdminsSid })
            if ($others.Count -gt 0) {
                Write-KioskLog WARN 'Otras cuentas siguen usando Shell Launcher: no se desactiva la caracteristica.'
            } else {
                $restart = Disable-KioskShellLauncherFeature
                Write-KioskLog OK 'Caracteristica Client-EmbeddedShellLauncher desactivada.'
                if ($restart) { Write-KioskLog WARN 'Windows pide REINICIAR para completar la desactivacion.' }
            }
        }
    }

    # 10. Marcador
    if ($null -ne $marker) {
        $remove = $false
        if ($markerMode -eq 'assigned-access') { $remove = $aaReverted }
        elseif ($markerMode -eq 'shell-launcher') { $remove = $slReverted }
        else { $remove = $aaReverted }
        if ($remove) {
            Remove-KioskMarker
            Write-KioskLog OK ('Marcador borrado: ' + (Get-KioskMarkerPath))
        } else {
            Write-KioskLog WARN ("El marcador (modo '{0}') se conserva porque ese mecanismo no se ha revertido en esta ejecucion." -f $markerMode)
        }
    }

    Write-Host ''
    Write-KioskLog OK ("Cuenta '{0}' y sus datos CONSERVADOS (no se borra nada del usuario)." -f $UserName)
    Write-KioskLog STEP 'SIGUIENTE PASO: cierra la sesion del usuario del kiosco o REINICIA el equipo para que el cambio surta efecto.'
    Write-KioskLog INFO 'Para comprobarlo: .\Install-Kiosk.ps1 -ExecutablePath <ruta> -Verify  (debe decir NO APROVISIONADO).'
}

function Invoke-RemoveKiosk {
    try {
        Invoke-RemoveKioskMain
    } catch {
        Write-KioskLog ERROR $_.Exception.Message
        $script:KioskExitCode = 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $null = Invoke-RemoveKiosk
    exit $script:KioskExitCode
}
