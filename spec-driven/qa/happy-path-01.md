# Happy Path 01 · Qué probar esta semana

| Campo | Valor |
|---|---|
| Para qué sirve | Guía corta para que QA y desarrollo prueben, **del 5 al 9 de octubre de 2026**, los cuatro caminos principales del producto |
| Quién lo usa | Quien ejecute las pruebas (QA, desarrollo, producto) |
| Qué contiene | Qué hace el producto · por qué estos cuatro caminos · cómo prepararse · los pasos de cada camino · lo que ya se sabe que falla · calendario |
| Base | Código en `main` (`9ef86b74`), documentos de `spec-driven/` y un recorrido previo **por API** (sin pantallas) el 5-oct-2026 contra la biblioteca real instalada |
| Estado de la ejecución | **2026-10-08**: HP-01, HP-03 y HP-04 probados; **pendientes HP-02 y ESC-05-01**. Cinco hallazgos abiertos (QA-28 a QA-32, sección 9). Detalle por escenario en [escenarios-qa-02.md](escenarios-qa-02.md) y [avance](escenarios-qa-02-avance.html) |
| Planes por módulo | Estos pasos son el resumen de la semana. El detalle fino vive en `04-modo-estudio/testing.md` (HP-EST), `06-evaluation-delivery/testing.md` (HP-EVA) y `05-audit-logs/testing.md` (HP-AUD) |

---

## 0 · Estado de la ejecución (2026-10-08)

| Camino | Estado | Qué quedó |
|---|---|---|
| HP-01 · Clase completa | **Hecho** | Los 8 escenarios dieron correcto. Las fallas halladas (QA-26 y QA-27) quedaron resueltas y corregidas |
| HP-02 · Examen aleatorio | **Pendiente** | Sin ejecutar |
| HP-03 · Modo estudio | **Hecho** | Estado de las pruebas correcto. Dos correcciones por hacer: **QA-30** (los controles de algunas láminas no se ven en el modo estudio) y **QA-31** (en algunos laboratorios no se puede terminar la actividad) |
| HP-04 · Acceso por rol | **Hecho** | Probado de manera efectiva y funciona bien. Una sola excepción: **QA-32** (las sesiones de Student duran poco; hay que aumentar la duración) |
| ESC-05-01 · Red y carga (25 y 35 tabletas) | **Pendiente** | Sin ejecutar |

Hallazgos nuevos de la ejecución, todos en la sección 9: **QA-28** (una sesión saca a un estudiante y deja entrar al otro), **QA-29** (los videos no muestran sus controles), **QA-30**, **QA-31** y **QA-32**. Sugerencias de mejora (umbrales en las métricas de rendimiento y un snapshot con timestamp) en `escenarios-qa-02.md`.

---

## 1 · En una página

| # | Camino | Qué se prueba | ¿Se puede hacer hoy en pantalla? | Tiempo |
|---|---|---|---|---|
| HP-01 | **Clase completa** | Una clase con todos los tipos de objeto de AVACOM Biblioteca | Sí | 2 h |
| HP-02 | **Examen aleatorio** | El examen de la clase en Student, con preguntas distintas por alumno | Sí, pero el profesor lo aplica **por API** (OPS no tiene el camino) | 2 h |
| HP-03 | **Modo estudio** | Asignar, estudiar, practicar, descargar, trabajar sin red y ver quién completó | Sí | 2 h |
| HP-04 | **Acceso por rol** | Entrar como alumno, profesor y administrador y ver lo que corresponde a cada uno | Con matices: hay que **activar la sesión obligatoria** y el menú no cambia por rol | 1,5 h |

**Tres cosas que conviene saber antes de empezar**

1. **El contenido sale siempre de AVACOM Contenido** (no del curso de ejemplo). Para HP-01, HP-02 y HP-03 usa **«Estados de la materia y sus cambios»** (6.º, ciencias): trae los cinco tipos de objeto y los cinco tipos de medio.
2. **Por defecto el nodo no pide usuario ni clave** (modo prototipo). Para HP-04 hay que encender la sesión obligatoria (sección 4.2). Los otros tres caminos se prueban con el modo por defecto.
3. **El examen se aplica por API.** Con el contenido real, OPS no muestra el examen en la secuencia de la clase y por eso no ofrece «Aplicar examen» (sección 6, paso 0).

---

## 2 · Qué hace el producto hoy

```
 Student (alumno)  ──┐   Wi-Fi del aula :8000
                     ├──────────────►  Nodo (backend Django)  ───►  AVACOM Contenido
 OPS (profesor)    ──┘                 guarda sólo el expediente      dueño de los cursos
```

| Módulo | Qué hace | Dónde se ve |
|---|---|---|
| **Acceso** (MOD-001) | Instala la organización, inicia sesión con documento y clave, maneja roles (alumno, profesor, administrador, reportes, técnico), grupos y alumnos | OPS «Grupos»; acceso de OPS y de Student |
| **Clase en vivo** (MOD-007) | El profesor da la clase desde «Clase de hoy»: código de 6 dígitos, proyecta láminas, lecturas y laboratorios, bloquea pantallas, avisa y lanza actividades. El alumno entra con el código | OPS «Clase de hoy» · Student «Clase en vivo» |
| **Modo estudio** (MOD-008) | El profesor asigna una lección; el alumno estudia, practica, descarga y trabaja sin red; el profesor ve quién completó | OPS «Modo de estudio» · Student «Modo de estudio» |
| **Dispositivos** (MOD-009) | Registra las tabletas, las deja «asignadas» a un alumno o «compartidas» y permite bloquearlas | OPS «Dispositivos» |
| **Evaluación** (MOD-010) | Aplica el examen de la biblioteca con un nivel de control; el alumno lo presenta; el profesor revisa y libera los resultados | Student «Exámenes» · pantallas `Examen*` de OPS |
| **Auditoría y logs** (MOD-019) | Bitácora encadenada de todo lo importante y logs de diagnóstico | OPS «Historial» (administrador y técnico) |
| **AVACOM Contenido** | Guarda y entrega los cursos, los medios y la corrección de las preguntas. El LMS no copia ningún curso | App aparte (`Avacom.Content.App`) |
| **Instalador** | OPS Master para Windows (servicio + app) y APK de Student | `installer/latest` · `installer/student-android` |

