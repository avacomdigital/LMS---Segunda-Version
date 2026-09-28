# 01 · Módulo de acceso y usuarios · Modelado de datos

| Campo | Valor |
|---|---|
| Módulo | `acceso` · **MOD-001 · Identity & Access** del Documento Maestro (DOM-001 · Identidad y Organización) |
| Estado | Especificado e implementado en `backend/acceso/`; alineado con el Maestro según [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md) |
| Prefijo de tablas | `m01_` (CV-01) · 18 tablas |
| Plataforma | Python 3.12 · Django 5.2.3 · DRF 3.16.1 · SQLite · `argon2-cffi` · `cryptography` · `PyJWT` |
| Cliente | .NET MAUI (AVACOM OPS Master en Windows, AVACOM Student en Windows/Android), sin internet, sin teclado en el nodo principal |
| Decisiones que cierra | Q-04 (autenticación mínima) y Q-24 (tabla preparatoria de identidad) |
| Documentos hermanos | [02 · Endpoints](02-Endpoints.md) · [03 · Casos de uso](03-casos-de-uso-backend.md) · [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md) · [Presentación](../../specs/presentaciones/acceso.html) |

---

## 0 · Resumen ejecutivo

El aula AVACOM funciona sin internet. Todo lo que hace falta para **decidir quién es alguien y qué puede hacer** tiene que estar en el SQLite del equipo maestro. Este documento define ese mínimo en tercera forma normal, siguiendo MOD-001 del Documento Maestro:

1. **Una persona, varios roles, un solo rol efectivo por sesión (BR-021).** Los roles se asignan con alcance concreto y vigencia (`m01_usuario_rol`); al entrar se elige con cuál se trabaja. La asignación acota al rol.
2. **Cinco roles de fábrica**: Alumno, Profesor, Administrador, Reportes y Técnico AVACOM, con el catálogo de permisos `identity.*` y **cuatro alcances**: propio (`SELF`), grupo (`ASSIGNED_GROUPS`), nivel educativo (`LEVEL`) e instalación (`ORGANIZATION`). El contexto («¿es mi estudiante?») se **calcula** con la pertenencia a grupos; no hay tabla de permisos por contexto.
3. **Una sola sesión abierta por persona** en toda la instalación, y **cero o una por dispositivo compartido** (INV-011). Abrir en otro aparato cierra la anterior y lo avisa.
4. **Reglamento de acceso por colegio, por perfil y por nivel educativo (BR-023, BR-024)**: con qué identificador se entra (documento, matrícula, clave de instalación, correo), qué secreto se usa (PIN, contraseña o **avatar** para preescolar), bloqueo por intentos, duración e **inactividad** de la sesión.
5. **Identidad en tres capas (DEC-048)**: identificador interno inmutable, identificadores externos con emisor y uno principal, y credenciales que no identifican fuera de la instalación. Nunca existe una persona sin identificador externo (DEC-049).
6. **Argon2id para todo secreto; AES-256-GCM para todo dato personal; HMAC-SHA-256 para poder buscar lo cifrado.**
7. **Recuperación sin correo ni internet**: restablecer la credencial desde el aula, acceso temporal a examen (tableta autorizada o código de un solo uso) y **admisión nominal** de un alumno sin credencial a la mano, con vinculación posterior.
8. **Escaladas temporales (BR-101)** con motivo, caducidad obligatoria y concedente distinto del receptor. **Carga masiva** desde archivo (FUN-003).
9. **Nada se borra (CV-05)**: identificadores se retiran, asignaciones se revocan, cuentas pasan a `RETIRADO` y no vuelven (BR-025). Todo cambio publica un evento `identidad.*.v1` en la cola de salida dentro de la misma transacción.
10. **Arquitectura hexagonal dentro del monolito modular.** Dominio y casos de uso no importan Django; ORM, DRF, Argon2, AES y JWT son adaptadores sustituibles.

---

## 1 · Requisitos que gobiernan el modelo

| # | Requisito | Dónde se cumple |
|---|---|---|
| R-01 | Cinco tipos de usuario (Alumno menor sin correo, Profesor, Administrador, Reportes, Técnico) | `m01_rol.menu_principal`; `m01_identificador_usuario` admite entrar sin email |
| R-02 | El colegio configura identificador y secreto por perfil y por nivel educativo | `m01_politica_credencial` (`perfil`, `nivel_clave`); `m01_grupo.politica_credencial_id` para excepciones por grupo |
| R-03 | Profesor: documento + contraseña (≥ 8, mayúscula, símbolo) | Política sembrada `teacher` |
| R-04 | RBAC claro; el menú varía por rol; varios roles por persona, uno efectivo | `m01_rol`, `m01_rol_permiso`, `m01_usuario_rol`, `m01_sesion.rol_id` |
| R-05 | Permisos adicionales sin tabla contextual gigante | `m01_usuario_permiso` (escalada) con `alcance`, `motivo` y `vigente_hasta` |
| R-06 | Alcances como regla, no como tabla | `SELF` / `ASSIGNED_GROUPS` / `LEVEL` / `ORGANIZATION` evaluados por `PoliticaAutorizacion` con `m01_miembro_grupo` y `m01_usuario_rol` |
| R-07 | Autorización 100 % offline | Todas las tablas en el SQLite local; el JWT se firma y verifica en el nodo |
| R-08 | Sesión de 4 h, inactividad configurable, una sola por persona | `duracion_sesion_min = 240`, `inactividad_min`, `abrir_sesion()` |
| R-09 | Recuperación sin email/SMS/internet | Restablecer credencial, `m01_autorizacion_temporal`, cuentas provisionales |
| R-10 | Hashing por estándar; OWASP Top 10 | Argon2id, bloqueo por intentos, auditoría, cifrado de PII, autorización centralizada |
| R-11 | Campos ISO | `pais` ISO 3166-1 alpha-2, `idioma` ISO 639-1, `locale` BCP 47 |
| R-12 | Hexagonal + Use Case + Repository + UoW + Policy + Value Objects + Outbox | §6 y `backend/acceso/` |
| R-13 | Nomenclatura del Maestro | Permisos `identity.*`, eventos `identidad.*.v1`, tablas `m01_*` |

---

## 2 · Opciones consideradas

### 2.1 · Cómo representar a las personas

| Opción | Ventaja | Inconveniente | Decisión |
|---|---|---|---|
| A · Una tabla por tipo | Campos específicos sin nulos | Triplica credenciales, sesiones y auditoría; una persona con dos papeles existe dos veces | Rechazada |
| B · Una tabla `usuario` con columna `tipo` | Sencilla | Mezcla cuenta con persona; no es 3FN con más de un identificador | Rechazada |
| **C · cuenta + persona (PII cifrada) + identificadores externos (1..n) + asignaciones de rol (1..n)** | 3FN, PII aislada, entra con documento o matrícula, acumula roles sin duplicarse | Más joins (triviales en SQLite local) | **Elegida** (coincide con DEC-048 y `m01_persona_rol`) |

