# 04 · Módulo de acceso · Lineamientos frente al Documento Maestro

| Campo | Valor |
|---|---|
| Fuente normativa | `AVACOM_LMS_Documento_Maestro_Consolidado_v1.0` · capítulo **MOD-001 · Identity & Access** (DOM-001) y `AVACOM_LMS_Arquitectura_y_Datos_v1.0` · tablas `m01_*`, Parte VI (identidad, tiempo y orden) y Parte VIII (convenciones CV-01 a CV-09) |
| Estado | Aplicado en el commit `Feature: Alinea el módulo de acceso con MOD-001 Identity & Access del Documento Maestro` |
| Para qué sirve | Registrar, capacidad por capacidad y función por función, cómo el código de `backend/acceso/` cumple lo que el Maestro exige, qué se decidió distinto y por qué, y qué queda pendiente |
| Documentos hermanos | [01 · Modelado de datos](01-modelado-datos.md) · [02 · Endpoints](02-Endpoints.md) · [03 · Casos de uso](03-casos-de-uso-backend.md) |

---

## 0 · Cómo leer este documento

El Documento Maestro describe MOD-001 en términos de **capacidades** (CAP), **funciones** (FUN), **reglas** (BR, INV), **eventos**, **permisos**, **pantallas** (PAN), **mensajes** (MSG) y **escenarios de prueba** (TST). El documento de Arquitectura fija las **tablas** y nueve **convenciones**. Este documento cruza cada uno de esos elementos con lo que hay en el código. Cada fila lleva un veredicto:

| Veredicto | Significado |
|---|---|
| **Cumple** | El comportamiento del Maestro está implementado y probado |
| **Cumple con matiz** | Está implementado, pero con una decisión de diseño distinta que se explica |
| **Preparado** | El modelo o el código lo permiten; falta la pieza de otro módulo o del frontend |
| **Pendiente** | No está; se anota como pregunta abierta con propuesta |

---

## 1 · Capacidades (CAP)

| ID | Capacidad del Maestro | Veredicto | Cómo se cumple en el código |
|---|---|---|---|
| CAP-001 | Iniciar sesión en el aula con credencial local del nodo (Alumno, sin red) | **Cumple** | `AutenticarUsuario` sobre `POST /api/acceso/sesiones/`. Credencial local hasheada con Argon2id; verificación y JWT firmados en el nodo, sin ningún servicio externo |
| CAP-002 | Entrar a clase con código de sesión sin escribir contraseña | **Cumple con matiz** | El *código de unión* de la clase lo emite MOD-007 (Classroom Engine), fuera de este módulo. Lo que MOD-001 aporta es la **sesión temporal en dispositivo compartido**: `OtorgarAccesoTemporal` + `CanjearAccesoTemporal` permiten entrar sin escribir la clave, autorizando la tableta (opción A) o con un código de 6 dígitos (opción B), con caducidad, un solo uso y sesión limitada a la evaluación |
| CAP-003 | Dar de alta alumnos por carga masiva desde archivo (Administrador, sin red) | **Cumple** | `ImportarUsuarios` sobre `POST /api/acceso/usuarios/importar/` y el comando `manage.py acceso_importar archivo.csv`. Lote transaccional, deduplica por identificador («fusiona»), devuelve filas rechazadas con motivo (MSG-065) |
| CAP-004 | Restablecer el acceso de un alumno desde el aula sin soporte externo (Profesor, sin red) | **Cumple** | `RestablecerCredencial` con alcance `ASSIGNED_GROUPS` para el profesor; devuelve el secreto provisional una sola vez y obliga a cambiarlo |
| CAP-005 | Asignar roles y permisos por perfil (Administrador) | **Cumple** | `AsignarRol` (m01_usuario_rol con alcance y vigencia), `CrearRol` (roles personalizados a partir de una plantilla), `ConfigurarPolitica` (reglamento por perfil y por nivel) |
| CAP-006 | Delegar acceso temporal a un profesor suplente con vigencia definida (V1) | **Preparado** | `AsignarRol` acepta `vigente_hasta` y alcance `ASSIGNED_GROUPS` sobre un grupo: un suplente recibe el rol TEACHER acotado al grupo hasta una fecha. Queda pendiente que MOD-002 registre la asignación docente con papel `suplente` (véase §9) |

