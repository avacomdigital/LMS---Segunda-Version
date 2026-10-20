using System.Reflection;
using System.Text.Json;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los textos de la licencia (MOD-018): cada estado, motivo, aviso, bandera y error tiene su frase; ninguna queda vacía, dice «null» ni deja un hueco sin llenar («{n}»); las fechas y los días
/// se dicen en español; los textos que el nodo y el cliente comparten (aun_no_vigente, MSG-063) dicen lo mismo; y la hoja de la copia de custodia no lleva datos de personas ni la huella.
/// En «estado global» por la misma razón que <see cref="ContratoLicenciaTests"/>: sus ~800 casos no deben alterar el reparto de la fase en paralelo.
/// </summary>
[Collection("estado global")]
public sealed class LicenciaTextoTests
{
    private static readonly TimeZoneInfo Utc = TimeZoneInfo.Utc;

    private static EstadoLicencia Fixture(string nombre) =>
        JsonSerializer.Deserialize<EstadoLicencia>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", nombre + ".json")), Ayudas.Web)!;

    private static long Ms(int anio, int mes, int dia) => new DateTimeOffset(anio, mes, dia, 12, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();

    /// <summary>Lo que ninguna frase puede tener: un hueco sin llenar, un «null», un espacio doble o un código del contrato.</summary>
    private static void Limpia(string? texto)
    {
        Assert.False(string.IsNullOrWhiteSpace(texto), "frase vacía");
        Assert.DoesNotContain("null", texto, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("{", texto);
        Assert.DoesNotContain("}", texto);
        Assert.DoesNotContain("  ", texto);
        foreach (var codigo in new[] { "sin_licencia", "en_gracia", "liberacion_pendiente", "licencia_invalida", "cupo_agotado", "no_disponible_por_licencia", "reloj_sospechoso" })
            Assert.DoesNotContain(codigo, texto);
    }

    // ---------------------------------------------------------------------------------------------------- fechas y días

    [Fact]
    public void LasFechas_SeDicenEnEspanol()
    {
        Assert.Equal("12 de octubre de 2027", LicenciaTexto.Fecha(Ms(2027, 10, 12), Utc));
        Assert.Equal("1 de enero de 2026", LicenciaTexto.Fecha(Ms(2026, 1, 1), Utc));
        Assert.Equal("12 de octubre de 2027 a las 12:00", LicenciaTexto.FechaYHora(Ms(2027, 10, 12), Utc));
    }

    [Theory]
    [InlineData(357, "quedan 357 días")]
    [InlineData(2, "quedan 2 días")]
    [InlineData(1, "queda 1 día")]
    [InlineData(0, "hoy es el último día")]
    [InlineData(-3, "hoy es el último día")]
    public void LosDias_EnSingularYPlural(int dias, string esperado) => Assert.Equal(esperado, LicenciaTexto.Quedan(dias));

    [Fact]
    public void LaLicenciaActiva_DiceCuandoVenceYCuantoQueda()
    {
        var e = Fixture("estado_activa") with { Vigencia = new VigenciaDeLicencia(Ms(2026, 10, 1), Ms(2027, 10, 12), 30, Ms(2027, 10, 12), 357) };
        Assert.Equal("Licencia activa", LicenciaTexto.Titulo(e));
        Assert.Equal("Vence el 12 de octubre de 2027 · quedan 357 días.", LicenciaTexto.Frase(e, Utc));
        Assert.Equal("Del 1 de octubre de 2026 al 12 de octubre de 2027 · 30 días de gracia", LicenciaTexto.Vigencia(e, Utc));
        Assert.Equal("Activa", LicenciaTexto.EstadoBreve(e));
        Assert.Equal(TonoDeAviso.Informativo, LicenciaTexto.TonoDelEstado(e));
    }

    // ---------------------------------------------------------------------------------------------------- cada estado y cada motivo

    public static IEnumerable<object[]> EstadosYMotivos()
    {
        foreach (var estado in EstadosDeLicencia.Todos)
            foreach (var motivo in MotivosDeEstado.Todos.Where(m => m != MotivosDeEstado.LicenciaIlimitada))
                foreach (var dias in new int?[] { 0, 1, 12, null })
                    yield return [estado, motivo, dias!];
    }

    [Theory]
    [MemberData(nameof(EstadosYMotivos))]
    public void CadaEstado_ConCadaMotivo_TieneTituloYFraseLimpios(string estado, string motivo, int? dias)
    {
        var con = Fixture("estado_activa") with { Estado = estado, Motivo = motivo, Vigencia = Fixture("estado_activa").Vigencia! with { DiasRestantes = dias } };
        var sin = Fixture("estado_sin_licencia") with { Estado = estado, Motivo = motivo, Vigencia = Fixture("estado_sin_licencia").Vigencia! with { DiasRestantes = dias } };
        foreach (var e in new[] { con, sin })
        {
            Limpia(LicenciaTexto.Titulo(e));
            Limpia(LicenciaTexto.Frase(e, Utc));
            Limpia(LicenciaTexto.EstadoBreve(e));
            Assert.NotEqual("Estado de la licencia", LicenciaTexto.Titulo(e));                     // todo estado conocido tiene su propio título
        }
    }

    [Fact]
    public void UnEstadoDesconocido_NoSeCalla()
    {
        var e = Fixture("estado_activa") with { Estado = "otro_estado_nuevo", Motivo = "otro" };
        Assert.Equal("Estado de la licencia", LicenciaTexto.Titulo(e));
        Limpia(LicenciaTexto.Frase(e));
        Assert.Contains(LicenciaTexto.NucleoSigue, LicenciaTexto.Frase(e));
    }

    [Fact]
    public void ElModoDeDesarrollo_LoDice()
    {
        var e = Fixture("estado_activa") with { Modo = ModosDeLicencia.Ilimitada, Motivo = MotivosDeEstado.LicenciaIlimitada, Licencia = null };
        Assert.True(e.Ilimitada);
        Assert.Equal("Modo de desarrollo: sin licencia", LicenciaTexto.Titulo(e));
        Limpia(LicenciaTexto.Frase(e));
        Assert.Equal("Modo de desarrollo", LicenciaTexto.EstadoBreve(e));
    }

    [Fact]
    public void LosEstadosReales_DicenSusCifras()
    {
        Assert.Contains("quedan 30 días", LicenciaTexto.Frase(Fixture("estado_sin_licencia"), Utc));
        Assert.StartsWith("La licencia venció el ", LicenciaTexto.Frase(Fixture("estado_gracia"), Utc));
        Assert.Contains("22 días más", LicenciaTexto.Frase(Fixture("estado_gracia"), Utc));
        Assert.Contains(LicenciaTexto.NucleoSigue, LicenciaTexto.Frase(Fixture("estado_degradada"), Utc));
        Assert.Equal(LicenciaTexto.Msg063(14), LicenciaTexto.Frase(Fixture("estado_liberacion_pendiente"), Utc));
        Assert.Contains("otro equipo", LicenciaTexto.Titulo(Fixture("estado_huella_distinta")));
        Assert.Equal(TonoDeAviso.Fuerte, LicenciaTexto.TonoDelEstado(Fixture("estado_degradada")));
        Assert.Equal(TonoDeAviso.Atencion, LicenciaTexto.TonoDelEstado(Fixture("estado_gracia")));
        Assert.Equal("Reactivada", LicenciaTexto.EstadoBreve(Fixture("reactivar")));
    }

    [Fact]
    public void Msg063_EsLaFraseDelMaestro()
    {
        Assert.Equal("Puedes seguir instalando y dar clase 14 días mientras se libera. Esta licencia está en uso en otra aula.", LicenciaTexto.Msg063(14));
        Assert.Equal("Puedes seguir instalando y dar clase 1 día mientras se libera. Esta licencia está en uso en otra aula.", LicenciaTexto.Msg063(1));
    }

    // ---------------------------------------------------------------------------------------------------- huella y banderas

    [Fact]
    public void LaHuella_SeExplicaSinIdentificadores()
    {
        Assert.Equal("Esta licencia se selló a una huella de instalación: es más débil que la de hardware.",
            LicenciaTexto.Huella(new HuellaDelEquipo(NivelesDeHuella.Instalacion, true, false, 1, 1, 1)));
        Assert.Equal("La licencia está sellada al hardware de este equipo: coinciden 4 de 4 piezas y hacen falta 3.", LicenciaTexto.Huella(Fixture("estado_activa").Huella));
        Assert.StartsWith("Este equipo no coincide con el de la licencia: coinciden 1 de 4", LicenciaTexto.Huella(Fixture("estado_huella_distinta").Huella));
        Assert.EndsWith("Una pieza del equipo cambió y la licencia sigue valiendo.", LicenciaTexto.Huella(Fixture("estado_huella_parcial").Huella));
        Assert.Contains("hardware", LicenciaTexto.Huella(Fixture("estado_sin_licencia").Huella));
        Assert.Contains("instalación", LicenciaTexto.Huella(new HuellaDelEquipo(NivelesDeHuella.Instalacion, null, false, null, null, null)));
        Limpia(LicenciaTexto.Huella(null));
        Assert.Equal("Instalación (más débil)", LicenciaTexto.NivelDeHuella(NivelesDeHuella.Instalacion));
        Assert.Equal("Hardware", LicenciaTexto.NivelDeHuella(NivelesDeHuella.Hardware));
    }

    [Fact]
    public void CadaBandera_TieneSuFraseYSuEtiqueta()
    {
        foreach (var b in BanderasDeLicencia.Todas.Append("otra_bandera"))
        {
            Limpia(LicenciaTexto.Bandera(b));
            Limpia(LicenciaTexto.BanderaBreve(b));
        }
        Assert.Contains("confírmala", LicenciaTexto.Bandera(BanderasDeLicencia.RelojSospechoso));
    }

    [Fact]
    public void LaFechaAdelantada_DiceLasDosFechas_YQueElAulaNoLaAcepto()
    {
        // Q-L13: un error con la fecha que tiene el equipo y la que el aula esperaba; nunca promete pausar nada
        var aviso = new AvisoDeLicencia(AvisosDeLicencia.RelojAdelantado, AdelantoDias: 32, FechaEquipo: Ms(2027, 3, 5), FechaEsperada: Ms(2027, 2, 1));
        var t = LicenciaTexto.Aviso(aviso, null, Utc);
        Assert.Contains("5 de marzo de 2027 a las 12:00", t);
        Assert.Contains("1 de febrero de 2027", t);
        Assert.Contains("está adelantada", t);
        Assert.Contains("No se aceptó", t);
        Assert.Contains("nada se pone en pausa", t);
        Assert.Contains("Corrígela", t);
        Limpia(t);
        Assert.Equal(LicenciaTexto.Bandera(BanderasDeLicencia.RelojAdelantado), LicenciaTexto.Aviso(new AvisoDeLicencia(AvisosDeLicencia.RelojAdelantado)));     // sin las fechas: la frase de la bandera
        Assert.Equal("Fecha adelantada", LicenciaTexto.BanderaBreve(BanderasDeLicencia.RelojAdelantado));
        Assert.Contains("confirmarla", LicenciaTexto.LlamadaDelBanner(aviso));
        Assert.Contains("Corrígela", LicenciaTexto.Bandera(BanderasDeLicencia.RelojAdelantado));
        Assert.Contains("el aula guarda esa fecha", LicenciaTexto.ConfirmacionDeFecha(Ms(2027, 3, 5), Utc));
    }

    [Fact]
    public void CadaModulo_TieneNombreYDescripcion_YLosBoletinesNoSePausan()
    {
        foreach (var c in CapacidadesLicenciables.Todas.Append("otro"))
        {
            Limpia(LicenciaTexto.Capacidad(c));
            Limpia(LicenciaTexto.DescripcionDeCapacidad(c));
        }
        Assert.Contains("boletines", LicenciaTexto.DescripcionDeCapacidad(CapacidadesLicenciables.Reportes));       // Q-L12 · D-6: no se licencian
    }

    // ---------------------------------------------------------------------------------------------------- avisos

    public static IEnumerable<object[]> Avisos()
    {
        foreach (var codigo in AvisosDeLicencia.Todos.Append("aviso_nuevo"))
            foreach (var motivo in MotivosDeEstado.Todos.Append(null))
                foreach (var dias in new int?[] { 0, 1, 12, 30, null })
                    yield return [new AvisoDeLicencia(codigo, motivo, dias, dias is <= 7, 14, "equipos", 50, 55, 91)];
        yield return [new AvisoDeLicencia(AvisosDeLicencia.Cupo, Tipo: "usuarios", EnUso: 4, Limite: 4, Porcentaje: 100)];
        yield return [new AvisoDeLicencia(AvisosDeLicencia.Cupo)];
    }

    [Theory]
    [MemberData(nameof(Avisos))]
    public void CadaAviso_TieneSuFraseYSuLlamada(AvisoDeLicencia aviso)
    {
        Limpia(LicenciaTexto.Aviso(aviso, Fixture("estado_activa"), Utc));
        Limpia(LicenciaTexto.Aviso(aviso));
        Limpia(LicenciaTexto.LlamadaDelBanner(aviso));
        Assert.Contains("«Ver la licencia»", LicenciaTexto.LlamadaDelBanner(aviso));
    }

    [Fact]
    public void LaEvaluacion_SeAvisaDesdeElPrimerDia_ConLaFraseAcordada()
    {
        var aviso = Assert.Single(Fixture("estado_sin_licencia").AvisosActivos);
        Assert.Equal("Este equipo todavía no tiene licencia: te quedan 30 días de evaluación.", LicenciaTexto.Aviso(aviso));
        Assert.Equal("Toca «Ver la licencia» para activarla.", LicenciaTexto.LlamadaDelBanner(aviso));
        var urgente = new AvisoDeLicencia(AvisosDeLicencia.Evaluacion, Dias: 3, Urgente: true);
        Assert.Equal("Este equipo todavía no tiene licencia y quedan 3 días de evaluación. Actívala cuanto antes para que nada se ponga en pausa.", LicenciaTexto.Aviso(urgente));
        Assert.Contains("queda 1 día", LicenciaTexto.Aviso(new AvisoDeLicencia(AvisosDeLicencia.Evaluacion, Dias: 1, Urgente: true)));
    }

    [Fact]
    public void LosAvisosReales_DicenSusCifras()
    {
        Assert.Contains("quedan 22 días de gracia", LicenciaTexto.Aviso(Fixture("estado_gracia").AvisosActivos[0]));
        Assert.Contains("Las clases siguen igual", LicenciaTexto.Aviso(Fixture("estado_degradada").AvisosActivos[0]));
        var porVencer = Fixture("estado_por_vencer_y_cupo");
        Assert.StartsWith("La licencia vence en 12 días (el ", LicenciaTexto.Aviso(porVencer.AvisosActivos[0], porVencer, Utc));
        var lleno = Fixture("estado_cupo_lleno");
        Assert.Contains("cupo de equipos de la licencia (2 de 2)", LicenciaTexto.Aviso(lleno.AvisosActivos[0]));
        Assert.Contains("cupo de usuarios de la licencia (4 de 4)", LicenciaTexto.Aviso(lleno.AvisosActivos[1]));
        Assert.Contains("el 91 % del cupo de equipos", LicenciaTexto.Aviso(new AvisoDeLicencia(AvisosDeLicencia.Cupo, Tipo: "equipos", EnUso: 50, Limite: 55, Porcentaje: 91)));
        Assert.Equal(LicenciaTexto.Msg063(14), LicenciaTexto.Aviso(Fixture("estado_liberacion_pendiente").AvisosActivos[0]));
        Assert.Equal(string.Empty, LicenciaTexto.MasAvisos(0));
        Assert.Equal("Hay 1 aviso más.", LicenciaTexto.MasAvisos(1));
        Assert.Equal("Hay 3 avisos más.", LicenciaTexto.MasAvisos(3));
    }

    // ---------------------------------------------------------------------------------------------------- motivos de rechazo y errores

    [Fact]
    public void CadaMotivoDeRechazo_DiceQuePasoYQueHacer()
    {
        foreach (var motivo in MotivosDeRechazo.Todos.Append("motivo_nuevo").Append(null))
        {
            var m = LicenciaTexto.Motivo(motivo);
            Limpia(m.Titulo);
            Limpia(m.Texto);
            Limpia(m.Accion);
        }
        Assert.Equal(MotivosDeRechazo.Todos.Count, MotivosDeRechazo.Todos.Select(m => LicenciaTexto.Motivo(m).Texto).Distinct().Count());   // ninguno se dice igual que otro
        Assert.Contains("Pide a AVACOM", LicenciaTexto.Motivo(MotivosDeRechazo.CampoFaltante).Accion);
        Assert.Contains("libera este equipo", LicenciaTexto.Motivo(MotivosDeRechazo.OtraLicencia).Accion);
    }

    private static ErrorAula Error(int estado, string? codigo, string json = "{}") => new(estado, codigo, "Detalle del nodo.", null, Ayudas.Json(json));

    public static IEnumerable<object[]> Errores() =>
    [
        [Error(400, CodigosDeLicencia.LicenciaInvalida, """{"motivo":"firma_invalida"}""")],
        [Error(400, CodigosDeLicencia.LicenciaInvalida, """{"motivo":"algo_nuevo"}""")],
        [Error(400, CodigosDeLicencia.LicenciaInvalida)],
        [Error(409, CodigosDeLicencia.HuellaNoCoincide, """{"coinciden":1,"k":3}""")],
        [Error(409, CodigosDeLicencia.HuellaNoCoincide)],
        [Error(409, CodigosDeLicencia.Conflicto, """{"motivo":"sin_licencia_instalada"}""")],
        [Error(409, CodigosDeLicencia.Conflicto)],
        [Error(404, CodigosDeLicencia.NoEncontrado, """{"motivo":"sin_licencia_instalada"}""")],
        [Error(404, CodigosDeLicencia.NoEncontrado)],
        [Error(403, CodigosDeLicencia.SinPermiso, """{"permiso":"license.read"}""")],
        [Error(403, CodigosDeLicencia.SinPermiso, """{"permiso":"license.activate"}""")],
        [Error(403, CodigosDeLicencia.SinPermiso, """{"permiso":"license.renew"}""")],
        [Error(400, CodigosDeLicencia.DatosInvalidos)],
        [Error(402, CodigosDeLicencia.NoDisponiblePorLicencia, """{"capacidad":"busqueda","modulo":"Búsqueda"}""")],
        [Error(402, CodigosDeLicencia.CupoAgotado, """{"tipo":"equipos","limite":2,"en_uso":2}""")],
        [Error(401, null)],
        [Error(401, "sesion_expirada")],
        [Error(500, null)],
        [Error(503, "bitacora_no_disponible")],
        [Error(0, "sin_conexion")],
        [Error(-1, "respuesta_incompleta")],
        [Error(418, "otro_codigo")],
    ];

    [Theory]
    [MemberData(nameof(Errores))]
    public void CadaError_DiceQuePasoYQueHacer(ErrorAula error)
    {
        var m = LicenciaTexto.DeError(error);
        Limpia(m.Titulo);
        Limpia(m.Texto);
        Limpia(m.Completo);
        Assert.DoesNotContain(error.Codigo ?? "-sin-codigo-", m.Completo);
    }

    [Fact]
    public void SinError_TambienHayTexto() => Limpia(LicenciaTexto.DeError(null).Completo);

    [Fact]
    public void LosPermisos_DicenQuienPuede()
    {
        Assert.Contains("administración", LicenciaTexto.DeError(Error(403, CodigosDeLicencia.SinPermiso, """{"permiso":"license.renew"}""")).Completo);
        Assert.Contains("soporte técnico", LicenciaTexto.DeError(Error(403, CodigosDeLicencia.SinPermiso, """{"permiso":"license.read"}""")).Completo);
        Assert.Contains("coinciden 1 de las 3 piezas", LicenciaTexto.DeError(Error(409, CodigosDeLicencia.HuellaNoCoincide, """{"coinciden":1,"k":3}""")).Texto);
    }

    // ---------------------------------------------------------------------------------------------------- el texto común de los 402

    [Fact]
    public void ElModuloNoDisponible_DiceCualYQueElPermisoSeConserva()
    {
        var conModulo = LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.NoDisponiblePorLicencia, """{"capacidad":"reportes","modulo":"Reportes y exportaciones"}"""))!;
        Assert.StartsWith("«Reportes y exportaciones» no está disponible con la licencia de este equipo.", conModulo);
        Assert.Contains("Tu permiso se conserva", conModulo);
        Assert.Contains("«Licencia»", conModulo);
        Assert.StartsWith("«Búsqueda» no está disponible", LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.NoDisponiblePorLicencia, """{"capacidad":"busqueda"}"""))!);
        Assert.StartsWith("Este módulo no está disponible", LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.NoDisponiblePorLicencia))!);
        var alumno = LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.NoDisponiblePorLicencia), Audiencia.Alumno)!;
        Assert.Contains("profesor", alumno);
        Assert.DoesNotContain("licencia", alumno);
    }

    [Fact]
    public void ElCupo_DiceQueLoQueExisteSigue_YAQuienLeToca()
    {
        var equipos = LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.CupoAgotado, """{"tipo":"equipos","limite":2,"en_uso":2}"""))!;
        Assert.StartsWith("Se llegó al cupo de equipos de la licencia (2 de 2).", equipos);
        Assert.Contains("siguen funcionando", equipos);
        var usuarios = LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.CupoAgotado, """{"tipo":"usuarios","limite":4,"en_uso":4}"""))!;
        Assert.StartsWith("Se llegó al cupo de usuarios de la licencia (4 de 4).", usuarios);
        Assert.Contains("siguen entrando", usuarios);
        Assert.StartsWith("Se llegó al cupo de equipos de la licencia.", LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.CupoAgotado))!);
        var tableta = LicenciaTexto.ParaError(Error(402, CodigosDeLicencia.CupoAgotado, """{"tipo":"equipos"}"""), Audiencia.Alumno)!;
        Assert.Equal("Esta tableta todavía no puede entrar al aula. Pídele ayuda a tu profesor.", tableta);
        foreach (var t in new[] { equipos, usuarios, tableta }) Limpia(t);
    }

    [Fact]
    public void LoQueNoEsDeLicencia_NoTieneTextoComun()
    {
        Assert.Null(LicenciaTexto.ParaError(null));
        Assert.Null(LicenciaTexto.ParaError(Error(403, CodigosDeLicencia.SinPermiso)));
        Assert.Null(LicenciaTexto.ParaError(Error(402, "pago_requerido")));
    }

    // ---------------------------------------------------------------------------------------------------- los pasos, la copia, la liberación y la fecha

    [Fact]
    public void LaConfirmacion_DiceQueArchivoDeDondeYQuePasa()
    {
        var activar = LicenciaTexto.Confirmacion("licencia-a7a7a7a7-serie1.avlic", "MEMORIA (X:)", Ms(2026, 10, 20), ViasDeInstalacion.Activar, Utc);
        Assert.Equal("Vas a instalar «licencia-a7a7a7a7-serie1.avlic» (MEMORIA (X:), guardado el 20 de octubre de 2026 a las 12:00). " +
                     "Si es una licencia de AVACOM para este equipo, queda instalada al momento. Las clases no se interrumpen.", activar);
        Assert.StartsWith("Vas a renovar la licencia de este equipo con «", LicenciaTexto.Confirmacion("x.avlic", "Documentos", Ms(2026, 10, 20), ViasDeInstalacion.Renovar, Utc));
    }

    [Fact]
    public void ElResultado_DiceQueHizoElNodo()
    {
        Assert.Equal("Licencia activada", LicenciaTexto.ResultadoDeInstalacion(Fixture("activar")).Titulo);
        Assert.Equal("Licencia renovada", LicenciaTexto.ResultadoDeInstalacion(Fixture("renovar")).Titulo);
        var reactivada = LicenciaTexto.ResultadoDeInstalacion(Fixture("reactivar"));
        Assert.Equal("Licencia reactivada", reactivada.Titulo);
        Assert.StartsWith("Era el mismo archivo", reactivada.Texto);
        foreach (var f in new[] { "activar", "renovar", "reactivar" }) Limpia(LicenciaTexto.ResultadoDeInstalacion(Fixture(f)).Texto);
    }

    [Fact]
    public void LaHojaDeCustodia_ExplicaCadaArchivo_SinDatosDePersonasNiHuella()
    {
        var copia = JsonSerializer.Deserialize<CopiaDeLicencia>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", "copia.json")), Ayudas.Web)!;
        var solicitud = JsonSerializer.Deserialize<SolicitudDeLicencia>(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia", "solicitud.json")), Ayudas.Web)!;
        var hoja = LicenciaTexto.HojaDeCustodia(copia, solicitud, "licencia-a7a7a7a7-serie1 (2).avlic", "solicitud-2026-10-20-1554.avreq", Ms(2026, 10, 20), Utc);
        Assert.StartsWith("COPIA DE LA LICENCIA DE AVACOM · Aula de pruebas\r\n", hoja);
        Assert.Contains("licencia-a7a7a7a7-serie1 (2).avlic", hoja);
        Assert.Contains("solicitud-2026-10-20-1554.avreq", hoja);
        Assert.Contains(LicenciaTexto.NombreDeLaHoja, hoja);
        Assert.Contains("serie 1", hoja);
        Assert.Contains("CÓMO VOLVER A ACTIVAR LA LICENCIA", hoja);
        Assert.Contains("lugar seguro", hoja, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(copia.Sha256, hoja);
        Assert.Contains(solicitud.Sha256, hoja);
        Assert.DoesNotContain(copia.Licencia!.Id, hoja);                                // ni el identificador de la licencia
        Assert.DoesNotContain("huella", hoja, StringComparison.OrdinalIgnoreCase);       // ni la huella del equipo
        Assert.DoesNotContain(copia.ArchivoB64[..20], hoja);
        Assert.DoesNotContain("\n", hoja.Replace("\r\n", string.Empty));                  // todos los saltos son de Windows (el Bloc de notas la abre bien)
        Assert.DoesNotContain("{", hoja);
    }

    [Fact]
    public void LaFecha_SeConfirmaDiciendoQueFechaTieneElEquipo()
    {
        var t = LicenciaTexto.ConfirmacionDeFecha(Ms(2027, 3, 5), Utc);
        Assert.Contains("5 de marzo de 2027 a las 12:00", t);
        Limpia(t);
    }

    [Fact]
    public void ElUsoYLaConcurrencia()
    {
        Assert.Equal("1 de 55 equipos (2 %)", LicenciaTexto.Uso(new UsoDelCupo(1, 55, 2), "equipos"));
        Assert.Equal("3 usuarios · sin tope", LicenciaTexto.Uso(new UsoDelCupo(3, null, null), "usuarios"));
        Assert.Equal("1 usuario · sin tope", LicenciaTexto.Uso(new UsoDelCupo(1, null, null), "usuarios"));
        Assert.Equal("Sin datos", LicenciaTexto.Uso(null, "equipos"));
        Assert.Equal("Hasta 50 conexiones a la vez (100 en un pico).", LicenciaTexto.Concurrencia(50, 100));
        Assert.Equal("Hasta 50 conexiones a la vez.", LicenciaTexto.Concurrencia(50, 50));
        Assert.Equal("Sin tope de conexiones a la vez.", LicenciaTexto.Concurrencia(null, null));
        Assert.Equal("Producción", LicenciaTexto.Tipo(TiposDeLicencia.Produccion));
        Assert.Equal("Sin licencia", LicenciaTexto.Tipo(null));
    }

    [Fact]
    public void CadaFraseFija_EstaLlena()
    {
        var fijas = typeof(LicenciaTexto).GetFields(BindingFlags.Public | BindingFlags.Static).Where(f => f.IsLiteral && f.FieldType == typeof(string)).ToList();
        Assert.True(fijas.Count >= 30, $"sólo {fijas.Count} frases fijas");
        foreach (var f in fijas) Limpia((string)f.GetRawConstantValue()!);
        Limpia(LicenciaTexto.SolicitudGuardada(@"X:\solicitud.avreq"));
        Limpia(LicenciaTexto.CopiaGuardada(@"X:\"));
        Limpia(LicenciaTexto.LiberadaGuardada(@"X:\liberacion.avrel"));
    }
}
