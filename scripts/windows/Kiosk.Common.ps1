<#
.SYNOPSIS
    Funciones compartidas de los scripts de bloqueo de examen en Windows (AVACOM LMS).

.DESCRIPTION
    No se ejecuta solo: lo cargan por "dot-sourcing" Install-Kiosk.ps1,
    Install-ShellLauncher.ps1 y Remove-Kiosk.ps1 (deben estar en la misma carpeta).
    Si copias un script a otro equipo, copia también este archivo.

    Reglas que todas las funciones respetan:
      * Las funciones de CONSULTA (Get-*, Test-*, Read-*) son de solo lectura.
      * Las unicas funciones que modifican el equipo son New-KioskLocalUser,
        Invoke-AssignedAccessApply, Invoke-KioskShellLauncherApply,
        Invoke-KioskShellLauncherRemove, Enable-/Disable-KioskShellLauncherFeature,
        Write-KioskMarker, Remove-KioskMarker e Initialize-KioskLog (con -ToFile $true).
        Los scripts principales solo las llaman en modo real, nunca con -DryRun ni -Verify.
      * Nunca se escribe, imprime ni registra una contraseña.
#>

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
$script:KioskAdminsSid      = 'S-1-5-32-544'   # BUILTIN\Administrators (independiente del idioma)
$script:KioskUsersSid       = 'S-1-5-32-545'   # BUILTIN\Users
$script:KioskMdmNamespace   = 'root\cimv2\mdm\dmmap'
$script:KioskMdmClass       = 'MDM_AssignedAccess'
$script:KioskWeslNamespace  = 'root\standardcimv2\embedded'
$script:KioskWeslClass      = 'WESL_UserSetting'
$script:KioskShellFeature   = 'Client-EmbeddedShellLauncher'
$script:KioskAaRegistryRoot = 'HKLM:\SOFTWARE\Microsoft\Windows\AssignedAccessConfiguration'

$script:KioskLogFile        = $null
$script:KioskScriptName     = 'kiosk'
$script:KioskExitCode       = 0
$script:KioskBlockMode      = 'throw'
$script:KioskBlockers       = New-Object System.Collections.Generic.List[string]

# ---------------------------------------------------------------------------
# Registro (consola siempre; archivo solo en modo real)
# ---------------------------------------------------------------------------
function Initialize-KioskLog {
    <# Prepara el registro. Con -ToFile $true crea %ProgramData%\AVACOM\logs (SOLO modo real). #>
    param(
        [Parameter(Mandatory = $true)][string]$ScriptName,
        [Parameter(Mandatory = $true)][string]$LogFileName,
        [Parameter(Mandatory = $true)][bool]$ToFile
    )
    $script:KioskScriptName = $ScriptName
    $script:KioskLogFile = $null
    if ($ToFile) {
        $dir = Join-Path $env:ProgramData 'AVACOM\logs'
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $script:KioskLogFile = Join-Path $dir $LogFileName
    }
}

function Get-KioskLogFile {
    return $script:KioskLogFile
}

function Write-KioskLog {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [ValidateSet('INFO', 'WARN', 'ERROR', 'OK', 'DRYRUN', 'STEP')][string]$Level,
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
    if ($null -ne $script:KioskLogFile) {
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        $line = ('{0} [{1}] [{2}] {3}{4}' -f $stamp, $Level, $script:KioskScriptName, $Message, [Environment]::NewLine)
        try {
            [System.IO.File]::AppendAllText($script:KioskLogFile, $line, (New-Object System.Text.UTF8Encoding($false)))
        } catch {
            Write-Host ('[WARN] No se pudo escribir en el registro: ' + $_.Exception.Message) -ForegroundColor Yellow
        }
    }
}

# Bloqueos: en modo real un bloqueo aborta (throw); en -DryRun se acumulan y se muestran.
function Set-KioskBlockMode {
    param([Parameter(Mandatory = $true)][ValidateSet('throw', 'collect')][string]$Mode)
    $script:KioskBlockMode = $Mode
    $script:KioskBlockers.Clear()
}

function Add-KioskBlocker {
    param([Parameter(Mandatory = $true)][string]$Message)
    if ($script:KioskBlockMode -eq 'throw') { throw $Message }
    Write-KioskLog ERROR ('[un run real se detendria aqui] ' + $Message)
    [void]$script:KioskBlockers.Add($Message)
}

function Get-KioskBlockerCount {
    return $script:KioskBlockers.Count
}

