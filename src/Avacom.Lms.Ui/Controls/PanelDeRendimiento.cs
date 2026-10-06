using System.Globalization;
using Avacom.Lms.Core.Diagnostico;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;
using Microsoft.Maui.Graphics;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// El panel de depuración «Rendimiento y red», el mismo en OPS (pestaña de Historial) y en Student (pantalla «Diagnóstico de red»): once indicadores
/// vivos con su semáforo, su promedio y su máximo, una gráfica de los últimos minutos, y tres acciones para las pruebas de descarga y de red:
/// «Marcar momento» (señala en el historial dónde empezó algo), «Copiar resumen» y «Exportar CSV». Se alimenta de <see cref="MonitorDeRendimiento"/>.
///
/// Las tarjetas se construyen una sola vez y después sólo cambian sus textos y la gráfica (tamaño fijo): así cada lectura no vuelve a medir la
/// pantalla, que es lo que dispara <c>LayoutCycleException</c> en WinUI con muchas tarjetas. Nada exige teclado.
/// </summary>
public sealed class PanelDeRendimiento : ContentView
{
    private enum Nivel { Neutro, Bien, Atencion, Mal }
    private enum Prioridad { Critica, Alta, Media }

    private sealed record Indicador(
        string Nombre, string Unidad, Prioridad Prioridad,
        Func<MuestraDeRendimiento, double?> Serie,
        Func<MuestraDeRendimiento, string> Valor,
        Func<MuestraDeRendimiento, string> Detalle,
        Func<MuestraDeRendimiento, Nivel> Nivel,
        Func<IReadOnlyList<MuestraDeRendimiento>, string?>? Tendencia = null);

    private sealed class Tarjeta
    {
        public required Indicador Indicador;
        public required Label Valor, Resumen, Detalle, Extra;
        public required Border Contenedor, Punto;
        public required GraphicsView Grafica;
        public required Linea Dibujo;
    }

    private static readonly Color TintaPeligro = Color.FromArgb("#8A1C1F");
    private static readonly Color TintaAlerta = Color.FromArgb("#7A5B00");
    private static readonly Color TintaInfo = Color.FromArgb("#0B5F80");
    private const double AnchoTarjeta = 296, AltoTarjeta = 204;

    private readonly MonitorDeRendimiento monitor;
    private readonly List<Tarjeta> tarjetas = [];
    private readonly Label estado = Ds.Secundario(string.Empty, 13);
    private readonly Label contexto = Ds.Secundario(string.Empty, 13);
    private readonly Label marcas = Ds.Secundario(string.Empty, 13);
    private readonly Label sinDatos = Ds.Secundario("Esperando la primera lectura…", 14);
    private bool suscrito;

    /// <summary>La carpeta donde «Exportar CSV» deja el archivo.</summary>
    public string CarpetaDeExportacion { get; set; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "avacom-diagnostico");
    /// <summary>Qué app es («ops» o «student»): va en el nombre del CSV y en el resumen.</summary>
    public string App { get; set; } = "app";
    /// <summary>Lo que significa «conexiones activas» en esta app, para el renglón de detalle.</summary>
    public string DescripcionDeConexiones { get; set; } = "alumnos con canal abierto en el nodo";

    public PanelDeRendimiento(MonitorDeRendimiento? monitor = null)
    {
        this.monitor = monitor ?? MonitorDeRendimiento.Global;
        Content = Armar();
        Loaded += (_, _) => Suscribir();
        Unloaded += (_, _) => Desuscribir();
    }

    // ------------------------------------------------------------------ indicadores

