using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// El teclado numérico propio del PIN (RF-00a): una sola implementación para OPS y Student. Seis puntos para el PIN maestro, de cuatro a seis para el PIN
/// del alumno. Nunca llama al teclado del sistema (el nodo del aula no tiene teclado y la tableta es compartida): el PIN se marca tocando, y los puntos
/// sólo dicen cuántos dígitos van, no cuáles.
///
/// <para><b>Medidas.</b> Por defecto 68 × 52: del mismo orden que los botones del acceso, para que el teclado no domine la tarjeta. Cada pantalla ajusta
/// <see cref="TeclaAncho"/> y <see cref="TeclaAlto"/> a su composición (tableta o nodo táctil).</para>
///
/// <para><b>Cuándo termina.</b> Con <see cref="LongitudMinima"/> igual a <see cref="Longitud"/> (el PIN maestro) el PIN se entrega solo al llegar al último
/// dígito. Con una mínima menor (el PIN del alumno, de 4 a 6) aparece «Listo», que se enciende al alcanzar la mínima; si se llega a la máxima también se
/// entrega solo. Quien recibe <see cref="PinCompleto"/> decide qué hacer y llama a <see cref="Limpiar"/> o <see cref="Sacudir"/> según el resultado.</para>
///
/// <para>El PIN no se escribe en ningún registro, ni siquiera de depuración.</para>
/// </summary>
public sealed class TecladoPinView : ContentView
{
    private static readonly Color Fondo = Color.FromArgb("#FFFFFFFF");
    private static readonly Color PuntoVacio = Color.FromArgb("#FFD4D4D8");

    private readonly VerticalStackLayout _pila = new() { Spacing = 18, HorizontalOptions = LayoutOptions.Center };
    private readonly HorizontalStackLayout _puntos = new() { Spacing = 14, HorizontalOptions = LayoutOptions.Center };
    private readonly Grid _teclas = new();
    private readonly List<Button> _botones = [];
    private readonly List<Border> _marcas = [];
    private Button? _listo;
    private string _pin = string.Empty;
    private bool _habilitado = true;

    private int _longitud = 6, _longitudMinima;
    private double _teclaAncho = 68, _teclaAlto = 52, _separacion = 10;
    private Color _acento = Ds.Rojo;

    /// <summary>Se entrega el PIN completo. El argumento es el PIN tal como se marcó (sólo dígitos).</summary>
    public event EventHandler<string>? PinCompleto;
    /// <summary>Cambió la cantidad de dígitos (para habilitar un botón propio, por ejemplo).</summary>
    public event EventHandler? PinCambiado;

    public TecladoPinView()
    {
        Reconstruir();
        _pila.Add(_puntos);
        _pila.Add(_teclas);
        Content = _pila;
        SemanticProperties.SetDescription(this, "Teclado numérico para marcar el PIN");
    }

    // ------------------------------------------------------------------------------------------------------------------------ configuración

    /// <summary>Máximo de dígitos (y cantidad de puntos): 6 para el PIN maestro, de 4 a 6 para el del alumno.</summary>
    public int Longitud
    {
        get => _longitud;
        set { value = Math.Clamp(value, 1, 12); if (value == _longitud) return; _longitud = value; if (_pin.Length > value) _pin = _pin[..value]; Reconstruir(); }
    }

    /// <summary>Mínimo de dígitos para poder entregar. 0 o igual a <see cref="Longitud"/>: se entrega solo al llegar al último dígito, sin botón «Listo».</summary>
    public int LongitudMinima
    {
        get => _longitudMinima;
        set { if (value == _longitudMinima) return; _longitudMinima = value; Reconstruir(); }
    }

    public double TeclaAncho { get => _teclaAncho; set { _teclaAncho = value; Reconstruir(); } }
    public double TeclaAlto { get => _teclaAlto; set { _teclaAlto = value; Reconstruir(); } }
    public double Separacion { get => _separacion; set { _separacion = value; Reconstruir(); } }
    /// <summary>El color de los puntos llenos y de «Listo».</summary>
    public Color Acento { get => _acento; set { _acento = value; Reconstruir(); } }

    /// <summary>Los puntos que dicen cuántos dígitos van. Se pueden ocultar si la pantalla ya los pinta de otra forma.</summary>
    public bool MostrarPuntos { get => _puntos.IsVisible; set => _puntos.IsVisible = value; }

    /// <summary>Apagado, las teclas no responden (mientras el nodo contesta, o la tableta está en pausa).</summary>
    public bool Habilitado
    {
        get => _habilitado;
        set { _habilitado = value; foreach (var b in _botones) b.IsEnabled = value && (b != _listo || EsEntregable); Opacity = value ? 1 : 0.55; }
    }

    // ------------------------------------------------------------------------------------------------------------------------ estado

    /// <summary>Los dígitos marcados hasta ahora. Quien lo lee es quien va a entregarlo; no lo guardes.</summary>
    public string Pin => _pin;

    public int Cantidad => _pin.Length;

