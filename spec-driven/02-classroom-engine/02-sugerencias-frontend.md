# 02 · Classroom Engine · Sugerencias para el frontend .NET MAUI

| Campo | Valor |
|---|---|
| Módulo | MOD-007 · Classroom Engine · clientes **AVACOM LMS OPS** (Windows, pantalla interactiva táctil **sin teclado**) y **AVACOM LMS Student** (Windows y Android) |
| Estado | **Propuesta** para el siguiente prompt: el componente que consume la vista de aula y las pantallas de la sesión. Nada de esto está implementado en `src/` todavía |
| Contrato que consume | `/api/aula/` según [01 · Modelo de datos y API](01-modelo-de-datos.md) §9. El endpoint de arranque es `GET /api/aula/pruebas/curso/` |
| Arquitectura | MVVM sobre la disposición actual: `Avacom.Lms.Core` (modelos, servicios HTTP) → `Avacom.Lms.Ui` (controles compartidos) → `Avacom.Lms.Ops` / `Avacom.Lms.Student` (páginas) |
| Regla de oro | El cliente **no guarda el curso**: lo pide en vivo, lo pinta y sólo conserva referencias (`curso_ref`, `objeto_ref`, `participante_id`) en `Preferences` |
| Journey que prevalece | [03 · Journey «Clase de Hoy»](03-journey-clase-de-hoy.md): la versión corta (4 pantallas en OPS + 2 en Student) que alimenta el prompt del frontend. Este documento aporta los DTO, el mapa de componentes y las reglas de WebView que ese journey reutiliza |
| Documentos hermanos | [00 · Introducción](00-introduccion.md) · [07 · Comunicación OPS ↔ Student](../07-comunicacion-ops-student.md) · [Sugerencias del módulo de acceso](../../specs/presentaciones/acceso-sugerencias.html) (privado) |

---

## 0 · Resumen

Qué construir, en orden:

1. **`IAulaApi` / `AulaApi` en Core**: el cliente HTTP de `/api/aula/` con los DTO de §3. Misma degradación que `BibliotecaDeContenido`: un `503` no es excepción, es un motivo que se muestra.
2. **`AulaContenidoView` en Ui**: un control compartido que recibe un `ObjetoAula` y lo pinta según `componente` (presentación, lectura, laboratorio web, actividad). Dentro, un `DataTemplateSelector` por bloque y otro por pregunta (§4).
3. **OPS · «Dar clase»**: desde el curso abierto (`CursoBibliotecaPage`), iniciar la sesión y operar la clase: código en grande, lista de conectados, proyectar, bloquear, lanzar, avisar, cerrar (§5.1).
4. **Student · «Entrar a la clase»**: teclado numérico de seis dígitos, seguir el selector, pantalla bloqueada, actividades pendientes, salir (§5.2).

Qué **no** construir: tablas locales del curso, análisis de `.pptx`, lógica de corrección, cálculo de notas, ni una segunda copia de lo que ya hace `CourseContentView` para el modo libre.

---

## 1 · Lo que ya existe y se conserva

| Pieza | Dónde | Qué aporta a MOD-007 |
|---|---|---|
| `BibliotecaDeContenido` | `Core/Services/BibliotecaDeContenido.cs` | El patrón de fachada: `BaseUri`, `UltimoMotivo`, `503 → lista vacía / null`, cuerpos con `Content-Length` (C-11). `AulaApi` lo copia |
| `CourseContentView` | `Ui/Controls/CourseContentView.xaml(.cs)` | El visor del contrato 1 (imagen, video, PDF, interactivo, lección, evaluación) y su regla de `WebView` acotada al host del backend (`OnNavigating`). Sigue sirviendo para el modo libre; la vista de aula añade láminas, páginas y laboratorios |
| `ProfessorHexTile`, `AsignaturasPage` (OPS y Student) | `Ui/Controls`, `Ops/Pages`, `Student/Pages` | El panel «Asignaturas» ya agrupa por curso; con `GET /api/aula/cursos/` pasa a agrupar por **asignatura** (`subject.name`) con los cursos dentro |
| `Sesion` (OPS y Student) | `Ops/Sesion.cs`, `Student/Sesion.cs` | `BaseUri`, `Dispositivo`, `PersonaId`, `Paleta`. Ahí viven `ParticipanteId` y `SesionDeClaseId` |
| `ActivitySocketClient`, `ConnectionOptions.WebSocketBaseUri` | `Core/Services`, `Core/Models` | Listos para el canal `ws/aula/{sesion_id}/` cuando exista (Q-51). Mientras, sondeo HTTP |
| Colores y estilos | `Resources/Styles/Colors.xaml`, `Styles.xaml` | `BrandRed #E5262B`, `BrandBlue #01A4E1`, `BrandGreen #019D60`, `Ink #18181B`, `InkMuted`, `SuccessSoft`, `ErrorSoft`; estilos `PrimaryButton`, `DarkButton`, `Muted`, `PageTitle` |
| `RegistroDeFallos` | `Core/Services` | Todo fallo de la sesión en vivo queda en `%LOCALAPPDATA%\AVACOM\lms\fallos-*.log` |
| Manifiesto Android | `Student/Platforms/Android/AndroidManifest.xml` | Hay que añadir `android:usesCleartextTraffic="true"` (T-L03 de [07](../07-comunicacion-ops-student.md)); sin él ninguna URL `http://<IP>:8000/…` carga en la tableta, tampoco las de la vista de aula |

---

## 2 · Especificación

### 2.1 · Historias

| ID | Historia | Superficie |
|---|---|---|
| US-A1 | Como docente, abro una asignatura, elijo un curso y una lección y pulso **Dar clase**; en menos de un minuto veo el código de unión en grande y la lista de alumnos que van llegando | OPS · PAN-021 → PAN-001/002 |
| US-A2 | Como docente, proyecto la primera lámina y avanzo con un toque; los alumnos ven la misma lámina en menos de 3 s | OPS · PAN-003 · Student · PAN-102 |
| US-A3 | Como docente, bloqueo las pantallas mientras explico y las libero después | OPS · CAP-042 |
| US-A4 | Como docente, lanzo la actividad de la lección; veo cuántas tabletas la recibieron y cierro la recepción | OPS · PAN-050 → PAN-004 |
| US-A5 | Como docente, envío un aviso a todo el grupo o a una tableta | OPS · FUN-075 |
| US-A6 | Como docente, cierro la clase y veo el resumen (participación, actividades, pendientes) | OPS · PAN-008 |
| US-A7 | Como estudiante, escribo el código de seis dígitos y entro; veo lo que proyecta el profesor y no puedo navegar mientras estoy en seguimiento | Student · PAN-100/101 → PAN-102 |
| US-A8 | Como estudiante, cuando el profesor bloquea, mi pantalla dice «Mira al frente» sin perder nada | Student · CAP-042 |
| US-A9 | Como estudiante, cuando llega una actividad la respondo con el flujo de intentos que ya existe | Student · PAN-110 |
| US-A10 | Como estudiante, si se cae el equipo del aula veo un aviso sereno y al volver sigo donde estaba, sin escribir el código otra vez | Student · PAN-007 / MSG-003 · FUN-077 |
| US-A11 | Como desarrollador, construyo y pruebo todo lo anterior contra `GET /api/aula/pruebas/curso/` sin AVACOM Biblioteca | ambos |

