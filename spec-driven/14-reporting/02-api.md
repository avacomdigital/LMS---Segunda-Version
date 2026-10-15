# 14 · Reporting (MOD-013) · API `/api/reportes/`

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-15) en `backend/reporting/`. El diseño, las decisiones y lo pendiente están en [01-diseno.md](01-diseno.md). |
| Respuestas reales | `tests/Avacom.Lms.Core.Tests/Fixtures/reportes/*.json` (+ `exportacion_cuerpo.csv`): las captura `backend/reporting/tests/test_capturar_contrato.py` contra el backend de verdad. Un DTO de C# que no las lee bien es un DTO mal escrito. |
| Cliente | `src/Avacom.Lms.Core/Reporting/` (`ReportesApi`, `IReportesApi`, `ModelosReportes`, `ReportesTexto`, `NombreDeArchivo`, `MotivosDeEscritura`). |

## 0 · Convenciones

- **Sólo lectura sobre datos académicos (BR-085).** Lo único que esta API escribe son sus propias tablas (`m13_*`): la configuración, las exportaciones y los «recientes».
- **Quién actúa.** Con sesión (MOD-001), quien firma el JWT. Sin sesión (Q-34, prototipo), el que el cliente declare con `actor` (consulta o cuerpo) y, si quiere, `actor_rotulo`. Con `AVACOM_LMS_EXIGIR_SESION=1`, 401 a lo anónimo. Todo se **recorta por el alcance de quien consulta**: el profesorado, sus grupos; Reportes y administración, toda la organización.
- **Tiempo.** Toda marca es del reloj del **nodo**, en milisegundos. Nada usa el reloj del cliente.
- **Cifras.** Porcentajes de 0 a 100 con a lo sumo dos decimales. **Sin dato = `null`, nunca `0`** (un promedio sin valores no es un cero).
- **Todo reporte lleva estos bloques** (BR-083, BR-086, art. 14):

  ```json
  "corte": {"en": 1790002430000, "antiguedad_ms": 0, "estado": "al_dia",
            "incompleto": false, "texto": "Datos al 21 sep · 09:53",
            "explicacion": "Esto es lo que había en el nodo a esa hora.",
            "integracion": {"estado": "completa", "equipos": 5, "sin_sincronizar": 0, "motivos": [], "texto": "Todo sincronizado", "motivo_linea": ""}},
  "privacidad": {"umbral_activo": false, "aplicada": false, "minimo": 5, "alumnos": 5, "aviso": ""},
  "objetivos": {"disponible": false, "texto": "Aún no disponible: el dominio por objetivo llega con el módulo de objetivos."},
  "nominal": true, "avisos": [], "generado_en": 1790002430000, "generado_por": {"id": "…", "rotulo": "…"}, "servidor_en": 1790002430000
  ```

  `corte.estado` es `al_dia`, `rezagada` o `reconstruyendose`: la pantalla lo dice como antigüedad del dato. `integracion.estado` es `completa` o `incompleta`; `motivos[]` trae `{codigo, equipos, texto}` con `conexion_perdida`, `entrega_pendiente` o `cola_de_estudio`. `avisos[]` dice, por ejemplo, que un filtro por materia **no se pudo aplicar** porque la biblioteca no respondió (`{filtro, aplicado, texto}`).
- **Errores.** `{detail, codigo, …extras}`. Los extras nunca pisan `detail` ni `codigo`.

  | HTTP | `codigo` |
  |---|---|
  | 400 | `datos_invalidos` · `razon_requerida` (+`razones[]`) |
  | 403 | `sin_permiso` (+`permiso`) · `fuera_de_alcance` (+`grupo_id`) · `destino_no_permitido` (+`destino_tipo`) |
  | 404 | `no_encontrado` (lo ajeno y lo inexistente responden igual) |
  | 409 | `clase_en_curso` · `sin_sesiones_finalizadas` (+`desde`, `hasta`) · `alumno_sin_grupo` · `no_instalado` · `sesion_activa` · `reconstruccion_en_curso` · `exportacion_caducada` · `exportacion_ya_confirmada` · `huella_distinta` · `conflicto_de_version` (+`version_actual`) |
  | 501 | `capacidad_reservada` (+`capacidad`, `permiso`) |

  Todo 403 sobre datos académicos —también el del rol técnico— deja el asiento `reporte.acceso_denegado` (TST-069).

## 1 · Leer

