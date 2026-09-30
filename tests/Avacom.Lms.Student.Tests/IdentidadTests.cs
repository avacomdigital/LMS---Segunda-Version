using Avacom.Lms.Core.Models;
using Avacom.Lms.Student.ModoEstudio.Services;

namespace Avacom.Lms.Student.Tests;

/// <summary>
/// «¿Quién eres?» (D-15): «Modo estudio» no pide código; la persona elige su nombre entre los de los grupos con lecciones asignadas. En un LMS
/// offline nada lo verifica, así que lo que se comprueba es que la elección se respete en cada llamada y que lo de una persona no le quede a la
/// siguiente.
/// </summary>
public sealed class IdentidadTests
{
    [Fact]
    public async Task SinElegirNombre_LaListaPreguntaQuienEres_YNoLlamaAlAula()
    {
        using var e = new Escenario().ConAulaLista();

        var resultado = await e.Servicio.LoadAsync();

        Assert.True(resultado.NeedsIdentity);
        Assert.Empty(resultado.Lessons);
        Assert.Null(e.Servicio.CurrentStudent);
        Assert.DoesNotContain(e.Api.Llamadas, l => l.StartsWith("Asignaciones"));
    }

    [Fact]
    public async Task LosNombres_LlegaOrdenadosConSuGrupo_YElDuenoDeLaTabletaSeOfreceAparte()
    {
        using var e = new Escenario().ConAulaLista(dueno: Escenario.Ethan);

        var roster = await e.Servicio.GetRosterAsync();

        var grupo = Assert.Single(roster.Groups);
        Assert.Equal("Quinto B", grupo.Name);
        Assert.Equal(["Ethan Martínez", "Sofía Ramírez"], grupo.Students.Select(a => a.Name));
        Assert.Equal(Escenario.Ethan, roster.Owner!.Id);
        Assert.Null(roster.Last);
        Assert.True(roster.AulaReachable);
        Assert.False(roster.FromCache);
        Assert.True(roster.HasStudents);
        Assert.Null(roster.Notice);
    }

    [Fact]
    public async Task LosNombres_SeGuardanCifrados_ParaPoderElegirSinConexion()
    {
        using var e = new Escenario().ConAulaLista();

        await e.Servicio.GetRosterAsync();

        var archivo = Path.Combine(e.Local.Carpeta, "estudiantes.avc");
        Assert.True(File.Exists(archivo));
        var bytes = File.ReadAllBytes(archivo);
        Assert.Equal(-1, bytes.AsSpan().IndexOf("Ethan"u8));      // ningún nombre en claro
        Assert.Equal(-1, bytes.AsSpan().IndexOf("Quinto"u8));

        e.Api.EnLinea = false;
        var sinAula = await e.Servicio.GetRosterAsync();

        Assert.False(sinAula.AulaReachable);
        Assert.True(sinAula.FromCache);
        Assert.Equal(2, sinAula.Groups.Single().Students.Count);
    }

    [Fact]
    public async Task SinAulaYSinNombresGuardados_DiceQueHayQueConectarseUnaVez()
    {
        using var e = new Escenario();
        e.Api.EnLinea = false;

        var roster = await e.Servicio.GetRosterAsync();

        Assert.False(roster.HasStudents);
        Assert.Contains("Conéctate al aula", roster.Notice);
    }

    [Fact]
    public async Task ElUltimoNombre_SeOfreceSiNoHayAula_SinDarloPorHecho()
    {
        using var e = new Escenario().ConAulaLista();
        await e.ElegirAsync(Escenario.Sofia);

        // Otra ejecución de la app en la misma tableta, sin aula: la persona no está elegida, pero se le ofrece seguir como la última.
        using var reinicio = new Escenario(conservar: e);
        reinicio.Api.EnLinea = false;
        var roster = await reinicio.Servicio.GetRosterAsync();
        var lista = await reinicio.Servicio.LoadAsync();

        Assert.True(lista.NeedsIdentity);
        Assert.Equal(Escenario.Sofia, roster.Last!.Id);
        Assert.Null(reinicio.Servicio.CurrentStudent);
    }

    [Fact]
    public async Task UnaTabletaQueNuncaEntroAUnaClase_SeDaDeAltaYSeVuelveAPreguntar()
    {
        using var e = new Escenario().ConAulaLista();
        var desconocida = FalsoEstudioApi.Json<EstudiantesEstudio>("""{"disponible":false,"motivo":"dispositivo_desconocido","grupos":[],"dueno":null,"servidor_en":1790000000000}""");
        e.Api.Estudiantes = () => e.Api.Registros == 0 ? desconocida : Escenario.Nombres();

        var roster = await e.Servicio.GetRosterAsync();

        Assert.Equal(1, e.Api.Registros);
        Assert.True(roster.HasStudents);
    }

