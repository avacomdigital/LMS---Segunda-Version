# 05 · Módulo de acceso · Requisitos de la semana (PIN maestro, docentes, alumnos y visitantes)

| Campo | Valor |
|---|---|
| Fecha | 2026-10-05 |
| Fuente normativa | `AVACOM_LMS_Documento_Maestro_Consolidado_v1.0` · MOD-001 *Identity & Access* (capacidades, funciones, reglas, escenarios), JRN-001, JRN-007, PAN-002, PAN-204, NFR-031 |
| Punto de partida | Lo que ya existe en [01 · Modelado](01-modelado-datos.md), [02 · Endpoints](02-Endpoints.md), [03 · Casos de uso](03-casos-de-uso-backend.md) y [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md), más lo que hay hoy en OPS y Student (ver §2) |
| Para qué sirve | Lista cerrada de lo que hay que construir esta semana para dar por completo el módulo de acceso, partida en **dominio del problema**, **backend** y **frontend MAUI** |
| Estado | Propuesta para revisión. Las decisiones que tomé por mi cuenta están en §6 y las que necesito que confirmes en §7 |

> **Condición que lo gobierna todo: el LMS funciona sin internet.** Sin internet no hay correo, ni SMS, ni «recuperar por enlace», ni servicio central que diga quién es quién. Lo que sí existe es el nodo del aula (el equipo con OPS Master) en la red local. Toda identificación y toda recuperación de acceso se resuelven entre las personas y ese nodo.

---

## 0 · Qué se pidió, en una página

| Quién | Qué necesita | Cómo lo resuelve el módulo |
|---|---|---|
| **Administrador o técnico** | Dejar el aula protegida la primera vez que se instala | Configura el **PIN maestro** (6 dígitos) en el primer arranque. Puede cambiarlo cuando quiera. **Está obligado a cambiarlo una vez al año** |
| **Profesor** | Tener su usuario y recuperar su contraseña sin llamar a nadie | Con el PIN maestro **crea su propio usuario** y **restablece su propia contraseña** |
| **Estudiante** | Tener su usuario y entrar rápido | **Crea su propio usuario** y elige un **PIN fácil de reconocer**. Entra tocando su nombre y marcando su PIN |
| **Estudiante que olvidó su PIN** | Seguir en la clase sin frenarla | Entra como **visitante**. No necesita al profesor, así que «olvidé mi clave» deja de servir para sabotear la clase |

Lo que **no** cambia: el modelo de roles, alcances, escaladas, sesión única, bloqueo por intentos, pase de examen y auditoría que ya están hechos y probados (118 pruebas en verde). Esta semana se añade encima.

---

# PARTE A · Requerimientos del Documento Maestro para este módulo

*(Tarea 1 · lista de requerimientos según el Maestro.)* El estado sale de [04 · Lineamientos](04-Lineamientos-Al-Documento-Maestro.md) contrastado con el código y con las pantallas de OPS y Student tal como están hoy.

| Estado | Significado |
|---|---|
| **Hecho** | Implementado y probado; no se toca |
| **Falta pantalla** | El backend lo cumple; ninguna app MAUI lo ofrece todavía |
| **Cambia** | Existe, pero lo pedido esta semana lo modifica |
| **Nuevo** | No existe |

## A.1 · Capacidades y funciones

| ID del Maestro | Requerimiento | Estado | Qué pasa esta semana |
|---|---|---|---|
| CAP-001 | Iniciar sesión con credencial local del nodo, sin red (alumno) | **Cambia** | El alumno ya no teclea código y clave: toca su nombre y marca su PIN (RN-30…RN-34) |
| CAP-002 | Entrar a clase sin escribir contraseña | **Hecho** | Se conserva el pase de examen. Se suma el **visitante** (RN-40…RN-47) |
| CAP-003 | Alta masiva desde archivo (administrador) | **Falta pantalla** | Fuera de esta semana salvo el ajuste de RB-26 (importados sin PIN) |
| CAP-004 | Restablecer el acceso desde el aula, sin soporte externo | **Cambia** | Profesor: se resuelve con el **PIN maestro** (RN-20…RN-25). Alumno: el profesor deja el PIN «pendiente» y el alumno elige uno nuevo (RN-35) |
| CAP-005 | Asignar roles y permisos por perfil (administrador) | **Falta pantalla** | Sin cambio de alcance; sólo se añade el permiso `identity.master_pin.manage` |
| CAP-006 | Delegar acceso temporal a un suplente | **Hecho** (backend) | Sin cambio |
| FUN-001 | Crear cuenta local | **Cambia** | Aparecen tres vías nuevas: autoalta de profesor, autoalta de alumno y visitante efímero (RN-05) |
| FUN-004 | Autenticar al profesor con contraseña en el nodo | **Hecho** | Sin cambio |
| FUN-005 | Autenticar al alumno con código o PIN | **Cambia** | Entra eligiendo su nombre en la lista del grupo (PAN-002) |
| FUN-006 | Restablecer la contraseña de un usuario | **Cambia** | Profesor: lo hace el propio profesor con PIN maestro. Administrador y técnico: **no** se restablecen con el PIN maestro |
| FUN-007 | Bloquear la cuenta tras intentos fallidos | **Cambia** | Para alumnos el castigo recae en la **tableta**, no en la cuenta (RN-33) |
| FUN-008 · 009 · 010 · 011 | Desbloquear, cerrar por inactividad, revocar sesiones, restaurar tras reinicio | **Hecho** | Sin cambio |

## A.2 · Reglas, invariantes y no funcionales

| ID | Requerimiento | Estado | Qué pasa esta semana |
|---|---|---|---|
| BR-020 | Identidad interna estable, distinta del nombre de acceso | **Hecho** | El alumno que se registra recibe un UUID; lo que ve y toca es su nombre |
| BR-021 | Varios roles, un rol efectivo por sesión | **Hecho** | Sin cambio |
| BR-023 | Longitud, caducidad y bloqueo configurables por institución, personal y alumnos por separado | **Cambia** | Se añade el PIN maestro como política propia, con vigencia fija de 365 días que nadie puede alargar |
| BR-024 | Nivel inicial con método simplificado (avatar o PIN) | **Hecho** | Preescolar sigue pudiendo usar avatar. Ningún otro nivel pasa a contraseña por defecto (D-A3) |
| BR-025 | La baja conserva identidad e historial | **Hecho** | El visitante efímero se retira al cerrar, nunca se borra (RN-45) |
| BR-047 | Un alumno se une a la clase si está inscrito, **o si el profesor lo admite como invitado** | **Nuevo** | El visitante es ese invitado; entra por su cuenta sin que el profesor tenga que admitirlo (RN-41, PA-04) |
| BR-053 · BR-057 · INV-011 | Tableta compartida: se limpia al salir y tiene cero o una sesión | **Hecho** | El visitante cumple lo mismo |
| BR-101 | Toda escalada temporal caduca sola | **Hecho** | El PIN maestro **no** es una escalada: es un secreto de la institución con vigencia anual (D-A5) |
| NFR-031 | Credencial resistente, una sesión por usuario, bloqueo a los 5 intentos en 15 min | **Cambia** | Se aplica también al PIN maestro, por tableta y global (RN-09) |
| NFR-038 | Contenedor cifrado por sesión en tableta compartida, clave destruida al cerrar | **Hecho** (MOD-009) | El visitante lo hereda |
| NFR-039 · AC-003 | El técnico no lee datos personales ni evidencias | **Hecho** | El técnico puede configurar el PIN maestro en la instalación, pero **no** ver listas de personas |
| AC-002 · TST-027 | Doble sesión: prevalece la más reciente | **Hecho** | Sin cambio; aplica a alumnos y profesores, no a visitantes (cada visita es una cuenta distinta) |
| JRN-001 · PAN-204 | Primer arranque: crear el administrador y entregar la **hoja de acceso** de un solo uso | **Falta pantalla** y **Cambia** | OPS no tiene la pantalla de primer arranque (el README del instalador la deja como «tarea de la aplicación»). Ahí se configura el PIN maestro (RF-01…RF-04) |
| JRN-007 · PAN-002 | El alumno toca su nombre en la lista y escribe su clave o toca su avatar | **Cambia** | Es exactamente el flujo nuevo del alumno (RF-20…RF-24) |
| UXR-005 · UXR-009 | Mensajes que dicen qué pasó y qué sigue, sin códigos ni la palabra «error» | **Hecho** como regla | Todos los mensajes nuevos la cumplen (§5) |
| Niveles educativos | Preescolar avatar · primaria clave corta · secundaria en adelante usuario y contraseña | **Cambia** | El pedido es PIN para todos los alumnos; el Maestro sólo lo exige hasta primaria. Secundaria puede volver a contraseña con `ConfigurarPolitica` sin tocar código |