### 2.2 · Cómo representar los permisos

| Opción | Decisión |
|---|---|
| A · Permisos fijos en código por rol | Rechazada: no admite adicionales ni roles del colegio |
| B · RBAC + tabla `usuario_permiso_contexto` (usuario, permiso, grupo, curso, estudiante, recurso, clase, dispositivo…) | Rechazada explícitamente: crece sin límite, casi todo nulo |
| **C · RBAC + alcance por permiso + asignación de rol con alcance + contexto derivado de pertenencia** | **Elegida**. `rol_permiso(rol, permiso, alcance)`, `usuario_rol(usuario, rol, alcance_tipo, alcance_id, vigencia)` y `usuario_permiso` para escaladas |

### 2.3 · Dónde vive la sesión

| Opción | Decisión |
|---|---|
| JWT sin estado | Rechazada: no se puede cerrar la sesión de un estudiante ni imponer la sesión única |
| Sesión opaca sin JWT | Rechazada: el cliente MAUI espera un portador estándar |
| **JWT HS256 + fila `m01_sesion` con `jti` y rol efectivo** | **Elegida**: estándar, verificable offline, revocable, sobrevive al reinicio del nodo (FUN-011) |

### 2.4 · Cómo guardar documento y nombre

| Opción | Decisión |
|---|---|
| Texto plano | Rechazada: el SQLite viaja en un portátil de colegio; datos de menores |
| Sólo hash | Rechazada: hay que mostrar el nombre y verificar el documento |
| **AES-256-GCM (recuperable) + HMAC-SHA-256 (buscable) con claves separadas** | **Elegida** |

### 2.5 · Cómo contar los intentos fallidos

| Opción | Decisión |
|---|---|
| Contador `intentos_fallidos` en la credencial (como en el Maestro) | Rechazada: desbloquear borra la evidencia de lo que pasó |
| **Registro de intentos + cálculo** | **Elegida**: el bloqueo se calcula sobre `m01_intento_acceso`; desbloquear inserta una fila `DESBLOQUEO` |

---

## 3 · Modelo de datos (3FN)

### 3.0 · Diagrama

```
 m01_organizacion 1───n m01_politica_credencial (por perfil y, opcionalmente, por nivel educativo)
        │1                         │0..1
        n                          │
   m01_usuario n───1 m01_rol 1───n m01_rol_permiso n───1 m01_permiso
     │1 │1 │1 │1 │1                 │1                       │1
     │  │  │  │  └──n m01_usuario_rol n─┘ (rol + alcance_tipo + alcance_id + vigencia)
     │  │  │  └─────n m01_usuario_permiso (escalada) n──────┘
     │  │  └────────n m01_identificador_usuario (emisor, principal, retirado_en)
     │  └───────────1 m01_persona (cifrada)
     ├──────────────n m01_credencial (PIN · PASSWORD · AVATAR)
     ├──────────────n m01_sesion (rol efectivo, clase, motivo_cierre) n───0..1 m01_dispositivo
     ├──────────────n m01_intento_acceso
     ├──────────────n m01_autorizacion_temporal (usuario, otorgada_por, dispositivo?, sesion?)
     ├──────────────n m01_miembro_grupo n───1 m01_grupo (nivel_clave, politica?) n───1 m01_organizacion
     └──0..1 vinculado_a ─► m01_usuario (admisión nominal)
 m01_evento_salida (outbox, sin FK: agregado_tipo + agregado_id)
```

Convenciones que se conservan: fechas en **bigint milisegundos** (CV-03), claves de texto (CV-02, hoy UUID), columnas `*_cifrado` para AES-GCM y `*_hmac` para índice ciego, ninguna columna de texto plano con PII, **nada se borra** (CV-05).

### 3.1 · `m01_organizacion` · Organizacion

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | UUID |
| `codigo` | char(32) UNIQUE | Corto, para mostrar («IE-SANJOSE»). Es el `emisor` por defecto de los identificadores |
| `nombre` | char(200) | |
| `pais` | char(2) | ISO 3166-1 alpha-2 |
| `idioma` | char(8) | ISO 639-1 |
| `locale` | char(16) | BCP 47 |
| `zona_horaria` | char(64) | IANA |
| `creado_en` | bigint | |

### 3.2 · `m01_politica_credencial` · PoliticaCredencial

El reglamento de acceso (BR-023, BR-024). Una fila **general por perfil** y, opcionalmente, **excepciones por nivel educativo** para el perfil de estudiantes.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `organizacion_id` | FK | |
| `perfil` | char(16) | `student` / `teacher` / `admin` / `reports` / `technician` |
| `nivel_clave` | char(24) null | `preescolar` · `primaria` · `secundaria` · `bachillerato` · `preuniversitario`. Null = política general |
| `tipo_identificador` | char(24) | `DNI` / `CODIGO_ESTUDIANTIL` / `CLAVE_INSTALACION` / `EMAIL` / `CUALQUIERA` |
| `tipo_secreto` | char(16) | `PIN` / `PASSWORD` / `AVATAR` |
| `longitud_minima` | smallint | 6 para PIN, 8 para contraseña docente, 12 para administración |
| `exige_mayuscula`, `exige_minuscula`, `exige_digito`, `exige_simbolo` | bool | Sólo aplican a `PASSWORD` |
| `intentos_maximos` | smallint | 5 |
| `ventana_intentos_min` | smallint | 15 |
| `bloqueo_minutos` | smallint | 15 (30 para administración) |
| `duracion_sesion_min` | int | **240** |
| `inactividad_min` | smallint | **20** (30 para estudiantes). FUN-009 |
| `vigencia_credencial_dias` | int null | Null = no caduca |
| `permite_acceso_temporal` | bool | Sólo `student` por defecto |
| `creado_en`, `actualizado_en` | bigint | |

Invariantes: única por `(organizacion, perfil)` sin nivel; única por `(organizacion, perfil, nivel_clave)` con nivel; `PIN` ⇒ 4..8; `AVATAR` sólo para `student`; `5 ≤ inactividad_min ≤ duracion_sesion_min`.

Resolución para una persona: **política de su grupo** → **política de su nivel educativo** → **política de su perfil**.

### 3.3 · `m01_rol` · Rol

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `organizacion_id` | FK null | Null = **plantilla de sistema** (los cinco roles). No nulo = rol propio del colegio |
| `codigo` | char(32) | `STUDENT`, `TEACHER`, `ADMIN`, `REPORTS`, `TECHNICIAN`, o el que defina el colegio |
| `nombre` | char(80) | |
| `menu_principal` | char(16) | `student` / `teacher` / `admin` / `reports` / `technician`. Decide qué menú abre el cliente |
| `nivel` | smallint | 1 alumno · 2 personal · 3 administración. Nadie administra a alguien de nivel superior |
| `es_sistema` | bool | Las plantillas no se editan ni se borran |
| `creado_en` | bigint | |