### 2.2 · Pantallas del Maestro → páginas MAUI

| Maestro | Superficie | Página / control propuesto | Datos |
|---|---|---|---|
| PAN-020 · PAN-021 (grupo y vía) | S2 | `DashboardPage` («Clase de hoy») → `DarClasePage` (OPS) | `GET /api/aula/cursos/` · `POST /api/aula/sesiones/` |
| PAN-001 · PAN-022 (sesión activa, espejo de control) | S1/S2 | `SesionDocentePage` (OPS): columna izquierda estructura + control, derecha proyección | `GET /api/aula/sesiones/{id}/` cada 3 s |
| PAN-002 (código en grande) | S1 | Bloque superior de `SesionDocentePage`, tipografía ≥ 96 pt, contraste rojo/blanco | `codigo_union`, `conteo` |
| PAN-003 (proyección de recurso) | S1 | `AulaContenidoView` en modo docente + `ControlDeAvance` (anterior · N de M · siguiente) | `selector`, `POST selector/` |
| PAN-004 (actividad en vivo, vista del grupo) | S1 | `ActividadEnVivoView`: entregas confirmadas / pendientes, sin nombres cuando el tipo lo exige | `distribuciones[].entregas` |
| PAN-050 (lanzar actividad) · PAN-055 (distribuir) | S2 | Hoja modal `LanzarActividadSheet`: objeto, alcance, «disponible en modo estudio» | `POST distribuciones/` |
| PAN-008 (cierre, resumen) | S1 | `ResumenCierreView` | `POST cerrar/` → `resumen`; `409 actividades_abiertas` → MSG-016 |
| PAN-100 · PAN-101 (aula anunciada, identificarse) | S3 | `UnirseClasePage` (Student): teclado numérico de 6 dígitos, nombre ya conocido de `Sesion.Nombre` | `POST sesiones/unirse/` |
| PAN-102 (en clase, siguiendo) | S3 | `SesionEstudiantePage`: `AulaContenidoView` en modo estudiante + CMP-001 (conexión) + CMP-002 (guardado) | `GET estado/` cada 2 s |
| PAN-103 (sesión cerrada en otro dispositivo) | S3 | Aviso CMP-052 al recibir `sesion_anterior` del login de MOD-001 | ya existe en acceso |
| PAN-104 (salir) | S3 | Botón «Salir» → `POST presencia/ {estado: salio}` y vuelta a PAN-100 en 3 s | |
| PAN-007 (aviso de reconexión) | S3 | Estado `activa: false` con `estado: suspendida` → MSG-003 «Tu trabajo está guardado…» | |
| PAN-110 (responder actividad) | S3 | Reutiliza el visor de evaluación de `CourseContentView` (intentos) con la `pregunta` de la vista de aula | `pendientes[]` |

### 2.3 · Requisitos funcionales

| ID | Requisito | Cómo se comprueba |
|---|---|---|
| RF-A01 | Toda URL nace de `BaseUri` + la ruta relativa que trae la vista (`url`, `url_lanzamiento`, `url_pagina_inicial`, `subtitulos_url`). Ninguna URL absoluta al backend en código | `grep 8000` en `Core`, `Ui`, `Ops`, `Student` sólo encuentra valores por defecto |
| RF-A02 | Los DTO se deserializan con `JsonSerializerDefaults.Web` y `JsonPropertyName` en `snake_case`; los campos desconocidos se ignoran | Prueba en `Avacom.Lms.Core.Tests` con el JSON de `pruebas/curso/` guardado como recurso |
| RF-A03 | El componente elige la vista por `componente`, nunca por `tipo`; un `componente` desconocido (`no_soportado`) pinta un aviso, no una excepción | Prueba con un bloque `{"componente": "hologram"}` |
| RF-A04 | Los `tramos` se convierten en `FormattedString` (negrita) en títulos, textos, listas, enunciados y opciones | Captura de la lámina 2 con «Sólido:» en negrita |
| RF-A05 | La `WebView` sólo navega al host de `BaseUri`; cualquier otra navegación se cancela (`block_network`) | `Navigating` cancela `https://phet.colorado.edu/…` |
| RF-A06 | Un laboratorio con `orientacion: landscape` pide orientación horizontal en la tableta y respeta `scale_to_fit`; si `destinos` no incluye `tablet`, Student muestra «Se ve en la pantalla del aula» en lugar de la simulación | Manual en tableta y en OPS |
| RF-A07 | El video respeta `desde_seg`/`hasta_seg` y `autoplay`, y ofrece subtítulos si hay `subtitulos_url` | `vid-changes` recortado a 0–60 s y a 60–150 s |
| RF-A08 | El PDF abre en `desde_pagina` (`url_pagina_inicial`) y muestra «páginas N–M» | Windows: página 1 de 3 |
| RF-A09 | El docente inicia la clase **sin escribir nada**: grupo, curso y lección se eligen tocando; el código lo genera el backend | Recorrido en OPS sin teclado |
| RF-A10 | Student guarda `participante_id` y `sesion_id` en `Preferences` y, al reabrir la app o volver la red, se readmite con `participante_id` sin pedir el código | Cerrar y abrir Student durante la clase |
| RF-A11 | Student sondea `estado/` cada `intervalo_sondeo_ms`; un cambio de `selector` se pinta antes de 3 s; con `seguimiento: true` no hay navegación libre; con `pantallas_bloqueadas: true` se muestra la pantalla de bloqueo por encima de todo | CA-A04..CA-A06 |
| RF-A12 | El reloj de la tableta no decide nada: la antigüedad de un aviso o de un selector se calcula con `servidor_en` | Cambiar la hora del dispositivo no altera nada visible |
| RF-A13 | Sin backend: «No hay conexión con el aula» + reintentar; con `503`: motivo + `sugerencia`; con `409 sesion_activa_existente`: ofrecer «Continuar esa clase» (`sesion_id`) o «Cerrarla» | Escenarios de §8 |
| RF-A14 | El examen (`fuera_de_alcance`) se muestra en la estructura, atenuado, con «Lo aplica el módulo de evaluación»; no se puede proyectar ni lanzar | Toque sobre el examen |
| RF-A15 | Los avisos se muestran como CMP-005 (no bloqueante), nunca como modal que interrumpa la actividad | |
| RF-A16 | Todo texto del componente admite +40 % de longitud sin recortes (DEC-036) | Pruebas con los `tips` largos del docente |

