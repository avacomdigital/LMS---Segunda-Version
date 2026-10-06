using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.Acceso;

/// <summary>Los pasos del acceso del alumno dentro de la tarjeta de <c>ConnectionPage</c> (RF-20…RF-23).</summary>
public enum PasoAcceso
{
    /// <summary>Dirección del aula y «Comprobar conexión» (paso 0, como siempre).</summary>
    Conexion,
    /// <summary>(1) Elegir el grupo en tarjetas grandes.</summary>
    Grupo,
    /// <summary>(2) Tocar el propio nombre en la lista del grupo.</summary>
    Nombre,
    /// <summary>(3) Marcar el PIN (o tocar el dibujo en preescolar).</summary>
    Pin,
    /// <summary>RF-22: el alumno está en «PIN pendiente» y elige el suyo (dos veces).</summary>
    ElegirPin,
    /// <summary>RF-21: «No estoy en la lista · soy nuevo».</summary>
    Nuevo,
    /// <summary>La salida de siempre: código y clave (grupos con contraseña, o quien prefiera escribirlos).</summary>
    Codigo,
}

/// <summary>
/// Lo que contesta cada acción del flujo. <c>Sesion</c> no nula: ya entró. <c>SinConexion</c>: el nodo no respondió y se puede reintentar sin volver a escribir
/// nada (<see cref="FlujoDeAcceso.ReintentarAsync"/>, RF-00e). <c>Sugerencia</c>: el alias libre más parecido (RN-34). <c>PideConfirmar</c>: el PIN nuevo se
/// marcó una vez y falta la segunda.
/// </summary>
public sealed record RespuestaDeAcceso(bool Ok, string? Mensaje = null, bool SinConexion = false, SesionAcceso? Sesion = null, string? Sugerencia = null,
                                       bool PideConfirmar = false)
{
    public static readonly RespuestaDeAcceso Hecho = new(true);
}

/// <summary>
/// El acceso del alumno en la tableta (RF-20…RF-28) sin nada de interfaz, para poder probarlo: elegir grupo, tocar el nombre, marcar el PIN; el alta propia, el
/// PIN pendiente, el visitante y la pausa de la tableta. La pantalla sólo pinta el <see cref="Paso"/> y lo que contesta cada acción.
///
/// <para>Reglas que cumple aquí:</para>
/// <list type="bullet">
/// <item>Antes de pedir la lista, la tableta se presenta ante el nodo (latido de MOD-009): sin tableta registrada el nodo no da nombres (BR-056).</item>
/// <item>Ni el PIN ni la clave se guardan más allá de la acción que los usa; un reintento por falta de red los conserva SÓLO en memoria y <see cref="Limpiar"/>
/// los suelta (RF-00d, BR-053).</item>
/// <item>La pausa por intentos es de la TABLETA (RN-33): se cuenta hacia atrás sin nombrar a nadie, y entrar como visitante sigue disponible.</item>
/// <item>Los textos son los del §5 (<see cref="MensajesDeAcceso"/>, audiencia alumno): qué pasó y qué sigue, sin códigos ni la palabra «error».</item>
/// <item>Nunca se simula un acceso: sin respuesta del nodo no hay sesión (RF-00e).</item>
/// </list>
/// </summary>
public sealed class FlujoDeAcceso
{
    public const string ConfirmaPin = "Márcalo otra vez para confirmar.";
    public const string ConfirmaDibujo = "Tócalo otra vez para confirmar.";
    public const string NoCoincidenPin = "Los dos PIN no son iguales. Márcalo otra vez desde el principio.";
    public const string NoCoincidenDibujo = "No tocaste el mismo dibujo. Elige otra vez desde el principio.";
    public const string PendienteDibujo = "Todavía no tienes dibujo. Elige uno que recuerdes.";
    public const string FaltaNombre = "Escribe tu nombre para continuar.";
    public const string FaltaGrupo = "Elige tu grupo para continuar.";
    public const string FaltaCodigo = "Escribe tu código y tu clave para entrar.";
    public const string CodigoNoCoincide = "Ese código o esa clave no coinciden. Prueba otra vez o pide ayuda a tu profesor.";
    public const string SinGrupos = "Este aula todavía no tiene grupos con alumnos. Entra como visitante o pide ayuda al profesor.";
    private const long PausaPorDefectoSeg = 120;

