# 15 · Licenciamiento (MOD-018) · API `/api/licencia/`

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-20) en `backend/licenciamiento/`. El diseño, las decisiones y lo pendiente están en [01-diseno.md](01-diseno.md). |
| Respuestas reales | `tests/Avacom.Lms.Core.Tests/Fixtures/licencia/` (41 respuestas JSON y 5 archivos de ejemplo: dos `.avlic`, uno alterado, un `.avlic` en texto, un `.avreq` y un `.avrel`): las captura `backend/licenciamiento/tests/test_capturar_contrato.py` contra el backend de verdad (`AVACOM_CAPTURAR_CONTRATO=1`). Un DTO de C# que no las lee bien es un DTO mal escrito. Los ejemplos de abajo son esas respuestas, recortadas. |
| Cliente | `src/Avacom.Lms.Core/Licencia/` (modelos, `LicenciaApi`, `LicenciaTexto`, reglas puras) y las pantallas de OPS. Student no tiene cliente de licencia (P-19). |
| Quién emite el archivo | `tools/licencias/` ([05-emision.md](05-emision.md)). El nodo nunca habla con él: el archivo viaja en un USB. |

## 0 · Convenciones

- **Quién actúa.** Con sesión (MOD-001), quien firma el JWT; el permiso lo evalúa la política de `acceso` con el rol efectivo, con alcance de toda la organización (una licencia es del nodo, no de un grupo). Sin sesión (Q-34, prototipo) la vista acepta al `actor` que el cliente declare, como los demás módulos; con `AVACOM_LMS_EXIGIR_SESION=1`, 401 a lo anónimo. **El permiso se comprueba antes de leer el cuerpo**: quien no puede activar no se entera de qué le faltaba al archivo.
- **Tiempo.** Toda marca es del reloj del **nodo**, en milisegundos (`ahora`, `calculada_en`, `desde`, `vence`…). Nada usa el reloj del cliente.
- **Los archivos viajan en JSON.** Para **enviar** una licencia: `licencia` con el texto `AVL1.…`, o `archivo_b64` con los bytes del `.avlic`. Al **recibir** un archivo la respuesta trae `archivo_b64` (los bytes), `texto` (la variante `AVL1.`/`AVQ1.`/`AVR1.` para copiar como texto), `nombre` sugerido y `sha256`. El tope es 16 KiB.
- **Cero internet** en cualquier ruta (R-13). Ninguna ruta de este módulo llama a otro servidor.
- **Errores.** `{detail, codigo, …extras}`; los extras nunca pisan `detail` ni `codigo`.

  | HTTP | `codigo` |
  |---|---|
  | 400 | `datos_invalidos` · `licencia_invalida` (+`motivo`, de una lista cerrada: §4) |
  | 401 | sesión requerida (con la sesión obligatoria) |
  | 402 | `cupo_agotado` (+`tipo`, `limite`, `en_uso`) · `no_disponible_por_licencia` (+`capacidad`, `modulo`) — **nunca 403** (P-09: un 403 se asentaría como acceso denegado). Los emiten el cupo y el middleware, no las rutas de `/api/licencia/` |
  | 403 | `sin_permiso` (+`permiso`) |
  | 404 | `no_encontrado` (+`motivo`) |
  | 409 | `huella_no_coincide` (+`coinciden`, `k`) · `conflicto` (+`motivo`) |

- **`/api/licencia/` es intocable** (R-01): con la licencia degradada responde igual; sin ella no se podría renovar. Y **ninguna ruta de licencia pide internet ni toca datos académicos**.

## 1 · Consultar (permiso `license.read`: técnico y administración)

| Ruta | Verbo | Qué hace |
|---|---|---|
| `estado/` | GET | El estado completo (el objeto de abajo). Lo recalcula a demanda sólo si todavía no hay una instantánea; el programador la mantiene al día |
| `consumo/` | GET | Equipos y usuarios frente a lo contratado, y la concurrencia (BR-063). **Se cuenta en el momento** (dos consultas pequeñas): `{equipos{en_uso, limite, porcentaje}, usuarios{…}, concurrentes{normal, pico}, calculado_en}`. `en_uso` y `porcentaje` son `null` si no se pudo contar (sin organización, base ocupada); un límite ilimitado es `null` |
| `capacidades/` | GET | **Cualquier sesión** (el profesor, el alumno, Reportes): qué módulos están habilitados, **sin un solo detalle de la licencia**: `{estado, restringe, habilitadas[], no_disponibles[]}` |
| `copia/` | GET | CAP-111: el `.avlic` vigente, para guardarlo fuera del nodo: `{archivo_b64, texto, nombre, sha256, licencia}`. Es una **lectura**: no cambia nada. 404 `sin_licencia_instalada` si no hay una |

