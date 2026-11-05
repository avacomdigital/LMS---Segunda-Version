# avacom_lic · biblioteca nativa de licenciamiento (MOD-018, Fase 4)

Una sola implementación en C11 del formato de licencia y de su verificación para tres consumidores: el backend (`ctypes`), el Host y Core (P/Invoke). Criptografía de Monocypher 4.0.2, vendida y fijada
(`vendor/VENDOR.md`). **La nativa nunca es obligatoria:** si no carga, el nodo sigue con la referencia en Python (`backend/licenciamiento/infraestructura/nativo.py`), deja un registro y un asiento.

## Qué hay

| Carpeta | Contenido |
|---|---|
| `include/avacom_lic.h` | El contrato (ABI 1): funciones, estructuras, códigos de error |
| `src/avl.c`, `src/avl_win.c` | La implementación (sin `malloc`, sin estado global) y la lectura de MachineGuid + SMBIOS de Windows |
| `vendor/` | Monocypher 4.0.2 sin tocar, con versión y SHA-256 |
| `tests/` | `test_avl.c` (vectores RFC 8032, XChaCha20-Poly1305, HMAC; harness de mutación; cuerpos re-firmados) y `vectors.h` (generado, contrastado) |
| `tools/` | `gen_vectors.py` (contrasta cada vector con una implementación independiente) y `gen_corpus.py` (licencias válidas del emisor de PRUEBAS) |
| `Build-Native.ps1` | Compila Windows x64 (MSVC de VS 18) y Android arm64-v8a / x86_64 (NDK 30.0.14904198) y comprueba las banderas EN el binario |
| `Verificar-Banderas.ps1` | `dumpbin` y `llvm-readelf`: ASLR, DEP, CET, CFG, cookie de pila, RELRO, BIND_NOW, pila no ejecutable, segmentos a 16 KB, sólo `avl_*` exportado |
| `Probar-Native.ps1` | Pruebas en C: normal, con ASan y (con `-Android`) en el AVD con UBSan |
| `dist/` y `build/` | Salidas. **No se versionan** |

Funciones: `avl_abi_version`, `avl_selftest`, `avl_verify_detached`, `avl_license_verify`, `avl_fp_match`, `avl_smbios_parse`, `avl_fp_collect` (sólo Windows), `avl_request_build`,
`avl_clock_advance`, `avl_key_derive`, `avl_key_wrap`, `avl_key_unwrap`, `avl_wipe`.

## Cómo se usa

```powershell
cd native\avacom-lic
.\Build-Native.ps1                 # compila todo, /analyze y clang --analyze, y comprueba las banderas en los binarios
.\Probar-Native.ps1 -Android       # pruebas en C: Windows, Windows + ASan y AVD (100 000 mutaciones por modo)
cd ..\..\backend
.\.venv\Scripts\python.exe manage.py test licenciamiento.tests.test_nativa   # diferenciales contra la referencia (≈ 35 000 casos)
```

No instala nada en el sistema. Hace falta VS con las herramientas de C++ (se busca con `vswhere`) y, para Android, el NDK.

## Qué debe copiar el build del instalador (lo hace la rama de integridad del despliegue, no esta carpeta)

| Origen (tras `Build-Native.ps1`) | Destino en el paquete | Para quién |
|---|---|---|
| `native\avacom-lic\dist\win-x64\avacom_lic.dll` | `Backend\native\avacom_lic.dll` | El backend (lo carga por ruta absoluta) y, si se quiere, el Host junto a su `.exe` |
| `native\avacom-lic\dist\SHA256.txt` | entra en el manifiesto firmado | La huella de la DLL que el Host verifica al arrancar el servicio (P-23) |
| `native\avacom-lic\dist\android-arm64-v8a\libavacom_lic.so`, `...\android-x86_64\libavacom_lic.so` | `lib/<abi>/libavacom_lic.so` dentro del APK | Student (el `.csproj` ya los incluye con `AndroidNativeLibrary` si existen; si no existen, no se incluye nada) |

Reglas del destino: la carpeta se llama exactamente `native` y está **dentro de `Backend\`** (junto a `manage.py`). **Si la carpeta existe y la DLL no carga, el nodo lo asienta** como
`integridad_alterada` (`biblioteca_nativa`): por eso el instalador sólo debe crear `Backend\native\` cuando también copia la DLL. Un paquete sin la carpeta usa la referencia en silencio.
`native\` entra en la huella de código que compara `Build-Installer.ps1` (hoy sólo mira `backend\`, la app y el asistente).

## Lo que NO es

No es una barrera contra un administrador del equipo con conocimientos: la DLL se puede reemplazar o quitar y el nodo sigue por la referencia (con asiento). Es una **única implementación del formato**,
con banderas de endurecimiento verificadas, que encarece y deja rastro. Ver `spec-driven/15-licenciamiento/04-proteccion.md`.
