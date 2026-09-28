# 04 · Classroom Engine · Frontend .NET MAUI del journey «Clase de hoy»

| Campo | Valor |
|---|---|
| Módulo | MOD-007 · Classroom Engine · clientes **AVACOM LMS OPS** (Windows, pantalla táctil sin teclado) y **AVACOM LMS Student** (Windows y Android) |
| Estado | **Implementado.** Compila en Windows (OPS y Student), 14 pruebas del núcleo en verde (6 nuevas). Todo el journey arranca al tocar **«Clase de hoy»** en el tablero de OPS |
| Journey que implementa | [03 · Journey «Clase de Hoy»](03-journey-clase-de-hoy.md): 4 pantallas en OPS (P1–P4) y 2 de reflejo en Student (S1–S2) |
| Contrato que consume | `/api/aula/` según [01 · Modelo de datos y API](01-modelo-de-datos.md) §9. OPS pide la fuente **`biblioteca`** (API de Contenido v2, [05](05-contrato-biblioteca.md)) y, si no está encendida, ofrece el curso de **`ejemplo`** (`example.json`) con un toque; Student no elige fuente |
| Design system | `LMS_DESIGN_SYSTEM_UI.html` (Avacom LMS UI Kit v2): tres materiales, colores semánticos y de categoría, botones de 64 px con relieve, radios por jerarquía, tacto primero |
| Documentos hermanos | [02 · Sugerencias](02-sugerencias-frontend.md) (DTO, mapa de componentes y reglas de WebView, de donde salió este código) · [00 · Introducción](00-introduccion.md) |

---

## 0 · Resumen

1. **Una sola entrada.** El hexágono y el botón del dock «Clase de hoy» de `DashboardPage` abren `clase-hoy` (P1). La demo `activity-monitor` sigue existiendo para «Reportes», ya no para la clase.
2. **Un cliente HTTP nuevo en el núcleo**, `AulaApi`, con la misma degradación que `BibliotecaDeContenido`: un `503` no es excepción, devuelve `null` y deja el motivo; además expone el `codigo` de negocio del backend (`sesion_activa_existente`, `actividades_abiertas`, `codigo_invalido`…) para que la pantalla decida.
3. **Un visor compartido**, `AulaContenidoView`, que pinta cualquier objeto del curso según su `componente` (presentación por láminas, lectura por páginas, laboratorio en WebView, actividad en vista previa, examen atenuado) y una `BloqueoView` para «Mira al frente».
4. **Los tokens del kit en código**, `Ds`: materiales, colores, radios, botones por rango con hundimiento al pulsar, píldoras de categoría y estado, tramos → `FormattedString`.
5. **Sin teclado en OPS.** Selección por toque, un solo Primary por pantalla, avisos con frases prehechas, confirmaciones de un toque. Lo único que se escribe es el código de seis dígitos, en la tableta del alumno, con un teclado numérico en pantalla.
6. **Sin tiempo real todavía.** OPS refresca la sesión cada 3 s y Student cada 2 s (`intervalo_sondeo_ms`). El WebSocket es Q-51 y no cambia estas pantallas: sólo la frecuencia con que llega el estado.
7. **Nada del curso se guarda.** Los clientes conservan sólo referencias en `Preferences`: la clase abierta en OPS y la participación en Student.

---

## 1 · Lo que se construyó

### 1.1 · Archivos

