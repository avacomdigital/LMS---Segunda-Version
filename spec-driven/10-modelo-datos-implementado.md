# 10 · Modelo de datos implementado

> Estado a 2026-10-06. Se **genera**, no se redacta a mano: se migra una base SQLite temporal con las migraciones del backend, se leen los modelos de Django (`models.py` de las siete apps) y lo que el motor guardó de verdad (restricciones `CHECK`, índices únicos parciales, triggers). Los comentarios de cada campo en `models.py` pasan a ser su descripción. Nunca se toca `backend/db.sqlite3`.

Este documento reúne en un solo lugar lo que cada módulo describe por separado ([01-acceso](01-acceso/01-modelado-datos.md), [02-classroom-engine](02-classroom-engine/01-modelo-de-datos.md), [03-device-manager](03-device-manager/00-modelo-y-api.md), [04-modo-estudio](04-modo-estudio/02-modelo-y-api.md), [05-audit-logs](05-audit-logs/modelado_datos.md), [06-evaluation-delivery](06-evaluation-delivery/modelado-datos.md)): qué tablas hay, qué atributos tienen, cómo se relacionan (1:N, 0..1:N, 1:1, N:M) y qué cambió frente al diseño v2 acordado con el CTO. El visor interactivo (`specs/analisis/index.html`, privado) dibuja exactamente estos datos con la PK y la FK escritas en cada fila.

## 1. Resumen

**53 tablas** en 7 módulos, **690 columnas**, **58 FK físicas** (las impone el motor) y **36 FK lógicas** entre módulos (se guarda la llave, la valida el puerto del módulo dueño), más **9 referencias `curso_ref`** a AVACOM Biblioteca (no son tablas del LMS) y **9 tablas puente** que resuelven relaciones N:M.

| Módulo | App | Tablas | Columnas | FK físicas | FK lógicas | Qué posee |
|---|---|---:|---:|---:|---:|---|
| MOD-001 · Acceso e identidad | `acceso` | 18 | 171 | 34 | 0 | Quién entra: organización, políticas de credencial, roles y permisos con alcance, cuentas, identificadores y credenciales cifrados, sesiones, autorizaciones temporales para examen, intentos de acceso, grupos y su padrón. |
| MOD-009 · Gestión de dispositivos | `device_manager` | 3 | 33 | 2 | 2 | Inventario de equipos del aula (bloqueo, latido, perfil compartida/asignada, capacidad de control declarada) y la sesión de alumno en cada equipo. |
| MOD-007 · Aula (Classroom Engine) | `classroom_engine` | 11 | 149 | 12 | 10 | La clase en vivo: sesión, participantes y su presencia, selector, controles, lanzamientos («distribuciones») con su avance de entrega, intentos en clase, avisos y resumen de cierre. |
| MOD-008 · Modo de estudio | `modo_estudio` | 6 | 103 | 3 | 10 | Lecciones asignadas para estudiar fuera de clase: asignación, tarea por alumno, paquete descargable, práctica autocalificable y libro de sincronización de la cola de la tableta. |
| MOD-010 · Evaluación y entrega | `evaluacion` | 5 | 118 | 3 | 9 | Evaluación formal: asignación con plazo y nivel de control, admisión de tabletas, intento con reloj y pausas, e incidentes. |
| MOD-005 · Expediente del estudiante | `expediente` | 7 | 72 | 2 | 4 | Lo único que el LMS posee del curso (artículos 13 y 14): inscripción, progreso por lección, apertura de material, intento de evaluación del expediente y memoria de disponibilidad. |
| MOD-019 · Auditoría y logs | `audit` | 3 | 44 | 2 | 1 | Bitácora encadenada e inmutable, con tramos verificables, y cola de salida de los eventos `auditoria.*`. |

Tipos de tabla: **ENTIDAD** (agregado), **REL** (asociativa: lleva dos o más FK y resuelve un N:M), **DIM** (dimensión de sesión), **REGISTRO** (sólo inserción), **COLA** (outbox transaccional, una por módulo hasta que exista MOD-015).

## 2. Cómo leer las relaciones

La cardinalidad se escribe **padres por fila hija : hijas por padre**. «Padre» es la tabla cuya PK se referencia; «hija», la que guarda la FK.

| Notación | Cuándo | Ejemplo real |
|---|---|---|
| `1 : N` | FK `NOT NULL`: cada hija tiene exactamente un padre y un padre puede tener muchas hijas. | `m01_autorizacion_temporal.usuario_id` → `m01_usuario.id` |
| `0..1 : N` | FK que admite `NULL`: la hija pertenece a un padre o a ninguno. | `m01_autorizacion_temporal.dispositivo_id` → `m09_dispositivo.id` |
| `1 : 1` | La FK es también la PK, o lleva `UNIQUE`: extensión o especialización de la tabla padre. | `m01_persona.usuario_id` → `m01_usuario.id` |
| `FK lógica` | La columna guarda la llave de otra tabla, pero el motor no la impone: cada módulo es dueño de sus tablas (escritor único, CV-08). La cardinalidad se lee igual. | `m09_dim_sesion_alumno.alumno_id` → `m01_usuario.id` |
| `N : M` | Se resuelve con una tabla puente que lleva una FK a cada lado; cada pareja es una fila. | `m01_miembro_grupo` resuelve `m01_usuario` ↔ `m01_grupo` |

**ON DELETE** (sólo en FK físicas): `CASCADE` (la hija muere con el padre), `PROTECT`/`RESTRICT` (impiden borrar al padre mientras existan hijas; es lo que impone «nada se borra», CV-05), `SET NULL` (la hija queda sin padre).

### 2.1 Relaciones N : M y su tabla puente

| Tabla puente | Tipo | Lado A | Cardinalidad | Lado B | Qué guarda además |
|---|---|---|:---:|---|---|
| `m01_miembro_grupo` | REL | `m01_usuario` | N : M | `m01_grupo` | `papel` (ESTUDIANTE/DOCENTE) y vigencia |
| `m01_rol_permiso` | REL | `m01_rol` | N : M | `m01_permiso` | `alcance` del permiso en ese rol |
| `m01_usuario_permiso` | REL | `m01_usuario` | N : M | `m01_permiso` | `alcance`, motivo, vigencia y quién lo otorgó |
| `m01_usuario_rol` | REL | `m01_usuario` | N : M | `m01_rol` | alcance (`ORGANIZATION`/`LEVEL`/`ASSIGNED_GROUPS`) y vigencia |
| `m09_dim_sesion_alumno` | DIM | `m01_usuario` | N : M | `m09_dispositivo` | periodo y motivo de cierre (INV-011, DEC-023) |
| `m07_distribucion_entrega` | REL | `m07_distribucion` | N : M | `m07_participante` | estado de entrega e intentos |
| `m07_participante` | REL | `m07_sesion` | N : M | `m01_usuario` | presencia técnica, admisión nominal, ayuda, proyección |
| `m08_tarea` | REL | `m08_asignacion` | N : M | `m01_usuario` | estado, avance y resumen de prácticas |
| `m05_inscripcion` | REL | `m01_usuario` | N : M | `biblioteca_curso` | fecha de inscripción y de retiro |

Las parejas de `m07_participante`, `m09_dim_sesion_alumno`, `m08_tarea` y `m05_inscripcion` cruzan módulos: sus dos lados son **FK lógicas**, así que el N:M existe en el modelo pero el motor sólo impone la unicidad de la pareja (`ux_*`).

## 3. Del diseño v2 a lo implementado

| Tabla del diseño v2 | Cómo quedó en el backend |
|---|---|
| `rol` | `m01_rol` |
| `usuario` | `m01_persona`, `m01_usuario` |
| `modulo_app` | `m01_permiso` |
| `permiso` | `m01_rol_permiso` |
| `bitacora` | `m19_bitacora` |
| `profesor` | Sin tabla propia: el rol está en `m01_usuario.rol_id` y `m01_usuario_rol`; el profesor de un grupo, en `m01_miembro_grupo.papel = DOCENTE`. |
| `alumno` | Sin tabla propia: `m01_usuario` + `m01_miembro_grupo.papel = ESTUDIANTE`; los datos personales van cifrados en `m01_persona`. |
| `dispositivo` | `m09_dispositivo` |
| `dim_sesion_profesor` | Sin equivalente directo. |
| `dim_sesion_alumno` | `m09_dim_sesion_alumno` |
| `grupo` | `m01_grupo` |
| `materia` | Sin tabla todavía. |
| `clase` | `m07_sesion` |
| `rel_alumno_grupo` | `m01_miembro_grupo` |
| `rel_grupo_materia` | Sin tabla todavía. |
| `configuracion` | `m05_inscripcion` |
| `rel_sesion_alumno_clase` | `m07_participante` |
| `selector` | `m07_selector` |
| `pais_nivel_grado_materia_tema` | No hay tabla: el catálogo vive en AVACOM Biblioteca (artículo 14); el LMS sólo guarda referencias `*_ref`. |
| `curso` | No hay tabla: `curso_ref` + `curso_version` + `curso_rotulo` en las tablas que lo usan. |
| `leccion` | No hay tabla: `leccion_ref` / `leccion_codigo` + rótulo. |
| `objeto` | No hay tabla: `objeto_ref` + `objeto_tipo` + rótulo. |
| `lanzamiento` | `m07_distribucion`, `m10_asignacion` |
| `intento` | `m07_intento`, `m10_intento_formal` |
| `evento` | Sin tabla única: cada módulo escribe su cola `m*_evento_salida` y los hechos auditables van a `m19_bitacora`; se unificarán en `m15_evento` cuando exista MOD-015. |
| `progreso` | `m05_progreso_leccion` |
| `ponderacion` | Sin tabla todavía. |
| `calificacion` | Sin tabla todavía. |
| `evaluacion` | Sin tabla con ese nombre: la asignación y el intento formal viven en `m10_asignacion` y `m10_intento_formal`. |

**34 tablas implementadas no existen en el diseño v2** (módulos y tablas agregados): `m01_autorizacion_temporal`, `m01_credencial`, `m01_evento_salida`, `m01_identificador_usuario`, `m01_intento_acceso`, `m01_organizacion`, `m01_pin_maestro`, `m01_politica_credencial`, `m01_sesion`, `m01_usuario_permiso`, `m01_usuario_rol`, `m09_evento_salida`, `m07_aviso`, `m07_control`, `m07_distribucion_entrega`, `m07_evento_salida`, `m07_presencia`, `m07_resumen`, `m08_asignacion`, `m08_evento_salida`, `m08_paquete`, `m08_practica`, `m08_sincronizacion`, `m08_tarea`, `m10_admision`, `m10_evento_salida`, `m10_incidente`, `m05_apertura_material`, `m05_disponibilidad_observada`, `m10_intento`, `m10_intento_pregunta`, `m10_intento_respuesta`, `m19_bitacora_tramo`, `m19_evento_salida`.

## 4. Todas las relaciones

103 relaciones, agrupadas por el módulo de la tabla hija. «Obligatoria» = la FK no admite `NULL`/vacío.

### 4.1 MOD-001 · Acceso e identidad

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m01_autorizacion_temporal.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_autorizacion_temporal` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_autorizacion_temporal`. |
| `m01_autorizacion_temporal.otorgada_por_id` | `m01_usuario.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_autorizacion_temporal` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_autorizacion_temporal`. |
| `m01_autorizacion_temporal.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_autorizacion_temporal` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m01_autorizacion_temporal`. |
| `m01_autorizacion_temporal.sesion_id` | `m01_sesion.id` | `0..1 : 1` | no | FK física | SET NULL | cada fila de `m01_autorizacion_temporal` apunta a una fila de `m01_sesion` o a ninguna, y cada fila de `m01_sesion` tiene como máximo una de `m01_autorizacion_temporal`. |
| `m01_credencial.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_credencial` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_credencial`. |
| `m01_credencial.creado_por_id` | `m01_usuario.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_credencial` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m01_credencial`. |
| `m01_grupo.organizacion_id` | `m01_organizacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_grupo` apunta a una fila de `m01_organizacion`, y una fila de `m01_organizacion` puede tener muchas de `m01_grupo`. |
| `m01_grupo.politica_credencial_id` | `m01_politica_credencial.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_grupo` apunta a una fila de `m01_politica_credencial` o a ninguna, y una fila de `m01_politica_credencial` puede tener muchas de `m01_grupo`. |
| `m01_identificador_usuario.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_identificador_usuario` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_identificador_usuario`. |
| `m01_intento_acceso.usuario_id` | `m01_usuario.id` | `0..1 : N` | no | FK física | CASCADE | cada fila de `m01_intento_acceso` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m01_intento_acceso`. |
| `m01_intento_acceso.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_intento_acceso` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m01_intento_acceso`. |
| `m01_intento_acceso.autorizacion_id` | `m01_autorizacion_temporal.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_intento_acceso` apunta a una fila de `m01_autorizacion_temporal` o a ninguna, y una fila de `m01_autorizacion_temporal` puede tener muchas de `m01_intento_acceso`. |
| `m01_miembro_grupo.grupo_id` | `m01_grupo.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_miembro_grupo` apunta a una fila de `m01_grupo`, y una fila de `m01_grupo` puede tener muchas de `m01_miembro_grupo`. |
| `m01_miembro_grupo.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_miembro_grupo` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_miembro_grupo`. |
| `m01_persona.usuario_id` | `m01_usuario.id` | `1 : 1` | sí | PK = FK | CASCADE | cada fila de `m01_persona` apunta a una fila de `m01_usuario`, y cada fila de `m01_usuario` tiene como máximo una de `m01_persona`. |
| `m01_pin_maestro.organizacion_id` | `m01_organizacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_pin_maestro` apunta a una fila de `m01_organizacion`, y una fila de `m01_organizacion` puede tener muchas de `m01_pin_maestro`. |
| `m01_pin_maestro.creado_por_id` | `m01_usuario.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_pin_maestro` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m01_pin_maestro`. |
| `m01_politica_credencial.organizacion_id` | `m01_organizacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_politica_credencial` apunta a una fila de `m01_organizacion`, y una fila de `m01_organizacion` puede tener muchas de `m01_politica_credencial`. |
| `m01_rol.organizacion_id` | `m01_organizacion.id` | `0..1 : N` | no | FK física | CASCADE | cada fila de `m01_rol` apunta a una fila de `m01_organizacion` o a ninguna, y una fila de `m01_organizacion` puede tener muchas de `m01_rol`. |
| `m01_rol_permiso.rol_id` | `m01_rol.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_rol_permiso` apunta a una fila de `m01_rol`, y una fila de `m01_rol` puede tener muchas de `m01_rol_permiso`. |
| `m01_rol_permiso.permiso_codigo` | `m01_permiso.codigo` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_rol_permiso` apunta a una fila de `m01_permiso`, y una fila de `m01_permiso` puede tener muchas de `m01_rol_permiso`. |
| `m01_sesion.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_sesion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_sesion`. |
| `m01_sesion.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_sesion` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m01_sesion`. |
| `m01_sesion.rol_id` | `m01_rol.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_sesion` apunta a una fila de `m01_rol` o a ninguna, y una fila de `m01_rol` puede tener muchas de `m01_sesion`. |
| `m01_usuario.organizacion_id` | `m01_organizacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_usuario` apunta a una fila de `m01_organizacion`, y una fila de `m01_organizacion` puede tener muchas de `m01_usuario`. |
| `m01_usuario.rol_id` | `m01_rol.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_usuario` apunta a una fila de `m01_rol`, y una fila de `m01_rol` puede tener muchas de `m01_usuario`. |
| `m01_usuario.creado_por_id` | `m01_usuario.id` | `0..1 : N` | no | FK física · self | SET NULL | cada fila de `m01_usuario` apunta a una fila de la misma tabla o a ninguna, y una fila de la misma tabla puede tener muchas de `m01_usuario`. |
| `m01_usuario.vinculado_a_id` | `m01_usuario.id` | `0..1 : N` | no | FK física · self | SET NULL | cada fila de `m01_usuario` apunta a una fila de la misma tabla o a ninguna, y una fila de la misma tabla puede tener muchas de `m01_usuario`. |
| `m01_usuario_permiso.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_usuario_permiso` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_usuario_permiso`. |
| `m01_usuario_permiso.permiso_codigo` | `m01_permiso.codigo` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_usuario_permiso` apunta a una fila de `m01_permiso`, y una fila de `m01_permiso` puede tener muchas de `m01_usuario_permiso`. |
| `m01_usuario_permiso.otorgado_por_id` | `m01_usuario.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_usuario_permiso` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_usuario_permiso`. |
| `m01_usuario_rol.usuario_id` | `m01_usuario.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m01_usuario_rol` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m01_usuario_rol`. |
| `m01_usuario_rol.rol_id` | `m01_rol.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m01_usuario_rol` apunta a una fila de `m01_rol`, y una fila de `m01_rol` puede tener muchas de `m01_usuario_rol`. |
| `m01_usuario_rol.asignado_por_id` | `m01_usuario.id` | `0..1 : N` | no | FK física | SET NULL | cada fila de `m01_usuario_rol` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m01_usuario_rol`. |

