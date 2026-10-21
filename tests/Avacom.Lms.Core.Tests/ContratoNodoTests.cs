using System.Text.Json;
using Avacom.Lms.Core.Nodo;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/nodo/</c> (MOD-015) contra las respuestas REALES del backend, capturadas por <c>backend/nodo/tests/test_capturar_contrato.py</c> en <c>Fixtures/nodo/</c>. Un campo
/// mal escrito en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores que no cambian entre corridas (los identificadores y las horas sí cambian).
/// Y la regla de la casa (R-13): ninguna respuesta trae la carga de un evento.
/// </summary>
public sealed class ContratoNodoTests
{
    private static string Carpeta => Path.Combine(AppContext.BaseDirectory, "Fixtures", "nodo");
    private static string Texto(string nombre) => File.ReadAllText(Path.Combine(Carpeta, nombre + ".json"));

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(Texto(nombre), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    [Fact]
    public void TodasLasRespuestasCapturadas_SeLeenConSusDtos_YNingunaTraeCarga()
    {
        var jsons = Directory.GetFiles(Carpeta, "*.json").Select(Path.GetFileNameWithoutExtension).Select(n => n!).ToList();
        Assert.True(jsons.Count >= 14, $"sólo hay {jsons.Count} respuestas capturadas en {Carpeta}");
        foreach (var n in jsons)
        {
            object? leido = n switch
            {
                _ when n.StartsWith("estado", StringComparison.Ordinal) => Cargar<EstadoDelNodo>(n),
                _ when n.StartsWith("cola", StringComparison.Ordinal) => Cargar<ColaDelNodo>(n),
                _ when n.StartsWith("problemas", StringComparison.Ordinal) => Cargar<ProblemasDeCola>(n),
                "reprocesar" => Cargar<ProblemaDeCola>(n),
                "reproducir" => Cargar<ReproduccionDeConsumidor>(n),
                "health" => Cargar<SaludConNodo>(n).Nodo,
                _ when n.StartsWith("error_", StringComparison.Ordinal) => Ayudas.Json(Texto(n)).GetProperty("detail").GetString(),
                _ => throw new Xunit.Sdk.XunitException($"Hay una respuesta capturada que ninguna prueba lee: {n}.json"),
            };
            Assert.NotNull(leido);
            Assert.DoesNotContain("\"carga\"", Texto(n), StringComparison.Ordinal);
        }
    }

    [Fact]
    public void Estado_TieneLaFormaCompleta()
    {
        var e = Cargar<EstadoDelNodo>("estado");
        Assert.Contains(e.Estado, EstadosDelNodo.Todos);
        Assert.Equal(EstadosDelNodo.Operativo, e.Estado);
        Assert.False(e.Restringido);
        Assert.Empty(e.Motivos);
        Assert.NotNull(e.Base);
        Assert.True(e.Base!.TransaccionInmediata && e.Base.Integra);
        Assert.NotNull(e.Disco);
        Assert.Null(e.Disco!.LibreBytes);                                   // no medido en la base en memoria de las pruebas: null, nunca cero
        Assert.NotNull(e.Reloj);
        Assert.True(e.Reloj!.Ahora > 1_700_000_000_000);
        Assert.NotNull(e.Cola);
        Assert.Equal(2, e.Cola!.Consumidores.Count);
        Assert.Contains(e.Cola.Consumidores, c => c.Nombre == "reportes" && c.Estado == EstadosDeConsumidor.Rezagado && c.Pendientes == 5 && c.Problemas == 1);
        Assert.NotNull(e.Purga);
        Assert.False(e.Purga!.Habilitada);
        Assert.NotNull(e.Arranque);
        Assert.False(e.Arranque!.ApagadoSucioPrevio);
        Assert.False(string.IsNullOrWhiteSpace(e.Version));
    }

    [Fact]
    public void EstadoRestringido_TraeSusMotivosDelCatalogo()
    {
        var e = Cargar<EstadoDelNodo>("estado_restringido");
        Assert.Equal(EstadosDelNodo.Restringido, e.Estado);
        Assert.True(e.Restringido);
        Assert.NotEmpty(e.Motivos);
        foreach (var m in e.Motivos) Assert.Contains(m, MotivosDeRestriccion.Todos);
        Assert.Contains(MotivosDeRestriccion.TransaccionNoInmediata, e.Motivos);
        Assert.NotNull(e.Disco!.LibreBytes);
        Assert.True(e.Base!.WalBytes > 0);
    }

    [Fact]
    public void Cola_TieneConsumidoresConFuentesMarcasYEstados()
    {
        var c = Cargar<ColaDelNodo>("cola");
        Assert.Equal(2, c.Consumidores.Count);
        foreach (var consumidor in c.Consumidores)
        {
            Assert.Contains(consumidor.Estado, EstadosDeConsumidor.Todos);
            Assert.NotEmpty(consumidor.Fuentes);
            foreach (var f in consumidor.Fuentes)
            {
                Assert.Contains(f.Estado, EstadosDeConsumidor.Todos);
                Assert.True(f.UltimaSecuencia >= f.Marca);
                Assert.Equal(f.UltimaSecuencia - f.Marca, f.Pendientes);
            }
        }
        var rezagado = c.Consumidores.Single(x => x.Nombre == "reportes");
        Assert.Equal((EstadosDeConsumidor.Rezagado, 5L, 1), (rezagado.Estado, rezagado.Pendientes, rezagado.Problemas));
        Assert.Empty(c.Cortes);
        Assert.True(c.Contador >= c.UltimaSecuencia);
        var reconstruyendose = Cargar<ColaDelNodo>("cola_reconstruyendose");
        Assert.Equal(EstadosDeConsumidor.Reconstruyendose, reconstruyendose.Consumidores.Single(x => x.Nombre == "reportes").Estado);
        Assert.Equal(0, reconstruyendose.Consumidores.Single(x => x.Nombre == "reportes").Fuentes[0].Marca);
    }

    [Fact]
    public void Problemas_SonMetadatosSinCarga_YElReprocesoDevuelveElMismoProblemaResuelto()
    {
        var p = Cargar<ProblemasDeCola>("problemas");
        Assert.Equal(1, p.Total);
        var problema = p.Problemas.Single();
        Assert.Equal((EstadosDeProblema.Apartado, "reportes", "evaluacion", 3L, "evaluacion.intento_abierto.v1"), (problema.Estado, problema.Consumidor, problema.Fuente, problema.Secuencia, problema.Tipo));
        Assert.True(problema.Apartado);
        Assert.StartsWith("RuntimeError", problema.UltimoError);
        Assert.Null(problema.ResueltoEn);
        var r = Cargar<ProblemaDeCola>("reprocesar");
        Assert.Equal((EstadosDeProblema.Reprocesado, problema.Id), (r.Estado, r.Id));
        Assert.False(r.Apartado);
        Assert.NotNull(r.ResueltoEn);
        Assert.False(string.IsNullOrEmpty(r.ResueltoPor));
        Assert.NotNull(r.ServidorEn);
        Assert.Equal(0, Cargar<ProblemasDeCola>("problemas_vacio").Total);
        Assert.Equal(EstadosDeProblema.Reprocesado, Cargar<ProblemasDeCola>("problemas_reprocesados").Problemas.Single().Estado);
    }

    [Fact]
    public void Reproducir_YLosErrores_TienenSuCodigo()
    {
        var r = Cargar<ReproduccionDeConsumidor>("reproducir");
        Assert.Equal(("reportes", 1, EstadosDeConsumidor.Reconstruyendose), (r.Consumidor, r.MarcasReiniciadas, r.Estado));
        Assert.Null(r.Fuente);
        Assert.Equal(ErroresDelNodo.SinPermiso, Ayudas.Json(Texto("error_sin_permiso")).GetProperty("codigo").GetString());
        Assert.Equal(PermisosDelNodo.Reprocesar, Ayudas.Json(Texto("error_sin_permiso")).GetProperty("permiso").GetString());
        Assert.Contains("escalada", Ayudas.Json(Texto("error_sin_permiso")).GetProperty("detail").GetString());
        Assert.Equal(ErroresDelNodo.SinPermiso, Ayudas.Json(Texto("error_sin_permiso_lectura")).GetProperty("codigo").GetString());
        Assert.Equal(ErroresDelNodo.ProblemaYaResuelto, Ayudas.Json(Texto("error_problema_ya_resuelto")).GetProperty("codigo").GetString());
        Assert.Equal(ErroresDelNodo.NoEncontrado, Ayudas.Json(Texto("error_no_encontrado")).GetProperty("codigo").GetString());
        Assert.Equal(ErroresDelNodo.ConsumidorDesconocido, Ayudas.Json(Texto("error_consumidor_desconocido")).GetProperty("codigo").GetString());
    }

    [Fact]
    public void Health_TraeElCampoNodoAditivo()
    {
        var salud = Cargar<SaludConNodo>("health");
        Assert.NotNull(salud.Nodo);
        Assert.Contains(salud.Nodo!.Estado, EstadosDelNodo.Todos);
        Assert.Equal(salud.Nodo.Estado == EstadosDelNodo.Restringido, salud.Nodo.Restringido);
        Assert.NotNull(salud.Nodo.Motivos);
        Assert.Equal("ok", Ayudas.Json(Texto("health")).GetProperty("status").GetString());      // el estado de /health/ no cambia: sólo se añade el campo
    }
}
