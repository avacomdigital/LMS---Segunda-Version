# Prompt · MOD-013 Reporting

> Pega todo lo que sigue, desde «# Introducción» hasta el final, como primer mensaje de una sesión nueva en este repositorio. Está escrito para que la sesión no tenga que preguntar nada: lo que falta lo decide con los criterios de abajo y lo deja dicho.

---

# Introducción

Estás en el prototipo del LMS de AVACOM (`C:\projects\prototypes\prototype-lms-v04`, rama `dev`). Tiene tres capas:

- **Backend**: Django + DRF + Channels (Daphne) en `backend/`, escucha en `0.0.0.0:8000`. SQLite. Es el **nodo** del colegio: hace CRUD y comunica por WebSocket.
- **AVACOM OPS Master** (`src/Avacom.Lms.Ops`, .NET MAUI, sólo Windows): corre en el host del profesor, **una pantalla interactiva gigante, táctil y sin teclado**. Nada de lo que construyas puede exigir escribir.
- **AVACOM Student** (`src/Avacom.Lms.Student`, MAUI en Windows y Android): lo que ve el alumno. Este módulo **no** necesita pantalla de Student.

Antes de escribir una línea, lee en este orden (son la manera de trabajar de este repo; no las reinventes):

1. `spec-driven/01-constitucion.md` — sobre todo los artículos 13 (el LMS sólo guarda el expediente) y 14 (el contenido del curso es de la Biblioteca; **no se copia al backend**).
2. `spec-driven/12-gradebook/` y `spec-driven/13-search/` (`01-diseno.md`, `02-api.md`, `03-pruebas.md`): son los dos módulos hermanos más recientes. Tu módulo se estructura, se documenta y se prueba **igual**.
3. `spec-driven/05-audit-logs/` (MOD-019) — cada exportación deja asiento; fíjate cómo `audit.export` pide una autorización de salida por operación y cómo `BitacoraPage.Exportaciones.cs` baja un archivo.
4. `prompt01.md` (raíz) — los estilos visuales vigentes. Se resumen más abajo.
5. El Documento Maestro (`AVACOM_LMS_Documento_Maestro_Consolidado_v1.0`), sección **MOD-013 · Reporting** (`#m-f-mod-013`), JRN-012 y TST-008. Lo esencial está copiado en este prompt; si algo no cuadra con el repo, **manda el repo** y lo dices.

# Objetivo

Construir **MOD-013 · Reporting** (DOM-007 · Aprendizaje y Analítica): el módulo que **no escribe ningún dato académico** y arma vistas sobre datos que otros módulos ya calcularon, recortadas siempre por el alcance de quien consulta. Y, por decisión del producto, **sube a este entregable la exportación a archivo (CAP-084 / FUN-146), que el Maestro tenía en V1**, con una condición no negociable:

> **Los profesores deben poder guardar cada reporte en un dispositivo extraíble (memoria USB, disco externo) o en cualquier carpeta que el Explorador de Windows del host vea (Documentos, Escritorio, una unidad de red mapeada o una carpeta compartida), sin internet y sin teclado.**

## Qué entra (MVP de esta entrega)

| ID | Capacidad | Notas |
|---|---|---|
| CAP-081 | Reporte de la clase al terminarla, con participación y aciertos | Profesor. Sin red. Es TST-008: clase cerrada hace 5 minutos → filtrar por clase → 25 filas y promedio calculado |
| CAP-082 | Avance individual del alumno | Informe nominal; el permiso `reports.student.view` ya existe |
| FUN-139 · 140 | Reporte de avance de un **grupo** y de un **alumno** | |
| FUN-142 | Reporte de **uso** de dispositivos y sesiones | Sólo si hay sesiones finalizadas en el periodo |
| FUN-143 | Filtrar por nodo académico y periodo | Más grupo, alumno y objetivo |
| FUN-144 · 145 | Actualización periódica de agregados fuera del horario de clase; marcar un reporte **incompleto** si hay dispositivos con cola local pendiente | Declarar el estado de integración (BR-083) |
| FUN-146 | **Exportar a archivo** | Ver §«Exportar a USB o carpeta». Alcance declarado **antes** de confirmar |
| FUN-147 | Reconstruir los agregados desde la cola | Permiso `reports.rebuild`, para el técnico |

