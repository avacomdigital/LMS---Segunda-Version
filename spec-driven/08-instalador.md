# 08 · Instalador de AVACOM OPS Master

| Campo | Valor |
|---|---|
| Ámbito | Distribución, instalación, actualización, configuración inicial, ejecución y desinstalación de AVACOM OPS Master y su backend |
| Estado | Implementado · versión 2.1.0 (actualiza la 2.0.0, que servía con Waitress) |
| Código | [`installer/`](../installer/) · construcción con [`installer/build/Build-Installer.ps1`](../installer/build/Build-Installer.ps1) |
| Salida | `installer/latest/AVACOM-OPS-Master-Setup-<versión>.exe` (+ `SHA256.txt`, `LEEME.txt` y `AVACOM-Verificar-Instalador.bat`) |
| Fuente de versión | [`installer/version.json`](../installer/version.json) |

Este documento registra las decisiones del instalador. La guía de uso está en
[`installer/README.md`](../installer/README.md).

**Alcance.** Este documento cubre el instalador de **AVACOM OPS Master**.
AVACOM Student (Windows y Android) tiene su propio instalador, identificador,
carpeta, versión y ciclo de publicación, y AVACOM Contenido tiene el suyo: aquí
sólo se cuenta cómo conviven con éste. El instalador de Student **no está
construido todavía** (ver «Pendiente»).

---

## 1 · Lo que el instalador no es

El instalador **no** es una oportunidad para arreglar nada del producto. Se
mueve dentro de un límite estrecho, y ese límite es el valor del documento:

| Prohibido | Cómo se cumple |
|---|---|
| Cambiar el comportamiento funcional | No se editó un solo archivo de `backend/` ni de `src/`. La configuración se entrega por variables de entorno, que `avacom_lms/settings.py` **ya** lee |
| Cambiar la arquitectura | Las propiedades de publicación viven en `installer/build/Distribucion.props` y se inyectan con `-p:CustomBeforeMicrosoftCommonProps`, no en los `.csproj` |
| Añadir rutas | `/health/` ya existía en `avacom_lms/urls.py`. El instalador lo consume tal cual |
| Tocar AVACOM Contenido | Ver el artículo 4 |
| Pedir comandos al usuario | Todo ocurre en el asistente; los `sc.exe` y `netsh.exe` los ejecuta el instalador |

Cambiar Waitress por Daphne es cambiar **cómo el instalador arranca el backend**
(`installer/src/payload/avacom_ops_backend.py`), no el backend.

La única decisión de configuración con consecuencia visible es
`AVACOM_LMS_DEBUG=0` en una instalación distribuida: un `DEBUG=1` publica
trazas con código fuente a toda la LAN del aula.

---

## 2 · El backend se ejecuta como servicio, sobre Daphne

**Principio.** La API del aula existe con independencia de que alguien tenga
abierta la interfaz.

**Por qué Daphne y no Waitress.** Desde el 2026-09-29 el aula tiene un canal en
tiempo real (WebSocket, Django Channels) en el mismo puerto 8000, y el
programador del nodo (presencia por latido, cierre de clases a los 120 minutos
de inactividad, archivado y detección de caída al arrancar) se inicia solo al
importar `avacom_lms.asgi`. Waitress es WSGI: ni atiende WebSocket ni inicia ese
programador.

```text
Windows
   └── Servicio AVACOMOPSBackend        Startup Type = Automatic
            └── Avacom.Ops.Host.exe servicio
                     └── python.exe avacom_ops_backend.py
                              └── Daphne  (avacom_lms.asgi:application)
                                       ├── HTTP      Django / DRF
                                       └── WebSocket Channels        → 0.0.0.0:8000
```

