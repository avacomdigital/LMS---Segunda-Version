using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// «Mis resultados» (MOD-011 · Gradebook): lo que el nodo deja ver al alumno de cada evaluación. Se sondea cada 8 s mientras la pantalla está a la vista.
///
/// Las reglas las decide el NODO, esta pantalla sólo las muestra:
///   · en modo SIMPLE (preescolar y todo nivel sin configurar) no hay notas ni letras ni números: un estado (○ no iniciado · ◐ en progreso · ● completado) y, si el
///     profesor ya liberó ese resultado, los aciertos como estrellas (★ acierto · ☆ por reforzar);
///   · en modo CALIFICACIONES una nota sólo aparece cuando el profesor la PUBLICÓ, tal como la presenta la escala de su nivel (número, letra o concepto) con su nivel de
///     desempeño y su retroalimentación; antes, sólo el estado de su entrega, sin ninguna cifra, ni siquiera una parcial.
///
/// Un número que sobraba en el JSON de un alumno no se pinta aquí: no hay ningún campo de resultado interno que mostrar. Sin conexión con el aula se dice con palabras y se
/// conserva lo último que se veía. Nunca en rojo (como «Mis evaluaciones»).
/// </summary>
public sealed class ResultadosPage : ContentPage
{
    private static readonly TimeSpan Sondeo = TimeSpan.FromSeconds(8);

    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 14, Padding = new Thickness(24, 8, 24, 36), MaximumWidthRequest = 960, HorizontalOptions = LayoutOptions.Center };
    private readonly Label _quien;
    private IDispatcherTimer? _temporizador;
    private bool _cargando;
    private string? _firma;

    public ResultadosPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Ds.Lienzo;

        var volver = Ds.Boton("‹  Mis evaluaciones", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 52);
        volver.FontSize = 17;
        volver.AutomationId = "resultados-volver";
        var titulo = Ds.Titulo("Mis resultados", 28);
        titulo.VerticalOptions = LayoutOptions.Center;
        titulo.AutomationId = "resultados-titulo";
        _quien = Ds.Secundario(string.Empty, 15);
        _quien.VerticalOptions = LayoutOptions.Center;
        _quien.HorizontalTextAlignment = TextAlignment.End;
        _quien.AutomationId = "resultados-quien";

        var barra = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 14, Padding = new Thickness(14, 12, 24, 4) };
        barra.Add(volver, 0, 0);
        barra.Add(titulo, 1, 0);
        barra.Add(_quien, 2, 0);

        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)] };
        raiz.Add(barra, 0, 0);
        raiz.Add(new ScrollView { Content = _cuerpo }, 0, 1);
        Content = raiz;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _firma = null;
        try { await CargarAsync(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ResultadosPage.OnAppearing", ex); }
        _temporizador ??= Dispatcher.CreateTimer();
        _temporizador.Interval = Sondeo;
        _temporizador.Tick -= AlTic;
        _temporizador.Tick += AlTic;
        _temporizador.Start();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _temporizador?.Stop();
    }

    private async void AlTic(object? remitente, EventArgs e)
    {
        try { if (Sesion.SabeQuienEvalua) await CargarAsync(); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ResultadosPage.AlTic", ex); }
    }

    // ------------------------------------------------------------------------------------ cargar

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            if (Sesion.EsVisitante)
            {
                _quien.Text = string.Empty;
                Pintar(Mensaje("Estás como visitante", "Los resultados son de quien entra con su nombre y su PIN."), "visitante");
                return;
            }
            if (!Sesion.SabeQuienEvalua)
            {
                _quien.Text = string.Empty;
                Pintar(Mensaje("Primero dinos quién eres", "Vuelve a «Mis evaluaciones» y toca tu nombre."), "sin-persona");
                return;
            }
            _quien.Text = Sesion.AlumnoDeEvaluacionRotulo is { Length: > 0 } rotulo ? $"Resultados de {rotulo}" : string.Empty;
            var api = Sesion.Gradebook;
            var mios = await api.MisResultadosAsync(Sesion.AlumnoParaEvaluar, Sesion.Dispositivo);
            if (mios is null)
            {
                var sinRed = api.UltimoError is null or { Estado: 0 };
                if (_firma is null)
                    Pintar(sinRed ? Mensaje("Sin conexión con el aula", "Cuando tu tableta vuelva a la red del aula, aquí verás tus resultados.")
                                  : Mensaje("No pudimos ver tus resultados ahora", api.UltimoMotivo ?? "Inténtalo de nuevo en un momento."), "sin-datos");
                return;                      // un tropiezo del sondeo no borra lo que ya se ve
            }
            var firma = string.Join("|", mios.Items.Select(i => $"{i.AsignacionId}:{i.Modo}:{i.EstadoSimple}:{i.Estado}:{i.Calificacion?.PublicadaEn}:{i.Aciertos?.Simbolos.Count}"));
            if (firma == _firma) return;    // lo mismo que ya se ve: no se repinta
            Pintar(mios.Items.Count == 0
                ? Mensaje("Todavía no tienes resultados", "Cuando presentes una evaluación, aquí verás cómo vas.")
                : ConstruirLista(mios), firma);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ResultadosPage.Cargar", ex);
        }
        finally { _cargando = false; }
    }

    private void Pintar(View contenido, string firma)
    {
        _firma = firma;
        _cuerpo.Clear();
        _cuerpo.Add(contenido);
    }

    private static View Mensaje(string titulo, string detalle)
    {
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, AutomationId = "resultados-mensaje" };
        var t = Ds.Titulo(titulo, 23);
        t.HorizontalTextAlignment = TextAlignment.Center;
        var d = Ds.Secundario(detalle, 17);
        d.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(t);
        pila.Add(d);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 40));
    }

    // ------------------------------------------------------------------------------ la lista

    private static View ConstruirLista(MisResultados mios)
    {
        var pila = new VerticalStackLayout { Spacing = 14 };
        foreach (var item in mios.Items) pila.Add(Tarjeta(item));
        return pila;
    }

    private static View Tarjeta(ResultadoDelAlumno item)
    {
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        var titulo = Ds.Cuerpo(item.Titulo, 20, Ds.Tinta);
        titulo.FontFamily = Ds.FuenteMedia;
        titulo.LineBreakMode = LineBreakMode.TailTruncation;
        titulo.MaxLines = 2;
        textos.Add(titulo);
        if (!string.IsNullOrWhiteSpace(item.CursoRotulo)) textos.Add(Ds.Secundario(item.CursoRotulo!, 15));

        View marca;
        if (item.EsSimple) marca = ParteSimple(item, textos);
        else if (item.TieneNota) marca = ParteConNota(item, textos);
        else marca = ParteSinNota(item, textos);

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 18, AutomationId = $"resultado-{item.AsignacionId}" };
        fila.Add(marca, 0, 0);
        fila.Add(textos, 1, 0);
        SemanticProperties.SetDescription(fila, DescripcionAccesible(item));
        return Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(20, 16));
    }

    /// <summary>Modo simple: un símbolo grande del estado y, con el resultado liberado, los aciertos como estrellas. Ningún número.</summary>
    private static View ParteSimple(ResultadoDelAlumno item, VerticalStackLayout textos)
    {
        textos.Add(Ds.Pildora(GradebookTexto.EstadoSimple(item.EstadoSimple), item.EstadoSimple == EstadosSimples.Completado ? Ds.ExitoSuave : Ds.Lienzo, Ds.Tinta, 14));
        if (item.Aciertos is { Simbolos.Count: > 0 } aciertos)
        {
            var estrellas = new Label { Text = string.Concat(aciertos.Simbolos.Select(GradebookTexto.SimboloDeAcierto)), FontSize = 24, TextColor = Ds.Alerta, LineBreakMode = LineBreakMode.WordWrap };
            SemanticProperties.SetDescription(estrellas, "Tus aciertos, como estrellas");
            textos.Add(estrellas);
            textos.Add(Ds.Secundario("Las estrellas llenas son lo que ya sabes; las vacías, lo que puedes repasar.", 14));
        }
        else if (item.EstadoSimple == EstadosSimples.Completado)
            textos.Add(Ds.Secundario("Terminaste. Tu profesor te mostrará cómo te fue.", 15));
        return Circulo(GradebookTexto.Simbolo(item.Simbolo), Ds.ExitoSuave);
    }

    /// <summary>Con la nota publicada: lo presentado por la escala (nunca el resultado interno), su nivel de desempeño y lo que el profesor escribió.</summary>
    private static View ParteConNota(ResultadoDelAlumno item, VerticalStackLayout textos)
    {
        var nota = item.Calificacion!;
        if (nota.Desempeno?.Nivel is { Length: > 0 } nivel) textos.Add(Ds.Pildora(nivel, Ds.ExitoSuave, Ds.Tinta, 14));
        if (nota.Aprobacion?.CumpleCriterio is { } cumple)
            textos.Add(Ds.Secundario(cumple ? "Alcanzaste lo esperado." : "Todavía puedes mejorar: tu profesor te dirá cómo.", 15));
        // Con qué sistema se leyó la nota (el de su país o institución, tal como se publicó) y desde dónde se aprueba: así «4,0» o «NT» significan algo.
        if (nota.Escala is { } sistema && !string.IsNullOrWhiteSpace(sistema.Nombre))
        {
            var lectura = GradebookTexto.ResumenDelSistema(sistema);
            var bloqueSistema = new VerticalStackLayout { Spacing = 0, Margin = new Thickness(0, 6, 0, 0), AutomationId = $"resultado-sistema-{item.AsignacionId}" };
            bloqueSistema.Add(Ds.Secundario($"Sistema de calificación: {GradebookTexto.Sistema(sistema)}", 13));
            if (lectura.Length > 0) bloqueSistema.Add(Ds.Secundario(lectura, 13));
            textos.Add(bloqueSistema);
        }
        if (nota.Retroalimentacion is { Count: > 0 } retro)
        {
            foreach (var (clave, rotulo) in new[] { ("fortalezas", "Lo que haces bien"), ("dificultades", "Lo que te cuesta"), ("oportunidades", "Para mejorar"), ("comentario", "Tu profesor dice") })
                if (retro.TryGetValue(clave, out var texto) && !string.IsNullOrWhiteSpace(texto))
                {
                    var bloque = new VerticalStackLayout { Spacing = 0, Margin = new Thickness(0, 6, 0, 0) };
                    bloque.Add(Ds.Secundario(rotulo, 13));
                    bloque.Add(Ds.Cuerpo(texto, 16, Ds.Tinta));
                    textos.Add(bloque);
                }
        }
        var presentada = GradebookTexto.Valor(nota.Presentada);
        return Circulo(presentada, Ds.ExitoSuave, grande: presentada.Length <= 3);
    }

    /// <summary>Sin nota publicada: sólo en qué va la entrega, con palabras. Nunca una cifra, ni siquiera una parcial.</summary>
    private static View ParteSinNota(ResultadoDelAlumno item, VerticalStackLayout textos)
    {
        textos.Add(Ds.Secundario(GradebookTexto.EstadoDeEntrega(item.Estado), 16));
        return Circulo(GradebookTexto.Simbolo(item.Simbolo), Ds.Lienzo);
    }

    private static Border Circulo(string texto, Color fondo, bool grande = true) => new()
    {
        WidthRequest = 76, HeightRequest = 76, BackgroundColor = fondo, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = 38 }, VerticalOptions = LayoutOptions.Center,
        Content = new Label { Text = texto, FontFamily = Ds.FuenteMedia, FontSize = grande ? 32 : 22, TextColor = Ds.Tinta, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
    };

    private static string DescripcionAccesible(ResultadoDelAlumno item) =>
        item.EsSimple ? $"{item.Titulo}. {GradebookTexto.EstadoSimple(item.EstadoSimple)}."
        : item.TieneNota ? $"{item.Titulo}. Resultado publicado: {(item.Calificacion!.Presentada?.Etiqueta ?? string.Empty)}. {item.Calificacion.Desempeno?.Nivel}"
        : $"{item.Titulo}. {GradebookTexto.EstadoDeEntrega(item.Estado)}.";
}
