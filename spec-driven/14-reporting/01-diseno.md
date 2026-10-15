# 14 · Reporting (MOD-013) · Diseño, decisiones y alcance

| Campo | Valor |
|---|---|
| Estado | **Implementado** (2026-10-15), sin commit. Backend `backend/reporting/` (app Django, tablas `m13_*`), cliente `src/Avacom.Lms.Core/Reporting/`, pantallas de OPS en `src/Avacom.Lms.Ops/Pages/Reporte*.cs` y lógica en `src/Avacom.Lms.Ops/Reportes/` (la parte con interfaz, en `Reportes/Ui/`). |
| Módulo | **MOD-013 · Reporting** (DOM-007 · Aprendizaje y Analítica). CAP-081, CAP-082 y CAP-084; FUN-139, 140, 142, 143, 144, 145, 146 y 147. **FUN-146 / CAP-084 (exportar) se sube de V1 a este entregable** por decisión de producto. |
| Contrato | [02-api.md](02-api.md) — rutas, cuerpos, errores, eventos y permisos. |
| Pruebas | [03-pruebas.md](03-pruebas.md) — qué se probó, con qué resultado y qué **no** se pudo comprobar. Capturas en [capturas/](capturas/). |
| Se apoya en | MOD-007 (clases), MOD-008 (estudio), MOD-010 (evaluaciones), MOD-011 (libro: calificación ya presentada), MOD-009 (equipos), MOD-001/002 (grupos y personas), MOD-019 (auditoría). El prompt original está en [00-prompt.md](00-prompt.md). |

> **Principio fundamental (Documento Maestro):** Reporting **no escribe ningún dato académico**. Arma vistas sobre lo que otros módulos ya calcularon, siempre recortadas por el alcance de quien consulta. Sus proyecciones se pueden borrar y reconstruir desde la cola sin pedirle nada a nadie (BR-007).

---

## 1 · Qué entra y qué no

| Entra (MVP de esta entrega) | Dónde |
|---|---|
| CAP-081 reporte de la clase al terminarla (participación, aciertos, promedio) · TST-008 | `GET /api/reportes/clases/{id}/` |
| CAP-082 avance individual del alumno (informe nominal) · FUN-140 | `GET /api/reportes/alumnos/{id}/` |
| FUN-139 avance de un grupo | `GET /api/reportes/grupos/{id}/` |
| FUN-142 uso de equipos y sesiones (sólo con sesiones finalizadas en el periodo) | `GET /api/reportes/uso/` |
| FUN-143 filtros: periodo, grupo, alumno, nodo académico | `GET /api/reportes/filtros/` + parámetros de cada reporte |
| FUN-144 actualización periódica de agregados fuera del horario de clase · FUN-145 marcar incompleto | consumidor + hilo del nodo |
| **FUN-146 exportar a archivo (xlsx / csv) con alcance declarado, en dos tiempos** | `…/exportaciones/` (§6) |
| FUN-147 reconstruir los agregados desde la cola | `POST /api/reportes/reconstruir/` · `manage.py reporting_reconstruir` |

| NO entra (queda preparado, sin inventar datos) | Por qué |
|---|---|
| CAP-083 comparar grupos de la misma sede · CAP-085 / FUN-141 cobertura curricular | V1. Permisos y rutas reservados (`reports.curriculum.view`; `GET …/comparar/` y `…/cobertura/` responden **501 `capacidad_reservada`**). La cobertura necesita el currículo congelado de MOD-003, que no está en este repo. |
| CAP-086 reportes propios por dimensiones | Futuro. |
| Impresión · analítica entre instituciones · PDF | El Maestro deja la impresión fuera del MVP; PDF queda para V1 (D-12). |
| Dominio por objetivo (MOD-012) | `ls backend` no tiene `mod_012`/`dominio`: el módulo no existe. En cada reporte esa sección sale como `{"disponible": false}` y la pantalla dice «Aún no disponible», nunca un cero. |
| Cualquier escritura sobre datos de origen (BR-085) | Una prueba de arquitectura comprueba que no hay `.save()`, `.update()`, `.create()` ni `.delete()` sobre modelos ajenos, ni imports de sus modelos. |

