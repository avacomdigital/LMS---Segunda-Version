# 06 · Evaluation & Delivery Engine (MOD-010) · Backend y API `/api/evaluacion/`

| Campo | Valor |
|---|---|
| Estado | **Contrato de diseño** (2026-09-30). Lo implementa `backend/evaluacion/` (Django/DRF), con la misma arquitectura hexagonal que `acceso/`, `classroom_engine/`, `modo_estudio/` y `audit/`. Lo construido y cómo se comprobó está en §10. |
| Módulo | **MOD-010 · Evaluation & Delivery Engine** (DOM-006). Funciones FUN-103…FUN-118, eventos `evaluacion.*.v1`, permisos `assessment.*`. |
| Modelo | [modelado-datos.md](modelado-datos.md): `m10_asignacion`, `m10_admision`, `m10_intento_formal`, `m10_incidente`, `m10_evento_salida`. |
| Cliente | [frontend.md](frontend.md): `Avacom.Lms.Core/Evaluacion/` (cliente `EvaluacionApi`, reglas de bloqueo), Student (antesala, examen, kiosco) y OPS (aplicar, panel, reactivar). |
| Bloqueo de la tableta | [kiosk.md](kiosk.md). El nodo **decide** el plan de bloqueo (§5.5); la tableta lo **ejecuta** y lo **informa** (`POST /intentos/{id}/bloqueo/`). |

---

## 1 · Arquitectura

```
backend/evaluacion/
├── models.py                       m10_* (§4 del modelo)
├── servicios.py                    interfaz para OTROS módulos (cuántos intentos vivos, por persona)
├── dominio/                        reglas puras; NO importan Django ni DRF
│   ├── catalogos.py                estados, niveles, tipos de incidente, eventos, permisos, textos obligatorios
│   ├── errores.py                  ErrorEvaluacion y sus hijos (cada uno lleva su código HTTP)
│   ├── asignacion.py               máquina de estados y plazos
│   ├── intento.py                  máquina de estados, reloj, entrega
│   ├── armado.py                   el examen de cada alumno (fixed · random_balanced, determinista)
│   ├── bloqueo.py                  niveles, capacidad, admisión y plan de bloqueo
│   └── respuestas.py               fusión idempotente, sesiones, totales
├── aplicacion/                     casos de uso; NO importan Django ni DRF
│   ├── puertos.py                  Contenido · Identidad · Dispositivos · Aula · Reloj · Auditoria · Outbox · TiempoReal · Autorizacion
│   ├── base.py                     Servicios, Contexto del alumno, utilidades
│   ├── asignaciones.py             FUN-105…108, 118 y el cierre
│   ├── admisiones.py               FUN-116 (BR-075, BR-076)
│   ├── intentos.py                 FUN-109, 114, reactivar, cierre forzado, anular
│   ├── respuestas.py               FUN-110, 111 y el latido
│   ├── incidentes.py               FUN-117 y el informe de bloqueo
│   ├── calificacion.py             FUN-112, 113, revisión docente, envío tardío, resultados
│   ├── panel.py                    PAN-005/121, PAN-062, elegibilidad, «mias», antesala
│   └── barrido.py                  lo que el nodo hace solo: pausar, entregar por tiempo, cerrar por plazo, restaurar
├── infraestructura/                adaptadores: ORM, biblioteca, otros módulos, canal de tiempo real
│   ├── contenedor.py               composition root (qué adaptador va con qué puerto)
│   ├── unidad_trabajo.py           una transacción por caso de uso
│   ├── repositorios.py             ORM → dicts planos
│   ├── contenido.py                el examen desde la fuente de cursos del aula (pool · questions · evaluate)
│   ├── identidad.py · dispositivos.py · aula.py · autorizacion.py · tiempo_real.py
│   └── programador.py              hilo del nodo (cada 5 s)
├── interfaces/                     DRF
│   ├── serializers.py · views.py · urls.py
└── tests/
```

* **Regla de oro (artículo 14).** Ninguna tabla ni columna guarda contenido del curso ni claves. La prueba `test_el_esquema_es_solo_de_evaluacion_sin_curso_ni_claves` falla si aparece una tabla `m10_*` con `curso`, `pregunta`, `opcion`… o una columna `clave`, `correcta` o `solucion`.
* **Dominio y aplicación no importan Django.** `test_arquitectura` lo comprueba y las vistas no tocan el ORM.
* **Una transacción por caso de uso.** El hecho, su asiento de auditoría y su evento de salida se confirman juntos (DEC-007). El aviso de tiempo real sale al confirmar (`transaction.on_commit`).
* **Escritor único.** MOD-010 no escribe `m01_*`, `m07_*`, `m08_*` ni `m09_*`: pide por la interfaz de su dueño (`device_manager.servicios`, `audit.servicios`, los casos de uso del aula).

---

## 2 · Quién llama

### 2.1 · Identidad (D-19)

| Quién | Cómo se identifica | Notas |
|---|---|---|
| **Profesor / administración** | JWT de `acceso` (rol efectivo) o, sin sesión (Q-34 abierta), `actor` y `actor_rotulo` declarados en el cuerpo o en `?actor=` | Con sesión, el permiso `assessment.*` lo concede el rol y, sobre una asignación concreta, hay que ser su profesor titular o la administración (nivel 3). Sin sesión se permite, como en el aula. |
| **Alumno en su tableta** | JWT o, sin sesión, `alumno_id` **declarado** + `dispositivo` (la huella `identificador_hw`) en el cuerpo o en `?dispositivo=&alumno_id=` | Debe existir, estar activo y **alcanzarle** la asignación (inscrito en el grupo o entre los destinatarios). La tableta debe estar registrada, activa y **no bloqueada** (MOD-009). Una asignación ajena responde **404** (no se revela). |
| **El nodo** | `actor = sistema` | Lo que hace el programador (§6.9). **Nunca** anula (INV-018). |

Errores de identidad: `falta_dispositivo` (400) · `falta_alumno` (400) · `sin_permiso` (403; con `motivo = alumno_desconocido` si el alumno no existe) · `dispositivo_bloqueado` / `dispositivo_inactivo` (403) · `no_instalado` (409, el nodo aún no tiene organización).

### 2.2 · Permisos

Los evalúa `AutorizacionEvaluacion` con la política de `acceso` (alcance concedido por el rol) y, para un profesor sobre una asignación, su titularidad. Los 16 permisos y su reparto por rol están en [modelado-datos.md](modelado-datos.md) §10.3; los siembra la migración `acceso/0009_permisos_evaluacion` y las plantillas de instalación nuevas.

---

## 3 · Funciones del Maestro → casos de uso → rutas

