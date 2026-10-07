# 04 · Audit (MOD-019) · Frontend: AVACOM LMS OPS y AVACOM Student

| Campo | Valor |
|---|---|
| Estado | **Construido** (2026-09-30). Core compartido en `src/Avacom.Lms.Core/Services/` (`RegistroLocal`, `AparatoRegistrado`, `AuditoriaApi`, `LogsApi`, `EntregadorDeLogs`, `AutorizacionDeSalida`), pantalla de OPS en `src/Avacom.Lms.Ops/Pages/BitacoraPage.*` (ruta `logs-bitacora`, hexágono «Historial» del tablero) y el lado tableta en `src/Avacom.Lms.Student/` (sesión, telemetría, conectividad, conexión). 287 pruebas de Core y 61 de Student en verde. |
| Backend | [backend.md](backend.md) (endpoints) y [modelado_datos.md](modelado_datos.md) (modelo y logs). |
| Regla común | El nodo principal de OPS es **táctil y sin teclado**: filtros por selectores y fechas de calendario, motivos de lista; lo único que se escribe es la autorización de salida (PAN-241), y la escribe OTRA persona. Las listas no tienen editar ni borrar. Nada de auditoría interrumpe una clase: sólo tarjetas, sin ventanas emergentes. |
| Verificado en vivo | OPS de prueba contra un nodo aparte (8010) con sesión obligatoria: Comportamiento, Integridad, Exportaciones (autorización → exportar → descargar, archivo firmado verificado), Accesos del técnico, Errores y Estado del equipo (técnico). Capturas en [`capturas/`](capturas/): [comportamiento](capturas/ops-comportamiento.png) · [integridad](capturas/ops-integridad.png) · [exportaciones](capturas/ops-exportaciones.png) · [errores](capturas/ops-errores.png) · [estado del equipo (técnico)](capturas/ops-tecnico-estado-del-equipo.png). |

---

## 1 · Decisiones (y por qué)

