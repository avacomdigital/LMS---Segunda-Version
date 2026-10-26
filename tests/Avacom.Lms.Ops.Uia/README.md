# Recorrido de interfaz del acceso de OPS (RF-31)

Prueba de punta a punta de las pantallas de acceso de AVACOM OPS Master contra un nodo **aislado**, manejando la ventana por UI Automation
(sin ratón ni teclado) y capturándola con `PrintWindow`.

| Archivo | Para qué |
|---|---|
| `recorrido_acceso.py` | El recorrido completo: levanta el nodo, abre OPS, recorre las pantallas, comprueba y captura |
| `ui-ops.ps1` | Lista controles, invoca botones por nombre (**una sola vez**), escribe en campos, marca un PIN en el teclado propio, espera un texto, cuenta elementos, mira si hay un control, hace un doble toque y captura el área de contenido |
| `tercios.ps1` | Dibuja la cuadrícula de tercios sobre una captura (así se juzga la composición de las pantallas de tarjeta) |
| `recorrido_licencia.py` | La pantalla **Licencia** (MOD-018) de punta a punta: ver más abajo |
| `licencia_en_vivo.py` | Las rutas del backend con la licencia en cada estado y el cupo, por HTTP, sin ventanas: ver más abajo |
| `licencia_paquete.py` | El backend empaquetado del instalador y el emisor portátil trabajando juntos, como producción: ver más abajo |
| `recorrido_fecha.py` | La **fecha adelantada** (Q-L13) de punta a punta, con el reloj de la licencia movible: ver más abajo |
| `recorrido_dispositivos.py` | La pantalla **Dispositivos** con la identidad por clave (MOD-018, Fase 5): tres tabletas con garantía declarada, con clave propia y verificada por hardware, y la línea «Identidad del equipo: …» de cada una; ≈ 2 minutos: `backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_dispositivos.py --ops <Avacom.Lms.Ops.exe> --salida <carpeta> [--puerto 8021]` |
| `estabilidad_ops.py` | La **estabilidad** de OPS bajo la UI Automation (Bugfix 03): la regresión del «Menú principal» activado dos veces (`doble`), ir y volver de Licencia con contadores por vuelta (`vueltas`) y la carga que reprodujo la caída de `Microsoft.UI.Xaml.dll` (`estres`): ver más abajo |
| `ui-carga.ps1` | Los clientes de UI Automation de esa carga: uno que invoca ir y volver de Licencia y otros que sólo leen el árbol |

## Cómo se corre

```powershell
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -p:OutDir=C:\temp\ops-uia\
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_acceso.py --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe [--puerto 8011] [--salida <carpeta>]
```

Tarda unos 6 minutos. Sale con 0 si todo se cumplió y lista lo que falló si no. Las capturas (`NN-nombre.png` y `NN-nombre-tercios.png`) quedan en
`salida/` (ignorada por git) o en la carpeta indicada.

## Qué recorre

1. **Primer arranque** con el nodo sin instalar: se abre solo; país, aula (el código sale del nombre), administrador; PIN `123456` rechazado por trivial
   (AC-A02); PIN marcado dos veces; **hoja de acceso** con la contraseña inicial y el PIN; «Ya la entregué» (AC-A01).
2. **Administración**: documento + contraseña de la hoja → el nodo pide el **PIN maestro** → «Elige tu contraseña» → tablero.
3. **Seguridad del aula**: estado real del PIN y **cambio del PIN maestro** (dos veces en el teclado).
4. Por la API, como lo haría la administración: un grupo, un alumno de padrón (PIN pendiente), una tableta, un alumno que se registró solo y un visitante.
5. **Crear mi usuario** con un PIN equivocado antes («Te quedan 4 intentos») y luego el bueno: entra directo (AC-A08).
6. **Grupos**: «sin confirmar» y «PIN pendiente»; Confirmar y Nuevo PIN (sin ningún número a la vista).
7. **Olvidé mi contraseña** → «Cerramos tus sesiones abiertas…» → entra con la nueva (AC-A09).
8. **Vencimiento**: a 12 días la banda del tablero lo dice con los días (AC-A05); vencido, «Crear mi usuario» explica qué pasó (AC-A04), la
   administración entra sin PIN y los profesores siguen entrando (RN-09). El paso del tiempo se simula moviendo `vence_en` en la base temporal.
