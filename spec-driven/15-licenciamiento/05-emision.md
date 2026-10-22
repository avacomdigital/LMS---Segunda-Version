# 15 · Licenciamiento (MOD-018) · Emisión: el emisor, la ceremonia de llaves y el registro

| Campo | Valor |
|---|---|
| Estado | **Construido y probado** (2026-10-20): `tools/licencias/` con 105 pruebas en verde y la carpeta portátil armada y ensayada. **Aplica las decisiones del CTO del 2026-10-20** (gracia de 30 días corridos exactos, Q-L16; un aula de hasta 60 equipos y 1200 usuarios, Q-L1): ver §3.1. **Llave de producción `prod-2026-1` desde el 2026-10-22** (ceremonia de llaves, Q-L3; acta y desviaciones en `07-ceremonia-de-llaves.md`) |
| Qué es | El «keygen» interno de AVACOM: lee la solicitud (`.avreq`) de un colegio y firma su licencia (`.avlic`). Es una herramienta de consola; **jamás viaja en el instalador ni en el APK** |
| Quién lo usa | Personal de AVACOM que emite licencias. La guía paso a paso es [guia-usuario-interno.md](guia-usuario-interno.md) |
| Requisitos que cumple | `LIC-E-01…15` de [requerimientos.md](requerimientos.md) §8 |
| Qué **no** contiene este documento | Ninguna llave, ni la privada ni la frase de paso, ni la de desarrollo |

---

## 1 · Dónde vive y cómo se compone

```
tools/licencias/
├── avacom_licencias/
│   ├── dominio_nodo.py     carga el dominio PURO del nodo (licenciamiento.dominio): vendor/ o backend/
│   ├── llaves.py           par Ed25519; la privada cifrada con frase de paso (.avkey); la pública en texto (.pub) y en el formato del nodo (.produccion.json)
│   ├── emision.py          fechas, construir la Licencia, firmar y volver a leer lo firmado con el lector del nodo
│   ├── registro.py         el registro de emisiones, de sólo añadir y encadenado
│   ├── planes.py           los planes como dato (planes/*.json) y las reglas del CTO (planes/reglas.json)
│   ├── presentacion.py     resúmenes y hoja de entrega
│   ├── archivos.py         leer una ruta o el texto AVQ1./AVL1./AVR1.; escribir sin sobrescribir
│   ├── cli.py              los subcomandos
│   └── guiado.py           el menú numerado
├── planes/                 evaluacion · anual-aula (valores provisionales, Q-L1) y reglas.json (lo que el CTO decidió y ningún plan ni opción contradice)
├── tests/                  105 pruebas
├── iniciar.py              punto de entrada de los .bat
├── Emitir-Licencia.bat     modo guiado (doble clic)
├── avacom-licencias.bat    línea de comandos
├── Build-Emisor.ps1        arma la carpeta portátil en dist/
└── LEEME.txt
```

- **Mismo dominio que el nodo.** El emisor importa `licenciamiento.dominio` (formato, firma, huella, estado) y **no** reimplementa nada: lo que emite y lo que el nodo lee no pueden diferir. Cada licencia firmada se **vuelve a leer con el lector del nodo** y debe decir exactamente lo pedido; si no, no se entrega.
- **Nunca** importa `licenciamiento.tests.*` (ahí vive el emisor de **pruebas** con llaves de desarrollo). Una prueba lo comprueba sobre todos los archivos de la carpeta.
- **Sin red.** Ningún módulo importa nada de red; una prueba corre la emisión con los sockets cerrados.
- **Excluido del instalador por construcción:** `Build-Installer.ps1` copia `backend/` y `installer/tools/`, no el `tools/` de la raíz.

## 2 · Los comandos