**Todavía son maquetas** (no las pruebes como funcionalidad): Comunicación, Enciclopedia, Progreso, Calendario, Estudiantes, Perfil y Ayuda; «Reportes» de OPS (datos ficticios); y «Asignaturas» de OPS y Student, que sigue usando la conexión vieja con la biblioteca y dice «Biblioteca no disponible» aunque Contenido funcione.

---

## 3 · Por qué estos cuatro caminos

Se eligieron por cuatro razones: son los objetivos de la semana, tocan lo que más cambió el 1 y 2 de octubre, casi no tienen pruebas automáticas de pantalla y son lo primero que un aula de verdad va a usar.

| Objetivo de la semana | Camino | Qué módulos recorre |
|---|---|---|
| Una clase completa con todos los tipos de objeto | HP-01 | Clase en vivo · Contenido · Dispositivos |
| Un examen de la clase con preguntas aleatorias en Student | HP-02 | Evaluación · Contenido · Acceso |
| El modo estudio completo | HP-03 | Modo estudio · Dispositivos · Acceso |
| Login de alumnos, profesores y administradores | HP-04 | Acceso · OPS · Student |

**Se dejó fuera de esta semana:** el kiosco y el bloqueo de tabletas en hardware real (Android Device Owner, Assigned Access), la prueba con 25 o 50 tabletas, el instalador, la auditoría (ya tiene su plan HP-AUD) y las pantallas que son maqueta.

**Lo que ya existe y no hay que repetir:** el backend tiene **989 pruebas en verde** (4 omitidas) y Student.Tests **61 en verde**. Core.Tests da **536 de 537**: `ElEntregadorNoIntentaNadaSinAparatoNiSesion` falla en la corrida completa y pasa sola (comparte estado global con otras pruebas). OPS no tiene pruebas automáticas de pantalla.

---

## 4 · Antes de empezar

### 4.1 · Qué debe estar abierto

| Qué | Cómo |
|---|---|
| **AVACOM Contenido 2.1.7** | `C:\Program Files\AVACOM\Contenido\Avacom.Content.App.exe`. Comprueba `GET /api/aula/fuente/` → `disponible: true`, 7 cursos |
| **Nodo de QA** (backend) | Ver 4.2. En el equipo del profesor, puerto 8000 |
| **OPS** | `dotnet run --project src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0`, o el `.exe` de `bin\Debug` |
| **Student** (1 o 2 equipos) | Igual con `Avacom.Lms.Student`. En Android, `installer/student-android/Student LMS 2.2.0.apk` |

**Ojo con las versiones.** El instalador 2.2.0 y el APK salieron de la revisión `ae8eefd4` con cambios sin confirmar; `main` está en `9ef86b74`. Para probar lo mismo que está en el repositorio, compila desde `main` (`dotnet build … -f net10.0-windows10.0.19041.0`) o compara las huellas de `installer/latest/SHA256.txt`.

**OPS y Student en el mismo PC:** define `AVACOM_EXAM_NO_LOCKDOWN=1` antes de abrir Student, si no el examen supervisado se apodera del teclado y los monitores.

### 4.2 · Nodo de QA (sin ensuciar git)

El backend de desarrollo escribe en `backend/db.sqlite3-wal` y en `backend/logs`, que están versionados. Para probar, usa una base propia:

```powershell
New-Item -ItemType Directory -Force "$HOME\qa-hp01\logs" | Out-Null
cd backend
$env:AVACOM_LMS_DB       = "$HOME\qa-hp01\qa.sqlite3"
$env:AVACOM_LMS_DIR_LOGS = "$HOME\qa-hp01\logs"
$env:AVACOM_LMS_EXIGIR_SESION = '0'          # '1' para HP-04 (sesión obligatoria)
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py acceso_instalar --codigo PRUEBA-QA --nombre "Colegio QA" --pais CO --admin-dni 90000001 --admin-nombres Admin --admin-apellidos Prueba
.venv\Scripts\python manage.py runserver 0.0.0.0:8000 --noreload
```

`acceso_instalar` muestra **una sola vez** la clave inicial del administrador. Es provisional: hay que cambiarla antes de usar la cuenta (`PUT /api/acceso/yo/credencial/` con `secreto_actual` y `secreto_nuevo`).

**Nodo instalado:** pon `AVACOM_LMS_EXIGIR_SESION=1` en `C:\ProgramData\AVACOM\OPS Master\Config\backend.env` y reinicia el servicio `AVACOMOPSBackend`. Para saber en qué modo está: `GET /api/acceso/configuracion/` → `sesion_obligatoria`.

### 4.3 · Personas y tabletas de prueba

