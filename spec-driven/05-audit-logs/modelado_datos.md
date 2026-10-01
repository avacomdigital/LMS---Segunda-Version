# 02 · Audit (MOD-019) · Modelo de datos `m19_*` y logs de archivo

| Campo | Valor |
|---|---|
| Estado | **Construido** (2026-09-30). Lo implementa `backend/audit/` (modelos, migración `0001_initial`, triggers) y `backend/expediente/migrations/0003_auditoria_vista.py`. Los endpoints están en [backend.md](backend.md); las pantallas y el lado cliente, en [frontend.md](frontend.md). |
| Módulo | **MOD-019 · Audit** del Documento Maestro (FUN-195…201, BR-097/099/100/105, INV-002/003/027, AC-003/054/081, VER-01/04, TST-071/072, NFR-036/039). |
| Requisitos de partida | La tabla 019-01…019-10 y §3 de [introduccion.md](introduccion.md). |
| Modelo de datos | Segunda versión del modelo (`specs/analisis/segunda-version-modelo.md`): la tabla `bitacora` del dominio **Acceso y RBAC**. Pasa de 1 a 2 tablas de auditoría (`bitacora_tramo` es nueva); el v2 sube de 28 a 29 (a confirmar con el CTO, Q-1 de §6.2 de la introducción). |
| Dueño único | MOD-019 escribe sólo `m19_*`. Los demás módulos no escriben la bitácora: llaman al puerto `uow.auditoria.registrar(...)` de su propia unidad de trabajo, cuyo adaptador llega a `audit.servicios.anexar` dentro de la misma transacción del hecho (BR-003, un solo escritor). |
| Lo que NO es tabla | Los logs de diagnóstico (§4): archivos JSON Lines rotativos en cada equipo y en el nodo. Nunca van a la base de datos. |

---

## 1 · Decisiones (y por qué)

| # | Decisión | Por qué / alternativa |
|---|---|---|
| D-1 | **`m19_bitacora` sustituye a `m19_auditoria`** y la tabla vieja queda como `m19_auditoria_legado` (sólo lectura por triggers) durante un ciclo de versión. `m19_auditoria` pasa a ser una **VISTA** sobre `m19_bitacora` con las columnas de siempre (`id = secuencia`, `actor_id = COALESCE(usuario_id, actor_tipo)`, `momento = ocurrido_en`), así `expediente.Auditoria` (ahora `managed = False`) sigue leyendo lo mismo. | 28 pruebas de cuatro módulos leen `Auditoria.objects`; cambiarlas no aportaba nada. §3.4 de la introducción. |
| D-2 | **`usuario_id` es referencia lógica (CV-08), no FK.** Con Q-34 abierta los módulos declaran actores que no son usuarios (`docente`, `cliente`, un `persona_id`). Por eso `actor_tipo` admite un valor más que §3.2: **`declarado`** (el asiento no prueba la identidad). `dispositivo_id` sí es FK RESTRICT a `m09_dispositivo`: siempre viene validado del contexto. | El modelo v2 pedía FK; con sesión obligatoria todo asiento llevará `usuario` real y la FK podrá añadirse sin migrar datos. |
| D-3 | **La huella se calcula sobre un contenido canónico fijo** (17 campos, JSON con claves ordenadas, sin espacios, UTF-8, `null` explícito): `huella = SHA-256(huella_previa ‖ canónico)`; génesis = 64 ceros. La función vive en `audit/dominio/huella.py`, sin Django, y es la misma en la migración, el anexado y la verificación. | FUN-196 / INV-002: cualquier cambio de un campo canónico se detecta; recalcular no depende de la versión del serializador. |
| D-4 | **Un único tramo abierto** (`abierta = 1`, índice único parcial `uq_m19_tramo_abierto`) hace de cabeza de la cadena: su `hasta_secuencia` y `huella_cierre` avanzan en la misma transacción que cada asiento. No hace falta una tercera tabla de «cabeza». | §3.2. El estado del tramo abierto puede ser `activa`, `verificada` o `con_salto`; al rotar pasa a `rotada` y nace el siguiente con `huella_previa = huella_cierre`. |
| D-5 | **Inmutabilidad en tres capas**: (1) el manager del ORM no permite `update/delete/bulk_*`, `save()` de una fila existente ni `delete()`, y cada intento deja `auditoria.alteracion_intentada` (resultado `denegado`); (2) triggers SQLite `m19_bitacora_no_update` / `_no_delete` abortan con `bitacora_inmutable` también por SQL directo; (3) la verificación comprueba que ambos triggers existan en `sqlite_master` (`triggers_ausentes` es un salto). | BR-100, INV-027, AC-081. No se pretende impedir al dueño del disco: se pretende que no pueda alterar sin que se note. |
| D-6 | **Catálogo cerrado y versionado de acciones** (`audit/dominio/catalogos.py`, `VERSION_CATALOGO`): clave `<dominio>.<objeto>.<verbo>`, módulo, `exige_motivo`, `sensible`, `evento_origen`. Familias abiertas por prefijo: `aula.control.*`, `aula.distribucion.*`, `aula.envio.*`, `estudio.envio.*` (y `prueba.*` sólo en pruebas). Fuera del catálogo: en pruebas falla (`AccionDesconocida`); en producción se asienta `auditoria.accion_desconocida` con la clave original. | §3.5: perder el hecho es peor que registrarlo con otra etiqueta. |
| D-7 | **Tamaño de rotación estimado**: `LENGTH` de los campos variables más 320 bytes por fila (SQLite no da el tamaño por tabla sin `dbstat`). Umbral por defecto 100 MB (`AVACOM_LMS_AUDITORIA_UMBRAL_MB`). Al rotar, las filas **no se borran**: se congelan en un archivo `tramo-<desde>-<hasta>.jsonl` con manifiesto HMAC. | FUN-201, INV-027. La purga a 5 años y la anonimización (CAP-117, BR-098) son V1 y operarán sobre archivos rotados. |
| D-8 | **Cola de salida propia** `m19_evento_salida` (misma forma que `m01_` y `m07_`) para `auditoria.cadena_verificada/salto_detectado/bitacora_rotada/tramo_exportado.v1`. `auditoria.registro_creado.v1` **no** se publica por asiento (duplicaría cada escritura). | 019-09 hasta que exista MOD-015. No cuenta como tabla del modelo v2. |
| D-9 | **Migraciones futuras sobre `m19_bitacora`** deben terminar con `RunSQL(triggers.sentencias(triggers.SQL_CREAR))`: el editor de esquema SQLite de Django reconstruye la tabla en muchos `AlterField` y pierde los triggers. | Lo detectaría la verificación igualmente, pero mejor no provocar un «salto» por una migración. |