## A.3 · Escenarios de prueba del Maestro que siguen siendo obligatorios

TST-027 (doble sesión), TST-064 (alumno con función de profesor), TST-065 (profesor en configuración), TST-066 (rol personalizado), TST-067 (sesión caducada), TST-070 (usuario desactivado), TST-074 (acceso por avatar). Ninguno debe romperse con lo nuevo. Los criterios de aceptación de lo nuevo están en §8.

---

# PARTE B · Dominio del problema

## B.1 · Actores

| Actor | Quién es | Qué necesita de este módulo |
|---|---|---|
| **Técnico AVACOM** | Quien instala el equipo | Dejar el nodo con organización, administrador y PIN maestro, sin ver datos personales |
| **Administrador** | Rectoría o coordinación | Custodiar el PIN maestro, cambiarlo, ver quién se registró con él |
| **Profesor** | Quien da clase | Crear su usuario y recuperar su contraseña estando solo con su grupo |
| **Estudiante** | Quien aprende | Tener usuario, PIN fácil, entrar en segundos, no depender de nadie |
| **Visitante** | Un estudiante sin PIN a la mano (o una persona sin cuenta) | Seguir la clase sin identidad confirmada |
| **Sistema (nodo)** | El equipo del aula | Aplicar las reglas sin internet y dejar rastro de todo |

## B.2 · Glosario nuevo

| Término | Significado |
|---|---|
| **PIN maestro** | Número de 6 dígitos que pertenece a la **institución**, no a una persona. Quien lo conoce puede crear su cuenta de profesor y restablecer la contraseña de un profesor. Nunca se vuelve a mostrar después de configurarlo |
| **Versión del PIN maestro** | Cada vez que se configura o se cambia nace una versión nueva con fecha de inicio y de vencimiento. Las anteriores quedan guardadas (nada se borra) |
| **PIN del alumno** | Número que el alumno elige para entrar. Sirve para reconocerse, no para custodiar secretos: se prefiere fácil de recordar |
| **PIN pendiente** | Estado de un alumno cuya cuenta existe pero que aún no eligió su PIN (alta por padrón o PIN restablecido) |
| **Visitante** | Sesión sin identidad confirmada. Cada entrada crea una cuenta efímera «Visitante · tableta N», con permisos mínimos |
| **Origen de la cuenta** | Cómo nació: `INSTALACION`, `IMPORTACION`, `PROFESOR`, `AUTOALTA_ALUMNO`, `PIN_MAESTRO`, `VISITANTE` |

## B.3 · Reglas de negocio

### B.3.1 · PIN maestro

| ID | Regla |
|---|---|
| **RN-01** | Hay **un solo** PIN maestro vigente por organización. |
| **RN-02** | Tiene **exactamente seis dígitos**. No admite letras. |
| **RN-03** | Se configura **por primera vez** en el primer arranque del equipo, por el técnico o el administrador, junto con la organización y el primer administrador. Sin PIN maestro configurado, el alta y el restablecimiento de profesores **no existen** (la pantalla ni se ofrece). |
| **RN-04** | Sólo se guarda su huella Argon2id. **Nadie puede leerlo después**, ni el administrador. Si se olvida se **reemplaza**, no se recupera. |
| **RN-05** | Rechaza PIN triviales: seis iguales (`111111`), secuencias (`123456`, `654321`), parejas repetidas (`121212`) y cualquiera de los **tres últimos** usados. |
| **RN-06** | El administrador lo cambia **cuando quiera**, con su sesión abierta. No necesita saber el actual: así puede reemplazarlo si se filtró o se perdió. |
| **RN-07** | **Vigencia obligatoria de 365 días**, contados desde que nace la versión. Nadie puede alargarla ni apagarla: no es configurable. Cambiarlo antes reinicia el reloj. |
| **RN-08** | **Aviso a los 30 días** del vencimiento a administrador y técnico (tablero de OPS). A los profesores **no** se les muestra una cuenta atrás: sólo se les dice «Pide el PIN maestro a administración». |
| **RN-09** | **Vencido** (día 366): el PIN deja de aceptar **altas y restablecimientos de profesores**. No bloquea nada más: las clases, los alumnos y los profesores ya registrados siguen operando. Esto respeta que «una sesión suspendida nunca bloquea al profesor» (DEC-018). Se cambia con la sesión del administrador. |
| **RN-10** | Contra la adivinación (hay un millón de combinaciones): **5 fallos en 15 minutos desde un mismo equipo** lo bloquean 15 minutos; tras **tres bloqueos seguidos** el bloqueo sube a 60 minutos y se avisa al administrador. Además hay un tope **global** de 20 fallos por hora en todo el nodo. Cada fallo y cada bloqueo quedan auditados. |
| **RN-11** | El PIN maestro **sólo se acepta desde un equipo que no sea una tableta de alumno** (`m09_dispositivo.tipo` ≠ `TABLETA`). Así un alumno no puede probar combinaciones desde su tableta. |
| **RN-12** | El PIN maestro es de la institución: **no abre** cuentas de administrador, reportes ni técnico, **ni** restablece sus contraseñas. Sólo crea y restablece **profesores**. |

### B.3.2 · Profesor

| ID | Regla |
|---|---|
| **RN-20** | Un profesor crea su usuario con: documento, nombres, apellidos, contraseña (dos veces) y el **PIN maestro**. El rol es siempre `TEACHER`. |
| **RN-21** | La contraseña cumple la política del perfil `teacher` (hoy: 8 caracteres, mayúscula y símbolo). La definitiva se elige en ese momento: **no** nace provisional. |
| **RN-22** | La cuenta nace **activa** y su origen es `PIN_MAESTRO`. La institución «aprueba» con el PIN; a cambio, el administrador ve en una lista quién se registró así y puede **suspenderlo** (PA-02). |
| **RN-23** | El profesor elige al registrarse los **grupos que dicta** (los existentes). Sin grupo no ve nada; con grupo, ve sólo lo suyo (alcance `ASSIGNED_GROUPS`, sin cambio). |
| **RN-24** | Para restablecer su contraseña, el profesor da su **documento**, el **PIN maestro** y la contraseña nueva (dos veces). Se cierran todas sus sesiones y queda auditado quién, desde qué equipo y cuándo. |
| **RN-25** | Mientras el PIN no sea válido, la respuesta es la misma exista o no el documento (no se descubre quién es profesor). Una vez el PIN es válido, sí se puede decir «ese documento no es de un profesor». |