| Quién | Cómo se crea | Nota |
|---|---|---|
| Grupos «Quinto A» y «Sexto B» | OPS «Grupos» → «+ Nuevo grupo» | |
| Alumnos (Ana, Beto, Carla en Quinto A; Diego en Sexto B) | OPS «Grupos» → registrar estudiante. **Pon siempre «Documento»** | Sin documento la clave que muestra OPS no sirve para entrar (QA-02) |
| Un profesor por grupo y, si quieres, técnico y reportes | **Sólo por API** (`POST /api/acceso/usuarios/`, con `secreto_definitivo: true`) | OPS no tiene pantalla para crear docentes |
| Profesor como «docente» de su grupo | **Sólo por API** (`POST /api/acceso/grupos/{id}/miembros/` con `papel: "DOCENTE"`) | Sin esto, su pantalla «Grupos» sale vacía |
| Tabletas | Se registran solas al abrir Student. Asigna una a Ana en OPS «Dispositivos» | T-A = asignada a Ana · T-C = compartida |

Ejemplo para crear un profesor (en modo con sesión, con el token del administrador):

```powershell
$h = @{ Authorization = "Bearer $TOKEN_ADMIN" }
$u = Invoke-RestMethod "$NODO/api/acceso/usuarios/" -Method Post -Headers $h -ContentType 'application/json' -Body (@{
  rol='TEACHER'; alias='Prof. Gómez'; persona=@{nombres='Luis'; apellidos='Gómez'}
  identificadores=@(@{tipo='DNI'; valor='80000001'; es_login=$true; principal=$true})
  secreto='<clave de 8+ con mayúscula y símbolo>'; secreto_definitivo=$true } | ConvertTo-Json -Depth 5)
Invoke-RestMethod "$NODO/api/acceso/grupos/$GRUPO_ID/miembros/" -Method Post -Headers $h -ContentType 'application/json' `
  -Body (@{ usuario_id=$u.id; papel='DOCENTE' } | ConvertTo-Json)
```

---

## 5 · HP-01 · Clase completa

> **Estado (2026-10-08): hecho.** Los 8 escenarios dieron correcto; QA-26 y QA-27 quedaron resueltos y corregidos. Abierto: QA-29 (controles del video).

**Objetivo.** Dar una clase de principio a fin con los cuatro tipos de objeto que entran en una clase (presentación, lectura, laboratorio y actividad) y comprobar que cada medio (imagen, video, audio, PDF y simulación) se ve en OPS y en Student. El quinto tipo, el examen, se prueba en HP-02.

**Curso:** *Estados de la materia y sus cambios* · **Lección 1:** «Los tres estados de la materia» (presentación de 7 láminas, lectura de 4 páginas con audio, video y PDF, laboratorio PhET y actividad de 7 preguntas) · **Lección 2:** «Cambios de estado».

**Comprobado por API el 5-oct:** código de 6 dígitos, entrada y readmisión del alumno, selector, bloqueo, avisos, mano levantada, actividad lanzada y respondida (el alumno no ve nota), cierre con resumen y los 106 medios de los 7 cursos (todos responden con su tipo correcto y admiten `Range`).

| # | Quién · dónde | Qué hacer | Qué debe pasar |
|---|---|---|---|
| 1 | OPS | «Clase de hoy» | El chip dice «Biblioteca conectada» y aparecen los cursos por materia |
| 2 | OPS | «Ciencias naturales» → *Estados de la materia…* → «Ver lecciones ›» | Lección 1 con 4 objetos; lección 2 con 3. **No** hay lección de examen |
| 3 | OPS | Lección 1 → «Dar clase con esta lección» | Aparece el **código de 6 dígitos** («CÓDIGO DE UNIÓN · TOCA PARA AMPLIAR») |
| 4 | Student A | «Clase en vivo» → escribe el código → «Entrar a la clase» | Entra. En OPS aparece «1 conectados» (≤ 3 s). Un código malo da «Ese código no es» |
| 5 | OPS | Presentación: pasa las 7 láminas con ▶ | Se ven título, texto, lista, imagen y video. Student las replica en ≤ 3 s |
| 6 | OPS | Lectura: las 4 páginas | Suenan el audio y el video; el PDF se abre |
| 7 | OPS | Laboratorio «PhET» y luego, en la lección 2, la curva de calentamiento | La simulación carga y responde. **Probar con el dedo en la tableta** (QA-08) |
| 8 | OPS | Actividad: vista previa (7 preguntas) | Se ven los 6 tipos: opción múltiple, V/F, completar, relacionar, ordenar y abierta |
| 9 | OPS → Student | «Bloquear pantallas» → «Navegación libre» → «Enviar un aviso» («Dos minutos») | Student muestra «Mira al frente», luego deja navegar, y muestra el aviso |
| 10 | Student → OPS | «✋ Pedir ayuda» y luego «Atender» | OPS muestra la mano levantada y luego la baja |
| 11 | OPS → Student | «Lanzar actividad» a todo el grupo; el alumno pulsa «Empezar» y responde los 6 tipos | Student: «Entregado. Tu profesor ya lo tiene.» (sin nota). OPS: «Ver avance en vivo» |
| 12 | OPS | «Terminar clase» | Con una actividad abierta espera 60 s o «Cerrar ahora». Sale el resumen. Student: «La clase terminó» |

**Para cubrir todos los tipos con contenido real**

| Tipo | Dónde se prueba | Nota |
|---|---|---|
| Objetos: presentación, lectura, laboratorio, actividad | Estados de la materia (pasos 5 a 11) | El examen va en HP-02 |
| Bloques: título, texto, lista, imagen, video, audio, PDF, simulación | Estados de la materia | |
| Preguntas: opción múltiple, V/F, completar, relacionar, ordenar, abierta | Estados de la materia, actividad de la lección 1 | |
| Fórmula | *Teoremas de Pitágoras y Tales* (15 fórmulas) | Se ven con TeX crudo (QA-10) |
| `drag_drop` (arrastrar y soltar) | *Pitágoras y Tales*, *Algoritmos*, *Lectura crítica* | No tiene editor (QA-07): se espera «Esta pregunta se responde con tu profesor» |
| Imágenes SVG | *Algoritmos* y *Lectura crítica* | Posible recuadro en blanco (QA-09) |
| Contenido en inglés | *The U.S. Constitution* | Los subtítulos salen marcados como «es» |

**Listo cuando** los 12 pasos pasan y los tipos de la tabla se vieron al menos una vez.

---

## 6 · HP-02 · Examen con preguntas aleatorias

> **Estado (2026-10-08): pendiente.** Aún no se ejecuta.

**Objetivo.** Un examen de la clase que cada alumno presenta en Student con **preguntas distintas**, y comprobar que el azar existe y que no cambia al reabrir.

**Cómo funciona el azar (para saber qué mirar).** El examen real *Examen de estados de la materia* tiene un banco de **18 preguntas** y pide **6 por alumno** (`random_balanced`: al azar, equilibradas por dificultad y con al menos una de cada uno de los 3 temas). El nodo arma el examen de cada alumno con una semilla (asignación + alumno + número de intento), así que **reabrir da lo mismo** y un intento nuevo da otro examen. Las opciones de las preguntas las baraja la biblioteca con esa misma semilla. Dura **6 minutos**; si necesitas más, usa `tiempo = @{modo='sin_limite'}` al aplicarlo.

Cursos con azar: *Estados de la materia* (6 de 18), *Fracciones* (4 de 12), *Algoritmos* (6 de 18), *Lectura crítica* (6 de 18) y *Pitágoras y Tales* (12 de 80). *The U.S. Constitution* es `fixed`: todos reciben lo mismo.

**Comprobado por API el 5-oct con 8 alumnos:** 8 conjuntos distintos y 8 órdenes distintos; 6 preguntas cada uno sin repetir; los 3 temas siempre; opciones en orden distinto; reabrir da lo mismo; el 2.º intento y una asignación nueva dan otro armado; sin claves de respuesta en lo que recibe el alumno; los alumnos con pregunta abierta quedan «en revisión» (entre 2 y 5 de 8, según el azar); antes de liberar, el alumno no ve nota.

**Paso 0 · aplicar el examen (profesor, por API).** Una sola vez, antes de que los alumnos entren:

```powershell
$cuerpo = @{ fuente='biblioteca'; curso_ref='avacom.co.lower_secondary.6.science.states-of-matter'; objeto_ref='l3-exam'
  alcance='grupo'; grupo_id=$GRUPO_ID; nivel_examen='abierto'; tiempo=@{modo='biblioteca'}; intentos_permitidos=2
  plazo='blando'; reactivacion='profesor'; resultados='tras_liberar'; iniciar=$true
  actor='prof-qa'; actor_rotulo='Profesor de prueba' } | ConvertTo-Json -Depth 5
