using Avacom.Lms.Core.Actualizacion;
using Avacom.Lms.Core.Services;
using Avacom.Lms.Ops.Actualizacion;
using Avacom.Lms.Ops.Actualizacion.Ui;
using Avacom.Lms.Ops.Examen;
using Avacom.Lms.Ops.Navegacion;
using Avacom.Lms.Ui.Design;

namespace Avacom.Lms.Ops.Pages;

/// <summary>
/// Actualizaciones (MOD-017, ruta <c>actualizaciones</c>): lo que el nodo dice de su versión y de sus módulos, los paquetes de AVACOM que hay en las memorias USB y en el aula, y lo que se
/// puede hacer con ellos (traer, programar, aplicar y volver atrás), sin teclado. Es una pantalla de tarjetas y sigue la composición de tercios: Grid de columnas <c>*,*,*</c> y de filas
/// <c>*,4*,*</c>, con las tres tarjetas en la fila central (de 1/6 a 5/6 del alto) y cada una en su tercio:
/// <list type="bullet">
/// <item>a la izquierda, <b>este equipo</b>: el estado, la versión, el espacio libre y los módulos con su versión de datos y de contrato;</item>
/// <item>en el centro, en una lámina de vidrio, el <b>paquete elegido</b>: qué cambia, cuánto pesa, si es compatible y los botones (Aplicar ahora, Programar, Volver a la versión anterior);</item>
/// <item>a la derecha, los <b>paquetes</b> (los de las memorias, que se traen con un toque, y los ya traídos) y el <b>historial</b>.</item>
/// </list>
/// El cliente no decide nada de la actualización (BR-013, SEC-001): pinta lo que responde <c>/api/actualizacion/</c> y el nodo verifica la firma, la compatibilidad y que no haya una clase
/// abierta. Aplicar y volver atrás piden UNA confirmación en <see cref="HojaDeActualizacion"/>. La ven la administración y el soporte técnico. Una clase abierta nunca se interrumpe. Sólo
/// Border, Label y Button; todo lo que se toca mide 64 px.
/// </summary>
public sealed class ActualizacionesPage : ContentPage
{
    private const double Aire = 10;       // lo que separa cada tarjeta de las líneas de tercios: así quedan DENTRO de su tercio
    private enum Pestana { Paquetes, Historial }

    private readonly Label _subtitulo = new() { FontFamily = Ds.FuenteLigera, FontSize = 15, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, Text = ActualizacionTexto.Cargando };
    private readonly ContentView _izquierda = new() { Margin = new Thickness(Aire, 0) };
    private readonly ContentView _centro = new() { Margin = new Thickness(Aire, 0) };
    private readonly ContentView _derecha = new() { Margin = new Thickness(Aire, 0) };
    private readonly Label _pie = new() { FontFamily = Ds.FuenteRegular, FontSize = 14, TextColor = Ds.TintaSuave, LineBreakMode = LineBreakMode.WordWrap, Text = string.Empty };
    private readonly HojaDeActualizacion _hoja = new();
    private readonly FlujoDeActualizacion _flujo = ActualizacionUi.NuevoFlujo();

    private Pestana _pestana = Pestana.Paquetes;
    private bool _cargando, _visible;
    private string _firma = string.Empty;
    private IDispatcherTimer? _reloj;

