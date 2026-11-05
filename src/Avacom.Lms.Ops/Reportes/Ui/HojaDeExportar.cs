using System.Runtime.CompilerServices;
using Avacom.Lms.Core.Reporting;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Pages;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ops.Reportes.Ui;

/// <summary>
/// La hoja de exportar (FUN-146): se abre SOBRE el reporte, como la hoja de opciones del examen (un velo tenue y una tarjeta al centro, en el tercio central de la ventana y de 1/6 a 5/6
/// de su alto), y lleva a la persona por cinco pasos sin teclado: <b>elegir</b> (formato, razón si el administrador la exige y destino, con las unidades que se enchufan o se retiran
/// apareciendo solas), <b>confirmar</b> (el alcance declarado, con el lugar y la advertencia), <b>guardando</b> (avance real y «Cancelar»), y el <b>resultado</b> (guardado con su ruta, tamaño y
/// «Abrir carpeta»; o el motivo exacto del fallo y qué hacer, con «Elegir otro destino» SIN generar de nuevo). El reporte de debajo nunca se toca.
///
/// Toda la lógica vive en <see cref="FlujoDeExportacion"/> y en <see cref="CatalogoDeDestinos"/>; aquí sólo se pinta lo que devuelven. Usar desde el hilo de interfaz.
/// </summary>
internal sealed class HojaDeExportar : ContentView
{
    private enum Paso { Preparando, Elegir, Confirmar, Guardando, Resultado, SinAlcance }

    private static readonly IProveedorDeUnidades Unidades = new ProveedorConUnidadesDePrueba(new ProveedorDeUnidadesDelSistema());

    private readonly Grid _raiz = new();
    private readonly Border _tarjeta;
    private readonly Label _titulo, _subtitulo;
    private readonly ScrollView _desplazable;
    private readonly VerticalStackLayout _cuerpo = new() { Spacing = 14 };
    private readonly FlexLayout _pie = new()
    {
        Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, Direction = Microsoft.Maui.Layouts.FlexDirection.Row, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.End,
        AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start,
    };
    // La barra de avance y su porcentaje se crean de nuevo en cada pintada: una vista no puede colgar de dos padres a la vez.
    private ContentView _barraHost = new();
    private Label _porcentaje = new();
    private readonly PreferenciasDeDestino _preferencias = new(new AlmacenDeAjustes());

    private FlujoDeExportacion? _flujo;
    private TaskCompletionSource? _cierre;
    private Paso _paso;
    private AlcanceDeExportacion? _alcance;
    private string _formato = FormatosDeExportacion.Xlsx;
    private string? _razon;
    private ResultadoDeBusqueda? _busqueda;
    private DestinoDeExportacion? _ultima, _carpetaAMano, _elegido;
    private string? _nota;
    private ResultadoDelGuardado? _resultado;
    private PoliticaDeDestinos _politica = new();
    private CancellationTokenSource? _cancelacion;
    private VigilanteDeUnidades? _vigilante;
    private double _avance, _ultimoPintado = -1;
    private int _version;

