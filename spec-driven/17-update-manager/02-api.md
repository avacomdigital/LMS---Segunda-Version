# 17 · Update Manager (MOD-017) · API `/api/actualizacion/`, orden y resultado del `Host`, interfaz `actualizacion.servicios`

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-21) en `backend/actualizacion/`. El diseño y lo pendiente están en [01-diseno.md](01-diseno.md). |
| Respuestas reales | Las captura `backend/actualizacion/tests/test_capturar_contrato.py` contra el backend de verdad (`AVACOM_CAPTURAR_CONTRATO=<carpeta>`): 36 archivos (`estado_*.json`, `importar_*.json`, `aplicar_*.json`, `orden_json.json`, `resultado_json.json`, `ejemplo.avupd`…). Los cuerpos de abajo salen de esa captura. Para OPS (Fase 3, hecho) se guardan en `tests/Avacom.Lms.Core.Tests/Fixtures/actualizacion/`. |

## 0 · Convenciones

- **Quién actúa.** Con sesión (MOD-001), quien firma el JWT. Sin sesión (Q-34, prototipo), el que el cliente declare con `actor`. Con `AVACOM_LMS_EXIGIR_SESION=1`, 401 a lo anónimo.
- **Sin rutas (P-11).** Ninguna respuesta trae un camino de archivo: los paquetes de un USB se nombran por un `id` opaco y las fichas no listan rutas.
- **Tiempo.** Toda marca es del reloj del **nodo** (`nodo.servicios.ahora_ms`), en milisegundos.
- **Errores.** `{detail, codigo, …extras}`.

  | HTTP | `codigo` |
  |---|---|
  | 400 | `datos_invalidos` |
  | 403 | `sin_permiso` (+`permiso`) |
  | 404 | `no_encontrado` (+`paquete_id` o `candidato`) |
  | 409 | `sesion_activa` (+`sesiones_activas`) · `contrato_incompatible` (+`incompatibilidades[]`) · `espacio_insuficiente` (+`espacio_requerido`, `espacio_libre`) · `ya_aplicado` · `serie_menor` · `fuera_de_plazo_reversion` (+`revertible_hasta`) · `estado_invalido` (+`estado`) · `actualizacion_en_curso` · `paquete_repetido` |
  | 422 | `firma_invalida` (+`motivo`, y `kid` si es desconocido) · `paquete_invalido` (+`motivo`) |
  | 503 | `actualizacion_en_curso` (+`reintentar_en_s`, cabecera `Retry-After: 60`): **sólo** `POST /api/aula/sesiones/` mientras hay una orden |

## 1 · Rutas

