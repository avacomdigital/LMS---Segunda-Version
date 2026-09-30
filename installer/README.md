# Instalador de AVACOM OPS Master

Produce un único `.exe` que instala en un equipo Windows la aplicación del
profesor y la API local del aula, sin pedirle al usuario que escriba nada.

```text
installer/
├── build/
│   ├── Build-Installer.ps1     Un comando: del código fuente al .exe
│   ├── Get-PythonRuntime.ps1   Ensambla el Python embebido con Django/DRF/Channels/Daphne
│   ├── Distribucion.props      Propiedades de publicación (no toca ningún .csproj)
│   ├── New-ImagenesAsistente.ps1  Imágenes de marca de las pantallas del asistente
│   ├── New-ProbadorBat.ps1     Empaqueta el diagnóstico en un .bat autocontenido
│   ├── Verificar-Asistente.ps1 Ejecuta las comprobaciones del asistente de verdad
│   └── PruebaAsistente.iss     Arnés: la misma lógica, sin nada que instalar
├── src/
│   ├── AvacomOpsMaster.iss     El asistente (Inno Setup 6): 8 pantallas, +1 de datos
│   ├── definiciones.iss        Nombres, versión, puerto y servicio, en un sitio
│   ├── codigo.iss              La lógica del asistente (compartida con el arnés)
│   ├── informacion.txt         Pantalla 2 · Información de AVACOM LMS 2.0
│   ├── host/                   Avacom.Ops.Host: servicio, lanzador y preparación
│   └── payload/
│       ├── avacom_ops_backend.py       Arranque de Daphne (ASGI, parada limpia)
│       └── requirements-runtime.txt    Dependencias que viajan en el paquete
├── version.json                Fuente única de la versión del producto
├── tools/
│   ├── AVACOM-Probar-Comunicacion.bat  Diagnóstico en UN archivo (lo que se distribuye)
│   └── Probar-Comunicacion.ps1         Su código fuente
└── latest/
    ├── AVACOM-OPS-Master-Setup-<versión>.exe
    ├── SHA256.txt
    ├── LEEME.txt
    └── AVACOM-Verificar-Instalador.bat   Revisa el equipo y el instalador, sin instalar
```

## Construirlo

```powershell
powershell -ExecutionPolicy Bypass -File installer\build\Build-Installer.ps1
```

Requiere, **solo en el equipo de compilación**: .NET SDK 10, Python 3.12 e
Inno Setup 6 (`winget install JRSoftware.InnoSetup`), y acceso a internet la
primera vez, para descargar el runtime de Python que después viaja dentro del
paquete.

El script pasa las pruebas del backend, publica la app, ensambla el runtime,
copia el backend, escribe el manifiesto, **verifica el asistente** y lo compila.
Si algo falla, se detiene: no produce un instalador a medias. Con `-OmitirApp`
reutiliza la publicación anterior de la app, que es la etapa lenta.

## Comprobar un equipo sin instalar nada

El propio instalador sabe diagnosticar sin tocar el equipo. Con `/VOLCADO`
ejecuta sus nueve comprobaciones, las escribe en un archivo y aborta:

```powershell
.\AVACOM-OPS-Master-Setup-2.0.0.exe /VERYSILENT /VOLCADO=C:	emp\diagnostico.txt
```

Eso es también lo que usa `Verificar-Asistente.ps1` en cada compilación: un
compilador comprueba la sintaxis del asistente, no que su lógica funcione en un
Windows real (parsear `netstat`, preguntar a `/health/` por COM, leer el
registro, crear los controles de la página táctil).

## Lo que instala

```text
AVACOM OPS Master
│
├── App\        Aplicación .NET MAUI, con el runtime de .NET y el
│               Windows App SDK dentro (no hay prerrequisitos)
├── Backend\    Django + Django REST Framework, tal cual está en backend\
├── Runtime\    Python 3.12 embebido + Django + DRF + Channels + Daphne
│               + Avacom.Ops.Host.exe (servicio, lanzador, preparación)
├── manifiesto.json   versión, revisión de git, servidor, política de datos, paquetes
└── LEEME.txt
```

