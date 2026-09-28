using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Menú vertical fijo del tablero táctil: exactamente cuatro opciones (Menú principal, Lección, Configuración y
/// Cerrar sesión) apiladas desde abajo, porque en una pantalla táctil gigante lo que está abajo es lo que se alcanza
/// con la mano: Menú principal queda pegado al borde inferior, Lección encima y, tras una línea translúcida,
/// Configuración y Cerrar sesión (la salida es lo más lejano). Sin perfil, avatar, progreso ni otras opciones.
///
/// La opción activa (<see cref="Active"/>) es una cápsula de vidrio con canto luminoso y halo violeta; las demás son
/// transparentes y se iluminan al pasar el puntero. Hover 1,02 (150 ms) · pressed 0,97 (90 ms) · release 1,0 (140 ms).
/// Con <see cref="Compact"/> se ocultan las etiquetas y queda un raíl de iconos para anchos insuficientes; nunca se
/// convierte en una barra horizontal. Los iconos son geometrías vectoriales (Phosphor, caja de 256), no emojis.
/// </summary>
public partial class VerticalNavigation : ContentView
{
    public const string OpcionMenu = "menu", OpcionLeccion = "leccion", OpcionConfiguracion = "configuracion", OpcionSalir = "salir";

    public static readonly BindableProperty ActiveProperty =
        BindableProperty.Create(nameof(Active), typeof(string), typeof(VerticalNavigation), OpcionMenu, propertyChanged: (b, _, _) => ((VerticalNavigation)b).Pintar());
    public static readonly BindableProperty CompactProperty =
        BindableProperty.Create(nameof(Compact), typeof(bool), typeof(VerticalNavigation), false, propertyChanged: (b, _, _) => ((VerticalNavigation)b).Pintar());

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

    private void Pintar()
    {
        if (opciones is null) return;
        foreach (var (clave, borde) in opciones)
        {
            var activa = clave == Active;
            borde.BackgroundColor = Colors.Transparent;
            borde.Background = activa ? Glass.Relleno(Colors.White, 0.36, 0.16) : null!;
            borde.Stroke = activa ? Glass.CantoLuminoso(0.95) : new SolidColorBrush(Colors.Transparent);
            borde.Shadow = activa ? Glass.Halo(Glass.Violeta, 0.40, 22, 8) : null!;
            borde.Padding = Compact ? new Thickness(0) : new Thickness(14, 0);
            if (borde.Content is not Grid fila) continue;
            if (fila.ColumnDefinitions.Count > 0) fila.ColumnDefinitions[0].Width = Compact ? GridLength.Star : new GridLength(30);
            foreach (var hijo in fila.Children)
            {
                if (hijo is Label etiqueta)
                {
                    etiqueta.IsVisible = !Compact;
                    etiqueta.FontFamily = activa ? Ds.FuenteSemi : Ds.FuenteMedia;
                }
            }
        }
        Separador.Margin = Compact ? new Thickness(14, 10) : new Thickness(12, 10);
    }

    private async void OnEntrar(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Add(borde);
        if (EsActiva(borde)) borde.Shadow = Glass.Halo(Glass.Violeta, 0.58, 28, 8);
        else borde.BackgroundColor = Color.FromArgb("#1FFFFFFF");
        await borde.ScaleToAsync(1.02, 150, Easing.CubicOut);
    }

    private async void OnSalir(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Remove(borde);
        if (EsActiva(borde)) borde.Shadow = Glass.Halo(Glass.Violeta, 0.40, 22, 8);
        else borde.BackgroundColor = Colors.Transparent;
        await borde.ScaleToAsync(1, 150, Easing.CubicOut);
    }

    private async void OnPresionar(object? sender, PointerEventArgs e)
    {
        if (sender is Border borde) await borde.ScaleToAsync(0.97, 90, Easing.CubicOut);
    }

    private async void OnSoltar(object? sender, PointerEventArgs e)
    {
        if (sender is Border borde) await borde.ScaleToAsync(bajoPuntero.Contains(borde) ? 1.02 : 1, 140, Easing.CubicOut);
    }

    private void OnMenuTapped(object? sender, TappedEventArgs e) => MenuPrincipalTapped?.Invoke(this, EventArgs.Empty);
    private void OnLeccionTapped(object? sender, TappedEventArgs e) => LeccionTapped?.Invoke(this, EventArgs.Empty);
    private void OnConfiguracionTapped(object? sender, TappedEventArgs e) => ConfiguracionTapped?.Invoke(this, EventArgs.Empty);
    private void OnSalirTapped(object? sender, TappedEventArgs e) => CerrarSesionTapped?.Invoke(this, EventArgs.Empty);
}