$asig = Invoke-RestMethod "$NODO/api/evaluacion/asignaciones/" -Method Post -ContentType 'application/json; charset=utf-8' `
          -Body ([Text.Encoding]::UTF8.GetBytes($cuerpo))        # con sesión obligatoria, agrega -Headers @{Authorization="Bearer $TOKEN"}
$asig.armado_previo     # estrategia random_balanced · 6 por alumno · banco 18 · ~360 s
```

| # | Quién · dónde | Qué hacer | Qué debe pasar |
|---|---|---|---|
| 1 | Student A | Dock «Exámenes» → «¿Quién eres?» → toca su nombre → «Mis evaluaciones» → «Comenzar» | Tarjeta con «6 preguntas» y chip «Abierto». La antesala muestra duración e «Intento 1 de 2» |
| 2 | Student A | «Comenzar» de la antesala. **Anota** las 6 preguntas en orden y las opciones de las de elegir | «Pregunta 1 de 6», cronómetro y «0 de 6 contestadas» |
| 3 | Student A | Responde una de cada tipo que toque; usa «Siguiente», «Anterior» y la tira de números | El contador sube y dice «✓ Guardado». No se ve ninguna nota |
| 4 | Student A | Deja **una sin responder** y pulsa «Entregar» | «Te faltan N preguntas. Puedes entregar igual» → «Entregar igual» → «Tu examen quedó entregado» |
| 5 | Student B (otra tableta o tras «¿No eres tú?») | Repite 1 a 4 y **anota** sus preguntas | Orden distinto al de A; conjunto distinto en la mayoría de los pares; opciones de una pregunta común en otro orden |
| 6 | Student A | Antes de entregar, sal y vuelve a «Comenzar» (o reinicia Student) | **Las mismas** preguntas, orden y opciones |
| 7 | Profesor (API) | `GET /api/evaluacion/asignaciones/{id}/panel/` | Las filas muestran entregados y en revisión |
| 8 | Profesor (API) | Si hay pregunta abierta: `GET …/intentos/{id}/revision/` → `POST …/respuestas/{ref}/puntuar/` → `POST …/intentos/{id}/publicar/` → `POST …/asignaciones/{id}/liberar-resultados/` | Antes de liberar, el alumno recibe «Tu profesor aún no publica los resultados». Después ve su porcentaje y «Pregunta por pregunta» |
| 9 | Profesor (API) | `POST …/intentos/{id}/anular/` con un motivo de 3+ caracteres | El intento queda «anulado» (un motivo de 1 letra da 400) |

**Cómo anotar el azar** (con 4 a 6 alumnos basta): una fila por alumno con sus 6 preguntas en orden. Debe haber conjuntos distintos, órdenes distintos, los 3 temas en cada uno y, en una pregunta común, opciones en orden distinto.