9. **Segundo arranque**: la hoja confirmada ya no aparece (AC-A03); el **monitor** lista al visitante y lo vincula a un alumno (RN-44).

## Cuidados (el equipo lo comparte quien trabaja en él)

- **El nodo es aislado**: base temporal propia, `127.0.0.1:8010` (o `--puerto`), sesión obligatoria. Nunca el nodo del aula (`:8000`).
- **OPS corre con un perfil de pruebas** (`AVACOM_OPS_PERFIL=uia-<hora>`, `AVACOM_OPS_SERVIDOR`): sus preferencias y su almacén cifrado van en un
  contenedor aparte y la dirección del servidor sale de la variable, así que la OPS de quien trabaja en el equipo no cambia. `AVACOM_OPS_RUTA` (sólo con
  el perfil) lleva una vez el tablero a otra pantalla, porque las teselas hexagonales no se pueden tocar por UI Automation.
- **Contraseñas**: el campo enmascarado de MAUI en Windows no acepta el `ValuePattern` de UI Automation (el texto se ve, pero la contraseña queda
  vacía). Con el perfil, `AVACOM_OPS_CLAVES_VISIBLES=1` deja esos campos sin máscara; el enmascarado en sí no lo prueba este recorrido.
- **Candado de pantalla**: antes de abrir ventanas toma `%LOCALAPPDATA%\Temp\avacom-gui.lock` (lo usan también las pruebas de Student) y lo suelta al
  terminar. La ventana de prueba toma el foco mientras dura.
