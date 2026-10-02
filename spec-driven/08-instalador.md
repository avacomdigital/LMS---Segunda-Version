# 08 · Instalador de AVACOM OPS Master

| Campo | Valor |
|---|---|
| Ámbito | Distribución, instalación, actualización, configuración inicial, ejecución y desinstalación de AVACOM OPS Master y su backend |
| Estado | Implementado · versión 2.2.0. La 2.1.0 pasó el backend de Waitress a Daphne; la 2.2.0 incorpora Modo Estudio, Evaluación y Auditoría, y cierra lo que una instalación real destapó: permisos de escritura (la aplicación se cerraba al abrir una lección), registros y auditoría del nodo, configuración ajena y comunicación con AVACOM Contenido (artículos 12 a 15) |
| Código | [`installer/`](../installer/) · construcción con [`installer/build/Build-Installer.ps1`](../installer/build/Build-Installer.ps1) |
| Salida | `installer/latest/AVACOM-OPS-Master-Setup-<versión>.exe` (+ `SHA256.txt`, `LEEME.txt`, `AVACOM-Verificar-Instalador.bat` y una copia de `AVACOM-Probar-Comunicacion.bat`, el diagnóstico de la comunicación con Contenido): la carpeta es la release completa |
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

**Lo que sí está pedido y no se hizo aquí.** El perfil de WebView2 dentro del propio
producto (artículo 14, capa 3) es un cambio de código de OPS y de Student: queda
descrito y **pendiente de que se pida**. Mientras tanto lo resuelve el instalador.

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
| 2.9 | **Si el host muere, el backend se detiene solo** | `Ensayar-Paquete.ps1` mata el host y comprueba que el `python.exe` sale (y no deja `-wal`/`-shm`). En la 2.1 fallaba: con el host muerto la tubería de salida está rota y el primer `print` del hilo vigilante lanzaba `OSError` *antes* de pedir la parada, así que el backend quedaba huérfano con el puerto ocupado. Ahora todo se escribe con `_decir` (nunca lanza) y, si tras cerrar el expediente el intérprete no termina, sale a los 10 s |
| 2.10 | El backend se configura **solo** con `backend.env` | `ProcesoBackend` descarta toda variable `AVACOM_*` heredada de Windows (del usuario o del equipo) antes de aplicar `backend.env`; el ensayo envenena el entorno a propósito y comprueba que no cuenta |
| 2.11 | Sin configuración, el servicio no arranca el backend | `Configuracion.EsUtilizable` exige `backend.env` legible con `AVACOM_LMS_SECRET` y `AVACOM_LMS_DB`; si no, lo escribe en `servicio.log` y reintenta con la espera de siempre. Arrancaría con valores de desarrollo y una base **nueva** dentro de Program Files, y el aula «funcionaría» sobre un expediente vacío sin que nadie lo notara |

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
| 3.2 | El runtime empaquetado importa lo que el backend necesita | `Get-PythonRuntime.ps1` y `Preparar.cs` importan `django, rest_framework, channels, daphne, twisted, autobahn, zoneinfo, sqlite3, argon2, cryptography, jwt` |
| 3.3 | Lo que se prueba es lo que se distribuye | `Get-PythonRuntime.ps1` comprueba que cada paquete de `requirements-runtime.txt` quedó con **exactamente** la versión fijada |
| 3.4 | La app no necesita prerrequisitos | La compilación falla si faltan `hostfxr.dll` o `Microsoft.WindowsAppRuntime.dll` |
| 3.5 | No se distribuye la base de datos del desarrollador | La compilación falla si `db.sqlite3*` aparece en el paquete |
| 3.6 | No hay bytecode ni migraciones sueltas de otra versión | La compilación falla si hay `.pyc` en el backend a empaquetar |
| 3.7 | No se distribuyen los registros del desarrollador | `backend\logs` (y todo `*.log*`) se excluye al copiar, y la compilación falla si llega al paquete: son de otro equipo y llevarían identificadores ajenos a cada aula |
| 3.8 | El backend empaquetado es, **byte a byte**, el del repositorio | `Build-Installer.ps1` toma la huella de `backend/` al empezar y la compara con la del paquete (y otra vez al terminar, por si el código cambió durante la compilación) |
| 3.9 | Todas las apps instaladas llegan, con sus migraciones | Se lee `INSTALLED_APPS` de `settings.py` y cada app (acceso, device_manager, biblioteca, expediente, classroom_engine, modo_estudio, evaluacion, audit…) tiene que estar en el paquete con su carpeta `migrations` |

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
| 4.5 | Los cursos salen **siempre** de AVACOM Contenido | `backend.env` fija `AVACOM_AULA_FUENTE_CURSOS=biblioteca` y `AVACOM_AULA_PERMITIR_EJEMPLO=0` también en una **actualización** (`Configuracion.Normalizar`): un `backend.env` de una versión anterior, o tocado a mano, no puede dejar el ejemplo encendido. El ejemplo ni siquiera viaja en el paquete |
| 4.6 | Una nota de enlace de pruebas no deja al aula sin cursos | `AVACOM_CONTENIDO_ENLACE` y `_V2` se **retiran** de un nodo real (la línea queda comentada, se sabe que hubo) y se avisa en la pantalla final |

