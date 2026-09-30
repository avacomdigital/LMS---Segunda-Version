using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// Una tableta de prueba completa: el servicio real de Student sobre una carpeta temporal, una clave en memoria y el aula de mentira. Cada prueba
/// arma la suya (sin compartir nada) y la libera al terminar.
/// </summary>
internal sealed class Escenario : IDisposable
{
    public const string Dispositivo = "hw-tableta-07";
    public const string Ethan = "e1", Sofia = "s1";
    public const string Asignacion = "asig-1";

    public const long Ahora = 1_790_000_000_000;   // la hora del nodo en las pruebas (octubre de 2026)
    public const long Dia = 86_400_000;

    public string Carpeta { get; }
    public FalsoEstudioApi Api { get; } = new();
    public ProveedorDeClaveEnMemoria Clave { get; }
    public EstudioLocal Local { get; }
    public DownloadService Descargas { get; }
    public ConnectivityService Conectividad { get; }
    public StudyModeService Servicio { get; }

    /// <param name="conservar">Otra ejecución de la app en LA MISMA tableta: la misma carpeta, la misma clave y las mismas preferencias (un reinicio).</param>
    public Escenario(Escenario? conservar = null)
    {
        Carpeta = conservar?.Carpeta ?? Path.Combine(Path.GetTempPath(), "avacom-student-tests", Guid.NewGuid().ToString("N"));
        Clave = conservar?.Clave ?? new ProveedorDeClaveEnMemoria();
        if (conservar is null) Preferences.Default.Clear();
        StudyModeService.RetrasoDeSincronizacionMs = 3_600_000;   // el envío automático no se cuela a media prueba: cada prueba sincroniza cuando quiere
        RelojNodo.Olvidar();
        RelojNodo.Aprender(Ahora);
        Local = EstudioLocal.Crear(Api, Dispositivo, Carpeta, Clave);
        Descargas = new DownloadService(Local);
        Conectividad = new ConnectivityService(Api, Dispositivo);
        Servicio = new StudyModeService(Local, Descargas, Conectividad, new DatosDelAparato("Tableta 07", "android", "1.0.0"), Api.RegistrarAparato);
    }

    /// <summary>Lo que el aula dice de la tableta cuando todo va bien.</summary>
    public Escenario ConAulaLista(string? dueno = null)
    {
        Api.Estado = _ => FalsoEstudioApi.Json<EstadoEstudio>($$"""
            {"disponible":true,"motivo":"","perfil":"{{(dueno is null ? "compartido" : "asignado")}}","alumno":null,
             "dueno":{{(dueno is null ? "null" : $$"""{"id":"{{dueno}}","rotulo":"Dueño"}""")}},
             "dispositivo":{"id":"d-1","nombre":"Tableta 07","identificador_hw":"{{Dispositivo}}"},"descarga_permitida":{{(dueno is null ? "false" : "true")}},"servidor_en":{{Ahora}}}
            """);
        Api.Estudiantes = () => Nombres(dueno);
        Api.Sesion = alumno => FalsoEstudioApi.Json<SesionEstudio>($$"""
            {"sesion_id":"ses-1","alumno":{"id":"{{alumno ?? Ethan}}","rotulo":"{{Rotulo(alumno ?? Ethan)}}"},"dispositivo":null,"perfil":"compartido","servidor_en":{{Ahora}}}
            """);
        return this;
    }

    public static string Rotulo(string id) => id == Ethan ? "Ethan Martínez" : id == Sofia ? "Sofía Ramírez" : id;

    public static EstudiantesEstudio Nombres(string? dueno = null) => FalsoEstudioApi.Json<EstudiantesEstudio>($$"""
        {"disponible":true,"motivo":"","grupos":[
           {"id":"g-5b","codigo":"5B","nombre":"Quinto B","alumnos":[{"id":"{{Sofia}}","rotulo":"Sofía Ramírez"},{"id":"{{Ethan}}","rotulo":"Ethan Martínez"}]}],
         "dueno":{{(dueno is null ? "null" : $$"""{"id":"{{dueno}}","rotulo":"{{Rotulo(dueno)}}"}""")}},"servidor_en":{{Ahora}}}
        """);

