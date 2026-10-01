# 06 · Evaluation & Delivery Engine (MOD-010) · Pruebas técnicas en producción (happy paths)

| Campo | Valor |
|---|---|
| Módulo | MOD-010 · Evaluation & Delivery Engine (`backend/evaluacion/`, Student, OPS, bloqueo de la tableta) |
| Tipo de documento | Plan de pruebas técnicas — spec driven dev |
| Alcance | **Sólo happy paths.** Los caminos tristes y malos (rechazos, 4xx, ataques, fallos del hardware) quedan fuera y se cubren con las pruebas automáticas del repositorio |
| Quién ejecuta | Operador/QA con acceso al nodo instalado, a OPS, a la biblioteca AVACOM Contenido y a tabletas reales (Windows y Android) |
| Fuentes | [introduccion.md](introduccion.md) · [modelado-datos.md](modelado-datos.md) · [backend.md](backend.md) · [frontend.md](frontend.md) · [kiosk.md](kiosk.md) · [`scripts/README.md`](../../scripts/README.md) |
| Fecha | 2026-10-01 |
| Estado | Borrador para ejecución. Se escribió **sin acceso a producción**: cada comando y cada texto de pantalla sale del código y de los documentos; lo que no se pudo confirmar va marcado «(por confirmar en producción)» |

---

## 1 · Propósito y alcance

Estos casos demuestran, **en el entorno real**, que el ciclo completo de una evaluación funciona cuando todo sale bien: el profesor aplica un examen de la biblioteca, el alumno lo presenta en su tableta (con o sin bloqueo), el nodo guarda, vigila, califica y entrega, el profesor revisa y libera, y todo queda asentado en la bitácora.

Qué se demuestra:

* Que el examen **sale siempre de AVACOM Contenido** (la biblioteca), con la versión congelada al asignar, y que el nodo **no guarda** curso, preguntas ni claves (artículo 14).
* Que lo que el alumno responde **nunca se pierde** (cola cifrada, pausa, reinicio del equipo del aula).
* Que el **reloj** es del nodo y el cronómetro del alumno no se vuelve alarma.
* Que el **bloqueo** lo decide el nodo, lo aplica la tableta y la tableta **informa lo que logró** (`aplicado`, `parcial`, `fallido`).
* Que las decisiones humanas (admitir una tableta, reactivar, revisar, publicar, anular) funcionan, quedan con nombre y motivo, y el sistema **nunca anula por sí solo** (INV-018).

Qué **no** se demuestra aquí: caminos tristes, carga con decenas de tabletas, ni nada que requiera dañar datos reales (ver §8).

---

## 2 · Entorno y precondiciones

### 2.1 · Lo que debe existir antes de ejecutar cualquier caso

| # | Precondición | Cómo comprobarla |
|---|---|---|
| P-1 | El **nodo** del aula está instalado y su servicio (`AVACOMOPSBackend`) en marcha, con la organización instalada | `GET <NODO>/api/evaluacion/asignaciones/` responde `200` con `{"asignaciones": [...]}` (con `409 no_instalado` el nodo no tiene organización) |
| P-2 | **AVACOM Contenido** (la biblioteca) está encendida y con índice listo | Leer `C:\ProgramData\AVACOM\content\link.json` (`apiPort`, `token`) y llamar `GET http://127.0.0.1:<apiPort>/v2/health` con la cabecera `X-Avacom-Token`: debe decir `contract: 2`, `index: "ready"` y `installedCourses ≥ 1` |
| P-3 | El **examen de prueba** está instalado en la biblioteca | Ver §2.2 |
| P-4 | Existe un **grupo de prueba** con **al menos 3 alumnos** y un **profesor** titular; los alumnos aparecen en `GET <NODO>/api/evaluacion/estudiantes/` (sólo salen si el grupo tiene una evaluación abierta; por eso se comprueba después de HP-EVA-01) | Anotar `<GRUPO_ID>`, `<ALUMNO_1..3>` y `<PROFESOR_ID>` |
| P-5 | **Dos tabletas** registradas en el inventario del aula (página Dispositivos de OPS): una **Windows** con Student instalada y una **Android** con Student instalada. Ambas con conexión al nodo por la LAN del aula | Dispositivos muestra cada tableta con su chip «Capacidad: …» |
| P-6 | El profesor tiene los permisos `assessment.*` (los 16 que siembra la migración `acceso/0009_permisos_evaluacion`) | Entrar a OPS con el profesor y abrir una clase |
| P-7 | Para HP-EVA-13 y HP-EVA-14: el aprovisionamiento del bloqueo del sistema operativo (scripts de [`scripts/`](../../scripts/README.md)) **sobre un equipo/tableta de pruebas con acceso físico y cuenta de recuperación** | Se prepara dentro de cada caso |

### 2.2 · El examen de prueba

Los valores de abajo son los **reales** de la biblioteca instalada al escribir este documento; si en producción el curso es otro, cambiar `CURSO` y `OBJETO` y ajustar los conteos.

| Dato | Valor |
|---|---|
| `CURSO` | `avacom.co.lower_secondary.6.science.states-of-matter` (versión `2.0.0`) |
| `OBJETO` | `l3-exam` («Examen de estados de la materia», lección `l3-assessment`) |
| Banco | 18 preguntas (opción múltiple, verdadero/falso, completar, ordenar y **una abierta**, `l3-q5`) |
| Ajustes de la biblioteca | `random_balanced` de **6 preguntas** por alumno, tiempo fijo de **360 s**, resultados `after_teacher_release`, retroceso permitido |

### 2.3 · Ayudante de PowerShell

Todos los comandos de §5 usan este bloque. Pegarlo una vez en la consola de PowerShell del equipo desde el que se prueba.

```powershell
$N = 'http://<NODO>:8000'          # la dirección del aula, la misma que muestra OPS
$TOKEN = $null                     # si el nodo EXIGE sesión: el JWT del profesor; si no, dejar $null y usar "actor"
$PROF = '<PROFESOR_ID>'
function Api($metodo, $ruta, $cuerpo = $null) {
  $p = @{ Method = $metodo; Uri = "$N$ruta"; ContentType = 'application/json; charset=utf-8' }
  if ($TOKEN) { $p.Headers = @{ Authorization = "Bearer $TOKEN" } }
  if ($null -ne $cuerpo) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($cuerpo | ConvertTo-Json -Depth 8)) }
  Invoke-RestMethod @p
}
```

Con sesión de usuario (`$TOKEN`), el permiso lo da el rol; sin sesión, las rutas del profesor aceptan `actor` y `actor_rotulo` en el cuerpo (D-19, Q-34 abierta). Las rutas del alumno se identifican con `dispositivo` (la huella `student-<NOMBRE-DEL-EQUIPO>`) y `alumno_id`.

---

## 3 · Convenciones

