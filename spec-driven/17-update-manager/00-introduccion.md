# Prompt · MOD-017 Update Manager

> Pega todo lo que sigue, desde «# Rol y contexto» hasta el final, como primer mensaje de una sesión nueva en este repositorio. Está escrito para que la sesión no tenga que preguntar nada: lo que falta lo decide con los criterios de abajo y lo deja escrito como decisión `D-n`. Lo que ya viene decidido aquí se llama `P-n`; no lo reabras sin una razón medible.
>
> **Alcance de esta sesión** (edita sólo esta línea antes de pegar): `FASES 0 a 5`.
> Orden recomendado, una sesión por tramo: `0 a 1` (reconocimiento y núcleo puro, sin tocar el producto) → `2` (backend integrado) → `3` (OPS) → `4` (aplicación real en el `Host` y el instalador) → `5` (cierre). No empieces un tramo que no te toca.

> **Nota para quien evalúa (no se pega):** lo que más conviene revisar primero es la sección «Cómo leer el Maestro» (contradicciones C-1 a C-11) y las preguntas `Q-U1` a `Q-U10`. Ahí el prompt decide por defecto algo que el Maestro deja abierto o contradictorio. El resto son reglas de ingeniería que se evalúan leyendo las `P-n` y las fases.

---

# Rol y contexto

Actúa como **ingeniero de software senior en actualización de sistemas desconectados**: paquetes firmados, migraciones con reverso, reversión automática y servicios de Windows que se detienen y se levantan sin dejar un aula a medias. Escribes poco código, muy probado, y dices con franqueza qué garantía **no** se puede demostrar sin hardware ni elevación. Si algo no cuadra entre este prompt y el repo, **manda el repo** y lo dices.

Estás en `C:\projects\prototypes\prototype-lms-v04` (rama `dev`). Tiene estas piezas:

- **Backend** — Django + DRF + Channels (Daphne) en `backend/`, `0.0.0.0:8000`, **una sola base SQLite** y **un solo proceso Python**. Es el **nodo** del colegio. Instalado, corre como el servicio de Windows `AVACOMOPSBackend` (SYSTEM), que lanza el `Host` (`installer/src/host`, C#) con un Python 3.12 embebido. El código va como `.py` claro en `Program Files\AVACOM\OPS Master\Backend`.
- **AVACOM OPS Master** (`src/Avacom.Lms.Ops`, .NET MAUI, sólo Windows) — equipo maestro del aula: **pantalla táctil de 86", sin teclado**. Nada de lo que construyas puede exigir escribir. OPS corre como usuario normal: **no puede escribir en `Program Files`**.
- **AVACOM Student** (`src/Avacom.Lms.Student`) — tabletas Android 14 y portátiles Windows 11. `src/Avacom.Lms.Core` y `src/Avacom.Lms.Ui` los comparten.
- **Instalador** (`installer/`, `installer/version.json` = **2.8.5**) — ya sabe actualizar **el producto completo** con copia previa y vuelta atrás. Lo describe `spec-driven/08-instalador.md` §5 y §6.
- **AVACOM Contenido / Biblioteca** — otro producto. Los cursos viven ahí. `backend/biblioteca/` es intocable.
- El árbol tiene **muchos archivos sin commit de otras sesiones**. No los toques, no los reviertas, no los añadas al índice. Antes de editar un archivo compartido (`backend/avacom_lms/settings.py`, `asgi.py`, `urls.py`, `backend/audit/dominio/catalogos.py`, `backend/acceso/dominio/plantillas.py`, `installer/version.json`, `installer/src/host/`) mira su `git diff` y añade sin pisar lo ajeno.
- **Hermanos que se construyen a la vez o antes**: `spec-driven/16-node-platform/00-prompt.md` (MOD-015: registro de módulos con versiones, reinicio de servicios y cola de salida) y `spec-driven/15-licenciamiento/00-prompt.md` (MOD-018: licencia; comparte la idea de clave de publicación y de manifiesto firmado). **MOD-016 (Backup) no existe** todavía. Si esas sesiones ya corrieron, **consume** sus puertos; si no, implementa los tuyos detrás de un puerto para que ellas los absorban.

# Lee antes de escribir (en este orden)

1. **El Documento Maestro**: `C:\Users\AVACOM\Downloads\AVACOM_LMS_Documento_Maestro_Consolidado_v1.0 (3) (2).html` (1,1 MB, no está en el repo). Conviértelo a texto en el scratchpad (quita `script`, `style`, `svg` y etiquetas) y léelo **por secciones**; no lo cargues entero. Ancla de la ficha: `#m-f-mod-017`. Lo que importa: **MOD-017 · Update Manager** (propósito, capacidades CAP-105…109, funciones FUN-179…187, estados, BR-013, INV-008, INV-023, permisos, eventos, escenarios TST-047, 048, 050, 061, 062); «Contrato modular» (BR-001, BR-003, BR-012, BR-013, BR-015, INV-007); «Recuperación automática del aula»; «Los tres escenarios de operación»; «Permisos» (la tabla, ESC-01, «Falla cerrada», «Reevaluación tras reinicio»); «Qué entra al respaldo y qué no»; la Parte XI «Eventos» (el sobre de doce campos); JRN-017 («Actualizar el contenido»); AC-077; NFR-022, NFR-044, NFR-049; la ficha de MOD-015 (`#m-f-mod-015`, «MOD-017 le pide reiniciar servicios dentro de una ventana controlada») y la de MOD-016 (`#m-f-mod-016`, FUN-174: «No hay sesión de clase activa»); la matriz de preparación (MOD-017: «Falta el procedimiento de reversión sin técnico en sitio»).
2. `spec-driven/01-constitucion.md` — artículos 13 y 14 (el LMS sólo guarda el expediente; el contenido del curso es de la Biblioteca).
3. `spec-driven/08-instalador.md` §2, §5 (política de datos, copia, claves) y §6 (instalar, actualizar, volver atrás); `installer/src/codigo.iss` (`RevertirActualizacion`, la carpeta `Anterior\`); `installer/src/host/Program.cs` (verbos) y `Datos.cs` (`Respaldar`, `Restaurar`); `installer/build/Ensayar-Paquete.ps1` (bloque E: una migración que falla de verdad); `installer/README.md`.
4. Los hermanos más recientes y cómo se documentan: `spec-driven/12-gradebook/`, `spec-driven/14-reporting/` (`01-diseno.md`, `02-api.md`, `03-pruebas.md`) y `spec-driven/15-licenciamiento/00-prompt.md` (sus P-03, P-12 y P-23, sobre claves y manifiesto firmado; `05-emision.md` como modelo de manual de emisor sin claves). Tu módulo se estructura, se documenta y se prueba **igual**.
5. `spec-driven/05-audit-logs/` (catálogo de acciones cerrado, cadena de huellas), `spec-driven/10-modelo-datos-implementado.md` y `spec-driven/01-acceso/04-Lineamientos-Al-Documento-Maestro.md`.
6. La **memoria del proyecto** (se carga sola): entorno, trampas de herramientas, reglas de commits y de instaladores.

# Objetivo

Construir **MOD-017 · Update Manager** (DOM-009 · Plataforma y Continuidad), tal como lo define el Maestro: *«aplica actualizaciones sin internet y sin perder lo propio. Verifica firma y compatibilidad de contratos antes de tocar nada, toma un respaldo previo, instala por módulo en lugar de todo a la vez, y revierte de forma automática si algo sale mal»*.

Su contribución más valiosa es **lo que impide**: que se instale un paquete no firmado o alterado, que se degrade a una versión vieja, que una aplicación arranque con una clase en curso, que se pierda la versión a la que volver antes de 14 días y que un módulo deje el aula con contratos incompatibles (INV-007).

## Qué entra y qué no

| Entra | Notas |
|---|---|
| CAP-109 · verificar firma e integridad antes de instalar (BR-013) | Ed25519 con `cryptography`, que ya viaja en el runtime. Manifiesto firmado (P-02). |
| CAP-106 · aplicar desde medio extraíble o unidad externa | Como el USB de MOD-018: lista de unidades, sin teclado ni ruta escrita (P-11). |
| CAP-105 · actualizar un módulo sin detener a los demás | Un paquete trae sólo lo que cambió. El aula se para **una vez**, fuera de clase. |
| CAP-107 · revertir al estado anterior (INV-008) | Automático si la verificación posterior falla; manual durante 14 días (P-09, Q-U4). |
| FUN-179 … FUN-187 (nueve funciones y nueve eventos `actualizacion.*.v1`) | Disparadores, precondiciones y permisos, tal como están en la ficha del Maestro. |
| Historial de la instalación (FUN-187) | De sólo inserción, con la marca del reloj del nodo (R-09). |
| CAP-108 · programar la ventana | Una ventana única en MVP; las recurrentes, V1 (C-2, Q-U1). |
| Pantalla **Actualizaciones** en OPS (Administración y Técnico) | Estado, paquetes, detalle, programar, aplicar, revertir e historial (P-19). |
| Canal por internet (en la ficha, MVP) | Sólo **detección** y descarga bajo petición. Aplicar nunca depende de la red (P-18). |

| No entra (déjalo preparado y dilo en el diseño) | Por qué |
|---|---|
| Validar la licencia (MOD-018) | Sólo se enlaza `PuertoLicencia`, que en MVP responde «sin restricción». |
| Crear paquetes **dentro del producto** | El Maestro lo excluye. Un emisor interno de AVACOM vive en `tools/actualizacion/`, fuera del instalador (P-03). |
| Actualizaciones sin firma | Excluidas por el Maestro. Sin excepción, tampoco en desarrollo (R-05). |
| Cursos, paquetes de contenido y versiones por linaje (MOD-004 en el Maestro) | Son de AVACOM Contenido (Biblioteca). R-12, C-6, Q-U7. |
| Respaldo completo y punto de recuperación cada 5 s (MOD-016) | No existe. Se usa `PuertoRespaldo` (P-14). |
| Actualizar los binarios de OPS y de Student | Siguen por el instalador (P-21). |
| Tocar el `Host`, el Python embebido, `installer/` o `backend.env` | Sólo los cambia el instalador completo (P-17, R-07). |

# Cómo leer el Maestro (y dónde se contradice)

La tabla reúne once puntos donde el Maestro se contradice, deja un hueco o no define algo que MOD-017 necesita. Cada fila trae una propuesta que la sesión adopta como `D-n` salvo que el repo diga otra cosa. Todo lo que no esté aquí se toma tal cual del Maestro.

| # | Dónde | Lo que dice | Propuesta |
|---|---|---|---|
| C-1 | FUN-183 frente a TST-050 y NFR-049 | FUN-183 bloquea la actualización con una sesión activa. TST-050 pide «actualizar durante una clase activa» con la clase siguiendo en la versión anterior. NFR-049 pide actualizar «sin interrumpir una clase activa» | Importar, verificar y programar sí pueden ocurrir **durante** una clase. **Aplicar** se difiere. NFR-049 se mide como «cero clases interrumpidas» con la aplicación diferida (Q-U5) |
| C-2 | CAP-108 (V1) frente a FUN-182 (MVP) | La ventana programada es V1 en la capacidad y MVP en la lista de funciones | Una ventana única en MVP. Las recurrentes, V1 (Q-U1) |
| C-3 | AC-077 frente a NFR-022, JRN-017 y el objetivo O8 | 3 minutos para el motor de evaluación; 5 minutos en general (O8: «reversión automática en 5 minutos») | 3 min para paquetes que toquen `evaluacion`; 5 min para el resto. Ambos se miden en los ensayos (Q-U2) |
| C-4 | CAP-105 | Figura como «sin red», pero depende de «descarga automática del paquete», que MOD-017 no define | La aplicación nunca necesita red. La descarga es opcional (P-18, Q-U6) |
| C-5 | Ficha de MOD-017, «Entidades que toca» | Lista EventoDeCola, Respaldo, SesionDeClase, RegistroAuditoria, Notificacion y Archivo | Son de otros módulos (INV-023). MOD-017 **sólo** llama a sus interfaces o puertos (P-14) |
| C-6 | MOD-004 y JRN-017 | MOD-004 «aplica las versiones nuevas» de contenido, y deja la «instalación física» a MOD-017 | En este repo el contenido es de AVACOM Contenido. Fuera de MOD-017 (R-12, Q-U7) |
| C-7 | Ficha de MOD-017, estado H y JRN-017 | La reversión queda disponible 14 días | El instalador borra `Anterior\` al terminar bien (`08-instalador.md` §6, paso 9). MOD-017 guarda su instantánea aparte (P-07) |
| C-8 | Catálogo de permisos | `update.package.import` y `update.schedule` (ficha J, FUN-180 y FUN-182) no aparecen en la tabla de permisos del Maestro. Sólo `update.apply` aparece: Admin «sí», Técnico «escalada» (ESC-01, 4 h). Lo mismo pasa con los `backup.*` de MOD-016 | Propuestos como extensión marcada (P-10, Q-U3) |
| C-9 | MOD-018, «Incluye»: «actualización por internet o paquete físico» | Parece solapar con MOD-017 | Se lee como renovación de la **licencia** (`.avlic`), no como paquete de software. MOD-017 no toca licencias |
| C-10 | Estado «incompatible con el ciclo congelado» (estado H) | Ninguna regla ni función lo calcula | Sólo aplica si el paquete trae cambios curriculares y hay un ciclo abierto (BR-031). Hoy no aplica en este repo |
| C-11 | Matriz de preparación | MOD-017: «Falta el procedimiento de reversión sin técnico en sitio» | La reversión automática sí. La manual sin técnico queda como pregunta (Q-U4) |

# Lo que ya existe y lo que no (verificado el 2026-10-20; **reconfirma con grep** antes de apoyarte: el árbol cambia)

| Hecho | Dónde | Por qué importa |
|---|---|---|
| **MOD-017 no existe.** No hay `backend/actualizacion/`, ni tablas `m17_*`, ni eventos `actualizacion.*` en el código (las menciones de `m15_`/`m17_` son sólo docstrings). | `backend/` | Se construye de cero. |
| **El instalador ya actualiza el producto completo**: aparta `Anterior\`, saca copia de la base (con `-wal`, `-shm` y `backend.env`), migra y, si algo falla, revierte con `RevertirActualizacion`. La política «protegidos» conserva siempre la base. | `installer/src/codigo.iss`, `08-instalador.md` §5–6 | MOD-017 **no** duplica ese mecanismo: lo complementa para paquetes parciales y reutiliza sus criterios (P-17). |
| **Sólo SYSTEM escribe en `Program Files`.** OPS corre como usuario. | `installer/src/host/`, `08-instalador.md` §2 | La aplicación la hace el `Host`, no Django ni OPS (P-06). |
| Verbos del `Host`: `iniciar`, `preparar` (con `check` y `migrate`), `salud`, `validar`, `respaldar`, `restaurar-datos`, `vaciar-datos`, `iniciar-servicio`, `detener-servicio`, etc. | `installer/src/host/Program.cs` | Hay que añadir un verbo (`aplicar-actualizacion`) o un vigilante en `Servir()`, y reutilizar `preparar`. |
| `Datos.Respaldar(registro, version)` y `Datos.Restaurar(registro)` ya existen. La copia va a `Respaldos\<versión>-<fecha>\` y se conservan cinco. | `installer/src/host/Datos.cs`, `08-instalador.md` §5.3 | El respaldo previo de MOD-017 puede reutilizarlos. |
| `installer/version.json` = **2.8.5**. Su nota fija que el contrato de red con Student sube el número cuando cambia. | `installer/version.json` | Un paquete que cambie la API sube el contrato y el número. |
| Permisos: `update.apply` = Admin «sí», Técnico «escalada». `update.package.import` y `update.schedule` **no** están en el catálogo del Maestro. Última migración de `acceso`: `0018_permisos_licencia.py`. | Maestro («Permisos»); `backend/acceso/migrations/` | Migración `acceso` con el **siguiente número libre** (hoy 0019; MOD-015 o MOD-018 pueden tomarlo antes). |
| `audit/dominio/catalogos.py` tiene `MODULOS` cerrado y ya incluye `M_LICENCIA`. Una acción desconocida falla en pruebas. | `backend/audit/dominio/catalogos.py` | Añade `M_ACTUALIZACION` y sus acciones. |
| **MOD-015 no existe** (sin `m15_evento`, sin registro de módulos). **MOD-016 no existe** (sin app de respaldo). **MOD-018 está en curso**: `backend/licenciamiento/` con migraciones 0001–0002; no hay código de licencia en OPS ni en Core. | `backend/`, `src/` | Puertos con adaptadores provisionales (P-14, P-15). |
| OPS tiene moldes: `SeguridadAulaPage.cs`, `ReportesPage.cs`, `ReportesEstadoPage.cs`; medio extraíble con `Reportes/Unidades.cs` y `VigilanteDeUnidades.cs`; escritura segura en `Reportes/EscrituraSegura.cs`. **No hay página de Actualizaciones.** | `src/Avacom.Lms.Ops/Pages/`, `…/Reportes/` | Moldes que debes imitar (R-10). |
| Ensayo del paquete: `installer/build/Ensayar-Paquete.ps1`, con el bloque E de migración fallida. `Build-Installer.ps1` compara huellas y **descarta el `.exe`** si algo cambia mientras compila. | `installer/build/` | El ensayo de MOD-017 se suma a ese bloque (R-14). |
| Emisor de referencia: `tools/licencias/` (keygen interno con `cryptography`). El build comprueba que nada de eso viaje en el paquete (`Build-Installer.ps1`, ≈ líneas 470–479). | `tools/licencias/`, `installer/build/` | El emisor de paquetes sigue ese molde y entra en la misma comprobación (P-03). |
| El LMS habla el **contrato 2** de AVACOM Contenido desde la 2.4.0 de este repo (nota de `version.json`). | `installer/version.json` | Sólo se **lee** la versión de contrato de la biblioteca para compatibilidad (R-12). |

# Modelo de amenazas y el límite honesto

| Adversario | Qué intenta |
|---|---|
| A1 · medio alterado | Cambiar un archivo del paquete en el USB o en la carpeta. |
| A2 · degradación | Instalar un paquete firmado pero **viejo**, con una vulnerabilidad ya corregida. |
| A3 · ruta maliciosa | Un paquete con `..`, rutas absolutas, enlaces simbólicos o una bomba de descompresión, para escribir fuera del backend. |
| A4 · corte a mitad | Un corte de energía, o un antivirus que bloquea un archivo durante la copia. |
| A5 · administrador local | Un técnico que edita los `.py` a mano o parchea el `Host`. |

**Lo que se promete y lo que no:**

- A1 y A3 se **impiden**: firma Ed25519 sobre el manifiesto, SHA-256 por archivo, rutas validadas y nada se extrae antes de verificar.
- A2 se **impide** con una serie monótona por módulo (P-02, P-16).
- A4 se **recupera**: checkpoints y, al arrancar, reanudación o reversión (P-07).
- A5 **no se puede impedir** a quien controla el aparato. Se **detecta** (huella de los archivos instalados, historial encadenado, aviso al administrador) y se **limita el daño**: el paquete de módulo nunca toca el `Host` ni `backend.env` (R-07).

# Reglas que no se rompen

- **R-01 · Nunca se detiene una clase.** Aplicar exige cero sesiones activas (FUN-183). Desde que el nodo acepta la orden hasta que termina, el inicio de clases responde 503 `actualizacion_en_curso` (P-08). Ninguna fase cierra una sesión.
- **R-02 · Nunca un 4xx en rutas con cola del cliente.** Las rutas de examen, las respuestas de clase y `modo-estudio/sync` no cambian por la actualización. Durante la aplicación sólo responden **503**, porque el cliente conserva su cola ante un 5xx y la descarta ante un 4xx (`Core/Services/ColaRespuestas.cs`).
- **R-03 · Un escritor por tabla** (INV-023). MOD-017 es dueño de `m17_*`. No escribe `m01_*`, `m07_*`, `m09_*` ni las tablas de MOD-016 o MOD-019: consulta o invoca sus `servicios.py` o sus puertos.
- **R-04 · Falla segura.** Si el verificador, el orquestador o el reloj fallan, el paquete se queda en `recibido` o `verificado`. **Nunca** se aplica a medias, y ningún fallo produce un 500 en una ruta de negocio.
- **R-05 · Firma siempre.** Ninguna instalación sin firma válida, tampoco en `desarrollo` o `pruebas`. La clave de pruebas vive en `backend/actualizacion/tests/` y no entra en el paquete (prueba de contenido, como la de MOD-018).
- **R-06 · Cero internet** en la verificación, la aplicación y la reversión. Internet sólo para detectar o descargar, nunca al aplicar.
- **R-07 · Un paquete de módulo nunca toca** el `Host`, el Python embebido, `installer/`, `backend.env`, las claves de datos (`AVACOM_LMS_CLAVE_*`) ni `backend/biblioteca/`.
- **R-08 · Catálogos cerrados.** Módulo y acciones de bitácora en `audit/dominio/catalogos.py`; permisos en `acceso/dominio/plantillas.py`, con una migración `acceso` idempotente y el siguiente número libre. No renumeres las migraciones ajenas.
- **R-09 · Reloj.** Las fechas de la ventana y de los 14 días salen del reloj del nodo a través de `PuertoReloj`. No crees otra copia de `RelojNodo` (lo mismo que MOD-018 R-06).
- **R-10 · OPS sin teclado.** Objetivos táctiles de **60 px o más** en la pantalla interactiva (NFR-044), confirmar **una** vez, sólo `Border`, `Label` y `Button` (un `Path` o `Ellipse` degenerado tumba los lienzos Win2D de toda la ventana), lógica pura enlazable por `Ops.Tests` y textos en español claro. Las capturas se revisan con la **regla de tercios**: tarjeta en el tercio central en X y de 1/6 a 5/6 en Y, con Grid `*,*,*` / `*,4*,*`.
- **R-11 · Línea base primero.** Antes de tocar nada, corre las suites afectadas (`acceso`, `audit`, `device_manager`), `dotnet test` de Core y Ops, y anota conteos y tiempos en `01-diseno.md`. Si la línea base no está en verde, dilo y no la arregles. Al terminar, **ninguna prueba existente cambia**.
- **R-12 · Biblioteca intocable.** No editar `backend/biblioteca/`, `FuenteDeCursos` ni `classroom_engine/dominio/curso.py`. La versión de contrato de la biblioteca **se lee** para comprobar compatibilidad y nada más.
- **R-13 · Compatibilidad de clientes.** Un paquete de módulo no cambia el contrato de red con Student y OPS salvo que lo declare. Si lo cambia, sube `installer/version.json`, lo dice en la nota y el paquete trae la versión mínima de cliente.
- **R-14 · Sin trabajo paralelo con el build.** El instalador descarta el `.exe` si `backend`, `src/`, `assets`, `installer/{src,tools,build}` o `version.json` cambian mientras compila. Antes de editar, mira si hay procesos `powershell.exe` con `Build-*` y coordina.

# Decisiones ya tomadas (`P-n`)

**A · El paquete y su verificación**

- **P-01 · Qué es un módulo en este repo.** Una app Django de `backend/` con sus tablas `m{NN}_*` y su manifiesto de módulo: versión de módulo, versión de datos, versión de contrato y rangos de eventos e interfaces que produce y consume (BR-012). El registro vive en `backend/avacom_lms/modulos.json`, provisional hasta que MOD-015 lo absorba. Una app sin entrada no es actualizable por separado, y una prueba lo comprueba.
- **P-02 · Formato `.avupd`.** Contenedor ZIP con `manifiesto.json` y `manifiesto.firma` (Ed25519 sobre los bytes exactos del manifiesto). El manifiesto lista cada archivo con su tamaño y SHA-256, las migraciones por app con su reverso declarado (BR-015), la versión de producto, los requisitos de contrato y de espacio, y la **serie** monótona por módulo. Primero se verifica la firma; después se interpreta cualquier campo. El algoritmo está fijado, sin campo `alg` negociable; el `kid` elige entre ≥ 2 claves públicas embebidas. Antes de extraer: sin rutas absolutas, `..`, letras de unidad, enlaces, duplicados ni entradas no declaradas, y topes de tamaño por archivo y total. Todo se extrae a `%ProgramData%\AVACOM\OPS Master\Actualizaciones\staging\`, nunca a `backend/`.
- **P-03 · Claves.** Par Ed25519 de **publicación**, distinto del de licencias, con su propio `kid` (el modelo es MOD-018 P-03). La privada vive fuera del repo y de todo equipo de cliente, en la máquina de emisión sin red. El emisor es `tools/actualizacion/` (molde `tools/licencias/`) y queda excluido del instalador. Prueba obligatoria: el paquete del instalador **no** contiene la clave privada, el emisor ni la clave de pruebas.
- **P-04 · Compatibilidad (BR-013, INV-007).** Antes de aplicar se comprueba: la versión de contrato de cada módulo afectado frente a la instalada, la versión de contrato con la biblioteca (R-12), la versión mínima de cliente (R-13) y el espacio libre para copia, instantánea y paquete. Si algo falla, la instalación **no inicia** y se notifica con el motivo. Ante duda, se conserva la última combinación funcional.
- **P-05 · Estados.** Función **pura** de transición con los estados del Maestro (`recibido`, `verificado`, `incompatible`, `aplicado`, `revertido`, `archivado`) y dos internos marcados como extensión: `programado` y `aplicando`. Un paquete rechazado por firma o por ruta no se guarda como paquete: queda **sólo en el historial**, con su motivo y sin escrituras en disco (TST-048). Como en MOD-018 (P-05), no se guarda un «estado actual» que pueda divergir: el historial es de sólo inserción y el estado se deriva.

**B · La aplicación**

- **P-06 · Quién aplica.** El **`Host`** (servicio SYSTEM), no Django ni OPS. Django verifica y decide, y deja una **orden** en `%ProgramData%\AVACOM\OPS Master\Actualizaciones\orden.json` (escritura atómica). El vigilante del `Host` la aplica dentro de la ventana, con el servicio del backend parado, y escribe `resultado.json`. Al arrancar, Django lo lee y registra el resultado en el historial (FUN-187). Razón: sólo SYSTEM escribe en `Program Files`, y un proceso no puede detenerse a sí mismo sin dejar el aula a medias.
- **P-07 · Secuencia con checkpoints.** (1) Comprobaciones finales: firma, compatibilidad, espacio y ausencia de sesiones. (2) Copia de la base (base, `-wal`, `-shm`) y de `backend.env` con `Datos.Respaldar`, con el servicio parado. (3) Instantánea del código de los módulos que cambian, en `Actualizaciones\versiones\<paquete>\anterior\`, **conservada 14 días** (C-7). (4) Copia del código nuevo desde el staging, verificando el SHA-256 de cada archivo al escribirlo. (5) Migraciones de cada app en orden de dependencias, cada una con su reverso (BR-015); reutiliza el paso `check`/`migrate` de `preparar`. (6) Arranque y `/health/` con los módulos reportando la versión nueva. (7) Éxito: se registra y se marca `aplicado`. Fallo en 2 a 6: **reversión automática** a la instantánea y a la copia de la base, verificada y registrada como `revertido` (INV-008). Si la propia reversión falla, no se borra nada, el aula queda con la copia de la base y se avisa (Q-U4). Se escribe un checkpoint antes de cada paso: si el `Host` muere a mitad, al volver reanuda o revierte (A4).
- **P-08 · Ventana y clases.** La orden se acepta sólo con cero sesiones abiertas. Desde que se acepta hasta que termina, el inicio de clases responde 503 `actualizacion_en_curso` (R-01). La ventana respeta un margen de 15 min antes de cualquier clase programada, si el nodo conoce el horario (Q-U9). Una clase que ya estaba abierta nunca se interrumpe: si aparece una durante la ventana, la aplicación se aplaza.
- **P-09 · Reversión.** Automática si la verificación posterior (paso 6) falla (FUN-186). Manual durante 14 días desde la aplicación, con `update.apply` y una nota escrita. Pasados 14 días, la instantánea se borra y el registro queda `archivado`.
- **P-10 · Permisos.** `update.apply` (Admin «sí», Técnico «escalada» ESC-01), tal como está en el Maestro. Como extensión marcada, pendientes de Q-U3: `update.package.import` (Técnico y Administración), `update.schedule` (Administración) y `update.read` (Administración y Técnico: estado e historial, sin datos de personas). Se siembran en `plantillas.py` con la migración `acceso` idempotente. Un profesor nunca ve esta pantalla.
- **P-11 · Medio extraíble.** OPS sólo ofrece los `.avupd` que encuentra en las unidades y carpetas conocidas (`VigilanteDeUnidades.cs`) y en `Actualizaciones\entrada\`. La API **no acepta una ruta libre**: sólo IDs de paquetes ya listados, y la ruta la resuelve el nodo.

**C · Eventos, auditoría y dependencias**

- **P-12 · Eventos.** Los nueve `actualizacion.*.v1` del Maestro (`disponible_detectada`, `paquete_importado`, `paquete_verificado`, `ventana_programada`, `bloqueada`, `modulo_aplicada`, `migracion_ejecutada`, `revertida`, `resultado_registrado`), con el sobre de doce campos. Los que añadas (`rechazado`, `reversion_fallida`) van marcados como extensión. Cola propia `m17_evento_salida`, con la misma forma que las de `m09`, `m18` y `m19`, detrás de un puerto `publicar()` que MOD-015 absorbe cuando exista `m15_evento`.
- **P-13 · Auditoría.** Módulo `actualizacion` en `MODULOS` y acciones `actualizacion.importado`, `.verificado`, `.rechazado`, `.programado`, `.aplicado`, `.revertido`, `.reversion_fallida`, `.bloqueada`, `.firma_invalida` e `.integridad_alterada`. Los asientos no llevan rutas de personas: sólo id de paquete, versiones, serie, resultado y hash. Un 503 de actualización no es un 403, así que no se asienta como `acceso.denegado`.
- **P-14 · Dependencias como puertos.** `PuertoRespaldo` (provisional: `Datos.Respaldar` a través del `Host`, hasta que MOD-016 exista), `PuertoRegistroModulos` (lee `modulos.json`), `PuertoReloj`, `PuertoLicencia` (provisional: siempre «sin restricción»; MOD-018 lo sustituye), `PuertoEventos`, `PuertoAuditoria` y `PuertoOrquestador` (escribe la orden). Cada adaptador se prueba con un doble. Ninguna escritura directa en tablas ajenas (C-5).
- **P-15 · Hermanos sin construir.** Si MOD-015 o MOD-016 no existen cuando llegues, usa los adaptadores de P-14 y **declara** en `01-diseno.md` qué garantía falta, por ejemplo el punto de recuperación de 5 s. Si ya existen, consúmelos.
- **P-16 · Serie y degradación (A2).** Un paquete con una serie menor que la instalada se rechaza, salvo que sea la reversión a la instantánea. La serie se guarda en `m17_*` y en el historial.

**D · Instalador, OPS y Student**

- **P-17 · Convivencia con el instalador completo.** El instalador completo sigue siendo la única ruta para el producto entero: `Host`, Python, OPS y Student. MOD-017 es la ruta para **módulos del backend**. El instalador no borra la instantánea de MOD-017, que vive en `Actualizaciones\` con la marca `uninsneveruninstall`, como `Respaldos`.
- **P-18 · Canal por internet.** En MVP sólo hay **detección** (`AVACOM_ACTUALIZACION_CANAL`, apagado de fábrica) y descarga bajo petición del administrador, a un temporal. Aplicar nunca depende de la red (C-4).
- **P-19 · Pantalla OPS.** Página **Actualizaciones** para Administración y Técnico, con el molde de `SeguridadAulaPage`: versión y módulos con su versión de datos y de contrato; paquetes encontrados; detalle (qué cambia, peso, espacio, compatibilidad); [Programar], [Aplicar ahora], [Revertir] (sólo dentro de 14 días) e historial. Aplicar pide **una** confirmación táctil. Core: `Core/Actualizacion/` (`ActualizacionApi`, `ActualizacionTexto` y reglas puras).
- **P-20 · Student.** Sin pantalla. Sólo un texto para la respuesta `actualizacion_en_curso`: «El aula se está actualizando; vuelve a intentarlo en unos minutos». Nunca bloquea una tableta ya registrada.
- **P-21 · Binarios de cliente.** OPS y Student siguen por el instalador. Un paquete de módulo no los trae (R-07, Q-U10).
- **P-22 · Corrupción.** Un paquete alterado se rechaza en el primer paso sin escribir un byte (TST-048). Un paquete sin firma, igual (TST-062). Un fallo inyectado al 60 % de la aplicación revierte solo (TST-061, bloqueante).

# Fases

Cada fase termina con algo que se puede probar. Entre fases hay una **puerta**: si lo medido contradice una `P-n`, dilo, decide una `D-n` y sigue; no sigas en silencio.

**Fase 0 · Reconocimiento (sin tocar el producto).** Reconfirma con grep la tabla de hechos. Convierte el Maestro a texto y lee las secciones de «Lee antes de escribir», punto 1. Corre la línea base (R-11). Mide: que el `Host` compila y que `Datos.Respaldar` deja la copia; el espacio libre de esta máquina; y, si hace falta elevación para el servicio, **dilo y pide al usuario que lo ejecute; no ejecutes nada elevado**. Entrega el borrador de `01-diseno.md` con C-1 a C-11 y tus `D-n`.

**Fase 1 · Núcleo puro** (`backend/actualizacion/dominio/` y `aplicacion/` sin Django). Formato `.avupd` y verificación (P-02), rutas seguras, límites, máquina de estados (P-05), compatibilidad (P-04), plan de aplicación con checkpoints (P-07), ventana (P-08), serie (P-16) y emisor de pruebas. *Aceptación*: dominio sin Django; **≥ 100 000 mutaciones con semilla fija, 0 aceptadas** (un byte cambiado en el manifiesto, en un archivo o en el relleno); rechazos con motivo para firma de otra clave, `kid` desconocido, versión de formato desconocida, etiqueta crítica desconocida, truncado, bytes sobrantes, rutas con `..`, absolutas o enlaces, duplicados, archivo no declarado, archivo declarado que falta, SHA distinto, bomba de descompresión y serie menor; tabla de estados × ventana × reversión completa; `test_arquitectura.py` (patrón de gradebook y reporting).

**Fase 2 · Backend integrado.** App `actualizacion` (capas, tablas `m17_*`, migraciones desde `0001`, añadida a `INSTALLED_APPS`). API, documentada en `02-api.md`: `GET /api/actualizacion/estado/`, `GET /api/actualizacion/paquetes/`, `POST /api/actualizacion/paquetes/importar/` (sólo IDs de la lista, P-11), `GET /api/actualizacion/paquetes/<id>/`, `POST …/<id>/programar/`, `POST …/<id>/aplicar/` (202 con la orden escrita), `POST …/<id>/revertir/` y `GET /api/actualizacion/historial/`. Errores `{"detail", "codigo", …}`: `firma_invalida` (422), `contrato_incompatible` (409, con la lista), `espacio_insuficiente` (409), `sesion_activa` (409), `ya_aplicado` (409) y `fuera_de_plazo_reversion` (409). Permisos y migración `acceso` (P-10), catálogo de bitácora (P-13), cola de eventos (P-12) y puertos (P-14). En `asgi.py`, un vigilante de órdenes y resultados dentro de un `try/except`, con el patrón de `cola_medios`. `/health/` gana el campo aditivo `actualizacion`, sólo con el estado. `modulos.json` tiene una entrada por app, y una prueba comprueba que no falta ninguna. *Aceptación*: suite completa del backend en verde **sin cambiar ninguna prueba existente**; pruebas nuevas de TST-047, TST-048, TST-062 y TST-050 (importar durante clase sí; aplicar durante clase, 409 `sesion_activa`, clase intacta); aplicar sin sesión da 202 y escribe la orden; aplicar con sesión da 409 y no escribe nada; con la orden aceptada, el inicio de clases da 503 `actualizacion_en_curso`; INV-023 (ninguna escritura en tablas ajenas); `makemigrations --check`.

**Fase 3 · Clientes.** `Core/Actualizacion/`, la página Actualizaciones de OPS (P-19) y el texto de Student (P-20). *Aceptación*: pruebas de Core y de Ops con **respuestas reales capturadas del backend** (patrón de `test_capturar_contrato.py`); recorrido UIA en un nodo aislado (puerto **8010**, copia de la base) con una carpeta que simule el USB, montada con `subst`; capturas con la regla de tercios; sin teclado; sin `Path`.

**Fase 4 · Aplicación real en el `Host` y el instalador.** Implementa P-06 y P-07 en `installer/src/host/` (verbo `aplicar-actualizacion` o vigilante en `Servir()`), la reversión, la instantánea de 14 días y un bloque nuevo en `Ensayar-Paquete.ps1` con un paquete que falla al 60 % (TST-061). Emisor `tools/actualizacion/` (P-03). *Aceptación*: TST-061 con reversión automática medida en minutos (≤ 3 min para `evaluacion`, ≤ 5 min en general; C-3); un corte del `Host` en cada checkpoint se reanuda o revierte al arrancar; el aula queda con la versión anterior funcionando; la instantánea sobrevive a una instalación completa (P-17). Si el servicio no se puede instalar sin elevación, **dilo** y haz los ensayos en modo consola sobre una copia en el scratchpad. **Cierre del tramo**: `installer/version.json` sube (propuesta 2.9.0, con nota) y `installer/latest` se reconstruye (≈ 35 min, en segundo plano desde PowerShell con la salida a un archivo).

**Fase 5 · Cierre y documentación.** Ensayo de reversión repetido: NFR-022 pide 30 ensayos con el 100 % de reversiones correctas; si el tiempo no alcanza, declara cuántos hiciste. Documentación en `spec-driven/17-update-manager/`: `01-diseno.md` (decisiones `D-n`, estados, qué entra y qué no, C-1 a C-11 resueltas o abiertas, riesgos, línea base), `02-api.md` (rutas, cuerpos y errores **reales capturados**), `03-pruebas.md` (qué se probó con qué resultado y **qué no se pudo comprobar**), `04-operacion.md` (reversión manual y qué hace el técnico en el aula; el hueco de Q-U4 queda explícito) y `05-emision.md` (manual del emisor **sin claves**). Añade las variables `AVACOM_ACTUALIZACION_*` a `backend/README.md`.

# Pruebas y evidencia

- **Backend**: `cd backend; .venv\Scripts\python manage.py test` (≈ 14 min; para iterar, `manage.py test actualizacion`). Dominio puro, permisos por rol, arquitectura, migraciones y la orden y el resultado en disco, con un `Host` doble.
- **Core y OPS (C#)**: `dotnet test tests/Avacom.Lms.Core.Tests` y `tests/Avacom.Lms.Ops.Tests`. Con OPS abierta, usa `-p:OutDir=<otra carpeta>`.
- **Host**: pruebas del orquestador con un sistema de archivos falso y un proceso de pruebas. El `Host` real se prueba sobre una copia en el scratchpad.
- **En vivo**: nodo aislado (puerto **8010**, copia de la base, `AVACOM_LMS_EXIGIR_SESION=1`), **sin tocar** `backend/db.sqlite3`, ni las Preferences ni la clase guardada del usuario. OPS se lanza con `AVACOM_OPS_PERFIL`, `SERVIDOR` y `RUTA` propios y se verifica con UI Automation y captura (`PrintWindow`).
- **Lo que no vas a poder probar y debes decir**: la instalación del servicio real con administrador (no puedes elevar); un antivirus que bloquee un archivo durante la copia; una memoria USB física (se simula con una carpeta y `subst`); el canal por internet real del aula (se simula con un servidor local); el panel de 86" real. Un ensayo de reversión con 30 casos es una **foto**, no un certificado.

# Trampas del entorno (de la memoria del proyecto)

- La herramienta Bash reduce `\\` a `\` y los heredocs largos fallan: escribe archivos con la herramienta Write. PowerShell bloquea con falsos «Remove-Item on system path» algunas combinaciones: parte en llamadas simples.
- Las compilaciones largas (`Build-Installer.ps1`, ≈ 35 min) van en segundo plano **desde PowerShell** con la salida a un archivo; desde Bash se colgó.
- No compiles OPS ni Student con la OPS del usuario abierta: usa `-p:OutDir=<scratchpad>`. No mates procesos del usuario.
- `backend/db.sqlite3-shm` y `-wal` están versionados de forma incorrecta, y `manage.py` los borra: restáuralos con `git checkout --`.
- UI Automation durante una navegación puede colgar la OPS de prueba: captura con `PrintWindow` cuando no necesites UIA. Una sesión por persona: iniciar sesión otra vez como la misma persona desde un script cierra la OPS de prueba.
- Los ganchos de entorno temporales van marcados `// PRUEBA-TEMPORAL` y se revierten antes de terminar.
- Antes de editar `backend/`, `src/`, `installer/` o `version.json`, mira si **otra sesión** está compilando (procesos `powershell.exe` con `Build-*`).

# Cómo trabajar y qué entregar

1. **Plan corto primero**, luego construir. Si dudas entre dos caminos, elige con estos criterios, en orden: (1) no cortar una clase; (2) tocar menos archivos ajenos; (3) que sea reversible; (4) que se pueda probar sin hardware que no tienes; (5) déjalo escrito como `D-n` en `01-diseno.md` y sigue. No preguntes lo que una decisión razonable resuelve.
2. **Docs** en `spec-driven/17-update-manager/`, con documentación **sencilla**, sin inflarla, y el mismo formato y tono que Gradebook, Search y Reporting.
3. **Cierre de cada tramo**: `manage.py test` de **todo** el backend, `dotnet test` de Core, Ops y Student, `makemigrations --check`, todo en verde, y compilación de OPS sin advertencias nuevas. Si tocaste `installer/` o el backend, reconstruye `installer/latest` (R-14), sube `installer/version.json` y avísalo. Recompila sólo lo que cambiaste.
4. **No hagas commit** salvo que se pida. Cuando lo pidan: firmados sólo por `ggalindo-avacom`, **sin coautoría de Claude**, separados en `Feature:` y `Docs:`, y con `git add` por **rutas explícitas**. Nunca `git add spec-driven/17-update-manager/` ni una carpeta entera: hay cientos de archivos ajenos sin commit.
5. **Informe final corto y franco**: qué quedó construido, las `D-n` que tomaste, **qué no se pudo comprobar**, qué defectos ajenos encontraste (**reporta, no arregles**) y qué debe confirmar el CTO (`Q-U1` a `Q-U10`).

## Preguntas para el CTO (`Q-U`)

Las respuestas por defecto ya están en los `P-n`. El CTO sólo tiene que confirmarlas o cambiarlas.

| # | Pregunta | Por defecto |
|---|---|---|
| Q-U1 | ¿La ventana programada es MVP o V1 (C-2)? | Una ventana única en MVP; recurrentes en V1 |
| Q-U2 | ¿El tiempo de reversión es 3 min para `evaluacion` y 5 min en general, o 5 min para todo (C-3)? | 3 y 5 |
| Q-U3 | ¿Qué permisos son `update.package.import` y `update.schedule`, y quién los tiene (C-8)? | Import: Técnico y Administración; schedule: Administración |
| Q-U4 | ¿Quién hace la reversión manual dentro de 14 días si no hay técnico en sitio (C-11)? | Administración con `update.apply`; el procedimiento de técnico queda pendiente |
| Q-U5 | ¿Aplicar durante clase se difiere (FUN-183) o se permite sin interrumpir (NFR-049)? | Diferido |
| Q-U6 | ¿El canal por internet en MVP sólo detecta, o también descarga (C-4)? | Detecta; descarga sólo si el administrador lo activa |
| Q-U7 | ¿Los paquetes de contenido son del LMS o de AVACOM Contenido (C-6)? | AVACOM Contenido |
| Q-U8 | ¿La clave de publicación de paquetes es la misma ceremonia que la de licencias (MOD-018 P-03) o una distinta? | Distinta, con el mismo procedimiento |
| Q-U9 | ¿Cuál es el margen antes de una clase programada para no empezar una aplicación? | 15 min |
| Q-U10 | ¿Los binarios de OPS y Student entrarán algún día en un paquete de módulo? | No en MVP |
