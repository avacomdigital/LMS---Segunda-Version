# 15 · Licenciamiento (MOD-018) · Guía interna: cómo otorgar una licencia

| Campo | Valor |
|---|---|
| Para quién | Personal de **AVACOM** que emite licencias (soporte, comercial, el CTO). No es una guía para el colegio: esa es [guia-usuario-cliente.md](guia-usuario-cliente.md) |
| Qué vas a hacer | Recibir la **solicitud** (`.avreq`) del colegio, revisarla, **firmar** una licencia (`.avlic`) con la herramienta **AVACOM Emisor de Licencias** y entregársela. Unos 10–15 minutos |
| Herramienta | `tools/licencias/` (el emisor o «keygen» interno). Sólo para AVACOM: **nunca** viaja en el instalador del colegio |
| Qué dice el sistema detrás | [requerimientos.md](requerimientos.md) §8 y el manual técnico `05-emision.md` |
| Estado | **Guía de trabajo.** Los valores comerciales (planes, días, límites) son **provisionales** hasta que el CTO conteste Q-L1 |

---

## 1 · Lo que tienes que saber antes de empezar

- Una licencia es un archivo **firmado por AVACOM**. El computador del colegio la verifica **sin internet**. Si el archivo cambia un solo carácter, deja de valer.
- La licencia queda **sellada al computador maestro del aula**: por eso necesitas la **solicitud** que ese computador genera. La solicitud no lleva datos de personas ni identificadores en claro del equipo.
- **La clave privada es lo único valioso de todo el sistema.** Quien la tiene puede emitir licencias a nombre de AVACOM. Se guarda **fuera** del repositorio, **fuera** de cualquier computador de un cliente y **cifrada** con una frase de paso.
- **Nunca se detiene una clase** por una licencia. Eso significa que un error tuyo (una fecha mal puesta) no deja a un colegio sin clase, pero sí le puede quitar funciones o darle de más: por eso hay un resumen y una confirmación antes de firmar.

## 2 · Reglas de oro

| # | Regla | Por qué |
|---|---|---|
| 1 | La clave privada (`.avkey`) **nunca** sale del equipo de emisión ni de su memoria USB. Ni por correo, ni por chat, ni en la nube, ni en una captura | Es lo que impide que cualquiera emita licencias |
| 2 | La **frase de paso** no se escribe en ningún lado ni se comparte | Sin ella la privada no abre |
| 3 | El equipo de emisión **no tiene red** mientras emites | Una clave en un equipo conectado es una clave expuesta |
| 4 | **Lee el resumen** antes de escribir la palabra de confirmación | Es la única revisión humana antes de firmar |
| 5 | Sólo se emiten licencias de tipo `produccion` y `evaluacion`. **Nunca** `desarrollo` | Las de desarrollo no se firman con la llave de producción |
| 6 | Cada emisión deja **un renglón** en el registro. No lo edites ni lo borres | Es tu comprobante y el de la conciliación mensual |
| 7 | Plan y límites salen del **contrato**, no de lo que pida el cliente por teléfono | Evita emitir de más |
| 8 | Si la solicitud no verifica, **no se emite**: pide una nueva | Una firma inválida significa un archivo alterado o dañado |

## 3 · Lo que necesitas

1. Un computador de emisión con Windows **sin conexión a internet**.
2. La carpeta de la herramienta (`AVACOM-Emisor-Licencias`) y, dentro, el archivo `Emitir-Licencia.bat`.
3. La **clave privada** (`prod-2026-1.avkey`, en su memoria USB) y su **frase de paso**.
4. La **solicitud** del colegio (`AVACOM-solicitud-…avreq`, o el texto que empieza con `AVQ1.`).
5. Los datos del **contrato**: nombre del aula, plan, vigencia, límites de equipos y usuarios, módulos incluidos.
6. Una memoria USB para entregar (o el correo del colegio: el `.avlic` **no** es secreto).

## 4 · Paso a paso: una licencia nueva

Puedes usar el **modo guiado** (haz doble clic en `Emitir-Licencia.bat`: un menú numerado te hace las mismas preguntas) o la **línea de comandos** de abajo. Los dos hacen exactamente lo mismo. Para la línea de comandos abre una consola **dentro de la carpeta de la herramienta** y escribe `avacom-licencias …` (en PowerShell, `.\avacom-licencias …`). Si las rutas llevan espacios, ponlas entre comillas; en el modo guiado puedes **arrastrar** el archivo a la ventana.

### Paso 1 · Recibe la solicitud