**Detalles que verás:** la lista de llamadas con sus cuerpos está en `06-evaluation-delivery/testing.md` (HP-EVA-01 a 05). Student **no ofrece «Comenzar» para un 2.º intento** aunque el nodo lo admite (QA-15). El cronómetro no cambia de color ni suena al terminar: es a propósito, y recuerda que el examen dura 6 minutos.

**Listo cuando** los pasos 1 a 8 pasan, el azar se ve en al menos 4 alumnos y reabrir no cambia nada.

---

## 7 · HP-03 · Modo estudio completo

> **Estado (2026-10-08): hecho, con dos correcciones.** QA-30: los controles de algunas láminas no se ven en el modo estudio. QA-31: en algunos laboratorios no se puede terminar la actividad.

**Objetivo.** Que un profesor asigne una lección y que un alumno la estudie, practique, descargue, trabaje sin red y termine, y que el profesor vea quién completó.

**Lección:** «Los tres estados de la materia» · **Tabletas:** T-A (asignada a Ana) y T-C (compartida).

**Comprobado por API el 5-oct:** asignar a un grupo, «¿Quién eres?» con los alumnos del grupo, abrir la lección, práctica con veredicto de la biblioteca, completar, paquete con huella correcta y descarga por tramos, descarga negada en la tableta de otra persona y en la compartida, trabajo sin red con 10 eventos que se integran y que no se duplican si se reenvían, «quién completó» y cierre de la asignación.

| # | Quién · dónde | Qué hacer | Qué debe pasar |
|---|---|---|---|
| 1 | OPS «Grupos» | Crea el grupo y registra a Ana, Beto y Carla con documento | «3 estudiantes»; cada uno «quedó registrado» |
| 2 | OPS «Dispositivos» | T-A → «Asignar a un alumno» → Ana → «Asignar» | «Asignada a Ana…» y botón «Devolver al aula» |
| 3 | OPS «Modo de estudio» | «Asignar mi primera lección» → todo el grupo → busca el curso → la lección → fecha límite, «Flexible», «Se puede descargar» → «Asignar la lección» | «Listo · Lección asignada a 3 alumnos» |
| 4 | Student T-A | «Modo de estudio» → «¿Quién eres?» → Ana → «Continuar como Ana» | «Estudias como Ana…» y la tarjeta ○ PENDIENTE |
| 5 | Student T-A | «Comenzar lección», pasa las láminas y páginas | Pasa a ◐ EN CURSO. OPS muestra «EN CURSO» |
| 6 | Student T-A | «Practicar» → «Comprobar» en cada pregunta → «Terminar» | «✓ ¡Correcto!» o «✗ Todavía no» en ≤ 2 s; al final «X de 7 correctas» (nunca «nota») |
| 7 | Student T-A | «Terminar lección» | «¡Lección completada!». OPS: COMPLETADA, 100 % |
| 8 | Student T-A | «Descargar · NN MB» (en otra lección) y pausa/continúa | «Disponible sin conexión». OPS: «En el aparato» |
| 9 | Student T-A | **Apaga el Wi-Fi.** Lee, responde la práctica, «Terminar lección» | «Sin conexión», «Pendiente de enviar · N» y «Práctica guardada» |
| 10 | Student T-A | **Enciende el Wi-Fi** | «Sincronizando…» → «Guardado» en menos de un minuto. OPS: COMPLETADA, práctica calificada |
| 11 | Student T-C | «Cambiar» → Beto (dos toques) | Ve sólo lo suyo. Su tarjeta muestra el candado y **no** puede descargar |
| 12 | OPS | «Ver quién completó» | Tabla con estado, avance, práctica y aparato de cada alumno |
| 13 | OPS | «Cerrar la asignación» | En Student desaparece de «Pendientes». Completar ya no es posible |
| 14 | Student | «Salir» | «Listo. Tu trabajo queda guardado y se enviará solo» (≤ 3 s) |
| 15 | OPS «Dispositivos» | T-A → «Devolver al aula» | Si quedó una descarga sin retirar, responde que hay un paquete sin integrar (QA-18) |

**Regla nueva que cambia el avance (1-oct):** en una lección **con práctica**, sólo las prácticas son obligatorias. Por eso el avance sigue en 0 % mientras el alumno ve láminas y salta a 100 % al terminar la práctica y la lección. OPS dice «3 de 7 actividades · 0 %» y la tarjeta de Student puede decir 43 %: es el mismo estado visto de tres formas (QA-19). Los documentos viejos todavía hablan de 75 %.

**Listo cuando** los 15 pasos pasan, el trabajo sin red llega una sola vez y OPS muestra a los tres alumnos con su estado correcto.

---

## 8 · HP-04 · Acceso por rol

> **Estado (2026-10-08): hecho; funciona bien con una sola excepción.** QA-32: las sesiones de Student duran poco y hay que aumentar la duración.

**Objetivo.** Entrar como alumno, profesor y administrador y comprobar que cada uno ve **la información que le corresponde** y no ve la de otros.

**Antes de empezar:** activa la **sesión obligatoria** (4.2), crea las personas (4.3) y cambia la clave provisional del administrador. Con el modo por defecto nadie pide clave: OPS entra con «EC Iniciar como profesor» y Student sólo pide un nombre.

**Comprobado por API el 5-oct:** inicio de sesión de los tres roles, permisos de cada uno (administrador 54, profesor 42, alumno 19), el administrador con clave provisional sólo puede cambiarla, el profesor ve sólo a los alumnos de sus grupos, el alumno sólo se ve a sí mismo, 5 intentos fallidos bloquean 15 minutos (y ni con la clave buena entra hasta que alguien lo desbloquea), y una segunda sesión cierra la primera.

