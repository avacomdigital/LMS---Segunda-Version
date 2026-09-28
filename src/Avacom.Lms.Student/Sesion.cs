using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student;

/// <summary>
/// La sesión del estudiante: quién es (identidad lógica del expediente), en qué
/// aula está (backend) y la fachada hacia la biblioteca a través del backend.
/// </summary>
public static class Sesion
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private static IBibliotecaDeContenido? _biblioteca;
    private static IAulaApi? _aula;
    private static Uri? _baseActual;
    private static Uri? _baseAula;

    public static string Nombre => Preferences.Default.Get("student_name", ConnectionOptions.Default.StudentName);
    public static string PersonaId => Identidad.SlugDe(Nombre);

    public static Uri BaseUri
    {
        get
        {
            var texto = Preferences.Default.Get("student_server", ConnectionOptions.Default.ServerAddress);
            try { return ConnectionOptions.Normalize(texto); }
            catch (ArgumentException) { return ConnectionOptions.Normalize(ConnectionOptions.Default.ServerAddress); }
        }
    }

    public static IBibliotecaDeContenido Biblioteca
    {
        get
        {
            var actual = BaseUri;
            if (_biblioteca is null || _baseActual != actual)
            {
                _biblioteca = new BibliotecaDeContenido(Http, actual);
                _baseActual = actual;
            }
            return _biblioteca;
        }
    }

    /// <summary>
    /// El cliente de <c>/api/aula/</c>. La tableta NO elige fuente de cursos: sigue la clase que abrió el
    /// profesor y el backend resuelve de dónde sale el curso (la biblioteca por la API de Contenido v2,
    /// o el manifiesto de ejemplo cuando la referencia es la suya). Las URL de los medios ya llegan con
    /// su fuente desde el backend.
    /// </summary>
    public static IAulaApi Aula
    {
        get
        {
            var actual = BaseUri;
            if (_aula is null || _baseAula != actual)
            {
                _aula = new AulaApi(Http, actual);
                _baseAula = actual;
            }
            return _aula;
        }
    }

    /// <summary>La huella con la que MOD-009 reconoce esta tableta en el inventario del aula.</summary>
    public static string Dispositivo => $"student-{DeviceInfo.Current.Name}";

    /// <summary>Plataforma y versión declaradas al entrar a clase, para que el inventario sepa qué app corre cada tableta.</summary>
    public static string Plataforma =>
        DeviceInfo.Current.Platform == DevicePlatform.Android ? "android" : DeviceInfo.Current.Platform == DevicePlatform.WinUI ? "windows" : string.Empty;

    public static string VersionApp => AppInfo.Current.VersionString;

    /// <summary>La participación en curso: se conserva para readmitirse sin escribir el código (FUN-077, RF-A10).</summary>
    public static string? ClaseSesionId
    {
        get => Preferences.Default.Get<string?>("aula_sesion", null);
        set { if (value is null) Preferences.Default.Remove("aula_sesion"); else Preferences.Default.Set("aula_sesion", value); }
    }

    public static string? ClaseParticipanteId
    {
        get => Preferences.Default.Get<string?>("aula_participante", null);
        set { if (value is null) Preferences.Default.Remove("aula_participante"); else Preferences.Default.Set("aula_participante", value); }
    }

    public static string? ClaseCodigo
    {
        get => Preferences.Default.Get<string?>("aula_codigo", null);
        set { if (value is null) Preferences.Default.Remove("aula_codigo"); else Preferences.Default.Set("aula_codigo", value); }
    }

    public static void OlvidarClase()
    {
        ClaseSesionId = null;
        ClaseParticipanteId = null;
        ClaseCodigo = null;
    }

    public static readonly string[] Paleta = ["#E5262B", "#F3C701", "#01A4E1", "#019D60", "#A81D81", "#52525B"];

    public const string IconoLibro =
        "M232,48 H160 A40,40 0 0 0 128,64 A40,40 0 0 0 96,48 H24 A8,8 0 0 0 16,56 V200 A8,8 0 0 0 24,208 H96 A24,24 0 0 1 120,232 A8,8 0 0 0 136,232 A24,24 0 0 1 160,208 H232 A8,8 0 0 0 240,200 V56 A8,8 0 0 0 232,48 Z M96,192 H32 V64 H96 A24,24 0 0 1 120,88 V200 A39.81,39.81 0 0 0 96,192 Z M224,192 H160 A39.81,39.81 0 0 0 136,200 V88 A24,24 0 0 1 160,64 H224 Z";
}
