# Prompt · Ajustes visuales y de UX al Gradebook y al Modo Evaluación

> Para pegar tal cual en una sesión de Claude Code sobre este repositorio.
> Es autosuficiente: tokens, medidas, componentes y reglas de UX están todos aquí.

---

## 0. Misión

Lleva el **Gradebook (MOD-011)** y el **Modo Evaluación (MOD-010)** de OPS (pizarra/tablero 1920×1080) y de Student (tableta 1280×800) al lenguaje visual **«Horizonte Cristal»**, que queda definido por completo en este prompt: superficies de cristal legible, botones de cápsula con arista inferior, iconos de capas, fondos de malla suave, tipografía redondeada y legible a distancia, y un trato **no punitivo de los resultados negativos**.

Son **ajustes de presentación y de UX**. No cambian reglas de negocio, contratos de red, permisos, textos legales ni el backend. Si algo del diseño choca con una regla del proyecto (sección 2), manda la regla del proyecto y lo dejas anotado en el informe final.

El Gradebook no tiene maquetas propias: se resuelve **extrapolando** los patrones de evaluación y resultados (tarjetas, tablas de filas, anillo de promedio, píldoras de estado, hojas de opciones) que se describen abajo.

---

## 1. Alcance

**OPS — Modo Evaluación** (`src/Avacom.Lms.Ops/Pages/` y `Examen/`): `ExamenAplicarPage` (aplicar examen y niveles de control), `ExamenPanelPage` (+ `.Cabecera`, `.Filas`) panel en vivo, `ExamenResultadosPage`, `ExamenExpedientePage` (+ `.Revision`), la página de Evaluaciones del menú principal, y las hojas de opciones (bajar nivel, admitir, anular, motivo, dar más tiempo, cerrar, liberar).

**OPS — Gradebook** (`Pages/` y `Calificaciones/`): `CalificacionesPage` (+ `.Cuadricula`, `.Listas`, `.NivelDelGrupo`), `RevisionBandejaPage`, `RevisionDocentePage`, `CalificacionDetallePage` (+ `.Acciones`), `CalificacionEstudiantePage` (+ `.Boletin`), `CalificacionesConfigPage` (+ `.Editor`, `.Paises`), y los ayudantes `CalificacionesUi`, `BoletinUi`, `ExamenUi`.

**Student — Evaluación y resultados** (`src/Avacom.Lms.Student/Examen/`): `EvaluacionesPage` (lista), `ExamenAntesalaPage`, `ExamenPage` (pregunta, confirmar entrega, pausa), `ExamenEntregaPage`, `ResultadosPage` («Mis resultados» / resultado del examen), la vista de bloqueo y la tesela «Exámenes» del menú.

**Fuera de alcance:** Clase en vivo, Acceso, Estudio, Dispositivos, Reportes, Biblioteca y backend. No los toques salvo para consumir tokens compartidos. El resto de módulos se migrará después, así que **los tokens nuevos se definen en un sitio compartido** (sección 7) y no dentro de cada página.

---

## 2. Reglas del proyecto que mandan sobre este diseño

1. **OPS Master no tiene teclado.** Nada de lo que toques puede exigir escribir: se elige con toques (fichas, opciones, teclado numérico propio, motivos prehechos). Nunca propongas teclado físico ni consola al usuario.
2. **Regla de tercios.** Una pantalla de tarjeta única (aplicar examen, hojas, antesala, entrega, confirmaciones) se ancla así: tarjeta en el **tercio central en X** (bordes exactamente sobre las líneas de tercios) y de **1/6 a 5/6 en Y**. En MAUI: `Grid` con `ColumnDefinitions="*,*,*"` y `RowDefinitions="*,4*,*"`, tarjeta en la celda central con `Fill` y **sin** márgenes ni `MaximumWidthRequest`. En tableta (1280×800) las columnas son `0,25* · 3,5* · 0,25*`. Se verifica con captura de la app maximizada y una cuadrícula de tercios superpuesta, **antes** de reportar.
3. **Win2D.** En OPS (MAUI + WinUI) un `Path`, `Ellipse` o `GraphicsView` con geometría degenerada deja sin pintar todos los lienzos de la ventana. Por eso: sólo `Border`, `Label`, `Button`, `Grid`, `Image` del kit. **Nada de `Path`/`Ellipse` ni de `Path` con degradado.** Los iconos de capas se incorporan como **imágenes** (SVG → `MauiImage`, que se rasteriza al compilar), no como geometría XAML.
4. **Relieve = dos `Border` hermanos en un `Grid`.** Un `Border` recorta la sombra de su `Border` interior. La arista inferior sólida de los botones se hace con un `Border` hermano desplazado, no con `Shadow`.
5. **La tabla de calificaciones no pasa de 10 columnas visibles** (con 30 se produjo «Layout cycle detected» y OPS se cerró). Mantén las vistas «en ventana»: máximo las 10 evaluaciones más recientes, paginación «Mostrar más» y listas, no tablas, para lo masivo.
6. **Frontera LMS ↔ Biblioteca.** No edites la capa `biblioteca/` ni `FuenteDeCursos`. Los cursos y exámenes salen siempre de la biblioteca.
7. **Se conservan los `AutomationId`, los nombres de ruta, los textos de accesibilidad (`SemanticProperties`) y la lógica de `Seguro(...)`** (un toque que falla se anota y la app sigue). Las pruebas de UI Automation del repositorio dependen de ellos.
8. **Sin commit si no lo piden.** Si lo piden: autoría `ggalindo-avacom`, sin coautoría de Claude, separado en `Feature:` y `Docs:`.
9. **Instalador al día.** Al terminar, reconstruye el instalador de OPS en `installer/latest` (y Student si cambió) subiendo la versión de `installer/version.json` con su nota, según la convención del repositorio, y deja los SHA-256 en el informe.

---

## 3. Lenguaje visual «Horizonte Cristal»

### 3.1 Principios

1. **Cristal legible, no vidrio decorativo.** Las superficies son blancas al 88–96 % de opacidad con filo de luz arriba; **nunca** hay texto corrido sobre material translúcido bajo 88 %. (MAUI no tiene desenfoque de fondo: se aproxima con opacidad + filo luminoso, como ya hace `Glass.CantoLuminoso`.)
2. **Táctil y de pizarra.** OPS se lee a 4–6 m en una pizarra de 86″: **ningún texto de OPS baja de 18 px**; única excepción, las etiquetas, píldoras y cabeceras de tabla en **mayúscula mono**, que pueden bajar a 16–17 px. En Student (tableta de 10,8″) el mínimo es **15 px**. Los objetivos táctiles miden **≥ 44 px** (OPS: ≥ 46; botones de acción 54–64).
3. **Un solo Primary por pantalla** (cápsula roja). Todo lo demás es `light`, `ghost` o `text`.
4. **El color nunca es el único aviso.** Cada tono lleva siempre texto y, cuando cabe, una forma (✓, —, «II», un punto con halo).
5. **Calma.** Sin sonidos, sin parpadeos, sin alarmas ni contadores que se pongan rojos. Lo urgente se dice con ámbar sereno y con palabras.
6. **Espacio negativo generoso.** Márgenes laterales de 56 px (OPS) y 28 px (Student); una idea por tarjeta; no llenes el lienzo.
7. **Honestidad del estado.** Cargando, vacío, sin conexión, sin permiso y error tienen cada uno su tarjeta con título, frase y, si aplica, un botón para salir (`Reintentar`).

