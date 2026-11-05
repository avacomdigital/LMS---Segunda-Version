# 15 · Licenciamiento (MOD-018) · Segunda protección: dispositivo AVACOM, puerta de instalación y backend cifrado

| Campo | Valor |
|---|---|
| Estado | **Fases S0, S1 y S2 construidas y probadas sin administrador ni hardware de panel** (2026-10-26). **2026-10-28: el cifrado ya está integrado en `Build-Installer.ps1` y hay un instalador de PRUEBAS 2.17.0** (§6.1). Sin commit. Quedan S3 a S6 |
| Alcance decidido por el CTO (SQ) | **Sólo AVACOM OPS Master** (SQ-07: Student no entra por ahora) · hardware de una fábrica con convenio AVACOM (SQ-03) · Windows 10/11 y Android 14 (SQ-01; el Android queda fuera mientras Student no entre) · gracia de 30 días (SQ-02, ver §7: choca con el cifrado del código) |
| Prompt de origen | [segunda-protección.md](segunda-protecci%C3%B3n.md) (premisas SP-01…11, reglas SR-01…10, preguntas SQ-01…08) |
| Piezas | `backend/licenciamiento/dominio/sello.py` · `tools/licencias/avacom_licencias/{sellos,cli_sello}.py` · `installer/src/host/Dispositivo/` · `installer/src/payload/avacom_boot.py` · `installer/build/{Build-Installer.ps1,Cifrar-Backend.py,Buscar-Llave.py,Ensayar-Dispositivo.ps1,Ensayar-ClaveDelPaquete.ps1}` |

## 0 · Lo que se promete y lo que no (SP-01)

«No copiable» absoluto no existe y este diseño no lo dice. Lo que **sí** se promete, y cómo se comprobó:

