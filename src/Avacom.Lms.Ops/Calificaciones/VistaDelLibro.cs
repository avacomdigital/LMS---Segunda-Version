using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>El tono de un estado. Los mismos nombres que <c>Tono</c> del examen: la pantalla los traduce. Ninguno es rojo y el color nunca es el único aviso: cada estado lleva su texto.</summary>
internal enum Matiz { Neutro, Info, Ambar, Exito, Violeta, Gris }

/// <summary>
/// Lo que una celda del libro dice, ya decidido: el estado en palabras, su tono y, según el modo, la nota presentada con su resultado interno o el símbolo del estado
/// simple. En modo simple <see cref="Principal"/> y <see cref="Secundario"/> son nulos: ninguna cifra ni letra. Lo pendiente nunca es un cero: es «—».
/// </summary>
internal sealed record CeldaPintable(
    string Estado,
    Matiz Matiz,
    string? Principal,
    string? Secundario,
    string? Simbolo,
    IReadOnlyList<string> Marcas,
    string? CalificacionId);

/// <summary>Una calificación que «Publicar lo revisado» omitió, con lo que el nodo dijo.</summary>
internal sealed record OmisionDePublicacion(string CalificacionId, string AlumnoId, string Codigo, IReadOnlyList<string> Motivos);

/// <summary>
/// La lógica de lo que el libro de calificaciones muestra, sin pintar nada. NINGÚN cálculo académico vive aquí: los valores salen tal cual del nodo (la nota
/// presentada, el resultado interno, el promedio); esto sólo decide qué se enseña según el modo, filtra lo que el profesor busca y redacta los avisos.
/// </summary>
internal static class VistaDelLibro
{
    // ------------------------------------------------------------------------------------------------ filtros

    /// <summary>Los alumnos que coinciden con lo buscado (sin tildes ni mayúsculas, con todas las palabras). Sin texto, todos. Opcional: nunca es obligatorio.</summary>
    public static IReadOnlyList<FilaDelLibro> Filas(LibroDelGrupo libro, string? busqueda)
    {
        var palabras = IndiceDeCursos.Palabras(busqueda);
        if (palabras.Length == 0) return libro.Alumnos;
        return libro.Alumnos.Where(a =>
        {
            var rotulo = IndiceDeCursos.Normalizar(a.Rotulo);
            return palabras.All(rotulo.Contains);
        }).ToList();
    }

    /// <summary>Las columnas a la vista: todas, o sólo la evaluación elegida.</summary>
    public static IReadOnlyList<ColumnaDelLibro> Columnas(LibroDelGrupo libro, string? asignacionId) =>
        string.IsNullOrWhiteSpace(asignacionId) ? libro.Asignaciones : libro.Asignaciones.Where(a => a.Id == asignacionId).ToList();

    public static CeldaDelLibro? Celda(FilaDelLibro fila, string asignacionId) => fila.Celdas.TryGetValue(asignacionId, out var c) ? c : null;

    /// <summary>La firma de lo que se ve: el reloj del nodo no cuenta como cambio, así el sondeo no repinta cuando nada cambió.</summary>
    public static string Firma(LibroDelGrupo libro) => JsonSerializer.Serialize(libro with { ServidorEn = 0 });

    // ------------------------------------------------------------------------------------------------- celdas

    public static Matiz MatizDeEstado(string? estado) => estado switch
    {
        EstadosDeResultado.Provisional => Matiz.Violeta,
        EstadosDeResultado.Revisado => Matiz.Info,
        EstadosDeResultado.Definitivo => Matiz.Exito,
        EstadosDeResultado.Reabierto => Matiz.Ambar,
        EstadosDeResultado.Anulado => Matiz.Gris,
        _ => Matiz.Neutro,
    };

    public static Matiz MatizDeEstadoSimple(string? estadoSimple) => estadoSimple switch
    {
        EstadosSimples.Completado => Matiz.Exito,
        EstadosSimples.EnProgreso => Matiz.Info,
        _ => Matiz.Neutro,
    };

    /// <summary>El símbolo de un estado simple (○ ◐ ●): lo que lee quien aún no lee números.</summary>
    public static string SimboloDeEstadoSimple(string? estadoSimple) => GradebookTexto.Simbolo(estadoSimple switch
    {
        EstadosSimples.Completado => "lleno",
        EstadosSimples.EnProgreso => "medio",
        _ => "vacio",
    });