La comprobación de presencia (`link.json` o carpeta `Program Files\AVACOM\Contenido`)
es **informativa**: sin biblioteca el producto instala y arranca, pero el aula no
tendrá cursos. El contrato anterior (`contenido\enlace.json`) ya no se mira.
El artículo 15 detalla qué pasa con cada fallo de comunicación con la biblioteca.

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
| 5.6 | Una configuración que ya existe se lleva a lo que el producto exige **sin tocar las claves** | `Configuracion.Normalizar` (en cada `preparar`): agrega lo que falta, corrige solo lo que no admite otro valor y retira las notas de enlace de pruebas; escribe a un temporal y reemplaza (una luz que se va a mitad de escritura no deja `backend.env` a medias). Antes, `respaldar` ya dejó una copia. El ensayo de actualización comprueba que las cuatro claves son idénticas antes y después |
| 5.7 | Lo que Django ve **de verdad** es lo que se espera | `preparar` evalúa `django.conf.settings` tras leer `backend.env` (línea `Configuracion efectiva` en `instalacion.log`) y se detiene (código 8) si apunta a otra base de datos que la del nodo o con el curso de ejemplo encendido; avisa si los registros van a otra carpeta o a la temporal, si la depuración está encendida o si hay una nota de enlace de pruebas |

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
| Los textos dicen «Toca», no «Haga clic» | `ClickNext` y `ReadyLabel2a` están sobreescritos; la bienvenida ya no repite dos veces la instrucción de continuar |

**Lo que se vio al mirar las pantallas.** Las pantallas del asistente se
comprobaron **viéndolas**, con una copia de pruebas del asistente (sin permisos de
administrador, con un host de mentira que devuelve 0, sin accesos directos ni
entrada de desinstalación, y con otro nombre de aplicación para no cerrar la OPS
del desarrollador) conducida con mensajes de Windows y capturada con
`PrintWindow`. Salieron defectos que ningún compilador ni prueba de lógica puede ver
y que ya estaban en la 2.1:

| Defecto | Arreglo |
|---|---|
| Atrás, Siguiente y Cancelar crecían hacia la izquierda **uno encima de otro**: Atrás tapaba a Siguiente y éste a Cancelar | `DistribuirBotonesDeNavegacion`: se colocan desde el borde derecho, del mismo tamaño y con un hueco |
| «Examinar…» quedaba **debajo** de la caja de la ruta | `AjustarExaminar`: se alinea con la caja y ésta cede el espacio |
| «Volver a comprobar» se cortaba por el pie de la página | Se ancla al pie de su página y el resumen toma el espacio que queda |
| Las dos opciones de «Datos del aula» salían apretadas (≈ 24 px) pese a pedir 64 px | El alto mínimo se fija **antes** de agregarlas: después no se recalcula |
| La pantalla final **cortaba el texto**: la etiqueta mide lo que mide su texto de fábrica, así que la dirección para las tabletas —lo único que hay que escribir en ellas— no se veía | Ver 7.3 |
| `informacion.txt` empezaba con dos líneas en inglés heredadas de la plantilla | En español |

### 7.2 · La comprobación del equipo

Diez comprobaciones, con un botón «Volver a comprobar»:

