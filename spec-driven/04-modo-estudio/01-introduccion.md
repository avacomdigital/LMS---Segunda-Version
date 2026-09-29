# Objetivo del Módulo
Es el producto cuando no hay profesor delante. Sirve el contenido autorizado al alumno, le deja practicar con retroalimentación inmediata, guarda lo que hace y lo entrega cuando el aparato vuelve a estar en la red del aula. Solo opera en dispositivos asignados a una persona, porque un paquete descargado en un aparato compartido sería accesible al siguiente alumno.

MOD-008 · Modo Estudio

Todo el módulo falta: 0 de 10 eventos, 0 permisos study.* y 0 pruebas.

## Incluye
Catálogo autorizado por inscripción; práctica autocalificable con retroalimentación; continuación y reanudación; consulta de progreso propio.

## Queda fuera
Evaluaciones formales de nivel examen. Las recomendaciones, de MOD-012. El acceso a contenido no autorizado.

#	Requerimiento	Dominio	Tabla	OPS	Student
008-01	Solo en dispositivo asignado (BR-054, DEC-013, FUN-084/085)	Gestión de dispositivos	Columnas perfil y asignado_a_id en dispositivo (009-06)	Marcar asignado o compartido al enrolar	Hexágono «Modo de estudio» solo si el aparato es del alumno. PAN-133 «descarga denegada»
008-02	Asignar trabajo con fecha límite a un alumno o al grupo (CAP-050/051, DEC-014, DEC-019)	Evaluación	Nueva asignacion. lanzamiento no sirve porque exige clase_id	Crear asignación y ver «quién completó». Hoy Estudiantes y Progreso son placeholders	Pendientes con fechas (PAN-130) y tarea con consigna, límite y gracia (PAN-131)
008-03	Paquete de estudio descargable (CAP-047). Estados: solicitado, descargándose, disponible, vencido, denegado	Evaluación	Nueva paquete_estudio (alumno, dispositivo, asignación, estado, vigencia, huella)	Estado del paquete por alumno	Descarga reanudable, almacenamiento local cifrado, vigencia y espacio (MSG-045). Hoy no guarda nada del curso
008-04	Abrir lección asignada y completarla (FUN-081/082/087/088)	Evaluación	No (progreso)	—	Completar por bloques obligatorios. Hoy el cierre manda siempre progreso_pct=100. Reanudar en el último punto
008-05	Práctica autocalificable separada de la evaluación formal (FUN-083, BR-055, NFR-012 ≤2 s)	Evaluación	Columnas: intento con asignacion_id alternativo a lanzamiento_id (hoy obligatorio) y modo	—	Componentes de respuesta para los 10 tipos (DEC-004), limitados por nivel. Hoy solo respuesta corta
008-06	Trabajo sin red que se integra sin duplicar ni exigir sesión (CAP-048, FUN-086, BR-059/060/137/138, TST-029)	Actividad del alumno	No. Riesgo: con las respuestas en JSON (decisión del CTO), INV-013 no puede ser constraint. Hay que validarlo en transacción y probarlo con reenvíos	Ver «pendiente de envío» por alumno	Cola local cifrada, secuencia persistida antes de enviar, estado de guardado de 3 valores (CMP-002). Hoy las escrituras se pierden si fallan
008-07	Cerrar sesión de estudio y limpiar el aparato (BR-053, FUN-089/090, TST-028). La mecánica está en 009-07	Gestión de dispositivos	Ver 009-07	—	«Salir» debe cerrar sesión en el servidor y borrar lo local. Hoy no lo hace. Riesgo observado: otro alumno en la misma tableta es readmitido con el participante del anterior
008-08	Permisos study.* (6) y eventos estudio.* (10)	Acceso y RBAC	No	Ocultar lo que el rol no puede	—
008-09	Alcance por nivel y vista «Mi trabajo» (PAN-124, DEC-032)	Acceso y RBAC	En v2 no hay dónde guardar la configuración por nivel (DEC-017). Preguntar al CTO	—	PAN-124. Revisar la barra de % de «Asignaturas» contra DEC-032


## Descripción Backend

El backend de este módulo debe correr en la app de ./backend/modo-estudio, llamado en DRF cómo modo-estudio.