| Ruta | Verbo | Permiso | Qué devuelve |
|---|---|---|---|
| `clases/?grupo_id=&desde=&hasta=&limite=&country=&level=&grade=&subject=&topic=` | GET | `reports.view` | **Las clases cerradas** que esta persona puede ver, la más reciente primero (`limite` ≤ 200): `clases[]` con `sesion_id`, `grupo`, `curso_rotulo`, `leccion_rotulo`, `finalizada_en`, `duracion_ms`, `participantes`, `actividades`, promedios e `incompleta`; `total`, `avisos`, `estado`. |
| `clases/{sesion_id}/` | GET | `reports.view` | **El reporte de la clase** (CAP-081): `clase{…}`, `filas[]` (por alumno: `estado` de la tableta al cerrar, `actividades_recibidas/entregadas`, `calificadas`, `aciertos`, `porcentaje_participacion`, `porcentaje_aciertos`, `entregas_por_cola`) y `totales{participantes, actividades, promedio_participacion, promedio_aciertos}`. Con la privacidad aplicada, `filas` va **vacío** y `nominal` en `false`. Una clase abierta: 409 `clase_en_curso`. |
| `grupos/{grupo_id}/?country=&level=…` | GET | `reports.group.view` | **El reporte del grupo**: `grupo`, `modo` (`simple`/`calificaciones`), `escala`, `totales{alumnos, clases, evaluaciones, estudios, en_atencion, promedios}`, **`atencion[]` primero** (cada uno con sus `atencion[{codigo, cantidad, texto}]` y `motivo` en una línea), `alumnos[]`, `clases[]` y `evaluaciones[]` (sólo conteos). Con la privacidad aplicada, `alumnos` y `atencion` van vacíos. |
| `alumnos/?grupo_id=` | GET | `reports.student.view` | Los alumnos de un grupo **para elegir sin escribir**: `alumnos[{id, rotulo, inicial, necesita_atencion}]` y `iniciales[{inicial, cantidad}]`. |
| `alumnos/{alumno_id}/?grupo_id=&country=…` | GET | `reports.student.view` | **El informe del alumno** (CAP-082, FUN-140): `alumno`, y por grupo `{grupo, modo, escala, resumen{…}, motivo_de_atencion, evaluaciones[], estudios[], clases[]}`. En cada evaluación, `presentacion` es la que **ya resolvió el libro** (null en modo simple, donde van `estado_simple` y `simbolo`). No se recorta con la privacidad. |
| `uso/?desde=&hasta=&grupo_id=&country=…` | GET | `reports.usage.view` | **Uso de equipos** (FUN-142): `periodo`, `totales{clases, equipos, tiempo_total_ms, duracion_media_ms}`, `equipos[]` y `clases[]`. **Sin datos de personas.** Sin clases finalizadas en el periodo: 409 `sin_sesiones_finalizadas`. |
| `filtros/` | GET | cualquiera de lectura | Lo que las fichas ofrecen (FUN-143): `grupos[]` (con `alumnos`, `en_atencion` y `desactualizado`; los dos primeros van en `null` para quien sólo puede ver el uso de equipos —el técnico—: son datos académicos, BR-085), `periodos[]`, `nodos{disponible, motivo, arbol[]}` (el árbol de AVACOM Biblioteca, en vivo), `objetivos` y **`puede{clase, grupo, alumno, uso, exportar, reconstruir, configurar}`**: lo que el nodo concederá a quien pregunta. |
| `recientes/` | GET | cualquiera de lectura | Los reportes que esta persona abrió (≤ 10): `{tipo, parametros, titulo, ultima_vez_en, veces, ultima_exportacion_en}`. Sólo parámetros, nunca contenido. El `titulo` distingue lo que hace distinto a un reciente: «Grupo 8A · con filtro de materia», «Uso de equipos · desde 8 oct» (D-27). |

`desde` y `hasta` aceptan milisegundos del nodo o fechas (`AAAA-MM-DD`; `hasta` incluye todo el día). Los filtros de nodo (`country`, `level`, `grade`, `subject`, `topic`) son los **códigos** del árbol de la biblioteca (letras, números y `. _ : -`, hasta 64; cualquier otra cosa da `400 datos_invalidos` con el nombre del `filtro`); si ésta no responde, el filtro no se aplica y `avisos[]` lo dice.

## 2 · Configuración y mantenimiento

