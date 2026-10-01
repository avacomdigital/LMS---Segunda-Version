# 03 · Audit (MOD-019) · Backend: funciones y endpoints `/api/auditoria/` y `/api/logs/`

| Campo | Valor |
|---|---|
| Estado | **Construido** (2026-09-30). App `backend/audit/` con arquitectura hexagonal (`dominio/` y `aplicacion/` sin Django; `infraestructura/` e `interfaces/` son los adaptadores). 71 pruebas en `audit/tests/`; la suite completa del backend está en verde (651). |
| Modelo | [modelado_datos.md](modelado_datos.md). Pantallas y clientes: [frontend.md](frontend.md). |
| Contrato de degradación | El de todo el backend: `{detail, codigo, ...extra}`. 401 `sesion_requerida` · 403 `permiso_denegado` (con asiento de denegación) · 403 `autorizacion_requerida` · 404 `no_encontrado` · 409 `cadena_con_salto` / `tramo_no_verificado` · 422 `accion_desconocida` · 400 `datos_invalidos` · 405 `bitacora_inmutable` en todo PUT/PATCH/DELETE · 503 `bitacora_no_disponible` (el hecho no ocurre). |
| Permisos | `audit.read` (Administrador) · `audit.export` (Administrador, **más** autorización de salida vigente) · `diagnostics.read` (Técnico y Administrador). Toda ruta exige sesión de usuario; `AVACOM_LMS_EXIGIR_SESION` no la relaja. |

---

## 1 · Estructura

```
backend/audit/
  contexto.py          contexto de la operación en contextvars (corr, usuario, rol, aparato, origen, caso)
  logging_setup.py     LOGGING del backend: JSON Lines por canal, carpeta por entorno, saneamiento
  middleware.py        corr por petición, X-Avacom-Dispositivo validado, línea por petición, asiento por cada 403
  pruebas.py           TEST_RUNNER (caso=<id del test>, triggers alrededor del flush) y mixin LogsDePrueba
  servicios.py         fachada para los demás módulos: anexar(actor, accion, tabla, objeto_id, anterior, nuevo, **extra)
  dominio/             huella.py · catalogos.py · asiento.py · tramo.py · errores.py        (sin Django)
  aplicacion/          anexar.py · verificar.py · rotar.py · estado.py · consultar.py · exportar.py · tecnico.py · logs.py
  infraestructura/     triggers.py · migracion.py · firma.py · archivos.py · eventos.py · archivo_logs.py · autorizacion.py · verificador.py
  interfaces/          urls.py · urls_logs.py · views.py · serializers.py
  migrations/0001_initial.py
backend/tools/ver_logs.py     backend/tools/romper_cadena.py
```

---

## 2 · Cómo se escribe un asiento (anexar)

```
caso de uso de cualquier módulo ── uow.auditoria.registrar(actor, accion, tabla, objeto_id, anterior, nuevo, motivo=…, resultado=…)
   └─ audit.servicios.anexar()              resuelve la acción contra el catálogo (exige_motivo, modulo); actor_tipo/usuario_id del contexto
        └─ aplicacion.anexar.anexar()       BEGIN IMMEDIATE: tramo abierto (select_for_update) → secuencia = hasta+1 → huella → INSERT → avanza la cabeza
              ├─ sin tramo abierto: abre uno; si la cadena está vacía, génesis `auditoria.bitacora_abierta`
              ├─ línea INFO en backend-auditoria.log (secuencia, acción, resultado, huella; nunca valores)
              └─ DatabaseError → línea ERROR (canal escritura) + BitacoraNoDisponible → el caso de uso revierte entero
```

Quién actúa, desde dónde y con qué correlación **no lo pasa el módulo**: lo toma del contexto (`audit.contexto`), que fijan:

| Quién | Cuándo | Qué deja en el contexto |
|---|---|---|
| `CorrelacionMiddleware` | Cada petición HTTP | `corr` (de `X-Avacom-Correlacion` si cumple `^[A-Za-z0-9._:-]{8,64}$`, si no uno nuevo), `dispositivo_id` validado contra `m09_dispositivo` (activo y no bloqueado; si no, NULL y línea WARNING), `origen = api` |
| `AutenticacionJwt` (acceso) | Al autenticar, antes de la vista | `usuario_id`, `rol_codigo`, `sesion_id`, `dispositivo_id` del Principal si no vino por cabecera |
| Consumidor WebSocket (aula) | Al conectar y en cada mensaje | `origen = ws`, persona del token, aparato (`X-Avacom-Dispositivo` del handshake o `?dispositivo=`), `corr` por conexión |
| Verificador / programador | Cada tick | `origen = sistema`, `corr` nuevo |
| Corredor de pruebas | Cada test | `caso = <id del test>`, `origen = prueba` |

**Resolución del actor** (`servicios._actor`): `''`/`sistema` → `sistema`; `instalador` → `instalador`; `cliente` → `declarado`; con sesión en el contexto → `usuario` (el id nombrado por el módulo); sin sesión → `declarado`.

**Denegaciones (019-08).** El middleware convierte todo 403 en un asiento `acceso.denegado` (o `aula.denegado` bajo `/api/aula/`) con `roles_activos`, `codigo`, `permiso_solicitado`, `metodo` y `ruta`, en su propia transacción, después de la respuesta.

**Intentos de alterar (AC-081).** El manager de `Bitacora` rechaza `update/delete/bulk_update/bulk_create/update_or_create`, `save()` de una fila existente y `delete()` con `BitacoraInmutable`, y asienta `auditoria.alteracion_intentada` (resultado `denegado`, operación y objeto pretendido). El SQL directo lo aborta el trigger (`bitacora_inmutable`).

---

## 3 · Casos de uso

