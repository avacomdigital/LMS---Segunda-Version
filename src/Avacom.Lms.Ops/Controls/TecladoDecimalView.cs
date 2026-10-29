using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// El teclado numérico táctil de una puntuación (Calificaciones · ajuste de una nota): dígitos, la coma decimal y «Borrar». El nodo principal del aula NO tiene teclado y el del
/// sistema no se llama nunca: lo que se marca se ve en una pantallita encima del teclado. Lo marcado lo gobierna <c>EntradaDecimal</c> (a lo sumo tres cifras enteras y dos
/// decimales, sin ceros a la izquierda); si el valor es válido o no lo dice quien lo usa con <c>GradebookTexto.LeerPuntaje</c>, con palabras.
///
/// Misma familia que <c>TecladoPinView</c> (teclas con filo, un toque una marca, descarte del segundo <c>Clicked</c> de la MISMA tecla dentro de 180 ms por el doble evento de WinUI),
/// con las teclas más grandes: 88 × 60. Nunca escribe lo marcado en ningún registro.
/// </summary>
public sealed class TecladoDecimalView : ContentView
{
    private readonly EntradaDecimal _entrada = new();
    private readonly Label _pantalla;
    private readonly Label _unidad;
    private readonly Grid _teclas = new();
    private readonly List<Button> _botones = [];
    private bool _habilitado = true;
    private double _teclaAncho = 88, _teclaAlto = 60;

    /// <summary>Cambió lo marcado.</summary>
    public event EventHandler? TextoCambiado;

    public TecladoDecimalView()
    {
        _pantalla = new Label
        {
            FontFamily = Ds.FuenteMedia, FontSize = 38, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End,
            AutomationId = "teclado-decimal-valor",
        };
        _unidad = new Label { Text = "de 100", FontFamily = Ds.FuenteLigera, FontSize = 16, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.End, Margin = new Thickness(0, 0, 0, 6) };
        var linea = new HorizontalStackLayout { Spacing = 10, HorizontalOptions = LayoutOptions.End };
        linea.Add(_pantalla);
        linea.Add(_unidad);
        var visor = new Border
        {
            BackgroundColor = Ds.Lienzo, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(18, 8), HeightRequest = 64,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = linea,
        };
        var pila = new VerticalStackLayout { Spacing = 12, HorizontalOptions = LayoutOptions.Center };
        pila.Add(visor);
        pila.Add(_teclas);
        Content = pila;
        SemanticProperties.SetDescription(this, "Teclado numérico para marcar la puntuación");
        Reconstruir();
        Pintar();
    }

    // ------------------------------------------------------------------------------------------ estado

    /// <summary>Lo marcado, con punto decimal («85», «85.5»). Lo que lee <c>GradebookTexto.LeerPuntaje</c>.</summary>
    public string Texto => _entrada.Texto;

    public bool EstaVacio => _entrada.EstaVacia;

    public double TeclaAncho { get => _teclaAncho; set { _teclaAncho = value; Reconstruir(); } }
    public double TeclaAlto { get => _teclaAlto; set { _teclaAlto = value; Reconstruir(); } }

    /// <summary>Apagado, las teclas no responden (mientras el nodo contesta).</summary>
    public bool Habilitado
    {
        get => _habilitado;
        set { _habilitado = value; foreach (var b in _botones) b.IsEnabled = value; Opacity = value ? 1 : 0.55; }
    }

    public void Limpiar()
    {
        if (_entrada.EstaVacia) return;
        _entrada.Limpiar();
        Pintar();
        TextoCambiado?.Invoke(this, EventArgs.Empty);
    }

    // ------------------------------------------------------------------------------------ construcción

    private void Reconstruir()
    {
        _teclas.Children.Clear();
        _teclas.RowDefinitions.Clear();
        _teclas.ColumnDefinitions.Clear();
        _botones.Clear();
        _teclas.RowSpacing = 10;
        _teclas.ColumnSpacing = 10;
        _teclas.HorizontalOptions = LayoutOptions.Center;
        for (var f = 0; f < 4; f++) _teclas.RowDefinitions.Add(new RowDefinition(_teclaAlto));
        for (var c = 0; c < 3; c++) _teclas.ColumnDefinitions.Add(new ColumnDefinition(_teclaAncho));

        // 1 2 3 / 4 5 6 / 7 8 9 / , 0 Borrar
        for (var n = 1; n <= 9; n++)
        {
            var digito = (char)('0' + n);      // una copia por tecla: la variable del for es una sola
            Poner(Tecla(digito.ToString(), () => _entrada.Digito(digito), $"teclado-decimal-{digito}", $"Número {digito}"), (n - 1) / 3, (n - 1) % 3);
        }
        Poner(Tecla(",", _entrada.Separador, "teclado-decimal-coma", "Coma decimal"), 3, 0);
        Poner(Tecla("0", () => _entrada.Digito('0'), "teclado-decimal-0", "Número 0"), 3, 1);
        Poner(Tecla("Borrar", _entrada.Borrar, "teclado-decimal-borrar", "Borrar el último número", secundaria: true), 3, 2);
        Habilitado = _habilitado;
    }

    private void Poner(Button boton, int fila, int columna)
    {
        _teclas.Add(boton, columna, fila);
        _botones.Add(boton);
    }

    private Button Tecla(string texto, Func<bool> alTocar, string automationId, string descripcion, bool secundaria = false)
    {
        var tamano = Math.Min(_teclaAncho, _teclaAlto);
        var boton = new Button
        {
            Text = texto, AutomationId = automationId, WidthRequest = _teclaAncho, HeightRequest = _teclaAlto,
            CornerRadius = (int)Math.Min(18, tamano / 3), BorderWidth = 1, BorderColor = Ds.Filo,
            FontSize = secundaria ? 17 : Math.Clamp(tamano * 0.42, 20, 32), FontFamily = Ds.FuenteMedia, TextColor = Ds.Tinta,
            BackgroundColor = secundaria ? Color.FromArgb("#FFF5F6F8") : Colors.White, Padding = new Thickness(0),
        };
        SemanticProperties.SetDescription(boton, descripcion);
        // Un toque, una marca: sólo se escucha Clicked y se descarta el segundo de la MISMA tecla dentro de 180 ms (el doble evento de WinUI).
        long ultimo = 0;
        boton.Clicked += (_, _) =>
        {
            if (!_habilitado) return;
            var ahora = Environment.TickCount64;
            if (ahora - ultimo < 180) return;
            ultimo = ahora;
            if (alTocar())
            {
                Pintar();
                TextoCambiado?.Invoke(this, EventArgs.Empty);
            }
        };
        return boton;
    }

    private void Pintar()
    {
        _pantalla.Text = _entrada.EstaVacia ? "—" : _entrada.Mostrado;
        _pantalla.TextColor = _entrada.EstaVacia ? Ds.TintaSuave : Ds.Tinta;
        SemanticProperties.SetDescription(_pantalla, _entrada.EstaVacia ? "Todavía no marcaste nada" : $"Marcaste {_entrada.Mostrado}");
    }
}
