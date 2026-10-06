using System.Text.Json;
using System.Text.Json.Serialization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>
/// El estado público del PIN maestro (<c>/api/acceso/configuracion/</c>): sin fechas ni días, que son de la administración. <c>PorVencer</c>
/// (a 30 días o menos) sólo enciende la banda del tablero para administración y técnico (RN-08).
/// </summary>
public sealed record EstadoPublicoDelPin(
    [property: JsonPropertyName("configurado")] bool Configurado,
    [property: JsonPropertyName("vencido")] bool Vencido = false,
    [property: JsonPropertyName("por_vencer")] bool PorVencer = false);

/// <summary>Lo que el nodo dice de sí mismo antes de identificarse (PAN-101): si está instalado, si exige sesión (Q-34) y qué puertas de entrada ofrece.</summary>
public sealed record ConfiguracionAcceso(
    [property: JsonPropertyName("instalado")] bool Instalado,
    [property: JsonPropertyName("sesion_obligatoria")] bool SesionObligatoria,
    [property: JsonPropertyName("perfiles")] JsonElement? Perfiles = null,
    [property: JsonPropertyName("inactividad_min")] int? InactividadMin = null,
    [property: JsonPropertyName("pin_maestro")] EstadoPublicoDelPin? PinMaestro = null,
    [property: JsonPropertyName("autoregistro_alumnos")] bool AutoregistroAlumnos = false,
    [property: JsonPropertyName("autoregistro_docentes")] bool AutoregistroDocentes = false,
    [property: JsonPropertyName("visitante")] bool Visitante = false)
{
    /// <summary>Sin PIN maestro configurado el alta y el restablecimiento de profesores no existen: la pantalla ni los ofrece (RN-03).</summary>
    public bool OfreceRegistroDeProfesores => AutoregistroDocentes && PinMaestro is { Configurado: true };
}

public sealed record UsuarioDeSesion(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string? Alias,
    [property: JsonPropertyName("rol")] string? Rol,
    [property: JsonPropertyName("menu")] string? Menu,
    [property: JsonPropertyName("nivel")] int Nivel,
    [property: JsonPropertyName("debe_cambiar_credencial")] bool DebeCambiarCredencial = false,
    [property: JsonPropertyName("clase_sesion")] string? ClaseSesion = null,
    [property: JsonPropertyName("origen")] string? Origen = null,
    [property: JsonPropertyName("confirmado")] bool Confirmado = true,
    [property: JsonPropertyName("provisional")] bool Provisional = false)
{
    /// <summary>RN-40…47: entró como visitante. Lo que haga no entra al expediente de nadie y se retira al cerrar.</summary>
    public bool EsVisitante => string.Equals(ClaseSesion, "VISITANTE", StringComparison.OrdinalIgnoreCase);
    public bool EsAdministracion => string.Equals(Menu, "admin", StringComparison.OrdinalIgnoreCase);
    public bool EsTecnico => string.Equals(Menu, "technician", StringComparison.OrdinalIgnoreCase);
}

/// <summary>La sesión de usuario que abre el login (MOD-001). <c>SesionAnterior</c> existe cuando esta entrada cerró otra de la misma persona (MSG-020/021).</summary>
public sealed record SesionAcceso(
    [property: JsonPropertyName("token")] string Token,
    [property: JsonPropertyName("expira_en")] long ExpiraEn,
    [property: JsonPropertyName("sesion_id")] string SesionId,
    [property: JsonPropertyName("usuario")] UsuarioDeSesion Usuario,
    [property: JsonPropertyName("sesion_anterior")] SesionAnterior? SesionAnterior = null)
{
    public bool CerroOtraSesion => SesionAnterior is not null;
}

/// <summary>El código de un solo uso (60 s) con el que la otra app abre esta misma sesión sin pedir la clave. <c>Menu</c> es el del rol: «student» u otro.</summary>
public sealed record TraspasoDeSesion(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("expira_en_seg")] int ExpiraEnSeg,
    [property: JsonPropertyName("menu")] string? Menu);