### 2.4 · Criterios de aceptación

| ID | Criterio |
|---|---|
| CA-A01 | Con el backend en `127.0.0.1:8000` y sin biblioteca, `AulaContenidoView` pinta las tres lecciones del ejemplo: 2 presentaciones, 1 lectura, 2 laboratorios, 2 actividades y 1 examen atenuado |
| CA-A02 | La lámina 2 muestra la imagen de marcador (PNG rojo/gris), el pie y la lista con negritas |
| CA-A03 | El laboratorio «Curva de calentamiento» abre en la `WebView` con partículas moviéndose y el texto «Temperatura inicial: -10 °C» (leyó `startTemp`) |
| CA-A04 | OPS declara el selector en la lámina 3 → dos tabletas cambian a la lámina 3 en menos de 3 s |
| CA-A05 | OPS bloquea → las tabletas muestran la pantalla de bloqueo; OPS libera → vuelven al selector sin recargar |
| CA-A06 | OPS lanza «Practica: los tres estados» → cada tableta muestra la tarjeta pendiente, la abre, responde con el flujo de intentos y confirma la entrega; OPS ve «2 de 2 entregadas» |
| CA-A07 | OPS cierra con la actividad abierta → diálogo MSG-016; confirma → resumen con 2 participantes |
| CA-A08 | Cerrar y reabrir Student durante la clase no pide el código y conserva el selector |
| CA-A09 | Apagar el backend con la clase abierta: OPS muestra «sin señal» en la lista de conectados y Student «Reconectando con el aula» (MSG-002); al volver, ambos se recuperan sin reiniciar |
| CA-A10 | En la tableta Android, imagen, audio, PDF y laboratorio cargan por `http://<IP>:8000/…` (`usesCleartextTraffic`) |

---

## 3 · Contratos que consume: DTO en C#

Un solo archivo `Core/Models/AulaModels.cs`. Los objetos son **planos con colecciones opcionales**: es más simple que un polimorfismo con discriminador y coincide con lo que devuelve el backend.

