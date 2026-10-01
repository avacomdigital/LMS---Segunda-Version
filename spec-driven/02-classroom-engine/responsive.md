# Responsive · video e imagen en la pantalla de clase (OPS y Student)

> Corrección de defecto (2026-10-01): en la pantalla de dar clase, el video de «Los tres estados de la materia» se veía recortado.
> Código: `src/Avacom.Lms.Ui/Controls/AulaContenidoView.cs` (visor) · `src/Avacom.Lms.Ui/Design/WebViewAjustes.cs` · `AjustesDePantalla.cs` · `Controls/SelectorPantallaView.cs` · lógica pura en `src/Avacom.Lms.Core/Services/PerfilDePantalla.cs`.
> Pruebas: `tests/Avacom.Lms.Core.Tests/PerfilDePantallaTests.cs` (45 casos; suite del núcleo: 520, de Student: 61).

## 1. El defecto y su causa

**Síntoma.** En la lectura «Repasa a tu ritmo» · página 1 (curso `avacom.co.lower_secondary.6.science.states-of-matter`), el video «El modelo de partículas en movimiento» (`vid-particles`) se mostraba con el fotograma pequeño, pegado arriba a la izquierda, el resto del recuadro en negro y los controles (0:00 / 2:30) a todo el ancho. Con el desplazamiento parecía «cortado».

**Lo que se descartó** (todo verificado contra el curso real, API de Contenido v2):

| Hipótesis | Resultado |
|---|---|
| El video declara una proporción rara | No: `vid-particles` y `vid-changes` son MP4 de 1280×720 (16∶9); el navegador decodifica `videoWidth=1280, videoHeight=720`. |
| El recuadro se calcula mal | No: el DOM de la WebView medía exactamente el recuadro (`innerWidth=1155, innerHeight=650`, `<video>` de 1155×650). |
| Chromium compone mal el video | No: `Page.captureScreenshot` (protocolo de depuración de WebView2) devolvía el fotograma completo, a tamaño. |

**Causa.** La *superposición de video de DirectComposition* de WebView2 (`DirectCompositionVideoOverlays`) se presentaba dentro de la ventana de MAUI a (recuadro ÷ pantalla) de su tamaño: el fotograma salía a `recuadro² ÷ pantalla`. Comprobado con dos medidas independientes:

| Recuadro del video | Fotograma observado | Cociente |
|---|---|---|
| 1432 × 805 (captura del usuario) | 1068 × 600 | 1432 ÷ 1920 = 0,746 |
| 1155 × 650 (compilación con el ajuste, misma pantalla de 1920×1080) | 695 × 391 | 1155 ÷ 1920 = 0,602 |

Quitar la superposición lo arregla (el video llena su recuadro). Cambiar CSS (`object-fit`, `transform`), el tamaño de la WebView, o recargar tras darle su tamaño final **no** lo arregla: el defecto no está en el tamaño sino en cómo se presenta esa capa.

Además se halló un problema de maquetación que también debía cerrarse: el alto de un medio se fijaba en cada `SizeChanged` **de su propio contenedor** (`ConProporcion`), dentro de un `ScrollView`. Aparecer la barra de desplazamiento cambia el ancho, que cambia el alto, que cambia la barra… (`fallos-ops.log` registra `LayoutCycleException: Layout cycle detected` el 2026-09-30 21:09 y 22:06), y el video de 16∶9 a todo el ancho (805 px) era más alto que el espacio visible (≈ 685 px), así que nunca se veía entero.

## 2. La solución, en tres capas

### 2.1 WebView2 sin superposición de video (`WebViewAjustes`)
Al inicio de `CreateMauiApp` (OPS y Student) se añade a `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`:

```
--disable-features=DirectCompositionVideoOverlays,DirectCompositionLetterboxVideoOverlays
```

Respeta lo que ya hubiera en la variable (depuración remota, etc.) y no duplica. Con la variable puesta, el video se compone como una capa normal; sigue decodificándose por hardware. **Verificado:** la línea de comandos del proceso `msedgewebview2.exe` de OPS lleva el argumento, y el fotograma llena el recuadro.

### 2.2 Un recuadro que cabe entero (`AjusteDeMedio`)
Regla única para cualquier video o imagen de bloque, sea cual sea su proporción (`ancho`/`alto` del medio; 16∶9 si no se publicó o si es absurda, fuera de 0,2–3,0):

1. Espacio útil = lo que mide el **visor** (`AulaContenidoView`, no el contenedor del medio — así no hay realimentación con la barra de desplazamiento): ancho − 2 × 28 × escala de texto, alto − 32.
2. `ancho = min(ancho útil, alto útil ÷ proporción)`; `alto = ancho × proporción`. El medio **cabe entero**, centrado, con su proporción.
3. Piso: si el alto disponible es tan poco que el medio quedaría de menos de 320 × 180, gana el piso y la página se desplaza.
4. Se recalcula con 120 ms de retardo tras el último cambio de tamaño de la ventana (arrastrar el borde dispara decenas por segundo) y al cambiar el perfil de pantalla.

El HTML del reproductor llena exactamente su WebView: `html,body{overflow:hidden}`, `video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}` sobre fondo negro; sin `flex` y sin desplazamiento propio. Por eso los reproductores propios (audio, video) **ya no reciben** la inyección de `overflow-y:auto` que sí se mantiene para documentos externos (laboratorios, PDF).