Y fuera de la carpeta del programa, porque cambia con el uso:

```text
%ProgramData%\AVACOM\OPS Master\Config      backend.env (claves de este nodo)
%ProgramData%\AVACOM\OPS Master\Data        ops-master.sqlite3 (+ -wal y -shm): la base del nodo
%ProgramData%\AVACOM\OPS Master\Respaldos   copias previas a cada actualización (las últimas 5)
%ProgramData%\AVACOM\OPS Master\Logs        instalacion, servicio, backend, lanzador
```

La base no es sólo el expediente: guarda la organización, el administrador, las
personas, los dispositivos, las clases y las asignaciones de estudio. Vive ahí
para sobrevivir a reinstalaciones y actualizaciones, y sólo se borra si en la
desinstalación se pide expresamente. **La base (con su `-wal` y su `-shm`) y
`backend.env` van juntos**: las claves de éste cifran las personas guardadas en
aquélla.

Fuera de `%ProgramData%\AVACOM\OPS Master` no se escribe nada: la carpeta padre
`%ProgramData%\AVACOM` es compartida con AVACOM Contenido y nunca se borra.

## Cómo se ejecuta el backend

```text
Windows
   │
   ├── AVACOM OPS Master  (icono)
   │        └── Avacom.Ops.Host.exe iniciar
   │                 servicio en marcha → /health/ validado → interfaz
   │
   └── Servicio AVACOMOPSBackend   (Startup Type = Automatic)
            └── Avacom.Ops.Host.exe servicio
                     └── python.exe avacom_ops_backend.py
                              └── Daphne  (avacom_lms.asgi:application)
                                       └── Django / DRF + WebSocket → 0.0.0.0:8000
```

`Startup Type = Automatic` es deliberado: el nodo debe atender a las tabletas
desde que arranca Windows, sin esperar a que alguien abra la interfaz. Si el
backend se cae, el servicio lo reinicia con espera creciente, y Windows
reinicia el servicio si es él el que muere.

No se usa `manage.py runserver`: es un servidor de desarrollo. Desde la versión
2.1 tampoco Waitress, que es WSGI: se usa **Daphne**, servidor ASGI, sirviendo
`avacom_lms.asgi:application`. Atiende HTTP y el canal en tiempo real del aula
(WebSocket, Channels) **en el mismo puerto**, y al importar `asgi.py` inicia el
programador del nodo (presencia por latido, cierre por inactividad, archivado,
detección de caída). Por eso el puerto sigue siendo uno solo y la regla de
firewall no cambia.

Para parar, el host le cierra al backend la entrada estándar: el backend detiene
Twisted, cierra Django y vuelca el WAL de SQLite, de modo que el expediente queda
en un solo archivo. Sólo si no cierra en 15 s se termina el proceso.

### Verbos de `Avacom.Ops.Host.exe`