### 3.2 Color

**Tinta y superficies**

| Token | Valor | Uso |
|---|---|---|
| `tinta` | `#17204A` | Texto principal, botón ink, anillos de foco, selección |
| `tinta-2` | `#454C70` | Texto secundario legible (8,3 : 1 sobre blanco) |
| `tinta-3` | `#6E7394` | Metadatos y rótulos (4,6 : 1 sobre blanco; **no** sobre fondos tintados: ahí usa `tinta-2`) |
| `tinta-4` | `#9A9EB8` | Sólo *placeholder* y deshabilitado (2,6 : 1: nunca porta información) |
| `filo` / `filo-2` | `rgba(23,32,74,.10)` / `.16` | Líneas, contornos de campo |
| `vidrio` | `rgba(255,255,255,.88)` | Tarjeta estándar |
| `vidrio-2` | `rgba(255,255,255,.95)` | Tarjeta «solid», filas, hojas |
| `vidrio-3` | `rgba(255,255,255,.72)` | Sólo barras de cromo (no texto corrido) |
| `pozo` | `rgba(23,32,74,.045)` | Fondo de bloques de datos dentro de una tarjeta |

**Marca y semánticos** (cada tono = fondo suave + tinta oscura que contrasta ≥ 4,5 : 1)

| Tono | Color | Fondo suave | Tinta sobre el suave | Significa |
|---|---|---|---|---|
| Rojo marca | `#E3262F` (oscuro `#A8141C`, suave `#FDE7E6`) | | | Acción principal y marca. **No** significa «mal» |
| Resaltado | `#FFD23F` (oscuro `#C99A00`, suave `#FFF6D6`) | | tinta | Elemento activo/seleccionado, foco |
| Éxito | `#1E9457` (oscuro `#146A3E`) | `#E2F4EA` | `#146A3E` (5,8 : 1) | Correcto, aprobó, publicado, listo |
| Ámbar | `#E89A0C` | `#FFF1D6` | `#8A5A00` (5,3 : 1) | Pide atención o decisión; fuera de plazo; no es la respuesta esperada |
| Violeta | `#7B4DF5` | `#EEE8FE` | `#4E25C2` (7,4 : 1) | Por revisar, provisional, espera decisión |
| Cian | `#1FB6D6` (oscuro `#0E7F99`) | `#DFF4F9` | `#0B5E73` (6,4 : 1) | Informativo, pendiente, sin conexión, en pausa |
| Gris | — | `#E7E7EA` / `#F0F0F2` | `tinta` / `tinta-2` | Anulado, no empezó, sin dato, cerrado |

Reglas de contraste ya medidas: **blanco sobre `#1FB6D6` falla (2,4 : 1)** → sobre cian lleva `tinta` (6,5 : 1) o usa `#0E7F99` con blanco (4,7 : 1). Blanco sobre `#1E9457` da 3,9 : 1: sólo con texto ≥ 21 px en seminegrita (botón ok); si es más pequeño usa `#146A3E` (6,6 : 1). Blanco sobre rojo `#E3262F` da 4,6 : 1: válido para botón.

**Acentos de materia** (identifican, nunca rellenan un CTA): mate `#D95A22`, ciencias `#2B8F4C`, lenguaje `#8159CC`, inglés `#3470D6`, sociales `#1A8A82`, arte `#CF3A86`, música `#E8A21C`, ed. física `#566384`. Se ven en la insignia cuadrada de la asignatura (52–64 px, radio 16–20, número o inicial Fredoka 600 en blanco; sobre música usa tinta).

### 3.3 Fondos de malla por sección

Cada sección lleva una malla suave de cinco manchas radiales sobre un degradado vertical. En MAUI se entrega como **imagen pre-renderizada** (1920×1080 para OPS, 1280×800 para Student) detrás de todo y sin captar toques (como hoy `fondo_discos.png`), con estas paradas (cada mancha es radial `70 % × 60 %` que se funde a transparente al 70 %; la central `60 % × 55 %` al 75 %):

| Sección | Arriba-izq. | Arriba-der. | Centro (50 %, 55 %) | Abajo-izq. | Abajo-der. | Vertical (arriba → abajo) |
|---|---|---|---|---|---|---|
| **OPS · Exámenes y Calificaciones** («nieve azul») | 201,210,216 | 188,217,247 | 230,233,235 | 205,205,202 | 229,230,230 | 217,229,244 → 233,232,227 |
| **Student · Exámenes y Mis resultados** («escarcha») | 235,229,225 | 204,210,220 | 205,196,186 | 197,183,177 | 195,183,181 | 218,215,216 → 194,181,178 |

El Gradebook de OPS comparte el fondo de Exámenes (misma familia: evaluar). Fondo oscuro sólo en el bloqueo (3.8).

### 3.4 Tipografía

Fuentes (todas OFL; empaquétalas como TTF estáticos y regístralas en `ConfigureFonts` con alias, **sin negrita sintética**, como ya se hace con Inter):

| Rol | Familia y pesos | Alias sugeridos |
|---|---|---|
| Títulos, cifras grandes, botones, píldoras de Student | **Fredoka** 500 / 600 / 700 | `FredokaMedium`, `FredokaSemiBold`, `FredokaBold` |
| Cuerpo OPS | **Lexend** 400 / 500 / 600 / 700 | `LexendRegular`… |
| Cuerpo Student (primaria) | **Andika** 400 / 700 | `AndikaRegular`, `AndikaBold` |
| Datos, horas, cronómetros, cabeceras de tabla, etiquetas `eyebrow`, códigos | **JetBrains Mono** 400 / 500 / 700 | `MonoRegular`… |

