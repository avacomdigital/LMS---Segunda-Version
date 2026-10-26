# 15 · Licenciamiento (MOD-018) · Identidad de dispositivo y endurecimiento (Fase 5)

| Campo | Valor |
|---|---|
| Estado | **Construida y probada sin hardware real** (2026-10-22). Backend, Core, Student (Windows y Android) y OPS. Sin commit |
| Qué es | Cada equipo (tableta Student u OPS Master) prueba ante el nodo que **tiene una clave que no sale de él**, y el nodo anota **qué pudo comprobar** de esa clave: un nivel de garantía. Además, tres endurecimientos de Student: sin copias de seguridad, interruptores de desarrollo muertos en una entrega y clave de datos envuelta (apagada de fábrica) |
| Qué NO es | No decide si una tableta entra a clase. Un equipo sin clave, sin red o con un error sigue como siempre (R-01, OQ-043). No cambia el transporte (sigue HTTP/WS en claro), ni la llave de firma del APK, ni el kiosco ni el examen |
| Decisiones | D-50 a D-59 de [01-diseno.md](01-diseno.md) §12 |

## 1 · Cómo funciona

```
 equipo (Student / OPS)                                    nodo
 ──────────────────────                                    ────
 al presentarse (primer contacto):
   POST /api/licencia/identidad/reto/            ───►      reto de 32 bytes, un solo uso, vence a los 5 min
   crea su clave EC P-256 (Keystore / CNG)
     (Android: con el reto como desafío de atestación)
   POST /api/dispositivos/latido/  { …, identidad }  ───►  verifica la prueba junto al cupo; si es un equipo
                                                           nuevo, lo da de alta CON su clave y su garantía
 al abrir sesión (y otra vez al presentarse):
   POST …/identidad/reto/                        ───►      otro reto
   firma «AVACOM-ID1 · reto · su huella»
   POST …/identidad/enrolar/  { identificador_hw,   ───►   verifica posesión (y atestación si trae cadena),
                                identidad }                 guarda/confirma en device_manager
```

* **Una sola prueba, dos fuerzas.** La *prueba de posesión* (firma del reto) demuestra que quien habla tiene la clave; no dice dónde vive. La *atestación* (sólo Android, al crear la clave) sí lo dice, y el nodo la verifica **sin internet** contra las raíces de Google que viajan en el paquete.
* **Se identifica al abrir sesión, no en cada petición.** El login de Core avisa (`ClienteJson.SesionIniciada`) y cada app firma un reto nuevo en segundo plano; el login no espera ni se entera si falla.
* **Qué se firma:** `"AVACOM-ID1" + reto (32 bytes) + huella del equipo (UTF-8)`. Atar el reto a la huella evita que la prueba de una tableta sirva para otra. ECDSA con SHA-256; el nodo acepta la firma en DER (Java) o en P1363 de 64 bytes (CNG).
* **Dónde queda:** en `m09_dispositivo` (`device_manager`): `clave_publica` (SubjectPublicKeyInfo en base64; no sale en los listados), `clave_huella` (SHA-256), `garantia`, `garantia_detalle` y `garantia_en`. `licenciamiento` no escribe `m09_*`: llama a `device_manager.servicios.registrar_identidad`.

### Niveles de garantía

| Nivel | Qué significa | Cómo se llega |
|---|---|---|
| `hardware` | La clave vive en un entorno seguro del equipo y la app es la de AVACOM | Atestación de Android válida de punta a punta (§3) |
| `software` | Tiene una clave propia y probó poseerla; el nodo no pudo comprobar dónde vive | Prueba de posesión válida sin atestación, o con una atestación que no pasa algo. El motivo queda en `garantia_detalle.motivo` |
| `declarada` | Sólo la huella que el equipo dice de sí mismo (lo de siempre) | Equipo sin clave, o que nunca la presentó |

