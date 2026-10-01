using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// ¿Se ve el aula? No es lo mismo que «hay red»: se le pregunta al aula misma (<c>GET /estado/</c>, que nunca falla por el modo de estudio) con un
/// tope corto. Cambia también cuando el sistema avisa de un cambio de red y cuando cualquier llamada al aula contesta o no contesta
/// (<see cref="Informar"/>). Optimista al arrancar: la primera carga de la lista confirma o corrige.
/// </summary>
internal sealed class ConnectivityService : IConnectivityService, IDisposable
{
    private readonly IEstudioApi _api;
    private readonly string _dispositivo;
    private volatile bool _visible = true;

    public ConnectivityService(IEstudioApi api, string dispositivo)
    {
        _api = api;
        _dispositivo = dispositivo;
        try { Connectivity.Current.ConnectivityChanged += AlCambiarLaRed; }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ConnectivityService.Suscribir", ex); }
    }

    public bool IsOnline => _visible;
    public event Action<bool>? Changed;

    public async Task<bool> ProbeAsync(CancellationToken ct = default)
    {
        var visible = false;
        try
        {
            using var tope = CancellationTokenSource.CreateLinkedTokenSource(ct);
            tope.CancelAfter(TimeSpan.FromSeconds(2.5));
            visible = await _api.EstadoAsync(_dispositivo, ct: tope.Token) is not null;
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested) { /* el aula no contestó a tiempo */ }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ConnectivityService.Probe", ex); }
        Informar(visible);
        return visible;
    }

    /// <summary>Lo que dice una llamada real al aula: si contestó, se ve; si no, no. Sólo avisa si cambia.</summary>
    internal void Informar(bool visible)
    {
        if (_visible == visible) return;
        _visible = visible;
        // MOD-019 §2.4 (canal comunicacion): sólo la transición. Perder el aula es un aviso; recuperarla, información.
        if (visible) RegistroLocal.Info(Canal.Comunicacion, "aula.visible", "El aula vuelve a verse desde la tableta");
        else RegistroLocal.Advertencia(Canal.Comunicacion, "aula.invisible", "El aula dejó de verse desde la tableta", new { dispositivo = _dispositivo });
        try { Changed?.Invoke(visible); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ConnectivityService.Changed", ex); }
    }

    private async void AlCambiarLaRed(object? sender, ConnectivityChangedEventArgs e)
    {
        try
        {
            // MOD-019 §2.4 (canal dispositivo): el cambio de red del aparato, sin nombres de redes.
            RegistroLocal.Info(Canal.Dispositivo, "red.cambio", "Cambió la red del aparato", new { acceso = e.NetworkAccess.ToString() });
            if (e.NetworkAccess == NetworkAccess.None) Informar(false);
            else await ProbeAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ConnectivityService.Red", ex); }
    }

    public void Dispose()
    {
        try { Connectivity.Current.ConnectivityChanged -= AlCambiarLaRed; }
        catch (Exception) { /* la app se está cerrando */ }
    }
}
