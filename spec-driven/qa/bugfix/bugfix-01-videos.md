# Bugfix 01 · Videos, audios e imágenes del aula no se ven (QA-27)

| Campo | Valor |
|---|---|
| Fecha | 2026-10-06 (hallazgo) · 2026-10-07 (arreglo) |
| Escenario | ESC-01-02 · Presentación (láminas) y, de paso, ESC-01-03 · Lectura con audio, video y PDF |
| Curso | *Estados de la materia y sus cambios* (Ciencias naturales, `avacom.co.lower_secondary.6.science.states-of-matter` 2.0.0) |
| Síntoma | Láminas con recuadro gris en OPS y en Student; el video muestra «Este video no está en el equipo del aula todavía. Lo servirá AVACOM Biblioteca»; en la tableta el video y el audio dan «El formato no es compatible o el archivo no existe» con la ruta de `fallos-student.log` |
| Estado | **Corregido en el nodo y en los dos clientes.** Verificado en vivo contra AVACOM Contenido real (HTTP y reproducción en Chromium). **No** verificado en una tableta Android ni en la pantalla de OPS/Student (ver §8) |

## 1. Resumen

El archivo **no es incompatible**. Los mensajes engañan: el reproductor dice «formato no compatible» (código `MediaError 4`) tanto cuando el códec no sirve como cuando el servidor contesta un error HTTP. Aquí el servidor contestaba **401**.

Con la sesión obligatoria (`AVACOM_LMS_EXIGIR_SESION=1`, que es como deja el nodo el instalador y como trae `backend/.env.example`), la ruta que sirve los medios exigía el pase del usuario en la cabecera `Authorization: Bearer`. Pero quien pide el medio es el **visor**, no el código de la app: la etiqueta `<video>`, la `<audio>` y la `Image` de MAUI no saben mandar cabeceras. El nodo les respondía 401 y todo medio del aula fallaba a la vez, en OPS y en Student, en Windows y en Android.

**Arreglo:** el nodo entrega ahora cada medio con un *pase* firmado dentro de la dirección (`/api/m/<pase>/aula/cursos/…`), que el visor puede abrir sin cabeceras; y los clientes dicen la causa real cuando un medio falla en vez de «formato no compatible».

## 2. Lo que se comprobó antes de arreglar (2026-10-06)

| # | Prueba | Resultado |
|---|---|---|
| 1 | Nodo de pruebas (puerto 8012, BD y logs temporales) con la sesión obligatoria. `GET /api/aula/cursos/<curso>/medios/<id>/?fuente=biblioteca` sin cabecera, para `vid-changes`, `aud-summary`, `img-cover-matter` e `img-particles` | **401 en los cuatro** |
| 2 | El mismo nodo con `AVACOM_LMS_EXIGIR_SESION=0` | **206** con `Content-Type` y `Content-Range` correctos: `video/mp4` 154 451 bytes, `audio/mpeg` 153 357, `image/webp`, `image/png` |
| 3 | Edge (WebView2, versión 154) cargando esas URL | `vid-changes`: 150 s, 1280×720, **reproduce**. `aud-summary`: 25,4 s, **reproduce** |
| 4 | Código de los clientes | Ningún cliente pone token en la URL de un medio: `ClienteJson.Absoluta` sólo une la base con la ruta; el JWT va sólo como cabecera en las llamadas JSON |
| 5 | Registros de Contenido del 2026-10-01 y 2026-10-05 | Los mismos medios salían 200/206: el servidor de medios y los paquetes funcionaban |

Por qué cuadra con lo que se ve: el recuadro gris de las láminas es la `Image` que recibió 401 (`AulaContenidoView.Imagen` la pintaba sobre un recuadro `Ds.Lienzo`, sin aviso); el mensaje de OPS salía de un `<div class="aviso">` fijo que se encendía con **cualquier** error; el de la tableta salía de traducir `MediaError 4`; y una sola causa en el nodo explica OPS y Student, audio, video e imagen a la vez (un problema de códec no explicaría las imágenes).

Las tres rutas de medios tenían el mismo defecto: `aula/cursos/…/medios/…`, `modo-estudio/asignaciones/…/medios/…` y `evaluacion/intentos/…/medios/…` usan `SesionSiSeExige`.

## 3. Los medios (no hubo que tocarlos)

| Medio | Formato real |
|---|---|
| `vid-changes`, `vid-particles` | MP4 idénticos entre sí (154 451 bytes), un solo track de **video** (sin audio), H.264 *High* nivel **5.0**, 1280×720, `moov` antes de `mdat` |
| `aud-summary`, `aud-changes` | MP3 idénticos entre sí (153 357 bytes) |
| Imágenes | PNG y WebP correctos |

