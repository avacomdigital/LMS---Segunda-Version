using Avacom.Lms.Core.Reporting;

namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Adónde va un reporte, a efectos de política y de auditoría. Es lo único que el administrador del colegio puede prohibir (memorias USB, red) y lo que se anota con la
/// exportación: no importa la letra de la unidad sino QUÉ clase de lugar es.
/// </summary>
public enum TipoDeDestino
{
    /// <summary>Una memoria USB o un disco externo: se puede retirar en cualquier momento.</summary>
    Extraible,
    /// <summary>Una carpeta de un disco del equipo (Documentos, Escritorio, Descargas, otra unidad interna).</summary>
    CarpetaLocal,
    /// <summary>Una unidad de red mapeada o una carpeta compartida (\\servidor\recurso).</summary>
    Red,
}

public static class TiposDeDestino
{
    /// <summary>El código que viaja al backend con la exportación («extraible», «carpeta_local», «red»): es un contrato, no se cambia. Se usa como <c>tipo.Codigo()</c> o como <c>TiposDeDestino.Codigo(tipo)</c>.</summary>
    public static string Codigo(this TipoDeDestino tipo) => tipo switch
    {
        TipoDeDestino.Extraible => "extraible",
        TipoDeDestino.CarpetaLocal => "carpeta_local",
        TipoDeDestino.Red => "red",
        _ => throw new ArgumentOutOfRangeException(nameof(tipo), tipo, "No es un tipo de destino conocido."),
    };
}

/// <summary>
/// Lo que el administrador del colegio permite. Por omisión todo. Lo que se prohíbe no aparece en la lista de <see cref="CatalogoDeDestinos"/>, y la pantalla tampoco debe aceptarlo si
/// la persona elige otra carpeta a mano: para saber de qué clase es esa carpeta está <see cref="ClasificadorDeRuta"/>.
/// </summary>
public sealed record PoliticaDeDestinos(bool PermitirExtraibles = true, bool PermitirRed = true);

/// <summary>
/// Un lugar donde se puede guardar el reporte, listo para pintar como tarjeta. <see cref="Id"/> es estable entre búsquedas («unidad:E», «atajo:documentos», «carpeta:&lt;ruta&gt;») y sirve para
/// mantener la selección cuando la lista se refresca. <see cref="Letra"/>, <see cref="LibreBytes"/> y <see cref="TotalBytes"/> sólo las tienen las unidades.
/// </summary>
public sealed record DestinoDeExportacion(string Id, string Nombre, string Ruta, TipoDeDestino Tipo, string? Letra, long? LibreBytes, long? TotalBytes, bool EsAtajo, bool Listo);

/// <summary>
/// La respuesta de <see cref="CatalogoDeDestinos.Buscar"/>. <see cref="HayExtraibles"/> dice si en <see cref="Destinos"/> se ofrece alguna unidad extraíble. La lista NUNCA queda vacía por
/// falta de extraíbles (siguen los atajos): <see cref="Aviso"/> es la frase que explica por qué no hay una memoria (no hay ninguna conectada, o el administrador las desactivó).
/// </summary>
public sealed record ResultadoDeBusqueda(IReadOnlyList<DestinoDeExportacion> Destinos, bool HayExtraibles, bool ExtraiblesOcultosPorPolitica, string? Aviso);

/// <summary>Las frases con que se explica la política y la falta de memorias. Constantes para que la pantalla y las pruebas digan lo mismo.</summary>
public static class AvisosDeDestinos
{
    public const string SinExtraibles = "Conecta una memoria USB y toca Buscar de nuevo.";
    public const string ExtraiblesDesactivados = "El administrador del colegio desactivó guardar reportes en memorias USB.";
    /// <summary>No sale en <see cref="ResultadoDeBusqueda.Aviso"/> (ahí sólo cabe una frase y es la de las memorias): es para la pantalla cuando se rechaza una carpeta de red elegida a mano.</summary>
    public const string RedDesactivada = "El administrador del colegio desactivó guardar reportes en carpetas de red.";
}

/// <summary>Las carpetas de siempre del usuario de Windows. Null si no existe o no se pudo saber. Las pruebas ponen unas falsas.</summary>
public interface ICarpetasConocidas
{
    string? Documentos { get; }
    string? Escritorio { get; }
    string? Descargas { get; }
}

/// <summary>
/// Las carpetas conocidas según Windows. Sólo se devuelven las que EXISTEN. Si Documentos está redirigida a un servidor que no contesta, comprobar que existe puede tardar mucho:
/// la comprobación tiene plazo y, si no contesta, la carpeta no se ofrece.
/// </summary>
public sealed class CarpetasConocidasDelSistema : ICarpetasConocidas
{
    private static readonly TimeSpan Plazo = TimeSpan.FromSeconds(2);

