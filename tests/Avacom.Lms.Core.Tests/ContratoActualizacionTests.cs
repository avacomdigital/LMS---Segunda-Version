using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Los DTOs y el cliente de <c>/api/actualizacion/</c> (MOD-017) contra las respuestas REALES del backend, capturadas por <c>backend/actualizacion/tests/test_capturar_contrato.py</c> en
/// <c>Fixtures/actualizacion/</c> (cada archivo es <c>{"status", "cuerpo"}</c>). Un campo mal escrito en un DTO se descubre aquí y no en una pantalla. Se comprueba la FORMA y los valores
/// que no cambian entre corridas (los identificadores y las horas sí cambian). Y la regla de la casa (P-11): ninguna respuesta trae una ruta de archivo.
/// </summary>
[Collection("estado global")]
public sealed class ContratoActualizacionTests : IDisposable
{
    private const string Base = "/api/actualizacion/";

    public ContratoActualizacionTests() => ClienteJson.Token = null;
    public void Dispose() => ClienteJson.Token = null;

    private static string Carpeta => Path.Combine(AppContext.BaseDirectory, "Fixtures", "actualizacion");
    private static JsonElement Archivo(string nombre) => Ayudas.Json(File.ReadAllText(Path.Combine(Carpeta, nombre + ".json")));
    private static int Estado(string nombre) => Archivo(nombre).GetProperty("status").GetInt32();
    private static string Cuerpo(string nombre) => Archivo(nombre).GetProperty("cuerpo").GetRawText();

    private static T Cargar<T>(string nombre) =>
        JsonSerializer.Deserialize<T>(Cuerpo(nombre), Ayudas.Web) ?? throw new InvalidOperationException($"{nombre}.json no se pudo leer como {typeof(T).Name}.");

    private static ErrorAula ErrorDe(string nombre) =>
        new(Estado(nombre), Archivo(nombre).GetProperty("cuerpo").GetProperty("codigo").GetString(), Archivo(nombre).GetProperty("cuerpo").GetProperty("detail").GetString()!, null,
            Archivo(nombre).GetProperty("cuerpo").Clone());

    // ================================================================================================== los DTOs contra las respuestas reales

    [Fact]
    public void TodasLasRespuestasCapturadas_SeLeenConSusDtos_YNingunaTraeUnaRuta()
    {
        var nombres = Directory.GetFiles(Carpeta, "*.json").Select(Path.GetFileNameWithoutExtension).Select(n => n!).ToList();
        Assert.True(nombres.Count >= 30, $"sólo hay {nombres.Count} respuestas capturadas en {Carpeta}");
        foreach (var n in nombres)
        {
            if (n is "manifiesto_ejemplo" or "orden_json" or "resultado_json") continue;            // los archivos que se cruzan con el Host: no son respuestas de la API
            object? leido = n switch
            {
                _ when n.StartsWith("estado_", StringComparison.Ordinal) && Estado(n) == 200 => Cargar<EstadoDeActualizacion>(n),
                _ when n.StartsWith("paquetes_", StringComparison.Ordinal) => Cargar<ListaDePaquetes>(n),
                _ when n.StartsWith("paquete_", StringComparison.Ordinal) && Estado(n) == 200 => Cargar<FichaDePaquete>(n),
                _ when (n.StartsWith("importar_2", StringComparison.Ordinal) || n.StartsWith("aplicar_2", StringComparison.Ordinal) || n.StartsWith("revertir_2", StringComparison.Ordinal)
                        || n.StartsWith("programar_2", StringComparison.Ordinal) || n.StartsWith("desprogramar_", StringComparison.Ordinal)) => Cargar<FichaDePaquete>(n),
                "historial" => Cargar<HistorialDeActualizacion>(n),
                "health_aplicando" => Archivo(n).GetProperty("cuerpo").GetProperty("actualizacion").Deserialize<SaludDeActualizacion>(Ayudas.Web),
                _ when Estado(n) >= 400 => Archivo(n).GetProperty("cuerpo").GetProperty("detail").GetString(),
                _ => throw new Xunit.Sdk.XunitException($"Hay una respuesta capturada que ninguna prueba lee: {n}.json"),
            };
            Assert.NotNull(leido);
            var texto = Cuerpo(n);
            Assert.DoesNotContain("\"ruta\"", texto, StringComparison.Ordinal);
            Assert.DoesNotContain("\\\\", texto, StringComparison.Ordinal);                         // ninguna ruta de Windows en el cuerpo
        }
    }

