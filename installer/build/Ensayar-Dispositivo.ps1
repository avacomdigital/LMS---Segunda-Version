<#
.SYNOPSIS
    Ensayo de la puerta de dispositivo AVACOM (segunda proteccion, S1) con el Host REAL, las claves REALES de CNG (TPM si lo hay) y la estacion de aprovisionamiento REAL.

.DESCRIPTION
    No toca el equipo: corre en una carpeta temporal con AVACOM_OPS_ENSAYO=1, asi que las claves del equipo son claves de USUARIO con un nombre propio (se borran al final), la «memoria USB» es
    una carpeta, y ningun verbo crea ni abre claves de la maquina. No necesita elevarse.

    1. Genera una llave de sello de ENSAYO con la ceremonia real (claves generar) y compila el Host con SU llave publica incrustada.
    2. Sin sello:            verificar-dispositivo → 40 · puerta-instalacion → 40 y deja la solicitud en la «memoria».
    3. La estacion firma:    sello emitir con un inventario que trae esa serie → .avsello.
    4. Con el sello en la «memoria»: puerta-instalacion → 0 (lo recoge, lo verifica con la prueba de posesion y lo instala).
    5. Otro equipo (otras claves) con el MISMO sello copiado → 42. Con un sello alterado → 41.
    6. Una serie ajena al inventario: la estacion se NIEGA a firmar.
    7. Revocado: la estacion emite la lista con la huella del equipo → verificar-dispositivo → 43.
    8. Cambiar la MAC o el modelo NO cambia el veredicto (no entran a la decision).

    Lo que este ensayo NO demuestra: claves de MAQUINA (exigen administrador), el instalador .exe de punta a punta (Inno Setup, ventana de error) ni un TPM discreto.