| Función | Caso de uso (`aplicacion/…`) | Ruta | Evento | Permiso |
|---|---|---|---|---|
| FUN-103 Crear una evaluación con banco | — **trasladada a la biblioteca** | `POST /evaluaciones/` → 409 `administracion_no_permitida` | (no se publica) | `assessment.create` |
| FUN-104 Añadir un reactivo | — **trasladada a la biblioteca** | `POST /reactivos/` → 409 `administracion_no_permitida` | (no se publica) | `assessment.item.create` |
| FUN-105 Definir el nivel mínimo | `DefinirNivel` (`asignaciones`) | `POST /asignaciones/{id}/nivel/` y, al crear, `nivel_examen` | `nivel_examen.definido` | `assessment.exam_mode.set` |
| FUN-106 Configurar la fecha límite blanda | `ConfigurarPlazo` | `PATCH /asignaciones/{id}/plazo/` y, al crear, `limite_en` | `fecha_limite.configurada` | `assessment.deadline.set` |
| FUN-107 Endurecer la fecha límite | `EndurecerPlazo` | `POST /asignaciones/{id}/endurecer/` | `fecha_limite.endurecida` | `assessment.deadline.enforce` |
| FUN-108 Asignar a un grupo o a alumnos | `CrearAsignacion`, `IniciarAsignacion` | `POST /asignaciones/` · `POST /asignaciones/{id}/iniciar/` | `asignada` | `assessment.assign` |
| FUN-109 Abrir un intento | `AbrirIntento` (`intentos`) | `POST /asignaciones/{id}/intentos/` | `intento_abierto` | `assessment.attempt.start` |
| FUN-110 Registrar una respuesta con secuencia | `EnviarRespuestas` (`respuestas`) | `POST /intentos/{id}/respuestas/` | `respuesta_registrada` | `assessment.answer.submit` |
| FUN-111 Deduplicar una respuesta reenviada | (dentro de `EnviarRespuestas`) | la misma | `respuesta_deduplicada` | — |
| FUN-112 Calificar de forma automática | `Calificar` (`calificacion`) | al entregar · `POST /intentos/{id}/recalificar/` | `autocalificacion.completada` | — |
| FUN-113 Enviar a revisión docente | (dentro de `Calificar`) | — | `revision.solicitada` | — |
| FUN-114 Entregar un intento y cerrarlo | `EntregarIntento` | `POST /intentos/{id}/entregar/` | `intento_entregado` | `assessment.attempt.submit` |
| FUN-115 Marcar un intento como fuera de plazo | `Barrido` y `EntregarIntento` | (automático) | `intento_fuera_de_plazo` | — |
| FUN-116 Admitir un dispositivo por debajo del nivel | `DecidirAdmision` (`admisiones`) | `POST /asignaciones/{id}/admisiones/{aid}/decidir/` | `dispositivo_admitido_bajo_nivel` | `assessment.exam_mode.override` |
| FUN-117 Registrar un incidente sin invalidar | `RegistrarIncidentes` (`incidentes`) | `POST /intentos/{id}/incidentes/` (tableta) y el nodo | `incidente_registrado` | — |
| FUN-118 Degradar el nivel en curso | `DegradarNivel` | `POST /asignaciones/{id}/degradar/` | `nivel_examen_degradado` | `assessment.exam_mode.downgrade` |
| PAN-061 Reactivar un intento suspendido | `ReactivarIntento`, `ReactivarTodos` | `POST /intentos/{id}/reactivar/` · `POST /asignaciones/{id}/reactivar/` | `intento_reactivado` | `assessment.attempt.reactivate` |
| Anular (decisión humana) | `AnularIntento` | `POST /intentos/{id}/anular/` | `intento_anulado` | `assessment.attempt.void` |
| CAP-062 Puntuar y publicar | `PuntuarRespuesta`, `PublicarIntento` | `…/respuestas/{pregunta_ref}/puntuar/` · `POST /intentos/{id}/publicar/` | `revision_publicada` | `assessment.review` |
| BR-074 Decidir un envío tardío | `DecidirEnvio` | `POST /intentos/{id}/decidir-envio/` | `envio_tardio_decidido` | `assessment.deadline.enforce` |

---

## 4 · Contrato HTTP

Todas las respuestas son JSON. Todos los tiempos son **milisegundos del reloj del nodo** (`servidor_en`). Los errores salen como `{detail, codigo, …extra}` con el estado HTTP del §7. Las rutas del alumno aceptan `dispositivo` y `alumno_id` en el cuerpo o en la consulta; las del profesor aceptan `actor` y `actor_rotulo`.

### 4.1 · Profesor: asignaciones

**`POST /api/evaluacion/asignaciones/`** — crea (y con `iniciar: true`, publica) una asignación. FUN-108 + FUN-105 + FUN-106.

```json
{
  "fuente": "biblioteca", "curso_ref": "avacom.co.lower-secondary.6.science.states-of-matter", "objeto_ref": "l3-exam",
  "alcance": "grupo", "grupo_id": "…", "destinatarios": [],
  "sesion_id": "(opcional: la clase de la que nace)",
  "nivel_examen": "controlado",
  "tiempo": {"modo": "biblioteca"},
  "intentos_permitidos": 1,
  "abre_en": null, "limite_en": null, "plazo": "blando", "gracia_min": 15,
  "reactivacion": "profesor",
  "recursos": [], "resultados": "tras_liberar",
  "iniciar": true,
  "actor": "…", "actor_rotulo": "Prof. Gómez"
}
```

* `nivel_examen` es **obligatorio**: el sistema nunca preselecciona «Controlado» por el profesor (Guion, paso 1).
* `tiempo.modo`: `biblioteca` (lo que dice el examen) · `fijo` (con `limite_seg`) · `sin_limite`.
* `plazo = endurecido` exige `limite_en` (400 si falta). `abre_en` futuro ⇒ la asignación nace `programada`.
* Valida con la biblioteca que `objeto_ref` exista, sea un `exam` y tenga banco; copia sus ajustes (`estrategia`, `preguntas_por_alumno`, `total_banco`, `resultados`, `aprobacion_pct`, `permite_retroceso`, `mezclar_opciones`) y **congela la versión instalada** (`curso_version`).
* **201** con la asignación y `armado_previo` `{estrategia, preguntas_por_alumno, total_banco, limite_seg_estimado, avisos[]}` (por ejemplo `W-EXAM-POOL-SMALL` si el banco es pequeño para las tolerancias). Si la biblioteca no está: **503** con `sugerencia` (no se crea nada).
* Errores: `datos_invalidos` · `no_encontrado` (grupo, curso, objeto) · `administracion_no_permitida` no aplica aquí.

**`GET /api/evaluacion/asignaciones/`** — `?estado=&grupo_id=&sesion_id=&profesor=` → `{asignaciones: […]}` con los conteos de `totales`.

**`GET /api/evaluacion/asignaciones/{id}/`** — la asignación y sus totales.

| Ruta | Efecto | Estado exigido | Errores |
|---|---|---|---|
| `POST …/iniciar/` | publica ahora (`borrador`/`programada` → `activa`) | `borrador`, `programada` | `transicion_invalida` |
| `POST …/cerrar/` `{motivo?}` | cierra; entrega los intentos abiertos (`origen_entrega = cierre`); deja los `no_iniciado` | `activa`, `activa_fuera_de_plazo` | `transicion_invalida` |
| `POST …/prorrogar/` `{limite_en}` | `activa_fuera_de_plazo → activa` con un nuevo plazo | `activa_fuera_de_plazo` | `datos_invalidos` (plazo en el pasado) |
| `POST …/reabrir/` `{limite_en?}` | `cerrada → activa` | `cerrada` | |
| `PATCH …/plazo/` `{limite_en, plazo?, gracia_min?}` | FUN-106 | no `cerrada`/`archivada` | |
| `POST …/endurecer/` `{limite_en?}` | FUN-107: `plazo = endurecido` | exige un plazo blando vigente | `transicion_invalida` |
| `POST …/nivel/` `{nivel_examen}` | FUN-105: fija el nivel **antes** de que haya intentos vivos | sin intentos vivos | `intentos_abiertos` (409) |
| `POST …/degradar/` `{nivel_examen, motivo}` | FUN-118: **baja** el nivel vigente de una evaluación en curso (nunca sube); recalcula la elegibilidad y deja un incidente `degradacion` en cada intento vivo | `activa`, `activa_fuera_de_plazo` | `datos_invalidos` (no baja) |
| `POST …/liberar-resultados/` | `liberados_en = ahora` (DEC-032); los alumnos ven su nota si `resultados ≠ nunca` | `cerrada` o con todo entregado | `intentos_abiertos` |

