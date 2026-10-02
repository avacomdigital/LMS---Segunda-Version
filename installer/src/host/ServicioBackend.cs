using Microsoft.Extensions.Hosting;

namespace Avacom.Ops.Host;

/// <summary>
/// El servicio Windows AVACOMOPSBackend.
///
/// Existe para que la API del aula no dependa de que alguien tenga abierta la
/// interfaz: las tabletas siguen pidiendo material aunque el profesor cierre
/// AVACOM OPS Master, y el nodo presta servicio desde que arranca Windows.
///
/// Si el backend se cae, se vuelve a levantar con espera creciente. Si lo que
/// falla es el puerto, reintentar cada segundo solo llena el log: por eso la
/// espera sube hasta un minuto y el motivo queda escrito.
/// </summary>
internal sealed class ServicioBackend : BackgroundService
{
    private static readonly int[] EsperasSegundos = [2, 5, 10, 20, 30, 60];

    private readonly Registro _registro = new("servicio.log");

    protected override async Task ExecuteAsync(CancellationToken cancelacion)
    {
        var puerto = Configuracion.PuertoConfigurado();
        _registro.Escribir($"Servicio {Servicio.Nombre} iniciado. Instalacion: {Rutas.RaizInstalacion}");
        _registro.Escribir($"Escucha prevista: {Configuracion.HostPorDefecto}:{puerto}");

        var intento = 0;
        while (!cancelacion.IsCancellationRequested)
        {
            // Sin configuracion no se arranca: el backend usaria los valores de desarrollo y
            // abriria una base de datos NUEVA dentro de Program Files. El aula seguiria
            // "funcionando" sobre un expediente vacio sin que nadie lo notara. Se espera y se
            // reintenta (con la espera creciente de siempre) por si es algo pasajero.
            if (!Configuracion.EsUtilizable(out var motivo))
            {
                _registro.Escribir(
                    $"No se arranca el backend: {motivo}. Se reintentara. " +
                    "Si persiste, vuelve a ejecutar la instalacion de AVACOM OPS Master.");
                var esperaSinConfig = EsperasSegundos[Math.Min(intento, EsperasSegundos.Length - 1)];
                intento++;
                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(esperaSinConfig), cancelacion).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                continue;
            }

            if (!Salud.PuertoLibre(puerto) && !await Salud.EsNuestroBackendAsync(puerto).ConfigureAwait(false))
            {
                _registro.Escribir(
                    $"El puerto {puerto} lo ocupa otro programa. El servicio espera a que se libere " +
                    "en lugar de detener nada ajeno.");
            }

            using var backend = new ProcesoBackend(_registro);
            if (backend.Iniciar())
            {
                var salud = await Salud.EsperarAsync(puerto, 30, cancelacion).ConfigureAwait(false);
                _registro.Escribir(salud.Correcto
                    ? $"Validacion correcta: {salud.Detalle}."
                    : $"El backend arranco pero no valido: {salud.Detalle}.");

                if (salud.Correcto) intento = 0;

                var codigo = await backend.EsperarSalidaAsync(cancelacion).ConfigureAwait(false);
                if (cancelacion.IsCancellationRequested) break;
                _registro.Escribir($"El backend termino con codigo {codigo}. Se reintentara.");
            }

            var espera = EsperasSegundos[Math.Min(intento, EsperasSegundos.Length - 1)];
            intento++;
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(espera), cancelacion).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }

        _registro.Escribir($"Servicio {Servicio.Nombre} detenido.");
    }
}
