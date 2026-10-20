# 15 · Licenciamiento (MOD-018) · Pruebas

Qué se probó, con qué resultado y —con la misma franqueza— qué **no** se pudo comprobar. Corridas del **2026-10-20** (Fases 0 a 3).

## 1 · Resultado

| Qué | Cuántas | Resultado |
|---|---|---|
| Backend `licenciamiento` (`manage.py test licenciamiento`) | «N_LIC» (6 omitidas: la captura de contrato sólo corre con `AVACOM_CAPTURAR_CONTRATO`, y la de interoperabilidad con el emisor se salta sola si `tools/licencias` no está en el árbol) | «R_LIC» |
| Mutación de licencias (`test_mutaciones.py`) | **100 000 mutaciones con semilla fija, 0 aceptadas**; toda mutación de un solo bit rechazada; 1000 llaves ajenas con un `kid` conocido; firmas aleatorias | ✅ |
| Backend, **todo** (`manage.py test`) | «N_TODO» («O_TODO» omitidas) en «T_TODO» s. **Línea base de antes de empezar: 1945 (8 omitidas), 870 s** | «R_TODO» |
| `makemigrations --check` | Sin migraciones pendientes (también lo comprueba `test_arquitectura.py`) | «R_MIG» |
| Core C# (`Avacom.Lms.Core.Tests`) | «N_CORE» (línea base 1221) | «R_CORE» |
| OPS C# (`Avacom.Lms.Ops.Tests`) | «N_OPS» (línea base 399) | «R_OPS» |
| Student C# (`Avacom.Lms.Student.Tests`) | «N_STU» (línea base 102; Student no cambia) | «R_STU» |
| Compilación | OPS y Student: «R_COMP» | |
| Instalador de OPS | «R_INST» | |
| Lo visto en pantalla | «R_UIA» | ver §5 |

Ninguna prueba existente cambió: las pruebas nuevas están en `backend/licenciamiento/tests/` y en `tests/Avacom.Lms.*.Tests`. Las pruebas de integración usan **un nodo real** (`BaseLicencia`: instalado por HTTP como lo hace OPS, con organización, administración, un docente, un estudiante y una tableta) con la licencia en modo `firmada` y sólo **dos cosas falsas** que el módulo recibe del mundo: el reloj del nodo y el hardware de «este equipo». Todo lo demás es de verdad: la base de datos, la bitácora encadenada, las anclas en una carpeta temporal, los permisos por rol y el middleware.

## 2 · Casos del Documento Maestro

| Caso | Dónde | Qué demuestra |
|---|---|---|
| **TST-060** restaurar en un equipo nuevo con hardware distinto | `test_evaluar.py::HuellaTests::test_tst_060…` | Se instala en otro equipo y se restaura la base: la licencia es de **otro hardware** → gracia completa de 30 días, **la clase se inicia y opera**, Reportes sigue activo; pasada la gracia se degradan **sólo** los módulos licenciables (Reportes responde 402) y la clase sigue; la solución es una solicitud de **este** equipo → una licencia nueva (serie 2, otra huella) → activar, que ahora es un **traslado** (D-10) |
| **VER-10** un módulo deshabilitado por licencia | `test_middleware.py::ModulosApagadosTests` | «No disponible por licencia» (402), **no** «acceso denegado»; el permiso del rol se conserva y vuelve a funcionar al renovar **sin reasignar roles**; el bloqueo se asienta como `licencia.bloqueo_aplicado`, **uno por actor, módulo y hora**, escrito por el programador y no en el camino de la petición |
| **JRN-020** reemplazar el equipo del aula | `test_activacion.py` (`LiberarTests`, `TrasladoTests`), `test_nodo.py`, `test_emisor_real.py` | El equipo viejo genera su `.avrel` firmado y el nuevo recibe la licencia de la misma `id` con otra huella (activada por el **técnico**); el equipo nuevo que **restauró la base** del viejo trae la licencia anterior y el técnico la sustituye sin `license.renew`; una licencia emitida con `liberacion_pendiente` opera con el plazo que trae; una base restaurada no resucita lo liberado |
| **FUN-188 / FUN-191 / FUN-194** activar, renovar, reactivar | `test_activacion.py` | Activar, renovar con serie posterior, volver a poner el mismo archivo tras una restauración (`reactivada`, sin pedir nada) |
| **FUN-189 / FUN-190** validar al arrancar y contar | `test_evaluar.py` | La primera evaluación abre la ventana y deja asiento, evento y ancla; repetirla no repite nada; el consumo cuenta equipos sin el maestro y usuarios sin visitantes y se guarda una vez por hora |
| **FUN-192 / FUN-193** gracia y degradación | `test_estado.py` (tabla), `test_evaluar.py` | La gracia y la degradación **salen del tiempo**, con histéresis de 24 h; degradar no toca el núcleo |
| **CAP-111** copia de la licencia | `test_activacion.py::CopiaTests` | La copia es **el mismo archivo firmado** que se instaló y no cambia nada; quien no lee la licencia no la ve |
| **BR-027 / BR-063** cupo y concurrencia | `test_cupo.py` | §3 |