### 3.4 · `m01_permiso` · Permiso

Catálogo cerrado y sembrado (28 permisos). Los de este módulo llevan el prefijo `identity.` del Maestro.

| Columna | Tipo | Nota |
|---|---|---|
| `codigo` | char(64) PK | `identity.password.reset`, `student.progress.read`… |
| `modulo` | char(24) | `acceso`, `expediente`, `contenido`, `aula`, `reportes`, `auditoria` |
| `descripcion` | char(200) | |
| `alcance_maximo` | char(20) | Techo: `identity.password.change_own` nunca pasa de `SELF`; `identity.exam_access.grant` nunca pasa de `ASSIGNED_GROUPS` |

Los **sensibles** (exigen asiento de auditoría siempre) se marcan en `plantillas.PERMISOS` y los expone `GET /permisos/`.

### 3.5 · `m01_rol_permiso` · RolPermiso

| Columna | Tipo | Nota |
|---|---|---|
| `rol_id` | FK | |
| `permiso_codigo` | FK | |
| `alcance` | char(20) | `SELF` / `ASSIGNED_GROUPS` / `LEVEL` / `ORGANIZATION` |

Invariante: `UNIQUE(rol_id, permiso_codigo)`; `alcance ≤ permiso.alcance_maximo`.

### 3.6 · `m01_usuario` · Usuario

La **cuenta**. Sin datos personales.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | Identidad interna estable (BR-020). Es el `persona_id` del expediente |
| `organizacion_id` | FK | |
| `rol_id` | FK | **Rol principal**: el que decide el menú si no se elige otro al entrar |
| `estado` | char(16) | `ACTIVO` / `BLOQUEADO` (manual) / `SUSPENDIDO` / `RETIRADO`. El bloqueo por intentos se calcula |
| `alias` | char(64) | Lo que muestra la tableta compartida («Juan P.») |
| `idioma` | char(8) | ISO 639-1 |
| `provisional` | bool | Admisión nominal: la creó el profesor «por su nombre» y aún no se vinculó |
| `vinculado_a` | FK null (usuario) | Al vincular, apunta a la persona definitiva y la provisional pasa a `RETIRADO` |
| `creado_en`, `actualizado_en`, `creado_por`, `ultimo_acceso_en` | | |

### 3.7 · `m01_persona` · Persona (1:1)

| Columna | Tipo | Protección |
|---|---|---|
| `usuario_id` | PK, FK | |
| `nombres_cifrado`, `apellidos_cifrado` | text | AES-256-GCM |
| `fecha_nacimiento_cifrado` | text null | AES-256-GCM |
| `telefono_cifrado` / `telefono_hmac` | text / char(64) | AES-256-GCM + índice HMAC |
| `pais` | char(2) | ISO 3166-1 alpha-2 |
| `actualizado_en` | bigint | |

### 3.8 · `m01_identificador_usuario` · IdentificadorUsuario

Identificadores **externos** (DEC-048): lo que vincula a la misma persona entre nodos.

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `usuario_id` | FK | |
| `tipo` | char(24) | `DNI` (documento nacional) / `CODIGO_ESTUDIANTIL` (matrícula) / `CLAVE_INSTALACION` (la emite el nodo, DEC-049) / `EMAIL` |
| `valor_cifrado` | text | AES-256-GCM |
| `valor_hmac` | char(64) | HMAC-SHA-256 del valor **normalizado** |
| `emisor` | char(64) | Institución o instalación que lo emitió; por defecto el código de la organización |
| `principal` | bool | **Uno por persona**: el que se muestra y el que vincula |
| `es_login` | bool | Si sirve para iniciar sesión |
| `verificado_en`, `creado_en` | bigint | |
| `retirado_en` | bigint null | CV-05: se retira, no se borra |

Invariantes (todos sobre los vigentes): `UNIQUE(tipo, valor_hmac)`; uno por `(usuario, tipo)`; un `principal` por usuario.

### 3.9 · `m01_credencial` · Credencial

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `usuario_id` | FK | |
| `tipo` | char(16) | `PIN` / `PASSWORD` / `AVATAR` |
| `hash` | char(255) | Cadena **Argon2id** con parámetros y sal |
| `activa` | bool | Sólo una activa por usuario |
| `debe_cambiar` | bool | Provisional: la puso otra persona |
| `creado_en`, `expira_en`, `sustituida_en`, `creado_por` | | |

### 3.10 · `m01_usuario_rol` · UsuarioRol (m01_persona_rol del Maestro)

Asignación de rol con alcance concreto y vigencia. Una persona puede tener varias; en cada sesión trabaja con una (BR-021).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `usuario_id` | FK | |
| `rol_id` | FK | |
| `alcance_tipo` | char(20) | `ORGANIZATION` / `LEVEL` / `ASSIGNED_GROUPS`. **Acota** el alcance del rol |
| `alcance_id` | char(36) null | `nivel_clave` o `grupo_id`; nulo con `ORGANIZATION` |
| `desde`, `hasta` | bigint / null | Vigencia (CAP-006: suplente hasta una fecha) |
| `asignado_por` | FK null | |
| `revocado_en` | bigint null | |

Invariantes: una vigente por `(usuario, rol, alcance_tipo, alcance_id)`; `hasta > desde`; alcance distinto de organización exige `alcance_id`.

### 3.11 · `m01_usuario_permiso` · Escalada (m01_escalada del Maestro)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `usuario_id` | FK | |
| `permiso_codigo` | FK | |
| `alcance` | char(20) | |
| `otorgado_por` | FK | Debe ser una identidad **distinta** del receptor |
| `motivo` | char(200) | Obligatorio por regla |
| `vigente_desde`, `vigente_hasta` | bigint | **Caducidad obligatoria** (BR-101), tope 24 h |
| `revocado_en` | bigint null | |

### 3.12 · `m01_grupo` · Grupo

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | |
| `organizacion_id` | FK | |
| `codigo`, `nombre`, `periodo` | | |
| `nivel_clave` | char(24) null | Nivel educativo del Maestro: decide la interfaz y las políticas por nivel |
| `politica_credencial_id` | FK null | Excepción de reglamento para el grupo |
| `activo`, `creado_en` | | |

### 3.13 · `m01_miembro_grupo` · MiembroGrupo

`grupo_id`, `usuario_id`, `papel` (`ESTUDIANTE` / `DOCENTE`), `desde`, `hasta`. Es lo que convierte `ASSIGNED_GROUPS` en una consulta: *existe un grupo donde el actor es DOCENTE vigente y el objetivo es miembro vigente*.

