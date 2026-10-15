using Avacom.Lms.Core.Search;
using Avacom.Lms.Ops.Busqueda;

namespace Avacom.Lms.Ops.Tests;

/// <summary>Lo que la pantalla Buscar (MOD-021) decide sin interfaz: quién la ve en el menú y adónde lleva cada resultado.</summary>
public sealed class BusquedaTests
{
    [Theory]
    [InlineData(true, "TEACHER", true)]
    [InlineData(true, "ADMIN", true)]
    [InlineData(true, "REPORTS", true)]
    [InlineData(true, "TECHNICIAN", false)]
    [InlineData(true, "STUDENT", false)]
    [InlineData(true, null, false)]
    [InlineData(false, null, true)]          // sin sesión (prototipo, Q-34): se deja ver y el nodo decide qué devuelve
    public void Buscar_SeOfreceAQuienPuedeBuscar(bool haySesion, string? rol, bool esperado) => Assert.Equal(esperado, PermisosDeBusqueda.Buscar(haySesion, rol));

    [Fact]
    public void UnCurso_UnaLeccionYUnRecurso_AbrenElCursoEnSuModulo()
    {
        foreach (var tipo in new[] { TiposDeBusqueda.Curso, TiposDeBusqueda.Leccion, TiposDeBusqueda.Recurso })
            Assert.Equal("clase-curso?curso=avacom.co.primary.4.math.fractions&titulo=Fracciones%20propias",
                         DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(tipo, "x", CursoRef: "avacom.co.primary.4.math.fractions"), null, "Fracciones propias"));
        Assert.Null(DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Leccion, "l1"), null, "t"));         // sin curso no hay a dónde ir
    }

    [Fact]
    public void UnaEvaluacion_AbreElPanelDelExamen_YUnEstudio_SuDetalle()
    {
        Assert.Equal("examen-panel?asignacion=a-1", DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Evaluacion, "a-1"), "activa", "t"));
        Assert.Equal("estudio?asignacion=e%201", DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Estudio, "e 1"), "activa", "t"));
    }

    [Fact]
    public void UnaClase_EnCursoVaALaClaseEnVivo_YTerminadaASuCierre()
    {
        var destino = new DestinoDeNavegacion(TiposDeBusqueda.Clase, "s-1");
        Assert.Equal("clase-sesion?sesion=s-1", DestinosDeBusqueda.Ruta(destino, "abierta", "t"));
        Assert.Equal("clase-sesion?sesion=s-1", DestinosDeBusqueda.Ruta(destino, "suspendida", "t"));
        Assert.Equal("clase-cierre?sesion=s-1", DestinosDeBusqueda.Ruta(destino, "cerrada", "t"));
        Assert.Equal("clase-cierre?sesion=s-1", DestinosDeBusqueda.Ruta(destino, "planificada", "t"));
    }

    [Fact]
    public void LoQueNoSeSabeAbrir_NoTieneRuta()
    {
        Assert.Null(DestinosDeBusqueda.Ruta(null, null, null));
        Assert.Null(DestinosDeBusqueda.Ruta(new DestinoDeNavegacion("alumno", "x"), null, null));
        Assert.Null(DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Evaluacion, " "), null, null));
        Assert.Null(DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Clase, ""), "abierta", null));
    }

    [Fact]
    public void ElTituloConCaracteresEspeciales_ViajaCodificadoEnLaRuta()
    {
        var ruta = DestinosDeBusqueda.Ruta(new DestinoDeNavegacion(TiposDeBusqueda.Curso, "c", CursoRef: "c"), null, "Año & «Fracciones»?");
        Assert.DoesNotContain(" ", ruta);
        Assert.DoesNotContain("&Fracciones", ruta);
        Assert.Contains("titulo=A%C3%B1o%20%26%20%C2%ABFracciones%C2%BB%3F", ruta);
    }
}