### 4.2 · Profesor: vigilar y decidir

**`GET /api/evaluacion/asignaciones/{id}/panel/`** — PAN-005/121. Una fila por destinatario, **ordenada por quién necesita al profesor** (no alfabéticamente, CMP-034): primero los suspendidos en espera de reactivación, luego los que esperan admisión, luego los envíos tardíos por decidir, los que tienen un bloqueo fallido, los que van en curso y al final los entregados.

```json
{
  "asignacion": {"id": "…", "titulo": "…", "estado": "activa", "nivel_examen": "controlado", "nivel_declarado": "controlado", "limite_en": null},
  "servidor_en": 1790000000000,
  "totales": {"destinatarios": 25, "sin_intento": 2, "en_espera_admision": 1, "en_curso": 18, "suspendidos": 2, "restaurando": 0,
              "entregados": 2, "en_revision": 0, "calificados": 0, "anulados": 0, "con_incidentes": 7, "pendientes_decision": 0},
  "filas": [{
    "alumno_id": "…", "rotulo": "Juan P.", "estado": "pausado_desconexion", "requiere_reactivacion": true,
    "intento_id": "…", "numero": 1, "nivel_efectivo": "controlado",
    "dispositivo": {"id": "…", "nombre": "Tableta 07", "capacidad": "controlado", "alcanza": true},
    "respondidas": 3, "total": 4, "pregunta_actual": "l3-q9",
    "reloj": {"restante_ms": 412000, "corriendo": false, "limite_seg": 600},
    "silencio_ms": 38000,
    "incidentes": {"total": 2, "informativa": 1, "atencion": 1, "alta": 0, "ultimo": {"tipo": "desconexion", "ocurrido_en": 1790000000000}},
    "bloqueo": {"resultado": "aplicado"}, "admision": null,
    "fuera_de_plazo": false, "envio_tardio": "", "porcentaje": null
  }]
}
```

El panel **no es de vigilancia**: no suena, no marca en rojo y no ofrece «anular» en esta vista (Guion, paso 6 y 7). Cada fila abre el **expediente** (§4.3).

**`GET /api/evaluacion/asignaciones/{id}/elegibilidad/`** — PAN-060, paso 4. Por destinatario con tableta conocida (la asignada o la que usa en la clase): `{alumno_id, dispositivo_id, capacidad, nivel_exigido, alcanza}` y el resumen `{alcanzan, no_alcanzan}` que alimenta MSG-036.

**`GET /api/evaluacion/asignaciones/{id}/admisiones/`** — las admisiones `en_espera` (y las decididas con `?todas=1`).
**`POST /api/evaluacion/asignaciones/{id}/admisiones/{aid}/decidir/`** — FUN-116/BR-076.

```json
{"decision": "admitir", "nivel_admitido": "supervisado", "motivo": "La tableta no está aprovisionada", "actor": "…"}
```

`decision`: `admitir` (con `nivel_admitido` **menor** que el exigido y `motivo`) o `rechazar` (con `motivo`). Admitir **no abre el intento**: deja la admisión `admitido` con su `nivel_admitido` y el alumno lo abre al volver a pulsar «Comenzar» (su siguiente sondeo de `mias/` ya le dice que puede), con `nivel_efectivo = nivel_admitido`; reutiliza el `no_iniciado` y el reloj arranca en ese momento. Errores: `datos_invalidos` (sin motivo, nivel no menor) · `transicion_invalida` (ya decidida; se puede **cambiar** una decisión `rechazado` mientras la asignación esté viva).

**`POST /api/evaluacion/asignaciones/{id}/reactivar/`** — reactiva a **todos** los suspendidos y dice a cuántos afecta (`{reactivados: n}`; el profesor ve el número antes de confirmar, Guion paso 12).

### 4.3 · Profesor: el intento

| Ruta | Efecto |
|---|---|
| `GET /intentos/{id}/` | **Expediente** (PAN-062, sólo lectura): el intento sin respuestas, `incidentes[]` con su contexto, `pausas[]`, `sesiones[]`, `admision`, `bloqueo`, `linea_de_tiempo[]` ordenada. **No ofrece anular.** |
| `GET /intentos/{id}/revision/` | Para `assessment.review`: las preguntas que vio el alumno (sin claves) con su respuesta y su veredicto. |
| `POST /intentos/{id}/reactivar/` `{desde_pregunta?}` | PAN-061: de `pausado_desconexion` o `restaurando` a `en_curso` (o `en_curso_fuera_de_plazo`). El reloj continúa **desde el valor congelado**. Responde `{restante_ms, desde_pregunta}`. |
| `POST /intentos/{id}/cerrar/` | «Cierre forzado» (`pausado_desconexion`/`restaurando` → `entregado`, `origen_entrega = profesor`). |
| `POST /intentos/{id}/anular/` `{motivo}` | Sólo desde `entregado`, `en_revision_docente` o `calificado`. **Motivo obligatorio**, persona obligatoria: `anulado_por`, `anulado_en`. |
| `POST /intentos/{id}/respuestas/{pregunta_ref}/puntuar/` `{puntaje, comentario?}` | Puntúa un reactivo pendiente (0 ≤ puntaje ≤ máximo). Cambiar un puntaje ya puesto deja el asiento `calificacion.modificada` con valor anterior y nuevo. |
| `POST /intentos/{id}/publicar/` | `en_revision_docente → calificado` cuando no queda nada pendiente. |
| `POST /intentos/{id}/decidir-envio/` `{decision: aceptar\|descartar, motivo?}` | BR-074: suma o conserva lo que llegó fuera de la gracia. |
| `POST /intentos/{id}/recalificar/` | Reintenta la calificación pendiente (`calificacion_pendiente`). Idempotente. |

### 4.4 · Alumno

**`GET /api/evaluacion/estudiantes/`** — el «¿Quién eres?» de la evaluación (D-19, D-25). **Sin sesión, sin permiso y sin parámetros.** `{disponible, motivo, grupos: [{id, nombre, alumnos: [{id, rotulo}]}], servidor_en}`: los alumnos de los grupos que tienen una evaluación `programada`, `activa` o `activa_fuera_de_plazo`, ordenados por nombre. Con sesión de usuario no hace falta (el pase del nodo ya dice quién es); sin ella, la tableta pregunta a la persona quién es y manda ese `alumno_id` en las demás llamadas. Es lo mismo que hace Modo Estudio con sus lecciones: el LMS es offline y no hay verificación central.