| Comando | Qué hace | Opciones que importan |
|---|---|---|
| `claves generar` | Ceremonia: crea `<kid>.avkey` (privada cifrada), `<kid>.pub` y `<kid>.produccion.json` (la pública en el formato del nodo) | `--kid` (hasta 32 caracteres: lo que acepta el cargador del nodo), `--salida`. No sobrescribe nada; frase de al menos 16 caracteres, escrita dos veces |
| `claves ver` | Comprueba que la privada abre y firma | `--privada` |
| `solicitud ver` | Verifica la firma del nodo y resume la solicitud, con avisos | un `.avreq` o su texto `AVQ1.…` |
| `emitir` | Firma la licencia | `--solicitud`, `--privada`, `--aula`, `--plan`, `--hasta` o `--meses`, `--gracia`, `--equipos`, `--usuarios`, `--normal`, `--pico`, `--capacidades`, `--tipo`, `--serie`, `--licencia`, `--reemplaza`, `--liberacion-pendiente`, `--salida`, `--registro`, `--reemitir` |
| `verificar` | Comprueba una licencia con las públicas | `--publica` (repetible) o `--publicas <carpeta>`, `--solicitud` (cotejo de la huella) |
| `liberacion ver` | Verifica un `.avrel` | un `.avrel` o su texto `AVR1.…` |
| `registro ver` | Muestra las emisiones y comprueba la cadena | `--todos`, `--json`, `--registro` |
| `planes` | Lista los planes y repite las reglas del CTO que ninguno contradice | `--planes` (otra carpeta de planes) |
| (sin argumentos) | Modo guiado | |

Códigos de salida: **0** bien · **1** error (se explica qué pasó y qué hacer) · **2** cancelado por quien opera.

`--yo-confirmo` omite la confirmación escrita y existe **sólo para automatizar pruebas**; la frase de paso puede salir de la variable `AVACOM_EMISOR_FRASE` **sólo para pruebas** (la herramienta avisa cada vez que la usa). En el uso diario se escribe `EMITIR` y la frase se teclea sin eco.

## 3 · Lo que hace `emitir`, en orden

1. Lee la solicitud y **verifica la firma** del nodo contra su propio `kid`. Si no verifica, termina.
2. Abre el registro y **comprueba la cadena**. Si está alterada, termina (no se sigue escribiendo sobre un registro dudoso).
3. Si el registro ya atendió ese `nonce`, se niega salvo `--reemitir` (que sale con una **serie nueva** de la misma licencia).
4. Decide la **licencia y la serie**: `--licencia` › la `licencia_vigente` de la solicitud › la liberación (`--reemplaza`) › una licencia nueva (UUID nuevo, serie 1). Si el registro conoce la licencia, la serie es la última + 1 (y `--serie` no puede ser menor); si no la conoce, **exige `--serie`**.
5. En un **cambio de equipo** con `--reemplaza <.avrel>`: comprueba que la liberación sea de **otro** equipo, que la serie exista en el registro y que el `hash_clave_nodo` registrado coincida con la llave de quien liberó. Con `--liberacion-pendiente DIAS` emite la licencia **con la bandera**.
6. Construye la licencia: huella **tal cual** de la solicitud; `hash_clave_nodo` = SHA-256 de la llave pública del nodo; `desde` = hoy 00:00 UTC **menos un día**; `vence` = 23:59:59.999 UTC del día elegido; sólo tipos `produccion` y `evaluacion`; límites y módulos del plan o de las opciones (`*` por omisión). **Antes de firmar comprueba las reglas del CTO** (§3.1): una gracia que no sea de 30 días o más de 60 equipos / 1200 usuarios —o «sin tope» en ellos— se rechaza, venga del plan o de una opción.
7. Comprueba que el archivo de salida **no exista** (no se pisa nada), muestra el **resumen** con los avisos y pide `EMITIR` (y `SIN TOPE` antes, si algún límite de **concurrentes** no tiene tope: equipos y usuarios ya no pueden quedar sin tope).
8. **Sólo entonces** pide la frase de paso, firma, **vuelve a leer** lo firmado con el lector del nodo, añade el renglón al registro y escribe el `.avlic` y la hoja de entrega.

Si la frase es equivocada, el archivo de la llave está dañado o la verificación de lo firmado falla, **no queda ningún archivo ni ningún renglón**.

### 3.1 · Las reglas del CTO (`planes/reglas.json`)

Lo que el CTO decidió del modelo comercial es **dato**, no código: `planes/reglas.json` (cambiarlo no toca el emisor; sólo hay que volver a armar la carpeta portátil, §8).

```json
{ "version": 1, "gracia_dias": 30, "tamano_maximo": { "equipos": 60, "usuarios": 1200 } }
```

