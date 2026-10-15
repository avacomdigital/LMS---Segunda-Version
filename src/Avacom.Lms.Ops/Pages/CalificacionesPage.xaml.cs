using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Calificaciones (MOD-011): el libro de calificaciones de un grupo. El profesor elige nivel educativo → periodo → grupo y ve una cuadrícula alumnos × evaluaciones; cada celda
/// dice el estado y, según el MODO del nivel, la nota presentada con su resultado interno (0–100) o sólo el estado simple con su símbolo (○ ◐ ●), sin ningún número. Lo pendiente
/// nunca es un cero: es «—» con su estado. Tocar una celda con calificación abre su detalle; tocar una por revisar abre la bandeja; por columna, «Publicar lo revisado».
///
/// El nodo es la fuente de todo número: aquí sólo se enseña lo que responde. Si el nodo no responde, un banner lo dice y se CONSERVA lo último que se veía; el libro se lee de nuevo
/// solo cada 8 s (con firma, para no repintar si nada cambió). Con un rol sin acceso académico (soporte técnico) la pantalla lo dice sin llamar al nodo (TST-069).
///
/// El buscador de estudiante es un extra OPCIONAL (el nodo principal no tiene teclado): nivel, periodo y grupo son fichas que se tocan. El buscador y el filtro de evaluación viven
/// fuera de lo que se repinta, para que lo escrito y lo elegido sobrevivan a cada lectura.
/// </summary>
public partial class CalificacionesPage : ContentPage
{
    private const double AnchoMaximo = 1280;

    // Lo elegido sobrevive a salir y volver (de un detalle, de la bandeja): la persona regresa al mismo grupo.
    private static string? _nivelElegido, _periodoElegido, _grupoElegido;

    private readonly FilterPicker _evaluaciones = new() { Placeholder = "Todas las evaluaciones" };
    private readonly AvisoTemporal _aviso;
    private readonly Dictionary<string, string> _evaluacionPorRotulo = [];

    private bool _visible, _cargando, _recargar;
    private IDispatcherTimer? _sondeo;
    private EstadoPadron? _padron;
    private LibroDelGrupo? _libro;
    private string _grupoDelLibro = string.Empty;
    private string _firma = string.Empty, _firmaDeSelector = string.Empty, _firmaDeEvaluaciones = string.Empty;
    private long _ultimaLectura;
    private ScrollView? _horizontal;

    private static IGradebookApi Api => Sesion.Gradebook;

    public CalificacionesPage()
    {
        InitializeComponent();
        _aviso = new AvisoTemporal(ResultadoHost);
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Actualizar", () => CargarAsync(forzar: true)), 170, "calificaciones-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Menú principal", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 220, "calificaciones-volver").Vista);
        // El filtro de evaluación y el buscador sólo cambian lo que se ve: no vuelven a pedir nada al nodo.
        _evaluaciones.SelectionChanged += (_, _) => Repintar();
        Buscador.AgregarFiltro(_evaluaciones);
        Buscador.TextChanged += (_, _) => Repintar();
        Buscador.LimpiarTapped += (_, _) => Repintar();
    }

    private string? EvaluacionElegida => _evaluaciones.Selected is { } rotulo && _evaluacionPorRotulo.TryGetValue(rotulo, out var id) ? id : null;

