using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student;

/// <summary>
/// RF-23: mientras dure una sesión de visitante, cada pantalla lleva arriba una banda amarilla permanente con <see cref="MensajesDeAcceso.BandaVisitante"/>.
/// No es un aviso que se va (eso es <see cref="Avisos"/>): es un recordatorio fijo de que lo que se hace no se guarda en el historial de nadie.
///
/// <para>Se pone al navegar (<see cref="AppShell"/>) sin mover ninguna vista de su contenedor: la raíz de cada pantalla de Student es una rejilla, así que
/// se le inserta una fila de arriba y se baja una fila a cada hijo. Re-colgar las vistas recargaría una WebView en plena clase; cambiar su fila, no.
/// Al cerrar la visita, la banda se quita de la pantalla que vuelva a verse.</para>
/// </summary>
public static class BandaDeVisitante
{
    private static readonly ConditionalWeakTable<Page, Border> Puestas = new();

    public static void Aplicar(Page? pagina)
    {
        try
        {
            if (pagina is not ContentPage { Content: Grid raiz } contenido) return;
            var debe = Sesion.EsVisitante && contenido is not Pages.ConnectionPage;
            var tiene = Puestas.TryGetValue(contenido, out var banda);
            if (debe && !tiene) Poner(contenido, raiz);
            else if (!debe && tiene) Quitar(contenido, raiz, banda!);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "BandaDeVisitante.Aplicar", ex); }
    }

    private static void Poner(ContentPage pagina, Grid raiz)
    {
        if (raiz.RowDefinitions.Count == 0) raiz.RowDefinitions.Add(new RowDefinition(GridLength.Star));
        foreach (var hijo in raiz.Children.OfType<BindableObject>()) Grid.SetRow(hijo, Grid.GetRow(hijo) + 1);
        raiz.RowDefinitions.Insert(0, new RowDefinition(GridLength.Auto));
        var banda = new Border
        {
            BackgroundColor = Ds.Alerta, StrokeThickness = 0, Padding = new Thickness(18, 10), ZIndex = 90, AutomationId = "banda-visitante",
            Content = new Label
            {
                Text = MensajesDeAcceso.BandaVisitante, FontSize = 15, FontFamily = Ds.FuenteMedia, TextColor = Ds.Tinta,
                HorizontalTextAlignment = TextAlignment.Center, LineBreakMode = LineBreakMode.WordWrap,
            },
        };
        SemanticProperties.SetDescription(banda, MensajesDeAcceso.BandaVisitante);
        Grid.SetRow(banda, 0);
        Grid.SetColumnSpan(banda, Math.Max(1, raiz.ColumnDefinitions.Count));
        raiz.Add(banda);
        Puestas.Add(pagina, banda);
    }

    private static void Quitar(ContentPage pagina, Grid raiz, Border banda)
    {
        raiz.Remove(banda);
        Puestas.Remove(pagina);
        if (raiz.RowDefinitions.Count > 0) raiz.RowDefinitions.RemoveAt(0);
        foreach (var hijo in raiz.Children.OfType<BindableObject>()) Grid.SetRow(hijo, Math.Max(0, Grid.GetRow(hijo) - 1));
    }
}