| Proyecto | Archivo | Papel |
|---|---|---|
| `Avacom.Lms.Core` | `Models/AulaModels.cs` | DTO de `/api/aula/`: catálogo (`CatalogoAula`, `AsignaturaAula`, `FichaCurso`), vista de aula (`VistaCurso`, `LeccionAula`, `ObjetoAula`, `UnidadAula`, `BloqueAula`, `PreguntaAula`, `MedioAula`, `SimulacionAula`, `Tramo`, `NotasDocente`), sesión (`SesionDeClase`, `FocoAula`, `ParticipanteAula`, `DistribucionAula`, `AvisoAula`, `ResumenSesion`, `EstadoTableta`) y `ErrorAula` |
| `Avacom.Lms.Core` | `Services/AulaApi.cs` | `IAulaApi` / `AulaApi`: curso (`CursosAsync`, `CursoAsync`, `ObjetoAsync`), docente (`IniciarAsync`, `SesionAsync`, `ProyectarAsync`, `ControlAsync`, `DistribuirAsync`, `CerrarDistribucionAsync`, `AvisarAsync`, `ParticipanteAsync`, `CerrarAsync`), estudiante (`UnirseAsync`, `EstadoAsync`, `PresenciaAsync`, `ConfirmarEntregaAsync`). `Absoluta(ruta)` resuelve las URL relativas de los medios |
| `Avacom.Lms.Ui` | `Design/Ds.cs` | Tokens y fábricas del design system (§3) |
| `Avacom.Lms.Ui` | `Controls/AulaContenidoView.cs` | El visor de la clase (§4) |
| `Avacom.Lms.Ui` | `Controls/BloqueoView.cs` | «Mira al frente» a pantalla completa |
| `Avacom.Lms.Ops` | `Pages/ClaseHoyPage.xaml(.cs)` | **P1** · Materias de hoy |
| `Avacom.Lms.Ops` | `Pages/ClaseCursoPage.xaml(.cs)` | **P2** · Curso y lecciones, selección y «Dar clase» |
| `Avacom.Lms.Ops` | `Pages/ClaseSesionPage.xaml(.cs)` | **P3** · Clase en curso (código, secuencia, proyección, controles, participantes, aviso) |
| `Avacom.Lms.Ops` | `Pages/ClaseCierrePage.xaml(.cs)` | **P4** · Resumen de cierre |
| `Avacom.Lms.Ops` | `Sesion.cs` | `FuenteAula`, `Aula`, `ProfesorId`, `ProfesorRotulo`, `ClaseAbiertaId` |
| `Avacom.Lms.Ops` | `AppShell.xaml.cs`, `Pages/DashboardPage.xaml(.cs)` | Rutas `clase-hoy`, `clase-curso`, `clase-sesion`, `clase-cierre`; el hexágono «Clase de hoy» (ahora magenta, categoría *Live class*) y el botón del dock abren P1 |
| `Avacom.Lms.Student` | `Pages/ClaseUnirsePage.xaml(.cs)` | **S1** · Código de seis dígitos con teclado numérico |
| `Avacom.Lms.Student` | `Pages/ClaseSiguiendoPage.xaml(.cs)` | **S2** · Siguiendo la clase |
| `Avacom.Lms.Student` | `Sesion.cs`, `AppShell.xaml.cs`, `Pages/StudentMenuPage.xaml(.cs)` | `FuenteAula`, `Aula`, participación guardada; rutas `clase-unirse`, `clase-siguiendo`; hexágono «Clase en vivo» (magenta) en el menú y en el dock |
| `Avacom.Lms.Student` | `Platforms/Android/AndroidManifest.xml` | `usesCleartextTraffic="true"`: sin él ninguna URL `http://<IP>:8000/…` carga en la tableta (RF-L05) |
| `Avacom.Lms.Core.Tests` | `AulaApiTests.cs` | Deserialización de la vista de aula y del estado de la tableta, degradación `503`, códigos `409`, cuerpo en `snake_case` con `Content-Length`, URL absolutas |

### 1.2 · Lo que se conserva sin tocar

`BibliotecaDeContenido`, `CourseContentView` (modo libre en «Asignaturas»), `ProfessorHexTile`, `HexagonButton`, `LoginPage`, `ConnectionPage`, `RegistroDeFallos`, estilos `Styles.xaml` / `Colors.xaml` de ambas apps.

---

## 2 · Las pantallas, tal como quedaron

### P1 · `ClaseHoyPage` · Materias de hoy

