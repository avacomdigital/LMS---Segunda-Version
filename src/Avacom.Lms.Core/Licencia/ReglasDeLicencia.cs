using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Licencia;

/// <summary>El aviso que el banner del menú principal muestra: el más importante, su tono y cuántos más hay (en la pantalla de Licencia se ven todos).</summary>
public sealed record AvisoDelBanner(AvisoDeLicencia Aviso, string Texto, TonoDeAviso Tono, int Mas)
{
    /// <summary>El texto completo del banner: el aviso, qué tocar y, si los hay, cuántos avisos más esperan en «Licencia».</summary>
    public string Completo => Mas > 0 ? $"{Texto} {LicenciaTexto.MasAvisos(Mas)}" : Texto;
}

/// <summary>
/// Lo que OPS decide sobre la licencia SIN interfaz y sin decidir nada de la licencia misma (SEC-001: el nodo manda): quién ve el botón y el banner, qué aviso va al banner y con qué
/// tono, por qué vía se instala un archivo y qué acciones se ofrecen. Son AYUDAS para no ofrecer lo que el nodo va a denegar: quien autoriza siempre es el nodo. Puro, sin MAUI.
/// </summary>
public static class ReglasDeLicencia
{
    // ================================================================================================== quién

    /// <summary>
    /// ¿Ve el botón «Licencia» y el banner? La administración y el soporte técnico (los dos tienen <c>license.read</c>). Sin sesión de usuario (el prototipo, Q-34) no hay rol que
    /// consultar: se deja ver y el nodo decide. El profesorado, Reportes y el alumnado no ven nada de la licencia (P-15): sólo el «no disponible por licencia» de un módulo en pausa.
    /// </summary>
    public static bool VeLaLicencia(UsuarioDeSesion? usuario) =>
        usuario is null || usuario.EsAdministracion || usuario.EsTecnico || usuario.Rol is "ADMIN" or "TECHNICIAN";

    /// <summary>¿Es de la administración? (sólo ella renueva, <c>license.renew</c>). Sin sesión no se sabe: no.</summary>
    public static bool EsAdministracion(UsuarioDeSesion? usuario) => usuario is not null && (usuario.EsAdministracion || usuario.Rol == "ADMIN");

    // ================================================================================================== el banner (R-01 · R-10)

    /// <summary>
    /// ¿Se muestra el banner? Sólo a quien ve la licencia y NUNCA con una clase abierta en este equipo: ninguna alerta administrativa interrumpe una sesión activa (Maestro, S4). El banner
    /// vive sólo en el menú principal y sólo se calcula al aparecer el menú, nunca encima de una clase.
    /// </summary>
    public static bool MostrarBanner(UsuarioDeSesion? usuario, bool hayClaseAbierta) => VeLaLicencia(usuario) && !hayClaseAbierta;

    /// <summary>
    /// El orden de importancia de los avisos, el mismo con que el nodo los emite (<c>estado.avisos</c>): primero el error de la fecha adelantada (Q-L13), luego el del estado
    /// (degradada, gracia, liberación pendiente, evaluación, por vencer), el cupo y al final las banderas. Un código que esta versión no conoce va al final, pero no se calla.
    /// </summary>
    private static int Rango(string codigo) => codigo switch
    {
        AvisosDeLicencia.RelojAdelantado => -1,
        AvisosDeLicencia.Degradada => 0,
        AvisosDeLicencia.Gracia => 1,
        AvisosDeLicencia.LiberacionPendiente => 2,
        AvisosDeLicencia.Evaluacion => 3,
        AvisosDeLicencia.PorVencer => 4,
        AvisosDeLicencia.Cupo => 5,
        AvisosDeLicencia.RelojSospechoso => 6,
        AvisosDeLicencia.HuellaParcial => 7,
        AvisosDeLicencia.IntegridadAlterada => 8,
        _ => 9,
    };

    /// <summary>Los avisos que van al banner, del más importante al menos (orden estable: dos del mismo rango quedan como los dio el nodo). En modo de desarrollo, ninguno.</summary>
    public static IReadOnlyList<AvisoDeLicencia> AvisosDelBanner(EstadoLicencia? estado)
    {
        if (estado is null || estado.Ilimitada) return [];
        return estado.AvisosActivos.Where(a => !string.IsNullOrWhiteSpace(a.Codigo)).Select((a, i) => (a, i)).OrderBy(x => Rango(x.a.Codigo)).ThenBy(x => x.i).Select(x => x.a).ToList();
    }