- Base: **OPS 22 px** (Lexend 400, interlínea 1,45); **Student 18 px** (Andika 400, 1,45).
- Títulos: Fredoka 600, `letter-spacing ≈ −0,01 em`, interlínea 1,12. `h1`: OPS 40 px, Student 28 px (en examen 26, una sola línea). `h2` de tarjeta: 1,45 × la base; `h3`: 1,15 ×.
- `eyebrow` (sobretítulo): JetBrains Mono 700, mayúsculas, `letter-spacing 0,14 em`, rojo marca (variante `ink` en `tinta-3`). OPS ≥ 17 px; Student 13–15.
- Cabeceras de tabla y píldoras de estado: JetBrains Mono 700, mayúsculas, `0,06–0,1 em`; OPS 16–17 px (mínimo tolerado bajo 18 px, porque son mayúsculas mono; si dudas, 17), Student 13–15 px. Cabeceras en `tinta-3`.
- Cifras: porcentaje de una fila 30 px Fredoka 600; promedio en anillo 38–40 px; porcentaje del alumno 64 px; cronómetro 28 px mono 600; cifra de estadística 2,1 × la base.
- **Variante de nivel en Student:** si la tableta ya distingue primaria de secundaria, en secundaria las familias Andika/Fredoka se sustituyen por Lexend (títulos 700). Si el dato no existe, usa Andika/Fredoka y deja el punto de cambio en un solo sitio; no inventes el dato.
- Texto en español: tuteo, frase en minúscula (sentence case), sin jerga. Números en formato `es`: **coma decimal y espacio antes del %** (`62,5 %`, `1,5 de 2`, `17 de 20 puntos`). Respeta `GradebookTexto`/`ExamenTexto` y no dupliques formateadores.

### 3.5 Medidas

| | OPS (1920×1080) | Student (1280×800) |
|---|---|---|
| Barra superior | alto 104, padding lateral 56, separación 20 | alto 76, padding 28, separación 14 |
| Zona principal | padding 8 / 56 / (dock + 24) | padding 4 / 28 / (dock + 16) |
| Dock inferior | alto 92, a 16 del borde; zona reservada 118 | alto 72, a 12; zona reservada 92 |
| Tarjeta | radio 28, relleno 28 | radio 24, relleno 22 |
| Fila de lista | radio 22, relleno 16×20, separación 10 | radio 18, relleno 12×16 |
| Campo | alto 68, radio 20 | alto 56, radio 16 |
| Hoja (sheet) | radio 36, relleno 40 | radio 28, relleno 28 |
| Nota/aviso | radio 20, relleno 16×20, icono 40 | igual, más compacto |
| Pozo | radio 20, relleno 16×18 | |
| Cápsulas | radio 999 | radio 999 |

Separaciones habituales: 16 (por defecto), 10 entre filas, 18–28 entre columnas de página. Ritmo vertical entre tarjetas: 20–28.

**Elevación** (aproximaciones de MAUI `Shadow`; calíbralas contra la captura):

| Nivel | Intención | Aproximación |
|---|---|---|
| `lift-1` filas, chips | línea + sombra corta suave | offset (0,6) · radio 12 · tinta · opacidad .22 |
| `lift-2` tarjetas | línea + sombra media | offset (0,14) · radio 22 · tinta · opacidad .30 |
| `lift-3` hojas, hoja de opciones | sombra larga | offset (0,30) · radio 40 · `#0C1028` · opacidad .40 |
| `edge` (filo de luz) | 1 px blanco .95 arriba | trazo de 1 px con degradado blanco → transparente (`Glass.CantoLuminoso`) |

### 3.6 Componentes

**Tarjeta (`card`)**: vidrio + `edge` + `lift-2`. Variantes: `solid` (vidrio-2), `flat` (`lift-1`, para estadísticas dentro de otra tarjeta), `tint` (10 % del color sobre blanco .92), `ink` (tinta al 94 %, texto blanco, secundario `#B9BDD8`: banner o barra del visor). Un `pozo` agrupa datos dentro de una tarjeta.

**Botón (cápsula con arista)**: alto 64 (OPS) / 54 (Student); `lg` 76/62; `sm` 50/42; `xs` 40/34 (en OPS ≥ 46 con 18 px). Relleno horizontal = 0,45 × alto. Fuente Fredoka 600 = 0,33 × alto. Icono de 0,56 × alto a la izquierda (margen −6).

| Variante | Fondo / texto | Arista inferior | Uso |
|---|---|---|---|
| `primary` | rojo `#E3262F` / blanco | 5 px `#A8141C` + sombra roja suave | La acción de la pantalla (Aplicar examen, Publicar calificación, Entregar, Comenzar) |
| `ink` | `#17204A` / blanco | 5 px `#070B24` | Acción fuerte alterna |
| `ok` | `#1E9457` / blanco | 5 px `#146A3E` | Confirmación positiva |
| `hl` | `#FFD23F` / tinta | 5 px `#C99A00` | Activo en pestañas y dock |
| `light` | vidrio-2 / tinta, `edge` | 4 px `rgba(23,32,74,.12)` | Secundario por defecto, opciones de hoja |
| `ghost` | transparente / `tinta-2`, contorno 2 px `filo-2` | ninguna | Cancelar, **Anular** y toda acción delicada |
| `text` | texto `tinta-2`, mín. 44 de alto | ninguna | Enlaces de acción |
| `danger` | `#C8222F` / blanco | 5 px `#8A141E` | **No se usa en estas pantallas** (ver 4.1) |

Pulsado: el cuerpo baja 4 px y la arista se reduce a 1 px (≤ 120 ms). Deshabilitado: opacidad .42 y saturación .6; un botón deshabilitado **dice por qué** en una frase cercana.

