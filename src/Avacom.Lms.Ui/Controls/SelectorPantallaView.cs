using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Layouts;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Selector de pantalla de proyección: resolución (Automático · 1920×1080 · 3840×2160) y escala de Windows (80–200 %).
/// «Automático» mide la propia ventana y es lo normal; elegir un perfil acota el video al espacio que ese perfil deja a la
/// proyección (útil con un proyector o una pantalla grande cuyo escalado Windows reporta distinto de lo que se ve).
/// Sin teclado: todo son botones grandes. El perfil queda en <see cref="AjustesDePantalla"/> y los visores se reajustan solos.
/// </summary>
public sealed class SelectorPantallaView : ContentView
{
    private readonly VerticalStackLayout _raiz = new() { Spacing = 12 };

    /// <summary>El docente pulsó «Cerrar».</summary>
    public event EventHandler? Cerrado;

    public SelectorPantallaView()
    {
        Content = _raiz;
        Pintar();
    }

    private void Pintar()
    {
        _raiz.Clear();
        var actual = AjustesDePantalla.Actual;
        var detectado = AjustesDePantalla.Detectado();

        _raiz.Add(Ds.Titulo("Pantalla de proyección", 18));
        _raiz.Add(Ds.Secundario(detectado.EsAuto
            ? "El video se ajusta al tamaño de la ventana."
            : $"El equipo reporta {detectado.Rotulo}. El video se ajusta para verse entero.", 14));

        _raiz.Add(Ds.Secundario("Resolución", 13));
        var resoluciones = Fila();
        resoluciones.Add(Opcion("Automático", actual.EsAuto, () => AjustesDePantalla.Actual = PerfilDePantalla.Auto));
        resoluciones.Add(Opcion("1920×1080", actual.Resolucion == ResolucionPantalla.FullHd, () => Elegir(ResolucionPantalla.FullHd, actual, detectado)));
        resoluciones.Add(Opcion("3840×2160", actual.Resolucion == ResolucionPantalla.Uhd4k, () => Elegir(ResolucionPantalla.Uhd4k, actual, detectado)));
        _raiz.Add(resoluciones);

        _raiz.Add(Ds.Secundario("Escala de Windows", 13));
        var escalas = Fila();
        foreach (var escala in PerfilDePantalla.Escalas)
        {
            var e = escala;
            var boton = Opcion($"{e} %", !actual.EsAuto && actual.EscalaPct == e, () => AjustesDePantalla.Actual = actual with { EscalaPct = e });
            if (actual.EsAuto) { boton.Opacity = 0.4; if (boton is Border { Content: Button b }) b.IsEnabled = false; }
            escalas.Add(boton);
        }
        _raiz.Add(escalas);

        var cerrar = Ds.Boton("Cerrar", Ds.Rango.Quiet, (_, _) => Cerrado?.Invoke(this, EventArgs.Empty), 52);
        cerrar.HorizontalOptions = LayoutOptions.End;
        _raiz.Add(cerrar);
    }

    private static void Elegir(ResolucionPantalla resolucion, PerfilDePantalla actual, PerfilDePantalla detectado)
    {
        // Conserva la escala si ya había un perfil manual; si no, la que reporta Windows (80–200 %).
        var escala = !actual.EsAuto ? actual.EscalaPct : detectado.EsAuto ? 100 : detectado.EscalaPct;
        AjustesDePantalla.Actual = new PerfilDePantalla(resolucion, escala);
    }

    private static FlexLayout Fila() => new() { Wrap = FlexWrap.Wrap, Direction = FlexDirection.Row, JustifyContent = FlexJustify.Start, AlignItems = FlexAlignItems.Center };

    private View Opcion(string texto, bool elegida, Action alElegir)
    {
        var boton = Ds.Boton(texto, elegida ? Ds.Rango.Primary : Ds.Rango.Secondary, (_, _) => { alElegir(); Pintar(); }, 52);
        boton.FontSize = 16;
        var capsula = Ds.Capsula(boton);
        capsula.Margin = new Thickness(0, 0, 10, 10);
        return capsula;
    }
}