| Ruta | Verbo | Permiso | Qué hace |
|---|---|---|---|
| `configuracion/` | GET | cualquiera de lectura | `configuracion{umbral_privacidad, extraibles_permitidos, exigir_razon, version, minimo_de_alumnos, razones[], formatos[], destinos[], actualizada_en, actualizada_por}`. |
| `configuracion/` | PUT | `reports.settings.manage` | Cambia lo que se mande (`umbral_privacidad`, `extraibles_permitidos`, `exigir_razon`) con `version_esperada` (si otro cambió antes: 409 `conflicto_de_version` con la versión actual). Responde `{configuracion, cambiado}`; repetir lo mismo no sube la versión. Deja el asiento `reporte.configuracion_cambiada` con el valor anterior y el nuevo. |
| `estado/` | GET | lectura | `estado` (`al_dia`/`rezagada`/`reconstruyendose`), `corte_en`, `antiguedad_ms`, `clase_en_curso`, `fuentes[{fuente, marca, ultima, pendientes, fallos_seguidos}]`, `grupos{total, desactualizados}`, `clases`, `reconstruccion{en_curso, ultima_en, por, error}`, `puede_reconstruir`. |
| `actualizar/` | POST | `reports.rebuild` | Pone al día lo que falte **aunque haya una clase abierta**: `{eventos, grupos, clases_limpiadas, exportaciones_caducadas, fallidos, grupos_fallidos}`. |
| `reconstruir/` | POST | `reports.rebuild` | **FUN-147.** Borra las derivadas y las reconstruye desde la cola (BR-007) en una transacción: `{eventos, grupos, grupos_fallidos[], borradas{m13_…: n}}`. Con una clase en curso: 409 `sesion_activa`. |

## 3 · Exportar a archivo (FUN-146), en dos tiempos

El cuerpo describe **el mismo reporte que se ve**: `{"reporte": {"tipo": "grupo", "grupo_id": "…"}, "formato": "xlsx", …}`. `reporte` lleva `tipo` (`clase`, `grupo`, `alumno`, `uso`) y los mismos parámetros que su ruta de lectura (`sesion_id`, `grupo_id`, `alumno_id`, `desde`, `hasta`, filtros de nodo).

| Ruta | Verbo | Permiso | Qué hace |
|---|---|---|---|
| `exportaciones/alcance/` | POST | `reports.export` + el del reporte | **Antes de confirmar, sin efectos:** `alcance` declarado — `titulo`, `alumnos`, `filas`, `incluye[]`, `nominal`, `umbral_aplicado`, `texto_alcance` («Vas a guardar el reporte del grupo 8A (7 alumnos, …, datos al 21 sep · 09:53)»), `advertencia` (con nombres de alumnos, o «Sin datos de personas.»), `corte`, `privacidad`, `nombre_sugerido`, `formatos[]` y la `politica{extraibles_permitidos, exigir_razon, razones[]}`. No genera ni registra nada. |
| `exportaciones/` | POST | idem | **1.er tiempo.** (OPS sólo reutiliza el archivo ya bajado para otro intento si el `destino_tipo` es el mismo; si cambia la clase de destino, vuelve a llamar aquí.) Con `formato`, `destino_tipo` (`extraible`/`carpeta_local`/`red`) y, si el administrador la exige, `razon_codigo`: aplica la política (403 `destino_no_permitido`, 400 `razon_requerida`), **genera el archivo y lo responde** (201, el cuerpo es el archivo). |
| `exportaciones/{id}/confirmar/` | POST | quien la pidió | **2.º tiempo.** `{resultado: "guardado", destino_tipo, huella_verificada}` — la huella que se **releyó** del destino; si no coincide, 409 `huella_distinta` y no se da por entregada — o `{resultado: "fallido", destino_tipo, motivo}` con `motivo` de la lista cerrada. Un fallo **no cierra** la exportación: se puede elegir otro destino sin generar de nuevo. Una caducada: 409 `exportacion_caducada`. Repetir un `guardado` ya hecho devuelve `reintento: true`. |
| `exportaciones/{id}/` | GET | quien la pidió | La exportación (`estado`, `intentos[]`, `huella`, `bytes`, `expira_en`…). Lo ajeno: 404. |
| `exportaciones/` | GET | lectura | Las exportaciones de esta persona. |

**La respuesta del primer tiempo** es el archivo (`Content-Type` `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` o `text/csv; charset=utf-8`, `Cache-Control: no-store`) con estas cabeceras, para que OPS lo baje directo a disco sin cargarlo entero en memoria:

```
X-Avacom-Export-Id: e7101922-…            X-Avacom-Export-Huella: 0a2cdfa2…   (SHA-256 de lo que viene en el cuerpo)
X-Avacom-Export-Bytes: 2025               X-Avacom-Export-Filas: 11
X-Avacom-Export-Formato: csv              X-Avacom-Export-Tipo: grupo
X-Avacom-Export-Nombre: reporte-grupo-8A-2026-09-21-0953.csv        (URL-codificado)
X-Avacom-Export-Expira-En: 1790003330000  X-Avacom-Export-Corte-En: 1790002430000
X-Avacom-Export-Nominal: true             X-Avacom-Export-Umbral-Aplicado: false
X-Avacom-Export-Destino: extraible        Content-Disposition: attachment; filename*=UTF-8''…
```

