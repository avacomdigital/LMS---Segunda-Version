using System.Diagnostics;
using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Controls;

/// <summary>
/// El avance vivo del grupo en una actividad lanzada (007-05 · PAN-004 · CAP-043 · FUN-072). Overlay sobre la clase (P3), sólo para el
/// profesor. El host lo usa así: <see cref="Configurar"/> al abrirlo (pinta ya lo que trae la <see cref="DistribucionAula"/>: avance,
/// cronómetro, rótulo y total de preguntas), <see cref="RefrescarAsync"/> cada vez que el canal en vivo avisa de un cambio en
/// «resultados», «entregas» o «distribucion», y <see cref="Detener"/> al ocultarlo. El panel NO sondea por su cuenta: lo único
/// que corre solo es el repintado LOCAL del cronómetro (dos veces por segundo, sólo mientras esté visible y en curso), calculado
/// con lo que el nodo dijo (<c>RestanteMs</c> a la hora de <c>ServidorEn</c>) más el tiempo transcurrido desde que llegó, medido con un
/// reloj monotónico: ninguna hora del aparato decide nada (BR-062).
///
/// Contenido: cronómetro por estado (en curso · detenido · terminó con gracia · terminó; sin rojo ni parpadeo), totales en letra grande,
/// promedio sólo con datos suficientes (CMP-043), y una fila por alumno con nombre, avance «n/N», nota provisional o «—», estado en texto
/// y la marca «Necesita atención» si va rezagado (nunca sólo color). Las filas ya llegan ordenadas con quien necesita atención primero y
/// se conservan entre refrescos (no se rehacen). Un envío tardío «por decidir» lleva «Aceptar» y «Descartar» (DEC-019).
/// El panel no trae botón de cerrar: mostrarlo y ocultarlo (<c>IsVisible</c>) es cosa de la página que lo aloja, que puede poner el suyo
/// en la franja libre de la parte de arriba (78 pt sin tarjeta, con el velo debajo).
/// Con <see cref="OcultarNombres"/> el panel puede proyectarse al grupo sin exponer a nadie. Si la red falla, conserva lo último pintado
/// y lo dice en una línea discreta. Usar desde el hilo de interfaz (los métodos que esperan devuelven el control a él).
/// </summary>
public partial class ResultadosActividadPanel : ContentView
{
    /// <summary>Cuando el aula proyecta este panel al grupo: muestra «Alumno 1, 2…» en lugar de los nombres (la numeración es estable mientras dure la actividad).</summary>
    public static readonly BindableProperty OcultarNombresProperty = BindableProperty.Create(
        nameof(OcultarNombres), typeof(bool), typeof(ResultadosActividadPanel), false,
        propertyChanged: (b, _, _) => ((ResultadosActividadPanel)b).PintarFilas());

    public bool OcultarNombres { get => (bool)GetValue(OcultarNombresProperty); set => SetValue(OcultarNombresProperty, value); }

    private static readonly Color Neutro = Color.FromArgb("#F4F4F5"), GrisTerminado = Color.FromArgb("#E4E4E7"), GrisPista = Color.FromArgb("#E4E4E7"), GrisSinEmpezar = Color.FromArgb("#A1A1AA");

    // Los pinceles de las filas se comparten: asignar uno nuevo en cada refresco repintaría 100 bordes sin que nada cambiara.
    private static readonly Brush FiloFila = new SolidColorBrush(Ds.Filo), FiloRezagado = new SolidColorBrush(Ds.Alerta), FiloPendiente = new SolidColorBrush(Ds.Info);

    /// <summary>Franja superior sin tarjeta (el velo sigue debajo): sitio para el botón de cerrar que pone la página anfitriona.</summary>
    private const double TopLibre = 78;