Desde 2026-09-28 viste el lenguaje **Liquid Glass** (`Avacom.Lms.Ui/Design/Glass.cs`) sobre el fondo claro de la aplicación: la imagen de discos en relieve `assets/fondo-discos.png` (`fondo_discos.png`, AspectFill, detrás de todo) y, encima, texto en tinta, un menú sólido y láminas de vidrio sólo donde se lee una ficha. No hay barra horizontal superior. (Una primera versión con fondo lavanda, panal y textos blancos se descartó el mismo día por oscura y ajena al resto de la aplicación.)

- **Menú vertical fijo** a la izquierda (`VerticalNavigation` dentro de un `Border` sólido `#5A5A56`, el gris del dock del tablero; 250 px, 224 en anchos intermedios y raíl de iconos por debajo de 1100 px, nunca barra horizontal). Sólo cuatro opciones en blanco, apiladas **desde abajo** porque el tablero táctil es gigante: «Menú principal» (activa, cápsula blanca translúcida pegada al borde inferior; vuelve al tablero), «Lección» (la clase abierta si la hay; si no, baja a la lista de cursos), línea translúcida, «Configuración» (representada en el prototipo) y «Cerrar sesión» (`//login`). Sin perfil, avatar ni progreso.
- **Chip de la fuente** (`SourceStatusChip`, cápsula blanca con filo y punto de color) arriba a la derecha del contenido, tocable como antes: alterna Biblioteca ↔ curso de ejemplo y conserva sus cinco estados («Comprobando…», «Biblioteca conectada» verde, «Curso de ejemplo» ámbar, «Biblioteca apagada» ámbar, «Sin conexión con el aula» rojo).
- **Hero** sobre el fondo, sin tarjeta: «¡Hola!», «¿Qué vas a dar hoy?» (44/SemiBold, tinta), la descripción y «N materias asignadas»; a la derecha, un libro abierto de cristal con tres hexágonos flotantes (`GlassBookView`, sólo decorativo).
- **Cuerpo**: un `ProfessorHexTile` con `Glass="True"` por asignatura (acento por materia: ciencias rosa, comunicación azul, matemáticas ámbar, sociales violeta; `Glass.AcentoMateria`), que al tocarse desplaza a su sección; por asignatura, una píldora del acento con «N cursos» y una **`CourseGlassCard` por curso** (`LiquidGlassPanel` blanca al 55 % con desenfoque: bloque de icono del acento, título, subtítulo y metadatos completos en tinta, y botón de vidrio con bisel «Ver lecciones ›»). Toda la tarjeta sigue siendo tocable.
- Si este equipo dejó una clase abierta o suspendida (`Sesion.ClaseAbiertaId`), aparece antes de los hexágonos una lámina con tinte violeta «Continuar la clase» (el único Primary de la pantalla) con código y conectados.
- Sin backend o con `503`: alerta de vidrio semántico suave (`Glass.Alerta`, ámbar o rojo con su tinta oscura) con `detail` + `sugerencia`, «Reintentar» y, si la biblioteca está apagada, «Usar el curso de ejemplo» (Primary sólo si no hay clase que continuar). Sin materias: `Glass.EstadoVacio`.
- Lección aprendida en Windows: un `Path` cuya geometría trae un arco diminuto (radio ≈ 1) produce un NaN al convertirse a bézier y Direct2D aborta el dibujado (`D2DERR_BAD_NUMBER`); el primer fallo deja inutilizados **todos** los lienzos Win2D de la ventana (iconos del tablero incluidos). Las geometrías de los iconos se simplifican a mano y los cuerpos con degradado se pintan en `GraphicsView` propios (`HexGlassDrawable`), nunca con `Path` + pincel degradado.

### P2 · `ClaseCursoPage` · Curso y lecciones