**El estado** (`estado/`, y lo que devuelven `activar/`, `renovar/`, `liberar/` y `reloj/confirmar/`; con `accion` o los datos del archivo además):

```json
{
  "estado": "activa", "motivo": "vigente", "tipo": "produccion", "restringe": false,
  "modo": "firmada", "entorno": "pruebas", "banderas": [],
  "licencia": {
    "id": "a7a7a7a7-0001-4000-8000-000000000001", "serie": 1, "aula": "Aula de pruebas", "kid": "dev-1", "tipo": "produccion",
    "emitida": 1789833262857, "desde": 1789919662857, "vence": 1821455662857, "gracia_dias": 30,
    "capacidades": ["*"], "liberacion_pendiente": false, "liberacion_dias": 0, "archivo": "494b280e4bd8",
    "limites": {"equipos": 55, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100}
  },
  "vigencia": {"desde": 1789919662857, "vence": 1821455662857, "gracia_dias": 30, "hasta": 1821455662857, "dias_restantes": 335},
  "huella": {"nivel": "hardware", "coincide": true, "parcial": false, "k": 3, "factores": 4, "coinciden": 4},
  "limites": {"equipos": 55, "usuarios": 1200, "concurrentes_normal": 50, "concurrentes_pico": 100},
  "capacidades": {"habilitadas": ["administracion_avanzada", "busqueda", "importacion", "reportes"], "no_disponibles": []},
  "avisos": [], "consumo": {"equipos": 1, "usuarios": 3},
  "calculada_en": 1792511662857, "ahora": 1792511663028
}
```

- `estado`: `sin_licencia` · `activa` · `reactivada` · `en_gracia` · `liberacion_pendiente` · `degradada`. `motivo`: `evaluacion` · `evaluacion_vencida` · `vigente` · `vencida` · `huella_distinta` · `liberacion_pendiente` · `liberacion_no_confirmada` · `aun_no_vigente` · `reactivada` · `licencia_ilimitada` (el nodo de desarrollo o pruebas). `banderas`: `reloj_sospechoso` (la fecha del equipo va **por detrás**) · `reloj_adelantado` (va **por delante** y el nodo no la acepta: Q-L13) · `huella_parcial` · `integridad_alterada`.
- `licencia` es `null` sin licencia. **Nunca** trae la firma ni identificadores de hardware: `archivo` es el hash corto del archivo, `huella` sólo cifras y el nivel (`hardware` · `instalacion`; en `sin_licencia` `coincide` es `null`).
- `vigencia.hasta` es el **próximo hito** para quien lee: fin de la vigencia, de la gracia, del plazo de liberación o de la evaluación; `dias_restantes` son días completos, hacia arriba y nunca negativos.
- `limites` son los de la licencia; sin licencia, los de la evaluación (60 equipos, 1200 usuarios, 50/100 concurrentes: el tamaño máximo de un aula, Q-L1). `null` = sin tope. (Los ejemplos de arriba son una captura con la licencia de las pruebas, que trae 55 equipos; el plan `anual-aula` del emisor trae 60.)
- `avisos[]`, en orden de importancia; son **códigos con sus cifras** y el texto lo pone el cliente:

  | `codigo` | Cifras | Cuándo |
  |---|---|---|
  | `reloj_adelantado` | `adelanto_dias` (al día más cercano, mínimo 1), `fecha_equipo` y `fecha_esperada` (ms del nodo) | La fecha del equipo saltó hacia adelante, el nodo no la aceptó ni la guardó y espera a que concuerde (Q-L13). Va **primero**. No cambia el estado: nada se degrada |
  | `degradada` | `motivo` | Estado `degradada` |
  | `gracia` | `dias`, `motivo` (`vencida` o `huella_distinta`) | `en_gracia` |
  | `liberacion_pendiente` | `dias` | `liberacion_pendiente` |
  | `evaluacion` | `dias`, `urgente` (7 días o menos) | `sin_licencia`, **desde el primer día** |
  | `por_vencer` | `dias`, `umbral` (30/14/7/3/1) | `activa` o `reactivada` cerca del vencimiento |
  | `cupo` | `tipo` (`equipos`/`usuarios`), `en_uso`, `limite`, `porcentaje` | 90 % o más del límite |
  | `reloj_sospechoso` · `huella_parcial` · `integridad_alterada` | — | La bandera correspondiente (la de `reloj_adelantado` ya tiene su aviso con cifras) |