## Qué NO entra (déjalo preparado y dilo en el diseño)

- CAP-083 comparar grupos de la misma sede y CAP-085 cobertura curricular real contra planeada (FUN-141): V1. Reserva el permiso y la ruta en el contrato, **sin implementar**. La cobertura necesita el currículo congelado de MOD-003, que no está en este repo: no inventes datos.
- CAP-086 reportes propios por dimensiones: futuro.
- **Impresión** (el Maestro la deja fuera del MVP) y la **analítica entre instituciones**.
- **Dominio por objetivo (MOD-012)**: ese módulo **no existe todavía** en `backend/`. En el reporte, esa columna/sección aparece como «Aún no disponible», no como un cero. Verifica con `ls backend` antes de afirmarlo.
- Cualquier escritura sobre datos de origen (BR-085). Si tu código llama un `save()` o un `update()` sobre tablas ajenas, está mal.

# Reglas del Maestro que gobiernan el módulo (cada una con su prueba)

- **BR-007** — Un consumidor nuevo o reconstruido empieza en marca cero y reproduce toda la cola. Las proyecciones son **reconstruibles por completo**: borrar todo `m13_*` y reconstruir devuelve exactamente los mismos reportes.
- **BR-083** — **Todo reporte declara el instante de corte** de los datos y **el estado de integración** de los dispositivos del grupo en ese instante. Se ve en pantalla («Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar») y **también dentro del archivo exportado**.
- **BR-084** — Los reportes se generan **íntegramente en el nodo local**. Ninguna llamada a internet, ninguna librería que descargue algo en ejecución.
- **BR-085** — El rol **Reportes** es de sólo lectura. El rol técnico **no** lee datos académicos (patrón TST-069 de Gradebook: las operaciones sobre datos devuelven 403 y dejan asiento).
- **BR-086** — Un reporte agregado con **menos de 5 alumnos** no expone comparativas individuales identificables **si el administrador activó el umbral de privacidad**. Es una configuración del nodo; por defecto apagada. Con el umbral activo, el reporte (y el archivo) muestran sólo el agregado y lo dicen.
- **Art. 14** — No guardes títulos de cursos, lecciones ni preguntas. Guarda **referencias** (`curso_ref`, `leccion_ref`) y pide el rótulo a la Biblioteca en el momento (o reutiliza los rótulos de evidencia que ya guardan MOD-007/008/010). Una prueba de arquitectura (como `search/tests/test_arquitectura.py`) lo comprueba.

# Cómo se construye (decisiones ya tomadas)

**Backend** — app Django `reporting` (tablas `m13_*`, migraciones desde `0001`), con la misma arquitectura en capas de `gradebook` y `search`: `dominio/` (reglas puras, sin Django), `aplicacion/` (casos de uso), `infraestructura/` (ORM, adaptadores), `interfaces/` (DRF, `urls.py`, `views.py`). Se monta en `/api/reportes/`.

