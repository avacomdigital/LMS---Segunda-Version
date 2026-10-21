using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Core.Nodo;

/// <summary>El aviso que el banner del menú principal muestra por el estado del nodo (P-18).</summary>
public sealed record AvisoDelNodo(string Estado, string Texto, TonoDeAviso Tono);

/// <summary>
/// Lo que OPS decide sobre el nodo SIN interfaz y sin decidir nada del nodo mismo (quien manda es el nodo): quién ve el estado del equipo y el banner, qué estados se anuncian y con qué
/// tono, qué acciones se ofrecen y en qué orden se listan los consumidores. Son AYUDAS para no ofrecer lo que el nodo va a denegar: quien autoriza siempre es el nodo. Puro, sin MAUI.
/// </summary>
public static class ReglasDeNodo
{
    // ================================================================================================== quién

    /// <summary>
    /// ¿Ve el estado del nodo y el banner? La administración y el soporte técnico (los dos tienen <c>node.health.read</c>). Sin sesión de usuario (el prototipo, Q-34) no hay rol que
    /// consultar: se deja ver y el nodo decide. El profesorado, Reportes y el alumnado no ven nada del nodo: ningún aviso de plataforma interrumpe una clase.
    /// </summary>
    public static bool VeElNodo(UsuarioDeSesion? usuario) => usuario is null || usuario.EsAdministracion || usuario.EsTecnico || usuario.Rol is "ADMIN" or "TECHNICIAN";

    /// <summary>¿Es de la administración? (reprocesa sin escalada). Sin sesión no se sabe: no.</summary>
    public static bool EsAdministracion(UsuarioDeSesion? usuario) => usuario is not null && (usuario.EsAdministracion || usuario.Rol == "ADMIN");

    /// <summary>
    /// ¿Se ofrece [Reprocesar] y [Reproducir]? A la administración y al técnico (que lo recibe por escalada temporal: si no la tiene, el nodo responde «sin permiso» y la pantalla lo dice
    /// con qué hacer). Sin sesión, se ofrece y el nodo decide.
    /// </summary>
    public static bool OfrecerReproceso(UsuarioDeSesion? usuario) => VeElNodo(usuario);

    // ================================================================================================== el banner (R-01)

    /// <summary>¿Se muestra el banner? Sólo a quien ve el nodo y NUNCA con una clase abierta en este equipo: ninguna alerta de plataforma interrumpe una sesión activa.</summary>
    public static bool MostrarBanner(UsuarioDeSesion? usuario, bool hayClaseAbierta) => VeElNodo(usuario) && !hayClaseAbierta;

    /// <summary>El aviso del banner: sólo «restringido» (fuerte) y «en recuperación» (atención). Operativo, arrancando o sin respuesta: nada (no se inventa un aviso).</summary>
    public static AvisoDelNodo? Banner(NodoEnSalud? salud)
    {
        var texto = NodoTexto.Banner(salud);
        if (salud is null || texto is null) return null;
        return new AvisoDelNodo(salud.Estado, texto, salud.Estado == EstadosDelNodo.Restringido ? TonoDeAviso.Fuerte : TonoDeAviso.Atencion);
    }

    // ================================================================================================== la pestaña «Estado del equipo»

    /// <summary>El orden de importancia de los estados de un consumidor: el peor primero.</summary>
    private static int Rango(string estado) => estado switch
    {
        EstadosDeConsumidor.Suspendido => 0,
        EstadosDeConsumidor.Reconstruyendose => 1,
        EstadosDeConsumidor.Rezagado => 2,
        EstadosDeConsumidor.AlDia => 3,
        _ => 4,
    };

    /// <summary>Los consumidores del peor estado al mejor y, a igual estado, el que más pendientes tiene primero (orden estable).</summary>
    public static IReadOnlyList<ConsumidorDeCola> Ordenados(IEnumerable<ConsumidorDeCola> consumidores) =>
        consumidores.Select((c, i) => (c, i)).OrderBy(x => Rango(x.c.Estado)).ThenByDescending(x => x.c.Pendientes).ThenBy(x => x.i).Select(x => x.c).ToList();

    /// <summary>¿Hay algo que pida atención en la cola? Un consumidor que no está al día o un evento apartado.</summary>
    public static bool ColaPideAtencion(ColaDelNodo? cola) => cola is not null && (cola.Problemas > 0 || cola.Consumidores.Any(c => c.Estado != EstadosDeConsumidor.AlDia));

    /// <summary>Qué se ofrece para un problema: reprocesar sólo mientras siga apartado.</summary>
    public static bool OfrecerReprocesar(ProblemaDeCola problema, UsuarioDeSesion? usuario) => problema.Apartado && OfrecerReproceso(usuario);
}
