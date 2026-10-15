using System.Text.Json;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// La bandeja de revisión docente (MOD-011 · FUN-120): los intentos entregados con respuestas por puntuar («pendiente») y las calificaciones reabiertas para recalificar
/// («reabierta»), los más antiguos primero. Cada renglón dice quién, qué evaluación, de qué grupo, cuántas respuestas faltan y la cifra provisional si la hay (que NO es la
/// calificación). Se filtra por grupo con fichas; tocar un renglón abre <c>revision-docente</c>. Vacía, dice «No hay nada por revisar». Se lee de nuevo sola cada 8 s con firma, y si el
/// nodo no responde se conserva lo último que se veía con un banner.
///
/// Se abre desde el libro con el grupo (y, a veces, la evaluación) ya elegidos: <c>calificaciones-revision?grupo=&amp;asignacion=</c>; sin parámetros muestra todos los grupos del profesor.
/// </summary>
[QueryProperty(nameof(GrupoId), "grupo")]
[QueryProperty(nameof(AsignacionId), "asignacion")]
public partial class RevisionBandejaPage : ContentPage
{
    private const double AnchoMaximo = 1280;

    /// <summary>El aviso que deja la pantalla de revisión al confirmar («Calificación registrada»): se muestra aquí al volver y se consume.</summary>
    internal static (string Titulo, string? Detalle)? AvisoAlVolver;

    public string GrupoId { get; set; } = string.Empty;
    public string AsignacionId { get; set; } = string.Empty;

    private readonly AvisoTemporal _aviso;
    private bool _visible, _cargando;
    private string _firma = string.Empty;
    private IDispatcherTimer? _sondeo;
    private BandejaDeRevision? _bandeja;
    private string? _grupoElegido;
    private string? _asignacionFiltrada;
    private bool _filtroInicial;
    private long _ultimaLectura;

    private static IGradebookApi Api => Sesion.Gradebook;

