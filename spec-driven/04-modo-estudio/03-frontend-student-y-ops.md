# 03 · Modo Estudio (MOD-008) · Frontend: Student y OPS

| Campo | Valor |
|---|---|
| Estado | **Construido y compilado** (2026-09-29). Student y OPS compilan para Windows; el modo de estudio se probó con datos de demostración y contra un nodo de prueba con la biblioteca real (ver §8). Android compila el proyecto pero no se probó en un aparato. |
| Contrato | [02 · Modelo y API](02-modelo-y-api.md): rutas, DTO, decisiones D-1…D-15 y preguntas Q-66…Q-74. Este documento sólo dice **cómo se pintó y cómo se comporta el cliente**. |
| Cambio de requisito (2026-09-29) | «Clase en vivo» sí pide código; **«Modo estudio» no**: como la lección ya está asignada a un grupo, la persona **elige quién es** entre los del grupo y el profesor ve su avance con ese nombre. El LMS es offline y ningún sistema central verifica a nadie, así que se maneja así «hasta nuevo aviso» (**D-15**). |
| Requisitos | La tabla 008-01…008-09 y los 34 apartados del frontend de [01 · Introducción](01-introduccion.md). |
| Dónde está | `src/Avacom.Lms.Student/ModoEstudio/` (pantallas y servicios), `src/Avacom.Lms.Ui/Controls/PracticaEstudioView.cs` (la práctica), `src/Avacom.Lms.Core/Estudio/` (almacén, cola, descargas y servidor local), `src/Avacom.Lms.Ops/Pages/Estudio*.cs` y `DispositivosPage.xaml.cs` (asignar y ver quién completó). |

---

## 1 · Qué ve cada persona

| Quién | Dónde | Qué hace |
|---|---|---|
| **Alumno** (Student) | Hexágono y botón de dock «Modo de estudio» (**en cualquier tableta**, sin código) → **«¿Quién eres?»** → **«Modo estudio · Mis lecciones»** | Elige su nombre; ve lo pendiente, lo descargado y lo completado; descarga una lección para estudiarla sin conexión (si la tableta es suya); la lee, la practica y la completa. |
| **Profesora** (OPS) | Hexágono «Modo de estudio» del tablero → **`EstudioPage`** | Asigna una lección a un grupo o a algunos alumnos, con fecha límite; ve en vivo quién completó; cierra la asignación. |
| **Profesora** (OPS) | «Dispositivos» | Marca una tableta como **asignada a un alumno** o la devuelve al fondo **compartido** (008-01). |

El nodo principal no tiene teclado: **nada de lo de OPS exige escribir** (grupos y alumnos en tarjetas y chips, fecha entre opciones, consigna entre frases).

---

## 2 · Student · «Modo estudio · Mis lecciones»

### 2.0 · «¿Quién eres?» (D-15)

Al abrir «Modo estudio» —**sin pedir ningún código**— la primera pantalla es el selector de nombres, dentro del mismo modal:

```
¿Quién eres?                                                                                      [X]
Elige tu nombre para ver las lecciones que te asignó tu profesor.
┌ ESTA TABLETA ES DE  ·  Ethan Martínez ──────────────────────────────  [ Continuar como Ethan ] ┐   ← o «LA ÚLTIMA PERSONA QUE ESTUDIÓ AQUÍ»
TU GRUPO   ( Quinto B · 5 )  ( Sexto A · 4 )          ← sólo si hay más de un grupo con lecciones asignadas
ELIGE TU NOMBRE   Tu profesor verá tu avance con el nombre que elijas.
( Ethan Martínez ) ( ✓ Sofía Ramírez ) ( Mateo Gómez ) ( Valentina Cruz ) ( Daniel Ortiz )
[ Continuar como Sofía ]
```

