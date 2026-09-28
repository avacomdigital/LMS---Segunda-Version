# 07 · Classroom Engine · Contrato de lanzamiento OPS → Student

| Campo | Valor |
|---|---|
| Módulo | MOD-007 · Classroom Engine · lo que la tableta del alumno **está obligada a mostrar** cuando el profesor proyecta o lanza algo desde AVACOM OPS |
| Estado | **Probado en vivo el 2026-09-28** con la app AVACOM LMS Student real (Windows) manejada por UI Automation y el lado del profesor por la API (las mismas llamadas que hace OPS), sobre un backend aislado. **Tres errores corregidos y verificados** (§5); el resto de hallazgos quedan como requisitos pendientes o decisiones (§3.4, §7) |
| Pregunta que responde | «¿El lanzamiento de la lección obliga a las tabletas a ver lo que presenta OPS?» → **El selector sí; el lanzamiento no** (§0) |
| Documentos hermanos | [03 · Journey](03-journey-clase-de-hoy.md) (P3 y S2) · [04 · Frontend](04-frontend-classroom-engine.md) · [01 · Modelo de datos](01-modelo-de-datos.md) (`m07_selector`, `m07_distribucion`, `m07_distribucion_entrega`) · [03-device-manager](../03-device-manager/00-modelo-y-api.md) (bloqueo por tableta) |

---

## 0 · Resumen · la respuesta

1. **Lo que obliga es el selector, no el lanzamiento.** Cada vez que el profesor proyecta algo (`POST …/selector/`: un objeto, una lámina, una página), la tableta lo pinta sola en **≤ 4 s** sin que el alumno toque nada, y con `seguimiento` activo no tiene mandos para irse. Comprobado con lámina 1 → lámina 2 → lectura → laboratorio → actividad. **Bloquear pantallas** impone «Mira al frente» encima de todo, también encima de un recurso que el alumno tenga abierto.
2. **El lanzamiento (`POST …/distribuciones/`, botones «Enviar a tabletas» y «Lanzar actividad» de P3) es una invitación, no una orden.** En la tableta aparece una **tarjeta** («Tu profesor te lo acaba de enviar» · **Abrir**) debajo de lo proyectado, que sigue en pantalla. Nada cambia hasta que el alumno toca **Abrir**: ese toque es lo que confirma la entrega y lo que OPS cuenta como «N de M tabletas lo abrieron». Si el alumno no toca, OPS ve «0 de M» indefinidamente.
3. **Mientras el alumno tiene abierto un recurso lanzado, la tableta deja de seguir al profesor.** Los cambios de selector se ignoran hasta que el alumno toca «Volver a la clase» o el profesor lo **retira** («Retirar de las tabletas» / «Cerrar recepción»), momento en que la tableta vuelve sola al selector vigente. Es lo que documentó 04 («lo que el profesor le envió sí se recorre a su ritmo mientras lo tenga abierto»); con dos recursos lanzados seguidos, el segundo no se puede abrir sin volver primero.
4. **Sin seguimiento la navegación libre es relativa**: aparecen los mandos y el alumno pasa de lámina, pero el **siguiente selector del profesor se impone** sobre lo que estuviera viendo. Reactivar el seguimiento no mueve la lámina hasta que el profesor declare otra.
5. **Tres errores corregidos** en esta entrega: liberar o activar el seguimiento no mostraba ni ocultaba los mandos hasta el siguiente cambio de selector; al volver de un recurso o al retirarlo quedaban mandos con el seguimiento activo; S1 conservaba el código de la clase anterior; y las tarjetas de pendientes se reconstruían en cada sondeo de 2 s (parpadeo y botón inaccesible entre una y otra).
6. **Quedan pendientes o por decidir**: un recurso lanzado sólo con `media_ref` (un medio suelto) no se puede abrir en la tableta; una tableta bloqueada por MOD-009 no se entera de que quedó fuera; **no existe un modo «abrir en las tabletas sin esperar al alumno»**, que es lo que la pregunta original da por hecho (§3.4 propone `apertura: automatica`).

