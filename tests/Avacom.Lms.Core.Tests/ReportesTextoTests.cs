using System.Globalization;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Las reglas PURAS de lo que dicen las pantallas de reportes: cómo se escribe una cifra, una fecha, una duración y un tamaño; qué dice cada estado vacío y cada error; cómo se ve una nota.
/// Lo que la pantalla y el archivo exportado deben decir igual, y lo que una persona frente a una pantalla gigante entiende sin jerga.
/// </summary>
public sealed class ReportesTextoTests
{
    private static decimal D(string valor) => decimal.Parse(valor, CultureInfo.InvariantCulture);
    private static long Ms(int anio, int mes, int dia, int hora, int minuto) => new DateTimeOffset(anio, mes, dia, hora, minuto, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();
    private static readonly TimeZoneInfo Bogota = TimeZoneInfo.CreateCustomTimeZone("bogota", TimeSpan.FromHours(-5), "Bogotá", "Bogotá");

    // ------------------------------------------------------------------------------------------------ cifras

    [Theory]
    [InlineData("84.5", "84,5")]
    [InlineData("100", "100")]
    [InlineData("22.2222", "22,22")]
    [InlineData("0", "0")]
    [InlineData("0.125", "0,13")]                                   // mitad hacia arriba, como el backend
    [InlineData("0.005", "0,01")]
    [InlineData("99.999", "100")]
    [InlineData("1234.5", "1234,5")]
    [InlineData("-3.456", "-3,46")]
    public void Cifra_UsaComaDecimal_ADosDecimales_YSinCerosDeRelleno(string valor, string esperado) => Assert.Equal(esperado, FormatoDeReportes.Cifra(D(valor)));

    [Fact]
    public void UnPromedioSinValores_NoEsUnCero_EsUnaRayaEnPantallaYEnElArchivo()
    {
        Assert.Equal("—", FormatoDeReportes.Cifra(null));
        Assert.Equal("—", FormatoDeReportes.Porcentaje(null));
        Assert.Equal("0 %", FormatoDeReportes.Porcentaje(0m));
        Assert.Equal("61,11 %", FormatoDeReportes.Porcentaje(D("61.11")));
        Assert.Equal("100 %", FormatoDeReportes.Porcentaje(100m));
    }

    [Fact]
    public void Cifra_ConOtrosDecimales()
    {
        Assert.Equal("3,1416", FormatoDeReportes.Cifra(D("3.14159"), 4));
        Assert.Equal("8", FormatoDeReportes.Cifra(D("7.5"), 0));
        Assert.Equal("7", FormatoDeReportes.Cifra(7m, 0));
    }

    [Fact]
    public void UnaCifraNoDependeDeLaCulturaDelEquipo()
    {
        var anterior = CultureInfo.CurrentCulture;
        try
        {
            foreach (var cultura in new[] { "en-US", "es-CO", "de-DE", "ar-SA" })
            {
                CultureInfo.CurrentCulture = new CultureInfo(cultura);
                Assert.Equal("84,5", FormatoDeReportes.Cifra(D("84.5")));
                Assert.Equal("1234,57", FormatoDeReportes.Cifra(D("1234.567")));
            }
        }
        finally { CultureInfo.CurrentCulture = anterior; }
    }

    [Fact]
    public void DeTotal_PoneLoConcretoAntesQueElPorcentaje() => Assert.Equal("4 de 5", FormatoDeReportes.DeTotal(4, 5));

    [Theory]
    [InlineData(0, "0 alumnos")]
    [InlineData(1, "1 alumno")]
    [InlineData(7, "7 alumnos")]
    public void Plural_PoneLaCantidadConSuNombre(int n, string esperado) => Assert.Equal(esperado, FormatoDeReportes.Plural(n, "alumno", "alumnos"));

    // ------------------------------------------------------------------------------------------------ duración y tamaño

    [Theory]
    [InlineData(null, "—")]
    [InlineData(0L, "menos de 1 min")]
    [InlineData(59_999L, "menos de 1 min")]
    [InlineData(-5L, "menos de 1 min")]
    [InlineData(60_000L, "1 min")]
    [InlineData(2_700_000L, "45 min")]
    [InlineData(3_600_000L, "1 h 00 min")]
    [InlineData(7_500_000L, "2 h 05 min")]
    public void Duracion_SeDiceEnMinutosYHoras(long? ms, string esperado) => Assert.Equal(esperado, FormatoDeReportes.Duracion(ms));

    [Theory]
    [InlineData(0L, "0 B")]
    [InlineData(-9L, "0 B")]
    [InlineData(1023L, "1023 B")]
    [InlineData(1024L, "1,0 KB")]
    [InlineData(2025L, "2,0 KB")]
    [InlineData(10_240L, "10 KB")]
    [InlineData(1_363_149L, "1,3 MB")]
    [InlineData(15_032_385_536L, "14 GB")]
    [InlineData(1_099_511_627_776L, "1,0 TB")]
    public void Tamano_UsaLaUnidadQueSeEntiende(long bytes, string esperado) => Assert.Equal(esperado, FormatoDeReportes.Tamano(bytes));

    // ------------------------------------------------------------------------------------------------ fechas

    [Fact]
    public void LasFechas_SeEscribenConMesCortoEnEspanol()
    {
        var ms = Ms(2026, 10, 15, 10, 42);
        Assert.Equal("15 oct · 10:42", FormatoDeReportes.FechaCorta(ms, TimeZoneInfo.Utc));
        Assert.Equal("15 oct 2026 · 10:42", FormatoDeReportes.FechaLarga(ms, TimeZoneInfo.Utc));
        Assert.Equal("15 oct", FormatoDeReportes.Dia(ms, TimeZoneInfo.Utc));
        Assert.Equal("10:42", FormatoDeReportes.Hora(ms, TimeZoneInfo.Utc));
        Assert.Equal("05:42", FormatoDeReportes.Hora(ms, Bogota));
        Assert.Equal("1 ene · 00:05", FormatoDeReportes.FechaCorta(Ms(2027, 1, 1, 0, 5), TimeZoneInfo.Utc));
        Assert.Equal("31 dic 2026 · 23:59", FormatoDeReportes.FechaLarga(Ms(2026, 12, 31, 23, 59), TimeZoneInfo.Utc));
    }

    [Fact]
    public void LaHoraSeConvierteALaZonaDelEquipo_YPuedeCambiarElDia()
    {
        Assert.Equal("15 oct · 05:42", FormatoDeReportes.FechaCorta(Ms(2026, 10, 15, 10, 42), Bogota));
        Assert.Equal("14 oct · 21:00", FormatoDeReportes.FechaCorta(Ms(2026, 10, 15, 2, 0), Bogota));
        Assert.Equal("14 oct", FormatoDeReportes.Dia(Ms(2026, 10, 15, 2, 0), Bogota));
    }

    // ------------------------------------------------------------------------------------------------ el corte de los datos (BR-083)

    private static CorteDeDatos Corte(string estado = EstadosDeProyeccion.AlDia, long antiguedadMs = 0, IntegracionDeEquipos? integracion = null) =>
        new(Ms(2026, 10, 15, 10, 42), antiguedadMs, estado, integracion?.Incompleta ?? false,
            integracion ?? new IntegracionDeEquipos("completa", 5, 0, [], "", ""), "", "");

    private static IntegracionDeEquipos Incompleta(int sinSincronizar) =>
        new("incompleta", 7, sinSincronizar, [new MotivoDeIntegracion("conexion_perdida", sinSincronizar, "perdieron la conexión")],
            sinSincronizar == 1 ? "1 tableta sin sincronizar" : $"{sinSincronizar} tabletas sin sincronizar", "");

    [Fact]
    public void LaLineaDeCorte_SoloAnunciaLoQueFalta()
    {
        Assert.Equal("Datos al 15 oct · 10:42", FormatoDeReportes.LineaDeCorte(Corte(), TimeZoneInfo.Utc));
        Assert.Equal("Datos al 15 oct · 10:42 · 2 tabletas sin sincronizar", FormatoDeReportes.LineaDeCorte(Corte(integracion: Incompleta(2)), TimeZoneInfo.Utc));
        Assert.Equal("Datos al 15 oct · 05:42 · 1 tableta sin sincronizar", FormatoDeReportes.LineaDeCorte(Corte(integracion: Incompleta(1)), Bogota));
    }

    [Fact]
    public void LaAntiguedadDelDato_SeDiceSinNombrarEstadosInternos()
    {
        Assert.Equal("Datos al día.", FormatoDeReportes.Antiguedad(Corte()));
        Assert.Equal("Se están actualizando los reportes. Lo que ves es lo último que estaba listo.", FormatoDeReportes.Antiguedad(Corte(EstadosDeProyeccion.Reconstruyendose)));
        Assert.Equal("Faltan novedades por reflejar: estos datos tienen 5 min.", FormatoDeReportes.Antiguedad(Corte(EstadosDeProyeccion.Rezagada, 300_000)));
        Assert.DoesNotContain("rezagada", FormatoDeReportes.Antiguedad(Corte(EstadosDeProyeccion.Rezagada, 300_000)), StringComparison.OrdinalIgnoreCase);
    }

    // ------------------------------------------------------------------------------------------------ nombres de estados

    [Theory]
    [InlineData("conectado", "Presente al cerrar")]
    [InlineData("reconectando", "Sin conexión al cerrar")]
    [InlineData("salio", "Salió antes del cierre")]
    [InlineData("expulsado", "Retirado de la clase")]
    [InlineData("otro_estado", "otro_estado")]
    public void LaPresenciaDiceQueHizoLaTableta(string estado, string esperado) => Assert.Equal(esperado, FormatoDeReportes.Presencia(estado));

    [Theory]
    [InlineData("pendiente", "Pendiente")]
    [InlineData("en_curso", "En curso")]
    [InlineData("completada", "Completada")]
    public void ElEstadoDeEstudio_SeLeeEnClaro(string estado, string esperado) => Assert.Equal(esperado, FormatoDeReportes.EstadoDeEstudio(estado));

    [Theory]
    [InlineData("programada", "Programada")]
    [InlineData("activa", "En curso")]
    [InlineData("activa_fuera_de_plazo", "Fuera de plazo")]
    [InlineData("cerrada", "Cerrada")]
    [InlineData("archivada", "Archivada")]
    public void ElEstadoDeUnaAsignacion_SeLeeEnClaro(string estado, string esperado) => Assert.Equal(esperado, FormatoDeReportes.EstadoDeAsignacion(estado));

    // ------------------------------------------------------------------------------------------------ estados vacíos

    [Fact]
    public void CadaEstadoVacio_TieneSuTextoYDiceQueHacer()
    {
        var textos = new[]
        {
            EstadosVaciosDeReportes.SinGrupos, EstadosVaciosDeReportes.SinClases, EstadosVaciosDeReportes.SinClasesDelGrupo, EstadosVaciosDeReportes.SinAlumnos,
            EstadosVaciosDeReportes.SinEvaluaciones, EstadosVaciosDeReportes.SinEstudio, EstadosVaciosDeReportes.SinUso, EstadosVaciosDeReportes.SinRecientes,
            EstadosVaciosDeReportes.SinExportaciones, EstadosVaciosDeReportes.SinEquipos, EstadosVaciosDeReportes.ClaseEnCurso, EstadosVaciosDeReportes.SinActividades,
            EstadosVaciosDeReportes.SinCifras, EstadosVaciosDeReportes.Cargando, EstadosVaciosDeReportes.Aviso,
        };
        Assert.All(textos, t => Assert.False(string.IsNullOrWhiteSpace(t)));
        Assert.Equal(textos.Length, textos.Distinct().Count());                              // ninguno repite el de otro: cada pantalla dice lo suyo
        Assert.Equal("Aún no disponible", EstadosVaciosDeReportes.AunNoDisponible);
    }

    [Fact]
    public void SinAlumnosVisibles_DiceLaVerdad_EsPrivacidadONoHayAlumnos()
    {
        var aplicada = new Privacidad(true, true, 5, 2, "Este reporte tiene menos de 5 alumnos: sólo se muestran los totales.");
        var noAplicada = new Privacidad(false, false, 5, 0, "");
        Assert.Equal(aplicada.Aviso, EstadosVaciosDeReportes.SinAlumnosVisibles(aplicada));
        Assert.Equal(EstadosVaciosDeReportes.SinAlumnos, EstadosVaciosDeReportes.SinAlumnosVisibles(noAplicada));
    }

    // ------------------------------------------------------------------------------------------------ errores

    private static ErrorAula Error(int estado, string? codigo, string detalle = "") => new(estado, codigo, detalle, null, null);

    [Fact]
    public void SinConexion_SeDiceConLoQueHayQueRevisar()
    {
        var sinRed = MensajesDeReportes.De(Error(0, "sin_conexion"));
        Assert.Contains("equipo del aula", sinRed);
        Assert.Equal(sinRed, MensajesDeReportes.De(Error(0, null)));
        Assert.True(MensajesDeReportes.SinConexion(Error(0, "sin_conexion")));
        Assert.False(MensajesDeReportes.SinConexion(Error(-1, "archivo_danado")));
        Assert.False(MensajesDeReportes.SinConexion(Error(403, "sin_permiso")));
        Assert.False(MensajesDeReportes.SinConexion(null));
    }

    [Fact]
    public void SinError_OSinSaberNombrarlo_SeUsaElRespaldo()
    {
        Assert.Equal("No se pudo armar el reporte. Vuelve a intentarlo.", MensajesDeReportes.De(null));
        Assert.Equal("Otra cosa", MensajesDeReportes.De(null, "Otra cosa"));
        Assert.Equal("No se pudo armar el reporte. Vuelve a intentarlo.", MensajesDeReportes.De(Error(500, "algo_nuevo", "  ")));
        Assert.Equal("Lo que dijo el nodo", MensajesDeReportes.De(Error(409, "algo_nuevo", "Lo que dijo el nodo")));
        Assert.Equal("Explicación del propio nodo", MensajesDeReportes.De(Error(501, "capacidad_reservada", "Explicación del propio nodo")));
    }

    [Theory]
    [InlineData("sin_permiso", "Tu rol no puede ver este reporte")]
    [InlineData("fuera_de_alcance", "Ese grupo no es de los tuyos")]
    [InlineData("clase_en_curso", "Esta clase aún no termina")]
    [InlineData("sin_sesiones_finalizadas", "No hay clases finalizadas")]
    [InlineData("alumno_sin_grupo", "no pertenece a ningún grupo activo")]
    [InlineData("no_encontrado", "Ese reporte ya no existe")]
    [InlineData("no_instalado", "El nodo aún no está instalado")]
    [InlineData("sesion_activa", "Hay una clase en curso")]
    [InlineData("reconstruccion_en_curso", "Ya se están reconstruyendo")]
    [InlineData("destino_no_permitido", "memorias extraíbles")]
    [InlineData("razon_requerida", "para qué vas a guardar")]
    [InlineData("exportacion_caducada", "Genera el reporte de nuevo")]
    [InlineData("exportacion_ya_confirmada", "ya quedó guardado")]
    [InlineData("huella_distinta", "no coincide con el original")]
    [InlineData("conflicto_de_version", "Otra persona cambió esta configuración")]
    public void CadaError_DiceQuePasoYQueHacer_SinElCodigo(string codigo, string fragmento)
    {
        var mensaje = MensajesDeReportes.De(Error(409, codigo, "detalle técnico del nodo"));
        Assert.Contains(fragmento, mensaje);
        Assert.DoesNotContain(codigo, mensaje);
        Assert.DoesNotContain("detalle técnico", mensaje);
    }

    [Fact]
    public void LosErroresPropiosDelCliente_DicenLoQueLeSucedioAlArchivo()
    {
        foreach (var codigo in new[] { "archivo_danado", "respuesta_incompleta", "sin_temporal" })
            Assert.Equal($"Texto de {codigo}", MensajesDeReportes.De(Error(-1, codigo, $"Texto de {codigo}")));
    }

    [Fact]
    public void ClasificarUnError_NoMezclaPermisosConFallosDelNodo()
    {
        Assert.True(MensajesDeReportes.EsDelNodo(Error(500, null)));
        Assert.True(MensajesDeReportes.EsDelNodo(Error(503, "x")));
        Assert.False(MensajesDeReportes.EsDelNodo(Error(404, "no_encontrado")));
        Assert.False(MensajesDeReportes.EsDelNodo(Error(0, "sin_conexion")));
        Assert.False(MensajesDeReportes.EsDelNodo(null));
        Assert.True(MensajesDeReportes.SinPermiso(Error(403, "sin_permiso")));
        Assert.True(MensajesDeReportes.SinPermiso(Error(403, "fuera_de_alcance")));
        Assert.False(MensajesDeReportes.SinPermiso(Error(409, "clase_en_curso")));
        Assert.False(MensajesDeReportes.SinPermiso(null));
    }

    // ------------------------------------------------------------------------------------------------ las notas, en el modo de su nivel

    private static EvaluacionDeAlumno Evaluacion(bool presento = true, bool sinPresentar = false, string estado = EstadosDeResultado.Definitivo, string estadoSimple = EstadosSimples.Completado,
                                                 Presentacion? presentacion = null) =>
        new("a-1", "Examen", "curso", "cerrada", presento, sinPresentar, "calificado", estadoSimple, "lleno", estado, estado == EstadosDeResultado.Definitivo, presentacion);

    private static Presentacion Nota(decimal? valor, string etiqueta, string? nivel, bool provisional = false) =>
        new(85m, new ValorPresentado(valor, etiqueta, "clave"), new Desempeno(nivel, null, null), new CriterioDeAprobacion(true), null, provisional);

    [Fact]
    public void QuienNoPresento_NoTieneNota_TieneSuEstado()
    {
        Assert.Equal("Sin presentar", PresentacionDeNotas.Texto(Evaluacion(presento: false, sinPresentar: true)));
        Assert.Equal("Aún sin presentar", PresentacionDeNotas.Texto(Evaluacion(presento: false, sinPresentar: false)));
    }

    [Fact]
    public void LaNotaSePresentaComoLaEntregoElLibro_ConSuNivelDeDesempeno()
    {
        Assert.Equal("3,8 · Básico", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(null, "3,8", "Básico"))));
        Assert.Equal("4,5", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(D("4.5"), "", null))));
        Assert.Equal("A", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(null, "A", "A"))));                 // el nivel que repite la nota no se dice dos veces
        Assert.Equal("3,8 (provisional)", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(null, "3,8", null, provisional: true))));
        Assert.Equal("85 · Alto (provisional)", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(null, "85", "Alto", provisional: true))));
        Assert.Equal("3,8 · Básico", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(D("3.8"), "3.8", "Básico"))));       // el nodo manda «3.8»: se lee con la coma, como en el libro
        Assert.Equal("4,0", PresentacionDeNotas.Texto(Evaluacion(presentacion: Nota(D("4.0"), "4.0", null))));                     // y no pierde el cero que fija la escala
    }

    [Theory]
    [InlineData(EstadosSimples.NoIniciado, "Sin empezar")]
    [InlineData(EstadosSimples.EnProgreso, "En progreso")]
    [InlineData(EstadosSimples.Completado, "Completado")]
    public void EnModoSimple_NoHayNota_HayUnEstado(string estado, string esperado)
    {
        Assert.Equal(esperado, PresentacionDeNotas.EstadoSimple(estado));
        Assert.Equal(esperado, PresentacionDeNotas.Texto(Evaluacion(estadoSimple: estado)));
    }

    [Theory]
    [InlineData("lleno", "●")]
    [InlineData("medio", "◐")]
    [InlineData("vacio", "○")]
    [InlineData("otro", "○")]
    public void LosTresSimbolos_SonLosMismosQueVeElAlumno(string simbolo, string esperado) => Assert.Equal(esperado, PresentacionDeNotas.Simbolo(simbolo));

    [Theory]
    [InlineData(EstadosDeResultado.Definitivo, "Publicada")]
    [InlineData(EstadosDeResultado.Revisado, "Revisada, sin publicar")]
    [InlineData(EstadosDeResultado.Provisional, "Provisional")]
    [InlineData(EstadosDeResultado.Pendiente, "Por revisar")]
    [InlineData(EstadosDeResultado.Reabierto, "Reabierta")]
    [InlineData(EstadosDeResultado.Anulado, "Anulada")]
    public void ElEstadoDeLaNota_SeLeeEnClaro(string estado, string esperado) => Assert.Equal(esperado, PresentacionDeNotas.EstadoDeLaNota(Evaluacion(estado: estado)));

    [Fact]
    public void SinRegistro_SoloSeAnunciaSiLaPersonaPresento()
    {
        Assert.Equal(PresentacionDeNotas.SinPublicar, PresentacionDeNotas.EstadoDeLaNota(Evaluacion(estado: EstadosDeResultado.SinRegistro, presento: true)));
        Assert.Equal("", PresentacionDeNotas.EstadoDeLaNota(Evaluacion(estado: EstadosDeResultado.SinRegistro, presento: false)));
    }
}