Para ./backend/modo-estudio yo no lo trataría como un CRUD aislado, sino como una app orquestadora de Modo Estudio dentro del monolito DRF. El documento maestro deja bastante claro que MOD-008 consume información de Asignacion, Dispositivo, Leccion, Progreso, Intento, Respuesta, Archivo, EventoDeCola, Usuario, etc., en lugar de ser dueño absoluto de esas entidades. AVACOM_LMS_Documento_Maestro_Co…
Las funciones backend más importantes que encontré serían estas:
1. Listar el trabajo disponible del estudiante
   - Obtener asignaciones pendientes.
   - Filtrar por estudiante/grupo.
   - Incluir fecha límite, estado, progreso y disponibilidad offline.
   - Corresponde directamente a FUN-081 y a la capacidad de mostrar pendientes y fechas límite. AVACOM_LMS_Documento_Maestro_Co… AVACOM_LMS_Documento_Maestro_Co…
   Endpoint sugerido:
   GET /api/modo-estudio/asignaciones/
2. Abrir una lección asignada
   Antes de devolver contenido, validar que:
   - la lección esté publicada;
   - esté realmente asignada al estudiante;
   - el usuario tenga permiso study.lesson.open.
   Esto corresponde a FUN-082. AVACOM_LMS_Documento_Maestro_Co…
   GET /api/modo-estudio/lecciones/{id}/
3. Reanudar la lección desde el último punto
   El backend debería devolver el último progreso válido:
   {
     "lesson_id": "...",
     "progress_pct": 62,
     "last_block_id": "...",
     "resume_position": 4,
     "can_resume": true
   }
   
   FUN-088 exige poder reanudar una actividad cuando existe un punto de recuperación. AVACOM_LMS_Documento_Maestro_Co…
4. Registrar progreso por bloques
   Esta me parece de las funciones más importantes.
   No debería existir únicamente algo como:
   progreso_pct = 100
   
   
   al cerrar la lección.
   El backend debe poder registrar:
   - bloque visto;
   - actividad realizada;
   - posición actual;
   - porcentaje;
   - bloques obligatorios completados;
   - timestamp del último avance.
   Porque el requisito establece que la lección se completa cuando todos los bloques obligatorios han sido atendidos, no simplemente cuando el alumno sale de la pantalla. AVACOM_LMS_Documento_Maestro_Co…
   Por ejemplo:
   PATCH /api/modo-estudio/lecciones/{id}/progreso/
5. Completar una lección
   Servicio específico:
   complete_lesson(student, lesson)
   
   
   Que valide:
   if not all_required_blocks_completed:    raise ValidationError(...)
   
   
   y solo después genere el evento conceptual:
   estudio.leccion.completada.v1
   
   Esto corresponde a FUN-087 y study.lesson.complete. AVACOM_LMS_Documento_Maestro_Co…
6. Gestionar paquetes de descarga para estudio offline
   Esta probablemente sea la parte más propia de modo-estudio.
   El documento define estos estados:
   solicitado
   descargándose
   disponible
   vencido
   denegado
   
   AVACOM_LMS_Documento_Maestro_Co…
   Yo lo expondría como:
   POST /api/modo-estudio/paquetes/
   GET  /api/modo-estudio/paquetes/{id}/
   DELETE /api/modo-estudio/paquetes/{id}/
   
   Con un servicio:
   StudyPackageService
   
   
   responsable de:
   request_package()validate_download_permission()prepare_manifest()mark_downloading()mark_available()expire_package()deny_package()
7. Validar si el dispositivo puede descargar
   Esta regla es crítica:
   La descarga para trabajar sin el nodo solo se permite en dispositivos asignados nominalmente; no en dispositivos compartidos. AVACOM_LMS_Documento_Maestro_Co…
   
   Por eso debería existir algo parecido a:
   can_download_study_package(    student=user,    device=device)
   
   
   Internamente:
   if device.perfil == DeviceProfile.SHARED:    raise StudyPackageDownloadDenied(...)
   
   
   Esto cubre FUN-084 y FUN-085. AVACOM_LMS_Documento_Maestro_Co…
8. Generar el manifest del contenido descargable
   En lugar de devolver un ZIP sin información, yo tendría un manifest:
   {
     "package_id": "uuid",
     "assignment_id": "uuid",
     "lesson_id": "uuid",
     "expires_at": "2026-10-05T23:59:59Z",
     "checksum": "...",
     "files": [
       {
         "id": "...",
         "type": "pdf",
         "size": 3829482,
         "hash": "..."
       }
     ]
   }
   
   Esto encaja con el requisito de paquete de estudio con vigencia y huella.    Markdown pegado (2)