### B.3.3 · Estudiante

| ID | Regla |
|---|---|
| **RN-30** | El estudiante crea su usuario con: **grupo**, **nombre** y **PIN** (dos veces). No necesita documento ni código. |
| **RN-31** | El PIN del alumno es **numérico de 4 a 6 dígitos** (por defecto 4) y **sin reglas de complejidad**: se quiere que lo recuerde, no que sea secreto de Estado. `1234` es válido. |
| **RN-32** | Para entrar, el alumno **elige su grupo, toca su nombre y marca su PIN**. No teclea nada más (PAN-002). Los nombres visibles son sólo el **alias** (nombre + inicial), nunca documento ni otros datos. |
| **RN-33** | **El castigo por fallar recae en la tableta, no en la cuenta.** Tras 5 fallos en 15 minutos en una tableta, esa tableta espera 2 minutos para PIN. La cuenta del alumno **no se bloquea nunca por intentos**, porque si no un compañero podría bloquearla a propósito. Entrar como visitante **nunca** se bloquea. |
| **RN-34** | El alias es **único dentro del grupo** (sin distinguir mayúsculas ni tildes). Si ya existe, se pide una letra más («Juan P.» → «Juan Pé.») en lugar de rechazar sin salida. |
| **RN-35** | Cuando el profesor «restablece el PIN» de un alumno, **no se genera ni se imprime un número**: la cuenta queda en **PIN pendiente** y el alumno elige uno nuevo la próxima vez que toque su nombre. Lo mismo para alumnos creados por padrón o importación sin PIN. |
| **RN-36** | El alumno puede **cambiar su PIN** con la sesión abierta. Los alumnos autoregistrados quedan marcados «sin confirmar» y el profesor puede **confirmarlos** (o vincularlos con el padrón, JRN-007). |
| **RN-37** | La autoalta se controla con una política **`autoregistro`** por perfil. Encendida por defecto para `student`. El administrador la apaga y desde ese momento sólo hay padrón o alta del profesor. |

### B.3.4 · Visitante

| ID | Regla |
|---|---|
| **RN-40** | En la pantalla de acceso del alumno **siempre** hay un botón «Entrar como visitante», visible desde el primer momento (no aparece sólo después de fallar). |
| **RN-41** | Entrar como visitante **no requiere profesor, PIN ni código**: dos toques. Es el invitado de BR-047, sin que el profesor tenga que admitirlo cada vez. |
| **RN-42** | **Puede**: unirse a la clase en vivo y seguir la proyección, responder las actividades en vivo de esa clase, leer lecciones y practicar. |
| **RN-43** | **No puede**: rendir evaluaciones formales, hacer el modo estudio **asignado** con progreso, ver o cambiar un progreso o un PIN, descargar paquetes (BR-054) ni cambiar ninguna credencial. |
| **RN-44** | Lo que el visitante hace **no entra al expediente de nadie**. Queda ligado a «Visitante · tableta N» y a la clase. Si el profesor identifica después quién fue, puede **vincular** esa visita a un alumno y acreditarle lo hecho (mismo mecanismo de JRN-007). |
| **RN-45** | Cada visita es una **cuenta efímera** con rol `STUDENT`, `provisional`, origen `VISITANTE`. Se **retira** al cerrar la sesión o a las 24 h; nunca se borra (CV-05). Como son cuentas distintas, la regla de sesión única no hace que un visitante cierre a otro. |
| **RN-46** | El profesor **ve** quiénes entraron como visitante (cuántos y desde qué tableta) en el monitor de actividad de OPS: la rendición de cuentas contra el sabotaje es la tableta, no la persona. |
| **RN-47** | La política **`visitante`** (por institución) permite apagarlo. Encendida por defecto. |

## B.4 · Qué NO es el visitante

No es una forma de saltarse una evaluación. Si un alumno olvidó su PIN **durante un examen**, entra como visitante a la clase, pero la evaluación formal queda cerrada para él. El profesor conserva, **por su propia decisión**, el pase de examen que ya existe (CAP-002, `OtorgarAccesoTemporal`); no forma parte del camino normal ni se ofrece desde la tableta del alumno (PA-05).

## B.5 · Riesgos asumidos

| # | Riesgo | Cómo se acota |
|---|---|---|
| R-1 | El PIN maestro lo conocen **todos los profesores**: uno podría restablecer la contraseña de otro y entrar en su cuenta | Sesiones cerradas y asiento de auditoría con equipo y hora; la víctima ve el cierre; el administrador puede suspender. No es un control fuerte: es el que permite operar sin internet. |
| R-2 | Alguien con el PIN maestro registra una cuenta de profesor que no lo es | RN-11 (no desde tabletas), RN-22 (lista y suspensión) y RN-07 (cambio anual) |
| R-3 | Un alumno **reclama** la cuenta sin PIN de un compañero antes que él | Aceptado: sin sistema central no hay verificación de identidad (misma postura que D-15 de Modo Estudio). El profesor lo corrige con «PIN pendiente» y queda auditado. |
| R-4 | Un alumno crea muchas cuentas falsas | RN-37 (apagable), tope de 5 altas por tableta por hora (RB-17), lista de «sin confirmar» para el profesor |
| R-5 | PIN de alumno trivial (`1234`) | Es deliberado (RN-31): el PIN reconoce, no protege. Lo que protege es que el expediente sólo se ve por el profesor y que nada se puede dañar con una cuenta de alumno |

---

# PARTE C · Backend

Se mantiene la arquitectura en capas de [03 · Casos de uso](03-casos-de-uso-backend.md): `dominio/` y `aplicacion/` sin Django. Todo lo nuevo sale como casos de uso con su ruta, su serializer, su evento y sus pruebas.

## C.1 · Modelo de datos

