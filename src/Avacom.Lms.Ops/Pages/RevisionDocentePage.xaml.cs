using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// La revisión docente de un intento (MOD-011 · FUN-120, FUN-121). Muestra sólo los reactivos que requieren la revisión del profesor; los que el sistema ya calificó se resumen en
/// una lista que se abre si se quiere. Por reactivo: el enunciado, lo que respondió el alumno (las evidencias —dibujo, audio— sólo con su referencia), la forma, el estado
/// (pendiente o revisada) y la puntuación: con la rúbrica criterio por criterio (total en vivo) o en pasos de 0 a 100 %. Todo con toques; los comentarios son frases y el texto es un extra.
///
/// <b>Qué sigue pendiente.</b> La cabecera cuenta lo que falta y cada reactivo pendiente lo dice con texto y con tono. «Confirmar revisión» sólo se habilita cuando el nodo dice que se
/// puede (<c>PuedeConfirmar</c>); antes, la pantalla avisa que no hay calificación definitiva y que la cifra que se ve es parcial. Al confirmar, el aviso «Calificación registrada» se
/// muestra en la bandeja, a la que se vuelve. Registrada no es publicada: el alumno la ve cuando el profesor la publique desde el libro.
///
/// <b>Red.</b> Cada guardado manda una <c>solicitud_id</c> nueva; si no llega al nodo, la tarjeta ofrece «Reintentar» con la MISMA solicitud y no se muestra nada como guardado.
/// Cambiar un puntaje ya asentado pide un motivo, en una hoja de frases (el nodo principal no tiene teclado).
/// </summary>
[QueryProperty(nameof(IntentoId), "intento")]
public partial class RevisionDocentePage : ContentPage
{
    private const double AnchoMaximo = 1280;

    public string IntentoId { get; set; } = string.Empty;

    private readonly HojaDeOpciones _hoja = new();
    private readonly AvisoTemporal _aviso;
    private readonly Dictionary<string, TarjetaDeReactivo> _tarjetas = [];
    private readonly Button _confirmar;
    private readonly View _confirmarVista;
    private bool _visible, _cargando, _verOtras, _confirmando;
    private RevisionParaDocente? _revision;
    private long _ultimaLectura;

    private static IGradebookApi Api => Sesion.Gradebook;

    public RevisionDocentePage()
    {
        InitializeComponent();
        Raiz.Add(_hoja);
        _aviso = new AvisoTemporal(ResultadoHost);
        var confirmar = ExamenUi.Accion("Confirmar revisión", Ds.Rango.Primary, CalificacionesUi.Seguro(nameof(RevisionDocentePage), "Confirmar", ConfirmarAsync), 230, "revision-confirmar");
        (_confirmar, _confirmarVista) = confirmar;
        Ds.Habilitar(_confirmar, false);
        AccionesHost.Add(_confirmarVista);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver a la bandeja", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 240, "revision-volver").Vista);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!CalificacionesUi.PuedeLeer)
            {
                TituloLabel.Text = "Este rol no accede a datos académicos";
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.SinAcceso("Sin acceso", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (!CalificacionesUi.PuedeCalificar)
            {
                TituloLabel.Text = "La revisión es del profesorado";
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.SinAcceso("Sólo lectura", "Revisar y puntuar respuestas lo hace el profesor del grupo."));
                return;
            }
            // Sólo se lee al entrar: una revisión en marcha no cambia sola, y releerla pisaría lo que el profesor tiene a medio elegir.
            if (_revision is null)
            {
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.Estado("Leyendo las respuestas…", "Un momento."));
                await CargarAsync();
            }
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "RevisionDocentePage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
    }

    private void OnPageSizeChanged(object? sender, EventArgs e)
    {
        if (Width <= 0) return;
        var ancho = Math.Max(560, Math.Min(AnchoMaximo, Width - 92));
        Cabecera.WidthRequest = AvisoHost.WidthRequest = Cuerpo.WidthRequest = ancho;
    }

    // ---------------------------------------------------------------------------------------------- leer