9. Registrar respuestas de práctica
   FUN-083 indica que el estudiante puede responder actividades del Modo Estudio. AVACOM_LMS_Documento_Maestro_Co…
   Endpoint:
   POST /api/modo-estudio/practicas/{id}/respuestas/
   
   El backend debería:
   - validar la respuesta;
   - guardar el intento/práctica;
   - calcular resultado;
   - devolver feedback;
   - hacerlo sin afectar una evaluación formal.
10. Separar práctica de evaluación formal
       Esta no es solo una decisión visual; debe estar protegida por backend.
   BR-055 dice explícitamente que la práctica de Modo Estudio no consume ni modifica intentos de evaluación formal. AVACOM_LMS_Documento_Maestro_Co…
   Yo pondría algo como:
class AttemptMode(models.TextChoices):    FORMAL = "formal"    STUDY = "study"


   o conceptualmente:
submit_study_answer(...)


   distinto de:
submit_formal_assessment_answer(...)


   Nunca reutilizar silenciosamente el flujo formal.
11. Autocalificar la práctica
       El flujo sería:
answer = validate_answer(...)result = grade_study_answer(answer)feedback = build_feedback(result)


   y responder:
{
  "correct": true,
  "score": 1,
  "feedback": "Correcto",
  "attempt_score": 7,
  "total_questions": 8
}

   El documento describe la práctica autocalificable con retroalimentación inmediata como una salida propia del módulo. AVACOM_LMS_Documento_Maestro_Co…
12. Recibir trabajo realizado offline
       Esta es otra función crítica:
POST /api/modo-estudio/sync/

   El cliente MAUI puede enviar eventos pendientes:
{
  "device_id": "...",
  "events": [
    {
      "sequence": 1041,
      "type": "study.answer.submitted",
      "occurred_at": "...",
      "payload": {}
    }
  ]
}

   El backend tiene que poder integrarlos sin duplicar respuestas o intentos. El documento lo define como una capacidad explícita del módulo. AVACOM_LMS_Documento_Maestro_Co…
13. Idempotencia
       Yo consideraría esta función obligatoria:
process_offline_event_once(...)


   Si MAUI manda dos veces:
sequence = 1041

   el servidor no debe registrar la misma respuesta dos veces.
   El requisito precisamente habla de integrar el trabajo offline sin duplicación.    Markdown pegado (2)
14. Estado de sincronización
       Backend debería poder informar:
synced
pending
rejected
conflict

   Por ejemplo:
GET /api/modo-estudio/sync/status/

15. Permisos específicos study.*
       El módulo necesita al menos:
study.open
study.assignment.read
study.lesson.open
study.lesson.complete
study.answer.submit
study.package.download

   Son los permisos definidos por MOD-008. AVACOM_LMS_Documento_Maestro_Co…
Cómo lo organizaría en backend/modo_estudio
Evitaría poner todo dentro de views.py.
backend/
└── modo_estudio/
    ├── __init__.py
    ├── apps.py
    ├── urls.py
    ├── models.py
    │
    ├── api/
    │   ├── serializers.py
    │   ├── views.py
    │   ├── permissions.py
    │   └── filters.py
    │
    ├── services/
    │   ├── assignment_service.py
    │   ├── lesson_service.py
    │   ├── study_package_service.py
    │   ├── study_practice_service.py
    │   └── study_sync_service.py
    │
    ├── selectors/
    │   ├── assignment_selectors.py
    │   ├── lesson_selectors.py
    │   └── package_selectors.py
    │
    ├── domain/
    │   ├── enums.py
    │   ├── exceptions.py
    │   └── rules.py
    │
    └── tests/
        ├── test_assignments.py
        ├── test_lessons.py
        ├── test_downloads.py
        ├── test_practice.py
        └── test_sync.py

views.py debería ser delgado
Por ejemplo:
class CompleteLessonAPIView(APIView):    permission_classes = [CanCompleteStudyLesson]    def post(self, request, pk):        result = StudyLessonService.complete(            student=request.user,            lesson_id=pk,        )        return Response(            StudyLessonSerializer(result).data        )


Y la lógica real:
class StudyLessonService:    @classmethod    def complete(cls, *, student, lesson_id):        lesson = get_assigned_lesson(            student=student,            lesson_id=lesson_id,        )        progress = get_lesson_progress(            student=student,            lesson=lesson,        )        if not progress.required_blocks_completed:            raise LessonNotCompletedError()        progress.mark_completed()        progress.save()        return progress


