# 05 · Audit y logs (MOD-019) · Pruebas técnicas en producción (happy paths)

| Campo | Valor |
|---|---|
| Módulo | MOD-019 · Audit y logs (`backend/audit/`: bitácora `m19_bitacora`, logs JSON Lines, `/api/auditoria/*` y `/api/logs/*`; pantallas de OPS; entrega de logs de OPS y Student) |
| Tipo de documento | Plan de pruebas técnicas — spec driven dev |
| Alcance | **Sólo happy paths.** Caminos tristes y malos, carga y pruebas destructivas quedan fuera y se cubren con las pruebas automáticas del repositorio (§8) |
| Quién ejecuta | Operador/QA con acceso de administrador al nodo instalado (PowerShell elevada), a OPS y a tabletas reales |
| Fuentes | [introduccion.md](introduccion.md) · [modelado_datos.md](modelado_datos.md) · [backend.md](backend.md) · [frontend.md](frontend.md) · formato de [`../06-evaluation-delivery/testing.md`](../06-evaluation-delivery/testing.md). Código: `backend/audit/` (`interfaces/`, `aplicacion/`, `dominio/`, `infraestructura/`, `logging_setup.py`, `middleware.py`, `tests/`) · `backend/tools/ver_logs.py` · `backend/avacom_lms/settings.py` · `backend/acceso/dominio/plantillas.py` · `backend/classroom_engine/aplicacion/casos_uso*.py` · `installer/src/host/{Rutas,Configuracion}.cs` · `src/Avacom.Lms.Ops/Pages/{BitacoraPage*,DispositivosPage,ClaseSesionPage}` · `src/Avacom.Lms.Core/Services/{RegistroLocal,EntregadorDeLogs,AutorizacionDeSalida}.cs` · `src/Avacom.Lms.Student/{CicloDeVida,Telemetria}.cs` |
| Fecha | 2026-10-01 |
| Estado | Borrador para ejecución. Escrito **sin acceso a producción**: cada ruta, permiso, acción, archivo, variable y texto de pantalla sale del código y de los documentos; lo no confirmable va marcado «(por confirmar en producción)» |

---

## 1 · Propósito y alcance

Estos casos demuestran, **en el entorno real**, que MOD-019 cumple cuando todo sale bien; cada caso demuestra uno o varios requisitos (matriz en §4). Se demuestra que:

* Cada hecho relevante deja un **asiento completo** y la bitácora **sólo crece**: secuencia sin huecos y cadena de huellas SHA-256 continua, verificable por el nodo y por fuera de él (HP-AUD-01, 02, 03, 05, 07, 08).
* Sólo quien tiene `audit.read` consulta; la consulta se filtra, se pagina y **se asienta**; lo sensible sale **enmascarado** salvo con una escalada vigente (HP-AUD-04, 06, 12).
* Exportar exige `audit.export` **y** una autorización de salida de una operación, y el archivo sale firmado (HP-AUD-07, 13); la bitácora **rota por tamaño** sin borrar filas (HP-AUD-15).
* Classroom Engine asienta clase, aviso, proyección y **sólo las transiciones** de presencia (HP-AUD-08); los **logs de archivo** son JSON Lines sin datos personales y Student y OPS entregan sus avisos al nodo (HP-AUD-09, 11, 14); el técnico lee logs, **no** la bitácora, y se puede mostrar que no accedió a datos personales (HP-AUD-10, 12, 14); MOD-010 queda asentado (HP-AUD-16).

**No** se demuestra: caminos tristes y malos, carga ni nada que dañe datos reales (§8).

---

## 2 · Entorno y precondiciones

### 2.1 · Antes de ejecutar cualquier caso

| # | Precondición | Cómo comprobarla |
|---|---|---|
| P-1 | **Nodo** instalado: servicio `AVACOMOPSBackend` en marcha, organización instalada, puerto `8000` (`AVACOM_OPS_BACKEND_PORT`) | `Get-Service AVACOMOPSBackend` → `Running`; `GET <NODO>/health/` → `status: "ok"` |
| P-2 | Con **MOD-019** y **Daphne** (`avacom_lms.asgi`), el único que arranca el temporizador. Producto `2.1.0` (`installer/version.json`; por confirmar que incluye MOD-019) | `GET /api/auditoria/estado/` → `200` y `version_catalogo: "2026.09.30"`; con `404`, detenerse |
| P-3 | Cuentas **identificables** (alias `QA-…`), creadas por el procedimiento de Acceso (ejemplo de petición en `backend/audit/tests/test_api.py`): **QA-ADMIN-A** (`ADMIN`, el operador) · **QA-ADMIN-B** (`ADMIN`, otra identidad: autoriza la salida) · **QA-TECNICO** (`TECHNICIAN`) · **QA-PROFESOR** (`TEACHER`, con materia asignada) | `GET /api/acceso/yo/` → ADMIN con `audit.read`, `audit.export`, `diagnostics.read`; TECHNICIAN **sólo** `diagnostics.read` |
| P-4 | **OPS** en el nodo principal (pantalla «Nodo principal del aula»: «Dirección del servidor», «Comprobar conexión», «Documento», «Clave», «Entrar») y una **tableta de prueba** con Student, registrada en OPS → «Dispositivos», que ningún alumno real use (`$DISP_QA`) | `GET /api/dispositivos/` la lista |
| P-5 | Herramienta de §2.4 en `$HERR`; carpeta `$EVID` (§2.3) | — |
| P-6 | Para HP-AUD-15: ventana **fuera de clase** y autorización escrita del responsable del nodo para cambiar `backend.env` y reiniciar el servicio | — |

### 2.2 · Rutas reales y variables de entorno

| Qué | Dónde |
|---|---|
| Instalación | `C:\Program Files\AVACOM\OPS Master\` (`Runtime\Python\python.exe`, `Backend\tools\ver_logs.py`; por confirmar en producción) |
| Configuración · base de datos (SQLite, WAL) | `C:\ProgramData\AVACOM\OPS Master\Config\backend.env` (`CLAVE=valor`, variables de entorno del servicio) · `...\Data\ops-master.sqlite3` |
| **Logs del nodo** | `C:\ProgramData\AVACOM\OPS Master\Logs\`: `backend-app.log`, `backend-errores.log` (WARNING+), `backend-auditoria.log`, `backend-clientes.log` (nace con la primera entrega de un equipo), `instalacion.log` (texto del instalador + JSON del backend). Rotación 2 MB × 5 (`.log.1` … `.log.5`) |
| Tramos · exportaciones | `...\Logs\auditoria\tramo-<desde>-<hasta>.jsonl` · `...\Logs\auditoria\exportaciones\exportacion-<id>.jsonl` |
| Logs de OPS y Student · descargas de OPS | `%LOCALAPPDATA%\AVACOM\lms\logs\{ops,student}-app.log` y `-errores.log` (Android: almacenamiento privado) · `%USERPROFILE%\Downloads\avacom-auditoria\` |

La carpeta de logs sale de `AVACOM_LMS_DEBUG=0` (entorno «instalado»); el instalador no escribe `AVACOM_LMS_DIR_LOGS` ni `AVACOM_LMS_ENTORNO` (si existieran, mandarían). Otras variables de `backend.env`: `AVACOM_LMS_NIVEL_LOG` (`INFO`; con `WARNING` no habría líneas por petición), `AVACOM_LMS_AUDITORIA_UMBRAL_MB` (`100`), `AVACOM_LMS_AUDITORIA_VERIFICAR_CADA_S` (`3600`; `0` apaga el temporizador), `AVACOM_LMS_SECRET` (de ella se deriva la clave HMAC de la firma; `AVACOM_LMS_CLAVE_AUDITORIA` figura en `backend.md` pero `settings.py` **no la lee**: hallazgo de documentación) y `AVACOM_LMS_EXIGIR_SESION` (por confirmar; no relaja `/api/auditoria/` ni `/api/logs/`, pero en `0` los asientos del aula salen con `actor_tipo = "declarado"`).

### 2.3 · Ayudante de PowerShell

Pegar una vez en una consola **elevada**. `<NODO>` es la dirección que muestra OPS; `$TA`, `$TB` y `$TT` guardan el `<TOKEN>` de QA-ADMIN-A, B y QA-TECNICO al identificarse; los `<ID>` que salen de un paso se guardan en variables (`$A_ID`, `$DISP_QA`, `$SEC0`…) que los pasos siguientes usan.

```powershell
$N = 'http://<NODO>:8000'; $INST = 'C:\Program Files\AVACOM\OPS Master'; $DATOS = 'C:\ProgramData\AVACOM\OPS Master'
$LOGS = "$DATOS\Logs"; $PY = "$INST\Runtime\Python\python.exe"; $VER = "$INST\Backend\tools\ver_logs.py"
$HERR = 'C:\QA-AUDIT\herramientas'; $EVID = 'C:\QA-AUDIT\evidencia\2026-10-01'      # <EVID>
New-Item -ItemType Directory -Force $HERR, $EVID | Out-Null; $TA = $null; $TB = $null; $TT = $null
function Api {   # Api GET|POST|DELETE <ruta> [cuerpo @{}] [-Token ''] ; token por defecto: el de A
  param([string]$Metodo, [string]$Ruta, $Cuerpo = $null, [string]$Token = $script:TA)
  $p = @{ Method = $Metodo; Uri = "$N$Ruta"; ContentType = 'application/json; charset=utf-8'; Headers = @{} }
  if ($Token) { $p.Headers['Authorization'] = "Bearer $Token" }
  if ($null -ne $Cuerpo) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($Cuerpo | ConvertTo-Json -Depth 8)) }
  Invoke-RestMethod @p
}
function Guardar {   # ... | Guardar 'HP-AUD-NN-x.json'  (JSON UTF-8 en $EVID; deja pasar el objeto)
  param([Parameter(Position=0)][string]$Nombre, [Parameter(ValueFromPipeline=$true)]$Objeto)
  process { $Objeto | ConvertTo-Json -Depth 10 | Out-File -Encoding utf8 -FilePath (Join-Path $EVID $Nombre); $Objeto }
}
function VerLogs    { & $PY $VER --carpeta $LOGS @args }
function VerArchivo { & $PY "$HERR\verificar_archivo_bitacora.py" @args }
```

### 2.4 · Verificar un archivo de la bitácora fuera del nodo

Guardar como `$HERR\verificar_archivo_bitacora.py`. Repite lo que hacen `firma.py` y `huella.py`: recalcula la firma HMAC-SHA256 del manifiesto (clave derivada de `AVACOM_LMS_SECRET` de `backend.env`; **no se imprime**) y la cadena de huellas. Sirve para exportaciones y tramos rotados. Sale con `0` si todo coincide y con `1` si no.

```python
import hashlib, hmac, json, sys
from pathlib import Path
CAMPOS = ("secuencia", "ocurrido_en", "usuario_id", "actor_tipo", "roles_activos", "modulo", "accion", "resultado",
          "objeto_tabla", "objeto_id", "valor_anterior", "valor_nuevo", "motivo", "origen", "dispositivo_id",
          "correlacion_id", "evento_id")
