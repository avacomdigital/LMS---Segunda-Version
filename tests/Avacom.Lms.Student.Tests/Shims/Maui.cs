// Sustitutos mínimos de las piezas de MAUI Essentials que usa la lógica del modo de estudio de Student. Sólo existen en las pruebas: en la app
// son las de verdad. Todo va en memoria y se reinicia con `Estado.Reiniciar()` entre pruebas.

namespace Microsoft.Maui.Storage
{
    public interface IPreferences
    {
        T Get<T>(string key, T defaultValue, string? sharedName = null);
        void Set<T>(string key, T value, string? sharedName = null);
        void Remove(string key, string? sharedName = null);
        bool ContainsKey(string key, string? sharedName = null);
        void Clear(string? sharedName = null);
    }

    internal sealed class PreferenciasEnMemoria : IPreferences
    {
        private readonly Dictionary<string, object?> _valores = new();

        public T Get<T>(string key, T defaultValue, string? sharedName = null) =>
            _valores.TryGetValue(key, out var v) && v is T t ? t : defaultValue;

        public void Set<T>(string key, T value, string? sharedName = null) => _valores[key] = value;
        public void Remove(string key, string? sharedName = null) => _valores.Remove(key);
        public bool ContainsKey(string key, string? sharedName = null) => _valores.ContainsKey(key);
        public void Clear(string? sharedName = null) => _valores.Clear();
    }

    public static class Preferences
    {
        public static IPreferences Default { get; } = new PreferenciasEnMemoria();
    }

    public static class FileSystem
    {
        public static string AppDataDirectory => Path.Combine(Path.GetTempPath(), "avacom-student-tests");
    }

    /// <summary>Sólo lo usa <c>ClaveDeStudent</c> fuera de Windows; las pruebas le ponen una clave en memoria y no llegan aquí.</summary>
    public sealed class SecureStorage
    {
        private readonly Dictionary<string, string> _valores = new();
        public static SecureStorage Default { get; } = new();
        public Task<string?> GetAsync(string key) => Task.FromResult(_valores.TryGetValue(key, out var v) ? v : null);
        public Task SetAsync(string key, string value) { _valores[key] = value; return Task.CompletedTask; }
        public bool Remove(string key) => _valores.Remove(key);
    }
}

namespace Microsoft.Maui.Devices
{
    public sealed class DeviceInfo
    {
        public static DeviceInfo Current { get; } = new();
        public string Name => "TABLETA-PRUEBA";
    }
}

namespace Microsoft.Maui.Networking
{
    public enum NetworkAccess { Unknown, None, Local, ConstrainedInternet, Internet }

    public sealed class ConnectivityChangedEventArgs(NetworkAccess acceso) : EventArgs
    {
        public NetworkAccess NetworkAccess { get; } = acceso;
    }

    public sealed class Connectivity
    {
        public static Connectivity Current { get; } = new();
        public event EventHandler<ConnectivityChangedEventArgs>? ConnectivityChanged;
        public void Cambiar(NetworkAccess acceso) => ConnectivityChanged?.Invoke(this, new ConnectivityChangedEventArgs(acceso));
    }
}