El colegio te entrega el archivo `.avreq` (o el texto `AVQ1.…`). Cópialo a una carpeta del equipo de emisión, por ejemplo `E:\entrada`.

### Paso 2 · Revísala

```text
avacom-licencias solicitud ver E:\entrada\AVACOM-solicitud-2026-10-20-0930.avreq
```

La herramienta **verifica la firma del computador del colegio** y te muestra:

| Qué mira | Qué debes ver | Qué hacer si no |
|---|---|---|
| **Firma** | «La firma del equipo es válida» | Si no lo es, **no sigas**: pide una solicitud nueva (el archivo se dañó o lo alteraron) |
| **Nivel de huella** | `hardware` (el equipo trae al menos dos datos de fábrica útiles, uno de ellos de la placa) | Si dice `instalación`, el equipo tiene datos de fábrica poco útiles (común en paneles OEM). **Se puede emitir**, pero avisa al colegio: es la huella más débil y no deben borrar la carpeta de licencia |
| **Piezas** | Cuántas piezas del equipo deben coincidir, por ejemplo «3 de 4» | Si dice «1 de 1», es nivel `instalación` |
| **Versión del nodo** | Una versión reciente de AVACOM OPS | Si es muy vieja, pide que actualicen antes |
| **Aula** | El nombre que el colegio escribió | Es sólo informativo: la licencia no depende de él |
| **Creada** | Una fecha reciente (últimos 30 días) | Si es muy vieja, pide una nueva |
| **Licencia vigente** | Vacío = licencia **nueva** · con un código = **renovación** | Si el colegio ya tenía licencia y aquí sale vacío, revisa el registro antes de emitir otra |

### Paso 3 · Emite

```text
avacom-licencias emitir ^
  --solicitud E:\entrada\AVACOM-solicitud-2026-10-20-0930.avreq ^
  --privada   F:\claves\prod-2026-1.avkey ^
  --aula      "Colegio San Martín" ^
  --plan      anual-aula ^
  --hasta     2027-10-31 ^
  --salida    E:\salida
```

(En una sola línea si no usas el `^` de Windows.) La herramienta:

1. Te pide la **frase de paso** (no se ve mientras escribes).
2. Verifica la solicitud y copia la huella tal cual.
3. Calcula las fechas: **empieza ayer a las 00:00 UTC** (un día de margen por si el reloj del colegio está atrasado) y **vence el 31 de octubre de 2027 a las 23:59:59 UTC**.
4. Te muestra un **resumen** como este y espera (sale tal cual, con el código de la licencia que corresponda):

```text
RESUMEN DE LA LICENCIA
  Aula ............ Colegio San Martín
  Tipo ............ producción
  Licencia ........ 9a944ae0… · serie 1 (licencia nueva)
  Vigencia ........ 2026-10-19 → 2027-10-31 (UTC)
  Gracia .......... 30 días
  Límites ......... 55 equipos · 1200 usuarios · 50 concurrentes normales · 100 en pico
  Módulos ......... todos (*)
  Huella .......... nivel hardware · 3 de 4 piezas
  Llave ........... prod-2026-1
Para firmar, escribe EMITIR y pulsa Intro:
```

   Si hay algo que debas saber (huella de nivel instalación, el reloj del colegio atrasado, una licencia de evaluación, un límite sin tope), el resumen trae debajo una sección **AVISOS**. Léela.

5. Si **lo escribes**, firma, **vuelve a leer lo firmado con el mismo lector que usará el computador del colegio** y deja un renglón en el registro. Si escribes otra cosa, no se crea ningún archivo ni ningún renglón.

```text
Licencia emitida y verificada (renglón 1 del registro).
  Licencia ........... E:\salida\colegio-san-martin-20261020-s1.avlic
  Hoja de entrega .... E:\salida\colegio-san-martin-20261020-s1.txt
  SHA-256 ............ 17cd2832…
```

Resultado en `E:\salida`:

| Archivo | Para qué |
|---|---|
| `colegio-san-martin-20261020-s1.avlic` | **La licencia.** Es lo que el colegio carga en OPS |
| `colegio-san-martin-20261020-s1.txt` | **Hoja de entrega**: el texto `AVL1.…` (por si no se puede mover el archivo), el SHA-256 y los tres pasos del colegio |

### Paso 4 · Compruébala otra vez (opcional pero recomendado)

```text
avacom-licencias verificar E:\salida\colegio-san-martin-20261020-s1.avlic --publica F:\claves\prod-2026-1.pub --solicitud E:\entrada\AVACOM-solicitud-2026-10-20-0930.avreq
```