**Píldora de estado (`tag`)**: alto 28 (OPS 32–34, Student 24), radio 999, JetBrains Mono 700 mayúsculas con `0,06 em` (OPS 16–17 px); neutro `rgba(23,32,74,.07)`; variantes ok / warn / info / vio / hl con los pares de 3.2.
**Ficha (`chip`)**: alto 44 (OPS 46–50 con 19 px; Student 36), vidrio-2 + `lift-1`, Lexend/Andika 600; variantes con punto (`dot` de 10 px con halo de 4 px al 22 %). Seleccionada: tinta con arista `#070B24`.
**Contador (`count`)**: círculo/píldora rojo con número Fredoka 700 (sólo para avisos que piden acción del profesor; nunca para «errores»).
**Segmentado (`seg`)**: contenedor cápsula `rgba(23,32,74,.06)` con relleno 6; activo blanco con `lift-1`. **Pestañas grandes**: contenedor vidrio-2 con relleno 7, pestaña de 62 px, Fredoka 600 de 21 px, icono 42; **activa = amarillo `hl`** con arista `#C99A00`.
**Opción (`opt`)** (ficha de elección): alto 58 (OPS) / 48, radio 999, blanco con contorno 2 px `filo-2`, 600; seleccionada = **tinta con texto blanco y arista `#070B24` en Modo Evaluación**, y **amarillo `hl` con contorno 2,5 px `#C99A00` en Calificaciones** (es una pantalla de gestión, a juego con sus pestañas amarillas). `✓` al inicio de la opción elegida.
**Campo (`in`)**: blanco, contorno 2 px `filo-2`; foco = contorno 3 px tinta + halo de 6 px `rgba(255,210,63,.55)`; ok = contorno `ok`; **error de captura** = contorno 2 px rojo y ayuda en `#A8141C` 600 que explica el rango válido. Placeholder en `tinta-4`.
**Interruptor**: 72×42, pista `rgba(23,32,74,.14)`, activo `ok`; perilla blanca de 34.
**Progreso**: barra alto 14 (Student 10), pista `rgba(23,32,74,.09)`, relleno degradado `ok → #47BE76`. **Pasos**: segmentos de 12 px (`ok`, `now` = amarillo con contorno `#C99A00`). **Anillo**: cónico, 120–180 px, interior blanco al 76 %, cifra Fredoka 600 centrada; color `ok` en el promedio.
**Estadística (`stat`)**: cifra Fredoka 600 (2,1 × base, coloreable con `--c`) y rótulo de `tinta-3` (≥ 18 px en OPS). Con valor 0 se atenúa a 55 % **sin desaparecer**.
**Fila de lista (`li`/`rr`)**: vidrio-2 + `edge` + `lift-1`; seleccionada = contorno interior 3 px tinta; resaltada = contorno 3 px `#C99A00` sobre `#FFF6D6`; atenuada = opacidad .6; chevrón de 12 px al final cuando abre otra pantalla.
**Tabla de filas**: cabecera mono (ver 3.4) sin fondo; cada fila es una tarjeta baja (radio 20, alto mínimo 84 en resultados, relleno 14×22) con columnas definidas por `Grid`; filas con estado: ámbar `#FFF4DC`/`#FFF1D6`, violeta `#EEE8FE`, abierta `#FFF6D6` con contorno 3 px `#C99A00`. Esquinas redondas por fila, nunca tabla de celdas con rejilla.
**Aviso (`note`)**: fondo suave del tono, sin borde, icono de capas a la izquierda, título en seminegrita y frase debajo. Los de buenas noticias o informativos se quitan solos a los 9 s; los ámbar se quedan.
**Hoja (`sheet`) y velo**: velo `rgba(23,32,74,.38)`; hoja vidrio-2, radio 36, `lift-3`, acciones alineadas a la derecha con separación 14. La **hoja de opciones** mide 640 px (tercio central), cada opción es un botón `light lg` a todo el ancho y «Cancelar» es `ghost`; **tocar una opción ES la confirmación**; tocar fuera o Cancelar no cambia nada.
**Toast**: cápsula de tinta con texto blanco, arriba al centro (24 px), icono de 44.
**Dock**: cápsula vidrio-2; el elemento activo es amarillo `hl` con arista; el principal («Clase de hoy» / «Clase en vivo») es rojo; en examen el dock de Student se **bloquea** (opacidad .32) y muestra una píldora amarilla «Examen en curso · navegación bloqueada».
**Estado vacío**: centrado, icono de capas, `h2` 1,5 × base, frase en `tinta-3` (máx. 34 em) y, si aplica, un botón.
**Burbuja de mensaje (Student)**: radio 24/24/6/24, vidrio-2 + `lift-2`, Fredoka 600; mensajes cortos y amables («¡Tú puedes! Lee con calma.»). Si el personaje (Hexi) no existe en la app, **no lo dibujes**: deja sólo la burbuja y anota el hueco.

### 3.7 Iconografía de capas

Cada icono es una pieza cuadrada de 100×100 con tres capas: **(1)** sombra de suelo elíptica (`rx 32 ry 6` al pie, radial del color del icono al 45 % → 0), **(2)** cuerpo con degradado diagonal de dos tonos del mismo color (claro arriba-izquierda → oscuro abajo-derecha) y **(3)** detalles blancos de trazo redondeado (7 px, extremos redondos). Una paleta por concepto (examen violeta `#B48CFF → #6A3FD8`, escudo/aviso coral `#FF8A6B → #D9442F`, mundo/red azul `#3FB0FF → #1E6FD8`, perfil rosa `#FFB0CC → #CF3A86`, éxito verde, reloj, candado, gráfica, libros, tableta, grupo…). Tamaños: 56 (fila), 40–48 (botón y nota), 34 (campo), 30 (opción), 22 (píldora). **Se entregan como SVG en `Resources/Images` (`MauiImage`)**; ya existen los `reportes_*.svg` como referencia de manejo. Marca de verificación y equis de resultados se dibujan con **rectángulos rotados** (bordes de 3 px), no con `Path`.

### 3.8 Marca, negativo de marca y superficies oscuras

- **Logotipo**: el horizontal (palabra AVACOM con sus colores de marca `#E5262B`, `#C82230`, `#F3C701`, `#019D60`, `#01A4E1`, `#A81D81`) en cabeceras de acceso/menú; el cubo (`mark`) dentro de un círculo blanco de 74 px a la izquierda del dock; el anillo como marca de agua a 85–90 % de opacidad. **En las pantallas de evaluación y calificaciones el logotipo no se repite en la barra superior**: la identidad la dan el dock y el color.
- **Negativo de marca**: sobre fondo oscuro o saturado el logotipo se usa en **versión monocroma blanca al 90 %** (la palabra completa, nunca recoloreada a medias ni con un solo color de la paleta). Genera `logo_horizontal_blanco` (y `mark` blanco) como activos SVG; no uses filtros en caliente. Respeta el área de respeto de una «A» alrededor y una altura mínima de 38 px en OPS.
- **Superficies oscuras permitidas** (sólo estas): barra de visor/banner `tinta` al 94 % (texto blanco; secundario `#B9BDD8` 8,4 : 1), toast de tinta, y **pantalla de bloqueo del examen** (`#141417`, título blanco de 64 px, frase `#C9CCE0` 11,5 : 1, halo cian muy suave detrás del icono, dock bloqueado visible). Sobre oscuro: acento `#FFD23F` (12,7 : 1) para sobretítulos, `#BDE9D0` (13,8 : 1) para confirmaciones. **No hay tema oscuro global** en estas pantallas.

### 3.9 Movimiento y estados

Transiciones de 100–150 ms (el pulsado de un botón). Auto-refresco **sin saltos**: el contenido no se reordena bajo el dedo (se reordena sólo en el refresco, y la fila que se está tocando se queda). Si el sistema pide reducir movimiento, anula animaciones. Foco visible: en un campo, contorno de 3 px tinta con halo amarillo de 6 px; en cualquier otro control, contorno de 3 px tinta con separación de 2 px.

---

## 4. Manejo de los negativos

Se entiende en cuatro sentidos; resuélvelos todos.

### 4.1 Resultados y estados negativos (lo más importante)

