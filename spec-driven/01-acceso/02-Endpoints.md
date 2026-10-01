# 02 · Módulo de acceso y usuarios · Endpoints (APIViews)

| Campo | Valor |
|---|---|
| Prefijo | `/api/acceso/` (incluido desde `avacom_lms/urls.py`) · 38 rutas (6 de ellas, `padron/`, nacieron el 2026-10-01) |
| Estilo | `APIView` de DRF, JSON, sin `ModelSerializer` hacia el dominio: las vistas traducen HTTP ↔ casos de uso |
| Autenticación | `Authorization: Bearer <JWT>`; la clase `AutenticacionJwt` resuelve la sesión (única, con rol efectivo, sujeta a inactividad) y construye un `Principal` |
| Autorización | Cada vista declara `permiso` (`identity.*`) y calcula el `objetivo`; la decisión la toma `PoliticaAutorizacion` (dominio), nunca la vista |
| Modelo | [01 · Modelado de datos](01-modelado-datos.md) · Alineación: [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md) |
| Estado | Implementado en `backend/acceso/interfaces/` con pruebas en `backend/acceso/tests/` |

---

## 0 · Convenciones

### 0.1 · Respuestas de error

```json
{ "detail": "Texto legible para el docente", "codigo": "credenciales_invalidas" }
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `datos_invalidos`, `secreto_debil`, `identificador_duplicado`, `politica_invalida` | Validación de entrada o de reglas de dominio |
| 401 | `sesion_requerida`, `sesion_invalida`, `sesion_expirada`, `sesion_revocada`, `sesion_inactiva`, `sesion_cerrada_otro_dispositivo`, `credenciales_invalidas` | Sin pase, pase inválido, sesión cerrada (con su motivo) o login fallido. Se envía `WWW-Authenticate: Bearer` |
| 403 | `sin_permiso`, `debe_cambiar_credencial`, `sesion_temporal_limitada` | La política denegó. **Fuera de alcance también es 403**: regla del Maestro «acceso denegado, nunca objeto inexistente». Incluye `permiso`, `alcance_requerido`, `alcance_concedido` |
| 404 | `no_encontrado` | El recurso **no existe** |
| 409 | `conflicto`, `ya_instalado`, `no_instalado` | Estado incompatible (p. ej. reactivar una cuenta dada de baja, BR-025) |
| 423 | `usuario_bloqueado` | Bloqueo automático (con `reintentar_en_seg`) o manual |

### 0.2 · Fechas

Milisegundos desde época (bigint), como el resto del backend (CV-03).

### 0.3 · El `Principal`

```python
Principal(usuario_id, organizacion_id, rol_id, rol_codigo, menu, nivel, sesion_id, clase_sesion,
          debe_cambiar_credencial, dispositivo_id, evaluacion_ref)