    // ------------------------------------------------------------------------------------- ciclo de vida

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!CalificacionesUi.PuedeLeer)
            {
                // TST-069: sin acceso a datos académicos, la pantalla lo dice y no llama al nodo (el nodo igualmente lo denegaría).
                SubtituloLabel.Text = string.Empty;
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.SinAcceso("Este rol no accede a datos académicos", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (_libro is null)
            {
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.Estado("Leyendo el libro de calificaciones…", "Un momento."));
            }
            await CargarAsync(forzar: true);
            if (!_visible) return;
            _sondeo ??= Dispatcher.CreateTimer();
            _sondeo.Interval = TimeSpan.FromSeconds(8);
            _sondeo.Tick -= OnSondeo;
            _sondeo.Tick += OnSondeo;
            _sondeo.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "CalificacionesPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _sondeo?.Stop();
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try { await CargarAsync(forzar: false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "CalificacionesPage.OnSondeo", ex); }
    }

    // ---------------------------------------------------------------------------------------------- leer

    /// <summary>
    /// Lee el padrón (al entrar y al actualizar) y el libro del grupo elegido. Una lectura que llega mientras otra sigue en vuelo no se pierde: si pide forzar, se repite al terminar
    /// (la persona tocó otro grupo mientras se leía el anterior).
    /// </summary>
    private async Task CargarAsync(bool forzar)
    {
        if (!_visible || !CalificacionesUi.PuedeLeer) return;
        if (_cargando)
        {
            if (forzar) _recargar = true;
            return;
        }
        _cargando = true;
        try
        {
            do
            {
                _recargar = false;
                await LeerAsync(forzar);
                forzar = true;
            } while (_recargar && _visible);
        }
        finally { _cargando = false; }
    }

    private async Task LeerAsync(bool forzar)
    {
        // ---- los grupos (y de ellos, el nivel y el periodo): sólo al entrar y al actualizar
        if (forzar || _padron is null)
        {
            var padron = await Sesion.Padron.EstadoAsync();
            if (!_visible) return;
            if (padron is null)
            {
                var error = Sesion.Padron.UltimoError;
                if (_padron is null)
                {
                    SelectorHost.Clear();
                    ContenidoHost.Clear();
                    ContenidoHost.Add(CalificacionesUi.Estado("No se pudieron leer los grupos",
                        GradebookTexto.SinConexion(error) ? "Sin conexión con el nodo del aula. Se vuelve a intentar solo." : (error?.Detalle ?? Sesion.Padron.UltimoMotivo ?? "El nodo no contestó.")));
                    MostrarBanner(GradebookTexto.SinConexion(error) ? null : error?.Detalle, GradebookTexto.SinConexion(error));
                    return;
                }
                MostrarBanner(error?.Detalle, GradebookTexto.SinConexion(error));
            }
            else _padron = padron;
        }

        var grupos = _padron!.Grupos;
        if (!_padron.Instalado || grupos.Count == 0)
        {
            SelectorHost.Clear();
            Buscador.IsVisible = false;
            ContenidoHost.Clear();
            ContenidoHost.Add(CalificacionesUi.Estado(_padron.Instalado ? "Todavía no hay grupos" : "El nodo todavía no tiene una organización instalada",
                _padron.Instalado ? "Cuando exista un grupo con estudiantes, su libro de calificaciones aparecerá aquí." : "Sin organización no hay grupos ni estudiantes. Pídele a la administración que la instale."));
            return;
        }

        // ---- nivel → periodo → grupo
        var eleccion = SelectorDeGrupo.Resolver(grupos, _nivelElegido, _periodoElegido, _grupoElegido);
        (_nivelElegido, _periodoElegido, _grupoElegido) = (eleccion.Nivel, eleccion.Periodo, eleccion.Grupo?.Id);
        PintarSelector(eleccion);
        if (eleccion.Grupo is not { } grupo) return;

        // ---- el libro del grupo
        var api = Api;
        var libro = await api.LibroAsync(CalificacionesUi.Actor, grupo.Id);
        if (!_visible || grupo.Id != _grupoElegido) return;
        if (libro is null)
        {
            // Un tropiezo no borra lo que ya se ve: sin conexión, o con un error que no es de este grupo, se CONSERVA el último libro y se avisa.
            if (_libro is not null && _grupoDelLibro == grupo.Id)
            {
                MostrarBanner(CalificacionesUi.Error(api), CalificacionesUi.SinConexion(api));
                return;
            }
            ContenidoHost.Clear();
            Buscador.IsVisible = false;
            ContenidoHost.Add(CalificacionesUi.Estado("No se pudo leer el libro de este grupo", CalificacionesUi.Error(api),
                ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionesPage), "Reintentar", () => CargarAsync(forzar: true)), 170, "calificaciones-reintentar", margen: false).Vista));
            MostrarBanner(CalificacionesUi.Error(api), CalificacionesUi.SinConexion(api));
            return;
        }

        ConexionHost.Clear();
        _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var firma = grupo.Id + "|" + VistaDelLibro.Firma(libro);
        _grupoDelLibro = grupo.Id;
        if (!forzar && firma == _firma) { _libro = libro; return; }       // nada cambió (el reloj del nodo no cuenta): no se repinta
        _firma = firma;
        _libro = libro;
        PoblarEvaluaciones(libro);
        Pintar();
    }

    /// <summary>
    /// El aviso de que el nodo no contesta (o rechazó la lectura). Dice qué se ve: lo último que se leyó. No es una alarma: se vuelve a intentar solo en cada sondeo y desaparece
    /// cuando una lectura llega.
    /// </summary>
    private void MostrarBanner(string? detalle, bool sinConexion)
    {
        ConexionHost.Clear();
        if (sinConexion)
            ConexionHost.Add(ExamenUi.Aviso("Sin conexión con el nodo",
                _libro is null ? "Se vuelve a intentar solo cada pocos segundos." : $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}. Se vuelve a intentar solo.", Tono.Ambar));
        else
            ConexionHost.Add(ExamenUi.Aviso("No se pudo actualizar el libro", string.IsNullOrWhiteSpace(detalle) ? "Se muestra lo último que se leyó." : detalle, Tono.Ambar));
    }

    // ----------------------------------------------------------------------------------------- el selector

    /// <summary>Nivel → periodo → grupo, en fichas de 52 px. Sólo se repinta si cambió algo (el sondeo no debe hacer parpadear las fichas).</summary>
    private void PintarSelector(EleccionDeGrupo e)
    {
        var grupos = _padron!.Grupos;
        var firma = $"{e.Nivel}|{e.Periodo}|{e.Grupo?.Id}|{string.Join(",", grupos.Select(g => $"{g.Id}:{g.Nombre}:{g.NivelClave}:{g.Periodo}"))}";
        if (firma == _firmaDeSelector) return;
        _firmaDeSelector = firma;
        SelectorHost.Clear();

        var niveles = SelectorDeGrupo.Niveles(grupos);
        if (niveles.Count > 1)
        {
            SelectorHost.Add(EstudioUi.Eyebrow("NIVEL EDUCATIVO"));
            var fila = EstudioUi.Envolver();
            foreach (var nivel in niveles)
                fila.Add(EstudioUi.Chip(SelectorDeGrupo.RotuloDeNivel(nivel), nivel == e.Nivel, CalificacionesUi.Seguro(nameof(CalificacionesPage), "ElegirNivel", () => ElegirAsync(nivel, null, null)),
                    $"calificaciones-nivel-{(nivel.Length == 0 ? "sin" : nivel)}"));
            SelectorHost.Add(fila);
        }

        var periodos = SelectorDeGrupo.Periodos(grupos, e.Nivel);
        if (periodos.Count > 1)
        {
            SelectorHost.Add(EstudioUi.Eyebrow("PERIODO"));
            var fila = EstudioUi.Envolver();
            fila.Add(EstudioUi.Chip("Todos", e.Periodo is null, CalificacionesUi.Seguro(nameof(CalificacionesPage), "ElegirPeriodo", () => ElegirAsync(e.Nivel, null, e.Grupo?.Id)), "calificaciones-periodo-todos"));
            foreach (var periodo in periodos)
                fila.Add(EstudioUi.Chip(periodo, periodo == e.Periodo, CalificacionesUi.Seguro(nameof(CalificacionesPage), "ElegirPeriodo", () => ElegirAsync(e.Nivel, periodo, e.Grupo?.Id)), $"calificaciones-periodo-{periodo}"));
            SelectorHost.Add(fila);
        }

        SelectorHost.Add(EstudioUi.Eyebrow("GRUPO"));
        var filaGrupos = EstudioUi.Envolver();
        foreach (var g in SelectorDeGrupo.Grupos(grupos, e.Nivel, e.Periodo))
        {
            var id = g.Id;
            var rotulo = g.Activo ? g.Nombre : $"{g.Nombre} (inactivo)";
            filaGrupos.Add(EstudioUi.Chip(rotulo, id == e.Grupo?.Id, CalificacionesUi.Seguro(nameof(CalificacionesPage), "ElegirGrupo", () => ElegirAsync(e.Nivel, e.Periodo, id)), $"calificaciones-grupo-{g.Codigo}"));
        }
        SelectorHost.Add(filaGrupos);
    }

    /// <summary>Cambia la elección: lo que se veía era de otro grupo, así que se suelta (no se conserva un libro ajeno) y se vuelve a leer.</summary>
    private async Task ElegirAsync(string? nivel, string? periodo, string? grupoId)
    {
        if (nivel == _nivelElegido && periodo == _periodoElegido && grupoId == _grupoElegido) return;
        (_nivelElegido, _periodoElegido, _grupoElegido) = (nivel, periodo, grupoId);
        _libro = null;
        _firma = string.Empty;
        _firmaDeSelector = string.Empty;
        Buscador.IsVisible = false;
        ConexionHost.Clear();
        ContenidoHost.Clear();
        ContenidoHost.Add(CalificacionesUi.Estado("Leyendo el libro de calificaciones…", "Un momento."));
        await CargarAsync(forzar: true);
    }

    // ------------------------------------------------------------------------------ el filtro de evaluación

    /// <summary>Las evaluaciones del grupo en el selector. Sólo se vuelve a poblar si cambió el conjunto, y entonces se conserva lo elegido (un sondeo no devuelve el filtro a «todas»).</summary>
    private void PoblarEvaluaciones(LibroDelGrupo libro)
    {
        var firma = string.Join("|", libro.Asignaciones.Select(a => $"{a.Id}:{a.Titulo}"));
        if (firma == _firmaDeEvaluaciones) return;
        _firmaDeEvaluaciones = firma;
        var elegida = EvaluacionElegida;
        _evaluacionPorRotulo.Clear();
        var rotulos = new List<string>();
        foreach (var a in libro.Asignaciones)
        {
            // Dos evaluaciones con el mismo título (el mismo examen aplicado dos veces) se distinguen con su número.
            var rotulo = a.Titulo;
            for (var n = 2; _evaluacionPorRotulo.ContainsKey(rotulo); n++) rotulo = $"{a.Titulo} ({n})";
            _evaluacionPorRotulo[rotulo] = a.Id;
            rotulos.Add(rotulo);
        }
        _evaluaciones.Poblar(rotulos);
        var previo = _evaluacionPorRotulo.FirstOrDefault(p => p.Value == elegida).Key;
        _evaluaciones.Elegir(previo);
    }

    private void Repintar()
    {
        if (_libro is null) return;
        Pintar();
    }
}
