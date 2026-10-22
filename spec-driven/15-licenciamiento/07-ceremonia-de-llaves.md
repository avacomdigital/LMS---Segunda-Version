# 15 · Licenciamiento (MOD-018) · Acta de la ceremonia de llaves (Q-L3)

| Campo | Valor |
|---|---|
| Estado | **Hecha el 2026-10-22, 14:51:58 UTC** (09:51 hora del equipo). La llave vigente es **`prod-2026-1`**; su pública viaja en `backend/licenciamiento/claves/produccion.json` desde el instalador **2.14.0**. Decisión D-22 de `01-diseno.md` |
| Qué es | El registro de la primera ceremonia (`05-emision.md` §7): qué se creó, dónde quedó cada cosa, cómo se comprobó, en qué se apartó del procedimiento y lo que le queda al CTO. **Sin claves ni frases**: aquí sólo hay públicas y huellas |
| Quién | A petición del CTO (Gabriel Galindo), ejecutada por una sesión de Claude Code en el equipo de desarrollo (cuenta de Windows `AVACOM`) |

## 1 · Lo que se creó

| Pieza | Valor |
|---|---|
| Nombre de la llave (`kid`) | `prod-2026-1` (cabe en los 32 caracteres que acepta el cargador del nodo) |
| Algoritmo | Ed25519 (el mismo de todo el módulo: `licenciamiento/dominio/firma.py`) |
| **Pública** (hex) | `78a53652fd857d974ca3c2bd40a2cbc09dcc972809fceebe833ec0fba269f463` |
| **Huella pública** (SHA-256 de la pública) | `e255ca3a451b17817b8ca9163f42872e98f31b77657e2138fcb1ab67e2d06435` |
| Creada | `2026-10-22T14:51:58Z` |
| Comprobación (`claves ver`) | «Llave prod-2026-1: abre con la frase de paso» · «Firma de prueba: correcta» · la misma huella |

La huella del repositorio (`produccion.json`) y la de este acta **coinciden** (paso 5 de §7): es la misma pública, copiada del archivo `prod-2026-1.produccion.json` que generó el emisor, sin editar.

## 2 · Dónde quedó cada cosa (fuera del repositorio)

