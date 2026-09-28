namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Quita el cromo nativo (borde, fondo, subrayado de foco) de los <see cref="Entry"/> y <see cref="Picker"/> marcados
/// con <c>ClassId="neumo"</c>: la cápsula neumórfica la pone el <see cref="Border"/> que los envuelve
/// (<see cref="SearchFilterBar"/>, <see cref="FilterPicker"/>), así que el control nativo debe ser transparente.
/// En Windows se hace con un mapeo añadido a los handlers (ver <c>Platforms/Windows/NeumoChrome.Windows.cs</c>);
/// en las demás plataformas basta con el fondo transparente que ya ponen los controles.
/// </summary>
public static partial class NeumoChrome
{
    public const string Clase = "neumo";

    private static bool registrado;

    /// <summary>Engancha los mapeos una sola vez; lo llaman los constructores estáticos de los controles que lo usan.</summary>
    public static void Registrar()
    {
        if (registrado) return;
        registrado = true;
        RegistrarPlataforma();
    }

    static partial void RegistrarPlataforma();
}
