using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops;

/// <summary>
/// Lo que el OPS Master necesita saber de la sesión: a qué backend hablar y con
/// qué fachada. El docente no tiene expediente: no registra progreso.
/// </summary>
public static class Sesion
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(15) };
    private static IBibliotecaDeContenido? _biblioteca;
    private static IAulaApi? _aula;
    private static IDispositivosApi? _dispositivos;
    private static Uri? _baseActual;
    private static Uri? _baseAula;
    private static Uri? _baseDispositivos;
    private static string? _fuenteAula;

    public const string DireccionPorDefecto = "http://127.0.0.1:8000";

    public const string FuenteBiblioteca = "biblioteca";
    public const string FuenteEjemplo = "ejemplo";

    /// <summary>
    /// Fuente de cursos de MOD-007. Por defecto <c>biblioteca</c>: el backend habla con la API de
    /// Contenido v2 de AVACOM Biblioteca. Cuando la biblioteca no está en el equipo, «Clase de hoy»
    /// ofrece pasar al manifiesto de ejemplo con un toque (y volver tocando el chip de la fuente).
    /// Se guarda en Preferences; nada más del cliente depende de esto.
    /// </summary>
    public static string FuenteAula
    {
        get => Preferences.Default.Get("ops_fuente_aula", FuenteBiblioteca) is FuenteEjemplo ? FuenteEjemplo : FuenteBiblioteca;
        set => Preferences.Default.Set("ops_fuente_aula", value == FuenteEjemplo ? FuenteEjemplo : FuenteBiblioteca);
    }

    public static Uri BaseUri
    {
        get
        {
            var texto = Preferences.Default.Get("ops_server", DireccionPorDefecto);
            try { return ConnectionOptions.Normalize(texto); }
            catch (ArgumentException) { return ConnectionOptions.Normalize(DireccionPorDefecto); }
        }
    }

    /// <summary>Una sola fachada por dirección: conserva la huella entre pantallas.</summary>
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

    /// <summary>El cliente de <c>/api/aula/</c> (MOD-007), una instancia por dirección y fuente.</summary>
    public static IAulaApi Aula
    {
        get
        {
            var actual = BaseUri;
            var fuente = FuenteAula;
            if (_aula is null || _baseAula != actual || _fuenteAula != fuente)
            {
                _aula = new AulaApi(Http, actual, fuente);
                _baseAula = actual;
                _fuenteAula = fuente;
            }
            return _aula;
        }
    }

    /// <summary>El cliente de <c>/api/dispositivos/</c> (MOD-009): inventario y bloqueo de tabletas, una instancia por dirección.</summary>
    public static IDispositivosApi Dispositivos
    {
        get
        {
            var actual = BaseUri;
            if (_dispositivos is null || _baseDispositivos != actual)
            {
                _dispositivos = new DispositivosApi(Http, actual);
                _baseDispositivos = actual;
            }
            return _dispositivos;
        }
    }

    public static string Dispositivo => $"ops-{DeviceInfo.Current.Name}";

    /// <summary>Identidad del docente mientras OPS no inicie sesión con MOD-001 (Q-04): estable por equipo.</summary>
    public static string ProfesorRotulo => Preferences.Default.Get("ops_profesor_nombre", "Ms. Carter");
    public static string ProfesorId => Preferences.Default.Get("ops_profesor_id", string.Empty) is { Length: > 0 } id ? id : $"docente-{Identidad.SlugDe(ProfesorRotulo)}";

    /// <summary>La clase que este equipo dejó abierta, para poder continuarla (BR-051) sin volver a elegir.</summary>
    public static string? ClaseAbiertaId
    {
        get => Preferences.Default.Get<string?>("aula_sesion_ops", null);
        set { if (value is null) Preferences.Default.Remove("aula_sesion_ops"); else Preferences.Default.Set("aula_sesion_ops", value); }
    }

    public static readonly string[] Paleta = ["#E5262B", "#F3C701", "#01A4E1", "#019D60", "#A81D81", "#52525B"];

    /// <summary>El mismo libro abierto del hexágono «Asignaturas» del menú principal.</summary>
    public const string IconoLibro =
        "M232,48 H160 A40,40 0 0 0 128,64 A40,40 0 0 0 96,48 H24 A8,8 0 0 0 16,56 V200 A8,8 0 0 0 24,208 H96 A24,24 0 0 1 120,232 A8,8 0 0 0 136,232 A24,24 0 0 1 160,208 H232 A8,8 0 0 0 240,200 V56 A8,8 0 0 0 232,48 Z M96,192 H32 V64 H96 A24,24 0 0 1 120,88 V200 A39.81,39.81 0 0 0 96,192 Z M224,192 H160 A39.81,39.81 0 0 0 136,200 V88 A24,24 0 0 1 160,64 H224 Z";

    /// <summary>El icono del hexágono «Clase de hoy».</summary>
    public const string IconoClase =
        "M128,88 A40,40 0 1 0 168,128 A40,40 0 0 0 128,88 Z M128,152 A24,24 0 1 1 152,128 A24,24 0 0 1 128,152 Z M201.71,159.14 A80,80 0 0 1 187.63,181.34 A8,8 0 0 1 175.71,170.67 A63.95,63.95 0 0 0 175.71,85.34 A8,8 0 1 1 187.63,74.67 A80.08,80.08 0 0 1 201.71,159.14 Z M69,103.09 A64,64 0 0 0 80.26,170.67 A8,8 0 0 1 68.34,181.34 A79.93,79.93 0 0 1 68.34,74.67 A8,8 0 1 1 80.29,85.34 A63.77,63.77 0 0 0 69,103.09 Z M248,128 A119.58,119.58 0 0 1 213.71,212 A8,8 0 1 1 202.29,200.8 A103.9,103.9 0 0 0 202.29,55.24 A8,8 0 1 1 213.71,44 A119.58,119.58 0 0 1 248,128 Z M53.71,200.78 A8,8 0 1 1 42.29,212 A119.87,119.87 0 0 1 42.29,44 A8,8 0 1 1 53.71,55.2 A103.9,103.9 0 0 0 53.71,200.78 Z";
}
