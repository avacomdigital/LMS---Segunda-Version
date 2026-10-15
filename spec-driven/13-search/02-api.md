# 13 · Search (MOD-021) · API `/api/search/`

Contrato de las rutas. Las respuestas de abajo son las **reales** del backend (capturadas por `backend/search/tests/test_capturar_contrato.py` en `tests/Avacom.Lms.Core.Tests/Fixtures/search/`), recortadas.

Quién actúa: con sesión, quien firma el JWT; sin ella (Q-34, prototipo), el que el cliente declare con `actor`. Con `AVACOM_LMS_EXIGIR_SESION=1` toda ruta exige sesión.

## Rutas

| Método y ruta | Permiso | Para qué |
|---|---|---|
| `GET /api/search/` | `search.query` | Buscar por texto con filtros (CAP-124, CAP-125) |
| `GET /api/search/filters/` | `search.query` | Las opciones de filtro **válidas para quien consulta** |
| `GET /api/search/status/` | `search.query` o `search.reindex` | El estado del índice; el **detalle** sólo con `search.reindex` |
| `POST /api/search/open/` | `search.query` | Volver a comprobar el permiso sobre el recurso original antes de abrirlo (BR-088) |
| `POST /api/search/reindex/` | `search.reindex` | Reconstruir el índice completo (FUN-215); 409 si hay una clase en curso |
| `POST /api/search/sync/` | `search.reindex` | Aplicar ya lo que los módulos publicaron (lo mismo que hace solo el hilo del nodo) |
| `GET · PUT /api/search/synonyms/` | `search.reindex` | Ver o reemplazar los sinónimos |

## `GET /api/search/`

Parámetros (todos validados; un valor inválido es 400 `datos_invalidos`):

| Parámetro | Valor |
|---|---|
| `q` | Texto. 2 letras como mínimo (sin contar espacios ni signos) y 120 caracteres como máximo; ≤ 12 palabras |
| `type` | Uno o varios, separados por coma: `course` · `lesson` · `resource` · `assessment` · `study` · `class` |
| `country` · `level` · `grade` · `subject` · `topic` | El nodo del **árbol académico** de la biblioteca (códigos de `GET /v2/tree`). Acotan el catálogo y, por el curso de cada entidad, lo del LMS |
| `period` | El ciclo (periodo del grupo). **Excluye el catálogo**: no es de ningún grupo |
| `group` | Un grupo (sólo entre los que la persona puede leer). **Excluye el catálogo** |
| `page` · `limit` | Página (1–40) y tamaño (1–50, por defecto 20) |

```http
GET /api/search/?q=estados&type=assessment,class&period=2026
```

```json
{
  "query": "estados",
  "normalized": "estados",
  "total": 5,
  "total_exact": true,
  "page": 1, "page_size": 20, "has_more": false,
  "results": [
    {
      "id": "<id original>", "entity_type": "assessment", "entity_id": "<id original>", "subtype": "examen",
      "title": "Estados de la materia",
      "description": "Examen de los estados de la materia",
      "snippet": "Examen de los estados de la materia", "highlights": [[16, 23]],
      "score": 0.85, "match": "titulo", "source": "local", "status": "activa",
      "context": {"group_id": "…", "group_name": "Octavo A", "period": "2026", "course_ref": "…", "course_label": "Estados de la materia y sus cambios", "lesson_label": "…", "tree_path": []},
      "navigation_target": {"entity_type": "assessment", "entity_id": "…", "group_id": "…", "course_ref": "…", "lesson_ref": "l3-assessment", "object_ref": "l3-exam", "source": "ejemplo"}
    }
  ],
  "filters_applied": {"type": [], "country": "", "level": "", "grade": "", "subject": "", "topic": "", "period": "", "group": ""},
  "match_mode": "all",
  "index_status": "consultable", "index_notice": "",
  "sources": {"local": {"status": "ok", "types": ["assessment", "study", "class"]},
              "catalog": {"status": "ok", "reason": "", "hint": ""}},
  "notice": ""
}
```

- `total` es **lo visible**: ya pasó los permisos y la verificación en vivo; no revela lo que la persona no puede leer. `total_exact` es `false` si se llegó a un tope (300 candidatos locales o más resultados que los que la biblioteca devolvió).
- `match`: el escalón de relevancia (`titulo_exacto` · `titulo` · `palabras_clave` · `descripcion` · `contexto` · `sinonimo`). `highlights`: `[inicio, fin)` dentro de `snippet`.
- `match_mode: "any"` = ninguna entidad tenía todas las palabras y se relajó a «alguna».
- `source`: `local` (índice del LMS) o `catalog` (la biblioteca, en vivo). Los resultados del catálogo traen `context.tree_path` (de país a tema) y `navigation_target.source = "biblioteca"`.
- `sources.catalog.status = "unavailable"` (con `reason` y `hint`): la biblioteca no contestó; la búsqueda siguió con lo del LMS. `notice`: un filtro que no se pudo aplicar (filtro del árbol con la biblioteca cerrada).
- `index_status`: `construyendose` · `consultable` · `rezagado` · `reconstruyendose`. Con `rezagado`, `index_notice` avisa de que los cambios más recientes podrían faltar; se consulta igual.

