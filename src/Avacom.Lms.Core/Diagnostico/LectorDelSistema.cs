using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;

namespace Avacom.Lms.Core.Diagnostico;

/// <summary>
/// De dónde salen las lecturas crudas del equipo. Todo es «mejor esfuerzo»: lo que el sistema no da (Android restringe <c>/proc/stat</c> y las
/// estadísticas de red de otras apps) vuelve nulo y el panel dice «no disponible» en vez de inventar un número. Las pruebas ponen uno falso.
/// </summary>
public interface ILectorDelSistema
{
    int Nucleos { get; }
    /// <summary>Tiempos acumulados de CPU de todo el equipo: (inactivo, total). Nulo si el sistema no los da.</summary>
    (ulong Inactivo, ulong Total)? TiemposDeCpuDelSistema();
    /// <summary>CPU acumulada por este proceso.</summary>
    TimeSpan TiempoDeCpuDelProceso();
    /// <summary>RAM del equipo en bytes: (total, disponible).</summary>
    (long Total, long Disponible)? MemoriaDelSistema();
    long MemoriaDelProceso();
    /// <summary>Bytes acumulados recibidos y enviados por las interfaces de red activas (sin loopback).</summary>
    (long Recibidos, long Enviados)? BytesDeRed();
    /// <summary>Bytes de lectura y escritura acumulados por este proceso (archivos).</summary>
    (long Leidos, long Escritos)? BytesDeDiscoDelProceso();
    /// <summary>Espacio del volumen que contiene <paramref name="ruta"/>: (total, libre) en bytes.</summary>
    (long Total, long Libre)? Disco(string ruta);
}

public sealed class LectorDelSistema : ILectorDelSistema
{
    public int Nucleos { get; } = Math.Max(1, Environment.ProcessorCount);

    public (ulong Inactivo, ulong Total)? TiemposDeCpuDelSistema()
    {
        try
        {
            if (OperatingSystem.IsWindows())
                return GetSystemTimes(out var inactivo, out var nucleo, out var usuario) ? (inactivo, nucleo + usuario) : null;   // «nucleo» ya incluye el inactivo
            // Linux / Android: la primera línea de /proc/stat. Android 8+ la niega a las apps: entonces queda nulo.
            var linea = File.ReadLines("/proc/stat").FirstOrDefault();
            if (linea is null || !linea.StartsWith("cpu ")) return null;
            var n = linea.Split(' ', StringSplitOptions.RemoveEmptyEntries).Skip(1).Select(ulong.Parse).ToArray();
            if (n.Length < 4) return null;
            ulong total = 0;
            foreach (var v in n.Take(8)) total += v;
            return (n[3] + (n.Length > 4 ? n[4] : 0), total);
        }
        catch { return null; }
    }

    public TimeSpan TiempoDeCpuDelProceso()
    {
        try { using var p = Process.GetCurrentProcess(); return p.TotalProcessorTime; }
        catch { return TimeSpan.Zero; }
    }

    public (long Total, long Disponible)? MemoriaDelSistema()
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                var m = new MemoriaEstado { Largo = (uint)Marshal.SizeOf<MemoriaEstado>() };
                return GlobalMemoryStatusEx(ref m) ? ((long)m.TotalFisica, (long)m.DisponibleFisica) : null;
            }
            long? total = null, disponible = null;
            foreach (var linea in File.ReadLines("/proc/meminfo"))
            {
                if (linea.StartsWith("MemTotal:")) total = Kb(linea);
                else if (linea.StartsWith("MemAvailable:")) disponible = Kb(linea);
                if (total is not null && disponible is not null) break;
            }
            return total is { } t && disponible is { } d ? (t, d) : null;
        }
        catch { return null; }

        static long Kb(string linea) => long.Parse(linea.Split(' ', StringSplitOptions.RemoveEmptyEntries)[1]) * 1024;
    }

    public long MemoriaDelProceso()
    {
        try { using var p = Process.GetCurrentProcess(); return p.WorkingSet64; }
        catch { return 0; }
    }

    public (long Recibidos, long Enviados)? BytesDeRed()
    {
        long rx = 0, tx = 0;
        var alguna = false;
        try
        {
            foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (nic.OperationalStatus != OperationalStatus.Up || nic.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;
                try
                {
                    var e = nic.GetIPv4Statistics();
                    rx += e.BytesReceived; tx += e.BytesSent; alguna = true;
                }
                catch { /* esta interfaz no da estadísticas (Android las restringe) */ }
            }
        }
        catch { return null; }
        return alguna ? (rx, tx) : null;
    }

    public (long Leidos, long Escritos)? BytesDeDiscoDelProceso()
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                using var p = Process.GetCurrentProcess();
                return GetProcessIoCounters(p.Handle, out var io) ? ((long)io.ReadTransferCount, (long)io.WriteTransferCount) : null;
            }
            long? r = null, w = null;
            foreach (var linea in File.ReadLines("/proc/self/io"))
            {
                if (linea.StartsWith("rchar:")) r = long.Parse(linea[6..].Trim());
                else if (linea.StartsWith("wchar:")) w = long.Parse(linea[6..].Trim());
            }
            return r is { } a && w is { } b ? (a, b) : null;
        }
        catch { return null; }
    }

    public (long Total, long Libre)? Disco(string ruta)
    {
        try
        {
            var raiz = Path.GetPathRoot(Path.GetFullPath(ruta));
            if (string.IsNullOrEmpty(raiz)) return null;
            var d = new DriveInfo(raiz);
            return (d.TotalSize, d.AvailableFreeSpace);
        }
        catch { return null; }
    }

    // ------------------------------------------------------------------ Windows

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoriaEstado
    {
        public uint Largo, CargaMemoria;
        public ulong TotalFisica, DisponibleFisica, TotalArchivoPaginacion, DisponibleArchivoPaginacion, TotalVirtual, DisponibleVirtual, DisponibleVirtualExtendida;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoContadores
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GlobalMemoryStatusEx(ref MemoriaEstado estado);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetProcessIoCounters(IntPtr proceso, out IoContadores io);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetSystemTimes(out ulong inactivo, out ulong nucleo, out ulong usuario);
}