| Caso de uso | Archivo | Qué hace |
|---|---|---|
| `verificar_cadena(todos=False, bloque=5000)` | `aplicacion/verificar.py` | Recorre cada tramo pendiente (o todos) recalculando huellas desde `verificado_hasta`; detecta `huella_discordante`, `secuencia_con_hueco`, `secuencia_repetida`, `huella_previa_no_enlaza`, `cabeza_discordante`, `triggers_ausentes`. Resultado: tramo `verificada` + asiento `auditoria.cadena_verificada` + evento; o `con_salto` (+ `salto_en_secuencia`, causa) + asiento `auditoria.salto_detectado` (resultado `fallido`) + evento de prioridad alta + línea ERROR. Precondición FUN-198: ≥ 2 asientos (`estado = insuficiente`) |
| `rotar(motivo)` · `rotar_si_supera()` | `aplicacion/rotar.py` | Verifica el tramo abierto (con salto no rota: 409); escribe `<logs>\auditoria\tramo-<desde>-<hasta>.jsonl` (manifiesto firmado + asientos); marca `rotada` (`abierta = 0`, `rotado_en`, `archivo`, `firma`); abre el siguiente con `huella_previa = huella_cierre`; asienta `auditoria.bitacora_rotada` (primer asiento del tramo nuevo) + evento. Umbral: `AVACOM_LMS_AUDITORIA_UMBRAL_MB` sobre el tamaño estimado |
| `estado()` | `aplicacion/estado.py` | Cabeza (`secuencia`, huella abreviada), total de asientos, tramo abierto, último verificado, `salto_detectado` y su causa, `triggers_ok`, tamaño frente al umbral, versión del catálogo, cadencia |
| `listar(principal, filtros, limite, antes, despues, enmascarar)` | `aplicacion/consultar.py` | Filtros de §4; cursor por secuencia (`antes=` hacia atrás, orden desc por defecto; `despues=` hacia adelante); `limite` ≤ 200; `total`; rótulos de los actores (alias de `m01_usuario`); **cada consulta asienta `auditoria.consulta_realizada`** con los filtros. Los asientos de acciones `sensible` llegan con `valor_anterior/nuevo = {"enmascarado": true}` salvo escalada vigente de `audit.read` (BR-131) |
| `detalle(principal, id_o_secuencia, enmascarar)` | ídem | Huella y `huella_previa` completas. Si es sensible y se ve sin máscara, asienta `acceso.dato_personal.consultado` |
| `exportar(principal, autorizacion, tramo_id | desde,hasta, motivo_codigo, motivo_detalle)` | `aplicacion/exportar.py` | Exige escalada vigente de `audit.export` (si no: asiento `auditoria.exportacion_denegada` y 403 **sin archivo**); rango existente y verificado sin salto (verifica al vuelo lo que falte; 409 si hay salto); escribe `<logs>\auditoria\exportaciones\exportacion-<id>.jsonl` (manifiesto con `exportacion_id`, firma HMAC, asientos); asienta `auditoria.tramo_exportado` (motivo obligatorio de lista) + evento; **consume la escalada** (`acceso.escalada.consumida`). Devuelve MSG-054 y la ruta de descarga |
| `accesos(principal, desde, hasta, limite, antes)` | `aplicacion/tecnico.py` | Asientos de los usuarios con rol TECHNICIAN (rol principal o asignación vigente), denegaciones, `sin_acceso_a_datos_personales` (no hay `acceso.dato_personal.consultado` ni acción sensible con `ok` en el periodo), `cadena_verificada`, `salto_detectado`. También asienta la consulta |
| `recibir_de_clientes(dispositivo_id, app, version, renglones)` | `aplicacion/logs.py` | Escribe cada renglón en `backend-clientes.log` con el `dispositivo_id` **autenticado** (nunca el declarado); tope por entrega (`AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES`, 200) y por minuto por equipo (`…_MAX_POR_MINUTO`, 1000). No toca la bitácora |
| `leer(filtros, ultimos)` | ídem | Últimas líneas de los logs del nodo, saneadas otra vez al salir, con resumen happy/sad/bad y niveles; una línea WARNING+ que está en su canal y en `errores` se cuenta una vez |

**Temporizador** (`infraestructura/verificador.py`): hilo del proceso ASGI (lo arranca `avacom_lms/asgi.py`), primer tick al minuto y después cada `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S` (3600; `0` lo desactiva): verifica y rota si supera el umbral. Un tick que falla se registra y el siguiente reintenta.

**Firma** (`infraestructura/firma.py`): HMAC-SHA256 del manifiesto canónico con una clave derivada de `SECRET_KEY` (`AVACOM_LMS_CLAVE_AUDITORIA` en base64 la sustituye). Manifiesto: `version_formato, tramo_id, desde, hasta, huella_inicial, huella_cierre, total, exportado_por, exportado_en, alcance, motivo (+ exportacion_id)`. La firma prueba «lo emitió este nodo y no fue modificado»; la verificación por terceros queda como Q-2.

**Autorización** (`infraestructura/autorizacion.py`): evalúa `audit.*` y `diagnostics.read` con la política de MOD-001 (`Base.contexto` + `alcance_concedido`, reglas transversales). `tiene_escalada(principal, permiso)` mira las concesiones adicionales vigentes de `m01_usuario_permiso` (aunque el rol ya tenga el permiso: la escalada es la autorización explícita, con motivo y caducidad). `consumir_escalada` la revoca y asienta `acceso.escalada.consumida`.

---

## 4 · Endpoints

Todos exigen sesión (`Authorization: Bearer`). Cabeceras que el cliente debe mandar en **toda** petición al nodo: `X-Avacom-Dispositivo: <m09_dispositivo.id>` (019-01) y `X-Avacom-Correlacion` (opcional; el nodo la devuelve siempre).

### 4.1 `/api/auditoria/`