- **Fuentes (sólo lectura)**: intentos y calificaciones de MOD-010 (`evaluacion`) y MOD-011 (`gradebook`), sesiones y participación de MOD-007 (`classroom_engine`), dispositivos de MOD-009 (`device_manager`), estudios de MOD-008 (`modo_estudio`), grupos y personas de MOD-001/002 (`acceso`, `expediente`). Se consumen **por los eventos que esos módulos ya publican**, con un consumidor idempotente y marca de lectura, igual que `gradebook/aplicacion/consumidor.py` y la sincronización de `search`. Si un dato no sale por evento, léelo por el servicio público del módulo dueño, nunca por sus tablas.
- **Proyecciones** (`m13_*`): sólo agregados y filas derivadas (por clase, por alumno, por grupo, por sesión). Cada una lleva `corte_en` y `estado_integracion`. Estado técnico de la proyección: `al_dia`, `reconstruyendose`, `rezagada`; **la pantalla lo muestra como antigüedad del dato**, no como estado interno.
- **Eventos que publica** (versionados `.v1`): `reporte.grupo_generado`, `reporte.alumno_generado`, `reporte.uso_generado`, `reporte.cobertura_generado` (reservado), `reporte.agregados_actualizados`, `reporte.agregados_reconstruidos`, `reporte.marcado_incompleto`, `reporte.exportado`.
- **Permisos** (siémbralos en `backend/acceso/dominio/plantillas.py` y asígnalos por rol con su alcance, revisando los roles reales del archivo): `reports.view`, `reports.group.view`, `reports.student.view` (ya existe), `reports.usage.view`, `reports.curriculum.view` (reservado), `reports.export`, `reports.rebuild`. Profesor: grupo/alumno/export sobre **sus grupos**; Reportes: lectura de toda la organización, **sin** `reports.rebuild`; administración: todo; técnico: `reports.usage.view` y `reports.rebuild` **solamente**.
- **Auditoría (MOD-019)**: cada generación sensible y **cada exportación** deja asiento: quién, qué reporte, alcance, número de filas, huella SHA-256 del archivo, **tipo** de destino (extraíble / carpeta local / red) y resultado. **Nunca** la ruta completa con nombres de personas, ni el contenido.
- **Sin sesión / con sesión**: igual que Search (`AVACOM_LMS_EXIGIR_SESION`): con sesión actúa quien firma el JWT; sin ella (prototipo) el actor declarado.
- **Errores**: mismas formas de `datos_invalidos`, `no_autorizado`, `conflicto` que los demás módulos. Mensajes en español claro para quien está frente a la pantalla, sin jerga.

**Cliente** — `src/Avacom.Lms.Core/Reporting/` (modelos, cliente HTTP, reglas puras sin MAUI), como `Core/Gradebook` y `Core/Search`. Los contratos del cliente se prueban con **respuestas reales capturadas del backend** (patrón `test_capturar_contrato.py`), no con JSON escrito a mano.

**OPS** — pantallas en `src/Avacom.Lms.Ops/Pages/` y lógica de interfaz en `src/Avacom.Lms.Ops/Reportes/` (patrón `Busqueda/` y `Calificaciones/`). El tile **«Reportes» ya existe** en `DashboardPage.xaml` (satélite superior del profesor) y hoy no lleva a nada: conéctalo, con la misma regla de visibilidad que «Calificaciones» (profesorado, administración y Reportes; no técnico ni alumno; sin sesión se deja ver y el nodo decide).

## Pantallas de OPS

1. **Reportes (inicio)** — tres tarjetas grandes: *Una clase*, *Un alumno*, *Un grupo*; más *Uso de equipos* si el rol puede. Debajo, «Recientes» del propio usuario (para reexportar sin regenerar).
2. **Reporte de la clase** (CAP-081) — filas por alumno: participación, aciertos, promedio de la clase abajo. **Cabecera fija con el instante de corte y el estado de integración** (BR-083) y, si aplica, la insignia **«Incompleto»** con el motivo en una línea («2 tabletas aún no sincronizan»).
3. **Reporte del alumno** (CAP-082) y **del grupo** (FUN-139/140) — mismas convenciones; las calificaciones se muestran **en el modo del nivel** (escala 0–100, símbolos en preescolar: no conviertas, pide al libro de MOD-011 la presentación ya resuelta).
4. **Uso** (FUN-142) — sesiones y equipos por periodo.
5. **Filtros** (FUN-143) — como **fichas táctiles** (periodo, grupo, nodo académico), nunca campo de texto. Los alumnos se eligen de una lista con búsqueda **por fichas de inicial**, no escribiendo.
6. **Exportar** — ver abajo. Se abre como hoja sobre el reporte, no como pantalla aparte.
7. **Estado de los agregados** (sólo `reports.rebuild`) — antigüedad, botón «Reconstruir», resultado.

Todo estado vacío, de error y de carga tiene su texto propio y dice **qué hacer** («No hay clases cerradas en este periodo. Elige otro periodo.»).

# Exportar a USB o carpeta (FUN-146 · lo que más importa de esta entrega)

El host de OPS es una pantalla táctil sin teclado y los profesores llevan los reportes **en una memoria USB** a otra computadora o a la secretaría. Diseña el flujo así:

**Dónde se escribe.** El archivo lo **escribe el cliente OPS** en el equipo del profesor, no el backend: el backend genera el contenido y lo entrega; OPS lo guarda donde el usuario elija. (Así sirve igual si algún día el backend corre en otra máquina y no hay riesgo de que escriba en el disco del servidor.)

**Selector de destino sin teclado, en dos niveles:**

1. **Lista táctil de destinos** detectada con las unidades del sistema (`DriveInfo`): cada fila muestra icono, nombre/etiqueta de la unidad, letra, **espacio libre** y una marca «Extraíble» para USB/disco externo. Siempre arriba, atajos a **Documentos**, **Escritorio** y **Descargas**. Las unidades de red mapeadas aparecen marcadas «Red». Se **refresca sola** cuando el profesor enchufa o retira la memoria (sondeo corto o evento de dispositivo) y tiene un botón «Buscar de nuevo». Si **no hay ningún extraíble**, lo dice con claridad («Conecta una memoria USB y toca Buscar de nuevo») y ofrece las carpetas locales; **no** se queda bloqueado.
2. **«Elegir otra carpeta…»**: abre el **selector de carpetas nativo de Windows** (el cuadro del Explorador, que ya es táctil), para llegar a una carpeta compartida o de red que la lista no muestra. Recuerda la última carpeta elegida **por usuario** (preferencia local del OPS, no en el backend) y la propone la próxima vez.

**Qué se guarda.** El profesor elige formato con dos fichas grandes:

- **Excel (.xlsx)** — por defecto; con hoja de resumen + hoja de detalle.
- **CSV (.csv)** — UTF-8 **con BOM** y separador adecuado para que Excel en español lo abra sin romper acentos ni columnas.

Revisa qué hay en `backend/requirements.txt` y `backend/.venv`: **no agregues dependencias pesadas** sin decirlo; si hace falta una librería para xlsx, que sea pura-Python y la dejas en `requirements.txt` y en el instalador (comprueba que el empaquetado del instalador la incluye). **PDF queda para V1** salvo que ya exista una librería en el entorno; di cuál elegiste y por qué. No hay impresión.

**Contenido del archivo** (también BR-083): primera hoja o primeras líneas con *Nombre del reporte · Grupo/alumno · Periodo · Generado por · Generado el · **Datos al corte** · **Estado de integración** · Umbral de privacidad aplicado (sí/no) · Versión del nodo*. Un archivo **suelto** sigue diciendo de dónde vino y qué tan fresco es.

**Confirmar con el alcance declarado** (el Maestro: «con su alcance declarado antes de confirmar»). Antes de escribir, una hoja de confirmación en lenguaje llano:

> «Vas a guardar el reporte del grupo 8A (24 alumnos, notas y asistencia, datos al 15 oct 10:42) en **E: · MEMORIA (14 GB libres)**. El archivo incluirá nombres de alumnos. Una vez fuera de este equipo, el colegio ya no controla quién lo abre.»

Botones: **Guardar** (primario, rojo de marca) y **Cancelar**. Si el reporte es **nominal** (con nombres), la advertencia aparece **siempre**; si es agregado, se dice «Sin datos de personas».

**Escritura segura** (esto es lo que más se rompe con memorias USB reales):

- Escribe a un **archivo temporal en la misma carpeta**, haz `Flush` a disco, **verifica tamaño y SHA-256 releyendo**, y sólo entonces renombra al nombre final. Si falla, borra el temporal. Nunca dejes un archivo a medias.
- Nombre de archivo **seguro para cualquier sistema de archivos** (FAT32/exFAT incluidos): sin `\ / : * ? " < > |`, sin espacios finales, ≤ 100 caracteres, determinista (`reporte-grupo-8A-2026-10-15-1042.xlsx`). Si ya existe, **no sobrescribas**: agrega un sufijo `(2)`.
- Casos que deben tener mensaje propio y accionable, no una excepción en crudo: memoria **retirada a mitad**, **sin espacio**, **protegida contra escritura**, **sin permiso**, ruta de red **inalcanzable**, nombre inválido, antivirus que bloquea. Todos dejan el reporte en pantalla intacto y permiten **elegir otro destino** sin regenerar.
- **Éxito**: «Guardado en E:\Reportes\reporte-grupo-8A-….xlsx», con el tamaño, y un botón **«Abrir carpeta»** (Explorador) y otro **«Guardar en otro lugar»**. Y un recordatorio corto: «Espera un momento antes de retirar la memoria» (ya hiciste `Flush`; no prometas expulsión segura que no implementaste).