    /// <summary>
    /// Lo que una celda enseña. <paramref name="celda"/> nula (el alumno no tiene registro de esa evaluación) es lo mismo que pendiente. En modo simple, sólo el estado simple
    /// con su símbolo; en calificaciones, el estado, la nota presentada (o «—»), el resultado interno en pequeño y las marcas: provisional, ajustada y publicación.
    /// </summary>
    public static CeldaPintable Describir(CeldaDelLibro? celda, bool modoCalificaciones)
    {
        if (!modoCalificaciones)
        {
            var simple = celda?.EstadoSimple ?? EstadosSimples.NoIniciado;
            return new(GradebookTexto.EstadoSimple(simple), MatizDeEstadoSimple(simple), null, null, SimboloDeEstadoSimple(simple), [], null);
        }
        if (celda is null) return new(GradebookTexto.Estado(EstadosDeResultado.Pendiente), Matiz.Neutro, "—", null, null, [], null);

        var presentacion = celda.Presentacion;
        // El cero no existe para lo pendiente: sin presentación no hay nota que mostrar.
        var principal = presentacion is null ? "—" : GradebookTexto.Presentada(presentacion);
        decimal? interno = presentacion?.Interno ?? celda.PuntajeEfectivo;
        // La nota se lee con los tres (puntos brutos · porcentaje · lo presentado): la cifra sólo acompaña a lo que ya es una calificación que cuenta (revisada o publicada); lo pendiente,
        // lo provisional, lo reabierto, lo anulado y lo que sólo tiene la cifra técnica de la evaluación («sin registro») no enseñan ninguna. Sin puntos (registrada a mano) va el interno.
        var cuenta = celda.Estado is EstadosDeResultado.Revisado or EstadosDeResultado.Definitivo;
        var secundario = !cuenta ? null
            : celda.Bruto is { TienePuntos: true } bruto ? GradebookTexto.Bruto(bruto)
            : interno is { } v ? $"interno {GradebookTexto.Puntaje(v)} de 100"
            : null;

        var marcas = new List<string>();
        if (presentacion?.Provisional == true && !celda.Publicada) marcas.Add("provisional");
        if (celda.Ajustada) marcas.Add("ajustada");
        if (celda.Publicada) marcas.Add("publicada");
        else if (celda.Estado == EstadosDeResultado.Revisado) marcas.Add("sin publicar");

        return new(GradebookTexto.Estado(celda.Estado), MatizDeEstado(celda.Estado), principal, secundario, null, marcas, celda.CalificacionId);
    }

    // ------------------------------------------------------------------------------------------------ cuentas

    /// <summary>Cuántas calificaciones de una evaluación están revisadas y sin publicar: lo que «Publicar lo revisado» publicaría.</summary>
    public static int PorPublicar(LibroDelGrupo libro, string asignacionId) =>
        libro.Alumnos.Count(a => a.Celdas.TryGetValue(asignacionId, out var c) && c.Estado == EstadosDeResultado.Revisado && !c.Publicada);

    /// <summary>
    /// Cuántos estudiantes completaron una evaluación que está calificada en MOD-010 pero SIN calificación registrada: pasa cuando el nivel estaba en modo simple (o sin nivel) al calificarse y después
    /// se eligió un sistema. Pasar de modo no registra nada solo; «Registrar lo calificado» lo hace.
    /// </summary>
    public static int SinRegistrar(LibroDelGrupo libro, string asignacionId) =>
        libro.Asignaciones.FirstOrDefault(a => a.Id == asignacionId)?.Conteo?.SinRegistro                           // el nodo ya lo contó (también en el libro en resumen, sin celdas)
        ?? libro.Alumnos.Count(a => a.Celdas.TryGetValue(asignacionId, out var c) && c.Estado == EstadosDeResultado.SinRegistro && c.EstadoSimple == EstadosSimples.Completado);