# ---------------------------------------------------------------------------
# Sistema: privilegios y edicion de Windows
# ---------------------------------------------------------------------------
function Test-KioskElevated {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-KioskSystem {
    return [System.Security.Principal.WindowsIdentity]::GetCurrent().IsSystem
}

function Get-KioskEdition {
    $editionId = ''
    $productName = ''
    $build = ''
    try {
        $cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
        $editionId = [string]$cv.EditionID
        $productName = [string]$cv.ProductName
        $build = [string]$cv.CurrentBuild
    } catch { }
    $caption = ''
    try { $caption = [string](Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop).Caption } catch { }
    if ([string]::IsNullOrWhiteSpace($caption)) { $caption = $productName }
    return [pscustomobject]@{
        EditionId   = $editionId
        ProductName = $productName
        Caption     = $caption
        Build       = $build
    }
}

function Test-KioskEditionSupported {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('AssignedAccess', 'ShellLauncher')][string]$Mode,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$EditionId
    )
    if ($Mode -eq 'AssignedAccess') {
        # Pro, Pro Education, Pro for Workstations, Enterprise, Education, IoT Enterprise (y variantes N / LTSC)
        return ($EditionId -match '^(Professional(Education|Workstation)?|Enterprise|Education|IoTEnterprise)(N|S|SN|K)?$')
    }
    # Shell Launcher: Enterprise, Education, IoT Enterprise (NO Pro)
    return ($EditionId -match '^(Enterprise|Education|IoTEnterprise)(N|S|SN|K)?$')
}

# ---------------------------------------------------------------------------
# Cuentas locales
# ---------------------------------------------------------------------------
function Test-KioskUserName {
    param([AllowEmptyString()][string]$Name)
    if ([string]::IsNullOrEmpty($Name)) { return $false }
    if ($Name.EndsWith('.')) { return $false }
    return ($Name -match '^[A-Za-z0-9][A-Za-z0-9_.-]{0,19}$')
}

function Get-KioskUser {
    param([Parameter(Mandatory = $true)][string]$Name)
    try { return (Get-LocalUser -Name $Name -ErrorAction Stop) } catch { return $null }
}

function Get-KioskAdminAccounts {
    <# Nombres (sin el prefijo del equipo) de las cuentas LOCALES de usuario del grupo Administradores. #>
    $names = New-Object System.Collections.Generic.List[string]
    $prefix = $env:COMPUTERNAME + '\'
    $members = $null
    try {
        $members = @(Get-LocalGroupMember -SID $script:KioskAdminsSid -ErrorAction Stop)
    } catch {
        # Get-LocalGroupMember falla si el grupo contiene SID huerfanos (p. ej. cuentas de Azure AD borradas):
        # se consulta el grupo por ADSI, que no tiene ese problema.
        $members = $null
    }
    if ($null -ne $members) {
        foreach ($m in $members) {
            # OJO: ObjectClass esta traducido al idioma de Windows ("Usuario"), por eso no se usa;
            # los grupos anidados se descartan despues, al cruzar con Get-LocalUser.
            $n = [string]$m.Name
            if ($n.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                [void]$names.Add($n.Substring($prefix.Length))
            }
        }
    } else {
        $groupName = [string](Get-CimInstance -ClassName Win32_Group -Filter ("SID='" + $script:KioskAdminsSid + "'") -ErrorAction Stop).Name
        $group = [ADSI]('WinNT://' + $env:COMPUTERNAME + '/' + $groupName + ',group')
        foreach ($mem in @($group.Invoke('Members'))) {
            $cls = [string]$mem.GetType().InvokeMember('Class', 'GetProperty', $null, $mem, $null)
            $path = [string]$mem.GetType().InvokeMember('ADsPath', 'GetProperty', $null, $mem, $null)
            if ($cls -ne 'User') { continue }
            # El ADsPath de una cuenta local es WinNT://<DOMINIO o GRUPO DE TRABAJO>/<EQUIPO>/<usuario>
            # (o WinNT://<EQUIPO>/<usuario>); el de una cuenta de dominio, WinNT://<DOMINIO>/<usuario>.
            $segs = $path.Substring($path.IndexOf('//') + 2).Split([char]47)
            if ($segs.Count -ge 2 -and $segs[$segs.Count - 2] -ieq $env:COMPUTERNAME) {
                [void]$names.Add([string]$mem.GetType().InvokeMember('Name', 'GetProperty', $null, $mem, $null))
            }
        }
    }
    return $names.ToArray()
}

function Test-KioskUserIsAdmin {
    param([Parameter(Mandatory = $true)][string]$Name)
    foreach ($n in @(Get-KioskAdminAccounts)) {
        if ($n -ieq $Name) { return $true }
    }
    return $false
}

function Get-KioskRecoveryAdmins {
    <# Cuentas administradoras locales HABILITADAS distintas de la cuenta del kiosco. #>
    param([Parameter(Mandatory = $true)][string]$ExcludeUser)
    $result = New-Object System.Collections.Generic.List[string]
    foreach ($n in @(Get-KioskAdminAccounts)) {
        if ($n -ieq $ExcludeUser) { continue }
        $u = Get-KioskUser -Name $n
        if ($null -ne $u -and $u.Enabled) { [void]$result.Add($n) }
    }
    return $result.ToArray()
}

