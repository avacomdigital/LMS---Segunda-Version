using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ops.Actualizacion;

/// <summary>Qué acción espera su única confirmación (aplicar y revertir cambian el aula: se dicen una vez, con sus consecuencias, y se envían una vez).</summary>
public enum AccionPendiente { Ninguna, Aplicar, Revertir }

/// <summary>
/// Todo lo que la pantalla «Actualizaciones» decide sin interfaz (MOD-017, P-19): leer el estado, los paquetes y el historial; elegir un paquete; importar el de la memoria; programar con el
/// selector táctil; aplicar y revertir con UNA confirmación y UN envío aunque se toque dos veces. Quien decide es el nodo (firma, compatibilidad, serie, espacio, clases abiertas, permisos):
/// aquí sólo se pide y se traduce lo que responde, y un error HTTP o de red nunca es una excepción. Usar desde el hilo de la interfaz. Sin MAUI: lo prueba <c>Ops.Tests</c>.
/// </summary>
public sealed class FlujoDeActualizacion(IActualizacionApi api, string actor, UsuarioDeSesion? usuario, Func<bool> hayClaseAbierta, Func<long> ahoraDelNodo, TimeZoneInfo? zona = null)
{
    private int _ocupado;
    private bool _veniaAplicando;
    private bool _mensajeDeRed;

    // ---- lo que se ve
    public EstadoDeActualizacion? Estado { get; private set; }
    public ListaDePaquetes? Paquetes { get; private set; }
    public FichaDePaquete? Elegida { get; private set; }
    public IReadOnlyList<HechoDeHistorial> Historial { get; private set; } = [];
    /// <summary>Lo último que el nodo o el cliente dijo (un resultado o un problema), listo para la pantalla; null si no hay nada que decir.</summary>
    public MensajeDeActualizacion? Mensaje { get; private set; }
    public bool MensajeEsProblema { get; private set; }
    /// <summary>¿El último intento de leer falló por no llegar al nodo? Entonces se conserva lo último que se vio.</summary>
    public bool SinConexion { get; private set; }

    // ---- la confirmación única
    public AccionPendiente Pendiente { get; private set; }
    public MotivoDeReversion? MotivoElegido { get; private set; }

    /// <summary>Cuántos envíos de acciones ha hecho este flujo (aplicar, revertir, programar, importar…): una prueba comprueba que dos toques son uno.</summary>
    public int Envios { get; private set; }

    public bool Ocupado => Volatile.Read(ref _ocupado) == 1;
    public UsuarioDeSesion? Usuario => usuario;
    public long Ahora => ahoraDelNodo();
    public TimeZoneInfo Zona => zona ?? TimeZoneInfo.Local;

    /// <summary>La frase del paquete elegido, con lo que ESTA persona puede hacer con él (el soporte técnico no aplica: se le dice quién sí).</summary>
    public string FraseDelPaquete(FichaDePaquete ficha) => ActualizacionTexto.FraseDelPaquete(ficha, Ahora, Zona, ReglasDeActualizacion.PuedeAplicar(usuario));

    public AccionesDelPaquete Acciones => Elegida is null ? AccionesDelPaquete.Ninguna : ReglasDeActualizacion.Acciones(Elegida, Estado, usuario, hayClaseAbierta(), Ahora);

    /// <summary>¿Se ofrece traer este candidato de la memoria?</summary>
    public bool PuedeImportar(CandidatoDePaquete candidato) => ReglasDeActualizacion.PuedeImportar(usuario, candidato, Estado);

    public SelectorDeVentana NuevoSelector() => new(Ahora, Zona);

    // ================================================================================================== leer