    private static readonly Indicador[] Indicadores =
    [
        new("Uso de CPU", "%", Prioridad.Critica, m => m.CpuSistemaPct ?? m.CpuProcesoPct,
            m => $"{(m.CpuSistemaPct ?? m.CpuProcesoPct):0} %",
            m => m.CpuSistemaPct is null ? $"Del equipo no disponible · esta app {m.CpuProcesoPct:0} %" : $"Equipo {m.CpuSistemaPct:0} % · esta app {m.CpuProcesoPct:0} %",
            m => Alto(m.CpuSistemaPct ?? m.CpuProcesoPct, 70, 90)),
        new("Uso de RAM", "% y MB", Prioridad.Critica, m => m.RamSistemaPct,
            m => m.RamSistemaPct is { } p ? $"{p:0} %" : $"{m.RamProcesoMb:0} MB",
            m => m.RamSistemaUsadaMb is { } u && m.RamSistemaTotalMb is { } t ? $"{u / 1024:0.0} de {t / 1024:0.0} GB · esta app {m.RamProcesoMb:0} MB" : $"Del equipo no disponible · esta app {m.RamProcesoMb:0} MB",
            m => Alto(m.RamSistemaPct, 75, 90), TendenciaDeRam),
        new("Velocidad de descarga", "Mbps", Prioridad.Critica, m => m.DescargaMbps ?? m.DescargaAppMbps,
            m => Mbps(m.DescargaMbps ?? m.DescargaAppMbps),
            m => m.DescargaMbps is null ? "Sólo lo que mueve esta app (la red del equipo no se puede leer)" : $"Todo el equipo · esta app {Mbps(m.DescargaAppMbps)}",
            _ => Nivel.Neutro),
        new("Velocidad de carga", "Mbps", Prioridad.Critica, m => m.CargaMbps ?? m.CargaAppMbps,
            m => Mbps(m.CargaMbps ?? m.CargaAppMbps),
            m => m.CargaMbps is null ? "Sólo lo que mueve esta app (la red del equipo no se puede leer)" : $"Todo el equipo · esta app {Mbps(m.CargaAppMbps)}",
            _ => Nivel.Neutro),
        new("Latencia de red", "ms", Prioridad.Critica, m => m.LatenciaMs,
            m => m.LatenciaMs is { } l ? $"{l:0} ms" : "sin respuesta",
            _ => "Tiempo de abrir una conexión TCP al nodo",
            m => m.LatenciaMs is null ? Nivel.Mal : Alto(m.LatenciaMs, 100, 300)),
        new("Pérdida de paquetes", "%", Prioridad.Alta, m => m.PerdidaPct,
            m => m.PerdidaPct is { } p ? $"{p:0.#} %" : "—",
            _ => "Sondeos al nodo sin respuesta en 1 s (de los últimos 30)",
            m => Alto(m.PerdidaPct, 1, 5)),
        new("Uso de disco", "% / GB libres", Prioridad.Alta, m => m.DiscoLibreGb,
            m => m.DiscoLibreGb is { } g ? $"{g:0.0} GB libres" : "no disponible",
            m => m.DiscoLibrePct is { } p ? $"{p:0} % libre del volumen de datos" : "El sistema no dio el espacio libre",
            m => m.DiscoLibrePct is { } p ? Bajo(p, 20, 10) : Nivel.Neutro),
        new("I/O de disco", "MB/s", Prioridad.Media, m => m.DiscoLecturaMBs is { } l && m.DiscoEscrituraMBs is { } e ? l + e : null,
            m => m.DiscoLecturaMBs is { } l && m.DiscoEscrituraMBs is { } e ? $"{l + e:0.0} MB/s" : "no disponible",
            m => m.DiscoLecturaMBs is { } l && m.DiscoEscrituraMBs is { } e ? $"Lee {l:0.0} · escribe {e:0.0} MB/s (archivos de esta app)" : "El sistema no da el I/O del proceso",
            _ => Nivel.Neutro),
        new("Conexiones activas", "N", Prioridad.Critica, m => m.ConexionesActivas ?? m.CanalesAbiertos,
            m => $"{m.ConexionesActivas ?? m.CanalesAbiertos}",
            m => m.ConexionesActivas is { } n ? $"{n} alumno{(n == 1 ? "" : "s")} con canal abierto en el nodo · canales de esta app {m.CanalesAbiertos}" : $"Canales en tiempo real abiertos por esta app: {m.CanalesAbiertos}",
            _ => Nivel.Neutro),
        new("Latencia de aplicación", "ms p50 / p95", Prioridad.Critica, m => m.LatenciaAppP95Ms,
            m => m.LatenciaAppP50Ms is { } a && m.LatenciaAppP95Ms is { } b ? $"{a:0} / {b:0} ms" : "sin llamadas",
            m => m.Aplicacion.Llamadas == 0 ? "Aún no hubo llamadas al nodo en los últimos 5 min" : $"{m.Aplicacion.Llamadas} llamadas en 5 min · máximo {(m.Aplicacion.MaximoMs is { } x ? x.ToString("0") : "—")} ms · hasta recibir cabeceras",
            m => Alto(m.LatenciaAppP95Ms, 500, 1500)),
        new("Errores", "errores/min", Prioridad.Alta, m => m.ErroresPorMinuto,
            m => $"{m.ErroresPorMinuto:0.#} /min",
            m => $"4xx {m.Aplicacion.Cliente4xx} · 5xx {m.Aplicacion.Servidor5xx} · timeouts {m.Aplicacion.TiemposAgotados} · sin red {m.Aplicacion.SinConexion} · reconexiones {m.Aplicacion.Reconexiones} (5 min)",
            m => m.ErroresPorMinuto >= 5 ? Nivel.Mal : m.ErroresPorMinuto > 0 ? Nivel.Atencion : Nivel.Bien),
    ];