    public ActualizacionesPage()
    {
        Shell.SetNavBarIsVisible(this, false);
        Title = "Actualizaciones";
        BackgroundColor = Ds.Lienzo;

        var textos = new VerticalStackLayout { Spacing = 6, VerticalOptions = LayoutOptions.Center };
        textos.Add(new Label { Text = "ACTUALIZACIONES", FontFamily = Ds.FuenteRegular, FontSize = 12, TextColor = Ds.TintaSuave, CharacterSpacing = 2.5 });
        textos.Add(new Label { Text = "Actualizaciones del aula", FontFamily = Ds.FuenteMedia, FontSize = 30, TextColor = Ds.Tinta, AutomationId = "actualizaciones-titulo" });
        textos.Add(_subtitulo);
        var acciones = new HorizontalStackLayout { Spacing = 12, VerticalOptions = LayoutOptions.Center };
        acciones.Add(ActualizacionUi.Accion("Actualizar", Ds.Rango.Secondary, ActualizacionUi.Seguro("Actualizar", () => CargarAsync(forzar: true)), "actualizaciones-actualizar", 170).Vista);
        acciones.Add(ActualizacionUi.Accion("‹  Menú principal", Ds.Rango.Secondary, ActualizacionUi.Seguro("Volver", AlMenuPrincipalAsync), "actualizaciones-volver", 220).Vista);
        var cabecera = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 24, Padding = new Thickness(44, 24, 48, 0), VerticalOptions = LayoutOptions.Start };
        cabecera.Add(textos, 0, 0);
        cabecera.Add(acciones, 1, 0);