---

## 2 · Modelo `m19_*`

```
 m19_bitacora_tramo ──1:N── m19_bitacora          (un tramo = un segmento contiguo de la cadena; el abierto es la cabeza)
 m19_bitacora ──N:1── m09_dispositivo (FK RESTRICT, nulo)        usuario_id → m01_usuario (referencia lógica, nulo = sistema)
 m19_evento_salida       (outbox auditoria.*.v1, sin FK)
 m19_auditoria           VISTA de lectura sobre m19_bitacora      m19_auditoria_legado   tabla vieja, sólo lectura (triggers)
```

### 2.1 `m19_bitacora` · sólo inserción (`bitacora` del v2)

| Columna | Tipo | Nulo | Notas |
|---|---|---|---|
| `id` | CHAR(36) UUID | no | PK, generado en el nodo |
| `secuencia` | BIGINT | no | **UNIQUE**, monótona, sin huecos ni reutilización. Base de la cadena (019-02) |
| `huella_previa` | CHAR(64) | no | Hex SHA-256 del asiento anterior; génesis = 64 ceros |
| `huella` | CHAR(64) | no | SHA-256(`huella_previa` ‖ contenido canónico) |
| `ocurrido_en` | BIGINT ms | no | Reloj del **nodo**, nunca el de la tableta |
| `usuario_id` | VARCHAR(64) | sí | Referencia lógica a `m01_usuario` (D-2). NULL = sistema |
| `actor_tipo` | VARCHAR(12) | no | `usuario` · `declarado` · `sistema` · `dispositivo` · `instalador` (CHECK) |
| `roles_activos` | JSON | sí | Lista de roles con los que actuó (el rol efectivo de la sesión, BR-021). Obligatoria en denegaciones |
| `modulo` | VARCHAR(24) | no | `acceso` · `aula` · `dispositivos` · `estudio` · `evaluacion` · `auditoria` · `instalacion` · `expediente` (`pruebas` sólo en tests). Sustituye a `modulo_app_id` hasta que exista `modulo_app` |
| `accion` | VARCHAR(64) | no | Clave del catálogo (D-6) |
| `resultado` | VARCHAR(16) | no | `ok` · `denegado` · `fallido` (CHECK) |
| `objeto_tabla` | VARCHAR(64) | sí | p. ej. `m07_sesion` |
| `objeto_id` | VARCHAR(64) | sí | Identificador del objeto afectado |
| `valor_anterior` | JSON | sí | Sólo los campos que cambian, no la fila entera |
| `valor_nuevo` | JSON | sí | Ídem |
| `motivo` | VARCHAR(250) | sí | Obligatorio para las acciones `exige_motivo` (calificaciones, anulaciones, exportaciones, borrado remoto) |
| `origen` | VARCHAR(12) | no | `api` · `ws` · `sistema` · `instalador` · `migracion` · `prueba` (CHECK) |
| `dispositivo_id` | CHAR(36) FK `m09_dispositivo` RESTRICT | sí | El aparato desde el que se hizo (019-01), validado por el middleware; nunca inventado |
| `correlacion_id` | VARCHAR(64) | sí | El `corr` de la petición: une petición, asiento, evento y log |
| `evento_id` | VARCHAR(64) | sí | Evento de la cola del que derivó (019-09). Hoy sólo lo migrado: `m19_auditoria:<id>` |
| `tramo_id` | CHAR(36) FK `m19_bitacora_tramo` RESTRICT | no | Tramo en que quedó |

