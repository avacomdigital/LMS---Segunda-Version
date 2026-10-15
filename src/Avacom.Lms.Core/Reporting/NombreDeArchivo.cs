using System.Globalization;
using System.Text;

namespace Avacom.Lms.Core.Reporting;

/// <summary>
/// El nombre con que se guarda un reporte exportado (MOD-013) y lo que hace falta para no pisar otro. El nombre lo PROPONE el sistema (el equipo del aula no tiene
/// teclado: nadie lo escribe), pero se compone con datos de la escuela (el grupo, la materia, el periodo) y el destino puede ser cualquier unidad: NTFS en el disco,
/// FAT32 o exFAT en una memoria USB, una carpeta de red. Por eso el nombre se SANEA hasta que valga en todos a la vez: sin los caracteres que ninguno admite, sin los
/// nombres que Windows reserva para dispositivos, sin espacios ni puntos que Windows se come al final, y a lo sumo 100 caracteres (el tope deja sitio al «(2)» y a una
/// ruta larga). Es PURO y determinista: la misma entrada da siempre la misma salida, sin mirar la cultura del equipo ni el disco.
/// </summary>
public static class NombreDeArchivo
{
    /// <summary>Largo máximo del nombre COMPLETO (base + extensión), en unidades UTF-16 (lo que cuentan NTFS, FAT32 y exFAT).</summary>
    public const int MaximoDeCaracteres = 100;

    /// <summary>Cuántos nombres distintos se prueban antes de rendirse: el nombre limpio y sus variantes «(2)» a «(999)».</summary>
    public const int MaximoDeVariantes = 999;

    // Lo que no se recorta nunca es la extensión (el sistema operativo abre el archivo por ella), así que ella misma tiene un tope: con él la base conserva siempre
    // al menos 80 caracteres y las cuentas de «cabe / no cabe» no tienen casos absurdos.
    private const int MaximoDeLaExtension = 20;

    // Lo que se pone cuando no queda nada utilizable (nombre vacío, sólo signos) y el prefijo de los nombres reservados.
    private const string Generico = "reporte";

    /// <summary>
    /// Nombres que Windows reserva para dispositivos: no se pueden crear como archivo, y lo son AUNQUE lleven extensión («CON.txt», «NUL.tar.gz»). Se incluyen los de
    /// los puertos con superíndice (COM¹, LPT²…), que Windows 10 también reserva, y los dos del servicio de consola.
    /// </summary>
    private static readonly HashSet<string> Reservados = CrearReservados();

    private static HashSet<string> CrearReservados()
    {
        var conjunto = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$" };
        foreach (var digito in "123456789¹²³")
        {
            conjunto.Add("COM" + digito);
            conjunto.Add("LPT" + digito);
        }
        return conjunto;
    }

    // ---------------------------------------------------------------------------------------------------- sanear

    /// <summary>
    /// Devuelve «base.ext» válido en cualquier sistema de archivos. A la base: cada <c>\ / : * ? " &lt; &gt; |</c> y cada control (los de 0x00 a 0x1F y 0x7F a 0x9F) pasa a
    /// «-», igual que lo que no es texto (un sustituto UTF-16 suelto, los «no caracteres» de Unicode); los espacios raros (el no separable, los de ancho fijo) pasan a un
    /// espacio normal y los invisibles de formato (marca de bytes, control de dirección, ancho cero) se quitan; se colapsan los espacios y los guiones repetidos; se
    /// recortan los espacios y puntos del inicio y del final (Windows se los comería y el nombre que se crea ya no sería el que se propuso); un nombre reservado de
    /// Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9, con o sin extensión) se prefija con «reporte-»; y si no queda nada con sentido —vacío o sólo separadores— se usa
    /// <paramref name="respaldo"/>. Las tildes y la eñe SE CONSERVAN (son válidas en los tres sistemas), pero el texto se normaliza a la forma FormC para que «é» sea siempre
    /// un solo carácter. La extensión (con o sin punto) se deja en minúsculas con un solo punto inicial y pasa por la misma limpieza; si la base ya la trae al final
    /// («informe.xlsx» con «.xlsx») no se repite. El TOTAL nunca pasa de <see cref="MaximoDeCaracteres"/>: se recorta la base (nunca la extensión) y sin partir un par
    /// sustituto UTF-16 ni una letra de su tilde. Sanear es ESTABLE: un nombre que ya salió de aquí vuelve a salir igual.
    /// </summary>
    public static string Sanear(string? propuesto, string extension = "", string respaldo = "reporte")
    {
        var ext = NormalizarExtension(extension);
        var cupo = MaximoDeCaracteres - ext.Length;

        var nombre = Limpiar(propuesto);
        // «informe.xlsx» pedido con la extensión «.xlsx»: la extensión no se pone dos veces.
        if (ext.Length > 0 && nombre.Length > ext.Length && nombre.EndsWith(ext, StringComparison.OrdinalIgnoreCase))
            nombre = Retocar(nombre[..^ext.Length]);
        if (nombre.Length == 0) nombre = Limpiar(respaldo);
        if (nombre.Length == 0) nombre = Generico;

        return Ajustar(nombre, cupo) + ext;
    }

