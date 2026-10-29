using Avacom.Lms.Core.Search;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Busqueda;

/// <summary>Piezas visuales de la pantalla Buscar. Sólo Border, Label y Button del kit: nada de Path ni Ellipse (un Path degenerado deja sin pintar los lienzos Win2D de la ventana).</summary>
internal static class BusquedaUi
{
    public static string Actor => Sesion.ProfesorId;
    public static bool HaySesion => Sesion.Usuario is not null;
    public static string? Rol => Sesion.Usuario?.Rol;
    public static bool PuedeBuscar => PermisosDeBusqueda.Buscar(HaySesion, Rol);

    /// <summary>El color y el glifo de cada tipo: el mismo de su módulo (Evaluaciones índigo, Modo de estudio verde, Clase de hoy magenta…).</summary>
    public static (Color Fondo, string Glifo) Marca(string? tipo) => tipo switch
    {
        TiposDeBusqueda.Curso => (Color.FromArgb("#A81D81"), "▥"),
        TiposDeBusqueda.Leccion => (Ds.CatLectura, "▤"),
        TiposDeBusqueda.Recurso => (Ds.CatVideo, "▶"),
        TiposDeBusqueda.Evaluacion => (Color.FromArgb("#5B45D1"), "✓"),
        TiposDeBusqueda.Estudio => (Ds.CatQuiz, "✎"),
        TiposDeBusqueda.Clase => (Ds.CatClaseEnVivo, "◉"),
        _ => (Ds.TintaSuave, "•"),
    };

    /// <summary>El icono de un resultado: un cuadrado redondeado con el color de su tipo y su glifo.</summary>
    public static Border Icono(string? tipo, double lado = 52)
    {
        var (fondo, glifo) = Marca(tipo);
        return new Border
        {
            BackgroundColor = fondo, StrokeThickness = 0, WidthRequest = lado, HeightRequest = lado, VerticalOptions = LayoutOptions.Start,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioControl },
            Content = new Label
            {
                Text = glifo, FontSize = lado * 0.46, TextColor = Ds.TintaSobre(fondo), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
            },
        };
    }

    /// <summary>El fragmento con lo encontrado en negrita: dos pesos de Inter, sin Markdown.</summary>
    public static Label Fragmento(string? fragmento, IReadOnlyList<IReadOnlyList<int>>? resaltados, double tamano = 14)
    {
        var formateado = new FormattedString();
        foreach (var trozo in BusquedaTexto.Trozos(fragmento, resaltados))
            formateado.Spans.Add(new Span
            {
                Text = trozo.Texto, FontFamily = trozo.Resaltado ? Ds.FuenteSemi : Ds.FuenteLigera, TextColor = trozo.Resaltado ? Ds.Tinta : Ds.TintaSuave,
            });
        return new Label { FormattedText = formateado, FontSize = tamano, LineBreakMode = LineBreakMode.WordWrap, MaxLines = 3 };
    }
}

/// <summary>Las búsquedas recientes de esta persona en este equipo (en las preferencias de OPS): repetir una búsqueda es un toque, sin teclado.</summary>
internal static class BusquedasRecientes
{
    private const int Maximo = 6;
    private static string Clave => $"ops_busquedas_recientes_{Sesion.ProfesorId}";

    public static IReadOnlyList<string> Leer() =>
        Ajustes.Get(Clave, string.Empty).Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    public static IReadOnlyList<string> Agregar(string texto)
    {
        var lista = BusquedaTexto.AgregarReciente(Leer(), texto, Maximo);
        Ajustes.Set(Clave, string.Join('\n', lista));
        return lista;
    }

    public static void Olvidar() => Ajustes.Remove(Clave);
}
