# Objetivo del módulo

Aplica una evaluación a un grupo con la garantía de que **cada respuesta queda a salvo, el reloj es el del nodo y lo que la plataforma no puede garantizar se dice en voz alta**. Asigna un examen que vive en AVACOM Biblioteca, arma el de cada alumno, lo presenta en su tableta (con el bloqueo que el nivel de control exige y que la tableta realmente puede cumplir), guarda cada respuesta sin duplicados, entrega y califica en la escala interna de 0 a 100, deja pendiente de revisión lo que sólo un profesor puede puntuar y registra los incidentes sin castigar a nadie. **Anular un intento es siempre una decisión humana, motivada y con nombre.**

## Objetivos secundarios - Generales

1. Documentar el modelo de datos `m10_*`, el backend y la API `/api/evaluacion/` y el frontend de OPS y Student ([modelado-datos.md](modelado-datos.md), [backend.md](backend.md), [frontend.md](frontend.md)).
2. Bloquear la tableta durante el examen cuando el nivel es «Controlado» (Android: Device Owner y Lock Task; Windows: pantalla completa, filtro de teclado, Assigned Access o Shell Launcher) para evitar que el alumno salga de la aplicación, sin prometer lo que la plataforma no garantiza ([kiosk.md](kiosk.md)).
3. Pruebas unitarias y de API que cubran los escenarios del Maestro que no dependen del hardware (TST-004, 005, 012, 015, 017, 021, 026, 027, 030…038, 040…042, 077, 078; AC-073; INV-018) y dejar dicho cuáles sólo se comprueban en una tableta real.
4. Sin autoría de Claude en los commits.

> **Lo que este documento es.** El archivo `introduccion.md` de esta carpeta **llegó vacío** (0 bytes). Se reconstruyó con lo que el Documento Maestro Consolidado v1.0 fija para MOD-010 (propósito, frontera, capacidades CAP-059…067, funciones FUN-103…118, reglas, invariantes, eventos, permisos y escenarios), el guion «Ejecutar un examen crítico» (JRN-010) y la guía de bloqueo [kiosk.md](kiosk.md). Si el CTO tenía otro texto previsto, es lo primero que hay que reemplazar.
>
> **Fuentes.** Documento Maestro (MOD-010; CAP-059…067; FUN-103…118; BR-009, 062, 068, 069, 071…077, 138; INV-005, 010, 012, 013, 017, 018, 019, 024, 026; DEC-003, 009, 014, 019, 032; TST-004…042, 076…078; AC-046, AC-073; PAN-060…062 y PAN-120…123; MSG-033, MSG-036), el modelo v2 (`specs/analisis/segunda-version-modelo.md`, entidades `evaluacion` e `intento`) y el código de `backend/` a 2026-10-01.

------------------------------

## Requerimientos específicos