* **ID de caso**: `HP-EVA-NN`. Cada caso lleva: Objetivo · Requisitos que demuestra · Precondiciones · Datos / actor · Pasos · Resultado esperado · Evidencia a guardar · Efectos colaterales / limpieza.
* **Evidencia**: la respuesta JSON guardada en un archivo (`| Tee-Object -FilePath .\evidencia\HP-EVA-NN-paso.json`), la **captura de pantalla** de la tableta o de OPS, y la fila del §7 completada. Nombrar los archivos con el ID del caso.
* **Criterio de paso**: un caso pasa sólo si **todos** sus resultados esperados se cumplen. Un resultado esperado se verifica contra lo que el nodo devuelve **o** lo que la pantalla dice, nunca contra la memoria del ejecutor.
* **Datos de prueba identificables**: usar el grupo y los alumnos de prueba (P-4). Que el título de la asignación de prueba lleve el prefijo `PRUEBA-` cuando el flujo lo permita.
* **Seguridad en producción**:
  * No usar alumnos ni grupos reales.
  * **La bitácora de auditoría no se puede borrar** (MOD-019): estas pruebas dejan asientos `evaluacion.*` permanentes y es lo esperado.
  * Las asignaciones de prueba se **cierran** al terminar (no hay borrado); a las 24 h pasan solas a `archivada`.
  * Device Owner en Android **sólo se deshace con un restablecimiento de fábrica**: usar una tableta de pruebas.
  * Nunca definir `AVACOM_EXAM_NO_LOCKDOWN` en un equipo de producción.
* **Tiempos**: salvo que el caso diga otra cosa, los alumnos usan el tiempo del examen. Los casos de tiempo/plazo crean su propia asignación con tiempo fijo corto para no esperar.

---

## 4 · Matriz de trazabilidad

| Requisito | Qué dice | Casos |
|---|---|---|
| FUN-108 | Asignar a un grupo o alumnos | HP-EVA-01 |
| FUN-105 | Nivel mínimo de control (obligatorio, sin preselección) | HP-EVA-01, HP-EVA-03 |
| FUN-109 | Abrir un intento (idempotente) | HP-EVA-04, HP-EVA-08 |
| FUN-110 / FUN-111 | Respuestas con secuencia y deduplicación | HP-EVA-04, HP-EVA-07 |
| FUN-112 / FUN-113 | Autocalificar en la biblioteca y enviar a revisión | HP-EVA-04, HP-EVA-05 |
| FUN-114 | Entregar un intento | HP-EVA-04 |
| FUN-106 / FUN-107 | Fecha límite blanda y endurecida | HP-EVA-17 |
| FUN-115 | Intento fuera de plazo | HP-EVA-17 |
| FUN-116 / BR-076 | Admitir una tableta por debajo del nivel | HP-EVA-12 |
| FUN-117 / BR-077 | Incidentes sin invalidar el intento | HP-EVA-11, HP-EVA-13, HP-EVA-14 |
| FUN-118 | Degradar el nivel en curso | HP-EVA-15 |
| PAN-061 | Reactivar un intento suspendido | HP-EVA-08, HP-EVA-09, HP-EVA-10 |
| PAN-005 / PAN-121 / CMP-034 | Panel del profesor ordenado por quién lo necesita | HP-EVA-06 |
| PAN-060 / MSG-036 | Elegibilidad de las tabletas al aplicar | HP-EVA-01, HP-EVA-12 |
| PAN-062 | Expediente de sólo lectura | HP-EVA-11, HP-EVA-19 |
| PAN-120 | Antesala del alumno | HP-EVA-03 |
| PAN-122 / MSG-033 | «Tu examen está en pausa» | HP-EVA-08 |
| PAN-123 | Entrega con confirmación única y «qué sigue» | HP-EVA-04 |
| CAP-062 | Puntuar y publicar | HP-EVA-05 |
| DEC-032 | Sin nota antes de que el profesor libere | HP-EVA-05, HP-EVA-18 |
| BR-051 / INV-010 / AC-073 | Reinicio del equipo: restaurar sin entregar ni anular | HP-EVA-10 |
| BR-071 | Las respuestas se guardan primero y llegan después | HP-EVA-07 |
| BR-075 | Capacidad de la tableta frente al nivel | HP-EVA-12, HP-EVA-13, HP-EVA-14 |
| INV-018 | El sistema nunca anula | HP-EVA-16, HP-EVA-17, HP-EVA-19 |
| INV-024 | La versión del curso se congela al asignar | HP-EVA-01 |
| DEC-038 | Mientras hay examen no hay relevo de profesor | HP-EVA-10 |
| TST-027 | Un alumno, una tableta a la vez (relevo de sesión) | HP-EVA-08 |
| MOD-019 | Todo queda asentado en la bitácora | HP-EVA-20 |

---

## 5 · Happy paths

### HP-EVA-01 · Aplicar un examen de la biblioteca a un grupo

**Objetivo.** El profesor aplica el examen real de la biblioteca a su grupo con un nivel de control elegido a propósito; el nodo valida el examen contra la biblioteca, congela su versión y deja la asignación activa.

**Requisitos que demuestra.** FUN-108 · FUN-105 · INV-024 · PAN-060 · MSG-036 · que los cursos salen siempre de la biblioteca.

**Precondiciones.** P-1 a P-6.

**Datos / actor.** Profesor titular. Nivel `abierto` (el caso más simple; los niveles `supervisado` y `controlado` se usan en HP-EVA-11 a HP-EVA-15).

**Pasos.**

1. Comprobar que el nodo lee la biblioteca (no el ejemplo): `Api GET '/api/aula/cursos/'` → `fuente = "biblioteca"`, `disponible = true`, y la lista contiene `CURSO`.
2. Crear y publicar la asignación:
   ```powershell
   $a = Api POST '/api/evaluacion/asignaciones/' @{
     fuente='biblioteca'; curso_ref='avacom.co.lower_secondary.6.science.states-of-matter'; objeto_ref='l3-exam'
     alcance='grupo'; grupo_id='<GRUPO_ID>'; nivel_examen='abierto'; tiempo=@{modo='biblioteca'}
     intentos_permitidos=1; plazo='blando'; reactivacion='profesor'; resultados='tras_liberar'
     iniciar=$true; actor=$PROF; actor_rotulo='Profesor de prueba' }
   $a | ConvertTo-Json -Depth 6 | Tee-Object .\evidencia\HP-EVA-01-asignacion.json
   $ASIG = $a.id
   ```
3. En OPS, abrir el panel de la asignación (`Ver panel del examen` si se llega desde la clase; si no, dejarlo para HP-EVA-06). **Nota:** con la biblioteca real el examen aún puede no aparecer en la secuencia de la clase (`mode=class`), por lo que «Aplicar examen» desde la clase puede no ofrecerse; es un hueco conocido y por eso este caso aplica por la API (por confirmar en producción).
4. Consultar la elegibilidad: `Api GET "/api/evaluacion/asignaciones/$ASIG/elegibilidad/"`.

**Resultado esperado.**

* El paso 2 responde **201** con `estado = "activa"`, `nivel_examen = "abierto"`, `fuente_curso = "biblioteca"`, `curso_version = "2.0.0"` (la versión instalada) y `armado_previo` con `estrategia = "random_balanced"`, `preguntas_por_alumno = 6`, `total_banco = 18` y `limite_seg_estimado` (≈ 360).
* Sin `nivel_examen` el nodo habría respondido `400 datos_invalidos`: **el sistema no preselecciona** el nivel (esto no se prueba aquí, sólo se constata que se mandó explícito).
* El paso 4 devuelve una lista por destinatario con tableta conocida y el resumen `{alcanzan, no_alcanzan}`.
* `GET /api/evaluacion/estudiantes/` ahora lista el grupo de prueba con sus alumnos.

**Evidencia a guardar.** `HP-EVA-01-asignacion.json`; captura del panel (si se abrió).

