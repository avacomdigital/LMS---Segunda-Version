# Fase 0 · Reconocimiento de herramientas e identificadores (MOD-018) — mediciones

Fecha de las mediciones: 2026-10-20. Máquina: Windows 11 Pro 10.0.26200, fabricante «AVACOM», modelo «AVACOM5G», CPU Intel Core Ultra 9 185H (16 núcleos, 22 lógicos).

Condiciones de la medición:

- Todo se ejecutó **sin elevación** (token de integridad media, `IsUserAnAdmin()` = False) y **sin escribir en el repositorio**. Lo único que se tocó dentro de él fue *ejecutar* el Python del venv del backend (`C:\projects\prototypes\prototype-lms-v04\backend\.venv\Scripts\python.exe`, 3.12.10) con `-I -B`. El `-B` se añadió a `-I` para que Python no escriba `.pyc` dentro del árbol del repositorio.
- `<FASE0>` = `C:\Users\AVACOM\AppData\Local\Temp\claude\C--projects-prototypes-prototype-lms-v04\8f9dd047-3826-488f-88bb-7410b1ae2156\scratchpad\fase0`. Fuentes en `<FASE0>\src`, guiones `.bat` en `<FASE0>`, salidas en `<FASE0>\logs`, `<FASE0>\msvc18` y `<FASE0>\ndk`.
- Carga del equipo mientras se medía: 6–19 % de CPU (muestras de `Win32_PerfFormattedData_PerfOS_Processor`), sin procesos `python` ajenos en ese instante. Las compilaciones duraron segundos y el benchmark de criptografía unos 6 s, una sola hebra.
- **No se copia ningún valor crudo de identificadores de hardware**: los scripts sólo emiten fuente, longitud, tipo y calidad (válido/basura) y booleanos de comparación.

---

## 0. Resumen frente a las suposiciones del plan

| Suposición del plan | Resultado | Matiz |
|---|---|---|
| `cl` por `vcvarsall.bat` compila con todas las banderas | **Sí, con VS 18** (cl 19.51.36248) | Aceptó las banderas exactas sin un solo aviso. **VS 2022 no sirve**: no tiene `vcvarsall.bat` ni cabeceras ni bibliotecas |
| El NDK 30 compila y enlaza con las banderas pedidas | **Sí** (clang 21.0.0, API 26, aarch64 y x86_64) | Es **r30-beta1** (preliminar), no una versión estable |
| `dumpbin` / `llvm-readelf` leen las banderas | **Sí** | CET sale en la entrada «dllchar» del directorio de depuración, no en «DLL characteristics» |
| ≥ 3 de 5 factores válidos en esta máquina | **Sí en el recuento (3/5)** | Sólo 2 distinguen de verdad la máquina (MachineGuid y UUID); `ProcessorId` es la firma de la CPU, y las series de placa, chasis, BIOS y sistema son «Default string» |
| DPAPI de máquina funciona sin elevar | **Sí** | Ida y vuelta de 32 bytes con la bandera 0x4 (y con 0x5, y con entropía), blob de 280 bytes, ≈ 0,28 ms |

Sorpresas que conviene tener presentes:

1. **El CRT es estático por omisión** con esas banderas (no se pasó `/MD` ni `/MT`): `hola.dll` pesa 103 424 B y sólo importa `KERNEL32.dll`. Con `/MD` pesa 9 216 B e importa además `VCRUNTIME140.dll` y `api-ms-win-crt-runtime-l1-1-0.dll`.
2. **VS 2022 está roto para C++**: `vcvars64.bat` falla porque falta `vcvarsall.bat`; la carpeta del toolset 14.44.35207 sólo tiene `Auxiliary`, `bin` y `lib\onecore`.
3. **No hay `clang-cl` ni `lld-link`** en ninguno de los dos Visual Studio (sólo `clang-format` y `clang-tidy`).
4. **El NDK es r30-beta1** y deja esa marca en cada binario (`.note.android.ident` con «r30-beta1» y la compilación 14904198).
5. **El texto del UUID de SMBIOS depende de la decodificación**: con el orden de bytes directo sale una versión 15 (no definida); con *mixed-endian* sale versión 1 y coincide con lo que da CIM. El plan debe fijar la decodificación.
6. **Las series de placa, chasis, BIOS y sistema son todas «Default string»** en este equipo (fabricante «AVACOM»): no sirven como factor.
7. **`Get-Tpm` exige administrador** («Se requiere privilegios de administrador para ejecutar este comando.»), pero `tpmtool getdeviceinformation` sí funciona sin elevar y el proveedor CNG de la plataforma (TPM) se abre sin elevar.
8. `NoDefaultCurrentDirectoryInExePath=1` está definida: en `cmd`, un `.exe` de la carpeta actual no se encuentra sin `.\`.
9. **El servidor `adb` no estaba arrancado**: no se ejecutó `adb devices` (habría arrancado el servidor).

---

## A) MSVC

### A.1 Instalaciones (vswhere)

Comando: `"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe" -all -products * -format json` (salida completa en `<FASE0>\vswhere.json`).

| | VS «2022» | VS «18» (Visual Studio Community 2026) |
|---|---|---|
| Ruta | `C:\Program Files\Microsoft Visual Studio\2022\Community` | `C:\Program Files\Microsoft Visual Studio\18\Community` |
| Versión de instalación | 17.14.37614.0 (catálogo 17.14.39) | 18.7.11925.98 (catálogo 18.7.3) |
| Toolset MSVC | 14.44.35207 | 14.51.36231 (v145) |
| `vcvarsall.bat` | **No existe** (sólo `vcvars64.bat` y `vcvarsamd64_x86.bat`) | Sí (`vcvars32/64/all/amd64_x86/x86_amd64`) |
| ¿Sirve para compilar C? | **No** | **Sí** |
| `Llvm` | `clang-format`, `clang-tidy` 19.1.5 | `clang-format`, `clang-tidy` 22.1.3 (x64 y ARM64) |

Evidencia de que VS 2022 no sirve:

- `cmd /c <FASE0>\run_msvc2022.bat` (llama a `...\2022\Community\VC\Auxiliary\Build\vcvars64.bat`) termina con: `""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" no se reconoce como un comando interno o externo, programa o archivo por lotes ejecutable.`
- La carpeta `VC\Tools\MSVC\14.44.35207` contiene sólo `Auxiliary`, `bin` y `lib\onecore` (no hay `include` ni `lib\x64`).
- `vswhere -all -products * -prerelease -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath` devuelve sólo `...\18\Community`.