**Windows nunca pasa de `software`.** CNG puede guardar la clave en el TPM, pero el nodo no tiene cómo verificarlo sin una autoridad que atestigüe el TPM. Lo que el equipo dice de dónde guarda la clave viaja como `proveedor_declarado` (`tpm` o `software`), informativo: nunca sube el nivel.

## 2 · El cupo de equipos: qué dejó de ser blando

La huella de un equipo la **declara él mismo**; por eso hasta la Fase 5 el cupo era blando (alguien podía inventar huellas). Lo que cambia:

1. **Una clave identifica a un solo equipo.** La misma clave con otra huella → `409 clave_en_uso`; otra clave para un equipo ya enrolado → `409 clave_distinta` (el técnico reinicia la identidad: servicio `reiniciar_identidad`, sin pantalla todavía).
2. **Un nivel mínimo para dar de alta equipos NUEVOS** (`AVACOM_LICENCIA_IDENTIDAD_MINIMA`: `declarada` por defecto, `software` o `hardware`; sólo cuenta en un nodo de producción). Sin el nivel, `402 identidad_requerida` y el equipo no se crea. Lo ya registrado, su latido, la clase y el examen no se tocan jamás; el equipo maestro tampoco cuenta.

3. **Cada app lleva su propia clave** (`AVACOM-Identidad-Ops-v1` y `AVACOM-Identidad-Student-v1` en CNG): OPS y Student pueden vivir en el mismo PC de desarrollo o de QA con el mismo usuario de Windows, y una clave compartida contaría como un solo equipo con dos huellas (`clave_en_uso`).

**Quién llega primero gana.** Como la huella del equipo la declara el equipo, quien enrole una clave para una huella **antes** que la tableta legítima se queda con ella (la tableta recibirá `409 clave_distinta` y seguirá funcionando con garantía `declarada`; el técnico reinicia la identidad). Con `hardware` esto exige además un aparato Android real con la app de AVACOM y su arranque verificado. No afecta nunca a la clase.

**Lo honesto:** con `software` el cupo sigue siendo fácil de burlar (cualquiera genera claves nuevas). Sólo con `hardware` cada equipo físico equivale a una clave que no se puede fabricar en un PC. Y con `hardware` **una Student de Windows no puede darse de alta** (su techo es `software`). Elegir el mínimo es del CTO (§9).

## 3 · La atestación de Android: qué se comprueba

Con la cadena que entrega el Keystore al crear la clave (`setAttestationChallenge` con el reto del nodo) el nodo exige **todo** esto para dar `hardware`; si algo falla da `software` con el motivo:

| Se comprueba | Motivo si falla |
|---|---|
| Cadena bien formada, cada certificado firmado por el siguiente, la última autofirmada | `cadena_invalida` |
| La raíz es **exactamente** una de las de Google del paquete (se compara la llave pública, no el nombre) | `raiz_desconocida` |
| La raíz y los certificados intermedios están dentro de su vigencia (la hoja no: el reloj de una tableta suele estar mal y su certificado trae fechas arbitrarias) | `certificado_fuera_de_vigencia` |
| Ningún certificado está en la lista de revocados de Google del paquete | `certificado_revocado` |
| La llave de la hoja es la que el equipo declaró | `clave_distinta` |
| Hay una sola extensión de atestación y se lee | `sin_extension` |
| El desafío de la atestación es el reto que emitió el nodo (un reto distinto, o ya usado, no sirve) | `reto_distinto` |
| `attestationSecurityLevel` y `keymasterSecurityLevel` son TEE o StrongBox | `clave_en_software` |
| `verifiedBootState` = verificado | `arranque_no_verificado` |
| `deviceLocked` = verdadero (gestor de arranque cerrado) | `gestor_de_arranque_abierto` |
| El paquete es `com.avacom.lms.student` | `paquete_ajeno` |
| Todas las firmas de la app están en la lista de AVACOM (`atestacion/app.json`) | `app_ajena` |

### Raíces de Google (confirmado en la documentación vigente, 2026-10-22)