Los 5 servicios que yo consideraría núcleo del módulo
Si tuvieras que empezar por pocos archivos, serían:
StudyAssignmentService
    └── pendientes del estudiante

StudyLessonService
    ├── open
    ├── resume
    ├── update_progress
    └── complete

StudyPackageService
    ├── request
    ├── authorize
    ├── manifest
    ├── expire
    └── status

StudyPracticeService
    ├── start
    ├── submit_answer
    ├── grade
    └── retry

StudySyncService
    ├── ingest_events
    ├── deduplicate
    ├── integrate
    └── acknowledge

Y conceptualmente el flujo completo del backend quedaría:
MAUI
  │
  ▼
modo_estudio/api
  │
  ▼
modo_estudio/services
  │
  ├──── Asignaciones
  ├──── Lecciones
  ├──── Progreso
  ├──── Evaluaciones / práctica
  ├──── Dispositivos
  ├──── Archivos
  └──── Cola / sincronización

La clave aquí es que modo_estudio coordina esos dominios, pero no debería duplicar los modelos maestros que ya pertenecen a otras apps. Esa separación encaja particularmente bien con el documento: el módulo produce la experiencia de estudio, pero consume datos y capacidades de otras partes del LMS.

## Descripción Frontend

Actúa como un Senior UI/UX Designer especializado en productos educativos y como Senior .NET MAUI Frontend Engineer.

Necesito diseñar e implementar en .NET MAUI una pantalla llamada:

"Modo Estudio · Mis lecciones"

Esta pantalla pertenece a AVACOM LMS y debe tomar como referencia visual una interfaz existente del LMS donde se abre un modal central sobre la pantalla de la asignatura.

============================================================
1. OBJETIVO DE LA PANTALLA
============================================================

Crear una interfaz desde la cual un estudiante pueda:

1. Ver las lecciones disponibles dentro del Modo Estudio.
2. Identificar rápidamente cuáles tiene pendientes, en curso o completadas.
3. Descargar contenido para trabajar offline.
4. Visualizar el progreso de una descarga que esté actualmente en curso.
5. Abrir una lección asignada.
6. Reanudar una lección desde el último punto guardado.
7. Completar una lección.
8. Acceder a prácticas autocalificables.
9. Diferenciar claramente una práctica de estudio de una evaluación formal.
10. Trabajar correctamente en tabletas Windows/Android con .NET MAUI.

La pantalla debe sentirse como una evolución natural del diseño actual de AVACOM LMS.

NO crear un dashboard completamente distinto.
NO utilizar una estética empresarial tipo ERP.
NO convertir la interfaz en una tabla.
Debe sentirse como una aplicación educativa moderna, ligera y táctil.

============================================================
2. REFERENCIA VISUAL PRINCIPAL
============================================================

Usar como referencia el modal existente mostrado en el prototipo, para AVACOM STUDENT:

- Fondo de la pantalla principal desenfocado y ligeramente oscurecido.
- Modal/card principal blanco.
- Modal centrado.
- BorderRadius aproximado de 22–28 px.
- Sombra muy suave.
- Mucho espacio en blanco.
- Encabezado superior limpio.
- Botón X circular en la esquina superior derecha.
- Separadores extremadamente suaves.
- Filas amplias diseñadas para interacción táctil.
- Estados mediante pequeños chips/pills.
- Iconografía lineal sencilla.
- Jerarquía tipográfica fuerte.

No copiar literalmente el contenido del prototipo anterior:
adaptarlo específicamente a Modo Estudio.

En AVACOM OPS LMS se debe crear una pantalla para poder asignar los recursos de estudio a los estudiantes (es decir en AVACOM STUDENT)

============================================================
3. ESTRUCTURA PRINCIPAL
============================================================

Mostrar un modal/panel central aproximadamente:

Width:
min(1050 px, 88% del ancho disponible)

Height:
aproximadamente 75–82% del área disponible.

En tablet utilizar la mayor parte del espacio disponible pero mantener márgenes exteriores generosos.

Estructura:

┌───────────────────────────────────────────────────────┐
│  Modo estudio                              [ X ]       │
│  Continúa aprendiendo a tu ritmo                       │
│                                                       │
│  [ Pendientes ] [ Descargadas ] [ Completadas ]       │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │ LECCIÓN 1                                       │  │
│  │ ...                                             │  │
│  ├─────────────────────────────────────────────────┤  │
│  │ LECCIÓN 2                                       │  │
│  │ ...                                             │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│              almacenamiento / sincronización          │
└───────────────────────────────────────────────────────┘

