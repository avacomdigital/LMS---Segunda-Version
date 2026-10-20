using System.Text.Json;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Lo que OPS decide sobre la licencia sin decidir la licencia (SEC-001): quién ve el botón y el banner, que el banner nunca sale con una clase abierta (R-01), qué aviso va primero y con qué
/// tono (la evaluación desde el primer día, en atención con 7 días o menos), por qué vía se instala un archivo y qué acciones se ofrecen (ninguna en modo de desarrollo).
/// </summary>
public sealed class ReglasDeLicenciaTests
{
    private static EstadoLicencia Fixture(string nombre) =>
        JsonSerializer.Deserialize<EstadoLicencia>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", nombre + ".json")), Ayudas.Web)!;

    private static UsuarioDeSesion Usuario(string rol, string menu) => new("u-1", "Alias", rol, menu, 2);
    private static readonly UsuarioDeSesion Admin = Usuario("ADMIN", "admin");
    private static readonly UsuarioDeSesion Tecnico = Usuario("TECHNICIAN", "technician");
    private static readonly UsuarioDeSesion Profesor = Usuario("TEACHER", "teacher");
    private static readonly UsuarioDeSesion Reportes = Usuario("REPORTS", "reports");
    private static readonly UsuarioDeSesion Alumno = Usuario("STUDENT", "student");

    private static EstadoLicencia Ilimitada() => Fixture("estado_activa") with { Modo = ModosDeLicencia.Ilimitada, Motivo = MotivosDeEstado.LicenciaIlimitada, Licencia = null, Tipo = TiposDeLicencia.Desarrollo };

    // ---------------------------------------------------------------------------------------------------- quién

    [Fact]
    public void LaLicencia_LaVenLaAdministracionYElTecnico_YSinSesionSeDejaVer()
    {
        Assert.True(ReglasDeLicencia.VeLaLicencia(Admin));
        Assert.True(ReglasDeLicencia.VeLaLicencia(Tecnico));
        Assert.True(ReglasDeLicencia.VeLaLicencia(null));                          // prototipo sin sesión: el nodo decide
        Assert.False(ReglasDeLicencia.VeLaLicencia(Profesor));
        Assert.False(ReglasDeLicencia.VeLaLicencia(Reportes));
        Assert.False(ReglasDeLicencia.VeLaLicencia(Alumno));
        Assert.True(ReglasDeLicencia.VeLaLicencia(Usuario("ADMIN", "otro")));       // el rol basta aunque el menú sea otro
        Assert.True(ReglasDeLicencia.VeLaLicencia(Usuario("OTRO", "technician")));  // y el menú basta aunque el rol sea otro
    }

    [Fact]
    public void ElBanner_NuncaConUnaClaseAbierta_YSoloParaQuienVeLaLicencia()
    {
        Assert.True(ReglasDeLicencia.MostrarBanner(Admin, hayClaseAbierta: false));
        Assert.False(ReglasDeLicencia.MostrarBanner(Admin, hayClaseAbierta: true));
        Assert.False(ReglasDeLicencia.MostrarBanner(null, hayClaseAbierta: true));
        Assert.True(ReglasDeLicencia.MostrarBanner(Tecnico, hayClaseAbierta: false));
        Assert.False(ReglasDeLicencia.MostrarBanner(Profesor, hayClaseAbierta: false));
    }

    // ---------------------------------------------------------------------------------------------------- qué aviso, en qué orden y con qué tono

    [Fact]
    public void LaEvaluacion_VaAlBannerDesdeElPrimerDia_ConTonoInformativo()
    {
        var b = ReglasDeLicencia.Banner(Fixture("estado_sin_licencia"))!;
        Assert.Equal(AvisosDeLicencia.Evaluacion, b.Aviso.Codigo);
        Assert.Equal(TonoDeAviso.Informativo, b.Tono);
        Assert.Equal(0, b.Mas);
        Assert.Equal("Este equipo todavía no tiene licencia: te quedan 30 días de evaluación. Toca «Ver la licencia» para activarla.", b.Completo);
    }

    [Fact]
    public void LaEvaluacionUrgente_PideAtencion()
    {
        var e = Fixture("estado_sin_licencia") with { Avisos = [new AvisoDeLicencia(AvisosDeLicencia.Evaluacion, Dias: 5, Urgente: true)] };
        var b = ReglasDeLicencia.Banner(e)!;
        Assert.Equal(TonoDeAviso.Atencion, b.Tono);
        Assert.Contains("quedan 5 días", b.Texto);
    }