    /// <summary>
    /// El tono de un aviso. La evaluación existe toda la ventana (desde el primer día): informa al principio y pide atención con <c>urgente</c> (7 días o menos). Lo que ya tiene módulos en
    /// pausa es fuerte; el cupo lleno, la gracia, la liberación pendiente y lo que vence en una semana piden atención; lo demás informa.
    /// </summary>
    public static TonoDeAviso TonoDe(AvisoDeLicencia aviso) => aviso.Codigo switch
    {
        AvisosDeLicencia.Degradada or AvisosDeLicencia.RelojAdelantado => TonoDeAviso.Fuerte,
        AvisosDeLicencia.Gracia or AvisosDeLicencia.LiberacionPendiente or AvisosDeLicencia.IntegridadAlterada => TonoDeAviso.Atencion,
        AvisosDeLicencia.Evaluacion => aviso.Urgente == true ? TonoDeAviso.Atencion : TonoDeAviso.Informativo,
        AvisosDeLicencia.PorVencer => aviso.Dias is <= 7 ? TonoDeAviso.Atencion : TonoDeAviso.Informativo,
        AvisosDeLicencia.Cupo => aviso.Porcentaje is >= 100 ? TonoDeAviso.Atencion : TonoDeAviso.Informativo,
        _ => TonoDeAviso.Informativo,
    };

    /// <summary>El aviso del banner: el más importante de <c>avisos[]</c>, con qué tocar y cuántos más hay. Null si no hay nada que avisar (o en modo de desarrollo).</summary>
    public static AvisoDelBanner? Banner(EstadoLicencia? estado, TimeZoneInfo? zona = null)
    {
        var avisos = AvisosDelBanner(estado);
        if (avisos.Count == 0) return null;
        var primero = avisos[0];
        var texto = $"{LicenciaTexto.Aviso(primero, estado, zona)} {LicenciaTexto.LlamadaDelBanner(primero)}";
        return new AvisoDelBanner(primero, texto, TonoDe(primero), avisos.Count - 1);
    }

    // ================================================================================================== qué se ofrece en la pantalla de Licencia

    /// <summary>Una licencia sana: instalada y en uso normal (activa o recién reactivada).</summary>
    public static bool LicenciaSana(EstadoLicencia? estado) =>
        estado is { Licencia: not null, Estado: EstadosDeLicencia.Activa or EstadosDeLicencia.Reactivada } && !estado.Ilimitada;

    /// <summary>
    /// Por qué ruta se instala el archivo elegido: <c>renovar</c> sólo con una licencia sana y la administración (que es quien tiene <c>license.renew</c>); en cualquier otro caso
    /// <c>activar</c>, que también reactiva el mismo archivo y, para la administración, renueva con uno posterior de la misma licencia. El nodo decide qué hace con el archivo.
    /// </summary>
    public static string Via(EstadoLicencia? estado, UsuarioDeSesion? usuario) =>
        LicenciaSana(estado) && EsAdministracion(usuario) ? ViasDeInstalacion.Renovar : ViasDeInstalacion.Activar;

    /// <summary>[Activar o renovar]: siempre que el nodo verifique licencias (en modo de desarrollo no hay nada que activar).</summary>
    public static bool OfrecerActivacion(EstadoLicencia? estado) => estado is not null && !estado.Ilimitada;

    /// <summary>[Guardar copia de la licencia] (CAP-111): hace falta una licencia instalada que copiar.</summary>
    public static bool OfrecerCopia(EstadoLicencia? estado) => estado is { Licencia: not null } && !estado.Ilimitada;

    /// <summary>[Liberar este equipo] (JRN-020): hace falta una licencia instalada que liberar.</summary>
    public static bool OfrecerLiberar(EstadoLicencia? estado) => estado is { Licencia: not null } && !estado.Ilimitada;

    /// <summary>
    /// [Confirmar la fecha de hoy] (P-06 · Q-L13): sólo con una bandera de reloj. Con <c>reloj_adelantado</c> es la salida cuando la fecha del equipo ES la correcta (el aula se había
    /// quedado atrás): sin confirmarla, el nodo no la acepta ni la guarda. Si la fecha está mal, se corrige en Windows y el aviso se quita solo.
    /// </summary>
    public static bool OfrecerConfirmarFecha(EstadoLicencia? estado) =>
        estado is not null && !estado.Ilimitada && (estado.Tiene(BanderasDeLicencia.RelojSospechoso) || estado.Tiene(BanderasDeLicencia.RelojAdelantado));
}