| ID | Requerimiento |
|---|---|
| **RB-01** | **Tabla nueva `m01_pin_maestro`**: `id`, `organizacion_id` (FK), `hash` (Argon2id), `activa`, `creado_en`, `creado_por_id` (FK `m01_usuario`, nulo en el primer arranque), `vence_en`, `sustituida_en`. Índice único parcial: **una sola fila `activa=true` por organización** (CV-07). Las filas sustituidas se conservan (CV-05). |
| **RB-02** | **Registro de intentos del PIN maestro.** `m01_intento_acceso` ya sirve: `usuario` es nulo y `dispositivo` existe. Añadir el motivo `pin_maestro` y el resultado `FALLO`/`BLOQUEO`/`EXITO`. No hace falta tabla nueva. |
| **RB-03** | `m01_usuario` gana la columna **`origen`** (`INSTALACION` · `IMPORTACION` · `PROFESOR` · `AUTOALTA_ALUMNO` · `PIN_MAESTRO` · `VISITANTE`) y **`confirmado_en`** (nulo = «sin confirmar»). Las filas existentes se migran a `INSTALACION` o `IMPORTACION` según el caso. |
| **RB-04** | `m01_politica_credencial` gana **`autoregistro`** (bool, sólo `student` y `teacher`; por defecto `true` para `student`) y **`bloqueo_alcance`** (`CUENTA` · `DISPOSITIVO`; por defecto `DISPOSITIVO` para `student`, `CUENTA` para el resto). Se añade la política **`visitante`** como booleana de la organización (columna en `m01_organizacion`, por defecto `true`). |
| **RB-05** | `m01_credencial` admite el estado **«pendiente»** (alumno sin PIN elegido): la fila existe con `debe_cambiar=true` y sin hash utilizable, o no hay fila activa; elegir una u otra y fijarlo en el modelo. Mientras esté pendiente no se acepta ningún PIN. |
| **RB-06** | Nueva **migración `0010`** con estas columnas y la tabla, más una migración de datos que ponga `origen`. Idempotente y probada sobre una base con datos (como las cuatro primeras). |
| **RB-07** | Valor nuevo **`ClaseSesion.VISITANTE`** (como `TEMPORAL`) con su conjunto `PERMISOS_SESION_VISITANTE` en `dominio/plantillas.py`: `content.read`, las actividades en vivo del propio grupo y `identity.session.revoke_own`. **No** se crea un sexto rol (D-A4). |
| **RB-08** | Nuevo permiso **`identity.master_pin.manage`**: lo tiene `ADMIN` con alcance `ORGANIZATION`. `TECHNICIAN` **no** lo lleva por plantilla (sólo configura el primer PIN en la instalación, que es una ruta sin sesión). Sembrado por migración, como `0006…0009`. |

> Tras el cambio hay que actualizar [01 · Modelado](01-modelado-datos.md) (§3.x, índices y cardinalidades), el modelo implementado que lee el visor y el documento `spec-driven/10`, y regenerar el visor (pipeline en `spec-driven/10-modelo-datos-implementado.md`).

## C.2 · Casos de uso nuevos

| ID | Caso de uso | Qué hace | Ruta | Sesión · permiso |
|---|---|---|---|---|
| **RB-10** | `ConfigurarPinMaestro` | Crea la primera versión del PIN. Sólo si no hay ninguna. Parte de la instalación | dentro de `POST /instalacion/` | Sin sesión (día cero) |
| **RB-11** | `CambiarPinMaestro` | Nueva versión: valida RN-02 y RN-05, sustituye la anterior, reinicia el reloj de 365 días | `PUT /api/acceso/pin-maestro/` | Sí · `identity.master_pin.manage` |
| **RB-12** | `ConsultarEstadoPinMaestro` | `{configurado, vence_en, dias_restantes, vencido, bloqueado_hasta}`. **Nunca** devuelve el PIN ni su huella | `GET /api/acceso/pin-maestro/` | Sí · `identity.master_pin.manage` |
| **RB-13** | `RegistrarDocente` | RN-20…RN-23. Verifica PIN (RN-09, RN-10, RN-11), crea cuenta `TEACHER`, persona, identificador (documento), asignación de rol, pertenencia a los grupos elegidos y credencial definitiva | `POST /api/acceso/docentes/registro/` | **Sin sesión; autoriza el PIN maestro** |
| **RB-14** | `RestablecerContrasenaDocente` | RN-24 y RN-25. Verifica PIN, cambia la credencial, cierra sesiones con motivo `credencial_restablecida_pin_maestro` | `POST /api/acceso/docentes/restablecer/` | **Sin sesión; autoriza el PIN maestro** |
| **RB-15** | `ListarDocentesPorPinMaestro` | Cuentas con origen `PIN_MAESTRO`: alias, fecha, equipo, estado. Para que el administrador los revise o suspenda (RN-22) | `GET /api/acceso/docentes/?origen=PIN_MAESTRO` | Sí · `identity.user.read` |
| **RB-16** | `ListarEstudiantesDelGrupo` | Alias, estado y si tiene PIN pendiente de los alumnos **activos** de un grupo; nada más. Alimenta «toca tu nombre» | `GET /api/acceso/aula/grupos/` y `GET /api/acceso/aula/grupos/{id}/estudiantes/` | **Sin sesión** (PAN-002); sólo desde dispositivos registrados (BR-056) |
| **RB-17** | `RegistrarEstudiante` | RN-30, RN-31, RN-34, RN-37. Crea cuenta `STUDENT`, origen `AUTOALTA_ALUMNO`, `confirmado_en` nulo, PIN elegido, pertenencia al grupo, identificador `CLAVE_INSTALACION` oculto (DEC-049). Tope de **5 altas por tableta por hora** | `POST /api/acceso/estudiantes/registro/` | **Sin sesión** |
| **RB-18** | `EstablecerPinAlumno` | Primera vez o PIN pendiente (RN-35): el alumno elige su PIN tocando su nombre | `POST /api/acceso/estudiantes/{id}/pin/` | Sin sesión, **sólo si la cuenta está en PIN pendiente** |
| **RB-19** | `AbrirSesionVisitante` | RN-40…RN-47. Crea la cuenta efímera, abre sesión `VISITANTE` en la tableta (cierra la sesión de otra persona en ella, INV-011) y devuelve el pase | `POST /api/acceso/sesiones/visitante/` | **Sin sesión** · política `visitante` encendida |
| **RB-20** | `ConfirmarEstudiante` | El profesor marca «confirmado» a un alumno autoregistrado | `POST /api/acceso/usuarios/{id}/confirmar/` | Sí · `identity.user.update` |

Cambios sobre casos de uso existentes:

| ID | Caso de uso | Cambio |
|---|---|---|
| **RB-21** | `InstalarNodo` | Recibe `pin_maestro` (obligatorio) y lo guarda con RB-10. Rechaza instalar sin él. El comando `acceso_instalar` gana `--pin-maestro` (o lo lee de una variable de entorno, **nunca** de un argumento visible en el listado de procesos). |
| **RB-22** | `AutenticarUsuario` | Acepta **`usuario_id`** como alternativa a `identificador`, **sólo** para perfil `student` con PIN o avatar. Aplica RN-33 (bloqueo por dispositivo si `bloqueo_alcance=DISPOSITIVO`). Un alumno en PIN pendiente recibe `403 pin_pendiente` con el mensaje para elegirlo. |
| **RB-23** | `RestablecerCredencial` | Para un alumno: deja la credencial en **pendiente** y no devuelve secreto (RN-35). Para el resto, igual que hoy. |
| **RB-24** | `ConsultarConfiguracion` | Añade `pin_maestro: {configurado, vencido}` (sin fechas ni días: el estado fino es de administrador), `autoregistro_alumnos`, `visitante`. Sin datos personales. |
| **RB-25** | `ResolverPrincipal` | Reconoce `ClaseSesion.VISITANTE` y aplica `PERMISOS_SESION_VISITANTE`; 403 `sesion_visitante_limitada` en lo demás (con la misma forma que `sesion_temporal_limitada`). |
| **RB-26** | `padron.py` | `POST /padron/estudiantes/` deja de **generar** un PIN: sin PIN, la cuenta queda en PIN pendiente (RN-35). `secreto_inicial` desaparece de esa respuesta. Importar (`ImportarUsuarios`) hace lo mismo cuando la columna `secreto` viene vacía. |
| **RB-27** | `ConfigurarPolitica` | Admite `autoregistro`, `bloqueo_alcance` y el interruptor `visitante`. El dominio sigue impidiendo reglamentos absurdos (`PoliticaCredencial.validar()`): PIN de alumno fuera de 4..6, `bloqueo_alcance=DISPOSITIVO` para perfiles de personal, etc. |
| **RB-28** | Permisos de `TEACHER` | Recibe `identity.group.manage` acotado a los grupos que **crea** (queda como docente de ellos). Si no, un profesor registrado por PIN en un nodo sin grupos no puede hacer nada y depende de la administración (PA-03). |

