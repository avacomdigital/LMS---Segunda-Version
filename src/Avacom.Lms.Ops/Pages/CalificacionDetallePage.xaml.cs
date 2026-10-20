using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Calificaciones;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// El detalle de UNA calificación (MOD-011 · FUN-122, FUN-123). Dice lo que el nodo respondió, sin calcular nada: estado y versión, quién y cómo se calificó, CUATRO bloques separados
/// (el resultado interno 0–100, la calificación presentada, el nivel de desempeño —con «valorado por el profesor» si aplica— y el criterio de aprobación), la puntuación ORIGINAL y la
/// EFECTIVA, la retroalimentación y el historial de versiones (tipo, anterior → nuevo, motivo, quién y cuándo según el reloj del nodo).
///
/// Quien califica (el profesorado) además puede ajustar la puntuación con un teclado numérico táctil y un motivo en frases, reabrir para recalificar, publicar o retirar la publicación,
/// valorar el nivel de desempeño y retroalimentar. Todo cambio manda la <c>version_esperada</c> que se leyó y una <c>solicitud_id</c>: si otra persona cambió la calificación se avisa, se
/// vuelve a leer y se muestra el valor actual sin perder lo que se había escrito; si el cambio no llegó al nodo NO se da por hecho y se puede reintentar sin duplicarlo.
/// Se abre desde el libro con <c>calificacion-detalle?id=</c> (y, de adorno, <c>alumno</c> y <c>titulo</c> para el encabezado: la calificación sólo trae el identificador del alumno).
/// </summary>
[QueryProperty(nameof(CalificacionId), "id")]
[QueryProperty(nameof(Alumno), "alumno")]
[QueryProperty(nameof(Titulo), "titulo")]
public partial class CalificacionDetallePage : ContentPage
{
    private const double AnchoMaximo = 1280;

    public string CalificacionId { get; set; } = string.Empty;
    public string Alumno { get; set; } = string.Empty;
    public string Titulo { get; set; } = string.Empty;

    private readonly HojaDeOpciones _hoja = new();
    private readonly AvisoTemporal _aviso;
    // Un identificador de solicitud por clase de acción: tocar de nuevo la misma acción con lo mismo reutiliza la solicitud (reintento tras perder la señal).
    private readonly SolicitudReintentable _solReabrir = new(), _solPublicar = new(), _solRetirar = new(), _solValorar = new();
    private PanelDeAjuste? _ajuste;
    private PanelDeRetroalimentacion? _retro;
    private DetalleDeCalificacion? _detalle;
    private IReadOnlyList<TramoDeEscala> _tramos = [];
    private string? _versionDeTramos;
    private bool _visible, _cargando, _retroAbierta;
    private long _ultimaLectura;

    private static IGradebookApi Api => Sesion.Gradebook;
    private Calificacion Actual => _detalle!.Calificacion;