| # | Regla | Cómo se comprueba |
|---|---|---|
| 2.1 | Se usa Daphne, no `manage.py runserver` ni Waitress | `Runtime\avacom_ops_backend.py` invoca `daphne.cli`; el runtime no trae `waitress` (la compilación falla si aparece) |
| 2.2 | La aplicación ASGI y la configuración son las del producto | Se sirve `avacom_lms.asgi:application` con `DJANGO_SETTINGS_MODULE=avacom_lms.settings` |
| 2.3 | La escucha es `0.0.0.0:8000`, un solo puerto | HTTP y WebSocket comparten puerto: la regla de firewall no cambia |
| 2.4 | El servicio arranca con Windows | `sc qc AVACOMOPSBackend` muestra `AUTO_START` |
| 2.5 | Un backend caído se vuelve a levantar | El servicio reintenta con espera creciente (2 s → 60 s) y `sc failure` reinicia el servicio |
| 2.6 | El usuario del aula puede arrancarlo sin credenciales | `sc sdset` concede `RP`/`WP` a los usuarios interactivos **solo** sobre este servicio |
| 2.7 | Al parar, SQLite queda consistente | Ver abajo |
| 2.8 | El canal en tiempo real se valida al instalar | El verbo `validar` hace el saludo WebSocket contra `/ws/aula/sesiones/…`: aceptarlo (HTTP 101) prueba que Daphne y Channels sirven el WebSocket. Con Waitress respondía 404 |

**Parada limpia (2.7).** Daphne no cierra por señal en Windows y terminar el
proceso a la fuerza deja conexiones SQLite abiertas. El host arranca Python con
la entrada estándar abierta; para parar, escribe `detener` y la cierra. El
backend detiene Twisted, cierra las conexiones de Django y ejecuta
`PRAGMA wal_checkpoint(TRUNCATE)`, de modo que el expediente queda en **un solo
archivo**. Si el host muere, la entrada se cierra igual y el proceso no queda
huérfano. Sólo si no cierra en 15 s se termina el árbol de procesos (SQLite en
modo WAL se recupera solo de eso).

**Startup Type = Automatic** es explícito y deliberado: el nodo presta servicio
LAN antes de que se abra la interfaz.

---

## 3 · El paquete es autosuficiente

**Principio.** Se puede instalar en un aula sin internet y sin que nadie
instale Python ni .NET.

| Componente | Cómo viaja |
|---|---|
| Aplicación .NET MAUI | Publicada con `SelfContained` y `WindowsAppSDKSelfContained`: el runtime de .NET y el Windows App SDK van dentro |
| Python 3.12 | Paquete *embeddable* de python.org, sin instalador ni registro |
| Paquetes de Python | Resueltos en el equipo de compilación con ruedas para Windows / 3.12 / 64 bits (`--only-binary`, `--platform win_amd64`): Django, DRF, Channels, Daphne y sus transitivas (Twisted, autobahn, txaio, attrs, Automat, constantly, hyperlink, Incremental, zope.interface, pyOpenSSL, service-identity, idna, cbor2, msgpack, ujson, packaging, typing_extensions), más asgiref, sqlparse, tzdata, argon2-cffi, cryptography y PyJWT con las suyas |
| Backend AVACOM | Copiado de `backend/`, sin `.venv`, sin `__pycache__` y sin la base de desarrollo (`db.sqlite3` **ni** su `-wal`/`-shm`) |

| # | Regla | Cómo se comprueba |
|---|---|---|
| 3.1 | La instalación no ejecuta `pip` ni `winget`, ni compila nada | No aparecen en el `.iss` ni en `Avacom.Ops.Host.exe`; todo son ruedas precompiladas |
| 3.2 | El runtime empaquetado importa lo que el backend necesita | `Get-PythonRuntime.ps1` y `Preparar.cs` importan `django, rest_framework, channels, daphne, twisted, autobahn, zoneinfo, sqlite3` |
| 3.3 | Lo que se prueba es lo que se distribuye | `Get-PythonRuntime.ps1` comprueba que cada paquete de `requirements-runtime.txt` quedó con **exactamente** la versión fijada |
| 3.4 | La app no necesita prerrequisitos | La compilación falla si faltan `hostfxr.dll` o `Microsoft.WindowsAppRuntime.dll` |
| 3.5 | No se distribuye la base de datos del desarrollador | La compilación falla si `db.sqlite3*` aparece en el paquete |
| 3.6 | No hay bytecode ni migraciones sueltas de otra versión | La compilación falla si hay `.pyc` en el backend a empaquetar |

`requirements-runtime.txt` sale de resolver `backend/requirements.txt`; si éste
cambia, se vuelve a resolver.