    private string _sesionId = string.Empty, _actor = string.Empty;
    private DistribucionAula? _actividad;
    private ResultadosActividadAula? _resultados;
    private CronometroAula? _crono;
    private long _cronoRecibidoEn;                       // Stopwatch.GetTimestamp() del momento en que llegó el cronómetro
    private bool _errorDeRed, _errorOtro;
    private string? _avisoDecision;
    private int _generacion;
    private CancellationTokenSource _cts = new();
    private Task? _enCurso;
    private bool _repetir;
    private IDispatcherTimer? _reloj;
    private readonly Dictionary<string, FilaVista> _filas = [];
    private readonly Dictionary<string, int> _anonimos = [];

    public ResultadosActividadPanel()
    {
        InitializeComponent();
        Tarjeta.Margin = new Thickness(0, TopLibre, 0, 32);
        PintarCronometro();
    }

    // ------------------------------------------------------------------ API pública

    /// <summary>
    /// Guarda a qué actividad sigue el panel y pinta lo que ya trae la <see cref="DistribucionAula"/> (avance, cronómetro, rótulo, total de
    /// preguntas). Descarta lo de la actividad anterior y cancela cualquier refresco en vuelo. No pide nada a la red: eso lo hace
    /// <see cref="RefrescarAsync"/>.
    /// </summary>
    public void Configurar(string sesionId, string actor, DistribucionAula actividad)
    {
        ArgumentNullException.ThrowIfNull(actividad);
        Liberar();
        _sesionId = sesionId;
        _actor = actor;
        _actividad = actividad;
        _crono = actividad.Cronometro;
        _cronoRecibidoEn = Stopwatch.GetTimestamp();
        PintarTodo();
        AjustarReloj();
    }

    /// <summary>
    /// Pide los resultados al aula y repinta. El host lo llama al recibir un aviso de cambio; varias llamadas seguidas se funden en una
    /// (mientras hay un refresco en vuelo, las nuevas sólo piden repetirlo una vez al terminar). Si falla la red conserva lo último
    /// pintado y lo indica en una línea discreta. Cancelar <paramref name="ct"/> no deja ningún mensaje.
    /// </summary>
    public Task RefrescarAsync(CancellationToken ct = default)
    {
        if (_actividad is null) return Task.CompletedTask;
        if (_enCurso is { IsCompleted: false })
        {
            _repetir = true;
            return _enCurso;
        }
        _enCurso = RefrescarEnSerieAsync(ct);
        return _enCurso;
    }

    /// <summary>
    /// Para el cronómetro local, cancela lo que esté en vuelo y libera las filas y los resultados (el host lo llama al ocultar el panel).
    /// Conserva a qué actividad seguía: si el host lo vuelve a mostrar, <see cref="RefrescarAsync"/> lo repinta todo desde el aula.
    /// </summary>
    public void Detener()
    {
        Liberar();
        PintarTodo();
        AjustarReloj();
    }

    // ------------------------------------------------------------------ ciclo de vida