- Cabecera del curso en content surface: píldoras (asignatura, grado, nivel, duración), título 30 pt, subtítulo, descripción, portada a la derecha. Botón quiet «Notas del docente» despliega las `notas_docente` del curso (tarjeta ámbar).
- **Una tarjeta por lección**: número en un cuadrado rojo, título, resumen, los objetos como **píldoras de categoría** («▣ Presentación · Todo lo que nos rodea es materia» en magenta, «▤ Lectura» en amarillo con tinta oscura, «⌗ Laboratorio» en cyan, «✎ Actividad» en verde, «✓ Examen» en gris atenuado) y el pie con minutos y conteo. La lección que sólo tiene examen queda al 60 % y no se selecciona.
- Tocar una lección la **selecciona** (filo rojo de 3 px). La **barra inferior** (dark glass) tiene «Clase libre» quiet a la izquierda, el texto «Lección seleccionada: …» y **un solo Primary** «Dar clase con esta lección», deshabilitado hasta seleccionar.
- `POST /api/aula/sesiones/` con `via`, `curso_ref`, `leccion_ref`, `fuente`, `profesor_id`, `profesor_rotulo`, `superficie: "pantalla"`. Ante `409 sesion_activa_existente`: diálogo «Continuar esa clase» / «Cerrarla y empezar» (cierra con `forzar` y reintenta).

### P3 · `ClaseSesionPage` · Clase en curso

Una sola superficie táctil con cuatro zonas:

| Zona | Contenido | Llamadas |
|---|---|---|
| Cabecera (dark glass) | **Código de unión a 72 pt** con espaciado, «N conectados», lección y curso, punto de conexión (Conectado · Clase suspendida · Sin señal) y botón «Participantes» (con «N esperando» cuando hay lista de espera) | `GET sesiones/{id}/` cada 3 s |
| Columna izquierda (content surface) · Secuencia | Los objetos de la lección con icono de categoría; el que está en foco resaltado en violeta y, si es una presentación, sus láminas como cuadros numerados tocables. Debajo, la tarjeta verde «Actividad en curso» con barra «N de M tabletas la recibieron» | `POST foco/` |
| Centro · Proyección | `AulaContenidoView` en modo docente (escala 1,15): lámina con bloques y mandos «◀ Anterior · • • • · Siguiente ▶», o el laboratorio en WebView, o la actividad en vista previa | `POST foco/` con `unidad_ref` |
| Barra inferior (dark glass) | Interruptor **Bloquear pantallas** (ámbar al estar activo), interruptor **Seguimiento** (cyan; «Navegación libre» al liberar), Secondary **Lanzar actividad** (habilitado cuando el foco es una actividad; pasa a «Cerrar recepción» mientras esté abierta), Secondary **Aviso** (hoja con frases prehechas: «Miren al frente», «Dos minutos», «Guarden lo que llevan», «Levanten la mano si terminaron», «Vamos a cerrar») y, separado, el Destructive **Terminar clase** | `POST controles/`, `distribuciones/`, `distribuciones/{id}/cerrar/`, `avisos/`, `cerrar/` |

Panel de participantes superpuesto: avatar con iniciales (verde admitido, ámbar esperando, gris salió), nombre, estado legible, «invitado» si fue admisión nominal; acciones «Admitir» (Secondary 52 px) para quien espera, «Expulsar» (quiet, con confirmación) para quien está dentro, «Readmitir» para quien salió.

Terminar: confirmación de un toque; ante `409 actividades_abiertas`, segundo diálogo MSG-016 «Terminar de todos modos» → `forzar: true`. Al cerrar, navega a P4 y olvida `ClaseAbiertaId`. Si el sondeo encuentra la sesión ya cerrada (desde otra superficie), también navega a P4.

### P4 · `ClaseCierrePage` · Resumen

Píldora «Clase terminada», título con la lección, subtítulo con curso, docente y código, y **tarjetas** del resumen: Participantes (con «máximo N a la vez»), Proyecciones, Actividades, Avisos, Duración, Pendientes (verde si cero, ámbar si hay intentos abiertos). Un solo Primary «Volver a Clase de hoy» y un quiet «Menú principal».

### S1 · `ClaseUnirsePage` · Entrar a la clase