    /// <summary>Borra lo marcado (después de entregarlo, o si el nodo lo rechazó). Los puntos vuelven a vacíos.</summary>
    public void Limpiar()
    {
        if (_pin.Length == 0) return;
        _pin = string.Empty;
        Pintar();
        PinCambiado?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>El PIN no fue: el teclado se sacude un instante y se vacía. Sin sonidos ni colores de «error».</summary>
    public async Task SacudirAsync()
    {
        foreach (var dx in new double[] { -12, 12, -8, 8, -4, 4, 0 })
        {
            await _pila.TranslateToAsync(dx, 0, 45, Easing.Linear);
        }
        Limpiar();
    }

    // ------------------------------------------------------------------------------------------------------------------------ construcción

    private bool ConBotonListo => _longitudMinima > 0 && _longitudMinima < _longitud;
    private bool EsEntregable => _pin.Length >= (ConBotonListo ? _longitudMinima : _longitud);

    private void Reconstruir()
    {
        _teclas.Children.Clear();
        _teclas.RowDefinitions.Clear();
        _teclas.ColumnDefinitions.Clear();
        _botones.Clear();
        _listo = null;
        _teclas.RowSpacing = _separacion;
        _teclas.ColumnSpacing = _separacion;
        _teclas.HorizontalOptions = LayoutOptions.Center;
        for (var f = 0; f < 4; f++) _teclas.RowDefinitions.Add(new RowDefinition(_teclaAlto));
        for (var c = 0; c < 3; c++) _teclas.ColumnDefinitions.Add(new ColumnDefinition(_teclaAncho));

        // 1 2 3 / 4 5 6 / 7 8 9 / Borrar 0 Listo
        for (var n = 1; n <= 9; n++)
        {
            var digito = n.ToString();   // una copia por tecla: la variable del for es una sola y terminaba en 10 (cada tecla marcaba «10»)
            Poner(Tecla(digito, () => Marcar(digito), $"tecla-{digito}", $"Número {digito}"), (n - 1) / 3, (n - 1) % 3);
        }
        Poner(Tecla("Borrar", Borrar, "tecla-borrar", "Borrar el último número", secundaria: true), 3, 0);
        Poner(Tecla("0", () => Marcar("0"), "tecla-0", "Número 0"), 3, 1);
        if (ConBotonListo)
        {
            _listo = Tecla("Listo", Entregar, "tecla-listo", "Listo", destacada: true);
            Poner(_listo, 3, 2);
        }

        _puntos.Children.Clear();
        _marcas.Clear();
        for (var i = 0; i < _longitud; i++)
        {
            var marca = new Border
            {
                WidthRequest = 20, HeightRequest = 20, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = 10 },
                BackgroundColor = PuntoVacio,
            };
            _marcas.Add(marca);
            _puntos.Children.Add(marca);
        }
        Pintar();
        Habilitado = _habilitado;
    }

    private void Poner(Button boton, int fila, int columna)
    {
        _teclas.Add(boton, columna, fila);
        _botones.Add(boton);
    }

    private Button Tecla(string texto, Action alTocar, string automationId, string descripcion, bool secundaria = false, bool destacada = false)
    {
        var tamano = Math.Min(_teclaAncho, _teclaAlto);
        var boton = new Button
        {
            Text = texto, AutomationId = automationId, WidthRequest = _teclaAncho, HeightRequest = _teclaAlto,
            CornerRadius = (int)Math.Min(18, tamano / 3), BorderWidth = 1, BorderColor = Ds.Filo,
            // El número va grande; «Borrar» y «Listo» son palabras: más chicas para que quepan en una tecla de 46 px de alto.
            FontSize = secundaria || destacada ? Math.Clamp(tamano * 0.26, 14, 20) : Math.Clamp(tamano * 0.42, 20, 32),
            FontFamily = Ds.FuenteMedia, TextColor = destacada ? Colors.White : Ds.Tinta,
            BackgroundColor = destacada ? _acento : secundaria ? Color.FromArgb("#FFF1F1F1") : Fondo, Padding = new Thickness(0),
        };
        SemanticProperties.SetDescription(boton, descripcion);
        // Un toque, una marca. Sólo se escucha Clicked (no Pressed/Released: en WinUI cada toque llegaba dos veces) y, por si el sistema repite el
        // evento, se descarta el segundo Clicked de la MISMA tecla dentro de 180 ms (ninguna mano marca dos veces el mismo número tan rápido).
        long ultimo = 0;
        boton.Clicked += (_, _) =>
        {
            if (!_habilitado) return;
            var ahora = Environment.TickCount64;
            if (ahora - ultimo < 180) return;
            ultimo = ahora;
            alTocar();
        };
        return boton;
    }

    // ------------------------------------------------------------------------------------------------------------------------ comportamiento

    private void Marcar(string digito)
    {
        if (_pin.Length >= _longitud) return;
        _pin += digito;
        Pintar();
        PinCambiado?.Invoke(this, EventArgs.Empty);
        // Sin «Listo» el PIN se entrega solo al llegar al último dígito; con «Listo» también si se llega a la máxima.
        if (_pin.Length == _longitud) Entregar();
    }

    private void Borrar()
    {
        if (_pin.Length == 0) return;
        _pin = _pin[..^1];
        Pintar();
        PinCambiado?.Invoke(this, EventArgs.Empty);
    }

    private void Entregar()
    {
        if (!EsEntregable) return;
        PinCompleto?.Invoke(this, _pin);
    }

    private void Pintar()
    {
        for (var i = 0; i < _marcas.Count; i++) _marcas[i].BackgroundColor = i < _pin.Length ? _acento : PuntoVacio;
        if (_listo is not null) _listo.IsEnabled = _habilitado && EsEntregable;
        SemanticProperties.SetDescription(_puntos, $"{_pin.Length} de {_longitud} números marcados");
    }
}