---

## 1 · Cómo se probó

| Pieza | Cómo |
|---|---|
| Backend | Una segunda instancia en `127.0.0.1:8010` sobre una **copia** de `db.sqlite3` (`AVACOM_LMS_DB=<copia> manage.py runserver 127.0.0.1:8010`), para no tocar la clase abierta que OPS tenía en el 8000 |
| Profesor (OPS) | Las mismas llamadas que hace `ClaseSesionPage`: `POST /api/aula/sesiones/` (vía `leccion`, fuente `ejemplo`), `POST …/selector/`, `POST …/controles/`, `POST …/distribuciones/` y `…/{id}/cerrar/`, `POST …/avisos/`, `POST …/cerrar/`, siempre con `profesor_id=prof-prueba-claude` |
| Alumno (Student) | `Avacom.Lms.Student.exe` compilado para Windows, sin ratón ni foco: `InvokePattern` sobre los botones (teclado numérico de S1, «Entrar a la clase», «Abrir», «Volver a la clase», «Siguiente ▶», «Salir»), `ValuePattern` sobre las entradas de la pantalla de conexión, y **captura de la ventana** con `PrintWindow` más el texto visible por UI Automation en cada paso |
| Arnés | `tests/Avacom.Lms.Student.Uia/`: `lanzar-student.ps1`, `ui-student.ps1` (list · text · invoke · set · shot), `escenario_1_lanzamiento.py`, `escenario_2_recurso_abierto.py`, `escenario_3_dos_recursos.py`, `verificacion_correcciones.py`; capturas y textos en `salida/capturas/` |

Dos cosas que hay que saber para repetirla:

- **La tableta se readmite sola.** Al abrir «Clase en vivo», si `Preferences` guarda una participación (`aula_sesion`, `aula_participante`) de una clase que sigue activa, S1 salta directo a S2 sin escribir código (FUN-077). En la primera ejecución el Student de prueba se readmitió en la clase que OPS tenía abierta en el 8000; la prueba se rehizo en el 8010. Es el comportamiento esperado, pero cualquier prueba debe empezar por «Salir» o por un backend aparte.
- **UI Automation no ve lo que queda debajo de una `WebView`** (audio, video, laboratorio, pdf): con la lectura o el laboratorio proyectados, ni la tarjeta «Abrir» ni los mandos aparecen en el árbol, aunque sí en la captura. Las comprobaciones que necesitan pulsar botones se hacen con láminas de texto o con la actividad proyectadas; lo demás se verifica por captura.

---

## 2 · Los dos mecanismos

| | Selector (proyectar) | Lanzamiento (distribuir) |
|---|---|---|
| Llamada | `POST /api/aula/sesiones/{id}/selector/` `{objeto_ref, unidad_ref?}` o `{media_ref}` | `POST /api/aula/sesiones/{id}/distribuciones/` `{clase: recurso\|actividad, objeto_ref \| media_ref, alcance, participantes?, intentos_permitidos?, tiempo_limite_seg?, disponible_estudio?}` |
| En OPS | Tocar un objeto o una lámina de la secuencia; ◀ ▶ | Un solo botón: **«Lanzar actividad»** si el selector es una actividad, **«Enviar a tabletas»** si es lámina, lectura o laboratorio; «Cerrar recepción» / «Retirar de las tabletas» para terminarlo. Siempre a **todo el grupo** admitido; un recurso nuevo retira el anterior |
| Tabla | `m07_selector` (uno vigente por sesión; el historial queda) | `m07_distribucion` + `m07_distribucion_entrega` (una fila por destinatario: `pendiente · entregado · fallido`, `intentos`) |
| Evento | `aula.recurso.proyectado.v1` | `aula.actividad.lanzada.v1` (sólo actividades), `aula.actividad.cerrada.v1`, `aula.resultados.mostrados.v1` |
| Llega a la tableta como | `estado.selector` | `estado.pendientes[]` (sólo las abiertas dirigidas a ese participante, con su `entrega`) |
| Qué hace la tableta | Lo pinta al instante; sin mandos si `seguimiento` | Tarjeta con **Abrir**; al abrir confirma (`POST …/distribuciones/{id}/confirmar/`) y navega libre; **«Volver a la clase»** regresa al selector |
| Espera confirmación | No | Sí (entregas) |
| Cuánto tarda en verse | ≤ 4 s (sondeo de 2 s) | ≤ 4 s la tarjeta; la apertura depende del alumno |

