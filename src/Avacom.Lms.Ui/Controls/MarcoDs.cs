using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Estructura de pantalla del Aula · Design System para las pantallas internas: fondo (Aurora, o liso en evaluar,
/// exámenes y calificaciones), isla de marca neumórfica arriba al centro y, en la esquina superior izquierda, la fecha y
/// la hora (pizarra) o la etiqueta de modo del alumno (tableta). Debajo va el contenido de la pantalla tal cual
/// (<see cref="Contenido"/>): sólo se envuelve, el contenido conserva sus nombres, su relleno y su código.
/// Desde XAML: <c>&lt;ui:MarcoDs&gt;…raíz de la página…&lt;/ui:MarcoDs&gt;</c>; desde código: <c>Content = new MarcoDs { Contenido = raiz };</c>.
/// </summary>
[ContentProperty(nameof(Contenido))]
public sealed class MarcoDs : Grid
{
    public static readonly BindableProperty AuroraProperty =
        BindableProperty.Create(nameof(Aurora), typeof(bool), typeof(MarcoDs), true, propertyChanged: (b, _, n) => ((MarcoDs)b).fondo.IsVisible = (bool)n);
    public static readonly BindableProperty TabletaProperty =
        BindableProperty.Create(nameof(Tableta), typeof(bool), typeof(MarcoDs), false, propertyChanged: (b, _, _) => ((MarcoDs)b).Cabecera());
    public static readonly BindableProperty ModoProperty =
        BindableProperty.Create(nameof(Modo), typeof(string), typeof(MarcoDs), null, propertyChanged: (b, _, _) => ((MarcoDs)b).Cabecera());

    private readonly FondoAurora fondo = new();
    private readonly Grid cabecera = new() { ZIndex = 3 };
    private View? contenido;

    public MarcoDs()
    {
        RowDefinitions = [new RowDefinition(112), new RowDefinition(GridLength.Star)];
        BackgroundColor = Ds.Fondo;
        Add(fondo);
        SetRowSpan((IView)fondo, 2);
        this.Add(cabecera, 0, 0);
        Cabecera();
    }

    /// <summary>Fondo Aurora (predeterminado). Falso: fondo liso, como manda el DS en evaluar, exámenes y bloqueo.</summary>
    public bool Aurora { get => (bool)GetValue(AuroraProperty); set => SetValue(AuroraProperty, value); }

    /// <summary>Tableta del alumno: isla compacta (220 × 60), fila de 86 y la etiqueta de <see cref="Modo"/> en la esquina.</summary>
    public bool Tableta { get => (bool)GetValue(TabletaProperty); set => SetValue(TabletaProperty, value); }

    /// <summary>Modo del alumno que se muestra en la esquina (tableta): Explorar, Aprender, Practicar o Evaluar.</summary>
    public string? Modo { get => (string?)GetValue(ModoProperty); set => SetValue(ModoProperty, value); }

    /// <summary>La raíz de la pantalla, que va debajo de la isla.</summary>
    public View? Contenido
    {
        get => contenido;
        set
        {
            if (contenido is not null) Children.Remove(contenido);
            contenido = value;
            if (value is not null) this.Add(value, 0, 1);
        }
    }

    private void Cabecera()
    {
        RowDefinitions[0].Height = new GridLength(Tableta ? 86 : 112);
        cabecera.Children.Clear();
        cabecera.Add(new IslaDeMarca { Compacta = Tableta });
        if (!Tableta) { cabecera.Add(new EsquinaFechaHora { Margin = new Thickness(44, 20, 0, 0) }); return; }
        if (string.IsNullOrWhiteSpace(Modo)) return;
        cabecera.Add(EtiquetaDeModo(Modo!));
    }

    /// <summary>Etiqueta de modo del DS: un color, un significado (Explorar azul · Aprender magenta · Practicar amarillo · Evaluar violeta).</summary>
    private static View EtiquetaDeModo(string modo)
    {
        var color = modo.ToLowerInvariant() switch
        {
            "aprender" => Ds.Magenta600,
            "practicar" => Ds.Amarillo500,
            "evaluar" => Ds.Violeta600,
            _ => Ds.Azul600,
        };
        var fila = new HorizontalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        fila.Add(new BoxView { Color = color, WidthRequest = 10, HeightRequest = 10, CornerRadius = 5, VerticalOptions = LayoutOptions.Center });
        fila.Add(new Label { Text = modo, FontFamily = Ds.FuenteSemi, FontSize = 16, TextColor = Ds.Oscuro(color), VerticalOptions = LayoutOptions.Center });
        return new CajaNeumorfica
        {
            Relleno = new Thickness(16, 8), HorizontalOptions = LayoutOptions.Start, VerticalOptions = LayoutOptions.Start,
            Margin = new Thickness(32, 12, 0, 0), InputTransparent = true, Interior = fila,
        };
    }
}