**Estados de una exportación:** `autorizada` («sin confirmar») → `entregada` (`confirmada_en`, `destino_tipo`, `huella_verificada`) o `caducada` (a los 15 minutos sin confirmar; no cuenta como entregada). Sólo `entregada` publica `reporte.exportado.v1` y deja el asiento `reporte.exportado`.

**Motivos de fallo** (contrato con `MotivosDeEscritura` del cliente): `medio_retirado` · `sin_espacio` · `protegido_contra_escritura` · `sin_permiso` · `ruta_de_red_inalcanzable` · `nombre_invalido` · `bloqueado_por_antivirus` · `archivo_en_uso` · `verificacion_fallida` · `cancelado` · `otro`.

**Dentro del archivo** (también BR-083): XLSX con una hoja «Resumen» (cabecera y totales) y una hoja por tabla, con encabezado fijo y filtro; CSV UTF-8 **con BOM**, `;` y coma decimal. La cabecera trae *Reporte · Grupo/alumno · Periodo · Generado por · Generado el · Datos al corte · Estado de integración · Umbral de privacidad aplicado · Versión del nodo*.

## 4 · Reservadas (V1)

`GET comparar/` (CAP-083) y `GET cobertura/` (CAP-085 / FUN-141, permiso `reports.curriculum.view`) responden **501 `capacidad_reservada`** con la explicación. El evento `reporte.cobertura_generado.v1` se declara y no se emite.

## 5 · Eventos

**Consume** (por la marca de lectura de cada módulo; sólo avisa qué cambió, el dato se vuelve a leer del dueño; idempotente):

| Fuente | Eventos |
|---|---|
| MOD-007 aula | `aula.sesion.finalizada.v1` · `aula.intento.entregado.v1` · `aula.presencia.registrada.v1` |
| MOD-010 evaluación | `evaluacion.asignada` · `intento_abierto` · `intento_entregado` · `intento_fuera_de_plazo` · `intento_calificado` · `intento_anulado` · `revision_publicada` · `envio_tardio_decidido` · `asignacion_cerrada` (`.v1`) |
| MOD-011 libro | `calificacion.registrada` · `manual_aplicada` · `rubrica_aplicada` · `intento_reabierto` · `ajustada` · `publicada` · `publicacion_retirada` · `valoracion_docente` · `anulada` · `modo_cambiado` · `escala_adoptada` · `estado_simple_calculado` (`.v1`) |
| MOD-008 estudio | `estudio.asignacion.creada` · `asignacion.cerrada` · `leccion.completada` · `practica.terminada` · `trabajo.integrado` · `sesion.cerrada` (`.v1`) |

**Publica** (`m13_evento_salida`, versionados): `reporte.grupo_generado.v1` · `reporte.alumno_generado.v1` · `reporte.uso_generado.v1` · `reporte.agregados_actualizados.v1` · `reporte.agregados_reconstruidos.v1` · `reporte.marcado_incompleto.v1` (una vez por cambio) · `reporte.exportado.v1` · `reporte.cobertura_generado.v1` (reservado). La clase no tiene función propia en el Maestro: no emite.

## 6 · Auditoría (MOD-019)

Módulo `reportes`; acciones `reporte.generado` (un reporte **nominal**: quién, cuál, alcance, filas) · `reporte.exportacion_autorizada` · `reporte.exportado` · `reporte.exportacion_fallida` · `reporte.exportacion_caducada` · `reporte.acceso_denegado` · `reporte.agregados_reconstruidos` · `reporte.configuracion_cambiada` · `reporte.evento_omitido`. Cada exportación asienta quién, qué reporte, alcance, filas, **huella SHA-256**, **tipo** de destino y resultado. **Nunca** la ruta, el nombre del archivo ni el contenido: una prueba lo comprueba.

## 7 · Permisos

`reports.view` · `reports.group.view` · `reports.student.view` (ya existía) · `reports.usage.view` · `reports.curriculum.view` (reservado) · `reports.export` · `reports.rebuild` · `reports.settings.manage` (extensión propuesta). Reparto por rol en [01-diseno.md §8](01-diseno.md#8--permisos-por-rol); migración `acceso/0017_permisos_reportes`.

## 8 · Variables de entorno del nodo

`AVACOM_REPORTES_PROGRAMADOR` (`1`; `0` apaga el hilo de FUN-144) · `AVACOM_REPORTES_INTERVALO_S` (`60`) · `AVACOM_REPORTES_EXPORTACION_TTL_S` (`900`) · `AVACOM_REPORTES_SINCRONIZAR` (`1`: cada consulta se pone al día antes de responder).