| Regla | Decisión | Dónde se aplica |
|---|---|---|
| **Gracia de 30 días corridos exactos** | Q-L16 (2026-10-20). El nodo degrada en el instante exacto en que se cumplen, sin horas de margen (histéresis 0) | `emitir` rechaza `--gracia` distinto de 30 y todo plan que traiga otra gracia **no se carga**. El plan `evaluacion` pasó de 7 a 30 días |
| **Tamaño máximo de un aula: 60 equipos y 1200 usuarios** | Q-L1 (2026-10-20), provisional: «en una misma pantalla» | `emitir` rechaza `--equipos`/`--usuarios` mayores **y «sin_tope»** (que supera cualquier máximo); `anual-aula` pasó de 55 a 60 equipos; el plan `anual-sin-tope` se **retiró** |

- Las reglas se comprueban **dos veces**: al cargar cada plan y al armar la licencia con lo que pidió la persona que opera (así ninguna opción las salta).
- Una carpeta de planes **sin** `reglas.json` no exige nada (sirve para las pruebas del mecanismo); la herramienta real siempre trae el archivo. `reglas.json` no se confunde con un plan.
- `avacom-licencias planes` imprime los planes y, debajo, las reglas vigentes.
- Los **concurrentes** (50 normales y 100 en pico en `anual-aula`) **no** están en las reglas: siguen siendo provisionales y pueden quedar «sin tope» con la segunda confirmación. Pregunta abierta al CTO: ¿deben subir a 60 para igualar el tamaño del aula?

## 4 · Los archivos que produce

| Archivo | Qué es |
|---|---|
| `<aula>-AAAAMMDD-s<serie>.avlic` | La licencia (≈ 380 bytes). Binaria, firmada con Ed25519 (formato de [requerimientos.md](requerimientos.md) §5.1) |
| `<aula>-AAAAMMDD-s<serie>.txt` | Hoja de entrega (UTF-8): aula, licencia, serie, vigencia, gracia, límites, módulos, nombre del archivo, SHA-256, **los cuatro pasos del colegio** y la variante de texto `AVL1.…` |
| `<kid>.avkey` | Llave privada **cifrada** (JSON): `formato`, `version`, `kid`, `publica`, `kdf` (scrypt N=2^15, r=8, p=1, sal), `cifrado` (AES-256-GCM, nonce, datos). El `kid` y la pública van como **dato asociado**: cambiar uno impide abrirla |
| `<kid>.pub` | Llave pública en texto: `kid`, `publica` (hex), `sha256`, `creada` |
| `<kid>.produccion.json` | La misma pública en el formato de `backend/licenciamiento/claves/produccion.json`: `{"version": 1, "claves": [{"kid", "publica", "estado": "vigente"}]}`. Es lo que se **pega o se une** a ese archivo para que el nodo reconozca la llave; junto con el `.pub`, **lo único que se entrega al equipo de desarrollo**. `verificar` también lo lee (y **nunca** toma por buena el `desarrollo.json` del nodo) |
| `registro-emisiones.jsonl` | Un renglón por emisión (§5) |

## 5 · El registro de emisiones

De **sólo añadir**, un JSON por línea. Cada renglón lleva `n`, `previo` (el hash del renglón anterior; el primero usa 64 ceros) y `hash` = SHA-256 de `previo` + el renglón canónico: **alterar, quitar o reordenar** un renglón rompe la cadena, y `registro ver` y `emitir` lo detectan.

Campos: `en` (UTC) · `accion` · `operador` (usuario de Windows) · `licencia_id` · `serie` · `clase` (`nueva`, `renovacion`, `cambio_definitiva`, `cambio_pendiente`) · `kid` · `aula` · `tipo` · `desde` · `vence` · `gracia_dias` · `limites` · `capacidades` · `liberacion_dias` · `sha256_licencia` · `sha256_solicitud` · `nonce` · `hash_clave_nodo` · `reemplaza_sha256` · `archivo`. **Nunca** lleva claves, frases de paso ni la huella del equipo (sólo el SHA-256 de los archivos).

**Límite honesto:** el registro es un archivo local. La cadena **detecta** una edición pero no impide que alguien con acceso borre el archivo entero. Por eso se guarda una copia junto a los respaldos de la llave (guía interna §7) y la conciliación mensual se hace contra la facturación.

## 6 · La seguridad de la llave: qué protege y qué no