    public RevisionBandejaPage()
    {
        InitializeComponent();
        _aviso = new AvisoTemporal(ResultadoHost);
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(RevisionBandejaPage), "Actualizar", () => CargarAsync(forzar: true)), 170, "bandeja-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 150, "bandeja-volver").Vista);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!_filtroInicial)
            {
                // El filtro que trae el libro se toma una sola vez: lo que la persona elija después manda.
                _filtroInicial = true;
                _grupoElegido = string.IsNullOrWhiteSpace(GrupoId) ? null : GrupoId;
                _asignacionFiltrada = string.IsNullOrWhiteSpace(AsignacionId) ? null : AsignacionId;
            }
            if (AvisoAlVolver is { } pendiente)
            {
                AvisoAlVolver = null;
                _aviso.Mostrar(pendiente.Titulo, pendiente.Detalle, Tono.Exito);
            }
            if (!CalificacionesUi.PuedeLeer)
            {
                // TST-069: el rol técnico no accede a datos académicos; se dice sin llamar al nodo.
                SubtituloLabel.Text = string.Empty;
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.SinAcceso("Este rol no accede a datos académicos", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (!CalificacionesUi.PuedeCalificar)
            {
                SubtituloLabel.Text = string.Empty;
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.SinAcceso("La revisión es del profesorado", "Revisar y calificar respuestas lo hace el profesor de cada grupo. La administración configura las escalas y los reportes sólo leen."));
                return;
            }
            if (_bandeja is null)
            {
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.Estado("Leyendo la bandeja de revisión…", "Un momento."));
            }
            await CargarAsync(forzar: true);
            if (!_visible) return;
            _sondeo ??= Dispatcher.CreateTimer();
            _sondeo.Interval = TimeSpan.FromSeconds(8);
            _sondeo.Tick -= OnSondeo;
            _sondeo.Tick += OnSondeo;
            _sondeo.Start();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "RevisionBandejaPage.OnAppearing", ex); }
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
        Cabecera.WidthRequest = AvisoHost.WidthRequest = ContenidoHost.WidthRequest = ancho;
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try { await CargarAsync(forzar: false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "RevisionBandejaPage.OnSondeo", ex); }
    }

    // ---------------------------------------------------------------------------------------------- leer

    private async Task CargarAsync(bool forzar)
    {
        if (_cargando || !_visible || !CalificacionesUi.PuedeCalificar) return;
        _cargando = true;
        try
        {
            var api = Api;
            // Siempre se piden todos los grupos del profesor: el filtro por grupo es local, así las fichas ofrecen lo que de verdad hay.
            var bandeja = await api.BandejaAsync(CalificacionesUi.Actor);
            if (!_visible) return;
            if (bandeja is null)
            {
                if (_bandeja is not null)
                {
                    // Un tropiezo no borra lo que ya se ve: se conserva la última bandeja y se avisa.
                    ConexionHost.Clear();
                    ConexionHost.Add(CalificacionesUi.SinConexion(api)
                        ? ExamenUi.Aviso("Sin conexión con el nodo", $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}. Se vuelve a intentar solo.", Tono.Ambar)
                        : ExamenUi.Aviso("No se pudo actualizar la bandeja", CalificacionesUi.Error(api), Tono.Ambar));
                    return;
                }
                SubtituloLabel.Text = string.Empty;
                ContenidoHost.Clear();
                ContenidoHost.Add(CalificacionesUi.Estado("No se pudo leer la bandeja", CalificacionesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(RevisionBandejaPage), "Reintentar", () => CargarAsync(forzar: true)), 170, "bandeja-reintentar", margen: false).Vista));
                return;
            }
            ConexionHost.Clear();
            _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            var firma = JsonSerializer.Serialize(bandeja with { ServidorEn = 0 }) + $"|{_grupoElegido}|{_asignacionFiltrada}";
            _bandeja = bandeja;
            if (!forzar && firma == _firma) return;
            _firma = firma;
            Pintar();
        }
        finally { _cargando = false; }
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Pintar()
    {
        if (_bandeja is not { } bandeja) return;
        var y = Desplazable.ScrollY;
        ContenidoHost.Clear();

        var grupos = OrdenDeBandeja.Grupos(bandeja.Items);
        // Un grupo elegido que ya no tiene nada por revisar deja de existir como ficha: se vuelve a «todos» en lugar de enseñar una bandeja vacía sin explicación.
        if (_grupoElegido is not null && grupos.All(g => g.Id != _grupoElegido)) _grupoElegido = null;
        var visibles = OrdenDeBandeja.Ordenar(OrdenDeBandeja.Filtrar(bandeja.Items, _grupoElegido, _asignacionFiltrada));

        SubtituloLabel.Text = bandeja.Items.Count == 0
            ? "Todo al día"
            : $"{(bandeja.Pendientes == 1 ? "1 intento pendiente" : $"{bandeja.Pendientes} intentos pendientes")} · {(bandeja.Reabiertas == 1 ? "1 reabierta" : $"{bandeja.Reabiertas} reabiertas")}";

        if (grupos.Count > 1 || _asignacionFiltrada is not null) ContenidoHost.Add(Filtros(grupos, bandeja.Items.Count));

        if (visibles.Count == 0)
        {
            ContenidoHost.Add(CalificacionesUi.Estado("No hay nada por revisar",
                bandeja.Items.Count == 0
                    ? "Cuando un estudiante entregue respuestas abiertas, un dibujo o una entrega, o reabras una calificación para recalificar, aparecerá aquí."
                    : "Con este filtro no hay nada. Quítalo para ver el resto de la bandeja."));
        }
        else
        {
            var pila = new VerticalStackLayout { Spacing = 8 };
            pila.Add(ExamenUi.Seccion(visibles.Count == 1 ? "1 esperando tu revisión" : $"{visibles.Count} esperando tu revisión"));
            pila.Add(Ds.Secundario("Lo más antiguo está arriba. Toca un renglón para revisarlo. La cifra provisional es sólo lo ya calificado: la calificación llega cuando confirmes la revisión.", 14));
            foreach (var item in visibles) pila.Add(Renglon(item));
            ContenidoHost.Add(ExamenUi.Tarjeta(pila));
        }

        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    /// <summary>El filtro por grupo: «Todos» y un grupo por ficha, con cuántos renglones tiene; y, si se llegó desde una evaluación, cómo quitar ese filtro.</summary>
    private View Filtros(IReadOnlyList<(string Id, string Rotulo, int Cantidad)> grupos, int total)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        if (grupos.Count > 1)
        {
            pila.Add(EstudioUi.Eyebrow("GRUPO"));
            var fila = EstudioUi.Envolver();
            fila.Add(EstudioUi.Chip($"Todos ({total})", _grupoElegido is null, CalificacionesUi.Seguro(nameof(RevisionBandejaPage), "FiltrarGrupo", () => ElegirGrupoAsync(null)), "bandeja-grupo-todos"));
            foreach (var (id, rotulo, cantidad) in grupos)
                fila.Add(EstudioUi.Chip($"{rotulo} ({cantidad})", id == _grupoElegido, CalificacionesUi.Seguro(nameof(RevisionBandejaPage), "FiltrarGrupo", () => ElegirGrupoAsync(id)), $"bandeja-grupo-{id}"));
            pila.Add(fila);
        }
        if (_asignacionFiltrada is not null)
        {
            pila.Add(Ds.Secundario("Se muestra sólo lo de una evaluación del libro.", 14));
            var quitar = ExamenUi.Accion("Ver todas las evaluaciones", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(RevisionBandejaPage), "QuitarEvaluacion", QuitarEvaluacionAsync), 300, "bandeja-quitar-evaluacion", margen: false);
            quitar.Vista.HorizontalOptions = LayoutOptions.Start;
            pila.Add(quitar.Vista);
        }
        return pila;
    }

    private Task ElegirGrupoAsync(string? id)
    {
        _grupoElegido = id;
        Pintar();
        return Task.CompletedTask;
    }

    private Task QuitarEvaluacionAsync()
    {
        _asignacionFiltrada = null;
        Pintar();
        return Task.CompletedTask;
    }

    private View Renglon(ItemDeBandeja i)
    {
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = i.AlumnoRotulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
        textos.Add(Ds.Secundario(string.Join(" · ", new[] { i.Titulo, i.GrupoRotulo }.Where(x => !string.IsNullOrWhiteSpace(x))), 14));
        var pastillas = ExamenUi.Fila();
        pastillas.Add(CalificacionesUi.PildoraEnFila(OrdenDeBandeja.Motivo(i), i.EsReapertura ? Matiz.Ambar : Matiz.Violeta, 13));
        pastillas.Add(CalificacionesUi.PildoraEnFila(OrdenDeBandeja.Falta(i), Matiz.Neutro, 13));
        textos.Add(pastillas);
        if (OrdenDeBandeja.CifraProvisional(i) is { } cifra) textos.Add(Ds.Secundario(cifra, 13));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(24)], ColumnSpacing = 12 };
        fila.Add(textos, 0, 0);
        fila.Add(new Label { Text = "›", FontFamily = Ds.FuenteLigera, FontSize = 28, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center }, 1, 0);
        var tarjeta = CalificacionesUi.Fila(fila);
        tarjeta.AutomationId = $"bandeja-intento-{i.IntentoId}";
        Ds.Tocable(tarjeta, () => Shell.Current.GoToAsync($"revision-docente?intento={Uri.EscapeDataString(i.IntentoId)}"));
        SemanticProperties.SetDescription(tarjeta, $"Revisar a {i.AlumnoRotulo}, {i.Titulo}. {OrdenDeBandeja.Motivo(i)}. {OrdenDeBandeja.Falta(i)}");
        return tarjeta;
    }
}
