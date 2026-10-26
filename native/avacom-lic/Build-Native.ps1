<#
.SYNOPSIS
    Compila avacom_lic (MOD-018, Fase 4, P-21): Windows x64 con MSVC de VS 18 y Android arm64-v8a / x86_64 con el NDK 30.0.14904198.

.DESCRIPTION
    Salidas (NO se versionan; dist/ y build/ estan en .gitignore):
      dist\win-x64\avacom_lic.dll
      dist\android-arm64-v8a\libavacom_lic.so
      dist\android-x86_64\libavacom_lic.so
      dist\SHA256.txt        huella de cada binario (para el manifiesto firmado del instalador)

    Banderas (P-21):
      Windows  /W4 /WX /GS /guard:cf /sdl /MT   enlace: /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /CETCOMPAT /guard:cf
      Android  -Wall -Wextra -Wconversion -Werror -fstack-protector-strong -D_FORTIFY_SOURCE=2 -fPIC -fvisibility=hidden
               -Wl,-z,relro,-z,now,-z,noexecstack,-z,max-page-size=16384
      Analisis estatico: MSVC /analyze y clang --analyze del NDK sobre las fuentes propias (no sobre Monocypher).
    Al final llama a Verificar-Banderas.ps1: las banderas se COMPRUEBAN EN EL BINARIO (dumpbin /headers, llvm-readelf), no se dan por buenas.

    No instala nada en el sistema. No toca installer\ ni el backend: el build del instalador copia dist\win-x64\avacom_lic.dll (ver LEEME.md).
#>
[CmdletBinding()]
param(
    [switch] $OmitirAndroid,
    [switch] $OmitirAnalisis,
    [string] $Ndk = (Join-Path $env:LOCALAPPDATA 'Android\Sdk\ndk\30.0.14904198'),
    [int] $Api = 30
)
$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$vendor = Join-Path $raiz 'vendor'
$src = Join-Path $raiz 'src'
$inc = Join-Path $raiz 'include'
$dist = Join-Path $raiz 'dist'
$build = Join-Path $raiz 'build'
New-Item -ItemType Directory -Force $dist, $build | Out-Null