## C.3 · Reglas de dominio (sin Django)

| ID | Requerimiento |
|---|---|
| **RB-30** | `dominio/politicas.py`: clase **`PoliticaPinMaestro`** con `validar_formato`, `es_trivial`, `esta_vencido`, `dias_restantes`, `evaluar_bloqueo` (RN-05, RN-07, RN-10). Sin I/O. |
| **RB-31** | `dominio/entidades.py`: entidad **`PinMaestro`** y valor **`OrigenCuenta`**. |
| **RB-32** | El bloqueo por dispositivo (RN-33 y RN-10) se **calcula** sobre `m01_intento_acceso`, igual que el bloqueo actual (D-1 de 04): sin contadores que se pierdan o se desincronicen. |
| **RB-33** | Vigencia anual con el reloj del nodo (`RelojNodo` / CV-03, milisegundos). Vencer es **calculado en el primer contacto** (sin temporizador), como la inactividad (D-5): `vence_en < ahora` en cada verificación. |
| **RB-34** | Comparación del PIN con `hmac.compare_digest` y verificación contra un hash señuelo si no hay versión activa, para que el tiempo no delate el estado. |

## C.4 · Contrato HTTP

### C.4.1 · Rutas nuevas

| Ruta | Verbo | Sesión | Cuerpo · respuesta |
|---|---|---|---|
| `/api/acceso/pin-maestro/` | GET | `identity.master_pin.manage` | `{ configurado, creado_en, vence_en, dias_restantes, vencido, bloqueado_hasta }` |
| `/api/acceso/pin-maestro/` | PUT | `identity.master_pin.manage` | `{ pin_nuevo }` → `200 { vence_en }` |
| `/api/acceso/docentes/registro/` | POST | no · PIN | `{ pin_maestro, documento, nombres, apellidos, secreto, grupos: [id…], dispositivo }` → `201 { id, alias }` |
| `/api/acceso/docentes/restablecer/` | POST | no · PIN | `{ pin_maestro, documento, secreto_nuevo, dispositivo }` → `200 { sesiones_revocadas }` |
| `/api/acceso/docentes/?origen=PIN_MAESTRO` | GET | `identity.user.read` | Lista de RB-15 |
| `/api/acceso/aula/grupos/` | GET | no · aparato registrado | `[{ id, codigo, nombre, nivel_clave }]` solo grupos con alumnos o con registro abierto |
| `/api/acceso/aula/grupos/{id}/estudiantes/` | GET | no · aparato registrado | `[{ id, alias, pin_pendiente }]` |
| `/api/acceso/estudiantes/registro/` | POST | no | `{ grupo_id, nombres, apellidos?, alias?, pin, dispositivo }` → `201 { id, alias }` |
| `/api/acceso/estudiantes/{id}/pin/` | POST | no · sólo PIN pendiente | `{ pin, dispositivo }` → `200` |
| `/api/acceso/sesiones/visitante/` | POST | no | `{ dispositivo, grupo_id? }` → `200` con la forma del login y `clase_sesion: "VISITANTE"` |
| `/api/acceso/usuarios/{id}/confirmar/` | POST | `identity.user.update` | → `200 { confirmado_en }` |

**Decisión de diseño: no existe `POST /pin-maestro/verificar/`.** Un endpoint que sólo diga «sí/no» sería el oráculo perfecto para quien prueba combinaciones. El PIN se verifica **dentro** de la operación que autoriza (alta o restablecimiento). A cambio, la app conserva lo escrito si el PIN falla, para no obligar a volver a teclear.

Estas rutas **no declaran un permiso `identity.*`**: su autorización es el PIN maestro. Es una excepción deliberada a «toda ruta declara permiso» y se documenta como tal en [02 · Endpoints](02-Endpoints.md).

### C.4.2 · Cambios sobre rutas existentes

| Ruta | Cambio |
|---|---|
| `POST /instalacion/` | Entrada `pin_maestro`; la respuesta **no** lo devuelve |
| `GET /configuracion/` | Campos nuevos de RB-24 |
| `POST /sesiones/` | Admite `usuario_id` (alumnos) |
| `POST /usuarios/{id}/credencial/restablecer/` | Alumno → PIN pendiente, sin secreto en la respuesta |
| `POST /padron/estudiantes/` | Sin `secreto_inicial` |
| `GET /api/acceso/yo/` | Incluye `origen` y `confirmado` en `usuario` |

### C.4.3 · Códigos de error nuevos

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `pin_invalido` · `pin_debil` | No son 6 dígitos · es trivial o repetido (RN-05) |
| 401 | `pin_maestro_invalido` | PIN equivocado (trae `intentos_restantes`) |
| 403 | `pin_maestro_vencido` | RN-09 |
| 403 | `dispositivo_no_autorizado` | RN-11: desde una tableta de alumno |
| 403 | `registro_cerrado` · `visitante_no_permitido` | Las políticas están apagadas |
| 403 | `pin_pendiente` | El alumno aún no eligió su PIN |
| 403 | `sesion_visitante_limitada` | El visitante intentó algo que no puede |
| 409 | `pin_maestro_no_configurado` | No hay versión activa |
| 409 | `alias_duplicado` | RN-34 (trae `sugerencia`) |
| 423 | `pin_maestro_bloqueado` | RN-10 (trae `reintentar_en_seg`) |
| 423 | `dispositivo_en_pausa` | RN-33 (trae `reintentar_en_seg`) |

## C.5 · Eventos y auditoría

Todos al outbox, dentro de la transacción del hecho, con la nomenclatura `identidad.<agregado>.<hecho>.v1`.

| Evento | Cuándo |
|---|---|
| `identidad.pin_maestro.configurado.v1` | Primera versión, en la instalación |
| `identidad.pin_maestro.cambiado.v1` | Cada nueva versión, con `motivo`: `administrador`, `vencimiento` |
| `identidad.pin_maestro.vencido.v1` | La primera vez que se detecta el vencimiento |
| `identidad.pin_maestro.fallido.v1` · `.bloqueado.v1` | Cada fallo y cada bloqueo, con equipo y hora; nunca el PIN intentado |
| `identidad.docente.registrado.v1` | RB-13, con equipo |
| `identidad.docente.contrasena_restablecida.v1` | RB-14, con equipo |
| `identidad.estudiante.registrado.v1` | RB-17 |
| `identidad.estudiante.pin_establecido.v1` | RB-18 |
| `identidad.sesion.visitante_abierta.v1` | RB-19, con tableta y grupo |
| `identidad.usuario.confirmado.v1` | RB-20 |

## C.6 · Integración con el resto del backend