### 3.14 · `m01_dispositivo` · Dispositivo → `m09_dispositivo` (MOD-009, 2026-09-28)

> Esta tabla se mudó a `device_manager` (`m09_dispositivo`, con `identificador_hw`, `ultimo_latido_en`, `plataforma`, `version_app` y `bloqueado`) por las migraciones `device_manager/0001` y `acceso/0005`; las tres FK de este módulo (`m01_sesion`, `m01_autorizacion_temporal`, `m01_intento_acceso`) apuntan a ella. Lo que sigue describe la tabla tal como nació aquí. Ver [03-device-manager](../03-device-manager/00-modelo-y-api.md).

`organizacion_id`, `identificador` (lo genera la app y lo guarda en el almacén seguro), `nombre` («tableta-07»), `tipo`, `activo`, `registrado_en`, `ultimo_visto_en`. Contexto, nunca identidad.

### 3.15 · `m01_sesion` · Sesion

| Columna | Tipo | Nota |
|---|---|---|
| `id` | char(36) PK | `jti` del JWT |
| `usuario_id` | FK | |
| `rol_id` | FK null | **Rol efectivo** de la sesión (BR-021) |
| `dispositivo_id` | FK null | Contexto |
| `clase` | char(16) | `NORMAL` / `TEMPORAL` |
| `emitida_en`, `expira_en`, `ultimo_uso_en` | bigint | La inactividad se mide desde `ultimo_uso_en` |
| `revocada_en` | bigint null | |
| `motivo_revocacion` | char(64) null | `persona` · `otro_dispositivo` · `dispositivo_compartido` · `inactividad` · `restauracion` · `profesor` · `administrador` · `credencial_cambiada` · `credencial_restablecida` · `rol_cambiado` · `estado_cuenta` · `dispositivo_baja` |
| `evaluacion_ref` | char(200) null | Sesión temporal limitada a una evaluación |

Reglas: **una sola vigente por persona** y **cero o una por dispositivo** (INV-011), impuestas al abrir; la fila cerrada conserva su motivo.

### 3.16 · `m01_intento_acceso` · IntentoAcceso

`usuario_id?`, `identificador_hmac`, `dispositivo_id?`, `resultado` (`EXITO` · `FALLO` · `BLOQUEADO` · `DESBLOQUEO` · `TEMPORAL_EXITO` · `TEMPORAL_FALLO`), `motivo`, `autorizacion_id?`, `momento`. De aquí se **calcula** el bloqueo (FUN-007).

### 3.17 · `m01_autorizacion_temporal` · AutorizacionTemporal

El pase de emergencia del examen: `tipo` (`DISPOSITIVO` · `CODIGO`), `secreto_hash` (SHA-256 del token de 256 bits, o Argon2id del código de 6 dígitos), `dispositivo_id?`, `evaluacion_ref?`, `expira_en` (5 min), `usada_en`, `revocada_en`, `sesion_id`, `motivo`.

### 3.18 · `m01_evento_salida` · EventoSalida (Transactional Outbox)

`agregado_tipo`, `agregado_id`, `tipo_evento` (`identidad.*.v1`), `carga` (sin PII ni secretos), `creado_en`, `publicado_en`, `intentos`. Se escribe en la **misma transacción** que el hecho (Parte VII del documento de Arquitectura).

Lo anterior definió cada tabla. Lo que sigue analiza ese mismo modelo desde nueve ángulos de diseño relacional, para dejar explícito el razonamiento detrás de cada decisión.

### 3.19 · Lectura de dominio: qué problema resuelve cada grupo de tablas

Las dieciocho tablas no son dieciocho ideas sueltas: son la respuesta a nueve preguntas que el aula sin internet tiene que poder contestar localmente.

| Grupo | Tablas | Pregunta del dominio que resuelve |
|---|---|---|
| Instalación | `m01_organizacion` | ¿En qué colegio estoy y con qué idioma, país y huso horario opera? |
| Reglamento de acceso | `m01_politica_credencial` | ¿Con qué se entra aquí (PIN, contraseña, avatar) y qué tan estricto es, por perfil y por nivel educativo? |
| Autorización (RBAC) | `m01_permiso`, `m01_rol`, `m01_rol_permiso` | ¿Qué puede hacer cada tipo de usuario, y hasta qué alcance? |
| Identidad de la persona | `m01_usuario`, `m01_persona`, `m01_identificador_usuario` | ¿Quién es esta cuenta, quién es la persona detrás (sin exponerla) y con qué documentos se la reconoce? |
| Secreto | `m01_credencial` | ¿Con qué prueba esta persona que es quien dice ser? |
| Concesión de rol y de permiso | `m01_usuario_rol`, `m01_usuario_permiso` | ¿Qué rol tiene esta persona, en qué alcance y desde cuándo; y qué permiso extra se le concedió, por qué y hasta cuándo? |
| Padrón | `m01_grupo`, `m01_miembro_grupo` | ¿Quién enseña y quién estudia en qué grupo, con qué reglamento propio? |
| Sesión y dispositivo | `m01_dispositivo`, `m01_sesion` | ¿Qué tableta es cuál, y quién tiene abierta ahora mismo una sesión en ella? |
| Emergencia | `m01_autorizacion_temporal` | ¿Cómo entra a un examen quien olvidó su clave, sin correo ni SMS? |
| Evidencia | `m01_intento_acceso`, `m01_evento_salida` | ¿Qué pasó exactamente en cada intento de entrar, y qué le contamos al resto del sistema? |

El hilo común: **nada de esto puede depender de un servidor remoto** (R-07). Cada tabla existe porque una de estas preguntas tiene que resolverse con una consulta al SQLite del propio nodo, nunca con una llamada de red.

### 3.20 · Cardinalidad de las relaciones, y por qué

