using System.Text.Json;
using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Los resultados de un examen (MOD-010): una tabla con el estado de cada alumno, su porcentaje, si aprobó, si entregó fuera de plazo y cuántos avisos tuvo su
/// intento. Con menos de tres entregas calificadas no se calcula un promedio (CMP-043: un promedio de uno o dos alumnos identifica a una persona). Mientras algo
/// falte por revisar, el resultado se marca como provisional. Tocar un alumno abre su expediente.
/// </summary>
[QueryProperty(nameof(AsignacionId), "asignacion")]
public partial class ExamenResultadosPage : ContentPage
{
    public string AsignacionId { get; set; } = string.Empty;

    private bool _visible, _cargando;
    private string _firma = string.Empty;
    private IDispatcherTimer? _sondeo;

    private static string Actor => Sesion.ProfesorId;

    public ExamenResultadosPage()
    {
        InitializeComponent();
        AccionesHost.Add(ExamenUi.Accion("Actualizar", Ds.Rango.Secondary, () => CargarAsync(forzar: true), 170, "resultados-actualizar").Vista);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver al panel", Ds.Rango.Quiet, () => Shell.Current.GoToAsync(".."), 220, "resultados-volver").Vista);
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
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenResultadosPage.OnAppearing", ex); }
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
        var ancho = Math.Max(560, Math.Min(1280, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = ContenidoHost.WidthRequest = ancho;
    }

    private async void OnSondeo(object? sender, EventArgs e)
    {
        try { await CargarAsync(forzar: false); }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ExamenResultadosPage.OnSondeo", ex); }
    }

    private async Task CargarAsync(bool forzar)
    {
        if (string.IsNullOrWhiteSpace(AsignacionId) || _cargando) return;
        _cargando = true;
        try
        {
            var api = Sesion.Evaluacion;
            var resultados = await api.ResultadosAsync(Actor, AsignacionId);
            if (!_visible) return;
            if (resultados is null)
            {
                if (_firma.Length > 0) return;   // un tropiezo del sondeo no borra lo que ya se ve
                TituloLabel.Text = "No se pudieron leer los resultados";
                ContenidoHost.Clear();
                ContenidoHost.Add(ExamenUi.Tarjeta(Ds.Secundario(ExamenTexto.Error(api.UltimoError, api.UltimoMotivo), 16)));
                return;
            }
            var firma = JsonSerializer.Serialize(resultados);
            if (!forzar && firma == _firma) return;
            _firma = firma;
            Pintar(resultados);
        }
        finally { _cargando = false; }
    }

    // ----------------------------------------------------------------------------------------------- pintar

    private void Pintar(ResultadosDeExamen r)
    {
        var y = Desplazable.ScrollY;
        TituloLabel.Text = string.IsNullOrWhiteSpace(r.Titulo) ? "Examen" : r.Titulo;
        SubtituloLabel.Text = r.AprobacionPct is { } aprueba ? $"Se aprueba con {ExamenTexto.Porcentaje(aprueba)}" : "Este examen no tiene una nota para aprobar";
        ContenidoHost.Clear();
        ContenidoHost.Add(Resumen(r));
        ContenidoHost.Add(Tabla(r));
        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    private static View Resumen(ResultadosDeExamen r)
    {
        var calificados = r.Filas.Count(f => f.Definitivo);
        var entregaron = r.Filas.Count(f => f.Estado is EstadosIntento.Entregado or EstadosIntento.EnRevision or EstadosIntento.Calificado);
        var aprobaron = r.Filas.Count(f => f.Aprobado == true);
        var porRevisar = r.Filas.Count(f => f.RequiereRevision);

        var izquierda = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        if (r.DatosSuficientes && r.PromedioPorcentaje is { } promedio)
        {
            izquierda.Add(new Label { Text = ExamenTexto.Porcentaje(promedio), FontFamily = Ds.FuenteMedia, FontSize = 40, TextColor = Ds.Tinta });
            izquierda.Add(Ds.Secundario($"Promedio de {ExamenTexto.Plural(calificados, "alumno calificado", "alumnos calificados")}", 15));
        }
        else
        {
            // CMP-043: con menos de tres entregas no se calcula un promedio.
            izquierda.Add(new Label { Text = "Con menos de 3 entregas no se calcula un promedio", FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap });
            izquierda.Add(Ds.Secundario("Un promedio de uno o dos alumnos dejaría ver a cada persona; por eso se espera a tener tres.", 14));
        }

        var derecha = new HorizontalStackLayout { Spacing = 30, VerticalOptions = LayoutOptions.Center };
        derecha.Add(ExamenUi.Total(entregaron, "entregaron", ExamenUi.TintaExito));
        derecha.Add(ExamenUi.Total(calificados, "calificados", Ds.Tinta));
        derecha.Add(ExamenUi.Total(aprobaron, "aprobaron", ExamenUi.TintaExito));
        if (porRevisar > 0) derecha.Add(ExamenUi.Total(porRevisar, "por revisar", ExamenUi.TintaVioleta));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 30 };
        fila.Add(izquierda, 0, 0);
        fila.Add(derecha, 1, 0);

        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(fila);
        pila.Add(Ds.Secundario(r.LiberadosEn is { } lib
            ? $"Resultados liberados a los alumnos a las {ExamenTexto.Hora(lib)}."
            : "Los alumnos todavía no ven estos resultados: los liberas tú desde el panel.", 14));
        if (porRevisar > 0 || r.Filas.Any(f => !f.Definitivo && f.Porcentaje is not null))
            pila.Add(Ds.Secundario("Lo marcado como provisional todavía tiene respuestas por revisar.", 14));
        return ExamenUi.Tarjeta(pila);
    }

    private static Grid Rejilla() => new()
    {
        ColumnDefinitions =
        [
            new ColumnDefinition(new GridLength(2.4, GridUnitType.Star)), new ColumnDefinition(new GridLength(230)), new ColumnDefinition(new GridLength(170)),
            new ColumnDefinition(new GridLength(130)), new ColumnDefinition(new GridLength(140)), new ColumnDefinition(new GridLength(100)), new ColumnDefinition(new GridLength(24)),
        ],
        ColumnSpacing = 16,
    };

    private View Tabla(ResultadosDeExamen r)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Alumno por alumno"));
        if (r.Filas.Count == 0)
        {
            pila.Add(Ds.Secundario("Este examen todavía no tiene alumnos.", 15));
            return ExamenUi.Tarjeta(pila);
        }
        var encabezado = Rejilla();
        encabezado.Margin = new Thickness(4, 4, 4, 0);
        string[] titulos = ["ALUMNO", "ESTADO", "RESULTADO", "¿APROBÓ?", "FUERA DE PLAZO", "AVISOS"];
        for (var i = 0; i < titulos.Length; i++) encabezado.Add(EstudioUi.Eyebrow(titulos[i]), i, 0);
        pila.Add(encabezado);
        foreach (var fila in r.Filas) pila.Add(Fila(fila));
        return ExamenUi.Tarjeta(pila);
    }

    private static View Fila(FilaDeResultados f)
    {
        var g = Rejilla();
        g.Add(new Label { Text = f.Rotulo, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.TailTruncation }, 0, 0);
        g.Add(ExamenUi.Pildora(ExamenTexto.EstadoIntento(f.Estado), ExamenTexto.TonoIntento(f.Estado), 13), 1, 0);

        var resultado = new VerticalStackLayout { Spacing = 0, VerticalOptions = LayoutOptions.Center };
        // Un intento anulado no cuenta: no se muestra un porcentaje que ya no vale.
        if (f.Porcentaje is { } pct && f.Estado != EstadosIntento.Anulado)
        {
            resultado.Add(new Label { Text = ExamenTexto.Porcentaje(pct), FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta });
            if (!f.Definitivo) resultado.Add(Ds.Secundario("provisional", 13));
        }
        else resultado.Add(Ds.Secundario("—", 17));
        g.Add(resultado, 2, 0);

        if (f.Aprobado is { } aprobo) g.Add(ExamenUi.Pildora(aprobo ? "Aprobó" : "No aprobó", aprobo ? Tono.Exito : Tono.Gris, 13), 3, 0);
        else g.Add(new Label { Text = "—", FontFamily = Ds.FuenteLigera, FontSize = 17, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center }, 3, 0);

        if (f.FueraDePlazo) g.Add(ExamenUi.Pildora("Fuera de plazo", Tono.Ambar, 13), 4, 0);
        g.Add(new Label
        {
            Text = f.Incidentes > 0 ? ExamenTexto.Plural(f.Incidentes, "aviso", "avisos") : "—", FontFamily = Ds.FuenteRegular, FontSize = 15,
            TextColor = Ds.TintaMedia, VerticalOptions = LayoutOptions.Center,
        }, 5, 0);

        if (f.IntentoId is { } intento)
        {
            g.Add(new Label { Text = "›", FontFamily = Ds.FuenteLigera, FontSize = 28, TextColor = Ds.TintaSuave, VerticalOptions = LayoutOptions.Center }, 6, 0);
            Ds.Tocable(g, () => Shell.Current.GoToAsync($"examen-expediente?intento={Uri.EscapeDataString(intento)}"));
            SemanticProperties.SetDescription(g, $"Expediente de {f.Rotulo}");
        }
        return new Border
        {
            BackgroundColor = Color.FromArgb("#FAFAFB"), Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, Padding = new Thickness(16, 12),
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = g,
        };
    }
}
