using System.Runtime.CompilerServices;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Examen;

/// <summary>Una opción de la hoja: <c>Clave</c> es lo que se devuelve; <c>Rotulo</c>, lo que se lee en el botón. <c>Principal</c> la pinta como la acción destacada.</summary>
internal sealed record OpcionDeHoja(string Clave, string Rotulo, bool Principal = false);

/// <summary>
/// La hoja de opciones del examen: una tarjeta al centro, sobre un velo tenue, con botones grandes. Es el mismo patrón que <c>LanzarActividadPanel</c> (overlay con
/// <see cref="PedirAsync"/> que devuelve lo elegido) para todo lo que en otras pantallas pediría escribir: los motivos de una admisión, de una anulación, de un
/// cierre o de una bajada de nivel son frases que se tocan; el nodo principal no tiene teclado.
///
/// Reglas: cada opción mide 64 px; tocar una opción es la confirmación (nunca se pregunta dos veces); «Cancelar» y tocar fuera devuelven <c>null</c> y no
/// cambian nada. La tarjeta ocupa el tercio central de la ventana, de 1/6 a 5/6 del alto (la composición de tercios de las pantallas con tarjeta). Una segunda
/// llamada a <see cref="PedirAsync"/> cancela la anterior devolviéndole <c>null</c>; ocultar la hoja desde fuera también la cancela. Usar desde el hilo de interfaz.
/// </summary>
internal sealed class HojaDeOpciones : ContentView
{
    private readonly Grid _raiz = new();
    private readonly Border _tarjeta;
    private readonly Label _titulo, _texto;
    private readonly VerticalStackLayout _opciones = new() { Spacing = 10 };
    private readonly ScrollView _desplazable;
    private readonly ContentView _cancelar = new();
    private TaskCompletionSource<string?>? _pendiente;

    public HojaDeOpciones()
    {
        IsVisible = false;
        ZIndex = 50;

        // El velo es hermano de la tarjeta (no su padre): un toque dentro de la tarjeta nunca llega aquí.
        var velo = new Border { BackgroundColor = Color.FromArgb("#73141417"), StrokeThickness = 0 };
        var tocar = new TapGestureRecognizer();
        tocar.Tapped += (_, _) => Completar(null, ocultar: true);
        velo.GestureRecognizers.Add(tocar);

        _titulo = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        _texto = new Label { FontFamily = Ds.FuenteLigera, FontSize = 16, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap };
        _desplazable = new ScrollView { Content = _opciones };

        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(_titulo);
        pila.Add(_texto);
        pila.Add(_desplazable);
        pila.Add(_cancelar);

        _tarjeta = new Border
        {
            BackgroundColor = Ds.SuperficieContenido, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande }, Padding = new Thickness(28, 24),
            HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Content = pila,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 12), Radius = 32, Opacity = 0.28f },
        };
        _raiz.Add(velo);
        _raiz.Add(_tarjeta);
        _raiz.SizeChanged += OnRaizSizeChanged;
        Content = _raiz;
    }

    /// <summary>La tarjeta en el tercio central: un tercio del ancho y, como mucho, de 1/6 a 5/6 del alto (4/6). El cuerpo de opciones se desplaza si no cabe.</summary>
    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (_raiz.Width <= 0 || _raiz.Height <= 0) return;
        _tarjeta.WidthRequest = Math.Max(480, _raiz.Width / 3);
        var alto = _raiz.Height * 4 / 6;
        _tarjeta.MaximumHeightRequest = alto;
        _desplazable.MaximumHeightRequest = Math.Max(150, alto - 300);
    }

    /// <summary>
    /// Muestra la hoja y espera. Devuelve la <see cref="OpcionDeHoja.Clave"/> tocada o <c>null</c> si se cancela (botón, tocar fuera, otra llamada, ocultar el panel).
    /// La hoja se oculta sola al terminar.
    /// </summary>
    public Task<string?> PedirAsync(string titulo, string? texto, IReadOnlyList<OpcionDeHoja> opciones, string cancelar = "Cancelar")
    {
        Completar(null, ocultar: false);
        _titulo.Text = titulo;
        _texto.Text = texto;
        _texto.IsVisible = !string.IsNullOrWhiteSpace(texto);
        _opciones.Clear();
        var indice = 0;
        foreach (var opcion in opciones)
        {
            var clave = opcion.Clave;
            var boton = Ds.Boton(opcion.Rotulo, opcion.Principal ? Ds.Rango.Primary : Ds.Rango.Secondary, (_, _) => Completar(clave, ocultar: true), 64);
            boton.HorizontalOptions = LayoutOptions.Fill;
            boton.AutomationId = $"hoja-opcion-{indice++}";
            var capsula = Ds.Capsula(boton);
            capsula.HorizontalOptions = LayoutOptions.Fill;
            _opciones.Add(capsula);
        }
        var cancela = Ds.Boton(cancelar, Ds.Rango.Quiet, (_, _) => Completar(null, ocultar: true), 56);
        cancela.AutomationId = "hoja-cancelar";
        cancela.HorizontalOptions = LayoutOptions.Fill;
        _cancelar.Content = cancela;

        var espera = new TaskCompletionSource<string?>(TaskCreationOptions.RunContinuationsAsynchronously);
        _pendiente = espera;
        IsVisible = true;
        return espera.Task;
    }

    /// <summary>
    /// Pide un motivo entre frases prehechas (el nodo principal no tiene teclado). Devuelve la frase tocada o <c>null</c> si se cancela. Tocar la frase es la
    /// confirmación: la hoja no vuelve a preguntar.
    /// </summary>
    public async Task<string?> PedirMotivoAsync(string titulo, string? texto, IReadOnlyList<string> motivos)
    {
        var opciones = motivos.Select((m, i) => new OpcionDeHoja(i.ToString(System.Globalization.CultureInfo.InvariantCulture), m)).ToList();
        var clave = await PedirAsync(titulo, texto, opciones);
        return clave is not null && int.TryParse(clave, out var i) && i >= 0 && i < motivos.Count ? motivos[i] : null;
    }

    /// <summary>Si el host oculta la hoja mientras hay una petición abierta, la petición termina en cancelación.</summary>
    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName == nameof(IsVisible) && !IsVisible) Completar(null, ocultar: false);
    }

    /// <summary>Si la hoja sale del árbol visual (la pantalla se cierra), nadie se queda esperando.</summary>
    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is null) Completar(null, ocultar: false);
    }

    private void Completar(string? resultado, bool ocultar)
    {
        var espera = Interlocked.Exchange(ref _pendiente, null);
        if (espera is null) return;
        if (ocultar) IsVisible = false;
        espera.TrySetResult(resultado);
    }
}