| Relación | Cardinalidad | Por qué es así |
|---|---|---|
| `organizacion` → `politica_credencial` | 1:N | Un colegio define varias políticas: una por perfil y, opcionalmente, excepciones por nivel educativo (BR-023/024) |
| `organizacion` → `rol` | 0/1:N | Nula cuando el rol es plantilla de sistema (los cinco de fábrica); no nula cuando el colegio define uno propio. Una FK opcional modela «global vs. propio del colegio» sin dos tablas |
| `organizacion` → `usuario`, `grupo`, `dispositivo` | 1:N | Toda cuenta, grupo y tableta pertenece a exactamente una instalación; no hay multi-tenencia cruzada |
| `rol` → `usuario` | 1:N | El **rol principal** (el que decide el menú si no se elige otro al entrar); una persona tiene un solo rol principal a la vez |
| `rol` ↔ `permiso` | **N:M** vía `rol_permiso` | Un rol agrupa muchos permisos y un permiso lo usan muchos roles; cada combinación además fija su propio alcance, así que no basta un par de FK |
| `usuario` ↔ `persona` | **1:0..1**, PK compartida | Ver §3.22: es una partición vertical de la misma entidad, no dos entidades independientes |
| `usuario` → `identificador_usuario` | 1:N | Una persona puede entrar por DNI, por matrícula o por clave de instalación a la vez (DEC-048); todas viven vigentes en paralelo |
| `usuario` → `credencial` | 1:N (con una **vigente**) | CV-05 impide sobrescribir el secreto anterior: cambiar la contraseña inserta una fila nueva y marca `sustituida_en` en la anterior; «una activa» es una regla de índice (§3.25), no la cardinalidad |
| `usuario` ↔ `rol` (asignaciones) | **N:M cualificada** vía `usuario_rol` | BR-021: una persona acumula varios roles vigentes, cada uno con su propio alcance y vigencia; en cada sesión sólo usa uno |
| `usuario` ↔ `permiso` (escaladas) | **N:M cualificada** vía `usuario_permiso` | BR-101: un permiso adicional puntual, con motivo y caducidad obligatoria, que no pertenece al rol |
| `grupo` ↔ `usuario` | **N:M cualificada** vía `miembro_grupo` | Un grupo tiene varios estudiantes y un docente puede repetirse en varios grupos; el papel (`ESTUDIANTE`/`DOCENTE`) cualifica cada par |
| `usuario` → `sesion` | 1:N (con **una vigente**, INV-011) | Igual que credencial: el historial de sesiones no se borra; la unicidad de «la vigente» es un índice parcial |
| `dispositivo` → `sesion`, `intento_acceso`, `autorizacion_temporal` | 0/1:N | Una tableta compartida ve pasar muchas sesiones; el campo es opcional porque también se entra sin declarar dispositivo |
| `usuario` → `autorizacion_temporal` | 1:N, **en dos papeles** | `usuario` (quien la recibe) y `otorgada_por` (quien la concede) son dos FK distintas a la misma tabla, que nunca pueden ser la misma fila (regla de negocio) |
| `autorizacion_temporal` → `sesion` | **1:0..1**, FK única (no PK compartida) | Ver §3.22: la autorización nace antes que la sesión y puede no llegar a usarse nunca; por eso no comparte clave |
| `usuario` → `usuario` (`creado_por`, `vinculado_a`) | 1:N, recursiva, **dos veces** | Dos hechos distintos sobre la misma tabla: quién dio de alta a quién (auditoría) y qué cuenta definitiva absorbió a cuál provisional (JRN-007). Cada una es una FK independiente con su propio `related_name` |

Ninguna relación **1:1 pura y obligatoria** existe en el módulo: hasta `usuario`↔`persona`, la más cercana, se modela como 1 a 0..1 porque la partición es intencional (§3.22), no una regla de negocio que exija exactamente una fila en ambos lados desde el primer instante.

### 3.21 · Tablas asociativas: cuáles son y si la relación tiene atributos propios

| Tabla asociativa | Resuelve | Atributos propios (por qué no basta un par de FK) |
|---|---|---|
| `m01_rol_permiso` | `rol` ↔ `permiso` | `alcance`: el mismo permiso puede concederse a un rol con techo `ASSIGNED_GROUPS` y a otro con `ORGANIZATION`. Sin este atributo, el alcance tendría que vivir en `permiso` (uno solo para todos los roles) o en `rol` (uno solo para todos los permisos); ninguna de las dos es correcta |
| `m01_usuario_rol` | `usuario` ↔ `rol` | `alcance_tipo`, `alcance_id`, `desde`, `hasta`, `asignado_por`, `revocado_en`. La pareja (usuario, rol) por sí sola ni siquiera es única: la misma persona puede tener el rol TEACHER dos veces, con dos alcances distintos (dos grupos) y dos vigencias distintas. La unicidad real es condicional — `UNIQUE(usuario, rol, alcance_tipo, alcance_id) WHERE revocado_en IS NULL` — por eso la tabla necesita su propia PK sustituta en vez de una PK compuesta |
| `m01_usuario_permiso` | `usuario` ↔ `permiso` (escalada) | `alcance`, `otorgado_por`, `motivo`, `vigente_desde`, `vigente_hasta`, `revocado_en`. Mismo razonamiento que la anterior, con un atributo que no existe en `usuario_rol`: `motivo`, obligatorio porque BR-101 exige poder explicar por qué alguien recibió un permiso que su rol no le da |
| `m01_miembro_grupo` | `grupo` ↔ `usuario` | `papel` (`ESTUDIANTE`/`DOCENTE`), `desde`, `hasta`. Aquí la unicidad **no** está filtrada por vigencia (`UNIQUE(grupo, usuario, papel)` a secas): la membresía se trata como un único hecho con intervalo abierto/cerrado que se reabre al reingresar, no como una bitácora de altas y bajas. Es una simplificación deliberada frente a `usuario_rol`/`usuario_permiso`: pertenecer a un grupo no necesita el mismo rastro de auditoría que un permiso o un rol con alcance de seguridad |

Las cuatro son «tablas puente» en sentido estricto: existen exclusivamente porque la relación en sí misma **tiene información** que no pertenece a ninguna de las dos entidades que conecta. Ninguna es un simple cruce de identificadores.

### 3.22 · PK, FK, identidad e integridad referencial

**Tres estrategias de clave, cada una donde corresponde:**

| Estrategia | Dónde se usa | Por qué |
|---|---|---|
| **UUID (texto, char36)** | `organizacion`, `politica_credencial`, `rol`, `usuario`, `identificador_usuario`, `credencial`, `usuario_permiso`, `usuario_rol`, `grupo`, `miembro_grupo`, `dispositivo`, `autorizacion_temporal` | Son entidades que **se referencian desde fuera** de su propia tabla (API, JWT, otros módulos vía `usuario.id` como `persona_id`). El UUID se genera en el dominio sin depender de que la base asigne el siguiente número — indispensable en un nodo que puede operar semanas sin sincronizarse con nadie (CV-02) |
| **Clave natural** | `permiso.codigo` (`identity.password.reset`…); `sesion.id` (es el `jti` del JWT, no un UUID adicional) | `permiso` es un catálogo cerrado y sembrado por código, no datos de usuario: usar el propio código de negocio como PK evita una columna sustituta que nadie necesitaría y hace autoexplicativa cada fila de `rol_permiso`/`usuario_permiso` (`permiso_codigo`) sin JOIN. `sesion.id` reutiliza un identificador que **ya existe** en el estándar (el `jti` del token): crear un UUID aparte y mantener una tabla de traducción sería una indirección sin beneficio |
| **Autoincremental (`BigAutoField` implícito)** | `rol_permiso`, `intento_acceso`, `evento_salida` (ninguna declara `id` explícito) | Son las únicas tablas del módulo que nunca se referencian por `id` desde otra tabla u otro módulo, y son de alta escritura y **append-only**. Un entero creciente ordena físicamente la inserción — el mismo orden en que se necesitan leer (`intento_acceso` para el cálculo de bloqueo por ventana de tiempo, `evento_salida` para el relevo del outbox) — mientras que un UUID v4 fragmentaría el índice sin aportar nada, porque nadie pide «la fila con `id = X`» de estas tres tablas |

