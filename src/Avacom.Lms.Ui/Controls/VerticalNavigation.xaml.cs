using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Barra de navegación de «Clase de hoy» con la forma de la barra inferior del Aula · Design System (el nombre del control
/// es histórico): las mismas cuatro opciones (Menú principal, Lección, Configuración y Cerrar sesión) en fila, con el icono
/// sólido sobre la etiqueta, los fijos primero y los de sistema al final. La página la pone flotante, blanca y centrada abajo.
/// La opción activa (<see cref="Active"/>) va en azul 50; al pasar el puntero se tiñe de <see cref="Ds.Superficie2"/>;
/// pulsado, escala 0,97 (120 ms). Con <see cref="Compact"/> se ocultan las etiquetas y quedan sólo los iconos.
/// </summary>
public partial class VerticalNavigation : ContentView
{
    public const string OpcionMenu = "menu", OpcionLeccion = "leccion", OpcionConfiguracion = "configuracion", OpcionSalir = "salir";

    public static readonly BindableProperty ActiveProperty =
        BindableProperty.Create(nameof(Active), typeof(string), typeof(VerticalNavigation), OpcionMenu, propertyChanged: (b, _, _) => ((VerticalNavigation)b).Pintar());
    public static readonly BindableProperty CompactProperty =
        BindableProperty.Create(nameof(Compact), typeof(bool), typeof(VerticalNavigation), false, propertyChanged: (b, _, _) => ((VerticalNavigation)b).Pintar());

    private static readonly Color Reposo = Colors.Transparent;
    private static readonly Color BajoPuntero = Ds.Superficie2;

    private readonly Dictionary<string, Border> opciones;
    private readonly HashSet<Border> bajoPuntero = new();

    public VerticalNavigation()
    {
        InitializeComponent();
        opciones = new Dictionary<string, Border>
        {
            [OpcionMenu] = MenuPrincipalItem, [OpcionLeccion] = LeccionItem, [OpcionConfiguracion] = ConfiguracionItem, [OpcionSalir] = SalirItem,
        };
        Pintar();
    }

    public event EventHandler? MenuPrincipalTapped;
    public event EventHandler? LeccionTapped;
    public event EventHandler? ConfiguracionTapped;
    public event EventHandler? CerrarSesionTapped;

    /// <summary>Opción seleccionada: <c>menu</c>, <c>leccion</c>, <c>configuracion</c> o <c>salir</c>.</summary>
    public string Active { get => (string)GetValue(ActiveProperty); set => SetValue(ActiveProperty, value); }

    /// <summary>Raíl de sólo iconos.</summary>
    public bool Compact { get => (bool)GetValue(CompactProperty); set => SetValue(CompactProperty, value); }

    private bool EsActiva(Border borde) => opciones.TryGetValue(Active ?? string.Empty, out var activa) && ReferenceEquals(activa, borde);

    /// <summary>Opción activa: azul 50 (un poco más presente con el puntero encima). Sin sombra: va dentro de la barra.</summary>
    private static void PintarActiva(Border borde, bool iluminada) =>
        borde.BackgroundColor = iluminada ? Ds.Azul100 : Ds.Azul50;

    private void Pintar()
    {
        if (opciones is null) return;
        foreach (var (clave, borde) in opciones)
        {
            var activa = clave == Active;
            borde.Background = null!;
            borde.Shadow = null!;
            if (activa) PintarActiva(borde, false);
            else borde.BackgroundColor = Reposo;
            borde.Padding = Compact ? new Thickness(8, 0) : new Thickness(14, 0);
            borde.MinimumWidthRequest = Compact ? 64 : 112;
            if (borde.Content is not Layout pila) continue;
            foreach (var hijo in pila.Children)
            {
                if (hijo is Label etiqueta)
                {
                    etiqueta.IsVisible = !Compact;
                    etiqueta.FontFamily = activa ? Ds.FuenteSemi : Ds.FuenteMedia;
                    etiqueta.TextColor = activa ? Ds.Azul700 : Ds.Tinta;
                }
            }
        }
        Separador.WidthRequest = Compact ? 8 : 24;
    }

    private async void OnEntrar(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Add(borde);
        if (EsActiva(borde)) PintarActiva(borde, true);
        else borde.BackgroundColor = BajoPuntero;
        await borde.TranslateToAsync(0, -2, Ds.DurBase, Easing.CubicOut);
    }

    private async void OnSalir(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Remove(borde);
        if (EsActiva(borde)) PintarActiva(borde, false);
        else borde.BackgroundColor = Reposo;
        await borde.TranslateToAsync(0, 0, Ds.DurBase, Easing.CubicOut);
    }

    private async void OnPresionar(object? sender, PointerEventArgs e)
    {
        if (sender is Border borde) await borde.ScaleToAsync(0.97, 60, Easing.CubicOut);
    }

    private async void OnSoltar(object? sender, PointerEventArgs e)
    {
        if (sender is Border borde) await borde.ScaleToAsync(1, 60, Easing.CubicOut);
    }

    private void OnMenuTapped(object? sender, TappedEventArgs e) => MenuPrincipalTapped?.Invoke(this, EventArgs.Empty);
    private void OnLeccionTapped(object? sender, TappedEventArgs e) => LeccionTapped?.Invoke(this, EventArgs.Empty);
    private void OnConfiguracionTapped(object? sender, TappedEventArgs e) => ConfiguracionTapped?.Invoke(this, EventArgs.Empty);
    private void OnSalirTapped(object? sender, TappedEventArgs e) => CerrarSesionTapped?.Invoke(this, EventArgs.Empty);
}