La página oficial *Key attestation* (actualizada el 2026-07-09) y `https://android.googleapis.com/attestation/root` dan **dos raíces vigentes**: la RSA (`f92009e853b6b045`, 2022-03-20 a 2042-03-15) y la **ECDSA P-384** nueva (`Key Attestation CA1`, 2025-07-17 a 2035-07-15), que Google empezó a usar para firmar cadenas el 1 de febrero de 2026. La página lista además tres raíces RSA «emitidas antes». El paquete lleva **cinco**: las dos vigentes y las tres anteriores. La de 2016 **caducó el 2026-05-24** y el nodo ya no la deja anclar nada; las de 2019 y 2021 siguen vigentes y se aceptan porque hay dispositivos con claves provisionadas con ellas. Todo está en `backend/licenciamiento/atestacion/raices_google.json` (sólo públicas, con su SHA-256) junto a `revocadas.json` (1765 números de serie, tal como los publica Google, decimal o hexadecimal) y `app.json`.

* **La lista de revocados envejece:** sin internet, es la del día de la compilación. Se refresca al reconstruir el instalador (repetir la descarga).
* **Rotar las raíces:** repetir la descarga de `.../attestation/root`, comparar con la página de Google y reconstruir.
* **La firma de la app hoy es la llave de depuración de Android.** `Build-StudentApk.ps1` firma el APK de entrega con `%USERPROFILE%\.android\debug.keystore` (certificado `CN=Android Debug`, SHA-256 `16efdeaf…5ce0`, verificado con `apksigner` sobre el APK 2.12.0). La identidad de la app vale lo que vale esa llave. Si se pasa a una llave de lanzamiento, hay que añadir su huella a `app.json` **antes** de distribuir el APK nuevo.

## 4 · Windows: lo probado con CNG

Sin elevar privilegios, en el equipo de desarrollo, con `CngKey.Create` y `NCryptGetProperty("Impl Type")` sobre el **proveedor** (en la clave da `NTE_NOT_SUPPORTED`):

| Proveedor | Crea clave EC P-256 | Exporta la privada | `Impl Type` | Firma |
|---|---|---|---|---|
| Microsoft Platform Crypto Provider | sí | no (política «ninguna») | **1 = hardware** (TPM) | sí, 64 bytes (P1363) |
| Microsoft Software Key Storage Provider | sí | no | 34 (software) | sí |

`ProveedorCng` intenta primero el de plataforma y cae al de software; nunca lanza. Un equipo sin TPM queda en `software` igual que uno con TPM, por lo dicho arriba.

## 5 · P-25 · Endurecimiento de Student

* **`allowBackup=false` + reglas de extracción.** `AndroidManifest.xml` pone `allowBackup=false`, `fullBackupContent=@xml/backup_rules` y `dataExtractionRules=@xml/data_extraction_rules`; las dos reglas **excluyen todo** (nube y transferencia entre aparatos, Android 11 y 12+). Verificado en el APK con `aapt2 dump xmltree` (§7).
* **Interruptores de desarrollo.** `AVACOM_EXAM_NO_LOCKDOWN`, `AVACOM_ESTUDIO_DEMO`, `AVACOM_ESTUDIO_DEMO_OFFLINE` y la preferencia `estudio_demo` sólo se obedecen en una compilación **Debug** o si junto al ejecutable hay un archivo vacío **`AVACOM-DESARROLLO`** (poner el archivo exige administrador). En un Release la variable no hace nada y el informe de bloqueo dice «está definida pero se ignora». Revisado qué usan UIA y QA: los arneses de UI Automation lanzan Student **Debug** (no cambia nada); QA con el Student **instalado** debe crear el marcador (notas puestas en `scripts/README.md`, `qa/happy-path-01.md` y `06-evaluation-delivery/testing.md`).
* **Clave de datos envuelta (bandera apagada de fábrica).** `AVACOM_CLAVE_ENVUELTA=1` o la preferencia `clave_envuelta` hacen que la clave AES de lo local (modo estudio y cola del examen) se guarde envuelta con una clave **no exportable**: RSA-2048 OAEP-SHA256 de CNG (TPM si hay) en Windows, AES-GCM del Keystore en Android. La clave de antes se **migra al leerla** (la misma clave: lo cifrado sigue legible). Apagar la bandera después **no** desenvuelve lo envuelto. Por defecto todo sigue en DPAPI (Windows) y `SecureStorage` (Android).
* **No se tocó:** la llave de firma del APK, TLS, el kiosco ni el examen.