    /// <summary>Elige a una persona como lo haría la pantalla: pide los nombres y confirma.</summary>
    public async Task<StudyStudent> ElegirAsync(string id = Ethan)
    {
        var estudiante = new StudyStudent(id, Rotulo(id));
        Assert.True(await Servicio.ChooseStudentAsync(estudiante));
        return estudiante;
    }

    // ---------------------------------------------------------------------------------- datos del aula

    public const string PresentacionJson = """
        {"objeto_ref":"o-pres","tipo":"lecture","componente":"presentacion","titulo":"Presentación","fuera_de_alcance":false,"total_unidades":3,
         "laminas":[{"unidad_ref":"u1","indice":1,"titulo":"Uno","bloques":[]},{"unidad_ref":"u2","indice":2,"titulo":"Dos","bloques":[]},{"unidad_ref":"u3","indice":3,"titulo":"Tres","bloques":[]}]}
        """;

    public const string LaboratorioJson = """{"objeto_ref":"o-lab","tipo":"simulation_lab","componente":"laboratorio_web","titulo":"Laboratorio","fuera_de_alcance":false}""";

    public const string ActividadJson = """
        {"objeto_ref":"o-act","tipo":"activity","componente":"actividad","titulo":"Comprueba lo aprendido","fuera_de_alcance":false,
         "preguntas":[{"pregunta_ref":"q1","tipo":"multiple_choice","componente":"opcion_multiple","enunciado":"¿Cuánto es 2 + 2?","credito_parcial":false,
                       "opciones":[{"opcion_ref":"a","texto":"4"},{"opcion_ref":"b","texto":"5"}]},
                      {"pregunta_ref":"q2","tipo":"true_false","componente":"verdadero_falso","enunciado":"El agua moja.","credito_parcial":false}]}
        """;

    public const string ExamenJson = """{"objeto_ref":"o-exam","tipo":"exam","componente":"examen","titulo":"Evaluación de la unidad","fuera_de_alcance":true}""";

    /// <summary>Una lección con tres láminas, un laboratorio y una práctica de dos preguntas (5 bloques), y un examen que no es bloque.</summary>
    public static readonly string ObjetosJson = $"[{PresentacionJson},{LaboratorioJson},{ActividadJson},{ExamenJson}]";

    public const string BloquesJson = """
        [{"ref":"o-pres:u1","indice":1,"tipo":"lamina","titulo":"Uno","obligatorio":true,"atendido":false,"objeto_ref":"o-pres"},
         {"ref":"o-pres:u2","indice":2,"tipo":"lamina","titulo":"Dos","obligatorio":true,"atendido":false,"objeto_ref":"o-pres"},
         {"ref":"o-pres:u3","indice":3,"tipo":"lamina","titulo":"Tres","obligatorio":true,"atendido":false,"objeto_ref":"o-pres"},
         {"ref":"o-lab","indice":4,"tipo":"laboratorio","titulo":"Laboratorio","obligatorio":true,"atendido":false,"objeto_ref":"o-lab"},
         {"ref":"o-act","indice":5,"tipo":"practica","titulo":"Comprueba lo aprendido","obligatorio":true,"atendido":false,"objeto_ref":"o-act"}]
        """;

