# 16 · Node Platform y Cola de Salida (MOD-015) · API `/api/nodo/` e interfaz `nodo.servicios`

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-21) en `backend/nodo/`. El diseño, las decisiones y lo pendiente están en [01-diseno.md](01-diseno.md). |
| Respuestas reales | `tests/Avacom.Lms.Core.Tests/Fixtures/nodo/*.json`: las captura `backend/nodo/tests/test_capturar_contrato.py` contra el backend de verdad (`AVACOM_CAPTURAR_CONTRATO=<carpeta>`). Un DTO de C# que no las lee bien es un DTO mal escrito. |
| Cliente | `src/Avacom.Lms.Core/Nodo/` (`NodoApi`, `INodoApi`, `ModelosNodo`, `NodoTexto`, `ReglasDeNodo`). |

## 0 · Convenciones

- **Rutas núcleo (R-01).** Todo `/api/nodo/*` está en `PREFIJOS_NUCLEO`: el modo restringido jamás las rechaza.
- **Quién actúa.** Con sesión (MOD-001), quien firma el JWT. Sin sesión (Q-34, prototipo), el que el cliente declare con `actor`. Con `AVACOM_LMS_EXIGIR_SESION=1`, 401 a lo anónimo.
- **Sin carga útil (R-13).** Ninguna respuesta trae la `carga` de un evento: el técnico ve secuencia, tipo, módulo, estado, tiempos y errores saneados.
- **Tiempo.** Toda marca es del reloj del **nodo** (`servicios.ahora_ms`), en milisegundos.
- **Errores.** `{detail, codigo, …extras}`.

  | HTTP | `codigo` |
  |---|---|
  | 400 | `datos_invalidos` |
  | 403 | `sin_permiso` (+`permiso`; deja el asiento `nodo.acceso_denegado`) |
  | 404 | `no_encontrado` · `consumidor_desconocido` |
  | 409 | `consumidor_sin_aplicador` · `problema_ya_resuelto` · `reproceso_fallido` (+`error`) |
  | 503 | `nodo_restringido` (+ cabecera `Retry-After: 30`; reservado: nada lo responde hasta la Fase 5) |

## 1 · Rutas

| Ruta | Verbo | Permiso | Qué devuelve |
|---|---|---|---|
| `estado/` | GET | `node.health.read` | **El estado del nodo evaluado ahora** (y publicado si cambió): `estado` (`arrancando`·`operativo`·`restringido`·`en_recuperacion`·`detenido`), `motivos[]`, `restringido`, `version`, `arranque{id, apagado_sucio_previo, restauracion{max_en_base, ancla, sin_ancla, contador, detectada_en}?}`, `base{transaccion_inmediata, integra, wal_bytes}`, `disco{libre_bytes, total_bytes}` (null = no medido), `reloj{ahora, marca_alta, retroceso_ms}`, `cola{eventos, ultima_secuencia, contador, problemas, consumidores[{nombre, estado, pendientes, problemas}]}`, `purga{habilitada, respaldo_verificado_hasta}`, `servidor_en`. |
| `cola/` | GET | `node.queue.read` | **La cola por consumidor** (CAP-097): `consumidores[]` con `nombre`, `modulo`, `version_contrato`, `estado`, `pendientes`, `problemas`, `registrado_en`, `actualizado_en` y `fuentes[{fuente, marca, ultima_secuencia, pendientes, estado, actualizada_en, reintento{secuencia, intentos, proximo_en, error}?}]`; `eventos`, `ultima_secuencia`, `contador`, `problemas`, `cortes[{modulo, ultima_legada, cortado_en}]`, `purga`, `servidor_en`. |
| `problemas/?consumidor=&estado=&limite=` | GET | `node.queue.read` | **Los eventos apartados** (por defecto `estado=apartado`, `limite` ≤ 500): `problemas[{id, consumidor, fuente, secuencia, evento_id, tipo, intentos, intentos_reproceso, ultimo_error, estado, apartado_en, resuelto_en, resuelto_por}]`, `total`, `servidor_en`. |
| `problemas/{id}/reprocesar/` | POST | `node.queue.replay` | **Reprocesa UN evento apartado** con el `aplicar` del consumidor (idempotente, BR-008): el problema ya `reprocesado` + `servidor_en`. Deja el asiento `nodo.evento_reprocesado` y publica `nodo.evento_reprocesado.v1`. Si vuelve a fallar: 409 `reproceso_fallido` (sigue apartado, con un intento más y asiento `nodo.reproceso_fallido`). |
| `consumidores/{nombre}/reproducir/` | POST | `node.queue.replay` | Cuerpo `{fuente?}`. **La marca vuelve a cero** (de esa fuente o de todas) y el consumidor queda `reconstruyendose` hasta alcanzar la cola (BR-007): `{consumidor, fuente, marcas_reiniciadas, estado, servidor_en}`. Asiento `nodo.consumidor_reproducido`. |

