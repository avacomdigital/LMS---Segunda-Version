# Preparación de la prueba masiva · contrato 2 de Contenido y 35 tabletas en LAN

| Campo | Valor |
|---|---|
| Fecha | 2026-10-07 |
| Para | OPS LMS (Windows) y AVACOM Student (Windows y Android) contra el nodo del aula y la **nueva** AVACOM Contenido |
| Guía | `openapi.v2 (3).json`, `course.schema (3).json`, `mensajes.es.json` (copias en `spec-driven/02-classroom-engine/`). **Este equipo no tiene la Contenido nueva**: la 2.1.7 instalada aquí no prueba el contrato 2, sólo el camino de red y los medios de siempre |
| Escenarios | ESC-01-02, ESC-01-03, ESC-01-05 (actividad) y ESC-05-01 (25 y 35 tabletas) de `escenarios-qa-02.md` |
| Detalle técnico | `spec-driven/02-classroom-engine/06-Versión-2-Contenido.md` §11 · `spec-driven/qa/bugfix/bugfix-01-videos.md` |

## 1. Qué se pidió y qué se hizo (todo a partir de los documentos)

| Pedido | Hecho | Dónde |
|---|---|---|
| En clase en vivo no se muestran cursos de prueba | El nodo sólo ofrece cursos de la biblioteca: el curso de ejemplo está apagado por configuración (`AVACOM_AULA_PERMITIR_EJEMPLO=0`, lo escribe el instalador) y `fuente()` resuelve «ejemplo» a biblioteca aunque alguien lo pida. Comprobado en el nodo aislado: el catálogo sale con `fuente: biblioteca` en todos y la ruta de pruebas devuelve biblioteca | `contenedor.fuente`, `installer/src/host/Configuracion.cs` |
| Gran parte del contenido viene en HTML; láminas con CSS + HTML | Medio `kind: html` y `html {mediaId, entry}` de cátedra y explicación (`url_html = url#s{n}` por lámina). El nodo sirve lo que una página del curso nombra con rutas relativas (`../medio`, `../medio/@captions`, `../medio/@poster`, `estilos.css`): ruta de medios sin barra final y nombres `@…`. OPS y Student cargan la página en una WebView acotada al nodo y cambian de lámina cambiando sólo el `#s{n}`. Los bloques siguen de respaldo | `curso.py`, `contenido_v2.py`, `AulaContenidoView.MostrarHtml` |
| Vídeos MP4 con reproductor HTML | El reproductor del aula pone el póster (`/medios/{ref}/poster`, siempre: la API no anuncia de antemano si hay) y las pausas para pensar (`interactions`); un `<video src="../vid">` dentro de una página html del curso va por la misma ruta con pase | `AulaContenidoView.Video` |
| Audio MP3 | Se sirve con pase y `Range` (bugfix 01) | bugfix 01 |
| Opción múltiple no se podía seleccionar en tabletas ni en OPS | La actividad *proyectada* era una vista previa sin toques; sólo se responde con «Lanzar actividad». Ahora las opciones de la vista previa se marcan en OPS y en Student (no envía nada) y, en Student, la actividad recién lanzada **se abre sola** para responder | `AulaContenidoView.Cuerpo`, `ClaseSiguiendoPage.PintarPendientes` |
| `drag_drop` (séptimo tipo del contrato) | Nodo: `elementos` (piezas) y `zonas` (rótulo o imagen), `placements` validado antes de `/v2/evaluate`. Tableta: editor táctil `EditorArrastrar` (tocar pieza → tocar zona; tocar una colocada la devuelve; las distractoras pueden quedarse). OPS: vista previa con bandeja y zonas | `respuestas.py`, `ActividadEditores.cs` |
| 35 tabletas en LAN | Capacidad 50 normal / 100 pico (sin tocar). Una sesión de medios por (curso, medio) cada 15 min en vez de una por trozo (`AVACOM_CONTENIDO_SESION_MEDIOS_SEG`); Daphne atiende cada petición en su hilo | §4 |

## 2. Lo verificado y con qué

