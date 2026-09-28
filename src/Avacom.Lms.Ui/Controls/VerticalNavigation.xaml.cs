using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Menú vertical fijo del tablero táctil: exactamente cuatro opciones (Menú principal, Lección, Configuración y
/// Cerrar sesión) apiladas desde abajo, porque en una pantalla táctil gigante lo que está abajo es lo que se alcanza
/// con la mano: Menú principal queda pegado al borde inferior, Lección encima y, tras una línea translúcida,
/// Configuración y Cerrar sesión (la salida es lo más lejano). Sin perfil, avatar, progreso ni otras opciones.
///
/// Vive sobre la barra sólida <c>#5A5A56</c> (el gris del dock del tablero), con iconos y etiquetas en blanco. La
/// opción activa (<see cref="Active"/>) es una cápsula blanca translúcida con canto claro; las demás son transparentes
/// y se iluminan al pasar el puntero. Hover 1,02 (150 ms) · pressed 0,97 (90 ms) · release 1,0 (140 ms).
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

    private static readonly Color Reposo = Colors.Transparent;
    private static readonly Color BajoPuntero = Color.FromArgb("#1FFFFFFF");

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

    /// <summary>Cápsula de la opción activa: blanco translúcido algo más presente arriba, canto claro y sin sombra (la barra es sólida).</summary>
    private static void PintarActiva(Border borde, bool iluminada)
    {
        borde.Background = Glass.Relleno(Colors.White, iluminada ? 0.32 : 0.24, iluminada ? 0.18 : 0.12);
        borde.Stroke = Glass.CantoLuminoso(iluminada ? 0.7 : 0.55);
    }

    private void Pintar()
    {
        if (opciones is null) return;
        foreach (var (clave, borde) in opciones)
        {
            var activa = clave == Active;
            borde.BackgroundColor = Reposo;
            borde.Shadow = null!;
            if (activa) PintarActiva(borde, false);
            else
            {
                borde.Background = null!;
                borde.Stroke = new SolidColorBrush(Colors.Transparent);
            }
            borde.Padding = Compact ? new Thickness(0) : new Thickness(12, 0);
            if (borde.Content is not Grid fila) continue;
            if (fila.ColumnDefinitions.Count > 0) fila.ColumnDefinitions[0].Width = Compact ? GridLength.Star : new GridLength(24);
            foreach (var hijo in fila.Children)
            {
                if (hijo is Label etiqueta)
                {
                    etiqueta.IsVisible = !Compact;
                    etiqueta.FontFamily = activa ? Ds.FuenteSemi : Ds.FuenteMedia;
                }
            }
        }
        Separador.Margin = Compact ? new Thickness(12, 8) : new Thickness(10, 8);
    }

    private async void OnEntrar(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Add(borde);
        if (EsActiva(borde)) PintarActiva(borde, true);
        else borde.BackgroundColor = BajoPuntero;
        await borde.ScaleToAsync(1.02, 150, Easing.CubicOut);
    }

    private async void OnSalir(object? sender, PointerEventArgs e)
    {
        if (sender is not Border borde) return;
        bajoPuntero.Remove(borde);
        if (EsActiva(borde)) PintarActiva(borde, false);
        else borde.BackgroundColor = Reposo;
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