- Otros ejemplos reales: `estado_sin_licencia` (`avisos: [{"codigo":"evaluacion","dias":30,"urgente":false}]`), `estado_gracia` (`dias: 22`), `estado_degradada` (`capacidades.no_disponibles` con las cuatro), `estado_huella_parcial`, `estado_huella_distinta`, `estado_liberacion_pendiente` (14 días), `estado_por_vencer_y_cupo` (`{"codigo":"por_vencer","dias":12,"umbral":14}`), `estado_cupo_lleno`, `estado_reloj_retroceso` y `estado_reloj_adelantado` (`{"codigo":"reloj_adelantado","adelanto_dias":32,"fecha_equipo":…,"fecha_esperada":…}`: el estado sigue `activa`).

## 2 · Activar, renovar y liberar (sin internet, por archivo)

| Ruta | Verbo | Permiso | Qué hace |
|---|---|---|---|
| `solicitud/` | POST | `license.activate` | CAP-110, primer paso: la **solicitud** de este equipo. 201 `{archivo_b64, texto, nombre, nivel, k, factores, sha256}`. Lleva la huella **hasheada** (nunca identificadores crudos), un nonce, la versión y el nivel de huella, firmada con la llave del nodo. Cada solicitud trae su propio nonce. Deja el asiento `licencia.solicitud_generada` |
| `activar/` | POST | `license.activate` | FUN-188 (y FUN-194): instala un `.avlic`. Cuerpo `{licencia}` o `{archivo_b64}`. 200 `{accion, …estado}` con `accion` ∈ `activada` · `renovada` · `reactivada` |
| `renovar/` | POST | `license.renew` | FUN-191: instala un `.avlic` **posterior de la misma licencia**. 200 `{accion: "renovada", …estado}` |
| `liberar/` | POST | `license.activate` | JRN-020: «Liberar este equipo». 201 `{archivo_b64, texto, nombre, licencia_id, serie, sha256, …estado}`: el `.avrel` firmado con la llave del nodo; el equipo deja de usar la licencia y vuelve a `sin_licencia`. 409 `sin_licencia_instalada` si no hay una |

**Qué se comprueba, en este orden** (el archivo se verifica **antes** de mirar lo que dice): tamaño y forma (`demasiado_grande` · `demasiado_corta` · `formato` · `texto`) → versión (`version_no_soportada`) → llave (`kid_desconocido`) → firma (`firma_invalida`) → campos (`etiqueta_critica_desconocida` · `campo_faltante` · `campo_invalido`) → tipo (`tipo_no_admitido`: una licencia de desarrollo no entra en producción) → que no empiece en el futuro (`aun_no_vigente`: más de un día, D-7/D-8) → **que sea para ESTE equipo** (409 `huella_no_coincide`, con cuántos factores coinciden y cuántos hacen falta) → las reglas de serie.

**Las reglas de serie** (qué es el archivo respecto de lo instalado):

| Situación | `activar/` | `renovar/` |
|---|---|---|
| No hay licencia instalada | `activada` | 400 `sin_licencia_instalada` |
| Otra licencia, y la vigente está sana (`activa`/`reactivada`) | 400 `otra_licencia`: primero se libera este equipo | 400 `otra_licencia` |
| Otra licencia, y la vigente no está sana | `activada` | 400 `otra_licencia` |
| La misma licencia, serie **anterior** | 400 `serie_no_posterior` | 400 `serie_no_posterior` |
| La misma licencia y serie (el mismo archivo otra vez) | `reactivada`: no cambia nada | 400 `serie_no_posterior` |
| La misma licencia, serie **posterior**, **otra huella** | `activada` (**traslado**, D-10: lo hace el técnico) | `renovada`* |
| La misma licencia, serie **posterior**, la **misma** huella | `renovada` (pide `license.renew`) | `renovada` |

\* `renovar/` siempre pide `license.renew`.

