using System.Text.Json;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Acceso;

namespace Avacom.Lms.Ops.Tests;

/// <summary>Lo que el acceso de OPS decide sin interfaz (RF-01…RF-09 de los requisitos de acceso).</summary>
public sealed class ReglasDeAccesoTests
{
    // ------------------------------------------------------------------------------------------------------------- PIN maestro (RN-02, RN-05)

    [Theory]
    [InlineData("111111")]
    [InlineData("123456")]
    [InlineData("654321")]
    [InlineData("012345")]
    [InlineData("121212")]
    [InlineData("123123")]
    public void Los_pin_triviales_se_avisan_antes_de_pedir_la_confirmacion(string pin)
    {
        Assert.True(PinMaestroLocal.EsTrivial(pin));
        Assert.NotNull(PinMaestroLocal.Problema(pin));
    }

    [Theory]
    [InlineData("482915")]
    [InlineData("739104")]
    [InlineData("112233")]
    public void Un_pin_de_seis_digitos_no_trivial_pasa_a_la_confirmacion(string pin) => Assert.Null(PinMaestroLocal.Problema(pin));

    [Theory]
    [InlineData("")]
    [InlineData("12345")]
    [InlineData("1234567")]
    [InlineData("12a456")]
    public void El_pin_maestro_son_exactamente_seis_numeros(string pin)
    {
        Assert.False(PinMaestroLocal.FormatoValido(pin));
        Assert.Equal("El PIN maestro son exactamente seis números.", PinMaestroLocal.Problema(pin));
    }

    // ------------------------------------------------------------------------------------------------------------- código del aula

    [Theory]
    [InlineData("IE San José · Sede primaria", "IE-SAN-JOSE-SEDE-PRIMARIA")]
    [InlineData("  Colegio  Ñandú  ", "COLEGIO-NANDU")]
    [InlineData("", "AULA")]
    [InlineData("···", "AULA")]
    public void El_codigo_del_aula_sale_del_nombre(string nombre, string codigo) => Assert.Equal(codigo, CodigoDeAula.Desde(nombre));

    [Fact]
    public void El_codigo_no_pasa_de_32_caracteres_ni_termina_en_guion()
    {
        var codigo = CodigoDeAula.Desde("Institución Educativa Departamental Agropecuaria San Rafael");
        Assert.True(codigo.Length <= 32);
        Assert.False(codigo.EndsWith('-'));
    }

    // ------------------------------------------------------------------------------------------------------------- borrador del primer arranque

    [Fact]
    public void El_borrador_se_reanuda_en_el_ultimo_paso_confirmado()
    {
        var b = new BorradorDeInstalacion(BorradorDeInstalacion.PasoPin, "MX", "es", "Aula 1", "52100200", "Ana", "Ríos");
        var leido = BorradorDeInstalacion.Desde(b.ToJson());
        Assert.Equal(b, leido);
        Assert.Equal(BorradorDeInstalacion.PasoPin, leido.Paso);
    }

    [Fact]
    public void El_borrador_nunca_salta_un_paso_sin_sus_datos_ni_guarda_secretos()
    {
        Assert.Equal(BorradorDeInstalacion.PasoAula, new BorradorDeInstalacion(BorradorDeInstalacion.PasoPin, Aula: "").PasoReanudable);
        Assert.Equal(BorradorDeInstalacion.PasoAdministrador, new BorradorDeInstalacion(BorradorDeInstalacion.PasoPin, Aula: "Aula 1").PasoReanudable);
        // La hoja (paso 5) no se reanuda desde el borrador: vive cifrada aparte.
        Assert.Equal(BorradorDeInstalacion.PasoPin, new BorradorDeInstalacion(BorradorDeInstalacion.PasoHoja, Aula: "A", Documento: "1", Nombres: "N").PasoReanudable);
        var json = new BorradorDeInstalacion(BorradorDeInstalacion.PasoPin, Aula: "A", Documento: "1", Nombres: "N").ToJson();
        Assert.DoesNotContain("pin", json.Replace("\"paso\"", string.Empty).Replace("\"pais\"", string.Empty), StringComparison.OrdinalIgnoreCase);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("{no es json")]
    public void Un_borrador_ilegible_empieza_de_cero(string? json) => Assert.Equal(new BorradorDeInstalacion(), BorradorDeInstalacion.Desde(json));

