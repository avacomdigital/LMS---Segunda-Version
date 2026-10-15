namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// Lo que se va marcando en el teclado numérico táctil de una puntuación (el nodo principal no tiene teclado): dígitos, un solo separador decimal y borrar. Guarda el
/// texto con punto decimal (lo que entiende <c>GradebookTexto.LeerPuntaje</c>, que también acepta la coma) y lo muestra con coma. Impide lo que nunca será válido
/// (más de tres cifras enteras, más de dos decimales, ceros a la izquierda); lo demás —pasarse de 100, por ejemplo— lo dice la validación con palabras. Sin MAUI.
/// </summary>
internal sealed class EntradaDecimal
{
    public const int MaximoDeEnteros = 3;
    public const int MaximoDeDecimales = 2;

    /// <summary>El texto marcado, con punto decimal: «», «8», «85.», «85.25».</summary>
    public string Texto { get; private set; } = string.Empty;

    /// <summary>Lo que se ve en pantalla: el mismo texto con coma decimal.</summary>
    public string Mostrado => Texto.Replace('.', ',');

    public bool EstaVacia => Texto.Length == 0;

    private int PosicionDelSeparador => Texto.IndexOf('.');

    /// <summary>Marca un dígito. Devuelve falso si no cabe (no cambia nada).</summary>
    public bool Digito(char digito)
    {
        if (digito is < '0' or > '9') return false;
        var separador = PosicionDelSeparador;
        if (separador >= 0)
        {
            if (Texto.Length - separador - 1 >= MaximoDeDecimales) return false;
            Texto += digito;
            return true;
        }
        // Parte entera: «0» seguido de otro dígito lo reemplaza (nadie escribe «07»), y hay a lo sumo tres cifras.
        if (Texto == "0")
        {
            if (digito == '0') return false;
            Texto = digito.ToString();
            return true;
        }
        if (Texto.Length >= MaximoDeEnteros) return false;
        Texto += digito;
        return true;
    }

    /// <summary>Marca el separador decimal. Sin nada marcado, empieza con «0.»; con uno ya puesto, no hace nada.</summary>
    public bool Separador()
    {
        if (PosicionDelSeparador >= 0) return false;
        Texto = Texto.Length == 0 ? "0." : Texto + ".";
        return true;
    }

    /// <summary>Borra lo último marcado.</summary>
    public bool Borrar()
    {
        if (Texto.Length == 0) return false;
        Texto = Texto[..^1];
        return true;
    }

    public void Limpiar() => Texto = string.Empty;

    /// <summary>Deja un valor ya conocido (para volver a pintar lo que el profesor tenía escrito). Se descarta lo que no sea un número bien formado.</summary>
    public void Poner(string? texto)
    {
        Limpiar();
        foreach (var c in (texto ?? string.Empty).Replace(',', '.'))
            if (c == '.') Separador(); else Digito(c);
    }
}
