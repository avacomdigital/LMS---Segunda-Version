# Escenarios de QA · Happy Path 01

Desglose de los cuatro caminos de [happy-path-01.md](happy-path-01.md) en escenarios de prueba. Cada escenario trae **entradas esperadas**, **salidas esperadas**, **pasos** y una columna de **resultados vacía** para llenarla al ejecutar y mostrarla en una tabla.

| Campo | Valor |
|---|---|
| Semana | 5 al 9 de octubre de 2026 |
| Preparación común | Sección 4 de `happy-path-01.md` (Contenido abierto, nodo de QA, OPS y Student desde `main`, personas y tabletas) |
| Estado de cada paso | `OK` · `FALLA` (anota el QA-nn si ya es conocido) · `BLOQ` (no se pudo probar) · `N/A` |
| Datos de prueba | Grupos **Quinto A** (Ana, Beto, Carla) y **Sexto B** (Diego). Tabletas **T-A** (asignada a Ana) y **T-C** (compartida). Curso: *Estados de la materia y sus cambios* |

**Índice:** HP-01 (ESC-01-01 a 08) · HP-02 (ESC-02-01 a 07) · HP-03 (ESC-03-01 a 06) · HP-04 (ESC-04-01 a 07) · [Transversal: red y carga con 25 a 35 tabletas (ESC-05-01)](#transversal--red-y-carga) · [Tabla consolidada de resultados](#tabla-consolidada-de-resultados)

---

## HP-01 · Clase completa

### ESC-01-01 · Abrir la clase y entrada de alumnos

| Entradas esperadas | Salidas esperadas |
|---|---|
| Contenido abierto y nodo en marcha. OPS en el tablero. Student A conectado al aula. Curso *Estados de la materia*, lección 1 | OPS muestra «Biblioteca conectada», la lección 1 con 4 objetos y la lección 2 con 3 (sin examen), y un código de 6 dígitos. El alumno entra con ese código y OPS muestra «1 conectados» en 3 s o menos. Un código malo da «Ese código no es» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Clase de hoy» | Chip «Biblioteca conectada» y cursos por materia | | |
| 2 | OPS: «Ciencias naturales» → *Estados de la materia…* → «Ver lecciones ›» | Lección 1 con 4 objetos, lección 2 con 3. No hay lección de examen | | |
| 3 | OPS: lección 1 → «Dar clase con esta lección» | Código de 6 dígitos («CÓDIGO DE UNIÓN · TOCA PARA AMPLIAR») | | |
| 4 | Student A: «Clase en vivo» → escribir un código equivocado | «Ese código no es» | | |
| 5 | Student A: escribir el código correcto → «Entrar a la clase» | Entra; OPS muestra «1 conectados» en ≤ 3 s | | |
| 6 | OPS: iniciar otra clase con el mismo profesor | Aviso «Ya tienes una clase abierta» con opción de continuar o cerrarla | | |

### ESC-01-02 · Presentación (láminas)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Clase abierta con Student A dentro. Objeto «presentación» de la lección 1 (7 láminas) | Cada lámina muestra título, texto, lista, imagen y video según corresponda, en OPS y en Student. Student replica el cambio en 3 s o menos |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: abrir la presentación | «Lámina 1 de 7» en OPS y en Student | | |
| 2 | OPS: avanzar con ▶ por las 7 láminas | Cada lámina se ve completa; imágenes cargan | | |
| 3 | OPS: llegar a la lámina con video y reproducirlo | El video se ve entero y se puede saltar a otro punto | | |
| 4 | Student A: comprobar cada cambio | Replica la lámina de OPS en ≤ 3 s | | |

### ESC-01-03 · Lectura con audio, video y PDF

| Entradas esperadas | Salidas esperadas |
|---|---|
| Objeto «lectura» de la lección 1 (4 páginas) | Suena el audio, se reproduce el video y el PDF se abre, en OPS y en Student |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: abrir la lectura | «Página 1 de 4» | | |
| 2 | OPS: reproducir el audio | Se oye; si falla, mensaje claro | | |
| 3 | OPS: reproducir el video | Se ve y avanza | | |
| 4 | OPS: abrir el PDF | Se muestra el documento | | |
| 5 | Student A: repetir los tres | Mismo resultado que en OPS | | |

### ESC-01-04 · Laboratorio (simulación)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Laboratorio «PhET» de la lección 1 y curva de calentamiento de la lección 2. Tableta con pantalla táctil | La simulación carga y responde a los controles, también con el dedo. La atribución aparece al pie. Ojo: QA-08 (archivo de toque) y QA-14 (banner de «sustituto de desarrollo») |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: abrir el laboratorio de la lección 1 | La simulación carga | | |
| 2 | OPS: mover los controles (temperatura, botones) | Responde y cambia de estado | | |
| 3 | Student A en tableta: abrir el mismo laboratorio y usarlo con el dedo | Responde al toque | | |
| 4 | OPS: abrir la curva de calentamiento (lección 2) | Carga y responde | | |

### ESC-01-05 · Controles de la clase

| Entradas esperadas | Salidas esperadas |
|---|---|
| Clase abierta con Student A y Student B dentro | Bloquear muestra «Mira al frente»; «Navegación libre» deja navegar; el aviso aparece en las tabletas; la mano levantada se ve en OPS y baja con «Atender»; si B pierde la red, OPS lo muestra como reconectando |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Bloquear pantallas» | Student muestra «Mira al frente» | | |
| 2 | OPS: desbloquear y pasar a «Navegación libre» | Student puede navegar con sus propios botones | | |
| 3 | OPS: «Enviar un aviso» → «Dos minutos» | Banda de aviso en las tabletas | | |
| 4 | Student A: «✋ Pedir ayuda» | OPS muestra la mano levantada | | |
| 5 | OPS: «Atender» | La mano baja | | |
| 6 | Student B: apagar el Wi-Fi 10 s | OPS: «1 reconectando» en ≤ 3 s; al volver, conectado | | |

### ESC-01-06 · Actividad lanzada y respondida

| Entradas esperadas | Salidas esperadas |
|---|---|
| Actividad de la lección 1 (7 preguntas de 6 tipos). Student A y B dentro | Student responde los 6 tipos y recibe «Entregado. Tu profesor ya lo tiene.» sin nota. OPS muestra el avance en vivo. Ojo: QA-11 (el orden de ordenar y relacionar cambia al reabrir) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: ver la vista previa de la actividad | 7 preguntas: opción múltiple, V/F ×2, completar, relacionar, ordenar, abierta | | |
| 2 | OPS: «Lanzar actividad» → todo el grupo → «Lanzar» | «Actividad en curso · 0 de 2 entregaron» | | |
| 3 | Student A: «Empezar» y responder cada tipo | Cada respuesta queda guardada («Guardado») | | |
| 4 | Student A: «Entregar» (con una sin responder: «Entregar igual») | «Entregado. Tu profesor ya lo tiene.» Sin nota ni correcto/incorrecto | | |
| 5 | Student B: responder y entregar | OPS: «2 de 2 entregaron» | | |
| 6 | OPS: «Ver avance en vivo» | La abierta aparece pendiente de revisar | | |

### ESC-01-07 · Cierre de la clase

| Entradas esperadas | Salidas esperadas |
|---|---|
| Clase abierta, con o sin actividad abierta | Con actividad abierta, espera hasta 60 s o «Cerrar ahora». Sale el resumen (participantes, proyecciones, actividades, avisos, duración). Student muestra «La clase terminó». El código deja de servir |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Terminar clase» con una actividad abierta | Pregunta «¿Terminar la clase?» y espera de 60 s con «Cerrar ahora» | | |
| 2 | OPS: «Cerrar ahora» | Pantalla «Clase terminada» con 6 tarjetas de resumen | | |
| 3 | Student: mirar su pantalla | «La clase terminó» y botón para volver al menú | | |
| 4 | Student C: intentar entrar con el código anterior | «Ese código no es» | | |
| 5 | OPS: abrir la clase siguiente (lección 2) | Se puede abrir sin conflicto | | |

### ESC-01-08 · Contenido extendido (casos conocidos)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Cursos *Teoremas de Pitágoras y Tales* (fórmulas, `drag_drop`), *Algoritmos* y *Lectura crítica* (imágenes SVG), *The U.S. Constitution* (inglés) | Se anota lo que se ve. Esperado hoy: fórmulas con TeX crudo (QA-10), `drag_drop` con «Esta pregunta se responde con tu profesor» (QA-07), posible recuadro en blanco en SVG (QA-09), subtítulos en inglés marcados «es» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Pitágoras, lección con fórmulas | Ver cómo se muestran (ejemplo de TeX crudo: `\sqrt75^2 + 42^2`) | | |
| 2 | Pitágoras, lección 1, práctica | La pregunta `drag_drop` no se puede responder | | |
| 3 | Algoritmos: portada y láminas con SVG | Anotar si las imágenes se ven | | |
| 4 | The U.S. Constitution: video con subtítulos | Anotar el idioma que dice la pista | | |

---

## HP-02 · Examen con preguntas aleatorias

### ESC-02-01 · Aplicar el examen (por API)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Grupo Quinto A con alumnos y tabletas registradas. Examen `l3-exam` del curso *Estados de la materia*. Nivel «abierto», 2 intentos, resultados «tras liberar» | Respuesta 201, asignación «activa» y `armado_previo`: estrategia `random_balanced`, 6 preguntas por alumno, banco de 18, unos 360 s |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | `POST /api/evaluacion/asignaciones/` (cuerpo en la sección 6 de `happy-path-01.md`) | 201 y estado «activa» | | |
| 2 | Leer `armado_previo` de la respuesta | `random_balanced`, 6 por alumno, banco 18 | | |
| 3 | OPS: buscar «Aplicar examen» en la secuencia de la clase | No aparece (QA-01), por eso se usa la API | | |

### ESC-02-02 · Presentar el examen (Alumno A)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Asignación activa. Student A conectado. Ana elegida en «¿Quién eres?» | Antesala con duración e «Intento 1 de 2». Examen de 6 preguntas, una a la vez, con cronómetro y «✓ Guardado». Sin claves de respuesta ni nota. El alumno entrega con una sin responder: «Tu examen quedó entregado» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student A: dock «Exámenes» → «¿Quién eres?» → Ana | «Mis evaluaciones» con tarjeta «6 preguntas» y «Comenzar» | | |
| 2 | «Comenzar» → leer la antesala → «Comenzar» | «Pregunta 1 de 6», cronómetro y «0 de 6 contestadas» | | |
| 3 | Anotar las 6 preguntas en orden y las opciones de las de elegir | Lista anotada (se usa en ESC-02-03) | | |
| 4 | Responder una de cada tipo; usar «Siguiente», «Anterior» y la tira de números | El contador sube; «✓ Guardado» | | |
| 5 | Dejar una sin responder y pulsar «Entregar» | «Te faltan N preguntas. Puedes entregar igual» | | |
| 6 | «Entregar igual» | «Tu examen quedó entregado»; no dice «calificado» ni muestra nota | | |

### ESC-02-03 · Comprobar el azar entre alumnos

| Entradas esperadas | Salidas esperadas |
|---|---|
| Al menos 4 a 6 alumnos que ya abrieron su examen (en tabletas distintas o tras «¿No eres tú?») | Cada alumno tiene 6 preguntas sin repetir y con los 3 temas. Hay conjuntos distintos y órdenes distintos. Una pregunta común tiene las opciones en otro orden según el alumno |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Alumno B, C, D…: repetir ESC-02-02 pasos 1 a 3 y anotar sus preguntas | Una fila anotada por alumno | | |
| 2 | Comparar los órdenes | Todos distintos | | |
| 3 | Comparar los conjuntos | Distintos en la mayoría de los pares | | |
| 4 | Verificar los temas de cada alumno | Los 3 temas presentes en cada examen | | |
| 5 | Elegir una pregunta que tengan 2 o más alumnos y comparar sus opciones | Opciones en orden distinto | | |

### ESC-02-04 · Reabrir no cambia el examen

| Entradas esperadas | Salidas esperadas |
|---|---|
| Alumno con intento abierto y sin entregar | Al volver a «Comenzar» (o reiniciar Student) salen las mismas preguntas, el mismo orden y las mismas opciones |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Alumno: salir del examen sin entregar | Respuestas guardadas | | |
| 2 | Volver a «Comenzar» | Continúa el mismo intento | | |
| 3 | Comparar con lo anotado | Preguntas, orden y opciones idénticos | | |

### ESC-02-05 · Entrega por tiempo y sin red

| Entradas esperadas | Salidas esperadas |
|---|---|
| Alumno en examen. Wi-Fi que se pueda apagar. El examen real dura 6 minutos | Si se corta la red menos de 30 s: «Sin conexión con el aula…» y «● Guardado en tu tableta»; al volver, «✓ Guardado» sin duplicados. Si pasa de 30 s sin señal, aparece «Tu examen está en pausa» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Apagar el Wi-Fi 15 s y responder dos preguntas | Aviso azul de sin conexión y respuestas guardadas en la tableta | | |
| 2 | Encender el Wi-Fi | Vuelve «✓ Guardado»; el panel cuenta 2 respondidas, sin duplicados | | |
| 3 | Apagar el Wi-Fi más de 40 s | «Tu examen está en pausa» | | |
| 4 | Profesor reactiva por API (`POST …/reactivar/`) | El alumno sigue en la misma pregunta | | |

### ESC-02-06 · Revisión del profesor y liberación de resultados

| Entradas esperadas | Salidas esperadas |
|---|---|
| Intentos entregados. Algunos con pregunta abierta («en revisión») | Antes de liberar, el alumno recibe «Tu profesor aún no publica los resultados». El profesor puntúa lo abierto, publica y libera. Después el alumno ve su porcentaje y «Pregunta por pregunta» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | `GET /api/evaluacion/asignaciones/{id}/panel/` | Filas con entregados y en revisión | | |
| 2 | Student: pedir «Ver resultado» antes de liberar | «Tu profesor aún no publica los resultados» (403 esperado) | | |
| 3 | `GET …/intentos/{id}/revision/` de un alumno en revisión | Muestra respuestas y la pendiente | | |
| 4 | `POST …/respuestas/{ref}/puntuar/` y `POST …/intentos/{id}/publicar/` | El intento pasa a «calificado» | | |
| 5 | `POST …/asignaciones/{id}/liberar-resultados/` | `liberados_en` queda fijado | | |
| 6 | Student: «Ver resultado» | Porcentaje, «Aprobado» o aviso ámbar, y detalle por pregunta | | |

### ESC-02-07 · Segundo intento y anulación

| Entradas esperadas | Salidas esperadas |
|---|---|
| Asignación con 2 intentos permitidos y un intento entregado | El nodo admite un 2.º intento con otro armado. El profesor anula un intento con motivo de 3 o más caracteres; con 1 letra se rechaza. Ojo: QA-15 (Student no muestra «Comenzar» para el 2.º intento) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student: buscar «Comenzar» para el 2.º intento | Hoy no aparece (QA-15) | | |
| 2 | API: abrir el 2.º intento del alumno | 201, intento número 2, otras preguntas u otro orden | | |
| 3 | `POST …/intentos/{id}/anular/` con motivo corto (1 letra) | 400 | | |
| 4 | Anular con motivo de 3 o más caracteres | Intento «anulado»; el alumno ve «Este intento no cuenta» | | |
| 5 | Nueva asignación del mismo examen al grupo | El mismo alumno recibe un armado distinto | | |

---

## HP-03 · Modo estudio

### ESC-03-01 · Preparar grupo, alumnos y tableta asignada

| Entradas esperadas | Salidas esperadas |
|---|---|
| OPS conectado al nodo. Nombres y documentos de Ana, Beto y Carla. Dos tabletas registradas | Grupo con 3 estudiantes («quedó registrado» cada uno). T-A queda «Asignada a Ana…» con botón «Devolver al aula» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS «Grupos»: «+ Nuevo grupo» «Quinto A» | Grupo creado | | |
| 2 | Registrar a Ana, Beto y Carla **con documento** | «3 estudiantes»; el PIN se muestra una sola vez | | |
| 3 | OPS «Dispositivos»: T-A → «Asignar a un alumno» → Ana → «Asignar» | «Asignada a Ana…» | | |
| 4 | Comprobar T-C | Aparece «Compartida del aula» | | |

### ESC-03-02 · Asignar una lección

| Entradas esperadas | Salidas esperadas |
|---|---|
| Grupo con alumnos. Lección «Los tres estados de la materia». Fecha límite en una semana, plazo «Flexible», «Se puede descargar» | «Listo · Lección asignada a 3 alumnos». La lista muestra «0 de 3 completaron». El buscador encuentra el curso sin tildes |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS «Modo de estudio»: «Asignar mi primera lección» | Paso 1: «¿Para quién es?» | | |
| 2 | Elegir «Todo el grupo» | Paso 2: «¿Qué lección?» | | |
| 3 | Buscar «estados materia» (sin tildes) y elegir la lección | Aparece el curso y la lección | | |
| 4 | Fecha límite, «Flexible», «Se puede descargar», consigna → «Asignar la lección» | «Listo · Lección asignada a 3 alumnos» | | |

### ESC-03-03 · Estudiar y practicar

| Entradas esperadas | Salidas esperadas |
|---|---|
| Lección asignada. Student T-A con Ana | Ana ve la lección pendiente, la abre y pasa a «en curso». La práctica da «✓ ¡Correcto!» o «✗ Todavía no» en 2 s o menos y termina con «X de 7 correctas» (sin «nota»). «Terminar lección» da «¡Lección completada!». Ojo: con práctica, el avance es 0 % hasta terminarla (QA-19) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student T-A: «Modo de estudio» → «¿Quién eres?» → «Continuar como Ana» | «Estudias como Ana…», tarjeta ○ PENDIENTE | | |
| 2 | «Comenzar lección» y recorrer láminas y páginas | Pasa a ◐ EN CURSO; OPS muestra «EN CURSO» | | |
| 3 | Intentar «Terminar lección» antes de practicar | No deja: falta la práctica | | |
| 4 | «Practicar» → «Comprobar» en cada pregunta | Veredicto en 2 s o menos | | |
| 5 | «Terminar» la práctica | «X de 7 correctas»; sin la palabra «nota» | | |
| 6 | «Terminar lección» | «¡Lección completada!»; OPS: COMPLETADA, 100 % | | |

### ESC-03-04 · Descargar (asignada sí, compartida no)

| Entradas esperadas | Salidas esperadas |
|---|---|
| T-A asignada a Ana. T-C compartida. Beto con su sesión de estudio | Ana descarga en T-A («Disponible sin conexión»; OPS «En el aparato»). Beto no puede descargar ni en T-A ni en T-C: ve el candado |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student T-A (Ana): «Descargar · NN MB» | Pasa por «Descargando contenido…» | | |
| 2 | Pausar y continuar la descarga | Retoma donde iba | | |
| 3 | Esperar el final | «Disponible sin conexión»; OPS «En el aparato» | | |
| 4 | Student T-C: «Cambiar» → Beto (dos toques) | Ve sólo lo suyo; la tarjeta muestra el candado y no hay «Descargar» | | |
| 5 | Elegir a Beto en T-A | Descarga negada (la tableta es de Ana) | | |

### ESC-03-05 · Trabajo sin red y sincronización

| Entradas esperadas | Salidas esperadas |
|---|---|
| Lección descargada en T-A. Wi-Fi que se pueda apagar | Sin red se lee, se practica y se completa; aparece «Pendiente de enviar · N». Al volver la red se envía una sola vez y OPS lo refleja. Ojo: QA-18 (Salir y cambio de alumno sin red) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Apagar el Wi-Fi de T-A | «Sin conexión» | | |
| 2 | Leer la lección y responder la práctica | Respuestas guardadas en la tableta | | |
| 3 | «Terminar lección» | «Práctica guardada» y «Pendiente de enviar · N» | | |
| 4 | Encender el Wi-Fi | «Sincronizando…» y luego «Guardado» en menos de 1 min | | |
| 5 | OPS: revisar la lección | COMPLETADA y práctica calificada, sin duplicados | | |
| 6 | (Provocar QA-18) Ana completa sin red → «Cambiar» a Beto → «Salir» → reconectar | Anotar si OPS recibe la lección de Ana | | |

### ESC-03-06 · Quién completó, cierre y «Salir»

| Entradas esperadas | Salidas esperadas |
|---|---|
| Ana y Beto completaron; Carla no ha empezado | OPS muestra el estado de cada alumno. Al cerrar la asignación desaparece de «Pendientes» y ya no se puede completar. «Salir» termina en 3 s o menos con el mensaje de trabajo guardado. «Devolver al aula» T-A funciona (o avisa de paquete sin integrar) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Ver quién completó» | Tabla con estado, avance, práctica y aparato; Carla sin empezar | | |
| 2 | OPS: «Cambios rápidos» → «Cerrar la asignación» | «Asignación cerrada» | | |
| 3 | Student (Carla): revisar «Pendientes» | Ya no aparece la lección | | |
| 4 | Student: «Salir» | «Listo. Tu trabajo queda guardado y se enviará solo» en ≤ 3 s | | |
| 5 | OPS «Dispositivos»: T-A → «Devolver al aula» | Compartida; si quedó descarga sin retirar, avisa paquete sin integrar (QA-18) | | |

---

## HP-04 · Acceso por rol

> Con el nodo por defecto nadie pide clave (QA-04). Para ESC-04-01 a 06 activa la sesión obligatoria (`AVACOM_LMS_EXIGIR_SESION=1`) y crea las personas como indica la sección 4.3 de `happy-path-01.md`. ESC-04-07 se hace con el modo por defecto.

### ESC-04-01 · Administrador: primer ingreso y cambio de clave

| Entradas esperadas | Salidas esperadas |
|---|---|
| Organización instalada con `acceso_instalar`. Documento del administrador y su clave inicial (provisional) | Entra, pero no puede crear nada hasta cambiar la clave (hoy por API). Con la clave definitiva ve «Administración», 12 teselas y «Historial» con 5 pestañas, y puede crear grupos |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Documento», «Clave» provisional → «Entrar» | Entra al tablero | | |
| 2 | Intentar «+ Nuevo grupo» | Rechazado: debe cambiar la clave | | |
| 3 | Cambiar la clave (`PUT /api/acceso/yo/credencial/`) y volver a entrar | Entra con la clave definitiva | | |
| 4 | Mirar el tablero | Etiqueta «Administración», 12 teselas, «Historial» visible | | |
| 5 | «Historial» | Bitácora con 5 pestañas | | |
| 6 | «+ Nuevo grupo» | Se crea | | |

### ESC-04-02 · Profesor

| Entradas esperadas | Salidas esperadas |
|---|---|
| Profesor creado por API y asignado como docente de Quinto A | Ve «Profesorado», 12 teselas sin «Historial» y en «Grupos» sólo su grupo. No puede crear grupos ni asignar tabletas. Puede registrar alumnos en su grupo |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: entrar con su documento y clave | Tablero «Profesorado» | | |
| 2 | Comprobar que no hay «Historial» | No aparece | | |
| 3 | «Grupos» | Sólo Quinto A (no Sexto B) | | |
| 4 | «+ Nuevo grupo» | «Con tu perfil no puedes hacer esto…» | | |
| 5 | Registrar un alumno en Quinto A | Se registra | | |
| 6 | Probar con un profesor sin grupo asignado | «Grupos» vacío: «Todavía no hay grupos» | | |

### ESC-04-03 · Alumno: su información y su aislamiento

| Entradas esperadas | Salidas esperadas |
|---|---|
| Ana (Quinto A) y Diego (Sexto B) creados con documento y PIN definitivo. Lección y examen asignados sólo a Quinto A | Cada alumno entra con «Tu código» y «Tu clave», ve «Bienvenido» con su primer nombre y 9 teselas. Ana ve lo de Quinto A; Diego no ve nada de Quinto A |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student: Ana entra con su código y clave | «Bienvenido, Ana» y 9 teselas | | |
| 2 | Ana: «Modo de estudio» y «Exámenes» | Ve lo asignado a Quinto A | | |
| 3 | Student: Diego entra | «Bienvenido, Diego» | | |
| 4 | Diego: «Modo de estudio» y «Exámenes» | No ve nada de Quinto A | | |
| 5 | Registrar un alumno **sin documento** y probar su «Clave de acceso» | Hoy no entra (QA-02) | | |

### ESC-04-04 · Credencial errónea y bloqueo

| Entradas esperadas | Salidas esperadas |
|---|---|
| Un alumno con su PIN correcto y uno equivocado | Cuatro fallos dan «Te quedan N intentos»; el quinto bloquea 15 min («Demasiados intentos…», 30 para administrador y técnico). Con la clave buena sigue sin entrar. Al desbloquear (API) vuelve a entrar |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Student: clave equivocada 4 veces | «Ese código o esa clave no coinciden…» con intentos restantes | | |
| 2 | 5.º intento | «Demasiados intentos. Vuelve a intentarlo en 15 min» | | |
| 3 | Probar la clave correcta | Sigue sin entrar | | |
| 4 | `POST /api/acceso/usuarios/{id}/desbloquear/` | Estado activo | | |
| 5 | Entrar con la clave correcta | Entra | | |

### ESC-04-05 · Sesión única por persona

| Entradas esperadas | Salidas esperadas |
|---|---|
| Un alumno con dos tabletas | Al entrar en la segunda, la primera queda cerrada y muestra «Abriste tu sesión en otra tableta» |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Tableta 1: Ana entra | Sesión abierta | | |
| 2 | Tableta 2: Ana entra | Entra; informa la sesión anterior | | |
| 3 | Tableta 1: hacer cualquier acción | «Abriste tu sesión en otra tableta» | | |

### ESC-04-06 · Alumno intenta entrar en OPS

| Entradas esperadas | Salidas esperadas |
|---|---|
| Ana con su sesión abierta en una tableta | OPS le responde «Esta pantalla es del profesorado. Usa la tableta del alumno.» Ojo: abre su sesión antes de rechazarla y cierra la de su tableta (QA-24) |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: entrar con el documento y la clave de Ana | «Esta pantalla es del profesorado…» | | |
| 2 | Revisar la tableta de Ana | Anotar si su sesión sigue abierta (QA-24) | | |

### ESC-04-07 · Modo por defecto (sin sesión)

| Entradas esperadas | Salidas esperadas |
|---|---|
| Nodo con `AVACOM_LMS_EXIGIR_SESION=0` | OPS entra con «EC Iniciar como profesor» sin clave y muestra «Ms. Carter / Profesora». Student pide sólo un nombre. «Historial» pide sesión y rebota. Ojo: QA-04 |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | OPS: «Comprobar conexión» y «EC Iniciar como profesor» | Entra sin credenciales | | |
| 2 | Student: escribir un nombre y «Entrar al aula» | Entra sin código ni clave | | |
| 3 | OPS: «Historial» | Pide sesión | | |
| 4 | Desde otro equipo, `POST /api/aula/sesiones/` sin token | Hoy responde 201 (QA-04) | | |

---

## Transversal · Red y carga

### ESC-05-01 · Ancho de banda del router y transmisión de objetos pesados con 25 y 35 tabletas

**Para qué sirve.** Saber cuántas tabletas aguanta el router del aula con la clase en vivo y cuánto tarda en llegar un objeto pesado (video) a todas a la vez. Hasta ahora nunca se ha probado con más de un equipo ni con tabletas reales (`happy-path-01.md`, sección 3). El nodo admite 50 tabletas en uso normal y 100 en pico (`AVACOM_AULA_DISPOSITIVOS_NORMAL` y `_PICO`), así que 35 debe caber.

**Cómo viaja un objeto.** Cada tableta pide el video al **nodo** (no a la biblioteca) y lo recibe por tramos (`Range`). El nodo lo lee de AVACOM Contenido y lo reenvía, de modo que el equipo del profesor y el router comparten la carga. Los videos instalados más pesados son los de *Teoremas de Pitágoras y Tales* (de 3,5 a 4 MB cada uno); los de los otros cursos pesan unos 150 KB.

**Cuenta rápida para anotar la expectativa.** Tiempo aproximado = (tabletas × MB × 8) ÷ Mbps reales del router. Ejemplo: 35 tabletas × 4 MB × 8 = 1.120 Mb; con 30 Mbps reales compartidos, unos 37 s si todas piden a la vez.

| Entradas esperadas | Salidas esperadas |
|---|---|
| **Red:** modelo del router, banda (2,4 o 5 GHz), canal, ancho de canal (20/40/80 MHz), si hay más de un punto de acceso, si el nodo va por cable o por Wi-Fi, y el «aislamiento de clientes» del Wi-Fi apagado. | **Conexión:** las 25 y luego las 35 tabletas entran, OPS cuenta «25 conectados» y «35 conectados» y se mantienen 10 minutos sin «reconectando» sostenido. No aparece «Aula en pico» ni «Aula llena». |
| **Nodo:** equipo del profesor con el nodo en el puerto 8000, el puerto abierto en el cortafuegos (la red Wi-Fi no puede estar en perfil Público, QA-21) y AVACOM Contenido abierto. | **Selector:** cada cambio de lámina llega a las tabletas en 3 s o menos (BR-049) en el 95 % de ellas, con 25 y con 35. |
| **Tabletas:** 25 y 35 con Student, cada una con **nombre de equipo distinto** (dos con el mismo nombre se registran como una, QA-20) y una persona distinta por tableta. Mismo modelo en lo posible; anotar los que sean distintos. | **Video pesado:** el video de 4 MB se ve en las 25 y en las 35 sin errores. Se anotan el tiempo hasta el primer fotograma (mediana y peor caso) y los cortes. Criterio propuesto, a confirmar con producto: peor caso de 15 s o menos y ningún corte de más de 5 s. |
| **Contenido:** un curso con videos pesados (Pitágoras y Tales) y uno con videos livianos (*Estados de la materia*). | **Saltos y reanudación:** al saltar a otro punto del video las tabletas piden sólo el tramo nuevo y siguen. |
| **Herramientas:** cronómetro o cámara de teléfono para filmar las tabletas, `GET /api/aula/tiempo-real/` (sockets y demora p50/p95/máximo del aviso), Administrador de tareas del equipo del nodo (CPU y red), `netsh wlan show interfaces` en una tableta Windows y los logs del nodo. | **Carga del nodo y logs:** sin errores 5xx ni tiempos agotados en los logs del nodo durante la prueba; la CPU del equipo del profesor no se queda al 100 % sostenido. |
| **Opcional:** `iperf3` entre el nodo y una tableta para medir el Mbps real antes de empezar. Si no hay, usar la descarga de un video grande y calcular Mbps = MB × 8 ÷ segundos. | **Resultado de capacidad:** una frase final: «con este router caben N tabletas y el video de X MB llega en Y s», y qué cambiar si no alcanza (banda de 5 GHz, otro canal, más puntos de acceso, cable para el nodo). |

| # | Paso | Salida esperada | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Anotar los datos de la red (router, banda, canal, ancho, puntos de acceso, nodo por cable o Wi-Fi) en la tabla de mediciones | Datos completos antes de empezar | | |
| 2 | Comprobar que el Wi-Fi no aísla clientes y que el puerto 8000 responde desde una tableta | `http://IP-del-nodo:8000/health/` abre en la tableta | | |
| 3 | Medir la velocidad real entre el nodo y una tableta cercana y una lejana (iperf3 o descarga) | Dos valores de Mbps anotados | | |
| 4 | Prueba base con **1 tableta**: abrir la clase de *Pitágoras y Tales* con un video de 4 MB y medir el tiempo hasta el primer fotograma | Referencia anotada (sin carga) | | |
| 5 | Conectar **25 tabletas** de 5 en 5 («Clase en vivo» con el código), esperando 1 minuto entre grupos | OPS cuenta 5, 10, 15, 20 y 25 conectados | | |
| 6 | Dejar las 25 conectadas y quietas 10 minutos; mirar OPS y `GET /api/aula/tiempo-real/` | Sin «reconectando» sostenido; sockets y demora p50/p95 anotados | | |
| 7 | OPS: pasar 10 láminas seguidas; medir en 5 tabletas de muestra (la más cercana, la más lejana, una de esquina, una del centro y la más antigua) | Cada cambio llega en 3 s o menos; las demás tabletas se anotan como OK o no | | |
| 8 | OPS: proyectar el video de 4 MB (seguimiento activo) para que las 25 lo pidan a la vez; medir en las 5 de muestra | Todas lo reproducen; tiempos anotados (mediana y peor caso) | | |
| 9 | Durante el video, saltar a otro punto desde OPS | Las tabletas siguen sin volver a bajar el video entero | | |
| 10 | Repetir el paso 8 con el video de *Estados de la materia* (150 KB) | Referencia de objeto liviano; casi inmediato | | |
| 11 | OPS: lanzar la actividad a las 25 y pedir que todas **entreguen a la vez** | «25 de 25 entregaron»; ninguna respuesta se pierde; sin errores en los logs | | |
| 12 | Sumar **10 tabletas** hasta tener 35 conectadas y repetir los pasos 6, 7, 8 y 11 | Mismos resultados; anotar qué empeoró | | |
| 13 | Con las 35: abrir el modo estudio y descargar el paquete de una lección en 5 tabletas asignadas al mismo tiempo (opcional) | Las descargas terminan; el tope de 15 s del cliente puede cortarlas con medios grandes (QA-18 y la lista de riesgos) | | |
| 14 | Degradar la red a propósito: alejar 5 tabletas o pasar el router a 2,4 GHz y repetir el video | Anotar cómo se ve («Sin conexión», «Reconectando», video con cortes) y si vuelve solo | | |
| 15 | Revisar los logs del nodo y las tabletas (`AVACOM_LMS_DIR_LOGS` o `backend\logs`, y «Exportar diagnóstico» en Student) | Sin 5xx ni tiempos agotados; anotar los avisos que aparezcan | | |
| 16 | Cerrar la clase y escribir la conclusión de capacidad | Frase final con N tabletas, tamaño del objeto y tiempo | | |

**Tabla de mediciones** (se llena durante la prueba; una fila por corrida).

| Corrida | Tabletas conectadas | Objeto y tamaño | Banda y Mbps medidos | Tiempo hasta el primer fotograma (mediana) | Peor caso | Cortes o fallos | Selector en 3 s o menos (de 5 de muestra) | CPU y red del nodo | Observaciones |
|---|---|---|---|---|---|---|---|---|---|
| Base | 1 | Video 4 MB | | | | | | | |
| 25 · quietas | 25 | Ninguno | | | | | | | |
| 25 · láminas | 25 | Láminas con imagen | | | | | | | |
| 25 · video pesado | 25 | Video 4 MB | | | | | | | |
| 25 · video liviano | 25 | Video 150 KB | | | | | | | |
| 25 · entrega simultánea | 25 | Actividad | | | | | | | |
| 35 · quietas | 35 | Ninguno | | | | | | | |
| 35 · láminas | 35 | Láminas con imagen | | | | | | | |
| 35 · video pesado | 35 | Video 4 MB | | | | | | | |
| 35 · video liviano | 35 | Video 150 KB | | | | | | | |
| 35 · entrega simultánea | 35 | Actividad | | | | | | | |
| 35 · red degradada | 35 | Video 4 MB | | | | | | | |

---

## Tabla consolidada de resultados

Se llena al terminar cada escenario.

| Escenario | Camino | Estado | Fecha | Quién | QA-nn / evidencia |
|---|---|---|---|---|---|
| ESC-01-01 · Abrir la clase y entrada de alumnos | HP-01 | | | | |
| ESC-01-02 · Presentación | HP-01 | | | | |
| ESC-01-03 · Lectura con audio, video y PDF | HP-01 | | | | |
| ESC-01-04 · Laboratorio | HP-01 | | | | |
| ESC-01-05 · Controles de la clase | HP-01 | | | | |
| ESC-01-06 · Actividad lanzada y respondida | HP-01 | | | | |
| ESC-01-07 · Cierre de la clase | HP-01 | | | | |
| ESC-01-08 · Contenido extendido | HP-01 | | | | |
| ESC-02-01 · Aplicar el examen (API) | HP-02 | | | | |
| ESC-02-02 · Presentar el examen | HP-02 | | | | |
| ESC-02-03 · Azar entre alumnos | HP-02 | | | | |
| ESC-02-04 · Reabrir no cambia el examen | HP-02 | | | | |
| ESC-02-05 · Entrega por tiempo y sin red | HP-02 | | | | |
| ESC-02-06 · Revisión y liberación | HP-02 | | | | |
| ESC-02-07 · Segundo intento y anulación | HP-02 | | | | |
| ESC-03-01 · Preparar grupo, alumnos y tableta | HP-03 | | | | |
| ESC-03-02 · Asignar una lección | HP-03 | | | | |
| ESC-03-03 · Estudiar y practicar | HP-03 | | | | |
| ESC-03-04 · Descargar | HP-03 | | | | |
| ESC-03-05 · Trabajo sin red y sincronización | HP-03 | | | | |
| ESC-03-06 · Quién completó, cierre y «Salir» | HP-03 | | | | |
| ESC-04-01 · Administrador | HP-04 | | | | |
| ESC-04-02 · Profesor | HP-04 | | | | |
| ESC-04-03 · Alumno e información propia | HP-04 | | | | |
| ESC-04-04 · Credencial errónea y bloqueo | HP-04 | | | | |
| ESC-04-05 · Sesión única | HP-04 | | | | |
| ESC-04-06 · Alumno en OPS | HP-04 | | | | |
| ESC-04-07 · Modo por defecto | HP-04 | | | | |
| ESC-05-01 · Red y carga con 25 y 35 tabletas | Transversal | | | | |