| # | Requerimiento | Dominio | Tabla | OPS | Student |
|---|---|---|---|---|---|
| 010-01 | Asignar una evaluación a un grupo o a alumnos con política de plazo (FUN-106, 107, 108; BR-073, BR-074) | Evaluación | `m10_asignacion` | Aplicar examen (PedirAsync, sin teclado) desde «Clase de hoy» | — |
| 010-02 | Nivel mínimo de modo examen y su degradación (FUN-105, FUN-118, DEC-009) | Evaluación | `m10_asignacion.nivel_declarado / nivel_examen` | Elegir y bajar el nivel; el sistema nunca preselecciona | — |
| 010-03 | Comparar el nivel con la capacidad declarada del dispositivo; admisión por el profesor (CAP-063, 064; FUN-116; BR-075, 076; TST-041) | Gestión de dispositivos | `m09_dispositivo.capacidad_control` (nuevo), `m10_admision` | Elegibilidad de tabletas (MSG-036) y decidir admisiones | Declarar la capacidad real al registrarse y en cada latido |
| 010-04 | Abrir un intento con cupo y versión congelada (FUN-109, BR-072, INV-012, INV-024) | Evaluación | `m10_intento_formal` | — | Antesala (PAN-120): duración, condiciones y qué se registra, antes de empezar |
| 010-05 | Guardar cada respuesta con secuencia y deduplicar (FUN-110, 111; CAP-065; BR-009, 071; INV-013; BR-138) | Evaluación | `m10_intento_formal.respuestas` | — | Cola local cifrada: la secuencia se persiste antes de enviar |
| 010-06 | Autocalificar al instante los tipos objetivos y dejar en cola los de revisión docente (FUN-112, 113; CAP-060, 062; BR-068, 069; NFR-012 ≤ 2 s) | Evaluación | `m10_intento_formal` (`puntaje`, `requiere_revision`) | Revisión del profesor: puntuar y publicar | — |
| 010-07 | Entregar, cerrar y marcar fuera de plazo (FUN-114, 115) | Evaluación | — | — | Entrega (PAN-123): confirma si faltan reactivos |
| 010-08 | Registrar incidentes sin invalidar (FUN-117; CAP-066; BR-077; INV-018) | Evaluación | `m10_incidente` (sólo inserción) | Incidentes por alumno, sin sonido ni alarma | Informar salidas, teclas bloqueadas, pantallas extra y el resultado del bloqueo |
| 010-09 | Reloj del nodo, punto de recuperación de 5 s, reconexión en 30 s, suspensión y reactivación (INV-010; TST-015, 034; PAN-061, 122) | Evaluación | `consumido_ms`, `reloj_desde`, `pausas` | Reactivar a uno o a todos los suspendidos | Pantalla «esperando a tu profesor»; el contador nunca se pone rojo |
| 010-10 | Bloquear la tableta durante el examen en nivel Controlado (JRN-010, DEC-009) | Gestión de dispositivos | `m10_intento_formal.bloqueo` | — | `IKioskService`: Android y Windows ([kiosk.md](kiosk.md)); script de aprovisionamiento |
| 010-11 | Permisos `assessment.*` (11 del Maestro y 5 del proyecto) | Acceso y RBAC | catálogo de `acceso` | — | — |
| 010-12 | Eventos `evaluacion.*.v1` (16 del Maestro) y auditoría (MOD-019) | Transversal | `m10_evento_salida` | — | — |
| 010-13 | Crear evaluaciones y añadir reactivos (FUN-103, 104; CAP-059) | — | — | — | **Trasladado a la biblioteca** (artículo 14): las rutas responden 409 nombrándola |
| 010-14 | Los diez tipos de actividad (CAP-059) | — | — | — | La biblioteca publica seis tipos de pregunta; los demás son la pregunta Q-79 |

------------------------------

## Entradas y salidas

**Entradas**

- Un examen instalado en AVACOM Biblioteca (`curso_ref`, `objeto_ref`, versión) y su calificador (`/v2/evaluate/batch`).
- Grupos y alumnos (`acceso`), tabletas y su capacidad declarada (`device_manager`), la clase de la que nace el examen (opcional).
- Latidos de 5 s, respuestas con su secuencia, incidentes e informes de bloqueo desde la tableta.
- Decisiones del profesor: nivel, plazo, admisión, reactivación, envío tardío, puntuación, anulación y liberación de resultados.

**Salidas**

- El examen de cada alumno (referencias, no texto; el texto se pide a la biblioteca con la misma semilla).
- Intento con reloj congelable, respuestas sin duplicados, calificación en escala 0–100 y revisión pendiente.
- El plan de bloqueo que cada tableta debe aplicar y el informe de lo que realmente logró.
- Incidentes, 16 eventos `evaluacion.*.v1` y asientos de la bitácora encadenada.
- Panel del profesor ordenado por quién lo necesita, expediente de sólo lectura y resultados.

**Además (objetivo secundario 2).** Lo que la tableta no puede garantizar se informa como `parcial` o `fallido` y llega al profesor; jamás se esconde, y tampoco anula el intento.