function Test-KioskAccountsPreflight {
    <#
        Reglas de cuentas comunes a los scripts de instalacion (solo lectura):
          - la cuenta del kiosco, si existe, NO puede ser administradora;
          - debe existir OTRA cuenta administradora local habilitada (recuperacion).
        Devuelve el objeto de usuario (o $null si aun no existe).
    #>
    param([Parameter(Mandatory = $true)][string]$UserName)

    $u = Get-KioskUser -Name $UserName
    if ($null -ne $u) {
        Write-KioskLog INFO ("La cuenta local '{0}' ya existe (habilitada: {1})." -f $UserName, $u.Enabled)
        if (-not $u.Enabled) {
            Write-KioskLog WARN ("La cuenta '{0}' esta deshabilitada y no podra iniciar sesion. Habilitala con: Enable-LocalUser -Name '{0}'" -f $UserName)
        }
        if (Test-KioskUserIsAdmin -Name $UserName) {
            Add-KioskBlocker ("La cuenta '{0}' es ADMINISTRADORA. El kiosco debe ser un usuario estandar: quitala del grupo Administradores o usa otro nombre." -f $UserName)
        }
    } else {
        Write-KioskLog INFO ("La cuenta local '{0}' no existe todavia." -f $UserName)
    }

    $recovery = @(Get-KioskRecoveryAdmins -ExcludeUser $UserName)
    if ($recovery.Count -eq 0) {
        Add-KioskBlocker ("No hay OTRA cuenta administradora local habilitada distinta de '{0}'. Crea o habilita una (cuenta de recuperacion) antes de continuar; si no, quedarias sin forma de revertir el kiosco." -f $UserName)
    } else {
        Write-KioskLog INFO ('Cuenta(s) administradora(s) de recuperacion: ' + ($recovery -join ', '))
    }
    return $u
}

