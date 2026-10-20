using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El boletín académico de UN estudiante (propuesta del CTO, 2026-10-19): un modelo de información común con la plantilla del país y del nivel —Colombia por áreas con los desempeños
/// nacionales, México por campos formativos o disciplinas, o genérica— que responde cuatro preguntas: qué aprendió (resultados por área y por evaluación, con los puntos obtenidos, el
/// porcentaje y la calificación en el sistema configurado), qué competencias alcanzó (logros y aprendizajes pendientes), cómo ha progresado (promedio por curso en cada periodo) y qué debe
/// mejorar (las recomendaciones del profesor). Todo viene ya presentado por el libro: aquí no se convierte ni se promedia nada. NO es un documento oficial y lo dice: es la base para que
/// el profesor arme el que su institución exige. «Exportar» lo guarda como un archivo (xlsx o csv).
/// </summary>
public sealed class ReporteBoletinPage : PaginaDeReporte
{
    private readonly SelectorDeNodoView _selector = new();
    private NodoAcademico? _nodo;
    private bool _nodoInicial;

    public ReporteBoletinPage() : base("REPORTES · BOLETÍN ACADÉMICO", "Boletín académico", "Qué aprendió, qué competencias alcanzó, cómo ha progresado y qué debe mejorar.")
    {
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReporteBoletinPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_nodoInicial) { _nodo = NodoDeLaRuta; _nodoInicial = true; }
        if (Parametro("alumno") is not { } alumno)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Falta elegir al estudiante", "Vuelve a Reportes, elige «Boletín académico», un grupo y un estudiante."));
            return;
        }
        var api = ReportesUi.Api;
        var filtros = await ReportesUi.FiltrosAsync();
        _selector.Mostrar(filtros?.Nodos, _nodo);
        await LeerYPintarAsync(api, () => api.BoletinAsync(ReportesUi.Actor, alumno, Parametro("grupo"), _nodo), r => Pintar(r), "No se pudo armar el boletín del estudiante",
            e => e?.Codigo == "alumno_sin_grupo" ? ("Sin grupo activo", "Ese estudiante no pertenece a ningún grupo activo: no hay boletín que armar.") : null);
    }

    private void Pintar(ReporteDeBoletin r)
    {
        var b = r.Boletin;
        var p = b.Plantilla;
        Poner(b.Estudiante.Rotulo, string.Join(" · ", new[] { $"Grupo {b.Grupo.Rotulo}", string.IsNullOrWhiteSpace(b.Periodo) ? null : $"periodo {b.Periodo}", p.Nombre }.Where(x => x is not null)));
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeBoletin(b.Grupo.Id, b.Estudiante.Id, _nodo));
        EncabezadoFijo(null);
        ContenidoHost.Clear();
        ContenidoHost.Add(ExamenUi.Aviso("No es un documento oficial", b.Leyenda, Tono.Info));
        ContenidoHost.Add(Cabecera(b));
        PintarQueAprendio(b);
        PintarCompetencias(b);
        PintarProgreso(b);
        PintarQueDebeMejorar(b);
        ContenidoHost.Add(ReportesUi.ObjetivosNoDisponibles(r.Objetivos));
    }

    // ------------------------------------------------------------------------------------------------------------------ cabecera

    private static View Cabecera(ModeloDeBoletin b)
    {
        var p = b.Plantilla;
        var pila = new VerticalStackLayout { Spacing = 6 };
        if (!string.IsNullOrWhiteSpace(b.Institucion.Nombre)) pila.Add(ExamenUi.Dato("Institución", b.Institucion.Nombre, 200));
        pila.Add(ExamenUi.Dato("Plantilla", p.Nombre, 200));
        pila.Add(ExamenUi.Dato("Organización", p.Organizacion, 200));
        if (!string.IsNullOrWhiteSpace(p.Marco)) pila.Add(ExamenUi.Dato("Marco de referencia", p.Marco, 200));
        pila.Add(ExamenUi.Dato("Sistema de calificación", b.SinCifras ? "Sin cifras (este nivel no califica con notas)" : GradebookTexto.Sistema(b.Sistema), 200));
        if (p.Periodos.Count > 0) pila.Add(ExamenUi.Dato("Periodos de la institución", string.Join(" · ", p.Periodos), 200));
        if (p.DesempenosNacionales is { Count: > 0 } nacionales) pila.Add(ExamenUi.Dato("Desempeños nacionales", string.Join(" · ", nacionales) + " (la equivalencia la define el SIEE)", 200));
        var r = b.Resumen;
        var totales = ExamenUi.Fila();
        totales.Add(ReportesUi.Total("Evaluaciones", r.Evaluaciones.ToString(), $"{r.Completadas} completadas", 200));
        if (!b.SinCifras)
        {
            totales.Add(ReportesUi.Total("Con nota", r.ConNota.ToString(), r.ConNota > 0 ? $"{r.Aprobadas} cumplen el criterio" + (r.NoAprobadas > 0 ? $" · {r.NoAprobadas} no" : string.Empty) : null, 220));
            totales.Add(ReportesUi.Total("Puntos", r.Bruto.TienePuntos ? $"{GradebookTexto.Puntaje(r.Bruto.Puntos)} de {GradebookTexto.Puntaje(r.Bruto.PuntosMaximos)}" : "—",
                r.Bruto.Porcentaje is { } pct ? FormatoDeReportes.Porcentaje(pct) : "sin puntos todavía", 220));
            totales.Add(ReportesUi.Total("Promedio", BoletinTexto.Promedio(r.Presentado), r.Presentado is null ? "sin nota aún" : BoletinTexto.LecturaDelPromedio(r.Presentado) + " · simple, informativo", 260));
        }
        pila.Add(totales);
        return ReportesUi.Tarjeta(pila);
    }

    // ------------------------------------------------------------------------------------------------------------------ 1 · qué aprendió

    private void PintarQueAprendio(ModeloDeBoletin b)
    {
        var p = b.Plantilla;
        ContenidoHost.Add(ReportesUi.Seccion("1 · ¿Qué aprendió?", b.SinCifras ? $"Resultados por {p.RotuloDeArea.ToLowerInvariant()}: en este nivel se ve si completó cada evaluación, sin cifras."
            : $"Resultados por {p.RotuloDeArea.ToLowerInvariant()}: los puntos obtenidos sobre el máximo, el porcentaje y la calificación en el sistema configurado."));
        if (b.Areas.Count == 0) { ContenidoHost.Add(ReportesUi.Estado("Sin evaluaciones", "Cuando el estudiante presente evaluaciones, aparecerán aquí por área.")); return; }

        var columnas = new List<ColumnaDeTabla> { new(p.RotuloDeArea, new GridLength(200)), new("Curso", GridLength.Star), new("Evaluaciones", new GridLength(120), Derecha: true) };
        if (!b.SinCifras)
        {
            columnas.Add(new("Puntos", new GridLength(140), Derecha: true));
            columnas.Add(new("Porcentaje", new GridLength(150), Derecha: true));
            columnas.Add(new("Calificación", new GridLength(130), Derecha: true));
            columnas.Add(new("Desempeño", new GridLength(140)));
            if (p.DesempenosNacionales is { Count: > 0 }) columnas.Add(new("Nacional", new GridLength(110)));
        }
        else columnas.Add(new("Completadas", new GridLength(120), Derecha: true));
        var tabla = new TablaDeReporte(columnas.ToArray());
        var filas = new List<View>();
        var i = 0;
        foreach (var area in b.Areas)
            foreach (var c in area.Cursos)
            {
                var celdas = new List<object?> { ReportesUi.Celda(area.Rotulo, medio: true), ReportesUi.Celda(c.CursoRotulo), c.Evaluaciones.ToString() };
                if (!b.SinCifras)
                {
                    celdas.Add(c.Bruto.TienePuntos ? $"{GradebookTexto.Puntaje(c.Bruto.Puntos)} de {GradebookTexto.Puntaje(c.Bruto.PuntosMaximos)}" : "—");
                    celdas.Add(ReportesUi.CeldaDePorcentaje(c.Bruto.Porcentaje, Ds.Exito));
                    celdas.Add(ReportesUi.Celda(BoletinTexto.Promedio(c.Presentado), derecha: true, medio: c.Presentado is not null, color: c.CumpleCriterio == false ? Ds.Peligro : null));
                    celdas.Add(c.Desempeno is { Length: > 0 } d ? ReportesUi.ConPunto(d, c.CumpleCriterio == false ? Ds.Peligro : Ds.Exito) : ReportesUi.Celda("—", color: Ds.TintaSuave));
                    if (p.DesempenosNacionales is { Count: > 0 }) celdas.Add(ReportesUi.Celda(c.DesempenoNacional ?? "—", color: c.DesempenoNacional is null ? Ds.TintaSuave : null));
                }
                else celdas.Add(c.Completadas.ToString());
                filas.Add(tabla.Fila(celdas, cebra: i++ % 2 == 1));
            }
        ContenidoHost.Add(tabla.EnTarjeta(filas));

        // ---- cada evaluación
        ContenidoHost.Add(ReportesUi.Seccion("Evaluaciones", "De la más antigua a la más reciente. Una evaluación sin calificar no es un cero."));
        var evaluaciones = new TablaDeReporte(new ColumnaDeTabla("Fecha", new GridLength(120)), new ColumnaDeTabla("Evaluación", GridLength.Star), new ColumnaDeTabla("Curso", new GridLength(220)),
            new ColumnaDeTabla("Estado", new GridLength(170)), new ColumnaDeTabla(b.SinCifras ? "Completada" : "Puntos", new GridLength(150), Derecha: true), new ColumnaDeTabla("Calificación", new GridLength(200), Derecha: true));
        var filasEv = b.Evaluaciones.Select((e, n) => evaluaciones.Fila([
            FormatoDeReportes.FechaCorta(e.Fecha ?? 0), ReportesUi.Celda(e.Titulo, medio: true), ReportesUi.Celda(e.CursoRotulo),
            b.SinCifras ? ReportesUi.ConPunto(GradebookTexto.EstadoSimple(e.EstadoSimple), e.EstadoSimple == EstadosSimples.Completado ? Ds.Exito : Ds.TintaSuave)
                        : ReportesUi.ConPunto(GradebookTexto.Estado(e.Estado), e.Estado == EstadosDeResultado.Definitivo ? Ds.Exito : ReportesUi.ColorDeAdvertencia),
            b.SinCifras ? (e.EstadoSimple == EstadosSimples.Completado ? "Sí" : "No") : (e.Bruto is { TienePuntos: true } br ? $"{GradebookTexto.Puntaje(br.Puntos)} de {GradebookTexto.Puntaje(br.PuntosMaximos)}" : "—"),
            b.SinCifras ? "" : ReportesUi.Celda(e.Presentada is { Length: > 0 } pres ? pres + (e.Desempeno is { Length: > 0 } d2 ? " · " + d2 : string.Empty) + (e.Provisional ? " (provisional)" : string.Empty) : "—",
                derecha: true, medio: e.Presentada is not null, color: e.CumpleCriterio == false ? Ds.Peligro : null),
        ], cebra: n % 2 == 1)).ToList();
        ContenidoHost.Add(b.Evaluaciones.Count == 0 ? ReportesUi.Estado("Sin evaluaciones", EstadosVaciosDeReportes.SinEvaluaciones) : evaluaciones.EnTarjeta(filasEv));
    }

    // ------------------------------------------------------------------------------------------------------------------ 2 · competencias

    private void PintarCompetencias(ModeloDeBoletin b)
    {
        var c = b.Competencias;
        ContenidoHost.Add(ReportesUi.Seccion("2 · ¿Qué competencias alcanzó?", "Evidencias y logros que el profesor anotó, y los aprendizajes pendientes."));
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Lista("Logros", c.Logros.Select(x => Cita(x)).ToList(), "Todavía no hay logros anotados. Se escriben como «fortalezas» en la retroalimentación de cada calificación."));
        pila.Add(Lista("Aprendizajes pendientes", c.Pendientes.Select(x => Cita(x)).Concat(c.EvaluacionesNoAprobadas.Select(t => $"No cumple el criterio en «{t}»")).ToList(), "Nada pendiente anotado."));
        if (c.EvaluacionesAprobadas.Count > 0) pila.Add(Ds.Secundario($"Cumple el criterio de aprobación en: {string.Join(", ", c.EvaluacionesAprobadas)}.", 14));
        pila.Add(Ds.Secundario(c.Objetivos.Texto, 13));
        ContenidoHost.Add(ReportesUi.Tarjeta(pila));
    }

    private static string Cita(ComentarioDelProfesor x) => string.IsNullOrWhiteSpace(x.Titulo) ? x.Texto : $"{x.Texto} ({x.Titulo})";

    private static View Lista(string titulo, IReadOnlyList<string> lineas, string vacio)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(EstudioUi.Eyebrow(titulo.ToUpperInvariant()));
        if (lineas.Count == 0) pila.Add(Ds.Secundario(vacio, 14));
        foreach (var l in lineas) pila.Add(new Label { Text = "•  " + l, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        return pila;
    }

    // ------------------------------------------------------------------------------------------------------------------ 3 · progreso

    private void PintarProgreso(ModeloDeBoletin b)
    {
        ContenidoHost.Add(ReportesUi.Seccion("3 · ¿Cómo ha progresado?", "El promedio simple por curso en cada periodo en que estuvo (informativo, sin ponderar, no oficial)."));
        var pr = b.Progreso;
        if (pr.Tendencia is { } t && !b.SinCifras) ContenidoHost.Add(ExamenUi.Aviso(BoletinTexto.SimboloDeTendencia(t.Direccion) + "  Tendencia", BoletinTexto.Tendencia(t), t.Direccion == "baja" ? Tono.Ambar : Tono.Info));
        if (pr.Filas.Count == 0 || b.SinCifras) { ContenidoHost.Add(ReportesUi.Estado("Sin progreso que mostrar", b.SinCifras ? "En este nivel no hay notas: se ve lo completado en cada evaluación." : "Cuando haya calificaciones registradas, aparecerá el promedio de cada periodo.")); return; }
        var tabla = new TablaDeReporte(new ColumnaDeTabla("Periodo", new GridLength(140)), new ColumnaDeTabla("Grupo", new GridLength(140)), new ColumnaDeTabla("Curso", GridLength.Star),
            new ColumnaDeTabla("Calificaciones", new GridLength(140), Derecha: true), new ColumnaDeTabla("Promedio (0–100)", new GridLength(170), Derecha: true), new ColumnaDeTabla("Promedio presentado", new GridLength(190), Derecha: true));
        ContenidoHost.Add(tabla.EnTarjeta(pr.Filas.Select((f, i) => tabla.Fila([
            ReportesUi.Celda(f.Periodo + (f.Actual ? " (actual)" : string.Empty), medio: f.Actual), f.GrupoCodigo, ReportesUi.Celda(f.CursoRotulo), f.Calificaciones.ToString(),
            GradebookTexto.Puntaje(f.PromedioSimple), ReportesUi.Celda(BoletinTexto.Promedio(f.Presentado) + (f.Presentado?.Desempeno is { Length: > 0 } d ? " · " + d : string.Empty), derecha: true, medio: f.Presentado is not null),
        ], cebra: i % 2 == 1)).ToList()));
    }

    // ------------------------------------------------------------------------------------------------------------------ 4 · qué debe mejorar

    private void PintarQueDebeMejorar(ModeloDeBoletin b)
    {
        var rec = b.Recomendaciones;
        ContenidoHost.Add(ReportesUi.Seccion("4 · ¿Qué debe mejorar?", "Las recomendaciones del profesor (se escriben en el boletín del libro de calificaciones) y lo que se desprende de sus notas."));
        var pila = new VerticalStackLayout { Spacing = 12 };
        if (rec.DelDocente.Count == 0) pila.Add(Ds.Secundario("El profesor todavía no dejó recomendaciones para este periodo. Se eligen en Calificaciones → el boletín del estudiante → «Recomendaciones».", 14));
        foreach (var o in rec.DelDocente)
        {
            var lineas = o.Recomendaciones.ToList();
            if (!string.IsNullOrWhiteSpace(o.Texto)) lineas.Add(o.Texto);
            pila.Add(Lista(string.IsNullOrWhiteSpace(o.CursoRotulo) ? "General" : o.CursoRotulo, lineas, "Sin recomendaciones."));
        }
        if (rec.Oportunidades.Count > 0) pila.Add(Lista("Oportunidades anotadas en las evaluaciones", rec.Oportunidades.Select(Cita).ToList(), string.Empty));
        if (rec.CursoAReforzar is { } peor) pila.Add(Ds.Secundario($"Conviene reforzar «{peor.CursoRotulo}»: es el curso de promedio más bajo ({BoletinTexto.Promedio(peor.Presentado)}).", 15));
        if (rec.MejorCurso is { } mejor) pila.Add(Ds.Secundario($"Le va mejor en «{mejor.CursoRotulo}» ({BoletinTexto.Promedio(mejor.Presentado)}).", 15));
        ContenidoHost.Add(ReportesUi.Tarjeta(pila));
    }
}
