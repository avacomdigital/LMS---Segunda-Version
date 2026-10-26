using System.Runtime.Versioning;
using static Avacom.Ops.Host.Dispositivo.FormatoSello;
using static Avacom.Ops.Host.Dispositivo.PuertaDeDispositivo;

namespace Avacom.Ops.Host.Dispositivo;

/// <summary>
/// Los verbos del Host para el sello de dispositivo. El Host es un WinExe (sin consola), asi que lo que se le quiere decir a una persona queda en
/// <c>Logs\dispositivo.txt</c> (el ultimo mensaje, para el instalador y para el tecnico) y en <c>dispositivo.log</c>; el resultado, en el codigo de salida.
/// </summary>
[SupportedOSPlatform("windows")]
internal static class Verbos
{
    private static string RutaDelMensaje => Path.Combine(Rutas.CarpetaLogs, "dispositivo.txt");

    private static void Decir(Registro registro, string mensaje)
    {
        registro.Escribir(mensaje);
        try { Directory.CreateDirectory(Rutas.CarpetaLogs); File.AppendAllText(RutaDelMensaje, mensaje + Environment.NewLine); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        try { Console.Out.WriteLine(mensaje); } catch (IOException) { }
    }

    private static void LimpiarMensaje() { try { File.Delete(RutaDelMensaje); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { } }

    private static long Ahora() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

    private static string? Opcion(string[] a, string nombre)
    {
        var i = Array.FindIndex(a, x => x.Equals(nombre, StringComparison.OrdinalIgnoreCase));
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
    }

    public static int Verificar(string[] argumentos) => VerificarCon(new ClavesCng(), LlavesIncrustadas(), CarpetaDeSelloDelNodo, RutaDeSenal, new Registro("dispositivo.log"), escribirMensaje: true);

    internal static int VerificarCon(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, string rutaSenal, Registro registro, bool escribirMensaje)
    {
        if (escribirMensaje) LimpiarMensaje();
        var r = HayMarcadorDeDesarrollo()
            ? new Resultado(Desarrollo, "marcador", null, claves.EnTpm, null, 0)
            : llaves.Count == 0 ? new Resultado(NoVerificable, "sin_llaves", null, claves.EnTpm, null, 0) : PuertaDeDispositivo.Verificar(claves, llaves, carpetaSello, Ahora());
        try { Actualizacion.Disco.EscribirAtomico(rutaSenal, Senal(r, DateTime.UtcNow)); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        Decir(registro, $"Dispositivo AVACOM: {r.Estado}{(r.Motivo.Length > 0 ? " (" + r.Motivo + ")" : "")}. {Mensaje(r.Estado)}");
        return Salida(r.Estado);
    }

    public static int Solicitar(string[] argumentos)
    {
        var registro = new Registro("dispositivo.log");
        LimpiarMensaje();
        var destino = argumentos.Skip(1).FirstOrDefault(a => !a.StartsWith("--", StringComparison.Ordinal) && a != Opcion(argumentos, "--serie"))
            ?? Path.Combine(UnidadesExtraibles().FirstOrDefault() ?? Path.Combine(Rutas.RaizDatos, "Solicitudes"), "AVACOM");
        var (codigo, ruta) = PuertaDeDispositivo.Solicitar(new ClavesCng(), destino, Opcion(argumentos, "--serie"), Ahora());
        if (codigo == SalidaSinClaves)
        {
            Decir(registro, "No se pudieron crear las claves del equipo. Abre el programa como administrador.");
            return codigo;
        }
        Decir(registro, $"Solicitud de sello guardada en {ruta}. Entregala a AVACOM; te devolvera un archivo .avsello.");
        return 0;
    }

    public static int Instalar(string[] argumentos)
    {
        var registro = new Registro("dispositivo.log");
        LimpiarMensaje();
        var ruta = argumentos.Length > 1 ? argumentos[1] : null;
        var candidatas = Candidatas(ruta).ToList();
        if (candidatas.Count == 0) { Decir(registro, "No se encontro ningun archivo .avsello ni .avrev. Inserta la memoria USB que dejo AVACOM."); return SalidaUso; }
        var (instalados, mensajes) = PuertaDeDispositivo.Instalar(candidatas, LlavesIncrustadas(), CarpetaDeSelloDelNodo);
        foreach (var m in mensajes) Decir(registro, m);
        return instalados > 0 ? 0 : SalidaSelloInvalido;
    }

    /// <summary>Lo que corre el instalador antes de copiar nada. 0 = se puede instalar.</summary>
    public static int PuertaDeInstalacion(string[] argumentos) => PuertaCon(new ClavesCng(), LlavesIncrustadas(), CarpetaDeSelloDelNodo, RutaDeSenal, new Registro("dispositivo.log"), () => UnidadesExtraibles().ToList());

    internal static int PuertaCon(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, string rutaSenal, Registro registro, Func<List<string>> unidades)
    {
        var codigo = VerificarCon(claves, llaves, carpetaSello, rutaSenal, registro, escribirMensaje: true);
        if (codigo == 0 || llaves.Count == 0) return codigo;
        // Un sello que esperaba en una memoria USB (el flujo de entrega): se recoge, se verifica y se vuelve a preguntar.
        var candidatas = unidades().SelectMany(u => Candidatas(u)).ToList();
        if (candidatas.Count > 0)
        {
            var (instalados, mensajes) = PuertaDeDispositivo.Instalar(candidatas, llaves, carpetaSello);
            foreach (var m in mensajes) Decir(registro, m);
            if (instalados > 0) { codigo = VerificarCon(claves, llaves, carpetaSello, rutaSenal, registro, escribirMensaje: false); if (codigo == 0) return 0; }
        }
        // Sigue sin pasar. Si el equipo aun no tiene claves (o no tiene sello), deja la solicitud para llevarla a AVACOM.
        if (codigo is SalidaSinSello or SalidaClaveDistinta or SalidaNoVerificable)
        {
            var donde = Path.Combine(unidades().FirstOrDefault() ?? Path.Combine(Rutas.RaizDatos, "Solicitudes"), "AVACOM");
            var (c, ruta) = PuertaDeDispositivo.Solicitar(claves, donde, null, Ahora());
            if (c == 0) Decir(registro, $"Se dejo la solicitud de sello en {ruta}. Llevala a AVACOM, copia el .avsello que te devuelvan a esa misma memoria y abre otra vez el instalador.");
        }
        return codigo;
    }
}