| Verbo | Quién lo usa | Qué hace |
|---|---|---|
| `servicio` | El SCM de Windows | Punto de entrada del servicio |
| `iniciar` | El icono del escritorio | Backend → validación → interfaz |
| `respaldar <versión>` | El instalador | Copia base + `-wal` + `-shm` + `backend.env` a `Respaldos\` |
| `vaciar-datos`, `restaurar-datos` | El instalador | «Empezar de cero» / volver a la copia |
| `preparar` | El instalador | Claves, comprobación del runtime, migraciones (según la política de datos) |
| `validar [seg]` | El instalador | `/health/` responde **y** el WebSocket acepta conexiones; escribe `Logs\resumen-nodo.txt` |
| `salud [seg]` | Diagnóstico | Espera a que `/health/` responda |
| `puerto-libre` | Diagnóstico | 0 libre · 12 nuestro backend · 13 ajeno |
| `instalar-servicio`, `quitar-servicio` | El instalador | Registro en el SCM |
| `iniciar-servicio`, `detener-servicio` | El instalador | Control del servicio |
| `abrir-firewall`, `cerrar-firewall` | El instalador | Regla TCP 8000 |

Ninguno pide interacción. El único que muestra algo es `iniciar`, y solo si el
backend no responde.

## Las pantallas

| # | Pantalla | Qué ocurre |
|---|---|---|
| 1 | Bienvenido | — |
| 2 | Información de AVACOM LMS 2.0 | `informacion.txt` |
| 3 | Carpeta de instalación | `C:\Program Files\AVACOM\OPS Master` |
| 4 | Comprobación del equipo | 10 comprobaciones, con «Volver a comprobar» |
| 4b | Datos del aula | **Conservar los datos** / **Empezar de cero**. Sólo si ya hay datos y la política de esta versión es `reemplazables` |
| 5 | Listo para instalar | Resumen de lo que se va a hacer |
| 6 | Instalando | Copia de archivos |
| 7 | Configuración del backend | Copia de seguridad, claves, migraciones, servicio, firewall, validación |
| 8 | Instalación completada | Las direcciones para las tabletas en letra grande, aviso si falta la organización, casilla para abrir el producto |

### Pantalla 4 · qué se comprueba

Windows 10/11 · arquitectura de 64 bits · espacio en disco · permisos de
administrador · **puerto 8000** · instalación previa · aplicación abierta (no
bloquea: el asistente la cierra) · dependencias del backend · AVACOM Contenido
(`link.json`) · red del aula (avisa si Windows la marca como pública).

Sobre el puerto 8000, el asistente distingue dos casos que se parecen y no son
lo mismo:

- **Lo ocupa un backend de AVACOM OPS** (se comprueba preguntando a
  `/health/`): es una reinstalación. Se avisa y se continúa; el propio
  instalador detiene su servicio antes de copiar archivos.
- **Lo ocupa otro programa**: la instalación se detiene con un mensaje
  entendible y **no cierra nada ajeno**. El usuario cierra ese programa y toca
  «Volver a comprobar».

## Pantalla táctil, sin teclado

El nodo principal del aula se maneja solo con toques, así que:

- ningún campo de texto es obligatorio: la caja de la ruta es de solo lectura
  y la carpeta se elige con «Examinar» o con el botón «Usar la carpeta
  recomendada»;
- la ventana se abre al 150 % y los botones del asistente miden 150 × 46 px;
- las casillas y opciones tienen entre 34 y 64 px de alto;
- el icono del escritorio **no es una casilla**: se crea siempre (y el del menú
  Inicio), porque un toque accidental no puede dejar la OPS sin icono;
- actualizar y desinstalar cierran solos la aplicación propia;
- cualquier aviso se cierra con un solo toque.

## Actualizar sobre una versión anterior

El `AppId` no cambia entre versiones, así que una versión nueva se reconoce como
actualización. El orden:

```text
1  Detectar la instalación previa y leer su versión
2  Detener el servicio y cerrar la aplicación propia
3  Apartar App\, Backend\ y Runtime\ a  <instalación>\Anterior\
4  Copiar lo nuevo sobre carpetas vacías
5  Copia de seguridad de los datos (base + -wal + -shm + backend.env)
6  Preparar: claves, revisión, migraciones
7  Volver a registrar el servicio y la regla de firewall
8  Arrancar y validar: /health/ y el canal en tiempo real
9  Bien → se borra Anterior\.  Fallo en 5–8 → se restauran datos y programa anteriores
```

Cada versión trae su runtime completo, y **nunca se mezcla** con el anterior:
Django carga todas las migraciones que encuentra en la carpeta, y una que la
versión nueva ya no trae rompería `migrate`. La instalación no ejecuta `pip` ni
descarga nada.

### Política de datos

Es un dato de cada versión (`manifiesto.json` → `politica_datos`, compilada con
`Build-Installer.ps1 -PoliticaDatos`):

| | `reemplazables` (hoy) | `protegidos` |
|---|---|---|
| Base | Se conserva si migra; si no migra se reemplaza, dejando antes la copia | Se conserva siempre |
| Copia previa | Sí | Obligatoria |
| Migración que falla | Base nueva y aviso | Se restaura la copia y se vuelve a la versión anterior |
| Botones Conservar / Empezar de cero | Sí | No |

Al llegar el módulo de progreso y calificaciones, pasar a `protegidos` es
cambiar ese valor al compilar.

### Claves de acceso

El backend espera `AVACOM_LMS_CLAVE_DATOS`, `_INDICE` y `_TOKENS` (32 bytes en
base64). El instalador las genera **una sola vez** en `backend.env`. Una
configuración de la 2.0.0 sólo tiene `AVACOM_LMS_SECRET` (de la que el backend
las deriva): se le agregan las claves únicamente si la base todavía no guarda
personas; si ya las guarda, se dejan como están y se avisa, porque cambiarlas
dejaría a esas personas sin poder descifrarse.

### Organización y primer administrador

Tras migrar, el nodo no tiene organización ni administrador y el login responde
`409 no_instalado`. Son datos de texto libre y el nodo no tiene teclado, así que
no se piden en el asistente: la pantalla final **avisa** si faltan, y crearlos
es una pantalla de primer arranque de OPS (tarea de la aplicación).

## La marca

Todo lo que se ve lleva el símbolo de AVACOM, y todo sale de un único archivo:
[`assets/avacom-symbol.svg`](../assets/avacom-symbol.svg).

| Dónde se ve | De dónde sale |
|---|---|
| Icono del instalador | `appicon.ico`, que MAUI genera de `Resources\AppIconppicon.svg` (placa blanca) + `appiconfg.svg` (el símbolo) |
| Icono del escritorio y del menú inicio | El mismo `appicon.ico` |
| Panel izquierdo de Bienvenido y de Instalación completada | `WizardImageFile` |
| Esquina superior derecha del resto de pantallas | `WizardSmallImageFile` |
| Pantalla de arranque de la aplicación | `Resources\Splash\splash.svg` |
| Tablero de AVACOM OPS Master | `Resources\Imagesvacom_mark.svg`, enlazado al asset |

Las dos imágenes del asistente las genera `New-ImagenesAsistente.ps1` en cada
compilación, a partir del símbolo que ya rasterizó la compilación de la
aplicación: así el asistente y el producto muestran la misma marca y no hay una
segunda copia que se desvíe.

Antes de esto, el icono era el cuadrado morado `#512BD4` de la plantilla de
.NET MAUI y el primer plano y el arranque eran el logotipo de .NET; el asistente
usaba además las ilustraciones genéricas de Inno Setup en cada pantalla. La
compilación ahora **falla** si el icono de la plantilla vuelve a aparecer.

