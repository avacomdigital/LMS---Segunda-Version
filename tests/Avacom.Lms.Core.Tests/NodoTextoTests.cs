using System.Text.Json;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Nodo;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los textos y las reglas del nodo (MOD-015): cada estado, motivo, estado de consumidor y de problema y cada error tiene su frase; ninguna queda vacía, dice «null» ni deja un hueco; las
/// cifras y las fechas se dicen en español; el banner sólo aparece a quien debe y nunca con una clase abierta; los consumidores se ordenan del peor al mejor.
/// </summary>
public sealed class NodoTextoTests
{
    private static readonly TimeZoneInfo Utc = TimeZoneInfo.Utc;
    private static readonly UsuarioDeSesion Admin = new("adm", "Rectoría", "ADMIN", "admin", 3);
    private static readonly UsuarioDeSesion Tecnico = new("tec", "Soporte", "TECHNICIAN", "technician", 2);
    private static readonly UsuarioDeSesion Docente = new("doc", "Prof.", "TEACHER", "teacher", 2);
    private static readonly UsuarioDeSesion Alumno = new("alu", "Juan", "STUDENT", "student", 1);

    private static T Fixture<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "nodo", nombre + ".json")), Ayudas.Web)!;

    private static void Limpia(string? texto)
    {
        Assert.False(string.IsNullOrWhiteSpace(texto), "frase vacía");
        Assert.DoesNotContain("null", texto, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("{", texto);
        Assert.DoesNotContain("}", texto);
        Assert.DoesNotContain("  ", texto);
    }

    // ---------------------------------------------------------------------------------------------------- estados y motivos

    [Fact]
    public void CadaEstadoDelNodo_TieneRotuloExplicacionYTono()
    {
        foreach (var estado in EstadosDelNodo.Todos)
        {
            Limpia(NodoTexto.Estado(estado));
            Limpia(NodoTexto.ExplicacionDeEstado(estado));
            Assert.NotEqual("Sin estado", NodoTexto.Estado(estado));
        }
        Assert.Equal("Sin estado", NodoTexto.Estado("raro"));
        Assert.Equal(TonoDelNodo.Bien, NodoTexto.TonoDeEstado(EstadosDelNodo.Operativo));
        Assert.Equal(TonoDelNodo.Problema, NodoTexto.TonoDeEstado(EstadosDelNodo.Restringido));
        Assert.Equal(TonoDelNodo.Atencion, NodoTexto.TonoDeEstado(EstadosDelNodo.EnRecuperacion));
        Assert.Equal(TonoDelNodo.Neutro, NodoTexto.TonoDeEstado(null));
    }

    [Fact]
    public void CadaMotivoDeRestriccion_DiceQueHacer()
    {
        foreach (var motivo in MotivosDeRestriccion.Todos)
        {
            var texto = NodoTexto.Motivo(motivo);
            Limpia(texto);
            Assert.DoesNotContain("(", texto);                   // sin el código entre paréntesis: la frase es para una persona
        }
        Assert.Contains("desconocido", NodoTexto.Motivo("desconocido"));
    }

    [Fact]
    public void ConsumidoresYProblemas_TienenSuFrase()
    {
        foreach (var e in EstadosDeConsumidor.Todos) { Limpia(NodoTexto.EstadoDeConsumidor(e)); Assert.NotEqual("Sin estado", NodoTexto.EstadoDeConsumidor(e)); }
        foreach (var e in EstadosDeProblema.Todos) Limpia(NodoTexto.EstadoDeProblema(e));
        Assert.Equal(TonoDelNodo.Problema, NodoTexto.TonoDeConsumidor(EstadosDeConsumidor.Suspendido));
        Assert.Equal("Libro de calificaciones", NodoTexto.NombreDeConsumidor("gradebook"));
        Assert.Equal("Mi consumidor", NodoTexto.NombreDeConsumidor("mi_consumidor"));
        Assert.Equal("Evaluación", NodoTexto.NombreDeFuente("evaluacion"));
        Assert.Equal("Aula", NodoTexto.NombreDeFuente("classroom_engine"));
        var p = Fixture<ProblemasDeCola>("problemas").Problemas.Single();
        Assert.Equal("Evento 3 de Evaluación (evaluacion.intento_abierto.v1) · apartado tras 1 intento para Reportes", NodoTexto.Problema(p));
        Assert.StartsWith("RuntimeError", NodoTexto.ErrorDeProblema(p));
        Assert.Equal("Sin detalle del error.", NodoTexto.ErrorDeProblema(p with { UltimoError = "" }));
        Limpia(NodoTexto.ConfirmarReproceso(p));
        Limpia(NodoTexto.ConfirmarReproduccion("reportes"));
        var fuente = Fixture<ColaDelNodo>("cola").Consumidores.Single(c => c.Nombre == "reportes").Fuentes[0];
        Assert.Equal("Evaluación · marca 3 de 8 · 5 eventos pendientes", NodoTexto.Fuente(fuente));
        Assert.Equal("El evento 42 falló 2 veces; se reintenta a las 10:43:20.", NodoTexto.Reintento(new ReintentoDeFuente(42, 2, Ms(2026, 10, 21, 10, 43, 20), "x"), Utc));
    }

    [Fact]
    public void CifrasFechasYTamanos_EnEspanol()
    {
        Assert.Equal("sin pendientes", NodoTexto.Pendientes(0));
        Assert.Equal("1 evento pendiente", NodoTexto.Pendientes(1));
        Assert.Equal("12.345 eventos pendientes", NodoTexto.Pendientes(12345));
        Assert.Equal("sin eventos apartados", NodoTexto.Apartados(0));
        Assert.Equal("3 eventos apartados", NodoTexto.Apartados(3));
        Assert.Equal("1 evento en la cola", NodoTexto.EventosEnCola(1));
        Assert.Equal("0 B", NodoTexto.Tamano(0));
        Assert.Equal("3 KB", NodoTexto.Tamano(3 * 1024));
        Assert.Equal("512 MB", NodoTexto.Tamano(512L * 1024 * 1024));
        Assert.Equal("1,5 GB", NodoTexto.Tamano((long)(1.5 * 1024 * 1024 * 1024)));
        Assert.Equal("21 de octubre de 2026 a las 10:42", NodoTexto.FechaYHora(Ms(2026, 10, 21, 10, 42, 0), Utc));
        Assert.Equal("21 oct · 10:42", NodoTexto.FechaCorta(Ms(2026, 10, 21, 10, 42, 0), Utc));
    }

    // ---------------------------------------------------------------------------------------------------- errores

    [Fact]
    public void CadaError_TieneTituloTextoYAccion()
    {
        foreach (var codigo in new[] { ErroresDelNodo.SinPermiso, ErroresDelNodo.SesionRequerida, ErroresDelNodo.NoEncontrado, ErroresDelNodo.ConsumidorDesconocido, ErroresDelNodo.ConsumidorSinAplicador,
                                       ErroresDelNodo.ProblemaYaResuelto, ErroresDelNodo.ReprocesoFallido, ErroresDelNodo.DatosInvalidos, ErroresDelNodo.NodoRestringido, "otro" })
        {
            var m = NodoTexto.DeError(new ErrorAula(409, codigo, "detalle", "sugerencia", null));
            Limpia(m.Titulo); Limpia(m.Texto); Limpia(m.Completo);
            Assert.False(string.IsNullOrWhiteSpace(m.Accion), codigo);
        }
        Assert.Contains("escalada", NodoTexto.DeError(new ErrorAula(403, ErroresDelNodo.SinPermiso, "x", "y", null)).Completo);
        Assert.Equal("Sin conexión con el nodo", NodoTexto.DeError(new ErrorAula(0, null, "", null, null)).Titulo);
        Assert.Equal("No se pudo completar", NodoTexto.DeError(null).Titulo);
    }

    // ---------------------------------------------------------------------------------------------------- reglas

    [Fact]
    public void QuienVeElNodo_YElBannerNuncaConClaseAbierta()
    {
        Assert.True(ReglasDeNodo.VeElNodo(null));
        Assert.True(ReglasDeNodo.VeElNodo(Admin));
        Assert.True(ReglasDeNodo.VeElNodo(Tecnico));
        Assert.False(ReglasDeNodo.VeElNodo(Docente));
        Assert.False(ReglasDeNodo.VeElNodo(Alumno));
        Assert.True(ReglasDeNodo.EsAdministracion(Admin));
        Assert.False(ReglasDeNodo.EsAdministracion(Tecnico));
        Assert.False(ReglasDeNodo.EsAdministracion(null));
        Assert.True(ReglasDeNodo.MostrarBanner(Tecnico, hayClaseAbierta: false));
        Assert.False(ReglasDeNodo.MostrarBanner(Tecnico, hayClaseAbierta: true));
        Assert.False(ReglasDeNodo.MostrarBanner(Docente, hayClaseAbierta: false));
        Assert.True(ReglasDeNodo.OfrecerReproceso(Tecnico));
        Assert.False(ReglasDeNodo.OfrecerReproceso(Docente));
    }

    [Fact]
    public void ElBanner_SoloParaRestringidoYEnRecuperacion()
    {
        Assert.Null(ReglasDeNodo.Banner(null));
        Assert.Null(ReglasDeNodo.Banner(new NodoEnSalud(EstadosDelNodo.Operativo, [], false, false, "2.9.1")));
        Assert.Null(ReglasDeNodo.Banner(new NodoEnSalud(EstadosDelNodo.Arrancando, [], false, false, null)));
        var restringido = ReglasDeNodo.Banner(Fixture<SaludConNodo>("health").Nodo);
        Assert.NotNull(restringido);
        Assert.Equal(TonoDeAviso.Fuerte, restringido!.Tono);
        Limpia(restringido.Texto);
        var recuperando = ReglasDeNodo.Banner(new NodoEnSalud(EstadosDelNodo.EnRecuperacion, [], false, true, null));
        Assert.Equal(TonoDeAviso.Atencion, recuperando!.Tono);
        Assert.Contains("clase", recuperando.Texto);
        Limpia(NodoTexto.RecuperacionParaStudent);
    }

    [Fact]
    public void LosConsumidores_SeOrdenanDelPeorAlMejor_YLaColaDiceSiPideAtencion()
    {
        var cola = Fixture<ColaDelNodo>("cola");
        var ordenados = ReglasDeNodo.Ordenados(cola.Consumidores);
        Assert.Equal(["reportes", "libro"], ordenados.Select(c => c.Nombre).ToArray());
        Assert.True(ReglasDeNodo.ColaPideAtencion(cola));
        var sana = cola with { Problemas = 0, Consumidores = cola.Consumidores.Select(c => c with { Estado = EstadosDeConsumidor.AlDia }).ToList() };
        Assert.False(ReglasDeNodo.ColaPideAtencion(sana));
        Assert.False(ReglasDeNodo.ColaPideAtencion(null));
        var p = Fixture<ProblemasDeCola>("problemas").Problemas.Single();
        Assert.True(ReglasDeNodo.OfrecerReprocesar(p, Admin));
        Assert.False(ReglasDeNodo.OfrecerReprocesar(p with { Estado = EstadosDeProblema.Reprocesado }, Admin));
        Assert.False(ReglasDeNodo.OfrecerReprocesar(p, Docente));
    }

    private static long Ms(int anio, int mes, int dia, int hora, int minuto, int segundo) => new DateTimeOffset(anio, mes, dia, hora, minuto, segundo, TimeSpan.Zero).ToUnixTimeMilliseconds();
}