Windows 10 **versión 1809 (compilación 17763)** o 11 —el Windows App SDK
autocontenido de la aplicación pide esa versión; el asistente declara
`MinVersion=10.0.17763` y la comprobación lo dice con esas palabras— ·
arquitectura de 64 bits · espacio en disco (1500 MB: la nueva versión más la
anterior apartada) · permisos de administrador · puerto 8000 · instalación previa ·
aplicación abierta (**ya no bloquea**: el asistente la cierra) · dependencias
incluidas en el paquete y runtime de WebView2 (avisa si falta) · AVACOM Contenido
(`link.json`) · red del aula (avisa si Windows la clasifica como **pública**).

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
organización; dice cómo ve el aula a AVACOM Contenido (*conectado, N cursos* o
*no está abierto ahora*); avisa si el servicio no está guardando sus registros;
y muestra los avisos de la preparación (base reemplazada, claves conservadas,
configuración corregida), recortados: el texto completo queda en los registros.
Todo sale de `Logs\resumen-nodo.txt`, que escribe el verbo `validar` del host.

**Cómo se dispone.** El contenido se reparte en tres bloques que se miden cada uno
con su propia letra y se apilan: la cabecera, **las direcciones en letra grande y en
negrita** (así se leen desde lejos, en una pantalla grande) y las notas. La casilla
«Abrir ahora» baja con ellos. Si no cabe en la página se baja la letra hasta 9; y si
aun así no cabe, los avisos de la configuración pasan a un solo renglón que remite a
los registros: lo importante es que se lea.

### 7.4 · Diagnóstico y verificador

`AVACOM-OPS-Master-Setup-<v>.exe /VERYSILENT /VOLCADO=<archivo>` ejecuta las
diez comprobaciones, las escribe y aborta sin tocar nada.

`installer/latest/AVACOM-Verificar-Instalador.bat` es el verificador: **un solo
archivo**, con el PowerShell dentro (fuente única:
`installer/tools/Verificar-Instalador.ps1`; lo genera `New-VerificadorBat.ps1`, que
lo pasa por el analizador de PowerShell y una prueba de extracción). Sirve antes de
instalar y, sobre todo, **después, cuando algo falla**. Revisa el instalador
(SHA256), el equipo (el volcado), lo instalado, los **permisos con la cuenta de quien
da la clase** (escritura real, no solo la lista de permisos), los registros, la
comunicación con AVACOM Contenido y, para el caso de «la aplicación se cierra»,
**el error exacto**: los cierres inesperados que Windows registró (Visor de
eventos, por proveedor e identificador, porque el texto sale en el idioma de
Windows) unidos a la excepción que la propia aplicación anotó en
`%LOCALAPPDATA%\AVACOM\lms\fallos-ops.log` de cada usuario. No cambia nada; deja
en el escritorio un informe y un `.zip` sin claves ni tokens. Salida: `0` todo en
orden, `1` problemas, `2` avisos.

La causa de que fuera necesario: un cierre por una excepción no controlada de la
interfaz queda en el Visor como `0xc000027b` en `Microsoft.UI.Xaml.dll`, la misma
firma para cualquier causa. Sin mirar `fallos-ops.log` de **ese usuario** no sale
el error, y el diagnóstico anterior solo miraba el backend.

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
| 10.1 | Lo empaquetado es la versión actual | `Build-Installer.ps1` publica desde el código fuente y falla si falta algo; el `manifiesto.json` instalado lleva versión, revisión de git, huellas del código, módulos del backend, servidor, política de datos y paquetes |
| 10.2 | No se distribuyen versiones anteriores | El script borra `AVACOM-OPS-Master-Setup-*` (el `.exe` **y** el `.tmp` que deja una compilación interrumpida) antes de compilar, y falla si queda algún `.tmp` |
| 10.3 | No se empaqueta un producto que no pasa sus pruebas | El paso 2 ejecuta la suite del backend y aborta si falla |
| 10.4 | El asistente se verifica a sí mismo | `Verificar-Asistente.ps1` ejecuta las diez comprobaciones de verdad en cada compilación |
| 10.5 | Una sola fuente de versión | `installer/version.json` (hoy 2.2.0); Student debe leerla también, para poder saber si un OPS y un Student son compatibles. **Sube cuando cambia el contrato de red** (2.2.0: `/api/modo-estudio/`, `/api/evaluacion/`, `/api/auditoria/`, `/api/logs/`) |
| 10.6 | La app empaquetada es la del código actual | Huella de `src/Avacom.Lms.Ops`, `Core`, `Ui` y `assets/` al empezar y al terminar; `-OmitirApp` solo reutiliza una publicación cuya huella coincide (`dist\staging\huella-app.txt`); la app tiene que ser más nueva que el último archivo de código. Antes bastaba con `-OmitirApp` para empaquetar una app de hacía semanas |
| 10.7 | El código no cambia mientras se compila | Las huellas de backend, app y asistente (incluidos `installer\src`, `tools` y `build`) se toman al empezar y al terminar; si difieren, el `.exe` se descarta |
| 10.8 | El instalador dice la verdad sobre su origen | `arbol_limpio` y la lista de archivos sin confirmar en git quedan en `manifiesto.json` y `SHA256.txt`; un árbol sucio se avisa, no se impide |
| 10.9 | El paquete **arranca** | `Ensayar-Paquete.ps1` (paso 7b): instalación nueva con el entorno envenenado, **actualización desde la versión anterior sobre una base con datos** (migra, claves intactas, el administrador inicia sesión), servicio sin configuración y lanzador. Si falla, no se compila |
| 10.10 | El `.exe` es de esta versión | Se lee la versión del propio archivo producido y su nombre; si no coinciden con `version.json`, se borra |

