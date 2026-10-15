using System.Globalization;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Reporte de un estudiante (CAP-082): por cada grupo en el que está, cómo va —asistencia, participación, aciertos, evaluaciones, estudio y sus clases— con lo que necesita atención
/// dicho en una línea. Las calificaciones salen en el MODO de su nivel, ya presentadas por el libro (MOD-011): con escala, la nota que el libro presentó (con «provisional» si todavía
/// no se publicó); en modo simple, un símbolo (○ ◐ ●) y un estado, sin ningún número. Quien no presentó no tiene una nota en cero: tiene su estado. Es un reporte nominal por naturaleza
/// y el umbral de privacidad no lo recorta (un solo estudiante no es un agregado).
/// </summary>
public sealed class ReporteAlumnoPage : PaginaDeReporte
{
    private static readonly TablaDeReporte Evaluaciones = new(
        new ColumnaDeTabla("Evaluación", GridLength.Star),
        new ColumnaDeTabla("Estado", new GridLength(230)),
        new ColumnaDeTabla("Resultado", new GridLength(280), Derecha: true));

    private static readonly TablaDeReporte Estudios = new(
        new ColumnaDeTabla("Tarea de estudio", GridLength.Star),
        new ColumnaDeTabla("Estado", new GridLength(200)),
        new ColumnaDeTabla("Avance", new GridLength(200), Derecha: true));

    private static readonly TablaDeReporte Clases = new(
        new ColumnaDeTabla("Cuándo", GridLength.Star),
        new ColumnaDeTabla("Asistió", new GridLength(230)),
        new ColumnaDeTabla("Entregó", new GridLength(160), Derecha: true),
        new ColumnaDeTabla("Aciertos", new GridLength(200), Derecha: true));

    private readonly SelectorDeNodoView _selector = new();
    private NodoAcademico? _nodo;
    private bool _nodoInicial;