```csharp
using System.Text.Json.Serialization;
namespace Avacom.Lms.Core.Models;

public sealed record Tramo([property: JsonPropertyName("texto")] string Texto, [property: JsonPropertyName("negrita")] bool Negrita);

public sealed record NodoClasificacion([property: JsonPropertyName("codigo")] string Codigo, [property: JsonPropertyName("nombre")] string Nombre,
                                       [property: JsonPropertyName("orden")] int? Orden);

public sealed record Clasificacion(
    [property: JsonPropertyName("pais")] string Pais, [property: JsonPropertyName("idioma")] string? Idioma,
    [property: JsonPropertyName("nivel")] NodoClasificacion? Nivel, [property: JsonPropertyName("grado")] NodoClasificacion? Grado,
    [property: JsonPropertyName("asignatura")] NodoClasificacion Asignatura, [property: JsonPropertyName("tema")] NodoClasificacion? Tema);

public sealed record SimulacionAula(
    [property: JsonPropertyName("entrada")] string? Entrada, [property: JsonPropertyName("proveedor")] string? Proveedor,
    [property: JsonPropertyName("tecnologia")] string? Tecnologia, [property: JsonPropertyName("orientacion")] string? Orientacion,
    [property: JsonPropertyName("ajustes")] IReadOnlyList<string> Ajustes, [property: JsonPropertyName("destinos")] IReadOnlyList<string> Destinos,
    [property: JsonPropertyName("ancho_diseno")] int? AnchoDiseno, [property: JsonPropertyName("alto_diseno")] int? AltoDiseno)
{
    public bool BloqueaRed => Ajustes.Contains("block_network");
    public bool EscalaAlViewport => Ajustes.Contains("scale_to_fit");
    public bool SirveEnTableta => Destinos.Count == 0 || Destinos.Contains("tablet");
}

public sealed record MedioAula(
    [property: JsonPropertyName("media_ref")] string MediaRef, [property: JsonPropertyName("clase")] string? Clase,
    [property: JsonPropertyName("componente")] string Componente, [property: JsonPropertyName("titulo")] string? Titulo,
    [property: JsonPropertyName("mime")] string? Mime, [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("base_url")] string? BaseUrl, [property: JsonPropertyName("ancho")] int? Ancho,
    [property: JsonPropertyName("alto")] int? Alto, [property: JsonPropertyName("duracion_seg")] double? DuracionSeg,
    [property: JsonPropertyName("paginas")] int? Paginas, [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo,
    [property: JsonPropertyName("subtitulos_url")] string? SubtitulosUrl, [property: JsonPropertyName("transcripcion_url")] string? TranscripcionUrl,
    [property: JsonPropertyName("simulacion")] SimulacionAula? Simulacion, [property: JsonPropertyName("ausente")] bool Ausente);

public sealed record BloqueAula(
    [property: JsonPropertyName("tipo")] string Tipo, [property: JsonPropertyName("componente")] string Componente,
    // titulo · texto · lista
    [property: JsonPropertyName("texto")] string? Texto, [property: JsonPropertyName("nivel")] int? Nivel,
    [property: JsonPropertyName("estilo")] string? Estilo, [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos,
    [property: JsonPropertyName("ordenada")] bool? Ordenada, [property: JsonPropertyName("items")] IReadOnlyList<string>? Items,
    [property: JsonPropertyName("items_tramos")] IReadOnlyList<IReadOnlyList<Tramo>>? ItemsTramos,
    // imagen · video · audio · pdf
    [property: JsonPropertyName("media_ref")] string? MediaRef, [property: JsonPropertyName("url")] string? Url,
    [property: JsonPropertyName("pie")] string? Pie, [property: JsonPropertyName("mime")] string? Mime,
    [property: JsonPropertyName("texto_alternativo")] string? TextoAlternativo, [property: JsonPropertyName("ancho")] int? Ancho,
    [property: JsonPropertyName("alto")] int? Alto, [property: JsonPropertyName("desde_seg")] double? DesdeSeg,
    [property: JsonPropertyName("hasta_seg")] double? HastaSeg, [property: JsonPropertyName("autoplay")] bool? Autoplay,
    [property: JsonPropertyName("duracion_seg")] double? DuracionSeg, [property: JsonPropertyName("subtitulos_url")] string? SubtitulosUrl,
    [property: JsonPropertyName("transcripcion_url")] string? TranscripcionUrl, [property: JsonPropertyName("desde_pagina")] int? DesdePagina,
    [property: JsonPropertyName("hasta_pagina")] int? HastaPagina, [property: JsonPropertyName("paginas")] int? Paginas,
    [property: JsonPropertyName("url_pagina_inicial")] string? UrlPaginaInicial);

public sealed record UnidadAula(   // lámina o página
    [property: JsonPropertyName("unidad_ref")] string UnidadRef, [property: JsonPropertyName("indice")] int Indice,
    [property: JsonPropertyName("titulo")] string Titulo, [property: JsonPropertyName("duracion_seg")] int? DuracionSeg,
    [property: JsonPropertyName("bloques")] IReadOnlyList<BloqueAula> Bloques, [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente);

public sealed record OpcionAula([property: JsonPropertyName("opcion_ref")] string OpcionRef, [property: JsonPropertyName("texto")] string Texto,
                                [property: JsonPropertyName("tramos")] IReadOnlyList<Tramo>? Tramos);
public sealed record ElementoAula([property: JsonPropertyName("ref")] string Ref, [property: JsonPropertyName("texto")] string Texto);
public sealed record EspacioAula([property: JsonPropertyName("espacio_ref")] string EspacioRef, [property: JsonPropertyName("modo_entrada")] string ModoEntrada,
                                 [property: JsonPropertyName("opciones")] IReadOnlyList<string> Opciones);

public sealed record PreguntaAula(
    [property: JsonPropertyName("pregunta_ref")] string PreguntaRef, [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("componente")] string Componente, [property: JsonPropertyName("enunciado")] string Enunciado,
    [property: JsonPropertyName("enunciado_tramos")] IReadOnlyList<Tramo>? EnunciadoTramos, [property: JsonPropertyName("puntos")] int? Puntos,
    [property: JsonPropertyName("dificultad")] int? Dificultad, [property: JsonPropertyName("duracion_estimada_seg")] int? DuracionEstimadaSeg,
    [property: JsonPropertyName("credito_parcial")] bool CreditoParcial,
    [property: JsonPropertyName("permite_varias")] bool? PermiteVarias, [property: JsonPropertyName("opciones")] IReadOnlyList<OpcionAula>? Opciones,
    [property: JsonPropertyName("plantilla")] string? Plantilla, [property: JsonPropertyName("espacios")] IReadOnlyList<EspacioAula>? Espacios,
    [property: JsonPropertyName("izquierda")] IReadOnlyList<ElementoAula>? Izquierda, [property: JsonPropertyName("derecha")] IReadOnlyList<ElementoAula>? Derecha,
    [property: JsonPropertyName("elementos")] IReadOnlyList<ElementoAula>? Elementos,
    [property: JsonPropertyName("formato_respuesta")] string? FormatoRespuesta, [property: JsonPropertyName("longitud_maxima")] int? LongitudMaxima);

public sealed record AjustesActividad([property: JsonPropertyName("retroalimentacion")] string? Retroalimentacion,
                                      [property: JsonPropertyName("intentos_permitidos")] int? IntentosPermitidos,
                                      [property: JsonPropertyName("barajar_preguntas")] bool BarajarPreguntas,
                                      [property: JsonPropertyName("barajar_opciones")] bool BarajarOpciones);

public sealed record NotasDocente([property: JsonPropertyName("summary")] string? Summary, [property: JsonPropertyName("tips")] IReadOnlyList<string>? Tips,
                                  [property: JsonPropertyName("timing")] string? Timing, [property: JsonPropertyName("commonMistakes")] IReadOnlyList<string>? CommonMistakes,
                                  [property: JsonPropertyName("differentiation")] string? Differentiation, [property: JsonPropertyName("materials")] IReadOnlyList<string>? Materials);

public sealed record ObjetoAula(
    [property: JsonPropertyName("objeto_ref")] string ObjetoRef, [property: JsonPropertyName("tipo")] string Tipo,
    [property: JsonPropertyName("componente")] string Componente, [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("modos")] IReadOnlyList<string> Modos, [property: JsonPropertyName("tema_ref")] string? TemaRef,
    [property: JsonPropertyName("duracion_estimada_seg")] int? DuracionEstimadaSeg,
    [property: JsonPropertyName("fuera_de_alcance")] bool FueraDeAlcance, [property: JsonPropertyName("modulo")] string Modulo,
    [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente,
    [property: JsonPropertyName("total_unidades")] int? TotalUnidades,
    [property: JsonPropertyName("laminas")] IReadOnlyList<UnidadAula>? Laminas,        // presentacion
    [property: JsonPropertyName("paginas")] IReadOnlyList<UnidadAula>? Paginas,        // lectura
    [property: JsonPropertyName("simulacion")] MedioAula? Simulacion,                  // laboratorio_web
    [property: JsonPropertyName("url_lanzamiento")] string? UrlLanzamiento,
    [property: JsonPropertyName("parametros_lanzamiento")] IReadOnlyDictionary<string, object>? ParametrosLanzamiento,
    [property: JsonPropertyName("objetivo_aprendizaje")] string? ObjetivoAprendizaje, [property: JsonPropertyName("instrucciones")] string? Instrucciones,
    [property: JsonPropertyName("instrucciones_tramos")] IReadOnlyList<Tramo>? InstruccionesTramos,
    [property: JsonPropertyName("pasos")] IReadOnlyList<string>? Pasos, [property: JsonPropertyName("preguntas_guia")] IReadOnlyList<string>? PreguntasGuia,
    [property: JsonPropertyName("ajustes")] AjustesActividad? Ajustes,                 // actividad
    [property: JsonPropertyName("preguntas")] IReadOnlyList<PreguntaAula>? Preguntas, [property: JsonPropertyName("puntos_totales")] int? PuntosTotales,
    [property: JsonPropertyName("total_preguntas_banco")] int? TotalPreguntasBanco)     // examen (fuera de alcance)
{
    public IReadOnlyList<UnidadAula> Unidades => Laminas ?? Paginas ?? [];
    public string Icono => Componente switch { "presentacion" => "▣", "lectura" => "▤", "laboratorio_web" => "⌗", "actividad" => "✎", "examen" => "✓", _ => "•" };
}

public sealed record LeccionAula(
    [property: JsonPropertyName("leccion_ref")] string LeccionRef, [property: JsonPropertyName("titulo")] string Titulo,
    [property: JsonPropertyName("resumen")] string? Resumen, [property: JsonPropertyName("objetivos")] IReadOnlyList<string> Objetivos,
    [property: JsonPropertyName("duracion_estimada_min")] int? DuracionEstimadaMin, [property: JsonPropertyName("modos")] IReadOnlyList<string> Modos,
    [property: JsonPropertyName("objetos")] IReadOnlyList<ObjetoAula> Objetos, [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente);

public sealed record VistaCurso(
    [property: JsonPropertyName("fuente")] string Fuente, [property: JsonPropertyName("esquema")] string Esquema,
    [property: JsonPropertyName("curso_ref")] string CursoRef, [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("titulo")] string Titulo, [property: JsonPropertyName("subtitulo")] string? Subtitulo,
    [property: JsonPropertyName("descripcion")] string? Descripcion, [property: JsonPropertyName("idioma")] string? Idioma,
    [property: JsonPropertyName("clasificacion")] Clasificacion Clasificacion, [property: JsonPropertyName("duracion_estimada_min")] int? DuracionEstimadaMin,
    [property: JsonPropertyName("modos")] IReadOnlyList<string> Modos, [property: JsonPropertyName("portada_url")] string? PortadaUrl,
    [property: JsonPropertyName("rol")] string Rol, [property: JsonPropertyName("medios")] IReadOnlyList<MedioAula> Medios,
    [property: JsonPropertyName("lecciones")] IReadOnlyList<LeccionAula> Lecciones, [property: JsonPropertyName("notas_docente")] NotasDocente? NotasDocente);
```

