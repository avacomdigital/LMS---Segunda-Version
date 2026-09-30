using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace Avacom.Ops.Host;

/// <summary>
/// Las direcciones a las que las tabletas pueden llegar. Student pide escribir
/// algo como http://192.168.0.55:8000: el instalador las muestra en su pantalla
/// final para que no haya que averiguarlas.
/// </summary>
internal static class Direcciones
{
    private static readonly string[] Virtuales =
        ["vethernet", "virtual", "vmware", "virtualbox", "hyper-v", "docker", "wsl", "loopback", "bluetooth", "tap-", "vpn", "tunnel"];

    public static IReadOnlyList<string> Listar(int puerto)
    {
        var resultado = new List<string>();
        try
        {
            foreach (var adaptador in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (adaptador.OperationalStatus != OperationalStatus.Up) continue;
                if (adaptador.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;

                var nombre = (adaptador.Name + " " + adaptador.Description).ToLowerInvariant();
                if (Virtuales.Any(nombre.Contains)) continue;

                foreach (var unicast in adaptador.GetIPProperties().UnicastAddresses)
                {
                    var ip = unicast.Address;
                    if (ip.AddressFamily != AddressFamily.InterNetwork) continue;
                    var texto = ip.ToString();
                    if (texto.StartsWith("169.254.", StringComparison.Ordinal) || texto.StartsWith("127.", StringComparison.Ordinal)) continue;
                    resultado.Add($"http://{texto}:{puerto}");
                }
            }
        }
        catch (NetworkInformationException)
        {
            // Sin lista de direcciones la pantalla final lo dice; no se detiene nada.
        }
        return resultado;
    }
}
