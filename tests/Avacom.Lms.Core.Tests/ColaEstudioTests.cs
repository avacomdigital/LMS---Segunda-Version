using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// La cola cifrada del modo de estudio: secuencia monotónica por instalación que se persiste antes de devolver y no retrocede aunque la cola se
/// vacíe; emisor propio; el acuse borra; el archivo corrupto se aparta sin reutilizar secuencias.
/// </summary>
[Collection("estado global")]
public sealed class ColaEstudioTests : IDisposable
{
    private static readonly byte[] Contexto = Encoding.UTF8.GetBytes("avacom-cola-estudio");

    private readonly string carpeta = Ayudas.CarpetaTemporal();
    private readonly ProveedorDeClaveEnMemoria proveedor = new();

    public ColaEstudioTests() => RelojNodo.Olvidar();

    public void Dispose()
    {
        RelojNodo.Olvidar();
        try { Directory.Delete(carpeta, true); } catch { }
    }

    private string Archivo => Path.Combine(carpeta, "cola-estudio.avc");
    private ColaEstudio Cola() => new(Archivo, proveedor);

    private static JsonElement Carga(string bloque = "b1") => Ayudas.Json($$"""{"asignacion_id":"asig-1","bloques_vistos":["{{bloque}}"]}""");

    private static long Encolar(ColaEstudio cola, string alumno = "ana", string tipo = TiposEventoEstudio.BloqueVisto, string bloque = "b1") =>
        cola.Encolar(alumno, tipo, Carga(bloque));

    // ----------------------------------------------------------------------------------- emisor

    [Fact]
    public void ElEmisor_SeCreaUnaVezYSeGuardaEnElPropioArchivo_CifradoConLaClave()
    {
        var primera = Cola();
        Assert.Matches("^[0-9a-f]{32}$", primera.EmisorId);
        Assert.True(File.Exists(Archivo));                                           // se guarda desde el principio, aun sin eventos
        Assert.Equal(primera.EmisorId, Cola().EmisorId);                             // reabrir no lo cambia
        Assert.NotEqual(primera.EmisorId, new ColaEstudio(Path.Combine(carpeta, "otra.avc"), proveedor).EmisorId);   // otra instalación, otro emisor
        Assert.False(EstudioAyudas.Contiene(File.ReadAllBytes(Archivo), Encoding.ASCII.GetBytes(primera.EmisorId)));
    }

    // ---------------------------------------------------------------------------- la secuencia

    [Fact]
    public void LaSecuenciaEsMonotonica_SobreviveAlReinicio_YNoRetrocedeAunqueLaColaSeVacie()
    {
        var cola = Cola();
        Assert.Equal([1L, 2L, 3L], new[] { Encolar(cola), Encolar(cola), Encolar(cola) });
        var reabierta = Cola();                                                       // la app se cerró y volvió a abrirse
        Assert.Equal(4, Encolar(reabierta));
        reabierta.Reconocer([1, 2, 3, 4]);                                            // el nodo acusó todo: la cola queda vacía
        Assert.Equal(0, reabierta.CantidadPendiente());
        Assert.Equal(5, Encolar(reabierta));                                          // y la secuencia sigue: nunca se reutiliza
        var otraVez = Cola();
        otraVez.Reconocer([5]);
        Assert.Equal(6, Encolar(otraVez));
        Assert.Equal(7, Encolar(Cola()));
    }

    [Fact]
    public void LaSecuenciaSePersisteAntesDeDevolver_UnaSegundaInstanciaLaVeYSigueDespues()
    {
        var cola = Cola();
        var secuencia = Encolar(cola, bloque: "b9");
        // Sin cerrar la primera, como si la app muriera justo ahora: otra instancia lee el archivo tal como quedó.
        var recuperada = Cola();
        var pendiente = Assert.Single(recuperada.Pendientes());
        Assert.Equal(secuencia, pendiente.Evento.Secuencia);
        Assert.Equal("b9", pendiente.Evento.Carga.GetProperty("bloques_vistos")[0].GetString());
        Assert.Equal(secuencia + 1, Encolar(recuperada));
    }

