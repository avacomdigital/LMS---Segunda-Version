using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El panel del examen en vivo (MOD-010 · PAN-005/121 · Guion, pasos 5 a 12). Una fila por alumno, en el ORDEN que manda el nodo —primero quien necesita al
/// profesor: los suspendidos, los que esperan admisión, los envíos tardíos por decidir, los de bloqueo fallido; después los que van en curso y al final los
/// entregados—, nunca alfabético. Es un panel de CONTINUIDAD, no de vigilancia: no suena, no marca nada en rojo, no parpadea y no ofrece «anular» (eso vive sólo
/// en el expediente de un intento ya entregado).
///
/// Se actualiza solo: sondea el panel cada 3 s mientras la pantalla se ve y, si el examen nació en una clase, escucha el canal en tiempo real del aula
/// (<see cref="AulaSocketClient"/>, rol «docente»): el aviso <c>evaluacion_panel</c> adelanta el sondeo. Los cronómetros avanzan cada segundo con la hora que
/// dio el nodo; la lista sólo se repinta cuando algo que se ve cambió.
///
/// Archivos: este (ciclo de vida y refresco), <c>ExamenPanelPage.Cabecera.cs</c> (el examen y lo que se puede hacer con él) y <c>ExamenPanelPage.Filas.cs</c>
/// (cada alumno y lo que se puede hacer con él).
/// </summary>
[QueryProperty(nameof(AsignacionId), "asignacion")]
public partial class ExamenPanelPage : ContentPage
{
    private const int SondeoMs = 3000;
    private const long SilencioVisibleMs = 15_000;

    public string AsignacionId { get; set; } = string.Empty;

    private PanelDeExamen? _panel;
    private ElegibilidadDeTabletas? _eleg;
    private string? _elegNivel;
    private IDispatcherTimer? _sondeo, _segundero;
    private AulaSocketClient? _canal;
    private string? _canalSesion;
    private bool _visible, _refrescando, _pendiente;
    private string _firmaCabecera = string.Empty, _firmaFilas = string.Empty;
    private int _versionAviso;
    private Border? _avisoDeCarga;   // el aviso «no se pudo actualizar»: se quita solo cuando el nodo vuelve a contestar
    private readonly HojaDeOpciones _hoja = new();

    private static string Actor => Sesion.ProfesorId;