Seis casillas de 62 × 76 px, teclado numérico de 76 px por tecla (dígitos Secondary, ⌫ y Borrar quiet), Primary «Entrar a la clase» habilitado al sexto dígito. Al entrar guarda `aula_sesion`, `aula_participante` y `aula_codigo`. `en_espera` → alerta ámbar «Tu profesor te va a admitir» y sondeo hasta ser admitido. Errores traducidos: `codigo_invalido` → «Ese código no es. Pídele a tu profesor que lo muestre en la pantalla», `participante_expulsado` → «Habla con tu profesor…», sin red → sugerencia del backend. Al abrir la pantalla con una participación guardada en una clase activa, se readmite sola y salta a S2 (FUN-077, RF-A10).

### S2 · `ClaseSiguiendoPage` · Siguiendo la clase

Barra superior con lección, curso y docente, punto de conexión (Conectado · Reconectando con el aula · La clase se está reanudando) y «Salir». `AulaContenidoView` en modo estudiante: pinta el `foco` (baja el objeto con `GET …/objetos/{ref}/` sólo cuando cambia de objeto; cambiar de lámina no vuelve a pedir nada). `seguimiento: true` oculta los mandos; al liberarlo aparecen. `pantallas_bloqueadas: true` muestra `BloqueoView` por encima de todo. Las `pendientes` de clase `actividad` aparecen como tarjeta verde con Primary «Abrir» (confirma la entrega y muestra la actividad; «Volver a la clase» regresa al foco). Los `avisos` nuevos salen como bandas no bloqueantes durante 8 s. Sesión `suspendida` → banda fija «La clase está en pausa»; `cerrada` → diálogo «La clase terminó» y vuelta al menú; participante `expulsado` → diálogo y salida. «Salir» confirma, declara `salio` y olvida la participación.

---

## 3 · Cómo se aplicó el design system

| Regla del kit | Dónde |
|---|---|
| **Tres materiales**: content surface blanco 96 % sin desenfoque y con filo de 9 %, glass chrome sólo en barras, dark glass en la barra de controles | `Ds.Tarjeta`, `Ds.BarraClara`, `Ds.BarraOscura`; las barras superiores de P1, P2, S1 y S2 son `#B3FFFFFF` con filo; la cabecera y la barra de controles de P3 y la barra de acción de P2 son `#D1141417`. **Ningún párrafo va sobre vidrio**: las láminas, notas y preguntas se leen en tarjetas blancas |
| El desenfoque de fondo | MAUI no lo ofrece en WinUI/Android sin código de plataforma; se aproxima con la transparencia y el filo. En la pantalla del aula (4 m) el kit mismo pide dejar el desenfoque, así que la pérdida es menor |
| **Colores semánticos** Success `#019D60`, Info `#01A4E1`, Warning `#F3C701`, Danger `#C82230` | `Ds.Exito` (conectado, actividad recibida), `Ds.Info` (seguimiento activo), `Ds.Alerta` (bloqueo activo, lista de espera, fuente de ejemplo, clase suspendida), `Ds.Peligro` (Terminar clase, sin señal). Danger es más oscuro que el rojo de marca: «terminar» nunca se lee como «continuar» |
| **Categorías de contenido**: Video cyan, Live class magenta, Quiz verde, Reading amarillo, Audio rojo | `Ds.Categoria(componente)`: presentación → magenta, lectura/pdf/texto → amarillo (con tinta oscura encima), laboratorio/video/imagen → cyan, actividad y preguntas → verde, audio → rojo, examen → gris. Se usan en iconos, píldoras, el resalte del foco y el hexágono «Clase de hoy»; **nunca como relleno de un botón** |
| **Radios**: 10–12 controles, 14 internos, 16 botones, 18–20 tarjetas, 22 barras, 24 grandes, 999 píldoras | `Ds.RadioControl` (cuadros de lámina, iconos), `Ds.RadioInterno` (bloques definición/destacado, actividad en curso), `Ds.RadioBoton`, `Ds.RadioTarjeta`, `Ds.RadioBarra`, `Ds.RadioGrande` (la lámina proyectada), `Ds.RadioPildora` |
| **Botones** 64 px, radio 16, 20/600; Primary `#E5262B`, Secondary blanco, Quiet transparente, Destructive `#C82230`; **uno Primary por pantalla** | `Ds.Boton(texto, rango)`. P1: «Continuar la clase» (sólo si hay clase abierta); P2: «Dar clase con esta lección»; P3: ninguno Primary (la barra son interruptores y Secondary; el Destructive va detrás de confirmación); P4: «Volver a Clase de hoy»; S1: «Entrar a la clase»; S2: «Abrir» la actividad pendiente |
| **Neumorfismo**: relieve con luz arriba-izquierda; el control se hunde al pulsar | `Ds.SombraElevada` (6, 8 / 14 / 14 %) en Primary, Secondary y Destructive; `Ds.Hundir`: al `Pressed` la sombra se recoge (2, 3 / 6) y el botón escala a 0,96 en 90 ms; al `Released` vuelve. MAUI admite una sola sombra por vista, así que el realce blanco (−5, −5) se representa con el fondo blanco de la tarjeta y el filo; el estado *inset* se aproxima con escala + sombra corta. Ninguna sombra de color |
| **Tacto**: 64 px de piso, 16 px entre objetivos, sin gestos ocultos, nada destructivo sin confirmar | Todos los botones de OPS y Student son ≥ 64 px salvo las acciones dentro de la lista de participantes (52 px, «Staff»); las teclas del código, 76 px; separación 14–16 px; expulsar y terminar confirman; ningún arrastre: ordenar se muestra con flechas, avanzar con botones |
| **Tipografía**: cuerpo `#18181B`, secundario `#52525B`, etiqueta de botón ≥ 20 | `Ds.Titulo`, `Ds.Cuerpo`, `Ds.Secundario`; en la proyección (P3) el texto escala ×1,15 |
| Estado, alertas y vacío | `Ds.Pildora` para estados (Conectado · Esperando · Salió · Clase suspendida), `Ds.Alerta_` no bloqueante para avisos y errores, tarjeta de estado vacío en P1 |