    [Fact]
    public void LaColaEstaCifrada_NoQuedaNadaEnClaroEnElDisco()
    {
        var cola = Cola();
        cola.Encolar("ana-perez", TiposEventoEstudio.RespuestaEnviada, Ayudas.Json("""{"asignacion_id":"asig-1","respuesta":{"value":"MARCA-DE-LA-RESPUESTA"}}"""));
        var bytes = File.ReadAllBytes(Archivo);
        foreach (var texto in new[] { "MARCA-DE-LA-RESPUESTA", "ana-perez", "study.answer.submitted", "asig-1", "emisorId", "secuencia" })
            Assert.False(EstudioAyudas.Contiene(bytes, Encoding.UTF8.GetBytes(texto)), texto);
    }

    // ------------------------------------------------------------------------------- lo pendiente

    [Fact]
    public void LosPendientes_VanEnOrdenDeSecuencia_SePuedenFiltrarPorAlumno_YLimitar()
    {
        var cola = Cola();
        foreach (var alumno in new[] { "ana", "beto", "ana", "beto", "ana" }) Encolar(cola, alumno);

        Assert.Equal([1L, 2, 3, 4, 5], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal([1L, 3, 5], cola.Pendientes("ana").Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal([2L, 4], cola.Pendientes("beto").Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal([1L, 2], cola.Pendientes(null, 2).Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal([1L], cola.Pendientes("ana", 1).Select(e => e.Evento.Secuencia).ToArray());
        Assert.Empty(cola.Pendientes(null, 0));
        Assert.Empty(cola.Pendientes("nadie"));
        Assert.All(cola.Pendientes("beto"), e => Assert.Equal("beto", e.AlumnoId));
        Assert.Equal((5, 3, 2, 0), (cola.CantidadPendiente(), cola.CantidadPendiente("ana"), cola.CantidadPendiente("beto"), cola.CantidadPendiente("nadie")));
    }

    [Fact]
    public void ReconocerBorraSoloLoAcusado_YAvisaSoloSiCambioAlgo()
    {
        var cola = Cola();
        for (var i = 0; i < 4; i++) Encolar(cola);
        var avisos = 0;
        cola.Cambio += () => avisos++;

        cola.Reconocer([2, 4, 99]);

        Assert.Equal([1L, 3], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
        Assert.Equal(1, avisos);
        cola.Reconocer([99, 100]);                                                    // nada de eso está en la cola
        cola.Reconocer([]);
        Assert.Equal(1, avisos);
        Assert.Equal([1L, 3], Cola().Pendientes().Select(e => e.Evento.Secuencia).ToArray());   // y el borrado quedó guardado
    }

    [Fact]
    public void ElCambioSeAvisaAlEncolarYAlReconocer_YUnOyenteQueFallaNoRompeNada()
    {
        var cola = Cola();
        var avisos = 0;
        cola.Cambio += () => avisos++;
        cola.Cambio += () => throw new InvalidOperationException("la pantalla ya no existe");
        var secuencia = Encolar(cola);                                                // la secuencia ya está guardada: no lanza
        cola.Reconocer([secuencia]);
        Assert.Equal(2, avisos);
        Assert.Equal(0, cola.CantidadPendiente());
    }

    [Fact]
    public void LosEventosSeGuardanCompletos_ConSuCargaClonada()
    {
        var cola = Cola();
        using (var documento = JsonDocument.Parse("""{"asignacion_id":"asig-7","objeto_ref":"act-1","intento_numero":2,"pregunta_ref":"q3","respuesta":{"value":[1,2]},"secuencia_respuesta":5}"""))
            cola.Encolar("ana", TiposEventoEstudio.RespuestaEnviada, documento.RootElement, ocurridoEnNodoMs: 1_759_000_123_000);
        // El documento de donde salió la carga ya se liberó: la cola no puede depender de él.

        foreach (var evento in new[] { cola.Pendientes().Single(), Cola().Pendientes().Single() })
        {
            Assert.Equal("ana", evento.AlumnoId);
            Assert.Equal((1L, TiposEventoEstudio.RespuestaEnviada, 1_759_000_123_000L), (evento.Evento.Secuencia, evento.Evento.Tipo, evento.Evento.OcurridoEn));
            Assert.Equal(5, evento.Evento.Carga.GetProperty("secuencia_respuesta").GetInt32());
            Assert.Equal(2, evento.Evento.Carga.GetProperty("respuesta").GetProperty("value")[1].GetInt32());
        }
    }

    [Fact]
    public void LosArgumentosInvalidos_SeRechazan_SinGastarSecuencia()
    {
        var cola = Cola();
        Assert.Throws<ArgumentException>(() => cola.Encolar("", "tipo", Carga()));
        Assert.Throws<ArgumentException>(() => cola.Encolar("ana", " ", Carga()));
        Assert.Throws<ArgumentException>(() => cola.Encolar("ana", "tipo", default));
        Assert.Throws<ArgumentNullException>(() => cola.Reconocer(null!));
        Assert.Equal(1, Encolar(cola));
    }

    // ------------------------------------------------------------------------------- la hora

    [Fact]
    public void LaHoraSeNormalizaConElRelojDelNodo_YSeGuardaLaCrudaDelAparato()
    {
        var cola = Cola();
        RelojNodo.Aprender(RelojNodo.LocalMs + 40 * 60_000);                          // el nodo va 40 minutos adelante de esta tableta
        Encolar(cola);
        var e = cola.Pendientes().Single().Evento;
        Assert.InRange(e.OcurridoEn - e.OcurridoEnTableta!.Value, 40 * 60_000 - 50, 40 * 60_000 + 50);
        Assert.InRange(e.OcurridoEnTableta!.Value, RelojNodo.LocalMs - 5_000, RelojNodo.LocalMs + 5_000);      // la cruda es la del aparato

        cola.Encolar("ana", TiposEventoEstudio.BloqueVisto, Carga(), ocurridoEnNodoMs: 1_759_000_000_000);   // con hora ya del nodo: se respeta
        var dado = cola.Pendientes().Last().Evento;
        Assert.Equal(1_759_000_000_000, dado.OcurridoEn);
        Assert.Equal(1_759_000_000_000 - RelojNodo.DesfaseMs, dado.OcurridoEnTableta);   // y la cruda sigue diciendo lo mismo que la normalizada
    }

    [Fact]
    public void SinHaberOidoAlNodo_LaHoraNormalizadaEsLaLocal()
    {
        var cola = Cola();
        Encolar(cola);
        var e = cola.Pendientes().Single().Evento;
        Assert.InRange(e.OcurridoEn - e.OcurridoEnTableta!.Value, -50, 50);
    }

    // ---------------------------------------------------------------------- corrupción y clave

    [Fact]
    public void UnArchivoCorrupto_SeApartaSinLanzar_YLaColaEmpiezaDeCeroConUnEmisorNuevo()
    {
        var vieja = Cola();
        Encolar(vieja);
        Encolar(vieja);
        var emisorViejo = vieja.EmisorId;
        var bytes = File.ReadAllBytes(Archivo);
        bytes[^5] ^= 0x40;
        File.WriteAllBytes(Archivo, bytes);

        var nueva = Cola();

        Assert.True(File.Exists(Archivo + ".dañado"));
        Assert.Empty(nueva.Pendientes());
        Assert.NotEqual(emisorViejo, nueva.EmisorId);                                 // sin el contador viejo, un emisor nuevo garantiza que no choque con las secuencias anteriores
        Assert.Equal(1, Encolar(nueva));
        Assert.Equal(nueva.EmisorId, Cola().EmisorId);
        Assert.Single(Cola().Pendientes());
    }

    [Fact]
    public void UnArchivoQueNoEsUnDocumento_TambienSeAparta()
    {
        File.WriteAllText(Archivo, "{esto no es json ni está cifrado");
        var cola = Cola();
        Assert.True(File.Exists(Archivo + ".dañado"));
        Assert.Empty(cola.Pendientes());
        Assert.Equal(1, Encolar(cola));
    }

    [Fact]
    public void LaClaveDestruida_DejaLaColaIlegible_ElEmisorCambia()
    {
        var vieja = Cola();
        Encolar(vieja);
        var emisorViejo = vieja.EmisorId;
        proveedor.Destruir();                                                         // BR-053

        var nueva = Cola();
        Assert.Empty(nueva.Pendientes());
        Assert.NotEqual(emisorViejo, nueva.EmisorId);
        Assert.True(File.Exists(Archivo + ".dañado"));
        Assert.Equal(1, Encolar(nueva));
    }

    [Fact]
    public void UnEventoMalformado_NoTumbaALosDemas_YSeConservanElEmisorYElContador()
    {
        var estado = """
            {"emisorId":"emisor-de-antes","ultimaSecuencia":10,"eventos":[
              {"alumnoId":"ana","secuencia":7,"tipo":"study.block.viewed","ocurridoEn":5,"ocurridoEnTableta":4,"carga":{"asignacion_id":"a"}},
              {"alumnoId":"ana","secuencia":"malo","tipo":"study.block.viewed","ocurridoEn":5,"carga":{}},
              {"alumnoId":"","secuencia":8,"tipo":"x","ocurridoEn":5,"carga":{}},
              {"alumnoId":"beto","secuencia":9,"tipo":"study.lesson.completed","ocurridoEn":6,"carga":{"asignacion_id":"a"}}]}
            """;
        File.WriteAllBytes(Archivo, DocumentoCifrado.Sellar(Encoding.UTF8.GetBytes(estado), proveedor.Obtener(), Contexto));

        var cola = Cola();

        Assert.Equal("emisor-de-antes", cola.EmisorId);
        Assert.Equal([7L, 9], cola.Pendientes().Select(e => e.Evento.Secuencia).ToArray());
        Assert.False(File.Exists(Archivo + ".dañado"));                               // no hubo que apartar nada: sólo se descartó lo malformado
        Assert.Equal(11, Encolar(cola));                                              // el contador de antes (10) manda, no el mayor evento que quedó (9)
        Assert.Equal([7L, 9, 11], Cola().Pendientes().Select(e => e.Evento.Secuencia).ToArray());   // y quedó normalizado en el disco
    }

    [Fact]
    public void SiElContadorNoSeLee_LaSecuenciaSigueDesdeLoMasAltoQueQuedo()
    {
        var estado = """{"emisorId":"e1","eventos":[{"alumnoId":"ana","secuencia":5,"tipo":"t","ocurridoEn":1,"carga":{}}]}""";
        File.WriteAllBytes(Archivo, DocumentoCifrado.Sellar(Encoding.UTF8.GetBytes(estado), proveedor.Obtener(), Contexto));
        var cola = Cola();
        Assert.Equal("e1", cola.EmisorId);
        Assert.Equal(6, Encolar(cola));
    }

    // ---------------------------------------------------------------- fallos de escritura y hilos

    [Fact]
    public void SiNoSePuedeGuardar_ElEventoNoExiste_YLaSecuenciaGastadaNoSeReutiliza()
    {
        var cola = Cola();
        File.Delete(Archivo);
        Directory.CreateDirectory(Archivo);                                           // el destino del reemplazo pasa a ser una carpeta: guardar es imposible
        Assert.ThrowsAny<Exception>(() => Encolar(cola));                             // el llamador se entera de que NO quedó guardado
        Assert.Equal(0, cola.CantidadPendiente());

        Directory.Delete(Archivo);
        Assert.Equal(2, Encolar(cola));                                               // la 1 se gastó: no se vuelve a entregar
        Assert.Equal(2, Cola().Pendientes().Single().Evento.Secuencia);
    }

    [Fact]
    public async Task VariosHilosEncolando_RecibenSecuenciasDistintasYConsecutivas()
    {
        var cola = Cola();
        var secuencias = await Task.WhenAll(Enumerable.Range(0, 8).Select(h => Task.Run(() =>
            Enumerable.Range(0, 12).Select(i => Encolar(cola, "ana", bloque: $"h{h}-{i}")).ToArray())));
        var todas = secuencias.SelectMany(s => s).OrderBy(s => s).ToArray();
        Assert.Equal(Enumerable.Range(1, 96).Select(i => (long)i).ToArray(), todas);
        Assert.Equal(96, Cola().CantidadPendiente());
    }
}
