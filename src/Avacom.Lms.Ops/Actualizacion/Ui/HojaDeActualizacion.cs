using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Actualizacion.Ui;

/// <summary>
/// La hoja de las actualizaciones: se abre SOBRE la pantalla «Actualizaciones» (un velo tenue y una tarjeta en el tercio central de la ventana, de 1/6 a 5/6 de su alto) y lleva a la persona,
/// sin teclado, por cada acción que cambia el aula:
/// <list type="bullet">
/// <item><b>Programar</b> (CAP-108): atajos («Esta noche a las 22:00»), ± media hora y ± un día, y la duración de una lista cerrada → una sola confirmación.</item>
/// <item><b>Aplicar ahora</b> (CAP-105): qué cambia, cuánto tarda y que una clase abierta nunca se interrumpe → una sola confirmación.</item>
/// <item><b>Volver a la versión anterior</b> (CAP-107): elegir por qué de una lista cerrada (la nota que pide el nodo, sin escribir) → una sola confirmación.</item>
/// </list>
/// Toda la lógica vive en <see cref="FlujoDeActualizacion"/> y <see cref="SelectorDeVentana"/>; aquí sólo se pinta lo que dicen. Usar desde el hilo de la interfaz. Sólo Border, Label y
/// Button; todo lo que se toca mide 64 px.
/// </summary>
internal sealed class HojaDeActualizacion : ContentView
{
    private enum Modo { Ninguno, Programar, Aplicar, Revertir }