---

## 2 · Funciones (FUN)

| ID | Función del Maestro | Actor · superficie | Veredicto | Caso de uso · ruta | Evento publicado | Permiso exigido |
|---|---|---|---|---|---|---|
| FUN-001 | Crear una cuenta de usuario local | Administrador · Navegador | **Cumple** | `CrearUsuario` · `POST /usuarios/` | `identidad.usuario.creado.v1` | `identity.user.create` |
| FUN-002 | Asignar un rol a un usuario | Administrador · Navegador | **Cumple** | `AsignarRol` · `POST /usuarios/{id}/roles/` | `identidad.rol.asignado.v1` | `identity.role.assign` |
| FUN-003 | Importar usuarios desde archivo delimitado | Administrador · Navegador | **Cumple** | `ImportarUsuarios` · `POST /usuarios/importar/` · comando `acceso_importar` | `identidad.usuarios.importados.v1` | `identity.user.import` |
| FUN-004 | Autenticar a un profesor con contraseña en el nodo | Profesor · Cualquiera | **Cumple** | `AutenticarUsuario` · `POST /sesiones/` | `identidad.sesion.abierta.v1` | ninguno |
| FUN-005 | Autenticar a un alumno con código o PIN de clase | Alumno · Tableta | **Cumple** | `AutenticarUsuario` (PIN / avatar) y `CanjearAccesoTemporal` (código) | `identidad.sesion.abierta.v1` | ninguno |
| FUN-006 | Restablecer la contraseña de un usuario | Administrador · Navegador | **Cumple** | `RestablecerCredencial` · `POST /usuarios/{id}/credencial/restablecer/` | `identidad.credencial.restablecida.v1` | `identity.password.reset` |
| FUN-007 | Bloquear una cuenta tras intentos fallidos consecutivos | Sistema · Nodo | **Cumple con matiz** | Dentro de `AutenticarUsuario`: al superar el umbral responde 423 y publica el evento. El bloqueo se **calcula** sobre `m01_intento_acceso` en lugar de mantener un contador (§7) | `identidad.cuenta.bloqueada.v1` | ninguno |
| FUN-008 | Desbloquear una cuenta bloqueada | Administrador · Navegador | **Cumple** | `DesbloquearUsuario` · `POST /usuarios/{id}/desbloquear/` | `identidad.cuenta.desbloqueada.v1` | `identity.user.unlock` |
| FUN-009 | Cerrar por inactividad la sesión de un usuario | Sistema · Cualquiera (temporizador) | **Cumple con matiz** | Dentro de `ResolverPrincipal`: en la primera petición tras superar `inactividad_min` la sesión se cierra con motivo `inactividad` y se rechaza con `sesion_inactiva`. No hay temporizador en segundo plano: el reloj del nodo decide al primer contacto (§7) | `identidad.sesion.cerrada.v1` | ninguno |
| FUN-010 | Revocar todas las sesiones activas de un usuario | Administrador · Navegador | **Cumple** | `RevocarSesionesDeUsuario` · `DELETE /usuarios/{id}/sesiones/` | `identidad.sesiones.revocadas.v1` | `identity.session.revoke` |
| FUN-011 | Restaurar la sesión del profesor tras reinicio del nodo | Sistema · Nodo (arranque) | **Cumple** | La sesión vive en `m01_sesion`, no en memoria; el pase JWT es válido mientras la fila lo sea. Tras un reinicio, la primera petición la valida y continúa. Probado en `test_la_sesion_sobrevive_al_reinicio_del_nodo` | `identidad.sesion.restaurada.v1` (definido en el catálogo; se publica cuando MOD-015 avise del arranque) | ninguno |

