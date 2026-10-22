using System.Globalization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Search;

/// <summary>Un trozo de texto y si va resaltado (lo que coincidió con la búsqueda).</summary>
public sealed record Trozo(string Texto, bool Resaltado);

/// <summary>Un aviso de la pantalla de búsqueda: qué pasó y qué hacer. <see cref="Grave"/>: algo no funcionó (distinto de «no hay resultados»).</summary>
public sealed record AvisoDeBusqueda(string Titulo, string Detalle, bool Grave);

/// <summary>
/// Lo que la pantalla Buscar dice y comprueba, sin pintar nada (se prueba sin interfaz). NINGUNA regla de acceso vive aquí: el backend decide qué se puede leer
/// (BR-088) y qué se puede abrir. Esto sólo traduce a palabras lo que el nodo respondió y valida la FORMA de la consulta antes de mandarla, con las mismas reglas del
/// nodo, para no gastar un viaje.
/// </summary>
public static class BusquedaTexto
{
    public static readonly CultureInfo Cultura = new("es-CO");

    /// <summary>Lo mínimo que el nodo acepta como búsqueda (letras sin espacios, ya normalizadas).</summary>
    public const int MinimoDeLetras = 2;
    public const int MaximoDeCaracteres = 120;

    // ---------------------------------------------------------------------------------------------------- la consulta

    /// <summary>¿Vale la pena preguntarle al nodo? Mismas reglas que él: al menos dos letras o dígitos y no más de 120 caracteres.</summary>
    public static bool ConsultaValida(string? texto) =>
        !string.IsNullOrWhiteSpace(texto) && texto.Trim().Length <= MaximoDeCaracteres && texto.Count(char.IsLetterOrDigit) >= MinimoDeLetras;

    /// <summary>La frase que dice por qué todavía no se busca (vacía si la consulta es válida).</summary>
    public static string PorQueNoSeBusca(string? texto)
    {
        if (string.IsNullOrWhiteSpace(texto)) return string.Empty;
        if (texto.Trim().Length > MaximoDeCaracteres) return $"La búsqueda es demasiado larga (máximo {MaximoDeCaracteres} caracteres).";
        return ConsultaValida(texto) ? string.Empty : "Escribe al menos dos letras para buscar.";
    }

    // ---------------------------------------------------------------------------------------------------- búsquedas recientes

    /// <summary>
    /// Las búsquedas recientes con <paramref name="nueva"/> a la cabeza: sin repetir (sin distinguir mayúsculas ni tildes), sin las que no valen como búsqueda y a lo sumo
    /// <paramref name="maximo"/>. Es lo que permite repetir una búsqueda tocando, en el equipo del aula que no tiene teclado.
    /// </summary>
    public static IReadOnlyList<string> AgregarReciente(IEnumerable<string> actuales, string? nueva, int maximo = 6)
    {
        var lista = new List<string>();
        if (ConsultaValida(nueva)) lista.Add(string.Join(' ', nueva!.Split(' ', StringSplitOptions.RemoveEmptyEntries)));
        foreach (var texto in actuales)
        {
            if (!ConsultaValida(texto)) continue;
            var limpio = string.Join(' ', texto.Split(' ', StringSplitOptions.RemoveEmptyEntries));
            if (lista.Any(x => Comparable(x) == Comparable(limpio))) continue;
            lista.Add(limpio);
        }
        return lista.Take(maximo).ToList();
    }

    private static string Comparable(string texto) => new string(texto.Normalize(System.Text.NormalizationForm.FormD)
        .Where(c => CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark).ToArray()).ToLowerInvariant();

    // ---------------------------------------------------------------------------------------------------- tipos y estados

    public static string Rotulo(string? tipo) => tipo switch
    {
        TiposDeBusqueda.Curso => "Curso",
        TiposDeBusqueda.Leccion => "Lección",
        TiposDeBusqueda.Recurso => "Recurso",
        TiposDeBusqueda.Evaluacion => "Evaluación",
        TiposDeBusqueda.Estudio => "Estudio asignado",
        TiposDeBusqueda.Clase => "Clase",
        _ => tipo ?? "—",
    };

    public static string RotuloDeTipoPlural(string? tipo) => tipo switch
    {
        TiposDeBusqueda.Curso => "Cursos",
        TiposDeBusqueda.Leccion => "Lecciones",
        TiposDeBusqueda.Recurso => "Recursos",
        TiposDeBusqueda.Evaluacion => "Evaluaciones",
        TiposDeBusqueda.Estudio => "Estudios asignados",
        TiposDeBusqueda.Clase => "Clases",
        _ => tipo ?? "—",
    };

