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

        // Los demás campos (Entry y Editor sueltos, sin cápsula): el campo del DS en el propio TextBox. Borde de 2 en Línea por
        // los cuatro lados, radio 14 y foco en el color de foco del DS, en vez del subrayado de acento de Windows.
        EntryHandler.Mapper.AppendToMapping("CampoDs", (handler, view) =>
        {
            if (view is Entry { ClassId: Clase }) return;
            CampoDelDs(handler.PlatformView);
        });
        EditorHandler.Mapper.AppendToMapping("CampoDs", (handler, _) => CampoDelDs(handler.PlatformView));
        PickerHandler.Mapper.AppendToMapping("CampoDs", (handler, view) =>
        {
            if (view is Picker { ClassId: Clase }) return;
            var lista = handler.PlatformView;
            lista.CornerRadius = new Microsoft.UI.Xaml.CornerRadius(14);
            lista.BorderThickness = new Microsoft.UI.Xaml.Thickness(2);
            lista.BorderBrush = Pincel(Design.Ds.Linea);
            lista.Background = Pincel(Design.Ds.Superficie);
            Recurso(lista, "ComboBoxBorderBrush", Pincel(Design.Ds.Linea));
            Recurso(lista, "ComboBoxBorderBrushPointerOver", Pincel(Design.Ds.Linea));
            Recurso(lista, "ComboBoxBorderBrushFocused", Pincel(Design.Ds.Foco));
            Recurso(lista, "ComboBoxBorderThemeThickness", new Microsoft.UI.Xaml.Thickness(2));
        });

        // Botones del DS en todas las pantallas: sin el contorno gris de Windows cuando el botón no pide borde, en píldora cuando no
        // declara radio (el de Windows es de 4) y, si es sólo texto azul sobre transparente, como terciario del DS: texto subrayado.
        ButtonHandler.Mapper.AppendToMapping("BotonDs", (handler, view) =>
        {
            if (view is not Button boton) return;
            var nativo = handler.PlatformView;
            if (boton.BorderWidth <= 0)
            {
                nativo.BorderThickness = new Microsoft.UI.Xaml.Thickness(0);
                foreach (var clave in new[] { "ButtonBorderBrush", "ButtonBorderBrushPointerOver", "ButtonBorderBrushPressed", "ButtonBorderBrushDisabled" })
                    Recurso(nativo, clave, Transparente());
            }
            if (boton.CornerRadius < 0)
            {
                nativo.SizeChanged -= PildoraAlCambiar;
                nativo.SizeChanged += PildoraAlCambiar;
            }
            if (EsTerciario(boton))
            {
                foreach (var clave in new[] { "ButtonBackgroundPointerOver", "ButtonBackgroundPressed" })
                    Recurso(nativo, clave, Pincel(Design.Ds.Azul50));
                nativo.Loaded -= SubrayarAlCargar;
                nativo.Loaded += SubrayarAlCargar;
                // El texto se vuelve a crear al mostrarse o cambiar: también se subraya al cambiar de tamaño.
                nativo.SizeChanged -= SubrayarAlCambiar;
                nativo.SizeChanged += SubrayarAlCambiar;
                Subrayar(nativo);
            }
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

    private static Microsoft.UI.Xaml.Media.SolidColorBrush Pincel(Color c) =>
        new(Windows.UI.Color.FromArgb((byte)(c.Alpha * 255), (byte)(c.Red * 255), (byte)(c.Green * 255), (byte)(c.Blue * 255)));

    private static void CampoDelDs(Microsoft.UI.Xaml.Controls.TextBox caja)
    {
        var borde = new Microsoft.UI.Xaml.Thickness(2);
        caja.CornerRadius = new Microsoft.UI.Xaml.CornerRadius(14);
        caja.BorderThickness = borde;
        caja.BorderBrush = Pincel(Design.Ds.Linea);
        // Algunas claves ya las fija MAUI en el TextBox y WinUI rechaza sustituirlas (COMException 0x800F0902): cada una por separado,
        // y si una no entra, el campo se queda con la de Windows en vez de tumbar la pantalla.
        Recurso(caja, "TextControlBorderThemeThickness", borde);
        Recurso(caja, "TextControlBorderThemeThicknessFocused", borde);
        Recurso(caja, "TextControlBorderBrush", Pincel(Design.Ds.Linea));
        Recurso(caja, "TextControlBorderBrushPointerOver", Pincel(Design.Ds.Linea));
        Recurso(caja, "TextControlBorderBrushFocused", Pincel(Design.Ds.Foco));
    }

    /// <summary>Terciario del DS: sólo texto azul sobre transparente, sin borde ni icono.</summary>
    private static bool EsTerciario(Button b) =>
        b.ImageSource is null && b.BorderWidth <= 0 && !string.IsNullOrWhiteSpace(b.Text) && b.Text.Trim().Length > 2
        && (b.Background is null || b.Background.IsEmpty) && b.BackgroundColor is { } fondo && fondo.Alpha == 0
        && b.TextColor is { } tinta && (Igual(tinta, Design.Ds.Azul700) || Igual(tinta, Design.Ds.Azul600));

    private static bool Igual(Color a, Color b) => Math.Abs(a.Red - b.Red) < 0.01 && Math.Abs(a.Green - b.Green) < 0.01 && Math.Abs(a.Blue - b.Blue) < 0.01;

    private static void PildoraAlCambiar(object sender, Microsoft.UI.Xaml.SizeChangedEventArgs e)
    {
        if (sender is Microsoft.UI.Xaml.Controls.Button b && e.NewSize.Height > 0)
            b.CornerRadius = new Microsoft.UI.Xaml.CornerRadius(e.NewSize.Height / 2);
    }

    private static void SubrayarAlCargar(object sender, Microsoft.UI.Xaml.RoutedEventArgs e)
    {
        if (sender is Microsoft.UI.Xaml.DependencyObject d) Subrayar(d);
    }

    private static void SubrayarAlCambiar(object sender, Microsoft.UI.Xaml.SizeChangedEventArgs e)
    {
        if (sender is Microsoft.UI.Xaml.DependencyObject d) Subrayar(d);
    }

    private static void Subrayar(Microsoft.UI.Xaml.DependencyObject raiz)
    {
        var n = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(raiz);
        for (var i = 0; i < n; i++)
        {
            var hijo = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(raiz, i);
            if (hijo is Microsoft.UI.Xaml.Controls.TextBlock texto) texto.TextDecorations = Windows.UI.Text.TextDecorations.Underline;
            Subrayar(hijo);
        }
    }

    private static void Recurso(Microsoft.UI.Xaml.FrameworkElement elemento, string clave, object valor)
    {
        try { elemento.Resources[clave] = valor; }
        catch (System.Runtime.InteropServices.COMException) { }
    }
}