    // ------------------------------------------------------------------------------------------------------------- hoja de acceso (PAN-204)

    private static HojaDeAcceso Hoja(string aula = "IE San José") => new(aula, "IE-SAN-JOSE", "Ana Ríos", "52100200", "kP7#vQ2m!Lr9", "482915", 1_790_000_000_000);

    [Fact]
    public void La_hoja_se_guarda_y_se_lee_entera()
    {
        var h = Hoja();
        Assert.Equal(h, HojaDeAcceso.Desde(h.ToJson()));
        Assert.Equal("482 915", h.PinLegible);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("{roto")]
    [InlineData("""{"aula":"A","codigo":"A","administrador":"x","documento":"1","contrasena":"","pin_maestro":"482915","creada_en":0}""")]
    public void Sin_contrasena_o_sin_pin_no_hay_hoja_pendiente(string? json) => Assert.Null(HojaDeAcceso.Desde(json));

    [Fact]
    public void La_hoja_impresa_lleva_la_contrasena_y_el_pin_y_escapa_el_html()
    {
        var html = Hoja("Aula <script>alert(1)</script>").Html();
        Assert.Contains("kP7#vQ2m!Lr9", html);
        Assert.Contains("482 915", html);
        Assert.Contains("window.print()", html);
        Assert.DoesNotContain("<script>alert(1)</script>", html);
        Assert.Contains("&lt;script&gt;", html);
    }

    // ------------------------------------------------------------------------------------------------------------- qué ofrece el acceso (RF-05, RN-03, RF-09)

    private static ConfiguracionAcceso Config(bool configurado = true, bool vencido = false, bool registroDocentes = true, bool instalado = true) =>
        new(instalado, true, PinMaestro: new EstadoPublicoDelPin(configurado, vencido), AutoregistroDocentes: registroDocentes);

    [Fact]
    public void Con_el_pin_vigente_y_el_registro_abierto_se_ofrecen_las_dos_acciones()
    {
        var o = OfertaDeCuenta.Para(Config());
        Assert.True(o.CrearMiUsuario && o.OlvideMiContrasena);
        Assert.Null(o.Nota);
        Assert.Null(o.AvisoAlTocar);
    }

    [Fact]
    public void Sin_pin_maestro_no_se_ofrece_ninguna_y_se_dice_que_sigue()
    {
        var o = OfertaDeCuenta.Para(Config(configurado: false));
        Assert.False(o.CrearMiUsuario || o.OlvideMiContrasena);
        Assert.Equal(OfertaDeCuenta.SinPinMaestro, o.Nota);
    }

    [Fact]
    public void Un_nodo_anterior_sin_estado_del_pin_tampoco_ofrece_nada()
    {
        var o = OfertaDeCuenta.Para(new ConfiguracionAcceso(true, true));
        Assert.False(o.CrearMiUsuario || o.OlvideMiContrasena);
    }

    [Fact]
    public void Con_el_registro_cerrado_solo_queda_olvide_mi_contrasena()
    {
        var o = OfertaDeCuenta.Para(Config(registroDocentes: false));
        Assert.False(o.CrearMiUsuario);
        Assert.True(o.OlvideMiContrasena);
        Assert.Equal(OfertaDeCuenta.RegistroCerrado, o.Nota);
    }

