@echo off
rem AVACOM Emisor de Licencias - MODO GUIADO (haz doble clic).
rem Uso interno de AVACOM. Sin red. La llave privada nunca sale de su memoria USB.
chcp 65001 >nul
setlocal
set "RAIZ=%~dp0"
set "PY=python"
if exist "%RAIZ%python\python.exe" set "PY=%RAIZ%python\python.exe"
"%PY%" "%RAIZ%iniciar.py"
echo.
pause
endlocal
