# 13 · Search (MOD-021) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **MVP implementado** (2026-10-14). Backend `backend/search/` (app Django, tablas `m21_*`), cliente `src/Avacom.Lms.Core/Search/`, pantalla **Buscar** en el menú principal de OPS. V1 y futuro documentados y desacoplados (§9). |
| Módulo | **MOD-021 · Search** (DOM-010 · Descubrimiento e Inteligencia). CAP-124 y CAP-125 completas; CAP-128 (reconstrucción) implementada; CAP-126 preparada, CAP-127 no implementada. |
| Contrato | [02-api.md](02-api.md) — rutas, cuerpos, errores, eventos y permisos. |
| Pruebas | [03-pruebas.md](03-pruebas.md) — qué se probó, con qué resultado y qué **no** se pudo comprobar. |
| Se apoya en | MOD-001 (permisos y grupos), MOD-007/008/010 (lo que se indexa), AVACOM Biblioteca (el catálogo, en vivo), MOD-019 (auditoría). |

> **Principio fundamental (Documento Maestro):** Search **no es la fuente de verdad** de nada. Los cursos, las evaluaciones, las clases pertenecen a sus módulos; Search sólo mantiene una proyección **reconstruible** para encontrarlos y no modifica jamás lo original.

---

## 1 · La decisión que cambia el diseño del Maestro: el catálogo NO se copia

El prompt de MOD-021 pide indexar «cursos, contenidos del catálogo, planes de clase y actividades» en un índice local. En este repositorio hay un obstáculo que el Maestro no conocía: el **artículo 14 de la constitución** (`01-constitucion.md`) prohíbe que el backend guarde cursos, lecciones, rótulos o títulos del contenido (14.1 y 14.4, «una tabla *para no llamar tanto a la biblioteca* es una violación, no una optimización»). Y AVACOM Contenido **ya tiene su propia búsqueda** con filtros por el árbol académico: `GET /v2/search` (`scope`: curso, lección, objeto, pregunta; `country`, `level`, `grade`, `subject`, `topic`; fragmento con `**`) y `GET /v2/tree`.

Así que Search se parte en dos fuentes, y cada dato se busca donde vive:

| Qué | Dónde vive | Cómo se busca | Se guarda en el LMS |
|---|---|---|---|
| **Curso · Lección · Recurso** | AVACOM Biblioteca | EN VIVO, en cada consulta, con su `/v2/search` (adaptador `infraestructura/catalogo.py`) | **Nada.** Lo que la biblioteca retira o la política del nodo desactiva deja de salir en ese mismo instante (TST-044) |
| **Evaluación** (examen o actividad asignada) | MOD-010 `m10_asignacion` | Índice local FTS5 | Una proyección mínima: título, descripción, palabras clave, grupo |
| **Estudio asignado** | MOD-008 `m08_asignacion` | Índice local FTS5 | ídem |
| **Clase** | MOD-007 `m07_sesion` | Índice local FTS5 | ídem |

Lo que se guarda de las tres últimas **ya lo guardan sus dueños** (`titulo`, `curso_rotulo`, `grupo_rotulo`…: son rótulos de evidencia histórica, no contenido de curso) y se puede borrar y reconstruir sin perder ningún dato académico. Nunca se proyectan alumnos, respuestas, notas ni claves. Una prueba de arquitectura (`search/tests/test_arquitectura.py`) comprueba que no existe tabla ni columna de curso, lección, pregunta, opción o clave: el único rastro de un curso es su **referencia** `curso_ref`.

**Si el CTO prefiere un índice local del catálogo** (para buscar con la biblioteca cerrada), se añade como una fuente más sin tocar lo demás, pero hay que **enmendar el artículo 14** (14.4) con una excepción explícita y acotada, y aceptar que un resultado que no se puede abrir porque la biblioteca está cerrada no sirve de mucho. Queda como la pregunta S-1 (§10).

## 2 · Arquitectura

Hexagonal, igual que `acceso/`, `evaluacion/` y `gradebook/`:

