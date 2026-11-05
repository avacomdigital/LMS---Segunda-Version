<#
.SYNOPSIS
    Ensayo de la LIBERACION DE LA CLAVE del paquete cifrado (segunda proteccion, S2) con el Host real, el TPM real (claves de USUARIO con nombre propio), la estacion real y el backend REAL de dist\staging.

.DESCRIPTION
    Arma, en una carpeta temporal y SIN tocar este equipo (AVACOM_OPS_ENSAYO, ProgramData redirigido, puerto libre), una instalacion de mentira:

        Runtime\   el Host compilado con la llave de sello de ENSAYO + avacom_boot.py + el Python embebido de dist\staging (una union de carpeta, no una copia)
        Backend\   el backend de dist\staging CIFRADO con Cifrar-Backend.py: sin ningun .py, solo codigo.avpkg y los datos

    Y comprueba, con el servicio de verdad (verbo servicio + /health/):
      A. Sin sello el codigo no se abre: la liberacion sale con 40 y el backend NO arranca.
      B. Con el sello y la clave del paquete de ESTE equipo (las firma la estacion) el backend arranca y responde, sin un solo .py en el disco.
      C. La instalacion y la carpeta de datos copiadas a OTRO equipo (otras claves del TPM): no se abre (42) y el backend no arranca.
      D. El sello y la clave de otro equipo con el sello propio: la clave no es para este equipo; no se abre.
      E. Una lista de revocados con la clave de ESTE equipo: no se libera (43).
      F. Un byte cambiado en codigo.avpkg: no arranca.
      G. Tiempos de arranque del mismo backend, plano y cifrado.

    Exige que dist\staging exista (lo deja Build-Installer.ps1). NO demuestra: claves de maquina (exigen administrador), el servicio de Windows real ni un TPM discreto.