---

## 3 · El contrato

### 3.1 · Reglas del backend (vigentes y probadas)

| # | Regla | Dónde |
|---|---|---|
| RL-01 | `clase` es `recurso` o `actividad`; se exige `objeto_ref` **o** `media_ref` (400 `datos_invalidos` si falta o si la clase o el alcance no existen) | `Distribuir` |
| RL-02 | Sólo se lanza sobre una sesión **abierta** (409 en suspendida o cerrada) | `dom.exigir_abierta` |
| RL-03 | `alcance: grupo` (por defecto) llega a **todos los admitidos**; `alcance: seleccion` a los `participantes` indicados (por `id` o `persona_id`) | `Distribuir` |
| RL-04 | Las tabletas **bloqueadas o retiradas** (MOD-009) quedan fuera aunque estén en la selección y constan en `excluidos_bloqueados` | `_con_bloqueo` |
| RL-05 | Una **actividad** exige al menos un destinatario: 409 `sin_participantes_admitidos` con `excluidos_bloqueados`; un **recurso** se crea aunque no haya destinatarios (`entregas.total: 0`) | `Distribuir` |
| RL-06 | El objeto debe existir en el curso vigente (404) y no ser de otro módulo (un examen es 400: «es de MOD-010»); como actividad sólo se lanza un objeto `activity` (400) | `cur.localizar` |
| RL-07 | `intentos_permitidos` y `tiempo_limite_seg` son enteros ≥ 0 (400 si no); una actividad además prepara la asignación en MOD-010 (`asignacion_ref`) | `validar_regla_entera`, `preparar_asignacion` |
| RL-08 | `rotulo`, `leccion_ref`, `objeto_tipo` y `curso_ref` se completan desde el curso si no vienen | `Distribuir` |
| RL-09 | Cada destinatario tiene una entrega `pendiente` que la tableta pasa a `entregado` (o `fallido`) con `POST …/distribuciones/{id}/confirmar/` `{participante_id}`; `intentos` cuenta las confirmaciones | `ConfirmarEntrega` |
| RL-10 | El profesor cierra con `POST …/distribuciones/{id}/cerrar/` (`abierta: false`, `cerrada_en`); cerrada, deja de venir en `pendientes` y no acepta más confirmaciones | `CerrarDistribucion` |
| RL-11 | `GET …/estado/?participante=` devuelve en `pendientes` sólo las distribuciones **abiertas** que tienen entrega para ese participante, con `entrega` y `clase` | `EstadoParaTableta` |
| RL-12 | El lanzamiento y el selector son independientes: lanzar no cambia el selector, proyectar no cierra nada | — |

### 3.2 · Reglas de OPS (P3, vigentes)

| # | Regla |
|---|---|
| RO-01 | El botón de lanzamiento se habilita sólo con un selector con `objeto_ref` y la sesión abierta; con `media_ref` suelto (un medio proyectado) **no se puede lanzar** desde OPS |
| RO-02 | Con una actividad abierta el mismo botón dice «Cerrar recepción»; un recurso nuevo **retira el anterior** antes de enviarse (sólo un recurso abierto a la vez) |
| RO-03 | El panel «Enviado a las tabletas» muestra «N de M tabletas lo abrieron», «Sin destinatarios» si M = 0, y «K tabletas bloqueadas no lo recibieron»; **«Retirar de las tabletas»** cierra la distribución |
| RO-04 | `sin_participantes_admitidos` se traduce a «Todavía no hay tabletas conectadas» o «Todas las tabletas conectadas están bloqueadas» |