## 3 · Lo que se comprobó, por área

**Formato y firma** (`test_formato.py`, 29). Una licencia se lee igual que se escribió y mide **menos de 600 bytes**; el mismo contenido da siempre los mismos bytes; la variante texto va y vuelve y es **estricta** (ni el último carácter admite variantes). Se **rechazan**, aunque estén bien firmadas: versión menor o mayor, `kid` desconocido, firma de otra llave con un `kid` conocido, etiqueta crítica desconocida (una no crítica se ignora), bit crítico cambiado, etiquetas desordenadas o repetidas, bytes sobrantes dentro de lo firmado o después de la firma, **toda licencia truncada**, un archivo demasiado grande (ni se mira), el *magic* equivocado, campos obligatorios y rangos, capacidades desordenadas o mal formadas, una huella mal formada. La solicitud va firmada por el nodo, **no lleva identificadores crudos ni datos de personas**, alterarla la invalida y no se acepta como licencia ni al revés.

**Mutación** (`test_mutaciones.py`, 7). 100 000 mutaciones de una licencia válida con semilla fija (un bit o varios, un byte, tramos reemplazados, insertados, borrados o intercambiados, cortes, bytes añadidos al final y tramos puestos a cero; también sobre la variante texto): **ninguna aceptada**; todo cambio de un bit es rechazado; la firma de una licencia no sirve para otra; el algoritmo está fijado (la firma no se negocia).

**Huella** (`test_huella.py`, 29). 36 valores de relleno de placas OEM no identifican a nadie (ceros, `FFFF…`, «To be filled by O.E.M.», «Default string», UUID de relleno…) y los reales sí cuentan; un factor basura no llega al hash; el `ProcessorId` **no sella** (D-3); el hash es distinto por factor y estable, y cambia con la clave de producto. **k de n**: el mismo equipo coincide en todo; con cuatro factores sobrevive al cambio de uno (y lo avisa) pero no al de dos; con tres, a un disco o a un dato pero no a una placa nueva; un disco clonado a otra placa **no pasa**; con dos se exigen los dos. La huella de instalación coincide con el secreto de **este** nodo y con ninguno más, y nunca se niega una solicitud por tener hardware pobre. Tablas SMBIOS fabricadas a mano, **incluida la de una placa de panel que sólo trae relleno de fábrica**, y una tabla rota o vacía no lanza.

**Estados** (`test_estado.py`, 35 filas de la tabla). La tabla completa de estado × reloj × gracia × huella × liberación × cupo, determinista; **ninguna combinación produce un estado fuera del catálogo**; la degradación nunca toca el núcleo porque el núcleo no es una capacidad; los límites vienen de la licencia o de la evaluación; los avisos escalonados y el aviso de evaluación desde el primer día; la tolerancia de inicio de un día (§4).