## Verificar el instalador y el equipo (sin instalar)

`latest/AVACOM-Verificar-Instalador.bat` es un solo archivo, se toca y no
modifica nada. Revisa: (1) que el instalador está completo (SHA256 contra
`SHA256.txt`); (2) las diez comprobaciones del asistente, ejecutadas de verdad
con `/VOLCADO` (Windows pide permiso de administrador una vez); (3) el estado de
lo ya instalado: versión, servicio, puerto 8000, `/health/`, base, `backend.env`,
copias de seguridad, una carpeta `Anterior` que quedó de una actualización
cortada y las últimas líneas del registro. Termina con un veredicto y devuelve
`0` (se puede instalar) o `1` (hay problemas).

## Diagnosticar la comunicación con AVACOM Contenido

Cuando en el aula «no aparecen los cursos», la causa puede estar en cualquiera
de los cuatro eslabones de la cadena, y desde la pantalla del profesor los
cuatro se ven igual. `AVACOM-Probar-Comunicacion.bat` los separa.

Es **un solo archivo**: se descarga de la release y se toca. No necesita nada al
lado. Al terminar deja en el escritorio un informe y un `.zip` con las
evidencias, y los abre.

Un `.bat` y no un `.ps1` por dos razones, las dos del equipo del aula: Windows
no ejecuta un `.ps1` con un doble toque —lo abre en el Bloc de notas— y, al
descargarlo de la release, lo marca como venido de internet y la política
`RemoteSigned` (la de fábrica) lo rechaza con *«no está firmado digitalmente»*.
El `.bat` lleva el PowerShell dentro, detrás de un marcador, lo extrae a un
temporal y lo ejecuta con la política en Bypass, que ignora esa marca.