### 4.2 MOD-009 · Gestión de dispositivos

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m09_dim_sesion_alumno.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m09_dim_sesion_alumno` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m09_dim_sesion_alumno`. |
| `m09_dim_sesion_alumno.dispositivo_id` | `m09_dispositivo.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m09_dim_sesion_alumno` apunta a una fila de `m09_dispositivo`, y una fila de `m09_dispositivo` puede tener muchas de `m09_dim_sesion_alumno`. |
| `m09_dispositivo.organizacion_id` | `m01_organizacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m09_dispositivo` apunta a una fila de `m01_organizacion`, y una fila de `m01_organizacion` puede tener muchas de `m09_dispositivo`. |
| `m09_dispositivo.asignado_a_id` | `m01_usuario.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m09_dispositivo` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m09_dispositivo`. |

### 4.3 MOD-007 · Aula (Classroom Engine)

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m07_aviso.sesion_id` | `m07_sesion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_aviso` apunta a una fila de `m07_sesion`, y una fila de `m07_sesion` puede tener muchas de `m07_aviso`. |
| `m07_aviso.participante_id` | `m07_participante.id` | `0..1 : N` | no | FK física | CASCADE | cada fila de `m07_aviso` apunta a una fila de `m07_participante` o a ninguna, y una fila de `m07_participante` puede tener muchas de `m07_aviso`. |
| `m07_control.sesion_id` | `m07_sesion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_control` apunta a una fila de `m07_sesion`, y una fila de `m07_sesion` puede tener muchas de `m07_control`. |
| `m07_distribucion.sesion_id` | `m07_sesion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_distribucion` apunta a una fila de `m07_sesion`, y una fila de `m07_sesion` puede tener muchas de `m07_distribucion`. |
| `m07_distribucion.curso_ref` | `biblioteca_curso.curso_ref` | `0..1 : N` | no | ref. Biblioteca | — | cada fila de `m07_distribucion` apunta a una fila de `biblioteca_curso` o a ninguna, y una fila de `biblioteca_curso` puede tener muchas de `m07_distribucion`. |
| `m07_distribucion.asignacion_ref` | `m10_asignacion.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_distribucion` apunta a una fila de `m10_asignacion` o a ninguna, y una fila de `m10_asignacion` puede tener muchas de `m07_distribucion`. |
| `m07_distribucion_entrega.distribucion_id` | `m07_distribucion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_distribucion_entrega` apunta a una fila de `m07_distribucion`, y una fila de `m07_distribucion` puede tener muchas de `m07_distribucion_entrega`. |
| `m07_distribucion_entrega.participante_id` | `m07_participante.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_distribucion_entrega` apunta a una fila de `m07_participante`, y una fila de `m07_participante` puede tener muchas de `m07_distribucion_entrega`. |
| `m07_intento.distribucion_id` | `m07_distribucion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_intento` apunta a una fila de `m07_distribucion`, y una fila de `m07_distribucion` puede tener muchas de `m07_intento`. |
| `m07_intento.participante_id` | `m07_participante.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_intento` apunta a una fila de `m07_participante`, y una fila de `m07_participante` puede tener muchas de `m07_intento`. |
| `m07_intento.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m07_intento` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m07_intento`. |
| `m07_intento.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_intento` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m07_intento`. |
| `m07_participante.sesion_id` | `m07_sesion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_participante` apunta a una fila de `m07_sesion`, y una fila de `m07_sesion` puede tener muchas de `m07_participante`. |
| `m07_participante.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m07_participante` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m07_participante`. |
| `m07_participante.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_participante` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m07_participante`. |
| `m07_participante.dim_sesion_alumno_id` | `m09_dim_sesion_alumno.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_participante` apunta a una fila de `m09_dim_sesion_alumno` o a ninguna, y una fila de `m09_dim_sesion_alumno` puede tener muchas de `m07_participante`. |
| `m07_participante.sesion_usuario_id` | `m01_sesion.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_participante` apunta a una fila de `m01_sesion` o a ninguna, y una fila de `m01_sesion` puede tener muchas de `m07_participante`. |
| `m07_presencia.participante_id` | `m07_participante.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_presencia` apunta a una fila de `m07_participante`, y una fila de `m07_participante` puede tener muchas de `m07_presencia`. |
| `m07_resumen.sesion_id` | `m07_sesion.id` | `1 : 1` | sí | PK = FK | CASCADE | cada fila de `m07_resumen` apunta a una fila de `m07_sesion`, y cada fila de `m07_sesion` tiene como máximo una de `m07_resumen`. |
| `m07_selector.sesion_id` | `m07_sesion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m07_selector` apunta a una fila de `m07_sesion`, y una fila de `m07_sesion` puede tener muchas de `m07_selector`. |
| `m07_selector.curso_ref` | `biblioteca_curso.curso_ref` | `0..1 : N` | no | ref. Biblioteca | — | cada fila de `m07_selector` apunta a una fila de `biblioteca_curso` o a ninguna, y una fila de `biblioteca_curso` puede tener muchas de `m07_selector`. |
| `m07_sesion.grupo_id` | `m01_grupo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m07_sesion` apunta a una fila de `m01_grupo` o a ninguna, y una fila de `m01_grupo` puede tener muchas de `m07_sesion`. |
| `m07_sesion.profesor_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m07_sesion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m07_sesion`. |
| `m07_sesion.relevo_de_sesion_id` | `m07_sesion.id` | `0..1 : N` | no | FK lógica · self | — | cada fila de `m07_sesion` apunta a una fila de la misma tabla o a ninguna, y una fila de la misma tabla puede tener muchas de `m07_sesion`. |
| `m07_sesion.curso_ref` | `biblioteca_curso.curso_ref` | `0..1 : N` | no | ref. Biblioteca | — | cada fila de `m07_sesion` apunta a una fila de `biblioteca_curso` o a ninguna, y una fila de `biblioteca_curso` puede tener muchas de `m07_sesion`. |

### 4.4 MOD-008 · Modo de estudio

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m08_asignacion.grupo_id` | `m01_grupo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m08_asignacion` apunta a una fila de `m01_grupo` o a ninguna, y una fila de `m01_grupo` puede tener muchas de `m08_asignacion`. |
| `m08_asignacion.profesor_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_asignacion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m08_asignacion`. |
| `m08_asignacion.curso_ref` | `biblioteca_curso.curso_ref` | `1 : N` | sí | ref. Biblioteca | — | cada fila de `m08_asignacion` apunta a una fila de `biblioteca_curso`, y una fila de `biblioteca_curso` puede tener muchas de `m08_asignacion`. |
| `m08_paquete.asignacion_id` | `m08_asignacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m08_paquete` apunta a una fila de `m08_asignacion`, y una fila de `m08_asignacion` puede tener muchas de `m08_paquete`. |
| `m08_paquete.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_paquete` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m08_paquete`. |
| `m08_paquete.dispositivo_id` | `m09_dispositivo.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_paquete` apunta a una fila de `m09_dispositivo`, y una fila de `m09_dispositivo` puede tener muchas de `m08_paquete`. |
| `m08_practica.tarea_id` | `m08_tarea.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m08_practica` apunta a una fila de `m08_tarea`, y una fila de `m08_tarea` puede tener muchas de `m08_practica`. |
| `m08_practica.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_practica` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m08_practica`. |
| `m08_practica.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m08_practica` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m08_practica`. |
| `m08_sincronizacion.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_sincronizacion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m08_sincronizacion`. |
| `m08_sincronizacion.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m08_sincronizacion` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m08_sincronizacion`. |
| `m08_sincronizacion.asignacion_id` | `m08_asignacion.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m08_sincronizacion` apunta a una fila de `m08_asignacion` o a ninguna, y una fila de `m08_asignacion` puede tener muchas de `m08_sincronizacion`. |
| `m08_tarea.asignacion_id` | `m08_asignacion.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m08_tarea` apunta a una fila de `m08_asignacion`, y una fila de `m08_asignacion` puede tener muchas de `m08_tarea`. |
| `m08_tarea.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m08_tarea` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m08_tarea`. |

### 4.5 MOD-010 · Evaluación y entrega

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m10_admision.asignacion_id` | `m10_asignacion.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m10_admision` apunta a una fila de `m10_asignacion`, y una fila de `m10_asignacion` puede tener muchas de `m10_admision`. |
| `m10_admision.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m10_admision` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m10_admision`. |
| `m10_admision.dispositivo_id` | `m09_dispositivo.id` | `1 : N` | sí | FK lógica | — | cada fila de `m10_admision` apunta a una fila de `m09_dispositivo`, y una fila de `m09_dispositivo` puede tener muchas de `m10_admision`. |
| `m10_asignacion.sesion_id` | `m07_sesion.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m10_asignacion` apunta a una fila de `m07_sesion` o a ninguna, y una fila de `m07_sesion` puede tener muchas de `m10_asignacion`. |
| `m10_asignacion.grupo_id` | `m01_grupo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m10_asignacion` apunta a una fila de `m01_grupo` o a ninguna, y una fila de `m01_grupo` puede tener muchas de `m10_asignacion`. |
| `m10_asignacion.profesor_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m10_asignacion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m10_asignacion`. |
| `m10_asignacion.curso_ref` | `biblioteca_curso.curso_ref` | `1 : N` | sí | ref. Biblioteca | — | cada fila de `m10_asignacion` apunta a una fila de `biblioteca_curso`, y una fila de `biblioteca_curso` puede tener muchas de `m10_asignacion`. |
| `m10_incidente.intento_id` | `m10_intento_formal.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m10_incidente` apunta a una fila de `m10_intento_formal`, y una fila de `m10_intento_formal` puede tener muchas de `m10_incidente`. |
| `m10_incidente.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m10_incidente` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m10_incidente`. |
| `m10_intento_formal.asignacion_id` | `m10_asignacion.id` | `1 : N` | sí | FK física | PROTECT | cada fila de `m10_intento_formal` apunta a una fila de `m10_asignacion`, y una fila de `m10_asignacion` puede tener muchas de `m10_intento_formal`. |
| `m10_intento_formal.alumno_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m10_intento_formal` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m10_intento_formal`. |
| `m10_intento_formal.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m10_intento_formal` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m10_intento_formal`. |
| `m10_intento_formal.sesion_ref` | `m07_sesion.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m10_intento_formal` apunta a una fila de `m07_sesion` o a ninguna, y una fila de `m07_sesion` puede tener muchas de `m10_intento_formal`. |

### 4.6 MOD-005 · Expediente del estudiante

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m05_apertura_material.curso_ref` | `biblioteca_curso.curso_ref` | `1 : N` | sí | ref. Biblioteca | — | cada fila de `m05_apertura_material` apunta a una fila de `biblioteca_curso`, y una fila de `biblioteca_curso` puede tener muchas de `m05_apertura_material`. |
| `m05_apertura_material.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m05_apertura_material` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m05_apertura_material`. |
| `m05_inscripcion.curso_ref` | `biblioteca_curso.curso_ref` | `1 : N` | sí | ref. Biblioteca | — | cada fila de `m05_inscripcion` apunta a una fila de `biblioteca_curso`, y una fila de `biblioteca_curso` puede tener muchas de `m05_inscripcion`. |
| `m05_inscripcion.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m05_inscripcion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m05_inscripcion`. |
| `m05_progreso_leccion.curso_ref` | `biblioteca_curso.curso_ref` | `1 : N` | sí | ref. Biblioteca | — | cada fila de `m05_progreso_leccion` apunta a una fila de `biblioteca_curso`, y una fila de `biblioteca_curso` puede tener muchas de `m05_progreso_leccion`. |
| `m05_progreso_leccion.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m05_progreso_leccion` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m05_progreso_leccion`. |
| `m10_intento.curso_ref` | `biblioteca_curso.curso_ref` | `0..1 : N` | no | ref. Biblioteca | — | cada fila de `m10_intento` apunta a una fila de `biblioteca_curso` o a ninguna, y una fila de `biblioteca_curso` puede tener muchas de `m10_intento`. |
| `m10_intento.persona_id` | `m01_usuario.id` | `1 : N` | sí | FK lógica | — | cada fila de `m10_intento` apunta a una fila de `m01_usuario`, y una fila de `m01_usuario` puede tener muchas de `m10_intento`. |
| `m10_intento_pregunta.intento_id` | `m10_intento.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m10_intento_pregunta` apunta a una fila de `m10_intento`, y una fila de `m10_intento` puede tener muchas de `m10_intento_pregunta`. |
| `m10_intento_respuesta.intento_id` | `m10_intento.id` | `1 : N` | sí | FK física | CASCADE | cada fila de `m10_intento_respuesta` apunta a una fila de `m10_intento`, y una fila de `m10_intento` puede tener muchas de `m10_intento_respuesta`. |

### 4.7 MOD-019 · Auditoría y logs

| Hija · FK | Padre · PK | Cardinalidad | Obligatoria | Tipo | ON DELETE | Lectura |
|---|---|:---:|:---:|---|---|---|
| `m19_bitacora.usuario_id` | `m01_usuario.id` | `0..1 : N` | no | FK lógica | — | cada fila de `m19_bitacora` apunta a una fila de `m01_usuario` o a ninguna, y una fila de `m01_usuario` puede tener muchas de `m19_bitacora`. |
| `m19_bitacora.dispositivo_id` | `m09_dispositivo.id` | `0..1 : N` | no | FK física | RESTRICT | cada fila de `m19_bitacora` apunta a una fila de `m09_dispositivo` o a ninguna, y una fila de `m09_dispositivo` puede tener muchas de `m19_bitacora`. |
| `m19_bitacora.tramo_id` | `m19_bitacora_tramo.id` | `1 : N` | sí | FK física | RESTRICT | cada fila de `m19_bitacora` apunta a una fila de `m19_bitacora_tramo`, y una fila de `m19_bitacora_tramo` puede tener muchas de `m19_bitacora`. |