public sealed record SesionAnterior(
    [property: JsonPropertyName("sesion_id")] string? SesionId,
    [property: JsonPropertyName("dispositivo")] string? Dispositivo);

// ---------------------------------------------------------------------------------------------------------- PIN maestro e instalación

/// <summary>RB-12: el estado fino del PIN maestro, sólo para quien tiene <c>identity.master_pin.manage</c>. NUNCA trae el PIN ni su huella.</summary>
public sealed record EstadoPinMaestro(
    [property: JsonPropertyName("configurado")] bool Configurado,
    [property: JsonPropertyName("creado_en")] long? CreadoEn = null,
    [property: JsonPropertyName("vence_en")] long? VenceEn = null,
    [property: JsonPropertyName("dias_restantes")] int? DiasRestantes = null,
    [property: JsonPropertyName("vencido")] bool Vencido = false,
    [property: JsonPropertyName("aviso")] bool Aviso = false,
    [property: JsonPropertyName("bloqueado_hasta")] long? BloqueadoHasta = null)
{
    public DateTimeOffset? VenceEl => VenceEn is { } ms ? DateTimeOffset.FromUnixTimeMilliseconds(ms).ToLocalTime() : null;
    public DateTimeOffset? CreadoEl => CreadoEn is { } ms ? DateTimeOffset.FromUnixTimeMilliseconds(ms).ToLocalTime() : null;
}

public sealed record CambioDePinMaestro(
    [property: JsonPropertyName("creado_en")] long CreadoEn,
    [property: JsonPropertyName("vence_en")] long VenceEn,
    [property: JsonPropertyName("dias_restantes")] int DiasRestantes);

/// <summary>Todo lo que hace falta para el primer arranque del nodo (JRN-001): el aula, su primer administrador y el PIN maestro (RN-03).</summary>
public sealed record DatosDeInstalacion(
    string Codigo, string Nombre, string Pais, string Idioma, string ZonaHoraria,
    string AdminDocumento, string AdminNombres, string AdminApellidos, string PinMaestro, string? AdminClave = null);

public sealed record AdministradorInstalado(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias);

/// <summary><c>PasswordInicial</c> (la contraseña generada del administrador) viaja AQUÍ Y NADA MÁS QUE AQUÍ (PAN-204: hoja de un solo uso). El PIN maestro no se devuelve nunca.</summary>
public sealed record InstalacionHecha(
    [property: JsonPropertyName("organizacion")] JsonElement? Organizacion,
    [property: JsonPropertyName("administrador")] AdministradorInstalado Administrador,
    [property: JsonPropertyName("password_inicial")] string? PasswordInicial = null);

// ---------------------------------------------------------------------------------------------------------- profesores

/// <summary>RB-13: el profesor crea su propio usuario. Lo autoriza el PIN maestro, no una sesión.</summary>
public sealed record RegistroDeDocente(
    string PinMaestro, string Documento, string Nombres, string Apellidos, string Secreto, IReadOnlyList<string> Grupos, string Dispositivo);

/// <summary>Una cuenta recién creada (profesor o alumno).</summary>
public sealed record UsuarioNuevo(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias);

public sealed record GrupoCorto(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("nombre")] string Nombre);

/// <summary>RB-15: un profesor que nació con el PIN maestro, para que la administración lo revise o lo suspenda (RN-22).</summary>
public sealed record DocentePorPin(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias,
    [property: JsonPropertyName("estado")] string Estado,
    [property: JsonPropertyName("origen")] string? Origen = null,
    [property: JsonPropertyName("registrado_en")] long RegistradoEn = 0,
    [property: JsonPropertyName("confirmado")] bool Confirmado = false,
    [property: JsonPropertyName("equipo")] string? Equipo = null,
    [property: JsonPropertyName("grupos")] IReadOnlyList<GrupoCorto>? Grupos = null)
{
    public bool Suspendido => string.Equals(Estado, "SUSPENDIDO", StringComparison.OrdinalIgnoreCase);
    public DateTimeOffset RegistradoEl => DateTimeOffset.FromUnixTimeMilliseconds(RegistradoEn).ToLocalTime();
}

