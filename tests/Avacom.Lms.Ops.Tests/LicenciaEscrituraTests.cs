using System.Security.Cryptography;
using System.Text;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Tests;

/// <summary>
/// Cómo se guardan en una memoria USB o una carpeta la solicitud (<c>.avreq</c>), la copia de custodia (<c>.avlic</c> + <c>.avreq</c> + hoja <c>.txt</c>) y la prueba de liberación
/// (<c>.avrel</c>), con <see cref="EscrituraSegura"/>: verificado contra el SHA-256 del nodo, sin sobrescribir nunca, sin dejar jamás un archivo a medias (ni el temporal), y el conjunto todo o
/// nada aunque la memoria se retire o se llene a mitad. Contra el sistema de archivos real en una carpeta temporal, con ganchos donde una memoria real falla de verdad.
/// </summary>
public sealed class LicenciaEscrituraTests : IDisposable
{
    private readonly CarpetaTemporal _tmp = new();

    public void Dispose() => _tmp.Dispose();

    private static string Sha(byte[] datos) => Convert.ToHexStringLower(SHA256.HashData(datos));

    private static SolicitudDeLicencia Solicitud => FixturesDeLicencia.Json<SolicitudDeLicencia>("solicitud");
    private static CopiaDeLicencia Copia => FixturesDeLicencia.Json<CopiaDeLicencia>("copia");

    private void SinTemporales() => Assert.DoesNotContain(_tmp.Entradas(), n => n.EndsWith(".parte", StringComparison.OrdinalIgnoreCase) || n.StartsWith('.'));

    // ---------------------------------------------------------------------------------------------------- un archivo

    [Fact]
    public async Task LaSolicitud_SeGuardaVerificadaContraElShaDelNodo()
    {
        var r = await new EscritorDeLicencias().GuardarAsync([ArchivoParaGuardar.DelNodo(Solicitud, ".avreq")], _tmp.Ruta);
        Assert.True(r.Ok, r.Detalle);
        var ruta = Assert.Single(r.Rutas);
        Assert.Equal(Path.Combine(_tmp.Ruta, Solicitud.Nombre), ruta);
        Assert.Equal(Solicitud.Bytes(), File.ReadAllBytes(ruta));
        Assert.Equal(Solicitud.Sha256, Sha(File.ReadAllBytes(ruta)));
        Assert.Equal([Solicitud.Nombre], _tmp.Entradas());
    }

    [Fact]
    public async Task NuncaSobrescribe_ElNuevoSaleConDos()
    {
        var existente = Path.Combine(_tmp.Ruta, Solicitud.Nombre);
        await File.WriteAllTextAsync(existente, "de otra persona");
        var r = await new EscritorDeLicencias().GuardarAsync([ArchivoParaGuardar.DelNodo(Solicitud, ".avreq")], _tmp.Ruta);
        Assert.True(r.Ok, r.Detalle);
        Assert.EndsWith(" (2).avreq", r.Rutas[0]);
        Assert.Equal("de otra persona", await File.ReadAllTextAsync(existente));
        Assert.Equal(2, _tmp.Entradas().Length);
    }

    [Fact]
    public async Task UnArchivoQueNoEsLoQueDijoElNodo_NoSeGuarda_YNoQuedaNada()
    {
        var mentiroso = new ArchivoParaGuardar("solicitud.avreq", Solicitud.Bytes(), new string('a', 64));
        var r = await new EscritorDeLicencias().GuardarAsync([mentiroso], _tmp.Ruta);
        Assert.False(r.Ok);
        Assert.Equal(MotivoDeEscritura.VerificacionFallida, r.Fallo!.Motivo);
        Assert.Empty(_tmp.Entradas());

        var danado = new SolicitudDeLicencia("@@no-es-base64@@", null, "solicitud.avreq", "hardware", 3, 4, Solicitud.Sha256);      // un base64 que se dañó en el camino
        Assert.False((await new EscritorDeLicencias().GuardarAsync([ArchivoParaGuardar.DelNodo(danado, ".avreq")], _tmp.Ruta)).Ok);
        Assert.Empty(_tmp.Entradas());
    }

