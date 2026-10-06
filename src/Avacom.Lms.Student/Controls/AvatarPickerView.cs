using Avacom.Lms.Student.Acceso;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Controls;

/// <summary>
/// RF-28 · TST-074: la cuadrícula de dibujos que el niño de preescolar toca en lugar de marcar un PIN. Doce dibujos (<see cref="Avatares"/>) en botones del orden de
/// los del acceso; tocar uno lo entrega al momento (<see cref="DibujoElegido"/>). El dibujo elegido se marca un instante y se suelta con <see cref="Limpiar"/>: no queda
/// a la vista de quien venga después.
///
/// <para>Cada dibujo es un emoji pintado como texto, no una geometría: así no hay trazos que Win2D tenga que recortar (un Path degenerado tumba los lienzos de
/// la ventana). Para la accesibilidad y la UI Automation cada botón se llama como su dibujo («Gato») y su AutomationId es <c>avatar-gato</c>.</para>
/// </summary>
public sealed class AvatarPickerView : ContentView
{
    private readonly Grid _rejilla = new() { HorizontalOptions = LayoutOptions.Center };
    private readonly Dictionary<string, Button> _botones = new(StringComparer.Ordinal);
    private double _lado = 56, _separacion = 8;
    private int _columnas = 4;
    private bool _habilitado = true;
    private string? _marcado;

    /// <summary>Se tocó un dibujo. El argumento es su clave («gato»), que es lo que viaja al nodo.</summary>
    public event EventHandler<string>? DibujoElegido;

    public AvatarPickerView()
    {
        Content = _rejilla;
        Construir();
        SemanticProperties.SetDescription(this, "Dibujos para entrar");
    }

    /// <summary>Lado de cada botón (56 por defecto: cómodo para un dedo de preescolar sin que la cuadrícula domine la tarjeta).</summary>
    public double Lado { get => _lado; set { _lado = Math.Max(44, value); Construir(); } }
    public double Separacion { get => _separacion; set { _separacion = value; Construir(); } }
    public int Columnas { get => _columnas; set { _columnas = Math.Clamp(value, 2, 6); Construir(); } }

    /// <summary>Apagado, los dibujos no responden (mientras el nodo contesta o la tableta está en pausa).</summary>
    public bool Habilitado
    {
        get => _habilitado;
        set { _habilitado = value; foreach (var b in _botones.Values) b.IsEnabled = value; Opacity = value ? 1 : 0.55; }
    }

    /// <summary>Resalta un dibujo (la primera vez que se elige uno nuevo, a la espera de la confirmación).</summary>
    public void Marcar(string? clave)
    {
        _marcado = clave;
        foreach (var (k, b) in _botones) Pintar(b, Avatares.Por(k)!, k == clave);
    }

    public void Limpiar() => Marcar(null);

    private void Construir()
    {
        _rejilla.Children.Clear();
        _rejilla.RowDefinitions.Clear();
        _rejilla.ColumnDefinitions.Clear();
        _botones.Clear();
        _rejilla.RowSpacing = _separacion;
        _rejilla.ColumnSpacing = _separacion;
        var filas = (int)Math.Ceiling(Avatares.Todos.Count / (double)_columnas);
        for (var c = 0; c < _columnas; c++) _rejilla.ColumnDefinitions.Add(new ColumnDefinition(_lado));
        for (var f = 0; f < filas; f++) _rejilla.RowDefinitions.Add(new RowDefinition(_lado));
        for (var i = 0; i < Avatares.Todos.Count; i++)
        {
            var avatar = Avatares.Todos[i];
            var boton = new Button
            {
                Text = avatar.Dibujo, FontSize = Math.Round(_lado * 0.46), Padding = 0, WidthRequest = _lado, HeightRequest = _lado,
                CornerRadius = (int)Math.Min(20, _lado / 3.5), BorderWidth = 1.5, AutomationId = $"avatar-{avatar.Clave}",
                FontFamily = OperatingSystem.IsWindows() ? "Segoe UI Emoji" : null,
            };
            SemanticProperties.SetDescription(boton, avatar.Nombre);
            Pintar(boton, avatar, avatar.Clave == _marcado);
            var clave = avatar.Clave;
            boton.Clicked += (_, _) => { if (_habilitado) DibujoElegido?.Invoke(this, clave); };
            boton.IsEnabled = _habilitado;
            _botones[clave] = boton;
            _rejilla.Add(boton, i % _columnas, i / _columnas);
        }
    }

    private static void Pintar(Button boton, Avatar avatar, bool marcado)
    {
        boton.BackgroundColor = Color.FromArgb(avatar.Color);
        boton.BorderColor = marcado ? Ds.Tinta : Ds.Filo;
        boton.BorderWidth = marcado ? 3 : 1.5;
        boton.Scale = marcado ? 1.06 : 1;
    }
}