| Qué | Dónde | Quién la abre |
|---|---|---|
| **Privada cifrada** `prod-2026-1.avkey` | `C:\Users\AVACOM\AVACOM-Llaves\claves\` (perfil de la cuenta `AVACOM`, **no** es una carpeta sincronizada con OneDrive ni está bajo `ProgramData`) | Quien tenga el archivo **y** la frase de paso |
| Pública `prod-2026-1.pub` y `prod-2026-1.produccion.json` | La misma carpeta | No son secretas |
| **Frase de paso** | `C:\Users\AVACOM\AVACOM-Llaves\frase\prod-2026-1.frase.dpapi`: la frase **protegida con DPAPI** (`ConvertFrom-SecureString`), que sólo descifra la cuenta de Windows `AVACOM` en **este** equipo; no está en claro en ningún archivo del disco. Se comprobó que la copia DPAPI se vuelve a abrir y da la misma frase | Sólo `AVACOM` en este equipo |
| La frase en claro | Se mostró **una vez** al CTO en el informe de la sesión que hizo la ceremonia, para que la pase al sobre cerrado o al gestor de contraseñas | El CTO |
| En el repositorio | **Sólo** la entrada pública en `backend/licenciamiento/claves/produccion.json` (`estado: vigente`). `git status` no muestra ningún `.avkey`; la prueba de contenido del instalador y la del emisor siguen rechazando llaves privadas y `PRIVATE KEY` | — |

Para **emitir** con ella (guía interna §3): `avacom-licencias emitir --solicitud <.avreq> --privada C:\Users\AVACOM\AVACOM-Llaves\claves\prod-2026-1.avkey --plan anual-aula …` y escribir la frase cuando la pida. Para recuperar la frase desde la copia DPAPI (sólo con la cuenta `AVACOM`, en este equipo):

```powershell
$s = Get-Content 'C:\Users\AVACOM\AVACOM-Llaves\frase\prod-2026-1.frase.dpapi' | ConvertTo-SecureString
[Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
```

## 3 · Cómo se comprobó que la llave sirve (paso 6 de §7)

| Comprobación | Resultado |
|---|---|
| `claves ver` abre la privada con la frase y firma de prueba | Correcta (§1) |
| Nodo: `licenciamiento.tests.test_entorno_produccion` (la de desarrollo **no** se carga en producción; en producción se carga **sólo** `prod-2026-1`, con la pública de este acta) y `test_emisor_real` | 19 de 19. La prueba de las llaves se actualizó: antes afirmaba que en producción no había ninguna |
| Nodo: la suite de `licenciamiento` entera | 303 (6 omitidas), con el único fallo que era esa afirmación ya corregida |
| Emisor: `tools/licencias/tests` | 105 de 105 (incluida la regla de coherencia de D-21: `concurrentes_pico ≥ equipos` en los planes de fábrica) |
| **Backend empaquetado + llave real** (`scratchpad/llave_real.py`, el mismo arnés de `licencia_paquete.py`: copia de `dist\staging` en una carpeta temporal con `%ProgramData%` redirigido, como nodo de producción) | Ver §3.1 |

### 3.1 · El nodo empaquetado activa lo que firma `prod-2026-1`

Se rellena con el resultado de la corrida (abajo, «Resultados»). Lo que comprueba, en orden: el paquete trae `prod-2026-1` como vigente y **no** trae la llave de desarrollo ni las pruebas; arranca en producción, modo «firmada», sin licencia; escribe su solicitud con la huella de este equipo; una licencia firmada con la llave de **desarrollo** se rechaza (`400 kid_desconocido`); el emisor de `tools/licencias` firma con la privada cifrada real (plan `anual-aula`, hasta 2027-10-31); esa licencia **se activa** (`200 activa`, 60 equipos, 1200 usuarios, 50/100 concurrentes); tras reiniciar el nodo sigue activa; y el `%ProgramData%` real no se tocó.

## 4 · En qué se apartó del procedimiento de `05-emision.md` §7 (honestidad)

| Paso del procedimiento | Lo que se hizo | Qué significa |
|---|---|---|
| 1 · Equipo **sin red**, con el CTO presente | Se hizo en el **equipo de desarrollo, con red**, por una sesión de Claude Code a petición del CTO | La privada existió **en claro en la memoria** de ese proceso mientras se generaba y se comprobaba (A4 de §6); no se imprimió ni se escribió en claro. Si el CTO quiere una llave que **nunca** haya tocado un equipo con red, la salida es **rotar** (§6): generar `prod-2026-2` en un equipo sin red, publicarla como `siguiente` en un instalador, emitir con ella cuando los nodos la traigan y retirar `prod-2026-1` cuando el registro diga que no quedan licencias vivas firmadas con ella. Nada de eso toca código |
| 2 · La frase se **teclea** dos veces | La sesión no tiene teclado interactivo: la frase se generó al azar (seis grupos de cinco caracteres, 35 en total, letras y dígitos) y se pasó al emisor por la variable `AVACOM_EMISOR_FRASE` (la herramienta avisa que es «sólo para pruebas») en un proceso hijo que murió al terminar | La frase no quedó en el historial de ninguna consola ni en un archivo en claro del disco; sí en la copia DPAPI (§2) y en el informe de la sesión, una vez |
| 4 · Dos copias en **dos memorias USB** en lugares distintos; la frase en sobre cerrado | **No se hizo** (no hay memorias en la sesión) | **Pendiente del CTO**: copiar `prod-2026-1.avkey` a dos memorias y guardar la frase aparte; después, borrar la carpeta `AVACOM-Llaves` de este equipo (o dejarla como copia de trabajo del emisor, a su criterio) |
| 5 · Comparar la huella del repositorio con la del acta | Hecho (§1) | Coinciden |
| 6 · Instalador **con** la pública que activa una licencia emitida | Instalador 2.14.0 compilado con `-ExigirLlaveDeProduccion`; la activación con la llave real está en §3.1 | — |
| 7 · Reconstruir `Build-Emisor.ps1` si el dominio cambió | El dominio del nodo **no** cambió; el emisor portátil `AVACOM-Emisor-Licencias-1.0.0` sigue valiendo (firma con cualquier `.avkey` que se le dé) | — |

## 5 · Lo que le queda al CTO

1. **Custodia**: dos copias de `prod-2026-1.avkey` en memorias distintas y lugares distintos; la frase en sobre cerrado o gestor de contraseñas (el informe de la sesión la dio una vez). Decidir si la copia DPAPI de este equipo se queda (cómoda para emitir desde aquí) o se borra.
2. **Decidir la custodia definitiva** (Q-L3, sigue siendo suya): archivo cifrado como ahora, YubiKey, HSM o equipo sin red. Y si quiere una llave nacida sin red: rotar (§4, fila 1).
3. **Registro de emisiones**: `avacom-licencias registro ver` cada mes y copia del `registro-emisiones.jsonl` junto a las copias de la llave (guía interna §7).
4. **La llave de publicación de paquetes `.avupd` (Update Manager, MOD-017) sigue sin ceremonia**: `backend/actualizacion/claves/produccion.json` está vacío y un nodo instalado rechaza todo paquete (`kid_desconocido`). Es otra llave (Q-U8), con su propio emisor en `tools/actualizacion`; no se tocó en esta sesión.

## 6 · Resultados

| Comprobación | Resultado |
|---|---|
| §3.1 · el nodo empaquetado activa lo que firma `prod-2026-1` (`llave_real.py`, puerto 8019, carpeta temporal) | **16 de 16** |
| Pruebas del nodo (`licenciamiento`) y del emisor | 303 (6 omitidas) · 105 |
| Recorrido de la pantalla Licencia por UI Automation con la OPS recompilada (U-2/U-3/U-4) | 58 de 58 |
| Instalador 2.14.0 con `-ExigirLlaveDeProduccion` | Construido (abajo); contra su `dist\staging` final: `llave_real.py` **16 de 16** otra vez y `licencia_paquete.py` **23 de 23** |

**Instalador 2.14.0** (2026-10-22 11:09, `installer/latest/AVACOM-OPS-Master-Setup-2.14.0.exe`, 106,2 MB): construido con `Build-Installer.ps1 -ExigirLlaveDeProduccion -VersionAnterior dist\anterior-2.10.0`; SHA-256 `A8DCF16754704111D8A689E447631EE2EFD812F348C990D5C4F54D23C3C31878`; revisión `4ae9e836` con 22 archivos sin confirmar (`arbol_limpio: false`: para un colegio, commitear y reconstruir). El manifiesto dice `llaves publicas de produccion: 1` y `licencias_activables: true`; la suite completa del backend dentro del build dio **2512** pruebas en verde (1054 s) y el ensayo del paquete (A–F, incluida la actualización desde la 2.10.0 con datos) «todo correcto». Contra ese `dist\staging` se repitieron `llave_real.py` y `licencia_paquete.py` (resultados en §3.1 y en `06-verificacion-independiente.md` §8).
