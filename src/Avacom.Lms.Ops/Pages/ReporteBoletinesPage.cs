using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Los boletines académicos de un grupo: uno por estudiante, en orden alfabético, con lo esencial de cada uno (puntos, promedio presentado, cuántas evaluaciones con nota) y «Ver boletín».
/// «Exportar» guarda un archivo por estudiante, todos juntos en un zip (es lo que el profesor entrega a cada familia). Es un reporte nominal; el umbral de privacidad no lo recorta.
/// </summary>
public sealed class ReporteBoletinesPage : PaginaDeReporte
{
    private static readonly TablaDeReporte Estudiantes = new(
        new ColumnaDeTabla("Estudiante", GridLength.Star),
        new ColumnaDeTabla("Evaluaciones", new GridLength(150), Derecha: true),
        new ColumnaDeTabla("Con nota", new GridLength(120), Derecha: true),
        new ColumnaDeTabla("Puntos", new GridLength(170), Derecha: true),
        new ColumnaDeTabla("Promedio", new GridLength(190), Derecha: true),
        new ColumnaDeTabla("Recomendaciones", new GridLength(170)));

    private readonly SelectorDeNodoView _selector = new();
    private NodoAcademico? _nodo;
    private bool _nodoInicial;

    public ReporteBoletinesPage() : base("REPORTES · BOLETINES ACADÉMICOS", "Boletines del grupo", "Un boletín por estudiante. «Exportar» los guarda todos, un archivo por estudiante.")
    {
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReporteBoletinesPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_nodoInicial) { _nodo = NodoDeLaRuta; _nodoInicial = true; }
        if (Parametro("grupo") is not { } grupo)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Falta elegir el grupo", "Vuelve a Reportes, elige «Boletín académico» y un grupo."));
            return;
        }
        var api = ReportesUi.Api;
        var filtros = await ReportesUi.FiltrosAsync();
        _selector.Mostrar(filtros?.Nodos, _nodo);
        await LeerYPintarAsync(api, () => api.BoletinesAsync(ReportesUi.Actor, grupo, _nodo), r => Pintar(r), "No se pudieron armar los boletines del grupo");
    }

    private void Pintar(ReporteDeBoletines r)
    {
        var g = r.Grupo;
        Poner($"Boletines · grupo {g.Rotulo}", string.Join(" · ", new[] { string.IsNullOrWhiteSpace(g.Periodo) ? null : $"periodo {g.Periodo}", r.Plantilla.Nombre, FormatoDeReportes.Plural(r.Totales.Boletines, "boletín", "boletines") }.Where(x => x is not null)));
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeBoletin(g.Id, null, _nodo));
        EncabezadoFijo(null);
        ContenidoHost.Clear();
        ContenidoHost.Add(ExamenUi.Aviso("No son documentos oficiales", (r.Plantilla.Leyenda ?? string.Empty) + " Al exportar se guarda un archivo por estudiante, todos en un zip.", Tono.Info));
        var totales = ExamenUi.Fila();
        totales.Add(ReportesUi.Total("Estudiantes", r.Totales.Estudiantes.ToString(), null, 190));
        totales.Add(ReportesUi.Total("Boletines", r.Totales.Boletines.ToString(), null, 190));
        totales.Add(ReportesUi.Total("Con alguna nota", r.Totales.ConNota.ToString(), null, 190));
        totales.Add(ReportesUi.Total("Plantilla", r.Plantilla.Organizacion, r.Plantilla.Pais is { Length: > 0 } pais ? $"país {pais}" : null, 300));
        ContenidoHost.Add(totales);
        if (r.Boletines.Count == 0)
        {
            ContenidoHost.Add(ReportesUi.Estado("Este grupo todavía no tiene estudiantes", EstadosVaciosDeReportes.SinAlumnos));
            return;
        }
        ContenidoHost.Add(ReportesUi.Seccion("Estudiantes", "Tocar un estudiante abre su boletín completo."));
        ContenidoHost.Add(Estudiantes.EnTarjeta(r.Boletines.Select((b, i) => Fila(g, b, i)).ToList()));
    }

    private View Fila(GrupoResumido g, ModeloDeBoletin b, int indice)
    {
        var res = b.Resumen;
        var recomendaciones = b.Recomendaciones.DelDocente.Sum(o => o.Recomendaciones.Count + (string.IsNullOrWhiteSpace(o.Texto) ? 0 : 1));
        return Estudiantes.Fila([
            ReportesUi.Celda(b.Estudiante.Rotulo, medio: true),
            $"{res.Completadas} de {res.Evaluaciones}",
            b.SinCifras ? "—" : res.ConNota.ToString(),
            b.SinCifras || !res.Bruto.TienePuntos ? "—" : $"{GradebookTexto.Puntaje(res.Bruto.Puntos)} de {GradebookTexto.Puntaje(res.Bruto.PuntosMaximos)}",
            ReportesUi.Celda(b.SinCifras ? "sin cifras" : BoletinTexto.Promedio(res.Presentado) + (res.Presentado?.Desempeno is { Length: > 0 } d ? " · " + d : string.Empty), derecha: true, medio: res.Presentado is not null,
                color: res.Presentado?.CumpleCriterio == false ? Ds.Peligro : null),
            recomendaciones > 0 ? ReportesUi.ConPunto(recomendaciones == 1 ? "1 del profesor" : $"{recomendaciones} del profesor", Ds.Exito) : ReportesUi.ConPunto("Sin recomendaciones", Ds.TintaSuave),
        ], cebra: indice % 2 == 1, alTocar: ReportesUi.Seguro(nameof(ReporteBoletinesPage), "AbrirBoletin", () => Shell.Current.GoToAsync(RutasDeReportes.DeBoletin(b.Estudiante.Id, g.Id, _nodo))),
           id: $"reporte-boletines-alumno-{b.Estudiante.Id}", descripcion: $"Ver el boletín de {b.Estudiante.Rotulo}");
    }
}
