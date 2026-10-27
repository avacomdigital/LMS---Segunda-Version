# AI Agent 3D (OPS) · etapa 1: sólo visual

La tableta 3D de AVACOM con rostro animado, como pantalla nueva de AVACOM LMS OPS (profesor). Sin LLM, voz ni red: dibuja el personaje y reproduce expresiones. El agente real se conectará después sin tocar el renderizador.

## Qué se hizo

| Pieza | Dónde |
|---|---|
| Pantalla `ai-agent.xaml` (+ `.xaml.cs`, clase `AiAgentPage`) | `src/Avacom.Lms.Ops/Pages/` |
| Ruta `ai-agent` | `AppShell.xaml.cs` |
| Tesela «AI Agent» (robot de Phosphor, celda libre a la derecha de «Comunicación») | `Pages/DashboardPage.xaml` y `.xaml.cs` |
| Renderizador Three.js (HTML/CSS/JS) | `Resources/Raw/wwwroot/ai-agent/` |
| Three.js 0.186.1 + GLTFLoader locales (sin CDN) | `.../ai-agent/vendor/three/` (ver `VERSION.txt`) |
| GLB | fuente única `assets/3d/agent/tablet.glb`, enlazado como `wwwroot/ai-agent/models/avacom-ai-agent.glb` en el `.csproj` (sin copia) |
| Atlas del rostro (reducido) | `.../ai-agent/assets/sprite-ai-agent.png`, generado por `tools/ai-agent/preparar_atlas.py` |
| Fotogramas y animaciones (editable) | `.../ai-agent/config/face-animations.json` |

No se tocó el backend, Student ni ningún otro módulo (sólo se añadió la ruta, la tesela y su `case`).

## Lo medido

**GLB** (`tablet.glb`, 16 KB): tres mallas, `tablet_cuerpo`, `pantalla_colores` y `face_sprite`, con `material_tablet_cuerpo`, `material_pantalla_colores` y `material_face_sprite`. No trae texturas ni imágenes. La pantalla mira hacia +X. `face_sprite` es un cubo de Blender con el desarrollo UV en cruz: su cara frontal ocupa sólo un cuarto de la textura (u 0.375–0.625, v 0.25–0.5) y girada; el controlador calcula esa transformación de la geometría, no la supone.

**Spritesheet** (`sprite-ai-agent.png`): 8688 × 2896 px, RGB **sin canal alfa**, 15 MB. Rejilla de **8 columnas × 3 filas** = 24 fotogramas de 1086 × 965,3 px, con una línea clara de 4 px en cada borde (se recorta con `inset`). Filas 1–2: ojos abiertos con 16 formas de boca; fila 3: ojos en arco (felices) con 8 bocas. No hay un fotograma de ojos cerrados lisos.
El original supera el `MAX_TEXTURE_SIZE` de muchas GPU móviles, así que WebGL carga una copia a 4096 px de ancho (4,2 MB, misma rejilla). El original queda intacto en `assets/`.

## Animaciones (`face-animations.json`)

Índice de fotograma = fila × 8 + columna.

| Estado | Fotogramas | Notas |
|---|---|---|
| `idle` | 12 | sonrisa suave; parpadeo automático cada 2,6–5,2 s |
| `blink` | 20 (140 ms) | **fallback**: no hay ojos cerrados; se usan los ojos en arco con la misma sonrisa. Interrumpe y luego reanuda lo que hubiera |
| `happy` | 20, 17, 21, 17 a 4 fps | 3,2 s y vuelve a `idle` |
| `tender` | 19, 20, 23, 20 a 2,5 fps | 4,2 s y vuelve a `idle` |
| `talking` | 16 formas de boca a 10 fps | en bucle hasta `stopAnimation()`; vuelve a `idle` |
| `thinking` | 13, 3, 13, 4 con pausas de 0,5–0,9 s | en bucle hasta `stopAnimation()` |

Un fotograma que no existe se omite con aviso; un estado sin fotogramas usa su respaldo (`fallbacks`).

## API

JavaScript (`window.AvacomAIAgent`): `playAnimation(name, {fps, durationMs, loop})`, `stopAnimation()`, `setExpression(name)`, `setAnimationFPS(fps)`, `getCurrentState()`, `dispose()`; además `setText(text)` (el recuadro bajo el personaje), `getDiagnostics()`, `pause()`, `resume()`. Las llamadas anteriores a «listo» se encolan.

C# (`AiAgentPage`): `ReproducirAsync`, `DetenerAsync`, `ExpresionAsync`, `FpsAsync`, `TextoAsync` (mensajes JSON por `HybridWebView.SendRawMessage`). La página manda `ready`, `error`, `log` y `state`.

## Decisiones

- **HybridWebView** con `HybridRoot="wwwroot/ai-agent"`; la página incluye `_framework/hybridwebview.js` (sin él no hay mensajes al host en .NET 10). Fuera del host (navegador) funciona igual.
- Materiales del cuerpo y la pantalla: no se tocan; `getDiagnostics().materialesIntactos` lo comprueba comparando una huella tomada al cargar.
- `material_face_sprite`: se le pone el atlas (`map`, color base blanco para no oscurecerlo), un brillo propio y un `onBeforeCompile` que pinta el sprite sólo en la cara frontal (los cantos conservan el color original). Un único material y una única textura; cada fotograma sólo reescribe la matriz UV.
- Render a 30 FPS máx., pixel ratio ≤ 2, sin dibujar si la pantalla no se ve; vaivén suave de la raíz del GLB (respeta `prefers-reduced-motion`).
- Al salir de la pantalla: `dispose` (bucle, listeners, geometrías, texturas, contexto WebGL) y desconexión del handler. Cada entrada crea una página nueva.

## Limitaciones verificadas

- **El degradado de `material_pantalla_colores` no existe en el GLB**: sin textura y con color base blanco, se ve como un marco gris claro alrededor del rostro. Se avisa en consola, en el log de OPS (`aiagent.aviso`) y en `getDiagnostics().pantalla`. No se simula; hay que hornearlo en Blender y volver a exportar.
- Sin fotograma de ojos cerrados (ver `blink`).
- Probado: página en Chrome-pane (WebGL2, estados y API) y dentro de OPS real con un nodo aislado (carga el GLB y el atlas sin red, mensaje `ready`, menú con la tesela). No probado en vivo: volver al menú y reentrar (UI Automation no ve la ventana con un WebView y no se pudo disparar el botón sin controlar el escritorio), ni Android.
