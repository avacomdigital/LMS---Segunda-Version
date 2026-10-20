using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Licencia;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs de <c>/api/licencia/</c> (MOD-018) contra las respuestas REALES del backend, capturadas por <c>backend/licenciamiento/tests/test_capturar_contrato.py</c> en
/// <c>Fixtures/licencia/</c>, y contra los archivos de verdad que el nodo produce (una licencia binaria, la misma en texto, una alterada, una solicitud y una liberación). Un campo mal escrito
/// en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores que no cambian entre corridas (los identificadores, los hashes y las horas sí cambian).
/// </summary>
public sealed class ContratoLicenciaTests
{
    private static string Carpeta => Path.Combine(AppContext.BaseDirectory, "Fixtures", "licencia");
    private static string Ruta(string archivo) => Path.Combine(Carpeta, archivo);

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(File.ReadAllText(Ruta(nombre + ".json")), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    private static EstadoLicencia Estado(string nombre) => Cargar<EstadoLicencia>(nombre);

    private static JsonElement Json(string nombre) => Ayudas.Json(File.ReadAllText(Ruta(nombre + ".json")));

    private static string Sha(byte[] datos) => Convert.ToHexStringLower(SHA256.HashData(datos));

    // ---------------------------------------------------------------------------------------------------- que no quede ninguna respuesta sin leer

    [Fact]
    public void TodasLasRespuestasCapturadas_SeLeenConSusDtos()
    {
        var jsons = Directory.GetFiles(Carpeta, "*.json").Select(Path.GetFileNameWithoutExtension).ToList();
        Assert.True(jsons.Count >= 40, $"sólo hay {jsons.Count} respuestas capturadas en {Carpeta}");
        foreach (var nombre in jsons)
        {
            var n = nombre!;
            object? leido = n switch
            {
                _ when n.StartsWith("estado_", StringComparison.Ordinal) || n is "activar" or "renovar" or "reactivar" or "reloj_confirmar" => Estado(n),
                _ when n.StartsWith("consumo", StringComparison.Ordinal) => Cargar<ConsumoDeLicencia>(n),
                _ when n.StartsWith("capacidades", StringComparison.Ordinal) => Cargar<CapacidadesDelNodo>(n),
                _ when n.StartsWith("solicitud", StringComparison.Ordinal) => Cargar<SolicitudDeLicencia>(n),
                "copia" => Cargar<CopiaDeLicencia>(n),
                "liberar" => new ResultadoDeLiberacion(Cargar<LiberacionDeLicencia>(n), Estado(n)),
                _ when n.StartsWith("error_", StringComparison.Ordinal) => Json(n).GetProperty("detail").GetString(),
                _ => throw new Xunit.Sdk.XunitException($"Hay una respuesta capturada que ninguna prueba lee: {n}.json"),
            };
            Assert.NotNull(leido);
            if (leido is EstadoLicencia e)
            {
                Assert.Contains(e.Estado, EstadosDeLicencia.Todos);
                Assert.Contains(e.Motivo, MotivosDeEstado.Todos);
                Assert.Equal(ModosDeLicencia.Firmada, e.Modo);
                Assert.NotNull(e.Vigencia);
                Assert.NotNull(e.Huella);
                Assert.NotNull(e.Capacidades);
                Assert.True(e.Ahora > 1_700_000_000_000 && e.CalculadaEn > 1_700_000_000_000);
                Assert.All(e.AvisosActivos, a => Assert.Contains(a.Codigo, AvisosDeLicencia.Todos));
                Assert.All(e.BanderasActivas, b => Assert.Contains(b, BanderasDeLicencia.Todas));
                Assert.All(e.Habilitadas.Concat(e.NoDisponibles), c => Assert.Contains(c, CapacidadesLicenciables.Todas));
            }
        }
    }

    // ---------------------------------------------------------------------------------------------------- estado/

    [Fact]
    public void SinLicencia_EsLaEvaluacion_ConSusTreintaDias_YElAvisoDesdeElPrimerDia()
    {
        var e = Estado("estado_sin_licencia");
        Assert.Equal((EstadosDeLicencia.SinLicencia, MotivosDeEstado.Evaluacion, "pruebas"), (e.Estado, e.Motivo, e.Entorno));
        Assert.Null(e.Licencia);
        Assert.Null(e.Tipo);
        Assert.False(e.TieneLicencia);
        Assert.False(e.Restringe);
        Assert.Equal(30, e.Vigencia!.DiasRestantes);
        Assert.Null(e.Vigencia.Desde);
        Assert.Null(e.Vigencia.Vence);
        Assert.NotNull(e.Vigencia.Hasta);
        var aviso = Assert.Single(e.AvisosActivos);
        Assert.Equal((AvisosDeLicencia.Evaluacion, 30, false), (aviso.Codigo, aviso.Dias, aviso.Urgente));
        Assert.Equal((NivelesDeHuella.Hardware, (bool?)null, false), (e.Huella!.Nivel, e.Huella.Coincide, e.Huella.Parcial));
        Assert.Equal((100, 3000, 50, 100), (e.Limites!.Equipos, e.Limites.Usuarios, e.Limites.ConcurrentesNormal, e.Limites.ConcurrentesPico));
        Assert.Equal(CapacidadesLicenciables.Todas.OrderBy(x => x), e.Habilitadas.OrderBy(x => x));
        Assert.Empty(e.NoDisponibles);
        Assert.Equal((1, 3), (e.Consumo!.Equipos, e.Consumo.Usuarios));
    }

    [Fact]
    public void Activa_TraeLaLicenciaSinFirmaNiHuellas()
    {
        var e = Estado("estado_activa");
        Assert.Equal((EstadosDeLicencia.Activa, MotivosDeEstado.Vigente, TiposDeLicencia.Produccion), (e.Estado, e.Motivo, e.Tipo));
        var lic = e.Licencia!;
        Assert.Equal(("a7a7a7a7-0001-4000-8000-000000000001", 1, "Aula de pruebas", "dev-1"), (lic.Id, lic.Serie, lic.Aula, lic.Kid));
        Assert.Equal((TiposDeLicencia.Produccion, 30, false, 0), (lic.Tipo, lic.GraciaDias, lic.LiberacionPendiente, lic.LiberacionDias));
        Assert.True(lic.Todas);
        Assert.Equal(12, lic.Archivo!.Length);                                         // sólo el comienzo del SHA-256 del archivo
        Assert.True(lic.Desde < lic.Vence && lic.Emitida < lic.Desde);
        Assert.Equal((55, 1200, 50, 100), (lic.Limites!.Equipos, lic.Limites.Usuarios, lic.Limites.ConcurrentesNormal, lic.Limites.ConcurrentesPico));
        Assert.Equal((lic.Desde, lic.Vence, 30), (e.Vigencia!.Desde!.Value, e.Vigencia.Vence!.Value, e.Vigencia.GraciaDias!.Value));
        Assert.Equal(335, e.Vigencia.DiasRestantes);
        Assert.Equal((true, 4, 4, 3, false), (e.Huella!.Coincide!.Value, e.Huella.Coinciden!.Value, e.Huella.Factores!.Value, e.Huella.K!.Value, e.Huella.Parcial));
        Assert.Empty(e.AvisosActivos);
        Assert.Empty(e.BanderasActivas);
        Assert.Null(e.Accion);
        // Ninguna clave con la firma ni con hashes de la huella (el valor «firmada» del modo no cuenta: se miran los NOMBRES de las claves).
        var claves = new List<string>();
        void Recorrer(JsonElement el)
        {
            if (el.ValueKind == JsonValueKind.Object)
                foreach (var p in el.EnumerateObject()) { claves.Add(p.Name); Recorrer(p.Value); }
            else if (el.ValueKind == JsonValueKind.Array)
                foreach (var x in el.EnumerateArray()) Recorrer(x);
        }
        Recorrer(Json("estado_activa"));
        Assert.DoesNotContain(claves, c => c.Contains("firma") || c.Contains("hash") || c.Contains("clave"));
        Assert.Equal(JsonValueKind.Number, Json("estado_activa").GetProperty("huella").GetProperty("factores").ValueKind);   // sólo cuántos factores, nunca cuáles
    }

    [Theory]
    [InlineData("activar", AccionesDeInstalacion.Activada, EstadosDeLicencia.Activa, 1)]
    [InlineData("renovar", AccionesDeInstalacion.Renovada, EstadosDeLicencia.Activa, 2)]
    [InlineData("reactivar", AccionesDeInstalacion.Reactivada, EstadosDeLicencia.Reactivada, 2)]
    public void InstalarUnArchivo_DevuelveLaAccionYElEstadoNuevo(string fixture, string accion, string estado, int serie)
    {
        var e = Estado(fixture);
        Assert.Equal((accion, estado, serie), (e.Accion, e.Estado, e.Licencia!.Serie));
        Assert.Contains(e.Accion, AccionesDeInstalacion.Todas);
    }

    [Fact]
    public void LaRenovacion_AlargaLaVigencia()
    {
        Assert.Equal(700, Estado("renovar").Vigencia!.DiasRestantes);
        Assert.Equal(MotivosDeEstado.Reactivada, Estado("reactivar").Motivo);
    }

    [Fact]
    public void EnGracia_YDegradada_DicenCuantoQuedaYQueSeApago()
    {
        var gracia = Estado("estado_gracia");
        Assert.Equal((EstadosDeLicencia.EnGracia, MotivosDeEstado.Vencida, false), (gracia.Estado, gracia.Motivo, gracia.Restringe));
        Assert.Equal(22, gracia.Vigencia!.DiasRestantes);
        var a = Assert.Single(gracia.AvisosActivos);
        Assert.Equal((AvisosDeLicencia.Gracia, 22, MotivosDeEstado.Vencida), (a.Codigo, a.Dias, a.Motivo));
        Assert.Equal(4, gracia.Habilitadas.Count);

        var degradada = Estado("estado_degradada");
        Assert.Equal((EstadosDeLicencia.Degradada, MotivosDeEstado.Vencida, true), (degradada.Estado, degradada.Motivo, degradada.Restringe));
        Assert.Equal(0, degradada.Vigencia!.DiasRestantes);
        var d = Assert.Single(degradada.AvisosActivos);
        Assert.Equal((AvisosDeLicencia.Degradada, MotivosDeEstado.Vencida), (d.Codigo, d.Motivo));
        Assert.Empty(degradada.Habilitadas);
        Assert.Equal(4, degradada.NoDisponibles.Count);
        Assert.NotNull(degradada.Licencia);                                            // la licencia vencida sigue ahí: renovarla es la salida
    }

    [Fact]
    public void LaHuella_DistintaYParcial()
    {
        var distinta = Estado("estado_huella_distinta");
        Assert.Equal((EstadosDeLicencia.EnGracia, MotivosDeEstado.HuellaDistinta), (distinta.Estado, distinta.Motivo));
        Assert.Equal((false, 1, 3), (distinta.Huella!.Coincide!.Value, distinta.Huella.Coinciden!.Value, distinta.Huella.K!.Value));
        Assert.Equal((AvisosDeLicencia.Gracia, MotivosDeEstado.HuellaDistinta, 30), (distinta.AvisosActivos[0].Codigo, distinta.AvisosActivos[0].Motivo, distinta.AvisosActivos[0].Dias));

        var parcial = Estado("estado_huella_parcial");
        Assert.Equal(EstadosDeLicencia.Activa, parcial.Estado);
        Assert.True(parcial.Tiene(BanderasDeLicencia.HuellaParcial));
        Assert.Equal((true, true, 3), (parcial.Huella!.Coincide!.Value, parcial.Huella.Parcial, parcial.Huella.Coinciden!.Value));
        Assert.Equal(AvisosDeLicencia.HuellaParcial, Assert.Single(parcial.AvisosActivos).Codigo);
    }

    [Fact]
    public void ElReloj_RetrocesoYSalto_YLaConfirmacionApagaLaBandera()
    {
        Assert.Empty(Estado("estado_reloj_retroceso").BanderasActivas);
        var salto = Estado("estado_reloj_salto");
        Assert.True(salto.Tiene(BanderasDeLicencia.RelojSospechoso));
        Assert.Equal(AvisosDeLicencia.RelojSospechoso, Assert.Single(salto.AvisosActivos).Codigo);
        var confirmada = Estado("reloj_confirmar");
        Assert.Empty(confirmada.BanderasActivas);
        Assert.Empty(confirmada.AvisosActivos);
        Assert.Equal(EstadosDeLicencia.Activa, confirmada.Estado);
    }

    [Fact]
    public void LiberacionPendiente_TraeSusDias()
    {
        var e = Estado("estado_liberacion_pendiente");
        Assert.Equal((EstadosDeLicencia.LiberacionPendiente, MotivosDeEstado.LiberacionPendiente), (e.Estado, e.Motivo));
        Assert.Equal((true, 14), (e.Licencia!.LiberacionPendiente, e.Licencia.LiberacionDias));
        Assert.Equal((AvisosDeLicencia.LiberacionPendiente, 14), (e.AvisosActivos[0].Codigo, e.AvisosActivos[0].Dias));
    }

    [Fact]
    public void PorVencer_YElCupo()
    {
        var porVencer = Estado("estado_por_vencer_y_cupo");
        var a = Assert.Single(porVencer.AvisosActivos);
        Assert.Equal((AvisosDeLicencia.PorVencer, 12, 14), (a.Codigo, a.Dias, a.Umbral));
        Assert.Equal((2, 4), (porVencer.Limites!.Equipos, porVencer.Limites.Usuarios));

        Assert.Empty(Estado("estado_cupo_casi_lleno").AvisosActivos);                  // 1 de 2 y 3 de 4: por debajo del 90 %
        var lleno = Estado("estado_cupo_lleno");
        Assert.Equal(2, lleno.AvisosActivos.Count);
        Assert.Equal(("equipos", 2, 2, 100), (lleno.AvisosActivos[0].Tipo, lleno.AvisosActivos[0].EnUso, lleno.AvisosActivos[0].Limite, lleno.AvisosActivos[0].Porcentaje));
        Assert.Equal(("usuarios", 4, 4, 100), (lleno.AvisosActivos[1].Tipo, lleno.AvisosActivos[1].EnUso, lleno.AvisosActivos[1].Limite, lleno.AvisosActivos[1].Porcentaje));
        Assert.Equal((2, 4), (lleno.Consumo!.Equipos, lleno.Consumo.Usuarios));
    }

    // ---------------------------------------------------------------------------------------------------- consumo/ y capacidades/

    [Fact]
    public void Consumo_TraeLasDosFilasYLaConcurrencia()
    {
        var c = Cargar<ConsumoDeLicencia>("consumo");
        Assert.Equal((1, 100, 1), (c.Equipos!.EnUso, c.Equipos.Limite, c.Equipos.Porcentaje));
        Assert.Equal((3, 3000, 0), (c.Usuarios!.EnUso, c.Usuarios.Limite, c.Usuarios.Porcentaje));
        Assert.Equal((50, 100), (c.Concurrentes!.Normal, c.Concurrentes.Pico));
        Assert.True(c.CalculadoEn > 0);
        var limitado = Cargar<ConsumoDeLicencia>("consumo_con_limites");
        Assert.Equal((1, 2, 50), (limitado.Equipos!.EnUso, limitado.Equipos.Limite, limitado.Equipos.Porcentaje));
        Assert.Equal((3, 4, 75), (limitado.Usuarios!.EnUso, limitado.Usuarios.Limite, limitado.Usuarios.Porcentaje));
        Assert.False(limitado.Equipos.SinTope);
    }

    [Fact]
    public void Capacidades_NoTraenNadaDeLaLicencia()
    {
        var sana = Cargar<CapacidadesDelNodo>("capacidades");
        Assert.Equal((EstadosDeLicencia.SinLicencia, false, 4), (sana.Estado, sana.Restringe, sana.Habilitadas!.Count));
        var degradada = Cargar<CapacidadesDelNodo>("capacidades_degradada");
        Assert.Equal((EstadosDeLicencia.Degradada, true), (degradada.Estado, degradada.Restringe));
        Assert.Empty(degradada.Habilitadas!);
        Assert.Equal(CapacidadesLicenciables.Todas.OrderBy(x => x), degradada.NoDisponibles!.OrderBy(x => x));
        var crudo = File.ReadAllText(Ruta("capacidades_degradada.json"));
        Assert.DoesNotContain("licencia", crudo);
        Assert.DoesNotContain("vence", crudo);
    }

    // ---------------------------------------------------------------------------------------------------- los archivos que entrega el nodo

    [Fact]
    public void LaSolicitud_EsUnAvreqConSuShaYSuNivel()
    {
        var s = Cargar<SolicitudDeLicencia>("solicitud");
        Assert.Equal((NivelesDeHuella.Hardware, 3, 4), (s.Nivel, s.K, s.Factores));
        Assert.EndsWith(".avreq", s.Nombre);
        Assert.StartsWith("AVQ1.", s.Texto);
        var bytes = s.Bytes();
        Assert.Equal("AVRQ", Encoding.ASCII.GetString(bytes, 0, 4));
        Assert.Equal(s.Sha256, Sha(bytes));
        Assert.Equal(FormaDeLicencia.Desconocida, MarcaDeLicencia.Reconocer(bytes));          // una solicitud NO es una licencia: no sale en las tarjetas

        var instalacion = Cargar<SolicitudDeLicencia>("solicitud_instalacion");
        Assert.Equal((NivelesDeHuella.Instalacion, 1, 1), (instalacion.Nivel, instalacion.K, instalacion.Factores));
    }

    [Fact]
    public void LaCopia_EsElAvlicVigente()
    {
        var c = Cargar<CopiaDeLicencia>("copia");
        Assert.Equal("licencia-a7a7a7a7-serie1.avlic", c.Nombre);
        Assert.StartsWith("AVL1.", c.Texto);
        var bytes = c.Bytes();
        Assert.Equal(FormaDeLicencia.Binaria, MarcaDeLicencia.Reconocer(bytes));
        Assert.Equal(c.Sha256, Sha(bytes));
        Assert.Equal((1, "Aula de pruebas"), (c.Licencia!.Serie, c.Licencia.Aula));
        Assert.StartsWith(c.Licencia.Archivo!, c.Sha256);                                 // el «archivo» del resumen es el comienzo del mismo SHA-256
    }

    [Fact]
    public void LaLiberacion_TraeElAvrelYElEstadoNuevo()
    {
        var archivo = Cargar<LiberacionDeLicencia>("liberar");
        var estado = Estado("liberar");
        Assert.EndsWith(".avrel", archivo.Nombre);
        Assert.StartsWith("AVR1.", archivo.Texto);
        Assert.Equal(("a7a7a7a7-0001-4000-8000-000000000001", 2), (archivo.LicenciaId, archivo.Serie));
        var bytes = archivo.Bytes();
        Assert.Equal("AVRL", Encoding.ASCII.GetString(bytes, 0, 4));
        Assert.Equal(archivo.Sha256, Sha(bytes));
        Assert.Equal((EstadosDeLicencia.SinLicencia, MotivosDeEstado.Evaluacion), (estado.Estado, estado.Motivo));
        Assert.Null(estado.Licencia);
        Assert.Equal(EstadosDeLicencia.SinLicencia, Estado("estado_tras_liberar").Estado);
    }

    [Fact]
    public void LosArchivosDeVerdad_SeReconocenPorSuMarca_SinInterpretarlos()
    {
        var binaria = File.ReadAllBytes(Ruta("ejemplo.avlic"));
        var texto = File.ReadAllBytes(Ruta("ejemplo-texto.avlic"));
        var alterada = File.ReadAllBytes(Ruta("ejemplo-alterada.avlic"));
        Assert.Equal(FormaDeLicencia.Binaria, MarcaDeLicencia.Reconocer(binaria));
        Assert.Equal(FormaDeLicencia.Texto, MarcaDeLicencia.Reconocer(texto));
        Assert.Equal(FormaDeLicencia.Binaria, MarcaDeLicencia.Reconocer(alterada));          // la alteración está dentro: la marca no la delata, la firma sí (en el nodo)
        Assert.Equal(binaria.Length, alterada.Length);
        Assert.NotEqual(binaria, alterada);
        Assert.Equal(FormaDeLicencia.Desconocida, MarcaDeLicencia.Reconocer(File.ReadAllBytes(Ruta("ejemplo.avreq"))));
        Assert.Equal(FormaDeLicencia.Desconocida, MarcaDeLicencia.Reconocer(File.ReadAllBytes(Ruta("ejemplo.avrel"))));
        Assert.All(new[] { binaria, texto, alterada }, b => Assert.InRange(b.Length, 5, MarcaDeLicencia.TamanoMaximo));

        // La forma de texto es la misma licencia: base64url sin relleno de los bytes binarios.
        var leido = MarcaDeLicencia.TextoDe(texto)!;
        var cuerpo = leido["AVL1.".Length..].Replace('-', '+').Replace('_', '/');
        cuerpo += new string('=', (4 - cuerpo.Length % 4) % 4);
        Assert.Equal(binaria, Convert.FromBase64String(cuerpo));
    }

    [Fact]
    public void LaFormaDeTexto_AceptaLaMarcaUtf8YLosSaltosDeLinea_YRechazaLoQueNoEsAscii()
    {
        var texto = File.ReadAllText(Ruta("ejemplo-texto.avlic")).Trim();
        var conMarca = new byte[] { 0xEF, 0xBB, 0xBF }.Concat(Encoding.ASCII.GetBytes(texto + "\r\n")).ToArray();
        Assert.Equal(FormaDeLicencia.Texto, MarcaDeLicencia.Reconocer(conMarca));
        Assert.Equal(texto, MarcaDeLicencia.TextoDe(conMarca));
        Assert.Null(MarcaDeLicencia.TextoDe(Encoding.UTF8.GetBytes("AVL1.ñandú")));
        Assert.Null(MarcaDeLicencia.TextoDe(File.ReadAllBytes(Ruta("ejemplo.avlic"))));
        Assert.Equal(FormaDeLicencia.Desconocida, MarcaDeLicencia.Reconocer("AVL"u8));
        Assert.Equal(FormaDeLicencia.Desconocida, MarcaDeLicencia.Reconocer([]));
    }

    // ---------------------------------------------------------------------------------------------------- los errores

    [Theory]
    [InlineData("error_firma_invalida", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.FirmaInvalida)]
    [InlineData("error_texto_invalido", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.Texto)]
    [InlineData("error_otra_licencia", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.OtraLicencia)]
    [InlineData("error_serie_no_posterior", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.SerieNoPosterior)]
    [InlineData("error_aun_no_vigente", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.AunNoVigente)]
    [InlineData("error_sin_licencia_para_renovar", CodigosDeLicencia.LicenciaInvalida, MotivosDeRechazo.SinLicenciaInstalada)]
    [InlineData("error_sin_licencia_para_copiar", CodigosDeLicencia.NoEncontrado, MotivosDeRechazo.SinLicenciaInstalada)]
    [InlineData("error_sin_licencia_para_liberar", CodigosDeLicencia.Conflicto, MotivosDeRechazo.SinLicenciaInstalada)]
    public void LosRechazos_TraenSuCodigoYSuMotivo(string fixture, string codigo, string motivo)
    {
        var j = Json(fixture);
        Assert.Equal(codigo, j.GetProperty("codigo").GetString());
        Assert.Equal(motivo, j.GetProperty("motivo").GetString());
        Assert.Contains(motivo, MotivosDeRechazo.Todos);
        Assert.False(string.IsNullOrWhiteSpace(j.GetProperty("detail").GetString()));
    }

    [Fact]
    public void ElTextoPropioDeAunNoVigente_EsElMismoQueElDelNodo()
    {
        Assert.Equal(Json("error_aun_no_vigente").GetProperty("detail").GetString(), LicenciaTexto.Motivo(MotivosDeRechazo.AunNoVigente).Completo);
    }

    [Fact]
    public void LosDemasErrores_TraenLoQueLaPantallaNecesita()
    {
        Assert.Equal((1, 3), (Json("error_huella_no_coincide").GetProperty("coinciden").GetInt32(), Json("error_huella_no_coincide").GetProperty("k").GetInt32()));
        Assert.Equal(PermisosDeLicencia.Leer, Json("error_sin_permiso").GetProperty("permiso").GetString());
        Assert.Equal(PermisosDeLicencia.Renovar, Json("error_sin_permiso_renovar").GetProperty("permiso").GetString());
        Assert.Equal(CodigosDeLicencia.DatosInvalidos, Json("error_sin_cuerpo").GetProperty("codigo").GetString());
        Assert.False(Json("error_sesion_requerida").TryGetProperty("codigo", out _));       // el 401 de DRF sin código: se reconoce por el estado
        var modulo = Json("error_modulo_no_disponible");
        Assert.Equal((CodigosDeLicencia.NoDisponiblePorLicencia, CapacidadesLicenciables.Reportes, "Reportes y exportaciones"),
            (modulo.GetProperty("codigo").GetString(), modulo.GetProperty("capacidad").GetString(), modulo.GetProperty("modulo").GetString()));
        var equipos = Json("error_cupo_equipos");
        Assert.Equal((CodigosDeLicencia.CupoAgotado, "equipos", 2, 2),
            (equipos.GetProperty("codigo").GetString(), equipos.GetProperty("tipo").GetString(), equipos.GetProperty("limite").GetInt32(), equipos.GetProperty("en_uso").GetInt32()));
        var usuarios = Json("error_cupo_usuarios");
        Assert.Equal(("usuarios", 4, 4), (usuarios.GetProperty("tipo").GetString(), usuarios.GetProperty("limite").GetInt32(), usuarios.GetProperty("en_uso").GetInt32()));
    }
}