function Fallar([string] $m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------------------------------------------------ 1 · entorno de MSVC
function Entrar-A-Msvc {
    $vs = $null
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
    }
    if (-not $vs -or -not (Test-Path $vs)) { $vs = 'C:\Program Files\Microsoft Visual Studio\18\Community' }
    $vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvarsall.bat'
    if (-not (Test-Path $vcvars)) { Fallar "No se encontro vcvarsall.bat en '$vs'." }
    Write-Host "  MSVC: $vs"
    $lineas = & cmd.exe /c "`"$vcvars`" x64 >nul 2>&1 && set"
    foreach ($l in $lineas) {
        if ($l -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] }
    }
    if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) { Fallar 'vcvarsall no dejo cl.exe en el PATH.' }
}

Write-Host '==> 1/4  Windows x64 (MSVC)'
Entrar-A-Msvc
$fuentesPropias = @((Join-Path $src 'avl.c'), (Join-Path $src 'avl_win.c'))
$fuentesVendor = @((Join-Path $vendor 'monocypher.c'), (Join-Path $vendor 'monocypher-ed25519.c'))
$objWin = Join-Path $build 'win-x64'
New-Item -ItemType Directory -Force $objWin | Out-Null
$comunes = @('/nologo', '/std:c11', '/O2', '/Gy', '/Gw', '/GS', '/guard:cf', '/sdl', '/MT', '/DNDEBUG', "/I$inc", "/I$vendor", '/utf-8')

$objetos = @()
foreach ($f in $fuentesPropias) {
    & cl.exe @comunes '/W4' '/WX' '/c' $f "/Fo$objWin\" | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "cl fallo con $f" }
    $objetos += Join-Path $objWin (([IO.Path]::GetFileNameWithoutExtension($f)) + '.obj')
}
foreach ($f in $fuentesVendor) {
    # Monocypher se compila con las MISMAS banderas de seguridad y sus fuentes NO se modifican, pero con /W3 sin /WX: /W4 marca una conversion de 64 a 32 bits
    # intencionada de upstream (C4244 en monocypher.c). D-31: el rigor total es para el codigo propio.
    & cl.exe @comunes '/W3' '/c' $f "/Fo$objWin\" | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "cl fallo con $f" }
    $objetos += Join-Path $objWin (([IO.Path]::GetFileNameWithoutExtension($f)) + '.obj')
}
$destinoWin = Join-Path $dist 'win-x64'
New-Item -ItemType Directory -Force $destinoWin | Out-Null
& link.exe /nologo /DLL "/OUT:$destinoWin\avacom_lic.dll" "/IMPLIB:$objWin\avacom_lic.lib" "/PDB:$objWin\avacom_lic.pdb" /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /CETCOMPAT /guard:cf /OPT:REF /OPT:ICF /INCREMENTAL:NO /MACHINE:X64 /WX @objetos advapi32.lib | Out-Host
if ($LASTEXITCODE -ne 0) { Fallar 'link fallo.' }
Write-Host "  -> $destinoWin\avacom_lic.dll ($((Get-Item "$destinoWin\avacom_lic.dll").Length) bytes)"

if (-not $OmitirAnalisis) {
    Write-Host '  /analyze (fuentes propias, advertencias como error)'
    $salidaAnalisis = Join-Path $build 'analyze-msvc.txt'
    $objAn = Join-Path $build 'analyze-obj'
    New-Item -ItemType Directory -Force $objAn | Out-Null
    $texto = @()
    foreach ($f in $fuentesPropias) {
        $texto += & cl.exe /nologo /std:c11 /analyze /analyze:stacksize 131072 /W4 /WX /c /utf-8 "/I$inc" "/I$vendor" $f "/Fo$objAn\" 2>&1
        if ($LASTEXITCODE -ne 0) { $texto | Set-Content -Encoding utf8 $salidaAnalisis; $texto | Out-Host; Fallar "/analyze reporto problemas en $f" }
    }
    $texto | Set-Content -Encoding utf8 $salidaAnalisis
    Write-Host "  /analyze limpio (informe en build\analyze-msvc.txt)"
}

# ------------------------------------------------------------------------------------------------------------ 2 · Android
if ($OmitirAndroid) {
    Write-Host '==> 2/4  Android OMITIDO por parametro'
} else {
    Write-Host '==> 2/4  Android (NDK)'
    $llvm = Join-Path $Ndk 'toolchains\llvm\prebuilt\windows-x86_64'
    $clang = Join-Path $llvm 'bin\clang.exe'
    if (-not (Test-Path $clang)) { Fallar "No se encontro clang del NDK en '$llvm'." }
    $objetivos = @(
        @{ abi = 'arm64-v8a'; triple = "aarch64-linux-android$Api" },
        @{ abi = 'x86_64';    triple = "x86_64-linux-android$Api" }
    )
    $banderasAndroid = @('-O2', '-std=c11', '-fPIC', '-fvisibility=hidden', '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2', '-DNDEBUG', '-ffunction-sections', '-fdata-sections',
                         "-I$inc", "-I$vendor")
    foreach ($o in $objetivos) {
        $dir = Join-Path $dist "android-$($o.abi)"
        New-Item -ItemType Directory -Force $dir | Out-Null
        $objs = Join-Path $build "android-$($o.abi)"
        New-Item -ItemType Directory -Force $objs | Out-Null
        $lista = @()
        foreach ($f in $fuentesPropias) {
            $obj = Join-Path $objs (([IO.Path]::GetFileNameWithoutExtension($f)) + '.o')
            & $clang "--target=$($o.triple)" @banderasAndroid '-Wall' '-Wextra' '-Wconversion' '-Werror' '-c' $f '-o' $obj
            if ($LASTEXITCODE -ne 0) { Fallar "clang fallo con $f ($($o.abi))" }
            $lista += $obj
        }
        foreach ($f in $fuentesVendor) {
            $obj = Join-Path $objs (([IO.Path]::GetFileNameWithoutExtension($f)) + '.o')
            & $clang "--target=$($o.triple)" @banderasAndroid '-Wall' '-Wextra' '-Werror' '-c' $f '-o' $obj
            if ($LASTEXITCODE -ne 0) { Fallar "clang fallo con $f ($($o.abi))" }
            $lista += $obj
        }
        & $clang "--target=$($o.triple)" '-shared' '-fPIC' '-Wl,-z,relro,-z,now,-z,noexecstack,-z,max-page-size=16384,--gc-sections,--build-id=sha1' '-o' (Join-Path $dir 'libavacom_lic.so') @lista
        if ($LASTEXITCODE -ne 0) { Fallar "enlace fallo ($($o.abi))" }
        Write-Host "  -> $dir\libavacom_lic.so ($((Get-Item "$dir\libavacom_lic.so").Length) bytes)"
        if (-not $OmitirAnalisis -and $o.abi -eq 'x86_64') {
            Write-Host '  clang --analyze (fuentes propias)'
            foreach ($f in $fuentesPropias) {
                $r = & $clang "--target=$($o.triple)" '--analyze' '-Xanalyzer' '-analyzer-werror' '-std=c11' "-I$inc" "-I$vendor" $f '-o' (Join-Path $build 'analyze-clang.plist') 2>&1
                if ($LASTEXITCODE -ne 0) { $r | Out-Host; Fallar "clang --analyze reporto problemas en $f" }
                if ($r) { $r | Out-Host; Fallar "clang --analyze emitio advertencias en $f" }
            }
            Write-Host '  clang --analyze limpio'
        }
    }
}

# ------------------------------------------------------------------------------------------------------------ 3 · huellas
Write-Host '==> 3/4  Huellas'
$lineas = foreach ($b in (Get-ChildItem $dist -Recurse -File | Where-Object { $_.Name -in 'avacom_lic.dll', 'libavacom_lic.so' })) {
    '{0}  {1}' -f (Get-FileHash $b.FullName -Algorithm SHA256).Hash.ToLower(), ($b.FullName.Substring($dist.Length + 1) -replace '\\', '/')
}
$lineas | Set-Content -Encoding ascii (Join-Path $dist 'SHA256.txt')
$lineas | Out-Host

# ------------------------------------------------------------------------------------------------------------ 4 · banderas en el binario
Write-Host '==> 4/4  Banderas de endurecimiento EN EL BINARIO'
& (Join-Path $raiz 'Verificar-Banderas.ps1') -Ndk $Ndk -OmitirAndroid:$OmitirAndroid
if ($LASTEXITCODE -ne 0) { Fallar 'Las banderas de endurecimiento no estan en el binario.' }
Write-Host 'Biblioteca nativa lista.' -ForegroundColor Green