Por eso **todo lo siguiente usa VS 18**, que funcionó a la primera. VS 2022 se probó después sólo como comparación; no se arregló ni se rodeó.

### A.2 Versiones (VS 18, tras `vcvarsall.bat x64`)

| Herramienta | Versión / ruta |
|---|---|
| `cl` | `Microsoft (R) C/C++ Optimizing Compiler Version 19.51.36248 for x64`, `...\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\cl.exe` |
| `link` | Microsoft Incremental Linker 14.51.36248.0 |
| `dumpbin` | 14.51.36248.0 |
| Entorno | `VSCMD_VER=18.0` («Visual Studio 2026 Developer Command Prompt v18.0»), `VCToolsVersion=14.51.36231`, Windows SDK 10.0.26100.0 (única en `Include`) |
| `CL`, `_CL_`, `LINK`, `_LINK_` | vacías (no alteran el CRT por omisión) |

`vcvarsall.bat` imprime al principio `"vswhere.exe" no se reconoce como un comando interno o externo`; es inofensivo (el entorno se inicializa: «Environment initialized for: 'x64'»). Los mensajes de `cl`, `link` y `cmd` salen **en español** (idioma de la instalación): un guion de compilación no debería depender del texto de los mensajes.

Objetivos de compilación presentes en VS 18: hosts `Hostx64` (→ x64, x86), `Hostx86` (→ x64, x86) y `HostArm64` (→ arm64). Hay `lib\arm64`, pero **no hay compilador cruzado `Hostx64\arm64`**. `signtool.exe` está en el SDK (`Windows Kits\10\bin\10.0.26100.0\{x64,x86,arm64}`).

### A.3 Compilación con las banderas exactas

Se ejecutó `cmd /c <FASE0>\run_msvc18.bat > <FASE0>\logs\msvc18.log 2>&1` (hace `call "...\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64` y luego `pasos_msvc.bat msvc18`). Líneas de comando literales (las rutas de las fuentes abreviadas):

```
cl /nologo /std:c11 /W4 /WX /GS /guard:cf /sdl /O2 /LD /DAVL_BUILD_LIB <FASE0>\src\hola.c /Fe:hola.dll /Fo:hola_dll.obj /link /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /CETCOMPAT /guard:cf
cl /nologo /std:c11 /W4 /WX /GS /guard:cf /sdl /O2 <FASE0>\src\hola.c /Fe:hola.exe /Fo:hola_exe.obj /link /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /CETCOMPAT /guard:cf
```

Resultado: **errorlevel 0 y ningún aviso** (la salida es sólo `hola.c` y «Creando biblioteca hola.lib y objeto hola.exp»). Ninguna bandera fue rechazada ni reemplazada. `hola.dll` = 103 424 B; `hola.exe` = 140 800 B; `hola.exe` imprime `avl_prueba(41) = 42`. `dumpbin /exports hola.dll` muestra **una sola exportación: `avl_prueba`**.

`hola.c` (en `<FASE0>\src`) define `avl_prueba` con `__declspec(dllexport)` cuando se compila con `-DAVL_BUILD_LIB`, y trae `main` en caso contrario.

### A.4 Banderas que quedaron realmente en el binario

Comandos: `dumpbin /headers hola.dll`, `dumpbin /loadconfig hola.dll` (salidas en `<FASE0>\msvc18\hola_headers.txt` y `hola_loadconfig.txt`).

| Bandera pedida | Qué muestra `dumpbin` | ¿Quedó? |
|---|---|---|
| `/DYNAMICBASE` | «4160 DLL characteristics … Dynamic base» | Sí |
| `/HIGHENTROPYVA` | «High Entropy Virtual Addresses» | Sí |
| `/NXCOMPAT` | «NX compatible» | Sí |
| `/guard:cf` | «Control Flow Guard»; `/loadconfig`: Guard Flags `10017500` = CF instrumented, FID table present, Protect delayload IAT, Delayload IAT in its own section, Export suppression info present, Long jump target table present; Guard CF function count `2D` (45) | Sí |
| `/CETCOMPAT` | `/headers` → «Debug Directories» → entrada `dllchar` (4 B) → «00000001 extended DLL characteristics — CET compatible» | Sí |
| `/GS` | `/loadconfig` → «Security Cookie» distinto de cero (`0000000180018040`) | Sí (ver nota) |

Nota sobre `/GS`: `avl_prueba` es una función trivial sin búferes y **no lleva canario** (así lo decide `/GS`). Para demostrar que la bandera actúa se compiló `canario.dll` (`<FASE0>\src\canario.c`, función con un búfer local y `memcpy`) con las mismas banderas: `dumpbin /disasm canario.dll` muestra el prólogo `mov rax,[cookie]` / `xor rax,rsp` / `mov [rsp+30h],rax` y el epílogo `mov rcx,[rsp+30h]` / `xor rcx,rsp` / `call 00000001800012D0`, rutina que hace `cmp rcx,[cookie]` (`__security_check_cookie`).

