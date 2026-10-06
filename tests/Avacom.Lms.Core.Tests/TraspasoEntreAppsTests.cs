using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Tests;

public sealed class TraspasoEntreAppsTests
{
    private static UsuarioDeSesion Con(string? menu) => new("u1", "Alias", "ROL", menu, 1);

    [Theory]
    [InlineData("student", AppDelAcceso.Student)]
    [InlineData("STUDENT", AppDelAcceso.Student)]
    [InlineData("teacher", AppDelAcceso.Ops)]
    [InlineData("admin", AppDelAcceso.Ops)]
    [InlineData("technician", AppDelAcceso.Ops)]
    [InlineData("reports", AppDelAcceso.Ops)]
    [InlineData(null, AppDelAcceso.Ops)]
    public void ElMenuDelRolDecideEnQueAppVive(string? menu, AppDelAcceso esperada) =>
        Assert.Equal(esperada, TraspasoEntreApps.AppDe(Con(menu)));

    [Fact]
    public void LeeElCodigoYElServidorDeLosArgumentos()
    {
        var t = TraspasoEntreApps.Leer(["--otra=1", "--traspaso=abc.def.ghi", "--servidor=http://192.168.1.5:8000"]);
        Assert.Equal(new TraspasoEntrante("abc.def.ghi", "http://192.168.1.5:8000"), t);
        Assert.Equal(new TraspasoEntrante("x", null), TraspasoEntreApps.Leer(["--traspaso=x"]));
    }

    [Theory]
    [InlineData]
    [InlineData("--servidor=http://x")]
    [InlineData("--traspaso=")]
    [InlineData("--traspaso=   ")]
    public void SinCodigoNoHayTraspaso(params string[] argumentos) =>
        Assert.Null(TraspasoEntreApps.Leer(argumentos));

    [Fact]
    public void LaVariableDeEntornoManda_YSiApuntaAUnArchivoQueNoExisteNoSeInventaOtro()
    {
        string? Entorno(string n) => n == "AVACOM_OPS_EXE" ? @"D:\ops\Avacom.Lms.Ops.exe" : null;
        Assert.Equal(@"D:\ops\Avacom.Lms.Ops.exe", TraspasoEntreApps.BuscarEjecutable(AppDelAcceso.Ops, Entorno, _ => true));
        Assert.Null(TraspasoEntreApps.BuscarEjecutable(AppDelAcceso.Ops, Entorno, _ => false));
    }

    [Fact]
    public void OpsSeBuscaEnLaInstalacionDeProgramFiles()
    {
        var esperado = Path.Combine(@"C:\Program Files", "AVACOM", "OPS Master", "App", "Avacom.Lms.Ops.exe");
        string? Entorno(string n) => n == "ProgramFiles" ? @"C:\Program Files" : null;
        Assert.Equal(esperado, TraspasoEntreApps.BuscarEjecutable(AppDelAcceso.Ops, Entorno, f => f == esperado));
    }

    [Fact]
    public void EnDesarrolloSeEligeLaCompilacionMasNuevaDeLaOtraApp()
    {
        var raiz = Ayudas.CarpetaTemporal();
        var student = Path.Combine(raiz, "src", "Avacom.Lms.Student", "bin", "Debug", "net10", "win-x64");
        var ops = Path.Combine(raiz, "src", "Avacom.Lms.Ops", "bin");
        var vieja = Path.Combine(ops, "Release", "Avacom.Lms.Ops.exe"); var nueva = Path.Combine(ops, "Debug", "Avacom.Lms.Ops.exe");
        Directory.CreateDirectory(student); Directory.CreateDirectory(Path.GetDirectoryName(vieja)!); Directory.CreateDirectory(Path.GetDirectoryName(nueva)!);
        File.WriteAllText(vieja, "x"); File.WriteAllText(nueva, "x");
        File.SetLastWriteTimeUtc(vieja, DateTime.UtcNow.AddDays(-3));
        Assert.Equal(nueva, TraspasoEntreApps.BuscarEjecutable(AppDelAcceso.Ops, _ => null, carpetaBase: student));
        Assert.Null(TraspasoEntreApps.BuscarEjecutable(AppDelAcceso.Student, _ => null, carpetaBase: student));   // no hay compilación de Student
    }
}