    /// <summary>El tipo de un resultado, con su subtipo cuando lo tiene (una evaluación puede ser un examen o una actividad).</summary>
    public static string RotuloCompleto(Hallazgo h) => h.Tipo == TiposDeBusqueda.Evaluacion
        ? h.Subtipo switch { "examen" => "Examen", "actividad" => "Actividad", _ => "Evaluación" }
        : Rotulo(h.Tipo);

    /// <summary>El estado del recurso del LMS en palabras (el del catálogo no tiene estado).</summary>
    public static string Estado(string? tipo, string? estado) => (tipo, estado) switch
    {
        (_, null or "") => string.Empty,
        (TiposDeBusqueda.Evaluacion, "programada") => "Programada",
        (TiposDeBusqueda.Evaluacion, "activa") => "Abierta",
        (TiposDeBusqueda.Evaluacion, "activa_fuera_de_plazo") => "Abierta, fuera de plazo",
        (TiposDeBusqueda.Evaluacion, "cerrada") => "Cerrada",
        (TiposDeBusqueda.Estudio, "activa") => "Vigente",
        (TiposDeBusqueda.Estudio, "cerrada") => "Cerrada",
        (TiposDeBusqueda.Clase, "planificada") => "Planificada",
        (TiposDeBusqueda.Clase, "abierta") => "En curso",
        (TiposDeBusqueda.Clase, "suspendida") => "Suspendida",
        (TiposDeBusqueda.Clase, "cerrada") => "Terminada",
        _ => estado!,
    };

    /// <summary>Una clase abierta o suspendida se continúa en vivo; el resto se abre en su resumen.</summary>
    public static bool ClaseEnCurso(string? estado) => estado is "abierta" or "suspendida";

    /// <summary>La línea de contexto de un resultado: dónde vive (grupo, ciclo, curso) o por dónde cuelga en el árbol de la biblioteca.</summary>
    public static string Contexto(Hallazgo h)
    {
        var c = h.Contexto;
        if (c is null) return string.Empty;
        if (c.Ruta is { Count: > 0 }) return string.Join(" › ", c.Ruta.Where(p => !string.IsNullOrWhiteSpace(p)));
        var partes = new List<string>();
        if (!string.IsNullOrWhiteSpace(c.Grupo)) partes.Add(c.Grupo!);
        if (!string.IsNullOrWhiteSpace(c.Periodo)) partes.Add(c.Periodo!);
        if (!string.IsNullOrWhiteSpace(c.Curso)) partes.Add(c.Curso!);
        if (!string.IsNullOrWhiteSpace(c.Leccion) && c.Leccion != h.Titulo) partes.Add(c.Leccion!);
        return string.Join(" · ", partes);
    }

    // ---------------------------------------------------------------------------------------------------- texto resaltado

    /// <summary>Parte un fragmento en trozos, marcando los que el nodo dijo que coincidieron (<c>[inicio, fin)</c>, en caracteres del propio fragmento).</summary>
    public static IReadOnlyList<Trozo> Trozos(string? fragmento, IReadOnlyList<IReadOnlyList<int>>? resaltados)
    {
        if (string.IsNullOrEmpty(fragmento)) return [];
        var rangos = (resaltados ?? [])
            .Where(r => r.Count == 2 && r[0] >= 0 && r[1] > r[0] && r[1] <= fragmento.Length)
            .OrderBy(r => r[0])
            .ToList();
        var salida = new List<Trozo>();
        var cursor = 0;
        foreach (var r in rangos)
        {
            if (r[0] < cursor) continue;                                           // un rango que se pisa con el anterior no se repite
            if (r[0] > cursor) salida.Add(new Trozo(fragmento[cursor..r[0]], false));
            salida.Add(new Trozo(fragmento[r[0]..r[1]], true));
            cursor = r[1];
        }
        if (cursor < fragmento.Length) salida.Add(new Trozo(fragmento[cursor..], false));
        return salida;
    }

    // ---------------------------------------------------------------------------------------------------- resumen y avisos

    public static string Resumen(RespuestaDeBusqueda r)
    {
        if (r.Total == 0) return $"Sin coincidencias para «{r.Consulta}».";
        var cuantos = r.Total == 1 ? "1 resultado" : $"{r.Total.ToString("N0", Cultura)}{(r.TotalExacto ? string.Empty : "+")} resultados";
        return $"{cuantos} para «{r.Consulta}»";
    }

    /// <summary>La aclaración cuando el nodo relajó la búsqueda (ninguna entidad tenía todas las palabras).</summary>
    public static string? AclaracionDeCoincidencia(RespuestaDeBusqueda r) =>
        r.Relajada && r.Total > 0 ? "Ningún resultado tiene todas las palabras: se muestran los que tienen alguna, los más completos primero." : null;