- **Quiénes aparecen:** los alumnos de los grupos que tienen al menos una lección asignada y abierta (`GET /estudiantes/`), más los destinatarios de asignaciones a alumnos sueltos. La lista se guarda **cifrada** en la tableta (son nombres de niños; desaparece con la clave) para poder elegir el nombre sin conexión con el aula.
- **Elegir es un toque y confirmar es otro:** elegir por error el nombre de un compañero significaría ver sus lecciones y que el profesor le anote a él lo que hagas.
- **Sugerencia de un toque:** «Continuar como …» ofrece primero a la última persona que estudió en la tableta (o a su dueño, si está asignada), sin darla nunca por hecha: **cada vez que se abre el modo de estudio en una ejecución nueva se pregunta**.
- **Sin nadie que elegir:** «Todavía no hay lecciones asignadas para ningún grupo…» o, sin aula y sin lista guardada, «Conéctate al aula una vez para elegir el tuyo» (con «Reintentar»).
- **Después,** la cabecera dice «Estudias como Sofía Ramírez · Cambiar»; «Cambiar» vuelve al selector sin borrar nada (si se vuelve a elegir el mismo nombre, sigue donde iba). Si se elige a **otra persona**, lo personal de la anterior se va de la tableta (BR-053) y su trabajo sin enviar queda en la cola y sale solo.
- **Nada se verifica.** No hay contraseña ni código: una persona podría elegir el nombre de otra. Es la limitación aceptada del LMS offline «hasta nuevo aviso»; el nodo sólo comprueba que la persona exista, esté activa y que la asignación le alcance (**Q-74** para cuando haya verificación).

### 2.1 · Composición

Modal blanco centrado sobre la retícula de hexágonos del menú, oscurecida (`min(1050 px, 88 %)` de ancho, ~80 % del alto, radio 28). MAUI no desenfoca el fondo en WinUI ni en Android sin código de plataforma, así que el «fondo desenfocado» es la retícula con un velo oscuro. La sombra del modal son tres capas con la misma silueta (la `Shadow` de WinUI sale rectangular bajo una esquina redonda).

```
Cabecera: «Modo estudio» · chip «● Sin conexión» / «DEMOSTRACIÓN»                      [X circular 40×40]
Filtros:  ( Pendientes 6 )  ( Descargadas 5 )  ( Completadas 1 )     ← segmentado: #1D1D1F/blanco · #F5F5F7/#5F6368
Lista:    CollectionView con una tarjeta por lección (única zona que se desplaza)
Pie:      ✓ Guardado · «370 MB en tu tableta · 32,7 GB libres» · barra de descargas activas
```

Estados de la lista: **esqueleto** de tres filas mientras carga (no un spinner), **vacío** «Estás al día» con acción hacia «Completadas», y aviso pasajero cuando algo se movió sin que la persona lo pidiera.

### 2.2 · La tarjeta de una lección

