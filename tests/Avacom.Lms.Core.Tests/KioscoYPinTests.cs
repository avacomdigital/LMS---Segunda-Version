using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Las decisiones puras del bloqueo (kiosk.md §5 y §7: «aísla la lógica detrás de la interfaz para poder probarla con un doble»): qué resultado se informa
/// según lo PEDIDO y lo LOGRADO, qué capacidad se declara y cómo se cuenta la verdad al alumno.
/// </summary>
public sealed class PoliticaDeKioscoTests
{
    private static PlanDeBloqueo Controlado(bool sistema = true) =>
        new(Niveles.Controlado, sistema, true, true, false, true, true, 5, Parcial: !sistema);

    private static readonly PlanDeBloqueo Supervisado = new(Niveles.Supervisado, false, false, true, true, false, false, 5);
    private static readonly CapasDeBloqueo Todas = new(true, true, true, true);

    [Fact]
    public void ControladoConTodasLasCapas_EsAplicado()
    {
        var i = PoliticaDeKiosco.Evaluar(Controlado(), Todas);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, i.Resultado);
        Assert.True(i.Completo);
    }

    [Fact]
    public void ControladoSinLaCapaDelSistema_EsParcial_NoSeEscondeAunqueLoDemasSeAplique()
    {
        // El nodo ya sabe que esta tableta no la tiene (plan.Parcial): aunque la app bloquee todo lo suyo, la salida del sistema operativo sigue abierta.
        var i = PoliticaDeKiosco.Evaluar(Controlado(sistema: false), new CapasDeBloqueo(false, true, true, true));
        Assert.Equal(ResultadosDeBloqueo.Parcial, i.Resultado);
        Assert.False(i.Completo);
        Assert.Contains("capa del sistema", i.Motivo);
    }

    [Fact]
    public void ElSistemaPedidoYNoLogrado_EsParcialYDiceQueFalto()
    {
        var i = PoliticaDeKiosco.Evaluar(Controlado(), new CapasDeBloqueo(false, true, true, true));
        Assert.Equal(ResultadosDeBloqueo.Parcial, i.Resultado);
        Assert.Equal("No se logró: sistema.", i.Motivo);
    }

    [Fact]
    public void NadaLogradoDeLoQueSePidio_EsFallido()
    {
        var i = PoliticaDeKiosco.Evaluar(Controlado(), CapasDeBloqueo.Ninguna);
        Assert.Equal(ResultadosDeBloqueo.Fallido, i.Resultado);
        Assert.Contains("sistema", i.Motivo);
        Assert.Contains("pantallas", i.Motivo);
    }

    [Fact]
    public void TambienEsFallidoUnPlanParcialDondeTampocoLaAppLogroNada()
    {
        Assert.Equal(ResultadosDeBloqueo.Fallido, PoliticaDeKiosco.Evaluar(Controlado(sistema: false), CapasDeBloqueo.Ninguna).Resultado);
    }

    [Fact]
    public void UnPlanQueNoPideNada_EsAplicado_NoHayNadaQueLograr()
    {
        var i = PoliticaDeKiosco.Evaluar(Supervisado, CapasDeBloqueo.Ninguna);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, i.Resultado);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, PoliticaDeKiosco.Evaluar(PlanDeBloqueo.Libre, CapasDeBloqueo.Ninguna).Resultado);
    }

    [Fact]
    public void ElMotivoDeLaPlataformaManda_SiLaPlataformaLoDa()
    {
        var i = PoliticaDeKiosco.Evaluar(Controlado(), CapasDeBloqueo.Ninguna, "La app no es Device Owner.");
        Assert.Equal("La app no es Device Owner.", i.Motivo);
    }

    [Theory]
    [InlineData(true, true, "controlado")]
    [InlineData(false, true, "supervisado")]
    [InlineData(false, false, "abierto")]
    [InlineData(true, false, "abierto")]            // la capa del sistema sin la de la app no garantiza nada que se pueda medir
    public void LaCapacidadQueSeDeclaraEsLaQueDeVerdadSeTiene(bool sistema, bool app, string esperada) =>
        Assert.Equal(esperada, PoliticaDeKiosco.CapacidadDeclarable(sistema, app));

    [Fact]
    public void ElResumenDiceLaVerdadSinAdornos()
    {
        Assert.Equal("Sin bloqueo aplicado.", PoliticaDeKiosco.Resumen(null));
        var completo = PoliticaDeKiosco.Resumen(new InformeDeBloqueo(ResultadosDeBloqueo.Aplicado, Todas));
        Assert.StartsWith("Bloqueo completo", completo);
        Assert.Contains("dispositivo dedicado al examen", completo);
        var parcial = PoliticaDeKiosco.Resumen(new InformeDeBloqueo(ResultadosDeBloqueo.Parcial, new CapasDeBloqueo(false, true, false, false), "Falta el sistema."));
        Assert.StartsWith("Bloqueo parcial", parcial);
        Assert.EndsWith("Falta el sistema.", parcial);
        Assert.Contains("no se pudo aplicar", PoliticaDeKiosco.Resumen(new InformeDeBloqueo(ResultadosDeBloqueo.Fallido, CapasDeBloqueo.Ninguna, "Sin Device Owner.")));
    }

    [Fact]
    public async Task KioscoNulo_DeclaraAbierto_NoAplicaNadaYLoDice()
    {
        var k = new KioscoNulo();
        Assert.Equal(Niveles.Abierto, k.Capacidad);
        Assert.False(k.IsTrueDeviceLockAvailable);
        Assert.NotEmpty(k.LockdownSummary);
        var informe = await k.StartExamLockAsync(Controlado());
        Assert.Equal(ResultadosDeBloqueo.Fallido, informe.Resultado);
        Assert.Equal(ResultadosDeBloqueo.Aplicado, (await k.StartExamLockAsync(PlanDeBloqueo.Libre)).Resultado);
        Assert.Equal(ResultadosDeBloqueo.Liberado, (await k.StopExamLockAsync()).Resultado);
    }

    [Fact]
    public void PlanDeBloqueo_MismasExigenciasIgnoraLaCadenciaDelLatido()
    {
        var a = Controlado();
        Assert.True(a.MismasExigencias(a with { LatidoSeg = 10 }));
        Assert.False(a.MismasExigencias(a with { CapaSistema = false }));
        Assert.False(a.MismasExigencias(null));
        Assert.True(Controlado().PideAlgo);
        Assert.False(Supervisado.PideAlgo);
    }

    [Fact]
    public void EstadosDelIntento_AgrupanComoLoNecesitaLaTableta()
    {
        Assert.True(EstadosIntento.Corriendo(EstadosIntento.EnCursoFueraDePlazo));
        Assert.True(EstadosIntento.Suspendido(EstadosIntento.Restaurando));
        Assert.True(EstadosIntento.AceptaRespuestas(EstadosIntento.Pausado));          // BR-071: lo capturado antes de la pausa llega después
        Assert.False(EstadosIntento.AceptaRespuestas(EstadosIntento.Entregado));
        Assert.True(EstadosIntento.Terminado(EstadosIntento.Anulado));
        Assert.False(EstadosIntento.Terminado(EstadosIntento.NoIniciado));
    }
}