    [Fact]
    public void Estado_AlDia_TieneLaFormaCompleta()
    {
        var e = Cargar<EstadoDeActualizacion>("estado_al_dia");
        Assert.Equal(EstadosDelNodoActualizado.AlDia, e.Estado);
        Assert.Null(e.EnCurso);
        Assert.False(e.OrdenPendiente);
        Assert.False(e.Aplicando);
        Assert.Empty(e.ProgramadosOVacio);
        Assert.Empty(e.RevertiblesOVacio);
        Assert.Equal(14, e.DiasReversion);
        Assert.Equal(2, e.ContratoBiblioteca);
        Assert.False(string.IsNullOrWhiteSpace(e.Version));
        Assert.True(e.ServidorEn > 1_700_000_000_000);
        Assert.True(e.EspacioLibre > 0);
        Assert.NotEmpty(e.ModulosOVacio);
        var acceso = e.ModulosOVacio.Single(m => m.Nombre == "acceso");
        Assert.True(acceso.Actualizable);
        Assert.Equal(1, acceso.VersionContrato);
        Assert.True(acceso.VersionDatos > 0);
        Assert.Contains("audit", acceso.Consume!.Keys);
        Assert.Equal([1, 1], acceso.Consume["audit"]);
        var biblioteca = e.ModulosOVacio.Single(m => m.Nombre == "biblioteca");
        Assert.False(biblioteca.Actualizable);                                                  // la biblioteca es de AVACOM Contenido (R-12)
    }

    [Fact]
    public void Estado_Aplicando_Programado_YAplicado_SeLeenConSuParteEspecifica()
    {
        var aplicando = Cargar<EstadoDeActualizacion>("estado_aplicando");
        Assert.Equal(EstadosDelNodoActualizado.Aplicando, aplicando.Estado);
        Assert.True(aplicando.Aplicando && aplicando.OrdenPendiente);
        Assert.Equal(AccionesDeOrden.Aplicar, aplicando.EnCurso!.Accion);
        Assert.False(string.IsNullOrEmpty(aplicando.EnCurso.OrdenId));
        Assert.True(aplicando.EnCurso.Desde > 0);

        var programado = Cargar<EstadoDeActualizacion>("estado_programado");
        var p = Assert.Single(programado.ProgramadosOVacio);
        Assert.True(p.Ventana!.Hasta > p.Ventana.Desde);
        Assert.False(programado.Aplicando);

        var aplicado = Cargar<EstadoDeActualizacion>("estado_aplicado");
        var r = Assert.Single(aplicado.RevertiblesOVacio);
        Assert.Equal(14L * 86_400_000, r.RevertibleHasta - r.AplicadoEn);                      // 14 días exactos, del reloj del nodo
        Assert.Equal(1, aplicado.Paquetes!["aplicado"]);
    }

    [Fact]
    public void Paquetes_TraeCandidatosOpacos_YLaFichaDeLoImportado()
    {
        var lista = Cargar<ListaDePaquetes>("paquetes_con_candidato");
        var c = Assert.Single(lista.CandidatosOVacio);
        Assert.False(c.YaImportado);
        Assert.Equal("reportes-1.4.0.avupd", c.Nombre);
        Assert.Matches("^[0-9a-f]{24}$", c.Id);                                                 // un id opaco: nunca una ruta
        Assert.Equal("unidad", c.Origen);
        Assert.True(c.Bytes > 0);
        Assert.Empty(lista.PaquetesOVacio);

        var importado = Cargar<ListaDePaquetes>("paquetes_importado");
        Assert.True(importado.CandidatosOVacio[0].YaImportado);
        var ficha = Assert.Single(importado.PaquetesOVacio);
        Assert.Equal(EstadosDePaquete.Verificado, ficha.Estado);
        Assert.Empty(ficha.HistorialOVacio);                                                    // la lista no trae el historial
    }

    [Fact]
    public void Ficha_Verificada_TraeManifiestoCompatibilidadEHistorial()
    {
        var f = Cargar<FichaDePaquete>("paquete_verificado");
        Assert.Equal(EstadosDePaquete.Verificado, f.Estado);
        Assert.Equal(7, f.Serie);
        Assert.False(f.EnCurso || f.Revertible);
        Assert.Equal("upd-dev-1", f.Kid);
        Assert.Matches("^[0-9a-f]{64}$", f.Sha256!);
        var m = Assert.Single(f.ModulosDelManifiesto);
        Assert.Equal(("reporting", "1.4.0", 4), (m.Nombre, m.Version, m.VersionDatos));
        Assert.Equal(["0004_parche_de_ejemplo"], m.Migraciones);
        Assert.Equal(1, m.Requiere!["nodo"]);
        Assert.Equal(2, f.Manifiesto!.Archivos);
        Assert.Equal("2.10.0", f.Manifiesto.Requisitos!.ClienteMinimo);
        Assert.Equal(new[] { TiposDeHistorial.Recibido, TiposDeHistorial.Verificado }, f.HistorialOVacio.Select(h => h.Tipo).ToArray());
        var verificado = f.HistorialOVacio[1];
        Assert.True(verificado.Detalle!.Value.GetProperty("compatibilidad").GetProperty("ok").GetBoolean());
        Assert.Equal("upd-dev-1", verificado.Texto("kid"));
        Assert.Equal(1821, verificado.Numero("bytes"));
    }

    [Fact]
    public void Ficha_Incompatible_TraeSuListaDeProblemas()
    {
        var f = Cargar<FichaDePaquete>("importar_201_incompatible");
        Assert.Equal(EstadosDePaquete.Incompatible, f.Estado);
        Assert.NotEmpty(f.IncompatibilidadesOVacio);
        Assert.All(f.IncompatibilidadesOVacio, i => Assert.False(string.IsNullOrWhiteSpace(i.Codigo)));
    }

