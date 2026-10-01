<#
.SYNOPSIS
    Bloquea un equipo Windows para el examen de AVACOM LMS con Assigned Access (multiaplicación).

.DESCRIPTION
    Capa «sistema» del bloqueo de examen en Windows (kiosk.md §4.5): crea (si falta) un usuario
    local ESTÁNDAR y le asigna, mediante Assigned Access en su forma MULTIAPLICACIÓN, una única
    aplicación de escritorio permitida (DesktopAppPath) que se lanza sola al iniciar sesión.

    Se usa la forma multiaplicación porque la Student de Windows es un ejecutable de escritorio
    NO empaquetado (WindowsPackageType None, no es MSIX y no tiene AUMID); la forma de una sola
    app «Set-AssignedAccess -AppUserModelId» no sirve para ese caso.

    La configuración se aplica por el puente MDM de WMI:
        espacio de nombres  root\cimv2\mdm\dmmap
        clase               MDM_AssignedAccess
        propiedad           Configuration (cadena con el XML escapado)
    Ese puente suele exigir la cuenta SYSTEM: el script lo intenta como administrador y, si
    Windows responde «Acceso denegado», reintenta como SYSTEM mediante una tarea programada de
    un solo uso (carpeta de trabajo protegida, se borra al terminar).

    ATENCIÓN: MDM_AssignedAccess tiene UNA sola configuración por equipo. Aplicarla REEMPLAZA
    la que hubiera para otras cuentas. Si ya existe una que no incluye a este usuario, el script
    se detiene salvo que uses -Force.

    Protecciones (siempre):
      * Modo real: exige consola elevada. -DryRun y -Verify funcionan SIN elevación y son
        estrictamente de solo lectura (no crean usuarios, ni escriben registro/WMI, ni archivos).
      * Comprueba que la edición de Windows admite Assigned Access (Pro/Enterprise/Education/IoT).
      * Exige que exista OTRA cuenta administradora local habilitada (recuperación) y aborta si
        el usuario del kiosco es administrador o es el único administrador.
      * La contraseña del usuario nuevo se pide con Read-Host -AsSecureString (o llega por
        -Password como SecureString). Nunca se escribe en pantalla, en el registro ni en disco.

    Marcador: tras aplicar, escribe %ProgramData%\AVACOM\kiosk-provisioned.marker (JSON con
    mode, user, executablePath, appliedAtUtc, configSha256). La Student solo comprueba que el
    archivo exista: es un INDICIO, no una prueba (kiosk.md §5.1). Para saber el estado REAL usa
    -Verify, que consulta el sistema y no el marcador.

    Registro: %ProgramData%\AVACOM\logs\kiosk-install.log (solo en modo real; en -DryRun y
    -Verify todo va únicamente a la consola).

    Códigos de salida: 0 = correcto / aprovisionado; 1 = error, bloqueo o NO aprovisionado;
    2 = (solo -Verify) no se pudo comprobar el estado real sin privilegios de administrador.

.PARAMETER UserName
    Cuenta local del kiosco. Predeterminado: AvacomExam. Se crea como usuario estándar si falta.

.PARAMETER ExecutablePath
    Ruta absoluta del ejecutable de la Student de Windows (OBLIGATORIO). Debe existir en modo
    real. Ejemplo: C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe

.PARAMETER AdditionalAllowedPaths
    Otros ejecutables que la cuenta podrá lanzar además de la Student (por ejemplo, el proceso
    de WebView2 si Windows bloquea la vista web). Rutas absolutas. Opcional.

.PARAMETER Password
    Contraseña de la cuenta NUEVA, como SecureString. Si falta y la cuenta no existe, se pide
    con Read-Host -AsSecureString. Se ignora si la cuenta ya existe.

.PARAMETER DryRun
    Simulación: muestra todo lo que haría (incluido el XML de Assigned Access) sin modificar
    nada. Funciona sin elevación.

.PARAMETER Force
    No pide la confirmación interactiva y permite REEMPLAZAR una configuración de Assigned
    Access ajena. No omite ninguna otra protección (elevación, administrador de recuperación…).

.PARAMETER Verify
    Solo lectura: consulta el estado REAL (MDM_AssignedAccess; si no hay permisos, el almacén
    del sistema en el registro) y sale con 0/1/2. No usa el marcador como prueba.

.EXAMPLE
    .\Install-Kiosk.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -DryRun
    Muestra el plan y el XML sin tocar el equipo (no requiere administrador).

