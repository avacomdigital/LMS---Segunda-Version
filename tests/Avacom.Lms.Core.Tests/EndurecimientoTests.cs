using System.Security.Cryptography;
using Avacom.Lms.Core.Desarrollo;
using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Core.Tests;

/// <summary>
/// Endurecimiento de Student y OPS (MOD-018 · Fase 5, P-25): los interruptores de desarrollo sólo valen en depuración o con el marcador junto al programa (y MUERTOS en un Release sin marcador:
/// estas pruebas corren también con <c>-c Release</c> para comprobarlo contra el binario de entrega), y la clave de datos envuelta con una clave no exportable de CNG.
/// </summary>
[Collection("estado global")]
public sealed class EndurecimientoTests : IDisposable
{
    private readonly Func<string, string?> variable = InterruptoresDeDesarrollo.LeerVariable;
    private readonly Func<bool> marcador = InterruptoresDeDesarrollo.HayMarcador;

    public void Dispose()
    {
        InterruptoresDeDesarrollo.LeerVariable = variable;
        InterruptoresDeDesarrollo.HayMarcador = marcador;
    }

    private static void Simular(string? valor, bool hayMarcador)
    {
        InterruptoresDeDesarrollo.LeerVariable = _ => valor;
        InterruptoresDeDesarrollo.HayMarcador = () => hayMarcador;
    }

    [Theory]
    [InlineData(true, false, true)]       // depuración
    [InlineData(false, true, true)]       // entrega con el marcador de QA
    [InlineData(false, false, false)]     // entrega sin marcador: el interruptor no hace nada
    [InlineData(true, true, true)]
    public void LaReglaPura(bool depuracion, bool marcadorPuesto, bool obedece) =>
        Assert.Equal(obedece, InterruptoresDeDesarrollo.Obedece(depuracion, marcadorPuesto));

#if DEBUG
    [Fact]
    public void EnDepuracion_LosInterruptoresValen_ConOSinMarcador()
    {
        Simular("1", hayMarcador: false);
        Assert.True(InterruptoresDeDesarrollo.Permitidos);
        Assert.True(InterruptoresDeDesarrollo.Encendido("AVACOM_EXAM_NO_LOCKDOWN"));
        Assert.True(InterruptoresDeDesarrollo.Preferencia(true));
        Assert.False(InterruptoresDeDesarrollo.IgnoradoPorSerEntrega("AVACOM_EXAM_NO_LOCKDOWN"));
    }
#else
    [Fact]
    public void EnUnaEntrega_SinMarcador_LosInterruptoresEstanMuertos()
    {
        Simular("1", hayMarcador: false);
        Assert.False(InterruptoresDeDesarrollo.Permitidos);
        Assert.False(InterruptoresDeDesarrollo.Encendido("AVACOM_EXAM_NO_LOCKDOWN"));
        Assert.False(InterruptoresDeDesarrollo.Encendido("AVACOM_ESTUDIO_DEMO"));
        Assert.False(InterruptoresDeDesarrollo.Preferencia(true));                          // ni la preferencia `estudio_demo`
        Assert.True(InterruptoresDeDesarrollo.IgnoradoPorSerEntrega("AVACOM_EXAM_NO_LOCKDOWN"));
    }

    [Fact]
    public void EnUnaEntrega_ConElMarcador_VuelvenAValer()
    {
        Simular("1", hayMarcador: true);
        Assert.True(InterruptoresDeDesarrollo.Encendido("AVACOM_EXAM_NO_LOCKDOWN"));
        Assert.True(InterruptoresDeDesarrollo.Preferencia(true));
    }
#endif

    [Fact]
    public void UnaVariableQueNoEsUno_NuncaEnciende()
    {
        foreach (var valor in new[] { null, "", "0", "true", "si", " 1" })
        {
            Simular(valor, hayMarcador: true);
            Assert.False(InterruptoresDeDesarrollo.Encendido("AVACOM_EXAM_NO_LOCKDOWN"), valor);
        }
    }

    [Fact]
    public void SiNoSePuedeMirarElMarcador_NoSeObedece()
    {
        InterruptoresDeDesarrollo.LeerVariable = _ => "1";
        InterruptoresDeDesarrollo.HayMarcador = () => throw new UnauthorizedAccessException();
#if !DEBUG
        Assert.False(InterruptoresDeDesarrollo.Permitidos);
#else
        Assert.True(InterruptoresDeDesarrollo.Permitidos);        // en depuración no hace falta mirar
#endif
    }

    // ---------------------------------------------------------------------------------------------------- clave de datos envuelta

    [Fact]
    public void LaClaveDeDatosEnvuelta_VuelveIgual_YNoEsLaClave()
    {
        if (!OperatingSystem.IsWindows()) return;
        var envoltorio = new EnvoltorioCng("AVACOM-Prueba-" + Guid.NewGuid().ToString("N")[..8], probarTpm: false);
        try
        {
            var clave = RandomNumberGenerator.GetBytes(32);
            var envuelta = envoltorio.Envolver(clave);
            Assert.Equal(256, envuelta.Length);
            Assert.DoesNotContain(clave[0..8].ToHex(), Convert.ToHexString(envuelta));
            Assert.Equal(clave, envoltorio.Desenvolver(envuelta));
            Assert.NotEqual(envuelta, envoltorio.Envolver(clave));                      // OAEP lleva sal: la misma clave no se envuelve igual dos veces
        }
        finally { envoltorio.Destruir(); }
    }

    [Fact]
    public void LoEnvueltoNoSeAbreSinLaClaveEnvolvente_NiAlterado()
    {
        if (!OperatingSystem.IsWindows()) return;
        var nombre = "AVACOM-Prueba-" + Guid.NewGuid().ToString("N")[..8];
        var envoltorio = new EnvoltorioCng(nombre, probarTpm: false);
        try
        {
            var envuelta = envoltorio.Envolver(RandomNumberGenerator.GetBytes(32));
            var alterada = (byte[])envuelta.Clone();
            alterada[10] ^= 1;
            Assert.Null(envoltorio.Desenvolver(alterada));
            Assert.Null(envoltorio.Desenvolver([1, 2, 3]));
            envoltorio.Destruir();                                                      // sin la clave envolvente, lo envuelto ya no abre
            Assert.Null(new EnvoltorioCng(nombre, probarTpm: false).Desenvolver(envuelta));
        }
        finally { envoltorio.Destruir(); }
    }

    [Fact]
    public void LaClaveEnvolventeNoSeExporta()
    {
        if (!OperatingSystem.IsWindows()) return;
        var nombre = "AVACOM-Prueba-" + Guid.NewGuid().ToString("N")[..8];
        var envoltorio = new EnvoltorioCng(nombre, probarTpm: false);
        try
        {
            envoltorio.Envolver(new byte[32]);
            using var llave = CngKey.Open(nombre, CngProvider.MicrosoftSoftwareKeyStorageProvider);
            Assert.Equal(CngExportPolicies.None, llave.ExportPolicy);
            Assert.ThrowsAny<CryptographicException>(() => llave.Export(CngKeyBlobFormat.Pkcs8PrivateBlob));
        }
        finally { envoltorio.Destruir(); }
    }
}

internal static class Hex
{
    public static string ToHex(this byte[] bytes) => Convert.ToHexString(bytes);
}
