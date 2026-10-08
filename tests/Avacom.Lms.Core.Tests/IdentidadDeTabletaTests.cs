using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// La huella de una tableta: 35 tabletas del mismo modelo traen el mismo nombre de fábrica y el nodo no puede verlas como una sola
/// (prueba de 35 tabletas, 2026-10-08), pero en las frases para las personas el equipo se lee sin el prefijo ni el código de instalación.
/// </summary>
public sealed class IdentidadDeTabletaTests
{
    [Fact]
    public void Dos_instalaciones_del_mismo_modelo_tienen_huellas_distintas()
    {
        var a = Identidad.HuellaDeTableta("SM-X110", Identidad.NuevaInstalacion());
        var b = Identidad.HuellaDeTableta("SM-X110", Identidad.NuevaInstalacion());
        Assert.NotEqual(a, b);
        Assert.StartsWith("student-SM-X110-", a);
    }

    [Fact]
    public void El_codigo_de_instalacion_son_ocho_digitos_hexadecimales_y_cabe_en_la_huella_del_nodo()
    {
        var codigo = Identidad.NuevaInstalacion();
        Assert.Matches("^[0-9a-f]{8}$", codigo);
        // identificador_hw del nodo admite 128 caracteres
        Assert.True(Identidad.HuellaDeTableta(new string('x', 100), codigo).Length <= 128);
    }

    [Theory]
    [InlineData("student-T-07-a3f9c2d1", "T-07")]
    [InlineData("student-SM-X110-0badf00d", "SM-X110")]
    [InlineData("student-Tablet de Ana-a3f9c2d1", "Tablet de Ana")]
    [InlineData("student-T-07", "T-07")]                       // huella de una versión anterior, sin código
    [InlineData("ops-AULA-MASTER", "AULA-MASTER")]
    [InlineData("ops-AULA-MASTER-0badf00d", "AULA-MASTER")]
    [InlineData("T-07", "T-07")]                               // lo que no es una huella se deja como está
    [InlineData("  student-T-07-a3f9c2d1  ", "T-07")]
    public void El_equipo_se_lee_sin_prefijo_ni_codigo(string huella, string esperado) =>
        Assert.Equal(esperado, Identidad.EquipoLegible(huella));

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Sin_huella_no_hay_equipo(string? huella) => Assert.Equal(string.Empty, Identidad.EquipoLegible(huella));

    [Fact]
    public void Un_aparato_sin_nombre_tiene_huella_igual()
    {
        var huella = Identidad.HuellaDeTableta("  ", "a3f9c2d1");
        Assert.Equal("student-tableta-a3f9c2d1", huella);
        Assert.Equal("tableta", Identidad.EquipoLegible(huella));
    }
}