## 5. Diccionario de atributos

Tipos: `VARCHAR(36)` = identificador de texto (CV-02); `BIGINT` en columnas de instante = milisegundos desde 1970 del reloj del nodo (CV-03); `JSON` = lista u objeto serializado (por ejemplo `respuestas` dentro del intento). «Null» = admite `NULL`.

### MOD-001 · Acceso e identidad

#### `m01_autorizacion_temporal`  ·  ENTIDAD

AutorizacionTemporal(id, usuario, otorgada_por, tipo, dispositivo, secreto_hash, evaluacion_ref, creada_en, expira_en, usada_en, revocada_en, sesion, motivo)

Clase `AutorizacionTemporal` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `otorgada_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `tipo` |  | VARCHAR(16) | no |  | DISPOSITIVO / CODIGO |
| `dispositivo_id` | **FK** → `m09_dispositivo.id` | VARCHAR(36) | sí |  | Llave foránea física → m09_dispositivo. |
| `secreto_hash` |  | VARCHAR(255) | no |  |  |
| `evaluacion_ref` | REF Biblioteca | VARCHAR(200) | sí |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `creada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `expira_en` |  | BIGINT | no |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `usada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `revocada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `sesion_id` | **FK** → `m01_sesion.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_sesion. |
| `motivo` |  | VARCHAR(200) | no | '' |  |

Restricciones del motor:

- `ck_m01_autorizacion_dispositivo: (NOT (tipo = 'DISPOSITIVO') OR dispositivo_id IS NOT NULL)`
- `ck_m01_autorizacion_uso_con_sesion: (usada_en IS NULL OR sesion_id IS NOT NULL)`

- Índices: (dispositivo_id)  [m01_autorizacion_temporal_dispositivo_id_79269106] · (otorgada_por_id)  [m01_autorizacion_temporal_otorgada_por_id_a0a17321] · (usuario_id)  [m01_autorizacion_temporal_usuario_id_f81fdde9] · (usuario_id, expira_en)  [m01_autoriz_usuario_1e29b4_idx]

#### `m01_credencial`  ·  ENTIDAD

Credencial(id, usuario, tipo, hash, activa, debe_cambiar, creado_en, expira_en, sustituida_en, creado_por)

Clase `Credencial` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `tipo` |  | VARCHAR(16) | no |  |  |
| `hash` |  | VARCHAR(255) | no |  | Argon2id codificado (parámetros + sal + hash) |
| `activa` |  | BOOLEAN | no | true |  |
| `debe_cambiar` |  | BOOLEAN | no | false |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `expira_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `sustituida_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_usuario. |

Restricciones del motor:

- `ck_m01_credencial_sustitucion: (activa OR sustituida_en IS NOT NULL)`
- `UNIQUE (usuario_id) WHERE activa  [uq_m01_credencial_activa]`

- Índices: (creado_por_id)  [m01_credencial_creado_por_id_92971aa6] · (usuario_id)  [m01_credencial_usuario_id_68f532a0]

#### `m01_evento_salida`  ·  COLA · outbox

Transactional Outbox: se escribe en la misma transacción que el cambio.

Clase `EventoSalida` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(36) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [m01_evento__publica_0dc93b_idx]

#### `m01_grupo`  ·  ENTIDAD

Grupo(id, organizacion, codigo, nombre, periodo, nivel_clave, politica_credencial, activo, creado_en)

Clase `Grupo` · app `acceso` · **PK** `id` · en el diseño v2: grupo

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | no |  | Llave foránea física → m01_organizacion. |
| `codigo` |  | VARCHAR(32) | no |  |  |
| `nombre` |  | VARCHAR(120) | no |  |  |
| `periodo` |  | VARCHAR(16) | no |  |  |
| `nivel_clave` |  | VARCHAR(24) | sí |  | Nivel educativo del Documento Maestro: decide la interfaz y permite políticas de acceso por nivel. |
| `politica_credencial_id` | **FK** → `m01_politica_credencial.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_politica_credencial. |
| `activo` |  | BOOLEAN | no | true |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `UNIQUE (organizacion_id, codigo, periodo)  [uq_m01_grupo_codigo_periodo]`

- Índices: (organizacion_id)  [m01_grupo_organizacion_id_4e8a8f11] · (politica_credencial_id)  [m01_grupo_politica_credencial_id_09bd4fb5]

#### `m01_identificador_usuario`  ·  ENTIDAD

IdentificadorUsuario(id, usuario, tipo, valor_cifrado, valor_hmac, es_login, verificado_en, creado_en, emisor, principal, retirado_en)

Clase `IdentificadorUsuario` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `tipo` |  | VARCHAR(24) | no |  |  |
| `valor_cifrado` |  | TEXT | no |  |  |
| `valor_hmac` |  | VARCHAR(64) | no |  |  |
| `es_login` |  | BOOLEAN | no | true |  |
| `verificado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `emisor` |  | VARCHAR(64) | no | '' | DEC-048: quién emitió el identificador (la institución o esta instalación). Vincula entre nodos. |
| `principal` |  | BOOLEAN | no | false |  |
| `retirado_en` |  | BIGINT | sí |  | CV-05: nada se borra. Un identificador que deja de valer se retira con fecha. |

Restricciones del motor:

- `UNIQUE (tipo, valor_hmac) WHERE retirado_en IS NULL  [uq_m01_identificador_valor]`
- `UNIQUE (usuario_id, tipo) WHERE retirado_en IS NULL  [uq_m01_identificador_tipo]`
- `UNIQUE (usuario_id) WHERE (principal AND retirado_en IS NULL)  [uq_m01_identificador_principal]`

- Índices: (usuario_id)  [m01_identificador_usuario_usuario_id_c772d50a] · (valor_hmac)  [m01_identif_valor_h_69e6fd_idx]

#### `m01_intento_acceso`  ·  REGISTRO · sólo inserción

IntentoAcceso(id, usuario, identificador_hmac, dispositivo, resultado, motivo, autorizacion, momento)

Clase `IntentoAcceso` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_usuario. |
| `identificador_hmac` |  | VARCHAR(64) | no | '' |  |
| `dispositivo_id` | **FK** → `m09_dispositivo.id` | VARCHAR(36) | sí |  | Llave foránea física → m09_dispositivo. |
| `resultado` |  | VARCHAR(24) | no |  |  |
| `motivo` |  | VARCHAR(64) | no | '' |  |
| `autorizacion_id` | **FK** → `m01_autorizacion_temporal.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_autorizacion_temporal. |
| `momento` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

- Índices: (autorizacion_id)  [m01_intento_acceso_autorizacion_id_697c3ba4] · (dispositivo_id)  [m01_intento_acceso_dispositivo_id_b4daccca] · (usuario_id)  [m01_intento_acceso_usuario_id_ec22ed07] · (usuario_id, momento DESC)  [m01_intento_usuario_79fa2b_idx] · (autorizacion_id)  [m01_intento_autoriz_d56615_idx] · (dispositivo_id, momento DESC)  [m01_intento_disposi_9a8167_idx] · (motivo, momento DESC)  [m01_intento_motivo_29a92d_idx]

#### `m01_miembro_grupo`  ·  REL · asociativa

MiembroGrupo(id, grupo, usuario, papel, desde, hasta)

Clase `MiembroGrupo` · app `acceso` · **PK** `id` · en el diseño v2: rel_alumno_grupo (con `papel` también cubre al profesor del grupo)

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `grupo_id` | **FK** → `m01_grupo.id` | VARCHAR(36) | no |  | Llave foránea física → m01_grupo. |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `papel` |  | VARCHAR(16) | no |  | ESTUDIANTE / DOCENTE |
| `desde` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `hasta` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_miembro_vigencia: (hasta IS NULL OR hasta >= (desde))`
- `UNIQUE (grupo_id, usuario_id, papel)  [uq_m01_miembro_papel]`

- Índices: (grupo_id)  [m01_miembro_grupo_grupo_id_b432a77e] · (usuario_id)  [m01_miembro_grupo_usuario_id_a20f8daf] · (usuario_id, papel)  [m01_miembro_usuario_9762df_idx]

#### `m01_organizacion`  ·  ENTIDAD

Organizacion(id, codigo, nombre, pais, idioma, locale, zona_horaria, creado_en, visitante)

Clase `Organizacion` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `codigo` | UQ | VARCHAR(32) | no |  |  |
| `nombre` |  | VARCHAR(200) | no |  |  |
| `pais` |  | VARCHAR(2) | no |  | ISO 3166-1 alpha-2 |
| `idioma` |  | VARCHAR(8) | no |  | ISO 639-1 |
| `locale` |  | VARCHAR(16) | no |  | BCP 47 |
| `zona_horaria` |  | VARCHAR(64) | no | 'America/Bogota' |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `visitante` |  | BOOLEAN | no | true | RN-47: la institución puede apagar la entrada como visitante (encendida por defecto). |

#### `m01_permiso`  ·  ENTIDAD

Permiso(codigo, modulo, descripcion, alcance_maximo)

Clase `Permiso` · app `acceso` · **PK** `codigo` · en el diseño v2: modulo_app

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `codigo` | **PK** | VARCHAR(64) | no |  |  |
| `modulo` |  | VARCHAR(24) | no |  |  |
| `descripcion` |  | VARCHAR(200) | no |  |  |
| `alcance_maximo` |  | VARCHAR(20) | no | 'ORGANIZATION' |  |

#### `m01_persona`  ·  ENTIDAD

Persona(usuario, nombres_cifrado, apellidos_cifrado, fecha_nacimiento_cifrado, telefono_cifrado, telefono_hmac, pais, actualizado_en)

Clase `Persona` · app `acceso` · **PK** `usuario_id` · en el diseño v2: usuario · alumno · profesor (nombre, apellido y fecha de nacimiento, ahora cifrados)

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `usuario_id` | **PK · FK** → `m01_usuario` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `nombres_cifrado` |  | TEXT | no |  |  |
| `apellidos_cifrado` |  | TEXT | no | '' |  |
| `fecha_nacimiento_cifrado` |  | TEXT | sí |  |  |
| `telefono_cifrado` |  | TEXT | sí |  |  |
| `telefono_hmac` |  | VARCHAR(64) | sí |  |  |
| `pais` |  | VARCHAR(2) | no |  |  |
| `actualizado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

- Índices: (telefono_hmac)  [m01_persona_telefono_hmac_a3f0e758]

#### `m01_pin_maestro`  ·  ENTIDAD

El PIN maestro de la institución (D-A5, RB-01): un secreto sin dueño, con versiones. Sólo se guarda su huella Argon2id. Una sola versión `activa` por organización; las sustituidas se conservan con su fecha (CV-05), porque el dominio impide reutilizar cualquiera de las tres últimas. `vence_en` = nacimiento + 365 días y nadie puede alargarlo.

Clase `PinMaestro` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | no |  | Llave foránea física → m01_organizacion. |
| `hash` |  | VARCHAR(255) | no |  | Argon2id codificado |
| `activa` |  | BOOLEAN | no | true |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | nulo en el primer arranque |
| `vence_en` |  | BIGINT | no |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `sustituida_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_pin_maestro_sustitucion: (activa OR sustituida_en IS NOT NULL)`
- `ck_m01_pin_maestro_vigencia: vence_en > (creado_en)`
- `UNIQUE (organizacion_id) WHERE activa  [uq_m01_pin_maestro_activo]`

- Índices: (creado_por_id)  [m01_pin_maestro_creado_por_id_f0f23598] · (organizacion_id)  [m01_pin_maestro_organizacion_id_99bd8478] · (organizacion_id, creado_en DESC)  [m01_pin_mae_organiz_e3a266_idx]

#### `m01_politica_credencial`  ·  ENTIDAD

PoliticaCredencial(id, organizacion, perfil, tipo_identificador, tipo_secreto, longitud_minima, exige_mayuscula, exige_minuscula, exige_digito, exige_simbolo, intentos_maximos, ventana_intentos_min, bloqueo_minutos, duracion_sesion_min, vigencia_credencial_dias, permite_acceso_temporal, nivel_clave, inactividad_min, autoregistro, bloqueo_alcance, creado_en, actualizado_en)

Clase `PoliticaCredencial` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | no |  | Llave foránea física → m01_organizacion. |
| `perfil` |  | VARCHAR(16) | no |  | student / teacher / admin |
| `tipo_identificador` |  | VARCHAR(24) | no |  |  |
| `tipo_secreto` |  | VARCHAR(16) | no |  |  |
| `longitud_minima` |  | SMALLINT | no | 6 |  |
| `exige_mayuscula` |  | BOOLEAN | no | false |  |
| `exige_minuscula` |  | BOOLEAN | no | false |  |
| `exige_digito` |  | BOOLEAN | no | false |  |
| `exige_simbolo` |  | BOOLEAN | no | false |  |
| `intentos_maximos` |  | SMALLINT | no | 5 |  |
| `ventana_intentos_min` |  | SMALLINT | no | 15 |  |
| `bloqueo_minutos` |  | SMALLINT | no | 15 |  |
| `duracion_sesion_min` |  | INTEGER | no | 240 |  |
| `vigencia_credencial_dias` |  | INTEGER | sí |  |  |
| `permite_acceso_temporal` |  | BOOLEAN | no | false |  |
| `nivel_clave` |  | VARCHAR(24) | sí |  | BR-024: excepción del perfil para un nivel educativo (preescolar con avatar). Nulo = política general. |
| `inactividad_min` |  | SMALLINT | no | 20 | FUN-009: minutos sin actividad tras los que la sesión se cierra sola. |
| `autoregistro` |  | BOOLEAN | no | false | RN-37: el propio usuario puede crear su cuenta (sólo `student` y `teacher`). RN-33: el castigo por fallar recae en la CUENTA o en la tableta (DISPOSITIVO). |
| `bloqueo_alcance` |  | VARCHAR(12) | no | 'CUENTA' |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `actualizado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_politica_pin_rango: (NOT (tipo_secreto = 'PIN') OR (longitud_minima >= 4 AND longitud_minima <= 8))`
- `ck_m01_politica_longitud: (longitud_minima >= 4 OR tipo_secreto = 'AVATAR')`
- `ck_m01_politica_bloqueo_alcance: bloqueo_alcance IN ('CUENTA', 'DISPOSITIVO')`
- `UNIQUE (organizacion_id, perfil) WHERE nivel_clave IS NULL  [uq_m01_politica_perfil]`
- `UNIQUE (organizacion_id, perfil, nivel_clave) WHERE nivel_clave IS NOT NULL  [uq_m01_politica_perfil_nivel]`

- Índices: (organizacion_id)  [m01_politica_credencial_organizacion_id_bd853e84]

#### `m01_rol`  ·  ENTIDAD

Rol(id, organizacion, codigo, nombre, menu_principal, nivel, es_sistema, creado_en)