#>
[CmdletBinding()]
param(
    [switch] $Conservar,
    # Contra el PAQUETE que salio del build (ya cifrado, sin .py): la carpeta (por omision dist\staging), el archivo de custodia con la llave K de ESE paquete y la privada (.avkey) de la llave de
    # sello con la que se compilo su Host. La frase de esa llave va por la variable de entorno AVACOM_FRASE_SELLO_ENSAYO (nunca por argumento). Sin -ClaveDelPaquete el ensayo cifra el Backend plano
    # de dist\staging por su cuenta, con su propia llave de sello y su propio Host (el modo de antes).
    [string] $Staging = '',
    [string] $ClaveDelPaquete = '',
    [string] $LlaveDeSello = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$staging = if ($Staging) { (Resolve-Path -LiteralPath $Staging).Path } else { Join-Path $raiz 'dist\staging' }
$modoPaquete = [bool]$ClaveDelPaquete
if (-not (Test-Path (Join-Path $staging 'Runtime\Python\python.exe'))) { throw 'Falta dist\staging (corre Build-Installer.ps1 una vez): hace falta el Python embebido.' }
$py = Join-Path $raiz 'backend\.venv\Scripts\python.exe'
$estacion = Join-Path $raiz 'tools\licencias\iniciar.py'
$pyRuntime = Join-Path $staging 'Runtime\Python\python.exe'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('avacom-ensayo-clave-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $temp | Out-Null
$frase = 'una frase de ensayo, larga y sin usar'
if ($modoPaquete) {
    if (-not (Test-Path -LiteralPath $ClaveDelPaquete)) { throw "No existe el archivo de custodia $ClaveDelPaquete." }
    if (-not $LlaveDeSello -or -not (Test-Path -LiteralPath $LlaveDeSello)) { throw 'Contra el paquete hace falta -LlaveDeSello (la .avkey de la llave de sello con la que se compilo su Host).' }
    if (-not (Test-Path (Join-Path $staging 'Backend\codigo.avpkg'))) { throw 'El paquete no esta cifrado (falta Backend\codigo.avpkg).' }
    $frase = $env:AVACOM_FRASE_SELLO_ENSAYO
    if (-not $frase) { throw 'Falta la variable de entorno AVACOM_FRASE_SELLO_ENSAYO (la frase de la llave de sello de prueba).' }
}
$bien = 0; $mal = 0
$procesos = New-Object System.Collections.Generic.List[int]
$entornoOriginal = @{}
foreach ($n in 'ProgramData', 'AVACOM_OPS_ENSAYO', 'AVACOM_OPS_DATOS', 'AVACOM_OPS_USB', 'AVACOM_OPS_UEFI') { $entornoOriginal[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }

function Comprobar([string] $Que, [bool] $Condicion, [string] $Detalle = '') {
    if ($Condicion) { $script:bien++; Write-Host "  OK   $Que" } else { $script:mal++; Write-Host "  FALLA $Que  $Detalle" -ForegroundColor Red }
}

function Estacion([string[]] $Argumentos) {
    $env:AVACOM_EMISOR_FRASE = $frase
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $salida = & $py $estacion @Argumentos 2>&1; return @{ Codigo = $LASTEXITCODE; Texto = ($salida | Out-String) } }
    finally { $ErrorActionPreference = $anterior; Remove-Item Env:AVACOM_EMISOR_FRASE -ErrorAction SilentlyContinue }
}

# La identidad UEFI de un ENSAYO sale de AVACOM_OPS_UEFI (el firmware real no se toca). '' = el equipo no trae la variable AVACOM_DEVICE_ID.
$script:uefiActual = 'AVACOM-OPS-00000001'

function Fijar([string] $datos, [string] $usb) {
    $env:AVACOM_OPS_ENSAYO = '1'; $env:AVACOM_OPS_DATOS = $datos; $env:AVACOM_OPS_USB = $usb
    if ($script:uefiActual) { $env:AVACOM_OPS_UEFI = $script:uefiActual } else { Remove-Item Env:AVACOM_OPS_UEFI -ErrorAction SilentlyContinue }
    $env:ProgramData = Join-Path $datos 'ProgramData'          # SR-10: ningun ensayo escribe en el ProgramData real
}

function Verbo([string] $instalacion, [string] $datos, [string] $usb, [string[]] $Argumentos) {
    Fijar $datos $usb
    $exe = Join-Path $instalacion 'Runtime\Avacom.Ops.Host.exe'
    $p = Start-Process -FilePath $exe -ArgumentList $Argumentos -Wait -PassThru -WindowStyle Hidden
    return $p.ExitCode
}

function Puerto-Libre {
    $o = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $o.Start(); $p = $o.LocalEndpoint.Port; $o.Stop(); return $p
}

function Poner-Valor([string] $archivo, [string] $clave, $valor) {
    $lineas = @(if (Test-Path $archivo) { Get-Content $archivo -Encoding UTF8 } else { @() }) | Where-Object { $_ -notmatch "^$clave=" }
    Set-Content -Path $archivo -Value (@($lineas) + "$clave=$valor") -Encoding UTF8
}

function Salud([int] $puerto, [int] $segundos) {
    $limite = (Get-Date).AddSeconds($segundos)
    while ((Get-Date) -lt $limite) {
        try {
            $p = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$puerto/health/"); $p.Timeout = 3000; $p.Proxy = $null
            $r = $p.GetResponse(); $ok = ([int]$r.StatusCode -eq 200); $r.Close()
            if ($ok) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

# Arranca el servicio (verbo servicio, como proceso normal) y devuelve cuantos segundos tardo en responder /health/ (o -1).
function Servir([string] $instalacion, [string] $datos, [int] $segundos = 90) {
    Fijar $datos ''
    $puerto = Puerto-Libre
    # Sin backend.env (antes de `preparar`) no se crea ninguno: un archivo a medias haria que `preparar` no generara las claves.
    if (Test-Path (Join-Path $datos 'Config\backend.env')) { Poner-Valor (Join-Path $datos 'Config\backend.env') 'AVACOM_OPS_BACKEND_PORT' $puerto }
    $exe = Join-Path $instalacion 'Runtime\Avacom.Ops.Host.exe'
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $exe -ArgumentList 'servicio' -PassThru -WindowStyle Hidden
    $null = $p.Handle
    $procesos.Add($p.Id)
    $respondio = Salud $puerto $segundos
    $segs = if ($respondio) { [math]::Round($reloj.Elapsed.TotalSeconds, 1) } else { -1 }
    return @{ Proceso = $p; Segundos = $segs; Puerto = $puerto }
}

function Detener($servicio) {
    $hijos = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($servicio.Proceso.Id)" -ErrorAction SilentlyContinue)
    Stop-Process -Id $servicio.Proceso.Id -Force -ErrorAction SilentlyContinue
    foreach ($h in $hijos) { $v = Get-Process -Id $h.ProcessId -ErrorAction SilentlyContinue; if ($v -and -not $v.WaitForExit(25000)) { Stop-Process -Id $h.ProcessId -Force -ErrorAction SilentlyContinue } }
}

function Armar-Instalacion([string] $nombre, [string] $hostExe, [bool] $cifrada, [string] $archivoK) {
    $inst = Join-Path $temp $nombre
    New-Item -ItemType Directory -Force (Join-Path $inst 'Runtime') | Out-Null
    Copy-Item $hostExe (Join-Path $inst 'Runtime\Avacom.Ops.Host.exe')
    if ($modoPaquete) { Copy-Item (Join-Path $staging 'Runtime\avacom_ops_backend.py'), (Join-Path $staging 'Runtime\avacom_boot.py') (Join-Path $inst 'Runtime') }
    else { Copy-Item (Join-Path $raiz 'installer\src\payload\avacom_ops_backend.py'), (Join-Path $raiz 'installer\src\payload\avacom_boot.py') (Join-Path $inst 'Runtime') }
    New-Item -ItemType Junction -Path (Join-Path $inst 'Runtime\Python') -Target (Join-Path $staging 'Runtime\Python') | Out-Null
    Copy-Item (Join-Path $staging 'manifiesto.json') $inst
    $null = robocopy (Join-Path $staging 'Backend') (Join-Path $inst 'Backend') /E /NFL /NDL /NJH /NJS /NP
    if ($cifrada -and -not $modoPaquete) {
        $r = & $pyRuntime -I (Join-Path $raiz 'installer\build\Cifrar-Backend.py') --backend (Join-Path $inst 'Backend') --escribir-clave $archivoK --eliminar-fuentes --exigir-cero-py
        if ($LASTEXITCODE -ne 0) { throw "No se pudo cifrar el backend: $r" }
        Write-Host "  $r"
    }
    return $inst
}

try {
    if ($modoPaquete) {
        Write-Host '==> 1  El PAQUETE del build: su Host, su codigo cifrado y su llave K de custodia; privada de la llave de sello de prueba'
        $hostExe = Join-Path $staging 'Runtime\Avacom.Ops.Host.exe'
        if (-not (Test-Path $hostExe)) { throw "El paquete no trae $hostExe." }
        $archivoK = (Resolve-Path -LiteralPath $ClaveDelPaquete).Path
        $llaves = ''
    } else {
        Write-Host '==> 1  Llave de sello de ENSAYO, Host con su llave publica y el backend cifrado'
        $llaves = Join-Path $temp 'llaves'
        $r = Estacion @('claves', 'generar', '--kid', 'sello-ensayo', '--salida', $llaves)
        if ($r.Codigo -ne 0) { throw "No se pudo generar la llave: $($r.Texto)" }
        $publica = (Select-String -Path (Join-Path $llaves 'sello-ensayo.pub') -Pattern '^publica=(.*)$').Matches[0].Groups[1].Value
        $salidaHost = Join-Path $temp 'host'
        & dotnet publish (Join-Path $raiz 'installer\src\host\Avacom.Ops.Host.csproj') -c Release -nologo -v q "-p:ClavesDeSello=sello-ensayo:$publica" "-p:PublishDir=$salidaHost\" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo publicar el Host.' }
        $hostExe = Join-Path $salidaHost 'Avacom.Ops.Host.exe'
        $archivoK = Join-Path $temp 'custodia\k.hex'
    }
    $instA = Armar-Instalacion 'equipoA' $hostExe $true $archivoK
    $privada = if ($modoPaquete) { (Resolve-Path -LiteralPath $LlaveDeSello).Path } else { Join-Path $llaves 'sello-ensayo.avkey' }
    $registro = Join-Path $temp 'estacion\registro.jsonl'
    $inv = Join-Path $temp 'inventario.json'
    '{"version":1,"lote":"L-ENSAYO","series":{"OPS-ENSAYO-1":{"uefi_id":"AVACOM-OPS-00000001"},"OPS-ENSAYO-2":{"uefi_id":"AVACOM-OPS-00000002"},"OPS-ENSAYO-3":{"uefi_id":"AVACOM-OPS-00000003"}}}' | Set-Content $inv -Encoding ascii
    $sinPy = @(Get-ChildItem (Join-Path $instA 'Backend') -Recurse -File -Filter *.py).Count
    Comprobar 'el Backend instalado no tiene ningun .py' ($sinPy -eq 0) "quedaron $sinPy"
    Comprobar 'el Backend instalado no tiene __pycache__' (-not (Get-ChildItem (Join-Path $instA 'Backend') -Recurse -Directory -Filter __pycache__))
    Comprobar 'codigo.avpkg esta' (Test-Path (Join-Path $instA 'Backend\codigo.avpkg'))

    $datosA = Join-Path $temp 'datosA'; $usbA = Join-Path $temp 'usbA'
    New-Item -ItemType Directory -Force $datosA, $usbA | Out-Null

    Write-Host '==> A  Sin sello el codigo no se abre'
    Comprobar 'probar-liberacion sin sello sale con 40' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 40)
    $sA = Servir $instA $datosA 25
    Comprobar 'el backend NO arranca sin la clave del paquete' ($sA.Segundos -lt 0)
    Detener $sA
    $log = if (Test-Path (Join-Path $datosA 'Logs\dispositivo.log')) { Get-Content (Join-Path $datosA 'Logs\dispositivo.log') -Raw } else { '' }
    Comprobar 'el Host anoto el motivo de la negativa en dispositivo.log' ($log -match 'Liberacion de la clave del paquete [0-9a-f]{16}: dispositivo_sin_sello')

    Write-Host '==> B  Con el sello y la clave del paquete de ESTE equipo'
    $null = Verbo $instA $datosA $usbA @('solicitar-sello', (Join-Path $usbA 'AVACOM'), '--serie', 'OPS-ENSAYO-1')
    $r = Estacion @('sello', 'emitir', '--solicitud', (Join-Path $usbA 'AVACOM\equipo.avsol'), '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbA, '--registro', $registro)
    Comprobar 'la estacion firmo el sello' ($r.Codigo -eq 0) $r.Texto
    $r = Estacion @('clave', 'emitir', '--serie', 'OPS-ENSAYO-1', '--llave-paquete', $archivoK, '--privada', $privada, '--version', 'ensayo', '--salida', $usbA, '--registro', $registro)
    Comprobar 'la estacion envolvio la llave del paquete para este equipo' ($r.Codigo -eq 0) $r.Texto
    Comprobar 'instalar-sello toma el sello y la clave de la memoria' ((Verbo $instA $datosA $usbA @('instalar-sello')) -eq 0)
    Comprobar 'probar-liberacion sale con 0' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 0)
    Comprobar 'preparar (check + migrate con el codigo cifrado) sale con 0' ((Verbo $instA $datosA $usbA @('preparar')) -eq 0) (Get-Content (Join-Path $datosA 'Logs\instalacion.log') -Tail 8 -ErrorAction SilentlyContinue | Out-String)
    $sB = Servir $instA $datosA 120
    Comprobar "el backend cifrado arranca y /health/ responde ($($sB.Segundos) s)" ($sB.Segundos -ge 0) (Get-Content (Join-Path $datosA 'Logs\servicio.log') -Tail 12 -ErrorAction SilentlyContinue | Out-String)
    $tiempoCifrado = $sB.Segundos
    $registroK = ''
    foreach ($f in Get-ChildItem $datosA -Recurse -File -ErrorAction SilentlyContinue) { if ((Select-String -Path $f.FullName -Pattern (Get-Content $archivoK -Raw).Trim() -Quiet -ErrorAction SilentlyContinue)) { $registroK += $f.FullName + ' ' } }
    Comprobar 'la llave K no esta escrita en ningun archivo de datos ni de registros del nodo' ($registroK -eq '') $registroK
    Detener $sB

    Write-Host '==> B2 Sin la identidad UEFI (firmware sin AVACOM_DEVICE_ID) el mismo nodo sellado NO abre su codigo'
    $script:uefiActual = ''
    Comprobar 'probar-liberacion sin la variable UEFI sale con 47' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 47)
    $sU = Servir $instA $datosA 25
    Comprobar 'el backend NO arranca si el firmware no trae AVACOM_DEVICE_ID' ($sU.Segundos -lt 0)
    Detener $sU
    $script:uefiActual = 'AVACOM-OPS-00000009'
    Comprobar 'ni con un identificador UEFI distinto al que el sello autoriza' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 47)
    $script:uefiActual = 'AVACOM-OPS-00000001'
    Comprobar 'con la identidad de vuelta, se libera otra vez' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 0)

    Write-Host '==> C  La instalacion y los datos copiados a OTRO equipo'
    $instC = Join-Path $temp 'equipoC'; $datosC = Join-Path $temp 'datosC'
    $null = robocopy $instA $instC /E /NFL /NDL /NJH /NJS /NP /XD Python
    New-Item -ItemType Junction -Path (Join-Path $instC 'Runtime\Python') -Target (Join-Path $staging 'Runtime\Python') -ErrorAction SilentlyContinue | Out-Null
    $null = robocopy $datosA $datosC /E /NFL /NDL /NJH /NJS /NP
    # el «otro equipo» tiene otra carpeta de estado y por tanto OTRAS claves del TPM (el ensayo nombra las claves por la carpeta de datos)
    $codigoC = Verbo $instC $datosC (Join-Path $temp 'usbC') @('probar-liberacion')
    Comprobar 'en un equipo SIN claves de AVACOM, la liberacion se niega (44: no se puede comprobar el equipo)' ($codigoC -eq 44) "salio con $codigoC"
    $null = Verbo $instC $datosC (Join-Path $temp 'usbC') @('solicitar-sello', (Join-Path $temp 'usbC\AVACOM'), '--serie', 'OPS-ENSAYO-1')      # ahora es un dispositivo AVACOM LEGITIMO, con SUS claves, que recibio una copia
    $codigoC = Verbo $instC $datosC (Join-Path $temp 'usbC') @('probar-liberacion')
    Comprobar 'en OTRO equipo con sus propias claves, la liberacion se niega (42: el sello es de otro equipo)' ($codigoC -eq 42) "salio con $codigoC"
    $sC = Servir $instC $datosC 25
    Comprobar 'el backend copiado NO arranca en el otro equipo' ($sC.Segundos -lt 0)
    Detener $sC

    Write-Host '==> D  Otro equipo con SU sello pero la clave de OTRO'
    $datosD = Join-Path $temp 'datosD'; $usbD = Join-Path $temp 'usbD'
    New-Item -ItemType Directory -Force $datosD, $usbD | Out-Null
    $script:uefiActual = 'AVACOM-OPS-00000002'
    $null = Verbo $instC $datosD $usbD @('solicitar-sello', (Join-Path $usbD 'AVACOM'), '--serie', 'OPS-ENSAYO-2')
    $r = Estacion @('sello', 'emitir', '--solicitud', (Join-Path $usbD 'AVACOM\equipo.avsol'), '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbD, '--registro', $registro)
    Comprobar 'la estacion firmo el sello del equipo 2' ($r.Codigo -eq 0) $r.Texto
    Copy-Item (Get-ChildItem $usbA -Filter *.avclave | Select-Object -First 1).FullName $usbD       # la clave que era para el equipo 1
    $null = Verbo $instC $datosD $usbD @('instalar-sello')
    Comprobar 'con su sello pero con la clave del paquete de otro equipo, no se libera' ((Verbo $instC $datosD $usbD @('probar-liberacion')) -ne 0)

    Write-Host '==> E  Revocado'
    $null = Verbo $instA $datosA $usbA @('verificar-dispositivo')
    $senal = Get-Content (Join-Path $datosA 'Config\dispositivo.json') -Raw | ConvertFrom-Json
    $r = Estacion @('sello', 'revocar', '--privada', $privada, '--huella', $senal.clave_huella, '--salida', $usbA, '--registro', $registro)
    Comprobar 'la estacion emitio la lista de revocados' ($r.Codigo -eq 0) $r.Texto
    $null = Verbo $instA $datosA $usbA @('instalar-sello', (Join-Path $usbA 'revocados-0001.avrev'))
    Comprobar 'un equipo revocado ya no libera la clave (43)' ((Verbo $instA $datosA $usbA @('probar-liberacion')) -eq 43)

    Write-Host '==> F  codigo.avpkg alterado'
    $datosF = Join-Path $temp 'datosF'
    $null = robocopy $datosA $datosF /E /NFL /NDL /NJH /NJS /NP /XF revocados.avrev
    $instF = Join-Path $temp 'equipoF'
    $null = robocopy $instA $instF /E /NFL /NDL /NJH /NJS /NP /XD Python
    New-Item -ItemType Junction -Path (Join-Path $instF 'Runtime\Python') -Target (Join-Path $staging 'Runtime\Python') -ErrorAction SilentlyContinue | Out-Null
    # las claves del TPM de ensayo se nombran por la carpeta de datos: se reusa la de A (el equipo es el mismo) con el paquete alterado
    $bytes = [IO.File]::ReadAllBytes((Join-Path $instF 'Backend\codigo.avpkg')); $bytes[$bytes.Length - 5] = $bytes[$bytes.Length - 5] -bxor 1
    [IO.File]::WriteAllBytes((Join-Path $instF 'Backend\codigo.avpkg'), $bytes)
    Remove-Item (Join-Path $datosA 'Config\sello\revocados.avrev') -ErrorAction SilentlyContinue
    $sF = Servir $instF $datosA 120
    # el ultimo modulo del paquete se abre solo cuando se importa: con un byte cambiado en los datos, el nodo debe fallar al usarlo o antes; el arranque completo importa casi todo
    Comprobar 'con un byte cambiado en codigo.avpkg el backend NO arranca (se detecta al abrir)' ($sF.Segundos -lt 0)
    Detener $sF

    if ($modoPaquete) {
        Write-Host "==> G  Arranque del paquete cifrado: $tiempoCifrado s hasta /health/ (no hay backend plano con que compararlo: el build ya lo cifro)"
    } else {
        Write-Host '==> G  Arranque: el mismo backend plano y cifrado'
        $instP = Armar-Instalacion 'equipoPlano' $hostExe $false ''
        $datosP = Join-Path $temp 'datosP'
        New-Item -ItemType Directory -Force $datosP | Out-Null
        $usbP = Join-Path $temp 'usbP'
        New-Item -ItemType Directory -Force $usbP | Out-Null
        # El Host compilado con llaves de sello tambien guarda la puerta del SERVICIO: un nodo plano (sin cifrar) tambien exige identidad UEFI y sello. Este equipo tiene los suyos.
        $script:uefiActual = 'AVACOM-OPS-00000003'
        $null = Verbo $instP $datosP $usbP @('solicitar-sello', (Join-Path $usbP 'AVACOM'), '--serie', 'OPS-ENSAYO-3')
        $r = Estacion @('sello', 'emitir', '--solicitud', (Join-Path $usbP 'AVACOM\equipo.avsol'), '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbP, '--registro', $registro)
        Comprobar 'la estacion firmo el sello del equipo plano' ($r.Codigo -eq 0) $r.Texto
        $null = Verbo $instP $datosP $usbP @('instalar-sello')
        $null = Verbo $instP $datosP $usbP @('preparar')
        $sP = Servir $instP $datosP 120
        Comprobar "el backend PLANO arranca ($($sP.Segundos) s)" ($sP.Segundos -ge 0)
        Detener $sP
        Write-Host "  Arranque hasta /health/: plano $($sP.Segundos) s · cifrado $tiempoCifrado s"
    }
}
finally {
    foreach ($id in $procesos) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    foreach ($n in $entornoOriginal.Keys) { [Environment]::SetEnvironmentVariable($n, $entornoOriginal[$n], 'Process') }
    # borra las claves de ensayo del TPM (de usuario, con nombre propio de cada carpeta de datos)
    if (Test-Path variable:hostExe) {
        foreach ($d in @('datosA', 'datosC', 'datosD', 'datosP')) {
            $datos = Join-Path $temp $d
            if ((Test-Path $datos) -and (Test-Path $hostExe)) {
                $env:AVACOM_OPS_ENSAYO = '1'; $env:AVACOM_OPS_DATOS = $datos
                $null = Start-Process -FilePath $hostExe -ArgumentList 'borrar-claves-de-ensayo' -Wait -PassThru -WindowStyle Hidden
            }
        }
    }
    foreach ($j in Get-ChildItem $temp -Recurse -Directory -Filter Python -ErrorAction SilentlyContinue) { if ($j.Attributes -band [IO.FileAttributes]::ReparsePoint) { cmd /c rmdir "`"$($j.FullName)`"" | Out-Null } }
    if ($Conservar) { Write-Host "Carpeta conservada: $temp" } else { Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue }
}
Write-Host ''
Write-Host "Resultado: $bien correctas, $mal con falla."
if ($mal -gt 0) { exit 1 }
exit 0