| Comprobación | Con qué | Resultado |
|---|---|---|
| Diferencia del contrato entregado frente al que conocía el repo (28-09 y app 2.1.7) | los tres JSON | `html` (medio y objeto), `interactions`, `posterPath`, `drag_drop` (`DragDropQuestion`, `DragTarget`), `track`/`area`, examen sin tolerancias, `/v2/curriculum?country`, `extras.poster`. Sin rutas nuevas |
| Contrato 2 de punta a punta (html, `../medio`, `@captions`, `@poster`, `estilos.css`, pausas, póster, sesiones reutilizadas, `drag_drop`) | **API de Contenido de pruebas** construida según los documentos (`tools/host_contenido_v2_pruebas.py`) · `test_contrato_html.py` | OK (10 pruebas) |
| Pase de medios con sesión obligatoria (bugfix 01) | `test_medios_con_pase.py` | OK (14) |
| Camino de red y medios de siempre (imagen, mp4, mp3, pdf, simulación) sin cabeceras, con pase, desde un nodo aislado | **Contenido 2.1.7 instalada aquí** (NO es la nueva) | OK: 7 cursos, 363 direcciones con pase, 206 en los cinco tipos. Prueba que el nodo no rompe lo viejo; no prueba el contrato 2 |
| OPS en pantalla (perfil de pruebas, nodo aislado): lámina con imagen, lámina con video, actividad proyectada y, desplazando la lista, la pregunta de arrastrar | capturas `PrintWindow` | Imagen y texto se ven; el fotograma del video aparece; opciones de la actividad pintadas como filas marcables (en una captura hay una opción marcada por un toque real en la ventana de prueba: la marca funciona); la pregunta de arrastrar sale con su bandeja de 5 piezas y sus 3 zonas. Las capturas no distinguen la superposición de video de DirectComposition: el video entero hay que verlo en la pantalla real |
| Suite completa del nodo | `manage.py test` | 1143 OK, 4 omitidas (antes de `drag_drop`; la corrida tras `drag_drop` está en §5) |

## 3. Lo que la Contenido nueva debe cumplir según los documentos (para leerlo el día de la prueba)

1. `GET /v2/courses/{id}` → `media[]` con `kind: "html"` y su `entry`; `GET …/lessons/{id}` → objetos `lecture`/`explanation` con `html {mediaId, entry}`.
2. `POST /v2/media-sessions {mediaIds:[html-id]}` → `urls[html-id]` y los archivos de la carpeta en `<baseUrl><mediaId>/<ruta>` (el nodo pide siempre `<baseUrl><mediaId>/<entry>` y `<baseUrl><mediaId>/<archivo>`).
3. `extras[videoId].poster` cuando el video declara `posterPath`; el nodo lo expone en `/medios/{ref}/poster` y responde 404 si no viene.
4. **Pregunta para Biblioteca:** el resumen de medios del `CourseOutline` (openapi) no lista `posterPath` ni `interactions`. Si la API no los reenvía, el nodo no puede saber que un video tiene pausas: ¿los incluye `media[]` del curso o sólo la sesión de medios? Hasta que respondan, las pausas existen en el aula pero sólo se verán si la API las manda.
5. Si Contenido instala un paquete con html en el aula: proyectar su cátedra; las láminas deben verse con los estilos del curso y el video dentro de la página debe reproducirse. **Es la única parte sin prueba contra un paquete real.**

## 4. Guion sugerido para la prueba

1. **OPS, un solo equipo:** «Clase de hoy» → curso → lección → «Dar clase». Ningún curso de prueba.
2. **ESC-01-02:** recorrer las láminas; imágenes (si una falla, el recuadro dice la causa) y video (se reproduce y se puede saltar). Con un curso maquetado en html: cada lámina sale con los estilos del curso.
3. **ESC-01-03:** audio, video (con póster si lo trae) y PDF.
4. **ESC-01-05:** proyectar la actividad (se marcan opciones en pantalla) → «Lanzar actividad» → en cada tableta se abre sola → responder los tipos, incluido arrastrar (tocar pieza, tocar zona) → «Entregar» → OPS muestra el avance.
5. **ESC-05-01:** 25 y luego 35 tabletas; «35 conectados»; cambiar de lámina llega en ≤ 3 s al 95 %; proyectar la lámina con el video más pesado con todas a la vez y anotar cuánto tarda en la primera y en la última.

