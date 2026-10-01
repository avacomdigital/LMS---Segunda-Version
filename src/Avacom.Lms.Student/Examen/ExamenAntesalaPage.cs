using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// La antesala del examen (PAN-120 · JRN-010): lo que el alumno debe ver ANTES de empezar —cuántas preguntas, cuánto tiempo, bajo qué condiciones presenta, qué se registra y
/// si esta tableta cumple lo que el examen pide—. Iniciar sin que lo haya visto es lo que el sistema nunca hace: el examen sólo se abre cuando el alumno toca «Comenzar».
///
/// Una tableta que no alcanza el nivel SÍ puede pulsar «Comenzar»: eso pide la decisión del profesor (BR-075) y el alumno no queda excluido por su aparato; la pantalla espera
/// con calma y, en cuanto el profesor admite la tableta, abre el examen sola. Si el profesor la rechaza se lo dice con una frase, sin culpar a nadie.
///
/// Con <c>reanudar=1</c> (viene de «Continuar») no hay nada que leer de nuevo: se vuelve a abrir el intento vivo y se entra al examen.
/// </summary>
[QueryProperty(nameof(AsignacionId), "asignacion")]
[QueryProperty(nameof(Reanudar), "reanudar")]
public sealed class ExamenAntesalaPage : ContentPage
{
    private static readonly TimeSpan SondeoAdmision = TimeSpan.FromSeconds(3);

    public string AsignacionId { get; set; } = string.Empty;
    public string Reanudar { get; set; } = "0";

    private readonly VerticalStackLayout _contenido = new() { Spacing = 14 };
    private SesionDeExamen? _sesion;
    private AntesalaDeExamen? _antesala;
    private IDispatcherTimer? _sondeo;
    private bool _abriendo;
    private bool _saliendo;