    /// <summary>Ocultar el panel para el reloj; mostrarlo lo pone al día (el tiempo siguió corriendo mientras estaba oculto).</summary>
    protected override void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        base.OnPropertyChanged(propertyName);
        if (propertyName != nameof(IsVisible)) return;
        if (IsVisible) PintarCronometro();
        AjustarReloj();
    }

    protected override void OnHandlerChanging(HandlerChangingEventArgs args)
    {
        base.OnHandlerChanging(args);
        if (args.NewHandler is null)
        {
            // La pantalla se cierra: que el panel no deje un reloj ni una petición vivos.
            Liberar();
            if (_reloj is not null) { _reloj.Stop(); _reloj.Tick -= OnRelojTick; _reloj = null; }
        }
    }

    protected override void OnHandlerChanged()
    {
        base.OnHandlerChanged();
        AjustarReloj();
    }

    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (Raiz.Width <= 0 || Raiz.Height <= 0) return;
        // Arriba queda una franja libre (TopLibre): ahí la página pone su botón para volver a la clase, sin tapar la tarjeta.
        Tarjeta.WidthRequest = Math.Min(1280, Math.Max(640, Raiz.Width - 64));
        Tarjeta.HeightRequest = Math.Max(420, Raiz.Height - TopLibre - 32);
    }

    /// <summary>Cancela lo que esté en vuelo y suelta lo pintado (filas, resultados, avisos). No toca a qué actividad sigue el panel.</summary>
    private void Liberar()
    {
        _generacion++;
        _cts.Cancel();
        _cts.Dispose();
        _cts = new CancellationTokenSource();
        _repetir = false;
        _resultados = null;
        _crono = null;
        _errorDeRed = _errorOtro = false;
        _avisoDecision = null;
        _filas.Clear();
        _anonimos.Clear();
        ListaHost?.Clear();
        _reloj?.Stop();
    }

    // ------------------------------------------------------------------ refresco

    private async Task RefrescarEnSerieAsync(CancellationToken ct)
    {
        do
        {
            _repetir = false;
            await UnRefrescoAsync(ct);
        }
        while (_repetir && !ct.IsCancellationRequested);
    }

    private async Task UnRefrescoAsync(CancellationToken ct)
    {
        var actividad = _actividad;
        if (actividad is null) return;
        var sesionId = _sesionId;
        var actor = _actor;
        var generacion = _generacion;
        using var union = CancellationTokenSource.CreateLinkedTokenSource(ct, _cts.Token);
        var api = Sesion.Aula;

        ResultadosActividadAula? resultados;
        try { resultados = await api.ResultadosAsync(sesionId, actor, actividad.Id, union.Token); }
        catch (OperationCanceledException) { return; }
        // El cliente convierte una cancelación en «sin respuesta»: si fuimos nosotros, no hay nada que decir.
        if (union.IsCancellationRequested) return;
        var error = resultados is null ? api.UltimoError : null;

        void Aplicar()
        {
            // Si mientras esperaba el panel cambió de actividad o se detuvo, lo que llegó ya no vale.
            if (generacion != _generacion || _actividad?.Id != actividad.Id) return;
            if (resultados is not null)
            {
                _resultados = resultados;
                _errorDeRed = _errorOtro = false;
                _crono = resultados.Cronometro;
                _cronoRecibidoEn = Stopwatch.GetTimestamp();
                PintarTodo();
                AjustarReloj();
            }
            else
            {
                // Se conserva lo último pintado; sólo cambia la línea de estado.
                _errorDeRed = error is null || error.Estado == 0 || error.Codigo == "sin_conexion";
                _errorOtro = !_errorDeRed;
                PintarAviso();
            }
        }
        if (MainThread.IsMainThread) Aplicar();
        else await MainThread.InvokeOnMainThreadAsync(Aplicar);
    }

    // ------------------------------------------------------------------ pintado general

    private void PintarTodo()
    {
        PintarCabecera();
        PintarCronometro();
        PintarTotales();
        PintarFilas();
        PintarAviso();
    }

    private void PintarCabecera()
    {
        var a = _actividad;
        RotuloLabel.Text = a is null ? "Actividad" : a.Rotulo is { Length: > 0 } r ? r : a.ObjetoRef ?? "Actividad";
        var partes = new List<string>();
        if (a is { TotalPreguntas: > 0 }) partes.Add(a.TotalPreguntas == 1 ? "1 pregunta" : $"{a.TotalPreguntas} preguntas");
        if (a is not null && !string.IsNullOrEmpty(a.ReglasTexto)) partes.Add(a.ReglasTexto);
        SubtituloLabel.Text = string.Join(" · ", partes);
        SubtituloLabel.IsVisible = partes.Count > 0;
    }

    /// <summary>Totales en una línea legible a 4 m; el promedio, sólo si el aula dice que hay datos suficientes (CMP-043).</summary>
    private void PintarTotales()
    {
        int destinatarios, entregaron, respondiendo, sinEmpezar, porDecidir;
        if (_resultados is { } r)
            (destinatarios, entregaron, respondiendo, sinEmpezar, porDecidir) =
                (r.Totales.Destinatarios, r.Totales.Entregaron, r.Totales.Respondiendo, r.Totales.SinEmpezar, r.Totales.PorDecidir);
        else if (_actividad?.Avance is { } av)
            (destinatarios, entregaron, respondiendo, sinEmpezar, porDecidir) = (av.Destinatarios, av.Entregaron, av.Respondiendo, av.SinEmpezar, av.PorDecidir);
        else
        {
            TotalesLabel.IsVisible = false;
            PromedioLabel.IsVisible = false;
            return;
        }
        var texto = $"{entregaron} de {destinatarios} entregaron · {respondiendo} respondiendo · {sinEmpezar} sin empezar";
        if (porDecidir > 0) texto += $" · {porDecidir} por decidir";
        TotalesLabel.Text = texto;
        TotalesLabel.IsVisible = true;

        // Antes del primer refresco sólo hay avance: no se afirma nada del promedio.
        PromedioLabel.IsVisible = _resultados is not null;
        if (_resultados is { } rr)
            PromedioLabel.Text = rr.Totales is { DatosSuficientes: true, PromedioPorcentaje: { } promedio }
                ? $"Promedio {Porcentaje(promedio)}"
                : "Faltan entregas para calcular el promedio (mínimo 3)";
    }

    private void PintarAviso()
    {
        var texto = _avisoDecision
            ?? (_errorDeRed ? "Sin conexión con el aula · se actualizará solo"
                : _errorOtro ? "No se pudo actualizar el avance · se intentará de nuevo" : null);
        AvisoLabel.IsVisible = texto is not null;
        AvisoLabel.Text = texto ?? string.Empty;
    }

    // ------------------------------------------------------------------ cronómetro (CMP-003)

    private double TranscurridoLocalMs => Stopwatch.GetElapsedTime(_cronoRecibidoEn).TotalMilliseconds;

    /// <summary>Lo que queda según el nodo menos lo que pasó desde que lo dijo. Sólo cuenta en «en_curso»; los demás estados no corren.</summary>
    private double RestanteLocalMs => _crono is { Estado: "en_curso" } c ? c.RestanteMs - TranscurridoLocalMs : _crono?.RestanteMs ?? 0;

    /// <summary>
    /// Los cuatro estados en texto, sin rojo ni animación de alarma: el fondo sólo acompaña. Si el tiempo local llega a cero antes de que el
    /// aula avise, se muestra «terminó con gracia» (lo mismo que dirá el aula en cuanto se le pregunte) sin inventar el paso a «terminó».
    /// </summary>
    private void PintarCronometro()
    {
        if (_crono is null) { CronoPildora.IsVisible = false; return; }
        var estado = _crono.Estado;
        var restante = RestanteLocalMs;
        if (estado == "en_curso" && restante <= 0) estado = "vencido_con_gracia";

        string texto;
        string? detalle = null;
        Color fondo;
        switch (estado)
        {
            case "en_curso": texto = $"Quedan {Reloj(restante)}"; fondo = Neutro; break;
            case "congelado": texto = "Tiempo detenido"; detalle = $"Quedaban {Reloj(restante)}"; fondo = Ds.InfoSuave; break;
            case "vencido_con_gracia": texto = "Terminó el tiempo · todavía se recibe lo capturado"; fondo = Ds.AlertaSuave; break;
            case "vencido": texto = "Terminó el tiempo"; fondo = GrisTerminado; break;
            default: CronoPildora.IsVisible = false; return;
        }
        CronoPildora.IsVisible = true;
        CronoPildora.BackgroundColor = fondo;
        CronoLabel.Text = texto;
        CronoDetalleLabel.Text = detalle ?? string.Empty;
        CronoDetalleLabel.IsVisible = detalle is not null;
        SemanticProperties.SetDescription(CronoPildora, detalle is null ? texto : $"{texto}. {detalle}");
    }

    private static string Reloj(double ms)
    {
        var s = (int)Math.Ceiling(Math.Max(0, ms) / 1000.0);
        return $"{s / 60:00}:{s % 60:00}";
    }

    /// <summary>El reloj local corre sólo si el panel se ve, está en pantalla y el cronómetro está en curso con tiempo por delante.</summary>
    private void AjustarReloj()
    {
        var debeCorrer = IsVisible && Handler is not null && _crono is { Estado: "en_curso" } && RestanteLocalMs > 0;
        if (!debeCorrer) { _reloj?.Stop(); return; }
        if (_reloj is null)
        {
            var despachador = Dispatcher ?? Application.Current?.Dispatcher;
            _reloj = despachador?.CreateTimer();
            if (_reloj is null) return;
            _reloj.Interval = TimeSpan.FromMilliseconds(500);
            _reloj.Tick += OnRelojTick;
        }
        if (!_reloj.IsRunning) _reloj.Start();
    }

    private void OnRelojTick(object? sender, EventArgs e)
    {
        PintarCronometro();
        AjustarReloj();      // al llegar a cero se detiene solo
    }

    // ------------------------------------------------------------------ filas

    /// <summary>
    /// Actualiza las filas en su sitio: cada alumno conserva su vista entre refrescos (con 100 filas y avisos cada pocos segundos no se
    /// rehace nada) y sólo se reordena la lista cuando el orden que manda el aula cambió.
    /// </summary>
    private void PintarFilas()
    {
        if (ListaHost is null) return;
        var filas = _resultados?.Filas ?? [];
        var vistos = new HashSet<string>();
        var orden = new List<FilaVista>(filas.Count);
        foreach (var f in filas)
        {
            if (!vistos.Add(f.ParticipanteId)) continue;
            if (!_filas.TryGetValue(f.ParticipanteId, out var vista))
                _filas[f.ParticipanteId] = vista = CrearFila();
            PintarFila(vista, f);
            orden.Add(vista);
        }
        foreach (var id in _filas.Keys.Where(k => !vistos.Contains(k)).ToList()) _filas.Remove(id);

        var hijos = ListaHost.Children;
        var igual = hijos.Count == orden.Count;
        for (var i = 0; igual && i < orden.Count; i++) igual = ReferenceEquals(hijos[i], orden[i].Raiz);
        if (!igual)
        {
            ListaHost.Clear();
            foreach (var vista in orden) ListaHost.Add(vista.Raiz);
        }
        ListaScroll.IsVisible = orden.Count > 0;
        EncabezadoGrid.IsVisible = orden.Count > 0;
        VacioLabel.IsVisible = orden.Count == 0;
    }

    private string NombreVisible(FilaResultado f)
    {
        if (!OcultarNombres) return f.Nombre;
        if (!_anonimos.TryGetValue(f.ParticipanteId, out var numero))
            _anonimos[f.ParticipanteId] = numero = _anonimos.Count + 1;
        return $"Alumno {numero}";
    }

    private FilaVista CrearFila()
    {
        var v = new FilaVista();
        var cuadricula = new Grid
        {
            ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(280), new ColumnDefinition(96), new ColumnDefinition(190), new ColumnDefinition(250)],
            ColumnSpacing = 12,
        };

        // Alumno: nombre y, si no está conectado, su presencia (por qué no avanza)
        v.Nombre = new Label { FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation, MaxLines = 1 };
        v.Presencia = new Label { FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave, IsVisible = false };
        cuadricula.Add(new VerticalStackLayout { Spacing = 1, VerticalOptions = LayoutOptions.Center, Children = { v.Nombre, v.Presencia } }, 0, 0);

        // Avance: pista con relleno proporcional (dos columnas Star; sin Path ni Ellipse) y «n/N»
        v.Relleno = new Grid { BackgroundColor = Ds.Info };
        var proporcion = new Grid { ColumnDefinitions = [new ColumnDefinition(new GridLength(0, GridUnitType.Star)), new ColumnDefinition(new GridLength(1, GridUnitType.Star))] };
        proporcion.Add(v.Relleno, 0, 0);
        v.Proporcion = proporcion;
        var pista = new Border
        {
            BackgroundColor = GrisPista, StrokeThickness = 0, HeightRequest = 14, VerticalOptions = LayoutOptions.Center,
            StrokeShape = new RoundRectangle { CornerRadius = 7 }, Content = proporcion,
        };
        v.Progreso = new Label { FontFamily = Ds.FuenteRegular, FontSize = 16, TextColor = Ds.TintaMedia, WidthRequest = 60, HorizontalTextAlignment = TextAlignment.End, VerticalOptions = LayoutOptions.Center };
        var avance = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10, VerticalOptions = LayoutOptions.Center };
        avance.Add(pista, 0, 0);
        avance.Add(v.Progreso, 1, 0);
        cuadricula.Add(avance, 1, 0);

        // Nota provisional
        v.Nota = new Label { FontFamily = Ds.FuenteMedia, FontSize = 22, TextColor = Ds.Tinta, HorizontalTextAlignment = TextAlignment.End, VerticalOptions = LayoutOptions.Center };
        cuadricula.Add(v.Nota, 2, 0);

        // Estado en texto y la marca de atención (texto, no sólo color)
        v.Estado = new Label { FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta };
        v.Detalle = new Label { FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave, IsVisible = false };
        v.Marca = Ds.Pildora("⚠  Necesita atención", Ds.Alerta, Ds.Tinta, 13);
        v.Marca.IsVisible = false;
        v.Marca.HorizontalOptions = LayoutOptions.Start;
        cuadricula.Add(new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center, Children = { v.Estado, v.Detalle, v.Marca } }, 3, 0);

        // Decisión sobre un envío tardío: los botones nacen la primera vez que la fila los necesita
        v.Acciones = new HorizontalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.End, VerticalOptions = LayoutOptions.Center, IsVisible = false };
        cuadricula.Add(v.Acciones, 4, 0);

        v.Raiz = new Border
        {
            Padding = new Thickness(16, 10), MinimumHeightRequest = 68, StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, BackgroundColor = Colors.White, Content = cuadricula,
        };
        v.Raiz.Stroke = FiloFila;
        return v;
    }

    private void PintarFila(FilaVista v, FilaResultado f)
    {
        v.Actual = f;
        var nombre = NombreVisible(f);
        v.Nombre.Text = nombre;
        var presencia = f.Presencia switch { "reconectando" => "Reconectando", "salio" => "Salió", _ => null };
        v.Presencia.Text = presencia ?? string.Empty;
        v.Presencia.IsVisible = presencia is not null;

        var avance = Math.Clamp(double.IsFinite(f.Avance) ? f.Avance : 0, 0, 1);
        v.Proporcion.ColumnDefinitions[0].Width = new GridLength(avance, GridUnitType.Star);
        v.Proporcion.ColumnDefinitions[1].Width = new GridLength(1 - avance, GridUnitType.Star);
        v.Relleno.BackgroundColor = f.Estado switch
        {
            "entregado" => Ds.Exito,
            "pendiente_decision" => Ds.Alerta,
            "sin_empezar" => GrisSinEmpezar,
            _ => Ds.Info,
        };
        v.Progreso.Text = f.TotalPreguntas > 0 ? $"{f.Respondidas}/{f.TotalPreguntas}" : f.Respondidas.ToString();
        v.Nota.Text = f.Porcentaje is { } p ? Porcentaje(p) : "—";
        v.Estado.Text = f.EstadoLegible;
        var pendiente = f.Estado == "pendiente_decision" && !string.IsNullOrEmpty(f.IntentoId);
        v.Detalle.Text = pendiente ? "Llegó fuera del tiempo" : string.Empty;
        v.Detalle.IsVisible = pendiente;
        v.Marca.IsVisible = f.Rezagado;

        v.Raiz.BackgroundColor = f.Rezagado ? Ds.AlertaSuave : pendiente ? Ds.InfoSuave : Colors.White;
        v.Raiz.Stroke = f.Rezagado ? FiloRezagado : pendiente ? FiloPendiente : FiloFila;

        if (pendiente) PrepararAcciones(v);
        v.Acciones.IsVisible = pendiente;

        SemanticProperties.SetDescription(v.Raiz, string.Join(", ", new[]
        {
            nombre, f.EstadoLegible, v.Progreso.Text.Contains('/') ? $"{f.Respondidas} de {f.TotalPreguntas} preguntas" : null,
            f.Porcentaje is null ? null : $"nota {Porcentaje(f.Porcentaje.Value)}", f.Rezagado ? "necesita atención" : null,
        }.Where(x => x is not null)));
    }

    private void PrepararAcciones(FilaVista v)
    {
        if (v.Aceptar is not null) return;
        v.Aceptar = Ds.Boton("Aceptar", Ds.Rango.Secondary, async (_, _) => await DecidirAsync(v, "aceptar"), 52);
        v.Descartar = Ds.Boton("Descartar", Ds.Rango.Secondary, async (_, _) => await DecidirAsync(v, "descartar"), 52);
        v.Aceptar.FontSize = v.Descartar.FontSize = 16;
        v.Acciones.Add(Ds.Capsula(v.Aceptar));
        v.Acciones.Add(Ds.Capsula(v.Descartar));
    }

    private static void HabilitarAcciones(FilaVista v, bool activo)
    {
        if (v.Aceptar is not null) Ds.Habilitar(v.Aceptar, activo);
        if (v.Descartar is not null) Ds.Habilitar(v.Descartar, activo);
    }

    /// <summary>
    /// DEC-019: lo que llegó fuera de la ventana de gracia lo decide el profesor. «Descartar» pide confirmación (no se puede deshacer desde
    /// aquí); «Aceptar» no. Mientras el aula contesta los dos botones de esa fila quedan atenuados, y después se refresca el panel.
    /// </summary>
    private async Task DecidirAsync(FilaVista v, string decision)
    {
        try
        {
            var actividad = _actividad;
            var fila = v.Actual;
            var sesionId = _sesionId;
            var actor = _actor;
            if (actividad is null || string.IsNullOrEmpty(fila?.IntentoId) || v.Decidiendo) return;

            if (decision == "descartar" && Window?.Page is { } pagina
                && !await pagina.DisplayAlertAsync($"¿Descartar lo que envió {NombreVisible(fila)}?",
                    "Lo que llegó fuera del tiempo no se contará y no se podrá recuperar desde aquí.", "Descartar", "Cancelar"))
                return;

            var token = _cts.Token;
            v.Decidiendo = true;
            HabilitarAcciones(v, false);
            bool hecho;
            try { hecho = await Sesion.Aula.DecidirEnvioAsync(sesionId, actor, actividad.Id, fila.IntentoId, decision, token); }
            finally { v.Decidiendo = false; }

            if (!hecho)
            {
                if (token.IsCancellationRequested) return;
                _avisoDecision = "No se pudo guardar la decisión · inténtalo de nuevo";
                PintarAviso();
                HabilitarAcciones(v, true);
                return;
            }
            _avisoDecision = null;
            PintarAviso();
            await RefrescarAsync();
        }
        catch (Exception)
        {
            // Un fallo inesperado no debe tumbar el panel: la fila vuelve a quedar disponible.
            HabilitarAcciones(v, true);
        }
    }

    private static string Porcentaje(double valor) => $"{Math.Round(valor, MidpointRounding.AwayFromZero):0} %";

    /// <summary>Las vistas de una fila de alumno: se crean una vez y se actualizan en su sitio.</summary>
    private sealed class FilaVista
    {
        public Border Raiz = null!;
        public Label Nombre = null!, Presencia = null!, Progreso = null!, Nota = null!, Estado = null!, Detalle = null!;
        public Grid Proporcion = null!, Relleno = null!;
        public Border Marca = null!;
        public HorizontalStackLayout Acciones = null!;
        public Button? Aceptar, Descartar;
        public FilaResultado? Actual;
        public bool Decidiendo;
    }
}