**`GET /api/evaluacion/mias/`** — `?dispositivo=&alumno_id=&todas=1`. `{pendientes: […], recientes: […], servidor_en}`: las asignaciones que le alcanzan y están `programada`, `activa` o `activa_fuera_de_plazo` (y, con `todas=1`, las cerradas de los últimos 7 días en que tiene intento). Cada una lleva `mi_intento` `{id, numero, estado}` o `null`, `puede_comenzar` y `nivel_examen`. **Es lo que sondea Student** (cada 3 s dentro de la clase) y lo que dispara la antesala.

**`GET /api/evaluacion/asignaciones/{id}/antesala/`** — PAN-120 (alumno).

```json
{
  "asignacion": {"id": "…", "titulo": "…", "curso_rotulo": "…", "estado": "activa", "preguntas": 4, "duracion_seg": 700,
                 "intentos_permitidos": 1, "intentos_usados": 0, "plazo": "blando", "limite_en": null, "resultados": "tras_liberar"},
  "condiciones": {"nivel": "controlado", "titulo": "Examen controlado", "texto": "Durante este examen tu tableta solo muestra el examen. Si sales, tu profesor lo verá, y tus respuestas se guardan igual.",
                  "registra": ["Salidas de la aplicación", "Tus respuestas y el tiempo que tomaste"]},
  "dispositivo": {"id": "…", "capacidad": "supervisado", "alcanza": false, "nivel_exigido": "controlado"},
  "admision": null,
  "mi_intento": null,
  "puede_comenzar": true, "motivo": "", "servidor_en": 1790000000000
}
```

`motivo` cuando `puede_comenzar = false`: `espera_admision` · `rechazada` · `intentos_agotados` · `no_abierta` (programada o cerrada) · `ya_entregado`. **Una tableta que no alcanza el nivel sí puede pulsar «Comenzar»**: eso crea la solicitud de admisión (no excluye al alumno por su dispositivo).

**`POST /api/evaluacion/asignaciones/{id}/intentos/`** — FUN-109. Idempotente: si el alumno ya tiene un intento **vivo**, lo devuelve (`200`, `reanudado: true`).

| Resultado | HTTP | Cuerpo |
|---|---|---|
| Intento abierto | **201** | `{intento, reloj, plan_bloqueo, condiciones, preguntas_total, reanudado: false}` |
| Ya había uno vivo | **200** | lo mismo con `reanudado: true` |
| La tableta no alcanza el nivel | **202** | `{intento: {estado: "no_iniciado"}, admision: {id, estado: "en_espera", nivel_exigido, nivel_alcanzado}, mensaje}` |
| El profesor rechazó la tableta | **403** | `admision_rechazada` |
| Sin cupo | **409** | `intentos_agotados` |
| La asignación no está abierta | **409** | `asignacion_no_abierta` (`motivo`: `programada` · `cerrada` · `borrador`) |

Al abrir se: (1) valida identidad y alcance; (2) abre la «Dim Sesión Alumno» (cierra con `relevo` la de otra tableta, TST-027); (3) compara nivel y capacidad (BR-075); (4) congela `curso_version`; (5) arma el examen con la `semilla` (§6.2); (6) calcula el límite (§6.3); (7) fija `reloj_desde = ahora`; (8) escribe el intento, el evento `intento_abierto`, el asiento `evaluacion.iniciada` y el aviso de tiempo real.

**`GET /api/evaluacion/intentos/{id}/estado/`** y **`POST /api/evaluacion/intentos/{id}/latido/`** — el mismo cuerpo de respuesta. El latido además registra `ultimo_latido_en`, `pregunta_actual`, `transcurrido_ms`, la capacidad declarada y la telemetría de la tableta.

```json
{
  "intento": {"id": "…", "estado": "en_curso", "numero": 1, "nivel_efectivo": "controlado", "pregunta_actual": "l3-q9",
              "respondidas": 3, "total": 4, "fuera_de_plazo": false, "envio_tardio": ""},
  "reloj": {"limite_seg": 700, "restante_ms": 412000, "corriendo": true, "congelado": false, "servidor_en": 1790000000000},
  "plan_bloqueo": {"nivel": "controlado", "capa_sistema": true, "capa_app": true, "registrar_salidas": true,
                   "registrar_consultas": false, "bloquear_capturas": true, "cubrir_pantallas_extra": true, "latido_seg": 5},
  "espera_reactivacion": false,
  "mensaje": null,
  "resultado_disponible": false
}
```

* Un latido sobre un intento `pausado_desconexion` **no lo reanuda** salvo `reactivacion = automatica` (en cuyo caso vuelve a `en_curso`, el reloj continúa y se registra `reconexion`). Con `reactivacion = profesor` responde `espera_reactivacion: true` y `mensaje.codigo = "suspendido"` (MSG-033: «Todo lo que respondiste está guardado y el tiempo está detenido. Tu examen queda en pausa. Avisa a tu profesor para continuar.»).
* Un latido de un intento `restaurando` lo pasa a `en_curso` (si la asignación es `automatica`) o a `pausado_desconexion` esperando al profesor.
* Un latido de un intento ya entregado devuelve su estado final sin error (la tableta puede reenviar).

**`GET /api/evaluacion/intentos/{id}/preguntas/`** — el examen **de este alumno**, en el orden del `armado`, en la forma de la vista de aula (la misma que ya pintan los controles de pregunta de Student: `pregunta_ref`, `tipo`, `componente`, `enunciado`, `opciones`, `espacios`, `izquierda`, `derecha`, `elementos`, `medios`, `puntos`…) y **sin ninguna clave** (`Cache-Control: no-store`). Incluye `respondidas` `{pregunta_ref: {respuesta, secuencia}}` para reanudar y `navegacion_atras`. Sólo en `en_curso`, `en_curso_fuera_de_plazo`, `pausado_desconexion` y `restaurando` (una tableta que vuelve debe poder reabrir su examen). Los medios de las preguntas se sirven por `GET /intentos/{id}/medios/{media_ref}/[ruta]` (con `Range`), sólo si pertenecen a una pregunta de **este** intento.

**`POST /api/evaluacion/intentos/{id}/respuestas/`** — FUN-110/111. Una sola llamada puede traer varias respuestas (hasta 200: lo que sale de la cola local).

```json
{"dispositivo": "…", "alumno_id": "…", "origen": "directo", "pregunta_actual": "l3-q9", "transcurrido_ms": 187000,
 "respuestas": [{"pregunta_ref": "l3-q1", "secuencia": 1, "respuesta": {"selectedOptionIds": ["a"]},
                 "capturada_en": 1790000001000, "capturada_en_tableta": 1790000000950}]}
```

```json
{"acuse": true, "aceptadas": ["l3-q1"], "duplicadas": [], "superadas": [], "rechazadas": [],
 "intento": {"id": "…", "estado": "en_curso", "respondidas": 1, "secuencia_maxima": 1},
 "reloj": {"restante_ms": 412000, "corriendo": true}, "recibida_en": 1790000001200, "servidor_en": 1790000001200}
```

