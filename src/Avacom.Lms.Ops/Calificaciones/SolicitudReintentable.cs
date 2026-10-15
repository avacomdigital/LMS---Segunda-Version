namespace Avacom.Lms.Ops.Calificaciones;

/// <summary>
/// La <c>solicitud_id</c> de un cambio que puede tener que reintentarse (idempotencia del nodo: reenviar la MISMA solicitud devuelve lo ya hecho y no duplica). Se
/// pide con la firma de lo que se manda: la misma firma reutiliza el identificador (es un reintento tras perder la señal) y una firma distinta —el profesor cambió el
/// valor o el motivo— es otra operación y estrena identificador. Sólo se suelta al confirmarse con un 2xx. Sin MAUI.
/// </summary>
internal sealed class SolicitudReintentable
{
    private string? _firma;
    private string? _id;

    /// <summary>El identificador de la operación con esta firma: nuevo si es otra operación, el mismo si se reintenta.</summary>
    public string Para(string firma)
    {
        if (_id is null || _firma != firma)
        {
            _firma = firma;
            _id = Guid.NewGuid().ToString();
        }
        return _id;
    }

    /// <summary>¿Mandar esto sería reintentar lo mismo que ya se intentó y no se confirmó?</summary>
    public bool EsReintento(string firma) => _id is not null && _firma == firma;

    /// <summary>La operación se confirmó (2xx): la siguiente, aunque tenga los mismos valores, es otra.</summary>
    public void Soltar()
    {
        _firma = null;
        _id = null;
    }
}