.EXAMPLE
    .\Install-Kiosk.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe'
    Aplicación real (consola de administrador). Pide confirmación y la contraseña si el usuario es nuevo.

.EXAMPLE
    .\Install-Kiosk.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -Verify
    Comprueba el estado real tras reiniciar. Código de salida 0 solo si está aprovisionado.
#>
[CmdletBinding()]
param(
    [string]$UserName = 'AvacomExam',

    [Parameter(Mandatory = $true)]
    [string]$ExecutablePath,

    [string[]]$AdditionalAllowedPaths = @(),

    [System.Security.SecureString]$Password,

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

function Invoke-InstallKioskVerify {
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
    if (Test-KioskUserIsAdmin -Name $UserName) {
        Write-KioskLog WARN ("La cuenta '{0}' es ADMINISTRADORA: Assigned Access debe aplicarse a un usuario estandar." -f $UserName)
    }

    $state = Get-KioskAssignedAccessState -UserName $UserName -ExecutablePath $Exe -UserSid $user.SID.Value
    Write-KioskLog INFO $state.Detail

    if ($state.HasConfig -eq $false) {
        Write-KioskLog ERROR 'NO APROVISIONADO: el equipo no tiene ninguna configuracion de Assigned Access.'
        return 1
    }
    if ($state.UserMatch -and $state.ExeMatch) {
        if ($state.Source -eq 'mdm') {
            Write-KioskLog OK ("APROVISIONADO: Assigned Access incluye a '{0}' y permite '{1}'." -f $UserName, $Exe)
        } else {
            Write-KioskLog OK ("APROVISIONADO (heuristica por el registro): se encontro '{0}' y '{1}'. Vuelve a ejecutar -Verify como administrador para confirmarlo con MDM." -f $UserName, $Exe)
        }
        return 0
    }
    if ($state.Source -eq 'mdm') {
        $faltan = @()
        if (-not $state.UserMatch) { $faltan += "la cuenta '$UserName'" }
        if (-not $state.ExeMatch) { $faltan += "el ejecutable '$Exe'" }
        Write-KioskLog ERROR ('NO APROVISIONADO: hay una configuracion de Assigned Access, pero no incluye ' + ($faltan -join ' ni ') + '.')
        return 1
    }
    Write-KioskLog WARN 'NO SE PUDO VERIFICAR: existe una configuracion de Assigned Access pero su contenido no se puede leer sin privilegios de administrador. Ejecuta -Verify desde una consola elevada.'
    return 2
}

function Invoke-InstallKioskMain {
    $isVerify = [bool]$Verify
    $isDry = ([bool]$DryRun) -and (-not $isVerify)
    $isReal = (-not $isVerify) -and (-not $isDry)
    $modeText = 'REAL'
    if ($isVerify) { $modeText = 'VERIFICAR (solo lectura)' }
    elseif ($isDry) { $modeText = 'SIMULACION -DryRun (no se modifica nada)' }

    Initialize-KioskLog -ScriptName 'Install-Kiosk' -LogFileName 'kiosk-install.log' -ToFile $false
    if ($isReal) { Set-KioskBlockMode -Mode 'throw' } else { Set-KioskBlockMode -Mode 'collect' }

    Write-KioskLog STEP ('AVACOM LMS - kiosco de examen (Assigned Access multiaplicacion) - modo: ' + $modeText)
    if ($Verify -and $DryRun) { Write-KioskLog WARN '-Verify ya es de solo lectura; se ignora -DryRun.' }

    # 1. Entradas
    if (-not (Test-KioskUserName -Name $UserName)) {
        throw "Nombre de usuario no valido: '$UserName'. Usa 1 a 20 caracteres: letras, numeros, punto, guion o guion bajo."
    }
    $exe = Resolve-KioskPath -Path $ExecutablePath
    if ($exe -notmatch '\.exe$') { throw "ExecutablePath debe ser un archivo .exe: '$exe'" }
    $extra = @()
    foreach ($p in $AdditionalAllowedPaths) {
        if (-not [string]::IsNullOrWhiteSpace($p)) { $extra += (Resolve-KioskPath -Path $p) }
    }

    # 2. Elevacion y registro
    if ($isReal) {
        if (-not (Test-KioskElevated)) {
            throw 'Este script debe ejecutarse como administrador (consola elevada) para aplicar cambios. Usa -DryRun o -Verify si solo quieres consultar.'
        }
        Initialize-KioskLog -ScriptName 'Install-Kiosk' -LogFileName 'kiosk-install.log' -ToFile $true
        Write-KioskLog INFO ('Registro en: ' + (Get-KioskLogFile))
    } elseif (-not (Test-KioskElevated)) {
        Write-KioskLog INFO 'Sin privilegios de administrador: modo de solo lectura; algunas consultas pueden ser parciales.'
    }

    # 3. Edicion de Windows
    $ed = Get-KioskEdition
    Write-KioskLog INFO ("Windows: {0} (EditionID={1}, compilacion {2})." -f $ed.Caption, $ed.EditionId, $ed.Build)
    $editionOk = Test-KioskEditionSupported -Mode AssignedAccess -EditionId $ed.EditionId
    if (-not $editionOk) {
        $msg = "La edicion '{0}' NO admite Assigned Access (requiere Pro, Enterprise, Education o IoT Enterprise). En Home no hay kiosco de sistema: queda solo la capa de la aplicacion." -f $ed.EditionId
        if ($isVerify) { Write-KioskLog WARN $msg } else { Add-KioskBlocker -Message $msg }
    }

    # 4. Verificacion: solo consulta y sale
    if ($isVerify) {
        $script:KioskExitCode = Invoke-InstallKioskVerify -Exe $exe
        return
    }

    # 5. Ejecutable
    if (Test-Path -LiteralPath $exe -PathType Leaf) {
        Write-KioskLog INFO ("Ejecutable encontrado: {0}" -f $exe)
    } else {
        $msg = "No existe el ejecutable '$exe'. Instala la Student de Windows y pasa su ruta real."
        if ($isReal) { Add-KioskBlocker -Message $msg } else { Write-KioskLog WARN ($msg + ' (en -DryRun solo se avisa)') }
    }
    foreach ($p in $extra) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { Write-KioskLog WARN ("La ruta adicional permitida no existe ahora: $p") }
    }

    # 6. Cuentas: usuario estandar + administrador de recuperacion
    $existingUser = Test-KioskAccountsPreflight -UserName $UserName
    $userSid = ''
    if ($null -ne $existingUser) { $userSid = $existingUser.SID.Value }

    # 7. Configuracion de Assigned Access ya presente
    $state = Get-KioskAssignedAccessState -UserName $UserName -ExecutablePath $exe -UserSid $userSid
    Write-KioskLog INFO ('Estado actual de Assigned Access: ' + $state.Detail)
    if ($state.HasConfig -eq $true) {
        if ($state.UserMatch) {
            Write-KioskLog INFO ("Ya hay una configuracion que incluye a '{0}'. Se reemplazara por la nueva (idempotente)." -f $UserName)
        } elseif ($Force) {
            Write-KioskLog WARN 'Hay una configuracion de Assigned Access que NO incluye a este usuario; -Force: se REEMPLAZARA y se perdera.'
        } else {
            Add-KioskBlocker -Message ("Ya existe una configuracion de Assigned Access que no incluye a '{0}'. Aplicar esta la REEMPLAZARIA (hay una sola por equipo). Revisala o usa -Force." -f $UserName)
        }
    }

    # 8. Construir y validar el XML
    $xml = New-KioskAssignedAccessXml -UserName $UserName -ExecutablePath $exe -AdditionalAllowedPaths $extra
    try {
        $doc = [xml]$xml
    } catch {
        throw ('La configuracion generada no es XML valido: ' + $_.Exception.Message)
    }
    $check = Test-KioskAssignedAccessText -ConfigText $xml -UserName $UserName -ExecutablePath $exe
    if (-not ($check.UserMatch -and $check.ExeMatch)) {
        throw 'Error interno: el XML generado no contiene la cuenta o el ejecutable esperados.'
    }
    $configSha = Get-KioskSha256Hex -Text $xml
    Write-KioskLog INFO ('XML de Assigned Access valido (SHA-256 {0}).' -f $configSha)

    # 9. Simulacion: mostrar el plan
    if ($isDry) {
        Write-KioskLog DRYRUN '--- Configuracion de Assigned Access que se aplicaria (XML, antes de escaparlo) ---'
        Write-Host $xml
        Write-KioskLog DRYRUN '--- fin del XML ---'
        if ($null -eq $existingUser) {
            Write-KioskLog DRYRUN ("Crearia el usuario local ESTANDAR '{0}' (grupo Usuarios, contrasena sin caducidad) pidiendo la contrasena con Read-Host -AsSecureString." -f $UserName)
        } else {
            Write-KioskLog DRYRUN ("Reutilizaria el usuario existente '{0}' (su contrasena no se toca)." -f $UserName)
        }
        Write-KioskLog DRYRUN ('Aplicaria el XML escapado (HtmlEncode, {0} caracteres) en {1}\{2}.Configuration: primero directo y, si da Acceso denegado, como SYSTEM con una tarea programada temporal.' -f ([System.Net.WebUtility]::HtmlEncode($xml)).Length, $script:KioskMdmNamespace, $script:KioskMdmClass)
        Write-KioskLog DRYRUN ('Escribiria el marcador {0} con:' -f (Get-KioskMarkerPath))
        Write-Host (Get-KioskMarkerJson -Mode 'assigned-access' -UserName $UserName -ExecutablePath $exe -ConfigSha256 $configSha)
        Write-KioskLog DRYRUN ('Escribiria el registro en {0}.' -f (Join-Path $env:ProgramData 'AVACOM\logs\kiosk-install.log'))
        Write-KioskLog DRYRUN 'Despues habria que REINICIAR e iniciar sesion como ese usuario.'
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
        Write-KioskLog WARN ("Se va a configurar Assigned Access para '{0}' con la unica app '{1}'." -f $UserName, $exe)
        Write-KioskLog WARN 'Esto REEMPLAZA la configuracion global de Assigned Access del equipo. Cuenta de recuperacion comprobada.'
        $answer = Read-Host -Prompt 'Escribe APLICAR (en mayusculas) para continuar'
        if ($answer -cne 'APLICAR') { throw 'Operacion cancelada: no se escribio APLICAR.' }
    }

    # 11. Crear el usuario si falta
    if ($null -eq $existingUser) {
        $pw = $Password
        if ($null -eq $pw) { $pw = Read-KioskNewPassword -UserName $UserName }
        New-KioskLocalUser -UserName $UserName -Password $pw
        Write-KioskLog OK ("Usuario local estandar '{0}' creado (la contrasena no se registra)." -f $UserName)
    } elseif ($null -ne $Password) {
        Write-KioskLog WARN ("La cuenta '{0}' ya existe: se ignora -Password y no se cambia su contrasena." -f $UserName)
    }

    # 12. Aplicar
    $how = Invoke-AssignedAccessApply -Xml $xml
    Write-KioskLog OK ('Configuracion de Assigned Access aplicada: ' + $how)

    # 13. Comprobar lo aplicado (lo que se pueda leer) y dejar el marcador
    $after = Get-KioskUser -Name $UserName
    $afterSid = ''
    if ($null -ne $after) { $afterSid = $after.SID.Value }
    $st = Get-KioskAssignedAccessState -UserName $UserName -ExecutablePath $exe -UserSid $afterSid
    if ($st.HasConfig -eq $true -and $st.UserMatch -and $st.ExeMatch) {
        Write-KioskLog OK ('Comprobacion posterior: el sistema ya contiene la configuracion (' + $st.Source + ').')
    } else {
        Write-KioskLog WARN ('Comprobacion posterior no concluyente: ' + $st.Detail + ' Tras reiniciar, ejecuta este script con -Verify.')
    }
    Write-KioskMarker -Mode 'assigned-access' -UserName $UserName -ExecutablePath $exe -ConfigSha256 $configSha
    Write-KioskLog OK ('Marcador escrito: ' + (Get-KioskMarkerPath) + ' (recuerda: es solo un indicio).')

    Write-Host ''
    Write-KioskLog STEP 'SIGUIENTE PASO: REINICIA el equipo e inicia sesion como el usuario del kiosco.'
    Write-KioskLog INFO ("  Usuario: {0}. Al entrar se abrira solo: {1}" -f $UserName, $exe)
    Write-KioskLog INFO '  Despues, desde una consola de administrador: .\Install-Kiosk.ps1 -ExecutablePath <ruta> -Verify'
    Write-KioskLog INFO '  Para deshacer: .\Remove-Kiosk.ps1 (conserva la cuenta y sus datos).'
    Write-KioskLog INFO '  Ctrl+Alt+Supr y el apagado fisico siguen fuera del alcance de cualquier aplicacion.'
}

function Invoke-InstallKiosk {
    try {
        Invoke-InstallKioskMain
    } catch {
        Write-KioskLog ERROR $_.Exception.Message
        $script:KioskExitCode = 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $null = Invoke-InstallKiosk
    exit $script:KioskExitCode
}