    public ExamenAntesalaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Ds.Lienzo;
        var tarjeta = Ds.Tarjeta(new ScrollView { Content = _contenido }, Ds.RadioTarjeta, new Thickness(30, 26));
        tarjeta.AutomationId = "antesala-tarjeta";
        var raiz = ExamenAyudas.ConTarjetaAnclada(tarjeta, this, out _);
        var volver = ExamenAyudas.BotonVolver("‹  Mis evaluaciones", () => Shell.Current.GoToAsync(".."));
        Grid.SetColumnSpan(volver, 3);
        raiz.Add(volver);
        Content = raiz;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _saliendo = false;
        Poner(Mensaje("Un momento…", "Estamos preparando tu examen.", "antesala-cargando"));
        if (Reanudar == "1")
        {
            await ComenzarAsync();
            return;
        }
        await CargarAsync();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _saliendo = true;
        _sondeo?.Stop();
    }

    // ------------------------------------------------------------------------------------ cargar

    private async Task CargarAsync()
    {
        try
        {
            var antesala = await Sesion.Evaluacion.AntesalaAsync(Sesion.Dispositivo, AsignacionId, Sesion.AlumnoParaEvaluar);
            if (_saliendo) return;
            if (antesala is null)
            {
                var sinRed = Sesion.Evaluacion.UltimoError is null or { Estado: 0 };
                var caja = Mensaje(sinRed ? "Sin conexión con el aula" : "No pudimos abrir esta evaluación", sinRed ? "Tus respuestas no se pierden. Vuelve a intentarlo en un momento." : Sesion.Evaluacion.UltimoMotivo ?? "Inténtalo de nuevo.", "antesala-sin-datos");
                var reintentar = Ds.Boton("Reintentar", Ds.Rango.Primary, async (_, _) => await CargarAsync(), 60);
                reintentar.AutomationId = "antesala-reintentar";
                var pila = new VerticalStackLayout { Spacing = 14 };
                pila.Add(caja);
                pila.Add(Ds.Capsula(reintentar));
                Poner(pila);
                return;
            }
            RelojNodo.Aprender(antesala.ServidorEn);
            _antesala = antesala;
            Construir(antesala);
            // Una admisión que ya espera: se sigue esperando sin que el alumno vuelva a pulsar nada.
            if (antesala.Motivo == "espera_admision" || antesala.Admision is { Estado: "en_espera" }) IniciarSondeo();
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ExamenAntesalaPage.Cargar", ex);
            Poner(Mensaje("No pudimos abrir esta evaluación", "Inténtalo de nuevo en un momento.", "antesala-fallo"));
        }
    }

    private void Poner(View vista)
    {
        _contenido.Clear();
        _contenido.Add(vista);
    }

    private static View Mensaje(string titulo, string detalle, string id)
    {
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, AutomationId = id };
        var t = Ds.Titulo(titulo, 24);
        t.HorizontalTextAlignment = TextAlignment.Center;
        var d = Ds.Secundario(detalle, 17);
        d.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(t);
        pila.Add(d);
        return pila;
    }

    // ------------------------------------------------------------------------------ la antesala

    private void Construir(AntesalaDeExamen a)
    {
        _contenido.Clear();
        var titulo = Ds.Titulo(a.Asignacion.Titulo, 28);
        titulo.AutomationId = "antesala-titulo";
        _contenido.Add(titulo);
        if (!string.IsNullOrWhiteSpace(a.Asignacion.CursoRotulo)) _contenido.Add(Ds.Secundario(a.Asignacion.CursoRotulo!, 17));

        var hechos = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Margin = new Thickness(0, 4, 0, 0) };
        foreach (var (texto, id) in new[]
        {
            ($"{a.Asignacion.Preguntas} preguntas", "antesala-preguntas"),
            (ExamenAyudas.Duracion(a.Asignacion.DuracionSeg), "antesala-duracion"),
            (ExamenAyudas.Intentos(a.Asignacion.IntentosPermitidos, a.Asignacion.IntentosUsados), "antesala-intentos"),
        })
        {
            var hecho = ExamenAyudas.Hecho(texto, id);
            hecho.Margin = new Thickness(0, 0, 8, 8);
            hechos.Add(hecho);
        }
        _contenido.Add(hechos);
        if (a.Asignacion.LimiteEn is { } limite)
            _contenido.Add(Ds.Secundario($"Fecha límite: {ExamenAyudas.Hora(limite)}", 16));

        // Las condiciones: el texto obligatorio del nivel (JRN-010). El alumno sabe SIEMPRE bajo qué condiciones presenta.
        var condiciones = a.Condiciones;
        var registra = new VerticalStackLayout { Spacing = 4, Margin = new Thickness(0, 6, 0, 0) };
        registra.Add(new Label { Text = condiciones.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 19, TextColor = Ds.Tinta });
        registra.Add(Ds.Cuerpo(condiciones.Texto, 17, Ds.TintaMedia));
        if (condiciones.Registra is { Count: > 0 } lista)
        {
            registra.Add(new Label { Text = "Qué se registra", FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.TintaSuave, Margin = new Thickness(0, 8, 0, 0) });
            foreach (var linea in lista) registra.Add(ExamenAyudas.Vineta(linea));
        }
        var cajaCondiciones = new Border
        {
            BackgroundColor = Ds.InfoSuave, StrokeThickness = 0, Padding = new Thickness(20, 16),
            StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = registra, AutomationId = "antesala-condiciones",
        };
        _contenido.Add(cajaCondiciones);

        // Lo que esta tableta puede garantizar, dicho tal cual (kiosk.md §5.1): ni más ni menos.
        if (Niveles.Rango(condiciones.Nivel) >= Niveles.Rango(Niveles.Controlado))
            _contenido.Add(ExamenAyudas.Caja("Bloqueo de esta tableta", Seguro(() => Sesion.Kiosco.LockdownSummary), Ds.Lienzo, "antesala-bloqueo"));

        if (a.Dispositivo is { } d && !d.Alcanza)
            _contenido.Add(ExamenAyudas.Caja("Tu tableta no cumple lo que pide este examen",
                "Puedes tocar «Comenzar» de todos modos: tu profesor decidirá cómo continúas. No pierdes nada.", Ds.AlertaSuave, "antesala-no-alcanza"));

        var estado = new Label { FontSize = 16, TextColor = Ds.TintaMedia, HorizontalTextAlignment = TextAlignment.Center, AutomationId = "antesala-estado" };
        var comenzar = Ds.Boton(a.MiIntento is { Estado: EstadosIntento.EnCurso or EstadosIntento.Pausado or EstadosIntento.Restaurando or EstadosIntento.EnCursoFueraDePlazo } ? "Continuar" : "Comenzar",
                                Ds.Rango.Primary, async (_, _) => await ComenzarAsync(), 68);
        comenzar.AutomationId = "antesala-comenzar";
        var puede = a.PuedeComenzar || a.Motivo == "espera_admision";
        Ds.Habilitar(comenzar, puede && a.Motivo != "espera_admision");
        _contenido.Add(estado);
        if (!puede)
        {
            estado.Text = a.Motivo switch
            {
                "rechazada" => "Tu profesor no admitió esta tableta para el examen. Pídele que te indique cómo continuar.",
                "no_abierta" => a.Asignacion.Estado == "programada" ? "Este examen todavía no abre." : "Este examen ya cerró.",
                "ya_entregado" => "Ya presentaste este examen.",
                "intentos_agotados" => "Ya usaste todos los intentos de este examen.",
                _ => "Por ahora no puedes presentar este examen.",
            };
        }
        else if (a.Motivo == "espera_admision" || a.Admision is { Estado: "en_espera" })
        {
            estado.Text = "Esperando que tu profesor decida sobre esta tableta. No cierres esta pantalla: el examen empieza solo.";
        }
        var capsula = Ds.Capsula(comenzar);
        capsula.IsVisible = puede && a.Motivo != "espera_admision";
        _contenido.Add(capsula);
    }

    // ---------------------------------------------------------------------------------- comenzar

    private async Task ComenzarAsync()
    {
        if (_abriendo || _saliendo) return;
        _abriendo = true;
        try
        {
            _sesion ??= Sesion.NuevaSesionDeExamen();
            Sesion.ExamenActual = _sesion;
            var salida = await _sesion.AbrirAsync(AsignacionId);
            if (_saliendo) return;
            switch (salida.Resultado)
            {
                case ResultadoDeApertura.Abierto or ResultadoDeApertura.Reanudado:
                    _sondeo?.Stop();
                    // Si el examen no se pudo leer ahora, el examen lo reintenta solo: no se deja al alumno afuera con el bloqueo puesto.
                    await _sesion.CargarPreguntasAsync();
                    _saliendo = true;
                    await Shell.Current.GoToAsync("../examen");
                    break;
                case ResultadoDeApertura.EsperaAdmision:
                    if (_antesala is null) await CargarAsync();
                    else IniciarSondeo();
                    PintarEspera(salida.Mensaje);
                    break;
                default:
                    PintarProblema(salida);
                    break;
            }
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "ExamenAntesalaPage.Comenzar", ex);
            PintarProblema(new SalidaDeApertura(ResultadoDeApertura.NoDisponible, "No pudimos abrir tu examen ahora. Inténtalo de nuevo."));
        }
        finally { _abriendo = false; }
    }

    private void PintarEspera(string? texto)
    {
        foreach (var v in _contenido.Children.OfType<Label>().Where(l => l.AutomationId == "antesala-estado"))
            v.Text = (string.IsNullOrWhiteSpace(texto) ? "Esperando que tu profesor decida sobre esta tableta." : texto) + " No cierres esta pantalla: el examen empieza solo.";
    }

    private void PintarProblema(SalidaDeApertura salida)
    {
        // El problema se dice en el lugar del estado, sin borrar lo que el alumno estaba leyendo.
        var etiqueta = _contenido.Children.OfType<Label>().FirstOrDefault(l => l.AutomationId == "antesala-estado");
        if (etiqueta is null)
        {
            Poner(Mensaje("No pudimos abrir tu examen", salida.Mensaje ?? "Inténtalo de nuevo.", "antesala-problema"));
            return;
        }
        etiqueta.Text = salida.Mensaje ?? "No pudimos abrir tu examen ahora.";
        if (salida.Resultado == ResultadoDeApertura.Rechazada) _sondeo?.Stop();
    }

    private void IniciarSondeo()
    {
        if (_saliendo) return;
        _sondeo ??= Dispatcher.CreateTimer();
        _sondeo.Interval = SondeoAdmision;
        _sondeo.Tick -= AlSondear;
        _sondeo.Tick += AlSondear;
        if (!_sondeo.IsRunning) _sondeo.Start();
    }

    private async void AlSondear(object? remitente, EventArgs e) => await ComenzarAsync();

    private static string Seguro(Func<string> lectura)
    {
        try { return lectura(); }
        catch (Exception) { return "No se pudo consultar el estado del bloqueo."; }
    }
}
