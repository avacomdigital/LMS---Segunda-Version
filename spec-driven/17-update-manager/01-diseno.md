# 17 · Update Manager (MOD-017) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **Fases 0 a 5 implementadas** (2026-10-21), **sin commit**: el núcleo y el backend (`backend/actualizacion/`, fases 0 a 2), los clientes (Core, página Actualizaciones de OPS y el texto de Student, fase 3), la aplicación real en el `Host`, el emisor y el ensayo (fase 4) y la documentación de operación y emisión (fase 5). Lo que sigue **sin comprobarse** (servicio real con elevación, USB física, antivirus, 30 ensayos, ceremonia de llaves) está en [03-pruebas.md](03-pruebas.md) §5. El prompt está en [00-introduccion.md](00-introduccion.md). |
| Módulo | **MOD-017 · Update Manager** (DOM-009 · Plataforma y Continuidad). CAP-105, CAP-106, CAP-107 y CAP-109 en lo que decide el backend; CAP-108 como ventana única (C-2). FUN-179 a FUN-187; los nueve eventos `actualizacion.*.v1`; permisos `update.apply`, `update.package.import`, `update.schedule` y la extensión `update.read`. |
| Contrato | [02-api.md](02-api.md) — rutas, cuerpos y errores **reales capturados**, el contrato de `orden.json` / `resultado.json` con el `Host` y la interfaz `actualizacion.servicios`. |
| Pruebas | [03-pruebas.md](03-pruebas.md) — qué se probó con qué resultado y **qué no se pudo comprobar**. |
| Se apoya en | **MOD-015** (la cola única `m15_evento` y el reloj del nodo: **ya existe**, se consume), MOD-019 (bitácora encadenada), MOD-001 (permisos y escalada), MOD-007 (¿hay clase?, por su `servicios.py`). MOD-016 y la parte de MOD-018 que necesita **no existen**: puertos con adaptadores provisionales (§10). No lee ni escribe ninguna tabla ajena (R-03, INV-023). |

> **Principio (Documento Maestro):** *aplica actualizaciones sin internet y sin perder lo propio. Verifica firma y compatibilidad de contratos antes de tocar nada, toma un respaldo previo, instala por módulo en lugar de todo a la vez, y revierte de forma automática si algo sale mal.* Su contribución más valiosa es lo que impide: un paquete sin firma o alterado, una degradación a una versión vieja, una aplicación con una clase en curso, perder la versión a la que volver antes de 14 días, y un aula con contratos incompatibles (INV-007). Y, por encima de todo: **nunca se detiene una clase** (R-01).

---

## 1 · Qué entra en este tramo y qué no

| Entra | Dónde |
|---|---|
| El formato `.avupd`: contenedor ZIP **canónico y sin comprimir**, `manifiesto.json` + `manifiesto.firma` (Ed25519), verificación completa en memoria y sin escribir un byte (CAP-109, BR-013, P-02) | `dominio/contenedor.py` · `firma.py` · `manifiesto.py` · `paquete.py` · `rutas.py` |
| Rutas seguras y el límite R-07: sólo archivos de las apps que el paquete declara (más `avacom_lms/modulos.json`), nunca `biblioteca/`, el `Host`, `backend.env` ni nada fuera de `backend/` | `dominio/rutas.py` |
| La máquina de estados (los seis del Maestro + tres internos) como función pura sobre un historial de **sólo inserción** (P-05) | `dominio/estados.py` · `models.Historial` · `migrations/0002_triggers.py` |
| Compatibilidad y serie (P-04, P-16, INV-007): versión mínima, contrato de la biblioteca, contratos entre módulos (rangos que cada consumidor acepta), serie monótona por módulo, versión de datos, espacio, licencia | `dominio/compatibilidad.py` · `dominio/registro.py` · `avacom_lms/modulos.json` |
| La ventana única (P-08, C-2) y la regla de apertura: dentro de la ventana, cero clases, lejos de la próxima clase | `dominio/ventana.py` · `aplicacion/vigilante.py` |
| La **orden** al `Host` y la lectura de su **resultado** (P-06, P-07, FUN-187): `orden.json` con los pasos y checkpoints, `resultado.json` validado y registrado en el historial con sus eventos | `dominio/orden.py` · `aplicacion/vigilante.py` · `infraestructura/almacen.py` |
| Importar desde unidades extraíbles y la carpeta de entrada, sin rutas libres (CAP-106, P-11) | `infraestructura/fuentes.py` |
| El 503 `actualizacion_en_curso` **sólo** en el inicio de clases mientras hay una orden (R-01, R-02) | `interfaces/middleware.py` |
| API `/api/actualizacion/`, permisos `update.*` (migración `acceso/0020`), acciones de bitácora, los 9 + 2 eventos en el catálogo de la cola única, `/health/` aditivo, variables `AVACOM_ACTUALIZACION_*` | `interfaces/` · `acceso/dominio/plantillas.py` · `audit/dominio/catalogos.py` · `nodo/dominio/catalogo_datos.py` · `expediente/views.py` · `settings.py` · `README.md` |
| El emisor de **pruebas** (llaves de desarrollo derivadas de una semilla pública) y las llaves públicas de publicación (`claves/produccion.json` **vacío** hasta la ceremonia) | `tests/emisor.py` · `claves/` |

