# PROMPT MAESTRO — PROTOTIPO MOD-007 · CLASSROOM ENGINE

Actúa como arquitecto de software senior especializado en Django Rest Framework, arquitectura limpia/hexagonal, sistemas offline-first y aplicaciones .NET C# MAUI con MVVM.

Tu objetivo es diseñar y estructurar un prototipo técnico completo exclusivamente para el módulo MOD-007 · Classroom Engine de AVACOM LMS / AVACOM OPS.

No debes diseñar el LMS completo.

No debes implementar internamente módulos distintos de MOD-007.

Cuando MOD-007 necesite capacidades de otros módulos, debes representarlas exclusivamente mediante interfaces, puertos, gateways, DTOs, eventos o servicios externos.

## DOCUMENTOS DE CONTEXTO

Analiza primero los siguientes archivos antes de proponer cualquier arquitectura:

AVACOM_LMS_Documento_Maestro_Consolidado_v1.0
AVACOM_LMS_Arquitectura_y_Datos_v1.0

00-linea-base-conexion-biblioteca.md 
01-constitucion.md 
06-contrato-biblioteca.md

course_example.json

Usa los documentos con la siguiente prioridad cuando exista una contradicción:

1. Restricciones indicadas en este prompt
2. 01-constitucion.md
3. Contrato vigente descrito en 00-linea-base-conexion-biblioteca.md
4. 06-contrato-biblioteca.md, teniendo en cuenta que contiene propuestas aún no necesariamente ratificadas
5. Especificación funcional de MOD-007 en Documento Maestro
6. Modelo de datos existente en Arquitectura y Datos
7. course_example.json como ejemplo orientativo, nunca como contrato rígido

# Aplicación LMS

Se entiende por aplicación del LMS, existe una aplicación maestra:
- LMS OPS 
- LMS Student

Se debe comprender que el LMS OPS usa el backend para emitir todas sus respuestas en el 0.0.0.0 en el puerto 8000

#Componentes que se reciben en el contenido

Se reciben varios objetos que estos deben reflejarse en el frontend de C# .NET:
	1. Presentaciones (tipo pptx)
	2- Audios
	3. Vídeos 

# Operación del aula 

BR-057	Un dispositivo compartido admite como máximo una sesión de usuario activa a la vez.	fija	MOD-009
BR-059	El dispositivo encola localmente toda escritura no confirmada y la reenvía con secuencia monotónica hasta recibir acuse.	conectividad	MOD-015
BR-060	El equipo del aula descarta como duplicado todo envío cuya clave ya se registró, y responde acuse positivo al dispositivo.	fija	MOD-015
BR-062	Ningún dato con valor académico usa el reloj del dispositivo. La marca temporal autoritativa la asigna el equipo del aula al confirmar la escritura.	fija	MOD-015
BR-137	La entrega de la cola pendiente de un dispositivo no requiere que ese dispositivo tenga una sesión abierta.	fija	MOD-015
BR-138	Cuando llegan escrituras de sesiones distintas para la misma pregunta del mismo intento, prevalece la de la sesión más reciente, con independencia de su orden de llegada.	fija	MOD-010

# El Rol de AVACOM Biblioteca

 Dentro del mismo host se encuentra una aplicación que tiene su propia API, esta entrega unos endpoints para consumir las materias (cursos). 

> En este momento los endpoints se están desarrollando en paralelo por otro programador
> Sin embargo ya existe la estructura de prueba de cómo se ve un curso
> La estructura de ejemplo ya existe

El JSON en el archivo example.json

La idea es que se revise la idea de clasificación:

"classification": {
    "country": "CO",
    "level": {
      "code": "lower_secondary",
      "name": "Básica secundaria",
      "order": 2
    },
    "grade": {
      "code": "6",
      "name": "Sexto",
      "order": 6
    },
    "subject": {
      "code": "science",
      "name": "Ciencias naturales"
    },
    "topic": {
      "code": "states-of-matter",
      "name": "Estados de la materia",
      "order": 2
    }
  }

