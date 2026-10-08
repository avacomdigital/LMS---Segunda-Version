@echo off
rem ============================================================================
rem  AVACOM Student - servidor local del APK para instalar las tabletas sin cable
rem
rem  Tocar este archivo hace todo:
rem    1. Pide el permiso de administrador UNA vez (para abrir el puerto en el firewall
rem       solo para la red local y solo mientras el servidor este encendido).
rem    2. Enciende el servidor y abre en ESTE equipo el panel con el codigo QR.
rem    3. Cuenta cuantas tabletas ya descargaron el APK (por defecto, 55).
rem    4. Al detenerlo (boton "Detener el servidor" del panel, o cerrar esta ventana)
rem       cierra el puerto otra vez.
rem
rem  Uso:  Servir-APK.bat                  puerto 8080, 55 tabletas
rem        Servir-APK.bat 8081 30          otro puerto y otra cantidad de tabletas
rem
rem  Python: usa el de la carpeta "python" que esta junto a este archivo; si no hay,
rem  el de AVACOM OPS Master; si no, el del equipo (Python 3.8 o mas nuevo).
rem  Este archivo esta escrito sin tildes a proposito: la consola de Windows no
rem  siempre las muestra bien.
rem ============================================================================
setlocal EnableExtensions
title AVACOM Student - servidor local del APK
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PUERTO=8080"
set "TABLETAS=55"
if not "%~1"=="" set "PUERTO=%~1"
if not "%~2"=="" set "TABLETAS=%~2"
set "AQUI=%~dp0"
set "REGLA=AVACOM Student APK (temporal)"

rem --- 1. Permiso de administrador (una sola vez). Sin el, el servidor igual arranca,
rem        pero Windows puede bloquear a las tabletas hasta que se abra el puerto.
fltmc >nul 2>&1
if errorlevel 1 (
    if /i not "%~3"=="elevado" (
        echo Pidiendo el permiso de administrador para abrir el puerto %PUERTO% mientras el servidor este encendido...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath '%~f0' -ArgumentList '%PUERTO% %TABLETAS% elevado' -Verb RunAs -ErrorAction Stop; exit 0 } catch { exit 1 }" >nul 2>&1
        if not errorlevel 1 exit /b 0
        echo.
        echo No se dio el permiso: el servidor arranca igual, pero sin abrir el puerto en el firewall.
        echo Si las tabletas no llegan, cierra esta ventana y vuelve a tocar este archivo aceptando el permiso.
        echo.
    )
)

rem --- 2. Un Python que funcione de verdad (el "python" de la Tienda de Windows existe aunque no haya Python).
set "PYEXE="
set "PYARG="
call :probar "%AQUI%python\python.exe" ""
call :probar "%ProgramFiles%\AVACOM\OPS Master\Runtime\Python\python.exe" ""
call :probar "py" "-3"
call :probar "python" ""
if not defined PYEXE goto sinpython

echo AVACOM Student - servidor local del APK
echo Python: %PYEXE% %PYARG%
echo.

rem --- 3. El servidor. Se queda aqui hasta que se detiene.
"%PYEXE%" %PYARG% "%AQUI%Servir-APK.py" --puerto %PUERTO% --tabletas %TABLETAS% --abrir
set "CODIGO=%ERRORLEVEL%"

rem --- 4. Por si algo impidio que el propio servidor cerrara el puerto: la regla temporal no se queda abierta.
netsh advfirewall firewall delete rule name="%REGLA%" >nul 2>&1

if not "%CODIGO%"=="0" goto conerror
echo.
echo Esta ventana se cierra sola en 20 segundos.
timeout /t 20 >nul 2>&1
exit /b 0

:conerror
echo.
echo El servidor termino con un error, codigo %CODIGO%. Lee los mensajes de arriba.
pause
exit /b %CODIGO%

:probar
rem  %~1 = ejecutable (ruta o nombre)   %~2 = argumento extra (por ejemplo -3 para el lanzador py)
if defined PYEXE exit /b 0
"%~1" %~2 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYEXE=%~1"
    set "PYARG=%~2"
)
exit /b 0

:sinpython
echo.
echo No se encontro Python en este equipo. Opciones (basta una):
echo   - Copia aqui, junto a este archivo, la carpeta "python" que viene con el APK.
echo   - Instala AVACOM OPS Master en este equipo (trae su propio Python).
echo   - Instala Python 3:  winget install Python.Python.3.12
echo.
pause
exit /b 1