**Efectos colaterales / limpieza.** Se deja la asignación activa: la usan HP-EVA-02 a HP-EVA-06. Asiento `evaluacion.asignada` en la bitácora.

---

### HP-EVA-02 · «¿Quién eres?» y «Mis evaluaciones» en la tableta

**Objetivo.** Una tableta **sin sesión de usuario** pregunta a la persona quién es, sin código ni contraseña, y le muestra sus evaluaciones.

**Requisitos que demuestra.** D-19 · D-25 · `GET /api/evaluacion/estudiantes/` · `GET /api/evaluacion/mias/`.

**Precondiciones.** HP-EVA-01 hecho (asignación `activa`). Student instalada y apuntando al aula (pantalla de conexión con la dirección del nodo). En Windows, **lanzada sin** `AVACOM_EXAM_NO_LOCKDOWN`.

**Datos / actor.** Alumno 1 en la tableta Windows.

**Pasos.**

1. En la tableta, entrar al aula (dirección del nodo; si el aula exige sesión, con el código y la clave del alumno: en ese caso no aparece «¿Quién eres?»).
2. En el menú de Student tocar **«Exámenes»** (el botón del dock).
3. En la pantalla **«¿Quién eres?»** tocar el nombre del alumno 1. Si hay varios grupos con evaluación abierta la pantalla dice primero «Elige tu grupo y luego tu nombre.»; con un grupo elegido dice «Toca tu nombre para ver tus evaluaciones.»
4. Mirar la pantalla **«Mis evaluaciones»**.
5. Desde un equipo del aula: `Api GET "/api/evaluacion/mias/?dispositivo=student-<EQUIPO>&alumno_id=<ALUMNO_1>"`.

**Resultado esperado.**

* El paso 3 muestra los alumnos de los grupos con una evaluación abierta, ordenados por nombre; no pide teclado.
* El paso 4 muestra «Presentas como *Nombre* · ¿No eres tú? Toca aquí», la sección **«Para presentar»** con la tarjeta del examen (título, «N preguntas», chip del nivel —«Examen abierto»— y chip «Abierto»), la frase «Lee las condiciones antes de empezar» y el botón **«Comenzar»**.
* El paso 5 devuelve `pendientes` con la asignación, `puede_comenzar = true`, `mi_intento = null`.

**Evidencia a guardar.** Capturas de «¿Quién eres?» y «Mis evaluaciones»; JSON del paso 5.

**Efectos colaterales / limpieza.** Student guarda en la tableta a quién presenta (`student_eval_*`); se olvida con «¿No eres tú? Toca aquí».

---

### HP-EVA-03 · Antesala con las condiciones del nivel

**Objetivo.** Antes de empezar, el alumno ve cuántas preguntas tiene, cuánto dura y **bajo qué condiciones** presenta; el examen sólo se abre al tocar «Comenzar».

**Requisitos que demuestra.** PAN-120 · FUN-105 · BR-075.

**Precondiciones.** HP-EVA-02.

**Datos / actor.** Alumno 1.

**Pasos.**

1. En «Mis evaluaciones» tocar **«Comenzar»** de la tarjeta del examen.
2. **No** tocar «Comenzar» de la antesala todavía; leerla.
3. Verificar por la API: `Api GET "/api/evaluacion/asignaciones/$ASIG/antesala/?dispositivo=student-<EQUIPO>&alumno_id=<ALUMNO_1>"`.

**Resultado esperado.**

* La antesala muestra el título del examen, el curso, los datos «6 preguntas», «6 min» e «Intento único», la caja de condiciones con el texto del nivel y la lista **«Qué se registra»**, y el botón **«Comenzar»**.
* En la API: `puede_comenzar = true`, `condiciones.nivel = "abierto"`, `condiciones.registra` lista lo que se registra, `dispositivo.alcanza = true`, `mi_intento = null`. **Todavía no hay intento abierto** (iniciar sin que el alumno lo haya visto es lo que el sistema nunca hace).
* La tarjeta está en el **tercio central** de la pantalla en una ventana de escritorio de 1920 px.

**Evidencia a guardar.** Captura de la antesala; JSON del paso 3.

**Efectos colaterales / limpieza.** Ninguno.

---

### HP-EVA-04 · Presentar el examen completo y entregarlo

**Objetivo.** El alumno presenta el examen de punta a punta: responde preguntas de los distintos tipos, ve el guardado y el cronómetro, y entrega; el nodo califica lo automático en la biblioteca y deja lo abierto para el profesor.

**Requisitos que demuestra.** FUN-109 · FUN-110 · FUN-111 · FUN-112 · FUN-113 · FUN-114 · PAN-121 · PAN-123 · BR-138 · D-16.

**Precondiciones.** HP-EVA-03.

**Datos / actor.** Alumno 1; tableta Windows.

**Pasos.**

1. En la antesala tocar **«Comenzar»**.
2. Verificar la cabecera: título, «✓ Guardado», el cronómetro `mm:ss` con «te quedan», «Pregunta 1 de 6» y «0 de 6 contestadas».
3. Responder cada pregunta según su tipo (opción, verdadero/falso, completar, ordenar con «Listo, este es mi orden» y la abierta con texto). Usar **«Siguiente»** y **«Anterior»**; probar también la tira de números.
4. Tras cada respuesta comprobar que el contador sube («1 de 6 contestadas»…) y que la pastilla dice «✓ Guardado» (o «● Guardado en tu tableta» un instante).
5. Dejar **una** pregunta sin responder y tocar **«Entregar»**.
6. En la confirmación leer «Te falta 1 pregunta. Puedes entregar igual.» y tocar **«Entregar igual»**.
7. En la pantalla de entrega leer el mensaje y tocar **«Volver a mis evaluaciones»**.
8. Desde el nodo: `Api GET "/api/evaluacion/intentos/<INTENTO>/"` (el id sale de `Api GET "/api/evaluacion/asignaciones/$ASIG/panel/"` → `filas[].intento_id`).

**Resultado esperado.**

* Paso 1: `201` (visible en el panel como `en_curso`) y el reloj corre desde ese momento.
* Pasos 2–4: el cronómetro **no cambia de color ni suena**, tampoco al final; las preguntas llegan en el orden de **su** armado y **sin ninguna clave** de respuesta.
* Paso 6: es **una sola** confirmación; «Entregar igual» no pide nada más.
* Paso 7: «Tu examen quedó entregado», debajo «Algunas respuestas las revisa tu profesor.» (hay una abierta) y «Respondiste 5 de 6 preguntas.» La pantalla **no dice «calificado»** ni muestra nota.
* Paso 8: `intento.estado = "en_revision_docente"` (la abierta quedó por revisar) o `"calificado"` si el armado de este alumno no incluyó la abierta; `origen_entrega = "alumno"`; `porcentaje` **nulo** mientras quede un reactivo por revisar. Ninguna respuesta registra la clave.
* La calificación automática se hizo con **una sola** llamada de lote a la biblioteca (se puede ver, si se tiene acceso, en el registro de la biblioteca: `POST /v2/evaluate/batch`) (por confirmar en producción).

**Evidencia a guardar.** Capturas de la cabecera, de la confirmación y de la entrega; JSON del paso 8.

**Efectos colaterales / limpieza.** Un intento entregado del alumno 1 (intento único: no puede volver a presentar). Asientos `evaluacion.iniciada` y `evaluacion.enviada`.

