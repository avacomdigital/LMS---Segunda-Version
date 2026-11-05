# 2. Instalar desde el navegador de la tableta (QR por la LAN)

No usa ADB ni cable. Reutiliza el servidor que ya existe: `installer\student-android\Servir-APK.bat` (+ `Servir-APK.py`, `GUIA-55-TABLETAS.txt`). No se duplica nada.

1. Doble clic en `Servir-Student.bat` (acepta el permiso de administrador: abre el puerto solo para la red local mientras corre).
2. En el computador se abre un panel con un QR y la direccion. En cada tableta (mismo Wi-Fi): escanea el QR con la camara, descarga el APK y abre el archivo.
3. Si Android avisa de "origen desconocido", pulsa *Ajustes* y permite instalar desde ese navegador una vez.
4. El panel cuenta cuantas tabletas descargaron. Al terminar, pulsa *Detener el servidor*.

Sirve el APK mas nuevo de `installer\student-android`. Para otro puerto o numero de tabletas: `Servir-Student.bat 8081 30`. Kiosco/Device Owner: `..\amapi\README.md`.

Limite: instalar desde el navegador NO fija el Device Owner; eso se hace aparte (QR de aprovisionamiento o AMAPI).