| # | Decisión | Por qué / alternativa |
|---|---|---|
| D-1 | **El aparato se identifica en cada llamada** con el id que el nodo le dio (`m09_dispositivo.id`), guardado en `AparatoRegistrado` y persistido en Preferences (`ops_dispositivo_id` / `student_dispositivo_id`). Lo aprende del latido (`POST /api/dispositivos/latido/`) y de la unión a una clase (`participante.dispositivo_id`). Sin id no hay cabecera: **nunca se inventa**. | 019-01. OPS se presenta como equipo `MASTER` al entrar al tablero (idempotente por su huella `ops-<nombre>`); Student ya se registraba al unirse y al latir. |
| D-2 | **`ClienteJson` pone `X-Avacom-Dispositivo` y `X-Avacom-Correlacion` en toda petición**; los WebSocket (`AulaSocketClient`, `ActivitySocketClient`) ponen la cabecera en el handshake y además `&dispositivo=` en la consulta (por si el handshake no admite cabeceras). `UltimoCorr` queda disponible para registrar errores con la misma correlación que el nodo. | Con un identificador se reconstruye la operación entera: petición, asiento, evento y error (§2.5). |
| D-3 | **`RegistroLocal` sustituye por dentro a `RegistroDeFallos`**, que queda como fachada (`Observar` y `Escribir` siguen donde estaban y además escriben el archivo plano de siempre). JSON Lines, niveles, canales cerrados (`escritura · comunicacion · dispositivo · aplicacion`), rotación 2 MB × 5, saneamiento por clave, ventana de repetición de 30 s para no inundar con un sondeo sin red, y una cola en memoria de los WARNING+ pendientes de entregar (500 como máximo). Nunca eleva excepciones. | §2.4 y §3.6: buffer offline, límite de almacenamiento, sin datos personales. |
| D-4 | **Entrega al nodo de mejor esfuerzo**: `EntregadorDeLogs` sube los WARNING+ cada 60 s (primera vez a los 15 s) a `POST /api/logs/clientes/`, sólo si hay equipo registrado o sesión; si falla, devuelve los renglones a la cola y el archivo local conserva todo. | «La red no puede ser requisito para diagnosticar un fallo de red.» El latido no cambió de contrato: la entrega va por su propio temporizador. |
| D-5 | **Autorización de salida (PAN-241) en el mismo equipo**: otra persona de administración escribe su documento y su clave en OPS; `AutorizacionDeSalida` (Core) la identifica, concede una escalada de `audit.export` de 30 minutos a quien usa el equipo, cierra la sesión de quien autoriza y **restaura siempre el pase** del usuario del equipo. Sin autoconcesión (el nodo la niega y aquí se corta antes). | ESC-03 / BR-101. Vive en el Core para probarse contra un nodo falso (token restaurado, cuerpo de la escalada, rechazos). Durante esos milisegundos el pase del proceso es el de quien autoriza: aceptado, está documentado. |
| D-6 | **Listas largas sin sombra.** Las filas de la bitácora y de los logs usan un borde de filo (`FilaPlana`), no la tarjeta con sombra del kit: WinUI cuenta las pasadas de layout y, con decenas de tarjetas con sombra dentro de un ScrollView, lanza `LayoutCycleException` (ocurrió con 200 líneas de log). Las pestañas son botones planos; los mensajes de una línea se recortan (`TailTruncation`) y lo técnico (JSON, huellas) envuelve por carácter. | Hallazgo de la verificación en vivo. La pestaña «Errores» muestra 80 líneas; los filtros acotan. |
| D-7 | **Student no tiene pantalla de bitácora ni de logs.** Su trabajo es alimentar: identificarse (D-1), registrar en local (D-3), entregar (D-4), y mostrar la banda «Proyectando tu pantalla al grupo» (ya existía, CMP-063/DEC-034). Lo único nuevo visible es «Exportar diagnóstico» en la pantalla de conexión (técnica): un ZIP con los logs, la versión y la configuración no sensible, en el almacenamiento privado de la app. | §5.2 de la introducción. Los mensajes al alumno siguen sin jerga; el detalle técnico va sólo al log. |
| D-8 | **Modo prototipo (nodo sin sesión obligatoria):** el hexágono «Historial» se ve y la pantalla se abre, pero el nodo responde 401 a toda ruta de auditoría; la pantalla lo dice («Esta pantalla exige identificarse») y ofrece ir al acceso. Con sesión, el hexágono sólo aparece para Administrador y Técnico. | La bitácora no tiene modo Q-34: sin persona identificada no hay quién consulte. |
| D-9 | **Un error llega a la bitácora del nodo aunque la app muera** (Bugfix 02, 2026-10-07). La cola de pendientes de D-3 vive también en disco (`{app}-pendientes.log`, JSON Lines): cada WARNING+ se anexa al escribirse, el archivo se reescribe sólo cuando el nodo **confirma** la entrega (`RegistroLocal.Confirmar`) y se recorta a 500; `Configurar` la recupera al arrancar (una sola vez por app). Un **ERROR o CRITICAL no espera al minuto de D-4**: `EntregadorDeLogs` se engancha a `RegistroLocal.Escrito` y entrega 1,5 s después (un WARNING sigue esperando al ciclo normal). Y una excepción que **termina el proceso** (`WinUI.UnhandledException` sin `Handled`, `AppDomain.UnhandledException` con `IsTerminating`) llama a `RegistroDeFallos.EntregaUrgente` y espera hasta 3 s a que el error salga antes de dejar morir la app. | Antes la cola sólo estaba en memoria y se vaciaba cada 60 s: el error que cerraba OPS se perdía con el proceso, y era justo el que había que ver. Alternativa descartada: entregar de forma síncrona cada renglón (bloquearía la clase si el nodo tarda). Un renglón puede entregarse dos veces si el proceso cae entre la respuesta del nodo y la confirmación: es preferible a perderlo. |
| D-10 | **El título de un fallo se entiende sin abrir el código.** `RegistroDeFallos.Escribir` ya no escribe el origen técnico («WinUI.UnhandledException») como mensaje: dice qué pasó en palabras, el tipo y el código de Windows de la excepción, y **dónde** (clase, método y línea de AVACOM de la pila), p. ej. «Falló la interfaz de Windows y la aplicación se cerró sin controlarlo. COMException (0x800F1000): … · en AulaContenidoView.MostrarObjeto (AulaContenidoView.cs:167)»; el detalle lleva `origen`, `tipo`, `codigo`, `donde` y `fatal`. Un fallo que la app atrapa pero que es un defecto (`RegistroDeFallos.Anotar`) lleva su propio evento (`aula.visor.fallo`, `ui.toque.fallo`) y un mensaje que nombra el objeto y la unidad afectados. | Pedido del 2026-10-07: «un técnico vea ese error y no sabría jamás de qué se trata». La traza completa sigue en `traza`. |
| D-11 | **La pestaña «Errores» abre en WARNING o peor.** El nivel del filtro es un mínimo, y antes sin filtro las últimas 80 líneas eran peticiones normales (INFO, ruta «happy»): un ERROR quedaba enterrado a los pocos segundos. Para ver todo se elige INFO o DEBUG. Tocar una fila muestra además el mensaje completo (la fila lo recorta a una línea por D-6). | Mismo pedido. |

