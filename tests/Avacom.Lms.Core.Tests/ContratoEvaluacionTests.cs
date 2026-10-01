using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/evaluacion/</c> contra respuestas REALES del backend, capturadas por <c>backend/evaluacion/tests/test_capturar_contrato.py</c> en
/// <c>Fixtures/evaluacion/</c>. Un campo mal escrito en un DTO se descubre aquí y no en una tableta. Se comprueba la FORMA y los valores que no cambian entre
/// corridas (los identificadores y las horas sí cambian).
/// </summary>
public sealed class ContratoEvaluacionTests
{
    private static string Leer(string nombre) =>
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Fixtures", "evaluacion", nombre + ".json"));

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(Leer(nombre), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    [Fact]
    public void Apertura_TraeElIntentoElRelojElPlanYLasCondiciones()
    {
        var a = Cargar<AperturaDeIntento>("apertura");
        Assert.False(a.EnEsperaDeAdmision);
        Assert.False(a.Reanudado);
        Assert.Equal((EstadosIntento.EnCurso, 1, 12), (a.Intento.Estado, a.Intento.Numero, a.Intento.Total));
        Assert.Equal(12, a.PreguntasTotal);
        Assert.Equal((900, true, false), (a.Reloj!.LimiteSeg, a.Reloj.Corriendo, a.Reloj.Congelado));
        Assert.Equal(900_000, a.Reloj.RestanteMs);
        var plan = a.PlanBloqueo!;
        Assert.Equal((Niveles.Supervisado, false, false, true, true, 5), (plan.Nivel, plan.CapaSistema, plan.CapaApp, plan.RegistrarSalidas, plan.RegistrarConsultas, plan.LatidoSeg));
        Assert.Equal("Examen supervisado", a.Condiciones!.Titulo);
        Assert.Contains("Tus respuestas y el tiempo que tomaste", a.Condiciones.Registra!);
    }

    [Fact]
    public void AperturaEnEspera_LaTabletaPorDebajoDelNivelNoEmpieza()
    {
        var a = Cargar<AperturaDeIntento>("apertura_espera");
        Assert.True(a.EnEsperaDeAdmision);
        Assert.Equal(EstadosIntento.NoIniciado, a.Intento.Estado);
        Assert.Equal(("en_espera", Niveles.Controlado, Niveles.Supervisado), (a.Admision!.Estado, a.Admision.NivelExigido, a.Admision.NivelAlcanzado));
        Assert.Equal("espera_admision", a.Mensaje!.Codigo);
        Assert.Null(a.PlanBloqueo);                       // sin plan: no hay nada que bloquear mientras el profesor decide
        Assert.Equal("Examen controlado", a.Condiciones!.Titulo);
    }

    [Fact]
    public void EstadoYLatido_ComparteLaForma()
    {
        foreach (var nombre in new[] { "estado", "latido" })
        {
            var e = Cargar<EstadoDeIntento>(nombre);
            Assert.Equal(EstadosIntento.EnCurso, e.Intento.Estado);
            Assert.True(e.Reloj!.Corriendo);
            Assert.False(e.EsperaReactivacion);
            Assert.True(e.SesionActiva);
            Assert.Null(e.Mensaje);
            Assert.True(e.ServidorEn > 0);
            Assert.Equal(5, e.PlanBloqueo!.LatidoSeg);
        }
    }

    [Fact]
    public void EstadoSuspendido_EsperaAlProfesorConElRelojCongelado()
    {
        var e = Cargar<EstadoDeIntento>("estado_suspendido");
        Assert.True(EstadosIntento.Suspendido(e.Intento.Estado));
        Assert.True(e.EsperaReactivacion);
        Assert.True(e.Reloj!.Congelado);
        Assert.False(e.Reloj.Corriendo);
        Assert.Equal("suspendido", e.Mensaje!.Codigo);
        Assert.Contains("Avisa a tu profesor", e.Mensaje.Texto);
        Assert.Equal(1, e.Intento.Respondidas);           // todo lo respondido sigue guardado
    }

    [Fact]
    public void Preguntas_LlegaConLosSeisTiposYSinNingunaClave()
    {
        var texto = Leer("preguntas");
        var p = JsonSerializer.Deserialize<PreguntasDeIntento>(texto, Ayudas.Web)!;
        Assert.Equal(12, p.Preguntas.Count);
        Assert.Equal(new[] { "abierta", "completar", "opcion_multiple", "ordenar", "relacionar", "verdadero_falso" },
                     p.Preguntas.Select(x => x.Componente).Distinct().OrderBy(x => x, StringComparer.Ordinal));
        Assert.True(p.NavegacionAtras);
        Assert.All(p.Preguntas, x => Assert.False(string.IsNullOrEmpty(x.PreguntaRef)));
        using var doc = JsonDocument.Parse(texto);
        foreach (var prohibida in new[] { "isCorrect", "answer", "acceptedAnswers", "correctOrder", "es_correcta", "respuesta_correcta", "explanation" })
            Assert.False(TieneClave(doc.RootElement, prohibida), $"El examen que recibe la tableta lleva «{prohibida}».");
    }

    private static bool TieneClave(JsonElement e, string clave) => e.ValueKind switch
    {
        JsonValueKind.Object => e.EnumerateObject().Any(p => p.Name == clave || TieneClave(p.Value, clave)),
        JsonValueKind.Array => e.EnumerateArray().Any(x => TieneClave(x, clave)),
        _ => false,
    };

    [Fact]
    public void AcuseDeRespuestas_SeparaAceptadasYRechazadasConSuMotivo()
    {
        var a = Cargar<AcuseDeRespuestas>("acuse_respuestas");
        Assert.True(a.Acuse);
        Assert.Single(a.Aceptadas!);
        Assert.Empty(a.Duplicadas!);
        Assert.Equal("la pregunta no está en tu examen", a.Rechazadas!.Single().Motivo);
        Assert.Equal(1, a.Intento!.Respondidas);
        Assert.False(a.EsperaAlProfesor);
        Assert.Equal("aceptar", a.Politica);
    }

    [Fact]
    public void AcusesDeIncidentesYBloqueo()
    {
        var i = Cargar<AcuseDeIncidentes>("acuse_incidentes");
        Assert.Equal((1, 0, EstadosIntento.EnCurso), (i.Registrados, i.Duplicados, i.Estado));
        var b = Cargar<AcuseDeBloqueo>("acuse_bloqueo");
        Assert.Null(b.Incidente);
        Assert.NotNull(b.PlanBloqueo);
    }

    [Fact]
    public void Entrega_NuncaDiceCalificadoSiQuedaAlgoPorRevisar()
    {
        var e = Cargar<EntregaDeIntento>("entrega");
        Assert.Equal(EstadosIntento.EnRevision, e.Intento.Estado);   // las dos preguntas abiertas esperan al profesor
        Assert.Equal("en_revision", e.QueSigue.Codigo);
        Assert.DoesNotContain("calificado", e.QueSigue.Texto, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("alumno", e.OrigenEntrega);
        Assert.False(e.ResultadoDisponible);
        Assert.True(e.EntregadoEn > 0);
    }

    [Fact]
    public void ErrorDeConfirmacion_TraeLaListaDeLoQueFalta()
    {
        using var doc = JsonDocument.Parse(Leer("error_confirmacion"));
        Assert.Equal("confirmacion_requerida", doc.RootElement.GetProperty("codigo").GetString());
        Assert.Equal(11, doc.RootElement.GetProperty("faltan").GetArrayLength());
    }

    [Fact]
    public void Resultado_SoloConLaNotaLiberadaYConElDetalleDeCadaPregunta()
    {
        var r = Cargar<ResultadoDeIntento>("resultado");
        Assert.Equal(12, r.Detalle!.Count);
        Assert.NotNull(r.Porcentaje);
        Assert.Equal(60, r.AprobacionPct);
        Assert.NotNull(r.Aprobado);
        Assert.All(r.Detalle, d => Assert.True(d.Respondida));
    }

    [Fact]
    public void MiasYAntesala_SonLoQueSondeaStudent()
    {
        var m = Cargar<MisEvaluaciones>("mias");
        var e = Assert.Single(m.Pendientes);
        Assert.Equal((true, Niveles.Supervisado, "activa", 12), (e.PuedeComenzar, e.NivelExamen, e.Estado, e.Preguntas));
        Assert.Null(e.MiIntento);

        var a = Cargar<AntesalaDeExamen>("antesala");
        Assert.Equal((12, 900, 1, 0), (a.Asignacion.Preguntas, a.Asignacion.DuracionSeg, a.Asignacion.IntentosPermitidos, a.Asignacion.IntentosUsados));
        Assert.True(a.PuedeComenzar);
        Assert.Equal((true, Niveles.Supervisado), (a.Dispositivo!.Alcanza, a.Dispositivo.NivelExigido));
        Assert.NotEmpty(a.Condiciones.Registra!);
        Assert.Null(a.MiIntento);
    }

    [Fact]
    public void AsignacionYLista()
    {
        var a = Cargar<AsignacionDeExamen>("asignacion");
        Assert.Equal(("activa", Niveles.Controlado, Niveles.Controlado, "blando"), (a.Estado, a.NivelExamen, a.NivelDeclarado, a.Plazo));
        Assert.Equal(900_000, a.GraciaMs);
        Assert.Equal((12, 12, "fixed"), (a.PreguntasPorAlumno, a.ArmadoPrevio!.TotalBanco, a.ArmadoPrevio.Estrategia));
        Assert.True(a.Abierta);
        var lista = Cargar<ListaDeAsignaciones>("lista_asignaciones");
        Assert.Equal(2, lista.Asignaciones.Count);
        Assert.NotNull(lista.Asignaciones[0].Totales);
    }

    [Fact]
    public void Panel_FilasConLaTabletaElRelojLosIncidentesYElBloqueo()
    {
        var p = Cargar<PanelDeExamen>("panel");
        Assert.Equal((1, 1), (p.Totales.Destinatarios, p.Filas.Count));
        var f = p.Filas[0];
        Assert.Equal(EstadosIntento.EnCurso, f.Estado);
        Assert.True(f.Dispositivo!.Alcanza);
        Assert.Equal(1, f.Incidentes!.Total);
        Assert.Equal("salida_de_app", f.Incidentes.Ultimo!.Tipo);
        Assert.Equal("aplicado", f.Bloqueo!.Resultado);
        Assert.False(f.RequiereReactivacion);
        Assert.False(f.EsperaAlProfesor);
        Assert.Equal(1, f.Respondidas);
        Assert.NotNull(f.Reloj);
    }

    [Fact]
    public void ElegibilidadYAdmisiones()
    {
        var e = Cargar<ElegibilidadDeTabletas>("elegibilidad");
        Assert.Equal(Niveles.Controlado, e.NivelExamen);
        Assert.Equal((0, 1, 0), (e.Resumen.Alcanzan, e.Resumen.NoAlcanzan, e.Resumen.SinTableta));
        Assert.Equal(false, e.Filas.Single().Alcanza);
        Assert.NotNull(e.Mensaje);
        var a = Cargar<ListaDeAdmisiones>("admisiones");
        Assert.Equal("en_espera", a.Admisiones.Single().Estado);
        var d = Cargar<AdmisionPendiente>("admision_decidida");
        Assert.Equal(("admitido", Niveles.Supervisado), (d.Estado, d.NivelAdmitido));
    }

    [Fact]
    public void ExpedienteRevisionYPuntaje()
    {
        var x = Cargar<ExpedienteDeIntento>("expediente");
        Assert.Equal(EstadosIntento.EnCurso, x.Intento.Estado);
        Assert.Equal(new[] { "intento_abierto", "salida_de_app" }, x.LineaDeTiempo.Select(l => l.Tipo));
        Assert.Equal(1, x.ResumenIncidentes.Total);
        var r = Cargar<RevisionDeIntento>("revision");
        Assert.Equal(12, r.Filas.Count);
        Assert.All(r.Filas, f => Assert.True(f.Respondida));
        var p = Cargar<PuntajeAsentado>("puntaje");
        Assert.Equal(1.0, p.Puntaje);
        var pub = Cargar<IntentoPublicado>("publicado");
        Assert.Equal((EstadosIntento.Calificado, true), (pub.Estado, pub.CalificadoPor is { Length: > 0 }));
    }

    [Fact]
    public void ReactivacionYResultadosDelProfesor()
    {
        var r = Cargar<ReactivacionHecha>("reactivacion");
        Assert.Equal(EstadosIntento.EnCurso, r.Estado);
        Assert.True(r.RestanteMs > 0);
        var res = Cargar<ResultadosDeExamen>("resultados");
        Assert.False(res.DatosSuficientes);                 // con menos de tres entregas no hay promedio (CMP-043)
        Assert.Null(res.PromedioPorcentaje);
        var fila = Assert.Single(res.Filas);
        Assert.True(fila.Definitivo);
    }

    [Fact]
    public void Niveles_AlcanzaCompara_YLoQueNoSeDeclaraCuentaComoAbierto()
    {
        Assert.True(Niveles.Alcanza(Niveles.Controlado, Niveles.Supervisado));
        Assert.True(Niveles.Alcanza(Niveles.Supervisado, Niveles.Supervisado));
        Assert.False(Niveles.Alcanza(Niveles.Supervisado, Niveles.Controlado));
        Assert.False(Niveles.Alcanza(null, Niveles.Supervisado));
        Assert.False(Niveles.Alcanza("", Niveles.Controlado));
        Assert.True(Niveles.Alcanza(null, Niveles.Abierto));
        Assert.Equal(Niveles.Abierto, Niveles.Normalizar("lo-que-sea"));
    }
}