    [Theory]
    [InlineData("dispositivo_bloqueado", "bloqueada")]
    [InlineData("dispositivo_inactivo", "retirada")]
    [InlineData("nodo_no_instalado", "no está lista")]
    public async Task UnaTabletaQueNoSePuedeUsar_ExplicaPorQueSinTecnicismos(string motivo, string fragmento)
    {
        using var e = new Escenario();
        e.Api.Estudiantes = () => FalsoEstudioApi.Json<EstudiantesEstudio>($$"""{"disponible":false,"motivo":"{{motivo}}","grupos":[],"dueno":null,"servidor_en":1790000000000}""");

        var roster = await e.Servicio.GetRosterAsync();

        Assert.False(roster.HasStudents);
        Assert.Contains(fragmento, roster.Notice);
    }

    [Fact]
    public async Task SinLeccionesAsignadas_DiceQueTodaviaNoHayNadie()
    {
        using var e = new Escenario();
        e.Api.Estudiantes = () => FalsoEstudioApi.Json<EstudiantesEstudio>("""{"disponible":true,"motivo":"","grupos":[],"dueno":null,"servidor_en":1790000000000}""");

        var roster = await e.Servicio.GetRosterAsync();

        Assert.Contains("Todavía no hay lecciones asignadas", roster.Notice);
    }

    [Fact]
    public async Task ElegirUnNombre_LoDejaComoQuienEstudia_YSePideAlAulaConEseAlumnoEnCadaLlamada()
    {
        using var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());

        await e.ElegirAsync(Escenario.Sofia);
        var lista = await e.CargarAsync();

        Assert.Equal(new StudyStudent(Escenario.Sofia, "Sofía Ramírez"), e.Servicio.CurrentStudent);
        Assert.Single(lista.Lessons);
        Assert.Contains($"Estado({Escenario.Dispositivo},{Escenario.Sofia})", e.Api.Llamadas);
        Assert.Contains($"AbrirSesion({Escenario.Dispositivo},{Escenario.Sofia})", e.Api.Llamadas);
        Assert.Contains($"Asignaciones({Escenario.Dispositivo},{Escenario.Sofia})", e.Api.Llamadas);
    }

    [Fact]
    public async Task ElegirAOtraPersona_LeQuitaALaTabletaLoPersonalDeLaAnterior_PeroConservaSuTrabajoSinEnviar()
    {
        using var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();
        Assert.NotNull(e.Local.Almacen.LeerLista(Escenario.Ethan));
        e.Local.Cola.Encolar(Escenario.Ethan, "study.lesson.completed", Escenario.Respuesta("""{"asignacion_id":"asig-1"}"""));

        await e.ElegirAsync(Escenario.Sofia);

        Assert.Null(e.Local.Almacen.LeerLista(Escenario.Ethan));                   // lo personal de Ethan ya no está a la vista
        Assert.Equal(1, e.Local.Cola.CantidadPendiente(Escenario.Ethan));          // pero lo que hizo sin enviar sale solo: nada se pierde
        Assert.Equal(Escenario.Sofia, e.Servicio.CurrentStudent!.Id);
    }

    [Fact]
    public async Task Cambiar_VuelveAPreguntar_YNoBorraNada_YElMismoNombreSigueDondeIba()
    {
        using var e = new Escenario().ConAulaLista();
        e.Api.Asignaciones = _ => Escenario.ListaDe(Escenario.AsignacionJson());
        await e.ElegirAsync(Escenario.Ethan);
        await e.CargarAsync();

        await e.Servicio.ChangeStudentAsync();

        Assert.Null(e.Servicio.CurrentStudent);
        Assert.True((await e.Servicio.LoadAsync()).NeedsIdentity);
        Assert.NotNull(e.Local.Almacen.LeerLista(Escenario.Ethan));                // no se borró nada
        var roster = await e.Servicio.GetRosterAsync();
        Assert.Equal(Escenario.Ethan, roster.Last!.Id);                            // se ofrece seguir como Ethan

        await e.ElegirAsync(Escenario.Ethan);
        Assert.NotNull(e.Local.Almacen.LeerLista(Escenario.Ethan));                // el mismo nombre no limpia nada
    }
}