function Test-KioskSecureStringEqual {
    param(
        [Parameter(Mandatory = $true)][System.Security.SecureString]$A,
        [Parameter(Mandatory = $true)][System.Security.SecureString]$B
    )
    $pa = [IntPtr]::Zero
    $pb = [IntPtr]::Zero
    try {
        $pa = [System.Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($A)
        $pb = [System.Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($B)
        $sa = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($pa)
        $sb = [System.Runtime.InteropServices.Marshal]::PtrToStringUni($pb)
        return [string]::Equals($sa, $sb, [System.StringComparison]::Ordinal)
    } finally {
        if ($pa -ne [IntPtr]::Zero) { [System.Runtime.InteropServices.Marshal]::ZeroFreeGlobalAllocUnicode($pa) }
        if ($pb -ne [IntPtr]::Zero) { [System.Runtime.InteropServices.Marshal]::ZeroFreeGlobalAllocUnicode($pb) }
    }
}

function Read-KioskNewPassword {
    <# Pide la contraseña con Read-Host -AsSecureString (dos veces). Nunca se imprime ni se registra. #>
    param([Parameter(Mandatory = $true)][string]$UserName)
    for ($i = 0; $i -lt 3; $i++) {
        $p1 = Read-Host -AsSecureString -Prompt ("Contrasena para la cuenta nueva '{0}'" -f $UserName)
        $p2 = Read-Host -AsSecureString -Prompt 'Repite la contrasena'
        if ($p1.Length -eq 0) {
            Write-KioskLog WARN 'La contrasena no puede estar vacia.'
            continue
        }
        if (Test-KioskSecureStringEqual -A $p1 -B $p2) { return $p1 }
        Write-KioskLog WARN 'Las contrasenas no coinciden.'
    }
    throw 'No se obtuvo una contrasena valida tras 3 intentos.'
}

function New-KioskLocalUser {
    <# MODIFICA EL EQUIPO: crea el usuario local estandar (grupo Usuarios). #>
    param(
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][System.Security.SecureString]$Password
    )
    New-LocalUser -Name $UserName -Password $Password `
        -FullName 'AVACOM Examen' `
        -Description 'Cuenta estandar del kiosco de examen (AVACOM LMS)' `
        -PasswordNeverExpires -UserMayNotChangePassword -AccountNeverExpires -ErrorAction Stop | Out-Null
    Add-LocalGroupMember -SID $script:KioskUsersSid -Member $UserName -ErrorAction Stop
}

# ---------------------------------------------------------------------------
# Rutas, hash y marcador
# ---------------------------------------------------------------------------
function Resolve-KioskPath {
    <# Expande variables de entorno, exige ruta absoluta y la normaliza. No exige que exista. #>
    param([Parameter(Mandatory = $true)][string]$Path)
    $p = [System.Environment]::ExpandEnvironmentVariables($Path.Trim().Trim('"'))
    if (-not [System.IO.Path]::IsPathRooted($p)) {
        throw ("La ruta '{0}' no es absoluta." -f $Path)
    }
    return [System.IO.Path]::GetFullPath($p)
}

function Get-KioskSha256Hex {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Text))
    } finally {
        $sha.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

function Get-KioskMarkerPath {
    return (Join-Path $env:ProgramData 'AVACOM\kiosk-provisioned.marker')
}

function Read-KioskMarker {
    <# Lee el marcador (SOLO UN INDICIO, kiosk.md 5.1). Devuelve $null si no existe o no es JSON valido. #>
    param([string]$Path = (Get-KioskMarkerPath))
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return ([System.IO.File]::ReadAllText($Path) | ConvertFrom-Json)
    } catch {
        return [pscustomobject]@{ mode = '(ilegible)'; user = ''; executablePath = ''; appliedAtUtc = ''; configSha256 = '' }
    }
}

function Get-KioskMarkerJson {
    param(
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][string]$ConfigSha256
    )
    $obj = [ordered]@{
        mode           = $Mode
        user           = $UserName
        executablePath = $ExecutablePath
        appliedAtUtc   = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        configSha256   = $ConfigSha256
    }
    return ($obj | ConvertTo-Json -Depth 3)
}

function Write-KioskMarker {
    <# MODIFICA EL EQUIPO: escribe %ProgramData%\AVACOM\kiosk-provisioned.marker (JSON UTF-8 sin BOM). #>
    param(
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][string]$ConfigSha256,
        [string]$Path = (Get-KioskMarkerPath)
    )
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $json = Get-KioskMarkerJson -Mode $Mode -UserName $UserName -ExecutablePath $ExecutablePath -ConfigSha256 $ConfigSha256
    $tmp = $Path + '.tmp'
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Remove-KioskMarker {
    <# MODIFICA EL EQUIPO: borra el marcador si existe. #>
    param([string]$Path = (Get-KioskMarkerPath))
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
}

# ---------------------------------------------------------------------------
# Assigned Access (multiaplicacion con DesktopAppPath)
# ---------------------------------------------------------------------------
function New-KioskAssignedAccessXml {
    <#
        Construye la configuracion de Assigned Access multiaplicacion: un perfil con las
        aplicaciones de escritorio permitidas (DesktopAppPath) y una cuenta local asociada.
        La app principal se lanza sola al iniciar sesion (rs5:AutoLaunch).
        Los valores se escapan para XML. No se incluye StartLayout (no hace falta).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [string[]]$AdditionalAllowedPaths = @()
    )
    $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }

    # Id de perfil determinista (mismo usuario => mismo Id), derivado del nombre.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes('AVACOM-kiosk|' + $UserName.ToLowerInvariant())) } finally { $sha.Dispose() }
    $gb = New-Object byte[] 16
    [Array]::Copy($h, $gb, 16)
    $profileId = '{' + (New-Object System.Guid (, $gb)).ToString().ToUpperInvariant() + '}'

    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('          <App DesktopAppPath="' + (& $esc $ExecutablePath) + '" rs5:AutoLaunch="true" />')
    foreach ($p in $AdditionalAllowedPaths) {
        if ([string]::IsNullOrWhiteSpace($p)) { continue }
        if ($p -ieq $ExecutablePath) { continue }
        [void]$lines.Add('          <App DesktopAppPath="' + (& $esc $p) + '" />')
    }
    $appsXml = $lines -join "`n"
    $account = & $esc $UserName

    $xml = @"
<?xml version="1.0" encoding="utf-8"?>
<AssignedAccessConfiguration xmlns="http://schemas.microsoft.com/AssignedAccess/2017/config" xmlns:rs5="http://schemas.microsoft.com/AssignedAccess/201810/config">
  <Profiles>
    <Profile Id="$profileId">
      <AllAppsList>
        <AllowedApps>
$appsXml
        </AllowedApps>
      </AllAppsList>
      <Taskbar ShowTaskbar="false" />
    </Profile>
  </Profiles>
  <Configs>
    <Config>
      <Account>$account</Account>
      <DefaultProfile Id="$profileId" />
    </Config>
  </Configs>
</AssignedAccessConfiguration>
"@
    return ($xml -replace "`r`n", "`n")
}

function Get-KioskAssignedAccessSummary {
    <# Extrae cuentas y rutas DesktopAppPath de un texto de configuracion (acepta la forma escapada). #>
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$ConfigText)
    $text = $ConfigText
    if (($text -notmatch '^\s*<') -and ($text -match '&lt;')) {
        $text = [System.Net.WebUtility]::HtmlDecode($text)
    }
    $accounts = New-Object System.Collections.Generic.List[string]
    $apps = New-Object System.Collections.Generic.List[string]
    $parsed = $false
    try {
        $doc = New-Object System.Xml.XmlDocument
        $doc.LoadXml($text)
        foreach ($n in $doc.SelectNodes("//*[local-name()='Account']")) { [void]$accounts.Add($n.InnerText.Trim()) }
        foreach ($n in $doc.SelectNodes("//*[local-name()='App']")) {
            $p = $n.GetAttribute('DesktopAppPath')
            if (-not [string]::IsNullOrEmpty($p)) { [void]$apps.Add($p) }
        }
        $parsed = $true
    } catch {
        $parsed = $false
    }
    return [pscustomobject]@{
        Parsed      = $parsed
        Text        = $text
        Accounts    = $accounts.ToArray()
        DesktopApps = $apps.ToArray()
    }
}

