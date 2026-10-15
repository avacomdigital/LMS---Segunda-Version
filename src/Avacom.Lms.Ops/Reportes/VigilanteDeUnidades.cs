namespace Avacom.Lms.Ops.Reportes;

/// <summary>
/// Avisa cuando se enchufa o se retira una unidad (una memoria USB, un disco externo, una unidad de red que aparece o se cae) para que la pantalla de destinos se refresque sola:
/// quien está frente al equipo no tiene teclado, y que tenga que tocar «Buscar de nuevo» después de conectar la memoria es una vuelta más que se puede ahorrar. Sondea la lista de
/// unidades cada <c>intervalo</c> y compara su FIRMA (cada raíz con su estado de lista, su tipo, su etiqueta y su tamaño) con la del sondeo anterior; el espacio libre NO entra,
/// porque cambia con cada archivo que se escribe y no es un cambio de lo que hay conectado. Si la firma cambia dispara <see cref="Cambio"/>, y nada más.
/// <para>
/// <see cref="Cambio"/> se dispara en una hebra del grupo, NO en la de la pantalla: quien lo escuche debe pasar a la hebra de la interfaz antes de tocar nada. Un fallo del proveedor
/// (se retiró la memoria justo mientras se leía) no es un cambio ni detiene al vigilante: se espera al sondeo siguiente. Un manejador que lanza tampoco lo detiene.
/// </para>
/// </summary>
public sealed class VigilanteDeUnidades : IDisposable
{
    private readonly IProveedorDeUnidades _unidades;
    private readonly TimeSpan _intervalo;
    private readonly object _candado = new();
    private CancellationTokenSource? _parada;
    private bool _iniciado;
    private bool _liberado;
    private string? _firma;

    /// <summary>Se enchufó o se retiró algo. Llega en una hebra del grupo, no en la de la interfaz.</summary>
    public event Action? Cambio;

    public VigilanteDeUnidades(IProveedorDeUnidades unidades, TimeSpan intervalo)
    {
        _unidades = unidades ?? throw new ArgumentNullException(nameof(unidades));
        if (intervalo <= TimeSpan.Zero || intervalo.TotalMilliseconds > uint.MaxValue - 1)
            throw new ArgumentOutOfRangeException(nameof(intervalo), intervalo, "El intervalo de sondeo debe ser mayor que cero y caber en un reloj del sistema.");
        _intervalo = intervalo;
    }

    /// <summary>
    /// Empieza a vigilar. Lo que hay AHORA es la base de comparación (se lee aquí, en la hebra que llama: llamarlo fuera de la de la pantalla), de modo que lo que se enchufe o se
    /// retire después de volver de este método siempre se avisa. Llamarlo otra vez, o después de <see cref="Dispose"/>, no hace nada.
    /// </summary>
    public void Iniciar()
    {
        lock (_candado)
        {
            if (_iniciado || _liberado) return;
            _iniciado = true;
        }

        var baseInicial = LeerFirma();                          // fuera del candado: puede tardar
        CancellationToken parada;
        lock (_candado)
        {
            if (_liberado) return;
            _firma ??= baseInicial;                             // un Sondear() que se adelantó ya dejó su base: esa vale
            _parada = new CancellationTokenSource();
            parada = _parada.Token;
        }
        _ = Task.Run(() => VigilarAsync(parada));
    }

    private async Task VigilarAsync(CancellationToken parada)
    {
        try
        {
            using var reloj = new PeriodicTimer(_intervalo);
            while (await reloj.WaitForNextTickAsync(parada).ConfigureAwait(false))
                Sondear();
        }
        catch (OperationCanceledException)
        {
            // se pidió detener: es la salida normal
        }
        catch
        {
            // nada de lo que pase aquí puede salir del vigilante: una tarea sin dueño que lanza tumba el proceso entero
        }
    }

    /// <summary>
    /// Mira las unidades ya, sin esperar al reloj, y avisa si cambiaron desde la última vez. Devuelve si hubo cambio. Es lo que corre cada tick; las pruebas lo llaman directo para no
    /// depender del tiempo.
    /// </summary>
    internal bool Sondear()
    {
        lock (_candado)
        {
            if (_liberado) return false;                        // ya no se mira nada: ni siquiera se le pregunta al proveedor
        }
        var nueva = LeerFirma();
        if (nueva is null) return false;                        // el proveedor falló: ni cambio ni fin; se vuelve a mirar en el siguiente tick

        bool cambio;
        lock (_candado)
        {
            if (_liberado) return false;
            cambio = _firma is not null && _firma != nueva;     // sin base previa (el proveedor había fallado al iniciar) la primera lectura buena es la base
            _firma = nueva;
        }
        if (cambio) AvisarCambio();
        return cambio;
    }

    private string? LeerFirma()
    {
        try
        {
            var lista = _unidades.Unidades();
            return string.Join('|', lista
                .OrderBy(u => u.Raiz, StringComparer.OrdinalIgnoreCase)
                .Select(u => $"{u.Raiz.ToUpperInvariant()};{u.Lista};{u.TipoEfectivo};{u.Etiqueta};{u.TotalBytes}"));
        }
        catch
        {
            return null;
        }
    }

    private void AvisarCambio()
    {
        var manejadores = Cambio;
        if (manejadores is null) return;
        foreach (var manejador in manejadores.GetInvocationList().Cast<Action>())
        {
            try { manejador(); }
            catch { /* un manejador que falla no debe callar a los demás ni detener la vigilancia */ }
        }
    }

    /// <summary>Deja de vigilar. Se puede llamar varias veces y desde dentro de un manejador de <see cref="Cambio"/> (no espera a que termine nada).</summary>
    public void Dispose()
    {
        CancellationTokenSource? parada;
        lock (_candado)
        {
            if (_liberado) return;
            _liberado = true;
            parada = _parada;
            _parada = null;
        }
        if (parada is null) return;
        try { parada.Cancel(); }
        catch { /* ya estaba cancelada */ }
        parada.Dispose();
    }
}
