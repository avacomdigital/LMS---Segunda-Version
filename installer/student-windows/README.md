# Instalador de AVACOM Student para Windows

Produce un único `.exe` que instala **AVACOM Student** (la app del estudiante) en un Windows 10
(1809 o posterior) o Windows 11 de 64 bits. Es **otro producto** que AVACOM OPS Master: otro
`AppId`, otra carpeta, otra entrega y otro desinstalador. No exige que OPS esté en el mismo equipo
y no lo toca. Lo único que comparten es la fuente de la versión (`installer/version.json`), para
poder saber si un OPS y un Student son compatibles.

```text
installer/student-windows/
├── build/
│   ├── Build-StudentInstaller.ps1  Un comando: del código fuente al .exe (y demuestra que es el actual)
│   ├── Distribucion.props          Propiedades de publicación (no toca ningún .csproj)
│   ├── New-VerificadorBat.ps1      Empaqueta el verificador en AVACOM-Verificar-Student.bat
│   └── PruebaAsistente.iss         Arnés: la misma lógica del asistente, sin nada que instalar
├── src/
│   ├── AvacomStudent.iss           El asistente (Inno Setup 6)
│   ├── definiciones.iss            Nombres, versión e identificador de instalación, en un sitio
│   ├── codigo.iss                  La lógica del asistente (compartida con el arnés)
│   ├── informacion.txt             Pantalla 2 · Información de AVACOM Student
│   └── lanzador/                   Avacom.Student.Lanzador: lo que abre el icono
├── tools/
│   └── Verificar-Student.ps1       El verificador (código fuente del .bat de latest)
└── latest/                         Lo que se entrega (todo junto)
    ├── AVACOM-Student-Setup-<versión>.exe   (no se versiona: supera los 100 MB de GitHub)
    ├── SHA256.txt                           Huella del .exe y del código que lleva
    ├── LEEME.txt
    └── AVACOM-Verificar-Student.bat         Revisa el equipo, el instalador y lo instalado; busca el error exacto
```

## Construirlo

```powershell
powershell -ExecutionPolicy Bypass -File installer\student-windows\build\Build-StudentInstaller.ps1
```

Requiere, solo en el equipo de compilación, el SDK de .NET 10 con la carga de trabajo MAUI e Inno
Setup 6 (`winget install JRSoftware.InnoSetup`). No hace falta Python ni internet en el equipo de
destino: el runtime de .NET y el Windows App SDK van dentro de la aplicación.

**Cómo demuestra que es la versión actual** (igual que el de OPS):

- Toma la huella del código (Student, Core, Ui y `assets/`; el asistente, el lanzador y los scripts)
  **al empezar y al terminar**: si cambió mientras compilaba, el `.exe` se descarta.
- `Avacom.Lms.Student.exe` tiene que declarar la versión de `installer/version.json`, ser más nuevo
  que el último archivo de código y no traer el icono de la plantilla de MAUI.
- El lanzador **verifica el paquete** tal como lo hará en el equipo (`verificar`).
- El arnés ejecuta las 8 comprobaciones del asistente de verdad (sin instalar nada).
- El `.exe` producido tiene que declarar la misma versión.
- Un árbol con cambios sin confirmar **se avisa** y queda en `manifiesto.json` y `SHA256.txt`.

## Lo que instala

```text
C:\Program Files\AVACOM\Student
├── App\         AVACOM Student (con .NET y el Windows App SDK dentro)
│   └── Avacom.Lms.Student.exe.WebView2\   perfil de WebView2 escribible por los usuarios (red de seguridad)
├── Lanzador\    Avacom.Student.Lanzador.exe (lo que abre el icono)
├── manifiesto.json   versión, revisión, huellas
└── LEEME.txt
```