    [Fact]
    public async Task SiLaMemoriaSeRetiraAMitad_NoQuedaUnArchivoAMedias()
    {
        var io = new IoConGanchos { CrearNuevoHook = ruta => new EscrituraQueSeCorta(new OperacionesDeArchivoDelSistema().CrearNuevo(ruta), 100) };
        var r = await new EscritorDeLicencias(io).GuardarAsync([ArchivoParaGuardar.DelNodo(Solicitud, ".avreq")], _tmp.Ruta);
        Assert.False(r.Ok);
        Assert.Equal(MotivoDeEscritura.MedioRetirado, r.Fallo!.Motivo);
        Assert.Single(io.Creados);                                                       // sí llegó a escribir el temporal…
        Assert.Empty(_tmp.Entradas());                                                   // …y no quedó ni él ni el archivo
    }

    [Fact]
    public async Task SiLaMemoriaEstaLlena_SeDiceAntesDeEscribir()
    {
        var io = new IoConGanchos { EspacioLibreHook = _ => 10 };
        var r = await new EscritorDeLicencias(io).GuardarAsync([ArchivoParaGuardar.DelNodo(Solicitud, ".avreq")], _tmp.Ruta);
        Assert.Equal(MotivoDeEscritura.SinEspacio, r.Fallo!.Motivo);
        Assert.Empty(io.Creados);
        Assert.Empty(_tmp.Entradas());
    }

    [Fact]
    public async Task LaPruebaDeLiberacion_SeGuardaYNoPisaOtra()
    {
        var avrel = FixturesDeLicencia.Liberacion().Archivo;
        var escritor = new EscritorDeLicencias();
        var r1 = await escritor.GuardarAsync([ArchivoParaGuardar.DelNodo(avrel, ".avrel")], _tmp.Ruta);
        var r2 = await escritor.GuardarAsync([ArchivoParaGuardar.DelNodo(avrel, ".avrel")], _tmp.Ruta);
        Assert.True(r1.Ok && r2.Ok);
        Assert.Equal(Path.Combine(_tmp.Ruta, avrel.Nombre), r1.Rutas[0]);
        Assert.EndsWith(" (2).avrel", r2.Rutas[0]);
        Assert.Equal(avrel.Bytes(), File.ReadAllBytes(r2.Rutas[0]));
    }

    [Theory]
    [InlineData("solicitud-2026-10-20-1554.avreq", ".avreq", "solicitud-2026-10-20-1554.avreq")]
    [InlineData("licencia-a7a7a7a7-serie1.avlic", ".avlic", "licencia-a7a7a7a7-serie1.avlic")]
    [InlineData("liberacion-2026-10-20-1554.avrel", ".avrel", "liberacion-2026-10-20-1554.avrel")]
    [InlineData("CON.avreq", ".avreq", "reporte-CON.avreq")]                                   // un nombre que Windows reserva (el saneador común le pone su prefijo)
    [InlineData(null, ".avrel", "licencia.avrel")]
    [InlineData("solicitud.txt", ".avreq", "solicitud.avreq")]                                // la extensión es la que corresponde, no la que venga
    public void ElNombre_EsSeguroEnCualquierUnidad_YConSuExtension(string? propuesto, string extension, string esperado) =>
        Assert.Equal(esperado, EscritorDeLicencias.NombreSeguro(propuesto, extension));

    [Fact]
    public void UnNombreHostil_NoSaleDeLaCarpeta()
    {
        var nombre = EscritorDeLicencias.NombreSeguro(@"..\..\x:mal?.avrel", ".avrel");
        Assert.EndsWith(".avrel", nombre);
        Assert.False(nombre.StartsWith('.'));
        Assert.DoesNotContain(nombre, c => c is '\\' or '/' or ':' or '?' or '*');
        Assert.Equal(nombre, Path.GetFileName(nombre));
    }

    // ---------------------------------------------------------------------------------------------------- un conjunto: todo o nada

    private static IReadOnlyList<ArchivoParaGuardar> Tres() =>
    [
        ArchivoParaGuardar.DelNodo(Copia, ".avlic"),
        ArchivoParaGuardar.DelNodo(Solicitud, ".avreq"),
        new ArchivoParaGuardar(LicenciaTexto.NombreDeLaHoja, Encoding.UTF8.GetBytes("hoja")),
    ];

