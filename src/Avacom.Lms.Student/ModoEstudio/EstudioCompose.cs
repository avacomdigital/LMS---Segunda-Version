using Avacom.Lms.Core.Services;
using Avacom.Lms.Student.ModoEstudio.Services;
using Avacom.Lms.Student.ModoEstudio.ViewModels;

namespace Avacom.Lms.Student.ModoEstudio;

/// <summary>
/// El punto de composición del modo de estudio: qué servicios usa la app (los reales, contra el aula y con el almacén y la cola locales,
/// o los de demostración) y cómo se arma cada pantalla. Student no tiene contenedor de dependencias, así que esto es lo mismo que hace
/// <see cref="Sesion"/> con el resto: un único lugar, estático y pequeño.
///
/// La demostración se enciende con <c>AVACOM_ESTUDIO_DEMO=1</c> (o la preferencia <c>estudio_demo</c>): enseña las siete lecciones de
/// muestra con todos los estados posibles y una práctica que se califica en el propio aparato, sin tocar el aula.
/// </summary>
public static class EstudioCompose
{
    private static readonly object Candado = new();
    private static IStudyModeService? _servicio;
    private static IDownloadService? _descargas;
    private static IConnectivityService? _conectividad;

    public static bool EsDemo =>
        Environment.GetEnvironmentVariable("AVACOM_ESTUDIO_DEMO") == "1" || Preferences.Default.Get("estudio_demo", false);

    public static IStudyModeService Servicio { get { Asegurar(); return _servicio!; } }
    public static IDownloadService Descargas { get { Asegurar(); return _descargas!; } }
    public static IConnectivityService Conectividad { get { Asegurar(); return _conectividad!; } }

    /// <summary>El ViewModel de «Mis lecciones». Cada visita crea uno nuevo; los servicios (y las descargas en curso) son de toda la app.</summary>
    public static StudyModeViewModel CrearViewModel(IStudyNavigation navegacion)
    {
        Asegurar();
        return new StudyModeViewModel(_servicio!, _descargas!, _conectividad!, navegacion);
    }

    private static void Asegurar()
    {
        lock (Candado)
        {
            if (_servicio is not null) return;
            if (EsDemo)
            {
                var almacen = new MockStudyStore();
                _conectividad = new MockConnectivityService();
                _descargas = new MockDownloadService(almacen);
                _servicio = new MockStudyModeService(almacen);
                return;
            }
            var real = EstudioReal.Crear();
            _servicio = real.Servicio;
            _descargas = real.Descargas;
            _conectividad = real.Conectividad;
        }
    }

    /// <summary>
    /// «Salir» (008-07, FUN-089, BR-053): cierra la sesión de estudio en el aula y suelta lo que la pantalla tenía en memoria. Con un tope
    /// corto, para que la persona siguiente no espere (JRN-022, ≤ 3 s en total). Lo pendiente queda en la cola cifrada y sale solo.
    /// </summary>
    public static async Task AlSalirAsync(CancellationToken ct = default)
    {
        IStudyModeService? servicio;
        lock (Candado) servicio = _servicio;
        try
        {
            // Aunque en esta ejecución no se haya abierto el modo de estudio, si la tableta guardó algo de una ejecución anterior también se limpia.
            if (servicio is null && !EsDemo && Preferences.Default.Get<string?>(EstudioLocal.ClaveAlumno, null) is not null)
            {
                Asegurar();
                lock (Candado) servicio = _servicio;
            }
            if (servicio is not null) await servicio.CloseSessionAsync(ct);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "EstudioCompose.AlSalir", ex); }
        Olvidar();
    }

    /// <summary>Suelta los servicios: la próxima pantalla los crea de nuevo (cambió el aula, la persona o la modalidad).</summary>
    public static void Olvidar()
    {
        lock (Candado)
        {
            foreach (var servicio in new object?[] { _servicio, _descargas, _conectividad })
            {
                try { (servicio as IDisposable)?.Dispose(); }
                catch (Exception ex) { RegistroDeFallos.Escribir("student", "EstudioCompose.Olvidar", ex); }
            }
            _servicio = null;
            _descargas = null;
            _conectividad = null;
        }
    }
}