---

## 4 · Convivencia con AVACOM Contenido

**Principio.** Los productos comparten el equipo y no comparten nada más.

| Recurso | AVACOM OPS Master | AVACOM Contenido |
|---|---|---|
| Identificador de instalación | `{B6D1F0A4-…-7F5C2E8D4A31}` (**no cambia** entre versiones) | El suyo |
| Archivos | `…\AVACOM\OPS Master` | `…\AVACOM\Contenido` |
| Configuración | `%ProgramData%\AVACOM\OPS Master\Config` | La suya |
| Base de datos | `%ProgramData%\AVACOM\OPS Master\Data\ops-master.sqlite3` | La suya |
| Logs | `%ProgramData%\AVACOM\OPS Master\Logs` | Los suyos |
| Servicio | `AVACOMOPSBackend` | — |
| Puerto | TCP 8000 (LAN) | loopback, puertos al azar |
| Regla de firewall | `AVACOM OPS Master Backend` | — |
| Menú inicio | Grupo `AVACOM OPS Master` | Grupo propio |

| # | Regla | Cómo se comprueba |
|---|---|---|
| 4.1 | Único punto de contacto: la nota de enlace, en modo lectura | `%ProgramData%\AVACOM\content\link.json` (puertos y token) la lee el backend en tiempo de ejecución; el instalador no la toca |
| 4.2 | `AVACOM_CONTENIDO_ENLACE` y `_V2` se dejan sin definir | Así el backend busca la nota donde la biblioteca la publica de verdad |
| 4.3 | La carpeta padre compartida no se borra | `{commonappdata}\AVACOM` va con `uninsneveruninstall`, y el desinstalador nunca la elimina |
| 4.4 | Desinstalar uno no afecta al otro | `AppId` distinto ⇒ entradas de desinstalación independientes |

La comprobación de presencia (`link.json` o carpeta `Program Files\AVACOM\Contenido`)
es **informativa**: sin biblioteca el producto instala y arranca, pero el aula no
tendrá cursos. El contrato anterior (`contenido\enlace.json`) ya no se mira.

---

## 5 · Los datos del nodo: política, copia y claves

«Los datos» no son sólo el expediente: la base contiene la organización, el
administrador, las personas importadas, los dispositivos, las clases y las
asignaciones de estudio. Borrarla obliga a repetir la instalación de la
organización, volver a importar el padrón y volver a registrar las tabletas.

### 5.1 · Política de datos: un dato de cada versión

Escrita en `manifiesto.json` (`politica_datos`) y compilada en el asistente
(`/DPoliticaDatos`). No es lógica cableada: pasar al modo protegido, cuando
llegue el módulo de progreso y calificaciones, es compilar con
`Build-Installer.ps1 -PoliticaDatos protegidos`.

| | `reemplazables` (hoy) | `protegidos` |
|---|---|---|
| Se conserva la base al actualizar | Sí, si migra sin error | Siempre |
| Copia de seguridad previa | Sí | Obligatoria |
| Una migración que falla | Se retira la base (la copia queda hecha) y se crea una nueva; se avisa en la pantalla final | Se restaura la copia y se vuelve a la versión anterior; no se destruye nada |
| Pantalla «Datos del aula» (**Conservar los datos** / **Empezar de cero**) | Se muestra si ya hay datos | No existe |
| Desinstalar | Pregunta; por defecto **conserva** | Ídem |

Si el manifiesto falta o no se puede leer, el host asume **protegidos**: perder
datos por un manifiesto roto es peor que detener una actualización.

### 5.2 · Base y `backend.env` son una sola cosa

La base se abre en modo WAL: junto al archivo aparecen `-wal` y `-shm`.
**Copiar, respaldar, restaurar o borrar la base es tratar los tres**, con el
servicio detenido. Además, `backend.env` guarda las tres claves de acceso
(`AVACOM_LMS_CLAVE_DATOS`, `_INDICE`, `_TOKENS`) que cifran y buscan a las
personas guardadas: se conservan o se reemplazan **juntos**.