---

## 3 · Estados que gobierna

| Estado del Maestro | En el código | Veredicto |
|---|---|---|
| Cuenta: activa · bloqueada por intentos · suspendida · dada de baja | `EstadoUsuario`: `ACTIVO` · `BLOQUEADO` (manual) · `SUSPENDIDO` · `RETIRADO`. El bloqueo por intentos se calcula y se expone como `bloqueado_hasta` | **Cumple con matiz** |
| Sesión: abierta · cerrada por la persona · cerrada por apertura en otro dispositivo · expirada por inactividad | `Sesion.revocada_en` + `MotivoCierre`: `persona` · `otro_dispositivo` · `inactividad`, más `dispositivo_compartido`, `restauracion`, `profesor`, `administrador`, `credencial_cambiada`, `credencial_restablecida`, `rol_cambiado`, `estado_cuenta`, `dispositivo_baja` | **Cumple** (superconjunto) |
| «La transición que más consecuencias tiene es el cierre por apertura en otro dispositivo» | `abrir_sesion()` cierra cualquier otra sesión de la persona con `otro_dispositivo` y devuelve `sesion_anterior` para PAN-103 / MSG-020. La orden de limpiar el contenedor la recibe MOD-009 consumiendo `identidad.sesion.cerrada.v1` | **Cumple** · **Preparado** el lado MOD-009 |

---

## 4 · Reglas e invariantes (BR, INV)

| Regla | Texto del Maestro | Veredicto | Dónde |
|---|---|---|---|
| BR-020 | Toda persona tiene una identidad interna estable, distinta de su nombre de acceso | **Cumple con matiz** | `m01_usuario.id` (UUID) nunca cambia; los identificadores de acceso son filas en `m01_identificador_usuario` con `emisor` y `principal` (DEC-048). El Maestro usa un identificador de **cinco segmentos**; aquí es UUID (§7, Q-38) |
| BR-021 | Varios roles activos, un solo rol efectivo por sesión, elegido al iniciar sesión | **Cumple** | `m01_usuario_rol` + `Sesion.rol_id`. `POST /sesiones/` acepta `rol`; la respuesta trae `roles_disponibles`; `/yo/` devuelve `rol_efectivo` |
| BR-023 | Longitud, caducidad y bloqueo configurables por institución, por separado para personal y alumnos | **Cumple** | `m01_politica_credencial`, una fila por perfil (`student`, `teacher`, `admin`, `reports`, `technician`) |
| BR-024 | Nivel inicial con método simplificado (código gráfico o PIN) si el administrador lo habilita para ese nivel | **Cumple** | `TipoSecreto.AVATAR`, `PoliticaCredencial.nivel_clave`, `PUT /politicas/student/?nivel=preescolar`. Orden de resolución: grupo → nivel → perfil |
| BR-025 | El dado de baja conserva identidad e historial, pierde acceso y no se reactiva bajo identidad nueva | **Cumple** | `RETIRADO` no vuelve a `ACTIVO` (409); sus identificadores siguen reservados; nada se borra |
| BR-101 | Toda escalada temporal tiene caducidad explícita y expira sola | **Cumple** | `OtorgarEscalada`: `vigente_hasta` obligatorio, tope 24 h, motivo obligatorio, concedente ≠ receptor |
| INV-011 | Un dispositivo compartido tiene, en todo instante, cero o una sesión activa | **Cumple** | `abrir_sesion()` cierra la sesión de otra persona en la misma tableta con `dispositivo_compartido` (JRN-022) |
| Sesión única | Una persona tiene una sola sesión abierta en toda la instalación | **Cumple** | `abrir_sesion()`; probado en `test_abrir_en_otro_dispositivo_cierra_la_anterior_y_lo_avisa` (TST-027) |

---

## 5 · Roles, permisos y alcances

### 5.1 · Los cinco roles

