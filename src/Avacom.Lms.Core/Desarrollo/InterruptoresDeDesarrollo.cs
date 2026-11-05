namespace Avacom.Lms.Core.Desarrollo;

/// <summary>
/// Los interruptores de desarrollo de Student y OPS (<c>AVACOM_EXAM_NO_LOCKDOWN</c>, <c>AVACOM_ESTUDIO_DEMO</c>, <c>AVACOM_ESTUDIO_DEMO_OFFLINE</c> y la preferencia <c>estudio_demo</c>) apagan
/// cosas que en un aula tienen que estar encendidas: el bloqueo del examen y el nodo real. Hasta la Fase 5 de MOD-018 valían también en un instalador de entrega, donde cualquiera con una
/// consola podía definir la variable y quitarse el bloqueo (hallazgo P-25).
///
/// Regla: un interruptor SÓLO se obedece si la compilación es de DEPURACIÓN o si junto al ejecutable hay un archivo marcador <see cref="NombreDelMarcador"/>. Un instalador de entrega (Release)
/// no lo trae; ponerlo exige escribir en la carpeta del programa (administrador). QA lo crea a propósito para probar OPS y Student en el mismo equipo. Nada de esto toca el kiosco ni el examen
/// de un aula: sin interruptor, todo funciona como siempre.
/// </summary>
public static class InterruptoresDeDesarrollo
{
    /// <summary>El archivo (vacío) que, junto al ejecutable, declara «esto es un equipo de desarrollo o de pruebas».</summary>
    public const string NombreDelMarcador = "AVACOM-DESARROLLO";

#if DEBUG
    private const bool Depuracion = true;
#else
    private const bool Depuracion = false;
#endif

    /// <summary>Quien lee el entorno y busca el marcador: SÓLO las pruebas los sustituyen.</summary>
    public static Func<string, string?> LeerVariable { get; set; } = Environment.GetEnvironmentVariable;
    public static Func<bool> HayMarcador { get; set; } = () => File.Exists(Path.Combine(AppContext.BaseDirectory, NombreDelMarcador));

    /// <summary>La regla pura: ¿se obedecen los interruptores con esta compilación y este marcador?</summary>
    public static bool Obedece(bool compiladoParaDepurar, bool hayMarcador) => compiladoParaDepurar || hayMarcador;

    /// <summary>¿Se obedecen los interruptores de desarrollo en este equipo?</summary>
    public static bool Permitidos => Obedece(Depuracion, HayMarcadorSeguro());

    /// <summary>¿Está encendido este interruptor? Una variable vale «1» SÓLO si los interruptores están permitidos.</summary>
    public static bool Encendido(string variable) => Permitidos && LeerVariable(variable) == "1";

    /// <summary>Una preferencia de desarrollo (<c>estudio_demo</c>): su valor sólo cuenta si los interruptores están permitidos.</summary>
    public static bool Preferencia(bool valorGuardado) => Permitidos && valorGuardado;

    /// <summary>Si alguien definió el interruptor pero no se obedece (un Release sin marcador): para anotarlo en el registro y que quien prueba sepa por qué no hizo efecto.</summary>
    public static bool IgnoradoPorSerEntrega(string variable) => !Permitidos && LeerVariable(variable) == "1";

    private static bool HayMarcadorSeguro()
    {
        try { return HayMarcador(); }
        catch { return false; }       // sin poder mirar, no hay marcador: lo seguro es no obedecer
    }
}