### 3.3 · Reglas de Student (S2, vigentes tras las correcciones)

| # | Regla | Estado |
|---|---|---|
| RS-01 | El selector se pinta en ≤ 4 s (sondeo de 2 s); cambiar de lámina no vuelve a pedir el objeto; cambiar de objeto pide `GET …/objetos/{ref}/` | ✅ |
| RS-02 | Con `seguimiento: true` no hay mandos; con `false` aparecen **al instante** y el alumno navega dentro del objeto proyectado | ✅ corregido |
| RS-03 | `pantallas_bloqueadas: true` muestra «Mira al frente» por encima de todo, incluido un recurso abierto; al liberar, vuelve a lo que había | ✅ |
| RS-04 | Cada pendiente abierta es una tarjeta (verde si actividad, azul si recurso) con «Abrir»; la tarjeta **no** reemplaza lo proyectado | ✅ |
| RS-05 | «Abrir» confirma la entrega y muestra el objeto con mandos propios; la tarjeta pasa a «Recibido · ábrelo cuando quieras» y el botón a «Volver a la clase» | ✅ |
| RS-06 | Con un pendiente abierto se ignoran los cambios de selector; los demás pendientes muestran «Volver a la clase» (no se abren directamente) | ✅ (por diseño; ver Q-62) |
| RS-07 | «Volver a la clase» o el retiro por el profesor devuelven al selector vigente **sin mandos** si hay seguimiento | ✅ corregido |
| RS-08 | Las tarjetas sólo se reconstruyen cuando cambian (ids, entrega, si hay una abierta), no en cada sondeo | ✅ corregido |
| RS-09 | Los avisos son bandas no bloqueantes de 8 s; la sesión `suspendida` pone banda fija; `cerrada` muestra «La clase terminó» y vuelve al menú; `expulsado` sale | ✅ |
| RS-10 | S1 vuelve con las casillas vacías; con una participación guardada en una clase activa se readmite sola | ✅ corregido / ✅ |
| RS-11 | Un pendiente con sólo `media_ref` se abre mostrando el medio | ❌ pendiente (B-05) |
| RS-12 | Una tableta bloqueada ve por qué no recibe lanzamientos | ❌ pendiente (B-06) |

### 3.4 · Requisitos que faltan (propuesta)