---

## 2 · Avacom.Lms.Core (compartido)

| Pieza | Archivo | Qué hace |
|---|---|---|
| `RegistroLocal` | `Services/RegistroLocal.cs` | `Configurar(app, version, dispositivoId)`; `Info/Advertencia/Error(canal, evento, mensaje, detalle, ex, corr)`; `Escribir(nivel, …, sinFreno)`; archivos `{app}-app.log` y `{app}-errores.log` en `AVACOM_LMS_DIR_LOGS` → `%LOCALAPPDATA%\AVACOM\lms\logs` (Android: directorio privado); `Sanear`; `TomarPendientes/Devolver/CuentaPendientes`; `Leer(soloErrores, ultimos)`; `ExportarDiagnostico(rutaZip, info)` |
| `Canal` | ídem | `escritura` (cola de respuestas, paquete, log mismo), `comunicacion` (HTTP 4xx/5xx, sin red, socket caído/recuperado/rechazado, aula visible/invisible), `dispositivo` (arranque, espacio bajo, batería baja, cambio de red, reloj desfasado, equipo registrado), `aplicacion` (excepciones no controladas, estados imposibles) |
| `AparatoRegistrado` | `Services/AparatoRegistrado.cs` | `Id` (normalizado), `Recordar(id)`, `Olvidar()`, ganchos `Cargar`/`Guardar` |
| `ClienteJson` | `Services/ClienteJson.cs` | Cabeceras de aparato y correlación; `http.error` (4xx WARNING, 404 INFO, 5xx ERROR, con método, ruta y `codigo`, nunca el cuerpo) y `red.sin_conexion` al canal `comunicacion` |
| `AulaSocketClient` / `ActivitySocketClient` | `Services/…` | Cabecera y `&dispositivo=`; `socket.caida` (WARNING), `socket.recuperado` (INFO con `duracion_ms`), `socket.no_conecta`, `socket.rechazado` (con el código 44xx); `corr` por conexión |
| `DispositivosApi.LatidoAsync(…, tipo)` · `AulaApi.UnirseAsync` | `Services/…` | Recuerdan el id que devuelve el nodo; el latido declara `tipo` (`TABLETA` por defecto, `MASTER` para OPS) |
| `ColaRespuestas.Persistir` · `RelojNodo.Aprender` | `Services/…` | `cola.persistir_fallo` (canal escritura, `hresult`, sin contenido) · `reloj.desfasado` (canal dispositivo, `desfase_ms` cuando pasa de un minuto) |
| `AuditoriaApi` / `IAuditoriaApi` | `Services/AuditoriaApi.cs` | `AsientosAsync(FiltrosBitacora)`, `AsientoAsync`, `CatalogoAsync`, `TramosAsync`, `EstadoAsync`, `VerificarAsync`, `ExportacionesAsync`, `ExportarAsync(motivo, tramoId | desde, hasta)`, `DescargarExportacionAsync(id, ruta)`, `AccesosDelTecnicoAsync` |
| `LogsApi` / `ILogsApi` | `Services/LogsApi.cs` | `EntregarAsync(app, version, renglones)` (nombres snake_case del nodo) y `LeerAsync(FiltrosLogs)` |
| `EntregadorDeLogs` | `Services/EntregadorDeLogs.cs` | `Iniciar()` (temporizador), `EntregarAhoraAsync()`, `UltimaEntrega`, `Entregados` |
| `AutorizacionDeSalida` | `Services/AutorizacionDeSalida.cs` | `ConcederAsync(acceso, beneficiarioId, dispositivo, documento, clave, motivo)` → `Resultado(Ok, Mensaje, VigenteHastaMs)`; `Motivos` (lista cerrada) |
| `AccesoApi.OtorgarEscaladaAsync` | `Services/AccesoApi.cs` | `POST usuarios/{id}/escaladas/` con el pase vigente |
| Modelos | `Models/AuditoriaModels.cs` | `Asiento`, `PaginaAsientos`, `CatalogoAuditoria`, `TramoBitacora`, `EstadoBitacora` (con `Semaforo` verde/ámbar/rojo), `ResultadoVerificacion`, `Exportacion`, `ListaExportaciones`, `AccesosDelTecnico`, `LineaLog`, `LogsDelNodo`, `EntregaLogs`, `FiltrosBitacora`, `FiltrosLogs` |

