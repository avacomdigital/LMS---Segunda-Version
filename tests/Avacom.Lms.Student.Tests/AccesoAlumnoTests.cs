using System.Text.RegularExpressions;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.Acceso;
using Avacom.Lms.Student.Tests.Ayudas;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// El acceso del alumno en la tableta (RF-20…RF-28) sin interfaz: grupo → nombre → PIN, «soy nuevo» con el alias repetido, «PIN pendiente», el visitante, la
/// pausa de la tableta, el reintento sin red y que nada de quien entró quede en memoria. El nodo es <see cref="FalsoAccesoApi"/>.
/// </summary>
public sealed class AccesoAlumnoTests
{
    private DateTimeOffset _ahora = new(2026, 10, 6, 9, 0, 0, TimeSpan.Zero);
    private int _registros;

    private (FlujoDeAcceso Flujo, FalsoAccesoApi Nodo) Armar(Action<FalsoAccesoApi>? preparar = null)
    {
        var nodo = new FalsoAccesoApi()
            .ConGrupo("g5b", "Quinto B", "PIN", 4, ("juan", "Juan P.", "1234"), ("sofia", "Sofía R.", null))
            .ConGrupo("pre", "Preescolar A", "AVATAR", 4, ("lia", "Lía M.", "gato"));
        preparar?.Invoke(nodo);
        var flujo = new FlujoDeAcceso(nodo, "student-TABLETA", _ =>
        {
            _registros++;
            nodo.TabletaRegistrada = true;
            return Task.FromResult(true);
        }, () => _ahora);
        flujo.Iniciar(new ConfiguracionAcceso(true, true, AutoregistroAlumnos: true, Visitante: true));
        return (flujo, nodo);
    }

    [Fact]
    public async Task GrupoNombrePin_Entra_YNoQuedaNadaDeQuienEntro()
    {
        var (flujo, _) = Armar();

        Assert.True((await flujo.CargarGruposAsync()).Ok);
        Assert.Equal(PasoAcceso.Grupo, flujo.Paso);
        Assert.Equal(["Preescolar A", "Quinto B"], flujo.Grupos.Select(g => g.Nombre));

        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        Assert.Equal(PasoAcceso.Nombre, flujo.Paso);
        Assert.Equal(["Juan P.", "Sofía R."], flujo.Alumnos.Select(a => a.Alias));

        flujo.ElegirAlumno(flujo.Alumnos[0]);
        Assert.Equal(PasoAcceso.Pin, flujo.Paso);
        Assert.Equal(4, flujo.LongitudMinima);

        var r = await flujo.EntrarAsync("1234");
        Assert.True(r.Ok);
        Assert.Equal("juan", r.Sesion!.Usuario.Id);
        // BR-053: de vuelta en la lista de grupos, sin grupo, nombre ni nada que reintentar.
        Assert.Equal(PasoAcceso.Grupo, flujo.Paso);
        Assert.Null(flujo.Grupo);
        Assert.Null(flujo.Alumno);
        Assert.False(flujo.PuedeReintentar);
    }

    [Fact]
    public async Task SinTabletaRegistrada_SePresentaYVuelveAPedirLosGrupos()
    {
        var (flujo, nodo) = Armar(n => n.TabletaRegistrada = false);
        _registros = 0;
        // Primera presentación «falla» del lado del nodo (sigue sin registrar) y el nodo contesta dispositivo_no_autorizado: se presenta otra vez.
        var r = await flujo.CargarGruposAsync();
        Assert.True(r.Ok);
        Assert.True(nodo.TabletaRegistrada);
        Assert.True(_registros >= 1);
        Assert.Equal(2, flujo.Grupos.Count);
    }

    [Fact]
    public async Task PinEquivocado_DiceCuantosIntentosQuedan_SinNombrarANadie()
    {
        var (flujo, _) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        flujo.ElegirAlumno(flujo.Alumnos[0]);

        var r = await flujo.EntrarAsync("9999");

        Assert.False(r.Ok);
        Assert.Equal("Ese PIN no es. Te quedan 4 intentos.", r.Mensaje);
        Assert.False(r.SinConexion);
        Assert.Equal(PasoAcceso.Pin, flujo.Paso);
    }

    [Fact]
    public async Task CincoFallos_PausaLaTableta_ConCuentaRegresiva_YElVisitanteSigueDisponible()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        flujo.ElegirAlumno(flujo.Alumnos[0]);

        RespuestaDeAcceso r = RespuestaDeAcceso.Hecho;
        for (var i = 0; i < 5; i++) r = await flujo.EntrarAsync("0000");

        Assert.True(flujo.EnPausa);
        Assert.Equal(120, flujo.SegundosDePausa);
        Assert.Equal("2:00", FlujoDeAcceso.Cuenta(flujo.SegundosDePausa));
        Assert.Equal("Esperemos un momento: vuelve a probar en 2 minutos, o entra como visitante.", r.Mensaje);
        Assert.DoesNotContain("Juan", r.Mensaje);

