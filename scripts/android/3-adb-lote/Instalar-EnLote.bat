@echo off
rem Doble clic: instala la Student en todas las tabletas de tabletas.txt por Wi-Fi y deja un informe CSV.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Instalar-EnLote.ps1" %*
