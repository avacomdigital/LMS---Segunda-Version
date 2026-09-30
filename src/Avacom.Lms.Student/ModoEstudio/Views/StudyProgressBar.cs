using Avacom.Lms.Student.ModoEstudio.Converters;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.ModoEstudio.Views;

/// <summary>
/// La barra de progreso de las tarjetas: pista gris (#E9E9E9) de 8 px con relleno redondeado (verde para la lección, azul para una
/// descarga). Son dos columnas de pesos «estrella» (<see cref="ProgressToWidthConverter"/>), así que no necesita saber su ancho, y cuando
/// el valor cambia el relleno se desliza en 280 ms en vez de saltar. No usa Path ni formas vectoriales: sólo <see cref="Border"/>.
/// </summary>
public sealed class StudyProgressBar : ContentView
{
    public static readonly BindableProperty ProgressProperty =
        BindableProperty.Create(nameof(Progress), typeof(double), typeof(StudyProgressBar), 0d, propertyChanged: (b, o, n) => ((StudyProgressBar)b).AlCambiar((double)o, (double)n));

    public static readonly BindableProperty FillColorProperty =
        BindableProperty.Create(nameof(FillColor), typeof(Color), typeof(StudyProgressBar), Color.FromArgb("#019D60"),
            propertyChanged: (b, o, n) => ((StudyProgressBar)b)._relleno.BackgroundColor = (Color)n);

    public static readonly BindableProperty TrackColorProperty =
        BindableProperty.Create(nameof(TrackColor), typeof(Color), typeof(StudyProgressBar), Color.FromArgb("#E9E9E9"),
            propertyChanged: (b, o, n) => ((StudyProgressBar)b)._pista.BackgroundColor = (Color)n);

    public static readonly BindableProperty BarHeightProperty =
        BindableProperty.Create(nameof(BarHeight), typeof(double), typeof(StudyProgressBar), 8d,
            propertyChanged: (b, o, n) => ((StudyProgressBar)b)._pista.HeightRequest = (double)n);

    private const string Animacion = "estudio-progreso";
    private readonly Grid _rejilla;
    private readonly Border _pista;
    private readonly Border _relleno;
    private double _mostrado;

    public StudyProgressBar()
    {
        _rejilla = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(ProgressToWidthConverter.Fill(0)), new ColumnDefinition(ProgressToWidthConverter.Rest(0))],
        };
        _relleno = new Border
        {
            BackgroundColor = FillColor,
            StrokeThickness = 0,
            StrokeShape = new RoundRectangle { CornerRadius = 999 },
        };
        _rejilla.Add(_relleno, 0, 0);
        _pista = new Border
        {
            BackgroundColor = TrackColor,
            StrokeThickness = 0,
            HeightRequest = BarHeight,
            StrokeShape = new RoundRectangle { CornerRadius = 999 },
            Content = _rejilla,
            Padding = 0,
        };
        Content = _pista;
        HorizontalOptions = LayoutOptions.Fill;
        VerticalOptions = LayoutOptions.Center;
        SemanticProperties.SetDescription(this, "Progreso");
        Aplicar(Progress);
    }

    /// <summary>De 0 a 1.</summary>
    public double Progress { get => (double)GetValue(ProgressProperty); set => SetValue(ProgressProperty, value); }
    public Color FillColor { get => (Color)GetValue(FillColorProperty); set => SetValue(FillColorProperty, value); }
    public Color TrackColor { get => (Color)GetValue(TrackColorProperty); set => SetValue(TrackColorProperty, value); }
    public double BarHeight { get => (double)GetValue(BarHeightProperty); set => SetValue(BarHeightProperty, value); }

    private void AlCambiar(double antes, double ahora)
    {
        ahora = Math.Clamp(ahora, 0, 1);
        this.AbortAnimation(Animacion);
        // Sin ventana todavía, o un salto insignificante: se pinta directo (una tarjeta recién creada no «llena» su barra desde cero).
        if (!IsLoaded || Math.Abs(ahora - _mostrado) < 0.005 || Handler is null)
        {
            Aplicar(ahora);
            return;
        }
        new Animation(Aplicar, _mostrado, ahora, Easing.CubicOut).Commit(this, Animacion, 16, 280);
    }

    private void Aplicar(double valor)
    {
        _mostrado = Math.Clamp(valor, 0, 1);
        _rejilla.ColumnDefinitions[0].Width = ProgressToWidthConverter.Fill(_mostrado);
        _rejilla.ColumnDefinitions[1].Width = ProgressToWidthConverter.Rest(_mostrado);
        _relleno.IsVisible = _mostrado > 0.0005;
    }
}
