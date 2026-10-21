# Bugfix 03 · AVACOM OPS se cierra o «vuelve al acceso» cuando la UI Automation la maneja

| Campo | Valor |
|---|---|
| Fecha | 2026-10-20 (hallazgo, al verificar la fecha adelantada de MOD-018) · 2026-10-21 (causa, arreglo y arnés) |
| Pantalla | AVACOM OPS Master (`src/Avacom.Lms.Ops`), ir y volver de **Licencia** ↔ **Menú principal**; el defecto de fondo está en todos los botones «Menú principal» y «Volver» |
| Síntoma 1 | OPS aparece en la pantalla de acceso **con el proceso vivo, la sesión abierta y sin ningún 401** en los registros del nodo |
| Síntoma 2 | `Avacom.Lms.Ops.exe` muere: APPCRASH 1000/1001, `Microsoft.UI.Xaml.dll` 3.1.7.0, `0xc0000005`, desplazamiento `0x940f4d` |
| Estado | **Síntoma 1: era un fallo de OPS, corregido y con prueba** (492 pruebas del cliente; la regresión por UI Automation falla con la OPS de antes y pasa con la de ahora). **Síntoma 2: es un fallo de Windows App SDK 1.7 (XAML), reproducido con su pila nativa; OPS no tiene qué corregir y el arnés queda endurecido.** **No hay fuga** (§4). Pendiente: §9 |

## 1. Resumen

Eran dos fallas distintas con la misma pinta («OPS no sobrevive a la UI Automation»):