| NO entra (queda preparado y dicho) — **las filas de Fase 3 y 4 se construyeron después: ver §16** | Por qué |
|---|---|
| **Aplicar de verdad**: copiar a `backend/`, migrar, verificar, revertir, la instantánea de 14 días, el verbo del `Host`, el bloque E del ensayo (TST-061) | Fase 4. Sólo SYSTEM escribe en `Program Files` (P-06): el backend decide y deja la orden; el `Host` aplica con el servicio parado. Hoy nadie lee `orden.json`: un paquete `aplicando` se queda ahí hasta que exista el `Host` (o diez minutos sin orden en disco, §6). |
| La pantalla **Actualizaciones** de OPS, `Core/Actualizacion/` y el texto de Student | Fase 3. El contrato ya está capturado para los clientes de C# (`test_capturar_contrato.py`). |
| El emisor interno `tools/actualizacion/` y la exclusión de `actualizacion\tests` y `claves\desarrollo.json` en `Build-Installer.ps1` | Fase 4 (P-03). `test_arquitectura` lo deja marcado como omitido mientras tanto; el patrón `desarrollo.json` ya cubre la llave. |
| El canal por internet (detección y descarga) | P-18: en MVP sólo la variable `AVACOM_ACTUALIZACION_CANAL`, apagada de fábrica. Aplicar nunca depende de la red. |
| Subir `installer/version.json` y reconstruir `installer/latest` | El tramo es sólo backend por decisión del usuario; además otra sesión está subiendo esa versión en este momento (MOD-015, Fase 3). Se sube con la Fase 4. |
| Validar la licencia (MOD-018) y el respaldo con punto de recuperación (MOD-016) | Puertos provisionales (§10). |

## 2 · Arquitectura

Hexagonal, igual que `licenciamiento/`, `nodo/`, `gradebook/` y `reporting/`:

```
backend/actualizacion/
├── models.py                   m17_paquete · m17_historial (§9)
├── servicios.py                la interfaz para los OTROS módulos: en_curso() · estado_resumido() · tick()
├── dominio/                    puro, sin Django: catalogos · errores · version · firma · contenedor · rutas · manifiesto · paquete · estados · registro · compatibilidad · ventana · orden
├── aplicacion/                 casos de uso, sin Django: puertos · base · acciones (importar, programar, desprogramar, aplicar, revertir, consultas) · vigilante (Tick)
├── infraestructura/            adaptadores: contenedor (composition root) · repositorios (m17_*, cola única, bitácora) · unidad_trabajo · autorizacion · almacen (la carpeta de
│                               actualizaciones) · fuentes (unidades y entrada) · claves · registro_modulos (modulos.json + migraciones aplicadas) · provisionales (reloj, aula,
│                               licencia, respaldo, memoria) · vigilante (el hilo)
├── interfaces/                 urls · views (`/api/actualizacion/`) · middleware (el 503)
├── claves/                     produccion.json (vacío) · desarrollo.json (upd-dev-1, upd-dev-2; sólo fuera de producción)
├── migrations/                 0001_initial · 0002_triggers
└── tests/                      emisor (de pruebas) · base · test_formato · test_mutaciones · test_estados · test_compatibilidad · test_arquitectura · test_api · test_capturar_contrato
```

## 3 · El paquete `.avupd` (P-02, P-03)