```

`rol_id` / `rol_codigo` / `menu` son los del **rol efectivo de la sesión** (BR-021), no necesariamente el rol principal de la persona.

Reglas transversales aplicadas antes de cualquier permiso: credencial provisional ⇒ sólo `identity.password.change_own` y `identity.session.revoke_own`; sesión `TEMPORAL` ⇒ sólo rendir la evaluación.

---

## 1 · Rutas sin sesión

### 1.1 · `GET /api/acceso/configuracion/`

Lo que la tableta necesita para pintar PAN-101. **Sin PII.** Incluye las excepciones por nivel educativo (BR-024).

```json
{
  "instalado": true,
  "organizacion": { "codigo": "IE-SANJOSE", "nombre": "IE San José", "pais": "CO", "idioma": "es", "locale": "es-CO" },
  "perfiles": {
    "student": { "tipo_identificador": "CODIGO_ESTUDIANTIL", "tipo_secreto": "PIN", "longitud_minima": 6,
                 "permite_acceso_temporal": true, "inactividad_min": 30,
                 "niveles": { "preescolar": { "tipo_identificador": "CODIGO_ESTUDIANTIL", "tipo_secreto": "AVATAR", "longitud_minima": 4, "permite_acceso_temporal": true, "inactividad_min": 30 } } },
    "teacher": { "tipo_identificador": "DNI", "tipo_secreto": "PASSWORD", "longitud_minima": 8, "permite_acceso_temporal": false, "inactividad_min": 20, "niveles": {} },
    "admin": { "...": "..." }, "reports": { "...": "..." }, "technician": { "...": "..." }
  },
  "duracion_sesion_min": 240, "inactividad_min": 30,
  "niveles_educativos": ["preescolar", "primaria", "secundaria", "bachillerato", "preuniversitario"],
  "claves_derivadas": false
}
```

### 1.2 · `POST /api/acceso/instalacion/`

Primer arranque (JRN-001). Sólo mientras no exista organización (409 `ya_instalado` después). Crea organización, las cinco políticas por perfil y el primer administrador. Devuelve `password_inicial` **una sola vez** si no se envió contraseña (PAN-204).

### 1.3 · Dispositivos → MOD-009

Desde el 2026-09-28 el registro idempotente de la tableta vive en **MOD-009 · Device Manager**: `POST /api/dispositivos/` (`{ "identificador_hw" | "identificador", "nombre", "tipo", "plataforma", "version_app" }` → 201 la primera vez, 200 después), con inventario, latido y bloqueo. Ver [03-device-manager](../03-device-manager/00-modelo-y-api.md). Este módulo sólo lo lee al abrir sesión: `dispositivo` en el login sigue siendo la huella, y una tableta bloqueada responde `403 dispositivo_bloqueado`.

### 1.4 · `POST /api/acceso/sesiones/` · Autenticar (FUN-004, FUN-005)

```json
{ "identificador": "122499", "secreto": "691302", "dispositivo": "a8f3…", "rol": "" }
```

`rol` es opcional: si la persona tiene varios roles vigentes elige con cuál trabaja (BR-021); si se omite, entra con su rol principal.

→ `200`

```json
{
  "token": "eyJ…", "tipo": "Bearer", "expira_en": 1789014400000, "sesion_id": "…", "inactividad_min": 30,
  "sesion_anterior": { "sesion_id": "…", "dispositivo": "tableta-03", "emitida_en": 1789000000000, "cerrada_en": 1789000600000 },
  "roles_disponibles": ["STUDENT"],
  "usuario": { "id": "…", "alias": "Juan P.", "rol": "STUDENT", "menu": "student", "nivel": 1,
               "debe_cambiar_credencial": false, "clase_sesion": "NORMAL", "evaluacion_ref": null, "provisional": false }
}
```

**Sesión única.** Si la persona tenía otra sesión abierta, se cierra con motivo `otro_dispositivo` y `sesion_anterior` trae de dónde se cerró, para mostrar PAN-103 / MSG-020. Si otra persona tenía sesión en esta misma tableta, se cierra con `dispositivo_compartido` (INV-011). Si no había nada que cerrar, `sesion_anterior` es `null`.

Errores: `401 credenciales_invalidas` (mismo mensaje y coste para inexistente, tipo no permitido, rol no asignado y secreto incorrecto; trae `intentos_restantes`), `423 usuario_bloqueado` con `reintentar_en_seg` (FUN-007).

### 1.5 · `POST /api/acceso/autorizaciones-temporales/canjear/`

Opción B: `{ "codigo": "834195", "dispositivo": "…" }`. Opción A: `{ "grant_id": "…", "token": "…", "dispositivo": "…" }`. → `200` como §1.4 con `clase_sesion: "TEMPORAL"`.

---

## 2 · Identidad propia

### 2.1 · `GET /api/acceso/yo/`

```json
{
  "usuario": { "id": "…", "alias": "Prof. Gómez", "rol": "TEACHER", "menu": "teacher", "nivel": 2, "estado": "ACTIVO",
               "provisional": false, "nivel_educativo": null, "persona": { "nombres": "Luis", "apellidos": "Gómez" } },
  "identificadores": [ { "tipo": "DNI", "valor": "80123456", "es_login": true, "emisor": "IE-SANJOSE", "principal": true } ],
  "rol_efectivo": { "codigo": "TEACHER", "menu": "teacher", "alcance_asignacion": "ORGANIZATION" },
  "roles_disponibles": [ { "id": "…", "rol": "TEACHER", "menu": "teacher", "alcance_tipo": "ORGANIZATION", "alcance_id": null, "desde": 1789000000000, "hasta": null },
                         { "id": "…", "rol": "REPORTS", "menu": "reports", "alcance_tipo": "LEVEL", "alcance_id": "secundaria", "desde": 1789000000000, "hasta": 1791000000000 } ],
  "permisos": [ { "codigo": "identity.password.reset", "alcance": "ASSIGNED_GROUPS", "origen": "rol", "vigente_hasta": null },
                { "codigo": "audit.read", "alcance": "ORGANIZATION", "origen": "adicional", "vigente_hasta": 1789014400000 } ],
  "grupos": [ { "id": "…", "codigo": "8A", "nombre": "Octavo A", "periodo": "2026", "nivel_clave": "secundaria", "papel": "DOCENTE" } ],
  "sesion": { "id": "…", "clase": "NORMAL", "rol": "TEACHER", "expira_en": 1789014400000, "dispositivo": "master", "motivo_cierre": null }
}
```

### 2.2 · `PUT /api/acceso/yo/credencial/`

`{ "secreto_actual", "secreto_nuevo" }`. Permiso `identity.password.change_own`. Revoca las demás sesiones con motivo `credencial_cambiada`.

### 2.3 · `DELETE /api/acceso/sesiones/actual/`

→ `204`. Motivo `persona`.

---

## 3 · Sesiones

| Ruta | Verbo | Permiso · objetivo | Nota |
|---|---|---|---|
| `/api/acceso/sesiones/?usuario=<id>&todas=1` | GET | `identity.session.read` | Cada fila trae `rol` (efectivo), `dispositivo`, `motivo_cierre` |
| `/api/acceso/sesiones/{id}/` | DELETE | `identity.session.revoke` · dueño | Motivo `profesor` o `administrador` según el nivel del actor |
| `/api/acceso/usuarios/{id}/sesiones/` | DELETE | `identity.session.revoke` · el usuario | **FUN-010**: revoca todas. → `200 { "sesiones_revocadas": n }` |

---

## 4 · Usuarios

### 4.1 · `GET /api/acceso/usuarios/?grupo=…&rol=STUDENT&estado=ACTIVO`

Permiso `identity.user.read`. La lista se recorta por alcance (propio, sus grupos, su nivel, organización). Cada fila trae `roles` (asignaciones vigentes), `provisional`, `nivel_educativo`, `bloqueado_hasta`, `debe_cambiar_credencial`, `tipo_secreto` e `identificadores` con `emisor` y `principal`.

### 4.2 · `POST /api/acceso/usuarios/` · Crear usuario (FUN-001)

```json
{
  "rol": "STUDENT", "alias": "Juan P.",
  "persona": { "nombres": "Juan", "apellidos": "Pérez", "fecha_nacimiento": "2012-04-09" },
  "identificadores": [ { "tipo": "CODIGO_ESTUDIANTIL", "valor": "122499", "es_login": true, "principal": true },
                       { "tipo": "DNI", "valor": "1.020.334.556", "es_login": false } ],
  "secreto": "691302", "secreto_definitivo": true, "grupo_id": "…"
}
```

- `identificadores` puede omitirse: el nodo emite una `CLAVE_INSTALACION` (DEC-049). `emisor` por defecto es el código de la organización; si nadie marca `principal`, lo es el primero de login.
- **Admisión nominal (JRN-007, MSG-023)**: `{ "rol": "STUDENT", "alias": "Lucía", "provisional": true, "grupo_id": "…" }`, sin identificadores ni persona. Crea una cuenta provisional con clave de instalación; se cierra con §4.4.
- El docente (`ASSIGNED_GROUPS`) sólo crea estudiantes y debe indicar un grupo propio. La inscripción se hace **antes** de fijar la credencial, porque el grupo o su nivel pueden cambiar el reglamento (avatar en preescolar).
- → `201` con `secreto_inicial` si se generó. La credencial nace provisional salvo `secreto_definitivo: true`.

### 4.3 · `POST /api/acceso/usuarios/importar/` · Importar usuarios (FUN-003, CAP-003)

```json
{ "contenido": "rol,alias,nombres,apellidos,tipo_identificador,identificador,grupo,secreto\nSTUDENT,,Carlos,Torres,CODIGO_ESTUDIANTIL,150001,8A,\n…",
  "delimitador": ",", "grupo_id": "" }