---

## 11 · Pendiente y decisiones sin cerrar

Pendiente de construir:

- **Instalador de AVACOM Student** (Windows: asistente, acceso directo,
  desinstalador y AppId propios, sin servicio ni firewall; Android: APK firmado
  con `ApplicationVersion` creciente). Debe tener su equivalente de
  `/VOLCADO` + verificador y leer `installer/version.json`.
- Pantalla de primer arranque de OPS que cree la organización y el primer
  administrador (tarea de la aplicación).
- El perfil de WebView2 dentro del producto (art. 14, capa 3).
- Probar en una OPS real: la instalación con permisos de administrador, una
  lección abierta tras instalar (que la aplicación **no se cierre**), la reversión de
  una actualización y la desinstalación. Las pantallas del asistente se vieron en
  una copia de pruebas sin administrador (7.1), y el paquete se ensayó de punta a
  punta en una carpeta de pruebas (host, backend, configuración, actualización
  desde la 2.1.0 con datos): ninguna de las dos cosas es una instalación.

Decisiones que el documento no toma y tienen recomendación:

| # | Tema | Estado |
|---|---|---|
| 1 | Política de datos al actualizar | Aplicada la recomendada: conservar si migra bien, reemplazar sólo si falla, con los dos botones táctiles mientras la política sea `reemplazables` |
| 2 | Quién crea la organización | Aplicada la recomendada (5.3) |
| 3 | Firewall en red pública | Sin elegir; sólo se avisa (art. 8) |
| 4 | OPS se abre sola al iniciar sesión (quiosco) | Sin implementar: hoy sólo el servicio arranca con Windows |
| 5–7 | Android mínimo, entrega del APK, Student en Windows por usuario o equipo | Corresponden al instalador de Student |
| 8 | Firma de código | Sin firma: SmartScreen advertirá de editor desconocido |
| 9 | Versión única | Aplicada en OPS: `installer/version.json` = 2.2.0 (los proyectos siguen diciendo 1.0) |
| 10 | Lectura de `backend.env` y de `Data` por los usuarios del equipo | Sin restringir (hereda ProgramData): las claves que cifran a las personas quedan legibles para un usuario local. Restringirlo exige cambios en el lanzador y en los diagnósticos (art. 12) |
| 11 | Perfil de WebView2 dentro del producto, y runtime de WebView2 en un Windows 10 limpio | Sin hacer: el primero es código de OPS y Student; el segundo es un instalador de ~170 MB sin conexión. Hoy el asistente solo avisa si falta (art. 14) |

---

## 12 · Permisos de escritura y lectura

El servicio corre como `SYSTEM` y es quien escribe la base y los registros; el
instalador y el mantenimiento los hace un administrador; la aplicación corre como
**quien da la clase** (`runasoriginaluser`: sin eso heredaría el token elevado del
instalador).

