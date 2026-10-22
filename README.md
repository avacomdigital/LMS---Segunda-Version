<div align="center">

<img src="https://avacomworld.com/SVG/avacom-logo-horizontal.svg" alt="AVACOM — Logo horizontal" width="340" />

<br />
<br />

![Windows](https://img.shields.io/badge/Windows-OPS%20%26%20Student-0078D4?style=for-the-badge&logo=windows&logoColor=white)
![Android 14](https://img.shields.io/badge/Android%2014-Student-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![.NET MAUI](https://img.shields.io/badge/.NET%20MAUI-10-512BD4?style=for-the-badge&logo=dotnet&logoColor=white)
![Django REST Framework](https://img.shields.io/badge/Django-REST%20Framework-092E20?style=for-the-badge&logo=django&logoColor=white)

# AVACOM LMS · clientes .NET MAUI

**Ecosistema de aplicaciones nativas para la gestión del aula AVACOM.**

Prototipo desarrollado en **C# y .NET MAUI**, conectado a un backend local en **Django REST Framework**, diseñado para funcionar dentro de la red del aula.

</div>

---

## Aplicaciones

| Aplicación | Plataforma | Funcionalidades principales |
| --- | --- | --- |
| **AVACOM LMS OPS** | Windows | Nodo principal del profesor: diagnóstico de API, tablero, creación de cursos y monitoreo de cuestionarios (*quiz*). |
| **AVACOM LMS Student** | Windows y **tablets Android 14** | Nodo secundario del estudiante: nombre y dirección del aula, menú hexagonal, navegación de cursos, progreso y cuestionarios. |

> [!IMPORTANT]
> **Contexto de dispositivos:** las tablets utilizadas en el aula ejecutan **Android 14**. Ten presente esta versión al desarrollar, probar o desplegar AVACOM LMS Student, especialmente en permisos, conectividad LAN y comportamiento de la aplicación.

## Arquitectura y flujo de información

```text
AVACOM Biblioteca (equipo maestro)
          │ API local por loopback (puerto efímero)
          ▼
Backend LMS · Django REST Framework (:8000)
          │ REST / WebSocket
          ├───────────────────────┐
          ▼                       ▼
AVACOM LMS OPS                AVACOM LMS Student
Windows · Profesor            Windows / Android 14 · Estudiante
```

**AVACOM Biblioteca** proporciona los cursos y materiales. El **backend LMS** es el único componente que se comunica directamente con Biblioteca. Los clientes OPS y Student consumen el backend, que conserva el **expediente del estudiante**: inscripciones, aperturas del visor, progreso, intentos y calificaciones.

## Estructura del repositorio

```text
backend/                         Backend Django REST Framework; conexión con Biblioteca y expediente
src/
  Avacom.Lms.Core/               Dominio, demo, HTTP, WebSocket y fachada BibliotecaDeContenido
  Avacom.Lms.Ui/                 Controles MAUI compartidos (hexágonos, CourseContentView)
  Avacom.Lms.Ops/                Cliente del profesor (Windows): asignaturas y consolidado
  Avacom.Lms.Student/            Cliente del estudiante (Windows / Android): cursos y progreso
tests/
  Avacom.Lms.Core.Tests/         Pruebas de contratos del núcleo
specs/
  001-maui-clients/              Especificación y criterios de aceptación
  conexion_LMS_Biblioteca.md     Integración LMS ↔ AVACOM Biblioteca
spec-driven/                    Constitución, plan y contratos de integración
installer/                      Instalador de AVACOM OPS Master para Windows
```

## Instalar AVACOM OPS en un equipo del aula

Los comandos de desarrollo de las siguientes secciones no son necesarios para el usuario final. Para instalar el producto en el aula existe un **instalador con asistente**, preparado para funcionar sin conexión a internet y sin necesidad de escribir comandos durante la instalación. Incluye la aplicación, el backend, Python, Django, Django REST Framework y Waitress, y configura la API local como servicio de Windows en el puerto **8000**.

Para **construir el instalador** desde el repositorio:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build\Build-Installer.ps1
```

El archivo `.exe` generado se encuentra en `installer/latest`.

Consulta [la guía del instalador](installer/README.md) y [sus decisiones técnicas](spec-driven/08-instalador.md).

## Conexión con AVACOM Biblioteca

Los cursos **no se almacenan en el LMS**: AVACOM Biblioteca los sirve desde el equipo maestro mediante una API local de loopback, con puerto efímero. La información de conexión está en:

```text
%ProgramData%\AVACOM\contenido\enlace.json
```

El backend de `backend/` es el único encargado de establecer la comunicación con AVACOM Biblioteca. OPS y Student hablan con este backend; el LMS almacena solamente el **expediente** del estudiante.

Para conocer el contrato de integración, consulta [Conexión LMS–Biblioteca](specs/conexion_LMS_Biblioteca.md) y la [documentación del backend](backend/README.md).

## Requisitos de desarrollo

- **Windows** para desarrollar y ejecutar OPS y la variante de escritorio de Student.
- **SDK de .NET 10** con las cargas de trabajo de .NET MAUI correspondientes a Windows y/o Android.
- **Python** y `pip` para ejecutar el backend.
- **Android SDK, emulador o tablet Android 14** para probar Student en Android.
- Conectividad LAN entre el equipo maestro y los clientes para las pruebas de integración.

## Ejecutar el backend (Django REST Framework)

> [!NOTE]
> Inicia el backend antes de probar la conexión real de OPS o Student. Ambos clientes disponen de un **modo demo** si el backend no está disponible.

Desde la raíz del repositorio, abre PowerShell y sigue estos pasos.

**1. Entrar al directorio del backend y crear un entorno virtual:**

```powershell
cd backend
py -m venv .venv
```

**2. Instalar dependencias dentro del entorno virtual:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**3. Preparar la base de datos:**

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

**4. Iniciar el servidor:**

```powershell
.\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000
```

Si activaste el entorno virtual con `.\.venv\Scripts\Activate.ps1`, también puedes usar el comando habitual:

```powershell
py manage.py runserver 0.0.0.0:8000
```

El backend quedará escuchando en el puerto `8000` en las interfaces de red del equipo. Los clientes pueden consultar el endpoint `/health/`. Para conectarse desde las tablets, utiliza la **IP LAN del equipo maestro**, no `0.0.0.0` ni `localhost` de la tablet.

> [!WARNING]
> `runserver` es un servidor **solo para desarrollo**. En equipos de aula destinados a uso real, utiliza la instalación del producto con **Waitress y el servicio de Windows**. Permite el puerto `8000` únicamente en la red local de confianza, con las reglas de firewall correspondientes.

## Compilar y ejecutar los clientes

### Restaurar dependencias y compilar en Windows

Ejecuta estos comandos desde la **raíz del repositorio**:

```powershell
dotnet restore Avacom.Lms.slnx
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
dotnet test tests/Avacom.Lms.Core.Tests/Avacom.Lms.Core.Tests.csproj
```

### Abrir las aplicaciones en Windows

`dotnet build` solo compila. Para iniciar las interfaces:

```powershell
dotnet run --project src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0
dotnet run --project src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
```

También puedes abrir los ejecutables de compilación *Debug* si están presentes en las rutas indicadas:

```powershell
& '.\src\Avacom.Lms.Ops\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Ops.exe'
& '.\src\Avacom.Lms.Student\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Student.exe'
```

### Compilar Student para Android 14

Con el SDK Android y un emulador o dispositivo preparado:

```powershell
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-android
```

> **Nota:** este comando **compila** la aplicación Android; no implica instalarla o iniciarla automáticamente en la tablet. Valida los permisos, el acceso a la red local y el funcionamiento en dispositivos reales con **Android 14**.

### Compilación Release para Windows

```powershell
dotnet restore Avacom.Lms.slnx
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -c Release
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0 -c Release
```

Las rutas de ejecutables de la configuración Release, para compilaciones `win-x64` que produzcan esas salidas, son:

```text
src/Avacom.Lms.Ops/bin/Release/net10.0-windows10.0.19041.0/win-x64/Avacom.Lms.Ops.exe
src/Avacom.Lms.Student/bin/Release/net10.0-windows10.0.19041.0/win-x64/Avacom.Lms.Student.exe
```

La ubicación efectiva puede variar según la configuración de compilación y el identificador de runtime utilizado.

## Comportamiento de las aplicaciones

OPS y Student ofrecen un **modo demo** cuando el backend no está disponible. En el escenario conectado, el cliente consulta `/health/`, muestra las **Asignaturas** provenientes de AVACOM Biblioteca y registra el progreso del estudiante. El núcleo cuenta también con un cliente WebSocket para `/ws/activities/{activity_id}/`.

## Especificaciones y contexto para desarrollo asistido por IA

> [!TIP]
> Si trabajas con una IA o un agente de programación, comparte los documentos Markdown de las carpetas **[`spec-driven/`](spec-driven/)** y **[`specs/`](specs/)**. Contienen especificaciones funcionales, acuerdos arquitectónicos, contratos de integración y criterios de aceptación que ayudan a comprender las responsabilidades de cada módulo.

**Contexto esencial para el agente:**

1. El sistema tiene dos clientes .NET MAUI: **OPS en Windows** y **Student en Windows y tablets Android 14**.
2. El backend está en `backend/`, utiliza **Django REST Framework** y expone la API del aula en el puerto `8000`.
3. **AVACOM Biblioteca** es el proveedor de contenido; el LMS no duplica los cursos, sino que gestiona el expediente del estudiante.
4. **Solo el backend** debe comunicarse con AVACOM Biblioteca; las aplicaciones cliente consumen la API del LMS.
5. Antes de modificar un módulo, revisa sus contratos y criterios de aceptación en `specs/` y `spec-driven/`.
6. La instalación de aula debe permitir funcionamiento **sin internet**; valida el comportamiento de conectividad local y de Android 14.

---

<div align="center">

**AVACOM LMS** · Tecnología para el aula conectada

</div>
