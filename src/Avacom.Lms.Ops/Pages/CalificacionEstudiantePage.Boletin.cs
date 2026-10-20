using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

// Lo que se pinta del boletín. Neumorfismo (BoletinUi): superficies en relieve para lo que se lee, pozos hundidos para las cifras y la tabla de notas, y notas «selladas» como en un boletín de colegio.
// Verde si la nota cumple el criterio de aprobación del sistema, rojo si no, gris si no hay nota: nunca un cero inventado.
public partial class CalificacionEstudiantePage
{
    private const double AnchoPanel = 334, AnchoCifra = 246;

    // ----------------------------------------------------------------------------------------- cabecera

    private static View Encabezado(BoletinDelEstudiante b)
    {
        var calif = b.EnModoCalificaciones;
        var pila = new VerticalStackLayout { Spacing = 16 };
        pila.Add(new Border { HeightRequest = 8, StrokeThickness = 0, Padding = 0, BackgroundColor = Colors.Transparent, StrokeShape = new RoundRectangle { CornerRadius = 4 }, Content = BoletinUi.BandaDeColores(8) });
        pila.Add(BoletinUi.Rotulo($"Informe de calificaciones · periodo {b.Grupo.Periodo}"));

        var datos = new VerticalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        datos.Add(new Label { Text = b.Alumno.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 40, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2, AutomationId = "boletin-nombre" });
        datos.Add(Ds.Secundario($"Grupo {b.Grupo.Codigo} · {b.Grupo.Nombre} · {SelectorDeGrupo.RotuloDeNivel(b.Grupo.NivelClave)}", 17));
        var sistema = ExamenUi.Fila();
        if (calif)
        {
            sistema.Add(ExamenUi.PildoraEnFila($"Sistema: {GradebookTexto.Sistema(b.Sistema)}", Tono.Info, 13));
            var resumen = GradebookTexto.ResumenDelSistema(b.Sistema);
            if (resumen.Length > 0) sistema.Add(ExamenUi.PildoraEnFila(resumen, Tono.Neutro, 13));
        }
        else sistema.Add(ExamenUi.PildoraEnFila("Modo simple · sin notas: sólo si completó cada evaluación", Tono.Neutro, 13));
        datos.Add(sistema);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 28 };
        fila.Add(BoletinUi.Avatar(b.Alumno.Rotulo, 108), 0, 0);
        fila.Add(datos, 1, 0);
        if (calif)
        {
            var promedio = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.Center };
            promedio.Add(BoletinUi.Rotulo("Promedio", 12));
            promedio.Add(BoletinUi.Sello(BoletinTexto.Promedio(b.Resumen.Presentado), b.Resumen.Presentado is null ? "sin nota aún" : BoletinTexto.LecturaDelPromedio(b.Resumen.Presentado), b.Resumen.Presentado?.CumpleCriterio, 170, 48));
            promedio.Add(new Label { Text = b.Resumen.PromedioSimple is { } p ? $"simple: {BoletinTexto.PromedioInterno(p)} de 100" : "informativo", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, HorizontalTextAlignment = TextAlignment.Center });
            // Los puntos brutos sumados: lo obtenido sobre lo posible. La nota se lee con los tres: puntos, porcentaje y sistema.
            if (BoletinTexto.Bruto(b.Resumen.Bruto) is { Length: > 0 } bruto)
                promedio.Add(new Label { Text = bruto, FontFamily = Ds.FuenteMedia, FontSize = 13, TextColor = Ds.TintaMedia, HorizontalTextAlignment = TextAlignment.Center, AutomationId = "boletin-puntos" });
            fila.Add(promedio, 2, 0);
        }
        pila.Add(fila);
        pila.Add(Ds.Secundario("Vista informativa para el profesor: el promedio es simple y no está ponderado, y esto no es un boletín oficial.", 13));
        return BoletinUi.Relieve(pila, 32, new Thickness(32, 26, 32, 24));
    }

    // ------------------------------------------------------------------------------------------ materias

    /// <summary>Las materias del grupo como fichas, para ver sólo los cursos de una (un profesor dicta varios cursos de la misma materia). Sólo si hay algo que segmentar.</summary>
    private View? Materias(BoletinDelEstudiante b)
    {
        var materias = b.Materias ?? [];
        if (materias.Count <= 1 && _materia is null) return null;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(BoletinUi.Rotulo("Materia", 12));
        var fila = EstudioUi.Envolver();
        fila.Add(EstudioUi.Chip($"Todas ({materias.Sum(m => m.Evaluaciones)})", _materia is null, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "MateriaTodas", () => FiltrarMateriaAsync(null)), "boletin-materia-todas", 44));
        foreach (var m in materias)
        {
            var codigo = m.Codigo;
            fila.Add(EstudioUi.Chip($"{m.Rotulo} ({m.Evaluaciones})", _materia == codigo, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Materia", () => FiltrarMateriaAsync(codigo)),
                $"boletin-materia-{(codigo.Length == 0 ? "sin" : codigo)}", 44));
        }
        pila.Add(fila);
        if (_materia is not null) pila.Add(Ds.Secundario("El resumen, los insights y las notas de abajo son sólo de esta materia.", 13));
        return BoletinUi.Relieve(pila, 24, new Thickness(24, 16));
    }

    // ------------------------------------------------------------------------------------ recomendaciones

    /// <summary>
    /// «¿Qué debe mejorar?»: las recomendaciones del profesor para este periodo, elegidas de un catálogo cerrado (el nodo principal no tiene teclado). Se tocan las que aplican y se guardan;
    /// cada cambio queda en la bitácora con quién y cuándo. Lo guardado por curso se muestra, no se edita aquí.
    /// </summary>
    private View Recomendaciones(BoletinDelEstudiante b)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(Ds.Titulo("Recomendaciones del profesor", 24));
        pila.Add(Ds.Secundario("Lo que le recomiendas a este estudiante en el periodo. Va a su boletín académico (la cuarta pregunta: ¿qué debe mejorar?). Toca las que apliquen y guarda.", 14));
        var catalogo = b.RecomendacionesDisponibles ?? [];
        var general = b.Observaciones?.FirstOrDefault(o => o.EsGeneral);
        if (CalificacionesUi.PuedeCalificar && catalogo.Count > 0)
        {
            var fichas = EstudioUi.Envolver();
            foreach (var r in catalogo)
            {
                var codigo = r.Codigo;
                var elegida = _recomendaciones.Contains(codigo);
                fichas.Add(EstudioUi.Chip(elegida ? $"✓  {r.Texto}" : r.Texto, elegida, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Recomendacion", () => AlternarRecomendacionAsync(codigo)), $"boletin-recomendacion-{codigo}", 48));
            }
            pila.Add(fichas);
            var guardadas = general?.Recomendaciones.Select(r => r.Codigo).ToHashSet() ?? [];
            var cambiado = _recomendacionesTocadas && !guardadas.SetEquals(_recomendaciones);
            var acciones = ExamenUi.Fila();
            var guardar = ExamenUi.Accion(_guardandoRecomendaciones ? "Guardando…" : "Guardar recomendaciones", cambiado ? Ds.Rango.Primary : Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "GuardarRecomendaciones", GuardarRecomendacionesAsync), 290, "boletin-recomendaciones-guardar", 52, margen: false);
            Ds.Habilitar(guardar.Boton, cambiado && !_guardandoRecomendaciones);
            acciones.Add(guardar.Vista);
            pila.Add(acciones);
            if (general is not null)
                pila.Add(Ds.Secundario($"Guardadas por {ExamenTexto.Persona(general.ActualizadaPor)} el {GradebookTexto.Hora(general.ActualizadaEn)} (versión {general.Version}). Cada cambio queda en la bitácora.", 13));
            else if (!cambiado) pila.Add(Ds.Secundario("Todavía no hay recomendaciones guardadas para este periodo.", 13));
        }
        else if (general is not null) pila.Add(new Label { Text = BoletinTexto.Recomendaciones(general), FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        foreach (var o in (b.Observaciones ?? []).Where(o => !o.EsGeneral))
        {
            var rotulo = b.Cursos.FirstOrDefault(c => c.CursoRef == o.CursoRef)?.CursoRotulo ?? o.CursoRef;
            pila.Add(Ds.Secundario($"{rotulo}: {BoletinTexto.Recomendaciones(o)}", 14));
        }
        return BoletinUi.Relieve(pila, 28, new Thickness(28, 22, 28, 18));
    }

    // ----------------------------------------------------------------------------------------- resumen

    private static View Resumen(BoletinDelEstudiante b)
    {
        var calif = b.EnModoCalificaciones;
        var c = b.Resumen.Conteo;
        var tarjetas = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start };
        if (calif)
        {
            tarjetas.Add(Panel(BoletinUi.Cifra($"{c.ConNota} de {b.Resumen.Evaluaciones}", "evaluaciones con nota"), AnchoCifra));
            if (c.ConNota > 0)
                tarjetas.Add(Panel(BoletinUi.Cifra($"{c.Aprobadas} de {c.ConNota}", c.NoAprobadas > 0 ? $"cumplen el criterio · {c.NoAprobadas} no" : "cumplen el criterio", c.NoAprobadas > 0 ? Ds.Tinta : ExamenUi.TintaExito), AnchoCifra));
        }
        tarjetas.Add(Panel(Avance(c.Completadas, b.Resumen.Evaluaciones), AnchoCifra));
        // Lo que le toca al PROFESOR con este estudiante (revisar, registrar, publicar): no es lo mismo que lo que el estudiante dejó sin hacer, que va en su tarjeta de arriba.
        var atender = BoletinTexto.PorAtender(c);
        tarjetas.Add(Panel(BoletinUi.Cifra(atender.Length == 0 ? "Nada" : atender, atender.Length == 0 ? "por revisar, registrar ni publicar" : "lo que te toca hacer con él", atender.Length == 0 ? ExamenUi.TintaExito : ExamenUi.TintaVioleta), AnchoCifra));

        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(Ds.Titulo("Resumen", 24));
        pila.Add(tarjetas);
        return BoletinUi.Relieve(pila, 28, new Thickness(28, 22, 28, 12));
    }

    private static View Avance(int completadas, int total)
    {
        var pila = new VerticalStackLayout { Spacing = 4 };
        pila.Add(new Label { Text = $"{completadas} de {total}", FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = Ds.Tinta });
        var sinHacer = total - completadas;
        pila.Add(new Label { Text = sinHacer > 0 ? $"completadas · {sinHacer} sin hacer" : "evaluaciones completadas", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = sinHacer > 0 ? ExamenUi.TintaAmbar : Ds.TintaSuave });
        pila.Add(BoletinUi.Medidor(total == 0 ? 0 : (double)completadas / total, completadas >= total && total > 0 ? Ds.Exito : Ds.Info, 9));
        return BoletinUi.Hundido(pila, 16, new Thickness(16, 10));
    }

    private static View Panel(View vista, double ancho = AnchoPanel)
    {
        vista.WidthRequest = ancho;
        vista.Margin = new Thickness(0, 0, 16, 16);
        return vista;
    }

    // ----------------------------------------------------------------------------------------- insights

    private static View Insights(BoletinDelEstudiante b)
    {
        var ins = b.Insights;
        var calif = b.EnModoCalificaciones;
        var panales = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start };

        if (calif)
        {
            // ---- hacia dónde va
            var (simbolo, color) = ins.Tendencia.Direccion switch
            {
                "sube" => ("▲", Ds.Exito), "baja" => ("▼", Ds.Peligro), "estable" => ("▬", Ds.Info), _ => ("·", Ds.TintaSuave),
            };
            var tendencia = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14 };
            tendencia.Add(new Border
            {
                WidthRequest = 54, HeightRequest = 54, BackgroundColor = color.WithAlpha(0.14f), StrokeThickness = 1.5, Stroke = new SolidColorBrush(color.WithAlpha(0.4f)), StrokeShape = new RoundRectangle { CornerRadius = 27 },
                VerticalOptions = LayoutOptions.Start, Content = new Label { Text = simbolo, FontSize = 22, TextColor = color, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            }, 0, 0);
            tendencia.Add(new Label { Text = BoletinTexto.Tendencia(ins.Tendencia), FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, VerticalOptions = LayoutOptions.Center, AutomationId = "boletin-tendencia" }, 1, 0);
            panales.Add(PanelDeInsight("Hacia dónde va", tendencia));

            // ---- por curso
            var cursos = new VerticalStackLayout { Spacing = 8 };
            if (ins.MejorCurso is { } mejor && ins.CursoAReforzar is { } peor)
            {
                cursos.Add(LineaDeCurso("▲", "Le va mejor en", mejor, Ds.Exito));
                cursos.Add(LineaDeCurso("▼", "Conviene reforzar", peor, Ds.Peligro));
            }
            else cursos.Add(Ds.Secundario("Se compara cuando hay promedio en al menos dos cursos distintos.", 14));
            panales.Add(PanelDeInsight("Por curso", cursos));
        }

        // ---- constancia
        var constancia = new VerticalStackLayout { Spacing = 10 };
        constancia.Add(new Label { Text = BoletinTexto.Constancia(ins.Constancia), FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        constancia.Add(BoletinUi.Medidor(ins.Constancia.Evaluaciones == 0 ? 0 : (double)ins.Constancia.Completadas / ins.Constancia.Evaluaciones, Ds.Info, 10));
        panales.Add(PanelDeInsight("Constancia", constancia));

        var pila = new VerticalStackLayout { Spacing = 14 };
        pila.Add(Ds.Titulo("Insights", 24));
        pila.Add(Ds.Secundario(calif ? "Cuentas sencillas sobre lo ya registrado: informativas, no un juicio. Con pocos datos no se inventa nada." : "En modo simple no hay notas: los insights de desempeño aparecen cuando el nivel califica con un sistema.", 14));
        pila.Add(panales);

        if (calif)
        {
            pila.Add(BoletinUi.Rotulo("Lo que escribió el profesor", 12));
            if (!ins.Comentarios.HayAlgo)
                pila.Add(Ds.Secundario("Todavía no hay comentarios sobre este estudiante. Se escriben en el detalle de cada calificación (fortalezas, dificultades y oportunidades).", 14));
            else
            {
                var comentarios = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start };
                if (ins.Comentarios.Fortalezas.Count > 0) comentarios.Add(PanelDeComentarios("Fortalezas", "✓", ins.Comentarios.Fortalezas, Ds.Exito, Ds.ExitoSuave));
                if (ins.Comentarios.Dificultades.Count > 0) comentarios.Add(PanelDeComentarios("Dificultades", "!", ins.Comentarios.Dificultades, ExamenUi.TintaAmbar, Ds.AlertaSuave));
                if (ins.Comentarios.Oportunidades.Count > 0) comentarios.Add(PanelDeComentarios("Oportunidades", "→", ins.Comentarios.Oportunidades, ExamenUi.TintaInfo, Ds.InfoSuave));
                pila.Add(comentarios);
            }
        }
        return BoletinUi.Relieve(pila, 28, new Thickness(28, 22, 28, 12));
    }

    private static View PanelDeInsight(string rotulo, View contenido)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(BoletinUi.Rotulo(rotulo, 11));
        pila.Add(contenido);
        var pozo = BoletinUi.Hundido(pila, 18, new Thickness(18, 14));
        return Panel(pozo);
    }

    private static View LineaDeCurso(string simbolo, string rotulo, CursoDestacado curso, Color color)
    {
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
        fila.Add(new Label { Text = simbolo, FontSize = 14, TextColor = color, VerticalOptions = LayoutOptions.Center }, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 0 };
        textos.Add(new Label { Text = rotulo, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave });
        textos.Add(new Label { Text = curso.CursoRotulo, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        fila.Add(textos, 1, 0);
        fila.Add(new Label { Text = BoletinTexto.Promedio(curso.Presentado), FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = color, VerticalOptions = LayoutOptions.Center }, 2, 0);
        return fila;
    }

    private static View PanelDeComentarios(string titulo, string simbolo, IReadOnlyList<ComentarioDelProfesor> comentarios, Color tinta, Color fondo)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        var cabecera = ExamenUi.Fila();
        cabecera.Add(Ds.Pildora($"{simbolo}  {titulo}", fondo, tinta, 13));
        pila.Add(cabecera);
        foreach (var c in comentarios)
        {
            var cita = new VerticalStackLayout { Spacing = 2 };
            cita.Add(new Label { Text = $"“{c.Texto}”", FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            var origen = string.Join(" · ", new[] { c.Titulo, c.Fecha is { } f ? BoletinTexto.Fecha(f) : null }.Where(x => !string.IsNullOrWhiteSpace(x)));
            if (origen.Length > 0) cita.Add(new Label { Text = origen, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 });
            pila.Add(cita);
        }
        return Panel(BoletinUi.Hundido(pila, 18, new Thickness(18, 14)));
    }

    // ----------------------------------------------------------------------------------------- cursos y evaluaciones

    private IEnumerable<View> Cursos(BoletinDelEstudiante b)
    {
        var calif = b.EnModoCalificaciones;
        if (b.Cursos.Count == 0)
        {
            yield return BoletinUi.Relieve(Ds.Secundario("Todavía no hay evaluaciones aplicadas en este grupo. Cuando las haya, sus notas aparecerán aquí por curso.", 15), 28, new Thickness(28, 22));
            yield break;
        }

        yield return Ds.Titulo(b.Cursos.Count == 1 ? "Notas del curso" : $"Notas por curso ({b.Cursos.Count})", 26);

        // Con más de un curso, lo más reciente de todos juntos: lo primero que se quiere ver. Con uno solo ya está en su tabla.
        if (b.Cursos.Count > 1 && b.Evaluaciones.Items.Count > 0)
        {
            var recientes = new VerticalStackLayout { Spacing = 10 };
            recientes.Add(Ds.Titulo("Lo más reciente", 22));
            recientes.Add(TablaDeEvaluaciones(b.Evaluaciones.Items, b.Evaluaciones.Total, calif, conCurso: true));
            yield return BoletinUi.Relieve(recientes, 28, new Thickness(24, 20, 24, 18));
        }

        foreach (var curso in b.Cursos.OrderByDescending(c => c.Conteo.PorAtender).ThenBy(c => c.CursoRotulo, StringComparer.CurrentCultureIgnoreCase).Take(_cursosVisibles))
            yield return TarjetaDeCurso(b, curso, calif);

        if (b.Cursos.Count > _cursosVisibles)
            yield return ExamenUi.Accion($"Mostrar más cursos ({b.Cursos.Count - _cursosVisibles})", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "MasCursos", MasCursosAsync), 320, "boletin-mas-cursos", 52, margen: false).Vista;
    }

    private View TarjetaDeCurso(BoletinDelEstudiante b, CursoDelBoletin curso, bool calif)
    {
        var abierto = _abiertos.Contains(curso.CursoRef);
        var c = curso.Conteo;
        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = curso.CursoRotulo.Length > 0 ? curso.CursoRotulo : "Sin curso", FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila($"{curso.Evaluaciones} {(curso.Evaluaciones == 1 ? "evaluación" : "evaluaciones")}", Tono.Neutro, 12));
        if (calif) pastillas.Add(ExamenUi.PildoraEnFila($"{c.ConNota} con nota", c.ConNota > 0 ? Tono.Info : Tono.Neutro, 12));
        if (calif && BoletinTexto.Bruto(curso.Bruto) is { Length: > 0 } bruto) pastillas.Add(ExamenUi.PildoraEnFila(bruto, Tono.Neutro, 12));
        pastillas.Add(ExamenUi.PildoraEnFila($"{c.Completadas} completadas", c.Completadas >= curso.Evaluaciones && curso.Evaluaciones > 0 ? Tono.Exito : Tono.Neutro, 12));
        if (c.PorRevisar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.PorRevisar} por revisar", Tono.Violeta, 12));
        if (c.SinRegistro > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.SinRegistro} sin registrar", Tono.Ambar, 12));
        if (c.SinPublicar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.SinPublicar} sin publicar", Tono.Info, 12));
        if (c.NoAprobadas > 0) pastillas.Add(Pildora(Ds.PeligroSuave, Ds.Peligro, $"{c.NoAprobadas} no cumplen"));
        textos.Add(pastillas);

        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 18 };
        cabecera.Add(textos, 0, 0);
        if (calif)
            cabecera.Add(BoletinUi.Sello(BoletinTexto.Promedio(curso.Presentado), curso.Presentado is null ? "sin nota aún" : BoletinTexto.LecturaDelPromedio(curso.Presentado), curso.Presentado?.CumpleCriterio, 150, 34), 1, 0);
        var alternar = ExamenUi.Accion(abierto ? "Ocultar evaluaciones" : "Ver evaluaciones", abierto ? Ds.Rango.Secondary : Ds.Rango.Primary,
            CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Curso", () => AlternarCursoAsync(curso.CursoRef)), 230, $"boletin-curso-{curso.CursoRef}", 52, margen: false);
        alternar.Vista.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(alternar.Vista, 2, 0);

        var pila = new VerticalStackLayout { Spacing = 16 };
        pila.Add(cabecera);
        if (abierto)
        {
            if (!_paginas.TryGetValue(curso.CursoRef, out var pagina) || (pagina.Items.Count == 0 && pagina.Cargando))
                pila.Add(Ds.Secundario("Leyendo las evaluaciones…", 15));
            else
            {
                pila.Add(TablaDeEvaluaciones(pagina.Items, pagina.Total, calif, conCurso: false));
                if (pagina.Items.Count < pagina.Total)
                {
                    var mas = ExamenUi.Accion(pagina.Cargando ? "Un momento…" : $"Mostrar más ({pagina.Total - pagina.Items.Count} evaluaciones)", Ds.Rango.Secondary,
                        CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "MasEvaluaciones", () => CargarPaginaAsync(curso.CursoRef, pagina.Items.Count)), 320, $"boletin-mas-{curso.CursoRef}", 52, margen: false);
                    Ds.Habilitar(mas.Boton, !pagina.Cargando);
                    mas.Vista.HorizontalOptions = LayoutOptions.Start;
                    pila.Add(mas.Vista);
                }
            }
        }
        return BoletinUi.Relieve(pila, 28, new Thickness(28, 22, 28, 22));
    }

    /// <summary>La tabla de notas, como una libreta: una fila por evaluación, de la más reciente a la más antigua, con su fecha, su tipo, la nota sellada, el desempeño y el estado.</summary>
    private View TablaDeEvaluaciones(IReadOnlyList<EvaluacionDelBoletin> items, int total, bool calif, bool conCurso)
    {
        var pila = new VerticalStackLayout { Spacing = 0 };
        pila.Add(EncabezadoDeTabla(calif));
        pila.Add(BoletinUi.Linea());
        for (var i = 0; i < items.Count; i++)
        {
            pila.Add(FilaDeEvaluacion(items[i], calif, conCurso));
            if (i < items.Count - 1) pila.Add(BoletinUi.Linea());
        }
        if (items.Count == 0) pila.Add(new Label { Text = "Sin evaluaciones en este curso.", FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave, Margin = new Thickness(0, 12) });
        return BoletinUi.Hundido(pila, 20, new Thickness(18, 8, 18, 8));
    }

    private static readonly double[] Columnas = [104, 0, 138, 100, 190, 150, 22];

    // Con la edición activa, la última columna deja sitio al botón «Editar».
    private Grid FilaDeTabla() => new()
    {
        ColumnDefinitions =
        [
            new ColumnDefinition(new GridLength(Columnas[0])), new ColumnDefinition(GridLength.Star), new ColumnDefinition(new GridLength(Columnas[2])), new ColumnDefinition(new GridLength(Columnas[3])),
            new ColumnDefinition(new GridLength(Columnas[4])), new ColumnDefinition(new GridLength(Columnas[5])), new ColumnDefinition(new GridLength(_edicion ? 120 : Columnas[6])),
        ],
        ColumnSpacing = 12, Padding = new Thickness(0, 10),
    };

    private View EncabezadoDeTabla(bool calif)
    {
        var fila = FilaDeTabla();
        fila.Padding = new Thickness(0, 6);
        string[] titulos = ["Fecha", "Evaluación", "Tipo", calif ? "Nota" : "Estado", calif ? "Desempeño" : string.Empty, calif ? "Estado" : string.Empty, string.Empty];
        for (var i = 0; i < titulos.Length; i++) if (titulos[i].Length > 0) fila.Add(BoletinUi.Rotulo(titulos[i], 10), i, 0);
        return fila;
    }

    private View FilaDeEvaluacion(EvaluacionDelBoletin e, bool calif, bool conCurso)
    {
        var fila = FilaDeTabla();
        fila.Add(new Label { Text = BoletinTexto.Fecha(e.Fecha), FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center }, 0, 0);

        var titulo = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        titulo.Add(new Label { Text = e.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        var notas = new List<string>();
        if (conCurso && !string.IsNullOrWhiteSpace(e.CursoRotulo)) notas.Add(e.CursoRotulo!);
        // La nota en bruto (puntos sobre el máximo y porcentaje) junto a la presentada; sin puntos, el resultado interno.
        if (calif && GradebookTexto.Bruto(e.Bruto) is { Length: > 0 } bruto) notas.Add(bruto);
        else if (calif && BoletinTexto.Interno(e) is { Length: > 0 } interno) notas.Add(interno);
        if (e.Presentacion?.Provisional == true && !e.Publicada) notas.Add("provisional");
        if (e.Ajustada) notas.Add("ajustada");
        if (notas.Count > 0) titulo.Add(new Label { Text = string.Join(" · ", notas), FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 });
        fila.Add(titulo, 1, 0);

        fila.Add(Centrado(ExamenUi.Pildora(GradebookTexto.TipoDeEvaluacion(e.TipoEvaluacion), Tono.Neutro, 12)), 2, 0);

        if (calif)
        {
            fila.Add(Centrado(BoletinUi.Sello(BoletinTexto.Nota(e), null, BoletinTexto.Cumple(e), 84, 22)), 3, 0);
            fila.Add(new Label { Text = TextoDeCalificaciones.Desempeno(e.Presentacion), FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.WordWrap, MaxLines = 2 }, 4, 0);
            fila.Add(Centrado(CalificacionesUi.PildoraEnFila(BoletinTexto.Estado(e), VistaDelLibro.MatizDeEstado(e.Estado), 12)), 5, 0);
        }
        else
        {
            var simbolo = VistaDelLibro.SimboloDeEstadoSimple(e.EstadoSimple);
            var estado = new HorizontalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
            estado.Add(new Label { Text = simbolo, FontSize = 20, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center });
            estado.Add(new Label { Text = GradebookTexto.EstadoSimple(e.EstadoSimple), FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center });
            fila.Add(estado, 3, 0);
            Grid.SetColumnSpan(estado, 3);
        }

        if (e.CalificacionId is { } id && _edicion && calif && CalificacionesUi.PuedeCalificar)
        {
            // Con la edición activa, cada nota se edita aquí mismo: la hoja de ajuste con motivo (queda en el historial y en la bitácora).
            var editar = ExamenUi.Accion("✎  Editar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Editar", () => EditarAsync(id, e.Titulo)), 110, $"boletin-editar-{e.AsignacionId}", 40, margen: false);
            editar.Boton.FontSize = 13;
            editar.Vista.VerticalOptions = LayoutOptions.Center;
            fila.Add(editar.Vista, 6, 0);
            fila.AutomationId = $"boletin-evaluacion-{e.AsignacionId}";
        }
        else if (e.CalificacionId is { } detalle)
        {
            fila.Add(new Label { Text = "›", FontSize = 22, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End }, 6, 0);
            fila.AutomationId = $"boletin-evaluacion-{e.AsignacionId}";
            SemanticProperties.SetDescription(fila, $"{e.Titulo}. Toca para ver el detalle de la calificación.");
            Ds.Tocable(fila, () => Shell.Current.GoToAsync($"calificacion-detalle?id={Uri.EscapeDataString(detalle)}&alumno={Uri.EscapeDataString(_boletin?.Alumno.Rotulo ?? Nombre)}&titulo={Uri.EscapeDataString(e.Titulo)}"));
        }
        return fila;
    }

    private static View Centrado(View vista)
    {
        vista.VerticalOptions = LayoutOptions.Center;
        return vista;
    }

    private static Border Pildora(Color fondo, Color tinta, string texto)
    {
        var p = Ds.Pildora(texto, fondo, tinta, 12);
        p.Margin = new Thickness(0, 0, 8, 8);
        p.HorizontalOptions = LayoutOptions.Start;
        return p;
    }

    // ----------------------------------------------------------------------------------------- la clave del sistema

    private static View Pie(BoletinDelEstudiante b)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(BoletinUi.Rotulo("Cómo se lee este boletín", 12));
        if (b.EnModoCalificaciones && b.Sistema is { } sistema)
        {
            pila.Add(new Label { Text = GradebookTexto.Sistema(sistema), FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            var lectura = GradebookTexto.ResumenDelSistema(sistema);
            if (lectura.Length > 0) pila.Add(Ds.Secundario(lectura, 14));
            if (sistema.Tramos is { Count: > 0 } tramos)
            {
                var niveles = ExamenUi.Fila();
                foreach (var t in tramos)
                    niveles.Add(t.Aprueba switch
                    {
                        true => Pildora(Ds.ExitoSuave, ExamenUi.TintaExito, $"{t.Etiqueta}  ✓"),
                        false => Pildora(Ds.PeligroSuave, Ds.Peligro, $"{t.Etiqueta}  ✗"),
                        _ => Pildora(ExamenUi.FondoNeutro, Ds.TintaMedia, t.Etiqueta),
                    });
                pila.Add(niveles);
                pila.Add(Ds.Secundario("✓ cumple el criterio de aprobación del sistema · ✗ no lo cumple. Aprobar o promover lo decide la institución.", 13));
            }
        }
        else pila.Add(Ds.Secundario("Este nivel está en modo simple: se ve si completó cada evaluación, sin notas, letras ni números.", 14));
        pila.Add(Ds.Secundario("El promedio es la media simple de lo ya registrado (informativa, sin ponderar, no oficial). Una evaluación sin calificar no es un cero: se ve como un guion.", 13));
        return BoletinUi.Relieve(pila, 26, new Thickness(26, 20));
    }
}