    /// <summary>
    /// Lee el estado, los paquetes y el historial. Si el estado no llega, se dice por qué y se conserva lo último que se vio (con sin conexión) o nada (con un error del nodo). La ficha
    /// elegida se vuelve a pedir para no mostrar un estado viejo; si el nodo ya no la tiene, se suelta.
    /// </summary>
    public async Task<bool> CargarAsync(CancellationToken ct = default)
    {
        var estado = await api.EstadoAsync(actor ?? string.Empty, ct);
        if (estado is null)
        {
            var error = ActualizacionTexto.DeError(api.UltimoError);
            SinConexion = api.UltimoError is { Estado: 0 };
            if (!SinConexion) { Estado = null; Paquetes = null; Elegida = null; Historial = []; }
            Poner(error, problema: true);
            _mensajeDeRed = SinConexion;
            return false;
        }
        SinConexion = false;
        if (_mensajeDeRed) { Mensaje = null; _mensajeDeRed = false; }       // el aula volvió (se reinicia al aplicar): el aviso de «sin conexión» ya no vale
        var termino = _veniaAplicando && !estado.Aplicando;
        _veniaAplicando = estado.Aplicando;
        Estado = estado;
        RelojNodo.Aprender(estado.ServidorEn);
        // El resto se lee aunque falle: sin la lista de paquetes la pantalla igual muestra el estado y los módulos.
        Paquetes = await api.PaquetesAsync(actor ?? string.Empty, ct) ?? Paquetes;
        Historial = (await api.HistorialAsync(actor ?? string.Empty, 8, null, ct))?.HechosOVacio ?? Historial;
        if (Elegida is not null) await ReleerElegidaAsync(ct);
        // Lo que se estaba aplicando (o revirtiendo) terminó: el aula vuelve sola y aquí se dice cómo quedó, sin que nadie tenga que adivinarlo.
        if (termino && Elegida is not null && Elegida.Estado is not (EstadosDePaquete.Aplicando or EstadosDePaquete.Verificado or EstadosDePaquete.Programado))
            Poner(ActualizacionTexto.Terminada(Elegida), problema: Elegida.Estado is not EstadosDePaquete.Aplicado);
        return true;
    }

    private async Task ReleerElegidaAsync(CancellationToken ct)
    {
        var id = Elegida!.PaqueteId;
        var ficha = await api.PaqueteAsync(actor ?? string.Empty, id, ct);
        if (ficha is not null) Elegida = ficha;
        else if (api.UltimoError is { Estado: 404 }) Elegida = null;
        // con otro error (sin red) se conserva la ficha que se tenía
    }

    /// <summary>Elige un paquete ya importado y pide su ficha completa (con historial). Si no se puede leer, se dice y se conserva la ficha anterior.</summary>
    public async Task<bool> ElegirAsync(string paqueteId, CancellationToken ct = default)
    {
        var ficha = await api.PaqueteAsync(actor ?? string.Empty, paqueteId, ct);
        if (ficha is null)
        {
            Poner(ActualizacionTexto.DeError(api.UltimoError), problema: true);
            return false;
        }
        Elegida = ficha;
        Cancelar();
        Mensaje = null;
        return true;
    }

    public void SoltarElegida() { Elegida = null; Cancelar(); }

    // ================================================================================================== importar y programar

    /// <summary>Trae al nodo el paquete de la memoria y lo verifica. Un paquete rechazado (sin firma, alterado…) se dice con su motivo y no se guarda nada.</summary>
    public async Task<bool> ImportarAsync(string candidatoId, CancellationToken ct = default)
    {
        if (!Tomar()) return false;
        try
        {
            Envios++;
            var ficha = await api.ImportarAsync(actor ?? string.Empty, candidatoId, ct);
            if (ficha is null)
            {
                Poner(ActualizacionTexto.DeError(api.UltimoError), problema: true);
                await RefrescarSinFallarAsync(ct);                    // un rechazo deja su fila en el historial
                return false;
            }
            Elegida = ficha;
            Cancelar();
            Poner(ActualizacionTexto.Importado(ficha, ReglasDeActualizacion.PuedeAplicar(usuario)), problema: ficha.Estado == EstadosDePaquete.Incompatible);
            await RefrescarSinFallarAsync(ct);
            return true;
        }
        finally { Soltar_(); }
    }

    public async Task<bool> ProgramarAsync(SelectorDeVentana ventana, CancellationToken ct = default)
    {
        if (Elegida is null || !ventana.EsValida) return false;
        if (!Tomar()) return false;
        try
        {
            Envios++;
            var ficha = await api.ProgramarAsync(actor ?? string.Empty, Elegida.PaqueteId, ventana.Desde, ventana.Hasta, ct);
            if (ficha is null) { Poner(ActualizacionTexto.DeError(api.UltimoError), problema: true); return false; }
            Elegida = ficha;
            Poner(ActualizacionTexto.Programado(ficha, Ahora, Zona), problema: false);
            await RefrescarSinFallarAsync(ct);
            return true;
        }
        finally { Soltar_(); }
    }

