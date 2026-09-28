# 03 · Classroom Engine · Journey «Clase de Hoy» en AVACOM OPS

| Campo | Valor |
|---|---|
| Estado | **Propuesta cerrada para el siguiente prompt** (el del frontend MAUI). Sustituye, para ese prompt, el recorrido largo de [02 · Sugerencias](02-sugerencias-frontend.md) §5: mismas piezas, menos pantallas |
| Punto de entrada único | El hexágono **«Clase de hoy»** del tablero de AVACOM OPS (`DashboardPage`). Hoy navega a `activity-monitor`, una demo estática; pasa a abrir este journey |
| Fuente de cursos, hoy | **`biblioteca`** por defecto: AVACOM Biblioteca por la API de Contenido v2 ([05](05-contrato-biblioteca.md)). Si la biblioteca no está encendida, P1 lo dice y ofrece **«Usar el curso de ejemplo»** con un toque: el manifiesto [`example.json`](example.json) («Ciencias naturales · Estados de la materia y sus cambios») servido por `/api/aula/…?fuente=ejemplo`. El chip de la fuente alterna entre las dos |
| Alcance | **4 pantallas nuevas en OPS** (P1–P4) y **2 de reflejo en Student** (S1–S2). Todo el journey del profesor ocurre dentro de «Clase de hoy» |
| Contrato | [01 · Modelo de datos y API](01-modelo-de-datos.md) §9 · DTO y mapa de componentes en [02](02-sugerencias-frontend.md) §3 y §4 |
| Restricción física | El nodo principal (OPS) es una pantalla táctil **sin teclado**: nada de este journey exige escribir |

---

## 0 · Contexto guardado

Lo que el siguiente prompt tiene que dar por hecho, sin volver a deducirlo:

1. **Backend listo.** La app `backend/classroom_engine/` (MOD-007) está implementada y probada: consumo del curso normalizado (`/api/aula/cursos/…`, `/api/aula/pruebas/curso/`) y ciclo de vida de la sesión de clase (`/api/aula/sesiones/…`). 161 pruebas en verde. Ninguna tabla guarda el curso; sólo referencias.
2. **Biblioteca conectada por la API de Contenido v2** ([05](05-contrato-biblioteca.md)): `GET /v2/courses/{courseId}?mode=class&profile=…` entrega el curso 1.0 recortado y el mismo normalizador lo sirve. OPS pide `fuente=biblioteca` por defecto y ofrece el ejemplo con un toque cuando la biblioteca está apagada; la tableta no manda `fuente` y el backend resuelve solo la referencia del ejemplo.
3. **Una sola entrada.** Todo MOD-007 vive detrás de «Clase de hoy». No se toca «Asignaturas» (modo libre, `CourseContentView`) ni se crea otra entrada en el menú.
4. **«Materias asignadas».** La lista de materias la da `GET /api/aula/cursos/` agrupada por `classification.subject`. Con la fuente de ejemplo trae **una**: Ciencias naturales, con el curso «Estados de la materia y sus cambios». La asignación real por grupo y docente vendrá de MOD-002 y de la política de la escuela en Biblioteca; el cliente no la calcula.
5. **El journey del profesor es completo hoy**: iniciar la clase, código de unión, ver quién entra, proyectar lámina a lámina, abrir el laboratorio, bloquear y liberar pantallas, lanzar la actividad y ver entregas, avisar al grupo y cerrar con resumen. Todas esas llamadas existen y están probadas.
6. **Sin tiempo real todavía.** OPS refresca la sesión cada 3 s y Student cada 2 s (`intervalo_sondeo_ms`). El WebSocket es Q-51.
7. **Fuera de este módulo**: el examen (`fuera_de_alcance`, MOD-010), la corrección de respuestas (MOD-010 con el flujo de intentos existente, Q-48), el padrón real (MOD-002) y los permisos `classroom.*` (Q-50).
8. **WebView obligatoria.** Los laboratorios (PhET y `html5_canvas`) se muestran en `WebView`. En Windows exige el runtime **WebView2**; el instalador de OPS debe comprobarlo o incluirlo (nota añadida en [02](02-sugerencias-frontend.md) §4.1).
9. **Selector y Device Manager (2026-09-28).** Lo que se proyecta se llama **selector** (`POST …/selector/`, antes «foco»); no es un lanzamiento. La tableta que entra queda en el inventario de MOD-009 (`/api/dispositivos/`, [03-device-manager](../03-device-manager/00-modelo-y-api.md)): la lista de participantes de P3 muestra la tableta de cada uno y permite **bloquearla o desbloquearla**; una tableta bloqueada no entra a clase ni recibe lanzamientos, y el panel «Actividad en curso» dice cuántas quedaron fuera. El tablero ganó el hexágono **«Dispositivos»** (en el lugar de «Asistencia», fuera del MVP) con el inventario y el bloqueo por tableta.