Clase `Rol` · app `acceso` · **PK** `id` · en el diseño v2: rol

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_organizacion. |
| `codigo` |  | VARCHAR(32) | no |  |  |
| `nombre` |  | VARCHAR(80) | no |  |  |
| `menu_principal` |  | VARCHAR(16) | no |  |  |
| `nivel` |  | SMALLINT | no | 1 |  |
| `es_sistema` |  | BOOLEAN | no | false |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_rol_sistema_global: (NOT (es_sistema) OR organizacion_id IS NULL)`
- `ck_m01_rol_nivel: (nivel >= 1 AND nivel <= 3)`
- `UNIQUE (codigo) WHERE organizacion_id IS NULL  [uq_m01_rol_sistema]`
- `UNIQUE (organizacion_id, codigo)  [uq_m01_rol_codigo]`

- Índices: (organizacion_id)  [m01_rol_organizacion_id_051f4870]

#### `m01_rol_permiso`  ·  REL · asociativa

RolPermiso(id, rol, permiso, alcance)

Clase `RolPermiso` · app `acceso` · **PK** `id` · en el diseño v2: permiso

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `rol_id` | **FK** → `m01_rol.id` | VARCHAR(36) | no |  | Llave foránea física → m01_rol. |
| `permiso_codigo` | **FK** → `m01_permiso.codigo` | VARCHAR(64) | no |  | Llave foránea física → m01_permiso. |
| `alcance` |  | VARCHAR(20) | no |  |  |

Restricciones del motor:

- `UNIQUE (rol_id, permiso_codigo)  [uq_m01_rol_permiso]`

- Índices: (permiso_codigo)  [m01_rol_permiso_permiso_codigo_8a23bb3a] · (rol_id)  [m01_rol_permiso_rol_id_fe08c962]

#### `m01_sesion`  ·  ENTIDAD

Sesion(id, usuario, dispositivo, clase, emitida_en, expira_en, ultimo_uso_en, revocada_en, motivo_revocacion, evaluacion_ref, rol)

Clase `Sesion` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | jti del JWT |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `dispositivo_id` | **FK** → `m09_dispositivo.id` | VARCHAR(36) | sí |  | Llave foránea física → m09_dispositivo. |
| `clase` |  | VARCHAR(16) | no | 'NORMAL' |  |
| `emitida_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `expira_en` |  | BIGINT | no |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `ultimo_uso_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `revocada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `motivo_revocacion` |  | VARCHAR(64) | sí |  |  |
| `evaluacion_ref` | REF Biblioteca | VARCHAR(200) | sí |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `rol_id` | **FK** → `m01_rol.id` | VARCHAR(36) | sí |  | BR-021: el rol EFECTIVO de la sesión, elegido al entrar. Nulo en filas anteriores = rol principal del usuario. |

Restricciones del motor:

- `ck_m01_sesion_expira_despues: expira_en > (emitida_en)`
- `ck_m01_sesion_revocacion_motivada: (revocada_en IS NULL OR motivo_revocacion IS NOT NULL)`

- Índices: (dispositivo_id)  [m01_sesion_dispositivo_id_d83a11a3] · (usuario_id)  [m01_sesion_usuario_id_03f20fd1] · (usuario_id, revocada_en, expira_en)  [m01_sesion_usuario_5c5ef9_idx] · (rol_id)  [m01_sesion_rol_id_33ef5802]

#### `m01_usuario`  ·  ENTIDAD

La cuenta. Sin datos personales: esos van cifrados en Persona.

Clase `Usuario` · app `acceso` · **PK** `id` · en el diseño v2: usuario

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | no |  | Llave foránea física → m01_organizacion. |
| `rol_id` | **FK** → `m01_rol.id` | VARCHAR(36) | no |  | Llave foránea física → m01_rol. |
| `estado` |  | VARCHAR(16) | no | 'ACTIVO' |  |
| `alias` |  | VARCHAR(64) | no |  |  |
| `idioma` |  | VARCHAR(8) | no | 'es' |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `actualizado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_usuario. |
| `ultimo_acceso_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `provisional` |  | BOOLEAN | no | false | Admisión nominal (JRN-007): cuenta creada por el profesor «por su nombre», pendiente de vincular. |
| `vinculado_a_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_usuario. |
| `origen` |  | VARCHAR(16) | no | 'INSTALACION' | RB-03: cómo nació la cuenta y si el profesor ya confirmó que es quien dice ser (nulo = «sin confirmar»). |
| `confirmado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

- Índices: (organizacion_id)  [m01_usuario_organizacion_id_2f1bd94b] · (rol_id)  [m01_usuario_rol_id_1a5cb13c] · (creado_por_id)  [m01_usuario_creado_por_id_56acb03a] · (vinculado_a_id)  [m01_usuario_vinculado_a_id_8487a4f8] · (organizacion_id, estado)  [m01_usuario_organiz_c8194f_idx] · (rol_id)  [m01_usuario_rol_id_5690f4_idx] · (vinculado_a_id)  [m01_usuario_vincula_153213_idx] · (organizacion_id, origen)  [m01_usuario_organiz_9fcd6f_idx]

#### `m01_usuario_permiso`  ·  REL · asociativa

Permisos adicionales con alcance y vigencia. No hay columnas de contexto: el contexto lo da la pertenencia.

Clase `UsuarioPermiso` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `permiso_codigo` | **FK** → `m01_permiso.codigo` | VARCHAR(64) | no |  | Llave foránea física → m01_permiso. |
| `alcance` |  | VARCHAR(20) | no |  |  |
| `otorgado_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `motivo` |  | VARCHAR(200) | no |  |  |
| `vigente_desde` |  | BIGINT | no | ahora_ms() |  |
| `vigente_hasta` |  | BIGINT | sí |  |  |
| `revocado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_usuario_permiso_vigencia: (vigente_hasta IS NULL OR vigente_hasta > (vigente_desde))`
- `UNIQUE (usuario_id, permiso_codigo) WHERE revocado_en IS NULL  [uq_m01_usuario_permiso_vigente]`

- Índices: (otorgado_por_id)  [m01_usuario_permiso_otorgado_por_id_0bf6e1dc] · (permiso_codigo)  [m01_usuario_permiso_permiso_codigo_275cacc1] · (usuario_id)  [m01_usuario_permiso_usuario_id_d3584cfc]

#### `m01_usuario_rol`  ·  REL · asociativa

Asignación de rol con alcance concreto y vigencia (m01_persona_rol del Documento Maestro, BR-021). `Usuario.rol` sigue siendo el rol principal (el que se usa si la persona no elige otro al entrar). Aquí van todos los roles vigentes de la persona; en cada sesión trabaja con uno solo.

Clase `UsuarioRol` · app `acceso` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `usuario_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | no |  | Llave foránea física → m01_usuario. |
| `rol_id` | **FK** → `m01_rol.id` | VARCHAR(36) | no |  | Llave foránea física → m01_rol. |
| `alcance_tipo` |  | VARCHAR(20) | no | 'ORGANIZATION' | ORGANIZATION / LEVEL / ASSIGNED_GROUPS |
| `alcance_id` |  | VARCHAR(36) | sí |  | nivel_clave o grupo_id |
| `desde` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `hasta` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `asignado_por_id` | **FK** → `m01_usuario.id` | VARCHAR(36) | sí |  | Llave foránea física → m01_usuario. |
| `revocado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m01_usuario_rol_vigencia: (hasta IS NULL OR hasta > (desde))`
- `ck_m01_usuario_rol_alcance_id: (alcance_tipo = 'ORGANIZATION' OR alcance_id IS NOT NULL)`
- `UNIQUE (usuario_id, rol_id, alcance_tipo, alcance_id) WHERE revocado_en IS NULL  [uq_m01_usuario_rol_vigente]`

- Índices: (asignado_por_id)  [m01_usuario_rol_asignado_por_id_60caf213] · (rol_id)  [m01_usuario_rol_rol_id_f6b33be0] · (usuario_id)  [m01_usuario_rol_usuario_id_9468c4d2] · (usuario_id, revocado_en)  [m01_usuario_usuario_55c112_idx]

### MOD-009 · Gestión de dispositivos

#### `m09_dim_sesion_alumno`  ·  DIM · dimensión

Desde qué tableta y durante qué periodo está conectado un alumno. De ella cuelga su participación en clase (`m07_participante.dim_sesion_alumno_id`). INV-011: una tableta compartida tiene cero o una sesión activa (`ux_m09_dsa_dispositivo_abierta`). DEC-023: un alumno tiene una sola sesión abierta (`ux_m09_dsa_alumno_abierta`). Abrir otra cierra la anterior con motivo `relevo`: el dispositivo nunca bloquea al alumno.

Clase `DimSesionAlumno` · app `device_manager` · **PK** `id` · en el diseño v2: dim_sesion_alumno

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | persona_id (referencia lógica a MOD-001, CV-08) |
| `dispositivo_id` | **FK** → `m09_dispositivo.id` | VARCHAR(36) | no |  | Llave foránea física → m09_dispositivo. |
| `iniciada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `finalizada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `motivo_cierre` |  | VARCHAR(16) | no | '' | usuario · inactividad · sistema · relevo |

Restricciones del motor:

- `ck_m09_dsa_vigencia: (finalizada_en IS NULL OR finalizada_en >= (iniciada_en))`
- `ck_m09_dsa_cierre_motivado: (finalizada_en IS NULL OR NOT (motivo_cierre = ''))`
- `UNIQUE (alumno_id) WHERE finalizada_en IS NULL  [ux_m09_dsa_alumno_abierta]`
- `UNIQUE (dispositivo_id) WHERE finalizada_en IS NULL  [ux_m09_dsa_dispositivo_abierta]`

- Índices: (dispositivo_id)  [m09_dim_sesion_alumno_dispositivo_id_c6cee9d0] · (dispositivo_id, finalizada_en)  [ix_m09_dsa_dispositivo] · (alumno_id, iniciada_en)  [ix_m09_dsa_alumno]

#### `m09_dispositivo`  ·  ENTIDAD

ENT-017. Contexto técnico, nunca identidad. `bloqueado` deja a la tableta fuera de las sesiones y de los lanzamientos sin darla de baja; `activo=False` la retira conservando su historial.

Clase `Dispositivo` · app `device_manager` · **PK** `id` · en el diseño v2: dispositivo

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `organizacion_id` | **FK** → `m01_organizacion.id` | VARCHAR(36) | no |  | Llave foránea física → m01_organizacion. |
| `identificador_hw` |  | VARCHAR(128) | no |  | huella de la instalación; con ella se reconoce la tableta |
| `nombre` |  | VARCHAR(120) | no |  |  |
| `tipo` |  | VARCHAR(16) | no | 'TABLETA' | TABLETA · MASTER · OTRO |
| `plataforma` |  | VARCHAR(16) | no | '' | windows · android · '' si no lo ha dicho |
| `version_app` |  | VARCHAR(32) | no | '' |  |
| `activo` |  | BOOLEAN | no | true |  |
| `bloqueado` |  | BOOLEAN | no | false |  |
| `registrado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `ultimo_latido_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `espacio_libre_mb` |  | INTEGER | sí |  | Última lectura que la tableta declaró con su latido (009-04). El historial va por el evento de inventario. |
| `bateria_pct` |  | SMALLINT | sí |  |  |
| `perfil` |  | VARCHAR(12) | no | 'compartido' | 009-06 · 008-01: el equipo es del aula (`compartido`) o nominal de una persona (`asignado`). El modo de estudio sirve en cualquier equipo (D-15), pero sólo el dueño de un equipo asignado se lleva la descarga de paquetes (BR-054). `asignado_a_id` es la referencia lógica a `m01_usuario.id` (CV-08). |
| `asignado_a_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | sí |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `asignado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `capacidad_control` |  | VARCHAR(12) | no | '' | MOD-010 · BR-075: lo que la tableta DECLARA poder garantizar en un examen (`abierto` · `supervisado` · `controlado`; vacío = nunca lo declaró) y el detalle que informa (`bloqueo_sistema`, `motivo`…). El nodo no lo infiere de la plataforma: la app mide e informa. |
| `capacidad_detalle` |  | JSON | no | dict() |  |
| `capacidad_declarada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m09_dispositivo_perfil_dueno: ((perfil = 'asignado' AND asignado_a_id IS NOT NULL) OR (NOT (perfil = 'asignado') AND asignado_a_id IS NULL))`
- `ck_m09_dispositivo_perfil_valido: perfil IN ('compartido', 'asignado')`
- `ck_m09_dispositivo_capacidad_valida: capacidad_control IN ('', 'abierto', 'supervisado', 'controlado')`
- `UNIQUE (organizacion_id, identificador_hw)  [uq_m09_dispositivo_identificador]`

- Índices: (organizacion_id)  [m09_dispositivo_organizacion_id_15f1aef0]

#### `m09_evento_salida`  ·  COLA · outbox

Transactional Outbox de MOD-009 (`dispositivo.*.v1`). Se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (m15_evento) las colas de todos los módulos se unifican allí.

Clase `EventoSalida` · app `device_manager` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(36) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [ix_m09_outbox]

### MOD-007 · Aula (Classroom Engine)

#### `m07_aviso`  ·  ENTIDAD

Mensaje de aviso del profesor a un dispositivo o al grupo (FUN-075).

Clase `Aviso` · app `classroom_engine` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `sesion_id` | **FK** → `m07_sesion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `participante_id` | **FK** → `m07_participante.id` | VARCHAR(36) | sí |  | Llave foránea física → m07_participante. |
| `texto` |  | VARCHAR(300) | no |  |  |
| `enviado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

- Índices: (participante_id)  [m07_aviso_participante_id_cd04c489] · (sesion_id)  [m07_aviso_sesion_id_3925057d] · (sesion_id, enviado_en)  [ix_m07_aviso]

#### `m07_control`  ·  ENTIDAD

Un periodo en que un control está activo sobre el grupo: `seguimiento` (BR-050) o `bloqueo` de pantallas (FUN-074). Abierto = `hasta` nulo; a lo sumo uno abierto por tipo.

Clase `Control` · app `classroom_engine` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `sesion_id` | **FK** → `m07_sesion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `tipo` |  | VARCHAR(16) | no |  | `IN ('seguimiento', 'bloqueo')` |
| `desde` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `hasta` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `motivo` |  | VARCHAR(200) | no | '' |  |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |
| `cerrado_por` |  | VARCHAR(64) | no | '' |  |

Restricciones del motor:

- `ck_m07_control_vigencia: (hasta IS NULL OR hasta >= (desde))`
- `UNIQUE (sesion_id, tipo) WHERE hasta IS NULL  [ux_m07_control_abierto]`

- Índices: (sesion_id)  [m07_control_sesion_id_7cc21a4f]

#### `m07_distribucion`  ·  ENTIDAD

El lanzamiento: envío de un recurso o de una actividad a todos o a algunos, con avance de entrega (CAP-040, FUN-070, FUN-071). Es la tabla `lanzamiento` de la segunda versión del modelo de datos: `alcance` y `destinatarios` dicen a quién; `intentos_permitidos` y `tiempo_limite_seg` son las reglas con las que se lanzó; una tableta bloqueada (MOD-009) queda fuera y consta en `excluidos_bloqueados`.

Clase `Distribucion` · app `classroom_engine` · **PK** `id` · en el diseño v2: lanzamiento

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `sesion_id` | **FK** → `m07_sesion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `clase` |  | VARCHAR(16) | no |  | `IN ('recurso', 'actividad')` |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | sí | '' | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `leccion_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_tipo` |  | VARCHAR(24) | no | '' |  |
| `media_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `rotulo` |  | VARCHAR(250) | no | '' |  |
| `alcance` |  | VARCHAR(16) | no | 'grupo' | `IN ('grupo', 'seleccion')` |
| `destinatarios` |  | JSON | no | list() | persona_id de quienes lo recibieron al lanzar |
| `excluidos_bloqueados` |  | JSON | no | list() | persona_id dejados fuera por tableta bloqueada o retirada |
| `intentos_permitidos` |  | SMALLINT | sí |  | NULL: manda el objeto |
| `tiempo_limite_seg` |  | INTEGER | sí |  |  |
| `disponible_estudio` |  | BOOLEAN | no | false | MOD-008 decide si lo descarga |
| `asignacion_ref` | **FK lógica** ⇢ `m10_asignacion.id` | VARCHAR(64) | sí | '' | MOD-010, devuelto por el puerto Evaluacion |
| `total_preguntas` |  | SMALLINT | no | 0 | de la actividad, fijado al lanzarla (el curso no se cachea) |
| `puntos_totales` |  | FLOAT | no | 0 |  |
| `pausada_ms` |  | BIGINT | no | 0 | tiempo que la clase estuvo suspendida con la actividad abierta |
| `estudio_hasta` |  | BIGINT | sí |  | «dejar como tarea de estudio» hasta este instante (MOD-008) |
| `abierta_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `cerrada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m07_dist_referencia: (NOT (objeto_ref = '') OR NOT (media_ref = ''))`
- `ck_m07_dist_cierre_posterior: (cerrada_en IS NULL OR cerrada_en >= (abierta_en))`
- `ck_m07_dist_intentos: (intentos_permitidos IS NULL OR intentos_permitidos >= 1)`
- `ck_m07_dist_tiempo: (tiempo_limite_seg IS NULL OR tiempo_limite_seg >= 1)`

