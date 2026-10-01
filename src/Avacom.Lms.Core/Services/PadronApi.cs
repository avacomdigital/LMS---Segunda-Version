using System.Text.Json.Serialization;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Core.Services;

/// <summary>Un estudiante dentro de un grupo, como lo ve la pantalla «Grupos».</summary>
public sealed record EstudiantePadron(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias,
    [property: JsonPropertyName("estado")] string? Estado = null,
    [property: JsonPropertyName("provisional")] bool Provisional = false);

public sealed record GrupoPadron(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("periodo")] string? Periodo,
    [property: JsonPropertyName("nivel_clave")] string? NivelClave,
    [property: JsonPropertyName("activo")] bool Activo,
    [property: JsonPropertyName("estudiantes")] IReadOnlyList<EstudiantePadron> Estudiantes,
    [property: JsonPropertyName("docentes")] int Docentes = 0);

public sealed record EstudianteSinGrupo(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias);

public sealed record OrganizacionPadron(
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre);

/// <summary>Todo lo que la pantalla «Grupos» necesita, en una sola lectura. <c>Instalado</c> falso = el nodo aún no tiene organización.</summary>
public sealed record EstadoPadron(
    [property: JsonPropertyName("instalado")] bool Instalado,
    [property: JsonPropertyName("organizacion")] OrganizacionPadron? Organizacion,
    [property: JsonPropertyName("grupos")] IReadOnlyList<GrupoPadron> Grupos,
    [property: JsonPropertyName("sin_grupo")] IReadOnlyList<EstudianteSinGrupo> SinGrupo);

/// <summary>El estudiante recién registrado. <c>SecretoInicial</c> (el PIN generado) se entrega UNA vez: si no se anota ahora, no vuelve a salir.</summary>
public sealed record EstudianteRegistrado(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("alias")] string Alias,
    [property: JsonPropertyName("grupo_id")] string GrupoId,
    [property: JsonPropertyName("identificador")] string Identificador,
    [property: JsonPropertyName("secreto_inicial")] string? SecretoInicial = null);

public sealed record GrupoCreado(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("codigo")] string Codigo,
    [property: JsonPropertyName("nombre")] string Nombre,
    [property: JsonPropertyName("periodo")] string? Periodo = null,
    [property: JsonPropertyName("nivel_clave")] string? NivelClave = null);

/// <summary>
/// Cliente de <c>/api/acceso/padron/</c> (MOD-001): registrar estudiantes y asociarlos a un grupo desde OPS. Mismas reglas de degradación que el
/// resto de clientes: <c>null</c>/<c>false</c> y el motivo en <see cref="UltimoError"/> (por ejemplo <c>no_instalado</c>, <c>identificador_duplicado</c>,
/// <c>sin_permiso</c>). Con sesión viaja el pase de quien está identificado; sin sesión (prototipo) actúa la administración del aula.
/// </summary>
public interface IPadronApi
{
    Uri BaseUri { get; }
    string? UltimoMotivo { get; }
    ErrorAula? UltimoError { get; }

    Task<EstadoPadron?> EstadoAsync(CancellationToken ct = default);
    Task<GrupoCreado?> CrearGrupoAsync(string nombre, string? nivelClave = null, CancellationToken ct = default);
    Task<EstudianteRegistrado?> RegistrarEstudianteAsync(string nombres, string? apellidos, string? documento, string grupoId, CancellationToken ct = default);
    /// <summary>Un estudiante que ya existe entra además a otro grupo.</summary>
    Task<bool> MatricularAsync(string grupoId, string usuarioId, CancellationToken ct = default);
    Task<bool> RetirarAsync(string grupoId, string usuarioId, CancellationToken ct = default);
    /// <summary>Sólo con el nodo vacío y sin sesión obligatoria: crea la organización de prueba para poder registrar. 409 si ya está instalado.</summary>
    Task<bool> PrepararAulaDePruebaAsync(CancellationToken ct = default);
}

public sealed class PadronApi(HttpClient http, Uri baseUri) : ClienteJson(http, baseUri), IPadronApi
{
    private sealed record Vacio();

    public Task<EstadoPadron?> EstadoAsync(CancellationToken ct = default) => ObtenerAsync<EstadoPadron>("api/acceso/padron/", ct);

    public Task<GrupoCreado?> CrearGrupoAsync(string nombre, string? nivelClave = null, CancellationToken ct = default) =>
        EnviarAsync<GrupoCreado>("api/acceso/padron/grupos/", new { nombre, nivel_clave = string.IsNullOrWhiteSpace(nivelClave) ? null : nivelClave }, ct);

    public Task<EstudianteRegistrado?> RegistrarEstudianteAsync(string nombres, string? apellidos, string? documento, string grupoId, CancellationToken ct = default) =>
        EnviarAsync<EstudianteRegistrado>("api/acceso/padron/estudiantes/",
            new { nombres, apellidos = apellidos ?? string.Empty, documento = documento ?? string.Empty, grupo_id = grupoId }, ct);

    public async Task<bool> MatricularAsync(string grupoId, string usuarioId, CancellationToken ct = default) =>
        await EnviarAsync<System.Text.Json.JsonElement?>($"api/acceso/padron/grupos/{Uri.EscapeDataString(grupoId)}/estudiantes/", new { usuario_id = usuarioId }, ct) is not null;

    public Task<bool> RetirarAsync(string grupoId, string usuarioId, CancellationToken ct = default) =>
        EliminarAsync($"api/acceso/padron/grupos/{Uri.EscapeDataString(grupoId)}/estudiantes/{Uri.EscapeDataString(usuarioId)}/", ct);

    public async Task<bool> PrepararAulaDePruebaAsync(CancellationToken ct = default) =>
        await EnviarAsync<System.Text.Json.JsonElement?>("api/acceso/padron/preparar/", new Vacio(), ct) is not null;
}
