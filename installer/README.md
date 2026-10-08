# Instalador de AVACOM OPS Master

Produce un único `.exe` que instala en un equipo Windows la aplicación del
profesor y la API local del aula, sin pedirle al usuario que escriba nada.

```text
installer/
├── build/
│   ├── Build-Installer.ps1     Un comando: del código fuente al .exe (y demuestra que es el actual)
│   ├── Get-PythonRuntime.ps1   Ensambla el Python embebido con Django/DRF/Channels/Daphne
│   ├── Distribucion.props      Propiedades de publicación (no toca ningún .csproj)
│   ├── New-ImagenesAsistente.ps1  Imágenes de marca de las pantallas del asistente
│   ├── New-VerificadorBat.ps1  Empaqueta el verificador en AVACOM-Verificar-Instalador.bat
│   ├── New-ProbadorBat.ps1     Empaqueta el diagnóstico de Contenido en un .bat autocontenido
│   ├── Verificar-Asistente.ps1 Ejecuta las comprobaciones del asistente de verdad
│   ├── Ensayar-Paquete.ps1     Levanta el paquete como lo haría el aula, sin tocar este equipo
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
│   ├── Verificar-Instalador.ps1        El verificador (código fuente del .bat de latest)
│   ├── AVACOM-Probar-Comunicacion.bat  Diagnóstico de Contenido en UN archivo (se distribuye)
│   └── Probar-Comunicacion.ps1         Su código fuente
└── latest/                                 Lo que se sube como release (todo junto)
    ├── AVACOM-OPS-Master-Setup-<versión>.exe
    ├── SHA256.txt                          Huella del .exe y del código que lleva (versión, revisión, árbol)
    ├── LEEME.txt
    ├── AVACOM-Verificar-Instalador.bat     Revisa el equipo, el instalador y lo instalado; busca el error exacto
    └── AVACOM-Probar-Comunicacion.bat      Copia del de tools\: diagnóstico de la comunicación con Contenido
```

## Construirlo

```powershell
powershell -ExecutionPolicy Bypass -File installer\build\Build-Installer.ps1
```

Requiere, **solo en el equipo de compilación**: .NET SDK 10, Python 3.12 e
Inno Setup 6 (`winget install JRSoftware.InnoSetup`), y acceso a internet la
primera vez, para descargar el runtime de Python que después viaja dentro del
paquete.

El script toma la **huella del código** que va a empaquetar, pasa las pruebas
del backend, publica la app, ensambla el runtime, copia el backend, escribe el
manifiesto, **verifica el asistente**, **ensaya el paquete** (ver abajo) y lo
compila. Si algo falla, se detiene: no produce un instalador a medias.

**Cómo demuestra que el instalador es el de la versión actual.** Una vez se
empaquetó una publicación de la app de hacía semanas, y es el tipo de error que
no se ve hasta el aula. Ahora:

- La huella (SHA-256 de cada archivo) de `backend/`, de la app (`src/Avacom.Lms.Ops`,
  `Core`, `Ui` y `assets/`) y del asistente se toma **al empezar** y se vuelve a
  tomar **al terminar**; si no coinciden, el código cambió mientras se compilaba
  y el `.exe` se descarta.
- El backend empaquetado se compara archivo por archivo con el del repositorio
  (menos lo que se excluye a propósito: `.venv`, `__pycache__`, la base de
  desarrollo y **`backend/logs`**, los registros del desarrollador) y todas las
  apps de `INSTALLED_APPS` tienen que haber llegado con sus migraciones.
- `-OmitirApp` reutiliza la publicación de la app **solo si su huella es la del
  código actual** (queda en `dist\staging\huella-app.txt`); si no, aborta.
- La app publicada tiene que ser más nueva que el último archivo de código.
- El `.exe` producido tiene que declarar la versión de `installer\version.json`.
- Un árbol de trabajo con cambios sin confirmar se **avisa** (no se impide) y
  queda escrito en `manifiesto.json` y `SHA256.txt`: el instalador no puede
  hacerse pasar por una revisión de git que no es del todo.
- Una compilación interrumpida no deja nada: se borran los `.exe` y `.tmp` de
  `installer\latest` antes de compilar y se comprueba que no quede ningún `.tmp`.

`-OmitirPruebas`, `-OmitirApp` y `-OmitirEnsayo` existen solo para iterar.
`-VersionAnterior <carpeta con Backend\ y Runtime\ de la versión anterior>` añade
al ensayo la **actualización sobre datos reales** de esa versión.

## Comprobar un equipo sin instalar nada

El propio instalador sabe diagnosticar sin tocar el equipo. Con `/VOLCADO`
ejecuta sus diez comprobaciones, las escribe en un archivo y aborta:

```powershell
.\AVACOM-OPS-Master-Setup-2.3.0.exe /VERYSILENT /VOLCADO=C:\temp\diagnostico.txt
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
│   └── Avacom.Lms.Ops.exe.WebView2\   perfil de WebView2 escribible por los usuarios (red de seguridad)
├── Backend\    Django + Django REST Framework, tal cual está en backend\
├── Runtime\    Python 3.12 embebido + Django + DRF + Channels + Daphne
│               + Avacom.Ops.Host.exe (servicio, lanzador, preparación)
├── manifiesto.json   versión, revisión, huellas del código, módulos, política de datos, paquetes
└── LEEME.txt
```

