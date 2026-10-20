using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Gradebook;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Calificaciones.Ui;

/// <summary>
/// «Editar la calificación» sin salir del libro ni del boletín (la edición que pidió el CTO, 2026-10-19): una hoja sobre la pantalla —un velo y una tarjeta en el tercio central— con
/// lo que ya hace el detalle de una calificación: la puntuación original y la efectiva, el teclado numérico táctil, el motivo en frases y «Confirmar ajuste». Cada ajuste va al nodo
/// con su <c>version_esperada</c> y su <c>solicitud_id</c>; el nodo lo deja en el historial y en la bitácora con quién lo hizo y cuándo (reloj del nodo). Editar aquí es EXACTAMENTE
/// lo mismo que editar desde el detalle: la hoja sólo ahorra el viaje.
///
/// Se abre con <see cref="MostrarAsync"/> y devuelve si hubo algún ajuste confirmado (para que la pantalla vuelva a leer). Cerrar sin confirmar no cambia nada. Una llamada mientras
/// hay otra abierta la cierra primero.
/// </summary>
internal sealed class HojaDeAjuste : ContentView
{
    private readonly Grid _raiz = new();
    private readonly Border _tarjeta;
    private readonly Label _titulo, _subtitulo;
    private readonly ScrollView _desplazable;
    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 12 };
    private readonly ContentView _cerrarHost = new();
    private TaskCompletionSource<bool>? _cierre;
    private PanelDeAjuste? _panel;
    private DetalleDeCalificacion? _detalle;
    private bool _ajustado;
    private int _version;

    private static IGradebookApi Api => Sesion.Gradebook;

    public HojaDeAjuste()
    {
        IsVisible = false;
        ZIndex = 60;
        // El velo es hermano de la tarjeta: un toque dentro nunca llega aquí. Tocar fuera NO cierra la hoja: un ajuste a medio escribir no se pierde de un roce.
        var velo = new Border { BackgroundColor = Color.FromArgb("#73141417"), StrokeThickness = 0 };
        _titulo = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        _subtitulo = new Label { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap };
        _desplazable = new ScrollView { Content = _cuerpo };
        var cabecera = new VerticalStackLayout { Spacing = 2, Margin = new Thickness(0, 0, 0, 10) };
        cabecera.Add(_titulo);
        cabecera.Add(_subtitulo);
        var contenido = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)] };
        contenido.Add(cabecera, 0, 0);
        contenido.Add(_desplazable, 0, 1);
        contenido.Add(_cerrarHost, 0, 2);
        _tarjeta = new Border
        {
            BackgroundColor = Ds.SuperficieContenido, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande },
            Padding = new Thickness(28, 24), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Content = contenido,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 12), Radius = 32, Opacity = 0.28f }, AutomationId = "ajuste-hoja",
        };
        _raiz.Add(velo);
        _raiz.Add(_tarjeta);
        _raiz.SizeChanged += OnRaizSizeChanged;
        Content = _raiz;
    }

    /// <summary>La tarjeta en el tercio central (el teclado numérico y las frases piden algo más de ancho que una hoja de opciones): de 1/6 a 5/6 del alto.</summary>
    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (_raiz.Width <= 0 || _raiz.Height <= 0) return;
        _tarjeta.WidthRequest = Math.Min(_raiz.Width, Math.Max(820, _raiz.Width / 2));
        _tarjeta.HeightRequest = Math.Min(_raiz.Height, Math.Max(560, _raiz.Height * 4 / 6));
    }

    /// <summary>Abre la hoja sobre la calificación y espera a que se cierre. Devuelve si se confirmó al menos un ajuste.</summary>
    public async Task<bool> MostrarAsync(string calificacionId, string alumno, string evaluacion)
    {
        Cerrar();
        var version = ++_version;
        _cierre = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        _ajustado = false;
        _detalle = null;
        _panel = null;
        _titulo.Text = string.IsNullOrWhiteSpace(alumno) ? "Editar la calificación" : $"Editar la calificación de {alumno}";
        _subtitulo.Text = evaluacion;
        _cuerpo.Clear();
        _cuerpo.Add(Ds.Secundario("Leyendo la calificación…", 15));
        PintarCierre();
        IsVisible = true;
        var tarea = _cierre.Task;
        var api = Api;
        var detalle = await api.CalificacionAsync(CalificacionesUi.Actor, calificacionId);
        if (version != _version) return await tarea;
        _cuerpo.Clear();
        if (detalle is null)
        {
            _cuerpo.Add(ExamenUi.Aviso("No se pudo leer la calificación", CalificacionesUi.Error(api), Tono.Ambar));
            return await tarea;
        }
        _detalle = detalle;
        var c = detalle.Calificacion;
        if (!GradebookTexto.PuedeAjustar(c))
        {
            _cuerpo.Add(ExamenUi.Aviso("Esta calificación no se puede ajustar ahora", TextoDeCalificaciones.EstadoExplicado(c), Tono.Info));
            return await tarea;
        }
        var lectura = ExamenUi.Fila();
        lectura.Add(CalificacionesUi.PildoraEnFila(TextoDeCalificaciones.Estado(c), TextoDeCalificaciones.MatizDeEstado(c), 13));
        if (GradebookTexto.Bruto(c.Bruto) is { Length: > 0 } bruto) lectura.Add(ExamenUi.PildoraEnFila(bruto, Tono.Neutro, 13));
        if (c.Presentacion is { } p) lectura.Add(ExamenUi.PildoraEnFila($"Presentada: {GradebookTexto.Presentada(p)}{(p.Desempeno.Nivel is { Length: > 0 } n ? " · " + n : string.Empty)}", Tono.Info, 13));
        _cuerpo.Add(lectura);
        _cuerpo.Add(Ds.Secundario("El ajuste queda en el historial con tu nombre, la hora del nodo y el motivo, y en la bitácora del aula. La puntuación original no cambia jamás.", 13));
        _panel = new PanelDeAjuste(c, AjustarAsync);
        _cuerpo.Add(_panel);
        return await tarea;
    }

    private void PintarCierre()
    {
        var boton = Ds.Boton(_ajustado ? "Listo" : "Cerrar sin cambiar", _ajustado ? Ds.Rango.Primary : Ds.Rango.Quiet, (_, _) => Cerrar(), 56);
        boton.AutomationId = "ajuste-hoja-cerrar";
        boton.HorizontalOptions = LayoutOptions.End;
        _cerrarHost.Content = boton;
    }

    private async Task<RespuestaDeAjuste> AjustarAsync(PeticionDeAjuste p)
    {
        if (_detalle is null) return new RespuestaDeAjuste(ResultadoDeAjuste.Rechazado, "No hay calificación que ajustar.");
        var api = Api;
        var antes = _detalle.Calificacion.PuntajeEfectivo;
        var r = await api.AjustarAsync(CalificacionesUi.Actor, _detalle.Calificacion.Id, p.Puntaje, p.Motivo, p.VersionEsperada, p.SolicitudId);
        if (r is not null)
        {
            _detalle = _detalle with { Calificacion = r.Calificacion, Historial = r.Historial };
            _panel?.Actualizar(r.Calificacion);
            _ajustado = true;
            PintarCierre();
            var c = r.Calificacion;
            return new RespuestaDeAjuste(ResultadoDeAjuste.Confirmado, r.Reintento
                ? $"El ajuste ya estaba registrado: no se duplicó (versión {c.Version})."
                : $"Ajuste registrado: de {GradebookTexto.Puntaje(antes)} a {GradebookTexto.Puntaje(c.PuntajeEfectivo)}, versión {c.Version}. Quedó en el historial y en la bitácora con tu nombre.");
        }
        var error = api.UltimoError;
        var mensaje = CalificacionesUi.Error(api);
        if (GradebookTexto.EsConflictoDeVersion(error))
        {
            var releida = await api.CalificacionAsync(CalificacionesUi.Actor, _detalle.Calificacion.Id);
            if (releida is not null)
            {
                _detalle = releida;
                _panel?.Actualizar(releida.Calificacion);
                return new RespuestaDeAjuste(ResultadoDeAjuste.Conflicto, $"{mensaje} El valor actual es {GradebookTexto.Puntaje(releida.Calificacion.PuntajeEfectivo)} (versión {releida.Calificacion.Version}). Lo que escribiste se conserva: revísalo y confirma de nuevo.");
            }
            return new RespuestaDeAjuste(ResultadoDeAjuste.Conflicto, $"{mensaje} No se pudo volver a leer el valor actual: cierra y vuelve a abrir.");
        }
        return new RespuestaDeAjuste(GradebookTexto.SinConexion(error) ? ResultadoDeAjuste.SinConexion : ResultadoDeAjuste.Rechazado, mensaje);
    }

    private void Cerrar()
    {
        var cierre = Interlocked.Exchange(ref _cierre, null);
        _version++;
        IsVisible = false;
        cierre?.TrySetResult(_ajustado);
    }

    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName == nameof(IsVisible) && !IsVisible && _cierre is not null) Cerrar();
    }

    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is null && _cierre is not null) Cerrar();
    }
}
