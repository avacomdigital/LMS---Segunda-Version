using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Reportes;
using Avacom.Lms.Ops.Reportes.Ui;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El esqueleto que comparten las pantallas de un reporte (MOD-013): arriba el título y las acciones (Exportar, Actualizar, volver); debajo, lo que NO se desplaza —el aviso de conexión,
/// el resultado de lo último que se hizo y la cabecera del CORTE de los datos con su estado de integración (BR-083), y a veces el encabezado de la tabla—; y el cuerpo, que sí. La hoja
/// de exportar se abre sobre todo esto. Cada pantalla pone sólo lo suyo: qué pedir al nodo y cómo pintarlo.
///
/// Reglas de todas: el nodo es la fuente de todo número y la pantalla sólo lo enseña; un fallo no borra lo que ya se veía (se conserva y un aviso lo dice); sin acceso, la pantalla lo
/// dice sin llamar al nodo (TST-069); nada exige teclado. El ancho es el de las demás pantallas de datos (hasta 1280 px, centrado), y las acciones llevan su AutomationId.
/// </summary>
public abstract class PaginaDeReporte : ContentPage, IQueryAttributable
{
    private readonly Grid _marco = new();
    private readonly ContentView _exportarHost = new();
    private bool _visible, _cargando, _recargar, _hayContenido;

    internal readonly Grid Raiz, Cabecera;
    internal readonly Label TituloLabel, SubtituloLabel;
    internal readonly HorizontalStackLayout AccionesHost = new() { Spacing = 12, VerticalOptions = LayoutOptions.Center };
    internal readonly VerticalStackLayout FijoHost = new() { Spacing = 8, HorizontalOptions = LayoutOptions.Center, WidthRequest = ReportesUi.AnchoMaximo };
    internal readonly VerticalStackLayout ConexionHost = new() { Spacing = 8 }, ResultadoHost = new() { Spacing = 8 }, CorteHost = new() { Spacing = 8 }, EncabezadoHost = new();
    internal readonly ScrollView Desplazable;
    internal readonly VerticalStackLayout Cuerpo, SelectorHost = new() { Spacing = 10 }, ContenidoHost = new() { Spacing = 14 };
    internal readonly HojaDeExportar Hoja = new();
    internal readonly HojaDeOpciones Opciones = new();
    internal readonly AvisoTemporal Aviso;

    /// <summary>Los parámetros de la ruta (los identificadores y los códigos del árbol académico), tal como los dejó la pantalla anterior.</summary>
    internal IReadOnlyDictionary<string, string> Consulta { get; private set; } = new Dictionary<string, string>();

    protected PaginaDeReporte(string etiqueta, string titulo, string subtitulo)
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Color.FromArgb("#EAF0F6");
        SizeChanged += OnPageSizeChanged;