```
backend/search/
├── models.py                       m21_* (§3)
├── dominio/                        reglas puras; NO importan Django ni DRF
│   ├── catalogos.py                tipos, permisos, estados del índice, eventos, acciones de auditoría, límites, sinónimos de partida
│   ├── errores.py                  ErrorBusqueda y sus hijos (cada uno lleva su código HTTP)
│   ├── texto.py                    normalizar (conserva la ñ), raíz ligera del español, fragmento y resaltado
│   ├── consulta.py                 interpretar y validar la consulta; armar la expresión FTS5 (nunca con texto del usuario crudo)
│   ├── ranking.py                  la escalera de relevancia (§6)
│   └── documento.py                el documento del índice y la Visibilidad de quien consulta
├── aplicacion/                     casos de uso; NO importan Django ni DRF
│   ├── puertos.py                  FuenteLocal · Catalogo · Identidad · Autorizacion · Indice · Marcas · Estado · Sinonimos · Outbox · Auditoria · Reloj · Aula
│   ├── buscar.py                   Buscar (FUN-211/213) y Abrir
│   ├── indexar.py                  Sincronizar (FUN-209/214/217), Reconstruir (FUN-215), Purgar
│   └── consultas.py                OpcionesDeFiltros · EstadoDelIndice · PonerAlDia · Sinonimos
├── infraestructura/                adaptadores
│   ├── repositorios.py             el índice FTS5 + marcas + estado + sinónimos + cola de salida + bitácora
│   ├── fuentes.py                  las tres fuentes locales (por la interfaz `servicios.py` de cada dueño)
│   ├── catalogo.py                 el catálogo de la biblioteca (sólo LEE; ver §1)
│   ├── autorizacion.py            los permisos con la política de MOD-001
│   ├── identidad.py                el padrón (grupos, periodos) — sólo lectura
│   ├── programador.py              hilo del nodo: pone el índice al día cada 5 s
│   └── contenedor.py · unidad_trabajo.py
├── interfaces/                     views.py · urls.py (`/api/search/`)
├── management/commands/search_reconstruir.py
└── tests/                          143 pruebas + la captura de contrato
```

**Interfaces de lectura que se añadieron a los módulos dueños** (BR-004: quien necesita un dato ajeno invoca la interfaz del propietario; Search nunca lee `m07_*`, `m08_*` ni `m10_*`): `evaluacion/servicios.py` → `ultima_secuencia()`; `modo_estudio/servicios.py` → `asignacion()`, `asignaciones()`, `eventos_desde()`, `ultima_secuencia()`; `classroom_engine/servicios.py` (archivo nuevo) → `sesion()`, `sesiones()`, `hay_sesion_activa()`, `eventos_desde()`, `ultima_secuencia()`. Todas de sólo lectura, sin transacción. **La capa de biblioteca no se tocó** (`biblioteca/`, `FuenteDeCursos` y sus adaptadores): el adaptador de Search usa sólo `contenido_v2._pedir`, `_lista`, `cursos` y `esquema_curso`, y una prueba lo comprueba.

## 3 · Tablas `m21_*`

| Tabla | Para qué |
|---|---|
| `m21_documento` | La proyección de una entidad del LMS: tipo, id, título, descripción, palabras clave, contexto, `grupo_id`, `profesor_id`, `curso_ref`, estado, referencia para abrirla y su huella. Única por `(tipo, entidad_id)` |
| `m21_documento_fts` | Tabla virtual **SQLite FTS5** (`titulo, palabras, descripcion, contexto`, tokenizador `unicode61 remove_diacritics 0`). Guarda las **raíces** de las palabras; su `rowid` es el `id` del documento |
| `m21_marca_lectura` | Hasta dónde se leyó la cola de salida de cada módulo (`evaluacion`, `estudio`, `aula`), con los fallos del evento que no se pudo aplicar |
| `m21_estado_indice` | Una fila: construyéndose · consultable · reconstruyéndose, y cuándo se construyó/sincronizó y el último error |
| `m21_sinonimo` | Grupos de palabras equivalentes (de Search, no del contenido). Se siembran seis grupos prudentes |
| `m21_evento_salida` | La cola de salida `busqueda.*.v1` (outbox) |

**Por qué FTS5:** la base ya es SQLite; FTS5 viene compilado en el Python del venv (SQLite 3.49), funciona sin internet, sin un servidor más, con BM25 incluido y se actualiza fila a fila. No hay dependencia nueva.