**Registro en dos tiempos** (así la bitácora no miente): `POST` que **autoriza y genera** el export (devuelve contenido, `export_id`, huella y filas) → el cliente escribe → `POST …/confirmar/` con `resultado` (`guardado` | `fallido` + código de motivo), tipo de destino y huella verificada. Sólo entonces se publica `reporte.exportado.v1`. Una exportación que **nunca se confirma** queda marcada «sin confirmar» y caduca; no cuenta como entregada.

**Política del administrador** (ajuste del nodo, por defecto permitido a todos los destinos): poder **desactivar la exportación a medios extraíbles** y/o **exigir motivo** (que se elige de una lista, **no se escribe**). Si está desactivado, la lista de destinos oculta los extraíbles y dice por qué.

**Límites razonables**: un reporte de grupo grande (≥ 1 000 filas) debe exportarse sin congelar la UI (trabajo en segundo plano con barra de avance) y sin tener el archivo entero en memoria dos veces.

# Estilos visuales (los mismos de todo el LMS)

Sigue `prompt01.md` y copia cómo lo resuelven `CalificacionesPage` y `BuscarPage`; **no inventes un estilo nuevo**:

- **Fondo** `LinearGradientBrush` a 120° con `#FDECEC` 0 % → `#E6F6FC` 42 % → `#FEF9E6` 78 % → `#F5E8F1` 100 %. Encabezado fijo de 68 px, contenido útil ≤ 1152 px, espacio inferior para la navegación flotante.
- **Tarjetas** blancas (`#FFFFFF`) con la sombra `0 1px 1px rgba(24,24,27,.05)` + `0 4px 8px rgba(24,24,27,.09)`; secundarias `#FDFBF8`; separadores `rgba(24,24,27,.09)`.
- **Tipografía** Inter (fallback Segoe UI); texto principal `#18181B`, etiquetas `#3F3F46`, descripciones `#52525B`, metadatos `#71717A`.
- **Color por significado**: CTA y acciones críticas `#E5262B` (hover `#A20D12`); éxito/progreso `#019D60` (`#E6F5EE`); información `#01A4E1` (`#E6F6FC`); advertencia `#F3C701` (`#FEF9E6`, texto `#6B5800`); error `#FDECEC`. **«Incompleto» usa advertencia, no rojo.**
- **Iconos** Phosphor (carpeta `phospor-icons/`), peso regular o duotone. Para USB, carpeta, hoja de cálculo, advertencia y comprobado usa los que ya existan ahí; no mezcles otra familia.
- **Hexágono** sólo donde ya se usa (el tile del menú). Dentro de las pantallas, tarjetas, tablas y fichas.
- **Tablas** densas pero legibles en pantalla gigante: fila ≥ 52 px de alto táctil, encabezado fijo, cebra suave, números alineados a la derecha, **cifras con el formato y escala del nivel**.
- **Gráficos**: pocos y honestos (barras de participación/aciertos, una línea de avance); eje en cero; **nada de promedio general del grupo como dato principal** (la pantalla de «Su grupo» pone primero a los alumnos que necesitan atención, con el motivo en una línea).
- **Regla de tercios (la usa quien revisa tus pantallas)**: las tarjetas centrales caen en el **tercio central en X** y entre **1/6 y 5/6 en Y** (Grid de columnas `*,*,*` y de filas `*,4*,*`). Verifica con captura + cuadrícula **antes de reportar** que cada pantalla cumple.
- **Táctil**: objetivos ≥ 48 px, sin hover como única pista, sin arrastres obligatorios; nada exige teclado (ni siquiera para filtrar o nombrar el archivo: el nombre lo propone el sistema).
- Textos en español, con tuteo cercano y sin jerga («Datos al corte» se explica con «Esto es lo que había en el nodo a esa hora»).