* **Aceptada**: nueva, o de secuencia mayor que la vigente de la misma pregunta y sesión. **Duplicada**: la misma terna (reenvío): se acusa y no se toca (`respuesta_deduplicada`). **Superada**: llega con una secuencia menor, o de una sesión más antigua que la vigente para esa pregunta (BR-138): se conserva en el intento como `superadas` en el acuse y como incidente `respuesta_tardia`, **sin** pisar la vigente. **Rechazada**: sin `pregunta_ref`, con una pregunta que **no está en el armado**, `secuencia < 1`, respuesta vacía o de forma no admitida para el tipo.
* Se aceptan respuestas en `en_curso`, `en_curso_fuera_de_plazo`, `pausado_desconexion` y `restaurando` (BR-071: lo capturado antes de la pausa llega después). En un intento entregado: **409 `intento_cerrado`**, salvo un reenvío idéntico de lo ya entregado (se acusa sin tocar nada, INV-005) o lo capturado antes del cierre dentro de la gracia (§6.5).
* Cada respuesta se guarda de forma independiente y **no espera a la entrega** (BR-071).

**`POST /api/evaluacion/intentos/{id}/incidentes/`** — FUN-117, desde la tableta.

```json
{"dispositivo": "…", "alumno_id": "…",
 "incidentes": [{"tipo": "salida_de_app", "detalle": {"desde": 1790000100000}, "ocurrido_en": 1790000100020,
                 "ocurrido_en_tableta": 1790000099900, "ref_cliente": "dev1-17"}]}
```

→ `{registrados: n, duplicados: n}`. La tableta sólo puede informar los tipos de origen `tableta` del catálogo (400 con cualquier otro: un cliente no puede fabricar `reactivado`, `degradacion` ni `desconexion`). **Nunca cambia el estado del intento** (BR-077). Idempotente por `ref_cliente`.

**`POST /api/evaluacion/intentos/{id}/bloqueo/`** — la tableta **informa** lo que logró aplicar del plan.

```json
{"dispositivo": "…", "alumno_id": "…", "resultado": "parcial",
 "capas": {"sistema": false, "app": true, "capturas": true, "pantallas": true},
 "motivo": "Android: la app no es Device Owner"}
```

`resultado`: `aplicado` · `parcial` · `fallido` · `liberado`. Se guarda en `intento.bloqueo`. Si el plan pedía `capa_sistema` y el resultado es `parcial`/`fallido`, se registran los incidentes `bloqueo_parcial` (atención) o `bloqueo_fallido` (alta) y el panel del profesor lo destaca. **El intento sigue**: el nodo no presume lo que la tableta no informó, ni invalida por ello.

**`POST /api/evaluacion/intentos/{id}/entregar/`** — FUN-114.

```json
{"dispositivo": "…", "alumno_id": "…", "confirmar": true, "transcurrido_ms": 612000,
 "respuestas": [{"pregunta_ref": "l3-q4", "secuencia": 4, "respuesta": {"order": ["…"]}, "capturada_en": 1790000600000}]}
```

`confirmar: true` es obligatorio si quedan reactivos sin responder (la tableta ya le mostró «Te faltan 2»). `respuestas` permite el último vaciado de la cola en la misma llamada. Responde `{intento, entregado_en, origen_entrega, que_sigue}` donde `que_sigue` es `{codigo, texto}`: `resultado_al_liberar` («Tu profesor publicará los resultados.») · `en_revision` («Algunas respuestas las revisa tu profesor.») · `sin_resultado`. **Nunca** dice «calificado» mientras quede un reactivo por revisar (Guion, paso 13). Idempotente: entregar dos veces devuelve lo mismo.

**`GET /api/evaluacion/intentos/{id}/resultado/`** — sólo cuando el profesor liberó los resultados (`resultados ≠ nunca` y `liberados_en` o `resultados = al_entregar` sin pendientes). `{porcentaje, puntaje, puntaje_maximo, aprobado, detalle[]}`; **403 `resultados_no_liberados`** antes (DEC-032).

### 4.5 · FUN-103 y FUN-104

`POST /api/evaluacion/evaluaciones/` y `POST /api/evaluacion/reactivos/` (y cualquier otro verbo de escritura sobre ellos) responden **409 `administracion_no_permitida`** con `detail` que nombra a la biblioteca como dueña, igual que `/api/courses/…` en el expediente (constitución, 14.2).

---

## 5 · La lógica

### 5.1 · Las transiciones por tiempo son perezosas (D-15)

Antes de leer o escribir una asignación o un intento, cada caso de uso llama a `asegurar_asignacion(uow, id, ahora)` y `asegurar_intento(uow, id, ahora)`, que aplican **de forma idempotente** lo que el reloj ya provocó:

| Si… | Entonces |
|---|---|
| `programada` y `abre_en ≤ ahora` | `activa` |
| `activa`, plazo blando, `limite_en ≤ ahora` | `activa_fuera_de_plazo`; sus intentos `en_curso` pasan a `en_curso_fuera_de_plazo` |
| `activa`/`activa_fuera_de_plazo`, plazo endurecido, `limite_en ≤ ahora` | `cerrada`; los intentos abiertos se **entregan** (`origen_entrega = plazo`, incidente `entrega_automatica`) |
| un intento corriendo y `restante ≤ 0` | se **entrega** (`origen_entrega = tiempo`, incidente `tiempo_agotado`) |
| un intento `en_curso` y `ahora − ultimo_latido_en > AVACOM_EVAL_LATIDO_VENCIDO_MS` | `pausado_desconexion`, reloj congelado **en el último latido** |

**Lo que el reloj provocó se confirma aunque la petición que lo descubrió se rechace** (D-21): la unidad de trabajo hace `commit` cuando el caso termina en un `ErrorEvaluacion` (409, 403, 404…) y `rollback` con cualquier otra excepción. Los casos de uso validan antes de escribir lo suyo, así que confirmar no deja nada a medias.

El programador (§5.8) ejecuta lo mismo cada 5 s para todo el nodo, de modo que un examen se entrega por tiempo aunque nadie consulte nada. En las pruebas no corre: la corrección no depende de él.

### 5.2 · Armado y tiempo

`armar(pool, estrategia, cantidad, tolerancias, cubrir_temas, semilla)` es una función pura (§7 del modelo). La `semilla` es `"{asignacion_id}|{alumno_id}|{numero}"`. El resultado se guarda en `m10_intento_formal.armado` (referencias) y `armado_meta`. El límite en segundos sale de `tiempo_modo` (§7.2 del modelo).

### 5.3 · Respuestas (INV-013, BR-138)

`fusionar(vigentes, nuevas, sesion)` (`dominio/respuestas.py`), dentro de la transacción:

1. Para cada respuesta nueva busca la vigente de la misma `pregunta_ref`.
2. Si hay una de la **misma sesión**: misma `secuencia` ⇒ **duplicada**; menor ⇒ **superada**; mayor ⇒ **aceptada** (sustituye).
3. Si la vigente es de **otra sesión**: prevalece la de mayor `sesion_orden` (la más reciente), con independencia del orden de llegada. La nueva de una sesión **más antigua** ⇒ **superada**; la de una más reciente ⇒ **aceptada** y sustituye.
4. Se actualizan `secuencia_maxima`, `pregunta_actual` y `respondidas`; se publica `respuesta_registrada` por cada aceptada y `respuesta_deduplicada` por cada duplicada, **sin el contenido**.

La forma de la respuesta se valida por tipo con `armado_meta.tipos` (la misma tabla `FORMAS_RESPUESTA` del aula); la validación profunda (cada referencia existe en la pregunta que vio el alumno) se hace al calificar.