    public ExamenPanelPage()
    {
        InitializeComponent();
        Raiz.Add(_hoja);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            await RefrescarAsync(forzar: true);
            if (!_visible) return;
            _sondeo ??= Dispatcher.CreateTimer();
            _sondeo.Interval = TimeSpan.FromMilliseconds(SondeoMs);
            _sondeo.Tick -= OnSondeo;
            _sondeo.Tick += OnSondeo;
            _sondeo.Start();
            _segundero ??= Dispatcher.CreateTimer();
            _segundero.Interval = TimeSpan.FromSeconds(1);
            _segundero.Tick -= OnSegundo;
            _segundero.Tick += OnSegundo;
            _segundero.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenPanelPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _sondeo?.Stop();
        _segundero?.Stop();
        _ = DetenerCanalAsync();
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(640, Math.Min(1500, Width - 92));
        CabeceraHost.WidthRequest = AvisoHost.WidthRequest = ReactivarHost.WidthRequest = FilasHost.WidthRequest = ancho;
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try { await RefrescarAsync(forzar: false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenPanelPage.OnSondeo", ex); }
    }

    // ------------------------------------------------------------------ canal en tiempo real (opcional)

    /// <summary>Si el examen nació en una clase, el aviso del nodo adelanta el sondeo. Sin clase, o sin canal, el sondeo de 3 s basta.</summary>
    private void ActualizarCanal(string? sesionId)
    {
        if (!_visible || string.IsNullOrWhiteSpace(sesionId)) return;
        if (_canal is not null && _canalSesion == sesionId) return;
        _ = DetenerCanalAsync();
        var canal = new AulaSocketClient(Sesion.BaseUri, sesionId, "docente", token: ClienteJson.Token);
        canal.Mensaje += OnMensajeCanal;
        _canal = canal;
        _canalSesion = sesionId;
        canal.Iniciar();
    }

    private async Task DetenerCanalAsync()
    {
        var canal = _canal;
        _canal = null;
        _canalSesion = null;
        if (canal is null) return;
        canal.Mensaje -= OnMensajeCanal;
        try { await canal.DetenerAsync(); } catch { /* el sondeo de 3 s sigue siendo la fuente de verdad */ }
    }

    // Los eventos del canal llegan en un hilo de fondo.
    private void OnMensajeCanal(MensajeAula mensaje) => MainThread.BeginInvokeOnMainThread(() =>
    {
        if (_visible && mensaje.Tipo == "cambio" && (mensaje.Que is "evaluacion_panel" or "evaluacion")) _ = RefrescarAsync(forzar: false);
    });

    // ------------------------------------------------------------------------------------------ refresco

    private async Task RefrescarAsync(bool forzar)
    {
        if (string.IsNullOrWhiteSpace(AsignacionId) || !_visible) return;
        if (_refrescando) { _pendiente = true; return; }
        _refrescando = true;
        try
        {
            do
            {
                _pendiente = false;
                var api = Sesion.Evaluacion;
                var panel = await api.PanelAsync(Actor, AsignacionId);
                if (!_visible) return;
                if (panel is null) { PintarSinPanel(api.UltimoError, api.UltimoMotivo); continue; }
                RelojNodo.Aprender(panel.ServidorEn);
                _panel = panel;
                ActualizarCanal(panel.Asignacion.SesionId);
                await ActualizarElegibilidadAsync(panel);
                AplicarPanel(panel, forzar);
            }
            while (_pendiente && _visible);
        }
        finally { _refrescando = false; }
    }

    /// <summary>
    /// MSG-036: qué tabletas no alcanzan el nivel, preguntado al nodo (<c>ElegibilidadAsync</c>). Se pide la primera vez y cada vez que cambia el nivel del examen
    /// (una bajada de nivel cambia la respuesta); no en cada sondeo.
    /// </summary>
    private async Task ActualizarElegibilidadAsync(PanelDeExamen panel)
    {
        var a = panel.Asignacion;
        if (!a.Abierta) { _eleg = null; _elegNivel = null; return; }
        if (_eleg is not null && _elegNivel == a.NivelExamen) return;
        var api = Sesion.Evaluacion;
        var eleg = await api.ElegibilidadAsync(Actor, a.Id);
        // Si el nodo no contesta ahora, se vuelve a intentar en el siguiente sondeo: _elegNivel sigue sin fijarse.
        if (eleg is null) return;
        _eleg = eleg;
        _elegNivel = a.NivelExamen;
    }

    /// <summary>Pinta lo que cambió. Con el mismo panel sólo se ponen al día los cronómetros: la lista no se repinta ni salta.</summary>
    private void AplicarPanel(PanelDeExamen panel, bool forzar)
    {
        var firmaCabecera = FirmaDeCabecera(panel);
        if (forzar || firmaCabecera != _firmaCabecera)
        {
            _firmaCabecera = firmaCabecera;
            PintarCabecera(panel);
            PintarReactivarTodos(panel);
        }
        var firmaFilas = FirmaDeFilas(panel);
        if (forzar || firmaFilas != _firmaFilas)
        {
            _firmaFilas = firmaFilas;
            PintarFilas(panel);
        }
        else PonerAlDiaLosRelojes(panel);
        if (_avisoDeCarga is { Parent: not null } carga) AvisoHost.Remove(carga);
        _avisoDeCarga = null;
    }

    /// <summary>Lo que hace que la cabecera se vea distinta: el examen y sus cuentas (no los cronómetros).</summary>
    private string FirmaDeCabecera(PanelDeExamen p) =>
        JsonSerializer.Serialize(new { a = p.Asignacion with { Totales = null, ArmadoPrevio = null }, t = p.Totales });

    private string FirmaDeFilas(PanelDeExamen p) =>
        JsonSerializer.Serialize(p.Filas.Select(f => new
        {
            f.AlumnoId, f.Estado, f.RequiereReactivacion, f.IntentoId, f.Numero, f.NivelEfectivo, f.Dispositivo, f.Respondidas, f.Total, Vigente = AdmisionVigente(f, p.Asignacion),
            Corre = f.Reloj?.Corriendo, Limite = f.Reloj?.LimiteSeg, Silencio = (f.SilencioMs ?? 0) >= SilencioVisibleMs || f.RequiereReactivacion,
            Incidentes = f.Incidentes is null ? null : new { f.Incidentes.Total, f.Incidentes.Atencion, f.Incidentes.Alta },
            Bloqueo = f.Bloqueo?.Resultado, f.Admision, f.FueraDePlazo, f.EnvioTardio, f.OrigenEntrega, f.RequiereRevision, f.Porcentaje, f.AnuladoPor,
            Nivel = p.Asignacion.NivelExamen, Abierta = p.Asignacion.Abierta, Eleg = _eleg?.Resumen,
        }));

    private void PintarSinPanel(ErrorAula? error, string? motivo)
    {
        if (_panel is not null)
        {
            // Ya hay un panel pintado: un tropiezo del sondeo no lo borra. Se dice una vez, con calma.
            if (_avisoDeCarga is null)
            {
                _avisoDeCarga = ExamenUi.Aviso("No se pudo actualizar el panel", $"{ExamenTexto.Error(error, motivo)} Se vuelve a intentar solo.", Tono.Ambar);
                AvisoHost.Add(_avisoDeCarga);
            }
            return;
        }
        CabeceraHost.Clear();
        FilasHost.Clear();
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo("No se pudo leer el examen", 22));
        pila.Add(Ds.Secundario(ExamenTexto.Error(error, motivo), 16));
        var acciones = ExamenUi.Fila();
        acciones.Add(ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, () => RefrescarAsync(forzar: true), 170, "examen-reintentar").Vista);
        acciones.Add(ExamenUi.Accion("Volver", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 140, "examen-volver").Vista);
        pila.Add(acciones);
        CabeceraHost.Add(ExamenUi.Tarjeta(pila));
    }

    // ------------------------------------------------------------------------------------------ avisos

    /// <summary>Un aviso que no interrumpe. El de éxito se quita solo a los 9 s; el de tropiezo se queda hasta la siguiente acción.</summary>
    private void Avisar(string titulo, string? detalle, Tono tono)
    {
        AvisoHost.Clear();
        _avisoDeCarga = null;
        AvisoHost.Add(ExamenUi.Aviso(titulo, detalle, tono));
        var version = ++_versionAviso;
        if (tono is Tono.Exito or Tono.Info)
            Dispatcher.DispatchDelayed(TimeSpan.FromSeconds(9), () => { if (version == _versionAviso) AvisoHost.Clear(); });
    }

    private Task VolverAsync() => Shell.Current.GoToAsync("..");
}