**Lo que el producto muestra hoy por rol**

| | Alumno | Profesor | Administrador |
|---|---|---|---|
| **Dónde entra** | Student: «Tu código» y «Tu clave» | OPS: «Documento», «Clave» y «Entrar» | OPS: igual que el profesor |
| **Qué ve al entrar** | «Bienvenido, Ana» (su primer nombre) y 9 teselas fijas. Con acción: Clase en vivo, Asignaturas y Modo de estudio; dock: Estudio y Exámenes | Tablero con la etiqueta «Profesorado» y 12 teselas, **sin** «Historial» | Tablero con «Administración» y 12 teselas, **con** «Historial» (Bitácora de 5 pestañas) |
| **Su información** | Sólo sus lecciones y exámenes, los de su grupo | Sólo sus grupos y alumnos | Toda la organización |
| **Qué puede hacer** | Estudiar, practicar, presentar su examen, ver su resultado cuando se libere | Dar clase, asignar estudio y exámenes, revisar, registrar alumnos **en sus grupos** | Todo lo del profesor, más crear grupos, asignar o liberar tabletas, leer la bitácora |
| **Qué NO puede** | Crear grupos, leer la bitácora, ver a los demás | Crear grupos (aparece «Con tu perfil no puedes hacer esto…»), asignar tabletas, bitácora | Presentar exámenes ni abrir el modo estudio como alumno |

**Lo que el objetivo pide y hoy no existe:** el menú **no cambia por rol**. Las teselas son las mismas para todos; sólo «Historial» depende del rol. El diseño promete «lo que el rol no puede hacer no se muestra» (UXR-010), pero no está construido (QA-05). Por eso estos pasos comprueban la **información** de cada rol y que el servidor **rechaza** lo que no corresponde, no que el menú se adapte.

| # | Quién | Qué hacer | Qué debe pasar |
|---|---|---|---|
| 1 | Administrador (OPS) | Entra con documento y clave **provisional** | Entra, pero no puede crear nada hasta cambiar la clave (hoy se hace por API) |
| 2 | Administrador (OPS) | Entra con la clave definitiva | «Administración», 12 teselas, «Historial» con 5 pestañas. «+ Nuevo grupo» funciona |
| 3 | Profesor (OPS) | Entra con su documento y clave | «Profesorado», sin «Historial». «Grupos» muestra **sólo su grupo** |
| 4 | Profesor (OPS) | «+ Nuevo grupo» | «Con tu perfil no puedes hacer esto…» |
| 5 | Profesor sin grupo asignado | Entra | «Grupos» vacío: «Todavía no hay grupos» (falta asignarlo como docente, por API) |
| 6 | Alumno de Quinto A (Student) | «Tu código» y «Tu clave» | «Bienvenido, Ana». En «Modo de estudio» y «Exámenes» sólo aparece lo de Quinto A |
| 7 | Alumno de Sexto B (Student) | Entra | **No** ve nada de Quinto A |
| 8 | Alumno en OPS | Intenta entrar en OPS | «Esta pantalla es del profesorado. Usa la tableta del alumno.» **Ojo:** abre su sesión y cierra la de su tableta (QA-24) |
| 9 | Cualquiera | Clave equivocada 4 veces | «Ese documento o esa clave no coinciden. Te quedan N intentos.» |
| 10 | Cualquiera | 5.º intento | «Demasiados intentos. Vuelve a intentarlo en 15 min.» (30 para administrador y técnico). Con la clave buena sigue sin entrar |
| 11 | Administrador/profesor | Desbloquear (por API: `POST /api/acceso/usuarios/{id}/desbloquear/`) | El alumno vuelve a entrar |
| 12 | Alumno | Entra en una segunda tableta | La primera muestra «Abriste tu sesión en otra tableta» |

**Extra si hay tiempo:** técnico (OPS «Historial» → «Diagnóstico del nodo»), reportes y un nodo vacío (hoy responde 401, no «no instalado»).

**Listo cuando** los 12 pasos pasan, la información de cada rol es la esperada y las diferencias con el objetivo quedaron anotadas.

---

## 9 · Lo que ya se sabe que falla (posibles bugs)

«Comprobado» = se reprodujo el 5-oct contra el nodo y la biblioteca real. «En el código» = se vio leyendo el código y hay que confirmarlo en pantalla.

**Bloquean un camino**

| ID | Camino | Qué pasa | Cómo verlo | Estado |
|---|---|---|---|---|
| QA-01 | HP-02 | OPS no puede aplicar el examen real: el aula pide el curso en modo «clase» y el examen es de modo «examen». «Aplicar examen» sólo nace de esa fila | «Clase de hoy» → *Estados de la materia* → la secuencia no trae examen. Desvío: aplicarlo por API (sección 6) | Comprobado |
| QA-02 | HP-04 | Con sesión obligatoria, los alumnos de «Grupos» no sirven: sin documento la «Clave de acceso» no entra (401); con documento el PIN es provisional y ninguna pantalla lo cambia (estudio y examen dan 403 «Tu rol no tiene concedido study.open») | Registra un alumno sin documento y entra en Student. Desvío: crear con documento y PIN por API | Comprobado |
| QA-03 | HP-04 | No hay «primer arranque» con administrador conocido: «Preparar aula de prueba» crea el admin sin devolver su clave y el instalador no crea la organización | Instalar y abrir OPS → Grupos. Desvío: `acceso_instalar` | Comprobado |
| QA-04 | HP-04 | Un nodo instalado queda sin sesión obligatoria: OPS entra sin clave y cualquier equipo de la red puede crear clases o grupos | `POST /api/aula/sesiones/` sin token → 201 | Comprobado |