    private static Nivel Alto(double? valor, double atencion, double mal) => valor is not { } v ? Nivel.Neutro : v >= mal ? Nivel.Mal : v >= atencion ? Nivel.Atencion : Nivel.Bien;
    private static Nivel Bajo(double valor, double atencion, double mal) => valor <= mal ? Nivel.Mal : valor <= atencion ? Nivel.Atencion : Nivel.Bien;
    private static string Mbps(double? valor) => valor is { } v ? $"{v:0.0} Mbps" : "—";

    /// <summary>Una app que consume cada vez más RAM sin soltarla (posible fuga): el cambio de la memoria de esta app entre la primera y la última lectura.</summary>
    private static string? TendenciaDeRam(IReadOnlyList<MuestraDeRendimiento> historial)
    {
        if (historial.Count < 30) return null;
        var delta = historial[^1].RamProcesoMb - historial[0].RamProcesoMb;
        var minutos = (historial[^1].Instante - historial[0].Instante).TotalMinutes;
        return $"Memoria de esta app {(delta >= 0 ? "+" : "")}{delta:0} MB en {minutos:0.#} min";
    }

    // ------------------------------------------------------------------ armado

    private View Armar()
    {
        var raiz = new VerticalStackLayout { Spacing = 12 };

        var botones = new HorizontalStackLayout { Spacing = 10 };
        botones.Add(Boton("Marcar momento", Ds.Rango.Secondary, (_, _) => { var m = monitor.Marcar(); Aviso($"{m} puesta: aparecerá en la próxima lectura y en el CSV."); }, 170));
        botones.Add(Boton("Copiar resumen", Ds.Rango.Secondary, async (_, _) => await CopiarAsync(), 170));
        botones.Add(Boton("Exportar CSV", Ds.Rango.Secondary, (_, _) => Exportar(), 150));
        botones.Add(Boton("Reiniciar mediciones", Ds.Rango.Quiet, (_, _) => { monitor.Reiniciar(); Aviso("Mediciones reiniciadas."); Repintar(); }, 190));
        raiz.Add(Ds.Tarjeta(new VerticalStackLayout { Spacing = 8, Children = { contexto, new ScrollView { Orientation = ScrollOrientation.Horizontal, Content = botones }, estado, marcas } },
            Ds.RadioTarjeta, new Thickness(18, 14), Colors.White));

        raiz.Add(sinDatos);
        var flujo = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start };
        foreach (var indicador in Indicadores)
        {
            var t = NuevaTarjeta(indicador);
            tarjetas.Add(t);
            flujo.Add(t.Contenedor);
        }
        raiz.Add(flujo);
        return raiz;
    }

    private static Button Boton(string texto, Ds.Rango rango, EventHandler alPulsar, double ancho)
    {
        var boton = Ds.Boton(texto, rango, alPulsar, 48, ancho);
        boton.FontSize = 14;
        return boton;
    }

    private Tarjeta NuevaTarjeta(Indicador i)
    {
        var (fondo, tinta, rotulo) = i.Prioridad switch
        {
            Prioridad.Critica => (Ds.PeligroSuave, TintaPeligro, "Crítica"),
            Prioridad.Alta => (Ds.AlertaSuave, TintaAlerta, "Alta"),
            _ => (Ds.InfoSuave, TintaInfo, "Media"),
        };
        var punto = new Border { WidthRequest = 14, HeightRequest = 14, StrokeThickness = 0, BackgroundColor = Color.FromArgb("#D4D4D8"), StrokeShape = new RoundRectangle { CornerRadius = 7 }, VerticalOptions = LayoutOptions.Center };
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 8 };
        cabecera.Add(punto, 0, 0);
        var nombre = Ds.Cuerpo(i.Nombre, 15);
        nombre.LineBreakMode = LineBreakMode.TailTruncation; nombre.MaxLines = 1; nombre.VerticalOptions = LayoutOptions.Center;
        cabecera.Add(nombre, 1, 0);
        var chip = Ds.Pildora(rotulo, fondo, tinta, 11); chip.Padding = new Thickness(8, 3);
        cabecera.Add(chip, 2, 0);

        var valor = Ds.Titulo("—", 26); valor.LineBreakMode = LineBreakMode.TailTruncation; valor.MaxLines = 1;
        var resumen = Ds.Secundario($"{i.Unidad}", 12); resumen.LineBreakMode = LineBreakMode.TailTruncation; resumen.MaxLines = 1;
        var detalle = Ds.Secundario(string.Empty, 12); detalle.LineBreakMode = LineBreakMode.TailTruncation; detalle.MaxLines = 2; detalle.HeightRequest = 34;
        var extra = Ds.Secundario(string.Empty, 12); extra.LineBreakMode = LineBreakMode.TailTruncation; extra.MaxLines = 1;
        var dibujo = new Linea();
        var grafica = new GraphicsView { Drawable = dibujo, HeightRequest = 38, InputTransparent = true };

        var pila = new VerticalStackLayout { Spacing = 4, Children = { cabecera, valor, resumen, grafica, detalle, extra } };
        // Sin sombra y con alto fijo: ni WinUI cuenta ciclos de layout con once tarjetas ni una lectura cambia el tamaño de la pantalla.
        var borde = new Border
        {
            BackgroundColor = Colors.White, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1,
            StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(16, 12), Content = pila,
            WidthRequest = AnchoTarjeta, HeightRequest = AltoTarjeta, Margin = new Thickness(0, 0, 10, 10),
        };
        return new Tarjeta { Indicador = i, Valor = valor, Resumen = resumen, Detalle = detalle, Extra = extra, Contenedor = borde, Punto = punto, Grafica = grafica, Dibujo = dibujo };
    }

    // ------------------------------------------------------------------ vida

    private void Suscribir()
    {
        if (suscrito) return;
        suscrito = true;
        monitor.Muestreado += AlMuestrear;
        Repintar();
    }

    private void Desuscribir()
    {
        suscrito = false;
        monitor.Muestreado -= AlMuestrear;
    }

    private void AlMuestrear(MuestraDeRendimiento _) => Dispatcher.Dispatch(Repintar);

    private void Repintar()
    {
        var historial = monitor.Historial();
        contexto.Text = $"{App.ToUpperInvariant()} · nodo {(monitor.Nodo?.Authority ?? "sin definir")} · una lectura cada {monitor.Intervalo.TotalSeconds:0} s · historial de {MonitorDeRendimiento.CapacidadDelHistorial * monitor.Intervalo.TotalSeconds / 60:0} min ({historial.Count} lecturas)";
        var ultima = historial.Count == 0 ? null : historial[^1];
        sinDatos.IsVisible = ultima is null;
        var puestas = historial.Where(m => m.Marca is not null).TakeLast(6).Select(m => $"{m.Marca} {m.Instante:HH:mm:ss}").ToArray();
        marcas.Text = puestas.Length == 0 ? "Sin marcas: usa «Marcar momento» al empezar una descarga o al conectar más tabletas." : "Marcas: " + string.Join(" · ", puestas);
        if (ultima is null) return;

        foreach (var t in tarjetas)
        {
            var i = t.Indicador;
            var nivel = i.Nivel(ultima);
            t.Valor.Text = i.Valor(ultima);
            t.Detalle.Text = i.Detalle(ultima);
            var serie = historial.Select(m => i.Serie(m)).ToArray();
            var validos = serie.Where(v => v is { } x && double.IsFinite(x)).Select(v => v!.Value).ToArray();
            t.Resumen.Text = validos.Length == 0 ? i.Unidad : $"{i.Unidad} · prom {Compacto(validos.Average())} · máx {Compacto(validos.Max())}";
            t.Extra.Text = i.Tendencia?.Invoke(historial) ?? string.Empty;
            t.Punto.BackgroundColor = nivel switch { Nivel.Bien => Ds.Exito, Nivel.Atencion => Ds.Alerta, Nivel.Mal => Ds.Peligro, _ => Color.FromArgb("#A1A1AA") };
            t.Dibujo.Valores = serie;
            t.Dibujo.Color = nivel switch { Nivel.Mal => Ds.Peligro, Nivel.Atencion => Color.FromArgb("#B8860B"), Nivel.Bien => Ds.Exito, _ => Ds.Info };
            t.Grafica.Invalidate();
        }
    }

    private static string Compacto(double v) => v >= 100 ? v.ToString("0", CultureInfo.CurrentCulture) : v.ToString("0.#", CultureInfo.CurrentCulture);

    // ------------------------------------------------------------------ acciones

    private void Aviso(string texto) => estado.Text = texto;

    private void Exportar()
    {
        try
        {
            var ruta = monitor.ExportarCsv(System.IO.Path.Combine(CarpetaDeExportacion, $"rendimiento-{App}-{DateTime.Now:yyyyMMdd-HHmmss}.csv"));
            Aviso($"CSV guardado en {ruta}");
        }
        catch (Exception ex) { Aviso("No se pudo exportar: " + ex.Message); }
    }

    private async Task CopiarAsync()
    {
        try
        {
            await Clipboard.Default.SetTextAsync(ResumenEnTexto());
            Aviso("Resumen copiado: pégalo en la tabla de mediciones.");
        }
        catch (Exception ex) { Aviso("No se pudo copiar: " + ex.Message); }
    }

    /// <summary>Una línea por indicador con el valor actual, el promedio y el máximo del historial. Pensado para pegarlo en el reporte de la prueba.</summary>
    public string ResumenEnTexto()
    {
        var historial = monitor.Historial();
        if (historial.Count == 0) return "Sin lecturas todavía.";
        var ultima = historial[^1];
        var lineas = new List<string> { $"{App.ToUpperInvariant()} · nodo {monitor.Nodo?.Authority} · {historial[0].Instante:HH:mm:ss}–{ultima.Instante:HH:mm:ss} ({historial.Count} lecturas)" };
        foreach (var i in Indicadores)
        {
            var validos = historial.Select(m => i.Serie(m)).Where(v => v is { } x && double.IsFinite(x)).Select(v => v!.Value).ToArray();
            lineas.Add(validos.Length == 0 ? $"{i.Nombre}: {i.Valor(ultima)}" : $"{i.Nombre}: {i.Valor(ultima)} (prom {Compacto(validos.Average())}, máx {Compacto(validos.Max())} {i.Unidad})");
        }
        return string.Join('\n', lineas);
    }

    // ------------------------------------------------------------------ gráfica

    /// <summary>La línea de los últimos minutos, de 0 al máximo visto. Segmentos sueltos (nunca un Path): un trazo degenerado tumba todos los lienzos de la ventana en Win2D.</summary>
    private sealed class Linea : IDrawable
    {
        public IReadOnlyList<double?> Valores { get; set; } = [];
        public Color Color { get; set; } = Ds.Info;

        public void Draw(ICanvas canvas, RectF area)
        {
            if (area.Width < 4 || area.Height < 4 || Valores.Count < 2) return;
            var maximo = 0.0;
            foreach (var v in Valores) if (v is { } x && double.IsFinite(x) && x > maximo) maximo = x;
            if (maximo <= 0) maximo = 1;
            canvas.StrokeColor = Color;
            canvas.StrokeSize = 1.6f;
            canvas.StrokeLineCap = LineCap.Round;
            var paso = area.Width / (Valores.Count - 1);
            PointF? anterior = null;
            for (var n = 0; n < Valores.Count; n++)
            {
                if (Valores[n] is not { } valor || !double.IsFinite(valor)) { anterior = null; continue; }
                var punto = new PointF((float)(n * paso), (float)(area.Height - 2 - valor / maximo * (area.Height - 4)));
                if (anterior is { } previo && (Math.Abs(punto.X - previo.X) > 0.01f || Math.Abs(punto.Y - previo.Y) > 0.01f)) canvas.DrawLine(previo, punto);
                anterior = punto;
            }
        }
    }
}