function Test-KioskAssignedAccessText {
    <# ¿El texto de configuracion menciona a nuestro usuario y a nuestro ejecutable? #>
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$ConfigText,
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [string]$UserSid = ''
    )
    $sum = Get-KioskAssignedAccessSummary -ConfigText $ConfigText
    $userHit = $false
    $exeHit = $false
    if ($sum.Parsed) {
        foreach ($a in $sum.Accounts) {
            if (($a -ieq $UserName) -or ($a -like ('*\' + $UserName)) -or ((-not [string]::IsNullOrEmpty($UserSid)) -and ($a -ieq $UserSid))) { $userHit = $true }
        }
        foreach ($p in $sum.DesktopApps) {
            $full = $p
            try { $full = [System.IO.Path]::GetFullPath([System.Environment]::ExpandEnvironmentVariables($p)) } catch { }
            if ($full -ieq $ExecutablePath) { $exeHit = $true }
        }
    } else {
        $userHit = ($sum.Text.IndexOf($UserName, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        $exeHit = ($sum.Text.IndexOf($ExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    }
    return [pscustomobject]@{ UserMatch = $userHit; ExeMatch = $exeHit; Accounts = $sum.Accounts; DesktopApps = $sum.DesktopApps }
}

function Get-KioskMdmConfiguration {
    <# Lee MDM_AssignedAccess.Configuration (solo lectura). Status: Ok | AccessDenied | Unavailable. #>
    try {
        $o = @(Get-CimInstance -Namespace $script:KioskMdmNamespace -ClassName $script:KioskMdmClass -ErrorAction Stop)
        $cfg = ''
        if ($o.Count -gt 0 -and $null -ne $o[0].Configuration) { $cfg = [string]$o[0].Configuration }
        return [pscustomobject]@{ Status = 'Ok'; Configuration = $cfg; Message = '' }
    } catch {
        $msg = ([string]$_.Exception.Message).Trim()
        $denied = $false
        if ($null -ne $_.Exception.PSObject.Properties['NativeErrorCode'] -and ([string]$_.Exception.NativeErrorCode) -eq 'AccessDenied') { $denied = $true }
        elseif ($msg -match 'denegado|denied|0x80070005|0x80041003') { $denied = $true }
        $status = 'Unavailable'
        if ($denied) { $status = 'AccessDenied' }
        return [pscustomobject]@{ Status = $status; Configuration = $null; Message = $msg }
    }
}

function Get-KioskAssignedAccessRegistry {
    <#
        Lee (solo lectura, sin privilegios) el almacen donde el sistema guarda la configuracion de
        Assigned Access: HKLM\SOFTWARE\Microsoft\Windows\AssignedAccessConfiguration.
        Empty = sin ningun valor ni clave de nivel 2 o mas (solo el esqueleto vacio que el sistema
                siempre crea) => NO hay ninguna configuracion en el equipo.
        Text  = volcado de nombres de clave y valores, para buscar el usuario y el ejecutable.
    #>
    $root = $script:KioskAaRegistryRoot
    if (-not (Test-Path -LiteralPath $root)) {
        return [pscustomobject]@{ Exists = $false; Empty = $true; Text = '' }
    }
    $sb = New-Object System.Text.StringBuilder
    $entries = 0
    $rootItem = Get-Item -LiteralPath $root
    $rootName = [string]$rootItem.Name
    $keys = @($rootItem)
    $keys += @(Get-ChildItem -LiteralPath $root -Recurse -ErrorAction SilentlyContinue)
    foreach ($k in $keys) {
        # El sistema mantiene siempre el esqueleto Configs / GroupConfigs / Profiles / RawData
        # (nivel 1). Hay configuracion real si existe alguna clave de nivel 2 o mas, o algun valor.
        $rel = ([string]$k.Name).Substring($rootName.Length).Trim([char]92)
        $depth = 0
        if ($rel -ne '') { $depth = $rel.Split([char]92).Count }
        if ($depth -ge 2) { $entries++ }
        [void]$sb.AppendLine($k.Name)
        foreach ($vn in $k.GetValueNames()) {
            $entries++
            $v = $k.GetValue($vn)
            [void]$sb.AppendLine('  ' + $vn)
            if ($v -is [byte[]]) {
                [void]$sb.AppendLine('  ' + [System.Text.Encoding]::Unicode.GetString($v))
                [void]$sb.AppendLine('  ' + [System.Text.Encoding]::UTF8.GetString($v))
            } elseif ($v -is [string[]]) {
                [void]$sb.AppendLine('  ' + ($v -join '|'))
            } else {
                [void]$sb.AppendLine('  ' + [string]$v)
            }
        }
    }
    return [pscustomobject]@{ Exists = $true; Empty = ($entries -eq 0); Text = $sb.ToString() }
}

function Get-KioskAssignedAccessState {
    <#
        Estado REAL de Assigned Access (solo lectura). Fuente 1: MDM_AssignedAccess (necesita
        administrador). Si no se puede leer, fuente 2: almacen del sistema en el registro
        (legible sin privilegios).
        HasConfig: $true / $false / $null (no se pudo saber).
    #>
    param(
        [Parameter(Mandatory = $true)][string]$UserName,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [string]$UserSid = ''
    )
    $mdm = Get-KioskMdmConfiguration
    if ($mdm.Status -eq 'Ok') {
        if ([string]::IsNullOrWhiteSpace($mdm.Configuration)) {
            return [pscustomobject]@{ Source = 'mdm'; HasConfig = $false; UserMatch = $false; ExeMatch = $false; Accounts = @(); Detail = 'MDM_AssignedAccess no tiene ninguna configuracion.' }
        }
        $t = Test-KioskAssignedAccessText -ConfigText $mdm.Configuration -UserName $UserName -ExecutablePath $ExecutablePath -UserSid $UserSid
        return [pscustomobject]@{ Source = 'mdm'; HasConfig = $true; UserMatch = $t.UserMatch; ExeMatch = $t.ExeMatch; Accounts = @($t.Accounts); Detail = 'Leido de MDM_AssignedAccess.Configuration.' }
    }

    $reg = Get-KioskAssignedAccessRegistry
    $why = ('No se pudo leer MDM_AssignedAccess ({0}: {1}).' -f $mdm.Status, $mdm.Message)
    if ($reg.Empty) {
        return [pscustomobject]@{ Source = 'registry'; HasConfig = $false; UserMatch = $false; ExeMatch = $false; Accounts = @(); Detail = ($why + ' El almacen del sistema en el registro esta VACIO: no hay ninguna configuracion de Assigned Access.') }
    }
    $userHit = ($reg.Text.IndexOf($UserName, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    if ((-not $userHit) -and (-not [string]::IsNullOrEmpty($UserSid))) {
        $userHit = ($reg.Text.IndexOf($UserSid, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    }
    $exeHit = ($reg.Text.IndexOf($ExecutablePath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    return [pscustomobject]@{ Source = 'registry'; HasConfig = $true; UserMatch = $userHit; ExeMatch = $exeHit; Accounts = @(); Detail = ($why + ' Se uso el almacen del sistema en el registro (busqueda de texto, heuristica).') }
}

function Set-AssignedAccessMdm {
    <#
        MODIFICA EL EQUIPO. Escribe la configuracion en MDM_AssignedAccess.Configuration.
        Este puente WMI normalmente exige la cuenta SYSTEM. -Xml vacio borra la configuracion.
        Autocontenida a proposito: su cuerpo se incrusta tal cual en el script que corre como SYSTEM.
    #>
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Xml)
    $ns = 'root\cimv2\mdm\dmmap'
    $cls = 'MDM_AssignedAccess'
    # La propiedad es una cadena: el XML va escapado (&lt; &gt; &amp; ...), como en la documentacion de Microsoft.
    $encoded = [System.Net.WebUtility]::HtmlEncode($Xml)
    $obj = Get-CimInstance -Namespace $ns -ClassName $cls -ErrorAction Stop
    if ($null -ne $obj) {
        $inst = @($obj)[0]
        $inst.Configuration = $encoded
        Set-CimInstance -CimInstance $inst -ErrorAction Stop
    } else {
        New-CimInstance -Namespace $ns -ClassName $cls -Property @{ ParentID = './Vendor/MSFT'; InstanceID = 'AssignedAccess'; Configuration = $encoded } -ErrorAction Stop | Out-Null
    }
}

function New-KioskSystemJobScript {
    <#
        Solo texto (no modifica nada): genera el script que ejecutara la tarea SYSTEM. Incrusta el cuerpo
        de Set-AssignedAccessMdm, lee config.xml de su propia carpeta y escribe result.json de forma atomica.
    #>
    param([Parameter(Mandatory = $true)][string]$FunctionBody)
    $template = @'
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
function Set-AssignedAccessMdm {
__BODY__
}
$result = $null
try {
    $xml = [System.IO.File]::ReadAllText((Join-Path $here 'config.xml'), [System.Text.Encoding]::UTF8)
    Set-AssignedAccessMdm -Xml $xml
    $result = @{ ok = $true; message = 'ok' }
} catch {
    $result = @{ ok = $false; message = [string]$_.Exception.Message }
}
$tmp = Join-Path $here 'result.tmp'
[System.IO.File]::WriteAllText($tmp, ($result | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
Move-Item -LiteralPath $tmp -Destination (Join-Path $here 'result.json') -Force
'@
    return $template.Replace('__BODY__', $FunctionBody)
}

function Invoke-KioskAsSystem {
    <#
        MODIFICA EL EQUIPO (temporalmente). Ejecuta Set-AssignedAccessMdm como SYSTEM mediante una
        tarea programada de un solo uso. La carpeta de trabajo (config.xml, job.ps1, result.json)
        se crea con una ACL que solo admite SYSTEM y Administradores, para que ningun usuario
        estandar pueda alterar lo que se ejecuta; se borra al terminar, igual que la tarea.
    #>
    param(
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Xml,
        [int]$TimeoutSeconds = 120
    )
    $parent = Join-Path $env:ProgramData 'AVACOM'
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $work = Join-Path $parent ('run-' + [guid]::NewGuid().ToString('N'))
    $taskName = 'AVACOM-Kiosk-' + [guid]::NewGuid().ToString('N')

    $sec = New-Object System.Security.AccessControl.DirectorySecurity
    $sec.SetAccessRuleProtection($true, $false)
    foreach ($sidText in @('S-1-5-18', $script:KioskAdminsSid)) {
        $sid = New-Object System.Security.Principal.SecurityIdentifier($sidText)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $sid,
            [System.Security.AccessControl.FileSystemRights]::FullControl,
            ([System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'),
            [System.Security.AccessControl.PropagationFlags]::None,
            [System.Security.AccessControl.AccessControlType]::Allow)
        $sec.AddAccessRule($rule)
    }
    [void][System.IO.Directory]::CreateDirectory($work, $sec)

    try {
        $utf8Bom = New-Object System.Text.UTF8Encoding($true)
        [System.IO.File]::WriteAllText((Join-Path $work 'config.xml'), $Xml, (New-Object System.Text.UTF8Encoding($false)))

        $job = New-KioskSystemJobScript -FunctionBody ((Get-Item -LiteralPath Function:\Set-AssignedAccessMdm).ScriptBlock.ToString())
        $jobPath = Join-Path $work 'job.ps1'
        [System.IO.File]::WriteAllText($jobPath, $job, $utf8Bom)

        $psExe = Join-Path $env:windir 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $action = New-ScheduledTaskAction -Execute $psExe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $jobPath + '"')
        $principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
        Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
        try {
            Start-ScheduledTask -TaskName $taskName
            $resultPath = Join-Path $work 'result.json'
            $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
            while (-not (Test-Path -LiteralPath $resultPath)) {
                if ((Get-Date) -gt $deadline) {
                    throw ('La tarea SYSTEM no respondio en {0} s.' -f $TimeoutSeconds)
                }
                Start-Sleep -Milliseconds 500
            }
            $res = [System.IO.File]::ReadAllText($resultPath) | ConvertFrom-Json
            if (-not $res.ok) { throw ('Fallo como SYSTEM: ' + [string]$res.message) }
        } finally {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        }
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-AssignedAccessApply {
    <#
        MODIFICA EL EQUIPO. Aplica (o, con -Xml '', borra) la configuracion por el puente MDM.
        Primero intenta directamente; si falla (lo normal sin SYSTEM: "Acceso denegado"),
        reintenta como SYSTEM mediante una tarea programada de un solo uso.
        Devuelve una cadena que dice como se aplico.
    #>
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Xml)
    if (Test-KioskSystem) {
        Set-AssignedAccessMdm -Xml $Xml
        return 'directo (ya se ejecutaba como SYSTEM)'
    }
    try {
        Set-AssignedAccessMdm -Xml $Xml
        return 'directo (administrador)'
    } catch {
        Write-KioskLog WARN ('El intento directo fallo: ' + ([string]$_.Exception.Message).Trim() + ' Se reintenta como SYSTEM (tarea programada de un solo uso).')
    }
    Invoke-KioskAsSystem -Xml $Xml
    return 'como SYSTEM (tarea programada temporal)'
}

# ---------------------------------------------------------------------------
# Shell Launcher v2
# ---------------------------------------------------------------------------
function Get-KioskShellLauncherFeatureState {
    <# Enabled | Disabled | EnablePending | DisablePending | Unknown (p. ej. sin elevacion). Solo lectura. #>
    try {
        $f = Get-WindowsOptionalFeature -Online -FeatureName $script:KioskShellFeature -ErrorAction Stop
        return [string]$f.State
    } catch {
        return 'Unknown'
    }
}

function Enable-KioskShellLauncherFeature {
    <# MODIFICA EL EQUIPO. Devuelve $true si Windows pide reiniciar. #>
    $r = Enable-WindowsOptionalFeature -Online -FeatureName $script:KioskShellFeature -All -NoRestart -ErrorAction Stop
    return [bool]$r.RestartNeeded
}

function Disable-KioskShellLauncherFeature {
    <# MODIFICA EL EQUIPO. Devuelve $true si Windows pide reiniciar. #>
    $r = Disable-WindowsOptionalFeature -Online -FeatureName $script:KioskShellFeature -NoRestart -ErrorAction Stop
    return [bool]$r.RestartNeeded
}

function Get-KioskShellLauncherState {
    <#
        Estado REAL de Shell Launcher (solo lectura).
        ClassAvailable = $false  => la caracteristica no esta activa (no hay clase WMI).
        Queried = $false         => hay clase pero no se pudo leer (p. ej. sin privilegios).
    #>
    param([string]$UserSid = '', [string]$ExecutablePath = '')
    try {
        [void](Get-CimClass -Namespace $script:KioskWeslNamespace -ClassName $script:KioskWeslClass -ErrorAction Stop)
    } catch {
        return [pscustomobject]@{ ClassAvailable = $false; Queried = $true; Enabled = $false; UserMapped = $false; ExeMatch = $false; Detail = 'La clase WESL_UserSetting no existe: la caracteristica Client-EmbeddedShellLauncher no esta activa.' }
    }
    try {
        $settings = @(Get-CimInstance -Namespace $script:KioskWeslNamespace -ClassName $script:KioskWeslClass -ErrorAction Stop)
    } catch {
        return [pscustomobject]@{ ClassAvailable = $true; Queried = $false; Enabled = $false; UserMapped = $false; ExeMatch = $false; Detail = ('No se pudo leer WESL_UserSetting: ' + ([string]$_.Exception.Message).Trim()) }
    }
    $mapped = $false
    $exeHit = $false
    foreach ($s in $settings) {
        if ((-not [string]::IsNullOrEmpty($UserSid)) -and ([string]$s.Sid -ieq $UserSid)) {
            $mapped = $true
            if ((-not [string]::IsNullOrEmpty($ExecutablePath)) -and ([string]$s.Shell -ieq $ExecutablePath)) { $exeHit = $true }
        }
    }
    $enabled = $false
    try {
        $cls = [wmiclass]('\\localhost\' + $script:KioskWeslNamespace + ':' + $script:KioskWeslClass)
        $enabled = [bool]($cls.IsEnabled().Enabled)
    } catch { }
    return [pscustomobject]@{ ClassAvailable = $true; Queried = $true; Enabled = $enabled; UserMapped = $mapped; ExeMatch = $exeHit; Detail = ('Leido de WESL_UserSetting ({0} asignacion(es)).' -f $settings.Count) }
}

function Invoke-KioskShellLauncherApply {
    <# MODIFICA EL EQUIPO. Asigna el shell personalizado al usuario y deja explorer.exe para los demas. #>
    param(
        [Parameter(Mandatory = $true)][string]$UserSid,
        [Parameter(Mandatory = $true)][string]$ExecutablePath,
        [Parameter(Mandatory = $true)][int]$ExitAction
    )
    $restartShell = 0
    $cls = [wmiclass]('\\localhost\' + $script:KioskWeslNamespace + ':' + $script:KioskWeslClass)
    try { [void]$cls.RemoveCustomShell($UserSid) } catch { }   # idempotente: si no existia, no pasa nada
    [void]$cls.SetDefaultShell('explorer.exe', $restartShell)
    [void]$cls.SetCustomShell($script:KioskAdminsSid, 'explorer.exe', $null, $null, $restartShell)
    [void]$cls.SetCustomShell($UserSid, $ExecutablePath, $null, $null, $ExitAction)
    [void]$cls.SetEnabled($true)
}

function Invoke-KioskShellLauncherRemove {
    <#
        MODIFICA EL EQUIPO. Quita la asignacion del usuario. Si no queda ninguna otra asignacion
        (aparte de la de Administradores -> explorer.exe que pone el instalador), tambien quita esa
        y desactiva Shell Launcher. Devuelve la lista de mensajes de lo hecho.
    #>
    param([Parameter(Mandatory = $true)][string]$UserSid)
    $msgs = New-Object System.Collections.Generic.List[string]
    $cls = [wmiclass]('\\localhost\' + $script:KioskWeslNamespace + ':' + $script:KioskWeslClass)
    try {
        [void]$cls.RemoveCustomShell($UserSid)
        [void]$msgs.Add('Asignacion de shell del usuario eliminada.')
    } catch {
        [void]$msgs.Add('No habia asignacion de shell para el usuario (o no se pudo quitar): ' + ([string]$_.Exception.Message).Trim())
    }
    $left = @(Get-CimInstance -Namespace $script:KioskWeslNamespace -ClassName $script:KioskWeslClass -ErrorAction Stop |
            Where-Object { [string]$_.Sid -ine $script:KioskAdminsSid })
    if ($left.Count -eq 0) {
        try { [void]$cls.RemoveCustomShell($script:KioskAdminsSid) } catch { }
        [void]$cls.SetEnabled($false)
        [void]$msgs.Add('No quedan otras asignaciones: Shell Launcher desactivado.')
    } else {
        [void]$msgs.Add(('Quedan {0} asignacion(es) de otros usuarios: Shell Launcher sigue activo.' -f $left.Count))
    }
    return $msgs.ToArray()
}