// ---------------------------------------------------------------------------------------------------------- alumnos y visitantes

/// <summary>RB-16: un grupo que la tableta ofrece. <c>TipoSecreto</c> dice si pedir teclado numérico (PIN), dibujos (AVATAR) o contraseña (PASSWORD).</summary>
public sealed record GrupoDelAula(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("nivel_clave")] string? NivelClave = null,
    [property: JsonPropertyName("tipo_secreto")] string TipoSecreto = "PIN",
    [property: JsonPropertyName("longitud_pin")] int LongitudPin = 4,
    [property: JsonPropertyName("alumnos")] int Alumnos = 0,
    [property: JsonPropertyName("registro_abierto")] bool RegistroAbierto = false)
{
    public bool UsaAvatar => string.Equals(TipoSecreto, "AVATAR", StringComparison.OrdinalIgnoreCase);
    public bool UsaContrasena => string.Equals(TipoSecreto, "PASSWORD", StringComparison.OrdinalIgnoreCase);
}

/// <summary>RB-16: lo único que la lista de nombres revela de un alumno (D-A8): el alias y si todavía le falta elegir su PIN.</summary>
public sealed record AlumnoDeLista(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias,
    [property: JsonPropertyName("pin_pendiente")] bool PinPendiente = false);

/// <summary>RB-17: el alumno que no está en la lista se crea solo con grupo, nombre y PIN (RN-30).</summary>
public sealed record RegistroDeAlumno(string GrupoId, string Nombres, string? Apellidos, string? Alias, string Pin, string Dispositivo);

/// <summary>RN-46: quién entró como visitante y desde qué tableta (el monitor de actividad de OPS).</summary>
public sealed record VisitanteEnClase(
    [property: JsonPropertyName("usuario_id")] string UsuarioId,
    [property: JsonPropertyName("alias")] string Alias,
    [property: JsonPropertyName("sesion_id")] string? SesionId = null,
    [property: JsonPropertyName("dispositivo_id")] string? DispositivoId = null,
    [property: JsonPropertyName("dispositivo")] string? Dispositivo = null,
    [property: JsonPropertyName("emitida_en")] long EmitidaEn = 0);

public sealed record ConfirmacionDeUsuario(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("confirmado_en")] long? ConfirmadoEn);

/// <summary>La política de un perfil tras cambiarla (RB-27). <c>Visitante</c> sólo viene en la del perfil de estudiantes.</summary>
public sealed record PoliticaDePerfil(
    [property: JsonPropertyName("perfil")] string Perfil,
    [property: JsonPropertyName("autoregistro")] bool Autoregistro = false,
    [property: JsonPropertyName("bloqueo_alcance")] string? BloqueoAlcance = null,
    [property: JsonPropertyName("visitante")] bool? Visitante = null);