        // Otro alumno en la misma tableta también espera (RN-33), sin que su PIN se envíe.
        flujo.Volver();
        flujo.ElegirAlumno(flujo.Alumnos[1] with { PinPendiente = false });
        var llamadas = nodo.Llamadas.Count;
        var otro = await flujo.EntrarAsync("1234");
        Assert.False(otro.Ok);
        Assert.Equal(llamadas, nodo.Llamadas.Count);

        // Entrar como visitante nunca se bloquea.
        Assert.True((await flujo.EntrarComoVisitanteAsync()).Ok);

        // Pasado el plazo, se vuelve a poder.
        _ahora = _ahora.AddSeconds(121);
        Assert.False(flujo.EnPausa);
        Assert.Equal(0, flujo.SegundosDePausa);
    }

    [Fact]
    public async Task PinPendiente_PideElegirlo_DosVeces_YEntraConEl()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        var sofia = flujo.Alumnos.Single(a => a.Alias == "Sofía R.");
        Assert.True(sofia.PinPendiente);

        flujo.ElegirAlumno(sofia);
        Assert.Equal(PasoAcceso.ElegirPin, flujo.Paso);

        var primera = await flujo.MarcarPinNuevoAsync("2468");
        Assert.True(primera.PideConfirmar);
        Assert.Equal(FlujoDeAcceso.ConfirmaPin, primera.Mensaje);

        var distinta = await flujo.MarcarPinNuevoAsync("2469");
        Assert.Equal(FlujoDeAcceso.NoCoincidenPin, distinta.Mensaje);
        Assert.DoesNotContain(nodo.Llamadas, l => l.StartsWith("pin:"));

        await flujo.MarcarPinNuevoAsync("2468");
        var r = await flujo.MarcarPinNuevoAsync("2468");

        Assert.True(r.Ok);
        Assert.Equal("sofia", r.Sesion!.Usuario.Id);
        Assert.Contains("pin:sofia", nodo.Llamadas);
    }

    [Fact]
    public async Task SiLaListaNoSabiaDelPinPendiente_ElNodoLoDice_YSePasaAElegirlo()
    {
        var (flujo, _) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        flujo.ElegirAlumno(flujo.Alumnos.Single(a => a.Id == "sofia") with { PinPendiente = false });

        var r = await flujo.EntrarAsync("1111");

        Assert.False(r.Ok);
        Assert.Equal(MensajesDeAcceso.PinPendiente, r.Mensaje);
        Assert.Equal(PasoAcceso.ElegirPin, flujo.Paso);
    }

    [Fact]
    public async Task SoyNuevo_AliasRepetido_OfreceLaSugerencia_YConUnToqueEntra()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));

        flujo.EmpezarRegistro();
        Assert.Equal(PasoAcceso.Nuevo, flujo.Paso);
        Assert.Equal("g5b", flujo.Grupo!.Id);   // el grupo que ya había elegido se queda
        Assert.False(flujo.PrepararRegistro("  ", null).Ok);
        Assert.True(flujo.PrepararRegistro("Juan", "Pérez").Ok);

        Assert.True((await flujo.MarcarPinNuevoAsync("1234")).PideConfirmar);
        var repetido = await flujo.MarcarPinNuevoAsync("1234");

        Assert.False(repetido.Ok);
        Assert.Equal("Juan Pé.", repetido.Sugerencia);
        Assert.Equal("Ya hay alguien llamado Juan P. en este grupo. Añade una letra: Juan Pé.", repetido.Mensaje);
        Assert.Empty(nodo.Altas);

        var r = await flujo.AceptarSugerenciaAsync();

        Assert.True(r.Ok);
        Assert.Equal("Juan Pé.", nodo.Altas.Single().Alias);
        Assert.Equal("1234", nodo.Altas.Single().Pin);
        Assert.Equal("Juan Pé.", r.Sesion!.Usuario.Alias);
    }

    [Fact]
    public async Task SoyNuevo_SinGrupoElegido_PideElegirlo()
    {
        var (flujo, _) = Armar();
        await flujo.CargarGruposAsync();

        flujo.EmpezarRegistro();

        Assert.Null(flujo.Grupo);   // hay dos grupos donde registrarse: no se elige por él
        Assert.Equal(FlujoDeAcceso.FaltaGrupo, flujo.PrepararRegistro("Mateo", null).Mensaje);
        flujo.ElegirGrupoParaRegistro(flujo.GruposParaRegistro.Single(g => g.Id == "g5b"));
        Assert.True(flujo.PrepararRegistro("Mateo", null).Ok);
    }

    [Fact]
    public async Task Visitante_ConElGrupoElegido_EntraEnDosToques()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));

        var r = await flujo.EntrarComoVisitanteAsync();

        Assert.True(r.Ok);
        Assert.True(r.Sesion!.Usuario.EsVisitante);
        Assert.Equal("g5b", nodo.GrupoDelVisitante);
        Assert.Equal(PasoAcceso.Grupo, flujo.Paso);
    }

    [Fact]
    public async Task VisitanteApagado_ElBotonNoSeOfrece_YElNodoLoExplica()
    {
        var (flujo, nodo) = Armar(n => n.Visitante = false);
        flujo.Iniciar(new ConfiguracionAcceso(true, true, AutoregistroAlumnos: false, Visitante: false));
        await flujo.CargarGruposAsync();

        Assert.False(flujo.OfreceVisitante);
        Assert.False(flujo.OfreceRegistro);
        var r = await flujo.EntrarComoVisitanteAsync();
        Assert.Equal("Hoy no se puede entrar como visitante. Pídele ayuda al profesor.", r.Mensaje);
    }

    [Fact]
    public async Task SinRed_LoDice_YReintentaSinVolverAMarcarElPin()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        flujo.ElegirAlumno(flujo.Alumnos[0]);

        nodo.SinRed = true;
        var r = await flujo.EntrarAsync("1234");
        Assert.True(r.SinConexion);
        Assert.Equal(MensajesDeAcceso.SinConexion, r.Mensaje);
        Assert.True(flujo.PuedeReintentar);
        Assert.Null(r.Sesion);   // nunca se simula un acceso

        nodo.SinRed = false;
        var otra = await flujo.ReintentarAsync();
        Assert.True(otra.Ok);
        Assert.Equal("juan", otra.Sesion!.Usuario.Id);
    }

    [Fact]
    public async Task Preescolar_HablaDeDibujos_YElDibujoViajaComoSecreto()
    {
        var (flujo, nodo) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "pre"));
        Assert.True(flujo.UsaAvatar);
        flujo.ElegirAlumno(flujo.Alumnos.Single());

        var mal = await flujo.EntrarAsync("perro");
        Assert.Equal("Ese dibujo no es. Te quedan 4 intentos.", mal.Mensaje);

        var bien = await flujo.EntrarAsync("gato");
        Assert.True(bien.Ok);
        Assert.Equal("lia", bien.Sesion!.Usuario.Id);
    }

    [Fact]
    public async Task GrupoConContrasena_PasaAEntrarConElCodigo()
    {
        var (flujo, _) = Armar(n => n.ConGrupo("sec", "Secundaria 1", "PASSWORD", 8));
        await flujo.CargarGruposAsync();

        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "sec"));

        Assert.Equal(PasoAcceso.Codigo, flujo.Paso);
        Assert.DoesNotContain(flujo.GruposParaRegistro, g => g.Id == "sec");
        Assert.Equal(FlujoDeAcceso.FaltaCodigo, (await flujo.EntrarConCodigoAsync("", "")).Mensaje);
        Assert.Equal($"{FlujoDeAcceso.CodigoNoCoincide} Te quedan 2 intentos.", (await flujo.EntrarConCodigoAsync("A-01", "otra")).Mensaje);
        Assert.True((await flujo.EntrarConCodigoAsync("A-01", "clave")).Ok);
    }

    [Fact]
    public async Task Volver_DesandaLosPasos_SinDejarUnPinAMedias()
    {
        var (flujo, _) = Armar();
        await flujo.CargarGruposAsync();
        await flujo.ElegirGrupoAsync(flujo.Grupos.Single(g => g.Id == "g5b"));
        flujo.ElegirAlumno(flujo.Alumnos.Single(a => a.Id == "sofia"));
        await flujo.MarcarPinNuevoAsync("1357");
        Assert.True(flujo.Doble.Confirmando);

        flujo.Volver();
        Assert.Equal(PasoAcceso.Nombre, flujo.Paso);
        Assert.False(flujo.Doble.Confirmando);
        Assert.Null(flujo.Alumno);
        flujo.Volver();
        Assert.Equal(PasoAcceso.Grupo, flujo.Paso);
        Assert.Null(flujo.Grupo);
        flujo.Volver();
        Assert.Equal(PasoAcceso.Conexion, flujo.Paso);
    }

    [Fact]
    public void Avatares_SonDocePalabrasQueElNodoAcepta()
    {
        Assert.Equal(12, Avatares.Todos.Count);
        Assert.Equal(12, Avatares.Todos.Select(a => a.Clave).Distinct().Count());
        // El dominio de acceso acepta [a-z0-9][a-z0-9-]{2,31}; aquí, además, sólo letras sin tildes.
        Assert.All(Avatares.Todos, a => Assert.Matches(new Regex("^[a-z]{3,32}$"), a.Clave));
        Assert.All(Avatares.Todos, a => Assert.False(string.IsNullOrWhiteSpace(a.Dibujo)));
        Assert.Equal("Gato", Avatares.Por("gato")!.Nombre);
    }

    [Fact]
    public void DobleMarcado_ComparaYEmpiezaDeCero()
    {
        var doble = new DobleMarcado();
        Assert.Equal(EstadoDobleMarcado.PideOtraVez, doble.Marcar("1234"));
        Assert.True(doble.Confirmando);
        Assert.Equal(EstadoDobleMarcado.NoCoinciden, doble.Marcar("4321"));
        Assert.False(doble.Confirmando);
        Assert.Null(doble.Valor);
        Assert.Equal(EstadoDobleMarcado.PideOtraVez, doble.Marcar("1234"));
        Assert.Equal(EstadoDobleMarcado.Coinciden, doble.Marcar("1234"));
        Assert.Equal("1234", doble.Valor);
    }
}
