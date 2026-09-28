# 00 · Device Manager (MOD-009) · Modelo `m09_*` y API `/api/dispositivos/`

| Campo | Valor |
|---|---|
| Estado | **Implementado y probado** el 2026-09-28: app `backend/device_manager/`, migraciones `device_manager/0001`, `acceso/0005`, `device_manager/0002`; 22 pruebas propias más las del aula que la ejercitan. |
| Módulo | **MOD-009 · Device Manager** del Documento Maestro (DOM-005, «el dominio que nunca dice que no»). Alcance MVP: CAP-052 registrar e inventariar, CAP-053 emparejar por huella, CAP-054 estado en vivo, CAP-055 reconexión. CAP-056/057/058 (agente desatendido, retiro con borrado remoto, diagnóstico de red) son V1 y no están. |
| Origen | `specs/analisis/borrador-01-lanzamiento.md` (sondeo de atributos contra el Maestro) y la segunda versión del modelo de datos (`specs/analisis/segunda-version-modelo.md`, dominio «Gestión de dispositivos» y «Dim Sesión Alumno»). |
| Dueño único | Este módulo es el único que escribe `m09_*` (BR-003). `acceso` lo lee en el login por su puerto `RepositorioDispositivos`; `classroom_engine` por su puerto `Dispositivos`. Los dos llegan por `device_manager/servicios.py`, dentro de su propia transacción, nunca por el ORM (BR-004). |

---

## 1 · Lo que se muda y lo que nace

Hasta el 2026-09-28 `Dispositivo` vivía en `acceso` (`m01_dispositivo`) y `classroom_engine` guardaba la tableta del participante como texto libre (`dispositivo`, CV-08: «pasarán a FK físicas cuando MOD-009 tenga dueño»). Desde hoy:

| Antes | Ahora | Cómo se llegó |
|---|---|---|
| `acceso.Dispositivo` · `m01_dispositivo` (`identificador`, `nombre`, `tipo`, `activo`, `registrado_en`, `ultimo_visto_en`) | `device_manager.Dispositivo` · **`m09_dispositivo`** (`identificador_hw`, `nombre`, `tipo`, `plataforma`, `version_app`, `activo`, **`bloqueado`**, `registrado_en`, `ultimo_latido_en`) | `device_manager/0001` toma el modelo en el estado de migraciones (sin tocar filas), renombra la tabla y las columnas y añade las nuevas; `acceso/0005` repunta sus tres FK (`m01_sesion`, `m01_autorizacion_temporal`, `m01_intento_acceso`) y borra el modelo de su estado; `device_manager/0002` deja el `related_name` definitivo. Verificado sobre una copia de `db.sqlite3`: `PRAGMA foreign_key_check` vacío, FK de `m01_sesion` apuntando a `m09_dispositivo`. |
| `POST` / `GET /api/acceso/dispositivos/`, `PATCH …/{id}/` | `POST` / `GET /api/dispositivos/`, `GET` / `PATCH …/{id}/`, `POST …/{id}/bloquear/`, `…/desbloquear/`, `POST …/latido/` | Los casos de uso `RegistrarDispositivo`, `ListarDispositivos` y `ActualizarDispositivo` salen de `acceso` y entran aquí con `BloquearDispositivo`, `DesbloquearDispositivo`, `RegistrarLatido`, `VerDispositivo`. |
| — | **`m09_dim_sesion_alumno`**: la «Dim Sesión Alumno» del modelo (alumno + tableta + periodo). El Maestro pone la sesión de usuario en el dispositivo bajo MOD-009 (ENT-018, AGG-005). | La abre el aula al unirse a clase (`POST /api/aula/sesiones/unirse/`), la cierra al salir (`salio`), al cerrar la clase (`sistema`) o al dar de baja la tableta. |
| `m07_participante.dispositivo` (texto) | Sigue, y gana `dispositivo_id` y `dim_sesion_alumno_id` (referencias lógicas a `m09_*`) | El aula las resuelve por su puerto; siguen sin ser FK físicas (CV-08) mientras los módulos no compartan motor definitivo. |