## 2 · Arquitectura

Hexagonal, igual que `gradebook/` y `search/`:

```
backend/reporting/
├── models.py                       m13_* (§3)
├── dominio/                        reglas puras; NO importan Django ni DRF
│   ├── catalogos.py                permisos, tipos de reporte, estados, motivos, eventos, acciones de auditoría, límites
│   ├── errores.py                  ErrorReporting y sus hijos (cada uno lleva su código HTTP)
│   ├── metricas.py                 porcentajes y promedios con Decimal (mitad_arriba), «necesita atención»
│   ├── integracion.py              estado de integración de los equipos (BR-083)
│   ├── privacidad.py               umbral de privacidad (BR-086)
│   ├── archivo.py                  nombre de archivo seguro, huella, política de destinos
│   └── documento.py                el documento exportable (cabecera BR-083, resumen, tablas)
├── aplicacion/                     casos de uso; NO importan Django ni DRF
│   ├── puertos.py                  Aula · Evaluacion · Libro · Estudio · Equipos · Identidad · Arbol · Autorizacion · Auditoria · Outbox · Reloj · repositorios
│   ├── consumidor.py               consume la cola de cada módulo con marca de lectura; reconstruir
│   ├── proyectar.py                recalcula UNA fila derivada desde el dueño (clase, alumno, grupo)
│   ├── reportes.py                 los cuatro reportes, el listado de clases, los filtros y «recientes»
│   ├── exportar.py                 alcance declarado · autorizar y generar · confirmar · caducar
│   └── ajustes.py                  configuración del nodo y estado de los agregados
├── infraestructura/                adaptadores: ORM, módulos dueños por su `servicios.py`, padrón, árbol de la biblioteca, archivos xlsx/csv, hilo del nodo
└── interfaces/                     vistas DRF y rutas (`/api/reportes/`)
```

**Frontera.** Cada dato ajeno se pide a la interfaz pública del dueño (`<módulo>.servicios`, BR-004); Reporting jamás lee ni escribe `m07_*`, `m08_*`, `m10_*`, `m11_*` (la única lectura directa es el padrón de MOD-001, que no tiene interfaz propia, como en el libro y en Search). Lo que ya existía se usó tal cual; lo que faltaba se **añadió como función de sólo lectura** (D-4).

**Cliente y OPS.**

```
src/Avacom.Lms.Core/Reporting/      ModelosReportes (DTOs) · IReportesApi/ReportesApi · ReportesTexto (cifras, fechas, estados vacíos, errores, notas) ·
                                    NombreDeArchivo y MotivosDeEscritura (escritura segura, sin MAUI)
src/Avacom.Lms.Ops/Reportes/        lógica pura (se prueba sin MAUI): destinos, unidades, vigilante, preferencias, escritura segura, flujo de exportación,
                                    periodos, rutas, listas, árbol de nodos, textos de la confirmación, permisos
src/Avacom.Lms.Ops/Reportes/Ui/     con interfaz: la hoja de exportar, la cabecera de corte, las tablas, el selector de nodo, el selector de carpeta de Windows
src/Avacom.Lms.Ops/Pages/           PaginaDeReporte (esqueleto) · ReportesPage · ReportesElegirPage · ReporteClasePage · ReporteGrupoPage · ReporteAlumnoPage ·
                                    ReporteUsoPage · ReportesEstadoPage
```

## 3 · Tablas `m13_*` (11)

Dos clases, y una prueba comprueba que **toda** tabla está en exactamente una:

| Derivadas (se borran y se reconstruyen: BR-007) | Qué guardan |
|---|---|
| `m13_clase` · `m13_clase_alumno` | El reporte de una clase terminada y la fila de cada alumno (presencia, actividades, aciertos por puntos, entregas que llegaron por la cola). |
| `m13_avance_grupo` · `m13_avance_alumno` | El avance de un grupo y el de cada alumno en él (modo y escala del nivel, conteos, «necesita atención», detalle de evaluaciones y estudios como ids y cifras). |
| `m13_estado_dispositivo` | Lo que cada tableta avisó de su cola de estudio (señal de integración, BR-083). |
| `m13_marca_consumidor` · `m13_estado_proyeccion` | Hasta qué secuencia se leyó la cola de cada módulo; si se está reconstruyendo. |

