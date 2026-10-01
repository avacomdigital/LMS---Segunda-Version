# 04 · Modo Estudio (MOD-008) · Pruebas técnicas en producción (happy paths)

| Campo | Valor |
|---|---|
| Módulo | **MOD-008 · Modo Estudio**: backend `backend/modo_estudio/` (tablas `m08_*`, rutas `/api/modo-estudio/`), Student «Modo estudio · Mis lecciones», OPS «Modo de estudio» y «Dispositivos» |
| Tipo de documento | Plan de pruebas técnicas — spec driven dev |
| Alcance | Sólo happy paths: 17 casos, HP-EST-01…17 (lo demás, en §8) |
| Quién ejecuta | Operador/QA con acceso al nodo instalado, a OPS, a AVACOM Contenido y a tabletas reales (Windows y Android) |
| Fuentes | `01-introduccion.md`, `02-modelo-y-api.md`, `03-frontend-student-y-ops.md` (esta carpeta); `backend/modo_estudio/**`; `backend/device_manager/{interfaces,aplicacion}/**`; `backend/avacom_lms/settings.py`; `backend/README.md`; `src/Avacom.Lms.Student/ModoEstudio/**` y `Pages/StudentMenuPage.xaml(.cs)`; `src/Avacom.Lms.Core/Estudio/*.cs`, `Services/EstudioApi.cs`; `src/Avacom.Lms.Ui/Controls/PracticaEstudioView.cs`; `src/Avacom.Lms.Ops/Pages/{Estudio*,Dispositivos*,Dashboard*}`; `installer/src/host/{Rutas,Configuracion}.cs` |
| Fecha | 2026-10-01 |
| Estado | Borrador para ejecución |

---

## 1 · Propósito y alcance

Este plan describe las pruebas que un operador ejecuta **en el nodo instalado** para comprobar que MOD-008 hace lo prometido cuando todo sale bien: la profesora asigna una lección, el alumno elige quién es, estudia en línea o con la lección descargada, practica, completa, trabaja sin red e integra sin duplicar, y la profesora lo ve y decide lo que llegó tarde. Cada HP demuestra requisitos concretos (§4) y termina en algo verificable: una pantalla, un JSON o una fila en la base.

**No demuestran:** caminos de error (§8); permisos `study.*` con sesión (§2.2); 008-09 (sin construir: D-13, Q-68); simulaciones sin red (Q-71); práctica calificada sin red (Q-67: se guarda y se califica al integrarse, como muestra HP-EST-11); verificación de identidad (Q-74: nadie verifica quién es quién, por D-15).

---

## 2 · Entorno y precondiciones

### 2.1 · Instalación esperada del nodo

| Elemento | Valor esperado | Fuente |
|---|---|---|
| Programa | Carpeta con `Backend`, `Runtime` y `App` (p. ej. `C:\Program Files\AVACOM\OPS Master`) | `Rutas.cs` (ruta real: por confirmar en producción) |
| Estado | `C:\ProgramData\AVACOM\OPS Master\` con `Config\backend.env`, `Data\ops-master.sqlite3`, `Logs\`, `Respaldos\` | `Rutas.cs` |
| Servicio | `AVACOMOPSBackend` en marcha, escuchando `0.0.0.0:8000` (`AVACOM_OPS_BACKEND_PORT`) | `Configuracion.cs` |
| Organización | Instalada: `GET /health/` → `acceso.instalado = true` (si no, `estado` dice `nodo_no_instalado` y las rutas del profesor contestan 409) | `expediente/views.py` |
| Migraciones | `acceso` 0007, `device_manager` 0004 y `modo_estudio` 0001 aplicadas | 02 §12 (cómo las aplica el instalador al actualizar: por confirmar) |

### 2.2 · Variables de entorno relevantes

Se leen de `Config\backend.env`; si la línea no existe rige el valor por defecto.

| Variable | Defecto | Efecto en estas pruebas |
|---|---|---|
| `AVACOM_ESTUDIO_VIGENCIA_DIAS` | 14 | Vigencia de un paquete sin fecha límite, o con la fecha ya vencida (HP-EST-13) |
| `AVACOM_ESTUDIO_GRACIA_MIN` | 15 | Gracia por defecto de una asignación nueva (900 000 ms) |
| `AVACOM_ESTUDIO_MEDIO_MAX_MB` | 512 | Un medio mayor queda fuera del paquete (`no_incluidos`) |
| `AVACOM_LMS_EXIGIR_SESION` | 0 | Con 0 no se exige JWT ni se evalúan los permisos `study.*` (Q-34). **Este plan asume 0** (`GET /api/acceso/configuracion/` → `sesion_obligatoria`). Con 1 se manda `Authorization: Bearer <TOKEN>` (lo admite el helper) y cada rol necesita el suyo (por confirmar) |
| `AVACOM_AULA_FUENTE_CURSOS` · `AVACOM_AULA_PERMITIR_EJEMPLO` | `biblioteca` · 0 | Los cursos salen sólo de AVACOM Contenido |
| Student: `AVACOM_ESTUDIO_DEMO` y preferencia `estudio_demo` | sin definir | **Deben estar apagadas**: encendidas, Student muestra datos de muestra (chip «DEMOSTRACIÓN») y no habla con el nodo |

### 2.3 · AVACOM Contenido y la lección de prueba

AVACOM Contenido abierto, con al menos un curso instalado y sin marca `no_disponible` (OPS lo muestra apagado). La **lección de prueba** (`$LECCION`) debe tener:

- Al menos 3 láminas o páginas (`lecture`/`explanation`) y **una** práctica (`activity`) con 3 o más preguntas autocalificables: N ≥ 4 actividades.
- Al menos un medio que no sea simulación (imagen, audio, pdf o video); sin medios no hay nada que verificar con `Range` (y si baja demasiado rápido para pausar, ese paso de HP-EST-09 es «no aplicable»).
- **Sin laboratorio** (`simulation_lab`): no se descarga (Q-71) e impediría completar sin red (HP-EST-11). Un examen (`exam`) es bienvenido: sale como tarjeta informativa «EVALUACIÓN».
- No ser sólo examen: OPS no la deja asignar.

### 2.4 · Datos semilla (prefijo `PRUEBA-`)

Los crea la administración (p. ej. con `manage.py acceso_importar`, README del backend; procedimiento real: por confirmar). Este plan no los crea.

| Dato | Valor |
|---|---|
| Grupo | `PRUEBA-Grupo`, activo, con el profesor de la prueba como `DOCENTE` |
| Alumnos activos del grupo | `PRUEBA-Ana`, `PRUEBA-Beto`, `PRUEBA-Carla` (alias **sin espacios**: «Continuar como …» usa el primer nombre) |

### 2.5 · Tabletas

| Clave | Qué es |
|---|---|
| **T-A** | Se asignará a PRUEBA-Ana en HP-EST-02. Primera pasada: Windows |
| **T-C** | Compartida, nunca se asigna. Primera pasada: Android |

Ambas con Student instalada, sin modo demostración, ≥ 500 MB libres, Wi-Fi que se pueda apagar, nodo alcanzable en `http://<NODO>:8000` y sin alumnos reales usándolas. Student en Android compila pero **no se había probado en una tableta** (03 §8): todo hallazgo propio se anota con `[AND]`. Segunda pasada recomendada: intercambiar plataformas y repetir HP-EST-02, 09, 11 y 17 (tocan el almacén cifrado: DPAPI en Windows, `SecureStorage` en Android).

### 2.6 · Equipo del operador

PC con **Windows PowerShell 5.1** (sintaxis verificada para esa versión) y `curl.exe`, con acceso HTTP al nodo. OPS corre en el nodo principal, que no tiene teclado: **en OPS todo es tocar**; lo que se escribe, se escribe en el PC del operador. Opcionales: Python 3 (`<PYTHON>`; el del nodo es `<RAÍZ>\Runtime\Python\python.exe`) para `huella.py`, y `sqlite3.exe` con lectura de la base (si puede abrirla con el servicio en marcha: por confirmar).

### 2.7 · Variables de trabajo (pegar al empezar cada sesión)