============================================================
4. HEADER
============================================================

Parte superior:

Título principal:

"Modo estudio"

font-size aproximado:
22–26 px

font-weight:
700

Debajo:

"Continúa tus lecciones asignadas incluso cuando estés sin conexión."

Color gris secundario.

En el extremo derecho:

botón circular X para cerrar.

El botón debe:

- tener aproximadamente 40x40 px;
- fondo blanco;
- borde gris #E5E5E5;
- hover/pressed muy sutil;
- área táctil mínima apropiada para tablet.

============================================================
5. FILTROS / SEGMENTED CONTROL
============================================================

Debajo del encabezado agregar un segmented control:

[ Pendientes 3 ] [ Descargadas 2 ] [ Completadas 5 ]

Estilo similar a los pills utilizados por AVACOM.

Estado seleccionado:

fondo:
#1D1D1F

texto:
#FFFFFF

Estado normal:

fondo:
#F5F5F7

texto:
#5F6368

BorderRadius:
18–22 px.

NO utilizar tabs tradicionales con underline.

============================================================
6. LISTADO DE LECCIONES
============================================================

Implementar mediante CollectionView de .NET MAUI.

Cada elemento debe ser una tarjeta/fila grande.

No usar ListView legado.

Cada lección debe mostrar:

- asignatura;
- unidad;
- nombre de la lección;
- descripción corta opcional;
- fecha límite;
- progreso;
- estado;
- estado de descarga;
- acción principal.

Ejemplo visual:

┌──────────────────────────────────────────────────────────────┐
│ LENGUA CASTELLANA · UNIDAD 2                         EN CURSO │
│                                                               │
│ Área y volumen con lenguaje algebraico                       │
│ Continúa desde: Actividad 4 de 7                             │
│                                                               │
│ ████████████████░░░░░░░░                         62 %         │
│                                                               │
│ ⏱ Entrega: 4 oct.                   [ Continuar lección → ]   │
│                                                               │
│ ✓ Disponible sin conexión                                    │
└──────────────────────────────────────────────────────────────┘

============================================================
7. JERARQUÍA DE INFORMACIÓN
============================================================

Eyebrow:

"LENGUA CASTELLANA · UNIDAD 2"

uppercase
font-size 11–12
font-weight 700
letter-spacing ligero
color gris.

Título:

"Área y volumen con lenguaje algebraico"

font-size:
17–19 px

font-weight:
650–700

Descripción:

"Continúa desde: Actividad 4 de 7"

font-size:
13–14 px

color:
#6E6E73

No saturar visualmente la tarjeta.

============================================================
8. ESTADOS DE LECCIÓN
============================================================

Crear chips visuales consistentes.

Estados:

PENDIENTE

fondo:
#FFF7D6

texto:
#806600


EN CURSO

fondo:
#E5F5FB

texto:
#02739E


COMPLETADA

fondo:
#E5F6ED

texto:
#017A48


VENCIDA

fondo:
rgba(229,38,43,0.10)

texto:
#C1191D


Los chips deben tener:

BorderRadius 999
padding horizontal 10–12
padding vertical 4–6
font-size 11–12
font-weight 600.

============================================================
9. PROGRESO DE LECCIÓN
============================================================

Para una lección comenzada mostrar una barra horizontal:

altura:
6–8 px

background:
#E9E9E9

progress:
#019D60

BorderRadius:
999

Mostrar a la derecha:

"62 %"

No marcar automáticamente una lección como completada simplemente porque se cierre.

La interfaz debe contemplar que la lección solo pueda considerarse completada cuando hayan sido realizados los bloques obligatorios.

============================================================
10. DESCARGA OFFLINE
============================================================

Esta es una sección especialmente importante.

Una lección debe poder mostrar diferentes estados de descarga:

- No descargada
- Solicitada
- Descargando
- Disponible sin conexión
- Descarga pausada
- Vencida
- Denegada

------------------------------------------------------------
ESTADO: NO DESCARGADA
------------------------------------------------------------

Mostrar botón secundario:

[ ↓ Descargar ]

Al lado indicar tamaño:

"84 MB"

------------------------------------------------------------
ESTADO: DESCARGANDO
------------------------------------------------------------

Cambiar la sección automáticamente a:

↓ Descargando contenido...

████████████░░░░░░░░     64 %

54 MB de 84 MB

Mostrar además acción:

[ Pausar ]

Opcionalmente:

"2 min restantes"

