# 08 · Tiempo real y actividad en clase (MOD-007)

> Cierra los requerimientos **007-01 a 007-13** del cruce del Documento Maestro con el código (2026-09-29).
> Backend: `backend/classroom_engine/` · Núcleo compartido: `src/Avacom.Lms.Core/` · Pantallas: AVACOM OPS y AVACOM Student.
> Pruebas: backend 90 nuevas (`test_tiempo_real` 43 · `test_actividad` 20 · `test_websockets` 18 · `test_autorizacion` 9; la suite completa del backend: 309) · núcleo 36 nuevas (`TiempoRealTests`; la suite del núcleo: 52).
> Verificado en vivo (2026-09-29): Daphne + OPS + Student reales contra un backend de pruebas: el recuadro verde pasa de 3 a 2 conectados al cerrarse un canal, el panel de lanzamiento, el avance en vivo, la espera de cierre, la pausa, el código grande y el cierre se ven y funcionan; la tableta ve la mano, «Proyectando tu pantalla», el cronómetro y el fin de la clase.

## 1. Qué hay y dónde

| Req. | Qué hace | Backend | Núcleo | Pantallas |
|---|---|---|---|---|
| 007-01 | El foco llega por WebSocket en ≤ 3 s (medido) | `interfaces/websockets.py`, `infraestructura/tiempo_real.py` | `AulaSocketClient`, `ConexionAula` | OPS P3 · Student S2 |
| 007-02 | Reanudar tras una caída: detección al arrancar, bloque y minuto | `DetectarCaida`, `ReanudarSesion`, `_recuperacion` | `RecuperacionAula` | OPS «Reanudar clase» · Student «en pausa» |
| 007-03 | Cierre a los **120 min** de inactividad y archivado a 24 h con programador | `CerrarInactivas`, `ArchivarCerradas`, `infraestructura/programador.py` | — | MSG-025 · texto de clase cerrada |
| 007-04 | Presencia automática por latido vencido | `BarrerPresencia`, `LatidoParticipante`, `PerderConexion` | `AulaSocketClient` (latido) | Latido visible · «reconectando» / «salió» declarados |
| 007-05 | Resultados en vivo, rezagados y respuestas del alumno | `EnviarRespuestas`, `ResultadosActividad`, tabla `m07_intento` | `ColaRespuestas`, `SincronizadorRespuestas` | Panel en vivo · responder la actividad |
| 007-06 | Lanzamiento completo y cronómetro de 4 estados | `Distribuir`, `dominio/actividad.cronometro` | `CronometroAula` | Elegir a quién, tiempo, intentos · cronómetro |
| 007-07 | Avance por alumno y espacio libre | `distribuciones[].avance`, telemetría en `m09_dispositivo` | `AvanceActividad`, `DispositivoAula.EspacioLibreMb` | Avance por alumno · confirmar tras abrir bien |
| 007-08 | El cierre no pierde entregas | `CerrarSesion`, `politica_de_recepcion`, `DecidirEnvio` | `SincronizadorRespuestas` | Cierre con espera de 60 s · PAN-132 |
| 007-09 | Cierre y resumen completos | `AnclarSesion`, `SugerirAnclaje`, `MarcarEstudio`, `resumen.detalle` | `AnclajeAula`, `DetalleResumen` | P4 ampliada · aviso de fin de clase |
| 007-10 | Autorización real | `AutorizacionAula`, permisos `classroom.*` (migración `acceso/0006`), freno de `unirse` | `AccesoApi`, `ClienteJson.Token` | Login real · PAN-101/103 |
| 007-11 | Capacidad 50 normal / 100 pico | `_capacidad`, `AulaLlena` | `CapacidadAula` | Aviso informativo · mensaje sin códigos |
| 007-12 | Capa de presentación | rotar código, rechazar, aviso individual (ya existían) | `RotarCodigoAsync` | Modo proyección |
| 007-13 | Mano levantada y proyección de un alumno | `SolicitarAyuda`, `AtenderAyuda`, `ProyectarAlumno` | `AyudaAsync`, `ProyeccionAsync` | Mano junto al nombre · «pedir ayuda» · «Proyectando tu pantalla» |

## 2. El canal WebSocket

`ws://<nodo>:8000/ws/aula/sesiones/<sesion_id>/?rol=docente` ó `?rol=estudiante&participante=<id>` (`&token=<JWT>` con sesión obligatoria).
Todo el protocolo y los códigos de cierre están documentados en la cabecera de `backend/classroom_engine/interfaces/websockets.py`.

**Regla de oro del canal:** un aviso NUNCA lleva contenido académico. Dice **qué** cambió y el cliente pide el estado por HTTP. Por eso el HTTP sigue siendo la fuente de verdad y el respaldo.

