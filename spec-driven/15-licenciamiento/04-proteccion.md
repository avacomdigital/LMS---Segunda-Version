# 15 · Licenciamiento (MOD-018) · Protección

| Campo | Valor |
|---|---|
| Estado | **En construcción** (Fases 4 a 6). Este archivo lo comparten las ramas de la Fase 4; cada una escribe su sección con encabezado propio |

## Fase 4 · Integridad del despliegue (P-23)

> Rama «integridad del despliegue» de la Fase 4. Lo que sigue describe **sólo** esa parte (manifiesto firmado, verificación del Host, señal al backend y lo que el instalador hace con la biblioteca nativa); la biblioteca en sí (`avacom_lic`, P-20 a P-22) tiene su propia sección. Decisiones `D-40` a `D-49` en [01-diseno.md](01-diseno.md).

### Qué hay

| Pieza | Dónde | Qué hace |
|---|---|---|
| Lista de integridad | `integridad.json`, junto a `manifiesto.json` | `ruta · SHA-256` de lo que el nodo **ejecuta**: `Backend\`, `Runtime\` (el Host, el Python embebido y `site-packages`) y, de `App\`, sólo `Avacom.Lms.*.dll/.exe` y la DLL nativa. Se escribe en el último paso de la compilación (`installer/build/Sellar-Paquete.py`) |
| Manifiesto firmado | `manifiesto.json` + `manifiesto.firma.json` | `manifiesto.json` lleva el SHA-256 de la lista (`integridad`); la firma es **Ed25519 sobre los bytes exactos** de `manifiesto.json`, con la llave de publicación `upd-2026-1` (la misma de los paquetes `.avupd`; otra ceremonia y otra llave que la de licencias) |
| Llaves de confianza | incrustadas en `Avacom.Ops.Host.exe` | las públicas vigentes y siguientes de `backend/actualizacion/claves/produccion.json`, pasadas al compilar el Host con `-p:ClavesDePublicacion=kid:hex\|kid:hex`. Rotar = una llave `siguiente` que entra con un instalador antes de firmar con ella |
| Verificación | `Host\Integridad\Verificador.cs` | al arrancar el servicio (y después de una actualización): firma → huella de la lista → cada archivo; además avisa de lo que **sobra** (un `.py`, `.dll`, `.exe`, `.pyd`… que no está en la lista) |
| Señal | `%ProgramData%\AVACOM\OPS Master\Config\integridad.json` | el resultado, en JSON y sin datos de personas ni de licencias (contrato abajo). Se reescribe en cada arranque |
| Aviso | `backend/licenciamiento/infraestructura/integridad.py` | si la señal dice `alterada`, cada tipo de hallazgo entra a la lectura de anclas como `despliegue:<tipo>` y recorre el camino de siempre: observación, asiento `licencia.integridad_alterada` y evento `.v1` (uno al día), bandera `integridad_alterada` en el estado (7 días) y aviso al administrador en OPS |
| Verbo | `Avacom.Ops.Host.exe verificar-integridad` | hace lo mismo a pedido, deja el resumen en `Logs\servicio.log` y sale **siempre con 0** |

### Qué dice la señal

```json
{"version": 1, "verificado": "2026-10-22T17:45:37Z", "estado": "alterada", "firma": "ok", "kid": "upd-2026-1", "version_producto": "2.16.0",
 "archivos_comprobados": 7091,
 "hallazgos": [{"tipo": "backend", "detalle": "modificado", "cantidad": 1, "ejemplos": ["Backend/expediente/__init__.py"]}]}