Las imágenes sueltas de preguntas, opciones e ítems (dentro de columnas) conservan el alto por ancho de su contenedor (`ConProporcion`): no usan el espacio del visor porque viven en columnas más angostas.

### 2.3 Selector de pantalla (`PerfilDePantalla` + `SelectorPantallaView`)
En OPS, la barra de controles de la clase tiene un botón redondo de **pantalla** (junto a bloquear y avisar). Abre una hoja con dos filas de botones grandes, sin teclado:

- **Resolución:** Automático · 1920×1080 · 3840×2160.
- **Escala de Windows:** 80 % · 100 % · 125 % · 150 % · 200 % (deshabilitada en Automático).

Lo que MAUI maqueta son unidades lógicas (DIP) = píxeles físicos ÷ escala:

| Resolución | 80 % | 100 % | 125 % | 150 % | 200 % |
|---|---|---|---|---|---|
| 1920×1080 | 2400×1350 | 1920×1080 | 1536×864 | 1280×720 | 960×540 |
| 3840×2160 | 4800×2700 | 3840×2160 | 3072×1728 | 2560×1440 | 1920×1080 |

Un 4K al 200 % maqueta igual que un Full HD al 100 %. Techo del recuadro de un medio en un perfil = espacio de proyección de OPS en esa pantalla: lógico − 424 de ancho y − 400 de alto (columna de secuencia de 360, márgenes, barra de título, de controles y de tareas, medidos a 1920×1080 al 100 %), menos los márgenes de la tarjeta.

- **Automático** (por defecto): manda lo que mide la ventana; es lo normal y no hace falta tocar nada.
- Un **perfil manual** sólo puede *encoger* el recuadro, nunca agrandarlo más allá de lo que mide la ventana. Sirve con un proyector o una pantalla cuyo escalado de Windows reporta distinto de lo que se ve, y para revisar cómo quedará un curso en otra pantalla.
- Se guarda en las preferencias (`aula_perfil_pantalla`: `auto` o `1920x1080@100`); cualquier valor ilegible cae en Automático. Cambiarlo reajusta al instante todos los visores abiertos.
- La hoja dice qué detecta el equipo («El equipo reporta 1920×1080 · 125 %») con `DeviceDisplay` — sólo informa, nunca cambia el perfil por sí sola.
- Con un Full HD al 200 % (960×540 lógicos) el propio chrome de OPS no cabe; ahí manda el piso de 320 × 180 y la página se desplaza.

## 3. Cómo se verificó

Con OPS real, el curso real (Biblioteca conectada, API de Contenido v2) y la clase «Los tres estados de la materia», en una pantalla de 1920×1080 al 100 %:

1. Antes: fotograma 1068×600 en un recuadro de 1432×805 (captura del usuario) y 695×391 en uno de 1155×650 (compilación con el ajuste de §2.2 sin §2.1).
2. Con depuración remota de WebView2 (`--remote-debugging-port`): DOM correcto, `Page.captureScreenshot` correcto → la causa no está en el HTML ni en el tamaño.
3. Con `DirectCompositionVideoOverlays` desactivado a mano: el fotograma llena el recuadro; se repitió con la lista mínima de argumentos de §2.1.
4. Con la compilación final, sin pasar nada a mano: el argumento aparece en el proceso de WebView2 que lanzó OPS.

Para repetirlo: lanzar OPS con `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9333`, abrir la clase, y consultar `http://127.0.0.1:9333/json` (el documento del video aparece como `about:blank`). `Runtime.evaluate` sobre `document.getElementById('v').getBoundingClientRect()` da el recuadro; `Page.captureScreenshot` da lo que compone Chromium.

## 4. Qué NO se probó

- **Las otras resoluciones y escalas en pantalla real.** Sólo hay una pantalla de 1920×1080 al 100 % en esta máquina. Los 4K y las escalas de 80/125/150/200 % están cubiertos por pruebas unitarias de la aritmética (`AjusteDeMedioTests`, `PerfilDePantallaTests`), no por captura. El fallo de la superposición ocurría en 100 %; si en un 4K al 200 % aparece otro, el selector de §2.3 y `AjusteDeMedio` ya están para acotarlo.
- **La hoja del selector abierta y pulsada** en la app: la página de clase construye el botón y la hoja sin error y el botón se ve en la barra, pero no se accionó la hoja. Hay que abrirla una vez en una clase y elegir un perfil.
- **Student en una tableta** con el cambio (compila y comparte el visor y el argumento de WebView2; no se lanzó).
- **Android**: `WebViewAjustes` no hace nada fuera de Windows; el WebView de Android no tiene esta superposición.

## 5. Dónde tocar si cambia algo

| Si… | Tocar |
|---|---|
| un video vuelve a verse chico o negro | `WebViewAjustes.SinSuperposicionDeVideo` (¿se aplicó antes de crear la primera WebView?) |
| el recuadro debe ocupar más/menos del visor | `AjusteDeMedio.Ajustar`, `PerfilDePantalla.MargenVertical`/`MargenLateral` |
| el chrome de OPS cambia de tamaño (columna de secuencia, barras) | `PerfilDePantalla.ReservaAnchoOps` / `ReservaAltoOps` |
| se quiere otra escala u otra resolución en el selector | `PerfilDePantalla.Escalas`, `ResolucionPantalla`, `Leer` |