| Mensaje del servidor | Quién lo recibe | Para qué |
|---|---|---|
| `hola` | quien se conecta | `servidor_en` (aprende el reloj del nodo), `latido_ms`, `respaldo_ms`; el profesor recibe además `conteo` y `capacidad` |
| `conteo` | sólo el profesor | `{total, conectados, reconectando, esperando, salieron}` cada vez que cambia la presencia de alguien: **es lo que pinta el recuadro verde** |
| `cambio` · `que=selector\|controles\|distribucion\|sesion` | profesor y todas las tabletas | pedir de nuevo el estado |
| `cambio` · `que=aviso` | todas (aviso al grupo) o profesor + tableta (aviso individual) | idem |
| `cambio` · `que=presencia\|ayuda\|proyeccion` | profesor + la tableta afectada | idem |
| `cambio` · `que=resultados\|entregas\|codigo` | sólo el profesor | refrescar el panel de resultados / el código |
| `pong` | quien mandó `ping` | medir el viaje de ida y vuelta |
| `error` + cierre 44xx | quien se conecta mal | 4401 sesión · 4403 permiso o expulsado · 4404 no existe · 4400 petición mal formada |

El cliente manda: `latido` (cada `latido_ms`, con `telemetria: {espacio_libre_mb, bateria_pct}`), `presencia` (`conectado`/`reconectando`/`salio`) y `ping`. El profesor sólo escucha: sus órdenes viajan por HTTP con su permiso y su auditoría.

**Semántica de la conexión en pantalla (UXR-003):** tres valores y nada más: *Conectado* (canal abierto) · *Reconectando* (se cayó hace menos de 10 s) · *Trabajando en el dispositivo* (más de 10 s sin canal). Mientras el canal está caído, la pantalla vuelve a sondear cada 2–3 s; con el canal vivo, sondea cada `respaldo_ms` (15 s) sólo como red de seguridad.

**Medición (007-01):** `GET /api/aula/tiempo-real/` devuelve sockets por sesión y `demora_ms {p50, p95, maximo}` del aviso desde que se confirma el hecho hasta que sale por el socket (objetivo 3000 ms). En la prueba en vivo (Daphne, 2026-09-29): p50 2 ms, p95 4 ms; el selector llega a la tableta en 34–45 ms incluyendo la llamada REST.

## 3. Endpoints nuevos o ampliados (`/api/aula/`)

| Método y ruta | Quién | Notas |
|---|---|---|
| `GET /sesiones/{id}/` | profesor | añade `capacidad`, `manos_levantadas`, `recuperacion`, `anclajes`, `distribuciones[].avance`, `.cronometro`, `resumen.detalle` |
| `GET /sesiones/{id}/estado/?participante=` | tableta | añade `proyectando`, `ayuda_pedida`, `recuperacion`, `cierre`, `pendientes[].cronometro/.intento/.intentos_usados`; `intento.respondidas_refs` (sólo las referencias de lo ya guardado, para no repetirlo al reabrir); **cuenta como latido** |
| `POST /sesiones/{id}/suspender/` · `/reanudar/` | profesor titular | piden `classroom.end` / `classroom.start` |
| `POST …/distribuciones/{id}/respuestas/` | tableta | `{participante_id, respuestas:[{pregunta_ref, secuencia, respuesta, capturada_en?, capturada_en_tableta?}], entregar?, intento_numero?, origen?}` → `{acuse, politica, intento, aceptadas, duplicadas, superadas, rechazadas}`. **Idempotente** por `(intento, pregunta, sesión, secuencia)` |
| `GET …/distribuciones/{id}/resultados/` | profesor | filas por alumno, totales, rezagados; sin promedio con menos de 3 entregas |
| `POST …/distribuciones/{id}/envios/{intento}/aceptar\|descartar/` | profesor | lo que llegó fuera de la gracia (DEC-019) |
| `POST …/distribuciones/{id}/estudio/` | profesor | `{disponible, hasta}` («dejar como tarea de estudio») |
| `POST …/participantes/{id}/ayuda/` `{activa}` | tableta | mano levantada |
| `POST …/participantes/{id}/atender/` | profesor | baja la mano |
| `POST …/participantes/{id}/proyeccion/` `{activa}` | profesor | estado de la proyección de una pantalla (DEC-034); la captura la aportará el cliente (P2) |
| `GET/POST /sesiones/{id}/anclaje/` | profesor | GET = anclajes + sugerencias del curso; POST `{nodos:[{ref, rotulo}]}`; vale con la clase cerrada (BR-040) |
| `GET /tiempo-real/` | diagnóstico | estadísticas del canal |
| `GET /api/acceso/configuracion/` | público | añade `sesion_obligatoria` |

Errores nuevos: `429 demasiados_intentos` (`reintentar_en_ms`) · `409 aula_llena` · `403 no_es_el_titular` · `403 persona_ajena` (una tableta habló por el participante de otra persona: la cola local **no** descarta ese paquete, sólo su dueña puede vaciarlo) · `409 distribucion_cerrada` · `409 intento_entregado` · `409 intentos_agotados`.

## 4. Reglas que las pantallas deben respetar