`hola.exe` conserva las mismas banderas (DLL characteristics `C160`: las anteriores más «Terminal Server Aware»; «CET compatible»). `/sdl` no deja una marca visible propia; fue aceptada.

### A.5 Carga desde Python 3.12 (ctypes, ruta absoluta, `-I`)

Comando: `C:\projects\prototypes\prototype-lms-v04\backend\.venv\Scripts\python.exe -I -B <FASE0>\src\cargar_dll.py <FASE0>\msvc18\hola.dll`

| DLL | Resultado |
|---|---|
| `hola.dll` (banderas exactas, CRT estático) | `avl_prueba(41) = 42` (python 3.12.10, MSC v.1943 64 bit; `sys.flags.isolated = 1`) |
| `hola_md.dll` (`/MD`, sin las banderas de endurecimiento; depende de `VCRUNTIME140.dll`) | `avl_prueba(41) = 42` |
| `canario.dll` | `avl_canario(b'abc', 3) = 294` (esperado 294) |

### A.6 `/analyze` (análisis estático de MSVC)

| Fuente | Comando | Resultado |
|---|---|---|
| `hola.c` | `cl /nologo /std:c11 /W4 /WX /GS /guard:cf /sdl /O2 /analyze /c /DAVL_BUILD_LIB hola.c /Fo:hola_analyze.obj` | Funciona; sin hallazgos, errorlevel 0 |
| `defecto.c` (defectos a propósito) | `cl /nologo /std:c11 /W4 /analyze /c defecto.c` | Detecta **C6201** (índice fuera de intervalo), **C6386** (saturación de búfer), **C6011** (puntero NULL), **C6001** (memoria sin inicializar), más C4701 y C4789 |

### A.7 AddressSanitizer de MSVC (`/fsanitize=address`)

Compilación (con las banderas de endurecimiento y `/Zi`): `cl /nologo /std:c11 /W4 /WX /GS /guard:cf /sdl /O2 /Zi /fsanitize=address asan_test.c /Fe:asan_test.exe /Fo:asan_test.obj /Fd:asan_test.pdb /link /DYNAMICBASE /HIGHENTROPYVA /NXCOMPAT /CETCOMPAT /guard:cf` → errorlevel 0.

| Caso | Resultado |
|---|---|
| Sin ASan (`asan_test_sin.exe`) | Escribe un byte pasado el final de un bloque de 10 B y termina «bien»: `sin deteccion: a`, código 0 |
| Con ASan (`asan_test.exe`) | **Detecta**: `ERROR: AddressSanitizer: heap-buffer-overflow … WRITE of size 1 … 0 bytes after 10-byte region`, con pila simbolizada (archivo y línea) y código de salida 1 |

