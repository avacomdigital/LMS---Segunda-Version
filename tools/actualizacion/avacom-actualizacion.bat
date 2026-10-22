@echo off
rem AVACOM Emisor de Paquetes de Actualizacion - LINEA DE COMANDOS. Ejemplo: avacom-actualizacion emitir --descripcion paquete.json --privada ... --salida ...
rem Uso interno de AVACOM. Sin red. La llave privada nunca sale de su memoria USB.
chcp 65001 >nul
setlocal
set "RAIZ=%~dp0"
set "PY=python"
if exist "%RAIZ%python\python.exe" set "PY=%RAIZ%python\python.exe"
if exist "%RAIZ%..\..\backend\.venv\Scripts\python.exe" set "PY=%RAIZ%..\..\backend\.venv\Scripts\python.exe"
"%PY%" "%RAIZ%iniciar.py" %*
exit /b %ERRORLEVEL%