    private readonly Grid _raiz = new();
    private readonly Border _tarjeta;
    private readonly Label _eyebrow, _titulo, _subtitulo;
    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 10 };
    private readonly FlexLayout _pie = new()
    {
        Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.End,
        AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start,
    };

    private TaskCompletionSource<bool>? _cierre;
    private Modo _modo;
    private bool _cambio;
    private FlujoDeActualizacion? _flujo;
    private SelectorDeVentana? _selector;
    private MensajeDeActualizacion? _problema;

    public HojaDeActualizacion()
    {
        IsVisible = false;
        ZIndex = 50;
        // El velo es hermano de la tarjeta: un toque dentro de la tarjeta nunca llega a él. Tocar fuera NO cierra la hoja (nada de esto se cancela de un roce).
        var velo = new Border { BackgroundColor = Color.FromArgb("#73141417"), StrokeThickness = 0 };
        _eyebrow = ActualizacionUi.Eyebrow(string.Empty);
        _titulo = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-hoja-titulo" };
        _subtitulo = new Label { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-hoja-subtitulo" };
        var cabecera = new VerticalStackLayout { Spacing = 4, Margin = new Thickness(0, 0, 0, 12) };
        cabecera.Add(_eyebrow);
        cabecera.Add(_titulo);
        cabecera.Add(_subtitulo);
        var contenido = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)] };
        contenido.Add(cabecera, 0, 0);
        contenido.Add(new ScrollView { Content = _cuerpo }, 0, 1);
        contenido.Add(new Border { Padding = new Thickness(0, 14, 0, 0), StrokeThickness = 0, BackgroundColor = Colors.Transparent, Content = _pie }, 0, 2);
        _tarjeta = new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande },
            Padding = new Thickness(28, 24), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Content = contenido,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 12), Radius = 32, Opacity = 0.28f }, AutomationId = "actualizaciones-hoja",
        };
        _raiz.Add(velo);
        _raiz.Add(_tarjeta);
        _raiz.SizeChanged += (_, _) =>
        {
            if (_raiz.Width <= 0 || _raiz.Height <= 0) return;
            // La tarjeta en el tercio central: un tercio del ancho y de 1/6 a 5/6 del alto. El cuerpo se desplaza si no cabe; los botones quedan siempre a la vista.
            _tarjeta.WidthRequest = Math.Min(_raiz.Width, Math.Max(640, _raiz.Width / 3));
            _tarjeta.HeightRequest = Math.Min(_raiz.Height, Math.Max(600, _raiz.Height * 4 / 6));
        };
        Content = _raiz;
    }

    // =============================================================================================================== abrir y cerrar

    /// <summary>Programar una ventana. Devuelve si algo cambió en el nodo (para volver a leer).</summary>
    public Task<bool> ProgramarAsync(FlujoDeActualizacion flujo)
    {
        _flujo = flujo;
        _selector = flujo.NuevoSelector();
        return Abrir(Modo.Programar);
    }

    /// <summary>Aplicar ahora, con UNA confirmación.</summary>
    public Task<bool> AplicarAsync(FlujoDeActualizacion flujo)
    {
        _flujo = flujo;
        if (!flujo.PedirAplicar()) return Task.FromResult(false);
        return Abrir(Modo.Aplicar);
    }

    /// <summary>Volver a la versión anterior: elegir el motivo y UNA confirmación.</summary>
    public Task<bool> RevertirAsync(FlujoDeActualizacion flujo)
    {
        _flujo = flujo;
        if (!flujo.PedirRevertir()) return Task.FromResult(false);
        return Abrir(Modo.Revertir);
    }

    private Task<bool> Abrir(Modo modo)
    {
        Cerrar(cancelarFlujo: false);                 // la confirmación que se acaba de pedir (PedirAplicar, PedirRevertir) tiene que sobrevivir a abrir la hoja
        _modo = modo;
        _cambio = false;
        _problema = null;
        _cierre = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var tarea = _cierre.Task;
        IsVisible = true;
        Pintar();
        return tarea;
    }

    private void Cerrar(bool cancelarFlujo = true)
    {
        var cierre = Interlocked.Exchange(ref _cierre, null);
        if (cancelarFlujo) _flujo?.Cancelar();
        _modo = Modo.Ninguno;
        IsVisible = false;
        cierre?.TrySetResult(_cambio);
    }

    /// <summary>Si la pantalla se cierra con la hoja abierta, nadie se queda esperando.</summary>
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

    // =============================================================================================================== pintar

    private void Pintar()
    {
        _cuerpo.Clear();
        _pie.Clear();
        switch (_modo)
        {
            case Modo.Programar: PintarProgramar(); break;
            case Modo.Aplicar: PintarAplicar(); break;
            case Modo.Revertir: PintarRevertir(); break;
        }
    }

    private void Boton(string texto, Ds.Rango rango, Func<Task> alPulsar, string id, bool activo = true)
    {
        var (boton, vista) = ActualizacionUi.Accion(texto, rango, ActualizacionUi.Seguro($"Hoja.{id}", alPulsar), id);
        if (!activo) Ds.Habilitar(boton, false);
        _pie.Add(vista);
    }

    private void BotonCancelar() => Boton("Cancelar", Ds.Rango.Quiet, () => { Cerrar(); return Task.CompletedTask; }, "actualizaciones-cancelar");

    private void PintarProblema()
    {
        if (_problema is null) return;
        _cuerpo.Add(ActualizacionUi.Aviso(_problema, true, "actualizaciones-hoja-problema"));
    }

    /// <summary>Un botón dentro del cuerpo (no del pie): se parte en filas.</summary>
    private static (Button Boton, View Vista) Mini(string texto, Ds.Rango rango, Func<Task> alPulsar, string id, double? ancho = null) =>
        ActualizacionUi.Accion(texto, rango, ActualizacionUi.Seguro($"Hoja.{id}", alPulsar), id, ancho);

    // ---------------------------------------------------------------------------------------------------- programar

    private void PintarProgramar()
    {
        var f = _flujo!;
        var s = _selector!;
        _eyebrow.Text = "PROGRAMAR";
        _titulo.Text = "¿Cuándo se aplica?";
        _subtitulo.Text = f.Elegida is { } e ? $"«{e.Nombre}»" : string.Empty;     // que no haya una clase abierta a esa hora lo dice el pie de la pantalla y lo comprueba el nodo

        PintarProblema();
        _cuerpo.Add(new Label { Text = s.Resumen, FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-ventana-resumen" });

        var atajos = ExamenUi.Fila();
        var i = 0;
        foreach (var atajo in s.Atajos())
        {
            var elegido = s.Inicio == atajo.InicioMs;
            var inicio = atajo.InicioMs;
            atajos.Add(Mini(atajo.Titulo, elegido ? Ds.Rango.Primary : Ds.Rango.Secondary, () => { s.Elegir(inicio); Pintar(); return Task.CompletedTask; }, $"actualizaciones-atajo-{i++}").Vista);
        }
        _cuerpo.Add(atajos);

        _cuerpo.Add(ActualizacionUi.Eyebrow("AJUSTAR LA HORA"));
        var hora = ExamenUi.Fila();
        hora.Add(Mini("‹ 30 min", Ds.Rango.Secondary, () => { s.MenosMediaHora(); Pintar(); return Task.CompletedTask; }, "actualizaciones-menos-media", 112).Vista);
        hora.Add(Mini("30 min ›", Ds.Rango.Secondary, () => { s.MasMediaHora(); Pintar(); return Task.CompletedTask; }, "actualizaciones-mas-media", 112).Vista);
        hora.Add(Mini("‹ 1 día", Ds.Rango.Secondary, () => { s.MenosUnDia(); Pintar(); return Task.CompletedTask; }, "actualizaciones-menos-dia", 112).Vista);
        hora.Add(Mini("1 día ›", Ds.Rango.Secondary, () => { s.MasUnDia(); Pintar(); return Task.CompletedTask; }, "actualizaciones-mas-dia", 112).Vista);
        _cuerpo.Add(hora);

        _cuerpo.Add(ActualizacionUi.Eyebrow("CUÁNTO TIEMPO SE RESERVA"));
        var duraciones = ExamenUi.Fila();
        foreach (var minutos in SelectorDeVentana.Duraciones)
        {
            var m = minutos;
            duraciones.Add(Mini(m < 60 ? $"{m} min" : m % 60 == 0 ? $"{m / 60} h" : $"{m} min", s.DuracionMin == m ? Ds.Rango.Primary : Ds.Rango.Secondary,
                () => { s.ElegirDuracion(m); Pintar(); return Task.CompletedTask; }, $"actualizaciones-duracion-{m}", 110).Vista);
        }
        _cuerpo.Add(duraciones);

        Boton("Programar", Ds.Rango.Primary, ConfirmarProgramarAsync, "actualizaciones-confirmar-programar", s.EsValida);
        BotonCancelar();
    }

    private async Task ConfirmarProgramarAsync()
    {
        var f = _flujo!;
        if (await f.ProgramarAsync(_selector!))
        {
            _cambio = true;
            Cerrar();
            return;
        }
        _problema = f.Mensaje;
        if (_modo == Modo.Programar) Pintar();
    }

    // ---------------------------------------------------------------------------------------------------- aplicar

    private void PintarAplicar()
    {
        var f = _flujo!;
        var e = f.Elegida!;
        _eyebrow.Text = "APLICAR AHORA";
        _titulo.Text = "¿Aplicar esta actualización?";
        _subtitulo.Text = $"«{e.Nombre}»";
        PintarProblema();
        var pila = new VerticalStackLayout { Spacing = 8 };
        pila.Add(ActualizacionUi.Dato("Qué cambia", ActualizacionTexto.ModulosQueCambia(e), 140));
        foreach (var m in e.ModulosDelManifiesto) pila.Add(Ds.Secundario("· " + ActualizacionTexto.LineaDeModulo(m), 14));
        pila.Add(ActualizacionUi.Dato("Peso", ActualizacionTexto.Peso(e.Bytes), 140));
        pila.Add(ActualizacionUi.Dato("Espacio", ActualizacionTexto.Espacio(e, f.Estado), 140));
        _cuerpo.Add(pila);
        _cuerpo.Add(Ds.Separador());
        _cuerpo.Add(new Label
        {
            Text = "El aula se detiene unos minutos y vuelve sola. Mientras tanto no se inician clases nuevas; las que ya estén abiertas siguen. Antes de empezar, el aula guarda una copia de sus datos y, si algo sale mal, vuelve sola a la versión anterior.",
            FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-aplicar-aviso",
        });
        _cuerpo.Add(Ds.Secundario("Si hay una clase abierta, la actualización no se aplica y te lo dice.", 14));
        Boton("Aplicar ahora", Ds.Rango.Primary, ConfirmarAsync, "actualizaciones-confirmar-aplicar");
        BotonCancelar();
    }

    // ---------------------------------------------------------------------------------------------------- revertir

    private void PintarRevertir()
    {
        var f = _flujo!;
        var e = f.Elegida!;
        _eyebrow.Text = "VOLVER A LA VERSIÓN ANTERIOR";
        _titulo.Text = "¿Por qué quieres volver atrás?";
        _subtitulo.Text = $"«{e.Nombre}». Queda anotado en el historial del aula.";
        PintarProblema();
        foreach (var motivo in ActualizacionTexto.MotivosDeReversion)
        {
            var m = motivo;
            var elegido = f.MotivoElegido?.Codigo == m.Codigo;
            var contenido = new Label { Text = (elegido ? "✓  " : string.Empty) + m.Titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center };
            _cuerpo.Add(ActualizacionUi.Tocable(contenido, ActualizacionUi.Seguro($"Hoja.motivo-{m.Codigo}", () => { f.ElegirMotivo(m); Pintar(); return Task.CompletedTask; }),
                m.Titulo, $"actualizaciones-motivo-{m.Codigo}", elegido));
        }
        _cuerpo.Add(Ds.Secundario("El aula se detiene unos minutos y vuelve sola. No se inician clases nuevas mientras tanto; las abiertas siguen.", 14));
        Boton("Volver a la versión anterior", Ds.Rango.Primary, ConfirmarAsync, "actualizaciones-confirmar-revertir", f.PuedeConfirmar);
        BotonCancelar();
    }

    private async Task ConfirmarAsync()
    {
        var f = _flujo!;
        if (!f.PuedeConfirmar) return;
        if (await f.ConfirmarAsync())
        {
            _cambio = true;
            Cerrar();
            return;
        }
        // El nodo no lo aceptó (una clase abierta, el espacio…): la hoja se cierra y la pantalla dice el motivo (flujo.Mensaje) sobre el paquete, que sigue como estaba. El nodo pudo cambiar
        // algo mientras tanto (un rechazo deja su fila en el historial): la pantalla vuelve a leer.
        _cambio = true;
        Cerrar();
    }
}