Debe decir «La firma es válida» y «La huella corresponde a la solicitud».

### Paso 5 · Entrégala

Copia el `.avlic` y el `.txt` a la memoria USB del colegio (o envíalos por correo: **no son secretos**). Pídele al colegio que compare el SHA-256 de la hoja con el que muestra OPS al cargar el archivo.

### Paso 6 · Confirma

Pregunta qué dice la pantalla **Licencia** del colegio: debe decir **Licencia activa**, con la fecha de vencimiento y los límites que emitiste. Anota en tu sistema comercial el número de serie y la fecha.

## 5 · Casos que no son «licencia nueva»

### 5.1 · Renovar (el colegio ya tiene licencia)

El colegio genera una solicitud **desde la pantalla Licencia** (trae el código de su licencia vigente). Repite los pasos 2 a 6. La herramienta ve el código, usa la **misma licencia** con **la serie siguiente** (según el registro) y el resumen dice «Serie 2 · renovación». Las fechas parten de hoy (no de la fecha de vencimiento anterior): si renueva antes de que venza, acuerda con el cliente si se suman los días que le quedaban.

### 5.2 · Ampliar (más equipos, más usuarios, más módulos)

Es igual que renovar: **misma licencia, serie siguiente**, con los límites o módulos nuevos del contrato. No se pierde nada de lo que ya existe en el colegio.

### 5.3 · Cambio del computador maestro (JRN-020)

El colegio instala AVACOM OPS en el computador **nuevo**, restaura su respaldo y genera una solicitud **allí**. Hay dos casos:

| Caso | Qué trae el colegio | Qué haces |
|---|---|---|
| **A · El equipo viejo todavía enciende** | Un archivo `.avrel` («prueba de liberación»), que el equipo viejo genera con «Liberar este equipo» | `avacom-licencias liberacion ver <archivo.avrel>` (debe decir que es válido y de **qué licencia y serie**), y luego `emitir … --reemplaza <archivo.avrel>`: emite la licencia **definitiva** para el equipo nuevo |
| **B · El equipo viejo no enciende** | Sólo la solicitud del equipo nuevo | `emitir … --liberacion-pendiente 45`: emite una licencia **con la bandera de liberación pendiente** y **45 días** de plazo. El colegio sigue dando clase y ve el mensaje: «Puedes seguir instalando y dar clase 45 días mientras se libera». Cuando confirmes con el colegio (por contrato) que el equipo viejo ya no se usa, emite la **definitiva** (serie siguiente, sin bandera) |

El sistema no puede saber, sin internet, que una licencia está activa en otro computador: **lo sabes tú y lo escribes en el archivo**. Por eso el caso B tiene plazo.

### 5.4 · Restauración en el **mismo** computador

**No emitas nada.** El computador reconoce su licencia solo (pasa a «Licencia reactivada»). Sólo si el colegio borró la carpeta de licencia de su equipo y la huella ya no coincide hace falta una solicitud nueva (se emite la misma licencia, serie siguiente).

### 5.5 · Cambio de piezas del computador

| Qué se cambió | Efecto | Qué hacer |
|---|---|---|
| Un disco, una tarjeta de red | Ninguno (la licencia admite que cambien piezas: con 4 datos, 3 deben coincidir) | Nada |
| La placa madre | Puede dejar de coincidir: el colegio ve «Esta licencia es de otro equipo» y sigue con clase durante los días de gracia | Nueva solicitud → misma licencia, serie siguiente |
| Reinstalar Windows | Cambia una sola pieza (el identificador de Windows) | Nada, salvo que el equipo sea de nivel `instalación`: ahí hay que pedir una solicitud nueva |

### 5.6 · Licencia de evaluación

Plan `evaluacion`: tipo evaluación, un mes, gracia corta. Sólo con aprobación comercial. La herramienta te avisa «tipo evaluación» en el resumen. No la mandes a un cliente de producción por error.

## 6 · La ceremonia de claves (sólo la primera vez, y al rotar)

Se hace **una vez**, con el CTO presente, en un equipo **sin red**.