| Protege | No protege |
|---|---|
| Que alguien que copie el `.avkey` (una memoria USB perdida) pueda firmar: necesita la frase de paso | Una frase **débil** o escrita junto al USB. Por eso se exigen 16 caracteres y se guarda **aparte** |
| Que un `.avkey` alterado se use: el cifrado autenticado lo rechaza | **Malware** en el equipo de emisión: ve la frase al teclearla y la llave al abrirse. Por eso el equipo no tiene red y sólo se usa para esto |
| Que la privada aparezca en pantalla, logs o registro: nunca se imprime | Quien tenga la llave **abierta en memoria** mientras se firma (A4). Mitigación real y futura: HSM o YubiKey (Q-L3) |
| Que se emita sin querer: resumen y palabra de confirmación | Que el operador confirme sin leer |

**Honestidad:** una llave en un archivo cifrado es una custodia razonable para un MVP, **no** el nivel de una llave en un HSM. La decisión de dónde vive la llave de producción es del CTO (Q-L3); esta herramienta la deja lista para moverla (la firma sólo necesita los 32 bytes de la semilla).

## 7 · La ceremonia de llaves (procedimiento)

Se hace **una vez**, con el CTO presente, en un equipo **sin red** y con la memoria USB que guardará la privada.

| # | Paso | Evidencia |
|---|---|---|
| 1 | Abrir una consola en la carpeta de la herramienta. Confirmar que el equipo **no tiene red** | Nota en el acta |
| 2 | `avacom-licencias claves generar --kid prod-2026-1 --salida <USB>\claves`; elegir y repetir la frase de paso (≥ 16 caracteres) | Archivos `prod-2026-1.avkey`, `prod-2026-1.pub` y `prod-2026-1.produccion.json` |
| 3 | `avacom-licencias claves ver --privada <USB>\claves\prod-2026-1.avkey`: debe decir «abre» y «firma de prueba correcta» | La **huella pública** (SHA-256) anotada en el acta |
| 4 | Dos copias de la privada **cifrada** en dos memorias distintas, en dos lugares distintos. La frase de paso va **aparte** (sobre cerrado, caja fuerte) | Acta con dónde está cada cosa (sin la frase) |
| 5 | Entregar **sólo** `prod-2026-1.pub` y `prod-2026-1.produccion.json` a desarrollo para `backend/licenciamiento/claves/produccion.json` (la entrada con `estado: "vigente"`); comparar la huella pública en el repositorio con la del acta | La huella coincide |
| 6 | Construir un instalador **con** esa pública y comprobar que activa una licencia emitida con la herramienta (`verificar` y una activación real) | `03-pruebas.md` |
| 7 | Reconstruir `Build-Emisor.ps1` si el dominio del nodo cambió | Versión de la carpeta portátil |

**Rotación.** Se genera `prod-2027-1`, su pública entra a un instalador **antes** de emitir con ella, y se sigue emitiendo con la vigente hasta que los nodos la traigan. Un nodo acepta las llaves públicas que `produccion.json` marca como `vigente` o `siguiente`; **una llave `retirada` deja de verificar** y lo firmado con ella se toma por inexistente (el colegio cae a la evaluación, y a degradada si ésta ya venció). Por eso la anterior se queda como `vigente` o `siguiente` mientras haya licencias vivas firmadas con ella (LIC-E-14, probado con dos llaves) y sólo se retira cuando el registro (`registro ver`) muestra que ya no queda ninguna.

**Pérdida o robo de la privada.** Avisar de inmediato al CTO. Se genera una llave nueva, se publica un instalador que la traiga y se **reemiten** las licencias firmadas con la anterior (con el registro se sabe cuáles). Una licencia ya emitida **no se puede revocar sin internet**: esa es la razón de ser de la revocación firmada de V1.

## 8 · La carpeta portátil

`Build-Emisor.ps1` (`-Zip` además deja el `.zip` y su SHA-256) arma `tools/licencias/dist/AVACOM-Emisor-Licencias-<versión>/`:

| Contenido | De dónde sale |
|---|---|
| `python/` | El Python embeddable de la caché de compilación del instalador (`%LOCALAPPDATA%\AVACOM\build-cache\python`), con `._pth` propio |
| `python/Lib/site-packages/` | `cryptography`, `cffi` y `pycparser` **copiados del venv del backend** (misma versión de Python: el script lo comprueba). **Sin internet y sin pip** |
| `avacom_licencias/`, `planes/` (con `reglas.json`), `iniciar.py`, los dos `.bat`, `LEEME.txt` | La herramienta |
| `vendor/licenciamiento/` | **Sólo** `__init__.py` y `dominio/*.py` del nodo: nunca las pruebas, nunca las llaves de desarrollo |
| `entrada/ salida/ datos/ claves-publicas/` | Carpetas de trabajo, vacías |

El script **falla** si el paquete contiene una llave privada, la semilla de desarrollo, un import de las pruebas del nodo, o si el Python del venv y el embeddable no son de la misma versión menor; y termina con una **prueba de humo** (la herramienta corre con su propio Python). Se probó el paquete **de punta a punta** con su Python embebido: llave, solicitud, emisión, verificación y registro (≈ 32 MB; el `.zip` ≈ 15 MB). La carpeta `dist/` no se versiona.

**Si el dominio del nodo cambia** (por ejemplo, otra versión del formato), hay que **reconstruir** la carpeta: el `vendor/` es una copia.

## 9 · Pruebas (105)

| Archivo | Qué comprueba |
|---|---|
| `test_llaves.py` (11) | Crear y abrir; la privada **no** está en claro en el archivo; frase equivocada; el `kid` y la pública atados al cifrado; archivos que no son llaves; nombres y frases inválidos; el nombre cabe en lo que acepta el nodo (32); la entrada para el nodo es el formato de `produccion.json` y se lee como la lee el nodo; la pública se comprueba |
| `test_registro.py` (6) | Cadena íntegra; alterar, quitar y reordenar rompen la cadena y se niega a seguir; renglón ilegible; consultas |
| `test_emision.py` (20) | **Las reglas del CTO se aplican a lo que se pide** (gracia distinta de 30, más de 60 equipos o 1200 usuarios y «sin tope» se rechazan; lo permitido, no); fechas (desde/vence, meses con calendario, vigencia pasada o de más de 25 años); **el margen contra un reloj atrasado** (el margen del emisor más el día de tolerancia del nodo: activa siempre hasta 48 h de atraso a cualquier hora de emisión y hasta 63 h con la hora del caso; más allá el nodo no la instala y, si el reloj se atrasó después, vuelve a la evaluación, H-08); validaciones; **400 licencias al azar que el lector del nodo lee idéntico**; un archivo distinto de lo pedido o firmado con otra llave no se entrega; **3000 mutaciones y todos los truncamientos rechazados**; liberación pendiente entendida por el estado del nodo; avisos |
| `test_cli.py` (51) | Licencia nueva de punta a punta; sin la palabra de confirmación no se crea nada; **un plan «sin tope» pide dos confirmaciones** (con una carpeta de planes sin reglas, porque las del CTO ya no dejan equipos ni usuarios sin tope); límites, módulos y gracia a mano; **las reglas del CTO no se contradicen ni con una opción** y **un plan que las contradice no se carga**; opciones inválidas; solicitud alterada, ajena o repetida; frase equivocada sin rastro; registro alterado; no se pisan archivos; **sin red**; ni la privada ni la frase quedan en ningún archivo; renovación; serie desconocida; **cambio de equipo** con `.avrel` (de otro equipo, del equipo emitido, serie conocida, alterado) y con liberación pendiente; `verificar` (otra llave, alterado, texto, huella contra la solicitud); `solicitud ver` (instalación avisa, sin hashes crudos, reloj atrasado); registro y planes; **rotación de llaves** |
| `test_guiado.py` (8) | Emitir desde el menú, rutas arrastradas con comillas, cancelar, opciones inexistentes, un error no cierra la herramienta, cambio de computador, verificar, fin de la entrada |
| `test_contenido.py` (9) | Sin imports de las pruebas del nodo, sin semilla de desarrollo, sin llaves PEM/OpenSSH, sin `.avkey`; ningún módulo toca la red; **no arrastra Django**; los planes de fábrica son válidos, emitibles y **dentro de las reglas del CTO**; **las reglas son un dato (`reglas.json`) y se comprueban**; `reglas.json` no se confunde con un plan; un plan de desarrollo o con datos malos se rechaza |

