@echo off
rem ===========================================================================
rem  Sirve el APK de AVACOM Student por la red local (http://<IP>:8080/download/).
rem  Uso: Servir-APK.bat            (puerto 8080)
rem       Servir-APK.bat 8081       (otro puerto)
rem  Usa el Python embebido de AVACOM OPS Master si esta instalado; si no, el del equipo.
rem  Ctrl+C para detenerlo. Ver Servir-APK.py.
rem ===========================================================================
setlocal
title AVACOM Student - servidor del APK
set "PUERTO=8080"
if not "%~1"=="" set "PUERTO=%~1"

set "PY=%ProgramFiles%\AVACOM\OPS Master\Runtime\Python\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%~dp0Servir-APK.py" --puerto %PUERTO%
if errorlevel 1 pause
