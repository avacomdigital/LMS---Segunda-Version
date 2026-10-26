# 18 · Backup & Recovery (MOD-016) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **Backend construido** (2026-10-26), **sin instalador ni pantallas de OPS**. App `backend/respaldo/`, tablas `m16_*`, API `/api/respaldo/`, permisos `backup.*` (acceso 0021), 14 eventos en la cola única, 15 acciones de bitácora. Lo que falta está en §10 y en [03-pruebas.md](03-pruebas.md) §5. El prompt está en [00-prompt.md](00-prompt.md). |
| Módulo | **MOD-016 · Backup & Recovery** (DOM-009 · Plataforma y Continuidad). CAP-100, CAP-101 (backend), CAP-103 y CAP-104 (a nivel de módulo; CAP-102 sólo la compuerta). FUN-169 a FUN-178 salvo FUN-172. |
| Contrato | [02-api.md](02-api.md). Operación del técnico: [04-operacion.md](04-operacion.md). Guía del personal administrativo: [05-guia-administrativa.md](05-guia-administrativa.md). Ejemplos de los archivos que genera: [ejemplos/](ejemplos/). |
| Se apoya en | MOD-015 (reloj, secuencia y cola única: **existe**), MOD-019 (bitácora), MOD-001 (permisos, sesiones, nombre de la institución), MOD-007 (¿hay clase?), MOD-018 (revalidar la licencia), MOD-021/013/011 (reconstruir lo derivado). No lee ni escribe ninguna tabla ajena (R-03). |

> **Principio (Documento Maestro):** *garantiza que existe una copia utilizable del aula y que se puede volver a ella.* Y la regla del encargo: **sólo el personal de AVACOM WORLD respalda y restaura**; la institución **lee** lo que el equipo deja para ella.

## 1 · Qué entra y qué no