## 4 · Cómo se cumple BR-088 (sólo lo que el usuario puede leer)

El índice **no decide permisos**. En cada consulta, en este orden:

1. **Qué puede leer la persona AHORA** (`Visibilidad`): por tipo, el alcance de su permiso de lectura en MOD-001 (organización o sus grupos) y sus grupos vigentes (`ContextoActor.grupos_docente`).
2. El índice propone candidatos con la consulta de texto completo **y las reglas de lectura y los filtros dentro del mismo SQL**: se filtra y se ordena antes de contar y de paginar.
3. **Cada candidato se verifica en vivo con su dueño**: existe, es buscable, su grupo sigue activo y la persona sigue pudiendo leerlo con lo que valen *ahora* su grupo y su dueño. Lo que no pasa se descarta; lo que el dueño ya no tiene se **purga** del índice (FUN-217).
4. El catálogo se pregunta en vivo; sólo se le aplica `content.read`.
5. Se puntúa todo con la misma escala, se ordena, **se cuenta lo visible** y recién entonces se pagina. Un candidato descartado no cuenta, no aparece y no deja rastro (ni título, ni fragmento, ni conteo).

Consecuencia: **con el índice rezagado no hay filtración.** Quitarle un grupo a un docente, desactivar el grupo o archivar la evaluación surte efecto en la siguiente consulta, sin esperar eventos (pruebas `RevocacionConIndiceRezagadoTests`).

| Tipo | Permiso de lectura (MOD-001) | Quién lo ve |
|---|---|---|
| curso · lección · recurso | `content.read` | profesorado, administración, reportes |
| evaluación | `assessment.read` | profesorado (sus grupos) · administración (todos) |
| estudio asignado | `study.assignment.review` | ídem |
| clase | `classroom.results.view` | ídem; una clase sin grupo (sin padrón) sólo la ve quien la abrió |

`search.query` abre la búsqueda (profesorado: sus grupos; administración y reportes: la organización); `search.reindex` mantiene el índice (administración y soporte técnico; no da lectura de nada). El alumno no tiene ninguno. Sin sesión (prototipo, Q-34) se puede buscar, pero quien no declara quién es sólo ve el catálogo, nunca lo de un grupo.

**Abrir** un resultado (`POST /api/search/open/`) vuelve a comprobar permiso y vigencia sobre el recurso original; lo ajeno y lo inexistente responden igual (404 `no_disponible`: no se revela qué hay) y el intento sobre algo existente que no se puede leer deja un asiento `busqueda.apertura_denegada` en la bitácora.

## 5 · Mantener el índice (FUN-209, 214, 215, 217)

**No hay MOD-015 todavía**, así que no hay cola unificada: Search sigue el patrón del Gradebook — lee la cola de salida de cada módulo desde **su marca de lectura** y guarda sólo la marca (cuando exista `m15_evento` la marca se llevará allí). **No se creó ninguna cola nueva.**

- **Incremental.** Cada evento *avisa que algo cambió*; el índice vuelve a leer la entidad al dueño y la indexa, la actualiza o la purga. Eventos que se leen: `evaluacion.asignada/…/asignacion_cerrada/resultados_*` (por `asignacion_id`), `estudio.asignacion.creada/cerrada`, `aula.sesion.iniciada/reanudada/suspendida/finalizada`.
- **Idempotente.** Un evento repetido no duplica nada ni emite evento: indexar una entidad cuya huella no cambió no escribe.
- **Atómico y aislado.** La marca avanza en la misma transacción que lo aplicado; una entidad que falla no detiene a las demás: se reintenta y, tras 5 ciclos, se deja atrás **con un asiento** `busqueda.evento_omitido` (nunca en silencio; se corrige con una reconstrucción).
- **Construcción inicial** (el índice nace `construyéndose`): la primera consulta o el hilo del nodo lo construyen desde los módulos dueños.
- **Reconstrucción** (`POST /api/search/reindex/`, `manage.py search_reconstruir`): vacía y vuelve a construir; se confirma de golpe, así que durante la reconstrucción **se sigue consultando**. Precondición del Maestro: **no puede haber una clase en curso** (409 `sesion_activa`). La primera construcción no la exige.
- **Estados.** Guardados: construyéndose, consultable, reconstruyéndose. **Rezagado se deriva** (hay eventos *relevantes* sin aplicar o el último ciclo falló: una respuesta de un examen no cuenta). Un índice rezagado se consulta igual y avisa de que los cambios más recientes podrían faltar.
- **Eventos emitidos:** `busqueda.entidad_indexada.v1` (una por entidad nueva o cambiada), `busqueda.reindexacion_incremental.v1` (por ciclo con novedades), `busqueda.indice_reconstruido.v1`, `busqueda.entradas_purgadas.v1`. **Declarados y no emitidos:** `texto_indexado` y `extraccion_encolada` (V1: no hay extracción de texto todavía; la cola rechaza publicarlos).

