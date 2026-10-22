using System.Text.Json;
using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Actualizacion;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// La pantalla «Actualizaciones» sin interfaz (MOD-017, P-19): el flujo contra un nodo falso que responde con las respuestas REALES del backend (capturadas por Core en
/// <c>Fixtures/actualizacion/</c>), la confirmación ÚNICA y el envío ÚNICO de aplicar y revertir, lo que se ofrece según el rol, la clase abierta y el plazo de 14 días, y el selector táctil de
/// la ventana (sin teclado, con la hora del nodo y la zona del aula).
/// </summary>
public sealed class ActualizacionFlujoTests
{
    private static JsonElement Archivo(string nombre) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "actualizacion", nombre + ".json"))).RootElement.Clone();

    private static readonly JsonSerializerOptions Web = new(JsonSerializerDefaults.Web);

    private static T Cuerpo<T>(string nombre) => Archivo(nombre).GetProperty("cuerpo").Deserialize<T>(Web)!;

    private static ErrorAula ErrorDe(string nombre) =>
        new(Archivo(nombre).GetProperty("status").GetInt32(), Archivo(nombre).GetProperty("cuerpo").GetProperty("codigo").GetString(),
            Archivo(nombre).GetProperty("cuerpo").GetProperty("detail").GetString()!, null, Archivo(nombre).GetProperty("cuerpo").Clone());

    private static readonly UsuarioDeSesion Admin = new("a", "ana", "ADMIN", "admin", 1);
    private static readonly UsuarioDeSesion Tecnico = new("t", "tec", "TECHNICIAN", "technician", 1);

    /// <summary>Un nodo falso: cada respuesta es una de las capturadas; un error se pone en <see cref="Error"/> y la llamada devuelve null.</summary>
    private sealed class NodoFalso : IActualizacionApi
    {
        public string? UltimoMotivo => UltimoError?.Detalle;
        public ErrorAula? UltimoError { get; private set; }
        public ErrorAula? Error;
        public Func<TaskCompletionSource?> Compuerta = () => null;
        public readonly List<string> Llamadas = [];
        public object? ProgramadoCon, RevertidoCon;
        public string Estado = "estado_al_dia";
        public string Ficha = "paquete_verificado";
        public string RespuestaImportar = "importar_201";
        public string RespuestaAplicar = "aplicar_202";
        public string RespuestaRevertir = "revertir_202";
        public string RespuestaProgramar = "programar_200";

        private T? Resp<T>(string llamada, string archivo)
        {
            Llamadas.Add(llamada);
            if (Error is not null) { UltimoError = Error; return default; }
            UltimoError = null;
            return Cuerpo<T>(archivo);
        }

        public Task<EstadoDeActualizacion?> EstadoAsync(string actor, CancellationToken ct = default) => Task.FromResult(Resp<EstadoDeActualizacion>("estado", Estado));
        public Task<ListaDePaquetes?> PaquetesAsync(string actor, CancellationToken ct = default) => Task.FromResult(Resp<ListaDePaquetes>("paquetes", "paquetes_con_candidato"));
        public Task<FichaDePaquete?> PaqueteAsync(string actor, string id, CancellationToken ct = default) => Task.FromResult(Resp<FichaDePaquete>("paquete:" + id, Ficha));
        public Task<HistorialDeActualizacion?> HistorialAsync(string actor, int limite = 50, IReadOnlyList<string>? tipos = null, CancellationToken ct = default) =>
            Task.FromResult(Resp<HistorialDeActualizacion>("historial", "historial"));

        public async Task<FichaDePaquete?> ImportarAsync(string actor, string candidato, CancellationToken ct = default)
        {
            var r = Resp<FichaDePaquete>("importar:" + candidato, RespuestaImportar);
            if (r is not null) Ficha = RespuestaImportar == "importar_201_incompatible" ? "importar_201_incompatible" : "paquete_verificado";
            await Task.Yield();
            return r;
        }

        public Task<FichaDePaquete?> ProgramarAsync(string actor, string id, long desde, long hasta, CancellationToken ct = default)
        {
            ProgramadoCon = (desde, hasta);
            return Task.FromResult(Resp<FichaDePaquete>("programar", RespuestaProgramar));
        }

        public Task<FichaDePaquete?> DesprogramarAsync(string actor, string id, CancellationToken ct = default) => Task.FromResult(Resp<FichaDePaquete>("desprogramar", "desprogramar_200"));

        public async Task<FichaDePaquete?> AplicarAsync(string actor, string id, CancellationToken ct = default)
        {
            var puerta = Compuerta();
            if (puerta is not null) await puerta.Task;
            var r = Resp<FichaDePaquete>("aplicar", RespuestaAplicar);
            if (r is not null) Ficha = RespuestaAplicar;
            return r;
        }

        public async Task<FichaDePaquete?> RevertirAsync(string actor, string id, string nota, CancellationToken ct = default)
        {
            RevertidoCon = nota;
            var puerta = Compuerta();
            if (puerta is not null) await puerta.Task;
            var r = Resp<FichaDePaquete>("revertir", RespuestaRevertir);
            if (r is not null) Ficha = RespuestaRevertir;
            return r;
        }
    }

    private static FlujoDeActualizacion Flujo(NodoFalso nodo, UsuarioDeSesion? usuario = null, bool clase = false, long? ahora = null) =>
        new(nodo, "actor", usuario ?? Admin, () => clase, () => ahora ?? Cuerpo<EstadoDeActualizacion>("estado_al_dia").ServidorEn, TimeZoneInfo.Utc);

    // ================================================================================================== leer

    [Fact]
    public async Task Cargar_LeeEstadoPaquetesEHistorial_YAprendeElRelojDelNodo()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        Assert.True(await f.CargarAsync());
        Assert.Equal(["estado", "paquetes", "historial"], nodo.Llamadas);
        Assert.Equal("al_dia", f.Estado!.Estado);
        Assert.Single(f.Paquetes!.CandidatosOVacio);
        Assert.NotEmpty(f.Historial);
        Assert.False(f.SinConexion);
        Assert.Null(f.Mensaje);
        Assert.Equal(AccionesDelPaquete.Ninguna, f.Acciones);                                      // sin paquete elegido no hay botones
    }

    [Fact]
    public async Task Cargar_SinConexion_ConservaLoQueSeVeia_YLoDice()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        nodo.Error = new ErrorAula(0, "sin_conexion", "x", null, null);
        Assert.False(await f.CargarAsync());
        Assert.True(f.SinConexion);
        Assert.NotNull(f.Estado);                                                                  // lo último que se vio se conserva
        Assert.Equal(ActualizacionTexto.SinConexion, f.Mensaje!.Titulo);
        Assert.True(f.MensajeEsProblema);
    }

    [Fact]
    public async Task Cargar_ConUnRolSinPermiso_NoDejaNadaViejoNiMuestraDatos()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        nodo.Error = ErrorDe("estado_403_docente");
        Assert.False(await f.CargarAsync());
        Assert.Null(f.Estado);
        Assert.Null(f.Paquetes);
        Assert.Equal("Tu rol no ve las actualizaciones", f.Mensaje!.Titulo);
    }

    [Fact]
    public async Task ElAulaVuelveSolaTrasReiniciarse_ElAvisoDeSinConexionSeQuita_YSeDiceQueTermino()
    {
        var nodo = new NodoFalso { Estado = "estado_aplicando", Ficha = "aplicar_202" };
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.True(f.Estado!.Aplicando);
        Assert.False(f.Acciones.Alguna);                                                           // con una actualización en marcha no se ofrece nada

        nodo.Error = new ErrorAula(0, "sin_conexion", "x", null, null);                           // el Host detiene el backend para aplicar
        Assert.False(await f.CargarAsync());
        Assert.True(f.SinConexion);
        Assert.NotNull(f.Estado);                                                                  // lo último que se vio se conserva
        Assert.True(f.Estado!.Aplicando);

        nodo.Error = null;                                                                         // el aula volvió con la actualización aplicada
        nodo.Estado = "estado_al_dia";
        nodo.Ficha = "paquete_aplicado";
        Assert.True(await f.CargarAsync());
        Assert.False(f.SinConexion);
        Assert.Equal("La actualización terminó", f.Mensaje!.Titulo);
        Assert.False(f.MensajeEsProblema);
        Assert.Equal(EstadosDePaquete.Aplicado, f.Elegida!.Estado);
        Assert.True(f.Acciones.Revertir);

        Assert.True(await f.CargarAsync());                                                        // otra lectura no repite el aviso de «terminó» (ya no hay transición)
        Assert.Equal("La actualización terminó", f.Mensaje!.Titulo);
    }

    [Fact]
    public async Task UnaReversionQueTermina_SeDiceComoQuedoElAula()
    {
        var nodo = new NodoFalso { Estado = "estado_aplicando", Ficha = "revertir_202" };
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        nodo.Estado = "estado_al_dia";
        nodo.Ficha = "paquete_revertido";
        await f.CargarAsync();
        Assert.Equal("El aula volvió a la versión anterior", f.Mensaje!.Titulo);
        Assert.True(f.MensajeEsProblema);                                                          // es un hecho a leer con atención, no una celebración
        Assert.False(f.Acciones.Alguna);
    }

    [Fact]
    public async Task Elegir_PideLaFichaCompleta_YOfreceSusAcciones()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        Assert.True(await f.ElegirAsync("17171717-0001-4000-8000-000000000001"));
        Assert.Equal(EstadosDePaquete.Verificado, f.Elegida!.Estado);
        Assert.True(f.Acciones.Programar && f.Acciones.Aplicar);
        f.SoltarElegida();
        Assert.Null(f.Elegida);
    }

    // ================================================================================================== importar

    [Fact]
    public async Task Importar_UnPaqueteBueno_QuedaElegidoYVerificado()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        Assert.True(f.PuedeImportar(f.Paquetes!.CandidatosOVacio[0]));
        Assert.True(await f.ImportarAsync("d18bb9ec0f9bfa22643c0e2b"));
        Assert.Equal(EstadosDePaquete.Verificado, f.Elegida!.Estado);
        Assert.Equal("Paquete verificado", f.Mensaje!.Titulo);
        Assert.False(f.MensajeEsProblema);
        Assert.Contains("importar:d18bb9ec0f9bfa22643c0e2b", nodo.Llamadas);
        Assert.Equal(1, f.Envios);
    }

    [Fact]
    public async Task Importar_UnPaqueteIncompatible_SeDiceYNoSeOfreceAplicarlo()
    {
        var nodo = new NodoFalso { RespuestaImportar = "importar_201_incompatible" };
        var f = Flujo(nodo);
        await f.CargarAsync();
        Assert.True(await f.ImportarAsync("x"));
        Assert.Equal("El paquete llegó, pero no es compatible", f.Mensaje!.Titulo);
        Assert.True(f.MensajeEsProblema);
        Assert.False(f.Acciones.Alguna);
    }

    [Theory]
    [InlineData("importar_422_sin_firma", "El paquete no está firmado")]
    [InlineData("importar_422_alterado", "El archivo no es un paquete válido")]
    [InlineData("importar_422_kid_desconocido", "Firma que el aula no reconoce")]
    public async Task Importar_UnPaqueteRechazado_SeDiceConSuMotivo_YNoQuedaElegido(string error, string titulo)
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        nodo.Error = ErrorDe(error);
        Assert.False(await f.ImportarAsync("x"));
        Assert.Null(f.Elegida);
        Assert.Equal(titulo, f.Mensaje!.Titulo);
        Assert.True(f.MensajeEsProblema);
        Assert.Equal(2, nodo.Llamadas.Count(l => l == "estado"));                                  // se volvió a leer: un rechazo deja su fila en el historial
    }

    [Fact]
    public async Task Importar_ElTecnicoPuede_ElProfesorNoLoVe()
    {
        var nodo = new NodoFalso();
        var tec = Flujo(nodo, Tecnico);
        await tec.CargarAsync();
        Assert.True(tec.PuedeImportar(tec.Paquetes!.CandidatosOVacio[0]));
        Assert.True(await tec.ImportarAsync("d18bb9ec0f9bfa22643c0e2b"));
        Assert.Contains("la administración del colegio puede aplicarlo", tec.Mensaje!.Completo, StringComparison.OrdinalIgnoreCase);             // no se le promete lo que no puede hacer
        Assert.Contains("la administración del colegio puede aplicarlo", tec.FraseDelPaquete(tec.Elegida!), StringComparison.OrdinalIgnoreCase);
        var adm = Flujo(new NodoFalso());
        await adm.CargarAsync();
        await adm.ImportarAsync("x");
        Assert.Contains("Ahora puedes aplicarlo o programarlo", adm.Mensaje!.Completo);
        Assert.False(ReglasDeActualizacion.VeLasActualizaciones(new UsuarioDeSesion("p", "pro", "TEACHER", "teacher", 1)));
    }

    // ================================================================================================== aplicar y revertir

    [Fact]
    public async Task Aplicar_PideUnaConfirmacion_YEnviaUnaVezAunqueSeToqueDosVeces()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.True(f.PedirAplicar());
        Assert.Equal(AccionPendiente.Aplicar, f.Pendiente);
        Assert.True(f.PuedeConfirmar);

        var puerta = new TaskCompletionSource();
        nodo.Compuerta = () => puerta;
        var primero = f.ConfirmarAsync();                                                           // el primer toque viaja…
        var segundo = await f.ConfirmarAsync();                                                     // …y el segundo, mientras tanto, no envía nada
        Assert.False(segundo);
        puerta.SetResult();
        Assert.True(await primero);
        Assert.Equal(1, nodo.Llamadas.Count(l => l == "aplicar"));
        Assert.Equal(AccionPendiente.Ninguna, f.Pendiente);
        Assert.Equal(EstadosDePaquete.Aplicando, f.Elegida!.Estado);
        Assert.Equal("Aplicando la actualización", f.Mensaje!.Titulo);
        Assert.Contains("5 minutos", f.Mensaje.Texto);
        Assert.False(f.Ocupado);

        Assert.False(await f.ConfirmarAsync());                                                     // sin nada pendiente, otro toque tampoco envía
        Assert.Equal(1, nodo.Llamadas.Count(l => l == "aplicar"));
    }

    [Fact]
    public async Task Aplicar_ConUnaClaseAbierta_NoSeOfrece_YDiceQueHacer()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo, clase: true);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.False(f.Acciones.Aplicar);
        Assert.True(f.Acciones.Programar);
        Assert.Contains("clase abierta", f.Acciones.Razon);
        Assert.False(f.PedirAplicar());
        Assert.Equal(AccionPendiente.Ninguna, f.Pendiente);
        Assert.DoesNotContain("aplicar", nodo.Llamadas);
    }

    [Fact]
    public async Task Aplicar_ElNodoRespondeSesionActiva_SeDiceQueEsperaYNadaSeAplica()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        f.PedirAplicar();
        nodo.Error = ErrorDe("aplicar_409_sesion_activa");
        Assert.False(await f.ConfirmarAsync());
        Assert.Equal("Hay una clase abierta", f.Mensaje!.Titulo);
        Assert.True(f.MensajeEsProblema);
        Assert.Equal(AccionPendiente.Ninguna, f.Pendiente);
    }

    [Fact]
    public async Task Aplicar_ElTecnicoSinEscalada_NoLoVe_PeroSiElNodoLoDeniega_SeDiceComoPedirlo()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo, Tecnico);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.False(f.Acciones.Aplicar);
        Assert.False(f.PedirAplicar());
        Assert.Contains("administración", f.Acciones.Razon);
        nodo.Error = ErrorDe("aplicar_403_tecnico");
        Assert.Contains("Pídeselo a la administración", ActualizacionTexto.DeError(nodo.Error).Completo);
    }

    [Fact]
    public async Task Revertir_PideUnMotivoDeLaLista_YLoEnviaComoLaNotaUnaSolaVez()
    {
        var nodo = new NodoFalso { Ficha = "paquete_aplicado" };
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.True(f.Acciones.Revertir);
        Assert.True(f.PedirRevertir());
        Assert.False(f.PuedeConfirmar);                                                             // falta el motivo: la nota es obligatoria
        Assert.False(await f.ConfirmarAsync());
        Assert.Equal(0, f.Envios);
        var motivo = ActualizacionTexto.MotivosDeReversion[1];
        f.ElegirMotivo(motivo);
        Assert.True(f.PuedeConfirmar);
        Assert.True(await f.ConfirmarAsync());
        Assert.Equal(motivo.Nota, nodo.RevertidoCon);
        Assert.Equal("Volviendo a la versión anterior", f.Mensaje!.Titulo);
        Assert.Equal(1, f.Envios);
        Assert.Equal(1, nodo.Llamadas.Count(l => l == "revertir"));
    }

    [Fact]
    public async Task Revertir_PasadosLos14Dias_NoSeOfrece()
    {
        var nodo = new NodoFalso { Ficha = "paquete_aplicado" };
        var aplicado = Cuerpo<FichaDePaquete>("paquete_aplicado");
        var f = Flujo(nodo, ahora: aplicado.RevertibleHasta!.Value + 1);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.False(f.Acciones.Revertir);
        Assert.Contains("14 días", f.Acciones.Razon);
        Assert.False(f.PedirRevertir());
    }

    [Fact]
    public async Task Cancelar_SueltaLoPendiente_SinEnviarNada()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        f.PedirAplicar();
        f.Cancelar();
        Assert.False(f.PuedeConfirmar);
        Assert.False(await f.ConfirmarAsync());
        Assert.DoesNotContain("aplicar", nodo.Llamadas);
    }

    // ================================================================================================== programar

    [Fact]
    public async Task Programar_EnviaLaVentanaDelSelector_YDiceCuandoSeAplica()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        var selector = f.NuevoSelector();
        selector.ElegirDuracion(120);
        Assert.True(await f.ProgramarAsync(selector));
        Assert.Equal((selector.Desde, selector.Hasta), ((long, long))nodo.ProgramadoCon!);
        Assert.Equal(2 * 3_600_000L, selector.Hasta - selector.Desde);
        Assert.Equal("Actualización programada", f.Mensaje!.Titulo);
        Assert.Contains("una clase abierta nunca se interrumpe", f.Mensaje.Completo, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task Programar_SiElNodoRechazaLaVentana_SeDiceQueElijaOtraHora()
    {
        var nodo = new NodoFalso();
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        var selector = f.NuevoSelector();
        nodo.Error = ErrorDe("programar_400");
        Assert.False(await f.ProgramarAsync(selector));                                             // el nodo la rechaza: se dice «elige otra hora»
        Assert.Equal("No se pudo programar", f.Mensaje!.Titulo);
        Assert.Contains("Elige otra hora", f.Mensaje.Completo);
    }

    [Fact]
    public async Task Desprogramar_QuitaLaVentana()
    {
        var nodo = new NodoFalso { Ficha = "paquete_verificado" };
        var f = Flujo(nodo);
        await f.CargarAsync();
        await f.ElegirAsync("p");
        Assert.True(await f.DesprogramarAsync());
        Assert.Equal("Programación cancelada", f.Mensaje!.Titulo);
    }

    // ================================================================================================== el selector de la ventana

    private static long Ms(int a, int mes, int d, int h, int min) => new DateTimeOffset(a, mes, d, h, min, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();

    [Fact]
    public void Selector_ArrancaEnLaProximaMediaHoraConMargen_YNuncaEnElPasado()
    {
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 15, 12), TimeZoneInfo.Utc);
        Assert.Equal(Ms(2026, 10, 21, 15, 30), s.Minimo);                                           // 15:12 + 5 min → 15:30
        Assert.Equal(Ms(2026, 10, 21, 16, 0), s.Inicio);                                            // 15:12 + 30 min → 16:00
        Assert.Equal(60, s.DuracionMin);
        Assert.True(s.EsValida);
        Assert.Equal("hoy de 16:00 a 17:00", s.Resumen);
        Assert.False(s.PuedeAdelantarUnDia);
        Assert.True(s.PuedeAdelantarMediaHora);
        s.MenosMediaHora();
        Assert.Equal(Ms(2026, 10, 21, 15, 30), s.Inicio);
        Assert.False(s.PuedeAdelantarMediaHora);
        s.MenosMediaHora();                                                                         // no baja del mínimo
        Assert.Equal(Ms(2026, 10, 21, 15, 30), s.Inicio);
    }

    [Fact]
    public void Selector_UnaHoraRedonda_AlMinuto_SinMargen_SaltaAlSiguienteBloque()
    {
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 15, 26), TimeZoneInfo.Utc);
        Assert.Equal(Ms(2026, 10, 21, 16, 0), s.Minimo);                                            // 15:26 + 5 = 15:31 → 16:00
        var t = new SelectorDeVentana(Ms(2026, 10, 21, 15, 25), TimeZoneInfo.Utc);
        Assert.Equal(Ms(2026, 10, 21, 15, 30), t.Minimo);                                           // 15:25 + 5 = 15:30 exacto
    }

    [Fact]
    public void Selector_MueveDeMediaHoraYDeUnDia_ConSusTopes()
    {
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 15, 0), TimeZoneInfo.Utc);
        s.MasUnDia();
        Assert.Equal(Ms(2026, 10, 22, 15, 30), s.Inicio);
        s.MasMediaHora();
        Assert.Equal(Ms(2026, 10, 22, 16, 0), s.Inicio);
        Assert.Equal("mañana de 16:00 a 17:00", s.Resumen);
        for (var i = 0; i < 200; i++) s.MasUnDia();
        Assert.False(s.PuedeAtrasarUnDia);
        Assert.True(s.EsValida);
        Assert.True(s.Inicio <= Ms(2026, 10, 21, 15, 0) + 90L * 86_400_000);                        // a 90 días como mucho (lo que acepta el nodo)
        for (var i = 0; i < 200; i++) s.MenosUnDia();
        Assert.True(s.Inicio >= s.Minimo);
    }

    [Fact]
    public void Selector_LasDuracionesSonUnaListaCerrada()
    {
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 15, 0), TimeZoneInfo.Utc);
        s.ElegirDuracion(180);
        Assert.Equal(180, s.DuracionMin);
        s.ElegirDuracion(7);                                                                        // no está en la lista: no cambia
        s.ElegirDuracion(100000);
        Assert.Equal(180, s.DuracionMin);
        Assert.Equal(s.Inicio + 180 * 60_000L, s.Hasta);
        Assert.All(SelectorDeVentana.Duraciones, d => Assert.InRange(d, 10, 1440));
    }

    [Fact]
    public void Selector_LosAtajos_SonMediasHorasExactas_Futuras_YSinRepetirse()
    {
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 15, 12), TimeZoneInfo.Utc);                  // miércoles
        var atajos = s.Atajos();
        Assert.Equal(["En 30 minutos", "Esta noche a las 22:00", "Mañana a las 06:00", "El sábado a las 08:00"], atajos.Select(a => a.Titulo).ToArray());
        Assert.Equal(Ms(2026, 10, 21, 22, 0), atajos[1].InicioMs);
        Assert.Equal(Ms(2026, 10, 22, 6, 0), atajos[2].InicioMs);
        Assert.Equal(Ms(2026, 10, 24, 8, 0), atajos[3].InicioMs);
        Assert.All(atajos, a => { Assert.True(a.InicioMs >= s.Minimo); Assert.Equal(0, a.InicioMs % 1_800_000); });
        s.Elegir(atajos[1].InicioMs);
        Assert.Equal("hoy de 22:00 a 23:00", s.Resumen);

        var tarde = new SelectorDeVentana(Ms(2026, 10, 21, 23, 0), TimeZoneInfo.Utc);                // 23:00: «esta noche a las 22:00» ya pasó y no se ofrece
        Assert.DoesNotContain(tarde.Atajos(), a => a.Titulo.StartsWith("Esta noche"));
        var sabado = new SelectorDeVentana(Ms(2026, 10, 24, 9, 0), TimeZoneInfo.Utc);                // un sábado: el atajo salta al sábado siguiente
        Assert.Equal(Ms(2026, 10, 31, 8, 0), sabado.Atajos().Single(a => a.Titulo.StartsWith("El sábado")).InicioMs);
    }

    [Fact]
    public void Selector_RespetaLaZonaHorariaDelAula()
    {
        // Bogotá es UTC-5 sin horario de verano: las 22:00 locales son las 03:00 UTC del día siguiente.
        var bogota = TimeZoneInfo.CreateCustomTimeZone("co", TimeSpan.FromHours(-5), "co", "co");
        var s = new SelectorDeVentana(Ms(2026, 10, 21, 20, 12), bogota);                             // 15:12 en Bogotá
        var noche = s.Atajos().Single(a => a.Titulo.StartsWith("Esta noche"));
        Assert.Equal(Ms(2026, 10, 22, 3, 0), noche.InicioMs);
        s.Elegir(noche.InicioMs);
        Assert.Equal("22:00", s.HoraTexto);
        Assert.Equal("hoy de 22:00 a 23:00", s.Resumen);
        Assert.Equal(0, (s.Inicio + (long)bogota.BaseUtcOffset.TotalMilliseconds) % 1_800_000);
    }
}
