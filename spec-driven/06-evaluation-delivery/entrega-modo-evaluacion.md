# 06 · Modo Evaluación · Entregables de la implementación (2026-10-13)

| Campo | Valor |
|---|---|
| Módulo | MOD-010 Evaluation & Delivery Engine (+ hooks en MOD-019 Audit) |
| Pedido | «Implementación del Modo Evaluación de AVACOM LMS» (RF-001…RF-014) |
| Punto de partida | MOD-010 construido el 2026-10-01 ([introduccion.md](introduccion.md), [backend.md](backend.md), [frontend.md](frontend.md), [modelado-datos.md](modelado-datos.md)) |
| Resultado | Brechas cerradas sin reescribir módulos; 58 pruebas nuevas de backend, 51 nuevas de cliente; versión del producto 2.6.0 |

---

## 1 · Diagnóstico (Fase 1): qué ya existía y qué faltaba

| Requisito | Estado al empezar | Qué se hizo |
|---|---|---|
| RF-001 Banco de preguntas desde AVACOM Contenido | **Existía**: `infraestructura/fuentes_examen.py` lee `pool` y `questions` de la API v2 sin tocar `biblioteca/`; versión congelada en asignación e intento | Se añadió la **ficha del examen** (`GET /examenes/`) para que el profesor vea el banco antes de asignar |
| RF-002 Selección aleatoria por alumno | **Existía**: `dominio/armado.py` determinista por semilla `asignación‖alumno‖número`, sin repetición, por temas y dificultad; congelada en `m10_intento_formal.armado` | **Faltaba** que el profesor fijara la cantidad y que el nodo rechazara un banco insuficiente; `mezclar_opciones` se guardaba sin usarse. Hecho (D-29) |
| RF-003 Configurar evaluaciones | Existía la pantalla de OPS con nivel, tiempo, plazo, intentos, resultados (3 políticas), reactivación | Se añadieron «¿Cuántas preguntas por alumno?» y «¿Cuándo ven su resultado?» (5 políticas, fecha); `descripcion` en el modelo |
| RF-004 Publicación controlada | Existía `tras_liberar`/`al_entregar`/`nunca` con `liberados_en` y DEC-032; el defecto lo decidía la biblioteca | **Rehecho**: cinco políticas, defecto manual institucional, liberación automática con el reloj del nodo, publicación por alumno, quién y cuándo, eventos y asientos (D-26…D-28) |
| RF-005/006 Student | Existían la lista, antesala, examen, entrega y resultado | Los **ocho estados visuales** en `EstadoDeEvaluacion.cs` (incluye «entrega pendiente de sincronización» leyendo la cola cifrada) y «Resultado: …» en la antesala |
| RF-007/008 Persistencia y deduplicación | **Existía y se reutiliza**: `ColaExamen` (AES-GCM, secuencia persistida antes de enviar, acuse antes de borrar) y `dominio/respuestas.fusionar` (intento+pregunta+sesión+secuencia; gana la sesión más reciente) | Sin cambios |
| RF-009 Eventos y outbox | **Existía**: `m10_evento_salida` en la misma transacción | Dos contratos nuevos versionados; `resultados_liberados.v1` con `origen`, `por`, `politica` |
| RF-010/011 Corrección | **Existía**: lote a `/v2/evaluate/batch`, `open` a revisión docente | Sin cambios (los tipos los publica la biblioteca, Q-79) |
| RF-012 Panel | Existía ordenado por quién necesita al profesor | Contadores nuevos: sin señal, calificación pendiente, reactivos por revisar, listos para publicar, publicados; `resultado_publicado` por fila; acciones de publicación |
| RF-013 Modelo | Cinco tablas `m10_*` | Migración `0002`: 4 columnas en `m10_asignacion`, 2 en `m10_intento_formal`, 4 `CHECK` |
| RF-014 Pruebas | 302 pruebas | +58 (`test_publicacion.py`, `test_seleccion.py`) y ajuste de 1 |

---