Y fuera de la carpeta del programa, porque cambia con el uso:

```text
%ProgramData%\AVACOM\OPS Master\Config      backend.env (claves de este nodo)
%ProgramData%\AVACOM\OPS Master\Data        ops-master.sqlite3 (+ -wal y -shm): la base del nodo
%ProgramData%\AVACOM\OPS Master\Respaldos   copias previas a cada actualización (las últimas 5)
%ProgramData%\AVACOM\OPS Master\Logs        registros del nodo (ver «Registros»)
%ProgramData%\AVACOM\OPS Master\CacheMedios  caché de medios (ver «Caché de medios»)
%LOCALAPPDATA%\AVACOM\OPS Master\WebView2   perfil de WebView2 de cada usuario (lo crea el icono)
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

Esa misma parada ocurre sola si **el host muere de golpe** (se cierra a la
fuerza, falla, lo mata el sistema): el backend ve cerrarse su entrada y se detiene
sin dejar el puerto ocupado. En la 2.1 esto fallaba: con el host muerto la salida
estaba rota, el primer `print` del hilo vigilante lanzaba una excepción y nunca se
pedía la parada, así que el backend quedaba huérfano. Ahora nada de lo que
escribe puede impedirla, y si tras cerrar el expediente el intérprete no termina,
sale a los 10 s (`Ensayar-Paquete.ps1` lo comprueba matando el host).

### El backend solo obedece a `backend.env`

El nodo se configura **únicamente** con `%ProgramData%\AVACOM\OPS Master\Config\backend.env`:

- Toda variable `AVACOM_*` que traiga Windows —del usuario o del equipo— se
  **descarta** antes de lanzar Python. Una base de pruebas, el curso de ejemplo
  encendido o una nota de enlace de pruebas, olvidados por un técnico o un
  desarrollador, no cambian lo que hace el aula (el ensayo del paquete los
  envenena a propósito y comprueba que no cuentan).
- Al instalar y al actualizar, `preparar` lleva ese archivo a lo que el producto
  exige, **sin tocar las claves de acceso**: agrega lo que falta (entorno
  `instalado`, carpeta de registros, fuente de cursos), corrige sólo lo que no
  admite otro valor (la base que miran las copias, la fuente de cursos siempre
  `biblioteca`, el curso de ejemplo apagado, la escucha en `0.0.0.0:8000`) y
  retira —dejándola comentada— cualquier `AVACOM_CONTENIDO_ENLACE`.
- Después revisa lo que Django ve **de verdad** (`Configuracion efectiva` en
  `instalacion.log`) y se niega a continuar si apunta a otra base de datos o con
  el ejemplo encendido.
- Si `backend.env` falta o no se puede leer, el servicio **no arranca el backend**
  (y lo escribe en `servicio.log`): arrancaría con valores de desarrollo y una base
  de datos nueva dentro de Program Files, y el aula «funcionaría» sobre un
  expediente vacío sin que nadie lo notara.

### Verbos de `Avacom.Ops.Host.exe`

| Verbo | Quién lo usa | Qué hace |
|---|---|---|
| `servicio` | El SCM de Windows | Punto de entrada del servicio |
| `iniciar` | El icono del escritorio | Backend → validación → interfaz |
| `respaldar <versión>` | El instalador | Copia base + `-wal` + `-shm` + `backend.env` a `Respaldos\` |
| `vaciar-datos`, `restaurar-datos` | El instalador | «Empezar de cero» / volver a la copia |
| `preparar` | El instalador | Configuración (crea o normaliza `backend.env`), claves, comprobación del runtime, configuración efectiva, migraciones (según la política de datos) |
| `validar [seg]` | El instalador | `/health/` responde, el WebSocket acepta conexiones, el módulo de acceso lee su base y el backend escribe sus registros; escribe `Logs\resumen-nodo.txt` (incluye el estado de AVACOM Contenido) |
| `salud [seg]` | Diagnóstico | Espera a que `/health/` responda |
| `puerto-libre` | Diagnóstico | 0 libre · 12 nuestro backend · 13 ajeno |
| `instalar-servicio`, `quitar-servicio` | El instalador | Registro en el SCM |
| `iniciar-servicio`, `detener-servicio` | El instalador | Control del servicio |
| `abrir-firewall`, `cerrar-firewall` | El instalador | Regla TCP 8000 |

Ninguno pide interacción. El único que muestra algo es `iniciar`, y solo si el
backend no responde.

## Permisos

Quién escribe dónde, y por qué. El servicio corre como `SYSTEM`; la aplicación,
como **quien da la clase** (el instalador la abre con `runasoriginaluser`: sin
eso heredaría el token de administrador y todo lo que escribiera quedaría a nombre
del administrador).

| Carpeta | `SYSTEM` y administradores | Usuarios (quien da la clase) | Quién escribe |
|---|---|---|---|
| `App\`, `Backend\`, `Runtime\` (Program Files) | control total | **solo lectura** | nadie en uso; solo el instalador |
| `App\Avacom.Lms.Ops.exe.WebView2\` | control total | **modificar** | WebView2, solo si la aplicación se abre sin el icono |
| `%ProgramData%\AVACOM\OPS Master\Config`, `Data`, `Respaldos` | **control total, explícito** | lo que hereden (leer) | el servicio y el instalador |
| `…\Logs` y `Logs\auditoria` | **control total, explícito** | modificar | el servicio (registros y bitácora), el lanzador |
| `…\CacheMedios` | **control total, explícito** | **nada** (se les quitan los permisos heredados) | el servicio |
| `%LOCALAPPDATA%\AVACOM\OPS Master\WebView2` | — | su propio perfil | WebView2, vía el icono |
| `%LOCALAPPDATA%\AVACOM\lms` | — | su propio perfil | la aplicación (`fallos-ops.log` y `logs\ops-*.log`) |

Control total para `SYSTEM` y administradores va **explícito** en cada carpeta
de estado, en lugar de fiarse de lo que herede de ProgramData: si una carpeta ya
existía con una lista de permisos rara (un intento anterior, una copia de otro
equipo), sin eso el servicio no podría escribir y el nodo funcionaría sin guardar
nada. El servicio, además, puede arrancarlo y detenerlo quien da la clase sin
credenciales (`sc sdset`, solo sobre este servicio).

**Por qué la aplicación se cerraba al abrir una lección.** Las lecciones con
audio, video, PDF o laboratorio usan **WebView2** (el motor de Microsoft Edge).
WebView2 guarda su perfil —caché, cookies, almacenamiento— por defecto *junto al
ejecutable*, `App\Avacom.Lms.Ops.exe.WebView2`, y la aplicación está en Program
Files, donde quien da la clase no puede escribir. Al crear la primera WebView el
perfil no se puede crear y el proceso se cierra sin avisar. En el equipo de
desarrollo no se ve: corre desde `bin\Debug`, que sí es escribible. Se resuelve
en dos capas, ninguna toca el código del producto:

1. **El icono** (`Avacom.Ops.Host.exe iniciar`) abre la aplicación con
   `WEBVIEW2_USER_DATA_FOLDER` apuntando a `%LOCALAPPDATA%\AVACOM\OPS Master\WebView2`,
   dentro del perfil de Windows de quien da la clase. Antes comprueba que se puede
   escribir (crea y borra un archivo); si no, prueba su carpeta temporal; y si
   tampoco, abre la aplicación igual con la carpeta por defecto —un fallo aquí no
   puede impedir abrirla—. Respeta la variable si el entorno ya la trae (soporte,
   depuración).
2. **Red de seguridad:** el instalador crea `App\Avacom.Lms.Ops.exe.WebView2` con
   permiso de modificar para los usuarios, y solo esa carpeta. Cubre abrir
   `Avacom.Lms.Ops.exe` directamente. El resto de `App\` sigue siendo de solo
   lectura: nadie puede reemplazar binarios.

Un cambio de 3 líneas en el arranque de OPS y de Student (poner esa misma
variable si falta) lo resolvería también dentro del producto y cubriría Student
en Windows; es un cambio de código y queda **pendiente de que se pida**.

## Registros

Todo lo del nodo queda en `%ProgramData%\AVACOM\OPS Master\Logs`, fuera de la
carpeta del programa (que se borra al actualizar) y con la marca de no
desinstalar:

| Archivo | Lo escribe | Contenido |
|---|---|---|
| `backend-app.log` | el backend | una línea JSON por petición (`ruta` happy/sad/bad), con `corr` para seguirla |
| `backend-errores.log` | el backend | solo WARNING o más, con la traza |
| `backend-auditoria.log` | el backend | un renglón por asiento de la bitácora |
| `backend-clientes.log` | el backend | lo que suben OPS y Student |
| `auditoria\` | el backend | tramos rotados y exportaciones de la bitácora (copias firmadas: las filas nunca se borran) |
| `servicio.log` | el host | arranques, reinicios del backend y **toda la salida de Python** (donde cae un error de importación) |
| `instalacion.log` | el host **y** el backend | pasos de la instalación, configuración efectiva, validación (texto) y arranque, migraciones y siembra del backend (JSON) |
| `lanzador.log` | el host | qué hizo el icono: perfil de WebView2, pid de la aplicación |
| `instalador-ultimo.log`, `instalador-anterior.log` | el asistente | la bitácora de Inno Setup, copiada desde `%TEMP%` de quien instaló |
| `resumen-nodo.txt`, `preparacion-*.txt`, `respaldo-ultimo.txt` | el host | lo que la pantalla final lee |

Rotación: 2 MB × 5 archivos, el mismo criterio en el host y en el backend. Los
dos escriben el mismo `instalacion.log`, así que el host lo abre **compartiendo
lectura y escritura** y reintenta unos instantes: ninguna línea se pierde porque
el backend lo tenga abierto. Un fallo de permisos al registrar nunca tumba nada.

**Que el nodo pueda guardar registros y auditoría es parte de la instalación,
no un deseo**: `validar` comprueba, con el servicio ya en marcha, que
`backend-app.log` tiene un renglón de los últimos minutos. Si no (el servicio no
puede escribir en `Logs` y el backend se ha desviado a su carpeta temporal), la
pantalla final lo dice. Y `preparar` comprueba antes que Django esté usando la
carpeta del nodo y no otra.

Los registros de **la aplicación** (OPS y Student) viven en el perfil de cada
usuario, `%LOCALAPPDATA%\AVACOM\lms`: `fallos-ops.log` (cada excepción no
controlada, justo antes de cerrarse) y `logs\ops-app.log` / `ops-errores.log`
(JSON Lines; los avisos y errores se suben al nodo cada minuto). Ahí está el error
exacto cuando OPS se cierra, y es lo primero que busca el verificador.

## AVACOM Contenido: lo que puede fallar y lo que no

La comunicación con la biblioteca es **de ida y por loopback**: el backend lee
`%ProgramData%\AVACOM\content\link.json` (puertos y token) **en cada petición** y
habla con su API v2. El instalador nunca la toca, no depende de ella, y ninguna
falla suya puede romper la instalación ni dejar el nodo inservible:

| Situación | Qué pasa |
|---|---|
| AVACOM Contenido no está instalado | Se instala y arranca igual. La comprobación 9 del asistente es informativa; el aula no tiene cursos |
| Está instalado pero cerrado, o `link.json` es de una sesión anterior | Igual. `/api/aula/fuente/` nunca falla (dice `disponible: false` y por qué); al abrir la biblioteca el aula recupera los cursos **sin reiniciar nada** |
| Se está reconstruyendo su índice | Igual: «vuelve a intentarlo en unos segundos» |
| La instalación es una actualización y `backend.env` traía una nota de enlace de pruebas | Se retira, y se avisa en la pantalla final: dejaba al aula sin cursos aunque la biblioteca estuviera abierta |
| El curso de ejemplo estaba encendido | Se apaga: los cursos salen **siempre** de AVACOM Contenido |
| Una variable `AVACOM_CONTENIDO_*` o `AVACOM_AULA_*` en Windows | Se ignora (el backend solo lee `backend.env`) |

La pantalla final dice cómo ve el aula a AVACOM Contenido (*conectado, N cursos*
o *no está abierto ahora*), preguntándoselo al propio backend (`/api/aula/fuente/`);
`/health/` ya no se usa para eso porque su campo `biblioteca` habla del contrato
anterior de la biblioteca. Si Contenido contesta y el aula no, el problema está en
el backend (configuración, permiso para leer `link.json`): lo dice el verificador.

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
| 8 | Instalación completada | Las direcciones para las tabletas en letra grande, aviso si falta la organización, cómo ve el aula a AVACOM Contenido, aviso si el servicio no guarda sus registros, lo que se corrigió de la configuración, casilla para abrir el producto |

### Pantalla 4 · qué se comprueba

Windows 10 **versión 1809 (compilación 17763)** o 11 —el Windows App SDK
autocontenido de la aplicación no corre en una más antigua— · arquitectura de 64
bits · espacio en disco · permisos de administrador · **puerto 8000** ·
instalación previa · aplicación abierta (no bloquea: el asistente la cierra) ·
dependencias del backend y runtime de WebView2 (avisa si falta) · AVACOM
Contenido (`link.json`) · red del aula (avisa si Windows la marca como pública).

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
- cualquier aviso se cierra con un solo toque;
- los textos dicen «Toca», no «Haga clic» (`ClickNext` y `ReadyLabel2a` están
  sobreescritos en `[Messages]`).

### Las pantallas se comprobaron viéndolas

Un compilador y las pruebas de lógica no ven que un botón tape a otro. Por eso las
pantallas del asistente se condujeron de verdad —con una **copia de pruebas** del
asistente (sin administrador, con un host de mentira que devuelve 0, sin accesos
directos ni entrada de desinstalación y con otro nombre de aplicación, para no
cerrar la OPS de quien desarrolla), mensajes de Windows para tocar los botones y
`PrintWindow` para capturar— en cinco escenarios (todo bien, el peor caso de avisos,
datos ya existentes, falla `validar`, falla `preparar`). Salieron seis defectos, que
ya estaban en la 2.1:

| Defecto | Arreglo (en `codigo.iss`) |
|---|---|
| Atrás, Siguiente y Cancelar se montaban uno sobre otro | `DistribuirBotonesDeNavegacion`: desde el borde derecho, mismo tamaño, con hueco |
| «Examinar…» quedaba debajo de la caja de la ruta | `AjustarExaminar`: junto a la caja, que cede el espacio |
| «Volver a comprobar» se cortaba por el pie | Anclado al pie de su página; el resumen toma lo que sobra |
| Las opciones de «Datos del aula» salían de ≈ 24 px, no de 64 | El alto mínimo se fija **antes** de agregarlas |
| La pantalla final **cortaba el texto** (la dirección para las tabletas no se veía) | `DisponerPantallaFinal`: tres bloques medidos por separado, direcciones en letra grande, la casilla baja, y si no cabe se baja la letra o se resume el aviso |
| `informacion.txt` empezaba en inglés | En español |

Esas capturas son un **ensayo de las pantallas**, no una instalación: no prueban
permisos de administrador, la reversión de una actualización ni la desinstalación.

## Actualizar sobre una versión anterior

El `AppId` no cambia entre versiones, así que una versión nueva se reconoce como
actualización. El orden:

```text
1  Detectar la instalación previa y leer su versión
2  Detener el servicio y cerrar la aplicación propia
3  Apartar App\, Backend\ y Runtime\ a  <instalación>\Anterior\
4  Copiar lo nuevo sobre carpetas vacías
5  Copia de seguridad de los datos (base + -wal + -shm + backend.env)
6  Preparar: configuración (se normaliza), claves, revisión, configuración efectiva,
   migraciones