    [Fact]
    public async Task SiFallaElTercero_SeQuitanLosDosQueEstaOperacionDejo()
    {
        var io = new IoConGanchos
        {
            CrearNuevoHook = ruta => ruta.Contains(".txt", StringComparison.OrdinalIgnoreCase)
                ? throw new IOException("No hay espacio en el disco.", unchecked((int)0x80070070))
                : new OperacionesDeArchivoDelSistema().CrearNuevo(ruta),
        };
        File.WriteAllText(Path.Combine(_tmp.Ruta, "ya-estaba.txt"), "no se toca");
        var r = await new EscritorDeLicencias(io).GuardarAsync(Tres(), _tmp.Ruta);
        Assert.False(r.Ok);
        Assert.Equal(MotivoDeEscritura.SinEspacio, r.Fallo!.Motivo);
        Assert.Empty(r.Rutas);
        Assert.Empty(r.SinBorrar);
        Assert.Equal(["ya-estaba.txt"], _tmp.Entradas());                                // sólo lo que ya estaba
    }

    [Fact]
    public async Task SiAlgoNoSeDejaBorrar_LoDice()
    {
        var io = new IoConGanchos
        {
            CrearNuevoHook = ruta => ruta.Contains(".txt", StringComparison.OrdinalIgnoreCase)
                ? throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015))
                : new OperacionesDeArchivoDelSistema().CrearNuevo(ruta),
            BorrarHook = ruta =>
            {
                if (ruta.EndsWith(".avlic", StringComparison.OrdinalIgnoreCase)) throw new IOException("En uso por otro proceso.", unchecked((int)0x80070020));
                File.Delete(ruta);
            },
        };
        var r = await new EscritorDeLicencias(io).GuardarAsync(Tres(), _tmp.Ruta);
        Assert.False(r.Ok);
        var pendiente = Assert.Single(r.SinBorrar);
        Assert.EndsWith(".avlic", pendiente);
        Assert.Contains("sin borrar", r.Detalle);
        Assert.Equal([Path.GetFileName(pendiente)], _tmp.Entradas());                   // el .avreq sí se quitó; nunca un temporal
    }

    [Fact]
    public async Task SiLaMemoriaYaNoEstaAlQuitarLoEscrito_NoEsUnProblemaMas()
    {
        var io = new IoConGanchos
        {
            CrearNuevoHook = ruta => ruta.Contains(".txt", StringComparison.OrdinalIgnoreCase)
                ? throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015))
                : new OperacionesDeArchivoDelSistema().CrearNuevo(ruta),
            BorrarHook = ruta => throw new DirectoryNotFoundException("la memoria ya no está"),
        };
        var r = await new EscritorDeLicencias(io).GuardarAsync(Tres(), _tmp.Ruta);
        Assert.False(r.Ok);
        Assert.Equal(MotivoDeEscritura.MedioRetirado, r.Fallo!.Motivo);
        Assert.Empty(r.SinBorrar);
    }

    [Fact]
    public async Task ElAvanceDelConjunto_SubeSinRetrocederYLlegaAUno()
    {
        var valores = new List<double>();
        var r = await new EscritorDeLicencias().GuardarAsync(Tres(), _tmp.Ruta, new ProgresoSincrono(valores));
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal(3, r.Rutas.Count);
        Assert.Equal(1.0, valores[^1]);
        Assert.Equal(valores.OrderBy(v => v).ToArray(), valores.ToArray());
        SinTemporales();
    }

    private sealed class ProgresoSincrono(List<double> valores) : IProgress<double>
    {
        public void Report(double valor) { lock (valores) valores.Add(valor); }
    }

    // ---------------------------------------------------------------------------------------------------- la copia de custodia (CAP-111)

    private static long Ahora => new DateTimeOffset(2026, 10, 20, 15, 54, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();

    [Fact]
    public async Task LaCopia_GuardaLosTresArchivos_YLaHojaCitaLosNombresConQueQuedaron()
    {
        await File.WriteAllTextAsync(Path.Combine(_tmp.Ruta, Copia.Nombre), "una copia anterior");          // ya había una licencia con ese nombre
        var api = new ApiDeLicenciaFalsa();
        var r = await new CopiaDeCustodia(api, "adm-1", new EscritorDeLicencias(), () => Ahora, TimeZoneInfo.Utc).GuardarAsync(new DestinoElegido(_tmp.Ruta, TipoDeDestino.Extraible));
        Assert.True(r.Ok, r.Detalle);
        Assert.Equal("Copia guardada", r.Mensaje.Titulo);
        Assert.Equal(3, r.Rutas.Count);
        var (avlic, avreq, hoja) = (r.Rutas[0], r.Rutas[1], r.Rutas[2]);
        Assert.EndsWith(" (2).avlic", avlic);
        Assert.Equal(Copia.Bytes(), File.ReadAllBytes(avlic));
        Assert.Equal(Solicitud.Bytes(), File.ReadAllBytes(avreq));
        Assert.Equal("una copia anterior", await File.ReadAllTextAsync(Path.Combine(_tmp.Ruta, Copia.Nombre)));
        var bytes = File.ReadAllBytes(hoja);
        Assert.Equal(Encoding.UTF8.GetPreamble(), bytes[..3]);                         // con marca UTF-8: el Bloc de notas la abre bien
        var texto = Encoding.UTF8.GetString(bytes, 3, bytes.Length - 3);
        Assert.Contains(Path.GetFileName(avlic), texto);
        Assert.Contains(Path.GetFileName(avreq), texto);
        Assert.Contains("20 de octubre de 2026 a las 15:54", texto);
        Assert.Contains("\r\n", texto);
        Assert.Equal((1, 1), (api.Veces("copia"), api.Veces("solicitud")));
        Assert.Equal(4, _tmp.Entradas().Length);
        SinTemporales();
    }

    [Fact]
    public async Task SiElNodoNoDaLaCopiaOLaSolicitud_NoSeEscribeNada()
    {
        var sinCopia = new ApiDeLicenciaFalsa { Copia = () => null, ErrorAlFallar = FixturesDeLicencia.Error(404, "error_sin_licencia_para_copiar") };
        var r = await new CopiaDeCustodia(sinCopia, "adm-1", new EscritorDeLicencias(), () => Ahora).GuardarAsync(new DestinoElegido(_tmp.Ruta, TipoDeDestino.CarpetaLocal));
        Assert.False(r.Ok);
        Assert.Equal("No se pudo preparar la copia", r.Mensaje.Titulo);
        Assert.Equal(LicenciaTexto.DeError(sinCopia.UltimoError).Texto, r.Mensaje.Texto);
        Assert.Equal(0, sinCopia.Veces("solicitud"));

        var sinSolicitud = new ApiDeLicenciaFalsa { Solicitud = () => null };
        Assert.False((await new CopiaDeCustodia(sinSolicitud, "adm-1", new EscritorDeLicencias(), () => Ahora).GuardarAsync(new DestinoElegido(_tmp.Ruta, TipoDeDestino.CarpetaLocal))).Ok);
        Assert.Empty(_tmp.Entradas());
    }

    [Fact]
    public async Task SiLaCopiaFallaAMitad_NoQuedaNinguno_YSePuedeRepetir()
    {
        var io = new IoConGanchos
        {
            CrearNuevoHook = ruta => ruta.Contains(".avreq", StringComparison.OrdinalIgnoreCase)
                ? throw new IOException("El dispositivo no está listo.", unchecked((int)0x80070015))
                : new OperacionesDeArchivoDelSistema().CrearNuevo(ruta),
        };
        var r = await new CopiaDeCustodia(new ApiDeLicenciaFalsa(), "adm-1", new EscritorDeLicencias(io), () => Ahora).GuardarAsync(new DestinoElegido(_tmp.Ruta, TipoDeDestino.Extraible));
        Assert.False(r.Ok);
        Assert.Equal(("No se pudo guardar la copia", MotivoDeEscritura.MedioRetirado), (r.Mensaje.Titulo, r.Fallo!.Motivo));
        Assert.True(r.SePuedeRepetir);
        Assert.Empty(_tmp.Entradas());
    }
}