    private readonly IAccesoApi _api;
    private readonly string _dispositivo;
    private readonly Func<CancellationToken, Task<bool>> _registrarTableta;
    private readonly Func<DateTimeOffset> _reloj;
    private Func<CancellationToken, Task<RespuestaDeAcceso>>? _reintento;
    private (string Nombres, string? Apellidos, string Secreto)? _altaPendiente;
    private PasoAcceso _antesDeSalir = PasoAcceso.Grupo;

    public FlujoDeAcceso(IAccesoApi api, string dispositivo, Func<CancellationToken, Task<bool>> registrarTableta, Func<DateTimeOffset>? reloj = null)
    {
        _api = api;
        _dispositivo = dispositivo;
        _registrarTableta = registrarTableta;
        _reloj = reloj ?? (() => DateTimeOffset.UtcNow);
    }

    // ------------------------------------------------------------------------------------------------------------------------ estado

    public ConfiguracionAcceso? Configuracion { get; private set; }
    public PasoAcceso Paso { get; private set; } = PasoAcceso.Conexion;
    public IReadOnlyList<GrupoDelAula> Grupos { get; private set; } = [];
    public GrupoDelAula? Grupo { get; private set; }
    public IReadOnlyList<AlumnoDeLista> Alumnos { get; private set; } = [];
    public AlumnoDeLista? Alumno { get; private set; }
    /// <summary>El PIN (o dibujo) nuevo que se marca dos veces: «Elegir mi PIN» y «Soy nuevo».</summary>
    public DobleMarcado Doble { get; } = new();
    /// <summary>El alias libre que propuso el nodo cuando el pedido ya existía en el grupo (RN-34).</summary>
    public string? Sugerencia { get; private set; }
    /// <summary>La tableta ya se presentó ante el nodo en esta ejecución.</summary>
    public bool TabletaRegistrada { get; private set; }

    /// <summary>RN-37 · AC-A20: con el autoregistro apagado el botón «Soy nuevo» no aparece.</summary>
    public bool OfreceRegistro => Configuracion?.AutoregistroAlumnos == true && GruposParaRegistro.Count > 0;
    /// <summary>RN-40 · RN-47: «Entrar como visitante» siempre visible, salvo que la institución lo haya apagado.</summary>
    public bool OfreceVisitante => Configuracion?.Visitante == true;
    /// <summary>Los grupos donde un alumno puede crearse solo (los de contraseña se dan de alta con el profesor).</summary>
    public IReadOnlyList<GrupoDelAula> GruposParaRegistro => [.. Grupos.Where(g => g.RegistroAbierto && !g.UsaContrasena)];

    /// <summary>RF-28: el grupo usa dibujos en lugar del teclado numérico.</summary>
    public bool UsaAvatar => Grupo?.UsaAvatar == true;
    /// <summary>RN-31: el PIN del alumno tiene de 4 a 6 dígitos; el grupo dice el mínimo.</summary>
    public int LongitudMinima => Math.Clamp(Grupo?.LongitudPin ?? 4, 4, 6);
    public const int LongitudMaxima = 6;

    /// <summary>RN-33: hasta cuándo espera esta tableta tras varios PIN equivocados (de cualquier alumno).</summary>
    public DateTimeOffset? PausaHasta { get; private set; }
    public bool EnPausa => PausaHasta is { } hasta && hasta > _reloj();
    public int SegundosDePausa => PausaHasta is { } hasta ? (int)Math.Max(0, Math.Ceiling((hasta - _reloj()).TotalSeconds)) : 0;
    /// <summary>«1:43»: lo que dice la cuenta regresiva.</summary>
    public static string Cuenta(int segundos) => $"{Math.Max(0, segundos) / 60}:{Math.Max(0, segundos) % 60:00}";

    /// <summary>Hay una acción que no llegó al nodo y se puede repetir tal cual (RF-00e).</summary>
    public bool PuedeReintentar => _reintento is not null;

    // ------------------------------------------------------------------------------------------------------------------------ pasos

    /// <summary>El aula dijo cómo es (sesión obligatoria, autoregistro, visitante). Se empieza de cero: nada de quien estuvo antes (BR-053).</summary>
    public void Iniciar(ConfiguracionAcceso configuracion)
    {
        Configuracion = configuracion;
        Limpiar();
        Paso = PasoAcceso.Conexion;
    }