## 6 · Cómo se probó

| Qué | Cómo | Resultado |
|---|---|---|
| Dominio de atestación (cadenas sintéticas, un defecto por prueba, mutaciones con semilla fija) | `licenciamiento.tests.test_atestacion` | 28 |
| Integración HTTP: reto, enrolamiento, claves repetidas, nivel mínimo, equipo nuevo | `test_identidad` | 32 |
| **Cadenas reales de un emulador** (Android 17, API 37, x86_64; APK de Student) y su recorrido HTTP | `test_atestacion_real`, `test_identidad_real` | 16 + 4 |
| Contratos capturados del nodo real para C# | `test_capturar_contrato_identidad` → `Fixtures/identidad/` | 9 archivos |
| Core (cliente, reglas, CNG real, interruptores, clave envuelta) | `IdentidadDeDispositivoTests`, `EndurecimientoTests` (Debug **y Release**) | 24 + 10 en Debug · 24 + 11 en Release |
| Student **en el emulador con la ruta real** (`Sesion.PresentarTabletaAsync` contra un nodo de pruebas en 8018, primer contacto → alta con su clave) | APK Debug + gancho **temporal** sólo en una copia (`C:\avs05`, nunca en el repo) | Alta con clave y garantía `software` (`raiz_desconocida`, 3 certificados); con `AVACOM_LICENCIA_IDENTIDAD_MINIMA=hardware` la presentación falla con `402` y el equipo no se crea |
| Suites completas (2026-10-22, con el árbol de las otras ramas en vuelo) | `manage.py test` · `dotnet test` de Core, Student y Ops · `makemigrations --check` | Backend **2628 correctas** (18 omitidas, 1210 s) · Core **2277** · Student **102** · Ops **528** · sin migraciones pendientes. Una primera corrida de Core, hecha a la vez que la suite del backend, dio 1 fallo que no se reprodujo en tres corridas seguidas (2277 de 2277) |
| UIA «iguales que la línea base» (Debug, nodos aislados, preferencias de Student restauradas) | `recorrido_acceso.py` (OPS) · `escenario_acceso.py` (Student) · `recorrido_dispositivos.py` (nuevo, en `tests/Avacom.Lms.Ops.Uia/`) | OPS **32 de 32** · Student **25 de 25** · Dispositivos **9 de 9** (las tres garantías con su color; captura con tercios revisada). El OPS y el Student del recorrido se identificaron de verdad: en el nodo quedó el equipo de OPS y la tableta de Student en `software` con `proveedor_declarado: tpm` |
| `allowBackup=false` en el APK | `aapt2 dump xmltree` | `allowBackup=false`, `fullBackupContent` y `dataExtractionRules` presentes; los dos XML dentro del APK |
| Interruptores muertos en Release | Un programa de sondeo que carga el `Avacom.Lms.Core.dll` que **lleva** cada Student compilado (Debug y Release) con las variables definidas | Debug: obedece. Release: `Permitidos=False`, ignora variable y preferencia. Release + marcador: obedece |

