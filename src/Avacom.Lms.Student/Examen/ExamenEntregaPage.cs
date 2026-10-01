using Avacom.Lms.Core.Evaluacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Student.Examen;

/// <summary>
/// La entrega confirmada (PAN-123) y, cuando el profesor la libera, el resultado.
///
///  · «Tu examen quedó entregado» y QUÉ SIGUE, con el texto que manda el nodo. <b>Nunca dice «calificado»</b> mientras quede un reactivo por revisar (Guion, paso 13).
///  · Si el examen se entregó solo (se acabó el tiempo, venció el plazo, el profesor lo cerró) lo dice con una frase, sin culpar a nadie.
///  · El resultado sólo existe si el profesor lo liberó (DEC-032): antes, el nodo responde 403 y aquí no hay botón. Un resultado que no alcanzó el mínimo se dice con calma, en ámbar:
///    nada en rojo y nunca una burla.
/// Se llega por dos caminos: recién entregado (con la sesión del examen) o desde «Mis evaluaciones» para ver un resultado (con <c>intento=ID</c>).
/// </summary>
[QueryProperty(nameof(IntentoId), "intento")]
public sealed class ExamenEntregaPage : ContentPage
{
    public string IntentoId { get; set; } = string.Empty;

    private readonly VerticalStackLayout _contenido = new() { Spacing = 14 };

