using Avacom.Ops.Host.Actualizacion;
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

    private static readonly TimeSpan MiraLaOrdenCada = TimeSpan.FromSeconds(3);

    private readonly Registro _registro = new("servicio.log");

    // MOD-017: obedece la orden de actualizacion que el backend deja en Actualizaciones\orden.json. Es el UNICO que para el backend a proposito.
    private readonly VigilanteDeActualizaciones _actualizaciones = new();

    protected override async Task ExecuteAsync(CancellationToken cancelacion)
    {
        var puerto = Configuracion.PuertoConfigurado();
        _registro.Escribir($"Servicio {Servicio.Nombre} iniciado. Instalacion: {Rutas.RaizInstalacion}");
        _registro.Escribir($"Escucha prevista: {Configuracion.HostPorDefecto}:{puerto}");

        // Un corte a mitad de una actualizacion se retoma o se deshace ANTES de levantar el backend: nunca arranca sobre un codigo a medias.
        _actualizaciones.Arrancar();

        // MOD-018 (P-23): la integridad del despliegue se verifica EN SEGUNDO PLANO: deja un asiento y una señal para el backend, y NUNCA retrasa ni impide el arranque.
        _ = Task.Run(() => Integridad.Senal.Comprobar(_registro), CancellationToken.None);

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

            // Con el backend caido tambien se atiende la orden (sin nada que parar).
            if (_actualizaciones.HayOrdenNueva())
            {
                await Task.Run(() => _actualizaciones.Atender(() => { }), CancellationToken.None).ConfigureAwait(false);
                intento = 0;
                continue;
            }

            // MOD-018 segunda proteccion: el backend solo arranca en un dispositivo AVACOM autorizado (identidad UEFI + sello). Sin la comprobacion no hay datos ni lecciones: la aplicacion queda inerte.
            if (OperatingSystem.IsWindows() && !Dispositivo.PuertaDelServicio.Permite(_registro))
            {
                var esperaDispositivo = EsperasSegundos[Math.Min(intento, EsperasSegundos.Length - 1)];
                intento++;
                try { await Task.Delay(TimeSpan.FromSeconds(esperaDispositivo), cancelacion).ConfigureAwait(false); }
                catch (OperationCanceledException) { break; }
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

                var salida = backend.EsperarSalidaAsync(cancelacion);
                var actualizado = false;
                while (!salida.IsCompleted && !cancelacion.IsCancellationRequested)
                {
                    try
                    {
                        await Task.WhenAny(salida, Task.Delay(MiraLaOrdenCada, cancelacion)).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                    if (salida.IsCompleted || cancelacion.IsCancellationRequested) break;

                    _actualizaciones.Mantener();
                    if (!_actualizaciones.HayOrdenNueva()) continue;

                    // Hay una orden: se atiende con el backend vivo (para ver si hay clase) y solo si no la hay se para. El resto, sin esperar a nadie ni a la cancelacion:
                    // un servicio que se detiene a mitad de una actualizacion la deja en su checkpoint y el siguiente arranque la retoma.
                    _registro.Escribir("Hay una orden de actualizacion: se atiende (el backend se para solo si no hay ninguna clase).");
                    actualizado = await Task.Run(() => _actualizaciones.Atender(backend.Detener), CancellationToken.None).ConfigureAwait(false);
                    if (actualizado) break;
                }

                if (actualizado)
                {
                    _registro.Escribir("La actualizacion termino con el backend parado: se vuelve a levantar.");
                    _ = Task.Run(() => Integridad.Senal.Comprobar(_registro), CancellationToken.None);     // el codigo cambio: se vuelve a verificar contra lo que el paquete firmado declaro
                    intento = 0;
                    continue;
                }

                if (cancelacion.IsCancellationRequested) break;
                var codigo = await salida.ConfigureAwait(false);
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