    [Fact]
    public void Ficha_Aplicando_TraeLaOrdenEmitida_YAplicado_ElPlazoDeReversion()
    {
        var f = Cargar<FichaDePaquete>("aplicar_202");
        Assert.Equal(EstadosDePaquete.Aplicando, f.Estado);
        Assert.True(f.EnCurso);
        Assert.Equal(AccionesDeOrden.Aplicar, f.Accion);
        Assert.Equal(5, f.Orden!.LimiteMinutos);                                               // C-3: 5 min en general (3 si toca evaluacion)
        Assert.Equal(["comprobar", "respaldar", "instantanea", "copiar", "migrar", "verificar"], f.Orden.Pasos);
        Assert.Equal(f.OrdenId, f.Orden.OrdenId);

        var revertir = Cargar<FichaDePaquete>("revertir_202");
        Assert.Equal(AccionesDeOrden.Revertir, revertir.Orden!.Accion);
        Assert.DoesNotContain("instantanea", revertir.Orden.Pasos!);                            // se restaura DESDE la instantánea

        var aplicado = Cargar<FichaDePaquete>("paquete_aplicado");
        Assert.True(aplicado.Revertible);
        Assert.Equal(14L * 86_400_000, aplicado.RevertibleHasta!.Value - aplicado.AplicadoEn!.Value);
        Assert.Equal(EstadosDePaquete.Revertido, Cargar<FichaDePaquete>("paquete_revertido").Estado);
    }

    [Fact]
    public void Historial_LoUltimoPrimero_ConSuDetalle()
    {
        var h = Cargar<HistorialDeActualizacion>("historial");
        Assert.NotEmpty(h.HechosOVacio);
        Assert.True(h.HechosOVacio.Zip(h.HechosOVacio.Skip(1)).All(par => par.First.Id > par.Second.Id));
        var revertido = h.HechosOVacio[0];
        Assert.Equal(TiposDeHistorial.Revertido, revertido.Tipo);
        Assert.Equal("sistema", revertido.Actor);
        Assert.Equal("revertir", revertido.Texto("accion"));
        Assert.All(h.HechosOVacio, x => Assert.Contains(x.Tipo, TiposDeHistorial.Todos));       // ningún tipo del backend es desconocido para el cliente
        Assert.All(h.HechosOVacio, x => Assert.False(string.IsNullOrWhiteSpace(ActualizacionTexto.Hecho(x))));
    }

    [Fact]
    public void Health_SumaElCampoAditivo()
    {
        var s = Archivo("health_aplicando").GetProperty("cuerpo").GetProperty("actualizacion").Deserialize<SaludDeActualizacion>(Ayudas.Web)!;
        Assert.Equal(EstadosDelNodoActualizado.Aplicando, s.Estado);
        Assert.True(s.OrdenPendiente);
        Assert.NotNull(s.EnCurso);
    }

    [Theory]
    [InlineData("aplicar_403_tecnico", 403, "sin_permiso")]
    [InlineData("estado_403_docente", 403, "sin_permiso")]
    [InlineData("aplicar_409_sesion_activa", 409, "sesion_activa")]
    [InlineData("aplicar_409_contrato_incompatible", 409, "contrato_incompatible")]
    [InlineData("aplicar_409_espacio_insuficiente", 409, "espacio_insuficiente")]
    [InlineData("aplicar_409_en_curso", 409, "estado_invalido")]
    [InlineData("revertir_409_estado_invalido", 409, "estado_invalido")]
    [InlineData("importar_422_alterado", 422, "paquete_invalido")]
    [InlineData("importar_422_sin_firma", 422, "firma_invalida")]
    [InlineData("importar_422_kid_desconocido", 422, "firma_invalida")]
    [InlineData("importar_404_candidato", 404, "no_encontrado")]
    [InlineData("importar_400_sin_candidato", 400, "datos_invalidos")]
    [InlineData("programar_400", 400, "datos_invalidos")]
    [InlineData("inicio_de_clase_503", 503, "actualizacion_en_curso")]
    public void CadaError_LlegaConSuCodigo_YElTextoNuncaLoMuestraCrudo(string archivo, int estado, string codigo)
    {
        var error = ErrorDe(archivo);
        Assert.Equal((estado, codigo), (error.Estado, error.Codigo));
        var m = ActualizacionTexto.DeError(error);
        Assert.False(string.IsNullOrWhiteSpace(m.Titulo));
        Assert.False(string.IsNullOrWhiteSpace(m.Texto));
        Assert.DoesNotContain(codigo, m.Completo, StringComparison.Ordinal);                    // «firma_invalida» no se le dice a nadie
        Assert.DoesNotContain("error", m.Titulo, StringComparison.OrdinalIgnoreCase);
    }

    // ================================================================================================== los textos

