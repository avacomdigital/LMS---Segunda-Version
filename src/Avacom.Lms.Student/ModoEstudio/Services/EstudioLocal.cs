using System.Text.Json;
using Avacom.Lms.Core.Estudio;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// Lo local del modo de estudio en ESTE aparato, todo junto: la clave, el almacén cifrado (lista, tareas, paquetes), la cola cifrada de lo que
/// el alumno hace, el sincronizador que la vacía, el descargador de paquetes y el servidor de medios en 127.0.0.1. Lo comparten el servicio de
/// estudio, el de descargas y el de conectividad (uno solo por aparato y por arranque).
/// </summary>
internal sealed class EstudioLocal : IDisposable
{
    private EstudioLocal(IEstudioApi api, string dispositivo, string carpeta, IProveedorDeClave clave, AlmacenEstudio almacen, ColaEstudio cola)
    {
        Api = api;
        Dispositivo = dispositivo;
        Carpeta = carpeta;
        RutaCola = Path.Combine(carpeta, "cola.avc");
        Clave = clave;
        Almacen = almacen;
        Cola = cola;
        Sincronizador = new SincronizadorEstudio(api, cola);
        Descargador = new DescargadorDePaquetes(api, almacen);
        Servidor = new ServidorLocalDeMedios(almacen);
    }

    public IEstudioApi Api { get; }
    public string Dispositivo { get; }
    public string Carpeta { get; }
    public string RutaCola { get; }
    public IProveedorDeClave Clave { get; }
    public AlmacenEstudio Almacen { get; }
    public ColaEstudio Cola { get; }
    public SincronizadorEstudio Sincronizador { get; }
    public DescargadorDePaquetes Descargador { get; }
    public ServidorLocalDeMedios Servidor { get; }

    /// <summary>
    /// La persona dueña de esta tableta, tal como la dijo el aula (D-3: en un aparato asignado, el nodo sabe quién es). Se recuerda para poder
    /// ver lo ya descargado sin conexión. Nulo hasta que el aula lo diga por primera vez.
    /// </summary>
    public string? AlumnoId { get; set; }
    public string? AlumnoRotulo { get; set; }

    /// <param name="carpetaDeDatos">Dónde vive lo local; por defecto, los datos privados de la app. Las pruebas usan una carpeta temporal.</param>
    /// <param name="claveLocal">Quien guarda la clave; por defecto, la del sistema (DPAPI en Windows, SecureStorage en Android).</param>
    public static EstudioLocal Crear(IEstudioApi api, string dispositivo, string? carpetaDeDatos = null, IProveedorDeClave? claveLocal = null)
    {
        var datos = carpetaDeDatos ?? FileSystem.AppDataDirectory;
        var carpeta = Path.Combine(datos, "estudio");
        Directory.CreateDirectory(carpeta);
        var clave = claveLocal ?? new ClaveDeStudent(Path.Combine(datos, "estudio-clave"));
        var almacen = new AlmacenEstudio(Path.Combine(carpeta, "almacen"), clave);
        var cola = new ColaEstudio(Path.Combine(carpeta, "cola.avc"), clave);
        var local = new EstudioLocal(api, dispositivo, carpeta, clave, almacen, cola)
        {
            AlumnoId = Preferences.Default.Get<string?>(ClaveAlumno, null),
            AlumnoRotulo = Preferences.Default.Get<string?>(ClaveRotulo, null),
        };
        return local;
    }

    internal const string ClaveAlumno = "estudio_alumno_id", ClaveRotulo = "estudio_alumno_rotulo", ClaveLimpiezaPendiente = "estudio_limpieza_pendiente";

    public void RecordarAlumno(string id, string? rotulo)
    {
        AlumnoId = id;
        AlumnoRotulo = rotulo;
        Preferences.Default.Set(ClaveAlumno, id);
        if (rotulo is null) Preferences.Default.Remove(ClaveRotulo);
        else Preferences.Default.Set(ClaveRotulo, rotulo);
    }

    // ---------------------------------------------------------------- los nombres de «¿Quién eres?», cifrados
    private static readonly byte[] ContextoNombres = "avacom-estudio-nombres"u8.ToArray();
    private string RutaNombres => Path.Combine(Carpeta, "estudiantes.avc");

    /// <summary>
    /// Lo último que el aula dijo sobre quiénes se pueden elegir. Son nombres de niños: se guardan cifrados con la clave de la tableta (BR-053) y
    /// desaparecen con ella. Sirve para poder elegir tu nombre sin conexión con el aula.
    /// </summary>
    public EstudiantesEstudio? LeerNombres()
    {
        try
        {
            if (!File.Exists(RutaNombres)) return null;
            var claro = DocumentoCifrado.Abrir(File.ReadAllBytes(RutaNombres), Clave.Obtener(), ContextoNombres);
            return JsonSerializer.Deserialize<EstudiantesEstudio>(claro, StudyModeService.Json);
        }
        catch (Exception ex) when (ex is ArchivoCifradoException or IOException or JsonException or UnauthorizedAccessException) { return null; }
    }

    public void GuardarNombres(EstudiantesEstudio nombres)
    {
        try
        {
            var claro = JsonSerializer.SerializeToUtf8Bytes(nombres, StudyModeService.Json);
            var sellado = DocumentoCifrado.Sellar(claro, Clave.Obtener(), ContextoNombres);
            var temporal = RutaNombres + ".tmp";
            Directory.CreateDirectory(Carpeta);
            File.WriteAllBytes(temporal, sellado);
            File.Move(temporal, RutaNombres, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            RegistroDeFallos.Escribir("student", "EstudioLocal.GuardarNombres", ex);   // no es grave: sin la copia, la próxima vez se pregunta al aula
        }
    }

    public void BorrarNombres()
    {
        try { if (File.Exists(RutaNombres)) File.Delete(RutaNombres); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { /* ilegible sin clave */ }
    }

    public void OlvidarAlumno()
    {
        AlumnoId = null;
        AlumnoRotulo = null;
        Preferences.Default.Remove(ClaveAlumno);
        Preferences.Default.Remove(ClaveRotulo);
    }

    public void Dispose()
    {
        try { Servidor.Dispose(); } catch (Exception ex) { RegistroDeFallos.Escribir("student", "EstudioLocal.Dispose", ex); }
    }
}