Lo genera [`build/New-ProbadorBat.ps1`](build/New-ProbadorBat.ps1) desde
[`tools/Probar-Comunicacion.ps1`](tools/Probar-Comunicacion.ps1), que es la
única fuente. El generador extrae lo que quedaría incrustado y lo pasa por el
analizador de PowerShell: si no parsea, no hay archivo. Sin esa comprobación un
`.bat` roto sólo se descubre al ejecutarlo en el aula.

**No modifica nada**: solo lee y consulta. Códigos de salida: `0` todo bien ·
`1` hay algo que bloquea · `2` sólo avisos.

### Qué lleva el paquete de evidencias

```text
AVACOM-diagnostico-<fecha>.zip
├── informe.txt                        el diagnóstico legible
├── respuestas/
│   ├── biblioteca-salud.json          /v1/salud de la Biblioteca
│   ├── biblioteca-cursos.json         SUS cursos, preguntados directamente
│   ├── biblioteca-catalogo.json       su contenido instalado
│   ├── biblioteca-enlace.json         la nota de enlace (sin la ficha)
│   ├── lms-health.json                /health/ del backend
│   └── lms-cursos.json                los cursos que ENTREGA el LMS
└── logs/                              los registros del servicio
```

Las dos listas de cursos, una al lado de la otra, son lo que permite decidir
quién pierde los cursos sin tener acceso al equipo. La ficha de la Biblioteca se
sustituye antes de escribir nada: es una credencial y no sale del nodo.

Lo que comprueba, en orden:

| # | Eslabón | Qué distingue |
|---|---|---|
| 1–2 | Instalación y configuración del nodo | Si `AVACOM_CONTENIDO_ENLACE` quedó apuntando a la nota del host de pruebas |
| 3–4 | Servicio y puerto | Servicio parado, inicio no automático, un `runserver` compitiendo, escucha sólo en loopback |
| 5 | La API local | Si contesta, y si quien contesta en ese puerto es de verdad el backend |
| 6 | La nota de enlace (`link.json`) | Nota ausente, incompleta (`apiPort`, `token`), de una sesión anterior, o ilegible por la cuenta del servicio |
| 7 | **Contacto directo con AVACOM Contenido** | Habla con su API v2 con el token de `link.json` (`X-Avacom-Token`), sin pasar por el backend |
| 8 | Lo que ve el backend | `/health/` (organización, claves) y el canal en tiempo real (WebSocket) |
| 9 | **Cursos: Contenido vs aula** | Compara los que ofrece AVACOM Contenido (`/v2/courses`) con los que entrega `/api/aula/cursos/` |
| 10 | **Errores de Python** | Clasifica los tracebacks y marca los que revientan una petición de Daphne |
| 11 | Interfaz y tabletas | Regla de firewall, IP del nodo, interfaz de desarrollo abierta por error |

El apartado 7 es el que gana el diagnóstico. Dos fallos que se ven idénticos
desde el aula tienen causas opuestas:

- el script **no** alcanza la Biblioteca → el problema es de la Biblioteca
  (pestaña «Contenido AVACOM» sin abrir, nota vieja, puerto muerto);
- el script **sí** la alcanza y el backend no → el problema es del backend
  (nota forzada por variable de entorno, permisos de la cuenta del servicio, o
  el servicio arrastrando un error y necesitando reinicio).

El apartado 9 responde la pregunta del aula comparando recuentos: si AVACOM
Contenido ofrece 0 cursos, el problema es suyo (no hay paquete de curso
instalado); si ofrece N y el aula entrega N, la cadena funciona y el fallo está
en la interfaz; si ofrece N y el aula entrega 0, los cursos se pierden dentro
del backend. Un `503` significa que el backend no alcanza a la biblioteca y un
`502` que ella falló por su cuenta.

### Errores de Python