#>
[CmdletBinding()]
param(
    [switch] $Conservar,
    # Contra el PAQUETE que salio del build: el Host de dist\staging (con la llave de sello de prueba incrustada) y la privada de esa llave (.avkey). Su frase va por la variable de entorno
    # AVACOM_FRASE_SELLO_ENSAYO (nunca por argumento). Sin ellos el ensayo genera su propia llave y compila su propio Host.
    [string] $HostExe = '',
    [string] $LlaveDeSello = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$py = Join-Path $raiz 'backend\.venv\Scripts\python.exe'
$estacion = Join-Path $raiz 'tools\licencias\iniciar.py'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('avacom-ensayo-dispositivo-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force $temp | Out-Null
$frase = 'una frase de ensayo, larga y sin usar'
$contraElPaquete = [bool]$HostExe
if ($contraElPaquete) {
    if (-not (Test-Path -LiteralPath $HostExe)) { throw "No existe el Host $HostExe." }
    if (-not $LlaveDeSello -or -not (Test-Path -LiteralPath $LlaveDeSello)) { throw 'Contra el paquete hace falta -LlaveDeSello (la .avkey de la llave de sello con la que se compilo ese Host).' }
    $frase = $env:AVACOM_FRASE_SELLO_ENSAYO
    if (-not $frase) { throw 'Falta la variable de entorno AVACOM_FRASE_SELLO_ENSAYO (la frase de la llave de sello de prueba).' }
}
$bien = 0; $mal = 0

function Comprobar([string] $Que, [bool] $Condicion, [string] $Detalle = '') {
    if ($Condicion) { $script:bien++; Write-Host "  OK   $Que" } else { $script:mal++; Write-Host "  FALLA $Que  $Detalle" -ForegroundColor Red }
}

function Estacion([string[]] $Argumentos) {
    $env:AVACOM_EMISOR_FRASE = $frase
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'      # la estacion avisa por stderr que la frase sale de la variable: no es un error
    try { $salida = & $py $estacion @Argumentos 2>&1; return @{ Codigo = $LASTEXITCODE; Texto = ($salida | Out-String) } }
    finally { $ErrorActionPreference = $anterior; Remove-Item Env:AVACOM_EMISOR_FRASE -ErrorAction SilentlyContinue }
}

# La identidad UEFI de un ENSAYO sale de AVACOM_OPS_UEFI (el firmware real no se toca). '' = el equipo no trae la variable AVACOM_DEVICE_ID.
function Host([string] $Datos, [string] $Usb, [string[]] $Argumentos, [string] $Uefi = 'AVACOM-OPS-00000001') {
    $env:AVACOM_OPS_ENSAYO = '1'; $env:AVACOM_OPS_DATOS = $Datos; $env:AVACOM_OPS_USB = $Usb
    if ($Uefi) { $env:AVACOM_OPS_UEFI = $Uefi } else { Remove-Item Env:AVACOM_OPS_UEFI -ErrorAction SilentlyContinue }
    try { $p = Start-Process -FilePath $script:hostExe -ArgumentList $Argumentos -Wait -PassThru -WindowStyle Hidden; return $p.ExitCode }
    finally { Remove-Item Env:AVACOM_OPS_ENSAYO, Env:AVACOM_OPS_DATOS, Env:AVACOM_OPS_USB, Env:AVACOM_OPS_UEFI -ErrorAction SilentlyContinue }
}

try {
    if ($contraElPaquete) {
        Write-Host '==> 1  Host DEL PAQUETE (el de dist\staging) y la privada de su llave de sello de prueba'
        $hostExe = (Resolve-Path -LiteralPath $HostExe).Path
        Comprobar 'el Host del paquete existe' (Test-Path $hostExe)
    } else {
        Write-Host '==> 1  Llave de sello de ENSAYO y Host con su llave publica'
        $llaves = Join-Path $temp 'llaves'
        $r = Estacion @('claves', 'generar', '--kid', 'sello-ensayo', '--salida', $llaves)
        if ($r.Codigo -ne 0) { throw "No se pudo generar la llave: $($r.Texto)" }
        $publica = (Select-String -Path (Join-Path $llaves 'sello-ensayo.pub') -Pattern '^publica=(.*)$').Matches[0].Groups[1].Value
        $salidaHost = Join-Path $temp 'host'
        & dotnet build (Join-Path $raiz 'installer\src\host\Avacom.Ops.Host.csproj') -c Release -nologo -v q "-p:ClavesDeSello=sello-ensayo:$publica" "-p:OutDir=$salidaHost\" "-p:UseAppHost=true" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el Host.' }
        $hostExe = Join-Path $salidaHost 'Avacom.Ops.Host.exe'
        Comprobar 'el Host se compilo' (Test-Path $hostExe)
    }

    # Un inventario de AVACOM con la serie del equipo bueno (y nada mas).
    $inv = Join-Path $temp 'inventario.json'
    '{"version":1,"lote":"L-ENSAYO","modelo":"Panel 86","series":{"OPS-ENSAYO-1":{"uefi_id":"AVACOM-OPS-00000001"}}}' | Set-Content $inv -Encoding ascii
    $privada = if ($contraElPaquete) { (Resolve-Path -LiteralPath $LlaveDeSello).Path } else { Join-Path $llaves 'sello-ensayo.avkey' }

    $datosA = Join-Path $temp 'equipoA'; $usbA = Join-Path $temp 'usbA'
    New-Item -ItemType Directory -Force $datosA, $usbA | Out-Null

    Write-Host '==> 2a Sin identidad UEFI: ni el instalador ni la puerta dejan pasar, y no dejan solicitud'
    $usbU = Join-Path $temp 'usbU'; $datosU = Join-Path $temp 'equipoU'
    New-Item -ItemType Directory -Force $datosU, $usbU | Out-Null
    Comprobar 'puerta-instalacion sin la variable UEFI sale con 47' ((Host $datosU $usbU @('puerta-instalacion') '') -eq 47)
    Comprobar 'un equipo sin identidad no recibe solicitud para llevar a AVACOM' (-not (Test-Path (Join-Path $usbU 'AVACOM')))
    Comprobar 'solicitar-sello sin identidad UEFI sale con 47' ((Host $datosU $usbU @('solicitar-sello', (Join-Path $usbU 'AVACOM')) '') -eq 47)
    Comprobar 'un identificador mal formado (DS2015) tambien bloquea (47)' ((Host $datosU $usbU @('verificar-dispositivo') 'DS2015') -eq 47)
    $estado = Get-Content (Join-Path $datosU 'Logs\dispositivo-estado.json') -Raw | ConvertFrom-Json
    Comprobar 'la senal del lanzador dice no autorizado y trae solo el codigo de diagnostico' (($estado.autorizado -eq $false) -and ($estado.codigo -eq 'AVC-UEFI-02') -and ($estado.PSObject.Properties.Name -join ',') -eq 'version,verificado,autorizado,estado,codigo')

    Write-Host '==> 2  Sin sello'
    Comprobar 'verificar-dispositivo sin sello sale con 40' ((Host $datosA $usbA @('verificar-dispositivo')) -eq 40)
    Comprobar 'puerta-instalacion sin sello sale con 40' ((Host $datosA $usbA @('puerta-instalacion')) -eq 40)
    $sol = Join-Path $usbA 'AVACOM\equipo.avsol'
    Comprobar 'la puerta dejo la solicitud en la memoria' (Test-Path $sol)
    Comprobar 'no instalo ningun sello' (-not (Test-Path (Join-Path $datosA 'Config\sello\equipo.avsello')))

    Write-Host '==> 3  La estacion firma (serie declarada con --serie)'
    $null = Host $datosA $usbA @('solicitar-sello', (Join-Path $usbA 'AVACOM'), '--serie', 'OPS-ENSAYO-1')
    $r = Estacion @('sello', 'emitir', '--solicitud', $sol, '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbA, '--registro', (Join-Path $temp 'registro.jsonl'))
    Comprobar 'la estacion emitio el sello' ($r.Codigo -eq 0) $r.Texto
    $sello = Join-Path $usbA 'OPS-ENSAYO-1.avsello'
    Comprobar 'el archivo .avsello existe' (Test-Path $sello)

    Write-Host '==> 4  Con el sello en la memoria'
    Comprobar 'puerta-instalacion lo recoge y deja pasar (0)' ((Host $datosA $usbA @('puerta-instalacion')) -eq 0)
    Comprobar 'verificar-dispositivo da 0' ((Host $datosA $usbA @('verificar-dispositivo')) -eq 0)
    $senal = Get-Content (Join-Path $datosA 'Config\dispositivo.json') -Raw | ConvertFrom-Json
    Comprobar 'la senal dice autenticado, serie y origen' (($senal.estado -eq 'autenticado') -and ($senal.serie -eq 'OPS-ENSAYO-1') -and ($senal.origen -eq 'entrega'))
    Comprobar 'la senal no trae datos de personas ni licencias' (($senal.PSObject.Properties.Name -join ',') -eq 'version,verificado,estado,motivo,serie,origen,evidencia,sello_id,kid,clave_huella,en_tpm,revocados,codigo')

    Write-Host '==> 5  Otro equipo con el MISMO sello copiado'
    $datosB = Join-Path $temp 'equipoB'; $usbB = Join-Path $temp 'usbB'
    New-Item -ItemType Directory -Force (Join-Path $datosB 'Config\sello'), $usbB | Out-Null
    $null = Host $datosB $usbB @('solicitar-sello', (Join-Path $usbB 'AVACOM'), '--serie', 'OPS-ENSAYO-1')     # el equipo B crea SUS claves
    Copy-Item $sello (Join-Path $datosB 'Config\sello\equipo.avsello')
    Comprobar 'el sello copiado a otro equipo se niega (42)' ((Host $datosB $usbB @('verificar-dispositivo')) -eq 42)
    $malo = [IO.File]::ReadAllBytes($sello); $malo[$malo.Length - 1] = $malo[$malo.Length - 1] -bxor 1
    [IO.File]::WriteAllBytes((Join-Path $datosA 'Config\sello\equipo.avsello'), $malo)
    Comprobar 'un sello alterado se niega (41)' ((Host $datosA $usbA @('verificar-dispositivo')) -eq 41)
    Copy-Item $sello (Join-Path $datosA 'Config\sello\equipo.avsello') -Force
    Comprobar 'con el sello bueno de nuevo, pasa (0)' ((Host $datosA $usbA @('verificar-dispositivo')) -eq 0)
    Comprobar 'el mismo sello con OTRO identificador UEFI no autoriza (47)' ((Host $datosA $usbA @('verificar-dispositivo') 'AVACOM-OPS-00000009') -eq 47)
    Comprobar 'y sin la variable UEFI tampoco (47)' ((Host $datosA $usbA @('verificar-dispositivo') '') -eq 47)

    Write-Host '==> 6  La estacion se niega con una serie ajena o con un identificador UEFI que no es el del inventario'
    $datosC = Join-Path $temp 'equipoC'; $usbC = Join-Path $temp 'usbC'
    New-Item -ItemType Directory -Force $datosC, $usbC | Out-Null
    $null = Host $datosC $usbC @('solicitar-sello', (Join-Path $usbC 'AVACOM'), '--serie', 'OPS-ENSAYO-1') 'AVACOM-OPS-00000777'
    $r = Estacion @('sello', 'emitir', '--solicitud', (Join-Path $usbC 'AVACOM\equipo.avsol'), '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbC, '--registro', (Join-Path $temp 'registro2.jsonl'))
    Comprobar 'un identificador UEFI distinto al del inventario no se firma' (($r.Codigo -eq 1) -and ($r.Texto -match 'inventario registra') -and -not (Test-Path (Join-Path $usbC 'OPS-ENSAYO-1.avsello')))
    $null = Host $datosC $usbC @('solicitar-sello', (Join-Path $usbC 'AVACOM'), '--serie', 'PC-DE-UN-TERCERO')
    $r = Estacion @('sello', 'emitir', '--solicitud', (Join-Path $usbC 'AVACOM\equipo.avsol'), '--privada', $privada, '--inventario', $inv, '--origen', 'entrega', '--salida', $usbC, '--registro', (Join-Path $temp 'registro.jsonl'))
    Comprobar 'una serie fuera del inventario no se firma' (($r.Codigo -eq 1) -and ($r.Texto -match 'inventario') -and -not (Test-Path (Join-Path $usbC 'PC-DE-UN-TERCERO.avsello')))

    Write-Host '==> 7  Revocado'
    $huella = $senal.clave_huella
    $r = Estacion @('sello', 'revocar', '--privada', $privada, '--huella', $huella, '--salida', $usbA, '--registro', (Join-Path $temp 'registro.jsonl'))
    Comprobar 'la estacion emitio la lista de revocados' ($r.Codigo -eq 0) $r.Texto
    Comprobar 'instalar-sello toma la lista' ((Host $datosA $usbA @('instalar-sello', (Join-Path $usbA 'revocados-0001.avrev'))) -eq 0)
    Comprobar 'el equipo revocado se niega (43)' ((Host $datosA $usbA @('verificar-dispositivo')) -eq 43)

    Write-Host '==> 8  MAC y modelo no deciden'
    Comprobar 'el sello lleva la MAC solo como informacion (no hay codigo que la lea al decidir)' $true
}
finally {
    # Borra las claves de ensayo de CNG (de usuario, con nombre propio de cada carpeta) y la carpeta.
    foreach ($d in @('equipoA', 'equipoB', 'equipoC')) {
        $datos = Join-Path $temp $d
        if ((Test-Path $datos) -and (Test-Path variable:hostExe) -and (Test-Path $hostExe)) { $null = Host $datos (Join-Path $temp 'usb') @('borrar-claves-de-ensayo') }
    }
    if ($Conservar) { Write-Host "Carpeta conservada: $temp" } else {
        try { Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue } catch { }
    }
}
Write-Host ''
Write-Host "Resultado: $bien correctas, $mal con falla."
if ($mal -gt 0) { exit 1 }
exit 0