---

## 1 · El journey en una frase

> El profesor toca «Clase de hoy», elige la materia y la lección, la clase arranca con un código en grande, proyecta y controla desde una sola pantalla, y termina con el resumen.

```
 Tablero OPS ──► P1 Materias de hoy ──► P2 Curso y lecciones ──► P3 Clase en curso ──► P4 Cierre
 «Clase de hoy»    (1 asignatura hoy)     «Dar clase con esta        código · proyectar ·    resumen ·
                                            lección» / «Clase libre»   bloquear · lanzar ·      volver
                                                                       avisar · terminar
                                                     Student:  S1 Código de 6 dígitos ──► S2 Siguiendo la clase
```

---

## 2 · Las pantallas de OPS

### P1 · Materias de hoy

| | |
|---|---|
| Qué ve | Título «Clase de hoy». Un hexágono por **asignatura** (hoy uno: **Ciencias naturales**) y, debajo, la lista de sus cursos: «Estados de la materia y sus cambios · Básica secundaria · Sexto · 3 lecciones · 180 min». Chip de estado de la fuente («Curso de ejemplo» o «Biblioteca conectada») |
| Qué toca | El curso |
| Qué llama | `GET /api/aula/cursos/?fuente=ejemplo` → `asignaturas[{codigo, nombre, cursos[ficha]}]` |
| Qué vuelve | La ficha: `curso_ref`, `titulo`, `subtitulo`, `clasificacion.{nivel, grado, asignatura, tema}`, `lecciones`, `duracion_estimada_min`, `portada_url` |
| Si falla | `503` → tarjeta con `detail` + `sugerencia` y botón «Reintentar». Con la fuente de ejemplo ausente, el mismo `503` dice qué ruta espera |

### P2 · Curso y lecciones

| | |
|---|---|
| Qué ve | Cabecera del curso (título, subtítulo, «Sexto · Básica secundaria», portada). Una tarjeta por **lección** con sus objetos como chips con icono y `componente`: ▣ presentación · ▤ lectura · ⌗ laboratorio · ✎ actividad · ✓ examen (atenuado, «lo aplica MOD-010»). Panel plegable con `notas_docente` del curso y de la lección |
| Qué toca | **«Dar clase con esta lección»** (botón grande en cada lección) o **«Clase libre»** (arriba a la derecha) |
| Qué llama | `GET /api/aula/cursos/{curso_ref}/?fuente=ejemplo&rol=docente` para pintar · luego `POST /api/aula/sesiones/` con `{via: "leccion", curso_ref, leccion_ref, fuente: "ejemplo", profesor_id, profesor_rotulo, superficie: "pantalla"}` (o `{via: "libre", …}`) |
| Qué vuelve | `201` con la sesión: `id`, `codigo_union`, `selector` inicial (primer objeto de la lección), `seguimiento: true` |
| Si falla | `409 sesion_activa_existente` → «Ya tienes una clase abierta»: **Continuar** (abre P3 con `sesion_id`) o **Cerrarla y empezar otra**. `404 referencia_no_encontrada` no debería ocurrir desde esta pantalla; se muestra el `detail` |

### P3 · Clase en curso (la pantalla principal)

Es PAN-001 y PAN-022 del Maestro en una sola superficie: el profesor **ve lo que se proyecta y lo controla** desde la misma pantalla táctil.