**Integridad referencial por política de borrado, no uniforme:**

| Política | Ejemplos | Significado de negocio |
|---|---|---|
| `CASCADE` | `organizacion → *`, `usuario → persona/identificador/credencial/usuario_rol/usuario_permiso/sesion/autorizacion_temporal`, `grupo → miembro_grupo`, `rol → rol_permiso` | Composición real: la fila hija **no tiene sentido** sin su dueño. Es la relación «parte de» |
| `PROTECT` | `usuario.rol`, `rol_permiso.permiso`, `usuario_permiso.permiso`, `usuario_rol.rol`, `usuario_permiso.otorgado_por` | La fila referenciada **sostiene una decisión vigente**; borrarla en cascada ocultaría un permiso o un rol que sigue concedido. Obliga a resolver el conflicto explícitamente en vez de perder el rastro en silencio |
| `SET_NULL` | `usuario.creado_por`, `usuario.vinculado_a`, `grupo.politica_credencial`, `sesion.dispositivo`, `sesion.rol`, `autorizacion_temporal.dispositivo/sesion`, `intento_acceso.dispositivo/autorizacion`, `credencial.creado_por` | Contexto o procedencia, no identidad: la fila principal **sobrevive** aunque se pierda el dato de quién u qué la originó |

Esta separación en tres políticas es en sí misma integridad referencial declarativa: el motor rechaza o resuelve cada borrado según el **papel** de la relación, sin lógica de aplicación adicional para decidirlo.

**Identidad:** ninguna tabla usa una clave natural insegura (documento, correo) como PK — precisamente porque esos valores son PII y viven cifrados (`identificador_usuario.valor_cifrado`); la identidad **direccionable** siempre es el UUID interno (`usuario.id`, BR-020), y el documento sólo sirve para *encontrar* esa fila a través del índice ciego HMAC (§3.25), nunca para *ser* la clave.

### 3.23 · Por qué el modelo está en 3FN

**1FN.** Toda columna es atómica: no hay listas ni pares repetidos dentro de una fila. `usuario_permiso`/`usuario_rol` resuelven la multiplicidad (varios roles, varios permisos por persona) con **filas adicionales**, no con una columna `roles = "TEACHER,ADMIN"`.

**2FN.** Todas las tablas tienen clave primaria de una sola columna (UUID, código o autoincremental); no existe clave compuesta en el módulo, así que no puede haber dependencia **parcial** de una PK compuesta: no hay nada de qué depender «a medias». Donde el negocio exige una combinación única (`rol_permiso`, `usuario_rol`, `miembro_grupo`…), esa combinación se declara como `UniqueConstraint` **además** de la PK sustituta, no en lugar de ella — precisamente para no verse forzado a una PK compuesta que reintroduciría el problema.

**3FN.** Ningún atributo no clave depende de otro atributo no clave; depende sólo de la clave completa:

- `usuario` no guarda el nombre de su organización ni el de su rol — sólo los FK. Mostrar «IE San José» exige un JOIN; guardarlo en `usuario` sería una dependencia transitiva clásica (`usuario.id → organizacion_id → organizacion.nombre`) y un valor que se desincroniza el día que el colegio se renombra.
- `persona` está separada de `usuario` **no por normalización** (las dos tienen el mismo determinante, `usuario_id`; fusionarlas no violaría 3FN) sino por una frontera de confidencialidad: aislar en una tabla propia lo que va cifrado permite rotar sus claves, respaldar o purgar PII sin tocar la cuenta, y limitar qué consulta puede tocarla. Normalización y aislamiento de PII son dos fuerzas distintas que aquí señalan en la misma dirección.
- `identificador_usuario.valor_hmac` **parece** depender de `valor_cifrado` (ambos codifican el mismo documento), pero ninguno se calcula a partir del otro dentro de la base de datos: los dos son funciones independientes del valor real, que no se almacena en ninguna columna. No hay dependencia intra-fila que viole 3FN porque el determinante común (el documento en claro) es externo al esquema.
- `sesion.rol_id` no se deriva de `usuario.rol_id`: es el **rol efectivo** elegido al entrar (BR-021), un hecho propio de la sesión que con frecuencia coincide con el rol principal pero es conceptualmente independiente — guardarlo es correcto, no redundante.
- No existe una columna `usuario.credencial_activa_id` ni `usuario.ultima_sesion_id`: ambos «actuales» se resuelven por índice parcial (§3.25) sobre la tabla de detalle, evitando el antipatrón de un puntero de caché en el padre que habría que mantener sincronizado en cada escritura del hijo.

### 3.24 · Tablas transitivas y forma del modelo

**Tablas transitivas** (de tránsito obligado): son las mismas cuatro tablas asociativas de §3.21 — `rol_permiso`, `usuario_rol`, `usuario_permiso`, `miembro_grupo`. `rol` y `permiso`, por ejemplo, **sólo** se alcanzan uno al otro transitando por `rol_permiso`; no hay ni puede haber una FK directa entre ellos, porque la relación misma tiene atributos (§3.21).

Aparte de ésas, el grafo de FK tiene caminos de **varios saltos** que no son tránsito obligado sino simple navegación — y ninguno copia un atributo a lo largo del camino, así que ninguno compromete la 3FN (§3.23): `usuario → grupo (miembro_grupo) → organizacion` coexiste con `usuario → organizacion` directo (son dos hechos distintos: la instalación de la cuenta y la pertenencia a un grupo de esa instalación); `miembro_grupo → grupo → politica_credencial → organizacion` es la cadena que resuelve qué reglamento aplica, y cada salto es una FK, no un valor copiado.