**Evaluación y reloj** (`test_evaluar.py`, 19). La ventana de evaluación empieza al primer arranque (P-14), nadie se bloquea por actualizar y a los 30 días se degrada **sin cortar nada**; restaurar una base vieja **no reinicia la evaluación**; un ancla alterada no cuenta y se avisa como integridad alterada; **retroceder el reloj no alarga una licencia**, deja rastro una sola vez y no aplaza la degradación; un respaldo viejo restaurado no rebobina el vencimiento; el paso normal del tiempo no es un salto; un **salto hacia adelante** no degrada a nadie, avisa y espera confirmación, y no aplaza la degradación para siempre (72 h); un ciclo sin novedades **no abre una transacción de escritura**; repetir un ciclo no repite asientos ni eventos.

**Activación y permisos** (`test_activacion.py`, 40). Pedir la solicitud (hardware pobre incluido), activar para este equipo, en base64 y en texto (con los saltos de línea de un copiar y pegar), la firma alterada (deja asiento `firma_invalida` y no cambia nada), `kid` desconocido, una licencia de desarrollo en producción, otro equipo (409 sin cambiar nada); renovar con una serie posterior, no volver a una anterior, no cambiar de licencia con una sana sin liberar; liberar; deshacer una liberación; **permisos por rol** (la administración hace todo, el técnico lee, pide, activa y libera pero no renueva, el profesor, el alumno y Reportes no ven datos de la licencia pero sí qué módulos hay, sin sesión nada con la sesión obligatoria); una licencia que empieza en el futuro se rechaza y una que empieza dentro del día de tolerancia **rige desde ya**, también como renovación y con la evaluación vencida.

**Middleware y lista blanca** (`test_middleware.py`, 17). Con la licencia degradada cada módulo licenciable responde **402 y no 403**; lo que **cierra puertas** y las calificaciones no se licencian (D-6); `HEAD` se trata como `GET` y `OPTIONS` pasa (D-11); la lista blanca **sale de los `urls.py` reales** (no de una enumeración) y **con la licencia degradada cada ruta intocable responde igual que sin licencia**; las rutas que cargan colas del cliente nunca responden 402 (R-02); un fallo interno de licenciamiento **deja pasar** (R-04); sin estado todavía, pasa; una licencia que no se puede evaluar conserva el último estado bueno; **0 consultas SQL en el camino caliente**, también cuando bloquea (R-07); 40 hilos piden módulos permitidos y bloqueados mientras el programador evalúa y asienta, **sin «database is locked»**.

**Cupo** (`test_cupo.py`, 16). Equipos: uno nuevo cabe hasta el límite y el siguiente recibe `402 cupo_agotado`; el latido de uno nuevo cuenta y el de uno registrado **nunca**; el equipo maestro no consume cupo ni se bloquea; un equipo que aparece por el aula no se bloquea nunca (R-01); el bloqueo se asienta agregado. Usuarios: uno nuevo cabe hasta el límite; lo que ya existe sigue funcionando con el cupo lleno; **la importación crea hasta el cupo y rechaza el resto fila por fila**; el autorregistro del alumno cuenta y el ingreso de un visitante **nunca** se bloquea; un profesor tampoco da de alta sobre el cupo pero su clase sigue; un límite sin tope no bloquea nada. Concurrencia: el aula toma 50/100 de la licencia, el tercer dispositivo nuevo no entra pero el ya admitido se readmite, y sin licencia valen los de `settings`.

**Entorno de producción** (`test_entorno_produccion.py`, 6; P-12). Un nodo con el marcador `.avacom-canal` en disco, o bajo `Program Files`, es de producción **aunque `AVACOM_LMS_ENTORNO` diga `pruebas`**; este repositorio se clasifica como pruebas con `manage.py test`; el modo y la carpeta de estado de un nodo de producción **no obedecen a ninguna variable**; con `AVACOM_LMS_ENTORNO=pruebas` en el texto editable el nodo instalado **sigue evaluando** y degrada cuando toca (sin tocar el `%ProgramData%` ni el registro reales de quien corre las pruebas); la llave de desarrollo no se carga en producción y, hasta la ceremonia, ninguna otra.