    /// <summary>La base ya limpia, dentro del cupo y sin ser un nombre reservado. Cada paso puede deshacer lo del anterior (recortar deja un punto al final, prefijar alarga), por eso se repasa.</summary>
    private static string Ajustar(string nombre, int cupo)
    {
        var b = Retocar(Recortar(nombre, cupo));
        if (b.Length == 0) b = Generico;
        // Se mira DESPUÉS de recortar: «CONe» + 200 marcas combinadas se queda en «CON» al caber, y ese sí es un dispositivo.
        if (EsReservado(b)) b = Retocar(Recortar(Generico + "-" + b, cupo));
        return b.Length == 0 || EsReservado(b) ? Generico : b;
    }

    /// <summary>
    /// ¿Windows lo trata como dispositivo? Cuenta lo que hay ANTES del primer punto, sin los espacios finales: «con», «Nul.txt», «COM1.backup» y «CON .x» lo son; «CONSOLA»,
    /// «COM10» y «LPT» no.
    /// </summary>
    private static bool EsReservado(string nombre)
    {
        var punto = nombre.IndexOf('.');
        var primero = (punto >= 0 ? nombre[..punto] : nombre).TrimEnd(' ');
        return Reservados.Contains(primero);
    }

    // ---------------------------------------------------------------------------------------------------- limpieza de texto

    /// <summary>Limpia y recorta lo que sobra a los lados. Vacío si no queda nada con sentido.</summary>
    private static string Limpiar(string? texto) => Retocar(LimpiarCaracteres(texto));

    /// <summary>
    /// Los pasos que comparten la base y la extensión, sin tocar los lados: lo que no es texto válido fuera, carácter por carácter la tabla de sustituciones con los espacios y
    /// guiones repetidos colapsados sobre la marcha, y por ÚLTIMO la normalización FormC. Va al final a propósito: quitar un invisible o cambiar un carácter deja pegadas dos
    /// piezas que antes no lo estaban («e» + ancho cero + tilde pasa a «e» + tilde, que SÍ se compone en «é»); normalizar antes dejaría un texto que ya no estaría en FormC.
    /// </summary>
    private static string LimpiarCaracteres(string? texto)
    {
        if (string.IsNullOrEmpty(texto)) return string.Empty;

        var salida = new StringBuilder(texto.Length);
        foreach (var rune in SinCaracteresInvalidos(texto).EnumerateRunes())
        {
            // Los separadores (el guion, que es el que sustituye a lo prohibido, y el espacio, al que se llevan todos los espacios raros) pasan por el mismo colador para
            // que se colapsen entre sí aunque unos vengan escritos y otros sustituidos: «a/-b» y «a--b» son los dos «a-b».
            char? separador = null;
            if (Rune.IsControl(rune) || EsCaracterProhibido(rune) || rune.Value == '-') separador = '-';
            else if (Rune.GetUnicodeCategory(rune) == UnicodeCategory.Format) continue;       // invisibles: no dejan rastro ni separan nada
            else if (Rune.IsWhiteSpace(rune)) separador = ' ';

            if (separador is { } c)
            {
                if (salida.Length > 0 && salida[^1] == c) continue;
                salida.Append(c);
            }
            else
            {
                salida.Append(rune.ToString());
            }
        }
        return Normalizar(salida.ToString());
    }