| ID | Requerimiento |
|---|---|
| **RB-40** | **Cerrar Q-34**: el instalador deja `AVACOM_LMS_EXIGIR_SESION=1`. Con ello, expediente, biblioteca, aula, estudio y evaluación exigen pase; el visitante pasa con sus permisos limitados. Hay que revisar cada módulo contra esto (véase §C.7). |
| **RB-41** | El **padrón sin sesión** (`padron.py` actuando como la primera cuenta `ADMIN`) deja de existir con sesión obligatoria. Ya lo previó el propio archivo; verificar que `test_api_padron` lo cubre. |
| **RB-42** | **`/health/`**: `acceso.pin_maestro: configurado | vencido | sin_configurar` (sin fechas). El instalador lo muestra en su resumen final. |
| **RB-43** | Comando **`manage.py acceso_pin_maestro`** (estado y cambio por consola, para el técnico) con `--cambiar` leyendo el nuevo PIN de entrada estándar. Cambia con permiso de consola: queda auditado como `actor = sistema`. |
| **RB-44** | Comando de **emergencia `acceso_restablecer_admin`**: hoy nada permite recuperar la contraseña del administrador (el PIN maestro no la cubre, RN-12). Lo ejecuta el técnico con acceso al equipo y queda auditado (PA-07). |

## C.7 · Efecto en otros módulos

| Módulo | Qué debe revisarse |
|---|---|
| **MOD-007 Classroom Engine** | Participante `VISITANTE` en la lista del aula y en el recuadro de conectados; canal WebSocket exige `?token=` (ya lo soporta) |
| **MOD-008 Modo Estudio** | La pantalla «¿Quién eres?» sin verificación (D-15) **se reemplaza** por el acceso con PIN (RF-24). Esto revisa la decisión D-15 y responde a su pregunta abierta Q-74 |
| **MOD-009 Device Manager** | Consultar `tipo` del dispositivo para RN-11; el visitante respeta la tableta compartida |
| **MOD-010 Evaluation & Delivery** | El visitante no rinde evaluación formal (RN-43). El pase de examen sigue siendo la excepción del profesor |
| **MOD-019 Audit** | Los eventos nuevos de §C.5 y el campo `origen` en las vistas de auditoría |

## C.8 · Pruebas del backend

Mantener las 118 en verde. Suites nuevas o ampliadas (`backend/acceso/tests/`): **`test_pin_maestro`**, **`test_api_docentes`** (registro, restablecimiento, bloqueo por PIN, vencimiento, desde tableta de alumno), **`test_api_estudiantes`** (autoalta, PIN, alias duplicado, PIN pendiente, bloqueo por tableta), **`test_api_visitante`**, y ampliaciones de `test_api_sesiones` y `test_api_padron`. Más una prueba de arquitectura: ni `dominio/` ni `aplicacion/` nombran Django.

---

# PARTE D · Frontend MAUI

OPS es el equipo del aula y **no tiene teclado**: todo lo que se pueda resolver tocando, se resuelve tocando. Student corre en tabletas, algunas compartidas.

## D.1 · Reglas transversales

| ID | Requerimiento |
|---|---|
| **RF-00a** | **Teclado numérico propio** de seis puntos (PIN maestro) y de cuatro a seis (PIN del alumno): `TecladoPinView` en `Avacom.Lms.Ui/Controls`, una sola implementación para OPS y Student. Teclas de **72 pt o más** en Student (Maestro: preescolar 72, primaria 60) y de **150 × 46 px o más** en OPS (regla del nodo táctil). Nada de teclado del sistema para el PIN. |
| **RF-00b** | **Composición** igual a la del acceso de OPS: tarjeta de vidrio, lápiz 3D y panal, con la tarjeta en el tercio central en X y entre 1/6 y 5/6 en Y. Se verifica con captura y cuadrícula de tercios antes de entregar. |
| **RF-00c** | Los mensajes siguen UXR-005 y UXR-009: dicen qué pasó y qué sigue, sin códigos ni la palabra «error» (§5). |
| **RF-00d** | **Ni PIN ni contraseña quedan escritos** después de usarse (lo hace hoy `LoginPage.OnAppearing`): el equipo lo usa mucha gente. Al volver al acceso no queda nada de quien estuvo antes (BR-053). |
| **RF-00e** | Cuando el nodo no responde, las pantallas lo dicen y dejan **reintentar** sin perder lo escrito. Nunca simulan un acceso. |

## D.2 · `Avacom.Lms.Core` (cliente)

| ID | Requerimiento |
|---|---|
| **RF-10** | `AccesoApi` / `IAccesoApi` gana: `EstadoPinMaestroAsync`, `CambiarPinMaestroAsync`, `RegistrarDocenteAsync`, `RestablecerContrasenaDocenteAsync`, `ListarGruposDelAulaAsync`, `ListarEstudiantesDelGrupoAsync`, `RegistrarEstudianteAsync`, `EstablecerPinAlumnoAsync`, `IniciarSesionAlumnoAsync(usuarioId, pin)`, `EntrarComoVisitanteAsync`, `ConfirmarEstudianteAsync`. |
| **RF-11** | Modelos nuevos en `Identidad.cs` o `AccesoApi.cs`: estado del PIN, alumno de la lista (`id`, `alias`, `pin_pendiente`), y `ClaseSesion` en `UsuarioDeSesion`. |
| **RF-12** | `ErrorAula` interpreta los códigos de §C.4.3 (con `reintentar_en_seg`, `intentos_restantes`, `sugerencia`). |
| **RF-13** | Pruebas en `tests/Avacom.Lms.Core.Tests`: serialización de cada llamada y cada código de error con un servidor de mentira. |

## D.3 · AVACOM OPS Master (profesor, administrador, técnico)

| ID | Pantalla | Qué hace |
|---|---|---|
| **RF-01** | **Primer arranque** (nueva, JRN-001) | Se abre sola cuando `configuracion.instalado = false`. Pasos tocables: (1) elegir país e idioma, (2) nombre del aula, (3) crear al administrador, (4) **configurar el PIN maestro** (teclado propio, dos veces, con la regla RN-05 explicada), (5) **hoja de acceso** (RF-03). Si se interrumpe, reanuda en el último paso confirmado. |
| **RF-02** | Texto libre del primer arranque | Documento, nombres y nombre del aula **sí** exigen escribir. Se resuelve con un teclado en pantalla propio o con el del sistema, pero el PIN y la hoja **no** pueden depender de él (regla del nodo sin teclado). Ver PA-08. |
| **RF-03** | **Hoja de acceso** (PAN-204) | Muestra y permite **imprimir** una sola vez la contraseña inicial del administrador **y** el PIN maestro recién creado. Confirmar entrega. **No se puede volver a ver** (RN-04). Si se interrumpe antes de confirmar, la hoja sigue disponible. |
| **RF-04** | Tablero del instalador | El resumen final del instalador deja de decir «falta crear el administrador» y muestra el estado del PIN maestro (RB-42). |
| **RF-05** | **Acceso del docente** (`LoginPage`, cambia) | Además de documento y contraseña, dos acciones siempre visibles: **«Crear mi usuario»** y **«Olvidé mi contraseña»**. «Iniciar como profesor» sin credenciales **sólo** existe con el nodo en modo prototipo (`EXIGIR_SESION=0`). |
| **RF-06** | **Crear mi usuario** (nueva) | Documento · nombres y apellidos · contraseña dos veces · **grupos que dicto** (casillas con los grupos existentes) · **PIN maestro** al final con el teclado propio. Si el PIN falla, conserva lo escrito y muestra los intentos que quedan. Si queda registrado, entra directamente. |
| **RF-07** | **Olvidé mi contraseña** (nueva) | Documento · PIN maestro · contraseña nueva dos veces. Al terminar, cierra todas las sesiones y vuelve al acceso con el aviso. |
| **RF-08** | **Seguridad del aula** (nueva, sólo administrador) | Tarjeta del **PIN maestro**: estado, creado el…, vence el… y días restantes; botón **Cambiar el PIN maestro** (teclado propio, dos veces); aviso de 30 días (RN-08). Lista de **docentes registrados con el PIN** con «Suspender». Interruptores de **autoregistro de alumnos** y **visitantes**. |
| **RF-09** | **Aviso de vencimiento** en el tablero | Banda para administrador y técnico a 30 días o menos; a los demás, nada. Con el PIN vencido, el botón «Crear mi usuario» sigue ahí pero explica qué pasó y qué sigue. |
| **RF-09b** | **Grupos** (`GruposPage`, cambia) | La fila de alumno muestra **«sin confirmar»** y acciones **Confirmar** y **Nuevo PIN** (deja PIN pendiente, sin mostrar número). Se retira la salida de `secreto_inicial`. |
| **RF-09c** | **Monitor de actividad** | Los visitantes aparecen como «Visitante · tableta N» y se pueden **vincular** a un alumno (RN-44). |