    public ReporteAlumnoPage() : base("REPORTES · UN ESTUDIANTE", "Reporte del estudiante", "Cómo va en cada grupo en el que está.")
    {
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReporteAlumnoPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_nodoInicial) { _nodo = NodoDeLaRuta; _nodoInicial = true; }
        if (Parametro("alumno") is not { } alumno)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Falta elegir al estudiante", "Vuelve a Reportes y elige un grupo y un estudiante."));
            return;
        }
        var api = ReportesUi.Api;
        var filtros = await ReportesUi.FiltrosAsync();
        _selector.Mostrar(filtros?.Nodos, _nodo);
        await LeerYPintarAsync(api, () => api.AlumnoAsync(ReportesUi.Actor, alumno, Parametro("grupo"), _nodo), r => Pintar(r), "No se pudo armar el reporte del estudiante");
    }

    private void Pintar(ReporteDeAlumno r)
    {
        Poner(r.Alumno.Rotulo, r.Grupos.Count == 0 ? "No está en ningún grupo activo." : $"Reporte del estudiante · {string.Join(", ", r.Grupos.Select(g => g.Grupo.Rotulo))}");
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeAlumno(r.Alumno.Id, Parametro("grupo"), _nodo));

        EncabezadoFijo(null);
        ContenidoHost.Clear();
        if (r.Grupos.Count == 0)
        {
            ContenidoHost.Add(ReportesUi.Estado("Sin avance que mostrar", MensajesDeReportes.De(new Avacom.Lms.Core.Models.ErrorAula(409, "alumno_sin_grupo", string.Empty, null, null))));
            return;
        }
        foreach (var g in r.Grupos) PintarGrupo(g, r.Grupos.Count > 1);
        ContenidoHost.Add(ReportesUi.ObjetivosNoDisponibles(r.Objetivos));
    }

    private void PintarGrupo(AvanceEnGrupo g, bool variosGrupos)
    {
        if (variosGrupos) ContenidoHost.Add(ReportesUi.Seccion($"Grupo {g.Grupo.Rotulo}", string.IsNullOrWhiteSpace(g.Grupo.Nombre) ? null : g.Grupo.Nombre));
        var s = g.Resumen;

        if (s.Atencion.Count > 0 || !string.IsNullOrWhiteSpace(g.MotivoDeAtencion))
            ContenidoHost.Add(ExamenUi.Aviso("Necesita atención", string.IsNullOrWhiteSpace(g.MotivoDeAtencion) ? string.Join(" · ", s.Atencion.Select(a => a.Texto)) : g.MotivoDeAtencion, Tono.Ambar));

        var bloques = ExamenUi.Fila();
        bloques.Add(ReportesUi.Total("Asistencia", s.ClasesTotal == 0 ? "—" : FormatoDeReportes.DeTotal(s.ClasesAsistidas, s.ClasesTotal), s.PorcentajeAsistencia is null ? "sin clases todavía" : FormatoDeReportes.Porcentaje(s.PorcentajeAsistencia), 220));
        bloques.Add(ReportesUi.Total("Participación", FormatoDeReportes.Porcentaje(s.PorcentajeParticipacion), s.ActividadesRecibidas == 0 ? "sin actividades" : $"entregó {FormatoDeReportes.DeTotal(s.ActividadesEntregadas, s.ActividadesRecibidas)}", 220));
        bloques.Add(ReportesUi.Total("Aciertos", FormatoDeReportes.Porcentaje(s.PorcentajeAciertos), s.PorcentajeAciertos is null ? "nada entregado todavía" : null, 220));
        bloques.Add(ReportesUi.Total("Evaluaciones", s.EvaluacionesTotal == 0 ? "—" : FormatoDeReportes.DeTotal(s.EvaluacionesPresentadas, s.EvaluacionesTotal),
            s.EvaluacionesSinPresentar > 0 ? FormatoDeReportes.Plural(s.EvaluacionesSinPresentar, "sin presentar", "sin presentar") : "presentadas", 220));
        bloques.Add(ReportesUi.Total("Estudio", s.EstudiosTotal == 0 ? "—" : FormatoDeReportes.DeTotal(s.EstudiosCompletados, s.EstudiosTotal),
            s.EstudiosVencidos > 0 ? FormatoDeReportes.Plural(s.EstudiosVencidos, "vencida", "vencidas") : "completadas", 220));
        ContenidoHost.Add(bloques);

        // ---- evaluaciones, en el modo del nivel
        ContenidoHost.Add(ReportesUi.Seccion("Evaluaciones", g.EnModoCalificaciones ? "Con la nota que presentó el libro de calificaciones." : "En este nivel no hay notas: se ve el estado de cada evaluación."));
        if (g.Evaluaciones.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin evaluaciones", EstadosVaciosDeReportes.SinEvaluaciones));
        else ContenidoHost.Add(Evaluaciones.EnTarjeta(g.Evaluaciones.Select((e, i) => FilaDeEvaluacion(e, g.EnModoCalificaciones, i)).ToList()));

        // ---- estudio
        ContenidoHost.Add(ReportesUi.Seccion("Tareas de estudio"));
        if (g.Estudios.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin tareas de estudio", EstadosVaciosDeReportes.SinEstudio));
        else ContenidoHost.Add(Estudios.EnTarjeta(g.Estudios.Select((e, i) => Estudios.Fila([
            ReportesUi.Celda(e.Titulo, medio: true),
            e.Vencida && !e.Completada ? ReportesUi.ConPunto("Vencida", Ds.Peligro) : e.Completada ? ReportesUi.ConPunto("Completada", Ds.Exito) : ReportesUi.ConPunto(FormatoDeReportes.EstadoDeEstudio(e.Estado), ReportesUi.ColorDeAdvertencia),
            ReportesUi.CeldaDePorcentaje(e.AvancePct, Ds.Exito),
        ], cebra: i % 2 == 1)).ToList()));

        // ---- sus clases
        ContenidoHost.Add(ReportesUi.Seccion("Clases", "Tocar una clase abre su reporte."));
        if (g.Clases.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin clases todavía", EstadosVaciosDeReportes.SinClasesDelGrupo));
        else ContenidoHost.Add(Clases.EnTarjeta(g.Clases.Select((c, i) => Clases.Fila([
            ReportesUi.Celda(FormatoDeReportes.FechaCorta(c.FinalizadaEn)),
            c.Asistio ? ReportesUi.ConPunto("Estuvo", Ds.Exito) : ReportesUi.ConPunto("No estuvo", Ds.TintaSuave),
            c.Recibidas == 0 ? "—" : FormatoDeReportes.DeTotal(c.Entregadas, c.Recibidas),
            ReportesUi.CeldaDePorcentaje(c.PorcentajeAciertos, Ds.Exito),
        ], cebra: i % 2 == 1, alTocar: ReportesUi.Seguro(nameof(ReporteAlumnoPage), "AbrirClase", () => Shell.Current.GoToAsync(RutasDeReportes.DeClase(c.SesionId))),
           id: $"reporte-alumno-clase-{c.SesionId}", descripcion: $"Ver el reporte de la clase del {FormatoDeReportes.FechaCorta(c.FinalizadaEn)}")).ToList()));
    }

    private static View FilaDeEvaluacion(EvaluacionDeAlumno e, bool modoCalificaciones, int indice)
    {
        View estado;
        View resultado;
        if (modoCalificaciones)
        {
            estado = e.Presento ? ReportesUi.ConPunto(PresentacionDeNotas.EstadoDeLaNota(e) is { Length: > 0 } t ? t : "Presentada", ColorDelResultado(e)) : ReportesUi.ConPunto(e.SinPresentar ? "Sin presentar" : "Aún sin presentar", e.SinPresentar ? Ds.Peligro : Ds.TintaSuave);
            resultado = ReportesUi.Celda(e.Presento ? PresentacionDeNotas.Texto(e) : FormatoDeReportes.SinDato, derecha: true, medio: e.Presento);
        }
        else
        {
            // Modo simple: un símbolo y un estado, nunca un número ni una letra.
            var simbolo = PresentacionDeNotas.Simbolo(e.Simbolo);
            estado = ReportesUi.Celda(e.Presento ? "Presentada" : e.SinPresentar ? "Sin presentar" : "Aún sin presentar", color: e.SinPresentar ? Ds.Peligro : Ds.Tinta);
            var fila = new HorizontalStackLayout { Spacing = 10, HorizontalOptions = LayoutOptions.End, VerticalOptions = LayoutOptions.Center };
            fila.Add(new Label { Text = simbolo, FontSize = 20, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center });
            fila.Add(ReportesUi.Celda(PresentacionDeNotas.EstadoSimple(e.EstadoSimple), derecha: true));
            resultado = fila;
        }
        return Evaluaciones.Fila([ReportesUi.Celda(e.Titulo, medio: true), estado, resultado], cebra: indice % 2 == 1);
    }

    private static Color ColorDelResultado(EvaluacionDeAlumno e) => e.Estado switch
    {
        EstadosDeResultado.Definitivo => Ds.Exito,
        EstadosDeResultado.Anulado => Ds.Peligro,
        _ => ReportesUi.ColorDeAdvertencia,
    };
}