- Índices: (sesion_id)  [m07_distribucion_sesion_id_da54b296] · (sesion_id, cerrada_en)  [ix_m07_dist_abiertas]

#### `m07_distribucion_entrega`  ·  REL · asociativa

Avance de entrega por participante: la «confirmación» de CAP-040.

Clase `DistribucionEntrega` · app `classroom_engine` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `distribucion_id` | **FK** → `m07_distribucion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_distribucion. |
| `participante_id` | **FK** → `m07_participante.id` | VARCHAR(36) | no |  | Llave foránea física → m07_participante. |
| `estado` |  | VARCHAR(16) | no | 'pendiente' | `IN ('pendiente', 'entregado', 'fallido')` |
| `confirmada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | INTEGER | no | 0 |  |

Restricciones del motor:

- `ck_m07_entrega_confirmada: (NOT (estado = 'entregado') OR confirmada_en IS NOT NULL)`
- `UNIQUE (distribucion_id, participante_id)  [ux_m07_entrega]`

- Índices: (distribucion_id)  [m07_distribucion_entrega_distribucion_id_9899c419] · (participante_id)  [m07_distribucion_entrega_participante_id_746b542b]

#### `m07_evento_salida`  ·  COLA · outbox

Transactional Outbox de MOD-007 (`aula.*.v1`). Se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (m15_evento) ambas colas se unifican allí.

Clase `EventoSalida` · app `classroom_engine` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(36) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [ix_m07_outbox]

#### `m07_intento`  ·  ENTIDAD

El intento de un alumno sobre una actividad lanzada en clase (tabla `intento` del modelo v2, provisional en MOD-007 hasta que MOD-010 tenga dueño). Las respuestas por pregunta viven dentro del intento (decisión del CTO del 2026-09-24): una por elemento de `respuestas`, con su secuencia, su hora capturada y su veredicto. La unicidad (pregunta, sesión, secuencia) de INV-013 se valida en la aplicación, dentro de la transacción, porque no se puede expresar como restricción sobre una lista JSON.

Clase `Intento` · app `classroom_engine` · **PK** `id` · en el diseño v2: intento

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `distribucion_id` | **FK** → `m07_distribucion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_distribucion. |
| `participante_id` | **FK** → `m07_participante.id` | VARCHAR(36) | no |  | Llave foránea física → m07_participante. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `numero` |  | SMALLINT | no | 1 |  |
| `estado` |  | VARCHAR(20) | no | 'en_curso' | `IN ('en_curso', 'entregado', 'pendiente_decision', 'descartado')` |
| `iniciado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `enviado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `capturado_en` |  | BIGINT | sí |  | última captura declarada por la tableta, ya normalizada |
| `puntaje` |  | FLOAT | sí |  | bruto, sólo de lo ya calificado |
| `puntaje_maximo` |  | FLOAT | sí |  |  |
| `respuestas` |  | JSON | no | list() |  |
| `origen_envio` |  | VARCHAR(16) | no | 'directo' | directo \| cola \| cierre |
| `recuperado_de_cola` |  | BOOLEAN | no | false | llegó por la ventana de gracia (DEC-019) |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m09_dispositivo: se guarda la llave, el motor no la impone. |

Restricciones del motor:

- `ck_m07_intento_envio_posterior: (enviado_en IS NULL OR enviado_en >= (iniciado_en))`
- `UNIQUE (distribucion_id, participante_id) WHERE estado = 'en_curso'  [ux_m07_intento_en_curso]`
- `UNIQUE (distribucion_id, participante_id, numero)  [ux_m07_intento_numero]`

- Índices: (distribucion_id)  [m07_intento_distribucion_id_eb67db00] · (participante_id)  [m07_intento_participante_id_4f933d8d] · (distribucion_id, estado)  [ix_m07_intento_dist]

#### `m07_participante`  ·  REL · asociativa

Presencia técnica, que no es asistencia académica. Su `id` es el identificador de participación que la tableta vuelve a presentar al reconectar (FUN-077).

Clase `Participante` · app `classroom_engine` · **PK** `id` · en el diseño v2: rel_sesion_alumno_clase

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `sesion_id` | **FK** → `m07_sesion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `persona_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `dispositivo` |  | VARCHAR(64) | no | '' | huella que declara la tableta; contexto, nunca identidad |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | m09_dispositivo (MOD-009), lógica |
| `dim_sesion_alumno_id` | **FK lógica** ⇢ `m09_dim_sesion_alumno.id` | VARCHAR(36) | sí | '' | m09_dim_sesion_alumno (MOD-009), lógica |
| `sesion_usuario_id` | **FK lógica** ⇢ `m01_sesion.id` | VARCHAR(36) | sí | '' | m01_sesion (MOD-001), lógica |
| `estado` |  | VARCHAR(16) | no | 'conectado' | `IN ('esperando', 'conectado', 'reconectando', 'salio', 'rechazado', 'expulsado')` |
| `admision_nominal` |  | BOOLEAN | no | false | BR-047: invitado admitido por el profesor |
| `ingreso` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `salida` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `ultimo_latido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `admitido_por` |  | VARCHAR(64) | no | '' |  |
| `motivo` |  | VARCHAR(200) | no | '' |  |
| `ayuda_en` |  | BIGINT | sí |  | mano levantada: instante en que pidió ayuda |
| `proyectado_desde` |  | BIGINT | sí |  | DEC-034: su pantalla se proyecta al grupo desde este instante |
| `proyectado_por` |  | VARCHAR(64) | no | '' |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m07_part_salida_fechada: (NOT (estado IN ('salio', 'rechazado', 'expulsado')) OR salida IS NOT NULL)`
- `UNIQUE (sesion_id, persona_id)  [ux_m07_part]`

- Índices: (sesion_id)  [m07_participante_sesion_id_e1c21588] · (sesion_id, estado)  [ix_m07_part_estado]

#### `m07_presencia`  ·  REGISTRO · sólo inserción

Bitácora de presencia técnica (FUN-073): cada cambio de estado, con el reloj del nodo. Append-only.

Clase `Presencia` · app `classroom_engine` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `participante_id` | **FK** → `m07_participante.id` | VARCHAR(36) | no |  | Llave foránea física → m07_participante. |
| `estado` |  | VARCHAR(16) | no |  | `IN ('esperando', 'conectado', 'reconectando', 'salio', 'rechazado', 'expulsado')` |
| `dispositivo` |  | VARCHAR(64) | no | '' |  |
| `detalle` |  | VARCHAR(200) | no | '' |  |
| `momento` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

- Índices: (participante_id)  [m07_presencia_participante_id_693639d8] · (participante_id, momento)  [ix_m07_presencia]

#### `m07_resumen`  ·  ENTIDAD

Consolidado al cerrar (FUN-079, CAP-045). Es lo que se conserva cinco años.

Clase `Resumen` · app `classroom_engine` · **PK** `sesion_id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `sesion_id` | **PK · FK** → `m07_sesion` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `participantes` |  | INTEGER | no | 0 |  |
| `conectados_maximo` |  | INTEGER | no | 0 |  |
| `admitidos_nominal` |  | INTEGER | no | 0 |  |
| `selectores` |  | INTEGER | no | 0 |  |
| `distribuciones` |  | INTEGER | no | 0 |  |
| `actividades` |  | INTEGER | no | 0 |  |
| `avisos` |  | INTEGER | no | 0 |  |
| `pendientes` |  | INTEGER | no | 0 | intentos abiertos al cierre (MOD-010, por el puerto) |
| `duracion_ms` |  | BIGINT | no | 0 |  |
| `origen_cierre` |  | VARCHAR(16) | no | 'profesor' | `IN ('profesor', 'inactividad', 'administrador', 'sistema')` |
| `consolidado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `detalle` |  | JSON | no | dict() | participación por alumno y pendientes, para PAN-008 (007-09) |

#### `m07_selector`  ·  ENTIDAD

Lo que el profesor tiene seleccionado para proyectar (FUN-069, BR-049): una lámina, una página, un objeto o un medio suelto. Bitácora con un solo selector vigente por sesión. No es un lanzamiento: cambia varias veces por minuto, no espera confirmación ni genera intentos.

Clase `Selector` · app `classroom_engine` · **PK** `id` · en el diseño v2: selector

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `sesion_id` | **FK** → `m07_sesion.id` | VARCHAR(36) | no |  | Llave foránea física → m07_sesion. |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | sí | '' | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `curso_version` |  | VARCHAR(32) | no | '' |  |
| `leccion_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_tipo` |  | VARCHAR(24) | no | '' | lecture, explanation, simulation_lab, activity |
| `unidad_ref` | REF Biblioteca | VARCHAR(120) | no | '' | lámina, página o pregunta |
| `unidad_indice` |  | INTEGER | sí |  |  |
| `media_ref` | REF Biblioteca | VARCHAR(120) | no | '' | un medio proyectado suelto |
| `rotulo` |  | VARCHAR(250) | no | '' |  |
| `vigente` |  | BOOLEAN | no | true |  |
| `declarado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `declarado_por` |  | VARCHAR(64) | no | '' |  |
| `sustituido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m07_selector_sustitucion: (vigente OR sustituido_en IS NOT NULL)`
- `ck_m07_selector_referencia: (NOT (curso_ref = '') OR NOT (media_ref = ''))`
- `UNIQUE (sesion_id) WHERE vigente  [ux_m07_selector_vigente]`

- Índices: (sesion_id)  [m07_selector_sesion_id_983f035c] · (sesion_id, declarado_en)  [ix_m07_selector]

#### `m07_sesion`  ·  ENTIDAD

ENT-015. Cerrada nunca se reabre; reanudar conserva el código de unión.

Clase `SesionDeClase` · app `classroom_engine` · **PK** `id` · en el diseño v2: clase

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `grupo_id` | **FK lógica** ⇢ `m01_grupo.id` | VARCHAR(36) | sí | '' | m01_grupo; vacío = sin padrón (Q-34) |
| `grupo_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `profesor_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | m01_usuario.id o identificador del aula |
| `profesor_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `relevo_de_sesion_id` | **FK lógica** ⇢ `m07_sesion.id` | VARCHAR(36) | sí | '' | DEC-035 |
| `via_origen` |  | VARCHAR(16) | no |  | --- por dónde empezó (BR-044) y qué se referencia (CV-08) --- `IN ('arbol', 'leccion', 'recurso', 'libre')` |
| `plan_id` |  | VARCHAR(36) | no | '' | MOD-006, por el puerto PlanDeClase |
| `nodo_ref` | REF Biblioteca | VARCHAR(120) | no | '' | MOD-003, árbol académico |
| `fuente_curso` |  | VARCHAR(16) | no | '' | biblioteca \| ejemplo |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | sí | '' | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `curso_version` |  | VARCHAR(32) | no | '' |  |
| `curso_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `leccion_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `leccion_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `objeto_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `codigo_union` |  | VARCHAR(8) | no |  | --- ciclo de vida --- |
| `estado` |  | VARCHAR(16) | no | 'abierta' | `IN ('planificada', 'abierta', 'suspendida', 'cerrada', 'archivada')` |
| `superficie` |  | VARCHAR(64) | no | '' | navegador \| pantalla \| dispositivo |
| `iniciada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `suspendida_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `causa_suspension` |  | VARCHAR(24) | no | '' |  |
| `finalizada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `origen_cierre` |  | VARCHAR(16) | no | '' |  |
| `archivada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `anclajes` |  | JSON | no | list() | Anclaje curricular (BR-039/040): nunca obligatorio y asignable después de cerrar. Provisional: lista de {ref, rotulo} hasta que el CTO decida entre `clase.tema_id` y una tabla puente (007-09). |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m07_sesion_cierre_fechado: (NOT (estado IN ('cerrada', 'archivada')) OR finalizada_en IS NOT NULL)`
- `ck_m07_sesion_archivo_fechado: (NOT (estado = 'archivada') OR archivada_en IS NOT NULL)`
- `ck_m07_sesion_via_leccion: (NOT (via_origen = 'leccion') OR (NOT (curso_ref = '') AND NOT (leccion_ref = '')))`
- `ck_m07_sesion_via_recurso: (NOT (via_origen = 'recurso') OR (NOT (curso_ref = '') AND NOT (objeto_ref = '')))`
- `ck_m07_sesion_via_arbol: (NOT (via_origen = 'arbol') OR NOT (nodo_ref = ''))`
- `UNIQUE (codigo_union) WHERE estado IN ('abierta', 'suspendida')  [ux_m07_codigo]`
- `UNIQUE (grupo_id) WHERE (estado IN ('abierta', 'suspendida') AND NOT (grupo_id = ''))  [ux_m07_grupo_activa]`
- `UNIQUE (profesor_id) WHERE estado = 'abierta'  [ux_m07_profesor_abierta]`

- Índices: (profesor_id, iniciada_en)  [ix_m07_sesion_prof] · (estado, finalizada_en)  [ix_m07_sesion_estado]

### MOD-008 · Modo de estudio

#### `m08_asignacion`  ·  ENTIDAD

Una lección asignada a un grupo o a alumnos con fecha límite (CAP-050). Provisional hasta MOD-010. `alcance = grupo` alcanza a todos los alumnos ACTIVOS del grupo, también a los que entren después; `seleccion` sólo a los `destinatarios`. `bloques` es la estructura de la lección como referencias (D-4) tal como se vio al asignar: se refresca al abrir la lección si la versión del curso cambió. `bytes_estimados` se mide al asignar y se afina al preparar el paquete.