| # | Requisito | Por qué | Cómo |
|---|---|---|---|
| RP-01 | **Apertura automática.** El profesor debe poder enviar un recurso que se **abra solo** en las tabletas, sin esperar al toque del alumno | Es lo que la pregunta original da por hecho y lo que un docente espera de «Enviar a tabletas» en clase sincronizada. Hoy sólo el selector obliga, y el selector no cuenta entregas | `POST …/distribuciones/` gana `apertura: "tarjeta"` (hoy) \| `"automatica"`. Con `automatica`, S2 abre el objeto al recibirlo, confirma la entrega él mismo y muestra la tarjeta ya en «Recibido». OPS: el botón «Enviar a tabletas» abre automáticamente por defecto y una opción larga (mantener pulsado o segundo botón) envía «para después». Las actividades siguen como tarjeta: responder es voluntario y tiene intentos |
| RP-02 | **El selector manda también con un recurso abierto cuando el profesor lo pide.** Un cambio de selector con `seguimiento` activo debería poder cerrar lo que la tableta tenga abierto | Hoy un alumno con un recurso abierto se desconecta de la proyección hasta que él o el profesor lo cierren (§0.3) | Opción A: el backend cierra los recursos abiertos al declarar un selector nuevo (`retirar_recursos: true` en `POST …/selector/`). Opción B: S2 vuelve al selector cuando cambia y muestra la tarjeta como «Recibido». Decidir con el CTO (Q-62) |
| RP-03 | **Medios sueltos.** Un lanzamiento (o un selector) con sólo `media_ref` se muestra en la tableta (imagen, video, audio, pdf con el visor por bloques que ya existe) | La API lo admite, el backend lo registra y la tableta responde «No se pudo abrir lo que te enviaron» (B-05); OPS hoy no lo ofrece (RO-01), pero un cliente futuro sí | `AulaContenidoView.MostrarMedio(MedioAula)` y en S2 rama `media_ref` en `PintarSelectorAsync` y `AbrirPendienteAsync`; el medio sale de `GET …/cursos/{ref}/` o de un endpoint nuevo `GET …/cursos/{ref}/medios/{media_ref}/ficha/` |
| RP-04 | **Aviso de tableta bloqueada.** Cuando `participante.dispositivo_bloqueado` es verdadero, S2 muestra una banda fija «Tu tableta está bloqueada: no recibirás lo que el profesor envíe» | Hoy la tableta sigue viendo el selector y «Conectado» sin saber que quedó fuera de los lanzamientos (RL-04) | S2 lee `estado.participante.dispositivo_bloqueado` (ya viaja) |
| RP-05 | **Reintento de entrega.** Si `GET …/objetos/{ref}/` falla al abrir, la tableta confirma `fallido` con el motivo y reintenta al siguiente sondeo | Hoy la entrega queda `entregado` aunque el objeto no se pudiera abrir (se confirma antes de pedirlo) | Confirmar después de obtener el objeto; `estado: fallido` + `detalle` |
| RP-06 | **Selección de destinatarios desde OPS** (`alcance: seleccion`) | El backend ya lo soporta; P3 sólo lanza al grupo | Hoja de selección en el panel de participantes |

---

## 4 · Resultados

Cuatro tandas sobre `example.json` (curso «Estados de la materia», lección «Los tres estados»), un alumno (`alumno-prueba`, tableta `student-DESKTOP-…`). «Captura» remite a `tests/Avacom.Lms.Student.Uia/salida/capturas/` cuando se repite la prueba.

### 4.1 · Tanda 1 · el selector obliga; el lanzamiento invita

| Paso | Profesor (API = OPS) | Tableta | Veredicto |
|---|---|---|---|
| Entrar | sesión nueva, código de 6 dígitos | S1 → S2 con «Presentación · Todo lo que nos rodea es materia · Lámina 1 de 3»; sin mandos; backend: participante `conectado` con su tableta | ✅ |
| Proyectar lámina 2 | `selector {l1-lecture, l1-lecture-s2}` | «Lámina 2 de 3 · Tres estados, tres formas de ordenarse» en ≤ 4 s, sin tocar nada | ✅ |
| Proyectar la lectura | `selector {l1-explanation}` | «Lectura · Escucha y repasa · Página 1 de 2» con el audio | ✅ |
| Enviar a tabletas la presentación | `distribuciones {recurso, l1-lecture}` | Tarjeta azul «Todo lo que nos rodea es materia · Tu profesor te lo acaba de enviar · **Abrir**» debajo de la lectura, que sigue proyectada (captura `05`); backend `pendientes[0].entrega = pendiente`, OPS «0 de 1 tabletas lo abrieron» | ✅ (invitación, no orden) |
| Proyectar el laboratorio (sin abrir el recurso) | `selector {l1-lab-phet}` | La tableta sigue al laboratorio: la tarjeta no la retiene mientras no se abra | ✅ |
| Bloquear pantallas | `controles {bloqueo, true}` | «Mira al frente · Tu profesor está explicando» a pantalla completa (captura `08`) | ✅ |
| Liberar | `controles {bloqueo, false}` | Vuelve al laboratorio | ✅ |
| Retirar el recurso | `…/cerrar/` | La tarjeta desaparece | ✅ |
| Lanzar actividad | `selector {l1-activity}` + `distribuciones {actividad, l1-activity, intentos 2}` | Vista previa de «Practica: los tres estados · 6 preguntas · 13 pts · Retroalimentación inmediata · 2 intento(s)» y tarjeta verde «Abrir»; sin claves ni botón de enviar | ✅ |
| Abrir | — | Se confirma la entrega (backend `entregadas: 1`); la actividad se ve con sus preguntas (vista previa: responder es de MOD-010) | ✅ |
| Aviso | `avisos {Dos minutos para terminar}` | Banda «Aviso de tu profesor · Dos minutos para terminar» | ✅ |
| Terminar | `…/cerrar/` | «La clase terminó · Tu profesor cerró la clase. Tu trabajo quedó guardado.» → menú | ✅ |