/// <summary>
/// Cliente de <c>/api/acceso/</c> (MOD-001) para OPS y Student: identificarse (documento, nombre en la lista o visitante), el PIN maestro, el alta propia de
/// profesores y alumnos y lo que la administración necesita para vigilar todo eso. El JWT que devuelve el login queda en <see cref="ClienteJson.Token"/> y
/// viaja en cada petición de todos los clientes del proceso.
///
/// Mismas reglas de degradación que el resto de clientes: <c>null</c>/<c>false</c> y el motivo en <see cref="UltimoError"/> (con su <c>codigo</c>, sus
/// <c>intentos_restantes</c>, <c>reintentar_en_seg</c> y <c>sugerencia</c>; <see cref="MensajesDeAcceso"/> los vuelve palabras de aula). Ninguna pantalla
/// simula un acceso cuando el nodo no contesta (RF-00e).
/// </summary>
public interface IAccesoApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }
    Task<ConfiguracionAcceso?> ConfiguracionAsync(CancellationToken ct = default);

    /// <summary>Documento (o código) y clave. La administración añade <paramref name="pinMaestro"/>: sin él el nodo contesta <c>pin_maestro_requerido</c> DESPUÉS de comprobar la clave.</summary>
    Task<SesionAcceso?> IniciarSesionAsync(string identificador, string secreto, string dispositivo, string? rol = null, string? pinMaestro = null, CancellationToken ct = default);
    /// <summary>PAN-002 · RB-22: el alumno tocó su nombre en la lista y marcó su PIN (o su avatar). Sólo desde una tableta registrada.</summary>
    Task<SesionAcceso?> IniciarSesionAlumnoAsync(string usuarioId, string secreto, string dispositivo, CancellationToken ct = default);
    /// <summary>RB-19: dos toques, sin profesor, PIN ni código. Cuenta efímera con permisos mínimos.</summary>
    Task<SesionAcceso?> EntrarComoVisitanteAsync(string dispositivo, string? grupoId = null, CancellationToken ct = default);
    Task<bool> CerrarSesionAsync(CancellationToken ct = default);
    /// <summary>Pide el código de traspaso de la sesión propia, para abrirla en la otra app (el profesorado en OPS, el alumno en Student).</summary>
    Task<TraspasoDeSesion?> PedirTraspasoAsync(CancellationToken ct = default);
    /// <summary>Canjea un código de traspaso por una sesión nueva en este equipo. El nodo cierra la de origen: el código sirve una sola vez.</summary>
    Task<SesionAcceso?> CanjearTraspasoAsync(string codigo, string dispositivo, CancellationToken ct = default);
    /// <summary>
    /// <c>PUT yo/credencial/</c>: la persona identificada cambia su propia contraseña (la provisional de la hoja de acceso, <c>DebeCambiarCredencial</c>, o
    /// cuando quiera). El nodo cierra sus otras sesiones y conserva ésta. <c>secreto_debil</c> trae las reglas que no se cumplieron.
    /// </summary>
    Task<bool> CambiarMiContrasenaAsync(string secretoActual, string secretoNuevo, CancellationToken ct = default);

    /// <summary>JRN-001: el primer arranque. Sin PIN maestro el nodo no se instala (RN-03).</summary>
    Task<InstalacionHecha?> InstalarAsync(DatosDeInstalacion datos, CancellationToken ct = default);

    Task<EstadoPinMaestro?> EstadoPinMaestroAsync(CancellationToken ct = default);
    Task<CambioDePinMaestro?> CambiarPinMaestroAsync(string pinNuevo, CancellationToken ct = default);

    Task<UsuarioNuevo?> RegistrarDocenteAsync(RegistroDeDocente datos, CancellationToken ct = default);
    /// <summary>RN-24: el profesor restablece su propia contraseña con el PIN maestro; el nodo cierra todas sus sesiones. Devuelve las sesiones cerradas, o null.</summary>
    Task<int?> RestablecerContrasenaDocenteAsync(string pinMaestro, string documento, string secretoNuevo, string dispositivo, CancellationToken ct = default);
    Task<IReadOnlyList<DocentePorPin>?> ListarDocentesPorPinMaestroAsync(CancellationToken ct = default);
    /// <summary>RN-22: suspender (o reactivar) una cuenta.</summary>
    Task<bool> CambiarEstadoDeUsuarioAsync(string usuarioId, string estado, CancellationToken ct = default);

    /// <summary>RB-16: los grupos que la tableta ofrece; <paramref name="paraDocente"/> trae todos los activos (el profesor elige los que dicta).</summary>
    Task<IReadOnlyList<GrupoDelAula>?> ListarGruposDelAulaAsync(string dispositivo, bool paraDocente = false, CancellationToken ct = default);
    Task<IReadOnlyList<AlumnoDeLista>?> ListarEstudiantesDelGrupoAsync(string grupoId, string dispositivo, CancellationToken ct = default);
    Task<UsuarioNuevo?> RegistrarEstudianteAsync(RegistroDeAlumno datos, CancellationToken ct = default);
    /// <summary>RB-18 · RN-35: el alumno cuya cuenta está en «PIN pendiente» elige el suyo.</summary>
    Task<bool> EstablecerPinAlumnoAsync(string usuarioId, string pin, string dispositivo, CancellationToken ct = default);
    Task<ConfirmacionDeUsuario?> ConfirmarUsuarioAsync(string usuarioId, CancellationToken ct = default);
    Task<IReadOnlyList<VisitanteEnClase>?> ListarVisitantesAsync(CancellationToken ct = default);
    /// <summary>RN-44: acredita al alumno lo que hizo una visita.</summary>
    Task<bool> VincularVisitanteAsync(string visitaId, string alumnoId, CancellationToken ct = default);

    /// <summary>RB-27: <paramref name="cambios"/> es un objeto anónimo con los campos de la política (<c>autoregistro</c>, <c>visitante</c>…).</summary>
    Task<PoliticaDePerfil?> ConfigurarPoliticaAsync(string perfil, object cambios, CancellationToken ct = default);

    /// <summary>
    /// BR-101 / PAN-241: concede a <paramref name="usuarioId"/> una escalada temporal de <paramref name="permiso"/> con motivo y caducidad. La
    /// concede quien firma el pase vigente (<see cref="ClienteJson.Token"/>), que debe ser una identidad DISTINTA de quien la recibe.
    /// Es la «autorización de salida» que exige exportar la bitácora (MOD-019, ESC-03). Devuelve la escalada o null (y el motivo en UltimoError).
    /// </summary>
    Task<JsonElement?> OtorgarEscaladaAsync(string usuarioId, string permiso, string alcance, string motivo, long vigenteHastaMs, CancellationToken ct = default);
}