Índices: `(usuario_id, ocurrido_en)`, `(modulo, ocurrido_en)`, `(resultado, ocurrido_en)`, `(objeto_tabla, objeto_id, ocurrido_en)`, `(accion, ocurrido_en)`, `(dispositivo_id, ocurrido_en)`, `(correlacion_id)` y `UNIQUE(secuencia)`.

CHECK: `resultado`, `origen` y `actor_tipo` dentro de sus listas; `actor_tipo = 'usuario' → usuario_id IS NOT NULL`; `secuencia >= 1`.

**Contenido canónico de la huella** (D-3): `secuencia, ocurrido_en, usuario_id, actor_tipo, roles_activos, modulo, accion, resultado, objeto_tabla, objeto_id, valor_anterior, valor_nuevo, motivo, origen, dispositivo_id, correlacion_id, evento_id`.

### 2.2 `m19_bitacora_tramo` (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | CHAR(36) UUID | PK |
| `desde_secuencia` | BIGINT | Primer asiento del tramo (`>= 1`) |
| `hasta_secuencia` | BIGINT | Último asiento; cabeza mientras está abierto. `desde - 1` si aún no tiene asientos (CHECK `hasta >= desde - 1`) |
| `huella_cierre` | CHAR(64) | Huella del último asiento; al rotar, `huella_previa` del primero del tramo siguiente |
| `estado` | VARCHAR(12) | `activa` · `verificada` · `con_salto` · `rotada` (CHECK) |
| `abierta` | BOOL | El tramo que recibe asientos. **Índice único parcial** `uq_m19_tramo_abierto WHERE abierta` (D-4) |
| `verificado_en` | BIGINT ms, nulo | Última verificación |
| `verificado_hasta` | BIGINT, nulo | Última secuencia verificada (la verificación avanza por bloques de 5.000 y retoma de aquí) |
| `salto_en_secuencia` | BIGINT, nulo | Primera secuencia discordante |
| `salto_causa` | VARCHAR(32) | `huella_discordante` · `secuencia_con_hueco` · `secuencia_repetida` · `huella_previa_no_enlaza` · `cabeza_discordante` · `triggers_ausentes` |
| `exportado_en` | BIGINT ms, nulo | Última exportación del tramo entero (019-06) |
| `firma` | TEXT, nulo | Firma HMAC-SHA256 del manifiesto del archivo rotado (`hmac-sha256:<hex>`) |
| `archivo` | VARCHAR(260), nulo | Ruta del archivo de tramo rotado (019-07) |
| `rotado_en` | BIGINT ms, nulo | |
| `creado_en` | BIGINT ms | |

### 2.3 `m19_evento_salida` (outbox)

`agregado_tipo`, `agregado_id`, `tipo_evento` (`auditoria.cadena_verificada.v1` · `auditoria.salto_detectado.v1` · `auditoria.bitacora_rotada.v1` · `auditoria.tramo_exportado.v1`), `carga` JSON, `creado_en`, `publicado_en`, `intentos`. Misma forma que `m01_evento_salida` y `m07_evento_salida`; se unificarán en `m15_evento` cuando exista MOD-015.

### 2.4 Lo que cambia en otros módulos

| Dónde | Cambio |
|---|---|
| `expediente.Auditoria` | `managed = False` (migración `expediente.0003`): es la vista `m19_auditoria`. `save()` lanza siempre; nadie escribe por ahí |
| `acceso.dominio.plantillas` | Permisos nuevos `audit.export` (sensible, ORGANIZATION) y `diagnostics.read` (ORGANIZATION); `audit.read` conserva su código. ADMIN recibe los tres; **TECHNICIAN sólo `diagnostics.read`** (BR-097). Migración `acceso.0008` los siembra en instalaciones existentes |
| Puertos `Auditoria` de acceso, aula, dispositivos y estudio | Misma firma (`registrar(actor, accion, tabla, objeto_id, anterior, nuevo)`) ampliada con `**extra`: `motivo`, `resultado`, `dispositivo_id`, `evento_id`. ~30 llamadas no cambiaron |