**Principio: un resultado negativo es información para actuar, no un castigo. Ningún estado de rendimiento se pinta de rojo.** El rojo es **marca y acción principal** (más el error de captura de un campo y el código de unión equivocado). Ni «No aprobó», ni «0 de 2», ni «Fuera de plazo», ni una tableta sin señal llevan rojo, ni suenan, ni parpadean. No uses la variante `danger` en estas pantallas: el peso de una decisión irreversible lo lleva la **hoja de confirmación** y su texto, no el color.

| Situación | Tono | Forma | Texto modelo |
|---|---|---|---|
| Correcto / aprobó / publicado | Éxito | píldora `ok` + ✓ | «Aprobó» · «Correcta · 1 de 1» |
| No aprobó (vista del profesor) | **Neutro** (gris) | píldora gris; la cifra va en tinta normal | «No aprobó» |
| No llegó al mínimo (vista del alumno) | Ámbar suave | píldora ámbar, frase en primera persona **y siguiente paso** | «Todavía no llegas al 60 % que pide el examen» |
| Respuesta incorrecta | Ámbar suave | caja `#FFF1D6` + marca ✕ fina + «Revisar», con pista cuando exista | «No es la respuesta esperada · 0 de 2» · «Revisa el signo: al pasar −4 al otro lado se suma.» |
| Por revisar / provisional | Violeta | píldora violeta + «provisional» bajo la cifra | «Por revisar» · «62,5 % provisional» |
| Pendiente de calificar (el alumno espera) | Cian | caja cian + glifo «…» | «Tu profesor lo revisará» |
| Sin responder / sin nota / no empezó | Gris | «—» (no «0») | «Sin responder» · «Todavía no empieza» |
| Fuera de plazo · envío tardío · con avisos | Ámbar | píldora ámbar; la decisión es del profesor, con botones | «Fuera de plazo» · «Respondió a tiempo, pero su tableta lo mandó después de la gracia. ¿Cuenta?» |
| Necesita al profesor (suspendido, admisión) | Ámbar con fondo de fila `rgba(255,241,214,.97)` | fila al principio de la lista | «2 alumnos esperan que los reactives» |
| Decisión pendiente (admitir, rechazar) | Violeta, fondo de fila `rgba(238,232,254,.97)` | | «Esperando tu decisión» |
| Anulado | Gris `#E7E7EA` | banner gris con nombre y motivo | «Anulado por Ms. Carter · Falla técnica que impidió presentar con normalidad» |
| Sin conexión · en pausa | Cian | nota cian; tranquiliza | «Tus respuestas no se pierden» · «Tu examen está en pausa» |
| Error al leer del nodo | Ámbar | nota ámbar + `Reintentar` | «No se pudieron leer tus grupos» |
| Captura fuera de rango (campo) | Rojo del **campo** | contorno rojo + ayuda `#A8141C` | «Escribe un valor entre 0 y 100» |

**Reglas de redacción:** nombra lo que pasó y lo que se puede hacer; en positivo («Todavía no…», «Aún falta…»); nunca «Reprobado», «Fallaste», «Error», «Incorrecto» como etiqueta de una persona; al alumno se le habla de **tú**, al profesor se le informa sin juzgar al alumno. Sin ranking entre alumnos ni nombres de otros alumnos en la vista del alumno. **Sin promedio de grupo con menos de 3 calificados** («Con menos de 3 entregas no se calcula un promedio» / «Un promedio de uno o dos alumnos dejaría ver a cada persona; por eso se espera a tener tres.»). Lo provisional se marca siempre.

**Acciones irreversibles** (anular un intento, cerrar el examen): botón `ghost` (nunca `danger`), hoja con la frase «Es la única decisión que no se puede deshacer. Quedará registrado que la tomaste tú, con tu nombre y este motivo.», **motivos prehechos como botones** (sin teclado), «Otro motivo (se registra sin detalle)» y `Cancelar`. El sistema nunca anula solo.

### 4.2 Números negativos y diferencias

Signo menos tipográfico **«−»** (U+2212), no guion; cifras en JetBrains Mono (anchura fija) en columnas de diferencias para que se alineen; la dirección se dice también con palabra o forma («−5 pts», «subió 3 pts»), no sólo con color; sin rojo por defecto (neutro si baja, `ok` suave sólo si el cambio es una mejora que importa). Cero ≠ vacío: **«0» es un valor; «—» es ausencia de dato**; una nota sin registrar no se pinta como 0. Un total en cero se atenúa pero conserva su sitio.

### 4.3 Negativo de marca y superficies oscuras

Ver 3.8: logotipo monocromo blanco al 90 % sobre fondos oscuros o saturados y las tres superficies oscuras permitidas, con los pares de contraste ya medidos.

### 4.4 Espacio negativo

Respira: márgenes de 56/28 px, tarjeta única anclada a tercios con el resto del lienzo libre, una sola tarjeta de mensaje cuando no hay datos, listas con 10 px entre filas y tarjetas con 20–28 px entre sí. Antes de añadir un elemento, quita otro. Una pantalla de OPS no muestra más de tres columnas de tarjetas ni más de un Primary.

---

## 5. UX transversal

- **Jerarquía en tres niveles:** (1) la pregunta de la pantalla en el título; (2) el estado y los totales arriba; (3) el detalle debajo. El Primary va **abajo a la derecha** de su tarjeta (o en la cabecera si la pantalla es de lista).
- **Progreso visible:** examen = barra + «2 de 12 contestadas» + mapa de preguntas; calificar = «N por revisar» como contador en la cabecera.
- **Siempre se puede salir:** botón `Volver` (píldora de 56 px, flecha de 12 px con trazo de 3) arriba a la izquierda; en examen en curso la navegación del sistema está bloqueada y el dock lo dice.
- **Autoguardado explícito:** píldora «Guardado» con ✓ cian en la cabecera del examen; si se pierde la señal, «Tus respuestas se guardan en esta tableta y se enviarán solas».
- **Cronómetro:** reloj mono 28 px en una cápsula de 58 px; con tiempo detenido pasa a ámbar suave y dice «tiempo detenido».
- **Panel en vivo = panel de continuidad, no de vigilancia:** una fila por alumno en el orden que manda el nodo (primero quien necesita al profesor, luego en curso, al final entregados; nunca alfabético); se refresca cada 3 s sin sonidos ni parpadeos; los avisos de fila se quitan solos a los 9 s.
- **Honestidad:** nada se muestra como definitivo si es provisional; un botón deshabilitado explica el motivo («Los resultados se pueden liberar cuando nadie siga presentando.»).
- **Táctil puro:** dos toques máximo para elegir una opción; fichas en lugar de campos; teclado numérico propio (`TecladoPinView`) cuando haga falta escribir un número.
- **Accesibilidad:** `SemanticProperties` en todo control sin etiqueta visible, orden de lectura coherente, contraste ≥ 4,5 : 1 en texto normal y ≥ 3 : 1 en texto grande, foco visible.