---

## 3 · AVACOM LMS OPS

### 3.1 Dónde se entra

Hexágono **«Historial»** del tablero (`DashboardPage`) → ruta `logs-bitacora` (`BitacoraPage`). Con sesión de usuario el hexágono sólo se ve para `ADMIN` y `TECHNICIAN`. Al entrar al tablero, OPS se presenta ante el nodo como equipo `MASTER` (`Sesion.RegistrarEquipoAsync`) y arranca `Sesion.EntregadorDeLogs`.

### 3.2 Composición

La de `DispositivosPage`: columna centrada de 1280, cabecera (eyebrow, título, resumen) con «Actualizar» y «Menú principal», fila de pestañas planas (activa en tinta, inactivas blancas) y el contenido de la pestaña en un ScrollView. Mientras carga, esqueleto de cuatro bloques grises; ante un error, la causa y «Reintentar»; sin sesión, «Esta pantalla exige identificarse» + «Ir al acceso»; sin permiso, el mensaje y «el intento quedó registrado en la bitácora».

### 3.3 Pestañas del Administrador (PAN-240)

| Pestaña | Archivo | Contenido | Datos |
|---|---|---|---|
| **Comportamiento** | `BitacoraPage.Comportamiento.cs` | Tarjeta de filtros: `FilterPicker` de módulo, acción (acotada al módulo), resultado y persona (las vistas en la página); `DatePicker` desde/hasta con «Aplicar fechas» y «Limpiar»; chip «Operación … ✕» cuando se filtra por correlación. Resumen («N asientos · del más reciente al más antiguo · enmascarados»). Filas: hora, actor (alias + roles), acción (etiqueta + `modulo · accion`), objeto, chip de resultado (verde/ámbar/rojo; la fila se tiñe si no es `ok`), dispositivo abreviado. «Cargar más» con el cursor `antes=`. Al tocar una fila se despliega el **detalle**: valor anterior → nuevo (el nuevo en verde cuando hubo anterior), aviso de enmascarado (BR-131), motivo, origen, dispositivo, secuencia, tramo, correlación, huella y previa completas (del detalle del nodo), y «Ver operación completa» (filtra por correlación) | `GET asientos/`, `asientos/{id}/`, `catalogo/` |
| **Integridad** | `BitacoraPage.Integridad.cs` | Semáforo grande: **«Cadena verificada»** (verde, fecha, cabeza, huella, asientos y tramos) · **«Salto detectado en la secuencia N»** (rojo, causa en lenguaje llano) · «Protección de la bitácora ausente» (triggers) · «Sin verificar todavía» (ámbar). Botón «Verificar ahora» (al terminar, tarjeta con el resultado). Barra de tamaño frente al umbral de rotación. Lista de tramos (rango, chip de estado, asientos, verificado/exportado/rotado, huella de cierre) | `estado/`, `tramos/`, `verificar/` |
| **Exportaciones** | `BitacoraPage.Exportaciones.cs` | Tarjeta de autorización: verde «Autorización de salida vigente (vale UNA exportación)» o ámbar con la explicación y el botón **«Autorizar esta salida»**, que despliega el formulario PAN-241 (documento y clave de quien autoriza, motivo de lista, «Conceder 30 minutos»; el estado dice que quien autoriza no deja sesión abierta). Exportador con **alcance declarado**: `FilterPicker` de tramo («Tramo 1 – 242 · Verificada») y de motivo (lista del nodo) y «Exportar» (deshabilitado sin autorización). Éxito: MSG-054 «Queda registrado que exportaste tramo 1-242.» con total y archivo; la autorización se consume. Errores de negocio en el rótulo (sin autorización, salto, no verificado). Lista de exportaciones: fecha, alcance y total, motivo y archivo, chip «Firmado»/«Archivo no disponible», **«Descargar»** → `%USERPROFILE%\Downloads\avacom-auditoria\exportacion-<id>.jsonl` (o AppData si no hay Descargas) y «Guardado en …» | `exportaciones/`, `exportar/`, `exportaciones/{id}/descargar/`, `POST acceso/sesiones/` + `usuarios/{id}/escaladas/` |
| **Accesos del técnico** | `BitacoraPage.Tecnico.cs` | Indicador verde «Sin acceso a datos personales en el periodo» (con la cadena verificada es la prueba, VER-01) o rojo si accedió; aviso si hay salto. Periodo con `DatePicker` («Aplicar periodo», «Todo el historial»), técnicos, asientos y denegaciones; filas iguales a Comportamiento | `tecnico/accesos/` |
| **Errores** | `BitacoraPage.Errores.cs` | `FilterPicker` de app (`backend`, `ops`, `student`), canal y nivel; resumen «happy N · sad N · bad N · total, se muestran las últimas 80». Filas: hora, chip de nivel, canal, app, mensaje (una línea) y evento · equipo · corr, chip de ruta. Al tocar: detalle JSON, últimas líneas de la traza, archivo, módulo, corr y caso. Sin datos personales | `GET /api/logs/` |

