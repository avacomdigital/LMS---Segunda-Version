namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Etiqueta que se turna entre varias palabras con un fundido lento: opacidad 0 → 1 en <see cref="FadeMilliseconds"/>,
/// se mantiene en 1 durante <see cref="HoldMilliseconds"/>, vuelve a 0 y pasa a la siguiente palabra, en bucle. Las
/// palabras se dan separadas por «|» para poder escribirlas en XAML. Arranca al entrar en el árbol visual (Loaded) y se
/// detiene al salir (Unloaded), así que no consume nada en otras páginas. Sólo decorativa: conviene marcarla
/// <c>InputTransparent</c> en el XAML que la use.
/// </summary>
public class CyclingLabel : Label
{
    public static readonly BindableProperty WordsProperty =
        BindableProperty.Create(nameof(Words), typeof(string), typeof(CyclingLabel), string.Empty, propertyChanged: (b, _, _) => ((CyclingLabel)b).Reiniciar());

    public static readonly BindableProperty FadeMillisecondsProperty =
        BindableProperty.Create(nameof(FadeMilliseconds), typeof(int), typeof(CyclingLabel), 1400);

    public static readonly BindableProperty HoldMillisecondsProperty =
        BindableProperty.Create(nameof(HoldMilliseconds), typeof(int), typeof(CyclingLabel), 2000);

    private CancellationTokenSource? ciclo;

    public CyclingLabel()
    {
        Opacity = 0;
        Loaded += (_, _) => Iniciar();
        Unloaded += (_, _) => Detener();
    }

    /// <summary>Palabras separadas por «|», en el orden en que se muestran.</summary>
    public string Words { get => (string)GetValue(WordsProperty); set => SetValue(WordsProperty, value); }

    /// <summary>Duración de cada fundido (entrada y salida), en milisegundos.</summary>
    public int FadeMilliseconds { get => (int)GetValue(FadeMillisecondsProperty); set => SetValue(FadeMillisecondsProperty, value); }

    /// <summary>Tiempo que la palabra permanece con opacidad 1, en milisegundos.</summary>
    public int HoldMilliseconds { get => (int)GetValue(HoldMillisecondsProperty); set => SetValue(HoldMillisecondsProperty, value); }

    private void Iniciar()
    {
        if (ciclo is not null) return;
        ciclo = new CancellationTokenSource();
        _ = Ciclar(ciclo.Token);
    }

    private void Detener()
    {
        ciclo?.Cancel();
        ciclo = null;
        this.CancelAnimations();
        Opacity = 0;
    }

    private void Reiniciar()
    {
        if (ciclo is null) return;
        Detener();
        Iniciar();
    }

    private async Task Ciclar(CancellationToken token)
    {
        var palabras = Words.Split('|', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (palabras.Length == 0) return;
        var fundido = (uint)Math.Max(0, FadeMilliseconds);
        var espera = Math.Max(0, HoldMilliseconds);
        var i = 0;
        try
        {
            while (!token.IsCancellationRequested)
            {
                Text = palabras[i];
                await this.FadeToAsync(1, fundido, Easing.SinInOut);
                await Task.Delay(espera, token);
                await this.FadeToAsync(0, fundido, Easing.SinInOut);
                i = (i + 1) % palabras.Length;
            }
        }
        catch (OperationCanceledException)
        {
            // Se detuvo el ciclo: la vista salió del árbol.
        }
    }
}
