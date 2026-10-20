# 15 · Licenciamiento (MOD-018) · Qué funciones se podrían perder

| Campo | Valor |
|---|---|
| Estado | **Análisis** (2026-10-20), hecho **antes** de construir las Fases 2 y 3. No cambia código: dice dónde puede doler y qué hay que cuidar. |
| Pregunta | ¿Qué funciones del producto puede perder un colegio por culpa del licenciamiento: **a propósito** (la licencia las apaga) y **por accidente** (un fallo, un reloj raro, un cambio de equipo, un error nuestro)? |
| Base | Inventario automático de las rutas reales (método + ruta) recorriendo el resolvedor de Django, clasificadas con `backend/licenciamiento/dominio/rutas.py`, más lectura de las pantallas de OPS y Student que las llaman. **Dos fotos:** la **inicial** (2026-10-20 a las 10:00: 307 pares, 260 rutas distintas; 100 intocables · 170 núcleo · 37 licenciables) con la que se hallaron los hallazgos, y la **actual** (≈ 10:55: 316 pares, 269 rutas distintas; **109 · 178 · 29**), ya con la ruta `/api/licencia/` y con H-02 y H-03 adoptados por la otra sesión. |
| Se lee con | [requerimientos.md](requerimientos.md) (qué se va a construir), [00-prompt.md](00-prompt.md) (decisiones P-n y reglas R-n) y, cuando existan, `01-diseno.md` y `03-pruebas.md` de la otra sesión. |
| Convención | **H-n** = hallazgo que cambia el diseño · **F-n** = modo de fallo · **E-n** = escenario del calendario escolar. |

---

## 0 · En una página

**Lo más importante.** Si todo sale mal con la licencia, lo máximo que se pierde son **29 de 316 rutas** (9 %): 15 de reportes, 8 de búsqueda, la importación masiva y cinco ajustes de administración avanzada (crear roles, crear, adoptar y versionar escalas de calificación, y reconstruir derivados). Con la tabla inicial eran 37 de 307 (12 %): la diferencia son los **boletines y las exportaciones** (H-03) y los **interruptores de seguridad** (H-02), que ya no se licencian. **Ninguna ruta de una clase, un examen, el modo estudio, el inicio de sesión ni la lectura de calificaciones puede apagarse** (las 109 rutas intocables). Eso es lo que prometen R-01 y R-04, y este análisis comprueba que la tabla actual lo cumple para todo lo que existe hoy.

**Lo que sí hay que corregir antes de construir** (verificado en el código):

| # | Riesgo | Efecto si no se corrige | Quién decide |
|---|---|---|---|
| H-01 | «Visitantes y actividad» (vincular a un visitante con un alumno) **sólo se alcanza desde la pantalla de Reportes** | Con Reportes apagado, esa función queda inalcanzable aunque su API siga abierta | Diseño de OPS (otra sesión) |
| H-02 | Los interruptores de seguridad (cerrar el registro de profesores y alumnos, apagar visitantes) usan **la misma ruta** que la tabla pone bajo «administración avanzada» | Con la licencia degradada **nadie podría cerrar esas puertas** | Tabla de rutas (otra sesión) |
| H-03 | `/api/reportes/` entero es licenciable: incluye `boletines/` y `exportaciones/`, que son la **única vía para exportar calificaciones** | Choca con Q-L12 y R-03: el vencimiento no debe tomar de rehén las notas del colegio | CTO (Q-L12); propuesta: núcleo |
| H-04 | OPS se registra como equipo `MASTER` | Si cuenta contra el cupo, el aula pierde un equipo de alumno | Cupo (otra sesión) |
| H-05 | Las identidades nacen en **un solo punto** (`CrearUsuario._crear`); el visitante nace aparte | Si el visitante cuenta o se bloquea, se viola RN-33 («entrar como visitante nunca se bloquea») | Cupo (otra sesión) |
| H-06 | La importación atrapa `ErrorAcceso` por fila | Un cupo agotado que no herede de ese error **aborta el lote entero** | Cupo (otra sesión) |
| H-07 | `device_manager.servicios.resolver` lo usan el inicio de sesión, el aula, el **examen** y el estudio | Poner el cupo de equipos ahí **impide abrir un examen** en una tableta nueva (R-02) | Cupo (otra sesión) |
| H-08 | Una licencia con `desde` posterior al reloj del equipo se toma como «aún no vigente» y el nodo vuelve a la evaluación | Tras activar, un equipo con el reloj atrasado minutos puede quedar en evaluación vencida (degradado) | Estado + emisor |
| H-09 | La marca alta del reloj sólo sube | Un salto **accidental** al futuro (fecha 2038 de BIOS) la deja alta para siempre | CTO / emisor |
| H-10 | Los avisos sólo los ve quien entra con rol administrador o técnico | En 30 días de evaluación nadie con ese rol abre OPS y el colegio se entera cuando ya está degradado | OPS + instalador |
| H-11 | Una licencia con lista **explícita** de capacidades no habilita capacidades licenciables añadidas después | Una actualización «apaga» un módulo nuevo a quien no tenga `*` | Emisor (plan por omisión) |
| H-12 | La llave pública de producción **todavía no existe** (ceremonia pendiente del CTO) | Un instalador sin ella no puede validar ninguna licencia real: todos los clientes caen a la evaluación y a los 30 días a degradada | Puerta de liberación |
| H-13 | El instante confiable es `max(reloj, marca alta)`: si el reloj queda por debajo de la marca, ese máximo es un valor **fijo** y el tiempo de la licencia **se congela** hasta que la hora de pared alcance la marca | **Atrasar la fecha alarga la licencia lo que se atrasó** (medido: con 30 días de vigencia y 30 de gracia, atrasar la fecha 100 días degrada a los 151 días reales en vez de a los ~51), con un solo cambio de fecha. Una pila de BIOS agotada (el reloj vuelve a 2010) la vuelve inmortal y la evaluación no termina nunca. Es lo contrario de lo que promete P-06 | Nodo (otra sesión) |
| H-14 | El tope de 72 h del aplazamiento por un salto sospechoso hacia adelante se mide en esa misma línea de tiempo congelada | **Adelantar la fecha y devolverla aplaza la degradación lo que duró el salto** (un año → 368 días en vez de 3), y un nodo ya degradado recupera sus cuatro módulos (pasa a `en_gracia`). Cuesta dos cambios de fecha | Nodo (otra sesión) |
| H-15 | El nodo acepta una licencia **firmada** con un límite en **0** (equipos, usuarios, concurrentes normales o en pico); sólo exige `normal ≤ pico` | Un 0 no limita: **detiene**. Con concurrencia 0 el aula responde «aula llena (0 dispositivos)» al **primer** alumno; con equipos o usuarios en 0 no se registra ninguna tableta ni persona nueva. El emisor oficial no emite ceros (lo valida), pero ningún archivo, venga de donde venga, puede detener una clase (R-01) | Nodo (otra sesión) |