---

### HP-EVA-05 · Revisión del profesor, liberación y resultado del alumno

**Objetivo.** El profesor puntúa lo abierto, publica la revisión y libera los resultados; el alumno ve su nota **sólo después**.

**Requisitos que demuestra.** CAP-062 · FUN-113 · DEC-032 · PAN-123.

**Precondiciones.** HP-EVA-04 (intento del alumno 1 en `en_revision_docente`). Para poder liberar, los demás alumnos deben haber entregado o la asignación estar cerrada (HP-EVA-18 los cierra); en una prueba con un solo alumno presentando, cerrar antes la asignación con `Api POST "/api/evaluacion/asignaciones/$ASIG/cerrar/" @{actor=$PROF}`.

**Datos / actor.** Profesor titular; alumno 1.

**Pasos.**

1. Antes de liberar, en la tableta del alumno 1 abrir «Mis evaluaciones»: la tarjeta dice «Entregado · tu profesor publicará los resultados» y **no** tiene botón de resultado.
2. Ver lo que respondió: `Api GET "/api/evaluacion/intentos/<INTENTO>/revision/"` (o en OPS, el **expediente** del intento).
3. Puntuar la pregunta abierta: `Api POST "/api/evaluacion/intentos/<INTENTO>/respuestas/l3-q5/puntuar/" @{actor=$PROF; puntaje=<N>; comentario='Buen razonamiento'}` (con `0 ≤ N ≤` puntaje máximo de la pregunta; en OPS, la revisión ofrece pasos de 0/25/50/75/100 %).
4. Publicar: `Api POST "/api/evaluacion/intentos/<INTENTO>/publicar/" @{actor=$PROF}`.
5. Liberar: `Api POST "/api/evaluacion/asignaciones/$ASIG/liberar-resultados/" @{actor=$PROF}`.
6. En la tableta, volver a «Mis evaluaciones» y tocar **«Ver resultado»**.

**Resultado esperado.**

* Paso 1: antes de liberar no hay nota; por la API `GET /api/evaluacion/intentos/<INTENTO>/resultado/?dispositivo=…&alumno_id=…` responde **403 `resultados_no_liberados`** (se constata, no se busca el error).
* Paso 3: `200` con el puntaje; el expediente deja el asiento de la revisión.
* Paso 4: el intento pasa a `calificado` con `calificado_por` = el profesor y `porcentaje` ≠ nulo.
* Paso 5: `liberados_en` queda fijado.
* Paso 6: la pantalla muestra el porcentaje grande, **«Aprobado»** (verde) o «Todavía no llegas al 60 % que pide el examen» (**ámbar, nunca rojo**), «x de y puntos», y **«Pregunta por pregunta»** con la retroalimentación y el comentario del profesor.

**Evidencia a guardar.** Captura del resultado; JSON de los pasos 2, 4 y 5.

**Efectos colaterales / limpieza.** Asientos `evaluacion.revision.publicada` y `evaluacion.resultados.liberados`.

---

### HP-EVA-06 · El panel del profesor con varios alumnos a la vez

**Objetivo.** El profesor ve a todos sus alumnos en un panel que se ordena por **quién lo necesita** y que no vigila ni alarma.

**Requisitos que demuestra.** PAN-005 · PAN-121 · CMP-034 · "el panel no es de vigilancia".

**Precondiciones.** Una asignación **nueva** activa (repetir HP-EVA-01 con otro título) y los alumnos 1, 2 y 3 presentando en sus tabletas (Windows y Android) en estados distintos: el 1 en curso, el 2 recién abierto, el 3 aún sin abrir.

**Datos / actor.** Profesor en OPS.

**Pasos.**

1. En OPS abrir el panel del examen (ruta `examen-panel`).
2. Mirar el orden de las filas, los totales de la cabecera y, por alumno, estado, respondidas, pregunta actual, reloj, tableta con su capacidad e incidentes.
3. Contestar una pregunta en la tableta del alumno 2 y esperar el siguiente sondeo (cada 3 s) o el aviso en tiempo real.
4. Comparar con la API: `Api GET "/api/evaluacion/asignaciones/$ASIG/panel/"`.

**Resultado esperado.**

* Las filas siguen el orden del nodo (suspendidos, esperando admisión, envíos tardíos, bloqueo fallido, en curso, entregados), **no alfabético**.
* Los totales coinciden con la API (`destinatarios`, `sin_intento`, `en_curso`, `entregados`…).
* Los cronómetros avanzan solos cada segundo; nada suena ni se pinta de rojo; no hay botón de anular en el panel.
* El contador «respondidas» del alumno 2 sube en el panel sin recargar.

**Evidencia a guardar.** Captura del panel con las tres filas; JSON del paso 4.

**Efectos colaterales / limpieza.** Dejar la asignación abierta si se reutiliza en HP-EVA-07 a HP-EVA-10.

---

### HP-EVA-07 · Responder sin red y recuperar sin perder nada

**Objetivo.** Un corte de red breve no pierde respuestas: se guardan en la tableta, se ven como «Guardado en tu tableta» y se envían solas al volver la conexión.

**Requisitos que demuestra.** BR-071 · FUN-110 · FUN-111 · INV-005 (reenviar no duplica) · cola cifrada.

**Precondiciones.** Alumno 1 con un intento en curso (asignación del HP-EVA-06). El corte debe ser **menor** que el silencio que el nodo tolera (30 s por omisión: `AVACOM_EVAL_LATIDO_VENCIDO_MS`).

**Datos / actor.** Alumno 1; tableta Android.

**Pasos.**

1. En la tableta, desactivar el Wi-Fi.
2. Responder **dos** preguntas distintas. Observar la pastilla de guardado y los avisos.
3. Esperar unos 15 s y reactivar el Wi-Fi.
4. Observar la tableta durante ~10 s (un latido).
5. En el nodo: `Api GET "/api/evaluacion/asignaciones/$ASIG/panel/"` y mirar la fila del alumno 1.

**Resultado esperado.**

* Paso 2: aparece el aviso azul suave «Sin conexión con el aula. Tus respuestas se guardan en esta tableta y se enviarán solas.» y las respuestas cuentan como contestadas; la pastilla dice «● Guardado en tu tableta». **Nunca** dice «error».
* Paso 4: el aviso de conexión desaparece y la pastilla vuelve a «✓ Guardado».
* Paso 5: `respondidas` incluye las dos respuestas; el estado sigue `en_curso` (no se pausó); ninguna se duplicó.

**Evidencia a guardar.** Capturas con y sin conexión; JSON del panel.

**Efectos colaterales / limpieza.** Ninguno.

---

### HP-EVA-08 · Pausa por falta de señal y reactivación del alumno

**Objetivo.** Si una tableta deja de dar señal más de lo tolerado, el nodo **pausa** el intento congelando el reloj; el profesor lo reactiva y el alumno sigue exactamente donde iba.

**Requisitos que demuestra.** PAN-061 · PAN-122 · MSG-033 · INV-010 · D-15 · TST-027.

**Precondiciones.** Alumno 1 con intento en curso. Reactivación `profesor` (la del HP-EVA-01).

**Datos / actor.** Alumno 1; profesor en OPS.

**Pasos.**