`ASIGNATURA · UNIDAD` (eyebrow) · título · «Continúa desde: Actividad 4 de 7» · barra de avance (#019D60) con el porcentaje · «⏱ Entrega: hoy, 8:00 p. m.» · chips de estado con icono + texto + color (nunca sólo color):

| Estado | Chip | Fondo / texto |
|---|---|---|
| Pendiente | `○ PENDIENTE` | #FFF7D6 / #806600 |
| En curso | `◐ EN CURSO` | #E5F5FB / #02739E |
| Completada | `✓ COMPLETADA` | #E5F6ED / #017A48 |
| Vencida | `! VENCIDA` | rojo 10 % / #C1191D |

El estado «vencida» es **derivado** (la fecha pasó y no está completada) y se calcula con la hora del nodo (`RelojNodo`, BR-062), no con el reloj de la tableta.

**Descarga** (CAP-047): siete estados, con los textos del Maestro.

| Estado | Texto | Acción |
|---|---|---|
| Sin descargar | «Descargar · 84 MB» | Descargar |
| Pedida | «Preparando descarga…» | — |
| Descargando | «Descargando contenido… · 62 % · 2 min restantes» | Pausar |
| Pausada | «Descarga pausada · 41 %» | Continuar descarga |
| Disponible | «Disponible sin conexión» | menú: Ver información · Eliminar descarga |
| Vencida | «El contenido descargado venció.» | Actualizar descarga |
| Denegada | «Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti.» (MSG-046) | — |

La barra global del pie suma las descargas en curso. Una descarga **nunca bloquea la interfaz**: el avance llega por evento y sólo se repinta esa tarjeta.

**Práctica y evaluación son cosas distintas** (BR-055): la práctica es una franja azul propia (`PRÁCTICA · Comprueba lo aprendido · 8 preguntas · Autocalificable`, «Practicar →» o, con intentos, «7 de 8 correctas · ¡Muy bien!» con «Revisar respuestas» / «Intentar nuevamente»). La **evaluación formal** sólo se explica («Ver información»): nunca ofrece «Practicar» ni se llama práctica.

**CTA principal:** «Comenzar lección», «Continuar» (reanuda en el bloque donde se quedó) o «Ver lección» (completadas).

### 2.3 · La lección y la práctica

- **`StudyLessonPage`** enmarca los visores del aula (`AulaContenidoView`: láminas, páginas, laboratorio, audio, video) y una tira de actividades (`StudyBlockChip`). Cada bloque visto se guarda **antes** de enviarse. «Completar» sólo se ofrece con todos los bloques obligatorios atendidos (FUN-087); si faltan, dice cuáles. Con la asignación cerrada se lee pero no se registra nada. Un laboratorio (simulación) **necesita el aula**: el bloque lo dice en vez de fallar (Q-71).
- **`StudyPracticePage`** + `PracticaEstudioView` (Ui): una pregunta a la vez con los editores del aula, «Comprobar» con retroalimentación en ≤ 2 s (NFR-012), navegador de preguntas, «Terminar» y resultado («7 de 8 correctas»; nunca «nota»). Sin el aula, la respuesta se guarda y el resultado dice «Práctica guardada»: se califica al volver (D-6).

### 2.4 · Guardado y conexión

Tres estados y nada más (CMP-002): **✓ Guardado** · **↑ Pendiente de enviar** · **↻ Sincronizando**. El chip «● Sin conexión» es discreto y **no bloquea nada de lo descargado**. «Sin conexión» significa «no se ve el aula» (se le pregunta al aula misma con `GET /estado/`), no «no hay Wi-Fi».

### 2.5 · Accesibilidad y microinteracciones

`SemanticProperties` en cada control, objetivos táctiles de 44–48 dp, estado por icono + texto + color, foco visible. Pulsar un botón lo hunde (escala .98); la lista aparece con un fundido corto; nada parpadea ni rebota.

---

## 3 · Arquitectura del cliente

```
Views (XAML)  ──►  ViewModels  ──►  IStudyModeService  ──►  ┌ IEstudioApi (aula: /api/modo-estudio/)
                                     IDownloadService        ├ IAlmacenEstudio  (lista, tareas y paquetes CIFRADOS)
                                     IConnectivityService    ├ IColaEstudio     (eventos CIFRADOS, secuencia persistida)
                                                             ├ IDescargadorDePaquetes · ISincronizadorEstudio
                                                             └ IServidorLocalDeMedios (127.0.0.1, Range)
```

Regla de oro del cliente: **la pantalla no espera a la red**. Toda acción del alumno se escribe primero en la tableta y después sale sola.

| Pieza | Qué hace |
|---|---|
| `EstudioCompose` | Punto de composición: servicios reales o de demostración (`AVACOM_ESTUDIO_DEMO=1`) y «Salir» (`AlSalirAsync`). El hexágono ya no depende de nada: está siempre (D-15). |
| `StudyModeService` | Mezcla lo del aula con lo local: **quién estudia** (lista de nombres, elegir, cambiar), lista de lecciones (del aula, o de la tableta sin conexión), abrir lección (del paquete si está descargada; si no, en línea), práctica, guardar bloques y respuestas, sincronizar, cerrar sesión. Toda llamada al aula lleva la huella de la tableta y el `alumno_id` elegido. |
| `StudyLessonSession` · `StudyPracticeSession` | Una lección o práctica abierta. Sin lógica de pantalla. |
| `DownloadService` | Una descarga por lección, reanudable; pausar cancela el token y lo bajado se queda. |
| `ConnectivityService` | Pregunta al aula con un tope de 2,5 s; también reacciona al sistema y a cada llamada real. |
| `EstudioLocal` · `ClaveDeStudent` | Lo local de la tableta y su clave AES-256: **DPAPI** en Windows (crypt32, sirve sin empaquetar la app) y **SecureStorage** en Android. |
| `MockStudyModeService` y compañía | La demostración: siete lecciones con todos los estados, descarga simulada y una práctica que se califica en el propio aparato (**la única clave local que existe**, sólo en demo). |

### 3.1 · Trabajo sin red (CAP-048, BR-059, BR-137)

1. El alumno marca un bloque, responde una pregunta, termina la práctica o completa la lección.
2. Se guarda el **avance local** (`TareaLocal`) y se encola un evento (`study.block.viewed`, `study.answer.submitted`, `study.practice.finished`, `study.lesson.completed`) con `emisor_id` (la instalación) y `secuencia` **persistida antes de devolver**.
3. Se intenta enviar a los 700 ms (varios cambios seguidos salen en un envío), al volver el aula, y cada 30 s si algo quedó. **No exige sesión abierta.**
4. El aula acusa recibo (`integrado`, `duplicado`, `rechazado` o `pendiente_decision`); sólo entonces se borra de la cola. Lo que el aula dice de cada tarea y cada veredicto se refleja en la tableta y se repinta esa tarjeta.

Repetir un envío no duplica nada (`UNIQUE(emisor_id, secuencia)`). La secuencia de las respuestas de una práctica crece siempre (segundos del reloj del nodo o la anterior + 1): si el alumno cambia una respuesta, gana la última (INV-013).

### 3.2 · Leer sin red

Una lección descargada se lee **del paquete cifrado**: el manifiesto trae la lección (vista de aula sin claves) y `ServidorLocalDeMedios` sirve sus medios desde `127.0.0.1` con `Range` y una capacidad aleatoria en la ruta, para que los **mismos visores del aula** funcionen sin cambios. Los medios de la lección en línea se piden al aula con `?dispositivo=&alumno_id=` en la URL (los visores no mandan cabeceras).

**Descargar** (BR-054) sigue siendo cosa de la **tableta asignada y de su dueño**: quien elige su nombre en una tableta compartida, o en la de otra persona, estudia con el aula conectada y, si pide llevarse la lección, lee «Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti.» (MSG-046).

### 3.3 · «Salir» (008-07, FUN-089/090, BR-053)

«Salir» **cierra la sesión de estudio en el aula y limpia la tableta**:

- Sin trabajo pendiente: se **destruye la clave** (todo lo cifrado queda ilegible al instante), se borra el almacén, la lista de nombres y la cola vacía. `limpieza = completa`.
- Con trabajo pendiente (se salió sin aula): se borra lo personal (lista de nombres, lista de lecciones, avance, paquetes) y se **conserva sólo la cola cifrada y su clave** — perder lo que el alumno hizo sería peor —, y sale sola (BR-137). `limpieza = pendiente`; en cuanto la cola se vacía (o al próximo arranque, FUN-090) se termina la limpieza y se avisa al aula (`estudio.limpieza.reintentada.v1`).
- El tope de todo esto es de ~2 s por llamada: la persona siguiente no espera (JRN-022).

Esto **también borra las descargas** de una tableta asignada: es lo que dice la tabla (008-07) y BR-053, pero choca con la utilidad de descargar para estudiar en casa. Es la **Q-72** para el CTO.

---

## 4 · OPS · asignar y ver quién completó

`EstudioPage` (ruta `estudio`, hexágono «Modo de estudio» en la celda libre a la derecha de «Clase de hoy») es una página con tres vistas. Columna centrada de 1280 px, la misma familia visual que «Dispositivos».

### 4.1 · Asignaciones (lista)

Filtros **Abiertas / Cerradas / Todas** y una tarjeta por asignación: título, `ASIGNATURA · UNIDAD · GRUPO`, «Entrega: vie 3 oct · 11:59 p. m.» (en rojo si ya pasó y hay quien no terminó), barra «18 de 27 completaron» y conteos en píldoras (completaron · en curso · sin empezar · fuera de plazo · envíos por decidir). Se refresca sola cada 8 s y **sólo repinta si cambió algo** (no salta el desplazamiento).

### 4.2 · Quién completó (detalle)

- **Resumen:** estado, plazo (flexible/estricto), si se puede descargar, entrega, consigna y los cuatro totales.
- **Cambios rápidos:** fecha límite (se elige, se ve qué día queda y **sólo entonces se guarda**), plazo flexible ↔ estricto, «se puede descargar» ↔ «sólo en línea», y **Cerrar la asignación** (con confirmación).
- **Tabla por alumno** con filtros (Todos · Completaron · En curso · Sin empezar · Vencidos · Por decidir): estado, avance («5 de 7 actividades · 71 %»), práctica («7 de 8 correctas · 2 intentos»), paquete («En el aparato», «Descargando»…) y aparato («asignada a este alumno» / «compartida»).
- **Envíos por decidir (BR-074):** lo que llegó fuera de la ventana de gracia con plazo estricto **nunca se descarta en silencio**: aparece bajo el alumno con «Aceptar» y «Descartar».

### 4.3 · Asignar una lección (tres pasos, todo por toques)

| Paso | Qué se elige |
|---|---|
| 1 · Para quién | El **grupo** (tarjetas) y «Todo el grupo» o «Elegir alumnos» (chips que se marcan; «Marcar a todos» / «Quitar a todos»). |
| 2 · Qué lección | **Materia** → **curso** → **lección**, de AVACOM Biblioteca (o del curso de ejemplo con un toque si la biblioteca no está). Una lección que sólo tiene examen no se asigna: la evaluación formal no es estudio. |
| 3 · Cuándo y cómo | **Día** (sin fecha · hoy · mañana · en 3 días · 1 semana · 2 semanas) y **hora** (8:00 · mediodía · 3:00 · 6:00 · final del día); **plazo** flexible o estricto (con **gracia** de 5/15/30/60 min); **descarga** sí/no; **consigna** entre cinco frases. Un resumen cierra el paso. |

Un pie fijo lleva «Atrás» y «Siguiente» (que en el último paso es «Asignar la lección»). Al asignar, se abre el detalle con «Lección asignada a N alumnos». Si la biblioteca no responde, no se asigna a ciegas (503 del nodo, dicho con amabilidad).

### 4.4 · Dispositivos: asignada o compartida (008-01)

Cada tableta dice de quién es («Asignada a Ethan · su dueño puede llevarse las lecciones» / «Compartida del aula · las lecciones se estudian con el aula conectada») y ofrece **«Asignar a un alumno»** (grupo → alumno, con confirmación) o **«Devolver al aula»**. Desde D-15 el perfil **ya no decide quién puede estudiar** (cualquiera elige su nombre en cualquier tableta): sólo decide quién puede **llevarse** las lecciones. Devolver una tableta con un paquete activo o trabajo sin enviar lo dice el nodo (409 `paquete_sin_integrar`) y la pantalla lo explica.

---

## 5 · Requisitos ↔ construido

| Req. | Estado | Dónde |
|---|---|---|
| 008-01 aparato asignado vs compartido | ✔ con la salvedad de D-15 | `perfil`/`asignado_a_id` en `dispositivo` (MOD-009), `GET /estado/`, `DispositivosPage`. **El hexágono ya no depende del perfil**: el alumno elige quién es (pedido del usuario, 2026-09-29); el perfil sólo gobierna las descargas |
| 008-02 asignación nueva | ✔ | `m08_asignacion` (provisional hasta MOD-010), `EstudioPage` |
| 008-03 paquete de estudio | ✔ | `m08_paquete`, `DescargadorDePaquetes`, `AlmacenEstudio`, `DownloadService` |
| 008-04 completar por bloques | ✔ | `StudyLessonSession.CompleteAsync`; el cierre ya no manda `progreso_pct = 100` |
| 008-05 práctica con `modo` separada | ✔ | `m08_practica` con `modo = 'estudio'` (`CHECK`); `PracticaEstudioView` |
| 008-06 trabajo sin red idempotente | ✔ | `ColaEstudio` + `SincronizadorEstudio` + `m08_sincronizacion` |
| 008-07 «Salir» cierra y limpia | ✔ con la salvedad de §3.3 | `StudyModeService.CloseSessionAsync` (**Q-72**) |
| (pedido del usuario) «Modo estudio» no pide código; el alumno elige quién es | ✔ | `¿Quién eres?` (§2.0), `GET /estudiantes/`, `IStudyModeService.GetRosterAsync/ChooseStudentAsync/ChangeStudentAsync` |
| 008-08 permisos `study.*` y eventos `estudio.*` | ✔ | migración `acceso/0007`, outbox `m08_evento_salida` |
| 008-09 alcance por nivel · vista «Mi trabajo» | **No** (se pregunta al CTO) | Q-68; ver §7 |

---

## 6 · Modo demostración

`AVACOM_ESTUDIO_DEMO=1` (o la preferencia `estudio_demo`) enciende siete lecciones de muestra que cubren **todos** los estados (pendiente, en curso, completada, vencida, descarga en cada uno de sus siete estados, con y sin práctica, con evaluación) y una práctica de ocho preguntas que se califica en el aparato. `AVACOM_ESTUDIO_DEMO_OFFLINE=1` la deja «sin conexión». Es la forma de ver la pantalla sin nodo.

---

## 7 · Hallazgo · barra de % de «Asignaturas» contra DEC-032 (008-09)

`AsignaturasPage` y `CursoBibliotecaPage` de Student pintan «N % completado» por curso (avance del expediente). DEC-032 dice que el alumno **no ve avance calculado hacia una calificación** que el profesor no haya formalizado, y que PAN-124 pasa a ser «el espacio de trabajo del alumno», no una vista de progreso. Un porcentaje de contenido visto **no es una calificación**, y el modo de estudio lo trata así (el porcentaje de una lección es «actividades atendidas / obligatorias» y el backend lo documenta como *no es una nota*), pero la barra de cursos sigue siendo un cálculo del sistema a la vista del alumno. **No se cambió**: la decisión es de producto (**Q-73**): conservar la barra como «avance de lectura» o sustituirla por conteos («3 de 8 lecciones»).

---

## 8 · Cómo se probó

1. **Compilación**: Student y OPS para `net10.0-windows10.0.19041.0` sin errores ni advertencias (en una copia de `src` para no chocar con las apps abiertas).
2. **Demostración**: Student con `AVACOM_ESTUDIO_DEMO=1`, capturas de todos los estados y recorrido de la práctica.
3. **Nodo de prueba aparte** (puerto 8010, base de datos propia, `AVACOM_LMS_DB`): grupo «Quinto B» con cinco alumnos, una tableta **asignada** a Ethan y una **compartida**, y la **biblioteca real** (AVACOM Contenido) como fuente. OPS asigna «Conozco las vocales» al grupo; Student la recibe, la descarga, la lee sin red, practica y completa; OPS ve el avance.
4. **Pruebas automáticas**: `dotnet test tests/Avacom.Lms.Core.Tests` (267: cifrado, descarga reanudable con huella, cola, sincronizador, servidor local, JSON canónico, cliente de la API), `dotnet test tests/Avacom.Lms.Student.Tests` (61: la lógica de Student —servicio, sesiones de lección y de práctica, descargas, conectividad— compilando **los mismos archivos** de la app con sustitutos mínimos de MAUI Essentials) y `manage.py test` (584, de ellas 259 de `modo_estudio`: asignaciones, lecciones, paquetes, práctica, sincronización, permisos, identidad declarada, arquitectura).

Para repetirlo, las variables de prueba (`AVACOM_STUDENT_SERVIDOR_PRUEBA`, `…_DISPOSITIVO_PRUEBA`, `…_DATOS_PRUEBA`, `…_PREFIJO_PRUEBA`) **no existen en el código del repositorio**: sólo se aplican a una copia de compilación, para no tocar las `Preferences` que comparte la instancia de quien trabaja en el equipo.