| Rol del Maestro | Código | Menú | Nivel | Límite declarado por el Maestro | Cómo se respeta |
|---|---|---|---|---|---|
| Administrador | `ADMIN` | `admin` | 3 | No califica de forma directa, no accede al modo de estudio del alumno | Sin `student.progress.write` ni `student.exam.attempt` |
| Profesor | `TEACHER` | `teacher` | 2 | Actúa sobre sus grupos, sus alumnos y sus objetos | Todos sus permisos de gestión son `ASSIGNED_GROUPS` |
| Alumno | `STUDENT` | `student` | 1 | Solo sobre lo propio. Una sola sesión abierta | Todos `SELF`; sesión única |
| Reportes | `REPORTS` | `reports` | 2 | Solo lectura. Ninguna escritura sobre datos académicos | Sólo permisos `.read`, `.view` y los propios de sesión |
| Técnico AVACOM | `TECHNICIAN` | `technician` | 2 | Sin acceso a datos personales ni a evidencias | Sin `identity.user.read`; sólo dispositivos, roles (lectura) y sesiones (lectura) |

Los roles personalizados se componen con `CrearRol` a partir de una plantilla, sin superar el alcance máximo de cada permiso, tal como exige el Maestro.

### 5.2 · Alcances

| Maestro | Código | Cómo se resuelve |
|---|---|---|
| propio | `SELF` | El objetivo es la misma persona |
| grupo | `ASSIGNED_GROUPS` | El objetivo es estudiante de un grupo donde el actor es docente vigente **o** que le abre la asignación de su rol |
| nivel | `LEVEL` | La asignación del rol (`m01_usuario_rol.alcance_tipo = LEVEL`) abre todos los grupos activos de ese nivel educativo |
| instalación | `ORGANIZATION` | Toda la organización, hasta el propio nivel jerárquico |

**Regla del Maestro que cambió el comportamiento:** «cualquier objeto fuera de esa unión se evalúa como acceso denegado, nunca como objeto inexistente». Antes de la alineación, fuera de alcance respondía 404; ahora responde **403 `sin_permiso`** y el 404 queda para lo que no existe.

Otras reglas de alcance del Maestro:

| Regla | Veredicto | Nota |
|---|---|---|
| El alcance se resuelve por el objeto, nunca por un atributo del usuario | **Cumple** | El nivel educativo sale del grupo del estudiante, no de la persona |
| La denegación explícita vence a la acumulación de roles | **Cumple por construcción** | Con un solo rol efectivo por sesión no hay acumulación; las escaladas sólo amplían |
| Falla cerrada si el catálogo no se puede leer | **Cumple** | Sin concesión no hay permiso; `contexto()` falla si el rol de la sesión no existe |
| Reevaluación tras reinicio | **Cumple** | Cada petición reevalúa contra la base; no hay autorización en memoria |
| Licencia y permiso son cosas distintas | **Pendiente** | Depende de MOD-018 (Q-40) |

### 5.3 · Permisos `identity.*`

Los seis que el Maestro exige a MOD-001 existen con su nombre exacto: `identity.user.create`, `identity.role.assign`, `identity.user.import`, `identity.password.reset`, `identity.user.unlock`, `identity.session.revoke`. El resto del módulo se nombró en el mismo espacio (`identity.user.read`, `identity.exam_access.grant`, `identity.escalation.grant`, `identity.policy.manage`…). La migración `0004_datos_mod001` renombró los códigos anteriores conservando los roles y escaladas que los referenciaban.

### 5.4 · Escaladas

| Maestro | Código |
|---|---|
| Seis tipos con duración máxima; ESC-02 (`identity.user.unlock`, `identity.session.revoke`) 2 h sin prórroga | `m01_usuario_permiso` es la escalada: `motivo` y `vigente_hasta` obligatorios, tope general de 24 h. Los topes por tipo (2 h, 30 min…) quedan como Q-39 |
| Quien concede debe ser distinto de quien recibe | **Cumple**: la autoconcesión responde 403 |
| Ninguna escalada se renueva sola | **Cumple**: caduca por `vigente_hasta`; renovar es un asiento nuevo |