### 3.4 Técnico (PAN-242 · «Estado del equipo»)

Misma pantalla con otro título («Diagnóstico del nodo y de los equipos») y dos pestañas: **Estado del equipo** (nodo en servicio / sin instalar / sin respuesta con el servidor y si exige sesión; este equipo: versión, nombre, plataforma, id ante el nodo, espacio libre, carpeta de logs, logs pendientes de entregar y última entrega; botones «Entregar logs ahora» y **«Exportar diagnóstico»** (ZIP en Descargas con logs, versión, servidor, fuente del aula, rol); «Últimos avisos de este equipo» con las 20 últimas líneas WARNING+ locales) y **Errores** (la misma de arriba). El técnico **no** ve Comportamiento, Integridad, Exportaciones ni Accesos: el nodo le niega `audit.read` y lo asienta.

### 3.5 PAN-241 · Escalada temporal

Está dentro de «Exportaciones» (D-5). Mensajes: MSG-052 al conceder («Autorización concedida hasta las HH:mm. Se registra todo lo que hagas con ella»); al vencer o consumirse, la tarjeta vuelve a ámbar. No hay pantalla aparte: la escalada se concede para una operación concreta y en el acto.

### 3.6 Lo que OPS hace sin pantalla

`Sesion.PrepararAparato()` (al arrancar: `RegistroLocal.Configurar("ops", versión, id)` y los ganchos de Preferences), latido `MASTER` al entrar al tablero, entrega de logs cada minuto, cabeceras en todas las llamadas y en el WebSocket del profesor.

---

## 4 · AVACOM Student

| Qué | Dónde | Cómo |
|---|---|---|
| Identificarse en cada llamada (019-01) | `Sesion.PrepararAparato()` (desde `MauiProgram`), `AulaApi.UnirseAsync`, `DispositivosApi.LatidoAsync` | El id de `m09_dispositivo` que devuelven la unión a clase y el latido queda en Preferences (`student_dispositivo_id`) y viaja en `X-Avacom-Dispositivo` y en el handshake de `AulaSocketClient` (`&dispositivo=`) |
| Logs locales (§2.4) | `RegistroLocal` (`student-app.log`, `student-errores.log` en `%LOCALAPPDATA%\AVACOM\lms\logs` o el directorio privado en Android) | `app.arranque` (versión, plataforma, servidor); `red.cambio` y `aula.invisible/visible` (`ConnectivityService`, sólo transiciones); `espacio.bajo/normal` (< 500 MB) y `bateria.baja/normal` (< 15 %) al leer la telemetría del latido (`Telemetria.Vigilar`, sólo al cruzar el umbral); `cola.persistir_fallo`; `socket.*`; `http.error`; `reloj.desfasado`; `excepcion.no_controlada` (lo que hoy va a `fallos-student.log`) |
| Entrega al nodo (mejor esfuerzo) | `Sesion.EntregadorDeLogs.Iniciar()` en `App.CreateWindow` | Cada minuto, sólo con equipo registrado o sesión; sin red espera y el archivo local conserva todo |
| Indicador de proyección (CMP-063, DEC-034) | `ClaseSiguiendoPage` (`ProyectandoBanda`, ya existía) | Banda discreta «Proyectando tu pantalla al grupo» mientras el nodo lo diga; nunca durante un examen (el nodo no proyecta en examen) |
| Errores al alumno | Sin cambio | Mensajes cortos y sin jerga; el detalle técnico sólo al log. Nunca se le muestra una secuencia ni una huella |
| Exportar diagnóstico (§3.6) | `ConnectionPage` (botón discreto bajo «modo demo») | ZIP con los logs del aparato, versión, plataforma, servidor y pendientes de entrega, en `FileSystem.AppDataDirectory/diagnostico/`; la ruta se muestra en la tarjeta de estado |
| Sin datos personales en el log | `RegistroLocal.Sanear` | Mismas claves prohibidas que el nodo; en una tableta compartida el log no conserva nada de la persona saliente porque no lo contiene |