---

## 4 · Cómo pinta `AulaContenidoView`

| `componente` | Qué construye | Notas |
|---|---|---|
| `presentacion` / `lectura` | Tarjeta grande (radio 24) con «Presentación · título» y la píldora «Lámina N de M» (o «Página N de M»), el título de la unidad a 30 pt y sus bloques; debajo, si `PuedeNavegar`, los mandos anterior/siguiente con puntos de posición | `UnidadPedida` avisa a la página; en OPS eso es `POST foco/`, en Student con navegación libre es local |
| bloque `titulo` | `Label` con tramos, 32/24/20 pt según `nivel` | |
| bloque `texto` | `Label` con tramos; `definition` → barra roja lateral sobre fondo rosado; `highlight` → fondo ámbar | |
| bloque `lista` | Filas «•» o «N.» rojas + tramos | |
| bloque `imagen` | `Image` (`UriImageSource`, sin caché) en un marco gris de 360 px, pie debajo, descripción semántica = `texto_alternativo` | Con la fuente de ejemplo llega el PNG de marcador |
| bloque `video` | `WebView` con `<video controls>` y `src="…#t=desde,hasta"`, `<track>` de subtítulos si hay `subtitulos_url`; un script pausa al llegar a `hasta_seg` y, si el archivo no existe, muestra «Este video no está en el equipo del aula todavía». La WebView va dentro de `ConProporcion`: **el alto se calcula del ANCHO real que le toque en cada pantalla** (`ancho`/`alto` del medio, p. ej. 1280×720, o 16∶9 si la biblioteca no los publicó), recalculado en cada `SizeChanged` — antes era un número de píxeles fijo (320 · Escala) que dejaba el video diminuto en la columna ancha de proyección de OPS | El ejemplo no trae video: la tarjeta lo explica |
| bloque `audio` | Icono rojo de categoría + `WebView` con un **reproductor propio** (`AulaContenidoView.HtmlAudio`): botón Primary de 64 px que se hunde al pulsar (▶ / ❚❚), barra de avance tocable y tiempo `m:ss / m:ss`; píldora «Audio · m:ss». Si el archivo no se puede reproducir (`MediaError` 1–4 o sin respuesta en 12 s), el reproductor lo dice en rojo, deshabilita el botón, navega a `avacom-aula://fallo?tipo=audio&codigo=…` (interceptado por MAUI), se anota en `%LOCALAPPDATA%\AVACOM\lms\fallos-<app>.log` y aparece una alerta bajo el bloque con la ruta del archivo; `MedioFallido` avisa a la página | MP3 real de la biblioteca (`audio/mpeg`, con `Range`); WAV de marcador con la fuente de ejemplo |
| bloque `pdf` | Cabecera con icono amarillo, título y «Páginas a–b de N»; en Windows `WebView` a `url_pagina_inicial` (WebView2 abre en `#page=N`); en Android botón «Abrir el documento» con `Launcher` | |
| `laboratorio_web` | Tarjeta con objetivo, instrucciones (tramos) y los pasos como píldoras desplazables; debajo la `WebView` a `url_lanzamiento` sobre fondo oscuro; pie con la atribución de licencia (PhET, CC BY 4.0) | Si `destinos` no incluye `tablet` y no es escritorio, tarjeta «Se ve en la pantalla del aula» |
| `actividad` | Cabecera verde con «N preguntas · M pts», píldoras de ajustes, una tarjeta por pregunta con su número, enunciado y tipo, y la vista previa del control (opciones, plantilla con huecos, columnas para relacionar, lista para ordenar, área para abierta) | Sin claves: el backend no las envía y la vista no las busca. Responder es del flujo de intentos (Q-48) |
| `examen` | Tarjeta al 75 % con «Lo aplica el módulo de evaluación (MOD-010)» y el tamaño del banco | Ni se proyecta ni se lanza |