```

| Campo | Valores |
|---|---|
| `estado` | `ok` · `alterada` · `sin_firma` (el paquete se compiló sin llave: se compararon huellas, no firma) · `no_verificable` (un paquete anterior a la 2.16.0, sin lista) |
| `firma` | `ok` · `ausente` · `ilegible` · `kid_desconocido` · `invalida` · `sin_llave` |
| `hallazgos[].tipo` | `backend` · `runtime` · `app` · `nativo` · `manifiesto` · `firma` · `otro` |
| `hallazgos[].detalle` | `modificado` · `falta` · `sobra` · `ruta_invalida` · `lista_alterada` · `ilegible` · `ausente`… |

Sólo `alterada` avisa. Un archivo que el nodo no entiende (otra versión, ilegible, enorme) **no inventa una alarma**.

### Qué impide, qué encarece, qué detecta

- **Impide:** nada. Es **evidencia, no prevención**: un antivirus que cambia un archivo o un parche de campo no pueden dejar un aula sin clase, así que una diferencia nunca detiene el arranque ni degrada una función (la bandera `integridad_alterada` es sólo un aviso).
- **Encarece:** cambiar código del backend en `Program Files` ya no pasa inadvertido: el administrador de turno ve el aviso y la bitácora (encadenada) guarda un asiento por día mientras siga así.
- **Detecta:** un `.py` o una DLL modificados, borrados o agregados en `Backend`, `Runtime` (incluido el Python embebido, que antes no tenía ninguna huella) y la parte propia de `App`; la DLL nativa cambiada o renombrada; el manifiesto o la lista editados; la firma quitada o de otra llave.
- **No cubre (declarado):**
  - **El Host también es un archivo parcheable.** Quien administra el equipo puede cambiar el `Avacom.Ops.Host.exe` —y con él las llaves que lleva incrustadas, o la propia verificación— y no se enterará nadie. La señal tampoco está firmada: quien escriba `Config\integridad.json` puede borrarla. Es el límite A4 del modelo de amenazas.
  - Lo que está en `App\` y no es de AVACOM (cientos de DLL de terceros) no entra en la lista: sólo se vigila lo propio.
  - Un código alterado **antes** de compilar el instalador sale firmado: la firma prueba que el paquete es el que salió de la máquina de compilación, no que el código sea bueno.
  - Una diferencia en un archivo que un antivirus tiene tomado se deja pasar (no se pudo leer; no es evidencia de nada).

### Las actualizaciones legítimas no son diferencias

Cuando el Host termina con éxito una orden de Update Manager, anota en `Actualizaciones\integridad-aplicada.json` las rutas y huellas que **el paquete firmado declaró** (no recalcula nada del disco: si lo hiciera, daría por buena una alteración hecha antes de actualizar). Esas huellas valen en lugar de las de la lista original; una reversión exitosa retira al paquete. Una actualización que falla y se deshace no anota nada. Si el archivo no se puede escribir, la siguiente verificación lo verá como una diferencia: es la dirección segura del error.

### Cómo se firma en la compilación

`Build-Installer.ps1` firma si encuentra la llave `%USERPROFILE%\AVACOM-Llaves\claves\upd-2026-1.avkey` **y** la copia DPAPI de su frase (`frase\upd-2026-1.frase.dpapi`); ambas rutas son parámetros. La frase se descifra dentro del script, viaja **sólo** por una variable de entorno del proceso hijo (`Sellar-Paquete.py`) y no se escribe ni se imprime. Antes de firmar se comprueba que la llave es una de las vigentes o siguientes de `produccion.json`; después de firmar se verifica la firma con la pública. Sin llave en el equipo, el paquete sale **sin firma** con un aviso (un desarrollo), y `-ExigirLlaveDeProduccion` lo rechaza.

### Lo que el instalador hace con la biblioteca nativa

`native\avacom-lic\dist\win-x64\avacom_lic.dll` (si está compilada) se copia a `Backend\native\` y a `App\`; su SHA-256 va en el manifiesto (`sha256_avacom_lic_dll`) y en la lista firmada. **Nunca es obligatoria**: sin la DLL el paquete sale con la implementación de referencia y un aviso; `-ExigirBinariosNativos` lo convierte en un fallo. Las fuentes de `native\avacom-lic` entran a la huella que el build toma al empezar y al terminar (`huella_nativo`): si cambian mientras se compila, el build aborta como con el backend o la app.

### Cómo se probó

| Prueba | Resultado |
|---|---|
| `dotnet test tests/Avacom.Ops.Host.Tests` (16): vector 1 de RFC 8032, firma hecha por `cryptography` aceptada, paquete íntegro, `.py` alterado, archivo que falta y que sobra, DLL nativa cambiada, runtime y app, firma ausente/de otra llave/`kid` desconocido, manifiesto y lista editados, desarrollo sin llaves, paquete anterior sin lista, actualización firmada (aplicada y revertida), ruta fuera de la instalación, contrato de la señal, lectura tolerante de llaves | 16 de 16 |
| `manage.py test licenciamiento.tests.test_integridad_despliegue` (11): sólo `alterada` avisa; lo ilegible no alarma; bandera, un asiento al día, sin degradar nada; la señal real del Host cumple el contrato y no lleva datos de personas | 11 de 11 (y el módulo entero: 399, 7 omitidas) |
| Ensayo del paquete, bloque **G** (`Ensayar-Paquete.ps1 -SoloIntegridad`): paquete firmado, servicio real en carpeta de estado de pruebas con `ProgramData` redirigido: intacto → `ok`; un `.py` alterado → el nodo **arranca igual**, `/health/` responde, señal `alterada` con el archivo, asiento en `servicio.log`, observación de integridad en la base del nodo; archivo restituido → vuelve a `ok`; firma alterada o quitada → `alterada` | **14 de 14** (la primera pasada falló en 2 por culpa del ensayo, no del código: el backend de la demostración era el anterior y la espera de la primera verificación era de 60 s; corregido y repetido) |
| Verificación de 7091 archivos (Backend, Runtime y App propios) | 4,5 s con los archivos en caché; 15 s la primera vez tras copiarlos (en segundo plano, sin retrasar el arranque) |
| Coste en el paquete | Host +4,7 MB (BouncyCastle), `integridad.json` ≈ 1 MB |

### Qué no se pudo comprobar

- **Un servicio de Windows real** (instalado con el asistente y con privilegios de administrador): el ensayo corre el verbo `servicio` como proceso normal, igual que los demás bloques del ensayo.
- **Un antivirus que bloquee o cambie archivos** a media verificación, y un equipo lento de panel: los tiempos son de este equipo de desarrollo.
- **La llave real `upd-2026-1` firmando el instalador**: la prueba usó una llave de prueba (`upd-prueba`) con la misma ruta de código; la firma con la llave de la ceremonia ocurre en la compilación de entrega.
- **La DLL nativa** (`avacom_lic.dll`) dentro del paquete: depende de que la rama de la biblioteca la deje compilada; el empaquetado y el aviso de «falta» están probados con y sin ella sólo hasta donde existía al compilar.

### Defectos ajenos que encontré (reporto, no arreglo)

- **El Python embebido no tenía ninguna huella ni hash** (`Get-PythonRuntime.ps1` baja el `embeddable` y no comprueba su SHA-256 contra el de python.org). Ahora el runtime **sí** entra a la lista firmada, pero eso sólo prueba que no cambió *después* de compilar; no que lo que se bajó fuera el de python.org.
- **`site-packages` de `Runtime\Python` se instala con `pip` sin hashes** (`requirements-runtime.txt` sin `--require-hashes`), con los mismos efectos.

## Fase 4 · biblioteca nativa (`avacom_lic`)

> Rama de la biblioteca nativa (P-20 a P-22). El despliegue firmado (P-23) lo documenta su propia sección más abajo. Fuentes en `native/avacom-lic/` (`LEEME.md` dice cómo compilar, probar y qué copia el instalador).

### Qué quedó

| Pieza | Estado |
|---|---|
| `avacom_lic.dll` (Windows x64) y `libavacom_lic.so` (arm64-v8a y x86_64) | Compiladas con las banderas de P-21; **no se versionan** (`dist/` y `build/` ignorados) |
| 13 funciones `avl_*` (ABI 1) | `avl_abi_version`, `avl_selftest`, `avl_verify_detached`, `avl_license_verify`, `avl_fp_match`, `avl_smbios_parse`, `avl_fp_collect` (sólo Windows), `avl_request_build`, `avl_clock_advance`, `avl_key_derive`, `avl_key_wrap`, `avl_key_unwrap`, `avl_wipe` |
| Gemelo de referencia en Python | `backend/licenciamiento/infraestructura/nativo.py` (`Referencia`), con la misma interfaz que el envoltorio de `ctypes` (`Nativa`) y una fachada (`Biblioteca`) que usa la nativa y, si no responde, la referencia |
| Envoltorio de Core | `src/Avacom.Lms.Core/Licencia/NativoLicencia.cs`: un archivo aparte con los `DllImport`, `null` si la nativa no está, sin `unsafe` |
| APK | `AndroidNativeLibrary` condicional en `Avacom.Lms.Student.csproj`: incluye los `.so` sólo si existen |

**Qué está cableado y qué no.** El verificador de firmas de todo el módulo (`firma.verificar`) usa `avl_verify_detached` cuando la biblioteca cargó: así la **verificación de licencias en producción ya pasa por la nativa**. El
lector de campos, la huella, SMBIOS, la solicitud, el ancla v2 del reloj y las llaves existen, están probados contra la referencia, pero **el nodo sigue usando la referencia en Python para ellos**: decidirlo así evita que dos
implementaciones del formato tomen caminos distintos mientras no haya una razón para cambiar (D-36). El Host y Core pueden llamarlas cuando las necesiten.

### Decisiones (D-30 a D-36)

| | Decisión | Por qué |
|---|---|---|
| **D-30** | La biblioteca se busca por ruta **absoluta**: `<backend>\native\avacom_lic.dll` (y, sólo fuera de producción, `AVACOM_LIC_NATIVA` y `native\avacom-lic\dist\<plataforma>\`). Se carga **una vez por proceso**, al construir los servicios, con `LOAD_LIBRARY_SEARCH_DEFAULT_DIRS \| DLL_LOAD_DIR` | Nunca el directorio actual ni el PATH; un nodo de producción no lee ninguna variable para decidir qué biblioteca cargar (P-12) |
| **D-31** | Monocypher se compila con las mismas banderas de seguridad pero con `/W3` (MSVC) y sin `-Wconversion` (clang), sin `/WX`. El código propio va con `/W4 /WX` y `-Wall -Wextra -Wconversion -Werror` | Upstream tiene una conversión de 64 a 32 bits intencionada (C4244). No se modifican las fuentes vendidas |
| **D-32** | `kid` y códigos de capacidad se validan con `\Z` y no con `$` en la referencia (`tlv.py`, `licencia.py`) | Lo halló la prueba diferencial: con `$` un `\n` final pasaba. Es más estricto y ninguna licencia legítima lo tiene |
| **D-33** | Se rechazan la llave pública y el `R` de la firma de **orden pequeño** (y las `S ≥ L`), en la nativa y en la referencia | La ecuación cofactorizada de la RFC 8032 acepta `S = 0` con llave y `R` de orden pequeño para cualquier mensaje. Las llaves del nodo son fijas, pero el `kid` de una solicitud o liberación **es** la llave que elige quien pide. La lista (y = 0, 1, p−1, p, p+1 y las dos de orden 8) se validó con aritmética de curva |
| **D-34** | `avl_clock_advance` define el ancla **v2**: HMAC-SHA-512 truncado a 32 bytes con llave `SHA-512("avl-ancla-v2\|" + secreto)[:32]`. **No sustituye** el ancla v1 (HMAC-SHA-256 en `anclas.py`) | Monocypher no trae SHA-256; cambiar el formato de un ancla ya escrita invalidaría el estado de los nodos instalados. Queda disponible; migrarla es una decisión aparte |
| **D-35** | `avl_fp_collect` devuelve **cadenas crudas** (MachineGuid y SMBIOS interpretado); el filtro de basura y el hash con clave de producto siguen en Python. La tabla SMBIOS se lee en un buffer de 96 KB de la pila (sin `malloc`): una mayor devuelve `AVL_E_SMALL` y se usa la referencia | El hash necesita SHA-256 (D-34); y así los identificadores no viajan nunca fuera del proceso en claro |
| **D-36** | La nativa **nunca es obligatoria**. Si la carpeta `native\` existe y la biblioteca no carga (falta, otra ABI, autoprueba falla, archivo dañado), el nodo sigue con la referencia, deja un registro y **un** asiento `integridad_alterada` (secreto `biblioteca_nativa`, por `NodoDeLicencia.anotar_novedad`). Sin carpeta `native\` (desarrollo, instalaciones anteriores) usa la referencia en silencio | Un antivirus o un parche de campo no pueden dejar un aula sin clase |

### Cómo se verificó

| Qué | Resultado |
|---|---|
| Vectores en C (RFC 8032 pruebas 1, 2 y SHA(abc); XChaCha20-Poly1305 A.3.1 del borrador IRTF-CFRG; HMAC-SHA-512 RFC 4231) | **306 comprobaciones, 0 fallas** en Windows, Windows + ASan, Android x86_64 y Android x86_64 + UBSan. Cada vector se contrastó antes con `cryptography` (`tools/gen_vectors.py` se detiene si alguno no coincide) |
| Mutación de licencias válidas (semilla fija) | **100 000** alteraciones por modo, **0 aceptadas**, en los cuatro modos |
| Cuerpos alterados y vueltos a firmar (ejercita el lector de campos) | **100 000** por modo; ≈ 18 900 aceptados con invariantes intactos, **0 invariantes rotos, 0 fallos de memoria o comportamiento indefinido** (ASan en Windows, UBSan en Android) |
| Diferenciales contra la referencia (`manage.py test licenciamiento.tests.test_nativa`) | **35 191 casos** (mínimo exigido 10 000) con semilla fija: licencias válidas y alteradas, cabeceras, firmas y llaves débiles, huella, SMBIOS, solicitudes **byte a byte**, ancla v2, HKDF, XChaCha. Mismo veredicto, mismo motivo, mismos bytes. 24 pruebas, todas correctas |
| Análisis estático | MSVC `/analyze` y `clang --analyze` sobre el código propio: limpios |
| Banderas en el binario (`Verificar-Banderas.ps1`) | DLL: ASLR, ASLR de 64 bits, DEP, CET, CFG, cookie de pila, sólo `avl_*` exportado, CRT estático (depende sólo de kernel32 y advapi32). `.so` (arm64-v8a y x86_64): RELRO, BIND_NOW, pila no ejecutable, sin TEXTREL, `__stack_chk_fail`, segmentos a 16 KB, sólo `avl_*` |
| Carga | Cargar + comprobar ABI + `avl_selftest`: mediana **2,7 ms** (máximo 3,8 ms, 15 procesos nuevos). Importar el módulo cuesta lo que ya costaba `cryptography` |
| Validar una licencia | Referencia ≈ 160 a 240 µs; nativa ≈ 190 a 250 µs. **La nativa no es más rápida** (el costo es el paso por `ctypes`): su valor es ser una sola implementación, no la velocidad. Muy por debajo del tope de +200 ms |
| Respaldo | Sin carpeta `native`: referencia en silencio. Carpeta sin DLL o DLL dañada: referencia, registro y una novedad que la evaluación asienta como `integridad_alterada` (una observación, la bandera) sin cambiar el estado ni detener nada. Una llamada que falla o un verificador que lanza caen a la referencia |
| Android | El `.so` x86_64 se ejecutó en el AVD (`Pixel_10`, Android 17 x86_64, `adb push` a `/data/local/tmp`): demuestra la compilación cruzada, **no** el rendimiento de una tableta ARM |
| P/Invoke de Core | `NativoLicencia.cs` compilado sin advertencias (net10.0, advertencias como error) y probado en un proyecto aparte con la DLL real: sin la DLL devuelve `null` sin lanzar; con ella verifica el vector RFC 8032, envuelve y abre, y su envoltura reproduce el vector A.3.1 |
| Suite de `licenciamiento` completa (con la nativa en uso) | 399 pruebas: 397 correctas, 7 omitidas de antes y **2 errores que no son de esta rama**: `test_integridad_despliegue` busca `fixtures/senal_integridad_alterada.json`, que la rama del despliegue firmado aún no creó |


### Lo que NO se pudo comprobar

- **Tableta ARM física:** el `.so` de `arm64-v8a` se compiló, se comprobaron sus banderas con `llvm-readelf`, pero **no se ejecutó**; sólo corrió el de `x86_64` en el AVD. No hay medida de rendimiento ARM.
- **APK:** no se compiló ni se abrió con `aapt2`: que `lib/<abi>/libavacom_lic.so` esté dentro del APK queda sin verificar (el `.csproj` lo declara).
- **P/Invoke de Core desde OPS/Student:** `NativoLicencia.cs` se probó en un proyecto aparte con la DLL real (no dentro de OPS, Student ni Core.Tests).
- **UBSan en Windows:** MSVC no lo trae; UBSan sólo corrió con clang del NDK en el AVD. ASan sí corrió en Windows.
- **Antivirus real** que bloquee la DLL, **Windows 10 de panel** y la **instalación con administrador**.
- **`/sdl`:** se compila con él, pero no hay una comprobación en el binario que lo distinga de `/GS`.
- La nativa **no es una barrera** contra un administrador del equipo: la DLL se puede quitar o sustituir y el nodo sigue con la referencia (con asiento). Encarece y unifica; no prohíbe.
