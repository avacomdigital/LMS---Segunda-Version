using System.Security.Cryptography;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// <see cref="IProveedorDeClave"/> que guarda la clave sólo en memoria: para pruebas y para arrancar una app sin almacén seguro de la plataforma.
/// Con una clave fija (32 bytes) las pruebas obtienen resultados repetibles; sin ella se crea una aleatoria. <see cref="Destruir"/> la cambia por
/// otra aleatoria y así lo cifrado con la anterior queda ilegible, igual que con la clave de Student (SecureStorage en Android, DPAPI en Windows).
/// </summary>
public sealed class ProveedorDeClaveEnMemoria : IProveedorDeClave
{
    private readonly object candado = new();
    private byte[] clave;

    public ProveedorDeClaveEnMemoria(byte[]? claveFija = null)
    {
        if (claveFija is not null && claveFija.Length != ArchivoCifrado.LongitudClave)
            throw new ArgumentException($"La clave debe tener {ArchivoCifrado.LongitudClave} bytes.", nameof(claveFija));
        clave = claveFija is null ? RandomNumberGenerator.GetBytes(ArchivoCifrado.LongitudClave) : (byte[])claveFija.Clone();
    }

    /// <summary>Cuántas veces se destruyó la clave (para que las pruebas comprueben que BR-053 se ejecutó).</summary>
    public int Destrucciones { get; private set; }

    /// <summary>Una COPIA de la clave: quien la recibe puede borrarla de su memoria sin afectar a las demás.</summary>
    public byte[] Obtener()
    {
        lock (candado) return (byte[])clave.Clone();
    }

    public void Destruir()
    {
        lock (candado)
        {
            CryptographicOperations.ZeroMemory(clave);
            clave = RandomNumberGenerator.GetBytes(ArchivoCifrado.LongitudClave);
            Destrucciones++;
        }
    }
}