        var tarjetas = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)] };
        tarjetas.Add(_izquierda, 0, 0);
        tarjetas.Add(_centro, 1, 0);
        tarjetas.Add(_derecha, 2, 0);

        var pie = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], Padding = new Thickness(0, 12, 0, 12) };
        pie.Add(new ContentView { Margin = new Thickness(Aire, 0), Content = _pie }, 1, 0);

        var raiz = new Grid { RowDefinitions = [new RowDefinition(GridLength.Star), new RowDefinition(new GridLength(4, GridUnitType.Star)), new RowDefinition(GridLength.Star)] };
        raiz.Add(cabecera, 0, 0);
        raiz.Add(tarjetas, 0, 1);
        raiz.Add(pie, 0, 2);
        raiz.Add(_hoja, 0, 0);
        Grid.SetRowSpan(_hoja, 3);
        Content = new Avacom.Lms.Ui.Controls.MarcoDs { Contenido = raiz };   // Aula · Design System: isla de marca, fecha y hora y fondo Aurora
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        _visible = true;
        try
        {
            if (!ReglasDeActualizacion.VeLasActualizaciones(Sesion.Usuario))
            {
                _subtitulo.Text = ActualizacionTexto.SoloAdministracion;
                SoloCentral(Estado(ActualizacionTexto.SoloAdministracion, ActualizacionTexto.SoloAdministracionDetalle));
                return;
            }
            await CargarAsync(forzar: true);
            IniciarReloj();
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ActualizacionesPage.OnAppearing", ex); }
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _visible = false;
        _reloj?.Stop();
        _hoja.IsVisible = false;                    // si se sale con la hoja abierta, nadie se queda esperando
    }

    /// <summary>
    /// Mientras se mira la pantalla se vuelve a leer cada pocos segundos: una memoria que se conecta aparece sola y, con una actualización en marcha, se ve cuándo termina (el aula vuelve
    /// sola). Sólo repinta si algo cambió, para no mover lo que la persona está leyendo, y nunca con la hoja abierta o con una acción en vuelo.
    /// </summary>
    private void IniciarReloj()
    {
        _reloj ??= Dispatcher.CreateTimer();
        _reloj.Interval = TimeSpan.FromSeconds(5);
        _reloj.Tick -= OnReloj;
        _reloj.Tick += OnReloj;
        _reloj.Start();
    }

    private async void OnReloj(object? sender, EventArgs e)
    {
        try
        {
            if (!_visible || _hoja.IsVisible || _cargando || _flujo.Ocupado) return;
            await CargarAsync(forzar: false);
        }
        catch (Exception ex) { RegistroDeFallos.Escribir("ops", "ActualizacionesPage.Reloj", ex); }
    }

    /// <summary>«Menú principal» lleva al menú aunque se haya llegado por otro camino; si el menú YA está a la vista no hay nada que sacar (el segundo toque de un doble toque).</summary>
    private static Task AlMenuPrincipalAsync()
    {
        var ruta = RutasDeVuelta.Hasta(Shell.Current.Navigation.NavigationStack.Select(p => p is DashboardPage).ToList(), porDefecto: "..");
        return ruta is null ? Task.CompletedTask : Shell.Current.GoToAsync(ruta);
    }

    // =============================================================================================================== leer

    private async Task CargarAsync(bool forzar)
    {
        if (_cargando || !_visible) return;
        _cargando = true;
        try
        {
            if (_flujo.Estado is null) SoloCentral(Estado("Leyendo las actualizaciones", ActualizacionTexto.Cargando));
            var ok = await _flujo.CargarAsync();
            if (!_visible) return;
            if (!ok)
            {
                var error = ActualizacionTexto.DeError(ActualizacionUi.Api.UltimoError);
                _subtitulo.Text = error.Titulo;
                // Sin conexión se conserva lo último que se vio, con el aviso encima (el aula se reinicia al aplicar: la pantalla espera sin alarmar).
                if (_flujo.Estado is not null && _flujo.SinConexion) { Pintar(forzar); return; }
                SoloCentral(Estado(error.Titulo, error.Completo, ActualizacionUi.Accion("Reintentar", Ds.Rango.Secondary, ActualizacionUi.Seguro("Reintentar", () => CargarAsync(forzar: true)), "actualizaciones-reintentar").Vista));
                _firma = string.Empty;
                return;
            }
            Pintar(forzar);
        }
        finally { _cargando = false; }
    }

    // =============================================================================================================== pintar

    private void SoloCentral(View vista)
    {
        _izquierda.Content = null;
        _derecha.Content = null;
        vista.VerticalOptions = LayoutOptions.Start;
        _centro.Content = vista;
        _pie.Text = string.Empty;
    }

    private static View Estado(string titulo, string texto, params View[] acciones)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        pila.Add(new Label { Text = titulo, FontFamily = Ds.FuenteMedia, FontSize = 24, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-estado-titulo" });
        pila.Add(new Label { Text = texto, FontFamily = Ds.FuenteRegular, FontSize = 17, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-estado-frase" });
        if (acciones.Length > 0)
        {
            var fila = ExamenUi.Fila();
            foreach (var a in acciones) fila.Add(a);
            pila.Add(fila);
        }
        return ActualizacionUi.Vidrio(pila);
    }

    /// <summary>Lo que se ve, en una línea: si no cambió desde la última vez, no se repinta (la lista que se desplaza se queda donde estaba).</summary>
    private string Firma()
    {
        var e = _flujo.Estado;
        var c = string.Join(',', _flujo.Paquetes?.CandidatosOVacio.Select(x => x.Id + (x.YaImportado ? "!" : string.Empty)) ?? []);
        var p = string.Join(',', _flujo.Paquetes?.PaquetesOVacio.Select(x => x.PaqueteId + ":" + x.Estado) ?? []);
        var h = string.Join(',', _flujo.Historial.Select(x => x.Id));
        return $"{e?.Estado}|{e?.Version}|{e?.EnCurso?.OrdenId}|{c}|{p}|{h}|{_flujo.Elegida?.PaqueteId}:{_flujo.Elegida?.Estado}:{_flujo.Elegida?.Ventana?.Desde}|{_flujo.Mensaje?.Titulo}|{_flujo.SinConexion}|{_pestana}|{_flujo.Acciones}";
    }

    private void Pintar(bool forzar)
    {
        var firma = Firma();
        if (!forzar && firma == _firma) return;
        _firma = firma;
        var e = _flujo.Estado!;
        _subtitulo.Text = $"{ActualizacionTexto.TituloDelEstado(e)} · {ActualizacionTexto.Version(e)}.";
        _izquierda.Content = new ScrollView { Content = TarjetaDelEquipo(e) };
        _centro.Content = new ScrollView { Content = TarjetaDelPaquete(e) };
        _derecha.Content = new ScrollView { Content = TarjetaDeLista(e) };
        _pie.Text = ActualizacionTexto.NucleoSigue;
    }

    // ---------------------------------------------------------------------------------------------------- este equipo (izquierda)

    private View TarjetaDelEquipo(EstadoDeActualizacion e)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        pila.Add(ActualizacionUi.Eyebrow("ESTE EQUIPO"));
        pila.Add(ExamenUi.Pildora(ActualizacionTexto.TituloDelEstado(e), ActualizacionUi.TonoDe(ActualizacionTexto.TonoDelEstado(e)), 14));
        pila.Add(new Label { Text = ActualizacionTexto.FraseDelEstado(e, _flujo.Ahora, _flujo.Zona), FontFamily = Ds.FuenteRegular, FontSize = 17, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap,
            AutomationId = "actualizaciones-estado-frase" });
        pila.Add(Ds.Separador());
        pila.Add(ActualizacionUi.Dato("Versión", e.Version));
        pila.Add(ActualizacionUi.Dato("Espacio libre", ActualizacionTexto.EspacioLibre(e.EspacioLibre)));
        pila.Add(ActualizacionUi.Dato("Volver atrás", $"{e.DiasReversion} días después de aplicar"));
        foreach (var r in e.RevertiblesOVacio)
            pila.Add(Ds.Secundario($"«{r.Nombre}»: se puede revertir {ActualizacionTexto.DiasHasta(r.RevertibleHasta, _flujo.Ahora)} más.", 13));
        pila.Add(Ds.Separador());

        pila.Add(ActualizacionUi.Eyebrow($"MÓDULOS · {e.ModulosOVacio.Count}"));
        foreach (var m in e.ModulosOVacio)
        {
            var texto = new VerticalStackLayout { Spacing = 2, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = ActualizacionTexto.NombreDeModulo(m), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta });
            texto.Add(Ds.Secundario(ActualizacionTexto.Modulo(m), 13));
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10, Margin = new Thickness(0, 0, 0, 8) };
            fila.Add(texto, 0, 0);
            if (!m.Actualizable) fila.Add(ExamenUi.Pildora("Instalador", Tono.Gris, 12), 1, 0);
            pila.Add(fila);
        }
        pila.Add(Ds.Secundario("«Instalador»: se actualiza con el instalador completo de AVACOM, no con un paquete.", 13));
        return ActualizacionUi.Tarjeta(pila);
    }

    // ---------------------------------------------------------------------------------------------------- el paquete elegido (centro, vidrio)

    private View TarjetaDelPaquete(EstadoDeActualizacion e)
    {
        var pila = new VerticalStackLayout { Spacing = 12 };
        if (_flujo.SinConexion && _flujo.Mensaje is { } sinRed)
            pila.Add(ExamenUi.Aviso(sinRed.Titulo, e.Aplicando ? "Si el aula se está reiniciando para aplicar la actualización, es normal: espera un momento." : sinRed.Completo, Tono.Ambar));
        else if (_flujo.Mensaje is { } m)
            pila.Add(ActualizacionUi.Aviso(m, _flujo.MensajeEsProblema, "actualizaciones-mensaje"));

        if (_flujo.Elegida is not { } f)
        {
            pila.Add(ActualizacionUi.Eyebrow("PAQUETE"));
            pila.Add(new Label { Text = "Elige un paquete", FontFamily = Ds.FuenteMedia, FontSize = 28, TextColor = Ds.Tinta, AutomationId = "actualizaciones-sin-paquete" });
            pila.Add(new Label
            {
                Text = "Conecta la memoria USB con el paquete de actualización que te dio AVACOM: aparece a la derecha. Tócalo para traerlo al aula; el aula comprueba que está firmado por AVACOM y que es compatible antes de tocar nada.",
                FontFamily = Ds.FuenteRegular, FontSize = 18, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap,
            });
            return ActualizacionUi.Vidrio(pila);
        }

        pila.Add(ActualizacionUi.Eyebrow("PAQUETE"));
        pila.Add(ExamenUi.Pildora(ActualizacionTexto.EstadoDelPaquete(f.Estado), ActualizacionUi.TonoDe(ActualizacionTexto.TonoDelPaquete(f.Estado)), 14));
        pila.Add(new Label { Text = f.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 26, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = "actualizaciones-paquete-nombre" });
        pila.Add(new Label { Text = _flujo.FraseDelPaquete(f), FontFamily = Ds.FuenteRegular, FontSize = 17, TextColor = Ds.TintaMedia, LineBreakMode = LineBreakMode.WordWrap,
            AutomationId = "actualizaciones-paquete-frase" });

        // Los botones, justo después de la frase: lo primero que se ve es lo que se puede hacer.
        var acciones = _flujo.Acciones;
        var fila = ExamenUi.Fila();
        if (acciones.Aplicar) fila.Add(ActualizacionUi.Accion("Aplicar ahora", Ds.Rango.Primary, ActualizacionUi.Seguro("Aplicar", AplicarAsync), "actualizaciones-aplicar").Vista);
        if (acciones.Programar) fila.Add(ActualizacionUi.Accion("Programar", Ds.Rango.Secondary, ActualizacionUi.Seguro("Programar", ProgramarAsync), "actualizaciones-programar").Vista);
        if (acciones.Desprogramar) fila.Add(ActualizacionUi.Accion("Quitar la programación", Ds.Rango.Secondary, ActualizacionUi.Seguro("Desprogramar", DesprogramarAsync), "actualizaciones-desprogramar").Vista);
        if (acciones.Revertir) fila.Add(ActualizacionUi.Accion("Volver a la versión anterior", Ds.Rango.Secondary, ActualizacionUi.Seguro("Revertir", RevertirAsync), "actualizaciones-revertir").Vista);
        if (acciones.Alguna) pila.Add(fila);
        if (!string.IsNullOrWhiteSpace(acciones.Razon)) pila.Add(Ds.Secundario(acciones.Razon!, 14));
        pila.Add(Ds.Separador());

        pila.Add(ActualizacionUi.Dato("Qué cambia", ActualizacionTexto.ModulosQueCambia(f), 130));
        foreach (var mod in f.ModulosDelManifiesto) pila.Add(Ds.Secundario("· " + ActualizacionTexto.LineaDeModulo(mod), 14));
        if (!string.IsNullOrWhiteSpace(f.Manifiesto?.Nota)) pila.Add(ActualizacionUi.Dato("Nota", f.Manifiesto!.Nota, 130));
        pila.Add(ActualizacionUi.Dato("Versión", f.VersionProducto, 130));
        pila.Add(ActualizacionUi.Dato("Peso", ActualizacionTexto.Peso(f.Bytes), 130));
        pila.Add(ActualizacionUi.Dato("Espacio", ActualizacionTexto.Espacio(f, e), 130));
        pila.Add(ActualizacionUi.Dato("Firma", string.IsNullOrWhiteSpace(f.Kid) ? "—" : "Verificada · llave " + f.Kid, 130));
        if (f.Ventana is { } v) pila.Add(ActualizacionUi.Dato("Programada", ActualizacionTexto.Ventana(v, _flujo.Ahora, _flujo.Zona), 130));
        if (f.AplicadoEn is { } aplicado) pila.Add(ActualizacionUi.Dato("Aplicada", ActualizacionTexto.FechaYHora(aplicado, _flujo.Zona), 130));
        if (f.Estado == EstadosDePaquete.Aplicado && f.RevertibleHasta is { } hasta && hasta > _flujo.Ahora)
            pila.Add(ActualizacionUi.Dato("Volver atrás", "hasta " + ActualizacionTexto.Fecha(hasta, _flujo.Zona), 130));
        if (f.IncompatibilidadesOVacio.Count > 0)
        {
            pila.Add(ActualizacionUi.Eyebrow("POR QUÉ NO ES COMPATIBLE"));
            foreach (var i in f.IncompatibilidadesOVacio) pila.Add(ExamenUi.Aviso(ActualizacionTexto.Incompatibilidad(i), null, Tono.Ambar));
        }
        return ActualizacionUi.Vidrio(pila);
    }

    // ---------------------------------------------------------------------------------------------------- paquetes e historial (derecha)

    private View TarjetaDeLista(EstadoDeActualizacion e)
    {
        var pila = new VerticalStackLayout { Spacing = 10 };
        var pestanas = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Star)], ColumnSpacing = 10 };
        pestanas.Add(Pestana_("Paquetes", Pestana.Paquetes, "actualizaciones-tab-paquetes"), 0, 0);
        pestanas.Add(Pestana_("Historial", Pestana.Historial, "actualizaciones-tab-historial"), 1, 0);
        pila.Add(pestanas);
        if (_pestana == Pestana.Historial) PintarHistorial(pila); else PintarPaquetes(pila, e);
        return ActualizacionUi.Tarjeta(pila);
    }

    private View Pestana_(string texto, Pestana pestana, string id)
    {
        var (boton, vista) = ActualizacionUi.Accion(texto, _pestana == pestana ? Ds.Rango.Primary : Ds.Rango.Secondary, ActualizacionUi.Seguro(id, () =>
        {
            _pestana = pestana;
            Pintar(forzar: true);
            return Task.CompletedTask;
        }), id);
        boton.HorizontalOptions = LayoutOptions.Fill;
        vista.HorizontalOptions = LayoutOptions.Fill;
        vista.Margin = new Thickness(0);
        return vista;
    }

    private void PintarPaquetes(VerticalStackLayout pila, EstadoDeActualizacion e)
    {
        pila.Add(ActualizacionUi.Eyebrow("EN LAS MEMORIAS"));
        var candidatos = _flujo.Paquetes?.CandidatosOVacio ?? [];
        if (candidatos.Count == 0)
            pila.Add(Ds.Secundario("No hay paquetes en las memorias USB conectadas. Conecta la memoria y toca «Actualizar».", 15));
        for (var i = 0; i < candidatos.Count; i++)
        {
            var c = candidatos[i];
            var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = c.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
            texto.Add(Ds.Secundario($"{ActualizacionTexto.Peso(c.Bytes)} · {(c.Origen == "unidad" ? "memoria o disco" : "carpeta de entrada")}", 13));
            var puede = _flujo.PuedeImportar(c);
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            fila.Add(texto, 0, 0);
            fila.Add(ExamenUi.Pildora(c.YaImportado ? "Ya está en el aula" : puede ? "Traer al aula" : "Espera", c.YaImportado ? Tono.Exito : puede ? Tono.Info : Tono.Gris, 12), 1, 0);
            var candidato = c;
            pila.Add(ActualizacionUi.Tocable(fila, ActualizacionUi.Seguro($"Candidato{i}", () => TocarCandidatoAsync(candidato)),
                c.YaImportado ? $"Ver el paquete {c.Nombre}" : $"Traer al aula el paquete {c.Nombre}", $"actualizaciones-candidato-{i}"));
        }
        pila.Add(Ds.Separador());

        pila.Add(ActualizacionUi.Eyebrow("EN EL AULA"));
        var fichas = _flujo.Paquetes?.PaquetesOVacio ?? [];
        if (fichas.Count == 0) pila.Add(Ds.Secundario("Todavía no has traído ningún paquete.", 15));
        for (var i = 0; i < fichas.Count; i++)
        {
            var f = fichas[i];
            var texto = new VerticalStackLayout { Spacing = 3, VerticalOptions = LayoutOptions.Center };
            texto.Add(new Label { Text = f.Nombre, FontFamily = Ds.FuenteMedia, FontSize = 17, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.TailTruncation });
            texto.Add(Ds.Secundario($"Versión {f.VersionProducto} · {ActualizacionTexto.Peso(f.Bytes)}", 13));
            var fila = new Grid { ColumnDefinitions = [new ColumnDefinition(GridLength.Star), new ColumnDefinition(GridLength.Auto)], ColumnSpacing = 10 };
            fila.Add(texto, 0, 0);
            fila.Add(ExamenUi.Pildora(ActualizacionTexto.EstadoDelPaquete(f.Estado), ActualizacionUi.TonoDe(ActualizacionTexto.TonoDelPaquete(f.Estado)), 12), 1, 0);
            var id = f.PaqueteId;
            pila.Add(ActualizacionUi.Tocable(fila, ActualizacionUi.Seguro($"Paquete{i}", () => ElegirAsync(id)), $"Ver el paquete {f.Nombre}", $"actualizaciones-paquete-{i}", _flujo.Elegida?.PaqueteId == f.PaqueteId));
        }
    }

    private void PintarHistorial(VerticalStackLayout pila)
    {
        pila.Add(ActualizacionUi.Eyebrow("LO ÚLTIMO QUE PASÓ"));
        if (_flujo.Historial.Count == 0) pila.Add(Ds.Secundario("Todavía no hay movimientos.", 15));
        var i = 0;
        foreach (var h in _flujo.Historial)
        {
            var texto = new VerticalStackLayout { Spacing = 2, Margin = new Thickness(0, 0, 0, 8) };
            texto.Add(new Label { Text = ActualizacionTexto.Hecho(h), FontFamily = Ds.FuenteMedia, FontSize = 16, TextColor = Ds.Tinta, LineBreakMode = LineBreakMode.WordWrap, AutomationId = $"actualizaciones-hecho-{i++}" });
            texto.Add(Ds.Secundario(ActualizacionTexto.FechaYHora(h.En, _flujo.Zona) + (h.VersionProducto is { Length: > 0 } v ? $" · versión {v}" : string.Empty), 13));
            pila.Add(texto);
        }
    }

    // =============================================================================================================== acciones

    private async Task TocarCandidatoAsync(CandidatoDePaquete c)
    {
        if (_hoja.IsVisible || _flujo.Ocupado) return;
        if (c.YaImportado) await _flujo.ElegirAsync(c.Importado!);
        else if (_flujo.PuedeImportar(c)) await _flujo.ImportarAsync(c.Id);
        else return;
        Pintar(forzar: true);
    }

    private async Task ElegirAsync(string id)
    {
        if (_hoja.IsVisible || _flujo.Ocupado) return;
        await _flujo.ElegirAsync(id);
        Pintar(forzar: true);
    }

    /// <summary>Con la hoja abierta, las acciones de la pantalla no hacen nada (cubre un segundo toque que llegó en cola y a UI Automation, que invoca sin mirar el velo).</summary>
    private bool Bloqueada => _hoja.IsVisible || _flujo.Ocupado;

    private async Task AplicarAsync()
    {
        if (Bloqueada) return;
        if (await _hoja.AplicarAsync(_flujo)) await CargarAsync(forzar: true);
        else Pintar(forzar: true);
    }

    private async Task RevertirAsync()
    {
        if (Bloqueada) return;
        if (await _hoja.RevertirAsync(_flujo)) await CargarAsync(forzar: true);
        else Pintar(forzar: true);
    }

    private async Task ProgramarAsync()
    {
        if (Bloqueada) return;
        if (await _hoja.ProgramarAsync(_flujo)) await CargarAsync(forzar: true);
    }

    private async Task DesprogramarAsync()
    {
        if (Bloqueada) return;
        await _flujo.DesprogramarAsync();
        Pintar(forzar: true);
    }
}