| Método y ruta | Permiso | Entrada | Salida |
|---|---|---|---|
| `GET asientos/` | `audit.read` | Query: `actor`, `actor_tipo`, `desde`/`hasta` (ms), `modulo`, `accion` (admite `aula.control.*`), `resultado`, `objeto_tabla`, `objeto_id`, `dispositivo`, `correlacion`, `texto` (sobre `motivo`), `tramo`, `sensible`, `limite` (≤ 200), `antes` **o** `despues` (cursor de secuencia) | `{asientos: [Asiento…], siguiente, orden: desc|asc, limite, total, enmascarado}`. `Asiento`: `id, secuencia, ocurrido_en, actor{tipo, usuario_id, rotulo}, roles_activos, modulo, modulo_etiqueta, accion, etiqueta, resultado, objeto{tabla, id}, motivo, origen, dispositivo_id, correlacion_id, evento_id, tramo_id, sensible, enmascarado, huella (abreviada), valor_anterior, valor_nuevo` |
| `GET asientos/{id}/` | `audit.read` | `id` o `secuencia` | El asiento con `huella` y `huella_previa` completas |
| `GET catalogo/` | `audit.read` | — | `{version, modulos[{clave, etiqueta}], acciones[{clave, modulo, etiqueta, exige_motivo, sensible, evento_origen}], resultados, origenes}` |
| `GET tramos/` | `audit.read` | — | `{tramos: [{id, desde, hasta, estado, abierta, huella_cierre, verificado_en, verificado_hasta, salto_en, salto_causa, exportado_en, archivo, rotado_en, creado_en, asientos}]}` |
| `POST verificar/` | `audit.read` | `{todos?: bool}` | `{estado: verificada|con_salto|insuficiente, verificados, salto_en, causa, tramos[]}` |
| `GET estado/` | `audit.read` | — | `{cabeza{secuencia, huella}, total_asientos, tramo_activo, ultimo_verificado_en, salto_detectado, salto{tramo_id, secuencia, causa}, triggers_ok, tamano_bytes, umbral_bytes, porcentaje_umbral, tramos, version_catalogo, verificar_cada_s}` |
| `POST exportar/` | `audit.export` + autorización de salida | `{tramo_id}` **o** `{desde, hasta}`, `motivo_codigo` (`inspeccion_interna` · `auditoria_externa` · `requerimiento_legal` · `respaldo_externo` · `soporte_avacom`), `motivo_detalle?`. No mandar `desde`/`hasta` nulos | 201 `{exportacion_id, alcance, desde, hasta, total, archivo, firma, exportado_en, secuencia_asiento, mensaje (MSG-054), descarga}`. 403 `autorizacion_requerida` (asentado, sin archivo) · 409 `cadena_con_salto` / `tramo_no_verificado` |
| `GET exportaciones/` | `audit.export` | — | `{exportaciones[{exportacion_id, exportado_en, exportado_por, alcance, desde, hasta, total, archivo, motivo, disponible, descarga}], motivos[{codigo, etiqueta}], autorizacion_vigente}` |
| `GET exportaciones/{id}/descargar/` | `audit.export` | — | El archivo `.jsonl` (`application/x-ndjson`, adjunto). Primera línea `{manifiesto, firma}`, después un asiento por línea |
| `GET tecnico/accesos/` | `audit.read` | `desde`, `hasta`, `limite`, `antes` | `{tecnicos[{usuario_id, rotulo}], asientos[], siguiente, total, denegaciones, sin_acceso_a_datos_personales, cadena_verificada, salto_detectado, periodo}` |

`PUT`, `PATCH` y `DELETE` responden 405 `bitacora_inmutable` en todas las rutas (una prueba las recorre).

### 4.2 `/api/logs/`

