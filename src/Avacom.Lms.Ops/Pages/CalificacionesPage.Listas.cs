using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

// Las vistas del libro de un grupo. Con cientos de evaluaciones al año la tabla alumnos × evaluaciones no se puede leer ni descargar, así que lo primero que se ve es la LISTA DE ESTUDIANTES: cada
// uno con lo que lleva y lo que le falta al profesor, y al tocarlo se abre su boletín en otra página (notas, resultados e insights). La lista de EVALUACIONES es el otro eje: cada evaluación con
// lo que hay que hacer (revisar, registrar, publicar), filtrable por curso y por páginas. La TABLA completa sigue ahí para grupos chicos. Las dos listas piden el libro en modo resumen (sin celdas).
public partial class CalificacionesPage
{
    private const string VistaEstudiantes = "estudiantes", VistaEvaluaciones = "evaluaciones", VistaTabla = "tabla";
    private const int EstudiantesPorTanda = 30, EvaluacionesPorTanda = 20;

    private string _vista = VistaEstudiantes, _orden = VistaDelLibro.OrdenNombre;
    private int _verEstudiantes = EstudiantesPorTanda, _verEvaluaciones = EvaluacionesPorTanda;

    // ------------------------------------------------------------------------------------------- elegir la vista

    /// <summary>Estudiantes · Evaluaciones · Tabla. Cambiar de vista vuelve a pedir el libro: las listas lo piden en resumen y la tabla completo.</summary>
    private View SelectorDeVista(LibroDelGrupo libro)
    {
        var fichas = EstudioUi.Envolver();
        fichas.Add(EstudioUi.Chip($"Estudiantes ({libro.Alumnos.Count})", _vista == VistaEstudiantes, CalificacionesUi.Seguro(nameof(CalificacionesPage), "VistaEstudiantes", () => ElegirVistaAsync(VistaEstudiantes)), "calificaciones-vista-estudiantes"));
        fichas.Add(EstudioUi.Chip($"Evaluaciones ({libro.Asignaciones.Count})", _vista == VistaEvaluaciones, CalificacionesUi.Seguro(nameof(CalificacionesPage), "VistaEvaluaciones", () => ElegirVistaAsync(VistaEvaluaciones)), "calificaciones-vista-evaluaciones"));
        fichas.Add(EstudioUi.Chip("Tabla", _vista == VistaTabla, CalificacionesUi.Seguro(nameof(CalificacionesPage), "VistaTabla", () => ElegirVistaAsync(VistaTabla)), "calificaciones-vista-tabla"));
        return fichas;
    }

    private async Task ElegirVistaAsync(string vista)
    {
        if (vista == _vista) return;
        _vista = vista;
        _verEstudiantes = EstudiantesPorTanda;
        _verEvaluaciones = EvaluacionesPorTanda;
        _libro = null;
        _firma = string.Empty;
        Buscador.IsVisible = vista != VistaEvaluaciones;
        await CargarAsync(forzar: true);
    }

    private Task MasAsync(Action mas)
    {
        mas();
        Pintar();
        return Task.CompletedTask;
    }

    // ------------------------------------------------------------------------------------------- estudiantes

    private View ListaDeEstudiantes(LibroDelGrupo libro)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        var calif = libro.EnModoCalificaciones;
        if (libro.Alumnos.Count == 0)
        {
            pila.Add(ExamenUi.Tarjeta(Ds.Secundario("Este grupo todavía no tiene estudiantes.", 15)));
            return pila;
        }
        if (libro.Asignaciones.Count == 0)
            pila.Add(ExamenUi.Aviso("Todavía no hay evaluaciones aplicadas", "Cuando apliques un examen o una actividad, aparecerá en el boletín de cada estudiante.", Tono.Info));