| # | Regla | Cómo se comprueba |
|---|---|---|
| 12.1 | `SYSTEM` y los administradores tienen control total, **explícito**, en cada carpeta de estado | `[Dirs]` con `Permissions: system-full admins-full` en `Config`, `Data`, `Respaldos`, `Logs` y `Logs\auditoria`. No se fía de lo heredado de ProgramData: una carpeta que ya existía con permisos raros dejaría al servicio sin poder escribir y al nodo funcionando sin guardar nada |
| 12.2 | Quien da la clase puede escribir en `Logs` | `users-modify` en `Logs` (el lanzador deja ahí su diagnóstico); el verificador lo prueba creando y borrando un archivo **con la cuenta de quien lo ejecuta** |
| 12.3 | Los binarios no se pueden reemplazar | `App\`, `Backend\` y `Runtime\` son de solo lectura para los usuarios; solo `App\Avacom.Lms.Ops.exe.WebView2` es escribible (art. 14) |
| 12.4 | El usuario del aula arranca y detiene el servicio sin credenciales | `sc sdset` (`RP`/`WP` a los usuarios interactivos, solo sobre este servicio) |
| 12.5 | El servicio no escribe `.pyc` en Program Files | `PYTHONDONTWRITEBYTECODE=1`; el ensayo comprueba que no queda `__pycache__` |
| 12.6 | Los permisos se **verifican**, no se suponen | `validar` comprueba que el módulo de acceso lee su base (código 15 si no) y que el backend escribe sus registros; el verificador revisa las listas de permisos y hace escrituras reales |

Lo que **no** se restringe: la lectura de `Config\backend.env` y de `Data` por los
usuarios (hereda lo de ProgramData). Contiene las claves que cifran a las personas,
así que un usuario local con acceso al equipo podría leerlas. Restringirlo exigiría
que el lanzador no leyera `backend.env` (hoy lee el puerto) y que el verificador y el
diagnóstico se ejecutaran elevados. Es una decisión de seguridad para el CTO, no del
instalador (ver artículo 11).

---

## 13 · Registros y auditoría del nodo

Los registros viven en `%ProgramData%\AVACOM\OPS Master\Logs`, fuera de la carpeta
del programa (que se borra al actualizar), con la marca de no desinstalar.

| # | Regla | Cómo se comprueba |
|---|---|---|
| 13.1 | El backend escribe en la carpeta del nodo | `backend.env` fija `AVACOM_LMS_ENTORNO=instalado` y `AVACOM_LMS_DIR_LOGS=<Logs>` (el backend los deducía de `AVACOM_LMS_DEBUG=0`; ahora es explícito y no depende de que alguien no toque la depuración) |
| 13.2 | El instalador comprueba que se pueden guardar | `preparar` evalúa la configuración efectiva (carpeta de registros efectiva y aviso de desvío a la temporal); `validar`, con el servicio en marcha, comprueba que `backend-app.log` tiene un renglón de los últimos 5 minutos (`registros=ok`/`sin_escritura`) |
| 13.3 | El host y el backend escriben el mismo `instalacion.log` sin perder líneas | `Registro` abre compartiendo lectura y escritura y reintenta; un fallo de rotación no impide escribir; un fallo de permisos desvía a la carpeta temporal del usuario |
| 13.4 | La salida de Python no sale rota | El host lee en UTF-8 (`StandardOutputEncoding`) y Python escribe en UTF-8 (`PYTHONIOENCODING`) |
| 13.5 | La bitácora de la instalación queda junto a los registros | El asistente copia la bitácora de Inno Setup (`{log}`, en `%TEMP%` de quien instaló) a `Logs\instalador-ultimo.log` (y la anterior a `instalador-anterior.log`), solo si la instalación llegó a empezar |
| 13.6 | La auditoría en archivo tiene dónde escribir | `Logs\auditoria` (tramos rotados y exportaciones firmadas; las filas de la bitácora nunca se borran al rotar) existe desde la instalación, con control total para `SYSTEM` |
| 13.7 | Los registros del desarrollador no viajan | Ver 3.7 |

Los registros de la aplicación (OPS y Student) están en el perfil de cada usuario:
`%LOCALAPPDATA%\AVACOM\lms\fallos-ops.log` y `logs\ops-*.log`.

---

## 14 · La aplicación se cerraba al abrir una lección

**Qué pasaba.** Tras instalar en una OPS real, el profesor daba una lección y la
aplicación se cerraba sin mensaje. Las lecciones con audio, video, PDF o laboratorio
usan WebView2 (el motor de Microsoft Edge), que guarda su perfil por defecto *junto
al ejecutable* (`App\Avacom.Lms.Ops.exe.WebView2`). La aplicación está en Program
Files, donde quien da la clase no puede escribir: al crear la primera WebView el
perfil no se puede crear y el proceso muere. En el equipo de desarrollo no se ve
porque corre desde `bin\Debug`. El Visor de eventos solo dice `0xc000027b` en
`Microsoft.UI.Xaml.dll`, que es la firma de cualquier excepción de la interfaz.

**Qué se hizo**, en capas, sin cambiar el código del producto:

| Capa | Qué | Cubre |
|---|---|---|
| 1 · el icono | `Avacom.Ops.Host.exe iniciar` abre la aplicación con `WEBVIEW2_USER_DATA_FOLDER` apuntando a `%LOCALAPPDATA%\AVACOM\OPS Master\WebView2`. Comprueba antes que se puede escribir (crea y borra un archivo); si no, prueba la carpeta temporal del usuario; y si tampoco, abre igual con la carpeta por defecto: un fallo de la carpeta no puede impedir abrir la aplicación. Respeta la variable si el entorno ya la trae | El icono del escritorio y el del menú Inicio (la forma normal de abrirla) |
| 2 · red de seguridad | El instalador crea `App\Avacom.Lms.Ops.exe.WebView2` con permiso de modificar para los usuarios (solo esa carpeta) y la borra al desinstalar | Abrir `Avacom.Lms.Ops.exe` directamente |
| 3 · en el producto | Poner esa misma variable en el arranque de OPS y de Student (3 líneas, junto a `WebViewAjustes`) | Cualquier forma de abrirla y **Student en Windows**, que tiene el mismo riesgo. **Pendiente de que se pida**: es un cambio de código |
| 4 · diagnóstico | El verificador recoge el error exacto (art. 7.4) | La próxima vez que algo se cierre, sale su causa |

Otros arreglos del lanzador que salieron de probarlo: «ya está abierta» compara la
**ruta** del ejecutable (una compilación de desarrollo abierta en otro sitio ya no
impide que el icono abra la instalada) y el perfil ya no se crea fuera de un
`try` (un fallo al crearlo impedía abrir la aplicación).

**Prueba.** `Ensayar-Paquete.ps1` ejecuta el lanzador con una aplicación de
mentira y comprueba que recibe el perfil de WebView2 del usuario y no el de la
carpeta del programa, que respeta una variable ya definida y que el perfil se crea
y se puede escribir. **No** se ha probado en una OPS real con una lección abierta.

---

## 15 · Si AVACOM Contenido falla, el aula no se rompe

La comunicación es de ida y por loopback: el backend lee `link.json` **en cada
petición** y habla con la API v2 de la biblioteca. El instalador nunca la toca ni
depende de ella.

| Situación | Qué pasa |
|---|---|
| AVACOM Contenido no está instalado | Se instala y arranca igual. El aula no tiene cursos. La comprobación 9 es informativa |
| Está cerrado, o `link.json` es de una sesión anterior | Igual. `/api/aula/fuente/` nunca devuelve 503 (`disponible: false` y el motivo); al abrir la biblioteca el aula recupera los cursos **sin reiniciar nada** |
| Reconstruye su índice | Igual: «vuelve a intentarlo en unos segundos» |
| `backend.env` traía una nota de enlace de pruebas | Se retira y se avisa (4.6) |
| El curso de ejemplo estaba encendido | Se apaga (4.5) |
| Una variable `AVACOM_CONTENIDO_*` o `AVACOM_AULA_*` en Windows | Se ignora (2.10) |
| Contenido contesta y el aula no ve cursos | El problema está en el backend (configuración, permiso de `SYSTEM` para leer `link.json`, servicio con un error). Lo dice el verificador (sección 7), que habla con la biblioteca directamente y compara |

El estado de la biblioteca visto desde el aula sale de `GET /api/aula/fuente/`, no
de `/health/`: el campo `biblioteca` de `/health/` habla del contrato anterior
(`enlace.json`) y respondería «no está abierta» con AVACOM Contenido funcionando.
(`Salud.Resumir` afirmaba eso en los registros; ya solo dice «backend operativo».)