| # | Regla | Cómo se comprueba |
|---|---|---|
| 5.1 | Las claves se generan una vez, en la primera instalación (32 bytes en base64 cada una) | `Configuracion.CrearSiFalta` no sobrescribe un `backend.env` existente |
| 5.2 | Nunca se agregan claves nuevas en silencio a una base con personas | `CompletarClavesDeAcceso`: una configuración de la 2.0.0 (sólo `AVACOM_LMS_SECRET`) recibe las claves únicamente si `m01_persona` está vacía; si no, sigue con las derivadas y lo avisa |
| 5.3 | La copia incluye base, `-wal`, `-shm` y `backend.env` | `Datos.Respaldar` → `Respaldos\<versión>-<fecha>\`, se conservan las últimas cinco |
| 5.4 | El expediente no vive en la carpeta del programa | `AVACOM_LMS_DB` apunta a `%ProgramData%\AVACOM\OPS Master\Data` |
| 5.5 | Los datos de estado se crean con la marca de no desinstalar | `Config`, `Data`, `Logs` y `Respaldos` con `uninsneveruninstall` |

### 5.3 · La organización y el primer administrador

Tras migrar, el nodo no tiene organización ni administrador y el login responde
`409 no_instalado`. Crearlos es texto libre (documento, nombres, código de la
organización) y el nodo no tiene teclado, así que **no se pide en el
asistente**. Decisión aplicada (recomendada en la Q-decisión 2): el instalador
deja el nodo listo —migrado, con claves— y **avisa en la pantalla final** si no
hay organización; la creación es una pantalla de primer arranque de OPS, que sí
puede usar el teclado táctil de Windows. Es una tarea de la aplicación, no del
instalador.

---

## 6 · Instalar, actualizar y volver atrás

Cada versión trae su runtime completo. Django carga **todos** los archivos de
migraciones que encuentra en la carpeta: una migración que la versión nueva ya
no trae pero que quedó de la anterior rompe `migrate`. Lo mismo pasa con
paquetes que dejan de usarse y con cachés compiladas. Por eso nunca se mezcla:
la versión anterior se **aparta** antes de copiar la nueva.

```text
 1  Detectar la instalación previa por su AppId y leer su versión
 2  Detener el servicio (el host espera a que pare; el backend cierra SQLite)
    y cerrar la aplicación propia (Avacom.Lms.Ops.exe, y sólo esa)
 3  Apartar App\, Backend\ y Runtime\ a  <instalación>\Anterior\
 4  Copiar lo nuevo sobre carpetas vacías          (InstallDelete como red de seguridad)
 5  Copia de seguridad de los datos (base + -wal + -shm + backend.env)
 6  Preparar: claves, comprobación del runtime, manage.py check, migrate,
    collectstatic sólo si hay STATIC_ROOT
 7  Volver a registrar el servicio y la regla de firewall (el comando cambió)
 8  Arrancar y validar: /health/ responde y el canal en tiempo real acepta conexiones
 9  Todo bien → se borra Anterior\.   Algo falla en 5–8 → REVERTIR
```

**Revertir.** Si algo falla entre los pasos 5 y 8 (o la instalación se
interrumpe después del 3, por ejemplo por falta de disco), el asistente:
detiene lo nuevo, restaura los datos desde la copia, retira lo nuevo, devuelve
`Anterior\` a su sitio, vuelve a registrar el servicio y la regla **con el host
de la versión anterior**, restablece la versión mostrada en «Aplicaciones
instaladas» y lo dice en la pantalla final. El aula queda con la versión
anterior funcionando, no a medias. En una primera instalación no hay a qué
volver: se avisa del fallo y se deja el detalle en los registros.

| # | Regla | Cómo se comprueba |
|---|---|---|
| 6.1 | Una versión nueva se reconoce como actualización | El `AppId` no cambia; `DisplayVersion` es la de `installer/version.json` |
| 6.2 | No quedan restos de la versión anterior | Se aparta antes de copiar; tras instalar, `Anterior\` no existe |
| 6.3 | Sólo se cierra lo propio | `taskkill /IM Avacom.Lms.Ops.exe`; nunca un proceso ajeno |
| 6.4 | Una migración que falla no deja el equipo a medias | Política de datos (5.1) + reversión |
| 6.5 | El instalador pide permisos de administrador una sola vez | `PrivilegesRequired=admin`; la app se lanza con `runasoriginaluser` |

---

## 7 · El asistente

```text
Bienvenido → Información AVACOM LMS 2.0 → Carpeta de instalación
   → Comprobación del equipo → [Datos del aula] → Listo para instalar
   → Instalando → Configuración del backend → Instalación completada
