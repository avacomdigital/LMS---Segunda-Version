using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El boletín de un estudiante (MOD-011), vista del profesor. Se abre desde la lista de estudiantes del libro con <c>calificacion-estudiante?alumno=&amp;grupo=&amp;nombre=</c>. Muestra todo lo que lleva
/// el estudiante en el grupo —resumen, insights, notas por curso— sin descargar todas sus evaluaciones: el nodo manda el resumen y los cursos, y las evaluaciones de cada curso se piden por
/// páginas de 20 cuando el profesor lo abre. Con cientos de evaluaciones al año esa es la diferencia entre una página que se lee y una tabla que no.
///
/// El nodo calcula todo (promedios, tendencia, aprobadas); aquí sólo se enseña. El promedio es simple e informativo; lo pendiente es un guion, no un cero; en modo simple no hay notas ni cifras.
/// </summary>
[QueryProperty(nameof(AlumnoId), "alumno")]
[QueryProperty(nameof(GrupoId), "grupo")]
[QueryProperty(nameof(Nombre), "nombre")]
public partial class CalificacionEstudiantePage : ContentPage
{
    private const double AnchoMaximo = 1200;
    private const int PorPagina = 20, Recientes = 8, CursosPorTanda = 8;

    public string AlumnoId { get; set; } = string.Empty;
    public string GrupoId { get; set; } = string.Empty;
    public string Nombre { get; set; } = string.Empty;

    /// <summary>Las evaluaciones de un curso que ya se pidieron, y cuántas hay en total.</summary>
    private sealed class PaginaCargada
    {
        public List<EvaluacionDelBoletin> Items { get; } = [];
        public int Total { get; set; }
        public bool Cargando { get; set; }
    }

    private readonly AvisoTemporal _aviso;
    private readonly Dictionary<string, PaginaCargada> _paginas = [];
    private readonly HashSet<string> _abiertos = [];
    private readonly Avacom.Lms.Ops.Calificaciones.Ui.HojaDeAjuste _hojaAjuste = new();
    // Las recomendaciones del profesor (la cuarta pregunta del boletín): lo que está tocado y si difiere de lo guardado. Una lectura del nodo no pisa lo que el profesor está eligiendo.
    private readonly HashSet<string> _recomendaciones = [];
    private bool _recomendacionesTocadas, _guardandoRecomendaciones;
    private readonly ContentView _edicionHost = new();
    private BoletinDelEstudiante? _boletin;
    private string? _materia;
    private bool _edicion;
    private int _cursosVisibles = CursosPorTanda;
    private bool _visible, _cargando, _primeraLectura = true;
    private long _ultimaLectura;

    private static IGradebookApi Api => Sesion.Gradebook;