## 2 · Archivos creados y modificados

**Backend (Django)**

| Archivo | Cambio |
|---|---|
| `evaluacion/dominio/catalogos.py` | Políticas (`RESULTADOS`, sinónimos, `RESULTADOS_QUE_LIBERA_EL_NODO`, orígenes), `QUE_SIGUE` nuevos, eventos `resultado_intento_liberado.v1` y `resultados_configurados.v1`, acciones de auditoría |
| `evaluacion/dominio/asignacion.py` | `validar_publicacion`, `validar_preguntas` (400 `banco_insuficiente`), `validar_estrategia`, `grupo_finalizado`, `publicacion_vencida` |
| `evaluacion/dominio/intento.py` | `ultimo_por_alumno` (compartido por motor, panel y publicación) |
| `evaluacion/models.py` · `migrations/0002_publicacion_de_resultados.py` | `descripcion`, `publicar_en`, `liberados_por` (asignación); `liberado_en`, `liberado_por` (intento); `CHECK` |
| `evaluacion/aplicacion/motor.py` | `asegurar_publicacion`, `liberar_resultados` (única escritura de `liberados_*`), `resultado_disponible` con políticas y publicación por alumno, hook al calificar |
| `evaluacion/aplicacion/asignaciones.py` | `CrearAsignacion` (preguntas, estrategia, cubrir_temas, mezclar_opciones, descripcion, publicación, defecto institucional), `LiberarResultados` firmado, **`ConfigurarPublicacion`**, **`FichaDelExamen`** |
| `evaluacion/aplicacion/calificacion.py` | **`LiberarResultadoDelIntento`**; `PublicarIntento` y `ResultadoDelAlumno` aplican la política |
| `evaluacion/aplicacion/intentos.py` | `que_sigue` por política; `mezclar_opciones` honrado; anular revisa el grupo |
| `evaluacion/aplicacion/panel.py` | Contadores RF-012, `resultado_publicado` por fila, `vista_publicacion`, `/mias/` con política y fecha, antesala con `publicar_en` y `descripcion` |
| `evaluacion/aplicacion/barrido.py` | Bucle de publicación pendiente (`publicadas` en el resumen) |
| `evaluacion/aplicacion/base.py` · `infraestructura/contenedor.py` · `avacom_lms/settings.py` | `resultados_por_defecto` ← `AVACOM_EVAL_RESULTADOS_POR_DEFECTO` |
| `evaluacion/infraestructura/repositorios.py` | Columnas nuevas en `CAMPOS_*` |
| `evaluacion/infraestructura/fuentes_examen.py` | Sin semilla no se barajan las opciones |
| `evaluacion/interfaces/serializers.py` · `views.py` · `urls.py` | Campos nuevos; `ExamenesView`, `PublicacionView`, `LiberarResultadoView` |
| `audit/dominio/catalogos.py` | `evaluacion.resultado.liberado`, `evaluacion.resultados.configurados` |
| `evaluacion/tests/test_publicacion.py` (nuevo, 24) · `test_seleccion.py` (nuevo, 16) · `test_barrido.py` · `test_capturar_contrato.py` | Pruebas y captura de fixtures |

**Cliente (.NET MAUI / Core)**