public sealed class AccesoApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IAccesoApi
{
    private sealed record Vacio();
    private sealed record Sesiones([property: JsonPropertyName("sesiones_revocadas")] int SesionesRevocadas);

    public Task<ConfiguracionAcceso?> ConfiguracionAsync(CancellationToken ct = default) =>
        ObtenerAsync<ConfiguracionAcceso>("api/acceso/configuracion/", ct);

    public async Task<SesionAcceso?> IniciarSesionAsync(string identificador, string secreto, string dispositivo, string? rol = null, string? pinMaestro = null, CancellationToken ct = default)
    {
        Token = null;   // un login nuevo no viaja con el pase de la sesión anterior
        var cuerpo = string.IsNullOrWhiteSpace(pinMaestro)
            ? (object)new { identificador, secreto, dispositivo, rol = rol ?? "" }
            : new { identificador, secreto, dispositivo, rol = rol ?? "", pin_maestro = pinMaestro };
        var sesion = await EnviarAsync<SesionAcceso>("api/acceso/sesiones/", cuerpo, ct);
        if (sesion is not null) Token = sesion.Token;
        return sesion;
    }

    public async Task<SesionAcceso?> IniciarSesionAlumnoAsync(string usuarioId, string secreto, string dispositivo, CancellationToken ct = default)
    {
        Token = null;
        var sesion = await EnviarAsync<SesionAcceso>("api/acceso/sesiones/", new { usuario_id = usuarioId, secreto, dispositivo }, ct);
        if (sesion is not null) Token = sesion.Token;
        return sesion;
    }

