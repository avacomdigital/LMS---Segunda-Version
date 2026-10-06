using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// El §5 de los requisitos de acceso (UXR-005, UXR-009): cada código del §C.4.3 se dice en palabras de aula —qué pasó y qué sigue—, sin el código ni la
/// palabra «error», y los números (intentos, minutos) salen de los extras del nodo.
/// </summary>
public sealed class MensajesDeAccesoTests
{
    private static ErrorAula Error(int estado, string codigo, string extraJson = "{}", string detalle = "x", string? sugerencia = null)
    {
        using var doc = JsonDocument.Parse(extraJson);
        return new ErrorAula(estado, codigo, detalle, sugerencia, doc.RootElement.Clone());
    }

    [Fact]
    public void Pin_maestro_equivocado_dice_los_intentos_que_quedan()
    {
        Assert.Equal("Ese PIN no es. Te quedan 3 intentos.", MensajesDeAcceso.Texto(Error(401, "pin_maestro_invalido", """{"intentos_restantes":3}""")));
        Assert.Equal("Ese PIN no es. Te queda 1 intento.", MensajesDeAcceso.Texto(Error(401, "pin_maestro_invalido", """{"intentos_restantes":1}""")));
        Assert.Equal("Ese PIN no es.", MensajesDeAcceso.Texto(Error(401, "pin_maestro_invalido")));
    }

    [Fact]
    public void Pin_maestro_bloqueado_dice_los_minutos_hacia_arriba()
    {
        Assert.Equal("Demasiados intentos desde este equipo. Vuelve a probar en 15 minutos.",
                     MensajesDeAcceso.Texto(Error(423, "pin_maestro_bloqueado", """{"reintentar_en_seg":900}""")));
        Assert.Contains("en 15 minutos", MensajesDeAcceso.Texto(Error(423, "pin_maestro_bloqueado", """{"reintentar_en_seg":841}""")));
        Assert.Contains("en 1 minutos", MensajesDeAcceso.Texto(Error(423, "pin_maestro_bloqueado", """{"reintentar_en_seg":5}""")));
    }

    [Fact]
    public void Pin_maestro_vencido_y_desde_una_tableta_de_alumno()
    {
        Assert.Equal("El PIN maestro venció. Pídele a administración que lo cambie y vuelve a intentarlo.", MensajesDeAcceso.Texto(Error(403, "pin_maestro_vencido")));
        Assert.Equal("Esto se hace desde el equipo del profesor.", MensajesDeAcceso.Texto(Error(403, "dispositivo_no_autorizado")));
        Assert.Contains("no está registrada", MensajesDeAcceso.Texto(Error(403, "dispositivo_no_autorizado"), Audiencia.Alumno));
    }

    [Fact]
    public void Alias_repetido_pide_una_letra_mas_con_la_sugerencia_del_nodo()
    {
        var e = Error(409, "alias_duplicado", """{"alias":"Juan P.","sugerencia":"Juan Pé."}""");
        Assert.Equal("Ya hay alguien llamado Juan P. en este grupo. Añade una letra: Juan Pé.", MensajesDeAcceso.Texto(e));
        var sin = Error(409, "alias_duplicado", """{"alias":"Sofía","sugerencia":null}""");
        Assert.Equal("Ya hay alguien llamado Sofía en este grupo. Añade una letra o tu apellido.", MensajesDeAcceso.Texto(sin));
    }

    [Fact]
    public void Tableta_en_pausa_ofrece_la_salida_del_visitante()
    {
        var texto = MensajesDeAcceso.Texto(Error(423, "dispositivo_en_pausa", """{"reintentar_en_seg":120}"""));
        Assert.Equal("Esperemos un momento: vuelve a probar en 2 minutos, o entra como visitante.", texto);
        Assert.DoesNotContain("Juan", texto);   // el castigo no menciona a ningún compañero
    }

    [Fact]
    public void Pin_pendiente_manda_a_elegir_uno()
    {
        Assert.Equal("Todavía no tienes PIN. Elige uno de 4 números que recuerdes.", MensajesDeAcceso.Texto(Error(403, "pin_pendiente")));
    }