### 5.4 · Calificar (D-16)

`Calificar` corre al entregar, dentro de la misma transacción de la entrega:

1. Arma el lote `[{objectId, questionId, response}]` con las respuestas **no revisadas** del intento y llama **una sola vez** a `evaluar_lote(curso_ref, curso_version, items)`.
2. Traduce cada veredicto (`puntaje` decimal o nulo, `correcta`, `requiere_correccion_manual`, `pendiente`, `retroalimentacion[]`). Un `requiresManualGrading` deja el puntaje **nulo** aunque la biblioteca mande un número.
3. Si el lote falla por **una** respuesta mal formada, prueba una por una (tope 20) para no dejar sin nota a las demás.
4. Si la biblioteca no está (503/501): `calificacion_pendiente = true`, el intento queda `entregado` con `puntaje`, `puntaje_maximo` y `porcentaje` **nulos** (no hay ni nota parcial, D-22) y `BarrerNodo`/`recalificar` lo resuelven después. `recalificar` sólo manda a la biblioteca lo que aún no tiene veredicto y **sólo publica eventos si calificó algo**: recalificar lo ya calificado es una operación sin efectos (INV-005).
5. `porcentaje = 100 × Σ puntaje / Σ puntaje_maximo` (escala interna 0–100; nunca se redondea a entero antes de guardar). Un reactivo omitido suma **cero** sobre su máximo; los pendientes no suman ni restan.
6. Con reactivos pendientes ⇒ `en_revision_docente` y `evaluacion.revision.solicitada.v1`. Sin ellos ⇒ `calificado` con `calificado_por = sistema` y `evaluacion.autocalificacion.completada.v1`.

NFR-012: calificar un envío de hasta 40 respuestas objetivas tarda ≤ 2 s con la biblioteca a la vista (una llamada por entrega, nunca una por respuesta).

### 5.5 · Nivel, capacidad y plan de bloqueo

`dominio/bloqueo.py`:

```python
def alcanza(capacidad: str, nivel: str) -> bool          # rango(capacidad) >= rango(nivel)
def plan_de_bloqueo(nivel_efectivo: str, capacidad: str, nivel_exigido: str | None = None) -> dict
def condiciones(nivel: str) -> dict                       # el texto obligatorio para la antesala
```

`plan_de_bloqueo` produce el diccionario del §6.4 del modelo. Se devuelve en **tres** sitios: al abrir el intento, en cada `estado`/`latido` (por si el profesor degradó el nivel en curso) y en la antesala (como `condiciones`). **Degradar** (FUN-118) cambia `nivel_examen` y por tanto el plan en el siguiente latido: la tableta suelta lo que ya no se exige.

### 5.6 · Reloj

`dominio/intento.reloj(intento, ahora)` devuelve `{limite_seg, restante_ms, corriendo, congelado}`:

```
transcurrido = consumido_ms + (ahora − reloj_desde  si reloj_desde else 0)
restante     = limite_ms − transcurrido           (nulo si no hay límite)
```

Congelar: `consumido_ms += ultimo_latido_en − reloj_desde`; `reloj_desde = null`. Reanudar: `reloj_desde = ahora`. **Reconciliación** con la tableta (D-8): si el latido o las respuestas traen `transcurrido_ms`, `consumido_efectivo = min(max(consumido_nodo, transcurrido_ms), ahora − iniciado_en)`: el tiempo no puede salir de un reloj ajeno ni superar el tiempo real desde que se abrió.

### 5.7 · Plazos y envíos tardíos

`dominio/asignacion.politica_de_recepcion(...)` generaliza la del aula con los dos plazos (§8 del modelo). Un envío que llega a un intento ya entregado de una asignación cerrada:

| Capturado | Recibido | Resultado |
|---|---|---|
| antes del cierre | ≤ cierre + gracia | `aceptar` (suma y recalifica) |
| antes del cierre | > cierre + gracia | `decide_el_profesor`: a `respuestas_pendientes`, `envio_tardio = pendiente_decision`, evento y aviso al panel |
| después del cierre | — | `rechazar` (409 `asignacion_cerrada`) |

«Cierre» es `dominio/asignacion.cierre_de_recepcion(intento, asignacion)`: el **cierre de la asignación** (`cerrada_en`) cuando el intento se entregó porque ella cerró (`origen_entrega = plazo` o `cierre`) y la **entrega del propio intento** en los demás casos. Así, una tableta que dejó de dar señal y cuyo intento el nodo entregó con el reloj detenido en el último latido todavía puede enviar lo que respondió sin red hasta la fecha límite. Si entregó el alumno, el intento no admite nada más: 409 `intento_cerrado`. Un reenvío idéntico de lo ya entregado se acusa sin tocar nada (INV-005).

### 5.8 · El programador del nodo

`evaluacion/infraestructura/programador.py` (hilo daemon que arranca `avacom_lms/asgi.py`, como el del aula; `AVACOM_EVAL_PROGRAMADOR=0` lo desactiva):

* **Al arrancar** (`AVACOM_EVAL_DETECTAR_REINICIO`): todo intento `en_curso`, `en_curso_fuera_de_plazo` o `pausado_desconexion` pasa a `restaurando`, con el reloj congelado en su último latido, incidente `reinicio_nodo` y evento `intento_restaurado` (BR-051, INV-010, AC-073). **Ninguno cambia a `entregado` ni a `anulado`.**
* **Cada 5 s**: pausar los que no dan latido, entregar los que agotaron el tiempo, cerrar las asignaciones con plazo endurecido vencido, mover `programada → activa` y `activa → activa_fuera_de_plazo`, reintentar las calificaciones pendientes.
* **Cada minuto**: `cerrada` hace más de 24 h ⇒ `archivada`.

`BarrerNodo` devuelve `{asignaciones, pausados, entregados, recalificados, errores}` y trata **cada asignación y cada intento en su propia transacción y su propio `try`**: un caso defectuoso se registra (`avacom.evaluacion.programador`), se cuenta en `errores` y los demás se ponen al día igual (D-24). Un tick sin novedades no escribe en el registro. Un tick que falla por completo se registra y el siguiente lo reintenta; el nodo no se cae por esto.

### 5.9 · Reactivar

* Sólo desde `pausado_desconexion` o `restaurando`. Vuelve al `estado_previo` guardado en la pausa. `reloj_desde = ahora`; el tiempo restante es el congelado.
* Incidente `reactivado` (`por`, `restante_ms`, `desde_pregunta`) y asiento `evaluacion.intento.reactivado` (MOD-019 «sella incidentes y reactivaciones»).
* `reactivar` sobre un intento que ya está corriendo no hace nada y responde igual (idempotente).
* **Cierre forzado** (`POST /intentos/{id}/cerrar/`): sólo de un intento suspendido; lo entrega con `origen_entrega = profesor`. **Anular** sólo parte de un intento ya entregado, de una persona identificada y con motivo (≥ 3 caracteres): sin `actor` ni sesión responde 400 (D-23).
* DEC-038: mientras haya un examen en curso, **no hay relevo de profesor**; la sesión permanece con el titular. Sólo el titular o la administración reactivan.

---

## 6 · Integración con el resto del backend