- Icono en el **escritorio de todas las cuentas** y en el menú Inicio. No es una casilla: se crea siempre.
- **Sin servicio, sin puertos, sin firewall**: Student solo hace conexiones salientes hacia la OPS.
- Se instala **para todo el equipo** (varios estudiantes pueden usar el mismo equipo) y pide permisos
  de administrador **una sola vez**, al principio. La aplicación se abre como quien la usa
  (`runasoriginaluser`), no con el token del instalador.

## Permisos (quién escribe dónde)

| Carpeta | Administradores y `SYSTEM` | Usuarios | Quién escribe |
|---|---|---|---|
| `Program Files\AVACOM\Student\App`, `Lanzador` | control total | **solo lectura** | nadie en uso; solo el instalador |
| `App\Avacom.Lms.Student.exe.WebView2` | control total | **modificar** | WebView2, solo si la app se abre sin el icono |
| `%LOCALAPPDATA%\AVACOM\Student\WebView2` | — | su perfil | WebView2, vía el icono |
| `%LOCALAPPDATA%\AVACOM\Student\lanzador.log` | — | su perfil | el lanzador |
| `%LOCALAPPDATA%\User Name\com.avacom.lms.student` | — | su perfil | la app: dirección del aula, cola de respuestas, material de estudio |
| `%LOCALAPPDATA%\AVACOM\lms` | — | su perfil | la app: `fallos-student.log`, `logs\student-*.log` (compartida con OPS) |

**Por qué un lanzador.** Las lecciones con audio, video, PDF o laboratorio usan **WebView2**, que
guarda su perfil por defecto junto al ejecutable. La app vive en Program Files, donde el estudiante
no escribe: al abrir una lección el proceso se cierra sin avisar. El lanzador le da a WebView2 una
carpeta propia en el perfil de cada persona (`WEBVIEW2_USER_DATA_FOLDER`, que WebView2 ya lee: no
cambia el producto), y de paso evita que los estudiantes de un mismo equipo compartan cookies y caché.
La carpeta junto al `.exe` cubre abrir la app sin el icono. Un cambio de 3 líneas en el arranque de
Student lo resolvería dentro del producto; es un cambio de código y queda pendiente de que se pida.

## Actualizar y desinstalar

- El `AppId` no cambia entre versiones: una versión nueva se reconoce como actualización. El
  asistente cierra Student (solo ese proceso), **aparta** `App` y `Lanzador` a `Anterior`, copia lo
  nuevo, lo verifica con el lanzador y borra `Anterior`. Si algo falla (o se cancela), la versión
  anterior vuelve a su sitio. Nada se mezcla.
- Los datos de cada persona viven en su perfil: **una actualización no los toca**.
- Desinstalar (Aplicaciones instaladas o menú Inicio) quita archivos y accesos. Al final pregunta si
  borrar los datos **de esa cuenta de Windows**; por defecto, **No** (puede haber respuestas que aún no
  llegaron a la OPS). No toca `%LOCALAPPDATA%\AVACOM\lms` (registros compartidos con OPS).

## Comprobar un equipo sin instalar nada

```powershell
.\AVACOM-Student-Setup-2.3.0.exe /VERYSILENT /VOLCADO=C:\temp\diagnostico.txt
```

Ejecuta las 8 comprobaciones, las escribe en el archivo y aborta (Windows pide permiso de
administrador). Es lo que usa `AVACOM-Verificar-Student.bat`.

## Decisiones tomadas (por confirmar)

| # | Decisión | Por qué |
|---|---|---|
| 7 | Instalación **para todo el equipo** | Es lo normal en un aula con equipos compartidos; los datos son por usuario |
| 7 | **No** se siembra la dirección del aula | Hay que escribirla (o elegirla) la primera vez; sembrarla exige escribir el `preferences.dat` de MAUI de cada cuenta |
| 8 | Sin firma de código | SmartScreen avisará de «editor desconocido»: toca «Más información» → «Ejecutar de todos modos» |
| 9 | La versión sale de `installer/version.json` | La misma que OPS y el APK |