| Promesa | Qué la sostiene | Qué NO cubre |
|---|---|---|
| Una copia de la instalación y de la carpeta de datos **no arranca** en un equipo que no sea el sellado | El código viaja cifrado; la llave `K` sólo la desenvuelve la clave RSA **no exportable** del TPM del equipo (S2) | Un administrador **del equipo legítimo** que vuelque la memoria del proceso (A4); un ataque físico a un TPM discreto |
| Instalar en un equipo sin sello AVACOM **se niega** | Puerta del instalador + sello firmado + prueba de posesión de la clave (S1) | Parchear el instalador o el Host: por eso la protección real es la liberación de la clave, no el `if` (SP-05) |
| Abrir `Backend\` no enseña código | Cero `.py` y cero `.pyc`; `codigo.avpkg` cifrado con AES-256-GCM, también el índice | Un experto con tiempo y un volcado de memoria; los **datos** (JSON de llaves públicas, atestación) siguen en claro |
| Una fuga se puede atribuir | **Pendiente** (marca por dispositivo, §6) | — |

## 1 · S0 · Línea base y supuestos

**Estado del repo.** Rama `feature_encapsulacion`, instalador 2.16.0, `04-proteccion.md` y `08-identidad-de-dispositivo.md` sin commit (de otras sesiones; no se tocaron). Este trabajo añade archivos nuevos y cambios aditivos en `Program.cs`, `ProcesoBackend.cs`, `Preparar.cs`, `Soporte.cs`, `Rutas.cs`, `Avacom.Ops.Host.csproj`, `Build-Installer.ps1`, `AvacomOpsMaster.iss` y `codigo.iss`.

**El ataque de hoy (paquete sin proteger, `dist/staging`, medido en este equipo).**

| Medida | Valor |
|---|---|
| `.py` del backend en el paquete | **732** (742 archivos, 7,5 MB; Runtime 174 MB, App 246 MB) |
| Localizar las vistas de DRF (`grep APIView\|ViewSet`) | **0,11 s** |
| Localizar `SECRET_KEY` | **0,13 s** |
| `manage.py check` (arranque frío del backend, equipo de desarrollo) | ver §5 (medido plano y cifrado) |

**TPM del equipo de desarrollo** (sin elevar): TPM 2.0, fabricante Intel (firmware, *PTT*, versión 700.19.15.2544), no discreto, listo para atestación. `Get-CimInstance Win32_Tpm` exige administrador. El proveedor de plataforma de CNG sí crea claves de usuario (EC P-256 en 296 ms, RSA-2048 en 2,3 s) y `Impl Type` = hardware. **Las claves de ÁMBITO DE MÁQUINA se niegan sin elevar** («Acceso denegado»): el instalador y el servicio (administrador/SYSTEM) sí podrán; **no se probó elevado** (§8).

**Supuestos [sin verificar] del prompt.**

| Supuesto | Resultado |
|---|---|
| (a) Quién puede pedir atestación de identificadores en Android | **No confirmado**: la página de AOSP (*Key and ID attestation*) sólo dice que se pide con las etiquetas `ATTESTATION_ID_*` y que falla con `CANNOT_ATTEST_IDS` si el equipo no lo soporta; no menciona `setAttestationIds`, dueño de dispositivo ni permisos. Queda abierto. Irrelevante hoy (Student fuera de alcance) |
| (b) Atestar un TPM de Windows | `PCP_EKPUB` se lee sin elevar (283 bytes, estructura del TPM, **no** SPKI). `PCP_EKNVCERT` devuelve 8 bytes (un puntero/índice NV, no el certificado). `PCP_WINDOWS_ATTESTATION` no existe en este equipo (0x80090029). La página de Microsoft de propiedades de NCrypt **no documenta** las `PCP_*`. `TPM2_MakeCredential/ActivateCredential` no se probó (sin librería de TPM 2.0 y sin administrador). Ver §3, evidencia «activación» pendiente |
| (c) SQLCipher | Confirmado en la página de diseño de Zetetic: AES-256-CBC por página, IV aleatorio por escritura, HMAC-SHA512 por página, sal de 16 bytes, PBKDF2-HMAC-SHA512 con 256 000 iteraciones por defecto, y opción de **clave cruda**. Pendiente de S4 |
| H-3 · la MAC no autentica | Confirmado **por el código**: la huella del equipo (`dominio/huella.py`) no usa la MAC y el veredicto del sello tampoco (pruebas `test_cambiar_mac_serie_modelo_no_cambia_el_veredicto` y `LaMacYElSerieNoDecidenNada`). **No se cambió la MAC de un adaptador real**: habría que tocar la red del equipo del usuario (anotado en §8). Este equipo trae adaptadores con MAC distinta por red (Wi-Fi) y uno virtual de Hyper-V |

> **Sobre SQ-01 («sólo podemos asegurarnos de la MAC»).** La MAC no puede autenticar un dispositivo: se cambia, viaja en claro y se copia con la instalación; en Android 11+ ni se puede leer. Por eso el sello sigue a **una clave del TPM**, y la MAC viaja sólo como dato informativo. Si la fábrica puede grabar algo en el firmware (SQ-01), lo útil sería que **registre la huella de la EKPub de cada TPM en el inventario** que entrega a AVACOM (ver §3).

## 2 · S1 · El sello de dispositivo

Mismo envoltorio TLV de la licencia (`tlv.py`): firma Ed25519 sobre todo lo anterior, verificada **antes** de leer ningún campo. Llave propia `sello-…` (SP-07), distinta de `prod-2026-1` (licencias) y `upd-2026-1` (publicación); el verificador **rechaza** un sello firmado con otro `kid`.

| Archivo | Magic | Para qué |
|---|---|---|
| `.avsol` | `AVSO` | Solicitud del equipo: su clave de identidad (EC P-256), su clave de cifrado (RSA-2048), la EKPub si el TPM la da, serie, modelo y MAC (informativas). La **firma el propio equipo con su clave del TPM** (prueba de posesión) |
| `.avsello` | `AVSL` | El sello: `clave_huella` (SHA-256 del SPKI de la clave de identidad), `origen` (fábrica / entrega), `evidencia` (inventario / EKCert / activación), vencimiento opcional (0 = no vence, SQ-05), huellas de la clave de cifrado y de la EKPub, serie, modelo, lote, MAC (informativos) |
| `.avrev` | `AVRV` | Lista de revocados (huellas de clave), con número que sube; el nodo guarda la más nueva |
| `.avclave` | `AVKY` | La llave `K` de **una versión** del paquete, envuelta (RSA-OAEP-SHA256) para **un** equipo (S2) |

**Veredictos** (idénticos en Python, `sello.evaluar`, y en C#, `FormatoSello.Evaluar`): `autenticado` · `sin_sello` · `sello_invalido` (firma, `kid`, formato, vencido) · `clave_distinta` (otra clave o no supo firmar el reto) · `revocado` · `no_verificable` (el equipo no pudo mostrar su clave: **fallo del sistema, no fraude**, SR-03). Códigos de salida del Host: 0 / 40 / 41 / 42 / 43 / 44.

**Verbos del Host** (`Avacom.Ops.Host.exe`; sin teclado: USB y archivos): `solicitar-sello [carpeta] [--serie X]` · `instalar-sello [ruta]` (toma `.avsello`, `.avrev` y `.avclave` de una ruta o de la memoria USB, **verifica antes de guardar** y no pisa un sello bueno con basura ni una lista de revocados nueva con una vieja) · `verificar-dispositivo` (escribe `Config\dispositivo.json`, sin datos de personas ni licencias) · `puerta-instalacion` · `probar-liberacion`.

**Estación de aprovisionamiento** (`tools/licencias`, misma custodia que `07-ceremonia-de-llaves.md`): `sello emitir`, `sello ver`, `sello revocar`, `sello revocados ver`, `clave emitir`. Se **niega a firmar**: una solicitud alterada o firmada con otra clave; una serie fuera del inventario («no es un dispositivo AVACOM conocido»); una EKPub que no es la que el inventario registra para esa serie; una serie que ya tiene sello (salvo `--reemitir`); un registro de emisiones alterado; y una llave que no sea `sello-…`.

**Puerta del instalador.** `InitializeSetup` (en `codigo.iss`, sólo si el build trae llaves de sello) extrae el Host a `{tmp}`, ejecuta `puerta-instalacion` y, si no es `autenticado`, **no instala** y muestra un mensaje claro con una salida humana (el Host deja la solicitud en la memoria USB para llevarla a AVACOM). No hay parámetro de línea de comandos que apague la puerta (SP-10); el modo de desarrollo es un archivo `%ProgramData%\AVACOM\AVACOM-DESARROLLO` **cuyo dueño debe ser Administradores o SYSTEM** (un usuario estándar puede crear el archivo, no ser su dueño como administrador). Compilado, el Host dentro de `{tmp}` **no duplica el tamaño** del instalador (Inno guarda una sola vez el mismo archivo: 113 805 636 B con puerta frente a 113 805 241 B sin ella).

### Decisiones

| | Decisión | Por qué |
|---|---|---|
| **SD-1** | La evidencia del sello es **«inventario»**: AVACOM autorizó *esa serie* con *esa clave*. La activación de credencial del TPM (que prueba que la clave vive en el mismo TPM que la EKPub) queda como evidencia 3, **pendiente** | Sin ella, una solicitud fabricada con la serie y la EKPub (ambas públicas) de un equipo legítimo podría engañar a la estación. Mitigaciones hoy: la serie debe estar en el inventario y se sella **una sola vez** (`--reemitir` deja rastro y obliga a revocar); en fábrica la estación corre en un entorno controlado. **Riesgo residual aceptado hasta implementar la activación** |
| **SD-2** | Las claves del equipo viven en el **almacén de la máquina** (las usan el instalador, el servicio SYSTEM y OPS), proveedor de plataforma (TPM) y, si no hay, software, con exportación «ninguna» | Una clave de usuario no la podría abrir SYSTEM |
| **SD-3** | Un ensayo del instalador usa claves de **usuario** con un nombre derivado de su carpeta de datos, nunca las de la máquina, y la «memoria USB» es una carpeta (`AVACOM_OPS_USB`) | SR-10: un ensayo no toca el equipo ni necesita elevarse |
| **SD-4** | El sello **no vence** y se revoca con una lista firmada (SQ-05 por omisión) | Sin internet en el aula, renovar sería otra entrega; la lista viaja con licencias y actualizaciones (la distribución con `.avlic`/`.avupd` queda pendiente) |

## 3 · Cómo se prueba la identidad: lo que el diseño pide a la fábrica (SQ-01, SQ-03)

El modelo de confianza más fuerte de Microsoft para TPM es la **lista de EKPub permitidas** (inventario uno por uno). Como el hardware sale de una fábrica con convenio con AVACOM, lo ideal es que **la fábrica entregue, por cada unidad, serie + huella SHA-256 de la EKPub** (el mismo valor que lee `PCP_EKPUB`), y que **ejecute `solicitar-sello` en la línea** (origen «fábrica»). El inventario (`inventario.json`) es custodia de AVACOM y **no viaja en ningún instalador**.

## 4 · S2 · Liberación de la llave del paquete

```
 build (Cifrar-Backend.py, con el Python embebido)              equipo sellado (Host)
 ─────────────────────────────────────────────────              ─────────────────────
 compila cada .py a bytecode y lo cifra (AES-256-GCM,           lee Config\sello\paquete-<kid>.avclave
   llave por módulo = HKDF(K, ruta); la ruta es dato asociado)    verifica su firma (llave de sello)
 cifra también el índice (los nombres de los módulos)             comprueba que es PARA este paquete y ESTA clave de cifrado
 borra los .py   →  Backend\codigo.avpkg                          el TPM desenvuelve K (RSA-OAEP-SHA256)
 K → archivo de custodia FUERA del paquete                        K viaja a python por la ENTRADA ESTÁNDAR (no por entorno, ni línea, ni disco)
                                                                  avacom_boot.py abre el paquete y pone un buscador de módulos delante del de Python