- Un archivo cuya firma o llave no valen es un hecho auditable (`licencia.firma_invalida`, resultado `denegado`, con el tamaño y el hash corto, nunca el contenido); el resto son errores de uso y no dejan asiento.
- **Liberar se puede deshacer** volviendo a activar el mismo archivo: el nodo guarda una «tumba» de lo que liberó para que una base restaurada no lo resucite, y activar a propósito la quita (la respuesta dice `activada` y no `reactivada`: tras liberar ya no hay una licencia vigente). Los nombres sugeridos (`solicitud-…`, `liberacion-…`) llevan la hora **UTC**.
- Activar, renovar o liberar **nunca detienen una clase ni tocan un dato académico** (R-01, R-03).

## 3 · El reloj (permiso `license.activate`)

| Ruta | Verbo | Qué hace |
|---|---|---|
| `reloj/confirmar/` | POST | Extensión (P-06): quien administra confirma que la fecha del equipo es la correcta. Con la bandera `reloj_adelantado` (Q-L13) es **la única forma de que el nodo acepte y guarde esa fecha**: el aula se había quedado atrás y hoy es la que dice el equipo; con `reloj_sospechoso` (la fecha iba por detrás) apaga la sospecha. Cuerpo vacío; 200 con el estado. Deja `licencia.reloj_confirmado`. Si la fecha del equipo está **mal**, no se confirma: se corrige en Windows y el aviso se quita solo |

Una fecha adelantada **no cambia el estado ni apaga nada**: sólo levanta la bandera y el aviso `reloj_adelantado` hasta que la fecha concuerde (o la administración confirme) y las acciones que fechan algo (`activar/`, `renovar/`, `liberar/`, `solicitud/`) usan la hora que el nodo considera confiable, no la del equipo (D-18).

No existe una ruta para **bajar** la marca alta del reloj (§5 de [01-diseno.md](01-diseno.md): Q-L13).

## 4 · Los `motivo` de `licencia_invalida`

Son parte del contrato (OPS los convierte en frases; **no se renombran**). El `detail` ya viene en español claro y no revela nada del contenido:

| `motivo` | Cuándo |
|---|---|
| `demasiado_grande` · `demasiado_corta` · `formato` · `texto` | El archivo no tiene la forma de una licencia (`texto`: el texto `AVL1.…` está incompleto o alterado) |
| `version_no_soportada` | Una versión del formato que este nodo no entiende (ni menor —degradación— ni mayor) |
| `kid_desconocido` | Firmada con una llave que este nodo no reconoce (por ejemplo, la de desarrollo en producción, o la de producción cuando todavía no hay ninguna) |
| `firma_invalida` | El archivo fue modificado o no es de AVACOM |
| `etiqueta_critica_desconocida` | «Actualiza AVACOM OPS»: la licencia exige algo que esta versión no entiende |
| `campo_faltante` · `campo_invalido` | Falta información obligatoria o hay un dato fuera de rango (por ejemplo, un límite en 0: no limita, detendría la clase; D-17) |
| `tipo_no_admitido` | Licencia de desarrollo en un nodo de producción |
| `aun_no_vigente` | Empieza en más de un día: «revisa que la fecha y la hora del equipo estén bien» |
| `serie_no_posterior` · `otra_licencia` · `sin_licencia_instalada` | Reglas de serie (§2) |
| `solicitud_ajena` | (reservado) una solicitud que no firmó este equipo |

Ejemplos reales: `error_firma_invalida`, `error_aun_no_vigente`, `error_otra_licencia`, `error_serie_no_posterior`, `error_texto_invalido`, `error_sin_cuerpo` (`datos_invalidos`: «Falta la licencia: manda `licencia` (texto AVL1.…) o `archivo_b64`»), `error_huella_no_coincide` (`{"codigo":"huella_no_coincide","coinciden":1,"k":3,"detail":"Esta licencia fue emitida para otro equipo."}`), `error_sin_permiso` y `error_sin_permiso_renovar` (`{"codigo":"sin_permiso","permiso":"license.renew"}`).

## 5 · Lo que ven los demás módulos y los clientes

- **Módulo apagado**: la petición a una ruta licenciable ([01-diseno.md](01-diseno.md) §7) recibe `402`:

  ```json
  {"codigo": "no_disponible_por_licencia", "capacidad": "reportes", "modulo": "Reportes y exportaciones",
   "detail": "Este módulo no está disponible con la licencia actual. Tu permiso se conserva: vuelve a funcionar al renovar la licencia."}
  ```

  El permiso del rol **no se toca**: al renovar, el mismo rol vuelve a funcionar. Un bloqueo no escribe en la base en el camino de la petición: el programador asienta `licencia.bloqueo_aplicado`, **uno por actor, módulo y hora**. En el cliente (Core) es `ErrorAula.PorLicencia` con **un texto común**, no un parche por pantalla.