    public async Task<bool> DesprogramarAsync(CancellationToken ct = default)
    {
        if (Elegida is null) return false;
        if (!Tomar()) return false;
        try
        {
            Envios++;
            var ficha = await api.DesprogramarAsync(actor ?? string.Empty, Elegida.PaqueteId, ct);
            if (ficha is null) { Poner(ActualizacionTexto.DeError(api.UltimoError), problema: true); return false; }
            Elegida = ficha;
            Poner(ActualizacionTexto.Desprogramado, problema: false);
            await RefrescarSinFallarAsync(ct);
            return true;
        }
        finally { Soltar_(); }
    }

    // ================================================================================================== aplicar y revertir (una sola confirmación)

    /// <summary>Pide confirmar «Aplicar ahora». Sólo si el paquete se puede aplicar (si no, no hay nada que confirmar).</summary>
    public bool PedirAplicar()
    {
        if (!Acciones.Aplicar) return false;
        Pendiente = AccionPendiente.Aplicar;
        MotivoElegido = null;
        Mensaje = null;
        return true;
    }

    /// <summary>Pide confirmar «Volver a la versión anterior»; el motivo se elige de la lista cerrada y viaja como la nota obligatoria.</summary>
    public bool PedirRevertir()
    {
        if (!Acciones.Revertir) return false;
        Pendiente = AccionPendiente.Revertir;
        MotivoElegido = null;
        Mensaje = null;
        return true;
    }

    public void ElegirMotivo(MotivoDeReversion motivo)
    {
        if (Pendiente == AccionPendiente.Revertir) MotivoElegido = motivo;
    }

    /// <summary>¿Se puede confirmar ya? Revertir pide antes un motivo.</summary>
    public bool PuedeConfirmar => Pendiente == AccionPendiente.Aplicar || (Pendiente == AccionPendiente.Revertir && MotivoElegido is not null);

    public void Cancelar()
    {
        Pendiente = AccionPendiente.Ninguna;
        MotivoElegido = null;
    }

    /// <summary>
    /// La confirmación: envía UNA vez lo que estaba pendiente. Un segundo toque mientras viaja el primero, o sin nada pendiente, no envía nada. Con una clase abierta el nodo responde 409
    /// <c>sesion_activa</c> y se dice que la actualización espera (nunca se interrumpe una clase).
    /// </summary>
    public async Task<bool> ConfirmarAsync(CancellationToken ct = default)
    {
        if (!PuedeConfirmar || Elegida is null) return false;
        if (!Tomar()) return false;
        var accion = Pendiente;
        var motivo = MotivoElegido;
        Cancelar();                                                   // lo pendiente se consume al confirmar: ni un reintento por UI Automation lo repite
        try
        {
            Envios++;
            var ficha = accion == AccionPendiente.Aplicar
                ? await api.AplicarAsync(actor ?? string.Empty, Elegida.PaqueteId, ct)
                : await api.RevertirAsync(actor ?? string.Empty, Elegida.PaqueteId, motivo!.Nota, ct);
            if (ficha is null)
            {
                Poner(ActualizacionTexto.DeError(api.UltimoError), problema: true);
                await RefrescarSinFallarAsync(ct);
                return false;
            }
            Elegida = ficha;
            Poner(accion == AccionPendiente.Aplicar ? ActualizacionTexto.Aplicando(ficha) : ActualizacionTexto.Revirtiendo(ficha), problema: false);
            await RefrescarSinFallarAsync(ct);
            return true;
        }
        finally { Soltar_(); }
    }

    // ================================================================================================== internos

    private bool Tomar() => Interlocked.Exchange(ref _ocupado, 1) == 0;
    private void Soltar_() => Interlocked.Exchange(ref _ocupado, 0);

    private void Poner(MensajeDeActualizacion mensaje, bool problema)
    {
        Mensaje = mensaje;
        MensajeEsProblema = problema;
    }

    /// <summary>Después de una acción se vuelve a leer lo que se ve; si esa lectura falla no se pisa el resultado de la acción.</summary>
    private async Task RefrescarSinFallarAsync(CancellationToken ct)
    {
        var mensaje = Mensaje;
        var problema = MensajeEsProblema;
        await CargarAsync(ct);
        Mensaje = mensaje;
        MensajeEsProblema = problema;
    }
}