---

## 6. Aplicación pantalla por pantalla

Las medidas son de OPS 1920×1080 salvo que diga Student (1280×800). Ajusta con el mismo criterio si la ventana es menor, pero verifica siempre en el tamaño nominal.

### 6.1 OPS · Aplicar examen

Tarjeta única anclada a tercios. Cabecera: `Volver a la clase`, título y subtítulo (examen · materia), usuario (avatar circular de 56 con iniciales). Cuerpo:
- **Nivel de control** como tres tarjetas en fila (separación 18): icono de capas 56, `h3` 30, frase de 19 px y, abajo, una línea discontinua de 2 px con «Tú verás: …». Seleccionada: contorno 4 px tinta + fondo `#FFF6D6` + píldora «✓ Elegido». **Ninguno viene preseleccionado** y `Aplicar examen` queda deshabilitado (.5) con la frase «Primero elige el nivel de control».
- **Ajustes** en tarjeta de dos columnas: Tiempo, Fecha límite, Intentos, Resultados, «Si un alumno se queda sin señal» y «¿A qué grupo?» como filas «rótulo + ayuda + fichas `opt` de 50 px / 18 px»; la primera (Tiempo) ocupa las dos columnas. Todo se elige con toques.
- **Elegibilidad** (después de elegir nivel): nota ámbar «2 tabletas no alcanzan para el nivel controlado» con la lista de alumnos y «No bloquea». Otras variantes: «Cualquier tableta sirve para un examen abierto», «24 tabletas alcanzan este nivel».
- Pie: `Cancelar` (`ghost`) + `Aplicar examen` (primary) y la frase «Se aplicará a 6° A (28 alumnos) · nivel Controlado».

### 6.2 OPS · Panel del examen en vivo

Rejilla `350 | resto`, con tira de **7 totales** arriba (cifra Fredoka 34 + rótulo de 18; fondos ámbar para «esperan reactivación» y violeta para «esperan admisión»; el 0 se atenúa sin desaparecer). Columna izquierda: tarjeta «Acciones del examen» (botones `light`/`ghost` de 52, alineados a la izquierda con icono 34: Dar más tiempo, Endurecer el plazo, Bajar el nivel, Cerrar el examen, Liberar resultados) y los datos fijos del examen (nivel, cierre, plazo blando, quién reactiva, quién libera) como fichas. Columna derecha: dos notas en fila (por ejemplo «2 alumnos esperan que los reactives» con `Reactivar a todos (2)`, y «2 tabletas no alcanzan el nivel controlado») y debajo las filas `er` (radio 18, vidrio-2, rejilla `390 | 1fr | 170 | 165 | 150 | 20`, alto mínimo 50): nombre con avatar, tableta, **ficha de estado** (`stp`, radio 12, 18 px: ok / ámbar / violeta / info / neutro), progreso «3 de 4», reloj mono 22 «12:05 restante», avisos «1 aviso». Fila que necesita al profesor = fondo ámbar suave con detalle desplegado (línea discontinua + botones `xs` de 46); fila que espera decisión = violeta suave. **No hay botón «Anular» en el panel.** `Ver resultados` es `light` en la cabecera.

### 6.3 OPS · Resultados del examen

Rejilla `480 | 1fr`. Izquierda, tarjeta `solid`: **anillo de 150 px** con el promedio (color `ok`; con < 3 calificados se reemplaza por la nota de privacidad), «de 3 alumnos calificados», cuatro estadísticas en tarjetas `flat` (entregaron · calificados · aprobaron en verde · por revisar en violeta) y dos notas: cian «Todavía no los ven» y violeta «Provisional». Derecha: rótulo «Alumno por alumno · toca una fila para abrir su expediente», cabecera mono y filas `rr` (alto mín. 84, rejilla `270 | 250 | 160 | 160 | 200 | 1fr | 20`): nombre 21 px, píldora de estado (Calificado verde / Por revisar violeta / Anulado, Todavía no empieza en gris), **porcentaje 30 px**, «¿Aprobó?» (`Aprobó` verde; `No aprobó` **gris neutro**), «Fuera de plazo» ámbar, avisos en texto, chevrón. Actualización cada 8 s.

### 6.4 OPS · Expediente del intento

Tres columnas `520 | 1fr | 450`. Cabecera: nombre, «Expediente del intento · Intento 1 · 6° A» y píldoras de estado (violeta «Entregó · por revisar», neutro «Nivel Controlado», ámbar «Calificación pendiente», ámbar «2 avisos»). Columna 1: «Resumen» en pozo con renglones `rótulo | valor` separados por 2 px (19 px) y «Bloqueo de la tableta» con sus «Sí». Columna 2: «Lo que pasó» como **línea de tiempo** (hora mono 19, punto de 18 con halo de 5 px: gris informativa, ámbar atención) y «Respuestas del alumno» (cada una: enunciado 20 px 600, tipo y valor, respuesta en caja blanca con contorno, resultado «Correcta · 1 de 1» o «No es la respuesta esperada · 0 de 1» en su tono; la abierta ofrece fichas **0 / 25 % / 50 % / 75 % / 100 %**, la elegida con ✓ y «Puntaje actual: 1,5 de 2»). Columna 3: «Qué puedes hacer con este intento»: `Revisar respuestas` (light), `Publicar calificación` (**primary**; con reactivos sin puntuar muestra el aviso «Todavía no se puede publicar»), y `Anular este intento` (**ghost**). Banner gris `#E7E7EA` cuando está anulado.

### 6.5 OPS · Hojas de opciones

Mismo molde para bajar nivel, admitir, anular, dar más tiempo, cerrar y liberar: velo + hoja de 640 en el tercio central, título (Fredoka 600), frase de consecuencia («Es un cambio de todo el examen y no se puede volver a subir…»), opciones `light lg` a ancho completo con motivos prehechos, `Cancelar` ghost. Tocar una opción confirma; después un aviso de 9 s («Valentina Ruiz puede entrar»).

### 6.6 OPS · Gradebook (extrapolado de 6.3 y 6.4)