1. Genera el par: `avacom-licencias claves generar --kid prod-2026-1 --salida F:\claves`. Elige la frase de paso (mínimo 16 caracteres) y escríbela **dos veces**. Se crean `prod-2026-1.avkey` (la privada, **cifrada**) y `prod-2026-1.pub` (la pública).
2. Comprueba: `avacom-licencias claves ver --privada F:\claves\prod-2026-1.avkey`. Debe decir que abre y que firma de prueba.
3. **Respaldos**: dos copias de la privada **cifrada** en dos memorias USB distintas, guardadas en **lugares distintos**. La frase de paso se guarda aparte (sobre cerrado, caja fuerte).
4. **Publica la pública**: entrega `prod-2026-1.pub` al equipo de desarrollo para ponerla en `backend/licenciamiento/claves/` y en el instalador. Una licencia sólo se puede verificar en los equipos cuyo instalador ya trae esa pública.
5. **Rotación** (cada año o si hay sospecha): genera `prod-2027-1`, publica su pública en un instalador **antes** de emitir con ella, y sigue emitiendo con la vigente hasta que los nodos la traigan. Los nodos conservan las públicas anteriores mientras haya licencias vivas firmadas con ellas.
6. **Pérdida o robo de la privada**: avisa **de inmediato** al CTO. Se genera una llave nueva, se publica un instalador que la traiga y se **reemiten** las licencias firmadas con la anterior.

## 7 · El registro y la conciliación mensual

`avacom-licencias registro ver` muestra las emisiones (fecha, operador, aula, tipo, serie, vigencia, límites, módulos y la huella SHA-256 de cada archivo) y **comprueba que la cadena no esté alterada**. Una vez al mes:

1. Compara el registro con la facturación (cada licencia emitida debe tener su contrato).
2. Mira qué vence en los próximos 60 días y avisa a los colegios.
3. Guarda una copia del archivo `registro-emisiones.jsonl` junto a los respaldos de la clave.

## 8 · Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| «La firma de la solicitud no es válida» | El archivo se dañó o se copió como texto con un carácter de más | Pide a tu contacto que **vuelva a generar** la solicitud (no hay que reparar nada) |
| La solicitud dice **nivel instalacion** | El equipo trae datos de fábrica sin identificar (SMBIOS «To be filled by O.E.M.») | Se puede emitir. Avisa que es la huella más débil y que no borren la carpeta de licencia |
| La solicitud ya fue atendida | El colegio mandó dos veces la misma solicitud | La herramienta lo detecta por el registro. Si hace falta de nuevo, usa `--reemitir` (queda una **serie nueva**) |
| El colegio dice «aún no vigente» | El reloj del computador está muy atrasado | Ya empezaste la vigencia un día antes; pídele que corrija la fecha y la hora del equipo |
| El colegio dice «otra licencia» | Cargó una licencia con otro código distinto de la instalada | Es un cambio de licencia: antes hay que **liberar** el equipo (caso 5.3) |
| El colegio dice «actualiza AVACOM OPS» | La licencia usa algo que su versión no entiende | Pídele que actualice el instalador y vuelva a cargar |
| El colegio dice «llave desconocida» | La licencia se firmó con una llave que su instalador no trae todavía | Revisa la rotación de llaves (§6, paso 5) |
| El resumen muestra límites o fechas que no son las del contrato | Te equivocaste en un dato | Escribe cualquier cosa distinta de EMITIR: no se crea nada. Vuelve a empezar |

## 9 · Lo que **nunca** se hace

- Emitir sin leer el resumen, o con la frase de confirmación puesta por costumbre.
- Guardar la clave privada o la frase de paso en el repositorio, en el correo, en el chat o en la nube.
- Emitir una licencia **sin solicitud** (no hay forma de sellarla al computador).
- Usar la herramienta en un computador conectado a internet.
- Pasarle el emisor, la clave privada o una captura de la frase de paso a un cliente.
- Prometer al cliente que «la licencia no se puede romper»: se **encarece**, se **detecta** y la **disuasión real** es el contrato; el sistema nunca corta una clase.

## 10 · Glosario

| Palabra | Quiere decir |
|---|---|
| **Solicitud** (`.avreq`) | El archivo que genera el computador del colegio para pedir una licencia. Va firmado por ese computador |
| **Licencia** (`.avlic`) | El archivo que firma AVACOM. Dice qué puede hacer el aula y hasta cuándo |
| **Liberación** (`.avrel`) | La prueba, firmada por el computador viejo, de que ya no usará la licencia |
| **Serie** | Un número que sube con cada archivo de la misma licencia (1, 2, 3…). No se puede volver a una serie anterior |
| **Gracia** | Los días en que el colegio sigue con todo funcionando después de vencer, antes de perder funciones |
| **Huella** | La identidad del computador maestro hecha con varias piezas (por ejemplo, 3 de 4 deben coincidir) |
| **kid** | El nombre de la llave con que se firmó (`prod-2026-1`) |
| **Degradada** | Se acabó la gracia: se apagan reportes, búsqueda, importación y ajustes avanzados. Las clases siguen |