**Estado de los hallazgos (≈ 11:40):** H-02 a H-07 ya están **adoptados** por la otra sesión (la ruta `politicas/` y los boletines y exportaciones salieron de la tabla de licenciables; el cupo de usuarios vive sólo en `CrearUsuario._crear`; el de equipos sólo en el latido y el alta manual, con `resolver` intacto y el equipo `MASTER` fuera). **H-08 también**: el nodo acepta y da por vigente una licencia que empieza hasta un día en el futuro (`tolerancia_inicio_ms`, la misma al activar y al calcular el estado) y el emisor retrasa `desde` un día. **H-09 queda sin decidir** como pregunta para el CTO (Q-L13, con el hueco de la línea de tiempo adelantada). **Pendientes:** H-01 (pantalla), H-10 (aviso), H-11 y H-12. **Nuevos, de la verificación independiente (≈ 11:30–12:00), confirmados con pruebas contra el nodo real: H-13 y H-14** (el reloj de confianza se congela cuando la fecha se atrasa, y eso deja sin efecto el tope de 72 h del aplazamiento) **y H-15** (un límite en 0 firmado detiene la clase).

**Los cinco modos de fallo con más probabilidad de doler** (§8): F-03 (reloj de fábrica atrasado al activar), F-07 (cambio de placa), F-08 (reinstalar Windows con SMBIOS de relleno), F-33 (nadie ve el aviso) y E-1 (vencer en vacaciones).

---

## 1 · Método

1. **Inventario.** Un script recorre el resolvedor de rutas de Django (todas las apps, cada método que implementa la vista) y pregunta a `licenciamiento.dominio.rutas` si cada una es intocable, licenciable (y de qué capacidad) o núcleo. Resultado: 307 pares, de los que 100 son intocables, 170 núcleo y 37 licenciables.
2. **Uso real.** Para cada ruta licenciable se buscó qué pantalla de OPS o Student la llama (lo que se apaga **desde la vista de la persona**, no sólo en el servidor).
3. **Camino de los datos.** Se siguió dónde nace una identidad y un equipo (para el cupo), qué clientes descartan su cola ante un 4xx (R-02) y quién llama a `resolver`.
4. **Modos de fallo.** Se enumeró lo que puede salir mal con el reloj, la huella, los archivos, el software y la operación, y para cada uno qué se pierde, qué se conserva y cómo se prueba.

Límite del análisis: es de **diseño y lectura de código**. Nada de esto sustituye las pruebas en vivo (ver §11 y `03-pruebas.md`).

## 2 · Las tres clases de función

| Clase | Qué es | Qué le hace la licencia | Cómo se decide |
|---|---|---|---|
| **A · Intocable** | Lo que mantiene una clase, un examen, un estudio o el propio inicio de sesión | **Nunca** responde 402 por capacidad ni por una falla de la licencia. No se cuenta. El WebSocket del aula ni pasa por el middleware | Lista blanca derivada de los `urls.py` reales (R-01) |
| **B · Núcleo** | Todo lo demás que no está en la tabla de licenciables: gestión, lectura del expediente y de las calificaciones, bitácora, biblioteca, cola de medios, gestión de evaluaciones, respaldo | No se apaga por vencimiento. Sólo el **alta** de una identidad o de un equipo nuevo puede toparse con el cupo | Por omisión: lo que no se nombra, pasa |
| **C · Licenciable** | La tabla «método + ruta → capacidad» | Responde `402 no_disponible_por_licencia` si la capacidad no está habilitada (degradada, o no incluida en la licencia) | `rutas.py` |

Regla de oro del análisis: **una función nueva es núcleo salvo que alguien la ponga en la tabla C**. Es la única forma de que un olvido no apague una clase.

## 3 · Inventario por módulo

Foto **actual** (≈ 10:55), con la ruta de la licencia y con H-02 y H-03 adoptados; entre paréntesis, la foto inicial donde difiere.

