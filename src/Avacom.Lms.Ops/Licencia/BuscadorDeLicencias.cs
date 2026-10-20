using System.Security.Cryptography;
using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Ops.Reportes;

namespace Avacom.Lms.Ops.Licencia;

/// <summary>Un archivo visto en una carpeta: su ruta completa, cuánto mide y cuándo se escribió por última vez.</summary>
public sealed record ArchivoVisto(string Ruta, long Bytes, DateTime ModificadoUtc);

/// <summary>
/// Lo que el buscador de licencias necesita del sistema de archivos, y nada más: listar los archivos de UNA carpeta (sin bajar a subcarpetas) y leer los primeros bytes o un archivo
/// pequeño entero. Existe para probar sin hardware lo que una memoria real hace: retirarse a mitad, colgarse, traer archivos enormes o basura con la extensión correcta.
/// Cualquier método puede lanzar (la unidad se fue): el buscador lo atrapa y sigue con las demás.
/// </summary>
public interface ILectorDeArchivos
{
    bool ExisteCarpeta(string carpeta);

    /// <summary>Los ARCHIVOS de esa carpeta que coinciden con <paramref name="patron"/> (p. ej. «*.avlic»), sin entrar en subcarpetas.</summary>
    IEnumerable<ArchivoVisto> Archivos(string carpeta, string patron);

    /// <summary>Hasta <paramref name="cuantos"/> bytes del principio del archivo (menos si es más corto).</summary>
    byte[] LeerInicio(string ruta, int cuantos);

    /// <summary>El archivo entero si no pasa de <paramref name="maximo"/> bytes; null si pasa.</summary>
    byte[]? LeerCompleto(string ruta, int maximo);
}

/// <summary>El sistema de archivos de verdad. Abre los archivos para LEER y compartidos: nunca cambia nada de lo que hay en la memoria.</summary>
public sealed class LectorDeArchivosDelSistema : ILectorDeArchivos
{
    private static readonly TimeSpan PlazoParaExistir = TimeSpan.FromSeconds(3);

    public bool ExisteCarpeta(string carpeta) => Existencia.DeCarpeta(carpeta, PlazoParaExistir);

    public IEnumerable<ArchivoVisto> Archivos(string carpeta, string patron)
    {
        var opciones = new EnumerationOptions
        {
            RecurseSubdirectories = false, IgnoreInaccessible = true, MatchCasing = MatchCasing.CaseInsensitive, MatchType = MatchType.Simple,
            AttributesToSkip = FileAttributes.Directory | FileAttributes.System | FileAttributes.Offline,
        };
        foreach (var info in new DirectoryInfo(carpeta).EnumerateFiles(patron, opciones))
            yield return new ArchivoVisto(info.FullName, info.Length, info.LastWriteTimeUtc);
    }

    public byte[] LeerInicio(string ruta, int cuantos)
    {
        using var archivo = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096);
        var bufer = new byte[cuantos];
        var leidos = 0;
        while (leidos < cuantos)
        {
            var n = archivo.Read(bufer, leidos, cuantos - leidos);
            if (n == 0) break;
            leidos += n;
        }
        return leidos == cuantos ? bufer : bufer[..leidos];
    }

    public byte[]? LeerCompleto(string ruta, int maximo)
    {
        using var archivo = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 4096);
        if (archivo.Length > maximo) return null;
        using var memoria = new MemoryStream((int)Math.Max(0, archivo.Length));
        var bufer = new byte[4096];
        int n;
        while ((n = archivo.Read(bufer, 0, bufer.Length)) > 0)
        {
            memoria.Write(bufer, 0, n);
            if (memoria.Length > maximo) return null;               // creció mientras se leía
        }
        return memoria.ToArray();
    }
}

/// <summary>De dónde salió un candidato: la raíz de una unidad, una carpeta conocida del usuario o la última carpeta que se usó para la licencia.</summary>
public enum OrigenDeCandidato { Unidad, Atajo, UltimaCarpeta }

/// <summary>
/// Un archivo de licencia que se puede tocar en el paso 3: dónde está (para decirlo en la tarjeta), su forma (binaria o texto), cuándo se escribió y su SHA-256 (con él se reconoce el
/// mismo archivo en dos lugares y se comprueba, al instalar, que no cambió desde que se listó). OPS no lo verifica ni lo interpreta: lo hace el nodo.
/// </summary>
public sealed record CandidatoDeLicencia(string Ruta, string Nombre, string Carpeta, string Lugar, OrigenDeCandidato Origen, long Bytes, DateTime ModificadoUtc, FormaDeLicencia Forma,
                                         string Sha256, int OtrosLugares = 0)
{
    public long ModificadoMs => new DateTimeOffset(DateTime.SpecifyKind(ModificadoUtc, DateTimeKind.Utc)).ToUnixTimeMilliseconds();
}

/// <summary>Lo que encontró una búsqueda: los candidatos (los más recientes primero, a lo sumo <see cref="BuscadorDeLicencias.Tope"/>) y cuántos lugares se revisaron.</summary>
public sealed record BusquedaDeLicencias(IReadOnlyList<CandidatoDeLicencia> Candidatos, int LugaresRevisados, int LugaresSinRespuesta, int Descartados, bool Recortada)
{
    public bool Vacia => Candidatos.Count == 0;
}