- **Cabecera**: `Volver`, título (40) «Calificaciones», subtítulo con grupo y periodo, **ficha con el sistema de calificación del país** («De 1 a 5 · Se aprueba con 3 o más») y avatar del usuario. `Sistema de calificación` y `Registrar lo calificado (N)` son botones `light`; sólo uno es Primary según el estado (en modo simple, «Sistema de calificación»).
- **Selector de vista** (Estudiantes · Evaluaciones · Tabla) como **pestañas grandes** (activa amarilla). Filtros (grupo, periodo, materia) como fichas `opt`; sin teclado.
- **Lista de estudiantes**: filas `rr` (avatar 56, nombre, píldora de estado, **nota 30 px** y su rótulo según el sistema del país, mini-barra de progreso de 14 px, chevrón) con orden elegible y «Mostrar más». Lo masivo va en listas, no en tabla.
- **Tabla** (máx. 10 columnas): cabecera mono; celda de nota = cifra Fredoka 600 + píldora diminuta; «—» para sin registro (no 0); celdas provisionales con violeta; **sin colorear en rojo las notas bajas** (tinta normal + píldora neutra «No aprobó»).
- **Boletín del estudiante**: columna izquierda `solid` con anillo de promedio de 150 y sistema de notas; centro con cursos (insignia de asignatura de 52–64 con su acento, nota y barra) e **insights** («Tendencia», «Mejor curso», «Curso a reforzar», «Constancia», «Comentarios») en pozos con icono de capas y frase amable (el curso a reforzar es ámbar suave, nunca rojo); derecha con evaluaciones recientes y «Mostrar más». Aspecto de boletín: hoja blanca de contorno 2 px, rótulos mono, cifras Fredoka.
- **Revisión docente / bandeja**: fila por intento con píldora violeta «Por revisar»; en la revisión, fichas de puntaje 0–100 % (como 6.4) y `Publicar` primary; el ajuste de una nota pide **motivo** con opciones prehechas y deja «valor anterior → valor nuevo» a la vista.
- **Detalle de calificación y ajustes**: pozo de «Resumen» (rótulo/valor), línea de tiempo de versiones (punto gris, ámbar para ajuste manual), `Reabrir`/`Retirar publicación` en `ghost` con hoja de confirmación.
- **Configuración del sistema por país**: país → sistema → niveles → «Usar en N niveles» como un recorrido de **pasos** (segmentos de 12 px, el actual en amarillo), tarjetas seleccionables `sel-card` (seleccionada = fondo `#FFF6D6` y contorno 3,5 px `#C99A00`, marca ✓ arriba a la derecha) y una nota ámbar «plantillas orientativas, no verificadas con la normativa».
- Tarjeta «Este grupo no tiene nivel educativo» y avisos de «sin acceso»/«no se pudo leer» = tarjetas de estado de 3.6 con `Reintentar`.

### 6.7 Student · Mis evaluaciones (lista)

Barra sin fondo: `‹ Menú` (píldora de 46), título 28, y —sólo en modo prototipo— «Presentas como … · ¿No eres tú? Toca aquí». Cuerpo máx. 960 centrado, dos bloques: «Para presentar» y «Presentadas hace poco» (se actualiza sola cada 5 s). **Tarjeta de examen**: icono de capas 52, título 20 (600), meta 15 («Álgebra Octavo B · 12 preguntas · hasta hoy 10:30»), **píldoras de nivel** (neutras) y **de estado** (Abierto verde · Abierto fuera de plazo ámbar · Aún no abre / Cerrado gris), una frase («Lee las condiciones antes de empezar», «Ya puedes ver tu resultado», «Tu examen está en pausa: avisa a tu profesor», «Tu profesor publicará tu calificación») y un botón de 170×60 **sólo si hay acción** (Comenzar · Continuar · Ver resultado). Vacío/sin conexión/visitante = tarjeta de mensaje (radio 20, relleno 28×40, título 23 + frase 17 centradas).

### 6.8 Student · Antesala

Tarjeta anclada a tercios (tableta: columnas `0,25* · 3,5* · 0,25*`; filas `*,4*,*`). Rejilla `440 | 1fr`: resumen con **tres datos** (12 preguntas · 45 min · Único intento; cifra Fredoka 24 sobre pozo, rótulo 15), «Fecha límite: hoy 10:30» y burbuja «¡Tú puedes! Lee con calma.»; a la derecha, el nivel («Examen controlado» + frase), «Qué se registra» con ✓ y el bloqueo de la tableta. `Comenzar` (primary `lg`, 62) al final; si el estado impide empezar («Esperando que tu profesor decida sobre esta tableta», «Este examen todavía no abre»), `Comenzar` se oculta y el estado se dice en una frase centrada de 16 px. Si la tableta no cumple, nota ámbar «Tu tableta no cumple lo que pide este examen… No pierdes nada».

### 6.9 Student · Examen en curso

Pantalla completa, sin dock navegable. **Barra**: icono de 50, título (26, una línea) + subtítulo (15) «Álgebra Octavo B · Examen controlado», píldora **«✓ Guardado»** (cian) y reloj `clk` (58, mono 28, «te quedan»; detenido = ámbar suave). **Raíl izquierdo de 300**: «Tu examen», «Pregunta 3 de 12», barra, «2 de 12 contestadas», **mapa de 4 columnas × 56 px** (radio 16, 21 px): actual = tinta con arista; contestada = cian suave + contorno cian + ✓; marcada = estrella amarilla en la esquina; **sin responder (al confirmar) = ámbar suave con contorno 3 px**; leyenda de 15 px. **Tarjeta de pregunta**: `Pregunta 3 de 12` + `Marcar para revisar` (`xs` 42), franja de instrucción cian suave, **enunciado 30 px/1,25**, respuestas de 64 px mín. (radio 20, letra en círculo de 46, 24 px; elegida = fondo cian suave + contorno 3 px tinta + letra invertida), V/F en dos losas grandes de 170 px con glifo de 72 (✓ verde, ✕ rojo suave: **es el glifo de la opción, no un resultado**), completar con hueco discontinuo, relacionar con columnas y conector, ordenar con flechas de 56×52, abierta con área de 170 px con foco amarillo. Pie: `Anterior` (ghost) · `Siguiente` (primary) · `Entregar`.
**Confirmar entrega** (en lugar de la pregunta): «Antes de entregar» / «Te faltan 3 preguntas. Puedes entregar igual.» + «Sin responder: 2 · 5 · 9»; `Volver` (light) y `Entregar igual` (primary). **Pausa**: círculo cian de 84 con dos barras, «Tu examen está en pausa» + «No necesitas hacer nada más: cuando tu profesor te reactive, sigues justo donde ibas.»

### 6.10 Student · Entrega y resultado

**Entregado**: círculo `ok` suave de 84 con ✓ (rectángulo rotado), «Tu examen quedó entregado», origen opcional («Se acabó el tiempo y tu examen se entregó solo. Lo que respondiste está guardado.»), «Tu profesor publicará los resultados.» y `Ver mi resultado` sólo si ya hay resultado. **Resultado / Mis resultados**: rejilla `300 | 1fr`. Izquierda: **porcentaje de 64 px**, píldora «Aprobado» (verde) **o** «Todavía no llegas al 60 % que pide el examen» (ámbar suave), «17 de 20 puntos», sistema de calificación del país y burbuja de ánimo («¡Bien hecho! Revisa la pregunta 4.»). Derecha: «Pregunta por pregunta» en **losas de dos columnas** (radio 14, alto mín. 46): Bien `#E2F4EA` con ✓ · Revisar `#FFF1D6` con ✕ de `#B5720A` y la pista · Pendiente cian con «…» · Sin responder gris con «—»; leyenda de 15 px arriba; comentarios del profesor como línea secundaria. «No disponible»: «Tu profesor aún no publica los resultados / Cuando lo haga, podrás verlos aquí.»

