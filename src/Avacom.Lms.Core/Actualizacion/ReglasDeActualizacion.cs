using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Actualizacion;

/// <summary>Qué botones se ofrecen para un paquete y, si alguno no se ofrece, por qué (para decirlo en pantalla en vez de esconderlo sin explicación).</summary>
public sealed record AccionesDelPaquete(bool Programar, bool Desprogramar, bool Aplicar, bool Revertir, string? Razon)
{
    public static readonly AccionesDelPaquete Ninguna = new(false, false, false, false, null);
    public bool Alguna => Programar || Desprogramar || Aplicar || Revertir;
}

/// <summary>
/// Lo que OPS decide sobre las actualizaciones SIN interfaz y sin decidir nada de la actualización misma (BR-013, SEC-001: el nodo manda): quién ve la pantalla, qué botones se ofrecen
/// para un paquete según su estado, el permiso y el plazo de 14 días, y cuándo una actualización espera por una clase. Son AYUDAS para no ofrecer lo que el nodo va a denegar: quien
/// autoriza siempre es el nodo (permisos <c>update.*</c>). Puro, sin MAUI.
/// </summary>
public static class ReglasDeActualizacion
{
    // ================================================================================================== quién

    /// <summary>
    /// ¿Ve la pantalla «Actualizaciones»? La administración y el soporte técnico (los dos tienen <c>update.read</c>). Sin sesión de usuario (el prototipo, Q-34) no hay rol que consultar:
    /// se deja ver y el nodo decide. El profesorado, Reportes y el alumnado nunca la ven (P-10).
    /// </summary>
    public static bool VeLasActualizaciones(UsuarioDeSesion? usuario) =>
        usuario is null || usuario.EsAdministracion || usuario.EsTecnico || usuario.Rol is "ADMIN" or "TECHNICIAN";

    /// <summary>¿Es de la administración? (sólo ella programa y aplica sin más: <c>update.schedule</c> y <c>update.apply</c>). Sin sesión no se sabe: no.</summary>
    public static bool EsAdministracion(UsuarioDeSesion? usuario) => usuario is not null && (usuario.EsAdministracion || usuario.Rol == "ADMIN");

    /// <summary>El prototipo sin sesión de usuario deja ofrecer todo y el nodo decide (Q-34).</summary>
    private static bool SinSesion(UsuarioDeSesion? usuario) => usuario is null;

    /// <summary>
    /// ¿Se ofrece traer un paquete de la memoria? La administración y el soporte técnico (<c>update.package.import</c>). Un paquete que ya entró, o con una actualización en marcha,
    /// no se ofrece otra vez.
    /// </summary>
    public static bool PuedeImportar(UsuarioDeSesion? usuario, CandidatoDePaquete candidato, EstadoDeActualizacion? estado) =>
        VeLasActualizaciones(usuario) && !candidato.YaImportado && estado is not { Aplicando: true };

    /// <summary>¿Puede programar una ventana (<c>update.schedule</c>)? La administración.</summary>
    public static bool PuedeProgramar(UsuarioDeSesion? usuario) => SinSesion(usuario) || EsAdministracion(usuario);

    /// <summary>
    /// ¿Puede aplicar o revertir (<c>update.apply</c>)? La administración; el soporte técnico sólo con una autorización temporal (escalada, ESC-01) que esta pantalla no concede: el
    /// botón no se le ofrece y se le dice a quién pedirlo.
    /// </summary>
    public static bool PuedeAplicar(UsuarioDeSesion? usuario) => SinSesion(usuario) || EsAdministracion(usuario);

    // ================================================================================================== qué se ofrece

    /// <summary>
    /// ¿Sigue vigente la reversión? Dentro de los 14 días desde que se aplicó (INV-008), con la hora del nodo. Sin <c>revertible_hasta</c> no hay a qué volver: la instantánea ya se
    /// borró o el paquete no está aplicado.
    /// </summary>
    public static bool DentroDelPlazo(FichaDePaquete ficha, long ahoraMs) => ficha.RevertibleHasta is { } hasta && ahoraMs < hasta;

    /// <summary>
    /// Los botones de un paquete. Aplicar: verificado o programado (se adelanta la ventana), con permiso, sin otra actualización en marcha y sin una clase abierta en ESTE equipo (el nodo
    /// vuelve a comprobarlo y responde 409 <c>sesion_activa</c>: una clase abierta nunca se interrumpe, R-01). Programar: verificado. Quitar la programación: programado. Revertir: aplicado
    /// dentro de los 14 días, o una reversión que falló (se reintenta).
    /// </summary>
    public static AccionesDelPaquete Acciones(FichaDePaquete ficha, EstadoDeActualizacion? estado, UsuarioDeSesion? usuario, bool hayClaseAbierta, long ahoraMs)
    {
        if (!VeLasActualizaciones(usuario)) return AccionesDelPaquete.Ninguna;
        if (ficha.EnCurso || estado is { Aplicando: true }) return new(false, false, false, false, "Hay una actualización en marcha: espera a que termine.");

        var puedeProgramar = PuedeProgramar(usuario);
        var puedeAplicar = PuedeAplicar(usuario);
        var aplicable = ficha.Estado is EstadosDePaquete.Verificado or EstadosDePaquete.Programado;
        var revertible = (ficha.Estado == EstadosDePaquete.Aplicado && ficha.Revertible && DentroDelPlazo(ficha, ahoraMs)) || ficha.Estado == EstadosDePaquete.ReversionFallida;

        var programar = puedeProgramar && ficha.Estado == EstadosDePaquete.Verificado;
        var desprogramar = puedeProgramar && ficha.Estado == EstadosDePaquete.Programado;
        var aplicar = puedeAplicar && aplicable && !hayClaseAbierta;
        var revertir = puedeAplicar && revertible && !hayClaseAbierta;

        string? razon = null;
        if ((aplicable || revertible) && hayClaseAbierta && puedeAplicar)
            razon = "Hay una clase abierta en este equipo. Una clase nunca se interrumpe: termínala, o programa una hora en que el aula esté libre.";
        else if ((aplicable || revertible) && !puedeAplicar)
            razon = "Aplicar o revertir lo hace la administración del colegio (el soporte técnico, con una autorización temporal).";
        else if (ficha.Estado == EstadosDePaquete.Aplicado && !revertible)
            razon = "Ya pasaron los 14 días: desde aquí no se puede volver a la versión anterior.";
        return new(programar, desprogramar, aplicar, revertir, razon);
    }

    /// <summary>¿La pantalla debe volver a leer al nodo con frecuencia? Mientras se aplica una actualización, para ver cuándo termina (el aula vuelve sola).</summary>
    public static bool SeguirMirando(EstadoDeActualizacion? estado) => estado is { Aplicando: true };
}