/// <summary>
/// Busca los <c>.avlic</c> que hay en las memorias y carpetas de este equipo para mostrarlos como tarjetas (P-18: no hay selector de archivos ni se pide una ruta). Las reglas, que se
/// prueban con un sistema de archivos falso:
/// <list type="bullet">
/// <item>Sólo la RAÍZ de cada unidad lista (memorias, discos, unidades de red) y de las carpetas conocidas (Documentos, Escritorio, Descargas) y la última carpeta usada; nunca se baja
/// a subcarpetas.</item>
/// <item>Sólo archivos <c>*.avlic</c> de 5 bytes a 16 KiB que empiezan por la marca <c>AVLC</c> (o <c>AVL1.</c>, la forma de texto): para no listar basura. No se verifica la firma.</item>
/// <item>El mismo archivo en dos lugares sale una vez (el más reciente), con cuántos lugares más lo tienen; los más recientes primero; como mucho 50.</item>
/// <item>Una unidad que se retira, que no contesta a tiempo o que no deja leer no tumba la búsqueda: se salta y se sigue.</item>
/// </list>
/// Puede tardar unos segundos si hay una unidad de red caída: llamarlo fuera del hilo de la pantalla. Nunca lanza.
/// </summary>
public sealed class BuscadorDeLicencias
{
    public const int Tope = 50;
    public const string Patron = "*.avlic";
    /// <summary>Cuántos <c>*.avlic</c> se miran como mucho en UNA carpeta (una raíz con miles de archivos no puede colgar la búsqueda).</summary>
    public const int MaximoPorCarpeta = 200;
    public const int TamanoMinimo = 5;

    public static readonly TimeSpan PlazoPorOmision = TimeSpan.FromSeconds(4);

    private readonly IProveedorDeUnidades _unidades;
    private readonly ICarpetasConocidas _carpetas;
    private readonly ILectorDeArchivos _lector;
    private readonly Func<string?> _ultimaCarpeta;
    private readonly TimeSpan _plazoPorCarpeta;

    public BuscadorDeLicencias(IProveedorDeUnidades unidades, ICarpetasConocidas carpetas, ILectorDeArchivos lector, Func<string?>? ultimaCarpeta = null, TimeSpan? plazoPorCarpeta = null)
    {
        _unidades = unidades ?? throw new ArgumentNullException(nameof(unidades));
        _carpetas = carpetas ?? throw new ArgumentNullException(nameof(carpetas));
        _lector = lector ?? throw new ArgumentNullException(nameof(lector));
        _ultimaCarpeta = ultimaCarpeta ?? (() => null);
        _plazoPorCarpeta = plazoPorCarpeta ?? PlazoPorOmision;
    }

    /// <summary>Un lugar donde mirar: la carpeta y cómo se nombra en la tarjeta.</summary>
    internal sealed record Lugar(string Carpeta, string Nombre, OrigenDeCandidato Origen, int Orden);

    /// <summary>Los lugares en el orden en que se miran: unidades (extraíbles, internas y de red), carpetas conocidas y la última usada. Sin repetir una carpeta.</summary>
    internal IReadOnlyList<Lugar> Lugares()
    {
        var lugares = new List<Lugar>();
        var vistas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        void Agregar(string? carpeta, string nombre, OrigenDeCandidato origen)
        {
            if (string.IsNullOrWhiteSpace(carpeta)) return;
            if (!vistas.Add(Normalizar(carpeta))) return;
            lugares.Add(new Lugar(carpeta, nombre, origen, lugares.Count));
        }

        IReadOnlyList<UnidadInfo> unidades;
        try { unidades = _unidades.Unidades() ?? []; }
        catch { unidades = []; }
        foreach (var tipo in new[] { TipoDeUnidad.Extraible, TipoDeUnidad.Fija, TipoDeUnidad.Red })
            foreach (var u in unidades.Where(u => u.Lista && !string.IsNullOrWhiteSpace(u.Raiz) && u.TipoEfectivo == tipo).OrderBy(u => u.Raiz, StringComparer.OrdinalIgnoreCase))
                Agregar(u.Raiz, NombreDeUnidad(u), OrigenDeCandidato.Unidad);

        Agregar(Seguro(() => _carpetas.Documentos), "Documentos", OrigenDeCandidato.Atajo);
        Agregar(Seguro(() => _carpetas.Escritorio), "Escritorio", OrigenDeCandidato.Atajo);
        Agregar(Seguro(() => _carpetas.Descargas), "Descargas", OrigenDeCandidato.Atajo);
        if (Seguro(_ultimaCarpeta) is { } ultima) Agregar(ultima, ultima, OrigenDeCandidato.UltimaCarpeta);
        return lugares;
    }