Y el campo aditivo de **`GET /health/`** (público): `"nodo": {estado, motivos[], restringido, apagado_sucio_previo, version}`, leído de memoria sin tocar la base.

## 2 · Permisos (P-17)

| Permiso | Del Maestro | Administración | Técnico | Otros |
|---|---|---|---|---|
| `node.queue.replay` | sí (sección J) | sí | **sólo por escalada temporal** (PAN-241) | no |
| `node.queue.read` | extensión técnica propuesta | sí | sí | no |
| `node.health.read` | extensión técnica propuesta | sí | sí | no |

Sembrados en `acceso/dominio/plantillas.py` y, para las instalaciones que ya existen, en la migración idempotente `acceso/0019_permisos_nodo.py`.

## 3 · La interfaz para los otros módulos: `nodo.servicios`

| Función | Qué hace |
|---|---|
| `publicar(modulo, agregado_tipo, agregado_id, tipo, carga, *, actor=None, dispositivo_id=None, correlacion_id=None, version=None) -> dict` | El sobre completo con su `secuencia`. **Exige una transacción abierta** (la del hecho): fuera de ella lanza `FueraDeTransaccion`. Un `INSERT`. Actor, aparato y correlación salen del contexto de MOD-019 si no se pasan. En pruebas y desarrollo un tipo fuera del catálogo o una carga con claves prohibidas **fallan**; en producción entran marcados (`catalogado=False` / `carga_omitida=True`) con `ERROR` y asiento `nodo.evento_no_catalogado` (R-06). |
| `leer(modulo, desde, limite, tipos=None) -> (eventos, hasta)` | La fachada (P-05): la tabla antigua del módulo si está cortado (por su lector registrado) y después `m15_evento`, como un flujo continuo. Misma forma que `eventos_desde` de hoy, más los campos del sobre. |
| `ultima_secuencia(modulo=None)` | La última secuencia emitida (de un módulo o global). |
| `registrar_lector_legado(modulo, lector)` · `cortar(modulo, ultima_legada, *, actor, version_contrato, asentar=True)` · `corte_de(modulo)` | El corte de un módulo (Fase 3): una transacción con la fila de `m15_corte` y el salto del contador; de una sola vía. El lector se registra una vez por proceso (`apps.ready`) y sobrevive a `contenedor.reiniciar()` (D-27). Con `asentar=False` (lo que usan las migraciones de datos de los módulos, D-24) no deja asiento ni evento técnico. Desde la Fase 3, `agregado_id` admite hasta 256 caracteres (D-26). |
| `nodo.pruebas` (sólo `*/tests/`) | `cola(modulo)` (lo publicado por un módulo con el vocabulario de su cola antigua y la API de un manager: `filter`, `get`, `count`, `values_list`…, más `create` para publicar en su nombre), `espiar(adaptador)` (registra las llamadas a `publicar`), `sembrar_historia(modelo_legado, modulo, eventos, creado_en)` y `recortar` (una instalación con historia), `como_consumidor(leer, marca, tipos)` (lee por lotes hasta vaciar), `nodo_limpio()` (estado vivo en cero). Ningún caso de uso lo importa. |
| `registrar_consumidor(nombre, modulo, fuentes, tipos=(), *, version_contrato=1, limite_rezago=None, aplicar=None)` | Registra (o actualiza) un consumidor, deja su marca en cero si es nuevo (BR-007) y guarda su `aplicar` en memoria. Un contrato incompatible (INV-006/007) se rechaza con `ContratoIncompatible` y asiento. |
| `desregistrar_consumidor(nombre)` | BR-018: deja de bloquear la purga; sus marcas se conservan. |
| `aplicar_lote(consumidor, fuente, aplicar=None, limite=None) -> dict` · `aplicar_hasta_vaciar(...)` | El ayudante único (P-06/P-07): lee sin bloqueo, bloquea y relee, aísla cada evento en un savepoint, avanza la marca en la **misma** transacción, reintenta con espera creciente (1 s, 2, 4… tope 60 s, ± 20 %) y aparta al quinto fallo. Devuelve `{leidos, procesados, fallidos[], marca_anterior, marca, pendientes, estado, apartado?, esperando?, proximo_en?}`. |
| `marca(consumidor, fuente)` · `reproducir(consumidor, fuente=None, *, actor)` · `reprocesar(problema_id, actor)` · `cola(actor=None)` · `problemas(actor, ...)` | Lo mismo que la API. |
| `ahora_ms()` | El reloj del nodo: `max(reloj del sistema, marca alta)` (P-13). |
| `nuevo_id()` | UUID4 (Q-38 queda para Q-N2). |
| `estado(actor=None)` · `estado_resumido()` | El estado evaluado ahora · lo que lee `/health/` (nunca lanza, nunca escribe). |
| `purgar(actor=None, *, forzar=False)` | La purga: apagada (`AVACOM_NODO_PURGA=0`); con el respaldo ausente nunca borra y dice por qué. |
| `arrancar()` · `parar()` | Lo que `asgi.py` llama al levantar el proceso (anclas, fila de arranque, `servicios_iniciados`) y al cerrarlo. Nunca lanzan. |