**Identidad del nodo** (`test_nodo.py`, 17; D-9). Un secreto o una llave que esta máquina no abre se **aparta sin borrar** y el nodo conserva una identidad **estable** entre arranques; la novedad se asienta **una sola vez** como integridad alterada, sin nombres de archivo ni contenido, y si la base no la acepta **vuelve a la cola**; si DPAPI no responde *ahora* o el disco no dejó leer el archivo, **no se toca**; si no se puede apartar, no se pisa; sólo se conservan los últimos 5 apartados; y un recorrido de extremo a extremo de **F-08** (reinstalar Windows en un panel con SMBIOS de relleno: gracia → solicitud nueva con llave estable → el técnico activa la serie 2).

**Un nodo sin organización** (`test_sin_organizacion.py`, 4). El estado se calcula igual (`sin_licencia`, evaluación desde el primer arranque, aviso desde el primer día), el consumo responde `null` y los 409 `no_instalado` siguen siendo de cada módulo dueño de su dato (§10 de [01-diseno.md](01-diseno.md)).

**Migraciones y triggers** (`test_migraciones.py`, 5). La migración de `acceso` reparte los tres permisos en una instalación que ya existía y es **idempotente**; los tres triggers existen y la migración se puede repetir; la marca alta sube pero **no baja**; el historial y las observaciones son de sólo inserción.

**Arquitectura** (`test_arquitectura.py`, 17). Dominio y aplicación no importan frameworks ni a otros módulos, las dependencias apuntan hacia adentro, **ninguna lee un reloj** (R-06), **nada habla con internet** (R-13), ningún archivo del módulo trae una clave privada ni un generador de licencias, el dominio no usa azar inseguro; el módulo no lee ni escribe las tablas de otro (R-08) y el resto del proyecto consulta la licencia sólo por `servicios.py`; los repositorios no actualizan ni borran el historial; **el instalador no copia las pruebas ni la llave de desarrollo al paquete**; las seis tablas `m18_*` están clasificadas una sola vez, sin claves foráneas fuera del módulo ni columnas con personas o claves de datos; las acciones de bitácora, los eventos (siete del Maestro más las extensiones marcadas) y las capacidades están en sus catálogos cerrados; y la migración está al día.

**Interoperabilidad con el emisor** (`test_emisor_real.py`, 13; escrito por la sesión que mantiene `tools/licencias/`). Lo que firma la herramienta lo activan, renuevan y trasladan el nodo real por su API, con su middleware, su historial y su estado: licencia nueva de punta a punta, la herramienta y el nodo leen lo mismo, una licencia sin la llave pública del nodo no se acepta, plan de evaluación, límites y módulos a mano, renovar, el técnico no renueva ni por la puerta de activar, traslado con la liberación del equipo viejo, **liberación pendiente** (45 días), el técnico traslada al equipo que restauró la base, y un reloj atrasado 30, 45 y 72 horas. Usa **sólo llaves que la propia prueba crea** (en una carpeta temporal, que muere con ella) y se salta sola si `tools/licencias` no está en el árbol.

**Contrato con los clientes** (`test_capturar_contrato.py`, 6). Recorre el flujo completo contra el backend de verdad y guarda **41 respuestas reales** (JSON) en `tests/Avacom.Lms.Core.Tests/Fixtures/licencia/` —estado en cada situación, consumo, capacidades, copia, solicitud, activación, renovación, reactivación, liberación y cada error— más cinco archivos de ejemplo (un `.avlic` en binario, en texto y alterado, un `.avreq` y un `.avrel`). Los DTO de C# las leen tal cual.

## 4 · La revisión independiente

Una sesión que no escribió este código (la de `tools/licencias/`) lo leyó y **reprodujo** dos defectos con mi propio dominio y planteó tres puntos de diseño. Lo que pasó con cada uno:

