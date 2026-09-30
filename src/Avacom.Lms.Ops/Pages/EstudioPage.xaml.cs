using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Modo de estudio en OPS (MOD-008 · CAP-050 y CAP-051): la profesora asigna una lección a un grupo o a algunos alumnos, con una fecha
/// límite que se elige entre opciones, y ve en vivo quién la completó, cómo va la práctica, quién se la llevó y qué envíos esperan su
/// decisión (BR-074). Tres vistas en la misma página: <b>asignaciones</b> (lista con totales), <b>quién completó</b> (detalle) y
/// <b>asignar una lección</b> (tres pasos). El nodo principal no tiene teclado: todo es un toque, y la consigna se elige entre frases.
///
/// La página no calcula nada de negocio: lo que dice «completó», «vencida» o «fuera de plazo» lo decide el nodo (D-9). La lección se
/// lee de AVACOM Biblioteca a través del aula (<see cref="Sesion.Aula"/>): aquí sólo se guarda una referencia (regla de oro del LMS).
/// </summary>
public partial class EstudioPage : ContentPage
{
    private enum Vista { Lista, Detalle, Nueva }

    private const double AnchoMaximo = 1280;

    private Vista _vista = Vista.Lista;
    private IDispatcherTimer? _temporizador;
    private bool _iniciada, _refrescando;
    private int _generacion;               // cada cambio de vista la sube: lo que llega de una vista anterior se descarta
    private int _versionAviso;
    private string _firma = string.Empty;  // lo último que se pintó; si el nodo contesta lo mismo, no se repinta (ni salta el desplazamiento)

    private static IEstudioApi Api => Sesion.Estudio;
    private static string Actor => Sesion.ProfesorId;

    public EstudioPage() => InitializeComponent();

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        try
        {
            if (!_iniciada)
            {
                _iniciada = true;
                await MostrarListaAsync();
            }
            _temporizador ??= Dispatcher.CreateTimer();
            _temporizador.Interval = TimeSpan.FromSeconds(8);
            _temporizador.Tick -= OnTick;
            _temporizador.Tick += OnTick;
            _temporizador.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "EstudioPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
    }

    private async void OnTick(object? sender, EventArgs e)
    {
        try { await RefrescarAsync(false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "EstudioPage.OnTick", ex); }
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = ContenidoHost.WidthRequest = PieBarra.WidthRequest = ancho;
    }

    // ------------------------------------------------------------------------ armazón común

    /// <summary>La lista y el detalle se refrescan solos (la profesora mira cómo avanza el grupo); el asistente para asignar, no.</summary>
    private async Task RefrescarAsync(bool forzar)
    {
        if (_refrescando) return;
        _refrescando = true;
        try
        {
            var generacion = _generacion;
            switch (_vista)
            {
                case Vista.Lista: await CargarListaAsync(generacion, forzar); break;
                case Vista.Detalle: await CargarDetalleAsync(generacion, forzar); break;
            }
        }
        finally { _refrescando = false; }
    }

    private void Entrar(Vista vista)
    {
        _vista = vista;
        _generacion++;
        _firma = string.Empty;
        LimpiarAvisos();
        PieBarra.IsVisible = vista == Vista.Nueva;
    }

    private void PonerCabecera(string sobre, string titulo, string subtitulo, params View[] acciones)
    {
        SobreLabel.Text = sobre;
        TituloLabel.Text = titulo;
        SubtituloLabel.Text = subtitulo;
        SubtituloLabel.IsVisible = !string.IsNullOrWhiteSpace(subtitulo);
        AccionesHost.Clear();
        foreach (var accion in acciones) AccionesHost.Add(accion);
    }

    private void Vaciar(bool alInicio)
    {
        ContenidoHost.Clear();
        if (alInicio) _ = Desplazable.ScrollToAsync(0, 0, false);
    }

    /// <summary>Repinta sin perder el sitio: al volver a llenar el contenedor el desplazamiento se queda en cero si no se restituye.</summary>
    private void Repintar(Action pintar)
    {
        var y = Desplazable.ScrollY;
        pintar();
        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la vista pudo cambiar mientras tanto */ }
            });
    }

    private void LimpiarAvisos()
    {
        _versionAviso++;
        AvisoHost.Clear();
    }

    /// <summary>Un aviso que no interrumpe. Los de éxito se quitan solos a los 9 s; los de error se quedan hasta la siguiente acción.</summary>
    private void Avisar(string titulo, string? detalle, bool error)
    {
        AvisoHost.Clear();
        AvisoHost.Add(error
            ? EstudioUi.Aviso(titulo, detalle, Ds.PeligroSuave, EstudioUi.TintaPeligro)
            : EstudioUi.Aviso(titulo, detalle, Ds.ExitoSuave, Color.FromArgb("#0B5D3B")));
        var version = ++_versionAviso;
        if (!error)
            Dispatcher.DispatchDelayed(TimeSpan.FromSeconds(9), () => { if (version == _versionAviso) AvisoHost.Clear(); });
    }

    private static View Cargando(string texto) => Ds.Tarjeta(Ds.Secundario(texto, 16), Ds.RadioTarjeta, new Thickness(24), Colors.White);

    private static Task Volver() => Shell.Current.GoToAsync("..");

    private (Button Boton, View Vista) AccionActualizar() =>
        EstudioUi.Accion("Actualizar", Ds.Rango.Secondary, async () => await RefrescarAsync(true), null, "estudio-actualizar");

    private (Button Boton, View Vista) AccionMenu() =>
        EstudioUi.Accion("Menú principal", Ds.Rango.Quiet, Volver, null, "estudio-menu");
}