Clase `Asignacion` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `grupo_id` | **FK lógica** ⇢ `m01_grupo.id` | VARCHAR(36) | sí | '' | m01_grupo (lógica); vacío si son alumnos sueltos |
| `grupo_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `alcance` |  | VARCHAR(16) | no | 'grupo' | `IN ('grupo', 'seleccion')` |
| `destinatarios` |  | JSON | no | list() | lista de alumno_id; sólo con `seleccion` |
| `profesor_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | quien asigna (m01_usuario.id o identificador del aula) |
| `profesor_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `fuente_curso` |  | VARCHAR(16) | no | '' | biblioteca \| ejemplo |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | no |  | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `curso_version` |  | VARCHAR(32) | no | '' |  |
| `curso_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `leccion_ref` | REF Biblioteca | VARCHAR(120) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `leccion_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `titulo` |  | VARCHAR(250) | no |  |  |
| `descripcion` |  | VARCHAR(500) | no | '' |  |
| `asignatura_rotulo` |  | VARCHAR(120) | no | '' | classification.subject.name |
| `unidad_rotulo` |  | VARCHAR(200) | no | '' | classification.topic.name |
| `consigna` |  | TEXT | no | '' | opcional: el profesor no tiene teclado, se ofrece por opciones |
| `bloques` |  | JSON | no | list() | [{ref, indice, objeto_ref, tipo, titulo, obligatorio, medios}] |
| `practica` |  | JSON | sí |  | {objeto_ref, titulo, total_preguntas}: la primera actividad |
| `evaluacion` |  | JSON | sí |  | {objeto_ref, titulo}: el primer examen, SÓLO informativo |
| `bytes_estimados` |  | BIGINT | sí |  |  |
| `paquete_permitido` |  | BOOLEAN | no | true | «decide si queda disponible en modo de estudio» (JRN-007) |
| `fecha_limite` |  | BIGINT | sí |  |  |
| `plazo` |  | VARCHAR(12) | no | 'blando' | `IN ('blando', 'endurecido')` |
| `gracia_ms` |  | INTEGER | no | 900000 | DEC-019 |
| `estado` |  | VARCHAR(12) | no | 'activa' | `IN ('activa', 'cerrada')` |
| `creada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `cerrada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m08_asignacion_alcance: alcance IN ('grupo', 'seleccion')`
- `ck_m08_asignacion_plazo: plazo IN ('blando', 'endurecido')`
- `ck_m08_asignacion_estado: estado IN ('activa', 'cerrada')`
- `ck_m08_asignacion_cierre_fechado: ((estado = 'cerrada' AND cerrada_en IS NOT NULL) OR (NOT (estado = 'cerrada') AND cerrada_en IS NULL))`
- `ck_m08_asignacion_gracia: gracia_ms >= 0`

- Índices: (grupo_id, estado)  [ix_m08_asignacion_grupo] · (estado, fecha_limite)  [ix_m08_asignacion_plazo]

#### `m08_evento_salida`  ·  COLA · outbox

Transactional Outbox de MOD-008 (`estudio.*.v1`). Se escribe en la misma transacción que el hecho (DEC-007). Cuando exista MOD-015 (m15_evento) las colas de todos los módulos se unifican allí.

Clase `EventoSalida` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(64) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [ix_m08_outbox]

#### `m08_paquete`  ·  ENTIDAD

El paquete de estudio de UN aparato para UN alumno y una asignación (CAP-047, D-7, D-8): la lección sin claves más los medios que referencia, con su huella y su vigencia. Sólo guarda metadatos de los archivos (nunca contenido). Volver a pedirlo reutiliza la fila («Actualizar descarga»). `vencido` se calcula al leer y se persiste; el alumno que borra su copia deja `retirado_en`.

Clase `Paquete` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `asignacion_id` | **FK** → `m08_asignacion.id` | VARCHAR(36) | no |  | Llave foránea física → m08_asignacion. |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | no |  | m09_dispositivo (lógica) |
| `estado` |  | VARCHAR(16) | no | 'solicitado' | `IN ('solicitado', 'descargandose', 'disponible', 'vencido', 'denegado')` |
| `motivo` |  | VARCHAR(48) | no | '' | denegado o vencido: por qué |
| `curso_version` |  | VARCHAR(32) | no | '' | la del curso al preparar el paquete |
| `huella` |  | VARCHAR(64) | no | '' | SHA-256 del manifiesto canónico |
| `bytes_total` |  | BIGINT | no | 0 | suma de los medios |
| `archivos` |  | JSON | no | list() | [{media_ref, clase, mime, bytes, sha256}] |
| `no_incluidos` |  | JSON | no | list() | [{media_ref, motivo}] |
| `vigente_hasta` |  | BIGINT | sí |  |  |
| `solicitado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `descarga_iniciada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `disponible_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `retirado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `actualizado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m08_paquete_estado: estado IN ('solicitado', 'descargandose', 'disponible', 'vencido', 'denegado')`
- `ck_m08_paquete_disponible_con_huella: (NOT (estado = 'disponible') OR (NOT (huella = '') AND disponible_en IS NOT NULL))`
- `UNIQUE (asignacion_id, alumno_id, dispositivo_id)  [ux_m08_paquete]`

- Índices: (asignacion_id)  [m08_paquete_asignacion_id_cd84e8f6] · (dispositivo_id, estado)  [ix_m08_paquete_dispositivo]

#### `m08_practica`  ·  ENTIDAD

Una práctica autocalificable: actividad de aprendizaje SEPARADA de la evaluación formal (D-5, BR-055). Provisional hasta MOD-010. `modo` sólo admite `estudio` (`CHECK`): esta tabla no puede contener intentos formales, y el módulo nunca toca `m07_intento` ni `m10_intento`. Sin tope de intentos. Las respuestas por pregunta viven dentro de la práctica, como en `m07_intento` (decisión del CTO del 2026-09-24): una por elemento de `respuestas` con su secuencia, su hora capturada y su veredicto. La unicidad (pregunta, secuencia) de INV-013 se valida en la aplicación, dentro de la transacción, porque no se puede expresar sobre una lista JSON. `puntaje` y `puntaje_maximo` viven en la escala interna y no se publican (DEC-032).

Clase `Practica` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `tarea_id` | **FK** → `m08_tarea.id` | VARCHAR(36) | no |  | Llave foránea física → m08_tarea. |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `objeto_ref` | REF Biblioteca | VARCHAR(120) | no |  | la `activity` practicada |
| `objeto_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `numero` |  | SMALLINT | no | 1 | 1, 2, 3… sin tope |
| `modo` |  | VARCHAR(8) | no | 'estudio' |  |
| `estado` |  | VARCHAR(12) | no | 'en_curso' | `IN ('en_curso', 'terminada')` |
| `respuestas` |  | JSON | no | list() | {pregunta_ref, respuesta, secuencia, sesion_ref, recibida_en, capturada_en, veredicto} |
| `total_preguntas` |  | SMALLINT | no | 0 |  |
| `aciertos` |  | SMALLINT | no | 0 | respuestas con correcta = true |
| `puntaje` |  | FLOAT | sí |  | sólo de lo ya calificado; escala interna, no se publica |
| `puntaje_maximo` |  | FLOAT | sí |  |  |
| `origen` |  | VARCHAR(8) | no | 'directo' | `IN ('directo', 'cola')` |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m09_dispositivo: se guarda la llave, el motor no la impone. |
| `iniciada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `terminada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m08_practica_modo_estudio: modo = 'estudio'`
- `ck_m08_practica_estado: estado IN ('en_curso', 'terminada')`
- `ck_m08_practica_terminada_fechada: (NOT (estado = 'terminada') OR terminada_en IS NOT NULL)`
- `UNIQUE (tarea_id, objeto_ref) WHERE estado = 'en_curso'  [ux_m08_practica_en_curso]`
- `UNIQUE (tarea_id, objeto_ref, numero)  [ux_m08_practica_numero]`

- Índices: (tarea_id)  [m08_practica_tarea_id_a0e04728] · (tarea_id, objeto_ref)  [ix_m08_practica_tarea]

#### `m08_sincronizacion`  ·  REGISTRO · sólo inserción

El libro de eventos que llegan de la cola del aparato (CAP-048, D-10, D-11). `UNIQUE(emisor_id, secuencia)`: el reenvío NO duplica (BR-060). Sin FK. `carga` sólo se conserva completa mientras el evento está `pendiente_decision`; después queda un resumen sin el contenido de las respuestas (BR-127). `resultado` guarda lo que se contestó, para responder igual a un reenvío. `ocurrido_en` ya viene normalizado al reloj del nodo; `ocurrido_en_tableta` es la hora cruda del aparato (dato adicional, BR-062).

Clase `Sincronizacion` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `emisor_id` |  | VARCHAR(64) | no |  |  |
| `secuencia` |  | BIGINT | no |  |  |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m09_dispositivo: se guarda la llave, el motor no la impone. |
| `tipo` |  | VARCHAR(40) | no |  |  |
| `asignacion_id` | **FK lógica** ⇢ `m08_asignacion.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m08_asignacion: se guarda la llave, el motor no la impone. |
| `estado` |  | VARCHAR(20) | no |  | `IN ('integrado', 'rechazado', 'pendiente_decision')` |
| `motivo` |  | VARCHAR(64) | no | '' |  |
| `ocurrido_en` |  | BIGINT | no |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `ocurrido_en_tableta` |  | BIGINT | sí |  |  |
| `recibido_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `carga` |  | JSON | no | dict() |  |
| `resultado` |  | JSON | no | dict() |  |

Restricciones del motor:

- `ck_m08_sync_estado: estado IN ('integrado', 'rechazado', 'pendiente_decision')`
- `UNIQUE (emisor_id, secuencia)  [ux_m08_sync_emisor_secuencia]`

- Índices: (alumno_id, estado)  [ix_m08_sync_alumno] · (asignacion_id, estado)  [ix_m08_sync_asignacion]

#### `m08_tarea`  ·  REL · asociativa

El estado de una asignación para UN alumno (provisional hasta MOD-010). Se crea al primer contacto del alumno (abrir, avanzar, pedir paquete o practicar); una asignación sin tarea equivale a `pendiente`. «Vencida» no se guarda: es derivada.

Clase `Tarea` · app `modo_estudio` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `asignacion_id` | **FK** → `m08_asignacion.id` | VARCHAR(36) | no |  | Llave foránea física → m08_asignacion. |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | m01_usuario.id (lógica) |
| `estado` |  | VARCHAR(12) | no | 'pendiente' | `IN ('pendiente', 'en_curso', 'completada')` |
| `bloques_vistos` |  | JSON | no | list() | sólo referencias que existen en `asignacion.bloques` |
| `ultimo_bloque_ref` | REF Biblioteca | VARCHAR(200) | no | '' | punto de reanudación |
| `posicion_seg` |  | INTEGER | sí |  |  |
| `avance_pct` |  | DECIMAL(5,2) | no | 0 | obligatorios atendidos / obligatorios; NO es una nota |
| `fuera_de_plazo` |  | BOOLEAN | no | false | completada o avanzada después de la fecha con plazo blando |
| `practica_intentos` |  | SMALLINT | no | 0 | resumen de sus prácticas (aciertos) |
| `practica_mejor` |  | SMALLINT | sí |  |  |
| `practica_ultima` |  | SMALLINT | sí |  |  |
| `practica_total` |  | SMALLINT | no | 0 |  |
| `abierta_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `ultimo_avance_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `completada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m08_tarea_estado: estado IN ('pendiente', 'en_curso', 'completada')`
- `ck_m08_tarea_completada_fechada: (NOT (estado = 'completada') OR completada_en IS NOT NULL)`
- `ck_m08_tarea_avance: (avance_pct >= '0' AND avance_pct <= '100')`
- `UNIQUE (asignacion_id, alumno_id)  [ux_m08_tarea]`

- Índices: (asignacion_id)  [m08_tarea_asignacion_id_9fd81f28] · (alumno_id, estado)  [ix_m08_tarea_alumno]

### MOD-010 · Evaluación y entrega

#### `m10_admision`  ·  ENTIDAD

BR-075, BR-076, FUN-116. Una tableta que no alcanza el nivel NO abre el intento sola: queda `en_espera` hasta que el PROFESOR la admite (en un nivel menor, con motivo) o la rechaza. El alumno no queda nunca excluido del examen por su dispositivo: el profesor puede admitirlo, bajar el nivel de todo el examen o cambiarle la tableta.

