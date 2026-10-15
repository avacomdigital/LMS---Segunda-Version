using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Evaluaciones (MOD-010), la entrada del MENÚ PRINCIPAL: el profesor ve los exámenes de sus cursos instalados y toca «Aplicar» sin necesidad de estar dentro
/// de una clase (con la biblioteca real el examen no aparece en la secuencia de la clase: el aula pide el curso con <c>mode=class</c> y el examen es de modo
/// <c>exam</c>). Aplicar abre <see cref="ExamenAplicarPage"/> con el curso y el examen ya elegidos; debajo, los exámenes que ya aplicó, cada uno con su panel.
///
/// <b>Buscador y filtros</b> (los mismos de «Clase de hoy»): el <see cref="SearchFilterBar"/> con texto libre, País y Nivel a la vista y, bajo «Más filtros», Grado y
/// Materia. Un examen no trae clasificación propia: hereda la de su CURSO, que sale del catálogo del aula (<see cref="IAulaApi.CursosAsync"/>, la misma lectura que
/// «Clase de hoy») y se cruza por <c>curso_ref</c>. El texto busca, sin tildes ni mayúsculas y con todas las palabras, en el título del examen, su lección y todos los
/// campos del curso (<see cref="IndiceDeCursos.Campos"/>). Un examen cuyo curso no está en el catálogo (otra materia, no asignada a esta persona) sólo se oculta si se
/// elige algún selector; el texto sigue buscando en su título y el de su curso. El buscador vive fuera de lo que se repinta: lo escrito y lo elegido sobreviven a cada
/// lectura (8 s) y los selectores sólo se vuelven a poblar cuando cambia el conjunto de cursos, conservando la elección.
///
/// Todo se toca; el texto es opcional (los selectores son la vía táctil). Con la biblioteca cerrada se dice, con su sugerencia, y lo ya aplicado sigue disponible.
/// </summary>
public partial class EvaluacionesPage : ContentPage
{
    private const int MaximoDeAplicados = 8;
    private const double AnchoMaximo = 1280;

    private readonly FilterPicker _pais = new() { Placeholder = "Todos los países" };
    private readonly FilterPicker _nivel = new() { Placeholder = "Todos los niveles" };
    private readonly FilterPicker _grado = new() { Placeholder = "Todos los grados" };
    private readonly FilterPicker _materia = new() { Placeholder = "Todas las materias" };

    private bool _visible, _cargando, _hayDatos;
    private string _firma = string.Empty, _firmaDeCursos = string.Empty;
    private IDispatcherTimer? _sondeo;
    private ExamenesDisponibles? _disponibles;
    private IReadOnlyList<AsignacionDeExamen>? _aplicados;
    private string? _errorDeCatalogo;
    private CatalogoAula? _catalogo;
    private Dictionary<string, List<CursoClasificado>> _clasificacion = [];

    private static string Actor => Sesion.ProfesorId;