    /// <summary>Los caracteres que NTFS, FAT32 y exFAT no admiten en un nombre (los controles se tratan aparte).</summary>
    private static bool EsCaracterProhibido(Rune rune) => rune.Value is '\\' or '/' or ':' or '*' or '?' or '"' or '<' or '>' or '|';

    /// <summary>
    /// Lo que no es texto: un sustituto UTF-16 sin su pareja y los «no caracteres» de Unicode (U+FFFE, U+FFFF, U+FDD0 a U+FDEF y los equivalentes de cada plano). Se cambian por
    /// «-» ANTES de normalizar (normalizar los rechaza: con U+FFFE lanza) y así el recorte tampoco puede partir un par ni dejar medio carácter.
    /// </summary>
    private static string SinCaracteresInvalidos(string texto)
    {
        var salida = new StringBuilder(texto.Length);
        for (var i = 0; i < texto.Length; i++)
        {
            var c = texto[i];
            if (char.IsHighSurrogate(c) && i + 1 < texto.Length && char.IsLowSurrogate(texto[i + 1]))
            {
                var bajo = texto[++i];
                if (EsNoCaracter(char.ConvertToUtf32(c, bajo))) salida.Append('-');
                else salida.Append(c).Append(bajo);
            }
            else if (char.IsSurrogate(c) || EsNoCaracter(c))
            {
                salida.Append('-');
            }
            else
            {
                salida.Append(c);
            }
        }
        return salida.ToString();
    }

    private static bool EsNoCaracter(int puntoDeCodigo) => puntoDeCodigo is >= 0xFDD0 and <= 0xFDEF || (puntoDeCodigo & 0xFFFE) == 0xFFFE;

    /// <summary>FormC: «e» + acento suelto pasa a «é». Si el texto trae algo que ni la normalización acepta, se deja como está (ya pasó por la limpieza de lo que no es texto).</summary>
    private static string Normalizar(string texto)
    {
        try { return texto.Normalize(NormalizationForm.FormC); }
        catch (ArgumentException) { return texto; }
    }

    /// <summary>
    /// Recorta los espacios y puntos de los lados (un nombre no puede empezar ni terminar así) y deja VACÍO lo que sólo tiene separadores: «---» o «. .» no dicen nada del
    /// reporte y es más útil el nombre de respaldo que un archivo llamado «-».
    /// </summary>
    private static string Retocar(string texto)
    {
        var recortado = texto.Trim(' ', '.');
        return recortado.All(c => c is '-' or ' ' or '.') ? string.Empty : recortado;
    }

    /// <summary>
    /// Cuando mucho <paramref name="maximo"/> unidades UTF-16, cortando por ELEMENTOS DE TEXTO (una letra con sus marcas, un emoji con su secuencia) para no dejar a medias
    /// un par sustituto ni una tilde suelta. Si el primer elemento ya no cabe (una letra con cientos de marcas encima) se corta por puntos de código, para no devolver nada.
    /// </summary>
    private static string Recortar(string texto, int maximo)
    {
        if (texto.Length <= maximo) return texto;
        if (maximo <= 0) return string.Empty;

        var fin = 0;
        while (fin < texto.Length)
        {
            var largo = StringInfo.GetNextTextElementLength(texto.AsSpan(fin));
            if (largo <= 0 || fin + largo > maximo) break;
            fin += largo;
        }
        if (fin == 0)
        {
            fin = Math.Min(maximo, texto.Length);
            if (char.IsHighSurrogate(texto[fin - 1])) fin--;
        }
        return texto[..fin];
    }

    /// <summary>La extensión como se pega al nombre: «» o «.xyz» en minúsculas, limpia, sin puntos ni espacios al final y con tope de largo.</summary>
    private static string NormalizarExtension(string? extension)
    {
        var e = Retocar(LimpiarCaracteres(extension).TrimStart('.', ' '));
        if (e.Length == 0) return string.Empty;
        e = Retocar(Recortar(e.ToLowerInvariant(), MaximoDeLaExtension - 1));
        return e.Length == 0 ? string.Empty : "." + e;
    }

