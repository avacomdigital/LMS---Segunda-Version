using System.Diagnostics;
using Avacom.Lms.Ui.Graphics;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Lápiz 3D decorativo: carga <c>Resources/Raw/models/lapiz.glb</c> (enlazado desde assets/3d/lapiz.glb) y lo pinta
/// con <see cref="RotatingModelDrawable"/> en un <see cref="GraphicsView"/> transparente: el lápiz gira despacio sobre
/// su eje vertical, inclinado unos grados, con una flotación casi imperceptible y una entrada en fundido con escala
/// (easeOutCubic, 0,8 s). Es sólo decorativo (<c>InputTransparent</c>) y ocupa el área que se le asigne desde XAML
/// (WidthRequest/HeightRequest o una celda del Grid): el encuadre se recalcula en cada cuadro con el tamaño real.
///
/// Por qué nativo y no un WebView con Three.js: en WinUI 3 el WebView2 normal vive en un HWND hijo y su fondo
/// «transparente» sólo deja ver el fondo de la ventana, no el XAML de detrás; y el WebView2 por composición exige el
/// compositor de sistema, que desplaza el renderizado de WinUI. Un render por software de un modelo de cien
/// triángulos es transparente por construcción, idéntico en Windows y Android y no necesita ni WebView ni 2 MB de
/// JavaScript. El visor Three.js equivalente queda en assets/3d/visor-web para la versión web.
///
/// Ciclo de vida: el temporizador de render (≈60 cuadros/s, con tiempo delta) arranca al entrar en el árbol visual
/// (Loaded) y se detiene al salir (Unloaded: se navegó a otra página) o al llamar a <see cref="Pausar"/>.
/// </summary>
public partial class Pencil3DView : ContentView
{
    public static readonly BindableProperty SecondsPerTurnProperty =
        BindableProperty.Create(nameof(SecondsPerTurn), typeof(double), typeof(Pencil3DView), 12.0, propertyChanged: AlCambiarOpcion);

    public static readonly BindableProperty TiltDegreesProperty =
        BindableProperty.Create(nameof(TiltDegrees), typeof(double), typeof(Pencil3DView), 8.0, propertyChanged: AlCambiarOpcion);

    public static readonly BindableProperty FloatPixelsProperty =
        BindableProperty.Create(nameof(FloatPixels), typeof(double), typeof(Pencil3DView), 3.0, propertyChanged: AlCambiarOpcion);

    public static readonly BindableProperty FillRatioProperty =
        BindableProperty.Create(nameof(FillRatio), typeof(double), typeof(Pencil3DView), 0.78, propertyChanged: AlCambiarOpcion);

    public static readonly BindableProperty ModelFileProperty =
        BindableProperty.Create(nameof(ModelFile), typeof(string), typeof(Pencil3DView), "models/lapiz.glb");

    private readonly RotatingModelDrawable dibujo = new();
    private readonly Stopwatch cronometro = new();
    private IDispatcherTimer? reloj;
    private bool cargando;
    private bool aparecido;

    public Pencil3DView()
    {
        InitializeComponent();
        Lienzo.Drawable = dibujo;
        AplicarOpciones();
        Loaded += (_, _) => Reanudar();
        Unloaded += (_, _) => Pausar();
    }

    /// <summary>Segundos por vuelta completa sobre el eje vertical (10–16: expuesto, no girando).</summary>
    public double SecondsPerTurn { get => (double)GetValue(SecondsPerTurnProperty); set => SetValue(SecondsPerTurnProperty, value); }

    /// <summary>Inclinación fija, en grados, sobre un eje secundario (5–12) para que se lea el volumen.</summary>
    public double TiltDegrees { get => (double)GetValue(TiltDegreesProperty); set => SetValue(TiltDegreesProperty, value); }

    /// <summary>Amplitud de la flotación en píxeles (2–5): se percibe apenas.</summary>
    public double FloatPixels { get => (double)GetValue(FloatPixelsProperty); set => SetValue(FloatPixelsProperty, value); }

    /// <summary>Fracción del área asignada que ocupa el lápiz (0,70–0,85).</summary>
    public double FillRatio { get => (double)GetValue(FillRatioProperty); set => SetValue(FillRatioProperty, value); }

    /// <summary>Ruta del modelo dentro de Resources/Raw (MauiAsset). Debe ser un .glb pequeño y sin texturas.</summary>
    public string ModelFile { get => (string)GetValue(ModelFileProperty); set => SetValue(ModelFileProperty, value); }

    /// <summary>Detiene el bucle de render. Seguro en cualquier momento.</summary>
    public void Pausar()
    {
        reloj?.Stop();
        cronometro.Stop();
    }

    /// <summary>Carga el modelo si hace falta y (re)arranca el bucle de render.</summary>
    public void Reanudar()
    {
        if (dibujo.Modelo is null) _ = CargarAsync();
        reloj ??= CrearReloj();
        cronometro.Restart();
        reloj.Start();
    }

    private IDispatcherTimer CrearReloj()
    {
        var temporizador = Dispatcher.CreateTimer();
        temporizador.Interval = TimeSpan.FromMilliseconds(16);
        temporizador.IsRepeating = true;
        temporizador.Tick += (_, _) => Cuadro();
        return temporizador;
    }

    private void Cuadro()
    {
        dibujo.Avanzar(cronometro.Elapsed.TotalSeconds);
        cronometro.Restart();
        if (dibujo.Modelo is not null) Lienzo.Invalidate();
    }

    private async Task CargarAsync()
    {
        if (cargando) return;
        cargando = true;
        try
        {
            var archivo = ModelFile;
            using var flujo = await FileSystem.OpenAppPackageFileAsync(archivo);
            var malla = await Task.Run(() => GlbMesh.Leer(flujo));
            dibujo.Modelo = malla;
            Lienzo.Invalidate();
            if (!aparecido)
            {
                aparecido = true;
                _ = Lienzo.FadeToAsync(1, 800, Easing.CubicOut);
                _ = Lienzo.ScaleToAsync(1, 800, Easing.CubicOut);
            }
        }
        catch (Exception error)
        {
            Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ui", $"Pencil3DView · cargar {ModelFile}", error);
        }
        finally
        {
            cargando = false;
        }
    }

    private static void AlCambiarOpcion(BindableObject bindable, object oldValue, object newValue) => ((Pencil3DView)bindable).AplicarOpciones();

    private void AplicarOpciones()
    {
        dibujo.SecondsPerTurn = SecondsPerTurn;
        dibujo.TiltDegrees = TiltDegrees;
        dibujo.FloatPixels = FloatPixels;
        dibujo.FillRatio = FillRatio;
    }
}