- **Contenedor.** Un ZIP leído con un lector propio y estricto: EOCD en los últimos 22 bytes sin comentario, directorio central pegado a las entradas, entradas contiguas en el orden del directorio y empezando en el byte 0, sin ZIP64, cifrado, descriptores, extras ni comentarios, sin directorios ni enlaces, nombres ASCII sin repetir. Y **canónico**: todo lo que no se verifica contra el manifiesto (versión 2.0, fecha fija, atributos a cero) tiene un valor fijo que el lector exige, y las entradas van **sin comprimir** (D-4). Así cada byte del archivo está determinado por el contenido, no hay descompresión (la bomba de descompresión no existe por construcción) y cualquier `zipfile` o 7-Zip lo abre para mirarlo.
- **Entradas.** `manifiesto.json`, `manifiesto.firma` y `archivos/<ruta>` por cada archivo declarado. Una de más es `archivo_no_declarado`; una de menos, `archivo_faltante`.
- **Firma.** `manifiesto.firma` = magic `AVUP` · versión (u16) · largo del kid (u8) · kid · firma Ed25519 (64 bytes). La firma cubre la cabecera **y los bytes exactos** de `manifiesto.json` (D-5): nadie degrada un paquete cambiando el kid o la versión de la firma. El algoritmo está fijado (sin `alg`); el `kid` elige entre las llaves públicas de **publicación** del nodo, distintas de las de licencias (Q-U8).
- **Orden de verificación** (`paquete.verificar`): tamaño → contenedor → firma presente y con forma → `kid` conocido → **firma válida** → manifiesto (formato, etiquetas críticas, campos, rutas) → entradas contra el manifiesto (tamaño del ZIP = `bytes`) → SHA-256 de cada archivo. Un paquete que no pasa cualquiera de los pasos se rechaza con **motivo** (`MENSAJES_DE_MOTIVO`, contrato con OPS) y **sin escribir un byte** (TST-048, TST-062).
- **Manifiesto** (`formato: 1`): `paquete_id` (UUID), `nombre`, `producto`, `version_producto`, `version_minima`, `emitido_en`, `criticas`, `nota`; `modulos[]` con `nombre`, `version`, `version_datos`, `version_contrato`, `serie`, `cambia_contrato`, `requiere{módulo: contrato mínimo}` y `migraciones[{nombre, reverso}]` (BR-015: **toda** migración declara su reverso, o `zero`); `archivos[{ruta, bytes, sha256}]`; `requisitos{contrato_biblioteca, cliente_minimo, espacio_bytes, contrato_red}`. El ejemplo completo está en `02-api.md`.
- **Rutas** (`rutas.py`, D-2): relativas con `/`, sin `..`, sin letra de unidad ni `\`, componentes `[A-Za-z0-9_][A-Za-z0-9._-]*` sin nombres reservados de Windows ni `__pycache__`, extensiones de código o datos (`.py .json .txt .md .html .css .js .sql .csv .ini .cfg`), y **dentro de las apps que el paquete declara** (más `avacom_lms/modulos.json`). `biblioteca/` es intocable (R-12).

## 4 · Estados y el historial (P-05)

```
(sin filas) ─recibido→ recibido ─verificado→ verificado ─programado→ programado ─aplicando→ aplicando ─aplicado→ aplicado ─archivado (14 días)→ archivado
                                 │ incompatible ↔ verificado        │ desprogramado · ventana_vencida → verificado        │ revertido → revertido
                                 └──────────── aplicando ───────────┘ bloqueada (no cambia el estado)                      │ reversion_fallida → reversion_fallida
                                                                                                                            └ aplazada → el estado anterior