Clase `Admision` · app `evaluacion` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `asignacion_id` | **FK** → `m10_asignacion.id` | VARCHAR(36) | no |  | Llave foránea física → m10_asignacion. |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `alumno_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | no |  | m09_dispositivo (lógica) |
| `dispositivo_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `nivel_exigido` |  | VARCHAR(12) | no |  | `IN ('abierto', 'supervisado', 'controlado')` |
| `nivel_alcanzado` |  | VARCHAR(12) | no |  | `IN ('abierto', 'supervisado', 'controlado')` |
| `estado` |  | VARCHAR(12) | no | 'en_espera' | `IN ('en_espera', 'admitido', 'rechazado')` |
| `nivel_admitido` |  | VARCHAR(12) | no | '' |  |
| `motivo` |  | VARCHAR(200) | no | '' |  |
| `solicitada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `decidido_por` |  | VARCHAR(64) | no | '' |  |
| `decidido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m10_admision_estado: estado IN ('en_espera', 'admitido', 'rechazado')`
- `ck_m10_admision_decidida: (estado = 'en_espera' OR (NOT (decidido_por = '') AND decidido_en IS NOT NULL))`
- `ck_m10_admision_admitida: (NOT (estado = 'admitido') OR (NOT (nivel_admitido = '') AND NOT (motivo = '')))`
- `UNIQUE (asignacion_id, alumno_id, dispositivo_id)  [ux_m10_admision]`

- Índices: (asignacion_id)  [m10_admision_asignacion_id_07160965] · (asignacion_id, estado)  [ix_m10_admision_estado]

#### `m10_asignacion`  ·  ENTIDAD

ENT-011. Una evaluación (un `exam` de un curso de la biblioteca, con su versión) asignada a un grupo o a alumnos con su política de plazo, su nivel de control y su regla de reactivación. `alcance = grupo` alcanza a todos los alumnos ACTIVOS del grupo, también a los que entren después; `seleccion` sólo a los `destinatarios`. `nivel_declarado` es el mínimo con que se creó; `nivel_examen` es el vigente y sólo baja (FUN-118). `ajustes` copia los ajustes del examen que se usaron para asignar (estrategia, tolerancias, política de tiempo…): son evidencia y parámetros de armado, no contenido.

Clase `Asignacion` · app `evaluacion` · **PK** `id` · en el diseño v2: lanzamiento · evaluacion (la asignación formal, con plazo y nivel de control)

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `tipo` |  | VARCHAR(10) | no | 'examen' | `IN ('examen', 'actividad')` |
| `sesion_id` | **FK lógica** ⇢ `m07_sesion.id` | VARCHAR(36) | sí | '' | m07_sesion (lógica) si nació en una clase |
| `grupo_id` | **FK lógica** ⇢ `m01_grupo.id` | VARCHAR(36) | sí | '' | m01_grupo (lógica); vacío si son alumnos sueltos |
| `grupo_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `alcance` |  | VARCHAR(16) | no | 'grupo' | `IN ('grupo', 'seleccion')` |
| `destinatarios` |  | JSON | no | list() | lista de alumno_id; sólo con `seleccion` |
| `profesor_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `profesor_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `fuente_curso` |  | VARCHAR(16) | no | '' | biblioteca \| ejemplo |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | no |  | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `curso_version` |  | VARCHAR(32) | no | '' | la CONGELADA (INV-024) |
| `curso_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `leccion_ref` | REF Biblioteca | VARCHAR(120) | no | '' | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_ref` | REF Biblioteca | VARCHAR(120) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `objeto_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `titulo` |  | VARCHAR(250) | no |  |  |
| `estrategia` |  | VARCHAR(16) | no | '' | fixed \| random_balanced |
| `preguntas_por_alumno` |  | SMALLINT | no | 0 |  |
| `total_banco` |  | SMALLINT | no | 0 |  |
| `ajustes` |  | JSON | no | dict() |  |
| `nivel_declarado` |  | VARCHAR(12) | no |  | `IN ('abierto', 'supervisado', 'controlado')` |
| `nivel_examen` |  | VARCHAR(12) | no |  | `IN ('abierto', 'supervisado', 'controlado')` |
| `tiempo_modo` |  | VARCHAR(12) | no | 'biblioteca' | `IN ('biblioteca', 'fijo', 'sin_limite')` |
| `tiempo_limite_seg` |  | INTEGER | sí |  |  |
| `intentos_permitidos` |  | SMALLINT | sí | 1 | BR-072: uno; nulo = sin tope |
| `abre_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `limite_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `plazo` |  | VARCHAR(12) | no | 'blando' | `IN ('blando', 'endurecido')` |
| `gracia_ms` |  | INTEGER | no | 900000 | DEC-019 |
| `reactivacion` |  | VARCHAR(12) | no | 'profesor' | `IN ('profesor', 'automatica')` |
| `recursos` |  | JSON | no | list() | [{media_ref, rotulo}] habilitados en `supervisado` |
| `resultados` |  | VARCHAR(16) | no | 'tras_liberar' | `IN ('nunca', 'al_entregar', 'tras_liberar')` |
| `liberados_en` |  | BIGINT | sí |  | DEC-032: el alumno ve su nota desde aquí |
| `aprobacion_pct` |  | FLOAT | sí |  |  |
| `permite_retroceso` |  | BOOLEAN | no | true |  |
| `mezclar_opciones` |  | BOOLEAN | no | true |  |
| `estado` |  | VARCHAR(24) | no | 'borrador' | `IN ('borrador', 'programada', 'activa', 'activa_fuera_de_plazo', 'cerrada', 'archivada')` |
| `creada_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `cerrada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `archivada_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m10_asignacion_tipo: tipo IN ('examen', 'actividad')`
- `ck_m10_asignacion_alcance: alcance IN ('grupo', 'seleccion')`
- `ck_m10_asignacion_plazo: plazo IN ('blando', 'endurecido')`
- `ck_m10_asignacion_reactivacion: reactivacion IN ('profesor', 'automatica')`
- `ck_m10_asignacion_resultados: resultados IN ('nunca', 'al_entregar', 'tras_liberar')`
- `ck_m10_asignacion_tiempo_modo: tiempo_modo IN ('biblioteca', 'fijo', 'sin_limite')`
- `ck_m10_asignacion_estado: estado IN ('borrador', 'programada', 'activa', 'activa_fuera_de_plazo', 'cerrada', 'archivada')`
- `ck_m10_asignacion_nivel: (nivel_declarado IN ('abierto', 'supervisado', 'controlado') AND nivel_examen IN ('abierto', 'supervisado', 'controlado'))`
- `ck_m10_asignacion_nivel_no_sube: (nivel_declarado = 'controlado' OR (nivel_declarado = 'supervisado' AND nivel_examen IN ('supervisado', 'abierto')) OR (nivel_declarado = 'abierto' AND nivel_examen = 'abierto'))`
- `ck_m10_asignacion_cierre_fechado: (NOT (estado IN ('cerrada', 'archivada')) OR cerrada_en IS NOT NULL)`
- `ck_m10_asignacion_archivo_fechado: (NOT (estado = 'archivada') OR archivada_en IS NOT NULL)`
- `ck_m10_asignacion_vigencia: (abre_en IS NULL OR limite_en IS NULL OR limite_en >= (abre_en))`
- `ck_m10_asignacion_gracia: gracia_ms >= 0`
- `ck_m10_asignacion_intentos: (intentos_permitidos IS NULL OR intentos_permitidos >= 1)`
- `ck_m10_asignacion_tiempo_fijo: ((tiempo_modo = 'fijo' AND tiempo_limite_seg >= 1) OR (NOT (tiempo_modo = 'fijo') AND tiempo_limite_seg IS NULL))`

- Índices: (grupo_id, estado)  [ix_m10_asignacion_grupo] · (sesion_id)  [ix_m10_asignacion_sesion] · (estado, limite_en)  [ix_m10_asignacion_plazo]

#### `m10_evento_salida`  ·  COLA · outbox

Transactional Outbox de MOD-010 (`evaluacion.*.v1`). Se escribe en la misma transacción que el hecho (DEC-007). Nunca lleva el contenido de una respuesta (BR-127). Cuando exista MOD-015 (m15_evento) las colas de todos los módulos se unifican allí.

Clase `EventoSalida` · app `evaluacion` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(64) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [ix_m10_outbox]

#### `m10_incidente`  ·  REGISTRO · sólo inserción

CAP-066, FUN-117, BR-077. SÓLO INSERCIÓN: no hay ruta ni caso de uso que actualice o borre una fila. Un incidente alimenta el expediente de integridad y NUNCA modifica el estado del intento. `ref_cliente` es la clave de idempotencia que manda la tableta: reenviar su cola no duplica incidentes (INV-005).

Clase `Incidente` · app `evaluacion` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `intento_id` | **FK** → `m10_intento_formal.id` | VARCHAR(36) | no |  | Llave foránea física → m10_intento_formal. |
| `tipo` |  | VARCHAR(32) | no |  |  |
| `severidad` |  | VARCHAR(12) | no |  | `IN ('informativa', 'atencion', 'alta')` |
| `origen` |  | VARCHAR(8) | no |  | `IN ('tableta', 'nodo', 'profesor')` |
| `ocurrido_en` |  | BIGINT | no | ahora_ms() | reloj del nodo |
| `reportado_en_tableta` |  | BIGINT | sí |  | hora cruda del aparato (BR-062: dato adicional) |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m09_dispositivo: se guarda la llave, el motor no la impone. |
| `detalle` |  | JSON | no | dict() |  |
| `resolucion` |  | VARCHAR(24) | no | 'registrado' |  |
| `ref_cliente` |  | VARCHAR(64) | no | '' |  |

Restricciones del motor:

- `ck_m10_incidente_severidad: severidad IN ('informativa', 'atencion', 'alta')`
- `ck_m10_incidente_origen: origen IN ('tableta', 'nodo', 'profesor')`
- `UNIQUE (intento_id, ref_cliente) WHERE NOT (ref_cliente = '')  [ux_m10_incidente_cliente]`

- Índices: (intento_id)  [m10_incidente_intento_id_d6ed272a] · (intento_id, ocurrido_en)  [ix_m10_incidente_intf]

#### `m10_intento_formal`  ·  ENTIDAD

ENT-012, el agregado más crítico. Las respuestas por pregunta viven DENTRO del intento (decisión del CTO del 2026-09-24): una por elemento de `respuestas`. INV-013 (intento + pregunta + sesión + secuencia) no se puede expresar como restricción sobre una lista JSON: se valida en la aplicación, dentro de la transacción, y se prueba con reenvíos. `armado` guarda sólo REFERENCIAS (el examen de este alumno); su texto se vuelve a pedir a la biblioteca con la misma `semilla`. El reloj es del nodo: `reloj_desde` es NULO mientras está congelado.

Clase `Intento` · app `evaluacion` · **PK** `id` · en el diseño v2: intento · evaluacion (el intento formal, con reloj, pausas y calificación)

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no |  | Identificador de texto de la fila (CV-02). |
| `asignacion_id` | **FK** → `m10_asignacion.id` | VARCHAR(36) | no |  | Llave foránea física → m10_asignacion. |
| `alumno_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `alumno_rotulo` |  | VARCHAR(120) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `numero` |  | SMALLINT | no | 1 |  |
| `estado` |  | VARCHAR(24) | no | 'no_iniciado' | `IN ('no_iniciado', 'en_curso', 'pausado_desconexion', 'restaurando', 'en_curso_fuera_de_plazo', 'entregado', 'en_revision_docente', 'calificado', 'anulado')` |
| `nivel_efectivo` |  | VARCHAR(12) | no |  | `IN ('abierto', 'supervisado', 'controlado')` |
| `bloqueo` |  | JSON | no | dict() | último informe de la tableta (D-12) |
| `dispositivo_id` | **FK lógica** ⇢ `m09_dispositivo.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m09_dispositivo: se guarda la llave, el motor no la impone. |
| `sesion_ref` | **FK lógica** ⇢ `m07_sesion.id` | VARCHAR(36) | sí | '' | Referencia lógica (CV-08) → m07_sesion: se guarda la llave, el motor no la impone. |
| `sesiones` |  | JSON | no | list() | [{sesion_ref, orden, dispositivo_id, desde, hasta}] |
| `semilla` |  | VARCHAR(160) | no | '' |  |
| `curso_version` |  | VARCHAR(32) | no | '' | congelada al abrir (INV-024) |
| `armado` |  | JSON | no | list() | [pregunta_ref] en el orden del alumno |
| `armado_meta` |  | JSON | no | dict() |  |
| `tiempo_limite_seg` |  | INTEGER | sí |  |  |
| `consumido_ms` |  | BIGINT | no | 0 |  |
| `reloj_desde` |  | BIGINT | sí |  |  |
| `pausas` |  | JSON | no | list() | [{desde, hasta, causa, estado_previo, reactivado_por}] |
| `ultimo_latido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `pregunta_actual` |  | VARCHAR(120) | no | '' |  |
| `respuestas` |  | JSON | no | list() |  |
| `secuencia_maxima` |  | INTEGER | no | 0 |  |
| `puntaje` |  | FLOAT | sí |  |  |
| `puntaje_maximo` |  | FLOAT | sí |  |  |
| `porcentaje` |  | FLOAT | sí |  | escala interna 0–100 (DEC-003) |
| `sin_calificar` |  | SMALLINT | no | 0 |  |
| `requiere_revision` |  | BOOLEAN | no | false |  |
| `calificacion_pendiente` |  | BOOLEAN | no | false | la biblioteca no estaba al entregar |
| `calificado_por` |  | VARCHAR(64) | no | '' | INV-019: `sistema` o la persona que publicó |
| `calificado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `fuera_de_plazo` |  | BOOLEAN | no | false |  |
| `origen_entrega` |  | VARCHAR(12) | no | '' |  |
| `envio_tardio` |  | VARCHAR(20) | no | '' |  |
| `respuestas_pendientes` |  | JSON | no | list() | lo recibido fuera de la gracia, a la espera del profesor |
| `decision_envio` |  | JSON | no | dict() |  |
| `anulado_por` |  | VARCHAR(64) | no | '' |  |
| `motivo_anulacion` |  | VARCHAR(300) | no | '' |  |
| `anulado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `iniciado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `entregado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m10_intf_estado: estado IN ('no_iniciado', 'en_curso', 'pausado_desconexion', 'restaurando', 'en_curso_fuera_de_plazo', 'entregado', 'en_revision_docente', 'calificado', 'anulado')`
- `ck_m10_intf_numero_consumido: (numero >= 1 AND consumido_ms >= 0)`
- `ck_m10_intf_anulado_humano: (NOT (estado = 'anulado') OR (NOT (anulado_por = '') AND NOT (anulado_por = 'sistema') AND NOT (motivo_anulacion = '') AND anulado_en IS NOT NULL))`
- `ck_m10_intf_entrega_fechada: (NOT (estado IN ('entregado', 'en_revision_docente', 'calificado')) OR entregado_en IS NOT NULL)`
- `ck_m10_intf_reloj_solo_corriendo: (reloj_desde IS NULL OR estado IN ('en_curso', 'en_curso_fuera_de_plazo'))`
- `ck_m10_intf_calificado_con_evaluador: (NOT (estado = 'calificado') OR (porcentaje IS NOT NULL AND NOT (calificado_por = '')))`
- `ck_m10_intf_envio_tardio: envio_tardio IN ('', 'pendiente_decision', 'aceptado', 'descartado')`
- `UNIQUE (asignacion_id, alumno_id) WHERE estado IN ('no_iniciado', 'en_curso', 'pausado_desconexion', 'restaurando', 'en_curso_fuera_de_plazo')  [ux_m10_intf_vivo]`
- `UNIQUE (asignacion_id, alumno_id, numero)  [ux_m10_intf_numero]`

- Índices: (asignacion_id)  [m10_intento_formal_asignacion_id_a6c1ede9] · (asignacion_id, estado)  [ix_m10_intf_asignacion] · (alumno_id, estado)  [ix_m10_intf_alumno] · (dispositivo_id, estado)  [ix_m10_intf_dispositivo]

### MOD-005 · Expediente del estudiante

#### `m05_apertura_material`  ·  REGISTRO · sólo inserción

El «visor del contenido»: qué material abrió cada persona, cuándo y por cuánto tiempo. Es el registro de uso del que se deriva el progreso. Se guarda la referencia y la versión del elemento, nunca su contenido.

Clase `AperturaMaterial` · app `expediente` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | no |  | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `leccion_codigo` | REF Biblioteca | VARCHAR(120) | no | '' |  |
| `elemento_ref` | REF Biblioteca | VARCHAR(200) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `version_elemento` |  | VARCHAR(32) | no | '' |  |
| `tipo` |  | VARCHAR(32) | no | '' |  |
| `elemento_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `dispositivo` |  | VARCHAR(64) | no | '' |  |
| `origen` |  | VARCHAR(16) | no | 'student' |  |
| `abierto_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `cerrado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `segundos` |  | INTEGER | sí |  |  |
| `progreso_pct` |  | INTEGER | sí |  |  |

Restricciones del motor:

- `ck_m05_apertura_pct: (progreso_pct IS NULL OR (progreso_pct >= 0 AND progreso_pct <= 100))`

- Índices: (curso_ref, persona_id)  [m05_apertur_curso_r_933520_idx] · (elemento_ref)  [m05_apertur_element_e61700_idx]

#### `m05_disponibilidad_observada`  ·  ENTIDAD

La única concesión del artículo 14: memoria de la última revisión, para poder explicar una ausencia con la biblioteca cerrada. Guarda fechas, no contenido.

Clase `DisponibilidadObservada` · app `expediente` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `referencia` |  | VARCHAR(200) | no |  |  |
| `clase` |  | VARCHAR(16) | no | 'curso' |  |
| `disponible_ultima_revision` |  | BOOLEAN | no | true |  |
| `revisado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `desaparecido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m05_disp_ausencia_con_fecha: (disponible_ultima_revision OR desaparecido_en IS NOT NULL)`
- `UNIQUE (referencia, clase)  [uq_m05_disponibilidad]`

#### `m05_inscripcion`  ·  REL · asociativa

Quién está en qué curso. Referencia estable de curso + identificador externo de persona.

Clase `Inscripcion` · app `expediente` · **PK** `id` · en el diseño v2: configuracion (aproximada: la misma pareja usuario × curso, sin `ajustes` ni `orden`)

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | no |  | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `persona_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `curso_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `inscrito_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `retirado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_por` |  | VARCHAR(64) | no | '' | Quién lo creó: identificador de usuario o del aula (texto, auditoría). |

Restricciones del motor:

- `ck_m05_inscripcion_retiro_posterior: (retirado_en IS NULL OR retirado_en >= (inscrito_en))`
- `UNIQUE (curso_ref, persona_id)  [uq_m05_inscripcion]`

