using System.Diagnostics;
using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// La espera antes de cerrar la clase (007-08 · JRN-011 · MSG-016): «alumnos aún con intento abierto: el cierre espera 60 segundos y luego
/// entrega lo capturado». El host la muestra cuando el profesor pulsa «Terminar clase» y hay alumnos respondiendo, y decide según lo que
/// devuelva <see cref="EsperarAsync"/>: <c>true</c> = cerrar la clase (el host la cierra con <c>forzar</c>), <c>false</c> = seguir en clase.
///
/// El panel dice cuántos alumnos siguen respondiendo, quiénes son (y quiénes no llegaron a empezar), y cuenta hacia atrás con texto grande
/// y una barra que se acorta, sin color de alarma ni animación. Cada 2 s pregunta al aula qué actividades siguen abiertas
/// (<c>SesionAsync</c>) y cómo va cada una (<c>ResultadosAsync</c>). Termina con <c>true</c> cuando ya nadie está respondiendo (tras una
/// breve pausa para que se lea el mensaje), cuando se acaba el tiempo o cuando se toca «Cerrar ahora»; con <c>false</c> cuando se toca
/// «Seguir en clase», se cancela el token, se oculta el panel desde fuera o se pide otra espera. Sin teclado; un toque fuera no hace nada.
/// Si el aula no contesta, el panel conserva lo último que mostró, lo dice en una línea discreta y la cuenta atrás sigue.
/// Llamar y usar desde el hilo de interfaz.
/// </summary>
public partial class EsperaDeCierrePanel : ContentView
{
    private static readonly TimeSpan CadaRefresco = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan PausaSiNadieResponde = TimeSpan.FromMilliseconds(1200);
    private static readonly Color FondoRespondiendo = Ds.InfoSuave, FondoSinEmpezar = Color.FromArgb("#F4F4F5");

    private TaskCompletionSource<bool>? _espera;
    private CancellationTokenRegistration _registro;
    private CancellationTokenSource? _cts;
    private CancellationToken _token;
    private IDispatcherTimer? _reloj;
    private string _sesionId = string.Empty, _actor = string.Empty;
    private int _segundos = 60;
    private long _inicio, _ultimoRefresco;
    private bool _refrescando, _cerrandoSolo, _sinConexion;
    private IReadOnlyList<string>? _respondiendo, _sinEmpezar;      // nulo = todavía no se sabe
    private string _firmaRespondiendo = string.Empty, _firmaSinEmpezar = string.Empty;

    public EsperaDeCierrePanel()
    {
        InitializeComponent();
        SeguirSlot.Content = Ds.Capsula(Ds.Boton("Seguir en clase", Ds.Rango.Secondary, (_, _) => Completar(false, ocultar: true), 64, 250));
        CerrarSlot.Content = Ds.Capsula(Ds.Boton("Cerrar ahora", Ds.Rango.Destructive, (_, _) => Completar(true, ocultar: true), 64, 250));
        CuentaProporcion.ColumnDefinitions =
            [new ColumnDefinition(new GridLength(1, GridUnitType.Star)), new ColumnDefinition(new GridLength(0, GridUnitType.Star))];
    }

    // ------------------------------------------------------------------ API pública

    /// <summary>
    /// Muestra la espera y devuelve <c>true</c> si hay que cerrar la clase (ya nadie responde, se acabó el tiempo o «Cerrar ahora») o
    /// <c>false</c> si se sigue en clase («Seguir en clase», <paramref name="ct"/> cancelado, panel oculto desde fuera u otra espera). El panel se
    /// oculta solo al terminar. Sólo hay una espera a la vez: una nueva termina la anterior con <c>false</c>.
    /// </summary>
    public Task<bool> EsperarAsync(string sesionId, string actor, int segundos = 60, CancellationToken ct = default)
    {
        // La anterior se cancela sin ocultar el panel: se reutiliza.
        Completar(false, ocultar: false);
        if (ct.IsCancellationRequested) return Task.FromResult(false);

        _sesionId = sesionId;
        _actor = actor;
        _segundos = Math.Max(1, segundos);
        _respondiendo = _sinEmpezar = null;
        _firmaRespondiendo = _firmaSinEmpezar = string.Empty;
        _sinConexion = _refrescando = _cerrandoSolo = false;
        CuentaPista.IsVisible = true;

        var espera = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        _espera = espera;
        _cts = new CancellationTokenSource();
        _token = _cts.Token;
        _registro = ct.Register(() => MainThread.BeginInvokeOnMainThread(() =>
        {
            if (ReferenceEquals(_espera, espera)) Completar(false, ocultar: true);
        }));

        _inicio = Stopwatch.GetTimestamp();
        PintarEstado();
        PintarCuenta(_segundos);
        PintarAviso();
        IsVisible = true;
        ArrancarReloj();
        _ = RefrescarAsync(espera, _token);          // sin esperar el primer segundo: quién sigue respondiendo se ve al abrir
        return espera.Task;
    }