    public string? Documentos => ConocidaQueExiste(() => Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments));

    public string? Escritorio => ConocidaQueExiste(() => Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory));

    /// <summary>La carpeta «Downloads» del perfil, si existe. (No hay una carpeta especial de .NET para las descargas.)</summary>
    public string? Descargas => ConocidaQueExiste(() =>
    {
        var perfil = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        return string.IsNullOrWhiteSpace(perfil) ? null : Path.Combine(perfil, "Downloads");
    });

    private static string? ConocidaQueExiste(Func<string?> ruta)
    {
        try
        {
            var r = ruta();
            return !string.IsNullOrWhiteSpace(r) && Existencia.DeCarpeta(r, Plazo) ? r : null;
        }
        catch
        {
            return null;
        }
    }
}

/// <summary>
/// Comprobar que una carpeta existe PUEDE no volver nunca pronto: una ruta de red cuyo servidor está apagado, o una unidad mapeada desconectada, hacen esperar a Windows decenas de
/// segundos. Aquí la comprobación tiene plazo; si no contesta a tiempo se toma por «no está» (la tarea que se quedó esperando termina sola cuando Windows se rinda).
/// </summary>
internal static class Existencia
{
    public static bool DeCarpeta(string? ruta, TimeSpan plazo) => DeCarpeta(ruta, plazo, Directory.Exists);

    /// <summary>La costura de las pruebas: «cómo se comprueba» (una que se cuelga, una que lanza).</summary>
    public static bool DeCarpeta(string? ruta, TimeSpan plazo, Func<string, bool> existe)
    {
        if (string.IsNullOrWhiteSpace(ruta)) return false;
        try
        {
            var tarea = Task.Run(() => existe(ruta));
            return tarea.Wait(plazo) && tarea.Result;
        }
        catch
        {
            return false;
        }
    }
}

/// <summary>
/// La lista de lugares donde se puede guardar un reporte: primero los atajos del usuario (Documentos, Escritorio, Descargas), luego las unidades extraíbles, las internas y las de
/// red. Aplica la política del administrador. No toca el disco por su cuenta (eso lo hacen el proveedor de unidades y el de carpetas) y nunca lanza: lo que no se pudo leer
/// simplemente no aparece. Leer las unidades puede tardar un poco si hay una de red desconectada: llamarlo fuera del hilo de la pantalla.
/// </summary>
public sealed class CatalogoDeDestinos
{
    private readonly IProveedorDeUnidades _unidades;
    private readonly ICarpetasConocidas _carpetas;
    private readonly PoliticaDeDestinos _politica;

    public CatalogoDeDestinos(IProveedorDeUnidades unidades, ICarpetasConocidas carpetas, PoliticaDeDestinos politica)
    {
        _unidades = unidades ?? throw new ArgumentNullException(nameof(unidades));
        _carpetas = carpetas ?? throw new ArgumentNullException(nameof(carpetas));
        _politica = politica ?? throw new ArgumentNullException(nameof(politica));
    }

    public ResultadoDeBusqueda Buscar()
    {
        var unidades = LeerUnidades();
        var destinos = new List<DestinoDeExportacion>();
        var rutasVistas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // 1. Los atajos. Si Documentos está redirigida a un recurso compartido (se ve en las redes de colegios con dominio) cuenta como RED y sigue la política de la red.
        foreach (var (id, nombre, ruta) in Atajos())
        {
            if (string.IsNullOrWhiteSpace(ruta)) continue;
            var tipo = ClasificadorDeRuta.ClasificarConLista(ruta, unidades);
            if (!Permitido(tipo) || !rutasVistas.Add(ParaComparar(ruta))) continue;
            destinos.Add(new DestinoDeExportacion(id, nombre, ruta, tipo, null, null, null, EsAtajo: true, Listo: true));
        }

        // 2. Las unidades, en este orden: extraíbles, internas, de red. Una que no está lista (un lector vacío) no se ofrece; las ópticas, de RAM y sin raíz tampoco.
        var listas = unidades.Where(u => u.Lista && !string.IsNullOrWhiteSpace(u.Raiz)).ToList();
        foreach (var (tipoDeUnidad, tipoDeDestino) in new[]
        {
            (TipoDeUnidad.Extraible, TipoDeDestino.Extraible),
            (TipoDeUnidad.Fija, TipoDeDestino.CarpetaLocal),
            (TipoDeUnidad.Red, TipoDeDestino.Red),
        })
        {
            if (!Permitido(tipoDeDestino)) continue;
            foreach (var u in listas.Where(u => u.TipoEfectivo == tipoDeUnidad).OrderBy(u => u.Raiz, StringComparer.OrdinalIgnoreCase))
                if (rutasVistas.Add(ParaComparar(u.Raiz)))
                    destinos.Add(Unidad(u, tipoDeDestino));
        }

        var hayExtraibles = destinos.Any(d => d.Tipo == TipoDeDestino.Extraible);
        var aviso = !_politica.PermitirExtraibles ? AvisosDeDestinos.ExtraiblesDesactivados
                  : !hayExtraibles ? AvisosDeDestinos.SinExtraibles
                  : null;
        return new ResultadoDeBusqueda(destinos, hayExtraibles, !_politica.PermitirExtraibles, aviso);
    }