**Cómo se capturó la atestación real** (para repetirlo): se copió Core, Ui y Student a una carpeta corta, se añadió **sólo en la copia** un gancho en `MainActivity.OnCreate` que lee dos extras del intent (`nonce_hex`, `hw`), llama a `ProveedorKeystore.ProbarAsync` y escribe `files/atestacion.json`; se compiló un APK Debug (`-r android-x64`), se instaló en el emulador, se lanzó con `adb shell am start -n …MainActivity --es nonce_hex <64 hex> --es hw <huella>` y se leyó con `adb shell run-as com.avacom.lms.student cat files/atestacion.json`. Con `uninstall` + `install` la clave es nueva. Las dos cadenas están en `backend/licenciamiento/tests/fixtures/atestacion/`. **Lo que dicen:** versión de atestación 400, nivel `Software`, arranque `Unverified`, gestor abierto, raíz `Droid Unregistered Device CA` (de Google Test, no una raíz oficial): por eso el resultado correcto del emulador es `software`.

## 7 · Lo que NO se pudo comprobar

* **Una tableta Android 14 física.** No la hubo. **Sin comprobar:** el Keystore de hardware real, StrongBox, y una atestación de nivel `TrustedEnvironment`/`StrongBox` con el arranque verificado y el gestor cerrado de verdad. El camino `hardware` está probado con cadenas **sintéticas** (que reproducen la estructura de la extensión, con una raíz de prueba) y la lectura de la extensión está probada contra una cadena **real**, pero ninguna cadena real de hardware pasó por el nodo.
* **El rendimiento** de crear la clave en StrongBox (puede tardar segundos) y cómo se comporta `PresentarTabletaAsync` con ese retraso en una tableta lenta.
* **La clave de datos envuelta** en Android (compila; no se ejecutó) y en Windows con el TPM como envoltorio de la clave de datos de Student (el TPM sí se probó con la clave de identidad).
* **Un Windows sin TPM o con el TPM bloqueado por directiva.** El código cae a software; no se probó con ese equipo.
* **Los instaladores:** esta rama no reconstruyó `installer/latest` ni el APK (lo hace quien integra).

## 8 · Defectos ajenos hallados (se reportan, no se arreglan)

1. **El APK de entrega se firma con la llave de depuración de Android** (`Build-StudentApk.ps1`); y `dotnet build` Debug usa **otra** (`%LOCALAPPDATA%\Xamarin\Mono for Android\debug.keystore`, SHA-256 `52e97552…b536` en esta máquina). Cualquier APK firmado con la misma llave de depuración pasaría por «app de AVACOM».
2. **`estudio-clave` y `examen-clave` comparten la entrada `avacom_estudio_clave_v1`** de `SecureStorage` en Android (dos carpetas, una sola clave en el Keystore): ya conocido; la bandera de clave envuelta **no** lo arregla (usa su propio archivo por carpeta).
3. **`ConnectionPage` (modo sin sesión) no llama a `PresentarTabletaAsync`**: en el modo prototipo la tableta sólo se registra cuando el modo estudio da su latido (`EstudioReal`), y ese latido **no lleva identidad**. Una tableta que nunca usa sesión no se identifica; con el nodo en producción (sesión obligatoria) el camino sí pasa por `FlujoDeAcceso` y se identifica.
4. `DispositivosPage` y el resto de OPS siguen con el aviso CS0108 de `ReporteBoletinPage` (anterior a esta fase).

## 9 · Qué debe confirmar el CTO

1. **El nivel mínimo para equipos nuevos** (`AVACOM_LICENCIA_IDENTIDAD_MINIMA`). Recomendación: dejar `declarada` hasta probar una tableta física; con `hardware`, las Student de Windows no se pueden dar de alta.
2. **¿Se firma el APK con una llave de lanzamiento propia?** Sin eso, «app de AVACOM» se apoya en la llave de depuración.
3. **El marcador `AVACOM-DESARROLLO` para QA** (en lugar de sólo la variable) y quién lo pone en los equipos de pruebas.
4. **Pantalla para «reiniciar identidad»** (hoy sólo el servicio): cuándo debe poder hacerlo el técnico desde OPS.
5. **Encender la clave de datos envuelta** en las tabletas de la flota una vez probada en una física.

---

## Anexo · Contratos reales (capturados del nodo)