    // ------------------------------------------------------------------ ciclo de vida

    /// <summary>Si el host oculta el panel mientras espera, la espera termina en «seguir en clase».</summary>
    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName == nameof(IsVisible) && !IsVisible) Completar(false, ocultar: false);
    }

    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is not null) return;
        // La pantalla se cierra: nadie se queda esperando y no queda un reloj vivo.
        Completar(false, ocultar: false);
        if (_reloj is not null) { _reloj.Stop(); _reloj.Tick -= OnRelojTick; _reloj = null; }
    }

    /// <summary>Termina la espera con el resultado dado. Idempotente: un segundo toque, o el reloj y un botón a la vez, no hacen nada más.</summary>
    private void Completar(bool cerrar, bool ocultar)
    {
        var espera = Interlocked.Exchange(ref _espera, null);
        if (espera is null) return;
        _registro.Dispose();
        _registro = default;
        _reloj?.Stop();
        _cts?.Cancel();
        _cts?.Dispose();
        _cts = null;
        if (ocultar) IsVisible = false;
        espera.TrySetResult(cerrar);
    }

    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (Raiz.Width <= 0 || Raiz.Height <= 0) return;
        Tarjeta.WidthRequest = Math.Min(800, Math.Max(360, Raiz.Width - 64));
        Cuerpo.MaximumHeightRequest = Math.Max(120, Raiz.Height - 64 - 430);
    }

    // ------------------------------------------------------------------ reloj y cuenta atrás

    private void ArrancarReloj()
    {
        if (_reloj is null)
        {
            var despachador = Dispatcher ?? Application.Current?.Dispatcher;
            _reloj = despachador?.CreateTimer();
            if (_reloj is null) return;
            _reloj.Interval = TimeSpan.FromMilliseconds(250);
            _reloj.Tick += OnRelojTick;
        }
        if (!_reloj.IsRunning) _reloj.Start();
    }

    private void OnRelojTick(object? sender, EventArgs e)
    {
        var espera = _espera;
        if (espera is null) { _reloj?.Stop(); return; }
        var restante = _segundos - Stopwatch.GetElapsedTime(_inicio).TotalSeconds;
        // Se acabó el tiempo: se entrega lo capturado y el host cierra (JRN-011).
        if (restante <= 0) { Completar(true, ocultar: true); return; }
        if (!_cerrandoSolo) PintarCuenta(restante);
        if (Stopwatch.GetElapsedTime(_ultimoRefresco) >= CadaRefresco) _ = RefrescarAsync(espera, _token);
    }

    private void PintarCuenta(double restante)
    {
        var segundos = (int)Math.Ceiling(Math.Max(0, restante));
        CuentaLabel.Text = $"Cerrando en {segundos} s";
        var fraccion = Math.Clamp(restante / _segundos, 0, 1);
        CuentaProporcion.ColumnDefinitions[0].Width = new GridLength(fraccion, GridUnitType.Star);
        CuentaProporcion.ColumnDefinitions[1].Width = new GridLength(1 - fraccion, GridUnitType.Star);
        SemanticProperties.SetDescription(CuentaLabel, $"Cerrando la clase en {segundos} segundos");
    }

    // ------------------------------------------------------------------ qué pregunta al aula

    private bool Vigente(TaskCompletionSource<bool> espera, CancellationToken token) =>
        ReferenceEquals(_espera, espera) && !token.IsCancellationRequested;

    /// <summary>
    /// Una pasada: qué actividades siguen abiertas y, de cada una, quién está respondiendo y quién no empezó. Si algo falla se conserva lo
    /// último mostrado. Una pasada a la vez; la siguiente sale cuando pasen 2 s desde que empezó esta.
    /// </summary>
    private async Task RefrescarAsync(TaskCompletionSource<bool> espera, CancellationToken token)
    {
        if (_refrescando) return;
        _refrescando = true;
        _ultimoRefresco = Stopwatch.GetTimestamp();
        try
        {
            var sesionId = _sesionId;
            var actor = _actor;
            var api = Sesion.Aula;
            var sesion = await api.SesionAsync(sesionId, token);
            if (!Vigente(espera, token)) return;

            var respondiendo = new Dictionary<string, string>();
            var sinEmpezar = new Dictionary<string, string>();
            var completo = sesion is not null;
            if (sesion is not null && !sesion.Cerrada)
            {
                foreach (var actividad in (sesion.Distribuciones ?? []).Where(d => d.Clase == "actividad" && d.EstaAbierta))
                {
                    var resultados = await api.ResultadosAsync(sesionId, actor, actividad.Id, token);
                    if (!Vigente(espera, token)) return;
                    if (resultados is null) { completo = false; break; }
                    foreach (var fila in resultados.Filas)
                    {
                        if (fila.Estado == "respondiendo") respondiendo[fila.ParticipanteId] = fila.Nombre;
                        else if (fila.Estado == "sin_empezar") sinEmpezar[fila.ParticipanteId] = fila.Nombre;
                    }
                }
            }

            var yaCerrada = sesion?.Cerrada == true;
            void Aplicar()
            {
                if (!Vigente(espera, token)) return;
                _sinConexion = !completo;
                PintarAviso();
                if (!completo) return;          // se conserva lo último; sólo la línea de estado cambia
                // Quien tiene un intento abierto no cuenta como «sin empezar».
                var siguen = Ordenar(respondiendo);
                var noEmpezaron = Ordenar(sinEmpezar.Where(p => !respondiendo.ContainsKey(p.Key)));
                _respondiendo = siguen;
                _sinEmpezar = noEmpezaron;
                PintarEstado();
                if (siguen.Count == 0 || yaCerrada) _ = CerrarPorqueNadieRespondeAsync(espera, token);
            }
            if (MainThread.IsMainThread) Aplicar();
            else await MainThread.InvokeOnMainThreadAsync(Aplicar);
        }
        catch (OperationCanceledException) { }
        finally { _refrescando = false; }
    }

    private static List<string> Ordenar(IEnumerable<KeyValuePair<string, string>> alumnos) =>
        alumnos.Select(a => a.Value).OrderBy(n => n, StringComparer.CurrentCultureIgnoreCase).ToList();

    /// <summary>Ya nadie tiene un intento abierto: se deja leer el mensaje un instante y se devuelve «cerrar». Tocar «Seguir en clase» lo impide.</summary>
    private async Task CerrarPorqueNadieRespondeAsync(TaskCompletionSource<bool> espera, CancellationToken token)
    {
        if (_cerrandoSolo) return;
        _cerrandoSolo = true;
        CuentaLabel.Text = "Cerrando la clase…";
        CuentaPista.IsVisible = false;
        try { await Task.Delay(PausaSiNadieResponde, token); }
        catch (OperationCanceledException) { return; }
        if (ReferenceEquals(_espera, espera)) Completar(true, ocultar: true);
    }

    // ------------------------------------------------------------------ pintado

    /// <summary>Qué se conservó, qué falta y qué sigue (UXR-005); sin códigos. n = alumnos con un intento abierto.</summary>
    private void PintarEstado()
    {
        if (_respondiendo is null || _sinEmpezar is null)
        {
            TituloLabel.Text = "Revisando quién sigue respondiendo…";
            CuerpoLabel.Text = "Un momento. Lo que llevan los alumnos se conserva.";
            RespondiendoSeccion.IsVisible = SinEmpezarSeccion.IsVisible = false;
            return;
        }
        int n = _respondiendo.Count, sin = _sinEmpezar.Count;
        if (n > 0)
        {
            TituloLabel.Text = n == 1 ? "1 alumno sigue respondiendo." : $"{n} alumnos siguen respondiendo.";
            CuerpoLabel.Text = "Si cierras ahora, se entrega lo que llevan.";
        }
        else if (sin > 0)
        {
            TituloLabel.Text = "Todos los que empezaron ya entregaron";
            CuerpoLabel.Text = sin == 1 ? "1 alumno no llegó a empezar la actividad." : $"{sin} alumnos no llegaron a empezar la actividad.";
        }
        else
        {
            TituloLabel.Text = "Todos entregaron";
            CuerpoLabel.Text = "Ya puedes cerrar la clase.";
        }

        RespondiendoSeccion.IsVisible = n > 0;
        RespondiendoTitulo.Text = $"Siguen respondiendo ({n})";
        Reconstruir(RespondiendoHost, _respondiendo, FondoRespondiendo, ref _firmaRespondiendo);
        SinEmpezarSeccion.IsVisible = sin > 0;
        SinEmpezarTitulo.Text = $"Sin empezar ({sin})";
        Reconstruir(SinEmpezarHost, _sinEmpezar, FondoSinEmpezar, ref _firmaSinEmpezar);
    }

    /// <summary>Las fichas de nombres se rehacen sólo si la lista cambió: con un refresco cada 2 s no deben parpadear.</summary>
    private static void Reconstruir(FlexLayout host, IReadOnlyList<string> nombres, Color fondo, ref string firma)
    {
        var nueva = string.Join("\u001f", nombres);
        if (nueva == firma) return;
        firma = nueva;
        host.Clear();
        foreach (var nombre in nombres)
            host.Add(new Border
            {
                BackgroundColor = fondo, StrokeThickness = 0, Padding = new Thickness(16, 10), MinimumHeightRequest = 44, Margin = new Thickness(0, 0, 8, 8),
                StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
                Content = new Label { Text = nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center },
            });
    }

    private void PintarAviso()
    {
        AvisoLabel.IsVisible = _sinConexion;
        AvisoLabel.Text = _sinConexion ? "Sin conexión con el aula · lo último que se vio sigue aquí y la cuenta continúa" : string.Empty;
    }
}