/// <summary>La salida administrativa del kiosco (kiosk.md §5.3): PBKDF2 con sal por equipo, nunca el PIN, y freno contra el recorrido de un PIN corto.</summary>
public sealed class AlmacenDePinTests : IDisposable
{
    private const int Pocas = 1_000;                 // las pruebas no necesitan 210 000 iteraciones
    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private DateTimeOffset ahora = new(2026, 10, 1, 8, 0, 0, TimeSpan.Zero);

    public void Dispose()
    {
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private string Ruta => Path.Combine(carpeta, "pin.json");
    private AlmacenDePin Almacen() => new(Ruta, Pocas, () => ahora);

    [Theory]
    [InlineData("482915", true)]
    [InlineData("4829153", true)]
    [InlineData("12345", false)]                    // corto
    [InlineData("111111", false)]                   // repetición
    [InlineData("123456", false)]                   // escalera
    [InlineData("654321", false)]                   // escalera descendente
    [InlineData("12a456", false)]                   // no son dígitos
    [InlineData("", false)]
    [InlineData(null, false)]
    public void ElPinDebeSerSeisDigitosOMasYNoTrivial(string? pin, bool aceptable) => Assert.Equal(aceptable, AlmacenDePin.EsAceptable(pin));

    [Fact]
    public void SinPinFijado_NoHaySalidaLocal()
    {
        var a = Almacen();
        Assert.False(a.Existe);
        Assert.Equal(ResultadoDePin.SinPin, a.Verificar("482915"));
    }

    [Fact]
    public void ElRegistroNuncaGuardaElPin_UsaSalPropiaYSeReconoceAlReabrir()
    {
        var a = Almacen();
        Assert.True(a.Establecer("482915"));
        var texto = File.ReadAllText(Ruta);
        Assert.DoesNotContain("482915", texto);
        Assert.Contains("\"iteraciones\":1000", texto);
        Assert.Equal(ResultadoDePin.Correcto, Almacen().Verificar("482915"));       // otra instancia sobre el mismo archivo
        Assert.Equal(ResultadoDePin.Incorrecto, Almacen().Verificar("482916"));
    }

    [Fact]
    public void DosEquiposConElMismoPin_GuardanSalesYHashesDistintos()
    {
        var a = AlmacenDePin.Crear("482915", Pocas);
        var b = AlmacenDePin.Crear("482915", Pocas);
        Assert.NotEqual(a.Sal, b.Sal);
        Assert.NotEqual(a.Hash, b.Hash);
        Assert.Equal(ResultadoDePin.Correcto, AlmacenDePin.Comprobar("482915", a));
        Assert.Equal(AlmacenDePin.LongitudSal, Convert.FromBase64String(a.Sal).Length);
        Assert.Equal(AlmacenDePin.LongitudHash, Convert.FromBase64String(a.Hash).Length);
    }

    [Fact]
    public void CambiarElPin_ExigeElActual_Y_ElNuevoDebeSerAceptable()
    {
        var a = Almacen();
        Assert.False(a.Establecer("123456"));                 // trivial: no se fija
        Assert.False(a.Existe);
        Assert.True(a.Establecer("482915"));
        Assert.False(a.Establecer("739104"));                 // sin el actual
        Assert.False(a.Establecer("739104", "000000"));       // con uno equivocado
        Assert.Equal(ResultadoDePin.Correcto, a.Verificar("482915"));
        Assert.True(a.Establecer("739104", "482915"));
        Assert.Equal(ResultadoDePin.Incorrecto, a.Verificar("482915"));
        Assert.Equal(ResultadoDePin.Correcto, a.Verificar("739104"));
    }

    [Fact]
    public void CincoFallosSeguidos_FrenanUnMinuto_Y_UnAciertoNoLoSaltaMientrasDura()
    {
        var a = Almacen();
        a.Establecer("482915");
        for (var i = 0; i < AlmacenDePin.FallosAntesDelFreno; i++) Assert.Equal(ResultadoDePin.Incorrecto, a.Verificar("000001"));
        Assert.Equal(ResultadoDePin.Frenado, a.Verificar("482915"));           // ni el correcto pasa mientras dura el freno
        Assert.True(a.EsperaRestante > TimeSpan.FromSeconds(55));
        ahora += TimeSpan.FromSeconds(61);
        Assert.Null(a.EsperaRestante);
        Assert.Equal(ResultadoDePin.Correcto, a.Verificar("482915"));
    }

    [Fact]
    public void CadaNuevoFreno_DuplicaLaEspera_HastaUnaHora()
    {
        var a = Almacen();
        a.Establecer("482915");
        var esperas = new List<double>();
        for (var ronda = 0; ronda < 9; ronda++)
        {
            for (var i = 0; i < AlmacenDePin.FallosAntesDelFreno; i++) a.Verificar("000001");
            esperas.Add(Math.Round(a.EsperaRestante!.Value.TotalMinutes));
            ahora += a.EsperaRestante!.Value + TimeSpan.FromSeconds(1);
        }
        Assert.Equal(new double[] { 1, 2, 4, 8, 16, 32, 60, 60, 60 }, esperas);
    }

    [Fact]
    public void UnAcierto_ReiniciaLosFallosYElFreno()
    {
        var a = Almacen();
        a.Establecer("482915");
        for (var i = 0; i < AlmacenDePin.FallosAntesDelFreno - 1; i++) a.Verificar("000001");
        Assert.Equal(ResultadoDePin.Correcto, a.Verificar("482915"));
        for (var i = 0; i < AlmacenDePin.FallosAntesDelFreno - 1; i++) Assert.Equal(ResultadoDePin.Incorrecto, a.Verificar("000001"));   // cuatro más: aún sin freno
        Assert.Equal(ResultadoDePin.Correcto, a.Verificar("482915"));
    }

    [Fact]
    public void UnArchivoCorrompidoNoDaSalida_YNuncaLanza()
    {
        File.WriteAllText(Ruta, "{no es json");
        var a = Almacen();
        Assert.False(a.Existe);
        Assert.Equal(ResultadoDePin.SinPin, a.Verificar("482915"));
        File.WriteAllText(Ruta, """{"sal":"!!!","iteraciones":1000,"hash":"???"}""");
        Assert.Equal(ResultadoDePin.Incorrecto, Almacen().Verificar("482915"));       // base64 inválido: no acierta, no lanza
    }
}
