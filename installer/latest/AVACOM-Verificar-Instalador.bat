@echo off
rem ============================================================================
rem  AVACOM OPS Master - Verificador del instalador
rem
rem  Sirve para revisar, SIN INSTALAR NADA, si este equipo esta listo para el
rem  instalador que hay en esta misma carpeta, y para encontrar posibles errores
rem  antes de tocar el aula. Un toque y nada que escribir.
rem
rem  Que comprueba:
rem    1. Que el instalador esta completo y no esta corrupto (huella SHA256
rem       contra SHA256.txt, que va en esta misma carpeta).
rem    2. Las diez comprobaciones del propio asistente (Windows, 64 bits,
rem       espacio, permisos, puerto 8000, instalacion previa, aplicacion abierta,
rem       dependencias, AVACOM Contenido, red del aula), ejecutadas de verdad
rem       con el modo de volcado /VOLCADO: no se instala nada.
rem    3. El estado de lo ya instalado, si lo hay: version, servicio, puerto
rem       8000, /health/, datos, copias de seguridad y ultimos registros.
rem
rem  No modifica el equipo. Windows pedira permiso de administrador una vez,
rem  porque el asistente lo necesita para poder comprobar los permisos.
rem
rem  Este archivo es solo ASCII a proposito: cmd.exe no lee bien acentos ni BOM.
rem ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title AVACOM OPS Master - Verificador del instalador

set "CARPETA=%~dp0"
set "SALIDA=%TEMP%\avacom-verificar-instalador"
set "VOLCADO=%SALIDA%\diagnostico.txt"
set "PROBLEMAS=0"
set "AVISOS=0"
set "DATOS=%ProgramData%\AVACOM\OPS Master"
set "CLAVE_DESINSTALAR=HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B6D1F0A4-3C57-4E2B-9A18-7F5C2E8D4A31}_is1"

if not exist "%SALIDA%" mkdir "%SALIDA%" >nul 2>&1
del /q "%VOLCADO%" >nul 2>&1

echo.
echo ================================================================
echo   AVACOM OPS Master - Verificador del instalador
echo ================================================================
echo.

rem ---------------------------------------------------------- 1. Instalador
set "INSTALADOR="
for %%F in ("%CARPETA%AVACOM-OPS-Master-Setup-*.exe") do set "INSTALADOR=%%~fF"

echo [1/3] El instalador
if not defined INSTALADOR (
    echo   [ERROR] No hay ningun AVACOM-OPS-Master-Setup-*.exe en esta carpeta:
    echo           %CARPETA%
    echo           Baja el instalador de la release y dejalo junto a este archivo.
    set /a PROBLEMAS+=1
    goto :estado
)
for %%F in ("%INSTALADOR%") do (
    set "NOMBRE=%%~nxF"
    set /a MB=%%~zF / 1048576
)
echo   Archivo : !NOMBRE! ^(!MB! MB^)

if not exist "%CARPETA%SHA256.txt" (
    echo   [AVISO] No esta SHA256.txt junto al instalador: no se puede verificar la descarga.
    set /a AVISOS+=1
) else (
    set "ESPERADA="
    for /f "tokens=2" %%H in ('findstr /B /C:"SHA256" "%CARPETA%SHA256.txt"') do set "ESPERADA=%%H"
    set "REAL="
    for /f "skip=1 tokens=1" %%H in ('certutil -hashfile "%INSTALADOR%" SHA256 2^>nul') do if not defined REAL set "REAL=%%H"
    if not defined REAL (
        echo   [AVISO] No se pudo calcular la huella del instalador ^(certutil no respondio^).
        set /a AVISOS+=1
    ) else if /i "!REAL!"=="!ESPERADA!" (
        echo   [OK] La huella SHA256 coincide con SHA256.txt: la descarga esta completa.
    ) else (
        echo   [ERROR] La huella NO coincide: el archivo esta corrupto o es de otra version.
        echo           Esperada: !ESPERADA!
        echo           Real    : !REAL!
        echo           Vuelve a descargarlo de la release.
        set /a PROBLEMAS+=1
    )
)

rem ------------------------------------------------- 2. Comprobaciones del asistente
echo.
echo [2/3] Las comprobaciones del equipo ^(no se instala nada^)
echo   Windows va a pedir permiso de administrador: tocalo para continuar.
start "" /wait "%INSTALADOR%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART "/VOLCADO=%VOLCADO%"

if not exist "%VOLCADO%" (
    echo   [ERROR] El asistente no llego a ejecutar sus comprobaciones.
    echo           Si cancelaste el permiso de administrador, vuelve a ejecutar este archivo.
    set /a PROBLEMAS+=1
) else (
    for /f "usebackq delims=" %%L in ("%VOLCADO%") do (
        set "LINEA=%%L"
        if /i "!LINEA:~0,7!"=="check: " (
            echo   !LINEA:~7!
        ) else if /i "!LINEA:~0,10!"=="Politica d" (
            echo   !LINEA!
        ) else if /i "!LINEA:~0,10!"=="Version in" (
            echo   !LINEA!
        ) else if /i "!LINEA:~0,10!"=="Datos prev" (
            echo   !LINEA!
        )
    )
    findstr /C:"Resultado: Todo listo" "%VOLCADO%" >nul
    if errorlevel 1 (
        echo.
        echo   [ERROR] El equipo NO esta listo para instalar. Motivo:
        for /f "usebackq tokens=1* delims=:" %%A in (`findstr /B /C:"Resultado:" "%VOLCADO%"`) do echo           %%B
        set /a PROBLEMAS+=1
    ) else (
        echo.
        echo   [OK] Este equipo esta listo para instalar AVACOM OPS Master.
    )
    powershell -NoProfile -Command "if (Select-String -LiteralPath '%VOLCADO%' -Pattern ([string][char]0x26A0) -Quiet) { exit 3 } else { exit 0 }" >nul 2>&1
    if errorlevel 3 (
        echo   [AVISO] Hay comprobaciones en amarillo ^(no bloquean, pero conviene leerlas^).
        set /a AVISOS+=1
    )
)