Lo que **no** se construyó todavía, a propósito (preguntas abiertas del sondeo, §5 del borrador): `nodo_maestro_id` (qué es un «nodo maestro» sigue sin confirmarse con el CTO), la asignación nominal de tabletas a alumnos (`dispositivo.asignado.v1`), los niveles de control de examen (MOD-010) y el borrado remoto (V1). `organizacion_id` se **conserva** (ya estaba en uso).

## 2 · Modelo `m09_*`

```
 m09_dispositivo ──1:N── m09_dim_sesion_alumno      (INV-011: cero o una abierta por tableta · DEC-023: una abierta por alumno)
        │                       ▲
        │ FK SET NULL           │ referencia lógica (dim_sesion_alumno_id)
 m01_sesion · m01_autorizacion_temporal · m01_intento_acceso (acceso)      m07_participante (classroom_engine, dispositivo_id)
 m09_evento_salida  (outbox dispositivo.*.v1, sin FK)
```

### 2.1 · `m09_dispositivo`

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | El que ya tenían las filas de `m01_dispositivo` |
| `organizacion` | FK → `m01_organizacion` CASCADE | El nodo tiene una sola (MOD-001 la instala). Se conserva: pregunta 4 del sondeo, pendiente |
| `identificador_hw` | char(128) | La huella con la que la tableta se presenta (`student-<equipo>`, `ops-<equipo>`); única por organización (`uq_m09_dispositivo_identificador`) |
| `nombre` · `tipo` · `plataforma` · `version_app` | char(120) · `TABLETA`/`MASTER`/`OTRO` · `windows`/`android`/`''` · char(32) | Lo que declara la tableta al registrarse o en cada latido |
| `activo` · `bloqueado` | bool | Retirada (conserva historial) · **bloqueada**: no abre sesión ni recibe lanzamientos. Reversible, queda en bitácora |
| `registrado_en` · `ultimo_latido_en` | bigint ms | `en_linea` = latido en el último minuto (`LATIDO_VIVO_MS`) |

### 2.2 · `m09_dim_sesion_alumno`

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `alumno_id` | char(64) | `persona_id` (referencia lógica a MOD-001, CV-08) |
| `dispositivo` | FK → `m09_dispositivo` PROTECT | |
| `iniciada_en` · `finalizada_en` · `motivo_cierre` | bigint · bigint nulo · `usuario`/`inactividad`/`sistema`/`relevo` | Abierta = `finalizada_en` nulo |

Invariantes como índices parciales (CV-07): `ux_m09_dsa_dispositivo_abierta` UNIQUE(`dispositivo`) WHERE abierta — **INV-011**; `ux_m09_dsa_alumno_abierta` UNIQUE(`alumno_id`) WHERE abierta — **DEC-023**; `ck_m09_dsa_vigencia`; `ck_m09_dsa_cierre_motivado`. Abrir una sesión donde ya hay otra la cierra con motivo `relevo`: **el dispositivo nunca bloquea al alumno**.

### 2.3 · `m09_evento_salida`

Outbox propio (`dispositivo.*.v1`), mismo contrato que `m01_` y `m07_`: `dispositivo.registrado.v1`, `dispositivo.inventario.actualizado.v1`, `dispositivo.reconectado.v1` (latido tras más de un minuto de silencio), `dispositivo.bloqueado.v1`, `dispositivo.desbloqueado.v1`, `dispositivo.sesion.abierta.v1`, `dispositivo.sesion.cerrada.v1`. Los dos de bloqueo y los dos de sesión son propios del proyecto (el Maestro no tiene bloqueo por el profesor). Cuando exista MOD-015 las colas se unifican.

## 3 · API · `/api/dispositivos/`

Misma degradación que el resto: `DatosInvalidos` → 400 · `SinPermiso`, `DispositivoBloqueado`, `DispositivoInactivo` → 403 · `NoEncontrado` → 404 · `NodoNoInstalado` → 409 `no_instalado`. Las tabletas llegan por la IP LAN del equipo maestro (`0.0.0.0:8000`, [07 · Comunicación](../07-comunicacion-ops-student.md)).