# Cómo trabajar y qué entregar

1. **Plan primero** (corto) y luego construir. Si dudas entre dos caminos, escoge uno, **déjalo escrito como decisión D-n en `01-diseno.md`** y sigue; no me preguntes lo que una decisión razonable resuelve.
2. **Docs** en `spec-driven/14-reporting/`: `01-diseno.md` (decisiones, qué entra / qué no, fuentes de cada número, riesgos), `02-api.md` (rutas, cuerpos y errores **reales**, capturados del backend), `03-pruebas.md` (qué se probó con qué resultado y **qué no se pudo comprobar**). Mismo formato y tono que Gradebook y Search. Documentación sencilla: no la infles.
3. **Pruebas**:
   - Backend: dominio puro, permisos por rol (incluido que Reportes y técnico **no escriben**, y que el técnico no lee datos académicos), alcance por grupo del profesor, **BR-007** (borrar `m13_*` → reconstruir → idéntico), **BR-083** (corte e integración presentes en la vista y en el archivo), **BR-086** con el umbral activo e inactivo, idempotencia del consumidor, arquitectura (sin tablas de contenido de curso), TST-008 (25 filas y promedio), exportación en dos tiempos (autorizar → confirmar, caducidad), nombre de archivo seguro, asientos de auditoría sin contenido.
   - Core C#: contratos con respuestas capturadas, reglas puras (nombre de archivo, formateo por escala, estados vacíos, mensajes de error de escritura).
   - OPS C#: lógica de destinos (clasificar extraíble / local / red, espacio libre, caso «sin extraíbles»), escritura segura (temporal → verificación → renombre; no sobrescribe; limpia el temporal si falla).
   - **En vivo** con un nodo aislado (puerto **8010**, base de pruebas, **sin tocar las Preferences ni la clase guardada del usuario**), y OPS lanzada con perfil y ruta propios, verificada por UI Automation + captura de pantalla (ver `memory` de este proyecto: «Entorno Biblioteca y LMS», «Pruebas de Student por UIA»). Para el USB: prueba con una **unidad virtual de prueba** (VHD montado o `subst`) con espacio justo, de sólo lectura y retirándola a mitad de la escritura. **No tienes una memoria USB física**: di exactamente qué se probó con la unidad virtual y qué queda sin comprobar en hardware real. No lo des por hecho.
4. **Cierre**:
   - `manage.py test` de **todo** el backend en verde (con el comando de módulos que ya usa `spec-driven/12-gradebook/03-pruebas.md`), tests de Core/OPS/Student en verde, compilación de OPS y Student **sin errores ni advertencias nuevas**.
   - Reconstruye el instalador de OPS en `installer/latest` **subiendo la versión**, con el backend incluido (si añadiste una librería, que esté dentro). Recuerda: el build descarta el `.exe` si alguien edita `installer/` o `src/` durante la compilación; no compiles con otra sesión escribiendo.
   - **No hagas commit** salvo que yo lo pida. Cuando lo pida: commits firmados sólo por `ggalindo-avacom`, **sin coautoría de Claude**, separados en `Feature:` y `Docs:`.
   - El informe final es corto y franco: qué quedó construido, qué decisiones tomaste (D-n), **qué no se pudo comprobar** y qué debe confirmar el CTO (por ejemplo: formato PDF, política de exportación a extraíbles por defecto, si BR-086 debe venir activo).

## Restricciones que no se negocian

- No edites `backend/biblioteca/` ni la capa de fuentes de cursos; los cursos se leen siempre de la Biblioteca.
- No cambies el contrato de otros módulos para que Reporting «le sea más cómodo»: si te falta un dato, lo pides por el servicio público del módulo dueño o lo dejas como «no disponible» y lo documentas.
- Ningún texto de interfaz, mensaje de error ni nombre de archivo incluye datos personales fuera de donde el reporte nominal lo declara.
- Sin llamadas a internet en ninguna ruta del módulo (BR-084).