Sesión (mismo estilo, abreviado): `SesionDeClase` (`Id`, `Estado`, `Activa`, `CodigoUnion`, `CursoRef`, `CursoRotulo`, `LeccionRef`, `Selector`, `Seguimiento`, `PantallasBloqueadas`, `Conteo`, `Participantes`, `Distribuciones`, `Avisos`, `Resumen`, `ServidorEn`), `SelectorAula` (`ObjetoRef`, `ObjetoTipo`, `UnidadRef`, `UnidadIndice`, `MediaRef`, `Rotulo`, `DeclaradoEn`), `ParticipanteAula` (`Id`, `PersonaId`, `PersonaRotulo`, `Dispositivo`, `Estado`, `AdmisionNominal`, `UltimoLatidoEn`), `DistribucionAula` (`Id`, `Clase`, `ObjetoRef`, `ObjetoTipo`, `Rotulo`, `Abierta`, `Entregas{Total, Entregadas, Pendientes}`, `Entrega` para la tableta), `AvisoAula`, `EstadoTableta` (`Sesion`, `Activa`, `Participante`, `Selector`, `Seguimiento`, `PantallasBloqueadas`, `Pendientes`, `Avisos`, `ServidorEn`, `IntervaloSondeoMs`), `ResumenSesion`.

`IAulaApi` (Core):

```csharp
public interface IAulaApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    Task<CatalogoAula?> CursosAsync(string? fuente = null, CancellationToken ct = default);
    Task<VistaCurso?> CursoAsync(string cursoRef, bool docente, string? fuente = null, CancellationToken ct = default);
    Task<VistaCurso?> CursoDePruebaAsync(bool docente, CancellationToken ct = default);          // GET pruebas/curso/
    Uri Absoluta(string rutaRelativa);                                                            // BaseUri + "/api/aula/…"
    // docente
    Task<SesionDeClase?> IniciarAsync(IniciarSesionSolicitud s, CancellationToken ct = default);   // 409 → UltimoMotivo + SesionExistenteId
    Task<SesionDeClase?> SesionAsync(string sesionId, CancellationToken ct = default);
    Task<SelectorAula?> ProyectarAsync(string sesionId, string objetoRef, string? unidadRef, CancellationToken ct = default);
    Task<bool> ControlAsync(string sesionId, string tipo, bool activo, CancellationToken ct = default);
    Task<DistribucionAula?> DistribuirAsync(string sesionId, DistribuirSolicitud s, CancellationToken ct = default);
    Task<DistribucionAula?> CerrarDistribucionAsync(string sesionId, string distribucionId, CancellationToken ct = default);
    Task<bool> AvisarAsync(string sesionId, string texto, string? participanteId, CancellationToken ct = default);
    Task<string?> RotarCodigoAsync(string sesionId, CancellationToken ct = default);
    Task<SesionDeClase?> CerrarAsync(string sesionId, bool forzar, CancellationToken ct = default); // 409 actividades_abiertas → preguntar (MSG-016)
    Task<ParticipanteAula?> ParticipanteAsync(string sesionId, string participanteId, string accion, CancellationToken ct = default);
    // estudiante
    Task<EstadoTableta?> UnirseAsync(string codigo, string personaId, string personaRotulo, string dispositivo, string? participanteId, CancellationToken ct = default);
    Task<EstadoTableta?> PresenciaAsync(string sesionId, string participanteId, string? estado, CancellationToken ct = default);
    Task<EstadoTableta?> EstadoAsync(string sesionId, string participanteId, long? avisosDesde, CancellationToken ct = default);
    Task<bool> ConfirmarEntregaAsync(string sesionId, string distribucionId, string participanteId, CancellationToken ct = default);
}
```

Regla de degradación (copiada de `BibliotecaDeContenido`): `503`, `501` y errores de red devuelven `null`/`false` y dejan el motivo en `UltimoMotivo`; `409` y `404` también, pero además exponen el `codigo` (`UltimoCodigo`) y los extras que el cliente necesita (`sesion_id` en `sesion_activa_existente`, `distribuciones` en `actividades_abiertas`).

---

## 4 · Mapa de componentes (web views y componentes especiales)

### 4.1 · Objeto → vista

| `componente` | Control propuesto (Ui) | Comportamiento |
|---|---|---|
| `presentacion` | `PresentacionView`: `Grid` con la lámina actual (bloques en `VerticalStackLayout`) + barra inferior «Lámina N de M» + título | Docente: botones grandes anterior/siguiente que llaman `ProyectarAsync(objeto, unidad)`; el temporizador usa `duracion_seg` como referencia, sin alarma (CMP-003). Estudiante en seguimiento: sin botones; pinta `selector.unidad_ref`. `CarouselView` sólo en modo libre |
| `lectura` | `LecturaView`: `ScrollView` de páginas con pestañas o «Página N de M» | Igual que la presentación pero con desplazamiento vertical y audio/pdf embebidos |
| `laboratorio_web` | `LaboratorioView`: cabecera (objetivo, instrucciones con tramos, pasos como lista numerada, preguntas guía plegables) + `WebView` a `Absoluta(url_lanzamiento)` | Reglas de §4.3. En OPS el laboratorio ocupa la proyección completa; en Student, si `SirveEnTableta` es falso, se sustituye por la tarjeta «Se ve en la pantalla del aula» |
| `actividad` | `ActividadView`: instrucciones + `ajustes` (intentos, retroalimentación) + lista de preguntas con `PreguntaTemplateSelector` | La respuesta viaja por el flujo de intentos existente (`IniciarIntentoAsync`, `ResponderAsync`, `FinalizarIntentoAsync`) con `evaluacion_ref = objeto_ref` cuando MOD-010 lo soporte (Q-48). Hasta entonces, el modo «vista previa» pinta las preguntas sin enviar |
| `examen` | Tarjeta atenuada `FueraDeAlcanceView` | Muestra `total_preguntas_banco`, `ajustes.seleccion.cantidad_preguntas`, `aprobacion_pct` y «Lo aplica el módulo de evaluación (MOD-010)». Sin acciones |
| `no_soportado` | `AvisoBloqueView` | «Este contenido todavía no tiene visor en el LMS» + `tipo` |