Riesgo secundario, **no es la causa de hoy**: el nivel 5.0 de H.264 es más alto de lo que hace falta para 720p y algunas tabletas Android de gama baja lo rechazan. Si tras este arreglo la tableta sigue dando error con una respuesta 206, el aviso de pantalla ya lo dirá («el aula sí entrega el archivo… el formato o el códec no es compatible») y habrá que pedir a Contenido republicar los videos como H.264 *Main/High* nivel 4.0 o 3.1, `yuv420p`, `faststart`. Es del paquete de contenido, no del LMS.

## 4. Solución implementada: el pase de medios en la dirección

Es el mismo modelo del traspaso OPS ↔ Student (`EmitirTraspaso`) y de las capacidades efímeras del servidor de medios de Contenido.

**Cómo funciona**

1. Cuando el backend arma una lección, un curso o una pregunta para una petición **con sesión**, cada `url` de medio sale con el pase en el camino: `/api/aula/cursos/C/medios/M/?fuente=biblioteca` → `/api/m/<pase>/aula/cursos/C/medios/M/?fuente=biblioteca`. Sin sesión (modo prototipo, pruebas) la dirección no cambia.
2. El `<pase>` es un JWT `tipo=medio` firmado por el nodo con la clave de tokens, con `sid` = la sesión de quien pidió. Su `jti` **no** es una sesión (`medio-<sid>`), así que nunca vale como pase de API: usado como `Authorization` da 401 `sesion_invalida`. Vida 24 h (lo máximo que dura una sesión), redondeada a cubetas de 15 min para que la dirección de un medio no cambie entre lecturas de la lección.
3. Un middleware (`PaseDeMediosMiddleware`) valida el pase, **comprueba la sesión como en cada petición con Bearer** (caducidad, revocación, inactividad, cuenta activa), exige GET/HEAD y una ruta de medios, y reescribe el camino a la ruta normal. La vista de siempre ve a la **misma persona** de la sesión: cada ruta conserva sus reglas (al alumno le tiene que alcanzar la asignación; el medio tiene que ser de ESE examen).
4. Si la sesión se cierra, caduca o se revoca, el pase muere con ella: por eso su propia vida no necesita ser corta ni renovarse a mitad de una clase.
5. Las respuestas con pase llevan CORS abierto (`Access-Control-Allow-Origin: *`, `Range` permitido) y el middleware contesta `OPTIONS`. Hace falta para los **subtítulos**: la página del reproductor se carga desde `about:blank` en Windows y `file:///android_asset/` en Android, y un `<track>` es siempre una petición de otro origen.
6. El registro de auditoría (`backend-app.log`) ve la ruta **sin** el pase.

**Por qué en el camino y no en `?token=`:** las simulaciones piden sus archivos con rutas relativas (`js/app.js`); un parámetro de consulta no se hereda, un prefijo de camino sí.

**Qué abre y qué no.** Un pase abre únicamente medios (aula, modo de estudio, evaluación), en lectura, y sólo mientras viva su sesión. No abre la API, ni el expediente, ni la identidad, ni la clase; no es una sesión.

**Diferencias con la propuesta del 2026-10-06** (la propuesta era una vista nueva `MedioFirmadoView` con `AllowAny` y un permiso sin persona, sólo para el aula): se cambió por un pase atado a la sesión, resuelto en un middleware, porque (a) el modo de estudio y la evaluación tenían el mismo 401 y además necesitan saber **quién** pregunta (asignación del alumno, intento del alumno), y (b) así el pase muere con la sesión sin tabla de revocación. El contrato con AVACOM Contenido no cambia.

## 5. Cambios realizados

### Nodo (backend)

| Archivo | Cambio |
|---|---|
| `backend/acceso/dominio/errores.py` | Errores `PaseDeMediosInvalido` (`pase_de_medios_invalido`) y `PaseDeMediosVencido` (`pase_de_medios_vencido`), ambos 401 |
| `backend/acceso/aplicacion/casos_uso.py` | Caso de uso `PaseDeMedios`: `emitir(usuario, sesión)` y `resolver(pase)` → `Principal` de la sesión de origen |
| `backend/acceso/interfaces/medios.py` (nuevo) | `con_pase(ruta)`, `PaseDeMediosMiddleware` (valida, restringe a GET/HEAD y rutas de medios, reescribe la ruta, CORS, `OPTIONS`), `AutenticacionPaseDeMedios` (entrega la persona a DRF) |
| `backend/avacom_lms/settings.py` | El middleware va dentro de la auditoría y antes de `CommonMiddleware`; la autenticación DRF lleva `AutenticacionPaseDeMedios` antes de `AutenticacionJwt`. Además: `manage.py test` ya no lee `backend/.env` (ver §8) |
| `backend/classroom_engine/infraestructura/contenedor.py` | `url_medio` (aula) devuelve la dirección con pase |
| `backend/modo_estudio/infraestructura/contenido.py` | Ídem para las direcciones del modo de estudio |
| `backend/evaluacion/infraestructura/contenido.py` | Ídem para las de evaluación |
| `backend/classroom_engine/tests/test_medios_con_pase.py` (nuevo) | 14 pruebas (ver §7) |