NO utilizar un spinner como única indicación del proceso.

Utilizar:

- indicador de progreso determinado;
- porcentaje;
- cantidad descargada;
- estado textual.

Puede acompañarse por un spinner muy pequeño,
pero la información principal debe ser la barra de progreso.

------------------------------------------------------------
ESTADO: DISPONIBLE
------------------------------------------------------------

Mostrar:

✓ Disponible sin conexión

con icono verde.

Acción secundaria:

[ ⋯ ]

para:

- Ver información
- Eliminar descarga

------------------------------------------------------------
ESTADO: PAUSADO
------------------------------------------------------------

Mostrar:

Descarga pausada · 64 %

[ Continuar descarga ]

------------------------------------------------------------
ESTADO: VENCIDO
------------------------------------------------------------

Mostrar:

"El contenido descargado venció."

[ Actualizar descarga ]

------------------------------------------------------------
ESTADO: DENEGADO
------------------------------------------------------------

Mostrar:

"Este dispositivo no permite descargar contenido para estudiar sin conexión."

No mostrar botón Descargar.

============================================================
11. INDICADOR GLOBAL DE DESCARGAS
============================================================

Cuando haya descargas activas, mostrar en la parte inferior del modal una barra discreta:

┌─────────────────────────────────────────────────────────┐
│ ↓ Descargando 2 lecciones                  68 %          │
│ ██████████████████░░░░░░░                              │
└─────────────────────────────────────────────────────────┘

Debe poder permanecer visible mientras el usuario navega por el listado.

No bloquear toda la UI durante una descarga.

============================================================
12. ABRIR / REANUDAR LECCIÓN
============================================================

Estados del CTA:

Si nunca fue iniciada:

[ Comenzar lección → ]

Si ya existe progreso:

[ Continuar lección → ]

Si existe punto de recuperación:

mostrar debajo del título:

"Continuarás donde quedaste"

o

"Último avance: Actividad 4 · 03:28"

Si está completada:

[ Ver lección ]

y adicionalmente:

✓ Lección completada

============================================================
13. PRÁCTICA AUTOCALIFICABLE
============================================================

Dentro de cada lección puede aparecer una sección separada:

PRÁCTICA

Ejemplo:

┌──────────────────────────────────────────────────┐
│ ✦ Práctica                                       │
│ Comprueba lo aprendido                           │
│                                                  │
│ 8 preguntas · Autocalificable                    │
│                                                  │
│ [ Practicar → ]                                  │
└──────────────────────────────────────────────────┘

Debe distinguirse visualmente del contenido normal.

Utilizar un pequeño accent:

#01A4E1

pero evitar llenar toda la tarjeta de azul.

============================================================
14. REGLA CRÍTICA: PRÁCTICA ≠ EVALUACIÓN
============================================================

Nunca presentar la práctica como:

"Examen"

"Evaluación"

"Evaluación formal"

"Nota definitiva"

La práctica del Modo Estudio debe aparecer explícitamente como:

"Práctica"

"Práctica de estudio"

"Comprueba lo aprendido"

"Puedes intentarlo nuevamente"

Después de responder una práctica:

mostrar resultado inmediatamente:

"7 de 8 correctas"

"¡Muy bien!"

y permitir:

[ Revisar respuestas ]

[ Intentar nuevamente ]

La retroalimentación debe mostrarse en máximo 2 segundos desde la acción del estudiante.

IMPORTANTE:

Esta práctica NO debe consumir,
modificar,
ni reutilizar visualmente un intento de evaluación formal.

Debe tratarse como actividad de aprendizaje independiente.

============================================================
15. EVALUACIÓN FORMAL
============================================================

Si dentro de la unidad existe una evaluación formal,
separarla completamente de la práctica.

Usar una tarjeta/section diferente:

EVALUACIÓN

Evaluación de la Unidad 2
Disponible desde el 20 de octubre

[ Ver información ]

NO utilizar el mismo botón "Practicar".

NO mostrarla dentro de la tarjeta de práctica.

La separación conceptual y visual tiene que ser evidente incluso para un niño.

============================================================
16. FECHAS Y PENDIENTES
============================================================

Mostrar la fecha límite con icono Clock.

Ejemplos:

Entrega: hoy, 4:00 p. m.

Entrega: mañana

Entrega: 4 oct.

Si está próxima:

chip:

"Vence hoy"

Si está vencida:

"Vencida"

Evitar mensajes alarmistas.

============================================================
17. ESTADO OFFLINE
============================================================

