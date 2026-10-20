# AVACOM LMS · clientes .NET MAUI

Prototipo nativo en C# para el aula AVACOM. La solución contiene dos aplicaciones:

- **AVACOM LMS OPS**: nodo principal Windows del profesor. Incluye diagnóstico de API, tablero, creación de curso y monitoreo de quiz.
- **AVACOM LMS Student**: nodo secundario Windows/Android. Incluye nombre y dirección del aula, menú hexagonal, curso navegable y quiz.

## Estructura

```text
backend/                 Backend Django REST Framework: cliente único hacia AVACOM Biblioteca + expediente del estudiante
src/
  Avacom.Lms.Core/       Dominio, demo, HTTP, WebSocket y la fachada BibliotecaDeContenido
  Avacom.Lms.Ui/         Controles MAUI compartidos (hexágonos, CourseContentView)
  Avacom.Lms.Ops/        Cliente profesor (Windows): Asignaturas de la biblioteca + consolidado
  Avacom.Lms.Student/    Cliente estudiante (Windows + Android): Asignaturas + curso con progreso
tests/
  Avacom.Lms.Core.Tests/ Pruebas de contratos del núcleo
specs/
  001-maui-clients/      Especificación y criterios de aceptación
  conexion_LMS_Biblioteca.md  Cómo se conectó el LMS con AVACOM Biblioteca (spec-driven)
spec-driven/             Constitución, plan y contrato de la frontera LMS ↔ Biblioteca
installer/               Instalador de AVACOM OPS Master para Windows
```

## Instalar en un equipo del aula

Lo de arriba es para desarrollar. Para entregar el producto a un aula hay un
instalador con asistente que no requiere teclado ni internet: incluye la
aplicación, el backend, Python, Django, DRF y Waitress, y deja la API local
como servicio de Windows en `0.0.0.0:8000`.

```powershell
powershell -ExecutionPolicy Bypass -File installer\build\Build-Installer.ps1
```

El `.exe` queda en `installer/latest`. Detalles en
[installer/README.md](installer/README.md) y decisiones en
[spec-driven/08-instalador.md](spec-driven/08-instalador.md).

## Conexión con AVACOM Biblioteca

Los cursos **no viven en el LMS**: los ofrece AVACOM Biblioteca en el equipo maestro
(API local en loopback, puerto efímero, ficha en `%ProgramData%\AVACOM\contenido\enlace.json`).
El backend de `backend/` es el único que habla con ella; OPS y Student hablan con el backend.
El LMS guarda únicamente el **expediente** (inscripción, aperturas del visor, progreso, intentos, notas).
Detalles en [specs/conexion_LMS_Biblioteca.md](specs/conexion_LMS_Biblioteca.md) y [backend/README.md](backend/README.md).

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver 0.0.0.0:8000
```

## Compilar

```powershell
dotnet restore Avacom.Lms.slnx
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
dotnet test tests/Avacom.Lms.Core.Tests/Avacom.Lms.Core.Tests.csproj
```

## Abrir las aplicaciones en Windows

`dotnet build` sólo compila. Para iniciar cada interfaz usa:

```powershell
dotnet run --project src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0
dotnet run --project src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
```


También puedes abrir directamente los ejecutables después de compilar:

```powershell
& '.\src\Avacom.Lms.Ops\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Ops.exe'
& '.\src\Avacom.Lms.Student\bin\Debug\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Student.exe'
```

Para Android, con un emulador o dispositivo configurado:

```powershell
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-android
```

Ambas apps ofrecen modo demo si el backend no está disponible. El servidor es el backend Django/DRF de `backend/` en `0.0.0.0:8000`; el cliente consulta `/health/`, pinta **Asignaturas** con los cursos de AVACOM Biblioteca y registra el progreso del estudiante. El núcleo incluye además el cliente para `/ws/activities/{activity_id}/`.

## Correr tu proyecto

```powershell
dotnet run --project src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0
dotnet run --project src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
```

## Construye el proyecto

```powershell
dotnet restore Avacom.Lms.slnx
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -c Release
dotnet build src/Avacom.Lms.Student/Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0 -c Release
```

Los ejecutables quedan en:

```powershell
.\src\Avacom.Lms.Ops\bin\Release\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Ops.exe
.\src\Avacom.Lms.Student\bin\Release\net10.0-windows10.0.19041.0\win-x64\Avacom.Lms.Student.exe
```