    /// <summary>Lee la revisión. <paramref name="reiniciar"/> es la pregunta cuyo guardado se acaba de confirmar: su tarjeta toma lo que el nodo tiene; las demás conservan lo que se tocó.</summary>
    private async Task CargarAsync(string? reiniciar = null)
    {
        if (string.IsNullOrWhiteSpace(IntentoId) || _cargando) return;
        _cargando = true;
        try
        {
            var api = Api;
            var revision = await api.RevisionAsync(CalificacionesUi.Actor, IntentoId);
            if (!_visible) return;
            if (revision is null)
            {
                if (_revision is not null)
                {
                    ConexionHost.Clear();
                    ConexionHost.Add(CalificacionesUi.SinConexion(api)
                        ? ExamenUi.Aviso("Sin conexión con el aula", $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}.", Tono.Ambar)
                        : ExamenUi.Aviso("No se pudo actualizar la revisión", CalificacionesUi.Error(api), Tono.Ambar));
                    return;
                }
                TituloLabel.Text = "No se pudo leer la revisión";
                SubtituloLabel.Text = string.Empty;
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.Estado("No se pudo leer la revisión", CalificacionesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(RevisionDocentePage), "Reintentar", () => CargarAsync()), 170, "revision-reintentar", margen: false).Vista));
                return;
            }
            ConexionHost.Clear();
            _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            _revision = revision;
            Aplicar(revision, reiniciar);
        }
        finally { _cargando = false; }
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Aplicar(RevisionParaDocente r, string? reiniciar)
    {
        var y = Desplazable.ScrollY;
        PintarCabecera(r);
        PintarResumen(r);
        SincronizarTarjetas(r, reiniciar);
        PintarOtras(r);
        if (reiniciar is not null && y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    private void PintarCabecera(RevisionParaDocente r)
    {
        var i = r.Intento;
        TituloLabel.Text = string.IsNullOrWhiteSpace(i.AlumnoRotulo) ? "Estudiante" : i.AlumnoRotulo;
        SubtituloLabel.Text = i.Titulo ?? "Evaluación";
        PastillasHost.Clear();
        var pendientes = i.Pendientes.Count;
        PastillasHost.Add(CalificacionesUi.PildoraEnFila(pendientes == 0 ? "Todo puntuado" : pendientes == 1 ? "1 pendiente" : $"{pendientes} pendientes", pendientes == 0 ? Matiz.Exito : Matiz.Violeta, 14));
        if (i.Reabierta) PastillasHost.Add(CalificacionesUi.PildoraEnFila("Reabierta para recalificar", Matiz.Ambar, 14));
        // La cifra provisional se dice como lo que es: lo ya calificado, no una nota.
        if (i.PorcentajeProvisional is { } p) PastillasHost.Add(CalificacionesUi.PildoraEnFila($"Cifra provisional {GradebookTexto.Puntaje(p)} % · no es la calificación", Matiz.Neutro, 14));
        Ds.Habilitar(_confirmar, r.PuedeConfirmar && !_confirmando);
    }

    /// <summary>Qué falta antes de poder ofrecer una calificación definitiva, y qué pasa al confirmar.</summary>
    private void PintarResumen(RevisionParaDocente r)
    {
        ResumenHost.Clear();
        var i = r.Intento;
        var pila = new VerticalStackLayout { Spacing = 10 };
        if (r.PuedeConfirmar)
        {
            pila.Add(ExamenUi.Aviso("Todo está puntuado", "Confirma la revisión para registrar la calificación.", Tono.Exito));
            pila.Add(Ds.Secundario("Quedará revisada pero sin publicar: el estudiante no la ve hasta que la publiques desde el libro de calificaciones.", 14));
        }
        else
        {
            var n = i.Pendientes.Count;
            pila.Add(ExamenUi.Aviso(n == 0 ? "No se puede confirmar todavía" : n == 1 ? "Queda 1 respuesta por puntuar" : $"Quedan {n} respuestas por puntuar",
                "Mientras algo siga pendiente no hay calificación definitiva: la cifra que ves es parcial, de lo ya calificado.", Tono.Violeta));
        }
        if (i.Reabierta)
            pila.Add(ExamenUi.Aviso("Esta calificación está reabierta", "No cuenta mientras la recalificas. Al confirmar la revisión, se vuelve a registrar.", Tono.Ambar));
        ResumenHost.Add(ExamenUi.Tarjeta(pila));
    }

    /// <summary>Una tarjeta por reactivo que requiere revisión, creada UNA vez y puesta al día después (lleva cajas de texto: no se mueve de contenedor).</summary>
    private void SincronizarTarjetas(RevisionParaDocente r, string? reiniciar)
    {
        var todas = r.Filas.ToList();
        for (var indice = 0; indice < todas.Count; indice++)
        {
            var fila = todas[indice];
            if (!fila.RequiereRevision) continue;
            if (_tarjetas.TryGetValue(fila.PreguntaRef, out var tarjeta))
            {
                tarjeta.Actualizar(fila, reiniciarSeleccion: fila.PreguntaRef == reiniciar);
                continue;
            }
            tarjeta = new TarjetaDeReactivo(r.Intento.Id, indice + 1, fila, GuardarAsync);
            _tarjetas[fila.PreguntaRef] = tarjeta;
            TarjetasHost.Add(tarjeta);
        }
        if (_tarjetas.Count == 0 && TarjetasHost.Children.Count == 0)
            TarjetasHost.Add(ExamenUi.Tarjeta(Ds.Secundario("Este intento no tiene respuestas que requieran tu revisión.", 15)));
    }

    /// <summary>Las respuestas que el sistema ya calificó: una línea cada una, plegadas por defecto.</summary>
    private void PintarOtras(RevisionParaDocente r)
    {
        OtrasHost.Clear();
        var otras = r.Filas.Select((f, i) => (Fila: f, Numero: i + 1)).Where(x => !x.Fila.RequiereRevision).ToList();
        if (otras.Count == 0) return;
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion(otras.Count == 1 ? "1 respuesta ya calificada por el sistema" : $"{otras.Count} respuestas ya calificadas por el sistema"));
        pila.Add(Ds.Secundario("No necesitan tu revisión. Si quieres verlas, ábrelas.", 14));
        var ver = ExamenUi.Accion(_verOtras ? "Ocultar" : "Ver estas respuestas", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(RevisionDocentePage), "VerOtras", AlternarOtrasAsync), 240, "revision-ver-otras", margen: false);
        ver.Vista.HorizontalOptions = LayoutOptions.Start;
        pila.Add(ver.Vista);
        if (_verOtras)
        {
            foreach (var (fila, numero) in otras)
            {
                var puntaje = fila.PuntajeActual is { } p ? $"{GradebookTexto.Puntaje(p)} de {GradebookTexto.Puntaje(fila.PuntajeMaximo)}" : "sin puntaje";
                var texto = new VerticalStackLayout { Spacing = 2 };
                texto.Add(new Label { Text = $"{numero}.  {fila.Enunciado}", FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 2 });
                texto.Add(Ds.Secundario($"{RespuestaDeRevision.Resumen(fila)} · {puntaje}", 13));
                pila.Add(CalificacionesUi.Fila(texto, new Thickness(14, 8)));
            }
        }
        OtrasHost.Add(ExamenUi.Tarjeta(pila));
    }

    private Task AlternarOtrasAsync()
    {
        _verOtras = !_verOtras;
        if (_revision is { } r) PintarOtras(r);
        return Task.CompletedTask;
    }

    // ------------------------------------------------------------------------------------------- guardar

    /// <summary>
    /// Guarda la puntuación de un reactivo. Un puntaje ya asentado pide un motivo (frases en una hoja; tocar una frase lo confirma). El resultado dice si se guardó, si no se llegó al
    /// nodo (la tarjeta ofrece reintentar con la misma solicitud) o si el nodo lo rechazó. Tras guardar, se vuelve a leer la revisión: el nodo es quien dice qué falta.
    /// </summary>
    private async Task<RespuestaDeGuardado> GuardarAsync(PeticionDeRevision p)
    {
        var motivo = p.MotivoPrevio;
        if (p.YaPuntuada && motivo is null)
        {
            motivo = await _hoja.PedirMotivoAsync("¿Por qué cambias el puntaje?", "Queda el valor anterior y el nuevo en el historial.", FrasesDeCalificaciones.MotivosDeCambioDePuntaje);
            if (motivo is null) return new RespuestaDeGuardado(ResultadoDeGuardado.Cancelado);
        }

        var api = Api;
        var r = p.Criterios is { } criterios
            ? await api.AplicarRubricaAsync(CalificacionesUi.Actor, IntentoId, p.PreguntaRef, criterios, p.Comentario, motivo, p.SolicitudId)
            : await api.PuntuarAsync(CalificacionesUi.Actor, IntentoId, p.PreguntaRef, p.Puntaje ?? 0m, p.Comentario, motivo, p.SolicitudId);
        if (!_visible) return new RespuestaDeGuardado(r is null ? ResultadoDeGuardado.SinConexion : ResultadoDeGuardado.Guardado, null, motivo);
        if (r is null)
        {
            // Una operación que no llegó al nodo NUNCA se muestra como confirmada.
            var texto = CalificacionesUi.Error(api);
            return new RespuestaDeGuardado(CalificacionesUi.SinConexion(api) ? ResultadoDeGuardado.SinConexion : ResultadoDeGuardado.Rechazado, texto, motivo);
        }

        var faltan = r.Pendientes.Count;
        _aviso.Mostrar(r.Reintento ? "Ya estaba guardado" : "Puntaje guardado",
            faltan == 0 ? "Ya no queda nada por puntuar: puedes confirmar la revisión." : $"Quedan {(faltan == 1 ? "1 respuesta" : $"{faltan} respuestas")} por puntuar.", Tono.Exito);
        await CargarAsync(reiniciar: p.PreguntaRef);
        return new RespuestaDeGuardado(ResultadoDeGuardado.Guardado, null, motivo);
    }

    // ------------------------------------------------------------------------------------------ confirmar

    /// <summary>
    /// «Confirmar revisión»: cierra la revisión y registra la calificación (FUN-119). Con pendientes el nodo lo rechaza y se dice qué falta. Si el nodo responde que la revisión ya no estaba
    /// pendiente (un reintento después de perder la señal), se toma como confirmada. Al terminar se vuelve a la bandeja con el aviso «Calificación registrada».
    /// </summary>
    private async Task ConfirmarAsync()
    {
        if (_confirmando || _revision is null) return;
        _confirmando = true;
        Ds.Habilitar(_confirmar, false);
        try
        {
            var api = Api;
            var r = await api.ConfirmarRevisionAsync(CalificacionesUi.Actor, IntentoId);
            if (!_visible) return;
            if (r is null && api.UltimoError?.Codigo == "revision_no_pendiente")
            {
                RevisionBandejaPage.AvisoAlVolver = ("La revisión ya estaba confirmada", "No hay nada más que hacer con este intento.");
                await Shell.Current.GoToAsync("..");
                return;
            }
            if (r is null)
            {
                _aviso.Mostrar("No se pudo confirmar la revisión", CalificacionesUi.Error(api), Tono.Ambar);
                await CargarAsync();       // el nodo dice qué sigue pendiente
                return;
            }
            RevisionBandejaPage.AvisoAlVolver = (r.Registrada ? "Calificación registrada" : "Revisión confirmada", Detalle(r));
            await Shell.Current.GoToAsync("..");
        }
        finally
        {
            _confirmando = false;
            if (_revision is { } actual) Ds.Habilitar(_confirmar, actual.PuedeConfirmar);
        }
    }

    private static string Detalle(RevisionConfirmada r)
    {
        if (!r.Registrada) return "El nivel de este grupo está en modo simple: no se registró una calificación.";
        var descartado = r.AjusteDescartado && r.AjusteAnterior is { } anterior
            ? $" Ojo: la puntuación cambió al recalificar y el ajuste que habías hecho ({GradebookTexto.Puntaje(anterior)}) ya no aplica; quedó en el historial. Si quieres otro valor, ajústala de nuevo."
            : string.Empty;
        return (r.Calificacion is { } c
            ? $"Resultado interno {GradebookTexto.Puntaje(c.PuntajeEfectivo)} de 100. Está revisada pero sin publicar: el estudiante la ve cuando la publiques."
            : "Quedó revisada pero sin publicar: el estudiante la ve cuando la publiques.") + descartado;
    }
}