    [Fact]
    public void Con_el_pin_vencido_las_acciones_siguen_y_explican_que_paso()
    {
        var o = OfertaDeCuenta.Para(Config(vencido: true));
        Assert.True(o.CrearMiUsuario && o.OlvideMiContrasena);
        Assert.Equal(OfertaDeCuenta.PinVencido, o.AvisoAlTocar);
        Assert.DoesNotContain("error", o.AvisoAlTocar!, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Sin_instalar_o_sin_respuesta_no_se_ofrece_nada()
    {
        Assert.False(OfertaDeCuenta.Para(null).CrearMiUsuario);
        Assert.False(OfertaDeCuenta.Para(Config(instalado: false)).OlvideMiContrasena);
    }

    // ------------------------------------------------------------------------------------------------------------- banda del vencimiento (RN-08, AC-A05)

    private static UsuarioDeSesion Persona(string menu) => new("u1", "Ana", menu.ToUpperInvariant(), menu, menu == "teacher" ? 2 : 3);

    private static EstadoPinMaestro Fino(int dias, bool aviso, bool vencido = false) =>
        new(true, 1_760_000_000_000, DateTimeOffset.UtcNow.AddDays(dias).ToUnixTimeMilliseconds(), dias, vencido, aviso);

    [Fact]
    public void Al_profesorado_nunca_se_le_muestra_la_cuenta_atras()
    {
        Assert.Null(AvisoDelPinMaestro.Texto(Persona("teacher"), new EstadoPublicoDelPin(true, false, true)));
        Assert.Null(AvisoDelPinMaestro.Texto(Persona("teacher"), new EstadoPublicoDelPin(true, true)));
        Assert.Null(AvisoDelPinMaestro.Texto(null, new EstadoPublicoDelPin(true, false, true)));
    }

    [Fact]
    public void Con_31_dias_no_hay_aviso_y_con_30_si_con_los_dias_exactos_para_la_administracion()
    {
        Assert.Null(AvisoDelPinMaestro.Texto(Persona("admin"), new EstadoPublicoDelPin(true, false, false), Fino(31, aviso: false)));
        var texto = AvisoDelPinMaestro.Texto(Persona("admin"), new EstadoPublicoDelPin(true, false, true), Fino(30, aviso: true));
        Assert.NotNull(texto);
        Assert.Contains("en 30 días", texto);
        Assert.Contains("Seguridad del aula", texto);
    }

    [Fact]
    public void El_tecnico_ve_el_aviso_sin_cifras()
    {
        var texto = AvisoDelPinMaestro.Texto(Persona("technician"), new EstadoPublicoDelPin(true, false, true));
        Assert.Equal("El PIN maestro vence en menos de 30 días. Avisa a la administración para que lo cambie.", texto);
    }

    [Fact]
    public void Vencido_o_sin_configurar_tambien_se_avisa_a_administracion_y_tecnico()
    {
        Assert.Contains("venció", AvisoDelPinMaestro.Texto(Persona("admin"), new EstadoPublicoDelPin(true, true), Fino(0, true, vencido: true)));
        Assert.Contains("venció", AvisoDelPinMaestro.Texto(Persona("technician"), new EstadoPublicoDelPin(true, true)));
        Assert.Contains("todavía no tiene PIN maestro", AvisoDelPinMaestro.Texto(Persona("admin"), new EstadoPublicoDelPin(false)));
        Assert.Null(AvisoDelPinMaestro.Texto(Persona("admin"), null));
    }

    [Theory]
    [InlineData(1, "vence mañana")]
    [InlineData(0, "vence hoy")]
    public void Los_ultimos_dias_se_dicen_en_palabras(int dias, string esperado) =>
        Assert.Contains(esperado, AvisoDelPinMaestro.Texto(Persona("admin"), new EstadoPublicoDelPin(true, false, true), Fino(dias, aviso: true)));

    // ------------------------------------------------------------------------------------------------------------- contraseña nueva

    [Fact]
    public void La_contrasena_nueva_se_escribe_dos_veces_y_alcanza_el_minimo()
    {
        Assert.Equal("Escribe tu contraseña nueva dos veces.", ContrasenaNueva.Problema("", "", 8));
        Assert.Equal("Las dos contraseñas no coinciden. Escríbelas otra vez.", ContrasenaNueva.Problema("Profe.2026", "Profe.2027", 8));
        Assert.Equal("La contraseña necesita al menos 12 caracteres.", ContrasenaNueva.Problema("Corta.1", "Corta.1", 12));
        Assert.Null(ContrasenaNueva.Problema("Profe.Rios.2026", "Profe.Rios.2026", 8));
    }

    [Fact]
    public void El_minimo_sale_de_la_politica_publica_del_perfil()
    {
        using var perfiles = JsonDocument.Parse("""{"teacher":{"longitud_minima":10},"admin":{"longitud_minima":12}}""");
        var c = new ConfiguracionAcceso(true, true, perfiles.RootElement.Clone());
        Assert.Equal(10, ContrasenaNueva.Minimo(c, "teacher", 8));
        Assert.Equal(12, ContrasenaNueva.Minimo(c, "admin", 8));
        Assert.Equal(8, ContrasenaNueva.Minimo(c, "reports", 8));
        Assert.Equal(8, ContrasenaNueva.Minimo(null, "teacher", 8));
    }
}