| Módulo (app) | A · Intocable | B · Núcleo | C · Licenciable | Total |
|---|---:|---:|---:|---:|
| acceso | 20 | 43 (42) | 2 (3) | 65 |
| aula (`classroom_engine`) | 30 | 0 | 0 | 30 |
| modo estudio | 32 | 0 | 0 | 32 |
| evaluación | 15 | 41 | 0 | 56 |
| calificaciones (`gradebook`) | 0 | 32 | 4 | 36 |
| reportes (`reporting`) | 0 | 7 (0) | **15 (22)** | 22 |
| búsqueda (`search`) | 0 | 0 | **8** | 8 |
| **licencia (`licenciamiento`)** | 9 | 0 | 0 | 9 |
| dispositivos | 1 | 5 | 0 | 6 |
| auditoría y logs | 1 | 11 | 0 | 12 |
| biblioteca | 0 | 13 | 0 | 13 |
| cola de medios | 0 | 6 | 0 | 6 |
| expediente (y `/health/`) | 1 | 20 | 0 | 21 |
| **Total** | **109 (100)** | **178 (170)** | **29 (37)** | **316 (307)** |

**Lo que hay en A (109; 100 sin la licencia).** Inicio y cierre de sesión (incluido visitante y traspaso entre apps), instalación, configuración pública, PIN maestro, «mi cuenta», registro propio de profesores y de alumnos, PIN del alumno, canje de autorizaciones temporales, grupos del aula; **todo** el aula (30) y **todo** el modo estudio (32); de evaluación, lo que usa el alumno (`estudiantes`, `mias`, `antesala`, abrir intento, `estado`, `latido`, `preguntas`, `medios`, `respuestas`, `incidentes`, `bloqueo`, `entregar`, `resultado`); el latido de los equipos, los logs de los clientes y `/health/`. (La ruta `…/respuestas/<pregunta>/puntuar/` —puntuar del profesor— cae en A porque el patrón es más ancho que su intención: no pierde nada, sólo está más protegida de lo necesario.)

**Lo que hay en C (29; 37 en la foto inicial).**

| Capacidad | Rutas | Qué quita al colegio | Quién la usa hoy en pantalla |
|---|---:|---|---|
| `reportes` | 15 (22) | Reportes de clase, grupo, alumno y uso de equipos; filtros, recientes, estado, actualizar y reconstruir. **Ya no** los boletines ni las exportaciones (H-03): siguen siendo la vía para sacar las calificaciones | Tesela **Reportes** de OPS y sus pantallas (inicio, elegir, clase, grupo, alumno, uso, estado) |
| `busqueda` | 8 | Buscar evaluaciones, estudios y clases; índice, sinónimos | Tesela **Buscar** de OPS |
| `importacion` | 1 | Alta **masiva** de usuarios por archivo (`POST usuarios/importar/`) | **Ninguna pantalla de OPS** la usa hoy (sólo clientes de API) |
| `administracion_avanzada` | 5 (6) | Crear roles; adoptar, crear y versionar escalas de calificación; reconstruir derivados del libro. **Ya no** cambiar políticas de acceso (`PUT politicas/<perfil>/`, H-02) | `CalificacionesConfigPage` (escalas) |

**Lo que queda en B y puede sorprender** (no se apaga, pero conviene saberlo): crear un usuario a mano (`POST usuarios/`), el padrón (`padron/estudiantes/`, grupos, matrícula), publicar y ajustar calificaciones, asignar y aplicar evaluaciones, la bitácora y su exportación, la cola de medios, la biblioteca y los equipos (`GET/POST dispositivos/`, bloquear, asignar, liberar).

## 4 · Qué se apaga en cada estado

Estados de `estado.py` (el estado **sale** del tiempo y de los hechos; no se guarda). «ON» = la capacidad responde; «OFF» = `402 no_disponible_por_licencia`.

| Estado | Cuándo | `reportes` · `busqueda` · `importacion` · `administracion_avanzada` | Clase, examen, estudio, notas, bitácora | Cupo que rige |
|---|---|---|---|---|
| `sin_licencia` (evaluación) | Desde el primer arranque con esta versión, 30 días | **ON** las cuatro | ON | Evaluación: 100 equipos · 3000 usuarios · 50/100 concurrentes |
| `activa` / `reactivada` | Dentro de la vigencia y con la huella de este equipo | Las que **trae la licencia** | ON | Los de la licencia |
| `en_gracia` | Venció, o este equipo ya no es el de la licencia | Las de la licencia (**no se pierde nada**; sólo aviso) | ON | Los de la licencia |
| `liberacion_pendiente` | Licencia emitida mientras se libera el equipo anterior (JRN-020) | Las de la licencia, por el plazo que trae | ON | Los de la licencia |
| `degradada` | Se acabó la gracia (o la evaluación) **y** pasaron 24 h de histéresis | **OFF** las cuatro | **ON** | Los de la licencia (o los de evaluación) |

Banderas que **no quitan nada**, sólo avisan: `reloj_sospechoso`, `huella_parcial`, `integridad_alterada`. Dos efectos sutiles: `reloj_sospechoso` por un salto hacia adelante **aplaza** una degradación hasta 72 h; y `degradada` no pone el cupo en cero (se rige por los límites que ya había).

**Consecuencia para el colegio.** La degradación es un «pantallazo gris» en cuatro lugares, no un apagón. Lo que el colegio hace cada día (dar clase, examinar, estudiar, calificar, ver notas) sigue igual. Lo que pierde: ver reportes y exportarlos, buscar, importar un padrón completo y cambiar ciertos ajustes.

## 5 · Qué ve la persona, pantalla por pantalla

**OPS (equipo maestro, pantalla táctil).**