7  Volver a registrar el servicio y la regla de firewall
8  Arrancar y validar: /health/, canal en tiempo real, base de datos y registros
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

Tras migrar, el nodo no tiene organización, administrador ni PIN maestro y el
login responde `409 no_instalado`. Son datos de texto libre y el nodo no tiene
teclado, así que no se piden en el asistente: la pantalla final **avisa** si
faltan (y, ya instalado, muestra el estado del PIN maestro: `configurado`,
`vencido` o `sin_configurar`, sin fechas), y crearlos es la pantalla de primer
arranque de OPS (aula, administrador y PIN maestro de seis dígitos; sin PIN no se
instala). Por consola: `manage.py acceso_instalar ...` con el PIN en la variable
`AVACOM_LMS_PIN_MAESTRO` o por la entrada estándar (`--pin-maestro-stdin`), nunca
como argumento. El técnico puede reemplazar el PIN maestro con
`manage.py acceso_pin_maestro --cambiar` y recuperar al administrador con
`manage.py acceso_restablecer_admin --dni <documento>`.

**Sesión obligatoria.** El instalador deja `AVACOM_LMS_EXIGIR_SESION=1` en
`backend.env` (cierra Q-34): expediente, biblioteca, aula, estudio y evaluación
exigen pase. El personal entra con documento y contraseña (la administración,
además, con el PIN maestro), el alumno toca su nombre y marca su PIN, y el
visitante entra con permisos mínimos. Una instalación que ya traía el valor lo
conserva; si falta, se agrega en 1.