1. Anotar la pregunta en que va el alumno y el tiempo restante.
2. Cortar la red de la tableta (Wi-Fi apagado) **más de 40 s**.
3. En OPS mirar el panel: la fila del alumno 1.
4. Restablecer la red.
5. En la tableta observar la pantalla durante un latido.
6. En OPS tocar **Reactivar** en la fila del alumno 1 (o `Api POST "/api/evaluacion/intentos/<INTENTO>/reactivar/" @{actor=$PROF}`).
7. Observar la tableta.

**Resultado esperado.**

* Paso 3: la fila sube al principio del panel como suspendida «esperando que lo reactives»; el reloj está **congelado** en el último latido.
* Paso 5: la tableta muestra la tarjeta **«Tu examen está en pausa»** con «Todo lo que respondiste está guardado y el tiempo está detenido. Tu examen queda en pausa. Avisa a tu profesor para continuar.» y «No necesitas hacer nada más: cuando tu profesor te reactive, sigues justo donde ibas.»; el cronómetro dice «tiempo detenido» y **no hay cuenta atrás en rojo**. Lo respondido sigue guardado.
* Paso 6: `200` con `restante_ms` (el congelado) y `desde_pregunta`.
* Paso 7: en el siguiente latido (≤ 10 s) la tableta **vuelve sola** a la pregunta donde iba y el cronómetro continúa desde el valor congelado.
* El expediente muestra los incidentes `desconexion` y `reactivado`.

**Evidencia a guardar.** Capturas de la pausa y de la vuelta; JSON de la reactivación.

**Efectos colaterales / limpieza.** Asientos `evaluacion.intento.pausado` y `evaluacion.intento.reactivado`.

---

### HP-EVA-09 · «Reactivar a todos»

**Objetivo.** Tras una caída general (el Wi-Fi del aula, por ejemplo), el profesor reactiva a todos los suspendidos con una sola confirmación y ve a cuántos afecta **antes** de confirmar.

**Requisitos que demuestra.** PAN-061 · Guion paso 12.

**Precondiciones.** Al menos **dos** alumnos con intento en curso. Apagar el Wi-Fi de **ambas** tabletas más de 40 s y reconectarlas (como en HP-EVA-08 pasos 2–4).

**Datos / actor.** Profesor en OPS.

**Pasos.**

1. En el panel, tocar **«Reactivar a todos (N)»**.
2. Leer la hoja de confirmación.
3. Confirmar.
4. Comprobar por la API: `Api GET "/api/evaluacion/asignaciones/$ASIG/reactivar/"` (cuenta) y, tras confirmar, el panel.

**Resultado esperado.**

* El botón muestra el número `N` de suspendidos y la hoja dice «Vas a reactivar a N alumnos» (el número es el que da el nodo, `GET …/reactivar/`).
* Tras confirmar, todos pasan a `en_curso`, cada uno con su reloj congelado intacto, y las tabletas vuelven solas a sus preguntas.

**Evidencia a guardar.** Captura de la hoja de confirmación; panel antes y después.

**Efectos colaterales / limpieza.** Un asiento `evaluacion.intento.reactivado` por alumno.

---

### HP-EVA-10 · El equipo del aula se reinicia durante el examen

**Objetivo.** Si el equipo del profesor (el nodo) se reinicia con exámenes en curso, **ninguno se entrega ni se anula**: pasan a `restaurando` con el reloj congelado y el profesor los reactiva.

**Requisitos que demuestra.** BR-051 · INV-010 · AC-073 · D-15 · DEC-038 · INV-018.

**Precondiciones.** Alumnos 1 y 2 con intento en curso y respuestas ya dadas. Un momento en que el reinicio no afecte a nadie más (es producción: **coordinar la ventana**).

**Datos / actor.** Operador con permiso para reiniciar el servicio; profesor en OPS.

**Pasos.**

1. Anotar `respondidas` y `restante_ms` de ambos desde el panel.
2. Reiniciar el servicio del nodo: `Restart-Service AVACOMOPSBackend` (como administrador).
3. Cuando el nodo vuelva (`Api GET '/api/evaluacion/asignaciones/'` responde), abrir el panel.
4. Mirar las tabletas durante un latido.
5. Reactivar a los alumnos (individualmente o «Reactivar a todos»).

**Resultado esperado.**

* Paso 3: ambos intentos están `restaurando` (no `entregado`, no `anulado`), con **las mismas** `respondidas`, el reloj congelado en su último latido y el incidente `reinicio_nodo`.
* Paso 4: las tabletas siguen mostrando su examen (o la tarjeta de pausa), conservan lo respondido y **no** se salen del bloqueo si lo tenían.
* Paso 5: pasan a `en_curso` y sigue el cronómetro desde lo congelado.

**Evidencia a guardar.** Panel antes del reinicio, después y tras reactivar.

**Efectos colaterales / limpieza.** Asientos `evaluacion.intento.restaurado` y `evaluacion.intento.reactivado`. El servicio queda reiniciado.

---

### HP-EVA-11 · Examen supervisado: las salidas de la aplicación quedan registradas

**Objetivo.** En un examen **supervisado** el alumno puede salir de la app, pero el profesor lo verá; la tableta no le muestra ninguna alarma.

**Requisitos que demuestra.** FUN-117 · BR-077 · PAN-062 · `registrar_salidas`.

**Precondiciones.** Una asignación nueva con `nivel_examen = 'supervisado'` (repetir HP-EVA-01 cambiando el nivel). Una tableta cuya capacidad sea **supervisado o mayor** (la Student de Windows sin `AVACOM_EXAM_NO_LOCKDOWN` declara «supervisado»; ver la columna «Capacidad» de Dispositivos). Alumno 1 con intento abierto.

**Datos / actor.** Alumno 1; profesor en OPS.

**Pasos.**

1. En la antesala verificar el texto del nivel («Examen supervisado») y que **no** hay bloqueo de sistema.
2. Abrir el examen. En Windows: **Alt+Tab** a otra ventana, esperar unos segundos y volver. En Android: pulsar el botón **Inicio** y volver desde Recientes.
3. Seguir respondiendo y entregar.
4. En OPS abrir el **expediente** del intento (fila del alumno 1).

**Resultado esperado.**

* Paso 1: la antesala muestra «Examen supervisado» y entre lo que se registra, «Salidas de la aplicación».
* Paso 2: la tableta **no** muestra alarma ni mensaje de infracción.
* Paso 4: la línea de tiempo muestra `salida_de_app` y `regreso_a_app` con hora (hh:mm:ss) y la duración fuera; el panel marca el incidente con severidad **informativa** (chip neutro) y el intento **no** cambia de estado por ello.

**Evidencia a guardar.** Captura del expediente.

**Efectos colaterales / limpieza.** Incidentes en el expediente (son de sólo inserción).

---

### HP-EVA-12 · Admitir una tableta que no alcanza el nivel

**Objetivo.** Una tableta sin la capacidad que pide el examen **no excluye** al alumno: queda esperando y el profesor decide admitirla en un nivel menor, con motivo.

**Requisitos que demuestra.** FUN-116 · BR-075 · BR-076 · PAN-060 · MSG-036.

**Precondiciones.** Una asignación nueva con `nivel_examen = 'controlado'`. La tableta **Windows** sin aprovisionar (capacidad `supervisado` o `abierto`). Alumno 1 sin intento.

**Datos / actor.** Alumno 1; profesor en OPS.

**Pasos.**

