@echo off
rem Doble clic: sirve el APK de Student por la red y muestra el QR (reutiliza installer\student-android\Servir-APK.bat).
set "SERVIDOR=%~dp0..\..\..\installer\student-android\Servir-APK.bat"
if not exist "%SERVIDOR%" (
    echo No encuentro installer\student-android\Servir-APK.bat. Ejecuta este archivo desde la carpeta del proyecto AVACOM.
    pause
    exit /b 1
)
call "%SERVIDOR%" %*
