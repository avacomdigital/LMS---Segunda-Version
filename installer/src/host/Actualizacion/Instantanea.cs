using System.Text.Json;

namespace Avacom.Ops.Host.Actualizacion;

internal sealed record EntradaDeInstantanea(string Ruta, bool Existia, string? Sha256, long Bytes);

/// <summary>
/// La instantanea del codigo que un paquete va a cambiar (P-07, C-7): <c>Actualizaciones\versiones\&lt;paquete&gt;\anterior\&lt;ruta&gt;</c> con cada archivo que EXISTIA en Backend\,
/// y <c>_indice.json</c> (que archivos existian y con que huella, la version del producto y la fecha). El indice se escribe AL FINAL y de forma atomica: una instantanea
/// sin indice esta a medias y no vale (el codigo no se habia tocado todavia). Se conserva 14 dias (P-09) y el instalador completo no la borra (P-17).
///
/// <c>posterior</c> es lo mismo, para una reversion manual: el codigo de ahora, por si hay que deshacer la reversion.
/// </summary>
internal sealed class Instantanea
{
    public const string NombreDelIndice = "_indice.json";

    private readonly string _carpeta;

    public Instantanea(string carpeta) => _carpeta = carpeta;

    public string Carpeta => _carpeta;
    private string RutaDelIndice => Path.Combine(_carpeta, NombreDelIndice);

    public sealed record Indice(string PaqueteId, string Producto, long CreadoEn, IReadOnlyList<EntradaDeInstantanea> Entradas);

    public bool Completa => Leer() is not null;

    public Indice? Leer()
    {
        try
        {
            if (!File.Exists(RutaDelIndice)) return null;
            using var documento = JsonDocument.Parse(File.ReadAllText(RutaDelIndice));
            var raiz = documento.RootElement;
            var entradas = new List<EntradaDeInstantanea>();
            foreach (var e in raiz.GetProperty("archivos").EnumerateArray())
            {
                var existia = e.GetProperty("existia").GetBoolean();
                entradas.Add(new EntradaDeInstantanea(
                    e.GetProperty("ruta").GetString() ?? "",
                    existia,
                    existia ? e.GetProperty("sha256").GetString() : null,
                    existia ? e.GetProperty("bytes").GetInt64() : 0));
            }
            return new Indice(raiz.GetProperty("paquete_id").GetString() ?? "", raiz.GetProperty("producto").GetString() ?? "",
                raiz.GetProperty("creado_en").GetInt64(), entradas);
        }
        catch (Exception error) when (error is IOException or JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            return null;
        }
    }

    /// <summary>
    /// Copia a la instantanea cada archivo de <paramref name="rutas"/> que exista hoy en Backend\ (verificando lo escrito) y deja el indice. Antes de empezar borra
    /// cualquier resto de un intento cortado: el codigo todavia es el original, asi que repetirla es seguro.
    /// </summary>
    public void Crear(Registro registro, string paqueteId, string producto, IEnumerable<string> rutas, Action<int>? avance = null)
    {
        Disco.BorrarCarpeta(_carpeta);
        Directory.CreateDirectory(_carpeta);
        var lista = rutas.ToList();
        var entradas = new List<object>();
        for (var i = 0; i < lista.Count; i++)
        {
            var ruta = lista[i];
            var origen = Disco.Confinar(Rutas.CarpetaBackend, ruta);
            if (File.Exists(origen))
            {
                var sha = Disco.Sha256DeArchivo(origen);
                Disco.CopiarVerificado(origen, Disco.Confinar(_carpeta, ruta), sha);
                entradas.Add(new { ruta, existia = true, sha256 = sha, bytes = new FileInfo(origen).Length });
            }
            else
            {
                entradas.Add(new { ruta, existia = false });
            }
            avance?.Invoke((i + 1) * 100 / Math.Max(1, lista.Count));
        }
        var indice = new { formato = 1, paquete_id = paqueteId, producto, creado_en = Disco.Ahora(), archivos = entradas };
        Disco.EscribirAtomico(RutaDelIndice, JsonSerializer.Serialize(indice, new JsonSerializerOptions { WriteIndented = true }));
        registro.Escribir($"Instantanea de {lista.Count} archivo(s) en {_carpeta}.");
    }

    /// <summary>
    /// Deja Backend\ como estaba al tomar la instantanea: restaura lo que existia (con su huella) y borra lo que no existia. Es idempotente: se puede repetir tras un corte.
    /// </summary>
    public int Restaurar(Registro registro)
    {
        var indice = Leer() ?? throw new IOException($"La instantanea de {_carpeta} esta incompleta: no se puede volver atras desde ella.");
        var cambios = 0;
        foreach (var entrada in indice.Entradas)
        {
            var destino = Disco.Confinar(Rutas.CarpetaBackend, entrada.Ruta);
            if (entrada.Existia)
            {
                if (File.Exists(destino) && string.Equals(Disco.Sha256DeArchivo(destino), entrada.Sha256, StringComparison.OrdinalIgnoreCase)) continue;
                Disco.CopiarVerificado(Disco.Confinar(_carpeta, entrada.Ruta), destino, entrada.Sha256!);
                cambios++;
            }
            else if (File.Exists(destino))
            {
                File.Delete(destino);
                Disco.PodarVacias(Path.GetDirectoryName(destino)!, Rutas.CarpetaBackend);
                cambios++;
            }
        }
        registro.Escribir($"Codigo restaurado desde {_carpeta}: {cambios} archivo(s) cambiados de {indice.Entradas.Count}.");
        return cambios;
    }
}