### Clientes MAUI (OPS y Student, Windows y Android)

| Archivo | Cambio |
|---|---|
| `src/Avacom.Lms.Core/Services/DiagnosticoDeMedio.cs` (nuevo) | `SondeoDeMedio` y `DiagnosticoDeMedio`: pregunta al aula qué contestó de verdad (`GET` con `Range: 0-0`), traduce estado y `codigo` a una causa en español, descarga imágenes y oculta el pase en lo que se escribe a registros (`SinPase`). Nunca lanza |
| `src/Avacom.Lms.Ui/Controls/AulaContenidoView.cs` | (1) Video: el aviso fijo «Este video no está en el equipo del aula…» pasa a «No se pudo reproducir este video». (2) `AvisarFallo` ya no se queda en «formato no compatible»: lanza el sondeo y muestra, anota y notifica (`MedioFallido`) la **causa real** («tu sesión terminó», «el medio no está en el curso», «AVACOM Contenido no está disponible», «el aula sí lo entrega pero este dispositivo no lo reproduce»). (3) Las imágenes las baja la app (`CargarImagen`) y, si fallan, el recuadro dice «Imagen no disponible» con su causa en lugar de quedar gris. (4) Lo que la unidad tiene en vuelo se cancela al cambiar de unidad. (5) El archivo de fallos no guarda el pase |
| `src/Avacom.Lms.Ui/Design/WebViewAjustes.cs` | **Android:** `MediaPlaybackRequiresUserGesture = false` en las WebView del aula, para que el `autoplay` que el curso declara en la cátedra no se ignore en silencio |
| `src/Avacom.Lms.Ops/Platforms/Android/AndroidManifest.xml` | **Android (OPS):** `usesCleartextTraffic="true"`. Student ya lo tenía; OPS no, y el nodo del aula habla HTTP (sin TLS) en la LAN: Android 9+ bloquea ese tráfico |
| `tests/Avacom.Lms.Core.Tests/DiagnosticoDeMedioTests.cs` (nuevo) | 11 pruebas del sondeo y de los mensajes |

No hizo falta cambiar `ClienteJson.Absoluta`, `StudyModeService.ResolveMedia` ni el modo de estudio con paquete descargado: la dirección con pase se usa tal cual llega, y la regex de `ResolveMedia` (`/medios/<ref>`) sigue casando.

### Documentos

| Archivo | Cambio |
|---|---|
| `spec-driven/02-classroom-engine/05-contrato-biblioteca.md` (§1) | Anotado el contrato nuevo de dirección de medios y sus errores |
| `spec-driven/qa/bugfix/bugfix-01-videos.md` | Esta página |

## 6. Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Poner `AVACOM_LMS_EXIGIR_SESION=0` | Devuelve el nodo al modo abierto (QA-04, QA-06): resuelve el medio abriendo todo lo demás |
| Quitar la sesión sólo a la ruta de medios (`AllowAny` sin firma) | Cualquier equipo de la red leería todos los cursos licenciados. Empeora QA-06 |
| Añadir `?token=<JWT de sesión>` a cada URL de medio | El JWT de la persona quedaría en registros, historial e URL copiadas, y no llega a los archivos relativos de las simulaciones |
| Que la app baje el medio con Bearer y lo pase al visor como `data:` o archivo | Un video de 4 MB a 35 tabletas a la vez, sin `Range` ni saltos: peor que lo actual (sólo se hace para **imágenes**, que son pequeñas) |
| Mini servidor local en la tableta que añade la cabecera | Mucho código y un puerto más; el servidor local de Student ya existe sólo para paquetes descargados |
| Permiso firmado sin persona, sólo para el aula (la propuesta original) | No sirve al modo de estudio ni a la evaluación, que necesitan saber quién pregunta (ver §4) |

## 7. Pruebas

**Nodo** (`manage.py test classroom_engine.tests.test_medios_con_pase`, sesión obligatoria, API de Contenido de pruebas): **14 de 14 pasan**.