| Archivo | Cambio |
|---|---|
| `Core/Evaluacion/ModelosEvaluacion.cs` | `PoliticasDeResultados`, `FichaDeExamen`, `ResultadoLiberado`; campos nuevos en `AsignacionDeExamen`, `NuevoExamen`, `TotalesDelPanel`, `FilaDelPanel`, `FilaDeResultados`, `ResultadosDeExamen`, `EntregaDeIntento`, `EvaluacionDelAlumno`, `MiIntento`, `DatosDeLaAntesala`, `IntentoPublicado` |
| `Core/Evaluacion/IExamenApi.cs` · `EvaluacionApi.cs` | `FichaAsync`, `ConfigurarPublicacionAsync`, `LiberarResultadoAsync`; `CrearAsync` con los campos nuevos |
| `Ops/Pages/ExamenAplicarPage.xaml.cs` | Ficha del banco, «¿Cuántas preguntas por alumno?», «¿Cuándo ven su resultado?» (5 políticas + hora) |
| `Ops/Pages/ExamenPanelPage.Cabecera.cs` | Contadores RF-012, pastilla de publicación, «Publicar resultados/ahora», **«Cambiar publicación»** |
| `Ops/Pages/ExamenResultadosPage.xaml.cs` | Columna «Publicación» y botón **Publicar** por alumno; resumen con quién/cuándo |
| `Ops/Examen/ExamenTexto.cs` | `ResultadosLegible` (5 políticas), `PoliticaCorta`, `Publicacion` |
| `Student/Examen/EstadoDeEvaluacion.cs` (nuevo) · `EvaluacionesPage.cs` · `ExamenAntesalaPage.cs` | Ocho estados visuales; «Resultado: …» y descripción en la antesala |
| `tests/Avacom.Lms.Core.Tests/PublicacionDeResultadosTests.cs` (nuevo, 12) · `Fixtures/evaluacion/*.json` (regenerados + 3 nuevos) · `tests/Avacom.Lms.Student.Tests/EstadoDeEvaluacionTests.cs` (nuevo, 39) | Pruebas de contrato y de rutas |

**Documentación**: [modelado-datos.md](modelado-datos.md) (D-26…D-29, columnas, eventos, Q-85/Q-86), [backend.md](backend.md) (§4.1, §4.3, §4.4, §8, §9, §10), [frontend.md](frontend.md) (§3.3, §3.7, §6), `installer/version.json` (2.6.0).

---

## 2.1 · Ajuste posterior (2026-10-13): la entrada del profesor desde el menú principal

**Problema visto en una clase real**: con AVACOM Contenido real el examen no aparece en la secuencia de la clase (el aula pide el curso con `mode=class`; el examen es de modo `exam`), así que «Aplicar examen» no se ofrecía. **Solución sin tocar la capa de biblioteca**: `ContenidoEvaluacion.examenes_disponibles` (adaptador propio de `evaluacion`, pide cada curso con `mode=exam`), caso de uso `ExamenesDisponibles` (suma cuántas veces se aplicó cada examen y si hay una aplicación abierta) y ruta `GET /api/evaluacion/examenes/disponibles/`. En OPS, un hexágono **Evaluaciones** en el menú principal (celda libre a la izquierda de «Calendario») lleva a la página `evaluaciones`: exámenes de los cursos instalados con **el mismo buscador de «Clase de hoy»** (texto sin tildes + País, Nivel y, bajo «Más filtros», Grado y Materia; el examen hereda la clasificación de su curso, `FiltroDeExamenes` en Core) y, debajo, los exámenes ya aplicados con su panel.

Comprobado en vivo contra la AVACOM Contenido 2.2.0 de este equipo: lista los **7 exámenes de los 7 cursos instalados** (el de «Guerra Fría y América Latina», 70 preguntas, incluido), y la pantalla de OPS se vio con captura: lista, búsqueda por texto («fracciones» deja 1 de 7), «Sin resultados» con «Limpiar filtros». Pruebas: `evaluacion/tests/test_examenes_disponibles.py` (6), `FiltroDeExamenesTests` (14) y 4 de ruta en `PublicacionDeResultadosTests`. Sin ver en vivo: los selectores desplegados (País, Nivel, Grado, Materia), que UI Automation no invoca.

---

## 3 · Arquitectura implementada

Se conservó la arquitectura hexagonal de MOD-010: dominio puro (`dominio/`), casos de uso por puertos (`aplicacion/`), adaptadores (`infraestructura/`) y vistas delgadas (`interfaces/`). La publicación es responsabilidad de **MOD-010** (quién puede ver qué y cuándo, con el reloj del nodo); la nota publicada y los ajustes siguen siendo de MOD-011, que no existe. **No se tocó `biblioteca/` ni las fuentes de cursos del aula**: la ficha del examen lee con `fuentes_examen` (adaptador propio del módulo).