        TituloLabel = new Label { Text = titulo, FontFamily = "LexendMedium", FontSize = 30, TextColor = Color.FromArgb("#1F2433"), LineBreakMode = LineBreakMode.WordWrap, AutomationId = "reporte-titulo" };
        SubtituloLabel = new Label { Text = subtitulo, FontFamily = "Lexend", FontSize = 15, TextColor = Color.FromArgb("#4F5566"), LineBreakMode = LineBreakMode.WordWrap, AutomationId = "reporte-subtitulo" };
        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = etiqueta, FontFamily = "Lexend", FontSize = 12, TextColor = Color.FromArgb("#4F5566"), CharacterSpacing = 2.5 });
        textos.Add(TituloLabel);
        textos.Add(SubtituloLabel);

        Cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24, HorizontalOptions = LayoutOptions.Center, WidthRequest = ReportesUi.AnchoMaximo };
        Cabecera.Add(textos, 0, 0);
        Cabecera.Add(AccionesHost, 1, 0);

        _exportarHost.IsVisible = false;
        AccionesHost.Add(_exportarHost);
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, ReportesUi.Seguro(GetType().Name, "Actualizar", () => CargarAsync(forzar: true)), 170, "reporte-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Reportes", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 170, "reporte-volver").Vista);

        FijoHost.Add(ConexionHost);
        FijoHost.Add(ResultadoHost);
        FijoHost.Add(CorteHost);
        FijoHost.Add(EncabezadoHost);
        Aviso = new AvisoTemporal(ResultadoHost);

        Cuerpo = new VerticalStackLayout { HorizontalOptions = LayoutOptions.Center, WidthRequest = ReportesUi.AnchoMaximo, Spacing = 14, Padding = new Thickness(0, 0, 0, 40) };
        Cuerpo.Add(SelectorHost);
        Cuerpo.Add(ContenidoHost);
        Desplazable = new ScrollView { Content = Cuerpo };

        Raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)], Padding = new Thickness(44, 24, 48, 16), RowSpacing = 12 };
        Raiz.Add(Cabecera, 0, 0);
        Raiz.Add(FijoHost, 0, 1);
        Raiz.Add(Desplazable, 0, 2);
        _marco.Add(Raiz);
        _marco.Add(Hoja);
        _marco.Add(Opciones);
        Content = new Avacom.Lms.Ui.Controls.MarcoDs { Contenido = _marco };   // Aula · Design System: isla de marca, fecha y hora y fondo Aurora
    }

    // ------------------------------------------------------------------------------------------------------------ lo que cada pantalla pone

    /// <summary>Pide el reporte al nodo y lo pinta (con <see cref="LeerYPintarAsync{T}"/>). <paramref name="forzar"/> es verdadero al entrar y al actualizar.</summary>
    protected abstract Task LeerAsync(bool forzar);

    /// <summary>Para la pantalla que recibe sus parámetros por la ruta.</summary>
    public void ApplyQueryAttributes(IDictionary<string, object> query) =>
        Consulta = query.Where(p => p.Value is not null).ToDictionary(p => p.Key, p => p.Value.ToString() ?? string.Empty);

    internal string? Parametro(string clave) => Consulta.TryGetValue(clave, out var v) && !string.IsNullOrWhiteSpace(v) ? v : null;

    internal NodoAcademico? NodoDeLaRuta => RutasDeReportes.NodoDe(Parametro);

    // ------------------------------------------------------------------------------------------------------------ ciclo de vida

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!ReportesUi.PuedeLeer)
            {
                // TST-069: sin acceso a datos académicos, la pantalla lo dice y no llama al nodo (el nodo igualmente lo denegaría).
                SubtituloLabel.Text = string.Empty;
                ContenidoHost.Clear();
                ContenidoHost.Add(ReportesUi.SinAcceso(ReportesUi.Rol));
                return;
            }
            ReportesUi.LimpiarTemporalesViejos();
            SelectorHost.IsVisible = SelectorHost.Children.Count > 0;          // sin fichas que mostrar, el espacio de arriba del cuerpo no se reserva
            if (!_hayContenido)
            {
                ContenidoHost.Clear();
                ContenidoHost.Add(ReportesUi.Estado(EstadosVaciosDeReportes.Cargando, "Un momento."));
            }
            await CargarAsync(forzar: true);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", $"{GetType().Name}.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
    }

    protected bool EstaVisible => _visible;

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(ReportesUi.AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = FijoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    /// <summary>
    /// Lee de nuevo. Una lectura que llega mientras otra sigue en vuelo no se pierde: si pide forzar, se repite al terminar (la persona tocó otra ficha mientras se leía la anterior).
    /// </summary>
    internal async Task CargarAsync(bool forzar)
    {
        if (!_visible || !ReportesUi.PuedeLeer) return;
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
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", $"{GetType().Name}.Cargar", ex); }
        finally { _cargando = false; }
    }

    // ------------------------------------------------------------------------------------------------------------ leer y pintar

    /// <summary>
    /// Lee algo del nodo y lo pinta. Si el nodo no contesta o lo niega: sin nada que ya se viera, una tarjeta que dice qué pasó y qué hacer (con «Reintentar»); con algo ya a la vista, se
    /// CONSERVA y un aviso lo dice. Devuelve lo leído, o null si no se pudo. <paramref name="esperado"/> reconoce lo que no es un fallo (una clase abierta, un periodo vacío) y lo dice como
    /// estado vacío.
    /// </summary>
    internal async Task<T?> LeerYPintarAsync<T>(IReportesApi api, Func<Task<T?>> leer, Action<T> pintar, string noSePudo, Func<ErrorAula?, (string Titulo, string Texto)?>? esperado = null) where T : class
    {
        var leido = await leer();
        if (!_visible) return null;
        if (leido is null)
        {
            // Hay respuestas del nodo que no son un fallo sino un «todavía no hay nada» (una clase que sigue abierta, un periodo sin clases): se dicen como estado vacío, con qué hacer.
            if (esperado?.Invoke(api.UltimoError) is { } vacio)
            {
                ConexionHost.Clear();
                CorteHost.Clear();
                EncabezadoFijo(null);
                ExportarVisible(null);
                _hayContenido = true;
                ContenidoHost.Clear();
                ContenidoHost.Add(ReportesUi.Estado(vacio.Titulo, vacio.Texto));
                return null;
            }
            var error = ReportesUi.Error(api);
            var sinConexion = ReportesUi.SinConexion(api);
            if (_hayContenido)
            {
                MostrarBanner(error, sinConexion);
                return null;
            }
            ContenidoHost.Clear();
            CorteHost.Clear();
            ExportarVisible(null);
            ContenidoHost.Add(ReportesUi.Estado(noSePudo, error,
                ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, ReportesUi.Seguro(GetType().Name, "Reintentar", () => CargarAsync(forzar: true)), 170, "reporte-reintentar", margen: false).Vista));
            MostrarBanner(sinConexion ? null : error, sinConexion);
            return null;
        }
        ConexionHost.Clear();
        _hayContenido = true;
        pintar(leido);
        return leido;
    }

    /// <summary>El aviso de que el nodo no contesta (o rechazó la lectura). Dice qué se ve: lo último que se leyó. Desaparece cuando una lectura llega.</summary>
    internal void MostrarBanner(string? detalle, bool sinConexion)
    {
        ConexionHost.Clear();
        if (sinConexion)
            ConexionHost.Add(ExamenUi.Aviso("Sin conexión con el aula", _hayContenido ? "Se muestra lo último que se leyó. Toca «Actualizar» cuando vuelva la conexión." : "Revisa que el equipo del aula esté encendido y vuelve a intentarlo.", Tono.Ambar));
        else if (!string.IsNullOrWhiteSpace(detalle))
            ConexionHost.Add(ExamenUi.Aviso("No se pudo actualizar el reporte", _hayContenido ? $"{detalle} Se muestra lo último que se leyó." : detalle, Tono.Ambar));
    }

    /// <summary>Pone el título y el subtítulo de lo que se está viendo.</summary>
    internal void Poner(string titulo, string subtitulo)
    {
        TituloLabel.Text = titulo;
        SubtituloLabel.Text = subtitulo;
    }

    /// <summary>
    /// El encabezado de la tabla principal, FIJO: queda fuera de lo que se desplaza, pegado a sus filas (el cuerpo sube lo que el espaciado de la página los separaba). Sin tabla, null.
    /// </summary>
    internal void EncabezadoFijo(View? encabezado)
    {
        EncabezadoHost.Clear();
        if (encabezado is not null) EncabezadoHost.Add(encabezado);
        Desplazable.Margin = new Thickness(0, encabezado is null ? 0 : -(Raiz.RowSpacing + Cuerpo.Spacing), 0, 0);
    }

    /// <summary>La cabecera de corte (BR-083) del reporte que se ve: sigue a la vista mientras el cuerpo se desplaza.</summary>
    internal void PonerCorte(CorteDeDatos corte, Privacidad? privacidad, IReadOnlyList<AvisoDeReporte>? avisos)
    {
        CorteHost.Clear();
        CorteHost.Add(ReportesUi.CabeceraDeCorte(corte, privacidad, avisos));
    }

    // ------------------------------------------------------------------------------------------------------------ exportar

    /// <summary>
    /// Muestra u oculta el botón «Exportar» según haya un reporte exportable y la persona pueda (lo dice el nodo: <c>filtros.puede.exportar</c>; si no se pudo saber, se ofrece y el nodo decide).
    /// </summary>
    internal async void ExportarVisible(ReporteSolicitado? reporte)
    {
        try
        {
            if (reporte is null) { _exportarHost.IsVisible = false; return; }
            var filtros = await ReportesUi.FiltrosAsync();
            if (!_visible) return;
            var puede = filtros?.Puede.Exportar ?? true;
            if (!puede) { _exportarHost.IsVisible = false; return; }
            var (_, vista) = ExamenUi.Accion("Exportar", Ds.Rango.Primary, ReportesUi.Seguro(GetType().Name, "Exportar", () => ExportarAsync(reporte)), 170, "reporte-exportar");
            _exportarHost.Content = vista;
            _exportarHost.IsVisible = true;
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", $"{GetType().Name}.ExportarVisible", ex); }
    }

    private async Task ExportarAsync(ReporteSolicitado reporte)
    {
        var flujo = new FlujoDeExportacion(ReportesUi.Api, ReportesUi.Actor, reporte, ReportesUi.CarpetaTemporal, EscrituraLentaDePrueba.Crear()) { AlFallarLaEscritura = ReportesUi.AnotarFalloDeEscritura };
        await Hoja.MostrarAsync(flujo);
        ReportesUi.OlvidarFiltros();
    }
}
