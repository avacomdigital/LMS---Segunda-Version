using System.Diagnostics;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Reportes.Ui;

/// <summary>
/// Lo que sólo Windows sabe hacer para la exportación: abrir el selector de carpetas del Explorador (el cuadro nativo, que ya es táctil) para llegar a una carpeta compartida o de red que
/// la lista no muestra, y abrir la carpeta donde quedó un archivo. Nada de esto lanza: un selector que no se pudo abrir devuelve «nada elegido» y la persona sigue con la lista.
/// </summary>
internal static class SelectorDeCarpeta
{
    /// <summary>Abre el selector de carpetas de Windows y devuelve la ruta elegida, o null si se cerró sin elegir (o no se pudo abrir). Se llama desde el hilo de la interfaz.</summary>
    public static async Task<string?> ElegirAsync()
    {
#if WINDOWS
        try
        {
            if (Application.Current?.Windows.FirstOrDefault()?.Handler?.PlatformView is not MauiWinUIWindow ventana) return null;
            var selector = new global::Windows.Storage.Pickers.FolderPicker { SuggestedStartLocation = global::Windows.Storage.Pickers.PickerLocationId.DocumentsLibrary };
            selector.FileTypeFilter.Add("*");
            WinRT.Interop.InitializeWithWindow.Initialize(selector, ventana.WindowHandle);
            var carpeta = await selector.PickSingleFolderAsync();
            return string.IsNullOrWhiteSpace(carpeta?.Path) ? null : carpeta!.Path;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", "SelectorDeCarpeta.ElegirAsync", ex);
            return null;
        }
#else
        await Task.CompletedTask;
        return null;
#endif
    }

    /// <summary>
    /// Abre el Explorador con el archivo ya señalado; si no se puede (el archivo ya no está), abre su carpeta. Devuelve si se abrió algo. Un fallo se anota y no se muestra como error:
    /// el archivo ya está guardado, que es lo que importa.
    /// </summary>
    public static bool AbrirCarpetaDe(string rutaDelArchivo)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(rutaDelArchivo)) return false;
            var carpeta = Path.GetDirectoryName(rutaDelArchivo);
            var argumentos = File.Exists(rutaDelArchivo) ? $"/select,\"{rutaDelArchivo}\"" : !string.IsNullOrEmpty(carpeta) && Directory.Exists(carpeta) ? $"\"{carpeta}\"" : null;
            if (argumentos is null) return false;
            Process.Start(new ProcessStartInfo("explorer.exe", argumentos) { UseShellExecute = true });
            return true;
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("ops", "SelectorDeCarpeta.AbrirCarpetaDe", ex);
            return false;
        }
    }
}

/// <summary>Las preferencias pequeñas de OPS (<see cref="Ajustes"/>, que respeta el perfil de pruebas) vistas como el almacén que necesita <see cref="PreferenciasDeDestino"/>.</summary>
internal sealed class AlmacenDeAjustes : IAlmacenDePreferencias
{
    public string? Leer(string clave) => Ajustes.Get<string?>(clave, null);

    public void Guardar(string clave, string valor) => Ajustes.Set(clave, valor);
}