    [Fact]
    public void ElBanner_EligeElMasImportante_YDiceCuantosMasHay()
    {
        var lleno = ReglasDeLicencia.Banner(Fixture("estado_cupo_lleno"))!;
        Assert.Equal(("cupo", "equipos", 1), (lleno.Aviso.Codigo, lleno.Aviso.Tipo, lleno.Mas));
        Assert.Equal(TonoDeAviso.Atencion, lleno.Tono);
        Assert.EndsWith("Hay 1 aviso más.", lleno.Completo);

        var degradada = ReglasDeLicencia.Banner(Fixture("estado_degradada"))!;
        Assert.Equal((AvisosDeLicencia.Degradada, TonoDeAviso.Fuerte), (degradada.Aviso.Codigo, degradada.Tono));
        Assert.Contains("renovarla", degradada.Texto);

        Assert.Equal((AvisosDeLicencia.Gracia, TonoDeAviso.Atencion), (ReglasDeLicencia.Banner(Fixture("estado_gracia"))!.Aviso.Codigo, ReglasDeLicencia.Banner(Fixture("estado_gracia"))!.Tono));
        Assert.Equal(AvisosDeLicencia.LiberacionPendiente, ReglasDeLicencia.Banner(Fixture("estado_liberacion_pendiente"))!.Aviso.Codigo);
        Assert.Equal(AvisosDeLicencia.RelojSospechoso, ReglasDeLicencia.Banner(Fixture("estado_reloj_salto"))!.Aviso.Codigo);
        Assert.Equal(AvisosDeLicencia.HuellaParcial, ReglasDeLicencia.Banner(Fixture("estado_huella_parcial"))!.Aviso.Codigo);
        var porVencer = ReglasDeLicencia.Banner(Fixture("estado_por_vencer_y_cupo"))!;
        Assert.Equal((AvisosDeLicencia.PorVencer, TonoDeAviso.Informativo), (porVencer.Aviso.Codigo, porVencer.Tono));     // 12 días: informa; con 7 o menos, atención
    }

    [Fact]
    public void SinAvisos_NoHayBanner()
    {
        Assert.Null(ReglasDeLicencia.Banner(Fixture("estado_activa")));
        Assert.Null(ReglasDeLicencia.Banner(Fixture("estado_cupo_casi_lleno")));
        Assert.Null(ReglasDeLicencia.Banner(Fixture("reloj_confirmar")));
        Assert.Null(ReglasDeLicencia.Banner(null));
    }