---

## 6 · Eventos

Todos los eventos del módulo siguen la nomenclatura `identidad.<agregado>.<hecho>.v1` y se escriben en `m01_evento_salida` dentro de la misma transacción que el hecho (Parte VII del documento de Arquitectura). Una prueba lo verifica sobre todos los eventos generados.

| Evento del Maestro | En el código |
|---|---|
| `identidad.usuario.creado.v1` | ✔ |
| `identidad.usuarios.importados.v1` | ✔ |
| `identidad.rol.asignado.v1` | ✔ |
| `identidad.sesion.abierta.v1` | ✔ |
| `identidad.sesion.cerrada.v1` | ✔ (con `motivo` en la carga) |
| `identidad.sesiones.revocadas.v1` | ✔ |
| `identidad.sesion.restaurada.v1` | definido; se publica con el aviso de arranque de MOD-015 |
| `identidad.credencial.restablecida.v1` | ✔ |
| `identidad.cuenta.bloqueada.v1` | ✔ |
| `identidad.cuenta.desbloqueada.v1` | ✔ |
| Adicionales del módulo | `identidad.escalada.concedida.v1`, `identidad.usuario.vinculado.v1`, `identidad.acceso_temporal.*.v1`, `identidad.politica.configurada.v1`, `identidad.grupo.*.v1`, `identidad.dispositivo.*.v1` |

---

## 7 · Modelo de datos: correspondencia tabla a tabla

| Tabla del Maestro | Tabla del módulo | Veredicto | Diferencia y motivo |
|---|---|---|---|
| `m01_persona` | `m01_usuario` + `m01_persona` | **Cumple con matiz** | Se separa la **cuenta** (estado, alias, rol principal) de los **datos personales** (cifrados con AES-256-GCM). El Maestro no exige cifrado en reposo; aquí se añade porque el SQLite viaja en un portátil escolar con datos de menores. `provisional` y `vinculado_a` están en `m01_usuario` |
| `m01_identificador_externo` | `m01_identificador_usuario` | **Cumple** | Mismos conceptos: `tipo`, `emisor`, `principal`. Tipos: `DNI` (documento nacional, equivale a CURP), `CODIGO_ESTUDIANTIL` (matrícula), `CLAVE_INSTALACION`, `EMAIL`. El valor va cifrado y se busca por índice HMAC |
| `m01_credencial` | `m01_credencial` | **Cumple con matiz** | Tipos `PIN`, `PASSWORD`, `AVATAR`. En vez de `valor_hash + sal + iteraciones`, una sola cadena Argon2id que incluye parámetros y sal. **Sin contador `intentos_fallidos`**: se calcula sobre `m01_intento_acceso` para conservar el historial completo (quién falló, cuándo, quién desbloqueó) |
| `m01_rol`, `m01_permiso`, `m01_rol_permiso` | idem | **Cumple** | `alcance_maximo` en el permiso y `sensible` en el catálogo (`ListarPermisos`) |
| `m01_persona_rol` | `m01_usuario_rol` | **Cumple** | `alcance_tipo` + `alcance_id` + `desde/hasta`, más `asignado_por` y `revocado_en` |
| `m01_escalada` | `m01_usuario_permiso` | **Cumple** | Mismas columnas obligatorias: `motivo`, `autorizada_por` (`otorgado_por`), `caduca_en` (`vigente_hasta`), `revocada_en` |
| `m01_sesion_usuario` | `m01_sesion` | **Cumple** | Índice de sesión única: el Maestro lo pone como índice parcial; aquí lo impone `abrir_sesion()` cerrando las demás, porque la fila de la sesión cerrada debe conservar su historial. Añade `rol` (efectivo), `clase` (`NORMAL`/`TEMPORAL`) y `evaluacion_ref` |
| — | `m01_organizacion`, `m01_politica_credencial`, `m01_grupo`, `m01_miembro_grupo`, `m01_dispositivo`, `m01_intento_acceso`, `m01_autorizacion_temporal`, `m01_evento_salida` | **Añadidas** | Contexto que el Maestro reparte en MOD-002 (grupos), MOD-009 (dispositivos), MOD-015 (cola) y la configuración BR-023. Se mantienen dentro del módulo hasta que esos módulos existan; los grupos y dispositivos se **replicarán** desde su dueño cuando llegue (§9) |