## La marca

Todo lo que se ve lleva el símbolo de AVACOM, y todo sale de un único archivo:
[`assets/avacom-symbol.svg`](../assets/avacom-symbol.svg).

| Dónde se ve | De dónde sale |
|---|---|
| Icono del instalador | `appicon.ico`, que MAUI genera de `Resources\AppIcon\appicon.svg` (placa blanca) + `appiconfg.svg` (el símbolo) |
| Icono del escritorio y del menú inicio | El mismo `appicon.ico` |
| Panel izquierdo de Bienvenido y de Instalación completada | `WizardImageFile` |
| Esquina superior derecha del resto de pantallas | `WizardSmallImageFile` |
| Pantalla de arranque de la aplicación | `Resources\Splash\splash.svg` |
| Tablero de AVACOM OPS Master | `Resources\Images\avacom_mark.svg`, enlazado al asset |

Las dos imágenes del asistente las genera `New-ImagenesAsistente.ps1` en cada
compilación, a partir del símbolo que ya rasterizó la compilación de la
aplicación: así el asistente y el producto muestran la misma marca y no hay una
segunda copia que se desvíe.

Antes de esto, el icono era el cuadrado morado `#512BD4` de la plantilla de
.NET MAUI y el primer plano y el arranque eran el logotipo de .NET; el asistente
usaba además las ilustraciones genéricas de Inno Setup en cada pantalla. La
compilación ahora **falla** si el icono de la plantilla vuelve a aparecer.