Es importante aclarar que para algunos componentes se llegue a requerir WebView de MAUI de C# en .NET para algunos componentes que requieren una interacción tipo dinámica. Cómolos laboratorios de phet de phet.colorado.edu que se muestra como componente. También es importante tener en cuenta esto en el momento de gneerar el instalador. 

### 4.2 · Bloque → control

| `componente` | Control MAUI | Detalle |
|---|---|---|
| `titulo` | `Label` con `FormattedText` de `tramos`; tamaño por `nivel` (1: 32 pt, 2: 24 pt, 3: 20 pt) | En pantalla interactiva, ×1,5 |
| `texto` | `Label` con `FormattedText`; `estilo` `definition` → borde izquierdo `BrandRed` y fondo `ErrorSoft`; `highlight` → fondo amarillo suave `#FEF9E6` | Ancho máximo 72 caracteres por línea en proyección |
| `lista` | `VerticalStackLayout` de filas «• / N.» + `Label` con `items_tramos[i]` | `ordenada` decide viñeta o número |
| `imagen` | `Image` con `UriImageSource { CachingEnabled = false }` a `Absoluta(url)`, `Aspect = AspectFit`, `SemanticProperties.Description = texto_alternativo`; `pie` debajo en `Muted` | `ancho`/`alto` reservan el espacio antes de cargar. Si el backend responde `X-Avacom-Marcador: ejemplo`, mostrar un chip «marcador» |
| `video` | **Preferido**: `MediaElement` de `CommunityToolkit.Maui.MediaElement` con `Source = Absoluta(url)`, `ShouldAutoPlay = autoplay`, `SeekTo(desde_seg)` al abrir y pausa al superar `hasta_seg` (`PositionChanged`). **Alternativa sin dependencia**: la `WebView` con el HTML de `HtmlReproductor` (ya existe) usando `src="…#t=desde,hasta"` y `<track kind="subtitles" src="subtitulos_url">` | Subtítulos: con `MediaElement` no hay pista nativa; mostrar la transcripción (`transcripcion_url`) en un panel plegable. `Range` del backend permite adelantar |
| `audio` | `MediaElement` sin superficie (o el `<audio controls>` de `HtmlReproductor`) + botón grande ▶ + transcripción plegable | Un solo audio a la vez por pantalla |
| `pdf` | Windows: `WebView` a `Absoluta(url_pagina_inicial)` (WebView2 renderiza PDF y respeta `#page=N`). Android: `Launcher.Default.OpenAsync` (como hoy en `CourseContentView`) o `pdf.js` incrustado si se quiere embebido | Pie «Páginas desde_pagina–hasta_pagina de paginas» |

### 4.3 · Web views: reglas para simulaciones y contenido HTML