| Método y ruta | Quién | Entrada | Salida |
|---|---|---|---|
| `GET /api/logs/` | `diagnostics.read` (Técnico y Administrador) | `canal`, `nivel`, `app` (`backend|ops|student`), `ruta`, `desde` (ISO), `corr`, `dispositivo`, `evento`, `archivo` (`backend-app|backend-errores|backend-auditoria|backend-clientes|instalacion`), `ultimos` (≤ 1000) | `{lineas[{ts, nivel, canal, app, modulo, evento, ruta, caso, dispositivo_id, usuario_id, corr, mensaje, detalle, traza, archivo}], total, resumen{happy, sad, bad, niveles}, archivos[]}`. Sin datos personales |
| `POST /api/logs/clientes/` | Equipo registrado y activo (`X-Avacom-Dispositivo` o `dispositivo_id` en el cuerpo) **o** sesión | `{app: ops|student, version_app, dispositivo_id?, renglones[{ts, nivel (DEBUG…CRITICAL), canal, app, modulo?, evento?, ruta?, mensaje (≤ 2000), detalle?, traza? (≤ 8000), corr?, version_app?}]}` | 202 `{recibidos, escritos, descartados, dispositivo_id}`. Con sesión y sin equipo conocido se atribuye a `sesion:<usuario_id>`. 403 sin equipo ni sesión; 403 con equipo bloqueado o retirado |

---

## 5 · Catálogo de acciones (resumen; la lista completa está en `audit/dominio/catalogos.py`)

| Módulo | Vigentes (ya en el código) | Nuevas en MOD-019 |
|---|---|---|
| `acceso` | `identidad.usuario.creado/actualizado/vinculado`, `identidad.usuarios.importados`, `identidad.rol.asignado/revocado/creado`, `identidad.sesion.abierta/cerrada`, `identidad.sesiones.revocadas`, `identidad.credencial.restablecida/cambiada`, `identidad.cuenta.bloqueada/desbloqueada`, `identidad.escalada.concedida/revocada`, `identidad.acceso_temporal.otorgado/canjeado/revocado`, `identidad.politica.configurada`, `identidad.grupo.*`, `identidad.instalacion` | `acceso.denegado`, `acceso.dato_personal.consultado` (sensible), `acceso.escalada.consumida`, `acceso.escalada.vencida` |
| `aula` | `aula.sesion.*`, `aula.participante.*`, `aula.selector.declarado`, `aula.distribucion.cerrada/estudio`, `aula.resultados.mostrados`, `aula.codigo.rotado`, `aula.proyeccion.iniciada/terminada`, `aula.ayuda.solicitada/atendida/retirada`, familias `aula.control.*`, `aula.distribucion.*`, `aula.envio.*` | `aula.aviso.enviado` (alcance y largo, sin texto), `aula.presencia.perdida/recuperada` (sólo la transición: declarada · socket cerrado · latido vencido · ausencia prolongada), `aula.proyeccion.terminada` con `duracion_seg`, `aula.nivel.excepcion` (sin punto de llamada aún), `aula.denegado` |
| `dispositivos` | `dispositivos.registrado/actualizado/bloqueado/desbloqueado/asignado/liberado` | `dispositivos.borrado_remoto` (motivo), `dispositivos.limpieza_registrada` |
| `estudio` | `estudio.asignacion.*`, `estudio.leccion.completada`, `estudio.envio.*` | `estudio.paquete.descargado/denegado`, `estudio.entrega.integrada` |
| `evaluacion` | — | `evaluacion.iniciada/enviada/anulada`, `calificacion.modificada` (motivo, sensible), `calificacion.reabierta`, `calificacion.correccion_posterior_cierre` — el punto de llamada espera a MOD-010/011 |
| `expediente` | `inscripcion.creada/retirada`, `progreso.actualizado`, `apertura.registrada`, `intento.iniciado/finalizado`, `disponibilidad.*`, `administracion.rechazada` | — |
| `auditoria` | — | `auditoria.bitacora_abierta`, `cadena_migrada`, `cadena_verificada`, `salto_detectado`, `bitacora_rotada`, `tramo_exportado` (motivo), `alteracion_intentada`, `consulta_realizada`, `exportacion_denegada`, `violacion_inv003`, `restauracion_registrada`, `accion_desconocida` |
| `instalacion` | — | `instalacion.organizacion_creada/licencia_activada/migracion_aplicada` |