### 6.11 Student · Bloqueo

`#141417`, icono de ojo con halo cian, «Mira al frente» (64, blanco) y «Tu profesor está explicando. Tu trabajo sigue guardado.» (`#C9CCE0`). Sin botones ni cuenta atrás; dock bloqueado con la píldora amarilla.

---

## 7. Cómo llevarlo a MAUI

1. **Tokens compartidos.** Crea (o extiende) un único lugar —un `Cristal`/`Horizonte` estático en `Avacom.Lms.Ui.Design`, junto a `Ds` y `Glass`, y su espejo en los `Colors.xaml` de Ops y Student— con: colores de 3.2, radios de 3.5, sombras de 3.5, fuentes de 3.4 y fábricas (`Tarjeta`, `Cápsula`, `Píldora`, `Ficha`, `Opción`, `Nota`, `Hoja`, `Fila`, `Estadística`, `Anillo`). Los `Tono` de `ExamenUi` y `Matiz` de `CalificacionesUi` siguen siendo la API de las pantallas: sólo cambian los **colores** que devuelven (3.2).
2. **No duples.** Reutiliza `ExamenUi`, `CalificacionesUi`, `BoletinUi`, `Ds`, `Glass`, `TecladoPinView`. Si una fábrica de `Ds` cambia de aspecto para estas pantallas, hazlo **parametrizable** para no mover el resto de módulos todavía.
3. **Botón con arista:** `Grid` de dos `Border` hermanos (la arista de color oscuro desplazada 5 px y el cuerpo encima); al pulsar, el cuerpo baja 4 px y la arista queda en 1 px. Mantén el hundimiento (escala 0,96) que ya existe sólo como respaldo.
4. **Cristal:** blanco con alfa (`#E0FFFFFF` ≈ .88, `#F2FFFFFF` ≈ .95) + trazo de 1 px con `CantoLuminoso`; sin `Path`, sin desenfoque.
5. **Fuentes:** añade los TTF de Fredoka, Lexend, Andika y JetBrains Mono (con su licencia) a `Resources/Fonts` de Ops y Student y regístralos; quita el uso de Inter **sólo** en estas pantallas.
6. **Iconos:** SVG de capas en `Resources/Images` como `MauiImage`; marcas ✓ y ✕ con rectángulos rotados.
7. **Fondos:** imágenes pre-renderizadas de 3.3, `Aspect=AspectFill`, `InputTransparent=true`, detrás de todo.
8. **Rendimiento:** la mayoría de las pantallas se redibuja cada 3–8 s. No recrees el árbol entero en cada refresco: actualiza lo que cambió, conserva el desplazamiento y el foco. Con 28–35 alumnos y 10 columnas, la pantalla debe seguir fluida en el hardware del tablero.
9. **Sin lógica nueva.** Los textos de estado salen de `ExamenTexto`/`GradebookTexto`/`FrasesDeCalificaciones`; si añades una frase, ponla ahí. Todo se redacta en positivo (4.1).

---

## 8. Criterios de aceptación y verificación

1. **Compilan** OPS y Student sin avisos nuevos y **pasan las pruebas existentes** (`dotnet test` de `Core.Tests`, `Ops.Tests`, `Student.Tests`; actualiza las que verifiquen colores o textos que cambiaron). El backend no se toca; si lo corres, que pase `pytest` de `gradebook` y `evaluacion` sin cambios.
2. **Capturas reales** de cada pantalla de la sección 6, en OPS maximizada a 1920×1080 y en Student a 1280×800 (y una tableta de 10,8″), en cada estado relevante: vacío, cargando, error, sin conexión, sin permiso, provisional, aprobado, no aprobado, anulado, fuera de plazo, pausa, bloqueo. Usa un nodo de prueba aislado (puerto 8010, base temporal, sin tocar las preferencias ni el escritorio del usuario) y UI Automation por `AutomationId`.
3. **Tercios**: superpón la cuadrícula en las pantallas de tarjeta única; la tarjeta debe encajar con las líneas de tercios en X y de 1/6 a 5/6 en Y.
4. **Negativos**: busca en el código y en las capturas que **no queda rojo** en ningún estado de rendimiento (`rg "Peligro|Danger|#C8222F|#E5262B|Rojo"` en las páginas del alcance debe mostrar sólo el Primary, el error de campo y la marca); `0` y `—` se distinguen; las notas bajas no se pintan; el logotipo sobre oscuro es la versión blanca.
5. **Contraste**: cada par texto/fondo de las pantallas cumple ≥ 4,5 : 1 (≥ 3 : 1 en texto grande). Comprueba especialmente: blanco sobre cian (no debe existir), `tinta-3` sobre pozos (usa `tinta-2`) y los ámbar.
6. **Legibilidad**: ningún texto de OPS < 18 px (salvo etiquetas, píldoras y cabeceras en mayúscula mono ≥ 16) ni de Student < 15 px (salvo esas mismas etiquetas ≥ 13); objetivos táctiles ≥ 44 px.
7. **Táctil**: recorre cada flujo sin teclado.
8. **Estabilidad**: abre y cierra cada pantalla 20 veces seguidas y recorre la tabla de 30 evaluaciones sin que OPS se cierre ni aparezca «Layout cycle» ni `0x88990011` en `%LOCALAPPDATA%\AVACOM\lms\fallos-ops.log`.
9. **Sin regresiones** de comportamiento: mismas rutas, mismos `AutomationId`, mismas llamadas a la API, mismos permisos.

---

## 9. Entrega

- Cambios sin commitear (salvo petición) y un **informe breve**: qué pantallas se tocaron; capturas antes/después de las seis más representativas (aplicar, panel, expediente, libro, antesala/examen, resultado); decisiones que tomaste donde este prompt no alcanza (y por qué); qué **no pudiste probar** (tableta física, kiosco, APK, 300 evaluaciones, rol real con sesión); fuentes y licencias añadidas; y los SHA-256 de los instaladores reconstruidos.
- Documenta el lenguaje en `spec-driven/12-gradebook/` y `spec-driven/06-evaluation-delivery/` (una sección «Lenguaje visual» con los tokens y la matriz de negativos), sin duplicar lo que ya está en el diseño del módulo.
- **No tomes por tu cuenta**: cambiar umbrales de aprobación, escalas, políticas de publicación, textos legales ni la lógica de privacidad (promedio con < 3). Si crees que alguno debe cambiar, déjalo como pregunta al final del informe.