    public CalificacionEstudiantePage()
    {
        InitializeComponent();
        Raiz.Add(_hojaAjuste);
        _aviso = new AvisoTemporal(ResultadoHost);
        AccionesHost.Add(_edicionHost);
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Actualizar", CargarAsync), 170, "boletin-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 150, "boletin-volver").Vista);
        PintarBotonDeEdicion();
    }

    /// <summary>«Activar la edición» es de las calificaciones (no del curso): con la edición activa cada nota del boletín ofrece «Editar».</summary>
    private void PintarBotonDeEdicion()
    {
        if (!CalificacionesUi.PuedeCalificar) { _edicionHost.Content = null; return; }
        _edicionHost.Content = ExamenUi.Accion(_edicion ? "Desactivar la edición" : "Activar la edición", _edicion ? Ds.Rango.Secondary : Ds.Rango.Quiet,
            CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Edicion", AlternarEdicionAsync), 220, "boletin-edicion").Vista;
    }

    private Task AlternarEdicionAsync()
    {
        _edicion = !_edicion;
        PintarBotonDeEdicion();
        _aviso.Mostrar(_edicion ? "Edición activada" : "Edición desactivada",
            _edicion ? "Cada nota ofrece «Editar». Todo ajuste pide un motivo y queda en el historial y en la bitácora con tu nombre y la hora." : "El boletín vuelve a ser de sólo lectura.",
            _edicion ? Tono.Info : Tono.Neutro);
        Pintar();
        return Task.CompletedTask;
    }

    private async Task EditarAsync(string calificacionId, string evaluacion)
    {
        var ajustado = await _hojaAjuste.MostrarAsync(calificacionId, _boletin?.Alumno.Rotulo ?? Nombre, evaluacion);
        if (ajustado && _visible) await CargarAsync();
    }

    private async Task FiltrarMateriaAsync(string? materia)
    {
        if (materia == _materia) return;
        _materia = materia;
        _paginas.Clear();
        await CargarAsync();
    }

    // ------------------------------------------------------------------------------------- recomendaciones

    private Task AlternarRecomendacionAsync(string codigo)
    {
        if (!_recomendaciones.Add(codigo)) _recomendaciones.Remove(codigo);
        _recomendacionesTocadas = true;
        Pintar();
        return Task.CompletedTask;
    }

    /// <summary>Guarda las recomendaciones elegidas (la observación GENERAL del periodo). El nodo deja el asiento con quién y cuándo; repetir lo mismo no deja nada.</summary>
    private async Task GuardarRecomendacionesAsync()
    {
        if (_boletin is not { } b || _guardandoRecomendaciones) return;
        _guardandoRecomendaciones = true;
        Pintar();
        try
        {
            var api = Api;
            var general = b.Observaciones?.FirstOrDefault(o => o.EsGeneral);
            var r = await api.ObservarAsync(CalificacionesUi.Actor, AlumnoId, GrupoId, _recomendaciones.ToList(), general?.Texto, null, general?.Version);
            if (!_visible) return;
            if (r is null)
            {
                _aviso.Mostrar("No se pudieron guardar las recomendaciones", CalificacionesUi.Error(api), Tono.Ambar);
                if (GradebookTexto.EsConflictoDeVersion(api.UltimoError)) { _recomendacionesTocadas = false; await CargarAsync(); }
                return;
            }
            _recomendacionesTocadas = false;
            _aviso.Mostrar(r.Cambiado ? "Recomendaciones guardadas" : "Ya estaban así", r.Cambiado ? "Quedaron en el boletín del estudiante y en la bitácora con tu nombre." : null, r.Cambiado ? Tono.Exito : Tono.Info);
            await CargarAsync();
        }
        finally
        {
            _guardandoRecomendaciones = false;
            if (_visible) Pintar();
        }
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!CalificacionesUi.PuedeLeer)
            {
                // TST-069: sin acceso a datos académicos, se dice y no se llama al nodo.
                EncabezadoHost.Clear();
                EncabezadoHost.Add(CalificacionesUi.SinAcceso("Este rol no accede a datos académicos", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (_boletin is null)
            {
                EncabezadoHost.Clear();
                EncabezadoHost.Add(CalificacionesUi.Estado("Armando el boletín…", "Un momento."));
            }
            await CargarAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "CalificacionEstudiantePage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    // ---------------------------------------------------------------------------------------------- leer

    private async Task CargarAsync()
    {
        if (_cargando || !_visible || string.IsNullOrWhiteSpace(AlumnoId) || string.IsNullOrWhiteSpace(GrupoId)) return;
        _cargando = true;
        try
        {
            var api = Api;
            var boletin = await api.BoletinAsync(CalificacionesUi.Actor, AlumnoId, GrupoId, limite: Recientes, materia: _materia);
            if (!_visible) return;
            if (boletin is null)
            {
                if (_boletin is not null)
                {
                    // Un tropiezo no borra lo que ya se ve.
                    ConexionHost.Clear();
                    ConexionHost.Add(CalificacionesUi.SinConexion(api)
                        ? ExamenUi.Aviso("Sin conexión con el aula", $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}.", Tono.Ambar)
                        : ExamenUi.Aviso("No se pudo actualizar el boletín", CalificacionesUi.Error(api), Tono.Ambar));
                    return;
                }
                EncabezadoHost.Clear();
                EncabezadoHost.Add(CalificacionesUi.Estado("No se pudo leer el boletín", CalificacionesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionEstudiantePage), "Reintentar", CargarAsync), 170, "boletin-reintentar", margen: false).Vista));
                return;
            }
            ConexionHost.Clear();
            _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            _boletin = boletin;
            if (!_recomendacionesTocadas)
            {
                // Lo guardado en el nodo manda mientras el profesor no haya tocado nada aquí.
                _recomendaciones.Clear();
                foreach (var r in boletin.Observaciones?.FirstOrDefault(o => o.EsGeneral)?.Recomendaciones ?? []) _recomendaciones.Add(r.Codigo);
            }
            if (_primeraLectura)
            {
                _primeraLectura = false;
                // Con un solo curso, o con uno que pide algo del profesor, se abre de entrada: es lo que se viene a ver.
                var primero = boletin.Cursos.OrderByDescending(c => c.Conteo.PorAtender).FirstOrDefault();
                if (boletin.Cursos.Count == 1 || primero is { Conteo.PorAtender: > 0 }) _abiertos.Add(primero!.CursoRef);
            }
            _paginas.Clear();      // lo leído de cada curso puede haber cambiado: se vuelve a pedir lo que está abierto
            Pintar();
        }
        finally { _cargando = false; }
        foreach (var abierto in _abiertos.ToList()) await CargarPaginaAsync(abierto, 0);
    }

    /// <summary>Pide una página de evaluaciones de un curso (la primera si <paramref name="desde"/> es 0). El nodo manda de la más reciente a la más antigua.</summary>
    private async Task CargarPaginaAsync(string cursoRef, int desde)
    {
        if (!_visible) return;
        var pagina = _paginas.TryGetValue(cursoRef, out var existente) ? existente : _paginas[cursoRef] = new PaginaCargada();
        if (pagina.Cargando) return;
        pagina.Cargando = true;
        Pintar();
        try
        {
            var api = Api;
            var r = await api.BoletinAsync(CalificacionesUi.Actor, AlumnoId, GrupoId, cursoRef, desde, PorPagina, _materia);
            if (!_visible) return;
            if (r is null)
            {
                _aviso.Mostrar("No se pudieron leer las evaluaciones de este curso", CalificacionesUi.Error(api), Tono.Ambar);
                return;
            }
            if (desde == 0) pagina.Items.Clear();
            pagina.Items.AddRange(r.Evaluaciones.Items);
            pagina.Total = r.Evaluaciones.Total;
        }
        finally
        {
            pagina.Cargando = false;
            if (_visible) Pintar();
        }
    }

    private async Task AlternarCursoAsync(string cursoRef)
    {
        if (!_abiertos.Add(cursoRef))
        {
            _abiertos.Remove(cursoRef);
            Pintar();
            return;
        }
        if (_paginas.TryGetValue(cursoRef, out var p) && p.Items.Count > 0) Pintar();
        else await CargarPaginaAsync(cursoRef, 0);
    }

    private Task MasCursosAsync()
    {
        _cursosVisibles += CursosPorTanda;
        Pintar();
        return Task.CompletedTask;
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Pintar()
    {
        if (_boletin is not { } b) return;
        var y = Desplazable.ScrollY;
        EncabezadoHost.Clear();
        EncabezadoHost.Add(Encabezado(b));
        ResumenHost.Clear();
        if (Materias(b) is { } materias) ResumenHost.Add(materias);
        ResumenHost.Add(Resumen(b));
        InsightsHost.Clear();
        InsightsHost.Add(Insights(b));
        if (CalificacionesUi.PuedeCalificar || (b.Observaciones?.Count ?? 0) > 0) InsightsHost.Add(Recomendaciones(b));
        CursosHost.Clear();
        foreach (var vista in Cursos(b)) CursosHost.Add(vista);
        PieHost.Clear();
        PieHost.Add(Pie(b));
        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }
}