Se corren con `backend\.venv\Scripts\python.exe -m unittest discover -s tools/licencias/tests -t tools/licencias` desde la raíz del repositorio (≈ 28 s).

**La otra mitad está del lado del nodo**: `backend/licenciamiento/tests/test_emisor_real.py` (13 pruebas, ≈ 13 s con `manage.py test licenciamiento.tests.test_emisor_real`) hace que **esta herramienta firme** y que **el nodo real** —por su API, con su middleware, su historial y su estado— active, renueve y traslade lo que ella emitió, con el reloj y el hardware de «este equipo» bajo control de la prueba: activación de punta a punta, la copia que el nodo devuelve (los mismos bytes), llave desconocida, plan de evaluación (con sus 30 días de gracia), plan de producción (60 equipos y 1200 usuarios), límites y módulos a mano (y el 402 de la búsqueda), renovación, el técnico que **no** renueva, traslado con `--reemplaza`, liberación pendiente, traslado con la base restaurada (D-10) y relojes atrasados de 30, 45 y 72 horas. Se salta sola si `tools/licencias` no está en el árbol o si falta `cryptography`; la llave de la prueba nace en una carpeta temporal y muere con ella (nunca usa una de desarrollo ni una de producción) y nada se escribe fuera de carpetas temporales.

## 10 · Lo que no se pudo comprobar

- **Una ceremonia con el procedimiento de §7 al pie de la letra**: la llave de producción `prod-2026-1` existe desde el 2026-10-22, pero nació en el equipo de desarrollo **con red** y por una sesión de Claude Code, no en un equipo sin red con el CTO presente (las desviaciones y lo que falta —dos copias en memorias distintas, el sobre con la frase— están en `07-ceremonia-de-llaves.md`). Las pruebas automáticas siguen usando llaves generadas por ellas mismas.
- **Un equipo de emisión realmente sin red**: se probó que la herramienta **no abre sockets**, no que el equipo esté desconectado.
- **Un cliente real que active con un instalador real.** Hasta que la otra sesión termine las fases 2 y 3, la activación se probó con el **lector del nodo** (`licencia.leer`) y su función de estado, no con OPS; ver `03-pruebas.md` para la prueba integrada.
- **Una memoria USB física** para el `.avkey` (se usó una carpeta).
- **Otros sistemas operativos:** sólo Windows (los `.bat`); el código Python es portable, sin probar.
- **Un HSM o una YubiKey:** fuera de alcance (Q-L3).

## 11 · Preguntas para el CTO (de la emisión)

| Pregunta | Qué se hizo mientras tanto |
|---|---|
| **Q-L3** ¿Dónde vive la privada de producción, quién emite, cada cuánto se rota, cómo se atiende una liberación? | **Ceremonia hecha el 2026-10-22** (`07-ceremonia-de-llaves.md`): `prod-2026-1` en un archivo cifrado con frase de paso fuera del repositorio; rotación por `kid`; liberaciones con `.avrel` o `--liberacion-pendiente`. La custodia definitiva (HSM, YubiKey, equipo sin red) sigue siendo del CTO |
| **Q-L1** Planes, días y límites | **Decidido por el CTO (2026-10-20), provisional:** un aula tiene como máximo **60 equipos y 1200 usuarios** «en una misma pantalla» (`planes/reglas.json`). Dos planes en `planes/*.json` (`anual-aula` con 60 y 1200, `evaluacion`); el plan `anual-sin-tope` se retiró. Cambiar un plan o una regla no toca código. Abierto: los concurrentes (50 y 100) no se tocaron |
| **Q-L16** Días de gracia | **Decidido por el CTO (2026-10-20): 30 días corridos exactos** (`gracia_dias` en `planes/reglas.json`): el emisor no emite otra gracia y el nodo degrada en el instante exacto, sin histéresis |
| ¿Dos personas para emitir en producción (cuatro ojos)? | Una sola persona con la privada y su frase; el registro queda para la conciliación. Se puede exigir una segunda confirmación (un segundo operador) si el CTO lo pide |
| ¿Se manda la **hoja de entrega** por correo? | Sí: no es secreta; sólo lleva el SHA-256 y el texto del propio archivo |
| ¿Quién guarda el registro y cada cuánto se respalda? | Propuesta: junto a los respaldos de la llave, y copia mensual tras la conciliación |