| Dónde | Qué se añadió | Por qué |
|---|---|---|
| `avacom_lms/settings.py`, `urls.py`, `asgi.py` | App `evaluacion`, ruta `api/evaluacion/`, variables `AVACOM_EVAL_*`, arranque del programador | Registro del módulo |
| `acceso/dominio/plantillas.py` + migración `0009_permisos_evaluacion` | Los 16 permisos `assessment.*` y su reparto por rol | D-18 |
| `audit/dominio/catalogos.py` | Acciones nuevas `evaluacion.*` (catálogo cerrado) | MOD-019 §3.5 |
| `device_manager` (modelo, caso de uso, serializer, `servicios`) + migración `0005_capacidad_control` | `capacidad_control` y `capacidad_detalle`, declarables en el registro y el latido | BR-075 |
| `classroom_engine/infraestructura/contenedor.py` + `avacom_lms/settings.py` | `AVACOM_AULA_PERMITIR_EJEMPLO` (apagado salvo `=1` o `manage.py test`): sin él, pedir la fuente `ejemplo` se resuelve con la biblioteca | Los cursos salen SIEMPRE de la biblioteca, también en el instalador |
| `classroom_engine/infraestructura/repositorios.py` | `EvaluacionExpediente.intentos_abiertos` suma los intentos vivos de MOD-010 | Cerrar una clase cuenta los exámenes abiertos (JRN-011) |
| `classroom_engine/infraestructura/tiempo_real.py` | `evaluacion_panel` va sólo al profesor | El aviso del panel no necesita llegar a 50 tabletas |

**La capa de biblioteca no se toca** (`biblioteca/`, `FuenteDeCursos` y sus adaptadores, `classroom_engine/dominio/curso.py`, el host de pruebas v2). Lo que sólo el examen necesita de un curso —el esquema con los objetos de modo `exam`, `GET …/exams/{oid}/pool` y `…/questions`, y la vista de las preguntas de un alumno— vive en `evaluacion/infraestructura/fuentes_examen.py`, que sólo *lee* de ellas (con la biblioteca, por el cliente `biblioteca.contenido_v2` tal como está; con el ejemplo de pruebas, por el manifiesto). Para las pruebas contra HTTP, `evaluacion/tests/host_examenes.py` extiende el host de pruebas de la biblioteca con esas dos rutas sin modificarlo.

---

## 7 · Errores

| Código | HTTP | Cuándo |
|---|---|---|
| `datos_invalidos` | 400 | Datos que no cumplen las reglas (nivel desconocido, plazo endurecido sin fecha, motivo ausente, anular sin persona identificada…) |
| `falta_dispositivo` · `falta_alumno` | 400 | No se sabe desde qué tableta o quién |
| `sin_permiso` · `no_es_el_titular` | 403 | Permiso `assessment.*` no concedido · la asignación es de otro profesor |
| `dispositivo_bloqueado` · `dispositivo_inactivo` | 403 | MOD-009 |
| `admision_rechazada` | 403 | El profesor rechazó la tableta |
| `resultados_no_liberados` | 403 | DEC-032 |
| `no_encontrado` | 404 | No existe o no le alcanza al alumno |
| `no_instalado` | 409 | El nodo no tiene organización |
| `administracion_no_permitida` | 409 | FUN-103/104: es de la biblioteca |
| `asignacion_no_abierta` · `asignacion_cerrada` | 409 | Programada, borrador o cerrada · se capturó después del cierre |
| `intentos_agotados` | 409 | BR-072 |
| `intentos_abiertos` | 409 | Hay intentos vivos y la operación lo prohíbe |
| `transicion_invalida` | 409 | La máquina de estados no la permite (con `estado` y `destino`) |
| `intento_cerrado` | 409 | Respuestas a un intento entregado |
| `reactivos_pendientes` | 409 | Publicar con reactivos sin puntuar |
| `fuente_no_disponible` | 503 | Biblioteca cerrada: `{disponible: false, detail, codigo, sugerencia}`. Guardar respuestas **nunca** falla por esto |
| `fuente_error` | 502 | La biblioteca contestó con error |

---

## 8 · Configuración (`settings.py`)

| Variable | Defecto | Para qué |
|---|---|---|
| `AVACOM_EVAL_LATIDO_VENCIDO_MS` | 30000 | Silencio tras el cual el intento se pausa (INV-010: reconexión en 30 s) |
| `AVACOM_EVAL_LATIDO_SEG` | 5 | Cadencia que se recomienda a la tableta (punto de recuperación de 5 s) |
| `AVACOM_EVAL_GRACIA_MIN` | 15 | Gracia por defecto de una asignación nueva (DEC-019) |
| `AVACOM_EVAL_PROGRAMADOR` | 1 | `0` desactiva el programador |
| `AVACOM_EVAL_DETECTAR_REINICIO` | 1 | `0` no pasa los intentos a `restaurando` al arrancar |
| `AVACOM_EVAL_ARCHIVADO_H` | 24 | Horas para `cerrada → archivada` |
| `AVACOM_EVAL_MAX_RESPUESTAS` | 200 | Tope de respuestas por envío |
| `AVACOM_EVAL_DESFASE_RELOJ_MS` | 5000 | Desfase del reloj de la tableta a partir del cual se registra `reloj_desfasado` |
| `AVACOM_EVAL_ARMADO_INTENTOS` | 200 | Combinaciones que prueba `random_balanced` |

---

## 9 · Pruebas

Se ejecutan con `.venv\Scripts\python manage.py test evaluacion` (302 pruebas, ~70 s) y la suite completa con `manage.py test` (961 pruebas, ~8 min). No necesitan la biblioteca real: la mayoría usa la fuente «ejemplo» con el calificador de referencia (`tools.host_contenido_v2_pruebas.calificar`); el contrato HTTP (`test_contrato_v2`) levanta el **host de pruebas de la API v2** con token y `link.json` y recorre `pool`, `questions` y `evaluate/batch` de verdad. Un reloj controlable (`self.avanzar(...)`) mueve el tiempo del nodo sin dormir.