    /// <summary>(1) Los grupos que la tableta ofrece. Antes, la tableta se presenta (una vez por ejecución, o de nuevo si el nodo no la reconoce).</summary>
    public async Task<RespuestaDeAcceso> CargarGruposAsync(CancellationToken ct = default)
    {
        _reintento = null;
        if (!TabletaRegistrada) TabletaRegistrada = await PresentarTabletaAsync(ct);
        var grupos = await _api.ListarGruposDelAulaAsync(_dispositivo, false, ct);
        if (grupos is null && _api.UltimoError is { DispositivoNoAutorizado: true } && (TabletaRegistrada = await PresentarTabletaAsync(ct)))
            grupos = await _api.ListarGruposDelAulaAsync(_dispositivo, false, ct);
        if (grupos is null) return Falla(_api.UltimoError, CargarGruposAsync);
        Grupos = [.. grupos.OrderBy(g => g.Nombre, StringComparer.CurrentCultureIgnoreCase)];
        Grupo = null; Alumno = null; Alumnos = []; Doble.Reiniciar();
        Paso = PasoAcceso.Grupo;
        return Grupos.Count == 0 ? new RespuestaDeAcceso(true, SinGrupos) : RespuestaDeAcceso.Hecho;
    }

    /// <summary>(2) Eligió su grupo: se piden los nombres. Un grupo con contraseña no entra por nombre: pasa a «Entrar con mi código».</summary>
    public async Task<RespuestaDeAcceso> ElegirGrupoAsync(GrupoDelAula grupo, CancellationToken ct = default)
    {
        _reintento = null;
        Grupo = grupo; Alumno = null; Doble.Reiniciar();
        if (grupo.UsaContrasena)
        {
            _antesDeSalir = PasoAcceso.Grupo;
            Paso = PasoAcceso.Codigo;
            return RespuestaDeAcceso.Hecho;
        }
        var alumnos = await _api.ListarEstudiantesDelGrupoAsync(grupo.Id, _dispositivo, ct);
        if (alumnos is null) return Falla(_api.UltimoError, c => ElegirGrupoAsync(grupo, c));
        Alumnos = [.. alumnos.OrderBy(a => a.Alias, StringComparer.CurrentCultureIgnoreCase)];
        Paso = PasoAcceso.Nombre;
        return RespuestaDeAcceso.Hecho;
    }

    /// <summary>(3) Tocó su nombre. Si todavía no tiene PIN, lo elige (RN-35); si no, lo marca.</summary>
    public void ElegirAlumno(AlumnoDeLista alumno)
    {
        _reintento = null;
        Alumno = alumno;
        Doble.Reiniciar();
        Paso = alumno.PinPendiente ? PasoAcceso.ElegirPin : PasoAcceso.Pin;
    }

    /// <summary>Marcó su PIN (o tocó su dibujo). Con «PIN pendiente» pasa a elegirlo; con la tableta en pausa no se envía nada.</summary>
    public async Task<RespuestaDeAcceso> EntrarAsync(string secreto, CancellationToken ct = default)
    {
        _reintento = null;
        if (Alumno is not { } alumno) return new RespuestaDeAcceso(false, "Toca tu nombre en la lista.");
        if (EnPausa) return new RespuestaDeAcceso(false, MensajesDeAcceso.Texto(new ErrorAula(423, "dispositivo_en_pausa", string.Empty, null, null), Audiencia.Alumno));
        var sesion = await _api.IniciarSesionAlumnoAsync(alumno.Id, secreto, _dispositivo, ct);
        if (sesion is null && _api.UltimoError is { DispositivoNoAutorizado: true } && (TabletaRegistrada = await PresentarTabletaAsync(ct)))
            sesion = await _api.IniciarSesionAlumnoAsync(alumno.Id, secreto, _dispositivo, ct);
        if (sesion is not null) return Entro(sesion);

        var error = _api.UltimoError;
        if (error is { PinPendiente: true })
        {
            Alumno = alumno with { PinPendiente = true };
            Doble.Reiniciar();
            Paso = PasoAcceso.ElegirPin;
            return new RespuestaDeAcceso(false, UsaAvatar ? PendienteDibujo : MensajesDeAcceso.PinPendiente);
        }
        if (error is { DispositivoEnPausa: true })
            PausaHasta = _reloj().AddSeconds(error.ReintentarEnSeg is { } seg and > 0 ? seg : PausaPorDefectoSeg);
        return Falla(error, c => EntrarAsync(secreto, c));
    }