### 4.2 · Tanda 2 · el recurso abierto frente al selector

| Paso | Tableta | Veredicto |
|---|---|---|
| Enviar la presentación con la lámina 1 proyectada y **Abrir** | Presentación con mandos; entrega confirmada («1 de 1 lo abrieron»); el alumno pasa a la lámina 2 por su cuenta | ✅ |
| El profesor proyecta la actividad mientras el recurso está abierto | **La tableta se queda en la lámina 2 del recurso**: el selector se ignora (captura `24`) | ⚠️ por diseño (RP-02, Q-62) |
| Bloquear / liberar con el recurso abierto | «Mira al frente» se impone; al liberar vuelve al recurso | ✅ |
| Liberar el seguimiento sin cambiar el selector | **No aparecían los mandos** hasta el siguiente selector | ❌ → corregido (B-01) |
| Sin seguimiento, el profesor proyecta otra lámina | Se impone sobre la que el alumno eligió | ✅ (navegación libre relativa) |
| Activar el seguimiento de nuevo | **Los mandos no desaparecían** | ❌ → corregido (B-01) |
| Bloquear la tableta por MOD-009 | No verificable en esta base: `GET /api/dispositivos/` responde 409 `no_instalado` (sin organización instalada, la tableta no se registra y `participante.dispositivo_id` queda vacío). Por código: la actividad es 409 y el recurso se crea sin destinatarios (`test_dispositivos`); la tableta no se entera (RP-04) | ⚠️ no probado en vivo |

### 4.3 · Tanda 3 · dos recursos seguidos

| Paso | Tableta | Veredicto |
|---|---|---|
| Recurso A (presentación) abierto | Mandos; tarjeta «Recibido · ábrelo cuando quieras» con «Volver a la clase» | ✅ |
| Recurso B (pdf suelto por `media_ref`) lanzado con A abierto | Segunda tarjeta «Guía del laboratorio · Tu profesor te lo acaba de enviar»; **las dos** dicen «Volver a la clase»: B no se abre sin volver; backend B `pendientes: 1` | ✅ (por diseño) |
| Volver a la clase | Selector (lámina 1) y las dos tarjetas con «Abrir»; **quedaban los mandos** con seguimiento activo | ❌ → corregido (B-02) |
| Retirar A | Desaparece su tarjeta, queda B | ✅ |
| Abrir B | Se confirma la entrega, pero la tableta dice **«No se pudo abrir lo que te enviaron · No se encontró lo que se pedía»**: no hay visor de medio suelto | ❌ pendiente (B-05) |
| Retirar B con B «abierto» | Vuelve al selector sin tarjetas | ✅ |

### 4.4 · Tanda 4 · verificación de las correcciones (Student recompilado)

| Comprobación | Veredicto |
|---|---|
| Liberar el seguimiento muestra los mandos sin esperar a un cambio de selector | ✅ |
| Activar el seguimiento oculta los mandos al instante y no mueve la lámina hasta el siguiente selector | ✅ |
| El siguiente selector del profesor vuelve a mandar | ✅ |
| La tarjeta del recurso es estable entre sondeos (cuatro lecturas seguidas la ven) | ✅ |
| Volver a la clase con seguimiento activo: sin mandos | ✅ |
| Retirar el recurso abierto: sin mandos, se ve el selector, sin tarjetas | ✅ |
| S1 vuelve con las casillas vacías | ✅ |