---

## 3 · Migración `audit.0001_initial` (§3.4)

1. Crea las tres tablas, índices y CHECK.
2. Copia cada fila de `m19_auditoria` por orden `(momento, id)` asignando `secuencia`, `huella_previa` y `huella` (función pura `audit/infraestructura/migracion.py`, la misma que prueban los tests): `origen = 'migracion'`, `actor_tipo` deducido (`sistema` si el actor era vacío, `sistema` o `cliente`; `instalador`; si no, `declarado`), `modulo` deducido del prefijo de la acción, `resultado = 'ok'`, `evento_id = m19_auditoria:<id>`.
3. Crea el tramo abierto con la cabeza resultante y asienta `auditoria.cadena_migrada` con el conteo y la huella final (o `auditoria.bitacora_abierta`, el génesis, si la tabla estaba vacía). Deja la línea en `instalacion.log`.
4. `ALTER TABLE m19_auditoria RENAME TO m19_auditoria_legado` + triggers de sólo lectura + `CREATE VIEW m19_auditoria`.
5. Triggers de inmutabilidad de `m19_bitacora`.

Reversible sólo hacia adelante. En el nodo de desarrollo convirtió 172 filas y la cadena verificó sin saltos (`verificar_cadena()` → `verificada`, 173 asientos).

**Base de pruebas.** Cada base de prueba arranca con la cadena vacía pero válida (el génesis lo deja la migración; un `TransactionTestCase` que vacía tablas vuelve a crearlo con el primer asiento). El corredor de pruebas retira y repone los triggers alrededor del vaciado de tablas (`DELETE` que los triggers abortarían); en producción nada toca los triggers. Romper la cadena en una prueba: `tools/romper_cadena.py` (alterar, borrar, quitar triggers), nunca SQL suelto.

---

## 4 · Logs de archivo (no es tabla)

| | Backend (nodo) | OPS y Student (equipos) |
|---|---|---|
| Formato | JSON Lines, un objeto por línea | Ídem |
| Archivos | `backend-app.log` (todo, con `ruta` happy/sad/bad) · `backend-errores.log` (WARNING+) · `backend-auditoria.log` (un renglón por asiento, sin valores; verificaciones, saltos, rotaciones) · `backend-clientes.log` (lo que suben OPS y Student) · `instalacion.log` · `pruebas-<corrida>.log` | `{app}-app.log` · `{app}-errores.log` (WARNING+), más el `fallos-{app}.log` plano de siempre |
| Carpeta | `AVACOM_LMS_DIR_LOGS` → instalado `%ProgramData%\AVACOM\OPS Master\Logs` → desarrollo `backend\logs` → pruebas: temporal por corrida (jamás ProgramData). Si no se puede escribir, cae a `%TEMP%\avacom-lms\logs` y lo avisa | `AVACOM_LMS_DIR_LOGS` → Windows `%LOCALAPPDATA%\AVACOM\lms\logs` · Android el directorio privado de la app |
| Rotación | 2 MB × 5 por archivo (`Registro.cs` del instalador). Se purgan: no son evidencia | Ídem |
| Campos | `ts, nivel, canal, app, modulo, evento, ruta, caso, dispositivo_id, usuario_id, corr, secuencia_bitacora, mensaje, detalle, traza, logger` | `ts, nivel, canal, app, modulo, evento, ruta, mensaje, detalle, traza, corr, dispositivo_id, version_app` |
| Canales | `escritura` · `comunicacion` · `dispositivo` · `aplicacion` · `auditoria` · `instalacion` | `escritura` · `comunicacion` · `dispositivo` · `aplicacion` |
| Privacidad | Filtro de saneamiento por clave (`secreto, pin, token, password, clave, respuesta, nombre, apellidos, dni, documento, authorization, correo…`; se admiten `*_id`, `identificador_hw`, `corr`): el valor se sustituye por `[redactado]`. Lo verifica una prueba sembrando esos valores | Mismo filtro en `RegistroLocal.Sanear` |
| Correlación | `corr` por petición (`X-Avacom-Correlacion`, se respeta la que trae el cliente); va al asiento (`correlacion_id`) y al log | Cada petición genera su `corr`; el WebSocket uno por conexión |

---

## 5 · Preguntas abiertas que tocan el modelo

Las de §6.2 de la introducción siguen en pie: Q-1 (29.ª tabla y `modulo` como texto), Q-2 (HMAC con clave del nodo frente a firma asimétrica), Q-3 (umbral y cadencia), Q-7 (secuencias tras restaurar un respaldo: la cabeza en `backend-auditoria.log`). Nuevas de la construcción: `actor_tipo = declarado` (D-2) y `auditoria.registro_creado.v1` sin publicar por asiento (D-8).