| Ruta | Verbo | Permiso | Qué devuelve |
|---|---|---|---|
| `estado/` | GET | `update.read` | `estado` (`al_dia`·`programado`·`aplicando`), `en_curso{paquete_id, nombre, accion, orden_id, desde}`\|null, `programados[{paquete_id, nombre, ventana}]`, `revertibles[{paquete_id, nombre, aplicado_en, revertible_hasta}]`, `paquetes{estado: n}`, `orden_pendiente`, `canal`, `version` (del producto), `contrato_biblioteca`, `modulos[{nombre, modulo, version, version_datos, version_contrato, serie, actualizable, produce[], consume{}}]`, `espacio_libre`, `dias_reversion`, `servidor_en` |
| `paquetes/` | GET | `update.read` | `candidatos[{id, nombre, origen, bytes, modificado_en, fuente, importado}]` (los `.avupd` de las unidades extraíbles y de `entrada\`, con `importado` = el `paquete_id` si ya entró) y `paquetes[]` (las fichas, sin `historial`) |
| `paquetes/importar/` | POST | `update.package.import` | Cuerpo `{candidato}`. **201** con la ficha (FUN-180 + FUN-181); 422 con `motivo` si se rechaza (sin escribir nada); 404 si el candidato ya no está |
| `paquetes/{id}/` | GET | `update.read` | **La ficha**: `paquete_id, nombre, version_producto, serie, modulos[], kid, sha256, bytes, archivo, origen, recibido_en, importado_por, manifiesto{…sin archivos}, estado, en_curso, accion, orden_id, ventana, aplicado_en, revertible_hasta, revertible, incompatibilidades[], ultima_en, historial[]` |
| `paquetes/{id}/programar/` | POST | `update.schedule` | Cuerpo `{desde, hasta}` (ms). 200 con la ficha `programado` (FUN-182) |
| `paquetes/{id}/desprogramar/` | POST | `update.schedule` | 200 con la ficha `verificado` |
| `paquetes/{id}/aplicar/` | POST | `update.apply` | **202** con la ficha `aplicando` + `orden{orden_id, accion, limite_minutos, pasos[], emitida_en}` y `orden.json` escrita (FUN-184); 409 `sesion_activa` con una clase (FUN-183) |
| `paquetes/{id}/revertir/` | POST | `update.apply` | Cuerpo `{nota}` (obligatoria). **202** con la orden de reversión; 409 `fuera_de_plazo_reversion` pasados 14 días (P-09) |
| `historial/?limite=&tipo=` | GET | `update.read` | `historial[{id, paquete_id, tipo, en, actor, serie, version_producto, detalle}]`, lo último primero, `limite` ≤ 500, `tipo` repetible (FUN-187) |

Y el campo aditivo de **`GET /health/`** (público): `"actualizacion": {estado, en_curso, programados, orden_pendiente}`.

## 2 · Cuerpos reales

**`POST paquetes/importar/` → 201** (recortado: el `manifiesto` completo y las dos filas del historial están en la captura):

```json
{
  "paquete_id": "17171717-0001-4000-8000-000000000001",
  "nombre": "Reportes 1.4.0 · corrección del boletín",
  "version_producto": "2.11.1", "serie": 7, "modulos": ["reporting"],
  "kid": "upd-dev-1", "sha256": "911d33b7…3ae445", "bytes": 1821, "archivo": "reportes-1.4.0.avupd", "origen": "unidad",
  "recibido_en": 1792613101171, "importado_por": "d9ad3316-…",
  "manifiesto": {"serie": 7, "archivos": 2, "bytes": 249,
                 "modulos": [{"nombre": "reporting", "version": "1.4.0", "version_datos": 4, "version_contrato": 1, "serie": 7, "cambia_contrato": false,
                              "requiere": {"nodo": 1}, "migraciones": ["0004_parche_de_ejemplo"]}],
                 "requisitos": {"contrato_biblioteca": 2, "cliente_minimo": "2.10.0", "contrato_red": null, "espacio_bytes": 0}},
  "estado": "verificado", "en_curso": false, "accion": null, "orden_id": null, "ventana": null,
  "aplicado_en": null, "revertible_hasta": null, "revertible": false, "incompatibilidades": [], "ultima_en": 1792613101171,
  "historial": [
    {"id": 1, "tipo": "recibido", "en": 1792613101171, "actor": "d9ad3316-…", "serie": 7, "version_producto": "2.11.1",
     "detalle": {"nombre": "…", "modulos": ["reporting"], "kid": "upd-dev-1", "sha256": "911d33b7…", "bytes": 1821, "origen": "unidad"}},
    {"id": 2, "tipo": "verificado", "…": "…", "detalle": {"…": "…", "compatibilidad": {"ok": true, "problemas": [], "avisos": [], "espacio_requerido": 67111183, "espacio_libre": 528031686656}}}
  ]
}
```

**`POST paquetes/{id}/aplicar/` → 202**: la misma ficha con `"estado": "aplicando", "en_curso": true, "accion": "aplicar", "orden_id": "7bfafe91-…"` y además

```json
"orden": {"orden_id": "7bfafe91-d062-4827-80cb-81cc2a5d0eda", "accion": "aplicar", "limite_minutos": 5,
          "pasos": ["comprobar", "respaldar", "instantanea", "copiar", "migrar", "verificar"], "emitida_en": 1792613101171}
```

**`GET estado/` → 200** (con una orden en curso):

```json
{"estado": "aplicando",
 "en_curso": {"paquete_id": "17171717-0001-…", "nombre": "Reportes 1.4.0 · corrección del boletín", "accion": "aplicar", "orden_id": "7bfafe91-…", "desde": 1792613101171},
 "programados": [], "revertibles": [], "paquetes": {"aplicando": 1}, "orden_pendiente": true, "canal": null,
 "version": "2.11.0", "contrato_biblioteca": 2, "dias_reversion": 14, "espacio_libre": 528031567872,
 "modulos": [{"nombre": "acceso", "modulo": "MOD-001", "version": "1.0.0", "version_datos": 20, "version_contrato": 1, "serie": 1, "actualizable": true,
              "produce": ["identidad", "acceso"], "consume": {"audit": [1, 1], "licenciamiento": [1, 1]}}, "…"],
 "servidor_en": 1792613101171}
```

**`GET paquetes/` → 200** (un USB con un paquete, ninguno importado):

```json
{"candidatos": [{"id": "0475b79ec9ce6242bb5d624f", "nombre": "reportes-1.4.0.avupd", "origen": "unidad", "bytes": 1821, "modificado_en": 1792613101195, "fuente": "E:", "importado": null}],
 "paquetes": [], "servidor_en": 1792613101171}
```

**Errores reales:**

```json
{"codigo": "firma_invalida", "motivo": "sin_firma", "detail": "El paquete no está firmado: no se instala nada sin firma."}                       ← 422
{"codigo": "paquete_invalido", "motivo": "estructura", "detail": "El archivo no tiene la forma de un paquete de actualización de AVACOM."}       ← 422 (un byte cambiado)
{"codigo": "firma_invalida", "motivo": "kid_desconocido", "kid": "prod-2030-1", "detail": "El paquete fue firmado con una llave que este equipo no reconoce."}
{"codigo": "sesion_activa", "sesiones_activas": 1, "detail": "Hay una clase en curso: la actualización se difiere (FUN-183, R-01)."}             ← 409
{"codigo": "contrato_incompatible", "incompatibilidades": [{"codigo": "contrato_biblioteca", "modulo": "", "detalle": "El paquete habla el contrato 3 de AVACOM Biblioteca y este nodo el 2."}],
 "detail": "El paquete no es compatible con los módulos instalados: la instalación no inicia (BR-013, INV-007)."}                                 ← 409
{"codigo": "sin_permiso", "permiso": "update.apply", "detail": "Tu rol no tiene concedido update.apply."}                                        ← 403 (técnico sin escalada)
{"codigo": "actualizacion_en_curso", "reintentar_en_s": 60, "detail": "El aula se está actualizando; vuelve a intentarlo en unos minutos."}      ← 503 en POST /api/aula/sesiones/
```

Los `motivo` de un 422 son un catálogo cerrado (`dominio/catalogos.MENSAJES_DE_MOTIVO`): `demasiado_grande`, `demasiado_corto`, `estructura`, `truncado`, `bytes_sobrantes`, `cifrado`, `zip64`, `metodo`, `nombre_duplicado`, `directorio`, `enlace`, `sin_manifiesto`, `sin_firma`, `firma_formato`, `version_firma_desconocida`, `kid_invalido`, `kid_desconocido`, `firma_invalida`, `manifiesto_ilegible`, `version_formato_desconocida`, `etiqueta_critica_desconocida`, `campo_faltante`, `campo_invalido`, `producto_distinto`, `ruta_invalida`, `ruta_absoluta`, `ruta_con_retroceso`, `ruta_duplicada`, `ruta_fuera_del_modulo`, `ruta_intocable`, `extension_prohibida`, `archivo_no_declarado`, `archivo_faltante`, `tamano_distinto`, `sha_distinto`, `demasiados_archivos`.

## 3 · El contrato con el `Host` (P-06, P-07)

Carpeta: `%ProgramData%\AVACOM\OPS Master\Actualizaciones\` (en desarrollo, `AVACOM_ACTUALIZACION_DIR`). `entrada\`, `paquetes\<id>.avupd`, `staging\<id>\`, `versiones\<id>\anterior\` (la instantánea, la escribe el `Host`), `orden.json`, `resultado.json`, `resultados\<orden>.json`.

**`orden.json`** (lo escribe Django, de forma atómica y sin sobrescribir; real):

```json
{"formato": 1, "orden_id": "7bfafe91-d062-4827-80cb-81cc2a5d0eda", "paquete_id": "17171717-0001-4000-8000-000000000001", "accion": "aplicar",
 "emitida_en": 1792613101171, "emitida_por": "d9ad3316-…", "limite_minutos": 5, "ventana": null, "nota": "",
 "paquete": {"nombre": "Reportes 1.4.0 · corrección del boletín", "version_producto": "2.11.1", "serie": 7, "sha256": "911d33b7…", "bytes": 1821, "kid": "upd-dev-1"},
 "modulos": [{"nombre": "reporting", "version": "1.4.0", "version_datos": 4, "version_contrato": 1, "serie": 7,
              "migraciones": [{"nombre": "0004_parche_de_ejemplo", "reverso": "0003_corte_cola_unica"}]}],
 "archivos": [{"ruta": "reporting/dominio/parche_de_ejemplo.py", "bytes": 95, "sha256": "801a4dfd…"},
              {"ruta": "reporting/migrations/0004_parche_de_ejemplo.py", "bytes": 154, "sha256": "e90a33e7…"}],
 "carpetas": {"staging": "staging/17171717-0001-…", "instantanea": "versiones/17171717-0001-…/anterior"},
 "pasos": ["comprobar", "respaldar", "instantanea", "copiar", "migrar", "verificar"]}
```

En una reversión: `"accion": "revertir"`, `nota` con lo que escribió la administración, las migraciones en orden inverso (se migra a cada `reverso`) y `pasos` sin `instantanea` (se restaura desde ella). **Orden real en el Host (D-20):** `comprobar → respaldar → migrar → copiar → verificar`: se migra hacia atrás *antes* de devolver el código, porque el reverso necesita el código que define la migración.

Lo que el `Host` hace (Fase 4, implementado en `installer/src/host/Actualizacion/`), con un `checkpoint.json` antes de cada paso: **comprobar** (firma y SHA del `.avupd` otra vez, espacio, cero sesiones: si hay una, `aplazada`), **respaldar** (`Datos.Respaldar`: base, `-wal`, `-shm` y `backend.env`, con el servicio parado), **instantanea** (copiar a `versiones\<id>\anterior\` cada archivo de `archivos[]` que exista en `Backend\`), **copiar** (desde `staging\` verificando el SHA-256 de cada archivo al escribirlo), **migrar** (`preparar` con `check` y `migrate` por módulo, en orden de dependencias), **verificar** (arrancar, `/health/` con los módulos en la versión nueva). Fallo en 2 a 6: reversión automática a la instantánea y a la copia, verificada, dentro de `limite_minutos`. Si la reversión falla: no borrar nada y `reversion_fallida`.

**`resultado.json`** (lo escribe el `Host`; Django lo lee al arrancar y en cada tick, lo registra y lo archiva; real, simulado por la prueba):

```json
{"formato": 1, "orden_id": "7bfafe91-…", "paquete_id": "17171717-0001-…", "accion": "aplicar", "resultado": "aplicado", "paso": "verificar",
 "iniciado_en": 1792613101171, "terminado_en": 1792613196171, "duracion_ms": 95000, "detalle": "…", "respaldo": "C:\\…\\Respaldos\\2.11.1-20261021-1500",
 "migraciones": [{"modulo": "reporting", "nombre": "0004_parche_de_ejemplo", "ok": true}], "error": null}
```

`resultado` ∈ `aplicado` · `revertido` · `reversion_fallida` · `aplazada` · `rechazada`; `paso` es el último alcanzado. Lo que no tenga esta forma no se registra. Un resultado de una orden que no está en curso se archiva sin registrar (y se deja un ERROR en el log).

## 4 · Interfaz `actualizacion.servicios` (para los otros módulos)

| Función | Qué hace |
|---|---|
| `en_curso() -> bool` | ¿Hay una orden aceptada y sin resultado? De memoria; nunca lanza (ante un fallo: `False`). La usa el middleware del 503. |
| `estado_resumido() -> dict` | `{estado, en_curso, programados, orden_pendiente}` para `/health/`. Nunca lanza. |
| `tick(origen) -> dict` | Un ciclo del vigilante a mano: `{resultado, ordenes, bloqueadas, vencidas, archivados, detectados, errores}`. |

## 5 · Eventos (`actualizacion.*.v1`, cola única de MOD-015, clase técnico)

| Evento | Cuándo | Carga (además de `paquete_id`, `serie`, `version_producto`, `tipo`) |
|---|---|---|
| `disponible_detectada` | el vigilante ve un `.avupd` nuevo en una fuente (una vez por proceso) | `candidato`, `origen`, `bytes`, `nombre` |
| `paquete_importado` · `paquete_verificado` | al importar (y `compatible: false` si quedó incompatible) | `nombre`, `modulos[]`, `kid`, `sha256`, `bytes`, `origen`, `compatibilidad` |
| `paquete_rechazado` (extensión) | un archivo no pasó la firma o la forma | `motivo`, `codigo`, `sha256`, `bytes`, `origen`, `nombre` |
| `ventana_programada` | al programar | `desde`, `hasta` |
| `bloqueada` | aplicar o revertir con una clase; la ventana con una clase; el `Host` aplazó | `sesiones_activas`, `motivo` |
| `modulo_aplicada` · `migracion_ejecutada` (una por migración) · `revertida` · `reversion_fallida` (extensión) | al registrar el resultado del `Host` | `orden_id`, `accion`, `resultado`, `paso`, `duracion_ms`, `respaldo` (booleano), `migraciones[]`, `error` |
| `resultado_registrado` | siempre, al registrar un resultado | `resultado`, `accion`, `duracion_ms`, `orden_id` |

## 6 · Variables (`backend/README.md`)

`AVACOM_ACTUALIZACION_DIR` (sólo desarrollo y pruebas), `AVACOM_ACTUALIZACION_UNIDADES` (carpetas que hacen de USB), `AVACOM_ACTUALIZACION_CANAL` (apagado), `AVACOM_ACTUALIZACION_VIGILANTE` · `AVACOM_ACTUALIZACION_INTERVALO_S` (30 s), `AVACOM_ACTUALIZACION_MAX_MB` (512).