Flujo: Profesor → `GET /examenes/` (ficha) → `POST /asignaciones/` (preguntas, política) → el nodo arma el examen de cada alumno al abrir el intento (semilla, congelado) → la tableta guarda cada respuesta en `ColaExamen` y la envía con secuencia → el nodo deduplica, autocalifica al entregar y deja en revisión lo abierto → el profesor revisa, publica la calificación y **publica el resultado** (a todos o a uno) o lo hace la política (`programada`/`al_finalizar_grupo`) con el reloj del nodo → el alumno ve su nota sólo cuando `Motor.resultado_disponible` lo dice.

## 4 · Modelo de datos y migraciones

`m10_asignacion`: `resultados` (char 20, cinco políticas), `publicar_en` (bigint nulo), `liberados_por` (char 64), `descripcion` (text). `m10_intento_formal`: `liberado_en` (bigint nulo), `liberado_por` (char 64). `CHECK`: `programada ⇒ publicar_en`; `liberados_en ⇒ liberados_por ≠ ''`; `liberado_en ⇒ liberado_por ≠ ''`. Migración `evaluacion/0002_publicacion_de_resultados` (firma como `docente` una liberación previa sin firma). No hay tablas nuevas: todo cabe en las existentes.

## 5 · Endpoints

Nuevos: `GET /api/evaluacion/examenes/?fuente&curso_ref&objeto_ref` · `PATCH /api/evaluacion/asignaciones/{id}/publicacion/` · `POST /api/evaluacion/intentos/{id}/liberar-resultado/`. Ampliados: `POST /asignaciones/` (`preguntas`, `estrategia`, `cubrir_temas`, `mezclar_opciones`, `descripcion`, `resultados` con sinónimos, `publicar_en`), `POST …/liberar-resultados/` (firma y origen), `GET …/panel/`, `GET …/resultados/`, `GET /mias/`, `GET …/antesala/`, `POST …/entregar/`, `POST …/publicar/`, `GET …/resultado/` (403 con `publicar_en`). Reutilizados sin cambio: los 36 restantes.

## 6 · Contratos de eventos

Reutilizados: `evaluacion.intento_abierto.v1`, `respuesta_registrada.v1`, `respuesta_deduplicada.v1`, `intento_entregado.v1`, `autocalificacion.completada.v1`, `revision.solicitada.v1`, `intento_calificado.v1`, `revision_publicada.v1`, `resultados_liberados.v1` (ahora con `origen: manual|programada|grupo`, `por`, `politica`; compatible). Nuevos: `evaluacion.resultado_intento_liberado.v1`, `evaluacion.resultados_configurados.v1`. `calificacion.registrada.v1` pertenece a MOD-011 (no construido); la nota interna sale como `intento_calificado.v1`. Todo en `m10_evento_salida`, en la misma transacción que el hecho (outbox).

## 7 · Selección aleatoria

`dominio/armado.py` (sin cambios): `random_balanced` elige `cantidad` preguntas del banco del curso con dificultad y tiempo totales cercanos al promedio del banco y, si se pide, cubriendo todos los temas; `fixed` da el banco entero. Determinista por semilla (`asignación‖alumno‖número`), por lo que un reinicio de la tableta o del nodo devuelve el mismo examen (`armado` guardado como referencias; el texto se vuelve a pedir con la misma semilla). Nuevo: el profesor fija `preguntas`; más que el banco → 400 antes de iniciar; `mezclar_opciones` decide si viaja la semilla a la fuente (baraja reproducible) o no (orden del banco). Las claves nunca salen del nodo (barrido `sin_claves`).

## 8 · Encolamiento y sincronización