**¿Estrella o copo de nieve?** Ninguno de los dos, con propiedad: este es un esquema **transaccional (OLTP) en 3FN**, no un modelo dimensional para analítica. Un esquema en estrella exige dimensiones **desnormalizadas** conectadas directamente a un hecho central; aquí ocurre lo contrario — cada dimensión (`organizacion`, `rol`, `permiso`, `grupo`, `dispositivo`) está, a propósito, normalizada y puede depender a su vez de otra (`grupo` depende de `organizacion` y de `politica_credencial`), que es precisamente la forma que en un almacén de datos se llamaría **copo de nieve**. Si algún día un módulo de reportes necesita un modelo dimensional sobre éste, el trabajo sería el inverso al habitual: **aplanar** estas cadenas normalizadas en dimensiones anchas (`dim_usuario` con el nombre de la organización y del rol ya incluidos) y convertir `m01_intento_acceso` y `m01_evento_salida` —las dos tablas de grano fino, con marca de tiempo, que hoy más se parecen a hechos— en tablas de hechos propiamente dichas, con clave de tiempo. Hoy esa vista no existe porque el módulo no la necesita: existe para escribir y decidir, no para agregar.

### 3.25 · Qué consulta justifica cada índice

| Índice | Consulta que resuelve |
|---|---|
| `uq_m01_identificador_valor` (única, `tipo+valor_hmac` con `retirado_en IS NULL`) | **La consulta más caliente del módulo**: dado el documento que teclea alguien al entrar, calcular su HMAC y encontrar la cuenta en O(1) (`AutenticarUsuario`) |
| `Index(valor_hmac)` en `identificador_usuario` | Búsquedas administrativas por identificador sin conocer el tipo exacto («¿este documento ya está registrado, con cualquier tipo?») |
| `Index(telefono_hmac)` en `persona` | Ubicar a una persona por teléfono para recuperación o para detectar duplicados, sin poder leer el teléfono en claro |
| `uq_m01_credencial_activa` (única, `usuario` con `activa=True`) | «Tráeme la credencial vigente de este usuario» al validar el secreto, sin escanear el historial completo |
| `Index(usuario, revocado_en)` en `usuario_rol` | «¿Qué roles vigentes tiene esta persona ahora?» — se ejecuta en cada inicio de sesión y en cada resolución de menú (`ResolverPrincipal`) |
| `Index(usuario, papel)` en `miembro_grupo` | «¿En qué grupos es DOCENTE esta persona?» — la evalúa `PoliticaAutorizacion` en **cada** decisión de alcance `ASSIGNED_GROUPS`/`LEVEL` (§5.2): la consulta de más volumen del módulo tras el login |
| `Index(organizacion, estado)` en `usuario` | Listar usuarios activos de una instalación (paneles de administración, `ListarUsuarios`) |
| `Index(rol)` en `usuario` | «¿Cuántas cuentas usan este rol como principal?» antes de editarlo o retirarlo |
| `Index(vinculado_a)` en `usuario` | Reconstruir qué cuentas provisionales terminaron fusionadas en una cuenta definitiva (JRN-007) |
| `Index(usuario, revocada_en, expira_en)` en `sesion` | «¿Tiene ya una sesión vigente esta persona?» al abrir sesión (INV-011) y el barrido que expira sesiones inactivas |
| `Index(usuario, expira_en)` en `autorizacion_temporal` | Autorizaciones temporales vigentes de una persona, para no emitir dos pases de emergencia superpuestos |
| `Index(usuario, -momento)` en `intento_acceso` | FUN-007: contar los intentos fallidos recientes de una persona, en orden descendente, para decidir el bloqueo por ventana de tiempo |
| `Index(autorizacion)` en `intento_acceso` | Todos los intentos que usaron un pase temporal concreto, para auditoría del acceso a examen |
| `Index(publicado_en, creado_en)` en `evento_salida` | La consulta del relevo del outbox: «eventos aún no publicados, en el orden en que ocurrieron» |

Cada índice explícito del modelo corresponde a una consulta que se ejecuta en el camino crítico de una regla de negocio ya citada (BR/FUN); ninguno es especulativo.

### 3.26 · Linaje de datos: de dónde viene cada dato y cuál es la fuente de verdad

| Dato | Fuente de verdad | Cómo llega |
|---|---|---|
| Identidad, credenciales, roles, sesiones | **Este módulo**, y sólo él | No hay directorio externo (sin LDAP, sin IdP): `acceso` es el sistema de registro. El dato nace aquí, tecleado por un administrador o un docente (`CrearUsuario`, `ImportarUsuarios`, FUN-003) |
| Documento, nombres, teléfono (en claro) | La persona, en el momento de la matrícula | Entra una sola vez a la aplicación; el adaptador de seguridad lo cifra/hashea antes de tocar la base de datos (`infraestructura/seguridad.py`). **El linaje se corta a propósito en la frontera de la aplicación**: no existe columna, respaldo ni caché intermedia con el valor plano |
| «¿Sigue viva esta sesión?» | **`m01_sesion`**, no el JWT | El token es autocontenido y se verifica sin red, pero sólo **afirma** quién lo emitió; la verdad de si ya fue revocado vive exclusivamente en la fila (`revocada_en`). El JWT es una copia portátil de un hecho cuyo original está en la base de datos |
| `usuario.id` usado como `persona_id` en `expediente` y `classroom_engine` | **`acceso`** es el módulo de origen | La referencia es lógica (texto), no una FK física entre apps (Q-52), pero el linaje es real: ese identificador nace aquí y ningún otro módulo lo genera ni lo reescribe |
| Eventos `identidad.*.v1` | El hecho de negocio que los originó, en la misma transacción | `m01_evento_salida` no es una fuente de verdad adicional: es la copia de propagación de un hecho ya escrito en `m01_*`, para que otros módulos (hoy ninguno; mañana MOD-015) lo consuman sin leer directamente estas tablas |
| Asientos de auditoría (acciones sensibles, `identidad.*`) | **`m19_auditoria`**, alojada en el app `expediente` (MOD-019 aún no tiene módulo propio) | El adaptador `AuditoriaExpediente` (`infraestructura/repositorios.py`) escribe ahí en la misma transacción que el hecho. Es el **único** punto donde `acceso` toca una tabla de otro app, y lo hace sólo desde infraestructura: el dominio nunca la importa. Consecuencia práctica: un esquema con sólo las `m01_*` no contiene su propia auditoría — vive en `m19_*` |

En síntesis: `acceso` nunca es espejo de otro sistema — es cabecera de linaje para la identidad de toda la instalación, incluida la que reutilizan `expediente` y `classroom_engine`.

### 3.27 · Conclusión: cómo el modelo resuelve el dominio de acceso

El módulo tiene que contestar, sin red y en milisegundos, tres preguntas que se repiten miles de veces al día en un aula: *¿quién es*, *qué puede hacer* y *ya pasó esto antes*. El diseño relacional resuelve cada una con el mecanismo mínimo suficiente: la identidad se parte en cuenta + persona cifrada + identificadores externos para poder mostrar, buscar y proteger a la vez (§3.20, §3.22); la autorización se resuelve con cuatro tablas (`rol`, `permiso`, `rol_permiso`, `usuario_rol`) en vez de una tabla de permisos por contexto que crecería sin límite (§2.2) — el alcance vive como **atributo de la relación**, no como fila nueva por combinación posible; y lo que ya ocurrió (intentos, eventos) se guarda append-only con índices pensados para las dos preguntas que de verdad se hacen sobre esa evidencia: «¿debo bloquear?» y «¿qué falta por publicar?». La 3FN no es un ejercicio académico aquí: es lo que permite que renombrar un colegio, rotar una contraseña o revocar un rol sea escribir **una fila**, nunca corregir el mismo dato en varios lugares — una propiedad indispensable en un nodo que nadie va a estar reparando a mano.