```powershell
$NODO  = 'http://<NODO>:8000'
$TOKEN = ''                                     # sólo si el nodo exige sesión (Authorization: Bearer <TOKEN>)
$EVID  = "$HOME\Evidencia-MOD008\2026-10-01"; New-Item -ItemType Directory -Force $EVID | Out-Null
$HA = '<HUELLA_T_A>'; $HAq = [uri]::EscapeDataString($HA)   # identificador_hw de T-A (se llena en HP-EST-01)
$HC = '<HUELLA_T_C>'; $HCq = [uri]::EscapeDataString($HC)   # ... de T-C
$GRUPO = '<ID_GRUPO>'; $ANA = '<ID_ANA>'; $BETO = '<ID_BETO>'; $CARLA = '<ID_CARLA>'
$CURSO = '<CURSO_REF>'; $LECCION = '<LECCION_REF>'
$A1 = $A2 = $A3 = $A4 = $A5 = $A6 = $null       # ids de asignación (HP-EST-03, 12, 13 y 14)
$DB = 'C:\ProgramData\AVACOM\OPS Master\Data\ops-master.sqlite3'   # opcional

function Llamar([string]$Metodo, [string]$Ruta, $Cuerpo = $null) {
    $p = @{ Method = $Metodo; Uri = "$NODO$Ruta"; UseBasicParsing = $true }
    if ($TOKEN) { $p.Headers = @{ Authorization = "Bearer $TOKEN" } }
    if ($null -ne $Cuerpo) {
        $p.ContentType = 'application/json; charset=utf-8'
        $p.Body = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Cuerpo -Depth 10 -Compress))
    }
    $r = Invoke-WebRequest @p
    $texto = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
    [pscustomobject]@{ Estado = [int]$r.StatusCode; Cuerpo = $(if ($texto.Trim()) { $texto | ConvertFrom-Json } else { $null }) }
}
function Guardar($Objeto, [string]$Nombre) {
    ConvertTo-Json -InputObject $Objeto -Depth 12 | Set-Content -Encoding UTF8 -Path (Join-Path $EVID $Nombre)
}
function Ahora { (Llamar GET "/api/modo-estudio/estado/?dispositivo=$HAq").Cuerpo.servidor_en }   # hora del NODO, en ms
function Eventos([long]$Desde, [string]$Tipo = '%') {      # outbox de MOD-008 (opcional, sólo lectura)
    sqlite3.exe -readonly $DB "SELECT id, tipo_evento, agregado_id, creado_en, carga FROM m08_evento_salida WHERE creado_en >= $Desde AND tipo_evento LIKE '$Tipo' ORDER BY id;"
}
function Libro([string]$Alumno) {                          # libro de sincronización (opcional)
    sqlite3.exe -readonly $DB "SELECT emisor_id, secuencia, tipo, estado, motivo FROM m08_sincronizacion WHERE alumno_id = '$Alumno' ORDER BY id DESC LIMIT 20;"
}
```

`huella.py` (guardarlo en la carpeta de trabajo) recalcula la huella de un manifiesto como lo hace el nodo, SHA-256 del JSON canónico sin el campo `huella`:

```python
import hashlib, json, sys, urllib.request

manifiesto = json.load(urllib.request.urlopen(sys.argv[1]))
declarada = manifiesto.pop("huella")
canonico = json.dumps(manifiesto, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
calculada = hashlib.sha256(canonico).hexdigest()
print("COINCIDE" if calculada == declarada else "NO COINCIDE", declarada, calculada)
```

### 2.8 · Antes de ejecutar cualquier HP

1. `Config\backend.env` revisado (sólo lectura): `AVACOM_LMS_EXIGIR_SESION` no vale 1 y las `AVACOM_ESTUDIO_*` están en lo esperado.
2. AVACOM Contenido abierto y lección de §2.3 identificada.
3. Datos de §2.4 existentes (se confirma en HP-EST-01).
4. T-A y T-C con el acceso de Student hecho: «Conéctate a tu aula» → «Dirección del aula» `http://<NODO>:8000` → «Comprobar conexión» → «Entrar al aula» (nombre cualquiera, p. ej. `PRUEBA-Tableta`).
5. OPS abierto en el Menú principal, conectado al nodo (no en modo demostración).
6. Variables de §2.7 pegadas.

---

## 3 · Convenciones

**Identificación.** `HP-EST-NN`. Cada caso trae siempre: Objetivo, Requisitos que demuestra, Precondiciones, Datos / actor, Pasos, Resultado esperado, Evidencia a guardar, Efectos colaterales / limpieza. Los botones van entre «comillas angulares», tal como se leen en la UI. `Llamar` devuelve `Estado` (HTTP) y `Cuerpo` (JSON).