aplicado ─aplicando (revertir, < 14 días)→ aplicando ─revertido→ revertido · reversion_fallida ─aplicando→ aplicando (se reintenta)
```

- Los **seis** estados del Maestro: `recibido`, `verificado`, `incompatible`, `aplicado`, `revertido`, `archivado`. Extensiones marcadas: `programado`, `aplicando` y `reversion_fallida` (el único estado en que el aula conserva la copia de la base sin haber vuelto atrás: se avisa y nadie borra nada, Q-U4).
- No se guarda un «estado actual»: se **deriva** de las filas de `m17_historial` (`estados.derivar`), de sólo inserción (trigger). `rechazado` no es un estado: es la única fila sin paquete (TST-048: un paquete rechazado no se guarda).
- `bloqueada` (FUN-183) no cambia el estado: deja constancia de que una clase impidió aplicar (o revertir). `aplazada` es lo que responde el `Host` si al empezar había una clase: vuelve al estado anterior a `aplicando`.
- El «incompatible con el ciclo congelado» del Maestro (C-10) no aplica en este repo: no hay ciclos ni paquetes curriculares.

## 5 · La aplicación: la orden al `Host` y su resultado (P-06, P-07)

Django **verifica y decide**; el `Host` (servicio SYSTEM) **aplica**, con el backend parado, y Django **registra** el resultado al volver (FUN-187).

1. `POST …/aplicar/` (o la ventana): permiso, estado aplicable, ninguna otra orden, **cero clases** (si hay una: 409 `sesion_activa` y fila `bloqueada`), el `.avupd` guardado se **vuelve a verificar** (A5), compatibilidad y espacio otra vez, extracción a `staging\<id>\` (rutas validadas otra vez al escribir), y en UNA transacción la fila `aplicando` + el asiento + `orden.json` (creado **sin sobrescribir**: una sola orden a la vez).
2. `orden.json` lleva los pasos con checkpoint (`comprobar · respaldar · instantanea · copiar · migrar · verificar`), los módulos con sus migraciones y reversos, los archivos con su SHA-256, las carpetas `staging` e `instantanea` relativas a `Actualizaciones\` y el límite de minutos (3 si toca `evaluacion`, 5 en general; C-3).
3. El `Host` (Fase 4) escribe `checkpoint.json` antes de cada paso, aplica y deja `resultado.json`: `aplicado`, `revertido`, `reversion_fallida`, `aplazada` o `rechazada`.
4. Al arrancar (antes de la primera petición) y en cada tick, el vigilante lee `resultado.json`, lo valida, lo registra en el historial con sus eventos (`modulo_aplicada`, `migracion_ejecutada` por migración, `revertida`, `reversion_fallida`, `bloqueada` si se aplazó, y siempre `resultado_registrado`), lo archiva en `resultados\<orden>.json`, borra el staging y levanta el 503.

Lo que hoy **no** ocurre: nadie lee `orden.json`. Hasta la Fase 4 un paquete `aplicando` espera; si la orden desaparece de disco (nadie la tomó) y pasan diez minutos, el vigilante la cierra como `aplazada` para que el aula no se quede con el 503 para siempre (D-10).

## 6 · Ventana, clases y el 503 (P-08, R-01, R-02)

- **Ventana única** (CAP-108 como MVP, C-2): `desde` como mucho 5 min en el pasado y 90 días en el futuro; duración entre 10 min y un día. Se cancela con `desprogramar/`. Vencida sin aplicar, vuelve a `verificado` (`ventana_vencida`).
- **Apertura** (`ventana.decidir`): dentro de la ventana, **cero** sesiones abiertas o suspendidas (lo responde `classroom_engine.servicios.hay_sesion_activa`) y a más de 15 min de la próxima clase programada **si el nodo la conoce** (hoy no: Q-U9). Con clase, una fila `bloqueada` por ventana y se espera al siguiente tick; una orden por tick: el aula se para **una** vez.
- **503.** Desde que se acepta la orden hasta que llega el resultado, `POST /api/aula/sesiones/` responde `503 actualizacion_en_curso` con `Retry-After: 60`, y **nada más** cambia: unirse, responder, exámenes, estudio y sus colas siguen igual (un 5xx conserva la cola del cliente; un 4xx la descartaría). Es un middleware propio, lee memoria y deja pasar ante cualquier fallo (R-04). Una clase ya abierta jamás se toca.

## 7 · Compatibilidad y serie (P-04, P-16, INV-007)

Antes de aplicar (y al importar, para mostrarlo) se comprueba y se devuelve **la lista completa** de problemas:

| Código | Cuándo |
|---|---|
| `version_minima_no_cumplida` | el paquete exige una versión del producto que el nodo no tiene |
| `serie_menor` | la versión del producto del paquete es anterior a la instalada, o la serie de un módulo es menor que la instalada (A2: no se degrada) |
| `ya_aplicado` | la serie del módulo es la instalada |
| `modulo_desconocido` · `modulo_no_actualizable` | el módulo no está en el registro, o no se actualiza por separado (`biblioteca`) |
| `version_datos_retrocede` | el paquete deja los datos en una versión anterior a la aplicada |
| `contrato_requerido` | el módulo necesita de otro un contrato que el nodo no tiene (y el paquete no lo trae) |
| `contrato_incompatible` | el módulo cambia su contrato y un consumidor instalado (que el paquete no trae) no acepta ese rango |
| `contrato_biblioteca` | el paquete habla otro contrato de AVACOM Biblioteca (se **lee** `biblioteca.contenido_v2.CONTRATO`, R-12) |
| `espacio_insuficiente` | libre < base (+wal +shm) + instantánea + staging + paquete + 64 MB (no hace al paquete `incompatible`: el espacio cambia) |
| `licencia` | MOD-018 no admite lo que la actualización habilita (provisional: nunca) |

Avisos que no bloquean: `cliente_minimo` (el nodo no sabe qué Student hay en las tabletas, R-13) y `contrato_red`.

Lo instalado sale del **registro de módulos** `avacom_lms/modulos.json` (P-01: una entrada por app, con versión de módulo, contrato, serie —la que trae el instalador es la 1—, lo que produce y lo que consume con rangos) más la **versión de datos viva**: el número de la última migración aplicada por app (D-3), y la versión del producto de `installer/version.json` (o `manifiesto.json` del instalador, o `AVACOM_LMS_VERSION`).

## 8 · Permisos, bitácora y eventos (P-10, P-12, P-13)

| Permiso | Del Maestro | Administración | Técnico | Otros |
|---|---|---|---|---|
| `update.apply` (aplicar y revertir) | sí (tabla y ficha) | sí | **escalada** ESC-01 (4 h) | no |
| `update.package.import` | ficha J (no en la tabla; extensión marcada, Q-U3) | sí | sí | no |
| `update.schedule` (programar y cancelar) | ficha J (extensión marcada) | sí | no | no |
| `update.read` (estado, paquetes, historial) | extensión técnica propuesta | sí | sí | no |

Bitácora (`audit/dominio/catalogos.py`, módulo `actualizacion`): `importado`, `verificado`, `rechazado`, `programado`, `aplicado`, `revertido`, `reversion_fallida`, `bloqueada`, `firma_invalida`, `integridad_alterada` (P-13) y las extensiones `orden_emitida`, `archivado`, `desprogramado`, `aplazada`. Los asientos llevan id de paquete, versiones, serie, resultado y hash; nunca rutas ni personas. Un 503 no se asienta como denegación.

Eventos: los nueve del Maestro más `paquete_rechazado.v1` y `reversion_fallida.v1` (extensiones), publicados en **la cola única de MOD-015** con el sobre de doce campos, en la misma transacción que el hecho (D-1), clase **técnico**. `disponible_detectada.v1` se publica una vez por proceso y candidato, sin historial (no es un hecho del paquete).

## 9 · Tablas `m17_*`

| Tabla | Qué guarda | Escritura |
|---|---|---|
| `m17_paquete` | cada `.avupd` que pasó la firma y la forma: id, nombre, versión, serie, módulos, el resumen del manifiesto (sin rutas), `kid`, SHA-256 del archivo, bytes, nombre del archivo, origen, cuándo y quién | sólo inserción (trigger) |
| `m17_historial` | una fila por hecho (recibido … rechazado), con la marca del reloj del nodo, el actor y un detalle con ids, versiones, serie, resultado, hashes y la lista de incompatibilidades | sólo inserción (trigger) |

Ninguna clave foránea sale del módulo; ninguna columna guarda personas ni rutas. El archivo `.avupd` vive en `Actualizaciones\paquetes\<id>.avupd` y se vuelve a verificar contra su huella cada vez que se usa.

## 10 · Puertos y hermanos (P-14, P-15)

| Puerto | Adaptador | Estado |
|---|---|---|
| `Reloj` | `nodo.servicios.ahora_ms()` (la marca alta de MOD-015) | **real** (R-09: ninguna copia nueva de `RelojNodo`) |
| `Eventos` | `nodo.servicios.publicar` en la transacción del hecho | **real** (D-1: no hay `m17_evento_salida`) |
| `Auditoria` | `audit.servicios.anexar` | real |
| `Aula` | `classroom_engine.servicios.hay_sesion_activa` (ante un fallo se asume que **sí** hay clase) · `proxima_clase_en` = None (Q-U9) | real / sin horario |
| `Autorizacion` | la política de MOD-001 | real |
| `RegistroModulos` | `modulos.json` + migraciones aplicadas + versión + contrato de la biblioteca | real (provisional hasta que MOD-015 absorba el registro) |
| `Fuentes` · `Almacen` · `Claves` | unidades extraíbles y `entrada\` · la carpeta `Actualizaciones\` · `claves/*.json` | real |
| `Licencia` | `LicenciaSinRestriccion`: siempre «sin restricción» | **provisional** (MOD-018 no publica qué habilita una actualización) |
| `Respaldo` | `RespaldoDelHost`: la copia de la base y `backend.env` la toma el `Host` con `Datos.Respaldar` como paso de la orden | **provisional** (MOD-016 no existe). **Garantía que falta:** el punto de recuperación de 5 s de los intentos en curso (FUN-172); por eso aplicar exige cero sesiones y nada se aplica con un examen abierto |

## 11 · Cómo se leyó el Maestro (C-1 a C-11)

| # | Resolución en este repo |
|---|---|
| C-1 | Importar, verificar y programar sí durante una clase; **aplicar se difiere** (409 `sesion_activa`, fila `bloqueada`). Probado con una clase real abierta (TST-050). |
| C-2 | Ventana única en MVP; recurrentes en V1. |
| C-3 | `limite_minutos`: 3 si el paquete toca `evaluacion`, 5 en general. Va en la orden; se mide en la Fase 4. |
| C-4 | Aplicar nunca necesita red; el canal sólo se declara (`AVACOM_ACTUALIZACION_CANAL`, apagado). |
| C-5 | Ninguna escritura en tablas ajenas: puertos y `servicios.py` de cada dueño (probado capturando las consultas, INV-023). |
| C-6 | Los paquetes de contenido son de AVACOM Contenido; `biblioteca/` es intocable y sólo se lee su contrato. |
| C-7 | La instantánea vive en `Actualizaciones\versiones\<id>\anterior\` 14 días; el instalador no la toca (marca `uninsneveruninstall`, Fase 4). |
| C-8 | `update.apply` tal cual; `update.package.import` y `update.schedule` como extensión marcada; `update.read` como extensión técnica (§8, Q-U3). |
| C-9 | MOD-018 «actualización por internet o paquete físico» = renovación de la licencia; MOD-017 no toca licencias. |
| C-10 | «Incompatible con el ciclo congelado» no aplica (sin ciclos ni curriculo en este repo). |
| C-11 | La reversión automática la hace el `Host` (Fase 4); la manual, la administración con `update.apply` y una nota, dentro de 14 días; el procedimiento del técnico sin sitio queda en `04-operacion.md` (Fase 5, Q-U4). |

## 12 · Decisiones (`D-n`)

| # | Decisión |
|---|---|
| D-1 | **MOD-015 ya existe**: los eventos van a `m15_evento` por `nodo.servicios.publicar` en la transacción del hecho; no se crea `m17_evento_salida`. Se regeneró el catálogo de la cola (`nodo/dominio/catalogo_datos.py`, +11 tipos de clase técnico, sin tocar ningún otro). |
| D-2 | R-07 concretado: un paquete sólo trae `backend/<app>/**` de las apps que declara y `avacom_lms/modulos.json`; extensiones de código o datos; nunca `biblioteca/`, `manage.py`, `avacom_lms/*` (salvo el registro), binarios ni nada fuera de `backend/`. |
| D-3 | La versión de **datos** de un módulo es el número de su última migración aplicada (`django_migrations`), leída viva; `modulos.json` no la guarda (las otras sesiones añaden migraciones a diario). |
| D-4 | Contenedor **canónico y sin compresión**. Hallazgo de las mutaciones: con `zipfile` 864 de 70 000 cambios de bytes se aceptaban (fechas, versiones, atributos); con valores fijos quedaban 2 (bits de relleno dentro de deflate); sin compresión, **0**. |
| D-5 | La firma cubre la cabecera (magic, versión, kid) y los bytes exactos del manifiesto; `manifiesto.firma` es binario con forma exacta. |
| D-6 | Rechazos: `firma_invalida` (422) para los motivos de firma (`sin_firma`, `kid_desconocido`, `firma_invalida`, forma de la firma) y `paquete_invalido` (422) para los de forma; fila `rechazado` sin paquete, asiento `firma_invalida` o `integridad_alterada` + `rechazado`, evento `paquete_rechazado.v1`; el mismo archivo rechazado se recuerda una hora (no llena la bitácora). |
| D-7 | FUN-181 se dispara al importar (el paquete «terminó de copiarse»): recibido + verificado (o incompatible) en una transacción; la compatibilidad se vuelve a evaluar al aplicar. |
| D-8 | Estados internos `programado`, `aplicando`, `reversion_fallida`; `aplazada` vuelve al estado anterior; `bloqueada` no cambia el estado (también sobre `aplicado` cuando una reversión choca con una clase). |
| D-9 | `orden.json` se crea sin sobrescribir (`os.rename`, que en Windows falla si existe): una sola orden a la vez, también entre procesos. El staging lo extrae Django (rutas validadas otra vez y confinadas); el `Host` copia desde ahí. |
| D-10 | El 503 sólo en `POST /api/aula/sesiones/`, de memoria; una fila `aplicando` sin orden en disco ni resultado durante más de 10 minutos se cierra como `aplazada` (orden que nadie tomó). |
| D-11 | Reloj: `nodo.servicios.ahora_ms()`; ninguna copia nueva de `RelojNodo` (una prueba lo exige). |
| D-12 | Permisos como en §8; el técnico importa y lee, aplica sólo por escalada. |
| D-13 | Revertir exige una **nota**; dentro de 14 días desde `aplicado_en`; pasado el plazo el vigilante deja `archivado` y el `Host` borrará la instantánea (Fase 4). `reversion_fallida` se puede reintentar. |
| D-14 | `disponible_detectada.v1` una vez por proceso y candidato, sin historial; el canal por internet sólo se declara. |
| D-15 | `version_producto` del paquete ≥ instalada (si no, `serie_menor`); `version_minima` ≤ instalada; serie por módulo > instalada (igual = `ya_aplicado`). |
| D-16 | Un candidato es un id opaco (huella de origen, fuente, nombre, bytes y fecha): la API nunca recibe ni devuelve una ruta. Fuentes: unidades extraíbles reales (`GetDriveType`, raíz y `AVACOM\`), `entrada\`, y en desarrollo las carpetas de `AVACOM_ACTUALIZACION_UNIDADES`. Un candidato ya importado (mismo nombre y tamaño) se marca `importado`. |
| D-17 | Entorno: se reutiliza `settings.AVACOM_LICENCIA_ENTORNO` (P-12 de MOD-018). En producción sólo `claves/produccion.json` (vacío hasta la ceremonia: ningún paquete se acepta, con `kid_desconocido`) y la carpeta de `%ProgramData%`; ninguna variable lo cambia. |
| D-18 | Licencia y respaldo provisionales (§10). Importar dos veces el mismo archivo devuelve el mismo paquete; el mismo `paquete_id` con otro contenido es 409 `paquete_repetido`. |
| D-19 | INV-023 se comprueba capturando las consultas SQL de importar + aplicar: sólo `m17_*`, `m15_evento` y `m19_*` (la bitácora) reciben escrituras. |

## 13 · Riesgos y el límite honesto

| Adversario | Qué pasa |
|---|---|
| A1 · medio alterado | Se **impide**: firma sobre el manifiesto, SHA-256 por archivo, contenedor canónico. 100 000 mutaciones con semilla fija, 0 aceptadas. |
| A2 · degradación | Se **impide**: serie por módulo y versión del producto monótonas. |
| A3 · ruta maliciosa, bomba | Se **impide**: rutas validadas dos veces (al leer y al escribir en el staging, confinado), sin descompresión. |
| A4 · corte a mitad | Se **recupera** en la Fase 4 (checkpoints del `Host`). Hoy: el resultado se lee al arrancar antes de la primera petición. |
| A5 · administrador local | **No se impide**. Se detecta: el `.avupd` guardado se vuelve a verificar al aplicar (un byte cambiado lo rechaza), y el historial queda en la bitácora encadenada. El `Host` y `backend.env` no son alcanzables por un paquete (D-2). |

## 14 · Línea base y hallazgos ajenos (R-11)

- Línea base antes de tocar nada (`manage.py test acceso audit device_manager nodo`): **484 pruebas, 313 s, 1 fallo ajeno**: `nodo.tests.test_dominio.SobreTests.test_lo_que_falte_se_rellena_con_el_sistema_o_falla_si_no_se_puede` espera que un `agregado_id` de más de 96 caracteres falle, y la otra sesión (MOD-015, Fase 3) acaba de ampliarlo a 256 (`nodo/0003`). **No se tocó**: es trabajo en curso de esa sesión.
- La suite completa con el módulo: 2512 pruebas, 2 fallos ajenos en `nodo.tests.test_publicar` (uno de tiempo bajo carga, otro por las anclas de la secuencia compartidas entre dos corridas a la vez), que pasan solos y con `actualizacion` delante; detalle en `03-pruebas.md` §1. La base de pruebas de este módulo aísla desde entonces las anclas del nodo por prueba (`AVACOM_NODO_DIR` temporal + `nodo_limpio()`).
- Ninguna prueba existente cambió.

## 15 · Preguntas para el CTO (`Q-U`)

Las respuestas por defecto del prompt se adoptaron tal cual: Q-U1 ventana única; Q-U2 3 y 5 min; Q-U3 import técnico y administración, schedule administración; Q-U4 reversión manual por la administración con `update.apply` y nota (el procedimiento del técnico, Fase 5); Q-U5 diferido; Q-U6 sólo detección (declarada); Q-U7 AVACOM Contenido; Q-U8 llaves distintas con el mismo procedimiento; Q-U9 15 min (el nodo no conoce el horario); Q-U10 no en MVP. Una pregunta nueva: **Q-U11** ¿el paquete debe aceptar compresión (D-4 lo descarta: un paquete de código mide pocos MB y así cada byte queda determinado por el contenido)?

## 16 · Fases 3 a 5 (clientes, Host, emisor y operación)

**Fase 3 · clientes.** `src/Avacom.Lms.Core/Actualizacion/` (modelos, `ActualizacionApi`, `ActualizacionTexto` y las reglas puras de qué botón se ofrece según rol, clase abierta, plazo de 14 días y orden en curso); `src/Avacom.Lms.Ops/Pages/ActualizacionesPage.cs` y `Ops/Actualizacion/` (flujo puro, selector táctil de ventana, hoja de confirmación única); botón «Actualizaciones» en el menú, sólo para administración y técnico (un profesor nunca lo ve); texto de `actualizacion_en_curso` en Student (`ClaseUnirsePage`) y en OPS (`ClaseCursoPage`), sin bloquear tabletas ya registradas y con la cola de respuestas intacta (un 503 no la descarta). Fixtures reales de 36 respuestas en `tests/Avacom.Lms.Core.Tests/Fixtures/actualizacion/`.

**Fase 4 · Host.** `installer/src/host/Actualizacion/` (`Orden`, `Aplicador`, `Instantanea`, `Soporte`, `VigilanteDeActualizaciones`) y el verbo `aplicar-actualizacion`. El servicio mira `orden.json` cada 3 s, escribe `checkpoint.json` antes de cada paso, aplaza si ve una clase (con el backend aún vivo), revierte solo, retoma o deshace tras un corte al arrancar y deja `resultado.json`. Emisor interno en `tools/actualizacion/` (llaves cifradas, `emitir`, `verificar`, `ver`, `plantilla`); ver [05-emision.md](05-emision.md). Bloque F de `Ensayar-Paquete.ps1`.

| # | Decisión |
|---|---|
| D-20 | **Orden de los pasos en una reversión manual**: `comprobar → respaldar → migrar → copiar → verificar` (no `copiar` antes de `migrar` como decía el primer borrador de `02-api.md` §3): el reverso de una migración necesita el código que la define, así que se migra hacia atrás **antes** de devolver el código. |
| D-21 | Los ganchos `AVACOM_ACTUALIZACION_FALLO` y `AVACOM_ACTUALIZACION_CORTE` (fallar o matar al Host en un paso) sólo actúan con `AVACOM_OPS_ENSAYO=1` y una carpeta de estado de pruebas. Son código permanente, no temporal. |
| D-22 | `limite_minutos` acota el avance hacia adelante; la duración de la reversión se mide y se informa aparte en el `detalle` del resultado. |
| D-23 | La instantánea anota la versión del producto: tras una instalación completa el Host **no vuelve** a código de otra versión (lo dice y no toca nada). `Actualizaciones\` está declarada `uninsneveruninstall`, como `Respaldos` (P-17). |
| D-24 | La pantalla de OPS pide el motivo de una reversión de una **lista cerrada** (no hay teclado, R-10); el texto elegido es la nota que exige el nodo. |
| D-25 | Aplicar, programar y revertir sólo se ofrecen a la administración: la pantalla no concede la escalada temporal ESC-01 del técnico (el nodo igual decide el permiso). |

**Preguntas nuevas:** **Q-U12** ¿el técnico debe poder pedir la escalada ESC-01 desde la propia pantalla Actualizaciones, o sigue siendo la administración quien aplica? **Q-U4** sigue abierta: no hay reversión sin técnico en sitio cuando la propia reversión automática falla ([04-operacion.md](04-operacion.md) §4).

**Qué falta y se sabe:** la ceremonia de llaves (`claves/produccion.json` vacío: un nodo de producción rechaza todo paquete con `kid_desconocido`); el paquete portátil del emisor (`Build-Emisor.ps1`); la instalación del servicio real con elevación; los 30 ensayos de NFR-022 (hechos 4 corridas completas, ver [03-pruebas.md](03-pruebas.md)).

