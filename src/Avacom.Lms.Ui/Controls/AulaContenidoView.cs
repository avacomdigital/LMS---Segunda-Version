using System.Net;
using System.Text.Json;
using Avacom.Lms.Core.Models;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ui.Design;
using Microsoft.Maui.Controls.Shapes;

namespace Avacom.Lms.Ui.Controls;

/// <summary>
/// El visor de la clase: pinta un <see cref="ObjetoAula"/> según su <c>componente</c>.
///
/// <list type="bullet">
/// <item><c>presentacion</c> · la lámina en foco con sus bloques y «Lámina N de M».</item>
/// <item><c>lectura</c> · la página en foco (texto, audio, pdf).</item>
/// <item><c>laboratorio_web</c> · cabecera pedagógica + <see cref="WebView"/> acotada al host del backend.</item>
/// <item><c>actividad</c> · instrucciones, ajustes y las preguntas en vista previa (sin claves).</item>
/// <item><c>examen</c> · tarjeta atenuada: lo aplica MOD-010.</item>
/// </list>
///
/// No conoce HTTP: recibe el objeto y una función que convierte las rutas relativas del
/// backend en URL absolutas. En modo docente (o con el seguimiento liberado) muestra los
/// mandos anterior/siguiente y avisa con <see cref="UnidadPedida"/>; en seguimiento sólo pinta
/// lo que le dicta el foco. Las WebView de una unidad (audio, video, pdf, laboratorio) viven juntas y se
/// vacían todas al cambiar de unidad; un reproductor que no puede reproducir su archivo lo dice en pantalla,
/// lo anota en el archivo de fallos y avisa por <see cref="MedioFallido"/>.
/// </summary>
public sealed class AulaContenidoView : ContentView
{
    private readonly Grid _raiz = new() { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(GridLength.Auto)] };
    private readonly ContentView _cuerpo = new();
    private readonly Grid _mandos = new() { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12, Padding = new Thickness(0, 12, 0, 0) };
    private readonly List<WebView> _webs = [];
    private string? _hostPermitido;

    // Lo que la unidad en pantalla tiene en vuelo (descarga de imágenes, sondeo de un medio que falló): se cancela al cambiar de unidad.
    private CancellationTokenSource _cancelarMedios = new();

    // Contrato 2: la cátedra o explicación maquetada por el curso vive en UNA WebView por objeto; cambiar de lámina es cambiar el `#s{n}`
    // de la misma página, no recargarla (recargar parpadea y pierde lo que el html del curso tuviera en marcha, como un video).
    private WebView? _webHtml;
    private string? _webHtmlPagina;
    private View? _htmlContenedor;
    // Un View sólo puede colgar de un padre. El encabezado nace con SU contenedor y muere con él: reutilizarlo en el contenedor de otra página
    // (cátedra → teoría) lo dejaba colgando del anterior y WinUI lanzaba COMException 0x800F1000 al montar el nuevo (Bugfix 02).
    private ContentView? _htmlCabecera;

    // Espacio útil para un medio (video o imagen de un bloque) según lo que mide el visor AHORA. Se mide en `_cuerpo`
    // y no en el contenedor del medio: el medio vive dentro de un ScrollView y su alto cambia el alto de la página, pero
    // no el tamaño del visor, así que no hay realimentación (medio → barra de desplazamiento → ancho → medio…) que dé
    // «Layout cycle detected» ni deje la capa del video con un tamaño viejo. Ver 02-classroom-engine/responsive.md.
    private double _anchoUtil, _altoUtil;
    private readonly List<Action> _ajustes = [];
    private int _versionAjuste;

    /// <summary>Esquema con el que el HTML de un reproductor avisa a MAUI (`avacom-aula://fallo?tipo=audio&codigo=3`).</summary>
    public const string EsquemaAviso = "avacom-aula";

    /// <summary>Nombre de la app para el archivo de fallos (`fallos-ops.log`, `fallos-student.log`). Lo fija cada app al arrancar.</summary>
    public static string NombreApp { get; set; } = "aula";

    /// <summary>Un medio no se pudo reproducir (archivo dañado, formato no soportado o no llegó). Ya quedó anotado en el archivo de fallos.</summary>
    public event EventHandler<FalloDeMedio>? MedioFallido;

    public AulaContenidoView()
    {
        _raiz.Add(_cuerpo, 0, 0);
        _raiz.Add(_mandos, 0, 1);
        Content = _raiz;
        _cuerpo.SizeChanged += (_, _) => AlCambiarElVisor();
        // El perfil de pantalla (selector de OPS) acota los medios en todos los visores abiertos; se suelta al salir de pantalla.
        Loaded += (_, _) => AjustesDePantalla.Cambio += AlCambiarElPerfil;
        Unloaded += (_, _) => AjustesDePantalla.Cambio -= AlCambiarElPerfil;
        MostrarVacio();
    }

    private void AlCambiarElPerfil(object? sender, PerfilDePantalla perfil) => Dispatcher.Dispatch(AjustarMedios);

    /// <summary>El visor cambió de tamaño (ventana, escala de Windows, reorientación): se recalcula el espacio útil y, ya asentado, se reajustan los medios.</summary>
    private void AlCambiarElVisor()
    {
        _anchoUtil = Math.Max(0, _cuerpo.Width - 2 * 28 * Escala);
        _altoUtil = Math.Max(0, _cuerpo.Height - PerfilDePantalla.MargenVertical);
        // Arrastrar el borde de la ventana dispara decenas de cambios por segundo: sólo cuenta el último, 120 ms después.
        var version = ++_versionAjuste;
        Dispatcher.DispatchDelayed(TimeSpan.FromMilliseconds(120), () => { if (version == _versionAjuste) AjustarMedios(); });
    }

    private void AjustarMedios()
    {
        foreach (var ajuste in _ajustes.ToArray()) ajuste();
    }

    /// <summary>Convierte una ruta relativa del backend (`/api/aula/…`) en URL absoluta.</summary>
    public Func<string, Uri>? Absoluta { get; set; }

    private bool _puedeNavegar;
    private IReadOnlyList<UnidadAula>? _unidadesEnPantalla;
    private int _indiceEnPantalla;

    /// <summary>
    /// Docente o estudiante con navegación libre: se muestran anterior/siguiente. Cambiarlo repinta los mandos
    /// de la unidad en pantalla al instante: liberar o activar el seguimiento no puede esperar al siguiente
    /// cambio de selector del profesor (visto en la prueba del 2026-09-28, 07 · Contrato de lanzamiento).
    /// </summary>
    public bool PuedeNavegar
    {
        get => _puedeNavegar;
        set
        {
            if (_puedeNavegar == value) return;
            _puedeNavegar = value;
            if (_unidadesEnPantalla is not null) PintarMandos(_unidadesEnPantalla, _indiceEnPantalla);
            else _mandos.IsVisible = false;
        }
    }

    /// <summary>Tamaño base del texto: 18 en tableta, 24 en la pantalla del aula.</summary>
    public double Escala { get; set; } = 1.0;

    public ObjetoAula? Objeto { get; private set; }
    public string? UnidadRef { get; private set; }

    /// <summary>El usuario pidió otra unidad (lámina o página): quien escucha declara el foco.</summary>
    public event EventHandler<string>? UnidadPedida;

    public void MostrarVacio(string titulo = "Nada proyectado todavía", string detalle = "Toca un objeto de la secuencia para proyectarlo.")
    {
        Objeto = null;
        UnidadRef = null;
        _unidadesEnPantalla = null;
        LimpiarWeb();
        var pila = new VerticalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Padding = 32 };
        pila.Add(new Label { Text = "⬡", FontSize = 54, TextColor = Ds.Rojo, HorizontalTextAlignment = TextAlignment.Center });
        pila.Add(Ds.Titulo(titulo, 22 * Escala));
        pila.Add(Ds.Secundario(detalle, 16 * Escala));
        ((Label)pila.Children[1]).HorizontalTextAlignment = TextAlignment.Center;
        ((Label)pila.Children[2]).HorizontalTextAlignment = TextAlignment.Center;
        _cuerpo.Content = pila;
        _mandos.Clear();
        _mandos.IsVisible = false;
    }

    /// <summary>
    /// Pinta el objeto en foco. Nunca lanza: un fallo al montar la pantalla se anota como ERROR con todo lo que hace falta para entenderlo
    /// (qué objeto, qué unidad, qué página del curso, qué excepción y dónde) y la clase sigue con una tarjeta que lo dice y deja reintentar.
    /// Lo llaman el sondeo, el canal en tiempo real y los toques del profesor: una excepción aquí cerraba la aplicación entera en medio de la clase.
    /// </summary>
    public void Mostrar(ObjetoAula objeto, string? unidadRef)
    {
        try { MostrarObjeto(objeto, unidadRef); }
        catch (Exception ex)
        {
            AnotarFalloDelVisor(objeto, unidadRef, ex, conRespaldo: false);
            try { LimpiarWeb(); } catch { /* ya está anotado: lo que importa es no tumbar la aplicación */ }
            _unidadesEnPantalla = null;
            _mandos.IsVisible = false;
            _cuerpo.Content = TarjetaDeFalloDelVisor(objeto, unidadRef);
        }
    }

    private void MostrarObjeto(ObjetoAula objeto, string? unidadRef)
    {
        // La misma cátedra maquetada, otra lámina: la WebView del html se queda y sólo cambia de sección.
        var conservarHtml = _webHtml is not null && Objeto?.ObjetoRef == objeto.ObjetoRef && objeto.TieneHtml;
        Objeto = objeto;
        _unidadesEnPantalla = null;
        LimpiarWeb(conservarHtml);
        switch (objeto.Componente)
        {
            case "presentacion":
            case "lectura":
                MostrarUnidades(objeto, unidadRef);
                break;
            case "laboratorio_web":
                UnidadRef = null;
                _cuerpo.Content = Laboratorio(objeto);
                _mandos.IsVisible = false;
                break;
            case "actividad":
                UnidadRef = null;
                _cuerpo.Content = new ScrollView { Content = Actividad(objeto) };
                _mandos.IsVisible = false;
                break;
            case "examen":
                UnidadRef = null;
                _cuerpo.Content = FueraDeAlcance(objeto);
                _mandos.IsVisible = false;
                break;
            default:
                UnidadRef = null;
                _cuerpo.Content = Ds.Tarjeta(new VerticalStackLayout
                {
                    Spacing = 6,
                    Children = { Ds.Titulo("Este contenido todavía no tiene visor", 22 * Escala), Ds.Secundario($"Tipo «{objeto.Tipo}» · componente «{objeto.Componente}».") },
                });
                _mandos.IsVisible = false;
                break;
        }
    }

    // ----------------------------------------------------------- láminas / páginas

    private void MostrarUnidades(ObjetoAula objeto, string? unidadRef)
    {
        var unidades = objeto.Unidades;
        if (unidades.Count == 0)
        {
            _cuerpo.Content = Ds.Tarjeta(Ds.Secundario("Esta presentación no tiene láminas."));
            _mandos.IsVisible = false;
            return;
        }
        var indice = Math.Max(0, unidades.ToList().FindIndex(u => u.UnidadRef == unidadRef));
        var unidad = unidades[indice];
        UnidadRef = unidad.UnidadRef;
        _unidadesEnPantalla = unidades;
        _indiceEnPantalla = indice;

        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cabecera.Add(Ds.Secundario($"{objeto.ComponenteLegible} · {objeto.Titulo}", 15 * Escala), 0, 0);
        cabecera.Add(Ds.Pildora(objeto.Componente == "presentacion" ? $"Lámina {indice + 1} de {unidades.Count}" : $"Página {indice + 1} de {unidades.Count}", Ds.Categoria(objeto.Componente)), 1, 0);

        // Contrato 2: el curso trae la cátedra o explicación maquetada (html con sus estilos). Se muestra ESA página, en la sección de la
        // lámina en foco; los bloques quedan de respaldo si el html falta en la biblioteca.
        if (objeto.TieneHtml && Absoluta is not null && !string.IsNullOrWhiteSpace(unidad.UrlHtml))
        {
            try
            {
                MostrarHtml(objeto, unidad, cabecera);
                PintarMandos(unidades, indice);
                return;
            }
            catch (Exception ex)
            {
                // La página maquetada no se pudo montar: se anota (ERROR, con la causa) y la clase sigue con los bloques del curso, que son la
                // verdad del contenido. Con las WebView a medio montar, se vacía todo antes de pintar el respaldo.
                AnotarFalloDelVisor(objeto, unidad.UnidadRef, ex, conRespaldo: true, unidad);
                LimpiarWeb();
            }
        }

        var pila = new VerticalStackLayout { Spacing = 18 * Escala, Padding = new Thickness(28 * Escala, 24 * Escala) };
        pila.Add(cabecera);
        if (!string.IsNullOrWhiteSpace(unidad.Titulo)) pila.Add(Ds.Titulo(unidad.Titulo!, 30 * Escala));
        foreach (var bloque in unidad.Bloques) pila.Add(Bloque(bloque));
        if (unidad.DuracionSeg is > 0) pila.Add(Ds.Secundario($"Referencia: ~{Math.Max(1, unidad.DuracionSeg.Value / 60)} min", 14 * Escala));

        _cuerpo.Content = new ScrollView { Content = Ds.Tarjeta(pila, Ds.RadioGrande, new Thickness(0)) };
        PintarMandos(unidades, indice);
    }

    /// <summary>
    /// La página html del curso (`entry`) en una WebView acotada al host del aula, en la sección `#s{n}` de la unidad en foco. La misma
    /// página con otra sección sólo cambia el <c>location.hash</c>: el html del curso decide qué sección se ve (<c>:target</c> o su propio
    /// guion). Una presentación no se desplaza (cada lámina cabe en pantalla); una lectura sí.
    /// </summary>
    private void MostrarHtml(ObjetoAula objeto, UnidadAula unidad, View cabecera)
    {
        var destino = Absoluta!(unidad.UrlHtml!);
        var pagina = destino.GetLeftPart(UriPartial.Query);                 // sin el `#s{n}`
        var seccion = destino.Fragment;                                      // `#s{n}`
        if (_webHtml is not null && _htmlContenedor is not null && _htmlCabecera is not null && string.Equals(_webHtmlPagina, pagina, StringComparison.Ordinal))
        {
            // Misma página, otra sección: sin recargar. Sólo cambia el texto del encabezado («Lámina 7 de 19»).
            _htmlCabecera.Content = cabecera;
            var hash = seccion.Replace("'", string.Empty).Replace("\\", string.Empty);
            _ = _webHtml.EvaluateJavaScriptAsync($"(function(){{try{{location.hash='{hash}';}}catch(e){{}}}})();");
            if (!ReferenceEquals(_cuerpo.Content, _htmlContenedor)) _cuerpo.Content = _htmlContenedor;
            return;
        }

        // Otra página (de la cátedra a la teoría, o de vuelta): contenedor, encabezado y WebView NUEVOS, y la anterior se apaga. Nada del contenedor
        // viejo se reutiliza: un View sólo puede colgar de un padre y WinUI lanza COMException al montarlo en dos a la vez.
        if (_webHtml is not null)
        {
            try { _webHtml.Source = new HtmlWebViewSource { Html = "<html><body></body></html>" }; } catch { }
            _webs.Remove(_webHtml);
        }
        _webHtml = NuevaWeb(null, null, desplazable: objeto.Componente != "presentacion");
        WebViewAjustes.FijarEscala(_webHtml);   // Android: sin zoom-out, para que la página vea el tamaño real de su recuadro (Bugfix 02)
        _hostPermitido = destino.GetLeftPart(UriPartial.Authority);
        _webHtmlPagina = pagina;
        _webHtml.Source = new UrlWebViewSource { Url = destino.AbsoluteUri };
        var marco = new Border
        {
            StrokeThickness = 0, BackgroundColor = Colors.White, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioGrande },
            Content = _webHtml,
        };
        _htmlCabecera = new ContentView { Content = cabecera, Padding = new Thickness(28 * Escala, 12 * Escala, 28 * Escala, 0) };
        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)], RowSpacing = 10 * Escala };
        raiz.Add(_htmlCabecera, 0, 0);
        raiz.Add(marco, 0, 1);
        _htmlContenedor = raiz;
        _cuerpo.Content = raiz;
    }

    private void PintarMandos(IReadOnlyList<UnidadAula> unidades, int indice)
    {
        _mandos.Clear();
        _mandos.IsVisible = PuedeNavegar;
        if (!PuedeNavegar) return;
        var anterior = Ds.Boton("◀  Anterior", Ds.Rango.Secondary, (_, _) => { if (indice > 0) UnidadPedida?.Invoke(this, unidades[indice - 1].UnidadRef); });
        var siguiente = Ds.Boton("Siguiente  ▶", Ds.Rango.Secondary, (_, _) => { if (indice < unidades.Count - 1) UnidadPedida?.Invoke(this, unidades[indice + 1].UnidadRef); });
        var capsulaAnterior = Ds.Capsula(anterior);
        var capsulaSiguiente = Ds.Capsula(siguiente);
        Ds.Habilitar(anterior, indice > 0, 0.45);
        Ds.Habilitar(siguiente, indice < unidades.Count - 1, 0.45);
        var puntos = new HorizontalStackLayout { Spacing = 8, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center };
        for (var i = 0; i < unidades.Count; i++)
            puntos.Add(new BoxView { WidthRequest = i == indice ? 26 : 10, HeightRequest = 10, CornerRadius = 5, Color = i == indice ? Ds.Rojo : Color.FromArgb("#C7C4BE") });
        _mandos.Add(capsulaAnterior, 0, 0);
        _mandos.Add(puntos, 1, 0);
        _mandos.Add(capsulaSiguiente, 2, 0);
    }

    // ------------------------------------------------------------------ bloques

    private View Bloque(BloqueAula b)
    {
        switch (b.Componente)
        {
            case "titulo":
                return Ds.ConTramos(b.Tramos, b.Texto, (b.Nivel switch { 1 => 32, 2 => 24, _ => 20 }) * Escala);
            case "texto":
            {
                var label = Ds.ConTramos(b.Tramos, b.Texto, 20 * Escala);
                if (b.Estilo == "definition")
                {
                    // La barra roja en la primera columna y el texto en la segunda (sin fijar la columna, el texto caía en la de 6 px y se leía letra por letra).
                    var cuerpo = new Grid { ColumnDefinitions = [new ColumnDefinition(6), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 16 };
                    cuerpo.Add(new BoxView { Color = Ds.Rojo, CornerRadius = 3 }, 0, 0);
                    cuerpo.Add(label, 1, 0);
                    return new Border
                    {
                        BackgroundColor = Ds.PeligroSuave, StrokeThickness = 0, Padding = new Thickness(20, 16),
                        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
                        Content = cuerpo,
                    };
                }
                if (b.Estilo == "highlight")
                    return new Border { BackgroundColor = Ds.AlertaSuave, StrokeThickness = 0, Padding = new Thickness(20, 16), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = label };
                return label;
            }
            case "lista":
            {
                var pila = new VerticalStackLayout { Spacing = 10 };
                var items = b.Items ?? [];
                for (var i = 0; i < items.Count; i++)
                {
                    var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(36), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 8 };
                    fila.Add(new Label { Text = b.Ordenada == true ? $"{i + 1}." : "•", FontSize = 20 * Escala, FontFamily = Ds.FuenteMedia, TextColor = Ds.Rojo }, 0, 0);
                    fila.Add(Ds.ConTramos(b.ItemsTramos is not null && i < b.ItemsTramos.Count ? b.ItemsTramos[i] : null, items[i], 20 * Escala), 1, 0);
                    pila.Add(fila);
                }
                return pila;
            }
            case "formula":
            {
                // Sin motor matemático en la tableta: el backend entrega una lectura del LaTeX («1/3 × 2») en `texto`.
                var pila = new VerticalStackLayout { Spacing = 6 };
                pila.Add(new Border
                {
                    BackgroundColor = Ds.Lienzo, StrokeThickness = 0, Padding = new Thickness(24, 14), HorizontalOptions = LayoutOptions.Center,
                    StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno },
                    Content = new Label { Text = b.Texto, FontSize = 28 * Escala, FontAttributes = FontAttributes.Italic, TextColor = Ds.Tinta, HorizontalTextAlignment = TextAlignment.Center },
                });
                if (!string.IsNullOrWhiteSpace(b.Pie)) pila.Add(Ds.Secundario(b.Pie!, 15 * Escala));
                return pila;
            }
            case "imagen":
                return Imagen(b);
            case "video":
                return Video(b);
            case "audio":
                return Audio(b);
            case "pdf":
                return Pdf(b);
            default:
                return Ds.Alerta_("Bloque sin visor", $"Tipo «{b.Tipo}».", Ds.AlertaSuave, Ds.Tinta);
        }
    }

    private View Imagen(BloqueAula b)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        if (Absoluta is not null && !string.IsNullOrWhiteSpace(b.Url))
        {
            var marco = new Border { StrokeThickness = 0, BackgroundColor = Ds.Lienzo, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioTarjeta } };
            CargarImagen(marco, Absoluta(b.Url!), b.TextoAlternativo, b.MediaRef);
            pila.Add(CajaAjustada(marco, b.Ancho, b.Alto));
        }
        else
        {
            pila.Add(new Border { StrokeThickness = 0, BackgroundColor = Ds.Lienzo, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioTarjeta }, HeightRequest = 360 * Escala });
        }
        if (!string.IsNullOrWhiteSpace(b.Pie)) pila.Add(Ds.Secundario(b.Pie!, 16 * Escala));
        return pila;
    }

    private View Video(BloqueAula b)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        if (Absoluta is null || string.IsNullOrWhiteSpace(b.Url))
            return Ds.Alerta_("Video no disponible", b.Pie, Ds.InfoSuave, Ds.Tinta);
        var url = Absoluta(b.Url!).AbsoluteUri;
        var inv = System.Globalization.CultureInfo.InvariantCulture;
        var fragmento = b.DesdeSeg is not null || b.HastaSeg is not null ? $"#t={b.DesdeSeg ?? 0},{(b.HastaSeg is null ? string.Empty : b.HastaSeg.Value.ToString(inv))}" : string.Empty;
        var pista = !string.IsNullOrWhiteSpace(b.SubtitulosUrl) ? $"<track kind=\"subtitles\" srclang=\"es\" label=\"Español\" src=\"{Absoluta(b.SubtitulosUrl!).AbsoluteUri}\" default>" : string.Empty;
        // Contrato 2: la imagen fija antes de reproducir y las pausas para pensar (`interactions`), serializadas para el guion del reproductor.
        // El serializador escapa `<`, `>` y `&`, así que el JSON puede ir dentro de <script> sin cerrar la etiqueta por accidente.
        var poster = !string.IsNullOrWhiteSpace(b.PosterUrl) ? $" poster=\"{Absoluta(b.PosterUrl!).AbsoluteUri}\"" : string.Empty;
        var pausas = JsonSerializer.Serialize((b.Pausas ?? []).Select(p => new
        {
            pausa_ref = p.PausaRef, en_seg = p.EnSeg, enunciado = p.Enunciado ?? string.Empty,
            opciones = (p.Opciones ?? []).Select(o => new { texto = o.Texto ?? string.Empty, es_respuesta = o.EsRespuesta, explicacion = o.Explicacion ?? string.Empty }),
        }));
        // Recuadro de tamaño fijo, calculado en C# (AjusteDeMedio): el documento llena exactamente la WebView y el video se
        // escala «contain» dentro (cualquier proporción, sin recortar). Nada de flex ni de desplazamiento propio.
        // Además WebView2 debe arrancar sin las superposiciones de video de DirectComposition (WebViewAjustes): con ellas el
        // fotograma se presentaba a (recuadro ÷ pantalla) de su tamaño, arriba a la izquierda, con el resto en negro.
        var html = $$$"""
            <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#000;color:#fff;font-family:Segoe UI,Arial,sans-serif}
            video{display:block;position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#000;outline:none}
            .aviso{display:none;position:absolute;inset:0;align-items:center;justify-content:center;padding:24px;text-align:center;font-size:20px;background:#111}
            .p{display:none;position:absolute;inset:0;background:rgba(0,0,0,.82);align-items:center;justify-content:center;padding:24px;box-sizing:border-box}
            .q{max-width:720px;width:100%;max-height:100%;overflow:auto;background:#fff;color:#18181B;border-radius:16px;padding:20px 24px;box-sizing:border-box;font-size:20px}
            .q p{margin:0 0 14px;font-weight:600}
            .q button{display:block;width:100%;text-align:left;margin:8px 0;padding:12px 16px;border-radius:12px;border:2px solid #C7C4BE;background:#fff;color:#18181B;font-size:19px;font-family:inherit}
            .q button.ok{border-color:#1B8A4C;background:#E7F6EC}.q button.no{border-color:#E5262B;background:#FDECEC}
            .q .r{min-height:24px;margin:10px 0;font-size:17px;color:#52525B}
            .q .c{background:#E5262B;color:#fff;border:0;text-align:center;font-weight:600}.q .c:disabled{opacity:.4}</style></head>
            <body><video id="v" controls {{{(b.Autoplay == true ? "autoplay" : "")}}} playsinline preload="metadata"{{{poster}}} src="{{{url}}}{{{fragmento}}}">{{{pista}}}</video>
            <div class="aviso" id="a">No se pudo reproducir este video.</div>
            <div class="p" id="p"></div>
            <script>var v=document.getElementById('v');var fin={{{(b.HastaSeg is null ? "null" : b.HastaSeg.Value.ToString(inv))}}};
            v.addEventListener('error',function(){v.style.display='none';document.getElementById('a').style.display='flex';
              try{location.href='{{{EsquemaAviso}}}://fallo?tipo=video&codigo='+(v.error?v.error.code:0)+'&estado='+v.networkState;}catch(x){}});
            // Pausas para pensar (contrato 2): en `en_seg` el video se detiene y pregunta; sigue cuando se eligió y se leyó la razón.
            var P={{{pausas}}},hecha={},ov=document.getElementById('p');
            function esc(s){return String(s||'').replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
            function pausa(q){v.pause();hecha[q.pausa_ref]=1;var h='<div class="q"><p>'+esc(q.enunciado)+'</p>';
              for(var i=0;i<q.opciones.length;i++){h+='<button type="button" data-i="'+i+'">'+esc(q.opciones[i].texto)+'</button>';}
              h+='<div class="r" id="r"></div><button type="button" class="c" id="c" disabled>Continuar</button></div>';ov.innerHTML=h;ov.style.display='flex';
              var bs=ov.querySelectorAll('button[data-i]');for(var j=0;j<bs.length;j++){bs[j].onclick=function(){var o=q.opciones[+this.getAttribute('data-i')];
                for(var k=0;k<bs.length;k++){bs[k].className='';}this.className=o.es_respuesta?'ok':'no';
                document.getElementById('r').textContent=(o.es_respuesta?'Correcto. ':'No es esa. ')+(o.explicacion||'');document.getElementById('c').disabled=false;};}
              document.getElementById('c').onclick=function(){ov.style.display='none';v.play();};}
            v.addEventListener('timeupdate',function(){if(fin!==null&&v.currentTime>=fin){v.pause();}
              for(var i=0;i<P.length;i++){var q=P[i];if(!hecha[q.pausa_ref]&&v.currentTime>=q.en_seg&&v.currentTime<q.en_seg+1.5){pausa(q);break;} }});
            v.addEventListener('seeking',function(){for(var i=0;i<P.length;i++){if(v.currentTime<P[i].en_seg){delete hecha[P[i].pausa_ref];} }});</script></body></html>
            """;
        var avisos = new VerticalStackLayout { Spacing = 6 };
        var web = Web(html, null, uri => AvisarFallo("video", b, uri, avisos));
        pila.Add(CajaAjustada(web, b.Ancho, b.Alto));
        pila.Add(avisos);
        if (!string.IsNullOrWhiteSpace(b.Pie)) pila.Add(Ds.Secundario(b.Pie!, 16 * Escala));
        var detalle = string.Join(" · ", new[]
        {
            b.DesdeSeg is not null ? $"desde {Mmss(b.DesdeSeg.Value)}" : null,
            b.HastaSeg is not null ? $"hasta {Mmss(b.HastaSeg.Value)}" : null,
            !string.IsNullOrWhiteSpace(b.SubtitulosUrl) ? "con subtítulos" : null,
        }.Where(x => x is not null));
        if (detalle.Length > 0) pila.Add(Ds.Pildora(detalle, Ds.CatVideo));
        return pila;
    }

    private View Audio(BloqueAula b)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        if (Absoluta is null || string.IsNullOrWhiteSpace(b.Url))
            return Ds.Alerta_("Audio no disponible", b.Pie, Ds.PeligroSuave, Ds.Tinta);
        var avisos = new VerticalStackLayout { Spacing = 6 };
        var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 14 };
        fila.Add(Ds.IconoCategoria("audio", 56), 0, 0);
        fila.Add(Web(HtmlAudio(Absoluta(b.Url!).AbsoluteUri, b.DuracionSeg), 88, uri => AvisarFallo("audio", b, uri, avisos)), 1, 0);
        pila.Add(Ds.Tarjeta(fila, Ds.RadioInterno, new Thickness(14)));
        pila.Add(avisos);
        if (!string.IsNullOrWhiteSpace(b.Pie)) pila.Add(Ds.Secundario(b.Pie!, 16 * Escala));
        if (b.DuracionSeg is > 0) pila.Add(Ds.Pildora($"Audio · {Mmss(b.DuracionSeg.Value)}", Ds.CatAudio));
        return pila;
    }

    /// <summary>
    /// Reproductor de audio propio: un botón de 64 px (Primary, se hunde al pulsar), barra de avance y
    /// tiempo, en vez de los controles nativos diminutos. Si el archivo no se puede reproducir (dañado,
    /// formato no compatible, no llegó), lo dice en el propio reproductor y avisa a MAUI por
    /// <see cref="EsquemaAviso"/> con el código de <c>MediaError</c> para que quede en el archivo de fallos.
    /// </summary>
    public static string HtmlAudio(string url, double? duracionSeg)
    {
        var dur = duracionSeg is > 0 ? Mmss(duracionSeg.Value) : "–:––";
        return $$$"""
            <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
            html,body{margin:0;height:100%;background:#FAFAFA;font-family:'Segoe UI',Arial,sans-serif;color:#18181B;overflow:hidden}
            .f{display:flex;align-items:center;gap:16px;height:100%;padding:0 6px;box-sizing:border-box}
            button{width:64px;height:64px;border-radius:16px;border:0;background:#E5262B;color:#fff;font-size:26px;line-height:64px;cursor:pointer;flex:none;
                   box-shadow:6px 8px 14px rgba(0,0,0,.14);transition:transform .09s}
            button:active{transform:scale(.96);box-shadow:2px 3px 6px rgba(0,0,0,.14)}
            button:disabled{background:#C7C4BE;box-shadow:none;cursor:default}
            .b{flex:1;height:12px;background:#E4E4E7;border-radius:6px;overflow:hidden;cursor:pointer}
            .b>i{display:block;height:100%;width:0;background:#E5262B;border-radius:6px}
            .t{font-size:17px;min-width:110px;text-align:right;color:#52525B;font-variant-numeric:tabular-nums}
            .e{display:none;position:absolute;inset:0;background:#FDECEC;color:#8A1C1F;font-size:17px;padding:10px 16px;box-sizing:border-box;align-items:center;gap:12px}
            .e b{font-size:22px}
            </style></head><body>
            <div class="f"><button id="p" aria-label="Reproducir">▶</button><div class="b" id="b"><i id="i"></i></div><div class="t" id="t">0:00 / {{{dur}}}</div></div>
            <div class="e" id="e"><b>!</b><span id="m"></span></div>
            <audio id="a" preload="auto" src="{{{url}}}"></audio>
            <script>
            var a=document.getElementById('a'),p=document.getElementById('p'),i=document.getElementById('i'),t=document.getElementById('t'),e=document.getElementById('e'),m=document.getElementById('m');
            var total={{{(duracionSeg is > 0 ? duracionSeg.Value.ToString(System.Globalization.CultureInfo.InvariantCulture) : "0")}}},avisado=false,listo=false;
            function mmss(s){s=Math.max(0,Math.floor(s||0));return Math.floor(s/60)+':'+('0'+(s%60)).slice(-2);}
            function pinta(){var d=a.duration&&isFinite(a.duration)?a.duration:total;t.textContent=mmss(a.currentTime)+' / '+(d?mmss(d):'–:––');i.style.width=(d?Math.min(100,a.currentTime/d*100):0)+'%';}
            var MENSAJES={1:'La reproducción se interrumpió.',2:'El archivo no llegó del equipo del aula.',3:'El archivo está dañado: no se pudo decodificar.',4:'El formato no es compatible o el archivo no existe.'};
            function falla(codigo,detalle){if(avisado)return;avisado=true;p.disabled=true;p.textContent='✕';m.textContent=(MENSAJES[codigo]||'No se pudo reproducir.')+(detalle?' '+detalle:'');e.style.display='flex';
              try{location.href='{{{EsquemaAviso}}}://fallo?tipo=audio&codigo='+codigo+'&estado='+a.networkState+'&detalle='+encodeURIComponent(detalle||'');}catch(x){}}
            a.addEventListener('loadedmetadata',function(){listo=true;pinta();});
            a.addEventListener('timeupdate',pinta);
            a.addEventListener('play',function(){p.textContent='❚❚';p.setAttribute('aria-label','Pausar');});
            a.addEventListener('pause',function(){p.textContent='▶';p.setAttribute('aria-label','Reproducir');});
            a.addEventListener('ended',function(){a.currentTime=0;pinta();});
            a.addEventListener('error',function(){falla(a.error?a.error.code:0,a.error&&a.error.message?a.error.message:'');});
            a.addEventListener('stalled',function(){if(!listo)setTimeout(function(){if(!listo)falla(2,'Sin datos tras 10 s.');},10000);});
            setTimeout(function(){if(!listo&&!avisado&&a.readyState<1)falla(2,'Sin respuesta tras 12 s.');},12000);
            p.addEventListener('click',function(){if(a.paused){var r=a.play();if(r&&r.catch)r.catch(function(x){falla(a.error?a.error.code:4,x&&x.name?x.name:'');});}else{a.pause();}});
            document.getElementById('b').addEventListener('click',function(ev){var d=a.duration&&isFinite(a.duration)?a.duration:total;if(!d)return;var r=this.getBoundingClientRect();a.currentTime=Math.max(0,Math.min(d,(ev.clientX-r.left)/r.width*d));pinta();});
            pinta();
            </script></body></html>
            """;
    }

    /// <summary>Un reproductor avisó de un fallo: se anota en el archivo de fallos y se muestra bajo el bloque.</summary>
    private void AvisarFallo(string tipo, BloqueAula b, Uri aviso, Layout destino)
    {
        var parametros = aviso.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(x => x.Split('=', 2)).ToDictionary(x => x[0], x => x.Length > 1 ? Uri.UnescapeDataString(x[1].Replace('+', ' ')) : string.Empty);
        var codigo = parametros.TryGetValue("codigo", out var c) && int.TryParse(c, out var n) ? n : 0;
        var mensaje = codigo switch
        {
            1 => "La reproducción se interrumpió",
            2 => "El archivo no llegó del equipo del aula (red o biblioteca)",
            3 => "El archivo está dañado: no se pudo decodificar",
            4 => "El formato no es compatible o el archivo no existe",
            _ => "No se pudo reproducir",
        };
        var detalle = parametros.TryGetValue("detalle", out var d) && !string.IsNullOrWhiteSpace(d) ? $" ({d})" : string.Empty;
        var destinoUri = Absoluta is not null && !string.IsNullOrWhiteSpace(b.Url) ? Absoluta(b.Url!) : null;
        // El registro no lleva el pase de la dirección (es un permiso de lectura de la sesión), sólo el camino del medio.
        var url = destinoUri is not null ? DiagnosticoDeMedio.SinPase(destinoUri) : b.Url ?? string.Empty;
        var medio = b.MediaRef ?? string.Empty;
        RegistroDeFallos.Escribir(NombreApp, $"{tipo} {medio} · {url}",
            new InvalidDataException($"{mensaje}{detalle}. MediaError {codigo}. El medio no pasó la comprobación de reproducción en el visor del aula."));
        if (destino.Children.Count == 0)
            destino.Children.Add(Ds.Alerta_($"El {tipo} no se pudo reproducir", "Comprobando la causa…", Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
        _ = DiagnosticarAsync(tipo, medio, destinoUri, url, codigo, mensaje + detalle, destino, _cancelarMedios.Token);
    }

    /// <summary>
    /// «MediaError 4» (formato no compatible) es también lo que ve el reproductor cuando el equipo del aula contestó 401, 404 o 503: el archivo puede estar
    /// perfecto. Se le pregunta al aula qué contestó de verdad y se dice esa causa en pantalla, en el archivo de fallos y por <see cref="MedioFallido"/>.
    /// </summary>
    private async Task DiagnosticarAsync(string tipo, string medio, Uri? uri, string urlSinPase, int codigo, string mensajeDelReproductor, Layout destino, CancellationToken ct)
    {
        var sondeo = uri is null ? new SondeoDeMedio(null, null, null, null, null, "sin dirección") : await DiagnosticoDeMedio.SondearAsync(uri, ct: ct);
        if (ct.IsCancellationRequested) return;
        // Si el aula sí entrega el archivo, el reproductor tiene razón y es un asunto de formato de ESTE dispositivo.
        var causa = sondeo.Entrega ? $"{mensajeDelReproductor}. {sondeo.Causa}" : sondeo.Causa;
        RegistroLocal.Advertencia(Canal.Comunicacion, "medio.diagnostico", $"{tipo} {medio} · {urlSinPase}",
            new { tipo, medio, media_error = codigo, respuesta = sondeo.Resumen, entrega = sondeo.Entrega });
        Dispatcher.Dispatch(() =>
        {
            destino.Children.Clear();
            destino.Children.Add(Ds.Alerta_($"El {tipo} no se pudo reproducir", $"{causa} Quedó anotado en {RegistroDeFallos.Ruta(NombreApp)} ({sondeo.Resumen}).",
                Ds.PeligroSuave, Color.FromArgb("#8A1C1F")));
        });
        MedioFallido?.Invoke(this, new FalloDeMedio(tipo, medio, urlSinPase, codigo, causa));
    }

    /// <summary>
    /// Una imagen del curso, bajada por la app y no por el visor: así un fallo (sesión terminada, medio que falta, aula apagada) se dice en el recuadro con su
    /// causa, en vez de dejar un rectángulo gris sin explicación. La dirección ya lleva el pase; la descarga manda además el Bearer si la ruta no lo trae.
    /// </summary>
    private void CargarImagen(Border marco, Uri uri, string? alternativo, string? mediaRef)
    {
        var imagen = new Image { Aspect = Aspect.AspectFit };
        if (!string.IsNullOrWhiteSpace(alternativo)) SemanticProperties.SetDescription(imagen, alternativo);
        marco.Content = imagen;
        var ct = _cancelarMedios.Token;
        _ = Task.Run(async () =>
        {
            var (bytes, sondeo) = await DiagnosticoDeMedio.DescargarImagenAsync(uri, ct: ct);
            if (ct.IsCancellationRequested) return;
            if (bytes is not null)
            {
                Dispatcher.Dispatch(() => imagen.Source = ImageSource.FromStream(() => new MemoryStream(bytes)));
                return;
            }
            RegistroLocal.Advertencia(Canal.Comunicacion, "medio.imagen_no_entregada", $"imagen {mediaRef} · {DiagnosticoDeMedio.SinPase(uri)}",
                new { medio = mediaRef, respuesta = sondeo.Resumen });
            Dispatcher.Dispatch(() => marco.Content = new VerticalStackLayout
            {
                Spacing = 4, Padding = new Thickness(16), VerticalOptions = LayoutOptions.Center, HorizontalOptions = LayoutOptions.Center,
                Children = { Ds.Cuerpo("Imagen no disponible", 17 * Escala), Ds.Secundario(sondeo.Causa, 14 * Escala) },
            });
        }, ct);
    }

    private View Pdf(BloqueAula b)
    {
        var pila = new VerticalStackLayout { Spacing = 8 };
        var rango = b.DesdePagina is not null ? $"Páginas {b.DesdePagina}–{b.HastaPagina ?? b.Paginas}{(b.Paginas is not null ? $" de {b.Paginas}" : string.Empty)}" : "Documento";
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cabecera.Add(Ds.IconoCategoria("pdf", 44), 0, 0);
        cabecera.Add(new VerticalStackLayout { Children = { Ds.Cuerpo(b.Titulo ?? "Documento", 17 * Escala), Ds.Secundario(rango, 14 * Escala) }, VerticalOptions = LayoutOptions.Center }, 1, 0);
        pila.Add(cabecera);
        if (Absoluta is not null && !string.IsNullOrWhiteSpace(b.Url))
        {
            var destino = Absoluta(b.UrlPaginaInicial ?? b.Url!);
            if (DeviceInfo.Platform == DevicePlatform.Android)
            {
                var abrir = Ds.Boton("Abrir el documento", Ds.Rango.Secondary, async (_, _) => await Launcher.Default.OpenAsync(destino));
                cabecera.Add(abrir, 2, 0);
            }
            else
            {
                pila.Add(Web(destino, 520 * Escala));
            }
        }
        if (!string.IsNullOrWhiteSpace(b.Pie)) pila.Add(Ds.Secundario(b.Pie!, 16 * Escala));
        return pila;
    }

    // ------------------------------------------------------------- laboratorio

    private View Laboratorio(ObjetoAula o)
    {
        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Auto), new RowDefinition(GridLength.Star)], RowSpacing = 12 };
        var cab = new VerticalStackLayout { Spacing = 8 };
        var titulo = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        titulo.Add(Ds.IconoCategoria("laboratorio_web", 44), 0, 0);
        titulo.Add(new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Children = { Ds.Titulo(o.Titulo, 22 * Escala), Ds.Secundario(o.ObjetivoAprendizaje ?? string.Empty, 15 * Escala) } }, 1, 0);
        titulo.Add(Ds.Pildora("Laboratorio", Ds.CatVideo), 2, 0);
        cab.Add(titulo);
        if (!string.IsNullOrWhiteSpace(o.Instrucciones)) cab.Add(Ds.ConTramos(o.InstruccionesTramos, o.Instrucciones, 17 * Escala));
        if (o.Pasos is { Count: > 0 })
        {
            var pasos = new HorizontalStackLayout { Spacing = 8 };
            for (var i = 0; i < o.Pasos.Count; i++) pasos.Add(Ds.Pildora($"{i + 1}. {o.Pasos[i]}", Ds.Lienzo, Ds.Tinta, 13));
            cab.Add(new ScrollView { Orientation = ScrollOrientation.Horizontal, HorizontalScrollBarVisibility = ScrollBarVisibility.Never, Content = pasos });
        }
        raiz.Add(Ds.Tarjeta(cab, Ds.RadioTarjeta, new Thickness(18, 14)), 0, 0);

        var sim = o.Simulacion?.Simulacion;
        if (Absoluta is null || string.IsNullOrWhiteSpace(o.UrlLanzamiento))
            raiz.Add(Ds.Alerta_("La simulación no tiene dirección de lanzamiento", null, Ds.AlertaSuave, Ds.Tinta), 0, 1);
        else if (sim is not null && !sim.SirveEnTableta && DeviceInfo.Idiom != DeviceIdiom.Desktop)
            raiz.Add(Ds.Alerta_("Esta simulación se ve en la pantalla del aula", "El paquete no la publica para tableta.", Ds.InfoSuave, Ds.Tinta), 0, 1);
        else
        {
            var marco = new Border
            {
                StrokeThickness = 0, BackgroundColor = Color.FromArgb("#101014"), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioTarjeta },
                Content = Web(Absoluta(o.UrlLanzamiento!), null),
            };
            raiz.Add(marco, 0, 1);
        }
        var licencia = o.Simulacion?.Licencia;
        if (licencia is not null && !string.IsNullOrWhiteSpace(licencia.Atribucion))
        {
            raiz.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
            raiz.Add(Ds.Secundario(licencia.Atribucion!, 12), 0, 2);
        }
        return raiz;
    }

    // ---------------------------------------------------------------- actividad

    private View Actividad(ObjetoAula o)
    {
        var pila = new VerticalStackLayout { Spacing = 14, Padding = new Thickness(0, 0, 0, 24) };
        var cab = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 12 };
        cab.Add(Ds.IconoCategoria("actividad", 44), 0, 0);
        cab.Add(new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Children = { Ds.Titulo(o.Titulo, 22 * Escala), Ds.Secundario(o.Instrucciones ?? string.Empty, 15 * Escala) } }, 1, 0);
        cab.Add(Ds.Pildora($"{o.Preguntas?.Count ?? 0} preguntas · {o.PuntosTotales ?? 0} pts", Ds.CatQuiz), 2, 0);
        pila.Add(Ds.Tarjeta(cab, Ds.RadioTarjeta, new Thickness(18, 14)));
        if (o.Ajustes is not null)
        {
            var chips = new HorizontalStackLayout { Spacing = 8 };
            chips.Add(Ds.Pildora(o.Ajustes.Retroalimentacion == "immediate" ? "Retroalimentación inmediata" : "Retroalimentación al final", Ds.Lienzo, Ds.Tinta));
            if (o.Ajustes.IntentosPermitidos is > 0) chips.Add(Ds.Pildora($"{o.Ajustes.IntentosPermitidos} intento(s)", Ds.Lienzo, Ds.Tinta));
            if (o.Ajustes.BarajarOpciones) chips.Add(Ds.Pildora("Opciones barajadas", Ds.Lienzo, Ds.Tinta));
            pila.Add(chips);
        }
        var n = 0;
        foreach (var p in o.Preguntas ?? [])
        {
            n++;
            var contenido = new VerticalStackLayout { Spacing = 10 };
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            fila.Add(Ds.Pildora(n.ToString(), Ds.CatQuiz), 0, 0);
            fila.Add(Ds.ConTramos(p.EnunciadoTramos, p.Enunciado, 19 * Escala), 1, 0);
            fila.Add(Ds.Secundario($"{p.TipoLegible} · {p.Puntos ?? 0} pt", 13), 2, 0);
            contenido.Add(fila);
            contenido.Add(Pregunta(p));
            pila.Add(Ds.Tarjeta(contenido, Ds.RadioTarjeta, new Thickness(18, 16)));
        }
        // Lo que esta pantalla puede y no puede hacer con la actividad, dicho según quién la mira (QA 2026-10-07: «no se podían seleccionar»).
        pila.Add(Ds.Secundario(NombreApp == "student"
            ? "Puedes marcar opciones para pensarlas. Para responder de verdad, espera a que tu profesor lance la actividad: te aparecerá abajo con el botón «Responder»."
            : "Marca opciones en pantalla para comentarlas con la clase; nada se envía. Para que los alumnos respondan en sus tabletas, pulsa «Lanzar actividad».", 13 * Escala));
        return pila;
    }

    private View Pregunta(PreguntaAula p)
    {
        var cuerpo = Cuerpo(p);
        if (p.Medios is not { Count: > 0 }) return cuerpo;
        // `mediaIds` del esquema 1.0: imagen, video, audio o pdf que acompañan al enunciado. La imagen se ve;
        // el resto se anuncia (el alumno lo abre desde su tableta, donde sí hay reproductor).
        var pila = new VerticalStackLayout { Spacing = 10 };
        foreach (var m in p.Medios)
        {
            if (m.Componente == "imagen" && !string.IsNullOrWhiteSpace(m.Url)) pila.Add(ImagenDeMedio(m.Url!, m.TextoAlternativo, m.Ancho, m.Alto));
            else pila.Add(Ds.Pildora($"{MedioLegible(m)} · {m.Titulo ?? m.MediaRef}", Ds.InfoSuave, Ds.Tinta, 14 * Escala));
        }
        pila.Add(cuerpo);
        return pila;
    }

    private static string MedioLegible(MedioAula m) => m.Componente switch
    {
        "video" => "Video", "audio" => "Audio", "pdf" => "Documento", "imagen" => "Imagen", _ => "Medio",
    };

    /// <summary>Una imagen suelta (medio de una pregunta, opción o ítem) con su proporción real.</summary>
    private View ImagenDeMedio(string url, string? alternativo, int? ancho, int? alto, double altoMaximo = 0)
    {
        if (Absoluta is null)
            return new Border { StrokeThickness = 0, BackgroundColor = Ds.Lienzo, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, HeightRequest = 160 * Escala };
        var marco = new Border { StrokeThickness = 0, BackgroundColor = Ds.Lienzo, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno } };
        CargarImagen(marco, Absoluta(url), alternativo, null);
        if (altoMaximo > 0) { marco.HeightRequest = altoMaximo; marco.HorizontalOptions = LayoutOptions.Start; return marco; }
        return ConProporcion(marco, ancho, alto);
    }

    /// <summary>Texto (tramos) o imagen de una opción o un ítem; con las dos, la imagen va encima.</summary>
    private View TextoOImagen(IReadOnlyList<Tramo>? tramos, string? texto, string? url, string? alternativo, string respaldo, double tamano)
    {
        var etiqueta = string.IsNullOrWhiteSpace(texto) && string.IsNullOrWhiteSpace(url) ? Ds.Cuerpo(respaldo, tamano) : Ds.ConTramos(tramos, texto, tamano);
        if (string.IsNullOrWhiteSpace(url)) return etiqueta;
        var pila = new VerticalStackLayout { Spacing = 6 };
        pila.Add(ImagenDeMedio(url!, alternativo, null, null, 140 * Escala));
        if (!string.IsNullOrWhiteSpace(texto)) pila.Add(etiqueta);
        return pila;
    }

    private View Cuerpo(PreguntaAula p)
    {
        switch (p.Componente)
        {
            case "opcion_multiple":
            case "verdadero_falso":
            {
                // Las opciones se pueden MARCAR en pantalla (una, o varias si la pregunta lo permite): en la pantalla del aula sirve para
                // comentar con la clase; en la tableta, para pensar la respuesta mientras el profesor la lanza. No se envía ni se corrige nada
                // desde aquí: la respuesta de verdad va por la actividad lanzada (ActividadResponderView).
                var varias = p.PermiteVarias == true;
                var pila = new VerticalStackLayout { Spacing = 8 };
                var filas = new List<(Border Caja, BoxView Marca, string Ref, string Rotulo)>();
                var marcadas = new HashSet<string>();
                void Pintar()
                {
                    foreach (var (caja, marca, referencia, rotulo) in filas)
                    {
                        var elegida = marcadas.Contains(referencia);
                        marca.Color = elegida ? Ds.Tinta : Ds.Lienzo;
                        caja.BackgroundColor = elegida ? Ds.InfoSuave : Colors.Transparent;
                        caja.StrokeThickness = elegida ? 2 : 0;
                        SemanticProperties.SetDescription(caja, $"{rotulo}. {(elegida ? "Marcada" : "Sin marcar")}");
                    }
                }
                foreach (var op in p.Opciones ?? [])
                {
                    var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(28), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 10 };
                    var marca = new BoxView { WidthRequest = 22, HeightRequest = 22, CornerRadius = varias ? 6 : 11, Color = Ds.Lienzo, VerticalOptions = LayoutOptions.Center };
                    fila.Add(marca, 0, 0);
                    fila.Add(TextoOImagen(op.Tramos, op.Texto, op.Url, op.TextoAlternativo, op.OpcionRef, 17 * Escala), 1, 0);
                    var caja = new Border
                    {
                        StrokeThickness = 0, Stroke = new SolidColorBrush(Ds.Tinta), BackgroundColor = Colors.Transparent, Padding = new Thickness(10, 8),
                        StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, MinimumHeightRequest = 48, Content = fila,
                        AutomationId = $"vista-opcion-{op.OpcionRef}",
                    };
                    var referencia = op.OpcionRef;
                    Ds.Tocable(caja, () =>
                    {
                        if (varias) { if (!marcadas.Remove(referencia)) marcadas.Add(referencia); }
                        else if (!marcadas.Remove(referencia)) { marcadas.Clear(); marcadas.Add(referencia); }
                        Pintar();
                        return Task.CompletedTask;
                    });
                    filas.Add((caja, marca, referencia, op.Texto ?? op.TextoAlternativo ?? referencia));
                    pila.Add(caja);
                }
                Pintar();
                return pila;
            }
            case "completar":
            {
                var texto = p.Plantilla ?? string.Empty;
                foreach (var e in p.Espacios ?? [])
                    texto = texto.Replace("{{" + e.EspacioRef + "}}", e.Opciones is { Count: > 0 } ? $"[ {string.Join(" / ", e.Opciones)} ]" : "[ ______ ]");
                return Ds.Cuerpo(texto, 17 * Escala);
            }
            case "relacionar":
            {
                var g = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 16 };
                var izq = new VerticalStackLayout { Spacing = 6 }; var der = new VerticalStackLayout { Spacing = 6 };
                foreach (var e in p.Izquierda ?? []) izq.Add(Item(e, Ds.Lienzo));
                foreach (var e in p.Derecha ?? []) der.Add(Item(e, Ds.InfoSuave));
                g.Add(izq, 0, 0); g.Add(der, 1, 0);
                return g;
            }
            case "ordenar":
            {
                var pila = new VerticalStackLayout { Spacing = 6 };
                foreach (var e in p.Elementos ?? []) pila.Add(Item(e, Ds.Lienzo, "↕  "));
                return pila;
            }
            case "arrastrar":
            {
                // Contrato 2: las piezas en una bandeja y las zonas donde van. En la vista previa no se mueven; en la tableta las coloca EditorArrastrar.
                var pila = new VerticalStackLayout { Spacing = 10 };
                var bandeja = new FlexLayout { Wrap = Microsoft.Maui.Layouts.FlexWrap.Wrap, JustifyContent = Microsoft.Maui.Layouts.FlexJustify.Start, AlignItems = Microsoft.Maui.Layouts.FlexAlignItems.Start };
                foreach (var e in p.Elementos ?? [])
                {
                    var pieza = Item(e, Colors.White);
                    pieza.Margin = new Thickness(0, 0, 8, 8);
                    bandeja.Add(pieza);
                }
                pila.Add(new Border { StrokeThickness = 1.5, Stroke = new SolidColorBrush(Color.FromArgb("#C7C4BE")), BackgroundColor = Colors.White, Padding = new Thickness(10, 10, 2, 2), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Content = bandeja });
                foreach (var z in p.Zonas ?? [])
                {
                    var cabecera = TextoOImagen(null, z.Rotulo, z.Url, z.TextoAlternativo, z.ZonaRef, 17 * Escala);
                    pila.Add(new Border { StrokeThickness = 0, BackgroundColor = Ds.Lienzo, Padding = new Thickness(14, 12), StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, MinimumHeightRequest = 56, Content = cabecera });
                }
                return pila;
            }
            case "abierta":
                return new Border
                {
                    BackgroundColor = Ds.Lienzo, StrokeThickness = 0, StrokeShape = new RoundRectangle { CornerRadius = Ds.RadioInterno }, Padding = new Thickness(16, 20),
                    Content = Ds.Secundario($"Respuesta escrita{(p.LongitudMaxima is > 0 ? $" · hasta {p.LongitudMaxima} caracteres" : string.Empty)} · la califica el docente", 14 * Escala),
                };
            default:
                return Ds.Secundario($"Tipo de pregunta «{p.Tipo}» sin visor.", 14 * Escala);
        }
    }

    /// <summary>Un ítem de relacionar u ordenar: píldora con el texto o, si es una imagen (`ChoiceItem.mediaId`), la imagen.</summary>
    private View Item(ElementoAula e, Color fondo, string prefijo = "")
    {
        if (string.IsNullOrWhiteSpace(e.Url)) return Ds.Pildora(prefijo + (e.Texto ?? e.Ref), fondo, Ds.Tinta, 15 * Escala);
        var pila = new VerticalStackLayout { Spacing = 4 };
        if (!string.IsNullOrWhiteSpace(prefijo)) pila.Add(Ds.Secundario(prefijo.Trim(), 15 * Escala));
        pila.Add(ImagenDeMedio(e.Url!, e.TextoAlternativo, null, null, 120 * Escala));
        if (!string.IsNullOrWhiteSpace(e.Texto)) pila.Add(Ds.Pildora(e.Texto!, fondo, Ds.Tinta, 15 * Escala));
        return pila;
    }

    private View FueraDeAlcance(ObjetoAula o)
    {
        var pila = new VerticalStackLayout { Spacing = 10, Opacity = 0.75 };
        var cab = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Auto), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 12 };
        cab.Add(Ds.IconoCategoria("examen", 44), 0, 0);
        cab.Add(new VerticalStackLayout { VerticalOptions = LayoutOptions.Center, Children = { Ds.Titulo(o.Titulo, 22 * Escala), Ds.Secundario($"Lo aplica el módulo de evaluación ({o.Modulo ?? "MOD-010"}). El aula lo muestra, no lo ejecuta.", 15 * Escala) } }, 1, 0);
        pila.Add(cab);
        if (o.TotalPreguntasBanco is > 0) pila.Add(Ds.Pildora($"Banco de {o.TotalPreguntasBanco} preguntas", Ds.Lienzo, Ds.Tinta));
        if (!string.IsNullOrWhiteSpace(o.Instrucciones)) pila.Add(Ds.Secundario(o.Instrucciones!, 15 * Escala));
        return Ds.Tarjeta(pila);
    }

    // ------------------------------------------------------------------ webview

    /// <summary>
    /// Envuelve el video o la imagen de un bloque en un contenedor que le fija el alto según el
    /// ANCHO real que le toque en cada pantalla (una tableta angosta, la columna ancha de
    /// proyección de OPS a escala 1,15, una ventana redimensionada…), con la proporción real del
    /// archivo (<c>ancho</c>/<c>alto</c> del medio) o 16∶9 si la biblioteca no la publicó.
    ///
    /// Antes el alto era un número de píxeles fijo: en la columna de proyección, mucho más ancha
    /// que una tableta, el medio quedaba diminuto con espacio vacío alrededor; aquí se recalcula
    /// en cada <c>SizeChanged</c>, así que sigue el tamaño real de la pantalla que se esté usando
    /// en cada momento, incluida una reorientación o un redimensionado.
    /// </summary>
    /// <summary>
    /// Recuadro de un medio de bloque (video o imagen a página completa): cabe ENTERO en el espacio visible del visor —ancho
    /// y alto—, con la proporción real del archivo (o 16∶9), centrado, y acotado además por el perfil de pantalla elegido
    /// en OPS (<see cref="AjustesDePantalla"/>). Se reajusta solo al cambiar la ventana, la escala de Windows o el perfil.
    /// <paramref name="aplicado"/> se llama cada vez que cambia el recuadro (la primera, al crearse).
    /// </summary>
    private View CajaAjustada(View medio, int? ancho, int? alto, Action<CajaDeMedio>? aplicado = null)
    {
        var proporcion = AjusteDeMedio.Proporcion(ancho, alto);
        medio.HorizontalOptions = LayoutOptions.Center;
        var contenedor = new ContentView { Content = medio };
        var ultima = CajaDeMedio.Vacia;
        void Ajustar()
        {
            var caja = AjusteDeMedio.Ajustar(_anchoUtil, _altoUtil, proporcion, AjustesDePantalla.Actual);
            if (caja.EsVacia || (Math.Abs(caja.Ancho - ultima.Ancho) < 1 && Math.Abs(caja.Alto - ultima.Alto) < 1)) return;
            ultima = caja;
            medio.WidthRequest = caja.Ancho;
            medio.HeightRequest = caja.Alto;
            aplicado?.Invoke(caja);
        }
        _ajustes.Add(Ajustar);
        Ajustar();
        return contenedor;
    }

    /// <summary>Alto fijado por el ancho del contenedor: sólo para imágenes sueltas dentro de columnas (opciones, ítems, enunciados).</summary>
    private static View ConProporcion(View medio, int? ancho, int? alto)
    {
        var proporcion = ancho is > 0 && alto is > 0 ? (double)alto!.Value / ancho!.Value : 9.0 / 16.0;
        var contenedor = new ContentView { Content = medio };
        contenedor.SizeChanged += (_, _) =>
        {
            if (contenedor.Width > 0) medio.HeightRequest = contenedor.Width * proporcion;
        };
        return contenedor;
    }

    private WebView Web(string html, double? alto, Action<Uri>? alAvisar = null)
    {
        var web = NuevaWeb(alto, alAvisar, desplazable: false);   // reproductores propios: llenan su recuadro y no se desplazan
        _hostPermitido = null; // HTML propio: sólo se permite el host del backend, que se fija al conocer la primera URL absoluta
        if (Absoluta is not null) _hostPermitido = Absoluta("/").GetLeftPart(UriPartial.Authority);
        web.Source = new HtmlWebViewSource { Html = html };
        return web;
    }

    private WebView Web(Uri url, double? alto)
    {
        var web = NuevaWeb(alto, null);
        _hostPermitido = url.GetLeftPart(UriPartial.Authority);
        web.Source = new UrlWebViewSource { Url = url.AbsoluteUri };
        return web;
    }

    /// <summary>
    /// Una WebView más de la unidad en pantalla. Una página puede llevar varias (audio + video + pdf):
    /// todas viven hasta que cambia la unidad, y entonces <see cref="LimpiarWeb"/> las vacía juntas.
    /// </summary>
    private WebView NuevaWeb(double? alto, Action<Uri>? alAvisar, bool desplazable = true)
    {
        var web = new WebView();
        if (alto is not null) web.HeightRequest = alto.Value;
        web.Navigating += (_, e) =>
        {
            if (!Uri.TryCreate(e.Url, UriKind.Absolute, out var uri)) return;
            // El HTML de un reproductor avisa de un fallo navegando a avacom-aula://…: se intercepta y no navega.
            if (string.Equals(uri.Scheme, EsquemaAviso, StringComparison.OrdinalIgnoreCase))
            {
                e.Cancel = true;
                alAvisar?.Invoke(uri);
                return;
            }
            // block_network: la WebView sólo navega al host del backend del LMS. El aula no tiene internet
            // y una simulación que intente salir simplemente no navega.
            if (_hostPermitido is null) return;
            if (uri.Scheme is "about" or "data" or "blob") return;
            if (!string.Equals(uri.GetLeftPart(UriPartial.Authority), _hostPermitido, StringComparison.OrdinalIgnoreCase)) e.Cancel = true;
        };
        // Un objeto HTML (reproductor propio o laboratorio/simulación externa) puede llegar más alto que el
        // recuadro que le da MAUI: sin esto, lo que sobra por abajo (vídeo con controles extra, panel largo de
        // un laboratorio) queda recortado y sin forma de bajar. Se inyecta tras cada navegación lograda, sobre
        // cualquier documento, sea nuestro o de un paquete externo, para no depender de que su propio CSS lo declare.
        web.Navigated += (_, e) =>
        {
            if (desplazable && e.Result == WebNavigationResult.Success) _ = web.EvaluateJavaScriptAsync(InyeccionDesplazamiento);
        };
        _webs.Add(web);
        return web;
    }

    // Sólo desbloquea el desplazamiento vertical; no toca height/flex de la página cargada, para no romper el
    // vídeo a pantalla completa (flex:1 sobre body{height:100%}) ni el resto de los reproductores propios.
    private const string InyeccionDesplazamiento =
        "(function(){try{var s=document.createElement('style');" +
        "s.textContent='html,body{overflow-y:auto!important;overflow-x:hidden!important;" +
        "-webkit-overflow-scrolling:touch!important}';" +
        "document.head?document.head.appendChild(s):document.documentElement.appendChild(s);}catch(e){}})();";

    private void LimpiarWeb(bool conservarHtml = false)
    {
        _cancelarMedios.Cancel();
        _cancelarMedios.Dispose();
        _cancelarMedios = new CancellationTokenSource();
        foreach (var web in _webs)
        {
            if (conservarHtml && ReferenceEquals(web, _webHtml)) continue;
            try { web.Source = new HtmlWebViewSource { Html = "<html><body></body></html>" }; } catch { }
        }
        _webs.Clear();
        if (conservarHtml && _webHtml is not null) _webs.Add(_webHtml);
        else { _webHtml = null; _webHtmlPagina = null; _htmlContenedor = null; _htmlCabecera = null; }
        _ajustes.Clear();
    }

    /// <summary>
    /// Deja el fallo del visor donde un técnico lo va a buscar: un renglón ERROR del canal «aplicacion» (archivo local y, de inmediato, la bitácora del nodo)
    /// que dice QUÉ se iba a mostrar (objeto, lámina o página), QUÉ salió mal (tipo, código y mensaje de la excepción) y DÓNDE (clase, método y línea), y cómo
    /// siguió la clase. Nunca lleva el pase de medios de la dirección ni datos de personas.
    /// </summary>
    private void AnotarFalloDelVisor(ObjetoAula objeto, string? unidadRef, Exception ex, bool conRespaldo, UnidadAula? unidad = null)
    {
        try
        {
            var unidades = objeto.Unidades;
            var enFoco = unidad ?? unidades.FirstOrDefault(u => u.UnidadRef == unidadRef) ?? (unidades.Count > 0 ? unidades[0] : null);
            var lugar = enFoco is null ? string.Empty : $" · {(objeto.Componente == "presentacion" ? "lámina" : "página")} {enFoco.Indice} de {unidades.Count}";
            var pagina = enFoco?.UrlHtml is { Length: > 0 } relativa && Absoluta is not null ? DiagnosticoDeMedio.SinPase(Absoluta(relativa)) : null;
            var que = pagina is not null ? "la página maquetada del curso" : "el contenido";
            var desenlace = conRespaldo
                ? "La clase sigue con el texto del curso, sin la maqueta."
                : "La pantalla quedó con un aviso y el botón «Reintentar»; la clase sigue.";
            var donde = RegistroDeFallos.DondeFallo(ex);
            var mensaje = $"No se pudo mostrar {que} «{objeto.Titulo}» ({objeto.ComponenteLegible.ToLowerInvariant()}{lugar}) en el visor del aula. {desenlace} " +
                          $"{RegistroDeFallos.Resumen(ex)}{(donde is null ? string.Empty : $" · en {donde}")}";
            RegistroDeFallos.Anotar(NombreApp, $"AulaContenidoView.Mostrar {objeto.ObjetoRef}", ex, "aula.visor.fallo", mensaje,
                new
                {
                    objeto_ref = objeto.ObjetoRef, tipo = objeto.Tipo, componente = objeto.Componente,
                    unidad_ref = enFoco?.UnidadRef ?? unidadRef, indice = enFoco?.Indice, total = unidades.Count,
                    pagina_html = pagina, tipo_excepcion = ex.GetType().Name, codigo = RegistroDeFallos.CodigoDe(ex), donde, con_respaldo = conRespaldo,
                });
        }
        catch { /* anotar el fallo nunca puede ser otro fallo */ }
    }

    /// <summary>La tarjeta que sustituye a lo que no se pudo pintar: dice qué pasó en palabras, que quedó anotado y deja reintentar.</summary>
    private View TarjetaDeFalloDelVisor(ObjetoAula objeto, string? unidadRef)
    {
        var reintentar = Ds.Boton("Reintentar", Ds.Rango.Primary, (_, _) => Mostrar(objeto, unidadRef), 56, 200);
        var capsula = Ds.Capsula(reintentar);
        capsula.HorizontalOptions = LayoutOptions.Center;
        var titulo = Ds.Titulo("No se pudo mostrar este contenido", 24 * Escala);
        titulo.HorizontalTextAlignment = TextAlignment.Center;
        var detalle = Ds.Secundario($"«{objeto.Titulo}» no se pudo pintar en esta pantalla. El fallo quedó anotado como ERROR en la bitácora del aula, con lo que hace falta para corregirlo. " +
                                    "Puedes reintentar o seguir con otro objeto de la secuencia.", 16 * Escala);
        detalle.HorizontalTextAlignment = TextAlignment.Center;
        var pila = new VerticalStackLayout
        {
            Spacing = 14, HorizontalOptions = LayoutOptions.Center, VerticalOptions = LayoutOptions.Center, Padding = 32, MaximumWidthRequest = 760,
            Children = { titulo, detalle, capsula },
        };
        return Ds.Tarjeta(pila, Ds.RadioGrande, new Thickness(0));
    }

    private static string Mmss(double seg) => $"{(int)seg / 60}:{(int)seg % 60:00}";

    public static string HtmlEscapar(string s) => WebUtility.HtmlEncode(s);
}

/// <summary>Lo que se anota cuando un medio no se pudo reproducir. `Codigo` es el <c>MediaError.code</c> del navegador.</summary>
public sealed record FalloDeMedio(string Tipo, string MediaRef, string Url, int Codigo, string Mensaje);