**Evidencia** es lo que permite a otra persona decidir sin repetir la prueba: capturas con la hora visible, JSON guardado con `Guardar` y, opcionalmente, filas de `Eventos`/`Libro`. Se guarda en `$EVID\HP-EST-NN\` como `HP-EST-NN_pPP_descripcion.ext` (PP = paso). Nunca un token ni nombres de alumnos reales.

**Criterio global.** Un HP es **OK** si todo su «Resultado esperado» se cumple y Student nunca muestra códigos ni mensajes técnicos. Es **FALLA** si algo no se cumple o no se pudo ejecutar (Observaciones: «no ejecutado: causa»). Se anota la plataforma de cada ejecución.

**Cómo anotar.** En §7, una fila por HP: fecha, ejecutor, OK/FALLA, ruta de evidencia y observaciones (cronómetros, desviaciones, `[AND]`). Una falla lleva paso, lo esperado, lo observado y captura.

**Seguridad en producción.**
1. Todo lo creado lleva `PRUEBA-` (grupo, alumnos y títulos de las asignaciones creadas por API). Las creadas desde OPS heredan el título de la lección (no hay teclado): se reconocen por el grupo, la consigna y el `id`, que se anota.
2. No se toca ningún grupo, alumno ni asignación reales. OPS y «¿Quién eres?» mostrarán también los grupos reales con lecciones abiertas: no se elige ningún nombre real.
3. T-A y T-C son de prueba y están fuera de clase; T-A vuelve a «compartida» en HP-EST-17.
4. Sólo lecturas sobre `Config`, `Data` y `Logs`; no se reinicia el servicio ni se edita `backend.env`. No se borra nada (CV-05): las asignaciones se **cierran** al final (§6) y los datos `PRUEBA-` permanecen.
5. La hora que cuenta es la del **nodo** (`servidor_en`), no la del PC ni la de las tabletas (BR-062).

**Asignaciones de prueba.**

| Clave | Cómo se crea | Para quién | Fecha límite · plazo | Se usa en |
|---|---|---|---|---|
| A1 | OPS · «Todo el grupo» · consigna «Lee con calma y haz la práctica al final.» | PRUEBA-Grupo | En 1 semana · Flexible | 03, 05–08, 10, 16 |
| A2 | OPS · «Elegir alumnos» · consigna «Termina todas las actividades.» | PRUEBA-Beto | En 3 días · Flexible | 03, 05, 10, 15 |
| A3 | OPS · «Elegir alumnos» · consigna «Haz la práctica dos veces.» | PRUEBA-Ana | En 2 semanas · Flexible | 03, 05, 09, 11, 17 |
| A4 | API · título `PRUEBA-A4 vigencia` | PRUEBA-Ana | ahora + 5 min · Flexible · gracia 1 min | 13, 17 |
| A5 | API · título `PRUEBA-A5 estricto` | PRUEBA-Ana | ahora + 8 min · Estricto · gracia 1 min | 14 |
| A6 | API · título `PRUEBA-A6 idempotencia` | PRUEBA-Carla | sin fecha · Flexible | 12, 16 |

---

## 4 · Matriz de trazabilidad

| Requisito (documentos de la carpeta) | HP |
|---|---|
| 008-01 · modo de estudio en cualquier tableta; paquete sólo para el dueño de una asignada (BR-054, DEC-013, D-1, D-2, D-15) | 01, 02, 09, 10, 17 |
| 008-02 · asignar con fecha límite a un alumno o al grupo (CAP-050/051, DEC-014, DEC-019) | 03, 05, 14 |
| 008-03 · paquete de estudio (CAP-047, D-7, D-8, MSG-045) | 09, 13, 17 |
| 008-04 · abrir y completar por bloques (FUN-081/082/087/088, D-4, PAN-124/130) | 05, 06, 08 |
| 008-05 · práctica separada de la evaluación (FUN-083, BR-055, NFR-012, D-5, DEC-032, BR-127) | 07 |
| 008-06 · trabajo sin red sin duplicar (CAP-048, FUN-086, BR-059/060/137/138, INV-013, D-6, D-10, D-11, MSG-011, CMP-002, TST-029) | 06, 11, 12, 14 |
| 008-07 · cerrar sesión y limpiar el aparato (BR-053, FUN-089/090, TST-028, JRN-022) | 16 |
| 008-08 · eventos `estudio.*` (consulta opcional del outbox) · permisos `study.*`: **sin HP** (§8) | 03, 07–09, 15, 16 |
| 008-09 · alcance por nivel y «Mi trabajo»: **sin HP**, no construido (D-13, Q-68) | — |
| FUN-080 · abrir sesión de estudio · D-3 | 01, 04 |
| FUN-084 · descargar · FUN-085 · denegar · PAN-133 · MSG-046 · JRN-007 | 09, 10 |
| FUN-092 · asignar tableta · FUN-093 · liberarla (D-14) | 02, 17 |
| CAP-050 · asignar · CAP-051 · quién completó y cerrar · PAN-131 | 03, 08, 14, 15 |
| BR-074 · D-9 · BR-062 · lo tardío lo decide el profesor, con hora del nodo | 14 |
| TST-079 · recorrido completo del Maestro | 03 → 08, 09, 11, 14 |
| D-12, Q-66…Q-74 · decisiones y preguntas abiertas | sin HP propio (§1, §8) |

---

## 5 · Happy paths

### HP-EST-01 · Nodo, biblioteca y tabletas listos para estudiar

**Objetivo.** Comprobar, sin cambiar nada, que el nodo está instalado, la biblioteca sirve cursos y las tabletas se dan de alta solas, quedan utilizables y ven el hexágono «Modo de estudio».

**Requisitos que demuestra.** 008-01 (con D-1/D-15), FUN-080.

**Precondiciones.** §2.8 completo.

**Datos / actor.** Operador; T-A y T-C; PRUEBA-Grupo.

**Pasos.**
1. `$r = Llamar GET '/health/'; Guardar $r.Cuerpo 'HP-EST-01_p01_health.json'; $r.Estado, $r.Cuerpo.status, $r.Cuerpo.biblioteca.disponible, $r.Cuerpo.acceso.instalado`
2. `$r = Llamar GET '/api/aula/fuente/'; $r.Cuerpo.disponible; $r.Cuerpo.cursos_instalados | Select curso_ref, version, titulo`. Elegir un curso: `$CURSO = '<curso_ref>'`.
3. `$c = (Llamar GET "/api/aula/cursos/$CURSO/").Cuerpo; $c.lecciones | Select leccion_ref, titulo, @{n='objetos';e={$_.objetos.tipo -join ','}}`. Elegir la que cumpla §2.3: `$LECCION = '<leccion_ref>'`.
4. En T-A y T-C: Student → menú principal → hexágono «Modo de estudio». Cerrar con la «X» circular.
5. `(Llamar GET '/api/dispositivos/').Cuerpo | Select id, identificador_hw, nombre, plataforma, activo, bloqueado, perfil, asignado_a`. Copiar el `identificador_hw` de cada tableta a `$HA` / `$HC` y recalcular `$HAq` / `$HCq`.
6. Por tableta: `$e = Llamar GET "/api/modo-estudio/estado/?dispositivo=$HAq"; Guardar $e.Cuerpo 'HP-EST-01_p06_estado-TA.json'` (y lo mismo con `$HCq`).
7. `$g = Llamar GET '/api/modo-estudio/docente/grupos/'; Guardar $g.Cuerpo 'HP-EST-01_p07_grupos.json'`. Copiar a las variables los ids del grupo y de sus tres alumnos.

**Resultado esperado.**
- Paso 1: `Estado = 200`, `status = 'ok'`, `biblioteca.disponible = True`, `acceso.instalado = True`. Paso 2: 200, `disponible = True`, ≥ 1 curso. Paso 3: 200 y la lección elegida existe.
- Paso 4: el hexágono se ve y abre sin pedir código y sin chip «DEMOSTRACIÓN»; sale «¿Quién eres?» y, sin lecciones abiertas en el nodo, el aviso «Todavía no hay lecciones asignadas para ningún grupo. Cuando tu profesor las asigne, tu nombre aparecerá aquí.» (si ya hay lecciones reales se listarán sus grupos: no tocar).
- Paso 5: ambas tabletas `activo = True`, `bloqueado = False`, `perfil = 'compartido'`, `asignado_a = null`.
- Paso 6: 200; `disponible = True`, `motivo = ''`, `perfil = 'compartido'`, `dueno = null`, `descarga_permitida = False`, `dispositivo.identificador_hw` = la huella, `servidor_en` ≈ hora actual en ms.
- Paso 7: 200, `instalado = True`; `PRUEBA-Grupo` con exactamente `PRUEBA-Ana`, `PRUEBA-Beto` y `PRUEBA-Carla`.

**Evidencia a guardar.** JSON de los pasos 1, 2, 5, 6 y 7; capturas del menú de Student con el hexágono y de «¿Quién eres?» en cada tableta.

**Efectos colaterales / limpieza.** Sólo lectura, salvo el alta de las tabletas en el inventario (queda).

---

### HP-EST-02 · Asignar una tableta a un alumno en «Dispositivos»

**Objetivo.** Que la profesora marque T-A como asignada a PRUEBA-Ana, con toques, y que el nodo lo refleje.

**Requisitos que demuestra.** 008-01, FUN-092, D-14.

**Precondiciones.** HP-EST-01 OK; T-A compartida y sin paquetes.

**Datos / actor.** Profesora/operador en OPS; T-A; PRUEBA-Ana.

**Pasos.**
1. OPS → Menú principal → hexágono «Dispositivos». En la tarjeta de T-A: «Compartida del aula · las lecciones se estudian con el aula conectada».
2. Tocar «Asignar a un alumno». Aparece «¿De quién es «…»?»; con más de un grupo, tocar el chip «PRUEBA-Grupo · 3».
3. Tocar el chip «PRUEBA-Ana». En «¿Asignar esta tableta?» tocar «Asignar».
4. `(Llamar GET '/api/dispositivos/').Cuerpo | Where-Object identificador_hw -eq $HA | Select perfil, asignado_a, sesion_abierta`
5. `Llamar GET "/api/modo-estudio/estado/?dispositivo=$HAq"`; lo mismo con `$HCq`; y `Llamar GET "/api/modo-estudio/estado/?dispositivo=$HAq&alumno_id=$BETO"`.

**Resultado esperado.**
- Paso 3: la tarjeta dice «Asignada a PRUEBA-Ana · su dueño puede llevarse las lecciones» (verde) y su botón pasa a «Devolver al aula»; el subtítulo de la página incluye «1 asignada a un alumno». T-C sigue «Compartida…».
- Paso 4: `perfil = 'asignado'`; `asignado_a.id` = `$ANA`, `asignado_a.rotulo = 'PRUEBA-Ana'`.
- Paso 5: T-A → 200, `disponible = True`, `perfil = 'asignado'`, `dueno.rotulo = 'PRUEBA-Ana'`, `descarga_permitida = True`. T-C → `perfil = 'compartido'`, `descarga_permitida = False`. T-A declarando a Beto → `alumno.rotulo = 'PRUEBA-Beto'` y `descarga_permitida = False` (sólo el dueño se lleva el paquete).

**Evidencia a guardar.** Capturas de OPS antes y después; JSON de los pasos 4 y 5.

**Efectos colaterales / limpieza.** Asignar cierra cualquier sesión de estudio abierta en T-A. T-A queda asignada hasta HP-EST-17.

---

### HP-EST-03 · Asignar una lección a todo el grupo y a alumnos elegidos

**Objetivo.** Crear desde OPS A1 (grupo), A2 (PRUEBA-Beto) y A3 (PRUEBA-Ana), con fecha límite y plazo flexible, y verlas con sus totales.

**Requisitos que demuestra.** 008-02, CAP-050, DEC-014, TST-079 (inicio), 008-08 (evento de creación).

**Precondiciones.** HP-EST-01 OK; AVACOM Contenido conectado (si no, OPS no asigna: no se asigna a ciegas).

**Datos / actor.** Profesora/operador en OPS; PRUEBA-Grupo; lección de §2.3.

**Pasos.**
1. OPS → Menú principal → hexágono «Modo de estudio» (a la derecha de «Clase de hoy») → «Asignar una lección» (o «Asignar mi primera lección»).
2. **A1.** «Para quién»: tarjeta `PRUEBA-Grupo` → chip «Todo el grupo · 3» → «Siguiente  ›». «Qué lección»: chip de materia (si hay varias) → tarjeta del curso → tarjeta de la lección → «Siguiente  ›». «Cuándo y cómo»: día «En 1 semana», hora «Final del día», plazo «Flexible», «Se puede descargar», consigna «Lee con calma y haz la práctica al final.» → revisar el «Resumen» → «Asignar la lección».
3. **A2.** Igual, con «Elegir alumnos» → chip «PRUEBA-Beto»; día «En 3 días», hora «Mediodía», consigna «Termina todas las actividades.».
4. **A3.** Igual, con «Elegir alumnos» → chip «PRUEBA-Ana»; día «En 2 semanas», consigna «Haz la práctica dos veces.».
5. «‹  Asignaciones», filtro «Abiertas».
6. `$l = (Llamar GET '/api/modo-estudio/docente/asignaciones/?estado=activa').Cuerpo.asignaciones | Where-Object grupo_rotulo -eq 'PRUEBA-Grupo' | Sort-Object fecha_limite; $l | Select id, alcance, fecha_limite, plazo, destinatarios_total, pendientes; $A2, $A1, $A3 = $l.id` (3 días, 1 semana, 2 semanas).

**Resultado esperado.**
- Tras «Asignar la lección» se abre el detalle con el aviso verde «Listo» + «Lección asignada a 3 alumnos. La verán en «Modo de estudio» al elegir su nombre.» (A2 y A3: «…a 1 alumno…»). Cabecera «ASIGNACIÓN» con el título de la lección y «<Asignatura> · <Unidad> · PRUEBA-Grupo · 3 alumnos»; píldoras «ABIERTA», «PLAZO FLEXIBLE», «SE PUEDE DESCARGAR»; «Entrega: <fecha> · 11:59 p. m.»; la consigna; totales 0 completaron · 0 en curso · 3 sin empezar (1 en A2 y A3) · 0 fuera de plazo; tabla «Quién completó» con filas «PENDIENTE» y «todavía no empieza».
- Paso 5: tres tarjetas con «0 de N completaron» y «Ver quién completó  ›».
- Paso 6: 200; A1 `alcance = 'grupo'`, A2 y A3 `'seleccion'`; las tres `plazo = 'blando'`, `estado = 'activa'`, `paquete_permitido = True`, `gracia_ms = 900000`; `destinatarios_total` 3, 1 y 1; `bloques_total` ≥ 4; `practica.total_preguntas` ≥ 3.

**Evidencia a guardar.** Capturas de los tres pasos y del detalle de A1; JSON del paso 6 (anotar `$A1`, `$A2`, `$A3`). Opcional: `Eventos <t0> 'estudio.asignacion.creada.v1'` → 3 filas.

**Efectos colaterales / limpieza.** Tres asignaciones activas; se cierran en §6 (A2 en HP-EST-15).

---

### HP-EST-04 · «¿Quién eres?»: el alumno elige su nombre, sin código

**Objetivo.** Comprobar que en cualquier tableta el alumno dice quién es tocando su nombre, sin código ni contraseña, y que el nodo abre su sesión de estudio.

**Requisitos que demuestra.** D-15, D-3, FUN-080.

**Precondiciones.** HP-EST-02 y 03 OK.

**Datos / actor.** PRUEBA-Ana en T-A; PRUEBA-Beto en T-C.

**Pasos.**
1. T-A: Student → «Modo de estudio». Observar «¿Quién eres?».
2. Tocar «Continuar como PRUEBA-Ana» (recuadro azul).
3. T-C: Student → «Modo de estudio» → chip «PRUEBA-Beto» → «Continuar como PRUEBA-Beto».
4. `(Llamar GET '/api/dispositivos/').Cuerpo | Where-Object { $_.identificador_hw -in $HA, $HC } | Select identificador_hw, perfil, sesion_abierta`
5. `Llamar GET "/api/modo-estudio/estado/?dispositivo=$HCq&alumno_id=$BETO"`

**Resultado esperado.**
- Paso 1: título «¿Quién eres?», subtítulo «Elige tu nombre para ver las lecciones que te asignó tu profesor.»; recuadro «ESTA TABLETA ES DE» · «PRUEBA-Ana» con «Continuar como PRUEBA-Ana»; «ELIGE TU NOMBRE» con «Tu profesor verá tu avance con el nombre que elijas.» y los chips de los tres alumnos («TU GRUPO» sólo con más de un grupo). **En ningún momento se pide código, contraseña ni documento.**
- Paso 2: esqueleto de carga y luego la lista; cabecera «Modo estudio» y botón «Estudias como PRUEBA-Ana  ·  Cambiar».
- Paso 3: T-C no muestra «ESTA TABLETA ES DE» ni «LA ÚLTIMA PERSONA…»; el botón dice «Elige tu nombre» (deshabilitado) hasta tocar un chip; elegir no confirma, hace falta el segundo toque. Luego «Estudias como PRUEBA-Beto  ·  Cambiar».
- Paso 4: `sesion_abierta.alumno_id` = `$ANA` en T-A y `$BETO` en T-C. En OPS «Dispositivos» cada tarjeta dice «en uso por <id>».
- Paso 5: 200; `alumno.rotulo = 'PRUEBA-Beto'`; `dueno = null`.

**Evidencia a guardar.** Capturas de «¿Quién eres?» y de la cabecera en ambas tabletas; JSON de los pasos 4 y 5.

**Efectos colaterales / limpieza.** Dos sesiones de estudio abiertas (se cierran en HP-EST-16 y 17).

---

### HP-EST-05 · «Mis lecciones»: pendientes con fecha, estado y filtros

**Objetivo.** Verificar que cada alumno ve sólo lo que le alcanza, con estado, consigna, fecha, práctica y evaluación como cosas separadas, y que los filtros cuentan bien.

**Requisitos que demuestra.** FUN-081, 008-04, PAN-124/130, PAN-131, 008-02, BR-062.

**Precondiciones.** HP-EST-04 OK.

**Datos / actor.** PRUEBA-Ana en T-A (ve A1 y A3); PRUEBA-Beto en T-C (ve A1 y A2).

**Pasos.**
1. T-A: observar «Mis lecciones»; tocar «Descargadas», «Completadas» y volver a «Pendientes».
2. Si la lección tiene examen: en la caja «EVALUACIÓN» tocar «Ver información».
3. T-C: observar la lista de PRUEBA-Beto.
4. `Llamar GET "/api/modo-estudio/asignaciones/?dispositivo=$HAq&alumno_id=$ANA"` y lo mismo con `$HCq` y `$BETO`.

**Resultado esperado.**
- T-A, «Pendientes 2 · Descargadas 0 · Completadas 0»: dos tarjetas por fecha (A1 «Entrega: <d MMM>» primero, A3 después), cada una con eyebrow `ASIGNATURA · UNIDAD` en mayúsculas, chip «○  PENDIENTE», título, la consigna como subtítulo, botón «Comenzar lección», caja «PRÁCTICA» («N preguntas · Autocalificable», «Practicar») y, si hay examen, caja «EVALUACIÓN» **sin** botón «Practicar». Pie «Guardado» y «<usado> en tu tableta · <libres> libres». Sin A2.
- «Descargadas»: «Todavía no descargas lecciones» / «Descarga una lección con conexión y podrás estudiarla aunque no estés en el aula.». «Completadas»: «Aún no completas lecciones» / «Cuando termines una, la verás aquí.».
- «Ver información»: diálogo con el título del examen y «La evaluación de la unidad la aplica tu profesor en clase o cuando él la abra. No es parte de la práctica…».
- T-C: «Pendientes 2» con A2 (más cercana) y A1; sin A3.
- Paso 4: 200; Ana `resumen = {pendientes: 2, descargadas: 0, completadas: 0}`, cada asignación con `tarea = null`, `practica.disponible = True`, `estado_asignacion = 'activa'`; en T-A `descarga.permitida = True`, en T-C `descarga = {permitida: False, motivo: 'dispositivo_compartido'}`.

**Evidencia a guardar.** Capturas de ambas listas y de cada filtro; JSON de ambas respuestas.

**Efectos colaterales / limpieza.** Ninguno.

---

### HP-EST-06 · Abrir una lección, avanzar y reanudar donde se quedó

**Objetivo.** Abrir A1 en línea, avanzar guardando el progreso (✓ / ↑ / ↻), salir y reanudar en el punto correcto; la profesora ve el avance.

**Requisitos que demuestra.** FUN-082, FUN-087, FUN-088, 008-04, D-4, D-6, CMP-002.

**Precondiciones.** HP-EST-05 OK; A1 sin tocar por Ana.

**Datos / actor.** PRUEBA-Ana en T-A; A1; OPS.

**Pasos.**
1. T-A: en la tarjeta de A1 (consigna «Lee con calma…») tocar «Comenzar lección».
2. Tocar «Siguiente» dos veces hasta «Actividad 3 de N» (tres vistas; **no** llegar a la práctica). Mirar el pie.
3. Tocar «Mis lecciones». Observar la tarjeta de A1.
4. Tocar «Continuar lección».
5. `Llamar GET "/api/modo-estudio/asignaciones/$A1/?dispositivo=$HAq&alumno_id=$ANA"`
6. OPS → «Modo de estudio» → tarjeta de A1 → «Ver quién completó  ›» (≤ 8 s o «Actualizar»).

**Resultado esperado.**
- Paso 1: botón «Mis lecciones», eyebrow, título, «Actividad 1 de N», barra, «1 de N actividades vistas» y la tira de números con la actual resaltada.
- Paso 2: «Actividad 3 de N», «3 de N actividades vistas», números 1–3 con ✓. El pie puede pasar un instante por «Sincronizando…» (↻) y queda en «Guardado» (✓); nunca un error.
- Paso 3: chip «◐  EN CURSO»; barra con `round(300/N) %` (75 % si N = 4); subtítulo «Continúa desde: Actividad 4 de N»; botón «Continuar lección».
- Paso 4: abre en la primera actividad sin ver («Actividad 4 de N») con 1–3 en ✓.
- Paso 5: 200; `tarea.estado = 'en_curso'`, `bloques_atendidos = 3`, `bloques_total = N`, `avance_pct = round(300/N, 2)`, `puede_reanudar = True`, `ultimo_bloque.indice = 3`, `abierta_en` no nulo; `bloques[0..2].atendido = True`.
- Paso 6: fila de PRUEBA-Ana «EN CURSO», «3 de N actividades · NN %», «último avance hace N min»; totales 1 en curso, 2 sin empezar.

**Evidencia a guardar.** Capturas de los pasos 1–4 y del detalle en OPS; JSON del paso 5.

**Efectos colaterales / limpieza.** El avance es monótono: volver a ver una actividad no lo baja.

---

### HP-EST-07 · Práctica autocalificable, separada de la evaluación

**Objetivo.** Practicar A1 con retroalimentación inmediata, ver «X de M correctas», repetir sin tope y reanudar un intento a medias, sin que nada se llame examen, evaluación ni nota.

**Requisitos que demuestra.** FUN-083, FUN-088, 008-05, BR-055, NFR-012, D-5, DEC-032, BR-127.

**Precondiciones.** HP-EST-06 OK; AVACOM Contenido conectado (la corrección vive allí).

**Datos / actor.** PRUEBA-Ana en T-A; A1; cronómetro.

**Pasos.**
1. T-A: en la caja «PRÁCTICA» de A1 tocar «Practicar».
2. Responder la pregunta 1 y tocar «Comprobar»; **cronometrar** hasta ver el panel de retroalimentación.
3. «Siguiente  ▶» y repetir hasta la última (fallar una a propósito); en la última, «Ver resultado».
4. En el resultado: «Revisar respuestas», recorrer, «Volver al resultado»; luego «Intentar nuevamente».
5. En el intento 2 responder sólo 2 preguntas y tocar «Mi lección»; en la lista, caja «PRÁCTICA»: «Continuar práctica».
6. Terminar el intento 2 (todas las preguntas, «Ver resultado») y volver a la lista.
7. `Llamar GET "/api/modo-estudio/asignaciones/$A1/?dispositivo=$HAq&alumno_id=$ANA"`; OPS → detalle de A1.

**Resultado esperado.**
- Paso 1: eyebrow «PRÁCTICA DE ESTUDIO», píldora «Práctica de estudio · puedes intentarlo nuevamente», «Pregunta 1 de M».
- Paso 2: panel «✓  ¡Correcto!» (verde) o «✗  Todavía no» (ámbar) en **≤ 2 s** (anotar el tiempo).
- Pasos 3–4: «X de M correctas», un mensaje amable («¡Muy bien!», «¡Buen avance!» o «Sigue practicando: puedes intentarlo otra vez»), «Es una práctica: puedes intentarlo nuevamente las veces que quieras.», marcas ✓/✗ y los botones «Revisar respuestas», «Intentar nuevamente», «Volver a la lección». En ninguna pantalla aparecen «examen», «evaluación» ni «nota».
- Paso 5: el botón de la caja pasa a «Continuar práctica» y reabre el intento 2 con las 2 respuestas marcadas.
- Paso 6: la tarjeta dice «Mejor resultado: X de M · puedes intentarlo nuevamente» (X = el mejor intento) y el botón «Intentar nuevamente».
- Paso 7: 200; `practica.intentos = 2`, `mejor_correctas` = el máximo, `ultima_correctas` = el del intento 2, `en_curso = False`; `tarea.bloques_atendidos = 4` (las 3 vistas más la práctica, que al terminarse cuenta como bloque: D-4), `avance_pct = round(400/N, 2)` y `tarea.estado` sigue `'en_curso'`: terminar la práctica no completa la lección. OPS: PRÁCTICA «X de M correctas · 2 intentos».

**Evidencia a guardar.** Capturas del panel, del resultado y de la tarjeta final; el tiempo medido; JSON del paso 7. Opcional: `Eventos <t0> 'evaluacion.respuesta_registrada.v1'` (carga con `modo = 'estudio'` y **sin** el contenido de la respuesta), `'estudio.practica.terminada.v1'` (2 filas), `'estudio.actividad.reanudada.v1'` (1 fila).

**Efectos colaterales / limpieza.** Dos prácticas terminadas en la tarea de Ana. Ningún intento de evaluación formal se consume (cubierto por `backend/modo_estudio/tests/test_arquitectura.py` y `test_practica.py`).

---

### HP-EST-08 · Completar la lección y verla en «Quién completó»

**Objetivo.** Completar A1 con todas las actividades atendidas y comprobar que la profesora la ve completada.

**Requisitos que demuestra.** FUN-087, 008-04, CAP-051, D-4, TST-079.

**Precondiciones.** HP-EST-07 OK.

**Datos / actor.** PRUEBA-Ana en T-A; OPS.

**Pasos.**
1. T-A: «Continuar lección» en A1; recorrer con «Siguiente» las actividades que falten hasta la última (cada una que se muestra queda vista).
2. Tocar el botón verde «Terminar lección» (habilitado con todas atendidas) y aceptar el diálogo.
3. Revisar «Pendientes» y «Completadas».
4. `Llamar GET "/api/modo-estudio/asignaciones/$A1/?dispositivo=$HAq&alumno_id=$ANA"`
5. OPS → «Modo de estudio»: lista y, dentro de A1, «Quién completó».

**Resultado esperado.**
- Paso 2: diálogo «¡Lección completada!» con «Tu avance quedó guardado. Si estás sin conexión, se enviará solo cuando vuelvas al aula.»; vuelve a la lista.
- Paso 3: «Pendientes 1» (queda A3) y «Completadas 1»; en «Completadas» la tarjeta tiene el chip «✓  COMPLETADA», «Lección completada» en verde y el botón «Ver lección».
- Paso 4: 200; `tarea.estado = 'completada'`, `avance_pct = 100`, `completada_en` no nulo, `fuera_de_plazo = False`.
- Paso 5: la lista muestra «1 de 3 completaron» en A1; en el detalle, la fila de PRUEBA-Ana «COMPLETADA», «terminó hace N min», «N de N actividades · 100 %», práctica «X de M correctas · 2 intentos», aparato «asignada a este alumno»; filtro «Completaron · 1».

**Evidencia a guardar.** Capturas del diálogo, de «Completadas» y de OPS; JSON del paso 4. Opcional: `Eventos <t0> 'estudio.leccion.completada.v1'` → 1 fila con `origen = 'cola'` (Student siempre envía por su cola).

**Efectos colaterales / limpieza.** A1 queda completada para Ana; Beto y Carla la ven pendiente.

---

### HP-EST-09 · Descargar el paquete en la tableta asignada

**Objetivo.** Descargar A3 en T-A con progreso visible, huella verificada y `Range` reanudable, y comprobar que el nodo lo da por disponible, con vigencia.

**Requisitos que demuestra.** FUN-084, CAP-047, 008-03, BR-054, D-7, D-8.

**Precondiciones.** HP-EST-02, 03 y 04 OK; Wi-Fi de T-A encendido; A3 sin tocar.

**Datos / actor.** PRUEBA-Ana en T-A; A3 (consigna «Haz la práctica dos veces.»).

**Pasos.**
1. T-A: en la tarjeta de A3 tocar «Descargar».
2. Observar el avance y el pie. **(Condicional)** si la descarga lo permite, «Pausar» y luego «Continuar descarga».
3. Esperar «Disponible sin conexión». Tocar el filtro «Descargadas».
4. `$pk = Llamar GET "/api/modo-estudio/paquetes/?dispositivo=$HAq&alumno_id=$ANA"; Guardar $pk.Cuerpo 'HP-EST-09_p04_paquetes.json'; $pk.Cuerpo.paquetes | Select id, asignacion_id, estado, motivo, bytes_total, huella, vigente_hasta`
5. `$PQ = ($pk.Cuerpo.paquetes | Where-Object asignacion_id -eq $A3).id; & '<PYTHON>' huella.py "$NODO/api/modo-estudio/paquetes/$PQ/manifiesto/?dispositivo=$HAq&alumno_id=$ANA"`
6. Elegir un `media_ref` (`($pk.Cuerpo.paquetes | Where-Object asignacion_id -eq $A3).archivos | Select media_ref, clase, bytes`) y pedir un trozo: `curl.exe -s -D - -o NUL -H "Range: bytes=0-99" "$NODO/api/modo-estudio/paquetes/$PQ/archivos/<MEDIA_REF>/?dispositivo=$HAq&alumno_id=$ANA"`
7. `Llamar GET "/api/modo-estudio/asignaciones/$A3/?dispositivo=$HAq&alumno_id=$ANA"`; OPS → detalle de A3.

**Resultado esperado.**
- Pasos 1–2: «Preparando la descarga…», luego «Descargando contenido…» con porcentaje, «X MB de Y MB», tiempo restante y «Pausar»; el pie dice «Descargando 1 lección» con su porcentaje; la pantalla sigue respondiendo. Tras «Pausar»: «Descarga pausada · NN %»; «Continuar descarga» sigue **desde ese porcentaje**, no desde 0.
- Paso 3: marca verde y «Disponible sin conexión» con el menú «⋯»; «Descargadas 1»; el pie suma «NN MB en tu tableta».
- Paso 4: 200; el paquete de A3 `estado = 'disponible'`, `motivo = ''`, `huella` de 64 hex, `bytes_total` = suma de `archivos[].bytes`, cada archivo con `sha256` de 64 hex, `no_incluidos` vacío (o sólo `simulacion_requiere_nodo`/`medio_*` justificados), `vigente_hasta = fecha_limite + 900000` (`fecha_limite` sale del paso 7).
- Paso 5: `COINCIDE` y la misma huella del paso 4 (si la lección cambió en la biblioteca sin cambiar de versión, la huella nueva es la vigente; en otro caso `NO COINCIDE` es falla).
- Paso 6: `HTTP/1.1 206 Partial Content`, `Content-Range: bytes 0-99/<total>`, `Accept-Ranges: bytes`, `ETag: "<sha256 del archivo>"` (el 206 depende de que AVACOM Contenido soporte `Range`: por confirmar).
- Paso 7: `paquete.estado = 'disponible'`, `descarga.permitida = True`. OPS: EN SU TABLETA «En el aparato».

**Evidencia a guardar.** Capturas de cada estado (preparando, descargando, pausada, disponible); JSON de los pasos 4 y 7; salida de `huella.py` y de `curl.exe`. Opcional: `Eventos <t0> 'estudio.paquete.descargado.v1'` → 1 fila con esa `huella`.

**Efectos colaterales / limpieza.** T-A guarda la lección cifrada (se retira en HP-EST-17). Pedir el paquete crea la tarea de Ana en A3 en estado «pendiente».

---

### HP-EST-10 · Tableta compartida: se estudia en línea y el material «es de la clase»

**Objetivo.** Comprobar que en una tableta compartida (o en la asignada a otra persona) se estudia con el aula conectada pero no se descarga, con el mensaje del Maestro, y que el profesor puede dejar una lección «Sólo en línea».

**Requisitos que demuestra.** 008-01, FUN-085, BR-054, PAN-133, MSG-046, D-2, JRN-007.

**Precondiciones.** HP-EST-04 y 08 OK.

**Datos / actor.** PRUEBA-Beto en T-C (A2); T-A consultada por API declarando a Beto; PRUEBA-Ana en T-A (A1); OPS.

**Pasos.**
1. T-C (Beto): mirar las tarjetas de A2 y A1.
2. Tocar «Comenzar lección» en A2 y volver.
3. `Llamar GET "/api/modo-estudio/asignaciones/$A2/?dispositivo=$HCq&alumno_id=$BETO"`
4. `Llamar GET "/api/modo-estudio/asignaciones/$A2/?dispositivo=$HAq&alumno_id=$BETO"` (T-A declarando a otra persona; sólo lectura, no toca la tableta).
5. OPS → detalle de A1 → «Cambios rápidos» → «Llevársela a casa» → «Sólo en línea». En T-A (Ana): «X», volver a entrar a «Modo de estudio», filtro «Completadas», tarjeta de A1.
6. OPS → «Se puede descargar» para dejar A1 como estaba.

**Resultado esperado.**
- Paso 1: en lugar del botón «Descargar», un candado y «Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti.»; «Comenzar lección» está habilitado.
- Paso 2: la lección abre desde el aula y registra el avance.
- Paso 3: 200; `descarga = {permitida: False, motivo: 'dispositivo_compartido'}`; `paquete = null`.
- Paso 4: 200; `descarga = {permitida: False, motivo: 'dispositivo_ajeno'}` (Beto estudiaría ahí en línea; la UI diría «Esta tableta es de otra persona.»).
- Paso 5: OPS dice «Guardado» + «Ahora sólo se estudia en línea.» y la píldora «SÓLO EN LÍNEA»; en T-A la tarjeta de A1 muestra «Tu profesor no dejó este material para llevártelo. Puedes estudiarlo con la tableta conectada al aula.».
- Paso 6: «Ahora se puede descargar.» y la píldora «SE PUEDE DESCARGAR».

**Evidencia a guardar.** Capturas de los pasos 1, 5 y 6; JSON de los pasos 3 y 4.

**Efectos colaterales / limpieza.** A1 vuelve a «Se puede descargar». Pedir un paquete por API en una compartida daría 403 `descarga_denegada` (contrato; fuera de este plan).

---

### HP-EST-11 · Trabajo sin red que se integra al volver

**Objetivo.** Estudiar, practicar y completar A3 sin red desde el paquete; comprobar que lo hecho se guarda primero (↑) y llega solo al volver el aula (↻ → ✓), con la práctica calificada al integrarse.

**Requisitos que demuestra.** 008-06, CAP-048, FUN-086, BR-059, BR-137, D-6, D-11, MSG-011, CMP-002, TST-029.

**Precondiciones.** HP-EST-09 OK (A3 «Disponible sin conexión»), A3 sin completar; el PC del operador sigue viendo el nodo.

**Datos / actor.** PRUEBA-Ana en T-A; A3.

**Pasos.**
1. Apagar el Wi-Fi de T-A (o modo avión) y esperar unos segundos en «Modo estudio».
2. Abrir A3 («Comenzar lección»), recorrer con «Siguiente» las actividades de lectura y volver a la lista.
3. «Practicar», responder todas las preguntas (el botón dice «Guardar respuesta») y terminar con «Ver resultado» (o «Terminar»).
4. Abrir A3 otra vez, ir a la última actividad y tocar «Terminar lección».
5. Desde el PC: `Llamar GET "/api/modo-estudio/asignaciones/$A3/?dispositivo=$HAq&alumno_id=$ANA"`; mirar el detalle de A3 en OPS.
6. Encender el Wi-Fi de T-A y observar el pie de «Mis lecciones».
7. Repetir el comando del paso 5 y OPS. Opcional: `Libro $ANA`.

**Resultado esperado.**
- Paso 1: chip ámbar «Sin conexión»; A3 sigue «Disponible sin conexión» y habilitada.
- Paso 2: chip verde «Desde tu tableta»; pie «Pendiente de enviar» (↑; con « · N» si hay más de un evento en cola) y, en la tarjeta, «Pendiente de sincronización».
- Paso 3: cada respuesta muestra «●  Guardada en tu tableta» + «Verás si acertaste cuando tu tableta vuelva a estar en el aula.» (sin veredicto); al terminar, «Práctica guardada» + «Se calificará cuando tu tableta vuelva a estar en el aula. Tus respuestas están a salvo.».
- Paso 4: «¡Lección completada!»; la tarjeta pasa a «Completadas» con «Pendiente de sincronización». Ana ya no tiene lecciones abiertas: «Pendientes» muestra «Estás al día» / «No tienes lecciones pendientes en modo estudio.» y la acción «Ver lecciones completadas».
- Paso 5: el nodo **aún no sabe nada**: `tarea` nula o `pendiente` con 0 actividades; en OPS la fila de Ana sigue «PENDIENTE».
- Paso 6: desaparece «Sin conexión»; el pie pasa por «Sincronizando…» (↻) y queda en «Guardado» (✓) en menos de 1 minuto, sin tocar nada.
- Paso 7: `tarea.estado = 'completada'`, `bloques_atendidos = N`, `practica.intentos = 1`, `practica.ultima_correctas` no nulo (calificada al integrarse); la tarjeta dice «Mejor resultado: X de M…». OPS: fila COMPLETADA y práctica «X de M correctas · 1 intento». `Libro $ANA`: todos los eventos `estado = 'integrado'`, `secuencia` creciente, un solo `emisor_id`.

**Evidencia a guardar.** Capturas de los pasos 1–4 y 6; JSON de los pasos 5 y 7; `Libro $ANA`; el tiempo del paso 6.

**Efectos colaterales / limpieza.** A3 queda completada para Ana. Wi-Fi de T-A encendido.

---

### HP-EST-12 · Reenvío idempotente por `emisor_id` + `secuencia`

**Objetivo.** Probar contra el nodo real que repetir un envío no duplica nada y que un envío mezclado sólo integra lo nuevo.

**Requisitos que demuestra.** BR-060, BR-138, INV-013, D-10, D-11, TST-029, 008-06.

**Precondiciones.** HP-EST-01 OK (ids, lección, T-C registrada).

**Datos / actor.** Operador por API; PRUEBA-Carla; emisor de prueba `PRUEBA-EMISOR-001` (no es una tableta); T-C como aparato.

**Pasos.**
1. Crear A6 y leer sus bloques:
```powershell
$ahora = Ahora
$r = Llamar POST '/api/modo-estudio/docente/asignaciones/' @{ alcance='seleccion'; grupo_id=$GRUPO; alumnos=@($CARLA); curso_ref=$CURSO; leccion_ref=$LECCION; fuente='biblioteca'; titulo='PRUEBA-A6 idempotencia'; plazo='blando'; paquete_permitido=$false; actor='PRUEBA-operador' }
$A6 = $r.Cuerpo.id
$b = (Llamar GET "/api/modo-estudio/asignaciones/$A6/?dispositivo=$HCq&alumno_id=$CARLA").Cuerpo.bloques
```
2. Enviar dos veces el mismo lote de 2 eventos (`Ev n i` = evento de secuencia `n` que marca visto el bloque `i`):
```powershell
function Ev($n, $i) { @{ secuencia=$n; tipo='study.block.viewed'; ocurrido_en=$ahora; carga=@{ asignacion_id=$A6; bloques_vistos=@($b[$i].ref); bloque_actual=$b[$i].ref } } }
function Enviar($eventos) { Llamar POST '/api/modo-estudio/sync/' @{ dispositivo=$HC; alumno_id=$CARLA; emisor_id='PRUEBA-EMISOR-001'; eventos=$eventos } }
$r1 = Enviar @((Ev 1 0), (Ev 2 1))
$r2 = Enviar @((Ev 1 0), (Ev 2 1))
```
3. Envío mezclado, con la secuencia 2 repetida y la 3 nueva: `$r3 = Enviar @((Ev 2 1), (Ev 3 2))`
4. `Llamar GET "/api/modo-estudio/asignaciones/$A6/?dispositivo=$HCq&alumno_id=$CARLA"` y `Llamar GET "/api/modo-estudio/sync/status/?dispositivo=$HCq&emisor_id=PRUEBA-EMISOR-001&alumno_id=$CARLA"`.

**Resultado esperado.**
- Paso 1: `Estado = 201`, `$A6` con id, `alcance = 'seleccion'`; `$b` con ≥ 3 bloques.
- Paso 2: `r1`: 200, `acuse = True`, `resumen = {integrados: 2, duplicados: 0, rechazados: 0, pendientes_decision: 0}`, cada `resultados[].estado = 'integrado'`. `r2`: 200, `resumen = {integrados: 0, duplicados: 2, …}`, cada resultado `'duplicado'` con `detalle.estado_original = 'integrado'`.
- Paso 3: `r3.Cuerpo.resumen` con `integrados = 1` y `duplicados = 1`: la secuencia 2 `duplicado`, la 3 `integrado`.
- Paso 4: `tarea.bloques_atendidos = 3` (no 5 ni 7), `estado = 'en_curso'`; `sync/status`: `ultima_secuencia = 3`, `conteos = {synced: 3, rejected: 0, conflict: 0}`, `pendientes_decision = []`. OPS, detalle de A6: Carla «EN CURSO» con 3 actividades.

**Evidencia a guardar.** JSON de `r1`, `r2`, `r3` y del paso 4. Opcional: `Libro $CARLA` (3 filas `PRUEBA-EMISOR-001`, secuencias 1–3, `integrado`).

**Efectos colaterales / limpieza.** A6 queda en curso para Carla (se cierra en §6). El emisor `PRUEBA-EMISOR-001` permanece en el libro (nada se borra).

---

### HP-EST-13 · Vigencia del paquete: vence, se libera y se vuelve a descargar

**Objetivo.** Comprobar que un paquete vence a `fecha_limite + gracia`, que la tableta libera lo vencido con un aviso y que descargar de nuevo reutiliza la fila con vigencia nueva.

**Requisitos que demuestra.** D-8, MSG-045, 008-03, CAP-047.

**Precondiciones.** HP-EST-02 OK; T-A con Wi-Fi y PRUEBA-Ana con sesión en T-A; ≈ 8 minutos de espera.

**Datos / actor.** PRUEBA-Ana en T-A; A4 por API.

**Pasos.**
1. Crear A4:
```powershell
$ahora = Ahora; $lim = $ahora + 5*60*1000
$r = Llamar POST '/api/modo-estudio/docente/asignaciones/' @{ alcance='seleccion'; grupo_id=$GRUPO; alumnos=@($ANA); curso_ref=$CURSO; leccion_ref=$LECCION; fuente='biblioteca'; titulo='PRUEBA-A4 vigencia'; fecha_limite=$lim; plazo='blando'; gracia_min=1; paquete_permitido=$true; actor='PRUEBA-operador' }
$A4 = $r.Cuerpo.id
```
2. T-A: «X» y volver a entrar a «Modo de estudio»; tarjeta «PRUEBA-A4 vigencia»; «Descargar» y esperar «Disponible sin conexión» (antes de que pasen 5 min).
3. `$pq = (Llamar GET "/api/modo-estudio/paquetes/?dispositivo=$HAq&alumno_id=$ANA").Cuerpo.paquetes | Where-Object asignacion_id -eq $A4; $pq | Select id, estado, motivo, vigente_hasta`
4. Repetir `(Ahora) -gt ($lim + 60000)` hasta que dé `True`.
5. T-A: «X» y volver a entrar a «Modo de estudio».
6. Repetir el paso 3.
7. Tocar «Descargar» en la tarjeta de A4, esperar «Disponible sin conexión» y repetir el paso 3.

**Resultado esperado.**
- Paso 2: «Entrega: hoy, <h:mm p. m.>» con el chip «Vence hoy»; descarga completa.
- Paso 3: `estado = 'disponible'`; `vigente_hasta = $lim + 60000`.
- Paso 5: aviso «Liberamos una lección descargada que ya venció. Puedes volver a descargarla.»; la tarjeta de A4 con el chip «!  VENCIDA» y «Descargar»; «Descargadas» baja en 1.
- Paso 6: el mismo paquete con `estado = 'vencido'`, `motivo = 'vigencia'`.
- Paso 7: el **mismo `id`** del paso 3 (fila reutilizada), `estado = 'disponible'`, `motivo = ''`, `vigente_hasta ≈ servidor_en + 14 días` (unos minutos de tolerancia): la fecha ya pasó y el plazo flexible sigue aceptando.

**Evidencia a guardar.** Capturas de los pasos 2, 5 y 7; los tres JSON del paso 3 con sus horas.

**Efectos colaterales / limpieza.** T-A queda con una copia de A4 (se retira en HP-EST-17). A4 sigue abierta (flexible) y se cierra en §6.

---

### HP-EST-14 · Lo que llega fuera de plazo: el profesor decide

**Objetivo.** Con plazo estricto, comprobar que lo hecho a tiempo pero entregado después de la gracia no se descarta en silencio: queda «por decidir» y la profesora lo acepta con un toque.

**Requisitos que demuestra.** BR-074, D-9, DEC-019, BR-062, 008-02, 008-06, PAN-131.

**Precondiciones.** HP-EST-02 y 09 OK; ≈ 15 minutos; T-A con Wi-Fi.

**Datos / actor.** PRUEBA-Ana en T-A; A5 por API; OPS.

**Pasos.**
1. Crear A5 (hora del nodo; plazo estricto, gracia de 1 min):
```powershell
$ahora = Ahora; $lim5 = $ahora + 8*60*1000
$r = Llamar POST '/api/modo-estudio/docente/asignaciones/' @{ alcance='seleccion'; grupo_id=$GRUPO; alumnos=@($ANA); curso_ref=$CURSO; leccion_ref=$LECCION; fuente='biblioteca'; titulo='PRUEBA-A5 estricto'; fecha_limite=$lim5; plazo='endurecido'; gracia_min=1; paquete_permitido=$true; actor='PRUEBA-operador' }
$A5 = $r.Cuerpo.id
```
2. T-A: «X» y volver a entrar; tarjeta «PRUEBA-A5 estricto»; «Descargar» hasta «Disponible sin conexión».
3. Apagar el Wi-Fi de T-A. Abrir A5 («Comenzar lección»), **quedarse en la actividad 1** y volver a la lista.
4. Con el Wi-Fi apagado, repetir `(Ahora) -gt ($lim5 + 60000)` hasta que dé `True`.
5. Encender el Wi-Fi; esperar a que el pie vuelva a «Guardado».
6. `$d = (Llamar GET "/api/modo-estudio/docente/asignaciones/$A5/").Cuerpo; $d.pendientes_decision; $d.alumnos[0].decisiones`
7. OPS → «Modo de estudio» → tarjeta de A5 → «Ver quién completó  ›». Tocar «Aceptar».
8. Repetir el paso 6.

**Resultado esperado.**
- Paso 3: pie «Pendiente de enviar» (un solo evento, sin « · N»).
- Paso 5: el pie llega a «Guardado» (el nodo acusó recibo, también de lo que deja por decidir).
- Paso 6: `pendientes_decision = 1`; `decisiones[0]` con `tipo = 'study.block.viewed'`, `motivo = 'fuera_de_gracia'`, `emisor_id`, `secuencia`, y `ocurrido_en` ≤ `$lim5` < `recibido_en`.
- Paso 7: en la lista, píldora violeta «1 envío por decidir»; en el detalle, filtro «Por decidir · 1» y, bajo la fila de PRUEBA-Ana, un recuadro violeta «PRUEBA-Ana avanzó en la lección y su tableta lo mandó tarde» / «Lo hizo el <fecha · hora> y llegó el <fecha · hora>, fuera de la gracia. ¿Lo aceptas?» con «Aceptar» y «Descartar». Tras «Aceptar»: «Listo» + «Aceptaste el envío: ya cuenta en el avance del alumno.».
- Paso 8: `pendientes_decision = 0`; `alumnos[0].estado = 'en_curso'`, `bloques_atendidos = 1`, `fuera_de_plazo = False` (se hizo antes de la fecha). En OPS la fila de Ana dice «VENCIDA» (la fecha pasó y no completó) con «1 de N actividades · NN %» y el recuadro violeta desapareció. Opcional: `Libro $ANA` → ese evento `estado = 'integrado'`, `motivo = 'aceptado_por_docente'`.

**Evidencia a guardar.** Capturas de los pasos 3, 5 y 7 (antes y después de «Aceptar»); JSON de los pasos 6 y 8; `$lim5` y las horas de `Ahora` usadas.

**Efectos colaterales / limpieza.** A5 queda estricta y vencida: ya no acepta trabajo en línea. La copia local de A5 se libera sola al vencer.

---

### HP-EST-15 · Cerrar una asignación

**Objetivo.** Cerrar A2 desde OPS conservando lo hecho, y comprobar que el alumno deja de verla como pendiente.

**Requisitos que demuestra.** CAP-051, 008-02, 008-04.

**Precondiciones.** HP-EST-03 y 04 OK; A2 abierta.

**Datos / actor.** PRUEBA-Beto en T-C; OPS.

**Pasos.**
1. T-C (Beto): abrir A2 («Comenzar lección»), ver la actividad 1 y volver; la tarjeta queda «◐  EN CURSO».
2. OPS → «Modo de estudio» → tarjeta de A2 → «Ver quién completó  ›» → «Cerrar la asignación».
3. En «¿Cerrar esta asignación?» tocar «Cerrar».
4. OPS: «‹  Asignaciones»; filtros «Abiertas» y «Cerradas».
5. `Llamar GET "/api/modo-estudio/docente/asignaciones/$A2/"`
6. T-C: «X», volver a entrar a «Modo de estudio» y mirar «Pendientes»; `Llamar GET "/api/modo-estudio/asignaciones/?dispositivo=$HCq&alumno_id=$BETO"`.

**Resultado esperado.**
- Paso 3: el diálogo dice «1 alumno todavía no la termina. Al cerrarla ya no se acepta trabajo nuevo y desaparece de «Pendientes» en las tabletas. Lo ya hecho se conserva.»; luego «Asignación cerrada» + «Ya no se acepta trabajo nuevo. Lo hecho se conserva.», la píldora «CERRADA» y ya no aparece «Cambios rápidos».
- Paso 4: A2 sólo en «Cerradas».
- Paso 5: 200; `estado = 'cerrada'`, `cerrada_en` no nulo; la fila de Beto conserva su avance.
- Paso 6: «Pendientes 1» (sólo A1); `asignaciones[]` sin A2 y `resumen.pendientes = 1`.

**Evidencia a guardar.** Capturas del diálogo, del detalle cerrado y de la lista de Beto; JSON de los pasos 5 y 6. Opcional: `Eventos <t0> 'estudio.asignacion.cerrada.v1'` → 1 fila.

**Efectos colaterales / limpieza.** A2 queda cerrada (lo buscado); el avance de Beto se conserva.

---

### HP-EST-16 · Cambiar de alumno y «Salir»: la tableta queda libre

**Objetivo.** En T-C, cambiar de PRUEBA-Beto a PRUEBA-Carla sin mezclar datos y «Salir» en ≤ 3 s dejando la tableta lista para la persona siguiente.

**Requisitos que demuestra.** 008-07, FUN-089, FUN-090, BR-053, TST-028, JRN-022, D-15.

**Precondiciones.** HP-EST-04 y 12 OK (Carla con A6 en curso); T-C con la sesión de Beto.

**Datos / actor.** T-C; Beto → Carla; cronómetro.

**Pasos.**
1. T-C: tocar «Estudias como PRUEBA-Beto  ·  Cambiar».
2. En «¿Quién eres?» elegir «PRUEBA-Carla» y «Continuar como PRUEBA-Carla».
3. `(Llamar GET '/api/dispositivos/').Cuerpo | Where-Object identificador_hw -eq $HC | Select sesion_abierta`
4. Volver al menú (la «X») y tocar «Salir» en el dock inferior; **cronometrar** hasta el aviso.
5. Repetir el comando del paso 3.
6. Volver a entrar a Student (§2.8, punto 4) → «Modo de estudio».

**Resultado esperado.**
- Paso 1: vuelve «¿Quién eres?» con el recuadro «LA ÚLTIMA PERSONA QUE ESTUDIÓ AQUÍ» · «PRUEBA-Beto».
- Paso 2: cabecera «Estudias como PRUEBA-Carla  ·  Cambiar»; sólo lecciones de Carla (A1 y A6, «Pendientes 2»), nada de Beto.
- Paso 3: `sesion_abierta.alumno_id = $CARLA` (el nodo relevó la de Beto).
- Paso 4: en **≤ 3 s** aparece «Conéctate a tu aula» con el aviso «Listo. Tu trabajo queda guardado y se enviará solo. La tableta ya está libre para el siguiente.».
- Paso 5: `sesion_abierta = null`; en OPS «Dispositivos» dice «libre».
- Paso 6: «¿Quién eres?» sin el recuadro «LA ÚLTIMA PERSONA QUE ESTUDIÓ AQUÍ» (la tableta olvidó a Carla); al volver a elegirla, «Descargadas 0». Opcional: `Eventos <t0> 'estudio.sesion.cerrada.v1'` → 1 fila con `motivo = 'usuario'`, `limpieza = 'completa'`, `cola_pendiente = 0`.

**Evidencia a guardar.** Capturas de los pasos 1, 2, 4 y 6; el tiempo medido; JSON de los pasos 3 y 5.

**Efectos colaterales / limpieza.** Q-72: en una tableta *asignada*, «Salir» también borra las descargas; por eso se usa T-C y T-A no sale hasta HP-EST-17.

---

### HP-EST-17 · Eliminar las descargas y devolver la tableta al aula

**Objetivo.** Que el alumno retire sus descargas de T-A y la profesora devuelva la tableta al fondo compartido, donde ya no se descarga.

**Requisitos que demuestra.** FUN-093, D-14, 008-01, 008-03 (retirar), D-2.

**Precondiciones.** HP-EST-09, 13 y 14 ejecutados (T-A guarda A3 y A4; la copia de A5 ya se liberó al vencer); Wi-Fi de T-A encendido; PRUEBA-Ana con sesión en T-A.

**Datos / actor.** PRUEBA-Ana en T-A; OPS.

**Pasos.**
1. T-A: filtro «Descargadas». En cada tarjeta que siga ahí (A3, A4) tocar «⋯» → «Ver información» (leer) y de nuevo «⋯» → «Eliminar descarga» → «Eliminar».
2. `Llamar GET "/api/modo-estudio/paquetes/?dispositivo=$HAq&alumno_id=$ANA"`
3. OPS → «Dispositivos» → tarjeta de T-A → «Devolver al aula» → en «¿Devolver esta tableta al aula?» tocar «Devolver».
4. `(Llamar GET '/api/dispositivos/').Cuerpo | Where-Object identificador_hw -eq $HA | Select perfil, asignado_a`; `Llamar GET "/api/modo-estudio/estado/?dispositivo=$HAq"`
5. T-A: «Modo de estudio» → una tarjeta de Ana.

**Resultado esperado.**
- Paso 1: «Ver información» dice «Esta lección está guardada en tu tableta (… MB). Puedes estudiarla y practicar sin conexión con el aula; tu avance se enviará solo cuando vuelvas.»; «Eliminar descarga» pide «¿Eliminar la descarga?» («Se liberará el espacio de esta lección en tu tableta. Tu avance se conserva y podrás descargarla otra vez.»); cada tarjeta vuelve a «Descargar»; «Descargadas 0»; baja el espacio usado.
- Paso 2: 200; `paquetes` sin ningún `solicitado`, `descargandose` ni `disponible` (los retirados no se listan; el de A5 puede salir `vencido`, que no cuenta).
- Paso 3: la tarjeta pasa a «Compartida del aula · las lecciones se estudian con el aula conectada» con el botón «Asignar a un alumno».
- Paso 4: `perfil = 'compartido'`, `asignado_a = null`; estado: `perfil = 'compartido'`, `dueno = null`, `descarga_permitida = False`.
- Paso 5: Ana sigue estudiando en línea y donde antes estaba «Descargar» ve «Este material está disponible durante la clase. Para llevártelo necesitas una tableta asignada a ti.».

**Evidencia a guardar.** Capturas de cada paso en Student y OPS; JSON de los pasos 2 y 4.

**Efectos colaterales / limpieza.** T-A vuelve a ser compartida. Si quedó una descarga sin retirar, OPS avisa «El alumno todavía tiene lecciones descargadas o trabajo sin enviar en esta tableta…» (409 `paquete_sin_integrar`): se retira y se repite el paso 3.

---

## 6 · Orden de ejecución y dependencias

**Orden recomendado:** 01 → 02 → … → 17 → cierre. Los HP 13 y 14 no se solapan (el 14 apaga el Wi-Fi de T-A y el 13 lo necesita).

| HP | Depende de | Nota |
|---|---|---|
| 01 | — | Sus ids y huellas los usan todos |
| 02 | 01 | T-A asignada |
| 03 | 01 | Crea A1, A2, A3 |
| 04 | 02, 03 | Abre las sesiones de Ana y Beto |
| 05 | 04 | Lectura de las listas |
| 06 · 07 · 08 | 05 · 06 · 07 | Cadena sobre A1; el 08 exige la práctica terminada |
| 09 | 02, 03, 04 | Usa A3 |
| 10 | 03, 04, 08 | A2 en T-C; A1 ya completada |
| 11 | 09 | Usa A3 descargada |
| 12 | 01 | Independiente; crea A6 |
| 13 | 02, 04 | Crea A4; ≈ 8 min de espera |
| 14 | 02, 09 | Crea A5; ≈ 15 min de espera |
| 15 | 03, 04 | Cierra A2 |
| 16 | 04, 12 | En T-C, no en T-A |
| 17 | 02, 09, 13, 14 | Retira A3 y A4 y devuelve T-A |

**Cierre de la sesión de pruebas (tras HP-EST-17).** OPS → «Modo de estudio» → «Abiertas» → abrir A1, A3, A4, A5 y A6 → «Cerrar la asignación» (A2 ya está cerrada). Dejar T-A y T-C compartidas, libres y con Student cerrada. Anotar en el registro los ids A1…A6 y avisar a la administración de que los datos `PRUEBA-` permanecen.

**Segunda pasada (recomendada):** intercambiar las plataformas de T-A y T-C y repetir HP-EST-02, 09, 11 y 17.

---

## 7 · Registro de ejecución

Evidencia: ruta de `$EVID\HP-EST-NN\`. Observaciones: plataforma, cronómetros, desviaciones, `[AND]`.

| HP | Fecha | Ejecutor | Resultado (OK/FALLA) | Evidencia (ruta) | Observaciones |
|---|---|---|---|---|---|
| HP-EST-01 | | | | | |
| HP-EST-02 | | | | | |
| HP-EST-03 | | | | | |
| HP-EST-04 | | | | | |
| HP-EST-05 | | | | | |
| HP-EST-06 | | | | | |
| HP-EST-07 | | | | | |
| HP-EST-08 | | | | | |
| HP-EST-09 | | | | | |
| HP-EST-10 | | | | | |
| HP-EST-11 | | | | | |
| HP-EST-12 | | | | | |
| HP-EST-13 | | | | | |
| HP-EST-14 | | | | | |
| HP-EST-15 | | | | | |
| HP-EST-16 | | | | | |
| HP-EST-17 | | | | | |

---

## 8 · Fuera de alcance

- **Caminos de error (sad/bad paths):** 4xx/5xx (`datos_invalidos`, `sin_permiso`, `alumno_desconocido`, `descarga_denegada` pedida por API, `huella_invalida`, `bloques_pendientes`, `practica_terminada`, `asignacion_cerrada`, `paquete_vencido`, `fuente_no_disponible`), manifiestos alterados, medios sobre el tope, biblioteca caída.
- **Permisos `study.*` con sesión** (008-08, D-12): sólo se evalúan con `AVACOM_LMS_EXIGIR_SESION=1`.
- **Carga y rendimiento:** muchas tabletas a la vez, descargas grandes, el tope de 200 eventos por envío.
- **Pruebas destructivas o de seguridad ofensiva:** corromper la cola o el almacén cifrado, matar procesos, llenar el disco, suplantar a un compañero (Q-74), manipular relojes.
- **Funciones no construidas o abiertas:** 008-09 (Q-68), simulaciones sin red (Q-71), práctica calificada sin red (Q-67), «Salir» que conserve las descargas del dueño (Q-72), barra de % de «Asignaturas» (Q-73), obligatoriedad por bloque (Q-66).
- **Cobertura automática del repositorio:** `backend/modo_estudio/tests/` (asignaciones, lecciones, paquetes, práctica, sincronización, permisos, identidad declarada, sesión, dominio y arquitectura) y `tests/Avacom.Lms.Core.Tests` (cifrado, almacén, descargador, cola, sincronizador, servidor local de medios, JSON canónico y cliente `EstudioApi`); la lógica de Student, en `tests/Avacom.Lms.Student.Tests`.