    /// <summary>RF-22 · RF-21: el PIN nuevo se marca dos veces; a la segunda, si coinciden, se guarda en el nodo y se entra con él.</summary>
    public async Task<RespuestaDeAcceso> MarcarPinNuevoAsync(string secreto, CancellationToken ct = default)
    {
        _reintento = null;
        switch (Doble.Marcar(secreto))
        {
            case EstadoDobleMarcado.PideOtraVez:
                return new RespuestaDeAcceso(false, UsaAvatar ? ConfirmaDibujo : ConfirmaPin, PideConfirmar: true);
            case EstadoDobleMarcado.NoCoinciden:
                return new RespuestaDeAcceso(false, UsaAvatar ? NoCoincidenDibujo : NoCoincidenPin);
        }
        var confirmado = Doble.Valor!;
        Doble.Reiniciar();
        return Paso == PasoAcceso.Nuevo ? await RegistrarConfirmadoAsync(confirmado, ct) : await EstablecerPinAsync(confirmado, ct);
    }

    private async Task<RespuestaDeAcceso> EstablecerPinAsync(string pin, CancellationToken ct)
    {
        _reintento = null;
        if (Alumno is not { } alumno) return new RespuestaDeAcceso(false, "Toca tu nombre en la lista.");
        if (!await _api.EstablecerPinAlumnoAsync(alumno.Id, pin, _dispositivo, ct))
        {
            var error = _api.UltimoError;
            if (error?.Codigo == "pin_ya_establecido")
            {
                // Alguien (o él mismo en otra tableta) ya lo eligió: se marca como cualquier otro.
                Alumno = alumno with { PinPendiente = false };
                Paso = PasoAcceso.Pin;
            }
            return Falla(error, c => EstablecerPinAsync(pin, c));
        }
        Alumno = alumno with { PinPendiente = false };
        Paso = PasoAcceso.Pin;
        return await EntrarAsync(pin, ct);
    }

    // ------------------------------------------------------------------------------------------------------------------------ soy nuevo

    /// <summary>«No estoy en la lista · soy nuevo». Si ya había elegido un grupo donde puede registrarse, se queda elegido.</summary>
    public void EmpezarRegistro()
    {
        _reintento = null;
        _antesDeSalir = Paso is PasoAcceso.Nombre or PasoAcceso.Pin or PasoAcceso.ElegirPin ? PasoAcceso.Nombre : PasoAcceso.Grupo;
        if (Grupo is { } g && !GruposParaRegistro.Any(x => x.Id == g.Id)) Grupo = null;
        if (Grupo is null && GruposParaRegistro.Count == 1) Grupo = GruposParaRegistro[0];
        Alumno = null;
        Doble.Reiniciar();
        Sugerencia = null;
        _altaPendiente = null;
        Paso = PasoAcceso.Nuevo;
    }

    /// <summary>En «Soy nuevo», el grupo se elige ahí mismo.</summary>
    public void ElegirGrupoParaRegistro(GrupoDelAula grupo)
    {
        Grupo = grupo;
        Doble.Reiniciar();
    }

    private string? _nombresNuevos, _apellidosNuevos;

    /// <summary>Se guardan (en memoria) el nombre y el apellido escritos; el PIN viene después, dos veces.</summary>
    public RespuestaDeAcceso PrepararRegistro(string? nombres, string? apellidos)
    {
        var limpio = (nombres ?? string.Empty).Trim();
        if (limpio.Length == 0) return new RespuestaDeAcceso(false, FaltaNombre);
        if (Grupo is null) return new RespuestaDeAcceso(false, FaltaGrupo);
        _nombresNuevos = limpio;
        _apellidosNuevos = string.IsNullOrWhiteSpace(apellidos) ? null : apellidos.Trim();
        Doble.Reiniciar();
        return RespuestaDeAcceso.Hecho;
    }

    private Task<RespuestaDeAcceso> RegistrarConfirmadoAsync(string secreto, CancellationToken ct) =>
        _nombresNuevos is null ? Task.FromResult(new RespuestaDeAcceso(false, FaltaNombre)) : RegistrarAsync(_nombresNuevos, _apellidosNuevos, secreto, null, ct);

