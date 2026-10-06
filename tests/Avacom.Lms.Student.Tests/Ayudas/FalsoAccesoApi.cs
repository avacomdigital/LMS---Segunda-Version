using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Student.Tests.Ayudas;

/// <summary>
/// Un nodo de acceso de mentira para el flujo del alumno: grupos, nombres, PIN por alumno, PIN pendiente, alias ocupados, pausa de la tableta tras N fallos y
/// visitante. Cada respuesta deja su <see cref="UltimoError"/> como lo haría <c>AccesoApi</c>. <see cref="SinRed"/> simula que el nodo no contesta.
/// </summary>
internal sealed class FalsoAccesoApi : IAccesoApi
{
    public Uri BaseUri { get; } = new("http://127.0.0.1:8010/");
    public string? UltimoMotivo => UltimoError?.Detalle;
    public ErrorAula? UltimoError { get; private set; }

    public bool SinRed { get; set; }
    public bool TabletaRegistrada { get; set; } = true;
    public int FallosParaPausa { get; set; } = 5;
    public long SegundosDePausa { get; set; } = 120;
    public int Fallos { get; private set; }
    public bool Visitante { get; set; } = true;
    public List<string> Llamadas { get; } = [];

    public List<GrupoDelAula> Grupos { get; } = [];
    public Dictionary<string, List<(AlumnoDeLista Alumno, string? Pin)>> Padron { get; } = [];
    public List<RegistroDeAlumno> Altas { get; } = [];

    public FalsoAccesoApi ConGrupo(string id, string nombre, string tipo = "PIN", int longitud = 4, params (string Id, string Alias, string? Pin)[] alumnos)
    {
        Grupos.Add(new GrupoDelAula(id, id.ToUpperInvariant(), nombre, TipoSecreto: tipo, LongitudPin: longitud, Alumnos: alumnos.Length, RegistroAbierto: true));
        Padron[id] = [.. alumnos.Select(a => (new AlumnoDeLista(a.Id, a.Alias, a.Pin is null), a.Pin))];
        return this;
    }

    private static ErrorAula Error(int estado, string codigo, object? extra = null) =>
        new(estado, codigo, codigo, null, extra is null ? null : JsonSerializer.SerializeToElement(extra));

    private bool Red()
    {
        if (!SinRed) return true;
        UltimoError = new ErrorAula(0, "sin_conexion", "sin red", null, null);
        return false;
    }

    private T? Bien<T>(T valor) { UltimoError = null; return valor; }

    private T? Mal<T>(ErrorAula error) { UltimoError = error; return default; }

    private static SesionAcceso Sesion(string id, string alias, string clase = "NORMAL") =>
        new($"token-{id}", 0, $"s-{id}", new UsuarioDeSesion(id, alias, "STUDENT", "student", 1, ClaseSesion: clase));

    public Task<ConfiguracionAcceso?> ConfiguracionAsync(CancellationToken ct = default) =>
        Task.FromResult(Red() ? Bien(new ConfiguracionAcceso(true, true, AutoregistroAlumnos: true, Visitante: Visitante)) : null);

    public Task<IReadOnlyList<GrupoDelAula>?> ListarGruposDelAulaAsync(string dispositivo, bool paraDocente = false, CancellationToken ct = default)
    {
        Llamadas.Add("grupos");
        if (!Red()) return Task.FromResult<IReadOnlyList<GrupoDelAula>?>(null);
        if (!TabletaRegistrada) return Task.FromResult(Mal<IReadOnlyList<GrupoDelAula>>(Error(403, "dispositivo_no_autorizado")));
        return Task.FromResult(Bien<IReadOnlyList<GrupoDelAula>>(Grupos.ToList()));
    }

    public Task<IReadOnlyList<AlumnoDeLista>?> ListarEstudiantesDelGrupoAsync(string grupoId, string dispositivo, CancellationToken ct = default)
    {
        Llamadas.Add($"alumnos:{grupoId}");
        if (!Red()) return Task.FromResult<IReadOnlyList<AlumnoDeLista>?>(null);
        return Task.FromResult(Bien<IReadOnlyList<AlumnoDeLista>>([.. Padron[grupoId].Select(x => x.Alumno with { PinPendiente = x.Pin is null })]));
    }

    private (string Grupo, int Indice)? Buscar(string usuarioId)
    {
        foreach (var (grupo, lista) in Padron)
            for (var i = 0; i < lista.Count; i++)
                if (lista[i].Alumno.Id == usuarioId) return (grupo, i);
        return null;
    }

    public Task<SesionAcceso?> IniciarSesionAlumnoAsync(string usuarioId, string secreto, string dispositivo, CancellationToken ct = default)
    {
        Llamadas.Add($"login:{usuarioId}");
        if (!Red()) return Task.FromResult<SesionAcceso?>(null);
        if (Fallos >= FallosParaPausa) return Task.FromResult(Mal<SesionAcceso>(Error(423, "dispositivo_en_pausa", new { reintentar_en_seg = SegundosDePausa })));
        if (Buscar(usuarioId) is not { } donde) return Task.FromResult(Mal<SesionAcceso>(Error(401, "credenciales_invalidas")));
        var (alumno, pin) = Padron[donde.Grupo][donde.Indice];
        if (pin is null) return Task.FromResult(Mal<SesionAcceso>(Error(403, "pin_pendiente")));
        if (pin != secreto)
        {
            Fallos++;
            if (Fallos >= FallosParaPausa) return Task.FromResult(Mal<SesionAcceso>(Error(423, "dispositivo_en_pausa", new { reintentar_en_seg = SegundosDePausa })));
            return Task.FromResult(Mal<SesionAcceso>(Error(401, "credenciales_invalidas", new { intentos_restantes = FallosParaPausa - Fallos })));
        }
        return Task.FromResult(Bien(Sesion(alumno.Id, alumno.Alias)));
    }