    [Fact]
    public void EnModoDeDesarrollo_NoHayBannerNiAcciones()
    {
        var e = Ilimitada() with { Avisos = [new AvisoDeLicencia(AvisosDeLicencia.Evaluacion, Dias: 3, Urgente: true)] };
        Assert.Null(ReglasDeLicencia.Banner(e));
        Assert.Empty(ReglasDeLicencia.AvisosDelBanner(e));
        Assert.False(ReglasDeLicencia.OfrecerActivacion(e));
        Assert.False(ReglasDeLicencia.OfrecerCopia(e));
        Assert.False(ReglasDeLicencia.OfrecerLiberar(e));
        Assert.False(ReglasDeLicencia.OfrecerConfirmarFecha(e with { Banderas = [BanderasDeLicencia.RelojSospechoso] }));
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(e, Admin));
    }

    [Fact]
    public void ElOrden_EsElDelNodo_AunqueLleguenDesordenados_YNadaSeCalla()
    {
        var e = Fixture("estado_activa") with
        {
            Avisos =
            [
                new AvisoDeLicencia("aviso_que_no_conozco"),
                new AvisoDeLicencia(AvisosDeLicencia.IntegridadAlterada),
                new AvisoDeLicencia(AvisosDeLicencia.HuellaParcial),
                new AvisoDeLicencia(AvisosDeLicencia.RelojSospechoso),
                new AvisoDeLicencia(AvisosDeLicencia.Cupo, Tipo: "usuarios", EnUso: 95, Limite: 100, Porcentaje: 95),
                new AvisoDeLicencia(AvisosDeLicencia.Cupo, Tipo: "equipos", EnUso: 55, Limite: 55, Porcentaje: 100),
                new AvisoDeLicencia(AvisosDeLicencia.PorVencer, Dias: 3, Umbral: 3),
                new AvisoDeLicencia(AvisosDeLicencia.Gracia, MotivosDeEstado.Vencida, 10),
                new AvisoDeLicencia(string.Empty),
            ],
        };
        var orden = ReglasDeLicencia.AvisosDelBanner(e).Select(a => a.Codigo + (a.Tipo is null ? string.Empty : ":" + a.Tipo)).ToArray();
        Assert.Equal(new[] { "gracia", "por_vencer", "cupo:usuarios", "cupo:equipos", "reloj_sospechoso", "huella_parcial", "integridad_alterada", "aviso_que_no_conozco" }, orden);
        Assert.Equal(7, ReglasDeLicencia.Banner(e)!.Mas);                                // el vacío no cuenta
    }

    [Theory]
    [InlineData(AvisosDeLicencia.Degradada, null, null, null, TonoDeAviso.Fuerte)]
    [InlineData(AvisosDeLicencia.Gracia, 20, null, null, TonoDeAviso.Atencion)]
    [InlineData(AvisosDeLicencia.LiberacionPendiente, 14, null, null, TonoDeAviso.Atencion)]
    [InlineData(AvisosDeLicencia.Evaluacion, 30, false, null, TonoDeAviso.Informativo)]
    [InlineData(AvisosDeLicencia.Evaluacion, 7, true, null, TonoDeAviso.Atencion)]
    [InlineData(AvisosDeLicencia.PorVencer, 14, null, null, TonoDeAviso.Informativo)]
    [InlineData(AvisosDeLicencia.PorVencer, 7, null, null, TonoDeAviso.Atencion)]
    [InlineData(AvisosDeLicencia.Cupo, null, null, 92, TonoDeAviso.Informativo)]
    [InlineData(AvisosDeLicencia.Cupo, null, null, 100, TonoDeAviso.Atencion)]
    [InlineData(AvisosDeLicencia.RelojSospechoso, null, null, null, TonoDeAviso.Informativo)]
    [InlineData(AvisosDeLicencia.HuellaParcial, null, null, null, TonoDeAviso.Informativo)]
    [InlineData(AvisosDeLicencia.IntegridadAlterada, null, null, null, TonoDeAviso.Atencion)]
    public void ElTonoDeCadaAviso(string codigo, int? dias, bool? urgente, int? porcentaje, TonoDeAviso tono) =>
        Assert.Equal(tono, ReglasDeLicencia.TonoDe(new AvisoDeLicencia(codigo, Dias: dias, Urgente: urgente, Porcentaje: porcentaje)));

    // ---------------------------------------------------------------------------------------------------- la vía y las acciones

    [Fact]
    public void Renovar_SoloConLicenciaSanaYLaAdministracion()
    {
        Assert.Equal(ViasDeInstalacion.Renovar, ReglasDeLicencia.Via(Fixture("estado_activa"), Admin));
        Assert.Equal(ViasDeInstalacion.Renovar, ReglasDeLicencia.Via(Fixture("reactivar"), Admin));
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_activa"), Tecnico));       // el técnico no tiene license.renew
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_activa"), null));          // sin sesión no se sabe: activar (el nodo decide)
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_sin_licencia"), Admin));
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_gracia"), Admin));         // vencida: puede ser otra licencia
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_degradada"), Admin));
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(Fixture("estado_huella_distinta"), Admin));
        Assert.Equal(ViasDeInstalacion.Activar, ReglasDeLicencia.Via(null, Admin));
        Assert.True(ReglasDeLicencia.LicenciaSana(Fixture("estado_huella_parcial")));
        Assert.False(ReglasDeLicencia.LicenciaSana(Fixture("estado_liberacion_pendiente")));
    }

    [Fact]
    public void LasAcciones_DependenDeLoQueHayInstalado()
    {
        var sin = Fixture("estado_sin_licencia");
        Assert.True(ReglasDeLicencia.OfrecerActivacion(sin));
        Assert.False(ReglasDeLicencia.OfrecerCopia(sin));                          // no hay nada que copiar
        Assert.False(ReglasDeLicencia.OfrecerLiberar(sin));                        // ni que liberar
        Assert.False(ReglasDeLicencia.OfrecerConfirmarFecha(sin));

        foreach (var nombre in new[] { "estado_activa", "estado_gracia", "estado_degradada", "estado_liberacion_pendiente", "estado_huella_distinta" })
        {
            var e = Fixture(nombre);
            Assert.True(ReglasDeLicencia.OfrecerActivacion(e), nombre);
            Assert.True(ReglasDeLicencia.OfrecerCopia(e), nombre);
            Assert.True(ReglasDeLicencia.OfrecerLiberar(e), nombre);
        }
        Assert.True(ReglasDeLicencia.OfrecerConfirmarFecha(Fixture("estado_reloj_salto")));
        Assert.False(ReglasDeLicencia.OfrecerConfirmarFecha(Fixture("estado_reloj_retroceso")));
        Assert.False(ReglasDeLicencia.OfrecerConfirmarFecha(Fixture("reloj_confirmar")));
        Assert.False(ReglasDeLicencia.OfrecerActivacion(null));
    }

    [Fact]
    public void LaAdministracion_SeReconocePorRolOMenu()
    {
        Assert.True(ReglasDeLicencia.EsAdministracion(Admin));
        Assert.True(ReglasDeLicencia.EsAdministracion(Usuario("ADMIN", "x")));
        Assert.False(ReglasDeLicencia.EsAdministracion(Tecnico));
        Assert.False(ReglasDeLicencia.EsAdministracion(null));
    }
}