| Hallazgo | Qué se hizo | Prueba |
|---|---|---|
| **BUG-1** · `Instalar` aceptaba una licencia con `desde` a menos de un día pero `calcular` la tomaba por «aún no vigente»: con la evaluación vencida el colegio quedaba **degradado** hasta que llegara `desde`, también en una renovación | Una sola tolerancia (`tolerancia_inicio_ms`) para los dos lados (D-8) | Tres filas de la tabla de estados (12 h, 24 h, 25 h) y dos pruebas de activación (con la evaluación vencida y como renovación) |
| **BUG-2** · un secreto propio ilegible devolvía un valor en memoria y no guardaba nada: una identidad distinta en cada arranque (F-08, sin salida) | Se aparta, se guarda uno nuevo y se asienta (D-9) | §3, «Identidad del nodo» |
| **DECISIÓN-A** · el técnico recibía un 403 al trasladar la licencia al equipo que restauró la base | Traslado = otra huella (`license.activate`); renovar = la misma (D-10) | `TrasladoTests`, y la prueba de TST-060 cambió de «renovada» a «activada» |
| **MENOR** · un `HEAD` se saltaba el 402 | `HEAD` como `GET` (D-11) | `test_head_se_trata_como_get…` |
| **DECISIÓN-B** · un salto accidental al futuro deja la marca alta alta | **No se cambió**: es tocar P-06 y la propuesta tiene un hueco (el aplazamiento se mediría en la línea de tiempo adelantada, y no cubre un salto con el nodo apagado). Queda como **Q-L13** | — |

Y un defecto que apareció **al repasar**: la prueba de P-12 («`AVACOM_LMS_ENTORNO=pruebas` en `backend.env` no apaga la licencia») usaba la carpeta de estado de **producción**, que es el `%ProgramData%` real de quien corre las pruebas: la primera corrida dejó ahí un ancla de reloj con una fecha 31 días en el futuro y la segunda fallaba. Se corrigió (la prueba redirige `%ProgramData%` y pone un registro de mentira) y se limpió lo que había dejado la corrida anterior. La lección: **ninguna prueba de este módulo debe usar el `%ProgramData%` ni el registro reales**.

## 5 · Interfaz (Core, OPS)

«R_UI»

## 6 · Lo que NO se pudo comprobar

- **El TPM y el SMBIOS del panel real.** La Fase 0 midió **una** máquina de desarrollo, no el panel que se compre (Q-L2): allí sólo 2 factores distinguen el equipo y las series de placa, chasis y BIOS son «Default string». `tpmtool` y el proveedor CNG de plataforma se abren sin elevar, pero **no se crearon claves**.
- **La estabilidad de la huella ante una reinstalación real de Windows, el cambio de placa o de BIOS**, y **la unicidad entre máquinas** del UUID y del MachineGuid (sólo hay una). La reinstalación se simuló apartando los archivos protegidos, no reinstalando.
- **DPAPI desde la cuenta del servicio** (SYSTEM): sólo se probó con un proceso de usuario estándar; que cualquier cuenta de la máquina abra un blob de ámbito de máquina es comportamiento documentado, no medido.
- **El ancla del registro de Windows** (`HKLM\SOFTWARE\AVACOM\OPS Master\Licencia`): sólo se probó con un registro de mentira; escribir de verdad exige SYSTEM o un administrador y no se ejecutó nada elevado.
- **El programador dentro de Daphne con tráfico real**: se probó el ciclo (`Programador.tick`, `iniciar`) y su interacción con 40 hilos, no el proceso ASGI instalado como servicio.
- **Una instalación real con administrador** del paquete con licenciamiento, ni la **actualización de un nodo ya instalado** (P-14): se probó la evaluación al actualizar con una base y una carpeta de estado de prueba, no con el instalador.
- **Una tableta Android 14 física**: el único dispositivo es el AVD `Pixel_10`, y su Keystore reporta `software` ([anexo](anexo-fase0-keystore-avd.md)). Student no tiene lógica de licencia y no cambia en estas fases.
- **Windows 10 de panel**, **un antivirus** que bloquee la DLL (todavía no hay DLL: Fase 4) y **la firma de código** (no hay certificado, Q-L9).
- **Que ninguna licencia real valide**: `claves/produccion.json` está vacío hasta la ceremonia de llaves (Q-L3); la verificación se probó de punta a punta con llaves de desarrollo y con las que la herramienta de emisión crea en la prueba, nunca con una de producción.
- **Un ejercicio adversarial** es una foto de un día y no un certificado, y todavía no se ha hecho (Fase 6); nada de lo anterior demuestra que la licencia «no se pueda romper», y este documento no lo afirma ([01-diseno.md](01-diseno.md) §14).