    /// <summary>El aviso de «Registrar lo calificado»: cuántas se registraron y, de lo que no, quién y por qué (lo que no se pudo no tumba a lo demás).</summary>
    public static (string Titulo, string? Detalle, bool Problemas) DescribirRegistro(RegistroDeAsignacion r, Func<string, string> rotuloDeAlumno)
    {
        var titulo = r.Registradas switch
        {
            0 when r.NoRegistrables.Count == 0 && r.EnModoSimple > 0 => "Este nivel está en modo simple: no se registra nada",
            0 when r.NoRegistrables.Count == 0 => "No había nada por registrar",
            0 => r.NoRegistrables.Count == 1 ? "No se registró ninguna: 1 aún no se puede" : $"No se registró ninguna: {r.NoRegistrables.Count} aún no se pueden",
            1 => "Se registró 1 calificación",
            var n => $"Se registraron {n} calificaciones",
        };
        var lineas = new List<string>();
        if (r.Registradas > 0) lineas.Add("Ya se ven con el sistema de calificación del nivel, sin publicar: el alumno no las ve hasta que las publiques.");
        if (r.YaRegistradas > 0) lineas.Add(r.YaRegistradas == 1 ? "1 ya estaba registrada." : $"{r.YaRegistradas} ya estaban registradas.");
        if (r.EnModoSimple > 0 && r.Registradas > 0) lineas.Add($"{r.EnModoSimple} {(r.EnModoSimple == 1 ? "es" : "son")} de un nivel en modo simple y no se registr{(r.EnModoSimple == 1 ? "ó" : "aron")}.");
        foreach (var o in r.NoRegistrables.Take(6))
            lineas.Add($"Sin registrar: {rotuloDeAlumno(o.AlumnoId)} · {(string.IsNullOrWhiteSpace(o.Detalle) ? "todavía no se puede registrar" : o.Detalle)}");
        if (r.NoRegistrables.Count > 6) lineas.Add($"…y {r.NoRegistrables.Count - 6} más.");
        return (titulo, lineas.Count == 0 ? null : string.Join("\n", lineas), r.NoRegistrables.Count > 0);
    }

    // ------------------------------------------------------------------------------------- lista de estudiantes

    public const string OrdenNombre = "nombre", OrdenAtencion = "atencion", OrdenPromedio = "promedio";

    /// <summary>
    /// El orden de la lista de estudiantes: de la A a la Z; quien más pide al profesor primero (revisar, registrar, publicar); o quien lleva el promedio más bajo primero. Quien aún no tiene
    /// promedio (nada calificado) va AL FINAL del orden por promedio: lo pendiente no es un cero, así que no es «el más bajo».
    /// </summary>
    public static IEnumerable<FilaDelLibro> Ordenar(IEnumerable<FilaDelLibro> filas, string orden) => orden switch
    {
        OrdenAtencion => filas.OrderByDescending(f => f.Resumen?.Conteo.PorAtender ?? 0).ThenBy(f => f.Rotulo, StringComparer.CurrentCultureIgnoreCase),
        OrdenPromedio => filas.OrderBy(f => f.Resumen?.PromedioSimple is null ? 1 : 0).ThenBy(f => f.Resumen?.PromedioSimple ?? 0).ThenBy(f => f.Rotulo, StringComparer.CurrentCultureIgnoreCase),
        _ => filas.OrderBy(f => f.Rotulo, StringComparer.CurrentCultureIgnoreCase),
    };

    public static int Reabiertas(LibroDelGrupo libro) =>
        libro.Alumnos.Sum(a => a.Celdas.Values.Count(c => c.Estado == EstadosDeResultado.Reabierto));

    /// <summary>Lo que espera revisión del profesor: intentos entregados con respuestas por puntuar y calificaciones reabiertas.</summary>
    public static int RevisionesPendientes(LibroDelGrupo libro) => libro.Totales.PorRevisar + Reabiertas(libro);

    // ----------------------------------------------------------------------------------------------- agregados

    /// <summary>Los cursos de las columnas a la vista, sin repetir y en orden, con su nombre legible: un promedio simple por curso.</summary>
    public static IReadOnlyList<(string CursoRef, string Rotulo)> Cursos(IEnumerable<ColumnaDelLibro> columnas) =>
        columnas.GroupBy(c => c.CursoRef).Select(g => (g.Key, g.Select(c => c.CursoRotulo).FirstOrDefault(r => !string.IsNullOrWhiteSpace(r)) ?? g.Key)).ToList();