### 7.1 · Convenciones del modelo (CV-01 a CV-09)

| Convención | Veredicto | Nota |
|---|---|---|
| CV-01 Prefijo por módulo | **Cumple** | Todas las tablas son `m01_*` |
| CV-02 Identificador de texto con cinco segmentos | **Cumple con matiz** | Claves de texto (UUID v4). El generador de cinco segmentos pertenece a MOD-015 (Q-38) |
| CV-03 Tiempo en milisegundos, reloj del nodo | **Cumple** | Todo `*_en` es bigint ms |
| CV-04 Tres columnas: creado_en, creado_por, secuencia | **Parcial** | `creado_en` y `creado_por` sí; `secuencia` depende del contador global de MOD-015 (Q-38) |
| CV-05 Nada se borra | **Cumple** | Identificadores se retiran; asignaciones y escaladas se revocan; usuarios pasan a `RETIRADO`. Excepción documentada: `m01_rol_permiso` es configuración y se reescribe al editar un rol |
| CV-06 Estados acotados por el motor | **Parcial** | Los `CHECK` cubren rangos, vigencias y exclusiones; los enumerados los acota el dominio (`Enum`). Añadir `CHECK IN (...)` es trivial y se anota |
| CV-07 Las invariantes son índices | **Cumple** | Una credencial activa, un identificador principal, una asignación vigente por (rol, alcance), un escalado vigente por permiso |
| CV-08 Referencias al contenido son texto | **Cumple** | `evaluacion_ref` es texto sin FK |
| CV-09 Claves foráneas activas | **Cumple** | Django + SQLite con FK activas |

---

## 8 · Pantallas, mensajes y pruebas del Maestro cubiertos por la API

| Elemento | Qué exige | Qué entrega el backend |
|---|---|---|
| PAN-101 Identificarse | Avatar, clave corta o contraseña según nivel | `GET /configuracion/` con `perfiles.student.niveles` |
| PAN-103 Sesión cerrada en otro dispositivo | Dónde estaba, qué se conservó, continuar aquí | `sesion_anterior` en la respuesta de login; `401 sesion_cerrada_otro_dispositivo` en el dispositivo abandonado |
| PAN-204 Hoja de acceso del administrador | Credencial inicial de un solo uso | `password_inicial` en `POST /instalacion/` |
| PAN-220 Importar padrón | Vista previa, filas rechazadas descargables | `POST /usuarios/importar/` devuelve `creados`, `existentes`, `rechazadas` |
| PAN-221 Usuarios y roles · PAN-222 Componer rol | Rol, nivel, estado; catálogo con alcance | `GET /usuarios/`, `GET /roles/`, `GET /permisos/` (con `sensible`), `POST /roles/` |
| PAN-241 Escalada temporal | Permiso, motivo, caducidad, quién autorizó | `POST /usuarios/{id}/escaladas/` |
| MSG-020 / MSG-021 | «Tenías tu sesión abierta en {dispositivo}. Se cerró allí…» | `sesion_anterior.dispositivo` |
| MSG-022 Clave equivocada | «Esa clave no es. Inténtalo otra vez…» | `401 credenciales_invalidas` con `intentos_restantes` |
| MSG-023 Alumno sin credencial a la mano | «Tu profesor puede dejarte entrar por tu nombre y vincularlo después» | `POST /usuarios/` con `provisional: true` + `POST /usuarios/{id}/vincular/` |
| TST-027 Doble sesión del alumno | La sesión A queda cerrada, prevalece la más reciente | `test_abrir_en_otro_dispositivo_cierra_la_anterior_y_lo_avisa` |
| TST-064 Alumno con función de profesor | Denegado y auditado | Pruebas de alcance en `test_politicas` y `test_api_usuarios` |
| TST-066 Rol personalizado | 3 acciones permitidas y 3 denegadas según la matriz | `test_rol_del_colegio_clonado_de_plantilla` |
| TST-067 Sesión caducada | Acción rechazada, reingreso solicitado | `test_sesion_se_cierra_por_inactividad`, `test_sesion_expirada` |
| TST-070 Usuario desactivado | Ingreso denegado y sesiones cerradas | `test_suspender_revoca_y_la_baja_no_se_revierte` |
| TST-074 Acceso por avatar | Ingreso en 2 toques sin teclado | `test_politica_por_nivel_educativo_preescolar_con_avatar` |