        // ---- orden
        var orden = EstudioUi.Envolver();
        foreach (var (clave, rotulo) in new[] { (VistaDelLibro.OrdenNombre, "De la A a la Z"), (VistaDelLibro.OrdenAtencion, "Quien necesita atención"), (VistaDelLibro.OrdenPromedio, "Promedio más bajo primero") })
        {
            if (clave == VistaDelLibro.OrdenPromedio && !calif) continue;
            var k = clave;
            orden.Add(EstudioUi.Chip(rotulo, _orden == k, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Orden", () => MasAsync(() => { _orden = k; _verEstudiantes = EstudiantesPorTanda; })), $"calificaciones-orden-{k}", 44));
        }
        pila.Add(EstudioUi.Eyebrow("ORDENAR"));
        pila.Add(orden);

        // ---- filas
        var filas = VistaDelLibro.Ordenar(VistaDelLibro.Filas(libro, Buscador.Text), _orden).ToList();
        if (filas.Count == 0)
        {
            pila.Add(ExamenUi.Aviso("Nadie coincide con la búsqueda", "Prueba con otro nombre o quita la búsqueda para volver a ver a todos.", Tono.Info));
            return pila;
        }
        foreach (var fila in filas.Take(_verEstudiantes)) pila.Add(FilaDeEstudiante(libro, fila, calif));
        if (filas.Count > _verEstudiantes)
            pila.Add(ExamenUi.Accion($"Mostrar más ({filas.Count - _verEstudiantes} estudiantes más)", Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionesPage), "MasEstudiantes", () => MasAsync(() => _verEstudiantes += EstudiantesPorTanda)), 320, "calificaciones-mas-estudiantes", 52, margen: false).Vista);
        pila.Add(Ds.Secundario("El promedio es simple e informativo: no es una nota oficial ni está ponderado. Lo pendiente no es un cero. Toca a un estudiante para ver todas sus notas, resultados e insights.", 13));
        return pila;
    }

    /// <summary>Un estudiante: su avatar, lo que lleva (completó, con nota), su promedio sellado con el sistema del nivel y lo que le falta al profesor por hacer con él.</summary>
    private View FilaDeEstudiante(LibroDelGrupo libro, FilaDelLibro fila, bool calif)
    {
        var r = fila.Resumen;
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = fila.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 21, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 });
        if (r is not null)
        {
            textos.Add(Ds.Secundario(calif ? $"Completó {r.Conteo.Completadas} de {r.Evaluaciones} · {BoletinTexto.ConNota(r)}" : $"Completó {r.Conteo.Completadas} de {r.Evaluaciones} evaluaciones", 14));
            var avance = r.Evaluaciones == 0 ? 0 : (double)r.Conteo.Completadas / r.Evaluaciones;
            var medidor = BoletinUi.Medidor(avance, avance >= 1 ? Ds.Exito : Ds.Info, 8);
            medidor.WidthRequest = 220;
            medidor.HorizontalOptions = LayoutOptions.Start;
            textos.Add(medidor);
            var atender = BoletinTexto.PorAtender(r.Conteo);
            if (atender.Length > 0)
            {
                var pastillas = ExamenUi.Fila();
                if (r.Conteo.PorRevisar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{r.Conteo.PorRevisar} por revisar", Tono.Violeta, 12));
                if (r.Conteo.SinRegistro > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{r.Conteo.SinRegistro} sin registrar", Tono.Ambar, 12));
                if (r.Conteo.SinPublicar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{r.Conteo.SinPublicar} sin publicar", Tono.Info, 12));
                textos.Add(pastillas);
            }
        }

        var contenido = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 20 };
        contenido.Add(BoletinUi.Avatar(fila.Rotulo, 64), 0, 0);
        contenido.Add(textos, 1, 0);
        if (calif && r is not null)
            contenido.Add(BoletinUi.Sello(BoletinTexto.Promedio(r.Presentado), r.Presentado is null ? "sin nota aún" : r.Presentado.Desempeno, r.Presentado?.CumpleCriterio, 124, 30), 2, 0);
        var ver = ExamenUi.Accion("Ver boletín", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "VerBoletin", () => AbrirBoletinAsync(libro, fila)), 170, $"calificaciones-boletin-{fila.AlumnoId}", 52, margen: false);
        ver.Vista.VerticalOptions = LayoutOptions.Center;
        contenido.Add(ver.Vista, 3, 0);

        var relieve = BoletinUi.Relieve(contenido, 24, new Thickness(20, 16));
        SemanticProperties.SetDescription(relieve, $"Estudiante {fila.Rotulo}. Toca para ver su boletín.");
        Ds.Tocable(relieve, () => AbrirBoletinAsync(libro, fila));
        return relieve;
    }

    private static Task AbrirBoletinAsync(LibroDelGrupo libro, FilaDelLibro fila) =>
        Shell.Current.GoToAsync($"calificacion-estudiante?alumno={Uri.EscapeDataString(fila.AlumnoId)}&grupo={Uri.EscapeDataString(libro.Grupo.Id)}&nombre={Uri.EscapeDataString(fila.Rotulo)}");

    // ------------------------------------------------------------------------------------------- evaluaciones

    private View ListaDeEvaluaciones(LibroDelGrupo libro)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        if (libro.Asignaciones.Count == 0)
        {
            pila.Add(ExamenUi.Tarjeta(Ds.Secundario("Este grupo todavía no tiene evaluaciones aplicadas. Cuando apliques un examen o una actividad, aparecerá aquí.", 15)));
            return pila;
        }
        var calif = libro.EnModoCalificaciones;

        // La materia y el curso se eligen arriba (fichas del libro) y los aplica el nodo: aquí ya llegan sólo las evaluaciones que tocan.
        // Lo que más pide al profesor primero; a igual, la más nueva (el nodo las manda de la más antigua a la más nueva).
        var columnas = libro.Asignaciones
            .Select((a, i) => (Columna: a, Orden: i)).OrderByDescending(x => x.Columna.Conteo?.PorAtender ?? 0).ThenByDescending(x => x.Orden).Select(x => x.Columna).ToList();
        foreach (var col in columnas.Take(_verEvaluaciones)) pila.Add(FilaDeEvaluacion(libro, col, calif));
        if (columnas.Count > _verEvaluaciones)
            pila.Add(ExamenUi.Accion($"Mostrar más ({columnas.Count - _verEvaluaciones} evaluaciones más)", Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionesPage), "MasEvaluaciones", () => MasAsync(() => _verEvaluaciones += EvaluacionesPorTanda)), 320, "calificaciones-mas-evaluaciones", 52, margen: false).Vista);
        pila.Add(Ds.Secundario("Primero las que piden algo del profesor (revisar, registrar o publicar). Registrar lo calificado hace aparecer la nota de lo que se calificó antes de elegir el sistema; publicar la muestra al estudiante.", 13));
        return pila;
    }

    private View FilaDeEvaluacion(LibroDelGrupo libro, ColumnaDelLibro col, bool calif)
    {
        var c = col.Conteo;
        var textos = new VerticalStackLayout { Spacing = 5, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = col.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        textos.Add(Ds.Secundario(col.CursoRotulo ?? string.Empty, 14));
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila(GradebookTexto.TipoDeEvaluacion(col.TipoEvaluacion), Tono.Neutro, 12));
        if (c is not null)
        {
            pastillas.Add(ExamenUi.PildoraEnFila($"{c.Completadas} de {libro.Alumnos.Count} completaron", c.Completadas >= libro.Alumnos.Count && libro.Alumnos.Count > 0 ? Tono.Exito : Tono.Neutro, 12));
            if (c.PorRevisar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.PorRevisar} por revisar", Tono.Violeta, 12));
            if (c.SinRegistro > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.SinRegistro} sin registrar", Tono.Ambar, 12));
            if (c.SinPublicar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.SinPublicar} sin publicar", Tono.Info, 12));
            if (c.Publicadas > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{c.Publicadas} publicadas", Tono.Exito, 12));
        }
        textos.Add(pastillas);

        var acciones = new VerticalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center };
        if (calif && CalificacionesUi.PuedeCalificar && c is not null)
        {
            if (c.SinRegistro > 0)
                acciones.Add(ExamenUi.Accion($"Registrar lo calificado ({c.SinRegistro})", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Registrar", () => RegistrarColumnaAsync(libro, col)), 290, $"calificaciones-registrar-{col.Id}", 48, margen: false).Vista);
            if (c.SinPublicar > 0)
                acciones.Add(ExamenUi.Accion($"Publicar lo revisado ({c.SinPublicar})", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Publicar", () => PublicarColumnaAsync(libro, col)), 290, $"calificaciones-publicar-{col.Id}", 48, margen: false).Vista);
            if (col.PorRevisar > 0)
                acciones.Add(ExamenUi.Accion($"Revisar ({col.PorRevisar})", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Revisar", () => AbrirBandejaAsync(col.Id)), 290, $"calificaciones-revisar-{col.Id}", 48, margen: false).Vista);
        }

        var contenido = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 20 };
        contenido.Add(textos, 0, 0);
        contenido.Add(acciones, 1, 0);
        return BoletinUi.Relieve(contenido, 24, new Thickness(22, 18));
    }
}
