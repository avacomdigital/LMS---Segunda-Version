using Avacom.Lms.Core.Licencia;
using Avacom.Lms.Core.Search;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Busqueda;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Licencia.Ui;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Controls;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Buscar (MOD-021 · Search), la entrada del MENÚ PRINCIPAL. Busca entre los cursos, lecciones y recursos de AVACOM Biblioteca (en vivo) y las evaluaciones, estudios asignados y clases
/// del LMS (índice local), y devuelve SÓLO lo que quien consulta puede leer: lo decide el nodo en cada consulta con lo vigente (BR-088), no esta pantalla. Cada resultado abre la
/// pantalla de su módulo (<see cref="DestinosDeBusqueda"/>) después de que el nodo vuelva a comprobar el permiso (<see cref="ISearchApi.AbrirAsync"/>): no hay una pantalla paralela.
///
/// <b>La consulta.</b> Se pide al nodo al terminar de escribir (500 ms de pausa, sin una petición por pulsación), al pulsar Enter o «Buscar», al tocar una sugerencia o al cambiar un filtro.
/// Una consulta nueva cancela la anterior y lo que llega de una consulta vieja se descarta. Los resultados se piden de a 20 y «Mostrar más» trae la página siguiente.
/// <b>Los filtros</b> son los válidos para quien consulta (sus tipos, sus grupos y el árbol de la biblioteca): Tipo y Grupo a la vista y, bajo «Más filtros», Ciclo, País, Nivel, Grado y
/// Materia. Cambiarlos no borra lo escrito; «Limpiar filtros» sí lo borra todo.
/// <b>Sin teclado.</b> El equipo principal puede no tenerlo: las búsquedas recientes y las materias se tocan.
/// <b>Los estados</b> se distinguen: pantalla inicial, buscando, resultados, sin coincidencias, error (sin conexión, sin permiso, fallo del nodo), índice construyéndose o rezagado
/// (se consulta igual, con aviso) y biblioteca cerrada (la búsqueda sigue con lo del LMS). No encontrar nada nunca se presenta como no poder buscar.
/// </summary>
public partial class BuscarPage : ContentPage
{
    private const double AnchoMaximo = 1280;
    private static readonly TimeSpan Pausa = TimeSpan.FromMilliseconds(500);
    private const int Materias = 8;

    // Las cápsulas de los selectores son de 170–190 px: el «sin filtro» dice el rótulo y «(todos)», corto para que no se corte.
    private readonly FilterPicker _tipo = new() { Placeholder = "Tipo (todos)", WidthRequest = 190 };
    private readonly FilterPicker _grupo = new() { Placeholder = "Grupo (todos)", WidthRequest = 190 };
    private readonly FilterPicker _periodo = new() { Placeholder = "Ciclo (todos)", WidthRequest = 180 };
    private readonly FilterPicker _pais = new() { Placeholder = "País (todos)", WidthRequest = 180 };
    private readonly FilterPicker _nivel = new() { Placeholder = "Nivel (todos)", WidthRequest = 180 };
    private readonly FilterPicker _grado = new() { Placeholder = "Grado (todos)", WidthRequest = 180 };
    private readonly FilterPicker _materia = new() { Placeholder = "Materia (todas)", WidthRequest = 190 };
    private readonly Dictionary<FilterPicker, Dictionary<string, string>> _codigos = [];

    private CancellationTokenSource? _cts;
    private int _version;                       // cada consulta nueva (o cambio de la pantalla) la sube: lo que llega de una anterior se descarta
    private bool _iniciada, _filtrosCargados;
    private OpcionesDeFiltros? _opciones;
    private ConsultaDeBusqueda? _ultima;
    private RespuestaDeBusqueda? _respuesta;
    private readonly List<Hallazgo> _mostrados = [];
    private AvisoDeBusqueda? _avisoDelIndice, _avisoDelCatalogo, _avisoDeFiltros;
    private string? _avisoPuntual;

    private static ISearchApi Api => Sesion.Search;
    private static string Actor => BusquedaUi.Actor;