```

* Se libera **sólo si** el equipo es `autenticado` (sello válido, clave presente y firmando, no revocado).
* `avacom_boot.py` es público por diseño (no lleva ningún secreto). Resuelve lo que Django necesita sin archivos `.py`: buscador de módulos (`sys.meta_path[0]`) y gancho de rutas (`sys.path_hooks[0]`) para que `pkgutil.iter_modules` liste migraciones y comandos de `manage.py`; `__file__` apunta a la carpeta real, así que los datos JSON de al lado se encuentran igual.
* Todos los puntos por donde el Host lanza Python pasan por `ProcesoBackend.Preparar`; el paquete cifrado se activa **sólo si existe `Backend\codigo.avpkg`** (un paquete sin él, o uno anterior, funciona como siempre).

| | Decisión | Por qué |
|---|---|---|
| **SD-5** | AES-256-GCM de `cryptography` (ya en el runtime) en lugar de XChaCha20-Poly1305 de `avacom_lic` | El cargador es Python y descifra ~800 módulos al arrancar: la nativa por `ctypes` y un XChaCha en Python puro costarían segundos. Criptografía estándar, ninguna propia |
| **SD-6** | Una `K` **por versión**, envuelta **por equipo** en un `.avclave` | Con sólo OPS Master (un equipo por aula, SQ-07) entregar un archivo por aula y versión es barato; una `K` filtrada abre sólo esa versión |
| **SD-7** | Se cifra **bytecode**, no fuente | Arranca más rápido que compilar y no deja `.py`; ata el paquete a la versión exacta de Python del runtime (el lector lo comprueba y el cifrador corre con el Python embebido) |

**Lo que cambia para quien depura:** los *tracebacks* ya no muestran el texto de las líneas (el código no tiene fuente en disco); los nombres de archivo y los números de línea sí.

## 5 · Resultados

| Qué | Resultado |
|---|---|
| Suite del backend **plana** (línea base, 2026-10-26) | **2794** pruebas, 18 omitidas, 1102 s; **1 error ajeno**: `backend/requirements.txt` quedó en UTF-16 con BOM y `reporting.tests.test_arquitectura` no puede leerlo |
| Suite del backend **desde el paquete cifrado** (825 módulos, cero `.py`; árbol con forma de repositorio: `.git`, `spec-driven`, `tools`, `installer`) | **2794** pruebas, 33 omitidas, 1156 s; **30 no pasan, todas explicadas**: 25 errores y 3 fallas de `test_arquitectura` y `test_concurrencia` (leen los `.py` del disco o lanzan un Python hijo sin el cargador: no aplican a un paquete sin fuentes) y 2 fallas de `test_vectores_sello` (buscan el archivo de vectores junto a las pruebas del Host, que el árbol de ensayo no copia). **Ninguna falla de comportamiento del producto** |
| Primera corrida cifrada (descartada) | 844 fallas y 440 errores por **mi montaje** (copia fuera del repositorio: sin `.git` el nodo se tomó como producción y rechazó las llaves de desarrollo; sin `spec-driven`). No dice nada del cargador |
| Pruebas nuevas | Backend: `test_sello` 26 · `test_vectores_sello` 4 · `test_paquete_cifrado` 8 (alteración en cualquier parte, llave equivocada, módulo cambiado de sitio, importar y listar migraciones desde otro proceso) · Estación: 18 (118 con las anteriores) · Host: **50** (16 de antes + 34: vectores, puerta, instalación, claves CNG reales con TPM, liberación) |
| Mutaciones del sello | 20 000 con semilla fija, **0 aceptadas**; 300 más en los vectores compartidos Python↔C#, mismo veredicto y motivo |
| `Ensayar-Dispositivo.ps1` (Host, TPM y estación reales) | **19 de 19** |
| `Ensayar-ClaveDelPaquete.ps1` (backend real de `dist\staging` cifrado) | **22 de 22**: sin sello no abre (40) · con sello y clave arranca y `/health/` responde · `K` en ningún archivo de datos ni registros · copia a un equipo sin claves (44) o con otras (42): no arranca · sello propio con la clave de otro equipo: no se libera · revocado (43) · un byte cambiado en `codigo.avpkg`: no arranca |
| Arranque hasta `/health/` (Host real, `preparar` hecho) | plano **6,2 s** · cifrado **3,9 s** (menos que el plano: no compila fuentes) · en otra corrida 4,6 s y 3,2 s |
| Verificar el sello con el TPM real | **209 ms** (incluye firmar el reto en el TPM); no está en el camino de cada petición |
| Tamaño | `codigo.avpkg` 8,9 MB frente a 7,5 MB de fuentes · el instalador crece **395 bytes** con la puerta |

El ensayo F descubrió un defecto del primer diseño: con un byte cambiado en el último módulo el nodo arrancaba (cada módulo se autentica al importarlo). Ahora el índice autenticado lleva el SHA-256 de **todos** los datos y se comprueba al abrir.

## 6 · Pendiente

* **Marca por dispositivo / atribución** (SP-09): no se hizo.
* **S1.6 · garantía «sellado» en `device_manager`**: no se hizo. La clave de identidad que OPS presenta hoy (Fase 5, de usuario) no es la del sello (de máquina); unificarlas exige probar la ACL de una clave de máquina con un usuario estándar (necesita administrador). Diseño: el backend ya puede verificar un sello por sí mismo (`sello.evaluar`); falta elegir el origen de la clave pública y añadir el nivel.
* **S1.7 Android**: fuera de alcance (SQ-07).
* **Actualizaciones `.avupd`** con el código cifrado: el paquete nuevo `codigo.avpkg` es un archivo más del paquete firmado, pero hace falta (a) una `.avclave` para la `K` nueva **antes** de aplicarla y (b) que `Aplicador.cs` compruebe que la liberación funcionará para evitar dejar un nodo sin arrancar. No se tocó `actualizacion`.
* ~~**Integración con `Build-Installer.ps1`** del cifrado~~ — **HECHO el 2026-10-28**, ver §6.1.
* **La ceremonia de la llave de sello `sello-2026-1`** (SQ-08): no se hizo (necesita la frase del CTO). `claves/sello/produccion.json` está vacío; un instalador de producción compilado hoy **sale sin puerta** y lo avisa (`-ExigirPuertaDeDispositivo` lo rechaza).

### 6.1 · Integración del cifrado en `Build-Installer.ps1` (2026-10-28)

**Qué hace el build ahora.** Si hay llave pública de sello (hay puerta), después del ensayo del paquete (7b) corre el paso **7c**:

1. Publica el **Host definitivo** con las llaves de sello incrustadas (`-p:ClavesDeSello=`) encima del de ensayo.
2. **Cifra** `dist\staging\Backend` con el Python **embebido** de `Runtime\Python` (`-B -I Cifrar-Backend.py --eliminar-fuentes --exigir-cero-py`): deja `Backend\codigo.avpkg`, sin `.py`.
3. Copia `avacom_boot.py` a `Runtime\`.
4. Guarda la llave `K` en un archivo de **custodia** (`-CustodiaDeLlaveDelPaquete`; por omisión `%USERPROFILE%\AVACOM-Llaves\paquete\k-<versión>-<rev>-<fecha>.hex`). El build **se niega** si esa ruta está dentro del repositorio, de `dist\staging` o de `installer\latest`, o si el archivo ya existe (una `K` es de un paquete: no se pisa).
5. Anota en `manifiesto.json` `codigo_cifrado`, `kid_llave_del_paquete` (el identificador público, nunca `K`), `sha256_codigo_avpkg` y `python_del_bytecode`, y **vuelve a sellar** el paquete (`Sellar-ElPaquete`: `integridad.json` y `manifiesto.firma.json` se calculan sobre el paquete ya cifrado).
6. Falla si: queda un `.py`, `.pyc`, `.pyo` o `__pycache__` en `Backend\`; falta `codigo.avpkg` (o mide menos de 1 MB); `manage.py` o `settings.py` siguen en claro; `K` aparece (en bruto, hex, HEX, base64, base64url o UTF-16) en cualquier archivo de `dist\staging` (`Buscar-Llave.py`) o en el `.exe`; o `integridad.json` lista código de `Backend\` en claro o no lista `codigo.avpkg` y `avacom_boot.py`.
7. Con la privada de la llave de sello (sólo un build de pruebas: `-LlaveDeSelloDePrueba` y `-FraseDeSelloDePrueba`) corre, **contra el paquete que salió**, `Ensayar-ClaveDelPaquete.ps1 -Staging … -ClaveDelPaquete … -LlaveDeSello …` y `Ensayar-Dispositivo.ps1 -HostExe … -LlaveDeSello …`. Sin esa privada (producción) los omite y **lo avisa**: se corren donde esté la estación de aprovisionamiento.

**Decisiones del build.**

| | Decisión | Por qué |
|---|---|---|
| **B-1** | `Ensayar-Paquete.ps1` (7b) corre sobre el código **en claro**, **antes** de cifrar, y con un Host **sin** llaves de sello | El Update Manager y `manage.py` del ensayo leen y escriben `.py`/migraciones, y un Host con puerta no levanta el servicio en un equipo sin sello (ni siquiera uno de ensayo: lo descubrió el primer intento, `AVC-UEFI-01`). Sólo cambia la constante de las llaves; el Host definitivo se publica en 7c y el ensayo que lo ejercita con su sello es el de la puerta |
| **B-2** | La lista de integridad y la firma se calculan **después** de cifrar (y se rehacen: se sella dos veces) | Lo que el nodo verifica es lo que viaja |
| **B-3** | Sin llave de sello **no se cifra** | Un paquete cifrado sin puerta no arrancaría nunca (nadie libera `K`). El build avisa que el código sale en claro; `-SinCifrarElCodigo` lo pide a propósito |
| **B-4** | `-ExigirPuertaDeDispositivo` cuenta **sólo** `claves\sello\produccion.json`: no acepta `-ClavesDeSelloDePrueba` ni `-SinCifrarElCodigo` | La ceremonia `sello-2026-1` es del CTO; una llave de prueba no puede hacer pasar por buena una entrega |
| **B-5** | `Ensayar-ClaveDelPaquete.ps1`/`Ensayar-Dispositivo.ps1` aceptan el paquete del build (`-Staging`, `-ClaveDelPaquete`, `-HostExe`, `-LlaveDeSello`; la frase por `AVACOM_FRASE_SELLO_ENSAYO`, nunca por argumento) y terminan con `exit 0` explícito | El `$LASTEXITCODE` de un `robocopy` previo no puede pasar por un «bien» |

**Producción sin puerta = no compila (comprobado).** `claves\sello\produccion.json` está vacío (`"claves": []`, 337 bytes). `Build-Installer.ps1 -ExigirPuertaDeDispositivo` en el árbol principal falla en el paso 1 con «No hay ninguna llave pública de SELLO … -ExigirPuertaDeDispositivo no acepta una llave de prueba en su lugar», sin escribir nada en `installer\latest`. Sin la bandera, el mismo build **avisa** («sale SIN la puerta … y con el código en claro»).

**Receta del instalador de PRUEBAS (no toca `installer\latest` ni las llaves reales).**

1. `git worktree add --detach C:\avt\r4 HEAD`; copiar (byte a byte) los archivos modificados y sin seguimiento del árbol **sólo los de este trabajo** (no el de otras sesiones); `mklink /J C:\avt\r4\backend\.venv <venv de este repo>`.
2. Llave de sello de prueba: `tools\licencias\iniciar.py claves generar --kid sello-prueba-1 --salida C:\avt\claves-sello` con una frase aleatoria sólo en `AVACOM_EMISOR_FRASE` del proceso; guardar la frase en un `.frase.dpapi` (`ConvertFrom-SecureString`). La pública va **sólo en el worktree**, en `backend\licenciamiento\claves\sello\produccion.json`.
3. Llave de publicación de prueba `upd-prueba-1` (`tools\actualizacion\iniciar.py llaves nueva --kid upd-prueba-1`), su pública como «siguiente» en `backend\actualizacion\claves\produccion.json` **del worktree**.
4. Desde el worktree: `Build-Installer.ps1 -OmitirPruebas [-OmitirApp] -LlaveDePublicacion … -FraseDeLaLlave … -CustodiaDeLlaveDelPaquete C:\avt\custodia\k-2.17.0-prueba.hex -LlaveDeSelloDePrueba … -FraseDeSelloDePrueba …`. `-OmitirPruebas` porque el guardia de arquitectura de `actualizacion` y la prueba de llaves de sello fallan a propósito con llaves extra; la suite del backend se corre aparte en el árbol principal. **No** usar `-ExigirLlaveDeProduccion` ni `-ClavesDeSelloDePrueba`: con la pública de prueba en `produccion.json` del worktree, el build la trata como la lista de sello.
5. Entregar el `.exe`, su `SHA256.txt` y `LEEME-PRUEBA.txt` («firmado con llaves de PRUEBA, no es para clientes») en una carpeta propia (`C:\avt\salida-2.17.0-prueba\`); la custodia de `K` y la privada **no** salen de `C:\avt\custodia` y `C:\avt\claves-sello`.

**Resultado del build de pruebas 2.17.0** (HEAD 61bc592a + el árbol de este trabajo, 36 archivos sin confirmar):

| Qué | Resultado |
|---|---|
| Ensayo del paquete en claro (7b, 127 comprobaciones del bloque F más A–G) | todo correcto. **Un intento previo falló en F7** («el nodo arranca con el programa nuevo», espera de 120 s) y no volvió a fallar: el bloque F repetido solo (`-SoloActualizaciones`, 127 `[ok]`, 0 fallas) y el build completo siguiente pasaron. Lo trato como intermitente por carga, **sin causa raíz demostrada** |
| `Ensayar-ClaveDelPaquete.ps1` contra el paquete cifrado del build | **25 de 25** (sin sello no abre; con sello y `K` arranca y `/health/` responde en 3,9 s; `K` en ningún archivo de datos; otro equipo 44/42; sello propio con la clave de otro; revocado 43; un byte cambiado: no arranca; sin variable UEFI 47) |
| `Ensayar-Dispositivo.ps1` con el Host del paquete | **27 de 27** |
| `Backend\` del paquete | 0 `.py`, 0 `.pyc`/`.pyo`, 0 `__pycache__`, `codigo.avpkg` 9 512 036 B (781 módulos); `manage.py` ya no está |
| `K` | no aparece en ningún archivo de `dist\staging` ni en `installer\latest` (7101 archivos, 555 681 196 B revisados) |
| Integridad y firma | `integridad.json` (6376 archivos) coincide con el disco, lista `codigo.avpkg` y `avacom_boot.py` y ningún `.py` de `Backend\`; el manifiesto verifica con `upd-prueba-1` y **no** con `upd-2026-1` |
| Puerta en el `.exe` | el mismo asistente compilado sin `/DPuertaDeDispositivo` pesa **417 bytes menos** (121 911 342 B frente a 121 911 759 B): `InitializeSetup` y el Host en `{tmp}` van dentro. No se abrió el asistente |
| `dotnet test` del Host (`tests/Avacom.Ops.Host.Tests`) | **89 correctas**, 0 fallas |

## 7 · Gracia de 30 días (SQ-02) frente al cifrado del código — **DECIDIDO: opción A (2026-10-26)**

> **Decisión del CTO:** la gracia de 30 días aplica **solo a la licencia**; el código cifrado **exige el TPM**. No existe gracia para abrir el código sin él. Consecuencia operativa: un nodo en marcha no se detiene, pero un reinicio tras borrar el TPM o cambiar la placa exige que AVACOM reemita el sello y la `.avclave` (con S4, además, la llave de recuperación de la institución). El texto que sigue es el análisis que llevó a la decisión.

La licencia tiene gracia porque no depende de ningún secreto del equipo. **El código cifrado sí depende de él**: si el TPM se borra o la placa se cambia, el servicio no puede liberar `K` y **no arranca**. Una «gracia» que deje abrir el código sin el TPM (por ejemplo, guardar `K` protegida con DPAPI de máquina durante 30 días) **anula la protección contra copiar el disco** durante esos 30 días, porque los secretos de DPAPI de máquina viajan con el disco clonado.

Lo implementado: **un nodo que ya está corriendo no se detiene** (`K` está en memoria) y los datos (la base) **no están cifrados** todavía, así que nada del expediente se pierde; **un reinicio sin TPM sí exige** que AVACOM reemita sello y `.avclave` para la clave nueva. Opciones: **(A, recomendada)** dejarlo así y aplicar los 30 días sólo a la licencia; **(B)** gracia de 30 días con una `K` guardada para el equipo (pierde la protección contra clonado esos días). Hace falta su decisión antes de S4 (cuando la base se cifre, un TPM perdido sí podría dejar el expediente ilegible: ahí la llave de recuperación bajo custodia de la institución es obligatoria).

## 8 · No se pudo comprobar (SR-09)

* Claves de **ámbito de máquina** (exigen administrador): el instalador y el servicio las usarán; el código crea y abre con `MachineKey`, pero **no se ejecutó elevado**. Tampoco se comprobó que un usuario estándar (OPS) pueda usarlas.
* El **instalador `.exe` de punta a punta** (la ventana de rechazo, Inno Setup elevado, un equipo sin sello): se compiló con la puerta y se probó todo lo que el Host hace; no se abrió el asistente.
* **Servicio de Windows real** (`AVACOMOPSBackend` bajo SYSTEM): el ensayo corre el verbo `servicio` como proceso normal.
* **El instalador de pruebas 2.17.0 de punta a punta** (2026-10-28): se compiló y se ensayó el paquete y el Host que lleva, **no se abrió el asistente** (ni en una PC elevada, ni en una sin sello para ver el mensaje de la sección 1.1 de `spec-driven/qa/grupo5-qa-test.md`): abrirlo en este equipo pediría elevación y escribiría en el `ProgramData` real. Que el `.exe` incluye la puerta se sabe por la diferencia de tamaño con el mismo asistente sin ella (§6.1), no por haberla visto actuar. El Host del paquete va comprimido en un solo archivo: no se puede comprobar con una búsqueda de texto que lleve la llave incrustada; lo prueban los ensayos de la puerta (aceptan un sello firmado con `sello-prueba-1`).
* **Producción:** `sello-2026-1` no existe; un build con `-ExigirPuertaDeDispositivo` no compila hasta la ceremonia. El ensayo de liberación contra el paquete **de entrega** exige la privada de la llave de sello: se corre en la estación de aprovisionamiento.
* **Windows 10**, TPM discreto, el firmware de una OPS AVACOM real: igual que en §8/§9.7.
* **TPM discreto**, TPM de otro fabricante, **Windows 10**, un equipo **sin TPM** o con el TPM bloqueado por directiva (el código cae al proveedor de software; sin probar), **panel de 86"**, antivirus.
* **Hyper-V con TPM virtual** (E2 del prompt) y **volcado de memoria** (E9): S6.
* **Cambiar la MAC de un adaptador real**: no se hizo (cambia la red del equipo del usuario).
* **`TPM2_ActivateCredential`** (evidencia 3): no se implementó.

## 9 · Identidad UEFI del dispositivo (`AVACOM_DEVICE_ID`) — 2026-10-27

Se añadió, **sobre el mismo mecanismo** (sello firmado + puerta del instalador + liberación de la clave), la comprobación de la variable UEFI que la fábrica graba en cada OPS AVACOM. No hay un sistema paralelo: la identidad del firmware es la primera capa de `PuertaDeDispositivo.Verificar`, y el sello es quien **autoriza**.

### 9.1 · Identidad no es autorización

| Capa | Quién | Qué dice | Dónde |
|---|---|---|---|
| Identidad | Firmware | «soy `AVACOM-OPS-…`» (variable `AVACOM_DEVICE_ID`, GUID `{8b7f9c20-3e51-4c8a-a7d1-91c62e0f4b35}`, atributos `0x7`) | `IdentidadUefi.Leer` (`Dispositivo/IdentidadUefi.cs`) |
| Autorización | AVACOM (Ed25519, llave `sello-…`) | «ese identificador, con **esta** clave del TPM, es un dispositivo AVACOM» | el sello trae el campo nuevo `uefi_id` (etiqueta 13; en la solicitud, etiqueta 10) |

Una variable UEFI corriente la puede crear quien tenga privilegios; que el valor cumpla `AVACOM-OPS-[0-9A-Z]{8,16}` **no prueba nada**. Por eso el formato es sólo una puerta de entrada: la autorización exige un sello firmado por AVACOM **cuyo `uefi_id` sea igual** al que el firmware declara, **y** que el equipo pruebe poseer la clave del TPM del sello. Nada se compara con un valor fijo: `AVACOM-OPS-00001234` es el equipo de pruebas y sólo aparece en las pruebas.

### 9.2 · Flujo (el mismo en instalador, servicio y liberación de la clave)

```
Verificar(equipo)
  1. firmware ─ GetFirmwareEnvironmentVariableExW (sólo lectura)
       Legacy BIOS · sin permiso · variable ausente · atributos ≠ 0x7 · vacío/no UTF-8/formato   ──▶ identidad_uefi (motivo)   47
  2. sello firmado por AVACOM + clave del TPM firma el reto + no revocado     ──▶ sin_sello 40 · invalido 41 · otra clave 42 · revocado 43 · no verificable 44
  3. sello.uefi_id == id leído                                                  ──▶ sin identificador / dispositivo_sin_licencia   47
  ✔ autenticado (0)