La interfaz debe ser offline-first.

En la parte superior o inferior puede existir un indicador discreto:

● Sin conexión

pero NO bloquear el contenido descargado.

Cuando el dispositivo está offline:

los elementos descargados siguen habilitados.

Mostrar:

"Disponible sin conexión"

Las acciones que requieren sincronización deben poder quedar:

"Pendiente de enviar"

Ejemplo:

☁ Pendiente de sincronización

No mostrar errores técnicos al estudiante.

============================================================
18. SINCRONIZACIÓN
============================================================

Implementar visualmente tres estados sencillos:

✓ Guardado

↑ Pendiente de enviar

↻ Sincronizando

El estudiante debe poder comprender el estado sin conocer conceptos técnicos.

============================================================
19. ESTADO VACÍO
============================================================

Si no existen tareas:

mostrar una pantalla amable dentro del modal.

Icono lineal de libro/check.

Título:

"Estás al día"

Texto:

"No tienes lecciones pendientes en modo estudio."

Acción opcional:

[ Ver lecciones completadas ]

No mostrar una pantalla vacía blanca.

============================================================
20. DISEÑO AVACOM
============================================================

Usar principalmente:

AVACOM Red
#E5262B

AVACOM Blue
#01A4E1

AVACOM Green
#019D60

AVACOM Yellow
#F3C701

Background:
#FFFFFF
#F5F5F7
#FBFBFD

Texto principal:
#1D1D1F

Texto secundario:
#6E6E73

Borders:
#E8E8ED

No utilizar todos los colores simultáneamente en una misma tarjeta.

Los colores deben comunicar estados y jerarquía,
no decorar arbitrariamente.

============================================================
21. ESTÉTICA
============================================================

La interfaz debe sentirse:

- moderna;
- educativa;
- limpia;
- amable;
- ligera;
- premium;
- sencilla para estudiantes;
- preparada para pantalla táctil.

Inspiración visual:

Apple Education
Duolingo en jerarquía de acciones
interfaces educativas modernas
AVACOM LMS existente

pero sin copiar directamente ninguna de ellas.

Mantener abundante espacio negativo.

============================================================
22. .NET MAUI — IMPLEMENTACIÓN
============================================================

Implementar utilizando XAML + MVVM.

NO colocar toda la lógica en code-behind.

Crear aproximadamente:

Views/
    StudyModePage.xaml
    StudyModePage.xaml.cs

ViewModels/
    StudyModeViewModel.cs

Models/
    StudyLessonItem.cs
    StudyDownloadState.cs
    StudyLessonState.cs
    StudyPractice.cs

Services/
    IStudyModeService.cs
    IDownloadService.cs
    IConnectivityService.cs

Converters/
    LessonStateToColorConverter.cs
    DownloadStateToTextConverter.cs
    ProgressToWidthConverter.cs

Styles/
    StudyModeStyles.xaml

============================================================
23. COLLECTIONVIEW
============================================================

Utilizar:

<CollectionView>

con:

SelectionMode="None"

y DataTemplate mediante x:DataType para compiled bindings.

Ejemplo conceptual:

CollectionView
└── DataTemplate
    └── Border
        └── Grid
            ├── información
            ├── status
            ├── progress
            ├── download
            └── actions

No crear manualmente 10 tarjetas repetidas en XAML.

============================================================
24. MODELO DE DATOS PARA LA UI
============================================================

Crear un ViewModel/model similar a:

StudyLessonItem

Id
Subject
UnitName
Title
Description
DueDate
Progress
CompletedBlocks
TotalBlocks
State
DownloadState
DownloadProgress
DownloadedBytes
TotalBytes
IsAvailableOffline
HasPractice
PracticeQuestionCount
PracticeBestScore
CanResume
ResumeLabel
IsPendingSync

Estados posibles:

StudyLessonState
{
    Pending,
    InProgress,
    Completed,
    Expired
}

StudyDownloadState
{
    None,
    Requested,
    Downloading,
    Paused,
    Available,
    Expired,
    Denied
}

============================================================
25. COMMANDS
============================================================

Implementar Commands MVVM:

OpenLessonCommand

ResumeLessonCommand

DownloadLessonCommand

PauseDownloadCommand

ResumeDownloadCommand

DeleteDownloadCommand

OpenPracticeCommand

RetryPracticeCommand

OpenCompletedLessonCommand

FilterLessonsCommand

CloseStudyModeCommand

No utilizar Clicked handlers innecesarios.

