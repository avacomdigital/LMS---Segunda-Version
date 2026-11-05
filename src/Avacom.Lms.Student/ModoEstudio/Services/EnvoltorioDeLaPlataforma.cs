using Avacom.Lms.Core.Estudio;

namespace Avacom.Lms.Student.ModoEstudio.Services;

/// <summary>
/// MOD-018 · Fase 5 (P-25): la bandera de la clave de datos envuelta y el envoltorio de esta plataforma. APAGADA de fábrica: se enciende con la variable <c>AVACOM_CLAVE_ENVUELTA=1</c> o la
/// preferencia <c>clave_envuelta</c> (no es un interruptor de desarrollo: es endurecimiento que el administrador decide). Con la bandera apagada todo funciona como siempre (DPAPI en Windows,
/// <c>SecureStorage</c> en Android); encendida, la clave de datos nueva se guarda envuelta con la clave no exportable de CNG (el TPM si lo hay) o del Keystore, y la de antes se migra al leerla.
/// </summary>
internal static class EnvoltorioDeLaPlataforma
{
    public static bool Encendida =>
        Environment.GetEnvironmentVariable("AVACOM_CLAVE_ENVUELTA") == "1" || Preferences.Default.Get("clave_envuelta", false);

    public static IEnvoltorioDeClave? Crear()
    {
#if ANDROID
        return OperatingSystem.IsAndroidVersionAtLeast(23) ? new Platforms.Android.EnvoltorioKeystore() : null;
#elif WINDOWS
        return OperatingSystem.IsWindows() ? new EnvoltorioCng() : null;
#else
        return null;
#endif
    }
}
