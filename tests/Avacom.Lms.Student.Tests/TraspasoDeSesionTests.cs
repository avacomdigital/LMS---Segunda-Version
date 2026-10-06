using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.Tests.Ayudas;

namespace Avacom.Lms.Student.Tests;

/// <summary>Un solo acceso para las dos apps: lo que pasa con la sesión cuando la cuenta es de la otra app.</summary>
public sealed class TraspasoDeSesionTests
{
    private static readonly Uri Nodo = new("http://127.0.0.1:8010/");

    [Fact]
    public async Task SiLaOtraAppNoSeEncuentraNoSePideNingunCodigo()
    {
        var api = new FalsoAccesoApi();
        var r = await TraspasoEntreApps.PasarAsync(api, AppDelAcceso.Ops, Nodo, buscar: _ => null, lanzar: (_, _, _) => true);
        Assert.Equal(ResultadoTraspaso.SinApp, r);
        Assert.DoesNotContain("traspaso", api.Llamadas);   // la sesión no se gasta en vano
    }

    [Fact]
    public async Task SeAbreLaOtraAppConElCodigoYElServidor()
    {
        var api = new FalsoAccesoApi();
        (string Exe, string Codigo, Uri Servidor)? lanzado = null;
        var r = await TraspasoEntreApps.PasarAsync(api, AppDelAcceso.Ops, Nodo, buscar: _ => @"C:\ops.exe", lanzar: (e, c, s) => { lanzado = (e, c, s); return true; });
        Assert.Equal(ResultadoTraspaso.Abierta, r);
        Assert.Equal((@"C:\ops.exe", "codigo-de-traspaso", Nodo), lanzado);
    }

    [Fact]
    public async Task SinRedNoHayCodigoYSiNoArrancaSeDice()
    {
        var sinRed = new FalsoAccesoApi { SinRed = true };
        Assert.Equal(ResultadoTraspaso.SinCodigo, await TraspasoEntreApps.PasarAsync(sinRed, AppDelAcceso.Student, Nodo, _ => @"C:\s.exe", (_, _, _) => true));
        var api = new FalsoAccesoApi();
        Assert.Equal(ResultadoTraspaso.NoArranco, await TraspasoEntreApps.PasarAsync(api, AppDelAcceso.Student, Nodo, _ => @"C:\s.exe", (_, _, _) => false));
    }

    [Fact]
    public void LosMensajesDicenDondeEntrar()
    {
        Assert.Contains("AVACOM OPS", TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Ops, ResultadoTraspaso.SinApp));
        Assert.Contains("AVACOM Student", TraspasoEntreApps.MensajeSinTraspaso(AppDelAcceso.Student, ResultadoTraspaso.NoArranco));
    }
}
