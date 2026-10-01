using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;

namespace Avacom.Lms.Ops.Examen;

/// <summary>Un alumno del grupo con la tableta que se le conoce, lo que esa tableta declara (<c>null</c>: no declaró su capacidad) y si alcanza el nivel elegido (<c>null</c>: no se sabe qué tableta usará).</summary>
internal sealed record FilaElegible(string AlumnoId, string Rotulo, string? Tableta, string? Capacidad, bool? Alcanza);

/// <summary>
/// El mensaje MSG-036 ANTES de aplicar el examen (Guion, paso 4). <c>GET /asignaciones/{id}/elegibilidad/</c> necesita una asignación ya creada, y al
/// elegir el nivel todavía no existe: aquí se repite la misma cuenta del nodo con lo que OPS ya conoce —el inventario de tabletas con su capacidad
/// declarada (MOD-009), la tableta que cada alumno usa en la clase y la que tiene asignada—. Una vez aplicado el examen, el panel vuelve a preguntar al
/// nodo con <c>ElegibilidadAsync</c>, que es la fuente de verdad. Nunca bloquea: el profesor decide.
/// </summary>
internal sealed record CalculoDeElegibilidad(string Nivel, IReadOnlyList<FilaElegible> Filas, bool InventarioConocido)
{
    public int Alcanzan => Filas.Count(f => f.Alcanza == true);
    public int NoAlcanzan => Filas.Count(f => f.Alcanza == false);
    public int SinTableta => Filas.Count(f => f.Alcanza is null);
    public IEnumerable<FilaElegible> LasQueNoAlcanzan => Filas.Where(f => f.Alcanza == false);

    /// <summary>MSG-036, con el plural que corresponde. Nulo si todas las tabletas conocidas alcanzan.</summary>
    public string? Mensaje => NoAlcanzan == 0 ? null : ExamenTexto.Msg036(NoAlcanzan, Nivel);

    /// <summary>
    /// La cuenta para <paramref name="nivel"/>. La tableta que un alumno usa en la clase gana a la que tiene asignada, como en el nodo; un aparato retirado no cuenta.
    /// Una tableta que no declaró su capacidad cuenta como «abierto» (BR-075): no alcanza supervisado ni controlado.
    /// </summary>
    public static CalculoDeElegibilidad Calcular(GrupoDocente grupo, string nivel, IReadOnlyList<DispositivoAula>? inventario, SesionDeClase? clase)
    {
        nivel = Niveles.Normalizar(nivel);
        var porId = (inventario ?? []).ToDictionary(d => d.Id);
        var filas = new List<FilaElegible>();
        foreach (var alumno in grupo.Alumnos.OrderBy(a => a.Rotulo ?? a.Id, StringComparer.CurrentCultureIgnoreCase))
        {
            DispositivoAula? tableta = null;
            var enClase = clase?.Participantes?.LastOrDefault(p => p.PersonaId == alumno.Id && p.TieneTableta);
            if (enClase?.DispositivoId is { } id) porId.TryGetValue(id, out tableta);
            tableta ??= inventario?.FirstOrDefault(d => d.Activo && d.AsignadoA?.Id == alumno.Id);
            var rotulo = alumno.Rotulo ?? alumno.Id;
            filas.Add(tableta is null
                ? new FilaElegible(alumno.Id, rotulo, null, null, null)
                : new FilaElegible(alumno.Id, rotulo, tableta.NombreVisible, tableta.CapacidadDeclarada ? tableta.CapacidadLegible : null, Niveles.Alcanza(tableta.CapacidadControl, nivel)));
        }
        return new CalculoDeElegibilidad(nivel, filas, inventario is not null);
    }
}
