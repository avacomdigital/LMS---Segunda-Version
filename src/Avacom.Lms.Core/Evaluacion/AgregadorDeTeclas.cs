namespace Avacom.Lms.Core.Evaluacion;

/// <summary>Lo que se descartó en UN minuto: las teclas distintas (de la más repetida a la menos) y cuántas veces se pulsaron en total. Es el <c>detalle</c> del incidente <c>tecla_bloqueada</c>.</summary>
/// <param name="Minuto">Número de minuto en el reloj del agregador (milisegundos / 60 000); sólo sirve para ordenar y para las pruebas.</param>
/// <param name="Teclas">Las combinaciones distintas que se descartaron en ese minuto.</param>
/// <param name="Veces">Cuántas pulsaciones descartadas en total en ese minuto.</param>
public sealed record ResumenDeTeclas(long Minuto, string[] Teclas, int Veces)
{
    /// <summary>El <c>detalle</c> tal como lo espera el nodo (modelado-datos.md §4.7): <c>{teclas, veces}</c>.</summary>
    public Dictionary<string, object?> Detalle() => new() { ["teclas"] = Teclas, ["veces"] = Veces };
}

/// <summary>
/// Agrega las teclas descartadas por minuto para informar UN incidente <c>tecla_bloqueada</c> por minuto en vez de uno por pulsación (modelado-datos.md §4.7):
/// un alumno que mantiene pulsada la tecla Windows generaría cientos de renglones, y el profesor necesita «intentó salir con Alt+Tab 6 veces», no el ruido.
///
/// Lógica pura. El reloj se inyecta (milisegundos, monotónico) para probarla sin esperar. <see cref="Registrar"/> es seguro desde cualquier hilo y barato
/// (lo llama el gancho de teclado, que no puede tardar). <see cref="Vaciar"/> entrega los minutos que ya TERMINARON; <see cref="VaciarTodo"/> entrega también el
/// minuto en curso (al soltar el bloqueo, para que nada se pierda).
/// </summary>
public sealed class AgregadorDeTeclas
{
    private const long MsPorMinuto = 60_000;

    private readonly Func<long> reloj;
    private readonly object candado = new();
    private readonly SortedDictionary<long, Dictionary<string, int>> minutos = [];

    /// <param name="reloj">Reloj en milisegundos (por ejemplo <see cref="Environment.TickCount64"/>); sólo importa su avance.</param>
    public AgregadorDeTeclas(Func<long> reloj) => this.reloj = reloj ?? throw new ArgumentNullException(nameof(reloj));

    /// <summary>Anota una tecla descartada en el minuto actual. Un nombre vacío no se anota.</summary>
    public void Registrar(string nombre)
    {
        if (string.IsNullOrEmpty(nombre)) return;
        var minuto = reloj() / MsPorMinuto;
        lock (candado)
        {
            if (!minutos.TryGetValue(minuto, out var teclas)) minutos[minuto] = teclas = [];
            teclas[nombre] = teclas.TryGetValue(nombre, out var veces) ? veces + 1 : 1;
        }
    }

    /// <summary>Hay algo anotado (de cualquier minuto) que aún no se entregó.</summary>
    public bool HayPendientes
    {
        get { lock (candado) return minutos.Count > 0; }
    }

    /// <summary>Entrega y olvida un resumen por cada minuto que ya terminó, del más antiguo al más reciente. El minuto en curso se queda.</summary>
    public IReadOnlyList<ResumenDeTeclas> Vaciar() => Extraer(todo: false);

    /// <summary>Entrega y olvida TODO, también el minuto en curso (al soltar el bloqueo o al cerrar la ventana).</summary>
    public IReadOnlyList<ResumenDeTeclas> VaciarTodo() => Extraer(todo: true);

    private List<ResumenDeTeclas> Extraer(bool todo)
    {
        var actual = reloj() / MsPorMinuto;
        var resumenes = new List<ResumenDeTeclas>();
        lock (candado)
        {
            // Un minuto «terminó» cuando el reloj ya está en uno posterior.
            var listos = minutos.Keys.Where(m => todo || m < actual).ToList();
            foreach (var minuto in listos)
            {
                var teclas = minutos[minuto];
                minutos.Remove(minuto);
                resumenes.Add(new ResumenDeTeclas(
                    minuto,
                    teclas.OrderByDescending(t => t.Value).ThenBy(t => t.Key, StringComparer.Ordinal).Select(t => t.Key).ToArray(),
                    teclas.Values.Sum()));
            }
        }
        return resumenes;
    }
}
