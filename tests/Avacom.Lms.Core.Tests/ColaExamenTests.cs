using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Evaluacion;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// La cola local cifrada del examen (BR-009, BR-071, INV-005): lo que el alumno responde, los incidentes y el informe de bloqueo se guardan en el dispositivo
/// ANTES de enviarse, con una secuencia que nunca retrocede, y sólo se borran cuando el nodo acusa recibo.
/// </summary>
[Collection("estado global")]
public sealed class ColaExamenTests : IDisposable
{
    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly ProveedorDeClaveEnMemoria clave = new();

    public void Dispose()
    {
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private string Ruta => Path.Combine(carpeta, "examen.cola");
    private ColaExamen Cola(IProveedorDeClave? proveedor = null) => new(Ruta, proveedor ?? clave, () => 1_000);
    private static JsonElement R(string texto) => Ayudas.Json($$"""{"text":"{{texto}}"}""");

    [Fact]
    public void LaSecuenciaEsMonotonicaPorIntento_YNoSeReutilizaTrasReconocerOReiniciar()
    {
        var cola = Cola();
        Assert.Equal(1, cola.Guardar("i-1", "q1", R("a")));
        Assert.Equal(2, cola.Guardar("i-1", "q2", R("b")));
        Assert.Equal(1, cola.Guardar("i-2", "q1", R("c")));            // cada intento cuenta aparte
        var paquete = cola.Pendientes("i-1").Single();
        cola.Reconocer(paquete);                                         // se vació la cola de i-1…
        Assert.Equal(0, cola.CantidadPendiente("i-1"));
        Assert.Equal(3, cola.Guardar("i-1", "q1", R("d")));              // …y la secuencia sigue: nunca se reutiliza
        Assert.Equal(4, Cola().Guardar("i-1", "q1", R("e")));            // ni al reiniciar la app (otra instancia sobre el mismo archivo)
    }

    [Fact]
    public void ResponderDeNuevoLaMismaPregunta_SustituyeLoPendienteYConservaLaSecuenciaMayor()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("primera"));
        cola.Guardar("i-1", "q1", R("segunda"));
        var p = cola.Pendientes("i-1").Single();
        var unica = Assert.Single(p.Respuestas);
        Assert.Equal((2, "segunda"), (unica.Secuencia, unica.Respuesta.GetProperty("text").GetString()));
        Assert.Equal(unica.Respuesta.GetProperty("text").GetString(), cola.RespuestaPendiente("i-1", "q1")!.Respuesta.GetProperty("text").GetString());
        Assert.Null(cola.RespuestaPendiente("i-1", "q9"));
    }

    [Fact]
    public void ReconocerBorraLoEnviado_YConservaLoQueSeGuardoMientrasElEnvioViajaba()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("a"));
        var enviado = cola.Pendientes("i-1").Single();
        cola.Guardar("i-1", "q1", R("corregida"));                       // secuencia 2 mientras viajaba la 1
        cola.Guardar("i-1", "q2", R("b"));
        cola.Reconocer(enviado, PartesDeCola.Respuestas);
        var resto = cola.Pendientes("i-1").Single().Respuestas.OrderBy(r => r.PreguntaRef).ToList();
        Assert.Equal(new[] { ("q1", 2), ("q2", 3) }, resto.Select(r => (r.PreguntaRef, r.Secuencia)));
    }

    [Fact]
    public void LoGuardadoEstaCifrado_NoQuedaNadaEnClaroEnElDisco()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("la-respuesta-secreta-del-alumno"));
        cola.RegistrarIncidente("i-1", TiposDeIncidente.SalidaDeApp, new() { ["motivo"] = "detalle-privado" });
        var bytes = File.ReadAllBytes(Ruta);
        var texto = Encoding.UTF8.GetString(bytes) + Encoding.Latin1.GetString(bytes);
        Assert.DoesNotContain("la-respuesta-secreta-del-alumno", texto);
        Assert.DoesNotContain("detalle-privado", texto);
        Assert.DoesNotContain("i-1", texto);
        Assert.Equal("la-respuesta-secreta-del-alumno", Cola().RespuestaPendiente("i-1", "q1")!.Respuesta.GetProperty("text").GetString());
    }

    [Fact]
    public void SiLaClaveSeDestruye_LaColaQuedaIlegible_SeApartaYArrancaConUnEmisorNuevo()
    {
        var cola = Cola();
        var emisor = cola.EmisorId;
        cola.Guardar("i-1", "q1", R("a"));
        clave.Destruir();                                                  // BR-053
        var despues = Cola();
        Assert.NotEqual(emisor, despues.EmisorId);                         // ninguna referencia vieja puede chocar con las nuevas
        Assert.Equal(0, despues.CantidadPendiente());
        Assert.Equal(1, despues.Guardar("i-1", "q1", R("b")));
        Assert.EndsWith(".dañado", Directory.GetFiles(carpeta, "*.dañado").Single());          // se aparta, no se borra
    }

    [Fact]
    public void ElRefClienteDeUnIncidenteEsUnicoYNoSeReutiliza_AunqueSeReinicie()
    {
        var cola = Cola();
        var a = cola.RegistrarIncidente("i-1", TiposDeIncidente.SalidaDeApp);
        var b = cola.RegistrarIncidente("i-1", TiposDeIncidente.RegresoAApp);
        cola.Reconocer(cola.Pendientes("i-1").Single(), PartesDeCola.Incidentes);
        var c = Cola().RegistrarIncidente("i-1", TiposDeIncidente.TeclaBloqueada);
        Assert.Equal(3, new[] { a, b, c }.Distinct().Count());
        Assert.All(new[] { a, b, c }, r => Assert.InRange(r.Length, 3, 64));
        Assert.StartsWith(cola.EmisorId[..8], a);
    }

    [Fact]
    public void LaTabletaSoloGuardaLosIncidentesQueSonSuyos()
    {
        var cola = Cola();
        foreach (var tipo in new[] { "reactivado", "degradacion", "desconexion", "tiempo_agotado", "no_existe" })
            Assert.Throws<ArgumentException>(() => cola.RegistrarIncidente("i-1", tipo));
        Assert.Equal(0, cola.CantidadPendiente());
        Assert.All(TiposDeIncidente.DeLaTableta, tipo => cola.RegistrarIncidente("i-1", tipo));
        Assert.Equal(TiposDeIncidente.DeLaTableta.Count, cola.CantidadPendiente("i-1"));
    }

    [Fact]
    public void ElIncidenteLlevaLaHoraDelNodoYLaCrudaDelAparato()
    {
        var cola = Cola();
        cola.RegistrarIncidente("i-1", TiposDeIncidente.PantallaAdicional, new() { ["cantidad"] = 2 });
        var i = Cola().Pendientes("i-1").Single().Incidentes.Single();          // releída del disco: el detalle vuelve como JSON
        Assert.NotNull(i.OcurridoEn);
        Assert.NotNull(i.OcurridoEnTableta);
        Assert.Equal(2, ((JsonElement)i.Detalle!["cantidad"]!).GetInt32());
    }

    [Fact]
    public void ElInformeDeBloqueoQueda_SoloElUltimo_YSeReconoceSoloSiSigueSiendoElMismo()
    {
        var cola = Cola();
        var parcial = new InformeDeBloqueo(ResultadosDeBloqueo.Parcial, new CapasDeBloqueo(false, true, true, true), "falta el sistema");
        cola.PonerBloqueo("i-1", parcial);
        var enviado = cola.Pendientes("i-1").Single();
        var aplicado = new InformeDeBloqueo(ResultadosDeBloqueo.Aplicado, new CapasDeBloqueo(true, true, true, true));
        cola.PonerBloqueo("i-1", aplicado);                              // llegó otro mientras viajaba el primero
        cola.Reconocer(enviado, PartesDeCola.Bloqueo);
        Assert.Equal(aplicado, cola.Pendientes("i-1").Single().Bloqueo);   // el más nuevo NO se borra
        cola.Reconocer(cola.Pendientes("i-1").Single(), PartesDeCola.Bloqueo);
        Assert.Empty(cola.Pendientes());
    }

    [Fact]
    public void LaEntregaGuardadaSobreviveAReiniciar_YSalePorSuCuenta()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("a"));
        cola.MarcarEntrega("i-1", confirmar: true);
        var otra = Cola();
        var p = otra.Pendientes("i-1").Single();
        Assert.True(p.Entregar && p.Confirmar);
        Assert.Equal(2, p.Cantidad);
        otra.Reconocer(p);
        Assert.Empty(otra.Pendientes());
        Assert.Equal(0, otra.CantidadPendiente());
    }

    [Fact]
    public void DescartarQuitaSoloLaParteRechazada()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("a"));
        cola.RegistrarIncidente("i-1", TiposDeIncidente.SalidaDeApp);
        cola.MarcarEntrega("i-1", false);
        cola.Descartar("i-1", PartesDeCola.Entrega);
        var p = cola.Pendientes("i-1").Single();
        Assert.False(p.Entregar);
        Assert.Equal((1, 1), (p.Respuestas.Count, p.Incidentes.Count));
        cola.Descartar("i-1", PartesDeCola.Todo);
        Assert.Empty(cola.Pendientes());
    }

    [Fact]
    public void AsegurarSecuenciaMinima_ArrancaDesdeLoQueElNodoYaAcepto_SinBajarNuncaUnContador()
    {
        var cola = Cola();
        cola.AsegurarSecuenciaMinima("i-1", 7);                            // datos borrados o relevo desde otra tableta
        Assert.Equal(8, cola.Guardar("i-1", "q1", R("a")));
        cola.AsegurarSecuenciaMinima("i-1", 3);                            // un valor menor no retrocede
        Assert.Equal(9, cola.Guardar("i-1", "q2", R("b")));
        cola.AsegurarSecuenciaMinima("i-1", 0);
        Assert.Equal(10, cola.Guardar("i-1", "q3", R("c")));
    }

    [Fact]
    public void OlvidarSoloBorraElContadorDeUnIntentoSinNadaPendiente()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("a"));
        cola.Olvidar("i-1");
        Assert.Equal(1, cola.CantidadPendiente("i-1"));                   // con algo pendiente no se olvida
        Assert.Equal(2, cola.Guardar("i-1", "q2", R("b")));
        cola.Reconocer(cola.Pendientes("i-1").Single());
        cola.Olvidar("i-1");
        Assert.Equal(1, cola.Guardar("i-1", "q1", R("c")));               // ya entregado: el contador se puede soltar
    }

    [Fact]
    public void UnaRespuestaQueNoEsUnObjetoNoSeGuarda()
    {
        var cola = Cola();
        Assert.Throws<ArgumentException>(() => cola.Guardar("i-1", "q1", Ayudas.Json("[1,2]")));
        Assert.Throws<ArgumentException>(() => cola.Guardar("", "q1", R("a")));
        Assert.Throws<ArgumentException>(() => cola.Guardar("i-1", "", R("a")));
        Assert.Equal(0, cola.CantidadPendiente());
    }

    [Fact]
    public void SiElDiscoNoDeja_LaRespuestaNoExiste_ElAlumnoSeEntera_YLoPendienteAnteriorNoSePierde()
    {
        var cola = Cola();
        cola.Guardar("i-1", "q1", R("buena"));
        File.Delete(Ruta);
        Directory.Delete(carpeta, true);
        File.WriteAllText(carpeta, "ahora esto es un archivo, no una carpeta");   // el destino ya no se puede escribir
        Assert.ThrowsAny<IOException>(() => cola.Guardar("i-1", "q1", R("nueva")));
        Assert.Equal("buena", cola.RespuestaPendiente("i-1", "q1")!.Respuesta.GetProperty("text").GetString());
        File.Delete(carpeta);
        Directory.CreateDirectory(carpeta);
        Assert.Equal(3, cola.Guardar("i-1", "q2", R("c")));               // la secuencia gastada no se reutiliza
    }

    [Fact]
    public void ElCambioSeAvisa_YUnaPantallaQueFallaNoRompeElGuardado()
    {
        var cola = Cola();
        var avisos = 0;
        cola.Cambio += () => avisos++;
        cola.Guardar("i-1", "q1", R("a"));
        cola.Cambio += () => throw new InvalidOperationException("la pantalla falló");
        cola.Guardar("i-1", "q2", R("b"));                                 // no lanza
        Assert.Equal(2, cola.CantidadPendiente("i-1"));
        Assert.True(avisos >= 2);
    }
}