## Verificar el instalador y el equipo (sin instalar)

`latest/AVACOM-Verificar-Instalador.bat` es **un solo archivo**: se toca y no
cambia la configuración, los datos ni el servicio (para probar los permisos
crea y borra al instante un archivo temporal). Sirve **antes** de instalar y
**después**, cuando algo falla en el aula —por ejemplo, la aplicación se cierra
al abrir una lección—. Lo genera `build\New-VerificadorBat.ps1` desde
[`tools/Verificar-Instalador.ps1`](tools/Verificar-Instalador.ps1), que es la
única fuente (misma técnica que el diagnóstico de Contenido: el PowerShell va
dentro del `.bat`, detrás de un marcador, y se ejecuta con la directiva en
Bypass; el generador lo pasa por el analizador de PowerShell y por una prueba de
extracción antes de dar el archivo por bueno).

| # | Revisa |
|---|---|
| 1 · El instalador | Huella SHA256 contra `SHA256.txt` (y que ese archivo sea de **este** instalador), versión que declara el `.exe`, si Windows lo marcó como descargado (SmartScreen) |
| 2 · El equipo | Las diez comprobaciones del asistente, ejecutadas de verdad con `/VOLCADO` (Windows pide permiso de administrador **una** vez). Sin instalador junto al `.bat`, se omite |
| 3 · Lo instalado | Versión y manifiesto, piezas del programa, servicio (inicio automático, cuenta, que los usuarios puedan arrancarlo), quién escucha en el 8000, `/health/` (con el error del módulo de acceso si no puede usar su base), WebSocket, módulo de auditoría, `backend.env` **sin mostrar secretos** (depuración, ejemplo, notas de enlace de pruebas, claves), base y copias, firewall, red pública, direcciones para las tabletas |
| 4 · Permisos | Control total de `SYSTEM` y administradores en `Config`, `Data`, `Respaldos` y `Logs`; escritura **real** (crea y borra un archivo) de quien lo ejecuta en `Logs` y en el perfil de WebView2 junto a la aplicación; que `App\` sea de solo lectura; que el icono ya haya creado el perfil de WebView2; versión del runtime de WebView2 |
| 5 · Registros | Archivos de `Logs`, que el backend esté escribiendo, errores del backend agrupados (`backend-errores.log`), reinicios y negativas a arrancar del servicio (`servicio.log`) |
| 6 · La aplicación | Si OPS está abierta; los **cierres inesperados que Windows registró** (Visor de eventos: ids 1000, 1002, 1026, filtrados por proveedor e id, no por el texto, que sale en el idioma de Windows) **unidos a la excepción exacta que la aplicación anotó** en `fallos-ops.log` de **cada usuario de Windows**; `ops-errores.log`; y la causa probable si apunta a WebView2 |
| 7 · AVACOM Contenido | `link.json` (el token no se muestra), si su proceso vive, si contesta directamente, qué ve el aula de ella (`/api/aula/fuente/`) y si SYSTEM puede leer `link.json`. Si Contenido contesta y el aula no, lo dice: el problema está en el backend |

**Por qué hace falta el cruce de la sección 6.** Un cierre por una excepción no
controlada de la interfaz queda en el Visor como `0xc000027b` en
`Microsoft.UI.Xaml.dll`, **la misma firma para cualquier causa**: el Visor nunca
dice cuál fue. La causa exacta la anota la propia aplicación en
`%LOCALAPPDATA%\AVACOM\lms\fallos-ops.log` un instante antes de morir, en el
perfil de quien la ejecutó. El verificador empareja cada cierre con lo que se
anotó en los segundos anteriores y lo muestra debajo.

Termina con un veredicto —*todo en orden*, *avisos* o *problemas*, cada uno con
«qué hacer»— y deja en el **escritorio** un informe y un `.zip` con las
evidencias, **sin claves ni tokens** (`backend.env` y `link.json` salen con los
valores secretos ocultos), para poder diagnosticar sin tocar el equipo. Los
permisos se prueban con la cuenta de quien lo ejecuta: **no hay que ejecutarlo
como administrador** (solo si hace falta leer el perfil de *otro* usuario de
Windows, y entonces las pruebas de escritura dejan de representar a quien da la
clase; lo dice).

Códigos de salida: `0` todo en orden · `1` hay algo que bloquea · `2` solo
avisos. Con `/silencioso` no abre el informe ni espera un toque al final.

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

Lee los dos formatos: el **texto** de `servicio.log` (lo que Python escribió en
pantalla) y el **JSON Lines** del backend (`backend-errores.log`, desde MOD-019:
la traza va dentro del campo `traza`). El mismo error, que aparece en los dos, se
cuenta una vez.

Para saber por qué se cierra **la aplicación** (no el backend), el diagnóstico
es otro: `AVACOM-Verificar-Instalador.bat` (sección 6).

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

## Caché de medios

Desde la 2.5.0 el nodo no reenvía cada medio de AVACOM Contenido tableta por tableta: trae cada video, audio, imagen, PDF o página html **una vez** a
`%ProgramData%\AVACOM\OPS Master\CacheMedios`, con su SHA-256, y desde ahí lo reparte a las tabletas con `Range`, con un límite de transferencias a la vez
y, si se quiere, de ancho de banda. El diseño completo está en `spec-driven/11-cola-de-medios.md`.

- **Es regenerable**: se puede borrar la carpeta con el servicio detenido (o con «Vaciar la caché» en la pestaña **Medios** de la bitácora de OPS) y se vuelve a
  llenar sola. Por eso **no entra en las copias de seguridad** y **se borra al desinstalar** (puede ocupar varios GB).
- **Sólo la leen `SYSTEM` y los administradores**: son medios de examen y no deben quedar a la mano de cualquier usuario del equipo. El host le quita los permisos
  heredados de ProgramData al preparar el nodo (si no puede, por ejemplo en un ensayo sin privilegios, queda con los que tenga y lo intenta de nuevo la próxima vez).
- **Se ajusta en `backend.env`** (`AVACOM_COLA_*`, reinicia el servicio `AVACOMOPSBackend`): `AVACOM_COLA_ACTIVA` (0 = cada tableta pide directo a AVACOM
  Contenido, como antes), `AVACOM_COLA_MAX_MB` (4096), `AVACOM_COLA_LIBRE_MIN_MB` (1024), `AVACOM_COLA_DESCARGAS` (3), `AVACOM_COLA_TRANSFERENCIAS` (24),
  `AVACOM_COLA_ANCHO_ENTRADA_KBPS` y `AVACOM_COLA_ANCHO_SALIDA_KBPS` (0 = sin tope). Ninguna se fuerza: una actualización agrega las que falten y respeta las que el
  técnico haya cambiado.
- **El ensayo del paquete** (`Ensayar-Paquete.ps1`) comprueba que las claves están, que la caché es la del nodo y no la de un entorno ajeno, y que `/api/medios/cola/` responde.
- **El verificador** (`Verificar-Instalador.ps1`) avisa si la cola está apagada y cuánto ocupa la caché.

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
gh release create v2.3.0 installer/latest/AVACOM-OPS-Master-Setup-2.3.0.exe installer/latest/SHA256.txt installer/latest/AVACOM-Verificar-Instalador.bat installer/latest/AVACOM-Probar-Comunicacion.bat --title "AVACOM OPS Master 2.3.0" --notes-file installer/latest/LEEME.txt
```