Reglas de la `WebView`: las de una misma unidad viven juntas (una página puede llevar audio, video y pdf: la regla anterior de «una sola viva» vaciaba el audio al crear el video) y se vacían todas con `about:blank` al cambiar de unidad u objeto; `Navigating` intercepta los avisos `avacom-aula://` de los reproductores y cancela cualquier destino fuera del host de `BaseUri` (`block_network`); la URL de lanzamiento se usa tal cual (ya trae `?fuente=…&startTemp=-10`). El bloque `video` avisa igual que el audio cuando falla (`avacom-aula://fallo?tipo=video…`).

---

## 5 · Flujos que se pueden probar hoy

Guion de §4 de [03](03-journey-clase-de-hoy.md), con el backend en `127.0.0.1:8000` y sin AVACOM Biblioteca:

1. OPS · tablero → «Clase de hoy» → P1 muestra **Ciencias naturales** → «Estados de la materia y sus cambios».
2. P2 → tocar «Los tres estados de la materia» → «Dar clase con esta lección» → P3 con código de seis dígitos y la lámina 1 proyectada.
3. Student · menú → «Clase en vivo» → S1 → escribir el código → S2 muestra la lámina 1; en P3 «1 conectados».
4. P3 · «Siguiente ▶» dos veces → S2 sigue a las láminas 2 (imagen de marcador y lista con negritas) y 3 (video: tarjeta explicativa).
5. P3 · tocar «Escucha y repasa» → páginas con audio WAV y PDF de tres páginas.
6. P3 · tocar «Laboratorio: partículas en movimiento» → la WebView carga la simulación de marcador; S2 la carga también.
7. P3 · «Bloquear pantallas» → S2 «Mira al frente» en ≤ 3 s; «Pantallas bloqueadas · liberar» → vuelve.
8. P3 · tocar «Practica: los tres estados» → «Lanzar actividad» → tarjeta verde «0 de 1 tabletas la recibieron»; S2 muestra «Abrir», confirma y ve las seis preguntas; P3 pasa a «1 de 1».
9. P3 · «Aviso» → «Dos minutos» → banda en S2.
10. P3 · «Cerrar recepción» → «Terminar clase» → P4 con el resumen; S2 «La clase terminó».

Variante MSG-016: saltar «Cerrar recepción» → «Terminar clase» → segundo diálogo «Terminar de todos modos».