---

## 4 · Protección de la información

| Dato | Protección | Motivo |
|---|---|---|
| Contraseña · PIN · avatar · código temporal | **Argon2id** `m=64 MiB, t=3, p=1` | Nunca se recuperan; la baja entropía del PIN y el avatar la compensan el coste y el bloqueo |
| Token de dispositivo (256 bits) | SHA-256 | Alta entropía |
| Documento · matrícula · correo | **AES-256-GCM + HMAC-SHA-256** | Mostrar y buscar |
| Nombres · apellidos · nacimiento · teléfono | **AES-256-GCM** | Recuperar |
| JWT | **HS256** con clave local de 256 bits | Un solo emisor y verificador |

Claves `AVACOM_LMS_CLAVE_DATOS`, `AVACOM_LMS_CLAVE_INDICE`, `AVACOM_LMS_CLAVE_TOKENS` (32 bytes base64). Si faltan, se derivan con HKDF de `SECRET_KEY` y `/health/` lo avisa.

Payload del JWT: `iss`, `sub` (usuario), `jti` (sesión), `org`, `rol` (efectivo), `menu`, `nivel`, `dev`, `clase`, `eval`, `iat`, `exp`. Los **permisos no viajan en el token**: se evalúan contra la base en cada petición.

---

## 5 · Plantillas plug-and-play

### 5.1 · Los cinco roles y sus permisos

| Permiso | STUDENT | TEACHER | ADMIN | REPORTS | TECHNICIAN |
|---|---|---|---|---|---|
| `student.progress.read` · `results.read` | SELF | ASSIGNED_GROUPS | ORGANIZATION | ORGANIZATION | — |
| `student.progress.write` · `student.exam.attempt` | SELF | — | — | — | — |
| `reports.student.view` | — | ASSIGNED_GROUPS | ORGANIZATION | ORGANIZATION | — |
| `content.read` | SELF | ORGANIZATION | ORGANIZATION | ORGANIZATION | — |
| `content.project` | — | ASSIGNED_GROUPS | ASSIGNED_GROUPS | — | — |
| `identity.user.read` | SELF | ASSIGNED_GROUPS | ORGANIZATION | ORGANIZATION | — |
| `identity.user.create` · `identity.user.update` · `identity.user.unlock` · `identity.password.reset` | — | ASSIGNED_GROUPS | ORGANIZATION | — | — |
| `identity.user.import` · `identity.role.assign` · `identity.escalation.grant` · `identity.role.manage` · `identity.policy.manage` · `identity.group.manage` · `audit.read` | — | — | ORGANIZATION | — | — |
| `identity.exam_access.grant` | — | ASSIGNED_GROUPS | ASSIGNED_GROUPS | — | — |
| `identity.session.read` | SELF | ASSIGNED_GROUPS | ORGANIZATION | SELF | ORGANIZATION |
| `identity.session.revoke` | — | ASSIGNED_GROUPS | ORGANIZATION | — | — |
| `identity.group.read` | SELF | ASSIGNED_GROUPS | ORGANIZATION | ORGANIZATION | — |
| `identity.group.member.manage` | — | ASSIGNED_GROUPS | ORGANIZATION | — | — |
| `identity.role.read` | — | ORGANIZATION | ORGANIZATION | ORGANIZATION | ORGANIZATION |
| `identity.device.manage` | — | — | ORGANIZATION | — | ORGANIZATION |
| `identity.password.change_own` · `identity.session.revoke_own` | SELF | SELF | SELF | SELF | SELF |

### 5.2 · Evaluación de una decisión (Policy Pattern)

```
decidir(actor, permiso, objetivo):
    rol_efectivo = el de la sesión (BR-021)
    concesiones = rol_permiso[rol_efectivo] ∪ escaladas vigentes
    alcance = min(concesiones[permiso], alcance de la asignación del rol)   # ausencia → DENEGADO
    grupos del actor = donde es DOCENTE ∪ los que abre la asignación (un grupo, o todos los de un nivel)
    ORGANIZATION → misma organización y actor.nivel ≥ objetivo.nivel
    LEVEL / ASSIGNED_GROUPS → objetivo es estudiante y comparte alguno de esos grupos
    SELF → objetivo == actor
    Fuera de alcance → 403 acceso denegado, nunca «no existe»
```

Reglas transversales previas: credencial provisional ⇒ sólo `identity.password.change_own`; sesión `TEMPORAL` ⇒ sólo rendir la evaluación.

---

## 6 · Arquitectura del módulo

```
DRF (interfaces/views.py, serializers.py, autenticacion.py, urls.py)
      ↓
Casos de uso (aplicacion/casos_uso.py)            ← Use Case Pattern (39 casos)
      ↓
Dominio (dominio/entidades.py, valores.py, politicas.py, errores.py, plantillas.py)
      ↓
Puertos (aplicacion/puertos.py)
      ↓
Adaptadores (infraestructura/repositorios.py, unidad_trabajo.py, seguridad.py, contenedor.py)
      ↓
Django ORM (models.py) → SQLite
```

Regla verificable: una prueba recorre `dominio/` y `aplicacion/` y falla si algún archivo importa `django`, `rest_framework`, `pydantic`, `sqlalchemy` o `fastapi`.

---

## 7 · Relación con el expediente y con los demás módulos del Maestro

- `m01_usuario.id` **es** el `persona_id` del expediente. `vinculado_a` permite reasignar lo que hizo una cuenta provisional.
- Grupos (MOD-002) viven hoy dentro de `acceso`; cuando exista ese módulo, se replicarán desde su dueño. Los dispositivos ya tienen dueño desde el 2026-09-28 (MOD-009, `device_manager`): este módulo los lee por su puerto `RepositorioDispositivos`, que llama a `device_manager/servicios.py` dentro de la transacción del login.
- La orden de limpiar el contenedor de la tableta (MOD-009) se deriva de `identidad.sesion.cerrada.v1` con motivo `otro_dispositivo` o `dispositivo_compartido`.
- La exigencia de sesión en el expediente sigue preparada y no activada (`AVACOM_LMS_EXIGIR_SESION=0`, Q-34).

---

## 8 · Preguntas abiertas

Ver la sección 10 de [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md): Q-34 a Q-43.