## 6 · Texto y relevancia

- **Normalización** (la misma al indexar y al consultar): minúsculas, sin tildes ni signos y **conservando la ñ** (`año` ≠ `ano`; `fracción` = `fraccion`).
- **Raíz ligera del español:** quita el plural y la vocal final cuando queda lo bastante, así `fracción/fracciones`, `matemática/matemáticas`, `examen/exámenes` se encuentran entre sí.
- Las palabras vacías (`de`, `la`…) no estorban; **la última palabra vale como prefijo** (`fracc` → `fracciones`); si ninguna entidad tiene **todas** las palabras se relaja a **alguna** (y se avisa: `match_mode: any`).
- **Sinónimos** configurables (`PUT /api/search/synonyms/`, `search.reindex`): de partida `examen ≈ evaluación ≈ prueba`, `matemáticas ≈ mates`, `lengua ≈ lenguaje`, `inglés ≈ english`, `clase ≈ sesión`, `lección ≈ tema`.
- **Escalera de relevancia** (la política propuesta; no es una regla institucional fija): título exacto 1.00 → título con todas las palabras 0.80 (0.85 si empieza por la consulta) → con algunas 0.55–0.65 → palabras clave 0.45–0.50 → descripción 0.30–0.35 → contexto/sinónimo 0.10–0.20. Dentro de cada escalón desempata BM25 (suma hasta 0.04: nunca salta de escalón). El catálogo, que la biblioteca ya ordenó, se puntúa con la misma escala.
- **Inyección:** la expresión `MATCH` nunca lleva texto del usuario sin pasar por `normalizar` (sólo letras, dígitos y ñ), entre comillas y como **parámetro**; `OR`, `NOT`, `*`, `"`, `NEAR(` escritos por quien busca son palabras más. Hay pruebas con 15 formas hostiles y una que comprueba que el SQL nunca contiene lo escrito.

## 7 · Cliente OPS

- `Avacom.Lms.Core.Search`: `ISearchApi` / `SearchApi` (mismo patrón de `ClienteJson`: un error no es una excepción), modelos, `BusquedaTexto` (textos y validaciones puras).
- **Menú principal:** la tesela **«Buscar»** (lupa, la misma tesela hexagonal que las demás) ocupa la celda libre a la izquierda de «Estudiantes»; la fila de abajo queda de tres teselas, centrada. Sólo la ven quienes pueden buscar (profesorado, administración, reportes). No se creó otro menú ni se rediseñó nada.
- **Pantalla `buscar`** (`BuscarPage`): el mismo diseño ancho de «Evaluaciones» y la misma barra `SearchFilterBar` + `FilterPicker` (se le añadió el evento `Completed` y un `AutomationId`). Tipo y Grupo a la vista; Ciclo, País, Nivel, Grado y Materia bajo «Más filtros». Búsqueda con pausa de 500 ms (sin una petición por pulsación), Enter o «Buscar»; una consulta nueva **cancela** la anterior y lo que llega tarde se descarta; «Mostrar más» pagina de a 20. Cambiar filtros **conserva** lo escrito; «Limpiar filtros» lo borra todo.
- **Sin teclado** (el equipo del aula puede no tenerlo): las **búsquedas recientes** y las **materias** del árbol de la biblioteca son botones.
- **Estados diferenciados:** inicial · buscando · resultados · sin coincidencias · error (sin conexión / sin permiso / fallo del nodo, con «Reintentar») · índice construyéndose o rezagado (aviso, se consulta igual) · biblioteca cerrada (la búsqueda sigue con lo del LMS). No encontrar nada nunca se presenta como no poder buscar.
- **Cada resultado abre la pantalla de su módulo** tras la comprobación del nodo: curso/lección/recurso → el curso en «Clase de hoy»; evaluación → el panel del examen; estudio → su detalle en Modo de estudio (la página ganó el parámetro `asignacion`); clase en curso → la clase en vivo, terminada → su cierre. Volver conserva la consulta y los resultados; la lista se vuelve a pedir en silencio al volver (lo retirado desaparece).