---

## 5 · Resumen OPS ↔ Student

| | OPS | Student |
|---|---|---|
| Pantalla de bitácora | Sí (Administrador), 5 pestañas | **No** |
| Pantalla de errores / estado del equipo | Sí (Administrador y Técnico) | **No** (sólo «Exportar diagnóstico») |
| Logs en archivo local | Sí (`ops-app.log`, `ops-errores.log`) | Sí (`student-app.log`, `student-errores.log`) |
| Cabecera de dispositivo en cada llamada y en el WebSocket | Sí (equipo `MASTER`) | Sí (tableta) |
| Entrega de logs al nodo | Sí, cada minuto | Sí, cada minuto |
| Autorización de salida | Sí (PAN-241 dentro de Exportaciones) | — |
| Indicador de hechos auditados | — | «Proyectando tu pantalla al grupo» |

---

## 6 · Pruebas

| Dónde | Qué cubre |
|---|---|
| `tests/Avacom.Lms.Core.Tests/AuditoriaTests.cs` | Campos mínimos del renglón y archivos app/errores; saneamiento en cualquier nivel; rotación por tamaño; cola de pendientes (`TomarPendientes`/`Devolver`); ventana de repetición; el logger nunca eleva; `Leer` y `ExportarDiagnostico`; fachada `RegistroDeFallos`; cabeceras de aparato y correlación en cada petición; `AparatoRegistrado` con ganchos y normalización; latido y unión recuerdan el id; `http.error` y `red.sin_conexion` sin cuerpo; URI del canal con `dispositivo`; `AuditoriaApi` (filtros en la query, DTOs, estado, tramos, verificar, exportar sin nulos); `LogsApi` (nombres snake_case) y `EntregadorDeLogs` (devuelve lo no entregado, no intenta sin equipo ni sesión); Bugfix 02: un ERROR se entrega sin esperar al minuto y un WARNING no, una caída entrega antes de morir y nunca espera más de lo concedido, la cola sobrevive a un cierre y se recupera al arrancar, lo tomado sigue en disco hasta confirmar, la cola en disco no crece sin límite, y el título de un fallo lleva tipo, código y lugar |
| `tests/Avacom.Lms.Core.Tests/AutorizacionDeSalidaTests.cs` | Otra persona concede con su pase y el pase del equipo vuelve; sin autoconcesión; credenciales malas, sin permiso y entradas incompletas |
| `tests/Avacom.Lms.Student.Tests` | La lógica del modo de estudio sigue en verde con `ConnectivityService` registrando transiciones |
| Verificación en vivo (2026-09-30) | OPS compilada aparte contra un nodo 8010 con sesión obligatoria y datos sembrados: las cinco pestañas y el estado del equipo; exportación con autorización concedida por otra identidad, archivo descargado (242 asientos) con firma válida y cadena del archivo verificada; el nodo recibió en `backend-clientes.log` el aviso que OPS entregó con su `dispositivo_id` y su `usuario_id` |

**Trampas que dejó la verificación.** UI Automation sobre la OPS de prueba durante una navegación la cuelga (nativo, WinUI): para capturar, `PrintWindow` por HWND y ganchos de entorno temporales (retirados antes del commit). `ValuePattern.SetValue` sobre un `Entry` no actualiza `Entry.Text` de MAUI: por eso la autorización se probó por unidad (Core) y, en vivo, concediéndola por la API como la otra persona.

---

## 7 · Pendiente / preguntas

1. **Android**: compila el mismo Core; falta correr Student en una tableta real para confirmar la carpeta privada de logs y la batería/espacio.
2. **Estado del equipo en OPS**: «servicios» y «último punto de recuperación» del instalador (PAN-242) aún no se consultan; hoy muestra nodo, equipo, logs y diagnóstico.
3. **Aviso diferido de salto** en OPS (alerta administrativa fuera de clase, S4): el semáforo lo muestra al entrar a «Integridad»; no hay todavía un aviso en el tablero.
4. **Q-2** (firma asimétrica para que un tercero verifique sin el nodo) y **Q-5** (si el nodo guarda los renglones de los equipos): construido con HMAC y guardando en `backend-clientes.log`, a confirmar con el CTO.