    /// <summary>RB-17: crea la cuenta y entra con ella. Si el alias ya existe en el grupo, devuelve la sugerencia y conserva lo marcado para aceptarla con un toque.</summary>
    public async Task<RespuestaDeAcceso> RegistrarAsync(string nombres, string? apellidos, string secreto, string? alias = null, CancellationToken ct = default)
    {
        _reintento = null;
        if (string.IsNullOrWhiteSpace(nombres)) return new RespuestaDeAcceso(false, FaltaNombre);
        if (Grupo is not { } grupo) return new RespuestaDeAcceso(false, FaltaGrupo);
        var nuevo = await _api.RegistrarEstudianteAsync(new RegistroDeAlumno(grupo.Id, nombres.Trim(), apellidos, alias, secreto, _dispositivo), ct);
        if (nuevo is null && _api.UltimoError is { DispositivoNoAutorizado: true } && (TabletaRegistrada = await PresentarTabletaAsync(ct)))
            nuevo = await _api.RegistrarEstudianteAsync(new RegistroDeAlumno(grupo.Id, nombres.Trim(), apellidos, alias, secreto, _dispositivo), ct);
        if (nuevo is null)
        {
            var error = _api.UltimoError;
            if (error is { AliasDuplicado: true })
            {
                _altaPendiente = (nombres.Trim(), apellidos, secreto);
                Sugerencia = error.Texto("sugerencia") ?? error.Sugerencia;
                return new RespuestaDeAcceso(false, MensajesDeAcceso.Texto(error, Audiencia.Alumno), Sugerencia: Sugerencia);
            }
            return Falla(error, c => RegistrarAsync(nombres, apellidos, secreto, alias, c));
        }
        _altaPendiente = null;
        Sugerencia = null;
        Alumno = new AlumnoDeLista(nuevo.Id, nuevo.Alias);
        Paso = PasoAcceso.Pin;
        return await EntrarAsync(secreto, ct);
    }

    /// <summary>RN-34: «Juan Pé.» con un toque, sin volver a escribir ni a marcar nada.</summary>
    public Task<RespuestaDeAcceso> AceptarSugerenciaAsync(CancellationToken ct = default) =>
        _altaPendiente is { } alta && Sugerencia is { Length: > 0 } sugerencia
            ? RegistrarAsync(alta.Nombres, alta.Apellidos, alta.Secreto, sugerencia, ct)
            : Task.FromResult(new RespuestaDeAcceso(false, FaltaNombre));

    // ------------------------------------------------------------------------------------------------------------------------ visitante y código

    /// <summary>RF-23 · RN-41: dos toques, sin PIN ni profesor. Nunca se bloquea, ni con la tableta en pausa (RN-33).</summary>
    public async Task<RespuestaDeAcceso> EntrarComoVisitanteAsync(CancellationToken ct = default)
    {
        _reintento = null;
        var sesion = await _api.EntrarComoVisitanteAsync(_dispositivo, Grupo?.Id, ct);
        if (sesion is null && _api.UltimoError is { DispositivoNoAutorizado: true } && (TabletaRegistrada = await PresentarTabletaAsync(ct)))
            sesion = await _api.EntrarComoVisitanteAsync(_dispositivo, Grupo?.Id, ct);
        return sesion is not null ? Entro(sesion) : Falla(_api.UltimoError, EntrarComoVisitanteAsync);
    }

    /// <summary>«Entrar con mi código»: la salida de siempre (código y clave), sobre todo para los grupos con contraseña.</summary>
    public void EmpezarConCodigo()
    {
        _reintento = null;
        if (Paso != PasoAcceso.Codigo) _antesDeSalir = Paso is PasoAcceso.Conexion ? PasoAcceso.Conexion : Paso is PasoAcceso.Grupo ? PasoAcceso.Grupo : PasoAcceso.Nombre;
        Alumno = null;
        Doble.Reiniciar();
        Paso = PasoAcceso.Codigo;
    }

    public async Task<RespuestaDeAcceso> EntrarConCodigoAsync(string? codigo, string? clave, CancellationToken ct = default)
    {
        _reintento = null;
        var id = (codigo ?? string.Empty).Trim();
        var secreto = clave ?? string.Empty;
        if (id.Length == 0 || secreto.Length == 0) return new RespuestaDeAcceso(false, FaltaCodigo);
        var sesion = await _api.IniciarSesionAsync(id, secreto, _dispositivo, ct: ct);
        if (sesion is not null) return Entro(sesion);
        var error = _api.UltimoError;
        if (error is { Codigo: "credenciales_invalidas" })
            return new RespuestaDeAcceso(false, error.IntentosRestantes is { } quedan and > 0 ? $"{CodigoNoCoincide} {MensajesDeAcceso.Intentos(quedan)}" : CodigoNoCoincide);
        return Falla(error, c => EntrarConCodigoAsync(id, secreto, c));
    }

