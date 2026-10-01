using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.Examen;

/// <summary>Lo que comparten las pantallas de la evaluación del alumno: composición, textos del nivel y formato de horas. Sin lógica de examen (esa vive en <c>SesionDeExamen</c>).</summary>
internal static class ExamenAyudas
{
    /// <summary>En una ventana ancha (escritorio, 1920 × 1080) la tarjeta se ancla a la cuadrícula de tercios del encuadre completo; en una tableta, más ancha para que quepa el texto.</summary>
    private const double AnchoDeEscritorio = 1500;

    /// <summary>
    /// Regla de tercios: la tarjeta ocupa el tercio central en X y va de 1/6 a 5/6 en Y (Grid <c>*,*,*</c> / <c>*,4*,*</c>, la tarjeta en la celda central con Fill y sin márgenes).
    /// En una ventana angosta (tableta) el tercio central sería demasiado estrecho para leer un examen: la tarjeta toma casi todo el ancho, con la misma proporción vertical.
    /// </summary>
    public static Grid ConTarjetaAnclada(View tarjeta, Page pagina, out Action ajustar)
    {
        var raiz = new Grid { BackgroundColor = Ds.Lienzo };
        raiz.RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)];
        raiz.ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)];
        Grid.SetRow(tarjeta, 1);
        Grid.SetColumn(tarjeta, 1);
        tarjeta.HorizontalOptions = LayoutOptions.Fill;
        tarjeta.VerticalOptions = LayoutOptions.Fill;
        raiz.Add(tarjeta);
        void Ajustar()
        {
            var ancho = pagina.Width;
            if (ancho <= 0) return;
            var escritorio = ancho >= AnchoDeEscritorio;
            raiz.ColumnDefinitions[0].Width = new GridLength(escritorio ? 1 : 0.25, GridUnitType.Star);
            raiz.ColumnDefinitions[1].Width = new GridLength(escritorio ? 1 : 3.5, GridUnitType.Star);
            raiz.ColumnDefinitions[2].Width = new GridLength(escritorio ? 1 : 0.25, GridUnitType.Star);
        }
        pagina.SizeChanged += (_, _) => Ajustar();
        ajustar = Ajustar;
        return raiz;
    }

    /// <summary>«‹ Volver» flotando arriba a la izquierda (fuera de la tarjeta anclada).</summary>
    public static Button BotonVolver(string texto, Func<Task> alPulsar)
    {
        var volver = Ds.Boton(texto, Ds.Rango.Quiet, async (_, _) => await alPulsar(), 52);
        volver.HorizontalOptions = LayoutOptions.Start;
        volver.VerticalOptions = LayoutOptions.Start;
        volver.Margin = new Thickness(18, 14, 0, 0);
        volver.FontSize = 17;
        volver.AutomationId = "exa-volver-pagina";
        return volver;
    }

    public static string RotuloNivel(string? nivel) => Niveles.Normalizar(nivel) switch
    {
        Niveles.Controlado => "Examen controlado",
        Niveles.Supervisado => "Examen supervisado",
        _ => "Examen abierto",
    };

    /// <summary>La hora del nodo, en la hora local de la tableta: «hoy 10:30» / «mañana 08:00» / «12/10 10:30».</summary>
    public static string Hora(long milisegundos)
    {
        var fecha = DateTimeOffset.FromUnixTimeMilliseconds(milisegundos).ToLocalTime();
        var hoy = DateTimeOffset.Now.Date;
        var dia = fecha.Date == hoy ? "hoy" : fecha.Date == hoy.AddDays(1) ? "mañana" : fecha.ToString("dd/MM");
        return $"{dia} {fecha:HH:mm}";
    }

    public static string Duracion(int? segundos)
    {
        if (segundos is not > 0) return "Sin límite de tiempo";
        var minutos = (int)Math.Ceiling(segundos.Value / 60.0);
        return minutos >= 60 && minutos % 60 == 0 ? $"{minutos / 60} h" : minutos > 60 ? $"{minutos / 60} h {minutos % 60} min" : $"{minutos} min";
    }

    public static string Intentos(int? permitidos, int usados) => permitidos switch
    {
        null => "Intentos sin límite",
        1 => "Intento único",
        _ => $"Intento {Math.Min(usados + 1, permitidos.Value)} de {permitidos}",
    };

    /// <summary>Los datos de un estado en una frase corta para una píldora (nunca el nombre del enum).</summary>
    public static string FraseDeEstado(string estado) => estado switch
    {
        "programada" => "Aún no abre",
        "activa" => "Abierto",
        "activa_fuera_de_plazo" => "Abierto · fuera de plazo",
        "cerrada" or "archivada" => "Cerrado",
        _ => estado,
    };

    public static Border Hecho(string texto, string id)
    {
        var pildora = Ds.Pildora(texto, Ds.Lienzo, Ds.Tinta, 15);
        pildora.AutomationId = id;
        return pildora;
    }

    /// <summary>Una fila de datos con un punto: lo que se registra, lo que se ve.</summary>
    public static View Vineta(string texto, double tamano = 16)
    {
        var fila = new HorizontalStackLayout { Spacing = 8 };
        fila.Add(new Label { Text = "•", FontSize = tamano, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Start });
        var etiqueta = Ds.Secundario(texto, tamano);
        etiqueta.TextColor = Ds.TintaMedia;
        fila.Add(etiqueta);
        return fila;
    }

    /// <summary>Una caja suave con un título y su texto (condiciones, avisos).</summary>
    public static Border Caja(string titulo, string? texto, Color fondo, string? id = null)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        if (!string.IsNullOrWhiteSpace(texto)) pila.Add(Ds.Cuerpo(texto!, 16, Ds.TintaMedia));
        return new Border
        {
            BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(18, 14), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
            Content = pila, AutomationId = id ?? string.Empty,
        };
    }
}
