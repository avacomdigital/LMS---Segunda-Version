using System.Globalization;

namespace Avacom.Lms.Student.ModoEstudio.Converters;

/// <summary>
/// De una fracción de progreso (0..1) al ancho de la parte llena o de la parte vacía de una barra: pesos «estrella» de dos columnas de un
/// <see cref="Grid"/>. Así la barra no necesita conocer su ancho en píxeles y se adapta a cualquier tarjeta o pantalla. Parámetro:
/// <c>fill</c> (por defecto) la parte llena, <c>rest</c> la vacía.
/// </summary>
public sealed class ProgressToWidthConverter : IValueConverter
{
    /// <summary>El peso mínimo evita una columna de 0 «estrella» exacta, que algunos motores de diseño miden mal.</summary>
    private const double Minimo = 0.0001;

    public static GridLength Fill(double progreso) => new(Math.Max(Minimo, Math.Clamp(progreso, 0, 1)), GridUnitType.Star);
    public static GridLength Rest(double progreso) => new(Math.Max(Minimo, 1 - Math.Clamp(progreso, 0, 1)), GridUnitType.Star);

    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture)
    {
        var progreso = value switch { double d => d, float f => f, int i => i / 100.0, _ => 0 };
        return string.Equals(parameter as string, "rest", StringComparison.OrdinalIgnoreCase) ? Rest(progreso) : Fill(progreso);
    }

    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>Niega un booleano (<c>IsVisible="{Binding IsLoading, Converter={StaticResource Not}}"</c>).</summary>
public sealed class InvertedBoolConverter : IValueConverter
{
    public object Convert(object? value, Type targetType, object? parameter, CultureInfo culture) => value is bool b ? !b : value is null;
    public object ConvertBack(object? value, Type targetType, object? parameter, CultureInfo culture) => value is bool b ? !b : value is null;
}