1. `Api GET "/api/evaluacion/asignaciones/$ASIG/elegibilidad/"` y mirar el resumen.
2. En la tableta, abrir la antesala del examen y leer el aviso.
3. Tocar **«Comenzar»**.
4. En el panel de OPS (o `Api GET "/api/evaluacion/asignaciones/$ASIG/admisiones/"`) ver la solicitud en espera.
5. Admitir en un nivel menor con motivo: `Api POST "/api/evaluacion/asignaciones/$ASIG/admisiones/<ADMISION>/decidir/" @{actor=$PROF; decision='admitir'; nivel_admitido='supervisado'; motivo='La tableta no está aprovisionada'}` (en OPS, «Admitir» con un motivo de la lista).
6. Observar la tableta.

**Resultado esperado.**

* Paso 1: el resumen cuenta la tableta en `no_alcanzan` (es el dato que alimenta MSG-036 al aplicar).
* Paso 2: la antesala dice «Tu tableta no cumple lo que pide este examen. Puedes tocar «Comenzar» de todos modos: tu profesor decidirá cómo continúas. No pierdes nada.»
* Paso 3: el nodo registra la solicitud (responde **202**: la tableta no pierde nada; se ve en la lista del paso 4) y la pantalla dice «Tu tableta no alcanza el nivel de control de este examen. Tu profesor debe decidir cómo continuar. No cierres esta pantalla: el examen empieza solo.»
* Paso 4: la solicitud está `en_espera` y la fila del panel marca «esperando admisión».
* Paso 5: `200`; la admisión queda `admitido` con `nivel_admitido = "supervisado"`.
* Paso 6: el examen **empieza solo** (sondeo de 3 s) con `nivel_efectivo = "supervisado"`; el reloj arranca en ese momento. El expediente registra el incidente `admitido_bajo_nivel`.

**Evidencia a guardar.** Capturas de la espera y del examen ya abierto; JSON de la admisión.

**Efectos colaterales / limpieza.** Asiento `evaluacion.admision.decidida` (con motivo).

---

### HP-EVA-13 · Examen controlado en Android con Device Owner y Lock Task *(hardware)*

**Objetivo.** En una tableta Android aprovisionada como Device Owner, el examen **controlado** deja la tableta dedicada: el alumno no puede salir hasta entregar, y la tableta informa `aplicado`.

**Requisitos que demuestra.** BR-075 · BR-077 · kiosk.md §3 · `InformeDeBloqueo` · PAN-121 (aviso de seguridad ausente).

**Precondiciones.** Una tableta Android **restablecida de fábrica sin cuentas** y con *Depuración por USB* (ver [`scripts/README.md`](../../scripts/README.md) «Android (una tableta por ADB)»). El APK de Student con el receptor `com.avacom.lms.student.ExamDeviceAdminReceiver`. **Device Owner es irreversible salvo restablecimiento de fábrica.**

**Datos / actor.** Operador con ADB; alumno 1 con esa tableta; asignación con `nivel_examen = 'controlado'`.

**Pasos.**

1. Instalar el APK: `adb install -r Student.apk`.
2. Simular: `.\android\Provision-DeviceOwner.ps1 -DryRun`.
3. Aprovisionar (pide teclear el número de serie): `.\android\Provision-DeviceOwner.ps1 -Serial <SERIE>`.
4. Verificar: `.\android\Provision-DeviceOwner.ps1 -Serial <SERIE> -Verify` (esperar código de salida `0`, con el paquete nombrado).
5. Abrir Student, entrar al aula; en Dispositivos de OPS comprobar el chip de la tableta.
6. Con la asignación `controlado` activa, abrir el examen en la tableta (pasos de HP-EVA-02/03/04) y fijarse en la antesala: «Bloqueo de esta tableta».
7. Con el examen abierto, intentar salir: **Inicio**, **Recientes**, deslizar desde arriba, **Atrás**.
8. Mirar el panel de OPS: la fila del alumno 1 y su bloqueo.
9. Responder, **entregar**, y observar la tableta tras la confirmación.

**Resultado esperado.**

* Paso 4: código `0` y `dpm list-owners` nombra `com.avacom.lms.student`.
* Paso 5: la tableta declara capacidad **«controlado»**.
* Paso 6: la antesala muestra el estado real del bloqueo («dispositivo dedicado al examen…»).
* Paso 7: ninguno de los gestos saca al alumno del examen; Atrás no hace nada.
* Paso 8: `bloqueo.resultado = "aplicado"` (todas las capas) y **ningún** aviso ámbar de bloqueo parcial.
* Paso 9: **sólo tras el acuse del nodo** a la entrega, la tableta suelta el bloqueo y vuelve la navegación normal; antes no.
* No aparece ningún incidente `bloqueo_parcial` ni `bloqueo_fallido`.

**Evidencia a guardar.** Salidas de los scripts con el código de salida; fotos/capturas de los intentos de salir; panel con `aplicado`.

**Efectos colaterales / limpieza.** La tableta queda como Device Owner (sólo se deshace con restablecimiento de fábrica). Si se necesita sacar a un alumno antes de entregar: **cierre forzado** del profesor (no hay PIN por defecto; ver §8).

---

### HP-EVA-14 · Examen controlado en Windows con Assigned Access *(hardware)*

**Objetivo.** En un equipo Windows aprovisionado con Assigned Access (o Shell Launcher), con la Student de escritorio, el examen **controlado** aplica además la capa de aplicación: gancho de teclado, pantalla completa, monitores cubiertos y cierre rechazado.

**Requisitos que demuestra.** BR-075 · BR-077 · kiosk.md §4 · FUN-117.

**Precondiciones.** Un equipo Windows de pruebas con **acceso físico**, una **cuenta administradora de recuperación distinta** de la del kiosco y la Student instalada en `C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe` (ajustar a la ruta real). **Sin** `AVACOM_EXAM_NO_LOCKDOWN`. Idealmente con un segundo monitor.

**Datos / actor.** Operador (administrador local); alumno 1; asignación `controlado`.

**Pasos.**

1. En una consola de PowerShell **como administrador**, en la carpeta `scripts`: `Get-ChildItem .\windows | Unblock-File`.
2. Simular: `.\windows\Install-Kiosk.ps1 -ExecutablePath 'C:\Program Files\AVACOM\Student\Avacom.Lms.Student.exe' -DryRun` y revisar que no haya líneas `[ERROR]`.
3. Aplicar (el mismo comando **sin** `-DryRun`; pide teclear `APLICAR`).
4. **Reiniciar** e iniciar sesión como el usuario del kiosco: la Student se abre sola.
5. Verificar (como administrador, en otra sesión): `.\windows\Install-Kiosk.ps1 -ExecutablePath '<ruta>' -Verify`.
6. Con el examen `controlado` abierto en esa tableta: pulsar **tecla Windows**, **Alt+Tab**, **Esc**, **F11**, **Alt+F4**; intentar cerrar la ventana; si hay segundo monitor, mirarlo.
7. En OPS: panel y expediente del intento.
8. Responder, entregar y probar de nuevo una tecla de salida.

**Resultado esperado.**

* Paso 5: código `0` = aprovisionado (`1` = no, `2` = no se pudo comprobar sin privilegios).
* Paso 6: ninguna de esas teclas saca al alumno del examen ni cierra la app; el monitor adicional está **cubierto**; la ventana está en pantalla completa.
* Paso 7: `bloqueo.resultado = "aplicado"`; el expediente muestra los incidentes `tecla_bloqueada` **agrupados por minuto** (no uno por tecla), `cierre_bloqueado` y, si hay segundo monitor, `pantalla_adicional`. Las pulsaciones bloqueadas y los cierres rechazados no cambian el estado del intento.
* Paso 8: tras la entrega confirmada el bloqueo de aplicación se suelta y las teclas vuelven a funcionar.