Los dos `.bat` se adjuntan para poder revisar un nodo sin clonar el repositorio
en él: se descargan y se tocan. Para verificar el `.exe` descargado:

```powershell
Get-FileHash .\AVACOM-OPS-Master-Setup-2.3.0.exe -Algorithm SHA256
```

**Versión 2.3.0.** La 2.2.0 se compiló el 2026-10-01, antes del acceso con PIN
maestro (`/api/acceso/pin-maestro/`, `docentes/registro/`, `estudiantes/registro/`,
`sesiones/visitante/`, el traspaso entre apps y las migraciones `acceso` 0010 y
0011); el contrato de red entre Student y el backend cambió, y `version.json` dice
que la versión sube cuando eso ocurre. Una OPS con la 2.2.0 y una Student nueva (o
al revés) no son compatibles. La misma versión sale en los tres entregables: este
instalador, `student-windows/` y el APK de `student-android/`.

**Versión 2.4.0.** Trae el arreglo de los medios del aula (bugfix 01: los videos, audios e
imágenes llegan con un *pase de medios* dentro de la dirección, `/api/m/<pase>/…`, que el
visor abre sin cabeceras aunque la sesión sea obligatoria; antes respondían 401 y se veía
«formato no compatible») y el contrato 2 de AVACOM Contenido (láminas html, pausas y portada
de video, arrastrar y soltar). Una Student 2.3.x sigue entrando al aula, pero no reproduce
medios con la sesión obligatoria ni ve las lecciones html: hay que actualizar también las
tabletas. Además, el ensayo del paquete ahora recorre el **primer arranque completo** (ver
abajo) y la actualización de una base que ya tiene PIN maestro.