Runtime necesario: `dumpbin /dependents asan_test.exe` → `clang_rt.asan_dynamic-x86_64.dll` y `KERNEL32.dll`. La DLL (1 881 952 B, versión 19.51.36247.0, «Microsoft® Address Sanitizer Runtime Library») está en `...\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\` y sólo está en el PATH dentro de `vcvarsall`. Copiada junto al `.exe` en una carpeta vacía, el programa corre y aborta con ASan **fuera** del entorno de VS (código 1).

### A.8 LLVM / `clang-cl` dentro de la instalación

`dir /s /b "%VCINSTALLDIR%Tools\Llvm\*clang*.exe"` (VS 18) sólo encuentra `clang-format.exe` y `clang-tidy.exe` en `Llvm\x64\bin` y `Llvm\ARM64\bin` (LLVM 22.1.3). Búsqueda de `*clang-cl*` y `*lld-link*` bajo `VC\Tools` en los **dos** Visual Studio: **no existen**. `where clang-cl` y `where clang` (dentro de vcvars): nada.

### A.9 CRT: estático o dinámico por omisión

| Variante | Tamaño | `dumpbin /dependents` |
|---|---|---|
| Sin `/MD` ni `/MT` (`hola.dll` con las banderas exactas) | 103 424 B | `KERNEL32.dll` |
| `/MT` explícito (`hola_mt.dll`) | 103 424 B | `KERNEL32.dll` |
| `/MD` explícito (`hola_md.dll`) | 9 216 B | `KERNEL32.dll`, `VCRUNTIME140.dll`, `api-ms-win-crt-runtime-l1-1-0.dll` |

Las variantes `/MT` y `/MD` se compilaron con `cl /nologo /std:c11 /W4 /WX /O2 /LD /MT|/MD /DAVL_BUILD_LIB hola.c` (sin `/GS /guard:cf /sdl` ni banderas de enlace): sirven para comparar el CRT, no las banderas de endurecimiento.

Conclusión medida: **por omisión (y con `/LD`) `cl` enlaza el CRT estáticamente (`/MT`)**; no hace falta el redistribuible de VC++. Es lo contrario del valor por omisión de los proyectos de Visual Studio (`/MD`).

---

## B) NDK de Android

### B.1 Ubicación y versiones

- NDK: `C:\Users\AVACOM\AppData\Local\Android\Sdk\ndk\30.0.14904198` (única versión). `source.properties`: `Pkg.Revision = 30.0.14904198-beta1`, `Pkg.ReleaseName = r30-beta1` → **versión beta**.
- Binarios: `...\toolchains\llvm\prebuilt\windows-x86_64\bin` (311 archivos). `clang --version`: `Android (14475230, based on r574158) clang version 21.0.0 (https://android.googlesource.com/toolchain/llvm-project 9f872551d3c681d06fd303b36f16ed5c274735eb)`; `llvm-readelf --version`: LLVM 21.0.0. Presentes: `llvm-readelf`, `llvm-readobj`, `llvm-objdump`, `llvm-nm`, `llvm-strip`, `llvm-ar`, `ld.lld`, `clang-tidy`, `llvm-symbolizer`, `llvm-cov`.
- Niveles de API (`meta\platforms.json`: min 21, max 36). Envoltorios `*-clang.cmd` disponibles:

| Triple | Niveles de API |
|---|---|
| `aarch64-linux-android` | 21 a 36 (todos) |
| `armv7a-linux-androideabi` | 21 a 36 |
| `i686-linux-android` | 21 a 36 |
| `x86_64-linux-android` | 21 a 36 |
| `riscv64-linux-android` | sólo 36 |

### B.2 Compilación (API 26) con las banderas pedidas

Se ejecutó `cmd /c <FASE0>\pasos_ndk.bat > <FASE0>\logs\ndk.log 2>&1`. Ejemplo literal (aarch64; el de x86_64 cambia el envoltorio):

```
aarch64-linux-android26-clang.cmd -std=c11 -Wall -Wextra -Wconversion -Werror -fstack-protector-strong -D_FORTIFY_SOURCE=2 -fPIE -fvisibility=hidden -O2 hola.c -o arm64-v8a\hola "-Wl,-z,relro,-z,now"
aarch64-linux-android26-clang.cmd <mismas banderas> -fPIC -shared -DAVL_BUILD_LIB hola.c -o arm64-v8a\libhola.so "-Wl,-z,relro,-z,now"
x86_64-linux-android26-clang.cmd  <mismas banderas> -fPIC -shared -DAVL_BUILD_LIB hola.c -o x86_64\libhola.so "-Wl,-z,relro,-z,now"
```

Resultado: las seis compilaciones principales (ejecutable, `libhola.so` y `libcanario.so`, por ABI) terminaron con **errorlevel 0 y sin avisos** pese a `-Wall -Wextra -Wconversion -Werror`. Una compilación y enlace de un `.so` tarda ≈ 0,26 s. (Los argumentos con comas se pasaron entre comillas porque `cmd` trata la coma como separador.)

### B.3 Qué dice `llvm-readelf` (`-h -l -d --dyn-syms -n`)

| Binario | Tipo / máquina | Align de LOAD | RELRO | BIND_NOW | FLAGS_1 | NEEDED | Símbolos definidos exportados | `__stack_chk_fail` / `__memcpy_chk` | Tamaño |
|---|---|---|---|---|---|---|---|---|---|
| `arm64-v8a\libhola.so` | DYN, AArch64 | `0x4000` | sí | sí | NOW | libdl, libc | **sólo `avl_prueba`** | no / no | 5 480 |
| `arm64-v8a\hola` (ejecutable) | DYN, AArch64 (INTERP `/system/bin/linker64`) | `0x4000` | sí | sí | NOW PIE | libdl, libc | ninguno | no / no (importa `printf`) | 6 328 |
| `arm64-v8a\libcanario.so` | DYN, AArch64 | `0x4000` | sí | sí | NOW | libdl, libc | sólo `avl_canario` | **sí / sí** | 5 880 |
| `x86_64\libhola.so` | DYN, x86-64 | `0x4000` | sí | sí | NOW | libdl, libc | **sólo `avl_prueba`** | no / no | 5 040 |
| `x86_64\hola` | DYN, x86-64 | `0x4000` | sí | sí | NOW PIE | libdl, libc | ninguno | no / no | 5 760 |
| `x86_64\libcanario.so` | DYN, x86-64 | `0x4000` | sí | sí | NOW | libdl, libc | sólo `avl_canario` | **sí / sí** | 5 456 |

Lecturas:

- **Tipo de ELF**: `DYN (Shared object file)` en todos; los ejecutables llevan `PIE` en `FLAGS_1`.
- **RELRO completo**: hay segmento `GNU_RELRO` y `FLAGS BIND_NOW` + `FLAGS_1 NOW`. Un control sin `-Wl,-z,relro,-z,now` (`libhola_sin_flags_enlace.so`) sale idéntico (5 480 B): el NDK ya lo hace **por omisión**.
- **Pila no ejecutable**: `GNU_STACK` con flags `RW` (sin `E`) en todos.
- **`__stack_chk_fail`**: no aparece en `hola` porque `avl_prueba` no tiene búferes (no se le pone canario). En `libcanario.so` (función con búfer local) aparecen `__stack_chk_fail` y `__memcpy_chk` como importados de libc: `-fstack-protector-strong` y `-D_FORTIFY_SOURCE=2` están **activos**.
- **Exportados**: `libhola.so` exporta únicamente `avl_prueba` (en ambos ABIs). Importa `__cxa_finalize`, `__cxa_atexit` y `__register_atfork` (de `crtbegin_so`). No tiene SONAME.
- **Alineación de página**: todos los segmentos `LOAD` salen con `Align 0x4000` (16 KB) **sin pasar `-Wl,-z,max-page-size`**: el NDK 30-beta1 lo hace por omisión, también en x86_64. (Para el APK existe `zipalign -P 16`, ver sección C.)
- Cada binario lleva `.note.android.ident` con el nivel de API (0x1a = 26) y la cadena `r30-beta1` / `14904198`.

### B.4 Analizador estático de clang (`--analyze`)

| Fuente | Resultado |
|---|---|
| `hola.c` (`aarch64-linux-android26-clang.cmd --analyze -Xclang -analyzer-output=text -std=c11 -Wall -Wextra -DAVL_BUILD_LIB hola.c`) | Funciona; sin hallazgos |
| `defecto.c` | Con los comprobadores por omisión: `unix.Malloc` (fuga de `p`) y `core.UndefinedBinaryOperatorResult` (`x` sin inicializar). **No** señala el índice fuera de límites ni el `p[0]` sin comprobar |
| `defecto.c` con `-Xclang -analyzer-checker=security.ArrayBound` | Sí señala `buf[8]`: «Out of bound access to memory after the end of 'buf'» |
| `defecto.c` compilado normalmente con `-Wall -Wextra -Wconversion -O2` | Avisos del compilador: `-Warray-bounds` y `-Wsometimes-uninitialized` |

### B.5 `-fsanitize=undefined` (UBSan), x86_64, sin ejecutar

| Variante | Resultado |
|---|---|
| Ejecutable `hola_ubsan` y `libhola_ubsan.so` | Compilan y enlazan (errorlevel 0). Importan `__ubsan_handle_add_overflow` (instrumenta `a + 1`) y añaden `NEEDED libclang_rt.ubsan_standalone-x86_64-android.so` |
| `-fsanitize=undefined -fsanitize-trap=undefined` (`hola_ubsan_trap`) | Compila; **sin** dependencia del runtime (NEEDED sólo libdl y libc) |

Los runtimes existen en el NDK: `...\lib\clang\21\lib\linux\libclang_rt.ubsan_standalone-{x86_64,aarch64}-android.{so,a}`. Para ejecutar una variante con runtime habría que empaquetar ese `.so` en el APK.

### B.6 Extra: BTI/PAC en arm64

Con `-mbranch-protection=standard` el `.so` arm64 compila y `llvm-readelf -n` muestra `.note.gnu.property` con «aarch64 feature: BTI, PAC». Las compilaciones con las banderas pedidas **no** lo llevan (no hay `.note.gnu.property`).

---

## C) Herramientas de apoyo

| Herramienta | ¿En el PATH? | Ruta | Versión |
|---|---|---|---|
| `adb.exe` | **Sí** | `C:\Users\AVACOM\AppData\Local\Android\Sdk\platform-tools\adb.exe` | 1.0.41, Version 37.0.0-14910828 |
| `emulator.exe` | No | `...\Android\Sdk\emulator\emulator.exe` | 36.6.11.0 (build 15507667) (`emulator -version`) |
| `aapt2.exe` | No | `...\Android\Sdk\build-tools\<ver>\aapt2.exe` | 2.20-15087165 (build-tools 37.0.0) |
| `apksigner` | No | `...\build-tools\<ver>\apksigner.bat` | 0.9 (necesita Java: hay JDK 17.0.20.101 de Microsoft en el PATH) |
| `zipalign.exe` | No | `...\build-tools\<ver>\zipalign.exe` | admite `-P <4,16,64>` (alinear `.so` sin comprimir a 16 KB) |
| build-tools instaladas | | `...\Android\Sdk\build-tools\` | 34.0.0, 35.0.0, 35.0.1, 36.0.0, 36.1.0, 37.0.0 (todas con aapt2, zipalign y apksigner.bat) |
| `git` | Sí | `C:\Program Files\Git\cmd\git.exe` | 2.55.0.windows.1 |
| `dotnet` | Sí | `C:\Program Files\dotnet\dotnet.exe` | SDK 9.0.317 y 10.0.400 |
| `java` / `javac` | Sí | `C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot\bin` | 17.0.20.101 |
| `cl`, `clang`, `cmake`, `ninja`, `msbuild`, `gradle` | No | — | — |

`python` en el PATH (por orden): 1) `C:\Users\AVACOM\AppData\Local\Programs\Python\Python312\python.exe` = 3.12.10; 2) `...\Microsoft\WindowsApps\python.exe` (alias de la tienda, 0 bytes con punto de reanálisis; **no se ejecutó**); 3) `...\Local\Python\bin\python.exe` (administrador de Python, «Python launcher» 26.2); 4) `...\Local\Python\pythoncore-3.14-64\python.exe` = 3.14.6. `py -0p`: 3.14 (por omisión) y 3.12. **Python del venv del backend**: 3.12.10 (`-I -B --version`), `base_prefix` = el Python312 de usuario. `requirements.txt` del backend ya declara `cryptography==50.0.1` y `PyJWT==2.14.0`.

`dotnet --list-runtimes`:

```
Microsoft.AspNetCore.App 8.0.30 / 9.0.19 / 10.0.11
Microsoft.NETCore.App 8.0.14 / 8.0.30 / 9.0.3 / 9.0.19 / 10.0.5 / 10.0.11
Microsoft.WindowsDesktop.App 8.0.30 / 9.0.3 / 9.0.19 / 10.0.5 / 10.0.11
(todos en C:\Program Files\dotnet\shared\...)
```

Android:

- **AVDs** (`emulator -list-avds`, que sólo imprime nombres): `Pixel_10` (único). Su `config.ini`: `x86_64`, `image.sysdir.1 = system-images\android-37.2-beta3\google_apis_playstore_ps16k\x86_64\` (Android beta con páginas de 16 KB). **No se arrancó.**
- **Imágenes de sistema instaladas**: android-36 (android-tv arm64-v8a/x86/x86_64; google-tv x86; google-tv-ps16k x86_64) y android-37.2-beta3 (google_apis_playstore_ps16k x86_64). Plataformas: android-35 y android-36.1. No hay imagen ni plataforma de Android 14.
- **`adb devices`: no se ejecutó**: no había nada escuchando en el puerto 5037 ni procesos `adb`/`emulator`, y `adb devices` habría arrancado el servidor.

---

## D) Huella de hardware de esta máquina (sólo lectura, sin elevar)

Script: `<FASE0>\src\huella.py` (`python -I -B huella.py`; salida en `<FASE0>\logs\huella.txt`). Lee con `winreg`, `ctypes` (`GetSystemFirmwareTable('RSMB', 0, …)`) y consultas CIM de PowerShell 5.1 (`Get-CimInstance`, proceso con `-EncodedCommand`). Proceso no elevado (`IsUserAnAdmin()` = False). Versión de SMBIOS: 3.8, 41 estructuras (tipos 0, 1, 2, 3 y 4 presentes una vez cada uno).

Filtro de basura aplicado: vacío, sólo ceros, sólo `F`, «To be filled by O.E.M.», «Default string», «None», «Not Specified», «System Serial Number», «Chassis Serial Number», «0123456789», «N/A», longitud < 4 o un solo carácter repetido.

### D.1 Los cinco factores (sin valores crudos)

| # | Factor | Fuente | ¿Sin elevación? | Calidad |
|---|---|---|---|---|
| 1 | MachineGuid | registro `HKLM\SOFTWARE\Microsoft\Cryptography` (`winreg`, `KEY_WOW64_64KEY`) | Sí | **Válido**, 36 caracteres, guid (versión 4; 16 bytes distintos) |
| 2 | UUID SMBIOS (tipo 1) | SMBIOS directo (`RSMB`) | Sí | **Válido**, 36, guid (versión 1 con decodificación *mixed-endian*; 16 bytes distintos; no es un relleno conocido) |
| 2 | `Win32_ComputerSystemProduct.UUID` | CIM | Sí | **Válido**, 36, guid |
| 3 | Serie de placa (tipo 2) | SMBIOS directo | Sí | **Basura**: «Default string» |
| 3 | `Win32_BaseBoard.SerialNumber` | CIM | Sí | **Basura**: «Default string» |
| 4 | Serie de chasis (tipo 3) | SMBIOS directo | Sí | **Basura**: «Default string» |
| 4 | `Win32_SystemEnclosure.SerialNumber` | CIM | Sí | **Basura**: «Default string» |
| 4 | `Win32_BIOS.SerialNumber` | CIM | Sí | **Basura**: «Default string» |
| 4 | Serie de sistema (tipo 1) | SMBIOS directo | Sí | **Basura**: «Default string» |
| 5 | `ProcessorId` (tipo 4) | SMBIOS directo | Sí | Válido, 16 caracteres, hex (pero ver D.3) |
| 5 | `Win32_Processor.ProcessorId` | CIM | Sí | Válido, 16, hex |
| — | (extra) serie de CPU (tipo 4) | SMBIOS directo | Sí | **Basura**: «To be filled by O.E.M.» |

**Factores válidos: 3 de 5** (MachineGuid, UUID, ProcessorId) con la regla «el factor es válido si alguna de sus fuentes pasa el filtro» (con la regla estricta en el factor 4 sigue siendo 3). Si se descarta `ProcessorId` por no ser único por unidad (D.3), quedan **2 de 5**.

### D.2 SMBIOS directo frente a CIM

| Comparación | Resultado |
|---|---|
| UUID SMBIOS (directo) frente a `Win32_ComputerSystemProduct.UUID` | **Coinciden: sí**, pero sólo con la decodificación *mixed-endian* de SMBIOS ≥ 2.6. Con el orden de bytes directo no coinciden |
| Orden directo == *mixed-endian* | No (el texto del UUID depende de la decodificación). Con el orden directo saldría «versión 15» (no definida); con *mixed-endian* sale versión 1: la decodificación correcta es la *mixed-endian* |
| Serie de placa SMBIOS == `Win32_BaseBoard` | Sí |
| Serie de chasis SMBIOS == `Win32_SystemEnclosure` | Sí |
| Serie de sistema SMBIOS == `Win32_BIOS.SerialNumber` | Sí |
| `ProcessorId` SMBIOS == `Win32_Processor.ProcessorId` | Sí (1 procesador) |
| MachineGuid == UUID SMBIOS | No (son factores independientes) |
| Series de placa, chasis y sistema entre sí | Iguales (la misma cadena de relleno) |

CIM no aporta nada que SMBIOS directo no dé: los valores son los mismos.

### D.3 `ProcessorId` no distingue unidades

La mitad baja de `ProcessorId` decodifica (como EAX de `CPUID(1)`: familia, modelo, stepping) a la misma familia/modelo/stepping que `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\Identifier` (comprobado: sí). La mitad alta (EDX) son indicadores de funciones. Es decir, **identifica el modelo de CPU, no la unidad**: dos equipos con el mismo procesador dan el mismo valor. No se pudo comprobar con una segunda máquina (ver «Lo que NO se pudo medir»).

### D.4 Tiempos de la lectura

| Lectura | Tiempo |
|---|---|
| MachineGuid (registro) | 1.ª lectura 99 µs; mediana de 50: **18 µs** |
| SMBIOS directo (descarga `RSMB` + análisis) | 1.ª lectura 271 µs; mediana de 50: **95 µs** |
| **Lectura directa completa** (registro + SMBIOS) | **≈ 0,11 ms** (mediana) |
| CIM por PowerShell (proceso completo, 3 ejecuciones) | 3 187 ms, 2 391 ms, 2 562 ms |
| Consultas internas en la 1.ª ejecución (ms) | `ComputerSystemProduct` 614, `BaseBoard` 37, `BIOS` 24, `SystemEnclosure` 24, `Processor` **1 466**, `ComputerSystem` 45 |
| **Lectura completa directa + CIM** | ≈ 2,4 a 3,2 s |

La lectura directa es unas 4 órdenes de magnitud más rápida que CIM y da los mismos valores.

### D.5 Fabricante, modelo y virtualización

- `Win32_ComputerSystem`: **Manufacturer = AVACOM**, **Model = AVACOM5G**, SystemType = x64-based PC.
- `HypervisorPresent` = True, pero **no es una máquina virtual**: el fabricante y el modelo no corresponden a ningún hipervisor conocido y los servicios `vmms` (Hyper-V Virtual Machine Management), `vmcompute`, `HvHost`, `WslService` y `hns` están en ejecución, es decir, Windows corre como partición raíz con Hyper-V/WSL habilitados. (`Win32_Processor.VirtualizationFirmwareEnabled`, `VMMonitorModeExtensions` y `SecondLevelAddressTranslationExtensions` salen False; es una inferencia, no medida, que se deba a que ya hay un hipervisor activo.) Un `HypervisorPresent` verdadero no basta para llamar «virtual» a una máquina.

### D.6 DPAPI de máquina (`CryptProtectData` / `CryptUnprotectData`, ctypes, sin elevar)

Ida y vuelta de 32 bytes aleatorios generados con `os.urandom(32)` (resultado comparado en memoria; no se muestran):

| Prueba | Resultado |
|---|---|
| Bandera `0x4` (`CRYPTPROTECT_LOCAL_MACHINE`), exactamente la pedida | **IGUAL**; blob de 280 bytes |
| `0x5` (`LOCAL_MACHINE` + `UI_FORBIDDEN`) | IGUAL; blob de 280 bytes |
| `0x5` con entropía secundaria de 16 bytes | IGUAL |
| Control: ámbito de usuario (`0x1`) | IGUAL |
| Control negativo: entropía equivocada | Falla como debe: `GetLastError` = 13 (`ERROR_INVALID_DATA`) |
| Control negativo: blob con 1 bit alterado | Falla como debe: `GetLastError` = 13 |
| Velocidad (proteger + desproteger, mediana de 100) | **277 µs** (mínimo 210, máximo 762) |

Por diseño (documentado, **no medido aquí**) un blob de ámbito de máquina puede ser desprotegido por cualquier cuenta local de ese equipo, salvo que se use entropía secundaria; y esa entropía tendría que vivir en el código.

### D.7 TPM

| Prueba (sin elevar) | Resultado |
|---|---|
| `Get-Tpm -ErrorAction Stop` | **Exige elevación**: «Se requiere privilegios de administrador para ejecutar este comando.» |
| `tpmtool getdeviceinformation` | **Funciona sin elevar**: TPM presente (Verdadero), versión 2.0, fabricante INTC (Intel), inicializado, listo para almacenamiento y para atestación, con capacidad de atestación, no requiere borrado, firmware no vulnerable, enlace BitLocker PCR7 posible, no bloqueado |
| `NCryptOpenStorageProvider("Microsoft Platform Crypto Provider")` | **Se abre sin elevar**; `Impl Type` = `0x1` (HARDWARE) |
| `NCryptOpenStorageProvider("Microsoft Software Key Storage Provider")` (control) | Se abre; `Impl Type` = `0x22` (SOFTWARE) |

Sólo se abrió el proveedor; **no se crearon claves** (ver «Lo que NO se pudo medir»). Script: `<FASE0>\src\tpm_pcp.py`.

---

## E) Rendimiento de la criptografía en Python

Script: `<FASE0>\src\cripto.py` (`python -I -B cripto.py`; salidas `<FASE0>\logs\cripto1.txt` y `cripto2.txt`). Python 3.12.10, `cryptography 50.0.1` enlazado con **OpenSSL 4.0.2 (25 Aug 2026)**. Mediana (y p95) de **2000 repeticiones** tras 100 de calentamiento, en **microsegundos**. Se hicieron dos pasadas completas para ver la variación entre pasadas, que resultó notable (CPU híbrida de 22 hilos lógicos y una carga de fondo de 6–19 %).

| Operación | Pasada 1: mediana / p95 | Pasada 2: mediana / p95 |
|---|---|---|
| Ed25519 firmar, 600 B | 40,7 / 59,0 | 33,9 / 48,3 |
| Ed25519 verificar, 600 B (clave ya cargada) | 120,7 / 254,8 | 92,4 / 163,1 |
| Ed25519 firmar + verificar, 600 B | 207,5 / 304,3 | 126,4 / 192,8 |
| Ed25519 cargar clave pública (32 B) + verificar | 124,0 / 224,9 | 109,9 / 216,0 |
| Ed25519 sólo cargar la clave pública | 3,6 / 4,6 | 2,1 / 2,4 |
| SHA-256 de 1 MB (`hashlib`) | 570,0 / 895,3 | 575,7 / 1 041,9 |
| SHA-256 de 1 MB (`cryptography` `hashes.Hash`) | 812,5 / 1 360,2 | 768,3 / 1 128,0 |
| SHA-256 de 600 B (`hashlib`) | 1,6 / 2,5 | 1,8 / 1,9 |
| HKDF-SHA256 (IKM 32 B, sal 16 B, info 16 B, salida 32 B) | 11,1 / 14,9 | 10,9 / 14,3 |
| HMAC-SHA256, 600 B (`cryptography` `hmac.HMAC`) | 3,7 / 5,0 | 6,6 / 7,4 |
| HMAC-SHA256, 600 B (`hmac.digest` de la biblioteca estándar) | 7,8 / 9,8 | 7,9 / 9,1 |

Importación en frío de `cryptography.hazmat.primitives.asymmetric.ed25519` (proceso nuevo, 11 ejecuciones por pasada, caché de disco caliente):

| Medida | Pasada 1 | Pasada 2 |
|---|---|---|
| Sentencia `import` dentro del hijo: 1.ª / mediana / mín. / máx. (µs) | 41 517 / **47 614** / 40 762 / 56 729 | 38 720 / **44 159** / 38 720 / 85 919 |
| Proceso completo con el `import` (reloj de pared, mediana, µs) | 97 523 | 87 836 |
| Proceso vacío `python -I -c pass` (mediana, µs) | 43 744 | 43 207 |
| Diferencia (con `import` − vacío) | 53 779 | 44 629 |

Lectura: verificar una firma Ed25519 cuesta ≈ 0,1 ms y el hash de 1 MB ≈ 0,6 ms; el coste dominante es la **importación en frío (≈ 45–50 ms)**, que no se paga de nuevo si el backend ya importa `cryptography` (está en `requirements.txt`). Los máximos (varios ms) son probablemente ruido del planificador y no del algoritmo (inferencia: no se aisló la causa).

---

## Lo que NO se pudo medir y por qué

- **Unicidad entre máquinas** (UUID de SMBIOS, `ProcessorId`, MachineGuid): sólo hay una máquina. No se sabe si el UUID o el MachineGuid se repiten en equipos clonados ni cuántas unidades comparten `ProcessorId` (por construcción, todas las del mismo modelo de CPU). Haría falta una muestra de la flota.
- **Estabilidad de los factores** ante reinstalación de Windows, restauración de imágenes, cambio de placa o de BIOS: exige cambios destructivos que no se hicieron.
- **Aspecto real de las series de fábrica en las tabletas Android** y en otros modelos de AVACOM: sólo se midió este equipo; no hay tabletas ni se ejecutó nada en Android.
- **DPAPI desde otra cuenta o servicio** (LocalSystem, otro usuario): sólo se probó un proceso de usuario estándar. Que cualquier cuenta local pueda desproteger un blob de máquina es comportamiento documentado, no medido.
- **TPM**: `Get-Tpm` no se pudo usar sin elevar; no se crearon claves ni se sellaron datos con el proveedor de plataforma (habría creado claves persistentes fuera de la carpeta de trabajo); tampoco se midió la creación de claves por un usuario estándar.
- **Android**: no se ejecutó ningún binario. Los `.so` y los ejecutables se verificaron sólo de forma estática (`llvm-readelf`). No se arrancó el AVD `Pixel_10` ni se ejecutó `adb devices` (el servidor `adb` no estaba arrancado y habría arrancado). No hay imagen de Android 14 ni tableta para probar; el único AVD usa una imagen beta de 16 KB (Android 37.2-beta3).
- **Que Android 15+ acepte los `.so` de 16 KB** y la alineación del APK (`zipalign -P 16`): sólo se comprobó la alineación `0x4000` del ELF y que `zipalign` admite `-P 16`.
- **UBSan y ASan en ejecución**: UBSan de Android no se ejecutó (sin dispositivo). ASan de MSVC sí se ejecutó, pero con un programa de una sola función.
- **Aplicación real de CET/CFG**: las banderas están en el binario, pero `python.exe` no activa la pila sombra en modo estricto; no se midió si el sistema las impone al cargar la DLL desde Python.
- **Compilación para otros destinos**: sólo x64 con `cl`; no hay compilador cruzado a ARM64 (`Hostx64\arm64` no existe) y no se probó x86. Con el NDK sólo aarch64 y x86_64 (no armv7a/i686/riscv64).
- **VS 2022**: no se pudo probar; su instalación de C++ está incompleta (sin `vcvarsall.bat`, cabeceras ni bibliotecas) y no se arregló.
- **Importación en frío desde disco** (sin caché de archivos): requiere vaciar la caché del sistema (privilegios de administrador); la medida es con la caché caliente y el entorno ya usado por el backend.
- **Firma de código, SmartScreen y antivirus** sobre la DLL sin firmar: no se firmó ni se midió; `signtool.exe` sí está en el SDK 10.0.26100.0.
- **Rendimiento con carga controlada**: otra sesión podía correr pruebas del backend; el ruido (±25 % entre pasadas, máximos de ms) no se pudo eliminar sin parar esa sesión.

---

## Archivos generados (todo bajo `<FASE0>`)

- Informe: `mediciones.md`.
- Fuentes: `src\hola.c`, `canario.c`, `defecto.c`, `asan_test.c`, `cargar_dll.py`, `huella.py`, `uuid_calidad.py`, `tpm_pcp.py`, `cripto.py`.
- Guiones: `run_msvc18.bat`, `run_msvc2022.bat`, `pasos_msvc.bat`, `ejecutar_msvc18.bat`, `extra_msvc.bat`, `pasos_ndk.bat`, `extra_ndk.bat`.
- Salidas: `vswhere.json`, `logs\*.log|txt`, `msvc18\*` (binarios y salidas de `dumpbin`), `ndk\arm64-v8a\*` y `ndk\x86_64\*` (binarios y salidas de `llvm-readelf`).
- Ajenos a esta fase, **no creados por estas mediciones** y dejados intactos: `listar_rutas.py` y `rutas.tsv` (aparecieron en esta carpeta a las 09:46, escritos por otro agente que comparte el directorio de trabajo).
