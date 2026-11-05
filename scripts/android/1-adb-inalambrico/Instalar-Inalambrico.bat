@echo off
rem Doble clic: instala la Student en una tableta por Wi-Fi. Descarga adb una sola vez; no toca controladores.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Instalar-Inalambrico.ps1" %*
