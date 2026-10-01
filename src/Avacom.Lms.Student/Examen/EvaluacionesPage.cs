using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// «Mis evaluaciones» (MOD-010 · JRN-010): lo que el profesor aplicó a esta persona y cómo va cada cosa —por presentar, en curso, entregado, con resultado—. Se sondea
/// cada 5 s mientras la pantalla está a la vista (el aviso en tiempo real sólo existe dentro de una clase).
///
/// Sin sesión de usuario (Q-34 abierta) la tableta no sabe a quién presentar: pregunta «¿Quién eres?» entre los alumnos de los grupos con una evaluación abierta, sin
/// código ni contraseña (D-19: el LMS es offline y no hay verificación central), igual que Modo Estudio. Con sesión el pase del nodo ya lo dice.
///
/// Nunca un código: cada estado es una frase (UXR-004), y nada aparece en rojo.
/// </summary>
public sealed class EvaluacionesPage : ContentPage
{
    private static readonly TimeSpan Sondeo = TimeSpan.FromSeconds(5);

    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 14, Padding = new Thickness(24, 8, 24, 36), MaximumWidthRequest = 960, HorizontalOptions = LayoutOptions.Center };
    private readonly Label _quien;
    private IDispatcherTimer? _temporizador;
    private bool _cargando;
    private string? _firma;
    private EstudiantesDeExamen? _estudiantes;
    private string? _grupoElegido;

    public EvaluacionesPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        BackgroundColor = Ds.Lienzo;

        var volver = Ds.Boton("‹  Menú", Ds.Rango.Quiet, async (_, _) => await Shell.Current.GoToAsync(".."), 52);
        volver.FontSize = 17;
        volver.AutomationId = "evals-volver";
        var titulo = Ds.Titulo("Mis evaluaciones", 28);
        titulo.VerticalOptions = LayoutOptions.Center;
        titulo.AutomationId = "evals-titulo";
        _quien = Ds.Secundario(string.Empty, 15);
        _quien.VerticalOptions = LayoutOptions.Center;
        _quien.HorizontalTextAlignment = TextAlignment.End;
        _quien.AutomationId = "evals-quien";
        var cambiar = new TapGestureRecognizer();
        cambiar.Tapped += (_, _) => CambiarDePersona();
        _quien.GestureRecognizers.Add(cambiar);

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
        await CargarAsync();
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
        if (Sesion.SabeQuienEvalua) await CargarAsync();
    }

    // ------------------------------------------------------------------------------------ cargar

    private async Task CargarAsync()
    {
        if (_cargando) return;
        _cargando = true;
        try
        {
            if (!Sesion.SabeQuienEvalua)
            {
                _quien.Text = string.Empty;
                await PintarQuienEresAsync();
                return;
            }
            _quien.Text = Sesion.AlumnoDeEvaluacion is null
                ? string.Empty
                : $"Presentas como {Sesion.AlumnoDeEvaluacionRotulo ?? "tú"}  ·  ¿No eres tú? Toca aquí";
            var mis = await Sesion.Evaluacion.MisAsync(Sesion.Dispositivo, Sesion.AlumnoParaEvaluar, todas: true);
            if (mis is null)
            {
                var sinRed = Sesion.Evaluacion.UltimoError is null or { Estado: 0 };
                if (_firma is null) Pintar(sinRed ? Mensaje("Sin conexión con el aula", "Cuando tu tableta vuelva a la red del aula, aquí verás tus evaluaciones.")
                                                  : Mensaje("No pudimos ver tus evaluaciones ahora", Sesion.Evaluacion.UltimoMotivo ?? "Inténtalo de nuevo en un momento."), "sin-datos");
                return;
            }
            RelojNodo.Aprender(mis.ServidorEn);
            var firma = string.Join("|", mis.Pendientes.Concat(mis.Recientes).Select(e => $"{e.Id}:{e.Estado}:{e.PuedeComenzar}:{e.Motivo}:{e.MiIntento?.Estado}:{e.MiIntento?.ResultadoDisponible}"));
            if (firma == _firma) return;                // lo mismo que ya se ve: no se repinta (parpadea y deja a la accesibilidad sin el botón)
            _firma = firma;
            Pintar(ConstruirLista(mis), firma);
        }
        catch (Exception ex)
        {
            RegistroDeFallos.Escribir("student", "EvaluacionesPage.Cargar", ex);
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
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, AutomationId = "evals-mensaje" };
        var t = Ds.Titulo(titulo, 23);
        t.HorizontalTextAlignment = TextAlignment.Center;
        var d = Ds.Secundario(detalle, 17);
        d.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(t);
        pila.Add(d);
        return Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 40));
    }

    // ------------------------------------------------------------------------------ la lista

    private View ConstruirLista(MisEvaluaciones mis)
    {
        var pila = new VerticalStackLayout { Spacing = 14 };
        if (mis.Pendientes.Count == 0 && mis.Recientes.Count == 0)
            return Mensaje("No tienes evaluaciones por ahora", "Cuando tu profesor aplique una, aparecerá aquí.");
        if (mis.Pendientes.Count > 0)
        {
            pila.Add(Ds.Cuerpo("Para presentar", 19, Ds.Tinta));
            foreach (var e in mis.Pendientes) pila.Add(Tarjeta(e));
        }
        if (mis.Recientes.Count > 0)
        {
            pila.Add(Ds.Cuerpo("Presentadas hace poco", 19, Ds.Tinta));
            foreach (var e in mis.Recientes) pila.Add(Tarjeta(e));
        }
        return pila;
    }

    private enum Accion { Comenzar, Continuar, VerResultado, Nada }

    /// <summary>Qué puede hacer el alumno con esta evaluación y qué se le dice, siempre en una frase.</summary>
    private static (Accion Accion, string Boton, string Frase) QuePuedeHacer(EvaluacionDelAlumno e)
    {
        var intento = e.MiIntento;
        if (intento is not null)
        {
            switch (intento.Estado)
            {
                case EstadosIntento.EnCurso or EstadosIntento.EnCursoFueraDePlazo or EstadosIntento.Pausado or EstadosIntento.Restaurando:
                    return (Accion.Continuar, "Continuar", EstadosIntento.Suspendido(intento.Estado) ? "Tu examen está en pausa: avisa a tu profesor" : "Tienes un examen en curso");
                case EstadosIntento.Entregado or EstadosIntento.EnRevision:
                    return (Accion.Nada, string.Empty, "Entregado · tu profesor publicará los resultados");
                case EstadosIntento.Calificado:
                    return intento.ResultadoDisponible ? (Accion.VerResultado, "Ver resultado", "Ya puedes ver tu resultado") : (Accion.Nada, string.Empty, "Entregado · tu profesor publicará los resultados");
                case EstadosIntento.Anulado:
                    return (Accion.Nada, string.Empty, "Este intento no cuenta: habla con tu profesor");
            }
        }
        if (e.PuedeComenzar) return (Accion.Comenzar, "Comenzar", "Lee las condiciones antes de empezar");
        return e.Motivo switch
        {
            "espera_admision" => (Accion.Comenzar, "Ver", "Esperando que tu profesor decida sobre esta tableta"),
            "rechazada" => (Accion.Nada, string.Empty, "Tu profesor no admitió esta tableta: pídele que te indique cómo continuar"),
            "no_abierta" => (Accion.Nada, string.Empty, e.Estado == "programada" && e.AbreEn is { } abre ? $"Abre {ExamenAyudas.Hora(abre)}" : "Este examen ya cerró"),
            "ya_entregado" or "intentos_agotados" => (Accion.Nada, string.Empty, "Ya presentaste este examen"),
            _ => (Accion.Nada, string.Empty, "Por ahora no puedes presentarlo"),
        };
    }

    private View Tarjeta(EvaluacionDelAlumno e)
    {
        var (accion, textoBoton, frase) = QuePuedeHacer(e);
        var textos = new VerticalStackLayout { Spacing = 4, VerticalOptions = LayoutOptions.Center };
        var titulo = Ds.Cuerpo(e.Titulo, 20, Ds.Tinta);
        titulo.FontFamily = Ds.FuenteMedia;
        titulo.LineBreakMode = LineBreakMode.TailTruncation;
        titulo.MaxLines = 2;
        textos.Add(titulo);
        textos.Add(Ds.Secundario(string.Join(" · ", new[] { e.CursoRotulo, $"{e.Preguntas} preguntas", e.LimiteEn is { } limite ? $"hasta {ExamenAyudas.Hora(limite)}" : null }.Where(x => !string.IsNullOrWhiteSpace(x))), 15));
        var etiquetas = new HorizontalStackLayout { Spacing = 8, Margin = new Thickness(0, 4, 0, 2) };
        etiquetas.Add(Ds.Pildora(ExamenAyudas.RotuloNivel(e.NivelExamen), Ds.Lienzo, Ds.Tinta, 13));
        etiquetas.Add(Ds.Pildora(ExamenAyudas.FraseDeEstado(e.Estado), e.Estado == "activa" ? Ds.ExitoSuave : e.Estado == "activa_fuera_de_plazo" ? Ds.AlertaSuave : Ds.Lienzo, Ds.Tinta, 13));
        textos.Add(etiquetas);
        textos.Add(Ds.Secundario(frase, 15));

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 16, AutomationId = $"eval-{e.Id}" };
        fila.Add(Ds.IconoCategoria("examen", 52), 0, 0);
        fila.Add(textos, 1, 0);
        if (accion != Accion.Nada)
        {
            var boton = Ds.Boton(textoBoton, accion == Accion.VerResultado ? Ds.Rango.Secondary : Ds.Rango.Primary, async (_, _) => await Abrir(e, accion), 60, 170);
            boton.AutomationId = $"eval-boton-{e.Id}";
            boton.VerticalOptions = LayoutOptions.Center;
            fila.Add(Ds.Capsula(boton), 2, 0);
        }
        return Ds.Tarjeta(fila, Ds.RadioTarjeta, new Thickness(20, 16));
    }

    private static async Task Abrir(EvaluacionDelAlumno e, Accion accion)
    {
        if (accion == Accion.VerResultado && e.MiIntento is { } intento)
            await Shell.Current.GoToAsync($"examen-entrega?intento={Uri.EscapeDataString(intento.Id)}");
        else
            await Shell.Current.GoToAsync($"examen-antesala?asignacion={Uri.EscapeDataString(e.Id)}&reanudar={(accion == Accion.Continuar ? 1 : 0)}");
    }

    // ----------------------------------------------------------------------------- ¿Quién eres?

    private void CambiarDePersona()
    {
        if (ClienteJson.Token is not null) return;   // con sesión el pase ya dice quién es
        Sesion.AlumnoDeEvaluacion = null;
        Sesion.AlumnoDeEvaluacionRotulo = null;
        _firma = null;
        _estudiantes = null;
        _grupoElegido = null;
        _ = CargarAsync();
    }

    private async Task PintarQuienEresAsync()
    {
        _estudiantes ??= await Sesion.Evaluacion.EstudiantesAsync();
        if (_estudiantes is null)
        {
            Pintar(Mensaje("Sin conexión con el aula", "Cuando tu tableta vuelva a la red del aula, podrás elegir quién eres."), "quien-sin-red");
            _estudiantes = null;
            return;
        }
        if (_estudiantes.Grupos.Count == 0)
        {
            Pintar(Mensaje("No hay evaluaciones abiertas", "Cuando tu profesor aplique una, aquí podrás elegir quién eres y presentarla."), "quien-vacio");
            _estudiantes = null;
            return;
        }
        var grupo = _estudiantes.Grupos.FirstOrDefault(g => g.Id == _grupoElegido) ?? (_estudiantes.Grupos.Count == 1 ? _estudiantes.Grupos[0] : null);
        var firma = $"quien|{grupo?.Id}|{string.Join(",", _estudiantes.Grupos.Select(g => g.Id))}";
        if (firma == _firma) return;
        var pila = new VerticalStackLayout { Spacing = 14, AutomationId = "evals-quien-eres" };
        var titulo = Ds.Titulo("¿Quién eres?", 26);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(titulo);
        var detalle = Ds.Secundario(grupo is null ? "Elige tu grupo y luego tu nombre." : "Toca tu nombre para ver tus evaluaciones.", 17);
        detalle.HorizontalTextAlignment = TextAlignment.Center;
        pila.Add(detalle);
        var lista = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Center, Margin = new Thickness(0, 6, 0, 0) };
        if (grupo is null)
        {
            foreach (var g in _estudiantes.Grupos)
            {
                var boton = Ds.Boton(g.Nombre ?? "Grupo", Ds.Rango.Secondary, (_, _) => { _grupoElegido = g.Id; _firma = null; _ = CargarAsync(); }, 64);
                boton.AutomationId = $"evals-grupo-{g.Id}";
                var capsula = Ds.Capsula(boton);
                capsula.Margin = new Thickness(6);
                lista.Add(capsula);
            }
        }
        else
        {
            foreach (var a in grupo.Alumnos)
            {
                var boton = Ds.Boton(a.Rotulo ?? a.Id, Ds.Rango.Secondary, (_, _) => Elegir(a), 64);
                boton.AutomationId = $"evals-alumno-{a.Id}";
                var capsula = Ds.Capsula(boton);
                capsula.Margin = new Thickness(6);
                lista.Add(capsula);
            }
        }
        pila.Add(lista);
        if (grupo is not null && _estudiantes.Grupos.Count > 1)
        {
            var otro = Ds.Boton("‹  Elegir otro grupo", Ds.Rango.Quiet, (_, _) => { _grupoElegido = null; _firma = null; _ = CargarAsync(); }, 52);
            pila.Add(otro);
        }
        Pintar(Ds.Tarjeta(pila, Ds.RadioTarjeta, new Thickness(28, 32)), firma);
    }

    private void Elegir(AlumnoDeGrupo alumno)
    {
        Sesion.AlumnoDeEvaluacion = alumno.Id;
        Sesion.AlumnoDeEvaluacionRotulo = alumno.Rotulo;
        _firma = null;
        _ = CargarAsync();
    }
}
