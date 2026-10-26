# 18 · Backup & Recovery (MOD-016) · Contrato de `/api/respaldo/`

Todas las rutas exigen **sesión**. No hay actor «declarado»: un respaldo nunca se pide de forma anónima. Errores con la forma de siempre `{"detail", "codigo", …}`.

| Método y ruta | Permiso | Cuerpo / respuesta |
|---|---|---|
| `GET estado/` | `backup.read` | ver abajo |
| `GET respaldos/?limite=` | `backup.read` | `{respaldos: [ficha], total}` |
| `GET respaldos/<id>/` | `backup.read` | la ficha + `historial: [{id, respaldo_id, tipo, en, actor, detalle}]` |
| `GET respaldos/<id>/constancia/` | `backup.read` | `{nombre, texto}`; con `?formato=txt` se descarga como archivo |
| `GET resumen/` | `backup.read` | `{nombre, texto}`; con `?formato=csv` se descarga (UTF-8 con BOM) |
| `GET informes/` · `GET informes/<nombre>/` | `backup.read` | los archivos de `Informes\`; `?formato=txt\|csv` descarga |
| `GET destinos/` | `backup.read` | `{unidades: [{id, rotulo, libre_bytes}], candidatos: [{id, nombre, bytes, fuente}]}` (ids **opacos**: nunca una ruta) |
| `POST respaldos/ahora/` | `backup.run` | `{tipo?: "completo"\|"incremental"}` → **201** con la ficha |
| `POST respaldos/<id>/verificar/` | `backup.verify` | `{custodia?}` → `{respaldo_id, verificado, motivo, entradas}` |
| `POST respaldos/<id>/exportar/` | `backup.export` + **pase** | `{unidad, pase}` → `{respaldo_id, exportado, unidad, archivos}` |
| `POST programacion/` | `backup.schedule` | `{activo?, hora_min?, dias?, completo_cada_dias?, retencion?, incluir_reinstalable?}` → `{programacion, siguiente_en}` |
| `POST custodia/emitir/` | `backup.schedule` + **pase** (operación `backup.schedule`) | `{reemplazar?, pase}` → **201** `{codigo, hoja, emitida_en, siguiente_paso}` — el código **se muestra una vez** |
| `POST restaurar/` | `backup.restore` + **pase** | `{respaldo_id` **o** `candidato, motivo, nota?, custodia?, pase}` → ver abajo |
| `POST restaurar/modulo/` | `backup.restore.module` + **pase** | `{modulo, pase}` → siempre **409** `modulo_sin_restauracion_aislada` hoy |

**El pase** va en `pase` como **base64** del archivo `.avsp` que emite AVACOM. **`motivo`** de una restauración es de una lista cerrada (no hay teclado): `equipo_danado`, `equipo_nuevo`, `datos_danados`, `error_humano`, `prueba_de_recuperacion`, `otro`.

## `estado/`

```json
{
  "nodo": "3F2A9C1E", "programacion": {"activo": true, "hora_min": 120, "dias": [0,1,2,3,4,5,6], "completo_cada_dias": 7, "retencion": 14, "incluir_reinstalable": false},
  "siguiente_en": 1793037600000,
  "ultimo_restaurable": {"respaldo_id": "…", "tipo": "completo", "estado": "completo_verificado", "creado_en": 0, "verificado_en": 0, "bytes": 0, "exportado": false},
  "ultimo": {"…": "el más reciente que existe, verificado o no"},
  "dias_sin_respaldo": 0, "aviso_sin_respaldo": false,
  "en_marcha": null, "aplazado_por_clase": null,
  "custodia": {"emitida": true, "emitida_en": 0},
  "espacio_libre": 0, "unidades": [], "respaldos": {"completo_verificado": 12, "caducado": 3}, "total": 15,
  "informes": ["resumen-de-respaldos.csv", "constancia-20261025-0700-b8c9dae0.txt"]
}
```

`aviso_sin_respaldo` es verdadero si no hay ningún respaldo restaurable o pasaron **7 días** (MSG-066). Ninguna ruta, ningún dato de personas.

## La ficha de un respaldo

`respaldo_id, tipo, base_id, disparo (programado·manual·previo_a_actualizacion·previo_a_restauracion), archivo, sha256, bytes, creado_en, secuencia_global, version_producto, entradas, archivos, incluye_reinstalable, con_custodia, creado_por, estado, restaurable, existe, ejecutado_en, verificado_en, exportado, exportado_en, error, ultima_en`.

Estados: `en_curso · completo_no_verificado · completo_verificado · exportado · caducado` (los del Maestro) y `incompleto · fallido`.

## Respuesta de `restaurar/`

`{ok, parcial, fallos_archivos, en, respaldo_id, punto_de_retorno, archivos, perdidas: {horas, eventos}, post: {esquema, nodo, sesiones, licencia, reconstruidos, fallos}, nueva_huella, reinicio_recomendado, informe, informe_texto, …}`. `ok: false, parcial: true` = la base **sí** se restauró (y lo derivado se rehizo) pero no se pudieron devolver los archivos de las carpetas de `fallos_archivos`; el informe lo dice. `post.fallos` lista lo que no se pudo rehacer (la restauración ya se aplicó: el técnico decide qué repetir).

## Errores

| HTTP · `codigo` | Cuándo |
|---|---|
| 400 `datos_invalidos` (`campo`) | cuerpo mal formado, `motivo` fuera de la lista, código de custodia con un dígito de control que no cuadra, `pase` que no es base64 |
| 403 `sin_permiso` | no es personal de AVACOM, sin sesión o con otro rol (también la bitácora asienta la denegación) |
| 403 `pase_requerido` · `pase_invalido` (`motivo`) | sin pase, o `formato · kid_desconocido · firma_invalida · contenido · vigencia_excesiva · aun_no_vigente · vencido · accion_no_incluida · otro_equipo · ya_usado` |
| 404 `no_encontrado` | respaldo, unidad o informe inexistente |
| 409 `sesion_activa` | hay una clase abierta (el pase no se gasta) |
| 409 `respaldo_en_curso` | ya hay un respaldo o una restauración |
| 409 `espacio_insuficiente` (`necesario`, `libre`) | se dice **antes** de empezar |
| 409 `sin_respaldo_previo` | un incremental sin completo anterior |
| 409 `respaldo_fallido` (`motivo`: `archivo_cambio · sin_origen · error_de_escritura · error_inesperado`) | el respaldo no terminó; lo anterior sigue intacto |
| 409 `restauracion_abortada` (`motivo`: `formato_invalido · version_no_soportada · integridad_alterada · truncado · huella_distinta · base_danada · base_de_version_posterior · cadena_incompleta · clave_no_disponible · punto_de_retorno · aplicacion_base`) | se abortó **sin tocar lo vivo** (`aplicacion_base`: la base no se pudo reemplazar y no cambió) |
| 409 `custodia_requerida` | el respaldo es de otro equipo: falta el código |
| 409 `custodia_ya_emitida` · `modulo_sin_restauracion_aislada` · `estado_invalido` | — |
| 422 `respaldo_invalido` · `clave_no_disponible` (`motivo`) | el archivo no es un respaldo, está alterado, o ni la clave del equipo ni el código lo abren |

## Interfaz para otros módulos (`respaldo.servicios`)

`verificado_hasta() → int` · `cubre(secuencia) → bool` (lo usa la purga de MOD-015, BR-017) · `estado_resumido() → dict` (lo usa `/health/`, campo aditivo `respaldo`) · `tick(origen)`. Ninguna lanza (R-04).

## Eventos (cola única, clase `técnico`)

`respaldo.programado.v1 · completo_ejecutado.v1 · incremental_ejecutado.v1 · verificado.v1 (resultado ok|falla) · exportado.v1 · restauracion_completada.v1 · modulo_restaurado.v1 · reanudado.v1 · indice_reconstruido.v1` (los nueve que el módulo publica de los diez del Maestro) y, como extensiones, `fallido.v1 · restauracion_abortada.v1 · caducado.v1 · custodia_emitida.v1`. `punto_recuperacion_creado.v1` está declarado y **no se publica** (D-14). Ningún evento lleva rutas ni personas.

## Variables de entorno (`backend.env`)

| Variable | Efecto |
|---|---|
| `AVACOM_RESPALDO_DIR` | carpeta de respaldos **sólo** en desarrollo y pruebas (en producción es siempre `%ProgramData%\AVACOM\OPS Master\Respaldos`) |
| `AVACOM_RESPALDO_UNIDADES` | carpetas (`;`) que hacen de unidad extraíble, sólo en desarrollo y pruebas |
| `AVACOM_RESPALDO_CARPETAS` | `nombre=ruta` o `nombre:reinstalable=ruta`, separadas por `;`: carpetas de archivos de la institución que entran al respaldo (vacío = sólo la base) |
| `AVACOM_RESPALDO_VIGILANTE` | `0` apaga el hilo del calendario |
| `AVACOM_RESPALDO_INTERVALO_S` | cadencia del vigilante (60) |
