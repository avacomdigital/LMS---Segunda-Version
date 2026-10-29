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

    /// <summary>
    /// Las claves de ESTE equipo: en el almacen de la MAQUINA (las usan el instalador, el servicio SYSTEM y OPS). En un ENSAYO del instalador (AVACOM_OPS_ENSAYO=1 + carpeta de pruebas) son claves de USUARIO con
    /// un nombre propio de esa carpeta: un ensayo nunca crea ni toca las claves reales del equipo, ni necesita elevarse.
    /// </summary>
    internal static ClavesCng ClavesDeEsteEquipo() => Rutas.EsEnsayo
        ? new ClavesCng("-ensayo-" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(Rutas.RaizDatos)))[..10].ToLowerInvariant(), maquina: false)
        : new ClavesCng();

    /// <summary>Solo en un ENSAYO: borra las claves de usuario que el ensayo creo con su nombre propio. Fuera de un ensayo no hace nada (nunca borra las claves reales del equipo).</summary>
    public static int BorrarClavesDeEnsayo()
    {
        if (!Rutas.EsEnsayo) return SalidaUso;
        ClavesDeEsteEquipo().Borrar();
        return 0;
    }

    /// <summary>El firmware de ESTE equipo. En un ENSAYO el identificador sale de AVACOM_OPS_UEFI (nunca se lee el firmware real ni se necesita elevarse).</summary>
    internal static ILectorUefi LectorUefiDeEsteEquipo() => Rutas.EsEnsayo ? new LectorUefiDeEnsayo(Environment.GetEnvironmentVariable("AVACOM_OPS_UEFI")) : new LectorUefiWindows();

    private static long Ahora() => DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

    private static string? Opcion(string[] a, string nombre)
    {
        var i = Array.FindIndex(a, x => x.Equals(nombre, StringComparison.OrdinalIgnoreCase));
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
    }

    public static int Verificar(string[] argumentos) => VerificarCon(ClavesDeEsteEquipo(), LlavesIncrustadas(), CarpetaDeSelloDelNodo, RutaDeSenal, new Registro("dispositivo.log"), escribirMensaje: true, LectorUefiDeEsteEquipo());

    /// <summary>
    /// El veredicto de este equipo, con sus dos señales (la de Config para el tecnico y la de Logs para el lanzador, que corre sin privilegios). NO escribe mensajes: la usan tambien el servicio, que
    /// verifica en cada arranque, y el contrato <see cref="IIdentidadDeDispositivoAvacom"/>.
    /// </summary>
    internal static Resultado Resolver(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, string rutaSenal, ILectorUefi lector)
    {
        var r = HayMarcadorDeDesarrollo()
            ? new Resultado(Desarrollo, "marcador", null, claves.EnTpm, null, 0)
            : llaves.Count == 0 ? new Resultado(NoVerificable, "sin_llaves", null, claves.EnTpm, null, 0) : PuertaDeDispositivo.Verificar(claves, llaves, carpetaSello, Ahora(), lector);
        try { Actualizacion.Disco.EscribirAtomico(rutaSenal, Senal(r, DateTime.UtcNow)); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        try { Actualizacion.Disco.EscribirAtomico(RutaDeSenalDelLanzador(rutaSenal), SenalParaElLanzador(r, DateTime.UtcNow)); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        return r;
    }

    private static int Declarar(Resultado r, Registro registro, bool escribirMensaje)
    {
        if (escribirMensaje) LimpiarMensaje();
        var codigo = r.Identidad == EstadoDeIdentidad.Autorizado ? "" : $" Codigo {r.CodigoDeDiagnostico}.";
        Decir(registro, $"Dispositivo AVACOM: {r.Estado}{(r.Motivo.Length > 0 ? " (" + r.Motivo + ")" : "")}. {Mensaje(r.Estado)}{codigo}");
        return Salida(r.Estado);
    }

    internal static int VerificarCon(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, string rutaSenal, Registro registro, bool escribirMensaje, ILectorUefi lector) =>
        Declarar(Resolver(claves, llaves, carpetaSello, rutaSenal, lector), registro, escribirMensaje);

    /// <summary>
    /// Diagnostico para quien da soporte en una OPS real: dice que leyo del firmware y en que estado de identidad queda este equipo. Es el UNICO lugar donde el identificador aparece (en el archivo
    /// dispositivo.txt de Logs, que lee la persona que pidio el diagnostico). Solo LEE. Debe abrirse como administrador: sin el privilegio de firmware el codigo es AVC-UEFI-06.
    /// </summary>
    public static int Identidad(string[] argumentos)
    {
        var registro = new Registro("dispositivo.log");
        LimpiarMensaje();
        var lector = LectorUefiDeEsteEquipo();
        var leida = IdentidadUefi.Leer(lector);
        Decir(registro, leida.Fallo is null ? $"Variable {IdentidadUefi.Nombre} leida: {leida.Id}." : $"No se pudo leer la variable {IdentidadUefi.Nombre}: {leida.Motivo}.");
        var r = new IdentidadDeDispositivo(ClavesDeEsteEquipo(), LlavesIncrustadas(), CarpetaDeSelloDelNodo, lector, Ahora).Validar();
        Decir(registro, $"Identidad del dispositivo: {r.Estado} ({r.Motivo}). Codigo {r.Codigo}.");
        return r.Autorizado ? 0 : r.Estado is EstadoDeIdentidad.DispositivoSinLicencia ? SalidaSinSello : SalidaIdentidadUefi;
    }

    public static int Solicitar(string[] argumentos)
    {
        var registro = new Registro("dispositivo.log");
        LimpiarMensaje();
        var destino = argumentos.Skip(1).FirstOrDefault(a => !a.StartsWith("--", StringComparison.Ordinal) && a != Opcion(argumentos, "--serie"))
            ?? Path.Combine(UnidadesExtraibles().FirstOrDefault() ?? Path.Combine(Rutas.RaizDatos, "Solicitudes"), "AVACOM");
        var uefi = IdentidadUefi.Leer(LectorUefiDeEsteEquipo());
        if (uefi.Fallo is not null)
        {
            Decir(registro, $"No se puede pedir el sello: este equipo no muestra una identidad UEFI de AVACOM valida (codigo {IdentidadUefi.Codigo(uefi.Fallo.Value)}).");
            return SalidaIdentidadUefi;
        }
        var (codigo, ruta) = PuertaDeDispositivo.Solicitar(ClavesDeEsteEquipo(), destino, Opcion(argumentos, "--serie"), Ahora(), uefi.Id);
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

    /// <summary>
    /// Diagnostico y ensayos de la liberacion: intenta liberar la llave del paquete de ESTE equipo y dice si pudo, SIN imprimirla ni escribirla (solo el kid del paquete y el motivo). 0 = se libero.
    /// </summary>
    public static int ProbarLiberacion(string[] argumentos)
    {
        var registro = new Registro("dispositivo.log");
        LimpiarMensaje();
        var kid = LiberacionDeClave.KidDelPaquete(LiberacionDeClave.RutaDelPaquete);
        if (kid is null) { Decir(registro, "Este paquete no esta cifrado (no hay Backend/codigo.avpkg)."); return SalidaUso; }
        try
        {
            LiberacionDeClave.Obtener();
            Decir(registro, $"Liberacion de la clave del paquete {Convert.ToHexString(kid).ToLowerInvariant()}: correcta.");
            return 0;
        }
        catch (LiberacionFallida f)
        {
            Decir(registro, $"Liberacion de la clave del paquete {Convert.ToHexString(kid).ToLowerInvariant()}: {f.Motivo}.");
            return f.Motivo.StartsWith("dispositivo_", StringComparison.Ordinal) ? Salida(f.Motivo["dispositivo_".Length..]) : SalidaNoVerificable;
        }
    }

    /// <summary>Lo que corre el instalador antes de copiar nada. 0 = se puede instalar.</summary>
    public static int PuertaDeInstalacion(string[] argumentos) => PuertaCon(ClavesDeEsteEquipo(), LlavesIncrustadas(), CarpetaDeSelloDelNodo, RutaDeSenal, new Registro("dispositivo.log"), () => UnidadesExtraibles().ToList(), LectorUefiDeEsteEquipo());

    internal static int PuertaCon(IClavesDeEquipo claves, IReadOnlyDictionary<string, byte[]> llaves, string carpetaSello, string rutaSenal, Registro registro, Func<List<string>> unidades, ILectorUefi lector)
    {
        var r = Resolver(claves, llaves, carpetaSello, rutaSenal, lector);
        var codigo = Declarar(r, registro, escribirMensaje: true);
        if (codigo == 0 || llaves.Count == 0) return codigo;
        // Sin una identidad UEFI valida (variable ausente, firmware Legacy, sin permiso, etc.) esto no es un equipo que AVACOM pueda sellar: no se recoge nada de una USB ni se deja solicitud.
        if (r.Estado == IdentidadUefiRechazada && r.Motivo is not ("dispositivo_sin_licencia" or "sello_sin_identificador")) return codigo;
        // Un sello que esperaba en una memoria USB (el flujo de entrega): se recoge, se verifica y se vuelve a preguntar.
        var candidatas = unidades().SelectMany(u => Candidatas(u)).ToList();
        if (candidatas.Count > 0)
        {
            var (instalados, mensajes) = PuertaDeDispositivo.Instalar(candidatas, llaves, carpetaSello);
            foreach (var m in mensajes) Decir(registro, m);
            if (instalados > 0) { r = Resolver(claves, llaves, carpetaSello, rutaSenal, lector); codigo = Declarar(r, registro, escribirMensaje: false); if (codigo == 0) return 0; }
        }
        // Sigue sin pasar. Si el equipo aun no tiene claves (o no tiene sello), deja la solicitud para llevarla a AVACOM.
        if ((codigo is SalidaSinSello or SalidaClaveDistinta or SalidaNoVerificable or SalidaIdentidadUefi) && r.UefiId.Length > 0)
        {
            var donde = Path.Combine(unidades().FirstOrDefault() ?? Path.Combine(Rutas.RaizDatos, "Solicitudes"), "AVACOM");
            var (c, ruta) = PuertaDeDispositivo.Solicitar(claves, donde, null, Ahora(), r.UefiId);
            if (c == 0) Decir(registro, $"Se dejo la solicitud de sello en {ruta}. Llevala a AVACOM, copia el .avsello que te devuelvan a esa misma memoria y abre otra vez el instalador.");
        }
        return codigo;
    }
}