## D.4 · AVACOM Student (alumno)

| ID | Pantalla | Qué hace |
|---|---|---|
| **RF-20** | **Acceso del alumno** (`ConnectionPage`, cambia) | Tras conectar con el aula: (1) **elegir grupo** (tarjetas grandes), (2) **tocar su nombre** en la lista, (3) **marcar su PIN** en el teclado propio. Dos acciones siempre visibles: **«No estoy en la lista · soy nuevo»** y **«Entrar como visitante»**. Sin teclado del sistema. |
| **RF-21** | **Soy nuevo** (nueva) | Nombre (teclado del sistema, es lo único que se escribe) · grupo · PIN dos veces. Si el alias ya existe, ofrece la variante con una letra más (RN-34). Al terminar, entra. |
| **RF-22** | **Elegir mi PIN** (nueva) | Cuando el alumno toca su nombre y está en «PIN pendiente»: «Todavía no tienes PIN. Elige uno de 4 números que recuerdes.» |
| **RF-23** | **Entrar como visitante** | Un botón, un toque de confirmación. Entra a la clase en curso del grupo o al menú limitado. Banda amarilla «Entraste como visitante: lo que hagas no se guarda en tu historial» (la misma banda de la sesión temporal, con texto propio). |
| **RF-24** | **Modo Estudio** | La pantalla «¿Quién eres?» sin verificación se **retira**: el modo estudio usa la sesión del acceso. Con la sesión de visitante muestra sólo la práctica y avisa que no se guarda. Revisa D-15 (§C.7). |
| **RF-25** | **Menú del alumno** | Las teselas se atenúan según los permisos de la sesión: el visitante no ve Progreso ni Perfil ni evaluaciones. |
| **RF-26** | **Bloqueo de la tableta** (RN-33) | Con `dispositivo_en_pausa` la pantalla muestra la cuenta regresiva, **deja visible «Entrar como visitante»** y no menciona a ningún compañero. |
| **RF-27** | **Avisos de sesión** | Se conservan los de sesión cerrada en otro dispositivo, inactividad y expirada (§7.1 de 03). Con visitante, la inactividad **cierra y retira** la cuenta efímera. |
| **RF-28** | **Preescolar** | El grupo cuyo nivel tiene política `AVATAR` muestra la cuadrícula de dibujos en lugar del teclado, igual que hoy (TST-074). |

## D.5 · Pruebas del frontend

| ID | Requerimiento |
|---|---|
| **RF-30** | `tests/Avacom.Lms.Student.Uia`: recorrido de acceso (grupo → nombre → PIN), alumno nuevo, PIN pendiente, visitante y tableta en pausa, contra un nodo aislado (puerto 8010). |
| **RF-31** | Un recorrido equivalente para OPS: primer arranque, alta de profesor, restablecimiento, cambio del PIN maestro y vencimiento. |
| **RF-32** | Capturas con la cuadrícula de tercios y a los tamaños de tableta usuales antes de dar la pantalla por buena. |

---

# PARTE E · Decisiones, criterios y orden de trabajo

## §5 · Mensajes

| Situación | Texto |
|---|---|
| PIN maestro equivocado | «Ese PIN no es. Te quedan 3 intentos.» |
| PIN maestro bloqueado | «Demasiados intentos desde este equipo. Vuelve a probar en 15 minutos.» |
| PIN maestro vencido | «El PIN maestro venció. Pídele a administración que lo cambie y vuelve a intentarlo.» |
| Desde una tableta de alumno | «Esto se hace desde el equipo del profesor.» |
| Alias repetido | «Ya hay alguien llamado Juan P. en este grupo. Añade una letra: Juan Pé.» |
| Tableta en pausa | «Esperemos un momento: vuelve a probar en 2 minutos, o entra como visitante.» |
| PIN pendiente | «Todavía no tienes PIN. Elige uno de 4 números que recuerdes.» |
| Visitante | «Entraste como visitante. Lo que hagas no se guardará en tu historial.» |
| Profesor restablecido | «Listo. Cerramos tus sesiones abiertas. Entra con tu nueva contraseña.» |

## §6 · Decisiones que tomé (confirmar o rechazar)

| # | Decisión | Por qué |
|---|---|---|
| **D-A1** | El PIN maestro **vencido** bloquea sólo altas y restablecimientos de profesores; no detiene clases ni sesiones | El Maestro y DEC-018 dicen que una suspensión nunca bloquea al profesor |
| **D-A2** | El bloqueo por intentos de alumnos recae en la **tableta**, no en la cuenta | Evita que un compañero bloquee a otro a propósito, que es el mismo sabotaje que el visitante evita |
| **D-A3** | El PIN es para todos los alumnos por defecto; secundaria puede volver a contraseña por política | El pedido lo dice; el Maestro sólo lo exige hasta primaria |
| **D-A4** | El visitante es una **clase de sesión** (como la temporal), no un sexto rol | Mantiene los cinco roles del Maestro |
| **D-A5** | El PIN maestro es un **secreto de la institución con versiones**, no una escalada ni una credencial de persona | No tiene dueño, no encaja en BR-101 ni en `m01_credencial` |
| **D-A6** | Sin endpoint «verificar PIN» | Sería un oráculo para adivinar combinaciones |
| **D-A7** | Cada visita crea una **cuenta efímera** | La sesión única por persona exige que cada visita sea una persona distinta |
| **D-A8** | La lista de nombres del aula es pública para dispositivos registrados, sólo con alias | Es lo que prescribe PAN-002; el documento y el resto nunca salen |

## §7 · Preguntas abiertas