    public CalificacionDetallePage()
    {
        InitializeComponent();
        Raiz.Add(_hoja);
        _aviso = new AvisoTemporal(ResultadoHost);
        AccionesHost.Add(ExamenUi.Accion("‹  Volver", Ds.Rango.Secondary, () => Shell.Current.GoToAsync(".."), 150, "calificacion-volver").Vista);
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!CalificacionesUi.PuedeLeer)
            {
                // TST-069: sin acceso a datos académicos, se dice y no se llama al nodo.
                TituloLabel.Text = "Este rol no accede a datos académicos";
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.SinAcceso("Sin acceso", PermisosDeCalificaciones.SinAccesoAcademico(CalificacionesUi.Rol)));
                return;
            }
            if (_detalle is null)
            {
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.Estado("Leyendo la calificación…", "Un momento."));
            }
            await CargarAsync();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "CalificacionDetallePage.OnAppearing", ex); }
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

    private async Task CargarAsync()
    {
        if (string.IsNullOrWhiteSpace(CalificacionId) || _cargando) return;
        _cargando = true;
        try
        {
            var api = Api;
            var detalle = await api.CalificacionAsync(CalificacionesUi.Actor, CalificacionId);
            if (!_visible) return;
            if (detalle is null)
            {
                if (_detalle is not null)
                {
                    // Un tropiezo no borra lo que ya se ve.
                    ConexionHost.Clear();
                    ConexionHost.Add(CalificacionesUi.SinConexion(api)
                        ? ExamenUi.Aviso("Sin conexión con el nodo", $"Se muestra lo último que se leyó, a las {ExamenTexto.Hora(_ultimaLectura)}.", Tono.Ambar)
                        : ExamenUi.Aviso("No se pudo actualizar la calificación", CalificacionesUi.Error(api), Tono.Ambar));
                    return;
                }
                TituloLabel.Text = "No se pudo leer la calificación";
                SubtituloLabel.Text = string.Empty;
                ResumenHost.Clear();
                ResumenHost.Add(CalificacionesUi.Estado("No se pudo leer la calificación", CalificacionesUi.Error(api),
                    ExamenUi.Accion("Reintentar", Ds.Rango.Secondary, CalificacionesUi.Seguro(nameof(CalificacionDetallePage), "Reintentar", CargarAsync), 170, "calificacion-reintentar", margen: false).Vista));
                return;
            }
            ConexionHost.Clear();
            _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            _detalle = detalle;
            await CargarTramosAsync(detalle.Calificacion);
            if (!_visible) return;
            Pintar();
        }
        finally { _cargando = false; }
    }

    /// <summary>
    /// Los niveles de desempeño de la escala con la que se presentó la calificación, para ofrecer «Valorar el nivel de desempeño». <c>/configuracion/</c> no trae la definición de las escalas,
    /// así que se lee la escala por su cuenta (<see cref="LectorDeEscalas"/>). Si no se puede leer, la acción simplemente no se ofrece.
    /// </summary>
    private async Task CargarTramosAsync(Calificacion c)
    {
        if (!CalificacionesUi.PuedeCalificar || !c.EsEditable || c.Presentacion?.Escala is not { } escala)
        {
            _tramos = [];
            _versionDeTramos = null;
            return;
        }
        if (_versionDeTramos == escala.VersionId && _tramos.Count > 0) return;
        _tramos = await LectorDeEscalas.Actual.TramosAsync(CalificacionesUi.Actor, escala.EscalaId, escala.VersionId);
        _versionDeTramos = _tramos.Count > 0 ? escala.VersionId : null;
    }

    /// <summary>El nodo mandó una calificación nueva (tras un cambio o un conflicto): se actualiza lo que se ve, SIN tocar lo que el profesor tiene escrito en los paneles.</summary>
    private void AplicarCambio(CambioDeCalificacion r)
    {
        if (_detalle is null) return;
        _detalle = _detalle with { Calificacion = r.Calificacion, Historial = r.Historial };
        Pintar();
    }

    /// <summary>Vuelve a leer la calificación (tras un conflicto de versión). Devuelve si se pudo.</summary>
    private async Task<bool> RelerAsync()
    {
        var api = Api;
        var detalle = await api.CalificacionAsync(CalificacionesUi.Actor, CalificacionId);
        if (detalle is null || !_visible) return false;
        _detalle = detalle;
        _ultimaLectura = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        await CargarTramosAsync(detalle.Calificacion);
        if (_visible) Pintar();
        return true;
    }

    // ---------------------------------------------------------------------------------------------- pintar

    private void Pintar()
    {
        if (!_visible || _detalle is not { } d) return;          // la pantalla pudo cerrarse mientras el nodo contestaba
        var c = d.Calificacion;
        var y = Desplazable.ScrollY;

        TituloLabel.Text = string.IsNullOrWhiteSpace(Alumno) ? "Calificación" : Alumno;
        SubtituloLabel.Text = string.Join(" · ", new[] { string.IsNullOrWhiteSpace(Titulo) ? null : Titulo, $"Intento {c.NumeroIntento}" }.Where(x => x is not null));
        PastillasHost.Clear();
        PastillasHost.Add(CalificacionesUi.PildoraEnFila(TextoDeCalificaciones.Estado(c), TextoDeCalificaciones.MatizDeEstado(c), 14));
        PastillasHost.Add(CalificacionesUi.PildoraEnFila($"Versión {c.Version}", Matiz.Neutro, 14));
        if (c.Ajustada) PastillasHost.Add(CalificacionesUi.PildoraEnFila("Ajustada", Matiz.Info, 14));
        if (c.DesfaseConEvaluacion) PastillasHost.Add(CalificacionesUi.PildoraEnFila("La evaluación cambió después", Matiz.Ambar, 14));

        ResumenHost.Clear();
        ResumenHost.Add(Resumen(c));
        ResumenHost.Add(CuatroBloques(c));

        QueHacerHost.Clear();
        QueHacerHost.Add(QueHacer(c));

        // Los paneles con cajas de texto se crean una vez y se quedan donde están; sólo cambian sus valores y su visibilidad.
        var puedeCalificar = CalificacionesUi.PuedeCalificar;
        if (puedeCalificar && _ajuste is null)
        {
            _ajuste = new PanelDeAjuste(c, AjustarAsync);
            AjusteHost.Add(_ajuste);
        }
        if (puedeCalificar && _retro is null)
        {
            _retro = new PanelDeRetroalimentacion(c, RetroalimentarAsync);
            RetroHost.Add(_retro);
        }
        _ajuste?.Actualizar(c);
        if (_ajuste is not null) _ajuste.IsVisible = puedeCalificar && GradebookTexto.PuedeAjustar(c);
        _retro?.Actualizar(c);
        if (_retro is not null) _retro.IsVisible = puedeCalificar && _retroAbierta && c.Estado != EstadosDeCalificacion.Anulada;

        LecturaHost.Clear();
        LecturaHost.Add(Retroalimentacion(c));
        HistorialHost.Clear();
        HistorialHost.Add(Historial(d));

        if (y > 1)
            Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(40), async () =>
            {
                try { await Desplazable.ScrollToAsync(0, y, false); } catch { /* la pantalla pudo cambiar mientras tanto */ }
            });
    }

    // -------------------------------------------------------------------------------------------- resumen

    private View Resumen(Calificacion c)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Qué es esta calificación"));
        pila.Add(Ds.Secundario(TextoDeCalificaciones.EstadoExplicado(c), 15));
        if (c.DesfaseConEvaluacion)
            pila.Add(ExamenUi.Aviso("La evaluación cambió después de registrar esta calificación",
                "La puntuación de la evaluación ya no coincide con la que se tomó. No se pisa en silencio: revísala y, si hace falta, reabre para recalificar.", Tono.Ambar));
        if (c.Estado == EstadosDeCalificacion.Reabierta)
            pila.Add(ExamenUi.Aviso("Esta calificación está reabierta", "No cuenta mientras se recalifica. Termina la revisión y confírmala para volver a registrarla.", Tono.Ambar));

        pila.Add(ExamenUi.Dato("Estado", TextoDeCalificaciones.Estado(c)));
        pila.Add(ExamenUi.Dato("Versión", $"{c.Version} (cada cambio suma una)"));
        pila.Add(ExamenUi.Dato("Calificada por", TextoDeCalificaciones.EsDelSistema(c.EvaluadorId) ? "El sistema" : ExamenTexto.Persona(c.EvaluadorId)));
        pila.Add(ExamenUi.Dato("Cómo se calificó", $"{GradebookTexto.Origen(c.Origen)} · {TextoDeCalificaciones.Regla(c.ReglaPuntuacion)}"));
        pila.Add(ExamenUi.Dato("Intento", c.Aciertos is { } a && c.Preguntas is { } n ? $"Número {c.NumeroIntento} · {a} de {n} aciertos" : $"Número {c.NumeroIntento}"));
        // La nota en bruto, tal como la contó la evaluación: los puntos sobre el máximo y el porcentaje. Se lee junto a la presentada (los tres a la vez).
        if (GradebookTexto.Bruto(c.Bruto) is { Length: > 0 } bruto) pila.Add(ExamenUi.Dato("Puntos", bruto));
        pila.Add(ExamenUi.Dato("Registrada", GradebookTexto.Hora(c.RegistradaEn)));
        pila.Add(ExamenUi.Dato("Última vez que cambió", GradebookTexto.Hora(c.ActualizadaEn)));
        if (c.PublicadaEn is { } en) pila.Add(ExamenUi.Dato("Publicada", $"{GradebookTexto.Hora(en)}{(string.IsNullOrWhiteSpace(c.PublicadaPor) ? string.Empty : " por " + ExamenTexto.Persona(c.PublicadaPor))}"));
        return ExamenUi.Tarjeta(pila);
    }

    /// <summary>Cuatro cosas que no son la misma: lo que el sistema o el profesor puntuó (0–100), cómo lo presenta la escala, el nivel de desempeño y el criterio de aprobación.</summary>
    private View CuatroBloques(Calificacion c)
    {
        var p = c.Presentacion;
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ExamenUi.Seccion("Cuatro cosas distintas"));
        pila.Add(Ds.Secundario("El resultado interno es la base; la nota que ve el estudiante depende de la escala del nivel. No son lo mismo y aquí se ven por separado.", 14));
        var datos = new VerticalStackLayout { Spacing = 6 };
        datos.Add(ExamenUi.Dato("Puntuación original", GradebookTexto.Puntaje(c.PuntajeOriginal) + " (lo que se registró; no cambia jamás)", 220));
        datos.Add(ExamenUi.Dato("Puntuación efectiva", GradebookTexto.Puntaje(c.PuntajeEfectivo) + (c.Ajustada ? " · ajustada" : " · la misma que la original"), 220));
        pila.Add(datos);

        var fila = ExamenUi.Fila();
        fila.Add(CalificacionesUi.Bloque("Resultado interno (0–100)", GradebookTexto.Puntaje(c.PuntajeEfectivo),
            c.Ajustada ? $"Ajustado: el original fue {GradebookTexto.Puntaje(c.PuntajeOriginal)}" : "Tal como se registró", 280, "calificacion-bloque-interno"));
        fila.Add(CalificacionesUi.Bloque("Calificación presentada", GradebookTexto.Presentada(p),
            p is null ? "No hay presentación mientras la calificación esté reabierta o anulada"
            : (p.Provisional && !c.Publicada ? "Provisional: puede cambiar hasta que se publique. " : "Estampada al publicar. ") + (p.Escala is { } e ? $"Escala: {e.Nombre}" : string.Empty), 280, "calificacion-bloque-presentada"));
        fila.Add(CalificacionesUi.Bloque("Nivel de desempeño", TextoDeCalificaciones.Desempeno(p),
            p?.Desempeno.ValoradoPorElDocente == true
                ? (string.IsNullOrWhiteSpace(c.DesempenoMotivo) ? "Lo fijó el profesor con su criterio pedagógico" : $"Motivo: {c.DesempenoMotivo}")
                : "Sale de la escala del nivel", 280, "calificacion-bloque-desempeno"));
        fila.Add(CalificacionesUi.Bloque("Criterio de aprobación", GradebookTexto.Aprobacion(p?.Aprobacion),
            GradebookTexto.MinimoParaAprobar(_detalle?.Sistema) is { } minimo
                ? $"{minimo} (sistema: {GradebookTexto.Sistema(_detalle?.Sistema)}). Aprobar o promover lo decide la institución"
                : "Sólo el criterio de la escala: aprobar o promover lo decide la institución", 280, "calificacion-bloque-aprobacion"));
        pila.Add(fila);
        return ExamenUi.Tarjeta(pila);
    }

    // ---------------------------------------------------------------------------------- retroalimentación

    private View Retroalimentacion(Calificacion c)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Retroalimentación actual"));
        var hay = false;
        foreach (var (clave, rotulo) in TextoDeCalificaciones.ApartadosDeRetroalimentacion)
        {
            if (TextoDeCalificaciones.Retroalimentacion(c, clave) is not { } texto) continue;
            hay = true;
            pila.Add(ExamenUi.Dato(rotulo, texto, 220));
        }
        if (!string.IsNullOrWhiteSpace(c.Adaptacion)) { hay = true; pila.Add(ExamenUi.Dato("Ajuste razonable aplicado", c.Adaptacion!, 220)); }
        if (!hay) pila.Add(Ds.Secundario("Todavía no hay retroalimentación para el estudiante.", 15));
        return ExamenUi.Tarjeta(pila);
    }

    // ------------------------------------------------------------------------------------------- historial

    private View Historial(DetalleDeCalificacion d)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ExamenUi.Seccion("Historial de cambios"));
        pila.Add(Ds.Secundario("Cada cambio deja su rastro: qué era antes, qué es ahora, por qué, quién lo hizo y cuándo según el reloj del nodo. Lo más reciente está arriba.", 14));
        if (d.Historial.Count == 0) pila.Add(Ds.Secundario("Todavía no hay cambios registrados.", 15));
        foreach (var v in d.Historial.OrderByDescending(x => x.Numero))
        {
            var contenido = new VerticalStackLayout { Spacing = 3 };
            var linea = ExamenUi.Fila();
            linea.Add(ExamenUi.PildoraEnFila(GradebookTexto.TipoDeCambio(v.Tipo), Tono.Neutro, 13));
            if (TextoDeCalificaciones.Cambio(v) is { } cambio) linea.Add(new Label { Text = cambio, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center });
            contenido.Add(linea);
            if (!string.IsNullOrWhiteSpace(v.Motivo)) contenido.Add(Ds.Secundario($"Motivo: {v.Motivo}", 14));
            contenido.Add(Ds.Secundario($"{(TextoDeCalificaciones.EsDelSistema(v.ActorId) ? "El sistema" : ExamenTexto.Persona(v.ActorId))} · {GradebookTexto.Hora(v.En)} · cambio {v.Numero}", 13));
            pila.Add(CalificacionesUi.Fila(contenido, new Thickness(16, 10)));
        }
        return ExamenUi.Tarjeta(pila);
    }
}
