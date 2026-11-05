using System.Globalization;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Reporte del grupo (FUN-139 y FUN-140): lo primero son los estudiantes que NECESITAN ATENCIÓN, cada uno con su motivo en una línea (sin ningún «promedio del grupo» como dato
/// principal); después todos los estudiantes con su asistencia, participación, aciertos, evaluaciones y estudio; las clases cerradas y las evaluaciones con sus conteos. Se puede
/// filtrar por materia con fichas. Las calificaciones salen en el MODO del nivel que ya resolvió el libro (MOD-011): aquí no se convierte nada. Con el umbral de privacidad aplicado
/// (BR-086) no hay estudiantes sueltos: sólo los totales. Tocar un estudiante o una clase abre su reporte.
/// </summary>
public sealed class ReporteGrupoPage : PaginaDeReporte
{
    private static readonly TablaDeReporte Estudiantes = new(
        new ColumnaDeTabla("Estudiante", GridLength.Star),
        new ColumnaDeTabla("Clases a las que fue", new GridLength(160), Derecha: true),
        new ColumnaDeTabla("Participación", new GridLength(190), Derecha: true),
        new ColumnaDeTabla("Aciertos", new GridLength(190), Derecha: true),
        new ColumnaDeTabla("Evaluaciones", new GridLength(150), Derecha: true),
        new ColumnaDeTabla("Estudio", new GridLength(120), Derecha: true));

    private static readonly TablaDeReporte Clases = new(
        new ColumnaDeTabla("Cuándo", new GridLength(170)),
        new ColumnaDeTabla("Clase", GridLength.Star),
        new ColumnaDeTabla("Estudiantes", new GridLength(120), Derecha: true),
        new ColumnaDeTabla("Participación", new GridLength(180), Derecha: true),
        new ColumnaDeTabla("Aciertos", new GridLength(180), Derecha: true),
        new ColumnaDeTabla("Datos", new GridLength(130)));

    private static readonly TablaDeReporte Evaluaciones = new(
        new ColumnaDeTabla("Evaluación", GridLength.Star),
        new ColumnaDeTabla("Presentaron", new GridLength(150), Derecha: true),
        new ColumnaDeTabla("Faltan", new GridLength(110), Derecha: true),
        new ColumnaDeTabla("Por revisar", new GridLength(130), Derecha: true),
        new ColumnaDeTabla("Publicadas", new GridLength(130), Derecha: true));

    private readonly SelectorDeNodoView _selector = new();
    private NodoAcademico? _nodo;
    private bool _nodoInicial;

    public ReporteGrupoPage() : base("REPORTES · UN GRUPO", "Reporte del grupo", "Quién necesita atención y cómo va cada estudiante.")
    {
        SelectorHost.Add(_selector);
        _selector.Cambio += async nodo =>
        {
            _nodo = nodo;
            await ReportesUi.Seguro(nameof(ReporteGrupoPage), "Filtrar", () => CargarAsync(forzar: true))();
        };
    }

    protected override async Task LeerAsync(bool forzar)
    {
        if (!_nodoInicial) { _nodo = NodoDeLaRuta; _nodoInicial = true; }
        if (Parametro("grupo") is not { } grupo)
        {
            ContenidoHost.Clear();
            ContenidoHost.Add(ReportesUi.Estado("Falta elegir el grupo", "Vuelve a Reportes y elige un grupo."));
            return;
        }
        var api = ReportesUi.Api;
        var filtros = await ReportesUi.FiltrosAsync();
        _selector.Mostrar(filtros?.Nodos, _nodo);
        await LeerYPintarAsync(api, () => api.GrupoAsync(ReportesUi.Actor, grupo, _nodo), r => Pintar(r), "No se pudo armar el reporte del grupo");
    }

    private void Pintar(ReporteDeGrupo r)
    {
        var g = r.Grupo;
        var nivel = r.EnModoCalificaciones ? $"Notas en escala {r.Escala?.Nombre ?? "del nivel"}" : "Sin notas: este nivel usa estados simples";
        var partes = new[] { string.IsNullOrWhiteSpace(g.Nombre) || g.Nombre == g.Codigo ? null : g.Nombre, string.IsNullOrWhiteSpace(g.Periodo) ? null : $"periodo {g.Periodo}",
                             FormatoDeReportes.Plural(r.Totales.Alumnos, "estudiante", "estudiantes"), nivel }.Where(x => !string.IsNullOrEmpty(x));
        Poner($"Grupo {g.Rotulo}", string.Join(" · ", partes));
        PonerCorte(r.Corte, r.Privacidad, r.Avisos);
        ExportarVisible(ReporteSolicitado.DeGrupo(g.Id, _nodo));

        EncabezadoFijo(null);
        ContenidoHost.Clear();
        var t = r.Totales;
        var totales = ExamenUi.Fila();
        totales.Add(ReportesUi.Total("Estudiantes", Num(t.Alumnos), null, 190));
        totales.Add(ReportesUi.Total("Clases cerradas", Num(t.Clases), null, 190));
        totales.Add(ReportesUi.Total("Evaluaciones", Num(t.Evaluaciones), null, 190));
        totales.Add(ReportesUi.Total("Tareas de estudio", Num(t.Estudios), null, 190));
        totales.Add(ReportesUi.Total("Necesitan atención", r.Privacidad.Aplicada ? "—" : Num(t.EnAtencion), t.EnAtencion > 0 && !r.Privacidad.Aplicada ? "se muestran primero" : null, 210));
        ContenidoHost.Add(totales);

        // ---- 1 · quién necesita atención (lo primero; el promedio del grupo NO es el dato principal)
        if (r.Privacidad.Aplicada)
        {
            ContenidoHost.Add(ReportesUi.Estado("Sólo se muestran los totales", "Los estudiantes no se listan uno por uno, para cuidar su privacidad. Lo mismo vale para el archivo que se exporte."));
        }
        else
        {
            ContenidoHost.Add(ReportesUi.Seccion("Necesitan atención", "Cada uno con lo que se notó. Tócalo para ver su reporte."));
            if (r.Atencion.Count == 0)
                ContenidoHost.Add(ExamenUi.Aviso(r.Alumnos.Count == 0 ? EstadosVaciosDeReportes.SinAlumnos : "Nadie necesita atención en este momento.", null, r.Alumnos.Count == 0 ? Tono.Info : Tono.Exito));
            else
                foreach (var a in r.Atencion) ContenidoHost.Add(FilaDeAtencion(g, a));

            // ---- 2 · todos los estudiantes
            if (r.Alumnos.Count > 0)
            {
                ContenidoHost.Add(ReportesUi.Seccion("Estudiantes", "Tocar un estudiante abre su reporte."));
                var filas = r.Alumnos.Select((a, i) => FilaDeEstudiante(g, a, i)).ToList();
                ContenidoHost.Add(Estudiantes.EnTarjeta(filas));
            }
        }

        // ---- 3 · clases cerradas
        ContenidoHost.Add(ReportesUi.Seccion("Clases cerradas", "Tocar una clase abre su reporte."));
        if (r.Clases.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin clases todavía", EstadosVaciosDeReportes.SinClasesDelGrupo));
        else ContenidoHost.Add(Clases.EnTarjeta(r.Clases.Select((c, i) => FilaDeClase(c, i)).ToList()));

        // ---- 4 · evaluaciones (conteos, sin promedios)
        ContenidoHost.Add(ReportesUi.Seccion("Evaluaciones", r.EnModoCalificaciones ? "Las notas están en el libro de calificaciones." : "En este nivel no hay notas: se cuenta quién presentó."));
        if (r.Evaluaciones.Count == 0) ContenidoHost.Add(ReportesUi.Estado("Sin evaluaciones", EstadosVaciosDeReportes.SinEvaluaciones));
        else ContenidoHost.Add(Evaluaciones.EnTarjeta(r.Evaluaciones.Select((e, i) => Evaluaciones.Fila([
            ReportesUi.Celda(e.Titulo, medio: true), FormatoDeReportes.DeTotal(e.Presentaron, e.Alumnos), Num(e.Pendientes), Num(e.PorRevisar), Num(e.Publicadas)], cebra: i % 2 == 1)).ToList()));

        ContenidoHost.Add(ReportesUi.ObjetivosNoDisponibles(r.Objetivos));
    }

    private static string Num(int n) => n.ToString(CultureInfo.InvariantCulture);

    private View FilaDeAtencion(GrupoResumido grupo, AlumnoEnGrupo a)
    {
        var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = a.Alumno, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta });
        texto.Add(Ds.Secundario(a.Motivo, 14));
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14, MinimumHeightRequest = 44 };
        fila.Add(texto, 0, 0);
        fila.Add(ExamenUi.Pildora("Atención", Tono.Ambar, 13), 1, 0);
        return ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(ReporteGrupoPage), "AbrirAlumno", () => Shell.Current.GoToAsync(RutasDeReportes.DeAlumno(a.AlumnoId, grupo.Id, _nodo))),
            $"{a.Alumno}. {a.Motivo}", $"reporte-grupo-atencion-{a.AlumnoId}", Color.FromArgb("#F6F7F9"), new Thickness(20, 12));
    }

    private View FilaDeEstudiante(GrupoResumido grupo, AlumnoEnGrupo a, int indice)
    {
        var nombre = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        nombre.Add(ReportesUi.Celda(a.Alumno, medio: true));
        if (a.NecesitaAtencion) nombre.Add(new Label { Text = "Necesita atención", FontFamily = Ds.FuenteMedia, FontSize = 12, TextColor = ExamenUi.TintaAmbar });
        return Estudiantes.Fila([
            nombre,
            a.ClasesTotal == 0 ? "—" : FormatoDeReportes.DeTotal(a.ClasesAsistidas, a.ClasesTotal),
            ReportesUi.CeldaDePorcentaje(a.PorcentajeParticipacion, Ds.Info),
            ReportesUi.CeldaDePorcentaje(a.PorcentajeAciertos, Ds.Exito),
            a.EvaluacionesTotal == 0 ? "—" : FormatoDeReportes.DeTotal(a.EvaluacionesPresentadas, a.EvaluacionesTotal),
            a.EstudiosTotal == 0 ? "—" : FormatoDeReportes.DeTotal(a.EstudiosCompletados, a.EstudiosTotal),
        ], cebra: indice % 2 == 1, alTocar: ReportesUi.Seguro(nameof(ReporteGrupoPage), "AbrirEstudiante", () => Shell.Current.GoToAsync(RutasDeReportes.DeAlumno(a.AlumnoId, grupo.Id, _nodo))),
           id: $"reporte-grupo-alumno-{a.AlumnoId}", descripcion: $"Ver el reporte de {a.Alumno}");
    }

    private View FilaDeClase(ClaseDeGrupo c, int indice)
    {
        var datos = c.Incompleta ? ExamenUi.Pildora("Incompleto", Tono.Ambar, 13) : (View)ExamenUi.Pildora("Completo", Tono.Exito, 13);
        return Clases.Fila([
            ReportesUi.Celda(FormatoDeReportes.FechaCorta(c.FinalizadaEn)),
            ReportesUi.Celda($"{c.CursoRotulo} · {c.LeccionRotulo}"),
            Num(c.Participantes),
            ReportesUi.CeldaDePorcentaje(c.PromedioParticipacion, Ds.Info),
            ReportesUi.CeldaDePorcentaje(c.PromedioAciertos, Ds.Exito),
            datos,
        ], cebra: indice % 2 == 1, alTocar: ReportesUi.Seguro(nameof(ReporteGrupoPage), "AbrirClase", () => Shell.Current.GoToAsync(RutasDeReportes.DeClase(c.SesionId))),
           id: $"reporte-grupo-clase-{c.SesionId}", descripcion: $"Ver el reporte de la clase del {FormatoDeReportes.FechaCorta(c.FinalizadaEn)}");
    }
}