**Afectan lo que verás**

| ID | Camino | Qué pasa | Cómo verlo | Estado |
|---|---|---|---|---|
| QA-05 | HP-04 | El menú no cambia por rol (12 teselas en OPS, 9 en Student; sólo «Historial» varía) | Entrar con cada rol y comparar | En el código |
| QA-06 | HP-04 | Con sesión obligatoria, `inscripciones`, `resultados`, el consolidado y la biblioteca siguen abiertos sin token | `POST /api/inscripciones/` sin token → 201 | Comprobado |
| QA-07 | HP-01 | `drag_drop` no tiene editor: «Esta pregunta se responde con tu profesor». Son 11 preguntas (Pitágoras 8, Algoritmos 2, Lectura crítica 1) y 8 más en los bancos de examen | Pitágoras, lección 1, práctica | Comprobado |
| QA-08 | HP-01 | Las simulaciones piden `/__avacom/shims.js` y el nodo responde 404 (22 de 22). 8 piden `touch=1` | Abrir las simulaciones de Algoritmos, Lectura crítica o la recta numérica de Fracciones con el dedo | Comprobado |
| QA-09 | HP-01 | Las 8 imágenes SVG (Algoritmos, Lectura crítica) pueden verse como recuadro en blanco | Abrir la portada y las láminas de esos cursos | En el código |
| QA-10 | HP-01 | 8 de 16 fórmulas de Pitágoras llegan con TeX crudo: `\sqrt75^2 + 42^2`, `\Rightarrow`, `\text m` | Pitágoras, lecciones con fórmulas | Comprobado |
| QA-11 | HP-01 | Ordenar, relacionar y las opciones cambian de lugar cada vez que se pide la actividad (12 lecturas: 5, 10 y 6 órdenes distintos) | Abrir la actividad, responder una pregunta, salir y volver | Comprobado |
| QA-12 | HP-01 | Reanudar una clase suspendida cuando el profesor ya abrió otra da **500** (`IntegrityError`) en vez de 409 | Reiniciar el nodo con una clase abierta, abrir otra y reanudar la primera | Comprobado |
| QA-13 | HP-01 | «Asignaturas» (OPS y Student) dice «Biblioteca no disponible» aunque Contenido nuevo funciona | Tocar «Asignaturas» | En el código |
| QA-14 | HP-01 | Las dos simulaciones «PhET» instaladas son sustitutos de desarrollo con un banner amarillo | Laboratorio PhET de Estados de la materia y de Fracciones | Comprobado |
| QA-15 | HP-02 | Student no ofrece «Comenzar» para un 2.º intento aunque el nodo lo admite | Aplicar con 2 intentos y entregar el primero | En el código |
| QA-16 | HP-02 | Si OPS bloquea la tableta en pleno examen, la cola descarta respuestas y entrega mientras la pantalla dice «guardado» | Bloquear una tableta durante el examen | En el código |
| QA-17 | HP-02 | El nivel «Supervisado» promete «consultar materiales» y no existe esa función; el PIN de salida del kiosco no se puede fijar; el kiosco no está probado en hardware | Sólo en tableta real | En el código |
| QA-18 | HP-03 | «Salir» borra la cola de **otro** alumno si no hay aula; los rechazos del nodo no se muestran; «Salir» deja paquetes huérfanos en el nodo (la tableta no se puede devolver al aula) | Ana completa sin red; «Cambiar» → Beto → «Salir»; reconectar | En el código |
| QA-19 | HP-03 | Con práctica, sólo la práctica es obligatoria y el avance es 0 % hasta terminarla; los documentos dicen 75 % | Ver láminas y mirar OPS | Comprobado |
| QA-20 | HP-03 | Dos alumnos con el mismo nombre se ven iguales; la huella de la tableta es `student-<nombre del equipo>` (dos con igual nombre son una) | Registrar dos «Ana» en «Grupos» | En el código |
| QA-26 | HP-01 | La sesión del profesor se denegaba a los pocos minutos: el pase dura 240 min pero la inactividad de fábrica la cerraba a los 20 (30 el alumno) mientras la clase seguía en pantalla | «Clase de hoy» con el instalador 2.3.0, dejar la clase sin tocar y volver a usar OPS | Corregido en 2.3.1 y repetido con éxito |

**Hallazgos de la ejecución (semana del 5 al 9)**

| ID | Camino | Qué pasa | Cómo verlo | Estado |
|---|---|---|---|---|
| QA-27 | HP-01 | Láminas en gris y video y audio que no se reproducen: con sesión obligatoria la ruta de medios respondía 401 porque el visor no mandaba el pase | Abrir la presentación con el nodo con sesión obligatoria | Resuelto y corregido (propuesta en `bugfix/bugfix-01-videos.md`) |
| QA-28 | HP-04 | Problemas de sesiones: el nodo saca a un estudiante y al otro lo deja entrar | Dos estudiantes con sesión abierta; ver si uno pierde la suya sin motivo | Abierto · por reproducir |
| QA-29 | HP-01 · HP-03 | Los videos no muestran sus controles | Reproducir un video en OPS y en Student | Abierto |
| QA-30 | HP-03 | Los controles de algunas láminas no se pueden ver en el modo estudio | Modo de estudio → recorrer las láminas de una lección | Abierto · corrección pendiente |
| QA-31 | HP-03 | En algunos laboratorios no se permite terminar la actividad | Modo de estudio → abrir los laboratorios de la lección y terminar | Abierto · corrección pendiente |
| QA-32 | HP-04 | Las sesiones de Student duran poco; hay que aumentar la duración | Entrar como alumno y dejar la tableta; ver cuándo pide entrar otra vez | Abierto · corrección pendiente |