## 4 · Eventos `nodo.*`

Del Maestro (`.v1`): `servicios_iniciados` (al arrancar), `marca_lectura_avanzada` (por lote y consumidor), `entrega_reintentada`, `evento_apartado`, `evento_reprocesado`, `recuperacion_completada` (con `incidente`, `inicio`, `fin`, `ultima_secuencia_valida`, `eventos_reprocesados`, `marcas_ajustadas`: hoy sólo por restauración detectada), `salud_evaluada` (sólo al cambiar), `ingreso_limitado` (reservado: el tope vive en el aula) y `evento_publicado` (reservado, no se emite: D-8). **Extensiones**, marcadas: `nodo.reloj_retrocedido.v1` (reservado para la Fase 6), `nodo.modo_restringido.v1`, `nodo.consumidor_rezagado.v1`, `nodo.modulo_cortado.v1`. Todos en la cola, clase *técnico* o *sincronización*, módulo `nodo`, y ninguno provoca otro.

## 5 · Variables (`backend/README.md`)

`AVACOM_NODO_DIR` (anclas, sólo desarrollo), `AVACOM_NODO_ESTRICTO`, `AVACOM_NODO_PURGA`, `AVACOM_NODO_EVENTOS_TECNICOS`, `AVACOM_NODO_LOTE`, `AVACOM_NODO_MAX_INTENTOS`, `AVACOM_NODO_ESPERA_BASE_MS`, `AVACOM_NODO_ESPERA_TOPE_MS`, `AVACOM_NODO_REZAGO_LIMITE`, `AVACOM_NODO_RETENCION_MIN_DIAS`, `AVACOM_NODO_CICLO_MESES`, `AVACOM_NODO_DISCO_MIN_GB`, `AVACOM_NODO_DISCO_MIN_PCT`, `AVACOM_NODO_WAL_MAX_MB`.
