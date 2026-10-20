# 14 · Reporting (MOD-013) · El boletín académico individual (2026-10-19)

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-19), sin commit. Backend `backend/reporting/` (migración **0002**), cliente `src/Avacom.Lms.Core/Reporting/`, OPS `Pages/ReporteBoletinPage.cs`, `Pages/ReporteBoletinesPage.cs`, ajustes en `ReportesEstadoPage`, tarjeta «Boletín académico» en `ReportesPage`. |
| Origen | «Propuesta de boletín de calificaciones 2026 — AVACOM OPS» del CTO: un **boletín académico individual** sobre un modelo de información común, con plantillas por país, nivel y sistema de evaluación, que responde cuatro preguntas; el XLSX y el CSV actuales «son muy básicos para lo que realmente necesita el profesor». |
| Decisiones | D-32 a D-37 (continúan las de [01-diseno.md §4](01-diseno.md#4--decisiones)). Lo que el libro aporta (puntos brutos, materias, recomendaciones) está en [../12-gradebook/05-correcciones-cto-2026-10-19.md](../12-gradebook/05-correcciones-cto-2026-10-19.md). |

> **Consideración importante (del CTO, y del diseño):** el boletín de AVACOM **no es un documento oficial**. En Colombia la escala y la periodicidad las define el SIEE de cada institución (Decreto 1290 de 2009, compilado en el Decreto 1075 de 2015) y es la institución quien relaciona su escala con los desempeños nacionales; en México la boleta oficial de la SEP (ciclo 2025–2026, Acuerdo SEP 10/09/23) tiene estructura y expedición reguladas. AVACOM **no impone** la escala 1,0–5,0 ni cuatro periodos ni tres: el boletín es la **base** para que, con pocas ediciones, el profesor arme el documento que su institución exige. La leyenda va dentro del archivo y de la pantalla.

## 1 · Las cuatro preguntas y de dónde sale cada respuesta

| Pregunta | Qué trae | De dónde (todo YA presentado por el libro; Reporting no convierte ni promedia nada) |
|---|---|---|
| 1 · ¿Qué aprendió? | Resultados por **área/asignatura** (CO), **campo formativo** (MX primaria), **disciplina** (MX secundaria) o **asignatura** (genérica); dentro, cada curso con sus evaluaciones, **puntos obtenidos sobre el máximo**, porcentaje, **calificación en el sistema configurado**, desempeño y, en Colombia, el **desempeño nacional**. Y la lista de evaluaciones. | `gradebook.servicios.boletin_de_alumno` (cursos, `bruto`, `presentado`, `materia`) |
| 2 · ¿Qué competencias alcanzó? | **Logros** (lo que el profesor anotó como fortalezas), **aprendizajes pendientes** (dificultades), las evaluaciones que cumplen y las que no cumplen el criterio. La agregación por objetivos sigue «aún no disponible» (MOD-012). | `insights.comentarios`, `presentacion.aprobacion` |
| 3 · ¿Cómo ha progresado? | El promedio simple por curso en **cada periodo** en que estuvo (sus grupos anteriores incluidos), presentado con el sistema del nivel, y la tendencia. | `gradebook.servicios.progreso_del_alumno` (agregados por periodo) |
| 4 · ¿Qué debe mejorar? | Las **recomendaciones del profesor** (frases del catálogo del libro, generales y por curso), las oportunidades anotadas y el curso que conviene reforzar. | `observaciones`, `insights.comentarios.oportunidades`, `insights.curso_a_reforzar` |

## 2 · Plantillas (`reporting/dominio/boletin.py`)

| Plantilla | Organización | Periodos | Cualitativo | Notas |
|---|---|---|---|---|
| `co` Colombia | Áreas y asignaturas (una por materia) | **No se imponen** (los define el SIEE; mínimo dos) | Desempeños nacionales Superior · Alto · Básico · Bajo: se dicen **sólo cuando el tramo de la escala institucional ya se llama así**; con otros nombres la equivalencia la declara el SIEE y la columna queda vacía | Marco: Decreto 1290/2009 (Decreto 1075/2015) |
| `mx` México | **Primaria:** cuatro campos formativos (Lenguajes · Saberes y pensamiento científico · Ética, naturaleza y sociedades · De lo humano y lo comunitario), con una correspondencia **orientativa** materia → campo (`CAMPOS_FORMATIVOS`; lo que no se reconoce queda «Sin clasificar»). **Secundaria y bachillerato:** disciplinas. **Preescolar:** sin cifras | 1.er, 2.º y 3.er periodo | Observaciones y sugerencias | Marco: Acuerdo SEP 10/09/23; la boleta oficial la expide la SEP |
| `generica` | Asignaturas (una por materia) | Los que fije la institución | Observaciones del profesor | Para los países sin plantilla propia (no se inventa una) |

`auto` (por defecto) elige por el **país de la política del libro** (`m11_politica.pais`) y el nivel del grupo; la administración puede fijar la plantilla, los nombres de los periodos (hasta seis) y la leyenda en `m13_config` (`plantilla_boletin`, `periodos_boletin`, `leyenda_boletin`; `PUT configuracion/`, permiso `reports.settings.manage`). En OPS: Reportes → «Estado y ajustes» → «Boletín académico» (fichas; nada exige escribir).

## 3 · Decisiones

| # | Decisión | Por qué |
|---|---|---|
| D-32 | **El boletín es un tipo de reporte más** (`boletin`), con el permiso del informe nominal (`reports.student.view`), su evento `reporte.boletin_generado.v1`, su asiento `reporte.generado` (nominal) y su reciente («Boletín de Juan P.», «Boletines del grupo 8A»). No es una tabla: se arma al pedirlo con lo que el libro ya presentó (`gradebook.servicios`: tres lecturas nuevas de sólo lectura, D-4), y el modelo de información común es una **función pura** (`armar_modelo`). | Reporting no escribe datos académicos; lo único propio que guarda es la configuración. |
| D-33 | **Por grupo, un archivo por estudiante, todos en un `zip`** del formato pedido (xlsx o csv), con fechas fijas (misma entrada → mismos bytes). El zip se llama como los demás archivos (`reporte-boletines-<grupo>-<corte>.zip`: sin personas, D-15); **dentro**, cada archivo lleva el nombre del estudiante con un número de orden (`boletin-02-Juan P.xlsx`): es lo que el profesor entrega a cada familia y el contenido es nominal de por sí. El formato entregado se guarda en `m13_exportacion.formato` (`zip`); la cabecera `X-Avacom-Export-Formato` lo dice y OPS lo escribe con esa extensión. Hasta 80 boletines por archivo. | El CTO pidió «los múltiples archivos por estudiante»; una exportación en dos tiempos necesita UN archivo que confirmar. |
| D-34 | **El XLSX del boletín tiene una hoja por pregunta** («Resumen» con la cabecera, «1 Qué aprendió», «1b Evaluaciones», «2 Competencias», «3 Progreso», «4 Qué debe mejorar») y una hoja **«Datos»** plana (una fila por evaluación, lista para CSV: es lo que el CTO describe como «hoja de datos para exportación CSV»). El CSV es la misma secuencia de tablas. La cabecera lleva institución, estudiante, grupo, periodo, organización, sistema, marco de referencia, quién lo generó, el corte (BR-083) y la versión del nodo; las notas, la leyenda de «no oficial». | Lo que se descarga es el boletín, no una tabla técnica. |
| D-35 | **Sin cifras en modo simple y en preescolar mexicano**: el boletín dice si completó cada evaluación y no inventa promedios, puntos ni desempeños. **Un área con varios cursos no promedia entre cursos** (no se convierte nada que el libro no haya convertido): el área suma los puntos y el promedio simple de sus cursos, pero la calificación presentada sólo se da cuando el área tiene un curso. | Un promedio entre cursos con sistemas distintos sería una cuenta nueva del nodo, no una presentación del libro. |
| D-36 | **El filtro por materia del boletín usa el `curso_ref`** (como el libro, D-30 del Gradebook), con los mismos parámetros del árbol (`subject=`…). | Coherencia con el libro, que es quien arma el boletín. |
| D-37 | **La correspondencia materia → campo formativo es orientativa** y queda en el código, no en la configuración: la institución mexicana la ajusta cuando el CTO confirme los códigos de materia reales de su biblioteca. Lo no reconocido va a «Sin clasificar», nunca a un campo adivinado. | Los códigos de materia del árbol de AVACOM Contenido no están todos a la vista desde aquí. |

## 4 · API (lo que se añade a [02-api.md](02-api.md))

| Ruta | Verbo | Permiso | Qué devuelve |
|---|---|---|---|
| `boletines/{alumno_id}/?grupo_id=&subject=…` | GET | `reports.student.view` | `{…cabecera de todo reporte…, alumno, grupo, plantilla, boletin}`; `boletin` = `{plantilla, institucion, estudiante, grupo, periodo, nivel_clave, modo, sin_cifras, sistema, areas[], evaluaciones[], competencias{logros, pendientes, evaluaciones_aprobadas, evaluaciones_no_aprobadas, objetivos}, progreso{periodos, filas, tendencia}, recomendaciones{del_docente, oportunidades, curso_a_reforzar, mejor_curso}, resumen, leyenda, preguntas}`. Sin `grupo_id`, el primero de sus grupos que se puede ver; sin grupo activo, 409 `alumno_sin_grupo`. |
| `boletines/?grupo_id=&subject=…` | GET | idem sobre el grupo | `{…, grupo, plantilla, boletines[] (uno por estudiante, alfabético), totales{estudiantes, boletines, con_nota}}`. Más de 80 estudiantes: 400. |
| `exportaciones/alcance/` y `exportaciones/` con `reporte: {tipo: "boletin", grupo_id, alumno_id?}` | POST | `reports.export` | Con `alumno_id`, un xlsx/csv; sin él, un **zip** con uno por estudiante. El alcance trae `formato_de_entrega` (`zip` o el pedido), `archivos` y `plantilla`. |
| `configuracion/` | GET/PUT | lectura / `reports.settings.manage` | `plantilla_boletin` (`auto`/`co`/`mx`/`generica`), `periodos_boletin[]` (hasta 6 nombres cortos, sin repetir), `leyenda_boletin` (≤ 400), `plantillas_de_boletin[]`. |

Evento `reporte.boletin_generado.v1` (se añade a los de §5 de la API). Tipo `boletin` en `m13_exportacion.tipo` y `m13_reciente.tipo`; `zip` en `m13_exportacion.formato` (migración 0002).

## 5 · Pantallas de OPS

- **Reportes** → tarjeta «Boletín académico» (tercio derecho del pie, junto a «Uso de equipos»; sólo si el rol puede ver el informe del alumno) → elegir el grupo → **Boletines del grupo** (lista: evaluaciones, con nota, puntos, promedio presentado, cuántas recomendaciones; «Exportar» = zip) → **Boletín** de cada estudiante (las cuatro preguntas; «Exportar» = xlsx o csv), con el filtro por materia.
- La hoja de exportar dice cuando va empaquetado («Un archivo por estudiante (24), todos en un zip») y la plantilla.
- **Estado y ajustes** → «Boletín académico»: plantilla y periodos como fichas (la leyenda se cambia por la API: sin teclado no se escribe).

## 6 · Pruebas

| Qué | Dónde | Resultado |
|---|---|---|
| Plantillas (auto por país, Colombia sin periodos impuestos y con desempeños nacionales, México por campos/disciplinas/sin cifras, desempeño nacional sólo con el nombre de la escala), el modelo común sobre un boletín de mentira (campos formativos, sin cifras, configuración del nodo) y el documento (una hoja por pregunta y «Datos») | `reporting/tests/test_boletin.py::PlantillasTests` (puras) | ✅ |
| El boletín de un estudiante real (examen calificado con `co-1-5`): las cuatro preguntas, bruto + presentada + desempeño nacional, recomendaciones, sin grupo → el primero visible, permisos (ajeno y técnico 403 con asiento; reportes y administración sí), rastro (evento, asiento sin nombres, reciente), filtro por materia | `…::BoletinDeUnEstudianteTests` | ✅ |
| Los boletines del grupo (uno por estudiante, alfabético; sin grupo 404; ajeno 403) | `…::BoletinesDelGrupoTests` | ✅ |
| Exportar: el xlsx con las siete hojas y el desempeño nacional; el **zip** con `boletin-01-Ana.xlsx` y `boletin-02-Juan P.xlsx` (y en csv con BOM); misma entrada → mismos bytes; quien no ve al estudiante no exporta | `…::ExportarBoletinTests` | ✅ |
| Configuración del boletín (fijar, repetir sin asiento, lo que no vale, sin permiso) y el catálogo | `…::ConfiguracionDelBoletinTests` | ✅ |
| Arquitectura (el catálogo de eventos con el nuevo; Reporting sigue sin escribir fuera de `m13_*`) | `reporting/tests/test_arquitectura.py` | ✅ |
| Contratos C# contra respuestas reales (`boletin`, `boletines`, `boletin_alcance`, `boletines_alcance`, `configuracion_boletin`, `recientes_boletin`) y el cliente (`BoletinAsync`, `BoletinesAsync`, `DeBoletin`, `zip`) | `tests/Avacom.Lms.Core.Tests/ContratoReportesTests.cs`, `ReportesApiTests.cs`; rutas en `Avacom.Lms.Ops.Tests/ReportesLogicaTests.cs` | ver [03-pruebas.md](03-pruebas.md) |

**No se probó**: el zip escrito en una memoria USB real por la hoja de exportar (la escritura segura es la misma de D-31, con otra extensión); abrir el XLSX del boletín con Excel real (el escritor es el mismo de D-12); las pantallas de OPS en una ventana (compilan sin errores); la plantilla mexicana con cursos reales de la biblioteca de México (no hay en este equipo).

## 7 · Lo que queda para el CTO

1. Las **plantillas** de su XLSX («tres modelos de boletín, ejemplos de calificaciones, competencias, observaciones y espacios de validación») no llegaron: lo armado sigue su texto. Con el archivo se ajustan columnas, orden y rótulos.
2. **Campos formativos** (D-37): confirmar la correspondencia materia → campo con los códigos reales de la biblioteca mexicana.
3. **Nombres dentro del zip** (D-33): llevan el nombre del estudiante; si debe ir sólo un código, es un cambio de una línea (`_nombres_internos`).
4. **PDF** sigue en V1 (sin librería en el entorno); el XLSX es la base editable que el CTO describe.