- **El alumno nunca ve una nota** de una actividad en clase (DEC-032): el acuse de `respuestas/` no lleva veredictos ni puntajes.
- **«Ordenar» y la columna derecha de «relacionar» llegan barajados al alumno** (siempre igual para la misma pregunta): la fuente puede traer los ítems en el orden en que el autor los escribió, y ese puede ser el correcto. El profesor los ve como vienen de la fuente.
- **Guardar nunca falla de cara al alumno** (UXR-004): la respuesta se escribe primero en la cola local del dispositivo (`ColaRespuestas`) y sale sola; el estado es *Guardado · Guardando · Guardado en el dispositivo*, sin estado de error.
- **Ninguna hora del aparato decide nada** (BR-062): la tableta manda `capturada_en` normalizada con `RelojNodo` y conserva la cruda aparte.
- **OPS del nodo no tiene teclado** (nota del proyecto): nada que exija escribir salvo el acceso con credenciales cuando el nodo exige sesión; lo demás, con toques.
- **Sin pantallas de error técnico** (UXR-009): ningún código ni nombre de módulo; el patrón de los mensajes es *qué se conservó · qué falta · qué sigue* (UXR-005).
- **Lo que el rol no puede hacer no se muestra** (UXR-010).

## 5. Pantallas (qué hay en cada aplicación)

**AVACOM OPS** — `Pages/ClaseSesionPage`: el recuadro verde de la esquina superior derecha (`ConteoBox`) se mueve con cada mensaje `conteo` del canal (docente); el chip de conexión tiene los tres valores de UXR-003; avisos de capacidad (pico/lleno), manos levantadas y «reconectando»; panel «Clase recuperada · Reanudar clase» (007-02); código en grande con «Cambiar el código» (007-12); participantes con mano levantada, atender, aviso individual y proyectar su pantalla (007-13); lanzamiento «a quién · tiempo · intentos» (`Controls/LanzarActividadPanel`), avance vivo (`ResultadosActividadPanel`) y espera de 60 s al terminar con alumnos respondiendo (`EsperaDeCierrePanel`). `LoginPage` (acceso real cuando el nodo exige sesión), `ClaseHoyPage` (cierre por inactividad MSG-025, reanudar) y `ClaseCierrePage` (participación, pendientes, tarea de estudio y tema de la clase).

**AVACOM Student** — `Pages/ClaseSiguiendoPage`: canal en tiempo real con latido y telemetría (`Sesion.SocketActual`); chip de tres valores; «Pedir ayuda» (levanta y baja la mano); «Proyectando tu pantalla al grupo» siempre visible con texto; tarjeta de pausa serena que se quita sola; las actividades se **responden** con `Ui/Controls/ActividadResponderView` (cola local durable, cronómetro de cuatro estados, «Guardado / Guardando / Guardado en tu tableta», nunca una nota); fin de la clase con qué se conservó, qué falta y qué sigue. `ConnectionPage` (identificación), `ClaseUnirsePage` (frenos y aula llena) y `CicloDeVida` (reconectando / salió sin que el alumno haga nada).

## 6. Deuda y decisiones abiertas

- **Instalador:** empaqueta el backend con `waitress` (WSGI): sin ASGI no hay WebSocket y las pantallas siguen por sondeo. Hay que pasar `installer/src/payload/avacom_ops_backend.py` a Daphne y sumar `channels`, `daphne` y sus dependencias a `requirements-runtime.txt`.
- **Anclaje curricular (007-09):** hoy es una lista `{ref, rotulo}` en `m07_sesion.anclajes`. El CTO decide entre `clase.tema_id` (un nodo) o `rel_clase_tema` (varios).
- **`intento`** vive provisionalmente en `m07_intento`; pasará a MOD-010 (`m10_`) cuando tenga dueño.
- **Proyección de la pantalla de un alumno (P2):** existe el estado, las salvaguardas y el indicador; falta la captura y su transporte.
- **Preguntas rápidas, temporizador de clase y pizarra (P2):** la frontera de MOD-007 los nombra sin función asociada; no se construyeron.
- **SQLite:** el nodo escribe desde varios hilos (vistas, sockets, programador). `settings.py` activa WAL y `BEGIN IMMEDIATE` (sin esto, una prueba en vivo dio `database is locked`).
- **Identificación (MOD-001):** el login de las dos apps no obliga a cambiar la clave provisional (`debe_cambiar_credencial`): quien la tenga entra y el backend le contesta 403 en las demás rutas. El login de Student no se restringe a alumnos (el `rol` viaja vacío).
- **Tablero de OPS «sólo lo permitido»:** el login devuelve rol, menú y nivel, no los permisos; los hexágonos son posiciones absolutas, así que REPORTS y TECHNICIAN (nivel 2) ven todo el tablero. Hace falta que el login devuelva permisos o un menú por rol.
- **Cola local y tableta compartida:** la cola no guarda la persona dueña de cada paquete; hoy se apoya en el código `persona_ajena` (el paquete se conserva). Con el nodo en `EXIGIR_SESION=1`, vaciarla sin sesión abierta recibe 401: la cola se conserva y sale con la sesión siguiente de su dueña.
- **Nota por alumno con `OcultarNombres`:** el panel de avance del profesor oculta los nombres al proyectarlo al grupo, pero la columna «Nota» sigue visible.