    private bool Permitido(TipoDeDestino tipo) => tipo switch
    {
        TipoDeDestino.Extraible => _politica.PermitirExtraibles,
        TipoDeDestino.Red => _politica.PermitirRed,
        _ => true,
    };

    private IReadOnlyList<UnidadInfo> LeerUnidades()
    {
        try { return _unidades.Unidades() ?? []; }
        catch { return []; }
    }

    private IEnumerable<(string Id, string Nombre, string? Ruta)> Atajos()
    {
        yield return ("atajo:documentos", "Documentos", Seguro(() => _carpetas.Documentos));
        yield return ("atajo:escritorio", "Escritorio", Seguro(() => _carpetas.Escritorio));
        yield return ("atajo:descargas", "Descargas", Seguro(() => _carpetas.Descargas));
    }

    private static string? Seguro(Func<string?> leer)
    {
        try { return leer(); }
        catch { return null; }
    }

    private static DestinoDeExportacion Unidad(UnidadInfo u, TipoDeDestino tipo)
    {
        var letra = u.Letra;
        var nombre = !string.IsNullOrWhiteSpace(u.Etiqueta)
            ? u.Etiqueta.Trim()
            : $"{(tipo switch { TipoDeDestino.Extraible => "Memoria USB", TipoDeDestino.Red => "Unidad de red", _ => "Disco local" })} ({letra ?? u.Raiz})";
        var id = letra is null ? $"carpeta:{u.Raiz}" : $"unidad:{letra[0]}";
        return new DestinoDeExportacion(id, nombre, u.Raiz, tipo, letra, u.LibreBytes, u.TotalBytes, EsAtajo: false, Listo: u.Lista);
    }

    /// <summary>La ruta sin la barra final y sin distinguir mayúsculas: dos atajos que apuntan a la misma carpeta no salen dos veces.</summary>
    private static string ParaComparar(string ruta)
    {
        try { return Path.TrimEndingDirectorySeparator(ruta.Trim()); }
        catch { return ruta; }
    }
}

/// <summary>
/// De qué clase de lugar es una ruta cualquiera. Sirve para la opción «Elegir otra carpeta…» (el selector de Windows deja elegir lo que sea y la política tiene que valer también
/// para eso): una ruta UNC es de red; una con letra de unidad es lo que sea esa unidad (una memoria USB, un disco, una unidad de red mapeada); una relativa o de una unidad que
/// no se conoce se toma por una carpeta local.
/// </summary>
public static class ClasificadorDeRuta
{
    public static TipoDeDestino Clasificar(string ruta, IProveedorDeUnidades unidades)
    {
        if (string.IsNullOrWhiteSpace(ruta)) return TipoDeDestino.CarpetaLocal;
        if (NombreDeArchivo.EsRutaDeRed(ruta)) return TipoDeDestino.Red;
        if (LetraDe(ruta) is null) return TipoDeDestino.CarpetaLocal;          // relativa o rara: no hace falta preguntarle nada a las unidades

        IReadOnlyList<UnidadInfo> lista;
        try { lista = unidades?.Unidades() ?? []; }
        catch { return TipoDeDestino.CarpetaLocal; }
        return ClasificarConLista(ruta, lista);
    }

    /// <summary>Lo mismo con las unidades ya leídas (el catálogo las tiene y no hay por qué volver a preguntar).</summary>
    internal static TipoDeDestino ClasificarConLista(string ruta, IReadOnlyList<UnidadInfo> unidades)
    {
        if (string.IsNullOrWhiteSpace(ruta)) return TipoDeDestino.CarpetaLocal;
        if (NombreDeArchivo.EsRutaDeRed(ruta)) return TipoDeDestino.Red;
        var letra = LetraDe(ruta);
        if (letra is null) return TipoDeDestino.CarpetaLocal;

        var unidad = unidades.FirstOrDefault(u => string.Equals(u.Letra, letra, StringComparison.OrdinalIgnoreCase));
        return unidad?.TipoEfectivo switch
        {
            TipoDeUnidad.Extraible => TipoDeDestino.Extraible,
            TipoDeUnidad.Red => TipoDeDestino.Red,
            _ => TipoDeDestino.CarpetaLocal,
        };
    }

    /// <summary>«E:» de «E:\Reportes», «e:reportes» o «\\?\E:\Reportes»; null si la ruta no empieza por una letra de unidad.</summary>
    private static string? LetraDe(string ruta)
    {
        var r = ruta.StartsWith(@"\\?\", StringComparison.Ordinal) ? ruta[4..] : ruta;
        return r.Length >= 2 && char.IsAsciiLetter(r[0]) && r[1] == ':' ? char.ToUpperInvariant(r[0]) + ":" : null;
    }
}