---

## 9 · Decisiones tomadas que difieren del Maestro

| # | Tema | Maestro | Decisión aquí | Por qué |
|---|---|---|---|---|
| D-1 | Bloqueo por intentos | Contador `intentos_fallidos` en la credencial y estado `bloqueada` | Se calcula sobre el registro de intentos; `DESBLOQUEO` es una fila más | Conserva el historial completo; desbloquear no borra evidencia |
| D-2 | Datos personales | Sin cifrado en reposo | AES-256-GCM + índice HMAC | Datos de menores en un SQLite que viaja en portátil |
| D-3 | Hash de credenciales | `valor_hash + sal + iteraciones` genéricos | Argon2id en cadena única | Estándar OWASP; parámetros incluidos en la cadena |
| D-4 | Grupos, dispositivos y cola | Son de MOD-002, MOD-009 y MOD-015 | Grupos y cola viven dentro de `acceso` con prefijo `m01_`; los dispositivos pasaron a MOD-009 (`device_manager`, `m09_dispositivo`) el 2026-09-28 | Grupos y cola se replicarán desde su dueño cuando exista; los dispositivos ya se leen por el puerto del dueño |
| D-5 | Inactividad | Temporizador del sistema | Se decide al primer contacto tras el plazo | Sin proceso en segundo plano; mismo efecto para quien usa la sesión |
| D-6 | Cierre por otro dispositivo | Índice único parcial | Cierre explícito en `abrir_sesion()` | La fila cerrada conserva su motivo e historial |
| D-7 | Identificador de cinco segmentos y `secuencia` | Obligatorios en toda tabla | UUID y sin `secuencia` | El generador pertenece a MOD-015; se añadirá con él |

---

## 10 · Pendientes y preguntas abiertas

| # | Pregunta | Propuesta |
|---|---|---|
| Q-38 | Identificador de cinco segmentos y columna `secuencia` (CV-02, CV-04) | Implementar el emisor y el contador en MOD-015 y migrar `id` y `secuencia` en todas las `m01_*` |
| Q-39 | Topes de escalada por tipo (ESC-01 a ESC-06) | Tabla `m01_tipo_escalada` con duración máxima y prórroga; hoy el tope es 24 h general |
| Q-40 | «No disponible por licencia» distinto de «acceso denegado» | Cuando exista MOD-018, la política consultará la licencia antes del permiso |
| Q-41 | CAP-006 suplente | Registrar en MOD-002 la asignación docente con papel `suplente`; MOD-001 ya acota el rol por grupo y vigencia |
| Q-42 | Publicar `identidad.sesion.restaurada.v1` | Al aviso de arranque de MOD-015, marcar las sesiones vigentes como restauradas |
| Q-43 | Orden de cierre de MOD-009 | Consumir `identidad.sesion.cerrada.v1` con motivo `otro_dispositivo` o `dispositivo_compartido` para destruir la clave del contenedor |
| Q-34 | Exigir sesión en expediente y biblioteca | Sigue abierta: `AVACOM_LMS_EXIGIR_SESION=1` cuando las apps MAUI tengan las pantallas de acceso |
