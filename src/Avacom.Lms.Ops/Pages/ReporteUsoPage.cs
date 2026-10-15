using System.Globalization;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Uso de equipos (FUN-142): qué tabletas se usaron en las clases de un periodo y cuánto, y esas clases con su duración. No lleva datos de personas (sólo cuántos estudiantes usaron cada
/// equipo). El periodo se elige con fichas (nadie escribe una fecha); se puede acotar a un grupo y a una materia. Un periodo sin clases cerradas no es un error: dice «No hay clases
/// finalizadas en este periodo. Elige otro periodo.».
/// </summary>
public sealed class ReporteUsoPage : PaginaDeReporte
{
    private static readonly TablaDeReporte Equipos = new(
        new ColumnaDeTabla("Equipo", GridLength.Star),
        new ColumnaDeTabla("Clases", new GridLength(110), Derecha: true),
        new ColumnaDeTabla("Tiempo de uso", new GridLength(160), Derecha: true),
        new ColumnaDeTabla("Estudiantes", new GridLength(140), Derecha: true),
        new ColumnaDeTabla("Último uso", new GridLength(190), Derecha: true),
        new ColumnaDeTabla("Estado", new GridLength(150)));

    private static readonly TablaDeReporte Clases = new(
        new ColumnaDeTabla("Cuándo", new GridLength(180)),
        new ColumnaDeTabla("Grupo", GridLength.Star),
        new ColumnaDeTabla("Duración", new GridLength(150), Derecha: true),
        new ColumnaDeTabla("Estudiantes", new GridLength(140), Derecha: true),
        new ColumnaDeTabla("Tabletas", new GridLength(120), Derecha: true),
        new ColumnaDeTabla("Datos", new GridLength(130)));

    private readonly VerticalStackLayout _filtrosHost = new() { Spacing = 8 };
    private readonly SelectorDeNodoView _selector = new();
    private FiltrosDeReportes? _filtros;
    private string _periodo = PeriodosDeUso.Todo;
    private PeriodoPedido? _personalizado;
    private string? _grupoId;
    private NodoAcademico? _nodo;
    private bool _inicial;

    public ReporteUsoPage() : base("REPORTES · USO DE EQUIPOS", "Uso de equipos", "Qué tabletas se usaron y cuánto, en las clases de un periodo.")
    {
        SelectorHost.Add(_filtrosHost);
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReporteUsoPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    private PeriodoPedido Periodo => _personalizado ?? PeriodosDeUso.Resolver(_periodo, DateTimeOffset.Now);

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_inicial)
        {
            _inicial = true;
            _nodo = NodoDeLaRuta;
            _grupoId = Parametro("grupo");
            var pedido = new PeriodoPedido(RutasDeReportes.NumeroDe(Parametro("desde")), RutasDeReportes.NumeroDe(Parametro("hasta")));
            if (pedido.Desde is not null || pedido.Hasta is not null)
            {
                if (PeriodosDeUso.ClaveDe(pedido, DateTimeOffset.Now) is { } clave) _periodo = clave;
                else _personalizado = pedido;
            }
        }
        var api = ReportesUi.Api;
        _filtros = await ReportesUi.FiltrosAsync();
        PintarFiltros();
        _selector.Mostrar(_filtros?.Nodos, _nodo);
        var periodo = Periodo;
        await LeerYPintarAsync(api, () => api.UsoAsync(ReportesUi.Actor, periodo, _grupoId, _nodo), r => Pintar(r, periodo), "No se pudo armar el reporte de uso",
            e => e?.Codigo == "sin_sesiones_finalizadas" ? ("No hay clases en este periodo", EstadosVaciosDeReportes.SinUso) : null);
    }

    /// <summary>Las fichas de periodo y de grupo: lo elegido sobrevive a cada lectura y tocar otra ficha vuelve a pedir el reporte.</summary>
    private void PintarFiltros()
    {
        _filtrosHost.Clear();
        _filtrosHost.Add(EstudioUi.Eyebrow("PERIODO"));
        var periodos = EstudioUi.Envolver();
        foreach (var (clave, rotulo) in PeriodosDeUso.Fichas)
            periodos.Add(EstudioUi.Chip(rotulo, _personalizado is null && _periodo == clave, ReportesUi.Seguro(nameof(ReporteUsoPage), "Periodo", () => ElegirPeriodoAsync(clave)), $"reporte-uso-periodo-{clave}"));
        if (_personalizado is not null)
            periodos.Add(EstudioUi.Chip("Periodo guardado", true, () => Task.CompletedTask, "reporte-uso-periodo-guardado"));
        _filtrosHost.Add(periodos);

        if (_filtros is { Grupos.Count: > 1 } f)
        {
            _filtrosHost.Add(EstudioUi.Eyebrow("GRUPO"));
            var grupos = EstudioUi.Envolver();
            grupos.Add(EstudioUi.Chip("Todos", _grupoId is null, ReportesUi.Seguro(nameof(ReporteUsoPage), "Grupo", () => ElegirGrupoAsync(null)), "reporte-uso-grupo-todos"));
            foreach (var g in ListasDeReportes.Grupos(f.Grupos, null))
            {
                var id = g.Id;
                grupos.Add(EstudioUi.Chip(g.Rotulo, _grupoId == id, ReportesUi.Seguro(nameof(ReporteUsoPage), "Grupo", () => ElegirGrupoAsync(id)), $"reporte-uso-grupo-{g.Codigo}"));
            }
            _filtrosHost.Add(grupos);
        }
    }

    private async Task ElegirPeriodoAsync(string clave)
    {
        if (_personalizado is null && _periodo == clave) return;
        (_periodo, _personalizado) = (clave, null);
        await CargarAsync(forzar: true);
    }

    private async Task ElegirGrupoAsync(string? id)
    {
        if (_grupoId == id) return;
        _grupoId = id;
        await CargarAsync(forzar: true);
    }

    private void Pintar(ReporteDeUso r, PeriodoPedido periodo)
    {
        var ambito = _grupoId is not null && _filtros?.Grupos.FirstOrDefault(g => g.Id == _grupoId) is { } grupo ? $" · grupo {grupo.Rotulo}" : string.Empty;
        Poner("Uso de equipos", $"{(_personalizado is null ? PeriodosDeUso.Rotulo(_periodo) : "Periodo guardado")}{ambito} · {FormatoDeReportes.Plural(r.Totales.Clases, "clase finalizada", "clases finalizadas")}");
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeUso(periodo, _grupoId));

        EncabezadoFijo(null);
        ContenidoHost.Clear();
        var t = r.Totales;
        var totales = ExamenUi.Fila();
        totales.Add(ReportesUi.Total("Clases", Num(t.Clases), null, 200));
        totales.Add(ReportesUi.Total("Tabletas usadas", Num(t.Equipos), null, 200));
        totales.Add(ReportesUi.Total("Tiempo total", FormatoDeReportes.Duracion(t.TiempoTotalMs), "sumando todas las clases", 230));
        totales.Add(ReportesUi.Total("Duración media", FormatoDeReportes.Duracion(t.DuracionMediaMs), "por clase", 200));
        ContenidoHost.Add(totales);

        ContenidoHost.Add(ReportesUi.Seccion("Equipos", "Sin datos de personas: sólo cuántos estudiantes usaron cada tableta."));
        if (r.Equipos.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin equipos", EstadosVaciosDeReportes.SinEquipos));
        else ContenidoHost.Add(Equipos.EnTarjeta(r.Equipos.Select((e, i) => Equipos.Fila([
            ReportesUi.Celda(e.Nombre, medio: true),
            Num(e.Clases),
            FormatoDeReportes.Duracion(e.TiempoTotalMs),
            Num(e.Alumnos),
            e.UltimoUsoEn is { } u ? FormatoDeReportes.FechaCorta(u) : "—",
            e.Bloqueado ? ReportesUi.ConPunto("Bloqueada", Ds.Peligro) : e.Activo ? ReportesUi.ConPunto("Activa", Ds.Exito) : ReportesUi.ConPunto("Sin conexión", Ds.TintaSuave),
        ], cebra: i % 2 == 1)).ToList()));

        ContenidoHost.Add(ReportesUi.Seccion("Clases", "Tocar una clase abre su reporte."));
        if (r.Clases.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin clases", EstadosVaciosDeReportes.SinUso));
        else ContenidoHost.Add(Clases.EnTarjeta(r.Clases.Select((c, i) => Clases.Fila([
            ReportesUi.Celda(FormatoDeReportes.FechaCorta(c.FinalizadaEn)),
            ReportesUi.Celda(c.Grupo?.Rotulo ?? "Sin grupo", medio: true),
            FormatoDeReportes.Duracion(c.DuracionMs),
            Num(c.Participantes),
            Num(c.Equipos),
            c.Incompleta ? ExamenUi.Pildora("Incompleto", Tono.Ambar, 13) : ExamenUi.Pildora("Completo", Tono.Exito, 13),
        ], cebra: i % 2 == 1, alTocar: ReportesUi.Seguro(nameof(ReporteUsoPage), "AbrirClase", () => Shell.Current.GoToAsync(RutasDeReportes.DeClase(c.SesionId))),
           id: $"reporte-uso-clase-{c.SesionId}", descripcion: $"Ver el reporte de la clase del {FormatoDeReportes.FechaCorta(c.FinalizadaEn)}")).ToList()));
    }

    private static string Num(int n) => n.ToString(CultureInfo.InvariantCulture);
}
