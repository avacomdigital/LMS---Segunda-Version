namespace Avacom.Lms.Student.Acceso;

public enum EstadoDobleMarcado { PideOtraVez, NoCoinciden, Coinciden }

/// <summary>
/// RF-21 y RF-22: el PIN (o el dibujo) nuevo se marca dos veces. La primera se guarda sólo en memoria; la segunda se compara. Si no coinciden se empieza de
/// cero (no se dice cuál de las dos estaba mal). Nada de esto se escribe en disco ni en registros.
/// </summary>
public sealed class DobleMarcado
{
    private string? _primero;

    /// <summary>Ya se marcó una vez y se espera la confirmación.</summary>
    public bool Confirmando => _primero is not null;

    /// <summary>El valor confirmado (sólo tras <see cref="EstadoDobleMarcado.Coinciden"/>).</summary>
    public string? Valor { get; private set; }

    public EstadoDobleMarcado Marcar(string valor)
    {
        if (_primero is null)
        {
            _primero = valor;
            Valor = null;
            return EstadoDobleMarcado.PideOtraVez;
        }
        var coinciden = string.Equals(_primero, valor, StringComparison.Ordinal);
        _primero = null;
        Valor = coinciden ? valor : null;
        return coinciden ? EstadoDobleMarcado.Coinciden : EstadoDobleMarcado.NoCoinciden;
    }

    public void Reiniciar()
    {
        _primero = null;
        Valor = null;
    }
}