def huella(previa, a):
    c = json.dumps({k: a.get(k) for k in CAMPOS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256((previa.lower() + c).encode("utf-8")).hexdigest()
env = Path(sys.argv[2] if len(sys.argv) > 2 else r"C:\ProgramData\AVACOM\OPS Master\Config\backend.env")
pares = (l.split("=", 1) for l in env.read_text(encoding="utf-8-sig").splitlines() if "=" in l and not l.lstrip().startswith("#"))
secreto = {k.strip(): v.strip() for k, v in pares}.get("AVACOM_LMS_SECRET", "prototipo-aula-sin-internet-no-es-secreto")
clave = hashlib.sha256(b"avacom-lms-auditoria-firma-v1|" + secreto.encode("utf-8")).digest()
ent = lambda s: int(float(s)) if float(s).is_integer() else float(s)   # como el nodo: 72.0 se hashea como 72
lineas = [json.loads(l, parse_float=ent) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
man, firma, asientos = lineas[0]["manifiesto"], lineas[0]["firma"], lineas[1:]
canonico = json.dumps(man, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
fallos = []
if not hmac.compare_digest("hmac-sha256:" + hmac.new(clave, canonico, hashlib.sha256).hexdigest(), str(firma)): fallos.append("la firma NO coincide")
if man["total"] != len(asientos): fallos.append(f"total {man['total']} != {len(asientos)} asientos")
previa, sec = man["huella_inicial"], man["desde"]
for a in asientos:
    if a["secuencia"] != sec: fallos.append(f"hueco o repetición en {sec}"); break
    if a["huella_previa"].lower() != previa.lower(): fallos.append(f"el asiento {sec} no enlaza con el anterior"); break
    if huella(previa, a) != a["huella"].lower(): fallos.append(f"la huella del asiento {sec} no coincide con su contenido"); break
    previa, sec = a["huella"], sec + 1
if not fallos and previa != man["huella_cierre"]: fallos.append("huella_cierre distinta de la del último asiento")
print(f"{Path(sys.argv[1]).name}: {man.get('alcance')} ({man['desde']}-{man['hasta']}, {len(asientos)} asientos)")
print("RESULTADO: FALLA - " + "; ".join(fallos) if fallos else "RESULTADO: OK - firma válida, totales y cadena de huellas íntegra")
sys.exit(1 if fallos else 0)
```

---

## 3 · Convenciones

* **ID de caso**: `HP-AUD-NN`. Cada caso: Objetivo · Requisitos que demuestra · Precondiciones · Datos / actor · Pasos · Resultado esperado · Evidencia a guardar · Efectos colaterales / limpieza.
* **Evidencia**: la salida de todo comando que sirva de prueba, guardada en `$EVID` (`Guardar` para JSON; `| Out-File -Encoding utf8` para texto) y nombrada `HP-AUD-NN-<paso>` (los comandos de §5 no repiten el `| Guardar`); las **capturas de pantalla** (`HP-AUD-NN-<paso>.png`); los archivos exportados; la fila de §7. **Nunca** guardar un `<TOKEN>`, una clave ni `backend.env`.
* **Criterio global**: un caso **pasa** sólo si **todos** sus resultados esperados se cumplen, verificados contra lo que devuelve el nodo o dice la pantalla; cualquier diferencia es **FALLA** con su evidencia. «N/E» (no ejecutado) sólo con autorización escrita y motivo; no cuenta como OK.
* **Anclas y resultados**: antes de un caso que genera asientos se anota la cabeza, `$SEC0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia`, y después se lista con `despues=$SEC0` (la referencia es la secuencia, no un reloj). Los resultados van a §7 (fecha, ejecutor, OK/FALLA, evidencia, observaciones).
* **Seguridad en producción**: datos de prueba **identificables** (cuentas `QA-…`, la tableta de prueba, motivos `QA-AUDIT HP-AUD-NN`, «Clase libre»); no se editan ni se usan usuarios, dispositivos, clases ni alumnos reales. **La bitácora no se puede borrar**: las pruebas dejan asientos permanentes y **es lo esperado**. **Nunca** ejecutar `tools/romper_cadena.py` ni tocar la base de datos. Los archivos exportados o rotados llevan los valores **sin enmascarar** y `asientos/` trae alias de personas reales: exportar sólo rangos de prueba y guardar la evidencia con acceso restringido. HP-AUD-15 cambia `backend.env` y **reinicia el servicio** (fuera de clase, con respaldo, restituyéndolo); los estímulos de red de HP-AUD-11 son con la tableta de prueba y sin clase abierta.

---

## 4 · Matriz de trazabilidad

| Requisito | Qué dice | Casos |
|---|---|---|
| 019-01 · FUN-195 · BR-099 | Asiento completo: actor, objeto, valores, motivo, origen, aparato | HP-AUD-02, 05, 07 (`motivo`), 08, 11 |
| TST-071 | 5 acciones sensibles con actor, fecha, valor anterior y motivo | HP-AUD-02, 07, 08 |
| 019-02 · FUN-196 · INV-002 | Secuencia sin huecos y huellas enlazadas | HP-AUD-01, 03 |
| 019-03 · BR-100 · INV-027 · AC-081 | Un cambio es un asiento nuevo (sólo el lado feliz) | HP-AUD-01, 02, 15 |
| 019-04 · FUN-198 · FUN-199 · NFR-036 | Verificar la cadena; detectar un salto es camino malo (§8) | HP-AUD-03, 12, 15 |
| 019-05 · FUN-197 · CAP-116 · BR-131 | Consulta por permiso, paginada, asentada y con enmascarado | HP-AUD-04, 06, 12 |
| 019-06 · FUN-200 · BR-105 · ESC-03 · MSG-054 | Exportar un tramo o rango firmado con autorización de salida | HP-AUD-07, 13 |
| PAN-240 · PAN-241 · MSG-052 | Pantalla «Bitácora» y autorización de salida | HP-AUD-12, 13 (PAN-241 por API en 06 y 07) |
| 019-07 · FUN-201 | Rotación por tamaño, filas intactas | HP-AUD-15 |
| 019-08 · DEC-034 · CMP-063 | Aviso, presencia, proyección con autor y duración, indicador «Proyectando» | HP-AUD-08 |
| 019-10 · BR-097 · CAP-118 · VER-01 · NFR-039 | El técnico no accede a datos personales | HP-AUD-10, 12, 14 |
| PAN-242 | «Estado del equipo» del técnico | HP-AUD-14 |
| Objetivo secundario 1 | Logs de archivo por canal y errores del dispositivo | HP-AUD-09, 10, 11, 14 |
| Objetivo secundario 4 · DEC-022 · AC-054 | Evaluaciones y cambio de calificación | HP-AUD-16 |
| TST-072 · VER-04 · AC-003 · INV-003 · 019-09 | Caminos tristes (exportar sin autorización, técnico abre evidencia, módulo no declarado) y eventos `auditoria.*` en `m19_evento_salida` (sólo por SQL) | Sin caso (§8) |

---

## 5 · Happy paths

### HP-AUD-01 · Nodo en servicio, logs en la carpeta real y bitácora abierta

**Objetivo.** Comprobar que el nodo tiene MOD-019, que sus logs caen en la carpeta de producción y que la bitácora arranca en la secuencia 1 con los disparadores de inmutabilidad presentes.

**Requisitos que demuestra.** 019-02 · 019-03 (capa de base de datos) · FUN-196 · INV-002.

**Precondiciones.** P-1 a P-5. **Datos / actor.** QA-ADMIN-A.

**Pasos.**

1. `Get-Service AVACOMOPSBackend | Select-Object Name, Status`; `Api GET '/health/' -Token ''`.
2. ```powershell
   $r = Api POST '/api/acceso/sesiones/' @{ identificador='<DOCUMENTO_QA_ADMIN_A>'; secreto='<CLAVE_QA_ADMIN_A>' } -Token ''
   $TA = $r.token; $A_ID = $r.usuario.id; $r.usuario
   (Api GET '/api/acceso/yo/').permisos | Where-Object { $_.codigo -in 'audit.read','audit.export','diagnostics.read' } | Select-Object codigo, alcance
   ```
3. `Api GET '/api/auditoria/estado/'; $T_INICIO = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')`; `Api GET '/api/auditoria/asientos/1/'`.
4. `Get-ChildItem $LOGS -File | Select-Object Name, Length`; `Select-String -Path "$DATOS\Config\backend.env" -Pattern '^AVACOM_LMS_(DEBUG|DIR_LOGS|ENTORNO|NIVEL_LOG|AUDITORIA_)' | ForEach-Object { $_.Line }`.

**Resultado esperado.**

* Servicio `Running`, salud `status = "ok"`; login con `usuario.rol = "ADMIN"` y los tres permisos con alcance `ORGANIZATION`.
* Estado: `version_catalogo = "2026.09.30"`, `triggers_ok = true` (existen los disparadores `m19_bitacora_no_update` y `_no_delete`), `salto_detectado = false`, `tramo_activo.abierta = true`, `total_asientos ≥ 2`, `verificar_cada_s = 3600`, `umbral_bytes = 104857600`.
* Asiento 1 con `huella_previa` de **64 ceros**: en un nodo nuevo es `auditoria.bitacora_abierta` (`actor.tipo = "sistema"`, `origen = "migracion"`); en uno actualizado, la primera acción migrada (y existe un `auditoria.cadena_migrada`).
* `backend-app.log`, `backend-auditoria.log` e `instalacion.log` en `C:\ProgramData\AVACOM\OPS Master\Logs`, ninguno de más de ≈ 2 MB; de `backend.env` sólo sale `AVACOM_LMS_DEBUG=0` (otra línea se anota: cambia carpeta, nivel o umbral).

**Evidencia a guardar.** Salidas de los pasos 2 a 4 (sin el token).

**Efectos colaterales / limpieza.** Asiento `identidad.sesion.abierta`. Cerrar la sesión de OPS al final (HP-AUD-14).

---

### HP-AUD-02 · Asiento completo y un asiento nuevo por cada cambio

**Objetivo.** Bloquear y desbloquear la tableta de prueba desde OPS deja un asiento completo por acción, con el contexto tomado de la petición, y el primero no se modifica.

**Requisitos que demuestra.** 019-01 · FUN-195 · BR-099 · TST-071 (con HP-AUD-07 y 08) · 019-03 · BR-100 · INV-027 · AC-081 (lado feliz).

**Precondiciones.** HP-AUD-01; OPS con sesión de QA-ADMIN-A, ya en el tablero (se registra como equipo `MASTER`). **Datos / actor.** QA-ADMIN-A; tableta `$DISP_QA`.

**Pasos.**

1. `$SEC0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia` y `Api GET '/api/dispositivos/' | Select-Object id, nombre, tipo, identificador_hw, bloqueado`: anotar `$DISP_QA` y `$DISP_OPS` (tipo `MASTER`, `identificador_hw` `ops-<nombre del equipo>`).
2. En OPS: hexágono **«Dispositivos»** → fila de la tableta de prueba → **«Bloquear»** (el botón pasa a **«Desbloquear»**).
3. ```powershell
   $fila = (Api GET "/api/auditoria/asientos/?despues=$SEC0&accion=dispositivos.bloqueado&objeto_id=$DISP_QA").asientos[0]; $SEC_B = $fila.secuencia
   $ASI1 = Api GET "/api/auditoria/asientos/$SEC_B/"; $ASI1
   ```
4. En OPS → **«Dispositivos»** → misma fila → **«Desbloquear»**. Luego:
   ```powershell
   Api GET "/api/auditoria/asientos/?objeto_tabla=m09_dispositivo&objeto_id=$DISP_QA&despues=$SEC0"
   $ASI2 = Api GET "/api/auditoria/asientos/$SEC_B/"; ($ASI1 | ConvertTo-Json -Depth 10 -Compress) -ceq ($ASI2 | ConvertTo-Json -Depth 10 -Compress)
   ```

**Resultado esperado.**

* Paso 3: `accion = "dispositivos.bloqueado"`, `etiqueta = "Equipo bloqueado"`, `resultado = "ok"`, `sensible = false`; `actor.tipo = "usuario"`, `actor.usuario_id = $A_ID`, `roles_activos = ["ADMIN"]`; `objeto = { tabla: "m09_dispositivo", id: $DISP_QA }`; `valor_anterior = { bloqueado: false }` y `valor_nuevo = { bloqueado: true, motivo: "desde Dispositivos del aula" }` (aquí el motivo viaja en `valor_nuevo`; la columna `motivo` se ve en HP-AUD-07).
* `origen = "api"`, `dispositivo_id = $DISP_OPS` (OPS manda `X-Avacom-Dispositivo`), `correlacion_id` no vacío, `evento_id = null`, `ocurrido_en` reciente; `huella` y `huella_previa` de 64 hexadecimales.
* Paso 4: la historia trae `total = 2` en orden `asc`: `dispositivos.bloqueado` y luego `dispositivos.desbloqueado` con secuencia **mayor**, `valor_anterior = { bloqueado: true }` y `valor_nuevo.bloqueado = false`; la comparación da `True` (el asiento viejo no cambió).

**Evidencia a guardar.** Salidas de los pasos 3 y 4 y una captura de OPS.

**Efectos colaterales / limpieza.** La tableta queda desbloqueada; los dos asientos quedan para siempre.

---

### HP-AUD-03 · Cadena de huellas continua y verificación de la cadena

**Objetivo.** La secuencia va de 1 en adelante sin huecos, cada asiento enlaza con el anterior y el nodo verifica la cadena (POST verificar, estado, tramos) dejando asiento, log y evento.

**Requisitos que demuestra.** 019-02 · FUN-196 · INV-002 · 019-04 · FUN-198 · FUN-199 (lado sin salto) · NFR-036.

**Precondiciones.** HP-AUD-01 (≥ 2 asientos). **Datos / actor.** QA-ADMIN-A.

**Pasos.**

1. ```powershell
   $p = Api GET '/api/auditoria/asientos/?despues=0&limite=200'
   $s = @($p.asientos | ForEach-Object { $_.secuencia }); $huecos = 0
   for ($i = 0; $i -lt $s.Count; $i++) { if ($s[$i] -ne $i + 1) { $huecos++ } }; "orden=$($p.orden) leidos=$($s.Count) huecos=$huecos"
   $d1 = Api GET '/api/auditoria/asientos/1/'; $d2 = Api GET '/api/auditoria/asientos/2/'; $d3 = Api GET '/api/auditoria/asientos/3/'
   $d1.huella_previa -eq ('0' * 64); $d2.huella_previa -eq $d1.huella; $d3.huella_previa -eq $d2.huella
   $e = Api GET '/api/auditoria/estado/'; $e.total_asientos -eq $e.cabeza.secuencia
   ```
2. ```powershell
   $SEC0 = $e.cabeza.secuencia; Api POST '/api/auditoria/verificar/' @{}
   $e0 = Api GET '/api/auditoria/estado/'; Api POST '/api/auditoria/verificar/' @{ todos = $true }
   Api GET '/api/auditoria/tramos/'; Api GET '/api/auditoria/estado/'
   Api GET "/api/auditoria/asientos/?despues=$SEC0&accion=auditoria.cadena_verificada"
   ```
3. `VerLogs --archivo backend-auditoria --evento auditoria.cadena_verificada --ultimos 3 --detalle`.

**Resultado esperado.**

* Paso 1: `orden = asc`, `huecos = 0` y cuatro `True` (la cabeza es igual al número de asientos; si el último da `False` por una escritura simultánea, repetirlo).
* Paso 2: ambas verificaciones dan `estado = "verificada"`, `salto_en = null`, `causa = null`; en la segunda, `verificados` = `$e0.total_asientos`. `tramos/`: el tramo abierto con `verificado_en` no nulo y `verificado_hasta` = la secuencia anterior al último `auditoria.cadena_verificada`. `estado/`: `ultimo_verificado_en` no nulo, `salto_detectado = false`, `triggers_ok = true`. Al menos dos asientos `auditoria.cadena_verificada` con `actor.usuario_id = $A_ID`, `origen = "api"`, `valor_nuevo = { verificados, tramos }`.
* Paso 3: log «Cadena verificada: tramo D-H (N asientos)» `[happy]`, canal `auditoria`.

**Evidencia a guardar.** Salidas de los pasos 1 a 3.

**Efectos colaterales / limpieza.** Dos asientos `cadena_verificada`, más un `auditoria.consulta_realizada` por cada lectura de `asientos/`.

---

### HP-AUD-04 · Consulta filtrada y paginada; la consulta deja su propio asiento

**Objetivo.** Consultar con filtros y por cursor y comprobar que cada consulta queda asentada con sus filtros.

**Requisitos que demuestra.** 019-05 · FUN-197 · CAP-116.

**Precondiciones.** HP-AUD-02. **Datos / actor.** QA-ADMIN-A.

**Pasos.**

1. `$SEC0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia; Api GET '/api/auditoria/catalogo/'`.
2. Filtros (cada llamada deja un asiento):
   ```powershell
   foreach ($q in 'modulo=dispositivos&limite=2', 'accion=dispositivos.*&limite=5', "accion=dispositivos.bloqueado&objeto_id=$DISP_QA", "actor=$A_ID&resultado=ok&limite=5") {
     $r = Api GET "/api/auditoria/asientos/?$q"; "$q -> total=$($r.total) devueltos=$($r.asientos.Count) enmascarado=$($r.enmascarado)"
   }
   ```
3. Su propio asiento: repetir `Api GET '/api/auditoria/asientos/?modulo=dispositivos&limite=2'` y enseguida `Api GET "/api/auditoria/asientos/?accion=auditoria.consulta_realizada&actor=$A_ID&limite=1"`.
4. Cursor:
   ```powershell
   $p1 = Api GET '/api/auditoria/asientos/?limite=3'; $p2 = Api GET "/api/auditoria/asientos/?limite=3&antes=$($p1.siguiente)"
   ($p1.asientos.secuencia -join ','); ($p2.asientos.secuencia -join ','); (Api GET "/api/auditoria/asientos/?despues=$SEC0&limite=200").orden
   ```

**Resultado esperado.**

* Catálogo: `version = "2026.09.30"`; `modulos` incluye `{ clave: "aula", etiqueta: "Aula (clase en vivo)" }` y no `pruebas`; `acciones` incluye `dispositivos.bloqueado` y `aula.control.*`.
* Filtros: todo asiento devuelto cumple su filtro, `enmascarado = true` y `limite ≤ 200`; cada asiento trae actor, roles, módulo, acción y `etiqueta`, resultado, objeto, motivo, origen, dispositivo, correlación, `sensible`, `huella` abreviada y valores.
* Paso 3: `auditoria.consulta_realizada` de A, `objeto.tabla = "m19_bitacora"`, `valor_nuevo = { filtros: { modulo: "dispositivos" }, limite: 2, devueltos, cursor: { antes: null, despues: null } }`.
* Paso 4: `desc`; las secuencias de `$p2` son menores que las de `$p1`, decrecen y no repiten ninguna aunque entre ambas llamadas se agregó un asiento; el último comando da `asc`.

**Evidencia a guardar.** Salidas de los pasos 2 a 4.

**Efectos colaterales / limpieza.** Un `auditoria.consulta_realizada` por cada `GET asientos/`.

---

### HP-AUD-05 · Correlación y aparato en cada asiento y en cada log

**Objetivo.** Con un identificador de correlación se reconstruye una operación (petición, asiento, log); el aparato nunca se inventa.

**Requisitos que demuestra.** 019-01 (origen, dispositivo, correlación) · §2.5 de la introducción.

**Precondiciones.** HP-AUD-02 (`$SEC_B`). **Datos / actor.** QA-ADMIN-A.

**Pasos.**

1. ```powershell
   $h = @{ Authorization = "Bearer $TA"; 'X-Avacom-Correlacion' = 'QA-HP05-0001' }
   $r = Invoke-WebRequest -UseBasicParsing -Uri "$N/api/auditoria/asientos/?modulo=dispositivos&limite=1" -Headers $h
   $r.StatusCode; $r.Headers['X-Avacom-Correlacion']
   Api GET '/api/auditoria/asientos/?correlacion=QA-HP05-0001'; VerLogs --corr QA-HP05-0001
   ```
2. La de una operación de OPS: `$X = Api GET "/api/auditoria/asientos/$SEC_B/"; VerLogs --corr $X.correlacion_id`.

**Resultado esperado.**

* `200` y la **misma** correlación en la cabecera de respuesta (sin cabecera de entrada, un UUID). El asiento `auditoria.consulta_realizada` de esa consulta trae `correlacion_id = "QA-HP05-0001"`, `origen = "api"`, **`dispositivo_id = null`** (sin `X-Avacom-Dispositivo` el aparato queda vacío) y `actor.usuario_id = $A_ID`.
* `VerLogs` muestra al menos dos líneas con ese `corr`: `http.peticion` `[happy]` «GET /api/auditoria/asientos/ → 200» (`backend-app.log`) y `bitacora.asiento` «Asiento anexado #N auditoria.consulta_realizada» (`backend-auditoria.log`). Con el `corr` que generó OPS: «POST /api/dispositivos/<id>/bloquear/ → 200» y el asiento `dispositivos.bloqueado`.

**Evidencia a guardar.** Salidas de los pasos 1 y 2.

**Efectos colaterales / limpieza.** Dos `auditoria.consulta_realizada`.

---

### HP-AUD-06 · Enmascarado de valores sensibles y lectura completa con escalada vigente

**Objetivo.** Los asientos sensibles llegan enmascarados; con una escalada vigente de `audit.read` concedida por otra identidad se ven completos y esa lectura queda asentada.

**Requisitos que demuestra.** BR-131 · 019-05 · PAN-241 (por API).

**Precondiciones.** Existe un asiento con `sensible = true` (p. ej. `identidad.usuario.creado` de las cuentas QA o `aula.proyeccion.iniciada` de HP-AUD-08). **Datos / actor.** A lee; B concede.

**Pasos.**

1. ```powershell
   $S0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia
   $m = Api GET '/api/auditoria/asientos/?sensible=true&limite=3'; $X = $m.asientos[0]
   Api GET "/api/auditoria/asientos/$($X.id)/"; (Api GET "/api/auditoria/asientos/?accion=acceso.dato_personal.consultado&despues=$S0").total
   ```
2. B se identifica y concede a A (15 minutos):
   ```powershell
   $TB = (Api POST '/api/acceso/sesiones/' @{ identificador='<DOCUMENTO_QA_ADMIN_B>'; secreto='<CLAVE_QA_ADMIN_B>' } -Token '').token
   $hasta = [DateTimeOffset]::UtcNow.AddMinutes(15).ToUnixTimeMilliseconds()
   Api POST "/api/acceso/usuarios/$A_ID/escaladas/" @{ permiso='audit.read'; alcance='ORGANIZATION'; motivo='QA-AUDIT HP-AUD-06 ver valores sensibles'; vigente_hasta=$hasta } -Token $TB
   ```
3. ```powershell
   $m2 = Api GET '/api/auditoria/asientos/?sensible=true&limite=3'; Api GET "/api/auditoria/asientos/$($X.id)/"
   Api GET "/api/auditoria/asientos/?accion=acceso.dato_personal.consultado&despues=$S0&actor=$A_ID"
   ```
4. Limpieza: `Api DELETE "/api/acceso/usuarios/$A_ID/escaladas/audit.read/" -Token $TB`; repetir la consulta del paso 1.

**Resultado esperado.**

* Paso 1: `$m.enmascarado = true`; cada asiento con `sensible = true`, `enmascarado = true`, `valor_anterior` y `valor_nuevo` iguales a `{ enmascarado: true }`; el detalle sigue enmascarado pero trae `huella` y `huella_previa` completas; la búsqueda da `0`.
* Paso 2: `201`. Paso 3: `$m2.enmascarado = false` y los valores reales a la vista; el detalle de `$X` deja un asiento **`acceso.dato_personal.consultado`** a nombre de A (`objeto.id = $X.id`, `valor_nuevo.secuencia = $X.secuencia`).
* Paso 4: `204` y, revocada, la consulta vuelve a salir enmascarada. Quedan `identidad.escalada.concedida` e `identidad.escalada.revocada` (actor B).

**Evidencia a guardar.** Salidas de los pasos 1 a 4 (valores visibles sólo si son de prueba).

**Efectos colaterales / limpieza.** Escalada revocada en el paso 4 (si se olvida, caduca a los 15 minutos). Cerrar la sesión de B: `Api DELETE '/api/acceso/sesiones/actual/' -Token $TB`.

---

### HP-AUD-07 · Exportación de un rango firmado con autorización de salida

**Objetivo.** Exportar un rango pequeño con una autorización concedida por otra identidad, verificar archivo y firma fuera del nodo y comprobar que la autorización se consume.

**Requisitos que demuestra.** 019-06 · FUN-200 · BR-105 · ESC-03 · MSG-054 · TST-071 (columna `motivo`) · FUN-196.

**Precondiciones.** HP-AUD-03; §2.4 guardado. **Datos / actor.** A exporta; B autoriza.

**Pasos.**

1. Ancla y un rango de 20 asientos ya verificados:
   ```powershell
   $S0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia; Api POST '/api/auditoria/verificar/' @{} | Out-Null
   $t = (Api GET '/api/auditoria/tramos/').tramos | Where-Object { $_.abierta }; $HASTA = $t.verificado_hasta; $DESDE = $HASTA - 19
   ```
2. B concede a A la autorización (30 minutos, una operación; si `$TB` está vacío, B se identifica como en HP-AUD-06):
   ```powershell
   $h30 = [DateTimeOffset]::UtcNow.AddMinutes(30).ToUnixTimeMilliseconds()
   Api POST "/api/acceso/usuarios/$A_ID/escaladas/" @{ permiso='audit.export'; alcance='ORGANIZATION'; motivo='QA-AUDIT HP-AUD-07 exportación de prueba'; vigente_hasta=$h30 } -Token $TB
   Api GET '/api/auditoria/exportaciones/'
   ```
3. ```powershell
   $x = Api POST '/api/auditoria/exportar/' @{ desde=$DESDE; hasta=$HASTA; motivo_codigo='inspeccion_interna'; motivo_detalle='QA-AUDIT HP-AUD-07' }; $x
   $ARCH = "$LOGS\auditoria\exportaciones\$($x.archivo)"; Api GET '/api/auditoria/exportaciones/'
   Api GET "/api/auditoria/asientos/?despues=$S0&accion=auditoria.tramo_exportado"; Api GET "/api/auditoria/asientos/?despues=$S0&accion=acceso.escalada.consumida"
   ```
4. Archivo, descarga y verificación fuera del nodo:
   ```powershell
   (Get-Content $ARCH -Encoding UTF8 -TotalCount 1).Substring(0, 100); (Get-Content $ARCH -Encoding UTF8 | Measure-Object -Line).Lines
   $d = Invoke-WebRequest -UseBasicParsing -Uri "$N$($x.descarga)" -Headers @{ Authorization = "Bearer $TA" } -OutFile "$EVID\$($x.archivo)" -PassThru
   $d.Headers['Content-Type']; (Get-FileHash $ARCH -Algorithm SHA256).Hash -eq (Get-FileHash "$EVID\$($x.archivo)" -Algorithm SHA256).Hash
   VerArchivo $ARCH
   ```

**Resultado esperado.**

* Paso 2: `201`; `exportaciones/` con `autorizacion_vigente = true` y los cinco `motivos` de lista (`inspeccion_interna`, `auditoria_externa`, `requerimiento_legal`, `respaldo_externo`, `soporte_avacom`).
* Paso 3: **201** con `exportacion_id`, `alcance = "asientos <DESDE>-<HASTA>"`, `total = 20`, `archivo = "exportacion-<id>.jsonl"`, `firma` que empieza con `hmac-sha256:`, `mensaje = "Queda registrado que exportaste asientos <DESDE>-<HASTA>."` (MSG-054) y `descarga`. Después, `autorizacion_vigente = false` (valía una operación) y la exportación con `disponible = true`, `exportado_por = $A_ID`, `motivo = "Inspección interna: QA-AUDIT HP-AUD-07"`.
* `auditoria.tramo_exportado` con `usuario = $A_ID`, la **columna `motivo`** con ese texto, `objeto = { tabla: "exportacion", id }` y `valor_nuevo` con `alcance`, `desde`, `hasta`, `archivo`, `firma`, `total`; `acceso.escalada.consumida` con `valor_nuevo.operacion = "exportacion:<id>"`.
* Paso 4: la primera línea del archivo es `{"firma": "hmac-sha256:…", "manifiesto": {…}}`; tiene 21 líneas (`total + 1`); la descarga responde `application/x-ndjson` y los SHA-256 coinciden (`True`); `VerArchivo` → `RESULTADO: OK - firma válida, totales y cadena de huellas íntegra`.

**Evidencia a guardar.** Salidas de los pasos 2 a 4 y el archivo descargado (acceso restringido).

**Efectos colaterales / limpieza.** El archivo queda en `Logs\auditoria\exportaciones\`. La autorización ya está consumida; cerrar la sesión de B.

---

### HP-AUD-08 · Classroom Engine: clase, aviso, proyección y presencia

**Objetivo.** Una clase de prueba deja los asientos del aula con autor, duración y transición, sin un asiento por latido ni el texto del aviso.

**Requisitos que demuestra.** 019-08 · FUN-195 · DEC-034 · CMP-063 · TST-071.

**Precondiciones.** HP-AUD-02, Student conectado al aula en la tableta de prueba y QA-PROFESOR. Anotar si el nodo exige sesión: `Api GET '/api/acceso/configuracion/' -Token ''` → `sesion_obligatoria`. **Datos / actor.** QA-PROFESOR en OPS; un alumno de prueba.

**Pasos.**

1. `$SEC0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia`.
2. En OPS con QA-PROFESOR: hexágono **«Clase de hoy»** → materia → curso → **«Clase libre»**. Anotar el código de unión.
3. En la tableta: menú de Student → **«Clase en vivo»** → «Entrar a la clase» y teclear el código. Si pide admisión: OPS **«Participantes»** → **«Admitir»**.
4. Aviso: botón **⚠** («Enviar un aviso») → frase **«Dos minutos»**.
5. Proyección: **«Participantes»** → fila del alumno → **«Proyectar»** (la tableta muestra **«Proyectando tu pantalla al grupo»**); esperar **10 s** o más; **«Dejar de proyectar»**.
6. Presencia: en la tableta pasar Student a segundo plano unos 10 s (Android: botón Inicio; Windows: minimizar) y volver.
7. En OPS: **«Terminar clase»** → **«Terminar»**.
8. ```powershell
   $a = Api GET "/api/auditoria/asientos/?despues=$SEC0&modulo=aula&limite=200"
   $a.asientos | Select-Object secuencia, accion, origen, dispositivo_id, @{n='actor';e={$_.actor.usuario_id}}, @{n='tipo';e={$_.actor.tipo}} | Format-Table -AutoSize
   ```

**Resultado esperado.**

* En este orden relativo: `aula.sesion.iniciada`, `aula.participante.ingreso` (y `aula.participante.admitido` si hubo admisión), `aula.aviso.enviado`, `aula.proyeccion.iniciada`, `aula.proyeccion.terminada`, `aula.presencia.perdida`, `aula.presencia.recuperada`, `aula.sesion.finalizada`.
* `aula.sesion.iniciada`: `objeto = { tabla: "m07_sesion", id }`, `valor_nuevo` con `via`, `curso_ref`, `grupo_id`; con sesión obligatoria el actor es `usuario` (QA-PROFESOR); sin ella, `declarado`.
* `aula.aviso.enviado`: `valor_nuevo = { alcance: "grupo", participante_id: null, largo: 11 }`; el texto «Dos minutos» **no aparece**.
* `aula.proyeccion.iniciada` sale **enmascarado** (`sensible`); `aula.proyeccion.terminada`: `valor_anterior.autor` = id de QA-PROFESOR y `valor_nuevo.duracion_seg ≥ 10`.
* `aula.presencia.perdida`: de `conectado` a `{ estado: "reconectando", causa: "declarada por la tableta" }`, con `dispositivo_id = $DISP_QA`; `aula.presencia.recuperada`: de `reconectando` a `conectado`. Una de cada una por ciclo: los latidos no dejan asiento.
* `aula.sesion.finalizada` con el resumen. La banda de proyección sólo se vio durante la proyección.

**Evidencia a guardar.** Salida del paso 8 y capturas de la tableta (banda) y de OPS.

**Efectos colaterales / limpieza.** La clase queda **cerrada** (no se reabre). `aula.proyeccion.iniciada` sirve a HP-AUD-06.

---

### HP-AUD-09 · Logs de archivo del nodo por canal, sin datos personales

**Objetivo.** Ver qué archivos hay en la carpeta real, qué línea deja cada acción y que el formato es JSON Lines sin secretos.

**Requisitos que demuestra.** Objetivo secundario 1 · §2.1, §2.2 y §2.6 de la introducción.

**Precondiciones.** HP-AUD-02 a 08 y 11; `$SEC_B`, `$T_INICIO`. **Datos / actor.** Operador con lectura de `$LOGS`.

**Pasos.**

1. `Get-ChildItem $LOGS -File | Sort-Object Name | Select-Object Name, Length`; `Get-Content "$LOGS\backend-auditoria.log" -Tail 1`.
2. ```powershell
   VerLogs --archivo backend-app --evento http.peticion --desde $T_INICIO --ultimos 5 --detalle
   VerLogs --archivo backend-auditoria --evento bitacora.asiento --desde $T_INICIO --ultimos 8
   VerLogs --archivo backend-errores --nivel ERROR --desde $T_INICIO; VerLogs --archivo instalacion --ultimos 5
   ```
3. ```powershell
   Select-String -Path "$LOGS\backend-auditoria.log*" -Pattern "`"secuencia_bitacora`": $SEC_B," -SimpleMatch
   Select-String -Path "$LOGS\backend-auditoria.log*" -Pattern '"valor_nuevo"' -SimpleMatch
   Select-String -Path "$LOGS\*.log*" -Pattern '<CLAVE_QA_ADMIN_A>', '<DOCUMENTO_QA_ADMIN_A>', $TA.Substring(0,30) -SimpleMatch
   ```

**Resultado esperado.**

* Paso 1: están `backend-app.log`, `backend-auditoria.log`, `instalacion.log` (y `backend-errores.log`, y `backend-clientes.log` tras HP-AUD-11); ninguno pasa de ≈ 2 MB. La línea es JSON (`ts, nivel, canal, app, modulo, evento, ruta, …, corr, secuencia_bitacora, mensaje, detalle`) con `app = "backend"`, `canal = "auditoria"`, `evento = "bitacora.asiento"`.
* Paso 2: `backend-app` con `[happy]` «GET /api/auditoria/… → 200»; `backend-auditoria` con «Asiento anexado #N <acción>»; **ninguna** línea `ERROR` con `corr` de las pruebas (las ajenas se anotan sin contarlas); `instalacion` con líneas de texto del instalador (`?` en `VerLogs`).
* Paso 3: **una** coincidencia (`"ruta": "happy"`), luego **cero** y **cero**: el log de auditoría no lleva valores ni secretos.

**Evidencia a guardar.** Salidas de los pasos 1 a 3.

**Efectos colaterales / limpieza.** Ninguno.

---

### HP-AUD-10 · Técnico: logs por API y «accesos del técnico»

**Objetivo.** El técnico lee los logs con `diagnostics.read` (no la bitácora) y el Administrador consulta sus acciones y el indicador «sin acceso a datos personales».

**Requisitos que demuestra.** 019-10 · BR-097 · CAP-118 · VER-01 · NFR-039 · Objetivo secundario 1.

**Precondiciones.** HP-AUD-03 (cadena verificada) y HP-AUD-05 (líneas `QA-HP05-0001`). **Datos / actor.** QA-TECNICO y QA-ADMIN-A.

**Pasos.**

1. ```powershell
   $rt = Api POST '/api/acceso/sesiones/' @{ identificador='<DOCUMENTO_QA_TECNICO>'; secreto='<CLAVE_QA_TECNICO>' } -Token ''
   $TT = $rt.token; $T_ID = $rt.usuario.id
   (Api GET '/api/acceso/yo/' -Token $TT).permisos | Select-Object codigo, alcance
   ```
2. ```powershell
   foreach ($q in '?archivo=backend-auditoria&ultimos=5', '?canal=auditoria&nivel=INFO&ultimos=3', '?archivo=backend-app&corr=QA-HP05&ultimos=10') {
     $l = Api GET "/api/logs/$q" -Token $TT; "$q -> total=$($l.total) lineas=$($l.lineas.Count)"
   }
   (Api GET '/api/logs/?ultimos=5').total; (($l | ConvertTo-Json -Depth 10) -match '<DOCUMENTO_QA_ADMIN_A>')
   ```
3. Como A: `$t = Api GET '/api/auditoria/tecnico/accesos/'; $t | Select-Object total, denegaciones, sin_acceso_a_datos_personales, cadena_verificada, salto_detectado; $t.tecnicos; $t.asientos | Select-Object secuencia, accion, resultado`.

**Resultado esperado.**

* Paso 1: `usuario.rol = "TECHNICIAN"`; permisos con `diagnostics.read` y **sin** `audit.read` ni `audit.export`.
* Paso 2: todo `200`, con `lineas` (≤ `ultimos`), `total`, `resumen = { happy, sad, bad, niveles }` y `archivos`; cada filtro devuelve sólo líneas que lo cumplen y el de `corr` trae las de HP-AUD-05; con el token de A también `200`; la búsqueda del documento da `False`. Leer logs no deja asiento.
* Paso 3: `tecnicos` incluye `{ usuario_id: $T_ID, rotulo: <alias> }` (y los técnicos reales, si hay); `asientos` sólo de técnicos, con `identidad.sesion.abierta` del login; **`sin_acceso_a_datos_personales = true`**, `cadena_verificada = true`, `salto_detectado = false` (si da `false`, revisar el asiento causante antes de marcar FALLA: puede ser un acceso real). La consulta deja `auditoria.consulta_realizada` con `filtros = { tecnico: true, desde, hasta }`.

**Evidencia a guardar.** Salidas de los pasos 1 a 3.

**Efectos colaterales / limpieza.** Cerrar la sesión del técnico: `Api DELETE '/api/acceso/sesiones/actual/' -Token $TT`.

---

### HP-AUD-11 · Student: logs locales, entrega al nodo y «Exportar diagnóstico»

**Objetivo.** La tableta escribe sus logs en su dispositivo, entrega sus avisos al nodo cuando hay red y exporta un ZIP de diagnóstico.

**Requisitos que demuestra.** Objetivo secundario 1 · 019-01 (Student se identifica con su aparato) · D-3, D-4 y D-7 de `frontend.md`.

**Precondiciones.** Tableta de prueba con Student **ya registrada** (HP-AUD-08) y **sin clase abierta**. Windows: acceso a `%LOCALAPPDATA%\AVACOM\lms\logs`; Android: sin acceso al almacenamiento privado. **Datos / actor.** Operador con la tableta.

**Pasos.**

1. `$T11 = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')`. Abrir Student; en **«Conéctate a tu aula»** tocar **«Comprobar conexión»** y **«Entrar al aula»**. Windows: `Get-Content "$env:LOCALAPPDATA\AVACOM\lms\logs\student-app.log" -Tail 5`.
2. Estímulo controlado (no es una falla: es la forma de producir un aviso real que entregar): con la tableta fuera de clase, **apagar el Wi‑Fi unos 20 s y volver a encenderlo**. Esperar **90 s** (la entrega corre cada 60 s).
3. En el nodo:
   ```powershell
   Api GET "/api/logs/?archivo=backend-clientes&app=student&dispositivo=$DISP_QA&ultimos=10"
   Select-String -Path "$LOGS\backend-clientes.log*", "$LOGS\backend-errores.log*" -Pattern '"evento": "aula.invisible"' -SimpleMatch
   VerLogs --archivo backend-app --evento http.peticion --desde $T11 --ultimos 80 | Select-String 'logs/clientes'
   ```
4. En la tableta, en «Conéctate a tu aula», tocar **«Exportar diagnóstico»**.

**Resultado esperado.**

* Paso 1 (y, en Android, el ZIP del paso 4): `student-app.log` con `app.arranque`, `red.cambio`, `aula.invisible` (**WARNING**, canal `comunicacion`) y `aula.visible`; `student-errores.log` sólo con el WARNING.
* Paso 3: `lineas` con `evento = "aula.invisible"`, `nivel = "WARNING"`, `canal = "comunicacion"`, `app = "student"`, **`dispositivo_id = $DISP_QA`** (el que el nodo autenticó) y `detalle.ts_cliente`. La línea está en `backend-clientes.log` y en `backend-errores.log`; la entrega aparece como «POST /api/logs/clientes/ → 202» `[happy]`. Ninguna línea trae nombres, claves ni respuestas.
* Paso 4: «Diagnóstico guardado en <ruta>» (`diagnostico-student-<yyyyMMdd-HHmmss>.zip` en `FileSystem.AppDataDirectory/diagnostico/`); en Windows trae `diagnostico.json` (`app = "student"`, `dispositivo_id = $DISP_QA`, `servidor`) y los dos logs; extraerlo en Android es por confirmar en producción.

**Evidencia a guardar.** Salidas del paso 3, el ZIP (Windows) y capturas de la tableta.

**Efectos colaterales / limpieza.** Nace `backend-clientes.log` si no existía. Borrar el ZIP de la tableta. La entrega no escribe en la bitácora.

---

### HP-AUD-12 · OPS · Bitácora: Comportamiento, Integridad, Accesos del técnico y Errores

**Objetivo.** El Administrador recorre la bitácora en OPS (tabla, filtros, detalle, semáforo, «Verificar ahora») sin ningún botón para editar o borrar.

**Requisitos que demuestra.** PAN-240 · 019-05 · 019-04 · BR-131 · 019-10 · VER-01 · NFR-036.

**Precondiciones.** HP-AUD-02, 03 y 10. OPS con sesión de QA-ADMIN-A. **Datos / actor.** QA-ADMIN-A en OPS.

**Pasos.**

1. Hexágono **«Historial»**: título **«Bitácora de auditoría»** y cinco pestañas: **«Comportamiento»**, **«Integridad»**, **«Exportaciones»**, **«Accesos del técnico»**, **«Errores»**.
2. **«Comportamiento»**: módulo **«Dispositivos»**, acción **«Equipo bloqueado»**, resultado **«Correcto»**; **«Limpiar»**. Tocar la fila del bloqueo de HP-AUD-02 → **«Ver operación completa»** → chip **«Operación … ✕»**.
3. **«Integridad»**: leer semáforo, barra y tramos; **«Verificar ahora»**.
4. **«Accesos del técnico»**: leer el indicador. **«Errores»**: app **«backend»**, canal **«auditoria»**; tocar una fila.
5. `Api GET '/api/auditoria/estado/'` y `Api GET "/api/auditoria/asientos/?accion=auditoria.consulta_realizada&actor=$A_ID&limite=5"`.

**Resultado esperado.**

* Resumen «N asientos · del más reciente al más antiguo · … enmascarados (BR-131)»; filas con hora, actor, acción, objeto, chip **Correcto / Denegado / Fallido** y aparato; el filtro deja la fila de HP-AUD-02.
* Detalle: «Valor anterior» `{ "bloqueado": false }`, «Valor nuevo» `{ "bloqueado": true, "motivo": "desde Dispositivos del aula" }`, origen, dispositivo, secuencia, correlación y huellas completas; «Ver operación completa» deja sólo esa correlación. Nada ofrece editar o borrar.
* Integridad: tarjeta verde **«Cadena verificada»** con cabeza, huella y total de asientos; barra «x.x MB de 100.0 MB (y.y %)…»; «Tramo D – H» **«Verificada»**; tras **«Verificar ahora»**: **«Verificación terminada: N asientos comprobados»**.
* Accesos del técnico: tarjeta verde **«Sin acceso a datos personales en el periodo»**. Errores: «happy N · sad N · bad N · T líneas, se muestran las últimas 80».
* API: cabeza y total coinciden con la pantalla; cada carga de lista deja un `auditoria.consulta_realizada` con `dispositivo_id = $DISP_OPS`, y «Verificar ahora» un `auditoria.cadena_verificada`.

**Evidencia a guardar.** Capturas de cada pestaña y del detalle; salida del paso 5.

**Efectos colaterales / limpieza.** Asientos `auditoria.consulta_realizada` y `auditoria.cadena_verificada`.

---

### HP-AUD-13 · OPS · Exportaciones: autorización de salida (PAN-241), exportar y descargar

**Objetivo.** Flujo completo en OPS: otra persona de administración concede la autorización en el mismo equipo, el Administrador exporta un tramo y descarga el archivo firmado.

**Requisitos que demuestra.** PAN-240 · PAN-241 · 019-06 · FUN-200 · BR-105 · ESC-03 · MSG-052 · MSG-054.

**Precondiciones.** HP-AUD-15 ejecutada (el tramo activo sólo tiene asientos de prueba) **o** autorización del responsable de datos para exportar el tramo entero; si no, N/E. QA-ADMIN-B presente. OPS con sesión de A. **Datos / actor.** A exporta; B concede.

**Pasos.**

1. `$S0 = (Api GET '/api/auditoria/estado/').cabeza.secuencia`. Pestaña **«Exportaciones»**.
2. **«Autorizar esta salida»** → en **«Quien autoriza»**, B escribe su documento y su clave, elige **«Inspección interna»** y toca **«Conceder 30 minutos»**.
3. «Elige el tramo» → el tramo activo; «Motivo de la exportación» → **«Inspección interna»**; **«Exportar»**. Luego, en la fila nueva de «Exportaciones realizadas», **«Descargar»**.
4. ```powershell
   VerArchivo "$env:USERPROFILE\Downloads\avacom-auditoria\exportacion-<ID>.jsonl"
   Api GET "/api/auditoria/asientos/?despues=$S0&limite=50"
   ```

**Resultado esperado.**

* Paso 1: tarjeta ámbar **«Exportar exige una autorización de salida»** («… No existe la autoconcesión.») y «Exportar» deshabilitado.
* Paso 2: «Autorización concedida hasta las HH:mm. Se registra todo lo que hagas con ella (MSG-052).» y tarjeta verde **«Autorización de salida vigente»**; B no queda con sesión abierta.
* Paso 3: tarjeta verde **«Queda registrado que exportaste tramo D-H.»** (MSG-054) y la autorización vuelve a ámbar; la fila muestra el chip **«Firmado»** y, al descargar, «Guardado en C:\Users\<usuario>\Downloads\avacom-auditoria\exportacion-<id>.jsonl».
* Paso 4: `RESULTADO: OK`; asientos nuevos: `identidad.sesion.abierta` e `identidad.sesion.cerrada` de B, `identidad.escalada.concedida` (actor B, `permiso = "audit.export"`), `auditoria.tramo_exportado` (A) y `acceso.escalada.consumida`.

**Evidencia a guardar.** Capturas de cada tarjeta, salida del paso 4 y el archivo (acceso restringido).

**Efectos colaterales / limpieza.** Borrar la copia de `Downloads\avacom-auditoria\`; el archivo del nodo queda en `Logs\auditoria\exportaciones\`.

---

### HP-AUD-14 · OPS · Estado del equipo (Técnico) y Errores

**Objetivo.** El técnico diagnostica el nodo y su equipo sin ver datos de alumnos ni la bitácora, entrega los logs pendientes y exporta un diagnóstico.

**Requisitos que demuestra.** PAN-242 · 019-10 · BR-097 · Objetivo secundario 1 · D-4 y D-7 de `frontend.md`.

**Precondiciones.** HP-AUD-10. **Datos / actor.** QA-TECNICO en OPS.

**Pasos.**

1. En el tablero, **«↪ Cerrar sesión»**; entrar con QA-TECNICO; hexágono **«Historial»**.
2. En **«Estado del equipo»**: **«Entregar logs ahora»** y **«Exportar diagnóstico»**. En **«Errores»**: app **«backend»**, canal **«auditoria»**.
3. `Expand-Archive "$env:USERPROFILE\Downloads\avacom-auditoria\diagnostico-ops-<yyyyMMdd-HHmmss>.zip" "$EVID\diagnostico-ops" -Force; Get-Content "$EVID\diagnostico-ops\diagnostico.json" -Encoding UTF8`.
4. (Opcional) Cerrar sesión y entrar con QA-PROFESOR.

**Resultado esperado.**

* Título **«Diagnóstico del nodo y de los equipos»** y **sólo dos pestañas**, **«Estado del equipo»** y **«Errores»** (no «Comportamiento», «Integridad», «Exportaciones» ni «Accesos del técnico»).
* «Estado del equipo»: **«Nodo en servicio»**; «Este equipo» con «Identificado ante el nodo como <`$DISP_OPS`>», espacio libre, carpeta de logs y «Logs pendientes de entregar al nodo: N»; «Últimos avisos de este equipo» (hasta 20 líneas WARNING+ o «Sin avisos en este equipo»).
* «Entregados N renglones.» (o «No había nada pendiente o el nodo no contestó.») y «Diagnóstico guardado en C:\Users\<usuario>\Downloads\avacom-auditoria\diagnostico-ops-<yyyyMMdd-HHmmss>.zip», con `diagnostico.json` (`app = "ops"`, `dispositivo_id = $DISP_OPS`, `rol = "TECHNICIAN"`).
* «Errores»: filas con hora, nivel, canal, app, mensaje y chip de ruta, sin nombres ni documentos. Paso 4: el tablero de QA-PROFESOR **no** muestra «Historial».

**Evidencia a guardar.** Capturas de las dos pestañas y del tablero del profesor; `diagnostico.json`.

**Efectos colaterales / limpieza.** Borrar el ZIP de `Downloads`. Cerrar la sesión de OPS al terminar.

---

### HP-AUD-15 · Temporizador del nodo y rotación por tamaño

**Objetivo.** Con un umbral de prueba, el temporizador verifica la cadena y rota el tramo: el viejo se archiva firmado, sus filas siguen en la tabla y la cadena continúa enlazada. Después se restituye la configuración.

**Requisitos que demuestra.** 019-07 · FUN-201 · INV-027 · 019-04 (estado `rotada`).

**Precondiciones.** HP-AUD-03 y 07; **fuera de clase** y con P-6 cumplido. Sin líneas `auditoria.temporizador` a los 3 minutos, el servidor no es Daphne: FALLA. **Datos / actor.** Operador con PowerShell elevada (el reinicio interrumpe un instante a OPS y a las tabletas).

**Pasos.**

1. Umbral de prueba (los MB enteros que el tramo activo ya alcanza; `0` si pesa menos de 1 MB), respaldo, cambio y reinicio:
   ```powershell
   $e0 = Api GET '/api/auditoria/estado/'; $mb = [int][math]::Floor($e0.tamano_bytes / 1MB); "tamano_bytes=$($e0.tamano_bytes) umbral de prueba=$mb MB"
   $CFG = "$DATOS\Config\backend.env"; Copy-Item $CFG "$CFG.antes-HP-AUD-15"
   Add-Content -Path $CFG -Value "`nAVACOM_LMS_AUDITORIA_UMBRAL_MB=$mb" -Encoding ascii
   Restart-Service AVACOMOPSBackend
   do { Start-Sleep 3; $ok = try { (Api GET '/health/' -Token '').status -eq 'ok' } catch { $false } } until ($ok)
   ```
2. Esperar el primer tick (a los 60 s del arranque) y leer los tramos (si hay uno solo, repetir cada 30 s hasta 5 min; con `401`, identificarse de nuevo como en HP-AUD-01):
   ```powershell
   Start-Sleep 90; $t1 = (Api GET '/api/auditoria/tramos/').tramos
   $t1 | Select-Object desde, hasta, estado, abierta, asientos, rotado_en, archivo | Format-Table -AutoSize
   ```
3. Comprobaciones:
   ```powershell
   $viejo = $t1 | Where-Object { $_.estado -eq 'rotada' } | Sort-Object desde | Select-Object -Last 1; $nuevo = $t1 | Where-Object { $_.abierta }
   $ult = Api GET "/api/auditoria/asientos/$($viejo.hasta)/"; $prim = Api GET "/api/auditoria/asientos/$($nuevo.desde)/"
   "enlace=" + ($prim.huella_previa -eq $ult.huella) + " primero=" + $prim.accion
   "filas intactas=" + ((Api GET "/api/auditoria/asientos/?tramo=$($viejo.id)&limite=1").total -eq $viejo.asientos)
   VerArchivo $viejo.archivo; Api POST '/api/auditoria/verificar/' @{ todos = $true }
   VerLogs --archivo backend-auditoria --evento auditoria.bitacora_rotada --detalle; VerLogs --archivo backend-auditoria --evento auditoria.temporizador
   ```
4. Restituir y reiniciar:
   ```powershell
   Copy-Item "$CFG.antes-HP-AUD-15" $CFG -Force; Remove-Item "$CFG.antes-HP-AUD-15"; Restart-Service AVACOMOPSBackend
   do { Start-Sleep 3; $ok = try { (Api GET '/health/' -Token '').status -eq 'ok' } catch { $false } } until ($ok)
   (Api GET '/api/auditoria/estado/').umbral_bytes
   ```

**Resultado esperado.**

* Paso 2: **dos** tramos. El viejo: `estado = "rotada"`, `abierta = false`, `rotado_en` no nulo, `archivo = "C:\ProgramData\AVACOM\OPS Master\Logs\auditoria\tramo-<desde>-<hasta>.jsonl"`. El nuevo: `abierta = true`, `desde = viejo.hasta + 1`.
* Paso 3: `enlace=True` y `primero=auditoria.bitacora_rotada` (`actor.tipo = "sistema"`, `origen = "sistema"`, `valor_nuevo.motivo = "umbral_tamano"`); `filas intactas=True`; `VerArchivo` → `RESULTADO: OK`; `verificar` con `todos` → `verificada` con **dos** entradas en `tramos[]` (el viejo sigue `rotada`); el log trae «Bitácora rotada: tramo D-H → tramo-D-H.jsonl» y el temporizador «verificar la cadena: verificada» y «rotar por tamaño: ok»; el último asiento del tramo viejo es el `auditoria.cadena_verificada` (actor `sistema`) que el mismo tick escribió antes de rotar.
* Paso 4: `umbral_bytes = 104857600`; tras 2 minutos sigue habiendo dos tramos.

**Evidencia a guardar.** Salidas de los pasos 1 a 4 y `tramo-D-H.jsonl` (acceso restringido).

**Efectos colaterales / limpieza.** La bitácora queda **para siempre** con un tramo más y el archivo en `Logs\auditoria\`. Con `$mb = 0` el nodo rotaría en cada tick horario hasta restituir la configuración: no demorar el paso 4. `backend.env` queda como estaba.

---

### HP-AUD-16 · Evaluaciones en la bitácora (lectura)

**Objetivo.** Las acciones de evaluación de MOD-010 quedaron asentadas con su estructura y sus valores sensibles enmascarados.

**Requisitos que demuestra.** Objetivo secundario 4 · DEC-022 · AC-054 · BR-099 · BR-131.

**Precondiciones.** Se ejecutó el plan de MOD-010 ([`../06-evaluation-delivery/testing.md`](../06-evaluation-delivery/testing.md)), al menos HP-EVA-01 a 04; para AC-054, que se haya **cambiado un puntaje ya asentado** de una pregunta de corrección manual (sólo así se asienta `calificacion.modificada`). **Datos / actor.** QA-ADMIN-A.

**Pasos.**

1. `(Api GET '/api/auditoria/asientos/?modulo=evaluacion&limite=100').asientos | Select-Object secuencia, accion, sensible, enmascarado | Format-Table -AutoSize`.
2. `Api GET '/api/auditoria/asientos/?accion=calificacion.modificada'`; con la escalada de `audit.read` de HP-AUD-06 (su paso 2), repetirlo y revocarla (su paso 4).

**Resultado esperado.**

* Paso 1: según los casos ejecutados, `evaluacion.asignada` (`objeto.tabla = "m10_asignacion"`), `evaluacion.iniciada` (`m10_intento_formal`, actor = el alumno), `evaluacion.enviada` y las demás `evaluacion.*`, con actor, objeto y `etiqueta`; las sensibles (`evaluacion.intento.calificado`, `evaluacion.anulada`, `calificacion.*`) salen con `enmascarado = true`.
* Paso 2: si hubo cambio de puntaje, `calificacion.modificada` con `motivo`, `valor_anterior = { pregunta_ref, puntaje }` y `valor_nuevo = { pregunta_ref, puntaje }`: enmascarados sin escalada y visibles con ella, con el autor en `actor.usuario_id` (DEC-022).

**Evidencia a guardar.** Salidas de los pasos 1 y 2 (puntajes visibles sólo si son de prueba).

**Efectos colaterales / limpieza.** Revocar la escalada.

---

## 6 · Orden de ejecución y dependencias

| Orden | Casos | Depende de |
|---|---|---|
| 1 | HP-AUD-01 | P-1 a P-5 |
| 2 | HP-AUD-02 → 03 → 04 → 05 | 01 (OPS ya en el tablero); 04 y 05 usan los asientos de 02 |
| 3 | HP-AUD-08 | 02 (tableta desbloqueada); QA-PROFESOR |
| 4 | HP-AUD-06 | un asiento sensible (p. ej. el de 08); QA-ADMIN-B |
| 5 | HP-AUD-10 | 03 y 05; QA-TECNICO |
| 6 | HP-AUD-11 | 08 (tableta registrada); sin clase abierta |
| 7 | HP-AUD-07 | 03; QA-ADMIN-B |
| 8 | HP-AUD-09 | 02 a 08 y 11 |
| 9 | HP-AUD-15 | 03 y 07; **fuera de clase**; reinicia el servicio |
| 10 | HP-AUD-13 | 15 (tramo activo sólo de prueba) |
| 11 | HP-AUD-12 | 02, 03, 10 (OPS con QA-ADMIN-A) |
| 12 | HP-AUD-14 | 10 (OPS con QA-TECNICO: lo último en OPS) |
| 13 | HP-AUD-16 | plan de MOD-010 ejecutado; 06 para ver valores |

---

## 7 · Registro de ejecución

| HP | Fecha | Ejecutor | Resultado (OK/FALLA) | Evidencia (ruta) | Observaciones |
|---|---|---|---|---|---|
| HP-AUD-01 | | | | | |
| HP-AUD-02 | | | | | |
| HP-AUD-03 | | | | | |
| HP-AUD-04 | | | | | |
| HP-AUD-05 | | | | | |
| HP-AUD-06 | | | | | |
| HP-AUD-07 | | | | | |
| HP-AUD-08 | | | | | |
| HP-AUD-09 | | | | | |
| HP-AUD-10 | | | | | |
| HP-AUD-11 | | | | | |
| HP-AUD-12 | | | | | |
| HP-AUD-13 | | | | | |
| HP-AUD-14 | | | | | |
| HP-AUD-15 | | | | | |
| HP-AUD-16 | | | | | |

---

## 8 · Fuera de alcance

* **Caminos tristes y malos**: 401/403/405 y su asiento de denegación (`acceso.denegado`, `aula.denegado`), exportar sin autorización (TST-072, VER-04), el técnico que abre evidencia (AC-003), editar o borrar un asiento (AC-081), exportar o rotar con salto (409), acción fuera del catálogo, entregas de logs sin equipo o sobre los topes. Los cubren `backend/audit/tests/` (71 pruebas según `backend.md`) y `tests/Avacom.Lms.Core.Tests/{AuditoriaTests,AutorizacionDeSalidaTests}.cs`.
* **Detectar un salto** (FUN-199, NFR-036) exige alterar la bitácora (`tools/romper_cadena.py`), que **nunca** se ejecuta en un nodo instalado; tampoco se provocan la falla de escritura, la concurrencia ni la restauración de un respaldo (Q-7).
* **Sin camino feliz o sin punto de llamada**: `aula.nivel.excepcion`, `auditoria.violacion_inv003` (INV-003), `acceso.escalada.vencida`, `auditoria.restauracion_registrada`, `dispositivos.borrado_remoto`, los `estudio.*` y el vencimiento de la autorización (MSG-053). **Pendientes de otros módulos o versiones**: derivar de la cola (019-09, MOD-015) y comprobar los eventos de `m19_evento_salida` (4 de 5 se publican; sólo se ven por SQL), retención de 5 años y anonimización (CAP-117, BR-098, V1), firma asimétrica para terceros (Q-2).
* **Carga y rendimiento** (cadenas muy largas, rotación real a 100 MB, 50 tabletas entregando logs) y **pruebas destructivas** (borrar o editar la base, `backend.env` o los logs; leer el almacenamiento privado de Student en Android).
