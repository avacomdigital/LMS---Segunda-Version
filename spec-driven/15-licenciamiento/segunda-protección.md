# Prompt · MOD-018 Licensing · Segunda protección: dispositivo AVACOM autenticado, instalación y backend protegido

> Pega todo lo que sigue, desde «# Rol y contexto» hasta el final, como primer mensaje de una sesión nueva en este repositorio. Está escrito para que la sesión no tenga que preguntar nada: lo que falta lo decide con los criterios de abajo y lo deja escrito como decisión `SD-n`. Lo que ya viene decidido se llama `SP-n` (premisa); las reglas que no se negocian, `SR-n`; lo que sólo el CTO puede cerrar, `SQ-n`. No reabras una `SP-n` sin una razón medible.
>
> **Alcance de esta sesión** (edita sólo esta línea antes de pegar): `FASES S0 a S2`.
> Orden recomendado, una sesión por tramo: `S0 a S2` (línea base, sello de dispositivo AVACOM y puerta de instalación) → `S3 a S4` (backend protegido y datos en reposo) → `S5 a S6` (entorno de ejecución, ciclo de vida y prueba adversarial). No empieces un tramo que no te toca: cada tramo termina en algo que se puede instalar y probar.
>
> Generado el 2026-10-24 a partir de una investigación con fuentes primarias (Anexo A). Lo que no se pudo verificar está marcado **[sin verificar]** y se confirma en la Fase S0 antes de apoyarse en ello.

---

# Rol y contexto

Actúa como **ingeniero de software senior con foco en seguridad aplicada**: identidad de dispositivo con TPM y Keystore, firmas digitales, protección de código Python, endurecimiento de servicios Windows y de instaladores. Escribes poco código, muy probado, y dices con franqueza lo que una defensa **no** impide. Si algo no cuadra entre este prompt y el repo, **manda el repo** y lo dices.

Estás en `C:\projects\prototypes\prototype-lms-v04`. El producto:

- **Backend** — Django + DRF + Channels (Daphne), SQLite, `0.0.0.0:8000`. Instalado corre como el servicio de Windows `AVACOMOPSBackend` (SYSTEM), que lanza el `Host` (`installer/src/host`, C#) con un **Python 3.12 embebido** y el código del backend en **`.py` claro** dentro de `Program Files`. `Get-PythonRuntime.ps1` arma el runtime con `pip` (`--only-binary`, `win_amd64`).
- **AVACOM OPS Master** (`src/Avacom.Lms.Ops`, MAUI, sólo Windows) — equipo maestro del aula: **pantalla táctil de 86", sin teclado**. Nada de lo que construyas puede exigir escribir.
- **AVACOM Student** (`src/Avacom.Lms.Student`, MAUI) — tabletas Android 14 y portátiles Windows 11.
- `src/Avacom.Lms.Core` y `src/Avacom.Lms.Ui` los comparten. Instalador en `installer/` (Inno Setup + Host).
- **El árbol tiene archivos sin commit de otras sesiones**, incluidos `04-proteccion.md` y `08-identidad-de-dispositivo.md` de esta misma carpeta. No los toques, no los reviertas, no los añadas al índice. Antes de editar un archivo compartido (`installer/version.json`, `Build-Installer.ps1`, `AvacomOpsMaster.iss`, `settings.py`, `catalogos.py`, `Avacom.Lms.Student.csproj`) mira su `git diff` y añade sin pisar lo ajeno. **Reconfirma con grep** cada dato de este prompt: las líneas se mueven.

# Lee antes de escribir (en este orden)

1. `spec-driven/15-licenciamiento/01-diseno.md`, sobre todo **§5 reloj, §6 huella, §11 producción/desarrollo, §12 decisiones D-1…D-59, §14 «Lo que esto NO impide»**. Es la voz que debes mantener: no promete lo que un cliente instalado en un aparato ajeno no puede cumplir.
2. `04-proteccion.md` (Fase 4: biblioteca nativa `avacom_lic`, manifiesto firmado, integridad del despliegue, límite A4) y `08-identidad-de-dispositivo.md` (Fase 5: clave EC P-256 no exportable, niveles `hardware`/`software`/`declarada`, atestación de Android, endurecimiento de Student). **Esta segunda protección se construye encima de ellos; no los rehagas.**
3. `00-prompt.md` (el prompt original: P-1…P-27, R-01…R-12, el modelo de amenazas A1…A6, P-26 el experimento de ofuscación), `07-ceremonia-de-llaves.md` (cómo se custodian y rotan las llaves) y `05-emision.md` (el emisor interno).
4. `installer/README.md`, `installer/build/Build-Installer.ps1`, `Sellar-Paquete.py`, `Get-PythonRuntime.ps1`, `installer/src/AvacomOpsMaster.iss` y `installer/src/host/` (`Integridad/`, `Actualizacion/`).
5. `spec-driven/03-device-manager/00-modelo-y-api.md` (la tabla `m09_dispositivo` y su servicio público) y `spec-driven/17-update-manager/` si existe (los paquetes `.avupd` también llevan código).
6. La **memoria del proyecto** (se carga sola): entorno, trampas de la herramienta Bash con las barras invertidas, reglas de commits y de instaladores, regla de tercios de la UI, frontera LMS ↔ Biblioteca, instalador `latest` siempre al día.

# Qué ya existe (y qué falta)

| Ya existe | Dónde | Qué deja sin cubrir |
|---|---|---|
| Licencia `.avlic` firmada (Ed25519), huella de equipo (`MachineGuid`/SMBIOS, k de n), reloj, estados con gracia; **nunca detiene una clase en curso** | `backend/licenciamiento`, `01-diseno.md` | La licencia sigue el **equipo**; no dice si el equipo es **un dispositivo AVACOM** ni impide copiar la instalación |
| `avacom_lic` nativa (verificación, envoltura de claves `avl_key_wrap/unwrap`, `avl_key_derive`) | `native/avacom-lic/`, `04-proteccion.md` | El código de la aplicación sigue en `.py`; la biblioteca no cifra nada de él |
| Manifiesto firmado + `integridad.json` verificados por el Host al arrancar; señal `integridad_alterada` | `installer/src/host/Integridad/` | **Evidencia, no prevención**: no impide leer ni copiar; el Host es parcheable (A4) |
| Identidad de dispositivo: clave EC P-256 no exportable (CNG/Keystore), reto de 32 bytes, atestación de Android contra raíces de Google, niveles de garantía | `08-identidad-de-dispositivo.md`, `m09_dispositivo` | **Windows nunca pasa de `software`** (D-52): el nodo no tiene una autoridad que atestigüe el TPM. Y nadie ha dicho todavía **qué equipos son de AVACOM**: un PC cualquiera puede generar una clave y enrolarse |
| Clave de datos envuelta por TPM/Keystore (bandera apagada) | `Core/Estudio/EnvoltorioDeClave.cs` | Sólo Student; la base del nodo y los secretos del backend no se envuelven |
| Interruptores de desarrollo muertos en Release (marcador `AVACOM-DESARROLLO`) | Core, `08` §5 | Patrón a **reutilizar** para cualquier puerta de desarrollo nueva |

**Lo que el usuario pide ahora (segunda parte del licenciamiento):**

1. Una capa adicional para que el programa sea **«no copiable»** o que alguien no autorizado por AVACOM no pueda copiarlo.
2. **Durante la instalación**, verificar que el programa corre sobre un **dispositivo AVACOM autenticado**.
3. **Proteger el código del backend después de instalado**: hoy basta entrar a la carpeta de instalación para leer los archivos de Django REST Framework.
4. Un **sistema** que permita aplicar esta protección sobre dispositivos AVACOM.

# Lo que se puede y no se puede prometer (leer dos veces)

**«No copiable» absoluto no existe, y el diseño no lo afirma.** Lo respaldan fuentes que no dependen de ningún proveedor:

- *Barak, Goldreich, Impagliazzo, Rudich, Sahai, Vadhan, Yang · On the (Im)possibility of Obfuscating Programs* (CRYPTO 2001, ePrint 2001/069): la ofuscación general de «caja negra virtual» es imposible; se prueba con una familia de programas que no se pueden ofuscar.
- *Schrittwieser, Katzenbeisser, Kinder, Merzdovnik, Weippl · Protecting Software through Obfuscation: Can It Keep Pace with Progress in Code Analysis?* (ACM Computing Surveys 49(1), 2016): el análisis ligero falla ante ofuscaciones básicas, pero con análisis interactivo humano se derrotan muchas; **proteger propiedad intelectual con ofuscación sigue siendo muy difícil**.
- *Ceccato, Tonella, Basile et al.* (ICPC 2017): estudio de informes de pentesters profesionales sobre código protegido de tres socios industriales; los atacantes entienden el código, construyen el ataque, eligen herramientas y **sortean las protecciones**.
- *Bos, Hubain, Michiels, Teuwen · Differential Computation Analysis* (CHES 2016): las cajas blancas criptográficas (esconder una clave dentro del código) se rompen con trazas de memoria. **Nunca escondas una clave dentro del programa y la llames protegida.**
- **OWASP MASVS-RESILIENCE / MASTG**: las medidas de resistencia (ofuscación, antimanipulación, RASP) son **defensa en profundidad, no sustituto** de los controles de seguridad; suben el costo, no hacen imposible la ingeniería inversa.

**Lo que sí es defendible y medible** (la meta de este trabajo):

| Promesa | Qué la sostiene | Qué no cubre |
|---|---|---|
| **Una copia de la instalación o del instalador no corre en un equipo que no sea AVACOM** | La clave que abre el código/los datos sólo sale de un **elemento no exportable (TPM / Keystore)** del equipo sellado por AVACOM (*key release*, no un `if`) | Un administrador con un equipo AVACOM **real** que vuelque la memoria del proceso (A4); un ataque físico a un TPM discreto (ver abajo) |
| **Instalar en un equipo que no es AVACOM falla** | Puerta de instalación que exige un **sello firmado** y la prueba de posesión de la clave del equipo | Parchear el instalador: por eso la puerta real es la liberación de la clave (SP-05) |
| **Abrir la carpeta de instalación no enseña código legible** | Código propio compilado a binario o cifrado, sin `.py` ni `.pyc` legibles; ACL de lectura; sin `python.exe` suelto | Un experto con tiempo, un depurador y un volcado de memoria |
| **Una fuga se puede atribuir** | Marca por dispositivo (SP-09) | Marcas eliminadas por un atacante que conozca el método |

# Hallazgos de la investigación

Cada hallazgo lleva su fuente en el Anexo A y su confianza: **[P]** documentación primaria del fabricante/estándar, **[A]** académica revisada por pares, **[V]** proveedor (indicativo, no probatorio), **[S]** secundaria (sólo para orientar). Las fuentes descartadas están en el Anexo B.

## H-1 · Referentes que protegen código o contenido

| Referente | Qué hace | Lección para AVACOM | Conf. |
|---|---|---|---|
| **Widevine / DRM de plataforma** | Claves de contenido **individualizadas por dispositivo**, aprovisionadas en fábrica, manejadas en un entorno seguro; el cliente nunca habla directo con el servicio de licencias | El patrón es **identidad aprovisionada en fábrica + licencia por dispositivo + clave que no sale del entorno seguro**. Es el modelo del sello (S1) | P (parcial) |
| **Android Key Attestation / Play Integrity** | La cadena de certificados del Keystore dice dónde vive la clave (`attestationSecurityLevel`), `verifiedBootState`, `deviceLocked`, parche; Play Integrity da veredictos de dispositivo/app | Ya usado en Fase 5. Play Integrity exige Google Play y red y Google dice que **no debe ser el único** mecanismo: encaja mal con aulas sin internet; sólo opcional | P |
| **TPM 2.0 + BitLocker** | Claves selladas al estado de la plataforma (PCR); el volumen sólo abre en el equipo que lo cifró; un disco movido a otro equipo no abre | Es la defensa estándar de «copiar el disco». Límite documentado: con **TPM discreto y sin PIN previo al arranque** la clave se puede **espiar en el bus** (LPC/SPI) con hardware barato (Pulse Security 2019; WithSecure) | P / S |
| **IEEE 802.1AR (IDevID) y perfil de TCG para TPM** | Identidad inicial **instalada por el fabricante**, certificada por la CA del fabricante, atada a una clave generada en el TPM | La respuesta de la industria a «¿es un equipo mío?»: **certificado de dispositivo emitido por quien fabrica/entrega**, no una lista de MAC | P (estándar) |
| **Microsoft TPM Key Attestation** (AD CS) | Tres modelos de confianza: por credencial de usuario (bajo), por **cadena del EKCert** del fabricante (medio: confía en *todos* los TPM del fabricante), por **lista de EKPub permitidas** (alto: sólo los dispositivos inventariados uno por uno) | **El modelo «lista blanca» correcto es de claves de TPM, no de MAC.** Es exactamente la decisión de S1 | P |
| **Keygen / licencias por archivo** | Archivos de licencia firmados, clave derivada de `licencia + huella`; la propia documentación admite que el enlace **es tan fuerte como la huella** | Ya adoptado (§6 del diseño). La huella declarada por el cliente es el eslabón débil, de ahí S1 | V (coincide con lo construido) |
| **Wibu CodeMeter / AxProtector** | Cifra el ejecutable y sólo corre si hay una licencia en una llave de hardware o servidor | Mismo principio de *key release*; producto comercial, **no se adopta sin decisión del CTO**; sirve de comparación en el experimento de S2 | V |
| **Pyarmor** | Cifra el bytecode; la «llave en tiempo de ejecución» puede atarse a MAC, serie de disco o `machine id` (`-b`); modo `--restrict` | El atado a dispositivo usa identificadores **falsificables**, y la llave debe estar en memoria al ejecutar; sin garantía declarada por el propio proveedor (su documentación no afirma un nivel de seguridad) | V / P (docs) |
| **Nuitka** | Compila Python a C y a binario; la edición comercial añade cifrado de constantes y de datos | Mucho más caro de revertir que un `.pyc`, pero es un compilador, no un sistema de licencias; **las constantes y cadenas quedan legibles sin la edición comercial** | P (docs) / V |
| **PyInstaller** | Retiró en 6.0 el cifrado de bytecode (CVE-2025-59042: carga de módulo opcional con `sys.path` controlable) | Un cifrado «de fábrica» con la llave dentro del ejecutable no es una barrera; y un cargador mal hecho es una vulnerabilidad | P (CVE) |

## H-2 · Proteger el backend Django/DRF ya instalado

1. **Causa raíz.** El código vive en `Program Files` como `.py` porque Python es un lenguaje interpretado: lo que se ejecuta **es** lo que se lee. Un administrador local puede leer cualquier archivo y volcar cualquier proceso. Por eso las capas se ordenan por **a quién detienen**: un usuario curioso, un técnico, un administrador con herramientas, un atacante con acceso físico (A1…A6 del modelo de amenazas).
2. **Compilar a binario** (Nuitka o Cython) es la capa de mayor relación costo/beneficio para código propio; deja cadenas y nombres de módulos, y no oculta el comportamiento (se ve con un depurador). Riesgos de Django: carga dinámica de `models`, `migrations`, `urls`, comandos de `manage.py`, plantillas y `AppConfig`; hay que **probarlo con toda la suite**.
3. **Cifrar el código con una clave liberada por hardware** (cargador de importación en la biblioteca nativa que abre módulos en memoria con una clave desenvuelta por el TPM) sube el costo de copiar el árbol a otro equipo, pero la clave tiene que estar en memoria cuando corre: **no detiene a un administrador con depurador**. Es el principio de Pyarmor/CodeMeter hecho a la medida con una clave que *sí* sale de un elemento no exportable.
4. **WDAC / App Control no basta para Python.** Microsoft documenta que App Control **no controla scripts de intérpretes no «iluminados» (muchos motores de Python)**: si la política permite `python.exe`, permite implícitamente todos los scripts que ese intérprete corra. Conclusión: no distribuir un `python.exe` suelto; el Host debe incrustar el intérprete (API de C de Python) y la política sólo debe permitir binarios firmados de AVACOM.
5. **Los ganchos de auditoría de Python (PEP 578) no son un sandbox**: la propia PEP lo dice. Sirven para **detectar**, no para impedir.
6. **ACL y cuenta del servicio.** `Program Files` ya impide escribir a usuarios estándar, pero no leer. Un servicio con cuenta virtual (`NT SERVICE\…`) en lugar de SYSTEM y ACL de lectura sólo para esa cuenta y administradores **encarece**; no detiene a un administrador.
7. **Datos en reposo.** Cifrar la base SQLite (SQLCipher: AES-256 de las páginas, comprobado en la ficha del proyecto; claves y parámetros **[sin verificar]** en su página de diseño) o cifrar campos sensibles, con la clave **envuelta por el TPM**, hace inútil una copia de la carpeta de datos en otro equipo. Cuesta en copias de seguridad, exportaciones y Update Manager: hay que medirlo.
8. **Evidencia ya construida** (Fase 4): integridad firmada. Es complementaria; no la repitas.
9. **El runtime también es superficie de cadena de suministro**: `Get-PythonRuntime.ps1` no comprueba el SHA-256 del Python embebido contra python.org y `requirements-runtime.txt` no usa `--require-hashes` (defectos ajenos que reportó la Fase 4). Es parte del trabajo de endurecer el paquete.
10. **Los ensamblados .NET de OPS, Host y Student son IL** y se leen con descompiladores gratuitos. El pedido es el backend; **anótalo como alcance ampliado (S4b)** y no lo hagas sin que el CTO lo confirme (SQ-07).

## H-3 · ¿Hace falta una lista blanca de direcciones MAC?

**Veredicto: no como control de seguridad. Sí, como mucho, como dato de inventario.** La evidencia:

- **Se cambia.** Los controladores de red permiten fijar la MAC; la MAC viaja sin cifrar en cada trama. Quien copia una instalación copia también el valor. (No hay una fuente primaria que cite aquí: es ingeniería elemental, así que **verifícalo tú en S0 con un adaptador real** y deja la captura.)
- **Android no la entrega.** Desde **Android 6** sólo apps del sistema leen la MAC; desde **Android 11** `NetworkInterface.getHardwareAddress()` devuelve `null` para todas las interfaces de apps no privilegiadas (documentación de Android). Además la **aleatorización de MAC** está activa por defecto desde Android 10 (AOSP). Una lista de MAC **no puede** aplicarse a las tabletas Student.
- **Windows la aleatoriza** (por red, en Wi-Fi) si el adaptador lo soporta (soporte de Microsoft). Un PC con Wi-Fi puede mostrar una MAC distinta por red.
- **Hasta la aleatorización falla:** el estudio de PoPETs 2017 halló que en muchos aparatos se filtra la dirección global real (útil como cautela: ni siquiera el identificador «de fábrica» es limpio).
- **Un MAC es de la tarjeta, no del equipo:** cambiar de adaptador cambia la identidad; con 55 tabletas esto generaría falsos rechazos.
- **El proyecto ya lo decidió a su manera:** la huella usa `MachineGuid`/SMBIOS y excluye `ProcessorId` (D-3); la MAC no entra.

**Lo que sí corresponde** es una **lista de permitidos de identidades de dispositivo no falsificables**: el hash de la **clave pública del TPM (EKPub)** o de la **clave de dispositivo sellada** (la `clave_huella` de la Fase 5), con su serie y modelo, emitida y firmada por AVACOM. Es el «modelo de confianza por EKPub» de Microsoft (el de más alta garantía) y el equivalente del IDevID del estándar 802.1AR. La lista se distribuye **como sellos individuales** y como **lista de revocados** firmada, no como una tabla que viaje completa en cada instalador.

## H-4 · Qué significa «dispositivo AVACOM autenticado»

Hoy nada lo define. La decisión de diseño depende de un hecho que **sólo el CTO conoce** (SQ-01): ¿AVACOM **fabrica o aprovisiona** los equipos (paneles, tabletas), o son equipos de mercado a los que se les instala el software? El diseño debe funcionar en ambos casos con **la misma pieza, el sello**:

| Origen del equipo | Cómo recibe su sello | Garantía |
|---|---|---|
| **AVACOM lo imagina o lo fabrica** (ideal) | En fábrica: el TPM (o Keystore) genera la clave; una estación de aprovisionamiento de AVACOM verifica la evidencia y firma el sello; queda en `%ProgramData%\AVACOM\OPS Master\Config\sello\` | `fabrica` |
| **Equipo de mercado, vendido por AVACOM** | En la entrega: el técnico corre un verbo del Host que escribe una **solicitud** (`.avsol`) en un USB (sin teclado); AVACOM firma y devuelve el `.avsello`; se inserta el USB y el Host lo instala. Mismo flujo que `.avreq`/`.avlic` | `entrega` |
| **Equipo ajeno** | No hay sello | sin sello: no se instala (puerta de S1) |

La **estación de aprovisionamiento es la autoridad que la Fase 5 no tenía** para atestiguar el TPM de Windows (D-52): en el aprovisionamiento AVACOM comprueba la cadena de **EKCert** del fabricante del TPM (o registra la EKPub contra su inventario de series) y firma. **En campo, sin internet, el nodo sólo verifica** una firma Ed25519 y la prueba de posesión de la clave (el reto de D-51). Sin tocar el transporte.

# Premisas decididas (`SP-n`)

- **SP-01 · Franqueza.** Ninguna frase del producto, de las guías ni de los informes dice «imposible de copiar». Usa el vocabulario de `01-diseno.md` §14: **impide / encarece / detecta / no cubre**, con las promesas de la tabla de arriba.
- **SP-02 · Dónde se puede bloquear y dónde no.** **Sí** se puede **negar la instalación** y **negar la liberación de la clave** en un equipo sin sello válido (aún no hay clase en curso). **No** se detiene ni se degrada una clase en curso por la verificación de dispositivo: un nodo ya instalado que pierda su sello válido (TPM borrado, placa cambiada) entra a una **gracia** con los mismos estados y avisos de la licencia (`01-diseno.md` §4), nunca a media clase (R-01). Los plazos son dato (`politica.py`). **SQ-02** pregunta si basta.
- **SP-03 · La MAC no autentica** (H-3). Puede guardarse como dato **informativo** en el sello; nunca decide.
- **SP-04 · Autenticidad = clave no exportable + sello firmado por AVACOM.** La lista de permitidos es de **huellas de clave** (EKPub / `clave_huella`), emitida por AVACOM, con **revocación**. No se pega una tabla de MAC ni de series en el instalador.
- **SP-05 · *Key release*, no `if`.** La protección de verdad no es un chequeo que un parche salta, sino que **la clave que abre el código y los datos sólo la entrega el TPM/Keystore del equipo sellado**. Sin la clave, el código cifrado no existe en claro. Todo chequeo adicional es evidencia y mensaje de error.
- **SP-06 · Sólo se protege lo propio.** Django, DRF, Channels, Daphne y demás terceros son públicos: **no se compilan ni se cifran** (no hay secreto, hay obligaciones de licencia y problemas de compatibilidad). Revisa las licencias de lo que se redistribuya compilado.
- **SP-07 · Una llave nueva.** El sello se firma con una llave **propia** (`sello-2026-1`), con su `kid`, su ceremonia y su rotación como en `07-ceremonia-de-llaves.md`. No mezcles con `prod-2026-1` (licencias) ni `upd-2026-1` (publicación). La privada **nunca** entra al repo ni a un instalador (reutiliza la prueba de contenido del paquete, D-49).
- **SP-08 · Medir y decidir con un sí/no.** Cada técnica de S2 y S3 es un **experimento con presupuesto de rendimiento y de compatibilidad fijado antes de empezar** y una decisión escrita. No adoptes una por ser la más conocida.
- **SP-09 · Atribución.** Cada instalación lleva una **marca por dispositivo** (el `kid` del sello y una huella derivada en un recurso del paquete) que permita atribuir una fuga (Collberg y Thomborson 2002: la marca de agua responde a la piratería; la ofuscación, a la ingeniería inversa; la protección contra manipulación, a la modificación). Documenta cómo se quita y cuánto cuesta.
- **SP-10 · Respaldo y puertas de desarrollo muertas.** Todo lo nuevo tiene un camino de desarrollo/pruebas **que en Release no existe** (marcador `AVACOM-DESARROLLO` junto al ejecutable, que exige administrador, como en `08` §5). Un instalador de producción **no** tiene una opción de línea de comandos que apague la puerta.
- **SP-11 · Sin teclado.** Todo flujo de OPS (sello, solicitud, revocación) se hace con toques, USB y archivos. Pantallas con la **regla de tercios** y verificadas con captura + cuadrícula, como en la memoria.

# Reglas que no se negocian (`SR-n`)

- **SR-01** · No toques `backend/biblioteca/` ni la capa de fuentes de cursos (frontera LMS ↔ Biblioteca). Compilar o cifrar el backend **no** puede cambiar lo que esa capa hace.
- **SR-02** · **Nunca más de lo que prometes.** Cada defensa se documenta con lo que **no** impide; una defensa que no puedas probar contra su ataque no entra a la promesa.
- **SR-03** · Una verificación que falla **por error del propio sistema** (TPM bloqueado, antivirus, reloj) no tumba una clase: gracia primero, bloqueo nunca a media clase.
- **SR-04** · Ningún secreto en el repo, en el instalador, en `backend.env` en claro, en logs ni en la bitácora. Las frases y llaves se manejan como en `07`. No imprimas ni repitas una frase.
- **SR-05** · **No instales herramientas en el sistema sin pedirlo** (Nuitka, compiladores, SQLCipher, el SDK del TPM). Si hacen falta, di cuáles, de dónde y qué versión, y espera. Todo se descarga a una carpeta nueva, sin ejecutar desde ella; el Python que lea archivos descargados corre con `-I`.
- **SR-06** · El árbol tiene trabajo ajeno: `git add` **siempre con rutas de archivo explícitas** y revisa `git diff --cached --name-only`. **No hagas commit si no te lo piden**; si te lo piden, autoría `ggalindo-avacom`, sin coautoría de Claude, separado en `Feature:` y `Docs:`.
- **SR-07** · Todo cambio que viaje en el instalador sube la versión (`installer/version.json`) y termina con **`installer/latest` reconstruido** y su `SHA256.txt` (memoria del proyecto). Si dos sesiones compilan a la vez, el build descarta el `.exe`: comprueba que nadie edita `installer/` ni `src/` durante la compilación.
- **SR-08** · Herramienta Bash: reduce `\\` a `\` y los heredocs largos fallan. Para archivos con barras, usa `Write` o Python con cadenas crudas y verifica bytes.
- **SR-09** · Lo que no pudiste probar (tableta ARM, TPM discreto, antivirus, panel real, Windows sin TPM) va en una lista **«No se pudo comprobar»**, igual que en `04` y `08`. No lo declares hecho.
- **SR-10** · Una prueba en modo producción **redirige** `%ProgramData%` y la carpeta de estado (trampa conocida: una vez escribió en el real). Verifica antes de correr.

# Objetivo

**Parte A (S0–S2) · Identidad AVACOM y puerta de instalación.** Un **sello de dispositivo AVACOM** firmado, un sistema de aprovisionamiento para emitirlo (en fábrica o en la entrega) y una **puerta en el instalador** que se niega a instalar donde no hay sello válido con la prueba de posesión de la clave.

**Parte B (S3–S5) · Backend ilegible y no copiable.** Código propio compilado o cifrado con una clave que sólo libera el TPM/Keystore del equipo sellado; datos en reposo atados al dispositivo; entorno de ejecución endurecido.

**Parte C (S6) · Prueba adversarial.** Intentar romper las promesas de la tabla, con presupuesto fijo, y documentar honestamente lo que resistió.

# Fases

Cada fase termina con: pruebas verdes, documentación en `09-segunda-proteccion.md` (qué impide / encarece / detecta / no cubre / qué no se pudo comprobar) y, si cambia el paquete, instalador reconstruido.

## Fase S0 · Línea base y verificación de supuestos

1. **Estado del repo.** `git status` y `git log -5`; qué de `04` y `08` está sin commit; versión del instalador; confirma que `Backend\` se instala en claro (lista los `.py`, cuenta archivos y tamaño).
2. **Línea base de lectura (el ataque de hoy).** Con un usuario estándar y con uno administrador sobre un nodo instalado de prueba: ¿qué se lee? Documenta con comandos reales cuánto tarda en localizar (a) las vistas de DRF y los modelos, (b) los secretos (`backend.env`, `SECRET_KEY`), (c) la base. Es la **línea de comparación** del resto del trabajo.
3. **Línea base de pruebas y rendimiento.** Suite completa del backend (el último dato conocido: 2628 correctas, 18 omitidas), tiempo de arranque del servicio (`python -X importtime`), tamaño del paquete, uso de memoria en reposo.
4. **Verifica lo marcado [sin verificar]:** (a) qué identificadores puede pedir una app de Android con atestación de ID y quién puede (`setAttestationIds`, dispositivo propietario o app privilegiada) en la documentación vigente; (b) la API de Windows para **atestiguar una clave de TPM** y obtener EKCert (proveedor de plataforma de CNG, `Get-TpmEndorsementKeyInfo`, `TPM2_MakeCredential/ActivateCredential` en la especificación de la biblioteca de TPM 2.0 de TCG; la fuente de apoyo hallada es un tutorial, **no es normativa**); (c) la página de diseño de SQLCipher (derivación de claves, parámetros).
5. **Demuestra H-3 con tu máquina:** cambia la MAC de un adaptador (Windows) y comprueba que la huella actual **no** cambia pero una lista de MAC sí fallaría; deja la captura. **No cambies configuración permanente del equipo del usuario**: usa una máquina virtual o revierte.
6. **Inventario del TPM disponible** (versión, fabricante, si es discreto, firmware o Pluton) en el equipo de desarrollo y, si el CTO lo informa, en el panel (SQ-03). El resultado decide la sección de ataque físico en S6.
7. **Entrega:** sección «Línea base» en `09-segunda-proteccion.md` con números, y la lista de supuestos confirmados, refutados o abiertos.

## Fase S1 · El sello de dispositivo AVACOM

Diseña y construye, reutilizando `08` (clave `AVACOM-Identidad-*-v1`, reto de D-51) y la infraestructura de llaves de `07`:

1. **Formato del sello `.avsello`** (mismo estilo TLV/Ed25519 que `.avlic`, `kid` `sello-2026-1`): versión, `serie`, `modelo`, `origen` (`fabrica`/`entrega`), `clave_huella` (SHA-256 de la clave pública del equipo, la misma de la Fase 5), huella de la EKPub del TPM, la MAC y datos informativos **marcados como no decisivos** (SP-03), emitido, **vence o no** (decide y documenta: un sello sin vencimiento exige revocación fiable; uno con vencimiento exige renovación sin internet; SQ-05), id de lote. **Sin datos de personas.**
2. **Estación de aprovisionamiento** (`tools/`, junto al emisor de licencias; custodia de la llave como en `07`): verifica la **evidencia** (cadena de EKCert contra las raíces del fabricante del TPM que AVACOM decida confiar, o EKPub contra su inventario de series; atestación de Android si es una tableta), comprueba la prueba de posesión de la clave y firma. Registra cada sello emitido (bitácora del emisor). Rechaza evidencia ambigua.
3. **Solicitud y entrega sin teclado:** verbos del Host (`solicitar-sello` → `.avsol` en USB; `instalar-sello` ← `.avsello`) con el mismo estilo de los demás, salida legible y **cero entrada de texto**. En fábrica, el mismo código corre sin USB.
4. **Verificación en el equipo:** `Avacom.Ops.Host.exe verificar-dispositivo` comprueba (a) firma del sello con las llaves de confianza incrustadas (como la integridad de `04`: llaves vigentes y siguientes), (b) que `clave_huella` es la de la clave del equipo, (c) **prueba de posesión** firmando un reto local con la clave no exportable, (d) que el sello no está en la **lista de revocados** (firmada, distribuida con licencias y actualizaciones; el nodo guarda la más nueva que ha visto). Resultado: `autenticado` · `sin_sello` · `sello_invalido` · `clave_distinta` · `revocado` · `no_verificable`.
5. **Puerta de instalación.** En `AvacomOpsMaster.iss` (y la variante Student para Windows) un paso previo que ejecuta el verificador **desde la carpeta temporal del instalador** y, si no da `autenticado`, **detiene la instalación** con un mensaje claro y táctil («Este equipo no es un dispositivo AVACOM autenticado») y una ruta de salida humana (contactar a AVACOM; sin teclado). No ofrezcas un parámetro de línea de comandos que la apague (SP-10): el modo de desarrollo es el marcador `AVACOM-DESARROLLO`. **Documenta con franqueza** que el instalador se puede parchear; la protección real es S2/S3 (SP-05).
6. **Integración con la identidad de la Fase 5:** el nivel `hardware` de Windows nunca existió (D-52); ahora un sello válido **puede** elevarlo (`garantia: sellado`) **sólo** cuando la clave del equipo coincide con la del sello. Cambio mínimo y declarado en `device_manager` (como se hizo antes: ganchos pequeños, nunca escribir `m09_*` desde `licenciamiento`).
7. **Android** (tabletas): el sello se emite tras verificar la atestación del Keystore al aprovisionar; en campo no se puede leer la MAC (H-3), se confía en la clave del Keystore y en la firma del APK. **Declara que sin una tableta física esto no se probó** (SR-09).
8. **Pruebas:** vectores de firma con una llave de prueba; sello válido/alterado/vencido/revocado/de otro equipo/sin clave; la puerta del instalador (ensayo del paquete como el bloque G de `04`: sello válido → instala; sin sello → se niega; sello copiado a otro equipo → se niega); una prueba que demuestre que **cambiar la MAC o el SMBIOS no cambia el veredicto**.

**Criterio de cierre:** un instalador de producción sólo instala en un equipo con sello válido y clave presente, y una copia del sello en otro equipo no sirve.

## Fase S2 · Liberación de clave del paquete (*key release*) y la marca por dispositivo

Aquí se hace real el «no copiable» (SP-05):

1. El `Backend` (código propio) y, si el experimento lo justifica, partes del runtime viajan **cifrados con una clave de paquete `K`** (AEAD, XChaCha20-Poly1305 de `avacom_lic`; nada de criptografía nueva). `K` **no** va en el instalador: llega **envuelta para la clave de cifrado del equipo** (una RSA-OAEP o ECDH no exportable en TPM/Keystore, como el envoltorio de `08` §5) dentro del sello o de un archivo anexo. Sólo el TPM del equipo sellado la desenvuelve.
2. **Decide con un sí/no y mide:** (a) una `K` por **versión** (el sello lleva `K` envuelta; ligero; una `K` filtrada abre todas las copias de esa versión) frente a una `K` por **dispositivo** (re-cifrado en la instalación; mejor atribución y contención; más trabajo y más tamaño). Define el costo de rotar `K` en una actualización (`.avupd`) y de recuperar un equipo (TPM borrado, sello reemitido).
3. **Marca por dispositivo (SP-09):** un recurso del paquete derivado de la `clave_huella` y del `kid` del sello que permita decir «esta copia salió del equipo X», con una prueba que **la detecte y atribuya** una fuga de un archivo de datos.
4. **Qué ocurre sin clave:** el Host no puede abrir el código; el backend no arranca; mensaje claro; **antes** de arrancar no hay clase en curso (SP-02). Si un equipo sellado pierde la clave **con el nodo ya en uso** (TPM restablecido), el comportamiento es el de la gracia de SP-02 y se avisa a un técnico; nunca se pierde el expediente de las personas: **la base queda donde está**, sin envolver, hasta S3.
5. **Actualizaciones:** los paquetes `.avupd` de Update Manager deben llevar el código **ya cifrado** y respetar la liberación de clave. Cambio mínimo y declarado en `actualizacion`, **sin romper** el formato canónico ni la prueba de 100 000 mutaciones.
6. **Pruebas:** (1) copiar `Program Files\AVACOM\OPS Master` y `ProgramData` a otra máquina limpia: **no arranca ni sirve nada**; (2) extraer el payload del instalador y correrlo en un equipo sin sello: sin código en claro; (3) sello de otro equipo: falla; (4) equipo sellado legítimo: arranca con el mismo tiempo ±presupuesto de S0; (5) recuperar tras restablecer el TPM con un sello nuevo.

**Criterio de cierre:** las pruebas (1) a (3) pasan en el ensayo del paquete; el equipo legítimo arranca y la suite sigue verde.

## Fase S3 · Código del backend ilegible (experimento con sí/no)

Matriz de opciones, cada una medida contra la línea base de S0 y contra el ataque de lectura de S0. **Corre toda la suite** (≥ el mismo número de correctas), `makemigrations --check`, el arranque de Daphne/Channels, los comandos de `manage.py`, las migraciones y las plantillas. Presupuestos propuestos (ajústalos con S0): arranque **≤ +25 % y ≤ +3 s**, memoria **≤ +15 %**, paquete **≤ +30 %**, ninguna prueba nueva omitida.

| Opción | Qué es | Pregunta que debe responder el experimento |
|---|---|---|
| **A · Sin fuentes, sólo `.pyc`** | Quitar los `.py` y dejar bytecode | Cuánto tarda recuperar el código con las herramientas públicas de descompilación para **Python 3.12** (**verifícalo**, no lo supongas). Esperable: poco. Es la **línea base «de defensa mínima»** |
| **B · Compilar código propio** (Nuitka standalone o Cython) | `.pyd` por módulo de `backend/` salvo terceros (SP-06) | ¿Pasa la suite? ¿Las migraciones y `AppConfig` se descubren? ¿Cuánto tarda recuperar la **lógica** (no los nombres) con un desensamblador? ¿Las cadenas y las rutas quedan legibles? ¿La licencia (comercial o libre) permite redistribuir y qué cuesta (**no compres nada**; SQ-06)? |
| **C · Cifrado con cargador propio** | Un importador en `avacom_lic` que abre módulos en memoria con `K` (S2) | ¿Cuánto cuesta el cargador? ¿Rompe `inspect`, trazas, depuración de campo? ¿Qué se ve en un volcado de memoria? Documenta que **la clave está en memoria al ejecutar** |
| **D · Producto comercial** (Pyarmor, Nuitka comercial, CodeMeter) | Sólo **evaluación documental** | Licencia de redistribución, soporte de Python 3.12 y Windows x64, qué atan al dispositivo (**identificadores falsificables**, H-1), costo anual. **No adoptes ni instales** sin decisión del CTO |
| **E · B + C** | Compilado y cifrado | Costo acumulado frente a B sola |

**Decisión `SD-n`:** elige por **medición** (se pasa la suite, entra en presupuesto, sube el costo de lectura en el ataque de S0) y escríbela con la tabla de resultados, incluida la opción descartada y por qué. **Sin `.py`, sin `.pyc` legible y sin árbol de cadenas del dominio** en el paquete instalado cuando termines (comprobable con un barrido de las cadenas propias, como en S6).

Entregables: `Build-Installer.ps1` (o un script nuevo, `installer/build/Proteger-Backend.ps1`) que produzca el backend protegido; el `integridad.json` y el manifiesto firmado de la Fase 4 **siguen valiendo** sobre los archivos resultantes; la prueba de contenido del paquete verifica que no viaja un `.py` propio.

## Fase S4 · Datos y secretos en reposo atados al dispositivo

1. **Qué proteger, en orden:** (a) los secretos del backend (`SECRET_KEY`, `backend.env` y cualquier clave que hoy esté en texto claro), (b) la **base SQLite** con el expediente, (c) las colas y cachés (`cola_medios`, bitácora, `m15_evento`), (d) los registros del estado de la licencia (ya protegidos con DPAPI de máquina según el diseño).
2. **Clave de datos envuelta por el TPM** del equipo sellado (reutiliza `EnvoltorioDeClave` y el patrón de `08` §5; apagada de fábrica en esa fase, aquí decide si se enciende). Para la base: compara **SQLCipher** (cifrado de páginas, sin cambios en el ORM; hay que verificar el empaquetado para Windows y la compatibilidad con Django, **[sin verificar]**) con el **cifrado de campos sensibles** en la aplicación. Mide cuánto cuesta cada una.
3. **Lo que no puede romperse:** copias de seguridad, **exportaciones** (`boletines/`, `exportaciones/` son núcleo, D-6), Update Manager, restauración en otro equipo del **mismo** colegio (migración legítima, ver S5), y «Buscar» sobre FTS5. Cada una con su prueba. **El expediente de una persona nunca queda ilegible por un fallo del TPM**: define el procedimiento de recuperación (llave de recuperación bajo custodia de la institución, como CAP-111) antes de cifrar nada.
4. **Migración de nodos existentes** (el campo hoy tiene bases en claro): ruta explícita, reversible, con respaldo previo y con una prueba sobre una copia de una base real de pruebas.
5. **Declara el límite** del ataque físico: con TPM discreto y **sin PIN previo al arranque** la clave se puede espiar en el bus (H-1). En OPS no hay teclado, así que el PIN de arranque no es una opción; la mitigación es el TPM de firmware/Pluton si el hardware lo trae, y es una pregunta al CTO (SQ-03).

## Fase S5 · Entorno de ejecución y ciclo de vida

1. **Servicio:** de SYSTEM a una **cuenta virtual** (`NT SERVICE\AVACOMOPSBackend`) con los mínimos permisos (carpeta de datos, red local); ACL de **lectura restringida** sobre `Backend\`, `Runtime\` y `Config\`. Cuidado: el servicio también lanza OPS y gestiona actualizaciones (Host, `Aplicador.cs`): **prueba la instalación, el arranque, la actualización y la reversión** con la cuenta nueva antes de cambiarla.
2. **Sin intérprete suelto:** el Host incrusta Python (API de C) y **no instala `python.exe`** ni `pythonw.exe` (H-2.4); `._pth` fijo, modo aislado, sin `PYTHONSTARTUP` ni variables de entorno que alteren la carga. **Honestidad:** un administrador instala su propio Python y vuelve a leer lo que pueda; esto sólo encarece.
3. **App Control (WDAC):** **evaluación**, no imposición. Redacta una política **suplementaria en modo auditoría** que permita sólo los binarios firmados de AVACOM y mide qué rompe (Authenticode está pendiente: Q-L6…Q-L11). **No la impongas.** Si el CTO decide firmar con Authenticode, es una decisión aparte (SQ-04).
4. **Ganchos de auditoría de Python (PEP 578):** sólo como **detección** (importar un módulo desde fuera del árbol, cargar un `.pyd` no listado). Escribe en la bitácora encadenada. Nunca los llames «protección».
5. **Cadena de suministro del paquete:** comprueba el SHA-256 del Python embebido contra el de python.org en `Get-PythonRuntime.ps1`; `pip install --require-hashes` con un `requirements-runtime.txt` con hashes; falla el build si algo no coincide. (Defectos ajenos hallados en la Fase 4; aquí se arreglan.)
6. **BitLocker y Secure Boot como estado informado:** el Host lee si el volumen del sistema está cifrado y si Secure Boot está activo y lo añade a la señal de integridad (`/health/` sólo **añade** campos). Es información para el administrador; **no** bloquea nada.
7. **Ciclo de vida del sello:** (a) **reemplazo de equipo** (RMA, cambio de placa, TPM borrado): reemisión y revocación del sello viejo; (b) **traslado legítimo** de un nodo a otro equipo del mismo colegio (la licencia ya tiene «liberar este equipo»: define cómo se enlaza con el sello nuevo y con la clave de datos); (c) **revocación** de un equipo robado o reportado; (d) **rotación de la llave de sello** (llaves vigentes y siguientes ya viajan en el Host); (e) qué ve el administrador en OPS.
8. **Pantalla en OPS «Dispositivo AVACOM»** (táctil, sin teclado, regla de tercios, verificada con captura y cuadrícula): estado del sello, origen, fecha de emisión, serie, aviso de revocación, botón «Solicitar sello» y «Instalar sello» (USB). **Sin datos de personas ni de licencias** en lo que se muestra o se registra.
9. **Instaladores:** sube la versión, reconstruye `installer/latest` y deja el `LEEME.txt` y el `SHA256.txt` coherentes. El instalador de **Student** (Windows y APK) lleva la puerta de S1 sólo donde S1 diga que aplica.

## Fase S6 · Prueba adversarial y cierre

Sobre **builds Release**, en un entorno aislado (máquinas virtuales; nunca el escritorio del usuario), con presupuesto de tiempo y de intentos fijado antes de empezar, y un **segundo revisor** (humano o un agente distinto) que repita las metas más prometedoras. Resultado por ejercicio: **resistió / encareció (cuánto) / cayó**, con la evidencia.

| # | Ejercicio | Resultado esperado |
|---|---|---|
| E1 | Copiar la instalación y `ProgramData` a una máquina limpia | No arranca, sin código en claro |
| E2 | Clonar el disco o la máquina virtual a otro hardware (y, en Hyper-V, con TPM virtual) | No libera la clave; documenta el caso del TPM virtual |
| E3 | Cambiar MAC, SMBIOS y `MachineGuid` del equipo legítimo | El veredicto del sello no cambia (SP-03) |
| E4 | Extraer el payload del instalador y correrlo en un equipo sin sello | Cifrado e inútil |
| E5 | Barrido del árbol instalado con búsqueda de cadenas propias (nombres de clases/rutas del dominio, docstrings, URLs de la API) | **Cero** coincidencias legibles de lo que SP-06 manda proteger |
| E6 | Descompilación/desensamblado con herramientas públicas, tiempo acotado | Documenta qué se recupera y a qué costo |
| E7 | Parchear el Host para saltar `verificar-dispositivo` | El código sigue cifrado (SP-05); la integridad lo detecta |
| E8 | Reutilizar un sello de otro equipo; uno revocado; uno vencido; uno alterado | Falla en todos |
| E9 | Un administrador **del equipo legítimo** vuelca la memoria del proceso | **Se espera que caiga** (A4); mide cuánto cuesta y qué deja de rastro |
| E10 | Restablecer el TPM o reinstalar Windows | Recuperación documentada, sin perder el expediente |
| E11 | Un agente de IA con presupuesto fijo intenta (E1–E9) | Resultado como en el modelo de amenazas de A6 |

Entregables de cierre: `09-segunda-proteccion.md` con **qué impide, qué encarece, qué detecta, qué no cubre, resultados de E1–E11, «No se pudo comprobar» y riesgo residual aceptado**; actualiza §14 de `01-diseno.md` y `04-proteccion.md` **sólo con referencias** (no reescribas lo ajeno); actualiza `guia-usuario-interno.md` (quién aprovisiona y cómo se revoca) y `guia-usuario-cliente.md` (qué verá el administrador del colegio).

# Pruebas y criterios de aceptación

- **Suites** (con redirección de `ProgramData`, SR-10): backend completo (no menos correctas que la línea base), `dotnet test` de Core, Ops, Student y `Avacom.Ops.Host.Tests`, `makemigrations --check`. Cada módulo nuevo con su prueba del defecto: una por cada «no cubre» que convirtieron en «cubre».
- **Pruebas diferenciales** donde haya una referencia (la verificación del sello en C#, la nativa y la de Python deben dar el mismo veredicto y el mismo motivo), con semilla fija y mutación de sellos como en la Fase 4 (**100 000** mutaciones, **0 aceptadas**).
- **Ensayo del paquete** ampliado (bloques nuevos tras el G de `04`): instalación con sello, sin sello, con sello copiado; arranque; actualización; reversión; recuperación.
- **UIA** de la pantalla de OPS con captura y cuadrícula de tercios; Student sólo si cambia.
- **Rendimiento:** dentro de los presupuestos de S3; el tiempo de verificar un sello y de liberar `K` medido y por debajo del tope de +200 ms por petición que ya rige a la licencia (no debe estar en el camino de cada petición).
- **Instalador reconstruido** (SR-07) y probado en una máquina virtual limpia con un TPM virtual, declarando lo que un TPM virtual no demuestra.

# Preguntas para el CTO (`SQ-n`)

| # | Pregunta | Opción tomada mientras tanto |
|---|---|---|
| SQ-01 | **¿Qué es un «dispositivo AVACOM»?** ¿AVACOM fabrica o aprovisiona (panel, tableta) o son equipos de mercado entregados con el software? ¿Quién los aprovisiona y dónde (fábrica, bodega, colegio)? | Se diseñan los dos caminos (`fabrica` y `entrega`) con el mismo sello (H-4) |
| SQ-02 | Un nodo **ya instalado** que pierde el sello válido (TPM borrado, placa cambiada): ¿gracia (como la licencia) o restricción? ¿Cuántos días? | Gracia con los estados de la licencia, nunca a media clase (SP-02) |
| SQ-03 | Hardware real: ¿versión, fabricante y tipo de TPM del panel de 86" y de las tabletas (discreto, de firmware o Pluton)? ¿Se acepta TPM-sólo sin PIN de arranque? | Se documenta el riesgo del TPM discreto sin PIN; no se supone nada del panel |
| SQ-04 | **Firma de código (Authenticode) y App Control:** ¿se firmará con un certificado de AVACOM? ¿La política de App Control se impondrá o sólo se evaluará? | Sólo evaluación en auditoría (S5.3) |
| SQ-05 | ¿El sello **vence**? Sin vencimiento exige revocación fiable sin internet; con vencimiento exige renovar | Sin vencimiento + lista de revocados firmada y distribuida con licencias y actualizaciones |
| SQ-06 | **Compra de herramientas** de protección (Nuitka comercial, Pyarmor, CodeMeter, certificados): ¿hay presupuesto o se hace con lo libre? | Sólo lo libre; evaluación documental de lo comercial (S3, opción D) |
| SQ-07 | ¿Se amplía a **OPS, Host y Student** (IL descompilable)? El pedido nombra el backend | No: se anota como S4b y se deja la decisión aquí |
| SQ-08 | **Custodia de la llave de sello** (`sello-2026-1`): ¿mismo procedimiento que `prod-2026-1` (equipo y frase DPAPI) o un HSM/YubiKey dedicado? | Mismo procedimiento que `07-ceremonia-de-llaves.md` |
| SQ-09 | ¿Una **`K` por versión** (ligera) o **por dispositivo** (con atribución y contención de fugas)? | Se decide por medición en S2.2 con la recomendación documentada |
| SQ-10 | **Equipos ya instalados en campo sin sello:** ¿se les emite un sello de entrega, se les da un plazo, o quedan fuera? | Plazo con aviso, como la evaluación de la licencia |

---

# Anexo A · Fuentes usadas (verificadas en esta sesión, 2026-10-24)

**Límites de la ofuscación y la protección de software**

- Barak et al., *On the (Im)possibility of Obfuscating Programs*, CRYPTO 2001 — <https://eprint.iacr.org/2001/069> **[A]**
- Schrittwieser et al., *Protecting Software through Obfuscation…*, ACM Computing Surveys 49(1), 2016 — <https://eprints.cs.univie.ac.at/6372/> **[A]**
- Ceccato et al., *How Professional Hackers Understand Protected Code while Performing Attack Tasks*, ICPC 2017 — <https://arxiv.org/pdf/1704.02774v1> **[A]**
- Bos et al., *Differential Computation Analysis*, CHES 2016 — <https://eprint.iacr.org/2015/753> **[A]**
- Collberg y Thomborson, *Watermarking, Tamper-Proofing, and Obfuscation*, IEEE TSE 28(8), 2002 — <https://experts.arizona.edu/en/publications/watermarking-tamper-proofing-and-obfuscation-tools-for-software-p/> **[A]** (resumen verificado; el texto completo no se leyó)
- OWASP MASVS-RESILIENCE — <https://mas.owasp.org/MASVS/11-MASVS-RESILIENCE/> y MASTG iOS anti-reversing — <https://mas.owasp.org/MASTG/0x06j-Testing-Resiliency-Against-Reverse-Engineering/> **[P]** (la lista exacta de controles no se pudo leer completa: confírmala)

**Identidad y atestación de dispositivo**

- Android Open Source Project, *Key and ID attestation* — <https://source.android.com/docs/security/features/keystore/attestation> **[P]**
- Android Developers, *Best practices for unique identifiers* — <https://developer.android.com/identity/user-data-ids> **[P]**
- Android Developers, *Play Integrity API overview* — <https://developer.android.com/google/play/integrity/overview> **[P]**
- AOSP, *Implement MAC randomization* — <https://source.android.com/devices/tech/connect/wifi-mac-randomization> **[P]**
- Martin et al., *A Study of MAC Address Randomization in Mobile Devices and When it Fails*, PoPETs 2017 — <https://petsymposium.org/popets/2017/popets-2017-0054.pdf> **[A]**
- Microsoft Support, *Random hardware addresses in Windows* — <https://support.microsoft.com/en-us/windows/how-to-use-random-hardware-addresses-in-windows-ac58de34-35fc-31ff-c650-823fc48eb1bc> **[P]**
- Microsoft Learn, *TPM Key Attestation* — <https://learn.microsoft.com/windows-server/identity/ad-ds/manage/component-updates/tpm-key-attestation> **[P]**
- Microsoft Learn, *TPM fundamentals* — <https://learn.microsoft.com/en-us/windows/security/hardware-security/tpm/tpm-fundamentals> **[P]**
- Microsoft Learn, *BitLocker overview* — <https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/> **[P]**
- IEEE 802.1AR, *Secure Device Identity* — <https://1.ieee802.org/security/802-1ar/> **[P]**
- TCG, *EK Credential Profile for TPM Family 2.0 v2.6 r23* — <https://trustedcomputinggroup.org/wp-content/uploads/TCG-EK-Credential-Profile-for-TPM-Family-2.0-Level-0-Version-2.6-Revision-23_16July24.pdf> **[P]** (existe; no se leyó el contenido)
- Pulse Security, *Extracting BitLocker keys from a TPM* (2019) — <https://pulsesecurity.co.nz/articles/TPM-sniffing> y WithSecure, *Sniff, there leaks my BitLocker key* — <https://labs.withsecure.com/blog/sniff-there-leaks-my-bitlocker-key> **[P]** investigación original de los autores

**Ejecución de código y Python**

- Microsoft Learn, *App Control script enforcement* — <https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/design/script-enforcement> **[P]** (la frase sobre intérpretes de Python no iluminados está en la sección «Scripts that aren't directly controlled by App Control»)
- Microsoft Learn, *Application Control for Windows* — <https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/appcontrol> **[P]**
- PEP 578, *Python Runtime Audit Hooks* — <https://peps.python.org/pep-0578/> **[P]** (marcada como histórica; la tabla vigente está en la documentación de Python)
- Pyarmor, manual y *Understanding Obfuscated Script* — <https://pyarmor.readthedocs.io/en/stable/topic/obfuscated-script.html> **[V]** (documentación del proveedor; no declara un nivel de seguridad)
- Nuitka Commercial — <https://nuitka.net/doc/commercial.html> **[V]**
- PyInstaller 6.0 / CVE-2025-59042 — <https://nvd.nist.gov/vuln/detail/CVE-2025-59042> **[P]**
- Zetetic, *About SQLCipher* — <https://www.zetetic.net/sqlcipher/about/> **[V]** (el diseño de claves no se leyó)
- Wibu-Systems, AxProtector — notas de producto en <https://www.automation.com/en-us/products/october-2023/wibu-systems-axprotector-ctp-software-piracy> **[V]**

# Anexo B · Fuentes descartadas o rebajadas

| Fuente | Por qué |
|---|---|
| Blogs de comparación de protectores de Python (`beatsyncpro.ai`, `pyobfus.readthedocs.io`) | Escritos por un competidor o por un proveedor con interés en la comparación; sin metodología. Sólo sirvieron para detectar qué preguntar |
| Hilos de foro y de Q&A de aficionados (`yomotherboard.com`, Scribd, `viblo.asia`, foros de comunidad sobre MAC y GPO) | Anónimos, sin revisión, a menudo desactualizados |
| Espejos de contenido genérico o spam (varias páginas de MAC randomization con dominios ajenos al tema) | Sin autoría ni fuente; descartadas por completo |
| Sitio de preparación de exámenes (`certempire.com`) que atribuye a NIST SP 800-153 una frase sobre filtrado de MAC | **No se pudo confirmar** en el texto de NIST; **no se cita a NIST** sobre este punto. La conclusión sobre MAC se apoya en la documentación de Android, de Microsoft y en el estudio de PoPETs |
| Patentes (varias sobre suplantación de MAC y ofuscación) | Una patente describe una invención, no prueba que funcione |
| Notas de prensa tecnológicas (`cyware.com`, `3dtested.com`) sobre el espionaje del bus del TPM | Se sustituyen por la investigación original de Pulse Security y WithSecure |
| Tutorial de TPM en un repositorio personal (`git.broken-by-design.fr`) | Sólo como puntero: el comportamiento de `TPM2_MakeCredential/ActivateCredential` hay que confirmarlo en la **especificación normativa de TCG** en la Fase S0 |
| Wikipedia, «MAC filtering» | Enciclopedia general; no se usa como fuente de una decisión |