| Pantalla | Llama a | Clase | Con la licencia degradada |
|---|---|---|---|
| Menú principal · Clase de hoy · sesión de clase · cierre | aula (A), biblioteca (B) | A/B | Igual |
| Evaluaciones · aplicar · panel · expediente · resultados | evaluación (B/A) | A/B | Igual |
| Calificaciones (libro, revisión, detalle, estudiante, boletín del libro) | gradebook (B) | B | Igual |
| Calificaciones · «Sistema de calificación» (elegir país y escala, editor) | `POST escalas/adoptar/`, `escalas/`, `…/versiones/` | **C** (administración avanzada) | «No disponible por licencia» al **cambiar** la escala; la ya elegida sigue rigiendo |
| Modo estudio (asignar, ver quién completó) | modo estudio (A) | A | Igual |
| Grupos (crear grupo, matricular, alta de estudiante) | padrón (B) | B | Igual, **sujeto al cupo de usuarios** |
| Dispositivos | dispositivos (B) | B | Igual |
| Bitácora y estado del equipo | auditoría (B) | B | Igual |
| Seguridad del aula | PIN maestro (A) · docentes (B) · **políticas (C: H-02)** | A/B/**C** | El PIN y la lista de profesores siguen; **los interruptores dejarían de funcionar** (a corregir) |
| **Reportes** (inicio, elegir, clase, grupo, alumno, uso, estado, boletín, boletines, exportar) | reportes (C) | **C** | «No disponible por licencia». **«Visitantes y actividad» queda inalcanzable (H-01)** |
| **Buscar** | búsqueda (C) | **C** | «No disponible por licencia» |
| Visitantes y actividad (vincular visitante con alumno) | acceso visitantes y vincular (B) | B | La API sigue abierta; **sólo falta una entrada** (H-01) |
| **Licencia** (nueva) | `/api/licencia/` (A) | A | Siempre disponible: sin ella no se puede renovar |

**Student (tabletas y portátiles de alumnos).** No llama a **ninguna** ruta licenciable. Sus únicos contactos con la licencia son dos respuestas posibles: `cupo_agotado` (equipos, en el latido de un equipo **nuevo**; usuarios, en el registro propio) y, en teoría, `no_disponible_por_licencia`. Una tableta **ya registrada** y un alumno **ya existente** no se ven afectados jamás.

## 6 · Los cupos: qué se bloquea y qué no

BR-027 y BR-063: **«bloquear lo nuevo, nunca lo existente»**. Sólo se mira al **crear**.

| Situación con el cupo lleno | Debe pasar | Evidencia / riesgo |
|---|---|---|
| Alumno ya registrado inicia sesión, entra a clase, presenta un examen | **Pasa siempre** | R-01 |
| Readmisión de un participante en la clase | **Pasa siempre** | `casos_uso.py` del aula: el cupo de concurrencia sólo mira participantes nuevos |
| Latido de una tableta **ya registrada** | **Pasa siempre** | Intocable |
| Latido de una tableta **nueva** (primera vez que se presenta) | Se rechaza con `402 cupo_agotado` (tipo `equipos`); la tableta **no queda registrada** y **no** reintenta en bucle | `LatidoView` / `RegistrarLatido`. **Sólo aquí y en `POST dispositivos/`** (H-07) |
| Tableta nueva que **abre un examen** o **entra a clase** sin haber hecho latido | **Se registra igual** (no se le niega el examen) | `evaluacion/aplicacion/intentos.py:54` exige aparato y lo da de alta con `resolver`; poner el cupo en `resolver` rompería R-02. Por eso el cupo de equipos es **blando** (la huella la declara el cliente: P-08) |
| Alta de un usuario a mano, por padrón, por importación, por autoalta de alumno o por registro de profesor | Se rechaza con `402 cupo_agotado` (tipo `usuarios`) | Único punto: `CrearUsuario._crear` (H-05) |
| Importación masiva al tope | Crea hasta el cupo y **rechaza el resto fila por fila** con su código | H-06: el error debe heredar de `ErrorAcceso` |
| **Entrar como visitante** | **Pasa siempre**; el visitante **no cuenta** (origen `VISITANTE`, se retira al cerrar) | RN-33, H-05 |
| Identidad **retirada** o equipo **retirado** | No cuentan | «Identidades activas» (BR-027) |
| Equipo `MASTER` (el propio equipo maestro) | No cuenta | H-04 |
| Participante **nuevo** en una clase con 100 conectados | `409 aula_llena` (ya existe, BR-063) | Sin cambio |

**Lo que el colegio puede perder aquí** (por diseño, y sólo cuando llega al tope): que un alumno **nuevo** se registre solo, que el profesor lo anote como admisión nominal, que se importe un padrón o que una tableta **nueva** se presente por su latido. El visitante ya es la salida para «no puedo entrar»: por eso nunca se bloquea.

## 7 · Hallazgos (H-n), con evidencia y propuesta

| # | Evidencia | Propuesta | Estado |
|---|---|---|---|
| **H-01** | `ReportesPage.cs:41` abre `activity-monitor` («Visitantes y actividad»); `AppShell.xaml.cs:16` lo registra pero la tesela del menú ya no lo abre (`DashboardPage.xaml:81`). Su API (`/api/acceso/visitantes/`, `usuarios/<id>/vincular/`) es núcleo | `ReportesPage` conserva ese botón aunque `reportes` esté apagada, o se le da entrada propia (p. ej. en «Seguridad del aula») | Enviado a la otra sesión · **pendiente** (Fase 3) |
| **H-02** | `rutas.py`: `PUT /api/acceso/politicas/<perfil>/` → `administracion_avanzada`. `SeguridadAulaPage.cs:239` y `AccesoApi.cs:355` usan **esa misma ruta** para los interruptores de «registro de profesores», «autorregistro de alumnos» y «visitantes» | Sacar `politicas/` de la tabla C. Lo que **cierra puertas** no se licencia | **Adoptado** (`rutas.py`) |
| **H-03** | `reporting` no tiene ruta de exportación aparte; `gradebook` no exporta. `Q-L12` y R-03: por omisión no limitar la exportación de calificaciones | `boletines/` y `exportaciones/` pasan a núcleo hasta que el CTO conteste; el resto de `/api/reportes/` se apaga. Alternativa: dejar todo en C y decidirlo (D-n) | **Adoptado** (`rutas.py`) · el CTO confirma (Q-L12) |
| **H-04** | `Sesion.cs:346` (`tipo: "MASTER"`); tipos `TABLETA`, `MASTER`, `OTRO` (`device_manager/dominio/dispositivo.py:15`) | El cupo de equipos cuenta `TABLETA` y `OTRO`, activos | **Adoptado** (`resolver`: `tipo != MASTER`) |
| **H-05** | `acceso/aplicacion/casos_uso.py:1227` (`_crear`) lo usan `CrearUsuario`, `ImportarUsuarios._fila` (1396), `RegistrarEstudiante` (autoalta), `RegistrarDocente` y el padrón. `AbrirSesionVisitante` (`estudiantes.py:190`) crea el `Usuario` directo | El gancho de cupo va **sólo** en `_crear`; «identidades activas» excluye origen `VISITANTE` y estado `RETIRADO` | **Adoptado** (`CrearUsuario._crear`, `contar_activos`) |
| **H-06** | `casos_uso.py:1345` atrapa `errores.ErrorAcceso` por fila; `views.py:49` sólo traduce `ErrorAcceso` | `CupoAgotado` hereda de `ErrorAcceso` (`http = 402`, `codigo = "cupo_agotado"`) | **Adoptado** (`acceso/dominio/errores.py`) |
| **H-07** | `resolver` lo llaman el aula (`casos_uso.py:455`), la evaluación (`aplicacion/base.py:104`, con `exigir_aparato=True` en `intentos.py:54`), el modo estudio (`base.py:111`, `sesion.py:141`, `paquetes.py:89`) y el acceso | `resolver` **nunca** rechaza por cupo. Un parámetro opt-in (`cupo`) lo activa sólo en `RegistrarLatido` y en `RegistrarDispositivo`, y sólo cuando el equipo **no existía** | **Adoptado** (`device_manager`: `resolver(cupo=…)`, sin `MASTER`) |
| **H-08** | `estado.calcular`: `ahora < lic.desde` → `sin_licencia` con motivo `aun_no_vigente`; sin tolerancia | Tolerancia de un día en `desde` (el nodo acepta una licencia que empieza «mañana»), la **misma** al activar y al calcular el estado, y el emisor **retrasa** `desde` un día (lo hace el keygen por omisión) | **Hecho**: nodo (`tolerancia_inicio_ms`) y emisor; probado de punta a punta con relojes de −30, −45 y −72 horas (`test_emisor_real.py`) |
| **H-09** | El trigger de la marca alta impide bajarla (P-06) | Una licencia con un indicador crítico «restablecer reloj» (sólo AVACOM puede emitirla) permite bajar la marca hasta su `emitida`; el administrador **no** puede bajarla solo. Alternativa (también en Q-L13): que la marca suba sólo con el tiempo monótono mientras el salto esté pendiente — con un hueco: el aplazamiento se mide en la línea de tiempo adelantada y un salto de un año lo aplazaría un año | **Por decidir** (CTO · Q-L13); la otra sesión **no** lo construye |
| **H-10** | El aviso es un banner por rol (molde `PinBanner`, sólo administración y técnico) | Además: (a) el profesor, al tocar una función apagada, ve «Pide a tu administrador que renueve la licencia»; (b) `/health/` y el verificador del instalador muestran el estado; (c) el asistente del instalador lo dice en la última pantalla | **Por enviar** |
| **H-11** | `estado._licenciables_de`: sólo las capacidades que **la licencia nombra** (o `*`) | El plan por omisión del emisor es `*`; una capacidad licenciable nueva exige decisión explícita (qué hacer con licencias vivas) | Emisor: hecho |
| **H-12** | «Todavía NO hay llave pública de producción embebida» (ranuras en `backend/licenciamiento/claves/`) | Puerta de liberación **bloqueante**: el build de producción falla si no hay una llave pública de producción (y la de desarrollo **no** viaja). Hasta la ceremonia, todo instalador de producción está incompleto | **Adoptado en el build** (`Build-Installer.ps1 -ExigirLlaveDeProduccion` falla sin llave; sin el interruptor sólo avisa). **La ceremonia sigue pendiente** (Q-L3) |
| **H-13** | `Evaluar._planear`: `lectura = rj.leer(ahora, marca, …)` da `max(reloj, marca)` y `marca_siguiente(marca, lectura.ahora)` no sube con un reloj atrasado. `RelojDelNodo.monotono_ms()` sólo alimenta `salto_adelante`; `reloj.retroceso_en_marcha` no se usa en ninguna parte. Prueba aparte contra el nodo real (reloj falso): licencia que vence a los 30 días, 10 días de uso, la fecha se atrasa 300 días y pasan 70 días reales → `activa`, `dias_restantes = 20`, `ahora_confiable` clavado en el día 10; atrasar 100 días degrada a los **151** días reales (sin el defecto, a los ~51) | **Piso monótono**: dentro de un mismo proceso, `ahora_confiable = max(reloj, marca, confiable_previo + (monótono − monótono_previo))` y la marca sube con él (se persiste con el margen de 10 minutos de siempre). Tras un reinicio sólo se pierde el tiempo apagado, que no se puede medir y que un atacante no puede aprovechar (apagar el equipo no le da nada). Prueba: la de arriba, con y sin reinicio entre medias | Enviado a la otra sesión · **pendiente** |
| **H-14** | Mismo código: `salto_desde` es la hora del asiento del salto y `_salto_pendiente` pregunta `ahora < salto_desde + 72 h` con el instante confiable, que con la fecha devuelta queda clavado en la marca. Prueba aparte: salto de +365 días, fecha devuelta, degrada a los **368** días reales; con el nodo ya `degradada`, un salto de +400 días y su devolución la dejan en `en_gracia` con los cuatro módulos durante los 4 días que dura la prueba | El mismo piso lo corrige sin tocar la decisión de H-09: con el instante confiable avanzando 1 a 1 con el tiempo real, las 72 h del tope son 72 h de verdad | Enviado a la otra sesión · **pendiente** |
| **H-15** | `dominio/licencia.py::desde_campos` sólo rechaza `normal > pico`: un 0 en cualquiera de los cuatro límites pasa. Prueba aparte contra el nodo real: una licencia firmada con `concurrentes_normal = 0` y `concurrentes_pico = 0` se instala (`activa`) y `POST /api/aula/sesiones/unirse/` responde `409 aula_llena` («El aula alcanzó su capacidad (0 dispositivos)») al primer alumno; con `equipos = 0` y `usuarios = 0` también se instala | Rechazar (`campo_invalido`) cualquier límite < 1 al leer la licencia (el emisor oficial ya lo exige); «sin tope» (0xFFFFFFFF) y el mínimo (1) siguen valiendo. Hay que cambiar una prueba del formato que usaba 0 como valor de ida y vuelta | Enviado a la otra sesión · **pendiente** |

## 8 · Modos de fallo (F-n): qué se pierde por accidente

Probabilidad: **B**aja · **M**edia · **A**lta (en un parque de aulas reales). Impacto = qué se pierde; «nada» significa que sólo hay aviso.

### Reloj

| # | Qué pasa | Impacto | P | Cómo lo cubre el diseño | Cómo se prueba |
|---|---|---|---|---|---|
| F-01 | El reloj **retrocede** (pila de la BIOS, cambio a mano) | Debería ser nada: `ahora = max(reloj, marca alta)`; bandera `reloj_sospechoso`; no alarga la licencia. **Hoy sí la alarga** (H-13): el instante confiable queda clavado en la marca y la licencia no vence hasta que la hora de pared la alcanza | M | P-06 · **H-13 (piso monótono)** | Retroceder 3 años y 70 días de verdad después: el estado **avanzó** (degrada a su hora) y deja asiento una vez |
| F-02 | El reloj **salta al futuro por error** (BIOS 2038, fecha mal tecleada) | Licencia vencida de golpe; tras 24 h de histéresis (más hasta 72 h por la sospecha) → `degradada`: **se apagan las 4 capacidades** hasta renovar. Volver el reloj **no** baja la marca | B | Histéresis, aplazamiento, aviso. **Sin salida limpia: H-09** | Saltar +5 años: no degrada de inmediato; confirma; degrada tras el plazo |
| F-03 | Equipo con el reloj **de fábrica atrasado** (2010–2020) al activar una licencia nueva | La licencia queda «aún no vigente» y el nodo vuelve a la evaluación; si ésta ya venció, **degradada** justo después de activar | M | **H-08 (hecho)**: el nodo tolera que `desde` esté un día en el futuro y el emisor retrasa `desde` un día: con un reloj atrasado hasta ~48 h la licencia se activa y se queda «activa». Más allá **no se instala nada** y el aviso dice «revisa la fecha y la hora del equipo» (400 `aun_no_vigente`) | Activar con reloj −2 h, −30 h, −45 h (activa) y −72 h, −5 años (rechaza con aviso, el estado no cambia) |
| F-04 | Restaurar un **respaldo viejo** | Nada: las anclas fuera de la base conservan la marca alta; la licencia guardada en la carpeta de estado se reactiva (FUN-194) | M | P-06, R-11 | TST-060 y restauración en el mismo equipo |
| F-05 | Cambio de horario de verano o de zona horaria | Nada: todo se guarda en milisegundos UTC | A | — | Cambiar la zona del sistema con licencia activa |

### Huella (el equipo)

| # | Qué pasa | Impacto | P | Cómo lo cubre | Prueba |
|---|---|---|---|---|---|
| F-06 | Se cambia un disco o la tarjeta de red | Nada: con 4 factores coinciden 3 de 4; bandera `huella_parcial`. **Con sólo 2 factores útiles se exigen los 2**: cambiar uno cuenta como otro equipo (D-3) | A | P-04 | Quitar un factor de 4: sigue `activa`; con 2 factores, quitar uno: gracia |
| F-07 | Se cambia la **placa madre** | Pueden quedar < 3 factores → «licencia de otro equipo» → `en_gracia` → `degradada` si no se reactiva | M | Gracia (`gracia_dias`), reactivación por solicitud nueva (JRN-020) | Cambiar 3 factores: gracia; reactivar: `activa` |
| F-08 | **Reinstalar Windows** en un panel con SMBIOS **de relleno** (nivel `instalacion`) | Se cambia `MachineGuid` y, **si se pierde `%ProgramData%\AVACOM\OPS Master\Config\licencia\`**, el secreto de instalación desaparece: huella irrecuperable → gracia → degradada | M | La carpeta se conserva al actualizar y desinstalar; CAP-111 (copia en USB); reactivación | Borrar la carpeta y comprobar que se pide reactivar y la clase sigue |
| F-09 | Panel con SMBIOS de relleno (muy común en OEM de pantallas interactivas) | Nada inmediato; la huella es la **débil** (de instalación) y se ve en pantalla | A | P-04: nunca se impide activar por hardware pobre | Factores basura → nivel `instalacion` visible |
| F-10 | Clonar el disco a **otro** panel (aunque sea del mismo modelo) | Es lo que se quiere impedir: huella distinta → gracia → degradada | B | P-04 | Cambiar placa y chasis |

### Archivos de licencia

| # | Qué pasa | Impacto | P | Cómo lo cubre | Prueba |
|---|---|---|---|---|---|
| F-11 | `.avlic` **corrupto** (USB defectuoso, copiado como texto con un carácter de más) | Nada: firma inválida, estado intacto, mensaje claro; se repite | M | `firma.abrir` verifica antes de interpretar | 100 000 mutaciones, 0 aceptadas |
| F-12 | Archivo **de una serie anterior** | Nada: se rechaza (`serie_anterior`); el estado no cambia | M | `serie` monótona | Activar la serie 1 sobre la 2 |
| F-13 | Licencia **de otro equipo** cargada por error | Si se aceptara, un equipo sano pasaría a «huella distinta» y a gracia. **Se rechaza al activar** (`huella_no_corresponde`) salvo `LIBERACION_PENDIENTE` | M | Precondición de FUN-188 | Cargar una licencia con otra huella |
| F-14 | Licencia de **desarrollo** en un nodo de producción | Rechazada (la llave de desarrollo sólo vale en desarrollo y pruebas) | B | P-03, P-12 | Activar una licencia firmada con la clave de desarrollo |
| F-15 | Licencia con **etiqueta crítica desconocida** (emitida con un emisor más nuevo) | Rechazada: no se entiende; se conserva la anterior | B | `tlv.leer_campos` | Archivo con una etiqueta nueva crítica |
| F-16 | Dos activaciones seguidas con series cruzadas | Manda la serie mayor; idempotente | B | Serie monótona | Activar 3, 2, 3 |
| F-17 | Se emite una licencia de **evaluación** a un cliente de producción | Vence pronto → gracia → degradada | B | Proceso: el keygen avisa el tipo y la vigencia antes de firmar | Guía interna |

### Software

| # | Qué pasa | Impacto | P | Cómo lo cubre | Prueba |
|---|---|---|---|---|---|
| F-18 | Una **excepción** en el middleware o en el cálculo de estado | Nada: se deja pasar y se registra (R-04); nunca un 500 por la licencia | B | `try/except` total | Forzar una excepción en cada punto |
| F-19 | El **programador** no arranca o muere | El estado queda como estaba (no degrada solo); se recalcula al arrancar y en cada consulta de estado | B | Fallo abierto, anotado | Matar el hilo y consultar `estado/` |
| F-20 | La **memoria** queda desfasada después de activar o renovar | Se verían rutas apagadas con una licencia buena | M | La activación refresca el estado en la misma operación | Activar y llamar de inmediato a una ruta licenciable |
| F-21 | La **migración** falla al actualizar | El instalador devuelve el equipo a la versión anterior con sus datos | B | Política de datos protegidos (2.8.0) | `Ensayar-Paquete.ps1` con migración que falla |
| F-22 | `backend.env` con `AVACOM_LMS_ENTORNO=pruebas` en un nodo instalado | Nada: **sigue evaluando** la licencia (P-12) | B | Marcador de canal, `Program Files` | Prueba obligatoria de P-12 |
| F-23 | Se borra el marcador de canal, se copia el backend fuera de `Program Files` y se fabrica un `.git` | Se evade el licenciamiento (A4). **No se impide**: se documenta y, desde la Fase 4, deja evidencia | B | Honestidad (P-12) | Sólo el caso documentado |
| F-24 | Falta la **llave pública de producción** en el instalador | **Ninguna licencia real valida**: todos los clientes degradan a los 30 días | M | **H-12**: puerta de liberación bloqueante | Prueba de contenido del paquete |
| F-25 | **Rotación** de llaves: el nodo ya no trae la llave con que se firmó una licencia viva | Esa licencia deja de validar | B | ≥ 2 llaves embebidas; el nodo conserva las anteriores mientras haya licencias vivas | Licencia firmada con kid antiguo |
| F-26 | Un antivirus bloquea la DLL nativa (Fase 4) | Nada: se usa la referencia en Python y se avisa | M | P-20 | Renombrar la DLL |
| F-27 | La tableta nueva recibe `402` en el latido y el cliente no lo entiende | La tableta nueva no queda registrada y reintenta | M | Textos de Student; sin bucle | UIA de Student con cupo lleno |
| F-28 | El cupo **cuenta mal** (visitantes, retirados, el maestro) | Se bloquea un alta legítima antes de tiempo | M | H-04, H-05 | Contar con 30 visitantes retirados |
| F-29 | La importación **pierde el lote** por un 402 que aborta la transacción | Se pierde un padrón entero | M | H-06 | Importar 10 filas con cupo de 6 |
| F-30 | «Visitantes y actividad» **inalcanzable** | No se puede vincular a un visitante con su alumno | A | H-01 | UIA con `reportes` apagada |
| F-31 | Los **interruptores de seguridad** dejan de funcionar con la licencia degradada | No se puede cerrar el registro propio ni los visitantes | A | H-02 | Cambiar un interruptor con la licencia degradada |
| F-32 | La **exportación de calificaciones** queda apagada | El colegio no puede sacar el boletín | M | H-03 | Exportar boletín con `reportes` apagada |

### Proceso y comunicación

| # | Qué pasa | Impacto | P | Cómo lo cubre | Prueba |
|---|---|---|---|---|---|
| F-33 | **Nadie ve el aviso** (sólo administración y técnico lo ven; en 30 días nadie con ese rol abre OPS) | El colegio se entera cuando ya está degradado | A | H-10 | UIA: profesor ve el aviso al tocar la función |
| F-34 | El banner **interrumpe una clase** | Rompe S4 («ninguna alerta administrativa interrumpe una sesión») | B | Regla de visualización | UIA con una clase abierta |
| F-35 | Un cliente **existente** se actualiza y no activa | A los 30 días (P-14) pierde las 4 capacidades | A | Aviso en el asistente, banner, `/health/` | Actualizar un nodo con datos |
| F-36 | El **emisor** firma una licencia con límites o fechas equivocados | El colegio queda corto o largo | M | Resumen y confirmación antes de firmar; registro de emisiones | Guía interna |

## 9 · Escenarios del calendario escolar

| # | Escenario | Qué pasa | Qué hacer |
|---|---|---|---|
| **E-1** | La licencia vence en diciembre y la gracia es de 30 días | El receso escolar **consume la gracia sin que nadie use el sistema**; al volver en febrero está degradado: sin reportes, búsqueda ni importación (la clase **funciona**) | El emisor sugiere vigencias que cierren **después** del fin de ciclo y gracia ≥ 45 días; avisos 30/14/7/3/1; Q-L1 |
| **E-2** | Un panel se daña en pleno ciclo (JRN-020) | Equipo nuevo + respaldo restaurado; el colegio da clase en ≤ 30 min (TST-060). La licencia vieja se **libera** (`.avrel`) o se emite una con `LIBERACION_PENDIENTE` | El nodo nuevo opera en gracia con MSG-063 mientras se regulariza |
| **E-3** | Inicio de ciclo: se matriculan 600 alumnos nuevos y el cupo está al 98 % | Altas por padrón o autoalta rechazadas con `cupo_agotado`; los visitantes siguen entrando | Aviso de cupo desde el 90 %; ampliar la licencia **antes** del inicio de ciclo |
| **E-4** | Corte de luz y restauración en el mismo equipo (JRN-019) | Se reconoce la licencia guardada y pasa a `reactivada`; nada se pierde | Ninguna |
| **E-5** | Un equipo nuevo con el reloj de fábrica | F-03: la licencia recién activada parece «aún no vigente» | H-08: tolerancia y aviso |
| **E-6** | Un colegio actualiza a la versión con licencia y nadie abre OPS como administrador en 30 días | F-33/F-35: se degrada sin que nadie lo sepa | H-10: aviso al profesor y en `/health/` |

## 10 · Lo que este análisis no garantiza

- **No hay prueba en vivo todavía.** Todo lo de arriba es lectura de código y de la tabla de rutas del 2026-10-20 a las 10:00; la otra sesión sigue construyendo. La tabla se **vuelve a generar** al cerrar cada fase (el script es de una pantalla) y las cifras de §3 se actualizan.
- **El cupo de equipos es blando** hasta que exista una clave de dispositivo (Fase 5): la huella la declara el cliente. El diseño lo dice y este análisis no promete lo contrario.
- **Un administrador con conocimientos puede evadir el licenciamiento** (A4): se encarece y se deja evidencia, no se impide.
- **Qué cuenta como «clase en curso»** para esconder el banner (F-34) lo define la pantalla (una sesión del aula abierta en el nodo); no está probado todavía.
- **Lo que depende de módulos que no existen** (MOD-004 derechos del paquete, MOD-017 actualizaciones con clave de licencia, MOD-015 reloj y huella propios): queda como enganche; cuando se construyan hay que repetir este análisis, sobre todo MOD-004 (un paquete sin derechos **no** puede cerrar una clase en curso: JRN-021 importa la estructura y bloquea el material).

## 11 · Cómo se comprobará (pruebas que cierran cada riesgo)

| Pruebas | Cubren |
|---|---|
| Tabla de rutas **derivada del resolvedor**: cada ruta intocable responde **igual** con la licencia degradada; cada licenciable responde 402; ninguna ruta nueva queda sin clasificar a escondidas | R-01, §3, H-02, H-03 |
| `assertNumQueries(0)` en el camino caliente de una petición | R-07 |
| Excepciones forzadas en middleware, cálculo y programador: la petición pasa | R-04, F-18, F-19 |
| Cupo: nuevos bloqueados; existentes, readmisiones, latidos, visitantes y el equipo `MASTER` intactos; importación al tope fila por fila | §6, H-04…H-07, F-27…F-29 |
| Reloj: retroceso, adelanto, respaldo viejo, tolerancia de `desde` | F-01…F-05, H-08 |
| Huella: factores de relleno, k de n, borrar el secreto de instalación | F-06…F-10 |
| Archivos: mutaciones, serie anterior, otra huella, llave de desarrollo, etiqueta crítica | F-11…F-16 |
| P-12: `AVACOM_LMS_ENTORNO=pruebas` en un layout de producción de pruebas **sigue evaluando** | F-22 |
| UIA de OPS con `reportes` apagada (botón «Visitantes y actividad»), con la licencia degradada (interruptores de seguridad) y con una clase abierta (sin banner) | H-01, H-02, F-30, F-31, F-34 |
| Contenido del instalador: sin emisor, sin clave de desarrollo, **con** llave pública de producción | F-24, H-12 |
| Línea base antes y después: **ninguna prueba existente cambia** | R-14 |