```

Estados del contrato `IIdentidadDeDispositivoAvacom.Validar()` y su código de diagnóstico (lo único que ve la persona, junto al mensaje):

| `EstadoDeIdentidad` | Código | Cuándo |
|---|---|---|
| `Autorizado` | AVC-UEFI-00 | los tres pasos |
| `VariableNoEncontrada` | AVC-UEFI-01 | error 203 (o GUID distinto) |
| `IdentificadorInvalido` | AVC-UEFI-02 | vacío, > 64 bytes, no UTF-8, formato |
| `AtributosInvalidos` | AVC-UEFI-03 | falta alguno de `NON_VOLATILE`/`BOOTSERVICE_ACCESS`/`RUNTIME_ACCESS` |
| `DispositivoSinLicencia` | AVC-UEFI-04 | sin sello, sello de otro equipo o de otro identificador, revocado |
| `FirmwareNoSoportado` | AVC-UEFI-05 | Legacy BIOS (`GetFirmwareType`=1 o error 1) |
| `AccesoDenegado` | AVC-UEFI-06 | error 1314/5: el proceso no tiene `SeSystemEnvironmentPrivilege` |
| `ErrorDeLectura` | AVC-UEFI-07 | cualquier otro fallo, el TPM no responde, excepción (no se propaga) |

### 9.3 · Dónde se aplica

| Punto | Qué hace | Quién lo corre |
|---|---|---|
| **Instalador** (`InitializeSetup` en `codigo.iss`) | ejecuta `puerta-instalacion`; si no sale 0 **no instala** y muestra el mensaje obligatorio (+ código; con 40-46 además lo que hay que hacer). Sin identidad UEFI no deja solicitud en la USB | administrador (Inno elevado) |
| **Servicio** (`ServicioBackend` → `PuertaDelServicio`) | antes de levantar el backend verifica; si no pasa **no arranca** (reintenta con espera creciente, se anota una vez por cambio de estado) y escribe la señal | SYSTEM |
| **Liberación de la clave** (`LiberacionDeClave.Liberar`) | llama a la misma puerta: sin autorización la llave `K` no se libera (el código cifrado no existe en claro) | SYSTEM |
| **Lanzador** (verbo `iniciar`, el de todos los accesos directos) | lee `Logs\dispositivo-estado.json` (estado y código, sin el identificador) y, si no está autorizado, **no abre la interfaz** y muestra el diálogo modal con el mensaje exacto | usuario estándar |

Mensaje (idéntico en instalador y aplicación, constante `IdentidadUefi.MensajeDeRechazo`): *«El LMS solo puede correr en dispositivos AVACOM. En caso de tratarse de un error, contacte con su distribuidor o canales de soporte autorizados.»*

**Menor privilegio.** Leer variables UEFI exige `SeSystemEnvironmentPrivilege` (la tienen Administradores y SYSTEM, desactivado). El lector la **activa sólo durante la lectura y la desactiva** después. No se eleva la aplicación ni el lanzador: quien da la clase (estándar) no puede leer el firmware, así que lo hace el servicio y el lanzador **sólo muestra** lo que el servicio dejó. Medido aquí sin elevar: la API responde 1314 → `AccesoDenegado`.

### 9.4 · Estación de aprovisionamiento

El inventario trae `uefi_id` por serie (obligatorio). La estación se niega a sellar si: el inventario no lo registra; la solicitud (firmada por el equipo) no lo trae o no coincide; el identificador ya está sellado para otra serie. `solicitar-sello` se niega (47) si el equipo no muestra una identidad UEFI válida, así que **la fábrica debe grabar la variable y correr `solicitar-sello` como administrador en la línea**.

### 9.5 · Pruebas

| Qué | Resultado |
|---|---|
| Host (`tests/Avacom.Ops.Host.Tests`) | **89** correctas: 7 de la lectura real y del lanzador + 32 de identidad (válida; inexistente; GUID incorrecto; vacío/formato/UTF-8/largo; atributos; sin licencia ×3; error de acceso; Legacy BIOS; excepción; sin red; reinicio; sin solicitud a un ajeno; servicio; mensaje exacto) |
| Prueba diferencial Python↔C# | 319 casos (3 nuevos con `uefi_id`: válido, mal formado, minúsculas) con el mismo veredicto y motivo |
| Estación (`tools/licencias`) | 129 en total, con 7 nuevas (identificador UEFI en sello, solicitud e inventario; dos series que no comparten identidad) |
| `Ensayar-Dispositivo.ps1` (Host, TPM y estación reales, firmware simulado con `AVACOM_OPS_UEFI`) | **27 de 27** |
| `Ensayar-ClaveDelPaquete.ps1` (backend cifrado real) | **27 de 27**, incluida «sin la variable UEFI no se libera ni arranca» (B2) |

El firmware real **jamás se escribe**: ningún archivo importa `SetFirmwareEnvironmentVariable` (una prueba lo vigila), el contrato `ILectorUefi` sólo tiene `Leer`, y las pruebas usan un lector falso. En un ensayo del instalador el identificador sale de `AVACOM_OPS_UEFI` y sólo vale con `AVACOM_OPS_ENSAYO=1` y carpeta de pruebas.

### 9.6 · Limitaciones de seguridad (franqueza)

1. **El identificador no es infalsificable.** Una variable UEFI normal la crea/cambia software con privilegios. Lo que protege es el **sello firmado** + la **clave del TPM** + la **liberación de `K`**; el identificador sólo ata ese sello a un equipo concreto.
2. **El identificador viaja en claro** en el sello y se puede copiar a otro equipo; en otro equipo falla la clave del TPM (42). Si la fábrica **no** puede grabar variables protegidas con escritura autenticada, otro software con privilegios puede reescribirlas: pedirle a la fábrica `TIME_BASED_AUTHENTICATED_WRITE_ACCESS` (0x20) mejora esto y **ya se acepta** (se exigen los tres bits, no se prohíben otros).
3. **El lanzador sólo presenta.** Quien edite `Logs\dispositivo-estado.json` (Logs es escribible por usuarios) sólo oculta o muestra el aviso; el servicio no arranca el backend y la clave no se libera igualmente. Abrir `Avacom.Lms.Ops.exe` **directamente** (sin el acceso directo) no muestra el mensaje: queda sin backend. Falta que la propia aplicación lea la señal (pendiente, ver §9.7).
4. **El servicio verifica al arrancar y en cada reintento, no en caliente:** un nodo ya en marcha no se detiene si luego se revoca el sello (igual que la decisión SQ-02 · opción A: no se corta el aula).
5. **Parchear el Host/instalador** salta el `if`; no salta el cifrado del código (§0, SP-05).
6. **Formato supuesto:** `AVACOM-OPS-` + 8 a 16 mayúsculas/dígitos (la referencia es `AVACOM-OPS-00001234`). Si producción usa otro formato hay que cambiar **dos** constantes: `IdentidadUefi.Formato` y `sello.FORMATO_UEFI_ID`.

### 9.7 · Qué no se pudo comprobar / pendiente

* **Lectura elevada del firmware real** y la variable en una OPS DS2015: aquí no hay variable ni sesión de administrador (la API respondió 1314). Que `SeSystemEnvironmentPrivilege` se pueda activar en el token de SYSTEM del servicio **no se probó** (está documentado para Administradores; SYSTEM pertenece a ese grupo).
* **Windows 10**, instalador `.exe` de punta a punta (el diálogo de Inno), servicio real y OPS con el lanzador abierto en una OPS sin identidad: sólo se probó lo que hace el Host.
* La aplicación MAUI no se modificó (§9.6.3). Instalador sin reconstruir en `installer/latest` (no se subió la versión).
* Las preguntas a la fábrica: ¿formato real del identificador (¿sólo dígitos?), ¿atributos `0x7` o con escritura autenticada?, ¿la solicitud de sello se corre en la línea?

### 9.8 · Cómo verificar en una OPS AVACOM real

1. Con el instalador de producción (llaves de sello publicadas), en la OPS **como administrador**:

```powershell
Start-Process -Wait "C:\Program Files\AVACOM\OPS Master\Runtime\Avacom.Ops.Host.exe" -ArgumentList "verificar-identidad"
Get-Content "$env:ProgramData\AVACOM\OPS Master\Logs\dispositivo.txt"
```

   Debe decir `Variable AVACOM_DEVICE_ID leida: AVACOM-OPS-…` y, con sello instalado, `Identidad del dispositivo: Autorizado`. Sin sello: `DispositivoSinLicencia` (AVC-UEFI-04) y salida 40.
2. Pedir el sello: `Avacom.Ops.Host.exe solicitar-sello` (deja `equipo.avsol` en la USB). La estación lo firma si el inventario trae ese `uefi_id`; `instalar-sello` lo guarda.
3. Para ver el bloqueo: en una PC cualquiera con el mismo instalador, abrir el instalador → debe mostrar el mensaje exacto con `AVC-UEFI-01` y no copiar nada; con el servicio instalado, el icono del escritorio muestra el diálogo y no abre la aplicación.
4. La verificación **no escribe** en el firmware: no hay ninguna llamada de escritura en el código (lo vigila una prueba). Si se quiere evidencia, `verificar-identidad` puede repetirse y debe dar siempre el mismo identificador.