    [Fact]
    public void LosTextosDeError_DicenQuePasoYQueHacer()
    {
        Assert.Contains("clase abierta", ActualizacionTexto.DeError(ErrorDe("aplicar_409_sesion_activa")).Titulo, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Espera a que la clase termine", ActualizacionTexto.DeError(ErrorDe("aplicar_409_sesion_activa")).Completo);
        var contrato = ActualizacionTexto.DeError(ErrorDe("aplicar_409_contrato_incompatible"));
        Assert.Contains("AVACOM Contenido", contrato.Texto);                                    // la causa real: la versión del contrato de la biblioteca
        Assert.Contains("No se instaló nada", contrato.Accion);
        var espacio = ActualizacionTexto.DeError(ErrorDe("aplicar_409_espacio_insuficiente"));
        Assert.Contains("64 MB", espacio.Texto);
        Assert.Contains("lo hace la administración", ActualizacionTexto.DeError(ErrorDe("aplicar_403_tecnico")).Texto);
        Assert.Equal("Tu rol no ve las actualizaciones", ActualizacionTexto.DeError(ErrorDe("estado_403_docente")).Titulo);
        Assert.Equal("El paquete no está firmado", ActualizacionTexto.DeError(ErrorDe("importar_422_sin_firma")).Titulo);
        Assert.Equal("Firma que el aula no reconoce", ActualizacionTexto.DeError(ErrorDe("importar_422_kid_desconocido")).Titulo);
        Assert.Contains("No se guardó nada", ActualizacionTexto.DeError(ErrorDe("importar_422_alterado")).Completo);
        Assert.Equal("El aula se está actualizando", ActualizacionTexto.DeError(ErrorDe("inicio_de_clase_503")).Titulo);
    }

    [Fact]
    public void SinConexion_YSesionPerdida_SeDicenSinCodigos()
    {
        Assert.Equal(ActualizacionTexto.SinConexion, ActualizacionTexto.DeError(new ErrorAula(0, "sin_conexion", "x", null, null)).Titulo);
        Assert.Equal("Tu sesión terminó", ActualizacionTexto.DeError(new ErrorAula(401, "sesion_expirada", "x", null, null)).Titulo);
        Assert.Equal("No se pudo completar", ActualizacionTexto.DeError(null).Titulo);
        Assert.Equal("El aula no pudo responder", ActualizacionTexto.DeError(new ErrorAula(500, "otro", "x", null, null)).Titulo);
    }

    [Fact]
    public void ElAulaSeActualiza_SeDiceIgualAlProfesorQueALaTableta_YNuncaEsOtroError()
    {
        var error = ErrorDe("inicio_de_clase_503");
        Assert.True(error.ActualizacionEnCurso);
        Assert.False(new ErrorAula(503, "fuente_no_disponible", "x", null, null).ActualizacionEnCurso);
        var profesor = ActualizacionTexto.SiEstaActualizando(error)!;
        Assert.Equal("El aula se está actualizando; vuelve a intentarlo en unos minutos.", profesor.Texto);
        var tableta = ActualizacionTexto.SiEstaActualizando(error, paraTableta: true)!;
        Assert.Equal("El aula se está actualizando; vuelve a intentarlo en unos minutos.", tableta.Texto);
        Assert.Contains("Lo que hiciste está guardado", tableta.Accion);
        Assert.Null(ActualizacionTexto.SiEstaActualizando(new ErrorAula(409, "sesion_activa", "x", null, null)));
        Assert.Null(ActualizacionTexto.SiEstaActualizando(null));
    }

    [Fact]
    public void PesoYFechas_SeDicenEnPalabras()
    {
        Assert.Equal("—", ActualizacionTexto.Peso(null));
        Assert.Equal("—", ActualizacionTexto.Peso(0));
        Assert.Equal("512 B", ActualizacionTexto.Peso(512));
        Assert.Equal("1,8 KB", ActualizacionTexto.Peso(1821));
        Assert.Equal("64 MB", ActualizacionTexto.Peso(67_111_183));
        Assert.Equal("502 GB", ActualizacionTexto.Peso(538_685_169_664));
        var zona = TimeZoneInfo.Utc;
        var ahora = new DateTimeOffset(2026, 10, 21, 15, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();
        var noche = new DateTimeOffset(2026, 10, 21, 22, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();
        var manana = new DateTimeOffset(2026, 10, 22, 6, 0, 0, TimeSpan.Zero).ToUnixTimeMilliseconds();
        Assert.Equal("hoy de 22:00 a 23:00", ActualizacionTexto.Ventana(new VentanaDeActualizacion(noche, noche + 3_600_000), ahora, zona));
        Assert.Equal("mañana de 06:00 a 07:30", ActualizacionTexto.Ventana(new VentanaDeActualizacion(manana, manana + 5_400_000), ahora, zona));
        Assert.Contains("al 22 de octubre a las 00:30", ActualizacionTexto.Ventana(new VentanaDeActualizacion(noche + 3_600_000, noche + 9_000_000), ahora, zona));
        Assert.Equal("13 días", ActualizacionTexto.DiasHasta(ahora + 13L * 86_400_000, ahora));
        Assert.Equal("1 día", ActualizacionTexto.DiasHasta(ahora + 86_400_000, ahora));
        Assert.Equal("menos de un día", ActualizacionTexto.DiasHasta(ahora + 3_600_000, ahora));
        Assert.Equal("ya pasó el plazo", ActualizacionTexto.DiasHasta(ahora - 1, ahora));
    }

    [Fact]
    public void LaTarjetaDelEquipo_DiceSuEstadoYQueSigue()
    {
        var zona = TimeZoneInfo.Utc;
        var aldia = Cargar<EstadoDeActualizacion>("estado_al_dia");
        Assert.Equal("El aula está al día", ActualizacionTexto.TituloDelEstado(aldia));
        Assert.Equal(TonoDeActualizacion.Bien, ActualizacionTexto.TonoDelEstado(aldia));
        var aplicando = Cargar<EstadoDeActualizacion>("estado_aplicando");
        Assert.Equal("El aula se está actualizando", ActualizacionTexto.TituloDelEstado(aplicando));
        Assert.Contains("Iniciar una clase espera", ActualizacionTexto.FraseDelEstado(aplicando, aplicando.ServidorEn, zona));
        Assert.Contains("las que ya están abiertas siguen", ActualizacionTexto.FraseDelEstado(aplicando, aplicando.ServidorEn, zona));
        var programado = Cargar<EstadoDeActualizacion>("estado_programado");
        Assert.Equal("Hay una actualización programada", ActualizacionTexto.TituloDelEstado(programado));
        Assert.Contains("siempre que no haya una clase abierta", ActualizacionTexto.FraseDelEstado(programado, programado.ServidorEn, zona));
        Assert.All(aldia.ModulosOVacio, m => Assert.False(string.IsNullOrWhiteSpace(ActualizacionTexto.NombreDeModulo(m))));
        Assert.Equal("1.0.0 · datos 20 · contrato 1", ActualizacionTexto.Modulo(aldia.ModulosOVacio.Single(m => m.Nombre == "acceso")));
    }

    [Fact]
    public void ElDetalleDeUnPaquete_DiceQueCambiaCuantoPesaYElEspacio()
    {
        var estado = Cargar<EstadoDeActualizacion>("estado_al_dia");
        var f = Cargar<FichaDePaquete>("paquete_verificado");
        Assert.Equal("Reportes", ActualizacionTexto.ModulosQueCambia(f));
        Assert.Equal("Reportes 1.4.0 · 1 cambio en los datos", ActualizacionTexto.LineaDeModulo(f.ModulosDelManifiesto[0]));
        Assert.Equal("Listo para aplicar", ActualizacionTexto.EstadoDelPaquete(f.Estado));
        Assert.Contains("aplicarlo ahora o programarlo", ActualizacionTexto.FraseDelPaquete(f, estado.ServidorEn));
        var espacio = ActualizacionTexto.Espacio(f, estado);
        Assert.Contains("64 MB", espacio);
        Assert.Contains("502 GB", espacio);
        Assert.Equal("Estado desconocido", ActualizacionTexto.EstadoDelPaquete("inventado"));
        Assert.Contains("no conoce", ActualizacionTexto.FraseDelPaquete(f with { Estado = "inventado" }, 0));
        Assert.Equal("Hubo un movimiento que esta versión no conoce", ActualizacionTexto.Hecho(new HechoDeHistorial(1, null, "inventado", 0, null, null, null, null)));
    }

    [Fact]
    public void LosMotivosDeReversion_SonUnaListaCerrada_ConUnaNotaParaElNodo()
    {
        Assert.InRange(ActualizacionTexto.MotivosDeReversion.Count, 4, 8);
        Assert.All(ActualizacionTexto.MotivosDeReversion, m =>
        {
            Assert.False(string.IsNullOrWhiteSpace(m.Nota));
            Assert.True(m.Nota.Length >= 10);
        });
        Assert.Equal(ActualizacionTexto.MotivosDeReversion.Count, ActualizacionTexto.MotivosDeReversion.Select(m => m.Codigo).Distinct().Count());
    }

    // ================================================================================================== qué botones se ofrecen

    private static readonly UsuarioDeSesion Admin = new("a", "ana", "ADMIN", "admin", 1);
    private static readonly UsuarioDeSesion Tecnico = new("t", "tec", "TECHNICIAN", "technician", 1);
    private static readonly UsuarioDeSesion Profesor = new("p", "pro", "TEACHER", "teacher", 1);

    [Fact]
    public void QuienVeLaPantalla_EsLaAdministracionYElTecnico_NuncaUnProfesor()
    {
        Assert.True(ReglasDeActualizacion.VeLasActualizaciones(Admin));
        Assert.True(ReglasDeActualizacion.VeLasActualizaciones(Tecnico));
        Assert.True(ReglasDeActualizacion.VeLasActualizaciones(null));                          // el prototipo sin sesión: se deja ver y el nodo decide
        Assert.False(ReglasDeActualizacion.VeLasActualizaciones(Profesor));
        Assert.False(ReglasDeActualizacion.VeLasActualizaciones(new UsuarioDeSesion("e", "est", "STUDENT", "student", 1)));
        Assert.False(ReglasDeActualizacion.VeLasActualizaciones(new UsuarioDeSesion("r", "rep", "REPORTS", "reports", 1)));
    }

    [Fact]
    public void Importar_ElTecnicoSi_PeroNoUnPaqueteYaImportadoNiConUnaActualizacionEnMarcha()
    {
        var libre = Cargar<ListaDePaquetes>("paquetes_con_candidato").CandidatosOVacio[0];
        var importado = Cargar<ListaDePaquetes>("paquetes_importado").CandidatosOVacio[0];
        var aldia = Cargar<EstadoDeActualizacion>("estado_al_dia");
        var aplicando = Cargar<EstadoDeActualizacion>("estado_aplicando");
        Assert.True(ReglasDeActualizacion.PuedeImportar(Admin, libre, aldia));
        Assert.True(ReglasDeActualizacion.PuedeImportar(Tecnico, libre, aldia));
        Assert.False(ReglasDeActualizacion.PuedeImportar(Profesor, libre, aldia));
        Assert.False(ReglasDeActualizacion.PuedeImportar(Admin, importado, aldia));
        Assert.False(ReglasDeActualizacion.PuedeImportar(Admin, libre, aplicando));
    }

    [Fact]
    public void Acciones_PorEstado_Rol_ClaseYPlazo()
    {
        var aldia = Cargar<EstadoDeActualizacion>("estado_al_dia");
        var ahora = aldia.ServidorEn;
        var verificado = Cargar<FichaDePaquete>("paquete_verificado");
        var programado = verificado with { Estado = EstadosDePaquete.Programado, Ventana = new VentanaDeActualizacion(ahora + 600_000, ahora + 4_200_000) };
        var aplicado = Cargar<FichaDePaquete>("paquete_aplicado");

        // La administración con un paquete verificado: programa y aplica; no hay nada que revertir ni que desprogramar.
        var a = ReglasDeActualizacion.Acciones(verificado, aldia, Admin, false, ahora);
        Assert.True(a.Programar && a.Aplicar);
        Assert.False(a.Desprogramar || a.Revertir);
        Assert.Null(a.Razon);

        // Programado: puede quitar la ventana o adelantar la aplicación; no programar otra encima.
        var p = ReglasDeActualizacion.Acciones(programado, aldia, Admin, false, ahora);
        Assert.True(p.Desprogramar && p.Aplicar);
        Assert.False(p.Programar);

        // El técnico no aplica ni programa (sólo con escalada, que esta pantalla no concede) y se le dice a quién pedirlo.
        var t = ReglasDeActualizacion.Acciones(verificado, aldia, Tecnico, false, ahora);
        Assert.False(t.Alguna);
        Assert.Contains("administración", t.Razon);

        // Con una clase abierta en este equipo no se ofrece aplicar (nunca se interrumpe una clase), pero sí programar para después.
        var c = ReglasDeActualizacion.Acciones(verificado, aldia, Admin, true, ahora);
        Assert.False(c.Aplicar);
        Assert.True(c.Programar);
        Assert.Contains("clase abierta", c.Razon);

        // Aplicado: se puede revertir dentro de los 14 días y no un milisegundo después.
        Assert.True(ReglasDeActualizacion.Acciones(aplicado, aldia, Admin, false, aplicado.AplicadoEn!.Value + 13L * 86_400_000).Revertir);
        var tarde = ReglasDeActualizacion.Acciones(aplicado, aldia, Admin, false, aplicado.RevertibleHasta!.Value);
        Assert.False(tarde.Revertir);
        Assert.Contains("14 días", tarde.Razon);
        Assert.False(ReglasDeActualizacion.Acciones(aplicado, aldia, Admin, true, aplicado.AplicadoEn!.Value + 1000).Revertir);          // con clase abierta tampoco

        // Una reversión que falló se puede reintentar.
        Assert.True(ReglasDeActualizacion.Acciones(aplicado with { Estado = EstadosDePaquete.ReversionFallida, Revertible = false }, aldia, Admin, false, ahora).Revertir);

        // Con otra actualización en marcha no se ofrece nada y se dice por qué.
        var enMarcha = ReglasDeActualizacion.Acciones(verificado, Cargar<EstadoDeActualizacion>("estado_aplicando"), Admin, false, ahora);
        Assert.False(enMarcha.Alguna);
        Assert.Contains("en marcha", enMarcha.Razon);

        // Un paquete incompatible, revertido o archivado no ofrece nada; un profesor, tampoco.
        Assert.False(ReglasDeActualizacion.Acciones(verificado with { Estado = EstadosDePaquete.Incompatible }, aldia, Admin, false, ahora).Alguna);
        Assert.False(ReglasDeActualizacion.Acciones(verificado with { Estado = EstadosDePaquete.Revertido }, aldia, Admin, false, ahora).Alguna);
        Assert.False(ReglasDeActualizacion.Acciones(verificado, aldia, Profesor, false, ahora).Alguna);
        Assert.True(ReglasDeActualizacion.SeguirMirando(Cargar<EstadoDeActualizacion>("estado_aplicando")));
        Assert.False(ReglasDeActualizacion.SeguirMirando(aldia));
    }

    // ================================================================================================== el cliente: rutas, cuerpos y errores

    private sealed record Captura(HttpMethod Metodo, string Url, string? Cuerpo)
    {
        public JsonElement Json => Ayudas.Json(Cuerpo!);
        public string[] Claves => Json.EnumerateObject().Select(p => p.Name).OrderBy(n => n, StringComparer.Ordinal).ToArray();
    }

    private static (ActualizacionApi Api, List<Captura> Capturas) Api(Func<Captura, HttpResponseMessage> responder)
    {
        var capturas = new List<Captura>();
        var http = new HttpClient(new ManejadorFalso(async (req, _) =>
        {
            var cuerpo = req.Content is null ? null : await req.Content.ReadAsStringAsync();
            var captura = new Captura(req.Method, req.RequestUri!.PathAndQuery, cuerpo);
            capturas.Add(captura);
            return responder(captura);
        }));
        return (new ActualizacionApi(http, new Uri("http://192.168.0.55:8000/")), capturas);
    }

    private static HttpResponseMessage Responder(string archivo) => Ayudas.Respuesta((HttpStatusCode)Estado(archivo), Cuerpo(archivo));

    [Fact]
    public async Task LasLecturas_SonGets_ConElActorEnLaConsulta()
    {
        var (api, capturas) = Api(c => c.Url switch
        {
            var u when u.StartsWith(Base + "estado/") => Responder("estado_al_dia"),
            var u when u.StartsWith(Base + "paquetes/17171717") => Responder("paquete_verificado"),
            var u when u.StartsWith(Base + "paquetes/") => Responder("paquetes_con_candidato"),
            _ => Responder("historial"),
        });
        var estado = await api.EstadoAsync("adm 1");
        var paquetes = await api.PaquetesAsync("adm 1");
        var ficha = await api.PaqueteAsync("adm 1", "17171717-0001-4000-8000-000000000001");
        var historial = await api.HistorialAsync("adm 1", 20, [TiposDeHistorial.Aplicado, TiposDeHistorial.Revertido]);
        Assert.Equal(new[]
        {
            Base + "estado/?actor=adm%201",
            Base + "paquetes/?actor=adm%201",
            Base + "paquetes/17171717-0001-4000-8000-000000000001/?actor=adm%201",
            Base + "historial/?limite=20&tipo=aplicado&tipo=revertido&actor=adm%201",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Get, c.Metodo));
        Assert.Equal(EstadosDelNodoActualizado.AlDia, estado!.Estado);
        Assert.Single(paquetes!.CandidatosOVacio);
        Assert.Equal(EstadosDePaquete.Verificado, ficha!.Estado);
        Assert.NotEmpty(historial!.HechosOVacio);
        Assert.Null(api.UltimoError);
    }

    [Fact]
    public async Task ElLimiteDelHistorial_SeAcotaALoQueAceptaElNodo()
    {
        var (api, capturas) = Api(_ => Responder("historial"));
        await api.HistorialAsync("", 99999);
        await api.HistorialAsync("", 0);
        Assert.Equal(new[] { Base + "historial/?limite=500", Base + "historial/?limite=1" }, capturas.Select(c => c.Url).ToArray());
    }

    [Fact]
    public async Task LasAcciones_SonPosts_ConElActorEnElCuerpo_YNuncaUnaRuta()
    {
        var (api, capturas) = Api(c => c.Url switch
        {
            var u when u.Contains("importar") => Responder("importar_201"),
            var u when u.Contains("desprogramar") => Responder("desprogramar_200"),
            var u when u.Contains("programar") => Responder("programar_200"),
            var u when u.Contains("revertir") => Responder("revertir_202"),
            _ => Responder("aplicar_202"),
        });
        const string id = "17171717-0001-4000-8000-000000000001";
        var importado = await api.ImportarAsync("adm", "d18bb9ec0f9bfa22643c0e2b");
        var programado = await api.ProgramarAsync("adm", id, 1_000, 5_000);
        var quitado = await api.DesprogramarAsync("adm", id);
        var aplicado = await api.AplicarAsync("adm", id);
        var revertido = await api.RevertirAsync("adm", id, "Algo dejó de funcionar después de la actualización.");
        Assert.Equal(new[]
        {
            Base + "paquetes/importar/", $"{Base}paquetes/{id}/programar/", $"{Base}paquetes/{id}/desprogramar/", $"{Base}paquetes/{id}/aplicar/", $"{Base}paquetes/{id}/revertir/",
        }, capturas.Select(c => c.Url).ToArray());
        Assert.All(capturas, c => Assert.Equal(HttpMethod.Post, c.Metodo));
        Assert.Equal(new[] { "actor", "candidato" }, capturas[0].Claves);
        Assert.Equal("d18bb9ec0f9bfa22643c0e2b", capturas[0].Json.GetProperty("candidato").GetString());
        Assert.Equal(new[] { "actor", "desde", "hasta" }, capturas[1].Claves);
        Assert.Equal((1_000L, 5_000L), (capturas[1].Json.GetProperty("desde").GetInt64(), capturas[1].Json.GetProperty("hasta").GetInt64()));
        Assert.Equal(new[] { "actor" }, capturas[2].Claves);
        Assert.Equal(new[] { "actor" }, capturas[3].Claves);
        Assert.Equal(new[] { "actor", "nota" }, capturas[4].Claves);
        Assert.Equal(EstadosDePaquete.Verificado, importado!.Estado);
        Assert.Equal(EstadosDePaquete.Programado, programado!.Estado);
        Assert.Equal(EstadosDePaquete.Verificado, quitado!.Estado);
        Assert.Equal(EstadosDePaquete.Aplicando, aplicado!.Estado);
        Assert.Equal(AccionesDeOrden.Revertir, revertido!.Accion);
        Assert.All(capturas, c => Assert.DoesNotContain(":\\", c.Cuerpo ?? string.Empty));       // el cliente nunca manda una ruta de archivo (P-11)
    }

    [Fact]
    public async Task ConSesion_ElActorNoSeManda_YSeManda_ElToken()
    {
        ClienteJson.Token = "jwt-de-prueba";
        string? autorizacion = null;
        var http = new HttpClient(new ManejadorFalso((req, _) =>
        {
            autorizacion = req.Headers.Authorization?.ToString();
            return Task.FromResult(Responder("estado_al_dia"));
        }));
        var api = new ActualizacionApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.NotNull(await api.EstadoAsync(string.Empty));
        Assert.Equal("Bearer jwt-de-prueba", autorizacion);
    }

    [Theory]
    [InlineData("aplicar_409_sesion_activa", "sesion_activa", 409)]
    [InlineData("aplicar_409_contrato_incompatible", "contrato_incompatible", 409)]
    [InlineData("importar_422_alterado", "paquete_invalido", 422)]
    [InlineData("importar_422_kid_desconocido", "firma_invalida", 422)]
    [InlineData("aplicar_403_tecnico", "sin_permiso", 403)]
    public async Task UnErrorDelNodo_NoEsUnaExcepcion_DejaElCodigoYSusExtras(string archivo, string codigo, int estado)
    {
        var (api, _) = Api(_ => Responder(archivo));
        Assert.Null(await api.AplicarAsync("adm", "x"));
        Assert.Equal((estado, codigo), (api.UltimoError!.Estado, api.UltimoError.Codigo));
        Assert.False(string.IsNullOrWhiteSpace(api.UltimoMotivo));
        if (codigo == "contrato_incompatible") Assert.Equal("contrato_biblioteca", Assert.Single(ActualizacionTexto.Incompatibilidades(api.UltimoError)).Codigo);
        if (codigo == "firma_invalida") Assert.Equal("kid_desconocido", api.UltimoError.Texto("motivo"));
        if (codigo == "sin_permiso") Assert.Equal("update.apply", api.UltimoError.Texto("permiso"));
    }

    [Fact]
    public async Task SinRed_NoEsUnaExcepcion_SeDiceSinConexion()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => throw new HttpRequestException("sin ruta al aula")));
        var api = new ActualizacionApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await api.EstadoAsync("adm"));
        Assert.Equal(0, api.UltimoError!.Estado);
        Assert.Equal(ActualizacionTexto.SinConexion, ActualizacionTexto.DeError(api.UltimoError).Titulo);
    }

    // ================================================================================================== R-02: un 503 de actualización no descarta lo que el alumno hizo

    [Fact]
    public async Task UnDobleCincuentaYTres_ActualizacionEnCurso_ConservaLaColaDeRespuestas()
    {
        var carpeta = Ayudas.CarpetaTemporal();
        try
        {
            var cola = new ColaRespuestas(Path.Combine(carpeta, "cola.json"));
            cola.Guardar("s1", "d1", "p1", 1, "q1", Ayudas.Json("""{"value":true}"""));
            var http = new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(Responder("inicio_de_clase_503"))));
            var sync = new SincronizadorRespuestas(new AulaApi(http, new Uri("http://192.168.0.55:8000/")), cola);
            var r = await sync.VaciarAsync();
            Assert.Equal((0, 1, 0), (r.Enviados, r.Pendientes, r.Descartados));                 // se conserva: un 5xx nunca descarta (un 4xx sí)
            Assert.Single(cola.Pendientes());
        }
        finally { try { Directory.Delete(carpeta, true); } catch { } }
    }

    [Fact]
    public async Task IniciarUnaClase_ConElAulaActualizandose_DejaElMensajeParaLaPantalla()
    {
        var http = new HttpClient(new ManejadorFalso((_, _) => Task.FromResult(Responder("inicio_de_clase_503"))));
        var aula = new AulaApi(http, new Uri("http://192.168.0.55:8000/"));
        Assert.Null(await aula.IniciarAsync(new IniciarSesionSolicitud("libre", null, null, null, "aula", "p", "Profe", "pantalla")));
        Assert.True(aula.UltimoError!.ActualizacionEnCurso);
        Assert.Equal(503, aula.UltimoError.Estado);
        Assert.Equal(ActualizacionTexto.EnCursoParaProfesor, aula.UltimoMotivo);
    }
}
