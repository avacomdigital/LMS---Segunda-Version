using Microsoft.Maui.Handlers;

namespace Avacom.Lms.Ui.Controls;

public static partial class NeumoChrome
{
    static partial void RegistrarPlataforma()
    {
        // TextBox: sin borde, sin fondo y sin la línea de acento del foco; el aspecto lo da la cápsula que lo envuelve.
        EntryHandler.Mapper.AppendToMapping("Neumo", (handler, view) =>
        {
            if (view is not Entry { ClassId: Clase }) return;
            var caja = handler.PlatformView;
            caja.BorderThickness = new Microsoft.UI.Xaml.Thickness(0);
            caja.Background = Transparente();
            foreach (var clave in new[] { "TextControlBackground", "TextControlBackgroundPointerOver", "TextControlBackgroundFocused", "TextControlBackgroundDisabled" })
                caja.Resources[clave] = Transparente();
            foreach (var clave in new[] { "TextControlBorderThemeThickness", "TextControlBorderThemeThicknessFocused" })
                caja.Resources[clave] = new Microsoft.UI.Xaml.Thickness(0);
        });

        // ComboBox: igual, conservando la flecha desplegable.
        PickerHandler.Mapper.AppendToMapping("Neumo", (handler, view) =>
        {
            if (view is not Picker { ClassId: Clase }) return;
            var lista = handler.PlatformView;
            lista.BorderThickness = new Microsoft.UI.Xaml.Thickness(0);
            lista.Background = Transparente();
            foreach (var clave in new[] { "ComboBoxBackground", "ComboBoxBackgroundPointerOver", "ComboBoxBackgroundPressed", "ComboBoxBackgroundFocused", "ComboBoxBackgroundDisabled", "ComboBoxBackgroundUnfocused" })
                lista.Resources[clave] = Transparente();
            foreach (var clave in new[] { "ComboBoxBorderBrush", "ComboBoxBorderBrushPointerOver", "ComboBoxBorderBrushPressed", "ComboBoxBorderBrushFocused" })
                lista.Resources[clave] = Transparente();
        });
    }

    private static Microsoft.UI.Xaml.Media.SolidColorBrush Transparente() => new(Microsoft.UI.Colors.Transparent);
}