    /// <summary>El aviso del estado del índice, o null si está al día. Un índice rezagado se consulta igual: sólo se avisa.</summary>
    public static AvisoDeBusqueda? AvisoDelIndice(string? estado, string? aviso) => estado switch
    {
        EstadosDelIndice.Construyendose => new AvisoDeBusqueda("El índice de búsqueda se está construyendo", string.IsNullOrWhiteSpace(aviso) ? "Por ahora pueden faltar resultados." : aviso, false),
        EstadosDelIndice.Reconstruyendose => new AvisoDeBusqueda("El índice de búsqueda se está reconstruyendo", string.IsNullOrWhiteSpace(aviso) ? "Los resultados podrían estar incompletos unos instantes." : aviso, false),
        EstadosDelIndice.Rezagado => new AvisoDeBusqueda("El índice va un poco atrás", string.IsNullOrWhiteSpace(aviso) ? "Los resultados podrían no incluir los cambios más recientes." : aviso, false),
        _ => null,
    };

    /// <summary>El aviso del catálogo cuando AVACOM Biblioteca no contestó: la búsqueda siguió con lo del LMS.</summary>
    public static AvisoDeBusqueda? AvisoDelCatalogo(RespuestaDeBusqueda r) => !r.CatalogoNoDisponible ? null : new AvisoDeBusqueda(
        "AVACOM Biblioteca no está disponible",
        string.Join(" ", new[] { "Se muestran sólo tus evaluaciones, estudios y clases; los cursos, lecciones y recursos vuelven cuando la biblioteca esté abierta.", r.Fuentes?.Catalogo?.Sugerencia }
            .Where(x => !string.IsNullOrWhiteSpace(x))), false);

    /// <summary>El título de la tarjeta de «Buscar» en pausa por la licencia: el mismo que usa Reportes (MOD-018, U-3).</summary>
    public const string EnPausaTitulo = "No disponible con la licencia de este equipo";

    /// <summary>
    /// MOD-018 · U-3: la búsqueda está EN PAUSA por la licencia (402 <c>no_disponible_por_licencia</c>). No es un fallo de carga ni de conexión: la pantalla muestra su tarjeta propia
    /// (como Reportes), con «Ver la licencia» para quien la administra, en vez del recuadro genérico «No se pudo cargar todo».
    /// </summary>
    public static bool EnPausaPorLicencia(ErrorAula? error) => error is { EsModuloNoDisponible: true };

    /// <summary>Qué decir cuando la búsqueda NO se pudo hacer (distinto de no encontrar nada): sin conexión, sin permiso, consulta inválida o un fallo del nodo.</summary>
    public static AvisoDeBusqueda Error(ErrorAula? error, string? motivo)
    {
        if (error is null || error.Estado == 0)
            return new AvisoDeBusqueda("No hay conexión con el nodo del aula", "No se pudo buscar. Revisa que el equipo principal esté encendido y en la misma red; se vuelve a intentar al tocar «Buscar».", true);
        return error.Codigo switch
        {
            "sin_permiso" or "fuera_de_alcance" => new AvisoDeBusqueda("Tu rol no puede buscar", "Pídele acceso a la administración.", true),
            "consulta_vacia" => new AvisoDeBusqueda("Escribe qué quieres buscar", string.Empty, false),
            "consulta_invalida" or "datos_invalidos" => new AvisoDeBusqueda("Esa búsqueda no se puede hacer", string.IsNullOrWhiteSpace(error.Detalle) ? "Prueba con otras palabras." : error.Detalle, false),
            "no_disponible" => new AvisoDeBusqueda("Ese resultado ya no está disponible", "Se retiró o ya no tienes acceso. Vuelve a buscar para ver lo que hay ahora.", false),
            "catalogo_no_disponible" => new AvisoDeBusqueda("AVACOM Biblioteca no está disponible", "Sin ella no se puede abrir el contenido. Abre la aplicación de contenido y vuelve a intentarlo.", true),
            _ when error.EsModuloNoDisponible => new AvisoDeBusqueda(EnPausaTitulo, Licencia.LicenciaTexto.ParaError(error) ?? Licencia.LicenciaTexto.NucleoSigue, true),
            _ when error.SesionPerdida => new AvisoDeBusqueda("Tu sesión terminó", "Vuelve a entrar para seguir buscando.", true),
            _ => new AvisoDeBusqueda("No se pudo buscar", string.IsNullOrWhiteSpace(motivo) ? "El nodo no contestó lo esperado. Se puede volver a intentar." : motivo!, true),
        };
    }
}