    [Fact]
    public void Registro_cerrado_y_visitante_apagado()
    {
        Assert.Contains("está apagado", MensajesDeAcceso.Texto(Error(403, "registro_cerrado"), Audiencia.Alumno));
        Assert.Contains("registro de profesores está cerrado", MensajesDeAcceso.Texto(Error(403, "registro_cerrado")));
        Assert.Contains("creó varios usuarios", MensajesDeAcceso.Texto(Error(403, "registro_cerrado", """{"motivo":"tope_por_tableta"}""")));
        Assert.Equal("Hoy no se puede entrar como visitante. Pídele ayuda al profesor.", MensajesDeAcceso.Texto(Error(403, "visitante_no_permitido")));
    }

    [Fact]
    public void Credenciales_invalidas_cambia_el_sujeto_segun_quien_lee()
    {
        var e = Error(401, "credenciales_invalidas", """{"intentos_restantes":2}""");
        Assert.Equal("Ese documento o esa clave no coinciden. Te quedan 2 intentos.", MensajesDeAcceso.Texto(e));
        Assert.Equal("Ese PIN no es. Te quedan 2 intentos.", MensajesDeAcceso.Texto(e, Audiencia.Alumno));
    }

    [Fact]
    public void Una_clave_debil_dice_las_reglas_que_no_cumple()
    {
        var e = Error(400, "secreto_debil", """{"reglas":["La contraseña debe tener al menos 8 caracteres.","Debe incluir al menos una letra mayúscula."]}""");
        Assert.Equal("La contraseña debe tener al menos 8 caracteres. Debe incluir al menos una letra mayúscula.", MensajesDeAcceso.Texto(e));
        Assert.Equal(2, e.Reglas.Count);
    }

    [Fact]
    public void Sin_conexion_y_sin_error_se_dicen_con_calma()
    {
        Assert.Equal(MensajesDeAcceso.SinConexion, MensajesDeAcceso.Texto(Error(0, "sin_conexion")));
        Assert.Equal(MensajesDeAcceso.Generico, MensajesDeAcceso.Texto(null));
        Assert.Equal(MensajesDeAcceso.Generico, MensajesDeAcceso.Texto(Error(500, "algo_raro")));
    }

    [Fact]
    public void Los_textos_fijos_son_los_del_requisito()
    {
        Assert.Equal("Listo. Cerramos tus sesiones abiertas. Entra con tu nueva contraseña.", MensajesDeAcceso.ContrasenaRestablecida);
        Assert.Equal("Entraste como visitante. Lo que hagas no se guardará en tu historial.", MensajesDeAcceso.AvisoVisitante);
    }

    [Theory]
    [InlineData("pin_maestro_invalido")]
    [InlineData("pin_maestro_bloqueado")]
    [InlineData("pin_maestro_vencido")]
    [InlineData("pin_maestro_requerido")]
    [InlineData("pin_maestro_no_configurado")]
    [InlineData("pin_debil")]
    [InlineData("pin_invalido")]
    [InlineData("dispositivo_no_autorizado")]
    [InlineData("dispositivo_en_pausa")]
    [InlineData("pin_pendiente")]
    [InlineData("alias_duplicado")]
    [InlineData("registro_cerrado")]
    [InlineData("visitante_no_permitido")]
    [InlineData("sesion_visitante_limitada")]
    [InlineData("credenciales_invalidas")]
    [InlineData("usuario_bloqueado")]
    [InlineData("secreto_debil")]
    [InlineData("identificador_duplicado")]
    public void Ningun_mensaje_lleva_el_codigo_ni_la_palabra_error(string codigo)
    {
        foreach (var audiencia in new[] { Audiencia.Personal, Audiencia.Alumno })
        {
            var texto = MensajesDeAcceso.Texto(Error(403, codigo, """{"reintentar_en_seg":60,"intentos_restantes":2}"""), audiencia);
            Assert.DoesNotContain(codigo, texto);
            Assert.DoesNotContain("error", texto, StringComparison.OrdinalIgnoreCase);
            Assert.NotEmpty(texto);
        }
    }
}