    public ExamenEntregaPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Shell.SetBackButtonBehavior(this, new BackButtonBehavior { IsVisible = false, IsEnabled = false });
        BackgroundColor = Ds.Lienzo;
        var tarjeta = Ds.Tarjeta(new ScrollView { Content = _contenido }, Ds.RadioTarjeta, new Thickness(30, 28));
        tarjeta.AutomationId = "entrega-tarjeta";
        Content = ExamenAyudas.ConTarjetaAnclada(tarjeta, this, out _);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        var sesion = Sesion.ExamenActual;
        if (!string.IsNullOrEmpty(IntentoId))
        {
            await MostrarResultadoAsync(IntentoId);
            return;
        }
        if (sesion?.Entrega is { } entrega) Entregado(sesion, entrega);
        else if (sesion is { Fase: FaseDeExamen.Terminado }) EntregadoPorElNodo(sesion);
        else await Shell.Current.GoToAsync("..");
    }

    protected override bool OnBackButtonPressed() => true;     // sin esta pantalla no se sale a medias: el botón «Volver» la cierra

    // ---------------------------------------------------------------------------------- entregado

    private void Entregado(SesionDeExamen sesion, EntregaDeIntento entrega)
    {
        _contenido.Clear();
        _contenido.Add(Marca("✓", "entrega-marca"));
        var titulo = Ds.Titulo("Tu examen quedó entregado", 28);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        titulo.AutomationId = "entrega-titulo";
        _contenido.Add(titulo);
        var origen = entrega.OrigenEntrega switch
        {
            "tiempo" => "Se acabó el tiempo y tu examen se entregó solo. Lo que respondiste está guardado.",
            "plazo" => "Venció el plazo y tu examen se entregó solo. Lo que respondiste está guardado.",
            "cierre" or "profesor" => "Tu profesor cerró el examen y tu trabajo se entregó. Lo que respondiste está guardado.",
            "nodo" => "Tu examen se entregó solo (se acabó el tiempo o tu profesor lo cerró). Lo que respondiste está guardado.",
            _ => null,
        };
        if (origen is not null)
        {
            var o = Ds.Cuerpo(origen, 18, Ds.TintaMedia);
            o.HorizontalTextAlignment = TextAlignment.Center;
            _contenido.Add(o);
        }
        // El nodo dice «Tu examen quedó entregado. …»: el título ya lo dijo, así que sólo se repite lo que sigue.
        var frase = (entrega.QueSigue.Texto ?? string.Empty).Trim();
        const string eco = "Tu examen quedó entregado.";
        if (frase.StartsWith(eco, StringComparison.Ordinal)) frase = frase[eco.Length..].Trim();
        if (frase.Length > 0)
        {
            var siguiente = Ds.Cuerpo(frase, 20, Ds.Tinta);
            siguiente.HorizontalTextAlignment = TextAlignment.Center;
            siguiente.AutomationId = "entrega-que-sigue";
            _contenido.Add(siguiente);
        }
        var cuenta = Ds.Secundario($"Respondiste {entrega.Intento.Respondidas} de {entrega.Intento.Total} preguntas.", 16);
        cuenta.HorizontalTextAlignment = TextAlignment.Center;
        _contenido.Add(cuenta);
        if (sesion.PendientesEnDispositivo > 0)
        {
            var pendiente = Ds.Secundario("Algo quedó guardado en esta tableta y se enviará solo cuando haya conexión.", 15);
            pendiente.HorizontalTextAlignment = TextAlignment.Center;
            _contenido.Add(pendiente);
        }
        if (entrega.ResultadoDisponible && entrega.Intento.Id is { Length: > 0 } id)
        {
            var ver = Ds.Boton("Ver mi resultado", Ds.Rango.Secondary, async (_, _) => await MostrarResultadoAsync(id), 60);
            ver.AutomationId = "entrega-ver-resultado";
            _contenido.Add(Ds.Capsula(ver));
        }
        _contenido.Add(BotonVolver());
        _ = sesion.VaciarAsync();     // cualquier incidente o respuesta de último momento sale ahora
    }

    private void EntregadoPorElNodo(SesionDeExamen sesion)
    {
        var estado = sesion.Intento?.Estado;
        var resumen = sesion.Intento ?? new ResumenDeIntento(sesion.IntentoId ?? string.Empty, estado ?? EstadosIntento.Entregado, 1);
        var queSigue = estado == EstadosIntento.EnRevision ? new QueSigue("en_revision", "Tu examen quedó entregado. Algunas respuestas las revisa tu profesor.")
                                                          : new QueSigue("resultado_al_liberar", "Tu examen quedó entregado. Tu profesor publicará los resultados.");
        Entregado(sesion, new EntregaDeIntento(resumen, null, "nodo", queSigue));      // entregó el nodo: no dice por qué en el estado
    }

    private static View Marca(string glifo, string id) => new Border
    {
        WidthRequest = 84, HeightRequest = 84, BackgroundColor = Ds.ExitoSuave, StrokeThickness = 0, HorizontalOptions = LayoutOptions.Center, AutomationId = id,
        StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = 42 },
        Content = new Label { Text = glifo, FontSize = 42, FontFamily = Ds.FuenteMedia, TextColor = Ds.Exito, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center },
    };

    private View BotonVolver()
    {
        var volver = Ds.Boton("Volver a mis evaluaciones", Ds.Rango.Primary, async (_, _) => await Volver(), 64);
        volver.AutomationId = "entrega-volver";
        var capsula = Ds.Capsula(volver);
        capsula.Margin = new Thickness(0, 10, 0, 0);
        return capsula;
    }

    private static async Task Volver()
    {
        Sesion.ExamenActual = null;
        await Shell.Current.GoToAsync("..");
    }

    // ----------------------------------------------------------------------------------- resultado

    private async Task MostrarResultadoAsync(string intentoId)
    {
        _contenido.Clear();
        _contenido.Add(Ds.Secundario("Un momento…", 17));
        ResultadoDeIntento? resultado = null;
        try { resultado = await Sesion.Evaluacion.ResultadoAsync(Sesion.Dispositivo, intentoId, Sesion.AlumnoParaEvaluar); }
        catch (Exception ex) { RegistroDeFallos.Escribir("student", "ExamenEntregaPage.Resultado", ex); }
        _contenido.Clear();
        if (resultado is null)
        {
            var codigo = Sesion.Evaluacion.UltimoError?.Codigo;
            var sinRed = Sesion.Evaluacion.UltimoError is null or { Estado: 0 };
            var t = Ds.Titulo(codigo == "resultados_no_liberados" ? "Tu profesor aún no publica los resultados" : sinRed ? "Sin conexión con el aula" : "No pudimos ver tu resultado ahora", 24);
            t.HorizontalTextAlignment = TextAlignment.Center;
            t.AutomationId = "resultado-no-disponible";
            _contenido.Add(t);
            var d = Ds.Secundario(codigo == "resultados_no_liberados" ? "Cuando lo haga, podrás verlos aquí." : "Inténtalo de nuevo en un momento.", 17);
            d.HorizontalTextAlignment = TextAlignment.Center;
            _contenido.Add(d);
            _contenido.Add(BotonVolver());
            return;
        }

        var porcentaje = resultado.Porcentaje is { } p ? $"{Math.Round(p):0} %" : "—";
        var nota = new Label { Text = porcentaje, FontFamily = Ds.FuenteMedia, FontSize = 64, TextColor = Ds.Tinta, HorizontalTextAlignment = TextAlignment.Center, AutomationId = "resultado-porcentaje" };
        _contenido.Add(nota);
        if (resultado.Aprobado is { } aprobado)
        {
            var pildora = Ds.Pildora(aprobado ? "Aprobado" : $"Todavía no llegas al {resultado.AprobacionPct:0} % que pide el examen", aprobado ? Ds.ExitoSuave : Ds.AlertaSuave, Ds.Tinta, 17);
            pildora.HorizontalOptions = LayoutOptions.Center;
            pildora.AutomationId = "resultado-estado";
            _contenido.Add(pildora);
        }
        _contenido.Add(Ds.Secundario(resultado.PuntajeMaximo is { } maximo ? $"{resultado.Puntaje:0.##} de {maximo:0.##} puntos" : string.Empty, 16));
        if (resultado.Detalle is { Count: > 0 } detalle)
        {
            _contenido.Add(new Label { Text = "Pregunta por pregunta", FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, Margin = new Thickness(0, 10, 0, 0) });
            var n = 1;
            foreach (var d in detalle)
            {
                var marca = !d.Respondida ? "—" : d.Correcta == true ? "✓" : d.Correcta == false ? "✗" : "…";
                var tono = !d.Respondida ? Ds.Lienzo : d.Correcta == true ? Ds.ExitoSuave : d.Correcta == false ? Ds.AlertaSuave : Ds.InfoSuave;
                var pila = new VerticalStackLayout { Spacing = 2 };
                pila.Add(Ds.Cuerpo($"{marca}  Pregunta {n}" + (d.PuntajeMaximo is { } m ? $" · {d.Puntaje:0.##} de {m:0.##}" : string.Empty), 17, Ds.Tinta));
                if (!d.Respondida) pila.Add(Ds.Secundario("No la respondiste.", 15));
                foreach (var retro in d.Retroalimentacion ?? []) pila.Add(Ds.Secundario(retro, 15));
                if (!string.IsNullOrWhiteSpace(d.Comentario)) pila.Add(Ds.Secundario($"Comentario de tu profesor: {d.Comentario}", 15));
                _contenido.Add(new Border { BackgroundColor = tono, StrokeThickness = 0, Padding = new Thickness(16, 10), StrokeShape = new Microsoft.Maui.Controls.Shapes.RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = pila });
                n++;
            }
        }
        _contenido.Add(BotonVolver());
    }
}