## La primera instalación: qué pide el instalador y qué pide OPS

El instalador **no pide ningún dato**: deja la API lista, con
`AVACOM_LMS_EXIGIR_SESION=1`, claves propias y la base sin organización. Todo lo
demás se pide en el **primer arranque de AVACOM OPS Master**, que se abre solo
cuando el nodo contesta `instalado = false`:

1. País e idioma. 2. Nombre del aula. 3. El administrador: documento, nombres y
apellidos (**la contraseña no se escribe**: la genera el nodo y sale una sola vez
en la hoja de acceso). 4. El **PIN maestro** (seis dígitos, dos veces, con teclado
propio; se rechazan los fáciles como `123456`). 5. La hoja de acceso.

Después el administrador entra con **documento, contraseña provisional y PIN
maestro**, y elige su contraseña. Los grupos y los alumnos los crea el
profesorado en OPS (Grupos), o los alumnos se crean solos (siempre dentro de un
**grupo**: sin ninguno no pueden); los profesores se registran con el PIN maestro.
Cada tableta se registra sola al conectarse. La pantalla final del instalador
avisa si falta el primer arranque y, en una actualización de un nodo sin PIN
maestro, que se configura en OPS → Seguridad del aula. El ensayo del paquete
comprueba el nodo nuevo (sin organización, sesión obligatoria, sin PIN maestro) y
el actualizado desde la 2.2.0.

**Lo que demuestra el ensayo del paquete (`Ensayar-Paquete.ps1`, bloque A2).** Con el backend
EMPAQUETADO en un puerto libre, el nodo recién instalado: rechaza un PIN maestro fácil (`123456`)
y uno corto, y sigue vacío; acepta el primer arranque real (organización, administrador con
documento, nombres y apellidos, y PIN maestro) con un 201, devuelve la contraseña inicial
generada —y no el PIN—, pasa a `instalado` con PIN vigente, rechaza un segundo primer arranque
(409), registra al equipo de OPS como MASTER y deja entrar al administrador solo con
documento + contraseña inicial + PIN maestro (sin PIN: `pin_maestro_requerido`; PIN equivocado:
`pin_maestro_invalido`), con la contraseña marcada como provisional, el aula respondiendo 200
con esa sesión y `validar` ya viendo organización y PIN configurados. La actualización (B)
también se ensaya con una base que ya tenía PIN maestro: lo conserva y el administrador entra.

**Nunca viaja** configuración de desarrollo: `backend/.env` (con la sesión
obligatoria y un PIN maestro de ejemplo) y las bases SQLite sueltas se excluyen del
paquete y de la huella, y el build falla si se cuelan. Las pruebas del backend del
build corren sin la sesión obligatoria (el modo para el que se escribieron).