- **Cupo agotado** (alta de un equipo o de una persona por encima del límite): `402 cupo_agotado` con `tipo`, `limite` y `en_uso`. Lo que ya existe, las readmisiones y los latidos no se tocan. Una importación al tope crea hasta el cupo y rechaza el resto fila por fila.
- **`/health/`** gana un campo **aditivo**: `"licencia": {"estado", "modo", "restringe", "dias_restantes"}` (sólo el estado; `estado: "desconocido"` si no se pudo leer; nunca hace fallar al health).
- **Concurrencia 50/100** (BR-063): el aula la toma de la licencia; sin licencia, de `settings`.
- **Student**: sólo textos para `cupo_agotado` y `no_disponible_por_licencia`; ninguna pantalla ni lógica de licencia.

## 6 · Permisos

| Permiso | Quién | Para qué |
|---|---|---|
| `license.read` | Administración, técnico | `estado/`, `consumo/`, `copia/` (extensión técnica propuesta, como `reports.settings.manage`: sin datos de personas) |
| `license.activate` | Administración, técnico | `solicitud/`, `activar/`, `liberar/`, `reloj/confirmar/` (FUN-188, FUN-194; el traslado de JRN-020) |
| `license.renew` | **Sólo la administración** | `renovar/` y la serie posterior con la misma huella (FUN-191) |

El profesor, el alumno y Reportes **no tienen ninguno**: ven «no disponible por licencia», jamás datos de la licencia (`capacidades/` es lo único que leen). Los permisos se siembran en `acceso/dominio/plantillas.py` y la migración `acceso/0018_permisos_licencia.py` los da a las instalaciones existentes (idempotente). La administración los hereda sola.

## 7 · Eventos y asientos

**Eventos** (`m18_evento_salida`, `.v1`, idempotentes por clave): `licencia.activada`, `licencia.validada` (una vez por arranque), `licencia.consumo_calculado` (una vez por hora), `licencia.renovada`, `licencia.periodo_gracia_iniciado`, `licencia.funciones_degradadas`, `licencia.reactivada` —los del Maestro— y las **extensiones** `licencia.liberada`, `licencia.reloj_sospechoso`, `licencia.integridad_alterada`, `licencia.evaluacion_iniciada` y `licencia.aviso_emitido` (al cruzar cada umbral de aviso).

**Bitácora** (módulo `licencia`): `licencia.activada` · `renovada` · `liberada` · `solicitud_generada` · `gracia_iniciada` · `degradada` · `reactivada` · `bloqueo_aplicado` · `reloj_sospechoso` · `integridad_alterada` · `firma_invalida`, y las extensiones `evaluacion_iniciada` y `reloj_confirmado`. **Sin contenido de licencia ni huellas crudas**: ids, serie, resultado y hash corto. Las transiciones que provoca el tiempo (gracia, degradación, avisos) se asientan **una sola vez por episodio**; repetir un ciclo no repite nada.

## 8 · Lo que añade a la lista de P-17

`GET copia/` (CAP-111: la ficha del Maestro pide la copia y P-17 no le daba ruta), `POST reloj/confirmar/` (P-06: «esperar confirmación» exige un modo de confirmar), el permiso `license.read`, el campo `licencia` de `/health/` y los eventos y acciones marcados como extensión (D-13).

## 9 · Identidad de dispositivo (Fase 5)

Dos rutas **públicas** (como el latido: el equipo se identifica antes de tener sesión): `POST identidad/reto/` (un reto de 32 bytes, de un solo uso, vence a los 5 minutos) y `POST identidad/enrolar/` (la clave pública, la firma del reto y, en Android, la cadena de atestación). Además, `POST /api/dispositivos/latido/` y `POST /api/dispositivos/` aceptan un campo opcional `identidad` que sólo usa un equipo **nuevo**, y los equipos de `/api/dispositivos/` traen `garantia`, `clave_huella` y `garantia_detalle`. Errores nuevos: `400 reto_invalido` · `400 identidad_invalida` · `409 clave_distinta` · `409 clave_en_uso` · `402 identidad_requerida` (equipo nuevo sin la garantía mínima de la licencia). Los cuerpos reales capturados están en [08-identidad-de-dispositivo.md](08-identidad-de-dispositivo.md), anexo.