## 5. Riesgos y pendientes

| # | Riesgo | Qué hacer |
|---|---|---|
| 1 | **Ningún paquete real con html, pausas o póster pasó por este nodo**: todo el contrato 2 está probado con la API de pruebas escrita a partir de los documentos | Primer paquete html que llegue: ESC-01-02 con él antes de contar la función como lista |
| 2 | **Pregunta 3.4** (la API no anuncia `posterPath`/`interactions` en el resumen de medios) | Preguntar a Biblioteca; mientras tanto el aula funciona sin pausas y pide el póster siempre |
| 3 | **Router.** 35 × 3,6 MB × 8 ≈ 1 Gb; con 30 Mbps reales, ~35 s si todas piden a la vez. El nodo no es el cuello (un trozo en 5 ms) | Nodo por cable, Wi-Fi 5 GHz sin aislamiento de clientes, puerto 8000 abierto (QA-21) |
| 4 | **Android no se ejecutó en un dispositivo**: la Ui compila para Android; los ajustes (autoplay sin toque, tráfico HTTP sin cifrar en OPS) son por documentación | Primera tableta: una lámina con video y una con imagen antes de meter a las 35 |
| 5 | **El editor de arrastrar** se escribió hoy y sólo se vio compilar | Probarlo en una tableta con una actividad que lo traiga |
| 6 | **Contenido reiniciada a mitad de clase:** las sesiones de medios guardadas mueren; el nodo abre otra una sola vez | Previsto |
| 7 | **Cursos de la pista complementaria** (`track: complementary`, `area`): el aula los acepta (lleva `area`) pero no los agrupa por área | Pendiente si llegan |
| 8 | **Instaladores 2.4.0.** Student Windows (`installer/student-windows/latest/AVACOM-Student-Setup-2.4.0.exe`, 64,7 MB, SHA256 `0BA9285C…`) y APK (`installer/student-android/Student LMS 2.4.0.apk`, 21,2 MB, SHA-256 `D691CB3C…`, firma de depuración como 2.2.0/2.3.0) salieron el 2026-10-07 a las 13:11–13:14 con el código de esta sesión (nodo 257 OK tras `drag_drop`; suite completa 1143 OK; Core 640 OK). El de **OPS** lo compiló la sesión «Instalador MAUI .NET corregido» con este mismo código (mi compilación se había descartado porque esa sesión editó `installer/src` y `installer/tools` mientras corría: teclado táctil del primer arranque): `installer/latest/AVACOM-OPS-Master-Setup-2.4.0.exe`, 104 MB, SHA256 `536E2CEA…259C`, 13:44, 1145 pruebas del backend OK y ensayo del paquete completo OK | Los tres instaladores están listos; instalar OPS en el nodo del aula, Student en las tabletas Windows y el APK en las Android |
| 9 | **Identificador de tableta = nombre del dispositivo** (`Sesion.Dispositivo => "student-{DeviceInfo.Current.Name}"`): 35 tabletas del mismo modelo con el nombre de fábrica se presentan al nodo como UNA sola (hallazgo de la sesión del instalador, comprobado en emulador). Con la misma identidad se pisan la presencia, el bloqueo por tableta y el registro en Dispositivos | **Antes de la prueba:** poner un nombre distinto a cada tableta en Ajustes de Android (p. ej. `T-01`…`T-35`). Arreglo de código propuesto aparte: identificador propio por instalación (GUID guardado en la tableta) añadido al nombre; exige recompilar Student Windows y el APK (~20 min) y re-registra las tabletas ya conocidas |
| 10 | La pantalla de conexión de Student no recarga la última dirección (muestra siempre `http://192.168.1.10:8000`) | Escribir la dirección del nodo en cada tableta al conectar; arreglo pendiente |
| 11 | «Asignaturas» de Student pide la biblioteca del contrato 1 (`enlace.json`) y dice «Biblioteca no disponible» con sólo AVACOM Contenido abierta | No usar «Asignaturas» de Student en la prueba (la clase en vivo y el modo estudio van por el nodo, que sí habla con Contenido); arreglo pendiente |