| # | Pregunta | Mi recomendación |
|---|---|---|
| **PA-01** | «PIN fácilmente reconocible»: ¿significa **fácil de recordar** (lo que asumí) o **reconocible visualmente** (p. ej. dibujos)? | Fácil de recordar, 4 dígitos. Si es lo segundo, el avatar de BR-024 ya lo cubre y basta ampliar a primaria |
| **PA-02** | ¿La cuenta de profesor registrada con PIN queda **activa al instante** o espera la aprobación del administrador? | Al instante, con lista y suspensión (offline: el administrador no siempre está) |
| **PA-03** | ¿Puede un profesor **crear grupos**? Sin ello, un nodo recién instalado no sirve hasta que el administrador cree grupos | Sí, acotado a los que crea (RB-28) |
| **PA-04** | ¿Debe el profesor **ver y admitir** a los visitantes (BR-047 dice «lo admite»), o basta con que los vea? | Que los vea y pueda expulsarlos (BR-048); no que los admita uno a uno |
| **PA-05** | Un alumno que olvidó su PIN **durante un examen**: ¿se mantiene el pase de examen del profesor o se prohíbe del todo? | Se mantiene a discreción del profesor, sin ofrecerlo desde la tableta |
| **PA-06** | Tras vencer, ¿qué ocurre si el administrador no lo cambia? | Nada más que lo de RN-09. Que se pueda seguir enseñando |
| **PA-07** | ¿Hace falta un camino para recuperar al **administrador** que olvidó su contraseña? | Sí: comando de consola para el técnico (RB-44) |
| **PA-08** | ¿OPS necesita su **propio teclado en pantalla** para texto libre, o se acepta el del sistema? | Se acepta el del sistema para texto; el PIN siempre con teclado propio |
| **PA-09** | ¿Los visitantes efímeros se acumulan (≈ 50 alumnos × 180 días)? | Aceptable en SQLite; archivar las de más de un año en la política de retención |

## §8 · Criterios de aceptación

| # | Dado… | Cuando… | Entonces… |
|---|---|---|---|
| **AC-A01** | Un nodo recién instalado | El técnico abre OPS | Se abre el primer arranque y no deja terminar sin un PIN maestro de 6 dígitos válido |
| **AC-A02** | El PIN `123456` | Se intenta configurar | Se rechaza por trivial y se explica |
| **AC-A03** | La hoja de acceso confirmada | Se intenta verla de nuevo | No se puede |
| **AC-A04** | El PIN maestro vigente desde hace 366 días | Un profesor intenta registrarse | Se le dice que venció; las clases y los profesores ya registrados siguen funcionando |
| **AC-A05** | El PIN maestro con 31 días restantes | El administrador abre el tablero | No hay aviso; a 30 días o menos, sí |
| **AC-A06** | 5 fallos seguidos de PIN maestro desde un equipo | Se vuelve a intentar con el PIN correcto | Respuesta de bloqueo hasta pasados 15 minutos, y queda auditado |
| **AC-A07** | Una tableta de alumno | Intenta registrar un profesor, aunque con el PIN correcto | `403 dispositivo_no_autorizado` |
| **AC-A08** | Un profesor con el PIN correcto | Se registra con una contraseña que cumple la política | Entra con su documento y su contraseña, y sólo ve sus grupos |
| **AC-A09** | Un profesor registrado | Olvida su contraseña y la restablece con el PIN | Sus sesiones abiertas se cierran y entra con la nueva |
| **AC-A10** | Una cuenta de administrador | Se intenta restablecer con el PIN maestro | Se rechaza sin revelar nada |
| **AC-A11** | Un alumno nuevo | Crea su usuario con grupo, nombre y PIN `1234` | Entra tocando su nombre y su PIN |
| **AC-A12** | El alias ya existe en el grupo | Se registra otro igual | Se pide una letra más y no se crea el duplicado |
| **AC-A13** | 5 PIN equivocados en una tableta | Otro alumno toca su propio nombre en esa tableta | Espera el plazo, **sin** bloquear su cuenta; en otra tableta entra normal |
| **AC-A14** | Un alumno que olvidó su PIN | Toca «Entrar como visitante» | Entra en dos toques, sin profesor |
| **AC-A15** | Una sesión de visitante | Intenta rendir una evaluación o ver un progreso | `403 sesion_visitante_limitada` |
| **AC-A16** | Un visitante que hizo una actividad en vivo | Termina la clase | Nada queda en el expediente de ningún alumno; el profesor puede vincularla |
| **AC-A17** | El profesor restablece el PIN de un alumno | El alumno vuelve a su tableta | Se le pide elegir un PIN nuevo; el profesor nunca vio un número |
| **AC-A18** | Un alumno creado por padrón sin PIN | Toca su nombre | Elige su PIN y entra |
| **AC-A19** | El visitante cierra sesión o pasan 24 h | Se consulta la cuenta | Está retirada, no borrada |
| **AC-A20** | `autoregistro` apagado | Un alumno intenta crear usuario | `403 registro_cerrado` y el botón ya no aparece |
| **AC-A21** | El nodo con sesión obligatoria | Se pide cualquier ruta sin pase | `401`; el visitante pasa con sus permisos limitados |
| **AC-A22** | Cualquier equipo | Se mira la base de datos y los registros | No aparece ningún PIN en claro, ni intentado ni vigente |
| **AC-A23** | Las pruebas existentes | Se ejecutan | Siguen en verde |

## §9 · Orden de trabajo sugerido (una semana)

| Día | Backend | Frontend |
|---|---|---|
| **Lun** | RB-01…08 (modelo y migración 0010), RB-30…34 (dominio del PIN), RB-10…12 y RB-21 (PIN maestro e instalación) | `TecladoPinView` (RF-00a) |
| **Mar** | RB-13…15 (docentes), RB-28, RB-42…44, `test_pin_maestro` y `test_api_docentes` | `Core` (RF-10…13) · RF-01…04 (primer arranque y hoja) |
| **Mié** | RB-16…20, RB-22…27 (alumnos, visitante, padrón), `test_api_estudiantes` y `test_api_visitante` | RF-05…09c (OPS: acceso del docente, seguridad del aula, grupos) |
| **Jue** | RB-40…41 (sesión obligatoria) y revisión de MOD-007/008/009/010 | RF-20…28 (Student) |
| **Vie** | Revisión cruzada; actualizar 01, 02, 03 y 04; regenerar el visor | RF-30…32 (pruebas de interfaz, capturas, tercios); recorrido completo con el AC-A01…A23 |

**Qué se puede recortar si falta tiempo:** RF-09c (vincular visitante en el monitor), PA-09 (archivado), RB-44 (comando de emergencia). **Qué no:** RN-04, RN-07, RN-10, RN-11, RN-33 y RB-40; sin ellas el PIN maestro no protege nada o el visitante no resuelve el sabotaje.

## §10 · Trazabilidad

| Necesidad del negocio | Reglas | Backend | Frontend | Criterios |
|---|---|---|---|---|
| PIN maestro de 6 dígitos, configurado al instalar | RN-01…05 | RB-01, 10, 21, 30 | RF-01, 03 | AC-A01…A03 |
| Cambio libre y cambio anual obligatorio | RN-06…09 | RB-11, 12, 33, 43 | RF-08, 09 | AC-A04, A05 |
| Protección contra adivinación | RN-10…12 | RB-02, 32, 34 | — | AC-A06, A07, A22 |
| Profesores crean su usuario | RN-20…23 | RB-13, 15, 28 | RF-05, 06 | AC-A08 |
| Profesores restablecen su contraseña | RN-24, 25 | RB-14 | RF-07 | AC-A09, A10 |
| Alumnos crean su usuario y PIN | RN-30…37 | RB-16…18, 22, 26 | RF-20…22, 28 | AC-A11…A13, A17, A18, A20 |
| Visitante contra el sabotaje | RN-40…47 | RB-07, 19, 25 | RF-23…27 | AC-A14…A16, A19 |
| Todo funciona sin internet | Condición inicial | RB-40, 41 | RF-00e | AC-A21 |
