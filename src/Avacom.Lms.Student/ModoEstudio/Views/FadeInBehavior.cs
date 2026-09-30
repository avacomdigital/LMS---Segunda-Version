namespace Avacom.Lms.Student.ModoEstudio.Views;

/// <summary>
/// La aparición de una tarjeta: un fundido de 180 ms al entrar a pantalla. Discreto a propósito (sin desplazamientos ni rebotes). Si el
/// elemento nunca llega a mostrarse (se creó fuera de pantalla), un temporizador de seguridad lo deja visible: una tarjeta jamás se queda
/// invisible.
/// </summary>
public sealed class FadeInBehavior : Behavior<VisualElement>
{
    private const uint Duracion = 180;
    private VisualElement? _elemento;

    protected override void OnAttachedTo(VisualElement elemento)
    {
        base.OnAttachedTo(elemento);
        _elemento = elemento;
        elemento.Opacity = 0;
        elemento.Loaded += AlCargarse;
        elemento.Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(700), () =>
        {
            if (_elemento is { Opacity: < 1 } visible) visible.Opacity = 1;
        });
    }

    protected override void OnDetachingFrom(VisualElement elemento)
    {
        elemento.Loaded -= AlCargarse;
        _elemento = null;
        base.OnDetachingFrom(elemento);
    }

    private async void AlCargarse(object? remitente, EventArgs e)
    {
        if (remitente is not VisualElement elemento) return;
        elemento.Loaded -= AlCargarse;
        try { await elemento.FadeToAsync(1, Duracion, Easing.CubicOut); }
        catch { elemento.Opacity = 1; }
    }
}