1. **Volver al acceso** no tenía nada que ver con la licencia ni con la plataforma. `Shell` resuelve cada `GoToAsync("..")` contra el estado del momento en que le toca, no del momento en que se pidió. Con «Menú principal» activado **dos veces seguidas** (un doble toque en la pantalla táctil de 86", o dos `Invoke()` seguidos de una prueba) el primer «..» saca la pantalla y el segundo, ya con el menú a la vista, **saca el menú**: `//login`, con la sesión abierta. `LicenciaPage.AlMenuPrincipalAsync` lo agravaba: con el menú ya arriba hacía `break` y caía a la ruta de reserva «..». Los ≈ 35 botones «Menú principal»/«Volver» de OPS son `GoToAsync("..")` pelado y tienen el mismo defecto.
2. **El APPCRASH** es un `NULL` que lee XAML (`0x110`, hilo de interfaz) en una devolución de llamada que XAML se encola a sí mismo, **53 ms después de descargar el menú** al abrir Licencia, con la UI Automation activa. Se reprodujo (una vez cada ≈ 800 vueltas con la carga máxima) y se capturó su pila. Windows App SDK 1.7.5 a 1.7.9 no traen ningún arreglo de UI Automation.

Lo que se descartó con datos: una **fuga** (páginas, visuales, GDI, manejadores) y la **licencia** (pasa igual sin fecha adelantada). Los tiempos por vuelta que crecían (≈ 7 → 13 s) eran carga de la máquina (instalador y pruebas compilando).

## 2. Evidencia de partida (2026-10-20)

| Dato | Valor |
|---|---|
| Visor de eventos → Application | «Application Error» 1000 y «Windows Error Reporting» 1001 de `Avacom.Lms.Ops.exe`; módulo `Microsoft.UI.Xaml.dll` 3.1.7.0; `0xc0000005`; desplazamiento `0x940f4d`. `Get-WinEvent` con `Level=2` y `-First 8` se pierde entre eventos de otros programas: **filtrar por `ProviderName`** |
| Archivo de WER (`C:\ProgramData\Microsoft\Windows\WER\ReportArchive`) | 19 informes de OPS desde el 2026-09-07. **Tres** con esta firma (`c0000005` en `Microsoft.UI.Xaml.dll+0x940f4d`): 2026-10-15 16:24 (OPS compilada en `out-ops-gb`), 2026-10-20 15:51 (fecha adelantada) y 2026-10-21 09:18 (la reproducción de esta investigación). Las demás son otras caídas anteriores y no son ésta (`80070490` y `800f1000` en `combase.dll`, `88000fa8` = `LayoutCycleException`, una en `coreclr.dll`, un cuelgue). Los 17 informes legibles traen `uiautomationcore.dll` cargada |
| `fallos-ops.log` | `LayoutCycleException` y `COMException 0x800F1000` del 1 y 15 de octubre: otra fragilidad previa de la capa WinUI/MAUI, no esta |
| Control de la sesión anterior (`crash_loop.py`) | Sin fecha adelantada, ≈ 20 vueltas «Licencia → Menú principal»: una vez el proceso murió con `0xc0000005`; otra vez OPS quedó en el acceso sin 401. Falló hacia la vuelta 9 |
| Versiones | Windows App SDK **1.7.250909003** (1.7.4), MAUI 10.0.20, Win2D 1.3.2, `Microsoft.UI.Xaml.dll` 3.1.7.2410 |

## 3. Cómo se midió

Para no tocar la OPS ni el nodo de quien trabaja en el equipo: nodos propios en 8017 a 8019, perfil de pruebas y candado de pantalla; OPS compilada con `-p:OutDir=` a carpetas aparte. Los experimentos con instrumentación corrieron sobre un `git worktree` desechable (nada de eso está en el árbol):

- un registro interno de OPS (navegación de `Shell`, ciclo de vida de las páginas, contadores del proceso, **elementos del árbol visual de WinUI**, retraso del hilo de interfaz, excepciones de primera oportunidad);
- un bucle de navegación **sin UI Automation** (OPS se mueve sola, ir y volver de Licencia) y modos «doble pop», «doble toque» y «carrera»;
- un manejador de excepciones **nativo** (`AddVectoredExceptionHandler`, sin código administrado) que anota cada `0xc0000005` con el módulo+desplazamiento de cada marco de la pila;
- clientes de UI Automation de dos tipos: uno que **invoca** (ir y volver de Licencia) y otros que sólo **leen** el árbol en bucle, en paralelo;
- `dumpbin /disasm` sobre `Microsoft.UI.Xaml.dll` para leer la función que falla (no hay símbolos: ver §9).

| Prueba | Qué hace | Resultado |
|---|---|---|
| E1/E2 | El arnés de antes (un PowerShell por acción), 10 + 40 vueltas | Sin caída; nada crece (§4) |
| E3 | Sin UIA: doble toque en «Menú principal» | **OPS queda en el acceso, viva, sin 401**: reproduce el síntoma 1 |
| E3 | Sin UIA: doble toque en «Licencia»; «carrera» (pedir ir y volver sin esperar, a 0, 100, 400 y 1000 ms) | Sin desvío: `Shell` serializa las peticiones y la pila ya incluye la página empujada |
| E6 | OPS navega sola + 2 lectores UIA, 194 vueltas de Licencia y 111 ciclos Menú ↔ Acceso | Sin caída |
| E7a | Un cliente UIA que invoca + 2 lectores, sin pausas | **Caída en la vuelta 197**, con pila |
| E8 | Tres OPS a la vez: A sin UIA (877 vueltas), B sin UIA y GC completo tras cada navegación (400), C UIA como E7a (600) | Sin caída en las tres |
| E10 | Atascos del hilo de interfaz de 6 s y de 25 s **dentro de la llamada del toque** (la pila de `Invoke()`), con el arnés antiguo y el endurecido, con la OPS vieja y la nueva | `Invoke()` **espera**, no lanza (76 llamadas medidas: ninguna excepción, ningún reintento) |
| `doble` | Dos `Invoke()` seguidos en «Menú principal» y en «Licencia» (§5) | OPS vieja: **FALLA**, «quedó en acceso». OPS nueva: 17 de 17 |

## 4. Fuga: no la hay

50 vueltas del arnés de antes (E1/E2) y, por separado, hasta 877 sin UI Automation (E8):

| Cosa | Medida |
|---|---|
| Elementos del árbol visual de WinUI | Menú **651**, Licencia **443**, **constantes** de la vuelta 1 a la 40 |
| Páginas | `DashboardPage` única y reutilizada; cada `LicenciaPage` se crea y se destruye (`Unloaded` + `HandlerChanging` sin manejador); ≤ 1 viva a la vez sin forzar el GC |
| Objetos GDI / USER | 48 / 50–54: planos |
| Manejadores | Suben a ≈ 1650 al abrir Licencia y vuelven a ≈ 1540 en el menú, cada vuelta |
| Memoria privada | **Meseta ≈ 780 MB** sin UI Automation (877 vueltas; 400 con GC completo tras cada navegación). Montón administrado: 10–19 MB |
| Con clientes UIA persistentes (E7a, E8-C) | Sube ≈ 0,6 MB por vuelta sin meseta (548 → 941 MB en 600 vueltas): son los *peers* y proveedores que los clientes de larga vida mantienen referenciados, no una fuga de OPS. El arnés de un PowerShell por acción no lo sufre (E2: meseta ≈ 550 MB) |

## 5. Síntoma 1 · OPS vuelve al acceso con el proceso vivo

**Reproducción sin UI Automation** (`doblepop`): ir a Licencia y activar dos veces seguidas el salto de «Menú principal».

```
Navigating //login/dashboard/licencia -> .. fuente=Pop
Navigated  //login/dashboard/licencia -> //login/dashboard fuente=Pop      (la primera)
Navigating //login/dashboard -> .. fuente=PopToRoot                       (84 ms después)
Navigated  //login/dashboard -> //login fuente=PopToRoot pila=(raíz)       (OPS en LoginPage, sin SesionRechazada: nada de 401)
```

**Por qué ocurre.** Shell evalúa cada «..» al ejecutarlo, no al pedirlo. El menú no tiene botón de atrás (se sale con «Cerrar sesión», que va a `//login` a propósito): cualquier «..» pedido con el menú a la vista es el segundo toque de un doble toque, y sacar el menú es siempre un error. `AlMenuPrincipalAsync` contaba las pantallas sobre el menú pero con 0 pantallas hacía `break` y caía a `GoToAsync("..")`; `ClaseCierrePage.RutaHasta` devolvía su ruta por defecto («../../../..») con 0 saltos.

**Qué no se pudo reproducir.** El detonante exacto del doble «Menú principal» en las corridas del 2026-10-20. La hipótesis era que el reintento de `ui-ops.ps1 invoke` (que repetía el toque si `Invoke()` lanzaba) lo activaba dos veces bajo carga; pero en ≈ 800 vueltas con lectores concurrentes y con atascos del hilo de interfaz de hasta 25 s **`Invoke()` no lanzó nunca**: UI Automation espera. Lo que sí es cierto: cualquier doble activación, del origen que sea, dejaba a OPS en el acceso. El arnés ya no repite a ciegas, pero eso es defensa en profundidad, no la causa demostrada.

**Arreglo (tres capas)** — `src/Avacom.Lms.Ops/Navegacion/`:

1. `AppShell` escucha `Navigating` y le pregunta a `GuardiaDeNavegacion` (lógica pura): **un «volver» con el menú principal a la vista se cancela**, y una petición idéntica a la anterior dentro de 350 ms (el doble toque) también. Cubre de una vez los ≈ 35 botones con «..» pelado y deja una línea `navegacion.ignorada` (INFO) en el registro local.
2. `LicenciaPage.AlMenuPrincipalAsync` y `ClaseCierrePage.RutaHasta` usan `RutasDeVuelta.Hasta`: con la pantalla buscada ya a la vista **no hay nada que sacar** (antes: ruta de reserva).
3. Pruebas: `tests/Avacom.Lms.Ops.Tests/GuardiaDeNavegacionTests.cs` (39 casos, entre ellos la secuencia exacta de 84 ms) y la regresión por UI Automation `estabilidad_ops.py doble`.

Una espera deliberada de más de 350 ms entre dos «Volver» (ver la pantalla nueva y tocar otra vez) pasa sin problema. Fuera de lo que cubre la guardia: el doble toque en un «Volver» de una pantalla **profunda** que cae dentro de la ventana se ignora; fuera de la ventana vale.

## 6. Síntoma 2 · APPCRASH 0xc0000005 en `Microsoft.UI.Xaml.dll+0x940f4d`

**Reproducido** (E7a, 2026-10-21 09:18:05.885): UIA invocando ir y volver de Licencia + 2 lectores que recorren el árbol sin pausa; la vuelta 197. **53 ms antes** el registro interno anota `Unloaded DashboardPage` (el menú se descarga al abrir Licencia). Es el hilo de interfaz y la dirección leída es **`0x110`**: un puntero nulo más un desplazamiento.

```
#00 Microsoft.UI.Xaml.dll+0x940f4d      mov rcx,[rax+110h]  con rax = NULL
#01 Microsoft.UI.Xaml.dll+0x3d4831      llamada virtual (ranura 2) con 3 argumentos
#02 …+0x9c80d  #03 …+0x9c0f0  #04 …+0x62dcc  #05 …+0xb90fd  #06 …+0xb8ee0  #07 …+0xb8e18
#08 …+0xd5e0e  #09 …+0xd609f  #10 …+0xd77f1  #11 …+0x2148ed
#12–#25 CoreMessagingXP.dll   (la cola del despachador)
#26–#31 USER32.dll            (DispatchMessage)
#32–#34 Microsoft.UI.Xaml.dll+0x20256c / 0x2024d1 / 0x2022c2   (el bucle de mensajes de XAML)
#35–#37 código administrado   #38–#47 coreclr.dll / hostpolicy.dll (el arranque de la app)
```

**Qué es.** La función (`0x940ef0`, 1051 bytes; sólo se la llama por una tabla virtual) hace `núcleo = this->[+0x28]`, `x = núcleo->[+0x110]` y, si es nulo, llama a un auxiliar (`0x918f2c`) que devuelve **el primer elemento de un vector del núcleo (`+0x160`) o `NULL` si está vacío**, y sin comprobarlo vuelve a leer `[rax+0x110]`. Es un `NULL` sin comprobar en una devolución de llamada que XAML se encola después de descargar un árbol grande (651 elementos, 92 lienzos Win2D), cuando ya no hay a qué engancharla.

**Con qué condiciones.** Sólo se vio con la UI Automation activa: 1 caída en 797 vueltas del cliente que invoca con 2 lectores (E7a 197 + E8-C 600) y **ninguna en 1277 vueltas sin UIA** (E8-A y E8-B). La muestra es corta: no prueba por sí sola que UIA sea imprescindible (si el ritmo sin UIA fuera el mismo, 0 en 1277 pasaría una de cada cinco veces); sí cuadra con los dos informes de WER de las corridas de pruebas y con que `uiautomationcore.dll` esté cargada en todos.

**Windows App SDK.** El proyecto usa **1.7.4**. Las notas de 1.7.5 a 1.7.9 (la última, del 2026-03-10) **no mencionan** nada de UI Automation ni de este fallo: [notas de la versión 1.7](https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/release-notes/windows-app-sdk-1-7). Sí hay varias correcciones de «caída por reentrada» en 1.7.1 a 1.7.4 (Popup, WebView2, entrada del puntero), que muestran la clase de defecto. Tres búsquedas en la web no dieron ningún informe igual; subir de versión dentro de 1.7 no está respaldado por las notas.

**Mitigación** (reduce la exposición; no está demostrada estadísticamente, la caída es de ≈ 1 en 800 vueltas con la carga máxima):

- el arnés endurecido pregunta menos y más barato (una `CacheRequest` por recorrido en lugar de cuatro llamadas por elemento, `FindFirst` por `AutomationId` en lugar de recorrer todo el árbol, sin clientes de larga vida ni lectores concurrentes);
- el arnés **no repite** un toque cuyo `Invoke()` lanzó y mira la pantalla antes de volver a tocar;
- `recorrido_fecha.py` conserva sus cuatro fases con OPS nueva y repite la fase si OPS muere o vuelve al acceso; ahora dice qué cosa es cada una;
- si OPS muere, el arnés dice el código de salida, el evento del Visor de eventos y las líneas de `fallos-ops.log` del pid (`estabilidad_ops.py`).

## 7. Qué cambió en el arnés (`tests/Avacom.Lms.Ops.Uia`)

| Archivo | Cambio |
|---|---|
| `ui-ops.ps1` | **Un toque se hace UNA vez**; si `Invoke()` lanza sale con 4 («dudosa») y nunca repite (buscar de nuevo mientras el control no aparece sí es seguro). `pin` igual (un dígito de más cambia el PIN). Lecturas con `CacheRequest`. Acciones nuevas: `existe`, `contar`, `doble` |
| `ui-carga.ps1` (nuevo) | Clientes de carga en un solo proceso: «vueltas» (invoca ir y volver, con `-Asentar` y `-Completo`) y «leer» (lector que sólo recorre el árbol) |
| `estabilidad_ops.py` (nuevo) | `doble` (la regresión), `vueltas` (el patrón endurecido con contadores por vuelta) y `estres` (la carga que reprodujo la caída) |
| `recorrido_licencia.py` | `toque` no repite tras una invocación dudosa; `donde_estoy` y `volver_al_menu` (por `AutomationId` `licencia-volver`: el botón «⌘ Menú principal» decorativo del dock del menú también contiene ese texto) |
| `recorrido_acceso.py`, `recorrido_fecha.py` | `Ops.dudosas`, `invocar` con la salida 4; `recorrido_fecha` usa `volver_al_menu` y su texto ya no atribuye todo a «una fragilidad de OPS» |

## 8. Cómo reproducirlo

```powershell
dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0 -p:OutDir=C:\temp\ops-uia\
# Síntoma 1: con una OPS anterior al arreglo falla («quedó en acceso»); con la actual pasa 17 de 17
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py doble --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\estab
# Síntoma 2: la carga máxima; ≈ una caída cada 200–600 vueltas (sale con 1 y dice el código, el evento y fallos-ops.log)
backend\.venv\Scripts\python.exe tests\Avacom.Lms.Ops.Uia\estabilidad_ops.py estres --ops C:\temp\ops-uia\Avacom.Lms.Ops.exe --salida C:\temp\ops-uia\estres --vueltas 600 --lectores 2
```

`estres` es la prueba más pesada: tres clientes de UI Automation sobre la ventana, que toma la pantalla y se ve lenta mientras corre. Con el equipo en uso conviene correrla en otro momento: el 2026-10-21, en una validación de 60 vueltas, quien trabajaba en el equipo la vio «atascada» y la cerró; OPS salió con código 0 y el guion lo contó como caída (ya no: un código 0 es un cierre normal y sale con 3).

## 9. Lo que no se probó o queda abierto

- **Símbolos.** `Microsoft.UI.Xaml.dll` no trae símbolos: los nombres de las funciones de la pila se habrían sacado del PDB público (`Microsoft.ui.xaml.pdb`, GUID `{842BD730-F2C1-3BF8-850C-829A507007F3}`, edad 1, del servidor de símbolos de Microsoft). **No se descargó** (una descarga necesita permiso expreso). Con él se podría escribir un informe en `microsoft/microsoft-ui-xaml`, que es lo que haría falta para un arreglo de verdad.
- **La mitigación del arnés no está demostrada con números.** Con ≈ 1 caída en 800 vueltas habría que correr miles de vueltas por variante para comparar `--asentar`, `--lectores` y `--completo`.
- **Student** (Android y Windows) usa el mismo patrón `GoToAsync("..")` pelado: probablemente tiene el mismo doble pop. No se tocó.
- **Con una pantalla real** de 86" no se probó el doble toque con dedos: se reprodujo con `Invoke()` y con llamadas a `Shell`.
- La OPS instalada del aula no se tocó ni se reconstruyó el instalador.
