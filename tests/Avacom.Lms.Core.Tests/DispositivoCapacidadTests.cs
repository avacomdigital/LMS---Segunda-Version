using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Tests;

/// <summary>MOD-009 × MOD-010: la capacidad de control que cada tableta declara (<c>capacidad_control</c>) llega en <c>/api/dispositivos/</c> y OPS la muestra junto al estado.</summary>
public sealed class DispositivoCapacidadTests
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private static DispositivoAula De(string extra) => JsonSerializer.Deserialize<DispositivoAula>(
        """{"id":"d-1","identificador_hw":"hw-1","nombre":"Tableta 07","tipo":"TABLETA","activo":true,"bloqueado":false,"en_linea":true,"registrado_en":1,"ultimo_latido_en":1,"sesion_abierta":null""" + extra + "}", Json)!;

    [Theory]
    [InlineData("controlado", "Controlado")]
    [InlineData("supervisado", "Supervisado")]
    [InlineData("abierto", "Abierto")]
    public void LaCapacidadDeclaradaSeLeeYSeDiceEnPalabrasDeAula(string valor, string legible)
    {
        var tableta = De($",\"capacidad_control\":\"{valor}\"");
        Assert.True(tableta.CapacidadDeclarada);
        Assert.Equal(valor, tableta.CapacidadControl);
        Assert.Equal(legible, tableta.CapacidadLegible);
    }

    [Theory]
    [InlineData("")]
    [InlineData(",\"capacidad_control\":\"\"")]
    [InlineData(",\"capacidad_control\":null")]
    public void SinDeclararNoEsUnaCapacidadYCuentaComoAbiertoFrenteAUnExamen(string extra)
    {
        var tableta = De(extra);
        Assert.False(tableta.CapacidadDeclarada);
        Assert.Equal("No declarada", tableta.CapacidadLegible);
        Assert.True(Niveles.Alcanza(tableta.CapacidadControl, Niveles.Abierto));
        Assert.False(Niveles.Alcanza(tableta.CapacidadControl, Niveles.Supervisado));
        Assert.False(Niveles.Alcanza(tableta.CapacidadControl, Niveles.Controlado));
    }
}
