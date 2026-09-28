using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Pages;

/// <summary>
/// S2 · Siguiendo la clase (PAN-102). Sondea el estado cada 2 s (BR-049: el selector llega en ≤ 3 s):
/// pinta lo que el profesor proyecta, se bloquea cuando lo pide (CAP-042), muestra las
/// actividades pendientes y los avisos como bandas no bloqueantes. Con seguimiento activo no
/// hay navegación propia; al liberarlo aparecen anterior/siguiente.
/// </summary>
[QueryProperty(nameof(SesionId), "sesion")]
[QueryProperty(nameof(ParticipanteId), "participante")]
public partial class ClaseSiguiendoPage : ContentPage
{
    private IDispatcherTimer? _temporizador;
    private EstadoTableta? _estado;
    private ObjetoAula? _objeto;
    private string? _selectorPintado;
    private long _ultimoAvisoVisto;
    private bool _refrescando;
    private bool _mostrandoPendiente;

    public string SesionId { get; set; } = string.Empty;
    public string ParticipanteId { get; set; } = string.Empty;

    public ClaseSiguiendoPage()
    {
        InitializeComponent();
        Visor.Absoluta = ruta => Sesion.Aula.Absoluta(ruta);
        Visor.PuedeNavegar = false;
        Visor.UnidadPedida += (_, unidad) => { if (_objeto is not null) Visor.Mostrar(_objeto, unidad); };
        Visor.MostrarVacio("Esperando a tu profesor", "Cuando proyecte algo, aparecerá aquí.");
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _ultimoAvisoVisto = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        await RefrescarAsync();
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Interval = TimeSpan.FromMilliseconds(_estado?.IntervaloSondeoMs ?? 2000);
        _temporizador.Tick -= OnTick;
        _temporizador.Tick += OnTick;
        _temporizador.Start();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
    }

    private async void OnTick(object? sender, EventArgs e) => await RefrescarAsync();

    private async Task RefrescarAsync()
    {
        if (_refrescando || string.IsNullOrWhiteSpace(SesionId) || string.IsNullOrWhiteSpace(ParticipanteId)) return;
        _refrescando = true;
        try
        {
            var aula = Sesion.Aula;
            var estado = await aula.EstadoAsync(SesionId, ParticipanteId);
            if (estado is null)
            {
                Conexion("Reconectando con el aula", Ds.Alerta, Ds.AlertaSuave);
                return;
            }
            _estado = estado;
            TituloLabel.Text = estado.Sesion.LeccionRotulo ?? estado.Sesion.CursoRotulo ?? "Clase";
            SubtituloLabel.Text = string.Join(" · ", new[] { estado.Sesion.CursoRotulo, estado.Sesion.ProfesorRotulo }.Where(x => !string.IsNullOrWhiteSpace(x)));

            if (estado.Sesion.Estado is "cerrada" or "archivada")
            {
                _temporizador?.Stop();
                Sesion.OlvidarClase();
                await DisplayAlertAsync("La clase terminó", "Tu profesor cerró la clase. Tu trabajo quedó guardado.", "Volver al menú");
                await Shell.Current.GoToAsync("..");
                return;
            }
            if (estado.Sesion.Estado == "suspendida")
            {
                Conexion("La clase se está reanudando", Ds.Alerta, Ds.AlertaSuave);
                MostrarBanda("La clase está en pausa", "Tu trabajo está guardado. En un momento continuamos.", Ds.AlertaSuave, Ds.Tinta, fijo: true);
            }
            else
            {
                Conexion("Conectado", Ds.Exito, Ds.ExitoSuave);
                QuitarBandaFija();
            }

            if (estado.Participante?.Estado is "expulsado" or "rechazado")
            {
                _temporizador?.Stop();
                Sesion.OlvidarClase();
                await DisplayAlertAsync("Saliste de la clase", "Habla con tu profesor para volver a entrar.", "Entendido");
                await Shell.Current.GoToAsync("..");
                return;
            }

            if (estado.PantallasBloqueadas) Bloqueo.Mostrar(); else Bloqueo.Ocultar();
            Visor.PuedeNavegar = !estado.Seguimiento;
            await PintarSelectorAsync(estado);
            PintarPendientes(estado);
            PintarAvisos(estado);
        }
        finally { _refrescando = false; }
    }

    private void Conexion(string texto, Color color, Color fondo)
    {
        ConexionLabel.Text = $"●  {texto}";
        ConexionLabel.TextColor = color;
        ConexionChip.BackgroundColor = fondo;
    }