| Ruta | Verbo | Sesión | Cuerpo → respuesta |
|---|---|---|---|
| `/api/dispositivos/` | POST | público (CAP-053: es la tableta la que se presenta) | `{identificador_hw \| identificador, nombre?, tipo?, plataforma?, version_app?}` → `201` la primera vez, `200` después. Idempotente por huella |
| `/api/dispositivos/` | GET | `SesionSiSeExige` (Q-34): OPS sin JWT lista; con JWT de alumno → 403 | `?todos=1` incluye retiradas → lista de dispositivos con `en_linea`, `bloqueado`, `sesion_abierta {id, alumno_id, iniciada_en}` |
| `/api/dispositivos/latido/` | POST | público | Igual que el registro; responde el estado (`bloqueado`, `activo`) y `servidor_en` |
| `/api/dispositivos/{id}/` | GET · PATCH | `device.read` · `device.update` | `{nombre?, tipo?, activo?}`; `activo=false` cierra la sesión de alumno (`sistema`) y las de login (`dispositivo_baja`, por los casos de uso de `acceso`) |
| `/api/dispositivos/{id}/bloquear/` · `desbloquear/` | POST | `device.block` | `{motivo?, actor?}` → dispositivo. Idempotente; bitácora `dispositivos.bloqueado` con actor y motivo |

Permisos `device.*` (sección J del Maestro; `device.block` es del proyecto) traducidos a los de MOD-001 cuando hay sesión: `device.read` y `device.block` ← `identity.device.manage` o `identity.exam_access.grant` (el profesor); `device.update` ← `identity.device.manage`. Sin sesión se permite, como en el aula y el expediente (Q-04).

## 4 · Cómo lo usan los otros módulos (`device_manager/servicios.py`)

| Función | Quién | Qué hace |
|---|---|---|
| `resolver(identificador_hw, nombre, tipo, plataforma, version_app, momento)` | aula al unirse | Reconoce o registra la tableta. `None` sin huella o sin nodo instalado: la participación sigue válida sin tableta (prototipo) |
| `abrir_sesion_alumno(alumno_id, dispositivo_id, momento)` | aula al unirse / al volver tras `salio` | La Dim Sesión Alumno. Lanza `DispositivoBloqueado` / `DispositivoInactivo` (el aula los traduce a 403 `dispositivo_bloqueado` / `dispositivo_inactivo`) |
| `cerrar_sesion_alumno(sesion_id, momento, motivo)` | aula al salir y al cerrar la clase | |
| `latido(dispositivo_id, momento)` | aula en presencia y en el sondeo `estado/` | El sondeo de la tableta es su latido: no hace falta otra llamada |
| `bloqueados_entre(ids)` | aula al lanzar, al admitir y al pintar participantes | Bloqueadas o retiradas |
| `por_id`, `por_identificador`, `listar`, `renombrar` | `acceso` en el login | Con la tableta bloqueada el login responde 403 `dispositivo_bloqueado`; retirada = como si no la hubiera dicho |

Reglas que el aula aplica con esto (probadas en `classroom_engine/tests/test_dispositivos.py`): una tableta bloqueada no entra ni se admite; el lanzamiento deja fuera a los participantes con tableta bloqueada (`excluidos_bloqueados`) y, si no queda nadie, responde 409 `sin_participantes_admitidos` con la lista; salir de clase cierra la sesión de alumno y volver la reabre; cerrar la clase cierra todas.

## 5 · Pruebas

`device_manager/tests/test_api_dispositivos.py` (registro idempotente y datos de la tableta, latido y `reconectado`, nodo sin instalar, listado por perfil, bloqueo reversible con bitácora y login denegado, baja que cierra sesiones, INV-011 y DEC-023 por relevo, tableta bloqueada sin sesión de alumno) y `test_arquitectura.py` (dominio y aplicación sin framework, vistas sin ORM, tablas `m09_*`, `acceso` sin `Dispositivo` y su FK apuntando a `m09_dispositivo`).

## 6 · Lo que queda abierto

Las preguntas 4 a 8 de `specs/analisis/borrador-01-lanzamiento.md` §5: `organizacion_id` en `dispositivo`, `rel_alumno_grupo` frente a `m01_miembro_grupo`, qué es `nodo_maestro_id`, si bastan `bloqueado` + `activo` como ciclo de vida en el MVP, y si batería/red se persisten o siguen el patrón efímero de la presencia (Q-28). Ninguna bloquea el control de lanzamientos de hoy.