**El teclado táctil (desde la 2.4.0).** El primer arranque pide texto (documento,
nombres, nombre del aula) y la OPS no tiene teclado: el teclado táctil de Windows
tiene que salir solo al tocar un campo. Windows 10 trae apagada esa opción fuera del
modo tableta («Mostrar el teclado táctil cuando no hay un teclado conectado», en
Configuración → Dispositivos → Escritura), y sin ella el primer arranque —y con él el
PIN maestro— no se puede hacer. El instalador la **enciende** para quien da la clase:
dos valores de usuario en `HKCU\Software\Microsoft\TabletTip\1.7`
(`EnableDesktopModeAutoInvoke` y `TipbandDesiredVisibility`, este último deja además el
botón del teclado en la barra de tareas como segunda vía). Va en `[Run]` con
`runasoriginaluser`: el `HKCU` tiene que ser el de la persona de la clase y no el del
administrador que elevó el instalador. No toca servicios ni nada de administración y se
revierte desde esa misma pantalla de Configuración; si fallara, no rompe la instalación y
`AVACOM-Verificar-Instalador.bat` lo avisa (y avisa también si el servicio
`TabletInputService` está deshabilitado). Si quien da la clase usa otra cuenta de Windows
que la que instaló, esa cuenta lo activa una vez desde Configuración.

## Instalar muchas tabletas Android (servidor local del APK)

`installer/student-android/` es la carpeta de entrega del APK y se copia entera a un USB o al equipo que
va a repartirlo. `Servir-APK.bat` enciende un servidor local para que las tabletas descarguen el APK por
la red del aula, sin cable: pide el permiso de administrador **una** vez, abre el puerto 8080 en el
firewall **solo para la red local y solo mientras corre** (lo cierra al detenerse, incluso si se cierra la
ventana), abre en ese equipo un **panel con el código QR**, la dirección y un contador «N de 55», y la
página que ve la tableta lleva los pasos, la huella SHA-256 y la dirección del aula si OPS corre en el mismo
equipo. El Python viaja en la carpeta (`python\`, el mismo 3.12 embebido del paquete de OPS; se copia de la
caché de compilación y no se versiona), así que sirve en cualquier Windows sin instalar nada. La guía de
campo, con los pasos de cada tableta y los problemas típicos, es `student-android/GUIA-55-TABLETAS.txt`.

Cómo se probó: `Servir-APK.py` se ejercitó con **55 clientes simultáneos** (cada uno con su propia dirección
de origen) y con el Python embebido: 55 de 55 descargas con la misma huella en menos de un segundo en local,
una descarga reanudada tras un corte, otra en tres trozos paralelos (como hace Chrome), rangos, HEAD, descarga
cortada (no cuenta), una tableta que baja dos veces (cuenta una), el CSV `descargas-apk.csv`, y que «Detener»
sólo lo acepta el propio equipo. **Una tableta cuenta cuando recibió el archivo entero** (cobertura de bytes por
dirección) **y su conexión terminó con cierre limpio**: una petición `Range` que llega al final no basta. El
codificador de QR es propio (modo byte, niveles L y M, versiones 1 a 6) y se verificó con los vectores
publicados de Reed-Solomon («HELLO WORLD» 1-M y 1-Q), las 16 cadenas de formato de la norma y un decodificador
escrito aparte (184 códigos en las 8 máscaras); **no** se escaneó con la cámara de una tableta real, y por eso la
dirección también sale en letra grande.

## Pendiente

- **Student** tiene su propio instalador de Windows (`student-windows/`, ver su
  README) y su APK (`student-android/`, `build/Build-StudentApk.ps1`). Pendiente en
  los dos: el **icono** sigue siendo el de la plantilla de .NET MAUI (cambiarlo es
  copiar los dos SVG de OPS a `src/Avacom.Lms.Student/Resources/AppIcon`, un cambio
  de `src`), la **llave de firma** del APK es la de depuración y la **versión mínima
  de Android** declarada es la 5.0 (API 21) aunque se prueba en Android 13 y 14.
- El perfil de WebView2 dentro del propio producto (3 líneas en el arranque de OPS
  y de Student, junto a `WebViewAjustes`): hoy lo resuelve el instalador.
- **WebView2 Runtime en un Windows 10 limpio**: el asistente solo lo avisa; no lo
  instala (el instalador sin conexión pesa unos 170 MB).
- Firma de código: sin ella, SmartScreen advertirá de un editor desconocido.
- Firewall en red pública y OPS abriéndose sola al iniciar sesión: decisiones sin
  cerrar (ver `spec-driven/08-instalador.md`, artículo 11).
- Probar en una instalación real (equipo de aula): la instalación con permisos de
  administrador, abrir una lección y que la aplicación **no se cierre**, la
  reversión de una actualización y la desinstalación. El ensayo del paquete cubre el
  host, el backend y la configuración; las pantallas del asistente se vieron en una
  copia de pruebas, sin administrador (ver «Las pantallas se comprobaron viéndolas»).
