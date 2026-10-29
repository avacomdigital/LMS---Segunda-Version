using System.Net;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// Un curso completo de AVACOM Biblioteca dentro del LMS: estructura vigente a
/// la izquierda y visor a la derecha. Lo usan OPS Master (modo docente) y Student
/// (modo estudiante) con la misma lógica.
///
/// Reglas:
///  - La estructura se pide en vivo al backend; aquí no se guarda nada del curso.
///  - En modo estudiante, abrir un material registra una apertura (el «visor del
///    contenido» del expediente) y cerrarlo registra el tiempo.
///  - Las evaluaciones se corrigen en la biblioteca a través del backend: este
///    control nunca ve una clave.
///  - Sin biblioteca no hay pantalla en blanco: se explica el motivo y se ofrece reintentar.
/// </summary>
public partial class CourseContentView : ContentView
{
    private IBibliotecaDeContenido? _biblioteca;
    private CursoDetalle? _curso;
    private ItemCurso? _itemActual;
    private long? _aperturaActual;
    private DateTimeOffset _abiertoEn;
    private IntentoIniciado? _intento;
    private int _preguntaIndice;
    private readonly Dictionary<string, (bool? acierta, string? retro, string respuesta)> _veredictos = new();
    private string? _urlPermitida;
    private bool _angosto;

    public CourseContentView() => InitializeComponent();

    public string CursoRef { get; set; } = string.Empty;
    /// <summary>Null en modo docente: no se registra progreso.</summary>
    public string? PersonaId { get; set; }
    public string? PersonaRotulo { get; set; }
    public string Dispositivo { get; set; } = "equipo";
    public bool EsDocente => string.IsNullOrWhiteSpace(PersonaId);

    public event EventHandler<CursoDetalle>? CursoCargado;
    public event EventHandler<double>? ProgresoCambiado;

    public void Configurar(IBibliotecaDeContenido biblioteca, string cursoRef, string? personaId, string? personaRotulo, string dispositivo)
    {
        _biblioteca = biblioteca;
        CursoRef = cursoRef;
        PersonaId = string.IsNullOrWhiteSpace(personaId) ? null : personaId;
        PersonaRotulo = personaRotulo;
        Dispositivo = dispositivo;
        MostrarAulaBtn.IsVisible = false;
    }

    // ------------------------------------------------------------ estructura

    public async Task CargarAsync()
    {
        if (_biblioteca is null || string.IsNullOrWhiteSpace(CursoRef)) return;
        Ocupado(true);
        var detalle = await _biblioteca.CursoAsync(CursoRef, PersonaId);
        Ocupado(false);
        if (detalle is null)
        {
            // «No se pudo comprobar» no es «no está»: se dice el motivo, no se afirma que desapareció.
            AvisoCard.IsVisible = true;
            AvisoLabel.Text = "No se pudo leer el curso desde AVACOM Biblioteca.";
            AvisoDetalle.Text = _biblioteca.UltimoMotivo ?? "Sin detalle.";
            EstadoLabel.Text = "Contenido no comprobable en este momento.";
            return;
        }
        AvisoCard.IsVisible = false;
        _curso = detalle;
        TituloLabel.Text = detalle.Titulo;
        SubtituloLabel.Text = detalle.Subtitulo;
        ProgresoBar.Progress = Math.Clamp(detalle.Progreso / 100d, 0, 1);
        ProgresoLabel.Text = $"{detalle.Progreso:0}%";
        EstadoLabel.Text = EsDocente
            ? $"{detalle.Secciones.Count} secciones · {detalle.TotalItems} materiales"
            : $"{detalle.Secciones.Count} secciones · {detalle.TotalItems} materiales · tu avance se guarda automáticamente";
        PintarSecciones(detalle);
        CursoCargado?.Invoke(this, detalle);
        ProgresoCambiado?.Invoke(this, detalle.Progreso);
    }