**De preparación**

| ID | Qué pasa | Estado |
|---|---|---|
| QA-21 | El instalador 2.2.0 y el APK salen de `ae8eefd4` con cambios sin confirmar; `main` está en `9ef86b74`. No hay instalador de Student para Windows. El cortafuegos abre el 8000 sólo en redes privadas y Student propone `192.168.1.10` | Comprobado |
| QA-22 | `backend/db.sqlite3-wal`, `-shm`, los logs y `dist/` están en git (commit `9ef86b74`): correr el backend de desarrollo ensucia el árbol | Comprobado |
| QA-23 | Core.Tests: 1 prueba falla en la corrida completa (estado global compartido). No hay CI ni pruebas de pantalla de OPS | Comprobado |
| QA-24 | OPS comprueba el nivel **después** de abrir la sesión: un alumno que prueba OPS cierra la sesión de su tableta. El login responde distinto si el documento existe (`intentos_restantes`) | En el código |
| QA-25 | OPS pide teclado (buscador del modo estudio, registro en «Grupos») aunque el nodo del profesor no tiene teclado | En el código |

**No son bugs (para no perder tiempo):** el alumno no ve nota en clase ni antes de que el profesor libere el examen (es la regla); el profesor puede leer el catálogo de permisos; el examen de *The U.S. Constitution* no tiene azar (es `fixed`); Student no entra a pantalla completa salvo `AVACOM_STUDENT_KIOSCO=1`.

---

## 10 · Calendario sugerido

| Día | Qué | Quién |
|---|---|---|
| **Lun 5** | Preparar: Contenido abierto, nodo de QA, apps compiladas desde `main`, personas y tabletas (4.1 a 4.3) | QA + desarrollo |
| **Mar 6** | **HP-04** (con sesión obligatoria) y primera pasada de **HP-01** | QA |
| **Mié 7** | **HP-02** (examen aleatorio con 4 a 6 alumnos) | QA + una persona de apoyo |
| **Jue 8** | **HP-03** (modo estudio, con el corte de red) | QA |
| **Vie 9** | Repetir lo corregido, extras de HP-01 (Pitágoras, SVG, simulaciones con el dedo) y decidir | QA + desarrollo + producto |

**Avance real al 2026-10-08:** HP-04, HP-01 y HP-03 hechos; falta **HP-02** y el escenario transversal **ESC-05-01** (red y carga con 25 y 35 tabletas).

**Decisiones que conviene tomar el lunes**

1. ¿HP-04 se prueba con sesión obligatoria? (recomendado) ¿Se acepta que el menú no cambie por rol esta semana?
2. ¿El examen se aplica por API esta semana o se construye antes la entrada en OPS (QA-01)?
3. ¿`drag_drop` entra en el alcance o se acepta como brecha (QA-07)?
4. ¿Qué se prueba: la compilación de `main` o el instalador 2.2.0 (QA-21)?

---

## 11 · Cómo reportar

Una fila por problema, con **qué hiciste, qué esperabas y qué pasó**, y una captura:

| ID | Camino y paso | Qué hice | Qué esperaba | Qué pasó | Gravedad | Evidencia |
|---|---|---|---|---|---|---|
| | HP-0X · paso N | | | | Alta / Media / Baja | captura o log |

- **Alta:** impide terminar el camino o pierde datos. **Media:** se termina, pero con un desvío o algo confuso. **Baja:** detalle visual o de texto.
- Si es un hallazgo de la sección 9, cita su **QA-nn** en vez de abrirlo de nuevo.
- Logs útiles: `backend\logs` o tu carpeta de `AVACOM_LMS_DIR_LOGS`, `%LOCALAPPDATA%\AVACOM\lms\fallos-ops.log` y `fallos-student.log`, y los registros de Contenido en `C:\ProgramData\AVACOM\content\logs`.

**Un camino queda aprobado** cuando todos sus pasos pasan, o cuando lo que falla está en la sección 9 y tiene desvío acordado.

---

## 12 · Anexo · contenido instalado

| Curso | Grado | Lecciones de clase | Examen (estrategia · preguntas por alumno · banco · tiempo) |
|---|---|---|---|
| **Estados de la materia y sus cambios** | 6.º | 2 | `random_balanced` · 6 · 18 · 6 min |
| Teoremas de Pitágoras y Tales | 8.º | 6 | `random_balanced` · 12 · 80 · 40 min |
| Fracciones: partes de un todo | 4.º | 1 | `random_balanced` · 4 · 12 · 4 min |
| Algoritmos | 9.º | 4 | `random_balanced` · 6 · 18 · 7 min |
| Lectura crítica de medios | 10.º | 4 | `random_balanced` · 6 · 18 · 7 min |
| Las vocales | Transición | 1 | sin examen |
| The U.S. Constitution (inglés) | 8.º | 2 | `fixed` · todas · 8 · 40 min |

**Cinco tipos de objeto** en 99 objetos: presentación (20), lectura (17), laboratorio (22), actividad (34) y examen (6). **Cinco tipos de medio:** imagen, video, audio, PDF y simulación. **Siete tipos de pregunta:** opción múltiple, verdadero/falso, completar, relacionar, ordenar, abierta y `drag_drop`.

**Roles y permisos** (65 permisos en total): alumno 19 (todos sobre sí mismo), profesor 42 (sobre sus grupos), administrador 54 (toda la organización), reportes 10 (sólo lectura) y técnico 6 (dispositivos, sesiones y diagnóstico).
