<#
.SYNOPSIS
    Pruebas de avacom_lic en C (Fase 4): vectores, harness de mutacion (>= 100 000, semilla fija) y sanitizadores.

.DESCRIPTION
    1. Regenera tests\vectors.h (cada vector se contrasta con `cryptography` antes de emitirse) y build\corpus.bin (licencias validas del emisor de PRUEBAS).
    2. Windows: compila las pruebas junto con las fuentes (no contra la DLL) y las corre
         a) normal  (/W4 /WX /GS)           b) con ASan (/fsanitize=address /MD /Zi)
       cada una con los vectores y con el harness de mutacion.
    3. Android (con -Android): compila para x86_64 (NDK) con -fsanitize=undefined y sin sanitizador, las empuja con adb a /data/local/tmp y las corre en el AVD:
       demuestra la compilacion cruzada y UBSan; NO mide el rendimiento de una tableta ARM real.

    Sale con codigo 1 si algo falla. No instala nada. No toca el backend ni el instalador.
#>
[CmdletBinding()]
param(
    [switch] $Android,
    [long] $Mutaciones = 100000,
    [string] $Python = (Join-Path $PSScriptRoot '..\..\backend\.venv\Scripts\python.exe'),
    [string] $Ndk = (Join-Path $env:LOCALAPPDATA 'Android\Sdk\ndk\30.0.14904198'),
    [string] $Adb = (Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'),
    [string] $Serie = ''
)
$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$build = Join-Path $raiz 'build'
New-Item -ItemType Directory -Force $build | Out-Null
function Fallar([string] $m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

Write-Host '==> Vectores y corpus'
$env:PYTHONIOENCODING = 'utf-8'
& $Python (Join-Path $raiz 'tools\gen_vectors.py'); if ($LASTEXITCODE -ne 0) { Fallar 'gen_vectors.py fallo (un vector no coincide con la implementacion independiente).' }
& $Python (Join-Path $raiz 'tools\gen_corpus.py') (Join-Path $build 'corpus.bin'); if ($LASTEXITCODE -ne 0) { Fallar 'gen_corpus.py fallo.' }
$corpus = Join-Path $build 'corpus.bin'

$fuentes = @((Join-Path $raiz 'tests\test_avl.c'), (Join-Path $raiz 'src\avl.c'), (Join-Path $raiz 'src\avl_win.c'), (Join-Path $raiz 'vendor\monocypher.c'), (Join-Path $raiz 'vendor\monocypher-ed25519.c'))
$inc = @("-I$(Join-Path $raiz 'include')", "-I$(Join-Path $raiz 'vendor')", "-I$(Join-Path $raiz 'tests')")

# ------------------------------------------------------------------------------------------------------------ Windows
$vs = 'C:\Program Files\Microsoft Visual Studio\18\Community'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (Test-Path $vswhere) {
    $h = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
    if ($h -and (Test-Path $h)) { $vs = $h }
}
$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvarsall.bat'
if (-not (Test-Path $vcvars)) { Fallar "No se encontro vcvarsall.bat en '$vs'." }
foreach ($l in (& cmd.exe /c "`"$vcvars`" x64 >nul 2>&1 && set")) { if ($l -match '^([^=]+)=(.*)$') { Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2] } }

function Correr([string] $exe, [string] $nombre) {
    Write-Host "  -- $nombre : vectores y casos de borde"
    & $exe | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "$nombre : las pruebas fallaron" }
    Write-Host "  -- $nombre : harness de mutacion ($Mutaciones)"
    $t = [Diagnostics.Stopwatch]::StartNew()
    & $exe --mutate $corpus $Mutaciones | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "$nombre : el harness de mutacion fallo (una mutacion fue aceptada o el corpus no valio)" }
    Write-Host ("     {0:N1} s" -f $t.Elapsed.TotalSeconds)
    Write-Host "  -- $nombre : cuerpos re-firmados ($Mutaciones)"
    & $exe --shape $corpus $Mutaciones | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallar "$nombre : el harness de cuerpos re-firmados fallo (invariante roto o fallo de memoria)" }
}

Write-Host '==> Windows (normal)'
$dirN = Join-Path $build 'test-win'; New-Item -ItemType Directory -Force $dirN | Out-Null
& cl.exe /nologo /std:c11 /O2 /W4 /WX /GS /guard:cf /sdl /MT /utf-8 /D_CRT_SECURE_NO_WARNINGS @($inc | ForEach-Object { $_ -replace '^-I', '/I' }) @fuentes "/Fo$dirN\" "/Fe$dirN\test_avl.exe" /link /INCREMENTAL:NO | Out-Null
if ($LASTEXITCODE -ne 0) {
    # Monocypher compila con /W3 sin /WX (ver Build-Native.ps1, D-31): se reintenta separando las fuentes de terceros.
    $objs = @()
    foreach ($f in $fuentes) {
        $esVendor = $f -like '*\vendor\*'
        $flags = @(if ($esVendor) { '/W3' } else { '/W4'; '/WX' })
        & cl.exe /nologo /std:c11 /O2 @flags /GS /guard:cf /sdl /MT /utf-8 /D_CRT_SECURE_NO_WARNINGS @($inc | ForEach-Object { $_ -replace '^-I', '/I' }) /c $f "/Fo$dirN\" | Out-Null
        if ($LASTEXITCODE -ne 0) { Fallar "cl fallo con $f" }
        $objs += Join-Path $dirN (([IO.Path]::GetFileNameWithoutExtension($f)) + '.obj')
    }
    & link.exe /nologo /INCREMENTAL:NO "/OUT:$dirN\test_avl.exe" @objs advapi32.lib | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallar 'link fallo.' }
}
Correr (Join-Path $dirN 'test_avl.exe') 'win-x64'

Write-Host '==> Windows con AddressSanitizer'
$dirA = Join-Path $build 'test-win-asan'; New-Item -ItemType Directory -Force $dirA | Out-Null
$objs = @()
foreach ($f in $fuentes) {
    & cl.exe /nologo /std:c11 /Od /Zi /W3 /fsanitize=address /MD /utf-8 /D_CRT_SECURE_NO_WARNINGS @($inc | ForEach-Object { $_ -replace '^-I', '/I' }) /c $f "/Fo$dirA\" "/Fd$dirA\vc.pdb" | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallar "cl /fsanitize=address fallo con $f" }
    $objs += Join-Path $dirA (([IO.Path]::GetFileNameWithoutExtension($f)) + '.obj')
}
& link.exe /nologo /INCREMENTAL:NO /DEBUG "/OUT:$dirA\test_avl.exe" @objs advapi32.lib | Out-Null
if ($LASTEXITCODE -ne 0) { Fallar 'link con ASan fallo.' }
Correr (Join-Path $dirA 'test_avl.exe') 'win-x64 + ASan'

# ------------------------------------------------------------------------------------------------------------ Android (AVD)
if ($Android) {
    Write-Host '==> Android x86_64 (NDK) en el AVD'
    $llvm = Join-Path $Ndk 'toolchains\llvm\prebuilt\windows-x86_64'
    $clang = Join-Path $llvm 'bin\clang.exe'
    $dirD = Join-Path $build 'test-android'; New-Item -ItemType Directory -Force $dirD | Out-Null
    $comunes = @('--target=x86_64-linux-android30', '-std=c11', '-O1', '-g', '-fPIE', '-pie', '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2', '-Wall', '-Wextra', '-Wl,-z,relro,-z,now') + $inc
    & $clang @comunes @fuentes '-o' (Join-Path $dirD 'test_avl') ; if ($LASTEXITCODE -ne 0) { Fallar 'clang fallo (sin sanitizador).' }
    & $clang @comunes '-fsanitize=undefined' '-fno-sanitize-recover=all' @fuentes '-o' (Join-Path $dirD 'test_avl_ubsan'); if ($LASTEXITCODE -ne 0) { Fallar 'clang fallo (UBSan).' }
    $rt = Get-ChildItem (Join-Path $llvm 'lib\clang') -Recurse -Filter 'libclang_rt.ubsan_standalone-x86_64-android.so' | Select-Object -First 1
    if (-not $rt) { Fallar 'No se encontro libclang_rt.ubsan_standalone-x86_64-android.so en el NDK.' }
    $ErrorActionPreference = 'Continue'      # adb escribe su progreso por stderr: no es un error
    $adbArgs = @(if ($Serie) { '-s'; $Serie })
    & $Adb @adbArgs wait-for-device | Out-Null
    $remoto = '/data/local/tmp/avl'
    & $Adb @adbArgs shell "rm -rf $remoto && mkdir -p $remoto" | Out-Null
    foreach ($f in @((Join-Path $dirD 'test_avl'), (Join-Path $dirD 'test_avl_ubsan'), $rt.FullName, $corpus)) { & $Adb @adbArgs push $f "$remoto/" | Out-Null }
    & $Adb @adbArgs shell "chmod 755 $remoto/test_avl $remoto/test_avl_ubsan" | Out-Null
    $abi = (& $Adb @adbArgs shell getprop ro.product.cpu.abi).Trim()
    $ver = (& $Adb @adbArgs shell getprop ro.build.version.release).Trim()
    Write-Host "  dispositivo: abi=$abi android=$ver"
    foreach ($par in @(@('test_avl', 'Android x86_64'), @('test_avl_ubsan', 'Android x86_64 + UBSan'))) {
        $exe = $par[0]; $nombre = $par[1]
        Write-Host "  -- $nombre : vectores y casos de borde"
        $salida = & $Adb @adbArgs shell "cd $remoto && LD_LIBRARY_PATH=$remoto ./$exe; echo EXIT=`$?"
        $salida | Out-Host
        if (($salida | Select-Object -Last 1) -notmatch 'EXIT=0') { Fallar "$nombre : las pruebas fallaron" }
        Write-Host "  -- $nombre : harness de mutacion ($Mutaciones)"
        $salida = & $Adb @adbArgs shell "cd $remoto && LD_LIBRARY_PATH=$remoto ./$exe --mutate corpus.bin $Mutaciones; echo EXIT=`$?"
        $salida | Out-Host
        if (($salida | Select-Object -Last 1) -notmatch 'EXIT=0') { Fallar "$nombre : el harness de mutacion fallo" }
        Write-Host "  -- $nombre : cuerpos re-firmados ($Mutaciones)"
        $salida = & $Adb @adbArgs shell "cd $remoto && LD_LIBRARY_PATH=$remoto ./$exe --shape corpus.bin $Mutaciones; echo EXIT=`$?"
        $salida | Out-Host
        if (($salida | Select-Object -Last 1) -notmatch 'EXIT=0') { Fallar "$nombre : el harness de cuerpos re-firmados fallo" }
    }
}
Write-Host 'Pruebas en C: todo correcto.' -ForegroundColor Green