    /// <summary>«MEMORIA (E:)», o «Memoria USB (E:)», «Disco local (C:)», «Unidad de red (Z:)» si la unidad no tiene etiqueta.</summary>
    internal static string NombreDeUnidad(UnidadInfo u)
    {
        var letra = u.Letra ?? u.Raiz;
        if (!string.IsNullOrWhiteSpace(u.Etiqueta)) return $"{u.Etiqueta.Trim()} ({letra})";
        return u.TipoEfectivo switch
        {
            TipoDeUnidad.Extraible => $"Memoria USB ({letra})",
            TipoDeUnidad.Red => $"Unidad de red ({letra})",
            _ => $"Disco local ({letra})",
        };
    }

    public BusquedaDeLicencias Buscar()
    {
        var lugares = Lugares();
        var hallados = new List<(CandidatoDeLicencia Candidato, int Orden)>();
        var sinRespuesta = 0;
        var descartados = 0;

        foreach (var lugar in lugares)
        {
            // Cada carpeta se mira con plazo: una unidad de red caída o un disco dormido no pueden dejar la pantalla esperando.
            var tarea = Task.Run(() => MirarCarpeta(lugar));
            bool termino;
            try { termino = tarea.Wait(_plazoPorCarpeta); }
            catch { termino = false; }
            if (!termino || !tarea.IsCompletedSuccessfully)
            {
                sinRespuesta++;
                continue;
            }
            var (candidatos, descartadosAqui) = tarea.Result;
            descartados += descartadosAqui;
            hallados.AddRange(candidatos.Select(c => (c, lugar.Orden)));
        }

        // El mismo archivo (mismo contenido) en varios lugares sale una vez: el más reciente, y se dice en cuántos lugares más está.
        var unicos = hallados
            .GroupBy(h => h.Candidato.Sha256, StringComparer.OrdinalIgnoreCase)
            .Select(g =>
            {
                var ordenados = g.OrderByDescending(h => h.Candidato.ModificadoUtc).ThenBy(h => h.Orden).ThenBy(h => h.Candidato.Ruta, StringComparer.OrdinalIgnoreCase).ToList();
                return (Candidato: ordenados[0].Candidato with { OtrosLugares = ordenados.Count - 1 }, ordenados[0].Orden);
            })
            .OrderByDescending(h => h.Candidato.ModificadoUtc)
            .ThenBy(h => h.Orden)
            .ThenBy(h => h.Candidato.Ruta, StringComparer.OrdinalIgnoreCase)
            .Select(h => h.Candidato)
            .ToList();

        return new BusquedaDeLicencias(unicos.Take(Tope).ToList(), lugares.Count, sinRespuesta, descartados, unicos.Count > Tope);
    }

    private (List<CandidatoDeLicencia> Candidatos, int Descartados) MirarCarpeta(Lugar lugar)
    {
        var candidatos = new List<CandidatoDeLicencia>();
        var descartados = 0;
        try
        {
            if (!_lector.ExisteCarpeta(lugar.Carpeta)) return (candidatos, 0);
            foreach (var archivo in _lector.Archivos(lugar.Carpeta, Patron).Take(MaximoPorCarpeta))
            {
                if (Candidato(archivo, lugar) is { } c) candidatos.Add(c);
                else descartados++;
            }
        }
        catch
        {
            // la unidad se retiró a mitad o no deja listar: lo que ya se vio de ella vale, y se sigue con las demás
        }
        return (candidatos, descartados);
    }

    private CandidatoDeLicencia? Candidato(ArchivoVisto archivo, Lugar lugar)
    {
        try
        {
            var nombre = Path.GetFileName(archivo.Ruta);
            if (string.IsNullOrWhiteSpace(nombre) || nombre.StartsWith('.')) return null;                 // los temporales de una escritura a medias empiezan por punto
            if (!nombre.EndsWith(".avlic", StringComparison.OrdinalIgnoreCase)) return null;
            if (archivo.Bytes < TamanoMinimo || archivo.Bytes > MarcaDeLicencia.TamanoMaximo) return null;
            var forma = MarcaDeLicencia.Reconocer(_lector.LeerInicio(archivo.Ruta, MarcaDeLicencia.BytesParaReconocer));
            if (forma == FormaDeLicencia.Desconocida) return null;
            var datos = _lector.LeerCompleto(archivo.Ruta, MarcaDeLicencia.TamanoMaximo);
            if (datos is null || datos.Length < TamanoMinimo || MarcaDeLicencia.Reconocer(datos) == FormaDeLicencia.Desconocida) return null;
            var carpeta = Path.GetDirectoryName(archivo.Ruta) ?? lugar.Carpeta;
            return new CandidatoDeLicencia(archivo.Ruta, nombre, carpeta, lugar.Nombre, lugar.Origen, datos.Length, archivo.ModificadoUtc, forma, Convert.ToHexStringLower(SHA256.HashData(datos)));
        }
        catch
        {
            return null;                                                                                // se retiró justo ahora, o no deja leer: no se lista
        }
    }

    private static string? Seguro(Func<string?> leer)
    {
        try { return leer(); }
        catch { return null; }
    }

    private static string Normalizar(string ruta)
    {
        try { return Path.TrimEndingDirectorySeparator(Path.GetFullPath(ruta.Trim())); }
        catch { return ruta.Trim().TrimEnd('\\', '/'); }
    }
}