| Regla | Cómo |
|---|---|
| **Sólo el host del backend** | `Navigating`: cancelar si `uri.GetLeftPart(Authority) != BaseUri.GetLeftPart(Authority)` (ya así en `CourseContentView.OnNavigating`). Cumple `block_network` aunque la simulación intente salir |
| **URL de lanzamiento tal cual** | `url_lanzamiento` ya trae `?fuente=…&startTemp=-10&altitudeMeters=0`; no reconstruir el query en el cliente. Los archivos internos (`app.js`, imágenes) resuelven contra `base_url` porque el backend sirve `…/medios/{ref}/{ruta}` |
| **`scale_to_fit`** | La simulación de ejemplo se escala sola. Para simulaciones que no lo hagan: `WebView` dentro de un `Grid` con `WidthRequest/HeightRequest = ancho_diseno/alto_diseno` y `Scale = min(ancho disponible / ancho_diseno, alto / alto_diseno)` |
| **`orientacion: landscape`** | Android: `MainActivity.RequestedOrientation = ScreenOrientation.Landscape` mientras la vista está activa; al salir, `Unspecified`. Windows: nada |
| **`destinos`** | `screen` y `tablet` según la app. Si falta `tablet`, Student no carga la `WebView` (ahorra memoria y evita simulaciones de ratón en pantallas de 8") |
| **Licencia** | Si `licencia.tipo` es `cc-by-4.0`, mostrar `licencia.atribucion` en el pie (obligación de la licencia PhET) |
| **Memoria** | Una sola `WebView` viva por página; al cambiar de selector, `Source = about:blank` antes de la nueva URL (evita la carrera descrita en `CourseContentView.LimpiarVisor`) |
| **Android texto claro** | `usesCleartextTraffic="true"` en el manifiesto (RF-L05 de [07](../07-comunicacion-ops-student.md)) |
| **Sin internet** | La `WebView` no muestra páginas de error de red: si `Navigated` trae `Result != Success`, tarjeta «Este material no se pudo abrir» + reintentar |

### 4.4 · Pregunta → control de respuesta

| `componente` | Control | Valor que se envía en `respuesta` (propuesta para MOD-010, Q-48) |
|---|---|---|
| `opcion_multiple` | `RadioButton` (una) o `CheckBox` (varias, `permite_varias`) con `tramos` | `"a"` o `["a","b"]` (JSON) |
| `verdadero_falso` | Dos botones grandes «Verdadero» / «Falso» | `"true"` / `"false"` |
| `completar` | Plantilla partida por `{{id}}`: `Picker` si `modo_entrada = select`, `Entry` numérico si `numeric`, `Entry` texto si `text` | `{"b1": "propio", "b2": "forma"}` |
| `relacionar` | Dos columnas; tocar izquierda y luego derecha traza el par; los distractores de la derecha quedan sin pareja | `{"solid": "fixed", "liquid": "slide", "gas": "spread"}` |
| `ordenar` | Lista con flechas ▲▼ (táctil, sin arrastre obligatorio) | `["o-solid","o-liquid","o-gas"]` |
| `abierta` | `Editor` con contador `longitud_maxima`; guardado por respuesta (DEC-006, CMP-033) | texto |

Nada del cliente decide si la respuesta es correcta: el veredicto llega de `ResponderAsync` (biblioteca vía backend) o queda `pendiente_correccion`.

### 4.5 · Presentaciones (láminas)

- Docente (OPS): la lámina ocupa la proyección; abajo, «N de M», anterior/siguiente, y un panel lateral plegable con `notas_docente.tips` de la lámina y del objeto. Cada avance llama `ProyectarAsync(objeto_ref, unidad_ref)`; el selector vuelve confirmado en la siguiente lectura de `SesionAsync`.
- Estudiante (Student): pinta `selector.unidad_ref` con `seguimiento: true`; cuando el docente libera el seguimiento aparecen anterior/siguiente locales.
- Duración: `duracion_seg` se muestra como referencia («~7 min») sin cuenta regresiva ni alarma (CMP-003).

### 4.6 · Texto con tramos

```csharp
static FormattedString Formateado(IReadOnlyList<Tramo>? tramos, string? plano) =>
    tramos is null or { Count: 0 }
        ? new FormattedString { Spans = { new Span { Text = plano ?? string.Empty } } }
        : new FormattedString { Spans = { tramos.Select(t => new Span { Text = t.Texto, FontAttributes = t.Negrita ? FontAttributes.Bold : FontAttributes.None }) } };
```

---

## 5 · Flujos

### 5.1 · Docente (OPS, sin teclado)

1. `DashboardPage` → «Clase de hoy» → `DarClasePage`: hexágonos de **asignaturas** (`GET /api/aula/cursos/`), luego cursos, luego lecciones; las cuatro vías al mismo nivel (CMP-011): «Esta lección», «Un recurso», «Nodo del árbol» (deshabilitado hasta MOD-003), «Clase libre».
2. Toque en «Dar clase» → `POST /api/aula/sesiones/` con `via`, `curso_ref`, `leccion_ref`, `fuente` (la de la vista), `profesor_id = Sesion.ProfesorId` (o el `usuario_id` del JWT), `superficie = "pantalla"`.
   - `409 sesion_activa_existente` → diálogo «Ya tienes una clase abierta» con «Continuar» (`SesionAsync(sesion_id)`) o «Cerrarla y empezar otra» (`CerrarAsync` y reintentar).
   - `503` → «AVACOM Biblioteca está cerrada» + `sugerencia`; ofrecer «Clase libre» igual.
3. `SesionDocentePage` (PAN-001): código en grande y `conteo.conectados` que sube; la lista de participantes con CMP-013 (Esperando · Conectado · Reconectando · Salió) y acciones admitir/rechazar/expulsar. Refresco de `SesionAsync` cada 3 s hasta el WebSocket.
4. Proyectar: la estructura de la lección a la izquierda; tocar un objeto o una lámina → `ProyectarAsync`. `AulaContenidoView` en modo docente pinta el selector.
5. Controles: dos interruptores grandes, «Seguimiento» (BR-050) y «Bloquear pantallas» (CAP-042) → `ControlAsync`.
6. Lanzar: desde una actividad, «Lanzar al grupo» → `DistribuirAsync(clase: actividad)`; `PAN-004` con `entregas.entregadas / total`; «Cerrar recepción» → `CerrarDistribucionAsync`. `409 sin_participantes_admitidos` → «Todavía no hay tabletas conectadas».
7. Avisar: hoja con frases prehechas tocables («Miren al frente», «Dos minutos», «Guarden lo que llevan») porque **no hay teclado** en el nodo; texto libre sólo en Student o desde el navegador.
8. Cerrar: «Terminar clase» → `CerrarAsync(forzar: false)`; ante `409 actividades_abiertas`, MSG-016 «{n} alumnos siguen respondiendo. Si cierras ahora, se entrega lo que llevan» → `forzar: true`. Mostrar `ResumenCierreView` con `resumen`.

### 5.2 · Estudiante (Student)

1. `StudentMenuPage` → «Entrar a la clase» → `UnirseClasePage`: seis casillas y un teclado numérico en pantalla (0–9, borrar). El nombre ya está en `Sesion.Nombre`.
2. `UnirseAsync(codigo, Sesion.PersonaId, Sesion.Nombre, Sesion.Dispositivo, participanteIdGuardado)`.
   - `201/200` → guardar `participante.id` y `sesion.id` en `Preferences` (`aula_participante`, `aula_sesion`); ir a `SesionEstudiantePage`.
   - `en_espera: true` → pantalla «Tu profesor te va a admitir» con sondeo de `estado/` hasta que `participante.estado` sea `conectado`.
   - `404 codigo_invalido` → MSG-022 adaptado: «Ese código no es. Pídele a tu profesor que lo muestre».
   - `403 participante_expulsado` → «Habla con tu profesor para volver a entrar».
3. `SesionEstudiantePage` (PAN-102): `EstadoAsync` cada `intervalo_sondeo_ms`.
   - `selector` cambió → cargar el objeto (`GET …/objetos/{objeto_ref}/`, con la `fuente_curso` de la sesión) y pintar `unidad_ref`.
   - `seguimiento: true` → sin navegación propia; `false` → aparecen anterior/siguiente.
   - `pantallas_bloqueadas: true` → `BloqueoView` a pantalla completa: «Mira al frente», sin cuenta regresiva.
   - `pendientes` con `entrega: pendiente` → tarjeta «Actividad: {rotulo}»; al abrirla, `ConfirmarEntregaAsync` y el flujo de intentos.
   - `avisos` nuevos (por `enviado_en > servidor_en anterior`) → CMP-005 no bloqueante.
   - `activa: false` con `estado: suspendida` → PAN-007 / MSG-003 y seguir sondeando; `estado: cerrada` → «La clase terminó» y volver al menú.
4. Salir: `PresenciaAsync(estado: "salio")`, borrar `aula_participante` y volver a PAN-100 en 3 s (PAN-104).

### 5.3 · Reconexión

- Al arrancar Student con `aula_participante` guardado: `UnirseAsync(..., participanteId)` con el código guardado; si el código ya rotó, el `participante_id` basta para readmitir (`200`, `nuevo: false`).
- Sin red: mantener la última pantalla, CMP-001 «Reconectando con el aula» (MSG-002), reintentar cada 5 s con retroceso hasta 30 s; nunca borrar lo que el alumno escribió (CMP-002 «Guardado en tu tableta»). Las respuestas encoladas son de MOD-015/MOD-010 (BR-059), fuera de esta propuesta.

---

## 6 · Arquitectura MVVM propuesta

```
Avacom.Lms.Core
  Models/AulaModels.cs            DTO de §3
  Services/IAulaApi.cs, AulaApi.cs  cliente HTTP de /api/aula/ (degradación como BibliotecaDeContenido)
  Services/SondeoDeAula.cs        temporizador de estado (2 s Student, 3 s OPS) con cancelación y retroceso

Avacom.Lms.Ui
  Controls/AulaContenidoView.xaml(.cs)   objeto → PresentacionView · LecturaView · LaboratorioView · ActividadView · FueraDeAlcanceView
  Controls/BloqueTemplateSelector.cs      componente del bloque → DataTemplate (titulo, texto, lista, imagen, video, audio, pdf)
  Controls/PreguntaTemplateSelector.cs    componente de la pregunta → DataTemplate (6)
  Controls/BloqueoView.xaml               «Mira al frente»
  Converters/TramosAFormattedString.cs

Avacom.Lms.Ops
  Pages/DarClasePage.xaml(.cs)        asignatura → curso → lección → vía → POST sesiones/
  Pages/SesionDocentePage.xaml(.cs)   PAN-001/022: código, participantes, selector, controles, distribuciones, avisos, cierre
  ViewModels/SesionDocenteViewModel.cs

Avacom.Lms.Student
  Pages/UnirseClasePage.xaml(.cs)     teclado numérico de 6 dígitos
  Pages/SesionEstudiantePage.xaml(.cs) PAN-102 con AulaContenidoView y BloqueoView
  ViewModels/SesionEstudianteViewModel.cs
```

ViewModels con `ObservableObject` (CommunityToolkit.Mvvm, ya disponible con MAUI) y comandos asíncronos; las páginas sólo enlazan. `AulaContenidoView` no conoce HTTP: recibe `ObjetoAula`, `SelectorAula?` y `Func<string, Uri> absoluta`.

---

## 7 · Tareas

| ID | Tarea | Archivos | Verificación |
|---|---|---|---|
| T-A01 `[P]` | DTO de la vista de aula y de la sesión | `Core/Models/AulaModels.cs` | Prueba que deserializa `pruebas/curso/` y `unirse/` guardados como recursos en `tests/Avacom.Lms.Core.Tests` |
| T-A02 `[P]` | `IAulaApi` / `AulaApi` con degradación | `Core/Services/AulaApi.cs` | Prueba con `HttpMessageHandler` falso: `503 → null + UltimoMotivo`, `409 → UltimoCodigo` |
| T-A03 | `AulaContenidoView` + selectores de bloque y pregunta | `Ui/Controls/…` | CA-A01, CA-A02 con el backend y `fuente=ejemplo` |
| T-A04 | Laboratorio en `WebView` (reglas §4.3) | `Ui/Controls/LaboratorioView.xaml(.cs)` | CA-A03; navegación externa cancelada |
| T-A05 | Video y audio (MediaElement o `HtmlReproductor`) con recorte y transcripción | `Ui/Controls/…` | RF-A07 con `fuente=biblioteca` (el ejemplo no trae video) |
| T-A06 | PDF por rango (Windows embebido, Android `Launcher`) | `Ui/Controls/…` | RF-A08 |
| T-A07 | `DarClasePage` con asignaturas → curso → lección → vía | `Ops/Pages/DarClasePage.xaml(.cs)` | RF-A09 sin teclado |
| T-A08 | `SesionDocentePage`: código, participantes, selector, controles, distribuciones, avisos, cierre | `Ops/Pages/SesionDocentePage.xaml(.cs)`, `ViewModels/` | CA-A04..CA-A07 |
| T-A09 | `UnirseClasePage` con teclado numérico | `Student/Pages/UnirseClasePage.xaml(.cs)` | US-A7 |
| T-A10 | `SesionEstudiantePage` con sondeo, seguimiento, bloqueo, pendientes, avisos | `Student/Pages/SesionEstudiantePage.xaml(.cs)`, `ViewModels/` | CA-A04..CA-A06, CA-A08 |
| T-A11 | Persistir `participante_id`/`sesion_id` y readmisión | `Student/Sesion.cs` | CA-A08 |
| T-A12 `[P]` | `usesCleartextTraffic` en Android | `Student/Platforms/Android/AndroidManifest.xml` | CA-A10 |
| T-A13 | Rutas en `AppShell` de ambas apps y entrada desde `DashboardPage` («Clase de hoy») y `StudentMenuPage` | `Ops/AppShell.xaml.cs`, `Student/AppShell.xaml.cs`, `Ops/Pages/DashboardPage.xaml.cs` | Navegación |
| T-A14 | Documentar en `README.md` cómo probar con `pruebas/curso/` | `README.md` | — |

Orden sugerido: T-A01/T-A02 en paralelo → T-A03 (el componente, sobre `pruebas/curso/`) → T-A04..T-A06 → T-A07/T-A08 → T-A09..T-A11 → T-A12/T-A13.

---

## 8 · Degradación, accesibilidad y el aula sin teclado

| Situación | OPS | Student |
|---|---|---|
| Backend apagado | Lista de conectados con «sin señal»; botones de clase deshabilitados; reintento automático | MSG-002 «Reconectando con el aula»; última pantalla intacta |
| Biblioteca cerrada (`503`) al iniciar o proyectar | Tarjeta con motivo y `sugerencia`; «Clase libre» sigue disponible | El selector que ya tenía se conserva; los medios que no carguen muestran tarjeta «no se pudo abrir» |
| `409 sesion_activa_existente` | Continuar / Cerrar y empezar | — |
| `409 sesion_cerrada` | «La clase ya terminó» | «La clase terminó» → menú |
| Sesión suspendida | Banner «Clase suspendida con el mismo código» (MSG-026) y botón «Reanudar» | PAN-007 · MSG-003 |
| Medio de marcador (`X-Avacom-Marcador`) | Chip «ejemplo» sobre el medio | Igual |
| Examen | Tarjeta atenuada, sin acciones | Igual |
| Nodo principal **sin teclado** | Toda acción del docente es un toque: selección por hexágonos y listas, avisos prehechos, confirmaciones con botones grandes (≥ 64 px). Nada exige `Entry` | El código de seis dígitos se escribe con teclado numérico en pantalla |
| Indicadores permanentes | CMP-001 conexión y CMP-002 guardado, siempre visibles, sin porcentajes | Igual, en su tamaño |
| Lectura en voz | «Escuchar» en enunciados y textos usando `VozUri` cuando la biblioteca publique `voz` para el manifiesto | Igual |
| Regla | **«No se pudo comprobar» no es «no está».** Ningún error de red afirma que el curso o la clase desaparecieron | |

---

## 9 · Preguntas abiertas del frontend

| Q | Pregunta | Propuesta |
|---|---|---|
| Q-F1 | ¿`CommunityToolkit.Maui.MediaElement` o `WebView` con HTML5 para video y audio? | `MediaElement` para recorte y control nativo; conservar `HtmlReproductor` como alternativa sin dependencia. Decidir en T-A05 midiendo en la tableta de 8" |
| Q-F2 | PDF embebido en Android | `Launcher` (como hoy) en el MVP; `pdf.js` servido por el backend si el docente pide verlo dentro de la clase |
| Q-F3 | ¿Cuándo sustituir el sondeo por WebSocket? | Cuando el backend publique `ws/aula/{sesion_id}/` (Q-51); `SondeoDeAula` queda como respaldo cuando el socket cae (Q-38: «sin señal en vivo», nunca «nadie») |
| Q-F4 | UI del examen | Pertenece a MOD-010 (PAN-120..123); aquí sólo la tarjeta atenuada |
| Q-F5 | Cola local de respuestas sin red (BR-059) | MOD-015 en el dispositivo; el componente sólo debe **no perder** lo escrito (guardado por respuesta) |
| Q-F6 | Identidad del docente en OPS | Hoy `profesor_id` declarado; con login de MOD-001 en OPS, el JWT decide y `AutorizacionPrototipo` niega al estudiante (403). Al sembrar `classroom.*` no cambia nada en el cliente |