```

También acepta `filas: [ {…}, … ]` ya parseadas. Permiso `identity.user.import` (organización). Precondición del Maestro: el archivo pasa la validación de columnas (si no, `400` con `columnas_esperadas`).

→ `200`

```json
{ "resumen": { "total": 5, "creados": 3, "existentes": 1, "rechazadas": 1 },
  "creados": [ { "fila": 1, "id": "…", "alias": "Carlos T.", "identificador": "150001", "grupo": "8A", "secreto_inicial": "204915" } ],
  "existentes": [ { "fila": 3, "id": "…", "alias": "Juan P.", "identificador": "122499" } ],
  "rechazadas": [ { "fila": 4, "motivo": "El grupo NO-EXISTE no existe.", "codigo": "datos_invalidos", "identificador": "150003" } ] }
```

Un identificador ya existente **fusiona**: no duplica la persona. El lote es una sola transacción; las rechazadas no lo abortan (MSG-065). Mismo caso de uso que `manage.py acceso_importar padron.csv --actor-dni …`.

### 4.4 · `POST /api/acceso/usuarios/{id}/vincular/`

`{ "usuario_definitivo_id": "…" }`. Permiso `identity.user.update` sobre ambas. La provisional pasa a `RETIRADO` con `vinculado_a`, sus sesiones se cierran. → `200 { "provisional_id", "definitivo_id", "sesiones_revocadas" }`. `409` si no es provisional.

### 4.5 · `GET` · `PATCH /api/acceso/usuarios/{id}/`

`PATCH` acepta `alias`, `idioma`, `estado` (`ACTIVO`/`SUSPENDIDO`/`RETIRADO`), `persona`, `identificadores` (reemplazo: los anteriores se **retiran**, no se borran). Salir de `ACTIVO` revoca sesiones (`estado_cuenta`). **BR-025**: de `RETIRADO` no se vuelve (409).

### 4.6 · Roles (FUN-002)

| Ruta | Verbo | Permiso | Cuerpo / respuesta |
|---|---|---|---|
| `/api/acceso/usuarios/{id}/roles/` | GET | `identity.user.read` | Asignaciones vigentes con `alcance_tipo`, `alcance_id`, `desde`, `hasta` |
| `/api/acceso/usuarios/{id}/roles/` | POST | `identity.role.assign` | `{ "rol": "REPORTS", "alcance_tipo": "LEVEL", "alcance_id": "secundaria", "vigente_hasta": 1791000000000, "principal": false }` → `201`. El actor no puede asignar un nivel superior al suyo ni un alcance mayor que el de su propia asignación. `principal: true` cambia el rol por defecto y revoca sesiones (`rol_cambiado`) |
| `/api/acceso/usuarios/{id}/rol/` | PUT | `identity.role.assign` | Compatibilidad: fija el rol principal con alcance de organización |
| `/api/acceso/usuarios/{id}/roles/{asignacion_id}/` | DELETE | `identity.role.assign` | Revoca la asignación; nunca deja a la persona sin rol (409) |

CAP-006 (suplente): `POST …/roles/` con `rol: "TEACHER"`, `alcance_tipo: "ASSIGNED_GROUPS"`, `alcance_id: <grupo>`, `vigente_hasta: <fin>`.

### 4.7 · Escaladas temporales (BR-101)

| Ruta | Verbo | Permiso | Cuerpo / respuesta |
|---|---|---|---|
| `/api/acceso/usuarios/{id}/escaladas/` | GET | `identity.user.read` | Vigentes y revocadas |
| `/api/acceso/usuarios/{id}/escaladas/` | POST | `identity.escalation.grant` | `{ "permiso": "audit.read", "alcance": "ORGANIZATION", "motivo": "Coordinadora académica 2026", "vigente_hasta": 1789014400000 }` → `201`. `vigente_hasta` **obligatorio**, máximo 24 h; el alcance no supera el techo del permiso ni el del actor; **no hay autoconcesión** (403) |
| `/api/acceso/usuarios/{id}/escaladas/{permiso}/` | DELETE | `identity.escalation.grant` | → `204` |

### 4.8 · `POST /api/acceso/usuarios/{id}/credencial/restablecer/` (FUN-006, CAP-004)

Permiso `identity.password.reset`. `{ "secreto": "204915" }` opcional. → `200 { "secreto_provisional", "tipo_secreto", "debe_cambiar": true, "sesiones_revocadas" }`. Se devuelve **una sola vez**.

### 4.9 · `POST /api/acceso/usuarios/{id}/desbloquear/` (FUN-008)

Permiso `identity.user.unlock`. → `200 { "estado": "ACTIVO", "bloqueado_hasta": null }`.

---

## 5 · Acceso temporal a examen

| Ruta | Verbo | Permiso | Nota |
|---|---|---|---|
| `/api/acceso/autorizaciones-temporales/` | POST | `identity.exam_access.grant` | `{ "usuario_id", "tipo": "DISPOSITIVO" \| "CODIGO", "dispositivo_id"?, "evaluacion_ref"?, "minutos": 5, "motivo" }` → `201` con `entrega` (`{grant_id, token}` o `{codigo}`) |
| `/api/acceso/autorizaciones-temporales/?usuario=…&vigentes=1` | GET | `identity.exam_access.grant` | Sin secretos |
| `/api/acceso/autorizaciones-temporales/{id}/` | DELETE | `identity.exam_access.grant` | Revoca el pase y, si produjo sesión, la cierra (`profesor`) |

---

## 6 · Catálogos y configuración

| Ruta | Verbo | Permiso | Nota |
|---|---|---|---|
| `/api/acceso/roles/` | GET | `identity.role.read` | Los cinco de sistema + los del colegio |
| `/api/acceso/roles/` | POST | `identity.role.manage` | Clona una plantilla y ajusta `permisos: [{codigo, alcance}]` |
| `/api/acceso/permisos/` | GET | `identity.role.read` | Catálogo con `alcance_maximo` y `sensible` |
| `/api/acceso/politicas/` | GET | `identity.policy.manage` | Generales y por nivel |
| `/api/acceso/politicas/{perfil}/` | PUT | `identity.policy.manage` | Columnas de la política, incl. `inactividad_min`. **`?nivel=preescolar`** crea o edita la excepción del nivel (BR-024) |
| `/api/acceso/grupos/` | GET, POST | `identity.group.read` / `identity.group.manage` | `{ "codigo", "nombre", "periodo", "nivel_clave"?, "politica_credencial_id"? }` |
| `/api/acceso/grupos/{id}/` | GET, PATCH | idem | Detalle con `miembros` (incluye `provisional`) |
| `/api/acceso/grupos/{id}/miembros/` · `…/{usuario_id}/` | POST, DELETE | `identity.group.member.manage` | Un docente sólo añade o retira estudiantes de sus grupos |
| `/api/dispositivos/` (MOD-009) | GET | `identity.exam_access.grant` o `identity.device.manage` | Movido a `device_manager` el 2026-09-28; mismos permisos traducidos desde `device.read` |
| `/api/dispositivos/{id}/` (MOD-009) | PATCH | `identity.device.manage` | Dar de baja cierra sus sesiones de login (`dispositivo_baja`, por este módulo) y su sesión de alumno |

---

## 6 bis · Padrón del aula (pantalla «Grupos» de OPS)

Estudiantes y grupos en pocas llamadas, pensadas para una pantalla táctil. No hay modelo propio: `acceso/aplicacion/padron.py` compone `CrearGrupo`, `CrearUsuario`, `AgregarMiembro` y `RetirarMiembro` ([01 · Modelado §3.28](01-modelado-datos.md)). **Con sesión** actúa quien firma el JWT, con sus permisos; **sin sesión** (Q-34 abierta) actúa la primera cuenta `ADMIN` activa; con `AVACOM_LMS_EXIGIR_SESION=1` un anónimo recibe 401.

| Ruta | Verbo | Cuerpo / respuesta |
|---|---|---|
| `/api/acceso/padron/` | GET | `{ instalado, organizacion{codigo,nombre}, grupos[{id,codigo,nombre,periodo,nivel_clave,activo,estudiantes[{id,alias,estado,provisional}],docentes}], sin_grupo[{id,alias}] }`. Nodo vacío: `{ instalado:false, … }` con **200** (no es un error). Con sesión, sólo los grupos que el alcance permite |
| `/api/acceso/padron/preparar/` | POST | Sin cuerpo. Crea la organización `AULA-PRUEBA` (día cero de prueba). `201 { organizacion }`; `409` si el nodo ya está instalado |
| `/api/acceso/padron/grupos/` | POST | `{ "nombre", "codigo"?, "periodo"?, "nivel_clave"? }`. El código sale del nombre («Sexto A» → `SEXTO-A`) y el periodo es el año si no se dan. `201`; `409` si ya existe ese código en ese periodo; `403` si el rol no tiene `identity.group.manage` |
| `/api/acceso/padron/estudiantes/` | POST | `{ "nombres", "apellidos"?, "documento"?, "pin"?, "grupo_id" }` → `201 { id, alias, grupo_id, identificador, secreto_inicial? }`. `secreto_inicial` (PIN generado) sale **una sola vez**. `400 identificador_duplicado`; `404` grupo inexistente; `403` grupo ajeno |
| `/api/acceso/padron/grupos/{id}/estudiantes/` | POST | `{ "usuario_id" }`: agrega a un estudiante existente (o lo reincorpora, reabriendo su pertenencia). `201`, o `200` con `ya_estaba: true` |
| `/api/acceso/padron/grupos/{id}/estudiantes/{usuario_id}/` | DELETE | Lo saca del grupo (`hasta = ahora`); la persona no se borra. `204` |

---

## 7 · Integración con el resto del backend

| Elemento | Cambio |
|---|---|
| `REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` | `acceso.interfaces.autenticacion.AutenticacionJwt`. Sin cabecera → anónimo; las rutas del expediente no cambian |
| `AVACOM_LMS_EXIGIR_SESION` | `0` por defecto (Q-34) |
| `/health/` | `"acceso": { "instalado", "claves_derivadas" }` |
| `m19_auditoria` | Acciones `identidad.*` (sesión abierta/cerrada, cuenta bloqueada/desbloqueada, credencial, rol, escalada, importación, vinculación…) |
| Comandos | `acceso_instalar` (§1.2) y `acceso_importar` (§4.3) |

---

## 8 · Trazabilidad casos de uso ↔ rutas ↔ Maestro

| Caso de uso | Ruta | Maestro |
|---|---|---|
| `InstalarNodo` | §1.2, comando | JRN-001, PAN-204 |
| `ConsultarConfiguracion` | §1.1 | PAN-101, BR-024 |
| `RegistrarDispositivo` | §1.3 | MOD-009 |
| `AutenticarUsuario` | §1.4 | FUN-004, FUN-005, FUN-007, BR-021, TST-027 |
| `ResolverPrincipal` | todas | FUN-009, FUN-011 |
| `CanjearAccesoTemporal` | §1.5 | CAP-002 (sesión temporal), TST-074 |
| `ConsultarIdentidad` | §2.1 | PAN-020, PAN-100 |
| `CambiarCredencialPropia` | §2.2 | — |
| `RevocarSesion` · `RevocarSesionesDeUsuario` · `ListarSesiones` | §2.3, §3 | FUN-010 |
| `CrearUsuario` | §4.2 | FUN-001, DEC-049, MSG-023 |
| `ImportarUsuarios` | §4.3, comando | FUN-003, CAP-003, JRN-003, PAN-220, MSG-065 |
| `VincularUsuarioProvisional` | §4.4 | JRN-007 |
| `ListarUsuarios` · `VerUsuario` · `ActualizarUsuario` | §4.1, §4.5 | PAN-221, BR-025 |
| `AsignarRol` · `RevocarRolAsignado` | §4.6 | FUN-002, CAP-005, CAP-006, BR-021 |
| `OtorgarEscalada` · `RevocarEscalada` | §4.7 | BR-101, PAN-241, MSG-052/053 |
| `RestablecerCredencial` | §4.8 | FUN-006, CAP-004 |
| `DesbloquearUsuario` | §4.9 | FUN-008 |
| `OtorgarAccesoTemporal` · `ListarAutorizaciones` · `RevocarAccesoTemporal` | §5 | CAP-002, CAP-004 |
| `ListarRoles` · `ListarPermisos` · `CrearRol` | §6 | PAN-222, TST-066 |
| `ListarPoliticas` · `ConfigurarPolitica` | §6 | BR-023, BR-024 |
| `ListarGrupos` · `VerGrupo` · `CrearGrupo` · `ActualizarGrupo` · `AgregarMiembro` · `RetirarMiembro` | §6 | MOD-002 (replicado) |
| `ListarDispositivos` · `ActualizarDispositivo` | §6 | MOD-009 (replicado) |

---

## 9 · Pruebas que acompañan al contrato

| Suite | Qué comprueba |
|---|---|
| `test_arquitectura` | Dominio y aplicación sin frameworks |
| `test_politicas` | Cuatro alcances, tope por asignación, los cinco roles, regla 403, avatar, inactividad, bloqueo |
| `test_seguridad` | AES-GCM, HMAC, Argon2id, JWT |
| `test_api_sesiones` | Instalación, login, bloqueo, **sesión única**, **dispositivo compartido**, **inactividad**, **reinicio**, revocación total |
| `test_api_usuarios` | Creación por alcance, **importación**, **admisión nominal**, credenciales, **roles con alcance**, **escaladas**, grupos, políticas por nivel, baja irreversible, retiro de identificadores |
| `test_api_temporal` | Opciones A y B del pase de examen |
| `test_api_padron` | Padrón de OPS: nodo vacío, aula de prueba, grupo con código y periodo por defecto, estudiante con y sin documento/PIN, documento repetido, matricular y retirar, **reingreso a un grupo**, visible para el modo de estudio, anónimo rechazado con sesión obligatoria, y permisos de docente (grupo propio sí, ajeno y crear grupo no) |
| `test_outbox` | Outbox transaccional y nomenclatura `identidad.*.v1` |