Un error dentro de una petición es el más difícil de ver: revienta una petición
suelta, la interfaz muestra un cuelgue o un 500, y el servicio sigue apareciendo
«en marcha». El apartado 10 los busca en los registros, los agrupa por excepción
y marca con `Hilo ·` los de esa clase: SQLite usado desde otro hilo,
`database is locked` por concurrencia, `SynchronousOnlyOperation`,
`Exception inside application` de Daphne y bucles de eventos ausentes. De cada
grupo dice qué es y qué hacer.

Para analizar registros traídos de otro equipo, sin tocar ese equipo:

```powershell
.\Probar-Comunicacion.ps1 -CarpetaDeLogs C:\logs-del-nodo
```

## Convivencia con AVACOM Contenido

Los productos pueden estar en el mismo equipo. Nada se comparte salvo la carpeta
padre `%ProgramData%\AVACOM`, y ahí cada uno escribe solo lo suyo.

| | AVACOM OPS Master | AVACOM Contenido |
|---|---|---|
| Carpeta | `…\AVACOM\OPS Master` | `…\AVACOM\Contenido` |
| Datos | `%ProgramData%\AVACOM\OPS Master\Data` | `%ProgramData%\AVACOM\content` (la nota `link.json`) y los suyos |
| Servicio | `AVACOMOPSBackend` | — |
| Puerto | TCP 8000 (LAN del aula, HTTP y WebSocket) | loopback, puertos al azar |
| Regla de firewall | `AVACOM OPS Master Backend` | — |
| Menú inicio | `AVACOM OPS Master` | grupo propio |
| Desinstalación | Entrada propia | Entrada propia |

De la biblioteca solo se **lee** `%ProgramData%\AVACOM\content\link.json` (puertos
y token), y lo hace el backend en tiempo de ejecución, no el instalador.
`AVACOM_CONTENIDO_ENLACE` se deja sin definir para que el backend busque la nota
donde la biblioteca la publica. Sin biblioteca el producto instala y arranca,
pero el aula no tendrá cursos.

## Desinstalar

Desde «Aplicaciones instaladas» de Windows y desde el menú Inicio. Detiene el
servicio, lo quita del SCM, retira la regla de firewall y borra los archivos del
programa y los accesos directos. Después pregunta si eliminar también los datos
de este equipo; la respuesta por defecto es **conservarlos**, y vale para la
base y para `backend.env` juntos. No borra `%ProgramData%\AVACOM` ni nada de
AVACOM Contenido. Reinstalar después, conservando los datos, deja el aula como
estaba, con las personas todavía descifrables.

## Publicar el instalador

`installer/latest` es lo que se sube como release. El `.exe` ronda los 100 MB,
en el límite por archivo de un push a GitHub, así que no se versiona: se publica
como *release asset*, que es donde GitHub espera un binario. Lo demás de la
carpeta (`SHA256.txt`, `LEEME.txt` y `AVACOM-Verificar-Instalador.bat`) sí se
versiona y se adjunta:

```bash
gh release create v2.1.0 installer/latest/AVACOM-OPS-Master-Setup-2.1.0.exe installer/latest/SHA256.txt installer/latest/AVACOM-Verificar-Instalador.bat installer/tools/AVACOM-Probar-Comunicacion.bat --title "AVACOM OPS Master 2.1.0" --notes-file installer/latest/LEEME.txt
```

Los dos `.bat` se adjuntan para poder revisar un nodo sin clonar el repositorio
en él: se descargan y se tocan. Para verificar el `.exe` descargado:

```powershell
Get-FileHash .\AVACOM-OPS-Master-Setup-2.1.0.exe -Algorithm SHA256
```

## Pendiente

- **El instalador de AVACOM Student** (Windows y Android) no está construido:
  tendrá su propio `AppId`, carpeta, versión y desinstalador, sin servicio ni
  firewall, y leerá `version.json`.
- La pantalla de primer arranque de OPS que cree la organización y el primer
  administrador es una tarea de la aplicación.
- Firma de código: sin ella, SmartScreen advertirá de un editor desconocido.
- Firewall en red pública y OPS abriéndose sola al iniciar sesión: decisiones sin
  cerrar (ver `spec-driven/08-instalador.md`, artículo 11).