**Evidencia a guardar.** Salida de los scripts con códigos; fotos de la pantalla; expediente con los incidentes.

**Efectos colaterales / limpieza.** Revertir al terminar: `.\windows\Remove-Kiosk.ps1 -DryRun` y luego `.\windows\Remove-Kiosk.ps1`; reiniciar y comprobar con `-Verify` que dice «NO APROVISIONADO». **Ctrl+Alt+Supr no se puede interceptar desde ninguna aplicación** (límite conocido, no un fallo de este caso).

---

### HP-EVA-15 · Degradar el nivel en curso

**Objetivo.** Con el examen en curso, el profesor **baja** el nivel de control y las tabletas sueltan lo que ya no se exige, sin interrumpir a nadie.

**Requisitos que demuestra.** FUN-118 · BR-076 · plan de bloqueo en cada latido.

**Precondiciones.** HP-EVA-14 o HP-EVA-13 en marcha (alumno 1 con el examen `controlado` aplicado) o, sin hardware aprovisionado, una tableta con la capa de aplicación.

**Datos / actor.** Profesor en OPS.

**Pasos.**

1. En OPS, **bajar el nivel** de la asignación a `supervisado` con un motivo, o: `Api POST "/api/evaluacion/asignaciones/$ASIG/degradar/" @{actor=$PROF; nivel_examen='supervisado'; motivo='La tableta no soporta el bloqueo'}`.
2. Esperar un latido (5–10 s) y observar la tableta.
3. Mirar el expediente.

**Resultado esperado.**

* Paso 1: `200`; la asignación pasa a `nivel_examen = "supervisado"` y queda `nivel_declarado = "controlado"`.
* Paso 2: la tableta suelta lo que ya no se exige (por ejemplo, las teclas vuelven a funcionar) **sin** interrumpir el examen, y el estado de bloqueo se informa al nodo.
* Paso 3: cada intento vivo muestra el incidente `degradacion`. Subir el nivel por esta vía **no** es posible (queda fuera de este documento).

**Evidencia a guardar.** Expediente con el incidente; asiento en la bitácora.

**Efectos colaterales / limpieza.** Asiento `evaluacion.nivel.degradado` (con motivo).

---

### HP-EVA-16 · Tiempo agotado: entrega automática

**Objetivo.** Cuando el tiempo se acaba, el nodo entrega el examen **solo** con lo respondido; la tableta lo dice con una frase tranquila y el sistema no anula nada.

**Requisitos que demuestra.** D-15 · INV-017 · INV-018 · incidente `tiempo_agotado`.

**Precondiciones.** Una asignación nueva con tiempo fijo corto: `tiempo = @{modo='fijo'; limite_seg=120}` (el resto como HP-EVA-01). Alumno 1 con el examen abierto.

**Datos / actor.** Alumno 1.

**Pasos.**

1. Abrir el examen y responder una o dos preguntas.
2. **Dejar correr** los 120 s sin entregar.
3. Observar la tableta.
4. `Api GET "/api/evaluacion/intentos/<INTENTO>/"`.

**Resultado esperado.**

* Antes del final el cronómetro **nunca** cambia de color ni suena.
* Paso 3: la tableta lleva sola a la pantalla de entrega con «Se acabó el tiempo y tu examen se entregó solo. Lo que respondiste está guardado.»
* Paso 4: `estado ∈ {entregado, en_revision_docente, calificado}`, `origen_entrega = "tiempo"` y el incidente `tiempo_agotado`; **ninguno** `anulado`.

**Evidencia a guardar.** Captura de la entrega automática; JSON del paso 4.

**Efectos colaterales / limpieza.** Asiento `evaluacion.enviada`.

---

### HP-EVA-17 · Fecha límite endurecida: cierre y entrega automática

**Objetivo.** El profesor pasa la fecha límite de «blanda» a «endurecida»; al vencer, la asignación **cierra** y los intentos abiertos se entregan solos con lo respondido.

**Requisitos que demuestra.** FUN-106 · FUN-107 · FUN-115 · BR-074 · D-14.

**Precondiciones.** Asignación nueva con plazo blando y `limite_en` ≈ 4 minutos en el futuro (milisegundos del reloj del nodo: tomar `servidor_en` de cualquier respuesta y sumar 240000). Alumno 1 con el examen abierto y respuestas dadas.

**Datos / actor.** Profesor; alumno 1.

**Pasos.**

1. `Api POST "/api/evaluacion/asignaciones/$ASIG/endurecer/" @{actor=$PROF}`.
2. Esperar a que pase `limite_en`.
3. Observar la tableta y el panel.
4. `Api GET "/api/evaluacion/asignaciones/$ASIG/"`.

**Resultado esperado.**

* Paso 1: `200` y `plazo = "endurecido"`.
* Paso 3: la tableta muestra «Venció el plazo y tu examen se entregó solo. Lo que respondiste está guardado.»; el panel pasa al alumno a entregado.
* Paso 4: `estado = "cerrada"`; el intento tiene `origen_entrega = "plazo"` y el incidente `entrega_automatica`. Ningún intento queda `anulado`.

**Evidencia a guardar.** Capturas y JSON de la asignación.

**Efectos colaterales / limpieza.** Asientos `evaluacion.plazo.endurecido` y `evaluacion.asignacion.cerrada`.

---

### HP-EVA-18 · Cerrar la asignación, liberar y ver los resultados del grupo

**Objetivo.** El profesor cierra la evaluación (entregando lo que siga abierto), libera los resultados y ve el resumen del grupo con promedio sólo cuando hay datos suficientes.

**Requisitos que demuestra.** DEC-032 · `POST …/cerrar/` · `POST …/liberar-resultados/` · `GET …/resultados/`.

**Precondiciones.** Asignación con ≥ 3 alumnos que hayan presentado (los alumnos 1, 2 y 3; los intentos con la abierta ya revisados, HP-EVA-05, o sin abierta).

**Datos / actor.** Profesor en OPS.

**Pasos.**

1. Con un alumno todavía en curso, **cerrar**: `Api POST "/api/evaluacion/asignaciones/$ASIG/cerrar/" @{actor=$PROF; motivo='Fin de la prueba'}`.
2. Liberar: `Api POST "/api/evaluacion/asignaciones/$ASIG/liberar-resultados/" @{actor=$PROF}`.
3. Ver resultados: `Api GET "/api/evaluacion/asignaciones/$ASIG/resultados/"` (en OPS, la pantalla **Resultados**).
4. En las tabletas, abrir «Mis evaluaciones» y **«Ver resultado»**.

**Resultado esperado.**

* Paso 1: el intento que seguía abierto queda **entregado** con `origen_entrega = "cierre"` y la tableta lo dice («Tu profesor cerró el examen y tu trabajo se entregó. Lo que respondiste está guardado.»). Los alumnos sin intento quedan `sin_intento`.
* Paso 2: `liberados_en` fijado (con intentos todavía abiertos, el nodo lo rechazaría: por eso se cierra primero).
* Paso 3: una fila por destinatario; con **3 o más** entregas calificadas, `datos_suficientes = true` y `promedio_porcentaje` con dos decimales; con menos, la pantalla dice «Con menos de 3 entregas no se calcula un promedio» y el promedio es nulo.
* Paso 4: cada alumno ve **su** resultado (porcentaje, aprobado/ámbar, pregunta por pregunta).