    // ---------------------------------------------------------------------------------------------------- variantes «(2)», «(3)»…

    /// <summary>
    /// «reporte-grupo-8A.xlsx» con 2 da «reporte-grupo-8A (2).xlsx». El «(n)» va antes de la extensión y el total sigue dentro de <see cref="MaximoDeCaracteres"/>: si no cabe se
    /// recorta la base. Con <paramref name="numero"/> menor que 2 es el nombre sin cambios (la primera variante es el nombre mismo).
    /// </summary>
    public static string ConSufijo(string nombreSeguro, int numero)
    {
        ArgumentNullException.ThrowIfNull(nombreSeguro);
        if (numero < 2) return nombreSeguro;

        var sufijo = " (" + numero.ToString(CultureInfo.InvariantCulture) + ")";
        var (nombre, extension) = SepararExtension(nombreSeguro);
        var cupo = Math.Max(1, MaximoDeCaracteres - extension.Length - sufijo.Length);
        var b = Recortar(nombre, cupo).TrimEnd(' ', '.');          // recortar puede dejar un espacio al final y saldría «base  (2)»
        if (b.Length == 0) b = Generico;
        return b + sufijo + extension;
    }

    /// <summary>
    /// El primer nombre libre: el mismo, o con «(2)», «(3)»… hasta <see cref="MaximoDeVariantes"/>. <paramref name="existe"/> dice si un nombre ya está ocupado en la carpeta.
    /// Lanza <see cref="InvalidOperationException"/> si no hay ninguno libre (ni la persona más constante guarda mil veces el mismo reporte).
    /// </summary>
    public static string Elegir(string nombreSeguro, Func<string, bool> existe)
    {
        ArgumentNullException.ThrowIfNull(nombreSeguro);
        ArgumentNullException.ThrowIfNull(existe);
        for (var n = 1; n <= MaximoDeVariantes; n++)
        {
            var candidato = ConSufijo(nombreSeguro, n);
            if (!existe(candidato)) return candidato;
        }
        throw new InvalidOperationException($"No hay un nombre libre para «{nombreSeguro}» en esa carpeta: ya existen el archivo y sus variantes «(2)» a «({MaximoDeVariantes})».");
    }

    /// <summary>
    /// La base y la extensión (con su punto) de un nombre: se parte en el ÚLTIMO punto, pero sólo si lo que le sigue PARECE una extensión (como mucho 20 caracteres con el punto
    /// y sin espacios; el punto no es el primer ni el último carácter). Un nombre sin extensión pero con un punto dentro («Grupo 8.A de la tarde») no se parte: de lo contrario
    /// su cola, que puede ser larga, se contaría como extensión, no se recortaría nunca y el tope de largo no se podría cumplir.
    /// </summary>
    public static (string Nombre, string Extension) SepararExtension(string nombre)
    {
        ArgumentNullException.ThrowIfNull(nombre);
        var punto = nombre.LastIndexOf('.');
        var parece = punto > 0 && punto < nombre.Length - 1 && nombre.Length - punto <= MaximoDeLaExtension && nombre.IndexOf(' ', punto) < 0;
        return parece ? (nombre[..punto], nombre[punto..]) : (nombre, string.Empty);
    }

    // ---------------------------------------------------------------------------------------------------- rutas

    /// <summary>
    /// ¿La ruta es de red? Las UNC («\\servidor\recurso», también escrita con barras normales o como «\\?\UNC\servidor\recurso»). Las rutas «\\?\C:\…» (disco local con ruta
    /// larga) y «\\.\E:» (dispositivo) empiezan igual y NO lo son. Una letra de unidad mapeada a la red no se distingue por el texto: eso lo decide quien conoce las unidades.
    /// </summary>
    public static bool EsRutaDeRed(string? ruta)
    {
        if (string.IsNullOrWhiteSpace(ruta)) return false;
        var r = ruta.Replace('/', '\\');
        if (!r.StartsWith(@"\\", StringComparison.Ordinal)) return false;
        if (r.StartsWith(@"\\?\", StringComparison.Ordinal) || r.StartsWith(@"\\.\", StringComparison.Ordinal))
            return r.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase);
        return true;
    }
}
