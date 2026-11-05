# 1. Instalar por Wi-Fi (una tableta, sin cable)

Requisito: tableta Android 11 o superior y el computador en el mismo Wi-Fi. Hace falta internet la primera vez (descarga adb a `%LOCALAPPDATA%\AVACOM\platform-tools`; no instala controladores).

1. Doble clic en `Instalar-Inalambrico.bat`.
2. Sigue lo que dice la pantalla: en la tableta, *Opciones de desarrollador > Depuracion inalambrica > Vincular con codigo*, y escribe la direccion y el codigo que muestra.
3. Escribe la direccion IP y puerto de la pantalla principal de Depuracion inalambrica. El script instala la Student.

Una linea de PowerShell: `powershell -ExecutionPolicy Bypass -File .\Instalar-Inalambrico.ps1 [-Apk ruta.apk] [-Reemplazar]`

Si dice "ya hay otra Student con distinta firma", repite con `-Reemplazar` (borra los datos de la app). Device Owner/kiosco: ver `..\Provision-DeviceOwner.ps1` y `..\amapi\README.md`.
