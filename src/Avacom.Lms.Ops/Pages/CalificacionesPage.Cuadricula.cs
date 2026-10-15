using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

// Lo que el libro pinta: el resumen del grupo y la cuadrícula alumnos × evaluaciones. La cuadrícula son DOS piezas con filas de alto FIJO, para que casen sin medir nada: a la
// izquierda la columna del alumno, que no se mueve, y a la derecha un ScrollView horizontal con una columna por evaluación (y, en modo calificaciones, una por curso con el promedio
// simple). Con muchas evaluaciones se desplaza de lado y el alumno sigue a la vista; el desplazamiento vertical es el de la pantalla.
public partial class CalificacionesPage
{
    private const double AnchoAlumno = 210, AnchoCelda = 224, AltoCabecera = 214, Separacion = 8;
    private const double AltoFilaCalificaciones = 132, AltoFilaSimple = 92;

    private void Pintar()
    {
        if (_libro is not { } libro) return;
        var y = Desplazable.ScrollY;
        var x = _horizontal?.ScrollX ?? 0;
        TituloLabel.Text = libro.Grupo.Nombre;
        SubtituloLabel.Text = string.Join(" · ", new[]
        {
            $"Grupo {libro.Grupo.Codigo}", SelectorDeGrupo.RotuloDeNivel(libro.Grupo.NivelClave), string.IsNullOrWhiteSpace(libro.Grupo.Periodo) ? null : $"periodo {libro.Grupo.Periodo}",
        }.Where(p => p is not null));
        Buscador.IsVisible = true;
        ContenidoHost.Clear();
        _horizontal = null;
        ContenidoHost.Add(Resumen(libro));
        ContenidoHost.Add(Cuadricula(libro));
        if (y > 1 || x > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try
                {
                    await Desplazable.ScrollToAsync(0, y, false);
                    if (_horizontal is not null && x > 1) await _horizontal.ScrollToAsync(x, 0, false);
                }
                catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    // ----------------------------------------------------------------------------------------------- resumen

    private View Resumen(LibroDelGrupo libro)
    {
        var calif = libro.EnModoCalificaciones;
        var texto = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        texto.Add(new Label { Text = calif ? "Modo calificaciones" : "Modo simple", FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta });
        texto.Add(Ds.Secundario(calif
            ? $"Escala del nivel: {libro.Escala?.Nombre ?? "sin escala elegida"}"
            : "Este nivel no muestra notas: sólo si cada estudiante completó la evaluación.", 15));
        texto.Add(Ds.Secundario($"Intento que cuenta: {GradebookTexto.Politica(libro.PoliticaIntentos).ToLowerInvariant()}", 15));

        var totales = new HorizontalStackLayout { Spacing = 30, VerticalOptions = LayoutOptions.Center };
        if (calif)
        {
            totales.Add(ExamenUi.Total(libro.Totales.PorRevisar, "por revisar", ExamenUi.TintaVioleta));
            totales.Add(ExamenUi.Total(libro.Totales.SinPublicar, "sin publicar", ExamenUi.TintaInfo));
            totales.Add(ExamenUi.Total(libro.Totales.Pendientes, "pendientes", Ds.Tinta));
        }
        else
        {
            totales.Add(ExamenUi.Total(libro.Totales.Alumnos, "estudiantes", Ds.Tinta));
            totales.Add(ExamenUi.Total(libro.Totales.Asignaciones, "evaluaciones", Ds.Tinta));
        }

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 30 };
        fila.Add(texto, 0, 0);
        fila.Add(totales, 1, 0);

        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(fila);
        pila.Add(Ds.Secundario(calif
            ? "El promedio simple de cada estudiante es informativo: no es una nota oficial ni está ponderado. Una calificación provisional puede cambiar hasta que se publique."
            : "Cada celda dice en qué va cada estudiante: ○ no ha empezado · ◐ va en progreso · ● completó. No hay notas ni números.", 14));

        var acciones = ExamenUi.Fila();
        if (calif && CalificacionesUi.PuedeCalificar)
        {
            var pendientes = VistaDelLibro.RevisionesPendientes(libro);
            acciones.Add(ExamenUi.Accion($"Revisiones pendientes ({pendientes})", pendientes > 0 ? Ds.Rango.Primary : Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionesPage), "Revisiones", () => AbrirBandejaAsync(null)), null, "calificaciones-revisiones").Vista);
        }
        if (CalificacionesUi.PuedeConfigurar)
            acciones.Add(ExamenUi.Accion("Configuración académica", Ds.Rango.Secondary,
                CalificacionesUi.Seguro(nameof(CalificacionesPage), "Configuracion", () => Shell.Current.GoToAsync("calificaciones-config")), null, "calificaciones-configuracion").Vista);
        if (acciones.Children.Count > 0) pila.Add(acciones);
        return ExamenUi.Tarjeta(pila);
    }

    // --------------------------------------------------------------------------------------------- cuadrícula

    private View Cuadricula(LibroDelGrupo libro)
    {
        var calif = libro.EnModoCalificaciones;
        var filas = VistaDelLibro.Filas(libro, Buscador.Text);
        var columnas = VistaDelLibro.Columnas(libro, EvaluacionElegida);
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Estudiantes y evaluaciones"));

        // ---- sin resultados: cada vacío dice por qué
        if (libro.Alumnos.Count == 0)
        {
            pila.Add(Ds.Secundario("Este grupo todavía no tiene estudiantes.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        if (libro.Asignaciones.Count == 0)
        {
            pila.Add(Ds.Secundario("Este grupo todavía no tiene evaluaciones aplicadas. Cuando apliques un examen o una actividad, aparecerá aquí como una columna.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        if (filas.Count == 0 || columnas.Count == 0)
        {
            pila.Add(ExamenUi.Aviso("Sin resultados con estos filtros", "Prueba con otra búsqueda o quita el filtro de evaluación para volver a ver a todos.", Tono.Info));
            var limpiar = ExamenUi.Accion("Limpiar filtros", Ds.Rango.Secondary, () =>
            {
                Buscador.Limpiar();
                Repintar();
                return Task.CompletedTask;
            }, 220, "calificaciones-limpiar", margen: false);
            limpiar.Vista.HorizontalOptions = LayoutOptions.Start;
            pila.Add(limpiar.Vista);
            return ExamenUi.Tarjeta(pila);
        }

        var alto = calif ? AltoFilaCalificaciones : AltoFilaSimple;
        IReadOnlyList<(string CursoRef, string Rotulo)> cursos = calif ? VistaDelLibro.Cursos(columnas) : [];
        var rotulos = new Dictionary<string, string>();

        // ---- a la izquierda, el alumno (no se mueve)
        var izquierda = new VerticalStackLayout { Spacing = Separacion, WidthRequest = AnchoAlumno, VerticalOptions = LayoutOptions.Start };
        var cuantos = Ds.Secundario(filas.Count == libro.Alumnos.Count ? $"{libro.Alumnos.Count} en el grupo" : $"{filas.Count} de {libro.Alumnos.Count}", 13);
        cuantos.Margin = new Thickness(2, 0, 0, 2);          // sin este aire el primer número se ve recortado por el borde de la celda
        izquierda.Add(new Border
        {
            HeightRequest = AltoCabecera, WidthRequest = AnchoAlumno, StrokeThickness = 0, BackgroundColor = Colors.Transparent,
            Content = new VerticalStackLayout
            {
                VerticalOptions = LayoutOptions.End, Spacing = 2,
                Children = { EstudioUi.Eyebrow("ESTUDIANTE"), cuantos },
            },
        });
        foreach (var fila in filas)
        {
            rotulos[fila.AlumnoId] = fila.Rotulo;
            izquierda.Add(CeldaDeAlumno(fila, alto));
        }

        // ---- a la derecha, una columna por evaluación (y por curso, el promedio simple)
        var rejilla = new Grid { ColumnSpacing = Separacion, RowSpacing = Separacion, VerticalOptions = LayoutOptions.Start };
        rejilla.RowDefinitions.Add(new RowDefinition(AltoCabecera));
        foreach (var _ in filas) rejilla.RowDefinitions.Add(new RowDefinition(alto));
        var indice = 0;
        foreach (var col in columnas)
        {
            rejilla.ColumnDefinitions.Add(new ColumnDefinition(AnchoCelda));
            rejilla.Add(EncabezadoDeColumna(libro, col, calif), indice, 0);
            for (var f = 0; f < filas.Count; f++) rejilla.Add(Celda(filas[f], col, calif, alto), indice, f + 1);
            indice++;
        }
        foreach (var (cursoRef, rotulo) in cursos)
        {
            rejilla.ColumnDefinitions.Add(new ColumnDefinition(AnchoCelda));
            rejilla.Add(EncabezadoDePromedio(rotulo), indice, 0);
            for (var f = 0; f < filas.Count; f++) rejilla.Add(CeldaDePromedio(filas[f], cursoRef, alto), indice, f + 1);
            indice++;
        }

        _horizontal = new ScrollView { Orientation = ScrollOrientation.Horizontal, HorizontalScrollBarVisibility = ScrollBarVisibility.Always, Content = rejilla };
        var contenedor = new Grid { ColumnDefinitions = [new ColumnDefinition(AnchoAlumno), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        contenedor.Add(izquierda, 0, 0);
        contenedor.Add(_horizontal, 1, 0);
        pila.Add(contenedor);
        if (columnas.Count + cursos.Count > 3) pila.Add(Ds.Secundario("Hay más columnas a la derecha: desliza la tabla de lado. El nombre del estudiante se queda a la vista.", 13));
        return ExamenUi.Tarjeta(pila);
    }

    private static View CeldaDeAlumno(FilaDelLibro fila, double alto) => new Border
    {
        BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(14, 8), HeightRequest = alto, WidthRequest = AnchoAlumno,
        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
        Content = new Label { Text = fila.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 },
    };

    private View EncabezadoDeColumna(LibroDelGrupo libro, ColumnaDelLibro col, bool calif)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = col.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        pila.Add(new Label { Text = col.CursoRotulo ?? string.Empty, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 });
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila(GradebookTexto.TipoDeEvaluacion(col.TipoEvaluacion), Tono.Neutro, 12));
        if (calif && col.PorRevisar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{col.PorRevisar} por revisar", Tono.Violeta, 12));
        pila.Add(pastillas);

        // «Publicar lo revisado»: un toque y un aviso con el resultado; no se pregunta dos veces. Sólo si hay algo revisado sin publicar y quien está al frente califica.
        if (calif && CalificacionesUi.PuedeCalificar)
        {
            var porPublicar = VistaDelLibro.PorPublicar(libro, col.Id);
            if (porPublicar > 0)
            {
                var publicar = ExamenUi.Accion($"Publicar lo revisado ({porPublicar})", Ds.Rango.Secondary,
                    CalificacionesUi.Seguro(nameof(CalificacionesPage), "Publicar", () => PublicarColumnaAsync(libro, col)), null, $"calificaciones-publicar-{col.Id}", 48, margen: false);
                publicar.Boton.FontSize = 14;
                publicar.Boton.Padding = new Thickness(10, 0);
                pila.Add(publicar.Vista);
            }
            else pila.Add(Ds.Secundario("Nada por publicar", 13));
        }
        return new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(12, 10), HeightRequest = AltoCabecera, WidthRequest = AnchoCelda,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila,
        };
    }

    private static View EncabezadoDePromedio(string cursoRotulo)
    {
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(new Label { Text = "Promedio simple", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta });
        pila.Add(new Label { Text = cursoRotulo, FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        pila.Add(ExamenUi.PildoraEnFila("Informativo, no oficial", Tono.Neutro, 12));
        pila.Add(Ds.Secundario("Sobre 100, de lo ya registrado.", 12));
        return new Border
        {
            BackgroundColor = Color.FromArgb("#F7F7F8"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(12, 10), HeightRequest = AltoCabecera, WidthRequest = AnchoCelda,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila,
        };
    }

    private static View CeldaDePromedio(FilaDelLibro fila, string cursoRef, double alto)
    {
        var agregado = VistaDelLibro.Agregado(fila, cursoRef);
        var promedio = VistaDelLibro.PromedioSimple(agregado);
        var pila = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label { Text = promedio, FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = promedio == "—" ? Ds.TintaSuave : Ds.Tinta });
        pila.Add(Ds.Secundario(VistaDelLibro.DetalleDeAgregado(agregado), 12));
        var tarjeta = new Border
        {
            BackgroundColor = Color.FromArgb("#F7F7F8"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(12, 8), HeightRequest = alto, WidthRequest = AnchoCelda,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila,
        };
        SemanticProperties.SetDescription(tarjeta, $"Promedio simple informativo de {fila.Rotulo}: {promedio}");
        return tarjeta;
    }

    // ------------------------------------------------------------------------------------------------ celdas

    private View Celda(FilaDelLibro fila, ColumnaDelLibro col, bool calif, double alto)
    {
        var celda = VistaDelLibro.Celda(fila, col.Id);
        var c = VistaDelLibro.Describir(celda, calif);
        var pila = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
        if (!calif)
        {
            // Modo simple: sólo el estado y su símbolo. Ni un número, ni una letra.
            pila.Add(new Label { Text = c.Simbolo, FontFamily = Ds.FuenteMedia, FontSize = 28, TextColor = Ds.Tinta });
            pila.Add(new Label { Text = c.Estado, FontFamily = Ds.FuenteRegular, FontSize = 15, TextColor = Ds.TintaMedia });
        }
        else
        {
            pila.Add(CalificacionesUi.Pildora(c.Estado, c.Matiz, 12));
            pila.Add(new Label { Text = c.Principal, FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = c.Principal == "—" ? Ds.TintaSuave : Ds.Tinta });
            if (c.Secundario is not null) pila.Add(Ds.Secundario(c.Secundario, 12));
            if (c.Marcas.Count > 0)
                pila.Add(new Label { Text = string.Join(" · ", c.Marcas), FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, MaxLines = 2 });
        }

        // Qué pasa al tocarla: una calificación abre su detalle; lo que espera revisión abre la bandeja de este grupo (con esta evaluación); lo demás no es tocable.
        Func<Task>? accion = null;
        if (calif && c.CalificacionId is { } calificacionId) accion = () => AbrirDetalleAsync(calificacionId, fila.Rotulo, col.Titulo);
        else if (calif && celda is { Estado: EstadosDeResultado.Provisional or EstadosDeResultado.Reabierto }) accion = () => AbrirBandejaAsync(col.Id);

        var contenido = new Grid();
        contenido.Add(pila);
        if (accion is not null)
            contenido.Add(new Label { Text = "›", FontFamily = Ds.FuenteLigera, FontSize = 24, TextColor = Ds.TintaSuave, HorizontalOptions = LayoutOptions.End, VerticalOptions = LayoutOptions.Start });
        var tarjeta = new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(accion is null ? Ds.Filo : Color.FromArgb("#33000000")), StrokeThickness = 1, Padding = new Thickness(12, 8),
            HeightRequest = alto, WidthRequest = AnchoCelda, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = contenido,
            AutomationId = $"calificaciones-celda-{fila.AlumnoId}-{col.Id}",
        };
        SemanticProperties.SetDescription(tarjeta,
            $"{fila.Rotulo}, {col.Titulo}: {c.Estado}{(c.Principal is { } p && p != "—" ? $", {p}" : string.Empty)}{(c.Marcas.Count > 0 ? ", " + string.Join(", ", c.Marcas) : string.Empty)}{(accion is null ? string.Empty : ". Toca para abrir")}");
        if (accion is not null) Ds.Tocable(tarjeta, accion);
        return tarjeta;
    }

    // ---------------------------------------------------------------------------------------------- acciones

    private static Task AbrirDetalleAsync(string calificacionId, string alumno, string evaluacion) =>
        Shell.Current.GoToAsync($"calificacion-detalle?id={Uri.EscapeDataString(calificacionId)}&alumno={Uri.EscapeDataString(alumno)}&titulo={Uri.EscapeDataString(evaluacion)}");

    private Task AbrirBandejaAsync(string? asignacionId) =>
        Shell.Current.GoToAsync($"calificaciones-revision?grupo={Uri.EscapeDataString(_grupoDelLibro)}" + (asignacionId is null ? string.Empty : $"&asignacion={Uri.EscapeDataString(asignacionId)}"));

    /// <summary>
    /// «Publicar lo revisado» de una evaluación: un toque, sin pedir confirmación dos veces. El aviso dice cuántas se publicaron y, de las omitidas, quién y por qué (una omitida no
    /// tumba a las demás). Publicar ya publicado no duplica nada, así que reintentarlo tras perder la señal es seguro.
    /// </summary>
    private async Task PublicarColumnaAsync(LibroDelGrupo libro, ColumnaDelLibro col)
    {
        var api = Api;
        var r = await api.PublicarAsignacionAsync(CalificacionesUi.Actor, col.Id);
        if (!_visible) return;
        if (r is null) _aviso.Mostrar($"No se pudo publicar lo revisado de «{col.Titulo}»", CalificacionesUi.Error(api), Tono.Ambar);
        else
        {
            var nombres = libro.Alumnos.ToDictionary(a => a.AlumnoId, a => a.Rotulo);
            var (titulo, detalle, problemas) = VistaDelLibro.DescribirPublicacion(r, id => nombres.TryGetValue(id, out var nombre) ? nombre : "un estudiante");
            _aviso.Mostrar($"{col.Titulo}: {titulo}", detalle, problemas ? Tono.Ambar : Tono.Exito);
        }
        await CargarAsync(forzar: true);
    }
}