    private void PintarSecciones(CursoDetalle detalle)
    {
        SeccionesHost.Clear();
        var numero = 0;
        foreach (var seccion in detalle.Secciones)
        {
            numero++;
            var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(40), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            var color = Paleta[(numero - 1) % Paleta.Length];
            var chip = new Border
            {
                BackgroundColor = Color.FromArgb(color), StrokeThickness = 0, WidthRequest = 34, HeightRequest = 34,
                StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 10 },
                Content = new Label { Text = numero.ToString(), TextColor = Colors.White, FontFamily = "LexendSemiBold", HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            };
            cabecera.Add(chip, 0, 0);
            var textos = new VerticalStackLayout { Spacing = 1 };
            textos.Add(new Label { Text = seccion.Titulo, FontFamily = "LexendSemiBold", FontSize = 15, TextColor = Color.FromArgb("#1F2433"), LineBreakMode = LineBreakMode.WordWrap });
            textos.Add(new Label { Text = $"{seccion.TipoLegible} · {seccion.Codigo}", FontSize = 11, TextColor = Color.FromArgb("#4F5566") });
            cabecera.Add(textos, 1, 0);
            if (!EsDocente)
                cabecera.Add(new Label { Text = seccion.ProgresoTexto, FontFamily = "LexendSemiBold", TextColor = Color.FromArgb(color), VerticalOptions = LayoutOptions.Center }, 2, 0);

            var pila = new VerticalStackLayout { Spacing = 6 };
            pila.Add(cabecera);
            if (!EsDocente)
                pila.Add(new ProgressBar { Progress = seccion.ProgresoFraccion, ProgressColor = Color.FromArgb(color), Margin = new Thickness(0, 4, 0, 6) });
            pila.Add(new BoxView { HeightRequest = 1, Color = Color.FromArgb("#E3E6EC") });
            foreach (var item in seccion.Items)
                pila.Add(FilaDeItem(seccion, item));

            SeccionesHost.Add(new Border
            {
                Padding = 16, BackgroundColor = Colors.White, Stroke = Color.FromArgb("#E3E6EC"),
                StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 18 }, Content = pila,
            });
        }
    }

    private View FilaDeItem(SeccionCurso seccion, ItemCurso item)
    {
        var seleccionado = _itemActual?.ElementoRef == item.ElementoRef;
        var fila = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(34), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)],
            ColumnSpacing = 8, Padding = new Thickness(6, 8), Opacity = item.Visible ? 1 : 0.5,
            BackgroundColor = seleccionado ? Color.FromArgb("#FDE7E7") : Colors.Transparent,
        };
        var iconoColor = item.Completado ? "#047857" : item.Abierto ? "#0A72A6" : "#4F5566";
        fila.Add(new Label { Text = item.Completado ? "✓" : item.Icono, FontSize = 18, TextColor = Color.FromArgb(iconoColor), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center }, 0, 0);
        var textos = new VerticalStackLayout { Spacing = 0 };
        textos.Add(new Label { Text = item.Titulo, FontSize = 14, TextColor = Color.FromArgb("#1F2433"), LineBreakMode = LineBreakMode.WordWrap });
        var estado = item.EstadoTexto;
        textos.Add(new Label { Text = string.IsNullOrEmpty(estado) ? item.TipoLegible : $"{item.TipoLegible} · {estado}", FontSize = 11, TextColor = Color.FromArgb("#4F5566") });
        fila.Add(textos, 1, 0);
        fila.Add(new Label { Text = "›", FontSize = 22, TextColor = Color.FromArgb("#6A788E"), VerticalOptions = LayoutOptions.Center }, 2, 0);
        if (item.Visible)
        {
            var tap = new TapGestureRecognizer();
            tap.Tapped += async (_, _) => await AbrirItemAsync(seccion, item);
            fila.GestureRecognizers.Add(tap);
        }
        return fila;
    }

    // ----------------------------------------------------------------- visor

    public async Task AbrirItemAsync(SeccionCurso? seccion, ItemCurso item)
    {
        if (_biblioteca is null) return;
        await CerrarAperturaAsync(100);
        _itemActual = item;
        LimpiarVisor();
        VisorTitulo.Text = item.Titulo;
        VisorSubtitulo.Text = $"{item.TipoLegible}{(seccion is null ? string.Empty : " · " + seccion.Titulo)}";
        CerrarVisorBtn.IsVisible = true;
        MostrarAulaBtn.IsVisible = EsDocente;
        if (_angosto) MostrarSoloVisor(true);
        if (_curso is not null) PintarSecciones(_curso);

        var capacidades = _curso?.Capacidades ?? [];
        switch (item.Tipo)
        {
            case "imagen":
                if (!Exige("medio", capacidades)) break;
                VisorImagen.Source = new UriImageSource { Uri = _biblioteca.MedioUri(item.ElementoRef), CachingEnabled = false };
                VisorImagen.IsVisible = true;
                break;
            case "video":
            case "audio":
                if (!Exige("medio", capacidades)) break;
                MostrarHtml(HtmlReproductor(item.Tipo, _biblioteca.MedioUri(item.ElementoRef).AbsoluteUri, item.Titulo));
                break;
            case "documento":
                if (!Exige("medio", capacidades)) break;
                if (DeviceInfo.Platform == DevicePlatform.Android)
                {
                    Mensaje("Documento PDF", "En la tableta el documento se abre con el visor del sistema.", "Abrir documento",
                        async () => await Launcher.Default.OpenAsync(_biblioteca.MedioUri(item.ElementoRef)));
                    break;
                }
                MostrarUrl(_biblioteca.MedioUri(item.ElementoRef));
                break;
            case "interactivo":
                if (!Exige("medio", capacidades)) break;
                MostrarUrl(_biblioteca.MedioUri(item.ElementoRef, "index.html"));
                break;
            case "leccion":
                if (!Exige("leccion", capacidades)) break;
                await MostrarLeccionAsync(item);
                break;
            case "evaluacion":
            case "actividad":
                if (!Exige("evaluacion", capacidades)) break;
                await MostrarEvaluacionAsync(seccion, item);
                break;
            default:
                Mensaje($"Tipo «{item.Tipo}»", "Este tipo de material todavía no tiene visor en el LMS. Puedes proyectarlo en la pantalla del aula desde AVACOM Biblioteca.");
                break;
        }

        // El expediente: sólo en modo estudiante, sólo si de verdad se abrió algo.
        if (!EsDocente && item.Tipo is not ("evaluacion" or "actividad"))
            await RegistrarAperturaAsync(seccion, item);
    }

    private bool Exige(string capacidad, IReadOnlyList<string> capacidades)
    {
        if (capacidades.Contains(capacidad)) return true;
        Mensaje("La biblioteca no publica esta capacidad",
            $"Para reproducir este material la biblioteca debe declarar «{capacidad}». Hoy declara: {string.Join(", ", capacidades)}. " +
            "Mientras tanto puede proyectarse en la pantalla del aula.");
        return false;
    }

    private void LimpiarVisor()
    {
        VisorVacio.IsVisible = false;
        VisorImagen.IsVisible = false;
        VisorImagen.Source = null;
        // No se «limpia» el WebView aquí: NavigateToString(blanco) seguido de Navigate(url)
        // en el mismo ciclo es una carrera, y a veces ganaba el blanco (PDF sin pintar).
        // El WebView se vacía sólo al cerrar el visor.
        VisorWeb.IsVisible = false;
        VisorLeccion.IsVisible = false;
        VisorEvaluacion.IsVisible = false;
        VisorMensaje.IsVisible = false;
        MensajeAccionBtn.IsVisible = false;
        _accionMensaje = null;
        _urlPermitida = null;
    }

    private void MostrarUrl(Uri uri)
    {
        _urlPermitida = uri.GetLeftPart(UriPartial.Authority);
        VisorWeb.Source = new UrlWebViewSource { Url = uri.AbsoluteUri };
        VisorWeb.IsVisible = true;
    }

    private void MostrarHtml(string html)
    {
        _urlPermitida = _biblioteca?.BaseUri.GetLeftPart(UriPartial.Authority);
        VisorWeb.Source = new HtmlWebViewSource { Html = html };
        VisorWeb.IsVisible = true;
    }

    private static string HtmlReproductor(string tipo, string url, string titulo)
    {
        var etiqueta = tipo == "audio" ? "audio" : "video";
        return $$"""
            <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>html,body{margin:0;height:100%;background:#111;color:#fff;font-family:Segoe UI,Arial,sans-serif;display:flex;flex-direction:column}
            .barra{padding:10px 14px;font-size:14px;opacity:.85}{{etiqueta}}{flex:1;width:100%;max-height:100%;background:#000;outline:none}</style></head>
            <body><div class="barra">{{WebUtility.HtmlEncode(titulo)}}</div>
            <{{etiqueta}} controls autoplay playsinline preload="metadata" src="{{url}}"></{{etiqueta}}></body></html>
            """;
    }

    private void Mensaje(string titulo, string detalle, string? accion = null, Func<Task>? alPulsar = null)
    {
        VisorMensaje.IsVisible = true;
        MensajeTitulo.Text = titulo;
        MensajeDetalle.Text = detalle;
        MensajeAccionBtn.IsVisible = accion is not null;
        MensajeAccionBtn.Text = accion ?? string.Empty;
        _accionMensaje = alPulsar;
    }

    private Func<Task>? _accionMensaje;
    private async void OnMensajeAccion(object? sender, EventArgs e) { if (_accionMensaje is not null) await _accionMensaje(); }

    private void OnNavigating(object? sender, WebNavigatingEventArgs e)
    {
        // El WebView sólo puede ir al host del backend del LMS: sin Internet y sin sorpresas.
        if (_urlPermitida is null || !Uri.TryCreate(e.Url, UriKind.Absolute, out var uri)) return;
        if (uri.Scheme is "about" or "data") return;
        if (!string.Equals(uri.GetLeftPart(UriPartial.Authority), _urlPermitida, StringComparison.OrdinalIgnoreCase)) e.Cancel = true;
    }

    private async void OnCerrarVisor(object? sender, EventArgs e)
    {
        await CerrarAperturaAsync(100);
        _itemActual = null;
        _intento = null;
        LimpiarVisor();
        VisorWeb.Source = new HtmlWebViewSource { Html = "<html><body></body></html>" };
        VisorVacio.IsVisible = true;
        VisorTitulo.Text = "Contenido del curso";
        VisorSubtitulo.Text = "Elige un material para verlo aquí";
        CerrarVisorBtn.IsVisible = false;
        MostrarAulaBtn.IsVisible = false;
        if (_angosto) MostrarSoloVisor(false);
        if (_curso is not null) PintarSecciones(_curso);
        await CargarAsync();   // refresca el progreso tras cerrar
    }

    private async void OnMostrarEnAula(object? sender, EventArgs e)
    {
        if (_biblioteca is null || _itemActual is null) return;
        var (ok, motivo) = await _biblioteca.MostrarEnAulaAsync(_itemActual.ElementoRef);
        await Alerta(ok ? "Proyectado en el aula" : "No se pudo proyectar",
            ok ? $"«{_itemActual.Titulo}» se está mostrando en la pantalla del aula (ventana de AVACOM Biblioteca)." : motivo ?? "Sin motivo.");
    }

    private async void OnReintentar(object? sender, EventArgs e) => await CargarAsync();

    // -------------------------------------------------------------- lección

    private async Task MostrarLeccionAsync(ItemCurso item)
    {
        if (_biblioteca is null) return;
        Ocupado(true);
        var leccion = await _biblioteca.LeccionAsync(item.ElementoRef);
        Ocupado(false);
        if (leccion is null)
        {
            Mensaje("No se pudo leer la lección", _biblioteca.UltimoMotivo ?? "Sin detalle.");
            return;
        }
        PasosHost.Clear();
        LeccionIntro.Text = $"Secuencia de la lección · {leccion.Pasos.Count} pasos. Toca un paso para abrirlo.";
        foreach (var paso in leccion.Pasos)
        {
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(44), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12, Padding = 14, BackgroundColor = Colors.White };
            fila.Add(new Border
            {
                BackgroundColor = Color.FromArgb(paso.Disponible ? "#A81D81" : "#6A788E"), StrokeThickness = 0, WidthRequest = 36, HeightRequest = 36,
                StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 18 },
                Content = new Label { Text = paso.Orden.ToString(), TextColor = Colors.White, FontFamily = "LexendSemiBold", HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
            }, 0, 0);
            var textos = new VerticalStackLayout { Spacing = 1 };
            textos.Add(new Label { Text = paso.Titulo ?? paso.ElementoRef, FontFamily = "LexendSemiBold", TextColor = Color.FromArgb("#1F2433"), LineBreakMode = LineBreakMode.WordWrap });
            textos.Add(new Label { Text = string.Join(" · ", new[] { TipoLegible(paso.Tipo), paso.Nota, paso.Disponible ? null : "no disponible en este equipo" }.Where(t => !string.IsNullOrWhiteSpace(t))), FontSize = 12, TextColor = Color.FromArgb("#4F5566") });
            fila.Add(textos, 1, 0);
            fila.Add(new Label { Text = "›", FontSize = 22, TextColor = Color.FromArgb("#6A788E"), VerticalOptions = LayoutOptions.Center }, 2, 0);
            if (paso.Disponible)
            {
                var tap = new TapGestureRecognizer();
                tap.Tapped += async (_, _) =>
                {
                    var (seccion, destino) = BuscarItem(paso.ElementoRef) ?? (null, new ItemCurso(paso.Orden, paso.Tipo ?? "documento", paso.ElementoRef, paso.Titulo ?? paso.ElementoRef, null, null, true, false, false, null, null, null));
                    await AbrirItemAsync(seccion, destino);
                };
                fila.GestureRecognizers.Add(tap);
            }
            PasosHost.Add(new Border { Padding = 0, Stroke = Color.FromArgb("#E3E6EC"), StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 14 }, Content = fila });
        }
        VisorLeccion.IsVisible = true;
    }

    private (SeccionCurso? seccion, ItemCurso item)? BuscarItem(string elementoRef)
    {
        if (_curso is null) return null;
        foreach (var s in _curso.Secciones)
            foreach (var i in s.Items)
                if (i.ElementoRef == elementoRef) return (s, i);
        return null;
    }

    private static string? TipoLegible(string? tipo) => tipo switch
    {
        null => null, "leccion" => "Lección", "video" => "Video", "audio" => "Audio", "imagen" => "Lámina",
        "documento" => "Documento", "interactivo" => "Interactivo", "actividad" => "Actividad", "evaluacion" => "Evaluación", _ => tipo,
    };

    // ----------------------------------------------------------- evaluación

    private async Task MostrarEvaluacionAsync(SeccionCurso? seccion, ItemCurso item)
    {
        if (_biblioteca is null || _curso is null) return;
        _veredictos.Clear();
        _intento = null;
        EvalResultado.IsVisible = false;
        if (EsDocente)
        {
            // El docente ve las preguntas sin abrir un intento a su nombre.
            Ocupado(true);
            var intento = await _biblioteca.IniciarIntentoAsync(new IntentoSolicitud(item.ElementoRef, "docente-vista-previa", _curso.CursoRef, seccion?.Codigo ?? string.Empty, "Vista previa docente", _curso.Titulo, Dispositivo));
            Ocupado(false);
            if (intento is null) { Mensaje("No se pudo abrir la evaluación", _biblioteca.UltimoMotivo ?? "Sin detalle."); return; }
            _intento = intento;
        }
        else
        {
            Ocupado(true);
            var intento = await _biblioteca.IniciarIntentoAsync(new IntentoSolicitud(item.ElementoRef, PersonaId!, _curso.CursoRef, seccion?.Codigo ?? string.Empty, PersonaRotulo, _curso.Titulo, Dispositivo));
            Ocupado(false);
            if (intento is null) { Mensaje("No se pudo abrir la evaluación", _biblioteca.UltimoMotivo ?? "Sin detalle."); return; }
            _intento = intento;
        }
        foreach (var p in _intento.Preguntas.Where(p => p.Respondida))
            _veredictos[p.Ref] = (p.Acierta, p.Retroalimentacion, string.Empty);
        _preguntaIndice = Math.Clamp(_intento.Preguntas.Count(p => p.Respondida), 0, Math.Max(0, _intento.Preguntas.Count - 1));
        if (_intento.Preguntas.Count == 0)
        {
            Mensaje("Evaluación sin preguntas", "La biblioteca no entregó preguntas para este elemento.");
            return;
        }
        EvalEstado.Text = _intento.PuedeCorregir ? "Corrección en la biblioteca" : "Sin corrección automática: queda pendiente";
        PintarPregunta();
        VisorEvaluacion.IsVisible = true;
    }

    private void PintarPregunta()
    {
        if (_intento is null) return;
        var pregunta = _intento.Preguntas[_preguntaIndice];
        EvalProgreso.Text = $"Pregunta {_preguntaIndice + 1} de {_intento.Preguntas.Count}";
        EvalBarra.Progress = (_preguntaIndice + 1) / (double)_intento.Preguntas.Count;
        EvalEnunciado.Text = pregunta.Enunciado;
        EvalVozBtn.IsVisible = pregunta.Voz && (_curso?.Tiene("voz") ?? false);
        EvalPista.Text = pregunta.Corregible
            ? $"Respuesta corta ({pregunta.Tipo ?? "texto"}, peso {pregunta.Peso:0.#}). Escribe y pulsa Comprobar."
            : "Pregunta abierta: la califica el docente con la rúbrica. Escribe tu respuesta y pulsa Guardar.";
        EvalComprobarBtn.Text = pregunta.Corregible ? "Comprobar" : "Guardar";
        EvalAnteriorBtn.IsVisible = _preguntaIndice > 0;
        EvalSiguienteBtn.IsVisible = _preguntaIndice < _intento.Preguntas.Count - 1;
        EvalFinalizarBtn.IsVisible = !EsDocente && _intento.Estado == "abierto";
        EvalComprobarBtn.IsEnabled = _intento.Estado == "abierto";
        EvalRespuesta.IsEnabled = _intento.Estado == "abierto";
        if (_intento.Estado == "abierto") EvalResultado.IsVisible = false;
        if (_veredictos.TryGetValue(pregunta.Ref, out var v))
        {
            EvalRespuesta.Text = v.respuesta;
            MostrarVeredicto(v.acierta, v.retro, pregunta.Corregible);
        }
        else
        {
            EvalRespuesta.Text = string.Empty;
            EvalVeredicto.Text = string.Empty;
            EvalRetro.IsVisible = false;
        }
    }

    private void MostrarVeredicto(bool? acierta, string? retro, bool corregible)
    {
        EvalVeredicto.Text = acierta switch
        {
            true => "✓ Correcto",
            false => "✗ Todavía no. Vuelve a mirarlo y prueba otra vez.",
            null => corregible ? "Guardada · pendiente de corrección" : "Guardada · la califica el docente",
        };
        EvalVeredicto.TextColor = Color.FromArgb(acierta == true ? "#047857" : acierta == false ? "#C81E24" : "#4F5566");
        EvalRetro.IsVisible = !string.IsNullOrWhiteSpace(retro);
        EvalRetro.Text = retro ?? string.Empty;
    }

    private async void OnComprobar(object? sender, EventArgs e)
    {
        if (_biblioteca is null || _intento is null) return;
        var pregunta = _intento.Preguntas[_preguntaIndice];
        var respuesta = EvalRespuesta.Text?.Trim() ?? string.Empty;
        if (respuesta.Length == 0) { EvalVeredicto.Text = "Escribe una respuesta."; EvalVeredicto.TextColor = Color.FromArgb("#C81E24"); return; }
        EvalComprobarBtn.IsEnabled = false;
        var veredicto = await _biblioteca.ResponderAsync(_intento.Id, pregunta.Ref, respuesta);
        EvalComprobarBtn.IsEnabled = true;
        if (veredicto is null)
        {
            EvalVeredicto.Text = _biblioteca.UltimoMotivo ?? "No se pudo enviar la respuesta.";
            EvalVeredicto.TextColor = Color.FromArgb("#C81E24");
            return;
        }
        _veredictos[pregunta.Ref] = (veredicto.Acierta, veredicto.Retroalimentacion, respuesta);
        MostrarVeredicto(veredicto.Acierta, veredicto.Retroalimentacion, pregunta.Corregible);
    }

    private void OnAnterior(object? sender, EventArgs e) { if (_preguntaIndice > 0) { _preguntaIndice--; PintarPregunta(); } }
    private void OnSiguiente(object? sender, EventArgs e) { if (_intento is not null && _preguntaIndice < _intento.Preguntas.Count - 1) { _preguntaIndice++; PintarPregunta(); } }

    private async void OnFinalizar(object? sender, EventArgs e)
    {
        if (_biblioteca is null || _intento is null) return;
        var sinResponder = _intento.Preguntas.Count(p => !_veredictos.ContainsKey(p.Ref));
        if (sinResponder > 0)
        {
            var seguir = await Confirmar("Preguntas sin responder", $"Te faltan {sinResponder} pregunta(s). ¿Finalizar de todos modos?");
            if (!seguir) return;
        }
        EvalFinalizarBtn.IsEnabled = false;
        var resultado = await _biblioteca.FinalizarIntentoAsync(_intento.Id);
        EvalFinalizarBtn.IsEnabled = true;
        if (resultado is null)
        {
            await Alerta("No se pudo finalizar", _biblioteca.UltimoMotivo ?? "Sin detalle.");
            return;
        }
        EvalResultado.IsVisible = true;
        EvalResultado.BackgroundColor = Color.FromArgb(resultado.Estado == "finalizado" ? "#E1F5EC" : "#FFEDDF");
        EvalResultadoTitulo.TextColor = Color.FromArgb(resultado.Estado == "finalizado" ? "#047857" : "#9A3412");
        EvalResultadoTitulo.Text = resultado.Puntaje is null ? "Registrado · pendiente de corrección" : $"Nota {resultado.Puntaje:0.#}/100";
        EvalResultadoDetalle.Text = $"{resultado.Aciertos} acierto(s) de {resultado.TotalPreguntas} pregunta(s)" +
            (resultado.Pendientes > 0 ? $" · {resultado.Pendientes} pendiente(s) de corrección del docente" : string.Empty) +
            (resultado.ProgresoCurso is null ? string.Empty : $" · progreso del curso {resultado.ProgresoCurso:0}%") +
            ". La nota queda en tu expediente del LMS.";
        EvalFinalizarBtn.IsVisible = false;
        EvalComprobarBtn.IsEnabled = false;
        EvalRespuesta.IsEnabled = false;
        _intento = _intento with { Estado = resultado.Estado };
        await VisorEvaluacion.ScrollToAsync(EvalResultado, ScrollToPosition.MakeVisible, true);
        await CargarAsync();
    }

    private void OnEscucharVoz(object? sender, EventArgs e)
    {
        if (_biblioteca is null || _intento is null) return;
        var pregunta = _intento.Preguntas[_preguntaIndice];
        var url = _biblioteca.VozUri(_intento.EvaluacionRef, pregunta.Ref).AbsoluteUri;
        Audio.Source = new HtmlWebViewSource { Html = $"<html><body><audio autoplay src=\"{url}\"></audio></body></html>" };
    }

    // ------------------------------------------------------------ expediente

    private async Task RegistrarAperturaAsync(SeccionCurso? seccion, ItemCurso item)
    {
        if (_biblioteca is null || _curso is null || EsDocente) return;
        _abiertoEn = DateTimeOffset.UtcNow;
        var apertura = await _biblioteca.RegistrarAperturaAsync(new AperturaSolicitud(
            _curso.CursoRef, PersonaId!, item.ElementoRef, seccion?.Codigo ?? string.Empty, item.Version, item.Tipo, item.Titulo,
            PersonaRotulo, _curso.Titulo, Dispositivo, "student"));
        _aperturaActual = apertura?.Id;
        if (apertura is not null)
        {
            ProgresoBar.Progress = Math.Clamp(apertura.ProgresoCurso / 100d, 0, 1);
            ProgresoLabel.Text = $"{apertura.ProgresoCurso:0}%";
            ProgresoCambiado?.Invoke(this, apertura.ProgresoCurso);
            // Se vuelve a pedir la estructura para pintar «visto» y el avance por sección.
            var detalle = await _biblioteca.CursoAsync(CursoRef, PersonaId);
            if (detalle is not null) { _curso = detalle; PintarSecciones(detalle); }
        }
    }

    private async Task CerrarAperturaAsync(int? pct)
    {
        if (_biblioteca is null || _aperturaActual is null) return;
        var id = _aperturaActual.Value;
        _aperturaActual = null;
        await _biblioteca.CerrarAperturaAsync(id, pct);
    }

    /// <summary>Lo llama la página al salir para no dejar una apertura sin cerrar.</summary>
    public Task CerrarTodoAsync() => CerrarAperturaAsync(100);

    // ---------------------------------------------------------------- layout

    private void OnSizeChanged(object? sender, EventArgs e)
    {
        var angosto = Width > 0 && Width < 860;
        if (angosto == _angosto) return;
        _angosto = angosto;
        if (!angosto)
        {
            Marco.ColumnDefinitions[0].Width = new GridLength(400);
            Marco.ColumnDefinitions[1].Width = GridLength.Star;
            PanelEstructura.IsVisible = true;
            PanelVisor.IsVisible = true;
            VolverListaBtn.IsVisible = false;
        }
        else MostrarSoloVisor(_itemActual is not null);
    }

    private void MostrarSoloVisor(bool visor)
    {
        Marco.ColumnDefinitions[0].Width = visor ? new GridLength(0) : GridLength.Star;
        Marco.ColumnDefinitions[1].Width = visor ? GridLength.Star : new GridLength(0);
        PanelEstructura.IsVisible = !visor;
        PanelVisor.IsVisible = visor;
        VolverListaBtn.IsVisible = visor;
    }

    private void OnVolverLista(object? sender, EventArgs e) => MostrarSoloVisor(false);

    private void Ocupado(bool ocupado)
    {
        Cargando.IsVisible = ocupado;
        Cargando.IsRunning = ocupado;
    }

    private static readonly string[] Paleta = ["#047857", "#C2410C", "#A81D81", "#0A72A6", "#0E7490", "#5B45D1"];

    private static Task Alerta(string titulo, string mensaje) =>
        Shell.Current?.CurrentPage?.AlertaAsync(titulo, mensaje, "Entendido") ?? Task.CompletedTask;

    private static Task<bool> Confirmar(string titulo, string mensaje) =>
        Shell.Current?.CurrentPage?.AlertaAsync(titulo, mensaje, "Finalizar", "Seguir respondiendo") ?? Task.FromResult(true);
}
