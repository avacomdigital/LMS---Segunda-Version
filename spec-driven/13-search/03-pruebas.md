# 13 · Search (MOD-021) · Pruebas

Fecha: 2026-10-14. Qué se probó, con qué resultado y —con la misma claridad— **qué no se pudo comprobar**.

## 1 · Resultado

| Suite | Pruebas | Resultado |
|---|---|---|
| `manage.py test search` (backend) | 144 (143 + 1 de captura de contrato que sólo corre con `AVACOM_CAPTURAR_CONTRATO`) | **OK** |
| `manage.py test` de los módulos que toca (acceso, audit, modo_estudio, classroom_engine, biblioteca, expediente, device_manager) | 861 | **OK** (3 omitidas que ya lo estaban) |
| `manage.py test evaluacion gradebook cola_medios` | 662 | **OK** (2 omitidas que ya lo estaban) |
| `Avacom.Lms.Core.Tests` (C#) | 810, de ellas 39 de Search | **OK** |
| `Avacom.Lms.Ops.Tests` (C#) | 132, de ellas 12 de Search | **OK** |
| OPS compilado para Windows | — | 0 errores, 0 advertencias |

## 2 · Las pruebas del Documento Maestro

| Prueba | Cómo se cumple | Dónde |
|---|---|---|
| **TST-044** · contenido desactivado | Lo que la biblioteca retira deja de salir en la consulta siguiente sin que Search haga nada (`test_lo_que_la_biblioteca_retira_deja_de_aparecer_en_el_acto`); una evaluación archivada o un grupo desactivado desaparecen aunque el índice no lo sepa y se purgan | `test_catalogo.py`, `test_seguridad.py` |
| **TST-073 (alta, bloqueante)** · búsqueda filtrada por permiso | Dos docentes con grupos distintos: cero resultados fuera del alcance, y **ni rastro** en el JSON (título, fragmento, grupo, id) para 5 consultas; el filtro de grupo ajeno devuelve 0; vale para los tres tipos | `TST073Tests` |
| **BR-088 con el índice rezagado** | Sin sincronizar: quitar al docente del grupo, desactivar el grupo, archivar o borrar la evaluación y renombrarla surten efecto en la siguiente consulta | `RevocacionConIndiceRezagadoTests` |
| **BR-095 / TST-052** · búsqueda en archivo (V1) | **No implementado ni medido** (§4) | — |

## 3 · Lo demás que se probó

- **Texto (28):** normalización con tildes y ñ (`año` ≠ `ano`), raíces, fragmentos, interpretación de la consulta, la expresión FTS5 y la escalera de relevancia.
- **Búsqueda por HTTP (26):** tildes, plural, prefijo, varias palabras (todas → alguna), sinónimos y su administración, 15 formas de sintaxis hostil, **el SQL no contiene lo escrito** (se mide con `execute_wrapper`), relevancia, paginación de 7 resultados en páginas disjuntas, tipos, grupo y ciclo, que buscar no cambia nada en los módulos dueños, y la clase sin grupo.
- **Seguridad (27):** por rol (alumno 403, técnico no busca pero reconstruye, reportes sólo el catálogo, profesor sin `reindex`), el detalle del estado sólo con `search.reindex`, sin sesión y sin actor declarado sólo el catálogo, sesión obligatoria, abrir lo ajeno = abrir lo inexistente (mismo cuerpo) con su asiento, abrir tras perder el acceso, y las opciones de filtro sólo con lo autorizado.
- **Indexación (25):** construcción inicial, los tres módulos, borradores y archivadas fuera, **idempotencia** (la cola entera se vuelve a leer tres veces: ni un documento ni un evento más), cambio y purga con su evento, la **marca avanza en la misma transacción** (un fallo a medias no la adelanta), una entidad que falla no detiene a las demás y **tras 5 ciclos se deja atrás con asiento**, la cola de un módulo que no contesta, reconstrucción (recupera todo, dos veces da lo mismo, no con una clase en curso, no pisa una en marcha pero sí una abandonada, si falla deja el índice anterior), estados, y los eventos: sólo los que ocurren y la cola rechaza los de V1.
- **Catálogo (24):** el adaptador contra respuestas de `/v2/search`, `/v2/tree` y `/v2/courses` (incluidas las preguntas, que no entran), errores de la biblioteca, mezcla y relevancia entre fuentes, paginación conjunta, biblioteca cerrada, filtros del árbol sobre lo del LMS, `content.read`, abrir con la biblioteca cerrada (503).
- **Arquitectura (13):** el dominio y la aplicación no importan Django ni conocen a otros módulos; las vistas no tocan el ORM; **ninguna tabla ni columna de curso, lección, pregunta o clave** (artículo 14); **sólo `catalogo.py` habla con la biblioteca y sólo con 4 funciones de lectura**; Search nunca lee `m07/m08/m10`; el SQL no se arma con texto del usuario; las acciones de bitácora y los permisos están donde corresponde; la matriz de roles sembrada coincide con las plantillas.
- **Contrato con C#:** el backend captura 15 respuestas reales (`Fixtures/search/`) y `ContratoSearchTests` las deserializa con los DTO.
- **Cliente C#:** URL, método y cuerpo de cada ruta, sin campos vacíos, con `ñ` y tildes codificadas, errores con código, nodo apagado, el JWT como pase; textos de estado, resumen, avisos y las búsquedas recientes; y en OPS: quién ve la tesela y adónde lleva cada resultado.

**Rendimiento** (medición suelta, base temporal, 3 000 documentos de evaluaciones y clases): la consulta FTS5 tarda **1–2 ms** para un docente con 5 grupos y **3–5 ms** para la administración (300 candidatos); indexar los 3 000 documentos en una transacción, **4,1 s**. Cada candidato se verifica con una lectura por clave primaria al dueño (≈ 300 como máximo por consulta).

## 4 · Verificación en vivo (OPS + nodo aislado)

Nodo propio (`127.0.0.1:8010`, base temporal, sesión obligatoria, siembra por la API: dos profesoras con sus grupos, una evaluación, un estudio y clases), una biblioteca de pruebas (el host v2 del repositorio con `/v2/search` y `/v2/tree` añadidos **sólo en el guion de prueba**) y OPS compilado con un perfil de pruebas, manejado por UI Automation. El nodo del aula (`:8000`) y la biblioteca real no se tocaron.

| Paso | Visto |
|---|---|
| Menú principal como profesora | La tesela **Buscar** (lupa) aparece entre «Estudiantes» y la celda vacía, en el mismo estilo hexagonal ([01](capturas/01-menu-principal.png)) |
| **Un clic de ratón real sobre la tesela** | Abre la pantalla Buscar (las teselas no se pueden invocar por UI Automation) |
| Escribir «Matemáticas» | 2 resultados desde el backend: el estudio asignado (por la materia) y el curso de la biblioteca, con el árbol y «matemáticas» resaltado ([03](capturas/03-matematicas.png)) |
| «estados» | 12 resultados de las dos fuentes, con icono, tipo, estado, contexto y fragmento ([06](capturas/06-estados.png)) |
| Filtros por UI | Tipo = Clases / Evaluaciones / Cursos deja sólo ese tipo; Clases + Octavo A deja la clase ([21](capturas/21-clases-octavo-a.png)); «Limpiar» vuelve a la pantalla inicial |
| Abrir un **curso** | La pantalla del curso en «Clase de hoy» con sus lecciones |
| Abrir una **evaluación** | El panel del examen («Octavo A · 2 alumnos») |
| Abrir una **clase** terminada | Su cierre («Clase terminada», [11](capturas/11-destino-class.png)) |
| Abrir un **estudio** | Su detalle «ASIGNACIÓN · Fracciones en casa» |
| Volver con «Atrás» | Search conserva la consulta y los resultados |
| «Menú principal» y entrar de nuevo, dos veces | Sin vistas duplicadas ni errores |
| **Privacidad:** buscar «confidencial» (la evaluación del Noveno B, de otra profesora) | «Sin coincidencias»; nada del Noveno B en pantalla |
| Una letra | «Escribe al menos dos letras para buscar» |
| Inicio | Búsquedas recientes y materias como botones ([10](capturas/10-inicio-filtros-nuevos.png)) |
| Se borra el enlace de la biblioteca | Aviso «AVACOM Biblioteca no está disponible» y siguen las evaluaciones y clases ([15](capturas/15-biblioteca-cerrada.png)) |
| Se apaga el nodo | «No hay conexión con el nodo del aula» con «Reintentar» (no «sin resultados», [16](capturas/16-sin-conexion.png)) |

Hallazgos de la verificación, ya corregidos: los selectores cortaban su texto («Todos los tipo»), el aviso de la biblioteca cerrada sobrevivía a un error del nodo, y la descripción de una clase repetía su estado en bruto.

## 5 · Lo que NO se pudo comprobar

- **Contra AVACOM Contenido real.** No estaba encendida en el equipo (no había `link.json`). El adaptador se probó contra el contrato publicado (`openapi.v2.json`, que la 2.1.7 instalada repite) y contra un host de pruebas; **no se ha visto un `/v2/search` real**. Hay que repasar, con la biblioteca abierta, que `scope=all`, `profile=teacher` y los filtros del árbol se comportan como dice el contrato.
- **TST-052** (documento de 120 páginas en ≤ 2 s) y toda CAP-126: no existe todavía el texto extraído de archivos (MOD-014).
- **«Más filtros» por UI Automation**: `GlassButton` no se expone como botón; los filtros de Ciclo, País, Nivel, Grado y Materia usan exactamente el mismo código que Tipo y Grupo (que sí se probaron por UI), y el backend los prueba todos.
- **Teclado en pantalla del equipo táctil.** La escritura se probó por UI Automation; en el equipo del aula sin teclado se espera que Windows muestre el suyo al tocar el campo, pero no se comprobó. Las búsquedas recientes y las materias existen justamente para no depender de él.
- **Carga con 50–100 tabletas y una clase en curso** (el índice se actualiza mientras llegan cientos de eventos de respuestas): la lógica está probada (los eventos irrelevantes no cuentan para «rezagado»), pero no se midió bajo esa carga.
- **El instalador no se reconstruyó** (`installer/latest` sigue con lo anterior). Hay trabajo de otra sesión sin confirmar en el mismo árbol y una compilación a la vez es lo que el instalador no tolera.
- **Nada se confirmó en git** (la autoría y el momento los decide quien lo pida).