```

«Datos del aula» sólo aparece si ya hay datos **y** la política los deja elegir.

### 7.1 · Pantalla táctil, sin teclado

El nodo principal del aula tiene pantalla táctil y **no tiene teclado**. El
asistente se maneja íntegramente con toques:

| Decisión | Motivo |
|---|---|
| Ningún campo de texto obligatorio | No hay teclado con el que rellenarlo |
| La caja de la ruta es de sólo lectura | Se elige con «Examinar» o con «Usar la carpeta recomendada» |
| Ventana al 150 %, botones de 150 × 46 px | Objetivos de toque, no de ratón |
| Casillas y opciones de 34–64 px de alto | Ídem |
| Cada aviso se cierra con un toque | Ningún diálogo pide escribir ni confirmar dos veces |
| **El icono del escritorio no es una casilla** | Un toque accidental no puede dejar la OPS sin icono: se crea siempre (y el del menú Inicio) |
| Desinstalar y actualizar cierran solos la aplicación propia | Pedir que se cierre y se reintente es un paso más sin teclado |

### 7.2 · La comprobación del equipo

Diez comprobaciones, con un botón «Volver a comprobar»:

Windows 10/11 · arquitectura de 64 bits · espacio en disco (1500 MB: la nueva
versión más la anterior apartada) · permisos de administrador · puerto 8000 ·
instalación previa · aplicación abierta (**ya no bloquea**: el asistente la
cierra) · dependencias incluidas en el paquete · AVACOM Contenido (`link.json`) ·
red del aula (avisa si Windows la clasifica como **pública**).

**El puerto 8000:**

| Situación | Qué hace el asistente |
|---|---|
| Libre | Continúa |
| Ocupado, y `/health/` responde `avacom-lms-backend` | Es una actualización: avisa, continúa, y detiene su propio servicio antes de copiar archivos |
| Ocupado por otro programa | Se detiene con un mensaje entendible y **no cierra nada** |

Los WebSocket usan el mismo puerto: no hay reglas nuevas.

### 7.3 · La pantalla final

Muestra las direcciones IPv4 del equipo (sin loopback, sin `169.254.x.x` y sin
adaptadores virtuales) en letra grande, con la frase de qué escribir en las
tabletas —`http://<ip>:8000`—, sin tocar el backend; avisa si falta la
organización; y muestra los avisos de la preparación (base reemplazada, claves
conservadas). Las direcciones las calcula el verbo `validar` del host.

### 7.4 · Diagnóstico sin instalar

`AVACOM-OPS-Master-Setup-<v>.exe /VERYSILENT /VOLCADO=<archivo>` ejecuta las
diez comprobaciones, las escribe y aborta sin tocar nada.
`installer/latest/AVACOM-Verificar-Instalador.bat` lo automatiza: verifica la
huella SHA256, ejecuta el volcado y muestra el estado de lo ya instalado
(versión, servicio, puerto, `/health/`, datos, respaldos, registros).

---

## 7.5 · La marca es la de AVACOM, y sale de un solo sitio

La plantilla de .NET MAUI trae el logotipo de Microsoft. Inno Setup, por su
parte, pone sus propias ilustraciones en todas las pantallas si no se le dan
otras.

Fuente única: [`assets/avacom-symbol.svg`](../assets/avacom-symbol.svg).

| # | Regla | Cómo se comprueba |
|---|---|---|
| 7.5.1 | El símbolo no se duplica a mano | `avacom_mark` se enlaza al asset desde el `.csproj`; icono y arranque sólo envuelven sus trazos en otro lienzo |
| 7.5.2 | Las imágenes del asistente son el mismo símbolo | `New-ImagenesAsistente.ps1` las compone del PNG que rasterizó la compilación de la app |
| 7.5.3 | El logo de la plantilla no puede volver | La compilación falla si `appicon.svg` contiene `512BD4` |

