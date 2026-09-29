using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student;

/// <summary>
/// Avisos tranquilizadores que no piden nada al alumno (MSG-020, MSG-024, sesión terminada): un cartel en la parte alta de la pantalla
/// visible, sin botones ni confirmación, que no capta toques y se va solo. Sirve para avisar sin retrasar lo que la persona estaba
/// haciendo (por ejemplo, entrar al menú cuando su sesión anterior se cerró en otra tableta). Nunca lleva códigos ni la palabra «error».
/// Se puede llamar desde cualquier hilo.
/// </summary>
public static class Avisos
{
    private static Border? _actual;
    private static Grid? _envoltorio;
    private static ContentPage? _pagina;
    private static View? _original;

    /// <summary>Muestra <paramref name="texto"/> sobre la pantalla actual durante unos segundos (por defecto 9).</summary>
    public static void Mostrar(string texto, TimeSpan? duracion = null)
    {
        MainThread.BeginInvokeOnMainThread(() =>
        {
            try { Poner(texto, duracion ?? TimeSpan.FromSeconds(9)); }
            catch (Exception ex) { Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("student", "Avisos.Mostrar", ex); }
        });
    }

    private static void Poner(string texto, TimeSpan duracion)
    {
        if (Shell.Current?.CurrentPage is not ContentPage pagina) return;
        Quitar();

        var cartel = Ds.Alerta_(texto, null, Ds.InfoSuave, Ds.Tinta);
        cartel.HorizontalOptions = LayoutOptions.Center;
        cartel.VerticalOptions = LayoutOptions.Start;
        cartel.MaximumWidthRequest = 640;
        cartel.Margin = new Thickness(16, 16, 16, 0);
        cartel.InputTransparent = true;   // el aviso nunca estorba: los toques pasan a lo que hay debajo
        cartel.ZIndex = 100;

        if (pagina.Content is Grid raiz)
        {
            Grid.SetRowSpan(cartel, Math.Max(1, raiz.RowDefinitions.Count));
            Grid.SetColumnSpan(cartel, Math.Max(1, raiz.ColumnDefinitions.Count));
            raiz.Add(cartel);
        }
        else
        {
            // La pantalla no es una rejilla: se envuelve su contenido en una y se restaura al quitar el aviso.
            _original = pagina.Content;
            _envoltorio = new Grid();
            pagina.Content = null;
            if (_original is not null) _envoltorio.Add(_original);
            _envoltorio.Add(cartel);
            pagina.Content = _envoltorio;
            _pagina = pagina;
        }
        _actual = cartel;

        var este = cartel;
        _ = Task.Delay(duracion).ContinueWith(_ => MainThread.BeginInvokeOnMainThread(() => { if (ReferenceEquals(_actual, este)) Quitar(); }));
    }

    private static void Quitar()
    {
        try
        {
            if (_actual?.Parent is Grid padre) padre.Remove(_actual);
            if (_envoltorio is not null && _pagina is not null)
            {
                if (_original is not null) _envoltorio.Remove(_original);
                _pagina.Content = _original;
            }
        }
        catch { /* si la pantalla ya no existe, no hay nada que quitar */ }
        _actual = null; _envoltorio = null; _pagina = null; _original = null;
    }
}