    // ------------------------------------------------------------------------------------------------------------------------ moverse

    /// <summary>Un paso atrás. Volver nunca deja un PIN marcado a medias.</summary>
    public void Volver()
    {
        _reintento = null;
        Doble.Reiniciar();
        switch (Paso)
        {
            case PasoAcceso.Pin or PasoAcceso.ElegirPin:
                Alumno = null;
                Paso = Alumnos.Count > 0 ? PasoAcceso.Nombre : PasoAcceso.Grupo;
                break;
            case PasoAcceso.Nombre:
                Grupo = null; Alumnos = []; Alumno = null;
                Paso = PasoAcceso.Grupo;
                break;
            case PasoAcceso.Nuevo or PasoAcceso.Codigo:
                _altaPendiente = null; Sugerencia = null; _nombresNuevos = null; _apellidosNuevos = null;
                Paso = _antesDeSalir == PasoAcceso.Nombre && Grupo is not null && Alumnos.Count > 0 ? PasoAcceso.Nombre
                     : _antesDeSalir == PasoAcceso.Conexion ? PasoAcceso.Conexion : PasoAcceso.Grupo;
                if (Paso == PasoAcceso.Grupo) { Grupo = null; Alumnos = []; }
                break;
            case PasoAcceso.Grupo:
                Paso = PasoAcceso.Conexion;
                break;
        }
    }

    /// <summary>Vuelve a la lista de grupos sin nada de quien estuvo antes: ni grupo, ni nombre, ni PIN, ni datos de alta (BR-053). La pausa de la tableta se queda: es de la tableta.</summary>
    public void Limpiar()
    {
        _reintento = null;
        _altaPendiente = null;
        _nombresNuevos = null; _apellidosNuevos = null;
        Sugerencia = null;
        Grupo = null; Alumno = null; Alumnos = [];
        Doble.Reiniciar();
        Paso = Grupos.Count > 0 ? PasoAcceso.Grupo : PasoAcceso.Conexion;
    }

    /// <summary>RF-00e: repite tal cual la última acción que no llegó al nodo.</summary>
    public Task<RespuestaDeAcceso> ReintentarAsync(CancellationToken ct = default) =>
        _reintento is { } accion ? accion(ct) : Task.FromResult(RespuestaDeAcceso.Hecho);

    // ------------------------------------------------------------------------------------------------------------------------ apoyo

    /// <summary>Lo que se dice al alumno: §5 con audiencia alumno, y en preescolar «dibujo» en lugar de «PIN».</summary>
    public string Texto(ErrorAula? error)
    {
        if (UsaAvatar && error is { Codigo: "credenciales_invalidas" })
            return "Ese dibujo no es." + (error.IntentosRestantes is { } quedan and > 0 ? " " + MensajesDeAcceso.Intentos(quedan) : string.Empty);
        if (UsaAvatar && error is { PinPendiente: true }) return PendienteDibujo;
        return MensajesDeAcceso.Texto(error, Audiencia.Alumno);
    }

    private RespuestaDeAcceso Falla(ErrorAula? error, Func<CancellationToken, Task<RespuestaDeAcceso>> reintento)
    {
        var sinRed = error is null || error.Estado == 0;
        // Sólo lo que no llegó al nodo se reintenta tal cual: si el nodo contestó, repetirlo daría la misma respuesta.
        _reintento = sinRed ? reintento : null;
        return new RespuestaDeAcceso(false, sinRed ? MensajesDeAcceso.SinConexion : Texto(error), SinConexion: sinRed);
    }

    private RespuestaDeAcceso Entro(SesionAcceso sesion)
    {
        // Ya entró: nada de lo marcado o escrito sigue en memoria.
        Limpiar();
        return new RespuestaDeAcceso(true, Sesion: sesion);
    }

    private async Task<bool> PresentarTabletaAsync(CancellationToken ct)
    {
        try { return await _registrarTableta(ct); }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested) { return false; }
    }
}