    /// <summary>Una asignación tal como la ve el alumno. <paramref name="extra"/> completa o pisa campos (JSON de un objeto).</summary>
    public static string AsignacionJson(string id = Asignacion, string titulo = "Área y volumen", long? limite = Ahora + 3 * Dia, string tarea = "null",
                                        string paquete = "null", string descarga = """{"permitida":true,"motivo":""}""", string practica = "auto",
                                        string estadoAsignacion = "activa", bool conBloques = false) => $$"""
        {"id":"{{id}}","titulo":"{{titulo}}","consigna":"","descripcion":"Leer con atención.","asignatura":"Matemáticas","unidad":"Unidad 2",
         "curso":{"fuente":"biblioteca","curso_ref":"curso-1","version":"1.0.0","titulo":"Matemáticas 5"},"leccion_ref":"l1",
         "fecha_limite":{{(limite is null ? "null" : limite.Value.ToString())}},"plazo":"blando","gracia_ms":900000,"estado_asignacion":"{{estadoAsignacion}}",
         "profesor":"Ms. Carter","asignada_en":{{Ahora - Dia}},"tarea":{{tarea}},
         "practica":{{(practica == "auto" ? """{"disponible":true,"objeto_ref":"o-act","titulo":"Comprueba lo aprendido","total_preguntas":2,"intentos":0,"mejor_correctas":null,"ultima_correctas":null,"en_curso":false}""" : practica)}},
         "evaluacion":{"objeto_ref":"o-exam","titulo":"Evaluación de la unidad"},"paquete":{{paquete}},"descarga":{{descarga}},
         "bloques":{{(conBloques ? BloquesJson : "null")}}}
        """;

    public static string TareaJson(string estado = "en_curso", int atendidos = 2, int total = 5, bool vencida = false, string? completadaEn = null, string ultimo = "null") => $$"""
        {"estado":"{{estado}}","vencida":{{(vencida ? "true" : "false")}},"fuera_de_plazo":false,"avance_pct":{{100.0 * atendidos / total:0.##}},"bloques_total":{{total}},
         "bloques_obligatorios":{{total}},"bloques_atendidos":{{atendidos}},"ultimo_bloque":{{ultimo}},"puede_reanudar":{{(atendidos > 0 ? "true" : "false")}},
         "abierta_en":1,"ultimo_avance_en":2,"completada_en":{{completadaEn ?? "null"}}}
        """;

    public static AsignacionesEstudio ListaDe(params string[] asignaciones) => FalsoEstudioApi.Json<AsignacionesEstudio>($$"""
        {"alumno":{"id":"{{Ethan}}","rotulo":"Ethan Martínez"},"asignaciones":[{{string.Join(",", asignaciones)}}],
         "resumen":{"pendientes":{{asignaciones.Length}},"descargadas":0,"completadas":0},"servidor_en":{{Ahora}}}
        """);

    public static LeccionEstudio LeccionJson(string asignacionJson, string bloques = BloquesJson, string reanudar = "null") => FalsoEstudioApi.Json<LeccionEstudio>($$"""
        {"asignacion":{{asignacionJson}},"curso":null,"leccion":{"leccion_ref":"l1","titulo":"Los tres estados","objetos":{{ObjetosJson}}},
         "bloques":{{bloques}},"reanudar":{{reanudar}},"servidor_en":{{Ahora}}}
        """);

    public static PracticaAbierta PracticaJson(int numero = 1, string estado = "en_curso", string respondidas = "{}", string id = "prac-1") => FalsoEstudioApi.Json<PracticaAbierta>($$"""
        {"practica":{"id":"{{id}}","numero":{{numero}},"estado":"{{estado}}","objeto_ref":"o-act","titulo":"Comprueba lo aprendido","total_preguntas":2,
                     "respondidas":{{respondidas}},"aciertos":0,"iniciada_en":{{Ahora}},"reanudada":false},
         "objeto":{{ActividadJson}}}
        """);

    /// <summary>Lo que cuesta correr todo esto sin que lo demás se entere: carga la lista y deja la tableta lista para actuar.</summary>
    public async Task<StudyListResult> CargarAsync()
    {
        var resultado = await Servicio.LoadAsync();
        Assert.False(resultado.NeedsIdentity);
        return resultado;
    }

    public static JsonElement Respuesta(string json) => JsonDocument.Parse(json).RootElement.Clone();

    public void Dispose()
    {
        Servicio.Dispose();
        Descargas.Dispose();
        Conectividad.Dispose();
        try { if (Directory.Exists(Carpeta)) Directory.Delete(Carpeta, recursive: true); }
        catch (IOException) { /* Windows todavía tiene abierto algo: la carpeta es temporal */ }
        Preferences.Default.Clear();
    }
}