Tableta: `ColaExamen` guarda cada respuesta cifrada **antes** de enviarla, con secuencia monotónica persistida y `ref_cliente` para incidentes; sólo borra tras el acuse del nodo; la entrega sin red queda marcada y sale sola al volver la conexión; los rechazos definitivos (4xx) se descartan, los 5xx y la red se reintentan. Nodo: `fusionar` deduplica por (intento, pregunta, sesión, secuencia) y, entre sesiones de tableta distintas, gana la más reciente; lo que llega tras la gracia espera al profesor (`decidir-envio`). Las dos colas (dispositivo y outbox del nodo) siguen separadas. Sin cambios en esta entrega: se verificó que ya cumplían RF-007/008.

## 9 · Reglas de publicación

1. Escala interna 0–100 (`porcentaje`). 2. El alumno sólo ve su nota si `resultado_disponible` (nodo) lo permite: intento `calificado` sin calificación pendiente **y** (`liberado_en` propio, o `al_entregar`, o `liberados_en` de la asignación); con `nunca`, nunca. 3. Ninguna ruta del alumno lleva `porcentaje`, `puntaje` ni `veredicto` (prueba `NadaSeFiltraTests`). 4. Con reactivos por revisar no hay resultado. 5. Nada parcial. 6. El profesor ve todo en `/resultados/` antes de publicar. 7. Publicación por grupo (`liberar-resultados`) o por alumno (`liberar-resultado`). 8. `liberados_por/liberados_en` y `liberado_por/liberado_en` + asientos `evaluacion.resultados.liberados` / `evaluacion.resultado.liberado`. 9. Cambiar la política deja `evaluacion.resultados.configurados` con valor anterior y nuevo; lo publicado no se retira. 10. `programada` y `al_finalizar_grupo` las resuelve el nodo con su reloj (barrido y lectura perezosa). Defecto: **manual** (`AVACOM_EVAL_RESULTADOS_POR_DEFECTO`).

## 10 · Pruebas ejecutadas

| Suite | Resultado |
|---|---|
| `manage.py test` (suite completa del backend) | **1341 en verde**, 4 omitidas (`jsonschema`), 13,7 min; de ellas 58 nuevas en `evaluacion` |
| Escenarios RF-014 | Banco 100 / examen 20 sin repetir ✔ · reinicio de la app recupera preguntas y respuestas ✔ · dos alumnos, selecciones independientes ✔ · red perdida / restablecida sin duplicar (ya cubierto: `test_respuestas`, `ColaExamenTests`) ✔ · evento enviado dos veces, una sola operación (`test_tst_040…`) ✔ · publicación manual, el alumno no ve antes ✔ · programada, el nodo habilita al llegar la hora ✔ · abiertas esperan revisión ✔ · reinicio del nodo sin duplicar ✔ · versión del banco congelada ✔ · resultados ajenos rechazados ✔ · respuestas tardías con política y evidencia (ya cubierto: `test_plazos`, `DecidirEnvio`) ✔ |
| `dotnet test Avacom.Lms.Core.Tests` | **683 en verde** (12 nuevas; fixtures regenerados desde el backend real) |
| `dotnet test Avacom.Lms.Student.Tests` | **100 en verde** (39 nuevas) |
| Compilación OPS y Student (Windows) | Sin errores ni advertencias (`dotnet build`, en serie: dos compilaciones MAUI a la vez chocan en `Avacom.Lms.Ui`) |
| Prueba de humo en vivo (nodo aislado en `127.0.0.1:8010`, base nueva migrada hasta `evaluacion/0002`, siembra por API, fuente «ejemplo») | **26 pasos en verde**: ficha sin claves → asignación con 6 preguntas y publicación programada → 13 preguntas rechazadas (`banco_insuficiente`) → intento con 6 preguntas distintas, la misma selección al repedir, sin claves → respuestas con `origen: cola` aceptadas y el reenvío deduplicado → entrega con `resultado_programado` y sin nota → 403 al alumno con `publicar_en` → `/mias/` sin nota → panel con los contadores → el profesor ve el estado interno → publicar a un alumno sin calificar: 409 → resultado ajeno: 404 → **el hilo programador del proceso real liberó a la hora fijada** (`liberados_por = sistema`, `liberados_en = publicar_en`) → un intento con la calificación pendiente sigue sin mostrar nada → la política no se cambia tras publicar (409) → por defecto `tras_liberar` → cambio a «al finalizar el grupo» → sin intentos el grupo no «termina». Con la fuente «ejemplo» el nodo **no califica** (la clave vive en la biblioteca), así que el intento quedó `entregado` con `calificacion_pendiente`: el camino con nota (`calificado` → publicar por alumno → el alumno ve su resultado) está cubierto por las pruebas automatizadas con el calificador de referencia |

