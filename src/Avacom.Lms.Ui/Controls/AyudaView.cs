using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Una explicación que no ocupa la pantalla todo el tiempo: junto a su <see cref="Contenido"/> (un título, por ejemplo) va un botón redondo «i»;
/// al tocarlo se abre debajo una burbuja con el <see cref="Texto"/> y, fuera de ella, un botón «Volver» que la cierra (tocar la «i» otra vez también). Es para
/// pantallas táctiles: no hay hover, todo se abre y se cierra con un toque. La burbuja empuja lo de abajo en vez de flotar encima, así no tapa nada.
///
/// La burbuja no lleva sombra: en Windows, un borde con sombra que se oculta y se vuelve a mostrar deja un rectángulo gris detrás.
/// </summary>
[ContentProperty(nameof(Contenido))]
public class AyudaView : ContentView
{
    public static readonly BindableProperty TextoProperty =
        BindableProperty.Create(nameof(Texto), typeof(string), typeof(AyudaView), string.Empty, propertyChanged: (b, _, n) => ((AyudaView)b).texto.Text = (string)n);
    public static readonly BindableProperty ContenidoProperty =
        BindableProperty.Create(nameof(Contenido), typeof(View), typeof(AyudaView), propertyChanged: (b, _, n) => ((AyudaView)b).Colocar((View?)n));

    private readonly Grid raiz;
    private readonly Border boton;
    private readonly Label letra;
    private readonly VerticalStackLayout burbuja;
    private readonly Label texto;

    public AyudaView()
    {
        letra = new Label
        {
            Text = "i", FontFamily = Ds.FuenteSemi, FontSize = 20, TextColor = Ds.Verde700,
            HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center,
        };
        boton = new Border
        {
            WidthRequest = 40, HeightRequest = 40, BackgroundColor = Ds.Verde50, StrokeThickness = 0,
            StrokeShape = new RoundRectangle { CornerRadius = 20 }, VerticalOptions = LayoutOptions.Center, Content = letra,
        };
        SemanticProperties.SetDescription(boton, "Más información");
        // El área de toque es mayor que el círculo (48 × 48): con el dedo, 40 se queda corto.
        var toque = new Grid { WidthRequest = 48, HeightRequest = 48, VerticalOptions = LayoutOptions.Center, Children = { boton } };
        boton.HorizontalOptions = LayoutOptions.Center;
        Ds.Tocable(toque, () => { Alternar(); return Task.CompletedTask; });

        texto = new Label { FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        var volver = new Button
        {
            Text = "Volver", FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Verde700, BackgroundColor = Colors.Transparent, BorderWidth = 0,
            Padding = new Thickness(0, 0, 12, 0), HeightRequest = 44, HorizontalOptions = LayoutOptions.Start,
        };
        Ds.PonerIcono(volver, "boton_atras.png");
        volver.Clicked += (_, _) => Cerrar();
        var caja = new Border
        {
            BackgroundColor = Ds.Verde50, Stroke = new SolidColorBrush(Ds.Verde100), StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(20, 16),
            MaximumWidthRequest = 720, HorizontalOptions = LayoutOptions.Start, Content = ConMarca(texto),
        };
        // «Volver» va fuera de la caja, debajo: así se lee como el botón de regresar de siempre y no como parte del texto.
        burbuja = new VerticalStackLayout { IsVisible = false, Spacing = 4, Margin = new Thickness(0, 10, 0, 0), Children = { caja, volver } };

        raiz = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)],
            RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Auto)],
            ColumnSpacing = 12,
        };
        raiz.Add(toque, 1, 0);
        toque.HorizontalOptions = LayoutOptions.Start;
        raiz.Add(burbuja, 0, 1);
        Grid.SetColumnSpan(burbuja, 2);
        Content = raiz;
    }

    private static Grid ConMarca(Label texto)
    {
        var marca = new Border
        {
            WidthRequest = 28, HeightRequest = 28, BackgroundColor = Ds.Principal, StrokeThickness = 0,
            StrokeShape = new RoundRectangle { CornerRadius = 14 }, VerticalOptions = LayoutOptions.Start,
            Content = new Label { Text = "i", FontFamily = Ds.FuenteSemi, FontSize = 15, TextColor = Colors.White, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
        };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14 };
        fila.Add(marca, 0, 0);
        texto.VerticalOptions = LayoutOptions.Center;
        fila.Add(texto, 1, 0);
        return fila;
    }

    /// <summary>La explicación que se abre al tocar la «i».</summary>
    public string Texto { get => (string)GetValue(TextoProperty); set => SetValue(TextoProperty, value); }

    /// <summary>Lo que va a la izquierda de la «i» (normalmente el título que la explicación amplía).</summary>
    public View? Contenido { get => (View?)GetValue(ContenidoProperty); set => SetValue(ContenidoProperty, value); }

    public bool Abierta => burbuja.IsVisible;

    private View? colocado;

    private void Colocar(View? vista)
    {
        if (colocado is not null) raiz.Remove(colocado);
        colocado = vista;
        if (vista is null) return;
        vista.VerticalOptions = LayoutOptions.Center;
        raiz.Add(vista, 0, 0);
    }

    private void Alternar()
    {
        if (Abierta) Cerrar();
        else Abrir();
    }

    public void Abrir()
    {
        burbuja.Opacity = 0;
        burbuja.IsVisible = true;
        _ = burbuja.FadeToAsync(1, 160, Easing.CubicOut);
        PintarBoton(true);
    }

    public void Cerrar()
    {
        burbuja.IsVisible = false;
        PintarBoton(false);
    }

    // Abierta: la «i» se rellena de verde principal con la letra blanca, como un elemento elegido del DS.
    private void PintarBoton(bool abierta)
    {
        boton.BackgroundColor = abierta ? Ds.Principal : Ds.Verde50;
        letra.TextColor = abierta ? Colors.White : Ds.Verde700;
    }
}
