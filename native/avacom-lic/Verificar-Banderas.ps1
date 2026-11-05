<#
.SYNOPSIS
    Comprueba EN EL BINARIO (no en la linea de comandos) que avacom_lic trae las banderas de endurecimiento de P-21.
    Windows: dumpbin /headers /loadconfig /exports. Android: llvm-readelf. Sale con codigo 1 si falta alguna.
#>
[CmdletBinding()]
param(
    [switch] $OmitirAndroid,
    [string] $Ndk = (Join-Path $env:LOCALAPPDATA 'Android\Sdk\ndk\30.0.14904198')
)
$ErrorActionPreference = 'Stop'
$dist = Join-Path $PSScriptRoot 'dist'
$fallos = 0
function Comprobar([string] $nombre, [bool] $ok, [string] $detalle = '') {
    if ($ok) { Write-Host ("  [ok]     {0}" -f $nombre) }
    else { Write-Host ("  [FALLA]  {0} {1}" -f $nombre, $detalle) -ForegroundColor Red; $script:fallos++ }
}

# ------------------------------------------------------------------------------------------------------ Windows
$dll = Join-Path $dist 'win-x64\avacom_lic.dll'
if (-not (Test-Path $dll)) { Write-Host "No existe $dll" -ForegroundColor Red; exit 1 }
$dumpbin = (Get-Command dumpbin.exe -ErrorAction SilentlyContinue).Source
if (-not $dumpbin) {
    $dumpbin = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\dumpbin.exe' -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName
}
if (-not $dumpbin) { Write-Host 'No se encontro dumpbin.exe (entra por vcvarsall).' -ForegroundColor Red; exit 1 }
Write-Host "  avacom_lic.dll (dumpbin: $dumpbin)"
$headers = (& $dumpbin /nologo /headers $dll) -join "`n"
$carga = (& $dumpbin /nologo /loadconfig $dll) -join "`n"
$exports = (& $dumpbin /nologo /exports $dll) -join "`n"
$dependencias = (& $dumpbin /nologo /dependents $dll) -join "`n"
Comprobar 'ASLR (Dynamic base)' ($headers -match 'Dynamic base')
Comprobar 'ASLR de 64 bits (High Entropy Virtual Addresses)' ($headers -match 'High Entropy Virtual Addresses')
Comprobar 'DEP (NX compatible)' ($headers -match 'NX compatible')
Comprobar 'CET (CETCOMPAT)' ($headers -match 'CET compatible|CET shadow stack|EH Continuation') 'no aparece CETCOMPAT en la cabecera extendida'
Comprobar 'CFG (Guard / Control Flow Guard)' (($headers -match 'Control Flow Guard|Guard') -and ($carga -match 'Guard CF|CF Instrumented|Guard Flags')) 'la tabla de CFG no esta en el binario'
Comprobar 'Cookie de pila (/GS)' ($carga -match 'Security Cookie')
Comprobar 'Maquina x64' ($headers -match 'x64')
$simbolos = @([regex]::Matches($exports, '(?m)^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)') | ForEach-Object { $_.Groups[1].Value })
Comprobar "Solo exporta avl_* ($($simbolos.Count) simbolos)" (($simbolos.Count -gt 0) -and (@($simbolos | Where-Object { $_ -notlike 'avl_*' }).Count -eq 0)) ($simbolos -join ',')
$dll_deps = @([regex]::Matches($dependencias, '(?mi)^\s+(\S+\.dll)\s*$') | ForEach-Object { $_.Groups[1].Value.ToLower() })
Comprobar "Sin runtime de C aparte (CRT estatico): depende solo de $($dll_deps -join ', ')" (@($dll_deps | Where-Object { $_ -notin 'kernel32.dll', 'advapi32.dll' -and $_ -notlike 'api-ms-win-*' }).Count -eq 0)

# ------------------------------------------------------------------------------------------------------ Android
if (-not $OmitirAndroid) {
    $readelf = Join-Path $Ndk 'toolchains\llvm\prebuilt\windows-x86_64\bin\llvm-readelf.exe'
    foreach ($abi in 'arm64-v8a', 'x86_64') {
        $so = Join-Path $dist "android-$abi\libavacom_lic.so"
        if (-not (Test-Path $so)) { Comprobar "existe $so" $false; continue }
        Write-Host "  libavacom_lic.so ($abi)"
        $prog = (& $readelf -l $so) -join "`n"
        $din = (& $readelf -d $so) -join "`n"
        $sim = (& $readelf --dyn-syms $so) -join "`n"
        Comprobar 'RELRO (GNU_RELRO)' ($prog -match 'GNU_RELRO')
        Comprobar 'BIND_NOW (-z now)' ($din -match 'BIND_NOW|FLAGS_1.*NOW')
        Comprobar 'Pila no ejecutable (GNU_STACK RW)' ($prog -match 'GNU_STACK[^\n]*RW ' -and $prog -notmatch 'GNU_STACK[^\n]*RWE')
        Comprobar 'Sin TEXTREL' ($din -notmatch 'TEXTREL')
        Comprobar 'Pila protegida (importa __stack_chk_fail)' ($sim -match '__stack_chk_fail')
        $alinea = @([regex]::Matches($prog, '(?m)^\s+LOAD\s+.*?(0x[0-9a-f]+)\s*$') | ForEach-Object { $_.Groups[1].Value })
        Comprobar "Segmentos LOAD alineados a 16 KB ($($alinea -join ','))" (($alinea.Count -gt 0) -and (@($alinea | Where-Object { [Convert]::ToInt64($_, 16) -lt 0x4000 }).Count -eq 0))
        $definidos = @([regex]::Matches($sim, '(?m)^\s*\d+:\s+[0-9a-f]+\s+\d+\s+\w+\s+(GLOBAL|WEAK)\s+DEFAULT\s+(?!UND)\S+\s+(\S+)') | ForEach-Object { $_.Groups[2].Value })
        Comprobar "Solo exporta avl_* ($($definidos.Count) simbolos)" (($definidos.Count -gt 0) -and (@($definidos | Where-Object { $_ -notlike 'avl_*' }).Count -eq 0)) ($definidos -join ',')
    }
}
if ($fallos -gt 0) { Write-Host "$fallos comprobacion(es) fallaron." -ForegroundColor Red; exit 1 }
Write-Host 'Todas las banderas estan en el binario.' -ForegroundColor Green
exit 0
