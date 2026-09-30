using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Hosting.WindowsServices;
using Microsoft.Extensions.Logging;

namespace Avacom.Ops.Host;

/// <summary>
/// Un solo ejecutable con varios verbos. Lo usa el instalador durante la
/// instalacion y la desinstalacion, y lo usa el equipo del aula cada dia como
/// servicio y como lanzador.
///
/// Todos los verbos son no interactivos salvo <c>iniciar</c>, y ninguno pide
/// que se escriba nada: el nodo principal se maneja solo con toques.
/// </summary>
internal static class Program
{
    private static int Main(string[] argumentos)
    {
        var verbo = argumentos.Length > 0 ? argumentos[0].ToLowerInvariant() : "iniciar";

        return verbo switch
        {
            "servicio" => Servir(),
            "iniciar" => Lanzador.Ejecutar(),
            "preparar" => Preparar.Ejecutar(),
            "salud" => Comprobar(argumentos),
            "validar" => Validar(argumentos),
            "respaldar" => Respaldar(argumentos),
            "restaurar-datos" => RestaurarDatos(),
            "vaciar-datos" => VaciarDatos(),
            "puerto-libre" => PuertoLibre(),
            "instalar-servicio" => Servicio.Instalar(new Registro("instalacion.log")),
            "quitar-servicio" => Con(Servicio.Quitar),
            "iniciar-servicio" => Servicio.Iniciar(new Registro("instalacion.log")) ? 0 : 10,
            "detener-servicio" => Con(r => Servicio.Detener(r)),
            "abrir-firewall" => Firewall.Abrir(new Registro("instalacion.log"), Configuracion.PuertoConfigurado()),
            "cerrar-firewall" => Con(Firewall.Cerrar),
            _ => Ayuda(verbo),
        };
    }

    /// <summary>Punto de entrada del servicio Windows AVACOMOPSBackend.</summary>
    private static int Servir()
    {
        // Nombre completo: en este ensamblado "Host" es el espacio de nombres propio.
        var constructor = Microsoft.Extensions.Hosting.Host.CreateApplicationBuilder();
        constructor.Services.AddHostedService<ServicioBackend>();
        constructor.Services.AddWindowsService(opciones => opciones.ServiceName = Servicio.Nombre);

        // El diagnostico va a los archivos de Logs del nodo: escribir en el
        // registro de eventos exigiria registrar un origen y no aporta nada
        // que no este ya en servicio.log.
        constructor.Logging.ClearProviders();

        constructor.Build().Run();
        return 0;
    }

    private static int Comprobar(string[] argumentos)
    {
        var segundos = argumentos.Length > 1 && int.TryParse(argumentos[1], out var valor) ? valor : 45;
        var puerto = Configuracion.PuertoConfigurado();
        var resultado = Salud.EsperarAsync(puerto, segundos).GetAwaiter().GetResult();

        var registro = new Registro("instalacion.log");
        registro.Escribir($"Comprobacion de salud en {Salud.UrlSalud(puerto)}: {resultado.Detalle}");
        return resultado.Correcto ? 0 : 11;
    }

    /// <summary>
    /// La validacion final de una instalacion o actualizacion: /health/ responde y
    /// el canal en tiempo real acepta conexiones. Deja en Logs/resumen-nodo.txt lo
    /// que la pantalla final muestra (direcciones para las tabletas, si falta la
    /// organizacion).
    /// 0 correcto, 11 el backend no responde, 14 el WebSocket no acepta conexiones.
    /// </summary>
    private static int Validar(string[] argumentos)
    {
        var segundos = argumentos.Length > 1 && int.TryParse(argumentos[1], out var valor) ? valor : 60;
        var puerto = Configuracion.PuertoConfigurado();
        var registro = new Registro("instalacion.log");
        var resumen = Path.Combine(Rutas.CarpetaLogs, "resumen-nodo.txt");
        File.Delete(resumen);

        var salud = Salud.EsperarAsync(puerto, segundos).GetAwaiter().GetResult();
        registro.Escribir($"Validacion de salud en {Salud.UrlSalud(puerto)}: {salud.Detalle}");
        if (!salud.Correcto) return 11;

        var socket = Salud.ProbarWebSocketAsync(puerto).GetAwaiter().GetResult();
        registro.Escribir($"Validacion del tiempo real: {socket.Detalle}");
        if (!socket.Correcto) return 14;

        var estado = Salud.EstadoAsync(puerto).GetAwaiter().GetResult();
        static string SiNo(bool? v) => v is null ? "desconocido" : v.Value ? "si" : "no";

        var lineas = new List<string>
        {
            "salud=ok",
            "websocket=ok",
            $"organizacion={SiNo(estado.Instalado)}",
            $"claves_derivadas={SiNo(estado.ClavesDerivadas)}",
        };
        lineas.AddRange(Direcciones.Listar(puerto).Select(d => $"direccion={d}"));
        File.WriteAllLines(resumen, lineas);
        registro.Escribir($"Estado del nodo: organizacion={SiNo(estado.Instalado)}, claves derivadas={SiNo(estado.ClavesDerivadas)}.");
        return 0;
    }

    /// <summary>Copia de seguridad de la base (+wal, +shm) y backend.env. Con el servicio detenido.</summary>
    private static int Respaldar(string[] argumentos)
    {
        var registro = new Registro("instalacion.log");
        try
        {
            Datos.Respaldar(registro, argumentos.Length > 1 ? argumentos[1] : "anterior");
            return 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            registro.Escribir("No se pudo hacer la copia de seguridad", error);
            return 20;
        }
    }

    private static int RestaurarDatos()
    {
        var registro = new Registro("instalacion.log");
        try
        {
            return Datos.Restaurar(registro) ? 0 : 21;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            registro.Escribir("No se pudieron restaurar los datos", error);
            return 22;
        }
    }

    private static int VaciarDatos()
    {
        var registro = new Registro("instalacion.log");
        try
        {
            Datos.Vaciar(registro);
            return 0;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            registro.Escribir("No se pudieron retirar los datos", error);
            return 23;
        }
    }

    private static int PuertoLibre()
    {
        var puerto = Configuracion.PuertoConfigurado();
        if (Salud.PuertoLibre(puerto)) return 0;
        // 12 = ocupado por nuestro propio backend (una reinstalacion, no un conflicto).
        // 13 = ocupado por otro programa.
        return Salud.EsNuestroBackendAsync(puerto).GetAwaiter().GetResult() ? 12 : 13;
    }

    private static int Con(Action<Registro> accion)
    {
        accion(new Registro("instalacion.log"));
        return 0;
    }

    private static int Ayuda(string verbo)
    {
        Lanzador.Avisar(
            "AVACOM OPS Master",
            $"La orden \"{verbo}\" no existe.\n\n" +
            "Este componente lo usa el instalador de AVACOM OPS Master.");
        return 64;
    }
}