    public async Task<SesionAcceso?> EntrarComoVisitanteAsync(string dispositivo, string? grupoId = null, CancellationToken ct = default)
    {
        Token = null;
        var cuerpo = string.IsNullOrWhiteSpace(grupoId) ? (object)new { dispositivo } : new { dispositivo, grupo_id = grupoId };
        var sesion = await EnviarAsync<SesionAcceso>("api/acceso/sesiones/visitante/", cuerpo, ct);
        if (sesion is not null) Token = sesion.Token;
        return sesion;
    }

    public Task<TraspasoDeSesion?> PedirTraspasoAsync(CancellationToken ct = default) =>
        EnviarAsync<TraspasoDeSesion>("api/acceso/sesiones/traspaso/", new { }, ct);

    public async Task<SesionAcceso?> CanjearTraspasoAsync(string codigo, string dispositivo, CancellationToken ct = default)
    {
        Token = null;   // el canje es público: no viaja con ningún pase anterior
        var sesion = await EnviarAsync<SesionAcceso>("api/acceso/sesiones/traspaso/canjear/", new { codigo, dispositivo }, ct);
        if (sesion is not null) Token = sesion.Token;
        return sesion;
    }

    public async Task<bool> CambiarMiContrasenaAsync(string secretoActual, string secretoNuevo, CancellationToken ct = default) =>
        await ReemplazarAsync<JsonElement?>("api/acceso/yo/credencial/", new { secreto_actual = secretoActual, secreto_nuevo = secretoNuevo }, ct) is not null;

    public Task<InstalacionHecha?> InstalarAsync(DatosDeInstalacion d, CancellationToken ct = default) =>
        EnviarAsync<InstalacionHecha>("api/acceso/instalacion/", new
        {
            organizacion = new { codigo = d.Codigo, nombre = d.Nombre, pais = d.Pais, idioma = d.Idioma, locale = $"{d.Idioma}-{d.Pais}", zona_horaria = d.ZonaHoraria },
            administrador = new { alias = "Administración", nombres = d.AdminNombres, apellidos = d.AdminApellidos, dni = d.AdminDocumento, password = d.AdminClave ?? string.Empty },
            pin_maestro = d.PinMaestro,
        }, ct);

    public Task<EstadoPinMaestro?> EstadoPinMaestroAsync(CancellationToken ct = default) =>
        ObtenerAsync<EstadoPinMaestro>("api/acceso/pin-maestro/", ct);

    public Task<CambioDePinMaestro?> CambiarPinMaestroAsync(string pinNuevo, CancellationToken ct = default) =>
        ReemplazarAsync<CambioDePinMaestro>("api/acceso/pin-maestro/", new { pin_nuevo = pinNuevo }, ct);

    public Task<UsuarioNuevo?> RegistrarDocenteAsync(RegistroDeDocente d, CancellationToken ct = default) =>
        EnviarAsync<UsuarioNuevo>("api/acceso/docentes/registro/", new
        {
            pin_maestro = d.PinMaestro, documento = d.Documento, nombres = d.Nombres, apellidos = d.Apellidos, secreto = d.Secreto,
            grupos = d.Grupos, dispositivo = d.Dispositivo,
        }, ct);

    public async Task<int?> RestablecerContrasenaDocenteAsync(string pinMaestro, string documento, string secretoNuevo, string dispositivo, CancellationToken ct = default) =>
        (await EnviarAsync<Sesiones>("api/acceso/docentes/restablecer/",
            new { pin_maestro = pinMaestro, documento, secreto_nuevo = secretoNuevo, dispositivo }, ct))?.SesionesRevocadas;

    public Task<IReadOnlyList<DocentePorPin>?> ListarDocentesPorPinMaestroAsync(CancellationToken ct = default) =>
        ObtenerAsync<IReadOnlyList<DocentePorPin>>("api/acceso/docentes/?origen=PIN_MAESTRO", ct);

    public async Task<bool> CambiarEstadoDeUsuarioAsync(string usuarioId, string estado, CancellationToken ct = default) =>
        await ParchearAsync<JsonElement?>($"api/acceso/usuarios/{Uri.EscapeDataString(usuarioId)}/", new { estado }, ct) is not null;

