using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Los flujos de la pantalla «Licencia» sin MAUI: activar o renovar en tres pasos (P-18) con su confirmación única y sus reintentos, liberar este equipo (el destino se elige ANTES de liberar,
/// y si el archivo no se pudo guardar se guarda en otro lugar sin volver a liberar) y confirmar la fecha. Contra un nodo falso que responde con las respuestas reales capturadas.
/// </summary>
public sealed class LicenciaFlujoTests : IDisposable
{
    private static readonly DateTime Hoy = new(2026, 10, 20, 15, 0, 0, DateTimeKind.Utc);
    private readonly CarpetaTemporal _tmp = new();
    private readonly ApiDeLicenciaFalsa _api = new();
    private readonly List<string> _recordadas = [];

    public void Dispose() => _tmp.Dispose();

    private DestinoElegido Destino(string? sub = null) => new(sub is null ? _tmp.Ruta : _tmp.Sub(sub), TipoDeDestino.Extraible);

    private (FlujoDeActivacion Flujo, LectorFalso Lector) Flujo(string via = ViasDeInstalacion.Activar, Action<LectorFalso>? archivos = null, IOperacionesDeArchivo? io = null)
    {
        var lector = new LectorFalso();
        if (archivos is null) lector.Archivo(@"X:\licencia-a7a7a7a7-serie1.avlic", FixturesDeLicencia.Bytes("ejemplo.avlic"), Hoy);
        else archivos(lector);
        var buscador = new BuscadorDeLicencias(new UnidadesFalsas(new UnidadInfo(@"X:\", "MEMORIA", TipoDeUnidad.Extraible, true, 1_000_000, 2_000_000, false)),
            new CarpetasFalsas(), lector);
        var flujo = new FlujoDeActivacion(_api, "adm-1", via, _ => Task.FromResult(buscador.Buscar()), lector, new EscritorDeLicencias(io), _recordadas.Add);
        return (flujo, lector);
    }

    // ---------------------------------------------------------------------------------------------------- los tres pasos

    [Fact]
    public async Task LosTresPasos_SolicitudAvacomYArchivo_ConUnaSolaConfirmacion()
    {
        var (f, _) = Flujo();
        Assert.Equal((PasoDeActivacion.Solicitud, 1), (f.Paso, f.NumeroDePaso));

        // 1 · la solicitud queda en la memoria, verificada contra el SHA-256 del nodo
        Assert.True(await f.GuardarSolicitudAsync(Destino()));
        Assert.Equal((PasoDeActivacion.SolicitudGuardada, 1), (f.Paso, f.NumeroDePaso));
        var solicitud = FixturesDeLicencia.Json<SolicitudDeLicencia>("solicitud");
        Assert.Equal(Path.Combine(_tmp.Ruta, solicitud.Nombre), f.RutaDeLaSolicitud);
        Assert.Equal(solicitud.Bytes(), File.ReadAllBytes(f.RutaDeLaSolicitud!));
        Assert.Equal("Solicitud guardada", f.Aviso!.Titulo);
        Assert.Null(f.Aviso.Accion);                                                      // huella de hardware: no hay nada que advertir
        Assert.Equal([_tmp.Ruta], _recordadas);

        // 2 · AVACOM firma (sólo se explica)
        f.Continuar();
        Assert.Equal((PasoDeActivacion.EsperandoLicencia, 2), (f.Paso, f.NumeroDePaso));

        // 3 · las tarjetas, la confirmación y la instalación
        await f.BuscarAsync();
        Assert.Equal((PasoDeActivacion.Eligiendo, 3), (f.Paso, f.NumeroDePaso));
        var candidato = Assert.Single(f.Busqueda!.Candidatos);
        Assert.True(f.Elegir(candidato));
        Assert.Equal(PasoDeActivacion.Confirmando, f.Paso);
        Assert.Contains("«licencia-a7a7a7a7-serie1.avlic» (MEMORIA (X:), guardado el", f.Confirmacion(TimeZoneInfo.Utc));
        Assert.True(await f.InstalarAsync());
        Assert.Equal(PasoDeActivacion.Instalada, f.Paso);
        Assert.Equal(AccionesDeInstalacion.Activada, f.EstadoNuevo!.Accion);
        Assert.Equal("Licencia activada", f.Aviso!.Titulo);
        Assert.Equal(FixturesDeLicencia.Bytes("ejemplo.avlic"), Assert.Single(_api.Enviados));   // lo que se envía son los bytes del archivo, tal cual
        Assert.Equal((1, 1), (_api.Veces("solicitud"), _api.Veces("activar")));
        Assert.Equal(@"X:\", _recordadas[^1]);                                            // la carpeta de donde vino la licencia queda como «última carpeta usada»
    }

    [Fact]
    public async Task YaTengoElArchivo_SaltaDirectoAlPaso3_SinPedirSolicitud()
    {
        var (f, _) = Flujo();
        await f.BuscarAsync();
        Assert.Equal(PasoDeActivacion.Eligiendo, f.Paso);
        Assert.Equal(0, _api.Veces("solicitud"));
        f.VolverAlPaso1();
        Assert.Equal(PasoDeActivacion.Solicitud, f.Paso);
    }

    [Fact]
    public async Task SinArchivos_LoDiceYQueHacer()
    {
        var (f, _) = Flujo(archivos: l => l.Carpeta(@"X:\"));
        await f.BuscarAsync();
        Assert.Equal(PasoDeActivacion.Eligiendo, f.Paso);
        Assert.True(f.Busqueda!.Vacia);
        Assert.Equal((LicenciaTexto.SinArchivos, LicenciaTexto.SinArchivosAccion), (f.Aviso!.Texto, f.Aviso.Accion));
    }

    [Fact]
    public async Task SinConfirmar_NoSeInstalaNada_NiSePuedeElegirLoQueNoEstaEnLaLista()
    {
        var (f, _) = Flujo();
        Assert.False(await f.InstalarAsync());                                            // desde el paso 1
        await f.BuscarAsync();
        Assert.False(await f.InstalarAsync());                                            // desde las tarjetas, sin la confirmación
        var ajeno = f.Busqueda!.Candidatos[0] with { Ruta = @"X:\otra.avlic" };
        Assert.False(f.Elegir(ajeno));
        Assert.Equal(PasoDeActivacion.Eligiendo, f.Paso);
        Assert.Empty(_api.Enviados);
    }

    [Fact]
    public async Task LaConfirmacionEsUnica_DosToquesSonUnEnvio()
    {
        var (f, _) = Flujo();
        await f.BuscarAsync();
        f.Elegir(f.Busqueda!.Candidatos[0]);
        _api.Freno = new TaskCompletionSource();
        var primero = f.InstalarAsync();
        var segundo = f.InstalarAsync();
        Assert.Equal(PasoDeActivacion.Instalando, f.Paso);
        _api.Freno.SetResult();
        Assert.True(await primero);
        Assert.False(await segundo);
        Assert.Equal((1, 1), (_api.Veces("activar"), f.Envios));
    }

    [Fact]
    public async Task UnArchivoRechazado_DiceElMotivoYQueHacer_YNoSeReintenta()
    {
        var (f, _) = Flujo();
        _api.Activar = _ => null;
        _api.ErrorAlFallar = FixturesDeLicencia.Error(400, "error_firma_invalida");
        await f.BuscarAsync();
        f.Elegir(f.Busqueda!.Candidatos[0]);
        Assert.False(await f.InstalarAsync());
        Assert.Equal(PasoDeActivacion.NoInstalada, f.Paso);
        Assert.Equal(LicenciaTexto.Motivo(MotivosDeRechazo.FirmaInvalida), f.Aviso);
        Assert.False(f.PuedeReintentar);
        Assert.False(await f.ReintentarAsync());
        f.VolverALaLista();
        Assert.Equal(PasoDeActivacion.Eligiendo, f.Paso);
        Assert.Equal(1, _api.Veces("activar"));
    }

    [Fact]
    public async Task UnArchivoDeOtroEquipo_LoDice()
    {
        var (f, _) = Flujo();
        _api.Activar = _ => null;
        _api.ErrorAlFallar = FixturesDeLicencia.Error(409, "error_huella_no_coincide");
        await f.BuscarAsync();
        f.Elegir(f.Busqueda!.Candidatos[0]);
        await f.InstalarAsync();
        Assert.Equal("Esta licencia es de otro equipo", f.Aviso!.Titulo);
        Assert.Contains("coinciden 1 de las 3", f.Aviso.Texto);
    }

    [Fact]
    public async Task SinConexion_SeReintentaElMismoArchivo()
    {
        var (f, _) = Flujo();
        _api.Activar = _ => null;
        _api.ErrorAlFallar = FixturesDeLicencia.SinConexion;
        await f.BuscarAsync();
        f.Elegir(f.Busqueda!.Candidatos[0]);
        Assert.False(await f.InstalarAsync());
        Assert.True(f.PuedeReintentar);
        Assert.Equal("Sin conexión con el aula", f.Aviso!.Titulo);
        _api.Activar = _ => FixturesDeLicencia.Estado("activar");
        Assert.True(await f.ReintentarAsync());
        Assert.Equal(PasoDeActivacion.Instalada, f.Paso);
        Assert.Equal(2, _api.Enviados.Count);
        Assert.Equal(_api.Enviados[0], _api.Enviados[1]);
    }

    [Fact]
    public async Task SiElArchivoYaNoEsta_NoSeEnviaNada()
    {
        var (f, lector) = Flujo();
        await f.BuscarAsync();
        var c = f.Busqueda!.Candidatos[0];
        f.Elegir(c);
        lector.Borrar(c.Ruta);                                                            // se retiró la memoria después de listar
        Assert.False(await f.InstalarAsync());
        Assert.Equal((PasoDeActivacion.NoInstalada, LicenciaTexto.ArchivoYaNoEsta), (f.Paso, f.Aviso!.Texto));
        Assert.Empty(_api.Enviados);
    }

    [Fact]
    public async Task SiElArchivoCambioDesdeQueSeListo_NoSeInstala()
    {
        var (f, lector) = Flujo();
        await f.BuscarAsync();
        var c = f.Busqueda!.Candidatos[0];
        f.Elegir(c);
        lector.Cambiar(c.Ruta, FixturesDeLicencia.Bytes("ejemplo-alterada.avlic"));
        Assert.False(await f.InstalarAsync());
        Assert.Equal("El archivo cambió", f.Aviso!.Titulo);
        Assert.Empty(_api.Enviados);
    }

    [Fact]
    public async Task ConLaViaRenovar_SeRenueva()
    {
        var (f, _) = Flujo(ViasDeInstalacion.Renovar);
        await f.BuscarAsync();
        f.Elegir(f.Busqueda!.Candidatos[0]);
        Assert.StartsWith("Vas a renovar la licencia de este equipo con", f.Confirmacion());
        Assert.True(await f.InstalarAsync());
        Assert.Equal((0, 1), (_api.Veces("activar"), _api.Veces("renovar")));
        Assert.Equal("Licencia renovada", f.Aviso!.Titulo);
    }

    [Fact]
    public async Task UnaSolicitudQueNoSePudoGuardar_SeGuardaEnOtroLugar_SinPedirOtraAlNodo()
    {
        var (f, _) = Flujo();
        var retirada = new DestinoElegido(Path.Combine(_tmp.Ruta, "memoria-retirada"), TipoDeDestino.Extraible);
        Assert.False(await f.GuardarSolicitudAsync(retirada));
        Assert.Equal(PasoDeActivacion.Solicitud, f.Paso);
        Assert.Equal("No se pudo guardar la solicitud", f.Aviso!.Titulo);
        Assert.Equal(MotivosDeEscritura.De(MotivoDeEscritura.MedioRetirado).Mensaje, f.Aviso.Texto);
        Assert.True(await f.GuardarSolicitudAsync(Destino("otra")));
        Assert.Equal(PasoDeActivacion.SolicitudGuardada, f.Paso);
        Assert.Equal(1, _api.Veces("solicitud"));
        Assert.DoesNotContain(_recordadas, r => r.Contains("memoria-retirada"));
    }

    [Fact]
    public async Task SiElNodoNoDaLaSolicitud_SeDiceQuienPuede()
    {
        var (f, _) = Flujo();
        _api.Solicitud = () => null;
        _api.ErrorAlFallar = FixturesDeLicencia.Error(403, "error_sin_permiso");
        Assert.False(await f.GuardarSolicitudAsync(Destino()));
        Assert.Equal((PasoDeActivacion.Solicitud, "No se pudo preparar la solicitud"), (f.Paso, f.Aviso!.Titulo));
        Assert.Empty(_tmp.Entradas());
    }

    [Fact]
    public async Task UnaSolicitudConHuellaDeInstalacion_LoAdvierte()
    {
        var (f, _) = Flujo();
        _api.Solicitud = () => FixturesDeLicencia.Json<SolicitudDeLicencia>("solicitud_instalacion");
        Assert.True(await f.GuardarSolicitudAsync(Destino()));
        Assert.Equal(LicenciaTexto.SolicitudConHuellaDeInstalacion, f.Aviso!.Accion);
        Assert.Equal(NivelesDeHuella.Instalacion, f.NivelDeLaSolicitud);
    }

    // ---------------------------------------------------------------------------------------------------- liberar este equipo

    [Fact]
    public async Task Liberar_GuardaElArchivoDeLiberacion_YDiceComoDeshacerlo()
    {
        var f = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias());
        Assert.False(await f.LiberarAsync());                                             // sin destino no hay nada que confirmar
        Assert.True(f.ElegirDestino(Destino()));
        Assert.Equal(PasoDeLiberacion.Confirmando, f.Paso);
        Assert.True(await f.LiberarAsync());
        Assert.Equal(PasoDeLiberacion.Liberada, f.Paso);
        var avrel = FixturesDeLicencia.Liberacion().Archivo;
        Assert.Equal(Path.Combine(_tmp.Ruta, avrel.Nombre), f.RutaDelArchivo);
        Assert.Equal(avrel.Bytes(), File.ReadAllBytes(f.RutaDelArchivo!));
        Assert.Equal(EstadosDeLicencia.SinLicencia, f.EstadoNuevo!.Estado);
        Assert.Equal(LicenciaTexto.LiberarDeshacer, f.Aviso!.Accion);
        Assert.Equal(1, _api.Veces("liberar"));
    }

    [Fact]
    public async Task SiElDestinoYaNoEstaOEstaLleno_NoSeLibera()
    {
        var f = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias());
        f.ElegirDestino(new DestinoElegido(Path.Combine(_tmp.Ruta, "retirada"), TipoDeDestino.Extraible));
        Assert.False(await f.LiberarAsync());
        Assert.Equal((PasoDeLiberacion.ElegirDestino, "Ese lugar ya no está"), (f.Paso, f.Aviso!.Titulo));

        var llena = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias(), new IoConGanchos { EspacioLibreHook = _ => 1_000 });
        llena.ElegirDestino(Destino());
        Assert.False(await llena.LiberarAsync());
        Assert.Equal("No hay espacio", llena.Aviso!.Titulo);
        Assert.Equal(0, _api.Veces("liberar"));
    }

    [Fact]
    public async Task LaLiberacion_SeConfirmaUnaVez_DosToquesUnaLlamada()
    {
        var f = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias());
        f.ElegirDestino(Destino());
        _api.Freno = new TaskCompletionSource();
        var primero = f.LiberarAsync();
        var segundo = f.LiberarAsync();
        _api.Freno.SetResult();
        Assert.True(await primero);
        Assert.False(await segundo);
        Assert.Equal((1, 1), (_api.Veces("liberar"), f.Envios));
    }

    [Fact]
    public async Task SiElNodoNoLibera_NoSeTocaNada_YSePuedeIntentarDeNuevo()
    {
        var f = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias());
        _api.Liberar = () => null;
        _api.ErrorAlFallar = FixturesDeLicencia.Error(409, "error_sin_licencia_para_liberar");
        f.ElegirDestino(Destino());
        Assert.False(await f.LiberarAsync());
        Assert.Equal((PasoDeLiberacion.NoLiberada, "El equipo no se liberó"), (f.Paso, f.Aviso!.Titulo));
        Assert.Empty(_tmp.Entradas());
        _api.Liberar = FixturesDeLicencia.Liberacion;
        Assert.True(f.ElegirDestino(f.Destino!));
        Assert.True(await f.LiberarAsync());
        Assert.Equal(PasoDeLiberacion.Liberada, f.Paso);
    }

    [Fact]
    public async Task SiElArchivoNoSePudoGuardar_SeGuardaEnOtroLugar_SinVolverALiberar()
    {
        var primera = _tmp.Sub("primera");
        var io = new IoConGanchos { CrearNuevoHook = ruta => ruta.StartsWith(primera, StringComparison.OrdinalIgnoreCase)
            ? throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015)) : new OperacionesDeArchivoDelSistema().CrearNuevo(ruta) };
        var f = new FlujoDeLiberacion(_api, "adm-1", new EscritorDeLicencias(io), io);
        f.ElegirDestino(new DestinoElegido(primera, TipoDeDestino.Extraible));
        Assert.True(await f.LiberarAsync());                                              // el equipo SÍ quedó liberado
        Assert.Equal(PasoDeLiberacion.LiberadaSinGuardar, f.Paso);
        Assert.Equal(LicenciaTexto.LiberarSinGuardar, f.Aviso!.Titulo);
        Assert.Empty(_tmp.Entradas(primera));
        Assert.True(await f.GuardarEnOtroDestinoAsync(Destino("segunda")));
        Assert.Equal(PasoDeLiberacion.Liberada, f.Paso);
        Assert.True(File.Exists(f.RutaDelArchivo));
        Assert.Equal(1, _api.Veces("liberar"));
    }

    // ---------------------------------------------------------------------------------------------------- confirmar la fecha

    [Fact]
    public async Task LaFecha_SeConfirmaUnaVez()
    {
        var c = new ConfirmacionDeFecha(_api, "adm-1");
        _api.Freno = new TaskCompletionSource();
        var primero = c.ConfirmarAsync();
        var segundo = await c.ConfirmarAsync();
        Assert.Equal("Ya se está confirmando", segundo.Titulo);
        _api.Freno.SetResult();
        var m = await primero;
        Assert.Equal(("Fecha confirmada", LicenciaTexto.FechaHecha), (m.Titulo, m.Texto));
        Assert.Empty(c.EstadoNuevo!.BanderasActivas);
        Assert.Equal((1, 1), (_api.Veces("reloj"), c.Envios));
    }

    [Fact]
    public async Task SiLaFechaNoSeConfirma_SeDicePorQue()
    {
        _api.Reloj = () => null;
        _api.ErrorAlFallar = FixturesDeLicencia.Error(403, "error_sin_permiso");
        var m = await new ConfirmacionDeFecha(_api, "prof-1").ConfirmarAsync();
        Assert.Equal("La fecha no se confirmó", m.Titulo);
        Assert.False(string.IsNullOrWhiteSpace(m.Accion));
    }
}