    public EvaluacionesPage()
    {
        InitializeComponent();
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, () => CargarAsync(forzar: true), 170, "evaluaciones-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Menú principal", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 220, "evaluaciones-volver").Vista);
        // País y Nivel a la vista; Grado y Materia bajo «Más filtros»: la misma disposición que «Clase de hoy». Cualquier cambio repinta sólo la lista de exámenes.
        foreach (var filtro in new[] { _pais, _nivel })
        {
            filtro.SelectionChanged += (_, _) => PintarDisponibles();
            Buscador.AgregarFiltro(filtro);
        }
        foreach (var filtro in new[] { _grado, _materia })
        {
            filtro.SelectionChanged += (_, _) => PintarDisponibles();
            Buscador.AgregarFiltro(filtro, extra: true);
        }
        Buscador.TextChanged += (_, _) => PintarDisponibles();
        Buscador.LimpiarTapped += (_, _) => PintarDisponibles();
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            await CargarAsync(forzar: true);
            if (!_visible) return;
            _sondeo ??= Dispatcher.CreateTimer();
            _sondeo.Interval = TimeSpan.FromSeconds(8);
            _sondeo.Tick -= OnSondeo;
            _sondeo.Tick += OnSondeo;
            _sondeo.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "EvaluacionesPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _sondeo?.Stop();
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try { await CargarAsync(forzar: false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "EvaluacionesPage.OnSondeo", ex); }
    }

    // ------------------------------------------------------------------------------------------------ leer

    private async Task CargarAsync(bool forzar)
    {
        if (_cargando || !_visible) return;
        _cargando = true;
        try
        {
            var api = Sesion.Evaluacion;
            var tDisponibles = api.ExamenesDisponiblesAsync(Actor, Sesion.FuenteAula);
            var tAplicados = api.AsignacionesAsync(Actor);
            // El catálogo del aula (la clasificación de cada curso) cambia poco: se lee al entrar y al pulsar «Actualizar», no en cada sondeo.
            Task<CatalogoAula?> tCatalogo = _catalogo is null || forzar ? Sesion.Aula.CursosAsync() : Task.FromResult<CatalogoAula?>(_catalogo);
            try { await Task.WhenAll(tDisponibles, tAplicados, tCatalogo); }
            catch (Exception ex) { RegistroDeFallos.Escribir("ops", "EvaluacionesPage.Cargar", ex); }
            if (!_visible) return;

            var disponibles = tDisponibles.IsCompletedSuccessfully ? tDisponibles.Result : null;
            var aplicados = tAplicados.IsCompletedSuccessfully ? tAplicados.Result : null;
            if (disponibles is null && aplicados is null && _hayDatos) return;       // un tropiezo del sondeo no borra lo que ya se ve
            var error = disponibles is null ? ExamenTexto.Error(api.UltimoError, api.UltimoMotivo) : null;
            _disponibles = disponibles ?? _disponibles;
            _aplicados = aplicados?.Asignaciones.Where(a => a.Estado != "archivada").Take(MaximoDeAplicados).ToList() ?? _aplicados;
            _errorDeCatalogo = error;
            if (tCatalogo.IsCompletedSuccessfully && tCatalogo.Result is { } catalogo && !ReferenceEquals(catalogo, _catalogo))
            {
                _catalogo = catalogo;
                _clasificacion = FiltroDeExamenes.Indexar(catalogo);
            }
            _hayDatos = _hayDatos || disponibles is not null || aplicados is not null;

            var firma = JsonSerializer.Serialize(new { d = _disponibles, a = _aplicados, e = _errorDeCatalogo, c = _clasificacion.Count });
            if (!forzar && firma == _firma) return;
            _firma = firma;
            PoblarFiltros();
            PintarDisponibles();
            PintarAplicados();
        }
        finally { _cargando = false; }
    }

    // ----------------------------------------------------------------------------------------- filtros

    /// <summary>
    /// Los selectores ofrecen sólo lo que hay entre los cursos que TIENEN examen (valores distintos, en el orden de la clasificación). Sólo se vuelven a poblar cuando cambia ese
    /// conjunto de cursos, y entonces se conserva lo elegido: un sondeo que no cambia nada no debe devolver un filtro a «todos».
    /// </summary>
    private void PoblarFiltros()
    {
        var cursos = _disponibles?.Cursos.Select(c => c.CursoRef).ToList() ?? [];
        var firma = string.Join("|", cursos.OrderBy(c => c, StringComparer.Ordinal)) + $"#{_clasificacion.Count}";
        if (firma == _firmaDeCursos) return;
        _firmaDeCursos = firma;
        var elegidos = (_pais.Selected, _nivel.Selected, _grado.Selected, _materia.Selected);
        var (paises, niveles, grados, materias) = FiltroDeExamenes.Opciones(cursos, _clasificacion);
        _pais.Poblar(paises);
        _nivel.Poblar(niveles);
        _grado.Poblar(grados);
        _materia.Poblar(materias);
        _pais.Elegir(elegidos.Item1);
        _nivel.Elegir(elegidos.Item2);
        _grado.Elegir(elegidos.Item3);
        _materia.Elegir(elegidos.Item4);
    }

    private bool HaySelector => _pais.Selected is not null || _nivel.Selected is not null || _grado.Selected is not null || _materia.Selected is not null;

    private bool HayFiltros => HaySelector || IndiceDeCursos.Normalizar(Buscador.Text).Length > 0;

    // ---------------------------------------------------------------------------------------------- pintar

    private static View Seccion(params View[] contenido)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        foreach (var vista in contenido) pila.Add(vista);
        return pila;
    }

    // ---- los exámenes de los cursos instalados
    private void PintarDisponibles()
    {
        DisponiblesHost.Clear();
        ResumenLabel.IsVisible = false;
        if (_disponibles is null)
        {
            DisponiblesHost.Add(ExamenUi.Aviso("No se pudieron leer los exámenes de tus cursos", _errorDeCatalogo ?? "El aula no contestó. Se vuelve a intentar sola.", Tono.Ambar));
            return;
        }
        if (!_disponibles.Disponible)
        {
            var detalle = string.Join(" ", new[] { _disponibles.Motivo, _disponibles.Sugerencia }.Where(x => !string.IsNullOrWhiteSpace(x)));
            DisponiblesHost.Add(ExamenUi.Aviso("AVACOM Contenido no está disponible", detalle.Length > 0 ? detalle : "Abre la aplicación de contenido y vuelve a intentarlo.", Tono.Ambar));
            return;
        }
        if (_disponibles.Total == 0)
        {
            DisponiblesHost.Add(ExamenUi.Aviso("Tus cursos no traen ningún examen",
                "Los exámenes los crea AVACOM Contenido. Cuando un curso instalado tenga uno, aparecerá aquí.", Tono.Info));
            if (_disponibles.Omitidos is { Count: > 0 } omitidos)
                DisponiblesHost.Add(Ds.Secundario($"{ExamenTexto.Plural(omitidos.Count, "curso no se pudo leer", "cursos no se pudieron leer")} ahora; se vuelve a intentar solo.", 14));
            return;
        }

        var palabras = IndiceDeCursos.Palabras(Buscador.Text);
        var coinciden = 0;
        foreach (var curso in _disponibles.Cursos)
        {
            _clasificacion.TryGetValue(curso.CursoRef, out var clasificacion);
            var visibles = curso.Examenes
                .Where(e => FiltroDeExamenes.Coincide(curso, e, clasificacion, _pais.Selected, _nivel.Selected, _grado.Selected, _materia.Selected, palabras)).ToList();
            if (visibles.Count == 0) continue;
            coinciden += visibles.Count;
            var bloque = new VerticalStackLayout { Spacing = 8 };
            var cl = clasificacion is { Count: > 0 } ? clasificacion[0].Curso.Clasificacion : null;
            var etiqueta = (curso.Titulo ?? curso.CursoRef) + (cl is { Resumen.Length: > 0 } ? $"  ·  {cl.Resumen}" : string.Empty);
            bloque.Add(EstudioUi.Eyebrow(etiqueta.ToUpperInvariant()));
            foreach (var examen in visibles) bloque.Add(FilaDeExamen(curso, examen));
            DisponiblesHost.Add(bloque);
        }

        ResumenLabel.Text = HayFiltros
            ? $"{coinciden} de {ExamenTexto.Plural(_disponibles.Total, "examen", "exámenes")} coinciden"
            : ExamenTexto.Plural(_disponibles.Total, "examen disponible", "exámenes disponibles");
        ResumenLabel.IsVisible = true;
        if (coinciden == 0) DisponiblesHost.Add(SinResultados());
        if (_disponibles.Omitidos is { Count: > 0 } sinLeer)
            DisponiblesHost.Add(Ds.Secundario($"{ExamenTexto.Plural(sinLeer.Count, "curso no se pudo leer", "cursos no se pudieron leer")} ahora; se vuelve a intentar solo.", 14));
    }

    private View SinResultados()
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Aviso("Sin resultados con estos filtros", "Prueba con otra búsqueda o quita algún filtro para volver a ver los exámenes.", Tono.Info));
        var limpiar = ExamenUi.Accion("Limpiar filtros", Ds.Rango.Secondary, () =>
        {
            Buscador.Limpiar();
            PintarDisponibles();
            return Task.CompletedTask;
        }, 220, "evaluaciones-limpiar", margen: false);
        limpiar.Vista.HorizontalOptions = LayoutOptions.Start;        // la cápsula llena la fila si no se le dice dónde quedarse
        pila.Add(limpiar.Vista);
        return pila;
    }

    private View FilaDeExamen(CursoConExamenes curso, ExamenDisponible examen)
    {
        var textos = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = examen.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
        var datos = new List<string>();
        if (!string.IsNullOrWhiteSpace(examen.LeccionTitulo)) datos.Add(examen.LeccionTitulo!);
        if (examen.Preguntas is { } n) datos.Add(ExamenTexto.Plural(n, "pregunta", "preguntas"));
        if (examen.Abiertas > 0) datos.Add(examen.Abiertas == 1 ? "Hay una aplicación abierta" : $"Hay {examen.Abiertas} aplicaciones abiertas");
        else if (examen.Aplicaciones > 0) datos.Add(examen.Aplicaciones == 1 ? "Ya se aplicó una vez" : $"Ya se aplicó {examen.Aplicaciones} veces");
        if (datos.Count > 0) textos.Add(Ds.Secundario(string.Join(" · ", datos), 14));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(textos, 0, 0);
        var aplicar = ExamenUi.Accion("Aplicar", Ds.Rango.Primary, () => AplicarAsync(curso, examen), 150, $"evaluaciones-aplicar-{curso.CursoRef}-{examen.ObjetoRef}", 56, margen: false);
        aplicar.Vista.VerticalOptions = LayoutOptions.Center;
        fila.Add(aplicar.Vista, 1, 0);
        return new Border
        {
            BackgroundColor = Color.FromArgb("#FAFAFB"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(16, 10),
            StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = fila,
        };
    }

    /// <summary>Lleva a «Aplicar examen» con el curso y el examen ya elegidos. Sin clase: el examen nace suelto y se encuentra desde aquí.</summary>
    private Task AplicarAsync(CursoConExamenes curso, ExamenDisponible examen)
    {
        var consulta = new (string Clave, string? Valor)[]
        {
            ("curso", curso.CursoRef), ("objeto", examen.ObjetoRef), ("fuente", _disponibles?.Fuente ?? Sesion.FuenteAula),
            ("titulo", examen.Titulo), ("curso_titulo", curso.Titulo),
        };
        return Shell.Current.GoToAsync("examen-aplicar?" + string.Join("&", consulta.Select(c => $"{c.Clave}={Uri.EscapeDataString(c.Valor ?? string.Empty)}")));
    }

    // ---- lo que ya se aplicó
    private void PintarAplicados()
    {
        AplicadosHost.Clear();
        if (_aplicados is null || _aplicados.Count == 0)
        {
            AplicadosHost.Add(Ds.Secundario(_aplicados is null ? "No se pudo leer la lista ahora." : "Todavía no has aplicado ninguno.", 15));
            return;
        }
        foreach (var a in _aplicados) AplicadosHost.Add(FilaDeAplicado(a));
    }

    private View FilaDeAplicado(AsignacionDeExamen a)
    {
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = a.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        textos.Add(Ds.Secundario(string.Join(" · ", new[] { a.GrupoRotulo, a.CursoRotulo }.Where(x => !string.IsNullOrWhiteSpace(x))), 14));
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila(ExamenTexto.EstadoAsignacion(a.Estado), ExamenTexto.TonoAsignacion(a.Estado), 13));
        pastillas.Add(ExamenUi.PildoraEnFila($"Nivel {Niveles.Rotulo(a.NivelExamen)}", Tono.Neutro, 13));
        if (a.Totales is { } t)
        {
            var entregaron = t.Entregados + t.EnRevision + t.Calificados;
            pastillas.Add(ExamenUi.PildoraEnFila($"{entregaron} de {t.Destinatarios} entregaron", entregaron > 0 ? Tono.Exito : Tono.Neutro, 13));
            if (t.EnCurso > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{t.EnCurso} presentando", Tono.Info, 13));
            if (t.Suspendidos + t.Restaurando > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{t.Suspendidos + t.Restaurando} esperan reactivación", Tono.Ambar, 13));
            if (t.ReactivosPorRevisar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{t.ReactivosPorRevisar} por revisar", Tono.Violeta, 13));
            if (t.ListosParaPublicar > 0) pastillas.Add(ExamenUi.PildoraEnFila($"{t.ListosParaPublicar} listos para publicar", Tono.Info, 13));
        }
        textos.Add(pastillas);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(textos, 0, 0);
        var abrir = ExamenUi.Accion("Abrir panel", Ds.Rango.Secondary, () => Shell.Current.GoToAsync($"examen-panel?asignacion={Uri.EscapeDataString(a.Id)}"),
                                    170, $"evaluaciones-panel-{a.Id}", 56, margen: false);
        abrir.Vista.VerticalOptions = LayoutOptions.Center;
        fila.Add(abrir.Vista, 1, 0);
        return new Border
        {
            BackgroundColor = Color.FromArgb("#FAFAFB"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(16, 10),
            StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = fila,
        };
    }
}