============================================================
26. DESCARGAS ASÍNCRONAS
============================================================

Las descargas NO deben bloquear el hilo de interfaz.

Utilizar async/await.

El ViewModel debe reaccionar a cambios de:

DownloadProgress

DownloadState

DownloadedBytes

La UI debe actualizarse progresivamente.

No utilizar bucles activos en UI.

============================================================
27. RESPONSIVIDAD
============================================================

Pensar primero en:

1920x1080

pero debe funcionar correctamente también en:

1366x768
1280x800
tabletas 10"
tabletas Android

Usar Grid y layouts responsivos.

NO depender de posiciones absolutas.

NO diseñar con AbsoluteLayout para toda la pantalla.

Evitar anchos rígidos salvo MaxWidthRequest.

============================================================
28. SCROLL
============================================================

El encabezado y segmented control deben permanecer visibles.

Solo la lista central de lecciones debe hacer scroll.

La barra global de descargas puede permanecer fija en la parte inferior.

Arquitectura:

Grid

Row 0 → Header
Row 1 → Filters
Row 2 → CollectionView (*)
Row 3 → Download status / sync

============================================================
29. MICROINTERACCIONES
============================================================

Agregar animaciones muy discretas:

Press:
Scale 1 → 0.98 → 1

Cambio de progreso:
animación suave

Aparición de tarjeta:
Fade 150–200 ms

Descarga completada:

barra llega a 100%
↓
pequeño fade
↓
✓ Disponible sin conexión

No utilizar animaciones exageradas.

============================================================
30. LOADING / SKELETON
============================================================

Cuando se cargan las lecciones:

NO mostrar simplemente un spinner gigante.

Crear skeletons de aproximadamente 3 filas.

Cada skeleton:

- línea pequeña para asignatura;
- línea grande para título;
- línea mediana;
- progress placeholder.

Puede existir además un spinner pequeño como indicador auxiliar.

============================================================
31. ACCESIBILIDAD
============================================================

Agregar SemanticProperties.Description.

Ejemplos:

"Área y volumen, progreso 62 por ciento."

"Descarga de Área y volumen, 64 por ciento completada."

"Práctica de estudio, 8 preguntas."

Mantener targets táctiles de mínimo aproximadamente 44–48 dp.

No depender exclusivamente del color para indicar un estado.

Usar siempre:

icono + texto + color.

============================================================
32. RENDIMIENTO
============================================================

La interacción local debe sentirse inmediata.

La retroalimentación de la práctica autocalificable debe aparecer en <= 2 segundos.

Evitar:

- layouts anidados innecesarios;
- múltiples ScrollView;
- imágenes pesadas;
- recrear toda la CollectionView durante un cambio de progreso.

Usar ObservableCollection y actualizar únicamente el elemento afectado.

============================================================
33. EJEMPLOS DE DATOS MOCK
============================================================

Incluir por lo menos estos casos:

1.
Lengua Castellana
Unidad 2
"Área y volumen con lenguaje algebraico"
62 %
En curso
Disponible offline
Tiene práctica
Entrega mañana

2.
Lengua Castellana
Unidad 2
"Geometría y medida"
0 %
Pendiente
No descargada
84 MB
Tiene práctica

3.
Lengua Castellana
Unidad 3
"Literatura latinoamericana"
35 %
En curso
Descargando 64 %
54 MB / 84 MB

4.
Lengua Castellana
Unidad 1
"Textos argumentativos"
100 %
Completada
Disponible offline

5.
Lengua Castellana
Unidad 3
"Análisis de textos"
Pendiente
Descarga denegada

Esto permitirá validar visualmente todos los estados.

============================================================
34. RESULTADO ESPERADO
============================================================

Entrega código funcional y organizado para .NET MAUI.

Generar:

1. StudyModePage.xaml
2. StudyModePage.xaml.cs
3. StudyModeViewModel.cs
4. StudyLessonItem.cs
5. Enums de estados
6. Converters necesarios
7. StudyModeStyles.xaml
8. Datos mock para visualizar inmediatamente la página
9. Commands necesarios
10. Manejo simulado de una descarga progresiva
11. Estado de sincronización
12. Práctica autocalificable simulada

El resultado debe compilar o quedar lo más cercano posible a código compilable.

No entregar pseudocódigo como sustituto de XAML.

No reemplazar el diseño solicitado por controles MAUI básicos sin personalización.

La pantalla final debe conservar la identidad visual del prototipo AVACOM mostrado como referencia.