| Qué se prueba | Resultado |
|---|---|
| El síntoma: sin cabecera, la ruta con Bearer da 401; con ella, 200 | ✔ |
| La lección entrega cada medio con `/api/m/<pase>/…` | ✔ |
| El visor sin cabeceras abre video, audio, imagen, subtítulos y PDF con su `Content-Type` | ✔ |
| `Range` (`0-1023` → 206 de 1024 bytes; `bytes=N-` → cola) y `HEAD` | ✔ |
| Archivo relativo de una simulación (`js/app.js`) hereda el pase del camino | ✔ |
| CORS en la respuesta y en `OPTIONS` | ✔ |
| Pase alterado → 401 `pase_de_medios_invalido`; vencido → 401 `pase_de_medios_vencido` | ✔ |
| Cerrar la sesión mata el pase (401 `sesion_revocada`) | ✔ |
| El pase no vale como `Authorization`, ni fuera de rutas de medios (403), ni con POST/PUT/PATCH/DELETE (405) | ✔ |
| El registro de la petición no lleva el pase | ✔ |
| Cada persona recibe su propio pase | ✔ |
| Modo de estudio: direcciones con pase, medio servido, y un alumno al que no le alcanza la asignación sigue recibiendo 404 | ✔ |
| Sin sesión, las direcciones no cambian | ✔ |

**Clientes** (`dotnet test tests/Avacom.Lms.Core.Tests --filter DiagnosticoDeMedioTests`): **11 de 11 pasan**. `Avacom.Lms.Ui` compila para `net10.0-windows10.0.19041.0` y para `net10.0-android` sin errores.

**En vivo (2026-10-07)**, nodo aislado (puerto 8012, BD y logs temporales, sesión obligatoria) contra la **AVACOM Contenido real instalada** (2.1.7, curso 2.0.0):

| Paso | Resultado |
|---|---|
| Ruta vieja sin cabecera (`/api/aula/cursos/…/medios/vid-changes/`) | **401** (el síntoma) |
| Lección 1 pedida por un profesor con sesión | 16 direcciones de medios, todas con `/api/m/<pase>/` |
| Esas direcciones SIN cabeceras, `Range: bytes=0-1023`: `vid-changes`, `vid-particles` (`video/mp4`, 154 451 bytes), `aud-summary` (`audio/mpeg`, 153 357), `img-particles` (`image/png`), `img-cover-matter` (`image/webp`), `pdf-lab-guide` (`application/pdf`) | **206 con el tipo correcto en los seis** |
| Chromium del panel de navegación abriendo la dirección del video con pase | `readyState 4`, 150 s, 1280×720, sin error de medio |

## 8. Lo que no se pudo verificar, riesgos y pendientes

1. **No se probó en una tableta Android ni se miró la pantalla de OPS o de Student.** Se razonó desde el nodo, el código y Chromium. Hay que repetir ESC-01-02 y ESC-01-03 con el instalador nuevo: las 7 láminas completas, el video se reproduce y se puede saltar, suena el audio, se abre el PDF; y en la tableta, el video y el audio. Es la prueba que cierra este bugfix.
2. **El nivel H.264 5.0 en Android** (ver §3) sigue siendo un riesgo aparte; ahora, si ocurre, la pantalla lo distingue de un 401.
3. **Android WebView y `autoplay`:** el ajuste de `MediaPlaybackRequiresUserGesture` y el `usesCleartextTraffic` de OPS son correctos por la documentación de Android, pero no se ejecutaron en un dispositivo.
4. **Las imágenes ahora las baja la app** (una petición por imagen visible, en vez de dos con el sondeo). Una imagen corrupta que sí llegue completa se sigue viendo vacía: el visor no avisa de errores de decodificación.
5. **Costo en Contenido:** cada `Range` abre una sesión de medios nueva en AVACOM Contenido (`abrir_medio` en `backend/biblioteca/contenido_v2.py`). Con 25 o 35 tabletas (ESC-05-01) conviene reutilizar la sesión por curso; se puede hacer aparte.
6. **Los videos de relleno** son el mismo archivo dos veces (y los audios también); si el CTO quiere probar niveles H.264 en tabletas reales, hay que pedir a Contenido un paquete con videos distintos.
7. **Las pruebas del repositorio no corrían con el `.env` de desarrollo.** El `.env` (sesión obligatoria, BD propia) que lee `settings.py` desde el commit `4d4df002` se colaba en `manage.py test` y hacía fallar el `setUp` de todas las pruebas de API. Se arregló de paso: `manage.py test` ya no lo lee.
8. **Instaladores:** se reconstruyen en la misma sesión como **2.4.0** (OPS en `installer/latest`, Student Windows y APK), junto con el contrato 2 de Contenido (`spec-driven/qa/preparacion-prueba-masiva.md`). Una página html del curso nombra sus medios como `../{mediaId}` (sin barra final): desde el 2026-10-07 esa ruta también existe y hereda el pase del camino.
9. **Pregunta para el CTO:** el pase dura 24 h como máximo y siempre está atado a la sesión. Si se prefiere una vida más corta, hay que añadir la renovación en el visor (volver a pedir la lección al recibir `pase_de_medios_vencido`).