| Entra | Dónde |
|---|---|
| Quién opera (D-1 a D-3): permisos, rol efectivo y pase de soporte | `acceso/dominio/plantillas.py` · `acceso/migrations/0021` · `infraestructura/autorizacion.py` · `dominio/pase.py` |
| El archivo `.avbak`: cifrado, trozos, manifiesto en claro sin datos, lector estricto | `dominio/cripto.py` · `dominio/formato.py` |
| Respaldar (completo/incremental), verificar, exportar, restaurar, catalogar, retener | `aplicacion/motor.py` |
| Calendario, aplazar con clase, reanudar, verificación y prueba periódica | `aplicacion/vigilante.py` · `dominio/programacion.py` · `infraestructura/vigilante.py` |
| Estado derivado de un historial de sólo inserción | `dominio/estados.py` · `m16_historial` |
| Archivos para el personal administrativo | `dominio/informes.py` · carpeta `Informes\` · rutas `constancia`, `resumen`, `informes` |
| Clave y identidad del equipo fuera de la base; custodia | `infraestructura/clavero.py` |
| La purga de MOD-015 por fin elegible (BR-017) | `nodo/infraestructura/respaldo.py` (`RespaldoVerificado`) |

| NO entra (queda dicho) | Por qué |
|---|---|
| Pantallas PAN-231 y PAN-232 de OPS y `Core/Respaldo/` | El tramo es backend. El contrato ya está en [02-api.md](02-api.md). |
| FUN-172 · punto de recuperación cada 5 s | No es un respaldo: es la durabilidad de los intentos abiertos (D-14). |
| FUN-175 / CAP-102 · restauración selectiva (V1) | La compuerta existe (`modulo_sin_restauracion_aislada`); ningún módulo declara restauración aislada. |
| Respaldo previo de MOD-017 con este módulo; exclusión de `respaldo\tests` en `Build-Installer.ps1` | Archivos con cambios de otra sesión sin commitear. |

## 2 · Arquitectura

Hexagonal, como `actualizacion/`, `nodo/` y `licenciamiento/`:

```
backend/respaldo/
├── models.py                 m16_respaldo · m16_historial · m16_ajuste · m16_pase_usado (§8)
├── servicios.py              la interfaz para los OTROS módulos: verificado_hasta() · cubre() · estado_resumido() · tick()
├── dominio/                  puro, sin Django: catalogos · errores · cripto · formato · estados · programacion · pase · informes
├── aplicacion/               casos de uso, sin Django: puertos · base · motor · acciones · vigilante (Tick)
├── infraestructura/          adaptadores: contenedor (composition root) · repositorios · unidad_trabajo · autorizacion · clavero · almacen · origen · unidades · aplicador · adaptadores · vigilante (el hilo)
├── interfaces/               urls · views (`/api/respaldo/`)
├── claves/                   produccion.json (VACÍO hasta la ceremonia) · desarrollo.json (sop-dev-1, sop-dev-2; sólo fuera de producción)
├── migrations/               0001_initial · 0002_triggers
└── tests/                    emisor (de pruebas) · base · test_formato · test_dominio · test_infraestructura · test_motor · test_acceso · test_vigilante · test_arquitectura
```

## 3 · Quién opera (D-1, D-2, D-3)

| Permiso | Administración | Técnico AVACOM | Otros |
|---|---|---|---|
| `backup.read` (estado, respaldos, constancias, informes) | **sí** | sí | no |
| `backup.run` · `backup.schedule` · `backup.verify` | **no** | sí (emitir el código de custodia, además, **con pase**) | no |
| `backup.export` · `backup.restore` · `backup.restore.module` | **no** | sí **+ pase de soporte** | no |

- **D-1.** El Maestro da `backup.schedule` a la administración y «Respaldar ahora» (JRN-018) al administrador. **Aquí no**: por el encargo, la administración sólo lee. Como `ADMIN` recibe por defecto todo permiso nuevo, las plantillas lo **excluyen** explícitamente (`PERMISOS_DE_RESPALDO_SOLO_DE_AVACOM`) y la migración 0021 se lo **retira** si ya lo tenía.
- **D-2 · el pase de soporte.** El Maestro exige escalada temporal (ESC-01 para restaurar, ESC-03 para exportar), que concede la administración. Pero en MOD-001 **nadie concede un permiso que no tiene** (probado): si la administración no tiene `backup.restore`, la escalada no existe. La segunda llave es entonces un **pase firmado por AVACOM** (`AVSP`: Ed25519, `kid`, `pase_id`, quién, qué operaciones, para qué equipo o `*`, vigencia ≤ 24 h, **un solo uso**), que sólo quien tiene la llave privada de AVACOM puede emitir. Una cuenta de técnico creada por la propia institución **no** puede producirlo. El pase de `backup.schedule` sirve **sólo** para emitir o reemplazar el código de custodia (que abre todos los respaldos); programar el calendario no lo pide. Los pases usados quedan en `m16_pase_usado`; los rechazados, en la bitácora con su motivo.
- **D-3.** Además del permiso, las operaciones del personal de AVACOM exigen que el **rol efectivo** de la sesión sea `TECHNICIAN`: un rol personalizado con `backup.*` que la administración componga no basta. No existe la rama «sin sesión» de los módulos del prototipo (Q-34): un actor declarado en el cuerpo no vale.

**Límite honesto (hallazgo 1 de la revisión independiente, parcialmente abierto):** la administración **sí** puede crear un usuario con el rol `TECHNICIAN` (o asignárselo), porque MOD-001 no restringe quién asigna ese rol. Con él puede **respaldar, programar y verificar** (no exportar, no restaurar y, desde la corrección, **tampoco emitir ni reemplazar la custodia**: eso exige el pase). Respaldar es inocuo: el archivo sale cifrado y sin la clave del equipo ni el código de custodia no se abre; y como emitir la custodia exige pase, quien acuña un técnico **no** obtiene el código. Lo que no se impide: que ese técnico espurio programe, apague el calendario o dispare respaldos (denegación de servicio, no fuga). Cerrarlo del todo exige que sólo AVACOM pueda asignar `TECHNICIAN` en MOD-001: ver Q-B8.

## 4 · El archivo `.avbak` (D-4, D-5)

```
AVBK · versión u16 · largo u32 · manifiesto (JSON canónico, en claro) · trozos { largo u32 · AES-256-GCM(1 MiB) }
```

- **Manifiesto en claro y sin datos:** `respaldo_id`, `tipo`, `base_id`, `creado_en`, `producto`, `secuencia_global`, `nodo_id`, cuántas entradas/bytes/trozos y las **dos claves de datos envueltas**. Así el nodo cataloga un respaldo sin descifrarlo. Ningún nombre de archivo, ninguna huella.
- **Todo lo demás cifrado:** un flujo de registros (`E` cabecera JSON + bytes exactos + SHA-256; `F` fin). Los nombres de los archivos de los alumnos van **dentro** (INV-021).
- **Una clave por respaldo (DEK)**, envuelta **dos veces**: con la **clave del nodo** (restaura en este equipo sin pedir nada) y con la **clave de custodia** derivada (scrypt) del código de la institución (restaura en otro equipo, BR-102).
- **Anti-alteración:** la AAD de cada trozo lleva el SHA-256 de toda la cabecera, su posición y si es el último. Reordenar, repetir, truncar, sobrar o tocar el manifiesto se detecta **sin descifrar nada más** (300 cambios de un bit al azar: 0 aceptados).
- **Lector estricto:** rutas relativas seguras (sin `..`, unidad, `\`, nombres reservados de Windows), sin duplicados, clase válida, huella por entrada, número de entradas y de bytes contra el manifiesto.
- **Escritura:** el largo del flujo se calcula **antes** con los tamaños; un archivo que cambia de tamaño mientras se copia aborta (`archivo_cambio`) en vez de dejar un respaldo incoherente.

### La custodia (BR-102)

`POST custodia/emitir/` genera un **código** de 20 bytes + control (34 caracteres en grupos de 5) y lo devuelve **una vez**, con la **hoja de custodia** lista para imprimir. El equipo **no guarda el código**: sólo la clave derivada, envuelta con su propia clave. Los respaldos hechos **antes** de emitirla abren sólo en su equipo (lo dice el estado y la respuesta: «haz un respaldo completo nuevo»). En un equipo **nuevo** se restaura con el código; el equipo nuevo vuelve a anclarlo y sus respaldos siguen abriendo con el mismo código.

### Dónde viven la clave y la identidad (D-6)

`%ProgramData%\AVACOM\OPS Master\Respaldos\estado\` (`nodo.key`, `nodo.json`), **fuera de la base**: una restauración devuelve la base al pasado y no debe rebobinar la clave con que se cifró lo que sigue en disco. En Windows la clave va con DPAPI ligada al equipo (`LOCAL_MACHINE`): copiar el archivo a otro equipo no sirve.

## 5 · Respaldar (D-7, D-9)

1. Se escribe `iniciado` en el historial (un corte aquí deja un respaldo «incompleto» detectable).
2. **Instantánea consistente** con la API de respaldo de SQLite sobre la conexión del nodo: no detiene a nadie (en WAL los escritores siguen). Comprobado con un hilo escribiendo parejas de filas: la copia nunca trae una pareja a medias. Cota de 60 s si la base está ocupada.
3. **Carpetas de la institución** (`AVACOM_RESPALDO_CARPETAS`, `nombre=ruta` o `nombre:reinstalable=ruta`). Lo reinstalable no entra salvo que se pida («exclusión opcional»). Un **incremental** lleva la base completa y sólo los archivos modificados desde el respaldo anterior (por fecha de modificación; **no** registra archivos borrados).
4. Se escribe `…avbak.parcial`, se vacía a disco y se **renombra**: nunca hay un respaldo a medias con su nombre final.
5. En una transacción: fila `m16_respaldo`, historial, asiento de bitácora y evento. Después, **verificación automática**, **retención** y la **constancia** para la administración (§9).
6. Un solo respaldo o restauración a la vez (`respaldo_en_curso`). Sin espacio (`2 × base + archivos + 64 MB`) se dice **antes** de empezar (`espacio_insuficiente`).

## 6 · Verificar (FUN-173, TST-058)

Descifra **todo**, comprueba la huella de cada entrada, el tamaño del archivo y la huella registrada, extrae la base y corre `PRAGMA integrity_check`, y exige que la **cadena** de un incremental esté completa. Un respaldo que falla **no se descarta**: queda `no_verificado` (con su motivo) y **no es restaurable**. Se reintenta cada 6 h, y el último restaurable se vuelve a probar cada 30 días (CAP-103).

## 7 · Restaurar (D-8, FUN-174, TST-059/060)

Orden estricto; **hasta el paso 5 no se toca nada vivo**:

1. Sin clase abierta (`sesion_activa` si la hay; el pase **no** se gasta).
2. Se resuelve la fuente: un respaldo del equipo, o uno traído de una unidad extraíble (id opaco) con su cadena.
3. **Se descifra y extrae todo en un lugar de trabajo**, comprobando cada huella. Un archivo truncado o alterado **aborta aquí** (`restauracion_abortada`, sin tocar los datos vivos ni gastar el pase). En otro equipo sin el código: `custodia_requerida`.
4. La base extraída pasa `PRAGMA integrity_check` y **no puede traer migraciones que este código no conoce** (`base_de_version_posterior`).
5. **Se gasta el pase** y se toma un **respaldo de seguridad** (el «punto de retorno», verificado). Sin punto de retorno **no se restaura**.
6. Se aplica: la base con la API de respaldo de SQLite **en una sola transacción de escritura** (queda la nueva o queda la anterior, nunca una mezcla; se restituye el modo WAL) y los archivos uno a uno con `os.replace` (no se borra lo que sobre).
7. Se rehace lo derivado, cada paso por la interfaz de su dueño y **sin que uno que falle detenga a los demás**: `migrate` (la base puede ser de una versión anterior) → `nodo.arrancar()` (**INV-002**: el ancla fuera de la base detecta la restauración y el contador **salta**: la secuencia nunca se repite) → **revocar todas las sesiones** (`MotivoCierre.RESTAURACION`, por fin usado) → revalidar la licencia → `search_reconstruir`, `reporting_reconstruir`, `gradebook_reconstruir`.
8. En la base **ya restaurada**: se vuelve a registrar el pase usado, el historial, la bitácora y el evento (la base restaurada no sabe que el pase ya se gastó), y se **cataloga** lo que la base no conocía (el propio respaldo usado y el punto de retorno).
9. **Informe de restauración** para la administración: qué se recuperó, qué se pierde (horas y eventos), qué pasó además y qué hacer ahora.

La respuesta trae `reinicio_recomendado: true`: el servicio sigue vivo y sirve la base restaurada, pero un reinicio limpio es lo prudente (el `Host` no se tocó en este tramo; ver Q-B7).

## 8 · Tablas `m16_*` (D-10)

| Tabla | Qué guarda | Escritura |
|---|---|---|
| `m16_respaldo` | cada `.avbak`: id, tipo, base, disparo, archivo, huella, bytes, secuencia global, versión, nodo, entradas, archivos, si abre con custodia | sólo inserción (trigger) |
| `m16_historial` | una fila por hecho: iniciado, completo_ejecutado, incremental_ejecutado, fallido, interrumpido, reanudado, verificado, no_verificado, exportado, caducado, programado, custodia_emitida, restauracion_*, indice_reconstruido | sólo inserción (trigger) |
| `m16_ajuste` | **una** fila: la programación vigente | mutable (cada cambio queda en historial y bitácora) |
| `m16_pase_usado` | los pases que ya se usaron | sólo inserción (trigger) |

Sin claves foráneas fuera del módulo; sin rutas ni personas. El **estado** de un respaldo se **deriva** de su historial (`estados.derivar`): `en_curso`, `completo_no_verificado`, `completo_verificado`, `exportado`, `caducado` (los cinco del Maestro) más `incompleto` y `fallido` (extensiones marcadas). Una restauración devuelve la base al pasado y los archivos siguen en disco: `reconciliar` **cataloga desde la carpeta** los `.avbak` que la base no conoce y marca los que ya no están.

## 9 · Archivos para el personal administrativo (D-13)

La administración **lee** (`backup.read`) y no opera. El módulo le deja, en `%ProgramData%\AVACOM\OPS Master\Respaldos\Informes\` y por la API, en castellano, **sin datos de personas ni rutas** (INV-021):

| Archivo | Cuándo | Qué dice |
|---|---|---|
| `constancia-AAAAMMDD-HHMM-<id>.txt` | cada vez que un respaldo termina, se verifica o se exporta | qué se guardó, cuándo, si se probó que se puede restaurar, tamaño, dónde está, protección |
| `resumen-de-respaldos.csv` | se actualiza con cada cambio (UTF-8 con BOM, `;`, decimal con coma: abre en Excel) | todo el historial |
| hoja de custodia | **una vez**, al emitir el código (`custodia/emitir/`) | el código y cómo guardarlo. **No se guarda en el equipo** |
| `restauracion-<id>-<instante>.txt` | cada restauración | qué se recuperó, qué se pierde, qué hacer ahora |

`estado/` ofrece además la **alerta de siete días** (`aviso_sin_respaldo`, MSG-066) y `/health/` lo repite sin rutas. Ejemplos reales de formato en [ejemplos/](ejemplos/).

## 10 · Decisiones restantes y preguntas para el CTO

| # | Decisión |
|---|---|
| D-11 | **Retención** por número: se conservan los 14 respaldos más recientes (configurable 3 a 120); jamás se retira la base de un incremental que se conserva ni el último restaurable; uno recién hecho que espera su verificación no se retira. |
| D-12 | **Calendario:** hora local y días elegidos; si el equipo estaba apagado se pone al día **una** vez (y un equipo sin ningún automático hace el primero al programarse); con una clase abierta se **aplaza** (`aplazado_por_clase`); un fallo se reintenta a la hora; un completo cada 7 días y entre medias incrementales. |
| D-14 | **FUN-172 (punto de recuperación cada 5 s) no se construyó**: no es un respaldo sino la durabilidad de los intentos abiertos (WAL + `synchronous`, MOD-015/MOD-010). El evento `respaldo.punto_recuperacion_creado.v1` está en el catálogo y **no se publica**. |
| D-15 | `nodo` usa `RespaldoVerificado`: un evento está «incluido en un respaldo verificado» si su secuencia ≤ la secuencia global del último respaldo restaurable que sigue en el equipo. La purga sigue **apagada** de fábrica (decisión de MOD-015); ahora puede avanzar cuando se encienda. |
| D-16 | `acceso` gana dos funciones de `servicios.py`: `nombre_de_la_organizacion()` y `revocar_sesiones_por_restauracion()`; y `revocar_todas` en su repositorio. Nada más fuera de `respaldo/`, `nodo` (catálogo de eventos y el adaptador), `audit` (catálogo) y `expediente` (`/health/`). |
| D-17 | Cada evento lleva un `agregado_id` único por hecho (`<respaldo>:<instante>:<tipo>`): la cola deduplica por agregado y un mismo respaldo se verifica o se exporta más de una vez. |
| D-20 | **Hallazgos de la revisión independiente (2026-10-26) corregidos:** la custodia exige pase; si la restauración falla al devolver los archivos **después** de la base, se sigue (sesiones, secuencia, licencia, índices) y se responde `ok: false, parcial: true` en vez de dejar el equipo a medias; antes de reemplazar la base se copian **todos** los pases gastados y se vuelven a anotar (la base restaurada no los conoce: un pase gastado no revive); la base de un incremental y «el completo de la semana» exigen un respaldo **restaurable**; el catálogo desde la carpeta descarta manifiestos no creíbles (UUID, fecha futura, sin entradas) y un archivo malo no rompe a los demás; los parámetros de scrypt del manifiesto **no se obedecen** (se exigen los del producto); los archivos restaurados llevan la fecha de la restauración; restaurar desde una unidad trae sólo la cadena (no toda la unidad) comprobando el espacio; la nota libre del técnico va a la bitácora, no al historial que lee la administración. |
| D-19 | **El calendario no exporta.** Sacar un respaldo del equipo es siempre manual y con pase (`destino` de la programación es sólo `local`): un técnico sin pase no puede dejar programada una salida continua de datos. Si el CTO quiere copia automática a una unidad, es una decisión (Q-B11). |
| D-18 | **Reanudar** (FUN-177) = rehacer el respaldo con el **mismo identificador** (no se continúa un archivo cifrado a medias); lo interrumpido hace más de un día no se reanuda, se deja `interrumpido`. |

**Preguntas para el CTO (`Q-B`):**

- **Q-B1** · La **ceremonia de la llave de soporte**: `respaldo/claves/produccion.json` está **vacío**. Hasta entonces, un nodo de producción **no acepta ningún pase**: respalda, verifica y programa, pero **nadie exporta ni restaura**. El emisor está listo (`tools/respaldo/emitir_pase.py`).
- **Q-B2** · ¿Se acepta **reemplazar** la escalada ESC-01/ESC-03 (la concede la administración) por el **pase de AVACOM**? Si el CTO quiere **las dos** llaves (la institución autoriza y AVACOM firma), hay que dar a la administración un permiso concedible sin darle la operación (p. ej. `backup.escalate`); no se hizo por no inventar un permiso.
- **Q-B3** · ¿Quién emite la custodia y a quién se entrega la hoja? Se propone: el técnico, al instalar, al representante legal de la institución.
- **Q-B4** · La **retención por clase de dato** (el Maestro la nombra) y el destino por defecto: hoy 14 respaldos, local.
- **Q-B5** · **FUN-172**: ¿se construye como parte de MOD-015/MOD-010 o se acepta la garantía de WAL?
- **Q-B6** · Medir NFR-030 (20 min / 200 GB), NFR-052 y TST-060 (equipo nuevo en 30 min) y CAP-101 (3 min) con el volumen de un ciclo escolar: **no medido** (el Maestro mismo lo marca «parcial», fila de la matriz).
- **Q-B7** · Restaurar con el servicio **detenido** (el «modo recuperación» de JRN-019) exige el `Host`; hoy se restaura en caliente y se recomienda reiniciar.
- **Q-B8** · La administración puede crear/asignarse el rol `TECHNICIAN` y con él respaldar, programar y verificar. ¿Se restringe en MOD-001 quién asigna ese rol (sólo AVACOM) o se exige el pase también para esas tres operaciones?
- **Q-B12** · La clave del equipo va con DPAPI en modo máquina: cualquier proceso local que **lea** `Respaldos\estado\nodo.key` puede abrirla. Hay que fijar la ACL efectiva de `ProgramData\AVACOM\OPS Master\Respaldos\estado` (sólo SYSTEM y administradores; el instalador la hereda de `ProgramData\AVACOM`) y comprobar con qué cuenta corre el servicio antes de quitar la herencia. **No verificado.**
- **Q-B9** · Restaurar **no borra** archivos que sobren en las carpetas de la institución. ¿Debe?
- **Q-B11** · ¿Copia **automática** a una unidad extraíble (JRN-018 «conecta un disco externo»)? Hoy sólo manual y con pase (D-19).
- **Q-B10** · Cuando exista MOD-014 (archivos por clase de retención) las carpetas de origen salen de su interfaz, no de una variable.