Backend: los 26 casos de `classroom_engine.tests.test_sesiones` y `test_dispositivos` siguen en verde (selector, controles, lanzar-confirmar-cerrar, avisos, cierre, tableta bloqueada excluida).

---

## 5 · Errores encontrados

| # | Síntoma | Causa | Corrección | Estado |
|---|---|---|---|---|
| B-01 | Liberar o activar el seguimiento desde OPS no mostraba ni ocultaba los mandos de la tableta hasta que el profesor cambiaba de lámina u objeto | `AulaContenidoView.PuedeNavegar` era una propiedad automática; los mandos sólo se pintaban dentro de `Mostrar()`, y S2 no vuelve a llamar a `Mostrar()` si el selector no cambió | `PuedeNavegar` repinta los mandos de la unidad en pantalla al cambiar (`_unidadesEnPantalla`, `_indiceEnPantalla`) | ✅ corregido y verificado |
| B-02 | Al tocar «Volver a la clase» o al retirar el profesor el recurso abierto, la tableta volvía al selector **con** mandos aunque el seguimiento estuviera activo | `AbrirPendienteAsync` y `PintarPendientes` limpiaban `_mostrandoPendiente` sin bajar `PuedeNavegar`; el siguiente sondeo lo bajaba, pero sin repintar (B-01) | Se fija `PuedeNavegar = !seguimiento` antes de volver a pintar el selector, en los dos caminos | ✅ corregido y verificado |
| B-03 | Al volver a S1 (clase terminada, salir) seguía escrito el código anterior y «Entrar a la clase» lo mandaba: «Ese código no es» | `_codigo` y las casillas viven en la página, que Shell reutiliza | `OnAppearing` limpia el código (`Tecla("Borrar")`) | ✅ corregido y verificado |
| B-04 | Las tarjetas de pendientes se reconstruían en **cada** sondeo (2 s): parpadeo y el botón «Abrir» desaparecía del árbol de accesibilidad entre una y otra (la automatización fallaba al pulsarlo) | `PintarPendientes` hacía `Clear()` y volvía a crear todo en cada refresco | Se guarda una firma (`id:entrega:rotulo` + si hay una abierta) y sólo se reconstruye cuando cambia | ✅ corregido y verificado |
| B-05 | Un recurso lanzado sólo con `media_ref` («Guía del laboratorio», pdf) confirma la entrega y luego dice «No se pudo abrir lo que te enviaron» | S2 pide `GET …/objetos/{objeto_ref}/` con `objeto_ref` vacío; no hay visor de medio suelto (lo mismo le pasa a un selector con `media_ref`, que S2 muestra como «Esperando a tu profesor») | RP-03 | ❌ pendiente |
| B-06 | Una tableta bloqueada por MOD-009 sigue viendo el selector y «Conectado» sin saber que no recibirá lanzamientos | S2 no lee `participante.dispositivo_bloqueado` | RP-04 | ❌ pendiente |
| B-07 | La entrega se confirma **antes** de pedir el objeto: si la petición falla, OPS cuenta «lo abrió» aunque no se abrió | Orden de `AbrirPendienteAsync` | RP-05 | ❌ pendiente |
| B-08 | En un nodo sin organización instalada la tableta no se registra en MOD-009 (`409 no_instalado`), `participante.dispositivo_id` queda vacío y el bloqueo por tableta no es posible; nada lo avisa en OPS | `device_manager.servicios` calla el 409 al unirse | Mostrar en el panel de participantes «Tableta sin registrar (nodo sin instalar)» y en `GET /api/aula/fuente/` o `sesiones/{id}/` un `dispositivos_registrados: false` | ❌ pendiente (fuera del alcance de MOD-007) |
| B-09 | El video de la lámina 3 muestra «Este video no está en el equipo del aula todavía» | El manifiesto de ejemplo no trae el MP4 (documentado en 04) | — | esperado |