| Zona | Qué ve | Qué toca | Qué llama |
|---|---|---|---|
| Cabecera | **Código de unión en grande** (≥ 96 pt) · «N conectados» · nombre de la lección · indicador de conexión (CMP-001) | «Ver participantes» despliega la lista | `GET /api/aula/sesiones/{id}/` cada 3 s → `codigo_union`, `conteo`, `participantes`, `selector`, `seguimiento`, `pantallas_bloqueadas`, `distribuciones` |
| Columna izquierda · Secuencia | Los objetos de la lección en orden; el que está en selector resaltado. En una presentación, sus láminas como miniaturas numeradas | Tocar un objeto o una lámina = **proyectar** | `POST …/selector/` `{objeto_ref, unidad_ref?}` → selector vigente |
| Centro · Proyección | `AulaContenidoView` en modo docente: la lámina con sus bloques; el laboratorio en `WebView`; la lectura por páginas; la actividad con sus preguntas en vista previa | ◀ ▶ para lámina anterior / siguiente («Lámina N de M») | `POST …/selector/` con la `unidad_ref` de la lámina vecina |
| Barra de controles (inferior) | Cinco botones grandes: **Bloquear pantallas** (interruptor) · **Seguimiento** (interruptor, encendido por defecto) · **Lanzar actividad** (activo cuando el selector es una actividad) · **Aviso** · **Terminar clase** | Un toque cada uno | `POST …/controles/` `{tipo: "bloqueo"|"seguimiento", activo}` · `POST …/distribuciones/` `{clase: "actividad", objeto_ref}` · `POST …/avisos/` `{texto}` · `POST …/cerrar/` |
| Panel «Actividad en curso» (aparece al lanzar) | «Practica: los tres estados · 2 de 3 entregadas» con barra | **Cerrar recepción** | `POST …/distribuciones/{id}/cerrar/` |
| Hoja «Aviso» | Frases prehechas tocables: «Miren al frente», «Dos minutos», «Guarden lo que llevan», «Levanten la mano si terminaron» | Una frase | `POST …/avisos/` `{texto}` |
| Lista de participantes (desplegable) | Nombre · estado (Esperando · Conectado · Reconectando · Salió) · la tableta con la que entró y, si está bloqueada, la píldora «Tableta bloqueada · sin lanzamientos» | **Admitir** (si espera) · **Expulsar** · **Bloquear tableta** / **Desbloquear** (MOD-009) | `POST …/participantes/{pid}/admitir/` · `…/expulsar/` · `POST /api/dispositivos/{id}/bloquear/` · `…/desbloquear/` |

Si falla: `409 sin_participantes_admitidos` al lanzar → «Todavía no hay tabletas conectadas». `409 sesion_cerrada` o `transicion_invalida` → volver a P1 con aviso. Sin respuesta del backend → el indicador pasa a «sin señal» y los botones se deshabilitan hasta que vuelva; nada se borra.

### P4 · Cierre

| | |
|---|---|
| Qué ve | Confirmación «¿Terminar la clase?». Si hay actividades abiertas, MSG-016: «{n} alumnos siguen respondiendo. Si cierras ahora, se entrega lo que llevan» |
| Qué toca | **Terminar** (y, si hace falta, **Terminar de todos modos**) |
| Qué llama | `POST /api/aula/sesiones/{id}/cerrar/` `{}`; ante `409 actividades_abiertas`, de nuevo con `{forzar: true}` |
| Qué vuelve | `estado: "cerrada"` y `resumen`: participantes, conectados máximo, selectores, distribuciones, actividades, avisos, pendientes, duración |
| Qué muestra | Tarjetas del resumen y botón **«Volver a Clase de hoy»** (P1). Una sesión cerrada no se reabre |

---

## 3 · Reflejo en Student (para que el journey del profesor se vea)

| Pantalla | Qué ve y qué toca | Qué llama |
|---|---|---|
| **S1 · Entrar a la clase** | Seis casillas y teclado numérico en pantalla. Nombre ya conocido (`Sesion.Nombre`) | `POST /api/aula/sesiones/unirse/` `{codigo_union, persona_id, persona_rotulo, dispositivo, participante_id?}` → guarda `participante.id` y `sesion.id` en `Preferences` |
| **S2 · Siguiendo la clase** | Lo que el profesor proyecta (`AulaContenidoView` en modo estudiante). Con `seguimiento: true` no navega. Con `pantallas_bloqueadas: true`, pantalla completa «Mira al frente». Las `pendientes` aparecen como tarjeta «Actividad: …» que se abre con el flujo de intentos existente. Los `avisos` como banda no bloqueante. Botón **Salir** | `GET /api/aula/sesiones/{id}/estado/?participante={pid}` cada 2 s · `POST …/participantes/{pid}/presencia/` `{estado: "salio"}` al salir |

Si la sesión pasa a `suspendida`, S2 muestra «La clase se está reanudando, tu trabajo está a salvo» y sigue sondeando; si pasa a `cerrada`, «La clase terminó» y vuelve al menú.

---

## 4 · Guion de demostración con el curso de ejemplo

Referencias reales de `example.json`, en el orden en que se tocan. Es el recorrido que debe funcionar de punta a punta al terminar el frontend.