rem ------------------------------------------------------ 3. Lo ya instalado
:estado
echo.
echo [3/3] Lo que ya hay instalado en este equipo
set "VERSION="
for /f "tokens=2,*" %%A in ('reg query "%CLAVE_DESINSTALAR%" /v DisplayVersion 2^>nul ^| findstr /I "DisplayVersion"') do set "VERSION=%%B"
if defined VERSION (
    echo   Version instalada : !VERSION!
) else (
    echo   Version instalada : ninguna ^(primera instalacion^)
)

sc query AVACOMOPSBackend >nul 2>&1
if errorlevel 1 (
    echo   Servicio          : AVACOMOPSBackend no esta registrado
) else (
    for /f "tokens=3,4" %%A in ('sc query AVACOMOPSBackend ^| findstr /C:"STATE"') do echo   Servicio          : AVACOMOPSBackend ^(%%B^)
    sc qc AVACOMOPSBackend 2>nul | findstr /C:"START_TYPE" | findstr /C:"AUTO_START" >nul
    if errorlevel 1 (
        echo   [AVISO] El servicio no esta en inicio automatico.
        set /a AVISOS+=1
    )
)

set "ESCUCHA="
for /f "tokens=1,2,5" %%A in ('netstat -ano -p tcp ^| findstr /C:":8000 "') do (
    echo %%B | findstr /C:":8000" >nul && set "ESCUCHA=%%B pid %%C"
)
if defined ESCUCHA (
    echo   Puerto 8000       : en uso ^(!ESCUCHA!^)
) else (
    echo   Puerto 8000       : libre
)

where curl >nul 2>&1
if not errorlevel 1 (
    curl -s -m 4 http://127.0.0.1:8000/health/ > "%SALIDA%\health.json" 2>nul
    findstr /C:"avacom-lms-backend" "%SALIDA%\health.json" >nul 2>&1
    if not errorlevel 1 (
        echo   API /health/      : responde ^(avacom-lms-backend^)
        findstr /C:"\"instalado\":false" "%SALIDA%\health.json" >nul 2>&1
        if not errorlevel 1 echo   [AVISO] El nodo todavia no tiene organizacion ni administrador.
    ) else (
        echo   API /health/      : no responde
    )
)

if exist "%DATOS%\Data\ops-master.sqlite3" (
    for %%F in ("%DATOS%\Data\ops-master.sqlite3") do echo   Base de datos     : presente ^(%%~zF bytes^)
) else (
    echo   Base de datos     : no hay
)
if exist "%DATOS%\Config\backend.env" (
    echo   backend.env       : presente ^(va junto con la base: no se copian por separado^)
) else (
    echo   backend.env       : no hay
)
if exist "%DATOS%\Respaldos" (
    set /a COPIAS=0
    for /d %%D in ("%DATOS%\Respaldos\*") do set /a COPIAS+=1
    echo   Copias de seguridad: !COPIAS! en %DATOS%\Respaldos
)
if exist "%ProgramFiles%\AVACOM\OPS Master\Anterior" (
    echo   [AVISO] Hay una carpeta "Anterior" de una actualizacion que no termino:
    echo           %ProgramFiles%\AVACOM\OPS Master\Anterior
    set /a AVISOS+=1
)
if exist "%ProgramData%\AVACOM\content\link.json" (
    echo   AVACOM Contenido  : link.json presente
) else (
    echo   AVACOM Contenido  : sin link.json ^(el aula no tendra cursos hasta abrirlo^)
)

if exist "%DATOS%\Logs\instalacion.log" (
    echo.
    echo   Ultimas lineas del registro de instalacion ^(%DATOS%\Logs\instalacion.log^):
    powershell -NoProfile -Command "Get-Content -LiteralPath '%DATOS%\Logs\instalacion.log' -Tail 8 -Encoding UTF8 | ForEach-Object { '    ' + $_ }" 2>nul
)

rem ------------------------------------------------------------- Veredicto
echo.
echo ================================================================
if %PROBLEMAS% GTR 0 (
    echo   RESULTADO: hay %PROBLEMAS% problema^(s^). No instales hasta resolverlos.
    set "CODIGO=1"
) else if %AVISOS% GTR 0 (
    echo   RESULTADO: se puede instalar, con %AVISOS% aviso^(s^) que conviene leer.
    set "CODIGO=0"
) else (
    echo   RESULTADO: todo en orden. Se puede instalar.
    set "CODIGO=0"
)
echo ================================================================
echo.
echo   El detalle completo quedo en: %VOLCADO%
echo.
if /i not "%~1"=="/silencioso" pause
exit /b %CODIGO%