---

## 6 · Lo que cambió en el código

| Capa | Archivo | Cambio |
|---|---|---|
| MAUI · Ui | `Controls/AulaContenidoView.cs` | `PuedeNavegar` con campo y repintado de mandos al cambiar; `_unidadesEnPantalla`/`_indiceEnPantalla` se fijan en `MostrarUnidades` y se limpian en `Mostrar` y `MostrarVacio` |
| MAUI · Student | `Pages/ClaseSiguiendoPage.xaml.cs` | `PintarPendientes` con firma (reconstruye sólo al cambiar) y baja `PuedeNavegar` al retirarse lo abierto; «Volver a la clase» fija `PuedeNavegar` antes de repintar |
| MAUI · Student | `Pages/ClaseUnirsePage.xaml.cs` | `OnAppearing` limpia el código |
| Pruebas | `tests/Avacom.Lms.Student.Uia/` | **Nuevo**: arnés de UI Automation (`ui-student.ps1`, `lanzar-student.ps1`) y los cuatro guiones de esta prueba (`AVACOM_AULA_URL` para el backend, por defecto `127.0.0.1:8010`) |
| Docs | `README.md` | Índice |

OPS comparte `AulaContenidoView` (modo docente, `PuedeNavegar = true` fijo): compila sin cambios de comportamiento.

---

## 7 · Cómo repetir la prueba

```
copy backend\db.sqlite3 %TEMP%\db-prueba.sqlite3
set AVACOM_LMS_DB=%TEMP%\db-prueba.sqlite3
backend\.venv\Scripts\python backend\manage.py runserver 127.0.0.1:8010 --noreload
dotnet build src\Avacom.Lms.Student\Avacom.Lms.Student.csproj -f net10.0-windows10.0.19041.0
powershell -File tests\Avacom.Lms.Student.Uia\lanzar-student.ps1
```

En la pantalla de conexión del Student escribir `http://127.0.0.1:8010` (o con el arnés: `ui-student.ps1 -Accion set -Nombre 192.168 -Valor http://127.0.0.1:8010`), «Entrar al aula», «Clase en vivo», y entonces:

```
python tests\Avacom.Lms.Student.Uia\verificacion_correcciones.py
python tests\Avacom.Lms.Student.Uia\escenario_1_lanzamiento.py
```

Cada guion imprime `OK`/`FALLA` por comprobación y deja capturas y textos en `salida\capturas\`. Al terminar, devolver la dirección del aula del Student a la del backend real: las `Preferences` son las mismas que usa la instancia del usuario.

---

## 8 · Preguntas para el CTO

| # | Pregunta | Efecto |
|---|---|---|
| Q-61 | ¿«Enviar a tabletas» debe **abrir** el recurso en las tabletas (apertura automática, RP-01) o basta la tarjeta? ¿Y una actividad? | Define el botón de P3 y el campo `apertura` |
| Q-62 | Con un recurso abierto en la tableta, ¿un cambio de selector con seguimiento activo debe **cerrarlo** (RP-02) o el alumno conserva lo que abrió? | Hoy lo conserva; el profesor pierde la sincronía hasta retirarlo |
| Q-63 | ¿Un medio suelto (imagen, pdf, video) se proyecta y se lanza por sí mismo (RP-03) o siempre dentro de un objeto? | Si sí, hace falta el visor de medio en Student y el botón en OPS |
| Q-64 | ¿La tableta bloqueada debe seguir viendo la proyección (hoy sí) o quedar en «Mira al frente» hasta que se desbloquee? | RP-04 |
| Q-65 | ¿Se cuenta como «lo abrió» el toque en «Abrir» aunque el objeto no cargue (B-07)? | RP-05 |