### Errores

| Estado | `codigo` | Cuándo |
|---|---|---|
| 400 | `consulta_vacia` | Sin texto |
| 400 | `consulta_invalida` | Menos de 2 letras, más de 120 caracteres o más de 12 palabras |
| 400 | `datos_invalidos` | `type`, `limit`, `page` o un filtro inválido (con `parametro`) |
| 403 | `sin_permiso` | El rol no tiene `search.query` (alumno, técnico) |

## `GET /api/search/filters/`

```json
{
  "types": [{"value": "course", "label": "Curso"}, … , {"value": "class", "label": "Clase"}],
  "tree": [{"kind": "country", "code": "CO", "name": "Colombia", "count": 1, "children": [ … ]}],
  "countries": [{"code": "CO", "name": "Colombia"}], "levels": […], "grades": […], "subjects": […], "topics": […],
  "groups": [{"id": "…", "name": "Octavo A", "code": "8A", "period": "2026", "level": ""}],
  "periods": ["2026"], "current_period": "2026",
  "catalog": {"status": "ok", "reason": ""}
}
```

Sólo lo válido para quien consulta: sus **tipos** (reportes ve sólo los tres del catálogo), sus **grupos** (el profesor, los que enseña; la administración, todos los activos) y los **periodos** de esos grupos. El árbol es el de la biblioteca (no se crea un catálogo paralelo); con la biblioteca cerrada llega vacío y `catalog.status = "unavailable"`.

## `POST /api/search/open/`

```json
{ "entity_type": "assessment", "entity_id": "…" }
{ "entity_type": "lesson", "entity_id": "l1", "course_ref": "…" }          // el catálogo pide `course_ref` (y `lesson_ref`/`object_ref` si aplica)
```

→ `200 {"allowed": true, "verified": true, "navigation_target": {…}}`. Lo local vuelve a comprobarse con el dueño (existe, es buscable, su grupo está activo, se puede leer *ahora*); lo del catálogo, con la biblioteca.

| Estado | `codigo` | Cuándo |
|---|---|---|
| 404 | `no_disponible` | Ya no existe, se retiró **o** la persona ya no puede leerlo: mismo cuerpo en los dos casos. Lo segundo deja el asiento `busqueda.apertura_denegada` |
| 503 | `catalogo_no_disponible` | La biblioteca no contestó: no se puede comprobar el recurso del catálogo |
| 400 | `datos_invalidos` | Tipo desconocido o falta `entity_id` / `course_ref` |

## `GET /api/search/status/`

Cualquiera que busca recibe `{"index_status", "index_notice", "queryable"}`. Con `search.reindex`, además `detail`: `documents` por tipo y `total`, `built_at`, `synchronized_at`, `last_error`, `sources` (marca, fallos y pendientes de cada módulo) y el estado del catálogo. **Los conteos del índice no se muestran a quien busca**: revelarían cuántas cosas hay que no puede leer.

## `POST /api/search/reindex/`

Reconstruye el índice desde los módulos dueños. Respuesta: `{"documentos": {"assessment": n, "study": n, "class": n}, "total": n, "duracion_ms": n, "estado": "consultable"}`. Deja el asiento `busqueda.indice_reconstruido`.

| Estado | `codigo` | Cuándo |
|---|---|---|
| 409 | `sesion_activa` | Hay una clase abierta o suspendida (precondición del Maestro) |
| 409 | `reconstruccion_en_curso` | Otra reconstrucción lleva menos de 10 min (una más vieja se considera abandonada) |

## `GET · PUT /api/search/synonyms/`

`PUT {"groups": [["examen", "evaluacion", "prueba"], …]}` reemplaza todos los grupos (palabras normalizadas; un grupo de una sola palabra se ignora; ≤ 500 grupos). Deja el asiento `busqueda.sinonimos_configurados`.

## Eventos (cola de salida `m21_evento_salida`)

| Evento | Cuándo | Carga |
|---|---|---|
| `busqueda.entidad_indexada.v1` | Una entidad nueva o cambiada entra al índice | `{tipo, entidad_id, resultado: nuevo\|actualizado}` |
| `busqueda.reindexacion_incremental.v1` | Un ciclo con eventos aplicados | `{fuente, tipo, eventos, indexadas, purgadas, marca_anterior, marca}` |
| `busqueda.indice_reconstruido.v1` | Termina una construcción o reconstrucción | `{documentos, total, duracion_ms, inicial}` |
| `busqueda.entradas_purgadas.v1` | Se purgaron entradas obsoletas | `{tipo, entradas, causa: evento\|verificacion}` |
| `busqueda.texto_indexado.v1` · `busqueda.extraccion_encolada.v1` | **Declarados, no emitidos** (V1: texto interno de archivos) | — |

## Permisos

`search.query` — profesorado (sus grupos), administración y reportes (organización). `search.reindex` — administración y soporte técnico. Los siembra MOD-001 (`acceso/migrations/0015_permisos_busqueda.py` para lo ya instalado; las plantillas para lo nuevo). Lo que se puede **leer** de cada tipo lo siguen decidiendo `content.read`, `assessment.read`, `study.assignment.review` y `classroom.results.view`.