    public static AgregadoDeCurso? Agregado(FilaDelLibro fila, string cursoRef) => fila.Agregados.FirstOrDefault(a => a.CursoRef == cursoRef);

    /// <summary>El promedio simple de un alumno en un curso, tal como lo calculó el nodo (0–100). Sin calificaciones, «—», nunca un cero.</summary>
    public static string PromedioSimple(AgregadoDeCurso? a) => a?.PromedioSimple is { } p ? GradebookTexto.Puntaje(p) : "—";

    public static string DetalleDeAgregado(AgregadoDeCurso? a)
    {
        if (a is null) return "sin calificaciones";
        var partes = new List<string> { a.Calificaciones == 1 ? "1 calificación" : $"{a.Calificaciones} calificaciones" };
        var faltan = a.Pendientes + a.Provisionales;
        if (faltan > 0) partes.Add(faltan == 1 ? "1 por completar" : $"{faltan} por completar");
        return string.Join(" · ", partes);
    }

    // ------------------------------------------------------------------------------------------- publicación

    /// <summary>Las omitidas de «Publicar lo revisado»: el nodo las manda como objetos libres; aquí se leen con tolerancia.</summary>
    public static IReadOnlyList<OmisionDePublicacion> Omisiones(PublicacionDeAsignacion r)
    {
        var lista = new List<OmisionDePublicacion>();
        foreach (var o in r.Omitidas)
        {
            if (o.ValueKind != JsonValueKind.Object) continue;
            var motivos = new List<string>();
            if (o.TryGetProperty("motivos", out var m) && m.ValueKind == JsonValueKind.Array)
                motivos.AddRange(m.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).Where(x => !string.IsNullOrWhiteSpace(x)));
            lista.Add(new OmisionDePublicacion(Texto(o, "calificacion_id"), Texto(o, "alumno_id"), Texto(o, "codigo"), motivos));
        }
        return lista;
    }

    private static string Texto(JsonElement o, string clave) => o.TryGetProperty(clave, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? string.Empty : string.Empty;

    private static string MotivoDeCodigo(string codigo) => codigo switch
    {
        "no_publicable" => "todavía no se puede publicar",
        "transicion_invalida" => "su estado no permite publicarla",
        "modo_simple" => "el nivel está en modo simple",
        _ => "no cumple las condiciones para publicarse",
    };

    /// <summary>
    /// El aviso con el resultado de «Publicar lo revisado»: cuántas se publicaron y, de las omitidas, quién y por qué. <paramref name="rotuloDeAlumno"/> traduce un
    /// identificador al nombre que se ve en el libro. <c>Problemas</c> es verdadero si algo se omitió (el aviso es ámbar, no verde).
    /// </summary>
    public static (string Titulo, string? Detalle, bool Problemas) DescribirPublicacion(PublicacionDeAsignacion r, Func<string, string> rotuloDeAlumno)
    {
        var omisiones = Omisiones(r);
        var publicadas = r.TotalPublicadas;
        string titulo;
        if (publicadas == 0 && omisiones.Count == 0) titulo = "No había nada por publicar";
        else if (omisiones.Count == 0) titulo = publicadas == 1 ? "Se publicó 1 calificación" : $"Se publicaron {publicadas} calificaciones";
        else titulo = $"Se publicaron {publicadas}; {(omisiones.Count == 1 ? "1 se omitió" : $"{omisiones.Count} se omitieron")}";

        var lineas = new List<string>();
        if (publicadas > 0) lineas.Add("Los alumnos ya pueden ver su calificación publicada.");
        if (r.YaPublicadas > 0) lineas.Add(r.YaPublicadas == 1 ? "1 ya estaba publicada." : $"{r.YaPublicadas} ya estaban publicadas.");
        foreach (var o in omisiones.Take(6))
        {
            var motivo = o.Motivos.Count > 0 ? string.Join(" ", o.Motivos) : MotivoDeCodigo(o.Codigo);
            lineas.Add($"Omitida: {rotuloDeAlumno(o.AlumnoId)} · {motivo}");
        }
        if (omisiones.Count > 6) lineas.Add($"…y {omisiones.Count - 6} más.");
        return (titulo, lineas.Count == 0 ? null : string.Join("\n", lineas), omisiones.Count > 0);
    }
}