| Paso | Dónde | Acción | Llamada | Resultado esperado |
|---|---|---|---|---|
| 1 | Tablero | Tocar «Clase de hoy» | `GET /api/aula/cursos/?fuente=ejemplo` | P1 con **Ciencias naturales** → «Estados de la materia y sus cambios» |
| 2 | P1 | Tocar el curso | `GET /api/aula/cursos/avacom.co.lower-secondary.6.science.states-of-matter/?fuente=ejemplo&rol=docente` | P2 con 3 lecciones; la 3.ª sólo tiene el examen atenuado |
| 3 | P2 | «Dar clase con esta lección» en **Los tres estados de la materia** (`l1-three-states`) | `POST /api/aula/sesiones/` `{via: "leccion", curso_ref, leccion_ref: "l1-three-states", fuente: "ejemplo", profesor_id, superficie: "pantalla"}` | P3 con código de 6 dígitos y selector en **Todo lo que nos rodea es materia** (`l1-lecture`) |
| 4 | Student S1 | Escribir el código | `POST /api/aula/sesiones/unirse/` | S2 muestra la lámina 1; en P3 «1 conectado» |
| 5 | P3 | ▶ dos veces | `POST …/selector/` `{objeto_ref: "l1-lecture", unidad_ref: "l1-lecture-s2"}` y luego `"l1-lecture-s3"` | Lámina 2 (imagen de marcador + lista con negritas) y lámina 3 (video: en el ejemplo, tarjeta «no incluido», `404` explicado) |
| 6 | P3 | Tocar **Escucha y repasa** (`l1-explanation`) | `POST …/selector/` `{objeto_ref: "l1-explanation"}` | Página 1 con audio (WAV de marcador) y texto resaltado; página 2 con el PDF de 3 páginas |
| 7 | P3 | Tocar **Laboratorio: partículas en movimiento** (`l1-lab-phet`) | `POST …/selector/` `{objeto_ref: "l1-lab-phet"}` | La `WebView` carga `…/medios/sim-phet-states/states-of-matter-basics_es.html?fuente=ejemplo` (partículas en movimiento); atribución CC BY 4.0 en el pie |
| 8 | P3 | Encender **Bloquear pantallas** | `POST …/controles/` `{tipo: "bloqueo", activo: true}` | S2 pasa a «Mira al frente» en ≤ 3 s |
| 9 | P3 | Apagar **Bloquear pantallas** | `{tipo: "bloqueo", activo: false}` | S2 vuelve al laboratorio |
| 10 | P3 | Tocar **Practica: los tres estados** (`l1-activity`) y **Lanzar actividad** | `POST …/selector/` y `POST …/distribuciones/` `{clase: "actividad", objeto_ref: "l1-activity"}` | Panel «1 de 1 pendiente»; S2 muestra la tarjeta pendiente con 6 preguntas (opción múltiple, V/F, completar, relacionar, ordenar, abierta), sin ninguna clave |
| 11 | P3 | **Aviso** → «Dos minutos» | `POST …/avisos/` `{texto: "Dos minutos"}` | Banda en S2 |
| 12 | P3 | **Cerrar recepción** | `POST …/distribuciones/{id}/cerrar/` | El panel cambia a «cerrada» |
| 13 | P3 | **Terminar clase** | `POST …/cerrar/` `{}` | P4 con el resumen (1 participante, 5 selectores, 1 actividad, 1 aviso) |
| 14 | P4 | «Volver a Clase de hoy» | — | P1. En S2: «La clase terminó» |

Variante para probar MSG-016: saltar el paso 12 y terminar en el 13 → `409 actividades_abiertas` → «Terminar de todos modos» → `{forzar: true}`.

---

## 5 · Interacciones disponibles hoy en el backend

Todas están implementadas y probadas. La columna «En este journey» dice cuál se pinta en las pantallas P1–P4/S1–S2 y cuál queda para después.