Cómo se puede observar dentro del JSON, cada materia viene con su respectivo "Subject", este tiene en la clave (key) "name" el nombre de la materia que debería mostrarse cómo opción disponible en el panel de navegación de "asignaturas". 
luego hay que revisar el "level" este viene para segundo de primaria:
"level": {
      "code": "lower_secondary",
      "name": "Básica secundaria",
      "order": 2
    }

El país  "country": "CO" para los que están en Colombia.

Recuerda que el estándar que se maneja es:

| Necesidad                 | Estándar                         | Ejemplo                |
| ------------------------- | -------------------------------- | ---------------------- |
| País                      | **ISO 3166-1**                   | `CO`, `COL`, `170`     |
| División territorial      | **ISO 3166-2**                   | `CO-DC`                |
| Idioma                    | **ISO 639**                      | `es`, `eng`, `spa`     |
| Idioma + país/región      | **BCP 47 / RFC 5646**            | `es-CO`, `en-US`       |


# Componentes del contenido

La estructura más importante para dar las clases son las lecciones, que se ven en la clase. Se pueden ver de esta manera:
 "objects": [
        {
          "id": "l1-lecture",
          "type": "lecture",
          "title": "Todo lo que nos rodea es materia",
          "modes": [
            "class",
            "review",
            "free_learning"
          ],
          "topicRef": "t-states",
          "estimatedDurationSec": 1200,
          "teacherNotes": {
            "tips": [
              "Pida a tres alumnos que nombren un sólido, un líquido y un gas del salón antes de pasar a la segunda lámina."
            ]
          },
          "slides": [
            {
              "id": "l1-lecture-s1",
              "title": "Qué es la materia",
              "estimatedSec": 240,
              "blocks": [
                {
                  "type": "heading",
                  "text": "Qué es la materia",
                  "level": 1
                },
                {
                  "type": "text",
                  "text": "**Materia** es todo lo que tiene masa y ocupa un lugar en el espacio: el pupitre, el agua de tu botella y el aire que respiras.",
                  "style": "definition"
                }
              ]
            },
            {
              "id": "l1-lecture-s2",
              "title": "Tres estados, tres formas de ordenarse",
              "estimatedSec": 420,
              "teacherNotes": {
                "tips": [
                  "Señale cada recipiente y pregunte qué tan libres se mueven las partículas."
                ]
              },
              "blocks": [
                {
                  "type": "image",
                  "mediaId": "img-particles",
                  "caption": "Las mismas partículas, ordenadas de tres maneras."
                },
                {
                  "type": "list",
                  "ordered": false,
                  "items": [
                    "**Sólido:** forma y volumen propios. Partículas muy juntas que vibran en su lugar.",
                    "**Líquido:** volumen propio, toma la forma del recipiente. Partículas juntas que se deslizan.",
                    "**Gas:** sin forma ni volumen propios, ocupa todo el recipiente. Partículas separadas que se mueven rápido."
                  ]
                }
              ]
            }
Por ejemplo, una Lesson contiene:

{
  "id": "l1-three-states",
  "title": "Los tres estados de la materia",
  "summary": "...",
  "objectives": [],
  "estimatedDurationMin": 90,
  "modes": [],
  "teacherNotes": {},
  "topics": [],
  "objects": [
    {
      "id": "...",
      "type": "lecture"
    },
    {
      "id": "...",
      "type": "explanation"
    },
    {
      "id": "...",
      "type": "simulation_lab"
    },
    {
      "id": "...",
      "type": "activity"
    }
  ]
}

La tercera lección introduce además el objeto exam, por ahora los exam no vienen dentro del módulo de Classroom Engine

2. lecture

Es el objeto más parecido a una presentación/cátedra. No existe un type: "reading" literal en el archivo; el equivalente conceptual más cercano sería lecture o explanation.

Estructura principal:

{
  "id": "l1-lecture",
  "type": "lecture",
  "title": "...",
  "modes": [],
  "topicRef": "...",
  "estimatedDurationSec": 1200,
  "teacherNotes": {},
  "slides": []
}

Cada slide tiene:

{
  "id": "...",
  "title": "...",
  "estimatedSec": 240,
  "teacherNotes": {},
  "blocks": []
}

Dentro de los blocks de una lecture encontré:

heading
text
image
list
video

Ejemplo:

{
  "type": "video",
  "mediaId": "vid-changes",
  "caption": "...",
  "startSec": 0,
  "endSec": 60,
  "autoplay": false
}

3. explanation

Representa una explicación/lectura guiada.

Su estructura cambia de slides a pages:

{
  "id": "l1-explanation",
  "type": "explanation",
  "title": "...",
  "modes": [],
  "topicRef": "...",
  "estimatedDurationSec": 600,
  "teacherNotes": {},
  "pages": []
}

Dentro de cada página:

{
  "id": "...",
  "title": "...",
  "blocks": []
}

Aquí aparecen:

audio
text
pdf

Por ejemplo:

{
  "type": "audio",
  "mediaId": "aud-summary",
  "caption": "Escucha el resumen de los tres estados."
}

y:

{
  "type": "pdf",
  "mediaId": "pdf-lab-guide",
  "fromPage": 1,
  "toPage": 3,
  "caption": "Guía completa, 3 páginas."
}

4. simulation_lab

Es una actividad interactiva que carga una simulación.

{
  "id": "l1-lab-phet",
  "type": "simulation_lab",
  "title": "...",
  "modes": [],
  "topicRef": "...",
  "estimatedDurationSec": 1500,
  "teacherNotes": {},
  "mediaId": "sim-phet-states",
  "learningGoal": "...",
  "instructions": "...",
  "steps": [],
  "guidingQuestions": []
}

Además puede incluir:

"launchParams": {
  "startTemp": -10,
  "altitudeMeters": 0
}

Es decir, aquí mediaId apunta a una simulación definida globalmente en media.

5. activity

Es una actividad de práctica compuesta por preguntas.

{
  "id": "l1-activity",
  "type": "activity",
  "title": "...",
  "modes": [],
  "topicRef": "...",
  "estimatedDurationSec": 1500,
  "teacherNotes": {},
  "instructions": "...",
  "settings": {},
  "questions": []
}

Los settings principales encontrados son:

{
  "feedback": "immediate",
  "attemptsAllowed": 2,
  "shuffleQuestions": false,
  "shuffleOptions": true
}

Dentro de questions encontré 6 tipos:

type	Uso
multiple_choice	Selección múltiple
true_false	Verdadero/Falso
fill_blanks	Completar espacios
matching	Relacionar columnas
ordering	Ordenar elementos
open	Respuesta abierta

Por ejemplo, multiple_choice maneja principalmente:

{
  "id": "...",
  "type": "multiple_choice",
  "prompt": "...",
  "topicRef": "...",
  "difficulty": 1,
  "estimatedSec": 30,
  "points": 1,
  "cognitiveLevel": "remember",
  "allowMultiple": false,
  "options": [],
  "feedback": {}
}

6. exam

Funciona parecido a activity, pero introduce reglas de evaluación y selección del banco de preguntas.

{
  "id": "l3-exam",
  "type": "exam",
  "title": "...",
  "modes": ["exam"],
  "teacherNotes": {},
  "instructions": "...",
  "settings": {},
  "questions": []
}

Los settings son más complejos:

{
  "selection": {
    "strategy": "random_balanced",
    "questionCount": 4,
    "difficultyTolerancePct": 15,
    "timeTolerancePct": 15,
    "coverAllTopics": true
  },
  "timeLimit": {
    "policy": "sum_of_estimates",
    "extraPct": 25
  },
  "passingScorePct": 60,
  "showResults": "after_teacher_release",
  "allowBackNavigation": true,
  "shuffleOptions": true
}

Catálogo completo que te conviene poner en el prompt

La jerarquía que realmente presenta este JSON es:

COURSE
│
├── media[]
│   ├── image
│   ├── video
│   ├── audio
│   ├── pdf
│   └── simulation
│
└── lessons[]
    │
    ├── lecture
    │   └── slides[]
    │       └── blocks[]
    │           ├── heading
    │           ├── text
    │           ├── image
    │           ├── list
    │           └── video
    │
    ├── explanation
    │   └── pages[]
    │       └── blocks[]
    │           ├── text
    │           ├── audio
    │           └── pdf
    │
    ├── simulation_lab
    │   └── mediaId → simulation
    │
    ├── activity
    │   └── questions[]
    │       ├── multiple_choice
    │       ├── true_false
    │       ├── fill_blanks
    │       ├── matching
    │       ├── ordering
    │       └── open
    │
    └── exam
        └── questions[]
            ├── multiple_choice
            ├── true_false
            ├── fill_blanks
            ├── matching
            ├── ordering
            └── open

Además, el catálogo global media define explícitamente los tipos image, video, audio, pdf y simulation, con propiedades como path, mimeType, title, dimensiones, duración, transcripciones y licencias.

Para tu prompt, la distinción más importante

No definiría los tipos simplemente como:

lectura
audio
video
pdf
quiz

porque eso no representa fielmente este JSON.

Usaría dos conceptos:

OBJECT TYPES
- lecture
- explanation
- simulation_lab
- activity
- exam

y dentro:

CONTENT BLOCK TYPES
- heading
- text
- list
- image
- video
- audio
- pdf

y adicionalmente:

QUESTION TYPES
- multiple_choice
- true_false
- fill_blanks
- matching
- ordering
- open

Esta separación te va a servir mucho para el prompt porque permite indicarle al agente que primero determine qué clase de experiencia pedagógica está construyendo (object.type) y después qué contenido visual/multimedia necesita (block.type), en lugar de tratar un video y un examen como objetos del mismo nivel.

#Elementos principales a tener en cuenta

Capacidades de MOD-007. La columna sin red indica si la capacidad funciona con el aula desconectada.
ID	Capacidad	Actor	Sin red	Alcance
CAP-037	Abrir una sesión de clase desde cualquiera de las cuatro formas	Profesor	Sí	MVP
CAP-038	Ver en vivo quién se conectó a la sesión	Profesor	Sí	MVP
CAP-039	Proyectar el mismo contenido en la pantalla interactiva y en los dispositivos	Profesor	Sí	MVP
CAP-040	Difundir un recurso o actividad a todos los dispositivos con confirmación	Profesor	Sí	MVP
CAP-041	Reanudar una sesión de clase interrumpida sin perder respuestas ni estado	Profesor	Sí	MVP
CAP-042	Bloquear y liberar las pantallas de los alumnos durante una explicación	Profesor	Sí	MVP
CAP-043	Ver el avance vivo del grupo mientras responden y detectar rezagados	Profesor	Sí	MVP
CAP-044	Sostener la sesión con 50 dispositivos y pico de 100 sin degradar la interacción	Sistema	Sí	MVP
CAP-045	Cerrar la sesión dejando la evidencia consolidada y lista para reporte	Profesor	Sí	MVP
G · Funciones
Funciones de MOD-007, con su disparador, su precondición, el evento que publica y el permiso que exige.
ID	Función	Actor y superficie	Disparador	Precondición	Evento	Permiso
FUN-064	Iniciar una sesión de clase desde un plan de clase	Profesor · Navegador	acción	El plan tiene al menos un bloque y el nodo está sano	aula.sesion.iniciada.v1	classroom.start
FUN-065	Generar el código de unión de una sesión	Sistema · Nodo	evento	La sesión está en estado iniciada	aula.codigo.generado.v1	ninguno
FUN-066	Rotar el código de unión de una sesión activa	Profesor · Navegador	acción	La sesión sigue activa	aula.codigo.rotado.v1	classroom.code.rotate
FUN-067	Admitir a un dispositivo en la sesión	Profesor · Navegador	acción	El dispositivo presentó un código válido	aula.dispositivo.admitido.v1	classroom.device.admit
FUN-068	Rechazar el ingreso de un dispositivo no autorizado	Profesor · Navegador	acción	El dispositivo está en la lista de espera	aula.dispositivo.rechazado.v1	classroom.device.admit
FUN-069	Proyectar un recurso en la pantalla interactiva	Profesor · Pantalla	acción	El recurso está disponible en el almacén del nodo	aula.recurso.proyectado.v1	classroom.present
FUN-070	Lanzar una actividad a los dispositivos del grupo	Profesor · Navegador	acción	Hay al menos un dispositivo admitido	aula.actividad.lanzada.v1	classroom.activity.launch
FUN-071	Cerrar la recepción de respuestas de la actividad en curso	Profesor · Navegador	acción	La actividad está abierta	aula.actividad.cerrada.v1	classroom.activity.close
FUN-072	Mostrar el panel de resultados agregados en la pantalla	Profesor · Pantalla	acción	La actividad tiene al menos una respuesta registrada	aula.resultados.mostrados.v1	classroom.results.view
FUN-073	Registrar la presencia técnica de los participantes conectados	Sistema · Nodo	evento	La sesión está activa y el grupo tiene inscritos	aula.presencia.registrada.v1	ninguno
FUN-074	Bloquear la pantalla de los dispositivos del grupo	Profesor · Navegador	acción	La sesión está activa	aula.dispositivos.bloqueados.v1	classroom.device.lock
FUN-075	Enviar un mensaje de aviso a un dispositivo o al grupo	Profesor · Navegador	acción	El destinatario está admitido en la sesión	aula.mensaje.enviado.v1	classroom.message.send
FUN-076	Reanudar una sesión de clase tras reinicio del nodo	Sistema · Nodo	arranque	Existe una sesión sin finalizar en el registro persistente	aula.sesion.reanudada.v1	ninguno
FUN-077	Readmitir a un dispositivo que perdió conexión sin duplicar su participación	Sistema · Nodo	evento	El dispositivo presenta el mismo identificador de participación	aula.dispositivo.readmitido.v1	ninguno
FUN-078	Expulsar a un dispositivo de la sesión	Profesor · Navegador	acción	El dispositivo está admitido	aula.dispositivo.expulsado.v1	classroom.device.remove
FUN-079	Finalizar la sesión de clase y consolidar su registro	Profesor · Navegador	acción	No hay actividades abiertas pendientes de cierre	aula.sesion.finalizada.v1	classroom.end
H · Estados que gobierna
Gobierna la sesión de clase, con planificada, abierta, suspendida por caída del equipo del aula, cerrada y archivada a las veinticuatro horas. Una sesión cerrada nunca se reabre: se crea una nueva. Reanudar conserva siempre el mismo código de unión, porque cambiarlo rompería la reconexión de las tabletas.

I · Reglas e invariantes que lo gobiernan
BR-044
Una sesión se inicia por cualquiera de las cuatro vías (nodo del árbol, lección de curso, recurso directo o clase libre) y todas producen el mismo tipo de sesión, con las mismas capacidades.

BR-045
Un profesor mantiene como máximo una sesión de clase activa a la vez en el mismo nodo.

BR-046
Una sesión se inicia y opera usando exclusivamente el nodo maestro local y la red del aula.

BR-047
Un alumno solo se une si está inscrito en el grupo de la sesión, o si el profesor lo admite de forma manual como invitado de esa sesión.

BR-048
El profesor puede expulsar o readmitir a un participante durante la sesión, y la expulsión no borra las respuestas ya registradas.

BR-049
El contenido proyectado es el que el profesor declara como selector de la sesión, y el cambio de selector se propaga a los dispositivos en seguimiento en un máximo de 3 segundos.

BR-050
Un alumno en modo seguimiento no navega libremente; al liberar el seguimiento recupera la navegación y el sistema registra el cambio en la sesión.

BR-051
Una sesión interrumpida por caída del nodo se reanuda en el mismo selector y con los mismos participantes cuando el nodo vuelve, dentro de la ventana de 3 minutos.

BR-052
Una sesión cerrada no admite participantes nuevos ni cambios de selector, y las respuestas encoladas en dispositivos se siguen aceptando hasta el cierre de sus asignaciones.

INV-025
Una sesión de clase existe siempre en exactamente uno de sus estados y solo transita por transiciones autorizadas.

J · Permisos que exige
classroom.activity.close
classroom.activity.launch
classroom.code.rotate
classroom.device.admit
classroom.device.lock
classroom.device.remove
classroom.end
classroom.message.send
classroom.present
classroom.results.view
classroom.start
K · Datos de los que es propietario
Grupos de datos con escritor único. Ningún otro módulo escribe en ellos, ni durante una migración ni durante una restauración.
Grupo de datos	Quién lo lee	Vía de lectura
Sesiones de clase y su resumen	010, 012, 013, 019	Evento
Participantes y presencia técnica	009, 013	Interfaz y evento
Entidades que toca: Archivo, Asignacion, Dispositivo, EventoDeCola, Grupo, Intento, Notificacion, PlanDeClase, Progreso, RegistroAuditoria, Respuesta, SesionDeClase, Usuario.

L · Eventos que publica
Evento
aula.actividad.cerrada.v1
aula.actividad.lanzada.v1
aula.codigo.generado.v1
aula.codigo.rotado.v1
aula.dispositivo.admitido.v1
aula.dispositivo.expulsado.v1
aula.dispositivo.readmitido.v1
aula.dispositivo.rechazado.v1
aula.dispositivos.bloqueados.v1
aula.mensaje.enviado.v1
aula.presencia.registrada.v1
aula.recurso.proyectado.v1
aula.resultados.mostrados.v1
aula.sesion.finalizada.v1
aula.sesion.iniciada.v1
aula.sesion.reanudada.v1
M · Escenarios de prueba
Escenarios en los que este módulo participa. Los de prioridad alta son bloqueantes para su aceptación.
ID	Escenario	Condición previa	Pasos	Resultado esperado	Prioridad
TST-001	Iniciar clase desde el árbol	Nodo activo, grupo de 25, sin internet	1 abrir árbol; 2 elegir nodo; 3 iniciar	Sesión activa con código de unión en 10 segundos o menos	Alta
TST-002	Conectar alumnos	25 tabletas, router del aula	1 abrir aplicación; 2 leer el código; 3 entrar	25 de 25 unidos en 60 segundos o menos	bloqueante
TST-005	Ver resultados en vivo	Panel del profesor abierto	1 abrir panel; 2 observar avance	Puntuación de 0 a 100 por alumno visible a menos de 5 segundos del envío	Alta
TST-007	Cerrar clase	Sesión con 25 intentos	1 pulsar cerrar; 2 confirmar	Sesión en estado cerrado y cola pendiente en cero	Alta
TST-019	Un solo dispositivo	Una tableta	1 conectar; 2 responder; 3 cerrar	Ciclo completo con un intento registrado	Media
TST-025	Navegador del profesor	Dos navegadores soportados	1 abrir el panel; 2 operar la clase	Control de clase completo desde el navegador	Alta
N · Dependencias
MOD-001 valida la sesión única de cada participante antes de admitirlo.
MOD-009 identifica cada dispositivo por su certificado y aplica el nivel de control.
MOD-010 se hace cargo de todo intento, y este módulo no toca respuestas.
MOD-015 le da el reloj y le garantiza el punto de recuperación de cinco segundos.
O · Estado de definición
Capacidades clasificadas	9
Funciones con disparador, precondición y evento	16
Reglas e invariantes que lo gobiernan	10
Grupos de datos en propiedad exclusiva	2
Eventos que publica	16
Permisos que exige	11
Escenarios de prueba en los que participa	6