Verificación automática: `dotnet test tests/Avacom.Lms.Core.Tests` (14 pruebas). Compilación: `dotnet build src/Avacom.Lms.Ops/Avacom.Lms.Ops.csproj -f net10.0-windows10.0.19041.0` y lo mismo para Student. Con OPS abierto, añadir `-p:OutDir=<carpeta aparte>` porque el ejecutable bloquea `bin/`.

---

## 6 · Decisiones tomadas al construir

| Decisión | Por qué |
|---|---|
| Vistas construidas en C# (código) sobre XAML mínimo con contenedores nombrados | Es el estilo de `CourseContentView` y `AsignaturasPage`; permite reutilizar `Ds` y evita duplicar plantillas XAML en OPS y Student |
| Un `Ds` estático en `Avacom.Lms.Ui` en vez de un `ResourceDictionary` compartido | Las dos apps ya tienen sus `Styles.xaml`; el design system se necesita sobre todo en código y `Ds` da tipado, fábricas y el hundimiento al pulsar |
| `Sesion.FuenteAula` en OPS es una preferencia (`ops_fuente_aula`, por defecto `biblioteca`); Student no manda `fuente` | Con la API de Contenido v2 conectada ([05](05-contrato-biblioteca.md)), OPS decide la fuente sin teclado (botón «Usar el curso de ejemplo» y chip que alterna) y la tableta sigue cualquier clase: el backend resuelve la fuente por la referencia y las URL de medios ya la traen |
| `profesor_id` derivado del nombre del docente del tablero (`docente-ms-carter`) | OPS aún no inicia sesión con MOD-001; con JWT lo aporta el backend y el cliente no cambia (Q-50) |
| P3 fusiona PAN-001 y PAN-022 | El nodo es una sola pantalla táctil: proyectar y controlar ocurren en la misma superficie |
| Selección de lección + un único Primary en P2 | Un Primary por lección violaría «uno por pantalla» |
| El video del ejemplo se explica dentro de la WebView | El paquete no trae el MP4; el `<video>` dispara `error` y el HTML muestra la tarjeta sin salir a MAUI |
| Sondeo con `IDispatcherTimer` (3 s OPS, 2 s Student) | Cumple BR-049 en un aula pequeña con el backend en el mismo equipo; se retira cuando exista el WebSocket (Q-51) |
| Confirmaciones con `DisplayAlertAsync` | Un toque, texto corto, sin escritura; el kit pide una hoja de confirmación para lo destructivo |

---

## 7 · Límites conocidos y siguientes pasos

| Qué | Estado | Siguiente paso |
|---|---|---|
| Responder la actividad desde la tableta y ver la nota | Vista previa sin envío | El backend ya califica con `POST /api/aula/cursos/{ref}/evaluar/` (forma de `respuesta` por tipo en [05](05-contrato-biblioteca.md) §4); falta que MOD-010 guarde el intento (Q-48) y entonces S2 envía en vez de previsualizar |
| Desenfoque real del vidrio | Aproximado con transparencia | Handler de plataforma (Acrylic en WinUI, RenderEffect en Android) si el CTO lo pide; el kit lo desaconseja en la pantalla del aula |
| Runtime WebView2 en Windows | No verificado por el instalador | Añadir la comprobación o instalación silenciosa en `installer/` (nota de [02](02-sugerencias-frontend.md) §4.1) |
| Orientación horizontal forzada en Android para laboratorios | No implementada | `MainActivity.RequestedOrientation` mientras `LaboratorioView` esté activa |
| Video con `MediaElement` nativo | Se usa `<video>` en WebView | Evaluar `CommunityToolkit.Maui.MediaElement` cuando haya un MP4 real (Q-F1) |
| Elegir grupo y vía «Nodo del árbol» | No ofrecidas | Con MOD-002 y MOD-003 |
| Rotar código, suspender/reanudar, aviso individual, rechazar, historial | Cliente listo en `IAulaApi`; sin botón | Versión siguiente de P3 |
| Compilación Android de Student | No ejecutada en esta entrega (sólo Windows) | `dotnet build … -f net10.0-android` con un emulador o tableta |