## 8 · Decisiones

| # | Decisión | Por qué |
|---|---|---|
| D-1 | El catálogo se busca en vivo y no se copia (§1) | Artículo 14; la biblioteca ya busca |
| D-2 | Sin cola nueva: marcas de lectura por módulo | No existe MOD-015; igual que el Gradebook |
| D-3 | Los permisos se evalúan en cada consulta con lo vigente; el índice sólo acota | BR-088 con el índice rezagado |
| D-4 | `search.query` y `search.reindex` nuevos; la lectura de cada tipo es el permiso de su dueño | No se construye otro RBAC |
| D-5 | El técnico recibe `search.reindex` y no `search.query` | Restaurar un respaldo es suyo; BR-097 (sin datos académicos) |
| D-6 | «Rezagado» se deriva, no se guarda; sólo cuentan los eventos relevantes | Un estado guardado queda viejo; durante un examen llegan cientos de eventos irrelevantes |
| D-7 | Filtros de ciclo y grupo excluyen el catálogo | Son conceptos del padrón; la biblioteca no los tiene |
| D-8 | Un filtro del árbol acota lo del LMS por el `curso_ref` de cada entidad; con la biblioteca cerrada no se aplica y se dice | No se enseña lo que no se pudo filtrar |
| D-9 | Lo ajeno y lo inexistente responden igual al abrir | No revelar qué hay |
| D-10 | Las preguntas de la biblioteca (`scope=question`) nunca entran | Pueden ser de exámenes |
| D-11 | `class` es lo más cercano a «plan de clase» | MOD-006 no existe; `m07_sesion.plan_id` está reservado |
| D-12 | Una clase sin grupo la ve sólo quien la abrió (o la administración) | Q-34 |

## 9 · Lo que queda (V1 y futuro)

| Capacidad | Estado | Cómo entra |
|---|---|---|
| CAP-124 buscar por texto · CAP-125 filtrar | **Hecho** | — |
| CAP-128 reconstruir tras restaurar | **Hecho** | `POST /reindex/`, `search_reconstruir` |
| **CAP-126** buscar dentro del texto de documentos (V1) | Preparado, **no implementado** | Una nueva `FuenteLocal` sobre MOD-014 (extracción) con `numero_pagina` y fragmento; las tablas `m21_extraccion` y los eventos `texto_indexado`/`extraccion_encolada` se crean cuando exista MOD-014. BR-095: invalidar al borrar o anonimizar el archivo. **TST-052 (120 páginas ≤ 2 s) no se midió** |
| **CAP-127** búsqueda semántica local (futuro) | No implementada | Un segundo ordenador de candidatos sobre el mismo puerto `Indice`, sin reemplazar el textual |
| FUN-212 buscar dentro de un curso o plan | Parcial | El catálogo ya busca lecciones y objetos de los cursos (`scope`); el plan no existe |
| Actividades lanzadas dentro de una clase | No indexadas | Son efímeras; las asignaciones formales (MOD-010) sí |

## 10 · Preguntas abiertas

| # | Pregunta | Propuesta |
|---|---|---|
| S-1 | ¿Indexar el catálogo en el LMS (buscar con la biblioteca cerrada)? Exige enmendar el artículo 14 | No: conservar la búsqueda en vivo |
| S-2 | ¿Debe el soporte técnico poder **buscar**? Hoy sólo mantiene el índice | No (BR-097) |
| S-3 | ¿Mostrar al profesor las evaluaciones de grupos que ya no enseña? Hoy no (BR-088) | No |
| S-4 | ¿Un acceso a Buscar también en el dock y en la cabecera de las pantallas principales? Hoy sólo la tesela del menú | Decidirlo con el UX |