| Propias (perderlas es perder información) | Qué guardan |
|---|---|
| `m13_config` | Una fila: umbral de privacidad, política de exportación (extraíbles permitidos, razón exigida), versión para la concurrencia optimista. |
| `m13_exportacion` | Cada exportación: autorizada → entregada o caducada, con sus intentos, la huella y las cifras del archivo. **Nunca** su contenido ni la ruta donde quedó. |
| `m13_reciente` | Los reportes que cada persona abrió: sólo parámetros. |
| `m13_evento_salida` | Outbox `reporte.*.v1`. |

**Lo que no hay (artículo 14):** ninguna columna con un título de curso, lección, evaluación o pregunta, ni con un nombre de persona: sólo `curso_ref`, `leccion_ref`, `asignacion_id`, `alumno_id` y cifras. Los rótulos se piden al dueño al mostrar; si una persona se anonimiza no hay nada que tocar aquí.

## 4 · Decisiones

Lo que el prompt no resolvía se decidió con el criterio de abajo (D-n) y se dice aquí. Las marcadas **(CTO)** están en §9 para que el CTO las confirme.

| # | Decisión | Por qué |
|---|---|---|
| D-1 | **Derivadas vs propias**, y reconstruir = borrar las derivadas y volver a leer **en una sola transacción** (`Reconstruir`). La marca de lectura también se borra: empieza en cero (BR-007). | Una reconstrucción a medias dejaría reportes que mienten. Una prueba borra todo `m13_*` derivado, reconstruye y compara: idéntico. |
| D-2 | **`rezagada` se deriva** (hay eventos relevantes sin aplicar) y sólo `reconstruyendose` se guarda. El corte es «ahora» si está al día, o el instante anterior al evento más viejo sin aplicar. La pantalla lo dice como **antigüedad del dato**, no como estado interno. | Lo derivado no se desincroniza y el corte nunca promete más de lo que se aplicó. |
| D-3 | El consumidor **sólo avisa qué cambió** (grupo, alumno, clase) y el dato se **vuelve a leer del dueño** por su `servicios.py`; nunca se copia lo que el dueño ya guarda. Es idempotente (repetir un evento no cambia nada) y reconstruible. | Evita una segunda fuente de verdad y hace trivial reconstruir. |
| D-4 | Funciones de **sólo lectura añadidas a módulos dueños**, sin tocar su contrato: `classroom_engine.servicios.detalle_de_sesion` (con `presencia_al_cerrar`), `modo_estudio.servicios.asignaciones_de_estudio` y `tareas_de`, y el archivo nuevo `gradebook/servicios.py` (`ultima_secuencia`, `eventos_desde`, `resultados_del_grupo`). **(CTO)** | El prompt manda pedir por el servicio público del dueño; faltaban estas lecturas. |
| D-5 | **Integración (BR-083): tres señales observables** —`conexion_perdida` (un participante quedó «reconectando» al cerrar), `entrega_pendiente` (un intento de clase sigue abierto) y `cola_de_estudio` (la tableta avisó de trabajo por enviar)—. Cada una **caduca a los 15 minutos** —la misma ventana de gracia de DEC-019, en la que el nodo aún acepta lo que llega de la cola de una tableta—: pasado ese tiempo el nodo ya no espera nada de ella y la señal deja de contar, **aunque lo que faltaba nunca haya llegado** (visto en vivo: un «Incompleto» se apagó solo a los 15 min). El Maestro no fija una ventana para los reportes; es criterio propio. **(CTO)** `reporte.marcado_incompleto.v1` se emite **una vez por cambio**, no al reconstruir. | Sólo se declara incompleto lo que el nodo puede ver. Hoy no hay otra forma de saber qué tiene una tableta sin enviar. |
| D-6 | **FUN-144 «fuera de clase» = no hay sesión activa.** El hilo del nodo (cada 60 s) sólo actualiza sin clase abierta; pero **cada consulta se pone al día antes de responder**, así que la corrección no depende del hilo. `AVACOM_REPORTES_PROGRAMADOR=0` lo apaga. | No competir con las tabletas por el turno de escritura de SQLite, sin dar un reporte viejo. |
| D-7 | **Porcentajes con `Decimal` (mitad arriba) y por PUNTOS**, no por conteo de preguntas; **sin dato = null, nunca cero**; el promedio es la media simple de los alumnos que tienen cifra. En pantalla, «—». | Un promedio sin valores no es un 0 %. TST-008 y el modo simple lo exigen. |
| D-8 | **«Necesita atención»** con criterios **propuestos** (no institucionales): ≥ 1 evaluación sin presentar · entrega < 50 % con ≥ 3 actividades · asistencia < 50 % con ≥ 2 clases · estudio vencido. Cada uno trae su motivo en una línea. **(CTO)** | El Maestro no define el criterio; con pocas clases no se juzga. |
| D-9 | **BR-086 recorta el reporte de clase y el de grupo (y su archivo)**, no el informe de un alumno (un solo estudiante no es un agregado) ni el uso de equipos (no lleva personas). Mínimo 5; apagado de fábrica. **(CTO)** | Es lo que dice la regla: agregados de menos de cinco. |
| D-10 | **BR-085 / TST-069:** el técnico sólo tiene `reports.usage.view` y `reports.rebuild`; leer datos académicos devuelve 403 y deja el asiento `reporte.acceso_denegado` (también en la interfaz: la pantalla lo dice sin llamar al nodo). Reportes no escribe: no tiene `reports.rebuild` ni `reports.settings.manage`. | Mismo patrón que Gradebook. |
| D-11 | **Permiso `reports.settings.manage` (extensión técnica propuesta)** para cambiar el umbral y la política de exportación; sólo la administración. **(CTO)** | El Maestro no da función a estos ajustes; sin permiso propio cualquiera con `reports.view` los cambiaría. |
| D-12 | **Formato de archivo:** XLSX escrito con la biblioteca estándar (zip + XML a mano, cadenas en línea y fecha fija en las partes del zip; el encabezado lleva la hora de generación, así que dos archivos pedidos en minutos distintos no son idénticos) y CSV UTF-8 **con BOM, `;` y coma decimal**. Sin dependencias nuevas; **PDF queda para V1** (no hay librería en el entorno). El CSV neutraliza lo que Excel tomaría por fórmula. **(CTO)** | `requirements.txt` no cambia, así que el instalador no necesita nada nuevo. Se abrió un XLSX y un CSV con Excel real (es-CO). |
| D-13 | **Exportar en dos tiempos.** `POST exportaciones/` autoriza, genera y **responde el archivo** (cuerpo binario + cabeceras `X-Avacom-Export-*`, 201), con una vigencia de 15 min; `…/confirmar/` registra `guardado` (con la huella que se **releyó** del destino) o `fallido` (motivo de una lista cerrada). Un fallo **no cierra** la exportación: se puede elegir otro destino de la misma clase sin generar de nuevo (si cambia la CLASE de destino —de una memoria a una carpeta del equipo o al revés— el nodo vuelve a autorizar: D-29). Sólo `entregada` publica `reporte.exportado.v1` y deja el asiento; lo que nadie confirma caduca y no cuenta. | Así la bitácora no miente (el prompt). |
| D-14 | **La política de exportación es del nodo, no una autorización por operación.** Se aplica al autorizar (por tipo de destino) y cada exportación deja su asiento; no se pide una autorización de salida por operación como `audit.export` (BR-105). **(CTO)** | Los profesores exportan a diario; el prompt pide una política con valor por defecto, no un permiso por archivo. |
| D-15 | **Nombre de archivo determinista y sin personas:** `reporte-<tipo>-<código del grupo>-AAAA-MM-DD-HHMM.<ext>`. OPS lo vuelve a sanear (FAT32/exFAT: sin `\ / : * ? " < > |`, ≤ 100 caracteres, sin nombres reservados) y **no sobrescribe**: agrega «(2)». Nadie lo escribe: no hay teclado. | Prompt. |
| D-16 | **Dominio por objetivo = «Aún no disponible»** (`{"disponible": false}`), nunca un cero. | MOD-012 no existe. |
| D-17 | **Rótulos pedidos al dueño en el momento**; sólo se guardan referencias (art. 14). Una prueba de arquitectura lo comprueba. | Constitución. |
| D-18 | **Filtro por nodo académico en vivo** con el árbol de AVACOM Biblioteca (se envían los **códigos** del árbol). Si la biblioteca no responde, el filtro **no se aplica y se dice** (aviso en el reporte y nota en la pantalla): nunca se esconde. | Art. 14 y honestidad con el dato. |
| D-19 | **Recientes** guardan sólo parámetros (`m13_reciente`); abrirlos vuelve a armar el reporte con lo de ahora. Se marca cuándo se exportó. | Reexportar sin repetir filtros, sin guardar contenido. |
| D-20 | **`filas` de un archivo = el total de filas de todas sus tablas**; es lo que dice la confirmación y lo que queda en el asiento. | Un número que el profesor puede contar en el archivo. |
| D-21 | **Tesela «Reportes»:** visible para profesorado, administración y Reportes (no técnico ni alumno; sin sesión se deja ver y el nodo decide), como pedía el prompt. Antes abría la demo `activity-monitor`: esa pantalla —con la lista de visitantes y «Vincular a un alumno» (RF-09c)— **queda a un toque desde Reportes → «Visitantes y actividad»**, para no quitarle su entrada. | No regresar otro módulo. |
| D-22 | **Estilo de OPS:** fondo `#F1F1F1` y ancho de 1280 px **como `CalificacionesPage` y `BuscarPage`** (el degradado pastel es del acceso y del panal); el inicio sí es una pantalla de tarjetas y sigue los **tercios** (`*,*,*` × `*,4*,*`); la hoja de exportar cae en el tercio central de 1/6 a 5/6 (verificado con captura y cuadrícula). | El prompt manda copiar esas dos pantallas y a la vez la regla de tercios. |
| D-23 | **Temporal de la exportación** en la caché local del equipo: se borra siempre (al guardar, al cancelar, al cerrar la hoja o la pantalla) y, tras un cierre brusco, al siguiente arranque se borran los de más de 20 minutos. | Un reporte con nombres no debe quedarse en un equipo compartido. |
| D-24 | **Hooks de prueba sólo con el perfil de pruebas de UI Automation** (`AVACOM_OPS_PERFIL`): `AVACOM_OPS_UNIDADES_PRUEBA` (agrega «memorias» que son carpetas reales) y `AVACOM_OPS_ESCRITURA_LENTA_MS`. Sin el perfil no hacen nada. | Sin una memoria USB física, es la única forma de ver la fila «Extraíble», la barra de avance y la memoria que se retira. |
| D-25 | **Un fallo al guardar ofrece los botones que nombra su frase.** «Vuelve a conectarla y toca Guardar otra vez, o elige otro destino» → **«Guardar otra vez»** (repite sobre el mismo destino **sin generar de nuevo** el archivo ya bajado) y **«Elegir otro destino»**. Se repite lo que se arregla afuera (memoria retirada, sin espacio, protegida, red, archivo en uso, verificación, antivirus) y una conexión caída o un archivo dañado. Un permiso negado del reporte mismo (`sin_permiso`, `fuera_de_alcance`) no se arregla cambiando de carpeta: sólo «Cerrar». Si el aula rechaza el destino o pide una razón (la política cambió con la hoja abierta), «Elegir otro destino» **vuelve a leer la política** para no repetir el rechazo. La decisión es una función pura con pruebas (`TextoDeExportacion.BotonesPara`). | Se vio en la pasada final: la frase decía «toca Guardar otra vez» y no había tal botón. |
| D-26 | **Con la privacidad aplicada, «Alumnos que necesitan atención» queda vacío en el archivo** (la pantalla ya pone «—»). | Un «0» diría «nadie necesita atención», que no es lo que se sabe: no se cuenta quién. |
| D-27 | **Los recientes se distinguen por lo que los hace distintos:** «Grupo 8A · con filtro de materia» y «Uso de equipos · desde 8 oct». Se reabren con los parámetros tal como se guardaron (un periodo «Últimos 7 días» guarda su fecha de inicio y el título la dice). No se guardan nombres del árbol (art. 14). | Tres «Grupo 8A» iguales no se podían diferenciar. |
| D-28 | **La lista de clases vacía dice por qué:** «Ninguna clase de esa materia · Toca «Quitar filtro»…», «No hay clases en este periodo», «Este grupo todavía no tiene clases cerradas» o «Todavía no hay clases cerradas». | Con un filtro de materia puesto decía «Elige otro periodo», que no explica nada. |
| D-29 | **El archivo bajado sólo se reutiliza para la MISMA clase de destino.** Si una memoria falla y se elige una carpeta del equipo (o al revés), OPS vuelve a pedir autorización al nodo, que aplica su política por clase de destino **al autorizar** (confirmar sólo anota). | Revisión independiente: el administrador pudo cerrar las memorias USB con la hoja abierta y el archivo ya autorizado para otra clase habría saltado la política. El nodo sigue anotando con verdad lo que ocurrió (`destino_autorizado` y `destino_tipo` en el asiento). |
| D-30 | **BR-085 en los filtros:** quien sólo puede ver el uso de equipos (el técnico) recibe los grupos para filtrar y **ninguna cifra**: `alumnos` y `en_atencion` van en `null`. Los códigos del árbol académico (país, nivel, grado, materia, tema) tienen que parecer un código (`[\w.:-]{1,64}`), con `400 datos_invalidos` si no. | Revisión independiente: «cuántos necesitan atención» por grupo es un dato académico, y esos valores acaban en recientes, en la exportación y en el asiento encadenado de la bitácora (que no se poda). |
| D-31 | **Endurecimientos de la exportación** (revisión independiente): el identificador que manda el nodo da nombre al temporal local, así que tiene que ser un código y nunca una ruta; el temporal se abre con `FileShare.Delete` y se borra aunque la hoja se cierre a mitad de la escritura (antes se quedaba con nombres de alumnos hasta el próximo arranque); un destino que falla se anota en el registro local con su **detalle técnico sin rutas** (la red de seguridad para el código de Windows que la tabla no conozca); una unidad de red **mapeada** que se cae se dice «no se pudo llegar a esa carpeta de red» y no «se retiró la memoria»; y poner los agregados al día antes de exportar ya no puede volver la exportación un error 500. | Cada punto tiene su prueba; ver [03-pruebas.md](03-pruebas.md#6--revisión-independiente). |

## 5 · De dónde sale cada número

| Se muestra | Lo dice | Cómo |
|---|---|---|
| Participación y aciertos de un alumno en una clase | MOD-007 `detalle_de_sesion` | Participación = actividades entregadas / recibidas. Aciertos = **puntos** ganados / posibles de lo **ya calificado**; si nada está calificado, «—». |
| Cómo quedó su tableta al cerrar | MOD-007 `presencia_al_cerrar` | La presencia que la tableta dijo antes del cierre (el cierre marca a todos «salió»: no sirve). |
| Asistencia en un grupo | MOD-007 | Clases cerradas del grupo a las que entró de verdad (no el rechazado ni el que esperaba). |
| Evaluaciones: presentó / sin presentar | MOD-010 `asignaciones_de_grupo`, `intentos_de_asignacion` | «Sin presentar» sólo cuando la evaluación ya cerró. |
| La nota de una evaluación | MOD-011 `resultados_del_grupo` | La presentación **ya resuelta por el libro** con la escala del nivel: aquí no se convierte nada. En modo simple, un símbolo (○ ◐ ●) y un estado, sin números. |
| Tareas de estudio | MOD-008 `asignaciones_de_estudio`, `tareas_de` | Estado, avance y si está vencida. |
| Equipos | MOD-009 `por_id` + la presencia de MOD-007 | Sólo el equipo y cuántos estudiantes lo usaron: **sin personas**. |
| Estado de integración | Las tres señales de D-5 | Con el motivo en una línea («1 tableta aún no sincroniza»). |

## 6 · Exportar a archivo (FUN-146)

1. **Alcance (sin efectos).** `POST exportaciones/alcance/` dice qué se va a guardar —el reporte, a cuántos alumnos toca, qué incluye, si lleva **nombres**, hasta qué corte llegan los datos, el nombre propuesto— y la **política** del administrador. No genera ni registra nada.
2. **Autorizar y generar.** `POST exportaciones/` aplica la política (destino permitido, razón si se exige), genera el archivo **en el nodo** y lo entrega en el cuerpo. OPS lo baja **directo a un temporal** calculando su SHA-256 por bloques (nunca entero en memoria) y lo compara con el que declaró el nodo.
3. **Escribir (en OPS, nunca en el nodo).** `EscrituraSegura`: se comprueba lo que se puede sin escribir (carpeta, nombre, espacio) → se copia a un **temporal en la misma carpeta del destino** → `FlushFileBuffers` → se **relee desde la unidad** (tamaño y SHA-256) → se renombra **sin sobrescribir** → ante cualquier fallo se borra el temporal. Los fallos tienen mensaje propio y accionable: memoria retirada, sin espacio, protegida contra escritura, sin permiso, red inalcanzable, nombre inválido, antivirus, archivo en uso, verificación fallida, cancelado.
4. **Confirmar.** `POST …/confirmar/` con el tipo de destino (extraíble / carpeta local / red), `guardado` + huella **releída** o `fallido` + motivo. Sin ruta, sin nombre.

**Dentro del archivo** (BR-083): *Reporte · Grupo/alumno · Periodo · Generado por · Generado el · Datos al corte · Estado de integración · Umbral de privacidad aplicado · Versión del nodo*, y las notas («incluye nombres de alumnos…», «Dominio por objetivo: aún no disponible»). Un archivo suelto sigue diciendo de dónde vino y qué tan fresco es.

**Destinos (OPS).** Atajos a Documentos, Escritorio y Descargas; las unidades del sistema con su etiqueta, letra, **espacio libre** y la marca «Extraíble» o «Red»; la última carpeta que usó esa persona (preferencia **local por usuario**, no en el backend); «Elegir otra carpeta…» (el selector nativo de Windows). La lista se **refresca sola** al enchufar o retirar una memoria (sondeo de 2 s con la firma de las unidades) y hay «Buscar de nuevo». Sin extraíbles lo dice («Conecta una memoria USB y toca Buscar de nuevo») y ofrece las carpetas locales. Si el administrador los desactivó, **no aparecen** y se dice por qué; lo mismo vale para una carpeta elegida a mano que esté en una memoria o en la red.

## 7 · Pantallas de OPS

| Ruta | Pantalla | Qué hace |
|---|---|---|
| `reportes` | **Inicio** | Tres tarjetas (Una clase · Un estudiante · Un grupo) con lo que se verá, «Uso de equipos» si el rol puede, y **Recientes**. Composición de tercios. |
| `reportes-elegir?que=` | Elegir | Clase (por periodo, grupo y materia), grupo, o estudiante (grupo → inicial → fila). Todo son fichas. |
| `reporte-clase` | **Reporte de la clase** | Una fila por estudiante (tableta al cerrar, entregó, participación y aciertos con barra desde cero) y el promedio abajo. Cabecera de corte y encabezado de tabla **fijos**. |
| `reporte-grupo` | Reporte del grupo | **Primero quién necesita atención**, con su motivo; luego todos, las clases y las evaluaciones. Sin «promedio del grupo» como dato principal. |
| `reporte-alumno` | Reporte del estudiante | Por grupo: asistencia, participación, aciertos, evaluaciones (nota en el modo del nivel), estudio y clases. |
| `reporte-uso` | Uso de equipos | Periodo por fichas, grupo, equipos y clases. |
| `reportes-estado` | Estado y ajustes | Antigüedad del dato, fuentes, «Actualizar ahora», «Reconstruir» (con confirmación), y los tres ajustes de la administración. |
| (hoja) | **Exportar** | Formato (Excel por defecto / CSV) → razón (si se exige) → destino → confirmación con el alcance → guardando con avance → resultado. Es una hoja sobre el reporte, no otra pantalla. |

Todo estado vacío, de error y de carga tiene su texto y dice **qué hacer**; nada exige teclado; los objetivos táctiles miden ≥ 48 px y las filas de tabla ≥ 52 px.

## 8 · Permisos por rol

| Rol | Permisos de reportes | Alcance |
|---|---|---|
| Profesorado | `reports.view` · `reports.group.view` · `reports.student.view` · `reports.export` | **Sus grupos** |
| Reportes | los anteriores + `reports.usage.view` + `reports.curriculum.view` (reservado); **sin** `reports.rebuild` | Toda la organización |
| Administración | todos, incluidos `reports.rebuild` y `reports.settings.manage` | Toda la organización |
| Soporte técnico | **sólo** `reports.usage.view` y `reports.rebuild` | — |
| Alumnado | ninguno | — |

La migración `acceso/0017_permisos_reportes` los siembra (depende de `0016`, de MOD-011). Cada 403 sobre datos académicos deja asiento.

## 9 · Lo que debe confirmar el CTO

1. **PDF:** queda para V1 (no hay librería en el entorno, D-12).
2. **Exportar a extraíbles por defecto:** hoy **permitido** y sin razón; ¿debe venir cerrado en las instalaciones nuevas?
3. **BR-086 (umbral de privacidad):** hoy **apagado de fábrica**, como pide el prompt; ¿debe venir activo?
4. **BR-105:** política del nodo + asiento por operación (D-14) en lugar de una autorización de salida por operación.
5. **CSV con `;` y coma decimal** (D-12): es lo que abre bien Excel en español; en una región con otro separador el CSV se vería en una sola columna (el XLSX no tiene ese problema).
6. **Permiso `reports.settings.manage`** (D-11) y las **funciones de lectura añadidas** a MOD-007, MOD-008 y MOD-011 (D-4).
7. **Criterios de «necesita atención»** (D-8).
8. **El técnico no ve la tesela** (D-21, como pedía el prompt), pero FUN-147 le da `reports.rebuild`: por la interfaz sólo la administración puede reconstruir. Si debe poder el técnico, es mostrarle la tesela con «Uso de equipos» y «Estado» y sin las tarjetas académicas.
9. **«Generado por»** muestra el alias de quien exporta (con sesión) o el identificador declarado (sin sesión, prototipo).
10. **«Incompleto» caduca a los 15 minutos** (D-5): pasado ese tiempo el reporte deja de marcarse incompleto aunque una tableta nunca haya enviado lo suyo. ¿Debe quedar marcado de forma permanente (dato que no llegó) o está bien que se apague?
11. **Una sola sesión por persona.** Iniciar sesión por la API como un usuario cierra la que ese usuario tenía abierta en OPS («Abriste tu sesión en otro equipo»): es el comportamiento del módulo de acceso, no de Reportes, pero afecta a quien prueba con la misma cuenta desde dos lugares.

**Riesgos conocidos.** No se probó con una memoria USB **física** (ver [03-pruebas.md](03-pruebas.md)): los códigos de error reales que devuelve cada dispositivo al retirarse o llenarse se clasifican con una tabla y, si aparece uno que no está, sale «No se pudo guardar el archivo» con el código completo (sin rutas) en el registro local, que lo entrega al nodo, para ampliarla. La verificación relee **sin caché** (`FILE_FLAG_NO_BUFFERING`); en FAT32, exFAT y red no se ha comprobado que esa lectura llegue al dispositivo.