---

## 6 · Pruebas (§4.5 de la introducción)

| Prueba | Archivo | Ruta |
|---|---|---|
| TST-071 · 5 acciones sensibles con actor, fecha, valor anterior y motivo | `test_bitacora.py` | happy |
| AC-054 · calificación 72→80 con motivo; sin motivo no se anexa; detalle enmascarado sin escalada y visible con ella | `test_bitacora.py`, `test_api.py` | happy / sad |
| AC-081 · editar/borrar: ORM, QuerySet, `bulk_*`, SQL directo (trigger), verbos HTTP → denegado, asiento intacto y asiento nuevo | `test_bitacora.py`, `test_api.py` | sad |
| TST-072 · exportar sin autorización: 403, sin archivo, `exportacion_denegada` | `test_exportar.py` | sad |
| AC-003 / VER-01 · técnico denegado con asiento; `tecnico/accesos/` e indicador | `test_logs_api.py` | sad |
| Cadena íntegra · romper la cadena (alterar, borrar, cabeza, triggers ausentes) · verificación por bloques | `test_cadena.py` | happy / bad |
| Falla la escritura de la bitácora → rollback, traza en `backend-errores.log`, cero asientos parciales | `test_bitacora.py` | bad |
| Rotación por tamaño · archivo firmado · tramo nuevo enlazado · filas intactas | `test_cadena.py` | happy |
| Privacidad: claves sembradas no aparecen en ningún archivo; logs de clientes redactados | `test_logs.py`, `test_logs_api.py` | sad |
| Carpeta por entorno · correlación por petición · `ruta` por estado · helper `LogsDePrueba` | `test_logs.py` | — |
| Cobertura del aula: aviso, transiciones de presencia (nunca el latido), duración de proyección | `test_cobertura_aula.py` | happy |
| Puertos de los cuatro módulos y el expediente en la misma cadena; contexto (aparato, origen, corr) | `test_bitacora.py` | happy |

No cubiertas: concurrencia con varios hilos (base en memoria; el aislamiento lo da `BEGIN IMMEDIATE` + `UNIQUE(secuencia)`) y restauración de respaldo.

---

## 7 · Variables de entorno

| Variable | Para qué |
|---|---|
| `AVACOM_LMS_DIR_LOGS` | Carpeta de los logs (manda sobre la elección por entorno) |
| `AVACOM_LMS_ENTORNO` | `instalado` · `desarrollo` · `pruebas` |
| `AVACOM_LMS_NIVEL_LOG` | Nivel mínimo de `backend-app.log` (`INFO`) |
| `AVACOM_LMS_CONSERVAR_LOGS` | `1` conserva la carpeta de una corrida de pruebas que pasó |
| `AVACOM_LMS_AUDITORIA_UMBRAL_MB` | Umbral de rotación (100) |
| `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S` | Cadencia del verificador (3600; `0` desactiva) |
| `AVACOM_LMS_AUDITORIA_ESTRICTA` | `1`: una acción fuera del catálogo falla (por defecto sólo en pruebas) |
| `AVACOM_LMS_CLAVE_AUDITORIA` | Clave HMAC (base64) de firmas; si falta se deriva de `SECRET_KEY` |
| `AVACOM_LMS_LOGS_CLIENTES_MAX_RENGLONES` · `_MAX_POR_MINUTO` | Topes de `POST /api/logs/clientes/` (200 · 1000) |

Herramientas: `python tools/ver_logs.py --ultimos 50 --nivel ERROR --canal escritura` (`--caso`, `--ruta`, `--corr`, `--app`, `--archivo`) · `python tools/romper_cadena.py --secuencia 7 [--borrar | --quitar-triggers]` (sólo pruebas).