    public Task<bool> EstablecerPinAlumnoAsync(string usuarioId, string pin, string dispositivo, CancellationToken ct = default)
    {
        Llamadas.Add($"pin:{usuarioId}");
        if (!Red()) return Task.FromResult(false);
        if (Buscar(usuarioId) is not { } donde) { UltimoError = Error(404, "no_encontrado"); return Task.FromResult(false); }
        var actual = Padron[donde.Grupo][donde.Indice];
        if (actual.Pin is not null) { UltimoError = Error(409, "pin_ya_establecido"); return Task.FromResult(false); }
        Padron[donde.Grupo][donde.Indice] = (actual.Alumno with { PinPendiente = false }, pin);
        UltimoError = null;
        return Task.FromResult(true);
    }

    public Task<UsuarioNuevo?> RegistrarEstudianteAsync(RegistroDeAlumno datos, CancellationToken ct = default)
    {
        Llamadas.Add("alta");
        if (!Red()) return Task.FromResult<UsuarioNuevo?>(null);
        var alias = string.IsNullOrWhiteSpace(datos.Alias)
            ? string.IsNullOrWhiteSpace(datos.Apellidos) ? datos.Nombres.Split(' ')[0] : $"{datos.Nombres.Split(' ')[0]} {datos.Apellidos![0]}."
            : datos.Alias!;
        var lista = Padron[datos.GrupoId];
        if (lista.Any(x => string.Equals(x.Alumno.Alias, alias, StringComparison.OrdinalIgnoreCase)))
            return Task.FromResult(Mal<UsuarioNuevo>(Error(409, "alias_duplicado", new { alias, sugerencia = alias.TrimEnd('.') + "é." })));
        Altas.Add(datos);
        var id = $"nuevo-{Altas.Count}";
        lista.Add((new AlumnoDeLista(id, alias), datos.Pin));
        return Task.FromResult(Bien(new UsuarioNuevo(id, alias)));
    }

    public string? GrupoDelVisitante { get; private set; }

    public Task<SesionAcceso?> EntrarComoVisitanteAsync(string dispositivo, string? grupoId = null, CancellationToken ct = default)
    {
        Llamadas.Add("visitante");
        if (!Red()) return Task.FromResult<SesionAcceso?>(null);
        if (!Visitante) return Task.FromResult(Mal<SesionAcceso>(Error(403, "visitante_no_permitido")));
        GrupoDelVisitante = grupoId;
        return Task.FromResult(Bien(Sesion("visita-1", "Visitante · tableta 1", "VISITANTE")));
    }

    public Task<SesionAcceso?> IniciarSesionAsync(string identificador, string secreto, string dispositivo, string? rol = null, string? pinMaestro = null, CancellationToken ct = default)
    {
        Llamadas.Add($"codigo:{identificador}");
        if (!Red()) return Task.FromResult<SesionAcceso?>(null);
        return Task.FromResult(identificador == "A-01" && secreto == "clave"
            ? Bien(Sesion("a01", "Ana R."))
            : Mal<SesionAcceso>(Error(401, "credenciales_invalidas", new { intentos_restantes = 2 })));
    }

    // ---------------------------------------------------------------- lo que el flujo del alumno no usa
    public Task<bool> CerrarSesionAsync(CancellationToken ct = default) => Task.FromResult(true);
    public Task<InstalacionHecha?> InstalarAsync(DatosDeInstalacion datos, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<EstadoPinMaestro?> EstadoPinMaestroAsync(CancellationToken ct = default) => throw new NotSupportedException();
    public Task<CambioDePinMaestro?> CambiarPinMaestroAsync(string pinNuevo, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<UsuarioNuevo?> RegistrarDocenteAsync(RegistroDeDocente datos, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<int?> RestablecerContrasenaDocenteAsync(string pinMaestro, string documento, string secretoNuevo, string dispositivo, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<IReadOnlyList<DocentePorPin>?> ListarDocentesPorPinMaestroAsync(CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> CambiarEstadoDeUsuarioAsync(string usuarioId, string estado, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<ConfirmacionDeUsuario?> ConfirmarUsuarioAsync(string usuarioId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<IReadOnlyList<VisitanteEnClase>?> ListarVisitantesAsync(CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> VincularVisitanteAsync(string visitaId, string alumnoId, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<PoliticaDePerfil?> ConfigurarPoliticaAsync(string perfil, object cambios, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<bool> CambiarMiContrasenaAsync(string secretoActual, string secretoNuevo, CancellationToken ct = default) => throw new NotSupportedException();
    public Task<JsonElement?> OtorgarEscaladaAsync(string usuarioId, string permiso, string alcance, string motivo, long vigenteHastaMs, CancellationToken ct = default) => throw new NotSupportedException();
}