    public HojaDeExportar()
    {
        IsVisible = false;
        ZIndex = 50;

        // El velo es hermano de la tarjeta (no su padre): un toque dentro de la tarjeta nunca llega aquí. Tocar fuera NO cierra la hoja: guardar un reporte no se cancela de un roce.
        var velo = new Border { BackgroundColor = Color.FromArgb("#731F2433"), StrokeThickness = 0 };

        _titulo = new Label { FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap };
        _subtitulo = new Label { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap };
        _desplazable = new ScrollView { Content = _cuerpo };

        var cabecera = new VerticalStackLayout { Spacing = 2, Margin = new Thickness(0, 0, 0, 10) };
        cabecera.Add(_titulo);
        cabecera.Add(_subtitulo);

        var contenido = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)], RowSpacing = 0 };
        contenido.Add(cabecera, 0, 0);
        contenido.Add(_desplazable, 0, 1);
        contenido.Add(new Border { Padding = new Thickness(0, 14, 0, 0), StrokeThickness = 0, BackgroundColor = Colors.Transparent, Content = _pie }, 0, 2);

        _tarjeta = new Border
        {
            BackgroundColor = Ds.SuperficieContenido, Stroke = new SolidColorBrush(Ds.Filo), StrokeThickness = 1, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande },
            Padding = new Thickness(28, 24), HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Content = contenido,
            Shadow = new Shadow { Brush = new SolidColorBrush(Ds.Tinta), Offset = new Point(0, 12), Radius = 32, Opacity = 0.28f },
            AutomationId = "exportar-hoja",
        };
        _raiz.Add(velo);
        _raiz.Add(_tarjeta);
        _raiz.SizeChanged += OnRaizSizeChanged;
        Content = _raiz;
    }

    /// <summary>La tarjeta en el tercio central: un tercio del ancho y de 1/6 a 5/6 del alto (4/6). El cuerpo se desplaza si no cabe y los botones quedan siempre a la vista.</summary>
    private void OnRaizSizeChanged(object? sender, EventArgs e)
    {
        if (_raiz.Width <= 0 || _raiz.Height <= 0) return;
        _tarjeta.WidthRequest = Math.Min(_raiz.Width, Math.Max(560, _raiz.Width / 3));
        _tarjeta.HeightRequest = Math.Min(_raiz.Height, Math.Max(560, _raiz.Height * 4 / 6));
    }

    // =============================================================================================================== abrir y cerrar

    /// <summary>Abre la hoja para exportar el reporte del <paramref name="flujo"/> y espera a que se cierre (guardado, cancelado o abandonado). El flujo se libera al cerrar.</summary>
    public async Task MostrarAsync(FlujoDeExportacion flujo)
    {
        Cerrar();
        _flujo = flujo;
        _cierre = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        (_alcance, _formato, _razon, _busqueda, _ultima, _carpetaAMano, _elegido, _nota, _resultado) = (null, FormatosDeExportacion.Xlsx, null, null, null, null, null, null, null);
        _politica = new PoliticaDeDestinos();
        IsVisible = true;
        var tarea = _cierre.Task;
        await PrepararAsync();
        await tarea;
    }

    private void Cerrar()
    {
        var cierre = Interlocked.Exchange(ref _cierre, null);
        _cancelacion?.Cancel();
        _cancelacion = null;
        DetenerVigilante();
        _version++;
        _flujo?.Dispose();
        _flujo = null;
        IsVisible = false;
        cierre?.TrySetResult();
    }

    /// <summary>Si el host oculta la hoja o sale del árbol visual (la pantalla se cierra), nadie se queda esperando y el temporal se borra.</summary>
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

    // =============================================================================================================== el alcance y los destinos

    private async Task PrepararAsync()
    {
        var version = _version;
        _paso = Paso.Preparando;
        Pintar();
        var alcance = await _flujo!.AlcanceAsync(_formato);
        if (version != _version) return;
        if (alcance is null)
        {
            _nota = MensajesDeReportes.De(_flujo.UltimoError);
            _paso = Paso.SinAlcance;
            Pintar();
            return;
        }
        _alcance = alcance;
        _politica = new PoliticaDeDestinos(PermitirExtraibles: alcance.Politica.ExtraiblesPermitidos, PermitirRed: true);
        await BuscarDestinosAsync();
        if (version != _version) return;
        _elegido ??= Lista().FirstOrDefault(EsLaUltima);                            // la última carpeta de esta persona se propone sola
        IniciarVigilante();
        _paso = Paso.Elegir;
        Pintar();
    }

    private bool Permitido(TipoDeDestino tipo) => tipo switch
    {
        TipoDeDestino.Extraible => _politica.PermitirExtraibles,
        TipoDeDestino.Red => _politica.PermitirRed,
        _ => true,
    };

    /// <summary>Lee las unidades y las carpetas conocidas fuera del hilo de la pantalla (una unidad de red caída puede tardar unos segundos) y recuerda la última carpeta de esta persona.</summary>
    private async Task BuscarDestinosAsync()
    {
        var politica = _politica;
        var actor = ReportesUi.Actor;
        var (busqueda, ultima) = await Task.Run(() =>
        {
            var encontrados = new CatalogoDeDestinos(Unidades, new CarpetasConocidasDelSistema(), politica).Buscar();
            DestinoDeExportacion? recordada = null;
            if (_preferencias.UltimaCarpeta(actor) is { } ruta)
            {
                var tipo = ClasificadorDeRuta.Clasificar(ruta, Unidades);
                var permitido = tipo switch { TipoDeDestino.Extraible => politica.PermitirExtraibles, TipoDeDestino.Red => politica.PermitirRed, _ => true };
                if (permitido) recordada = new DestinoDeExportacion($"ultima:{ruta}", "Última carpeta que usaste", ruta, tipo, null, null, null, EsAtajo: false, Listo: true);
            }
            return (encontrados, recordada);
        });
        _busqueda = busqueda;
        _ultima = ultima;
        // Lo elegido que ya no está (la memoria se retiró) se suelta y se dice.
        if (_elegido is { } e && !Lista().Any(d => d.Id == e.Id))
        {
            _nota = $"«{e.Nombre}» ya no está conectado. Elige otro destino.";
            _elegido = null;
        }
    }

    private static string Clave(string ruta) => ruta.TrimEnd('\\', '/');

    private IEnumerable<DestinoDeExportacion> Lista()
    {
        var vistos = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var conocidos = _busqueda?.Destinos ?? [];
        if (_carpetaAMano is { } a && vistos.Add(Clave(a.Ruta))) yield return a;
        // La última carpeta que usó esta persona va primero; si es un lugar que la lista ya conoce (una unidad, un atajo) se muestra ESE, con su etiqueta y su espacio, y no una copia.
        if (_ultima is { } u)
        {
            var conocido = conocidos.FirstOrDefault(d => string.Equals(Clave(d.Ruta), Clave(u.Ruta), StringComparison.OrdinalIgnoreCase));
            var primero = conocido ?? u;
            if (vistos.Add(Clave(primero.Ruta))) yield return primero;
        }
        foreach (var d in conocidos)
            if (vistos.Add(Clave(d.Ruta))) yield return d;
    }

    private bool EsLaUltima(DestinoDeExportacion d) => _ultima is { } u && string.Equals(Clave(d.Ruta), Clave(u.Ruta), StringComparison.OrdinalIgnoreCase);

    private void IniciarVigilante()
    {
        if (_vigilante is not null) return;
        // Las memorias que se enchufan o se retiran aparecen solas, sin tocar nada. El aviso llega en una hebra del grupo: se pasa a la de la interfaz.
        var vigilante = new VigilanteDeUnidades(Unidades, TimeSpan.FromSeconds(2));
        vigilante.Cambio += () => Dispatcher.Dispatch(async () =>
        {
            try { if (_paso == Paso.Elegir && IsVisible) await RefrescarDestinosAsync(); }
            catch (Exception ex) { Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ops", "HojaDeExportar.Vigilante", ex); }
        });
        _vigilante = vigilante;
        _ = Task.Run(vigilante.Iniciar);
    }

    private void DetenerVigilante()
    {
        _vigilante?.Dispose();
        _vigilante = null;
    }

    private async Task RefrescarDestinosAsync()
    {
        var version = _version;
        await BuscarDestinosAsync();
        if (version != _version || _paso != Paso.Elegir) return;
        Pintar();
    }

    // =============================================================================================================== pintar cada paso

    private void Pintar()
    {
        _cuerpo.Clear();
        _pie.Clear();
        switch (_paso)
        {
            case Paso.Preparando: PintarPreparando(); break;
            case Paso.SinAlcance: PintarSinAlcance(); break;
            case Paso.Elegir: PintarElegir(); break;
            case Paso.Confirmar: PintarConfirmar(); break;
            case Paso.Guardando: PintarGuardando(); break;
            case Paso.Resultado: PintarResultado(); break;
        }
    }

    private void Boton(string texto, Ds.Rango rango, Func<Task> alPulsar, string id, bool activo = true, double? ancho = null)
    {
        var (boton, vista) = ExamenUi.Accion(texto, rango, ReportesUi.Seguro(nameof(HojaDeExportar), id, alPulsar), ancho, id);
        if (!activo) Ds.Habilitar(boton, false);
        _pie.Add(vista);
    }

    private void PintarPreparando()
    {
        _titulo.Text = "Guardar el reporte en un archivo";
        _subtitulo.Text = string.Empty;
        _cuerpo.Add(Ds.Secundario("Preparando las opciones…", 16));
        Boton("Cancelar", Ds.Rango.Quiet, () => { Cerrar(); return Task.CompletedTask; }, "exportar-cancelar");
    }

    private void PintarSinAlcance()
    {
        _titulo.Text = "No se pudo preparar el archivo";
        _subtitulo.Text = string.Empty;
        _cuerpo.Add(ExamenUi.Aviso("El aula no contestó como se esperaba", _nota, Tono.Ambar));
        Boton("Reintentar", Ds.Rango.Primary, PrepararAsync, "exportar-reintentar");
        Boton("Cerrar", Ds.Rango.Quiet, () => { Cerrar(); return Task.CompletedTask; }, "exportar-cancelar");
    }

    // ---------------------------------------------------------------------------------------------------- 1 · elegir

    private void PintarElegir()
    {
        var alcance = _alcance!;
        _titulo.Text = "Guardar el reporte en un archivo";
        _subtitulo.Text = alcance.Titulo;

        if (!string.IsNullOrWhiteSpace(_nota))
            _cuerpo.Add(ExamenUi.Aviso(_nota!, null, Tono.Ambar));

        // --- formato
        _cuerpo.Add(EstudioUi.Eyebrow("FORMATO"));
        var formatos = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 10 };
        var disponibles = alcance.Formatos.Count > 0 ? alcance.Formatos : [FormatosDeExportacion.Xlsx, FormatosDeExportacion.Csv];
        for (var i = 0; i < disponibles.Count && i < 2; i++)
            formatos.Add(TarjetaDeFormato(disponibles[i]), i, 0);
        _cuerpo.Add(formatos);

        // --- razón (sólo si el administrador la exige; se elige, no se escribe)
        if (alcance.Politica.ExigirRazon)
        {
            _cuerpo.Add(EstudioUi.Eyebrow("¿PARA QUÉ LO VAS A GUARDAR?"));
            var fila = EstudioUi.Envolver();
            foreach (var razon in alcance.Politica.Razones)
            {
                var codigo = razon.Codigo;
                fila.Add(EstudioUi.Chip(razon.Etiqueta, _razon == codigo, ReportesUi.Seguro(nameof(HojaDeExportar), "Razon", () => { _razon = codigo; Pintar(); return Task.CompletedTask; }), $"exportar-razon-{codigo}"));
            }
            _cuerpo.Add(fila);
            if (_razon is null) _cuerpo.Add(Ds.Secundario("El administrador del colegio pide elegir una para poder continuar.", 13));
        }

        // --- destino
        _cuerpo.Add(EstudioUi.Eyebrow("DÓNDE GUARDARLO"));
        var herramientas = ExamenUi.Fila();
        herramientas.Add(ExamenUi.Accion("Buscar de nuevo", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(HojaDeExportar), "Buscar", RefrescarDestinosAsync), null, "exportar-buscar", 52).Vista);
        herramientas.Add(ExamenUi.Accion("Elegir otra carpeta…", Ds.Rango.Secondary, ReportesUi.Seguro(nameof(HojaDeExportar), "OtraCarpeta", ElegirOtraCarpetaAsync), null, "exportar-otra-carpeta", 52).Vista);
        _cuerpo.Add(herramientas);
        if (_busqueda?.Aviso is { } aviso)
            _cuerpo.Add(ExamenUi.Aviso(aviso, null, _busqueda.ExtraiblesOcultosPorPolitica ? Tono.Ambar : Tono.Info));
        var todos = Lista().ToList();
        var atajos = todos.Where(d => d.EsAtajo).OrderBy(d => Array.IndexOf(new[] { "atajo:documentos", "atajo:escritorio", "atajo:descargas" }, d.Id)).ToList();
        if (atajos.Count > 0)
        {
            var fila = new Grid { ColumnSpacing = 8 };
            for (var i = 0; i < atajos.Count; i++)
            {
                fila.ColumnDefinitions.Add(new ColumnDefinition(GridLength.Star));
                fila.Add(FichaDeAtajo(atajos[i]), i, 0);
            }
            _cuerpo.Add(fila);
        }
        foreach (var destino in todos.Where(d => !d.EsAtajo))
            _cuerpo.Add(FilaDeDestino(destino));

        var listo = _elegido is not null && (!alcance.Politica.ExigirRazon || _razon is not null);
        Boton("Cancelar", Ds.Rango.Quiet, () => { Cerrar(); return Task.CompletedTask; }, "exportar-cancelar");
        Boton("Continuar", Ds.Rango.Primary, ContinuarAsync, "exportar-continuar", listo);
    }

    private View TarjetaDeFormato(string formato)
    {
        var (titulo, descripcion) = TextoDeExportacion.Formato(formato);
        if (_alcance is { Empaquetado: true } empaquetado) descripcion = $"Un archivo por estudiante ({empaquetado.Archivos}), todos en un zip.";
        var pila = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label { Text = _formato == formato ? $"✓  {titulo}" : titulo, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta });
        pila.Add(Ds.Secundario(descripcion, 13));
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        fila.Add(new Image { Source = formato == FormatosDeExportacion.Csv ? "reportes_csv.png" : "reportes_xlsx.png", WidthRequest = 40, HeightRequest = 40, VerticalOptions = LayoutOptions.Center }, 0, 0);
        fila.Add(pila, 1, 0);
        var elegido = _formato == formato;
        return ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(HojaDeExportar), "Formato", async () =>
        {
            if (_formato == formato) return;
            _formato = formato;
            Pintar();
            await Task.CompletedTask;
        }), $"Formato {titulo}", $"exportar-formato-{formato}", Colors.White, new Thickness(14, 12), elegido);
    }

    /// <summary>Un atajo (Documentos, Escritorio, Descargas) como una ficha compacta: icono y nombre, para que las unidades de abajo no queden fuera de la vista.</summary>
    private View FichaDeAtajo(DestinoDeExportacion destino)
    {
        var elegido = _elegido?.Id == destino.Id;
        var fila = new HorizontalStackLayout { Spacing = 10, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center };
        fila.Add(new Image { Source = IconoDe(destino), WidthRequest = 26, HeightRequest = 26, VerticalOptions = LayoutOptions.Center });
        fila.Add(new Label { Text = elegido ? $"✓  {destino.Nombre}" : destino.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 15, TextColor = Ds.Tinta, VerticalOptions = LayoutOptions.Center, LineBreakMode = LineBreakMode.TailTruncation });
        var ficha = ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(HojaDeExportar), "Atajo", () => { _elegido = destino; _nota = null; Pintar(); return Task.CompletedTask; }),
            $"{destino.Nombre}. {destino.Ruta}", $"exportar-destino-{destino.Id}", Colors.White, new Thickness(8, 12), elegido);
        ficha.MinimumHeightRequest = 52;
        return ficha;
    }

    private View FilaDeDestino(DestinoDeExportacion destino)
    {
        var elegido = _elegido?.Id == destino.Id;
        var pila = new VerticalStackLayout { Spacing = 1, VerticalOptions = LayoutOptions.Center };
        pila.Add(new Label { Text = destino.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
        var detalle = DetalleDe(destino);
        if (!string.IsNullOrWhiteSpace(detalle))
            pila.Add(new Label { Text = detalle, FontFamily = Ds.FuenteRegular, FontSize = 13, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.MiddleTruncation });

        var marcas = new HorizontalStackLayout { Spacing = 8, VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.End };
        if (EsLaUltima(destino)) marcas.Add(ExamenUi.Pildora("Última vez", Tono.Neutro, 12));
        if (TextoDeExportacion.Marca(destino.Tipo) is { } marca) marcas.Add(ExamenUi.Pildora(marca, destino.Tipo == TipoDeDestino.Extraible ? Tono.Info : Tono.Violeta, 12));
        if (elegido) marcas.Add(new Label { Text = "✓", FontFamily = Ds.FuenteMedia, FontSize = 20, TextColor = Ds.Exito, VerticalOptions = LayoutOptions.Center });

        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(40), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12, MinimumHeightRequest = 44 };
        fila.Add(new Image { Source = IconoDe(destino), WidthRequest = 30, HeightRequest = 30, VerticalOptions = LayoutOptions.Center }, 0, 0);
        fila.Add(pila, 1, 0);
        fila.Add(marcas, 2, 0);
        return ReportesUi.Tocable(fila, ReportesUi.Seguro(nameof(HojaDeExportar), "Destino", () => { _elegido = destino; _nota = null; Pintar(); return Task.CompletedTask; }),
            $"{destino.Nombre}{(TextoDeExportacion.Marca(destino.Tipo) is { } m ? ", " + m : string.Empty)}", $"exportar-destino-{destino.Id}", Colors.White, new Thickness(14, 10), elegido);
    }

    private static string? DetalleDe(DestinoDeExportacion d)
    {
        if (d.Letra is not null)
        {
            var libre = d.LibreBytes is { } l ? $"{FormatoDeReportes.Tamano(l)} libres" : null;
            var total = d.TotalBytes is { } t ? $"de {FormatoDeReportes.Tamano(t)}" : null;
            return string.Join(" · ", new[] { d.Letra, libre is null ? null : total is null ? libre : $"{libre} {total}" }.Where(x => !string.IsNullOrEmpty(x)));
        }
        return d.Ruta;
    }

    private static string IconoDe(DestinoDeExportacion d) => d.Id switch
    {
        "atajo:documentos" => "reportes_documentos.png",
        "atajo:escritorio" => "reportes_escritorio.png",
        "atajo:descargas" => "reportes_descargas.png",
        _ => d.Tipo switch
        {
            TipoDeDestino.Extraible => "reportes_usb.png",
            TipoDeDestino.Red => "reportes_red.png",
            _ => d.Letra is not null ? "reportes_disco.png" : "reportes_carpeta.png",
        },
    };

    /// <summary>
    /// «Elegir otra carpeta…»: el selector de carpetas de Windows (táctil, ya viene en el Explorador). La política del administrador vale también aquí: una carpeta de una memoria USB o de red
    /// que está desactivada se rechaza y se dice por qué.
    /// </summary>
    private async Task ElegirOtraCarpetaAsync()
    {
        var ruta = await SelectorDeCarpeta.ElegirAsync();
        if (string.IsNullOrWhiteSpace(ruta)) return;
        var tipo = await Task.Run(() => ClasificadorDeRuta.Clasificar(ruta, Unidades));
        if (!Permitido(tipo))
        {
            _nota = tipo == TipoDeDestino.Extraible ? AvisosDeDestinos.ExtraiblesDesactivados : AvisosDeDestinos.RedDesactivada;
            Pintar();
            return;
        }
        var nombre = System.IO.Path.GetFileName(ruta.TrimEnd('\\', '/'));
        _carpetaAMano = new DestinoDeExportacion($"carpeta:{ruta}", string.IsNullOrWhiteSpace(nombre) ? ruta : nombre, ruta, tipo, null, null, null, EsAtajo: false, Listo: true);
        _elegido = _carpetaAMano;
        _nota = null;
        Pintar();
    }

    // ---------------------------------------------------------------------------------------------------- 2 · confirmar

    private async Task ContinuarAsync()
    {
        if (_elegido is null || _flujo is null) return;
        var version = _version;
        _paso = Paso.Preparando;
        Pintar();
        // El nombre, las filas y lo que trae pueden cambiar con el formato: se vuelve a pedir el alcance (no genera ni registra nada).
        var alcance = await _flujo.AlcanceAsync(_formato);
        if (version != _version) return;
        if (alcance is null)
        {
            _nota = MensajesDeReportes.De(_flujo.UltimoError);
            _paso = Paso.Elegir;
            Pintar();
            return;
        }
        _alcance = alcance;
        _nota = null;
        _paso = Paso.Confirmar;
        Pintar();
    }

    private void PintarConfirmar()
    {
        var alcance = _alcance!;
        var destino = _elegido!;
        var texto = TextoDeExportacion.Confirmacion(alcance, destino);
        _titulo.Text = "Confirma antes de guardar";
        _subtitulo.Text = string.Empty;

        _cuerpo.Add(new Label { Text = texto.Frase, FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "exportar-alcance" });
        _cuerpo.Add(ExamenUi.Aviso(texto.Advertencia, null, texto.Nominal ? Tono.Ambar : Tono.Info));
        if (texto.Privacidad is { } privacidad) _cuerpo.Add(ExamenUi.Aviso("Privacidad", privacidad, Tono.Info));
        var (formatoTitulo, _) = TextoDeExportacion.Formato(_formato);
        _cuerpo.Add(ExamenUi.Dato("Formato", alcance.Empaquetado ? $"{formatoTitulo} · {alcance.Archivos} archivos (uno por estudiante) en un zip" : formatoTitulo, 110));
        if (alcance.Plantilla is { Length: > 0 } plantilla) _cuerpo.Add(ExamenUi.Dato("Plantilla", plantilla, 110));
        _cuerpo.Add(ExamenUi.Dato("Nombre", alcance.NombreSugerido, 110));
        _cuerpo.Add(ExamenUi.Dato("Datos al", FormatoDeReportes.FechaLarga(alcance.Corte.En), 110));
        if (alcance.Corte.Incompleto || alcance.Corte.Integracion.Incompleta)
            _cuerpo.Add(ExamenUi.Aviso("Incompleto", alcance.Corte.Integracion.MotivoLinea + ". Esto también queda escrito dentro del archivo.", Tono.Ambar));
        if (_razon is not null && alcance.Politica.Razones.FirstOrDefault(r => r.Codigo == _razon) is { } razon)
            _cuerpo.Add(ExamenUi.Dato("Motivo", razon.Etiqueta, 110));

        Boton("Cambiar", Ds.Rango.Quiet, () => { _paso = Paso.Elegir; Pintar(); return Task.CompletedTask; }, "exportar-cambiar");
        Boton("Guardar", Ds.Rango.Primary, GuardarAsync, "exportar-guardar");
    }

    // ---------------------------------------------------------------------------------------------------- 3 · guardando

    private async Task GuardarAsync()
    {
        if (_elegido is null || _flujo is null) return;
        var version = _version;
        var destino = _elegido;
        var flujo = _flujo;
        _avance = 0;
        _ultimoPintado = -1;
        _paso = Paso.Guardando;
        Pintar();
        _cancelacion = new CancellationTokenSource();
        var progreso = new Progress<double>(valor => { _avance = valor; ActualizarAvance(); });
        ResultadoDelGuardado resultado;
        try
        {
            resultado = await flujo.GuardarAsync(new DestinoElegido(destino.Ruta, destino.Tipo), _formato, _razon, progreso, _cancelacion.Token);
        }
        catch (Exception ex)
        {
            Avacom.Lms.Core.Services.RegistroDeFallos.Escribir("ops", "HojaDeExportar.Guardar", ex);
            resultado = new ResultadoDelGuardado(EstadoDelGuardado.ArchivoDanado, "No se pudo guardar el reporte.", "Vuelve a intentarlo.", Detalle: ex.GetType().Name);
        }
        if (version != _version) return;
        _cancelacion = null;
        _resultado = resultado;
        if (resultado.Escrito) _preferencias.RecordarCarpeta(ReportesUi.Actor, destino.Ruta);
        if (resultado.Estado == EstadoDelGuardado.Cancelado)
        {
            _nota = "Cancelaste el guardado. No se guardó nada.";
            _paso = Paso.Elegir;
            Pintar();
            return;
        }
        _paso = Paso.Resultado;
        Pintar();
    }

    private void PintarGuardando()
    {
        _titulo.Text = "Guardando el reporte…";
        _subtitulo.Text = string.Empty;
        _cuerpo.Add(Ds.Secundario(_elegido?.Tipo == TipoDeDestino.Extraible ? "No retires la memoria hasta que termine." : "Un momento: se está preparando, guardando y comprobando el archivo.", 16));
        _barraHost = new ContentView { Content = EstudioUi.Barra(_avance, Ds.Exito, 12), VerticalOptions = LayoutOptions.Center };
        _porcentaje = new Label { Text = $"{(int)(_avance * 100)} %", FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, HorizontalTextAlignment = TextAlignment.End, VerticalOptions = LayoutOptions.Center, AutomationId = "exportar-avance" };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(72)], ColumnSpacing = 10 };
        fila.Add(_barraHost, 0, 0);
        fila.Add(_porcentaje, 1, 0);
        _cuerpo.Add(fila);
        Boton("Cancelar", Ds.Rango.Quiet, () =>
        {
            _cancelacion?.Cancel();
            return Task.CompletedTask;
        }, "exportar-cancelar-guardado");
    }

    private void ActualizarAvance()
    {
        if (_paso != Paso.Guardando || Math.Abs(_avance - _ultimoPintado) < 0.01 && _avance < 1) return;
        _ultimoPintado = _avance;
        _barraHost.Content = EstudioUi.Barra(_avance, Ds.Exito, 12);
        _porcentaje.Text = $"{(int)(_avance * 100)} %";
    }

    // ---------------------------------------------------------------------------------------------------- 4 · resultado

    private void PintarResultado()
    {
        var r = _resultado!;
        if (r.Escrito) PintarGuardado(r);
        else PintarFallo(r);
    }

    private void PintarGuardado(ResultadoDelGuardado r)
    {
        var (titulo, detalle, recordatorio) = TextoDeExportacion.Exito(r.RutaFinal!, r.Bytes, r.Tipo ?? TipoDeDestino.CarpetaLocal);
        _titulo.Text = "Listo";
        _subtitulo.Text = string.Empty;

        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(56), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        cabecera.Add(new Image { Source = "reportes_ok.png", WidthRequest = 48, HeightRequest = 48, VerticalOptions = LayoutOptions.Start }, 0, 0);
        var texto = new VerticalStackLayout { Spacing = 4 };
        texto.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.CharacterWrap, AutomationId = "exportar-guardado" });
        texto.Add(Ds.Secundario(detalle, 14));
        cabecera.Add(texto, 1, 0);
        _cuerpo.Add(cabecera);
        if (recordatorio is not null) _cuerpo.Add(ExamenUi.Aviso(recordatorio, null, Tono.Info));
        if (r.Estado == EstadoDelGuardado.GuardadoSinConfirmar)
            _cuerpo.Add(ExamenUi.Aviso(r.Mensaje, r.Accion, Tono.Ambar));

        if (r.Estado == EstadoDelGuardado.GuardadoSinConfirmar && _flujo?.HayConfirmacionPendiente == true)
            Boton("Avisar al aula", Ds.Rango.Secondary, AvisarAlAulaAsync, "exportar-avisar");
        Boton("Abrir carpeta", Ds.Rango.Secondary, () => { SelectorDeCarpeta.AbrirCarpetaDe(r.RutaFinal!); return Task.CompletedTask; }, "exportar-abrir-carpeta");
        Boton("Guardar en otro lugar", Ds.Rango.Secondary, GuardarEnOtroLugarAsync, "exportar-otro-lugar");
        Boton("Listo", Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "exportar-listo");
    }

    private async Task AvisarAlAulaAsync()
    {
        if (_flujo is null) return;
        var version = _version;
        var r = await _flujo.ReintentarConfirmacionAsync();
        if (version != _version) return;
        _resultado = r.Escrito ? r with { Tipo = _resultado?.Tipo } : _resultado;
        Pintar();
    }

    /// <summary>«Guardar en otro lugar»: el archivo ya quedó entregado, así que otro destino es un reporte nuevo (se vuelve a generar y a registrar).</summary>
    private async Task GuardarEnOtroLugarAsync()
    {
        _nota = null;
        _elegido = null;
        _resultado = null;
        await RefrescarDestinosAsync();
        _paso = Paso.Elegir;
        Pintar();
    }

    private void PintarFallo(ResultadoDelGuardado r)
    {
        _titulo.Text = r.Estado switch
        {
            EstadoDelGuardado.NoAutorizado => "El aula no permitió guardarlo",
            EstadoDelGuardado.SinConexion => "Sin conexión con el aula",
            EstadoDelGuardado.ArchivoDanado => "El archivo no quedó bien",
            _ => "No se pudo guardar",
        };
        _subtitulo.Text = string.Empty;

        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(44), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        cabecera.Add(new Image { Source = "reportes_aviso.png", WidthRequest = 32, HeightRequest = 32, VerticalOptions = LayoutOptions.Start }, 0, 0);
        var texto = new VerticalStackLayout { Spacing = 4 };
        texto.Add(new Label { Text = r.Mensaje, FontFamily = Ds.FuenteMedia, FontSize = 18, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "exportar-fallo" });
        if (!string.IsNullOrWhiteSpace(r.Accion)) texto.Add(Ds.Secundario(r.Accion!, 15));
        cabecera.Add(texto, 1, 0);
        _cuerpo.Add(cabecera);
        _cuerpo.Add(Ds.Secundario("El reporte sigue en pantalla, tal como estaba.", 13));

        // Los botones son los que nombra la frase de arriba («toca Guardar otra vez, o elige otro destino»). «Guardar otra vez» repite sobre el MISMO destino sin generar de nuevo el archivo ya bajado:
        // sirve a lo que se arregla afuera (se vuelve a conectar la memoria, se libera espacio, vuelve la red, se quita el seguro) y a una conexión caída o un archivo dañado. «Elegir otro destino»
        // queda al lado cuando hay otro destino que elegir; si lo que falla es el permiso del reporte mismo, cambiar de carpeta no lo arregla y sólo se ofrece cerrar.
        var botones = TextoDeExportacion.BotonesPara(r);
        if (botones.GuardarOtraVez) Boton("Guardar otra vez", Ds.Rango.Primary, GuardarAsync, "exportar-reintentar");
        if (botones.ElegirOtroDestino)
            Boton("Elegir otro destino", botones.GuardarOtraVez ? Ds.Rango.Secondary : Ds.Rango.Primary, () => ElegirOtroDestinoAsync(botones.ReleerLaPolitica), "exportar-otro-destino");
        var haySalida = botones.GuardarOtraVez || botones.ElegirOtroDestino;
        Boton(haySalida ? "Cancelar" : "Cerrar", haySalida ? Ds.Rango.Quiet : Ds.Rango.Primary, () => { Cerrar(); return Task.CompletedTask; }, "exportar-cancelar");
    }

    /// <summary>
    /// Vuelve al paso de elegir sin generar de nuevo el archivo ya bajado. Si el aula rechazó el destino o pidió una razón, lo que valía al abrir la hoja cambió (la política del administrador): se
    /// vuelve a leer, para que lo que se ofrece sea lo que el aula acepta ahora y no se repita el mismo rechazo.
    /// </summary>
    private async Task ElegirOtroDestinoAsync(bool politicaCambio)
    {
        _nota = null;
        _resultado = null;
        if (politicaCambio)
        {
            _elegido = null;
            await PrepararAsync();
            return;
        }
        await RefrescarDestinosAsync();
        _paso = Paso.Elegir;
        Pintar();
    }
}
