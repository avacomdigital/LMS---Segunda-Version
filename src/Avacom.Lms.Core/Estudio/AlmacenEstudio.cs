using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Estudio;

/// <summary>
/// El almacén local cifrado de MOD-008 (<see cref="IAlmacenEstudio"/>): la lista de pendientes, el avance de cada tarea, los manifiestos y los
/// medios de los paquetes, todo cifrado con la clave que entrega <see cref="IProveedorDeClave"/> (BR-053, BR-054). Nada sale en claro al disco
/// y nada lleva un identificador en su ruta: cada alumno vive en una carpeta cuyo nombre es un hash de su id.
///
/// Disposición bajo la carpeta raíz:
/// <code>
/// a-{hash(alumno)}/lista.avc · tarea-{hash(asignación)}.avc
///                 paquetes/{hash(asignación)}/estado.avc · manifiesto.avc · m-{hash(medio)}.avc (completo) · m-{hash(medio)}.parte (a medias)
/// </code>
/// Los documentos pequeños son <see cref="DocumentoCifrado"/> (con el lugar al que pertenecen como dato asociado: no se pueden cambiar de
/// carpeta) y se escriben de forma atómica; los medios son <see cref="ArchivoCifrado"/> por bloques, con acceso aleatorio y reanudables.
///
/// Si un archivo no se puede descifrar (la clave se destruyó, está corrupto o alterado) se trata como AUSENTE: se aparta como <c>.dañado</c> y
/// nunca se lanza al llamador. Un archivo que no se puede leer ahora mismo (otro proceso lo tiene) no se aparta: puede volver a estar bien.
///
/// Además de <see cref="IAlmacenEstudio"/> expone lo que necesita <see cref="DescargadorDePaquetes"/> para escribir un paquete
/// (<see cref="RegistrarPaquete"/>, <see cref="GuardarManifiesto"/>, <see cref="AbrirEscritura"/>, <see cref="CompletarArchivo"/>…). Hilo-seguro: un
/// único cerrojo protege lo que se lee y se escribe; los medios se leen fuera de él, cada lector con su propio archivo abierto.
/// </summary>
public sealed class AlmacenEstudio : IAlmacenEstudio
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private readonly string raiz;
    private readonly IProveedorDeClave proveedor;
    private readonly Func<long> ahoraNodoMs;
    private readonly Func<long?> espacioLibre;
    private readonly object candado = new();

    /// <param name="raiz">Carpeta donde se guarda todo (en Student, dentro de los datos privados de la app).</param>
    /// <param name="proveedor">Quien guarda la clave.</param>
    /// <param name="ahoraNodoMs">Reloj del nodo para juzgar la vigencia de un paquete (por defecto <see cref="RelojNodo.AhoraMs"/>).</param>
    /// <param name="espacioLibreBytes">Espacio libre del volumen; por defecto el de la unidad de <paramref name="raiz"/>. Las pruebas lo inyectan.</param>
    public AlmacenEstudio(string raiz, IProveedorDeClave proveedor, Func<long>? ahoraNodoMs = null, Func<long?>? espacioLibreBytes = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(raiz);
        this.raiz = Path.GetFullPath(raiz);
        this.proveedor = proveedor ?? throw new ArgumentNullException(nameof(proveedor));
        this.ahoraNodoMs = ahoraNodoMs ?? (() => RelojNodo.AhoraMs);
        espacioLibre = espacioLibreBytes ?? EspacioLibreDelVolumen;
    }

    /// <summary>Cambió algo (lista, tarea o paquete) para el alumno indicado; cadena vacía = cambió todo (se destruyó el almacén).</summary>
    public event Action<string>? Cambio;

    private void Avisar(string alumnoId)
    {
        try { Cambio?.Invoke(alumnoId); }
        catch (Exception) { /* un oyente que falla (la pantalla ya no existe) no debe romper lo que se está guardando */ }
    }

    // ------------------------------------------------------------------------- lo que se guarda en disco

    /// <summary>El estado de un paquete tal como queda en <c>estado.avc</c>: el recibo de lo pedido al nodo y de lo que ya se bajó.</summary>
    private sealed class EstadoPaqueteDisco
    {
        public string AlumnoId { get; set; } = "";
        public string AsignacionId { get; set; } = "";
        public string PaqueteId { get; set; } = "";
        /// <summary>descargando · pausado · disponible · vencido (éste último sólo si el nodo dijo 410; el vencimiento por fecha se deriva al leer).</summary>
        public string Estado { get; set; } = "descargando";
        public long BytesTotal { get; set; }
        public long? VigenteHasta { get; set; }
        public string Huella { get; set; } = "";
        public string? CursoVersion { get; set; }
        public long? DisponibleEn { get; set; }
        public List<ArchivoDisco> Archivos { get; set; } = [];
    }

    private sealed class ArchivoDisco
    {
        public string MediaRef { get; set; } = "";
        public string? Clase { get; set; }
        public string? Mime { get; set; }
        public long Bytes { get; set; }
        public string? Sha256 { get; set; }
        public bool Completo { get; set; }
    }

    // ----------------------------------------------------------------------------------------- rutas

    /// <summary>Un nombre de carpeta o archivo que no revela el identificador: SHA-256 (128 bits, hexadecimal) con un prefijo de dominio.</summary>
    private static string Hash(string valor) =>
        Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes("avacom-estudio|" + valor)))[..32];

    private string CarpetaAlumno(string alumnoId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(alumnoId);
        return Path.Combine(raiz, "a-" + Hash(alumnoId));
    }

    private string RutaLista(string alumnoId) => Path.Combine(CarpetaAlumno(alumnoId), "lista.avc");

    private string RutaTarea(string alumnoId, string asignacionId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(asignacionId);
        return Path.Combine(CarpetaAlumno(alumnoId), "tarea-" + Hash(asignacionId) + ".avc");
    }

    private string CarpetaPaquetes(string alumnoId) => Path.Combine(CarpetaAlumno(alumnoId), "paquetes");

    private string CarpetaPaquete(string alumnoId, string asignacionId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(asignacionId);
        return Path.Combine(CarpetaPaquetes(alumnoId), Hash(asignacionId));
    }

    private string RutaEstado(string alumnoId, string asignacionId) => Path.Combine(CarpetaPaquete(alumnoId, asignacionId), "estado.avc");
    private string RutaManifiesto(string alumnoId, string asignacionId) => Path.Combine(CarpetaPaquete(alumnoId, asignacionId), "manifiesto.avc");

    private string RutaMedio(string alumnoId, string asignacionId, string mediaRef, bool parcial) =>
        Path.Combine(CarpetaPaquete(alumnoId, asignacionId), "m-" + Hash(mediaRef) + (parcial ? ".parte" : ".avc"));

    /// <summary>El lugar al que pertenece un documento: viaja como dato asociado de su cifrado.</summary>
    private static byte[] Contexto(string tipo, params string[] partes) => Encoding.UTF8.GetBytes(tipo + "|" + string.Join('|', partes));

    // -------------------------------------------------------------------- documentos cifrados

    /// <summary>
    /// Lee un documento. Nulo si no existe, si no se puede leer ahora o si no se puede descifrar; en este último caso lo aparta e indica
    /// <paramref name="ilegible"/>.
    /// </summary>
    private byte[]? LeerBytes(string ruta, byte[] contexto, out bool ilegible)
    {
        ilegible = false;
        byte[] sellado;
        try { sellado = File.ReadAllBytes(ruta); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; }
        try { return DocumentoCifrado.Abrir(sellado, proveedor.Obtener(), contexto); }
        catch (Exception ex) when (ex is ArchivoCifradoException or CryptographicException)
        {
            ArchivosLocales.Apartar(ruta);
            ilegible = true;
            return null;
        }
    }

    private T? LeerDocumento<T>(string ruta, byte[] contexto, out bool ilegible) where T : class
    {
        var claro = LeerBytes(ruta, contexto, out ilegible);
        if (claro is null) return null;
        try { return JsonSerializer.Deserialize<T>(claro, Json); }
        catch (JsonException)
        {
            ArchivosLocales.Apartar(ruta);
            ilegible = true;
            return null;
        }
    }

    private void EscribirBytes(string ruta, byte[] claro, byte[] contexto) =>
        ArchivosLocales.EscribirAtomico(ruta, DocumentoCifrado.Sellar(claro, proveedor.Obtener(), contexto));

    private void EscribirDocumento<T>(string ruta, T valor, byte[] contexto) =>
        EscribirBytes(ruta, JsonSerializer.SerializeToUtf8Bytes(valor, Json), contexto);

    // ---------------------------------------------------------------------- la lista de pendientes

    public AsignacionesEstudio? LeerLista(string alumnoId)
    {
        lock (candado) return LeerDocumento<AsignacionesEstudio>(RutaLista(alumnoId), Contexto("lista", alumnoId), out _);
    }

    public void GuardarLista(string alumnoId, AsignacionesEstudio lista)
    {
        ArgumentNullException.ThrowIfNull(lista);
        lock (candado) EscribirDocumento(RutaLista(alumnoId), lista, Contexto("lista", alumnoId));
        Avisar(alumnoId);
    }

    // ------------------------------------------------------------------------- el avance de las tareas

    public TareaLocal? LeerTarea(string alumnoId, string asignacionId)
    {
        lock (candado) return LeerDocumento<TareaLocal>(RutaTarea(alumnoId, asignacionId), Contexto("tarea", alumnoId, asignacionId), out _);
    }

    public void GuardarTarea(string alumnoId, TareaLocal tarea)
    {
        ArgumentNullException.ThrowIfNull(tarea);
        lock (candado) EscribirDocumento(RutaTarea(alumnoId, tarea.AsignacionId), tarea, Contexto("tarea", alumnoId, tarea.AsignacionId));
        Avisar(alumnoId);
    }

    // ------------------------------------------------------------------------------------- paquetes

    /// <summary>El estado guardado de un paquete; nulo si no existe o si estaba ilegible (en ese caso lo bajado ya no sirve y se borra).</summary>
    private EstadoPaqueteDisco? LeerEstado(string alumnoId, string asignacionId)
    {
        var ruta = RutaEstado(alumnoId, asignacionId);
        var e = LeerDocumento<EstadoPaqueteDisco>(ruta, Contexto("estado", alumnoId), out var ilegible);
        if (e is not null && (e.AlumnoId != alumnoId || e.AsignacionId != asignacionId))
        {
            ArchivosLocales.Apartar(ruta);   // un estado que no es de este paquete
            e = null;
            ilegible = true;
        }
        // Sin su estado, los archivos que quedaron no se pueden verificar (no se sabe ni su sha256 ni si están completos): se borran.
        if (ilegible) BorrarCarpeta(CarpetaPaquete(alumnoId, asignacionId));
        return e;
    }

    private void GuardarEstado(EstadoPaqueteDisco e) =>
        EscribirDocumento(RutaEstado(e.AlumnoId, e.AsignacionId), e, Contexto("estado", e.AlumnoId));

    private List<EstadoPaqueteDisco> EstadosDe(string alumnoId)
    {
        var estados = new List<EstadoPaqueteDisco>();
        var carpeta = CarpetaPaquetes(alumnoId);
        if (!Directory.Exists(carpeta)) return estados;
        foreach (var dir in Directory.EnumerateDirectories(carpeta))
        {
            var ruta = Path.Combine(dir, "estado.avc");
            var e = LeerDocumento<EstadoPaqueteDisco>(ruta, Contexto("estado", alumnoId), out var ilegible);
            if (e is not null && (e.AlumnoId != alumnoId || Hash(e.AsignacionId) != Path.GetFileName(dir)))
            {
                ArchivosLocales.Apartar(ruta);
                e = null;
                ilegible = true;
            }
            if (e is not null) estados.Add(e);
            else if (ilegible) BorrarCarpeta(dir);
        }
        return estados;
    }

    private PaqueteLocal Publico(EstadoPaqueteDisco e)
    {
        var vencido = e.Estado == "vencido" || (e.VigenteHasta is { } hasta && ahoraNodoMs() > hasta);
        return new PaqueteLocal(e.AlumnoId, e.AsignacionId, e.PaqueteId, vencido ? "vencido" : e.Estado, e.BytesTotal, BytesBajados(e), e.VigenteHasta, e.Huella, e.CursoVersion);
    }

    private long BytesBajados(EstadoPaqueteDisco e)
    {
        if (e.Estado == "disponible") return e.BytesTotal;
        return e.Archivos.Sum(a => a.Completo ? a.Bytes : BytesParciales(e, a));
    }

    /// <summary>Lo que ya hay a salvo de un archivo a medio bajar (sus bloques completos), sin descifrar nada.</summary>
    private long BytesParciales(EstadoPaqueteDisco e, ArchivoDisco a)
    {
        try
        {
            var parte = new FileInfo(RutaMedio(e.AlumnoId, e.AsignacionId, a.MediaRef, parcial: true));
            return parte.Exists ? Math.Min(a.Bytes, ArchivoCifrado.BytesDeBloquesCompletos(parte.Length)) : 0;
        }
        catch (IOException) { return 0; }
    }

    public IReadOnlyList<PaqueteLocal> ListarPaquetes(string alumnoId)
    {
        lock (candado) return EstadosDe(alumnoId).Select(Publico).OrderBy(p => p.AsignacionId, StringComparer.Ordinal).ToList();
    }

    public PaqueteLocal? ObtenerPaquete(string alumnoId, string asignacionId)
    {
        lock (candado) return LeerEstado(alumnoId, asignacionId) is { } e ? Publico(e) : null;
    }

    /// <summary>
    /// El manifiesto de un paquete DISPONIBLE, releído tal como llegó. Nulo si no está o si el paquete aún no está completo. Un paquete que
    /// dice estar completo pero cuyo manifiesto no se puede leer deja de estar disponible: el próximo intento de descarga lo rehace
    /// (baja el manifiesto otra vez y conserva los archivos que sigan valiendo). El vencimiento por fecha NO lo impide: eso lo decide quien
    /// mira <see cref="PaqueteLocal.Estado"/> y <see cref="LiberarVencidos"/>.
    /// </summary>
    public ManifiestoPaquete? LeerManifiesto(string alumnoId, string asignacionId)
    {
        var cambio = false;
        try
        {
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId);
                if (e is not { Estado: "disponible" }) return null;
                var claro = LeerBytes(RutaManifiesto(alumnoId, asignacionId), Contexto("manifiesto", alumnoId, asignacionId), out _);
                if (claro is not null)
                {
                    try { return JsonSerializer.Deserialize<ManifiestoPaquete>(claro, Json); }
                    catch (JsonException) { ArchivosLocales.Apartar(RutaManifiesto(alumnoId, asignacionId)); }
                }
                e.Estado = "pausado";
                GuardarEstado(e);
                cambio = true;
                return null;
            }
        }
        finally
        {
            if (cambio) Avisar(alumnoId);
        }
    }

    /// <summary>El texto del manifiesto tal como llegó del nodo (aunque el paquete aún se esté descargando); nulo si no está guardado.</summary>
    public string? LeerManifiestoCrudo(string alumnoId, string asignacionId)
    {
        lock (candado)
        {
            var claro = LeerBytes(RutaManifiesto(alumnoId, asignacionId), Contexto("manifiesto", alumnoId, asignacionId), out _);
            return claro is null ? null : Encoding.UTF8.GetString(claro);
        }
    }

    /// <summary>
    /// El archivo íntegro de un medio: marcado como completo y con el tamaño en disco EXACTO que le corresponde (el formato es determinista, así
    /// que un archivo truncado o alargado se nota). Si estaba marcado pero ya no cumple, se invalida —el paquete deja de estar disponible— para
    /// que la próxima descarga lo baje otra vez.
    /// </summary>
    private ArchivoDisco? ArchivoCompleto(EstadoPaqueteDisco e, string mediaRef, ref bool cambio)
    {
        var a = e.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef);
        if (a is not { Completo: true }) return null;
        var ruta = RutaMedio(e.AlumnoId, e.AsignacionId, mediaRef, parcial: false);
        try
        {
            var info = new FileInfo(ruta);
            if (info.Exists && info.Length == ArchivoCifrado.LongitudDelArchivo(a.Bytes)) return a;
        }
        catch (IOException) { return null; }
        Invalidar(e, a);
        cambio = true;
        return null;
    }

    private void Invalidar(EstadoPaqueteDisco e, ArchivoDisco a)
    {
        BorrarMedio(e, a);
        a.Completo = false;
        if (e.Estado == "disponible") e.Estado = "pausado";
        GuardarEstado(e);
    }

    public (long Longitud, string? Mime)? InfoArchivo(string alumnoId, string asignacionId, string mediaRef)
    {
        var cambio = false;
        try
        {
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId);
                if (e is not { Estado: "disponible" }) return null;
                return ArchivoCompleto(e, mediaRef, ref cambio) is { } a ? (a.Bytes, a.Mime) : null;
            }
        }
        finally
        {
            if (cambio) Avisar(alumnoId);
        }
    }

    public Stream? AbrirArchivo(string alumnoId, string asignacionId, string mediaRef)
    {
        string ruta;
        var cambio = false;
        try
        {
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId);
                if (e is not { Estado: "disponible" }) return null;
                if (ArchivoCompleto(e, mediaRef, ref cambio) is null) return null;
                ruta = RutaMedio(alumnoId, asignacionId, mediaRef, parcial: false);
            }
        }
        finally
        {
            if (cambio) Avisar(alumnoId);
        }

        try { return ArchivoCifrado.AbrirLectura(ruta, proveedor.Obtener()); }
        catch (ArchivoCifradoException)
        {
            // Ilegible con la clave de hoy (se destruyó o el archivo cambió): lo bajado ya no sirve, la próxima descarga lo repone.
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId);
                var a = e?.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef);
                if (e is not null && a is not null) Invalidar(e, a);
            }
            Avisar(alumnoId);
            return null;
        }
        catch (IOException) { return null; }   // lo borró otro hilo mientras tanto: para quien pregunta es como si no estuviera
    }

    public void EliminarPaquete(string alumnoId, string asignacionId)
    {
        lock (candado) BorrarCarpeta(CarpetaPaquete(alumnoId, asignacionId));
        Avisar(alumnoId);
    }

    public (int Paquetes, long Bytes) LiberarVencidos(string alumnoId, long ahoraNodoMs)
    {
        var paquetes = 0;
        long bytes = 0;
        lock (candado)
        {
            foreach (var e in EstadosDe(alumnoId))
            {
                if (!(e.Estado == "vencido" || (e.VigenteHasta is { } hasta && ahoraNodoMs > hasta))) continue;
                var carpeta = CarpetaPaquete(alumnoId, e.AsignacionId);
                var ocupado = TamanoDe(carpeta);
                BorrarCarpeta(carpeta);
                if (Directory.Exists(carpeta)) continue;   // no se pudo borrar (un visor lo tiene abierto): se intentará la próxima vez
                paquetes++;
                bytes += ocupado;
            }
        }
        if (paquetes > 0) Avisar(alumnoId);
        return (paquetes, bytes);
    }

    public long BytesUsados(string alumnoId)
    {
        lock (candado) return TamanoDe(CarpetaAlumno(alumnoId));
    }

    public long? EspacioLibreBytes() => espacioLibre();

    public void OlvidarAlumno(string alumnoId)
    {
        lock (candado) BorrarCarpeta(CarpetaAlumno(alumnoId));
        Avisar(alumnoId);
    }

    public void Destruir()
    {
        // Primero la clave: aunque el borrado físico falle (un archivo abierto, un antivirus), lo que quede está cifrado con una clave que ya no existe.
        proveedor.Destruir();
        lock (candado)
        {
            // Se borra lo que creó el almacén (las carpetas de alumnos) y, si con eso la raíz queda vacía, la raíz. Si alguien apuntó el almacén a una
            // carpeta compartida, lo que no es suyo no se toca.
            try
            {
                if (Directory.Exists(raiz))
                    foreach (var carpeta in Directory.EnumerateDirectories(raiz, "a-*")) BorrarCarpeta(carpeta);
                if (Directory.Exists(raiz)) Directory.Delete(raiz);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* mejor esfuerzo: lo que quede está cifrado */ }
        }
        Avisar("");
    }

    // --------------------------------------------- lo que necesita el descargador para escribir un paquete

    /// <summary>
    /// Registra el paquete que el nodo entregó (<c>POST /paquetes/</c>). Si ya había uno con el mismo id (volver a pedir para «Actualizar
    /// descarga») se conserva lo bajado y se refresca su vigencia; si el nodo entregó OTRO paquete para la asignación, lo anterior se borra.
    /// </summary>
    public PaqueteLocal RegistrarPaquete(string alumnoId, PaqueteEstudio paquete)
    {
        ArgumentNullException.ThrowIfNull(paquete);
        PaqueteLocal resultado;
        lock (candado)
        {
            var e = LeerEstado(alumnoId, paquete.AsignacionId);
            if (e is not null && e.PaqueteId != paquete.Id)
            {
                BorrarCarpeta(CarpetaPaquete(alumnoId, paquete.AsignacionId));
                e = null;
            }
            var nuevo = e is null;
            e ??= new EstadoPaqueteDisco { AlumnoId = alumnoId, AsignacionId = paquete.AsignacionId, PaqueteId = paquete.Id, Estado = "descargando" };
            if (nuevo)
            {
                e.BytesTotal = paquete.BytesTotal;
                e.Huella = paquete.Huella ?? "";
                if (paquete.Archivos is { Count: > 0 }) e.Archivos = paquete.Archivos.Select(NuevoArchivo).ToList();
            }
            e.VigenteHasta = paquete.VigenteHasta ?? e.VigenteHasta;
            e.CursoVersion = paquete.CursoVersion ?? e.CursoVersion;
            if (e.Estado == "vencido") e.Estado = "descargando";   // el nodo lo volvió a dar por vigente
            GuardarEstado(e);
            resultado = Publico(e);
        }
        Avisar(alumnoId);
        return resultado;
    }

    private static ArchivoDisco NuevoArchivo(ArchivoPaquete a) =>
        new() { MediaRef = a.MediaRef, Clase = a.Clase, Mime = a.Mime, Bytes = a.Bytes, Sha256 = a.Sha256 };

    /// <summary>
    /// Guarda el manifiesto (el texto original, ya verificado) y deja el paquete listo para bajar sus archivos. Concilia con lo que hubiera de un
    /// intento anterior: los archivos cuyo contenido no cambió (mismo <c>sha256</c> y tamaño) se conservan, los que cambiaron o ya no están se
    /// borran. Con una huella distinta un paquete disponible vuelve a «descargando».
    /// </summary>
    public void GuardarManifiesto(string alumnoId, string asignacionId, string manifiestoCrudo, ManifiestoPaquete manifiesto)
    {
        ArgumentNullException.ThrowIfNull(manifiestoCrudo);
        ArgumentNullException.ThrowIfNull(manifiesto);
        lock (candado)
        {
            var e = LeerEstado(alumnoId, asignacionId) ?? throw new InvalidOperationException("El paquete no está registrado: primero hay que llamar a RegistrarPaquete.");
            var previos = new Dictionary<string, ArchivoDisco>(StringComparer.Ordinal);
            foreach (var a in e.Archivos) previos[a.MediaRef] = a;
            var vigentes = new List<ArchivoDisco>();
            foreach (var a in manifiesto.Archivos)
            {
                if (vigentes.Any(v => v.MediaRef == a.MediaRef)) continue;   // un medio repetido en el manifiesto cuenta una sola vez
                if (previos.Remove(a.MediaRef, out var previo))
                {
                    if (previo.Bytes == a.Bytes && previo.Sha256 == a.Sha256)
                    {
                        previo.Clase = a.Clase;
                        previo.Mime = a.Mime;
                        vigentes.Add(previo);
                        continue;
                    }
                    BorrarMedio(e, previo);   // cambió su contenido: lo que se bajó de la versión anterior no vale
                }
                vigentes.Add(NuevoArchivo(a));
            }
            foreach (var sobrante in previos.Values) BorrarMedio(e, sobrante);   // ya no forma parte del paquete
            var huellaCambio = e.Huella != manifiesto.Huella;
            e.Archivos = vigentes;
            e.BytesTotal = vigentes.Sum(a => a.Bytes);
            e.Huella = manifiesto.Huella;
            e.VigenteHasta = manifiesto.VigenteHasta ?? e.VigenteHasta;
            e.CursoVersion = manifiesto.Curso?.Version ?? e.CursoVersion;
            if (huellaCambio && e.Estado == "disponible") e.Estado = "descargando";
            // Primero el manifiesto y después el estado: si se corta entre los dos, el próximo intento vuelve a bajar el manifiesto y concilia.
            EscribirBytes(RutaManifiesto(alumnoId, asignacionId), Encoding.UTF8.GetBytes(manifiestoCrudo), Contexto("manifiesto", alumnoId, asignacionId));
            GuardarEstado(e);
        }
        Avisar(alumnoId);
    }

    /// <summary>Si un archivo del paquete ya está completo en el aparato y cuántos bytes en claro hay de él (completo o a medias).</summary>
    public (bool Completo, long Bytes) EstadoDeArchivo(string alumnoId, string asignacionId, string mediaRef)
    {
        var cambio = false;
        try
        {
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId);
                var a = e?.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef);
                if (e is null || a is null) return (false, 0);
                if (ArchivoCompleto(e, mediaRef, ref cambio) is not null) return (true, a.Bytes);
                return (false, BytesParciales(e, a));
            }
        }
        finally
        {
            if (cambio) Avisar(alumnoId);
        }
    }

    /// <summary>
    /// El escritor cifrado de un archivo del paquete: si quedó a medias lo REANUDA (verifica lo escrito, descarta lo roto y sigue desde el último
    /// bloque íntegro); si no existe, o no se puede reanudar (otra clave, alterado), empieza de cero. Quien lo usa lo cierra con
    /// <see cref="EscritorCifrado.Cerrar"/> al terminar, lo libera siempre y llama a <see cref="CompletarArchivo"/>. Liberarlo sin cerrarlo es una pausa.
    /// </summary>
    public EscritorCifrado AbrirEscritura(string alumnoId, string asignacionId, string mediaRef)
    {
        string parte;
        byte[] clave;
        lock (candado)
        {
            var e = LeerEstado(alumnoId, asignacionId) ?? throw new InvalidOperationException("El paquete no está registrado.");
            var a = e.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef) ?? throw new ArgumentException("El manifiesto del paquete no incluye ese archivo.", nameof(mediaRef));
            if (a.Completo) throw new InvalidOperationException("Ese archivo ya está completo.");
            parte = RutaMedio(alumnoId, asignacionId, mediaRef, parcial: true);
            clave = proveedor.Obtener();
        }
        // Reanudar verifica y descifra todo lo ya escrito (puede ser cientos de MB): se hace fuera del cerrojo para no congelar a quien lea la lista.
        // Sólo el descargador toca este archivo, y él no corre dos veces a la vez sobre la misma lección.
        if (File.Exists(parte))
        {
            try { return EscritorCifrado.Reanudar(parte, clave); }
            catch (Exception ex) when (ex is ArchivoCifradoException or CryptographicException) { /* ilegible o alterado: se empieza de cero */ }
        }
        return EscritorCifrado.Crear(parte, clave);
    }

    /// <summary>
    /// El archivo terminó de bajarse y se cerró: pasa de «a medias» a definitivo. Comprueba que su tamaño en disco sea el que corresponde al
    /// manifiesto (que se cerró y no sobra ni falta nada).
    /// </summary>
    public void CompletarArchivo(string alumnoId, string asignacionId, string mediaRef)
    {
        lock (candado)
        {
            var e = LeerEstado(alumnoId, asignacionId) ?? throw new InvalidOperationException("El paquete no está registrado.");
            var a = e.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef) ?? throw new ArgumentException("El manifiesto del paquete no incluye ese archivo.", nameof(mediaRef));
            var parte = RutaMedio(alumnoId, asignacionId, mediaRef, parcial: true);
            if (!File.Exists(parte)) throw new InvalidOperationException("No hay una descarga terminada de ese archivo.");
            if (new FileInfo(parte).Length != ArchivoCifrado.LongitudDelArchivo(a.Bytes))
                throw new InvalidOperationException("El archivo descargado no tiene el tamaño del manifiesto (¿se cerró el escritor?).");
            File.Move(parte, RutaMedio(alumnoId, asignacionId, mediaRef, parcial: false), overwrite: true);
            a.Completo = true;
            GuardarEstado(e);
        }
        Avisar(alumnoId);
    }

    /// <summary>Tira lo que hubiera de un archivo (a medias o completo): su contenido no coincidió con el manifiesto.</summary>
    public void DescartarArchivo(string alumnoId, string asignacionId, string mediaRef)
    {
        lock (candado)
        {
            var e = LeerEstado(alumnoId, asignacionId);
            var a = e?.Archivos.FirstOrDefault(x => x.MediaRef == mediaRef);
            if (e is null || a is null) return;
            BorrarMedio(e, a);
            a.Completo = false;
            if (e.Estado == "disponible") e.Estado = "pausado";
            GuardarEstado(e);
        }
        Avisar(alumnoId);
    }

    /// <summary>
    /// Publica el estado de una descarga: <c>descargando</c>, <c>pausado</c> o <c>vencido</c> (el nodo dijo 410). Un paquete ya disponible no
    /// vuelve a «descargando» ni «pausado» por esto; sí puede pasar a «vencido».
    /// </summary>
    public void PublicarEstado(string alumnoId, string asignacionId, string estado)
    {
        if (estado is not ("descargando" or "pausado" or "vencido")) throw new ArgumentException("Estado no válido para una descarga.", nameof(estado));
        lock (candado)
        {
            var e = LeerEstado(alumnoId, asignacionId);
            if (e is null || e.Estado == estado) return;
            if (e.Estado == "disponible" && estado != "vencido") return;
            e.Estado = estado;
            GuardarEstado(e);
        }
        Avisar(alumnoId);
    }

    /// <summary>El nodo confirmó el paquete: todos sus archivos están completos y verificados. Lanza si falta alguno.</summary>
    public void MarcarDisponible(string alumnoId, string asignacionId, PaqueteEstudio? confirmado = null)
    {
        var cambio = false;
        try
        {
            lock (candado)
            {
                var e = LeerEstado(alumnoId, asignacionId) ?? throw new InvalidOperationException("El paquete no está registrado.");
                foreach (var a in e.Archivos.ToList())
                    if (ArchivoCompleto(e, a.MediaRef, ref cambio) is null)
                        throw new InvalidOperationException("Faltan archivos por descargar: el paquete no puede quedar disponible.");
                e.Estado = "disponible";
                e.DisponibleEn = ahoraNodoMs();
                if (confirmado?.VigenteHasta is { } vigente) e.VigenteHasta = vigente;
                GuardarEstado(e);
                cambio = true;
            }
        }
        finally
        {
            if (cambio) Avisar(alumnoId);
        }
    }

    // ------------------------------------------------------------------------------------ utilidades

    private void BorrarMedio(EstadoPaqueteDisco e, ArchivoDisco a)
    {
        foreach (var parcial in new[] { false, true })
        {
            try { File.Delete(RutaMedio(e.AlumnoId, e.AsignacionId, a.MediaRef, parcial)); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* un visor lo tiene abierto: el archivo queda huérfano hasta borrar el paquete */ }
        }
    }

    private static void BorrarCarpeta(string carpeta)
    {
        try { if (Directory.Exists(carpeta)) Directory.Delete(carpeta, recursive: true); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* mejor esfuerzo: lo que quede está cifrado */ }
    }

    /// <summary>Lo que ocupa una carpeta, sin contar lo apartado (<c>.dañado</c>) ni los temporales de una escritura interrumpida.</summary>
    private static long TamanoDe(string carpeta)
    {
        if (!Directory.Exists(carpeta)) return 0;
        long total = 0;
        try
        {
            foreach (var archivo in new DirectoryInfo(carpeta).EnumerateFiles("*", SearchOption.AllDirectories))
            {
                if (archivo.Name.EndsWith(".dañado", StringComparison.Ordinal) || archivo.Name.EndsWith(".tmp", StringComparison.Ordinal)) continue;
                total += archivo.Length;
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* se cuenta lo que se pudo */ }
        return total;
    }

    /// <summary>El espacio libre del volumen de la carpeta raíz, o nulo si el sistema no lo dice.</summary>
    private long? EspacioLibreDelVolumen()
    {
        try
        {
            var ruta = raiz;
            while (!Directory.Exists(ruta))
            {
                var padre = Path.GetDirectoryName(ruta);
                if (string.IsNullOrEmpty(padre)) return null;
                ruta = padre;
            }
            // DriveInfo en Windows exige la raíz de la unidad; en Unix y Android sirve cualquier ruta del volumen.
            var unidad = OperatingSystem.IsWindows() ? Path.GetPathRoot(ruta)! : ruta;
            return new DriveInfo(unidad).AvailableFreeSpace;
        }
        catch (Exception)
        {
            return null;
        }
    }
}