**Evidencia a guardar.** JSON de resultados; capturas de la pantalla Resultados y de un resultado de alumno.

**Efectos colaterales / limpieza.** Asientos `evaluacion.asignacion.cerrada` y `evaluacion.resultados.liberados`. La asignación pasa sola a `archivada` a las 24 h.

---

### HP-EVA-19 · Anular un intento entregado (decisión humana)

**Objetivo.** Sólo una persona identificada, con motivo, puede anular un intento **ya entregado**; el expediente lo registra con su nombre.

**Requisitos que demuestra.** INV-018 · D-23 · PAN-062 · `evaluacion.anulada`.

**Precondiciones.** Un intento entregado de la asignación de prueba (cualquiera de las anteriores). El profesor identificado (sesión o `actor`).

**Datos / actor.** Profesor titular.

**Pasos.**

1. En OPS abrir el **expediente** de un intento ya entregado. Verificar que, mientras un intento está en curso, el expediente **no** ofrece anular.
2. En el intento entregado, usar la acción de anular con un motivo de la lista (o: `Api POST "/api/evaluacion/intentos/<INTENTO>/anular/" @{actor=$PROF; actor_rotulo='Profesor de prueba'; motivo='Prueba de producción'}`).
3. Volver a abrir el expediente.

**Resultado esperado.**

* Paso 2: `200`; el intento queda `anulado` con `anulado_por` = el profesor, `anulado_en` y el motivo.
* Paso 3: el expediente dice «Anulado por *nombre* · motivo». El alumno ve «Este intento no cuenta: habla con tu profesor».
* El sistema **nunca** anuló por sí solo en ninguno de los casos anteriores.

**Evidencia a guardar.** Captura del expediente anulado; JSON del paso 2.

**Efectos colaterales / limpieza.** Asiento `evaluacion.anulada` (sensible, con motivo). Usar un intento de prueba: **la anulación no se revierte** desde las pantallas.

---

### HP-EVA-20 · Todo el ciclo queda asentado en la bitácora

**Objetivo.** Cada decisión relevante del ciclo dejó un asiento en la bitácora de MOD-019 y la cadena de huellas sigue íntegra.

**Requisitos que demuestra.** MOD-019 · catálogo `evaluacion.*` · integridad de la cadena.

**Precondiciones.** Se ejecutaron HP-EVA-01 a HP-EVA-19 (o los que apliquen). Un usuario **Administrador** con `audit.read`.

**Datos / actor.** Administrador.

**Pasos.**

1. Consultar los asientos del módulo: `GET <NODO>/api/auditoria/asientos/?modulo=evaluacion&limite=100` (con el JWT del administrador).
2. Verificar la cadena: `POST <NODO>/api/auditoria/verificar/`.

**Resultado esperado.**

* Aparecen, según los casos ejecutados, las acciones `evaluacion.asignada`, `evaluacion.iniciada`, `evaluacion.enviada`, `evaluacion.intento.pausado`, `evaluacion.intento.reactivado`, `evaluacion.intento.restaurado`, `evaluacion.admision.decidida`, `evaluacion.nivel.degradado`, `evaluacion.plazo.endurecido`, `evaluacion.revision.publicada`, `evaluacion.resultados.liberados`, `evaluacion.asignacion.cerrada` y `evaluacion.anulada`, cada una con actor, objeto y (las que lo exigen) motivo.
* Los asientos de calificación y de anulación llegan **enmascarados** salvo que el administrador tenga una escalada vigente de `audit.read` (BR-131).
* La verificación de la cadena responde sin salto (`estado` verificada; `salto_en` vacío).
* Cada consulta deja a su vez un asiento `auditoria.consulta_realizada`.

**Evidencia a guardar.** JSON de la consulta y de la verificación.

**Efectos colaterales / limpieza.** La consulta y la verificación dejan sus propios asientos.

---

## 6 · Orden de ejecución y dependencias

| Orden | Casos | Depende de |
|---|---|---|
| 1 | HP-EVA-01 | P-1 a P-6 |
| 2 | HP-EVA-02 → 03 → 04 | 01 |
| 3 | HP-EVA-05 | 04 |
| 4 | HP-EVA-06 → 07 → 08 → 09 | una asignación nueva con alumnos presentando |
| 5 | HP-EVA-10 | 06 (coordinar la ventana de reinicio) |
| 6 | HP-EVA-11, 12, 15, 16, 17 | cada uno con su **asignación nueva** |
| 7 | HP-EVA-13 y HP-EVA-14 | aprovisionamiento con acceso físico (los últimos: son los que dejan huella en el equipo) |
| 8 | HP-EVA-18 y HP-EVA-19 | intentos entregados de los casos anteriores |
| 9 | HP-EVA-20 | al final, con todo ejecutado |

---

## 7 · Registro de ejecución

| HP | Fecha | Ejecutor | Resultado (OK/FALLA) | Evidencia (ruta) | Observaciones |
|---|---|---|---|---|---|
| HP-EVA-01 | | | | | |
| HP-EVA-02 | | | | | |
| HP-EVA-03 | | | | | |
| HP-EVA-04 | | | | | |
| HP-EVA-05 | | | | | |
| HP-EVA-06 | | | | | |
| HP-EVA-07 | | | | | |
| HP-EVA-08 | | | | | |
| HP-EVA-09 | | | | | |
| HP-EVA-10 | | | | | |
| HP-EVA-11 | | | | | |
| HP-EVA-12 | | | | | |
| HP-EVA-13 | | | | | |
| HP-EVA-14 | | | | | |
| HP-EVA-15 | | | | | |
| HP-EVA-16 | | | | | |
| HP-EVA-17 | | | | | |
| HP-EVA-18 | | | | | |
| HP-EVA-19 | | | | | |
| HP-EVA-20 | | | | | |

---

## 8 · Fuera de alcance

* **Caminos tristes y malos**: tabletas rechazadas, 4xx, respuestas mal formadas, un cliente que intenta fabricar incidentes, resultados pedidos antes de liberarse (sólo se constata la ausencia de nota en HP-EVA-05), entregas tardías por decidir, etc. Los cubren las pruebas automáticas: `backend/evaluacion/tests/` (304 pruebas) y `tests/Avacom.Lms.Core.Tests/`.
* **Carga**: la latencia con 50 tabletas latiendo a la vez no se ha medido y no entra en este plan.
* **Salida administrativa con PIN** (siete toques sobre el título): el PIN es local de cada tableta y **no tiene valor por defecto**; quién lo genera y cómo viaja durante el aprovisionamiento es la pregunta abierta **Q-83**, así que el caso no se puede escribir todavía. La vía que sí funciona es el **cierre forzado** del profesor (`POST /intentos/{id}/cerrar/`).
* **Lo que ningún software puede probar**: Ctrl+Alt+Supr y el apagado forzado por hardware.
* **«Aplicar examen» desde la clase con la biblioteca real**: depende de que la vista del docente incluya los objetos de modo `exam` (hueco conocido); mientras tanto el caso aplica por la API (HP-EVA-01).