Los de `/api/licencia/identidad/` salen de `test_capturar_contrato_identidad.py` y se prueban en C# (`IdentidadDeDispositivoTests`). Las rutas son **públicas** (sin sesión), como el latido.

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /api/licencia/identidad/reto/` | `{}` | `201` `{"nonce": "<base64 de 32 bytes>", "vence_en": <ms>, "algoritmo": "ecdsa-p256-sha256", "contexto": "AVACOM-ID1"}` |
| `POST /api/licencia/identidad/enrolar/` | `{"identificador_hw": "<huella>", "identidad": {"nonce", "clave_publica", "firma", "cadena"?: [..], "proveedor"?}}` (todo base64) | `200` `{"garantia", "motivo", "clave_huella", "dispositivo_id", "confirmada_en", "detalle"}` |
| `POST /api/dispositivos/latido/` y `POST /api/dispositivos/` | los de siempre + `"identidad": {…}` opcional (sólo la usa un equipo **nuevo**) | el equipo, con `garantia`, `clave_huella` y `garantia_detalle` |

```json
// 201 reto
{"algoritmo": "ecdsa-p256-sha256", "contexto": "AVACOM-ID1", "nonce": "saqDaZud1Msv1crgQayIunjsH66a0hGOUK9xAcChPWE=", "vence_en": 1792691525712}

// 200 enrolar · primer enrolamiento sin cadena
{"clave_huella": "ad38a71d18adb6cc3c74ea9e15bdecf36a0acd3c99c2db0bc7be978a39af6e79", "confirmada_en": 1792691225712, "detalle": {"motivo": "sin_cadena"},
 "dispositivo_id": "9d065d19-…", "garantia": "software", "motivo": "sin_cadena"}

// 200 enrolar · confirmación de una sesión posterior (conserva el nivel)
{"clave_huella": "ad38a71d…6e79", "confirmada_en": 1792691285712, "detalle": {"motivo": "sin_cadena"}, "dispositivo_id": "9d065d19-…", "garantia": "software", "motivo": "confirmada"}

// 200 enrolar · atestación válida (cadena SINTÉTICA con la raíz de prueba: no es hardware real)
{"detalle": {"arranque": "verificado", "certificados": 3, "gestor_cerrado": true, "motivo": "ok", "nivel": "tee", "raiz": "prueba", "version_atestacion": 300}, "garantia": "hardware", "motivo": "ok", …}
```

| Error | Cuándo | Cuerpo |
|---|---|---|
| `400 reto_invalido` | reto desconocido, vencido, repetido o corto | `{"codigo": "reto_invalido", "detail": "El reto que trae el equipo no existe, ya venció o ya se usó. Un reto vale una sola vez: se pide otro."}` |
| `400 identidad_invalida` | la clave no es EC P-256 o la firma no cuadra con la clave y la huella | `{"codigo": "identidad_invalida", "detail": "La firma del reto no corresponde a esa clave y a este equipo.", "motivo": "firma"}` |
| `404 no_encontrado` | el equipo aún no se registró (`codigo_interno: dispositivo_no_registrado`) | `{"codigo": "no_encontrado", "codigo_interno": "dispositivo_no_registrado", "detail": "Ese equipo todavía no se registró en el aula."}` |
| `409 clave_distinta` | el equipo ya tiene otra clave | `{"codigo": "clave_distinta", "detail": "Este equipo ya tiene registrada otra clave."}` |
| `409 clave_en_uso` | esa clave ya es de otro equipo | ídem, `clave_en_uso` |
| `402 identidad_requerida` | equipo **nuevo** sin la garantía mínima (capturado de un nodo vivo con `AVACOM_LICENCIA_IDENTIDAD_MINIMA=hardware`) | `{"detail": "Para dar de alta un equipo nuevo, la licencia pide identidad con garantía «hardware» y este llegó con «declarada».", "codigo": "identidad_requerida", "minimo": "hardware", "nivel": "declarada"}` |