| Escenario del Maestro | ¿Se cubre en el backend? | Prueba (`evaluacion/tests/`) |
|---|---|---|
| **TST-004** Completar actividad (25 intentos entregados, ninguno sin dueño) | Sí | `test_carga.AulaCompletaTests.test_tst_004_veinticinco_alumnos_abren_responden_y_entregan_sin_perder_nada` |
| **TST-005** Ver resultados en vivo | Sí (panel y totales) | `test_panel.OrdenDelPanelTests` · `test_calificacion.ResultadosDeLaAsignacionTests` |
| **TST-012**, **TST-017** Caída de red y 50 reconectan sin duplicados | Sí | `test_carga.test_tst_017_cincuenta_tabletas_dan_senal_y_escriben_a_la_vez_y_nadie_se_suspende` · `test_respuestas.ReanudacionTests.test_la_cola_de_una_desconexion_larga_entra_completa_y_en_orden_al_volver` |
| **TST-015** Corte de 20 s | Sí (no se pausa antes de 30 s) | `test_reloj.RelojDelIntentoTests.test_tst_015_un_corte_de_20_segundos_no_pausa_ni_pierde_nada` |
| **TST-021** Carga nominal de 50 / latencia p95 | Parcial: 50 alumnos en una corrida y consultas del panel acotadas; la latencia real es de hardware | `test_carga` |
| **TST-024** Paridad Windows/tableta | No es del backend | [frontend.md](frontend.md) |
| **TST-026** Cambio de equipo a mitad de intento | Sí | `test_reloj.CambioDeTabletaTests.test_tst_026_pasar_a_otra_tableta_continua_donde_iba_y_no_pierde_respuestas` |
| **TST-027** Doble sesión del alumno | Sí | `test_reloj.CambioDeTabletaTests.test_tst_027_…` · `test_respuestas.GuardarRespuestasTests.test_br_138_la_sesion_mas_reciente_prevalece_aunque_su_secuencia_sea_menor` |
| **TST-030**, **TST-031** Intentos ilimitados / intento único | Sí | `test_api_intentos.AbrirIntentoTests.test_intentos_ilimitados_tst_030` · `test_cupo_por_defecto_de_uno_…` |
| **TST-032** Tiempo límite al reloj del nodo | Sí | `test_reloj.RelojDelIntentoTests.test_tst_032_el_tiempo_se_agota_en_el_instante_exacto_y_el_nodo_entrega` · `test_barrido.BarridoTests.test_entrega_a_quien_agoto_el_tiempo_y_lo_califica` |
| **TST-033** Entrega automática con plazo endurecido | Sí | `test_plazos.PlazoEndurecidoTests.test_tst_033_al_vencer_el_plazo_cierra_la_asignacion_y_entrega_lo_respondido` |
| **TST-034** Reconexión en examen | Sí | `test_reloj.RelojDelIntentoTests.test_tst_034_un_corte_de_45_segundos_suspende_registra_incidente_y_no_invalida` |
| **TST-036** Guardado parcial | Sí | `test_respuestas.GuardarRespuestasTests.test_tst_036_una_respuesta_mala_no_tumba_a_las_buenas_y_se_rechaza_con_su_motivo` |
| **TST-037** Autocalificación de los tipos objetivos | Sí: una sola llamada por lote, ≤ 2 s, los seis tipos de la biblioteca | `test_calificacion.AutocalificacionTests.test_tst_037_…` · `test_contrato_v2.ExamenPorHttpTests` |
| **TST-038** Revisión docente | Sí (provisional hasta MOD-011) | `test_calificacion.RevisionDocenteTests.test_tst_038_…` |
| **TST-040** Intento duplicado | Sí | `test_respuestas.GuardarRespuestasTests.test_tst_040_el_reenvio_exacto_no_duplica_nada_y_lo_acusa_igual` |
| **TST-041** Equipo por debajo del nivel | Sí | `test_niveles.AdmisionTests.test_tst_041_…` |
| **TST-042**, **TST-078** Cola y ventana de gracia | Sí | `test_plazos.GraciaTests.test_tst_042_…` · `test_tst_078_…` |
| **TST-076** Arrastrar y soltar | **No**: la biblioteca no publica ese tipo (Q-79) | — |
| **TST-077** Examen Supervisado, incidentes, intentos válidos | Sí | `test_incidentes.IncidentesDeLaTabletaTests.test_tst_077_…` · `test_br_077_muchos_incidentes_no_anulan_…` |
| **AC-073** Reinicio del nodo con alumnos presentando | Sí | `test_reloj.ReinicioDelNodoTests` · `test_barrido.ProgramadorTests.test_al_arrancar_…` |
| **INV-018** Ninguna flecha automática a `anulado` | Sí | `test_dominio_intento.test_inv_018_…` · `test_arquitectura.test_el_dominio_nunca_asigna_anulado_fuera_de_anular` · `test_panel.AnularTests` |
| **INV-024** La versión del curso se congela y se califica con ella | Sí, contra la API v2 real | `test_contrato_v2.CursoQueCambiaTests` |
| **DEC-032** El alumno no ve su nota antes de que se libere | Sí | `test_calificacion.ResultadoDelAlumnoTests` |

Por archivo: `test_dominio_reglas` (43) y `test_dominio_intento` (19) son puras (sin base de datos); `test_arquitectura` (10) comprueba que dominio y aplicación no importan Django, que las vistas no tocan el ORM, que el esquema no guarda curso ni claves, que `m10_incidente` es de sólo inserción, que el catálogo de permisos y de eventos es el esperado y que toda acción auditada existe en el catálogo cerrado de MOD-019; `test_api_asignaciones` (31), `test_api_intentos` (28), `test_niveles` (13), `test_reloj` (21), `test_plazos` (26), `test_respuestas` (20), `test_incidentes` (22), `test_calificacion` (26), `test_panel` (15), `test_barrido` (15), `test_carga` (3), `test_contrato_v2` (9) y `test_humo` (1) recorren la API. En `device_manager`, `test_capacidad_control` (8) cubre la capacidad declarada.

Cada respuesta que recibe un alumno se recorre con `contiene_clave` en `test_api_intentos` y `test_contrato_v2.test_el_nodo_nunca_recibe_ni_entrega_una_clave`: ninguna lleva `isCorrect`, `answer`, `acceptedAnswers`, `correctOrder`, `pairs` ni `explanation`.

---

## 10 · Estado de construcción

**Construido y probado (2026-10-01).**

* La app `evaluacion` entera: cinco tablas `m10_*` (la del intento se llama `m10_intento_formal`), dominio puro, casos de uso por la interfaz de sus puertos, repositorios, unidad de trabajo, programador del nodo y las 36 rutas de §4. Migraciones `evaluacion/0001`, `acceso/0009` y `device_manager/0005`.
* Integraciones: permisos `assessment.*` (16), acciones `evaluacion.*` del catálogo de MOD-019, capacidad de control de la tableta (MOD-009), `pool`/`questions` de la API v2 por `fuentes_examen` (sin tocar la capa de biblioteca), el conteo de exámenes abiertos al cerrar una clase y el aviso por el canal de tiempo real del aula.
* Suite completa: **961 pruebas en verde** (651 de la línea base más 310 nuevas), 3 omitidas por depender de `jsonschema`.

**Defectos que las pruebas destaparon y se corrigieron.** (1) La unidad de trabajo revertía lo que el reloj había provocado cuando la petición que lo descubrió se rechazaba (D-21). (2) Un intento entregado con la biblioteca caída guardaba `porcentaje = 0` (D-22). (3) Recalificar lo ya calificado volvía a publicar `intento_calificado`. (4) El cierre manual de la asignación entregaba con `origen_entrega = profesor` en vez de `cierre`, y el corte de la gracia de una tableta sin señal se medía contra su último latido y no contra el cierre de la asignación (§5.7). (5) Anular sin persona identificada se firmaba como «docente» (D-23). (6) Un intento defectuoso detenía el barrido del nodo entero (D-24).

**No construido en el backend, a propósito.** Crear evaluaciones y reactivos (FUN-103/104, de la biblioteca); la nota publicada y los ajustes (MOD-011); archivos de dibujo y proyecto (MOD-014); SCORM (V1); arrastrar y soltar y matemática con equivalencias (la biblioteca no los publica, Q-79); unificar `m07_intento` y `m08_practica` bajo `m10_*` (Q-75).

**No se puede comprobar aquí.** El comportamiento de las tabletas reales (Lock Task, Assigned Access, Shell Launcher), la latencia con 50 tabletas físicas y el apagado forzado: ver [frontend.md](frontend.md) §10 y [kiosk.md](kiosk.md) §7.