- Si una OPS del usuario está abierta, compila con `-p:OutDir=` a otra carpeta (la suya bloquea `bin\`); el guion sólo cierra las instancias que abre.
- UI Automation no ve lo que queda debajo de una WebView; en estas pantallas no hay ninguna.

## Estabilidad de OPS bajo UI Automation (Bugfix 03)

Dos fallas que parecían una («OPS no sobrevive a la UI Automation») y no lo eran; el detalle, con la pila y los números, está en `spec-driven/qa/bugfix/bugfix-03-estabilidad-ops-uia.md`.

```powershell
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py doble   --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\estab [--puerto 8018] [--repeticiones 3]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py vueltas --ops ... --salida ... [--vueltas 60]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py estres  --ops ... --salida ... [--vueltas 600 --lectores 2 --asentar 0 --completo]
```

| Subcomando | Qué comprueba | Cuánto tarda |
|---|---|---|
| `doble` | **La regresión.** Desde Licencia, dos «Menú principal» seguidos (`ui-ops.ps1 doble`) y dos toques seguidos en «Licencia» del menú: OPS debe quedar siempre en el menú, con una sola pantalla de Licencia. Con una OPS anterior al arreglo falla en la primera repetición con «quedó en acceso» | ≈ 1 min |
| `vueltas` | Ir y volver de Licencia con el patrón endurecido; por vuelta, memoria privada, manejadores, GDI/USER, hilos de OPS y elementos del árbol de UI Automation del menú y de Licencia (`vueltas.jsonl`). Falla si OPS se cae, vuelve al acceso o GDI, USER, los manejadores o el árbol de UI Automation crecen sin parar. Imprime la pendiente de la memoria (con clientes de UI Automation de larga vida sube sola; sin ellos llega a una meseta) | ≈ 4 s por vuelta |
| `estres` | La carga que tumbó a OPS: un cliente que invoca ir y volver sin pausas + N lectores que recorren el árbol sin parar. Sale con 1 si OPS se cae y dice el código de salida, el «Application Error» del Visor de eventos y las líneas de `fallos-ops.log` de ese pid; con 3 si alguien cerró la ventana (código de salida 0: no es una caída). Es la prueba más pesada y la ventana se ve lenta mientras corre: mejor con el equipo libre. **Una caída por cada ≈ 200–600 vueltas es lo normal con esta carga**: el resultado de un solo intento no prueba nada; sirve para comparar `--asentar` (pausa tras cada toque), `--lectores` y `--completo` con miles de vueltas | ≈ 1,3 s por vuelta |

**Reglas del arnés** (las que dejó este trabajo; cumplirlas en cualquier guion nuevo):

- **Un toque se hace UNA vez.** `ui-ops.ps1` sale con **4** («invocación dudosa») si `Invoke()` lanza: el toque pudo llegar igual y repetirlo activaba dos veces el mismo botón. Buscar el control otra vez mientras no aparece sí es seguro (todavía no se tocó nada). Quien llama confirma por el efecto (la pantalla que debe aparecer) antes de volver a tocar; `rl.toque` lo hace y anota el toque en `ops.dudosas`.
- **Se toca por `AutomationId`, no por nombre**, cuando el nombre se repite: «Menú principal» es también el botón decorativo del dock del menú, sin acción; el de Licencia es `licencia-volver`. `rl.volver_al_menu` y `rl.donde_estoy` (menú, licencia, acceso u otra) existen para eso.
- **Lecturas baratas.** Cada elemento se lee con una `CacheRequest` (una llamada entre procesos, no cuatro) y la pregunta de «¿dónde estoy?» es un `FindFirst` por `AutomationId` (`ui-ops.ps1 existe`), no un recorrido de todo el árbol cada 400 ms. Cada llamada de UI Automation la atiende el hilo de interfaz de OPS.
- **Sin clientes de larga vida ni lectores en paralelo** fuera de `estres`: cada elemento que un cliente mantiene referenciado mantiene vivo su proveedor en OPS (≈ 0,6 MB por vuelta).
- **Mirar cómo muere OPS.** Visor de eventos → Application, filtrando por `ProviderName` (con `Level=2` y `-First` se pierde entre eventos de otros programas); «Application Error» 1000 trae el módulo y el desplazamiento. `estabilidad_ops.py` los imprime.

## Licencia (MOD-018)

Tres guiones que comprueban la licencia **desde fuera**, contra un nodo aislado (puerto propio, base y carpeta de estado temporales, sesión obligatoria): los dos primeros con `AVACOM_LICENCIA_MODO=firmada`; el tercero con el
backend **empaquetado** del instalador, que se clasifica solo como producción. Sólo corren en un árbol de desarrollo: las licencias se firman con las llaves de desarrollo de `backend/licenciamiento/tests/emisor.py`, como lo
haría AVACOM con la solicitud que OPS guarda (el tercero las usa únicamente para comprobar que el paquete **no** las acepta).

| Guion | Qué comprueba | Cuánto tarda |
|---|---|---|
| `recorrido_licencia.py --ops <exe> --salida <carpeta>` | **La pantalla Licencia por UIA, sin teclado y con la regla de tercios en cada captura**: evaluación y su aviso desde el primer día · activar en los tres pasos con una licencia firmada a partir de la solicitud (una memoria USB simulada con `subst`) · copia de custodia (tres archivos, hoja sin documentos ni nombres) · renovar · «Vencida · en gracia» · «Funciones en pausa» y el aviso del menú · el soporte técnico **no renueva** · la administración renueva · liberar y volver a activar · el profesor no ve botón ni aviso · con la licencia en pausa, Reportes y Buscar lo dicen y Evaluaciones, Calificaciones y Clase de hoy abren sin aviso | ≈ 12 min |
| `licencia_en_vivo.py rutas` | **Todas las rutas del backend** (el inventario sale del resolvedor de Django en el momento) con la licencia en evaluación, activa, en gracia y degradada: la licenciable apagada responde 402 `no_disponible_por_licencia`, ninguna intocable ni de núcleo lo responde y todas responden lo mismo que con la licencia activa. Imprime los 5xx para clasificarlos a mano | ≈ 5 min |
| `licencia_en_vivo.py cupo` | Con 2 equipos y 6 usuarios: la tercera tableta recibe 402 `cupo_agotado`, las registradas y el equipo maestro siguen, la clase y el visitante entran siempre, el séptimo usuario recibe 402 y el estado avisa del cupo al ciclo siguiente del programador | ≈ 1 min |
| `licencia_paquete.py` | **Lo que se entrega**: copia el backend empaquetado (`dist\staging`, con su Python embebido y Daphne) y el emisor portátil (`tools\licencias\dist`) a una carpeta temporal con `%ProgramData%` redirigido. Como se entrega (`produccion.json` vacío): modo «firmada», entorno «produccion», «sin licencia» con 30 días, solicitud con la huella de este equipo, y una licencia firmada con la llave de desarrollo **se rechaza** (`kid_desconocido`), igual que una de una llave que el nodo no conoce. Tras la «ceremonia» (la pública del emisor en el `produccion.json` de la copia): la de desarrollo sigue rechazada, la del emisor portátil se activa y queda «activa» con sus cuatro módulos, y tras reiniciar el proceso del nodo sigue activa | ≈ 1 min |

```powershell
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\recorrido_licencia.py --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\capturas-licencia [--puerto 8013] [--sin-modulos]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_en_vivo.py todo [--puerto 8014]
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\licencia_paquete.py [--puerto 8016] [--staging <dist\staging>] [--emisor <carpeta del emisor portátil>]
```

`licencia_paquete.py` necesita el instalador preparado (`installer\build\Build-Installer.ps1` deja `dist\staging`) y el emisor compilado (`tools\licencias\Build-Emisor.ps1`); si falta alguno lo dice y sale con 2. Corre al compilar cada versión: es la prueba de que el
instalador que se entrega, el emisor y la llave pública que se incruste después de la ceremonia **funcionan juntos**.

### La fecha adelantada (Q-L13)

`recorrido_fecha.py --ops <exe> --salida <carpeta> [--puerto 8017]` comprueba lo que decidió el CTO el 2026-10-20: **una fecha adelantada no se acepta, no se guarda y no degrada; avisa con un error hasta que la fecha concuerde**
(≈ 6 min, con las ventanas en primer plano y el candado de pantalla; 37 comprobaciones). No cambia la fecha de Windows (exigiría administrador): el nodo aislado arranca con un `sitecustomize.py` **de la prueba** (en una carpeta temporal, por
`PYTHONPATH`) que lee un archivo de desfase y se lo suma a `time.time()` **sólo** para quien llama desde el módulo `licenciamiento` (mirando tres marcos hacia arriba: su reloj es el de la evaluación, `RelojNodo`); las sesiones, la
bitácora y el resto del nodo siguen con la hora real. Así «alguien adelantó la fecha 40 días» pasa **dentro del proceso en marcha**, que es lo único que el nodo trata como salto.

Recorre: licencia activa sin error · fecha adelantada 40 días → el nodo la detecta en su siguiente ciclo, **no la acepta** (la hora del aula no se mueve), no degrada ni apaga ningún módulo y avisa con los 40 días y las dos fechas,
primero · la pantalla Licencia y el menú principal lo dicen como un error, con «Confirmar la fecha de hoy» y «Ver la licencia» · la hoja habla de la fecha del equipo y de corregirla en Windows · al **corregir** la fecha el error se
quita solo · de nuevo adelantada: la administración **confirma** y sólo entonces el aula guarda esa fecha · devolver el reloj después es otro aviso (`reloj_sospechoso`). Escribe `30-…` a `35-…` (con su versión de tercios).

**Va en cuatro fases cortas** (la fecha se adelanta · la hoja de confirmación · la fecha se corrige · la administración confirma), cada una con una OPS recién abierta, y **repite la fase si OPS se cae o vuelve al acceso**
(lo dice en la salida y descarta lo anotado en ese intento; una falla con OPS viva sigue siendo una falla). Es por dos fallas que **no** son de esta pantalla (se reproducen con la fecha en orden) y que se investigaron en el
Bugfix 03 (`spec-driven/qa/bugfix/bugfix-03-estabilidad-ops-uia.md`): la vuelta al acceso era un fallo de OPS (un «Menú principal» activado dos veces sacaba también el menú) y **ya está corregida**; el
`APPCRASH` de `Avacom.Lms.Ops.exe` con 0xc0000005 dentro de `Microsoft.UI.Xaml.dll` es un fallo raro de Windows App SDK 1.7 con la UI Automation activa (una vez cada ≈ 800 vueltas con la carga máxima), y
esta repetición de fase es su red de seguridad. La última fase cambia lo que el nodo guardó
(la fecha confirmada), así que cada intento suyo levanta un nodo nuevo. Además, el campo de contraseña a veces no recibe la clave si se escribe antes de que la pantalla esté lista: el ingreso se repite hasta tres veces y sólo
sigue al PIN cuando la pantalla del PIN aparece de verdad.

Cuidados: los mismos de arriba (nodo aislado, perfil de OPS de pruebas, candado de pantalla). Dos más: la sesión del personal es **única**, así que el guion mira el estado por la API con una cuenta lectora aparte (entrar con
la de la administración cerraría la de OPS); y los controles se tocan por `AutomationId` con la acción `tecla` de `ui-ops.ps1` porque la página y la hoja tienen botones que se llaman igual («Liberar este equipo»).