    public BuscarPage()
    {
        InitializeComponent();
        AccionesHost.Add(ExamenUi.Accion("Buscar", Ds.Rango.Primary, () => { Programar(inmediata: true, reciente: true); return Task.CompletedTask; }, 150, "buscar-buscar").Vista);
        AccionesHost.Add(ExamenUi.Accion("Limpiar", Ds.Rango.Secondary, () => { Reiniciar(); return Task.CompletedTask; }, 150, "buscar-limpiar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Menú principal", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 220, "buscar-volver").Vista);

        Buscador.CampoAutomationId = "buscar-campo";
        // Tipo y Grupo a la vista; Ciclo, País, Nivel, Grado y Materia bajo «Más filtros». Cualquier cambio vuelve a buscar con lo ya escrito.
        foreach (var filtro in new[] { _tipo, _grupo })
        {
            filtro.SelectionChanged += (_, _) => Programar(inmediata: true);
            Buscador.AgregarFiltro(filtro);
        }
        foreach (var filtro in new[] { _periodo, _pais, _nivel, _grado, _materia })
        {
            filtro.SelectionChanged += (_, _) => Programar(inmediata: true);
            Buscador.AgregarFiltro(filtro, extra: true);
        }
        Buscador.TextChanged += (_, _) => Programar(inmediata: false);
        Buscador.Completed += (_, _) => Programar(inmediata: true, reciente: true);
        Buscador.LimpiarTapped += (_, _) => Reiniciar(conservarTexto: true);
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
        try
        {
            if (!BusquedaUi.PuedeBuscar)
            {
                Buscador.IsEnabled = false;
                _avisoPuntual = "Tu rol no puede buscar. Pídele acceso a la administración.";
                RepintarAvisos();
                return;
            }
            if (!_iniciada)
            {
                _iniciada = true;
                PintarInicio(null);
            }
            await CargarFiltrosAsync();
            await ActualizarEstadoAsync();
            // Al volver de un resultado se repite la última consulta en silencio: lo retirado o lo que ya no se puede leer no debe seguir en la lista (BR-088).
            if (_ultima is not null) _ = BuscarAsync(++_version, reciente: false, silenciosa: true);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "BuscarPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _cts?.Cancel();
    }

    // ------------------------------------------------------------------------------------------ la consulta

    /// <summary>Pide la búsqueda: ya (Enter, «Buscar», una sugerencia, un filtro) o tras una pausa de escritura. La anterior se cancela.</summary>
    private void Programar(bool inmediata, bool reciente = false)
    {
        var version = ++_version;
        _cts?.Cancel();
        if (inmediata) _ = BuscarAsync(version, reciente);
        else Dispatcher.DispatchDelayed(Pausa, () => { if (version == _version) _ = BuscarAsync(version, reciente); });
    }

    private ConsultaDeBusqueda Consulta(string texto, int pagina)
    {
        string? Codigo(FilterPicker f) => f.Selected is { } nombre && _codigos.TryGetValue(f, out var mapa) && mapa.TryGetValue(nombre, out var codigo) ? codigo : null;
        var tipo = Codigo(_tipo);
        return new ConsultaDeBusqueda(texto, tipo is null ? null : [tipo], Codigo(_pais), Codigo(_nivel), Codigo(_grado), Codigo(_materia), null, Codigo(_periodo), Codigo(_grupo), pagina);
    }

    private async Task BuscarAsync(int version, bool reciente, bool silenciosa = false, bool masPaginas = false)
    {
        try
        {
            var texto = Buscador.Text.Trim();
            if (!BusquedaTexto.ConsultaValida(texto))
            {
                if (version != _version) return;
                _ultima = null;
                _respuesta = null;
                _mostrados.Clear();
                _avisoDelCatalogo = _avisoDeFiltros = null;
                _avisoPuntual = null;
                RepintarAvisos();
                PintarInicio(BusquedaTexto.PorQueNoSeBusca(texto));
                return;
            }

            var consulta = Consulta(texto, masPaginas && _respuesta is { } previa ? previa.Pagina + 1 : 1);
            var cts = new CancellationTokenSource();
            _cts = cts;
            if (!masPaginas && !silenciosa)
            {
                SugerenciasHost.IsVisible = false;
                ResumenLabel.Text = "Buscando…";
                ResumenLabel.IsVisible = true;
                if (_respuesta is null) ResultadosHost.Clear();
            }

            var respuesta = await Api.BuscarAsync(Actor, consulta, cts.Token);
            if (cts.IsCancellationRequested || version != _version) return;       // llegó tarde: ya hay una consulta más nueva

            if (respuesta is null)
            {
                _respuesta = null;
                _mostrados.Clear();
                _avisoDelCatalogo = _avisoDeFiltros = null;           // lo que se dijo de la consulta anterior ya no vale: no se pudo hacer ésta
                RepintarAvisos();
                if (BusquedaTexto.EnPausaPorLicencia(Api.UltimoError)) PintarPausaPorLicencia();
                else PintarError(BusquedaTexto.Error(Api.UltimoError, Api.UltimoMotivo));
                return;
            }
            _ultima = consulta;
            _respuesta = respuesta;
            if (!masPaginas) _mostrados.Clear();
            _mostrados.AddRange(respuesta.Resultados);
            if (reciente && respuesta.Total > 0) BusquedasRecientes.Agregar(texto);
            _avisoPuntual = null;
            _avisoDelIndice = BusquedaTexto.AvisoDelIndice(respuesta.EstadoDelIndice, respuesta.AvisoDelIndice);
            _avisoDelCatalogo = BusquedaTexto.AvisoDelCatalogo(respuesta);
            _avisoDeFiltros = string.IsNullOrWhiteSpace(respuesta.Aviso) ? null : new AvisoDeBusqueda("Un filtro no se pudo aplicar", respuesta.Aviso!, false);
            RepintarAvisos();
            PintarResultados(respuesta);
        }
        catch (OperationCanceledException) { /* una consulta más nueva sustituyó a esta */ }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "BuscarPage.Buscar", ex); }
    }

    /// <summary>«Limpiar»: vuelve a la pantalla inicial. Con <paramref name="conservarTexto"/> (el «Limpiar filtros» de la barra, que ya borró todo) sólo repinta.</summary>
    private void Reiniciar(bool conservarTexto = false)
    {
        _version++;
        _cts?.Cancel();
        if (!conservarTexto) Buscador.Limpiar();
        _ultima = null;
        _respuesta = null;
        _mostrados.Clear();
        _avisoDelCatalogo = _avisoDeFiltros = null;
        _avisoPuntual = null;
        RepintarAvisos();
        PintarInicio(null);
    }

    // ------------------------------------------------------------------------------------------ filtros y estado

    private async Task CargarFiltrosAsync()
    {
        if (_filtrosCargados) return;
        var opciones = await Api.FiltrosAsync(Actor);
        if (opciones is null)
        {
            // MOD-018 · U-3: con la búsqueda en pausa por la licencia no es «no se pudo cargar todo»: la tarjeta propia, y nada de sugerencias que no se podrían buscar.
            if (BusquedaTexto.EnPausaPorLicencia(Api.UltimoError))
            {
                _avisoPuntual = null;
                RepintarAvisos();
                PintarPausaPorLicencia();
                return;
            }
            // Sin las opciones se puede buscar igual (el texto no las necesita); se avisa y se reintenta al volver.
            var error = BusquedaTexto.Error(Api.UltimoError, Api.UltimoMotivo);
            _avisoPuntual = $"{error.Titulo}. {error.Detalle}".Trim();
            RepintarAvisos();
            return;
        }
        _opciones = opciones;
        _filtrosCargados = true;
        PoblarFiltros(opciones);
        _avisoPuntual = null;
        RepintarAvisos();
        if (_respuesta is null) PintarInicio(null);
    }

    private async Task ActualizarEstadoAsync()
    {
        var estado = await Api.EstadoAsync(Actor);
        if (estado is null) return;
        _avisoDelIndice = BusquedaTexto.AvisoDelIndice(estado.EstadoDelIndice, estado.AvisoDelIndice);
        RepintarAvisos();
    }

    private void PoblarFiltros(OpcionesDeFiltros o)
    {
        Poblar(_tipo, o.Tipos.Select(t => (BusquedaTexto.RotuloDeTipoPlural(t.Valor), t.Valor)));
        Poblar(_grupo, o.Grupos.Select(g => (g.Nombre, g.Id)));
        Poblar(_periodo, o.Periodos.Select(p => (p, p)));
        Poblar(_pais, (o.Paises ?? []).Select(n => (n.Nombre, n.Codigo)));
        Poblar(_nivel, (o.Niveles ?? []).Select(n => (n.Nombre, n.Codigo)));
        Poblar(_grado, (o.Grados ?? []).Select(n => (n.Nombre, n.Codigo)));
        Poblar(_materia, (o.Materias ?? []).Select(n => (n.Nombre, n.Codigo)));
    }

    /// <summary>
    /// Carga un selector con (nombre, código) y conserva lo elegido por CÓDIGO. Si dos opciones se llaman igual («Matemáticas» en dos grados) se les añade el código para poder
    /// distinguirlas al tocar.
    /// </summary>
    private void Poblar(FilterPicker selector, IEnumerable<(string Nombre, string Codigo)> opciones)
    {
        var anterior = selector.Selected is { } n && _codigos.TryGetValue(selector, out var viejo) && viejo.TryGetValue(n, out var c) ? c : null;
        var lista = opciones.Where(o => !string.IsNullOrWhiteSpace(o.Codigo)).DistinctBy(o => o.Codigo).ToList();
        var repetidos = lista.GroupBy(o => o.Nombre).Where(g => g.Count() > 1).Select(g => g.Key).ToHashSet();
        var mapa = new Dictionary<string, string>();
        foreach (var (nombre, codigo) in lista)
            mapa[repetidos.Contains(nombre) ? $"{nombre} ({codigo})" : nombre] = codigo;
        _codigos[selector] = mapa;
        selector.Poblar(mapa.Keys);
        selector.Elegir(anterior is null ? null : mapa.FirstOrDefault(p => p.Value == anterior).Key);
    }

    private bool HayFiltros => new[] { _tipo, _grupo, _periodo, _pais, _nivel, _grado, _materia }.Any(f => f.Selected is not null);

    // ------------------------------------------------------------------------------------------ avisos

    private void RepintarAvisos()
    {
        AvisoHost.Clear();
        if (!string.IsNullOrWhiteSpace(_avisoPuntual)) AvisoHost.Add(ExamenUi.Aviso("No se pudo cargar todo", _avisoPuntual, Tono.Ambar));
        foreach (var aviso in new[] { _avisoDelIndice, _avisoDelCatalogo, _avisoDeFiltros })
            if (aviso is not null) AvisoHost.Add(ExamenUi.Aviso(aviso.Titulo, aviso.Detalle, aviso.Grave ? Tono.Ambar : Tono.Info));
    }

    // ------------------------------------------------------------------------------------------ pintar

    /// <summary>La pantalla inicial (sin consulta): lo que se puede buscar y, para hacerlo tocando, las búsquedas recientes y las materias.</summary>
    private void PintarInicio(string? pista)
    {
        ResumenLabel.IsVisible = false;
        ResultadosHost.Clear();
        var texto = new VerticalStackLayout { Spacing = 6 };
        texto.Add(Ds.Titulo("¿Qué quieres buscar?", 20));
        texto.Add(Ds.Secundario(string.IsNullOrWhiteSpace(pista)
            ? "Escribe el nombre de un curso, una lección, un examen, una clase o un tema. También puedes tocar una búsqueda reciente o una materia."
            : pista!, 15));
        ResultadosHost.Add(Ds.Tarjeta(texto, Ds.RadioTarjeta, new Thickness(24, 18), Colors.White));
        PintarSugerencias();
    }

    private void PintarSugerencias()
    {
        SugerenciasHost.Clear();
        SugerenciasHost.IsVisible = true;
        var recientes = BusquedasRecientes.Leer();
        if (recientes.Count > 0)
        {
            SugerenciasHost.Add(Ds.Secundario("Búsquedas recientes", 14));
            var fila = ExamenUi.Fila();
            foreach (var texto in recientes) fila.Add(Sugerencia(texto, "reciente"));
            SugerenciasHost.Add(fila);
        }
        var materias = (_opciones?.Materias ?? []).Select(m => m.Nombre).Where(n => BusquedaTexto.ConsultaValida(n)).Distinct().Take(Materias).ToList();
        if (materias.Count > 0)
        {
            SugerenciasHost.Add(Ds.Secundario("Materias", 14));
            var fila = ExamenUi.Fila();
            foreach (var materia in materias) fila.Add(Sugerencia(materia, "materia"));
            SugerenciasHost.Add(fila);
        }
    }

    private View Sugerencia(string texto, string clase)
    {
        var id = $"buscar-sugerencia-{clase}-{new string(texto.Where(char.IsLetterOrDigit).ToArray())}";
        return ExamenUi.Accion(texto, Ds.Rango.Secondary, () =>
        {
            Buscador.Text = texto;                      // dispara TextChanged (una consulta con pausa) …
            Programar(inmediata: true, reciente: true); // … y ésta, inmediata, la sustituye
            return Task.CompletedTask;
        }, null, id, 48).Vista;
    }

    private void PintarResultados(RespuestaDeBusqueda r)
    {
        SugerenciasHost.IsVisible = false;
        ResultadosHost.Clear();
        ResumenLabel.Text = BusquedaTexto.Resumen(r);
        ResumenLabel.IsVisible = true;
        if (r.Total == 0)
        {
            ResultadosHost.Add(ExamenUi.Aviso("Sin coincidencias", HayFiltros
                ? "Prueba con otras palabras o quita algún filtro para ver más."
                : "Prueba con otras palabras, con menos letras o con el nombre de una materia.", Tono.Info));
            if (HayFiltros)
            {
                var limpiar = ExamenUi.Accion("Limpiar filtros", Ds.Rango.Secondary, () => { LimpiarFiltros(); return Task.CompletedTask; }, 220, "buscar-sin-filtros", margen: false);
                limpiar.Vista.HorizontalOptions = LayoutOptions.Start;
                ResultadosHost.Add(limpiar.Vista);
            }
            return;
        }
        if (BusquedaTexto.AclaracionDeCoincidencia(r) is { } aclaracion) ResultadosHost.Add(Ds.Secundario(aclaracion, 14));
        foreach (var h in _mostrados) ResultadosHost.Add(Tarjeta(h));
        if (r.HayMas)
        {
            var mas = ExamenUi.Accion($"Mostrar más ({_mostrados.Count} de {r.Total}{(r.TotalExacto ? string.Empty : "+")})", Ds.Rango.Secondary,
                () => BuscarAsync(_version, reciente: false, masPaginas: true), 300, "buscar-mas", margen: false);
            mas.Vista.HorizontalOptions = LayoutOptions.Start;
            ResultadosHost.Add(mas.Vista);
        }
    }

    /// <summary>Quita los filtros y deja el texto: «sin resultados con estos filtros» no debe obligar a volver a escribir.</summary>
    private void LimpiarFiltros()
    {
        foreach (var filtro in new[] { _tipo, _grupo, _periodo, _pais, _nivel, _grado, _materia }) filtro.Reset();
        Programar(inmediata: true);
    }

    /// <summary>No se pudo buscar (distinto de «sin coincidencias»): se dice qué pasó y se ofrece reintentar. Lo que ya se veía se conserva si el fallo fue al paginar.</summary>
    private void PintarError(AvisoDeBusqueda aviso)
    {
        SugerenciasHost.IsVisible = false;
        ResumenLabel.IsVisible = false;
        ResultadosHost.Clear();
        ResultadosHost.Add(ExamenUi.Aviso(aviso.Titulo, aviso.Detalle, aviso.Grave ? Tono.Ambar : Tono.Info));
        var reintentar = ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, () => { Programar(inmediata: true); return Task.CompletedTask; }, 200, "buscar-reintentar", margen: false);
        reintentar.Vista.HorizontalOptions = LayoutOptions.Start;
        ResultadosHost.Add(reintentar.Vista);
    }

    /// <summary>
    /// MOD-018 · U-3: «Buscar» en pausa por la licencia (402 <c>no_disponible_por_licencia</c>) no es un fallo de carga: la misma tarjeta que Reportes («No disponible con la licencia de
    /// este equipo», el texto común de la licencia), con «Ver la licencia» para quien la administra y «Reintentar» para cuando se haya renovado. Sin sugerencias: no se podrían buscar.
    /// </summary>
    private void PintarPausaPorLicencia()
    {
        SugerenciasHost.IsVisible = false;
        ResumenLabel.IsVisible = false;
        ResultadosHost.Clear();
        var aviso = BusquedaTexto.Error(Api.UltimoError, Api.UltimoMotivo);
        var acciones = new List<View>();
        if (ReglasDeLicencia.VeLaLicencia(Sesion.Usuario))
            acciones.Add(ExamenUi.Accion("Ver la licencia", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(BuscarPage), "VerLicencia", () => Shell.Current.GoToAsync("licencia")),
                200, "buscar-licencia-ver", LicenciaUi.AltoTactil, margen: false).Vista);
        acciones.Add(ExamenUi.Accion("Reintentar", Ds.Rango.Quiet, ReportesUi.Seguro(nameof(BuscarPage), "ReintentarConLicencia", async () =>
        {
            await CargarFiltrosAsync();                                   // si la licencia ya se renovó, vuelven las opciones y la pantalla inicial
            if (_filtrosCargados) Programar(inmediata: true);
        }), 170, "buscar-reintentar", LicenciaUi.AltoTactil, margen: false).Vista);
        ResultadosHost.Add(ReportesUi.Estado(aviso.Titulo, aviso.Detalle, [.. acciones]));
    }

    private static Tono TonoDelEstado(Hallazgo h) => (h.Tipo, h.Estado) switch
    {
        (TiposDeBusqueda.Clase, "abierta" or "suspendida") => Tono.Exito,
        (TiposDeBusqueda.Evaluacion, "activa" or "activa_fuera_de_plazo") => Tono.Info,
        (TiposDeBusqueda.Evaluacion or TiposDeBusqueda.Estudio or TiposDeBusqueda.Clase, "cerrada") => Tono.Gris,
        (TiposDeBusqueda.Evaluacion, "programada") or (TiposDeBusqueda.Clase, "planificada") => Tono.Violeta,
        _ => Tono.Neutro,
    };

    /// <summary>El identificador de un resultado para UI Automation: un recurso o una lección de la biblioteca sólo es único dentro de su curso.</summary>
    private static string IdDe(Hallazgo h) => TiposDeBusqueda.EsDelCatalogo(h.Tipo) && h.Tipo != TiposDeBusqueda.Curso ? $"{h.Tipo}-{h.Destino.CursoRef}-{h.EntidadId}" : $"{h.Tipo}-{h.EntidadId}";

    private View Tarjeta(Hallazgo h)
    {
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = h.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
        var pastillas = ExamenUi.Fila();
        pastillas.Add(ExamenUi.PildoraEnFila(BusquedaTexto.RotuloCompleto(h), Tono.Neutro, 13));
        if (BusquedaTexto.Estado(h.Tipo, h.Estado) is { Length: > 0 } estado) pastillas.Add(ExamenUi.PildoraEnFila(estado, TonoDelEstado(h), 13));
        textos.Add(pastillas);
        if (BusquedaTexto.Contexto(h) is { Length: > 0 } contexto) textos.Add(Ds.Secundario(contexto, 14));
        if (!string.IsNullOrWhiteSpace(h.Fragmento)) textos.Add(BusquedaUi.Fragmento(h.Fragmento, h.Resaltados));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16 };
        fila.Add(BusquedaUi.Icono(h.Tipo), 0, 0);
        fila.Add(textos, 1, 0);
        var abrir = ExamenUi.Accion("Abrir", Ds.Rango.Secondary, () => AbrirAsync(h), 150, $"buscar-abrir-{IdDe(h)}", 56, margen: false);
        abrir.Vista.VerticalOptions = LayoutOptions.Center;
        fila.Add(abrir.Vista, 2, 0);
        return new Border
        {
            BackgroundColor = Color.FromArgb("#F6F7F9"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(16, 12),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = fila, AutomationId = $"buscar-resultado-{IdDe(h)}",
        };
    }

    // ------------------------------------------------------------------------------------------ abrir

    /// <summary>BR-088 al abrir: el nodo vuelve a comprobar el permiso y la vigencia del recurso original, y sólo entonces se navega a la pantalla de su módulo.</summary>
    private async Task AbrirAsync(Hallazgo h)
    {
        try
        {
            var apertura = await Api.AbrirAsync(Actor, h.Destino);
            if (apertura is null)
            {
                var aviso = BusquedaTexto.Error(Api.UltimoError, Api.UltimoMotivo);
                _avisoPuntual = $"{aviso.Titulo}. {aviso.Detalle}".Trim();
                RepintarAvisos();
                // Ya no se puede abrir: la lista estaba vieja. Se vuelve a pedir para que lo retirado desaparezca.
                if (Api.UltimoError?.Codigo is "no_disponible") _ = BuscarAsync(++_version, reciente: false, silenciosa: true);
                return;
            }
            var ruta = DestinosDeBusqueda.Ruta(apertura.Destino ?? h.Destino, h.Estado, h.Titulo);
            if (ruta is null)
            {
                _avisoPuntual = "No se sabe cómo abrir ese resultado.";
                RepintarAvisos();
                return;
            }
            if (BusquedaTexto.ConsultaValida(Buscador.Text)) BusquedasRecientes.Agregar(Buscador.Text);
            _avisoPuntual = null;
            RepintarAvisos();
            await Shell.Current.GoToAsync(ruta);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "BuscarPage.Abrir", ex); }
    }
}