- Índices: (persona_id)  [m05_inscrip_persona_fc0a98_idx] · (curso_ref)  [m05_inscrip_curso_r_39fa8e_idx]

#### `m05_progreso_leccion`  ·  ENTIDAD

Avance de una persona en una sección del curso (identidad lógica = código de taxonomía).

Clase `ProgresoLeccion` · app `expediente` · **PK** `id` · en el diseño v2: progreso

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | no |  | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `leccion_codigo` | REF Biblioteca | VARCHAR(120) | no |  |  |
| `leccion_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `porcentaje` |  | DECIMAL(5,2) | no | 0 |  |
| `estado` |  | VARCHAR(16) | no | 'no_iniciada' | `IN ('no_iniciada', 'en_curso', 'completada')` |
| `version_observada` |  | VARCHAR(32) | no | '' |  |
| `iniciado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `actualizado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `completado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m05_progreso_rango: (porcentaje >= '0' AND porcentaje <= '100')`
- `ck_m05_progreso_completada_sella: (NOT (estado = 'completada') OR (porcentaje = '100' AND completado_en IS NOT NULL))`
- `UNIQUE (curso_ref, persona_id, leccion_codigo)  [uq_m05_progreso]`

#### `m10_intento`  ·  ENTIDAD

Un intento de evaluación. Registro autoritativo de la nota.

Clase `Intento` · app `expediente` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `evaluacion_ref` | REF Biblioteca | VARCHAR(200) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `curso_ref` | **FK lógica** ⇢ `biblioteca_curso.curso_ref` | VARCHAR(200) | sí | '' | Referencia lógica (CV-08) → biblioteca_curso: se guarda la llave, el motor no la impone. |
| `leccion_codigo` | REF Biblioteca | VARCHAR(120) | no | '' |  |
| `version_observada` |  | VARCHAR(32) | no | '' |  |
| `evaluacion_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `persona_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | no |  | Referencia lógica (CV-08) → m01_usuario: se guarda la llave, el motor no la impone. |
| `persona_rotulo` |  | VARCHAR(250) | no | '' | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `dispositivo` |  | VARCHAR(64) | no | '' |  |
| `pregunta_actual` |  | INTEGER | no | 0 |  |
| `total_preguntas` |  | INTEGER | no | 0 |  |
| `estado` |  | VARCHAR(24) | no | 'abierto' | `IN ('abierto', 'finalizado', 'pendiente_correccion')` |
| `puntaje` |  | DECIMAL(6,2) | sí |  |  |
| `aciertos` |  | INTEGER | no | 0 |  |
| `pendientes` |  | INTEGER | no | 0 |  |
| `iniciado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `finalizado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m10_intento_cierre_fechado: (estado = 'abierto' OR finalizado_en IS NOT NULL)`
- `ck_m10_intento_puntaje_solo_cerrado: (puntaje IS NULL OR NOT (estado = 'abierto'))`
- `UNIQUE (evaluacion_ref, persona_id, dispositivo) WHERE estado = 'abierto'  [uq_m10_intento_abierto]`

- Índices: (curso_ref, persona_id)  [m10_intento_curso_r_6d426b_idx]

#### `m10_intento_pregunta`  ·  ENTIDAD

Qué se le preguntó a quién y en qué orden. No hay columna para la clave, y no es un olvido.

Clase `IntentoPregunta` · app `expediente` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `intento_id` | **FK** → `m10_intento.id` | BIGINT | no |  | Llave foránea física → m10_intento. |
| `pregunta_ref` | REF Biblioteca | VARCHAR(200) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `elemento_ref` | REF Biblioteca | VARCHAR(200) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `version_elemento` |  | VARCHAR(32) | no | '' |  |
| `orden` |  | INTEGER | no |  |  |
| `peso` |  | DECIMAL(6,2) | no | 1 |  |
| `corregible` |  | BOOLEAN | no | true |  |

Restricciones del motor:

- `UNIQUE (intento_id, pregunta_ref)  [uq_m10_ip_pregunta]`
- `UNIQUE (intento_id, orden)  [uq_m10_ip_orden]`

- Índices: (intento_id)  [m10_intento_pregunta_intento_id_a632ec2c]

#### `m10_intento_respuesta`  ·  ENTIDAD

Lo que la persona contestó y el veredicto que devolvió la biblioteca. Nunca la clave.

Clase `IntentoRespuesta` · app `expediente` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `intento_id` | **FK** → `m10_intento.id` | BIGINT | no |  | Llave foránea física → m10_intento. |
| `pregunta_ref` | REF Biblioteca | VARCHAR(200) | no |  | Referencia (CV-08) a un elemento de AVACOM Biblioteca; nunca su contenido. |
| `respuesta` |  | TEXT | no | '' |  |
| `acierta` |  | BOOLEAN | sí |  |  |
| `corregido_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `retroalimentacion_rotulo` |  | TEXT | sí |  | Rótulo visto en ese momento: evidencia histórica que no se refresca. |
| `respondido_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `UNIQUE (intento_id, pregunta_ref)  [uq_m10_ir_pregunta]`

- Índices: (intento_id)  [m10_intento_respuesta_intento_id_2c301d43]

### MOD-019 · Auditoría y logs

#### `m19_bitacora`  ·  REGISTRO · sólo inserción

`bitacora` del v2 (→ m19_bitacora). Sólo inserción. Las columnas canónicas participan en la huella.

Clase `Bitacora` · app `audit` · **PK** `id` · en el diseño v2: bitacora

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no | _nuevo_id() | Identificador de texto de la fila (CV-02). |
| `secuencia` | UQ | BIGINT | no |  |  |
| `huella_previa` |  | VARCHAR(64) | no |  |  |
| `huella` |  | VARCHAR(64) | no |  |  |
| `ocurrido_en` |  | BIGINT | no |  | reloj del NODO, nunca el de la tableta |
| `usuario_id` | **FK lógica** ⇢ `m01_usuario.id` | VARCHAR(64) | sí |  | referencia lógica a m01_usuario (CV-08); NULL = sistema |
| `actor_tipo` |  | VARCHAR(12) | no | 'sistema' |  |
| `roles_activos` |  | JSON | sí |  |  |
| `modulo` |  | VARCHAR(24) | no |  | sustituye a modulo_app_id hasta que exista modulo_app |
| `accion` |  | VARCHAR(64) | no |  |  |
| `resultado` |  | VARCHAR(16) | no | 'ok' |  |
| `objeto_tabla` |  | VARCHAR(64) | sí |  |  |
| `objeto_id` |  | VARCHAR(64) | sí |  |  |
| `valor_anterior` |  | JSON | sí |  | sólo los campos que cambian |
| `valor_nuevo` |  | JSON | sí |  |  |
| `motivo` |  | VARCHAR(250) | sí |  |  |
| `origen` |  | VARCHAR(12) | no |  |  |
| `dispositivo_id` | **FK** → `m09_dispositivo.id` | VARCHAR(36) | sí |  | Llave foránea física → m09_dispositivo. |
| `correlacion_id` |  | VARCHAR(64) | sí |  |  |
| `evento_id` |  | VARCHAR(64) | sí |  | el evento de la cola del que derivó (019-09) |
| `tramo_id` | **FK** → `m19_bitacora_tramo.id` | VARCHAR(36) | no |  | Llave foránea física → m19_bitacora_tramo. |

Restricciones del motor:

- `ck_m19_bit_resultado: resultado IN ('ok', 'denegado', 'fallido')`
- `ck_m19_bit_origen: origen IN ('api', 'ws', 'sistema', 'instalador', 'migracion', 'prueba')`
- `ck_m19_bit_actor_tipo: actor_tipo IN ('usuario', 'declarado', 'sistema', 'dispositivo', 'instalador')`
- `ck_m19_bit_usuario_con_id: (NOT (actor_tipo = 'usuario') OR usuario_id IS NOT NULL)`
- `ck_m19_bit_secuencia: secuencia >= 1`

- Índices: (dispositivo_id)  [m19_bitacora_dispositivo_id_6043fc6c] · (tramo_id)  [m19_bitacora_tramo_id_515fc4bb] · (usuario_id, ocurrido_en)  [ix_m19_bit_usuario] · (modulo, ocurrido_en)  [ix_m19_bit_modulo] · (resultado, ocurrido_en)  [ix_m19_bit_resultado] · (objeto_tabla, objeto_id, ocurrido_en)  [ix_m19_bit_objeto] · (accion, ocurrido_en)  [ix_m19_bit_accion] · (dispositivo_id, ocurrido_en)  [ix_m19_bit_dispositivo] · (correlacion_id)  [ix_m19_bit_corr]
- Trigger m19_bitacora_no_update: el motor aborta UPDATE y DELETE (inmutabilidad en la base).
- Trigger m19_bitacora_no_delete: el motor aborta UPDATE y DELETE (inmutabilidad en la base).

#### `m19_bitacora_tramo`  ·  ENTIDAD

BitacoraTramo(id, desde_secuencia, hasta_secuencia, huella_cierre, estado, abierta, verificado_en, verificado_hasta, salto_en_secuencia, salto_causa, exportado_en, firma, archivo, rotado_en, creado_en)

Clase `BitacoraTramo` · app `audit` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | VARCHAR(36) | no | _nuevo_id() | Identificador de texto de la fila (CV-02). |
| `desde_secuencia` |  | BIGINT | no |  |  |
| `hasta_secuencia` |  | BIGINT | no |  | cabeza mientras está activa; desde-1 si aún no tiene asientos |
| `huella_cierre` |  | VARCHAR(64) | no |  | huella del último asiento; al rotar, huella_previa del siguiente tramo |
| `estado` |  | VARCHAR(12) | no | 'activa' |  |
| `abierta` |  | BOOLEAN | no | true | el tramo que recibe asientos; False al rotar (índice único parcial) |
| `verificado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `verificado_hasta` |  | BIGINT | sí |  | última secuencia verificada (verificación por bloques) |
| `salto_en_secuencia` |  | BIGINT | sí |  |  |
| `salto_causa` |  | VARCHAR(32) | no | '' |  |
| `exportado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `firma` |  | TEXT | sí |  |  |
| `archivo` |  | VARCHAR(260) | sí |  |  |
| `rotado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |

Restricciones del motor:

- `ck_m19_tramo_rango: hasta_secuencia >= (desde_secuencia - 1)`
- `ck_m19_tramo_estado: estado IN ('activa', 'verificada', 'con_salto', 'rotada')`
- `ck_m19_tramo_desde: desde_secuencia >= 1`
- `UNIQUE (abierta) WHERE abierta  [uq_m19_tramo_abierto]`

#### `m19_evento_salida`  ·  COLA · outbox

Transactional Outbox de MOD-019 (`auditoria.*.v1`): se escribe en la misma transacción que el hecho. Cuando exista MOD-015 (m15_evento) todas las colas se unifican allí.

Clase `EventoSalida` · app `audit` · **PK** `id` · en el diseño v2: _sin equivalente (tabla agregada)_

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `id` | **PK** | BIGINT | no |  | Identificador de texto de la fila (CV-02). |
| `agregado_tipo` |  | VARCHAR(32) | no |  |  |
| `agregado_id` |  | VARCHAR(36) | no |  |  |
| `tipo_evento` |  | VARCHAR(64) | no |  |  |
| `carga` |  | JSON | no | dict() |  |
| `creado_en` |  | BIGINT | no | ahora_ms() | Instante en milisegundos del reloj del nodo (CV-03). |
| `publicado_en` |  | BIGINT | sí |  | Instante en milisegundos del reloj del nodo (CV-03). |
| `intentos` |  | SMALLINT | no | 0 |  |

- Índices: (publicado_en, creado_en)  [ix_m19_outbox]

### Externo · AVACOM Biblioteca

#### `biblioteca_curso`  ·  EXTERNA

No es una tabla del LMS: es el curso que entrega AVACOM Biblioteca por su API. El LMS no lo guarda (artículo 14); sólo conserva su referencia `curso_ref` en las tablas que la usan y, como evidencia, su rótulo. Se dibuja para que se vea de dónde viene cada `curso_ref`.

| Campo | Llave | Tipo | Null | Default | Descripción · restricción |
|---|---|---|:---:|---|---|
| `curso_ref` | **PK** | VARCHAR(200) | no |  | Clave estable del paquete de curso en la biblioteca. |

## 6. Hallazgos del cruce

1. **La integridad entre módulos es lógica.** Las 36 referencias entre módulos (por ejemplo `m07_participante.persona_id → m01_usuario.id`) no son FK del motor: cada módulo es dueño de sus tablas y valida por un puerto (`Identidad`, `Dispositivos`, `Evaluacion`…). Pasarán a FK físicas «cuando los módulos compartan un motor definitivo» (docstring de `classroom_engine/models.py`). Hasta entonces una fila puede apuntar a una llave que ya no exista sin que el motor lo impida.
2. **Hay cuatro «intentos» donde el v2 tenía uno.** `m07_intento` (en clase), `m08_practica` (modo estudio, sólo modo `estudio`), `m10_intento_formal` (evaluación formal) y `m10_intento` + `m10_intento_pregunta` + `m10_intento_respuesta` (expediente, MOD-005). Este último conserva las respuestas en una tabla aparte, contra la decisión del CTO del 2026-09-24 de dejarlas dentro del intento (`respuestas`, JSON), que sí siguen las otras tres.
3. **Dos «asignaciones».** `m08_asignacion` (lección con fecha límite) y `m10_asignacion` (evaluación con plazo, nivel de control y reactivación) comparten alcance (`grupo`/`seleccion`), destinatarios, plazo y gracia; `m07_distribucion.asignacion_ref` enlaza la segunda con el lanzamiento en clase. `m08_*` y `m07_intento` se declaran provisionales en su código hasta que MOD-010 absorba lo suyo.
4. **Las colas de salida son seis tablas con el mismo esquema** (`m01`, `m07`, `m08`, `m09`, `m10` y `m19` `_evento_salida`) a la espera de MOD-015 (`m15_evento`).
5. **Tiempo e identificadores difieren del v2.** El v2 usa UUID `BINARY(16)` y fechas ISO 8601; lo implementado usa texto de 36 caracteres y milisegundos `BIGINT` (CV-02, CV-03). Es la tensión que ya estaba señalada en el visor.
6. **`nodo_maestro_id` no existe** en `m09_dispositivo`: el v2 la tenía como autorreferencia; el nodo del que depende cada tableta no se modela todavía.
7. **`m19_auditoria` ya no es tabla**: es una vista de sólo lectura sobre `m19_bitacora` (`managed = False` en `expediente/models.py`); no figura en este inventario.
8. **Tablas sin ninguna relación:** `m01_evento_salida`, `m09_evento_salida`, `m07_evento_salida`, `m08_evento_salida`, `m10_evento_salida`, `m05_disponibilidad_observada`, `m19_evento_salida` (las colas de salida y `m05_disponibilidad_observada`, memoria de disponibilidad que guarda fechas, no contenido).

## 7. Cómo se regenera

```powershell
backend\.venv\Scripts\python.exe specs\analisis\fuentes\extraer_modelo.py   # models.py + esquema migrado → modelo-implementado.json
python specs\analisis\fuentes\insertar_modelo.py                              # inserta el JSON en el visor index.html
python specs\analisis\fuentes\documento_modelo.py                             # escribe este documento
```

El visor abre el modelo implementado por defecto y el diseño v2 con `index.html#modelo=v2`; `#relaciones` abre la lista completa de relaciones.