---

## 8 · Firewall

El backend escucha en `0.0.0.0:8000` porque las tabletas llegan por la IP del
equipo maestro. Sin regla, Windows bloquea esas conexiones.

| Campo | Valor |
|---|---|
| Nombre | `AVACOM OPS Master Backend` |
| Protocolo y puerto | TCP 8000, entrante (HTTP y WebSocket) |
| Perfiles | `private`, `domain` |
| Programa | El `python.exe` del runtime instalado |

Se excluye el perfil público a propósito: la API no exige sesión por defecto y
el aula es una red privada. **Riesgo abierto** (Decisión 3): si Windows clasifica
la red del aula como pública, las tabletas no llegan. Mitigación aplicada, sin
elegir aún entre las tres opciones: la comprobación del equipo lo **avisa**.
La regla se recrea en cada instalación porque el comando que ejecuta cambia.

---

## 9 · Desinstalar

Desde «Aplicaciones instaladas» y desde el menú Inicio. Detiene el servicio, lo
elimina, retira la regla de firewall, borra los archivos del programa y los
accesos directos. **Al final pregunta** si eliminar también los datos; la
respuesta por defecto es **conservarlos** y vale para la base y para
`backend.env` juntos. No borra `%ProgramData%\AVACOM` ni nada de AVACOM
Contenido. Reinstalar después, conservando los datos, deja el aula como estaba,
con las personas todavía descifrables.

---

## 10 · Distribución

El instalador ronda los 100 MB, contra un límite de 100 MB por archivo en un
push a GitHub. Se distribuye como *release asset*; en el repositorio quedan el
código que lo reconstruye, `installer/latest/SHA256.txt`,
`installer/latest/LEEME.txt` y `AVACOM-Verificar-Instalador.bat`.

| # | Regla | Cómo se comprueba |
|---|---|---|
| 10.1 | Lo empaquetado es la versión actual | `Build-Installer.ps1` publica desde el código fuente y falla si falta algo; el `manifiesto.json` instalado lleva versión, revisión de git, servidor, política de datos y paquetes |
| 10.2 | No se distribuyen versiones anteriores | El script borra los `.exe` previos de `installer/latest` antes de compilar |
| 10.3 | No se empaqueta un producto que no pasa sus pruebas | El paso 2 ejecuta la suite del backend y aborta si falla |
| 10.4 | El asistente se verifica a sí mismo | `Verificar-Asistente.ps1` ejecuta las diez comprobaciones de verdad en cada compilación |
| 10.5 | Una sola fuente de versión | `installer/version.json` (hoy 2.1.0); Student debe leerla también, para poder saber si un OPS y un Student son compatibles |

---

## 11 · Pendiente y decisiones sin cerrar

Pendiente de construir:

- **Instalador de AVACOM Student** (Windows: asistente, acceso directo,
  desinstalador y AppId propios, sin servicio ni firewall; Android: APK firmado
  con `ApplicationVersion` creciente). Debe tener su equivalente de
  `/VOLCADO` + verificador y leer `installer/version.json`.
- Pantalla de primer arranque de OPS que cree la organización y el primer
  administrador (tarea de la aplicación).

Decisiones que el documento no toma y tienen recomendación:

| # | Tema | Estado |
|---|---|---|
| 1 | Política de datos al actualizar | Aplicada la recomendada: conservar si migra bien, reemplazar sólo si falla, con los dos botones táctiles mientras la política sea `reemplazables` |
| 2 | Quién crea la organización | Aplicada la recomendada (5.3) |
| 3 | Firewall en red pública | Sin elegir; sólo se avisa (art. 8) |
| 4 | OPS se abre sola al iniciar sesión (quiosco) | Sin implementar: hoy sólo el servicio arranca con Windows |
| 5–7 | Android mínimo, entrega del APK, Student en Windows por usuario o equipo | Corresponden al instalador de Student |
| 8 | Firma de código | Sin firma: SmartScreen advertirá de editor desconocido |
| 9 | Versión única | Aplicada en OPS: `installer/version.json` = 2.1.0 (los proyectos siguen diciendo 1.0) |