El humo destapó un detalle que se corrigió: la liberación programada se fechaba en el tick del barrido (hasta 5 s después) y no en la hora fijada; ahora `liberados_en = publicar_en` (como `cerrada_en = limite_en` en el cierre por plazo) y la bitácora guarda además `aplicado_en`.

**Instaladores 2.6.1** (`installer/version.json`; reconstruidos al final del ajuste del menú principal, con la suite completa del backend y el ensayo del paquete dentro del build de OPS). Sin cambio en lo que ya respondían las rutas: Student 2.6.0 sigue entrando.

| Paquete | Dónde | Resultado |
|---|---|---|
| AVACOM OPS Master 2.6.1 | `installer/latest/AVACOM-OPS-Master-Setup-2.6.1.exe` | 104,2 MB · SHA256 `46F73376B642776F94E1E9297B044D800500D203D20DDDB08A237B332932C046` · revisión 802526bc + 84 archivos sin confirmar |
| AVACOM Student 2.6.1 (Windows) | `installer/student-windows/latest/AVACOM-Student-Setup-2.6.1.exe` | 64,7 MB · SHA256 `90006CBBA2670F1D876DC53F9E62F7334ECC6CB189635AFB647FD49DA78CDA3F` |
| AVACOM Student 2.6.1 (Android) | `installer/student-android/Student LMS 2.6.1.apk` | 21,2 MB · SHA256 `77601ACC3DFDD5D0ADCA88DBADD5A8E46F2E92D5341483DCBE63113E3758C7D5` (firmado con la llave de depuración, como las anteriores) |

Nota: `backend/tools/sembrar_evaluacion.py` (herramienta de desarrollo, no se ejecuta en el producto) se arregló después del primer empaquetado: desde el acceso de octubre el primer arranque exige `pin_maestro` y la herramienta no lo mandaba. Los paquetes 2.6.0 ya no son los vigentes: los reemplazan los 2.6.1 de arriba.

## 11 · Limitaciones, pendientes y decisiones

* **No probado en vivo**: las pantallas nuevas de OPS y Student compilaron y sus reglas están probadas sin interfaz, pero no se abrieron contra un nodo ni con tabletas. No se probó con AVACOM Contenido real (este equipo tiene la 2.1.7; la ficha y el armado usan las rutas `pool`/`questions` del contrato 2 por el host de pruebas, como siempre).
* **MOD-011 no existe**: la nota publicada y los ajustes posteriores siguen siendo provisionales en MOD-010 (`puntuar`/`publicar`), como ya decía D-17; `calificacion.registrada.v1` no se emite.
* **Tipos de reactivo**: la biblioteca publica 6 (+ `drag_drop` en el contrato 2 sin editor táctil); arrastrar y soltar, matemática con equivalencias y proyecto dependen de ella (Q-79).
* **Sin teclado en OPS**: `descripcion` existe en el modelo y la API, pero la pantalla de aplicar no la escribe (el nodo principal no tiene teclado); Student la muestra si viene.
* **Decisiones a confirmar con el CTO**: D-26 (el defecto deja de salir de `showResults`), D-27 (`al_finalizar_grupo` con varios intentos y con quien nunca empezó: Q-85), Q-86 (dónde vive la política institucional).
* **Alcance de la asignación**: el backend admite `seleccion` (alumnos sueltos); OPS sigue asignando por grupo (táctil).