    private async Task PintarSelectorAsync(EstadoTableta estado)
    {
        if (_mostrandoPendiente) return;
        var selector = estado.Selector;
        if (selector is null || string.IsNullOrWhiteSpace(selector.ObjetoRef))
        {
            if (_selectorPintado is not null) { Visor.MostrarVacio("Esperando a tu profesor", "Cuando proyecte algo, aparecerá aquí."); _selectorPintado = null; _objeto = null; }
            return;
        }
        var llave = $"{selector.ObjetoRef}|{selector.UnidadRef}";
        if (llave == _selectorPintado) return;
        if (_objeto?.ObjetoRef != selector.ObjetoRef)
        {
            var suelto = await Sesion.Aula.ObjetoAsync(estado.Sesion.CursoRef ?? selector.CursoRef ?? string.Empty, selector.ObjetoRef!, docente: false);
            if (suelto is null)
            {
                Visor.MostrarVacio("No se pudo abrir lo proyectado", Sesion.Aula.UltimoMotivo ?? selector.Rotulo ?? string.Empty);
                return;
            }
            _objeto = suelto.Objeto;
        }
        Visor.Mostrar(_objeto!, string.IsNullOrWhiteSpace(selector.UnidadRef) ? null : selector.UnidadRef);
        _selectorPintado = llave;
    }

    // -------------------------------------------------------------- pendientes

    private void PintarPendientes(EstadoTableta estado)
    {
        PendientesHost.Clear();
        var pendientes = (estado.Pendientes ?? []).Where(p => p.Clase == "actividad").ToList();
        if (pendientes.Count == 0)
        {
            if (_mostrandoPendiente) { _mostrandoPendiente = false; _selectorPintado = null; }
            return;
        }
        foreach (var d in pendientes)
        {
            var grid = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
            grid.Add(Ds.IconoCategoria("actividad", 48), 0, 0);
            grid.Add(new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Children = { Ds.Cuerpo(d.Rotulo ?? "Actividad", 17), Ds.Secundario(d.Entrega == "entregado" ? "Recibida · puedes seguir respondiendo" : "Tu profesor te la acaba de enviar", 13) } }, 1, 0);
            var abrir = Ds.Boton(_mostrandoPendiente ? "Volver a la clase" : "Abrir", _mostrandoPendiente ? Ds.Rango.Quiet : Ds.Rango.Primary, async (_, _) => await AbrirPendienteAsync(d), 56);
            abrir.FontSize = 16;
            grid.Add(abrir, 2, 0);
            PendientesHost.Add(Ds.Tarjeta(grid, Ds.RadioInterno, new Thickness(14, 12), Ds.ExitoSuave));
        }
    }

    private async Task AbrirPendienteAsync(DistribucionAula d)
    {
        if (_mostrandoPendiente)
        {
            _mostrandoPendiente = false;
            _selectorPintado = null;
            if (_estado is not null) { await PintarSelectorAsync(_estado); PintarPendientes(_estado); }
            return;
        }
        var aula = Sesion.Aula;
        if (d.Entrega != "entregado") await aula.ConfirmarEntregaAsync(SesionId, d.Id, ParticipanteId);
        var suelto = await aula.ObjetoAsync(_estado?.Sesion.CursoRef ?? d.CursoRef ?? string.Empty, d.ObjetoRef ?? string.Empty, docente: false);
        if (suelto is null)
        {
            MostrarBanda("No se pudo abrir la actividad", aula.UltimoMotivo, Ds.PeligroSuave, Color.FromArgb("#8A1C1F"));
            return;
        }
        _mostrandoPendiente = true;
        Visor.Mostrar(suelto.Objeto, null);
        if (_estado is not null) PintarPendientes(_estado);
    }

    // ------------------------------------------------------------------ avisos

    private void PintarAvisos(EstadoTableta estado)
    {
        foreach (var aviso in (estado.Avisos ?? []).Where(a => a.EnviadoEn > _ultimoAvisoVisto).OrderBy(a => a.EnviadoEn))
        {
            _ultimoAvisoVisto = Math.Max(_ultimoAvisoVisto, aviso.EnviadoEn);
            MostrarBanda(aviso.ParticipanteId is null ? "Aviso de tu profesor" : "Aviso para ti", aviso.Texto, Ds.InfoSuave, Ds.Tinta);
        }
    }

    private Border? _bandaFija;

    private void MostrarBanda(string titulo, string? detalle, Color fondo, Color tinta, bool fijo = false)
    {
        if (fijo && _bandaFija is not null) return;
        var banda = Ds.Alerta_(titulo, detalle, fondo, tinta);
        AvisosHost.Add(banda);
        if (fijo) { _bandaFija = banda; return; }
        Dispatcher.StartTimer(TimeSpan.FromSeconds(8), () => { AvisosHost.Remove(banda); return false; });
    }

    private void QuitarBandaFija()
    {
        if (_bandaFija is null) return;
        AvisosHost.Remove(_bandaFija);
        _bandaFija = null;
    }

    private async void OnSalir(object? sender, EventArgs e)
    {
        if (!await DisplayAlertAsync("¿Salir de la clase?", "Tu trabajo queda guardado. Puedes volver con el mismo código.", "Salir", "Seguir en clase")) return;
        _temporizador?.Stop();
        await Sesion.Aula.PresenciaAsync(SesionId, ParticipanteId, "salio", Sesion.Dispositivo);
        Sesion.OlvidarClase();
        await Shell.Current.GoToAsync("..");
    }
}
