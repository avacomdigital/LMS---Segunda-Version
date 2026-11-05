# 3. Instalar en lote por Wi-Fi (varias tabletas, informe por tableta)

Requisito: tabletas Android 11+ con Depuracion inalambrica activada, en la misma red que el computador. Sin cable ni drivers; descarga adb a `%LOCALAPPDATA%\AVACOM\platform-tools` la primera vez.

1. Doble clic en `Instalar-EnLote.bat`. La primera vez crea `tabletas.txt` y lo abre en el Bloc de notas.
2. Escribe una tableta por linea (formatos en el propio archivo): `IP:puerto`, o `IP:puerto;IP:puerto-de-vincular;codigo` si es nueva.
3. Guarda y vuelve a tocar el `.bat`. Al final muestra el resumen y escribe `informe-FECHA.csv` (tableta, modelo, resultado, motivo).

Una linea: `powershell -ExecutionPolicy Bypass -File .\Instalar-EnLote.ps1 [-Lista tabletas.txt] [-Apk ruta.apk] [-Reemplazar]`

Notas: el puerto de la Depuracion inalambrica cambia cada vez que se reactiva; si una tableta falla por "No conecto", copia el puerto actual. Para muchas tabletas sin escribir IPs, mejor la alternativa 2 (QR). Kiosco/Device Owner: `..\amapi\README.md`.