    public Task<IReadOnlyList<GrupoDelAula>?> ListarGruposDelAulaAsync(string dispositivo, bool paraDocente = false, CancellationToken ct = default) =>
        ObtenerAsync<IReadOnlyList<GrupoDelAula>>($"api/acceso/aula/grupos/?dispositivo={Uri.EscapeDataString(dispositivo)}{(paraDocente ? "&para=docente" : string.Empty)}", ct);

    public Task<IReadOnlyList<AlumnoDeLista>?> ListarEstudiantesDelGrupoAsync(string grupoId, string dispositivo, CancellationToken ct = default) =>
        ObtenerAsync<IReadOnlyList<AlumnoDeLista>>($"api/acceso/aula/grupos/{Uri.EscapeDataString(grupoId)}/estudiantes/?dispositivo={Uri.EscapeDataString(dispositivo)}", ct);

    public Task<UsuarioNuevo?> RegistrarEstudianteAsync(RegistroDeAlumno d, CancellationToken ct = default) =>
        EnviarAsync<UsuarioNuevo>("api/acceso/estudiantes/registro/", new
        {
            grupo_id = d.GrupoId, nombres = d.Nombres, apellidos = d.Apellidos ?? string.Empty, alias = d.Alias ?? string.Empty, pin = d.Pin, dispositivo = d.Dispositivo,
        }, ct);

    public async Task<bool> EstablecerPinAlumnoAsync(string usuarioId, string pin, string dispositivo, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>($"api/acceso/estudiantes/{Uri.EscapeDataString(usuarioId)}/pin/", new { pin, dispositivo }, ct) is not null;

    public Task<ConfirmacionDeUsuario?> ConfirmarUsuarioAsync(string usuarioId, CancellationToken ct = default) =>
        EnviarAsync<ConfirmacionDeUsuario>($"api/acceso/usuarios/{Uri.EscapeDataString(usuarioId)}/confirmar/", new Vacio(), ct);

    public Task<IReadOnlyList<VisitanteEnClase>?> ListarVisitantesAsync(CancellationToken ct = default) =>
        ObtenerAsync<IReadOnlyList<VisitanteEnClase>>("api/acceso/visitantes/", ct);

    public async Task<bool> VincularVisitanteAsync(string visitaId, string alumnoId, CancellationToken ct = default) =>
        await EnviarAsync<JsonElement?>($"api/acceso/usuarios/{Uri.EscapeDataString(visitaId)}/vincular/", new { usuario_definitivo_id = alumnoId }, ct) is not null;

    public Task<PoliticaDePerfil?> ConfigurarPoliticaAsync(string perfil, object cambios, CancellationToken ct = default) =>
        ReemplazarAsync<PoliticaDePerfil>($"api/acceso/politicas/{Uri.EscapeDataString(perfil)}/", cambios, ct);

    public Task<JsonElement?> OtorgarEscaladaAsync(string usuarioId, string permiso, string alcance, string motivo, long vigenteHastaMs, CancellationToken ct = default) =>
        EnviarAsync<JsonElement?>($"api/acceso/usuarios/{Uri.EscapeDataString(usuarioId)}/escaladas/",
                                  new { permiso, alcance, motivo, vigente_hasta = vigenteHastaMs }, ct);

    public async Task<bool> CerrarSesionAsync(CancellationToken ct = default)
    {
        var mio = Token;
        var cerrada = await EliminarAsync("api/acceso/sesiones/actual/", ct);
        // Aunque el nodo no conteste, esta app deja de presentarse como esa persona. Pero sólo si el pase sigue siendo el de quien se despide: si otra
        // persona ya se identificó mientras la llamada viajaba, su pase no se toca.
        if (Token == mio) Token = null;
        return cerrada;
    }
}