| Interacción | Endpoint | En este journey |
|---|---|---|
| Listar materias y cursos | `GET /api/aula/cursos/?fuente=` | P1 |
| Vista de aula del curso (docente / estudiante) | `GET /api/aula/cursos/{ref}/?rol=` | P2, S2 |
| Una lección o un objeto sueltos | `GET …/lecciones/{ref}/` · `GET …/objetos/{ref}/` | S2 (baja sólo el objeto en selector) |
| Medios (imagen, audio, PDF, simulación, subtítulos, transcripción) | `GET …/medios/{media_ref}/[ruta]` | P3, S2 |
| Iniciar la clase (4 vías) | `POST /api/aula/sesiones/` | P2 (`leccion` y `libre`) |
| Detalle para el profesor | `GET /api/aula/sesiones/{id}/` | P3 (cada 3 s) |
| Unirse / readmitirse | `POST /api/aula/sesiones/unirse/` | S1 |
| Estado para la tableta | `GET …/estado/?participante=` | S2 (cada 2 s) |
| Presencia (conectado · reconectando · salio) | `POST …/participantes/{pid}/presencia/` | S2 (al salir) |
| Admitir · expulsar | `POST …/participantes/{pid}/admitir/` · `expulsar/` | P3 (lista desplegable) |
| Rechazar a quien espera | `POST …/participantes/{pid}/rechazar/` | Después (sólo tiene sentido con padrón) |
| Declarar el selector (objeto, lámina, página, medio) | `POST …/selector/` | P3 |
| Bloquear pantallas · seguimiento | `POST …/controles/` | P3 |
| Lanzar actividad · difundir recurso | `POST …/distribuciones/` | P3 (actividad) |
| Confirmar entrega desde la tableta | `POST …/distribuciones/{id}/confirmar/` | S2 (al abrir la tarjeta) |
| Cerrar recepción · mostrar resultados | `POST …/distribuciones/{id}/cerrar/` · `resultados/` | P3 (cerrar). Resultados: después (los datos son de MOD-010) |
| Aviso al grupo · a una tableta | `POST …/avisos/` | P3 (al grupo, frases prehechas) |
| Rotar el código | `POST …/codigo/rotar/` | Después |
| Suspender · reanudar | `POST …/suspender/` · `reanudar/` | Después (lo dispara MOD-015) |
| Cerrar y consolidar | `POST …/cerrar/` | P4 |
| Listar sesiones (y archivar a 24 h) | `GET /api/aula/sesiones/` | Después (historial) |

---

## 6 · Fuera de este journey

| Qué | Por qué | Dónde queda |
|---|---|---|
| El examen de la lección 3 | Lo ejecuta MOD-010; el aula sólo lo muestra atenuado | Tarjeta `fuera_de_alcance` en P2 y P3 |
| Responder la actividad y ver la nota | Flujo de intentos existente; falta que MOD-010 conozca las preguntas del manifiesto (Q-48) | S2 abre la tarjeta y, por ahora, muestra las preguntas en vista previa |
| Elegir grupo y vía «Nodo del árbol» | Sin MOD-002 ni MOD-003 | P2 sólo ofrece «esta lección» y «clase libre» |
| Tiempo real por WebSocket | Q-51 | Sondeo 3 s / 2 s |
| Video real | El paquete de ejemplo no lo trae | Tarjeta explicativa; funciona con la biblioteca |
| Historial de clases, rotar código, suspender/reanudar, aviso individual, rechazar | Válidos, pero no hacen falta para dar la primera clase | Botones secundarios en una versión posterior de P3 |

---

## 7 · Consideraciones para redactar el prompt del frontend

- **Navegación**: redirigir «Clase de hoy» (hexágono y botón del dock de `DashboardPage`) a la nueva ruta `clase-hoy`; rutas Shell nuevas `clase-hoy` (P1), `clase-curso` (P2), `clase-sesion` (P3), `clase-cierre` (P4) en OPS y `clase-unirse` (S1), `clase-siguiendo` (S2) en Student. `activity-monitor` queda como demo hasta retirarla.
- **Una constante para la fuente**: `Sesion.FuenteAula = "ejemplo"` en OPS y Student; toda llamada la envía como `?fuente=`. Cambiarla a `"biblioteca"` es el único paso cuando Biblioteca publique el manifiesto.
- **Identidad del profesor**: hoy `profesor_id` declarado (por ejemplo `ops-<equipo>` o el nombre del docente elegido en `LoginPage`); con login de MOD-001 lo aporta el JWT y el cliente no cambia.
- **Piezas reutilizables** de [02](02-sugerencias-frontend.md): DTO (§3), `IAulaApi` (§3), `AulaContenidoView` con selectores por `componente` (§4.1–4.2), reglas de `WebView` (§4.3), preguntas (§4.4), tramos (§4.6).
- **Sin teclado en OPS**: selección por toque, avisos prehechos, confirmaciones con botones grandes. El único texto que se escribe en todo el journey es el código de 6 dígitos, y se escribe en la tableta del alumno.
- **Instalador**: la `WebView` de OPS en Windows depende del runtime WebView2; añadir su comprobación o instalación silenciosa al instalador (`installer/`). En Android la `WebView` es del sistema; hace falta `usesCleartextTraffic="true"`.
- **Degradación**: «no se pudo comprobar» nunca se muestra como «no está». `503` con `sugerencia`, `409` con opción de continuar, sin backend con «sin señal» y reintento.
- **Pruebas de aceptación** para el prompt: el guion de §4 completo con una tableta; CA-A01–CA-A08 de [02](02-sugerencias-frontend.md) §2.4.
